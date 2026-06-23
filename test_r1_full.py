import sys
from pathlib import Path
sys.path.insert(0, str(Path('/Users/bbui')))
import unittest
from rb_ss_bridge_v2.state_manager import StateManager
from rb_ss_bridge_v2.rb_memory import PositionCache
from unittest.mock import Mock
import queue
from rb_ss_bridge_v2.drop_lifecycle import DropLifecycle, DropLifecycleConfig
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState

def _cfg(max_drops=2, impact_beats=8.0, cycle_beats=32.0):
    return DropLifecycleConfig(
        max_drops_in_a_row=max_drops,
        drop_impact_beats=impact_beats,
        post_drop_cycle_beats=cycle_beats,
        impact_predecessors=frozenset({"up", "low", "buildup", "breakdown"}),
    )

def _sp(**kw) -> SmartPhrasingState:
    defaults = dict(
        abs_beat=None,
        current_phrase_start_beat=None,
        beats_into_phrase=None,
        active_drop_beat=None,
        beats_to_next_drop=None,
        current_phrase_is_up=False,
        current_phrase_is_low=False,
        current_phrase_is_chorus=False,
        phrase_start_crossing=False,
        smart_drop_crossing=False,
        previous_phrase_label="other",
        current_phrase_label="other",
        smart_post_drop_active=False,
        smart_breakdown_active=False,
        breakdown_start_crossing=False,
        transition_window_active=False,
    )
    defaults.update(kw)
    return SmartPhrasingState(**defaults)

class TestMock(unittest.TestCase):
    def setUp(self):
        self.lc = DropLifecycle(_cfg(impact_beats=8.0, max_drops=2))
        self.sm = StateManager(queue.Queue(), PositionCache(), Mock())
        # mock flat window on LED
        self.sm.LED_MAX_DROP_IMPACTS = 2
        self.sm.LED_DROP_IMPACT_BEATS = 8.0

    def assertParity(self, sp, msg=""):
        res = self.lc.resolve(sp, mutate=True)
        # LED non-drop roles (breakdown, pre_drop, buildup, low, groove) mapped to none
        led_role = self.sm._led_role_from_smart_phrasing(sp, mutate=True)
        if led_role in ("breakdown", "pre_drop", "buildup", "low", "groove"):
            led_role = "none"
        self.assertEqual(res.role, led_role, f"{msg}: pure={res.role}, led={led_role}")

    def test_parity(self):
        # 1. allowed predecessor -> drop -> hold -> post_drop
        sp1 = _sp(smart_drop_crossing=True, active_drop_beat=64.0, previous_phrase_label="up", current_phrase_is_chorus=True, abs_beat=64.0)
        self.assertParity(sp1, "Allowed cross")

        sp2 = _sp(current_phrase_is_chorus=True, smart_post_drop_active=True, abs_beat=68.0)
        self.assertParity(sp2, "Hold impact")

        sp3 = _sp(current_phrase_is_chorus=True, smart_post_drop_active=True, abs_beat=80.0)
        self.assertParity(sp3, "Post drop")

        # 4. Clear when leaving
        sp4 = _sp(abs_beat=200.0, current_phrase_label="other")
        self.assertParity(sp4, "Clear leaving")

        # 2. disallowed predecessor -> post_drop
        sp5 = _sp(smart_drop_crossing=True, active_drop_beat=300.0, previous_phrase_label="groove", abs_beat=300.0, current_phrase_is_chorus=True)
        self.assertParity(sp5, "Disallowed cross")
        
        sp6 = _sp(abs_beat=400.0, current_phrase_label="other")
        self.assertParity(sp6, "Clear leaving again")

        # 3. chorus -> chorus cap at max=2
        sp7 = _sp(smart_drop_crossing=True, active_drop_beat=500.0, previous_phrase_label="up", abs_beat=500.0, current_phrase_is_chorus=True)
        self.assertParity(sp7, "Chorus 1")
        
        sp8 = _sp(smart_drop_crossing=True, active_drop_beat=600.0, previous_phrase_label="chorus", abs_beat=600.0, current_phrase_is_chorus=True)
        self.assertParity(sp8, "Chorus 2")

        sp9 = _sp(smart_drop_crossing=True, active_drop_beat=700.0, previous_phrase_label="chorus", abs_beat=700.0, current_phrase_is_chorus=True)
        self.assertParity(sp9, "Chorus 3 (capped)")

if __name__ == "__main__":
    unittest.main()
