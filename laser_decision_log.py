"""Bounded structured log for LaserDirector scene decisions."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Literal, Optional


@dataclass(frozen=True)
class LaserDecision:
    mono: float
    wall: float
    scene: str
    prev_scene: str
    reason: str
    abs_beat: Optional[float]
    deck: int
    personality: str
    lighting_mode: str
    triggered_by: Literal["scene_change", "reason_update"]


class LaserDecisionLog:
    def __init__(self, capacity: int = 32) -> None:
        self._decisions: deque[LaserDecision] = deque(maxlen=max(1, int(capacity)))
        self._lock = Lock()

    def record(self, decision: LaserDecision) -> None:
        with self._lock:
            self._decisions.append(decision)

    def recent(self, n: int = 32) -> list[LaserDecision]:
        limit = max(0, int(n))
        with self._lock:
            if limit == 0:
                return []
            return list(self._decisions)[-limit:]

    def as_dicts(self) -> list[dict]:
        with self._lock:
            return [asdict(decision) for decision in self._decisions]

    def recent_as_dicts(self, n: int = 32) -> list[dict]:
        limit = max(0, int(n))
        with self._lock:
            if limit == 0:
                return []
            tail = list(self._decisions)[-limit:]
        return [asdict(decision) for decision in tail]
