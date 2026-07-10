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

    def test_shuffle_bag_rebuilds_when_preference_subset_changes(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        subsets = ({f"drop_a_{i}" for i in range(4)}, {f"drop_b_{i}" for i in range(4)})
        for name in set.union(*subsets):
            cfg["looks"][name] = copy.deepcopy(cfg["looks"]["room_manual"])
        cfg["banks"]["default"]["drop"] = sorted(set.union(*subsets))
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)

        for seed in range(6):
            with self.subTest(seed=seed):
                director = LEDLookDirector(
                    result.config, rng=random.Random(seed), shuffled_roles=("drop",),
                )
                for _ in range(seed % 3 + 1):
                    self.assertIn(
                        director.commit_role("drop", look_preference=lambda n: n in subsets[0]).look,
                        subsets[0],
                    )
                self.assertIn(
                    director.commit_role("drop", look_preference=lambda n: n in subsets[1]).look,
                    subsets[1],
                )

    def test_shuffle_bag_cycle_intact_for_stable_subset(self) -> None:
        cfg = _director_config()
        cfg["automation_enabled"] = True
        subset = {f"drop_a_{i}" for i in range(4)}
        for name in subset:
            cfg["looks"][name] = copy.deepcopy(cfg["looks"]["room_manual"])
        cfg["banks"]["default"]["drop"] = sorted(subset)
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(
            result.config, rng=random.Random(0), shuffled_roles=("drop",),
        )

        picks = [
            director.commit_role("drop", look_preference=lambda n: n in subset).look
            for _ in range(len(subset))
        ]
        self.assertEqual(set(picks), subset)

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
        # Part J happy-path pin: the pair is queued when the drop is ACCEPTED, not
        # at decision time. The dispatch policy calls this after outcome=="accepted".
        director.queue_paired_post_drop_on_accept(drop.look, stamp=100.0)
        preview = director.preview_role("post_drop")
        paired = director.tick(LEDContext(role="post_drop", post_drop_stamp=100.0))
        next_generic = director.tick(LEDContext(role="post_drop", post_drop_stamp=100.0))

        self.assertIsNotNone(drop)
        self.assertEqual(drop.look, "room_manual")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.look, "room_post_drop")
        self.assertIsNotNone(paired)
        self.assertEqual(paired.look, "room_post_drop")
        self.assertEqual(paired.reason, "paired_post_drop")
        self.assertIsNotNone(next_generic)
        self.assertEqual(next_generic.look, "room_safe_default")

    def test_partj_suppressed_drop_decision_leaves_queue_empty(self) -> None:
        # A drop decision is computed but never accepted (gate/blackout/reject).
        # It must NOT queue a pair, so the next post_drop is normal rotation.
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

        drop = director.tick(LEDContext(role="drop"))  # decision only, never accepted
        self.assertEqual(drop.look, "room_manual")
        self.assertEqual(director._queued_post_drop_look, "")

        post = director.tick(LEDContext(role="post_drop", post_drop_stamp=100.0))
        self.assertEqual(post.look, "room_safe_default")
        self.assertNotEqual(post.reason, "paired_post_drop")

    def test_partj_stale_stamp_pair_ignored_then_next_drop_wins(self) -> None:
        # Drop A accepted -> its pair queued with stamp A. A later post_drop that
        # belongs to a different drop (stamp B) must NOT fire A's pair; and a drop
        # B that is accepted overwrites the queue with B's pair.
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
        cfg["looks"]["room_post_drop_b"] = {
            "target": "room_perimeter",
            "action": "scene",
            "scene_ref": "PostDrop-B",
            "fallback": "room_blackout",
            "safety_class": "post_drop",
            "brightness": 80,
            "allow_strobe": False,
        }
        for name, ref in (("drop_a", "Drop-A"), ("drop_b", "Drop-B")):
            cfg["looks"][name] = {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": ref,
                "fallback": "room_blackout",
                "safety_class": "drop",
                "brightness": 100,
                "allow_strobe": True,
            }
        cfg["banks"]["default"]["post_drop"] = ["room_safe_default"]
        cfg["drop_pairs"] = {
            "drop_a": {"post_drop": "room_post_drop", "duration_beats": 8.0},
            "drop_b": {"post_drop": "room_post_drop_b", "duration_beats": 8.0},
        }
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)

        # Drop A accepted, stamp 100. A post_drop for a DIFFERENT drop (stamp 200)
        # must reject A's stale pair and fall through to rotation.
        director.queue_paired_post_drop_on_accept("drop_a", stamp=100.0)
        stale = director.tick(LEDContext(role="post_drop", post_drop_stamp=200.0))
        self.assertEqual(stale.look, "room_safe_default")
        self.assertNotEqual(stale.reason, "paired_post_drop")
        self.assertEqual(director._queued_post_drop_look, "")  # cleared on reject

        # Drop B accepted overwrites the queue; its own post_drop fires B's pair.
        director.queue_paired_post_drop_on_accept("drop_b", stamp=300.0)
        paired_b = director.tick(LEDContext(role="post_drop", post_drop_stamp=300.0))
        self.assertEqual(paired_b.look, "room_post_drop_b")
        self.assertEqual(paired_b.reason, "paired_post_drop")

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
                director._role_shuffle_bags.pop((role, "cloud_diy"), None)

                decision = director.tick(LEDContext(role=role))

                self.assertIsNotNone(decision)
                # AWR-149: shuffle bags are keyed by (role, backend) now.
                self.assertIn((role, "cloud_diy"), director._role_shuffle_bags)
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
        # AWR-149: shuffle bags are keyed by (role, backend) now.
        self.assertIn(("drop", "cloud_diy"), director._role_shuffle_bags)

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

        # A drop is accepted, so its pair is genuinely queued (Part J).
        director.queue_paired_post_drop_on_accept("room_manual", stamp=100.0)
        self.assertEqual(director._queued_post_drop_look, "room_post_drop")
        # Simulate a track/deck change / stop tearing the lifecycle down before
        # the post_drop section ever ran.
        director.clear_queued_post_drop()
        after_teardown = director.tick(LEDContext(role="post_drop", post_drop_stamp=100.0))

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


