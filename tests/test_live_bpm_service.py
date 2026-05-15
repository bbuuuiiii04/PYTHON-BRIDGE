import os
import queue
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.live_bpm import (
    LIVE_BPM_DIAGNOSTICS_ENV,
    LIVE_BPM_DIRECT_SOURCE,
    LIVE_BPM_DISCOVERY_SOURCE,
    LIVE_BPM_FALLBACK_SOURCE,
    LiveBPMCandidate,
    LiveBPMSession,
    LiveBPMService,
    MachLiveBPMReader,
    _Validated,
)
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot, TrackMetadata
from rb_ss_bridge_v2.rb_offsets import ChainEntry, RBOffsetVersion
from rb_ss_bridge_v2.rb_memory import PositionCache
from rb_ss_bridge_v2 import state_manager as sm_mod
from rb_ss_bridge_v2.state_manager import (
    StateManager,
    _beatgrid_elapsed_for_abs_beat,
    _compute_beatgrid_position,
)
from rb_ss_bridge_v2.autoloop_controller import AutoloopTickContext


class FakeLiveBPMReader:
    def __init__(self) -> None:
        self.session = LiveBPMSession(pid=os.getpid(), base=0x1000, task=1)
        self.candidate = LiveBPMCandidate(0x2000, "f32", "fake")
        self.values: list[float | Exception] = []
        self.scan_calls = 0
        self.attach_calls = 0
        self.on_scan = None

    def attach(self):
        self.attach_calls += 1
        return self.session

    def scan_candidates(self, session, deck, expect_bpm, library_bpm, limit):
        self.scan_calls += 1
        if self.on_scan is not None:
            self.on_scan()
        return [self.candidate]

    def read_candidate(self, session, candidate):
        if not self.values:
            return 120.0
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeDirectLiveBPMReader(FakeLiveBPMReader):
    def __init__(self) -> None:
        super().__init__()
        self.candidate = LiveBPMCandidate(
            0x3000,
            "f32",
            "offset_table",
            "rb_offsets:test:deck1",
            0,
            LIVE_BPM_DIRECT_SOURCE,
        )

    def direct_candidate(self, session, deck):
        return self.candidate


class FakeUnsupportedDirectLiveBPMReader(FakeLiveBPMReader):
    def __init__(self) -> None:
        super().__init__()
        self.direct_calls = 0

    def direct_candidate(self, session, deck):
        self.direct_calls += 1
        return None


