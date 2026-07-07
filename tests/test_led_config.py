from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import REALTIME_EFFECT_NAMES  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import REALTIME_STROBE_EFFECTS  # noqa: E402
from rb_ss_bridge_v2.led_config import (  # noqa: E402
    load_drop_presentation_config,
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


class DropPresentationConfigLoaderTests(unittest.TestCase):
    """led_config.load_drop_presentation_config: same path/env resolution as
    load_led_look_director_config, but fully independent of its validate/build
    pipeline -- an unrelated looks/banks error there must never block this."""

    def test_missing_file_degrades_to_defaults(self) -> None:
        cfg = load_drop_presentation_config("/definitely/not/found/led_look_director.json")
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.hotcue_marker, "LASER")

    def test_invalid_json_degrades_to_defaults_rather_than_raising(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{not valid json")
            path = fh.name
        cfg = load_drop_presentation_config(path)
        self.assertTrue(cfg.enabled)

    def test_reads_the_block_independent_of_an_unrelated_validation_error(self) -> None:
        # A config missing required top-level keys (targets/looks/etc.) fails
        # load_led_look_director_config's validation entirely -- but the
        # drop_presentation block must still be readable from the same file.
        data = {"drop_presentation": {"enabled": False, "hotcue_marker": "LZR"}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(data, fh)
            path = fh.name
        broken = load_led_look_director_config(path)
        self.assertFalse(broken.available)
        cfg = load_drop_presentation_config(path)
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.hotcue_marker, "LZR")

    def test_example_file_carries_the_documented_defaults(self) -> None:
        cfg = load_drop_presentation_config(str(_EXAMPLE_PATH))
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.laser_ratio, 0.4)
        self.assertEqual(cfg.opening_tracks, 3)
        self.assertEqual(cfg.led_predark_beats, 4)
        self.assertEqual(cfg.drop_window_cap_beats, 192)
        self.assertEqual(cfg.hotcue_marker, "LASER")
        self.assertEqual(cfg.gearshift_bpm_jump, 10)
        self.assertEqual(cfg.record_min_drops, 5)
        self.assertFalse(cfg.ws_handoff_enabled)


class ExampleConfigTests(unittest.TestCase):
    def test_example_file_exists(self) -> None:
        self.assertTrue(_EXAMPLE_PATH.exists())

    def test_example_file_loads(self) -> None:
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.reason, "ok")

    def test_example_defaults_support_color_engine_automation(self) -> None:
        """The example config now enables automation by default for the color-engine."""
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        self.assertFalse(result.config.enabled)
        self.assertTrue(result.config.dry_run)
        self.assertTrue(result.config.automation_enabled)
        self.assertNotIn("room_safe_default", result.config.looks)

    def test_example_maps_ambient_for_color_engine(self) -> None:
        """The example config now maps ambient roles for color-engine support."""
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(
            result.config.banks["default"].ambient,
            ("ambient_pb_halves", "rt_twinkle")
        )
        self.assertIn("rt_twinkle_blue", result.config.banks["legacy_color_suffix"].ambient)
        self.assertEqual(result.config.looks["rt_twinkle"].color_source, "engine")
        self.assertEqual(result.config.safe_default, "room_blackout")
        self.assertNotIn("groove_meteor", result.config.looks)
        self.assertFalse(
            any(
                str(look.scene_ref).casefold() == "meteor"
                for look in result.config.looks.values()
            )
        )


