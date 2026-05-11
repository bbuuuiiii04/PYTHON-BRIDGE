from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from .config import (
    SMART_DROP_IGNORE_INTRO_BEATS,
    SMART_DROP_IGNORE_OUTRO_BEATS,
    SMART_BREAKDOWN_IGNORE_INTRO_BEATS,
    SMART_BREAKDOWN_IGNORE_OUTRO_BEATS,
)


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

@dataclass(frozen=True)
class SmartPhrasingState:
    current_phrase_label: PhraseLabel
    current_phrase_is_up: bool
    current_phrase_is_chorus: bool
    current_phrase_is_low: bool
    next_smart_drop_beat: Optional[float]
    beats_to_next_drop: Optional[float]
    smart_drop_window_active: bool
    smart_drop_crossing: bool
    smart_drop_preclear_requested: bool
    smart_drop_rearm_requested: bool
    smart_post_drop_active: bool
    active_drop_beat: Optional[float]
    smart_buildup_active: bool
    smart_breakdown_active: bool
    breakdown_start_crossing: bool
    breakdown_end_crossing: bool
    smart_breakdown_clear_requested: bool
    smart_breakdown_restore_requested: bool
    transition_mask_should_arm: bool
    transition_mask_should_clear: bool
    transition_window_active: bool
    reason: str = ""

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

class SmartPhrasingEngine:
    def __init__(self) -> None:
        self._previous_abs_beat: Optional[float] = None
        self._fired_drop_beats: set[float] = set()
        self._active_drop_beat: Optional[float] = None
        self._last_deck_id: Optional[str] = None
        self._last_track_id: Optional[str] = None
        self._transition_window_active: bool = False
        self._smart_drop_window_active: bool = False

    def reset(self, reason: str) -> SmartPhrasingState:
        self._previous_abs_beat = None
        self._fired_drop_beats.clear()
        self._active_drop_beat = None
        self._last_deck_id = None
        self._last_track_id = None
        self._transition_window_active = False
        self._smart_drop_window_active = False

        return self._default_state(reason)

    def _default_state(self, reason: str) -> SmartPhrasingState:
        return SmartPhrasingState(
            current_phrase_label="other",
            current_phrase_is_up=False,
            current_phrase_is_chorus=False,
            current_phrase_is_low=False,
            next_smart_drop_beat=None,
            beats_to_next_drop=None,
            smart_drop_window_active=False,
            smart_drop_crossing=False,
            smart_drop_preclear_requested=False,
            smart_drop_rearm_requested=False,
            smart_post_drop_active=False,
            active_drop_beat=None,
            smart_buildup_active=False,
            smart_breakdown_active=False,
            breakdown_start_crossing=False,
            breakdown_end_crossing=False,
            smart_breakdown_clear_requested=False,
            smart_breakdown_restore_requested=False,
            transition_mask_should_arm=False,
            transition_mask_should_clear=False,
            transition_window_active=False,
            reason=reason,
        )

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
        elif self._previous_abs_beat is not None and abs_beat < self._previous_abs_beat:
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
        
        # 1. Resolve current phrase
        current_phrase_label: PhraseLabel = "other"
        for seg in snapshot.phrase_segments:
            if seg.start_beat <= abs_beat < seg.end_beat:
                current_phrase_label = seg.label
                break
                
        current_phrase_is_up = current_phrase_label == "up"
        current_phrase_is_chorus = current_phrase_label == "chorus"
        current_phrase_is_low = current_phrase_label == "low"
        
        # 2. Drop crossing
        # Drop crossing is detected first so already-fired drops are excluded from the next future drop selection.
        smart_drop_crossing = False
        if prev_abs_beat is not None:
            for drop_beat in sorted(snapshot.smart_drop_beats):
                if prev_abs_beat < drop_beat <= abs_beat and drop_beat not in self._fired_drop_beats:
                    smart_drop_crossing = True
                    self._fired_drop_beats.add(drop_beat)
                    self._active_drop_beat = drop_beat
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
        if smart_drop_window_active and not self._smart_drop_window_active:
            smart_drop_preclear_requested = True
            
        self._smart_drop_window_active = smart_drop_window_active
        
        # 4b. Rearm Intent
        smart_drop_rearm_requested = smart_drop_crossing

        # 5. Post-drop
        smart_post_drop_active = False
        if self._active_drop_beat is not None:
            if abs_beat >= self._active_drop_beat and abs_beat < self._active_drop_beat + snapshot.post_drop_beats:
                smart_post_drop_active = True
            else:
                self._active_drop_beat = None
                
        # 6. Buildup
        smart_buildup_active = False
        if current_phrase_is_up and next_smart_drop_beat is not None and beats_to_next_drop is not None:
            if beats_to_next_drop <= snapshot.phrase_lookahead_beats:
                smart_buildup_active = True
                
        # 7. Breakdown
        smart_breakdown_active = False
        breakdown_start_crossing = False
        breakdown_end_crossing = False
        
        for seg in snapshot.breakdown_segments:
            if seg.start_beat <= abs_beat < seg.end_beat:
                smart_breakdown_active = True

            if prev_abs_beat is not None:
                if prev_abs_beat < seg.start_beat <= abs_beat:
                    breakdown_start_crossing = True
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
        
        if new_transition_window_active and not self._transition_window_active:
            transition_mask_should_arm = True
        elif not new_transition_window_active and self._transition_window_active:
            transition_mask_should_clear = True
            
        self._transition_window_active = new_transition_window_active
        
        state = SmartPhrasingState(
            current_phrase_label=current_phrase_label,
            current_phrase_is_up=current_phrase_is_up,
            current_phrase_is_chorus=current_phrase_is_chorus,
            current_phrase_is_low=current_phrase_is_low,
            next_smart_drop_beat=next_smart_drop_beat,
            beats_to_next_drop=beats_to_next_drop,
            smart_drop_window_active=smart_drop_window_active,
            smart_drop_crossing=smart_drop_crossing,
            smart_drop_preclear_requested=smart_drop_preclear_requested,
            smart_drop_rearm_requested=smart_drop_rearm_requested,
            smart_post_drop_active=smart_post_drop_active,
            active_drop_beat=self._active_drop_beat,
            smart_buildup_active=smart_buildup_active,
            smart_breakdown_active=smart_breakdown_active,
            breakdown_start_crossing=breakdown_start_crossing,
            breakdown_end_crossing=breakdown_end_crossing,
            smart_breakdown_clear_requested=smart_breakdown_clear_requested,
            smart_breakdown_restore_requested=smart_breakdown_restore_requested,
            transition_mask_should_arm=transition_mask_should_arm,
            transition_mask_should_clear=transition_mask_should_clear,
            transition_window_active=new_transition_window_active,
            reason="tick",
        )
        
        self._last_deck_id = snapshot.deck_id
        self._last_track_id = snapshot.track_id
        self._previous_abs_beat = snapshot.abs_beat
        
        return SmartPhrasingResult(state=state, diagnostics=tuple(diagnostics))


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



