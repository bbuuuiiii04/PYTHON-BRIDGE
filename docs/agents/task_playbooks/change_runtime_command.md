---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-only
---

# Task: runtime command changes

Use when:
- The requested work is specifically about runtime command changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/runtime_commands.md`
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
- Inspect `runtime_status.py`, `__main__.py`.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.

Required tests:
- Run the targeted tests listed in the subsystem card.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.

Required docs updates:
- `docs/setup/runtime_commands.md`, `docs/subsystems/runtime_commands.md`, parser/handler tests

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
