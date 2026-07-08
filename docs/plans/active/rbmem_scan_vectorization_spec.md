# Codex Implementation Spec - RBMEM Scan Vectorization (kill the multi-second bridge freezes)

status: planned
last_verified_commit: d2ed39c (rb_memory.py last changed cbc6311, 2026-07-05 — line refs current)
owner: operator (Brandon) via Claude Fable 5 executive session 2026-07-08
registry: AWR-148

One commit per task. Labels: [confirmed] = read in current code / measured on this machine 2026-07-08,
[assumed] stated where load-bearing.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make unless
> explicitly requested. If asked to make edits and there are unrelated changes in those files, do
> not revert them. If you notice unexpected changes you didn't make, STOP and ask how to proceed.
> NEVER use destructive commands like `git reset --hard` or `git checkout --` unless specifically
> requested. Commit ONLY by explicit file paths (never `-a`, never `add -A`) — other agent lanes and
> an auto-sync hook share this worktree.

## Part A - Context & Root Cause (verified; read, do not implement)

When a deck is cued/paused/loaded and the deck-2 playhead is unresolved, `rb_memory.py` re-scans
Rekordbox process memory on the reader thread. The mach reads themselves release the GIL (ctypes
foreign calls, `rb_memory.py:95-101`) and the deliberate `time.sleep(dt)` between snapshot pairs is
harmless — but the candidate loops that follow compare the buffers **one int32 at a time in pure
Python**, holding the GIL:

1. [confirmed] `_scan_objc_zone` (`rb_memory.py:264-326`): loop at `:303-317` over `n = size // 4`
   ints (512 KB window ⇒ 131,072 iterations). Measured: **54 ms** GIL-held per pass; numpy
   equivalent **1.9 ms** (28×).
2. [confirmed] `_scan_objc_heap_moving` (`rb_memory.py:400-495`): loop at `:452-478` per chunk;
   `_D2_HEAP_CHUNK_BYTES = 0x400000` (4 MB), `_D2_HEAP_MAX_BYTES = 0x8000000` (**128 MB** cap,
   `:241-242`). Measured: **427 ms** GIL-held per 4 MB chunk (numpy 10.6 ms, 40×) ⇒ worst case is
   **multiple seconds** of whole-process freeze. This is the 1–7 fps LED collapse and the
   `event-late` bursts in live logs (86/min at deck-work moments, session 2026-07-08 10:00).
3. [confirmed] `_scan_static_elapsed_candidates` (`rb_memory.py:329-397`): same shape at `:356-378`
   (single buffer, cheap numeric filters, then rare expensive per-candidate checks).
4. [confirmed] Scans retry every 5 s while deck-2 is unresolved during play
   (`_D2_RETRY_PLAYING_S`, `:237`; driver `:1131-1170`), so the freezes recur exactly while the
   operator works the decks.
5. [confirmed] numpy 2.4.3 is installed; the repo's existing numpy pattern is a **lazy optional
   import inside the using function** (`audio_spectral_features.py:131`). numpy must NOT become a
   hard runtime dependency.

Goal: identical scan RESULTS, GIL-hold per slice bounded to a few ms. No semantic change to deck
resolution whatsoever.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY `rb_memory.py`, `tests/test_rb_memory_scans.py` (new), and the Part E docs. All other
  files — especially `govee_*`, `led_*`, `state_manager.py` — belong to other active lanes.
- Behavior that must not change: candidate VALUES and ORDER for identical inputs (byte-identical
  result lists); the snapshot-pair `time.sleep(dt)`; retry cadence/windows/attempt ladder; every log
  line's format; the per-candidate expensive checks (`_is_objc`, secondary reads) stay in Python
  exactly as they are.
- Error handling: numpy import failure ⇒ silently use the fallback (log once at DEBUG); never let a
  numpy error propagate — wrap the numpy path so any exception falls back to the pure loop for that
  call (fail toward correctness, not speed).

### Task 1 - `rb_memory.py`: pure candidate-filter helpers with numpy fast path + yielding fallback
1. Module-level lazy loader:
   `_np = None; _np_checked = False` and `def _numpy():` that imports once, caches, returns module
   or None (repo pattern: lazy, optional, type: ignore).
