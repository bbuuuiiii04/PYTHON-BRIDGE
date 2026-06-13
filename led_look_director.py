"""Policy-only LED Look Director for Phase 3.

This module intentionally avoids transport/network I/O. It only computes which
configured look should be active given manual and emergency policy inputs.
"""
from __future__ import annotations

import random
from dataclasses import asdict, replace
from typing import Iterable

from .led_models import (
    LEDConfig,
    LEDContext,
    LEDLookDecision,
    LEDLookDirectorStatus,
)

_AUTOMATION_ROLE_ORDER = (
    "ambient",
    "groove",
    "buildup",
    "pre_drop",
    "drop",
    "post_drop",
    "breakdown",
    "utility",
)
_AUTOMATION_ROLES = frozenset(_AUTOMATION_ROLE_ORDER)


class LEDLookDirector:
    """Minimal policy engine with emergency > manual > default ordering."""

    def __init__(
        self,
        config: LEDConfig,
        *,
        rng: random.Random | None = None,
        shuffled_roles: Iterable[str] = (),
    ) -> None:
        self._config = config
        self._rng = rng if rng is not None else random.Random()
        self._shuffled_roles = frozenset(str(role) for role in shuffled_roles)
        self._role_shuffle_bags: dict[str, tuple[str, ...]] = {}
        self._manual_override: str = ""
        self._emergency_blackout: bool = False
        self._last_decision: LEDLookDecision | None = None
        self._last_reason: str = "not_started"
        self._last_source: str = "policy"
        self._role_cursors: dict[str, int] = {
            role: 0 for role in _AUTOMATION_ROLE_ORDER
        }

    def set_manual_override(self, look_name: str | None) -> bool:
        """Set or clear manual override. Returns False when unknown look."""
        if look_name is None or look_name == "":
            self._manual_override = ""
            return True
        if look_name not in self._config.looks:
            return False
        self._manual_override = look_name
        return True

    def set_emergency_blackout(self, enabled: bool) -> None:
        self._emergency_blackout = bool(enabled)

    def tick(self, context: LEDContext | None = None) -> LEDLookDecision | None:
        """Compute one bounded decision with no I/O."""
        if not self._config.enabled:
            self._last_decision = None
            self._last_reason = "disabled"
            self._last_source = "policy"
            return None

        role = "utility"
        if context is not None:
            role = str(context.role or "").strip()
            if not role:
                role = ""
        default_role = role or "utility"

        emergency_active = self._emergency_blackout
        if context is not None and context.emergency_blackout:
            emergency_active = True

        if emergency_active:
            decision = self._decision_for_look(
                self._config.blackout,
                reason="emergency_blackout",
                source="emergency",
                priority=0,
                role="emergency",
            )
            decision = self._apply_target_override(decision, context)
            self._record_decision(decision)
            return decision

        manual = self._manual_override
        if context is not None and context.manual_look:
            manual = context.manual_look
        if manual:
            if manual in self._config.looks:
                decision = self._decision_for_look(
                    manual,
                    reason="manual_override",
                    source="manual",
                    priority=1,
                    role="manual",
                )
                decision = self._apply_target_override(decision, context)
                self._record_decision(decision)
                return decision
            self._last_decision = None
            self._last_reason = "manual_override_unknown_look"
            self._last_source = "manual"
            return None

        if self._config.automation_enabled:
            decision = self._automation_decision_for_role(role)
            if decision is None:
                self._last_decision = None
                reason_role = role if role else "empty_role"
                self._last_reason = f"automation_no_look:{reason_role}"
                self._last_source = "automation"
                return None
            decision = self._apply_target_override(decision, context)
            self._record_decision(decision)
            return decision

        decision = self._decision_for_look(
            self._config.safe_default,
            reason="safe_default",
            source="policy",
            priority=2,
            role=default_role,
        )
        self._record_decision(decision)
        return decision

    def status(self) -> dict:
        current_look = ""
        if self._last_decision is not None:
            current_look = self._last_decision.look
        payload = LEDLookDirectorStatus(
            available=True,
            enabled=self._config.enabled,
            dry_run=self._config.dry_run,
            automation_enabled=self._config.automation_enabled,
            automation_offset_s=float(self._config.automation.offset_s),
            scripted_mode_automation=self._config.safety.scripted_mode_automation,
            current_look=current_look,
            last_reason=self._last_reason,
            last_source=self._last_source,
            manual_override=self._manual_override,
            emergency_blackout=self._emergency_blackout,
            role_cursors=dict(self._role_cursors),
        )
        return asdict(payload)

    def _automation_decision_for_role(self, role: str) -> LEDLookDecision | None:
        if role not in _AUTOMATION_ROLES:
            return None
        normalized_role = role
        bank = self._config.banks.get("default")
        if bank is None:
            return None
        look_names = getattr(bank, normalized_role, ())
        if not look_names:
            return None
        cursor = self._role_cursors.get(normalized_role, 0)
        look_name = self._look_name_for_role(normalized_role, look_names, cursor)
        if look_name not in self._config.looks:
            return None
        decision = self._decision_for_look(
            look_name,
            reason=f"role_entry:{normalized_role}",
            source="automation",
            priority=2,
            role=normalized_role,
        )
        self._role_cursors[normalized_role] = cursor + 1
        return decision

    def _look_name_for_role(
        self,
        role: str,
        look_names: tuple[str, ...],
        cursor: int,
    ) -> str:
        if role not in self._shuffled_roles or len(look_names) <= 1:
            return look_names[cursor % len(look_names)]
        bag = self._role_shuffle_bags.get(role, ())
        if cursor % len(look_names) == 0 or not bag:
            shuffled = list(look_names)
            self._rng.shuffle(shuffled)
            bag = tuple(shuffled)
            self._role_shuffle_bags[role] = bag
        return bag[cursor % len(bag)]

    def _decision_for_look(
        self,
        look_name: str,
        *,
        reason: str,
        source: str,
        priority: int,
        role: str,
    ) -> LEDLookDecision:
        look = self._config.looks[look_name]
        return LEDLookDecision(
            look=look_name,
            target=look.target,
            action=look.action,
            scene_ref=look.scene_ref,
            reason=reason,
            source=source,
            priority=priority,
            role=role,
        )

    def _record_decision(self, decision: LEDLookDecision) -> None:
        self._last_decision = decision
        self._last_reason = decision.reason
        self._last_source = decision.source

    def _apply_target_override(
        self,
        decision: LEDLookDecision,
        context: LEDContext | None,
    ) -> LEDLookDecision:
        if context is None:
            return decision
        override = str(context.target_override or "").strip()
        if not override or override == decision.target:
            return decision
        if override not in self._config.targets:
            return decision
        return replace(decision, target=override)
