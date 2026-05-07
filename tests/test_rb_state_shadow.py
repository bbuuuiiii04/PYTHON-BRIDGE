"""Unit tests for rb_state shadow parity helpers."""
from __future__ import annotations

import plistlib
import queue
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import BridgeEvent, Ev
from rb_ss_bridge_v2.rb_state_shadow import (
    RBStateParityMonitor,
    bpm_matches,
    bridge_deck_from_rb_index,
    classify_transport_pair,
    compare_events,
    normalize_rb_version,
    normalize_title,
    read_rekordbox_version,
    title_is_tl_prefix,
    titles_match,
)


class NormalizationTests(unittest.TestCase):
    def test_title_normalization_ignores_case_and_whitespace(self) -> None:
        self.assertEqual(normalize_title("  My   Track - ARTIST  "), "my track - artist")
        self.assertTrue(titles_match("My   Track - Artist", " my track - artist "))

    def test_title_comparison_detects_different_titles(self) -> None:
        self.assertFalse(titles_match("Track A - Artist", "Track B - Artist"))

    def test_tl_prefix_title_detection(self) -> None:
        self.assertTrue(title_is_tl_prefix("Where You Are (Crankdat Remi", "Where You Are (Crankdat Remix)"))
        self.assertFalse(title_is_tl_prefix("Track B", "Track A"))

    def test_bpm_epsilon(self) -> None:
        self.assertTrue(bpm_matches(128.0, 128.08))
        self.assertFalse(bpm_matches(128.0, 128.2))
        self.assertFalse(bpm_matches("nan", 128.0))

    def test_rb_zero_based_deck_mapping(self) -> None:
        self.assertEqual([bridge_deck_from_rb_index(i) for i in range(4)], [1, 2, 1, 2])

    def test_version_normalization_strips_build_component(self) -> None:
        self.assertEqual(normalize_rb_version("7.2.11.0342"), "7.2.11")
        self.assertEqual(normalize_rb_version(" 7.2.14 "), "7.2.14")
        self.assertEqual(normalize_rb_version("not-a-version"), "")


class CompareEventsTests(unittest.TestCase):
    def test_track_loaded_title_match(self) -> None:
        tl = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "My Track - Artist"},
            source="tl_log",
        )
        rb = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": " my   track - artist "},
            source="rb_state",
        )
        self.assertEqual(compare_events(tl, rb), (True, "match"))

    def test_track_loaded_title_mismatch_reason(self) -> None:
        tl = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "Track A"},
            source="tl_log",
        )
        rb = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "Track B"},
            source="rb_state",
        )
        self.assertEqual(compare_events(tl, rb), (False, "title differs"))

    def test_track_loaded_tl_prefix_reason(self) -> None:
        tl = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "John Summit - Where You Are (Crankdat Remi"},
            source="tl_log",
        )
        rb = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "John Summit - Where You Are (Crankdat Remix)"},
            source="rb_state",
        )
        self.assertEqual(compare_events(tl, rb), (False, "title_truncated_prefix"))

    def test_deck_mismatch_reason(self) -> None:
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log")
        rb = BridgeEvent(kind=Ev.PLAY, deck=2, source="rb_state")
        self.assertEqual(compare_events(tl, rb), (False, "deck differs"))

    def test_bpm_mismatch_reason_includes_delta(self) -> None:
        tl = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 128.0}, source="engine_state")
        rb = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 128.25}, source="rb_state")
        ok, reason = compare_events(tl, rb)
        self.assertFalse(ok)
        self.assertIn("BPM delta", reason)

    def test_transport_tight_play_is_strong_match(self) -> None:
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=100.000)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=100.050)
        self.assertEqual(classify_transport_pair(tl, rb), (True, "strong match"))

    def test_transport_late_play_is_weak_inside_window(self) -> None:
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=100.000)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=100.300)
        self.assertEqual(classify_transport_pair(tl, rb), (True, "late / weak match"))

    def test_transport_play_outside_tight_window_is_mismatch(self) -> None:
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=100.000)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=100.600)
        self.assertEqual(classify_transport_pair(tl, rb), (False, "outside play window"))

    def test_transport_pause_rb_leads_tl_as_expected_lag(self) -> None:
        tl = BridgeEvent(kind=Ev.PAUSE, deck=1, source="tl_log", mono=101.000)
        rb = BridgeEvent(kind=Ev.PAUSE, deck=1, source="rb_state", mono=100.250)
        self.assertEqual(
            classify_transport_pair(tl, rb),
            (True, "expected TL-lag pause match"),
        )

    def test_transport_pause_outside_wide_window_is_mismatch(self) -> None:
        tl = BridgeEvent(kind=Ev.PAUSE, deck=1, source="tl_log", mono=102.000)
        rb = BridgeEvent(kind=Ev.PAUSE, deck=1, source="rb_state", mono=100.000)
        self.assertEqual(classify_transport_pair(tl, rb), (False, "outside pause window"))


