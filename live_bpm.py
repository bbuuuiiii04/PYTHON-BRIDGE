"""Runtime live-BPM discovery and readout.

The service is deliberately fail-closed: discovery candidates are not
published until they move in the current rekordbox pid/base session. Fixed
offset-table candidates are published only when the running Rekordbox version
is supported and the direct chain reads a fresh, plausible BPM.
"""
from __future__ import annotations

import logging
import math
import os
import plistlib
import re
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Optional, Protocol

from .config import RB_DECK1_OFF, RB_DECK2_OFF, RB_GLOBAL_OFF, RB_INNER_OFF, RB_SEC_OFF
from .rb_memory import (
    _base_from_vmmap,
    _get_vmmap_output,
    _objc_regions_from_vmmap,
    _read_bytes,
    _read_u64,
    _scan_objc_zone,
    _task_for_pid,
    get_rb_pid,
)
from .rb_offsets import ChainEntry, RBOffsetVersion, load_offsets_for_version
from . import bridge_log

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
LIVE_BPM_LOG_DELTA = 0.10
LIVE_BPM_LOG_INTERVAL_S = 1.0
LIVE_BPM_DIRECT_SOURCE = "offset_table"
LIVE_BPM_DISCOVERY_SOURCE = "discovery"
LIVE_BPM_FALLBACK_SOURCE = "fallback_meta"
LIVE_BPM_DIAGNOSTICS_ENV = "RBSS_LIVE_BPM_DIAGNOSTICS"

# Memory-scan discovery primitives. probe_live_bpm.py's CLI imports these back
# from here; they live here because the always-running BPM service is what
# actually depends on them.
_ADDR_RE = re.compile(r"\b([0-9a-fA-F]+)-([0-9a-fA-F]+)\b")


@dataclass(frozen=True)
class Region:
    start: int
    size: int
    label: str

    @property
    def end(self) -> int:
        return self.start + self.size


@dataclass(frozen=True)
class Anchor:
    name: str
    addr: int


@dataclass(frozen=True)
class Hit:
    addr: int
    type_name: str
    value: float
    role: str
    score: float
    region: str
    nearest_anchor: str
    anchor_delta: int


@dataclass(frozen=True)
class WatchResult:
    hit: Hit
    samples: int
    start: float
    end: float
    minimum: float
    maximum: float
    max_delta: float
    verdict: str
    started_at_zero: bool = False
    ended_at_zero: bool = False
    num_discontinuities: int = 0
    timestamps: tuple[float, ...] = ()
    values: tuple[float, ...] = ()


def _safe_read_u64(task: int, addr: int) -> int | None:
    try:
        return _read_u64(task, addr)
    except OSError:
        return None


def _nearest_anchor(addr: int, anchors: list[Anchor]) -> tuple[str, int]:
    if not anchors:
        return "<none>", 0
    anchor = min(anchors, key=lambda a: abs(addr - a.addr))
    return anchor.name, addr - anchor.addr


def _rw_regions_from_vmmap(
    vmmap_out: str,
    max_region_size: int,
    max_total_size: int,
) -> list[Region]:
    """Return bounded readable/writable regions from vmmap output.

    The cap keeps broad scans interactive. Regions are listed in vmmap order so
    anchor-adjacent malloc/nano pages tend to be scanned before large tail areas.
    """
    regions: list[Region] = []
    total = 0
    for line in vmmap_out.splitlines():
        if "rw-" not in line:
            continue
        m = _ADDR_RE.search(line)
        if not m:
            continue
        start = int(m.group(1), 16)
        end = int(m.group(2), 16)
        size = end - start
        if size < 0x100 or size > max_region_size:
            continue
        if total + size > max_total_size:
            break
        label = line.split()[0] if line.split() else "rw_region"
        regions.append(Region(start, size, f"vmmap:{label}"))
        total += size
    return regions


def _readable_window_regions(
    task: int,
    anchors: list[Anchor],
    window: int,
    extra_regions: list[Region],
) -> list[Region]:
    regions: list[Region] = []
    seen: set[tuple[int, int]] = set()

    for anchor in anchors:
        if anchor.addr <= 0:
            continue
        start = max(0, anchor.addr - window)
        size = window * 2
        key = (start, size)
        if key in seen:
            continue
        seen.add(key)
        try:
            _read_bytes(task, start, min(size, 16))
        except OSError:
            continue
        regions.append(Region(start, size, f"{anchor.name} +/-0x{window:x}"))

    for region in extra_regions:
        key = (region.start, region.size)
        if key not in seen:
            regions.append(region)
            seen.add(key)

    return regions


def _score_value(
    value: float,
    expect_bpm: float | None,
    library_bpm: float | None,
    bpm_min: float,
    bpm_max: float,
    factor_min: float,
    factor_max: float,
    mode: str,
) -> tuple[str, float] | None:
    if not math.isfinite(value):
        return None

    best: tuple[str, float] | None = None
    if mode != "factor" and bpm_min <= value <= bpm_max:
        score = 0.0 if expect_bpm is None else abs(value - expect_bpm)
        best = ("bpm", score)

    if mode != "bpm" and factor_min <= value <= factor_max:
        factor_score = 0.0
        if expect_bpm is not None and library_bpm and library_bpm > 0:
            factor_score = abs((library_bpm * value) - expect_bpm) / max(library_bpm, 1.0)
        if best is None or factor_score < best[1]:
            best = ("factor", factor_score)

    return best


