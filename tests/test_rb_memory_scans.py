"""Equivalence / yielding / numpy-failure tests for the RBMEM scan pre-filters.

Pure seams only -- no mach syscalls, no live Rekordbox process. The vectorized
helpers `_i32_moving_candidates` / `_i32_static_candidates` (rb_memory.py) must
return byte-identical candidate lists on the numpy fast path, the pure fallback,
AND a straight port of the OLD int32 loop (the oracle below) -- including the
int32-overflow edge -- and must yield the GIL periodically so the 200 Hz push
loop and LED runner keep breathing while a scan runs.
"""
from __future__ import annotations

import random
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import rb_memory as mod

RB_SCALE = mod.RB_SCALE
MAX_MS = mod.MEM_MAX_ELAPSED_MS
RATE_LO = mod._D2_RATE_LO
RATE_HI = mod._D2_RATE_HI
HEAP_TOL = mod._D2_HEAP_TARGET_TOL_MS
STATIC_TOL = mod._D2_STATIC_TOL_MS
_HAS_NUMPY = mod._numpy() is not None


def _pack(vals: list[int]) -> bytes:
    return struct.pack("<%di" % len(vals), *vals)


# ── oracles: faithful transcriptions of the OLD numeric pre-filter loops ─────

def _moving_oracle(chunk0, chunk1, actual_dt, *, target_ms, clamp_ms_zero):
    n = min(len(chunk0), len(chunk1)) // 4
    out = []
    for i in range(n):
        r0 = struct.unpack_from("<i", chunk0, i * 4)[0]
        r1 = struct.unpack_from("<i", chunk1, i * 4)[0]
        d = r1 - r0
        if d <= 0:
            continue
        rate = d / actual_dt
        if not (RATE_LO <= rate <= RATE_HI):
            continue
        if clamp_ms_zero:
            ms = max(0, int(r1 * RB_SCALE))
        else:
            ms = int(r1 * RB_SCALE)
            if ms < 0:
                continue
        if ms > MAX_MS:
            continue
        if target_ms is not None and abs(ms - target_ms) > HEAP_TOL:
            continue
        out.append((i, rate, ms))
    return out


def _static_oracle(chunk, *, target_ms, tolerance_ms):
    n = len(chunk) // 4
    out = []
    for i in range(n):
        raw = struct.unpack_from("<i", chunk, i * 4)[0]
        if raw < 0:
            continue
        ms = int(raw * RB_SCALE)
        if ms > MAX_MS:
            continue
        delta_ms = abs(ms - target_ms)
        if delta_ms > tolerance_ms:
            continue
        out.append((i, ms, delta_ms))
    return out


# ── buffer builders (randomized base + planted candidates) ───────────────────

# Moving plants: index -> (r0, r1). With actual_dt=0.5, a survivor needs the
# delta in [19000, 25000] (rate 38000-50000).
_MOVING_PLANTS = {
    10: (100_000, 122_000),        # clean survivor (d=22000, r1>0)
    20: (-30_000, -8_000),         # d=22000 but r1<0: zone clamps to ms=0, heap rejects
    30: (-2**31, 2**31 - 1),       # int32-overflow forward: true d huge -> rate reject
    40: (2**31 - 1, -2**31),       # int32-overflow reverse: true d negative -> d<=0 reject
    50: (2147483647, -2147461649), # int32-wrap trap: int64 d<0 rejects, int32 wrap would keep
    60: (0, 200_000),              # d=200000 -> rate 400000 out of range
    70: (50, 45),                  # d<0 -> rejected
    80: (200_000, 221_000),        # survivor near a heap target (r1=221000 -> ms=5011)
}


def _build_moving(n=2000, seed=1234):
    rnd = random.Random(seed)
    v0 = [rnd.randint(0, 1_000_000) for _ in range(n)]
    v1 = [v0[i] + rnd.randint(-30_000, 30_000) for i in range(n)]
    for idx, (a, b) in _MOVING_PLANTS.items():
        v0[idx] = a
        v1[idx] = b
    return _pack(v0), _pack(v1)


_STATIC_PLANTS = {
    10: 220_000,        # ms ~ 4988, near target
    20: -5_000,         # negative raw -> rejected
    30: 400_000_000,    # ms ~ 9.07M > MAX_MS -> rejected
    40: 221_000,        # ms ~ 5011
}


