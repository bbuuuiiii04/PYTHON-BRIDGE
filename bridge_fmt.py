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
from typing import Optional


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
