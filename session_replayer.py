"""Offline replay helpers for recorded StateManager input sessions."""
from __future__ import annotations

import json
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

from .live_bpm import LiveBPMStatus
from .models import BridgeEvent, PositionSnapshot
from .state_manager import StateManager


@dataclass(frozen=True)
class PreTickInputs:
    events: list[BridgeEvent] = field(default_factory=list)
    positions: list[tuple[int, PositionSnapshot]] = field(default_factory=list)
    live_bpm: list[tuple[int, Optional[float], Optional[LiveBPMStatus]]] = field(default_factory=list)


@dataclass
class CapturedSession:
    events: list[BridgeEvent]
    positions: dict[int, list[PositionSnapshot]]
    live_bpm: dict[int, list[tuple[float, Optional[float]]]]
    live_bpm_status: dict[int, list[tuple[float, Optional[LiveBPMStatus]]]] = field(default_factory=dict)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "CapturedSession":
        events: list[BridgeEvent] = []
        positions: dict[int, list[PositionSnapshot]] = {}
        live_bpm: dict[int, list[tuple[float, Optional[float]]]] = {}
        live_bpm_status: dict[int, list[tuple[float, Optional[LiveBPMStatus]]]] = {}

        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                kind = row.get("kind")
                if kind == "header":
                    if row.get("schema") != 1:
                        raise ValueError(f"unsupported session schema: {row.get('schema')!r}")
                    continue
                if kind == "event":
                    events.append(BridgeEvent(**row["data"]))
                elif kind == "position":
                    deck = int(row["deck"])
                    positions.setdefault(deck, []).append(PositionSnapshot(**row["data"]))
                elif kind == "live_bpm":
                    deck = int(row["deck"])
                    data = row.get("data") or {}
                    bpm = data.get("bpm")
                    status_data = data.get("status")
                    status = LiveBPMStatus(**status_data) if status_data is not None else None
                    t = float(row["t"])
                    live_bpm.setdefault(deck, []).append((t, bpm))
                    live_bpm_status.setdefault(deck, []).append((t, status))

        events.sort(key=lambda ev: ev.mono)
        for snaps in positions.values():
            snaps.sort(key=lambda snap: snap.updated_at)
        for samples in live_bpm.values():
            samples.sort(key=lambda sample: sample[0])
        for samples in live_bpm_status.values():
            samples.sort(key=lambda sample: sample[0])
        return cls(events, positions, live_bpm, live_bpm_status)


class ReplayPositionCache:
    def __init__(self, session: CapturedSession) -> None:
        self._session = session
        self.now = 0.0

    def get(self, deck: int) -> Optional[PositionSnapshot]:
        candidate = None
        for snap in self._session.positions.get(deck, []):
            if snap.updated_at <= self.now:
                candidate = snap
            else:
                break
        return candidate


class ReplayLiveBPMService:
    def __init__(self, session: CapturedSession) -> None:
        self._session = session
        self.now = 0.0

    def get_bpm(self, deck: int) -> Optional[float]:
        sample = self._closest(self._session.live_bpm.get(deck, []))
        return None if sample is None else sample[1]

    def get_status(self, deck: int) -> Optional[LiveBPMStatus]:
        sample = self._closest(self._session.live_bpm_status.get(deck, []))
        return None if sample is None else sample[1]

    def _closest(self, samples, *, now: Optional[float] = None):
        if not samples:
            return None
        at = self.now if now is None else now
        return min(samples, key=lambda sample: abs(sample[0] - at))


class ReplayHarness:
    def __init__(self, session: CapturedSession) -> None:
        self.session = session
        self.event_queue: queue.Queue[BridgeEvent] = queue.Queue()
        self.position_cache = ReplayPositionCache(session)
        self.live_bpm = ReplayLiveBPMService(session)

    def tick_iter(self):
        rows: list[tuple[float, str, object]] = []
        rows.extend((ev.mono, "event", ev) for ev in self.session.events)
        for deck, snaps in self.session.positions.items():
            rows.extend((snap.updated_at, "position", (deck, snap)) for snap in snaps)
        for deck, samples in self.session.live_bpm.items():
            rows.extend((t, "live_bpm", (deck, bpm)) for t, bpm in samples)
        rows.sort(key=lambda row: row[0])

        i = 0
        while i < len(rows):
            mono_t = rows[i][0]
            events: list[BridgeEvent] = []
            positions: list[tuple[int, PositionSnapshot]] = []
            live_bpm: list[tuple[int, Optional[float], Optional[LiveBPMStatus]]] = []
            while i < len(rows) and rows[i][0] == mono_t:
                _, kind, value = rows[i]
                if kind == "event":
                    events.append(value)
                elif kind == "position":
                    positions.append(value)
                elif kind == "live_bpm":
                    deck, bpm = value
                    status_sample = self.live_bpm._closest(
                        self.session.live_bpm_status.get(deck, []),
                        now=mono_t,
                    )
                    status = None if status_sample is None else status_sample[1]
                    live_bpm.append((deck, bpm, status))
                i += 1
            yield mono_t, PreTickInputs(events=events, positions=positions, live_bpm=live_bpm)

    def make_state_manager(self, output=None) -> StateManager:
        return StateManager(
            self.event_queue,
            self.position_cache,
            output if output is not None else Mock(),
            live_bpm=self.live_bpm,
            live_bpm_follow=False,
        )
