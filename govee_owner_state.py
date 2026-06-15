"""Owner tracking for cloud and realtime Govee control paths."""
from __future__ import annotations

import threading
from enum import Enum


class OwnerState(str, Enum):
    NONE = "none"
    CLOUD_DIY = "cloud_diy"
    REALTIME_RAZER = "realtime_razer"


class GoveeOwnerStateMachine:
    """Tiny locked state machine for transport ownership."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = OwnerState.NONE

    def acquire(self, owner: OwnerState) -> bool:
        with self._lock:
            if self._current in (OwnerState.NONE, owner):
                self._current = owner
                return True
            return False

    def release(self, owner: OwnerState) -> bool:
        with self._lock:
            if self._current != owner:
                return False
            self._current = OwnerState.NONE
            return True

    def current(self) -> OwnerState:
        with self._lock:
            return self._current

    def force_release(self) -> None:
        with self._lock:
            self._current = OwnerState.NONE
