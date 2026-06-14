from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_config import (  # noqa: E402
    load_led_look_director_config,
    load_led_look_director_config_from_dict,
)


_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


def _example_config() -> dict:
    return json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))


def _live_ready_base_config() -> dict:
    return {
        "schema_version": 1,
        "enabled": True,
        "dry_run": False,
        "automation_enabled": False,
        "targets": {
            "room_perimeter": {
                "label": "Strip Light",
                "device_ref": "local-device-ref-123",
                "expected_model": "H612D",
                "control_route": "govee_platform_dynamic_scene",
                "capabilities": ["scene", "off"],
            }
        },
        "looks": {
            "room_safe_default": {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": "Release-A",
                "fallback": "room_blackout",
                "safety_class": "safe",
                "brightness": 60,
                "allow_strobe": False,
            },
            "room_blackout": {
                "target": "room_perimeter",
                "action": "off",
                "fallback": "",
                "safety_class": "blackout",
                "brightness": 0,
                "allow_strobe": False,
            },
            "room_drop": {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": "Lightning-A",
                "fallback": "room_blackout",
                "safety_class": "drop",
                "brightness": 100,
                "allow_strobe": True,
            },
        },
        "banks": {
            "default": {
                "ambient": ["room_safe_default"],
                "groove": ["room_safe_default"],
                "buildup": ["room_safe_default"],
                "pre_drop": [],
                "drop": ["room_drop"],
                "post_drop": [],
                "breakdown": ["room_safe_default"],
                "utility": ["room_safe_default", "room_blackout"],
            }
        },
        "safe_default": "room_safe_default",
        "blackout": "room_blackout",
        "rate_limits": {
            "queue_maxsize": 8,
            "scene_retrigger_cooldown_s": 4.0,
            "high_impact_cooldown_s": 12.0,
            "request_timeout_s": 2.0,
            "worker_shutdown_timeout_s": 1.0,
        },
        "safety": {
            "max_brightness": 100,
            "allow_strobe": True,
            "max_strobe_duration_ms": 750,
            "high_impact_cooldown_s": 12.0,
            "drop_flash_duration_ms": 750,
            "emergency_blackout_always_available": True,
            "scripted_mode_automation": False,
        },
    }


class MissingInvalidConfigTests(unittest.TestCase):
    def test_missing_config_returns_not_configured(self) -> None:
        result = load_led_look_director_config("/definitely/not/found/led_look_director.json")
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "not_configured")
        self.assertEqual(result.errors, ())

    def test_invalid_json_returns_invalid_config(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{not valid json")
            path = fh.name
        result = load_led_look_director_config(path)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")
        self.assertTrue(result.errors)

    def test_non_object_root_returns_invalid_config(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("[]")
            path = fh.name
        result = load_led_look_director_config(path)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "invalid_config")


class ExampleConfigTests(unittest.TestCase):
    def test_example_file_exists(self) -> None:
        self.assertTrue(_EXAMPLE_PATH.exists())

    def test_example_file_loads(self) -> None:
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.reason, "ok")

    def test_example_defaults_are_phase_3_safe(self) -> None:
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        self.assertFalse(result.config.enabled)
        self.assertTrue(result.config.dry_run)
        self.assertFalse(result.config.automation_enabled)
        self.assertEqual(result.config.looks["room_safe_default"].action, "unmapped")

    def test_example_does_not_map_meteor_or_ambient(self) -> None:
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.banks["default"].ambient, ())
        self.assertEqual(result.config.safe_default, "room_blackout")
        self.assertNotIn("groove_meteor", result.config.looks)
        self.assertFalse(
            any(
                str(look.scene_ref).casefold() == "meteor"
                for look in result.config.looks.values()
            )
        )


class SecretKeyValidationTests(unittest.TestCase):
    def test_rejects_secret_like_top_level_key(self) -> None:
        cfg = _example_config()
        cfg["api_key"] = "never-allowed"
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("secret-like key" in err for err in result.errors))

    def test_rejects_secret_like_nested_key(self) -> None:
        cfg = _example_config()
        cfg["targets"]["room_perimeter"]["auth_header"] = "Bearer local-secret"
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("auth_header" in err for err in result.errors))


