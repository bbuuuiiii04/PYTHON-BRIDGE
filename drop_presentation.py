"""Drop presentation policy: pure planner + session state (Package 3 of AWR-119).

Behavior contract: docs/architecture/drop_presentation_authority.md — its ladder,
edge rulings, and Required Behavior Tests are the acceptance oracle for this
module. Implementation spec: docs/plans/active/drop_presentation_impl_spec.md.

This module owns no threads and performs no blocking I/O on any hot path:
  - `plan_track()`, `runway_beats()`, `resolve_presentation()`, and
    `gearshift_qualifies()` are pure functions of their arguments — no I/O, no
    randomness, no clock reads.
  - `SessionState` is pure in-memory bookkeeping (counters/latches); it never
    touches a file or a clock.
  - `WindowMachine` is a pure beat-driven state machine: its `tick()` reads only
    the `WindowInputs` it is given and never calls `time.time()`/`time.monotonic()`.
  - `LearnedStore` is the one piece that touches a file, and only via `load()`
    (a plain read) and `to_dict()` (pure serialization). Persisting a mutation is
    the CALLER's job (state_manager.py): it must ride a background writer thread,
    never the state-manager tick path — see `docs/plans/active/
    drop_presentation_impl_spec.md` Task 4 item 5.

Zero RNG anywhere in this file, by design.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .smart_phrasing import PhraseSegment

log = logging.getLogger("drop_presentation")

# ---- Presentation vocabulary (authority doc §Meaning / §Observability) ------

LEDS_ONLY = "leds_only"
LEDS_PLUS_LASERS = "leds_plus_lasers"
LASERS_ONLY = "lasers_only"

_RUNWAY_LABELS = frozenset({"up", "low"})  # "up"=buildup, "low"=breakdown (smart_phrasing.py)
_WINDOW_ACTIVE_ROLES = frozenset({"drop", "post_drop"})

HOTCUE_TOLERANCE_BEATS = 2.0
LEARNED_TOLERANCE_BEATS = 2.0
AUDIBLE_DAMPER_BEATS = 16.0


# ---- Config -------------------------------------------------------------


def _float_or_default(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_default(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class DropPresentationConfig:
    """`/drop_presentation` config block (Task 5). Immutable after construction."""

    __slots__ = (
        "enabled", "laser_ratio", "opening_tracks", "led_predark_beats",
        "drop_window_cap_beats", "hotcue_marker", "solo_learn_threshold",
        "gearshift_bpm_jump", "record_min_drops", "ws_handoff_enabled",
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        laser_ratio: float = 0.4,
        opening_tracks: int = 3,
        led_predark_beats: int = 4,
        drop_window_cap_beats: int = 32,
        hotcue_marker: str = "LASER",
        solo_learn_threshold: int = 1,
        gearshift_bpm_jump: float = 10.0,
        record_min_drops: int = 5,
        ws_handoff_enabled: bool = False,
    ) -> None:
        self.enabled = bool(enabled)
        self.laser_ratio = laser_ratio
        self.opening_tracks = opening_tracks
        self.led_predark_beats = led_predark_beats
        self.drop_window_cap_beats = drop_window_cap_beats
        self.hotcue_marker = hotcue_marker
        self.solo_learn_threshold = solo_learn_threshold
        self.gearshift_bpm_jump = gearshift_bpm_jump
        self.record_min_drops = record_min_drops
        self.ws_handoff_enabled = bool(ws_handoff_enabled)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DropPresentationConfig":
        src = data if isinstance(data, Mapping) else {}
        return cls(
            enabled=bool(src.get("enabled", True)),
            laser_ratio=_float_or_default(src.get("laser_ratio"), 0.4),
            opening_tracks=_int_or_default(src.get("opening_tracks"), 3),
            led_predark_beats=_int_or_default(src.get("led_predark_beats"), 4),
            drop_window_cap_beats=_int_or_default(src.get("drop_window_cap_beats"), 32),
            hotcue_marker=str(src.get("hotcue_marker") or "LASER"),
            solo_learn_threshold=_int_or_default(src.get("solo_learn_threshold"), 1),
            gearshift_bpm_jump=_float_or_default(src.get("gearshift_bpm_jump"), 10.0),
            record_min_drops=_int_or_default(src.get("record_min_drops"), 5),
            ws_handoff_enabled=bool(src.get("ws_handoff_enabled", False)),
        )


def load_drop_presentation_config(path: str | Path) -> DropPresentationConfig:
    """Self-contained loader mirroring laser_color_engine.load_laser_color_map:
    any failure degrades to defaults, never raises. Reads the `drop_presentation`
    block from the same top-level LED config file (led_config.py owns the
    canonical path/env-override resolution and calls this with that path)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        data = {}
    block = data.get("drop_presentation") if isinstance(data, Mapping) else None
    return DropPresentationConfig.from_dict(block if isinstance(block, Mapping) else {})


