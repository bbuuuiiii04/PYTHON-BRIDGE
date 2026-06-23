---
doc_status: completed-plan
truth_level: code-grounded
last_verified_commit: HEAD
last_verified_date: 2026-06-22
validation_scope: spec + implementation; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
implementer: Opus (operator override)
---

# B1 phase-trace tick wiring — spec + implementation record

Wire the already-built, already-tested `AutoloopPhaseTracer` into the live
`StateManager` 200 Hz tick so that **while a session recording is active** the
`session.jsonl` gains schema-2 `autoloop_phase` rows. Without this, every T7d
capture is useless: the oracle `validate_autoloop_capture.py` hard-exits with
`"no schema-2 autoloop_phase rows in trace"` and no phase-contract evidence can
be produced. This is the §4 prerequisite called out in
`docs/plans/active/soundswitch_t7d_capture_gate_handoff.md`.

This is a **live-critical 200 Hz hot-path edit**. It was plan-first by policy
(`feedback_plan_first_live_critical`).

## IMPLEMENTATION STATUS — DONE 2026-06-22 (Opus, operator override)

**Opus implemented this pass directly** under an explicit, task-scoped operator
override of the usual "Codex implements" rule (consistent with the standing SS
exception). What this changes vs the original plan below:

- **`session_phase_trace.py`** — `AutoloopPhaseTracer.close()` is now
  **deterministic** (option A): it enqueues a sentinel, joins, and returns a
  frozen `PhaseTracerCloseResult(ok, timed_out, undrained, dropped,
  writer_error)`. A writer exception is captured in `_run` (the remaining queue
  is drained and counted as `undrained`) so close never hangs and never silently
  loses the sentinel.
- **`session_recorder.py`** — new `write_phase_trace_footer(...)` writes a
  schema-2 `phase_trace_footer` integrity record.
- **`state_manager.py`** — import + `self._phase_tracer`; `start_session_recording`
  opens the recorder at **schema=2** and attaches the tracer;
  `stop_session_recording` closes the tracer, writes the footer, **then** closes
  the recorder; the tick emits one row at the **end of `_push_tick_inner`**,
  **gated on `d.playing`** (non-playing/stale/stop paths emit nothing).
- **`tools/ssfmt/re/validate_autoloop_capture.py`** — `load_phase_trace_footer`
  + pure `evaluate_phase_trace_integrity`; `run_t7d` raises
  `INCOMPLETE_T7D_EVIDENCE` if the footer is missing/unclean or any
  dropped/undrained count is nonzero.

