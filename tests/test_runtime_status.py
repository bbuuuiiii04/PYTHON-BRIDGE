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


class LaserCommandParseTests(unittest.TestCase):
    def test_parse_command_accepts_toggle_laser_director(self) -> None:
        command = parse_command('{"cmd":"toggle_laser_director"}')
        self.assertEqual(command["cmd"], "toggle_laser_director")

    def test_parse_command_accepts_set_laser_director(self) -> None:
        command = parse_command('{"cmd":"set_laser_director","enabled":false}')
        self.assertFalse(command["enabled"])

    def test_parse_command_rejects_set_laser_director_without_enabled(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"set_laser_director"}')

    def test_parse_command_rejects_set_laser_director_non_bool_enabled(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"set_laser_director","enabled":"false"}')

    def test_parse_command_accepts_laser_blackout(self) -> None:
        command = parse_command('{"cmd":"laser_blackout"}')
        self.assertEqual(command["cmd"], "laser_blackout")

    def test_parse_command_accepts_laser_clear_blackout(self) -> None:
        command = parse_command('{"cmd":"laser_clear_blackout"}')
        self.assertEqual(command["cmd"], "laser_clear_blackout")

    def test_parse_command_accepts_laser_scene(self) -> None:
        command = parse_command('{"cmd":"laser_scene","scene":"house_drop_1","ttl_s":4}')
        self.assertEqual(command["scene"], "house_drop_1")
        self.assertEqual(command["ttl_s"], 4.0)

    def test_parse_command_laser_scene_requires_non_empty_scene(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"laser_scene","scene":""}')

    def test_parse_command_laser_scene_defaults_ttl_s(self) -> None:
        command = parse_command('{"cmd":"laser_scene","scene":"house_drop_1"}')
        self.assertEqual(command["ttl_s"], 4.0)

    def test_parse_command_laser_scene_clamps_ttl_low(self) -> None:
        command = parse_command('{"cmd":"laser_scene","scene":"house_drop_1","ttl_s":-10}')
        self.assertEqual(command["ttl_s"], 0.0)

    def test_parse_command_laser_scene_clamps_ttl_high(self) -> None:
        command = parse_command('{"cmd":"laser_scene","scene":"house_drop_1","ttl_s":100}')
        self.assertEqual(command["ttl_s"], 30.0)

    def test_parse_command_laser_scene_rejects_bool_ttl_s(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"laser_scene","scene":"house_drop_1","ttl_s":true}')

    def test_parse_command_laser_scene_rejects_non_finite_ttl_s_nan(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"laser_scene","scene":"house_drop_1","ttl_s":NaN}')

    def test_parse_command_laser_scene_rejects_non_finite_ttl_s_inf(self) -> None:
        with self.assertRaises(ValueError):
            parse_command(json.dumps({"cmd": "laser_scene", "scene": "house_drop_1", "ttl_s": float("inf")}))

    def test_parse_command_accepts_laser_clear_scene_override(self) -> None:
        command = parse_command('{"cmd":"laser_clear_scene_override"}')
        self.assertEqual(command["cmd"], "laser_clear_scene_override")

    def test_parse_command_accepts_laser_set_personality(self) -> None:
        command = parse_command('{"cmd":"laser_set_personality","personality":"dubstep"}')
        self.assertEqual(command["personality"], "dubstep")

    def test_parse_command_laser_set_personality_requires_non_empty(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"laser_set_personality","personality":""}')


class LaserCommandCallbackTests(unittest.TestCase):
    def test_toggle_laser_director_callback_failure_sets_last_error(self) -> None:
        reader = CommandReader(
            Mock(),
            Mock(),
            laser_toggle_callback=lambda: False,
        )

        reader.handle_command({"cmd": "toggle_laser_director"})

        self.assertIn("callback returned False", reader.status()["last_error"])

    def test_set_laser_director_callback_receives_enabled(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            Mock(),
            laser_set_enabled_callback=callback,
        )

        reader.handle_command({"cmd": "set_laser_director", "enabled": False})

        callback.assert_called_once_with(False)

    def test_laser_scene_callback_receives_scene_and_ttl(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            Mock(),
            laser_scene_callback=callback,
        )

        reader.handle_command({"cmd": "laser_scene", "scene": "custom_123", "ttl_s": 4.0})

        callback.assert_called_once_with("custom_123", 4.0)

    def test_laser_set_personality_callback_failure_sets_last_error(self) -> None:
        reader = CommandReader(
            Mock(),
            Mock(),
            laser_set_personality_callback=lambda _personality: False,
        )

        reader.handle_command({"cmd": "laser_set_personality", "personality": "dubstep"})

        self.assertIn("callback returned False", reader.status()["last_error"])


if __name__ == "__main__":
    unittest.main()
