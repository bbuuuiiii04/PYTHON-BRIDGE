from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from .config import (
    SMART_DROP_IGNORE_INTRO_BEATS,
    SMART_DROP_IGNORE_OUTRO_BEATS,
    SMART_BREAKDOWN_IGNORE_INTRO_BEATS,
    SMART_BREAKDOWN_IGNORE_OUTRO_BEATS,
)

_EXACT_DROP_EPSILON = 1e-6
# ANLZ marks each 32-beat phrase in a drop section; keep the section entry only.
SMART_DROP_MIN_GAP_BEATS = 64


PhraseLabel = Literal["up", "chorus", "low", "other"]

@dataclass(frozen=True)
class PhraseSegment:
    start_beat: float
    end_beat: float
    label: PhraseLabel

@dataclass(frozen=True)
class BeatSegment:
    start_beat: float
    end_beat: float

@dataclass(frozen=True)
class SmartPhrasingSnapshot:
    deck_id: Optional[str]
    track_id: Optional[str]
    is_playing: bool
    abs_beat: Optional[float]
    phrase_segments: tuple[PhraseSegment, ...]
    smart_drop_beats: tuple[float, ...]
    breakdown_segments: tuple[BeatSegment, ...]
    phrase_lookahead_beats: float
    drop_window_beats: float
    post_drop_beats: float
    transition_window_beats: float
    phrase_anchor_last_beat: int = -1
    phrase_anchor_period_beats: int = 64
    # AWR-170 (D.2): laser blackout beats before every chorus phrase start. 0 ⇒
    # feature off (no arm flags ever); the caller gates F2-off/scripted/no-plan to 0.
    pre_chorus_beats: float = 0.0
    # AWR-179 D2-F1 (OLC-B): beats-before-drop at which the pre-drop dark window
    # releases EARLY (the F2 floor-return abort). 0.0 ⇒ no early release, byte-
    # identical to before; the caller gates F2-off/scripted/no-plan/no-abort to 0.0.
    transition_release_beats: float = 0.0

@dataclass(frozen=True)
class SmartPhrasingState:
    abs_beat: Optional[float] = None
    current_phrase_label: PhraseLabel = "other"
    current_phrase_start_beat: Optional[float] = None
    phrase_start_crossing: bool = False
    previous_phrase_label: PhraseLabel = "other"
    current_phrase_is_up: bool = False
    current_phrase_is_chorus: bool = False
    current_phrase_is_low: bool = False
    beats_into_phrase: Optional[float] = None
    next_smart_drop_beat: Optional[float] = None
    beats_to_next_drop: Optional[float] = None
    smart_drop_window_active: bool = False
    smart_drop_crossing: bool = False
    smart_drop_preclear_requested: bool = False
    smart_drop_rearm_requested: bool = False
    smart_post_drop_active: bool = False
    active_drop_beat: Optional[float] = None
    smart_buildup_active: bool = False
    smart_breakdown_active: bool = False
    breakdown_start_crossing: bool = False
    breakdown_end_crossing: bool = False
    smart_breakdown_clear_requested: bool = False
    smart_breakdown_restore_requested: bool = False
    transition_mask_should_arm: bool = False
    transition_mask_should_clear: bool = False
    transition_window_active: bool = False
    transition_mask_arm_latched: bool = False
    # AWR-170 (D.2) pre-chorus laser blackout window (mask owner "pre_chorus").
    pre_chorus_window_active: bool = False
    pre_chorus_mask_should_arm: bool = False
    pre_chorus_mask_should_clear: bool = False
    phrase_anchor_requested: bool = False
    phrase_anchor_preclear_requested: bool = False
    phrase_anchor_rearm_requested: bool = False
    phrase_anchor_target_beat: Optional[int] = None
    reason: str = ""
    breakdown_restore_beat: Optional[float] = None

