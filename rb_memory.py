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
import re
import struct
import subprocess
import threading
import time
from typing import Optional

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

log = logging.getLogger("rb_memory")

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
        m = re.match(r'\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)', line)
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
    log.info("ObjC zone scan inner1±0x%x (dt=%.2fs): %d hit(s)",
             window, actual_dt, len(results))
    for ptr, rate in results[:5]:
        pos_off = ptr - inner1 + RB_POS_OFF
        log.info("  pos=inner1%+#x  inner_ptr=inner1%+#x  rate=%.1f",
                 pos_off, ptr - inner1, rate)
    return [ptr for ptr, _ in results]


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
        log.info("deck2 candidate 0x%x REJECT: neg_jumps=%d rate=%.0f ms=%d",
                 ptr, neg_jumps, rate, ms_end)
        return False

    if not (_D2_RATE_LO <= rate <= _D2_RATE_HI):
        log.info("deck2 candidate 0x%x REJECT: rate=%.0f (need %d–%d) ms=%d",
                 ptr, rate, _D2_RATE_LO, _D2_RATE_HI, ms_end)
        return False

    if ms_end > MEM_MAX_ELAPSED_MS:
        log.info("deck2 candidate 0x%x REJECT: ms=%d out of range", ptr, ms_end)
        return False

    log.info("deck2 candidate 0x%x PASS: rate=%.0f samples=%d ms=%d",
             ptr, rate, len(samples), ms_end)
    return True


# ── RB memory session ────────────────────────────────────────────────────────

