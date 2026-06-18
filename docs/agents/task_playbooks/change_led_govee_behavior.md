---
doc_status: current
truth_level: code-verified
last_verified_commit: 9ed183f
last_verified_date: 2026-06-18
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
- For color-engine slot behavior, verify `resolve_slot_colors()` invariants and slot strategy config validation before updating setup/status docs.
- For M2.5 slotized cues, keep `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED` language until operator hardware visual sign-off covers sparkle hue stability, center-burst band split, strobe gating, drop snap behavior, Patch E visual balance, and Patch S probabilistic solid-color outcomes.

Required tests:
- Run the targeted tests listed in the subsystem card.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.
- For M2.5 slot-cue work, include every existing `tests/test_led_color_engine_m2_patch_*.py` file, including the newest Patch S file when present.

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
