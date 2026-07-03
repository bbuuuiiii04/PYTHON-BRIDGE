"""
Tests for deprecated Laser Director personality timing keys.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import rb_ss_bridge_v2.laser_config as laser_config  # noqa: E402
from rb_ss_bridge_v2.laser_config import load_laser_director_config  # noqa: E402
from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402

_DEPRECATED_KEYS = (
    "buildup_approach_beats",
    "buildup_hold_beats",
    "pre_drop_lookahead_beats",
    "buildup_max_drop_distance_beats",
    "pre_drop_scene",
)


def _write_config(data: dict) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, f)
    f.close()
    return f.name


def _config_with_personality(overrides: dict[str, object] | None = None) -> dict:
    personality = {
        "safe_scene": "safe_static",
        "default_scene": "safe_static",
        "phrase_scene": "safe_static",
        "buildup_scene": "safe_static",
        "drop_scene": "safe_static",
        "post_drop_scene": "safe_static",
        "breakdown_scene": "safe_static",
        "transition_scene": "safe_static",
    }
    if overrides:
        personality.update(overrides)
    return {
        "enabled": False,
        "dry_run": True,
        "smart_drop_mode": "legacy_rearm",
        "midi_output_port": "IAC Driver Bus 1",
        "startup_scene": "safe_static",
        "stop_scene": "safe_static",
        "stale_scene": "safe_static",
        "emergency_scene": "emergency_blackout",
        "fallback_scene": "safe_static",
        "default_personality": "house",
        "scenes": {
            "safe_static": {
                "scene_type": "static",
                "safety_class": "safe",
                "midi": {"kind": "note_pulse", "channel": 1, "note": 36},
            },
            "emergency_blackout": {
                "scene_type": "utility",
                "safety_class": "blackout",
                "midi": {"kind": "note_pulse", "channel": 1, "note": 44},
            },
        },
        "personalities": {"house": personality},
    }


class LaserConfigDeprecationTests(unittest.TestCase):
    def test_all_deprecated_keys_warn_once_and_load(self) -> None:
        cfg = _config_with_personality(
            {
                "buildup_approach_beats": -1,
                "buildup_hold_beats": False,
                "pre_drop_lookahead_beats": "old",
                "buildup_max_drop_distance_beats": 99,
                "pre_drop_scene": "old_scene",
            }
        )
        with mock.patch.object(laser_config.log, "warning") as warning:
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        warning.assert_called_once()
        self.assertIn("[LASER-CONFIG] deprecated keys ignored", warning.call_args.args[0])
        named_keys = warning.call_args.args[1]
        for key in _DEPRECATED_KEYS:
            self.assertIn(key, named_keys)

    def test_subset_deprecated_keys_warn_once_for_present_key_only(self) -> None:
        cfg = _config_with_personality({"buildup_approach_beats": "old"})
        with mock.patch.object(laser_config.log, "warning") as warning:
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        warning.assert_called_once()
        named_keys = warning.call_args.args[1]
        self.assertEqual(named_keys, "buildup_approach_beats")

    def test_no_deprecated_keys_emit_no_warning(self) -> None:
        cfg = _config_with_personality()
        with mock.patch.object(laser_config.log, "warning") as warning:
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        warning.assert_not_called()

    def test_loaded_personality_and_director_do_not_have_deprecated_attrs(self) -> None:
        cfg = _config_with_personality({key: 1 for key in _DEPRECATED_KEYS})
        with mock.patch.object(laser_config.log, "warning"):
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        personality = result.config.personalities["house"]
        director = LaserDirector(enabled=True)
        for key in _DEPRECATED_KEYS:
            self.assertFalse(hasattr(personality, key), msg=key)
            self.assertFalse(hasattr(director, f"_{key}"), msg=key)


if __name__ == "__main__":
    unittest.main()
