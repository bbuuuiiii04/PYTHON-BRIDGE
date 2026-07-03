---
doc_status: current
truth_level: code-verified
last_verified_commit: 1ee870f
last_verified_date: 2026-07-02
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
- Inspect `led_*`, `govee_*`, `beat_sync_engine.py`, `state_manager.py` dispatch seam.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For scripted-track LED automation, preserve the split between `safety.scripted_mode_automation` as the master switch (the shipped example config enables it; the `LEDSafety` dataclass default stays `false`) and the top-level `scripted_mode` role-remap policy. `utility` is a blackout destination only; verify active and off role transitions separately.
- For StateManager LED automation timing changes, keep the push-loop path pure/non-blocking, keep source arming at the content-change event, and prove arm/release/cleanup in `tests/test_led_state_manager.py`.
- For color-engine slot behavior, verify `resolve_slot_colors()` invariants and slot strategy config validation before updating setup/status docs.
- For M2.5 slotized cues, keep `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED` language until operator hardware visual sign-off covers sparkle hue stability, center-burst band split, strobe gating, drop snap behavior, Patch E visual balance, Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation.
- `drop_lifecycle.py` is a pure flat-window parity seam used by laser policy. The live LED resolver remains in `StateManager`; do not redirect LED runtime through the shared resolver without a separate approved change.

Required tests:
- Run the targeted tests listed in the subsystem card.
- For active-content LED hold or role-gate changes in `StateManager`, run `python3 -m unittest tests.test_led_state_manager`.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.
- For M2.5 slot-cue work, include every existing `tests/test_led_color_engine_m2_patch_*.py` file, including the newest Patch F file when present.
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