class RBSession:
    """One attached session to a running rekordbox process.

    Deck 1: base+RB_GLOBAL_OFF → container → container+0x478 → DPU1 → inner1 → +0x0C
    Deck 2: independently resolved via three ordered candidates (A/B/C).
            Validation is non-blocking — samples accumulate across poll ticks.
    """

    def __init__(self, pid: int, base: int, task: int):
        self.pid  = pid
        self.base = base
        self.task = task

        # ── Deck 1 ──────────────────────────────────────────────────────────
        self._container: Optional[int] = None
        self._dpu1:      Optional[int] = None
        self._inner1:    Optional[int] = None   # cached deck-1 inner ptr

        # ── Deck 2 ──────────────────────────────────────────────────────────
        self._deck2_inner:      Optional[int] = None
        self._deck2_fail_count: int = 0

        # Incremental validation state (populated by start_deck2_resolution,
        # sampled by poll_deck2_candidates, consumed by _eval_deck2_candidates)
        self._d2_pending:     list[int] = []                          # candidate inner ptrs
        self._d2_samples:     dict[int, list[tuple[float, int]]] = {} # ptr → [(t, raw)]
        self._d2_eval_after:  float = 0.0   # monotonic time when sampling window closes
        self._d2_sample_next: float = 0.0   # next time to take a sample

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
        inner_u64 = _read_u64(self.task, inner + RB_INNER_LEN_OFF)
        len_samples = inner_u64 >> 32
        track_length_ms = int(len_samples * RB_SCALE) if len_samples > 0 else 0

        raw_pos = _read_i32(self.task, inner + RB_POS_OFF)
        elapsed_ms = max(0, int(raw_pos * RB_SCALE))
        if elapsed_ms > MEM_MAX_ELAPSED_MS:
            elapsed_ms = 0

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

    # ── Deck 2 resolution ────────────────────────────────────────────────────

    def start_deck2_resolution(self, scan_regions: list[tuple[int, int]]) -> bool:
        """Find deck-2 inner candidates and open a 4-second sampling window.

        Candidate order:
          B. (container − OUTER_FAST_PATH_DELTA)[+OUTER_INNER2_OFF] → ptr
             Quick structural check — no sleep, often wrong but cheap.
          C. ObjC zone scan: two bulk reads of inner1±0x10000 separated by 0.5s.
             Primary method. Finds any field advancing at ~44100 Hz regardless of
             the inner1/inner2 relative offset (proven session-dependent).

        Blocks ~0.5s for the zone scan. Returns True if candidates were found.
        Temporal validation (neg-jump detection) happens incrementally in
        poll_deck2_candidates() over the following 4 seconds.
        """
        inner1 = self._get_inner1()
        candidates: list[int] = []
        seen: set[int] = set()

        def _add(ptr: int, label: str) -> None:
            if ptr and ptr not in seen and _quick_plausible_inner(self.task, ptr):
                candidates.append(ptr)
                seen.add(ptr)
                log.info("deck2 candidate %s: 0x%x", label, ptr)

        # B: (container − 0x270)[+0x78] → ptr (quick, no sleep)
        try:
            container = self._get_container()
            ptr_b     = _read_u64(self.task, container - OUTER_FAST_PATH_DELTA + OUTER_INNER2_OFF)
            if ptr_b != inner1:
                _add(ptr_b, "B(container-0x%x+0x%x)" % (OUTER_FAST_PATH_DELTA, OUTER_INNER2_OFF))
        except OSError:
            pass

        # C: ObjC zone scan — two reads 0.5s apart, finds position field directly.
        # inner1/inner2 offset is session-dependent; this handles any offset in ±0x10000.
        if inner1:
            zone_hits = _scan_objc_zone(self.task, inner1)
            for ptr in zone_hits:
                if ptr != inner1 and ptr not in seen:
                    candidates.append(ptr)
                    seen.add(ptr)
                    log.info("deck2 candidate C(zone): 0x%x", ptr)

        log.info("deck2 resolution: %d candidate(s) entering 4s validation window",
                 len(candidates))
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
                self._deck2_fail_count = 0
                log.info("deck2 inner committed: 0x%x", ptr)
                committed = True
                break
            if result is False:
                all_inconclusive = False

        self._d2_pending.clear()
        self._d2_samples.clear()
        self._d2_eval_after  = 0.0
        self._d2_sample_next = 0.0

        if not committed:
            if all_inconclusive:
                log.info("deck2: validation inconclusive (deck paused?) — will retry in 30 s")
            else:
                log.warning("deck2: all candidates failed strict validation — will retry in 30 s")

    # ── Runtime reads ────────────────────────────────────────────────────────

    def read_deck(self, bridge_deck: int) -> Optional[PositionSnapshot]:
        """Read position + play state for bridge_deck (1 or 2).

        Deck 1: container → DPU1 → inner1 (proven reliable).
        Deck 2: validated deck2_inner (None → caller falls back to TL TC).
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
                log.warning("deck2: %d consecutive read failures — invalidating",
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

    def __init__(self, cache: PositionCache, drift_detector=None, event_queue=None) -> None:
        super().__init__(name="rb-memory-reader", daemon=True)
        self._cache    = cache
        self._drift    = drift_detector    # optional DriftDetector
        self._eq       = event_queue       # FM-11: optional queue for RB_RESTARTED events
        self._stop     = threading.Event()
        self._session: Optional[RBSession] = None
        self._interval = 1.0 / MEM_POLL_HZ
        self._attach_time   = 0.0
        self._last_dpu_log  = 0.0
        self._scan_regions: list[tuple[int, int]] = []   # cached from last vmmap run
        self._d2_retry_at:  float = 0.0                  # rate-limit deck-2 resolution retries

    def stop(self) -> None:
        self._stop.set()

    def get_session(self) -> Optional[RBSession]:
        return self._session

    def run(self) -> None:
        log.info("RBMemoryReader: starting at %d Hz", MEM_POLL_HZ)
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
            log.warning("RBMemoryReader: RB pid %d gone — detaching", self._session.pid)
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

        # Drive deck-2 resolution pipeline (non-blocking).
        if s._deck2_inner is None:
            if s._d2_pending:
                # Mid-validation: take samples this tick.
                s.poll_deck2_candidates(now_t)
            elif now_t - self._d2_retry_at >= 30.0:
                # No active window and retry interval elapsed — start a new attempt.
                self._d2_retry_at = now_t
                log.info("RBMemoryReader: starting deck-2 resolution")
                s.start_deck2_resolution(self._scan_regions)
        elif s._d2_pending:
            # Deck 2 got committed mid-window; discard leftover pending state.
            s._d2_pending.clear()
            s._d2_samples.clear()

        for deck in (1, 2):
            snap = s.read_deck(deck)
            if snap is not None:
                self._cache.update(snap)
                if self._drift is not None:
                    warn = self._drift.update(deck, snap.elapsed_ms, snap.playing)
                    if warn:
                        log.warning("drift: %s", warn)

    def _try_attach(self) -> None:
        pid = get_rb_pid()
        if pid is None:
            time.sleep(self._ATTACH_RETRY_S)
            return
        try:
            vmmap_out = _get_vmmap_output(pid)
            base      = _base_from_vmmap(vmmap_out)
            self._scan_regions = _scan_regions_from_vmmap(vmmap_out)
            task = _task_for_pid(pid)
            self._session     = RBSession(pid, base, task)
            self._attach_time = time.monotonic()
            self._d2_retry_at = 0.0   # allow immediate deck-2 resolution on first tick
            log.info("RBMemoryReader: attached pid=%d base=0x%x regions=%d",
                     pid, base, len(self._scan_regions))
        except Exception as exc:
            log.warning("RBMemoryReader: attach failed pid=%d: %s — retry in %ds",
                        pid, exc, int(self._ATTACH_RETRY_S))
            time.sleep(self._ATTACH_RETRY_S)
