"""JSONL session recorder for StateManager replay inputs."""
from __future__ import annotations

import atexit
import json
import os
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .live_bpm import LiveBPMStatus
from .models import BridgeEvent, PositionSnapshot

RECORD_SESSION_ENV = "RBSS_RECORD_SESSION"
RECORD_DEDUP_ENV = "RBSS_RECORD_DEDUP"


class SessionRecorder:
    """Thread-safe JSONL recorder for pre-tick StateManager inputs."""

    def __init__(self, path: str | os.PathLike[str], *, dedup: bool = False) -> None:
        self.path = Path(path)
        self.dedup = dedup
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = self.path.open("w", encoding="utf-8", buffering=1024 * 1024)
        self._closed = False
        self._counts: dict[str, int] = {"event": 0, "position": 0, "live_bpm": 0}
        self._position_seen: dict[int, tuple[int, bool, int]] = {}
        self._write_locked(
            {
                "kind": "header",
                "schema": 1,
                "started_at": time.time(),
                "started_mono": time.monotonic(),
            }
        )
        atexit.register(self.close)

    @classmethod
    def from_env(cls) -> Optional["SessionRecorder"]:
        path = os.environ.get(RECORD_SESSION_ENV)
        if not path:
            return None
        return cls(path, dedup=os.environ.get(RECORD_DEDUP_ENV) == "1")

    def record_event(self, ev: BridgeEvent) -> None:
        self._append({"t": ev.mono, "kind": "event", "data": asdict(ev)})

    def record_position(self, deck: int, snap: PositionSnapshot) -> None:
        with self._lock:
            if self._closed:
                return
            if self.dedup:
                key = (int(snap.elapsed_ms), bool(snap.playing), int(snap.track_length_ms))
                if self._position_seen.get(deck) == key:
                    return
                self._position_seen[deck] = key
            row = {
                "t": snap.updated_at,
                "kind": "position",
                "deck": deck,
                "data": asdict(snap),
            }
            self._write_locked(row)
            self._counts["position"] += 1

    def record_live_bpm(
        self,
        deck: int,
        bpm: Optional[float],
        status: Optional[LiveBPMStatus],
    ) -> None:
        self._append(
            {
                "t": time.monotonic(),
                "kind": "live_bpm",
                "deck": deck,
                "data": {
                    "bpm": bpm,
                    "status": asdict(status) if status is not None else None,
                },
            }
        )

    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def status(self) -> dict:
        with self._lock:
            return {
                "active": not self._closed,
                "path": str(self.path),
                "dedup": self.dedup,
                "counts": dict(self._counts),
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._fh.flush()
            self._fh.close()
            self._closed = True
            total = sum(self._counts.values())
            print(
                "[REC] session-capture "
                f"path={self.path} total={total} "
                f"events={self._counts['event']} "
                f"positions={self._counts['position']} "
                f"live_bpm={self._counts['live_bpm']}",
                file=sys.stderr,
            )

    def _append(self, row: dict) -> None:
        with self._lock:
            if self._closed:
                return
            self._write_locked(row)
            kind = row.get("kind")
            if kind in self._counts:
                self._counts[kind] += 1

    def _write_locked(self, row: dict) -> None:
        self._fh.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def from_env() -> Optional[SessionRecorder]:
    return SessionRecorder.from_env()
