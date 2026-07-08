# Implementation Spec - Frame Engine Scheduling-Band Follow-up (verify the raise, self-heal the timing)

status: approved for implementation — RESHAPED by operator doctrine 2026-07-08 (root-cause fixes only): Tasks 1-2 proceed (instrumentation = root-cause enablement); Task 3 precision-sleep DROPPED as a declared bandage; Phase B root-cause investigation is the core deliverable, Phase C true fix gated on executive review of findings
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
   sleep overshooting to ~30 ms suggests timer coalescing in an intermediate band). This spec's
   shipping round (Tasks 1-2) does NOT bet on naming the mechanism: it makes the band state
   VISIBLE and re-asserts the cheap lever continuously; NAMING the mechanism is Phase B's job,
   and the fix is Phase C's.
4. [confirmed] The runner already accepts an injected `sleep_fn`
   (`govee_realtime_runner.py:60,79`), so any future timing lever can be injected without
   runner changes — the child owns the sleep function. (Context for Phase C; nothing ships here.)
5. [confirmed, operator live 2026-07-08 evening — post coast-fix + AWR-148 restart] Scan
   GIL-holds are down to ~30 ms and the blackout cycling is gone; live fps under load is
   **15-19 with child CPU at 1.4%** — the loop is nowhere near compute-bound, so the 16.7 ms
   sleep is stretching ~3-4×. Pure sleep-stretch: the demotion mechanism Phase B must name.

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
  of the host loop.

### Task 1 - `govee_frame_engine.py`: band state into every heartbeat

1. `raise_scheduling_band()` return dict gains `"darwin_prio": int | None` — read back via
   `libc.getpriority(4 /*PRIO_DARWIN_PROCESS*/, 0)` after the raise (clear errno first;
   [assumed] returns 0 when non-bg — verify the live value semantics with one manual run on
   this machine and record it in the test comments).
2. Store the report in a module/host field; `_send_heartbeat` adds flattened scalars:
   `"band_setpriority": bool`, `"band_nsactivity": bool`, `"band_darwin_prio": int|None`. Re-read `getpriority` at each heartbeat (cheap syscall) so a
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
   `"band_setpriority"`, `"band_nsactivity"`, `"band_darwin_prio"`.

### Task 3 - DROPPED (operator doctrine 2026-07-08: root-cause fixes only)

The adaptive precision sleep was a mechanism-independent BANDAGE — it would have masked the
demotion instead of removing it, at a permanent CPU tax and with a new mode to reason about.
The operator's standing doctrine (recorded 2026-07-08: "every fix needs to be a genuine root
cause fix, not just a quick bandage; if the fix is large and monumental, so be it") drops it.
Do not implement anything below in this section; it is retained only so the wall-clock-spin-cap
amendment and the reasoning are on the record if a bounded backstop is ever explicitly
re-approved.

<details>
The dropped design: when the frame loop is being starved by sleep overshoot,
switch the runner's sleep to a two-stage precise mode at bounded CPU cost.

1. Pure function `plan_precise_sleep(remaining_s: float, coarse_margin_s: float) ->
   tuple[float, float]` returning `(coarse_sleep_s, spin_deadline_offset_s)` — trivially
   testable arithmetic. Constants: `PRECISE_COARSE_MARGIN_S = 0.004`,
   `PRECISE_SPIN_SLICE_S = 0.0005`, `PRECISE_SPIN_MAX_S = 0.004`.
2. The host builds the runner with `sleep_fn=self._adaptive_sleep` (a closure; the runner
   constructor already takes it — no runner change). Normal mode: `time.sleep(s)` verbatim.
   Precise mode: `time.sleep(max(0, s - PRECISE_COARSE_MARGIN_S))` then short
   `time.sleep(PRECISE_SPIN_SLICE_S)` slices until the original deadline. **Spin-cap semantics
   are WALL-CLOCK (executive amendment 1): the slice loop exits at
   `min(original_deadline, slice_loop_start + PRECISE_SPIN_MAX_S)` measured by
   `time.monotonic()` — NOT by summed requested sleep time — because under the very throttling
   this mode exists to defeat, each 0.5 ms slice may really take 2-3 ms. State this in a code
   comment at the loop.**
3. Mode switching lives in `_send_heartbeat` (single-writer: the host loop): after 3 consecutive
   degraded heartbeats (`fps_degraded` already computed there) → `sleep_mode = "precise"`;
   after 10 consecutive clean streaming heartbeats → back to `"normal"`. The mode is a plain
   attribute read by the sleep closure (host loop writes, runner thread reads — a bool/str flip
   is safe under the GIL; document that). `sleep_mode` rides every heartbeat (Task 1).
4. Worst-case CPU cost, stated for the record: at 60 fps precise mode burns ≤ 4 ms × 60/s =
   24% of one core in slices — acceptable as a degraded-only backstop on this machine; it
   self-disarms after 10 clean heartbeats.

</details>

## Phase B - Root-cause investigation (THE core deliverable; separate dispatch after Tasks 1-2)

Identify the ACTUAL demotion mechanism. All experiments are OFFLINE with throwaway test children
(dry-run transport, own socketpairs, spawned by a standalone harness) — NEVER the live bridge,
and full-compute experiments run only when the operator is not mixing.

