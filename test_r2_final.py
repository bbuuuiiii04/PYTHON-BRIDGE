import sys
from pathlib import Path
sys.path.insert(0, str(Path('/Users/bbui')))
import unittest
from rb_ss_bridge_v2.tests.test_laser_executor_lifecycle import _make_config, _FakeMidiOutput, _ctx, _decision, _scene
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor
from rb_ss_bridge_v2.laser_models import LaserPersonality

class TestLaserBlackoutEquivalence(unittest.TestCase):
    def test_blackout_equivalence(self) -> None:
        scenes = {
            "d1": _scene("d1", note=41),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",),
            drop_lifecycle_mirror=True,
        )

        # Flag ON (blackout_mask)
        backend_on = _FakeMidiOutput()
        ex_on = LaserSceneExecutor(config=_make_config(scenes, "blackout_mask"), backend=backend_on, personality=personality, randomize_cursors=False)
        ctx_on = _ctx(smart_drop_blackout_arm=True)
        ex_on.on_decision(_decision("d1", "drop_crossing", "drop"), ctx_on)
        blackout_on = [m for m, _ in backend_on.calls if m.kind == "manual_blackout"]
        
        # Flag OFF (scene)
        backend_off = _FakeMidiOutput()
        ex_off = LaserSceneExecutor(config=_make_config(scenes, "scene"), backend=backend_off, personality=personality, randomize_cursors=False)
        ctx_off = _ctx(smart_drop_blackout_arm=True)
        ex_off.on_decision(_decision("d1", "drop_crossing", "drop"), ctx_off)
        blackout_off = [m for m, _ in backend_off.calls if m.kind == "manual_blackout"]

        # 1. Allowed crossing, flag-on vs flag-off: assert blackout pair byte-identical
        self.assertTrue(len(blackout_on) > 0)
        self.assertEqual(len(blackout_on), len(blackout_off))
        for b_on, b_off in zip(blackout_on, blackout_off):
            self.assertEqual(b_on.channel, b_off.channel)
            self.assertEqual(b_on.note, b_off.note)
            self.assertEqual(b_on.velocity, b_off.velocity)
            self.assertEqual(b_on.kind, b_off.kind)

    def test_disallowed_crossing_no_stranded_dark(self) -> None:
        scenes = {
            "d1": _scene("d1", note=41),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",),
            drop_lifecycle_mirror=True,
        )
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(config=_make_config(scenes, "blackout_mask"), backend=backend, personality=personality, randomize_cursors=False)
        
        # 2. Disallowed crossing, flag-on: deliver post_drop_cycle with autoloop_tick_just_fired=False
        ctx = _ctx(autoloop_tick_just_fired=False, smart_drop_blackout_arm=True)
        
        ex.blackout_pending_for_drop_window = True
        ex.mask_owners.add("smart_drop")
        
        # If we just clear the pending blackout through `clear_pending_blackout` or send a disallowed crossing
        ex.on_decision(_decision("d1", "post_drop_cycle", "post_drop"), ctx)
        
        self.assertFalse(ex.blackout_pending_for_drop_window)
        self.assertEqual(len(ex.mask_owners), 0)

if __name__ == "__main__":
    unittest.main()
