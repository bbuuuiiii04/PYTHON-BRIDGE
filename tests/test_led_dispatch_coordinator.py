from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_owner_state import GoveeOwnerStateMachine, OwnerState  # noqa: E402
from rb_ss_bridge_v2.led_dispatch_coordinator import LEDDispatchCoordinator  # noqa: E402
from rb_ss_bridge_v2.led_models import LEDLookDecision  # noqa: E402


class _Config:
    blackout = "room_blackout"


class _Adapter:
    def __init__(self) -> None:
        self.trigger_calls: list[LEDLookDecision] = []
        self.shutdown_called = False

    def trigger(self, decision: LEDLookDecision) -> bool:
        self.trigger_calls.append(decision)
        return True

    def status(self) -> dict:
        return {"available": True, "running": False, "dry_run": True}

    def shutdown(self) -> bool:
        self.shutdown_called = True
        return True


class _Runner:
    def __init__(self) -> None:
        self.desired = []
        self.emergency_count = 0
        self.stop_called = False

    def set_desired(self, spec) -> None:  # type: ignore[no-untyped-def]
        self.desired.append(spec)

    def fire_trigger(self) -> None:
        pass

    def emergency_stop(self) -> None:
        self.emergency_count += 1

    def force_deactivate(self) -> None:
        self.desired.append(None)

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
    def _coordinator(self) -> tuple[LEDDispatchCoordinator, _Adapter, _Runner, GoveeOwnerStateMachine]:
        adapter = _Adapter()
        runner = _Runner()
        owner = GoveeOwnerStateMachine()
        return (
            LEDDispatchCoordinator(adapter, runner, owner, _Config()),
            adapter,
            runner,
            owner,
        )

    def test_realtime_decision_sets_runner_without_cloud_trigger(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator()

        self.assertTrue(coordinator.trigger(_decision()))

        self.assertEqual(adapter.trigger_calls, [])
        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)
        self.assertEqual(runner.desired[-1].effect_name, "groove_chase_blue")

    def test_realtime_to_cloud_handoff_stands_down_runner_then_triggers_cloud(self) -> None:
        coordinator, adapter, runner, owner = self._coordinator()
        coordinator.trigger(_decision())

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


if __name__ == "__main__":
    unittest.main()
