"""Software-only tests for the SoundSwitch pack-player config loader."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import soundswitch_pack_player_config as config_module  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_player_config import (
    SoundSwitchPackPlayerConfig,
    load_soundswitch_pack_player_config,
    load_soundswitch_pack_player_config_from_dict,
)  # noqa: E402


def _identity_map() -> dict[str, int]:
    return {str(channel): channel for channel in range(1, 20)}


def _valid(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "enabled": False,
        "dry_run": True,
        "output_backend": "none",
        "pack_path": "",
        "fixture_map": _identity_map(),
        "fixture_map_path": "",
        "midi_input_aliases": {},
        "enttec_port": "",
        "frame_stale_timeout_ms": 250,
        "controller_hold_timeout_ms": 2000,
    }
    value.update(updates)
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class SoundSwitchPackPlayerConfigTests(unittest.TestCase):
    def test_absent_explicit_path_is_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = load_soundswitch_pack_player_config(str(Path(tmp) / "missing.json"))
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "not_configured")
        self.assertIsNone(result.config)
        self.assertEqual(result.errors, ())

    def test_empty_object_uses_safe_defaults(self) -> None:
        result = load_soundswitch_pack_player_config_from_dict({})
        self.assertTrue(result.available, result.errors)
        self.assertEqual(result.reason, "ok")
        config = result.config
        self.assertIsNotNone(config)
        assert config is not None
        self.assertFalse(config.enabled)
        self.assertTrue(config.dry_run)
        self.assertEqual(config.output_backend, "none")
        self.assertEqual(config.pack_path, "")
        self.assertEqual(dict(config.fixture_map), {channel: channel for channel in range(1, 20)})
        self.assertEqual(config.fixture_map_path, "")
        self.assertEqual(dict(config.midi_input_aliases), {})
        self.assertEqual(config.enttec_port, "")
        self.assertEqual(config.frame_stale_timeout_ms, 250)
        self.assertEqual(config.controller_hold_timeout_ms, 2000)

    def test_valid_full_config_and_frozen_fields(self) -> None:
        result = load_soundswitch_pack_player_config_from_dict(_valid(
            enabled=True,
            dry_run=False,
            output_backend="pack",
            pack_path="packs/current",
            midi_input_aliases={"DDJ-800": "controller-input"},
            enttec_port="dmx-output",
            frame_stale_timeout_ms=500,
            controller_hold_timeout_ms=3000,
        ))
        self.assertTrue(result.available, result.errors)
        config = result.config
        assert config is not None
        with self.assertRaises(FrozenInstanceError):
            config.enabled = False  # type: ignore[misc]
        with self.assertRaises(TypeError):
            config.fixture_map[1] = 99  # type: ignore[index]
        with self.assertRaises(TypeError):
            config.midi_input_aliases["x"] = "y"  # type: ignore[index]

    def test_tracked_example_is_valid_and_inert(self) -> None:
        example = Path(__file__).resolve().parents[1] / "config" / \
            "soundswitch_pack_player.example.json"
        result = load_soundswitch_pack_player_config(str(example))
        self.assertTrue(result.available, result.errors)
        assert result.config is not None
        self.assertFalse(result.config.enabled)
        self.assertTrue(result.config.dry_run)
        self.assertEqual(result.config.output_backend, "none")
        self.assertEqual(result.config.enttec_port, "")

    def test_explicit_path_precedes_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "explicit.json"
            environ = root / "env.json"
            _write_json(explicit, _valid(output_backend="pack"))
            _write_json(environ, _valid(output_backend="midi"))
            with mock.patch.dict(
                os.environ,
                {"RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG": str(environ)},
            ):
                result = load_soundswitch_pack_player_config(str(explicit))
        self.assertTrue(result.available, result.errors)
        assert result.config is not None
        self.assertEqual(result.config.output_backend, "pack")

    def test_environment_precedes_repo_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            environ = root / "env.json"
            default = root / "default.json"
            _write_json(environ, _valid(output_backend="midi"))
            _write_json(default, _valid(output_backend="pack"))
            with mock.patch.object(config_module, "_DEFAULT_CONFIG_PATH", default), \
                    mock.patch.dict(
                        os.environ,
                        {"RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG": str(environ)},
                    ):
                result = load_soundswitch_pack_player_config()
        self.assertTrue(result.available, result.errors)
        assert result.config is not None
        self.assertEqual(result.config.output_backend, "midi")

    def test_repo_default_used_without_explicit_or_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            default = Path(tmp) / "default.json"
            _write_json(default, _valid(output_backend="pack"))
            with mock.patch.object(config_module, "_DEFAULT_CONFIG_PATH", default), \
                    mock.patch.dict(os.environ, {}, clear=True):
                result = load_soundswitch_pack_player_config()
        self.assertTrue(result.available, result.errors)
        assert result.config is not None
        self.assertEqual(result.config.output_backend, "pack")

    def test_relative_fixture_map_path_is_relative_to_config_and_overrides_inline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            maps = root / "maps"
            maps.mkdir()
            fixture = {str(channel): channel + 100 for channel in range(1, 20)}
            _write_json(maps / "fixture.json", fixture)
            config_path = root / "player.json"
            _write_json(config_path, _valid(
                fixture_map=_identity_map(),
                fixture_map_path="maps/fixture.json",
            ))
            result = load_soundswitch_pack_player_config(str(config_path))
        self.assertTrue(result.available, result.errors)
        assert result.config is not None
        self.assertEqual(dict(result.config.fixture_map), {
            channel: channel + 100 for channel in range(1, 20)
        })

    def test_absolute_fixture_map_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_path = root / "fixture.json"
            _write_json(fixture_path, _identity_map())
            result = load_soundswitch_pack_player_config_from_dict(
                _valid(fixture_map_path=str(fixture_path)),
                base_dir=root / "ignored",
            )
        self.assertTrue(result.available, result.errors)

    def test_fixture_map_path_read_or_parse_error_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fixture.json").write_text("[", encoding="utf-8")
            result = load_soundswitch_pack_player_config_from_dict(
                _valid(fixture_map_path="fixture.json"),
                base_dir=root,
            )
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")
        self.assertTrue(any("fixture_map_path cannot be loaded" in e for e in result.errors))

    def test_invalid_json_and_non_object_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid_json = root / "invalid.json"
            invalid_json.write_text("{", encoding="utf-8")
            invalid_root = root / "root.json"
            invalid_root.write_text("[]", encoding="utf-8")
            json_result = load_soundswitch_pack_player_config(str(invalid_json))
            root_result = load_soundswitch_pack_player_config(str(invalid_root))
        self.assertEqual(json_result.reason, "invalid_config")
        self.assertEqual(root_result.reason, "invalid_config")

    def test_duplicate_exact_json_key_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.json"
            path.write_text(
                '{"enabled": false, "enabled": true}',
                encoding="utf-8",
            )
            result = load_soundswitch_pack_player_config(str(path))
        self.assertFalse(result.available)
        self.assertTrue(any("duplicate JSON key" in e for e in result.errors))

    def test_duplicate_fixture_channel_after_integer_coercion_is_invalid(self) -> None:
        fixture = _identity_map()
        fixture["01"] = 50
        result = load_soundswitch_pack_player_config_from_dict(_valid(fixture_map=fixture))
        self.assertFalse(result.available)
        self.assertTrue(any("duplicate channel" in e for e in result.errors))

    def test_fixture_map_requires_exact_ch1_ch19(self) -> None:
        cases = []
        missing = _identity_map()
        missing.pop("19")
        cases.append(missing)
        extra = _identity_map()
        extra["20"] = 20
        cases.append(extra)
        bool_address = _identity_map()
        bool_address["1"] = True
        cases.append(bool_address)
        string_address = _identity_map()
        string_address["1"] = "1"  # type: ignore[assignment]
        cases.append(string_address)
        out_of_range = _identity_map()
        out_of_range["1"] = 513
        cases.append(out_of_range)
        for fixture in cases:
            with self.subTest(fixture=fixture):
                result = load_soundswitch_pack_player_config_from_dict(
                    _valid(fixture_map=fixture),
                )
                self.assertFalse(result.available)
                self.assertEqual(result.reason, "invalid_config")

    def test_scalar_and_alias_validation(self) -> None:
        invalid_values = (
            {"enabled": 1},
            {"dry_run": "true"},
            {"output_backend": "serial"},
            {"pack_path": 1},
            {"fixture_map_path": 1},
            {"midi_input_aliases": []},
            {"midi_input_aliases": {"": "port"}},
            {"midi_input_aliases": {"DDJ-800": ""}},
            {"enttec_port": 1},
            {"frame_stale_timeout_ms": True},
            {"frame_stale_timeout_ms": 0},
            {"controller_hold_timeout_ms": -1},
            {"unknown_key": True},
        )
        for update in invalid_values:
            with self.subTest(update=update):
                result = load_soundswitch_pack_player_config_from_dict(_valid(**update))
                self.assertFalse(result.available)
                self.assertEqual(result.reason, "invalid_config")

    def test_public_loaders_never_raise(self) -> None:
        with mock.patch.object(
            config_module,
            "_read_json_object",
            side_effect=RuntimeError("unexpected read failure"),
        ), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{}", encoding="utf-8")
            result = load_soundswitch_pack_player_config(str(path))
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")

        with mock.patch.object(config_module, "_fixture_map", side_effect=RuntimeError("boom")):
            result = load_soundswitch_pack_player_config_from_dict(_valid())
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")

    def test_result_config_type(self) -> None:
        result = load_soundswitch_pack_player_config_from_dict(_valid())
        self.assertIsInstance(result.config, SoundSwitchPackPlayerConfig)
        with self.assertRaises(FrozenInstanceError):
            result.available = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
