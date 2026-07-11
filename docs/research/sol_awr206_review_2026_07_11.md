---
doc_status: current
truth_level: independent adversarial code review
last_verified_commit: a59022f
last_verified_date: 2026-07-11
validation_scope: >
  Read-only adversarial review of AWR-206 commits d95d7ce and f0da6b1 at HEAD
  a59022f. Code, tests, docs, and the two lane reports were inspected; focused
  software tests and one pure production-path reproduction were run. No bridge,
  MIDI, config, process, or hardware state was contacted or changed.
---

# SOL adversarial review — AWR-206 relaxed laser blackout gate

## Verdict: FAIL

- **[CONFIRMED]** The implementation does not reach its new relaxed executor
  branch through the real `LaserDirector -> LaserSceneExecutor` path. With
  `autoloop_ready=False`, the director returns `role="idle", scene=""` before
  the executor runs; the executor then returns at its idle/no-scene guard before
  `_passes_blackout_gates()` can be checked (`laser_director.py:223-239`,
  `laser_director.py:442-452`, `laser_executor.py:133-157`,
  `state_manager.py:4839-4869`).
- **[CONFIRMED]** A pure reproduction through the real two objects at HEAD
  produced `decision.role='idle'`, `scene=''`, `reason='autoloop_not_ready'`,
  zero backend calls, and no pending blackout. The direct executor tests pass
  only because they inject a `role="buildup"` decision that production cannot
  produce from the same blocked context (`tests/test_laser_executor.py:1006-1043`).
- **[CONFIRMED]** Do not activate AWR-206 expecting the four-beat pre-drop laser
  blackout to return. A required code correction and an end-to-end regression
  test must land before operator restart validation.

## Findings, severity ordered

### 1. Critical — the relaxed arm branch is unreachable for the failure it claims to fix

- **[CONFIRMED]** StateManager builds one immutable `LaserContext`, passes it to
  `LaserDirector.tick()`, then passes the resulting decision and that same
  context to `LaserSceneExecutor.on_decision()` (`state_manager.py:4839-4869`).
- **[CONFIRMED]** The director checks `playing`, loaded track, fresh position,
  scripted mode, and `autoloop_ready` before selecting any automatic role. The
  exact AWR-206 trigger state, `autoloop_ready=False`, returns an idle decision
  with no scene (`laser_director.py:394-452`).
- **[CONFIRMED]** The executor checks `role == "idle" or not decision.scene`
  before its strict automatic-gate branch. It logs a DEBUG no-scene skip and
  returns; the new relaxed branch at lines 140-157 never runs
  (`laser_executor.py:128-157`).
- **[CONFIRMED]** Every production StateManager executor call is paired with a
  director decision made from the same context; no alternate runtime caller
  supplies the artificial buildup decision used by the new tests
  (`state_manager.py:4302-4310`, `state_manager.py:4353-4361`,
  `state_manager.py:4583-4591`, `state_manager.py:4839-4869`).
- **[CONFIRMED]** The required fix shape is to make blackout-arm intent cross
  the director's readiness early return independently of scene selection. A
  dedicated arm result or a separately invoked executor arm path is safer than
  letting the director pretend an automatic scene fired: scene policy state and
  scene MIDI must remain strict-gated (`laser_director.py:241-292`,
  `laser_executor.py:159-319`).
- **[CONFIRMED]** The required regression must exercise the real chain:
  `LaserDirector.tick(ctx)` followed by `LaserSceneExecutor.on_decision(decision,
  ctx)` with `autoloop_ready=False` and an arm signal. It must assert blackout-on
  exactly once, scene MIDI zero times, and release at the crossing. Directly
  injecting an automatic decision into the executor is insufficient.

### 2. High — the tests prove a synthetic seam, not the shipped behavior

- **[CONFIRMED]** The five AWR-206 tests call the executor directly with
  `_decision(... role="buildup")`; none invokes `LaserDirector.tick()`
  (`tests/test_laser_executor.py:1006-1106`).
- **[CONFIRMED]** The two edited legacy tests removed only the intentionally
  changed `autoloop_ready=False` cases; their remaining playing, track-loaded,
  stale-position, mode, scripted, none/manual/emergency, and idle guards are
  still pinned (`tests/test_laser_executor.py:976-1004`,
  `tests/test_laser_executor.py:1360-1387`). They did not weaken another gate.
- **[CONFIRMED]** The missing coverage is above those tests: the director's
  priority-7 return makes their new setup unreachable. This is why 291 focused
  laser tests pass while the production-path reproduction still sends nothing.
- **[CONFIRMED]** Fix shape: keep the direct executor tests for local gate math,
  add one integrated director/executor test, and make that integrated test fail
  on current HEAD before changing production code.

