#!/usr/bin/env python3
"""
Standalone probe: find deck-2 position field by scanning around inner1.

Usage:
    python3 -m rb_ss_bridge_v2.probe_deck2 [--window 0x8000] [--dt 5] [--hz 30]

Attaches to the running rekordbox process, walks the known deck-1 chain to
get inner1, then scans inner1 ± WINDOW for any i32 field that advances at
~44100 samples/sec while deck 2 is playing.

Prints a ranked result table. STRICT PASS entries are the deck-2 candidates.
"""
from __future__ import annotations

import argparse
import struct
import sys
import time

sys.path.insert(0, __file__.rsplit("/rb_ss_bridge_v2", 1)[0])

from rb_ss_bridge_v2.rb_memory import (
    _get_vmmap_output, _base_from_vmmap,
    _task_for_pid, _read_bytes, _read_u64, _read_i32,
    _D2_RATE_LO, _D2_RATE_HI, _D2_NEG_JUMP_THR,
    get_rb_pid,
)
from rb_ss_bridge_v2.config import (
    RB_GLOBAL_OFF, RB_DECK1_OFF, RB_INNER_OFF, RB_POS_OFF,
    RB_SCALE, MEM_MAX_ELAPSED_MS,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan for deck-2 position field near inner1")
    ap.add_argument("--window", default="0x8000", help="Scan ± this many bytes from inner1 (hex ok)")
    ap.add_argument("--dt", type=float, default=5.0, help="Sampling duration in seconds")
    ap.add_argument("--hz", type=float, default=30.0, help="Sample rate in Hz")
    args = ap.parse_args()

    window = int(args.window, 16) if args.window.startswith("0x") else int(args.window)
    dt     = args.dt
    hz     = args.hz

    pid = get_rb_pid()
    if pid is None:
        print("ERROR: rekordbox not running")
        sys.exit(1)

    print(f"Attaching to rekordbox pid={pid} ...")
    vmmap_out = _get_vmmap_output(pid)
    base      = _base_from_vmmap(vmmap_out)
    task      = _task_for_pid(pid)
    print(f"  base=0x{base:x}")

    # Walk deck-1 chain: container → DPU1 → inner1
    container = _read_u64(task, base + RB_GLOBAL_OFF)
    dpu1      = _read_u64(task, container + RB_DECK1_OFF)
    inner1    = _read_u64(task, dpu1 + RB_INNER_OFF)
    pos1_now  = _read_i32(task, inner1 + RB_POS_OFF)
    print(f"  container=0x{container:x}  dpu1=0x{dpu1:x}  inner1=0x{inner1:x}")
    print(f"  deck-1 position now: {pos1_now} samples ({int(pos1_now * RB_SCALE)} ms)")

    # Build scan range: inner1 − window .. inner1 + window, step 4 (i32-aligned)
    scan_lo = inner1 - window
    scan_hi = inner1 + window
    stride  = 4
    n_addrs = (scan_hi - scan_lo) // stride

    print(f"\nScanning 0x{scan_lo:x}–0x{scan_hi:x} ({n_addrs} addresses) at {hz} Hz for {dt}s")
    print("Play deck 2 now if not already playing.\n")
    time.sleep(1.0)

    # Phase 1: read initial values
    samples: dict[int, list[tuple[float, int]]] = {}
    t0 = time.monotonic()
    interval = 1.0 / hz
    n_ticks  = int(dt * hz)

    for tick in range(n_ticks):
        deadline = t0 + tick * interval
        now = time.monotonic()
        if deadline > now:
            time.sleep(deadline - now)
        now = time.monotonic()

        try:
            chunk = _read_bytes(task, scan_lo, (scan_hi - scan_lo))
        except OSError as e:
            print(f"  read error tick {tick}: {e}")
            continue

        for i in range(0, len(chunk) - 4, stride):
            addr = scan_lo + i
            raw  = struct.unpack_from("<i", chunk, i)[0]
            if addr not in samples:
                samples[addr] = []
            samples[addr].append((now, raw))

        if tick % int(hz) == 0:
            elapsed = now - t0
            print(f"  {elapsed:.1f}s / {dt}s ...", end="\r", flush=True)

    print(f"\n  Done. Evaluating {len(samples)} addresses ...")

    # Phase 2: evaluate each address
    results = []
    for addr, pts in samples.items():
        if len(pts) < 4:
            continue
        raws     = [r for _, r in pts]
        total_d  = raws[-1] - raws[0]
        total_dt = pts[-1][0] - pts[0][0]
        if total_dt <= 0 or abs(total_d) < 500:
            continue  # not moving

        rate = total_d / total_dt
        neg_jumps = sum(1 for i in range(1, len(raws)) if raws[i] - raws[i-1] < _D2_NEG_JUMP_THR)
        ms_end    = max(0, int(raws[-1] * RB_SCALE))
        min_d = min(raws[i] - raws[i-1] for i in range(1, len(raws)))
        max_d = max(raws[i] - raws[i-1] for i in range(1, len(raws)))

        strict_pass = (
            _D2_RATE_LO <= rate <= _D2_RATE_HI
            and neg_jumps == 0
            and ms_end <= MEM_MAX_ELAPSED_MS
        )
        results.append({
            "addr": addr,
            "offset": addr - inner1,
            "rate": rate,
            "neg_jumps": neg_jumps,
            "ms_end": ms_end,
            "min_d": min_d,
            "max_d": max_d,
            "pass": strict_pass,
        })

    # Sort: PASS first, then by rate proximity to 44100
    results.sort(key=lambda r: (0 if r["pass"] else 1, abs(r["rate"] - 44100)))

    print(f"\n{'addr':18s} {'offset':>10s} {'rate':>10s} {'neg_j':>6s} {'ms_end':>10s} {'min_d':>7s} {'max_d':>7s} {'verdict'}")
    print("-" * 90)
    for r in results[:40]:
        verdict = "STRICT PASS" if r["pass"] else "reject"
        rel = r["offset"]
        sign = "+" if rel >= 0 else "-"
        print(f"  0x{r['addr']:016x}  {sign}0x{abs(rel):04x}  {r['rate']:>10.1f}  {r['neg_jumps']:>6d}  "
              f"{r['ms_end']:>10d}  {r['min_d']:>7d}  {r['max_d']:>7d}  {verdict}")

    passes = [r for r in results if r["pass"]]
    if passes:
        print(f"\n{len(passes)} STRICT PASS address(es):")
        for r in passes:
            rel = r["offset"]
            sign = "+" if rel >= 0 else "-"
            inner_offset = rel - RB_POS_OFF  # subtract 0x0C to get inner ptr offset
            print(f"  addr=0x{r['addr']:x}  inner1{sign}0x{abs(rel):x}  "
                  f"=> inner_ptr = inner1{'+' if inner_offset >= 0 else '-'}0x{abs(inner_offset):x}  "
                  f"rate={r['rate']:.1f}  ms={r['ms_end']}")
    else:
        print("\nNo STRICT PASS found. Is deck 2 playing during the scan?")


if __name__ == "__main__":
    main()
