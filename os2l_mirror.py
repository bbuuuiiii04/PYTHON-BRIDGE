"""OS2L queue-boundary mirror and optional JSONL capture."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional


CAPTURE_DIR = "/tmp/rb_ss_bridge_v2_captures"


@dataclass(frozen=True)
class MirrorRecord:
    ts: float
    outcome: str
    packet_kind: str
    deck: int
    trigger: str
    value: Any
    source_helper: str
    simulated: bool
    packet: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "outcome": self.outcome,
            "packet_kind": self.packet_kind,
            "deck": self.deck,
            "trigger": self.trigger,
            "value": self.value,
            "source_helper": self.source_helper,
            "simulated": self.simulated,
            "packet": self.packet,
        }


class OS2LMirror:
    """Bounded, thread-safe packet mirror.

    Outcomes are intentionally queue-boundary accurate:
      queued, queue_full_drop, sent_live, no_socket_drop, send_error, simulated
    """

    def __init__(self, ring_size: int = 200) -> None:
        self._lock = threading.Lock()
        self._ring: deque[MirrorRecord] = deque(maxlen=ring_size)
        self._enabled = False
        self._capture_path: Optional[str] = None
        self._capture_fp = None
        self._outcome_counts: dict[str, int] = {}

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def toggle(self) -> bool:
        with self._lock:
            self._enabled = not self._enabled
            return self._enabled

    def start_capture(self, name: str) -> str:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-"))[:40] or "capture"
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        path = os.path.join(CAPTURE_DIR, f"{safe}.jsonl")
        with self._lock:
            self._close_capture_locked()
            self._capture_fp = open(path, "a", encoding="utf-8")
            self._capture_path = path
            self._enabled = True
        return path

    def stop_capture(self) -> Optional[str]:
        with self._lock:
            path = self._capture_path
            self._close_capture_locked()
            return path

    def record(
        self,
        obj: dict[str, Any],
        outcome: str,
        *,
        simulated: bool = False,
        source_helper: str = "",
    ) -> None:
        ts = time.time()
        record = MirrorRecord(
            ts=ts,
            outcome=outcome,
            packet_kind=str(obj.get("evt", "")),
            deck=int(obj.get("deck") or _deck_from_trigger(str(obj.get("trigger", ""))) or 0),
            trigger=str(obj.get("trigger", "")),
            value=obj.get("value"),
            source_helper=source_helper,
            simulated=simulated,
            packet=dict(obj),
        )
        line = None
        with self._lock:
            self._outcome_counts[outcome] = self._outcome_counts.get(outcome, 0) + 1
            if self._enabled or self._capture_fp is not None:
                self._ring.append(record)
                line = json.dumps(record.to_dict(), sort_keys=True)
                fp = self._capture_fp
            else:
                fp = None
        if fp is not None and line is not None:
            try:
                fp.write(line + "\n")
                fp.flush()
            except OSError:
                with self._lock:
                    self._close_capture_locked()

    def get_summary(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            recent = [r for r in self._ring if now - r.ts <= 10.0]
            last = self._ring[-1].to_dict() if self._ring else None
            return {
                "enabled": self._enabled,
                "capture_path": self._capture_path,
                "capturing": self._capture_fp is not None,
                "ring_size": len(self._ring),
                "last_packet": last,
                "rate_per_s": round(len(recent) / 10.0, 2),
                "outcome_counts": dict(self._outcome_counts),
            }

    def _close_capture_locked(self) -> None:
        if self._capture_fp is not None:
            try:
                self._capture_fp.close()
            except OSError:
                pass
        self._capture_fp = None
        self._capture_path = None


def _deck_from_trigger(trigger: str) -> int:
    parts = trigger.split()
    if len(parts) >= 2 and parts[0] == "deck":
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0
