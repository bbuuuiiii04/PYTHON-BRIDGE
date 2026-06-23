"""Offline replay helpers for recorded StateManager input sessions."""
from __future__ import annotations

import json
import queue
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import Mock
from unittest.mock import patch

from .live_bpm import LiveBPMStatus
from .models import BridgeEvent, PositionSnapshot
from .state_manager import StateManager


@dataclass(frozen=True)
class PreTickInputs:
    events: list[BridgeEvent] = field(default_factory=list)
    positions: list[tuple[int, PositionSnapshot]] = field(default_factory=list)
    live_bpm: list[tuple[int, Optional[float], Optional[LiveBPMStatus]]] = field(default_factory=list)


@dataclass(frozen=True)
class ReplayRunResult:
    state_manager: StateManager
    ticks: int
    start_mono: float
    end_mono: float


@dataclass
class CapturedSession:
    events: list[BridgeEvent]
    positions: dict[int, list[PositionSnapshot]]
    live_bpm: dict[int, list[tuple[float, Optional[float]]]]
    live_bpm_status: dict[int, list[tuple[float, Optional[LiveBPMStatus]]]] = field(default_factory=dict)
    # schema-2 evidence-only autoloop phase rows (empty for schema-1 sessions)
    autoloop_phase: list[dict] = field(default_factory=list)

    # Session schemas this replayer can parse. Schema 1 is the historical
    # event/position/live_bpm format; schema 2 additionally carries
    # autoloop_phase rows and is byte-compatible for the schema-1 row kinds.
    SUPPORTED_SCHEMAS = (1, 2)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "CapturedSession":
        events: list[BridgeEvent] = []
        positions: dict[int, list[PositionSnapshot]] = {}
        live_bpm: dict[int, list[tuple[float, Optional[float]]]] = {}
        live_bpm_status: dict[int, list[tuple[float, Optional[LiveBPMStatus]]]] = {}
        autoloop_phase: list[dict] = []

        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                kind = row.get("kind")
                if kind == "header":
                    if row.get("schema") not in cls.SUPPORTED_SCHEMAS:
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
                elif kind == "autoloop_phase":
                    autoloop_phase.append(row)

        autoloop_phase.sort(key=lambda r: r.get("mono_ns", 0))
        events.sort(key=lambda ev: ev.mono)
        for snaps in positions.values():
            snaps.sort(key=lambda snap: snap.updated_at)
        for samples in live_bpm.values():
            samples.sort(key=lambda sample: sample[0])
        for samples in live_bpm_status.values():
            samples.sort(key=lambda sample: sample[0])
        return cls(events, positions, live_bpm, live_bpm_status, autoloop_phase)


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

    def run_for(
        self,
        *,
        seconds: float,
        state_manager: Optional[StateManager] = None,
        output=None,
    ) -> ReplayRunResult:
        """Replay captured inputs through StateManager ticks for a fixed span.

        The replay clock is synthetic so recorded positions are not treated as
        stale, but profiler timings use perf_counter so real CPU regressions are
        still visible to performance tests.
        """
        if seconds <= 0:
            raise ValueError("seconds must be positive")

        sm = state_manager if state_manager is not None else self.make_state_manager(output=output)
        start = self._start_mono()
        end = start + float(seconds)
        interval = sm._TICK_INTERVAL
        self.position_cache.now = start
        self.live_bpm.now = start
        sm._next_snapshot_publish_at = start

        events = sorted(self.session.events, key=lambda ev: ev.mono)
        event_index = 0
        tick = 0
        mono_t = start
        while mono_t < end:
            while event_index < len(events) and events[event_index].mono <= mono_t:
                self.event_queue.put_nowait(events[event_index])
                event_index += 1

            self.position_cache.now = mono_t
            self.live_bpm.now = mono_t
            self._run_one_tick(sm, mono_t)
            tick += 1
            mono_t = start + tick * interval

        return ReplayRunResult(
            state_manager=sm,
            ticks=tick,
            start_mono=start,
            end_mono=min(mono_t, end),
        )

    def _run_one_tick(self, sm: StateManager, mono_t: float) -> None:
        profiler = sm._profiler
        with patch("rb_ss_bridge_v2.state_manager.time.monotonic", return_value=mono_t):
            if profiler is None:
                sm._drain_events()
                sm._push_tick()
                sm._maybe_publish_snapshot(mono_t)
                return

            queue_depth = sm._queue_depth()
            t0 = time.perf_counter()
            sm._drain_events()
            t1 = time.perf_counter()
            sm._push_tick()
            t2 = time.perf_counter()
            did_publish = sm._maybe_publish_snapshot(mono_t)
            t3 = time.perf_counter()

        elapsed_s = t3 - t0
        profiler.record(
            tick_ms=elapsed_s * 1000.0,
            drain_ms=(t1 - t0) * 1000.0,
            push_ms=(t2 - t1) * 1000.0,
            snapshot_ms=((t3 - t2) * 1000.0 if did_publish else None),
            overrun_ms=max(0.0, (elapsed_s - sm._TICK_INTERVAL) * 1000.0),
            queue_depth=queue_depth,
        )

    def _start_mono(self) -> float:
        candidates: list[float] = []
        candidates.extend(ev.mono for ev in self.session.events)
        for snaps in self.session.positions.values():
            candidates.extend(snap.updated_at for snap in snaps)
        for samples in self.session.live_bpm.values():
            candidates.extend(t for t, _ in samples)
        return min(candidates) if candidates else 0.0