### 3. Medium — the INFO diagnostic cannot report the real failure, and the arm is not edge-triggered

- **[CONFIRMED]** The new INFO line exists only inside the unreachable automatic-
  role blocked branch (`laser_executor.py:140-156`). The actual
  `autoloop_ready=False` path exits earlier with a DEBUG no-scene message
  (`laser_executor.py:133-138`), so the promised live-visible skip reason still
  will not appear.
- **[CONFIRMED]** The spec's “edge-triggered once per drop” premise is false.
  `smart_drop_blackout_arm` remains true on every push tick while
  `drop_cut_armed` is latched and the crossing has not occurred
  (`state_manager.py:4827-4837`); a regression test explicitly requires that
  level behavior across ticks (`tests/test_smart_transitions.py:1368-1413`).
  Smart-phrasing likewise keeps `transition_mask_arm_latched` true until a
  crossing or falling edge (`smart_phrasing.py:437-454`,
  `state_manager.py:5214-5221`).
- **[CONFIRMED]** Successful repeated calls are MIDI-idempotent because the
  pending latch is set under a lock before the backend call
  (`laser_executor.py:321-340`), and the existing retry test observes one
  blackout note across three arm ticks (`tests/test_laser_executor.py:1287-1309`).
- **[ASSUMED]** Once the core path is corrected, an INFO skip placed on the
  persistent arm level could run at the 200 Hz push rate during a lasting
  failure. The fix should emit once per changed failing-condition tuple or use
  the repo's throttled/changed logging helper, not log every arm-level tick.

### 4. Low — the release report mixes real release paths with precedence/zeroing paths

- **[CONFIRMED]** The smart pending latch itself is cleared safely by
  `_resolve_pending_blackout`; note-off waits until `_mask_owners` is also empty
  (`laser_executor.py:342-389`). Lifecycle resets release all smart owners and
  then resolve the pending latch (`laser_executor.py:80-98`,
  `laser_executor.py:395-399`).
- **[CONFIRMED]** Active-deck change, active-track load, idle entry, scripted/
  idle mode transition, stop, resume, director disable, and personality change
  all reach those executor clears (`state_manager.py:2118-2126`,
  `state_manager.py:2222-2235`, `state_manager.py:3314-3367`,
  `state_manager.py:5275-5330`, `state_manager.py:1710-1738`,
  `state_manager.py:2388-2401`). The drop-crossing executor branches and the
  StateManager no-drop-decision safety net also clear it
  (`laser_executor.py:133-286`, `state_manager.py:4882-4893`).
- **[CONFIRMED]** Emergency/manual blackout precedence is separate from clearing
  the smart latch. The director selects emergency/manual before automatic
  policy (`laser_director.py:371-392`), and pack output ORs manual input with
  executor smart state (`state_manager.py:3849-3884`). An emergency-clear
  command clears the director emergency state, not the executor pending latch
  (`state_manager.py:1769-1783`).
- **[CONFIRMED]** Shutdown zeroing also does not clear the in-memory latch; it
  makes hardware safe by zeroing pack output and releasing held MIDI notes as
  the process stops (`__main__.py:1798-1817`, `midi_output.py:101-113`). The
  lane report should call these precedence/teardown guarantees, not smart-latch
  release paths.
- **[CONFIRMED]** This wording error does not reveal a stranded-dark path in the
  existing latch/refcount implementation. It does overstate what the audit
  independently proved.

### 5. Low residual — a rejected MIDI blackout-on is latched and never retried

- **[CONFIRMED]** `trigger_blackout_on()` sets the pending latch before checking
  configuration or backend acceptance. A rejected backend records the error but
  leaves the latch true, so later persistent arm ticks hit the idempotency guard
  and do not retry (`laser_executor.py:321-340`). The blackout-rewire test pins
  this behavior (`tests/test_laser_blackout_rewire.py:89-96`).
- **[CONFIRMED]** For the native pack path this is intentional and safe because
  frame masking reads the latched smart state independently of MIDI acceptance
  (`docs/architecture/laser_blackout_authority.md:62-69`,
  `state_manager.py:3849-3884`).
- **[UNKNOWN]** For legacy physical MIDI, one transient queue/backend rejection
  can still mean no visible blackout for that drop even after the core AWR-206
  reachability fix. This predates AWR-206 and is not a stranded-dark hazard, but
  the next implementation review should decide whether MIDI mode needs one
  bounded retry while the arm level remains active.

## Attack-surface results

