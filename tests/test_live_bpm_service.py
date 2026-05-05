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
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot, TrackMetadata
from rb_ss_bridge_v2.rb_memory import PositionCache
from rb_ss_bridge_v2.state_manager import StateManager, _compute_beatgrid_position


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
        self.assertIsNotNone(sm._os.pending_autoloop_arm_meta)
        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 16)

        sm._deck[2].elapsed_ms = 8500
        sm._maybe_lock_autoloop_arm(2, 1, 120.0, 15.9)
        self.assertEqual(output.loads, [])

        sm._maybe_lock_autoloop_arm(2, 1, 120.0, 16.0)

        self.assertEqual(len(output.loads), 4)
        self.assertEqual(output.loads[0][0], 2)
        self.assertEqual(output.loads[0][3], "on")
        self.assertIsNone(sm._os.pending_autoloop_arm_meta)
        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertTrue(sm._os.autoloop_change_on_next_beat)
        self.assertEqual(output.bpms[-4:], [(2, 120.0), (1, 120.0), (3, 120.0), (4, 120.0)])

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
        self.assertTrue(sm._os.autoloop_change_on_next_beat)

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
        sm._apply_lighting(2, "autoloop", 8100, 120.0)

        self.assertEqual(len(output.loads), 4)
        self.assertIsNone(sm._os.pending_autoloop_arm_meta)
        self.assertEqual(output.beats, [
            (2, 120.0, 16, True),
            (1, 120.0, 16, True),
            (3, 120.0, 16, True),
            (4, 120.0, 16, True),
        ])
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
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

    def test_master_transition_autoloop_arm_marks_next_beat_change_once(self) -> None:
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
        self.assertTrue(sm._os.autoloop_change_on_next_beat)

        cache.update(PositionSnapshot(2, elapsed_ms=3000, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((2, 120.0, 6, True), output.beats)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

        cache.update(PositionSnapshot(2, elapsed_ms=3500, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((2, 120.0, 7, False), output.beats)

    def test_next_autoloop_arm_phrase_uses_16_beat_phrase_starts(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )

        self.assertEqual(sm._next_autoloop_arm_phrase(0.2), 16)
        self.assertEqual(sm._next_autoloop_arm_phrase(5.2), 16)
        self.assertEqual(sm._next_autoloop_arm_phrase(15.9), 16)
        self.assertEqual(sm._next_autoloop_arm_phrase(16.0), 32)
        self.assertEqual(sm._next_autoloop_arm_phrase(17.0), 32)
        self.assertEqual(sm._next_autoloop_arm_phrase(-0.5), 16)

    def test_previous_autoloop_arm_phrase_anchors_recent_phrase_start(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )

        self.assertEqual(sm._previous_autoloop_arm_phrase(0.2), 0)
        self.assertEqual(sm._previous_autoloop_arm_phrase(16.2), 16)
        self.assertEqual(sm._previous_autoloop_arm_phrase(17.9), 16)
        self.assertEqual(sm._previous_autoloop_arm_phrase(32.0), 32)

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

        sm._maybe_lock_autoloop_arm(1, 2, 120.5, 5.2)

        self.assertTrue(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 16)
        self.assertEqual(output.bpms, [])

        sm._maybe_lock_autoloop_arm(1, 2, 120.5, 16.0)

        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)
        self.assertEqual(sm._os.autoloop_arm_pending_since, 0.0)
        self.assertEqual(output.bpms, [(1, 120.5), (2, 120.5), (3, 120.5), (4, 120.5)])

    def test_autoloop_arm_phrase_lock_clears_on_master_change(self) -> None:
        sm = StateManager(
            queue.Queue(), PositionCache(), FakeOutput(),
            live_bpm=FakeLiveProvider(None), live_bpm_follow=False,
        )
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 16
        sm._os.autoloop_arm_pending_since = 100.0

        sm._on_master_changed(2, "test")

        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)
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
        deck.meta.beatgrid_times_ms = [float(i * 300) for i in range(20)]
        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_deck = 1
        sm._os.autoloop_arm_bpm = 120.0
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 16
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 4800
        cache.update(PositionSnapshot(1, elapsed_ms=5100, playing=False, updated_at=time.monotonic()))

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

    def test_live_bpm_follow_defaults_on_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=None)

            bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 132.0)
        self.assertEqual(output.bpms, [(1, 132.0), (2, 132.0), (3, 132.0), (4, 132.0)])
        self.assertEqual(sm._os.autoloop_arm_bpm, 132.0)

    def test_live_bpm_follow_env_zero_disables_default_follow(self) -> None:
        with patch.dict(os.environ, {"RBSS_LIVE_BPM_FOLLOW": "0"}, clear=True):
            sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=None)

            bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_explicit_false_keeps_v1_timing(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=False)

        bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.5, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])
        self.assertEqual(sm._os.pending_live_bpm, 0.0)

    def test_live_bpm_follow_applies_changed_bpm_without_rearming_autoloop(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)

        bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        self.assertEqual(bpm, 132.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 132.0)
        self.assertTrue(sm._os.autoloop_change_on_next_beat)
        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(output.bpms, [(1, 132.0), (2, 132.0), (3, 132.0), (4, 132.0)])
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

        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 1.2, 100.0), 132.0)
        self.assertTrue(sm._os.autoloop_change_on_next_beat)
        live.bpm = None
        cache.update(PositionSnapshot(1, elapsed_ms=1000, playing=False, updated_at=time.monotonic()))

        sm._push_tick()

        self.assertIn((1, 132.0, 2, True), output.beats)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

        cache.update(PositionSnapshot(1, elapsed_ms=1500, playing=False, updated_at=time.monotonic()))
        sm._push_tick()

        self.assertIn((1, 132.0, 3, False), output.beats)

    def test_live_bpm_follow_rate_limits_and_sends_latest_value(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, output = self._autoloop_sm(live, follow=True)

        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0), 132.0)
        live.bpm = 134.0
        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 132.0, 8.4, 100.05), 132.0)
        self.assertEqual(output.bpms, [(1, 132.0), (2, 132.0), (3, 132.0), (4, 132.0)])

        self.assertEqual(sm._maybe_apply_live_bpm_follow(1, 2, 132.0, 8.6, 100.11), 134.0)

        self.assertEqual(output.bpms[-4:], [(1, 134.0), (2, 134.0), (3, 134.0), (4, 134.0)])
        self.assertEqual(sm._os.autoloop_arm_bpm, 134.0)

    def test_live_bpm_follow_clears_pending_when_live_bpm_unvalidated(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)

        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        live.bpm = None
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.4, 100.5)

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 132.0)

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
        sm._os.autoloop_change_on_next_beat = True

        sm._on_master_changed(2, "test")

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_deck, 0)
        self.assertFalse(sm._os.autoloop_change_on_next_beat)

    def test_live_bpm_follow_clears_pending_on_active_track_load(self) -> None:
        sm, _ = self._autoloop_sm(FakeLiveProvider(132.0), follow=True)
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)
        sm._os.autoloop_arm_pending = True
        sm._os.autoloop_arm_sync_beat = 16

        sm._on_track_loaded(1, "new track", BridgeEvent(Ev.TRACK_LOADED, 1, {}, "test"))

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertFalse(sm._os.autoloop_arm_pending)
        self.assertEqual(sm._os.autoloop_arm_sync_beat, 0)

    def test_live_bpm_follow_clears_pending_on_rekordbox_restart(self) -> None:
        live = FakeLiveProvider(132.0)
        sm, _ = self._autoloop_sm(live, follow=True)
        sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        sm._handle_event(BridgeEvent(Ev.RB_RESTARTED, 1, {"pid": 123}, "test"))

        self.assertEqual(sm._os.pending_live_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_bpm, 0.0)
        self.assertEqual(sm._os.autoloop_arm_deck, 0)
        self.assertIsNone(live.bpm)

    def test_live_bpm_follow_ignores_small_jitter(self) -> None:
        sm, output = self._autoloop_sm(FakeLiveProvider(128.05), follow=True)

        bpm = sm._maybe_apply_live_bpm_follow(1, 2, 128.0, 8.2, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(output.bpms, [])


if __name__ == "__main__":
    unittest.main()