# ---- Runway ------------------------------------------------------------


def runway_beats(beat: float, phrase_roles: Sequence[PhraseSegment]) -> float:
    """Contiguous breakdown/buildup beats immediately before `beat`.

    Walks backward through phrase segments whose label is "low" (breakdown) or
    "up" (buildup) and are contiguous with `beat` (each segment's end must equal
    the running boundary), stopping at the first segment that is anything else
    (e.g. "chorus"/"other" — a groove between breakdown and buildup resets the
    count) or the first gap. Missing/absent phrase data yields 0.0 and is
    invisible to the record-breaker tier. Pure; no I/O.
    """
    if not phrase_roles:
        return 0.0
    # Index by end_beat so the backward walk finds the segment landing exactly
    # at the current boundary regardless of where it sits among the track's
    # OTHER segments (a naive reverse-chronological scan breaks as soon as the
    # track's LAST segment doesn't happen to be the one ending at `beat`).
    by_end: dict[float, PhraseSegment] = {seg.end_beat: seg for seg in phrase_roles}
    total = 0.0
    boundary = beat
    while True:
        seg = by_end.get(boundary)
        if seg is None or seg.label not in _RUNWAY_LABELS:
            break
        total += seg.end_beat - seg.start_beat
        boundary = seg.start_beat
    return total


# ---- Nearest-within-tolerance (shared by hot-cue and learned-store lookup) --


def _nearest_within_tolerance(
    candidate: float, pool: Sequence[float], tolerance: float,
) -> Optional[float]:
    best: Optional[float] = None
    best_dist: Optional[float] = None
    for value in pool:
        dist = abs(value - candidate)
        if dist <= tolerance and (best_dist is None or dist < best_dist):
            best = value
            best_dist = dist
    return best


# ---- Track plan (pure track-structure classification, Task 1.1) ------------


class DropDecision:
    """Per-drop STATIC classification — a pure function of track structure plus
    curation data (tags/learned beats). This is NOT the final ladder verdict:
    tiers 1/2/5/6/7 are session/live state unknowable at track-load time, so
    `resolve_presentation()` combines this with live inputs per actual drop
    arrival (authority doc, Implementation Notes)."""

    __slots__ = ("beat", "tagged", "learned", "is_finale", "personality_presentation", "runway")

    def __init__(
        self, *, beat: float, tagged: bool, learned: bool, is_finale: bool,
        personality_presentation: str, runway: float,
    ) -> None:
        self.beat = beat
        self.tagged = tagged
        self.learned = learned
        self.is_finale = is_finale
        self.personality_presentation = personality_presentation
        self.runway = runway

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DropDecision):
            return NotImplemented
        return all(getattr(self, name) == getattr(other, name) for name in self.__slots__)

    def __repr__(self) -> str:
        return (
            f"DropDecision(beat={self.beat!r}, tagged={self.tagged!r}, learned={self.learned!r}, "
            f"is_finale={self.is_finale!r}, personality_presentation={self.personality_presentation!r}, "
            f"runway={self.runway!r})"
        )


class TrackPlan:
    """Static per-track plan: one `DropDecision` per true drop, plus any hot-cue
    markers that matched no smart drop (surfaced in status, never dropped)."""

    __slots__ = ("drop_beats", "decisions", "unmatched_tag_beats", "has_phrase_data")

    def __init__(
        self, *, drop_beats: tuple[float, ...], decisions: tuple[DropDecision, ...],
        unmatched_tag_beats: tuple[float, ...], has_phrase_data: bool,
    ) -> None:
        self.drop_beats = drop_beats
        self.decisions = decisions
        self.unmatched_tag_beats = unmatched_tag_beats
        self.has_phrase_data = has_phrase_data

    def decision_for(self, beat: float) -> Optional[DropDecision]:
        for candidate_beat, decision in zip(self.drop_beats, self.decisions):
            if candidate_beat == beat:
                return decision
        return None


