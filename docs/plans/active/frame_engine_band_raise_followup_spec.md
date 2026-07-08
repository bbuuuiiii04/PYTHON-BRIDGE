# Implementation Spec - Frame Engine Scheduling-Band Follow-up (verify the raise, self-heal the timing)

status: planned (awaiting executive review)
last_verified_commit: e707199
owner: operator (Brandon) via Claude Fable 5 orchestration session 2026-07-08
registry: AWR-151

Execute tasks **in order, one commit per task**. File:lines verified at HEAD `e707199` on
2026-07-08. Labels: [confirmed] / [assumed] / [unknown].

> Shared dirty worktree + auto-sync hook: NEVER revert changes you did not make; commit ONLY by
> explicit file paths; no destructive git; work on `main`; touch ONLY the files listed here.
> Never touch a running bridge.

## Part A - Live Evidence & Root Cause (verified; read, do not implement)

1. [confirmed, operator live 2026-07-08] The frame-engine child, spawned from the REAL launch
   chain (menubar → watcher → bridge → child), self-reported `achieved_fps ≈ 33` with
   `fps_degraded=True` (oscillating 12-20 during load) — the AWR-146 self-report did its job;
   the band raise did not fully do its own. `raise_scheduling_band()`
   (`govee_frame_engine.py:87-104` at AWR-146 HEAD; shifted a few lines by the `aa8fe2f`
   comment block) succeeded when tested from an interactive shell, but its effectiveness when
   the band is INHERITED from the real launch chain is different — this was the explicitly
   recorded [unknown] in the AWR-146 design.
2. [confirmed] The band report (`[ENGINE] scheduling band report=...`) is logged once to child
   stderr at startup (`main()`, `logging.basicConfig(stream=sys.stderr)`) — visible only in the
   watcher terminal, absent from the jsonl event stream and the runtime status surface. The
   operator cannot see whether setpriority/NSActivity even succeeded in production.
3. [confirmed] The mechanism that demotes long-running faceless processes remains [unknown]
   (AWR-146 Part A.1: darwin-bg alone explains 20.5 fps, not 33; ~33 ≈ every second 16.7 ms
   sleep overshooting to ~30 ms suggests timer coalescing in an intermediate band). This spec
   therefore does NOT bet on naming the mechanism: it makes the band state VISIBLE, re-asserts
   the cheap lever continuously, and gives the frame loop a timing backstop that works in ANY
   band at bounded CPU cost.
4. [confirmed] The runner already accepts an injected `sleep_fn`
   (`govee_realtime_runner.py:60,79`), so a precision-sleep backstop needs ZERO runner changes —
   the child owns the sleep function.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `govee_frame_engine.py`, `govee_frame_engine_client.py`,
  `led_dispatch_policy.py` (status-sanitize whitelist line only),
  `tests/test_govee_frame_engine.py`, `tests/test_govee_frame_engine_integration.py`, the
  Part E docs, and the AWR-151 registry row (exists before you start; STOP if absent).
- Out of scope: `govee_realtime_runner.py` (sleep_fn injection makes it unnecessary), all other
  bridge subsystems, config schema, new env flags.
- Behavior that must not change: every AWR-146 protocol message and fail-dark path; the anchor
  coast fix (`aa8fe2f`); heartbeat cadence; the `os._exit(0)` exit discipline.
- Error handling: band syscalls that fail report False/None in the heartbeat — never raise out
  of the host loop; the precision sleep must be arithmetically bounded (never spin more than
  `PRECISE_SPIN_MAX_S` per frame).

### Task 1 - `govee_frame_engine.py`: band state into every heartbeat

1. `raise_scheduling_band()` return dict gains `"darwin_prio": int | None` — read back via
   `libc.getpriority(4 /*PRIO_DARWIN_PROCESS*/, 0)` after the raise (clear errno first;
   [assumed] returns 0 when non-bg — verify the live value semantics with one manual run on
   this machine and record it in the test comments).
2. Store the report in a module/host field; `_send_heartbeat` adds flattened scalars:
   `"band_setpriority": bool`, `"band_nsactivity": bool`, `"band_darwin_prio": int|None`,
   `"sleep_mode": str` (Task 3). Re-read `getpriority` at each heartbeat (cheap syscall) so a
   post-start demotion becomes visible as a changing number.
3. Re-assert the raise each heartbeat: call `libc.setpriority(4, 0, 0)` (cheap, idempotent,
   heals a post-start demotion); log at INFO only when the getpriority reading CHANGES
   (edge-triggered; high-frequency detail stays out of INFO).

### Task 2 - `govee_frame_engine_client.py` + `led_dispatch_policy.py`: surface it

