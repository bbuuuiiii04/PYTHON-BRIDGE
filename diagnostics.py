"""
Pipeline diagnostics and debug tooling.

Enable per-module debug logging:
  export BRIDGE_DEBUG=1   (or pass --debug on CLI)

Drift detection for memory position reads.
"""
from __future__ import annotations

import logging
import os
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


# ── Verbose mode toggle ────────────────────────────────────────────────────────

def enable_debug() -> None:
    """Set all bridge loggers to DEBUG level."""
    for name in ("rb_memory", "filepath_resolver",
                 "scripted_tracks", "osl_output", "state_manager",
                 "diagnostics", "bridge", "logging_manager",
                 # Laser
                 "laser_director", "laser_executor", "laser_config",
                 # LED / Govee
                 "led_look_director", "led_color_engine", "beat_sync_engine",
                 "led_dispatch_coordinator", "govee_scene_adapter",
                 "govee_runtime_sender", "govee_realtime_runner",
                 "govee_realtime_transport", "govee_frame_renderer",
                 "govee_owner_state"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    log.info("Verbose debug mode enabled")


def is_debug() -> bool:
    return bool(os.environ.get("BRIDGE_DEBUG"))
