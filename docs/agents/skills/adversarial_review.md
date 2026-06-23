---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# Skill: adversarial review

Use this for fresh-context PR/diff review. The reviewer should not be the same agent that implemented the change.

## Required reading

1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. Relevant task playbook
4. Relevant subsystem card
5. Changed files and tests

Do not read old prompts/plans as authority. Use them only as historical evidence if the current code/docs are insufficient.

## Review attack checklist

- Is the contract key correct?
- Did every required doc in `docs_update` change when behavior changed?
- Did tests actually cover the changed behavior?
- Did the change quietly alter unrelated runtime behavior?
- Did any hot path gain blocking I/O?
- Did `StateManager` remain the runtime owner where required?
- Did status wording stay conservative?
- Did the PR claim hardware/device support without validation evidence?
- Are secrets, local IPs, device IDs, live config, or backups present?
- Are failures hidden by deleting/weakening tests?

## Output

```text
Review verdict: approve / hold / reject
Contract key checked:
Changed files reviewed:
Blocking issues:
Non-blocking issues:
Missing tests/checks:
Missing docs:
Unsafe or overclaimed validation language:
Recommended repair prompt:
```

## Merge rule

Approve only when there are no blocking issues and the remaining uncertainty is explicitly documented. “Probably fine” is not a merge criterion.
