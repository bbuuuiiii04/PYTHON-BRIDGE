#!/usr/bin/env python3
"""
AWR-173 passive CFX FILTER desk-calibration probe.

Standalone, read-only. Attaches to the running Rekordbox process with the same
Mach read helpers rb_state_reader.py uses, resolves the six CFX FILTER chains for
the detected RB version from rb_offsets.py, and prints one line per deck per
sample so the operator can calibrate the bloom threshold at the desk. It never
writes to the RB process and has no bridge import side effects.

Desk workflow (Part F):
    python3 probe_cfx_filter.py
    # Sweep deck 1 knob full CCW -> full CW: expect param0 ~0.0 / ~0.5 / ~1.0,
    # [VALID] throughout. If inverted, the envelope mapping flips in one place.
    # Play a bass-heavy track, sweep slowly clockwise, press Enter at the ear-
    # bloom moment -> a MARK line captures param0 for both decks. Repeat 2-3x;
    # take the median for cfx_sweep.bloom_threshold_norm.
    # Ctrl-C to exit.
"""
from __future__ import annotations

import math
import select
import struct
import sys
import time

sys.path.insert(0, __file__.rsplit("/rb_ss_bridge_v2", 1)[0])

from rb_ss_bridge_v2.live_bpm import read_rekordbox_version  # noqa: E402
from rb_ss_bridge_v2.rb_memory import (  # noqa: E402
    _base_from_vmmap,
    _get_vmmap_output,
    _read_bytes,
    _task_for_pid,
    get_rb_pid,
)
from rb_ss_bridge_v2.rb_offsets import ChainEntry, load_offsets_for_version  # noqa: E402

SAMPLE_HZ = 10.0


def _attach() -> tuple[int, int, int]:
    pid = get_rb_pid()
    if pid is None:
        raise SystemExit("ERROR: rekordbox not running")
    base = _base_from_vmmap(_get_vmmap_output(pid))
    task = _task_for_pid(pid)
    return pid, base, task


def _follow_addr(task: int, base: int, ch: ChainEntry) -> int | None:
    """Walk the pointer chain; None on any null deref. Mirrors
    RBStateReader._follow_addr exactly (passive, read-only)."""
    addr = base
    for hop in ch.hops:
        try:
            ptr = _read_bytes(task, addr + hop, 8)
        except OSError:
            return None
        addr = struct.unpack_from("<Q", ptr)[0]
    return addr + ch.final_off


def _read_f32(task: int, base: int, ch: ChainEntry) -> float | None:
    addr = _follow_addr(task, base, ch)
    if addr is None:
        return None
    try:
        return struct.unpack_from("<f", _read_bytes(task, addr, 4))[0]
    except OSError:
        return None


def _read_i32(task: int, base: int, ch: ChainEntry) -> int | None:
    addr = _follow_addr(task, base, ch)
    if addr is None:
        return None
    try:
        return struct.unpack_from("<i", _read_bytes(task, addr, 4))[0]
    except OSError:
        return None


def _sample_deck(task, base, param_ch, id_ch, unit_ch, deck):
    param0 = _read_f32(task, base, param_ch)
    selected_id = _read_i32(task, base, id_ch)
    unit_channel = _read_i32(task, base, unit_ch)
    valid = (
        selected_id == 0
        and unit_channel == deck - 1
        and param0 is not None
        and math.isfinite(param0)
        and 0.0 <= param0 <= 1.0
    )
    return param0, selected_id, unit_channel, valid


def main() -> None:
    pid, base, task = _attach()
    version = read_rekordbox_version()
    print(f"Attached rekordbox pid={pid} base=0x{base:x} version={version or 'unknown'}")

    offs = load_offsets_for_version(version) if version else None
    decks = None
    if offs is not None:
        decks = (
            (1, offs.cfx_deck1_filter_param0, offs.cfx_deck1_selected_id, offs.cfx_deck1_unit_channel),
            (2, offs.cfx_deck2_filter_param0, offs.cfx_deck2_selected_id, offs.cfx_deck2_unit_channel),
        )
    if decks is None or any(ch is None for _d, *chs in decks for ch in chs):
        raise SystemExit(
            f"ERROR: no CFX FILTER chains for RB version {version or 'unknown'} "
            "(this feature exists for 7.2.11 only)"
        )

    print("Sampling at ~10 Hz. Press Enter to MARK the bloom point; Ctrl-C to exit.\n")
    interval = 1.0 / SAMPLE_HZ
    try:
        while True:
            start = time.monotonic()
            samples = {}
            for deck, param_ch, id_ch, unit_ch in decks:
                p, sid, uc, valid = _sample_deck(task, base, param_ch, id_ch, unit_ch, deck)
                samples[deck] = (p, sid, uc, valid)
                p_str = f"{p:.3f}" if p is not None else "None"
                tag = "[VALID]" if valid else "[INVALID]"
                print(f"deck={deck} selected_id={sid} unit_ch={uc} param0={p_str} {tag}")

            # Non-blocking Enter check: a MARK captures the active sample per deck.
            ready, _, _ = select.select([sys.stdin], [], [], 0.0)
            if ready:
                sys.stdin.readline()
                for deck, (p, _sid, _uc, _v) in samples.items():
                    p_str = f"{p:.3f}" if p is not None else "None"
                    print(f"MARK deck={deck} param0={p_str}")

            elapsed = time.monotonic() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)
    except KeyboardInterrupt:
        print("\nexit")


if __name__ == "__main__":
    main()