**THE CONTROL GROUP (operator observation 2026-07-08 evening, live): "the LED pads dont look
laggy when I play them."** The Pad process (pid 39899 that session, Python 3.9 CommandLineTools
build, up since Jul-3) holds ~28 fps steady under the SAME live load, same machine, same hours,
same renderer code, while the frame-engine child (Python 3.14 homebrew, menubar→watcher→bridge
chain) wobbles at 15-19. This kills the global-machine-load hypothesis: the mechanism is
whatever differs between the two chains.

Evidence already captured at `e707199`+ (2026-07-08 evening, read-only, live processes):
- Parent chains: the Pad is PARENTED TO LAUNCHD (ppid 1 — orphaned/detached from its launcher);
  the frame-engine child sits inside the menubar app's tree (child ← bridge ← watcher bash ←
  menubar python ← launchd). Coalition membership is inherited through spawn.
- Per-thread priorities (`ps -M`): EVERY child thread runs at `20T` — including the frame
  thread whose `on_thread_start` hook sets QOS_CLASS_USER_INTERACTIVE (which would read ~47) —
  so the thread-QoS lever is visibly NOT in effect or is clamped at the process level. The Pad's
  threads are also all `20T` (at 28 fps). The bridge owns one `97R` realtime thread (CoreMIDI's,
  [assumed]) — elevated bands ARE attainable inside this coalition.
- `launchctl procinfo` REQUIRES ROOT — the orchestrator cannot run it; the operator runs, when
  convenient (pids are volatile — capture before any restart):
  `sudo launchctl procinfo <child-pid> > /tmp/procinfo_child.txt` and the same for the pad,
  bridge, and menubar pids. The interesting fields: coalition id/name, role, QoS clamp,
  darwin role, App Nap state.

1. Baseline matrix — spawn the identical dry-run child through: (a) an interactive login shell,
   (b) a chain mimicking the real launch path (menubar → watcher shell → python → child), (c)
   detached (`start_new_session=True` / setsid / double-fork — replicating the Pad's
   orphaned-to-launchd placement), (d) `launchctl submit`/`launchctl asuser` placement, (e) the
   SAME interpreter as the Pad (`/Library/Developer/CommandLineTools/.../3.9/bin/python3` — the
   explicit Python 3.9-vs-3.14 elimination the operator required; the renderer imports are
   stdlib-pure so a 3.9 test child is feasible [verify syntax compat, else measure sleep
   overshoot with a minimal timer script instead]). For each: measured fps or direct
   sleep-overshoot histogram (request 16.7 ms, measure actual, under a synthetic load) + thread
   priorities via `ps -M` + `getpriority(PRIO_DARWIN_PROCESS)` + (operator-run) procinfo.
2. Diff the fast case against the slow case until ONE variable flips 15-19 → ≥28 (the Pad's
   band) and ideally → ~60 (the clean-shell band). Sharpened suspects, confirm or eliminate,
   not assume: (a) a process-level QoS clamp capping thread QoS (explains the 20T frame
   thread), (b) coalition inheritance from the menubar tree vs launchd-orphan placement, (c)
   interpreter timer behavior (CLT 3.9 vs homebrew 3.14 — different sleep syscalls/leeway), (d)
   per-thread timer-coalescing leeway at default QoS under load.
3. **Deliverable: a findings report to the executive naming the mechanism with the flip
   experiment as proof — BEFORE any Phase C implementation (hard review gate).**

## Phase C - The true fix (design-gated; do not start until the executive reviews Phase B)

Whatever Phase B names, the fix lands at the right layer: correct scheduling placement at spawn
(e.g. detached session / coalition escape / spawn attributes) and/or the macOS **thread
time-constraint policy** (`thread_policy_set(THREAD_TIME_CONSTRAINT_POLICY)` via ctypes on the
frame thread — the mach primitive audio apps use; the frame loop's duty cycle is tiny, ~0.5 ms
of work per 16.7 ms period, so a time-constraint contract is safe here), properly parameterized
(period/computation/constraint from the configured fps) and tested. Large is acceptable; right
layer is mandatory.

## Part C - Invariants That MUST Still Hold (live safety)

- All AWR-146 fail-dark paths, message handling, and the anchor coast (`aa8fe2f`) byte-identical.
- The heartbeat never blocks or raises out of the host loop; band syscall failures degrade to
  False/None values, not exceptions.
- No timing-behavior change ships in this round (Task 3 dropped by doctrine): frames, sleeps,
  and the runner are byte-identical; only observability is added.
- No runner, protocol-message, or client-command changes; the IPC surface is unchanged except
  new scalar fields inside the existing `hb` payload (decode-compatible both directions).

## Part D - Tests

Pure (`tests/test_govee_frame_engine.py`): heartbeat carries the new band scalars; getpriority
re-read/re-assert called per heartbeat (fake libc seam — factor the ctypes calls behind a small
module-level function the test monkeypatches). (Task 3 tests dropped with Task 3; `sleep_mode`
is not shipped.) Client: new fields pass through
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

Plain-language operator summary (Tasks 1-2 round): the frame engine's status now shows not just
its speed but WHY — whether each of the priority levers actually took hold, as numbers in the
normal status output instead of a line lost in the watcher terminal, refreshed every second.
This round deliberately changes NO timing behavior — per the root-cause doctrine, it is the
instrumentation that lets the investigation phase name the real slowdown mechanism, after which
the true fix (correct scheduling placement at spawn, and/or the guaranteed-scheduling contract
audio apps use for their sound threads) gets designed against evidence and reviewed before it
ships.