- **[CONFIRMED] Live-mixing hazards:** current AWR-206 cannot newly strand the
  lasers dark because it cannot arm through the intended runtime state. The
  existing pending-latch, mask-owner, lifecycle, crossing, and shutdown paths
  are otherwise internally consistent (`laser_executor.py:321-399`,
  `state_manager.py:4882-4893`, `state_manager.py:5327-5346`).
- **[CONFIRMED] Precedence:** emergency and manual decisions remain ahead of all
  automatic policy; master-switch/breakdown/pre-chorus owners remain refcounted;
  manual pack blackout remains a separate owner system; pack/shutdown zeroing
  remains above scene rendering (`laser_director.py:371-392`,
  `laser_executor.py:357-399`, `docs/architecture/laser_blackout_authority.md:27-81`).
- **[CONFIRMED] Double-arm/re-entrancy:** the executor latch prevents repeated
  blackout-on MIDI after one accepted or rejected first attempt
  (`laser_executor.py:327-340`). No double-arm MIDI spam was found.
- **[CONFIRMED] Updated tests:** the removed assertions match the intended local
  gate change, but the replacement tests omit the policy layer that makes the
  new branch unreachable (`tests/test_laser_executor.py:976-1106`,
  `tests/test_laser_executor.py:1360-1387`).
- **[CONFIRMED] Scene/blackout divergence:** current production emits neither
  scene nor blackout when `autoloop_ready=False`. Any correction must carry
  blackout arm intent across readiness without advancing the director's scene
  state or firing scene MIDI (`laser_director.py:241-292`,
  `laser_executor.py:140-157`).
- **[CONFIRMED] INFO logging:** the current line is unreachable for the named
  cause, and its once-per-drop volume premise contradicts the level-latched arm
  behavior (`laser_executor.py:133-156`, `state_manager.py:4827-4837`).

## Verification

- **[CONFIRMED]** Reviewed code at HEAD `a59022f`; AWR-206 runtime/test content
  remains the named `d95d7ce` change, with docs in `f0da6b1`.
- **[CONFIRMED]** Focused software suites passed: `test_laser_executor` (88),
  `test_laser_executor_lifecycle` (10), `test_laser_blackout_rewire` (7),
  `test_laser_director` (180), and `test_laser_reset_wiring` (6): 291 total.
- **[CONFIRMED]** The pure production-path reproduction used no bridge process,
  MIDI device, SoundSwitch, config write, or hardware. It returned idle/no scene
  and sent zero backend calls under `autoloop_ready=False` plus an arm signal.
- **[UNKNOWN]** No room-visible behavior was hardware-validated. The original
  30-intent/0-send and 3/3-send observations remain historical lane evidence,
  not evidence that AWR-206 works after restart.

## Required fix gate

- **[CONFIRMED]** Required before live activation: route blackout arm intent
  independently past the director's `autoloop_ready` scene gate; preserve the
  director's emergency/manual precedence and scene-state behavior; keep scene
  MIDI strict-gated; rate-limit the diagnostic; and add the real two-object
  integration test described in Finding 1.
- **[CONFIRMED]** Re-run the focused laser suites, the crossing/lifecycle tests,
  and the three hard docs checks after the correction. Update the AWR-206 status
  text that currently claims the relaxed path is implemented
  (`docs/subsystems/laser.md:46`,
  `docs/architecture/laser_blackout_authority.md:128-150`,
  `docs/status/active_work_registry.md:110`).
- **[CONFIRMED]** No restart, toggle, MIDI send, hardware check, or live command
  is authorized by this review. A later operator-approved restart is the first
  room-visible gate only after the required fix and independent re-review land.

## Operator closeout

- **[CONFIRMED] What should change live now:** nothing. AWR-206 is staged, and
  this review changed no runtime code. Even after a restart, current code should
  not be expected to restore the missing pre-drop blackout during autoloop churn.
- **[CONFIRMED] What remains unchanged:** SoundSwitch scenes, emergency/manual
  laser precedence, master-switch masks, LED/Govee behavior, Rekordbox reader
  state, and shutdown zeroing were not changed by this review.
- **[CONFIRMED] Healthy recognition:** until corrected, logs may continue to
  show smart-drop blackout arm intents without matching `[LX] blackout_on sent`
  during churn; the new INFO skip line will not explain that real path.
- **[CONFIRMED] What to watch after a later approved fix:** one blackout-on per
  pre-drop window, no buildup/scene MIDI while the strict gate is closed,
  blackout-off at the crossing or lifecycle exit, no per-tick INFO flood, and
  no change in SoundSwitch, LED/Govee, or Rekordbox-reader behavior.
- **[UNKNOWN] Hardware state:** no physical laser, MIDI, DMX, Enttec,
  SoundSwitch, LED/Govee, or Rekordbox runtime was observed. Status remains
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
