from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_config import load_led_look_director_config_from_dict  # noqa: E402
from rb_ss_bridge_v2.led_look_director import LEDLookDirector  # noqa: E402
from rb_ss_bridge_v2.led_models import LEDContext  # noqa: E402


def _director_config(enabled: bool = True) -> dict:
    return {
        "schema_version": 1,
        "enabled": enabled,
        "dry_run": True,
        "automation_enabled": False,
        "targets": {
            "room_perimeter": {
                "label": "Strip Light",
                "device_ref": "redacted-operator-local-strip-light-id",
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
                "brightness": 50,
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
            "room_manual": {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": "Meteor",
                "fallback": "room_blackout",
                "safety_class": "manual",
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
                "drop": ["room_manual"],
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
            "high_impact_cooldown_s": 4.0,
            "request_timeout_s": 2.0,
            "worker_shutdown_timeout_s": 1.0,
        },
        "safety": {
            "max_brightness": 100,
            "allow_strobe": True,
            "max_strobe_duration_ms": 750,
            "high_impact_cooldown_s": 4.0,
            "drop_flash_duration_ms": 750,
            "emergency_blackout_always_available": True,
            "scripted_mode_automation": False,
        },
    }


class LEDLookDirectorPriorityTests(unittest.TestCase):
    def _build_director(self, enabled: bool = True) -> LEDLookDirector:
        cfg = copy.deepcopy(_director_config(enabled=enabled))
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        return LEDLookDirector(result.config)

    def test_disabled_returns_none(self) -> None:
        director = self._build_director(enabled=False)
        decision = director.tick(LEDContext(role="drop"))
        self.assertIsNone(decision)
        status = director.status()
        self.assertEqual(status["last_reason"], "disabled")

    def test_default_safe_decision_when_no_manual_or_emergency(self) -> None:
        director = self._build_director()
        decision = director.tick(LEDContext(role="drop"))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.look, "room_safe_default")
        self.assertEqual(decision.source, "policy")

    def test_manual_override_beats_default(self) -> None:
        director = self._build_director()
        self.assertTrue(director.set_manual_override("room_manual"))
        decision = director.tick(LEDContext(role="ambient"))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.look, "room_manual")
        self.assertEqual(decision.source, "manual")

    def test_manual_target_override_routes_to_named_target(self) -> None:
        cfg = _director_config()
        cfg["targets"]["strip_light_mirror"] = {
            "label": "Strip Light",
            "device_ref": "local-device-ref-456",
            "expected_model": "H612D",
            "control_route": "govee_platform_dynamic_scene",
            "capabilities": ["scene", "off"],
        }
        loaded = load_led_look_director_config_from_dict(cfg)
        director = LEDLookDirector(loaded.config)
        self.assertTrue(director.set_manual_override("room_manual"))
        decision = director.tick(
            LEDContext(role="manual", target_override="strip_light_mirror")
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.target, "strip_light_mirror")

    def test_emergency_blackout_beats_manual(self) -> None:
        director = self._build_director()
        self.assertTrue(director.set_manual_override("room_manual"))
        director.set_emergency_blackout(True)
        decision = director.tick(LEDContext(role="drop"))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.look, "room_blackout")
        self.assertEqual(decision.source, "emergency")
        self.assertEqual(decision.priority, 0)

    def test_context_emergency_blackout_beats_stored_state(self) -> None:
        director = self._build_director()
        self.assertTrue(director.set_manual_override("room_manual"))
        decision = director.tick(
            LEDContext(role="drop", manual_look="room_manual", emergency_blackout=True)
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.look, "room_blackout")
        self.assertEqual(decision.source, "emergency")

    def test_empty_ambient_bank_returns_no_automation_decision(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["banks"]["default"]["ambient"] = []
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)

        decision = director.tick(LEDContext(role="ambient"))

        self.assertIsNone(decision)
        self.assertEqual(director.status()["last_reason"], "automation_no_look:ambient")

    def test_unknown_manual_override_returns_safe_default(self) -> None:
        director = self._build_director()
        self.assertFalse(director.set_manual_override("missing-look"))
        decision = director.tick(LEDContext(role="drop"))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.look, "room_safe_default")

    def test_status_contains_manual_and_emergency_flags(self) -> None:
        director = self._build_director()
        director.set_manual_override("room_manual")
        director.set_emergency_blackout(True)
        director.tick(LEDContext(role="groove"))
        status = director.status()
        self.assertEqual(status["manual_override"], "room_manual")
        self.assertTrue(status["emergency_blackout"])
        self.assertEqual(status["current_look"], "room_blackout")

    def test_preview_role_does_not_advance_cursor(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["targets"]["room_perimeter"]["realtime"] = {
            "enabled": True,
            "protocol": "razer_dreamview",
            "ip": "192.168.0.219",
            "port": 4003,
            "segments": 20,
            "header_bytes": [187, 0, 250, 176, 0],
            "fps": 30,
            "activate_pt": "uwABsQEK",
            "deactivate_pt": "uwABsQAL",
        }
        cfg["looks"]["rt_drop_blue"] = {
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
        cfg["banks"]["default"]["drop"] = ["rt_drop_blue", "room_manual"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)

        preview = director.preview_role("drop")
        decision = director.tick(LEDContext(role="drop"))

        self.assertIsNotNone(preview)
        self.assertIsNotNone(decision)
        self.assertEqual(preview.look, "rt_drop_blue")
        self.assertEqual(decision.look, "rt_drop_blue")
        self.assertEqual(decision.backend, "realtime_razer")


if __name__ == "__main__":
    unittest.main()
