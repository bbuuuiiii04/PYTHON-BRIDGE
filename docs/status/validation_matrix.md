---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: eff532e
last_verified_date: 2026-06-21
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
| Runtime `[BEAT]` heartbeat | partial | unvalidated | `tests/test_runtime_status.py` covers heartbeat payload/log assembly and suppression, StateManager-published color-engine status, fail-soft provider handling, and throttled provider-failure warnings; no hardware behavior changes are implied. |
| Logging visibility live watch | partial | unvalidated | `tests/test_logging_diag_coverage.py` covers preset parseability, heartbeat visibility, module filtering, and error pass-through. `tests/test_bridge_fmt_rate.py` covers throttle/change primitives, including a small threaded throttle check. |
| Agent routing/contracts | docs-checkable | not applicable | `tools/check_agent_contracts.py` checks key routes and referenced files. |
| Rekordbox readers | partial | unvalidated | Reader correctness depends on live app/version/permissions. |
| SoundSwitch OS2L | partial | unvalidated | OS2L output code exists; hardware/app validation log needed. |
| SoundSwitch offline decoder/exporter/pack/verifier | software-tested | not applicable | Pinned to SoundSwitch 2.10.3 plus the canonical UUID/RAVE profile. Tests verify deterministic 95-artifact export, independent semantic verification, exact 232+1/32/42/45 inventory, seven-class F-3 crosswalk, and F9 mutation rejection. Current proof: 28 PASS / 0 FAIL / 1 INCOMPLETE, foundation 27/27 PASS; only F10 is deferred to Task 4. No project mutation or live output. |
| SoundSwitch loader/player/MIDI/runtime/backend/Enttec | unvalidated/planned | unvalidated | Task 3 and Task 4+ are not implemented; no config, commands, status, `StateManager`, backend, Enttec, or hardware path exists. |
| Laser policy/executor | partial | unvalidated | MIDI path exists; fixture validation must be recorded separately. |
| LED/Govee cloud | partial | unvalidated | Cloud path exists; device behavior must be logged. |
| LED scripted-track automation policy | partial | unvalidated | `tests/test_led_config.py` covers the JSON blackout defaults and `utility` destination validation; `tests/test_led_state_manager.py` covers groove/drop/post-drop blackout mapping, active buildup/breakdown, opt-in overrides, and non-scripted identity behavior. This does not prove room-visible Govee behavior during scripted SoundSwitch tracks. |
| LED/Govee realtime | partial/experimental | unvalidated | Realtime path exists; slot-color strategy behavior, Patch S `random_with_mono_chance`, generic groove/post_drop/drop slot cues, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, and Patch F default-bank cleanup have software tests, but repeatable H612D validation record is still needed. Patch D/E/S/F remain SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
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
