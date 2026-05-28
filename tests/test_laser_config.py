"""
Tests for laser_config.py — JSON config loader and validator.

Covers:
  - Missing config file → not_configured.
  - Invalid JSON → invalid_config.
  - Valid config (disabled, dry_run) → ok / available=True.
  - Disabled config is safe (available=True even when enabled=False).
  - dry_run defaults to True when key is absent.
  - RBSS_LASER_CONFIG env var path override.
  - Invalid scene reference in lifecycle fields.
  - Invalid MIDI note (> 127 or < 0).
  - Invalid MIDI channel (0 or > 16).
  - Invalid duration_ms below minimum (< 10).
  - Invalid duration_ms above maximum (> 250).
  - midi_output_port required when enabled=True and dry_run=False.
  - midi_output_port not required when dry_run=True.
  - Scene names are arbitrary (no fixed names required).
  - Personality references unknown scene → invalid_config.
  - default_personality missing when personalities present → invalid_config.
  - load_laser_director_config never raises on any bad input.
  - example file loads and is valid.
  - LaserConfig fields are correct types.
  - LaserConfigResult is frozen.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_config import (  # noqa: E402
    LaserConfig,
    LaserConfigResult,
    _infer_behavior,
    load_laser_director_config,
    load_laser_director_config_from_dict,
)
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
)

# ---------------------------------------------------------------------------
# Minimal valid config fixture (disabled, dry_run, no personalities)
# ---------------------------------------------------------------------------

_MINIMAL_SCENES = {
    "safe_static": {
        "scene_type": "static",
        "safety_class": "safe",
        "midi": {"kind": "note_pulse", "channel": 1, "note": 36, "velocity": 127, "duration_ms": 80},
    },
    "emergency_blackout": {
        "scene_type": "utility",
        "safety_class": "blackout",
        "midi": {"kind": "note_pulse", "channel": 1, "note": 44, "velocity": 127, "duration_ms": 80},
    },
}

_MINIMAL_CONFIG: dict = {
    "enabled": False,
    "dry_run": True,
    "midi_output_port": "IAC Driver Bus 1",
    "startup_scene":   "safe_static",
    "stop_scene":      "safe_static",
    "stale_scene":     "safe_static",
    "emergency_scene": "emergency_blackout",
    "fallback_scene":  "safe_static",
    "scenes": _MINIMAL_SCENES,
}


def _write_config(data: dict) -> str:
    """Write data as JSON to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, f)
    f.close()
    return f.name


def _with_scene(overrides: dict, scene_name: str = "safe_static") -> dict:
    """Return a copy of _MINIMAL_CONFIG with the named scene overridden."""
    cfg = copy.deepcopy(_MINIMAL_CONFIG)
    cfg["scenes"][scene_name] = overrides
    return cfg


class DictLoaderParityTests(unittest.TestCase):
    def test_dict_loader_matches_path_loader_for_fixture_configs(self) -> None:
        invalid_missing_scene = copy.deepcopy(_MINIMAL_CONFIG)
        invalid_missing_scene["startup_scene"] = "missing_scene"
        fixtures = [
            ("minimal", copy.deepcopy(_MINIMAL_CONFIG)),
            (
                "with_manual_blackout",
                {
                    **copy.deepcopy(_MINIMAL_CONFIG),
                    "manual_commands": {
                        "blackout_on": {"kind": "note_on", "channel": 1, "note": 1},
                        "blackout_off": {"kind": "note_off", "channel": 1, "note": 1},
                    },
                },
            ),
            ("invalid_missing_scene", invalid_missing_scene),
            (
                "example",
                json.loads(
                    (Path(__file__).resolve().parents[1] / "config" / "laser_director.example.json").read_text(
                        encoding="utf-8"
                    )
                ),
            ),
        ]
        for name, config in fixtures:
            with self.subTest(name=name):
                path_result = load_laser_director_config(_write_config(config))
                dict_result = load_laser_director_config_from_dict(copy.deepcopy(config))

                self.assertEqual(dict_result, path_result)


# ---------------------------------------------------------------------------
# Missing config
# ---------------------------------------------------------------------------

class MissingConfigTests(unittest.TestCase):
    def test_missing_file_returns_not_configured(self) -> None:
        result = load_laser_director_config("/nonexistent/path/laser_director.json")
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "not_configured")
        self.assertIsNone(result.config)
        self.assertEqual(result.errors, ())

    def test_missing_file_errors_are_empty(self) -> None:
        result = load_laser_director_config("/nonexistent/path.json")
        self.assertEqual(result.errors, ())


# ---------------------------------------------------------------------------
# Invalid JSON
# ---------------------------------------------------------------------------