def _build_static(n=2000, seed=99):
    rnd = random.Random(seed)
    vals = [rnd.randint(-5_000, 500_000) for _ in range(n)]
    for idx, v in _STATIC_PLANTS.items():
        vals[idx] = v
    return _pack(vals)


def _fallback_moving(chunk0, chunk1, dt, **kw):
    with mock.patch.object(mod, "_numpy", lambda: None):
        return mod._i32_moving_candidates(chunk0, chunk1, dt, **kw)


def _fallback_static(chunk, **kw):
    with mock.patch.object(mod, "_numpy", lambda: None):
        return mod._i32_static_candidates(chunk, **kw)


class MovingEquivalenceTests(unittest.TestCase):
    DT = 0.5

    def _configs(self):
        # (label, kwargs, oracle target_ms, clamp)
        return [
            ("zone", dict(rate_lo=RATE_LO, rate_hi=RATE_HI, scale=RB_SCALE,
                          max_ms=MAX_MS, clamp_ms_zero=True), None, True),
            ("heap", dict(rate_lo=RATE_LO, rate_hi=RATE_HI, scale=RB_SCALE,
                          max_ms=MAX_MS, target_ms=5000, target_tol_ms=HEAP_TOL,
                          clamp_ms_zero=False), 5000, False),
        ]

    def test_fallback_matches_oracle(self):
        c0, c1 = _build_moving()
        for label, kw, target_ms, clamp in self._configs():
            with self.subTest(label=label):
                oracle = _moving_oracle(c0, c1, self.DT, target_ms=target_ms,
                                        clamp_ms_zero=clamp)
                got = _fallback_moving(c0, c1, self.DT, **kw)
                self.assertEqual(got, oracle)
                self.assertTrue(oracle, "expected some planted survivors")

    @unittest.skipUnless(_HAS_NUMPY, "numpy not installed (CI 3.11 may lack it)")
    def test_numpy_matches_oracle_and_fallback(self):
        c0, c1 = _build_moving()
        for label, kw, target_ms, clamp in self._configs():
            with self.subTest(label=label):
                oracle = _moving_oracle(c0, c1, self.DT, target_ms=target_ms,
                                        clamp_ms_zero=clamp)
                numpy_res = mod._i32_moving_candidates(c0, c1, self.DT, **kw)
                fb = _fallback_moving(c0, c1, self.DT, **kw)
                self.assertEqual(numpy_res, oracle)
                self.assertEqual(numpy_res, fb)

    def test_overflow_edge_isolated(self):
        # Only the int32-overflow / wrap plants; everything must be rejected the
        # same way by all paths (no wrap-induced false positive).
        v0 = [0] * 8
        v1 = [0] * 8
        for slot, (idx, (a, b)) in enumerate(
            [(0, (-2**31, 2**31 - 1)), (1, (2**31 - 1, -2**31)),
             (2, (2147483647, -2147461649))]
        ):
            v0[slot] = a
            v1[slot] = b
        c0, c1 = _pack(v0), _pack(v1)
        for label, kw, target_ms, clamp in self._configs():
            with self.subTest(label=label):
                oracle = _moving_oracle(c0, c1, self.DT, target_ms=target_ms,
                                        clamp_ms_zero=clamp)
                self.assertEqual(oracle, [])  # nothing survives the edges
                self.assertEqual(_fallback_moving(c0, c1, self.DT, **kw), oracle)
                if _HAS_NUMPY:
                    self.assertEqual(
                        mod._i32_moving_candidates(c0, c1, self.DT, **kw), oracle)


class StaticEquivalenceTests(unittest.TestCase):
    TARGET = 5000
    TOL = STATIC_TOL

    def test_fallback_matches_oracle(self):
        chunk = _build_static()
        oracle = _static_oracle(chunk, target_ms=self.TARGET, tolerance_ms=self.TOL)
        got = _fallback_static(chunk, scale=RB_SCALE, max_ms=MAX_MS,
                               target_ms=self.TARGET, tolerance_ms=self.TOL)
        self.assertEqual(got, oracle)
        self.assertTrue(oracle, "expected some planted survivors")

    @unittest.skipUnless(_HAS_NUMPY, "numpy not installed (CI 3.11 may lack it)")
    def test_numpy_matches_oracle_and_fallback(self):
        chunk = _build_static()
        oracle = _static_oracle(chunk, target_ms=self.TARGET, tolerance_ms=self.TOL)
        numpy_res = mod._i32_static_candidates(chunk, scale=RB_SCALE, max_ms=MAX_MS,
                                               target_ms=self.TARGET, tolerance_ms=self.TOL)
        fb = _fallback_static(chunk, scale=RB_SCALE, max_ms=MAX_MS,
                              target_ms=self.TARGET, tolerance_ms=self.TOL)
        self.assertEqual(numpy_res, oracle)
        self.assertEqual(numpy_res, fb)


