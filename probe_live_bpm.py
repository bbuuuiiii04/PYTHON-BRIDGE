#!/usr/bin/env python3
"""
Standalone read-only probe for Rekordbox live BPM / pitch-factor fields.

This does not change bridge behavior. It attaches to the running rekordbox
process with the same Mach read helpers used by rb_memory.py, resolves current
deck anchors, then scans nearby readable memory for float32/float64 values that
look like displayed BPM or pitch factors.

Typical workflow:
    python3 -m rb_ss_bridge_v2.probe_live_bpm snapshot --deck 1 --expect-bpm 128
    python3 -m rb_ss_bridge_v2.probe_live_bpm snapshot --deck 1 --expect-bpm 140 --library-bpm 128
    python3 -m rb_ss_bridge_v2.probe_live_bpm watch --deck 1 --addr 0x600001234568 --type f32
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, __file__.rsplit("/rb_ss_bridge_v2", 1)[0])

from rb_ss_bridge_v2.config import (  # noqa: E402
    MEM_MAX_ELAPSED_MS,
    RB_DECK1_OFF,
    RB_DECK2_OFF,
    RB_GLOBAL_OFF,
    RB_INNER_OFF,
    RB_POS_OFF,
    RB_SCALE,
    RB_SEC_OFF,
)
from rb_ss_bridge_v2.rb_memory import (  # noqa: E402
    _base_from_vmmap,
    _get_vmmap_output,
    _objc_regions_from_vmmap,
    _read_bytes,
    _read_i32,
    _read_u64,
    _scan_objc_zone,
    _task_for_pid,
    get_rb_pid,
)


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


def _parse_int(text: str) -> int:
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def _is_objc(ptr: int) -> bool:
    return 0x600000000000 <= ptr <= 0x6FFFFFFFFFFF


def _safe_read_u64(task: int, addr: int) -> int | None:
    try:
        return _read_u64(task, addr)
    except OSError:
        return None


def _safe_read_i32(task: int, addr: int) -> int | None:
    try:
        return _read_i32(task, addr)
    except OSError:
        return None


def _find_region(regions: Iterable[Region], addr: int) -> Region | None:
    for region in regions:
        if region.start <= addr < region.end:
            return region
    return None


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


def _nearest_anchor(addr: int, anchors: list[Anchor]) -> tuple[str, int]:
    if not anchors:
        return "<none>", 0
    anchor = min(anchors, key=lambda a: abs(addr - a.addr))
    return anchor.name, addr - anchor.addr


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


def _attach() -> tuple[int, int, int, str]:
    pid = get_rb_pid()
    if pid is None:
        raise SystemExit("ERROR: rekordbox not running")
    vmmap_out = _get_vmmap_output(pid)
    base = _base_from_vmmap(vmmap_out)
    task = _task_for_pid(pid)
    return pid, base, task, vmmap_out


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


def _print_anchors(task: int, anchors: list[Anchor]) -> None:
    print("Anchors:")
    for anchor in anchors:
        suffix = ""
        if anchor.name.startswith("inner") or "candidate" in anchor.name:
            raw = _safe_read_i32(task, anchor.addr + RB_POS_OFF)
            if raw is not None and 0 <= int(raw * RB_SCALE) <= MEM_MAX_ELAPSED_MS:
                suffix = f" pos={raw} samples/{int(raw * RB_SCALE)}ms"
        print(f"  {anchor.name:24s} 0x{anchor.addr:016x}{suffix}")


def _extra_regions_from_args(vmmap_out: str, args: argparse.Namespace) -> list[Region]:
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


def _collect_hits(
    task: int,
    vmmap_out: str,
    anchors: list[Anchor],
    args: argparse.Namespace,
) -> list[Hit]:
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


def _seed_hits_from_addrs(
    task: int,
    anchors: list[Anchor],
    addrs: list[str] | None,
    type_name: str,
) -> list[Hit]:
    if not addrs:
        return []
    seeds: list[Hit] = []
    seen: set[int] = set()
    for addr_text in addrs:
        addr = _parse_int(addr_text)
        if addr in seen:
            continue
        seen.add(addr)
        try:
            value = _read_float(task, addr, type_name)
        except OSError:
            continue
        nearest, delta = _nearest_anchor(addr, anchors)
        seeds.append(
            Hit(
                addr=addr,
                type_name=type_name,
                value=value,
                role="bpm",
                score=0.0,
                region="manual_seed",
                nearest_anchor=nearest,
                anchor_delta=delta,
            )
        )
    return seeds


def snapshot(args: argparse.Namespace) -> None:
    pid, base, task, vmmap_out = _attach()
    print(f"Attached rekordbox pid={pid} base=0x{base:x}")

    anchors = _resolve_anchors(task, base, args.deck, args.objc_window, not args.no_deck2_scan)
    _print_anchors(task, anchors)

    all_hits = _collect_hits(task, vmmap_out, anchors, args)
    print(
        f"\nTop {min(args.limit, len(all_hits))} float candidates "
        f"(deck={args.deck}, expect_bpm={args.expect_bpm}, library_bpm={args.library_bpm}):"
    )
    print(
        f"{'addr':18s} {'type':4s} {'role':7s} {'value':>12s} {'score':>10s} "
        f"{'nearest_anchor':24s} {'delta':>10s} region"
    )
    print("-" * 120)
    for hit in all_hits[: args.limit]:
        sign = "+" if hit.anchor_delta >= 0 else "-"
        print(
            f"0x{hit.addr:016x} {hit.type_name:4s} {hit.role:7s} "
            f"{hit.value:12.6f} {hit.score:10.6f} {hit.nearest_anchor:24s} "
            f"{sign}0x{abs(hit.anchor_delta):x} {hit.region}"
        )


def watch(args: argparse.Namespace) -> None:
    pid, base, task, _ = _attach()
    print(f"Attached rekordbox pid={pid} base=0x{base:x}")
    anchors = _resolve_anchors(task, base, args.deck, args.objc_window, not args.no_deck2_scan)
    _print_anchors(task, anchors)
    addrs = [_parse_int(addr) for addr in args.addr]
    fmt = "<f" if args.type == "f32" else "<d"
    size = 4 if args.type == "f32" else 8
    interval = 1.0 / args.hz
    t0 = time.monotonic()
    print("\ntime_s,addr,type,value,computed_bpm,nearest_anchor,delta")
    while time.monotonic() - t0 < args.duration:
        now = time.monotonic()
        for addr in addrs:
            try:
                value = struct.unpack(fmt, _read_bytes(task, addr, size))[0]
            except OSError as exc:
                print(f"{now - t0:.3f},0x{addr:x},{args.type},READ_ERROR:{exc},,,")
                continue
            computed = ""
            if args.library_bpm and args.factor_min <= value <= args.factor_max:
                computed = f"{args.library_bpm * value:.6f}"
            nearest, delta = _nearest_anchor(addr, anchors)
            sign = "+" if delta >= 0 else "-"
            print(
                f"{now - t0:.3f},0x{addr:x},{args.type},{value:.9f},"
                f"{computed},{nearest},{sign}0x{abs(delta):x}"
            )
        elapsed = time.monotonic() - now
        if elapsed < interval:
            time.sleep(interval - elapsed)


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
    if expected_after is None:
        return "moved_unverified"
    if abs(values[-1] - expected_after) <= tolerance:
        return "pass"
    return "moved_wrong_value"


def _watch_hits_for_validation(
    task: int,
    hits: list[Hit],
    duration: float,
    hz: float,
    expected_after: float | None,
    tolerance: float,
    min_delta: float,
) -> list[WatchResult]:
    values_by_hit: dict[tuple[int, str], list[float]] = {(hit.addr, hit.type_name): [] for hit in hits}
    interval = 1.0 / hz
    t0 = time.monotonic()
    while time.monotonic() - t0 < duration:
        now = time.monotonic()
        for hit in hits:
            try:
                value = _read_float(task, hit.addr, hit.type_name)
            except OSError:
                continue
            if math.isfinite(value):
                values_by_hit[(hit.addr, hit.type_name)].append(value)
        elapsed = time.monotonic() - now
        if elapsed < interval:
            time.sleep(interval - elapsed)

    results: list[WatchResult] = []
    for hit in hits:
        values = values_by_hit[(hit.addr, hit.type_name)]
        verdict = _verdict_for_samples(values, expected_after, tolerance, min_delta)
        if values:
            start = values[0]
            end = values[-1]
            minimum = min(values)
            maximum = max(values)
            max_delta = maximum - minimum
        else:
            start = end = minimum = maximum = max_delta = float("nan")
        results.append(WatchResult(hit, len(values), start, end, minimum, maximum, max_delta, verdict))

    verdict_order = {"pass": 0, "moved_unverified": 1, "moved_wrong_value": 2, "stale": 3, "read_error": 4}
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


def _load_cache(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"sessions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": []}
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        return {"sessions": []}
    return data


def _write_cache(
    path: Path,
    pid: int,
    base: int,
    deck: int,
    expected_before: float | None,
    expected_after: float,
    results: list[WatchResult],
) -> None:
    passed = [result for result in results if result.verdict == "pass"]
    if not passed:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_cache(path)
    sessions = data.setdefault("sessions", [])
    assert isinstance(sessions, list)
    sessions.append(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pid": pid,
            "base": f"0x{base:x}",
            "deck": deck,
            "expected_before": expected_before,
            "expected_after": expected_after,
            "candidates": [
                {
                    "addr": f"0x{result.hit.addr:x}",
                    "type": result.hit.type_name,
                    "start": result.start,
                    "end": result.end,
                    "max_delta": result.max_delta,
                    "nearest_anchor": result.hit.nearest_anchor,
                    "anchor_delta": result.hit.anchor_delta,
                    "region": result.hit.region,
                }
                for result in passed
            ],
        }
    )
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cached_candidates_for_session(
    cache: dict[str, object],
    pid: int,
    base: int,
    deck: int,
) -> list[dict[str, object]]:
    sessions = cache.get("sessions")
    if not isinstance(sessions, list):
        return []
    out: list[dict[str, object]] = []
    for session in reversed(sessions):
        if not isinstance(session, dict):
            continue
        if session.get("pid") != pid:
            continue
        if session.get("base") != f"0x{base:x}":
            continue
        if session.get("deck") != deck:
            continue
        candidates = session.get("candidates")
        if isinstance(candidates, list):
            out.extend(candidate for candidate in candidates if isinstance(candidate, dict))
    return out


def validate(args: argparse.Namespace) -> None:
    pid, base, task, vmmap_out = _attach()
    print(f"Attached rekordbox pid={pid} base=0x{base:x}")
    anchors = _resolve_anchors(task, base, args.deck, args.objc_window, not args.no_deck2_scan)
    _print_anchors(task, anchors)

    hits = _dedupe_hits(_collect_hits(task, vmmap_out, anchors, args))
    if args.type != "both":
        hits = [hit for hit in hits if hit.type_name == args.type]

    seeded_hits = _seed_hits_from_addrs(task, anchors, args.addr, args.seed_type)
    selected_hits = _select_validation_hits(hits, max(0, args.watch_limit - len(seeded_hits)))
    watch_hits = _dedupe_hits([*seeded_hits, *selected_hits])[: args.watch_limit]
    if not watch_hits:
        raise SystemExit("ERROR: no candidates found for validation")

    print(
        f"\nWatching {len(watch_hits)} candidates for {args.duration:.1f}s at {args.hz:.1f} Hz. "
        "Move only the target deck pitch during this window."
    )
    print(
        f"{'addr':18s} {'type':4s} {'start':>12s} {'end':>12s} {'min':>12s} "
        f"{'max':>12s} {'delta':>12s} {'verdict':18s} anchor delta region"
    )
    print("-" * 132)
    results = _watch_hits_for_validation(
        task,
        watch_hits,
        args.duration,
        args.hz,
        args.expected_after,
        args.tolerance,
        args.min_delta,
    )
    for result in results:
        sign = "+" if result.hit.anchor_delta >= 0 else "-"
        print(
            f"0x{result.hit.addr:016x} {result.hit.type_name:4s} "
            f"{result.start:12.6f} {result.end:12.6f} {result.minimum:12.6f} "
            f"{result.maximum:12.6f} {result.max_delta:12.6f} {result.verdict:18s} "
            f"{result.hit.nearest_anchor} {sign}0x{abs(result.hit.anchor_delta):x} {result.hit.region}"
        )

    passed = [result for result in results if result.verdict == "pass"]
    moved = [result for result in results if result.verdict == "moved_unverified"]
    stale = [result for result in results if result.verdict == "stale"]
    print(f"\nSummary: pass={len(passed)} moved_unverified={len(moved)} stale={len(stale)}")
    if args.expected_after is None:
        print("No --expected-after was provided, so moved candidates were not promoted or cached.")
    else:
        cache_path = Path(args.cache_file).expanduser()
        _write_cache(cache_path, pid, base, args.deck, args.expect_bpm, args.expected_after, results)
        if passed:
            print(f"Cached {len(passed)} passed candidates to {cache_path}")
        else:
            print("No candidates passed; cache was not updated.")


def cache_check(args: argparse.Namespace) -> None:
    pid, base, task, _ = _attach()
    cache_path = Path(args.cache_file).expanduser()
    cache = _load_cache(cache_path)
    candidates = _cached_candidates_for_session(cache, pid, base, args.deck)
    print(f"Attached rekordbox pid={pid} base=0x{base:x}")
    print(f"Cache: {cache_path}")
    print(f"Current-session cached candidates for deck {args.deck}: {len(candidates)}")
    if not candidates:
        return

    print(f"{'addr':18s} {'type':4s} {'value':>12s} {'status':14s} source_end source_delta")
    print("-" * 92)
    for candidate in candidates[: args.limit]:
        addr_text = candidate.get("addr")
        type_name = candidate.get("type")
        if not isinstance(addr_text, str) or type_name not in ("f32", "f64"):
            continue
        try:
            value = _read_float(task, _parse_int(addr_text), type_name)
        except OSError:
            print(f"{addr_text:18s} {type_name:4s} {'READ_ERROR':>12s} read_error     - -")
            continue
        status = "readable"
        if args.expect_bpm is not None:
            status = "matches" if abs(value - args.expect_bpm) <= args.tolerance else "mismatch"
        source_end = candidate.get("end", "-")
        source_delta = candidate.get("max_delta", "-")
        print(f"{addr_text:18s} {type_name:4s} {value:12.6f} {status:14s} {source_end} {source_delta}")


def compare(args: argparse.Namespace) -> None:
    before = Path(args.before).read_text(encoding="utf-8", errors="replace")
    after = Path(args.after).read_text(encoding="utf-8", errors="replace")
    row_re = re.compile(
        r"^(0x[0-9a-fA-F]+)\s+(f32|f64)\s+(\w+)\s+([-0-9.]+)\s+([-0-9.]+)\s+(\S+)\s+([+-]0x[0-9a-fA-F]+)\s+(.*)$"
    )

    def rows(text: str) -> dict[tuple[str, str], tuple[float, str, str, str]]:
        out: dict[tuple[str, str], tuple[float, str, str, str]] = {}
        for line in text.splitlines():
            m = row_re.match(line.strip())
            if not m:
                continue
            out[(m.group(1).lower(), m.group(2))] = (
                float(m.group(4)),
                m.group(3),
                m.group(6),
                m.group(7),
            )
        return out

    b = rows(before)
    a = rows(after)
    changed = []
    for key, b_data in b.items():
        if key not in a:
            continue
        a_data = a[key]
        delta = a_data[0] - b_data[0]
        if abs(delta) < args.min_delta:
            continue
        changed.append((abs(delta), delta, key, b_data, a_data))
    changed.sort(reverse=True)
    print(f"Changed candidates present in both snapshots: {len(changed)}")
    print(f"{'addr':18s} {'type':4s} {'before':>12s} {'after':>12s} {'delta':>12s} anchor delta role")
    print("-" * 92)
    for _, delta, (addr, typ), b_data, a_data in changed[: args.limit]:
        print(
            f"{addr:18s} {typ:4s} {b_data[0]:12.6f} {a_data[0]:12.6f} {delta:12.6f} "
            f"{a_data[2]} {a_data[3]} {a_data[1]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Rekordbox memory for live BPM / pitch-factor fields")
    sub = parser.add_subparsers(dest="cmd", required=True)

    snap = sub.add_parser("snapshot", help="Scan current memory around deck anchors")
    snap.add_argument("--deck", type=int, choices=(1, 2), default=1)
    snap.add_argument("--expect-bpm", type=float, default=None)
    snap.add_argument("--library-bpm", type=float, default=None)
    snap.add_argument("--window", type=lambda s: int(s, 0), default=0x4000)
    snap.add_argument("--objc-window", type=lambda s: int(s, 0), default=0x10000)
    snap.add_argument("--no-deck2-scan", action="store_true")
    snap.add_argument("--include-objc-regions", action="store_true")
    snap.add_argument("--max-objc-region", type=lambda s: int(s, 0), default=0x200000)
    snap.add_argument("--bpm-min", type=float, default=40.0)
    snap.add_argument("--bpm-max", type=float, default=240.0)
    snap.add_argument("--factor-min", type=float, default=0.50)
    snap.add_argument("--factor-max", type=float, default=2.00)
    snap.add_argument("--mode", choices=("both", "bpm", "factor"), default="both")
    snap.add_argument("--max-hits-per-region", type=int, default=100)
    snap.add_argument("--include-rw-regions", action="store_true")
    snap.add_argument("--max-rw-region", type=lambda s: int(s, 0), default=0x200000)
    snap.add_argument("--max-rw-total", type=lambda s: int(s, 0), default=0x8000000)
    snap.add_argument("--limit", type=int, default=80)
    snap.set_defaults(func=snapshot)

    wt = sub.add_parser("watch", help="Watch one or more candidate addresses over time")
    wt.add_argument("--deck", type=int, choices=(1, 2), default=1)
    wt.add_argument("--addr", action="append", required=True, help="Address to watch; repeatable")
    wt.add_argument("--type", choices=("f32", "f64"), default="f32")
    wt.add_argument("--library-bpm", type=float, default=None)
    wt.add_argument("--duration", type=float, default=20.0)
    wt.add_argument("--hz", type=float, default=10.0)
    wt.add_argument("--objc-window", type=lambda s: int(s, 0), default=0x10000)
    wt.add_argument("--no-deck2-scan", action="store_true")
    wt.add_argument("--factor-min", type=float, default=0.50)
    wt.add_argument("--factor-max", type=float, default=2.00)
    wt.set_defaults(func=watch)

    val = sub.add_parser("validate", help="Scan, watch, classify, and optionally cache live BPM candidates")
    val.add_argument("--deck", type=int, choices=(1, 2), default=1)
    val.add_argument("--expect-bpm", type=float, required=True, help="Current BPM before pitch movement")
    val.add_argument("--expected-after", type=float, default=None, help="Expected BPM after pitch movement; enables pass/cache")
    val.add_argument("--library-bpm", type=float, default=None)
    val.add_argument("--window", type=lambda s: int(s, 0), default=0x10000)
    val.add_argument("--objc-window", type=lambda s: int(s, 0), default=0x10000)
    val.add_argument("--no-deck2-scan", action="store_true")
    val.add_argument("--include-objc-regions", action="store_true")
    val.add_argument("--max-objc-region", type=lambda s: int(s, 0), default=0x200000)
    val.add_argument("--include-rw-regions", action="store_true")
    val.add_argument("--max-rw-region", type=lambda s: int(s, 0), default=0x400000)
    val.add_argument("--max-rw-total", type=lambda s: int(s, 0), default=0x10000000)
    val.add_argument("--bpm-min", type=float, default=40.0)
    val.add_argument("--bpm-max", type=float, default=240.0)
    val.add_argument("--factor-min", type=float, default=0.50)
    val.add_argument("--factor-max", type=float, default=2.00)
    val.add_argument("--mode", choices=("both", "bpm", "factor"), default="bpm")
    val.add_argument("--type", choices=("both", "f32", "f64"), default="f32")
    val.add_argument("--addr", action="append", help="Manual candidate address to include in validation; repeatable")
    val.add_argument("--seed-type", choices=("f32", "f64"), default="f32")
    val.add_argument("--max-hits-per-region", type=int, default=20)
    val.add_argument("--watch-limit", type=int, default=24)
    val.add_argument("--duration", type=float, default=25.0)
    val.add_argument("--hz", type=float, default=5.0)
    val.add_argument("--min-delta", type=float, default=0.05)
    val.add_argument("--tolerance", type=float, default=0.25)
    val.add_argument(
        "--cache-file",
        default="~/.cache/rb_ss_bridge_v2/live_bpm_candidates.json",
        help="Per-process validation cache path",
    )
    val.set_defaults(func=validate)

    cc = sub.add_parser("cache-check", help="Read current-session validated candidate cache")
    cc.add_argument("--deck", type=int, choices=(1, 2), default=1)
    cc.add_argument("--expect-bpm", type=float, default=None)
    cc.add_argument("--tolerance", type=float, default=0.25)
    cc.add_argument("--limit", type=int, default=20)
    cc.add_argument(
        "--cache-file",
        default="~/.cache/rb_ss_bridge_v2/live_bpm_candidates.json",
        help="Per-process validation cache path",
    )
    cc.set_defaults(func=cache_check)

    cmp = sub.add_parser("compare", help="Compare two saved snapshot outputs")
    cmp.add_argument("before")
    cmp.add_argument("after")
    cmp.add_argument("--min-delta", type=float, default=0.001)
    cmp.add_argument("--limit", type=int, default=80)
    cmp.set_defaults(func=compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
