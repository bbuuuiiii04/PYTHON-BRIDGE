"""Tests for M0 color engine config plumbing.

Covers:
- ColorEngineConfig / Palette dataclasses in led_models.py
- _validate_color_engine / _parse_color_engine in led_config.py
- LEDLook.color_source / diy_color fields
- LEDConfig.color_engine field
- Critical invariant: malformed color_engine disables only the engine,
  never LED automation (available must stay True)
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_config import (  # noqa: E402
    load_led_look_director_config,
    load_led_look_director_config_from_dict,
)
from rb_ss_bridge_v2.led_models import (  # noqa: E402
    ColorEngineConfig,
    IdentityV2Config,
    LEDLook,
    Palette,
    ZoneRampConfig,
)

_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


# ---------------------------------------------------------------------------
# Minimal valid base config (no color_engine block)
# ---------------------------------------------------------------------------

def _base_config() -> dict:
    """Minimal valid LED config with no color_engine block."""
    return {
        "schema_version": 1,
        "enabled": True,
        "dry_run": False,
        "automation_enabled": False,
        "targets": {
            "room_perimeter": {
                "label": "Strip Light",
                "device_ref": "local-device-ref-123",
                "expected_model": "H612D",
                "control_route": "govee_platform_dynamic_scene",
                "capabilities": ["scene", "off"],
            }
        },
        "looks": {
            "room_safe_default": {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": "Release-A",
                "fallback": "room_blackout",
                "safety_class": "safe",
                "brightness": 60,
                "allow_strobe": False,
            },
            "room_blackout": {
                "target": "room_perimeter",
                "action": "off",
                "fallback": "",
                "safety_class": "blackout",
                "brightness": 0,
                "allow_strobe": False,
            },
        },
        "banks": {
            "default": {
                "ambient": ["room_safe_default"],
                "groove": ["room_safe_default"],
                "buildup": ["room_safe_default"],
                "pre_drop": [],
                "drop": [],
                "post_drop": [],
                "breakdown": ["room_safe_default"],
                "utility": ["room_safe_default", "room_blackout"],
            }
        },
        "safe_default": "room_safe_default",
        "blackout": "room_blackout",
        "rate_limits": {
            "queue_maxsize": 8,
            "scene_retrigger_cooldown_s": 4.0,
            "high_impact_cooldown_s": 12.0,
            "request_timeout_s": 2.0,
            "worker_shutdown_timeout_s": 1.0,
        },
        "safety": {
            "max_brightness": 100,
            "allow_strobe": True,
            "max_strobe_duration_ms": 750,
            "high_impact_cooldown_s": 12.0,
            "drop_flash_duration_ms": 750,
            "emergency_blackout_always_available": True,
            "scripted_mode_automation": False,
        },
    }


def _valid_color_engine_block() -> dict:
    """A valid color_engine block matching §7 defaults."""
    return {
        "enabled": True,
        "scale_stops": {
            "green":   [0, 255, 0],
            "cyan":    [0, 255, 255],
            "blue":    [0, 0, 255],
            "purple":  [160, 0, 255],
            "magenta": [255, 0, 160],
            "red":     [255, 0, 0],
        },
        "palette_dwell_tracks": 4,
        "snap_eligible_drop_indices": [2, 3],
        "big_shift_chance": 0.25,
        "big_shift_weight_bias": 1.0,
        "drama_by_role": True,
        "role_spread": {"drop": 0.35, "groove": 0.12, "ambient": 0.10},
        "step_within_section": {"drop": False, "post_drop": True, "groove": True},
        "fade_beats_by_role": {
            "drop": 0, "buildup": 0, "breakdown": 4,
            "post_drop": 2, "groove": 2, "ambient": 4,
        },
        "exempt_looks": ["rt_drop_white_aggressive"],
        "diy_color_tags": {"groove_diy_red_chasing": "red"},
        "set_seed_mode": "random",
        "palettes": {
            "blue_cyan": {
                "range": ["cyan", "blue"],
                "white": 0.0,
                "spread": 0.10,
                "weight": 14,
                "dwell": 4,
                "focus_modes": {"mono": 3, "lean": 3, "full": 2},
            },
            "red": {
                "range": ["red", "red"],
                "white": 0.0,
                "spread": 0.10,
                "weight": 9,
            },
        },
    }


def _valid_v2_block() -> dict:
    zones = {
        "GLACIER": {
            "base_ramp": [[10, 40, 120], [0, 120, 255], [0, 220, 255]],
            "accent_ramp": [[120, 240, 255], [210, 250, 255]],
        },
        "DEEP_POOL": {
            "base_ramp": [[5, 10, 60], [0, 40, 140], [0, 90, 140]],
            "accent_ramp": [[40, 0, 160], [0, 60, 200]],
        },
        "TWILIGHT": {
            "base_ramp": [[40, 0, 90], [90, 0, 180], [140, 0, 220]],
            "accent_ramp": [[180, 0, 220], [230, 0, 180]],
        },
        "ION": {
            "base_ramp": [[0, 60, 255], [0, 180, 255], [60, 255, 220]],
            "accent_ramp": [[140, 255, 60], [240, 255, 220]],
        },
        "VOLT": {
            "base_ramp": [[180, 0, 120], [255, 0, 160], [200, 0, 255]],
            "accent_ramp": [[0, 220, 255], [120, 255, 240]],
        },
        "EMBERCORE": {
            "base_ramp": [[120, 0, 10], [200, 0, 30], [120, 0, 120]],
            "accent_ramp": [[255, 30, 30], [255, 200, 180]],
        },
        "NEUTRAL": {
            "base_ramp": [[0, 80, 200], [0, 160, 230], [0, 220, 255]],
            "accent_ramp": [[0, 255, 255], [140, 220, 255]],
        },
    }
    return {
        "enabled": True,
        "zones": zones,
        "bass_norm": [0.15, 0.90],
        "store_path": "local/state/led_identity_v2.json",
    }


# ---------------------------------------------------------------------------
# Tests for ColorEngineConfig / Palette dataclasses
# ---------------------------------------------------------------------------

class TestPaletteDataclass(unittest.TestCase):
    def test_palette_defaults(self) -> None:
        p = Palette()
        self.assertEqual(p.range, ("blue", "cyan"))
        self.assertEqual(p.spread, 0.10)
        self.assertEqual(p.weight, 1.0)
        self.assertIsNone(p.dwell)
        self.assertEqual(p.focus_modes, {})

    def test_palette_with_values(self) -> None:
        p = Palette(
            range=("cyan", "blue"),
            spread=0.15,
            weight=3.0,
            dwell=5,
            focus_modes={"mono": 2.0, "full": 1.0},
        )
        self.assertEqual(p.range, ("cyan", "blue"))
        self.assertEqual(p.dwell, 5)
        self.assertEqual(p.focus_modes["mono"], 2.0)

    def test_palette_is_frozen(self) -> None:
        p = Palette()
        with self.assertRaises(Exception):
            p.spread = 0.5  # type: ignore[misc]


class TestColorEngineConfigDataclass(unittest.TestCase):
    def test_defaults(self) -> None:
        cfg = ColorEngineConfig()
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.palette_dwell_tracks, 4)
        self.assertEqual(cfg.snap_eligible_drop_indices, (2, 3))
        self.assertAlmostEqual(cfg.big_shift_chance, 0.25)
        self.assertTrue(cfg.drama_by_role)
        self.assertEqual(cfg.set_seed_mode, "random")
        self.assertEqual(cfg.slot_mono_chance_by_look, {})
        self.assertEqual(cfg.locked_palette_by_look, {})
        self.assertEqual(cfg.exempt_looks, ())
        self.assertEqual(cfg.diy_color_tags, {})
        self.assertEqual(cfg.palettes, {})
        # Scale stops includes the 6 canonical stops
        self.assertIn("green", cfg.scale_stops)
        self.assertIn("magenta", cfg.scale_stops)
        self.assertEqual(cfg.scale_stops["magenta"], (255, 0, 160))

    def test_is_frozen(self) -> None:
        cfg = ColorEngineConfig()
        with self.assertRaises(Exception):
            cfg.enabled = False  # type: ignore[misc]

    def test_identity_v2_defaults(self) -> None:
        cfg = IdentityV2Config()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.bass_norm, (0.5856, 0.9688))
        self.assertEqual(cfg.store_path, "local/state/led_identity_v2.json")

    def test_zone_ramp_is_frozen(self) -> None:
        ramp = ZoneRampConfig(
            base_ramp=((1, 2, 3), (4, 5, 6), (7, 8, 9)),
            accent_ramp=((10, 11, 12), (13, 14, 15)),
        )
        with self.assertRaises(Exception):
            ramp.hue_span = 0.1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests for LEDLook.color_source / diy_color fields
# ---------------------------------------------------------------------------

class TestLEDLookColorFields(unittest.TestCase):
    def test_ledlook_defaults(self) -> None:
        """LEDLook carries color_source='engine' and diy_color='' by default."""
        look = LEDLook(name="test", target="t", action="off")
        self.assertEqual(look.color_source, "engine")
        self.assertEqual(look.diy_color, "")
        self.assertEqual(look.motion_style, "")
        self.assertEqual(look.travel, "")

    def test_ledlook_explicit_values(self) -> None:
        look = LEDLook(
            name="test",
            target="t",
            action="off",
            color_source="baked",
            diy_color="red",
            motion_style="sharp",
            travel="wide",
        )
        self.assertEqual(look.color_source, "baked")
        self.assertEqual(look.diy_color, "red")
        self.assertEqual(look.motion_style, "sharp")
        self.assertEqual(look.travel, "wide")

    def test_color_source_carried_through_config(self) -> None:
        """color_source and diy_color flow from JSON look → LEDLook via _build_config."""
        cfg_data = _base_config()
        cfg_data["looks"]["room_safe_default"]["color_source"] = "baked"
        cfg_data["looks"]["room_safe_default"]["diy_color"] = "blue"
        cfg_data["looks"]["room_safe_default"]["motion_style"] = "flowing"
        cfg_data["looks"]["room_safe_default"]["travel"] = "calm"
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        look = result.config.looks["room_safe_default"]
        self.assertEqual(look.color_source, "baked")
        self.assertEqual(look.diy_color, "blue")
        self.assertEqual(look.motion_style, "flowing")
        self.assertEqual(look.travel, "calm")

    def test_color_source_default_when_omitted(self) -> None:
        """Omitting color_source in JSON yields default 'engine'."""
        result = load_led_look_director_config_from_dict(_base_config())
        self.assertTrue(result.available, msg=result.errors)
        look = result.config.looks["room_safe_default"]
        self.assertEqual(look.color_source, "engine")
        self.assertEqual(look.diy_color, "")


# ---------------------------------------------------------------------------
# Tests for color_engine absent / valid / invalid → always LED available
# ---------------------------------------------------------------------------

class TestColorEngineAbsent(unittest.TestCase):
    def test_absent_block_yields_none(self) -> None:
        """No color_engine key → LEDConfig.color_engine is None, config available."""
        result = load_led_look_director_config_from_dict(_base_config())
        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNone(result.config.color_engine)

    def test_regression_existing_config_unchanged(self) -> None:
        """An existing valid config without color_engine loads with available=True, color_engine=None."""
        result = load_led_look_director_config_from_dict(_base_config())
        self.assertTrue(result.available)
        self.assertEqual(result.reason, "ok")
        self.assertIsNone(result.config.color_engine)


class TestColorEngineValid(unittest.TestCase):
    def test_valid_block_parses(self) -> None:
        """A well-formed color_engine block parses into LEDConfig.color_engine."""
        cfg_data = _base_config()
        cfg_data["color_engine"] = _valid_color_engine_block()
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNotNone(result.config.color_engine)

    def test_enabled_field_carried(self) -> None:
        """color_engine.enabled is carried through."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["enabled"] = False
        cfg_data["color_engine"] = block
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNotNone(result.config.color_engine)
        self.assertFalse(result.config.color_engine.enabled)

    def test_palettes_carried(self) -> None:
        cfg_data = _base_config()
        cfg_data["color_engine"] = _valid_color_engine_block()
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        ce = result.config.color_engine
        self.assertIn("blue_cyan", ce.palettes)
        self.assertIn("red", ce.palettes)
        p = ce.palettes["blue_cyan"]
        self.assertIsInstance(p, Palette)
        self.assertEqual(p.range, ("cyan", "blue"))
        self.assertAlmostEqual(p.weight, 14.0)
        self.assertEqual(p.focus_modes["mono"], 3.0)

    def test_palette_without_dwell_is_none(self) -> None:
        """Palette without an explicit 'dwell' key has dwell=None."""
        cfg_data = _base_config()
        cfg_data["color_engine"] = _valid_color_engine_block()
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        ce = result.config.color_engine
        self.assertIsNone(ce.palettes["red"].dwell)

    def test_snap_indices_tuple(self) -> None:
        cfg_data = _base_config()
        cfg_data["color_engine"] = _valid_color_engine_block()
        result = load_led_look_director_config_from_dict(cfg_data)
        ce = result.config.color_engine
        self.assertEqual(ce.snap_eligible_drop_indices, (2, 3))

    def test_exempt_looks_tuple(self) -> None:
        cfg_data = _base_config()
        cfg_data["color_engine"] = _valid_color_engine_block()
        result = load_led_look_director_config_from_dict(cfg_data)
        ce = result.config.color_engine
        self.assertIn("rt_drop_white_aggressive", ce.exempt_looks)

    def test_slot_fill_strategy_defaults_empty(self) -> None:
        # M2.5 §2.D: absent strategy keys default to empty dicts.
        cfg_data = _base_config()
        cfg_data["color_engine"] = _valid_color_engine_block()
        result = load_led_look_director_config_from_dict(cfg_data)
        ce = result.config.color_engine
        self.assertEqual(ce.slot_fill_strategy_by_look, {})
        self.assertEqual(ce.slot_fill_strategy_by_role, {})
        self.assertEqual(ce.slot_mono_chance_by_look, {})

    def test_slot_fill_strategy_valid_values_carried(self) -> None:
        # M2.5 Patch S: validation accepts the two original strategies plus
        # random_with_mono_chance.
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_fill_strategy_by_look"] = {
            "rt_groove_chase": "random_with_replacement",
            "rt_other": "gradient_even",
            "rt_solid": "random_with_mono_chance",
        }
        block["slot_fill_strategy_by_role"] = {
            "groove": "random_with_replacement",
            "ambient": "gradient_even",
            "post_drop": "random_with_mono_chance",
        }
        cfg_data["color_engine"] = block
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        ce = result.config.color_engine
        self.assertEqual(
            ce.slot_fill_strategy_by_look["rt_groove_chase"], "random_with_replacement"
        )
        self.assertEqual(ce.slot_fill_strategy_by_look["rt_other"], "gradient_even")
        self.assertEqual(ce.slot_fill_strategy_by_look["rt_solid"], "random_with_mono_chance")
        self.assertEqual(ce.slot_fill_strategy_by_role["groove"], "random_with_replacement")
        self.assertEqual(ce.slot_fill_strategy_by_role["ambient"], "gradient_even")
        self.assertEqual(ce.slot_fill_strategy_by_role["post_drop"], "random_with_mono_chance")

    def test_slot_mono_chance_valid_values_carried(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_mono_chance_by_look"] = {
            "rt_groove_chase": 0.0,
            "rt_x": 1.0,
            "rt_y": 0.15,
        }
        cfg_data["color_engine"] = block
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=result.errors)
        ce = result.config.color_engine
        self.assertEqual(ce.slot_mono_chance_by_look["rt_groove_chase"], 0.0)
        self.assertEqual(ce.slot_mono_chance_by_look["rt_x"], 1.0)
        self.assertAlmostEqual(ce.slot_mono_chance_by_look["rt_y"], 0.15)

    def test_locked_palette_valid_values_carried(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["locked_palette_by_look"] = {"rt_groove_chase": "red"}
        cfg_data["color_engine"] = block

        result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNotNone(result.config.color_engine)
        self.assertEqual(result.config.color_engine.locked_palette_by_look, {"rt_groove_chase": "red"})

    def test_palette_control_bindings_carried(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["white_sand"] = {
            "type": "fixed_rgb",
            "weight": 0,
            "rgb": [255, 235, 200],
        }
        block["palettes"]["rainbow"] = {"type": "rainbow", "weight": 0}
        block["palette_control"] = {
            "enabled": True,
            "device": "Stream Deck",
            "channel": 2,
            "palette_notes": {"blue_cyan": 51, "red": 52},
            "white_sand_note": 56,
            "lock_note": 57,
            "led_mute_note": 58,
            "laser_mute_note": 59,
            "laser_solo_note": 60,
            "rainbow_note": 61,
        }
        cfg_data["color_engine"] = block

        result = load_led_look_director_config_from_dict(cfg_data)

        ce = result.config.color_engine
        self.assertIsNotNone(ce)
        self.assertEqual(
            [(b.target_kind, b.data_byte, b.target_name, b.interaction) for b in ce.palette_control_bindings],
            [
                ("palette_pad", 51, "blue_cyan", "press"),
                ("palette_pad", 52, "red", "press"),
                ("palette_pad", 56, "white_sand", "press"),
                ("palette_lock_pad", 57, None, "press"),
                ("led_mute_pad", 58, None, "press"),
                ("rainbow_pad", 61, None, "press"),
                ("laser_solo_pad", 60, None, "press"),
                ("blackout_mask", 59, None, "toggle"),
            ],
        )

    def test_palette_control_omits_lock_binding_when_lock_note_absent(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["white_sand"] = {
            "type": "fixed_rgb",
            "weight": 0,
            "rgb": [255, 235, 200],
        }
        block["palettes"]["rainbow"] = {"type": "rainbow", "weight": 0}
        block["palette_control"] = {
            "enabled": True,
            "device": "Stream Deck",
            "channel": 2,
            "palette_notes": {"blue_cyan": 51, "red": 52},
            "white_sand_note": 56,
            "long_press_s": 0.5,
            "led_mute_note": 58,
            "laser_mute_note": 59,
            "laser_solo_note": 60,
            "rainbow_note": 61,
        }
        cfg_data["color_engine"] = block

        result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        ce = result.config.color_engine
        self.assertIsNotNone(ce)
        self.assertNotIn("palette_lock_pad", [b.target_kind for b in ce.palette_control_bindings])

    def test_palette_control_long_press_threshold_validated(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palette_control"] = {
            "enabled": True,
            "device": "Stream Deck",
            "channel": 2,
            "palette_notes": {"blue_cyan": 51, "red": 52},
            "white_sand_note": 56,
            "long_press_s": 2.5,
            "led_mute_note": 58,
            "laser_mute_note": 59,
            "laser_solo_note": 60,
            "rainbow_note": 61,
        }
        cfg_data["color_engine"] = block

        with self.assertLogs("rb_ss_bridge_v2.led_config", level="WARNING") as logs:
            result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNone(result.config.color_engine)
        self.assertIn(
            "color_engine.palette_control.long_press_s must be a number in 0.15..2.0",
            "\n".join(logs.output),
        )

    def test_identity_v2_valid_block_parses_and_adds_bindings(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["white_sand"] = {
            "type": "fixed_rgb",
            "weight": 0,
            "rgb": [255, 235, 200],
        }
        block["palettes"]["rainbow"] = {"type": "rainbow", "weight": 0}
        block["v2"] = _valid_v2_block()
        block["palette_control"] = {
            "enabled": True,
            "device": "Stream Deck",
            "channel": 2,
            "palette_notes": {"blue_cyan": 51, "red": 52},
            "white_sand_note": 56,
            "lock_note": 57,
            "led_mute_note": 58,
            "laser_mute_note": 59,
            "laser_solo_note": 60,
            "rainbow_note": 61,
            "zone_notes": {
                "GLACIER": 62,
                "DEEP_POOL": 63,
                "TWILIGHT": 64,
                "ION": 65,
                "VOLT": 66,
                "EMBERCORE": 67,
            },
            "manual_notes": {"red": 68, "green": 69, "blue": 70},
            "max_energy_note": 71,
        }
        cfg_data["color_engine"] = block

        result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        ce = result.config.color_engine
        self.assertIsNotNone(ce)
        self.assertIsNotNone(ce.v2)
        self.assertTrue(ce.v2.enabled)
        self.assertEqual(ce.v2.bass_norm, (0.15, 0.90))
        self.assertEqual(ce.v2.zones["GLACIER"].base_ramp[1], (0, 120, 255))
        kinds = [(b.target_kind, b.data_byte, b.target_name) for b in ce.palette_control_bindings]
        self.assertIn(("zone_pad", 62, "GLACIER"), kinds)
        self.assertIn(("manual_pad", 68, "red"), kinds)
        self.assertIn(("max_energy_pad", 71, None), kinds)

    def test_identity_v2_error_keeps_v1_engine(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["white_sand"] = {
            "type": "fixed_rgb",
            "weight": 0,
            "rgb": [255, 235, 200],
        }
        block["v2"] = _valid_v2_block()
        block["v2"]["zones"]["GLACIER"]["base_ramp"][0] = [0, 0, 0]
        cfg_data["color_engine"] = block

        with self.assertLogs("rb_ss_bridge_v2.led_config", level="WARNING") as logs:
            result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNotNone(result.config.color_engine)
        self.assertIsNone(result.config.color_engine.v2)
        self.assertIn("color_engine.v2 config invalid", "\n".join(logs.output))

    def test_identity_v2_note_collision_keeps_v1_engine(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["white_sand"] = {
            "type": "fixed_rgb",
            "weight": 0,
            "rgb": [255, 235, 200],
        }
        block["palettes"]["rainbow"] = {"type": "rainbow", "weight": 0}
        block["v2"] = _valid_v2_block()
        block["palette_control"] = {
            "enabled": True,
            "device": "Stream Deck",
            "channel": 2,
            "palette_notes": {"blue_cyan": 51, "red": 52},
            "white_sand_note": 56,
            "led_mute_note": 58,
            "laser_mute_note": 59,
            "laser_solo_note": 60,
            "rainbow_note": 61,
            "zone_notes": {"GLACIER": 51},
        }
        cfg_data["color_engine"] = block

        result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNotNone(result.config.color_engine)
        self.assertIsNone(result.config.color_engine.v2)

    def test_identity_v2_disabled_block_does_not_require_zones(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["v2"] = {"enabled": False}
        cfg_data["color_engine"] = block

        result = load_led_look_director_config_from_dict(cfg_data)

        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNotNone(result.config.color_engine.v2)
        self.assertFalse(result.config.color_engine.v2.enabled)


# ---------------------------------------------------------------------------
# Tests for invalid color_engine blocks → engine=None, LED still available
# ---------------------------------------------------------------------------

class TestColorEngineInvalidDoesNotDisableLED(unittest.TestCase):
    """Critical invariant (§15.5/C5): bad color_engine block → engine off, LED stays up."""

    def _assert_engine_off_led_up(self, cfg_data: dict, msg: str = "") -> None:
        result = load_led_look_director_config_from_dict(cfg_data)
        self.assertTrue(result.available, msg=f"LED must stay available. {msg} errors={result.errors}")
        self.assertEqual(result.reason, "ok", msg=msg)
        self.assertIsNone(result.config.color_engine, msg=f"engine must be None. {msg}")

    def test_all_zero_palette_weights_engine_off_led_up(self) -> None:
        """All-zero palette weights → div-by-zero → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        for pal in block["palettes"].values():
            pal["weight"] = 0
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "all-zero weights")

    def test_empty_palettes_dict_engine_off_led_up(self) -> None:
        """Empty palettes dict → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"] = {}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "empty palettes")

    def test_invalid_slot_fill_strategy_by_look_engine_off(self) -> None:
        """Unknown slot_fill_strategy_by_look value → engine None, LED available (Rule 3)."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_fill_strategy_by_look"] = {"rt_groove_chase": "mono"}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "invalid by_look strategy 'mono'")

    def test_invalid_slot_fill_strategy_by_role_engine_off(self) -> None:
        """Unknown slot_fill_strategy_by_role value → engine None, LED available (Rule 3)."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_fill_strategy_by_role"] = {"groove": "weighted_random"}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "invalid by_role strategy 'weighted_random'")

    def test_slot_mono_chance_negative_engine_off(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_mono_chance_by_look"] = {"rt_groove_chase": -0.01}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "slot_mono_chance < 0")

    def test_slot_mono_chance_above_one_engine_off(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_mono_chance_by_look"] = {"rt_groove_chase": 1.01}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "slot_mono_chance > 1")

    def test_slot_mono_chance_non_number_engine_off(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_mono_chance_by_look"] = {"rt_groove_chase": "high"}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "slot_mono_chance non-number")

    def test_slot_mono_chance_bool_engine_off(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_mono_chance_by_look"] = {"rt_groove_chase": True}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "slot_mono_chance bool")

    def test_slot_mono_chance_not_object_engine_off(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["slot_mono_chance_by_look"] = ["rt_groove_chase"]
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "slot_mono_chance not object")

    def test_locked_palette_unknown_palette_engine_off_names_look(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["locked_palette_by_look"] = {"rt_groove_chase": "missing"}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "rt_groove_chase")

    def test_locked_palette_not_object_engine_off(self) -> None:
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["locked_palette_by_look"] = ["rt_groove_chase"]
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "locked_palette not object")

    def test_range_endpoint_not_in_scale_stops(self) -> None:
        """range endpoint referencing a non-existent scale_stop → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        # Use "orange" which is not in scale_stops
        block["palettes"]["blue_cyan"]["range"] = ["cyan", "orange"]
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "unknown range endpoint")

    def test_enabled_wrong_type_engine_off_led_up(self) -> None:
        """enabled: 'yes' (string) → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["enabled"] = "yes"
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "enabled is string")

    def test_palette_weight_negative_engine_off_led_up(self) -> None:
        """Negative palette weight → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["blue_cyan"]["weight"] = -1
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "negative weight")

    def test_big_shift_chance_out_of_range(self) -> None:
        """big_shift_chance > 1 → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["big_shift_chance"] = 2.0
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "big_shift_chance > 1")

    def test_palette_dwell_tracks_zero(self) -> None:
        """palette_dwell_tracks = 0 → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palette_dwell_tracks"] = 0
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "palette_dwell_tracks = 0")

    def test_snap_index_zero_invalid(self) -> None:
        """snap_eligible_drop_indices containing 0 → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["snap_eligible_drop_indices"] = [0, 2]
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "snap index 0")

    def test_focus_modes_all_zero_weights(self) -> None:
        """focus_modes with all-zero weights → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"]["blue_cyan"]["focus_modes"] = {"mono": 0, "lean": 0, "full": 0}
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "focus_modes all-zero")

    def test_non_dict_color_engine_block(self) -> None:
        """color_engine is a string, not a dict → engine None, LED available."""
        cfg_data = _base_config()
        cfg_data["color_engine"] = "oops"
        self._assert_engine_off_led_up(cfg_data, "color_engine not a dict")

    def test_palettes_not_dict(self) -> None:
        """palettes is a list → engine None, LED available."""
        cfg_data = _base_config()
        block = _valid_color_engine_block()
        block["palettes"] = ["blue_cyan"]
        cfg_data["color_engine"] = block
        self._assert_engine_off_led_up(cfg_data, "palettes not a dict")


# ---------------------------------------------------------------------------
# Regression: example config without color_engine still loads identically
# ---------------------------------------------------------------------------

class TestExampleConfigRegression(unittest.TestCase):
    def test_example_loads_with_empty_slot_mono_chance(self) -> None:
        result = load_led_look_director_config(_EXAMPLE_PATH)
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.errors, ())
        self.assertIsNotNone(result.config.color_engine)
        self.assertEqual(result.config.color_engine.slot_mono_chance_by_look, {})
        self.assertEqual(result.config.color_engine.locked_palette_by_look, {})

    def test_example_loads_with_color_engine_none(self) -> None:
        """The existing example config (no color_engine key) loads as before:
        available=True, color_engine=None.
        """
        import json
        data = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))
        # Strip color_engine block to simulate legacy config
        data.pop("color_engine", None)
        result = load_led_look_director_config_from_dict(data)
        self.assertTrue(result.available, msg=result.errors)
        self.assertIsNone(result.config.color_engine)


if __name__ == "__main__":
    unittest.main()