class ScriptedModePolicyConfigTests(unittest.TestCase):
    def test_absent_scripted_mode_uses_conservative_default(self) -> None:
        cfg = _live_ready_base_config()
        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.scripted_mode.default_role, "breakdown")
        self.assertEqual(result.config.scripted_mode.role_map["groove"], "utility")
        self.assertEqual(result.config.scripted_mode.role_map["drop"], "utility")
        self.assertEqual(result.config.scripted_mode.role_map["post_drop"], "utility")
        self.assertEqual(result.config.scripted_mode.role_map["buildup"], "buildup")

    def test_scripted_mode_must_be_object(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = 5
        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("'scripted_mode' must be an object" in err for err in result.errors))

    def test_scripted_mode_rejects_utility_default_role(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"default_role": "utility"}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("must be one of" in err for err in result.errors))

    def test_scripted_mode_role_map_must_be_object(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"role_map": []}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("'scripted_mode.role_map' must be an object" in err for err in result.errors))

    def test_scripted_mode_rejects_invalid_source_role(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"role_map": {"chorus": "breakdown"}}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("invalid source role" in err for err in result.errors))

    def test_scripted_mode_accepts_utility_as_off_destination(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"role_map": {"groove": "utility"}}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.scripted_mode.role_map["groove"], "utility")

    def test_scripted_mode_rejects_invalid_destination_role(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"role_map": {"groove": "chorus"}}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("invalid destination role" in err for err in result.errors))

    def test_scripted_mode_rejects_utility_source_role(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"role_map": {"utility": "breakdown"}}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("invalid source role" in err for err in result.errors))

    def test_scripted_mode_partial_map_is_allowed(self) -> None:
        cfg = _live_ready_base_config()
        cfg["scripted_mode"] = {"role_map": {"groove": "groove"}}
        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(result.config.scripted_mode.default_role, "breakdown")
        self.assertEqual(dict(result.config.scripted_mode.role_map), {"groove": "groove"})


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
        # Force safe_default to be unmapped to test the rejection logic
        cfg["looks"][cfg["safe_default"]]["action"] = "unmapped"
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

    def test_realtime_param_profile_expands_into_look_params(self) -> None:
        cfg = self._realtime_config()
        cfg["realtime_param_profiles"] = {
            "beat_chase_reset": {
                "sync_mode": "retrigger",
                "beat_division": 1.0,
                "travel_beats": 1.0,
                "trail_beats": 0.25,
                "width": 0.8,
            }
        }
        cfg["looks"]["rt_groove_chase_blue"]["param_profile"] = "beat_chase_reset"
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"travel_beats": 2.0}

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        params = result.config.looks["rt_groove_chase_blue"].params
        self.assertEqual(params["sync_mode"], "retrigger")
        self.assertEqual(params["beat_division"], 1.0)
        self.assertEqual(params["travel_beats"], 2.0)
        self.assertEqual(params["trail_beats"], 0.25)
        self.assertEqual(params["width"], 0.8)

    def test_drop_pair_config_loads_duration_and_post_drop(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_post_drop_chase_blue"] = {
            "target": "room_perimeter",
            "action": "realtime",
            "scene_ref": "post_drop_chase_blue",
            "fallback": "rt_blackout",
            "safety_class": "post_drop",
            "brightness": 100,
            "allow_strobe": True,
            "backend": "realtime_razer",
            "params": {},
        }
        cfg["banks"]["default"]["post_drop"] = ["rt_post_drop_chase_blue"]
        cfg["drop_pairs"] = {
            "rt_drop_chase_blue": {
                "post_drop": "rt_post_drop_chase_blue",
                "duration_beats": 8.0,
            }
        }
        cfg["post_drop_cycle_beats"] = 32.0

        result = load_led_look_director_config_from_dict(cfg)

        self.assertTrue(result.available, msg=result.errors)
        pair = result.config.drop_pairs["rt_drop_chase_blue"]
        self.assertEqual(pair.post_drop, "rt_post_drop_chase_blue")
        self.assertEqual(pair.duration_beats, 8.0)
        self.assertEqual(result.config.post_drop_cycle_beats, 32.0)

    def test_drop_pair_unknown_post_drop_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["drop_pairs"] = {
            "rt_drop_chase_blue": {
                "post_drop": "missing_post_drop",
                "duration_beats": 8.0,
            }
        }

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("missing_post_drop" in err for err in result.errors))

    def test_drop_pair_duration_must_be_positive(self) -> None:
        cfg = self._realtime_config()
        cfg["drop_pairs"] = {
            "rt_drop_chase_blue": {
                "post_drop": "rt_drop_chase_blue",
                "duration_beats": 0,
            }
        }

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("duration_beats" in err for err in result.errors))

    def test_unknown_realtime_param_profile_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["param_profile"] = "missing_profile"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("unknown profile 'missing_profile'" in err for err in result.errors))

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

    def test_realtime_header_bytes_must_be_five_long(self) -> None:
        cfg = self._realtime_config()
        cfg["targets"]["room_perimeter"]["realtime"]["header_bytes"] = [187, 0, 250, 176]

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("header_bytes must be exactly 5 bytes" in err for err in result.errors))

    def test_realtime_floor_param_above_one_is_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["scene_ref"] = "breathe"
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"floor": 2.0}

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("params.floor must be between 0 and 1" in err for err in result.errors))

    def test_safety_blackout_must_remain_cloud(self) -> None:
        cfg = self._realtime_config()
        cfg["blackout"] = "rt_blackout"

        result = load_led_look_director_config_from_dict(cfg)

        self.assertFalse(result.available)
        self.assertTrue(any("'blackout' must reference a cloud_diy look" in err for err in result.errors))

    def test_sync_params_accepted_on_all_realtime_effects(self) -> None:
        sync_params = {
            "sync_mode": "continuous",
            "beat_division": 1.0,
            "travel_beats": 1.0,
            "width": 0.8,
            "trail_beats": 0.25,
            "heads": 1,
            "max_pulses": 8,
            "spawn_on_wrap": False,
            "reverse": False,
        }
        for effect_name in sorted(REALTIME_EFFECT_NAMES):
            cfg = self._realtime_config()
            cfg["looks"]["rt_groove_chase_blue"]["scene_ref"] = effect_name
            cfg["looks"]["rt_groove_chase_blue"]["params"] = dict(sync_params)
            if effect_name in REALTIME_STROBE_EFFECTS:
                cfg["looks"]["rt_groove_chase_blue"]["allow_strobe"] = True
            result = load_led_look_director_config_from_dict(cfg)
            self.assertTrue(result.available, msg=f"{effect_name}: {result.errors}")

    def test_sync_mode_bogus_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"sync_mode": "bogus"}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("sync_mode must be one of" in err for err in result.errors))

    def test_beat_division_zero_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"beat_division": 0}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("beat_division must be a number > 0" in err for err in result.errors))

    def test_travel_beats_zero_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"travel_beats": 0}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("travel_beats must be a number > 0" in err for err in result.errors))

    def test_width_zero_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"width": 0}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("width must be a number > 0" in err for err in result.errors))

    def test_slot_cue_positive_beat_params_accept_numbers(self) -> None:
        cases = [
            ("groove_center_burst_retract", {"burst_beats": 1.0}),
            ("breakdown_full_breathing", {"breath_beats": 2.0, "drift_beats": 4.0}),
        ]
        for scene_ref, params in cases:
            cfg = self._realtime_config()
            cfg["looks"]["rt_groove_chase_blue"]["scene_ref"] = scene_ref
            cfg["looks"]["rt_groove_chase_blue"]["params"] = params
            result = load_led_look_director_config_from_dict(cfg)
            self.assertTrue(result.available, msg=f"{scene_ref}: {result.errors}")

    def test_burst_beats_string_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["scene_ref"] = "groove_center_burst_retract"
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"burst_beats": "1"}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("burst_beats must be a number > 0" in err for err in result.errors))

    def test_breath_beats_string_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["scene_ref"] = "breakdown_full_breathing"
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"breath_beats": "1"}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("breath_beats must be a number > 0" in err for err in result.errors))

    def test_drift_beats_string_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["scene_ref"] = "breakdown_full_breathing"
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"drift_beats": "1"}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("drift_beats must be a number > 0" in err for err in result.errors))

    def test_max_pulses_zero_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"max_pulses": 0}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("max_pulses must be an integer >= 1" in err for err in result.errors))

    def test_spawn_on_wrap_non_bool_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"spawn_on_wrap": "yes"}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("spawn_on_wrap must be a boolean" in err for err in result.errors))

    def test_reverse_non_bool_rejected(self) -> None:
        cfg = self._realtime_config()
        cfg["looks"]["rt_groove_chase_blue"]["params"] = {"reverse": 1}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available)
        self.assertTrue(any("reverse must be a boolean" in err for err in result.errors))

    def test_live_json_still_validates_clean(self) -> None:
        live_path = Path(__file__).resolve().parents[1] / "config" / "led_look_director.json"
        if not live_path.is_file():
            self.skipTest("live config not present in this checkout")
        result = load_led_look_director_config(str(live_path))
        self.assertTrue(result.available, msg=result.errors)
        self.assertEqual(
            result.config.drop_pairs["rt_drop_chase_freestyle_nebula"].post_drop,
            "rt_post_drop_freestyle_nebula",
        )
        self.assertIn(
            "rt_post_drop_freestyle_nebula",
            result.config.banks["default"].post_drop,
        )


if __name__ == "__main__":
    unittest.main()