RT = "realtime_razer"
CLOUD = "cloud_diy"


def _mixed_config() -> dict:
    """Config whose groove role has 2 realtime + 1 cloud look, so the
    deterministic mixed-transport plan (AWR-149) can be exercised."""
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

    def _rt(scene: str) -> dict:
        return {
            "target": "room_perimeter",
            "action": "realtime",
            "scene_ref": scene,
            "fallback": "",
            "safety_class": "groove",
            "brightness": 100,
            "allow_strobe": True,
            "backend": "realtime_razer",
            "params": {},
        }

    cfg["looks"]["rt_groove_a"] = _rt("drop_chase_blue")
    cfg["looks"]["rt_groove_b"] = _rt("drop_chase_blue")
    cfg["looks"]["cloud_groove"] = copy.deepcopy(cfg["looks"]["room_safe_default"])
    cfg["looks"]["cloud_drop"] = copy.deepcopy(cfg["looks"]["room_manual"])
    cfg["looks"]["cloud_post"] = copy.deepcopy(cfg["looks"]["room_safe_default"])
    # groove leads realtime (2 RT, 1 cloud) -> plan (RT, cloud, RT).
    cfg["banks"]["default"]["groove"] = ["rt_groove_a", "rt_groove_b", "cloud_groove"]
    cfg["banks"]["default"]["drop"] = ["cloud_drop"]
    cfg["banks"]["default"]["post_drop"] = ["cloud_post"]
    cfg["drop_pairs"] = {"cloud_drop": {"post_drop": "cloud_post", "duration_beats": 8.0}}
    return cfg