class InvalidJsonTests(unittest.TestCase):
    def _write_raw(self, text: str) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        f.write(text)
        f.close()
        return f.name

    def test_malformed_json_returns_invalid_config(self) -> None:
        path = self._write_raw("{not valid json")
        result = load_laser_director_config(path)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")
        self.assertTrue(len(result.errors) > 0)

    def test_json_non_object_root_returns_invalid_config(self) -> None:
        path = self._write_raw("[1, 2, 3]")
        result = load_laser_director_config(path)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")

    def test_empty_file_returns_invalid_config(self) -> None:
        path = self._write_raw("")
        result = load_laser_director_config(path)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")


# ---------------------------------------------------------------------------
# Valid config
# ---------------------------------------------------------------------------

class ValidConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._path = _write_config(_MINIMAL_CONFIG)
        self._result = load_laser_director_config(self._path)

    def test_valid_config_available_true(self) -> None:
        self.assertTrue(self._result.available)

    def test_valid_config_reason_ok(self) -> None:
        self.assertEqual(self._result.reason, "ok")

    def test_valid_config_no_errors(self) -> None:
        self.assertEqual(self._result.errors, ())

    def test_valid_config_is_laser_config(self) -> None:
        self.assertIsInstance(self._result.config, LaserConfig)

    def test_valid_config_enabled_false(self) -> None:
        self.assertFalse(self._result.config.enabled)

    def test_valid_config_dry_run_true(self) -> None:
        self.assertTrue(self._result.config.dry_run)

    def test_valid_config_scenes_populated(self) -> None:
        self.assertIn("safe_static", self._result.config.scenes)
        self.assertIn("emergency_blackout", self._result.config.scenes)

    def test_valid_config_scene_is_laser_scene(self) -> None:
        scene = self._result.config.scenes["safe_static"]
        self.assertIsInstance(scene, LaserScene)

    def test_valid_config_scene_midi_is_laser_midi_message(self) -> None:
        midi = self._result.config.scenes["safe_static"].midi
        self.assertIsInstance(midi, LaserMidiMessage)

    def test_valid_config_lifecycle_scenes_set(self) -> None:
        c = self._result.config
        self.assertEqual(c.startup_scene, "safe_static")
        self.assertEqual(c.stop_scene, "safe_static")
        self.assertEqual(c.stale_scene, "safe_static")
        self.assertEqual(c.emergency_scene, "emergency_blackout")
        self.assertEqual(c.fallback_scene, "safe_static")


# ---------------------------------------------------------------------------
# Disabled config is safe
# ---------------------------------------------------------------------------

class DisabledConfigTests(unittest.TestCase):
    def test_disabled_config_available_true(self) -> None:
        """enabled=False is valid; available=True means the config was parsed OK."""
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["enabled"] = False
        path = _write_config(cfg)
        result = load_laser_director_config(path)
        self.assertTrue(result.available)
        self.assertEqual(result.reason, "ok")
        self.assertFalse(result.config.enabled)

    def test_disabled_config_with_dry_run_false_ok(self) -> None:
        """disabled + dry_run=False is fine; no port required when enabled=False."""
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["enabled"] = False
        cfg["dry_run"] = False
        cfg["midi_output_port"] = ""
        path = _write_config(cfg)
        result = load_laser_director_config(path)
        self.assertTrue(result.available)
        self.assertEqual(result.reason, "ok")


# ---------------------------------------------------------------------------
# dry_run defaults to True
# ---------------------------------------------------------------------------