@dataclass(frozen=True)
class SmartPhrasingDiagnostic:
    event: str
    level: str
    reason: str
    deck_id: Optional[str]
    track_id: Optional[str]
    abs_beat: Optional[float]
    previous_abs_beat: Optional[float]
    phrase_label: Optional[str] = None
    drop_beat: Optional[float] = None
    beats_to_drop: Optional[float] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    extra: Optional[dict] = None

@dataclass(frozen=True)
class SmartPhrasingResult:
    state: SmartPhrasingState
    diagnostics: tuple[SmartPhrasingDiagnostic, ...]


@dataclass
class _EngineScratch:
    active_drop_beat: Optional[float]
    smart_drop_window_active: bool
    transition_window_active: bool
    transition_window_arm_suppressed: bool
    blackout_arm_latched: bool
    pre_chorus_window_active: bool

    @classmethod
    def from_engine(cls, engine: "SmartPhrasingEngine") -> "_EngineScratch":
        return cls(
            active_drop_beat=engine._active_drop_beat,
            smart_drop_window_active=engine._smart_drop_window_active,
            transition_window_active=engine._transition_window_active,
            transition_window_arm_suppressed=engine._transition_window_arm_suppressed,
            blackout_arm_latched=engine._blackout_arm_latched,
            pre_chorus_window_active=engine._pre_chorus_window_active,
        )

    def apply_to_engine(self, engine: "SmartPhrasingEngine") -> None:
        engine._active_drop_beat = self.active_drop_beat
        engine._smart_drop_window_active = self.smart_drop_window_active
        engine._transition_window_active = self.transition_window_active
        engine._transition_window_arm_suppressed = self.transition_window_arm_suppressed
        engine._blackout_arm_latched = self.blackout_arm_latched
        engine._pre_chorus_window_active = self.pre_chorus_window_active


