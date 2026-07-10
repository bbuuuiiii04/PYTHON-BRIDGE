"""Tests for M2.5 Patch B: Slotize groove chase."""
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import govee_frame_renderer as gfr
from rb_ss_bridge_v2.govee_frame_renderer import (
    MAX_SLOTS,
    SLOT_EFFECTS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    _M2_PHASE2A_PARAM_KEYS,
    _slot_groove_chase,
    _EFFECTS,
)
from rb_ss_bridge_v2.led_config import load_led_look_director_config

class PatchBTests(unittest.TestCase):
    def test_slot_groove_chase_returns_segments_x_6(self):
        segments = 20
        # Call the function for beat 0.0 to 10.0
        for beat in [0.0, 1.5, 3.2, 4.0]:
            field = _slot_groove_chase(
                beat=beat, local_t=0.0, frame_index=0,
                params={}, segments=segments, seed=42
            )
            self.assertEqual(len(field), segments)
            for row in field:
                self.assertEqual(len(row), 6)  # Exactly 6 lanes

    def test_slots_0_to_4_receive_nonzero_intensity(self):
        # AWR-156 knob #4: the mashup died -- a head is now ONE fixed palette
        # slot for its whole loop_beats cycle (cycle = int(cue_beat/loop_beats),
        # slots = cycle % 5 and (cycle + 2) % 5), not an intensity-swept
        # gradient. The sweep window widened from 8 beats to 40 beats (10
        # full loop_beats cycles) so all 5 cycle-derived slots still appear.
        segments = 30
        used_slots = set()
        for beat in range(400):  # sweep across beats
            field = _slot_groove_chase(
                beat=beat / 10.0, local_t=0.0, frame_index=0,
                params={}, segments=segments, seed=42
            )
            for row in field:
                for slot_idx, intensity in enumerate(row):
                    if intensity > 0.0:
                        used_slots.add(slot_idx)

        # We expect slots 0, 1, 2, 3, 4 to be used for the comet
        for expected_slot in range(5):
            self.assertIn(expected_slot, used_slots)

    def test_slot_5_remains_exactly_zero(self):
        segments = 30
        for beat in range(80):
            field = _slot_groove_chase(
                beat=beat / 10.0, local_t=0.0, frame_index=0,
                params={}, segments=segments, seed=42
            )
            for row in field:
                self.assertEqual(row[5], 0.0, "Slot 5 must remain pure 0.0")

    def test_rt_groove_chase_in_slot_effects(self):
        self.assertIn("rt_groove_chase", SLOT_EFFECTS)

    def test_rt_groove_chase_in_realtime_effect_names(self):
        self.assertIn("rt_groove_chase", REALTIME_EFFECT_NAMES)

    def test_slot_colors_not_in_param_keys(self):
        keys = _M2_PHASE2A_PARAM_KEYS.get("rt_groove_chase", frozenset())
        self.assertNotIn("slot_colors", keys)
        
        all_keys = REALTIME_EFFECT_PARAM_KEYS.get("rt_groove_chase", frozenset())
        self.assertNotIn("slot_colors", all_keys)

    def test_legacy_names_still_resolve(self):
        legacy_names = [
            "groove_chase_red",
            "groove_chase_blue",
            "groove_chase_cyan",
            "groove_chase_green",
            "groove_chase_cyan_white",
        ]
        for name in legacy_names:
            self.assertIn(name, REALTIME_EFFECT_NAMES)
            self.assertIn(name, _EFFECTS)

    def test_tracked_config_validates(self):
        # config/led_look_director.example.json is tracked
        example_path = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"
        
        res = load_led_look_director_config(str(example_path))
        self.assertEqual(len(res.errors), 0, f"Example config validation errors: {res.errors}")
        
        # Check that the look exists
        self.assertIn("rt_groove_chase", res.config.looks)
        look = res.config.looks["rt_groove_chase"]
        self.assertEqual(look.scene_ref, "rt_groove_chase")
        self.assertEqual(look.color_source, "engine")
        # AWR-156 knob #9: role-scoped width (was {}).
        self.assertEqual(look.params, {"width": 2.5, "loop_beats": 4.0})

if __name__ == "__main__":
    unittest.main()
