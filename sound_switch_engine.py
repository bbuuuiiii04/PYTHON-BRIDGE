"""
SoundSwitchEngine scaffold.

PR 6a scope: deck routing helper only. No behavior migration.
"""
from __future__ import annotations

from .osl_output import OS2LOutput


class SoundSwitchEngine:
    """Facade for SoundSwitch routing/sends.

    PR 6a keeps this as a no-op scaffold that only exposes deck_route().
    """

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

    def send_autoloop_bpm(self, active: int, bpm: float) -> None:
        """Fan out an autoloop BPM update across the canonical 4-deck route."""
        for dk in self.deck_route(active):
            self._out.send_bpm(dk, bpm)