class SmartPhrasingEngine:
    def __init__(self) -> None:
        self._previous_abs_beat: Optional[float] = None
        self._fired_drop_beats: set[float] = set()
        self._active_drop_beat: Optional[float] = None
        self._last_deck_id: Optional[str] = None
        self._last_track_id: Optional[str] = None
        self._transition_window_active: bool = False
        self._transition_window_arm_suppressed: bool = False
        self._smart_drop_window_active: bool = False
        self._blackout_arm_latched: bool = False
        self._pre_chorus_window_active: bool = False

    def reset(self, reason: str) -> SmartPhrasingState:
        self._previous_abs_beat = None
        self._fired_drop_beats.clear()
        self._active_drop_beat = None
        self._last_deck_id = None
        self._last_track_id = None
        self._transition_window_active = False
        self._transition_window_arm_suppressed = False
        self._smart_drop_window_active = False
        self._blackout_arm_latched = False
        self._pre_chorus_window_active = False

        return self._default_state(reason)

    def clear_blackout_latch(self) -> None:
        self._blackout_arm_latched = False

    def clear_smart_rearm_state(self) -> None:
        """Clear smart-rearm internals without dropping beat continuity.

        Preserves _previous_abs_beat, _fired_drop_beats, _last_deck_id, and
        _last_track_id so next-tick crossing detection, fired-drop
        suppression, and track/deck continuity still work after
        StateManager-side smart-rearm clears.
        """
        self._active_drop_beat = None
        self._smart_drop_window_active = False
        self._blackout_arm_latched = False
        self._transition_window_active = False
        self._transition_window_arm_suppressed = False
        self._pre_chorus_window_active = False

    def _default_state(self, reason: str) -> SmartPhrasingState:
        return SmartPhrasingState(reason=reason)

    def update(self, snapshot: SmartPhrasingSnapshot) -> SmartPhrasingResult:
        diagnostics: list[SmartPhrasingDiagnostic] = []
        
        needs_reset = False
        reset_reason = ""
        
        if not snapshot.is_playing:
            reset_reason = "not_playing"
        elif snapshot.deck_id is None:
            reset_reason = "no_deck"
        elif snapshot.track_id is None:
            reset_reason = "no_track"
        elif snapshot.abs_beat is None:
            reset_reason = "no_beat"
        else:
            reset_reason = ""
            
        if reset_reason:
            diagnostics.append(SmartPhrasingDiagnostic(
                event="smart_phrasing_reset",
                level="info",
                reason=reset_reason,
                deck_id=snapshot.deck_id,
                track_id=snapshot.track_id,
                abs_beat=snapshot.abs_beat,
                previous_abs_beat=self._previous_abs_beat
            ))
            state = self.reset(reset_reason)
            return SmartPhrasingResult(state=state, diagnostics=tuple(diagnostics))
            
        abs_beat = snapshot.abs_beat
        
        needs_reset = False
        if snapshot.deck_id != self._last_deck_id:
            needs_reset = True
            reset_reason = "deck_change"
        elif snapshot.track_id != self._last_track_id:
            needs_reset = True
            reset_reason = "track_change"
        elif self._previous_abs_beat is not None and abs_beat < self._previous_abs_beat - 0.1:
            needs_reset = True
            reset_reason = "playhead_jump_backward"
            
        if needs_reset:
            diagnostics.append(SmartPhrasingDiagnostic(
                event="smart_phrasing_reset",
                level="info",
                reason=reset_reason,
                deck_id=snapshot.deck_id,
                track_id=snapshot.track_id,
                abs_beat=snapshot.abs_beat,
                previous_abs_beat=self._previous_abs_beat
            ))
            self.reset(reset_reason)
            
        self._last_deck_id = snapshot.deck_id
        self._last_track_id = snapshot.track_id

        prev_abs_beat = self._previous_abs_beat
        scratch = _EngineScratch.from_engine(self)
        state = self._compute_tick_state(
            snapshot,
            snapshot.abs_beat,
            prev_abs_beat,
            scratch=scratch,
            mutate=True,
        )
        scratch.apply_to_engine(self)
        self._previous_abs_beat = snapshot.abs_beat

        return SmartPhrasingResult(state=state, diagnostics=tuple(diagnostics))

    def preview_with_beat_offset(
        self,
        snapshot: SmartPhrasingSnapshot,
        offset_beats: float,
    ) -> SmartPhrasingState:
        """Read-only SmartPhrasing state at abs_beat + offset_beats for LED lead time."""
        if snapshot.abs_beat is None or offset_beats <= 0.0:
            return SmartPhrasingState(reason="preview_unavailable")
        abs_beat = snapshot.abs_beat + offset_beats
        prev_abs_beat = self._previous_abs_beat
        scratch = _EngineScratch.from_engine(self)
        return self._compute_tick_state(
            snapshot,
            abs_beat,
            prev_abs_beat,
            scratch=scratch,
            mutate=False,
        )

    def _compute_tick_state(
        self,
        snapshot: SmartPhrasingSnapshot,
        abs_beat: float,
        prev_abs_beat: Optional[float],
        *,
        scratch: _EngineScratch,
        mutate: bool,
    ) -> SmartPhrasingState:
        # 1. Resolve current phrase and crossings
        current_phrase_label: PhraseLabel = "other"
        current_phrase_start_beat: Optional[float] = None
        current_phrase_index: Optional[int] = None
        phrase_anchor_requested = False

        for index, seg in enumerate(snapshot.phrase_segments):
            if prev_abs_beat is not None and prev_abs_beat < seg.start_beat <= abs_beat:
                phrase_anchor_requested = True

            if seg.start_beat <= abs_beat < seg.end_beat:
                current_phrase_label = seg.label
                current_phrase_start_beat = seg.start_beat
                current_phrase_index = index
                break

        previous_phrase_label: PhraseLabel = "other"
        if current_phrase_index is not None and current_phrase_index > 0:
            previous_phrase_label = snapshot.phrase_segments[current_phrase_index - 1].label
        phrase_start_crossing = bool(
            prev_abs_beat is not None
            and current_phrase_start_beat is not None
            and prev_abs_beat < current_phrase_start_beat <= abs_beat
        )

        current_phrase_is_up = current_phrase_label == "up"
        current_phrase_is_chorus = current_phrase_label == "chorus"
        current_phrase_is_low = current_phrase_label == "low"
        beats_into_phrase = (
            abs_beat - current_phrase_start_beat
            if current_phrase_start_beat is not None else None
        )

        # 2. Drop crossing
        smart_drop_crossing = False
        for drop_beat in sorted(snapshot.smart_drop_beats):
            crossed_from_history = (
                prev_abs_beat is not None
                and prev_abs_beat < drop_beat <= abs_beat
            )
            exact_resume_landing = (
                mutate
                and prev_abs_beat is None
                and abs(drop_beat - abs_beat) <= _EXACT_DROP_EPSILON
            )
            if (
                (crossed_from_history or exact_resume_landing)
                and drop_beat not in self._fired_drop_beats
            ):
                smart_drop_crossing = True
                if mutate:
                    self._fired_drop_beats.add(drop_beat)
                scratch.active_drop_beat = drop_beat
                break

        # 3. Resolve next Smart Drop
        next_smart_drop_beat = None
        beats_to_next_drop = None
        for drop_beat in sorted(snapshot.smart_drop_beats):
            if drop_beat >= abs_beat and drop_beat not in self._fired_drop_beats:
                next_smart_drop_beat = drop_beat
                beats_to_next_drop = drop_beat - abs_beat
                break

        # 4. Drop window and Preclear Intent
        smart_drop_window_active = False
        if next_smart_drop_beat is not None and beats_to_next_drop is not None:
            smart_drop_window_active = beats_to_next_drop <= snapshot.drop_window_beats

        smart_drop_preclear_requested = False
        if smart_drop_window_active and not scratch.smart_drop_window_active:
            smart_drop_preclear_requested = True

        scratch.smart_drop_window_active = smart_drop_window_active

        # 4b. Rearm Intent
        smart_drop_rearm_requested = smart_drop_crossing

        # 5. Post-drop
        smart_post_drop_active = False
        if scratch.active_drop_beat is not None:
            if (
                abs_beat >= scratch.active_drop_beat
                and abs_beat < scratch.active_drop_beat + snapshot.post_drop_beats
            ):
                smart_post_drop_active = True
            elif mutate:
                scratch.active_drop_beat = None

        # 6. Buildup
        smart_buildup_active = False
        if (
            current_phrase_is_up
            and next_smart_drop_beat is not None
            and beats_to_next_drop is not None
        ):
            if beats_to_next_drop <= snapshot.phrase_lookahead_beats:
                smart_buildup_active = True

        # 7. Breakdown
        smart_breakdown_active = False
        breakdown_start_crossing = False
        breakdown_end_crossing = False
        breakdown_restore_beat: Optional[float] = None

        for seg in snapshot.breakdown_segments:
            if seg.start_beat <= abs_beat < seg.end_beat:
                smart_breakdown_active = True
                if breakdown_restore_beat is None:
                    breakdown_restore_beat = seg.end_beat

            if prev_abs_beat is not None:
                if prev_abs_beat < seg.start_beat <= abs_beat:
                    breakdown_start_crossing = True
                    if breakdown_restore_beat is None:
                        breakdown_restore_beat = seg.end_beat
                if prev_abs_beat < seg.end_beat <= abs_beat:
                    breakdown_end_crossing = True

        smart_breakdown_clear_requested = breakdown_start_crossing
        smart_breakdown_restore_requested = breakdown_end_crossing

        # 8. Transition mask intent
        new_transition_window_active = False
        if next_smart_drop_beat is not None and beats_to_next_drop is not None:
            if beats_to_next_drop <= snapshot.transition_window_beats:
                new_transition_window_active = True

        transition_mask_should_arm = False
        transition_mask_should_clear = False

        breakdown_between = (
            next_smart_drop_beat is not None
            and any(
                abs_beat <= seg.start_beat < next_smart_drop_beat
                for seg in snapshot.breakdown_segments
            )
        )

        if new_transition_window_active:
            rising_edge = not scratch.transition_window_active
            suppressed = smart_breakdown_active or breakdown_between
            if (rising_edge or scratch.transition_window_arm_suppressed) and not suppressed:
                transition_mask_should_arm = True
                scratch.transition_window_arm_suppressed = False
            elif rising_edge and suppressed:
                scratch.transition_window_arm_suppressed = True
        elif scratch.transition_window_active:
            transition_mask_should_clear = True
            scratch.transition_window_arm_suppressed = False

        if transition_mask_should_arm:
            scratch.blackout_arm_latched = True
        if smart_drop_crossing or transition_mask_should_clear:
            scratch.blackout_arm_latched = False

        scratch.transition_window_active = new_transition_window_active

        # 8b. Pre-chorus laser blackout intent (AWR-170 D.2). Chorus phrase starts
        # are the RAW anlz-drop markers (uncollapsed — the AWR-131 collapse only
        # merged drop DECISIONS), so a chorus mid-drop-section that F2's per-drop
        # window never darkens still gets its own pre-chorus laser breath. Window =
        # the pre_chorus_beats before the next chorus marker at/after the playhead;
        # releases exactly at the marker. pre_chorus_beats==0 ⇒ no window ever
        # (byte-identical to pre-AWR-170; the caller gates F2-off/scripted to 0).
        pre_chorus_window_active = False
        if snapshot.pre_chorus_beats > 0:
            next_chorus_marker: Optional[float] = None
            for seg in snapshot.phrase_segments:
                if seg.label == "chorus" and seg.start_beat > abs_beat:
                    if next_chorus_marker is None or seg.start_beat < next_chorus_marker:
                        next_chorus_marker = seg.start_beat
            if next_chorus_marker is not None:
                beats_to_next_chorus_marker = next_chorus_marker - abs_beat
                pre_chorus_window_active = (
                    0 < beats_to_next_chorus_marker <= snapshot.pre_chorus_beats
                )

        pre_chorus_mask_should_arm = (
            pre_chorus_window_active and not scratch.pre_chorus_window_active
        )
        pre_chorus_mask_should_clear = (
            scratch.pre_chorus_window_active and not pre_chorus_window_active
        )
        scratch.pre_chorus_window_active = pre_chorus_window_active

        # 9. Periodic phrase-anchor intents (pure function of snapshot state).
        phrase_anchor_preclear_requested = False
        phrase_anchor_rearm_requested = False
        phrase_anchor_target_beat: Optional[int] = None
        this_beat_int = int(abs_beat)
        if snapshot.phrase_anchor_last_beat >= 0 and snapshot.phrase_anchor_period_beats > 0:
            target_beat = int(snapshot.phrase_anchor_last_beat) + int(
                snapshot.phrase_anchor_period_beats
            )
            phrase_anchor_target_beat = target_beat
            if this_beat_int <= target_beat + 8:
                phrase_anchor_preclear_requested = this_beat_int == (target_beat - 1)
                phrase_anchor_rearm_requested = this_beat_int >= target_beat

        return SmartPhrasingState(
            abs_beat=abs_beat,
            current_phrase_label=current_phrase_label,
            current_phrase_start_beat=current_phrase_start_beat,
            phrase_start_crossing=phrase_start_crossing,
            previous_phrase_label=previous_phrase_label,
            current_phrase_is_up=current_phrase_is_up,
            current_phrase_is_chorus=current_phrase_is_chorus,
            current_phrase_is_low=current_phrase_is_low,
            beats_into_phrase=beats_into_phrase,
            next_smart_drop_beat=next_smart_drop_beat,
            beats_to_next_drop=beats_to_next_drop,
            smart_drop_window_active=smart_drop_window_active,
            smart_drop_crossing=smart_drop_crossing,
            smart_drop_preclear_requested=smart_drop_preclear_requested,
            smart_drop_rearm_requested=smart_drop_rearm_requested,
            smart_post_drop_active=smart_post_drop_active,
            active_drop_beat=scratch.active_drop_beat,
            smart_buildup_active=smart_buildup_active,
            smart_breakdown_active=smart_breakdown_active,
            breakdown_start_crossing=breakdown_start_crossing,
            breakdown_end_crossing=breakdown_end_crossing,
            breakdown_restore_beat=breakdown_restore_beat,
            smart_breakdown_clear_requested=smart_breakdown_clear_requested,
            smart_breakdown_restore_requested=smart_breakdown_restore_requested,
            transition_mask_should_arm=transition_mask_should_arm,
            transition_mask_should_clear=transition_mask_should_clear,
            transition_window_active=new_transition_window_active,
            transition_mask_arm_latched=scratch.blackout_arm_latched,
            pre_chorus_window_active=pre_chorus_window_active,
            pre_chorus_mask_should_arm=pre_chorus_mask_should_arm,
            pre_chorus_mask_should_clear=pre_chorus_mask_should_clear,
            phrase_anchor_requested=phrase_anchor_requested,
            phrase_anchor_preclear_requested=phrase_anchor_preclear_requested,
            phrase_anchor_rearm_requested=phrase_anchor_rearm_requested,
            phrase_anchor_target_beat=phrase_anchor_target_beat,
            reason="preview" if not mutate else "tick",
        )


