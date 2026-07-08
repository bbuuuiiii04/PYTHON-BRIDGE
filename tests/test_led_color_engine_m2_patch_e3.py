"""Tests for M2.5 Patch E3: ambient twinkle slot cue.

Covers:
- _slot_twinkle unit tests (shape, ambient slot use, no white-slot writes)
- Config: rt_twinkle generic look is available in the ambient bank
- Regression: legacy rt_twinkle_blue remains registered, stored, and exempt
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
    _slot_twinkle,
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


def _call_twinkle(beat: float, *, segments: int = 60,
                  local_t: float | None = None) -> list[list[float]]:
    return _slot_twinkle(
        beat=beat,
        local_t=beat if local_t is None else local_t,
        frame_index=int(beat * 40.0),
        params={},
        segments=segments,
        seed=42,
    )


def _solid_config() -> ColorEngineConfig:
    return ColorEngineConfig(
        enabled=True,
        drama_by_role=False,
        role_spread={},
        step_within_section={"ambient": False},
        slot_fill_strategy_by_look={},
        palettes={
            "solid_red": Palette(
                range=("red", "red"),
                spread=0.0,
                weight=1.0,
            )
        },
        set_seed_mode="fixed:99",
    )


class SlotTwinkleTests(unittest.TestCase):
    def test_shape_segments_x_6(self) -> None:
        for beat in (0.0, 0.25, 4.0, 16.0, 31.5):
            field = _call_twinkle(beat=beat, segments=60)
            self.assertEqual(len(field), 60)
            for row in field:
                self.assertEqual(len(row), MAX_SLOTS)

    def test_uses_engine_slots_0_to_4_and_never_slot_5(self) -> None:
        used: set[int] = set()
        active_frames = 0
        for tick in range(0, 32 * 8):
            field = _call_twinkle(tick / 8.0, segments=80)
            energy = sum(sum(row) for row in field)
            if energy > 0.0:
                active_frames += 1
            used.update(_used_slots(field))
            for row in field:
                self.assertGreaterEqual(min(row), 0.0)
                self.assertEqual(row[5], 0.0)
        self.assertGreater(active_frames, 0)
        self.assertTrue(set(range(5)).issubset(used), f"used slots: {sorted(used)}")
        self.assertNotIn(5, used)

    def test_deterministic_for_same_inputs(self) -> None:
        a = _call_twinkle(beat=12.375, segments=64, local_t=12.375)
        b = _call_twinkle(beat=12.375, segments=64, local_t=12.375)
        self.assertEqual(a, b)

    def test_never_negative_after_macro_swell_crosses_zero(self) -> None:
        for tick in range(32 * 8, 64 * 8):
            beat = tick / 8.0
            field = _call_twinkle(beat=beat, segments=80)
            for row in field:
                self.assertGreaterEqual(min(row), 0.0, f"beat={beat}")


class PatchE3ConfigTests(unittest.TestCase):
    def _load_config(self):
        root = Path(__file__).resolve().parents[1]
        return load_led_look_director_config(str(root / "config/led_look_director.example.json"))

    def test_rt_twinkle_look_example(self) -> None:
        result = self._load_config()
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), (), f"example config errors: {result.errors}")

        look = result.config.looks.get("rt_twinkle")
        self.assertIsNotNone(look, "rt_twinkle missing from example config")
        self.assertEqual(look.scene_ref, "rt_twinkle")
        self.assertEqual(look.color_source, "engine")
        self.assertFalse(look.allow_strobe)
        self.assertEqual(look.safety_class, "ambient")
        self.assertEqual(look.params, {})
        self.assertIn("rt_twinkle", result.config.banks["default"].ambient)

    def test_legacy_twinkle_blue_still_resolves(self) -> None:
        self.assertIn("twinkle_blue", _EFFECTS)
        self.assertIn("twinkle_blue", REALTIME_EFFECT_NAMES)

        result = self._load_config()
        self.assertTrue(result.available, f"config not available: {result.reason}")
        legacy = result.config.looks["rt_twinkle_blue"]
        self.assertEqual(legacy.scene_ref, "twinkle_blue")
        self.assertNotIn("rt_twinkle_blue", result.config.banks["default"].ambient)
        self.assertIn("rt_twinkle_blue", result.config.banks["legacy_color_suffix"].ambient)
        self.assertIn("rt_twinkle_blue", result.config.color_engine.exempt_looks)


class PatchE3RegistrationTests(unittest.TestCase):
    def test_rt_twinkle_registrations(self) -> None:
        self.assertIn("rt_twinkle", SLOT_EFFECTS)
        self.assertIn("rt_twinkle", REALTIME_EFFECT_NAMES)
        self.assertNotIn("rt_twinkle", REALTIME_STROBE_EFFECTS)
        keys = _M2_PHASE2A_PARAM_KEYS.get("rt_twinkle", frozenset())
        all_keys = REALTIME_EFFECT_PARAM_KEYS.get("rt_twinkle", frozenset())
        self.assertIn("duration_beats", keys)
        self.assertNotIn("slot_colors", keys)
        self.assertNotIn("slot_colors", all_keys)

    def test_rt_twinkle_can_resolve_solid_slots(self) -> None:
        engine = LedColorEngine(_solid_config(), set_seed=99)
        engine.begin_dispatch(
            active_deck=1,
            load_gen=1,
            content_id="solid-twinkle",
            filepath="/tracks/solid-twinkle.wav",
            role="ambient",
            section_id="ambient-solid",
            cycle=0,
        )
        slots = engine.resolve_slot_colors(
            role="ambient",
            section_id="ambient-solid",
            cycle=0,
            look_name="rt_twinkle",
            color_source="engine",
        )["slot_colors"]
        self.assertEqual(len(slots), MAX_SLOTS)
        self.assertEqual(len(set(slots[:5])), 1)
        self.assertEqual(slots[5], (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
