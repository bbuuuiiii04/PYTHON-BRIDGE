from __future__ import annotations

import copy
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_config import load_led_look_director_config_from_dict  # noqa: E402
from rb_ss_bridge_v2.led_look_director import (  # noqa: E402
    LEDLookDirector,
    LED_AUTOMATION_ROLE_ORDER,
)
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

    def test_commit_role_filters_diy_eligibility_like_tick(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["looks"]["room_second"] = copy.deepcopy(cfg["looks"]["room_manual"])
        cfg["banks"]["default"]["drop"] = ["room_manual", "room_second"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)
        director._role_cursors["drop"] = 0

        decision = director.commit_role(
            "drop",
            diy_eligible=lambda name: name == "room_second",
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.look, "room_second")

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
        director._role_cursors["drop"] = 0

        preview = director.preview_role("drop")
        decision = director.tick(LEDContext(role="drop"))

        self.assertIsNotNone(preview)
        self.assertIsNotNone(decision)
        self.assertEqual(preview.look, "rt_drop_blue")
        self.assertEqual(decision.look, "rt_drop_blue")
        self.assertEqual(decision.backend, "realtime_razer")

    def test_has_role_look_does_not_mutate_shuffled_role_state(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["banks"]["default"]["drop"] = ["room_blackout", "room_manual"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config, shuffled_roles=("drop",))
        director._role_cursors["drop"] = 0

        self.assertTrue(director.has_role_look("drop"))
        self.assertEqual(director._role_shuffle_bags, {})
        self.assertEqual(director._role_cursors["drop"], 0)
        self.assertFalse(director.has_role_look("missing"))

    def test_paired_drop_queues_exact_post_drop_once(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["looks"]["room_post_drop"] = {
            "target": "room_perimeter",
            "action": "scene",
            "scene_ref": "PostDrop-A",
            "fallback": "room_blackout",
            "safety_class": "post_drop",
            "brightness": 80,
            "allow_strobe": False,
        }
        cfg["banks"]["default"]["post_drop"] = ["room_safe_default"]
        cfg["drop_pairs"] = {
            "room_manual": {
                "post_drop": "room_post_drop",
                "duration_beats": 8.0,
            }
        }
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)

        drop = director.tick(LEDContext(role="drop"))
        preview = director.preview_role("post_drop")
        paired = director.tick(LEDContext(role="post_drop"))
        next_generic = director.tick(LEDContext(role="post_drop"))

        self.assertIsNotNone(drop)
        self.assertEqual(drop.look, "room_manual")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.look, "room_post_drop")
        self.assertIsNotNone(paired)
        self.assertEqual(paired.look, "room_post_drop")
        self.assertEqual(paired.reason, "paired_post_drop")
        self.assertIsNotNone(next_generic)
        self.assertEqual(next_generic.look, "room_safe_default")

    def test_preview_role_does_not_mutate_shuffled_state(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["banks"]["default"]["drop"] = ["room_blackout", "room_manual"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config, shuffled_roles=("drop",))
        director._role_cursors["drop"] = 0
        rng_state_before = director._rng.getstate()

        preview = director.preview_role("drop")

        self.assertIsNotNone(preview)
        # Preview must not build a shuffle bag or advance the RNG; otherwise it
        # would change which look the next real drop tick selects.
        self.assertEqual(director._role_shuffle_bags, {})
        self.assertEqual(director._rng.getstate(), rng_state_before)
        self.assertEqual(director._role_cursors["drop"], 0)

    def test_every_automation_role_can_use_shuffle_bag(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        for role in LED_AUTOMATION_ROLE_ORDER:
            cfg["banks"]["default"][role] = ["room_safe_default", "room_manual"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(
            result.config,
            rng=random.Random(1),
            shuffled_roles=LED_AUTOMATION_ROLE_ORDER,
        )

        for role in LED_AUTOMATION_ROLE_ORDER:
            with self.subTest(role=role):
                director._role_cursors[role] = 0
                director._role_shuffle_bags.pop(role, None)

                decision = director.tick(LEDContext(role=role))

                self.assertIsNotNone(decision)
                self.assertIn(role, director._role_shuffle_bags)
                self.assertEqual(director._role_cursors[role], 1)

    def test_shuffled_preview_matches_next_real_drop_without_existing_bag(self) -> None:
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
        for seed in range(10):
            with self.subTest(seed=seed):
                director = LEDLookDirector(
                    result.config,
                    rng=random.Random(seed),
                    shuffled_roles=("drop",),
                )
                director._role_cursors["drop"] = 0

                preview = director.preview_role("drop")
                decision = director.tick(LEDContext(role="drop"))

                self.assertIsNotNone(preview)
                self.assertIsNotNone(decision)
                self.assertEqual(preview.look, decision.look)
                self.assertEqual(preview.backend, decision.backend)
                self.assertEqual(director._role_cursors["drop"], 1)

    def test_shuffled_preview_matches_next_real_drop_at_bag_boundary(self) -> None:
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
        for seed in range(10):
            with self.subTest(seed=seed):
                director = LEDLookDirector(
                    result.config,
                    rng=random.Random(seed),
                    shuffled_roles=("drop",),
                )
                director._role_cursors["drop"] = 2
                director._role_shuffle_bags["drop"] = ("rt_drop_blue", "room_manual")

                preview = director.preview_role("drop")
                decision = director.tick(LEDContext(role="drop"))

                self.assertIsNotNone(preview)
                self.assertIsNotNone(decision)
                self.assertEqual(preview.look, decision.look)
                self.assertEqual(preview.backend, decision.backend)
                self.assertEqual(director._role_cursors["drop"], 3)

    def test_commit_role_advances_shuffled_drop_once(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["banks"]["default"]["drop"] = ["room_blackout", "room_manual"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(
            result.config,
            rng=random.Random(1),
            shuffled_roles=("drop",),
        )
        director._role_cursors["drop"] = 0

        committed = director.commit_role("drop")

        self.assertIsNotNone(committed)
        self.assertEqual(director._role_cursors["drop"], 1)
        self.assertIn("drop", director._role_shuffle_bags)

    def test_clear_queued_post_drop_prevents_cross_teardown_leak(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["looks"]["room_post_drop"] = {
            "target": "room_perimeter",
            "action": "scene",
            "scene_ref": "PostDrop-A",
            "fallback": "room_blackout",
            "safety_class": "post_drop",
            "brightness": 80,
            "allow_strobe": False,
        }
        cfg["banks"]["default"]["post_drop"] = ["room_safe_default"]
        cfg["drop_pairs"] = {
            "room_manual": {"post_drop": "room_post_drop", "duration_beats": 8.0}
        }
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)

        director.tick(LEDContext(role="drop"))
        # Simulate a track/deck change / stop tearing the lifecycle down before
        # the post_drop section ever ran.
        director.clear_queued_post_drop()
        after_teardown = director.tick(LEDContext(role="post_drop"))

        self.assertIsNotNone(after_teardown)
        self.assertEqual(after_teardown.look, "room_safe_default")
        self.assertNotEqual(after_teardown.reason, "paired_post_drop")

    def test_drop_duration_and_post_drop_cycle_come_from_config(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        cfg["looks"]["room_post_drop"] = {
            "target": "room_perimeter",
            "action": "scene",
            "scene_ref": "PostDrop-A",
            "fallback": "room_blackout",
            "safety_class": "post_drop",
            "brightness": 80,
            "allow_strobe": False,
        }
        cfg["drop_pairs"] = {
            "room_manual": {
                "post_drop": "room_post_drop",
                "duration_beats": 12.0,
            }
        }
        cfg["post_drop_cycle_beats"] = 24.0
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)

        self.assertEqual(director.paired_post_drop_look("room_manual"), "room_post_drop")
        self.assertEqual(director.drop_duration_beats("room_manual"), 12.0)
        self.assertEqual(director.drop_duration_beats("room_safe_default"), 8.0)
        self.assertEqual(director.post_drop_cycle_beats(), 24.0)


if __name__ == "__main__":
    unittest.main()
