"""Shadow-mode parity monitor for RBStateReader events.

This module compares direct Rekordbox state-reader events against the
TL-authoritative stream. It never forwards rb_state events to StateManager.
"""
from __future__ import annotations

import logging
import math
import queue
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import BridgeEvent, Ev

log = logging.getLogger("rb_state_shadow")

SHADOW_ENV = "RBSS_RB_STATE_SHADOW"
RB_STATE_SOURCE = "rb_state"
TL_SOURCES = frozenset({"tl_log", "engine_state"})
TL_EDGE_SOURCES = frozenset({"tl_log"})
TL_BPM_SOURCES = frozenset({"engine_state"})
PARITY_KINDS = frozenset({
    Ev.MASTER_CHANGED,
    Ev.TRACK_LOADED,
    Ev.BPM_UPDATE,
    Ev.PLAY,
    Ev.PAUSE,
})

_BPM_EPSILON = 0.10
_PAIR_WINDOW_S = 2.0
_PLAY_MATCH_WINDOW_S = 0.35
_PAUSE_MATCH_WINDOW_S = 1.25
_TRANSPORT_STRONG_MATCH_S = 0.15
_TRANSPORT_MICRO_BURST_S = 1.0
_TRANSPORT_LOAD_ADJACENT_S = 3.0
_BPM_WINDOW_S = 5.0
_BOOTSTRAP_SUPPRESS_S = 3.0
_REPEAT_MISMATCH_LOG_S = 10.0
_MAX_PENDING_PER_KEY = 8
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+")


def bridge_deck_from_rb_index(rb_idx: int) -> int:
    """Map RB's zero-based A/B/C/D index to bridge deck 1/2."""
    return (int(rb_idx) % 2) + 1


def normalize_title(title: object) -> str:
    """Normalize track titles for parity comparison without rewriting payloads."""
    return " ".join(str(title or "").strip().casefold().split())


def titles_match(a: object, b: object) -> bool:
    return normalize_title(a) == normalize_title(b)


def title_is_tl_prefix(tl_title: object, rb_title: object) -> bool:
    tl_norm = normalize_title(tl_title)
    rb_norm = normalize_title(rb_title)
    return bool(tl_norm and rb_norm and tl_norm != rb_norm and rb_norm.startswith(tl_norm))


def bpm_matches(a: object, b: object, *, epsilon: float = _BPM_EPSILON) -> bool:
    try:
        left = float(a)
        right = float(b)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(left) or not math.isfinite(right):
        return False
    return abs(left - right) <= epsilon


def normalize_rb_version(version: str) -> str:
    """Return the short RB version key used by rb_offsets.py, or empty string."""
    m = _VERSION_RE.match(str(version or "").strip())
    return m.group(0) if m else ""


def _event_key(ev: BridgeEvent) -> tuple[str, int]:
    return (ev.kind, int(ev.deck or 0))


def _describe(ev: BridgeEvent) -> str:
    if ev.kind == Ev.TRACK_LOADED:
        return f"title={ev.payload.get('title', '')!r}"
    if ev.kind == Ev.BPM_UPDATE:
        return f"bpm={ev.payload.get('bpm', 0.0)!r}"
    return ""


def compare_events(tl_ev: BridgeEvent, rb_ev: BridgeEvent) -> tuple[bool, str]:
    """Compare a TL-authoritative event with a candidate rb_state event."""
    if tl_ev.kind != rb_ev.kind:
        return False, "event kind differs"
    if int(tl_ev.deck or 0) != int(rb_ev.deck or 0):
        return False, "deck differs"
    if tl_ev.kind == Ev.TRACK_LOADED:
        tl_title = tl_ev.payload.get("title", "")
        rb_title = rb_ev.payload.get("title", "")
        if not tl_title or not rb_title:
            return False, "title missing"
        if not titles_match(tl_title, rb_title):
            if title_is_tl_prefix(tl_title, rb_title):
                return False, "title_truncated_prefix"
            return False, "title differs"
    elif tl_ev.kind == Ev.BPM_UPDATE:
        tl_bpm = tl_ev.payload.get("bpm")
        rb_bpm = rb_ev.payload.get("bpm")
        if not bpm_matches(tl_bpm, rb_bpm):
            try:
                delta = float(rb_bpm) - float(tl_bpm)
                return False, f"BPM delta {delta:+.3f}"
            except (TypeError, ValueError):
                return False, "BPM invalid"
    return True, "match"


