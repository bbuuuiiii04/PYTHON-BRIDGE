"""Policy-only LED Look Director for Phase 3.

This module intentionally avoids transport/network I/O. It only computes which
configured look should be active given manual and emergency policy inputs.
"""
from __future__ import annotations

import random
from dataclasses import asdict, replace
from fractions import Fraction
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


def plan_backend_sequence(
    look_names: Iterable[str],
    backend_of: Callable[[str], str],
) -> tuple[str, ...]:
    """Deterministic, evenly-interleaved backend sequence for one role's
    (already-filtered) bank.

    Partition the names by backend preserving first-seen order, then emit one
    backend label per future pick -- length == len(look_names) -- with the
    smaller subset's slots spread evenly through the larger's. Ordering: the
    larger subset leads; on a size tie 'realtime_razer' leads (F2-forward). A
    single-backend bank returns that backend uniformly. Empty input -> ().

    No RNG enters here: two directors with the same bank get the same plan, so
    which transport a role runs on is a fixed rotation, not a per-session coin
    flip. 6 realtime + 2 cloud -> (rt, rt, cloud, rt, rt, rt, cloud, rt).
    """
    names = tuple(look_names)
    if not names:
        return ()
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for name in names:
        backend = backend_of(name)
        if backend not in groups:
            groups[backend] = []
            order.append(backend)
        groups[backend].append(name)
    if len(order) == 1:
        return tuple(order[0] for _ in names)
    # Leader order: larger subset first; ties -> realtime_razer, then first-seen.
    ranked = sorted(
        order,
        key=lambda b: (-len(groups[b]), b != "realtime_razer", order.index(b)),
    )
    rank_of = {backend: i for i, backend in enumerate(ranked)}
    # Even interleave: give each element the fractional position (k+0.5)/size
    # within its subset, merge all elements sorted by that position, and break
    # equal positions toward the leader. Fraction keeps the ties exact.
    slots = [
        (Fraction(2 * k + 1, 2 * len(groups[backend])), rank_of[backend], backend)
        for backend in order
        for k in range(len(groups[backend]))
    ]
    slots.sort(key=lambda slot: (slot[0], slot[1]))
    return tuple(backend for _, _, backend in slots)


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
        # AWR-149: shuffle bags and within-transport cursors are keyed by
        # (role, backend). The deterministic plan picks WHICH transport a pick
        # runs on; these pick WHICH look inside that transport, so RNG never
        # decides transport.
        self._role_shuffle_bags: dict[tuple[str, str], tuple[str, ...]] = {}
        self._role_backend_cursors: dict[tuple[str, str], int] = {}
        self._manual_override: str = ""
        self._emergency_blackout: bool = False
        self._last_decision: LEDLookDecision | None = None
        self._last_reason: str = "not_started"
        self._last_source: str = "policy"
        self._role_cursors: dict[str, int] = {}
        self._queued_post_drop_look: str = ""
        # AWR-149: every role starts at plan index 0 (realtime-leading) so the
        # mixed-transport rotation is deterministic across bridge relaunches --
        # no RNG in the cursor. Look variety still comes from the shuffle bags.
        for role in _AUTOMATION_ROLE_ORDER:
            self._role_cursors[role] = 0

    def reset_for_track(self) -> None:
        """No-op: the deterministic plan/backend cursors deliberately persist
        across tracks (AWR-149).

        Kept for call-site parity with ``state_manager.py``; resetting here
        would snap every role back to plan index 0 on each track load and
        re-flatten the transport rotation.
        """
        pass

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
        # AWR-149: preview through the same plan as a commit, but filterless
        # (no eligibility/preference) -- this preserves the pre-existing preview
        # gap exactly. Peek the (role, backend) bag with RNG restore so nothing
        # (cursor, bag, or RNG) is mutated.
        known = tuple(n for n in look_names if n in self._config.looks)
        if not known:
            return None
        plan = plan_backend_sequence(
            known, lambda n: self._config.looks[n].backend
        )
        if not plan:
            return None
        cursor = self._role_cursors.get(role, 0)
        chosen_backend = plan[cursor % len(plan)]
        subset = tuple(
            n for n in known if self._config.looks[n].backend == chosen_backend
        )
        backend_cursor = self._role_backend_cursors.get((role, chosen_backend), 0)
        look_name = self._look_name_for_backend(
            role, chosen_backend, subset, backend_cursor, peek=True
        )
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
                return self._decision_for_look(
                    look_name,
                    reason="paired_post_drop",
                    source="automation",
                    priority=2,
                    role=normalized_role,
                )
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
        # AWR-149: drop unknown names, then let the deterministic plan choose the
        # transport for this pick and the (role, backend) bag choose the look.
        # Both transports stay reachable in every role that has both -- this
        # replaces the WI-7 sticky latch, which coin-flipped a role onto one
        # transport for a whole session.
        known = tuple(n for n in look_names if n in self._config.looks)
        if not known:
            return None
        plan = plan_backend_sequence(
            known, lambda n: self._config.looks[n].backend
        )
        if not plan:
            return None
        cursor = self._role_cursors.get(normalized_role, 0)
        chosen_backend = plan[cursor % len(plan)]
        subset = tuple(
            n for n in known if self._config.looks[n].backend == chosen_backend
        )
        backend_cursor = self._role_backend_cursors.get(
            (normalized_role, chosen_backend), 0
        )
        look_name = self._look_name_for_backend(
            normalized_role, chosen_backend, subset, backend_cursor
        )
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
        # The role cursor advances the PLAN (which transport comes next); the
        # (role, backend) cursor advances only for the transport actually picked
        # and drives that transport's shuffle bag.
        self._role_cursors[normalized_role] = cursor + 1
        self._role_backend_cursors[(normalized_role, chosen_backend)] = (
            backend_cursor + 1
        )
        return decision

    def _look_name_for_backend(
        self,
        role: str,
        backend: str,
        subset: tuple[str, ...],
        cursor: int,
        *,
        peek: bool = False,
    ) -> str:
        """Pick a look within one transport's subset via the (role, backend)
        shuffle bag. ``cursor`` is the per-(role, backend) cursor."""
        if role not in self._shuffled_roles or len(subset) <= 1:
            return subset[cursor % len(subset)]
        key = (role, backend)
        bag = self._role_shuffle_bags.get(key, ())
        if cursor % len(subset) == 0 or not bag:
            if peek:
                # Preview the would-be shuffled bag while restoring RNG state so
                # the next real selection builds the exact same bag.
                state = self._rng.getstate()
                try:
                    shuffled = list(subset)
                    self._rng.shuffle(shuffled)
                finally:
                    self._rng.setstate(state)
                return tuple(shuffled)[cursor % len(subset)]
            shuffled = list(subset)
            self._rng.shuffle(shuffled)
            bag = tuple(shuffled)
            self._role_shuffle_bags[key] = bag
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