class YieldingTests(unittest.TestCase):
    def test_fallback_yields_per_slice(self):
        n = 100_000
        c0, c1 = _build_moving(n=n, seed=7)
        calls = []
        _fallback_moving(
            c0, c1, 0.5, rate_lo=RATE_LO, rate_hi=RATE_HI, scale=RB_SCALE,
            max_ms=MAX_MS, clamp_ms_zero=True, yield_fn=lambda _x: calls.append(_x),
        )
        self.assertGreaterEqual(len(calls), n // mod._SLICE_INTS)

    def test_static_fallback_yields_per_slice(self):
        n = 100_000
        chunk = _build_static(n=n, seed=8)
        calls = []
        _fallback_static(
            chunk, scale=RB_SCALE, max_ms=MAX_MS, target_ms=5000,
            tolerance_ms=STATIC_TOL, yield_fn=lambda _x: calls.append(_x),
        )
        self.assertGreaterEqual(len(calls), n // mod._SLICE_INTS)

    @unittest.skipUnless(_HAS_NUMPY, "numpy not installed (CI 3.11 may lack it)")
    def test_heap_scan_yields_between_chunks(self):
        # With numpy active the per-chunk helper does not yield internally, so
        # the heap scan itself must yield between chunks to let the push loop run.
        chunk_bytes = 4096
        n_chunks = 3
        region = [(0x1000, chunk_bytes * n_chunks)]
        sleeps = []
        with mock.patch.object(mod, "_read_bytes",
                               side_effect=lambda task, addr, size: b"\x00" * size), \
             mock.patch.object(mod, "_D2_HEAP_CHUNK_BYTES", chunk_bytes), \
             mock.patch.object(mod.time, "sleep", lambda x: sleeps.append(x)):
            hits = mod._scan_objc_heap_moving(0, region, target_ms=1000)
        self.assertEqual(hits, [])  # all-zero memory -> no moving candidates
        zero_yields = [s for s in sleeps if s == 0]
        self.assertEqual(len(zero_yields), n_chunks - 1)


class NumpyFailureFallbackTests(unittest.TestCase):
    @unittest.skipUnless(_HAS_NUMPY, "numpy not installed (CI 3.11 may lack it)")
    def test_moving_numpy_error_falls_back(self):
        c0, c1 = _build_moving()
        expected = _moving_oracle(c0, c1, 0.5, target_ms=None, clamp_ms_zero=True)
        with mock.patch.object(mod, "_moving_numpy", side_effect=RuntimeError("boom")):
            got = mod._i32_moving_candidates(
                c0, c1, 0.5, rate_lo=RATE_LO, rate_hi=RATE_HI, scale=RB_SCALE,
                max_ms=MAX_MS, clamp_ms_zero=True)
        self.assertEqual(got, expected)

    @unittest.skipUnless(_HAS_NUMPY, "numpy not installed (CI 3.11 may lack it)")
    def test_static_numpy_error_falls_back(self):
        chunk = _build_static()
        expected = _static_oracle(chunk, target_ms=5000, tolerance_ms=STATIC_TOL)
        with mock.patch.object(mod, "_static_numpy", side_effect=RuntimeError("boom")):
            got = mod._i32_static_candidates(
                chunk, scale=RB_SCALE, max_ms=MAX_MS, target_ms=5000,
                tolerance_ms=STATIC_TOL)
        self.assertEqual(got, expected)


class ClassifyAttachErrorTests(unittest.TestCase):
    def test_task_for_pid_is_reads_blocked(self) -> None:
        from rb_ss_bridge_v2.rb_memory import classify_attach_error
        self.assertEqual(
            classify_attach_error(OSError("task_for_pid(123) failed kern_return=5")),
            "reads_blocked",
        )
        self.assertEqual(classify_attach_error(RuntimeError("vmmap timed out")), "attach_failed")


if __name__ == "__main__":
    unittest.main()