class LiveBPMServiceTests(unittest.TestCase):
    def test_promotes_direct_offset_candidate_without_hint_or_movement_validation(self) -> None:
        reader = FakeDirectLiveBPMReader()
        reader.values = [124.0]
        service = LiveBPMService(reader=reader, disabled=False)

        with self.assertLogs("live_bpm", level="INFO") as logs:
            service.tick()

        self.assertEqual(service.get_bpm(1), 124.0)
        status = service.get_status(1)
        self.assertIsNotNone(status)
        self.assertEqual(status.addr, 0x3000)
        self.assertEqual(status.source, LIVE_BPM_DIRECT_SOURCE)
        self.assertTrue(
            any("[LBPM][DIRECT] deck1 first_read_attempt=1 source=offset_table" in line for line in logs.output)
        )
        self.assertTrue(any("[LBPM][DIRECT] deck1" in line and "accepted=1" in line for line in logs.output))
        self.assertTrue(
            any(
                "[LBPM][SOURCE] deck1" in line
                and f"source={LIVE_BPM_DIRECT_SOURCE}" in line
                and "reason=direct_accept" in line
                and "direct_before_hint=1" in line
                for line in logs.output
            )
        )
        summary = service.get_summary(1)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.current_source, LIVE_BPM_DIRECT_SOURCE)
        self.assertEqual(summary.first_source, LIVE_BPM_DIRECT_SOURCE)
        self.assertEqual(summary.direct_accepted_count, 1)
        self.assertEqual(summary.direct_rejected_count, 0)
        self.assertEqual(summary.last_accepted_bpm, 124.0)
        self.assertTrue(summary.direct_before_hint)

    def test_diagnostics_mode_logs_summary_on_first_direct_source(self) -> None:
        reader = FakeDirectLiveBPMReader()
        reader.values = [126.0]

        with patch.dict(os.environ, {LIVE_BPM_DIAGNOSTICS_ENV: "1"}):
            service = LiveBPMService(reader=reader, disabled=False)
            with self.assertLogs("live_bpm", level="INFO") as logs:
                service.tick()

        self.assertTrue(
            any(
                "[LBPM][SUMMARY] deck1" in line
                and f"source={LIVE_BPM_DIRECT_SOURCE}" in line
                and "first_source=offset_table" in line
                and "direct_ok=1" in line
                and "direct_before_hint=1" in line
                for line in logs.output
            )
        )

    def test_direct_offset_candidate_still_fails_closed_on_invalid_read(self) -> None:
        reader = FakeDirectLiveBPMReader()
        reader.values = [float("nan")]
        service = LiveBPMService(reader=reader, disabled=False)

        with self.assertLogs("live_bpm", level="INFO") as logs:
            service.tick()

        self.assertIsNone(service.get_bpm(1))
        self.assertTrue(
            any("[LBPM][DIRECT] deck1 first_read_attempt=1 source=offset_table" in line for line in logs.output)
        )
        self.assertTrue(any("rejected reason=invalid_value" in line for line in logs.output))
        self.assertTrue(
            any(
                "[LBPM][SOURCE] deck1" in line
                and f"source={LIVE_BPM_FALLBACK_SOURCE}" in line
                and "reason=attach" in line
                for line in logs.output
            )
        )
        summary = service.get_summary(1)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.current_source, LIVE_BPM_FALLBACK_SOURCE)
        self.assertEqual(summary.first_source, "")
        self.assertEqual(summary.direct_accepted_count, 0)
        self.assertEqual(summary.direct_rejected_count, 1)

    def test_direct_offset_candidate_still_fails_closed_on_unreadable_value(self) -> None:
        reader = FakeDirectLiveBPMReader()
        reader.values = [OSError("gone")]
        service = LiveBPMService(reader=reader, disabled=False)

        with self.assertLogs("live_bpm", level="INFO") as logs:
            service.tick()

        self.assertIsNone(service.get_bpm(1))
        self.assertTrue(any("rejected reason=value_unreadable" in line for line in logs.output))
        summary = service.get_summary(1)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.current_source, LIVE_BPM_FALLBACK_SOURCE)
        self.assertEqual(summary.direct_rejected_count, 1)

    def test_unsupported_direct_path_still_falls_back_to_discovery_validation(self) -> None:
        reader = FakeUnsupportedDirectLiveBPMReader()
        reader.values = [120.0, 122.0]
        service = LiveBPMService(reader=reader, disabled=False)

        service.update_hint(1, 120.0, 120.0)
        service.tick()
        service.tick()
        time.sleep(0.22)
        service.update_hint(1, 122.0, 120.0)
        service.tick()

        self.assertGreater(reader.direct_calls, 0)
        self.assertEqual(service.get_bpm(1), 122.0)
        status = service.get_status(1)
        self.assertIsNotNone(status)
        self.assertEqual(status.source, LIVE_BPM_DISCOVERY_SOURCE)
        summary = service.get_summary(1)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.current_source, LIVE_BPM_DISCOVERY_SOURCE)
        self.assertEqual(summary.first_source, LIVE_BPM_DISCOVERY_SOURCE)
        self.assertEqual(summary.direct_accepted_count, 0)

    def test_summary_lines_report_fallback_and_source_counts(self) -> None:
        reader = FakeUnsupportedDirectLiveBPMReader()
        service = LiveBPMService(reader=reader, disabled=False)

        service.tick()

        lines = service.summary_lines()
        self.assertTrue(
            any(
                "[LBPM][SUMMARY] deck1" in line
                and f"source={LIVE_BPM_FALLBACK_SOURCE}" in line
                and "first_source=<none>" in line
                and "direct_ok=0" in line
                and "direct_reject=0" in line
                for line in lines
            )
        )

    def test_mach_reader_uses_offset_table_bpm_candidate_before_scan(self) -> None:
        import rb_ss_bridge_v2.live_bpm as live_bpm_mod
        import rb_ss_bridge_v2.probe_live_bpm as probe_live_bpm_mod

        base = 0x1000
        ptr = 0x2000
        endpoint = ptr + 0x188
        offsets = RBOffsetVersion(
            version="test",
            deck_count=4,
            master_deck=ChainEntry((0x20,), 0x0),
            bpm_per_deck=(
                ChainEntry((0x10,), 0x188),
                ChainEntry((0x18,), 0x188),
                ChainEntry((0x20,), 0x188),
                ChainEntry((0x28,), 0x188),
            ),
            live_pos_per_deck=tuple(ChainEntry((0x30 + i,), 0) for i in range(4)),
            track_info_per_deck=tuple(ChainEntry((0x40 + i,), 0) for i in range(4)),
            anlz_path_per_deck=tuple(ChainEntry((0x50 + i,), 0) for i in range(4)),
        )

        def fake_read_bytes(task, addr, size):
            if addr == base + 0x10 and size == 8:
                return ptr.to_bytes(8, "little")
            if addr == endpoint and size == 4:
                return struct.pack("<f", 126.5)
            raise OSError(f"no fake mapping at 0x{addr:x}")

        reader = MachLiveBPMReader(rb_version="test")
        session = LiveBPMSession(pid=os.getpid(), base=base, task=1, vmmap_out="")
        with patch.object(live_bpm_mod, "load_offsets_for_version", return_value=offsets), \
             patch.object(live_bpm_mod, "_read_bytes", side_effect=fake_read_bytes), \
             patch.object(probe_live_bpm_mod, "_read_bytes", side_effect=fake_read_bytes):
            candidates = reader.scan_candidates(session, 1, 126.5, 126.5, 24)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source, LIVE_BPM_DIRECT_SOURCE)
        self.assertEqual(candidates[0].addr, endpoint)

    def test_hint_updates_during_sampling_do_not_drop_or_block_promotion(self) -> None:
        reader = FakeLiveBPMReader()
        # Two samples: start at 120.0, then move to 122.0.
        reader.values = [120.0, 122.0]
        service = LiveBPMService(reader=reader, disabled=False)

        # Start discovery at 120.0.
        service.update_hint(1, 120.0, 120.0)
        service.tick()  # attach + scan install

        # Take first sample at 120.0.
        with service._lock:
            service._deck[1].next_sample_at = 0.0
        service.tick()

        # Multiple valid hint updates within the same sampling epoch.
        # This must NOT be treated as semantic drift by itself.
        service.update_hint(1, 121.0, 120.0)
        service.update_hint(1, 122.0, 120.0)

        # Next tick: take second sample (122.0) and validate against latest hint.
        with service._lock:
            service._deck[1].next_sample_at = 0.0

        with self.assertLogs("live_bpm", level="INFO") as logs:
            service.tick()

        self.assertTrue(any("[LBPM][VALIDATED]" in line for line in logs.output))
        self.assertFalse(any("[LBPM][DROP]" in line for line in logs.output))
        self.assertEqual(service.get_bpm(1), 122.0)

    def test_drops_scan_results_if_session_gen_changes_mid_scan(self) -> None:
        reader = FakeLiveBPMReader()
        service = LiveBPMService(reader=reader, disabled=False)

        # First tick attaches and resets epochs.
        service.tick()

        service.update_hint(1, 120.0, 120.0)

        # Ensure scan is eligible.
        with service._lock:
            service._deck[1].last_scan_at = 0.0

        def invalidate_mid_scan() -> None:
            service.invalidate()

        reader.on_scan = invalidate_mid_scan

        with self.assertLogs("live_bpm", level="INFO") as logs:
            service.tick()

        self.assertTrue(any("drop_scan reason=session_gen_mismatch" in line for line in logs.output))
        with service._lock:
            self.assertEqual(service._deck[1].candidates, [])

    def test_drops_validation_commit_if_epoch_changes_mid_validate(self) -> None:
        reader = FakeLiveBPMReader()
        # Provide values that would otherwise pass when hint moves.
        reader.values = [120.0, 122.0]
        service = LiveBPMService(reader=reader, disabled=False)

        service.update_hint(1, 120.0, 120.0)
        service.tick()  # attach + scan install
        service.tick()  # take first sample(s)

        # Force next tick to validate by making the hint "moved" and expediting timing.
        time.sleep(0.22)
        service.update_hint(1, 122.0, 120.0)

        # Simulate epoch change between unlocked computation and commit by
        # forcing a discovery reset inside the validation function's commit window.
        # We do this by patching _results_from_samples to reset discovery before returning.
        import rb_ss_bridge_v2.live_bpm as live_bpm_mod

        original = live_bpm_mod._results_from_samples

        def wrapped(*args, **kwargs):
            results = original(*args, **kwargs)
            with service._lock:
                service._reset_discovery(service._deck[1], keep_validated=True)
            return results

        with patch.object(live_bpm_mod, "_results_from_samples", wraps=wrapped):
            with self.assertLogs("live_bpm", level="INFO") as logs:
                service.tick()

        self.assertTrue(any("drop_validate reason=epoch_mismatch" in line for line in logs.output))
        self.assertIsNone(service.get_bpm(1))

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

    def test_current_bpm_logging_ignores_sub_tenth_jitter(self) -> None:
        reader = FakeLiveBPMReader()
        reader.values = [120.05]
        service = LiveBPMService(reader=reader, disabled=False)
        service._session = reader.session
        service._deck[1].validated = _Validated(
            candidate=reader.candidate,
            latest_bpm=120.0,
            updated_at=time.monotonic(),
            last_logged_bpm=120.0,
            last_logged_at=0.0,
        )

        with self.assertNoLogs("live_bpm", level="INFO"):
            service._refresh_validated(reader.session, 1, service._deck[1].validated)

    def test_current_bpm_logging_reports_moves_over_tenth(self) -> None:
        reader = FakeLiveBPMReader()
        reader.values = [120.11]
        service = LiveBPMService(reader=reader, disabled=False)
        service._session = reader.session
        service._deck[1].validated = _Validated(
            candidate=reader.candidate,
            latest_bpm=120.0,
            updated_at=time.monotonic(),
            last_logged_bpm=120.0,
            last_logged_at=0.0,
        )

        with self.assertLogs("live_bpm", level="INFO") as logs:
            service._refresh_validated(reader.session, 1, service._deck[1].validated)

        self.assertTrue(any("[LBPM][CURRENT]" in line for line in logs.output))


