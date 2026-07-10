from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.beat_sync_engine import (  # noqa: E402
    MAX_CATCHUP,
    MAX_PULSES,
    WRAP_HOLD_BEATS,
    BeatSyncEngine,
    TriggerClock,
)


class BeatSyncEngineTests(unittest.TestCase):
    def test_clock_holds_sub_threshold_backward_step(self) -> None:
        clock = TriggerClock(1.0, spawn_on_wrap=True)
        self.assertEqual(clock.advance(10.0), (0, False))

        self.assertEqual(clock.advance(9.995), (0, False))

        self.assertEqual(clock._last_abs, 10.0)
        self.assertEqual(clock._last_idx, 10)

    def test_clock_oscillating_jitter_never_wraps_or_spawns(self) -> None:
        clock = TriggerClock(1.0, spawn_on_wrap=True)
        self.assertEqual(clock.advance(10.0), (0, False))

        for beat in (9.995, 10.0, 9.996, 10.0) * 8:
            self.assertEqual(clock.advance(beat), (0, False))

        self.assertEqual(clock._last_abs, 10.0)
        self.assertEqual(clock._last_idx, 10)

    def test_clock_real_loop_wraps_and_reseeds(self) -> None:
        clock = TriggerClock(1.0, spawn_on_wrap=True)
        clock.advance(10.0)

        self.assertEqual(clock.advance(2.0), (1, True))
        self.assertEqual(clock._last_abs, 2.0)
        self.assertEqual(clock._last_idx, 2)

        no_spawn = TriggerClock(1.0, spawn_on_wrap=False)
        no_spawn.advance(10.0)
        self.assertEqual(no_spawn.advance(2.0), (0, True))
        self.assertEqual(no_spawn._last_abs, 2.0)
        self.assertEqual(no_spawn._last_idx, 2)

    def test_clock_wrap_hold_boundary(self) -> None:
        clock = TriggerClock(1.0, spawn_on_wrap=True)
        clock.advance(10.0)
        self.assertEqual(clock.advance(10.0 - WRAP_HOLD_BEATS), (1, True))

        held = TriggerClock(1.0, spawn_on_wrap=True)
        held.advance(10.0)
        self.assertEqual(held.advance(10.0 - WRAP_HOLD_BEATS + 0.01), (0, False))
        self.assertEqual(held._last_abs, 10.0)

    def test_clock_forward_spawns_still_capped(self) -> None:
        clock = TriggerClock(1.0, spawn_on_wrap=True)
        clock.advance(0.0)
        self.assertEqual(clock.advance(1.0), (1, False))
        self.assertEqual(clock.advance(50.0), (MAX_CATCHUP, False))

    def test_continuous_holds_jitter_but_reanchors_real_wrap(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="solid",
            sync_mode="continuous",
            beat_division=1.0,
            params={},
            seed=42,
            now=0.0,
            abs_beat=10.0,
            bpm=120.0,
        )
        born_before = engine._instances[0].born_abs_beat
        bucket_before = engine._instances[0].bucket

        engine.on_tick(10.25, 0.1, 120.0)
        engine.on_tick(10.245, 0.2, 120.0)

        self.assertEqual(engine._instances[0].born_abs_beat, born_before)
        self.assertEqual(engine._instances[0].bucket, bucket_before)

        engine.on_tick(9.75, 0.3, 120.0)
        self.assertEqual(engine._instances[0].born_abs_beat, 9.75)
        self.assertNotEqual(engine._instances[0].bucket, bucket_before)

    def test_born_bpm_stamped_on_activation_overlap_and_retrigger(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=123.0,
        )
        self.assertEqual(engine._instances[0].born_bpm, 123.0)

        engine.fire_manual(0.1, 0.0, 90.0)
        self.assertEqual(engine._instances[-1].born_bpm, 90.0)

        retrigger = BeatSyncEngine()
        retrigger.configure(
            effect_name="beat_chase",
            sync_mode="retrigger",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        retrigger.on_tick(1.0, 0.5, 60.0)
        self.assertEqual(retrigger._instances[0].born_bpm, 60.0)

    def test_born_bpm_floored_positive(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=0.0,
        )
        self.assertEqual(engine._instances[0].born_bpm, 1.0)

    def test_rate_lock_ignores_live_bpm_change_mid_flight(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"travel_beats": 2.0, "trail_beats": 1.0},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )

        renders = engine.on_tick(1.0, 0.5, 240.0)

        self.assertAlmostEqual(renders[0].progress, 0.5)
        self.assertAlmostEqual(renders[0].local_beat, 1.0)
        self.assertEqual(engine._instances[0].born_bpm, 120.0)
        self.assertEqual(engine._instances[1].born_bpm, 240.0)

    def test_animate_advances_expires_and_never_spawns(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"travel_beats": 1.0, "trail_beats": 0.25},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        spawn_count = engine.spawn_count

        renders = engine.animate(0.25)
        self.assertEqual(engine.instance_count, 1)
        self.assertEqual(engine.spawn_count, spawn_count)
        self.assertAlmostEqual(renders[0].progress, 0.5)

        self.assertEqual(engine.animate(0.7), [])
        self.assertEqual(engine.instance_count, 0)
        self.assertEqual(engine.spawn_count, spawn_count)

    def test_animate_without_clock_or_instances_returns_empty(self) -> None:
        engine = BeatSyncEngine()
        self.assertEqual(engine.animate(0.0), [])
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"travel_beats": 1.0, "trail_beats": 0.0},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        engine.animate(1.0)
        self.assertEqual(engine.animate(1.1), [])

    def test_overlap_division_spawns_once(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"travel_beats": 0.25},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        seed_spawns = engine.spawn_count
        engine.on_tick(0.4, 0.2, 120.0)
        engine.on_tick(1.1, 0.5, 120.0)
        self.assertEqual(engine.spawn_count, seed_spawns + 1)

    def test_wrap_no_freeze(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"travel_beats": 2.0, "trail_beats": 1.0},
            seed=1,
            now=0.0,
            abs_beat=7.0,
            bpm=120.0,
        )
        renders = engine.on_tick(7.6, 0.3, 120.0)
        progress_before = renders[0].progress
        renders_after = engine.on_tick(0.0, 0.5, 120.0)
        self.assertTrue(renders_after)
        self.assertGreater(renders_after[0].progress, progress_before)

    def test_wrap_no_flood(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"spawn_on_wrap": False},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        initial = engine.spawn_count
        engine.on_tick(1.0, 0.1, 120.0)
        engine.on_tick(2.0, 0.2, 120.0)
        before_wrap = engine.spawn_count
        engine.on_tick(0.0, 0.3, 120.0)
        after_wrap = engine.spawn_count
        self.assertEqual(after_wrap - before_wrap, 0)
        self.assertLessEqual(after_wrap, initial + 3)

    def test_wrap_spawns_on_wrap_default(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        engine.on_tick(1.0, 0.1, 120.0)
        engine.on_tick(2.0, 0.2, 120.0)
        before_wrap = engine.spawn_count
        engine.on_tick(0.0, 0.3, 120.0)
        after_wrap = engine.spawn_count
        self.assertEqual(after_wrap - before_wrap, 1)

    def test_forward_seek_capped(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        before = engine.spawn_count
        engine.on_tick(50.0, 0.1, 120.0)
        self.assertLessEqual(engine.spawn_count - before, MAX_CATCHUP)

    def test_retrigger_keeps_single_instance(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="beat_chase",
            sync_mode="retrigger",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        for beat in (1.0, 2.0, 3.0, 4.0):
            engine.on_tick(beat, float(beat) * 0.5, 120.0)
        self.assertEqual(engine.instance_count, 1)

    def test_continuous_reanchors_on_wrap_only(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="solid",
            sync_mode="continuous",
            beat_division=1.0,
            params={},
            seed=42,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        r1 = engine.on_tick(1.0, 0.5, 120.0)
        r2 = engine.on_tick(2.0, 1.0, 120.0)
        self.assertEqual(r1[0].bucket, r2[0].bucket)
        r3 = engine.on_tick(0.0, 1.5, 120.0)
        self.assertNotEqual(r2[0].bucket, r3[0].bucket)
        self.assertLess(r3[0].local_beat, 0.1)

    def test_overlap_instance_cap(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={"max_pulses": MAX_PULSES, "travel_beats": 10.0},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        for i in range(MAX_PULSES + 5):
            engine.fire_manual(float(i) * 0.01, float(i), 120.0)
        self.assertLessEqual(engine.instance_count, MAX_PULSES)

    def test_reset_clears(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        engine.on_tick(0.5, 0.1, 120.0)
        engine.reset()
        self.assertEqual(engine.on_tick(0.5, 0.2, 120.0), [])

    def test_manual_fire_overlap_spawns(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="groove_chase_blue",
            sync_mode="overlap",
            beat_division=1.0,
            params={},
            seed=1,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        before = engine.instance_count
        engine.fire_manual(0.1, 0.0, 120.0)
        self.assertEqual(engine.instance_count, before + 1)

    def test_continuous_local_beat_grid_quantized_at_spawn(self) -> None:
        # Continuous look dispatched at abs_beat=32.6 must render phase 0.6 on the
        # grid at spawn, then advance with elapsed beats -- not phase-lock to the
        # dispatch instant (Bug 1).
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="rt_groove_center_chase",
            sync_mode="continuous",
            beat_division=1.0,
            params={},
            seed=3,
            now=0.0,
            abs_beat=32.6,
            bpm=120.0,
        )
        at_spawn = engine.animate(0.0)
        self.assertAlmostEqual(at_spawn[0].local_beat % 1.0, 0.6)
        # half a beat later (120 bpm -> 0.25 s) the grid phase advances to ~0.1
        later = engine.animate(0.25)
        self.assertAlmostEqual(later[0].local_beat % 1.0, 0.1)

    def test_continuous_progress_stays_spawn_relative(self) -> None:
        # progress must be elapsed/travel (0.0 at spawn), NOT the quantized origin.
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="rt_groove_center_chase",
            sync_mode="continuous",
            beat_division=1.0,
            params={"travel_beats": 4.0},
            seed=3,
            now=0.0,
            abs_beat=32.6,
            bpm=120.0,
        )
        at_spawn = engine.animate(0.0)
        self.assertAlmostEqual(at_spawn[0].progress, 0.0)

    def test_retrigger_local_beat_and_progress_unchanged(self) -> None:
        # Regression pin: quantization is continuous-only. A retrigger instance
        # spawned off-grid keeps spawn-relative local_beat and progress.
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="beat_chase",
            sync_mode="retrigger",
            beat_division=1.0,
            params={"travel_beats": 2.0},
            seed=1,
            now=0.0,
            abs_beat=32.6,
            bpm=120.0,
        )
        renders = engine.animate(0.5)  # 0.5 s -> 1.0 elapsed beat
        self.assertAlmostEqual(renders[0].local_beat, 1.0)
        self.assertAlmostEqual(renders[0].progress, 0.5)

    def test_bucket_stable_within_continuous_arc(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="solid",
            sync_mode="continuous",
            beat_division=1.0,
            params={},
            seed=7,
            now=0.0,
            abs_beat=0.0,
            bpm=120.0,
        )
        buckets = []
        for beat in (0.5, 1.0, 1.5, 2.0):
            renders = engine.on_tick(beat, beat * 0.5, 120.0)
            buckets.append(renders[0].bucket)
        self.assertEqual(len(set(buckets)), 1)


class Awr189ReanchorTests(unittest.TestCase):
    """AWR-189: continuous-mode sustained-divergence re-anchor (operator-ratified).

    The heartbeat shape: a continuous look spawns while the live-BPM feed is
    mid-transition (stale rate), then the feed stabilizes at the true tempo —
    the look must re-anchor onto the real grid within the sustain window,
    while sub-delta wobble and brief flap-backs re-anchor nothing (AWR-141
    jitter immunity, no raw tracking).
    """

    def _continuous(self, *, born_bpm: float, params: dict | None = None) -> BeatSyncEngine:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="rt_groove_heartbeat",
            sync_mode="continuous",
            beat_division=1.0,
            params=params or {},
            seed=7,
            now=0.0,
            abs_beat=100.0,
            bpm=born_bpm,
        )
        return engine

    @staticmethod
    def _true_abs(t: float, bpm: float = 160.0) -> float:
        return 100.0 + t * (bpm / 60.0)

    def test_heartbeat_shape_reanchors_within_sustain_window(self) -> None:
        # Spawned at a stale 120 while the real grid runs 160: after >=3 s of
        # sustained divergence the phase must land back on the true grid.
        engine = self._continuous(born_bpm=120.0)
        for t in (1.0, 2.0, 3.0):
            renders = engine.on_tick(self._true_abs(t), t, 160.0)
            self.assertIsNone(engine._instances[0].reanchor)
            # still free-running at the stale rate while the timer arms
            self.assertAlmostEqual(renders[0].local_beat, t * 2.0)
        renders = engine.on_tick(self._true_abs(4.0), 4.0, 160.0)
        self.assertIsNotNone(engine._instances[0].reanchor)
        self.assertAlmostEqual(
            renders[0].local_beat % 1.0, self._true_abs(4.0) % 1.0, places=6)
        # and it keeps tracking the real grid afterwards
        renders = engine.on_tick(self._true_abs(5.5), 5.5, 160.0)
        self.assertAlmostEqual(
            renders[0].local_beat % 1.0, self._true_abs(5.5) % 1.0, places=6)

    def test_sub_delta_wobble_never_reanchors_and_is_byte_identical(self) -> None:
        engine = self._continuous(born_bpm=120.0)
        for i, live in enumerate((121.0, 119.2, 120.9, 118.4, 121.9), start=1):
            t = float(i) * 2.0  # 10 s of in-band wobble, far past the sustain window
            renders = engine.on_tick(self._true_abs(t, 120.0), t, live)
            self.assertIsNone(engine._instances[0].reanchor)
            self.assertEqual(renders[0].local_beat, 100.0 % 1.0 + t * 2.0)

    def test_flap_back_resets_the_divergence_timer(self) -> None:
        engine = self._continuous(born_bpm=120.0)
        engine.on_tick(self._true_abs(1.0), 1.0, 160.0)   # diverged, timer arms at 1.0
        engine.on_tick(self._true_abs(2.0), 2.0, 120.5)   # flap back in-band: timer resets
        engine.on_tick(self._true_abs(3.0), 3.0, 160.0)   # diverged again, re-arms at 3.0
        renders = engine.on_tick(self._true_abs(5.9), 5.9, 160.0)  # 2.9 s < sustain
        self.assertIsNone(engine._instances[0].reanchor)
        self.assertAlmostEqual(renders[0].local_beat, 5.9 * 2.0)

    def test_reanchor_preserves_local_t_bucket_and_progress(self) -> None:
        engine = self._continuous(born_bpm=120.0)
        before = engine.on_tick(self._true_abs(3.5), 3.5, 160.0)[0]
        bucket_before = before.bucket
        after = engine.on_tick(self._true_abs(4.5), 4.5, 160.0)[0]
        self.assertIsNotNone(engine._instances[0].reanchor)
        self.assertEqual(after.bucket, bucket_before)
        self.assertAlmostEqual(after.local_t, 4.5)                  # never resets
        self.assertAlmostEqual(after.local_t - before.local_t, 1.0)
        self.assertAlmostEqual(after.progress, 4.5 * 2.0)           # born-based, travel=1.0

    def test_params_override_delta_and_sustain(self) -> None:
        wide = self._continuous(born_bpm=120.0, params={"reanchor_bpm_delta": 50.0})
        for t in (2.0, 4.0, 8.0, 12.0):
            wide.on_tick(self._true_abs(t), t, 160.0)
        self.assertIsNone(wide._instances[0].reanchor)

        fast = self._continuous(born_bpm=120.0, params={"reanchor_sustain_s": 0.5})
        fast.on_tick(self._true_abs(0.2), 0.2, 160.0)
        fast.on_tick(self._true_abs(0.9), 0.9, 160.0)
        self.assertIsNotNone(fast._instances[0].reanchor)

    def test_second_sustained_divergence_converges_again(self) -> None:
        engine = self._continuous(born_bpm=120.0)
        for t in (1.0, 2.0, 3.0, 4.0):
            engine.on_tick(self._true_abs(t), t, 160.0)
        first = engine._instances[0].reanchor
        self.assertIsNotNone(first)
        # feed keeps being wrong vs the NEW rate (drops to 128): converges again
        for t in (5.0, 6.0, 7.0, 8.0, 9.0):
            engine.on_tick(self._true_abs(t, 128.0), t, 128.0)
        second = engine._instances[0].reanchor
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        self.assertAlmostEqual(second[2], 128.0)

    def test_wrap_and_manual_fire_reset_divergence_state(self) -> None:
        engine = self._continuous(born_bpm=120.0)
        engine.on_tick(self._true_abs(1.0), 1.0, 160.0)          # timer armed
        engine.on_tick(90.0, 2.0, 160.0)                          # real wrap: fresh instance
        self.assertIsNone(engine._diverged_since)
        self.assertIsNone(engine._instances[0].reanchor)
        self.assertEqual(engine._instances[0].born_bpm, 160.0)

        engine.on_tick(91.0, 3.0, 120.0)                          # diverged vs 160, arms
        engine.fire_manual(3.5, 91.5, 120.0)                      # manual restart
        self.assertIsNone(engine._diverged_since)
        self.assertIsNone(engine._instances[0].reanchor)

    def test_retrigger_and_overlap_paths_untouched(self) -> None:
        engine = BeatSyncEngine()
        engine.configure(
            effect_name="comet", sync_mode="retrigger", beat_division=4.0,
            params={}, seed=1, now=0.0, abs_beat=0.0, bpm=120.0,
        )
        for t in (2.0, 4.0, 6.0):  # no division crossing, wildly divergent bpm
            renders = engine.on_tick(1.0 + t * 0.01, t, 999.0)
        self.assertIsNone(engine._instances[0].reanchor)
        self.assertAlmostEqual(renders[0].local_beat, 6.0 * 2.0)  # spawn-relative


if __name__ == "__main__":
    unittest.main()
