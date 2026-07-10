"""Tripwires for the staged AWR-197 speed/size law."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.apply_speed_size_law import DEAD_PAIRS, SPEED_PARAMS, apply


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


class SpeedSizeLawTests(unittest.TestCase):
    def _tmp_config(self) -> dict:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / EXAMPLE.name
        shutil.copy2(EXAMPLE, path)
        return json.loads(path.read_text(encoding="utf-8"))

    def test_example_config_carries_the_speed_law(self) -> None:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for name, (scene_ref, wanted) in SPEED_PARAMS.items():
            self.assertIn(name, data["looks"])
            look = data["looks"][name]
            self.assertEqual(look["scene_ref"], scene_ref)
            for key, value in wanted.items():
                self.assertEqual(look["params"][key], value)

    def test_example_config_has_no_dead_pairs(self) -> None:
        pairs = json.loads(EXAMPLE.read_text(encoding="utf-8"))["drop_pairs"]
        for name in DEAD_PAIRS:
            self.assertNotIn(name, pairs)

    def test_apply_is_idempotent(self) -> None:
        data = self._tmp_config()
        self.assertFalse(apply(data))
        name, (_, wanted) = next(iter(SPEED_PARAMS.items()))
        key, value = next(iter(wanted.items()))
        del data["looks"][name]["params"][key]
        self.assertTrue(apply(data))
        self.assertEqual(data["looks"][name]["params"][key], value)

    def test_apply_never_clobbers_existing(self) -> None:
        data = self._tmp_config()
        name, (_, wanted) = next(iter(SPEED_PARAMS.items()))
        key, value = next(iter(wanted.items()))
        data["looks"][name]["params"][key] = value + 1.0
        apply(data)
        self.assertEqual(data["looks"][name]["params"][key], value + 1.0)

    def test_apply_aborts_on_missing_look(self) -> None:
        data = self._tmp_config()
        del data["looks"][next(iter(SPEED_PARAMS))]
        before = copy.deepcopy(data)
        with self.assertRaises(ValueError):
            apply(data)
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