class FakeOutput:
    def __init__(self) -> None:
        self.loads: list[tuple[int, TrackMetadata, int, str]] = []
        self.bpms: list[tuple[int, float]] = []
        self.beats: list[tuple[int, float, int, bool]] = []
        self.elapsed: list[tuple[int, int, float]] = []
        self.clears: list[int] = []
        self.loop_ons: list[int] = []
        self.loop_offs: list[int] = []
        self.plays: list[tuple[int, str]] = []

    def _sub(self, *args, **kwargs):
        pass

    def send_deck_load(self, deck, meta, active, play="on"):
        self.loads.append((deck, meta, active, play))

    def send_loop_on(self, deck):
        self.loop_ons.append(deck)

    def send_loop_off(self, deck):
        self.loop_offs.append(deck)

    def send_deck_play(self, deck, state):
        self.plays.append((deck, state))

    def send_deck_clear(self, deck):
        self.clears.append(deck)

    def send_bpm(self, deck, bpm):
        self.bpms.append((deck, bpm))

    def send_beat(self, deck, bpm, beat_index, change=False):
        self.beats.append((deck, bpm, beat_index, change))

    def send_elapsed(self, deck, elapsed_ms, beatpos):
        self.elapsed.append((deck, elapsed_ms, beatpos))


class FakeLiveProvider:
    def __init__(self, bpm: float | None) -> None:
        self.bpm = bpm

    def get_bpm(self, deck):
        return self.bpm

    def update_hint(self, deck, bpm, library_bpm=0.0):
        pass

    def invalidate(self):
        self.bpm = None


def _autoloop_tick(sm, active, mirror, bpm, abs_beat_pos, elapsed_ms=None):
    return sm._autoloop.tick(
        0.0,
        AutoloopTickContext(active, mirror, bpm, abs_beat_pos, elapsed_ms),
    )


