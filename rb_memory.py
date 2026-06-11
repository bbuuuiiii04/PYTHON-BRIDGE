"""
Direct Rekordbox memory reading via macOS mach task API.

No Frida. No injection. Pure ctypes + mach syscalls.

Requirements:
  - rekordbox must have com.apple.security.get-task-allow = true (confirmed 7.2.11)
  - bridge process and rekordbox run as same OS user (no root needed)

Public API:
  PositionCache   — thread-safe dict of PositionSnapshot per deck
  RBMemoryReader  — daemon thread; populates PositionCache at MEM_POLL_HZ
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import re
import struct
import subprocess
import threading
import time
from dataclasses import replace
from typing import Callable, Optional

from .config import (
    RB_SCALE, RB_GLOBAL_OFF, RB_DECK_OFFS,
    RB_DECK1_OFF, RB_DECK2_OFF,
    RB_DPU_VTABLE_OFF, RB_DPU_SCAN_WINDOW,
    RB_INNER_OFF, RB_INNER_LEN_OFF, RB_POS_OFF,
    RB_SEC_OFF, RB_PLAY_OFF, RB_DDJ_OFF,
    OUTER_INNER1_OFF, OUTER_INNER2_OFF, OUTER_FAST_PATH_DELTA, DECK2_INNER1_DELTA,
    MEM_POLL_HZ, MEM_MAX_ELAPSED_MS,
)
from .models import PositionSnapshot
from .rb_offsets import ChainEntry, RBOffsetVersion, load_offsets_for_version

log = logging.getLogger("rb_memory")
POS_CHAIN_DIRECT_ENV = "RBSS_POS_CHAIN_DIRECT"
# Opt-in: when the live_pos chain is healthy, skip the redundant per-tick ObjC
# read_deck() (whose result the chain immediately overwrites) and the deck-2
# resolution pipeline (whose inner the chain makes unnecessary). Default OFF —
# leaves the production hot path byte-for-byte unchanged until A/B-measured.
POS_CHAIN_SKIP_OBJC_ENV = "RBSS_POS_CHAIN_SKIP_OBJC"
# Cadence for refreshing deck-1 track_length_ms via read_deck() while in
# skip-ObjC mode (the chain cannot read length; filepath_resolver needs it).
_LENGTH_REFRESH_INTERVAL_S = 1.0

# ── mach syscall bindings ────────────────────────────────────────────────────

_KERN_SUCCESS = 0
_libsys = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)

# mach_task_self_ is a mach_port_t *variable* on Apple Silicon — NOT a callable function.
# Reading it via in_dll avoids the SIGBUS crash from jumping into a __DATA_DIRTY page.
_task_self_var = ctypes.c_uint32.in_dll(_libsys, "mach_task_self_")

# task_for_pid(task_t, pid_t, *task_t) → kern_return_t
_fn_task_for_pid = _libsys.task_for_pid
_fn_task_for_pid.restype  = ctypes.c_int
_fn_task_for_pid.argtypes = [
    ctypes.c_uint32,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_uint32),
]

# mach_vm_read_overwrite(task, addr, size, data_addr_as_u64, *outsize) → kern_return_t
_fn_vm_read = _libsys.mach_vm_read_overwrite
_fn_vm_read.restype  = ctypes.c_int
_fn_vm_read.argtypes = [
    ctypes.c_uint32,   # target task
    ctypes.c_uint64,   # address
    ctypes.c_uint64,   # size
    ctypes.c_uint64,   # buffer address (cast from pointer)
    ctypes.POINTER(ctypes.c_uint64),  # bytes read out
]


def _mach_task_self() -> int:
    return _task_self_var.value


def _task_for_pid(pid: int) -> int:
    task = ctypes.c_uint32(0)
    kr = _fn_task_for_pid(_mach_task_self(), pid, ctypes.byref(task))
    if kr != _KERN_SUCCESS:
        raise OSError(f"task_for_pid({pid}) failed kern_return={kr}")
    return task.value


def _read_bytes(task: int, addr: int, size: int) -> bytes:
    buf = (ctypes.c_uint8 * size)()
    out = ctypes.c_uint64(0)
    kr = _fn_vm_read(task, addr, size, ctypes.addressof(buf), ctypes.byref(out))
    if kr != _KERN_SUCCESS:
        raise OSError(f"mach_vm_read_overwrite(0x{addr:x}, {size}) kern_return={kr}")
    return bytes(buf[: int(out.value)])


def _read_u64(task: int, addr: int) -> int:
    return struct.unpack_from("<Q", _read_bytes(task, addr, 8))[0]


def _read_i32(task: int, addr: int) -> int:
    return struct.unpack_from("<i", _read_bytes(task, addr, 4))[0]


def _read_u8(task: int, addr: int) -> int:
    return struct.unpack_from("B", _read_bytes(task, addr, 1))[0]


# ── Heap range constants ─────────────────────────────────────────────────────

# ObjC nano-malloc zone — inner1/inner2 pointers from outer live here.
_OBJC_HEAP_LO = 0x600000000000
_OBJC_HEAP_HI = 0x6fffffffffff

# Standard process heap range scanned when searching for outer struct.
_STD_HEAP_LO  = 0x100000000
_STD_HEAP_HI  = 0x1000000000  # 64 GB ceiling covers all observed allocations

# ── Process discovery ────────────────────────────────────────────────────────

def get_rb_pid() -> Optional[int]:
    out = subprocess.run(
        ["pgrep", "-x", "rekordbox"],
        capture_output=True, text=True, timeout=3,
    ).stdout.strip()
    if not out:
        return None
    return int(out.splitlines()[0])


def _get_vmmap_output(pid: int) -> str:
    """Run vmmap --wide and return raw output (may take several seconds)."""
    return subprocess.run(
        ["vmmap", "--wide", str(pid)],
        capture_output=True, text=True, timeout=15,
    ).stdout


def _base_from_vmmap(out: str) -> int:
    """Extract TEXT segment load address from vmmap output."""
    m = re.search(r"Load Address:\s*0x([0-9a-fA-F]+)", out)
    if m:
        return int(m.group(1), 16)
    for line in out.splitlines():
        if "rekordbox" in line and "__TEXT" in line:
            m = re.match(r"\s*([0-9a-fA-F]+)-", line)
            if m:
                return int(m.group(1), 16)
    raise ValueError("Cannot determine RB base from vmmap output")


def _scan_regions_from_vmmap(out: str) -> list[tuple[int, int]]:
    """Extract (start, size) pairs for standard heap regions from vmmap output.

    Filters for rw- regions in the standard process heap address range that are
    large enough to contain the outer struct (≥128 bytes) and small enough to
    scan efficiently (≤64 MB).
    """
    regions: list[tuple[int, int]] = []
    for line in out.splitlines():
        if "rw-" not in line:
            continue
        m = re.search(r'\b([0-9a-fA-F]+)-([0-9a-fA-F]+)\b', line)
        if not m:
            continue
        start = int(m.group(1), 16)
        end   = int(m.group(2), 16)
        size  = end - start
        if not (_STD_HEAP_LO <= start < _STD_HEAP_HI):
            continue
        if size < 0x80 or size > 0x4000000:
            continue
        regions.append((start, size))
    return regions


def _objc_regions_from_vmmap(out: str) -> list[tuple[int, int]]:
    """Extract readable ObjC/nano heap regions for broad Deck-2 fallback scans."""
    regions: list[tuple[int, int]] = []
    for line in out.splitlines():
        if "rw-" not in line:
            continue
        m = re.search(r'\b([0-9a-fA-F]+)-([0-9a-fA-F]+)\b', line)
        if not m:
            continue
        start = int(m.group(1), 16)
        end   = int(m.group(2), 16)
        if not (_OBJC_HEAP_LO <= start < _OBJC_HEAP_HI):
            continue
        size = end - start
        if size < 0x1000:
            continue
        regions.append((start, size))
    return regions


def get_rb_base(pid: int) -> int:
    """Return the TEXT segment load address (ASLR base) for rekordbox."""
    return _base_from_vmmap(_get_vmmap_output(pid))


# ── Deck-2 inner discovery ───────────────────────────────────────────────────
#
# The paired "outer" model (outer+0x08 → inner1, outer+0x78 → inner2) was
# disproven as a reliable finder — container−0x270+0x78 produces a 4-second
# repeating counter, not true track position. The correct deck-2 inner is
# found independently via three ordered candidates:
#
#   A. inner1 + DECK2_INNER1_DELTA  (strongest: probe found it at inner1+0x4e0)
#   B. (container − OUTER_FAST_PATH_DELTA)[+OUTER_INNER2_OFF] → ptr (demoted)
#   C. Standard-heap scan for ObjC ptrs at +0x08 or +0x78 with plausible pos
#
# All candidates are validated by _strict_eval_candidate() which rejects:
#   - short-cycle repeating counters (negative jumps)
#   - wrong rate (not 38k–50k samples/sec)
#   - out-of-range positions
#
# Validation is NON-BLOCKING: the reader thread samples candidates across
# normal poll ticks (~30 Hz over 4 s) so deck-1 reads are never interrupted.

_D2_RATE_LO        = 38_000   # samples/sec — lower bound for true playback
_D2_RATE_HI        = 50_000   # samples/sec — upper bound
_D2_NEG_JUMP_THR   = -1_000   # samples — delta below this = backwards jump / reset
_D2_VALIDATE_DT    = 4.0      # seconds to sample each resolution attempt
_D2_SAMPLE_HZ      = 30.0     # target sample rate during validation window
_D2_STATIC_TOL_MS   = 1_500    # paused/startup target elapsed tolerance
_D2_STATIC_GAP_MS   = 250      # require clear best-vs-runner-up separation
_D2_SCAN_WINDOWS    = (0x10000, 0x20000, 0x40000)
_D2_RETRY_IDLE_S    = 30.0
_D2_RETRY_PLAYING_S = 5.0
_D2_PROVISIONAL_RETRY_S = 5.0  # re-sample remembered candidate soon after play starts
_D2_PLAY_RECENT_S = 8.0        # tolerate TL play/load/pause jitter during resolution
_D2_HEAP_SCAN_MIN_ATTEMPT = 4
_D2_HEAP_CHUNK_BYTES = 0x400000
_D2_HEAP_MAX_BYTES = 0x8000000
_D2_HEAP_TARGET_TOL_MS = 10_000
_D2_HEAP_MAX_CANDIDATES = 8
_CHAIN_BACKWARD_THR_SAMPLES = 10_000
_CHAIN_RESET_SAMPLES = 10_000


def _is_objc(ptr: int) -> bool:
    return _OBJC_HEAP_LO <= ptr <= _OBJC_HEAP_HI


def _quick_plausible_inner(task: int, ptr: int) -> bool:
    """True if ptr is an ObjC-heap address whose +0x0C position is in-range."""
    if not _is_objc(ptr):
        return False
    try:
        raw = _read_i32(task, ptr + RB_POS_OFF)
        return 0 <= max(0, int(raw * RB_SCALE)) <= MEM_MAX_ELAPSED_MS
    except OSError:
        return False


def _scan_objc_zone(
    task: int, inner1: int, window: int = 0x10000, dt: float = 0.5
) -> list[int]:
    """Scan inner1 ± window for i32 fields advancing at ~44100 Hz.

    Two bulk mach reads separated by dt seconds (blocking ~dt s). Returns
    candidate inner ptrs (pos_field_addr − RB_POS_OFF) sorted by rate proximity
    to 44100 Hz.

    inner1 and inner2 are independent ObjC allocations — their relative offset
    is session-dependent. Observed: +0x4e0 (one session), -0x7570 (another).
    This scan handles any offset within ±window without pointer chasing.

    Keep dt ≤ 1 s so deck-1 cache stays within MEM_STALE_S = 3 s.
    """
    scan_lo = inner1 - window
    scan_hi = inner1 + window
    size    = scan_hi - scan_lo

    t_scan0 = time.monotonic()
    try:
        chunk0 = _read_bytes(task, scan_lo, size)
        t0     = time.monotonic()
    except OSError:
        return []

    time.sleep(dt)

    try:
        chunk1 = _read_bytes(task, scan_lo, size)
        t1     = time.monotonic()
    except OSError:
        return []

    actual_dt = max(t1 - t0, 0.001)
    scan_ms = (time.monotonic() - t_scan0) * 1000.0
    results: list[tuple[int, float]] = []
    n = len(chunk0) // 4

    for i in range(n):
        r0 = struct.unpack_from("<i", chunk0, i * 4)[0]
        r1 = struct.unpack_from("<i", chunk1, i * 4)[0]
        d  = r1 - r0
        if d <= 0:
            continue
        rate = d / actual_dt
        if not (_D2_RATE_LO <= rate <= _D2_RATE_HI):
            continue
        ms = max(0, int(r1 * RB_SCALE))
        if ms > MEM_MAX_ELAPSED_MS:
            continue
        pos_addr  = scan_lo + i * 4
        inner_ptr = pos_addr - RB_POS_OFF
        results.append((inner_ptr, rate))

    results.sort(key=lambda x: abs(x[1] - 44100))
    log.info("[RBMEM][SCAN] deck2 ObjC zone inner1±0x%x dt=%.2fs bytes=%d scan_ms=%.1f hits=%d",
             window, actual_dt, size * 2, scan_ms, len(results))
    for ptr, rate in results[:5]:
        pos_off = ptr - inner1 + RB_POS_OFF
        log.debug("[RBMEM][CANDIDATE] deck2 zone pos=inner1%+#x inner=inner1%+#x rate=%.1f",
                  pos_off, ptr - inner1, rate)
    return [ptr for ptr, _ in results]


def _scan_static_elapsed_candidates(
    task: int,
    inner1: int,
    target_ms: int,
    window: int,
    tolerance_ms: int = _D2_STATIC_TOL_MS,
) -> list[int]:
    """Find paused Deck-2 candidates by matching current timecode elapsed.

    This is intentionally weaker than movement validation. It only produces a
    provisional candidate for later strict promotion and should never be used as
    a final proof of Deck-2 memory position.
    """
    if target_ms <= 0:
        return []

    scan_lo = inner1 - window
    scan_hi = inner1 + window
    size    = scan_hi - scan_lo

    try:
        chunk = _read_bytes(task, scan_lo, size)
    except OSError:
        return []

    matches: list[tuple[int, int, int]] = []
    n = len(chunk) // 4
    for i in range(n):
        raw = struct.unpack_from("<i", chunk, i * 4)[0]
        if raw < 0:
            continue
        ms = int(raw * RB_SCALE)
        if ms > MEM_MAX_ELAPSED_MS:
            continue
        delta_ms = abs(ms - target_ms)
        if delta_ms > tolerance_ms:
            continue
        pos_addr = scan_lo + i * 4
        inner_ptr = pos_addr - RB_POS_OFF
        if inner_ptr & 0xF:
            continue
        if not _is_objc(inner_ptr):
            continue
        try:
            secondary = _read_u64(task, inner_ptr + RB_SEC_OFF)
        except OSError:
            continue
        if secondary and not _is_objc(secondary):
            continue
        matches.append((inner_ptr, delta_ms, ms))

    matches.sort(key=lambda x: x[1])
    log.info("[RBMEM][SCAN] deck2 static inner1±0x%x target=%dms hits=%d",
             window, target_ms, len(matches))
    for ptr, delta_ms, ms in matches[:5]:
        log.debug("[RBMEM][CANDIDATE] deck2 static pos=inner1%+#x inner=inner1%+#x ms=%d delta=%d",
                  ptr - inner1 + RB_POS_OFF, ptr - inner1, ms, delta_ms)

    if not matches:
        return []

    best_delta = matches[0][1]
    close = [m for m in matches if m[1] <= best_delta + _D2_STATIC_GAP_MS]
    if len(close) > 1:
        log.info("[RBMEM][INCONCLUSIVE] deck2 static scan ambiguous best_delta=%d close_hits=%d",
                 best_delta, len(close))
        return []

    return [matches[0][0]]


def _scan_objc_heap_moving(
    task: int,
    regions: list[tuple[int, int]],
    target_ms: int,
    dt: float = 0.5,
) -> list[int]:
    """Broad fallback scan over ObjC heap regions for moving Deck-2 fields.

    This is used only after near-inner1 scans fail. The target elapsed is a
    ranking/filter hint, not proof; candidates still need strict validation.
    """
    if target_ms <= 0 or not regions:
        return []

    t_scan0 = time.monotonic()
    hits: list[tuple[int, float, int]] = []
    chunks0: list[tuple[int, bytes, float]] = []
    bytes_queued = 0

    for start, size in regions:
        end = start + size
        addr = start
        while addr < end:
            chunk_size = min(_D2_HEAP_CHUNK_BYTES, end - addr)
            if bytes_queued >= _D2_HEAP_MAX_BYTES:
                break
            try:
                chunk0 = _read_bytes(task, addr, chunk_size)
                t0 = time.monotonic()
            except OSError:
                addr += chunk_size
                continue
            chunks0.append((addr, chunk0, t0))
            bytes_queued += len(chunk0)
            addr += chunk_size
        if bytes_queued >= _D2_HEAP_MAX_BYTES:
            break

    if not chunks0:
        log.info("[RBMEM][INCONCLUSIVE] deck2 heap moving scan no readable chunks")
        return []

    time.sleep(dt)

    for addr, chunk0, t0 in chunks0:
        try:
            chunk1 = _read_bytes(task, addr, len(chunk0))
            t1 = time.monotonic()
        except OSError:
            continue
        actual_dt = max(t1 - t0, 0.001)
        n = min(len(chunk0), len(chunk1)) // 4
        for i in range(n):
            r0 = struct.unpack_from("<i", chunk0, i * 4)[0]
            r1 = struct.unpack_from("<i", chunk1, i * 4)[0]
            d = r1 - r0
            if d <= 0:
                continue
            rate = d / actual_dt
            if not (_D2_RATE_LO <= rate <= _D2_RATE_HI):
                continue
            ms = int(r1 * RB_SCALE)
            if ms < 0 or ms > MEM_MAX_ELAPSED_MS:
                continue
            if abs(ms - target_ms) > _D2_HEAP_TARGET_TOL_MS:
                continue
            pos_addr = addr + i * 4
            inner_ptr = pos_addr - RB_POS_OFF
            if inner_ptr & 0xF:
                continue
            if not _is_objc(inner_ptr):
                continue
            try:
                secondary = _read_u64(task, inner_ptr + RB_SEC_OFF)
            except OSError:
                continue
            if secondary and not _is_objc(secondary):
                continue
            hits.append((inner_ptr, rate, abs(ms - target_ms)))

    seen: set[int] = set()
    deduped: list[tuple[int, float, int]] = []
    for ptr, rate, delta_ms in sorted(hits, key=lambda x: (x[2], abs(x[1] - 44100))):
        if ptr in seen:
            continue
        seen.add(ptr)
        deduped.append((ptr, rate, delta_ms))
        if len(deduped) >= _D2_HEAP_MAX_CANDIDATES:
            break

    scan_ms = (time.monotonic() - t_scan0) * 1000.0
    log.info("[RBMEM][SCAN] deck2 heap moving regions=%d chunks=%d bytes=%d target=%dms hits=%d scan_ms=%.1f",
             len(regions), len(chunks0), bytes_queued, target_ms, len(deduped), scan_ms)
    for ptr, rate, delta_ms in deduped[:5]:
        log.debug("[RBMEM][CANDIDATE] deck2 heap inner=0x%x rate=%.1f target_delta=%d",
                  ptr, rate, delta_ms)
    return [ptr for ptr, _, _ in deduped]


def _strict_eval_candidate(
    samples: list[tuple[float, int]],
    ptr: int,
) -> Optional[bool]:
    """Evaluate a candidate inner ptr from accumulated (time, raw) samples.

    Returns:
      True  — passes strict validation (playing at 44.1 kHz, no jumps)
      False — definitively wrong (bad rate, negative jump, or out-of-range)
      None  — inconclusive (not enough movement — deck may be paused)
    """
    if len(samples) < 4:
        return None

    raws = [r for _, r in samples]
    total_d  = raws[-1] - raws[0]
    total_dt = samples[-1][0] - samples[0][0]

    if total_dt <= 0:
        return None

    # Not moving — paused or no track loaded
    if abs(total_d) < 500:
        return None

    rate = total_d / total_dt

    neg_jumps = sum(1 for i in range(1, len(raws)) if raws[i] - raws[i - 1] < _D2_NEG_JUMP_THR)

    ms_end = max(0, int(raws[-1] * RB_SCALE))

    if neg_jumps > 0:
        log.debug("[RBMEM][REJECT] deck2 candidate=0x%x neg_jumps=%d rate=%.0f ms=%d",
                  ptr, neg_jumps, rate, ms_end)
        return False

    if not (_D2_RATE_LO <= rate <= _D2_RATE_HI):
        log.debug("[RBMEM][REJECT] deck2 candidate=0x%x rate=%.0f need=%d-%d ms=%d",
                  ptr, rate, _D2_RATE_LO, _D2_RATE_HI, ms_end)
        return False

    if ms_end > MEM_MAX_ELAPSED_MS:
        log.debug("[RBMEM][REJECT] deck2 candidate=0x%x ms=%d out_of_range", ptr, ms_end)
        return False

    log.info("[RBMEM][VALIDATED] deck2 candidate=0x%x rate=%.0f samples=%d ms=%d",
             ptr, rate, len(samples), ms_end)
    return True


# ── RB memory session ────────────────────────────────────────────────────────

class RBSession:
    """One attached session to a running rekordbox process.

    Deck 1: base+RB_GLOBAL_OFF → container → container+0x478 → DPU1 → inner1 → +0x0C
    Deck 2: independently resolved via three ordered candidates (A/B/C).
            Validation is non-blocking — samples accumulate across poll ticks.
    """

    def __init__(self, pid: int, base: int, task: int, offsets: Optional[RBOffsetVersion] = None):
        self.pid  = pid
        self.base = base
        self.task = task
        self.offsets = offsets

        # ── Deck 1 ──────────────────────────────────────────────────────────
        self._container: Optional[int] = None
        self._dpu1:      Optional[int] = None
        self._inner1:    Optional[int] = None   # cached deck-1 inner ptr

        # ── Deck 2 ──────────────────────────────────────────────────────────
        self._deck2_inner:      Optional[int] = None
        self._deck2_provisional: Optional[int] = None
        self._deck2_fail_count: int = 0

        # Incremental validation state (populated by start_deck2_resolution,
        # sampled by poll_deck2_candidates, consumed by _eval_deck2_candidates)
        self._d2_pending:     list[int] = []                          # candidate inner ptrs
        self._d2_samples:     dict[int, list[tuple[float, int]]] = {} # ptr → [(t, raw)]
        self._d2_eval_after:  float = 0.0   # monotonic time when sampling window closes
        self._d2_sample_next: float = 0.0   # next time to take a sample

        # Offset-table live-position chain state. This is enabled only by
        # RBSS_POS_CHAIN_DIRECT=1 and feeds PositionCache alongside the ObjC
        # scanner, with chain values taking priority when valid.
        self._chain_last_raw: dict[int, int] = {}
        self._chain_valid_count: dict[int, int] = {}
        self._chain_unreadable_logged: set[int] = set()

    # ── Container / DPU1 / inner1 ────────────────────────────────────────────

    def _get_container(self) -> int:
        if self._container is None:
            self._container = _read_u64(self.task, self.base + RB_GLOBAL_OFF)
        return self._container

    def _get_inner1(self) -> Optional[int]:
        """Return deck-1 inner ptr, resolving and caching on first call."""
        if self._inner1:
            return self._inner1
        try:
            container = self._get_container()
            if not container:
                self._container = None
                return None
            dpu1 = _read_u64(self.task, container + RB_DECK1_OFF)
            if not dpu1:
                return None
            self._dpu1 = dpu1
            inner1 = _read_u64(self.task, dpu1 + RB_INNER_OFF)
            if not inner1:
                return None
            self._inner1 = inner1
            return inner1
        except OSError:
            return None

    # ── Shared inner read ────────────────────────────────────────────────────

    def _read_inner(self, inner: int, bridge_deck: int) -> PositionSnapshot:
        """Read position + play state from a validated inner ptr.

        May raise OSError — callers catch it.
        """
        raw_pos = _read_i32(self.task, inner + RB_POS_OFF)
        elapsed_ms = max(0, int(raw_pos * RB_SCALE))
        if elapsed_ms > MEM_MAX_ELAPSED_MS:
            elapsed_ms = 0

        inner_u64 = _read_u64(self.task, inner + RB_INNER_LEN_OFF)
        len_samples = inner_u64 >> 32
        track_length_ms = int(len_samples * RB_SCALE) if len_samples > 0 else 0
        # Validated Deck-2 inners are discovered by the +0x0c position field.
        # Their surrounding layout is not proven to match Deck 1; +0x08 has
        # been observed to mirror live position, not track length. Keep Deck 2
        # length unknown so filepath resolution uses ANLZ/title fallbacks
        # instead of a bogus duration match.
        if bridge_deck == 2:
            track_length_ms = 0

        secondary = _read_u64(self.task, inner + RB_SEC_OFF)
        if secondary == 0:
            return PositionSnapshot(
                deck=bridge_deck,
                elapsed_ms=elapsed_ms,
                track_length_ms=track_length_ms,
                updated_at=time.monotonic(),
            )
        play_i32 = _read_i32(self.task, secondary + RB_PLAY_OFF)
        ddj_byte  = _read_u8(self.task, secondary + RB_DDJ_OFF)
        return PositionSnapshot(
            deck=bridge_deck,
            elapsed_ms=elapsed_ms,
            playing=(play_i32 < 0),
            track_length_ms=track_length_ms,
            ddj_mode=(ddj_byte != 0),
            updated_at=time.monotonic(),
        )

    # ── Offset-table live-position chain ────────────────────────────────────

    def _follow_chain_addr(self, ch: ChainEntry) -> Optional[int]:
        addr = self.base
        for hop in ch.hops:
            try:
                addr = _read_u64(self.task, addr + hop)
            except OSError:
                return None
            if addr == 0:
                return None
        return addr + ch.final_off

    def _read_chain_i64(self, ch: ChainEntry) -> Optional[int]:
        addr = self._follow_chain_addr(ch)
        if addr is None:
            return None
        try:
            return struct.unpack_from("<q", _read_bytes(self.task, addr, 8))[0]
        except OSError:
            return None

    def read_live_pos_chain(
        self,
        bridge_deck: int,
        previous: Optional[PositionSnapshot] = None,
    ) -> Optional[PositionSnapshot]:
        """Read a validated live_pos_per_deck chain as a PositionSnapshot."""
        if self.offsets is None:
            return None
        rb_idx = bridge_deck - 1
        if rb_idx < 0 or rb_idx >= len(self.offsets.live_pos_per_deck):
            return None

        raw = self._read_chain_i64(self.offsets.live_pos_per_deck[rb_idx])
        if raw is None:
            if bridge_deck not in self._chain_unreadable_logged:
                self._chain_unreadable_logged.add(bridge_deck)
                log.info("[RBMEM][CHAIN] deck=%d unreadable; using ObjC scan fallback", bridge_deck)
            return None
        self._chain_unreadable_logged.discard(bridge_deck)
        if raw < 0:
            log.info("[RBMEM][INVALID] deck=%d chain negative raw=%d", bridge_deck, raw)
            return None

        prev_raw = self._chain_last_raw.get(bridge_deck)
        if prev_raw is not None and raw < prev_raw:
            delta = raw - prev_raw
            if delta < -_CHAIN_BACKWARD_THR_SAMPLES and raw >= _CHAIN_RESET_SAMPLES:
                log.debug("[RBMEM] deck=%d chain backward_jump samples=%d prev=%d raw=%d (rewind)",
                          bridge_deck, delta, prev_raw, raw)
                self._chain_last_raw[bridge_deck] = raw  # reset baseline so chain recovers after rewind
                return None

        elapsed_ms = int(raw * RB_SCALE)
        if elapsed_ms > MEM_MAX_ELAPSED_MS:
            log.info("[RBMEM][INVALID] deck=%d chain elapsed_ms=%d out_of_range",
                     bridge_deck, elapsed_ms)
            return None

        playing = bool(previous.playing) if previous is not None else False
        if prev_raw is not None:
            playing = raw != prev_raw
        self._chain_last_raw[bridge_deck] = raw
        self._chain_valid_count[bridge_deck] = self._chain_valid_count.get(bridge_deck, 0) + 1

        track_length_ms = previous.track_length_ms if previous is not None else 0
        ddj_mode = previous.ddj_mode if previous is not None else False
        return PositionSnapshot(
            deck=bridge_deck,
            elapsed_ms=max(0, elapsed_ms),
            playing=playing,
            track_length_ms=track_length_ms,
            ddj_mode=ddj_mode,
            updated_at=time.monotonic(),
        )

    # ── Deck 2 resolution ────────────────────────────────────────────────────

    def start_deck2_resolution(
        self,
        objc_regions: list[tuple[int, int]],
        target_ms: Optional[int] = None,
        scan_window: int = 0x10000,
        attempt: int = 1,
        deck2_playing: bool = False,
    ) -> bool:
        """Find deck-2 inner candidates and open a 4-second sampling window.

        Candidate order:
          P. previously discovered provisional candidate, if any
          B. (container − OUTER_FAST_PATH_DELTA)[+OUTER_INNER2_OFF] → ptr
             Quick structural check — no sleep, often wrong but cheap.
          C. ObjC zone scan: two bulk reads around inner1 separated by 0.5s.
             Primary method. Finds any field advancing at ~44100 Hz regardless of
             the inner1/inner2 relative offset (proven session-dependent).
          S. paused/static scan: if target_ms is available, find one unique field
             near current timecode elapsed and hold it as provisional only.
          D. ObjC heap moving scan: after repeated near-inner1 failures while
             Deck 2 is playing, scan vmmap-derived ObjC heap regions for moving
             fields near target_ms.

        Blocks ~0.5s for the zone scan. Returns True if candidates were found.
        Temporal validation (neg-jump detection) happens incrementally in
        poll_deck2_candidates() over the following 4 seconds.
        """
        inner1 = self._get_inner1()
        candidates: list[int] = []
        seen: set[int] = set()
        stage_ms: dict[str, float] = {"B": 0.0, "C": 0.0, "S": 0.0, "D": 0.0}
        stage_counts: dict[str, int] = {"P": 0, "B": 0, "C": 0, "S": 0, "D": 0}
        t_attempt0 = time.monotonic()

        def _add(ptr: int, label: str) -> None:
            if ptr and ptr not in seen and _quick_plausible_inner(self.task, ptr):
                candidates.append(ptr)
                seen.add(ptr)
                log.debug("[RBMEM][CANDIDATE] deck2 %s inner=0x%x", label, ptr)

        if self._deck2_provisional:
            stage_counts["P"] += 1
            _add(self._deck2_provisional, "P(provisional)")

        # B: (container − 0x270)[+0x78] → ptr (quick, no sleep)
        t0 = time.monotonic()
        try:
            container = self._get_container()
            ptr_b     = _read_u64(self.task, container - OUTER_FAST_PATH_DELTA + OUTER_INNER2_OFF)
            if ptr_b != inner1:
                stage_counts["B"] += 1
                _add(ptr_b, "B(container-0x%x+0x%x)" % (OUTER_FAST_PATH_DELTA, OUTER_INNER2_OFF))
        except OSError:
            pass
        stage_ms["B"] = (time.monotonic() - t0) * 1000.0

        # C: ObjC zone scan — two reads 0.5s apart, finds position field directly.
        # inner1/inner2 offset is session-dependent; the caller can widen the
        # scan after repeated failures without hardcoding a relative offset.
        if inner1:
            t0 = time.monotonic()
            zone_hits = _scan_objc_zone(self.task, inner1, window=scan_window)
            stage_ms["C"] = (time.monotonic() - t0) * 1000.0
            for ptr in zone_hits:
                if ptr != inner1 and ptr not in seen:
                    candidates.append(ptr)
                    seen.add(ptr)
                    stage_counts["C"] += 1
                    log.debug("[RBMEM][CANDIDATE] deck2 C(zone) inner=0x%x", ptr)

            if target_ms is not None and not zone_hits and not self._deck2_provisional:
                t0 = time.monotonic()
                static_hits = _scan_static_elapsed_candidates(
                    self.task, inner1, target_ms, window=scan_window
                )
                stage_ms["S"] = (time.monotonic() - t0) * 1000.0
                if len(static_hits) == 1:
                    ptr = static_hits[0]
                    if ptr != inner1 and ptr not in seen:
                        self._deck2_provisional = ptr
                        candidates.append(ptr)
                        seen.add(ptr)
                        stage_counts["S"] += 1
                        log.info(
                            "[RBMEM][PENDING] deck2 provisional=0x%x target_ms=%d awaiting movement validation",
                            ptr, target_ms,
                        )

            if (
                target_ms is not None
                and not zone_hits
                and attempt >= _D2_HEAP_SCAN_MIN_ATTEMPT
                and deck2_playing
            ):
                t0 = time.monotonic()
                heap_hits = _scan_objc_heap_moving(self.task, objc_regions, target_ms)
                stage_ms["D"] = (time.monotonic() - t0) * 1000.0
                for ptr in heap_hits:
                    if ptr != inner1 and ptr not in seen:
                        candidates.append(ptr)
                        seen.add(ptr)
                        stage_counts["D"] += 1
                        log.debug("[RBMEM][CANDIDATE] deck2 D(heap) inner=0x%x", ptr)

        attempt_ms = (time.monotonic() - t_attempt0) * 1000.0
        log.info(
            "[RBMEM][D2ATTEMPT] attempt=%d window=0x%x target_ms=%s playing_recent=%s "
            "candidates=%d P=%d B=%d C=%d S=%d D=%d stage_ms(B=%.1f C=%.1f S=%.1f D=%.1f) attempt_ms=%.1f",
            attempt,
            scan_window,
            target_ms if target_ms is not None else "none",
            deck2_playing,
            len(candidates),
            stage_counts["P"],
            stage_counts["B"],
            stage_counts["C"],
            stage_counts["S"],
            stage_counts["D"],
            stage_ms["B"],
            stage_ms["C"],
            stage_ms["S"],
            stage_ms["D"],
            attempt_ms,
        )
        log.info("[RBMEM][SCAN] deck2 resolution candidates=%d window=4s", len(candidates))
        if not candidates:
            return False

        now = time.monotonic()
        self._d2_pending     = candidates
        self._d2_samples     = {ptr: [] for ptr in candidates}
        self._d2_eval_after  = now + _D2_VALIDATE_DT
        self._d2_sample_next = now
        return True

    def poll_deck2_candidates(self, now: float) -> None:
        """Sample all pending deck-2 candidates. Call each poll tick.

        When the sampling window closes, evaluates candidates and sets
        self._deck2_inner if one passes strict validation.
        """
        if not self._d2_pending:
            return

        if now >= self._d2_sample_next:
            self._d2_sample_next = now + (1.0 / _D2_SAMPLE_HZ)
            for ptr in self._d2_pending:
                try:
                    raw = _read_i32(self.task, ptr + RB_POS_OFF)
                    self._d2_samples[ptr].append((now, raw))
                except OSError:
                    pass

        if now >= self._d2_eval_after:
            self._eval_deck2_candidates()

    def _eval_deck2_candidates(self) -> None:
        """Evaluate accumulated samples for all pending candidates.

        Commits the first candidate that passes strict criteria.
        Defers (leaves _deck2_inner=None) if no deck is playing yet.
        """
        all_inconclusive = True
        committed = False

        for ptr in self._d2_pending:
            result = _strict_eval_candidate(self._d2_samples.get(ptr, []), ptr)
            if result is True:
                self._deck2_inner     = ptr
                if self._deck2_provisional == ptr:
                    log.info("[RBMEM][VALIDATED] deck2 provisional promoted inner=0x%x", ptr)
                self._deck2_provisional = None
                self._deck2_fail_count = 0
                log.info("[RBMEM][VALIDATED] deck2 inner committed=0x%x", ptr)
                committed = True
                break
            if result is False:
                if self._deck2_provisional == ptr:
                    log.debug("[RBMEM][REJECT] deck2 provisional rejected inner=0x%x", ptr)
                    self._deck2_provisional = None
                all_inconclusive = False

        self._d2_pending.clear()
        self._d2_samples.clear()
        self._d2_eval_after  = 0.0
        self._d2_sample_next = 0.0

        if not committed:
            if all_inconclusive:
                log.debug("[RBMEM][INCONCLUSIVE] deck2 all candidates inconclusive (deck likely paused)")
            else:
                log.info("[RBMEM][INVALID] deck=2 all candidates failed strict validation; retrying")

    # ── Runtime reads ────────────────────────────────────────────────────────

    def read_deck(self, bridge_deck: int) -> Optional[PositionSnapshot]:
        """Read position + play state for bridge_deck (1 or 2).

        Deck 1: container → DPU1 → inner1 (proven reliable).
        Deck 2: validated deck2_inner (None -> caller falls back to timecode).
        Returns None if data unavailable.
        """
        if bridge_deck == 1:
            try:
                inner1 = self._get_inner1()
                if inner1 is None:
                    return None
                return self._read_inner(inner1, 1)
            except OSError:
                self._inner1 = None   # invalidate cache on read failure
                return None

        # Deck 2
        if self._deck2_inner is None:
            return None
        try:
            snap = self._read_inner(self._deck2_inner, 2)
            self._deck2_fail_count = 0
            return snap
        except OSError:
            self._deck2_fail_count += 1
            if self._deck2_fail_count >= 3:
                log.warning("[RBMEM][INVALID] deck2 read_failures=%d invalidating",
                            self._deck2_fail_count)
                self._deck2_inner      = None
                self._deck2_fail_count = 0
            return None


# ── Thread-safe position cache ───────────────────────────────────────────────

class PositionCache:
    """Thread-safe store for the latest PositionSnapshot per deck.

    The lock is held for ~1 µs per access. No contention in practice.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snaps: dict[int, PositionSnapshot] = {}

    def update(self, snap: PositionSnapshot) -> None:
        with self._lock:
            self._snaps[snap.deck] = snap

    def get(self, deck: int) -> Optional[PositionSnapshot]:
        with self._lock:
            return self._snaps.get(deck)

    def clear(self) -> None:
        with self._lock:
            self._snaps.clear()