def _transport_window(kind: str) -> float:
    if kind == Ev.PLAY:
        return _PLAY_MATCH_WINDOW_S
    if kind == Ev.PAUSE:
        return _PAUSE_MATCH_WINDOW_S
    return _PAIR_WINDOW_S


def classify_transport_pair(tl_ev: BridgeEvent, rb_ev: BridgeEvent) -> tuple[bool, str]:
    """Classify play/pause parity with asymmetric timing expectations."""
    ok, reason = compare_events(tl_ev, rb_ev)
    if not ok:
        return False, reason
    delta_s = rb_ev.mono - tl_ev.mono
    abs_delta_s = abs(delta_s)
    window_s = _transport_window(tl_ev.kind)
    if abs_delta_s > window_s:
        return False, f"outside {tl_ev.kind} window"
    if abs_delta_s <= _TRANSPORT_STRONG_MATCH_S:
        return True, "strong match"
    if tl_ev.kind == Ev.PAUSE and delta_s < 0:
        return True, "expected TL-lag pause match"
    return True, "late / weak match"


@dataclass
class _PendingEvent:
    ev: BridgeEvent
    observed_mono: float
    scope: str = "normal"
    load_adjacent: bool = False


class RBStateParityMonitor(threading.Thread):
    """Daemon thread that pairs TL and rb_state events for shadow validation."""

    def __init__(
        self,
        rb_queue: queue.Queue[BridgeEvent],
        *,
        clock=time.monotonic,
        pair_window_s: float = _PAIR_WINDOW_S,
        bpm_window_s: float = _BPM_WINDOW_S,
        bootstrap_s: float = _BOOTSTRAP_SUPPRESS_S,
    ) -> None:
        super().__init__(name="rb-state-parity", daemon=True)
        self._rb_queue = rb_queue
        self._tl_queue: queue.Queue[BridgeEvent] = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._clock = clock
        self._pair_window_s = pair_window_s
        self._bpm_window_s = bpm_window_s
        self._bootstrap_s = bootstrap_s
        self._started_mono = clock()
        self._pending_tl: dict[tuple[str, int], list[_PendingEvent]] = {}
        self._pending_rb: dict[tuple[str, int], list[_PendingEvent]] = {}
        self._last_mismatch_log: dict[tuple[str, int, str], float] = {}
        self._last_rb_bpm: dict[int, _PendingEvent] = {}
        self._last_master_summary: dict[int, float] = {}
        self._last_tl_track_load_mono: dict[int, float] = {}
        self._last_transport_event_mono: dict[tuple[str, int], float] = {}
        self._last_transport_outcome_mono: dict[int, float] = {}
        self._stats: Counter[str] = Counter()
        self._summary_logged = False

    def observe_tl(self, ev: BridgeEvent) -> None:
        """Cheap enqueue tap for authoritative events."""
        if ev.kind not in PARITY_KINDS or ev.source not in TL_SOURCES:
            return
        try:
            self._tl_queue.put_nowait(ev)
        except queue.Full:
            log.warning("[rb_state_shadow] TL parity queue full; dropping kind=%s deck=%s",
                        ev.kind, ev.deck)

    def stop(self) -> None:
        self._stop.set()
        self.log_summary()

    def run(self) -> None:
        log.info("[rb_state_shadow] parity monitor started "
                 "master=edge-only bpm=value-window bootstrap_s=%.1f",
                 self._bootstrap_s)
        while not self._stop.is_set():
            did_work = False
            did_work = self._drain_queue(self._tl_queue, is_tl=True) or did_work
            did_work = self._drain_queue(self._rb_queue, is_tl=False) or did_work
            self._expire_old()
            if not did_work:
                time.sleep(0.02)

    def _drain_queue(self, q: queue.Queue[BridgeEvent], *, is_tl: bool) -> bool:
        did_work = False
        while True:
            try:
                ev = q.get_nowait()
            except queue.Empty:
                return did_work
            did_work = True
            if ev.kind not in PARITY_KINDS:
                continue
            if is_tl:
                self._accept_tl(ev)
            elif ev.source == RB_STATE_SOURCE:
                self._accept_rb(ev)

    def _accept_tl(self, ev: BridgeEvent) -> None:
        if ev.kind == Ev.MASTER_CHANGED and ev.source not in TL_EDGE_SOURCES:
            self._accept_master_summary(ev)
            return
        if ev.kind == Ev.BPM_UPDATE:
            self._accept_tl_bpm(ev)
            return
        if ev.kind in (Ev.PLAY, Ev.PAUSE):
            self._accept_transport_tl(ev)
            return
        if ev.kind == Ev.TRACK_LOADED:
            self._last_tl_track_load_mono[int(ev.deck or 0)] = ev.mono
        key = _event_key(ev)
        match = self._pop_candidate(self._pending_rb, key)
        if match is None:
            match = self._pop_kind_candidate(self._pending_rb, ev.kind)
        if match is None:
            self._remember(self._pending_tl, key, ev)
            return
        self._log_pair(ev, match.ev)

    def _accept_rb(self, ev: BridgeEvent) -> None:
        if ev.kind == Ev.BPM_UPDATE:
            self._last_rb_bpm[int(ev.deck or 0)] = _PendingEvent(
                ev=ev,
                observed_mono=self._clock(),
            )
            return
        if ev.kind in (Ev.PLAY, Ev.PAUSE):
            self._accept_transport_rb(ev)
            return
        key = _event_key(ev)
        match = self._pop_candidate(self._pending_tl, key)
        if match is None:
            match = self._pop_kind_candidate(self._pending_tl, ev.kind)
        if match is None:
            self._remember(self._pending_rb, key, ev)
            return
        self._log_pair(match.ev, ev)

    def _accept_transport_tl(self, ev: BridgeEvent) -> None:
        key = _event_key(ev)
        match = self._pop_transport_candidate(self._pending_rb, ev)
        if match is None:
            self._remember(self._pending_tl, key, ev, side="tl")
            return
        self._log_transport_pair(
            ev,
            match.ev,
            scope=self._transport_event_scope(ev, "tl"),
            load_adjacent=self._is_load_adjacent(ev),
        )

    def _accept_transport_rb(self, ev: BridgeEvent) -> None:
        key = _event_key(ev)
        match = self._pop_transport_candidate(self._pending_tl, ev)
        if match is None:
            self._remember(self._pending_rb, key, ev, side="rb")
            return
        self._log_transport_pair(
            match.ev,
            ev,
            scope=match.scope,
            load_adjacent=match.load_adjacent,
        )

    def _accept_master_summary(self, ev: BridgeEvent) -> None:
        deck = int(ev.deck or 0)
        prev = self._last_master_summary.get(deck, 0.0)
        now = self._clock()
        self._last_master_summary[deck] = now
        self._record(ev.kind, "summary")
        if not prev:
            log.info("[rb_state_shadow][summary] kind=%s deck=%s source=%s mono=%.6f",
                     ev.kind, ev.deck, ev.source, ev.mono)

    def _accept_tl_bpm(self, ev: BridgeEvent) -> None:
        if ev.source not in TL_BPM_SOURCES:
            return
        deck = int(ev.deck or 0)
        rb = self._last_rb_bpm.get(deck)
        if rb is None:
            self._record(ev.kind, "summary_no_recent_rb")
            log.info("[rb_state_shadow][bpm-summary] deck=%s tl_mono=%.6f "
                     "tl_source=%s bpm=%r reason=no recent rb_state bpm",
                     ev.deck, ev.mono, ev.source, ev.payload.get("bpm"))
            return
        age_s = self._clock() - rb.observed_mono
        if age_s > self._bpm_window_s:
            self._record(ev.kind, "summary_outside_window")
            log.info("[rb_state_shadow][bpm-summary] deck=%s tl_mono=%.6f "
                     "rb_mono=%.6f age_ms=%.1f tl_source=%s rb_source=%s "
                     "tl_bpm=%r rb_bpm=%r reason=rb_state bpm outside window",
                     ev.deck, ev.mono, rb.ev.mono, age_s * 1000.0,
                     ev.source, rb.ev.source, ev.payload.get("bpm"),
                     rb.ev.payload.get("bpm"))
            return
        ok, reason = compare_events(ev, rb.ev)
        delta_ms = (rb.ev.mono - ev.mono) * 1000.0
        level = log.info if ok else log.warning
        tag = "agree" if ok else "mismatch"
        self._record(ev.kind, tag)
        level("[rb_state_shadow][bpm-%s] deck=%s tl_mono=%.6f rb_mono=%.6f "
              "delta_ms=%+.1f age_ms=%.1f tl_source=%s rb_source=%s "
              "tl_bpm=%r rb_bpm=%r reason=%s",
              tag, ev.deck, ev.mono, rb.ev.mono, delta_ms, age_s * 1000.0,
              ev.source, rb.ev.source, ev.payload.get("bpm"),
              rb.ev.payload.get("bpm"), reason)

    def _remember(
        self,
        pending: dict[tuple[str, int], list[_PendingEvent]],
        key: tuple[str, int],
        ev: BridgeEvent,
        *,
        side: Optional[str] = None,
    ) -> None:
        scope = (
            self._transport_event_scope(ev, side)
            if side and ev.kind in (Ev.PLAY, Ev.PAUSE)
            else "normal"
        )
        load_adjacent = self._is_load_adjacent(ev) if ev.kind in (Ev.PLAY, Ev.PAUSE) else False
        items = pending.setdefault(key, [])
        items.append(_PendingEvent(
            ev=ev,
            observed_mono=self._clock(),
            scope=scope,
            load_adjacent=load_adjacent,
        ))
        del items[:-_MAX_PENDING_PER_KEY]
        if len(items) > 1:
            self._log_mismatch(
                ev,
                None,
                "duplicate or ordering: no counterpart yet",
                transport_scope=scope,
                load_adjacent=load_adjacent,
            )

    def _pop_candidate(
        self,
        pending: dict[tuple[str, int], list[_PendingEvent]],
        key: tuple[str, int],
    ) -> Optional[_PendingEvent]:
        items = pending.get(key)
        if not items:
            return None
        item = items.pop(0)
        if not items:
            pending.pop(key, None)
        return item

    def _pop_transport_candidate(
        self,
        pending: dict[tuple[str, int], list[_PendingEvent]],
        ev: BridgeEvent,
    ) -> Optional[_PendingEvent]:
        key = _event_key(ev)
        items = pending.get(key)
        if not items:
            return None
        window_s = _transport_window(ev.kind)
        for idx, item in enumerate(items):
            if abs(item.ev.mono - ev.mono) <= window_s:
                out = items.pop(idx)
                if not items:
                    pending.pop(key, None)
                return out
        return None

    def _pop_kind_candidate(
        self,
        pending: dict[tuple[str, int], list[_PendingEvent]],
        kind: str,
    ) -> Optional[_PendingEvent]:
        for key in sorted(pending):
            if key[0] == kind and pending[key]:
                return self._pop_candidate(pending, key)
        return None

    def _expire_old(self) -> None:
        now = self._clock()
        for pending, side in ((self._pending_tl, "missing rb_state pair"),
                              (self._pending_rb, "missing TL pair")):
            for key in list(pending):
                keep = []
                for item in pending[key]:
                    if now - item.observed_mono > self._pair_window_s:
                        self._log_mismatch(
                            item.ev,
                            None,
                            side,
                            transport_scope=item.scope,
                            load_adjacent=item.load_adjacent,
                        )
                    else:
                        keep.append(item)
                if keep:
                    pending[key] = keep
                else:
                    pending.pop(key, None)

    def _log_pair(self, tl_ev: BridgeEvent, rb_ev: BridgeEvent) -> None:
        ok, reason = compare_events(tl_ev, rb_ev)
        delta_ms = (rb_ev.mono - tl_ev.mono) * 1000.0
        fields = (
            "kind=%s deck=%s tl_mono=%.6f rb_mono=%.6f delta_ms=%+.1f "
            "tl_source=%s rb_source=%s %s %s"
        )
        if ok:
            self._record(tl_ev.kind, "agree")
            log.info("[rb_state_shadow][agree] " + fields,
                     tl_ev.kind, tl_ev.deck, tl_ev.mono, rb_ev.mono, delta_ms,
                     tl_ev.source, rb_ev.source, _describe(tl_ev), _describe(rb_ev))
            return
        self._log_mismatch(tl_ev, rb_ev, reason)

    def _log_transport_pair(
        self,
        tl_ev: BridgeEvent,
        rb_ev: BridgeEvent,
        *,
        scope: Optional[str] = None,
        load_adjacent: Optional[bool] = None,
    ) -> None:
        ok, classification = classify_transport_pair(tl_ev, rb_ev)
        delta_ms = (rb_ev.mono - tl_ev.mono) * 1000.0
        if ok:
            self._record_transport(
                tl_ev,
                _transport_outcome(classification, ok),
                scope=scope,
                load_adjacent=load_adjacent,
            )
            log.info("[rb_state_shadow][transport-%s] kind=%s deck=%s "
                     "tl_mono=%.6f rb_mono=%.6f delta_ms=%+.1f "
                     "tl_source=%s rb_source=%s",
                     classification.replace(" ", "-").replace("/", ""),
                     tl_ev.kind, tl_ev.deck, tl_ev.mono, rb_ev.mono, delta_ms,
                     tl_ev.source, rb_ev.source)
            return
        self._log_mismatch(tl_ev, rb_ev, classification)

    def _log_mismatch(
        self,
        primary: BridgeEvent,
        other: Optional[BridgeEvent],
        reason: str,
        *,
        transport_scope: Optional[str] = None,
        load_adjacent: Optional[bool] = None,
    ) -> None:
        now = self._clock()
        if now - self._started_mono < self._bootstrap_s:
            log.debug("[rb_state_shadow][bootstrap-suppressed] kind=%s deck=%s "
                      "source=%s reason=%s",
                      primary.kind, primary.deck, primary.source, reason)
            return
        sig = (primary.kind, int(primary.deck or 0), reason)
        last = self._last_mismatch_log.get(sig, 0.0)
        if last and now - last < _REPEAT_MISMATCH_LOG_S:
            return
        self._last_mismatch_log[sig] = now
        if primary.kind in (Ev.PLAY, Ev.PAUSE):
            self._record_transport(
                primary,
                _mismatch_outcome(reason),
                scope=transport_scope,
                load_adjacent=load_adjacent,
            )
        else:
            self._record(primary.kind, _mismatch_outcome(reason))
        if other is None:
            log.warning("[rb_state_shadow][mismatch] kind=%s deck=%s source=%s "
                        "mono=%.6f reason=%s %s",
                        primary.kind, primary.deck, primary.source, primary.mono,
                        reason, _describe(primary))
            return
        delta_ms = (other.mono - primary.mono) * 1000.0
        log.warning("[rb_state_shadow][mismatch] kind=%s deck=%s tl_mono=%.6f "
                    "rb_mono=%.6f delta_ms=%+.1f tl_source=%s rb_source=%s "
                    "reason=%s tl_%s rb_%s",
                    primary.kind, primary.deck, primary.mono, other.mono, delta_ms,
                    primary.source, other.source, reason, _describe(primary),
                    _describe(other))

    def _record(self, kind: str, outcome: str) -> None:
        self._stats[f"{kind}.{outcome}"] += 1

    def _record_transport(
        self,
        ev: BridgeEvent,
        outcome: str,
        *,
        scope: Optional[str] = None,
        load_adjacent: Optional[bool] = None,
    ) -> None:
        if scope is None:
            scope = self._transport_outcome_scope(ev)
        self._stats[f"{ev.kind}.{outcome}.{scope}"] += 1
        if load_adjacent is None:
            load_adjacent = self._is_load_adjacent(ev)
        load_key = "load_adjacent_true" if load_adjacent else "load_adjacent_false"
        self._stats[f"{ev.kind}.{outcome}.{scope}.{load_key}"] += 1

    def _transport_outcome_scope(self, ev: BridgeEvent) -> str:
        deck = int(ev.deck or 0)
        prev = self._last_transport_outcome_mono.get(deck)
        self._last_transport_outcome_mono[deck] = ev.mono
        if prev is not None and 0.0 <= ev.mono - prev <= _TRANSPORT_MICRO_BURST_S:
            return "micro_burst"
        return "normal"

    def _transport_event_scope(self, ev: BridgeEvent, side: str) -> str:
        key = (side, int(ev.deck or 0))
        prev = self._last_transport_event_mono.get(key)
        self._last_transport_event_mono[key] = ev.mono
        if prev is not None and 0.0 <= ev.mono - prev <= _TRANSPORT_MICRO_BURST_S:
            return "micro_burst"
        return "normal"

    def _is_load_adjacent(self, ev: BridgeEvent) -> bool:
        last_load = self._last_tl_track_load_mono.get(int(ev.deck or 0))
        return last_load is not None and 0.0 <= ev.mono - last_load <= _TRANSPORT_LOAD_ADJACENT_S

    def summary_lines(self) -> list[str]:
        """Return compact session summary lines for logs and tests."""
        def count(key: str) -> int:
            return int(self._stats.get(key, 0))

        lines = ["[rb_state_shadow][session-summary]"]
        lines.append(
            "track_loaded agree=%d title_truncated_prefix=%d mismatch=%d"
            % (
                count(f"{Ev.TRACK_LOADED}.agree"),
                count(f"{Ev.TRACK_LOADED}.title_truncated_prefix"),
                count(f"{Ev.TRACK_LOADED}.mismatch"),
            )
        )
        lines.append(
            "master_changed agree=%d mismatch=%d summary=%d"
            % (
                count(f"{Ev.MASTER_CHANGED}.agree"),
                count(f"{Ev.MASTER_CHANGED}.mismatch"),
                count(f"{Ev.MASTER_CHANGED}.summary"),
            )
        )
        lines.append(
            "bpm_update agree=%d mismatch=%d summary_no_recent_rb=%d "
            "summary_outside_window=%d"
            % (
                count(f"{Ev.BPM_UPDATE}.agree"),
                count(f"{Ev.BPM_UPDATE}.mismatch"),
                count(f"{Ev.BPM_UPDATE}.summary_no_recent_rb"),
                count(f"{Ev.BPM_UPDATE}.summary_outside_window"),
            )
        )
        for kind in (Ev.PLAY, Ev.PAUSE):
            parts = [kind]
            outcomes = (
                "strong_match",
                "weak_late_match",
                "expected_tl_lag_pause_match",
                "missing_pair",
                "duplicate_ordering",
                "outside_window",
                "mismatch",
            )
            for scope in ("normal", "micro_burst"):
                scoped = [
                    "%s=%d" % (outcome, count(f"{kind}.{outcome}.{scope}"))
                    for outcome in outcomes
                ]
                parts.append("%s{%s}" % (scope, " ".join(scoped)))
            lines.append(" ".join(parts))
            for load_adjacent, label in (
                ("load_adjacent_false", "load_adjacent=false"),
                ("load_adjacent_true", "load_adjacent=true"),
            ):
                parts = [kind, label]
                for scope in ("normal", "micro_burst"):
                    scoped = [
                        "%s=%d" % (
                            outcome,
                            count(f"{kind}.{outcome}.{scope}.{load_adjacent}"),
                        )
                        for outcome in outcomes
                    ]
                    parts.append("%s{%s}" % (scope, " ".join(scoped)))
                lines.append(" ".join(parts))
        return lines

    def log_summary(self) -> None:
        if self._summary_logged:
            return
        self._summary_logged = True
        for line in self.summary_lines():
            log.info(line)


