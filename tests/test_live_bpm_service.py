import os
import queue
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.live_bpm import (
    LiveBPMCandidate,
    LiveBPMSession,
    LiveBPMService,
)
from rb_ss_bridge_v2.models import BridgeEvent, Ev, TrackMetadata
from rb_ss_bridge_v2.rb_memory import PositionCache
from rb_ss_bridge_v2.state_manager import StateManager


class FakeLiveBPMReader:
    def __init__(self) -> None:
        self.session = LiveBPMSession(pid=os.getpid(), base=0x1000, task=1)
        self.candidate = LiveBPMCandidate(0x2000, "f32", "fake")
        self.values: list[float | Exception] = []
        self.scan_calls = 0
        self.attach_calls = 0

    def attach(self):
        self.attach_calls += 1
        return self.session

    def scan_candidates(self, session, deck, expect_bpm, library_bpm, limit):
        self.scan_calls += 1
        return [self.candidate]

    def read_candidate(self, session, candidate):
        if not self.values:
            return 120.0
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class LiveBPMServiceTests(unittest.TestCase):
    def test_promotes_candidate_that_moves_to_current_hint(self) -> None:
        reader = FakeLiveBPMReader()
        reader.values = [120.0, 122.0]
        service = LiveBPMService(reader=reader, disabled=False)

        service.update_hint(1, 120.0, 120.0)
        service.tick()
        service.tick()
        time.sleep(0.22)
        service.update_hint(1, 122.0, 120.0)
        service.tick()

        self.assertEqual(service.get_bpm(1), 122.0)
        status = service.get_status(1)
        self.assertIsNotNone(status)
        self.assertEqual(status.bpm, 122.0)
        self.assertEqual(status.addr, 0x2000)

    def test_does_not_promote_static_match(self) -> None:
        reader = FakeLiveBPMReader()
        reader.values = [120.0, 120.0, 120.0]
        service = LiveBPMService(reader=reader, disabled=False)

        service.update_hint(1, 120.0, 120.0)
        service.tick()
        service.tick()
        with service._lock:
            service._deck[1].sample_start_at -= 60.0
        time.sleep(0.22)
        service.tick()

        self.assertIsNone(service.get_bpm(1))

    def test_restart_invalidates_validated_candidate(self) -> None:
        reader = FakeLiveBPMReader()
        reader.values = [120.0, 122.0]
        service = LiveBPMService(reader=reader, disabled=False)

        service.update_hint(1, 120.0, 120.0)
        service.tick()
        service.tick()
        time.sleep(0.22)
        service.update_hint(1, 122.0, 120.0)
        service.tick()
        self.assertEqual(service.get_bpm(1), 122.0)

        reader.session = LiveBPMSession(pid=os.getpid(), base=0x2000, task=1)
        service._last_session_check_at -= 10.0
        service.tick()

        self.assertIsNone(service.get_bpm(1))

    def test_invalid_reads_clear_validated_candidate(self) -> None:
        reader = FakeLiveBPMReader()
        reader.values = [120.0, 122.0]
        service = LiveBPMService(reader=reader, disabled=False)

        service.update_hint(1, 120.0, 120.0)
        service.tick()
        service.tick()
        time.sleep(0.22)
        service.update_hint(1, 122.0, 120.0)
        service.tick()
        self.assertEqual(service.get_bpm(1), 122.0)

        reader.values = [OSError("gone"), OSError("gone"), OSError("gone")]
        service.tick()
        service.tick()
        service.tick()

        self.assertIsNone(service.get_bpm(1))

    def test_session_check_does_not_reattach_when_pid_is_unchanged(self) -> None:
        reader = FakeLiveBPMReader()
        service = LiveBPMService(reader=reader, disabled=False)

        with patch("rb_ss_bridge_v2.live_bpm.get_rb_pid", return_value=reader.session.pid):
            service.tick()
            self.assertEqual(reader.attach_calls, 1)
            service._last_session_check_at -= 10.0
            service.tick()

        self.assertEqual(reader.attach_calls, 1)


class FakeOutput:
    def __init__(self) -> None:
        self.loads: list[tuple[int, TrackMetadata, int, str]] = []
        self.bpms: list[tuple[int, float]] = []
        self.clears: list[int] = []

    def _sub(self, *args, **kwargs):
        pass

    def send_deck_load(self, deck, meta, active, play="on"):
        self.loads.append((deck, meta, active, play))

    def send_loop_on(self, deck):
        pass

    def send_loop_off(self, deck):
        pass

    def send_deck_play(self, deck, state):
        pass

    def send_deck_clear(self, deck):
        self.clears.append(deck)

    def send_bpm(self, deck, bpm):
        self.bpms.append((deck, bpm))


class FakeLiveProvider:
    def __init__(self, bpm: float | None) -> None:
        self.bpm = bpm

    def get_bpm(self, deck):
        return self.bpm

    def update_hint(self, deck, bpm, library_bpm=0.0):
        pass

    def invalidate(self):
        self.bpm = None