class StateManagerLiveBPMTests(unittest.TestCase):
    def test_beatgrid_position_exact_marker(self) -> None:
        self.assertEqual(_compute_beatgrid_position(1500.0, [1000.0, 1500.0, 2100.0]), (1.0, 1.0))

    def test_beatgrid_position_midpoint(self) -> None:
        wrapped, absolute = _compute_beatgrid_position(1250.0, [1000.0, 1500.0, 2000.0])

        self.assertEqual(wrapped, 0.5)
        self.assertEqual(absolute, 0.5)

    def test_beatgrid_position_variable_spacing(self) -> None:
        wrapped, absolute = _compute_beatgrid_position(1800.0, [1000.0, 1500.0, 2100.0])

        self.assertAlmostEqual(wrapped, 1.5)
        self.assertAlmostEqual(absolute, 1.5)

    def test_beatgrid_position_extrapolates_before_and_after_grid(self) -> None:
        self.assertEqual(_compute_beatgrid_position(500.0, [1000.0, 1500.0, 2100.0]), (3.0, -1.0))
        wrapped, absolute = _compute_beatgrid_position(2400.0, [1000.0, 1500.0, 2100.0])

        self.assertAlmostEqual(wrapped, 2.5)
        self.assertAlmostEqual(absolute, 2.5)

    def test_beatgrid_elapsed_for_abs_beat_uses_marker_timestamp(self) -> None:
        grid = [float(i * 500) for i in range(130)]

        self.assertEqual(_beatgrid_elapsed_for_abs_beat(128, grid), (64000, "grid"))

    def test_beatgrid_elapsed_for_abs_beat_extrapolates_after_grid(self) -> None:
        grid = [0.0, 500.0, 1000.0]

        self.assertEqual(_beatgrid_elapsed_for_abs_beat(4, grid), (2000, "grid-extrapolated"))

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

    def test_autoloop_live_bpm_records_to_session_started_after_init(self) -> None:
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as tmp:
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(123.45), live_bpm_follow=False,
            )
            path = str(Path(tmp) / "capture.jsonl")

            self.assertTrue(sm.start_session_recording(path))
            deck = sm._deck[1]
            deck.meta.filepath = "/tmp/test.wav"
            deck.meta.bpm = 120.0
            sm._apply_lighting(1, "autoloop", 1000, 120.0)

            self.assertEqual(sm.recording_status()["counts"]["live_bpm"], 1)
            self.assertTrue(sm.stop_session_recording())

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
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)
        self.assertGreater(sm._os.autoloop_arm_pending_since, 0.0)

    def test_autoloop_master_phrase_arm_flag_does_not_delay_normal_arm(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[1]
        deck.meta.filepath = "/tmp/normal.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0

        sm._apply_lighting(1, "autoloop", 1000, 120.0)

        self.assertEqual(len(output.loads), 4)
        self.assertIsNone(sm._os.pending_autoloop_arm_meta)

    def test_autoloop_master_phrase_arm_defaults_on_and_delays_deck_load_to_target(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(40)]

        sm._on_master_changed(2, "test-master")
        sm._os.lighting_mode = "autoloop"
        sm._apply_lighting(2, "autoloop", 2600, 120.0)

        self.assertEqual(output.loads, [])
        self.assertEqual(output.clears, [2, 1, 3, 4])
        self.assertEqual(output.loop_offs, [2, 1, 3, 4])
        self.assertIsNotNone(sm._os.pending_autoloop_arm_meta)
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 32)
        self.assertEqual(sm._os.autoloop_arm_target_elapsed_ms, 16000)
        self.assertEqual(sm._os.autoloop_arm_target_source, "grid")

        _autoloop_tick(sm, 2, 1, 120.0, 31.9, 15950)
        self.assertEqual(output.loads, [])

        _autoloop_tick(sm, 2, 1, 120.0, 32.0, 16000)

        self.assertEqual(len(output.loads), 4)
        self.assertEqual(output.loads[0][0], 2)
        self.assertEqual(output.loads[0][3], "on")
        self.assertIsNone(sm._os.pending_autoloop_arm_meta)
        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)
        self.assertEqual(output.bpms[-4:], [(2, 120.0), (1, 120.0), (3, 120.0), (4, 120.0)])
        self.assertEqual(output.beats, [])
        self.assertEqual(output.loads[0][1].elapsed_ms, 16000)

    def test_autoloop_master_phrase_arm_env_zero_disables_default_delay(self) -> None:
        with patch.dict(os.environ, {"RBSS_AUTOLOOP_MASTER_PHRASE_ARM": "0"}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(40)]

        sm._on_master_changed(2, "test-master")
        sm._apply_lighting(2, "autoloop", 2600, 120.0)

        self.assertEqual(len(output.loads), 4)
        self.assertIsNone(sm._os.pending_autoloop_arm_meta)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)
        self.assertEqual(output.beats, [])

    def test_autoloop_master_phrase_arm_snaps_when_near_phrase_start(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(40)]

        sm._on_master_changed(2, "test-master")
        sm._apply_lighting(2, "autoloop", 16100, 120.0)

        self.assertEqual(len(output.loads), 4)
        self.assertEqual(output.clears, [2, 1, 3, 4])
        self.assertEqual(output.loop_offs, [2, 1, 3, 4])
        self.assertIsNone(sm._os.pending_autoloop_arm_meta)
        self.assertEqual(output.beats, [])
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

    def test_autoloop_master_phrase_arm_delays_when_almost_two_beats_after_phrase_start(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(240)]

        sm._on_master_changed(2, "test-master")
        sm._apply_lighting(2, "autoloop", 88950, 120.0)

        self.assertEqual(output.loads, [])
        self.assertIsNotNone(sm._os.pending_autoloop_arm_meta)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 192)
        self.assertEqual(sm._os.autoloop_arm_target_elapsed_ms, 96000)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

    def test_autoloop_master_phrase_arm_delays_when_mid_phrase(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(40)]

        sm._on_master_changed(2, "test-master")
        sm._apply_lighting(2, "autoloop", 12000, 120.0)

        self.assertEqual(output.loads, [])
        self.assertIsNotNone(sm._os.pending_autoloop_arm_meta)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 32)
        self.assertEqual(sm._os.autoloop_arm_target_elapsed_ms, 16000)
        self.assertEqual(sm._os.autoloop_arm_target_source, "grid")
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

    def test_autoloop_master_phrase_arm_arms_short_runway_and_schedules_correction(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 132.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [round(i * (60000.0 / 132.0)) for i in range(100)]

        sm._on_master_changed(2, "test-master")
        sm._os.lighting_mode = "autoloop"
        sm._apply_lighting(2, "autoloop", 28194, 132.0)

        self.assertEqual(output.loads, [])
        self.assertIsNotNone(sm._os.pending_autoloop_arm_meta)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 64)
        self.assertEqual(sm._os.pending_autoloop_arm_reason, "short-runway")
        self.assertLess(sm._os.autoloop_arm_target_elapsed_ms - 28194, 1000)

        _autoloop_tick(sm, 2, 1, 132.0, 64.0, sm._os.autoloop_arm_target_elapsed_ms)

        self.assertEqual(len(output.loads), 4)
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 96)
        self.assertEqual(sm._os.pending_autoloop_arm_reason, "correction-short-runway")

    def test_autoloop_master_phrase_grace_late_arms_and_schedules_correction(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = FakeOutput()
            sm = StateManager(
                queue.Queue(), PositionCache(), output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(120)]

        sm._on_master_changed(2, "test-master")
        sm._os.lighting_mode = "autoloop"
        with self.assertLogs("state_manager", level="WARNING") as logs:
            sm._apply_lighting(2, "autoloop", 16150, 120.0)

        self.assertEqual(len(output.loads), 4)
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 64)
        self.assertEqual(sm._os.pending_autoloop_arm_reason, "correction-phrase-grace-late")
        self.assertTrue(any("AUTOLOOP-MASTER-ARM-GRACE-LATE" in line for line in logs.output))

    def test_master_transition_autoloop_arm_does_not_mark_next_beat_change(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        with patch.dict(os.environ, {"RBSS_AUTOLOOP_MASTER_PHRASE_ARM": "0"}, clear=True):
            sm = StateManager(
                queue.Queue(), cache, output,
                live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
            )
        deck = sm._deck[2]
        deck.playing = True
        deck.meta.filepath = "/tmp/transition.flac"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(12)]

        sm._on_master_changed(2, "test-master")
        sm._apply_lighting(2, "autoloop", 2500, 120.0)
        sm._os.lighting_mode = "autoloop"
        sm._os.lighting_desired = "autoloop"
        sm._os.lighting_stable_since = 0.0
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 2500

        self.assertEqual(len(output.loads), 4)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

        cache.update(PositionSnapshot(2, elapsed_ms=3000, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((2, 120.0, 6, False), output.beats)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

        cache.update(PositionSnapshot(2, elapsed_ms=3500, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((2, 120.0, 7, False), output.beats)

    def test_next_autoloop_arm_phrase_uses_32_beat_phrase_starts(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )

        self.assertEqual(sm._autoloop.next_arm_phrase(0.2), 32)
        self.assertEqual(sm._autoloop.next_arm_phrase(5.2), 32)
        self.assertEqual(sm._autoloop.next_arm_phrase(31.9), 32)
        self.assertEqual(sm._autoloop.next_arm_phrase(32.0), 64)
        self.assertEqual(sm._autoloop.next_arm_phrase(33.0), 64)
        self.assertEqual(sm._autoloop.next_arm_phrase(-0.5), 32)

    def test_previous_autoloop_arm_phrase_anchors_recent_phrase_start(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )

        self.assertEqual(sm._autoloop.previous_arm_phrase(0.2), 0)
        self.assertEqual(sm._autoloop.previous_arm_phrase(16.2), 0)
        self.assertEqual(sm._autoloop.previous_arm_phrase(33.9), 32)
        self.assertEqual(sm._autoloop.previous_arm_phrase(32.0), 32)

    def test_autoloop_arm_phrase_lock_sends_arm_bpm_at_target(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.5
        sm._os.autoloop_arm_pending = True

        _autoloop_tick(sm, 1, 2, 120.5, 5.2)

        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 32)
        self.assertEqual(output.bpms, [])

        _autoloop_tick(sm, 1, 2, 120.5, 32.0)

        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)
        self.assertEqual(sm._os.autoloop_arm_pending_since, 0.0)
        self.assertEqual(output.bpms, [(1, 120.5), (2, 120.5), (3, 120.5), (4, 120.5)])

    def test_autoloop_arm_phrase_lock_waits_for_target_elapsed(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.meta.bpm = 120.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(40)]
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32
        sm._os.autoloop_arm_target_elapsed_ms = 16000
        sm._os.autoloop_arm_target_source = "grid"

        _autoloop_tick(sm, 1, 2, 120.0, 32.0, 15999)
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(output.bpms, [])

        _autoloop_tick(sm, 1, 2, 120.0, 32.0, 16000)
        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(output.bpms[-4:], [(1, 120.0), (2, 120.0), (3, 120.0), (4, 120.0)])

    def test_master_phrase_late_observed_beat_arms_and_schedules_correction(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        pending = TrackMetadata(filepath="/tmp/transition.flac", bpm=120.0)
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 128
        sm._os.autoloop_arm_target_elapsed_ms = 64000
        sm._os.autoloop_arm_target_source = "grid"
        sm._os.pending_autoloop_arm_meta = pending
        sm._os.pending_autoloop_arm_deck = 1
        sm._os.pending_autoloop_arm_mirror = 2
        sm._os.pending_autoloop_arm_active = 1
        sm._os.pending_autoloop_arm_source = "test"

        with self.assertLogs("state_manager", level="WARNING") as logs:
            _autoloop_tick(sm, 1, 2, 120.0, 129.2, 64200)

        self.assertEqual(output.beats, [])
        self.assertEqual(len(output.loads), 4)
        self.assertEqual(output.loads[0][1].elapsed_ms, 64200)
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertIsNotNone(sm._os.pending_autoloop_arm_meta)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 160)
        self.assertEqual(sm._os.autoloop_arm_target_elapsed_ms, 80000)
        self.assertEqual(sm._os.pending_autoloop_arm_reason, "correction-late")
        self.assertTrue(any("AUTOLOOP-MASTER-ARM-LATE-CORRECTION" in line for line in logs.output))

    def test_master_phrase_lock_uses_target_elapsed_when_on_time(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        pending = TrackMetadata(filepath="/tmp/transition.flac", bpm=120.0)
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 128
        sm._os.autoloop_arm_target_elapsed_ms = 64000
        sm._os.autoloop_arm_target_source = "grid"
        sm._os.pending_autoloop_arm_meta = pending
        sm._os.pending_autoloop_arm_deck = 1
        sm._os.pending_autoloop_arm_mirror = 2
        sm._os.pending_autoloop_arm_active = 1
        sm._os.pending_autoloop_arm_source = "test"

        _autoloop_tick(sm, 1, 2, 120.0, 128.0, 64000)

        self.assertEqual(output.beats, [])
        self.assertEqual(len(output.loads), 4)
        self.assertEqual(output.loads[0][1].elapsed_ms, 64000)

    def test_autoloop_phrase_lock_tolerates_small_lateness_without_miss_warning(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32
        sm._os.autoloop_arm_target_elapsed_ms = 16000
        sm._os.autoloop_arm_target_source = "grid"

        with self.assertLogs("state_manager", level="INFO") as logs:
            _autoloop_tick(sm, 1, 2, 120.0, 32.1, 16125)

        self.assertFalse(any("AUTOLOOP-PHRASE-MISS" in line for line in logs.output))

    def test_autoloop_phrase_lock_warns_on_large_lateness_but_commits(self) -> None:
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), PositionCache(), output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32
        sm._os.autoloop_arm_target_elapsed_ms = 16000
        sm._os.autoloop_arm_target_source = "grid"

        with self.assertLogs("state_manager", level="WARNING") as logs:
            _autoloop_tick(sm, 1, 2, 120.0, 32.4, 16200)

        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(output.bpms[-4:], [(1, 120.0), (2, 120.0), (3, 120.0), (4, 120.0)])
        self.assertTrue(any("AUTOLOOP-PHRASE-MISS" in line for line in logs.output))

    def test_autoloop_arm_phrase_lock_clears_on_master_change(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32
        sm._os.autoloop_arm_target_elapsed_ms = 16000
        sm._os.autoloop_arm_target_source = "grid"
        sm._os.autoloop_arm_pending_since = 100.0

        sm._on_master_changed(2, "test")

        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)
        self.assertEqual(sm._os.autoloop_arm_target_elapsed_ms, 0)
        self.assertEqual(sm._os.autoloop_arm_target_source, "")
        self.assertEqual(sm._os.autoloop_arm_pending_since, 0.0)

    def test_autoloop_elapsed_uses_grid_absolute_beatpos(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), cache, output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.bpm = 120.0
        deck.meta.beatgrid_times_ms = [1000.0, 1500.0, 2100.0]
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 1000
        cache.update(PositionSnapshot(1, elapsed_ms=1500, playing=False, updated_at=time.monotonic()))

        sm._push_tick()

        self.assertTrue(output.elapsed)
        self.assertEqual(output.elapsed[-1][2], 1.0)

    def test_autoloop_live_bpm_drop_preserves_absolute_beat_anchor(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        live = FakeLiveProvider(144.0)
        sm = StateManager(
            queue.Queue(), cache, output,
            live_bpm=live, live_bpm_follow=True,
        )
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.bpm = 180.0
        deck.meta.first_beat_ms = 0.0
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 180.0
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 180.0
        sm._os.last_beat_elapsed_ms = 29600
        sm._autoloop.set_tempo_anchor(0, 0.0, 180.0)

        cache.update(PositionSnapshot(1, elapsed_ms=30000, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((1, 144.0, 90, True), output.beats)
        self.assertEqual(output.elapsed[-1][2], 90.0)

        cache.update(PositionSnapshot(1, elapsed_ms=35000, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertGreater(output.elapsed[-1][2], 100.0)
        self.assertGreater(output.elapsed[-1][2], 90.0)

    def test_scripted_elapsed_ignores_beatgrid(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), cache, output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.playing = True
        deck.scripted_id = 123
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [1000.0, 1500.0, 2100.0]
        sm._os.lighting_mode = "scripted"
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 1000
        cache.update(PositionSnapshot(1, elapsed_ms=1500, playing=False, updated_at=time.monotonic()))

        sm._push_tick()

        self.assertTrue(output.elapsed)
        self.assertEqual(output.elapsed[-1][2], 3.0)

    def test_scripted_direct_arms_from_filepath_resolved_same_drain_cycle(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 7
        payload = {
            "load_gen": 7,
            "filepath": "/tmp/scripted.wav",
            "bpm": 128.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "ssid-scripted",
            "total_ms": 180000,
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {900: {"ssid": "ssid-scripted"}}, clear=True):
                sm._on_filepath_resolved(1, payload)
                self.assertEqual(q.qsize(), 1)
                sm._drain_events()

        self.assertEqual(sm._deck[1].scripted_id, 900)

    def test_scripted_direct_clears_unscripted_from_filepath_resolved(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 3
        sm._deck[1].scripted_id = 42
        sm._deck[1].meta.soundswitch_id = "old"
        payload = {
            "load_gen": 3,
            "filepath": "/tmp/unscripted.wav",
            "bpm": 124.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "",
            "total_ms": 180000,
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            sm._on_filepath_resolved(1, payload)
            self.assertEqual(q.qsize(), 1)
            sm._drain_events()

        self.assertEqual(sm._deck[1].scripted_id, 0)
        self.assertEqual(sm._deck[1].meta.soundswitch_id, "")

    def test_scripted_direct_arms_empty_ssid_track_by_unique_filepath(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 8
        payload = {
            "load_gen": 8,
            "filepath": "/tmp/empty-ssid-scripted.wav",
            "bpm": 128.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "",
            "total_ms": 180000,
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(
                sm_mod.SCRIPTED_TRACKS,
                {901: {"ssid": "", "filepath": "/tmp/empty-ssid-scripted.wav"}},
                clear=True,
            ):
                with self.assertLogs("state_manager", level="WARNING") as logs:
                    sm._on_filepath_resolved(1, payload)
                self.assertEqual(q.qsize(), 1)
                sm._drain_events()

        self.assertTrue(any("scripted_id=901" in line for line in logs.output))
        self.assertEqual(sm._deck[1].scripted_id, 901)

    def test_scripted_direct_arms_unregistered_ssid_directly(self) -> None:
        # Unknown SSID alone is not enough to arm; registry filepath fallback can still arm.
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 9
        payload = {
            "load_gen": 9,
            "filepath": "/tmp/path-fallback-scripted.wav",
            "bpm": 128.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "new-ssid",
            "total_ms": 180000,
            "beatgrid_times_ms": [],
            "beatgrid_bpms": [],
            "beatgrid_source": "",
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(
                sm_mod.SCRIPTED_TRACKS,
                {902: {"ssid": "old-ssid", "filepath": "/tmp/path-fallback-scripted.wav"}},
                clear=True,
            ):
                with self.assertLogs("state_manager", level="INFO") as logs:
                    sm._on_filepath_resolved(1, payload)
                self.assertEqual(q.qsize(), 1)
                ev = q.get_nowait()

        self.assertEqual(ev.payload["scripted_id"], 902)
        self.assertTrue(any("source=registry" in line for line in logs.output))
        self.assertFalse(any("WARNING" in line for line in logs.output))

    def test_scripted_direct_does_not_arm_ambiguous_filepath_match(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 10
        sm._deck[1].scripted_id = 42
        payload = {
            "load_gen": 10,
            "filepath": "/tmp/ambiguous.wav",
            "bpm": 128.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "",
            "total_ms": 180000,
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(
                sm_mod.SCRIPTED_TRACKS,
                {
                    903: {"ssid": "", "filepath": "/tmp/ambiguous.wav"},
                    904: {"ssid": "", "filepath": "/tmp/ambiguous.wav"},
                },
                clear=True,
            ):
                with self.assertLogs("state_manager", level="INFO") as logs:
                    sm._on_filepath_resolved(1, payload)
                self.assertEqual(q.qsize(), 1)
                sm._drain_events()

        self.assertTrue(any("ambiguous_matches=2" in line for line in logs.output))
        self.assertFalse(any("WARNING" in line for line in logs.output))
        self.assertEqual(sm._deck[1].scripted_id, 0)

    def test_scripted_direct_disabled_does_not_enqueue_from_filepath_resolved(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 5
        payload = {
            "load_gen": 5,
            "filepath": "/tmp/scripted.wav",
            "bpm": 128.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "ssid-scripted",
            "total_ms": 180000,
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {900: {"ssid": "ssid-scripted"}}, clear=True):
                sm._on_filepath_resolved(1, payload)

        self.assertTrue(q.empty())
        self.assertEqual(sm._deck[1].scripted_id, 0)

    def test_scripted_direct_arms_ssid_not_in_registry_when_show_file_exists(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 11
        payload = {
            "load_gen": 11,
            "filepath": "/tmp/unknown-ssid.wav",
            "bpm": 130.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "unknown-ssid-xyz",
            "total_ms": 200000,
            "beatgrid_times_ms": [],
            "beatgrid_bpms": [],
            "beatgrid_source": "",
        }

        with patch.dict(
            os.environ,
            {"RBSS_SCRIPTED_DIRECT": "1", "RBSS_SCRIPTED_SHOWFILE_DIRECT": "1"},
            clear=True,
        ):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {}, clear=True):
                with patch.object(sm_mod, "has_soundswitch_scripted_id", return_value=True):
                    with self.assertLogs("state_manager", level="INFO") as logs:
                        sm._on_filepath_resolved(1, payload)

        self.assertEqual(q.qsize(), 1)
        ev = q.get_nowait()
        self.assertEqual(ev.kind, sm_mod.Ev.SCRIPTED_ARM)
        scripted_id = ev.payload["scripted_id"]
        self.assertNotEqual(scripted_id, 0)
        self.assertTrue(any("source=direct" in line for line in logs.output))

    def test_scripted_direct_clears_show_file_match_by_default(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 11
        payload = {
            "load_gen": 11,
            "filepath": "/tmp/unknown-ssid.wav",
            "bpm": 130.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "unknown-ssid-xyz",
            "total_ms": 200000,
            "beatgrid_times_ms": [],
            "beatgrid_bpms": [],
            "beatgrid_source": "",
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {}, clear=True):
                with patch.object(sm_mod, "has_soundswitch_scripted_id", return_value=True):
                    sm._on_filepath_resolved(1, payload)

        self.assertEqual(q.qsize(), 1)
        ev = q.get_nowait()
        self.assertEqual(ev.kind, sm_mod.Ev.SCRIPTED_CLEAR)

    def test_scripted_direct_clears_ssid_not_in_registry_without_show_file(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 11
        payload = {
            "load_gen": 11,
            "filepath": "/tmp/unknown-ssid.wav",
            "bpm": 130.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "unknown-ssid-xyz",
            "total_ms": 200000,
            "beatgrid_times_ms": [],
            "beatgrid_bpms": [],
            "beatgrid_source": "",
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {}, clear=True):
                with patch.object(sm_mod, "has_soundswitch_scripted_id", return_value=False):
                    sm._on_filepath_resolved(1, payload)

        self.assertEqual(q.qsize(), 1)
        ev = q.get_nowait()
        self.assertEqual(ev.kind, sm_mod.Ev.SCRIPTED_CLEAR)

    def test_scripted_direct_ssid_not_in_registry_arm_scripted_executes(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 12
        sm._deck[1].meta.soundswitch_id = "unknown-ssid-abc"
        sm._deck[1].meta.filepath = "/tmp/unknown-ssid-abc.wav"
        sm._deck[1].meta.bpm = 128.0
        sm._deck[1].meta.first_beat_ms = 0.0
        sm._deck[1].meta.total_ms = 180000.0
        sm._deck[1].meta.beatgrid_times_ms = [0.0, 468.75]
        sm._deck[1].meta.beatgrid_bpms = [128.0, 128.0]
        sm._deck[1].meta.beatgrid_source = "rekordbox"

        synthetic_id = (hash("unknown-ssid-abc") & 0x7FFFFFFF) or 1

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {}, clear=True):
                sm._arm_scripted(1, synthetic_id)

        self.assertEqual(sm._deck[1].meta.soundswitch_id, "unknown-ssid-abc")
        self.assertEqual(sm._deck[1].meta.beatgrid_times_ms, [0.0, 468.75])

    def test_scripted_arm_phase0_send_tape(self) -> None:
        q: queue.Queue = queue.Queue()
        out = FakeOutput()
        sm = StateManager(
            q, PositionCache(), out,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 12
        sm._deck[1].meta.soundswitch_id = "phase0-tape-ssid"
        sm._deck[1].meta.filepath = "/tmp/phase0-tape-ssid.wav"
        sm._deck[1].meta.bpm = 128.0
        sm._deck[1].meta.first_beat_ms = 0.0
        sm._deck[1].meta.total_ms = 180000.0
        sm._deck[1].meta.beatgrid_times_ms = [0.0, 468.75]
        sm._deck[1].meta.beatgrid_bpms = [128.0, 128.0]
        sm._deck[1].meta.beatgrid_source = "rekordbox"

        synthetic_id = (hash("phase0-tape-ssid") & 0x7FFFFFFF) or 1

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {}, clear=True):
                sm._arm_scripted(1, synthetic_id)

        self.assertEqual(out.loop_offs, [1, 2, 3, 4])
        self.assertEqual(out.plays, [(1, "off"), (2, "off"), (3, "off"), (4, "off")])
        self.assertIsNotNone(sm._pending_arm)

    def test_scripted_direct_registry_hit_still_uses_registry_id(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].load_gen = 13
        payload = {
            "load_gen": 13,
            "filepath": "/tmp/known-ssid.wav",
            "bpm": 128.0,
            "content_id": "content",
            "first_beat_ms": 0.0,
            "soundswitch_id": "known-ssid",
            "total_ms": 180000,
            "beatgrid_times_ms": [],
            "beatgrid_bpms": [],
            "beatgrid_source": "",
        }

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {900: {"ssid": "known-ssid"}}, clear=True):
                sm._on_filepath_resolved(1, payload)

        self.assertEqual(q.qsize(), 1)
        ev = q.get_nowait()
        self.assertEqual(ev.payload["scripted_id"], 900)

    def test_scripted_direct_synthetic_id_debounce(self) -> None:
        q: queue.Queue = queue.Queue()
        sm = StateManager(
            q, PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._deck[1].meta.soundswitch_id = "debounce-ssid"
        sm._deck[1].meta.filepath = "/tmp/debounce.wav"
        sm._deck[1].meta.bpm = 128.0
        sm._deck[1].meta.first_beat_ms = 0.0
        sm._deck[1].meta.total_ms = 180000.0
        sm._deck[1].meta.beatgrid_times_ms = []
        sm._deck[1].meta.beatgrid_bpms = []
        sm._deck[1].meta.beatgrid_source = ""

        synthetic_id = (hash("debounce-ssid") & 0x7FFFFFFF) or 1

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            with patch.dict(sm_mod.SCRIPTED_TRACKS, {}, clear=True):
                sm._arm_scripted(1, synthetic_id)
                first_arm_time = sm._arm_times.get((synthetic_id, 1), 0.0)
                sm._arm_scripted(1, synthetic_id)
                second_arm_time = sm._arm_times.get((synthetic_id, 1), 0.0)

        self.assertNotEqual(first_arm_time, 0.0)
        self.assertEqual(first_arm_time, second_arm_time)

    def test_master_change_transfer_runs_only_for_tl_osc_scripted_path(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.active_deck = 1
        sm._deck[1].scripted_id = 77
        sm._deck[1].playing = False

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"}, clear=True):
            sm._on_master_changed(2, "osc")

        self.assertEqual(sm._deck[1].scripted_id, 0)
        self.assertEqual(sm._deck[2].scripted_id, 77)

        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.active_deck = 1
        sm._deck[1].scripted_id = 77
        sm._deck[1].playing = False

        with patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "1"}, clear=True):
            sm._on_master_changed(2, "osc")

        self.assertEqual(sm._deck[1].scripted_id, 77)
        self.assertEqual(sm._deck[2].scripted_id, 0)

    def test_autoloop_beat_boundary_uses_grid_absolute_index(self) -> None:
        for beat in (2, 4, 8, 16):
            with self.subTest(beat=beat):
                cache = PositionCache()
                output = FakeOutput()
                sm = StateManager(
                    queue.Queue(), cache, output,
                    live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
                )
                deck = sm._deck[1]
                deck.playing = True
                deck.meta.bpm = 120.0
                deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(beat + 2)]
                sm._os.lighting_mode = "autoloop"
                sm._os.autoloop_arm_deck = 1
                sm._os.autoloop_arm_bpm = 120.0
                sm._os.was_playing = True
                sm._os.last_sent_bpm = 120.0
                sm._os.last_beat_elapsed_ms = (beat - 1) * 500
                cache.update(PositionSnapshot(
                    1, elapsed_ms=beat * 500, playing=False, updated_at=time.monotonic(),
                ))

                sm._push_tick()

                self.assertIn((1, 120.0, beat, False), output.beats)

    def test_autoloop_tick_logs_only_on_32_beat_phrase_boundary(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), cache, output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 15000
        sm._last_pos_log[1] = time.monotonic()

        cache.update(PositionSnapshot(1, elapsed_ms=15500, playing=False, updated_at=time.monotonic()))
        with self.assertNoLogs("state_manager", level="INFO"):
            sm._push_tick()

        cache.update(PositionSnapshot(1, elapsed_ms=16000, playing=False, updated_at=time.monotonic()))
        with self.assertLogs("state_manager", level="INFO") as logs:
            sm._push_tick()

        self.assertTrue(any("[SS][AUTOLOOP-TICK]" in line for line in logs.output))
        self.assertIn((1, 120.0, 32, False), output.beats)

    def test_scripted_beat_boundary_keeps_wrapped_change_marker(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), cache, output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.playing = True
        deck.scripted_id = 123
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        sm._os.lighting_mode = "scripted"
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 1500
        cache.update(PositionSnapshot(1, elapsed_ms=2000, playing=False, updated_at=time.monotonic()))

        sm._push_tick()

        self.assertIn((1, 120.0, 0, True), output.beats)

    def test_autoloop_phrase_lock_uses_grid_absolute_beatpos(self) -> None:
        cache = PositionCache()
        output = FakeOutput()
        sm = StateManager(
            queue.Queue(), cache, output,
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.bpm = 120.0
        deck.meta.beatgrid_times_ms = [float(i * 300) for i in range(40)]
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 9300
        cache.update(PositionSnapshot(1, elapsed_ms=9600, playing=False, updated_at=time.monotonic()))

        sm._push_tick()

        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(output.bpms[-4:], [(1, 120.0), (2, 120.0), (3, 120.0), (4, 120.0)])

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
                "source": LIVE_BPM_DIRECT_SOURCE,
            },
        )()

        text = sm._autoloop.live_bpm_status_text(1)

        self.assertIn("live_bpm=124.50", text)
        self.assertIn(f"live_source={LIVE_BPM_DIRECT_SOURCE}", text)
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

    def test_live_bpm_follow_defaults_on_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=None)

            bpm = sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 132.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 128.0)

    def test_live_bpm_follow_env_zero_disables_default_follow(self) -> None:
        with patch.dict(os.environ, {"RBSS_LIVE_BPM_FOLLOW": "0"}, clear=True):
            sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=None)

            bpm = sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_explicit_false_keeps_v1_timing(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=False)

        bpm = sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_applies_changed_bpm_without_rearming_autoloop(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)

        bpm = sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 128.0)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)
        self.assertEqual(sm._os.pending_live_bpm, 132.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(output.loads, [])
        self.assertEqual(output.loop_ons, [])
        self.assertEqual(output.loop_offs, [])
        self.assertEqual(output.plays, [])

    def test_live_bpm_follow_marks_next_autoloop_beat_change_once(self) -> None:
        live = FakeLiveProvider(132.0)
        cache = PositionCache()
        output = FakeOutput()
        sm = StateManager(queue.Queue(), cache, output, live_bpm=live, live_bpm_follow=True)
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.bpm = 128.0
        deck.meta.beatgrid_times_ms = [float(i * 500) for i in range(5)]
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 128.0
        sm._os.last_sent_bpm = 128.0
        sm._os.was_playing = True
        sm._os.last_beat_elapsed_ms = 500

        self.assertEqual(sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 1.2, 100.0), 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 132.0)
        live.bpm = None
        cache.update(PositionSnapshot(1, elapsed_ms=1000, playing=False, updated_at=time.monotonic()))

        sm._push_tick()

        self.assertEqual(output.bpms, [(1, 132.0), (2, 132.0), (3, 132.0), (4, 132.0)])
        self.assertIn((1, 132.0, 2, True), output.beats)
        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

        cache.update(PositionSnapshot(1, elapsed_ms=1500, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((1, 132.0, 3, False), output.beats)

    def test_live_bpm_follow_rate_limits_and_sends_latest_value(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, output = self._autoloop_sm(live, follow=True)

        self.assertEqual(sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0), 128.0)
        live.bpm = 134.0
        self.assertEqual(sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.4, 100.05), 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 134.0)

        cache = sm._cache
        cache.update(PositionSnapshot(1, elapsed_ms=1000, playing=False, updated_at=time.monotonic()))
        sm._os.last_beat_elapsed_ms = 500
        sm._push_tick()

        self.assertEqual(output.bpms[-4:], [(1, 134.0), (2, 134.0), (3, 134.0), (4, 134.0)])
        self.assertEqual(sm._os.autoloop_arm_bpm, 134.0)

    def test_live_bpm_follow_keeps_staged_bpm_until_next_beat(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)

        sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        live.bpm = None
        sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.4, 100.5)

        self.assertEqual(sm._os.pending_live_bpm, 132.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 128.0)

    def test_live_bpm_pending_update_does_not_rewrite_phrase_target(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32
        sm._os.autoloop_arm_target_elapsed_ms = 16000
        sm._os.autoloop_arm_target_source = "grid"

        sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 20.0, 100.0)

        self.assertEqual(sm._os.pending_live_bpm, 132.0)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 32)
        self.assertEqual(sm._os.autoloop_arm_target_elapsed_ms, 16000)
        self.assertEqual(sm._os.autoloop_arm_target_source, "grid")

    def test_autoloop_phrase_target_falls_back_to_bpm_anchor_without_grid(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        meta = TrackMetadata(bpm=120.0, first_beat_ms=1000.0)

        self.assertEqual(sm._autoloop.target_elapsed_for_beat(16, 0, 120.0, meta), (9000, "fallback"))

    def test_live_bpm_follow_waits_until_resume_settle_completed(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._os.was_playing = False

        bpm = sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_clears_pending_on_master_change(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        sm._os.autoloop_change_on_next_beat = True

        sm._on_master_changed(2, "test")

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_deck, 0)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

    def test_live_bpm_follow_clears_pending_on_active_track_load(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 32

        sm._on_track_loaded(1, "new track", BridgeEvent(Ev.TRACK_LOADED, 1, {}, "test"))

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)

    def test_live_bpm_follow_clears_pending_on_rekordbox_restart(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)
        sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        sm._handle_event(BridgeEvent(Ev.RB_RESTARTED, 1, {"pid": 123}, "test"))

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_deck, 0)
        self.assertIsNone(live.bpm)

    def test_live_bpm_follow_ignores_small_jitter(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(128.05), follow=True)

        bpm = sm._autoloop.apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])


if __name__ == "__main__":
    unittest.main()