def build_phase2_phrase_segments(
    anlz_buildups: list[int],
    anlz_drops: list[int],
    anlz_breakdowns: list[int],
    smart_drops: list[int],
    total_beats: int,
) -> tuple[PhraseSegment, ...]:
    """Phase 2 shadow: infer PhraseSegment ranges from ordered ANLZ markers.

    Maps: anlz_buildups → "up", anlz_drops → "chorus", anlz_breakdowns → "low".
    Each marker's end_beat = next marker's start_beat.
    Final marker uses *total_beats* (from beatgrid length) if available,
    otherwise it is skipped — Phase 2 does not invent arbitrary durations.

    When no explicit anlz_buildups exist but smart_drops are present, infers
    conservative 32-beat "up" segments before each Smart Drop.  This is a
    Phase 2 shadow fallback based on the project rule that true musical
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

    # Phase 2 shadow fallback: infer 32-beat "up" segments before Smart Drops
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
) -> list[int]:
    """Return Smart Drop candidates after conservative intro/outro filtering."""
    selected: list[int] = []
    outro_start = total_beats - ignore_outro_beats if total_beats > 0 else 0
    for drop_beat in sorted(set(raw_drops)):
        if drop_beat < ignore_intro_beats:
            continue
        if outro_start > 0 and drop_beat >= outro_start:
            continue
        selected.append(drop_beat)
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
