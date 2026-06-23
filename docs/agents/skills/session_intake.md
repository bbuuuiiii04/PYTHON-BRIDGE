---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# Skill: session intake

Use this when the maintainer gives a broad, unclear, emotional, or high-energy task. The goal is to turn the request into a bounded implementation or review unit before any file is edited.

## Inputs

- Maintainer request.
- Current branch or PR, if any.
- Any known target subsystem/device.

## Required reading

1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. The matching task playbook, if one exists.
4. The matching subsystem card, if one exists.

Do not read old plans, prompts, history, or archive first.

## Procedure

1. Restate the task in one sentence.
2. Classify it as small, medium, or large using `AGENTS.md`.
3. Pick the likely contract key.
4. List exact code/config/docs files to inspect.
5. List tests/checks required by the contract.
6. Identify assumptions that must not be made.
7. Identify stop conditions.
8. Recommend one next action: proceed, split, review first, or abandon.

## Output

```text
Task sentence:
Task size:
Contract key:
Likely subsystem:
Read path:
Files to inspect:
Docs/tests required:
Forbidden assumptions:
Stop conditions:
Recommendation:
```

## Good intake behavior

- Push back on scope creep.
- Convert “make it better” into measurable behavior.
- Treat hardware claims as unvalidated until evidence exists.
- Say “unknown” when code/docs have not been checked.

## Bad intake behavior

- Editing code during intake.
- Reading the whole repo.
- Treating old plans as current truth.
- Claiming support/validation from vibes.