def _transport_outcome(classification: str, ok: bool) -> str:
    if ok and classification == "strong match":
        return "strong_match"
    if ok and classification == "late / weak match":
        return "weak_late_match"
    if ok and classification == "expected TL-lag pause match":
        return "expected_tl_lag_pause_match"
    if classification.startswith("outside "):
        return "outside_window"
    return "mismatch"


def _mismatch_outcome(reason: str) -> str:
    if reason == "title_truncated_prefix":
        return "title_truncated_prefix"
    if reason.startswith("duplicate or ordering"):
        return "duplicate_ordering"
    if reason.startswith("missing "):
        return "missing_pair"
    if reason.startswith("outside "):
        return "outside_window"
    return "mismatch"


def read_rekordbox_version(app_paths: tuple[Path, ...] | None = None) -> str:
    """Read and normalize Rekordbox's CFBundleShortVersionString."""
    import plistlib

    paths = app_paths or (
        Path("/Applications/rekordbox 7/rekordbox.app"),
        Path("/Applications/rekordbox 6/rekordbox.app"),
        Path("/Applications/rekordbox/rekordbox.app"),
    )
    for app_path in paths:
        info_path = app_path / "Contents" / "Info.plist"
        try:
            with open(info_path, "rb") as fh:
                info = plistlib.load(fh)
        except OSError:
            continue
        raw = str(
            info.get("CFBundleShortVersionString")
            or info.get("CFBundleVersion")
            or ""
        )
        version = normalize_rb_version(raw)
        if version:
            return version
    return ""
