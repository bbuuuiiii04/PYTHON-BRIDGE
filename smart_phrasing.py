from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

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
    smart_post_drop_active: bool
    active_drop_beat: Optional[float]
    smart_buildup_active: bool
    smart_breakdown_active: bool
    breakdown_start_crossing: bool
    breakdown_end_crossing: bool
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

    def reset(self, reason: str) -> SmartPhrasingState:
        self._previous_abs_beat = None
        self._fired_drop_beats.clear()
        self._active_drop_beat = None
        self._last_deck_id = None
        self._last_track_id = None
        self._transition_window_active = False

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
            smart_post_drop_active=False,
            active_drop_beat=None,
            smart_buildup_active=False,
            smart_breakdown_active=False,
            breakdown_start_crossing=False,
            breakdown_end_crossing=False,
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
        
        # 3. Drop crossing
        smart_drop_crossing = False
        if prev_abs_beat is not None:
            for drop_beat in sorted(snapshot.smart_drop_beats):
                if prev_abs_beat < drop_beat <= abs_beat and drop_beat not in self._fired_drop_beats:
                    smart_drop_crossing = True
                    self._fired_drop_beats.add(drop_beat)
                    self._active_drop_beat = drop_beat
                    break
                    
        # 2. Resolve next Smart Drop
        next_smart_drop_beat = None
        beats_to_next_drop = None
        for drop_beat in sorted(snapshot.smart_drop_beats):
            if drop_beat >= abs_beat and drop_beat not in self._fired_drop_beats:
                next_smart_drop_beat = drop_beat
                beats_to_next_drop = drop_beat - abs_beat
                break
                
        # 4. Drop window
        smart_drop_window_active = False
        if next_smart_drop_beat is not None and beats_to_next_drop is not None:
            smart_drop_window_active = beats_to_next_drop <= snapshot.drop_window_beats

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
            smart_post_drop_active=smart_post_drop_active,
            active_drop_beat=self._active_drop_beat,
            smart_buildup_active=smart_buildup_active,
            smart_breakdown_active=smart_breakdown_active,
            breakdown_start_crossing=breakdown_start_crossing,
            breakdown_end_crossing=breakdown_end_crossing,
            transition_mask_should_arm=transition_mask_should_arm,
            transition_mask_should_clear=transition_mask_should_clear,
            transition_window_active=new_transition_window_active,
            reason="tick",
        )
        
        self._last_deck_id = snapshot.deck_id
        self._last_track_id = snapshot.track_id
        self._previous_abs_beat = snapshot.abs_beat
        
        return SmartPhrasingResult(state=state, diagnostics=tuple(diagnostics))