class LiveModeValidationTests(unittest.TestCase):
    def test_live_ready_base_config_is_valid(self) -> None:
        cfg = _live_ready_base_config()
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)

    def test_diy_scene_look_is_valid(self) -> None:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["capabilities"].append("diy_scene")
        cfg["looks"]["room_drop"]["action"] = "diy_scene"
        cfg["looks"]["room_drop"]["scene_ref"] = "23254201"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.looks["room_drop"].action, "diy_scene")

    def test_blackout_can_use_numeric_diy_scene(self) -> None:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["capabilities"].append("diy_scene")
        cfg["looks"]["room_blackout"]["action"] = "diy_scene"
        cfg["looks"]["room_blackout"]["scene_ref"] = "23259999"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.blackout, "room_blackout")
        self.assertEqual(result.config.looks["room_blackout"].action, "diy_scene")

    def test_blackout_can_use_named_diy_scene(self) -> None:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["capabilities"].append("diy_scene")
        cfg["looks"]["room_blackout"]["action"] = "diy_scene"
        cfg["looks"]["room_blackout"]["scene_ref"] = "BLACKOUT SCENE"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.looks["room_blackout"].action, "diy_scene")
        self.assertEqual(result.config.looks["room_blackout"].scene_ref, "BLACKOUT SCENE")

    def test_music_mode_look_is_valid(self) -> None:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["capabilities"].append("music_mode")
        cfg["looks"]["room_drop"]["action"] = "music_mode"
        cfg["looks"]["room_drop"]["scene_ref"] = "Rhythm:100:auto"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.looks["room_drop"].action, "music_mode")

    def test_music_mode_look_rejects_invalid_sensitivity(self) -> None:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["capabilities"].append("music_mode")
        cfg["looks"]["room_drop"]["action"] = "music_mode"
        cfg["looks"]["room_drop"]["scene_ref"] = "Rhythm:101:auto"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("sensitivity" in err for err in result.errors))

    def test_placeholder_scene_ref_rejected_when_not_dry_run(self) -> None:
        cfg = _live_ready_base_config()
        cfg["looks"]["room_drop"]["scene_ref"] = "operator_scene_name_or_id"
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("placeholder-like scene_ref" in err for err in result.errors))

    def test_placeholder_target_ref_rejected_when_not_dry_run(self) -> None:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["device_ref"] = "redacted-operator-local-id"
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("device_ref is placeholder-like" in err for err in result.errors))

    def test_example_unmapped_safe_default_rejected_when_not_dry_run(self) -> None:
        cfg = _example_config()
        cfg["enabled"] = True
        cfg["dry_run"] = False
        cfg["targets"]["room_perimeter"]["device_ref"] = "local-device-ref-123"
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("safe_default" in err for err in result.errors))

    def test_queue_maxsize_hard_cap_16(self) -> None:
        cfg = _live_ready_base_config()
        cfg["rate_limits"]["queue_maxsize"] = 17
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("queue_maxsize" in err for err in result.errors))

    def test_missing_bank_role_fails_validation(self) -> None:
        cfg = _live_ready_base_config()
        del cfg["banks"]["default"]["utility"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("missing role list 'utility'" in err for err in result.errors))


class RateLimitDefaultAndBoundsTests(unittest.TestCase):
    def test_rate_limit_defaults_applied_when_fields_missing(self) -> None:
        cfg = _live_ready_base_config()
        cfg["rate_limits"] = {}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.rate_limits.queue_maxsize, 8)
        self.assertEqual(result.config.rate_limits.scene_retrigger_cooldown_s, 4.0)
        self.assertEqual(result.config.rate_limits.high_impact_cooldown_s, 12.0)
        self.assertEqual(result.config.rate_limits.request_timeout_s, 2.0)
        self.assertEqual(result.config.rate_limits.worker_shutdown_timeout_s, 1.0)

    def test_automation_offset_defaults_to_zero(self) -> None:
        cfg = _live_ready_base_config()
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.automation.offset_s, 0.0)
        self.assertEqual(result.config.automation.cloud_offset_s, 0.0)
        self.assertEqual(result.config.automation.realtime_offset_s, 0.0)

    def test_automation_offset_s_parsed_when_configured(self) -> None:
        cfg = _live_ready_base_config()
        cfg["automation"] = {"offset_s": 1.0}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.automation.offset_s, 1.0)
        self.assertEqual(result.config.automation.cloud_offset_s, 1.0)
        self.assertEqual(result.config.automation.realtime_offset_s, 0.0)

    def test_split_automation_offsets_parse_when_configured(self) -> None:
        cfg = _live_ready_base_config()
        cfg["automation"] = {
            "cloud_offset_s": 0.6,
            "realtime_offset_s": 0.0,
        }
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.automation.offset_s, 0.6)
        self.assertEqual(result.config.automation.cloud_offset_s, 0.6)
        self.assertEqual(result.config.automation.realtime_offset_s, 0.0)

    def test_automation_offset_s_rejects_negative(self) -> None:
        cfg = _live_ready_base_config()
        cfg["automation"] = {"offset_s": -0.5}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("automation.offset_s" in err for err in result.errors))

    def test_split_automation_offsets_reject_negative(self) -> None:
        cfg = _live_ready_base_config()
        cfg["automation"] = {
            "cloud_offset_s": -0.5,
            "realtime_offset_s": -0.1,
        }
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("automation.cloud_offset_s" in err for err in result.errors))
        self.assertTrue(any("automation.realtime_offset_s" in err for err in result.errors))

    def test_supports_high_impact_cooldown_12_when_configured(self) -> None:
        cfg = _live_ready_base_config()
        cfg["rate_limits"]["high_impact_cooldown_s"] = 12.0
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.rate_limits.high_impact_cooldown_s, 12.0)

    def test_request_timeout_must_be_positive(self) -> None:
        cfg = _live_ready_base_config()
        cfg["rate_limits"]["request_timeout_s"] = 0.0
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("request_timeout_s" in err for err in result.errors))

    def test_drop_flash_duration_respects_750ms_cap(self) -> None:
        cfg = _live_ready_base_config()
        cfg["safety"]["drop_flash_duration_ms"] = 751
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("drop_flash_duration_ms" in err for err in result.errors))


