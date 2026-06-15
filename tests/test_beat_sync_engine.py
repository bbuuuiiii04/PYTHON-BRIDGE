from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.beat_sync_engine import (  # noqa: E402
    MAX_CATCHUP,
    MAX_PULSES,
    BeatSyncEngine,
)


class BeatSyncEngineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