class StateManagerLiveBPMTests(unittest.TestCase):
    def test_autoloop_arm_uses_live_bpm_snapshot(self) -> None:
        output = FakeOutput()
        live = FakeLiveProvider(123.45)
        sm = StateManager(queue.Queue(), PositionCache(), output, live_bpm=live, live_bpm_follow=False)
        deck = sm._deck[1]
        deck.meta.filepath = "/tmp/test.wav"
        deck.meta.bpm = 120.0

        sm._apply_lighting(1, "autoloop", 1000, 120.0)

        self.assertEqual(sm._os.autoloop_arm_bpm, 123.45)
        self.assertTrue(output.loads)
        self.assertTrue(all(load[1].bpm == 123.45 for load in output.loads))

        live.bpm = 130.0
        self.assertEqual(sm._os.autoloop_arm_bpm, 123.45)

    def test_autoloop_arm_falls_back_without_live_bpm(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.meta.filepath = "/tmp/test.wav"
        deck.meta.bpm = 120.0

        sm._apply_lighting(1, "autoloop", 1000, 120.0)

        self.assertEqual(sm._os.autoloop_arm_bpm, 120.0)
        self.assertTrue(all(load[1].bpm == 120.0 for load in output.loads))

    def test_live_bpm_status_text_reports_current_live_bpm(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(124.5), live_bpm_follow=False,
        )
        sm._live_bpm.get_status = lambda deck: type(  # type: ignore[attr-defined]
            "Status",
            (),
            {
                "bpm": 124.5,
                "updated_at": time.monotonic(),
                "addr": 0x2000,
                "type_name": "f32",
            },
        )()

        text = sm._live_bpm_status_text(1)

        self.assertIn("live_bpm=124.50", text)
        self.assertIn("live_addr=0x2000/f32", text)

    def test_autoloop_idle_transition_ignores_short_pause_blip(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        sm._os.lighting_mode = "autoloop"
        sm._os.lighting_desired = "autoloop"
        sm._os.lighting_stable_since = 100.0

        sm._update_lighting(1, deck, False, 1000, 120.0, 100.6)

        self.assertEqual(sm._os.lighting_mode, "autoloop")
        self.assertEqual(output.clears, [])

    def _autoloop_sm(self, live_bpm: FakeLiveProvider, follow: bool = True):
        output = FakeOutput()
        sm = StateManager(queue.Queue(), PositionCache(), output, live_bpm=live_bpm, live_bpm_follow=follow)
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 128.0
        sm._os.last_sent_bpm = 128.0
        sm._os.was_playing = True
        sm._deck[1].playing = True
        return sm, output

    def test_live_bpm_follow_default_off_keeps_v1_timing(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=False)

        bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_schedules_and_applies_at_phrase_beat(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)

        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0), 128.0)
        self.assertEqual(sm._os.pending_live_bpm, 132.0)
        self.assertEqual(sm._os.pending_live_bpm_target_beat, 0)
        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.4, 101.1), 128.0)
        self.assertEqual(sm._os.pending_live_bpm_target_beat, 0)
        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.4, 101.6), 128.0)
        self.assertEqual(sm._os.pending_live_bpm_target_beat, 9)

        bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 9.0, 101.7)

        self.assertEqual(bpm, 132.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 132.0)
        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(output.bpms, [(1, 132.0), (2, 132.0), (3, 132.0), (4, 132.0)])

    def test_live_bpm_follow_replaces_pending_value_before_boundary(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)

        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        live.bpm = 134.0
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.4, 100.5)

        self.assertEqual(sm._os.pending_live_bpm, 134.0)
        self.assertEqual(sm._os.pending_live_bpm_target_beat, 0)
        self.assertAlmostEqual(sm._os.pending_live_bpm_since, 100.5)

    def test_live_bpm_follow_clears_pending_when_live_bpm_unvalidated(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)

        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        live.bpm = None
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.4, 100.5)

        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_waits_until_resume_settle_completed(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._os.was_playing = False

        bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_clears_pending_on_master_change(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        sm._on_master_changed(2, "test")

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_deck, 0)

    def test_live_bpm_follow_clears_pending_on_active_track_load(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        sm._on_track_loaded(1, "new track", BridgeEvent(Ev.TRACK_LOADED, 1, {}, "test"))

        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_clears_pending_on_rekordbox_restart(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        sm._handle_event(BridgeEvent(Ev.RB_RESTARTED, 1, {"pid": 123}, "test"))

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_deck, 0)
        self.assertIsNone(live.bpm)

    def test_next_live_bpm_follow_beat_uses_9_17_25_pattern(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)

        self.assertEqual(sm._next_live_bpm_follow_beat(1.0), 9)
        self.assertEqual(sm._next_live_bpm_follow_beat(8.1), 9)
        self.assertEqual(sm._next_live_bpm_follow_beat(9.0), 17)
        self.assertEqual(sm._next_live_bpm_follow_beat(24.9), 25)


if __name__ == "__main__":
    unittest.main()
