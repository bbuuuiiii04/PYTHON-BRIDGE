"""Runtime live-BPM discovery and readout.

The service is deliberately fail-closed: it never publishes a BPM until a
candidate has moved during the current rekordbox pid/base session and landed
near the current ENGINE STATE hint.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Iterable, Optional, Protocol

from .probe_live_bpm import (
    Hit,
    _base_from_vmmap,
    _collect_hits,
    _dedupe_hits,
    _get_vmmap_output,
    _read_float,
    _resolve_anchors,
    _results_from_samples,
    _select_validation_hits,
    _task_for_pid,
)
from .rb_memory import get_rb_pid

log = logging.getLogger("live_bpm")

LIVE_BPM_DISABLE_ENV = "RBSS_LIVE_BPM_DISABLE"
LIVE_BPM_MIN = 40.0
LIVE_BPM_MAX = 250.0
LIVE_BPM_VALIDATE_DELTA = 0.05
LIVE_BPM_VALIDATE_TOLERANCE = 0.25
LIVE_BPM_VALIDATE_HZ = 5.0
LIVE_BPM_VALIDATE_MAX_S = 45.0
LIVE_BPM_SCAN_RETRY_S = 10.0
LIVE_BPM_SESSION_CHECK_S = 5.0
LIVE_BPM_READ_FAILURES = 3
LIVE_BPM_STALE_S = 3.0
LIVE_BPM_LOG_DELTA = 0.02
LIVE_BPM_LOG_INTERVAL_S = 1.0


@dataclass(frozen=True)
class LiveBPMSession:
    pid: int
    base: int
    task: int
    vmmap_out: str = ""


@dataclass(frozen=True)
class LiveBPMCandidate:
    addr: int
    type_name: str
    region: str = ""
    nearest_anchor: str = ""
    anchor_delta: int = 0

    @property
    def key(self) -> tuple[int, str]:
        return (self.addr, self.type_name)


@dataclass
class LiveBPMReading:
    deck: int
    bpm: float
    pid: int
    base: int
    addr: int
    type_name: str
    updated_at: float

    def is_stale(self, threshold_s: float = LIVE_BPM_STALE_S) -> bool:
        return time.monotonic() - self.updated_at > threshold_s


@dataclass(frozen=True)
class LiveBPMStatus:
    deck: int
    bpm: float
    pid: int
    base: int
    addr: int
    type_name: str
    updated_at: float
    valid: bool


class LiveBPMReader(Protocol):
    def attach(self) -> Optional[LiveBPMSession]:
        ...

    def scan_candidates(
        self,
        session: LiveBPMSession,
        deck: int,
        expect_bpm: float,
        library_bpm: float,
        limit: int,
    ) -> list[LiveBPMCandidate]:
        ...

    def read_candidate(self, session: LiveBPMSession, candidate: LiveBPMCandidate) -> float:
        ...


class MachLiveBPMReader:
    """Read-only Mach-backed candidate scanner/reader."""

    def attach(self) -> Optional[LiveBPMSession]:
        pid = get_rb_pid()
        if pid is None:
            return None
        vmmap_out = _get_vmmap_output(pid)
        base = _base_from_vmmap(vmmap_out)
        task = _task_for_pid(pid)
        return LiveBPMSession(pid=pid, base=base, task=task, vmmap_out=vmmap_out)

    def scan_candidates(
        self,
        session: LiveBPMSession,
        deck: int,
        expect_bpm: float,
        library_bpm: float,
        limit: int,
    ) -> list[LiveBPMCandidate]:
        anchors = _resolve_anchors(session.task, session.base, deck, 0x10000, deck == 2)
        args = SimpleNamespace(
            window=0x10000,
            include_objc_regions=False,
            include_rw_regions=False,
            max_objc_region=0x400000,
            max_rw_region=0x400000,
            max_rw_total=0x2000000,
            expect_bpm=expect_bpm,
            library_bpm=library_bpm if library_bpm > 0 else None,
            bpm_min=LIVE_BPM_MIN,
            bpm_max=LIVE_BPM_MAX,
            factor_min=0.80,
            factor_max=1.20,
            mode="bpm",
            max_hits_per_region=12,
        )
        hits = _select_validation_hits(
            _dedupe_hits(_collect_hits(session.task, session.vmmap_out, anchors, args)),
            limit,
        )
        return [_candidate_from_hit(hit) for hit in hits]

    def read_candidate(self, session: LiveBPMSession, candidate: LiveBPMCandidate) -> float:
        return _read_float(session.task, candidate.addr, candidate.type_name)


@dataclass
class _Validated:
    candidate: LiveBPMCandidate
    latest_bpm: float
    updated_at: float
    failure_count: int = 0
    last_logged_bpm: float = 0.0
    last_logged_at: float = 0.0


@dataclass
class _DeckDiscovery:
    hint_bpm: float = 0.0
    library_bpm: float = 0.0
    hint_updated_at: float = 0.0
    candidates: list[LiveBPMCandidate] = field(default_factory=list)
    values: dict[tuple[int, str], list[float]] = field(default_factory=dict)
    timestamps: dict[tuple[int, str], list[float]] = field(default_factory=dict)
    sample_start_at: float = 0.0
    sample_start_hint: float = 0.0
    next_sample_at: float = 0.0
    last_scan_at: float = 0.0
    validated: Optional[_Validated] = None


def _candidate_from_hit(hit: Hit) -> LiveBPMCandidate:
    return LiveBPMCandidate(
        addr=hit.addr,
        type_name=hit.type_name,
        region=hit.region,
        nearest_anchor=hit.nearest_anchor,
        anchor_delta=hit.anchor_delta,
    )


def _hit_from_candidate(candidate: LiveBPMCandidate) -> Hit:
    return Hit(
        addr=candidate.addr,
        type_name=candidate.type_name,
        value=0.0,
        role="bpm",
        score=0.0,
        region=candidate.region,
        nearest_anchor=candidate.nearest_anchor,
        anchor_delta=candidate.anchor_delta,
    )


def _valid_bpm(value: float) -> bool:
    return math.isfinite(value) and LIVE_BPM_MIN <= value <= LIVE_BPM_MAX


class LiveBPMService(threading.Thread):
    """Background live BPM discovery.

    ENGINE STATE BPM is a hint only. A candidate is promoted only after its
    observed memory value moves in this process session and finishes near the
    latest hint. Static matches remain unvalidated and are never returned.
    """

    def __init__(
        self,
        reader: Optional[LiveBPMReader] = None,
        disabled: Optional[bool] = None,
        poll_interval: float = 0.2,
        scan_limit: int = 24,
    ) -> None:
        super().__init__(name="live-bpm-service", daemon=True)
        self.disabled = (
            os.environ.get(LIVE_BPM_DISABLE_ENV) == "1" if disabled is None else disabled
        )
        self._reader = reader or MachLiveBPMReader()
        self._poll_interval = poll_interval
        self._scan_limit = scan_limit
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._session: Optional[LiveBPMSession] = None
        self._last_session_check_at = 0.0
        self._deck: dict[int, _DeckDiscovery] = {1: _DeckDiscovery(), 2: _DeckDiscovery()}

    def stop(self) -> None:
        self._stop_event.set()

    def update_hint(self, deck: int, bpm: float, library_bpm: float = 0.0) -> None:
        if self.disabled or deck not in self._deck or not _valid_bpm(float(bpm)):
            return
        with self._lock:
            state = self._deck[deck]
            state.hint_bpm = float(bpm)
            if _valid_bpm(float(library_bpm)):
                state.library_bpm = float(library_bpm)
            elif state.library_bpm <= 0:
                state.library_bpm = float(bpm)
            state.hint_updated_at = time.monotonic()

    def get_bpm(self, deck: int) -> Optional[float]:
        if self.disabled or deck not in self._deck:
            return None
        with self._lock:
            session = self._session
            state = self._deck[deck]
            validated = state.validated
            if not self._is_current_validated(session, validated):
                return None
            assert validated is not None
            return validated.latest_bpm

    def get_status(self, deck: int) -> Optional[LiveBPMStatus]:
        if self.disabled or deck not in self._deck:
            return None
        with self._lock:
            session = self._session
            state = self._deck[deck]
            validated = state.validated
            if not self._is_current_validated(session, validated):
                return None
            assert session is not None and validated is not None
            return LiveBPMStatus(
                deck=deck,
                bpm=validated.latest_bpm,
                pid=session.pid,
                base=session.base,
                addr=validated.candidate.addr,
                type_name=validated.candidate.type_name,
                updated_at=validated.updated_at,
                valid=True,
            )

    def invalidate(self) -> None:
        with self._lock:
            self._session = None
            for state in self._deck.values():
                self._reset_discovery(state)
                state.validated = None

    def run(self) -> None:
        if self.disabled:
            log.info("[LBPM][INVALID] disabled by %s=1", LIVE_BPM_DISABLE_ENV)
            return
        log.info("[LBPM][SCAN] starting")
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                log.warning("[LBPM][ERROR] tick failed: %s", exc)
            time.sleep(self._poll_interval)

    def tick(self) -> None:
        if self.disabled:
            return
        session = self._ensure_session()
        if session is None:
            return
        for deck in (1, 2):
            self._tick_deck(session, deck, time.monotonic())

    def _ensure_session(self) -> Optional[LiveBPMSession]:
        with self._lock:
            current = self._session
        if current is not None:
            try:
                os.kill(current.pid, 0)
            except (OSError, ProcessLookupError):
                log.info("[LBPM][INVALID] rekordbox pid %d gone; invalidating candidates", current.pid)
                self.invalidate()
                current = None
            else:
                now = time.monotonic()
                if now - self._last_session_check_at < LIVE_BPM_SESSION_CHECK_S:
                    return current
                self._last_session_check_at = now
                pid = get_rb_pid()
                if pid == current.pid:
                    return current
                log.info(
                    "[LBPM][INVALID] rekordbox pid changed %s -> %s; invalidating candidates",
                    current.pid,
                    pid if pid is not None else "none",
                )
                self.invalidate()
                current = None
        attached = self._reader.attach()
        self._last_session_check_at = time.monotonic()
        if attached is None:
            if current is not None:
                log.info("[LBPM][INVALID] rekordbox unavailable; invalidating candidates")
                self.invalidate()
            return None
        if current is None or attached.pid != current.pid or attached.base != current.base:
            log.info("[LBPM][ATTACH] attached pid=%d base=0x%x", attached.pid, attached.base)
            with self._lock:
                self._session = attached
                for state in self._deck.values():
                    self._reset_discovery(state)
                    state.validated = None
        else:
            with self._lock:
                self._session = attached
        return attached

    def _tick_deck(self, session: LiveBPMSession, deck: int, now: float) -> None:
        with self._lock:
            state = self._deck[deck]
            hint = state.hint_bpm
            library_bpm = state.library_bpm
            validated = state.validated

        if validated is not None:
            self._refresh_validated(session, deck, validated)
            return

        if not _valid_bpm(hint):
            return

        with self._lock:
            state = self._deck[deck]
            if not state.candidates and now - state.last_scan_at >= LIVE_BPM_SCAN_RETRY_S:
                state.last_scan_at = now
                scan_needed = True
            else:
                scan_needed = False

        if scan_needed:
            candidates = self._reader.scan_candidates(
                session, deck, hint, library_bpm, self._scan_limit
            )
            candidates = list(_dedupe_candidates(candidates))
            with self._lock:
                state = self._deck[deck]
                state.candidates = candidates
                state.values = {candidate.key: [] for candidate in candidates}
                state.timestamps = {candidate.key: [] for candidate in candidates}
                state.sample_start_at = now
                state.sample_start_hint = hint
                state.next_sample_at = now
            if candidates:
                log.info("[LBPM][SCAN] deck%d watching %d BPM candidate(s)", deck, len(candidates))
            return

        self._sample_and_maybe_validate(session, deck, now)

    def _refresh_validated(
        self,
        session: LiveBPMSession,
        deck: int,
        validated: _Validated,
    ) -> None:
        try:
            value = self._reader.read_candidate(session, validated.candidate)
        except OSError:
            value = float("nan")
        now = time.monotonic()
        with self._lock:
            state = self._deck[deck]
            current = state.validated
            if current is None:
                return
            if _valid_bpm(value):
                previous = current.latest_bpm
                current.latest_bpm = float(value)
                current.updated_at = now
                current.failure_count = 0
                should_log = (
                    abs(current.latest_bpm - current.last_logged_bpm) >= LIVE_BPM_LOG_DELTA
                    and now - current.last_logged_at >= LIVE_BPM_LOG_INTERVAL_S
                )
                if should_log:
                    log.info(
                        "[LBPM][CURRENT] deck%d current=%.3f previous=%.3f "
                        "delta=%+.3f addr=0x%x type=%s",
                        deck,
                        current.latest_bpm,
                        previous,
                        current.latest_bpm - previous,
                        current.candidate.addr,
                        current.candidate.type_name,
                    )
                    current.last_logged_bpm = current.latest_bpm
                    current.last_logged_at = now
            else:
                current.failure_count += 1
                if current.failure_count >= LIVE_BPM_READ_FAILURES:
                    log.warning("[LBPM][INVALID] deck%d invalidated after read failures", deck)
                    state.validated = None
                    self._reset_discovery(state)

    def _sample_and_maybe_validate(self, session: LiveBPMSession, deck: int, now: float) -> None:
        with self._lock:
            state = self._deck[deck]
            candidates = list(state.candidates)
            if not candidates or now < state.next_sample_at:
                return
            hint = state.hint_bpm
            sample_start_hint = state.sample_start_hint
            sample_start_at = state.sample_start_at
            state.next_sample_at = now + (1.0 / LIVE_BPM_VALIDATE_HZ)

        for candidate in candidates:
            try:
                value = self._reader.read_candidate(session, candidate)
            except OSError:
                continue
            if not _valid_bpm(value):
                continue
            with self._lock:
                state = self._deck[deck]
                if candidate.key in state.values:
                    state.values[candidate.key].append(float(value))
                    state.timestamps[candidate.key].append(now - sample_start_at)

        moved_hint = abs(hint - sample_start_hint) >= LIVE_BPM_VALIDATE_DELTA
        expired = now - sample_start_at >= LIVE_BPM_VALIDATE_MAX_S
        if not moved_hint and not expired:
            return

        with self._lock:
            state = self._deck[deck]
            hits = [_hit_from_candidate(candidate) for candidate in state.candidates]
            values = {key: list(val) for key, val in state.values.items()}
            timestamps = {key: list(val) for key, val in state.timestamps.items()}

        results = _results_from_samples(
            hits,
            values,
            timestamps,
            hint if moved_hint else None,
            LIVE_BPM_VALIDATE_TOLERANCE,
            LIVE_BPM_VALIDATE_DELTA,
        )
        passed = [result for result in results if result.verdict == "pass"]
        with self._lock:
            state = self._deck[deck]
            if passed:
                winner = passed[0]
                candidate = LiveBPMCandidate(
                    addr=winner.hit.addr,
                    type_name=winner.hit.type_name,
                    region=winner.hit.region,
                    nearest_anchor=winner.hit.nearest_anchor,
                    anchor_delta=winner.hit.anchor_delta,
                )
                now = time.monotonic()
                state.validated = _Validated(
                    candidate,
                    winner.end,
                    now,
                    last_logged_bpm=winner.end,
                    last_logged_at=now,
                )
                self._reset_discovery(state, keep_validated=True)
                log.info(
                    "[LBPM][VALIDATED] deck%d addr=0x%x type=%s bpm=%.3f",
                    deck,
                    candidate.addr,
                    candidate.type_name,
                    winner.end,
                )
            else:
                self._reset_discovery(state, keep_validated=True)

    def _reset_discovery(self, state: _DeckDiscovery, keep_validated: bool = False) -> None:
        state.candidates = []
        state.values = {}
        state.timestamps = {}
        state.sample_start_at = 0.0
        state.sample_start_hint = state.hint_bpm
        state.next_sample_at = 0.0
        state.last_scan_at = 0.0
        if not keep_validated:
            state.validated = None

    def _is_current_validated(
        self,
        session: Optional[LiveBPMSession],
        validated: Optional[_Validated],
    ) -> bool:
        if session is None or validated is None:
            return False
        if validated.updated_at <= 0 or time.monotonic() - validated.updated_at > LIVE_BPM_STALE_S:
            return False
        return _valid_bpm(validated.latest_bpm)


def _dedupe_candidates(candidates: Iterable[LiveBPMCandidate]) -> Iterable[LiveBPMCandidate]:
    seen: set[tuple[int, str]] = set()
    for candidate in candidates:
        if candidate.key in seen:
            continue
        seen.add(candidate.key)
        yield candidate
