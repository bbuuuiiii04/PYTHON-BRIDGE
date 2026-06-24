---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: 988d73a
last_verified_date: 2026-06-23
validation_scope: independent review of RW-1A implementation commits 1908737 and 988d73a; review-only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no live/runtime mutation authorized
---

# Independent implementation review — RW-1A shutdown ownership

You are the independent adversarial reviewer for RW-1A in
`/Users/bbui/rb_ss_bridge_v2`.

This is **review-only**. Do not edit files, commit, push, change configuration,
start/restart/stop the bridge, append runtime commands, enable pack output, open
MIDI/serial/Enttec/DMX devices, or perform fixture-visible testing. Read-only
inspection and offline tests that write only to `/tmp` are allowed.

## Review target

```text
Branch: soundswitch/rw1-export-from-ss
Implementation base: 584dd20
Implementation head: 988d73a
Implementation commits:
  1908737 fix(soundswitch): zero live pack runtime on shutdown
  988d73a test(soundswitch): cover swapped sender shutdown
Spec: docs/plans/active/soundswitch_rw1a_shutdown_ownership_spec.md
Allowed implementation files:
  __main__.py
  tests/test_soundswitch_pack_startup.py
```

Review the fixed range `584dd20..988d73a`, even if the current HEAD also
contains this review-prompt commit. Confirm the implementation range changes
only the two allowed files.

## Required source order

1. Read `AGENTS.md` completely and `PRIVATE_OPERATOR_PROFILE.md` if present.
2. Read the RW-1A spec named above.
3. Inspect `git diff 584dd20..988d73a` and resolve all anchors against current
   code rather than trusting the spec's line numbers.
4. Inspect the relevant current implementations in:
   - `__main__.py`
   - `state_manager.py`
   - `soundswitch_pack_controller.py`
   - `soundswitch_pack_runtime.py`
   - `soundswitch_frame_sender.py`
   - `soundswitch_midi_input.py`
   - `tests/test_soundswitch_pack_startup.py`
5. Read `docs/architecture/runtime_invariants.md` and
   `docs/subsystems/soundswitch_output.md` only as secondary evidence. Code and
   tests win when documentation conflicts.

## Claims to verify independently

- Before `StateManager` exists, shutdown touches only the startup-owned sender
  and MIDI input.
- Immediately after `StateManager(...)` construction, shutdown can retrieve the
  current immutable `PackRuntime` through one `get_pack_runtime()` call.
- After an enable/reload/backend runtime swap, graceful shutdown stops the live
  sender/input rather than only the stale startup owners.
- The live runtime is stopped before startup-owned slots are drained.
- The no-swap case safely calls `.stop()` on the same sender/input through both
  ownership paths. Verify the real sender and MIDI-input implementations make
  this safe; do not accept the spec's idempotency claim without code evidence.
- SIGINT, SIGTERM, startup failure, normal exit/atexit, and repeated cleanup do
  not skip a required owner or raise out of cleanup.
- Disabled/default-off runtime remains a guarded no-op and never enables a
  backend, opens a port, or falls back to physical MIDI.
- `_cleanup_pack_outputs()` remains before watcher/thread joins and `sm.stop()`.
- No filesystem, socket, MIDI, serial, sleep, retry, or other blocking work was
  added to `_push_tick`, `StateManager._run()`, or any 200 Hz path.
- OS2L, laser, LED/Govee, Rekordbox-reader, runtime-command, logging, and pack
  selection behavior remain unchanged outside graceful pack-output cleanup.
- `kill -9` remains explicitly unsupported as a safe blackout path.

## Attack these risks hardest

1. **Concurrent swap during shutdown.** `_shutdown` calls pack cleanup before
   stopping the command reader. Determine whether a command-thread swap can
   publish a new live runtime after the helper's atomic read, leaving that new
   sender unclosed. Classify this as confirmed, theoretical but reachable, or
   impossible, with exact code evidence.
2. **Double-stop safety.** Trace both `SoundSwitchFrameSender.stop()` and every
   concrete MIDI-input `.stop()` reached in the no-swap case. Check whether
   repeated cleanup is truly idempotent, including signal followed by atexit.
3. **Failure swallowing.** Determine whether broad exception suppression can
   strand a live owner without any operator-visible evidence, and whether that
   is pre-existing policy or a new material risk.
4. **Startup windows.** Examine every point between owner-slot creation, worker
   construction/start, `StateManager` construction, and `_sm_holder` publication.
5. **Test strength.** Confirm the behavioral tests prove live-swapped cleanup,
   startup-window behavior, disabled-runtime neutrality, both startup slots,
   and source ordering. Identify missing acceptance coverage or false-positive
   assertions.
6. **Scope and docs.** The implementation deliberately followed the spec's
   two-file boundary. The advisory staleness check reports `core_bridge`,
   `runtime_commands`, and `soundswitch_pack_player` stale. Decide whether this
   is acceptable follow-up documentation debt or a merge blocker; do not edit
   the docs during this review.

## Verification

Run the smallest useful set. At minimum:

```bash
cd /Users/bbui/rb_ss_bridge_v2
git status --short --branch
git diff --name-only 584dd20..988d73a
python3 -m unittest tests.test_soundswitch_pack_startup
python3.11 -m unittest tests.test_soundswitch_pack_startup
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check 584dd20..988d73a
```

You may rerun the full suite and offline pack-generation proof if useful. Do
not treat software tests as hardware validation.

## Required response

Return the review in chat without modifying the repo:

1. Verdict: exactly `APPROVE`, `REVISE-AND-APPROVE`, or `REJECT`.
2. Findings first, ordered by severity, with `path:line`, concrete failure mode,
   and why it matters live. If none, say `No findings.`
3. Verification commands and exact result summaries.
4. Explicit conclusions for the concurrent-swap race, no-swap double-stop,
   pre-/post-`sm` windows, default-off neutrality, push-loop isolation, and
   two-file scope.
5. Residual risks and missing evidence, preserving the label
   **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

