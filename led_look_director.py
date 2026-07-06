"""Policy-only LED Look Director for Phase 3.

This module intentionally avoids transport/network I/O. It only computes which
configured look should be active given manual and emergency policy inputs.
"""
from __future__ import annotations

import os as _os
import random
from dataclasses import asdict, replace
from typing import Callable, Iterable, Optional

from .led_models import (
    LEDConfig,
    LEDContext,
    LEDLookDecision,
    LEDLookDirectorStatus,
)

LED_AUTOMATION_ROLE_ORDER = (
    "ambient",
    "groove",
    "buildup",
    "pre_drop",
    "drop",
    "post_drop",
    "breakdown",
    "utility",
)
_AUTOMATION_ROLE_ORDER = LED_AUTOMATION_ROLE_ORDER
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
        self._role_cursors: dict[str, int] = {}
        self._queued_post_drop_look: str = ""
        # WI-7 transport-sticky: remember the last dispatched backend per role
        # so consecutive same-role selections stay on the same transport.
        self._transport_sticky_enabled: bool = _os.environ.get("RBSS_LED_TRANSPORT_STICKY", "1") != "0"
        self._last_role_backend: dict[str, str] = {}  # role → last backend
        bank = self._config.banks.get("default")
        for role in _AUTOMATION_ROLE_ORDER:
            look_names = getattr(bank, role, ()) if bank else ()
            if look_names:
                self._role_cursors[role] = self._rng.randrange(len(look_names))
            else:
                self._role_cursors[role] = 0

    def reset_for_track(self) -> None:
        """Clear sticky staleness on track load."""
        self._last_role_backend.clear()

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
            decision = self._automation_decision_for_role(
                role,
                diy_eligible=(context.diy_eligible if context is not None else None),
                look_preference=(context.look_preference if context is not None else None),
            )
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
            automation_cloud_offset_s=float(self._config.automation.cloud_offset_s),
            automation_realtime_offset_s=float(
                self._config.automation.realtime_offset_s
            ),
            scripted_mode_automation=self._config.safety.scripted_mode_automation,
            current_look=current_look,
            last_reason=self._last_reason,
            last_source=self._last_source,
            manual_override=self._manual_override,
            emergency_blackout=self._emergency_blackout,
            role_cursors=dict(self._role_cursors),
        )
        status = asdict(payload)
        status["queued_post_drop_look"] = self._queued_post_drop_look
        status["post_drop_cycle_beats"] = float(self._config.post_drop_cycle_beats)
        status["scripted_mode"] = {
            "default_role": self._config.scripted_mode.default_role,
            "role_map": dict(self._config.scripted_mode.role_map),
        }
        return status

    def has_role_look(self, role: str) -> bool:
        if role not in _AUTOMATION_ROLES:
            return False
        bank = self._config.banks.get("default")
        if bank is None:
            return False
        look_names = getattr(bank, role, ())
        return any(look_name in self._config.looks for look_name in look_names)

    def preview_role(self, role: str) -> LEDLookDecision | None:
        """Return the next automation decision for a role without advancing it."""
        if role not in _AUTOMATION_ROLES:
            return None
        bank = self._config.banks.get("default")
        if bank is None:
            return None
        if role == "post_drop" and self._queued_post_drop_look in self._config.looks:
            return self._decision_for_look(
                self._queued_post_drop_look,
                reason="role_preview:paired_post_drop",
                source="automation",
                priority=2,
                role=role,
            )
        look_names = getattr(bank, role, ())
        if not look_names:
            return None
        cursor = self._role_cursors.get(role, 0)
        look_name = self._look_name_for_role(role, look_names, cursor, peek=True)
        if look_name not in self._config.looks:
            return None
        return self._decision_for_look(
            look_name,
            reason=f"role_preview:{role}",
            source="automation",
            priority=2,
            role=role,
        )

    def commit_role(
        self,
        role: str,
        *,
        diy_eligible: Optional[Callable[[str], bool]] = None,
        look_preference: Optional[Callable[[str], bool]] = None,
    ) -> LEDLookDecision | None:
        """Select the next automation look for a role and advance once."""
        if not self._config.enabled or not self._config.automation_enabled:
            return None
        return self._automation_decision_for_role(
            role,
            diy_eligible=diy_eligible,
            look_preference=look_preference,
        )

    def clear_queued_post_drop(self) -> None:
        """Drop any pending paired post_drop look.

        Called when the drop lifecycle is torn down (track/deck change, stop,
        resume, phrase interruption) so a paired post_drop queued for one drop
        cannot leak across the teardown and fire on the next track/deck.
        """
        self._queued_post_drop_look = ""

    def paired_post_drop_look(self, drop_look: str) -> str:
        pair = self._config.drop_pairs.get(str(drop_look))
        if pair is None:
            return ""
        return pair.post_drop if pair.post_drop in self._config.looks else ""

    def drop_duration_beats(self, drop_look: str) -> float:
        pair = self._config.drop_pairs.get(str(drop_look))
        if pair is None:
            return 8.0
        return max(0.001, float(pair.duration_beats))

    def post_drop_cycle_beats(self) -> float:
        return max(0.001, float(self._config.post_drop_cycle_beats))

    def _automation_decision_for_role(
        self,
        role: str,
        *,
        diy_eligible: Optional[Callable[[str], bool]] = None,
        look_preference: Optional[Callable[[str], bool]] = None,
    ) -> LEDLookDecision | None:
        if role not in _AUTOMATION_ROLES:
            return None
        normalized_role = role
        bank = self._config.banks.get("default")
        if bank is None:
            return None
        if normalized_role == "post_drop" and self._queued_post_drop_look:
            look_name = self._queued_post_drop_look
            self._queued_post_drop_look = ""
            if look_name in self._config.looks:
                decision = self._decision_for_look(
                    look_name,
                    reason="paired_post_drop",
                    source="automation",
                    priority=2,
                    role=normalized_role,
                )
                self._last_role_backend[normalized_role] = decision.backend
                return decision
        look_names = getattr(bank, normalized_role, ())
        if not look_names:
            return None
        # M1b WI-3: filter the bank by the color engine's DIY-eligibility
        # predicate.  Realtime/untagged looks are recolored, so the engine
        # returns True for them; only off-palette DIY looks are dropped.
        # Empty subset ⇒ keep the full bank (the C4 breakdown invariant: a
        # DIY-only bank must never be emptied by a non-matching palette).
        if diy_eligible is not None:
            eligible = tuple(n for n in look_names if diy_eligible(n))
            if eligible:
                look_names = eligible
        if look_preference is not None:
            preferred = tuple(n for n in look_names if look_preference(n))
            if preferred:
                look_names = preferred
        cursor = self._role_cursors.get(normalized_role, 0)
        # WI-7 transport-sticky: when flag is ON, prefer looks whose backend
        # matches the last dispatched backend for this role.
        if self._transport_sticky_enabled and normalized_role in self._last_role_backend:
            sticky_backend = self._last_role_backend[normalized_role]
            sticky_names = tuple(
                n for n in look_names
                if n in self._config.looks
                and self._config.looks[n].backend == sticky_backend
            )
            if sticky_names:
                # Select within the sticky subset using the cursor modulo its length
                look_name = self._look_name_for_role(normalized_role, sticky_names, cursor)
            else:
                # Fallback: no matching-backend candidates; use the full bank
                look_name = self._look_name_for_role(normalized_role, look_names, cursor)
        else:
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
        if normalized_role == "drop":
            self._queue_paired_post_drop(look_name)
        self._role_cursors[normalized_role] = cursor + 1
        self._last_role_backend[normalized_role] = decision.backend
        return decision

    def _look_name_for_role(
        self,
        role: str,
        look_names: tuple[str, ...],
        cursor: int,
        *,
        peek: bool = False,
    ) -> str:
        if role not in self._shuffled_roles or len(look_names) <= 1:
            return look_names[cursor % len(look_names)]
        bag = self._role_shuffle_bags.get(role, ())
        if cursor % len(look_names) == 0 or not bag:
            if peek:
                # Preview the would-be shuffled bag while restoring RNG state so
                # the next real selection builds the exact same bag.
                state = self._rng.getstate()
                try:
                    shuffled = list(look_names)
                    self._rng.shuffle(shuffled)
                finally:
                    self._rng.setstate(state)
                return tuple(shuffled)[cursor % len(look_names)]
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
            backend=look.backend,
            params=look.params,
            color_source=look.color_source,
        )

    def _record_decision(self, decision: LEDLookDecision) -> None:
        if decision.role in {"drop", "manual"}:
            self._queue_paired_post_drop(decision.look)
        self._last_decision = decision
        self._last_reason = decision.reason
        self._last_source = decision.source

    def _queue_paired_post_drop(self, drop_look: str) -> None:
        paired = self.paired_post_drop_look(drop_look)
        self._queued_post_drop_look = paired

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