def plan_track(
    drop_beats: Sequence[float],
    phrase_roles: Sequence[PhraseSegment],
    tagged_beats: Sequence[float],
    learned_keys: Sequence[float],
    config: DropPresentationConfig,
) -> TrackPlan:
    """Per true drop: the pure track-structure classification (authority doc's
    tiers 3/4/8/9 inputs). Deterministic — identical inputs always produce an
    identical plan (Required Behavior Test: planner determinism).

    - hot-cue match: nearest smart drop within +/-2 beats (HOTCUE_TOLERANCE_BEATS).
    - learned match: nearest smart drop within +/-2 beats (LEARNED_TOLERANCE_BEATS),
      surviving a shifted re-analysis beat.
    - finale: the last true drop.
    - personality: rank drops last-drop-first, then longest runway (ties keep
      beat-ascending order); the top ceil(laser_ratio * N) render leds_plus_lasers.
    """
    drops = tuple(float(b) for b in drop_beats)
    tags = tuple(float(b) for b in tagged_beats)
    learned = tuple(float(b) for b in learned_keys)
    has_phrase_data = bool(phrase_roles)

    if not drops:
        unmatched = tuple(sorted(set(tags)))
        return TrackPlan(
            drop_beats=(), decisions=(), unmatched_tag_beats=unmatched,
            has_phrase_data=has_phrase_data,
        )

    matched_tags: set[float] = set()
    unmatched_tags: list[float] = []
    for tag in tags:
        nearest = _nearest_within_tolerance(tag, drops, HOTCUE_TOLERANCE_BEATS)
        if nearest is None:
            unmatched_tags.append(tag)
        else:
            matched_tags.add(nearest)

    matched_learned: set[float] = set()
    for beat in learned:
        nearest = _nearest_within_tolerance(beat, drops, LEARNED_TOLERANCE_BEATS)
        if nearest is not None:
            matched_learned.add(nearest)

    runways = {beat: runway_beats(beat, phrase_roles) for beat in drops}
    last_drop = max(drops)
    n = len(drops)
    laser_count = max(0, min(n, math.ceil(config.laser_ratio * n)))

    # Stable sort on beat-ascending input: ties (equal runway, neither last-drop)
    # keep earliest-beat-first. last-drop-first outranks runway entirely.
    ranked = sorted(
        sorted(drops),
        key=lambda beat: (1 if beat == last_drop else 0, runways[beat]),
        reverse=True,
    )
    laser_set = set(ranked[:laser_count])

    decisions = []
    for beat in drops:
        decisions.append(DropDecision(
            beat=beat,
            tagged=beat in matched_tags,
            learned=beat in matched_learned,
            is_finale=(beat == last_drop),
            personality_presentation=(LEDS_PLUS_LASERS if beat in laser_set else LEDS_ONLY),
            runway=runways[beat],
        ))

    return TrackPlan(
        drop_beats=drops,
        decisions=tuple(decisions),
        unmatched_tag_beats=tuple(sorted(set(unmatched_tags))),
        has_phrase_data=has_phrase_data,
    )


# ---- Ladder resolution (live, per actual drop arrival) ---------------------


def resolve_presentation(
    decision: DropDecision,
    *,
    armed: bool,
    gearshift_pending: bool,
    record_breaking: bool,
    auto_solo_used: bool,
    damper_active: bool,
) -> tuple[str, str, bool]:
    """First-match-wins ladder for one true drop (authority doc §The Ladder).

    Returns (presentation, reason, auto_solo_fired). `auto_solo_fired` is True
    exactly when this call consumed one of the once-per-track auto-solo tiers
    (learned/gear-shift/record) — the caller latches
    `SessionState.mark_auto_solo_used()` only then. Manual arm and hot-cue tags
    are exempt from that cap and from the opening damper. The finale guarantee
    (tier 8) is never blocked by the opening damper (tier 7): Required Behavior
    Test 1 demands the last true drop always render at least `leds_plus_lasers`,
    unconditionally.
    """
    if armed:
        return (LASERS_ONLY, "solo_manual", False)
    if decision.tagged:
        return (LASERS_ONLY, "solo_hotcue", False)
    if decision.learned and not auto_solo_used:
        return (LASERS_ONLY, "solo_learned", True)
    if not damper_active:
        if gearshift_pending and not auto_solo_used:
            return (LASERS_ONLY, "solo_gearshift", True)
        if record_breaking and not auto_solo_used:
            return (LASERS_ONLY, "solo_record", True)
    if decision.is_finale:
        return (LEDS_PLUS_LASERS, "both_finale", False)
    if damper_active:
        return (LEDS_ONLY, "leds_only_damper", False)
    if decision.personality_presentation == LEDS_PLUS_LASERS:
        return (LEDS_PLUS_LASERS, "both_personality", False)
    return (LEDS_ONLY, "leds_only_personality", False)


