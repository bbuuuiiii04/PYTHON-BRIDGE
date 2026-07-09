"""Tests for M2.5 Patch C: Slotize post-drop chase."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    _EFFECTS,
    MAX_SLOTS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    _M2_PHASE2A_PARAM_KEYS,
    _slot_post_drop_chase,
)
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402


class PatchCTests(unittest.TestCase):
    def _field(self, beat: float, segments: int = 30):
        return _slot_post_drop_chase(
            beat=beat,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=segments,
            seed=42,
        )

    def test_slot_post_drop_chase_returns_segments_x_6(self) -> None:
        for beat in (0.0, 0.5, 1.0, 2.25, 4.0):
            field = self._field(beat, segments=24)
            self.assertEqual(len(field), 24)
            for row in field:
                self.assertEqual(len(row), MAX_SLOTS)

    def test_slots_0_to_4_receive_nonzero_intensity(self) -> None:
        used_slots: set[int] = set()
        for tick in range(160):
            field = self._field(tick / 20.0, segments=36)
            for row in field:
                for slot_idx, intensity in enumerate(row):
                    if intensity > 0.0:
                        used_slots.add(slot_idx)
        for expected_slot in range(5):
            self.assertIn(expected_slot, used_slots)

    def test_slot_5_remains_zero_no_firework_accent(self) -> None:
        for tick in range(160):
            field = self._field(tick / 20.0, segments=36)
            for row in field:
                self.assertEqual(row[5], 0.0)

    def test_strobe_off_frames_are_dark(self) -> None:
        # AWR-161: the strobe gate migrated from a beat-parity gate to the
        # wall-clock Hz gate (_hz_strobe_on), driven by local_t not beat.
        # Pin the real contract: across one full strobe period at the
        # reference hz 6.0 / duty 0.3 there must be BOTH lit frames and fully
        # dark frames. A strobe that never goes dark is the exact bug class
        # this guards, so sweep local_t over a whole 1/6 s cycle and prove
        # both outcomes occur.
        cycle_s = 1.0 / 6.0
        params = {"hz": 6.0, "duty": 0.3}
        lit = dark = False
        for i in range(48):
            field = _slot_post_drop_chase(
                beat=0.07,
                local_t=cycle_s * i / 48.0,
                frame_index=i,
                params=params,
                segments=20,
                seed=42,
            )
            if any(value > 0.0 for row in field for value in row):
                lit = True
            else:
                dark = True
        self.assertTrue(lit, "strobe never lit across a full period")
        self.assertTrue(dark, "strobe never went dark across a full period")

    def test_rt_post_drop_chase_registrations(self) -> None:
        self.assertIn("rt_post_drop_chase", SLOT_EFFECTS)
        self.assertIn("rt_post_drop_chase", REALTIME_EFFECT_NAMES)
        self.assertIn("rt_post_drop_chase", REALTIME_STROBE_EFFECTS)
        keys = _M2_PHASE2A_PARAM_KEYS.get("rt_post_drop_chase", frozenset())
        all_keys = REALTIME_EFFECT_PARAM_KEYS.get("rt_post_drop_chase", frozenset())
        self.assertNotIn("slot_colors", keys)
        self.assertNotIn("slot_colors", all_keys)

    def test_legacy_post_drop_chase_names_still_resolve(self) -> None:
        legacy_names = [
            "post_drop_chase_blue",
            "post_drop_chase_cyan",
            "post_drop_chase_red",
            "post_drop_chase_green",
            "post_drop_chase_cyan_white",
        ]
        for name in legacy_names:
            self.assertIn(name, REALTIME_EFFECT_NAMES)
            self.assertIn(name, _EFFECTS)

    def test_tracked_and_live_configs_validate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        # AWR-156 knob #9 added a role-scoped width param. It landed in the
        # TRACKED example config first; the 2026-07-09 executive-approved live
        # mirror then carried it into the gitignored/read-only live config, so
        # both now render with {'width': 4}. Pinned explicit per approved
        # mirror content (drift tripwire: an unapproved live change turns red).
        expected_params_by_rel = {
            "config/led_look_director.example.json": {"width": 4},
            "config/led_look_director.json": {"width": 4},
        }
        for rel in ("config/led_look_director.example.json", "config/led_look_director.json"):
            cfg_path = root / rel
            if not cfg_path.exists():
                # Live config is gitignored / local-only; absent on CI. The
                # tracked example.json above still exercises validation.
                continue
            result = load_led_look_director_config(str(cfg_path))
            self.assertEqual(tuple(result.errors), (), f"{rel}: {result.errors}")
            self.assertIn("rt_post_drop_chase", result.config.looks)
            look = result.config.looks["rt_post_drop_chase"]
            self.assertEqual(look.scene_ref, "rt_post_drop_chase")
            self.assertEqual(look.color_source, "engine")
            self.assertEqual(look.params, expected_params_by_rel[rel], msg=rel)
            self.assertIn("rt_post_drop_chase", result.config.banks["default"].post_drop)

    def test_live_config_slot_color_smoke(self) -> None:
        root = Path(__file__).resolve().parents[1]
        live = root / "config/led_look_director.json"
        if not live.exists():
            self.skipTest("live LED config not present (gitignored; local-only)")
        result = load_led_look_director_config(str(live))
        self.assertEqual(tuple(result.errors), ())
        engine = LedColorEngine(result.config.color_engine, set_seed=123)
        engine.begin_dispatch(
            active_deck=1,
            load_gen=7,
            content_id="patch-c",
            filepath="/tracks/patch-c.wav",
            role="post_drop",
            section_id="pd-1",
            cycle=0,
        )
        slots = engine.resolve_slot_colors(
            role="post_drop",
            section_id="pd-1",
            cycle=0,
            look_name="rt_post_drop_chase",
            color_source="engine",
        )["slot_colors"]
        self.assertEqual(len(slots), MAX_SLOTS)
        # AWR-156 zone tint landed in the 2026-07-09 executive-approved live
        # mirror: slot 5 now renders the approved tint (was pure white).
        self.assertEqual(slots[5], (220, 240, 255))
        self.assertGreater(len(set(slots[:5])), 1)


if __name__ == "__main__":
    unittest.main()
