import logging
import math
import sys
import time
import unittest
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.autoloop_controller import (  # noqa: E402
    AutoloopController,
    AutoloopTickContext,
)
from rb_ss_bridge_v2.models import DeckState, OutputState, TrackMetadata  # noqa: E402


class FakeLiveBPM:
    def __init__(self, bpm=None, status=None):
        self.bpm = bpm
        self.status = status

    def get_bpm(self, deck):
        if isinstance(self.bpm, Exception):
            raise self.bpm
        return self.bpm

    def get_status(self, deck):
        return self.status


class FakeSSE:
    def __init__(self):
        self.loads = []
        self.bpms = []
        self.clears = []

    def send_autoloop_deck_load(self, deck, mirror, active, meta):
        self.loads.append((deck, mirror, active, meta))

    def send_autoloop_bpm(self, active, bpm):
        self.bpms.append((active, bpm))

    def send_autoloop_clear(self, active):
        self.clears.append(active)


class FakeRecorder:
    def __init__(self):
        self.live_bpm = []

    def record_live_bpm(self, deck, bpm, status):
        self.live_bpm.append((deck, bpm, status))


class AutoloopControllerTests(unittest.TestCase):
    def make_controller(self, live=None, follow=True, clock=None, recorder_ref=None):
        os = OutputState()
        decks = {1: DeckState(number=1), 2: DeckState(number=2)}
        sse = FakeSSE()
        controller = AutoloopController(
            output_state_ref=lambda: os,
            deck_ref=lambda d: decks[d],
            live_bpm_service=live,
            sse=sse,
            clock=clock or (lambda: 100.0),
            logger=logging.getLogger("state_manager"),
            live_bpm_follow=follow,
            recorder_ref=recorder_ref,
        )
        return controller, os, decks, sse

    def test_target_elapsed_prefers_grid_marker(self):
        controller, _, _, _ = self.make_controller()
        meta = TrackMetadata(beatgrid_times_ms=[0.0, 500.0, 1000.0])

        self.assertEqual(
            controller.target_elapsed_for_beat(2, 0, 120.0, meta),
            (1000, "grid"),
        )

    def test_target_elapsed_uses_anchor_for_fallback(self):
        controller, os, _, _ = self.make_controller()
        meta = TrackMetadata(first_beat_ms=1000.0)
        os.autoloop_anchor_elapsed_ms = 2500
        os.autoloop_anchor_abs_beat = 3.0
        os.autoloop_anchor_bpm = 120.0

        self.assertEqual(
            controller.target_elapsed_for_beat(7, 0, 120.0, meta),
            (4500, "fallback"),
        )

    def test_target_elapsed_nonpositive_bpm_returns_current_elapsed(self):
        controller, _, _, _ = self.make_controller()

        self.assertEqual(
            controller.target_elapsed_for_beat(16, 1234, 0.0, TrackMetadata()),
            (1234, "fallback"),
        )

    def test_fallback_abs_beat_uses_anchor_when_current_autoloop_deck_matches(self):
        controller, os, _, _ = self.make_controller()
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_anchor_elapsed_ms = 1000
        os.autoloop_anchor_abs_beat = 4.0
        os.autoloop_anchor_bpm = 120.0

        self.assertEqual(
            controller.fallback_abs_beat_for_elapsed(1, 2000, 120.0, 0.0),
            6.0,
        )

    def test_fallback_abs_beat_returns_zero_without_positive_bpm(self):
        controller, _, _, _ = self.make_controller()

        self.assertEqual(
            controller.fallback_abs_beat_for_elapsed(1, 2000, 0.0, 0.0),
            0.0,
        )

    def test_abs_beat_for_elapsed_uses_grid_position(self):
        controller, _, _, _ = self.make_controller()
        meta = TrackMetadata(beatgrid_times_ms=[0.0, 500.0, 1000.0])

        self.assertEqual(controller.abs_beat_for_elapsed(750, 120.0, meta), 1.5)

    def test_tempo_anchor_set_and_clear_mutates_output_state(self):
        controller, os, _, _ = self.make_controller()

        controller.set_tempo_anchor(1000, 2.5, 128.0)
        self.assertEqual(os.autoloop_anchor_elapsed_ms, 1000)
        self.assertEqual(os.autoloop_anchor_abs_beat, 2.5)
        self.assertEqual(os.autoloop_anchor_bpm, 128.0)

        controller.clear_tempo_anchor()
        self.assertEqual(os.autoloop_anchor_elapsed_ms, 0)
        self.assertEqual(os.autoloop_anchor_abs_beat, 0.0)
        self.assertEqual(os.autoloop_anchor_bpm, 0.0)

    def test_phrase_helpers(self):
        controller, _, _, _ = self.make_controller()

        self.assertTrue(controller.is_near_phrase_start(32.2))
        self.assertFalse(controller.is_near_phrase_start(33.0))
        self.assertFalse(controller.should_delay_master_arm(False, True, 33.0))
        self.assertTrue(controller.should_delay_master_arm(True, True, 33.0))
        self.assertEqual(controller.next_arm_phrase(31.9), 32)
        self.assertEqual(controller.next_arm_phrase(32.0), 64)
        self.assertEqual(controller.previous_arm_phrase(33.9), 32)

    def test_live_bpm_value_records_valid_and_invalid_reads(self):
        recorder = FakeRecorder()
        controller, _, _, _ = self.make_controller(
            live=FakeLiveBPM(129.5), recorder_ref=lambda: recorder,
        )

        self.assertEqual(controller.live_bpm_value(1), 129.5)
        self.assertEqual(recorder.live_bpm, [(1, 129.5, None)])

        controller._live_bpm = FakeLiveBPM(float("nan"))
        self.assertIsNone(controller.live_bpm_value(1))
        self.assertEqual(recorder.live_bpm[-1], (1, None, None))

    def test_live_bpm_value_uses_current_recorder_ref(self):
        current = {"recorder": None}
        controller, _, _, _ = self.make_controller(
            live=FakeLiveBPM(129.5),
            recorder_ref=lambda: current["recorder"],
        )

        self.assertEqual(controller.live_bpm_value(1), 129.5)
        recorder = FakeRecorder()
        current["recorder"] = recorder
        self.assertEqual(controller.live_bpm_value(1), 129.5)

        self.assertEqual(recorder.live_bpm, [(1, 129.5, None)])

    def test_arm_bpm_prefers_live_value(self):
        controller, _, _, _ = self.make_controller(live=FakeLiveBPM(127.25))

        self.assertEqual(controller.arm_bpm(1, 120.0), (127.25, "live"))

    def test_apply_live_bpm_follow_stages_changed_bpm(self):
        controller, os, decks, _ = self.make_controller(live=FakeLiveBPM(132.0))
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = 128.0
        os.was_playing = True
        decks[1].playing = True

        bpm = controller.apply_live_bpm_follow(1, 2, 128.0, 12.0, 100.0)

        self.assertEqual(bpm, 128.0)
        self.assertEqual(os.pending_live_bpm, 132.0)

    def test_apply_live_bpm_follow_clears_pending_when_jitter_is_small(self):
        controller, os, decks, _ = self.make_controller(live=FakeLiveBPM(128.05))
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = 128.0
        os.pending_live_bpm = 132.0
        os.was_playing = True
        decks[1].playing = True

        controller.apply_live_bpm_follow(1, 2, 128.0, 12.0, 100.0)

        self.assertEqual(os.pending_live_bpm, 0.0)

    def test_apply_live_bpm_follow_respects_disabled_flag(self):
        controller, os, decks, _ = self.make_controller(
            live=FakeLiveBPM(132.0), follow=False,
        )
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = 128.0
        os.was_playing = True
        decks[1].playing = True

        controller.apply_live_bpm_follow(1, 2, 128.0, 12.0, 100.0)

        self.assertEqual(os.pending_live_bpm, 0.0)

    def test_tick_locks_arm_and_sends_bpm(self):
        controller, os, _, sse = self.make_controller()
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = 120.5
        os.autoloop_arm_pending = True
        os.autoloop_arm_sync_beat = 32
        os.autoloop_arm_target_elapsed_ms = 16000
        os.autoloop_arm_target_source = "fallback"

        result = controller.tick(
            100.0,
            AutoloopTickContext(1, 2, 120.5, 32.0, 16000),
        )

        self.assertTrue(result.arm_locked)
        self.assertFalse(os.autoloop_arm_pending)
        self.assertEqual(sse.bpms, [(1, 120.5)])

    def test_tick_waits_until_target_elapsed(self):
        controller, os, _, sse = self.make_controller()
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = 120.0
        os.autoloop_arm_pending = True
        os.autoloop_arm_sync_beat = 32
        os.autoloop_arm_target_elapsed_ms = 16000

        result = controller.tick(
            100.0,
            AutoloopTickContext(1, 2, 120.0, 32.0, 15999),
        )

        self.assertFalse(result.arm_locked)
        self.assertTrue(os.autoloop_arm_pending)
        self.assertEqual(sse.bpms, [])

    def test_pending_meta_deck_load_uses_target_elapsed_when_on_time(self):
        controller, os, _, sse = self.make_controller()
        pending = TrackMetadata(filepath="/tmp/transition.flac", bpm=120.0)
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = 120.0
        os.autoloop_arm_pending = True
        os.autoloop_arm_sync_beat = 128
        os.autoloop_arm_target_elapsed_ms = 64000
        os.pending_autoloop_arm_meta = pending
        os.pending_autoloop_arm_deck = 1
        os.pending_autoloop_arm_mirror = 2
        os.pending_autoloop_arm_active = 1

        controller.tick(100.0, AutoloopTickContext(1, 2, 120.0, 128.0, 64000))

        self.assertEqual(len(sse.loads), 1)
        self.assertEqual(sse.loads[0][3].elapsed_ms, 64000)

    def test_schedule_master_correction_chooses_future_runway(self):
        controller, os, _, _ = self.make_controller()
        meta = TrackMetadata(filepath="/tmp/a.flac", bpm=120.0)

        controller.schedule_master_correction(
            1, 2, 1, meta, 120.0, 15750, 16, "test", "short-runway",
        )

        self.assertTrue(os.autoloop_arm_pending)
        self.assertEqual(os.autoloop_arm_sync_beat, 48)
        self.assertGreaterEqual(os.autoloop_arm_target_elapsed_ms - 15750, 1000)

    def test_clear_helpers_reset_output_state_fields(self):
        controller, os, _, _ = self.make_controller()
        os.autoloop_arm_pending = True
        os.autoloop_arm_sync_beat = 32
        os.autoloop_arm_target_elapsed_ms = 16000
        os.pending_live_bpm = 132.0
        os.autoloop_change_on_next_beat = True
        os.pending_autoloop_arm_meta = TrackMetadata(filepath="/tmp/a.flac")
        os.pending_autoloop_arm_deck = 1

        controller.clear_arm_phrase_lock()
        controller.clear_live_bpm_follow()
        controller.clear_tempo_relock()
        controller.clear_pending_master_phrase_arm()

        self.assertFalse(os.autoloop_arm_pending)
        self.assertEqual(os.autoloop_arm_sync_beat, 0)
        self.assertEqual(os.autoloop_arm_target_elapsed_ms, 0)
        self.assertEqual(os.pending_live_bpm, 0.0)
        self.assertFalse(os.autoloop_change_on_next_beat)
        self.assertIsNone(os.pending_autoloop_arm_meta)
        self.assertEqual(os.pending_autoloop_arm_deck, 0)


