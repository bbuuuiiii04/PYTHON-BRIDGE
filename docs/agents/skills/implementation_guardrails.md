---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# Skill: implementation guardrails

Use this when an agent is about to edit files.

## Required preflight

Before editing, report:

```text
Branch:
Approved scope:
Contract key:
Files allowed to change:
Docs expected to change:
Tests/checks expected:
Explicit non-goals:
```

If the agent cannot fill this out, it is not ready to edit.

## Editing rules

- Make the smallest diff that satisfies the approved scope.
- Do not reformat unrelated files.
- Do not move modules to “fix” imports.
- Do not change tests merely to pass a broken implementation.
- Do not commit secrets, local IPs, device IDs, live config, or backup files.
- Do not claim hardware validation from software tests.
- For runtime changes, preserve `StateManager` ownership and keep the 200 Hz push loop free of blocking I/O.

## Required final report

```text
Summary:
Files changed:
Behavior changed:
Docs updated:
Tests/checks run:
Tests/checks not run:
Validation status language preserved:
Uncertainty:
Reviewer focus areas:
```

## Stop instead of editing when

- the task crosses subsystem boundaries not covered by the selected contract;
- the needed behavior requires hardware evidence;
- code and docs disagree and the correct source cannot be verified;
- implementing the feature would require committing live config or secrets;
- the maintainer request conflicts with a safety invariant.
