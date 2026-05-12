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
