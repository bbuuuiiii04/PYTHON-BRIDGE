"""
Ableton Link BPM + phase reader via aalink.

LinkReader runs a background daemon thread with its own asyncio event loop,
polls the Link session at ~60 Hz, and exposes thread-safe bpm / phase / available
properties.

Used by StateManager._push_tick for unscripted (autoloop) mode only.
Scripted mode must NOT use these values — scripted shows depend on track-relative timing.

Degrades gracefully when aalink is not installed or Link has no peers.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

log = logging.getLogger("link_reader")

_POLL_INTERVAL = 1.0 / 60   # 60 Hz
_QUANTUM       = 4.0         # 4-beat bar


class LinkReader:
    """Background daemon thread that reads BPM + phase from the Ableton Link session.

    If aalink is not installed or Link cannot start, all properties return
    safe defaults (bpm=0.0, phase=0.0, available=False) without raising.
    """

    def __init__(self) -> None:
        self._lock   = threading.Lock()
        self._bpm:   float = 0.0
        self._phase: float = 0.0
        self._available: bool = False
        self._stop   = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public properties (thread-safe) ───────────────────────────────────────

    @property
    def bpm(self) -> float:
        with self._lock:
            return self._bpm

    @property
    def phase(self) -> float:
        with self._lock:
            return self._phase

    @property
    def available(self) -> bool:
        """True when Link has at least one peer and a valid tempo."""
        with self._lock:
            return self._available

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="link-reader", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import aalink  # type: ignore
        except ImportError:
            log.debug("LinkReader: aalink not installed — Link disabled")
            return
        try:
            asyncio.run(self._async_run(aalink))
        except Exception:
            log.exception("LinkReader: event loop crashed")

    async def _async_run(self, aalink) -> None:
        try:
            link = aalink.Link(120.0)
            link.quantum = _QUANTUM
            link.enabled = True
        except Exception as exc:
            log.warning("LinkReader: could not start Link session: %s", exc)
            return

        log.info("LinkReader: Ableton Link active — polling at 60 Hz")
        last_logged_bpm = 0.0

        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                peers = link.num_peers
                if peers >= 1:
                    bpm   = float(link.tempo)
                    phase = float(link.phase) % _QUANTUM
                    with self._lock:
                        self._bpm       = bpm
                        self._phase     = phase
                        self._available = bpm > 0
                    if bpm > 0 and abs(bpm - last_logged_bpm) >= 0.1:
                        log.info("Link BPM: %.2f (peers=%d)", bpm, peers)
                        last_logged_bpm = bpm
                else:
                    with self._lock:
                        self._available = False
                    if last_logged_bpm != 0.0:
                        log.info("Link: no peers")
                        last_logged_bpm = 0.0
            except Exception as exc:
                log.debug("LinkReader: poll error: %s", exc)
                with self._lock:
                    self._available = False

            remaining = _POLL_INTERVAL - (time.monotonic() - t0)
            if remaining > 0:
                await asyncio.sleep(remaining)