def _latest_marker_beat_at_or_before(abs_beat: float, beats: list[int]) -> Optional[int]:
    latest: Optional[int] = None
    for marker in beats:
        if marker <= abs_beat and (latest is None or marker > latest):
            latest = marker
    return latest



def _current_phrase_context(
    *,
    abs_beat: float,
    up_markers: list[int],
    chorus_markers: list[int],
    low_markers: list[int],
) -> tuple[bool, bool]:
    up = _latest_marker_beat_at_or_before(abs_beat, up_markers)
    chorus = _latest_marker_beat_at_or_before(abs_beat, chorus_markers)
    low = _latest_marker_beat_at_or_before(abs_beat, low_markers)

    candidates: list[tuple[int, int, str]] = []
    if up is not None:
        candidates.append((up, 1, "up"))
    if chorus is not None:
        candidates.append((chorus, 2, "chorus"))
    if low is not None:
        candidates.append((low, 3, "low"))
    if not candidates:
        return False, False

    _beat, _priority, marker_type = max(candidates, key=lambda item: (item[0], item[1]))
    if marker_type == "up":
        return True, False
    if marker_type == "chorus":
        return False, True
    return False, False



def build_phrase_segments_from_markers(
    anlz_buildups: list[int],
    anlz_drops: list[int],
    anlz_breakdowns: list[int],
    smart_drops: list[int],
    total_beats: int,
) -> tuple[PhraseSegment, ...]:
    """Infer PhraseSegment ranges from ordered ANLZ markers.

    Maps: anlz_buildups → "up", anlz_drops → "chorus", anlz_breakdowns → "low".
    Each marker's end_beat = next marker's start_beat.
    Final marker uses *total_beats* (from beatgrid length) if available,
    otherwise it is skipped — this helper does not invent arbitrary durations.

    When no explicit anlz_buildups exist but smart_drops are present, infers
    conservative 32-beat "up" segments before each Smart Drop.  This is a
    conservative fallback based on the project rule that true musical
    buildups typically happen during the 32 beats before a Smart Drop.

    Pure computation — no I/O, no config reads, no file parsing.
    """
    markers: list[tuple[int, str]] = []
    for beat in anlz_buildups:
        markers.append((beat, "up"))
    for beat in anlz_drops:
        markers.append((beat, "chorus"))
    for beat in anlz_breakdowns:
        markers.append((beat, "low"))

    # Fallback: infer 32-beat "up" segments before Smart Drops
    # when no explicit buildup markers exist from ANLZ analysis.
    if not anlz_buildups and smart_drops:
        existing_beats = {m[0] for m in markers}
        for drop_beat in smart_drops:
            up_beat = max(0, drop_beat - 32)
            if up_beat >= 0 and up_beat not in existing_beats:
                markers.append((up_beat, "up"))
                existing_beats.add(up_beat)

    if not markers:
        return ()

    # Same-beat tiebreak: match _current_phrase_context priority
    # (low=3 > chorus=2 > up=1 → low wins at same beat).
    _priority = {"low": 0, "chorus": 1, "up": 2}
    markers.sort(key=lambda m: (m[0], _priority.get(m[1], 3)))

    # Deduplicate: keep highest-priority label at each beat (first after sort).
    deduped: list[tuple[int, str]] = []
    for beat, label in markers:
        if deduped and deduped[-1][0] == beat:
            continue
        deduped.append((beat, label))

    # Build segments from consecutive markers.
    segments: list[PhraseSegment] = []
    for i in range(len(deduped) - 1):
        start_beat, label = deduped[i]
        end_beat = deduped[i + 1][0]
        if end_beat > start_beat:
            segments.append(PhraseSegment(
                start_beat=float(start_beat),
                end_beat=float(end_beat),
                label=label,
            ))

    # Final marker: use total_beats if available; otherwise skip.
    # Phase 2 does not invent a final segment duration.
    if deduped and total_beats > 0:
        last_beat, last_label = deduped[-1]
        if total_beats > last_beat:
            segments.append(PhraseSegment(
                start_beat=float(last_beat),
                end_beat=float(total_beats),
                label=last_label,
            ))

    return tuple(segments)


