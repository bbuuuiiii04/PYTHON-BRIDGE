"""Tests for M2.5 Patch F: legacy color-suffix bank cleanup."""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import SLOT_EFFECTS, _EFFECTS  # noqa: E402
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402


_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_PATH = _ROOT / "config/led_look_director.example.json"
_ROLES = (
    "ambient",
    "groove",
    "buildup",
    "pre_drop",
    "drop",
    "post_drop",
    "breakdown",
    "utility",
)
_LEGACY_COLOR_SUFFIX_BY_ROLE = {
    "ambient": ("rt_twinkle_blue",),
    "groove": (
        "rt_groove_chase_blue",
        "rt_groove_chase_cyan",
        "rt_groove_chase_red",
        "rt_groove_chase_green",
        "rt_groove_chase_cyan_white",
    ),
    "buildup": (),
    "pre_drop": (),
    "drop": (
        "rt_drop_chase_blue",
        "rt_drop_chase_cyan",
        "rt_drop_chase_red",
        "rt_drop_chase_green",
        "rt_drop_chase_cyan_white",
        "rt_drop_center_burst_blue_cyan",
        "rt_drop_strobe_blue",
        "rt_drop_strobe_cyan",
        "rt_drop_strobe_green",
        "rt_drop_strobe_red",
        "rt_drop_strobe_red_white",
        "rt_drop_strobe_blue_cyan",
        "rt_drop_strobe_cyan_white",
    ),
    "post_drop": (
        "rt_post_drop_chase_blue",
        "rt_post_drop_chase_cyan",
        "rt_post_drop_chase_red",
        "rt_post_drop_chase_green",
        "rt_post_drop_chase_cyan_white",
        "rt_post_drop_center_comet_blue_cyan",
    ),
    "breakdown": (),
    "utility": (),
}
_MOVED_LEGACY_LOOKS = {
    look_name
    for role_looks in _LEGACY_COLOR_SUFFIX_BY_ROLE.values()
    for look_name in role_looks
}
_EXPECTED_DEFAULT_GENERICS = {
    "groove": "rt_groove_chase",
    # AWR-156 bank recast (f): rt_drop_chase moved drop -> post_drop, so the
    # "drop" role no longer has a generic chase representative.
    "post_drop": "rt_post_drop_chase",
    "ambient": "rt_twinkle",
}
_GENERIC_ENGINE_LOOKS = (
    "rt_groove_chase",
    # AWR-156 T6.4: renamed rt_drop_chase -> rt_post_drop_remnant_chase
    # (LOOK-name rename only; scene_ref stays rt_drop_chase).
    "rt_post_drop_remnant_chase",
    "rt_post_drop_chase",
    "rt_drop_center_burst",
    "rt_post_drop_center_comet",
    "rt_twinkle",
)
_LEGACY_EXEMPT_LOOKS = (
    "rt_twinkle_blue",
    "rt_drop_center_burst_blue_cyan",
    "rt_post_drop_center_comet_blue_cyan",
)


def _load():
    result = load_led_look_director_config(str(_EXAMPLE_PATH))
    assert result.config is not None
    return result


def _bank_names(bank) -> set[str]:
    names: set[str] = set()
    for role in _ROLES:
        names.update(getattr(bank, role))
    return names


