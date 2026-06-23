"""Shared log-formatting helpers for rb_ss_bridge_v2.

Design rules
------------
Subsystem tags  [SM] [MEM] [TL] [FRES] [LBPM] [OS2L] [MTC] [RSR] [MAIN]
Field order     deck= | primary-fact | src= | elapsed= | bpm= | file= | reason=
elapsed()       always M:SS.mmm
short()         basename only; "<none>" on empty/None
log_once()      suppress repeated identical one-shots per bridge session
"""
from __future__ import annotations

import os as _os
import threading
import time as _time
from typing import Any, Optional


def elapsed(ms: int | float) -> str:
    """Format milliseconds as M:SS.mmm.  e.g. 83461 → '1:23.461'"""
    ms_int  = max(0, int(ms))
    total_s = ms_int // 1000
    rem_ms  = ms_int % 1000
    minutes = total_s // 60
    seconds = total_s % 60
    return f"{minutes}:{seconds:02d}.{rem_ms:03d}"


def short(path: Optional[str]) -> str:
    """Return basename of path, or '<none>' if empty/None."""
    if not path:
        return "<none>"
    return _os.path.basename(path)


class _OnceLog:
    """Log each key at most once per bridge session (process-scoped)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def should_log(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True


_ONCE = _OnceLog()


def log_once(key: str) -> bool:
    """Return True the first time *key* is seen this session; False thereafter."""
    return _ONCE.should_log(key)


class _RateState:
    """Process-scoped throttle + change-detection state for log gating.

    Thread-safe; every method holds the lock only for an O(1) dict access, so it
    is safe to call from high-frequency threads (e.g. the 30 fps Govee runner).
    """

    _MISSING = object()

    def __init__(self) -> None:
        self._last_emit: dict[str, float] = {}
        self._last_value: dict[str, Any] = {}
        self._lock = threading.Lock()

    def throttled(self, key: str, min_interval_s: float, now: Optional[float] = None) -> bool:
        ts = _time.monotonic() if now is None else float(now)
        with self._lock:
            last = self._last_emit.get(key)
            if last is not None and (ts - last) < float(min_interval_s):
                return False
            self._last_emit[key] = ts
            return True

    def changed(self, key: str, value: Any) -> bool:
        with self._lock:
            prev = self._last_value.get(key, self._MISSING)
            if prev is not self._MISSING and prev == value:
                return False
            self._last_value[key] = value
            return True

    def reset(self) -> None:
        """Clear all throttle/change state. For test isolation only."""
        with self._lock:
            self._last_emit.clear()
            self._last_value.clear()


_RATE = _RateState()


def reset_rate_state() -> None:
    """Reset the process-global throttle/change registry.

    Test-support only.  Throttle keys are sometimes derived from ``id(obj)``,
    which CPython reuses after an object is collected, so without a reset the
    global registry leaks state across tests that create many short-lived
    objects (e.g. one status writer per test).  Production never needs this.
    """
    _RATE.reset()


def log_throttled(key: str, min_interval_s: float, now: Optional[float] = None) -> bool:
    """Return True at most once per *min_interval_s* for *key* (first call True).

    Pass *now* (monotonic seconds) from a thread that already has a timestamp to
    avoid an extra clock read.
    """
    return _RATE.throttled(key, min_interval_s, now)


def log_changed(key: str, value: Any) -> bool:
    """Return True only when *value* differs from the last value seen for *key*.

    First call for a key returns True. Use to log state transitions once instead
    of every tick.
    """
    return _RATE.changed(key, value)