def _scan_region(
    task: int,
    region: Region,
    anchors: list[Anchor],
    expect_bpm: float | None,
    library_bpm: float | None,
    bpm_min: float,
    bpm_max: float,
    factor_min: float,
    factor_max: float,
    mode: str,
    max_hits_per_region: int,
) -> list[Hit]:
    try:
        chunk = _read_bytes(task, region.start, region.size)
    except OSError:
        return []

    hits: list[Hit] = []
    for i in range(0, max(0, len(chunk) - 8), 4):
        addr = region.start + i
        f32 = struct.unpack_from("<f", chunk, i)[0]
        scored = _score_value(f32, expect_bpm, library_bpm, bpm_min, bpm_max, factor_min, factor_max, mode)
        if scored is not None:
            role, score = scored
            name, delta = _nearest_anchor(addr, anchors)
            hits.append(Hit(addr, "f32", f32, role, score, region.label, name, delta))

        if i % 8 == 0:
            f64 = struct.unpack_from("<d", chunk, i)[0]
            scored = _score_value(f64, expect_bpm, library_bpm, bpm_min, bpm_max, factor_min, factor_max, mode)
            if scored is not None:
                role, score = scored
                name, delta = _nearest_anchor(addr, anchors)
                hits.append(Hit(addr, "f64", f64, role, score, region.label, name, delta))

    hits.sort(key=lambda h: (h.score, 0 if h.role == "bpm" else 1, abs(h.anchor_delta)))
    return hits[:max_hits_per_region]


def _read_float(task: int, addr: int, type_name: str) -> float:
    if type_name == "f32":
        return struct.unpack("<f", _read_bytes(task, addr, 4))[0]
    if type_name == "f64":
        return struct.unpack("<d", _read_bytes(task, addr, 8))[0]
    raise ValueError(f"unsupported float type: {type_name}")


def _resolve_anchors(
    task: int,
    base: int,
    deck: int,
    objc_window: int,
    include_deck2_scan: bool,
) -> list[Anchor]:
    anchors: list[Anchor] = [Anchor("base", base)]
    container = _safe_read_u64(task, base + RB_GLOBAL_OFF)
    if container:
        anchors.append(Anchor("container", container))
        dpu1 = _safe_read_u64(task, container + RB_DECK1_OFF)
        dpu2 = _safe_read_u64(task, container + RB_DECK2_OFF)
        if dpu1:
            anchors.append(Anchor("dpu1", dpu1))
            inner1 = _safe_read_u64(task, dpu1 + RB_INNER_OFF)
            if inner1:
                anchors.append(Anchor("inner1", inner1))
                sec1 = _safe_read_u64(task, inner1 + RB_SEC_OFF)
                if sec1:
                    anchors.append(Anchor("secondary1", sec1))
                if deck == 2 and include_deck2_scan:
                    for idx, inner2 in enumerate(_scan_objc_zone(task, inner1, window=objc_window), start=1):
                        if inner2 != inner1:
                            anchors.append(Anchor(f"deck2_zone_candidate{idx}", inner2))
                            sec2 = _safe_read_u64(task, inner2 + RB_SEC_OFF)
                            if sec2:
                                anchors.append(Anchor(f"secondary2_candidate{idx}", sec2))
                            break
        if dpu2:
            anchors.append(Anchor("container_dpu2_slot", dpu2))
            inner2_slot = _safe_read_u64(task, dpu2 + RB_INNER_OFF)
            if inner2_slot:
                anchors.append(Anchor("container_dpu2_inner", inner2_slot))

    if deck == 1:
        return [a for a in anchors if not a.name.startswith(("deck2_", "secondary2_", "container_dpu2"))]
    return anchors


def _extra_regions_from_args(vmmap_out: str, args) -> list[Region]:
    extra_regions: list[Region] = []
    if getattr(args, "include_objc_regions", False):
        for idx, (start, size) in enumerate(_objc_regions_from_vmmap(vmmap_out), start=1):
            if size <= args.max_objc_region:
                extra_regions.append(Region(start, size, f"objc_region{idx}"))
    if getattr(args, "include_rw_regions", False):
        extra_regions.extend(
            _rw_regions_from_vmmap(vmmap_out, args.max_rw_region, args.max_rw_total)
        )
    return extra_regions


def _collect_hits(task: int, vmmap_out: str, anchors: list[Anchor], args) -> list[Hit]:
    extra_regions = _extra_regions_from_args(vmmap_out, args)
    regions = _readable_window_regions(task, anchors, args.window, extra_regions)
    all_hits: list[Hit] = []
    for region in regions:
        all_hits.extend(
            _scan_region(
                task,
                region,
                anchors,
                args.expect_bpm,
                args.library_bpm,
                args.bpm_min,
                args.bpm_max,
                args.factor_min,
                args.factor_max,
                args.mode,
                args.max_hits_per_region,
            )
        )

    all_hits.sort(key=lambda h: (h.score, 0 if h.role == "bpm" else 1, h.region, abs(h.anchor_delta)))
    return all_hits


def _dedupe_hits(hits: Iterable[Hit]) -> list[Hit]:
    out: list[Hit] = []
    seen: set[tuple[int, str]] = set()
    for hit in hits:
        key = (hit.addr, hit.type_name)
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out