# ── Memory reader thread ─────────────────────────────────────────────────────

class RBMemoryReader(threading.Thread):
    """Polls RB memory at MEM_POLL_HZ and writes to PositionCache.

    Handles RB restarts: detects when the PID is gone and re-attaches automatically.
    vmmap is only called on attach (expensive); subsequent reads use the cached session.
    """

    _ATTACH_RETRY_S  = 5.0
    _VMMAP_TIMEOUT_S = 15.0

    def __init__(
        self,
        cache: PositionCache,
        drift_detector=None,
        event_queue=None,
        deck_elapsed_hint: Optional[Callable[[int], Optional[int]]] = None,
        deck_playing_hint: Optional[Callable[[int], bool]] = None,
        rb_version: str = "",
    ) -> None:
        super().__init__(name="rb-memory-reader", daemon=True)
        self._cache    = cache
        self._drift    = drift_detector    # optional DriftDetector
        self._eq       = event_queue       # FM-11: optional queue for RB_RESTARTED events
        self._deck_elapsed_hint = deck_elapsed_hint
        self._deck_playing_hint = deck_playing_hint
        self._pos_chain_direct = os.environ.get(POS_CHAIN_DIRECT_ENV) == "1"
        self._offsets = load_offsets_for_version(rb_version) if self._pos_chain_direct and rb_version else None
        # Skip-ObjC optimization is only meaningful when the chain path is the
        # authoritative writer (chain mode on + offsets resolved).
        self._skip_objc_when_chain = (
            os.environ.get(POS_CHAIN_SKIP_OBJC_ENV) == "1"
            and self._pos_chain_direct
            and self._offsets is not None
        )
        self._chain_ok_last: dict[int, bool] = {1: False, 2: False}
        self._length_refresh_at: float = 0.0
        self._stop     = threading.Event()
        self._session: Optional[RBSession] = None
        self._interval = 1.0 / MEM_POLL_HZ
        self._attach_time   = 0.0
        self._last_dpu_log  = 0.0
        self._objc_regions: list[tuple[int, int]] = []   # cached from last vmmap run
        self._d2_retry_at:  float = 0.0                  # rate-limit deck-2 resolution retries
        self._d2_attempts:   int = 0
        self._d2_was_playing: bool = False
        self._d2_play_seen_at: float = 0.0
        # Measurement-only: time to committed deck-2 inner.
        self._d2_unresolved_since: float = 0.0
        self._d2_last_committed_inner: Optional[int] = None

    def stop(self) -> None:
        self._stop.set()

    def get_session(self) -> Optional[RBSession]:
        return self._session

    def run(self) -> None:
        log.info("[RBMEM][STATUS] reader starting hz=%d", MEM_POLL_HZ)
        if self._pos_chain_direct:
            if self._offsets is None:
                log.warning("[RBMEM][CHAIN] enabled via %s=1 but offset table unavailable; using ObjC scan only",
                            POS_CHAIN_DIRECT_ENV)
            else:
                log.info("[RBMEM][CHAIN] enabled via %s=1 version=%s",
                         POS_CHAIN_DIRECT_ENV, self._offsets.version)
        while not self._stop.is_set():
            t0 = time.monotonic()
            self._tick()
            remaining = self._interval - (time.monotonic() - t0)
            if remaining > 0:
                time.sleep(remaining)

    def _tick(self) -> None:
        if self._session is None:
            self._try_attach()
            return
        # Liveness check (cheap)
        try:
            import os as _os
            _os.kill(self._session.pid, 0)
        except (OSError, ProcessLookupError):
            log.warning("[RBMEM][INVALID] rekordbox pid=%d gone; detaching", self._session.pid)
            old_pid = self._session.pid
            self._session = None
            self._cache.clear()
            # FM-11: notify StateManager so it can force-stop active shows
            if self._eq is not None:
                try:
                    from .models import BridgeEvent, Ev
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.RB_RESTARTED,
                        deck=0,
                        payload={"pid": old_pid},
                        source="memory",
                    ))
                except Exception:
                    pass
            return

        now_t = time.monotonic()
        s = self._session
        if s is not None and s._deck2_inner is None and self._d2_unresolved_since <= 0.0:
            self._d2_unresolved_since = now_t
        deck2_playing = False
        if self._deck_playing_hint is not None:
            try:
                deck2_playing = bool(self._deck_playing_hint(2))
            except Exception:
                deck2_playing = False
        d2_play_started = deck2_playing and not self._d2_was_playing
        self._d2_was_playing = deck2_playing
        if deck2_playing:
            self._d2_play_seen_at = now_t
        deck2_recently_playing = (
            self._d2_play_seen_at > 0.0
            and now_t - self._d2_play_seen_at < _D2_PLAY_RECENT_S
        )

        # When the deck-2 live_pos chain was healthy last tick, the ObjC deck-2
        # inner is never read (the chain supplies deck-2 position), so skip the
        # whole resolution pipeline — including its periodic blocking zone scans.
        # Falls back automatically the moment the chain misses a tick.
        skip2 = self._skip_objc_when_chain and self._chain_ok_last.get(2, False)

        # Drive deck-2 resolution pipeline (non-blocking).
        if not skip2 and s._deck2_inner is None:
            if s._d2_pending:
                # Mid-validation: take samples this tick.
                s.poll_deck2_candidates(now_t)
            else:
                if d2_play_started:
                    log.info("[RBMEM][SCAN] deck2 play trigger; starting resolution")
                retry_s = (
                    _D2_PROVISIONAL_RETRY_S if s._deck2_provisional
                    else _D2_RETRY_PLAYING_S if deck2_playing
                    else _D2_RETRY_IDLE_S
                )
                if d2_play_started or now_t - self._d2_retry_at >= retry_s:
                    # No active window and retry interval elapsed — start a new attempt.
                    self._d2_retry_at = now_t
                    self._d2_attempts += 1
                    scan_window = _D2_SCAN_WINDOWS[
                        min(self._d2_attempts - 1, len(_D2_SCAN_WINDOWS) - 1)
                    ]
                    target_ms = None
                    if self._deck_elapsed_hint is not None:
                        try:
                            target_ms = self._deck_elapsed_hint(2)
                        except Exception:
                            target_ms = None
                    log.info(
                        "[RBMEM][SCAN] deck2 attempt=%d window=0x%x target_ms=%s "
                        "playing=%s recently_playing=%s provisional=%s",
                        self._d2_attempts, scan_window,
                        target_ms if target_ms is not None else "none",
                        deck2_playing, deck2_recently_playing, bool(s._deck2_provisional),
                    )
                    s.start_deck2_resolution(
                        self._objc_regions,
                        target_ms=target_ms,
                        scan_window=scan_window,
                        attempt=self._d2_attempts,
                        deck2_playing=deck2_recently_playing,
                    )
        elif not skip2 and s._d2_pending:
            # Deck 2 got committed mid-window; discard leftover pending state.
            s._d2_pending.clear()
            s._d2_samples.clear()
            self._d2_attempts = 0
        if not skip2 and s._deck2_inner is not None and s._deck2_inner != self._d2_last_committed_inner:
            self._d2_last_committed_inner = s._deck2_inner
            if self._d2_unresolved_since > 0.0:
                ttc_ms = (now_t - self._d2_unresolved_since) * 1000.0
                log.info(
                    "[RBMEM][D2COMMIT] inner=0x%x ttc_ms=%.0f attempts=%d",
                    s._deck2_inner,
                    ttc_ms,
                    self._d2_attempts,
                )
            self._d2_unresolved_since = 0.0

        if self._skip_objc_when_chain:
            self._read_decks_chain_first(s, now_t)
            return

        for deck in (1, 2):
            snap = s.read_deck(deck)
            if snap is not None:
                self._cache.update(snap)
                if self._drift is not None:
                    warn = self._drift.update(deck, snap.elapsed_ms, snap.playing)
                    if warn:
                        log.warning("drift deck=%d: %s", deck, warn)
            if self._pos_chain_direct and self._offsets is not None:
                previous = self._cache.get(deck)
                chain_snap = s.read_live_pos_chain(deck, previous)
                if chain_snap is not None:
                    self._cache.update(chain_snap)
                    if self._drift is not None:
                        warn = self._drift.update(deck, chain_snap.elapsed_ms, chain_snap.playing)
                        if warn:
                            log.warning("drift deck=%d: %s", deck, warn)

    def _publish_chain(self, deck: int, chain_snap: PositionSnapshot) -> None:
        self._cache.update(chain_snap)
        if self._drift is not None:
            warn = self._drift.update(deck, chain_snap.elapsed_ms, chain_snap.playing)
            if warn:
                log.warning("drift deck=%d: %s", deck, warn)

    def _read_decks_chain_first(self, s: "RBSession", now_t: float) -> None:
        """Skip-ObjC path: chain is authoritative; read_deck only as fallback.

        For each deck, read the live_pos chain first. When it is valid we publish
        it and skip the redundant ObjC read_deck() — except for a slow-cadence
        deck-1 read used solely to keep track_length_ms fresh (the chain cannot
        read length). When the chain misses a tick, fall back to read_deck() so
        position never goes dark.
        """
        for deck in (1, 2):
            previous = self._cache.get(deck)
            chain_snap = s.read_live_pos_chain(deck, previous)
            chain_ok = chain_snap is not None
            self._chain_ok_last[deck] = chain_ok
            if chain_ok:
                self._publish_chain(deck, chain_snap)
                if deck == 1 and now_t - self._length_refresh_at >= _LENGTH_REFRESH_INTERVAL_S:
                    self._refresh_deck1_length(s, now_t)
                continue
            # Chain unavailable this tick — ObjC fallback (also re-seeds length).
            snap = s.read_deck(deck)
            if snap is not None:
                self._cache.update(snap)
                if self._drift is not None:
                    warn = self._drift.update(deck, snap.elapsed_ms, snap.playing)
                    if warn:
                        log.warning("drift deck=%d: %s", deck, warn)

    def _refresh_deck1_length(self, s: "RBSession", now_t: float) -> None:
        """Refresh deck-1 track_length_ms without disturbing chain position.

        read_deck(1) is the only producer of track_length_ms; the chain carries
        the last known length forward. Merge a changed length into the current
        (chain-authoritative) cache snapshot, leaving elapsed/playing/updated_at
        untouched.
        """
        self._length_refresh_at = now_t
        snap = s.read_deck(1)
        if snap is None or snap.track_length_ms <= 0:
            return
        cur = self._cache.get(1)
        if cur is None:
            self._cache.update(snap)
        elif cur.track_length_ms != snap.track_length_ms:
            self._cache.update(replace(cur, track_length_ms=snap.track_length_ms))

    def _try_attach(self) -> None:
        pid = get_rb_pid()
        if pid is None:
            time.sleep(self._ATTACH_RETRY_S)
            return
        try:
            t0 = time.monotonic()
            vmmap_out = _get_vmmap_output(pid)
            vmmap_ms = (time.monotonic() - t0) * 1000.0
            base      = _base_from_vmmap(vmmap_out)
            self._objc_regions = _objc_regions_from_vmmap(vmmap_out)
            t1 = time.monotonic()
            task = _task_for_pid(pid)
            task_ms = (time.monotonic() - t1) * 1000.0
            self._session     = RBSession(pid, base, task, offsets=self._offsets)
            self._attach_time = time.monotonic()
            self._d2_retry_at = 0.0   # allow immediate deck-2 resolution on first tick
            self._d2_attempts = 0
            self._d2_was_playing = False
            self._d2_play_seen_at = 0.0
            self._d2_unresolved_since = 0.0
            self._d2_last_committed_inner = None
            log.info(
                "[RBMEM][ATTACH] attached pid=%d base=0x%x objc_regions=%d vmmap_ms=%.1f task_ms=%.1f",
                pid,
                base,
                len(self._objc_regions),
                vmmap_ms,
                task_ms,
            )
        except Exception as exc:
            log.warning("[RBMEM][ERROR] attach failed pid=%d error=%s retry_s=%d",
                        pid, exc, int(self._ATTACH_RETRY_S))
            time.sleep(self._ATTACH_RETRY_S)
