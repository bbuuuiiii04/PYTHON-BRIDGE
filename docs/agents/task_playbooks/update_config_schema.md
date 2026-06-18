---
doc_status: current
truth_level: code-verified
last_verified_commit: 9ed183f
last_verified_date: 2026-06-18
validation_scope: software-only
---

# Task: config schema changes

Use when:
- The requested work is specifically about config schema changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/config.md`
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
- Inspect `config.py`, `laser_config.py`, `led_config.py`, `config/*.example.json`.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For LED `color_engine` strategy fields, document defaults, accepted values, `slot_mono_chance_by_look` range validation when relevant, and invalid-config behavior in the setup and subsystem docs.
- For M2.5 slot-cue example changes, keep legacy color-suffix looks defined until the gated cleanup patch and document that solid slots 0-4 remain possible through point/mono palettes.

Required tests:
- Run the targeted tests listed in the subsystem card.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.

Required docs updates:
- `docs/subsystems/config.md`
- `docs/setup/configuration.md`
- `docs/status/feature_status_matrix.md`
- tracked config examples
- config tests
- `docs/agents/task_playbooks/update_config_schema.md` if workflow guidance changes

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
