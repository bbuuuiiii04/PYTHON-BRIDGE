"""Tests for M2.5 Patch E2: center-comet slot cue.

Covers:
- _slot_post_drop_center_comet unit tests (shape, strobe gate, slot use)
- Config: rt_post_drop_center_comet look and rt_drop_center_burst pairing
- Regression: legacy blue/cyan center comet still resolves
- Solid slot-color selection remains possible for every slot cue
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    MAX_SLOTS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    _EFFECTS,
    _M2_PHASE2A_PARAM_KEYS,
    _slot_post_drop_center_comet,
)
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette  # noqa: E402


def _used_slots(field: list[list[float]]) -> set[int]:
    out: set[int] = set()
    for row in field:
        for slot_idx, intensity in enumerate(row):
            if intensity > 0.0:
                out.add(slot_idx)
    return out


def _call_center_comet(beat: float, *, segments: int = 60,
                       frame_index: int = 0) -> list[list[float]]:
    return _slot_post_drop_center_comet(
        beat=beat,
        local_t=0.0,
        frame_index=frame_index,
        params={},
        segments=segments,
        seed=42,
    )


def _role_for_slot_look(name: str) -> str:
    if name == "rt_twinkle":
        return "ambient"
    if name.startswith("rt_drop_"):
        return "drop"
    if name.startswith("rt_post_drop_") or name.startswith("post_drop_"):
        return "post_drop"
    if name.startswith("breakdown_"):
        return "breakdown"
    return "groove"


def _solid_config(strategy_by_look: dict[str, str] | None = None) -> ColorEngineConfig:
    return ColorEngineConfig(
        enabled=True,
        drama_by_role=False,
        role_spread={},
        step_within_section={
            "drop": False,
            "post_drop": True,
            "groove": True,
            "breakdown": False,
            "ambient": False,
        },
        slot_fill_strategy_by_look=strategy_by_look or {},
        palettes={
            "solid_red": Palette(
                range=("red", "red"),
                spread=0.0,
                weight=1.0,
            )
        },
        set_seed_mode="fixed:99",
    )


class SlotPostDropCenterCometTests(unittest.TestCase):
    def test_shape_segments_x_6(self) -> None:
        for beat in (0.0, 0.25, 0.5, 1.0, 1.5):
            field = _call_center_comet(beat=beat, segments=60)
            self.assertEqual(len(field), 60)
            for row in field:
                self.assertEqual(len(row), MAX_SLOTS)

    def test_strobe_gate_can_go_dark(self) -> None:
        # AWR-161: the strobe gate migrated to the wall-clock Hz gate
        # (_hz_strobe_on), driven by local_t not beat. Pin the real contract:
        # across one full strobe period at the reference hz 6.0 / duty 0.3
        # there must be BOTH lit frames and fully dark frames -- a strobe that
        # never goes dark is the exact bug this guards.
        cycle_s = 1.0 / 6.0
        params = {"hz": 6.0, "duty": 0.3}
        lit = dark = False
        for i in range(48):
            field = _slot_post_drop_center_comet(
                beat=0.0625,
                local_t=cycle_s * i / 48.0,
                frame_index=i,
                params=params,
                segments=60,
                seed=42,
            )
            if sum(sum(row) for row in field) > 0.0:
                lit = True
            else:
                dark = True
        self.assertTrue(lit, "strobe never lit across a full period")
        self.assertTrue(dark, "strobe never went dark across a full period")

    def test_uses_slots_0_to_4_and_never_slot_5(self) -> None:
        used: set[int] = set()
        for tick in range(640):
            field = _call_center_comet(tick / 80.0, segments=60, frame_index=tick)
            used.update(_used_slots(field))
            for row in field:
                self.assertEqual(row[5], 0.0)
        self.assertTrue(set(range(5)).issubset(used), f"used slots: {sorted(used)}")
        self.assertNotIn(5, used)

    def test_center_out_motion_hits_both_halves(self) -> None:
        field = _call_center_comet(beat=0.5, segments=60)
        active = [idx for idx, row in enumerate(field) if any(value > 0.0 for value in row[:5])]
        self.assertTrue(any(idx < 30 for idx in active), f"active={active}")
        self.assertTrue(any(idx >= 30 for idx in active), f"active={active}")


class PatchE2ConfigTests(unittest.TestCase):
    def _load_config(self):
        root = Path(__file__).resolve().parents[1]
        return load_led_look_director_config(str(root / "config/led_look_director.example.json"))

    def test_rt_post_drop_center_comet_look_example(self) -> None:
        result = self._load_config()
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), (), f"example config errors: {result.errors}")

        look = result.config.looks.get("rt_post_drop_center_comet")
        self.assertIsNotNone(look, "rt_post_drop_center_comet missing from example config")
        self.assertEqual(look.scene_ref, "rt_post_drop_center_comet")
        self.assertEqual(look.color_source, "engine")
        self.assertTrue(look.allow_strobe)
        self.assertEqual(look.safety_class, "post_drop")
        # AWR-156 knob #9: role-scoped width (was {}).
        self.assertEqual(look.params, {"width": 4})
        self.assertIn("rt_post_drop_center_comet", result.config.banks["default"].post_drop)

    def test_generic_center_burst_pairs_to_generic_center_comet(self) -> None:
        result = self._load_config()
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        pair = result.config.drop_pairs.get("rt_drop_center_burst")
        self.assertIsNotNone(pair)
        self.assertEqual(pair.post_drop, "rt_post_drop_center_comet")


class PatchE2RegistrationTests(unittest.TestCase):
    def test_rt_post_drop_center_comet_registrations(self) -> None:
        self.assertIn("rt_post_drop_center_comet", SLOT_EFFECTS)
        self.assertIn("rt_post_drop_center_comet", REALTIME_EFFECT_NAMES)
        self.assertIn("rt_post_drop_center_comet", REALTIME_STROBE_EFFECTS)
        keys = _M2_PHASE2A_PARAM_KEYS.get("rt_post_drop_center_comet", frozenset())
        all_keys = REALTIME_EFFECT_PARAM_KEYS.get("rt_post_drop_center_comet", frozenset())
        self.assertIn("duration_beats", keys)
        self.assertNotIn("slot_colors", keys)
        self.assertNotIn("slot_colors", all_keys)

    def test_legacy_center_comet_still_resolves(self) -> None:
        self.assertIn("post_drop_center_comet_blue_cyan", _EFFECTS)
        self.assertIn("post_drop_center_comet_blue_cyan", REALTIME_EFFECT_NAMES)

        root = Path(__file__).resolve().parents[1]
        result = load_led_look_director_config(str(root / "config/led_look_director.example.json"))
        self.assertTrue(result.available, f"config not available: {result.reason}")
        legacy = result.config.looks["rt_post_drop_center_comet_blue_cyan"]
        self.assertEqual(legacy.scene_ref, "post_drop_center_comet_blue_cyan")
        self.assertIn(
            "rt_post_drop_center_comet_blue_cyan",
            result.config.color_engine.exempt_looks,
        )

    def test_slot_effects_has_current_entries(self) -> None:
        expected = {
            "rt_groove_chase",
            "rt_groove_nebula",
            "rt_post_drop_chase",
            "rt_post_drop_nebula",
            "rt_drop_chase",
            "rt_drop_nebula",
            "rt_drop_center_burst",
            "rt_post_drop_center_comet",
            "rt_twinkle",
            "groove_center_chase",
            "groove_center_burst_retract",
            "post_drop_firework_chase",
            "breakdown_full_breathing",
            "breakdown_star_twinkle",
            # AWR-156: promoted accepted looks.
            "rt_groove_heartbeat",
            "rt_post_drop_firework_remnants",
        }
        self.assertEqual(set(SLOT_EFFECTS), expected)


class SolidSlotColorSelectionTests(unittest.TestCase):
    def test_every_slot_cue_can_resolve_solid_gradient_slots(self) -> None:
        engine = LedColorEngine(_solid_config(), set_seed=99)
        for idx, look_name in enumerate(sorted(SLOT_EFFECTS)):
            role = _role_for_slot_look(look_name)
            engine.begin_dispatch(
                active_deck=1,
                load_gen=idx + 1,
                content_id=f"solid-gradient-{look_name}",
                filepath=f"/tracks/{look_name}.wav",
                role=role,
                section_id=f"{role}-solid",
                cycle=0,
            )
            slots = engine.resolve_slot_colors(
                role=role,
                section_id=f"{role}-solid",
                cycle=0,
                look_name=look_name,
                color_source="engine",
            )["slot_colors"]
            self.assertEqual(len(slots), MAX_SLOTS, look_name)
            self.assertEqual(len(set(slots[:5])), 1, look_name)
            self.assertEqual(slots[5], (255, 255, 255), look_name)

    def test_rt_chase_comet_and_nebula_cues_can_resolve_solid_random_slots(self) -> None:
        chase_comet_and_nebula = {
            name: "random_with_replacement"
            for name in SLOT_EFFECTS
            if "chase" in name or "comet" in name or "nebula" in name
        }
        engine = LedColorEngine(_solid_config(chase_comet_and_nebula), set_seed=99)
        for idx, look_name in enumerate(sorted(chase_comet_and_nebula)):
            role = _role_for_slot_look(look_name)
            engine.begin_dispatch(
                active_deck=1,
                load_gen=idx + 1,
                content_id=f"solid-random-{look_name}",
                filepath=f"/tracks/{look_name}.wav",
                role=role,
                section_id=f"{role}-solid-random",
                cycle=idx,
            )
            slots = engine.resolve_slot_colors(
                role=role,
                section_id=f"{role}-solid-random",
                cycle=idx,
                look_name=look_name,
                color_source="engine",
            )["slot_colors"]
            self.assertEqual(len(slots), MAX_SLOTS, look_name)
            self.assertEqual(len(set(slots[:5])), 1, look_name)
            self.assertEqual(slots[5], (255, 255, 255), look_name)


if __name__ == "__main__":
    unittest.main()