class AutoloopControllerPropertyTests(unittest.TestCase):
    def make_controller(self, live=None, follow=True, clock=None):
        os = OutputState()
        decks = {1: DeckState(number=1), 2: DeckState(number=2)}
        sse = FakeSSE()
        controller = AutoloopController(
            output_state_ref=lambda: os,
            deck_ref=lambda d: decks[d],
            live_bpm_service=live,
            sse=sse,
            clock=clock or (lambda: 100.0),
            logger=logging.getLogger("state_manager"),
            live_bpm_follow=follow,
        )
        return controller, os, decks, sse

    @given(
        bpm=st.floats(min_value=60.0, max_value=220.0, allow_nan=False, allow_infinity=False),
        first_beat_ms=st.floats(min_value=-2000.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
        a=st.integers(min_value=0, max_value=4096),
        b=st.integers(min_value=0, max_value=4096),
    )
    @settings(max_examples=100)
    def test_target_elapsed_for_beat_is_monotone_for_fixed_bpm(
        self, bpm, first_beat_ms, a, b,
    ):
        controller, _, _, _ = self.make_controller()
        meta = TrackMetadata(first_beat_ms=first_beat_ms)
        low, high = sorted((a, b))

        low_elapsed, _ = controller.target_elapsed_for_beat(low, 0, bpm, meta)
        high_elapsed, _ = controller.target_elapsed_for_beat(high, 0, bpm, meta)

        self.assertLessEqual(low_elapsed, high_elapsed)

    @given(
        timing_bpm=st.floats(min_value=60.0, max_value=220.0, allow_nan=False, allow_infinity=False),
        live_delta=st.floats(min_value=0.2, max_value=20.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_apply_live_bpm_follow_is_idempotent_within_tolerance(
        self, timing_bpm, live_delta,
    ):
        live_bpm = timing_bpm + live_delta
        controller, os, decks, _ = self.make_controller(live=FakeLiveBPM(live_bpm))
        os.lighting_mode = "autoloop"
        os.autoloop_arm_deck = 1
        os.autoloop_arm_bpm = timing_bpm
        os.was_playing = True
        decks[1].playing = True

        first = controller.apply_live_bpm_follow(1, 2, timing_bpm, 8.0, 100.0)
        pending = os.pending_live_bpm
        second = controller.apply_live_bpm_follow(1, 2, timing_bpm, 8.2, 100.01)

        self.assertEqual(first, timing_bpm)
        self.assertEqual(second, timing_bpm)
        self.assertTrue(math.isclose(os.pending_live_bpm, pending, rel_tol=0.0, abs_tol=1e-9))

    @given(
        bpm=st.floats(min_value=80.0, max_value=180.0, allow_nan=False, allow_infinity=False),
        current_elapsed_ms=st.integers(min_value=0, max_value=240_000),
        from_target_beat=st.integers(min_value=0, max_value=512),
    )
    @settings(max_examples=100)
    def test_late_arm_correction_always_schedules_with_runway_at_least_1000_ms(
        self, bpm, current_elapsed_ms, from_target_beat,
    ):
        controller, os, _, _ = self.make_controller()
        meta = TrackMetadata(filepath="/tmp/a.flac", bpm=bpm)

        controller.schedule_master_correction(
            1,
            2,
            1,
            meta,
            bpm,
            current_elapsed_ms,
            from_target_beat,
            "property",
            "late",
        )

        runway_ms = os.autoloop_arm_target_elapsed_ms - current_elapsed_ms
        self.assertGreaterEqual(runway_ms, 1000)


if __name__ == "__main__":
    unittest.main()
