"""
Pipeline diagnostics and debug tooling.

Drift detection for memory position reads. Per-module debug logging is now
`bridge_log.init()`'s job (BRIDGE_DEBUG=1 / --debug set logging.root to
DEBUG; see bridge_log.py and __main__.py:main()).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger("diagnostics")


# ── Memory position drift detector ───────────────────────────────────────────

class DriftDetector:
    """Detects implausible memory-position movement while playing."""

    _BACKWARD_JUMP_MS  = 2_000   # ignore normal rewinds less than this
    _FREEZE_THRESHOLD_S = 3.0    # flag if position doesn't advance for this long

    def __init__(self) -> None:
        self._last_pos: dict[int, tuple[int, float]] = {}   # deck → (ms, mono)

    def update(self, deck: int, elapsed_ms: int, playing: bool) -> Optional[str]:
        """Call on each memory read. Returns a warning string or None."""
        now = time.monotonic()
        prev = self._last_pos.get(deck)
        self._last_pos[deck] = (elapsed_ms, now)

        if prev is None or not playing:
            return None
        prev_ms, prev_mono = prev
        delta_ms   = elapsed_ms - prev_ms
        delta_wall = (now - prev_mono) * 1000.0

        # Backward jump (seek / hot-cue)
        if delta_ms < -self._BACKWARD_JUMP_MS:
            return f"deck {deck}: backward jump {prev_ms}→{elapsed_ms} ms ({delta_ms:+d} ms)"

        # Position freeze while playing
        if playing and abs(delta_ms) < 10 and delta_wall > self._FREEZE_THRESHOLD_S * 1000:
            return (f"deck {deck}: position frozen at {elapsed_ms} ms for "
                    f"{delta_wall:.0f} ms while playing")

        return None
