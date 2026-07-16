"""AWR-265 Step 0 — color-clone collapse mapping + frame A/B regression harness.

Foundation for the config-only migration: every collapse-scope clone is classified,
and mono chase/strobe colorways that can be reproduced via palette VALUE edits must
pass base+literal frame identity on a seeded grid.
"""
from __future__ import annotations

import runpy
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _load_tool():
    path = Path(__file__).resolve().parents[1] / "tools" / "awr265_color_clone_collapse.py"
    return types.SimpleNamespace(**runpy.run_path(str(path), run_name="awr265_tool"))


_TOOL = _load_tool()
_EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"

# Cue classes Step 1 must materialize as base looks (final list from Step 0).
EXPECTED_BASE_LOOKS = frozenset(
    {
        "rt_drop_strobe",
        "rt_drop_chase",
        "rt_groove_chase",
        "rt_post_drop_chase",
        "rt_drop_center_burst",
        "rt_post_drop_center_comet",
        "rt_twinkle",
    }
)

# Mono chase suffixes that Step 0 proved byte-identical to the slot base under
# literal slot injection (CONFIG_EDIT path for palette values).
FRAME_IDENTICAL_MONO_CHASES = frozenset(
    {
        "rt_groove_chase_blue",
        "rt_groove_chase_cyan",
        "rt_groove_chase_red",
        "rt_groove_chase_green",
        "rt_drop_chase_blue",
        "rt_drop_chase_cyan",
        "rt_drop_chase_red",
        "rt_drop_chase_green",
        "rt_post_drop_chase_blue",
        "rt_post_drop_chase_cyan",
        "rt_post_drop_chase_red",
        "rt_post_drop_chase_green",
    }
)

# Residuals that must stay until engine work or live-taste deletion — never
# delete in Step 3 without a new A/B green.
KNOWN_IMPOSSIBLE_OR_RESIDUAL = frozenset(
    {
        "rt_groove_chase_cyan_white",
        "rt_drop_chase_cyan_white",
        "rt_post_drop_chase_cyan_white",
        "rt_drop_center_burst_blue_cyan",
        "rt_post_drop_center_comet_blue_cyan",
        "rt_twinkle_blue",
    }
)


class Awr265Step0MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded, cls.rows = _TOOL.build_mapping_table(_EXAMPLE)
        cls.by_name = {row.spec.look_name: row for row in cls.rows}

    def test_inventory_is_29_names(self) -> None:
        self.assertEqual(len(self.rows), 29)

    def test_collapse_scope_has_expected_base_classes(self) -> None:
        bases = {row.spec.base_look for row in self.rows if row.spec.scope == "collapse"}
        self.assertEqual(bases, EXPECTED_BASE_LOOKS)

    def test_diy_cloud_names_are_out_of_scope(self) -> None:
        diy = [row for row in self.rows if row.spec.cue_class == "diy_cloud"]
        self.assertEqual(len(diy), 4)
        for row in diy:
            self.assertEqual(row.classification, "OUT_OF_SCOPE")

    def test_mono_chases_are_config_edit_with_zero_frame_mismatch(self) -> None:
        for name in FRAME_IDENTICAL_MONO_CHASES:
            row = self.by_name[name]
            self.assertEqual(row.clone_vs_base_mismatches, 0, name)
            self.assertIn(row.classification, {"CONFIG_EDIT", "EXACT_TODAY"}, name)
            self.assertTrue(row.edit_match, msg=f"{name} edit_multi={row.edit_multi}")

    def test_known_residuals_are_impossible(self) -> None:
        for name in KNOWN_IMPOSSIBLE_OR_RESIDUAL:
            row = self.by_name[name]
            self.assertEqual(row.classification, "IMPOSSIBLE", name)
            self.assertGreater(row.clone_vs_base_mismatches, 0, name)
            self.assertTrue(row.residual, name)

    def test_strobe_literals_extract_from_config_params(self) -> None:
        blue = self.by_name["rt_drop_strobe_blue"]
        self.assertEqual(blue.spec.color_a, (0, 0, 255))
        self.assertIsNone(blue.spec.color_b)
        duo = self.by_name["rt_drop_strobe_blue_cyan"]
        self.assertEqual(duo.spec.color_a, (0, 0, 255))
        self.assertEqual(duo.spec.color_b, (0, 135, 255))
        self.assertTrue(duo.edit_match)
        self.assertEqual(duo.classification, "CONFIG_EDIT")
        cyan_white = self.by_name["rt_drop_strobe_cyan_white"]
        self.assertEqual(cyan_white.spec.color_b, (100, 105, 255))
        self.assertTrue(cyan_white.edit_match)
        self.assertEqual(cyan_white.classification, "CONFIG_EDIT")
        self.assertEqual(cyan_white.clone_vs_base_mismatches, 0)

    def test_base_plus_literal_injection_is_byte_identical(self) -> None:
        """Motion-identical-by-construction gate for every collapse-scope cue."""
        for row in self.rows:
            if row.spec.scope != "collapse":
                continue
            mism, checked = _TOOL.frame_ab_base_vs_literals(
                base_scene=row.spec.base_scene,
                inject=row.spec.inject,
                literals=row.spec,
                beats=_TOOL.GRID_BEATS[:80],
            )
            self.assertEqual(mism, 0, row.spec.look_name)
            self.assertEqual(checked, 80, row.spec.look_name)

    def test_mapping_table_emits_all_verdicts(self) -> None:
        text = _TOOL.format_table(self.rows)
        self.assertIn("CONFIG_EDIT", text)
        self.assertIn("IMPOSSIBLE", text)
        self.assertIn("OUT_OF_SCOPE", text)
        self.assertIn("rt_drop_chase_blue", text)


if __name__ == "__main__":
    unittest.main()
