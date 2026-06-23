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
        config = _make_config(scenes)
        
        # Flag ON
        pers_on = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",), drop_lifecycle_mirror=True,
        )
        backend_on = _FakeMidiOutput()
        ex_on = LaserSceneExecutor(config=config, backend=backend_on, personality=pers_on, randomize_cursors=False)
        ctx_on = _ctx(smart_drop_blackout_arm=True)
        ex_on.on_decision(_decision("d1", "drop_crossing", "drop"), ctx_on)
        blackout_on = [m for m, _ in backend_on.calls if m.kind == "manual_blackout"]
        
        # Flag OFF
        pers_off = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",), drop_lifecycle_mirror=False,
        )
        backend_off = _FakeMidiOutput()
        ex_off = LaserSceneExecutor(config=config, backend=backend_off, personality=pers_off, randomize_cursors=False)
        ctx_off = _ctx(smart_drop_blackout_arm=True)
        ex_off.on_decision(_decision("d1", "drop_crossing", "drop"), ctx_off)
        blackout_off = [m for m, _ in backend_off.calls if m.kind == "manual_blackout"]

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
        pers_on = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",), drop_lifecycle_mirror=True,
        )
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(config=_make_config(scenes), backend=backend, personality=pers_on, randomize_cursors=False)
        
        # simulated pending state
        ex._blackout_pending_for_drop_window = True
        ex._mask_owners.add("smart_drop")
        
        ctx = _ctx(autoloop_tick_just_fired=False, smart_drop_blackout_arm=True)
        ex.on_decision(_decision("d1", "post_drop_cycle", "post_drop"), ctx)
        
        # Actually a disallowed crossing (drop_cycle/post_drop_cycle with autoloop_tick_just_fired=False) 
        # doesn't run `_resolve_pending_blackout` unless we explicitly call clear_pending_blackout.
        # Wait, the spec says: "deliver the gated-off equivalent (a post_drop_cycle/drop_cycle decision with autoloop_tick_just_fired=False, i.e., the blackout-mode crossing tick) and assert that after the clear the executor ends with blackout_pending_for_drop_window=False and empty mask_owners. If exercising the SM net requires StateManager, assert the executor-level invariant directly (clear_pending_blackout leaves it clear)."
        
        # So we just test clear_pending_blackout leaves it clear.
        ex.clear_pending_blackout()
        
        self.assertFalse(ex._blackout_pending_for_drop_window)
        self.assertEqual(len(ex._mask_owners), 0)

if __name__ == "__main__":
    unittest.main()
