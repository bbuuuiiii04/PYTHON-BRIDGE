"""Pure, renderer-agnostic drop / post_drop lifecycle resolver.

Mirrors the LED drop-region resolver in state_manager.py (_led_role_from_smart_phrasing and its
helpers). Pure: no I/O, no bridge imports. `sp` is any object exposing the SmartPhrasing attributes
read below (the live laser passes a SmartPhrasingState; tests pass a types.SimpleNamespace).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DropLifecycleConfig:
    max_drops_in_a_row: int            # = LED_MAX_DROP_IMPACTS (2)
    drop_impact_beats: float           # flat impact window (operator 32.0; LED-parity 8.0)
    post_drop_cycle_beats: float       # inert here; carried for the future native-DMX cadence
    impact_predecessors: frozenset     # = frozenset({"up", "low", "buildup", "breakdown"})


@dataclass(frozen=True)
class DropResult:
    role: str            # "drop" | "post_drop" | "none"
    armed_this_tick: bool


class DropLifecycle:
    def __init__(self, config: DropLifecycleConfig) -> None:
        self._config = config
        self._first_drop_anchor_beat: Optional[float] = None
        self._impact_until_beat: Optional[float] = None
        self._impact_count: int = 0

    def reset(self) -> None:
        self._first_drop_anchor_beat = None
        self._impact_until_beat = None
        self._impact_count = 0

    def _abs_beat(self, sp) -> Optional[float]:
        if sp.abs_beat is not None:
            return float(sp.abs_beat)
        if sp.current_phrase_start_beat is not None and sp.beats_into_phrase is not None:
            return float(sp.current_phrase_start_beat) + float(sp.beats_into_phrase)
        if sp.active_drop_beat is not None:
            return float(sp.active_drop_beat)
        return None

    def drop_anchor(self, sp) -> Optional[float]:
        if sp.current_phrase_is_chorus and sp.phrase_start_crossing:
            if sp.current_phrase_start_beat is not None:
                return float(sp.current_phrase_start_beat)
        if sp.smart_drop_crossing:
            if sp.active_drop_beat is not None:
                return float(sp.active_drop_beat)
            return self._abs_beat(sp)
        return None

    def impact_allowed(self, sp) -> bool:
        previous = str(sp.previous_phrase_label or "other")
        if previous in self._config.impact_predecessors:
            return True
        if sp.smart_drop_crossing:
            current = str(sp.current_phrase_label or "other")
            if current in self._config.impact_predecessors:
                return True
        if previous == "chorus":
            if (
                self._first_drop_anchor_beat is not None
                and self._impact_count < self._config.max_drops_in_a_row
            ):
                return True
        return False

    def should_clear(self, sp) -> bool:
        if sp.smart_drop_crossing:
            return False
        if sp.current_phrase_is_chorus or sp.smart_post_drop_active:
            return False
        return self._first_drop_anchor_beat is not None

    def arm(self, anchor_beat: float) -> None:
        if self._first_drop_anchor_beat is None:
            self._first_drop_anchor_beat = float(anchor_beat)
        self._impact_until_beat = float(anchor_beat) + self._config.drop_impact_beats
        self._impact_count += 1

    def resolve(self, sp, *, mutate: bool) -> DropResult:
        if mutate and self.should_clear(sp):
            self.reset()
        anchor = self.drop_anchor(sp)
        if anchor is not None:
            if self.impact_allowed(sp):
                armed_this_tick = False
                if mutate:
                    self.arm(anchor)
                    armed_this_tick = True
                return DropResult(role="drop", armed_this_tick=armed_this_tick)
            if mutate and self._first_drop_anchor_beat is None:
                self._first_drop_anchor_beat = anchor
            return DropResult(role="post_drop", armed_this_tick=False)
        # No anchor. Reproduce ONLY the chorus/post_drop window (LED :2248-2256). Breakdown,
        # pre_drop, buildup, low, groove are the laser director's OWN branches -> "none".
        if sp.current_phrase_is_chorus or sp.smart_post_drop_active:
            abs_beat = self._abs_beat(sp)
            if (
                abs_beat is not None
                and self._impact_until_beat is not None
                and abs_beat < self._impact_until_beat
            ):
                return DropResult(role="drop", armed_this_tick=False)
            return DropResult(role="post_drop", armed_this_tick=False)
        return DropResult(role="none", armed_this_tick=False)