class LEDLookDirectorPlanRotationTests(unittest.TestCase):
    def _director(self, *, seed: int = 0, shuffled: bool = True) -> LEDLookDirector:
        result = load_led_look_director_config_from_dict(copy.deepcopy(_mixed_config()))
        self.assertTrue(result.available, msg=result.errors)
        return LEDLookDirector(
            result.config,
            rng=random.Random(seed),
            shuffled_roles=LED_AUTOMATION_ROLE_ORDER if shuffled else (),
        )

    def _backend_of(self, mapping):
        return lambda name: mapping[name]

    # Part D.1 -----------------------------------------------------------
    def test_plan_backend_sequence_exact_tuples(self) -> None:
        from rb_ss_bridge_v2.led_look_director import plan_backend_sequence

        names6_2 = [f"rt{i}" for i in range(6)] + [f"c{i}" for i in range(2)]
        b6_2 = {n: (RT if n.startswith("rt") else CLOUD) for n in names6_2}
        self.assertEqual(
            plan_backend_sequence(names6_2, self._backend_of(b6_2)),
            (RT, RT, CLOUD, RT, RT, RT, CLOUD, RT),
        )
        # 1 + 1 -> alternation, realtime first even though cloud is listed first.
        self.assertEqual(
            plan_backend_sequence(["c0", "rt0"], self._backend_of({"c0": CLOUD, "rt0": RT})),
            (RT, CLOUD),
        )
        # 3 + 3 tie -> realtime leads.
        names3 = [f"rt{i}" for i in range(3)] + [f"c{i}" for i in range(3)]
        b3 = {n: (RT if n.startswith("rt") else CLOUD) for n in names3}
        self.assertEqual(
            plan_backend_sequence(names3, self._backend_of(b3)),
            (RT, CLOUD, RT, CLOUD, RT, CLOUD),
        )
        # Single backend -> uniform.
        self.assertEqual(
            plan_backend_sequence(
                ["c0", "c1", "c2"], self._backend_of({"c0": CLOUD, "c1": CLOUD, "c2": CLOUD})
            ),
            (CLOUD, CLOUD, CLOUD),
        )
        # Empty -> ().
        self.assertEqual(plan_backend_sequence([], self._backend_of({})), ())
        # Order stability: reordering names within a subset never changes labels.
        shuffled_names = ["c0", *[f"rt{i}" for i in range(6)], "c1"]
        self.assertEqual(
            plan_backend_sequence(shuffled_names, self._backend_of(b6_2)),
            (RT, RT, CLOUD, RT, RT, RT, CLOUD, RT),
        )

    # Part D.2 -----------------------------------------------------------
    def test_backend_sequence_is_seed_independent(self) -> None:
        def groove_backends(seed: int) -> list[str]:
            director = self._director(seed=seed)
            return [
                director.tick(LEDContext(role="groove")).backend for _ in range(12)
            ]

        seq_a = groove_backends(1)
        seq_b = groove_backends(2)
        self.assertEqual(seq_a, seq_b)
        # 2 RT + 1 cloud -> plan (RT, cloud, RT) cycled 12 times.
        self.assertEqual(seq_a, [RT, CLOUD, RT] * 4)
        # Look names within a backend may still differ across seeds.
        looks_a = [self._director(seed=3).tick(LEDContext(role="groove")).look for _ in range(1)]
        self.assertIsNotNone(looks_a)

    # Part D.3 -----------------------------------------------------------
    def test_no_latch_groove_follows_plan_cycle(self) -> None:
        director = self._director(seed=7)
        backends = [
            director.tick(LEDContext(role="groove")).backend for _ in range(6)
        ]
        # Cloud recurs at its planned slots -- the OLD sticky code latched onto
        # whichever transport it hit first and never returned to the other.
        self.assertEqual(backends, [RT, CLOUD, RT, RT, CLOUD, RT])
        self.assertEqual([i for i, b in enumerate(backends) if b == CLOUD], [1, 4])

    # Part D.4 -----------------------------------------------------------
    def test_session_phase_starts_at_zero_for_every_seed(self) -> None:
        for seed in (0, 1, 17, 999):
            director = self._director(seed=seed)
            for role in LED_AUTOMATION_ROLE_ORDER:
                self.assertEqual(director._role_cursors[role], 0)

    # Part D.5 -----------------------------------------------------------
    def test_eligibility_rebase_still_reaches_both_transports(self) -> None:
        rt_only = self._director(seed=1)
        for _ in range(6):
            decision = rt_only.commit_role(
                "groove",
                diy_eligible=lambda n: rt_only._config.looks[n].backend == RT,
            )
            self.assertEqual(decision.backend, RT)

        restored = self._director(seed=1)
        backends = [restored.commit_role("groove").backend for _ in range(6)]
        self.assertIn(CLOUD, backends)

        # C4: a predicate that rejects everything keeps the FULL bank, so the
        # pick still succeeds and follows the full-bank plan (RT at cursor 0).
        c4 = self._director(seed=1)
        decision = c4.commit_role("groove", diy_eligible=lambda n: False)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.backend, RT)

    # Part D.6 -----------------------------------------------------------
    def test_preview_parity_and_no_mutation(self) -> None:
        for seed in range(6):
            with self.subTest(seed=seed):
                director = self._director(seed=seed)
                rng_before = director._rng.getstate()
                p1 = director.preview_role("groove")
                p2 = director.preview_role("groove")
                self.assertIsNotNone(p1)
                # Two previews agree and neither mutates cursor/bag/RNG.
                self.assertEqual((p1.look, p1.backend), (p2.look, p2.backend))
                self.assertEqual(director._role_cursors["groove"], 0)
                self.assertEqual(director._role_shuffle_bags, {})
                self.assertEqual(director._rng.getstate(), rng_before)
                committed = director.commit_role("groove")
                self.assertEqual((p1.look, p1.backend), (committed.look, committed.backend))
                self.assertEqual(director._role_cursors["groove"], 1)

    # AWR-150: realtime substitute for a cloud drop pick ------------------
    def _mixed_drop_director(self, *, seed: int = 0) -> LEDLookDirector:
        """A director whose drop bank has 1 realtime + 1 cloud look."""
        cfg = copy.deepcopy(_mixed_config())
        cfg["looks"]["rt_drop"] = {
            "target": "room_perimeter",
            "action": "realtime",
            "scene_ref": "drop_chase_blue",
            "fallback": "",
            "safety_class": "drop",
            "brightness": 100,
            "allow_strobe": True,
            "backend": "realtime_razer",
            "params": {},
        }
        cfg["banks"]["default"]["drop"] = ["rt_drop", "cloud_drop"]
        cfg["drop_pairs"] = {
            "rt_drop": {"post_drop": "cloud_post", "duration_beats": 8.0},
            "cloud_drop": {"post_drop": "cloud_post", "duration_beats": 8.0},
        }
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        return LEDLookDirector(
            result.config, rng=random.Random(seed),
            shuffled_roles=LED_AUTOMATION_ROLE_ORDER,
        )

    def test_substitute_realtime_drop_picks_rt_and_leaves_plan_cursor(self) -> None:
        director = self._mixed_drop_director(seed=0)
        # What the plan WOULD pick for the drop role, on a pristine director.
        planned = self._mixed_drop_director(seed=0).commit_role("drop")

        backend_before = director._role_backend_cursors.get(("drop", RT), 0)
        sub = director.substitute_realtime_drop()

        self.assertIsNotNone(sub)
        self.assertEqual(sub.backend, RT)
        self.assertEqual(sub.reason, "role_entry:drop:rt_substitute")
        self.assertEqual(sub.role, "drop")
        # Only the (drop, realtime_razer) cursor advanced; the plan cursor did not.
        self.assertEqual(director._role_cursors["drop"], 0)
        self.assertEqual(director._role_backend_cursors[("drop", RT)], backend_before + 1)
        # No paired post_drop queued (the committed cloud pick owns pairing).
        self.assertEqual(director._queued_post_drop_look, "")
        # Plan cursor untouched => the next real drop commit is exactly what it
        # would have been without the substitute.
        self.assertEqual(director.commit_role("drop").look, planned.look)

    def test_substitute_realtime_drop_returns_none_on_cloud_only_bank(self) -> None:
        # _mixed_config's drop bank is ["cloud_drop"] -- no realtime look.
        director = self._director(seed=0)
        self.assertIsNone(director.substitute_realtime_drop())

    # Part D.7 -----------------------------------------------------------
    def test_paired_post_drop_bypasses_plan_and_advances_no_cursor(self) -> None:
        director = self._director(seed=0)
        drop = director.tick(LEDContext(role="drop"))
        self.assertEqual(drop.look, "cloud_drop")
        # Part J: the pair is queued on accepted dispatch, not by the drop tick.
        director.queue_paired_post_drop_on_accept(drop.look, stamp=100.0)
        role_before = dict(director._role_cursors)
        backend_before = dict(director._role_backend_cursors)

        paired = director.tick(LEDContext(role="post_drop", post_drop_stamp=100.0))

        self.assertEqual(paired.look, "cloud_post")
        self.assertEqual(paired.reason, "paired_post_drop")
        # The paired post_drop advances neither the plan cursor nor any
        # (role, backend) cursor.
        self.assertEqual(director._role_cursors["post_drop"], role_before["post_drop"])
        self.assertEqual(director._role_backend_cursors, backend_before)


if __name__ == "__main__":
    unittest.main()
