"""Tests for tools/apply_firework_redesign.py (AWR-187 staging script).

The script flips exactly ONE look (rt_drop_firework_explosion) to the
redesigned drop_firework_explosion_2 strobe and must touch nothing else,
refuse to write under a strobe-forbidding safety block, back up once, write
atomically, and be idempotent.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import apply_firework_redesign as m  # noqa: E402

SCRIPT = Path(m.__file__).resolve()


def _fixture():
    """Live-shaped config: the pre-apply v1 firework look + bystander keys."""
    return {
        "enabled": True,
        "safety": {"max_brightness": 100, "allow_strobe": True},
        "looks": {
            "rt_drop_firework_explosion": {
                "target": "room_perimeter",
                "action": "realtime",
                "scene_ref": "drop_firework_explosion",
                "fallback": "rt_blackout",
                "safety_class": "drop",
                "brightness": 100,
                "allow_strobe": False,
                "backend": "realtime_razer",
                "color_source": "baked",
                "params": {
                    "color_a": [255, 240, 220],
                    "spark_a": [255, 170, 60],
                    "spark_b": [255, 240, 220],
                    "surge_beats": 0.5,
                    "bg_hold": 0.7,
                    "sparkle_density": 0.35,
                    "sparkle_size": 1.0,
                    "sparkle_life_s": 0.35,
                },
            },
            "rt_blackout": {"scene_ref": "blackout", "allow_strobe": False},
        },
        "drop_pairs": {"rt_drop_firework_explosion": {"post_drop": "rt_post_drop_firework_remnants"}},
        "unrelated_key": {"keep": "me"},
    }


class ApplyFireworkRedesignTests(unittest.TestCase):
    def test_flips_only_the_firework_look(self):
        data = _fixture()
        untouched = copy.deepcopy(data)
        self.assertTrue(m.apply(data))
        look = data["looks"]["rt_drop_firework_explosion"]
        for key, value in m.TARGET_FIELDS.items():
            self.assertEqual(look[key], value, key)
        # Non-target fields on the look survive.
        self.assertEqual(look["target"], "room_perimeter")
        self.assertEqual(look["fallback"], "rt_blackout")
        self.assertEqual(look["safety_class"], "drop")
        # Nothing else in the config moves.
        for key in ("enabled", "safety", "drop_pairs", "unrelated_key"):
            self.assertEqual(data[key], untouched[key], key)
        self.assertEqual(data["looks"]["rt_blackout"], untouched["looks"]["rt_blackout"])

    def test_idempotent_second_apply_is_a_noop(self):
        data = _fixture()
        self.assertTrue(m.apply(data))
        self.assertFalse(m.apply(data))

    def test_cli_refuses_without_safety_allow_strobe(self):
        data = _fixture()
        data["safety"]["allow_strobe"] = False
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "led_look_director.json"
            cfg.write_text(json.dumps(data), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(cfg)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 3, proc.stderr)
            # Nothing written: file unchanged, no backup.
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8")), data)
            self.assertFalse((Path(td) / "led_look_director.json.pre_awr187.bak").exists())

    def test_cli_applies_backs_up_once_and_reruns_clean(self):
        data = _fixture()
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "led_look_director.json"
            cfg.write_text(json.dumps(data), encoding="utf-8")
            backup = Path(td) / "led_look_director.json.pre_awr187.bak"

            proc = subprocess.run([sys.executable, str(SCRIPT), "--config", str(cfg)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            written = json.loads(cfg.read_text(encoding="utf-8"))
            look = written["looks"]["rt_drop_firework_explosion"]
            self.assertEqual(look["scene_ref"], "drop_firework_explosion_2")
            self.assertTrue(look["allow_strobe"])
            # Backup holds the PRE-apply content.
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), data)

            # Second run: no-op, backup untouched.
            proc2 = subprocess.run([sys.executable, str(SCRIPT), "--config", str(cfg)],
                                   capture_output=True, text=True)
            self.assertEqual(proc2.returncode, 0, proc2.stderr)
            self.assertIn("already applied", proc2.stdout)
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), data)


if __name__ == "__main__":
    unittest.main()
