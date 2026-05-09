import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.runtime_status import (  # noqa: E402
    MAX_ARM_TTL_S,
    CommandReader,
    parse_command,
)


class RuntimeCommandTests(unittest.TestCase):
    def test_parse_command_rejects_unknown_command(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd": "live_replay"}')

    def test_parse_command_drops_expires_at(self) -> None:
        command = parse_command('{"cmd": "arm_live", "expires_at": 9999999999, "ttl_s": 10}')
        self.assertNotIn("expires_at", command)
        self.assertEqual(command["ttl_s"], 10)

    def test_parse_command_accepts_smart_breakdown_toggle(self) -> None:
        command = parse_command('{"cmd": "toggle_smart_breakdown"}')

        self.assertEqual(command["cmd"], "toggle_smart_breakdown")

    def test_arm_ttl_is_clamped_by_bridge(self) -> None:
        reader = CommandReader(Mock(), Mock())

        reader.handle_command({"cmd": "arm_live", "ttl_s": 9999})

        status = reader.status()
        self.assertTrue(status["armed"])
        self.assertLessEqual(status["arm_expires_at"], time.time() + MAX_ARM_TTL_S + 0.5)

    def test_invalid_json_sets_last_error(self) -> None:
        reader = CommandReader(Mock(), Mock())

        reader.handle_line("{not json")

        self.assertIn("invalid json", reader.status()["last_error"])

    def test_toggle_mirror_delegates_to_mirror(self) -> None:
        mirror = Mock()
        reader = CommandReader(mirror, Mock())

        reader.handle_command(json.loads('{"cmd": "toggle_mirror"}'))

        mirror.toggle.assert_called_once()

    def test_toggle_smart_drop_delegates_to_callback(self) -> None:
        callback = Mock()
        reader = CommandReader(Mock(), Mock(), smart_drop_toggle_callback=callback)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_drop"}'))

        callback.assert_called_once()

    def test_toggle_smart_breakdown_delegates_to_callback(self) -> None:
        callback = Mock()
        reader = CommandReader(Mock(), Mock(), smart_breakdown_toggle_callback=callback)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_breakdown"}'))

        callback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