class ParityMonitorTests(unittest.TestCase):
    def test_transport_candidate_inside_window_is_popped(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=100.100)
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=100.000)
        monitor._remember(monitor._pending_rb, (Ev.PLAY, 1), rb)
        match = monitor._pop_transport_candidate(monitor._pending_rb, tl)
        self.assertIsNotNone(match)
        self.assertEqual(monitor._pending_rb, {})

    def test_transport_candidate_outside_window_is_not_popped(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=100.800)
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=100.000)
        monitor._remember(monitor._pending_rb, (Ev.PLAY, 1), rb)
        match = monitor._pop_transport_candidate(monitor._pending_rb, tl)
        self.assertIsNone(match)
        self.assertIn((Ev.PLAY, 1), monitor._pending_rb)

    def test_pause_candidate_uses_wider_window(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        rb = BridgeEvent(kind=Ev.PAUSE, deck=1, source="rb_state", mono=100.000)
        tl = BridgeEvent(kind=Ev.PAUSE, deck=1, source="tl_log", mono=101.000)
        monitor._remember(monitor._pending_rb, (Ev.PAUSE, 1), rb)
        match = monitor._pop_transport_candidate(monitor._pending_rb, tl)
        self.assertIsNotNone(match)

    def test_engine_state_master_summary_is_not_edge_pending(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        ev = BridgeEvent(kind=Ev.MASTER_CHANGED, deck=1, source="engine_state")
        monitor._accept_tl(ev)
        self.assertEqual(monitor._pending_tl, {})
        self.assertIn(1, monitor._last_master_summary)

    def test_tl_log_master_edge_still_uses_pending_matcher(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        ev = BridgeEvent(kind=Ev.MASTER_CHANGED, deck=1, source="tl_log")
        monitor._accept_tl(ev)
        self.assertIn((Ev.MASTER_CHANGED, 1), monitor._pending_tl)

    def test_rb_bpm_updates_latest_value_without_pending_mismatch(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        rb = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.0}, source="rb_state")
        monitor._accept_rb(rb)
        self.assertIn(1, monitor._last_rb_bpm)
        self.assertEqual(monitor._pending_rb, {})

    def test_engine_state_bpm_compares_against_recent_rb_value(self) -> None:
        times = iter([100.0, 100.0, 100.0, 101.0])
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: next(times), bootstrap_s=0.0)
        rb = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.04}, source="rb_state")
        tl = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.0}, source="engine_state")
        monitor._accept_rb(rb)
        monitor._accept_tl(tl)
        self.assertEqual(monitor._pending_tl, {})
        self.assertEqual(monitor._pending_rb, {})

    def test_engine_state_bpm_without_recent_rb_value_does_not_create_pending_pair(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        tl = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.0}, source="engine_state")
        monitor._accept_tl(tl)
        self.assertEqual(monitor._pending_tl, {})
        self.assertEqual(monitor._pending_rb, {})

    def test_track_master_and_bpm_counters_feed_summary(self) -> None:
        times = iter([100.0, 100.0, 100.0, 101.0])
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: next(times), bootstrap_s=0.0)
        tl_track = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "Track"},
            source="tl_log",
            mono=10.0,
        )
        rb_track = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "Track"},
            source="rb_state",
            mono=10.02,
        )
        rb_bpm = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.0}, source="rb_state")
        tl_bpm = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.02}, source="engine_state")

        monitor._log_pair(tl_track, rb_track)
        monitor._accept_master_summary(BridgeEvent(kind=Ev.MASTER_CHANGED, deck=1, source="engine_state"))
        monitor._accept_rb(rb_bpm)
        monitor._accept_tl(tl_bpm)

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("track_loaded agree=1 title_truncated_prefix=0 mismatch=0", summary)
        self.assertIn("master_changed agree=0 mismatch=0 summary=1", summary)
        self.assertIn("bpm_update agree=1 mismatch=0", summary)

    def test_track_title_truncated_prefix_counter_feeds_summary(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        tl_track = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "John Summit - Where You Are (Crankdat Remi"},
            source="tl_log",
            mono=10.0,
        )
        rb_track = BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=1,
            payload={"title": "John Summit - Where You Are (Crankdat Remix)"},
            source="rb_state",
            mono=10.02,
        )
        monitor._log_pair(tl_track, rb_track)
        self.assertIn(
            "track_loaded agree=0 title_truncated_prefix=1 mismatch=0",
            "\n".join(monitor.summary_lines()),
        )

    def test_bpm_outside_window_counter_feeds_summary(self) -> None:
        times = iter([100.0, 100.0, 110.5])
        monitor = RBStateParityMonitor(
            queue.Queue(),
            clock=lambda: next(times),
            bootstrap_s=0.0,
            bpm_window_s=5.0,
        )
        rb = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.0}, source="rb_state")
        tl = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 130.0}, source="engine_state")
        monitor._accept_rb(rb)
        monitor._accept_tl(tl)
        self.assertIn("summary_outside_window=1", "\n".join(monitor.summary_lines()))

    def test_transport_strong_matches_are_split_normal_vs_micro_burst(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        first_tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=10.0)
        first_rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=10.04)
        second_tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=10.5)
        second_rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=10.55)

        monitor._log_transport_pair(first_tl, first_rb)
        monitor._log_transport_pair(second_tl, second_rb)

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play normal{strong_match=1", summary)
        self.assertIn("micro_burst{strong_match=1", summary)

    def test_transport_load_adjacent_context_counts_true(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        load = BridgeEvent(kind=Ev.TRACK_LOADED, deck=1, source="tl_log", mono=9.0)
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=10.0)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=10.04)

        monitor._accept_tl(load)
        monitor._log_transport_pair(tl, rb)

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play load_adjacent=true normal{strong_match=1", summary)
        self.assertIn("play load_adjacent=false normal{strong_match=0", summary)

    def test_transport_load_adjacent_context_counts_false_outside_window(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        load = BridgeEvent(kind=Ev.TRACK_LOADED, deck=1, source="tl_log", mono=9.0)
        tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=13.5)
        rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=13.54)

        monitor._accept_tl(load)
        monitor._log_transport_pair(tl, rb)

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play load_adjacent=false normal{strong_match=1", summary)
        self.assertIn("play load_adjacent=true normal{strong_match=0", summary)

    def test_transport_outside_micro_burst_threshold_counts_normal(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        first_tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=10.0)
        first_rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=10.04)
        second_tl = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=11.2)
        second_rb = BridgeEvent(kind=Ev.PLAY, deck=1, source="rb_state", mono=11.24)

        monitor._log_transport_pair(first_tl, first_rb)
        monitor._log_transport_pair(second_tl, second_rb)

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play normal{strong_match=2", summary)
        self.assertIn("micro_burst{strong_match=0", summary)

    def test_expected_pause_lag_counter_is_scoped(self) -> None:
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: 100.0, bootstrap_s=0.0)
        tl = BridgeEvent(kind=Ev.PAUSE, deck=1, source="tl_log", mono=20.0)
        rb = BridgeEvent(kind=Ev.PAUSE, deck=1, source="rb_state", mono=19.25)
        monitor._log_transport_pair(tl, rb)
        self.assertIn(
            "pause normal{strong_match=0 weak_late_match=0 "
            "expected_tl_lag_pause_match=1",
            "\n".join(monitor.summary_lines()),
        )

    def test_transport_missing_pair_counter_is_scoped(self) -> None:
        now = [100.0]
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: now[0], bootstrap_s=0.0)
        first = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=30.0)
        second = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=30.5)

        monitor._log_mismatch(first, None, "missing rb_state pair")
        now[0] += 11.0
        monitor._log_mismatch(second, None, "missing rb_state pair")

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play normal{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=1", summary)
        self.assertIn("micro_burst{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=1", summary)

    def test_transport_duplicate_ordering_counter_is_scoped(self) -> None:
        now = [100.0]
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: now[0], bootstrap_s=0.0)
        first = BridgeEvent(kind=Ev.PAUSE, deck=1, source="rb_state", mono=40.0)
        second = BridgeEvent(kind=Ev.PAUSE, deck=1, source="rb_state", mono=40.4)

        monitor._remember(monitor._pending_rb, (Ev.PAUSE, 1), first, side="rb")
        now[0] += 11.0
        monitor._remember(monitor._pending_rb, (Ev.PAUSE, 1), second, side="rb")

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("pause normal{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=0 duplicate_ordering=0", summary)
        self.assertIn("micro_burst{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=0 duplicate_ordering=1", summary)

    def test_expired_pending_transport_uses_tl_micro_burst_scope(self) -> None:
        now = [100.0]
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: now[0], bootstrap_s=0.0)
        play = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=50.0)
        pause = BridgeEvent(kind=Ev.PAUSE, deck=1, source="tl_log", mono=50.4)

        monitor._accept_tl(play)
        monitor._accept_tl(pause)
        now[0] += 3.0
        monitor._expire_old()

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play normal{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=1", summary)
        self.assertIn("pause normal{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=0", summary)
        self.assertIn("micro_burst{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=1", summary)

    def test_expired_pending_transport_preserves_load_adjacent_context(self) -> None:
        now = [100.0]
        monitor = RBStateParityMonitor(queue.Queue(), clock=lambda: now[0], bootstrap_s=0.0)
        load = BridgeEvent(kind=Ev.TRACK_LOADED, deck=1, source="tl_log", mono=60.0)
        play = BridgeEvent(kind=Ev.PLAY, deck=1, source="tl_log", mono=60.5)

        monitor._accept_tl(load)
        monitor._accept_tl(play)
        now[0] += 3.0
        monitor._expire_old()

        summary = "\n".join(monitor.summary_lines())
        self.assertIn("play load_adjacent=true normal{strong_match=0 weak_late_match=0 expected_tl_lag_pause_match=0 missing_pair=1", summary)


class VersionLookupTests(unittest.TestCase):
    def test_read_rekordbox_version_from_plist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "rekordbox.app"
            info = app / "Contents" / "Info.plist"
            info.parent.mkdir(parents=True)
            with open(info, "wb") as fh:
                plistlib.dump({"CFBundleShortVersionString": "7.2.11.0342"}, fh)
            self.assertEqual(read_rekordbox_version((app,)), "7.2.11")

    def test_read_rekordbox_version_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_rekordbox_version((Path(tmp) / "missing.app",)), "")


if __name__ == "__main__":
    unittest.main()
