"""T7e — set_soundswitch_pack parse/validate + sanitized status/error tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.runtime_status import CommandReader, parse_command
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime

_FORBIDDEN = ("/", "tty", "cu.", "COM", "enttec", "port", "alias", "device",
              "fixture_map", "pack_path")


class _LeakyBackend:
    """A backend whose status() tries to leak sensitive fields."""
    def status(self):
        return {
            "backend": "pack",
            "frame_count": 3,
            "last_accepted_identity": "3CCBCD6F-7C1B-44D8-882C-A52A74CC1827",
            "enttec_port": "/dev/cu.usbserial-AB",
            "midi_input_aliases": {"IAC Driver Bus 1": "x"},
            "pack_path": "/Users/bbui/Music/SoundSwitch/default.ssproj",
        }


class PackCommandParseTests(unittest.TestCase):
    def test_accepts_valid_forms(self):
        for line in (
            '{"cmd":"set_soundswitch_pack","action":"reload"}',
            '{"cmd":"set_soundswitch_pack","action":"backend","backend":"pack"}',
            '{"cmd":"set_soundswitch_pack","action":"backend","backend":"none"}',
            '{"cmd":"set_soundswitch_pack","action":"enable","enabled":true}',
            '{"cmd":"set_soundswitch_pack","action":"enable","enabled":false}',
        ):
            self.assertEqual(parse_command(line)["cmd"], "set_soundswitch_pack")

    def test_rejects_bad_forms(self):
        for line in (
            '{"cmd":"set_soundswitch_pack","action":"bogus"}',
            '{"cmd":"set_soundswitch_pack","action":"backend","backend":"laser"}',
            '{"cmd":"set_soundswitch_pack","action":"enable","enabled":"yes"}',
            '{"cmd":"set_soundswitch_pack","action":"reload","junk":1}',
            '{"cmd":"set_soundswitch_pack"}',
        ):
            with self.assertRaises(ValueError):
                parse_command(line)

    def test_backend_midi_parses_but_callback_rejects(self):
        # parse accepts midi syntactically; the deferral happens at the callback.
        self.assertEqual(
            parse_command('{"cmd":"set_soundswitch_pack","action":"backend","backend":"midi"}')["backend"],
            "midi")


class PackCommandDispatchTests(unittest.TestCase):
    def _reader(self, cb):
        return CommandReader(validation_runner=mock.Mock(), pack_command_callback=cb)

    def test_rejected_command_does_not_invoke_callback(self):
        cb = mock.Mock()
        reader = self._reader(cb)
        reader.handle_line('{"cmd":"set_soundswitch_pack","action":"bogus"}')
        cb.assert_not_called()
        self.assertIn("action must be", reader.status()["last_error"])

    def test_valid_command_invokes_callback_with_kwargs(self):
        cb = mock.Mock(return_value=(True, "pack"))
        reader = self._reader(cb)
        reader.handle_line('{"cmd":"set_soundswitch_pack","action":"backend","backend":"none"}')
        cb.assert_called_once_with("backend", backend="none")
        self.assertEqual(reader.status()["last_error"], "")

    def test_callback_exception_is_sanitized(self):
        def boom(action, **k):
            raise ValueError("verify failed reading /dev/cu.usbserial enttec port alias")
        reader = self._reader(boom)
        reader.handle_line('{"cmd":"set_soundswitch_pack","action":"reload"}')
        err = reader.status()["last_error"]
        self.assertIn("ValueError", err)
        for tok in _FORBIDDEN:
            self.assertNotIn(tok, err, f"leaked {tok!r} in {err!r}")

    def test_callback_returns_sanitized_unsupported_for_midi(self):
        cb = mock.Mock(return_value=(False, "unsupported_action"))
        reader = self._reader(cb)
        reader.handle_line('{"cmd":"set_soundswitch_pack","action":"backend","backend":"midi"}')
        cb.assert_called_once_with("backend", backend="midi")
        self.assertIn("unsupported_action", reader.status()["last_error"])


class PackStatusSanitizationTests(unittest.TestCase):
    def test_sanitized_status_drops_sensitive_fields(self):
        rt = PackRuntime(enabled=True, reason="pack", player=object(),
                         backend=_LeakyBackend(), pack_sha12="88a2e9484869")
        status = rt.sanitized_status()
        blob = json.dumps(status)
        for tok in _FORBIDDEN:
            self.assertNotIn(tok, blob, f"leaked {tok!r} in {blob!r}")
        # the raw UUID identity must not appear; only a boolean flag.
        self.assertNotIn("3CCBCD6F", blob)
        self.assertTrue(status["has_active_identity"])
        self.assertEqual(status["frame_count"], 3)
        self.assertEqual(status["pack_sha12"], "88a2e9484869")

    def test_disabled_status_is_clean(self):
        blob = json.dumps(PackRuntime().sanitized_status())
        for tok in _FORBIDDEN:
            self.assertNotIn(tok, blob)


if __name__ == "__main__":
    unittest.main()
