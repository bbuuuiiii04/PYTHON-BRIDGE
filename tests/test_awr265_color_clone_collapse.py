"""AWR-265 FINAL — color-level A/B gate for promoted residual colorways.

Step 0's clone-inventory mapping tests are retired: the collapse executed
(Steps 1–3 + FINAL). Living gate: base cue classes under blue_cyan resolve the
exact curated pairs that the deleted residual clones used to bake.

Config-only mechanism (no led_color_engine.py change): scale_stops order puts
``ice`` between ``cyan`` and ``blue``, so blue_cyan's cyan→blue gradient keeps
its existing multi ends (cyan, blue) while slots also contain exact ice and
reserved white — cyan+white, blue+ice, and blue+cyan are all reachable.
"""
from __future__ import annotations

import runpy
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402


def _load_tool():
    path = Path(__file__).resolve().parents[1] / "tools" / "awr265_color_clone_collapse.py"
    return types.SimpleNamespace(**runpy.run_path(str(path), run_name="awr265_tool"))


_TOOL = _load_tool()
_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE = _ROOT / "config" / "led_look_director.example.json"

# Retired residual clones → curated pairs that must surface under blue_cyan.
_PROMOTED_PAIRS: tuple[tuple[str, str, tuple[int, int, int], tuple[int, int, int]], ...] = (
    ("rt_drop_chase_cyan_white", "rt_drop_chase", (0, 255, 255), (255, 255, 255)),
    ("rt_groove_chase_cyan_white", "rt_groove_chase", (0, 255, 255), (255, 255, 255)),
    ("rt_post_drop_chase_cyan_white", "rt_post_drop_chase", (0, 255, 255), (255, 255, 255)),
    ("rt_drop_center_burst_blue_cyan", "rt_drop_center_burst", (0, 0, 255), (0, 200, 255)),
    ("rt_post_drop_center_comet_blue_cyan", "rt_post_drop_center_comet", (0, 0, 255), (0, 200, 255)),
    ("rt_twinkle_blue", "rt_twinkle", (0, 0, 255), (0, 255, 255)),
)

_BASE_LOOKS = frozenset(base for _, base, _, _ in _PROMOTED_PAIRS)


def _pair_reachable(multi, slots, color_a, color_b) -> bool:
    if multi is not None and None not in multi:
        if frozenset(multi) == frozenset((color_a, color_b)):
            return True
    if slots and color_a in slots and color_b in slots:
        return True
    return False


class Awr265FinalColorABTests(unittest.TestCase):
    """Living gate replacing Step 0 inventory + byte-exact frame A/B."""

    @classmethod
    def setUpClass(cls) -> None:
        loaded = load_led_look_director_config(str(_EXAMPLE))
        assert loaded.available and loaded.config is not None, loaded.errors
        cls.cfg = loaded.config
        cls.ce = loaded.config.color_engine
        assert cls.ce is not None

    def test_residual_clones_are_gone(self) -> None:
        looks = self.cfg.looks
        for retired, *_ in _PROMOTED_PAIRS:
            self.assertNotIn(retired, looks)
        self.assertNotIn("legacy_color_suffix", self.cfg.banks)

    def test_base_cue_classes_remain_engine_fed(self) -> None:
        checked = 0
        for base in _BASE_LOOKS:
            look = self.cfg.looks.get(base)
            if look is None:
                # rt_drop_chase / rt_post_drop_chase were retired by the
                # 2026-07-17 cue dedup; their clones stay retired either way
                # (test_residual_clones_are_gone).
                continue
            checked += 1
            self.assertEqual(look.color_source, "engine", base)
        self.assertGreater(checked, 0, "no AWR-265 base looks survive")

    def test_blue_cyan_keeps_existing_cyan_blue_multi(self) -> None:
        # Taste guard: promote pairs ADD to blue_cyan; do not take over multi ends.
        multi = _TOOL._resolve_v1_multi(self.ce, "blue_cyan")
        self.assertEqual(multi, ((0, 255, 255), (0, 0, 255)))

    def test_promoted_pairs_resolve_under_blue_cyan(self) -> None:
        multi = _TOOL._resolve_v1_multi(self.ce, "blue_cyan")
        slots = _TOOL._resolve_v1_slots(self.ce, "blue_cyan")
        self.assertIsNotNone(slots)
        for retired, base, color_a, color_b in _PROMOTED_PAIRS:
            with self.subTest(retired=retired, base=base):
                self.assertTrue(
                    _pair_reachable(multi, slots, color_a, color_b),
                    msg=(
                        f"{retired} pair {(color_a, color_b)} not reachable under "
                        f"blue_cyan (multi={multi}, slots={slots})"
                    ),
                )

    def test_ice_stop_sits_between_cyan_and_blue(self) -> None:
        stops = list(self.ce.scale_stops)
        self.assertLess(stops.index("cyan"), stops.index("ice"))
        self.assertLess(stops.index("ice"), stops.index("blue"))

    def test_collapse_tool_is_honest_on_clone_free_config(self) -> None:
        # Runnable after FINAL: empty collapse inventory, no crash.
        _, rows = _TOOL.build_mapping_table(_EXAMPLE)
        collapse = [r for r in rows if r.spec.scope == "collapse"]
        self.assertEqual(collapse, [])
        diy = [r for r in rows if r.spec.scope == "out_of_scope"]
        self.assertEqual(len(diy), 4)


if __name__ == "__main__":
    unittest.main()