def _validation_rank(hit: Hit) -> tuple[float, int, float, float]:
    label = hit.region.lower()
    penalty = 0.0
    if "malloc_tiny" in label or "malloc_small" in label or "malloc_large" in label:
        penalty -= 0.25
    if "+/-" in label:
        penalty -= 0.10
    if (
        "ioaccelerator" in label
        or "coreanimation" in label
        or "skywalk" in label
        or "__auth_const" in label
        or "__data_const" in label
        or "mapped" in label
    ):
        penalty += 5.0
    type_rank = 0 if hit.type_name == "f32" else 1
    return (hit.score + penalty, type_rank, abs(hit.anchor_delta), hit.addr)


def _select_validation_hits(hits: list[Hit], limit: int) -> list[Hit]:
    ranked = sorted(hits, key=_validation_rank)
    selected: list[Hit] = []
    seen_addr: set[tuple[int, str]] = set()
    region_counts: dict[str, int] = {}
    max_per_region = max(2, min(6, limit // 3 or 2))

    for hit in ranked:
        key = (hit.addr, hit.type_name)
        if key in seen_addr:
            continue
        if region_counts.get(hit.region, 0) >= max_per_region:
            continue
        selected.append(hit)
        seen_addr.add(key)
        region_counts[hit.region] = region_counts.get(hit.region, 0) + 1
        if len(selected) >= limit:
            return selected

    for hit in ranked:
        key = (hit.addr, hit.type_name)
        if key in seen_addr:
            continue
        selected.append(hit)
        seen_addr.add(key)
        if len(selected) >= limit:
            break
    return selected


def _is_zeroish(value: float, tolerance: float = 1e-6) -> bool:
    return math.isfinite(value) and abs(value) <= tolerance


def _verdict_for_samples(
    values: list[float],
    expected_after: float | None,
    tolerance: float,
    min_delta: float,
) -> str:
    if not values:
        return "read_error"
    max_delta = max(values) - min(values)
    if max_delta < min_delta:
        return "stale"
    if _is_zeroish(values[0]) and any(not _is_zeroish(value) for value in values[1:]):
        return "zero_start_churn"
    if _is_zeroish(values[-1]) and any(not _is_zeroish(value) for value in values[:-1]):
        return "zero_end_decay"
    if expected_after is None:
        return "moved_unverified"
    if abs(values[-1] - expected_after) <= tolerance:
        return "pass"
    return "moved_wrong_value"


def _count_discontinuities(values: list[float], threshold: float = 1.0) -> int:
    return sum(
        1
        for before, after in zip(values, values[1:])
        if abs(after - before) > threshold
    )


def _results_from_samples(
    hits: list[Hit],
    values_by_hit: dict[tuple[int, str], list[float]],
    timestamps_by_hit: dict[tuple[int, str], list[float]],
    expected_after: float | None,
    tolerance: float,
    min_delta: float,
) -> list[WatchResult]:
    results: list[WatchResult] = []
    for hit in hits:
        key = (hit.addr, hit.type_name)
        values = values_by_hit.get(key, [])
        verdict = _verdict_for_samples(values, expected_after, tolerance, min_delta)
        if values:
            start = values[0]
            end = values[-1]
            minimum = min(values)
            maximum = max(values)
            max_delta = maximum - minimum
            started_at_zero = _is_zeroish(start)
            ended_at_zero = _is_zeroish(end)
            num_discontinuities = _count_discontinuities(values)
        else:
            start = end = minimum = maximum = max_delta = float("nan")
            started_at_zero = ended_at_zero = False
            num_discontinuities = 0
        results.append(
            WatchResult(
                hit,
                len(values),
                start,
                end,
                minimum,
                maximum,
                max_delta,
                verdict,
                started_at_zero,
                ended_at_zero,
                num_discontinuities,
                tuple(timestamps_by_hit.get(key, [])),
                tuple(values),
            )
        )

    verdict_order = {
        "pass": 0,
        "moved_unverified": 1,
        "moved_wrong_value": 2,
        "zero_start_churn": 3,
        "zero_end_decay": 4,
        "stale": 5,
        "read_error": 6,
    }
    results.sort(
        key=lambda r: (
            verdict_order.get(r.verdict, 99),
            r.hit.score,
            0 if r.hit.type_name == "f32" else 1,
            -r.max_delta if math.isfinite(r.max_delta) else 0.0,
            abs(r.hit.anchor_delta),
        )
    )
    return results


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
    source: str = LIVE_BPM_DISCOVERY_SOURCE

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
    source: str
    updated_at: float
    valid: bool


@dataclass(frozen=True)
class LiveBPMDeckSummary:
    deck: int
    current_source: str
    first_source: str
    direct_accepted_count: int
    direct_rejected_count: int
    fallback_count: int
    last_accepted_bpm: float
    direct_before_hint: bool


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

    def __init__(
        self,
        *,
        rb_version: Optional[str] = None,
        app_paths: tuple[Path, ...] | None = None,
    ) -> None:
        self._rb_version = rb_version
        self._app_paths = app_paths
        self._offsets: Optional[RBOffsetVersion] = None
        self._offsets_loaded = False
        self._direct_log_seen: set[tuple[int, int, int, str]] = set()

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
        direct = self.direct_candidate(session, deck)
        if direct is not None:
            return [direct]

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

    def direct_candidate(
        self,
        session: LiveBPMSession,
        deck: int,
    ) -> Optional[LiveBPMCandidate]:
        candidate, reason = self._offset_candidate(session, deck)
        if candidate is not None:
            return candidate
        self._log_direct_fallback(session, deck, reason)
        return None

    def _offset_candidate(
        self,
        session: LiveBPMSession,
        deck: int,
    ) -> tuple[Optional[LiveBPMCandidate], str]:
        offsets = self._load_offsets()
        if offsets is None or not 1 <= deck <= min(2, offsets.deck_count):
            return None, "unsupported_version"
        ch = offsets.bpm_per_deck[deck - 1]
        addr = _follow_addr(session.task, session.base, ch)
        if addr is None:
            return None, "chain_unreadable"
        try:
            value = _read_float(session.task, addr, "f32")
        except OSError:
            return None, "value_unreadable"
        if not _valid_bpm(value):
            return None, "invalid_value"
        return (
            LiveBPMCandidate(
                addr=addr,
                type_name="f32",
                region=LIVE_BPM_DIRECT_SOURCE,
                nearest_anchor=f"rb_offsets:{offsets.version}:deck{deck}",
                anchor_delta=0,
                source=LIVE_BPM_DIRECT_SOURCE,
            ),
            "available",
        )

    def _load_offsets(self) -> Optional[RBOffsetVersion]:
        if self._offsets_loaded:
            return self._offsets
        self._offsets_loaded = True
        version = self._rb_version if self._rb_version is not None else read_rekordbox_version(self._app_paths)
        if not version:
            log.info("[LBPM][DIRECT] Rekordbox version lookup failed; using discovery fallback")
            self._offsets = None
            return None
        self._offsets = load_offsets_for_version(version)
        if self._offsets is None:
            log.info("[LBPM][DIRECT] unsupported Rekordbox version %s; using discovery fallback", version)
        else:
            log.info("[LBPM][DIRECT] offset-table BPM enabled version=%s", self._offsets.version)
        return self._offsets

    def _log_direct_fallback(
        self,
        session: LiveBPMSession,
        deck: int,
        reason: str,
    ) -> None:
        key = (session.pid, session.base, deck, reason)
        if key in self._direct_log_seen:
            return
        self._direct_log_seen.add(key)
        log.info("[LBPM][DIRECT] deck%d unavailable reason=%s fallback=discovery", deck, reason)


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
    # Epoch counters used to drop stale scan/validation commits.
    # These must not affect validation semantics; they only prevent committing work
    # computed under an older session/discovery snapshot.
    hint_epoch: int = 0
    discovery_gen: int = 0
    validation_epoch_id: int = 0
    candidates_session_gen: int = 0
    candidates_hint_epoch: int = 0
    # Measurement-only fields (do not affect behavior).
    first_valid_hint_at: float = 0.0
    first_valid_hint_epoch: int = 0
    sample_moved_hint_at: float = 0.0
    sample_hint_epoch_start: int = 0
    candidates: list[LiveBPMCandidate] = field(default_factory=list)
    values: dict[tuple[int, str], list[float]] = field(default_factory=dict)
    timestamps: dict[tuple[int, str], list[float]] = field(default_factory=dict)
    sample_start_at: float = 0.0
    sample_start_hint: float = 0.0
    next_sample_at: float = 0.0
    last_scan_at: float = 0.0
    validated: Optional[_Validated] = None
    current_source: str = ""
    first_source: str = ""
    direct_accepted_count: int = 0
    direct_rejected_count: int = 0
    fallback_count: int = 0
    last_accepted_bpm: float = 0.0
    direct_before_hint: bool = False
    summary_logged: bool = False


def _candidate_from_hit(hit: Hit) -> LiveBPMCandidate:
    return LiveBPMCandidate(
        addr=hit.addr,
        type_name=hit.type_name,
        region=hit.region,
        nearest_anchor=hit.nearest_anchor,
        anchor_delta=hit.anchor_delta,
        source=LIVE_BPM_DISCOVERY_SOURCE,
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


def _follow_addr(task: int, base: int, ch: ChainEntry) -> Optional[int]:
    addr = base
    for hop in ch.hops:
        try:
            ptr_bytes = _read_bytes(task, addr + hop, 8)
        except OSError:
            return None
        addr = struct.unpack_from("<Q", ptr_bytes)[0]
        if addr == 0:
            return None
    return addr + ch.final_off


def read_rekordbox_version(app_paths: tuple[Path, ...] | None = None) -> str:
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
        version = _normalize_rb_version(raw)
        if version:
            return version
    return ""


def _normalize_rb_version(version: str) -> str:
    parts = str(version or "").strip().split(".")
    if len(parts) < 3:
        return ""
    short = ".".join(parts[:3])
    if all(part.isdigit() for part in short.split(".")):
        return short
    return ""


class LiveBPMService(threading.Thread):
    """Background live BPM discovery.

    ENGINE STATE BPM is a hint only. Offset-table candidates are promoted after
    a supported-version chain read succeeds. Discovery candidates are promoted
    only after their observed memory value moves in this process session and
    finishes near the latest hint; static discovery matches remain unvalidated.
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
        self._diagnostics = os.environ.get(LIVE_BPM_DIAGNOSTICS_ENV) == "1"
        self._reader = reader or MachLiveBPMReader()
        self._poll_interval = poll_interval
        self._scan_limit = scan_limit
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._session: Optional[LiveBPMSession] = None
        # Monotonically increasing session generation. Incremented whenever the
        # attached pid/base session is invalidated or replaced. Used to prevent
        # stale scan/validation work (performed outside the lock) from committing.
        self._session_gen: int = 0
        # Measurement-only counters.
        self._drop_scan_total: int = 0
        self._drop_validate_total: int = 0
        self._drop_reason_counts: dict[str, int] = {}
        self._direct_attempt_log_seen: set[tuple[int, int, int]] = set()
        self._direct_reject_log_seen: set[tuple[int, int, int, str]] = set()
        self._last_session_check_at = 0.0
        self._deck: dict[int, _DeckDiscovery] = {1: _DeckDiscovery(), 2: _DeckDiscovery()}

    def stop(self) -> None:
        self._stop_event.set()
        if self._diagnostics:
            self.log_summary()

    def update_hint(self, deck: int, bpm: float, library_bpm: float = 0.0) -> None:
        if self.disabled or deck not in self._deck or not _valid_bpm(float(bpm)):
            return
        with self._lock:
            state = self._deck[deck]
            state.hint_epoch += 1
            state.hint_bpm = float(bpm)
            if state.first_valid_hint_at <= 0.0:
                state.first_valid_hint_at = time.monotonic()
                state.first_valid_hint_epoch = state.hint_epoch
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
                source=validated.candidate.source,
                updated_at=validated.updated_at,
                valid=True,
            )

    def get_summary(self, deck: int) -> Optional[LiveBPMDeckSummary]:
        if self.disabled or deck not in self._deck:
            return None
        with self._lock:
            state = self._deck[deck]
            source = state.current_source or LIVE_BPM_FALLBACK_SOURCE
            return LiveBPMDeckSummary(
                deck=deck,
                current_source=source,
                first_source=state.first_source,
                direct_accepted_count=state.direct_accepted_count,
                direct_rejected_count=state.direct_rejected_count,
                fallback_count=state.fallback_count,
                last_accepted_bpm=state.last_accepted_bpm,
                direct_before_hint=state.direct_before_hint,
            )

    def invalidate(self) -> None:
        with self._lock:
            self._session_gen += 1
            self._session = None
            for deck, state in self._deck.items():
                self._reset_discovery(state)
                state.validated = None
                self._set_source_locked(deck, state, LIVE_BPM_FALLBACK_SOURCE, "invalidate")

    def run(self) -> None:
        if self.disabled:
            log.info("[LBPM][INVALID] disabled by %s=1", LIVE_BPM_DISABLE_ENV)
            return
        log.info("[LBPM][SCAN] starting")
        with bridge_log.thread_guard("live-bpm-service"):
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

    def log_summary(self) -> None:
        for line in self.summary_lines():
            log.info(line)

    def summary_lines(self) -> list[str]:
        out: list[str] = []
        with self._lock:
            items = [
                (deck, state.current_source or LIVE_BPM_FALLBACK_SOURCE, state.first_source,
                 state.direct_accepted_count, state.direct_rejected_count, state.fallback_count,
                 state.last_accepted_bpm, state.direct_before_hint)
                for deck, state in sorted(self._deck.items())
            ]
        for deck, source, first, direct_ok, direct_reject, fallback_count, last_bpm, before_hint in items:
            out.append(
                "[LBPM][SUMMARY] deck%d source=%s first_source=%s direct_ok=%d "
                "direct_reject=%d fallback=%d last_bpm=%.3f direct_before_hint=%s"
                % (
                    deck,
                    source,
                    first or "<none>",
                    direct_ok,
                    direct_reject,
                    fallback_count,
                    last_bpm,
                    "1" if before_hint else "0",
                )
            )
        return out

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
        # attach() may run vmmap and take seconds; measure wall time outside lock.
        self._last_session_check_at = time.monotonic()
        if attached is None:
            if current is not None:
                log.info("[LBPM][INVALID] rekordbox unavailable; invalidating candidates")
                self.invalidate()
            return None
        if current is None or attached.pid != current.pid or attached.base != current.base:
            log.info("[LBPM][ATTACH] attached pid=%d base=0x%x", attached.pid, attached.base)
            with self._lock:
                self._session_gen += 1
                self._session = attached
                for deck, state in self._deck.items():
                    self._reset_discovery(state)
                    state.validated = None
                    self._set_source_locked(deck, state, LIVE_BPM_FALLBACK_SOURCE, "attach")
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
            session_gen = self._session_gen
            discovery_gen = state.discovery_gen

        if validated is not None:
            self._refresh_validated(session, deck, validated)
            return

        if self._try_direct_candidate(session, deck, session_gen, discovery_gen, now):
            return

        if not _valid_bpm(hint):
            with self._lock:
                state = self._deck[deck]
                self._set_source_locked(deck, state, LIVE_BPM_FALLBACK_SOURCE, "no_hint")
            return

        with self._lock:
            state = self._deck[deck]
            if not state.candidates and now - state.last_scan_at >= LIVE_BPM_SCAN_RETRY_S:
                state.last_scan_at = now
                scan_needed = True
            else:
                scan_needed = False

        if scan_needed:
            t_scan0 = time.monotonic()
            candidates = self._reader.scan_candidates(
                session, deck, hint, library_bpm, self._scan_limit
            )
            scan_ms = (time.monotonic() - t_scan0) * 1000.0
            candidates = list(_dedupe_candidates(candidates))
            direct_candidate = _first_direct_candidate(candidates)
            if direct_candidate is not None:
                self._promote_direct_candidate(
                    session,
                    deck,
                    direct_candidate,
                    session_gen,
                    discovery_gen,
                    scan_ms,
                )
                return
            with self._lock:
                state = self._deck[deck]
                current_session = self._session
                if (
                    current_session is None
                    or current_session.pid != session.pid
                    or current_session.base != session.base
                    or self._session_gen != session_gen
                ):
                    self._drop_scan_total += 1
                    self._drop_reason_counts["scan_session_gen_mismatch"] = (
                        self._drop_reason_counts.get("scan_session_gen_mismatch", 0) + 1
                    )
                    cur_pid = current_session.pid if current_session else 0
                    cur_base = current_session.base if current_session else 0
                    log.info(
                        "[LBPM][DROP] deck%d drop_scan reason=session_gen_mismatch "
                        "scan(pid=%d base=0x%x gen=%d) cur(pid=%d base=0x%x gen=%d)",
                        deck,
                        session.pid,
                        session.base,
                        session_gen,
                        cur_pid,
                        cur_base,
                        self._session_gen,
                    )
                    return
                if state.discovery_gen != discovery_gen:
                    self._drop_scan_total += 1
                    self._drop_reason_counts["scan_discovery_gen_mismatch"] = (
                        self._drop_reason_counts.get("scan_discovery_gen_mismatch", 0) + 1
                    )
                    log.info(
                        "[LBPM][DROP] deck%d drop_scan reason=discovery_gen_mismatch "
                        "scan_gen=%d cur_gen=%d",
                        deck,
                        discovery_gen,
                        state.discovery_gen,
                    )
                    return
                if state.validated is not None:
                    self._drop_scan_total += 1
                    self._drop_reason_counts["scan_already_validated"] = (
                        self._drop_reason_counts.get("scan_already_validated", 0) + 1
                    )
                    log.info("[LBPM][DROP] deck%d drop_scan reason=already_validated", deck)
                    return
                if state.candidates:
                    self._drop_scan_total += 1
                    self._drop_reason_counts["scan_candidates_already_installed"] = (
                        self._drop_reason_counts.get("scan_candidates_already_installed", 0) + 1
                    )
                    log.info("[LBPM][DROP] deck%d drop_scan reason=candidates_already_installed", deck)
                    return

                state.discovery_gen += 1
                state.validation_epoch_id += 1
                state.candidates_session_gen = session_gen
                state.candidates_hint_epoch = state.hint_epoch
                state.sample_moved_hint_at = 0.0
                state.sample_hint_epoch_start = state.hint_epoch
                state.candidates = candidates
                state.values = {candidate.key: [] for candidate in candidates}
                state.timestamps = {candidate.key: [] for candidate in candidates}
                state.sample_start_at = now
                state.sample_start_hint = hint
                state.next_sample_at = now
            if candidates:
                log.info(
                    "[LBPM][SCAN] deck%d watching=%d scan_ms=%.1f drops_scan=%d drops_validate=%d",
                    deck,
                    len(candidates),
                    scan_ms,
                    self._drop_scan_total,
                    self._drop_validate_total,
                )
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
                    abs(current.latest_bpm - current.last_logged_bpm) > LIVE_BPM_LOG_DELTA
                    and now - current.last_logged_at >= LIVE_BPM_LOG_INTERVAL_S
                )
                if should_log:
                    log.info(
                        "[LBPM][CURRENT] deck%d current=%.3f previous=%.3f "
                        "delta=%+.3f addr=0x%x type=%s source=%s",
                        deck,
                        current.latest_bpm,
                        previous,
                        current.latest_bpm - previous,
                        current.candidate.addr,
                        current.candidate.type_name,
                        current.candidate.source,
                    )
                    current.last_logged_bpm = current.latest_bpm
                    current.last_logged_at = now
            else:
                current.failure_count += 1
                if current.failure_count >= LIVE_BPM_READ_FAILURES:
                    log.warning("[LBPM][INVALID] deck%d invalidated after read failures", deck)
                    state.validated = None
                    self._reset_discovery(state)
                    self._set_source_locked(deck, state, LIVE_BPM_FALLBACK_SOURCE, "read_failures")

    def _try_direct_candidate(
        self,
        session: LiveBPMSession,
        deck: int,
        session_gen: int,
        discovery_gen: int,
        now: float,
    ) -> bool:
        direct_reader = getattr(self._reader, "direct_candidate", None)
        if direct_reader is None:
            return False
        attempt_key = (session.pid, session.base, deck)
        if attempt_key not in self._direct_attempt_log_seen:
            self._direct_attempt_log_seen.add(attempt_key)
            log.info("[LBPM][DIRECT] deck%d first_read_attempt=1 source=%s", deck, LIVE_BPM_DIRECT_SOURCE)
        try:
            candidate = direct_reader(session, deck)
        except Exception:
            log.debug("direct live BPM candidate read failed", exc_info=True)
            return False
        if candidate is None:
            return False
        return self._promote_direct_candidate(
            session,
            deck,
            candidate,
            session_gen,
            discovery_gen,
            (time.monotonic() - now) * 1000.0,
        )

    def _promote_direct_candidate(
        self,
        session: LiveBPMSession,
        deck: int,
        candidate: LiveBPMCandidate,
        session_gen: int,
        discovery_gen: int,
        scan_ms: float,
    ) -> bool:
        try:
            value = self._reader.read_candidate(session, candidate)
        except OSError:
            self._log_direct_reject(session, deck, "value_unreadable")
            return False
        if not _valid_bpm(value):
            self._log_direct_reject(session, deck, "invalid_value")
            return False
        now = time.monotonic()
        with self._lock:
            state = self._deck[deck]
            current_session = self._session
            if (
                current_session is None
                or current_session.pid != session.pid
                or current_session.base != session.base
                or self._session_gen != session_gen
            ):
                self._drop_scan_total += 1
                self._drop_reason_counts["direct_session_gen_mismatch"] = (
                    self._drop_reason_counts.get("direct_session_gen_mismatch", 0) + 1
                )
                return False
            if state.discovery_gen != discovery_gen:
                self._drop_scan_total += 1
                self._drop_reason_counts["direct_discovery_gen_mismatch"] = (
                    self._drop_reason_counts.get("direct_discovery_gen_mismatch", 0) + 1
                )
                return False
            if state.validated is not None:
                return True
            state.validated = _Validated(
                candidate,
                float(value),
                now,
                last_logged_bpm=float(value),
                last_logged_at=now,
            )
            self._reset_discovery(state, keep_validated=True)
            state.direct_accepted_count += 1
            state.last_accepted_bpm = float(value)
            if not _valid_bpm(state.hint_bpm):
                state.direct_before_hint = True
            self._set_source_locked(deck, state, LIVE_BPM_DIRECT_SOURCE, "direct_accept", value)
            ttfv_ms = 0.0
            if state.first_valid_hint_at > 0.0:
                ttfv_ms = (now - state.first_valid_hint_at) * 1000.0
        log.info(
            "[LBPM][DIRECT] deck%d addr=0x%x bpm=%.3f version_anchor=%s "
            "direct_ms=%.1f ttfv_ms=%.0f accepted=1",
            deck,
            candidate.addr,
            value,
            candidate.nearest_anchor or "<none>",
            scan_ms,
            ttfv_ms,
        )
        return True

    def _log_direct_reject(self, session: LiveBPMSession, deck: int, reason: str) -> None:
        with self._lock:
            state = self._deck.get(deck)
            if state is not None:
                state.direct_rejected_count += 1
                self._set_source_locked(deck, state, LIVE_BPM_FALLBACK_SOURCE, f"direct_reject:{reason}")
        key = (session.pid, session.base, deck, reason)
        if key in self._direct_reject_log_seen:
            return
        self._direct_reject_log_seen.add(key)
        log.info("[LBPM][DIRECT] deck%d rejected reason=%s fallback=discovery", deck, reason)

    def _set_source_locked(
        self,
        deck: int,
        state: _DeckDiscovery,
        source: str,
        reason: str,
        bpm: float = 0.0,
    ) -> None:
        previous = state.current_source
        if not state.first_source and source != LIVE_BPM_FALLBACK_SOURCE:
            state.first_source = source
        if source == LIVE_BPM_FALLBACK_SOURCE and previous != LIVE_BPM_FALLBACK_SOURCE:
            state.fallback_count += 1
        if previous == source:
            return
        state.current_source = source
        log.info(
            "[LBPM][SOURCE] deck%d source=%s previous=%s reason=%s bpm=%.3f "
            "first_source=%s direct_before_hint=%s",
            deck,
            source,
            previous or "<none>",
            reason,
            bpm,
            state.first_source or "<none>",
            "1" if state.direct_before_hint else "0",
        )
        if self._diagnostics and source != LIVE_BPM_FALLBACK_SOURCE and not state.summary_logged:
            state.summary_logged = True
            log.info(
                "[LBPM][SUMMARY] deck%d source=%s first_source=%s direct_ok=%d "
                "direct_reject=%d fallback=%d last_bpm=%.3f direct_before_hint=%s",
                deck,
                state.current_source or LIVE_BPM_FALLBACK_SOURCE,
                state.first_source or "<none>",
                state.direct_accepted_count,
                state.direct_rejected_count,
                state.fallback_count,
                state.last_accepted_bpm,
                "1" if state.direct_before_hint else "0",
            )

    def _sample_and_maybe_validate(self, session: LiveBPMSession, deck: int, now: float) -> None:
        with self._lock:
            state = self._deck[deck]
            val_session_gen = self._session_gen
            val_discovery_gen = state.discovery_gen
            val_validation_epoch_id = state.validation_epoch_id
            val_candidates_session_gen = state.candidates_session_gen
            val_candidates_hint_epoch = state.candidates_hint_epoch
            candidates = list(state.candidates)
            if not candidates or now < state.next_sample_at:
                return
            hint = state.hint_bpm
            sample_start_hint = state.sample_start_hint
            sample_start_at = state.sample_start_at
            val_sample_start_at = sample_start_at
            val_sample_start_hint = sample_start_hint
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
        if moved_hint:
            with self._lock:
                state = self._deck[deck]
                if state.sample_moved_hint_at <= 0.0 and state.sample_start_at > 0.0:
                    state.sample_moved_hint_at = now
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
            current_session = self._session
            if (
                current_session is None
                or current_session.pid != session.pid
                or current_session.base != session.base
                or self._session_gen != val_session_gen
            ):
                self._drop_validate_total += 1
                self._drop_reason_counts["validate_session_gen_mismatch"] = (
                    self._drop_reason_counts.get("validate_session_gen_mismatch", 0) + 1
                )
                cur_pid = current_session.pid if current_session else 0
                cur_base = current_session.base if current_session else 0
                log.info(
                    "[LBPM][DROP] deck%d drop_validate reason=session_gen_mismatch "
                    "val(pid=%d base=0x%x gen=%d) cur(pid=%d base=0x%x gen=%d)",
                    deck,
                    session.pid,
                    session.base,
                    val_session_gen,
                    cur_pid,
                    cur_base,
                    self._session_gen,
                )
                self._reset_discovery(state, keep_validated=True)
                return
            if (
                state.discovery_gen != val_discovery_gen
                or state.validation_epoch_id != val_validation_epoch_id
                or state.candidates_session_gen != val_candidates_session_gen
                or state.sample_start_at != val_sample_start_at
                or state.sample_start_hint != val_sample_start_hint
            ):
                self._drop_validate_total += 1
                self._drop_reason_counts["validate_epoch_mismatch"] = (
                    self._drop_reason_counts.get("validate_epoch_mismatch", 0) + 1
                )
                log.info(
                    "[LBPM][DROP] deck%d drop_validate reason=epoch_mismatch "
                    "discovery_gen=%d->%d validation_epoch=%d->%d",
                    deck,
                    val_discovery_gen,
                    state.discovery_gen,
                    val_validation_epoch_id,
                    state.validation_epoch_id,
                )
                self._reset_discovery(state, keep_validated=True)
                return
            # Cautious hint semantic guard: only drop when the candidate epoch hint identity
            # changed (candidates_hint_epoch mismatch). Do not require hint_epoch to stay fixed
            # during sampling; hint movement is expected and required for promotion.
            if state.candidates_hint_epoch != val_candidates_hint_epoch:
                self._drop_validate_total += 1
                self._drop_reason_counts["validate_hint_epoch_drift"] = (
                    self._drop_reason_counts.get("validate_hint_epoch_drift", 0) + 1
                )
                log.info(
                    "[LBPM][DROP] deck%d drop_validate reason=hint_epoch_drift "
                    "candidates_hint_epoch=%d->%d cur_hint_epoch=%d",
                    deck,
                    val_candidates_hint_epoch,
                    state.candidates_hint_epoch,
                    state.hint_epoch,
                )
                self._reset_discovery(state, keep_validated=True)
                return
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
                state.last_accepted_bpm = float(winner.end)
                self._set_source_locked(deck, state, LIVE_BPM_DISCOVERY_SOURCE, "discovery_validated", winner.end)
                validate_reason = "hint_moved" if moved_hint else "expired"
                wait_for_moved_ms = 0.0
                if state.sample_moved_hint_at > 0.0 and state.sample_start_at > 0.0:
                    wait_for_moved_ms = (state.sample_moved_hint_at - state.sample_start_at) * 1000.0
                ttfv_ms = 0.0
                if state.first_valid_hint_at > 0.0:
                    ttfv_ms = (now - state.first_valid_hint_at) * 1000.0
                self._reset_discovery(state, keep_validated=True)
                log.info(
                    "[LBPM][VALIDATED] deck%d addr=0x%x type=%s source=%s bpm=%.3f "
                    "ttfv_ms=%.0f validate=%s waited_moved_ms=%.0f drops_scan=%d drops_validate=%d",
                    deck,
                    candidate.addr,
                    candidate.type_name,
                    candidate.source,
                    winner.end,
                    ttfv_ms,
                    validate_reason,
                    wait_for_moved_ms,
                    self._drop_scan_total,
                    self._drop_validate_total,
                )
            else:
                # Measurement-only: log whether we validated due to moved hint or expiry.
                validate_reason = "hint_moved" if moved_hint else "expired"
                wait_for_moved_ms = 0.0
                if state.sample_moved_hint_at > 0.0 and state.sample_start_at > 0.0:
                    wait_for_moved_ms = (state.sample_moved_hint_at - state.sample_start_at) * 1000.0
                log.info(
                    "[LBPM][VALIDATE] deck%d result=none reason=%s watched=%d age_ms=%.0f waited_moved_ms=%.0f",
                    deck,
                    validate_reason,
                    len(state.candidates),
                    (now - state.sample_start_at) * 1000.0 if state.sample_start_at > 0 else 0.0,
                    wait_for_moved_ms,
                )
                self._reset_discovery(state, keep_validated=True)

    def _reset_discovery(self, state: _DeckDiscovery, keep_validated: bool = False) -> None:
        state.discovery_gen += 1
        state.candidates = []
        state.values = {}
        state.timestamps = {}
        state.sample_start_at = 0.0
        state.sample_start_hint = state.hint_bpm
        state.next_sample_at = 0.0
        state.last_scan_at = 0.0
        state.candidates_session_gen = 0
        state.candidates_hint_epoch = state.hint_epoch
        state.sample_moved_hint_at = 0.0
        state.sample_hint_epoch_start = 0
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


def _first_direct_candidate(candidates: Iterable[LiveBPMCandidate]) -> Optional[LiveBPMCandidate]:
    for candidate in candidates:
        if candidate.source == LIVE_BPM_DIRECT_SOURCE:
            return candidate
    return None
