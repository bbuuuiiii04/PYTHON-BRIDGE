---
doc_status: current
truth_level: code-verified
last_verified_commit: 56c5f90
last_verified_date: 2026-07-03
validation_scope: software-only
---

# Task: LED/Govee behavior changes

Use when:
- The requested work is specifically about LED/Govee behavior changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/led_govee.md`
4. `docs/agents/change_contracts.md`

Do not read first:
- archive docs
- old prompts
- old plans
- unrelated subsystem cards

Allowed changes:
- The narrow files required by the task.
- Docs/status/test inventory files required by the change contract.

Forbidden changes:
- unrelated runtime behavior
- local ignored configs or backups
- support/validation claims without evidence
- test modifications just to hide failures

Implementation notes:
- Inspect `led_*`, `govee_*`, `beat_sync_engine.py`, `led_dispatch_policy.py`, and StateManager dispatch call sites.
- LED color-engine live controls are operator-reserved future pad/deck surfaces; if they become live
  from outside `StateManager`, route through `BridgeEvent`s or runtime commands.
- Committed drop-look selection must thread the same `diy_eligible` predicate used by normal
  `LEDLookDirector.tick()` automation.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For scripted-track LED automation, preserve the split between `safety.scripted_mode_automation` as the master switch (the shipped example config enables it; the `LEDSafety` dataclass default stays `false`) and the top-level `scripted_mode` role-remap policy. `utility` is a blackout destination only; verify active and off role transitions separately.
- For StateManager LED automation timing changes, keep the push-loop path pure/non-blocking, keep source arming at the content-change event, and prove arm/release/cleanup in `tests/test_led_state_manager.py`.
- For realtime-to-cloud handoff changes, `force_deactivate()` must not perform transport socket
  calls on the caller/push-loop thread; prove teardown on the runner thread in
  `tests/test_govee_realtime_runner.py`.
- The realtime frame trio runs in a bridge-owned child process (AWR-146): `govee_frame_engine.py`
  (`FrameEngineHost` + JSON-lines protocol + `main()`) and `govee_frame_engine_client.py`
  (`GoveeFrameEngineClient`, the in-bridge supervisor and drop-in for `GoveeRealtimeRunner`). Keep
  every client method the coordinator calls lock-and-flag (zero I/O on the caller thread); all IPC,
  spawning, respawn/replay, and IP re-resolution stay on the client thread. Fail-dark on EOF is
  `runner.stop()` (blackout + deactivate, never brightness-0 so cloud looks survive a restart); a
  pure-emergency respawn replays `emergency_stop` + an unconditional brightness-0. The runner change
  is only the additive `on_thread_start` hook. Prove host/client behavior in
  `tests/test_govee_frame_engine.py` and the real-subprocess fps/orphan proof in
  `tests/test_govee_frame_engine_integration.py`.
- For Govee cloud health-reporting changes, keep fixes reporting-only: log
  mirror send failure/recovery on state changes only, do not alter send order or
  queue/rate-limit behavior, and prove status healing in the sender/adapter
  tests.
- For color-engine slot behavior, verify `resolve_slot_colors()` invariants and slot strategy config validation before updating setup/status docs.
- For M2.5 slotized cues, keep `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED` language until operator hardware visual sign-off covers sparkle hue stability, center-burst band split, strobe gating, drop snap behavior, Patch E visual balance, Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation.
- `drop_lifecycle.py` is a pure flat-window parity seam used by laser policy. The live LED resolver remains in `StateManager`; do not redirect LED runtime through the shared resolver without a separate approved change.
- For LIGHTING ENGINE v2 identity work, preserve the v1-off compatibility gate, keep identity-store
  disk writes on writer/helper threads (never the 200 Hz push loop), route Stream Deck/runtime
  mutations through `BridgeEvent`s, and update the palette authority/design docs plus AWR-128.

Required tests:
- Run the targeted tests listed in the subsystem card.
- For active-content LED hold or role-gate changes in `StateManager`, run `python3 -m unittest tests.test_led_state_manager`.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.
- For Govee cloud health-reporting changes, run `python3 -m unittest tests.test_govee_runtime_sender tests.test_govee_scene_adapter`.
- For frame-engine child-process changes (AWR-146), run `python3 -m unittest tests.test_govee_frame_engine tests.test_govee_frame_engine_integration` (the integration suite is timing-sensitive and skips under `CI=true`).
- For M2.5 slot-cue work, include every existing `tests/test_led_color_engine_m2_patch_*.py` file, including the newest Patch F file when present.
- For LIGHTING ENGINE v2 identity work, include `tests/test_led_identity_v2.py`,
  `tests/test_led_color_engine.py`, `tests/test_color_engine_config.py`,
  `tests/test_led_palette_control.py`, `tests/test_soundswitch_midi_input.py`,
  `tests/test_streamdeck_midi.py`, `tests/test_runtime_status.py`, and the relevant
  StateManager LED tests.
- When changing the shared drop resolver, run `tests.test_drop_lifecycle` and the existing LED state-manager tests; pure parity does not prove live per-look-duration or offset parity.

Required docs updates:
- `docs/subsystems/led_govee.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/validation/hardware_validation_log.md`
- `docs/status/active_work_registry.md`
- `docs/agents/task_playbooks/change_led_govee_behavior.md` if workflow guidance changes

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
