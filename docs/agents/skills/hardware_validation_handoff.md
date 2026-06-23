---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# Skill: hardware validation handoff

Use this when a change touches live Rekordbox state, SoundSwitch, Govee LEDs, MIDI lasers, DMX/Enttec, network device output, or visible lighting behavior.

Agents may prepare the handoff. The operator supplies the real-world evidence. Until that evidence is recorded, hardware behavior remains hardware-unvalidated.

## Required handoff fields

```text
Feature/path:
Date:
Operator:
Machine/OS:
Rekordbox version:
SoundSwitch version, if relevant:
Govee model/firmware/app assumptions, if relevant:
Laser fixture/interface/mapping, if relevant:
DMX/Enttec/interface details, if relevant:
Config used, sanitized:
Branch/commit:
Exact run commands:
Expected visible behavior:
Observed visible behavior:
Pass/fail/unknown:
Safety notes:
Manual override/blackout behavior:
Logs/status files captured:
Remaining unknowns:
```

## Handoff rules

- Do not put API keys, local IPs, device IDs, or live config values into docs.
- Do not generalize from one device to all devices.
- Do not claim broad compatibility from one local setup.
- Separate software/wire evidence from physical fixture behavior.
- Record failures and weirdness. Weirdness is data, not shame.

## Status update rule

Update `docs/validation/hardware_validation_log.md`, support/status matrices, or public wording only when evidence is actually supplied. Otherwise create a checklist and leave the status as hardware-unvalidated.