def select_smart_drops(
    raw_drops: list[int],
    *,
    total_beats: int = 0,
    ignore_intro_beats: int = SMART_DROP_IGNORE_INTRO_BEATS,
    ignore_outro_beats: int = SMART_DROP_IGNORE_OUTRO_BEATS,
    min_gap_beats: int = SMART_DROP_MIN_GAP_BEATS,
) -> list[int]:
    """Return Smart Drop candidates after conservative intro/outro filtering."""
    selected: list[int] = []
    previous_drop_beat: Optional[int] = None
    outro_start = total_beats - ignore_outro_beats if total_beats > 0 else 0
    for drop_beat in sorted(set(raw_drops)):
        if drop_beat < ignore_intro_beats:
            continue
        if outro_start > 0 and drop_beat >= outro_start:
            continue
        if previous_drop_beat is not None and drop_beat - previous_drop_beat < min_gap_beats:
            previous_drop_beat = drop_beat
            continue
        selected.append(drop_beat)
        previous_drop_beat = drop_beat
    return selected


def select_smart_breakdowns(
    raw_breakdowns: list[int],
    *,
    total_beats: int = 0,
) -> list[int]:
    return select_smart_drops(
        raw_breakdowns,
        total_beats=total_beats,
        ignore_intro_beats=SMART_BREAKDOWN_IGNORE_INTRO_BEATS,
        ignore_outro_beats=SMART_BREAKDOWN_IGNORE_OUTRO_BEATS,
        min_gap_beats=0,
    )



def find_restore_beat(
    breakdown_beat: int,
    anlz_buildups: list[int],
    smart_drops: list[int],
    default_duration: int,
) -> int:
    candidates = []
    candidates.extend([b for b in anlz_buildups if b > breakdown_beat])
    candidates.extend([b for b in smart_drops if b > breakdown_beat])
    if candidates:
        return min(candidates)
    return breakdown_beat + default_duration
