"""Tripwires for the staged AWR-197 speed/size law.

The staging tool (tools/apply_speed_size_law.py) is a HISTORICAL one-shot: it
ran at the 2026-07-10 gate and its SPEED_PARAMS still names looks that the
2026-07-17 cue dedup retired, so it can no longer run against a current config
and is never invoked again (spec Absolute Rule). What still matters is that the
example config CARRIES the law for every look that survived, so that is what
these tripwires pin — no tool execution.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.apply_speed_size_law import DEAD_PAIRS, SPEED_PARAMS

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


class SpeedSizeLawTests(unittest.TestCase):
    def test_example_config_carries_the_speed_law(self) -> None:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        checked = 0
        for name, (scene_ref, wanted) in SPEED_PARAMS.items():
            look = data["looks"].get(name)
            if look is None:
                # Retired by the 2026-07-17 cue dedup; the law cannot apply to
                # a look that no longer exists.
                continue
            checked += 1
            self.assertEqual(look["scene_ref"], scene_ref, name)
            for key, value in wanted.items():
                self.assertEqual(look["params"][key], value, f"{name}.{key}")
        self.assertGreater(checked, 0, "no speed-law looks survive — law unpinned")

    def test_example_config_has_no_dead_pairs(self) -> None:
        pairs = json.loads(EXAMPLE.read_text(encoding="utf-8"))["drop_pairs"]
        for name in DEAD_PAIRS:
            self.assertNotIn(name, pairs)

    def test_retired_speed_law_looks_are_really_gone(self) -> None:
        # The other half of the law's truth: the dedup's kill list must not
        # reappear in the example under a speed-law param.
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for name in ("rt_post_drop_chase", "rt_post_drop_nebula",
                     "rt_post_drop_remnant_chase", "rt_post_drop_remnant_nebula"):
            self.assertNotIn(name, data["looks"], name)


if __name__ == "__main__":
    unittest.main()