def gearshift_qualifies(
    outgoing_bpm: Optional[float], incoming_bpm: Optional[float], threshold: float,
) -> bool:
    """Tier 5: incoming exceeds outgoing by >= threshold, upward only. Missing/
    non-positive outgoing (the session's first master) never fires. Pure;
    live-vs-meta BPM resolution is the caller's job (state_manager.py)."""
    if outgoing_bpm is None or incoming_bpm is None:
        return False
    if outgoing_bpm <= 0 or incoming_bpm <= 0:
        return False
    return (incoming_bpm - outgoing_bpm) >= threshold


# ---- Session state (Task 1.2) ----------------------------------------------


class SessionState:
    """In-memory per-session counters and latches. A session is one bridge
    process lifetime — construct a fresh instance per process; never persisted
    (the learned store is the only state that survives across sessions)."""

    def __init__(self) -> None:
        self.opening_tracks_counted: int = 0
        self.runway_record: float = 0.0
        self.observed_drop_count: int = 0
        self._counted_tracks: set[tuple[int, int]] = set()
        self._auto_solo_used_tracks: set[tuple[int, int]] = set()
        self._gearshift_pending_track: Optional[tuple[int, int]] = None

    def damper_active(self, opening_tracks: int) -> bool:
        return self.opening_tracks_counted < max(0, opening_tracks)

    def mark_track_counted(self, deck: int, load_gen: int) -> bool:
        """Idempotent per (deck, load_gen); True the first time this load counts.
        Loaded-but-never-audible decks must never call this."""
        key = (deck, load_gen)
        if key in self._counted_tracks:
            return False
        self._counted_tracks.add(key)
        self.opening_tracks_counted += 1
        return True

    def auto_solo_used(self, track_key: tuple[int, int]) -> bool:
        return track_key in self._auto_solo_used_tracks

    def mark_auto_solo_used(self, track_key: tuple[int, int]) -> None:
        self._auto_solo_used_tracks.add(track_key)

    def is_record_breaking(self, runway: float, record_min_drops: int) -> bool:
        """Pure read (no mutation) — usable ahead of impact (the runway of a
        known upcoming drop is fully determined by track structure, so the
        crossing is detectable as soon as the drop is identified, not only at
        impact) and re-checked at impact."""
        return self.observed_drop_count >= record_min_drops and runway > self.runway_record

    def finalize_drop_observation(self, runway: float, *, has_phrase_data: bool) -> None:
        """Call once per true-drop IMPACT, regardless of ladder outcome — records
        are tracked even when a solo is suppressed by the damper. Tracks without
        phrase data are invisible to this tier: no count, no record update."""
        if not has_phrase_data:
            return
        if runway > self.runway_record:
            self.runway_record = runway
        self.observed_drop_count += 1

    def set_gearshift_pending(self, track_key: tuple[int, int]) -> None:
        self._gearshift_pending_track = track_key

    def consume_gearshift_pending(self, track_key: tuple[int, int]) -> bool:
        """One-shot: True (and clears the flag) only for the incoming track's
        FIRST true drop after a qualifying handover."""
        if self._gearshift_pending_track == track_key:
            self._gearshift_pending_track = None
            return True
        return False

    def clear_gearshift_pending(self) -> None:
        self._gearshift_pending_track = None


# ---- Learned store (Task 1.3) ----------------------------------------------


