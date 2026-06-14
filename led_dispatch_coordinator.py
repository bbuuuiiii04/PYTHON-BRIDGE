"""Dispatch coordinator for cloud DIY and realtime Govee backends."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from .govee_owner_state import GoveeOwnerStateMachine, OwnerState
from .govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
from .led_models import LEDConfig, LEDLookDecision


def _stable_seed(value: str) -> int:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False) & 0x7FFFFFFF


class LEDDispatchCoordinator:
    """Duck-typed adapter surface used by StateManager."""

    def __init__(
        self,
        adapter,
        runner: GoveeRealtimeRunner,
        owner: GoveeOwnerStateMachine,
        config: LEDConfig,
        *,
        time_fn=None,
    ) -> None:
        self._adapter = adapter
        self._runner = runner
        self._owner = owner
        self._config = config
        self._time_fn = time_fn or time.monotonic
        self._tactical_blackout_count = 0
        self._realtime_trigger_count = 0

    def trigger(self, decision: LEDLookDecision) -> bool:
        if self._is_operator_blackout(decision):
            self._runner.emergency_stop()
            self._owner.force_release()
            return bool(self._adapter.trigger(decision))

        backend = str(getattr(decision, "backend", "cloud_diy") or "cloud_diy")
        if backend == "realtime_razer":
            if self._owner.current() == OwnerState.CLOUD_DIY:
                self._owner.force_release()
            if not self._owner.acquire(OwnerState.REALTIME_RAZER):
                return False
            self._runner.set_desired(self._spec_from_decision(decision))
            self._realtime_trigger_count += 1
            return True

        if self._owner.current() == OwnerState.REALTIME_RAZER:
            self._runner.set_desired(None)
            self._owner.release(OwnerState.REALTIME_RAZER)
        accepted = bool(self._adapter.trigger(decision))
        if accepted:
            if self._owner.current() == OwnerState.NONE:
                self._owner.acquire(OwnerState.CLOUD_DIY)
        return accepted

    def tactical_blackout(self, decision: LEDLookDecision | None = None) -> bool:
        if self._owner.current() == OwnerState.CLOUD_DIY:
            self._owner.force_release()
        if not self._owner.acquire(OwnerState.REALTIME_RAZER):
            return False
        look_name = getattr(decision, "look", "tactical_blackout") if decision is not None else "tactical_blackout"
        self._runner.set_desired(
            EffectSpec(
                effect_name="blackout",
                params={},
                seed=_stable_seed(f"{look_name}:tactical_blackout"),
                applied_monotonic=self._time_fn(),
            )
        )
        self._tactical_blackout_count += 1
        return True

    def status(self) -> dict[str, Any]:
        payload = self._adapter.status()
        if not isinstance(payload, dict):
            payload = {}
        payload = dict(payload)
        payload["realtime"] = {
            "owner": self._owner.current().value,
            "realtime_trigger_count": self._realtime_trigger_count,
            "tactical_blackout_count": self._tactical_blackout_count,
            **self._runner.status(),
        }
        return payload

    def shutdown(self) -> bool:
        runner_ok = self._runner.stop()
        adapter_shutdown = getattr(self._adapter, "shutdown", None)
        adapter_ok = bool(adapter_shutdown()) if callable(adapter_shutdown) else True
        return runner_ok and adapter_ok

    def close(self) -> bool:
        return self.shutdown()

    def _is_operator_blackout(self, decision: LEDLookDecision) -> bool:
        return (
            str(getattr(decision, "action", "")) == "off"
            or str(getattr(decision, "look", "")) == self._config.blackout
        )

    def _spec_from_decision(self, decision: LEDLookDecision) -> EffectSpec:
        return EffectSpec(
            effect_name=str(getattr(decision, "scene_ref", "")),
            params=dict(getattr(decision, "params", {}) or {}),
            seed=_stable_seed(str(getattr(decision, "look", ""))),
            applied_monotonic=self._time_fn(),
        )
