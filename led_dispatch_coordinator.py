"""Dispatch coordinator for cloud DIY and realtime Govee backends."""
from __future__ import annotations

import hashlib
import logging
import os as _os
import time
from typing import Any

from .govee_frame_renderer import default_sync_mode, default_beat_division
from .govee_owner_state import GoveeOwnerStateMachine, OwnerState
from .govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
from .led_models import LEDConfig, LEDLookDecision
from .bridge_fmt import log_changed

log = logging.getLogger("led_dispatch_coordinator")

_DEFAULT_WHITE_TEMPLATES = frozenset({
    "drop_white_aggressive",
    "post_drop_white_shatter",
    "buildup_white_zone_strobe",
    "buildup_white_half_strobe",
})


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
        white_templates: Any = None,
    ) -> None:
        self._adapter = adapter
        self._runner = runner
        self._owner = owner
        self._config = config
        self._time_fn = time_fn or time.monotonic
        self._tactical_blackout_count = 0
        self._realtime_trigger_count = 0
        # `white_templates` (explicit, from the loaded LaserColorMap — see
        # laser_color_engine.load_laser_color_map) takes priority over a
        # `laser_color_white_templates` attribute on `config`, which LEDConfig does
        # not declare today; both fall back to the coordinator's own defaults.
        configured_white = (
            white_templates
            if white_templates is not None
            else getattr(config, "laser_color_white_templates", None)
        )
        self._white_templates = frozenset(str(name) for name in (configured_white or _DEFAULT_WHITE_TEMPLATES))
        self._last_white_moment = False

        # WI-3 min-dwell: suppress same-role re-picks inside the dwell window
        self._min_dwell_enabled: bool = _os.environ.get("RBSS_LED_MIN_DWELL", "1") != "0"
        self._last_dispatch_mono: float = 0.0
        self._last_dispatch_role: str = ""

        # WI-4 cancel-pending: drain queued cloud DIY on RT acquire
        self._cancel_pending_enabled: bool = _os.environ.get("RBSS_LED_CANCEL_PENDING", "1") != "0"

        # WI-5 transport-switch cooldown (default OFF — WI-1/2/3 already eliminate the flap)
        self._transport_cooldown_enabled: bool = _os.environ.get("RBSS_LED_TRANSPORT_COOLDOWN", "0") == "1"
        self._last_transport: str = ""
        self._last_transport_mono: float = 0.0

        # WI-8 observability counters
        self._dwell_suppressed_count: int = 0
        self._cancel_pending_total: int = 0
        self._transport_cooldown_count: int = 0

    def trigger(self, decision: LEDLookDecision) -> bool:
        self._last_white_moment = False
        # Operator blackout is unconditionally first — bypasses ALL gates.
        if self._is_operator_blackout(decision):
            self._runner.emergency_stop()
            self._owner.force_release()
            return bool(self._adapter.trigger(decision))

        backend = str(getattr(decision, "backend", "cloud_diy") or "cloud_diy")
        role = str(getattr(decision, "role", ""))
        now = self._time_fn()

        # WI-3 min-dwell gate: suppress same-role re-picks within the dwell window.
        # Keyed on role so groove→buildup→drop is never throttled (role changes pass).
        if self._min_dwell_enabled:
            dwell_s = float(getattr(getattr(self._config, "rate_limits", None), "min_look_dwell_s", 1.5) or 1.5)
            if (
                role == self._last_dispatch_role
                and (now - self._last_dispatch_mono) < dwell_s
            ):
                log.debug(
                    "[RGB] dwell-suppressed role=%s look=%s dt=%.3f",
                    role,
                    getattr(decision, "look", ""),
                    now - self._last_dispatch_mono,
                )
                self._dwell_suppressed_count += 1
                return False

        # WI-5 transport-switch cooldown (default OFF).
        # Exempts: role changes, drop/pre_drop/breakdown, operator blackout (handled above).
        _EXEMPT_ROLES = frozenset({"drop", "pre_drop", "breakdown"})
        if self._transport_cooldown_enabled and role not in _EXEMPT_ROLES:
            cooldown_s = float(
                getattr(
                    getattr(self._config, "rate_limits", None),
                    "transport_switch_cooldown_s",
                    2.0,
                ) or 2.0
            )
            if (
                self._last_transport
                and backend != self._last_transport
                and role == self._last_dispatch_role
                and (now - self._last_transport_mono) < cooldown_s
            ):
                log.debug(
                    "[RGB] transport-cooldown role=%s look=%s backend=%s last=%s dt=%.3f",
                    role,
                    getattr(decision, "look", ""),
                    backend,
                    self._last_transport,
                    now - self._last_transport_mono,
                )
                self._transport_cooldown_count += 1
                return False

        if backend == "realtime_razer":
            if self._owner.current() == OwnerState.CLOUD_DIY:
                # WI-4: drain queued cloud commands before acquiring RT so a late
                # cloud response cannot land and flip the device out of razer mode.
                if self._cancel_pending_enabled:
                    cancel = getattr(self._adapter, "cancel_pending", None)
                    if callable(cancel):
                        n = cancel()
                        self._cancel_pending_total += n
                self._owner.force_release()
            if not self._owner.acquire(OwnerState.REALTIME_RAZER):
                return False
            self._runner.set_desired(self._spec_from_decision(decision))
            self._runner.fire_trigger()
            self._realtime_trigger_count += 1
            self._last_dispatch_mono = now
            self._last_dispatch_role = role
            self._last_transport = backend
            self._last_transport_mono = now
            if log_changed("led_live", (getattr(decision, "look", ""), "realtime", role)):
                log.info(
                    "[LED] look=%s role=%s via=realtime",
                    getattr(decision, "look", ""), role,
                )
            return True

        if self._owner.current() == OwnerState.REALTIME_RAZER:
            self._runner.force_deactivate()
            self._owner.release(OwnerState.REALTIME_RAZER)
        accepted = bool(self._adapter.trigger(decision))
        if accepted:
            if self._owner.current() == OwnerState.NONE:
                self._owner.acquire(OwnerState.CLOUD_DIY)
            self._last_dispatch_mono = now
            self._last_dispatch_role = role
            self._last_transport = backend
            self._last_transport_mono = now
            if log_changed("led_live", (getattr(decision, "look", ""), "cloud", role)):
                log.info(
                    "[LED] look=%s role=%s via=cloud",
                    getattr(decision, "look", ""), role,
            )
            # WI-6: notify runner that a cloud DIY was dispatched so it can
            # reconcile if a late response flips the strip out of razer mode.
            rate_limits = getattr(self._config, "rate_limits", None)
            window_s = float(getattr(rate_limits, "rt_reconcile_window_s", 5.0) or 5.0)
            interval_s = float(getattr(rate_limits, "rt_reconcile_interval_s", 1.0) or 1.0)
            note = getattr(self._runner, "note_cloud_dispatch", None)
            if callable(note):
                note(now, window_s=window_s, interval_s=interval_s)
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
            # WI-8 observability counters
            "dwell_suppressed_count": self._dwell_suppressed_count,
            "cancel_pending_total": self._cancel_pending_total,
            "transport_cooldown_count": self._transport_cooldown_count,
            **self._runner.status(),
        }
        return payload

    def last_white_moment(self) -> bool:
        return self._last_white_moment

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
        scene_ref = str(getattr(decision, "scene_ref", ""))
        params = dict(getattr(decision, "params", {}) or {})
        sync_mode = str(params.get("sync_mode") or default_sync_mode(scene_ref))
        beat_division = float(params.get("beat_division") or default_beat_division(scene_ref))
        self._last_white_moment = scene_ref in self._white_templates
        return EffectSpec(
            effect_name=scene_ref,
            params=params,
            seed=_stable_seed(str(getattr(decision, "look", ""))),
            applied_monotonic=self._time_fn(),
            sync_mode=sync_mode,
            beat_division=beat_division,
        )