class LearnedStore:
    """Persistent per-track memory of manually-soloed drops. Keys are
    `f"{content_id}:{round(beat)}"` (beat-position, not list index — survives
    Rekordbox re-analysis reindexing). `load()`/`to_dict()` are the only I/O
    surface; the caller (state_manager.py) is responsible for routing the
    ACTUAL file write through a background thread — see module docstring."""

    def __init__(self, entries: Mapping[str, list[float]] | None = None) -> None:
        self._entries: dict[str, list[float]] = (
            {key: list(beats) for key, beats in entries.items()} if entries else {}
        )

    @classmethod
    def load(cls, path: str | Path) -> "LearnedStore":
        """Missing/corrupt file -> empty store + exactly one logged warning."""
        target = Path(path)
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(
                "[DROP-PRESENTATION] learned-store-load-failed path=%s err=%s",
                target, type(exc).__name__,
            )
            return cls()
        if not isinstance(raw, dict):
            log.warning("[DROP-PRESENTATION] learned-store-malformed path=%s", target)
            return cls()
        entries: dict[str, list[float]] = {}
        for key in raw:
            if not isinstance(key, str) or ":" not in key:
                continue
            content_id, _, beat_str = key.rpartition(":")
            if not content_id:
                continue
            try:
                beat = float(beat_str)
            except ValueError:
                continue
            entries.setdefault(content_id, []).append(beat)
        return cls(entries)

    def beats_for_track(self, content_id: str) -> tuple[float, ...]:
        return tuple(self._entries.get(content_id, ()))

    def record(self, content_id: str, beat: float) -> bool:
        """Record a solo FIRE (never an arm). No-op (returns False) if this
        (content_id, beat) already matches an existing entry within tolerance —
        firing on an already-tagged/learned drop records nothing new."""
        beats = self._entries.setdefault(content_id, [])
        if _nearest_within_tolerance(beat, beats, LEARNED_TOLERANCE_BEATS) is not None:
            return False
        beats.append(float(round(beat)))
        return True

    def remove(self, content_id: str, beat: float) -> bool:
        """Veto-unlearn: remove the nearest stored entry within tolerance."""
        beats = self._entries.get(content_id)
        if not beats:
            return False
        nearest = _nearest_within_tolerance(beat, beats, LEARNED_TOLERANCE_BEATS)
        if nearest is None:
            return False
        beats.remove(nearest)
        if not beats:
            self._entries.pop(content_id, None)
        return True

    def to_dict(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for content_id, beats in self._entries.items():
            for beat in beats:
                result[f"{content_id}:{round(beat)}"] = True
        return result


# ---- Window machine (Task 1.4) ---------------------------------------------


class WindowInputs:
    """One push tick's worth of already-computed, pure signals (Task 4 item 3)."""

    __slots__ = (
        "abs_beat", "beats_to_next_drop", "next_drop_beat", "drop_role",
        "impact_now", "laser_visible", "scripted_mode", "stopped",
        "track_changed", "active_deck_changed", "manual_interaction",
    )

    def __init__(
        self, *, abs_beat: Optional[float], beats_to_next_drop: Optional[float],
        next_drop_beat: Optional[float], drop_role: str, impact_now: bool,
        laser_visible: bool, scripted_mode: bool = False, stopped: bool = False,
        track_changed: bool = False, active_deck_changed: bool = False,
        manual_interaction: bool = False,
    ) -> None:
        self.abs_beat = abs_beat
        self.beats_to_next_drop = beats_to_next_drop
        self.next_drop_beat = next_drop_beat
        self.drop_role = drop_role
        self.impact_now = impact_now
        self.laser_visible = laser_visible
        self.scripted_mode = scripted_mode
        self.stopped = stopped
        self.track_changed = track_changed
        self.active_deck_changed = active_deck_changed
        self.manual_interaction = manual_interaction


class WindowActions:
    """What state_manager.py applies this tick. Idempotent — safe to apply every
    tick even when unchanged from the previous one."""

    __slots__ = ("led_dark_hold", "base_suppressed", "presentation", "reason")

    def __init__(
        self, *, led_dark_hold: bool, base_suppressed: bool,
        presentation: Optional[str], reason: str,
    ) -> None:
        self.led_dark_hold = led_dark_hold
        self.base_suppressed = base_suppressed
        self.presentation = presentation
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WindowActions):
            return NotImplemented
        return (
            self.led_dark_hold == other.led_dark_hold
            and self.base_suppressed == other.base_suppressed
            and self.presentation == other.presentation
            and self.reason == other.reason
        )

    def __repr__(self) -> str:
        return (
            f"WindowActions(led_dark_hold={self.led_dark_hold!r}, "
            f"base_suppressed={self.base_suppressed!r}, presentation={self.presentation!r}, "
            f"reason={self.reason!r})"
        )


_IDLE_ACTIONS = WindowActions(led_dark_hold=False, base_suppressed=False, presentation=None, reason="")


