import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.runtime_status import (  # noqa: E402
    CommandReader,
    StatusWriter,
    parse_command,
)


class RuntimeCommandTests(unittest.TestCase):
    def test_parse_command_rejects_unknown_command(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd": "live_replay"}')

    def test_parse_command_accepts_run_validation(self) -> None:
        command = parse_command('{"cmd": "run_validation"}')
        self.assertEqual(command["cmd"], "run_validation")

    def test_parse_command_accepts_smart_breakdown_toggle(self) -> None:
        command = parse_command('{"cmd": "toggle_smart_breakdown"}')

        self.assertEqual(command["cmd"], "toggle_smart_breakdown")

    def test_invalid_json_sets_last_error(self) -> None:
        reader = CommandReader(Mock())

        reader.handle_line("{not json")

        self.assertIn("invalid json", reader.status()["last_error"])

    def test_toggle_smart_drop_delegates_to_callback(self) -> None:
        callback = Mock()
        reader = CommandReader(Mock(), smart_drop_toggle_callback=callback)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_drop"}'))

        callback.assert_called_once()

    def test_toggle_smart_breakdown_delegates_to_callback(self) -> None:
        callback = Mock()
        reader = CommandReader(Mock(), smart_breakdown_toggle_callback=callback)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_breakdown"}'))

        callback.assert_called_once()

    def test_parse_command_accepts_toggle_record_session(self) -> None:
        command = parse_command(
            '{"cmd": "toggle_record_session", "path": "/tmp/capture.jsonl", "dedup": true}'
        )

        self.assertEqual(command["cmd"], "toggle_record_session")
        self.assertEqual(command["path"], "/tmp/capture.jsonl")
        self.assertTrue(command["dedup"])

    def test_toggle_record_session_delegates_to_callback(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(Mock(), record_session_toggle_callback=callback)

        reader.handle_command(
            {"cmd": "toggle_record_session", "path": "/tmp/capture.jsonl", "dedup": True}
        )

        callback.assert_called_once_with("/tmp/capture.jsonl", True)


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

    def test_parse_command_rejects_laser_set_personality_runtime_override(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"laser_set_personality","personality":"dubstep"}')


class LaserCommandCallbackTests(unittest.TestCase):
    def test_toggle_laser_director_callback_failure_sets_last_error(self) -> None:
        reader = CommandReader(
            Mock(),
            laser_toggle_callback=lambda: False,
        )

        reader.handle_command({"cmd": "toggle_laser_director"})

        self.assertIn("callback returned False", reader.status()["last_error"])

    def test_set_laser_director_callback_receives_enabled(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            laser_set_enabled_callback=callback,
        )

        reader.handle_command({"cmd": "set_laser_director", "enabled": False})

        callback.assert_called_once_with(False)

    def test_laser_scene_callback_receives_scene_and_ttl(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            laser_scene_callback=callback,
        )

        reader.handle_command({"cmd": "laser_scene", "scene": "custom_123", "ttl_s": 4.0})

        callback.assert_called_once_with("custom_123", 4.0)

    def test_laser_set_personality_runtime_command_is_unknown(self) -> None:
        reader = CommandReader(
            Mock(),
        )

        with self.assertRaises(ValueError):
            reader.handle_command({"cmd": "laser_set_personality", "personality": "dubstep"})


class RuntimeStatusWriterTests(unittest.TestCase):
    def _make_writer(self, *, sm_snapshot, laser_status):
        sm = Mock()
        sm.snapshot.return_value = sm_snapshot
        live_bpm = Mock()
        live_bpm.get_status.return_value = None
        live_bpm.get_summary.return_value = None
        pos_cache = Mock()
        pos_cache.get.return_value = None
        conn = Mock()
        conn.status.return_value = {"connected": True}
        validation_runner = Mock()
        validation_result = Mock()
        validation_result.to_dict.return_value = {
            "state": "idle",
            "checks": [],
            "pass_count": 0,
            "warn_count": 0,
            "fail_count": 0,
            "not_applicable_count": 0,
            "warming_count": 0,
            "latest_issue": "",
        }
        validation_runner.last_result.return_value = validation_result
        command_reader = Mock()
        command_reader.status.return_value = {"armed": False}
        return StatusWriter(
            sm,
            live_bpm,
            pos_cache,
            conn,
            validation_runner,
            command_reader,
            laser_status_provider=lambda: laser_status,
        )

    def test_status_writer_emits_smart_phrasing_block(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 1,
                "deck": {"1": {}, "2": {}},
                "smart_phrasing": {
                    "phrase_label": "up",
                    "next_smart_drop_beat": 128.0,
                    "beats_to_next_drop": 32.0,
                },
            },
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
        )
        snap = writer.snapshot()
        self.assertEqual(
            snap["state_manager"]["smart_phrasing"]["phrase_label"],
            "up",
        )
        self.assertEqual(
            snap["state_manager"]["smart_phrasing"]["next_smart_drop_beat"],
            128.0,
        )

    def test_status_writer_laser_director_includes_executor(self) -> None:
        writer = self._make_writer(
            sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
            laser_status={
                "available": True,
                "enabled": True,
                "current_scene": "house_phrase_1",
                "executor": {
                    "midi": {
                        "queue_size": 1,
                        "queue_max": 256,
                        "drop_count": 0,
                    }
                },
            },
        )
        snap = writer.snapshot()
        self.assertTrue(snap["laser_director"]["available"])
        self.assertEqual(snap["laser_director"]["current_scene"], "house_phrase_1")
        self.assertEqual(
            snap["laser_director"]["executor"]["midi"]["queue_size"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
