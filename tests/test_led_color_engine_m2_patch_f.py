"""Tests for M2.5 Patch F + AWR-265 FINAL: default-bank generics, clone-free."""
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
# Former color-suffix clones — must stay absent after AWR-265 FINAL.
_RETIRED_COLOR_SUFFIX_LOOKS = frozenset(
    {
        "rt_twinkle_blue",
        "rt_groove_chase_blue",
        "rt_groove_chase_cyan",
        "rt_groove_chase_red",
        "rt_groove_chase_green",
        "rt_groove_chase_cyan_white",
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
        "rt_post_drop_chase_blue",
        "rt_post_drop_chase_cyan",
        "rt_post_drop_chase_red",
        "rt_post_drop_chase_green",
        "rt_post_drop_chase_cyan_white",
        "rt_post_drop_center_comet_blue_cyan",
    }
)
_EXPECTED_DEFAULT_GENERICS = {
    "groove": "rt_groove_chase",
    # 2026-07-17 dedup: the generic post-drop chase retired; the center comet
    # is the surviving engine-fed post-drop generic.
    "post_drop": "rt_post_drop_center_comet",
    "ambient": "rt_twinkle",
}
_GENERIC_ENGINE_LOOKS = (
    "rt_groove_chase",
    "rt_drop_center_burst",
    "rt_post_drop_center_comet",
    "rt_twinkle",
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

    def test_default_bank_contains_no_retired_color_suffix_looks(self) -> None:
        result = _load()
        default_names = _bank_names(result.config.banks["default"])
        self.assertEqual(default_names & _RETIRED_COLOR_SUFFIX_LOOKS, set())
        self.assertIn("rt_drop_strobe", result.config.banks["default"].drop)

    def test_legacy_color_suffix_bank_is_gone(self) -> None:
        # AWR-265 FINAL: storage bank deleted with the clones.
        result = _load()
        self.assertNotIn("legacy_color_suffix", result.config.banks)

    def test_retired_clones_are_absent_from_looks(self) -> None:
        result = _load()
        for look_name in sorted(_RETIRED_COLOR_SUFFIX_LOOKS):
            self.assertNotIn(look_name, result.config.looks)

    def test_default_bank_look_names_resolve(self) -> None:
        result = _load()
        defined = set(result.config.looks)
        self.assertTrue(_bank_names(result.config.banks["default"]) <= defined)

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

    def test_generics_use_engine_and_retired_exempts_cleared(self) -> None:
        result = _load()
        exempt = set(result.config.color_engine.exempt_looks)
        for look_name in _RETIRED_COLOR_SUFFIX_LOOKS:
            self.assertNotIn(look_name, exempt)
        for look_name in _GENERIC_ENGINE_LOOKS:
            self.assertNotIn(look_name, exempt)
            self.assertEqual(result.config.looks[look_name].color_source, "engine")

    def test_drop_pairs_resolve_and_generic_pair_exists(self) -> None:
        result = _load()
        # 2026-07-17 dedup: the generic chase pair retired with its two looks.
        self.assertIsNone(result.config.drop_pairs.get("rt_drop_chase"))
        self.assertIsNone(result.config.drop_pairs.get("rt_post_drop_remnant_chase"))
        pair = result.config.drop_pairs.get("rt_drop_center_burst")
        self.assertIsNotNone(pair)
        self.assertEqual(pair.post_drop, "rt_post_drop_center_comet")
        for drop_name, drop_pair in result.config.drop_pairs.items():
            self.assertIn(drop_name, result.config.looks)
            self.assertIn(drop_pair.post_drop, result.config.looks)

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
