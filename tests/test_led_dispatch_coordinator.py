from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_owner_state import GoveeOwnerStateMachine, OwnerState  # noqa: E402
from rb_ss_bridge_v2.led_dispatch_coordinator import (  # noqa: E402
    _DEFAULT_WHITE_TEMPLATES,
    LEDDispatchCoordinator,
)
from rb_ss_bridge_v2.led_models import LEDLookDecision, LEDRateLimits  # noqa: E402


class _Config:
    blackout = "room_blackout"
    rate_limits = LEDRateLimits(
        min_look_dwell_s=1.5,
        transport_switch_cooldown_s=2.0,
        rt_reconcile_window_s=5.0,
        rt_reconcile_interval_s=1.0,
    )


class _Adapter:
    def __init__(self) -> None:
        self.trigger_calls: list[LEDLookDecision] = []
        self.cancel_pending_calls: int = 0
        self.shutdown_called = False

    def trigger(self, decision: LEDLookDecision) -> bool:
        self.trigger_calls.append(decision)
        return True

    def status(self) -> dict:
        return {"available": True, "running": False, "dry_run": True}

    def cancel_pending(self) -> int:
        self.cancel_pending_calls += 1
        return 1

    def shutdown(self) -> bool:
        self.shutdown_called = True
        return True


class _Runner:
    def __init__(self) -> None:
        self.desired = []
        self.fire_count = 0
        self.emergency_count = 0
        self.stop_called = False
        self.assert_count = 0
        self.brightness_requests: list[int] = []

    def set_desired(self, spec) -> None:  # type: ignore[no-untyped-def]
        self.desired.append(spec)

    def fire_trigger(self) -> None:
        self.fire_count += 1

    def emergency_stop(self) -> None:
        self.emergency_count += 1

    def force_deactivate(self) -> None:
        self.desired.append(None)

    def request_activate_assert(self) -> None:
        self.assert_count += 1

    def request_brightness(self, value: int) -> None:
        self.brightness_requests.append(int(value))

    def status(self) -> dict:
        return {"active": bool(self.desired), "last_error": ""}

    def stop(self) -> bool:
        self.stop_called = True
        return True


def _decision(
    *,
    look: str = "rt_groove",
    action: str = "realtime",
    backend: str = "realtime_razer",
    scene_ref: str = "groove_chase_blue",
    role: str = "groove",
) -> LEDLookDecision:
    return LEDLookDecision(
        look=look,
        target="room_perimeter",
        action=action,
        scene_ref=scene_ref,
        reason=f"role_entry:{role}",
        source="automation",
        priority=2,
        role=role,
        backend=backend,
        params={},
    )


class OwnerStateTests(unittest.TestCase):
    def test_owner_transitions(self) -> None:
        owner = GoveeOwnerStateMachine()
        self.assertTrue(owner.acquire(OwnerState.REALTIME_RAZER))
        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)
        self.assertFalse(owner.acquire(OwnerState.CLOUD_DIY))
        self.assertTrue(owner.release(OwnerState.REALTIME_RAZER))
        self.assertEqual(owner.current(), OwnerState.NONE)
        owner.acquire(OwnerState.CLOUD_DIY)
        owner.force_release()
        self.assertEqual(owner.current(), OwnerState.NONE)