1. Client `status()` passes through the new heartbeat scalars (they arrive inside the hb dict
   merge already — verify the keys are top-level in the hb, not nested, and add them to the
   client's pre-heartbeat safe defaults as `False/None/"normal"`).
2. Client logs ONE INFO line via `bridge_log` on the first heartbeat after every (re)spawn with
   the band report values, and an edge-triggered health line if `band_setpriority` or
   `band_nsactivity` report False — the operator must be able to see a failed raise in the
   jsonl, not just the watcher terminal.
3. `led_dispatch_policy.py` `_sanitize_led_adapter_status` realtime key tuple gains
   `"band_setpriority"`, `"band_nsactivity"`, `"band_darwin_prio"`, `"sleep_mode"`.

### Task 3 - `govee_frame_engine.py`: adaptive precision sleep (works in any band)

The mechanism-independent backstop: when the frame loop is being starved by sleep overshoot,
switch the runner's sleep to a two-stage precise mode at bounded CPU cost.

1. Pure function `plan_precise_sleep(remaining_s: float, coarse_margin_s: float) ->
   tuple[float, float]` returning `(coarse_sleep_s, spin_deadline_offset_s)` — trivially
   testable arithmetic. Constants: `PRECISE_COARSE_MARGIN_S = 0.004`,
   `PRECISE_SPIN_SLICE_S = 0.0005`, `PRECISE_SPIN_MAX_S = 0.004`.
2. The host builds the runner with `sleep_fn=self._adaptive_sleep` (a closure; the runner
   constructor already takes it — no runner change). Normal mode: `time.sleep(s)` verbatim.
   Precise mode: `time.sleep(max(0, s - PRECISE_COARSE_MARGIN_S))` then short
   `time.sleep(PRECISE_SPIN_SLICE_S)` slices until the original deadline, never exceeding
   `PRECISE_SPIN_MAX_S` of slicing per call.
3. Mode switching lives in `_send_heartbeat` (single-writer: the host loop): after 3 consecutive
   degraded heartbeats (`fps_degraded` already computed there) → `sleep_mode = "precise"`;
   after 10 consecutive clean streaming heartbeats → back to `"normal"`. The mode is a plain
   attribute read by the sleep closure (host loop writes, runner thread reads — a bool/str flip
   is safe under the GIL; document that). `sleep_mode` rides every heartbeat (Task 1).
4. Worst-case CPU cost, stated for the record: at 60 fps precise mode burns ≤ 4 ms × 60/s =
   24% of one core in slices — acceptable as a degraded-only backstop on this machine; it
   self-disarms after 10 clean heartbeats.

## Part C - Invariants That MUST Still Hold (live safety)

- All AWR-146 fail-dark paths, message handling, and the anchor coast (`aa8fe2f`) byte-identical.
- The heartbeat never blocks or raises out of the host loop; band syscall failures degrade to
  False/None values, not exceptions.
- The precision sleep is bounded (≤4 ms slicing per frame), degraded-triggered only,
  self-disarming, and visible (`sleep_mode` in status) — never a silent CPU tax.
- No runner, protocol-message, or client-command changes; the IPC surface is unchanged except
  new scalar fields inside the existing `hb` payload (decode-compatible both directions).

## Part D - Tests

Pure (`tests/test_govee_frame_engine.py`): heartbeat carries the four new scalars; getpriority
re-read/re-assert called per heartbeat (fake libc seam — factor the ctypes calls behind a small
module-level function the test monkeypatches); `plan_precise_sleep` arithmetic incl. the spin
cap and sub-margin remainders; mode switches at exactly 3 degraded / 10 clean heartbeats (fake
clock); the adaptive closure calls plain sleep in normal mode. Client: new fields pass through
`status()` with safe defaults pre-heartbeat; the first-heartbeat INFO log fires once per spawn
(fake bridge_log seam or log_changed key assertion). Policy: whitelist passes the four keys.
Integration (`tests/test_govee_frame_engine_integration.py`, CI-skipped): the real child's first
heartbeat contains `band_setpriority` True and a `band_darwin_prio` value on this machine.

Run single modules while iterating; full `python3 -m unittest discover tests` before the final
commit — green except the 5 known environmental reds.

## Part E - Acceptance

1. Part D green; 3 hard checks green.
2. `led_govee` docs_update where affected: `docs/subsystems/led_govee.md` (band self-report +
   adaptive sleep backstop), `docs/status/feature_status_matrix.md`,
   `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`; registry
   row AWR-151 → implemented/software-tested. Status language: implemented / software-tested /
   hardware-unvalidated only. The LIVE question — what fps the child holds during a real mix
   with the coast fix + AWR-148 landed — is answered only by the operator's next mix; say so.
3. No changes outside the Part B file list; explicit-path commits.

## When You Finish

Plain-language operator summary: the frame engine's status now shows not just its speed but
WHY — whether each of the priority levers actually took hold, as numbers in the normal status
output instead of a line lost in the watcher terminal; and if macOS still slows it down anyway,
it now notices within ~3 seconds and switches itself to a more precise (slightly more
CPU-hungry) timing mode until the speed recovers, then switches back. What this does NOT do:
change any look, blackout, or timing behavior — it is instrumentation plus a self-healing
backstop, and the real proof is the fps number on his next mix.