class DryRunDefaultTests(unittest.TestCase):
    def test_dry_run_absent_defaults_to_true(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        del cfg["dry_run"]
        path = _write_config(cfg)
        result = load_laser_director_config(path)
        self.assertTrue(result.available)
        self.assertTrue(result.config.dry_run)

    def test_dry_run_explicit_false_stored(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["dry_run"] = False
        path = _write_config(cfg)
        result = load_laser_director_config(path)
        self.assertTrue(result.available)
        self.assertFalse(result.config.dry_run)


class SmartDropModeTests(unittest.TestCase):
    def test_smart_drop_mode_defaults_to_blackout_mask(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg.pop("smart_drop_mode", None)
        result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.smart_drop_mode, "blackout_mask")

    def test_smart_drop_mode_legacy_rearm_is_valid(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "legacy_rearm"
        result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.smart_drop_mode, "legacy_rearm")

    def test_invalid_smart_drop_mode_fails_validation(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "invalid_mode"
        result = load_laser_director_config(_write_config(cfg))
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")
        self.assertTrue(any("smart_drop_mode" in e for e in result.errors))


class ManualBlackoutPairValidationTests(unittest.TestCase):
    def test_blackout_mode_requires_blackout_command_pair(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg["manual_commands"] = {
            "blackout_on": {
                "kind": "note_on",
                "behavior": "note_on",
                "channel": 1,
                "note": 90,
                "velocity": 127,
            },
        }
        result = load_laser_director_config(_write_config(cfg))
        self.assertFalse(result.available)
        self.assertTrue(any("manual_commands.blackout_on" in e for e in result.errors))

    def test_blackout_mode_requires_blackout_off_when_blackout_on_missing(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg["manual_commands"] = {
            "blackout_off": {
                "kind": "note_off",
                "behavior": "note_off",
                "channel": 1,
                "note": 90,
                "velocity": 0,
            },
        }
        result = load_laser_director_config(_write_config(cfg))
        self.assertFalse(result.available)
        self.assertTrue(any("manual_commands.blackout_on" in e for e in result.errors))

    def test_blackout_mode_allows_blackout_command_pair(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg["manual_commands"] = {
            "blackout_on": {
                "kind": "note_on",
                "behavior": "note_on",
                "channel": 1,
                "note": 91,
                "velocity": 127,
            },
            "blackout_off": {
                "kind": "note_off",
                "behavior": "note_off",
                "channel": 1,
                "note": 91,
                "velocity": 0,
            },
        }
        result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)

    def test_blackout_mode_rejects_blackout_on_pulse_behavior(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg["manual_commands"] = {
            "blackout_on": {
                "kind": "note_pulse",
                "channel": 1,
                "note": 91,
                "velocity": 127,
                "duration_ms": 80,
            },
            "blackout_off": {
                "kind": "note_off",
                "behavior": "note_off",
                "channel": 1,
                "note": 91,
                "velocity": 0,
            },
        }
        result = load_laser_director_config(_write_config(cfg))
        self.assertFalse(result.available)
        self.assertTrue(any("manual_commands.blackout_on" in e for e in result.errors))
        self.assertTrue(any("behavior='note_on'" in e for e in result.errors))

    def test_blackout_mode_rejects_blackout_off_pulse_behavior(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg["manual_commands"] = {
            "blackout_on": {
                "kind": "note_on",
                "behavior": "note_on",
                "channel": 1,
                "note": 91,
                "velocity": 127,
            },
            "blackout_off": {
                "kind": "note_pulse",
                "channel": 1,
                "note": 91,
                "velocity": 127,
                "duration_ms": 80,
            },
        }
        result = load_laser_director_config(_write_config(cfg))
        self.assertFalse(result.available)
        self.assertTrue(any("manual_commands.blackout_off" in e for e in result.errors))
        self.assertTrue(any("behavior='note_off'" in e for e in result.errors))

    def test_legacy_mode_does_not_require_manual_blackout_commands(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "legacy_rearm"
        cfg["manual_commands"] = {
            "blackout_on": {
                "kind": "note_on",
                "behavior": "note_on",
                "channel": 1,
                "note": 91,
                "velocity": 127,
            },
        }
        result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)


class ManualBlackoutWarningTests(unittest.TestCase):
    def test_blackout_mode_without_manual_commands_logs_warning(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg.pop("manual_commands", None)
        with self.assertLogs("laser_config", level="WARNING") as captured:
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)
        output = "\n".join(captured.output)
        self.assertIn("smart_drop_mode='blackout_mask'", output)
        self.assertIn("will not be masked", output)

    def test_blackout_mode_with_manual_pair_logs_no_missing_warning(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "blackout_mask"
        cfg["manual_commands"] = {
            "blackout_on": {
                "kind": "note_on",
                "behavior": "note_on",
                "channel": 1,
                "note": 90,
                "velocity": 127,
            },
            "blackout_off": {
                "kind": "note_off",
                "behavior": "note_off",
                "channel": 1,
                "note": 90,
                "velocity": 0,
            },
        }
        with self.assertNoLogs("laser_config", level="WARNING"):
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)

    def test_legacy_mode_without_manual_commands_logs_no_blackout_warning(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["smart_drop_mode"] = "legacy_rearm"
        cfg.pop("manual_commands", None)
        with self.assertNoLogs("laser_config", level="WARNING"):
            result = load_laser_director_config(_write_config(cfg))
        self.assertTrue(result.available, msg=result.errors)


class MidiBehaviorInferenceTests(unittest.TestCase):
    def test_explicit_behavior_wins(self) -> None:
        self.assertEqual(_infer_behavior("note_on", "hold_ms"), "hold_ms")

    def test_note_pulse_defaults_to_pulse(self) -> None:
        self.assertEqual(_infer_behavior("note_pulse", None), "pulse")

    def test_note_on_defaults_to_note_on(self) -> None:
        self.assertEqual(_infer_behavior("note_on", ""), "note_on")

    def test_note_off_defaults_to_note_off(self) -> None:
        self.assertEqual(_infer_behavior("note_off", None), "note_off")

    def test_unknown_kind_defaults_to_pulse(self) -> None:
        self.assertEqual(_infer_behavior("unknown_kind", None), "pulse")


# ---------------------------------------------------------------------------
# RBSS_LASER_CONFIG env var override
# ---------------------------------------------------------------------------

class EnvPathOverrideTests(unittest.TestCase):
    def test_env_var_points_to_valid_config(self) -> None:
        path = _write_config(_MINIMAL_CONFIG)
        old = os.environ.pop("RBSS_LASER_CONFIG", None)
        try:
            os.environ["RBSS_LASER_CONFIG"] = path
            result = load_laser_director_config()
            self.assertTrue(result.available)
            self.assertEqual(result.reason, "ok")
        finally:
            if old is None:
                os.environ.pop("RBSS_LASER_CONFIG", None)
            else:
                os.environ["RBSS_LASER_CONFIG"] = old

    def test_env_var_points_to_missing_file(self) -> None:
        old = os.environ.pop("RBSS_LASER_CONFIG", None)
        try:
            os.environ["RBSS_LASER_CONFIG"] = "/nonexistent/env/path.json"
            result = load_laser_director_config()
            self.assertEqual(result.reason, "not_configured")
        finally:
            if old is None:
                os.environ.pop("RBSS_LASER_CONFIG", None)
            else:
                os.environ["RBSS_LASER_CONFIG"] = old

    def test_explicit_path_beats_env_var(self) -> None:
        """Explicit path argument takes priority over env var."""
        import copy
        cfg_good = copy.deepcopy(_MINIMAL_CONFIG)
        path_good = _write_config(cfg_good)
        old = os.environ.pop("RBSS_LASER_CONFIG", None)
        try:
            os.environ["RBSS_LASER_CONFIG"] = "/nonexistent/env.json"
            result = load_laser_director_config(path_good)
            self.assertTrue(result.available)
        finally:
            if old is None:
                os.environ.pop("RBSS_LASER_CONFIG", None)
            else:
                os.environ["RBSS_LASER_CONFIG"] = old


# ---------------------------------------------------------------------------
# Invalid scene reference
# ---------------------------------------------------------------------------

class InvalidSceneReferenceTests(unittest.TestCase):
    def _bad_lifecycle(self, field: str) -> LaserConfigResult:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg[field] = "nonexistent_scene"
        return load_laser_director_config(_write_config(cfg))

    def test_bad_startup_scene(self) -> None:
        r = self._bad_lifecycle("startup_scene")
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("startup_scene" in e for e in r.errors))

    def test_bad_stop_scene(self) -> None:
        r = self._bad_lifecycle("stop_scene")
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("stop_scene" in e for e in r.errors))

    def test_bad_stale_scene(self) -> None:
        r = self._bad_lifecycle("stale_scene")
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_bad_emergency_scene(self) -> None:
        r = self._bad_lifecycle("emergency_scene")
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_bad_fallback_scene(self) -> None:
        r = self._bad_lifecycle("fallback_scene")
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_missing_scenes_key(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        del cfg["scenes"]
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_empty_scenes_dict(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["scenes"] = {}
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")


# ---------------------------------------------------------------------------
# Invalid MIDI note
# ---------------------------------------------------------------------------

class InvalidMidiNoteTests(unittest.TestCase):
    def _result_with_note(self, note) -> LaserConfigResult:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["scenes"]["safe_static"]["midi"]["note"] = note
        return load_laser_director_config(_write_config(cfg))

    def test_note_128_invalid(self) -> None:
        r = self._result_with_note(128)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("note" in e for e in r.errors))

    def test_note_minus_1_invalid(self) -> None:
        r = self._result_with_note(-1)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_note_200_invalid(self) -> None:
        r = self._result_with_note(200)
        self.assertFalse(r.available)

    def test_note_0_valid(self) -> None:
        r = self._result_with_note(0)
        self.assertTrue(r.available)

    def test_note_127_valid(self) -> None:
        r = self._result_with_note(127)
        self.assertTrue(r.available)


# ---------------------------------------------------------------------------
# Invalid MIDI channel
# ---------------------------------------------------------------------------

class InvalidMidiChannelTests(unittest.TestCase):
    def _result_with_channel(self, channel) -> LaserConfigResult:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["scenes"]["safe_static"]["midi"]["channel"] = channel
        return load_laser_director_config(_write_config(cfg))

    def test_channel_0_invalid(self) -> None:
        r = self._result_with_channel(0)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("channel" in e for e in r.errors))

    def test_channel_17_invalid(self) -> None:
        r = self._result_with_channel(17)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_channel_1_valid(self) -> None:
        r = self._result_with_channel(1)
        self.assertTrue(r.available)

    def test_channel_16_valid(self) -> None:
        r = self._result_with_channel(16)
        self.assertTrue(r.available)


# ---------------------------------------------------------------------------
# Invalid duration_ms
# ---------------------------------------------------------------------------

class InvalidDurationTests(unittest.TestCase):
    def _result_with_duration(self, duration_ms) -> LaserConfigResult:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["scenes"]["safe_static"]["midi"]["duration_ms"] = duration_ms
        return load_laser_director_config(_write_config(cfg))

    def test_duration_9_invalid(self) -> None:
        """Below minimum (10) must fail."""
        r = self._result_with_duration(9)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("duration_ms" in e for e in r.errors))

    def test_duration_0_invalid(self) -> None:
        r = self._result_with_duration(0)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_duration_251_invalid(self) -> None:
        """Above maximum (250) must fail."""
        r = self._result_with_duration(251)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("duration_ms" in e for e in r.errors))

    def test_duration_500_invalid(self) -> None:
        r = self._result_with_duration(500)
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_duration_10_valid(self) -> None:
        r = self._result_with_duration(10)
        self.assertTrue(r.available)

    def test_duration_250_valid(self) -> None:
        r = self._result_with_duration(250)
        self.assertTrue(r.available)

    def test_duration_80_valid(self) -> None:
        r = self._result_with_duration(80)
        self.assertTrue(r.available)

    def test_duration_not_validated_for_non_note_pulse(self) -> None:
        """duration_ms is only validated for note_pulse kind."""
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["scenes"]["safe_static"]["midi"]["kind"] = "cc"
        cfg["scenes"]["safe_static"]["midi"]["duration_ms"] = 9999
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)

    def test_behavior_hold_ms_requires_valid_range(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        midi = cfg["scenes"]["safe_static"]["midi"]
        midi["behavior"] = "hold_ms"
        midi["kind"] = "note_on"
        midi["hold_ms"] = 30001
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("hold_ms" in e for e in r.errors))

    def test_behavior_hold_beats_requires_valid_range(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        midi = cfg["scenes"]["safe_static"]["midi"]
        midi["behavior"] = "hold_beats"
        midi["kind"] = "note_on"
        midi["hold_beats"] = 0.1
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("hold_beats" in e for e in r.errors))

    def test_behavior_hold_beats_valid(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        midi = cfg["scenes"]["safe_static"]["midi"]
        midi["behavior"] = "hold_beats"
        midi["kind"] = "note_on"
        midi["hold_beats"] = 4
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available, msg=r.errors)


# ---------------------------------------------------------------------------
# midi_output_port validation
# ---------------------------------------------------------------------------

class MidiOutputPortTests(unittest.TestCase):
    def test_port_required_when_enabled_and_live(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["enabled"] = True
        cfg["dry_run"] = False
        cfg["midi_output_port"] = ""
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("midi_output_port" in e for e in r.errors))

    def test_port_not_required_when_dry_run_true(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["enabled"] = True
        cfg["dry_run"] = True
        cfg["midi_output_port"] = ""
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)

    def test_port_not_required_when_disabled(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["enabled"] = False
        cfg["dry_run"] = False
        cfg["midi_output_port"] = ""
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)

    def test_port_whitespace_only_invalid_when_live(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["enabled"] = True
        cfg["dry_run"] = False
        cfg["midi_output_port"] = "   "
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)

    def test_valid_port_stored_in_config(self) -> None:
        r = load_laser_director_config(_write_config(_MINIMAL_CONFIG))
        self.assertEqual(r.config.midi_output_port, "IAC Driver Bus 1")


# ---------------------------------------------------------------------------
# Arbitrary scene names
# ---------------------------------------------------------------------------

class ArbitrarySceneNameTests(unittest.TestCase):
    def test_arbitrary_scene_names_accepted(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["scenes"]["my_custom_xyz_1"] = {
            "scene_type": "autoloop",
            "safety_class": "movement_low",
            "midi": {"kind": "note_pulse", "channel": 1, "note": 50, "velocity": 127, "duration_ms": 80},
        }
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)
        self.assertIn("my_custom_xyz_1", r.config.scenes)

    def test_no_fixed_scene_names_required(self) -> None:
        """Config with entirely non-standard scene names is valid."""
        cfg = {
            "enabled": False,
            "dry_run": True,
            "midi_output_port": "IAC Driver Bus 1",
            "startup_scene":   "alpha_1",
            "stop_scene":      "alpha_1",
            "stale_scene":     "alpha_1",
            "emergency_scene": "omega_blackout",
            "fallback_scene":  "alpha_1",
            "scenes": {
                "alpha_1": {
                    "scene_type": "static",
                    "safety_class": "safe",
                    "midi": {"kind": "note_pulse", "channel": 1, "note": 36, "velocity": 127, "duration_ms": 80},
                },
                "omega_blackout": {
                    "scene_type": "utility",
                    "safety_class": "blackout",
                    "midi": {"kind": "note_pulse", "channel": 1, "note": 44, "velocity": 127, "duration_ms": 80},
                },
            },
        }
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)
        self.assertIn("alpha_1", r.config.scenes)
        self.assertIn("omega_blackout", r.config.scenes)

    def test_names_like_low_sweep_not_required(self) -> None:
        """Names like low_sweep, drop_hit, breakdown_blackout must not be mandatory."""
        r = load_laser_director_config(_write_config(_MINIMAL_CONFIG))
        self.assertTrue(r.available)
        self.assertNotIn("low_sweep", r.config.scenes)
        self.assertNotIn("drop_hit", r.config.scenes)
        self.assertNotIn("breakdown_blackout", r.config.scenes)


# ---------------------------------------------------------------------------
# Personality validation
# ---------------------------------------------------------------------------

class PersonalityValidationTests(unittest.TestCase):
    def _cfg_with_personality(self, personality_data: dict, default: str = "house") -> dict:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["personalities"] = {"house": personality_data}
        cfg["default_personality"] = default
        return cfg

    def _valid_personality(self) -> dict:
        return {
            "safe_scene": "safe_static",
            "default_scene": "safe_static",
            "phrase_scene": "safe_static",
            "buildup_scene": "safe_static",
            "pre_drop_scene": "safe_static",
            "drop_scene": "safe_static",
            "post_drop_scene": "safe_static",
            "breakdown_scene": "safe_static",
            "transition_scene": "safe_static",
        }

    def test_valid_personality_ok(self) -> None:
        cfg = self._cfg_with_personality(self._valid_personality())
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)
        self.assertIn("house", r.config.personalities)

    def test_personality_bad_scene_ref(self) -> None:
        p = self._valid_personality()
        p["drop_scene"] = "nonexistent_drop"
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("drop_scene" in e for e in r.errors))

    def test_missing_default_personality(self) -> None:
        cfg = self._cfg_with_personality(self._valid_personality(), default="techno")
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")
        self.assertTrue(any("default_personality" in e for e in r.errors))

    def test_default_personality_absent_when_personalities_present(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        cfg["personalities"] = {"house": self._valid_personality()}
        # deliberately omit default_personality
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertEqual(r.reason, "invalid_config")

    def test_no_personalities_no_default_required(self) -> None:
        """Without 'personalities', default_personality is not required."""
        r = load_laser_director_config(_write_config(_MINIMAL_CONFIG))
        self.assertTrue(r.available)

    def test_personality_is_laser_personality(self) -> None:
        cfg = self._cfg_with_personality(self._valid_personality())
        r = load_laser_director_config(_write_config(cfg))
        self.assertIsInstance(r.config.personalities["house"], LaserPersonality)

    def test_phrase_interval_beats_must_be_positive_int(self) -> None:
        p = self._valid_personality()
        p["phrase_interval_beats"] = 0
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("phrase_interval_beats" in e for e in r.errors))

    def test_phrase_interval_beats_rejects_non_int(self) -> None:
        p = self._valid_personality()
        p["phrase_interval_beats"] = "32"
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("phrase_interval_beats" in e for e in r.errors))

    def test_phrase_interval_beats_rejects_bool(self) -> None:
        p = self._valid_personality()
        p["phrase_interval_beats"] = True
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("phrase_interval_beats" in e for e in r.errors))

    def test_phrase_interval_beats_defaults_to_32(self) -> None:
        cfg = self._cfg_with_personality(self._valid_personality())
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)
        self.assertEqual(r.config.personalities["house"].phrase_interval_beats, 32)

    def test_minimum_scene_hold_beats_must_be_non_negative_int(self) -> None:
        p = self._valid_personality()
        p["minimum_scene_hold_beats"] = -1
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("minimum_scene_hold_beats" in e for e in r.errors))

    def test_minimum_scene_hold_beats_rejects_bool(self) -> None:
        p = self._valid_personality()
        p["minimum_scene_hold_beats"] = False
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("minimum_scene_hold_beats" in e for e in r.errors))

    def test_normal_changes_only_on_phrase_boundary_must_be_bool(self) -> None:
        p = self._valid_personality()
        p["normal_changes_only_on_phrase_boundary"] = "true"
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(
            any("normal_changes_only_on_phrase_boundary" in e for e in r.errors)
        )

    def test_new_personality_fields_default_values(self) -> None:
        cfg = self._cfg_with_personality(self._valid_personality())
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available)
        p = r.config.personalities["house"]
        self.assertEqual(p.minimum_scene_hold_beats, 0)
        self.assertFalse(p.normal_changes_only_on_phrase_boundary)
        self.assertEqual(p.buildup_lookahead_beats, 32)
        self.assertEqual(p.aliases, ())
        self.assertEqual(p.bpm_band_min, 0.0)
        self.assertEqual(p.bpm_band_max, 0.0)
        self.assertEqual(p.pre_drop_blackout_beats, 4)
        self.assertEqual(p.post_drop_hold_beats, 8)
        self.assertEqual(p.breakdown_default_restore_beats, 64)
        self.assertEqual(r.config.bpm_priority, ())

    def test_aliases_are_canonicalized(self) -> None:
        p = self._valid_personality()
        p["aliases"] = ["  Tech   House  "]
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available, msg=r.errors)
        self.assertEqual(r.config.personalities["house"].aliases, ("tech house",))

    def test_duplicate_alias_across_personalities_fails(self) -> None:
        import copy
        cfg = copy.deepcopy(_MINIMAL_CONFIG)
        house = self._valid_personality()
        house["aliases"] = ["House"]
        dubstep = self._valid_personality()
        dubstep["aliases"] = [" house "]
        cfg["personalities"] = {"house": house, "dubstep": dubstep}
        cfg["default_personality"] = "house"
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("duplicates" in e for e in r.errors))

    def test_bpm_band_min_must_be_less_than_max_unless_disabled(self) -> None:
        p = self._valid_personality()
        p["bpm_band_min"] = 130
        p["bpm_band_max"] = 120
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("bpm_band_min" in e for e in r.errors))

    def test_bpm_priority_references_existing_personalities(self) -> None:
        p = self._valid_personality()
        cfg = self._cfg_with_personality(p)
        cfg["bpm_priority"] = ["dubstep"]
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("bpm_priority" in e for e in r.errors))

    def test_bpm_priority_stored_in_config(self) -> None:
        p = self._valid_personality()
        p["bpm_band_min"] = 120
        p["bpm_band_max"] = 130
        cfg = self._cfg_with_personality(p)
        cfg["bpm_priority"] = ["house"]
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available, msg=r.errors)
        self.assertEqual(r.config.bpm_priority, ("house",))

    def test_buildup_lookahead_beats_must_be_positive_int(self) -> None:
        p = self._valid_personality()
        p["buildup_lookahead_beats"] = 0
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("buildup_lookahead_beats" in e for e in r.errors))

    def test_buildup_lookahead_beats_rejects_bool(self) -> None:
        p = self._valid_personality()
        p["buildup_lookahead_beats"] = True
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("buildup_lookahead_beats" in e for e in r.errors))

    def test_buildup_lookahead_beats_rejects_negative(self) -> None:
        p = self._valid_personality()
        p["buildup_lookahead_beats"] = -1
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("buildup_lookahead_beats" in e for e in r.errors))

    def test_pre_drop_scene_is_optional(self) -> None:
        p = self._valid_personality()
        p.pop("pre_drop_scene")
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available, msg=r.errors)

    def test_pre_drop_scene_must_reference_known_scene_when_present(self) -> None:
        p = self._valid_personality()
        p["pre_drop_scene"] = "unknown_scene"
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("pre_drop_scene" in e for e in r.errors))

    def test_scene_banks_are_optional(self) -> None:
        cfg = self._cfg_with_personality(self._valid_personality())
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available, msg=r.errors)
        p = r.config.personalities["house"]
        self.assertEqual(p.phrase_bank, ())
        self.assertEqual(p.buildup_bank, ())
        self.assertEqual(p.drop_bank, ())

    def test_scene_bank_references_must_exist(self) -> None:
        p = self._valid_personality()
        p["drop_bank"] = ["safe_static", "missing_scene"]
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("drop_bank" in e for e in r.errors))

    def test_scene_bank_must_be_list(self) -> None:
        p = self._valid_personality()
        p["phrase_bank"] = "safe_static"
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("phrase_bank" in e for e in r.errors))

    def test_scene_bank_items_must_be_non_empty_strings(self) -> None:
        p = self._valid_personality()
        p["post_drop_bank"] = ["safe_static", ""]
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertFalse(r.available)
        self.assertTrue(any("post_drop_bank" in e for e in r.errors))

    def test_scene_bank_empty_list_is_allowed(self) -> None:
        p = self._valid_personality()
        p["breakdown_bank"] = []
        cfg = self._cfg_with_personality(p)
        r = load_laser_director_config(_write_config(cfg))
        self.assertTrue(r.available, msg=r.errors)
        self.assertEqual(r.config.personalities["house"].breakdown_bank, ())

# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------

class NeverRaisesTests(unittest.TestCase):
    def _try(self, content: str) -> None:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        result = load_laser_director_config(f.name)
        self.assertIsInstance(result, LaserConfigResult)

    def test_empty_string(self) -> None:
        self._try("")

    def test_null_json(self) -> None:
        self._try("null")

    def test_array_json(self) -> None:
        self._try("[1, 2, 3]")

    def test_garbage_bytes(self) -> None:
        self._try("}{garbage}{")

    def test_deeply_wrong_values(self) -> None:
        self._try(json.dumps({
            "enabled": "yes",
            "dry_run": 42,
            "scenes": "not-a-dict",
        }))

    def test_missing_path_does_not_raise(self) -> None:
        result = load_laser_director_config("/completely/nonexistent/file.json")
        self.assertIsInstance(result, LaserConfigResult)


# ---------------------------------------------------------------------------
# Example file
# ---------------------------------------------------------------------------

class ExampleFileTests(unittest.TestCase):
    _EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "laser_director.example.json"

    def test_example_file_exists(self) -> None:
        self.assertTrue(self._EXAMPLE.exists(), f"example file missing: {self._EXAMPLE}")

    def test_example_file_loads_ok(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertTrue(result.available, f"example failed: {result.errors}")
        self.assertEqual(result.reason, "ok")

    def test_example_file_disabled_by_default(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertFalse(result.config.enabled)

    def test_example_file_dry_run_true(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertTrue(result.config.dry_run)

    def test_example_file_uses_iac_bus_1(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertEqual(result.config.midi_output_port, "IAC Driver Bus 1")

    def test_example_file_has_emergency_scene(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertIn(result.config.emergency_scene, result.config.scenes)

    def test_example_file_no_hardcoded_bad_names(self) -> None:
        """low_sweep, drop_hit, breakdown_blackout must not appear."""
        result = load_laser_director_config(str(self._EXAMPLE))
        for name in ("low_sweep", "drop_hit", "breakdown_blackout"):
            self.assertNotIn(name, result.config.scenes)

    def test_example_file_has_personality(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertIn("house", result.config.personalities)

    def test_example_file_default_personality_exists(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        self.assertIn(result.config.default_personality, result.config.personalities)

    def test_example_file_pre_drop_scene_not_active(self) -> None:
        result = load_laser_director_config(str(self._EXAMPLE))
        house = result.config.personalities["house"]
        self.assertEqual(house.pre_drop_scene, "")
        self.assertEqual(house.buildup_lookahead_beats, 32)


# ---------------------------------------------------------------------------
# LaserConfigResult is frozen
# ---------------------------------------------------------------------------

class LaserConfigResultFrozenTests(unittest.TestCase):
    def test_result_is_frozen(self) -> None:
        result = load_laser_director_config("/nonexistent.json")
        with self.assertRaises((AttributeError, TypeError)):
            result.available = True  # type: ignore[misc]

    def test_errors_tuple_is_immutable(self) -> None:
        result = LaserConfigResult(available=False, reason="not_configured")
        self.assertIsInstance(result.errors, tuple)


# ---------------------------------------------------------------------------
# LaserMidiMessage / LaserScene / LaserPersonality frozen model tests
# ---------------------------------------------------------------------------

class LaserModelsTests(unittest.TestCase):
    def test_laser_midi_message_is_frozen(self) -> None:
        msg = LaserMidiMessage(kind="note_pulse", channel=1, note=36)
        with self.assertRaises((AttributeError, TypeError)):
            msg.note = 99  # type: ignore[misc]

    def test_laser_scene_is_frozen(self) -> None:
        midi = LaserMidiMessage()
        scene = LaserScene(
            name="test", scene_type="static", safety_class="safe", midi=midi
        )
        with self.assertRaises((AttributeError, TypeError)):
            scene.name = "mutated"  # type: ignore[misc]

    def test_laser_personality_is_frozen(self) -> None:
        p = LaserPersonality(
            name="house",
            safe_scene="s", default_scene="s", phrase_scene="s",
            buildup_scene="s", pre_drop_scene="s", drop_scene="s",
            post_drop_scene="s", breakdown_scene="s", transition_scene="s",
        )
        with self.assertRaises((AttributeError, TypeError)):
            p.name = "mutated"  # type: ignore[misc]

    def test_laser_midi_message_defaults(self) -> None:
        msg = LaserMidiMessage()
        self.assertEqual(msg.kind, "note_pulse")
        self.assertEqual(msg.channel, 1)
        self.assertEqual(msg.note, 0)
        self.assertEqual(msg.velocity, 127)
        self.assertEqual(msg.duration_ms, 80)
        self.assertEqual(msg.behavior, "pulse")

    def test_laser_scene_defaults(self) -> None:
        scene = LaserScene(
            name="x", scene_type="static", safety_class="safe",
            midi=LaserMidiMessage(),
        )
        self.assertEqual(scene.fallback_scene, "safe_static")
        self.assertEqual(scene.cooldown_beats, 0.0)
        self.assertFalse(scene.immediate)

    def test_laser_personality_defaults(self) -> None:
        p = LaserPersonality(
            name="house",
            safe_scene="s", default_scene="s", phrase_scene="s",
            buildup_scene="s", pre_drop_scene="s", drop_scene="s",
            post_drop_scene="s", breakdown_scene="s", transition_scene="s",
        )
        self.assertFalse(p.allow_high_impact)
        self.assertEqual(p.phrase_interval_beats, 32)
        self.assertEqual(p.minimum_scene_hold_beats, 0)
        self.assertFalse(p.normal_changes_only_on_phrase_boundary)
        self.assertEqual(p.buildup_lookahead_beats, 32)


if __name__ == "__main__":
    unittest.main()