**Drop / integrity policy (fix #2):** there are no timestamped drop ranges, so
**any nonzero `dropped` OR `undrained`, an unclean close, or a missing footer
invalidates the ENTIRE capture run.** Per-segment salvage is explicitly future
work, possible only if drop timestamps/ranges are added later.

**Scope guardrails honored:** B1 is **evidence tooling only**. T7d runtime
autoloop DMX is **still not implemented**; the live pack driver still resolves
safe-zero and **never calls `select_autoloop`**; **no phase mapping is selected**;
**`600` ticks/beat remains unproven**; no MIDI/serial/Enttec/DMX opened; bridge
not restarted; no SoundSwitch project mutated; no production value seeded from
captures. **Repo status stays SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.**

Tests: `tests/replay/test_phase_trace.py` (+close-result/writer-exception),
`tests/replay/test_phase_trace_wiring.py` (new), `tests/test_t7d_capture_integrity.py`
(new). Full suite **2176 OK** (skipped 3, xfail 1); doc hard checks green;
`git diff --check` clean.

> The Part A–E sections below are the original pre-implementation plan, retained
> as the design record. Where they describe close()/drop semantics or "Codex
> implements," the IMPLEMENTATION STATUS block above supersedes them.

---

## Part A — Context & root cause (verified; read, do not implement)

- **[confirmed]** The B1 tooling exists and is unit-tested in isolation:
  `session_phase_trace.py` defines the pure `build_autoloop_phase_row(...)`
  (`session_phase_trace.py:57`) and `AutoloopPhaseTracer` (bounded mailbox +
  daemon writer thread; `emit()` does only `put_nowait`, drops counted in
  `.dropped`; `close()` drains + joins — `session_phase_trace.py:70-132`).
  `SessionRecorder.write_phase_row()` persists a row under the file lock
  (`session_recorder.py:103-109`). `tests/replay/test_phase_trace.py` proves the
  pure builder, drop accounting, no-I/O-on-emit, schema-2 round-trip, and
  schema-1 byte-compatibility.
- **[confirmed]** The call-site is **not wired**: `AutoloopPhaseTracer` is
  instantiated only in `tests/replay/test_phase_trace.py`; there is **zero**
  reference to it in `state_manager.py` (no `AutoloopPhaseTracer`, no `.emit(`,
  no `write_phase_row` caller in the live path). `test_phase_trace.py:10-12`
  states the call-site is intentionally deferred to plan-first review. **Root
  cause: the tick never builds or emits a phase row.**
- **[confirmed]** The oracle only consumes a subset of the captured fields:
  `load_phase_trace` filters by `row["kind"] == "autoloop_phase"`
  (`validate_autoloop_capture.py:312-322`); `_beat_at_epoch` aligns wire frames
  to the nearest row by `epoch_ns` and reads `abs_beat_pos`
  (`validate_autoloop_capture.py:325-330`); `_origin_hypotheses` reads
  `autoloop_arm_sync_beat`, `midi_refire_origin_beat`, `phrase_anchor_last_beat`,
  `last_autoloop_status_phrase_beat`, and `abs_beat_pos` (only when
  `autoloop_tick_just_fired` is truthy) — `validate_autoloop_capture.py:333-362`.
  It exits if there are zero phase rows (`:384`). **These are the load-bearing
  fields. `role`, `reason`, `accepted_scene`, `accepted_note`,
  `accepted_trigger_gen` are NOT consumed by the oracle.**
- **[confirmed]** Because alignment is nearest-neighbor-by-`epoch_ns` over ALL
  rows, the trace must be **dense** (sampled every playing tick), so the emit
  belongs on the steady playing path, not only on fire ticks.
- **[confirmed]** Recorder ownership and lifecycle live in `state_manager.py`:
  `self._recorder` is set in `__init__` (`state_manager.py:339`);
  `start_session_recording` / `stop_session_recording` / `toggle_session_recording`
  create/close it (`state_manager.py:1008-1027`); `SessionRecorder.from_env()`
  is the construction-time fallback. The runtime command `toggle_record_session`
  → `_toggle_record_session` (`__main__.py:1228-1231`) → `sm.toggle_session_recording(path, dedup)`.
  The T7d conductor drives exactly this command
  (`tools/t7d_capture_conductor.py:394`).
- **[confirmed]** Authoritative field sources at tick end (all already in scope):
  - `active` (local, `state_manager.py:3288`) → `active_deck`
  - `d` = `self._deck[active]`; `d.load_gen`, `d.playing`, `d.meta.beatgrid_source`
    (`models.py:41`)
  - `abs_beat_pos` (local, finalized at `state_manager.py:3461`) → beat authority
  - `bpm`, `elapsed_ms` (locals) ; `snap` (local) for `position_stale`
  - `os = self._os` (`OutputState`, `state_manager.py:492`/`3287`); confirmed
    `OutputState` fields in `models.py`: `lighting_mode` (`:139`),
    `autoloop_arm_pending` (`:145`), `autoloop_arm_sync_beat` (`:146`),
    `autoloop_arm_target_elapsed_ms` (`:147`),
    `last_autoloop_status_phrase_beat` (`:150`), `pending_autoloop_arm_reason`
    (`:165`), `drop_cut_armed` (`:167`), `phrase_anchor_last_beat` (`:171`),
    `midi_refire_origin_beat` (`:174`)
  - `autoloop_tick_just_fired` (local, finalized within the `if bpm > 0:` block by
    `state_manager.py:3753`; defaults `False` at `:3613`)
- **[confirmed]** `_push_tick_inner` runs `state_manager.py:3282-3829`; its final
  statement is the elapsed/beatpos send loop (`:3827-3828`). All non-playing
  exits (`stale-stop` `:3337`, `stop_confirmed` `:3516`, `resume-settle` `:3546`,
  `idle` `:3567`) return **before** the playing path. The end of the function is
  reached only on a full playing tick — the correct single, dense emit point.
- **[confirmed]** `_push_tick` wraps `_push_tick_inner` and, on any exception,
  submits a ZERO pack frame then re-raises (`state_manager.py:3170-3189`). The
  emit must never raise (it won't: `emit()` is `put_nowait`-only and the two
  clock reads cannot raise in practice), but Part C keeps it dependency-free so a
  failure can never retain DMX.
- **[confirmed]** `role`, `reason`, `accepted_scene`, `accepted_note`,
  `accepted_trigger_gen` appear **only** in `PHASE_FIELDS`
  (`session_phase_trace.py:48-54`); there is **no** authoritative tick-local
  source for them in the bridge today. **[assumed]** They are reserved
  diagnostics; emitting them as `None` is correct because the oracle never reads
  them (Part A bullet 3).
- **[confirmed]** `start()`/`stop()` on `StateManager`: `stop()` only sets the
  stop event (`state_manager.py:608-609`); it does not close the recorder. The
  recorder closes via `atexit` (`session_recorder.py:55`).

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Do not touch** `session_phase_trace.py`, `session_recorder.py`,
  `session_replayer.py`, the oracle, or the conductor — the tooling is complete.
- **No behavior change when no session recording is active.** When
  `self._phase_tracer is None` the only added tick cost is one attribute load +
  truth test.
- **No new env flag.** Phase tracing is bound to the existing session-recording
  lifecycle (a deliberate diagnostic mode), exactly as the conductor expects.
- **Do not** add a tracer to the `from_env()` construction path — out of scope;
  the capture flow uses the `toggle_record_session` runtime command.
- **Do not** mutate `DeckState`/`OutputState` in the emit block (read-only).
- Before editing, find the matching contract in
  `docs/agents/change_contracts.yml` (core bridge / session tooling). If none
  matches, extend it first (AGENTS.md §7), then edit code.

### Task 1 — `state_manager.py`: import + new field
1. Add the import near the existing recorder import (`state_manager.py:75`):
   ```python
   from .session_recorder import SessionRecorder
   from .session_phase_trace import AutoloopPhaseTracer, build_autoloop_phase_row
   ```
2. In `__init__`, immediately after `self._recorder = ...` (`state_manager.py:339`):
   ```python
   self._recorder = recorder if recorder is not None else SessionRecorder.from_env()
   # B1 evidence-only autoloop phase tracer (schema-2). Attached ONLY while a
   # session recording started via the runtime command is active; None ⇒ the
   # tick emits no phase rows (zero overhead beyond one truth test). NOT a T7d
   # runtime/output feature — preparatory capture tooling only.
   self._phase_tracer: Optional[AutoloopPhaseTracer] = None
   ```
   (`Optional` is already imported.)

### Task 2 — `state_manager.py`: attach the tracer on record start
Replace `start_session_recording` (`state_manager.py:1008-1013`) with:
```python
def start_session_recording(self, path: str, *, dedup: bool = False) -> bool:
    if self._recorder:
        return False
    # schema=2 so the session carries autoloop_phase rows. The replayer/oracle
    # read schema-1 and schema-2 (kind-filtered); schema-1 stays byte-compatible.
    self._recorder = SessionRecorder(path, dedup=dedup, schema=2)
    self._phase_tracer = AutoloopPhaseTracer(self._recorder.write_phase_row)
    log.info(
        "[SM] record-session-start  path=%s  dedup=%s  phase_trace=on",
        path, "on" if dedup else "off",
    )
    return True
```

### Task 3 — `state_manager.py`: tear down the tracer BEFORE the recorder
Replace `stop_session_recording` (`state_manager.py:1015-1022`) with:
```python
def stop_session_recording(self) -> bool:
    if not self._recorder:
        return False
    path = str(self._recorder.path)
    # Stop new emits FIRST, then drain the writer thread into the still-open
    # recorder file handle, THEN close the recorder. Closing the recorder first
    # would make write_phase_row a silent no-op and lose queued rows.
    tracer = self._phase_tracer
    self._phase_tracer = None
    if tracer is not None:
        tracer.close()  # joins the writer thread; flushes all queued rows
        if tracer.dropped:
            log.warning("[SM] phase-trace dropped=%d (queue overflow)", tracer.dropped)
    self._recorder.close()
    self._recorder = None
    log.info("[SM] record-session-stop  path=%s", path)
    return True
```
(`toggle_session_recording` is unchanged: it calls start/stop, which now own the
tracer.)

### Task 4 — `state_manager.py`: emit one row at the end of every playing tick
At the very end of `_push_tick_inner`, immediately after the elapsed/beatpos send
loop (`state_manager.py:3827-3828`, the function's last statement), append:
```python
        # ── B1 evidence-only autoloop phase trace (schema-2) ──────────────────
        # Active ONLY while a session recording is running. Hot-path cost:
        #   inactive → one attribute load + truth test;
        #   active   → two non-blocking clock reads + one dict build + one
        #              bounded put_nowait. NO file/socket/MIDI/lock I/O on the
        #              tick (the tracer's daemon writer thread owns all I/O).
        # Read-only w.r.t. DeckState/OutputState. emit() never blocks or raises.
        tracer = self._phase_tracer
        if tracer is not None:
            tracer.emit(build_autoloop_phase_row(
                mono_ns=time.monotonic_ns(),
                epoch_ns=time.time_ns(),
                active_deck=active,
                load_gen=int(d.load_gen),
                playing=bool(d.playing),
                position_stale=bool(snap is None or snap.is_stale(MEM_STALE_S)),
                elapsed_ms=int(elapsed_ms),
                bpm=float(bpm),
                abs_beat_pos=float(abs_beat_pos),
                beatgrid_source=d.meta.beatgrid_source,
                lighting_mode=os.lighting_mode,
                autoloop_arm_pending=bool(os.autoloop_arm_pending),
                autoloop_arm_sync_beat=int(os.autoloop_arm_sync_beat),
                autoloop_arm_target_elapsed_ms=int(os.autoloop_arm_target_elapsed_ms),
                pending_autoloop_arm_reason=os.pending_autoloop_arm_reason,
                midi_refire_origin_beat=int(os.midi_refire_origin_beat),
                last_autoloop_status_phrase_beat=int(os.last_autoloop_status_phrase_beat),
                phrase_anchor_last_beat=int(os.phrase_anchor_last_beat),
                drop_cut_armed=bool(os.drop_cut_armed),
                autoloop_tick_just_fired=bool(autoloop_tick_just_fired),
                # Reserved diagnostic fields — no confirmed cheap tick-local
                # source today; the oracle does not consume them. Do NOT add
                # hot-path computation to derive these.
                role=None,
                reason=None,
                accepted_scene=None,
                accepted_note=None,
                accepted_trigger_gen=None,
            ))
```
Notes for the implementer:
- `os` here is the function-local `os = self._os` (`OutputState`), per this
  function's existing convention — **not** the stdlib module.
- `MEM_STALE_S` is already in scope (used at `:3315`, `:3587`); reuse it.
- Place the block at the same indentation as line `:3827` (inside
  `_push_tick_inner`, after the send loop, before the next method `def` at
  `:3830`).

---

## Part C — Invariants that MUST still hold (live safety)

1. **Push loop gains no blocking I/O** (AGENTS.md §6;
   `docs/architecture/runtime_invariants.md`). `emit()` is `put_nowait`-only;
   `time.monotonic_ns()`/`time.time_ns()` are non-blocking vDSO clock reads (the
   tick already calls `time.monotonic()` at `:3286`), not file/socket/MIDI/
   serial/subprocess I/O. All file writes happen on the tracer's daemon thread.
2. **No DeckState/OutputState mutation** in the emit block — reads only. Reader/
   owner separation preserved (`StateManager` stays the sole `DeckState` writer).
3. **Zero behavior change when not recording.** Tracer is `None` outside an
   explicit `start_session_recording`; tick adds one truth test only.
4. **Crash-safety unchanged.** The emit cannot retain DMX: it never touches the
   pack runtime, and `_push_tick`'s ZERO-on-exception wrapper (`:3170-3189`) is
   untouched.
5. **Teardown ordering + deterministic close.** `tracer.close()` enqueues a
   sentinel and joins (FIFO ⇒ guaranteed drain of all prior rows), returning a
   `PhaseTracerCloseResult`; it runs before `recorder.close()`. A writer
   exception is captured and the rest of the queue is drained (counted
   `undrained`) so close never hangs and the sentinel is never lost.
   `SessionRecorder._append` is lock-guarded and no-ops after close, so a stray
   late write cannot crash. `stop_session_recording` writes the integrity footer
   from the close result before closing the recorder.
6. **Drop/integrity is fail-closed and whole-run.** Hot-path overflow increments
   `tracer.dropped`; writer failures increment `undrained`. The footer records
   both plus close cleanliness. The offline oracle
   (`evaluate_phase_trace_integrity`) invalidates the **entire capture run** on
   any nonzero dropped/undrained, an unclean close, or a missing footer — there
   are no timestamped drop ranges, so no per-segment salvage. Never reinterpret a
   drop as evidence.
7. **Abrupt process exit is safe.** The writer is a daemon thread; the recorder's
   `atexit` close no-ops late writes (invariant 5). Trailing queued rows may be
   lost on a hard kill — acceptable for evidence tooling, never a crash.
8. **Repo status unchanged:** SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
   This is capture tooling, not a runtime feature; it does not upgrade status.

---

## Part D — Tests

Pure-function correctness already has a seam in
`tests/replay/test_phase_trace.py` (keep green). Add a **wiring** test module
(e.g. `tests/replay/test_phase_trace_wiring.py`) that exercises the real
`StateManager` tick. Reuse the existing StateManager construction/playing-tick
harness in `tests/test_led_state_manager.py` (`_prepare_playing_push_tick`,
`state_manager.py:3170` driver) rather than inventing a new one.

1. **Dense emit on the playing path.** Build a playing SM; call
   `start_session_recording(tmp)`; drive N (≥5) `_push_tick()` calls; call
   `stop_session_recording()`. Load the JSONL: header `schema == 2`; assert
   ≥ N−1 `autoloop_phase` rows (allow one boundary tick); each row carries
   `abs_beat_pos`, `epoch_ns`, `mono_ns`, and the four origin fields
   (`autoloop_arm_sync_beat`, `midi_refire_origin_beat`, `phrase_anchor_last_beat`,
   `last_autoloop_status_phrase_beat`); `mono_ns` is non-decreasing.
2. **No emit when not recording.** Drive ticks without
   `start_session_recording`; assert `sm._phase_tracer is None` and no JSONL/
   phase rows are produced; driving ticks never creates a tracer.
3. **No loss across teardown.** With a small driven tick count (≪ 4096), assert
   `tracer.dropped == 0` is reflected (no overflow warning) and the phase-row
   count equals the number of playing ticks driven (minus at most one boundary
   tick). This proves Task 3's ordering flushes the queue.
4. **Non-playing ticks emit nothing.** Drive a stale/idle tick (deck not playing)
   while recording; assert no `autoloop_phase` row is appended for that tick
   (the emit is past the non-playing early returns).
5. **Schema-1 path untouched.** `start_session_recording` always uses schema 2;
   the `from_env()` construction path stays schema 1 with no phase rows — assert
   an env-built recorder produces no `autoloop_phase` rows (existing
   `Schema1CompatibilityTests` already covers the round-trip; add the
   construction-path assertion if not covered).

Run: `python3 -m unittest discover tests` (note CI unit job is Python 3.11 per
`reference_ci_python_311`; local is 3.14 — watch for dataclass/import drift).

---

## Part E — Acceptance (definition of done)

- [ ] Tasks 1–4 implemented exactly; `session_phase_trace.py`,
      `session_recorder.py`, `session_replayer.py`, oracle, and conductor
      unchanged.
- [ ] `python3 -m unittest discover tests` green, including the new wiring tests
      and the existing `tests/replay/test_phase_trace.py`.
- [ ] A real (or harnessed) recording session yields a `session.jsonl` whose
      `autoloop_phase` rows make `validate_autoloop_capture.py` advance past the
      `"no schema-2 autoloop_phase rows in trace"` guard (`:384`) on a capture
      that has them.
- [ ] AGENTS.md §7: the matching change contract in
      `docs/agents/change_contracts.yml` is found/extended and every doc it lists
      under `docs_update` is updated; run the §8 hard checks
      (`check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py`) and the advisory `check_docs_staleness.py --report`.
- [ ] No regression to the `_push_tick` ZERO-on-exception contract; no
      DeckState/OutputState mutation added to the tick.
- [ ] **A bridge restart is required** for the wiring to take effect in a live
      capture; that restart is an operator action (menubar toggle) — verify
      exactly one core process afterward (`pgrep -f rb_ss_bridge_v2 | wc -l`
      core == 1; `feedback_bridge_restart`).

---

## Adversarial self-review (attack the spec before handoff)

- **"`time.time_ns()` on the 200 Hz tick adds jitter / is I/O."** It is a
  non-blocking vDSO clock read (sub-µs), only when recording (a deliberate
  diagnostic mode); the tick already calls `time.monotonic()`. Not file/network/
  MIDI I/O. Invariant §1 holds.
- **"The writer thread can't keep up with 200 rows/s → drops corrupt evidence."**
  200 small buffered JSON appends/s is trivial; on a stall, drops are counted +
  logged and the offline oracle invalidates any spanned segment (fail-closed,
  §6). `maxsize=4096` ≈ 20 s of slack.
- **"Race: command thread sets/clears `_phase_tracer` while the tick reads it."**
  Single attribute read per tick (atomic in CPython). Stop sets `None` before
  `close()`, so new emits cease first; a trailing emit captured pre-clear is
  harmless. No `DeckState` involvement.
- **"Stop closes the recorder before the tracer drains → lost rows / crash."**
  Task 3 mandates `tracer.close()` (drain+join) **before** `recorder.close()`;
  and `_append` no-ops after close, so a stray write cannot crash (§5).
- **"schema=2 breaks existing replay/consumers."** The replayer reads both
  schemas (kind-filtered) and the oracle filters by row kind, not header schema;
  `test_phase_trace.py` already proves schema-1 byte-compatibility and schema-2
  round-trip. Env-path recording stays schema-1.
- **"The emit point misses ticks (early returns) → sparse beat sampling."**
  Intended. Phase evidence is only meaningful during playback; the emit sits past
  every non-playing early return on the full playing path, producing a dense
  ~200 Hz beat trace — exactly what nearest-neighbor `_beat_at_epoch` needs.
  Non-playing ticks carry no autoloop phase to prove.
- **"`abs_beat_pos` at emit ≠ the value used for output this tick."** It is the
  same local finalized at `:3461` and used for `beatpos_out`/laser ctx; the emit
  recomputes nothing.
- **Forced failure scenario (phrase-anchor):** does the row carry
  `phrase_anchor_last_beat` at/after the fire tick? `os.phrase_anchor_last_beat`
  is an `OutputState` field updated in the rearm/anchor paths; the emit reads its
  current value every tick, so the post-update value is captured on that tick and
  all subsequent ticks — which is what `_origin_hypotheses` enumerates across
  rows. Confirmed sufficient.

## When you finish
- Commit per task with messages like
  `soundswitch(T7d-B1): wire AutoloopPhaseTracer into StateManager tick`.
- Report back: tests run + results, the change-contract key updated, the exact
  lines changed in `state_manager.py`, and an explicit reminder that a
  **bridge restart** is required before the next live capture and that repo
  status stays SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
