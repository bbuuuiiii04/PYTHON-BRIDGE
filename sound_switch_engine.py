"""SoundSwitch routing facade over OS2L output sends."""
from __future__ import annotations

from .osl_output import OS2LOutput


class SoundSwitchEngine:
    """Facade for SoundSwitch routing/sends."""

    def __init__(self, out: OS2LOutput) -> None:
        self._out = out

    def deck_route(self, active: int) -> tuple[int, ...]:
        """Return canonical 4-deck routing tuple for the active deck."""
        mirror = 3 - active
        return (active, mirror, 3, 4)

    def send_loop_off(self, deck: int) -> None:
        """Delegate per-deck loop-off to the underlying OS2L output."""
        self._out.send_loop_off(deck)

    def send_deck_clear(self, deck: int) -> None:
        """Delegate per-deck SS clear to the underlying OS2L output."""
        self._out.send_deck_clear(deck)

    def send_autoloop_deck_load(
        self,
        deck: int,
        mirror: int,
        active: int,
        arm_meta: "TrackMetadata",
    ) -> None:
        """Fan out an autoloop deck-load (play=on) across the canonical 4-deck route."""
        for dk in self.deck_route(deck):
            self._out.send_deck_load(dk, arm_meta, active, play="on")

    def send_autoloop_clear(self, active: int) -> None:
        """Clear SS deck slots and disarm autoloop across the canonical 4-deck route."""
        for dk in self.deck_route(active):
            self._out.send_deck_clear(dk)
            self._out.send_loop_off(dk)

    def send_smart_transition_clear(self, active: int) -> None:
        """Clear SS deck slots and disarm loops across the canonical 4-deck route
        for a smart-transition cut/preclear (smart-drop legacy cut, smart-breakdown
        cut, phrase-anchor pre-clear).
        Byte-equivalent to send_autoloop_clear(active), but kept distinct to avoid
        coupling smart-transition intent to autoloop arm/disarm semantics.
        """
        for dk in self.deck_route(active):
            self._out.send_deck_clear(dk)
            self._out.send_loop_off(dk)

    def send_autoloop_bpm(self, active: int, bpm: float) -> None:
        """Fan out an autoloop BPM update across the canonical 4-deck route."""
        for dk in self.deck_route(active):
            self._out.send_bpm(dk, bpm)

    def send_live_bpm_follow(self, active: int, bpm: float) -> None:
        """Fan out a live-BPM-follow update across the canonical 4-deck route.
        Byte-equivalent to send_autoloop_bpm(active, bpm), but kept distinct
        to avoid coupling live-BPM-follow intent to autoloop arm/disarm
        semantics.
        """
        for dk in self.deck_route(active):
            self._out.send_bpm(dk, bpm)

    def send_scripted_arm_phase0(self, active: int) -> None:
        """Phase 0 of scripted arm: clear filepath, loop-off, play-off across the canonical 4-deck route."""
        for dk in self.deck_route(active):
            self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            self._out.send_loop_off(dk)
            self._out.send_deck_play(dk, "off")

    def send_scripted_arm_phase1(
        self,
        deck: int,
        arm_meta: "TrackMetadata",
        active: int,
    ) -> None:
        """Phase 1 of scripted arm: send_deck_load(play="on") across the canonical 4-deck route for the armed deck."""
        for dk in self.deck_route(deck):
            self._out.send_deck_load(dk, arm_meta, active, play="on")
