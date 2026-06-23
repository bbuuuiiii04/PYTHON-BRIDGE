---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# Agent skills

Skills are reusable micro-workflows for common agent jobs. They are not new authority. `AGENTS.md`, `docs/agents/change_contracts.yml`, code, tests, and validation docs still win.

Use only the skill that matches the current job. Do not read every skill by default.

| Skill | Use when | File |
| --- | --- | --- |
| Session intake | A request is vague, broad, exciting, or risky | `docs/agents/skills/session_intake.md` |
| Implementation guardrails | An agent is about to edit code/docs | `docs/agents/skills/implementation_guardrails.md` |
| Adversarial review | A PR/diff needs a fresh-context attack | `docs/agents/skills/adversarial_review.md` |
| Hardware validation handoff | The change touches live SoundSwitch, Govee, lasers, DMX, MIDI, or Rekordbox runtime behavior | `docs/agents/skills/hardware_validation_handoff.md` |

## Skill rules

- Start with `AGENTS.md`.
- Pick the matching change contract before touching code.
- Keep scope narrow.
- Produce evidence, not confidence.
- Preserve conservative project status unless validation docs prove more.

## Skill output format

Every skill should end with:

```text
Decision: proceed / hold / split / abandon
Contract key: <key or none>
Files inspected: <paths>
Files changed: <paths or none>
Checks/tests: <commands + results or not run + reason>
Uncertainty: <what is still unknown>
Next action: <one concrete step>
```