class WindowMachine:
    """Pre-dark / solo-window / suppression state machine (authority doc
    §Presentation Mechanics). Pure transitions driven by `WindowInputs` — no I/O,
    no `time.time()`/`time.monotonic()` (beat-driven, not time-driven). The
    policy can never latch a fixture dark: every phase has an enumerated
    fail-open reset back to idle."""

    def __init__(self, config: DropPresentationConfig) -> None:
        self._config = config
        self._phase = "idle"           # "idle" | "pre_dark" | "in_window"
        self._presentation: Optional[str] = None
        self._reason: str = ""
        self._target_impact_beat: Optional[float] = None
        self._window_end_beat: Optional[float] = None

    def _reset(self) -> None:
        self._phase = "idle"
        self._presentation = None
        self._reason = ""
        self._target_impact_beat = None
        self._window_end_beat = None

    def _enter_window(self, presentation: str, reason: str, abs_beat: Optional[float]) -> None:
        self._phase = "in_window"
        self._presentation = presentation
        self._reason = reason
        self._window_end_beat = (
            abs_beat + float(self._config.drop_window_cap_beats) if abs_beat is not None else None
        )

    def _window_actions(self) -> WindowActions:
        return WindowActions(
            led_dark_hold=(self._presentation == LASERS_ONLY),
            base_suppressed=(self._presentation == LEDS_ONLY),
            presentation=self._presentation,
            reason=self._reason,
        )

    def tick(
        self, inputs: WindowInputs, *,
        pending_presentation: Optional[str], pending_reason: str,
    ) -> WindowActions:
        # Universal fail-open triggers: restore immediately regardless of phase.
        if (
            inputs.scripted_mode or inputs.stopped or inputs.track_changed
            or inputs.active_deck_changed or inputs.manual_interaction
        ):
            self._reset()
            return _IDLE_ACTIONS

        if self._phase == "pre_dark":
            # Impact takes precedence over the countdown's own fail-open checks:
            # the guard below already handles "not visible right at impact" by
            # downgrading to leds_plus_lasers, which is a WINDOW (the drop still
            # happened), not an idle reset (which would mean no drop happened).
            if inputs.impact_now:
                presentation, reason = self._guarded(pending_presentation, pending_reason, inputs)
                self._enter_window(presentation, reason, inputs.abs_beat)
                return self._window_actions()
            passed_without_drop = (
                inputs.abs_beat is not None
                and self._target_impact_beat is not None
                and inputs.abs_beat > self._target_impact_beat + 1e-6
            )
            if passed_without_drop or not inputs.laser_visible:
                self._reset()
                return _IDLE_ACTIONS
            return WindowActions(
                led_dark_hold=True, base_suppressed=False, presentation=None, reason="pre_dark",
            )

        if self._phase == "in_window":
            window_ended = (
                inputs.drop_role not in _WINDOW_ACTIVE_ROLES
                or (
                    self._window_end_beat is not None
                    and inputs.abs_beat is not None
                    and inputs.abs_beat >= self._window_end_beat
                )
            )
            lost_visibility = self._presentation == LASERS_ONLY and not inputs.laser_visible
            if window_ended or lost_visibility:
                self._reset()
                return _IDLE_ACTIONS
            return self._window_actions()

        # phase == "idle"
        if inputs.impact_now and pending_presentation is not None:
            presentation, reason = self._guarded(pending_presentation, pending_reason, inputs)
            self._enter_window(presentation, reason, inputs.abs_beat)
            return self._window_actions()

        if (
            pending_presentation == LASERS_ONLY
            and inputs.next_drop_beat is not None
            and inputs.beats_to_next_drop is not None
            and inputs.beats_to_next_drop <= float(self._config.led_predark_beats)
            and inputs.laser_visible
        ):
            self._phase = "pre_dark"
            self._target_impact_beat = inputs.next_drop_beat
            return WindowActions(
                led_dark_hold=True, base_suppressed=False, presentation=None, reason="pre_dark",
            )

        return _IDLE_ACTIONS

    @staticmethod
    def _guarded(
        pending_presentation: str, pending_reason: str, inputs: WindowInputs,
    ) -> tuple[str, str]:
        """Darkness guard re-checked at impact (authority doc): a `lasers_only`
        verdict downgrades to `leds_plus_lasers` when lasers are not actually
        visible right now."""
        if pending_presentation == LASERS_ONLY and not inputs.laser_visible:
            return LEDS_PLUS_LASERS, "guard_fallback_both"
        return pending_presentation, pending_reason
