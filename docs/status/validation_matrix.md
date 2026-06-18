---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: c9db322
last_verified_date: 2026-06-18
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Validation Matrix

This page separates software tests from hardware validation. They are not the same thing, because reality remains rude.

Current repo-facing status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

## Validation levels

| Level | Meaning |
| --- | --- |
| software-tested | Unit/integration/replay/static tests exist. |
| docs-checkable | Lightweight repo/docs checks can verify routing, metadata, and selected code/doc consistency. |
| operator-local | I have run it locally, but the repo does not contain repeatable validation evidence. |
| hardware-validated | A repeatable hardware validation log exists in `docs/validation/hardware_validation_log.md`. |
| unvalidated | No useful evidence yet. |
| unknown | Not inspected or not enough evidence. |

## Current validation summary

| Area | Software validation | Hardware validation | Notes |
| --- | --- | --- | --- |
| Core runtime/event/state | partial | unvalidated | Tests exist across state snapshots and runtime behavior, but hardware is separate. |
| Runtime command docs | docs-checkable | not applicable | `tools/check_docs_drift.py` checks command docs against `runtime_status.py`. |
| Agent routing/contracts | docs-checkable | not applicable | `tools/check_agent_contracts.py` checks key routes and referenced files. |
| Rekordbox readers | partial | unvalidated | Reader correctness depends on live app/version/permissions. |
| SoundSwitch OS2L | partial | unvalidated | OS2L output code exists; hardware/app validation log needed. |
| Laser policy/executor | partial | unvalidated | MIDI path exists; fixture validation must be recorded separately. |
| LED/Govee cloud | partial | unvalidated | Cloud path exists; device behavior must be logged. |
| LED/Govee realtime | partial/experimental | unvalidated | Realtime path exists; slot-color strategy behavior, Patch S `random_with_mono_chance`, generic groove/post_drop/drop slot cues, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, and Patch E3 ambient twinkle slot cue have software tests, but repeatable H612D validation record is still needed. Patch D/E/S remain SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| Laser Pad/frontend | partial | unvalidated | Syntax/frontend smoke tests do not prove live safety. |

## Required hardware validation record

A hardware validation entry must include:

- commit SHA
- date
- OS version
- Rekordbox version
- SoundSwitch version
- device/fixture models
- config file path or redacted config hash
- exact test steps
- observed result
- pass/fail
- caveats
- rollback notes
