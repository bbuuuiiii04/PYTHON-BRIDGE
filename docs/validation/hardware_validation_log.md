---
doc_status: current-incomplete
truth_level: code-and-config-grounded
last_verified_commit: 4138c61
last_verified_date: 2026-06-24
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Hardware Validation Log

Current repo-facing hardware validation status:

> **HARDWARE-UNVALIDATED**

The current exporter/importer evidence boundary is **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

The pinned SoundSwitch 2.10.3 project/pack tooling, immutable loader/player,
MIDI-input adapter, output backends, Enttec sender, default-off config/startup,
StateManager scripted driver, runtime controller, and copied RW-5 status have
software validation only. Current ignored-config/runtime/device state was not
inspected during RW-5 implementation. Owner-driven Enttec stop sends zero, but process
death/`kill -9` can leave the last frame latched; a physical kill path and
explicit hardware gate remain mandatory.

The reusable procedure is `soundswitch_hardware_validation_procedure.md`; copy
`soundswitch_hardware_runs/TEMPLATE.md` for a real operator run. These documents are not evidence
that a run occurred.

My local setup may be operational, but this repo does not yet contain repeatable hardware-validation records sufficient to claim hardware support.

## Required entry template

```text
Date:
Commit:
Operator:
OS version:
Rekordbox version:
SoundSwitch version:
Lighting hardware:
Config files used, with secrets redacted:
Test steps:
Observed results:
Pass/fail:
Caveats:
Rollback notes:
```

## Tracking table

| Date | Area | Hardware/software | Version/config | Test performed | Result | Evidence path | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pending | SoundSwitch | pending | pending | reviewed procedure/template available | pending | pending | no repeatable repo evidence yet |
| pending | Enttec exporter/player backend | pending | software/startup/status lane implemented; current live config not inspected | zero preflight, one scripted track, controls/masks, emergency physical kill, known-dark reset, graceful closeout | pending | pending | process death is not accepted as a hard kill; no operator run occurred |
| pending | Laser MIDI | pending | lifecycle default-on; local ignored config | gated drop impact, 32-beat hold, post-drop/drop fallback cycling, shuffle-bag order, blackout release, and kill switch | pending | pending | lifecycle is software-tested only; verify no drop leak during groove/buildup and no dark initial hit before any hardware-validated claim |
| pending | Govee/LED | pending | pending | pending | pending | pending | no repeatable repo evidence yet; scripted groove/drop/post-drop blackout policy, slot-color strategy, Patch S probabilistic solid-color outcomes, generic groove/post_drop/drop slot cues, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, and Patch F default-bank cleanup are software-tested only; the pure laser lifecycle parity helper does not change live LED behavior; scripted blackout/active-role transitions, Patch D stable-hue sparkle, center-burst 0-2 / 2-4 accent band split, Patch E1/E2/E3 visuals, Patch S solid outcomes, and Patch F generic-default rotation need operator visual sign-off |

## Claim rule

Do not change support/status docs from hardware-unvalidated to hardware-validated unless this file contains a repeatable validation record and the supporting evidence is committed or explicitly referenced.