class LEDDispatchCoordinatorTests(unittest.TestCase):
    def _coordinator(
        self,
        *,
        clock: float = 1000.0,
        min_dwell_env: str = "1",
        cancel_pending_env: str = "1",
        transport_cooldown_env: str = "0",
    ) -> tuple[LEDDispatchCoordinator, _Adapter, _Runner, GoveeOwnerStateMachine]:
        adapter = _Adapter()
        runner = _Runner()
        owner = GoveeOwnerStateMachine()
        _clock = {"v": clock}
        with patch.dict(os.environ, {
            "RBSS_LED_MIN_DWELL": min_dwell_env,
            "RBSS_LED_CANCEL_PENDING": cancel_pending_env,
            "RBSS_LED_TRANSPORT_COOLDOWN": transport_cooldown_env,
        }):
            coordinator = LEDDispatchCoordinator(
                adapter, runner, owner, _Config(),
                time_fn=lambda: _clock["v"],
            )
        coordinator._clock = _clock  # expose for tests
        return coordinator, adapter, runner, owner

    def test_realtime_decision_sets_runner_without_cloud_trigger(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator()

        self.assertTrue(coordinator.trigger(_decision()))

        self.assertEqual(adapter.trigger_calls, [])
        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)
        self.assertEqual(runner.desired[-1].effect_name, "groove_chase_blue")
        self.assertEqual(runner.fire_count, 1)
        # Realtime takeover re-asserts razer mode.
        self.assertEqual(runner.assert_count, 1)

    def test_realtime_white_template_sets_white_moment_flag(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator(min_dwell_env="0")

        self.assertTrue(coordinator.trigger(_decision(scene_ref="drop_white_aggressive")))
        self.assertTrue(coordinator.last_white_moment())

        self.assertTrue(coordinator.trigger(_decision(scene_ref="groove_chase_blue", look="rt_groove_2")))
        self.assertFalse(coordinator.last_white_moment())

    def test_custom_white_template_from_loaded_map_is_flagged(self) -> None:
        # A template name absent from the coordinator's own hardcoded defaults
        # must still be recognized when it comes from the loaded LaserColorMap
        # (config/laser_color_map.json's white_templates), proving the plumb.
        self.assertNotIn("custom_white_flash", _DEFAULT_WHITE_TEMPLATES)
        adapter = _Adapter()
        runner = _Runner()
        owner = GoveeOwnerStateMachine()
        with patch.dict(os.environ, {"RBSS_LED_MIN_DWELL": "0"}):
            coordinator = LEDDispatchCoordinator(
                adapter, runner, owner, _Config(),
                time_fn=lambda: 1000.0,
                white_templates=("custom_white_flash",),
            )

        self.assertTrue(coordinator.trigger(_decision(scene_ref="custom_white_flash")))
        self.assertTrue(coordinator.last_white_moment())

        self.assertTrue(coordinator.trigger(_decision(scene_ref="drop_white_aggressive", look="rt_groove_2")))
        self.assertFalse(coordinator.last_white_moment())

    def test_realtime_to_cloud_handoff_stands_down_runner_then_triggers_cloud(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator()
        coordinator.trigger(_decision())
        # advance clock past dwell window
        coordinator._clock["v"] = 1000.0 + 2.0

        cloud = _decision(
            look="groove_cloud",
            action="scene",
            backend="cloud_diy",
            scene_ref="Release-A",
        )
        self.assertTrue(coordinator.trigger(cloud))

        self.assertIsNone(runner.desired[-1])
        self.assertEqual(adapter.trigger_calls[-1], cloud)
        self.assertEqual(owner.current(), OwnerState.CLOUD_DIY)

    def test_operator_blackout_hard_kills_and_uses_cloud_adapter(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator()
        coordinator.trigger(_decision())

        blackout = _decision(
            look="room_blackout",
            action="diy_scene",
            backend="cloud_diy",
            scene_ref="23259999",
            role="emergency",
        )
        self.assertTrue(coordinator.trigger(blackout))

        self.assertEqual(runner.emergency_count, 1)
        self.assertEqual(adapter.trigger_calls[-1], blackout)
        self.assertEqual(owner.current(), OwnerState.NONE)

    def test_tactical_blackout_keeps_realtime_owner_and_skips_cloud_adapter(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator()

        self.assertTrue(coordinator.tactical_blackout(_decision(role="drop")))

        self.assertEqual(adapter.trigger_calls, [])
        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)
        self.assertEqual(runner.desired[-1].effect_name, "blackout")
        # Tactical blackout re-asserts razer so the black frames reach the strip,
        # but does NOT dim (a drop look follows within a few beats).
        self.assertEqual(runner.assert_count, 1)
        self.assertEqual(runner.brightness_requests, [])

    # ── WI-3 min-dwell tests ──────────────────────────────────────────────────

    def test_wi3_same_role_within_dwell_is_suppressed(self) -> None:
        """WI-3: a second groove dispatch within min_look_dwell_s must be suppressed."""
        coordinator, adapter, runner, owner = self._coordinator(min_dwell_env="1")
        # First dispatch accepted
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        # 6 ms later — still within 1.5 s dwell
        coordinator._clock["v"] = 1000.006
        result = coordinator.trigger(_decision(role="groove", look="rt_groove_alt"))
        self.assertFalse(result)
        # Only one runner set_desired call happened
        self.assertEqual(sum(1 for d in runner.desired if d is not None), 1)
        # WI-8 counter
        self.assertEqual(coordinator._dwell_suppressed_count, 1)

    def test_wi3_different_role_within_dwell_is_allowed(self) -> None:
        """WI-3: role change (groove→drop) within dwell window must always pass."""
        coordinator, adapter, runner, owner = self._coordinator(min_dwell_env="1")
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        coordinator._clock["v"] = 1000.006
        result = coordinator.trigger(_decision(role="drop", look="rt_drop", scene_ref="drop_chase_red"))
        self.assertTrue(result)

    def test_wi3_same_role_after_dwell_expires_is_allowed(self) -> None:
        """WI-3: after dwell_s elapses, a same-role re-pick must be accepted."""
        coordinator, adapter, runner, owner = self._coordinator(min_dwell_env="1")
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        coordinator._clock["v"] = 1000.0 + 2.0  # 2 s > 1.5 s dwell
        result = coordinator.trigger(_decision(role="groove", look="rt_groove_alt"))
        self.assertTrue(result)

    def test_wi3_dwell_off_reproduces_previous_behavior(self) -> None:
        """Flag OFF parity: RBSS_LED_MIN_DWELL=0 must never suppress."""
        coordinator, adapter, runner, owner = self._coordinator(min_dwell_env="0")
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        coordinator._clock["v"] = 1000.001  # 1 ms — would be suppressed if flag were ON
        result = coordinator.trigger(_decision(role="groove", look="rt_groove_alt"))
        self.assertTrue(result)
        self.assertEqual(coordinator._dwell_suppressed_count, 0)

    # ── WI-4 cancel-pending tests ─────────────────────────────────────────────

    def test_wi4_cancel_pending_called_when_switching_from_cloud_to_rt(self) -> None:
        """WI-4: switching from cloud DIY to RT must call adapter.cancel_pending()."""
        coordinator, adapter, runner, owner = self._coordinator(cancel_pending_env="1")
        # Get into CLOUD_DIY state
        cloud = _decision(look="groove_cloud", action="scene", backend="cloud_diy", scene_ref="Release-A")
        owner.acquire(OwnerState.CLOUD_DIY)
        # Now trigger RT
        self.assertTrue(coordinator.trigger(_decision()))
        self.assertEqual(adapter.cancel_pending_calls, 1)
        self.assertEqual(coordinator._cancel_pending_total, 1)

    def test_wi4_cancel_pending_off_skips_drain(self) -> None:
        """Flag OFF parity: RBSS_LED_CANCEL_PENDING=0 must not call cancel_pending."""
        coordinator, adapter, runner, owner = self._coordinator(cancel_pending_env="0")
        owner.acquire(OwnerState.CLOUD_DIY)
        coordinator.trigger(_decision())
        self.assertEqual(adapter.cancel_pending_calls, 0)

    # ── WI-5 transport-cooldown tests ─────────────────────────────────────────

    def test_wi5_cooldown_off_by_default_never_suppresses(self) -> None:
        """WI-5 default OFF: RT→DIY switch is never suppressed without the flag."""
        coordinator, adapter, runner, owner = self._coordinator(transport_cooldown_env="0")
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        coordinator._clock["v"] = 1000.001
        cloud = _decision(look="groove_cloud", action="scene", backend="cloud_diy",
                          scene_ref="Release-A", role="groove")
        # Advance past dwell to isolate cooldown
        coordinator._clock["v"] = 1000.0 + 2.0
        result = coordinator.trigger(cloud)
        self.assertTrue(result)
        self.assertEqual(coordinator._transport_cooldown_count, 0)

    def test_wi5_cooldown_on_suppresses_same_role_transport_switch_within_window(self) -> None:
        """WI-5 ON: same-role RT→DIY within cooldown_s must be suppressed."""
        coordinator, adapter, runner, owner = self._coordinator(
            min_dwell_env="0",  # disable dwell so only cooldown is tested
            transport_cooldown_env="1",
        )
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        coordinator._clock["v"] = 1000.5  # 0.5 s < 2 s cooldown
        cloud = _decision(look="groove_cloud", action="scene", backend="cloud_diy",
                          scene_ref="Release-A", role="groove")
        result = coordinator.trigger(cloud)
        self.assertFalse(result)
        self.assertEqual(coordinator._transport_cooldown_count, 1)

    def test_wi5_cooldown_on_exempts_role_change(self) -> None:
        """WI-5 ON: a role change (groove→drop) must bypass the transport cooldown."""
        coordinator, adapter, runner, owner = self._coordinator(
            min_dwell_env="0",
            transport_cooldown_env="1",
        )
        self.assertTrue(coordinator.trigger(_decision(role="groove")))
        coordinator._clock["v"] = 1000.5
        drop = _decision(role="drop", look="rt_drop", scene_ref="drop_chase_red")
        result = coordinator.trigger(drop)
        self.assertTrue(result)

    # ── razer keepalive replaces WI-6 reconcile ──────────────────────────────

    def test_cloud_dispatch_does_not_assert_razer(self) -> None:
        """A cloud DIY trigger must not re-assert razer (WI-6 note_cloud_dispatch is gone)."""
        coordinator, adapter, runner, owner = self._coordinator()
        self.assertFalse(hasattr(runner, "note_cloud_dispatch"))
        cloud = _decision(look="groove_cloud", action="scene", backend="cloud_diy",
                          scene_ref="Release-A", role="groove")
        coordinator.trigger(cloud)
        self.assertEqual(runner.assert_count, 0)

    def test_restore_brightness_requests_full(self) -> None:
        """restore_brightness() asks the runner for full LAN brightness."""
        coordinator, adapter, runner, owner = self._coordinator()
        coordinator.restore_brightness()
        self.assertEqual(runner.brightness_requests, [100])

    def test_blackout_brightness_requests_zero(self) -> None:
        """AWR-146 Task 6: blackout_brightness() asks the runner for LAN 0 —
        darkens even when the runner is inactive (cloud look showing)."""
        coordinator, adapter, runner, owner = self._coordinator()
        coordinator.blackout_brightness()
        self.assertEqual(runner.brightness_requests, [0])

    # ── WI-8 status counters ──────────────────────────────────────────────────

    def test_wi8_status_includes_observability_counters(self) -> None:
        """WI-8: status() must include dwell_suppressed_count, cancel_pending_total,
        transport_cooldown_count."""
        coordinator, adapter, runner, owner = self._coordinator()
        status = coordinator.status()
        realtime = status.get("realtime", {})
        self.assertIn("dwell_suppressed_count", realtime)
        self.assertIn("cancel_pending_total", realtime)
        self.assertIn("transport_cooldown_count", realtime)


if __name__ == "__main__":
    unittest.main()