class RealtimeConfigTests(unittest.TestCase):
    def _realtime_config(self) -> dict:
        cfg = _live_ready_base_config()
        cfg["targets"]["room_perimeter"]["capabilities"].append("diy_scene")
        cfg["targets"]["room_perimeter"]["realtime"] = {
            "enabled": True,
            "protocol": "razer_dreamview",
            "ip": "192.168.0.219",
            "port": 4003,
            "segments": 20,
            "header": "dreams",
            "header_bytes": [187, 0, 250, 176, 0],
            "stretch": False,
            "fps": 30,
            "activate_pt": "uwABsQEK",
            "deactivate_pt": "uwABsQAL",
            "proof_status": "confirmed_visual_pass",
        }
        cfg["looks"]["rt_groove_chase_blue"] = {
            "target": "room_perimeter",
            "action": "realtime",
            "scene_ref": "groove_chase_blue",
            "fallback": "rt_blackout",
            "safety_class": "groove",
            "brightness": 100,
            "allow_strobe": False,
            "backend": "realtime_razer",
            "params": {},
        }
        cfg["looks"]["rt_drop_chase_blue"] = {
            "target": "room_perimeter",
            "action": "realtime",
            "scene_ref": "drop_chase_blue",
            "fallback": "rt_blackout",
            "safety_class": "drop",
            "brightness": 100,
            "allow_strobe": True,
            "backend": "realtime_razer",
            "params": {},
        }
        cfg["looks"]["rt_blackout"] = {
            "target": "room_perimeter",
            "action": "realtime",
            "scene_ref": "blackout",
            "fallback": "",
            "safety_class": "blackout",
            "brightness": 0,
            "allow_strobe": False,
            "backend": "realtime_razer",
            "params": {},
        }
        cfg["banks"]["default"]["groove"].append("rt_groove_chase_blue")
        cfg["banks"]["default"]["drop"].append("rt_drop_chase_blue")
        return cfg

    def test_realtime_config_loads_and_preserves_backend_fields(self) -> None:
        cfg = self._realtime_config()

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        target = result.config.targets["room_perimeter"]
        self.assertTrue(target.realtime.enabled)
        self.assertEqual(target.realtime.header_bytes, (187, 0, 250, 176, 0))
        self.assertEqual(result.config.looks["rt_groove_chase_blue"].backend, "realtime_razer")
        self.assertEqual(result.config.looks["rt_drop_chase_blue"].scene_ref, "drop_chase_blue")

    def test_mixed_cloud_and_realtime_role_lists_are_valid(self) -> None:
        cfg = self._realtime_config()

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertIn("room_safe_default", result.config.banks["default"].groove)
        self.assertIn("rt_groove_chase_blue", result.config.banks["default"].groove)
        self.assertIn("room_drop", result.config.banks["default"].drop)
        self.assertIn("rt_drop_chase_blue", result.config.banks["default"].drop)

    def test_realtime_look_requires_realtime_enabled_target(self) -> None:
        cfg = self._realtime_config()
        cfg["targets"]["room_perimeter"]["realtime"]["enabled"] = False

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("realtime.enabled=false" in err for err in result.errors))

    def test_realtime_params_reject_unknown_keys(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"colour": [1, 2, 3]}

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("params.colour" in err for err in result.errors))

    def test_safety_blackout_must_remain_cloud(self) -> None:
        cfg = self._realtime_config()
        cfg["blackout"] = "rt_blackout"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("'blackout' must reference a cloud_diy look" in err for err in result.errors))


if __name__ == "__main__":
    unittest.main()
