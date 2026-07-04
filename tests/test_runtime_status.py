import json
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.runtime_status import (  # noqa: E402
    CommandReader,
    StatusWriter,
    _safe_provider_snapshot,
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

    def test_toggle_smart_drop_callback_failure_sets_last_error(self) -> None:
        reader = CommandReader(Mock(), smart_drop_toggle_callback=lambda: False)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_drop"}'))

        self.assertIn("callback returned False", reader.status()["last_error"])

    def test_toggle_smart_breakdown_delegates_to_callback(self) -> None:
        callback = Mock()
        reader = CommandReader(Mock(), smart_breakdown_toggle_callback=callback)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_breakdown"}'))

        callback.assert_called_once()

    def test_toggle_smart_breakdown_callback_failure_sets_last_error(self) -> None:
        reader = CommandReader(Mock(), smart_breakdown_toggle_callback=lambda: False)

        reader.handle_command(json.loads('{"cmd": "toggle_smart_breakdown"}'))

        self.assertIn("callback returned False", reader.status()["last_error"])

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


class LEDCommandParseTests(unittest.TestCase):
    def test_parse_command_accepts_led_scene_with_look(self) -> None:
        command = parse_command('{"cmd":"led_scene","look":"room_drop_white_burst","ttl_s":5}')
        self.assertEqual(command["cmd"], "led_scene")
        self.assertEqual(command["look"], "room_drop_white_burst")
        self.assertEqual(command["ttl_s"], 5.0)

    def test_parse_command_accepts_led_scene_with_scene_alias(self) -> None:
        command = parse_command('{"cmd":"led_scene","scene":"room_drop_white_burst"}')
        self.assertEqual(command["look"], "room_drop_white_burst")
        self.assertNotIn("scene", command)

    def test_parse_command_rejects_led_scene_without_look(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_scene"}')

    def test_parse_command_rejects_led_scene_conflicting_look_and_scene(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_scene","look":"room_a","scene":"room_b"}')

    def test_parse_command_rejects_led_scene_non_positive_ttl(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_scene","look":"room_a","ttl_s":0}')

    def test_parse_command_rejects_led_scene_non_finite_ttl(self) -> None:
        with self.assertRaises(ValueError):
            parse_command(json.dumps({"cmd": "led_scene", "look": "room_a", "ttl_s": float("inf")}))

    def test_parse_command_rejects_led_scene_unknown_field(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_scene","look":"room_a","foo":"bar"}')

    def test_parse_command_accepts_led_blackout_without_reason(self) -> None:
        command = parse_command('{"cmd":"led_blackout"}')
        self.assertEqual(command["cmd"], "led_blackout")

    def test_parse_command_accepts_led_blackout_with_reason(self) -> None:
        command = parse_command('{"cmd":"led_blackout","reason":"operator"}')
        self.assertEqual(command["reason"], "operator")

    def test_parse_command_rejects_led_blackout_invalid_reason(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_blackout","reason":""}')

    def test_parse_command_accepts_led_clear_blackout(self) -> None:
        command = parse_command('{"cmd":"led_clear_blackout"}')
        self.assertEqual(command["cmd"], "led_clear_blackout")

    def test_parse_command_rejects_led_clear_blackout_payload(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_clear_blackout","reason":"nope"}')

    def test_parse_command_accepts_led_clear_scene_override(self) -> None:
        command = parse_command('{"cmd":"led_clear_scene_override"}')
        self.assertEqual(command["cmd"], "led_clear_scene_override")

    def test_parse_command_accepts_set_led_look_director(self) -> None:
        command = parse_command('{"cmd":"set_led_look_director","enabled":true}')
        self.assertTrue(command["enabled"])

    def test_parse_command_rejects_set_led_look_director_missing_enabled(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"set_led_look_director"}')

    def test_parse_command_rejects_set_led_look_director_non_bool_enabled(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"set_led_look_director","enabled":"true"}')

    def test_parse_command_accepts_palette_queue_and_override(self) -> None:
        self.assertEqual(
            parse_command('{"cmd":"led_palette_queue","name":"blue_cyan"}')["name"],
            "blue_cyan",
        )
        self.assertEqual(
            parse_command('{"cmd":"led_palette_override","name":"white_sand"}')["name"],
            "white_sand",
        )

    def test_parse_command_rejects_palette_queue_without_name(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_palette_queue"}')

    def test_parse_command_accepts_palette_toggles(self) -> None:
        for cmd in ("led_palette_lock", "led_palette_unlock", "led_rainbow_toggle"):
            self.assertEqual(parse_command(json.dumps({"cmd": cmd}))["cmd"], cmd)


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


class LEDCommandCallbackTests(unittest.TestCase):
    def test_set_led_look_director_callback_receives_enabled(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            led_set_enabled_callback=callback,
        )

        reader.handle_command({"cmd": "set_led_look_director", "enabled": True})

        callback.assert_called_once_with(True)

    def test_led_scene_callback_receives_look_and_ttl(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            led_scene_callback=callback,
        )

        reader.handle_command({"cmd": "led_scene", "look": "room_drop_white_burst", "ttl_s": 4.0})
        callback.assert_called_once_with("room_drop_white_burst", 4.0, None)

    def test_led_scene_callback_receives_target(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            led_scene_callback=callback,
        )

        reader.handle_command(
            {"cmd": "led_scene", "look": "room_drop_white_burst", "target": "strip_light_mirror"}
        )
        callback.assert_called_once_with("room_drop_white_burst", None, "strip_light_mirror")

    def test_led_blackout_callback_receives_target(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(
            Mock(),
            led_blackout_callback=callback,
        )

        reader.handle_command({"cmd": "led_blackout", "target": "strip_light_mirror"})
        callback.assert_called_once_with(None, "strip_light_mirror")

    def test_led_blackout_callback_failure_sets_last_error(self) -> None:
        reader = CommandReader(
            Mock(),
            led_blackout_callback=lambda reason, target=None: False,
        )

        reader.handle_command({"cmd": "led_blackout", "reason": "operator"})

        self.assertIn("callback returned False", reader.status()["last_error"])

    def test_led_palette_callback_receives_command_and_name(self) -> None:
        callback = Mock(return_value=True)
        reader = CommandReader(Mock(), led_palette_callback=callback)

        reader.handle_command({"cmd": "led_palette_queue", "name": "blue_cyan"})
        reader.handle_command({"cmd": "led_palette_lock"})

        callback.assert_any_call("led_palette_queue", "blue_cyan")
        callback.assert_any_call("led_palette_lock", None)


class RuntimeStatusWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        # Heartbeat throttle keys derive from id(self) of the writer, and the
        # throttle registry is process-global; id() reuse across short-lived
        # per-test writers otherwise leaks throttle state between tests.
        from rb_ss_bridge_v2.bridge_fmt import reset_rate_state

        reset_rate_state()

    def _make_writer(
        self,
        *,
        sm_snapshot,
        laser_status,
        laser_provider=None,
        led_status=None,
        led_provider=None,
        color_status=None,
        color_provider=None,
        pack_status=None,
        pack_provider=None,
    ):
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
        if led_provider is None:
            led_provider = (
                (lambda: led_status)
                if led_status is not None
                else None
            )
        if color_provider is None:
            color_provider = (
                (lambda: color_status)
                if color_status is not None
                else None
            )
        if laser_provider is None:
            laser_provider = lambda: laser_status
        if pack_provider is None and pack_status is not None:
            pack_provider = lambda: pack_status
        return StatusWriter(
            sm,
            live_bpm,
            pos_cache,
            conn,
            validation_runner,
            command_reader,
            laser_status_provider=laser_provider,
            led_status_provider=led_provider,
            color_engine_status_provider=color_provider,
            pack_status_provider=pack_provider,
        )

    def test_pack_status_default_and_copied_provider_schema(self) -> None:
        writer = self._make_writer(
            sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
        )
        default = writer.snapshot()["soundswitch_pack"]
        self.assertEqual(default["operational_state"], "disabled")
        self.assertTrue(default["software_zero_frame"])
        self.assertFalse(default["parity_live_blocked"])
        self.assertEqual(default["frame_count"], 0)

        pack = dict(default, enabled=True, backend="pack",
                    operational_state="scripted_active", scripted_active=True,
                    software_zero_frame=False, frame_count=7)
        writer = self._make_writer(
            sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            pack_status=pack,
        )
        self.assertEqual(writer.snapshot()["soundswitch_pack"], pack)

    def test_pack_provider_failure_is_bounded_and_does_not_leak(self) -> None:
        def fail():
            raise RuntimeError("/private/device/raw provider failure")

        writer = self._make_writer(
            sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            pack_provider=fail,
        )
        pack = writer.snapshot()["soundswitch_pack"]
        self.assertEqual(pack["reason"], "provider_error")
        self.assertEqual(pack["operational_state"], "disabled")
        self.assertNotIn("private", repr(pack))
        self.assertNotIn("device", repr(pack))

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

    def test_status_writer_led_status_provider_failure_is_fail_soft(self) -> None:
        def _boom():
            raise RuntimeError("led status unavailable")

        writer = self._make_writer(
            sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            led_provider=_boom,
        )
        snap = writer.snapshot()
        self.assertFalse(snap["led_look_director"]["available"])
        self.assertEqual(snap["led_look_director"]["reason"], "provider_error")
        self.assertIn("RuntimeError", snap["led_look_director"]["last_error"])

    def test_status_writer_emits_beat_heartbeat_payload(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 2,
                "rb_master_deck": 1,
                "rb_master_deck_valid": True,
                "active_deck_authority_reason": "bass_dominance",
                "mixer_authority_valid": True,
                "mixer_fallback_reason": "",
                "deck": {"1": {}, "2": {"bpm": 126.25}},
                "smart_phrasing": {"phrase_label": "chorus"},
            },
            laser_status={
                "available": True,
                "enabled": True,
                "current_scene": "house_chorus",
            },
            led_status={
                "available": True,
                "enabled": True,
                "reason": "ok",
                "last_look": "rt_groove_chase",
                "adapter": {
                    "realtime": {
                        "active": True,
                        "transport": {"send_error_count": 0},
                    },
                },
            },
            color_status={"current_palette": "cyan_lime"},
        )

        snap = writer.snapshot()

        self.assertEqual(
            snap["heartbeat"],
            {
                "deck": 2,
                "show_deck": 2,
                "master": 1,
                "rb_master_deck": 1,
                "rb_master_deck_valid": True,
                "active_deck_authority_reason": "bass_dominance",
                "mixer_authority_valid": True,
                "mixer_fallback_reason": "",
                "bpm": "126.2",
                "bpm_source": "deck",
                "phrase": "chorus",
                "laser_scene": "house_chorus",
                "led_look": "rt_groove_chase",
                "palette": "cyan_lime",
                "rgb_health": "realtime_active",
            },
        )

    def test_status_writer_heartbeat_suppresses_stale_rb_master(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 2,
                "rb_master_deck": 1,
                "rb_master_deck_valid": True,
                "rb_master_deck_age_s": 3.0,
                "active_deck_authority_reason": "rb_master_tie",
                "mixer_authority_valid": True,
                "mixer_fallback_reason": "",
                "deck": {"1": {}, "2": {"bpm": 126.25}},
            },
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            led_status={"available": False, "enabled": False, "reason": "not_configured"},
            color_status={},
        )

        snap = writer.snapshot()

        self.assertIsNone(snap["heartbeat"]["master"])
        self.assertIsNone(snap["heartbeat"]["rb_master_deck"])
        self.assertFalse(snap["heartbeat"]["rb_master_deck_valid"])
        self.assertEqual(snap["heartbeat"]["deck"], 2)

    def test_status_writer_heartbeat_keeps_fresh_rb_master(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 1,
                "rb_master_deck": 2,
                "rb_master_deck_valid": True,
                "rb_master_deck_age_s": 0.5,
                "deck": {"1": {"bpm": 128.0}, "2": {}},
            },
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            led_status={"available": False, "enabled": False, "reason": "not_configured"},
            color_status={},
        )

        snap = writer.snapshot()

        self.assertEqual(snap["heartbeat"]["master"], 2)
        self.assertEqual(snap["heartbeat"]["rb_master_deck"], 2)
        self.assertTrue(snap["heartbeat"]["rb_master_deck_valid"])

    def test_status_writer_logs_throttled_beat_heartbeat(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 1,
                "rb_master_deck": 2,
                "rb_master_deck_valid": True,
                "deck": {"1": {"bpm": 128.0}, "2": {}},
                "smart_phrasing": {"phrase_label": "up"},
            },
            laser_status={
                "available": True,
                "enabled": True,
                "current_scene": "house_up",
            },
            led_status={
                "available": True,
                "enabled": True,
                "reason": "ok",
                "director": {"current_look": "rt_twinkle"},
            },
            color_status={"current_palette": "blue_green"},
        )

        with self.assertLogs("runtime_status", level="INFO") as captured:
            writer.snapshot()

        line = "\n".join(captured.output)
        self.assertIn("[BEAT] deck=1 rb_master=2 bpm=128.0", line)
        self.assertIn("phrase=up", line)
        self.assertIn("laser=house_up", line)
        self.assertIn("led=rt_twinkle", line)
        self.assertIn("palette=blue_green", line)

    def test_status_writer_heartbeat_safe_for_idle_show_deck(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 0,
                "rb_master_deck": None,
                "rb_master_deck_valid": False,
                "active_deck_authority_reason": "idle_no_audible",
                "mixer_authority_valid": True,
                "mixer_fallback_reason": "",
                "deck": {"1": {"bpm": 128.0}, "2": {"bpm": 130.0}},
                "smart_phrasing": {"phrase_label": "unknown"},
            },
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            led_status={"available": False, "enabled": False, "reason": "not_configured"},
            color_status={},
        )

        snap = writer.snapshot()

        self.assertEqual(snap["heartbeat"]["deck"], 0)
        self.assertIsNone(snap["heartbeat"]["master"])
        self.assertEqual(snap["heartbeat"]["bpm"], "unknown")
        self.assertEqual(snap["heartbeat"]["active_deck_authority_reason"], "idle_no_audible")

    def test_status_writer_suppresses_immediate_beat_heartbeat_repeat(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 1,
                "deck": {"1": {"bpm": 128.0}, "2": {}},
                "smart_phrasing": {"phrase_label": "up"},
            },
            laser_status={
                "available": True,
                "enabled": True,
                "current_scene": "house_up",
            },
            led_status={
                "available": True,
                "enabled": True,
                "reason": "ok",
                "director": {"current_look": "rt_twinkle"},
            },
            color_status={"current_palette": "blue_green"},
        )

        with self.assertLogs("runtime_status", level="INFO") as captured:
            writer.snapshot()
            writer.snapshot()

        messages = [record for record in captured.output if "[BEAT]" in record]
        self.assertEqual(len(messages), 1)

    def test_status_writer_uses_published_color_engine_status(self) -> None:
        writer = self._make_writer(
            sm_snapshot={
                "active_deck": 1,
                "deck": {"1": {"bpm": 128.0}, "2": {}},
                "smart_phrasing": {"phrase_label": "up"},
                "led_color_engine": {"current_palette": "published_palette"},
            },
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            led_status={"available": False, "enabled": False, "reason": "not_configured"},
        )

        snap = writer.snapshot()

        self.assertEqual(snap["heartbeat"]["palette"], "published_palette")

    def test_status_writer_color_provider_failure_is_fail_soft(self) -> None:
        def _boom():
            raise RuntimeError("color engine unavailable")

        writer = self._make_writer(
            sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
            laser_status={"available": False, "enabled": False, "reason": "not_configured"},
            led_status={"available": False, "enabled": False, "reason": "not_configured"},
            color_provider=_boom,
        )

        snap = writer.snapshot()

        self.assertEqual(snap["heartbeat"]["palette"], "none")
        self.assertEqual(snap["heartbeat"]["rgb_health"], "not_configured")

    def test_safe_provider_failure_warning_is_throttled(self) -> None:
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        def _boom():
            raise RuntimeError("provider unavailable")

        logger = logging.getLogger("runtime_status")
        handler = _Capture()
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            provider_name = f"unit_provider_{id(self)}"
            _safe_provider_snapshot(
                _boom,
                provider_name=provider_name,
                default={"available": False, "reason": "not_configured"},
            )
            _safe_provider_snapshot(
                _boom,
                provider_name=provider_name,
                default={"available": False, "reason": "not_configured"},
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

        messages = [record.getMessage() for record in records]
        self.assertEqual(len(messages), 1)
        self.assertIn("unit_provider_", messages[0])

    def test_status_provider_failure_warnings_are_throttled(self) -> None:
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        def _boom():
            raise RuntimeError("provider unavailable")

        logger = logging.getLogger("runtime_status")
        handler = _Capture()
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            laser_writer = self._make_writer(
                sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
                laser_status={},
                laser_provider=_boom,
            )
            laser_writer.snapshot()
            laser_writer.snapshot()

            led_writer = self._make_writer(
                sm_snapshot={"active_deck": 1, "deck": {"1": {}, "2": {}}},
                laser_status={"available": False, "enabled": False, "reason": "not_configured"},
                led_provider=_boom,
            )
            led_writer.snapshot()
            led_writer.snapshot()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

        messages = [record.getMessage() for record in records]
        laser_messages = [
            message for message in messages
            if "laser_status_provider_failed" in message
        ]
        led_messages = [
            message for message in messages
            if "led_status_provider_failed" in message
        ]
        self.assertEqual(len(laser_messages), 1)
        self.assertEqual(len(led_messages), 1)


if __name__ == "__main__":
    unittest.main()
