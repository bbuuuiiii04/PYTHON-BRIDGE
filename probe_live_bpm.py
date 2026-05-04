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
import math
import re
import struct
import sys
import time
from dataclasses import dataclass
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


def snapshot(args: argparse.Namespace) -> None:
    pid, base, task, vmmap_out = _attach()
    print(f"Attached rekordbox pid={pid} base=0x{base:x}")

    anchors = _resolve_anchors(task, base, args.deck, args.objc_window, not args.no_deck2_scan)
    _print_anchors(task, anchors)

    extra_regions: list[Region] = []
    if args.include_objc_regions:
        for idx, (start, size) in enumerate(_objc_regions_from_vmmap(vmmap_out), start=1):
            if size <= args.max_objc_region:
                extra_regions.append(Region(start, size, f"objc_region{idx}"))
    if args.include_rw_regions:
        extra_regions.extend(
            _rw_regions_from_vmmap(vmmap_out, args.max_rw_region, args.max_rw_total)
        )

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
