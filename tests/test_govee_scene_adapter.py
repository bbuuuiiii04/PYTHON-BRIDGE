from __future__ import annotations

import copy
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_scene_adapter import GoveeSceneAdapter  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config_from_dict  # noqa: E402
from rb_ss_bridge_v2.led_models import LEDLookDecision  # noqa: E402


def _adapter_config(
    *,
    enabled: bool = True,
    dry_run: bool = True,
    queue_maxsize: int = 2,
    scene_retrigger_cooldown_s: float = 4.0,
    high_impact_cooldown_s: float = 12.0,
    request_timeout_s: float = 2.0,
    worker_shutdown_timeout_s: float = 1.0,
    target_capabilities: list[str] | None = None,
) -> dict:
    capabilities = target_capabilities if target_capabilities is not None else [
        "scene",
        "diy_scene",
        "off",
    ]
    return {
        "schema_version": 1,
        "enabled": enabled,
        "dry_run": dry_run,
        "automation_enabled": False,
        "targets": {
            "room_perimeter": {
                "label": "Strip Light",
                "device_ref": "local-device-ref-123",
                "expected_model": "H612D",
                "control_route": "govee_platform_dynamic_scene",
                "capabilities": capabilities,
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
            "room_safe_alt": {
                "target": "room_perimeter",
                "action": "scene",
                "scene_ref": "Release-B",
                "fallback": "room_blackout",
                "safety_class": "safe",
                "brightness": 60,
                "allow_strobe": False,
            },
            "room_blackout": {
                "target": "room_perimeter",
                "action": "diy_scene",
                "scene_ref": "23259999",
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
            "queue_maxsize": queue_maxsize,
            "scene_retrigger_cooldown_s": scene_retrigger_cooldown_s,
            "high_impact_cooldown_s": high_impact_cooldown_s,
            "request_timeout_s": request_timeout_s,
            "worker_shutdown_timeout_s": worker_shutdown_timeout_s,
        },
        "safety": {
            "max_brightness": 100,
            "allow_strobe": True,
            "max_strobe_duration_ms": 750,
            "high_impact_cooldown_s": high_impact_cooldown_s,
            "drop_flash_duration_ms": 750,
            "emergency_blackout_always_available": True,
            "scripted_mode_automation": False,
        },
    }


def _decision(*, look: str = "room_safe_default", scene_ref: str = "Release-A") -> LEDLookDecision:
    return LEDLookDecision(
        look=look,
        target="room_perimeter",
        action="scene",
        scene_ref=scene_ref,
        reason="safe_default",
        source="policy",
        priority=2,
        role="ambient",
    )


class GoveeSceneAdapterTests(unittest.TestCase):
    def _build_adapter(
        self,
        *,
        enabled: bool = True,
        dry_run: bool = True,
        queue_maxsize: int = 2,
        scene_retrigger_cooldown_s: float = 4.0,
        high_impact_cooldown_s: float = 12.0,
        request_timeout_s: float = 2.0,
        worker_shutdown_timeout_s: float = 1.0,
        target_capabilities: list[str] | None = None,
    ) -> GoveeSceneAdapter:
        cfg = copy.deepcopy(
            _adapter_config(
                enabled=enabled,
                dry_run=dry_run,
                queue_maxsize=queue_maxsize,
                scene_retrigger_cooldown_s=scene_retrigger_cooldown_s,
                high_impact_cooldown_s=high_impact_cooldown_s,
                request_timeout_s=request_timeout_s,
                worker_shutdown_timeout_s=worker_shutdown_timeout_s,
                target_capabilities=target_capabilities,
            )
        )
        loaded = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(loaded.available, msg=loaded.errors)
        return GoveeSceneAdapter(loaded.config)

    def test_dry_run_trigger_queues_command(self) -> None:
        adapter = self._build_adapter()
        ok = adapter.trigger(_decision())
        self.assertTrue(ok)
        queued = adapter.pop_next_command()
        self.assertIsNotNone(queued)
        self.assertEqual(queued.look, "room_safe_default")
        self.assertEqual(queued.scene_ref, "Release-A")

    def test_status_shape_contains_queue_and_counters(self) -> None:
        adapter = self._build_adapter()
        adapter.trigger(_decision())
        status = adapter.status()
        self.assertTrue(status["available"])
        self.assertFalse(status["running"])
        self.assertTrue(status["dry_run"])
        self.assertIn("queue_depth", status)
        self.assertIn("queue_max", status)
        self.assertIn("accepted_count", status)
        self.assertIn("rejected_count", status)
        self.assertIn("dropped_count", status)

    def test_trigger_is_non_blocking_when_queue_full(self) -> None:
        adapter = self._build_adapter(
            queue_maxsize=1,
            scene_retrigger_cooldown_s=0.0,
            high_impact_cooldown_s=0.0,
        )
        self.assertTrue(adapter.trigger(_decision()))
        start = time.perf_counter()
        ok = adapter.trigger(_decision(look="room_safe_alt", scene_ref="Release-B"))
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self.assertFalse(ok)
        self.assertLess(elapsed_ms, 5.0)
        status = adapter.status()
        self.assertEqual(status["dropped_count"], 1)
        self.assertEqual(status["rejected_count"], 1)
        self.assertEqual(status["last_error"], "queue_full")

    def test_disabled_adapter_rejects_trigger(self) -> None:
        adapter = self._build_adapter(enabled=False)
        self.assertFalse(adapter.trigger(_decision()))
        status = adapter.status()
        self.assertEqual(status["last_error"], "disabled")
        self.assertEqual(status["rejected_count"], 1)

    def test_live_mode_rejected_in_phase_3(self) -> None:
        adapter = self._build_adapter(enabled=True, dry_run=False)
        self.assertFalse(adapter.trigger(_decision()))
        status = adapter.status()
        self.assertEqual(status["last_error"], "live_output_not_supported_in_phase3")
        self.assertEqual(status["rejected_count"], 1)

    def test_no_real_network_call_on_trigger(self) -> None:
        adapter = self._build_adapter(enabled=True, dry_run=True)
        with patch("socket.create_connection", side_effect=AssertionError("network call not allowed")):
            self.assertTrue(adapter.trigger(_decision()))

    # --- blackout / high-impact handling --------------------------------

    def _adapter_with_clock(self, clock: dict, **kwargs) -> GoveeSceneAdapter:
        cfg = copy.deepcopy(_adapter_config(**kwargs))
        loaded = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(loaded.available, msg=loaded.errors)
        return GoveeSceneAdapter(loaded.config, time_fn=lambda: clock["v"])

    @staticmethod
    def _drop_decision(look: str = "room_safe_default", scene_ref: str = "Release-A") -> LEDLookDecision:
        return LEDLookDecision(
            look=look, target="room_perimeter", action="scene", scene_ref=scene_ref,
            reason="role_entry:drop", source="automation", priority=2, role="drop",
        )

    @staticmethod
    def _blackout_decision() -> LEDLookDecision:
        return LEDLookDecision(
            look="room_blackout", target="room_perimeter", action="diy_scene", scene_ref="23259999",
            reason="emergency_blackout", source="emergency", priority=0, role="emergency",
        )

    def test_blackout_is_not_high_impact_and_does_not_block_following_drop(self) -> None:
        # Pre-drop blackout then drop ~2s later: the drop must still be accepted
        # because the configured blackout look is the safety de-escalation and
        # must not consume the high_impact cooldown budget.
        clock = {"v": 1000.0}
        adapter = self._adapter_with_clock(
            clock, queue_maxsize=8, high_impact_cooldown_s=12.0, scene_retrigger_cooldown_s=0.0,
        )
        self.assertTrue(adapter.trigger(self._blackout_decision()))
        clock["v"] += 2.0
        self.assertTrue(adapter.trigger(self._drop_decision()))
        self.assertEqual(adapter.status()["last_error"], "")

    def test_drop_remains_high_impact_rate_limited(self) -> None:
        # Control: drops are still high-impact, so a second drop within the
        # cooldown is rejected (we only exempted blackout, not drops).
        clock = {"v": 1000.0}
        adapter = self._adapter_with_clock(
            clock, queue_maxsize=8, high_impact_cooldown_s=12.0, scene_retrigger_cooldown_s=0.0,
        )
        self.assertTrue(adapter.trigger(self._drop_decision("room_safe_default", "Release-A")))
        clock["v"] += 2.0
        self.assertFalse(adapter.trigger(self._drop_decision("room_safe_alt", "Release-B")))
        self.assertEqual(adapter.status()["last_error"], "high_impact_rate_limited")

    def test_ambient_scene_bypasses_scene_retrigger_cooldown(self) -> None:
        clock = {"v": 1000.0}
        adapter = self._adapter_with_clock(
            clock, queue_maxsize=8, high_impact_cooldown_s=0.0, scene_retrigger_cooldown_s=4.0,
        )
        self.assertTrue(adapter.trigger(LEDLookDecision(
            look="groove_release_a",
            target="room_perimeter",
            action="scene",
            scene_ref="Release-A",
            reason="role_entry:groove",
            source="automation",
            priority=3,
            role="groove",
        )))

        clock["v"] += 1.0
        self.assertFalse(adapter.trigger(LEDLookDecision(
            look="room_safe_default",
            target="room_perimeter",
            action="scene",
            scene_ref="Meteor",
            reason="role_entry:groove",
            source="automation",
            priority=3,
            role="groove",
        )))
        self.assertEqual(adapter.status()["last_error"], "scene_retrigger_rate_limited")

        self.assertTrue(adapter.trigger(LEDLookDecision(
            look="room_safe_default",
            target="room_perimeter",
            action="scene",
            scene_ref="Meteor",
            reason="role_entry:ambient",
            source="automation",
            priority=3,
            role="ambient",
        )))
        self.assertEqual(adapter.status()["last_error"], "")

    def test_emergency_blackout_bypasses_full_queue(self) -> None:
        clock = {"v": 1000.0}
        adapter = self._adapter_with_clock(
            clock, queue_maxsize=1, high_impact_cooldown_s=0.0, scene_retrigger_cooldown_s=0.0,
        )
        self.assertTrue(adapter.trigger(_decision()))  # fills the size-1 queue
        # A non-blackout here would be queue_full-rejected; the blackout evicts and enqueues.
        self.assertTrue(adapter.trigger(self._blackout_decision()))
        popped = adapter.pop_next_command()
        self.assertIsNotNone(popped)
        self.assertEqual(popped.look, "room_blackout")
        self.assertEqual(adapter.status()["dropped_count"], 1)

    def test_emergency_blackout_bypasses_open_circuit(self) -> None:
        clock = {"v": 1000.0}
        adapter = self._adapter_with_clock(clock, queue_maxsize=8)
        adapter._circuit_open_until = clock["v"] + 100.0  # force the breaker open
        self.assertFalse(adapter.trigger(_decision()))
        self.assertEqual(adapter.status()["last_error"], "circuit_open")
        self.assertTrue(adapter.trigger(self._blackout_decision()))


if __name__ == "__main__":
    unittest.main()
