from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_runtime_sender import GoveeRuntimeSender  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config_from_dict  # noqa: E402
from rb_ss_bridge_v2.led_models import LEDAdapterCommand  # noqa: E402


def _config(*, mirrored: bool = False) -> dict:
    targets = {
        "room_perimeter": {
            "label": "Strip Light",
            "device_ref": "local-device-1",
            "expected_model": "H612D",
            "control_route": "govee_platform_dynamic_scene",
            "capabilities": ["scene", "music_mode", "off"],
        }
    }
    if mirrored:
        targets["room_perimeter"]["mirror_targets"] = ["room_mirror"]
        targets["room_mirror"] = {
            "label": "Mirror Strip",
            "device_ref": "local-device-2",
            "expected_model": "H612D",
            "control_route": "govee_platform_dynamic_scene",
            "capabilities": ["scene", "music_mode", "off"],
        }
    return {
        "schema_version": 1,
        "enabled": True,
        "dry_run": False,
        "automation_enabled": True,
        "targets": targets,
        "looks": {
            "room_safe_default": {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": "Meteor",
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
        },
        "banks": {
            "default": {
                "ambient": ["room_safe_default"],
                "groove": ["room_safe_default"],
                "buildup": ["room_safe_default"],
                "pre_drop": [],
                "drop": ["room_safe_default"],
                "post_drop": [],
                "breakdown": ["room_safe_default"],
                "utility": ["room_safe_default", "room_blackout"],
            }
        },
        "safe_default": "room_safe_default",
        "blackout": "room_blackout",
        "rate_limits": {
            "queue_maxsize": 8,
            "scene_retrigger_cooldown_s": 0.0,
            "high_impact_cooldown_s": 0.0,
            "request_timeout_s": 2.0,
            "worker_shutdown_timeout_s": 1.0,
        },
        "safety": {
            "max_brightness": 100,
            "allow_strobe": True,
            "max_strobe_duration_ms": 750,
            "high_impact_cooldown_s": 0.0,
            "drop_flash_duration_ms": 750,
            "emergency_blackout_always_available": True,
            "scripted_mode_automation": False,
        },
    }


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self) -> int:
        return 200

    def read(self) -> bytes:
        return json.dumps({"code": 200, "msg": "success"}).encode("utf-8")


