"""Pure active-deck authority resolver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

FADER_DOWN_MAX_NORM = 0.02
FADER_TOP_MIN_NORM = 0.98
BASS_NEUTRAL_NORM = 0.5
BASS_NEUTRAL_TOL = 0.03
BASS_EQUAL_TOL = 0.01
MIXER_STALE_AFTER_S = 1.0
RB_MASTER_STALE_AFTER_S = 2.0
ACTIVE_DECK_STABILITY_S = 0.15


@dataclass(frozen=True)
class ResolverState:
    pending_deck: int = 0
    pending_since: float = 0.0
    pending_reason: str = ""


@dataclass(frozen=True)
class ResolverDeckInput:
    playing: bool
    upfader_raw: float
    upfader_norm: float
    upfader_label: str
    low_raw: float
    low_norm: float
    low_label: str


@dataclass(frozen=True)
class ActiveDeckDecision:
    active_deck: int
    authority_reason: str
    fallback_reason: str
    state: ResolverState
    pending_deck: int = 0
    stable: bool = True


def label_upfader(norm: float) -> str:
    if norm <= FADER_DOWN_MAX_NORM:
        return "down"
    if norm >= FADER_TOP_MIN_NORM:
        return "top"
    return "audible"


def label_low(norm: float) -> str:
    if abs(norm - BASS_NEUTRAL_NORM) <= BASS_NEUTRAL_TOL:
        return "neutral"
    return "high" if norm > BASS_NEUTRAL_NORM else "low"


def resolve_active_deck(
    *,
    current_active_deck: int,
    rb_master_deck: Optional[int],
    rb_master_deck_valid: bool,
    rb_master_deck_source: str,
    rb_master_deck_updated_at: float,
    rb_master_fallback_reason: str,
    deck: Mapping[int, ResolverDeckInput],
    mixer_valid: bool,
    mixer_updated_at: float,
    mixer_reason: str,
    state: ResolverState,
    now: float,
) -> ActiveDeckDecision:
    """Resolve the show-driving deck from decoded Deck 1/2 mixer state."""
    mixer_age = now - mixer_updated_at if mixer_updated_at > 0 else float("inf")
    if not mixer_valid or mixer_age > MIXER_STALE_AFTER_S:
        reason = "stale" if mixer_valid else (mixer_reason or "invalid")
        return _fallback_decision(
            current_active_deck=current_active_deck,
            rb_master_deck=rb_master_deck,
            rb_master_deck_valid=rb_master_deck_valid,
            rb_master_deck_source=rb_master_deck_source,
            rb_master_deck_updated_at=rb_master_deck_updated_at,
            rb_master_fallback_reason=rb_master_fallback_reason,
            deck=deck,
            state=state,
            now=now,
            reason=reason,
        )

    if 1 not in deck or 2 not in deck:
        return _candidate_decision(
            candidate=0,
            reason="idle_no_audible",
            fallback_reason="partial_deck_state",
            current_active_deck=current_active_deck,
            deck=deck,
            state=state,
            now=now,
        )

    eligible = {num for num in (1, 2) if _eligible(deck[num])}
    if not eligible:
        return _candidate_decision(
            candidate=0,
            reason="idle_no_audible",
            fallback_reason="no_eligible_deck",
            current_active_deck=current_active_deck,
            deck=deck,
            state=state,
            now=now,
        )
    if len(eligible) == 1:
        candidate = next(iter(eligible))
        return _candidate_decision(
            candidate=candidate,
            reason="only_audible",
            fallback_reason="",
            current_active_deck=current_active_deck,
            deck=deck,
            state=state,
            now=now,
        )

    top = {num for num in eligible if deck[num].upfader_label == "top"}
    if len(top) == 1:
        candidate = next(iter(top))
        return _candidate_decision(
            candidate=candidate,
            reason="fader_top",
            fallback_reason="",
            current_active_deck=current_active_deck,
            deck=deck,
            state=state,
            now=now,
        )
    if len(top) == 2:
        d1 = deck[1]
        d2 = deck[2]
        if d1.low_label == "neutral" and d2.low_label == "neutral":
            candidate = _usable_master(
                rb_master_deck,
                rb_master_deck_valid,
                rb_master_deck_source,
                rb_master_deck_updated_at,
                now,
                eligible,
            )
            if candidate is not None:
                return _candidate_decision(
                    candidate=candidate,
                    reason="rb_master_tie",
                    fallback_reason="",
                    current_active_deck=current_active_deck,
                    deck=deck,
                    state=state,
                    now=now,
                )
            return _hold_or_idle(
                current_active_deck, deck, eligible, state, now, "rb_master_unavailable_tie"
            )
        if abs(d1.low_norm - d2.low_norm) > BASS_EQUAL_TOL:
            candidate = 1 if d1.low_norm > d2.low_norm else 2
            return _candidate_decision(
                candidate=candidate,
                reason="bass_dominance",
                fallback_reason="",
                current_active_deck=current_active_deck,
                deck=deck,
                state=state,
                now=now,
            )
        if current_active_deck in eligible:
            return _hold(current_active_deck, "hold_current", state)
        candidate = _usable_master(
            rb_master_deck,
            rb_master_deck_valid,
            rb_master_deck_source,
            rb_master_deck_updated_at,
            now,
            eligible,
        )
        if candidate is not None:
            return _candidate_decision(
                candidate=candidate,
                reason="rb_master_tie",
                fallback_reason="",
                current_active_deck=current_active_deck,
                deck=deck,
                state=state,
                now=now,
            )
        return _idle("rb_master_unavailable_tie", state)

    if current_active_deck in eligible:
        return _hold(current_active_deck, "hold_current", state)
    candidate = _usable_master(
        rb_master_deck,
        rb_master_deck_valid,
        rb_master_deck_source,
        rb_master_deck_updated_at,
        now,
        eligible,
    )
    if candidate is not None:
        return _candidate_decision(
            candidate=candidate,
            reason="rb_master_tie",
            fallback_reason="",
            current_active_deck=current_active_deck,
            deck=deck,
            state=state,
            now=now,
        )
    return _idle("rb_master_unavailable_tie", state)


def _eligible(reading: ResolverDeckInput) -> bool:
    return bool(reading.playing) and reading.upfader_label != "down"


def _fallback_decision(
    *,
    current_active_deck: int,
    rb_master_deck: Optional[int],
    rb_master_deck_valid: bool,
    rb_master_deck_source: str,
    rb_master_deck_updated_at: float,
    rb_master_fallback_reason: str,
    deck: Mapping[int, ResolverDeckInput],
    state: ResolverState,
    now: float,
    reason: str,
) -> ActiveDeckDecision:
    usable = _usable_master(
        rb_master_deck,
        rb_master_deck_valid,
        rb_master_deck_source,
        rb_master_deck_updated_at,
        now,
        {1, 2},
    )
    if usable is not None:
        return _candidate_decision(
            candidate=usable,
            reason="mixer_invalid_fallback",
            fallback_reason=reason,
            current_active_deck=current_active_deck,
            deck=deck,
            state=state,
            now=now,
        )
    current = deck.get(current_active_deck)
    if current_active_deck in (1, 2) and current is not None and current.playing:
        return ActiveDeckDecision(
            active_deck=current_active_deck,
            authority_reason="mixer_invalid_fallback",
            fallback_reason=rb_master_fallback_reason or "rb_master_unavailable_fallback",
            state=ResolverState(),
        )
    return ActiveDeckDecision(
        active_deck=0,
        authority_reason="mixer_invalid_fallback",
        fallback_reason=rb_master_fallback_reason or "rb_master_unavailable_fallback",
        state=ResolverState(),
    )


def _candidate_decision(
    *,
    candidate: int,
    reason: str,
    fallback_reason: str,
    current_active_deck: int,
    deck: Mapping[int, ResolverDeckInput],
    state: ResolverState,
    now: float,
) -> ActiveDeckDecision:
    if candidate == current_active_deck:
        return ActiveDeckDecision(candidate, reason, fallback_reason, ResolverState())
    if candidate == 0:
        return ActiveDeckDecision(0, reason, fallback_reason, ResolverState())

    if state.pending_deck != candidate or state.pending_reason != reason:
        next_state = ResolverState(candidate, now, reason)
        return _waiting_decision(
            current_active_deck, deck, next_state, reason, fallback_reason
        )
    if now - state.pending_since < ACTIVE_DECK_STABILITY_S:
        return _waiting_decision(
            current_active_deck, deck, state, reason, fallback_reason
        )
    return ActiveDeckDecision(candidate, reason, fallback_reason, ResolverState())


def _waiting_decision(
    current_active_deck: int,
    deck: Mapping[int, ResolverDeckInput],
    state: ResolverState,
    reason: str,
    fallback_reason: str,
) -> ActiveDeckDecision:
    current = deck.get(current_active_deck)
    if current_active_deck in (1, 2) and current is not None and _eligible(current):
        return ActiveDeckDecision(
            current_active_deck,
            "hold_current",
            fallback_reason,
            state,
            pending_deck=state.pending_deck,
            stable=False,
        )
    return ActiveDeckDecision(
        0,
        "idle_no_audible",
        fallback_reason or reason,
        state,
        pending_deck=state.pending_deck,
        stable=False,
    )


def _usable_master(
    rb_master_deck: Optional[int],
    rb_master_deck_valid: bool,
    rb_master_deck_source: str,
    rb_master_deck_updated_at: float,
    now: float,
    eligible: set[int],
) -> Optional[int]:
    if rb_master_deck not in eligible or rb_master_deck not in (1, 2):
        return None
    if not rb_master_deck_valid or rb_master_deck_updated_at <= 0.0:
        return None
    if rb_master_deck_source in ("", "unknown", "osc", "legacy_osc"):
        return None
    if now - rb_master_deck_updated_at > RB_MASTER_STALE_AFTER_S:
        return None
    return int(rb_master_deck)


def _hold_or_idle(
    current_active_deck: int,
    deck: Mapping[int, ResolverDeckInput],
    eligible: set[int],
    state: ResolverState,
    now: float,
    fallback_reason: str,
) -> ActiveDeckDecision:
    if current_active_deck in eligible:
        return _hold(current_active_deck, "hold_current", state)
    return _idle(fallback_reason, state)


def _hold(active_deck: int, reason: str, state: ResolverState) -> ActiveDeckDecision:
    return ActiveDeckDecision(active_deck, reason, "", ResolverState())


def _idle(fallback_reason: str, state: ResolverState) -> ActiveDeckDecision:
    return ActiveDeckDecision(0, "idle_no_audible", fallback_reason, ResolverState())