2. `def _i32_moving_candidates(chunk0: bytes, chunk1: bytes, actual_dt: float, *, rate_lo: float,
   rate_hi: float, scale: float, max_ms: int, target_ms: int | None = None,
   target_tol_ms: int | None = None, yield_fn=time.sleep) -> list[tuple[int, float, int]]`
   returning `(index, rate, ms)` ascending by index — the exact numeric pre-filter shared by the
   zone loop (`:303-317`, no target) and the heap loop (`:452-465`, with `abs(ms - target_ms) >
   target_tol_ms` filtering). Two implementations behind it:
   - numpy: `frombuffer("<i4")` on both buffers **cast to int64 before subtracting** (int32
     wraparound must match the pure-Python big-int arithmetic; equivalence test covers the
     overflow edge), then the mask chain `d > 0`, `rate_lo <= d/actual_dt <= rate_hi`,
     `0 <= ms <= max_ms` (ms from `r1 * scale` truncated toward the existing `int(...)`/`max(0,
     int(...))` semantics — replicate the zone loop's `max(0, int(r1 * RB_SCALE))` vs the heap
     loop's `int(r1 * RB_SCALE)` + `ms < 0` reject EXACTLY; parameterize if needed), optional
     target-tolerance mask, `np.nonzero` → build the small result list.
   - pure fallback: today's loop body, restructured to process in slices of 16,384 ints with
     `yield_fn(0)` between slices (releases the GIL so the 200 Hz loop and LED runner breathe;
     bounds GIL-hold to ~5-7 ms per slice).
3. `def _i32_static_candidates(chunk: bytes, *, scale: float, max_ms: int, target_ms: int,
   tolerance_ms: int, yield_fn=time.sleep) -> list[tuple[int, int, int]]` returning
   `(index, ms, delta_ms)` ascending by index — the numeric pre-filter of `:356-365`, same
   numpy/fallback split.

### Task 2 - `rb_memory.py`: rewrite the three call sites onto the helpers
- `_scan_objc_zone` `:300-317`: replace the loop; keep result assembly, the sort by
  `abs(rate - 44100)`, and all logging identical.
- `_scan_objc_heap_moving` `:444-478`: per chunk, call the helper (with target/tolerance), then run
  the UNCHANGED per-candidate Python checks (`pos_addr` math, `inner_ptr & 0xF`, `_is_objc`,
  secondary read) only on the few survivors; keep dedupe/sort/cap and logging identical. Add
  `yield_fn(0)` between chunks.
- `_scan_static_elapsed_candidates` `:354-378`: helper for the numeric pre-filter, then the
  unchanged per-candidate checks, sort, ambiguity guard, logging.

### Task 3 - `tests/test_rb_memory_scans.py` (new, pure seams only — no mach, no processes)
- Equivalence: for randomized buffer pairs WITH planted candidates (known indices/rates/ms) and for
  the int32-overflow edge (`r0 = -2**31`, `r1 = 2**31 - 1` and the reverse), the numpy path and the
  pure fallback return byte-identical lists, and both match a straight port of the OLD loop
  (implement the old loop inside the test as the oracle). Skip the numpy cases with
  `unittest.skipUnless(_numpy() is not None, ...)` — CI (Python 3.11) may not have numpy.
- Yielding: with an injected counting `yield_fn`, the fallback yields at least
  `n // 16384` times on a large buffer; the numpy path yields between heap chunks.
- Numpy-failure fallback: monkeypatch the numpy path to raise; the call still returns the correct
  (fallback) result.

## Part C - Invariants That MUST Still Hold (live safety)

- Deck-resolution SEMANTICS unchanged: same candidates, same order, same commit/validation flow,
  same retry ladder, same logs. This spec changes only how fast a filter loop runs.
- The reader thread's snapshot-pair sleep (`dt`) is untouched; deck-1 cache staleness margins
  (`MEM_STALE_S`) are unaffected.
- numpy stays optional: the bridge must start and resolve decks with numpy absent.
- The 200 Hz push loop and all other threads gain nothing new; they simply stop being starved.
- No new I/O, no new threads, no changes outside `rb_memory.py` + the new test file + docs.

## Part D - Tests

`python3 -m unittest tests.test_rb_memory_scans` (new, per Task 3) plus the existing
`python3 -m unittest discover tests` at its known baseline (the environmental reds documented in
AWR-145's registry entry are pre-existing; do not touch them).

## Part E - Acceptance (definition of done)

1. Task 3 tests green; full discover at the known baseline.
2. `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
   `python3 tools/check_docs_drift.py` all pass.
3. `rekordbox_readers` contract `docs_update` satisfied (`docs/agents/change_contracts.yml:421+`):
   update `docs/subsystems/rekordbox_readers.md` (scan filters vectorized with optional numpy +
   yielding fallback; freeze numbers from Part A) and the other docs that contract lists. Status
   language: implemented / software-tested only.
4. Registry row AWR-148 updated to implemented/software-tested — re-read
   `docs/status/active_work_registry.md` fresh immediately before editing (parallel lanes edit it).
5. Nothing outside the Part B file list changed.

## When You Finish

Report changed files, tests/checks run, and a plain-language operator summary: what the room
gains (working the decks — cueing, loading, pausing — can no longer freeze the whole bridge for
up to seconds at a time; the worst pause becomes a few milliseconds), what is unchanged (how decks
are found and validated, all timings and retries), and rollback (`git revert` of these commits +
menubar restart). SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED until the operator's next mix.