class GoveeRuntimeSenderTests(unittest.TestCase):
    def _build_sender(self, *, urlopen, mirrored: bool = False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        devices = {
            "data": [
                {
                    "sku": "H612D",
                    "device": "local-device-1",
                    "deviceName": "Strip Light",
                    "capabilities": [
                        {
                            "type": "devices.capabilities.on_off",
                            "instance": "powerSwitch",
                            "parameters": {
                                "options": [
                                    {"name": "on", "value": 1},
                                    {"name": "off", "value": 0},
                                ]
                            },
                        }
                    ],
                }
            ]
        }
        if mirrored:
            devices["data"].append(
                {
                    "sku": "H612D",
                    "device": "local-device-2",
                    "deviceName": "Mirror Strip",
                    "capabilities": [
                        {
                            "type": "devices.capabilities.on_off",
                            "instance": "powerSwitch",
                            "parameters": {
                                "options": [
                                    {"name": "on", "value": 1},
                                    {"name": "off", "value": 0},
                                ]
                            },
                        }
                    ],
                }
            )
        scenes = {
            "scene_attempts": [
                {
                    "target": {"sku": "H612D", "device": "local-device-1"},
                    "response": {
                        "payload": {
                            "capabilities": [
                                {
                                    "type": "devices.capabilities.dynamic_scene",
                                    "instance": "lightScene",
                                    "parameters": {
                                        "options": [
                                            {
                                                "name": "Meteor",
                                                "value": {"id": 133, "paramId": 15953},
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    },
                }
            ]
        }
        if mirrored:
            scenes["scene_attempts"].append(
                {
                    "target": {"sku": "H612D", "device": "local-device-2"},
                    "response": {
                        "payload": {
                            "capabilities": [
                                {
                                    "type": "devices.capabilities.dynamic_scene",
                                    "instance": "lightScene",
                                    "parameters": {
                                        "options": [
                                            {
                                                "name": "Meteor",
                                                "value": {"id": 233, "paramId": 25953},
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    },
                }
            )
        devices_path = root / "devices.json"
        scenes_path = root / "scenes.json"
        devices_path.write_text(json.dumps(devices), encoding="utf-8")
        scenes_path.write_text(json.dumps(scenes), encoding="utf-8")
        loaded = load_led_look_director_config_from_dict(_config(mirrored=mirrored))
        self.assertTrue(loaded.available, msg=loaded.errors)
        return GoveeRuntimeSender(
            loaded.config,
            api_key="unit-test-key",
            devices_path=devices_path,
            scenes_path=scenes_path,
            urlopen=urlopen,
        )

    @staticmethod
    def _scene_command() -> LEDAdapterCommand:
        return LEDAdapterCommand(
            look="room_safe_default",
            target="room_perimeter",
            action="scene",
            scene_ref="Meteor",
            reason="role_entry:groove",
            source="automation",
            role="groove",
        )

    def test_scene_command_posts_dynamic_scene_payload(self) -> None:
        captured = {}

        def _urlopen(req, timeout):
            captured["timeout"] = timeout
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["api_key"] = req.get_header("Govee-api-key")
            return _Response()

        sender = self._build_sender(urlopen=_urlopen)
        result = sender.send(
            LEDAdapterCommand(
                look="room_safe_default",
                target="room_perimeter",
                action="scene",
                scene_ref="Meteor",
                reason="role_entry:groove",
                source="automation",
                role="groove",
            ),
            timeout_s=1.5,
        )

        self.assertTrue(result["ok"])
        capability = captured["body"]["payload"]["capability"]
        self.assertEqual(capability["type"], "devices.capabilities.dynamic_scene")
        self.assertEqual(capability["instance"], "lightScene")
        self.assertEqual(capability["value"], {"id": 133, "paramId": 15953})
        self.assertEqual(captured["api_key"], "unit-test-key")

    def test_mirror_send_logs_only_on_failure_and_recovery_edges(self) -> None:
        sender = self._build_sender(
            mirrored=True,
            urlopen=lambda *_args, **_kwargs: self.fail("network called"),
        )
        results = iter(
            [
                {"ok": True},
                {"ok": False, "error": "api_code:500"},
                {"ok": True},
                {"ok": False, "error": "api_code:500"},
                {"ok": False, "error": "primary_down"},
                {"ok": True},
            ]
        )

        with patch.object(sender, "_send_to_target", side_effect=lambda *_args, **_kwargs: next(results)):
            with self.assertLogs("govee_runtime_sender", level="WARNING") as warning_logs:
                first = sender.send(self._scene_command(), timeout_s=1.0)
                second = sender.send(self._scene_command(), timeout_s=1.0)
            with self.assertLogs("govee_runtime_sender", level="INFO") as info_logs:
                third = sender.send(self._scene_command(), timeout_s=1.0)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(third, {"ok": False, "error": "primary_down"})
        self.assertEqual(
            warning_logs.output,
            ["WARNING:govee_runtime_sender:[RGB] mirror-send-degraded target=room_mirror err=api_code:500"],
        )
        self.assertEqual(
            info_logs.output,
            ["INFO:govee_runtime_sender:[RGB] mirror-send-recovered target=room_mirror"],
        )
        self.assertEqual(sender.status()["mirror_send_ok"], {"room_mirror": True})

    def test_missing_api_key_raises_before_network(self) -> None:
        sender = self._build_sender(urlopen=lambda *_args, **_kwargs: self.fail("network called"))
        sender._api_key = ""
        with self.assertRaisesRegex(RuntimeError, "missing_govee_api_key"):
            sender.send(
                LEDAdapterCommand(
                    look="room_safe_default",
                    target="room_perimeter",
                    action="scene",
                    scene_ref="Meteor",
                    reason="role_entry:groove",
                    source="automation",
                    role="groove",
                ),
                timeout_s=1.0,
            )

    def test_music_mode_command_posts_max_sensitivity_payload(self) -> None:
        captured = {}

        def _urlopen(req, timeout):
            captured["timeout"] = timeout
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _Response()

        sender = self._build_sender(urlopen=_urlopen)
        result = sender.send(
            LEDAdapterCommand(
                look="room_music",
                target="room_perimeter",
                action="music_mode",
                scene_ref="Rhythm:100:auto",
                reason="role_entry:drop",
                source="automation",
                role="drop",
            ),
            timeout_s=1.0,
        )

        self.assertTrue(result["ok"])
        capability = captured["body"]["payload"]["capability"]
        self.assertEqual(capability["type"], "devices.capabilities.music_setting")
        self.assertEqual(capability["instance"], "musicMode")
        self.assertEqual(
            capability["value"],
            {"musicMode": 0, "sensitivity": 100, "autoColor": 1},
        )


if __name__ == "__main__":
    unittest.main()
