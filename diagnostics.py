"""
Pipeline diagnostics and debug tooling.

Enable per-module debug logging:
  export BRIDGE_DEBUG=1   (or pass --debug on CLI)

Drift detection between memory position and TL-derived state.
Per-deck state transition logger.
Latency sampler for event ingestion → processing.
"""
from __future__ import annotations

import collections
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .models import BridgeEvent, Ev

log = logging.getLogger("diagnostics")


# ── Per-deck state transition logger ─────────────────────────────────────────

@dataclass
class DeckTransition:
    ts: float
    deck: int
    field: str      # what changed ('playing', 'filepath', 'scripted_id', 'master')
    old: object
    new: object
    source: str


class TransitionLog:
    """Records the last N state transitions per deck for debugging."""

    def __init__(self, maxlen: int = 50) -> None:
        self._events: collections.deque[DeckTransition] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, deck: int, field: str, old, new, source: str) -> None:
        if old == new:
            return
        ev = DeckTransition(
            ts=time.monotonic(), deck=deck,
            field=field, old=old, new=new, source=source,
        )
        with self._lock:
            self._events.append(ev)
        log.debug("transition deck=%d [%s] %r → %r  src=%s", deck, field, old, new, source)

    def dump(self) -> list[DeckTransition]:
        with self._lock:
            return list(self._events)


# ── Event pipeline latency sampler ────────────────────────────────────────────

@dataclass
class LatencySample:
    kind: str
    source: str
    enqueue_mono: float     # when event was put_nowait()'d
    process_mono: float     # when StateManager._handle_event() ran
    latency_ms: float = field(init=False)

    def __post_init__(self) -> None:
        self.latency_ms = (self.process_mono - self.enqueue_mono) * 1000.0


class LatencyTracker:
    """Wraps an event queue to measure enqueue→process latency.

    Injects a timestamp into each event's payload at enqueue time.
    StateManager._handle_event reads it back to compute latency.
    """

    _TS_KEY = "__enqueue_mono"

    def __init__(self, inner: queue.Queue[BridgeEvent]) -> None:
        self._inner = inner
        self._samples: collections.deque[LatencySample] = collections.deque(maxlen=200)
        self._lock = threading.Lock()

    def put_nowait(self, ev: BridgeEvent) -> None:
        ev.payload[self._TS_KEY] = time.monotonic()
        self._inner.put_nowait(ev)

    def get_nowait(self) -> BridgeEvent:
        ev = self._inner.get_nowait()
        enqueue_t = ev.payload.pop(self._TS_KEY, None)
        if enqueue_t is not None:
            s = LatencySample(ev.kind, ev.source, enqueue_t, time.monotonic())
            with self._lock:
                self._samples.append(s)
            if s.latency_ms > 20:
                log.warning("event latency: kind=%s src=%s %.1f ms",
                            ev.kind, ev.source, s.latency_ms)
        return ev

    # Proxy Queue methods used by StateManager
    def get(self, *a, **kw):
        return self._inner.get(*a, **kw)

    def qsize(self) -> int:
        return self._inner.qsize()

    def percentiles(self) -> dict[str, float]:
        with self._lock:
            samples = sorted(s.latency_ms for s in self._samples)
        if not samples:
            return {}
        n = len(samples)
        return {
            "p50": samples[n // 2],
            "p95": samples[int(n * 0.95)],
            "p99": samples[int(n * 0.99)],
            "max": samples[-1],
            "n":   float(n),
        }


# ── Memory vs TL position drift detector ─────────────────────────────────────

class DriftDetector:
    """Detects when memory position diverges from TL-expected position.

    The TL log doesn't give us position, but we know position should be
    monotonically increasing when playing. A backward jump or sudden freeze
    indicates a seek or RB restart.
    """

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
    for name in ("tl_tailer", "rb_memory", "filepath_resolver",
                 "scripted_tracks", "osl_output", "state_manager",
                 "diagnostics", "bridge"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    log.info("Verbose debug mode enabled")


def is_debug() -> bool:
    return bool(os.environ.get("BRIDGE_DEBUG"))