class PatchFBankCleanupTests(unittest.TestCase):
    def test_example_config_validates(self) -> None:
        result = _load()
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.reason, "ok")
        self.assertEqual(tuple(result.errors), ())

    def test_default_bank_contains_no_moved_legacy_color_suffix_looks(self) -> None:
        # AWR-265 Step 2: all color-suffix clones (including the former Part C
        # gentle-drop quartet and the seven drop strobes) live only in
        # legacy_color_suffix. Default drop rotates the palette-fed bases.
        result = _load()
        default_names = _bank_names(result.config.banks["default"])
        self.assertEqual(default_names & _MOVED_LEGACY_LOOKS, set())
        self.assertIn("rt_drop_chase", result.config.banks["default"].drop)
        self.assertIn("rt_drop_strobe", result.config.banks["default"].drop)

    def test_legacy_color_suffix_bank_contains_exactly_moved_looks(self) -> None:
        result = _load()
        legacy = result.config.banks.get("legacy_color_suffix")
        self.assertIsNotNone(legacy)
        for role in _ROLES:
            self.assertEqual(
                getattr(legacy, role),
                _LEGACY_COLOR_SUFFIX_BY_ROLE[role],
                role,
            )
        self.assertEqual(_bank_names(legacy), _MOVED_LEGACY_LOOKS)

    def test_default_and_legacy_bank_look_names_resolve(self) -> None:
        result = _load()
        defined = set(result.config.looks)
        self.assertTrue(_bank_names(result.config.banks["default"]) <= defined)
        self.assertTrue(_bank_names(result.config.banks["legacy_color_suffix"]) <= defined)

    def test_default_realtime_scene_refs_are_registered(self) -> None:
        result = _load()
        registered = set(_EFFECTS) | set(SLOT_EFFECTS)
        for look_name in sorted(_bank_names(result.config.banks["default"])):
            look = result.config.looks[look_name]
            if look.action == "realtime" or look.backend == "realtime_razer":
                self.assertIn(look.scene_ref, registered, look_name)

    def test_generic_slot_looks_are_in_expected_default_roles(self) -> None:
        result = _load()
        default = result.config.banks["default"]
        for role, look_name in _EXPECTED_DEFAULT_GENERICS.items():
            self.assertIn(look_name, getattr(default, role), role)
        self.assertIn("rt_post_drop_center_comet", default.post_drop)

    def test_legacy_exempt_looks_remain_exempt_and_generics_use_engine(self) -> None:
        result = _load()
        exempt = set(result.config.color_engine.exempt_looks)
        for look_name in _LEGACY_EXEMPT_LOOKS:
            self.assertIn(look_name, exempt)
        for look_name in _GENERIC_ENGINE_LOOKS:
            self.assertNotIn(look_name, exempt)
            self.assertEqual(result.config.looks[look_name].color_source, "engine")

    def test_drop_pairs_resolve_and_generic_chase_pair_exists(self) -> None:
        # AWR-156 bank recast (f), T6.4 amended: rt_drop_chase moved to the
        # post_drop bank AND renamed to rt_post_drop_remnant_chase, so it no
        # longer fires a drop_pairs entry -- rt_drop_center_burst is the
        # remaining generic (non-legacy-suffixed) drop pair.
        result = _load()
        self.assertIsNone(result.config.drop_pairs.get("rt_drop_chase"))
        self.assertIsNone(result.config.drop_pairs.get("rt_post_drop_remnant_chase"))
        pair = result.config.drop_pairs.get("rt_drop_center_burst")
        self.assertIsNotNone(pair)
        self.assertEqual(pair.post_drop, "rt_post_drop_center_comet")
        for drop_name, drop_pair in result.config.drop_pairs.items():
            self.assertIn(drop_name, result.config.looks)
            self.assertIn(drop_pair.post_drop, result.config.looks)

    def test_legacy_look_definitions_still_resolve(self) -> None:
        result = _load()
        for look_name in sorted(_MOVED_LEGACY_LOOKS):
            self.assertIn(look_name, result.config.looks)

    def test_no_static_slot_colors_params_in_config(self) -> None:
        result = _load()
        for look_name, look in result.config.looks.items():
            self.assertNotIn("slot_colors", look.params, look_name)

    def test_solid_reachable_through_default_generic_slot_look(self) -> None:
        result = _load()
        self.assertIn("rt_groove_chase", result.config.banks["default"].groove)
        color_engine_config = replace(
            result.config.color_engine,
            set_seed_mode="fixed:12345",
            slot_fill_strategy_by_look={
                **result.config.color_engine.slot_fill_strategy_by_look,
                "rt_groove_chase": "random_with_mono_chance",
            },
            slot_mono_chance_by_look={"rt_groove_chase": 1.0},
        )
        engine = LedColorEngine(color_engine_config, set_seed=12345)
        engine.begin_dispatch(
            active_deck=1,
            load_gen=1,
            content_id="patch-f-solid",
            filepath="/tracks/patch-f-solid.wav",
            role="groove",
            section_id="groove-solid",
            cycle=0,
        )
        slots = engine.resolve_slot_colors(
            role="groove",
            section_id="groove-solid",
            cycle=0,
            look_name="rt_groove_chase",
            color_source="engine",
        )["slot_colors"]
        self.assertEqual(len(slots), 6)
        self.assertEqual(len(set(slots[:5])), 1)
        self.assertEqual(slots[5], (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
