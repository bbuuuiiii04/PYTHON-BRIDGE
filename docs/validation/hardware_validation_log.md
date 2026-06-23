---
doc_status: current-incomplete
truth_level: code-and-config-grounded
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Hardware Validation Log

Current repo-facing hardware validation status:

> **HARDWARE-UNVALIDATED**

The current exporter/importer evidence boundary is **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

The pinned SoundSwitch 2.10.3 project/pack tooling, immutable loader/player,
MIDI-input adapter, output backends, Enttec sender, default-off config/startup,
StateManager scripted driver, and runtime controller have software validation
only. The local pack config was absent during the 2026-06-23 audit, so no live
pack backend was configured. Owner-driven Enttec stop sends zero, but process
death/`kill -9` can leave the last frame latched; a physical kill path and
explicit hardware gate remain mandatory.

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
| pending | SoundSwitch | pending | pending | pending | pending | pending | no repeatable repo evidence yet |
| pending | Enttec exporter/player backend | pending | software/startup lane implemented; local config absent | zero preflight, one scripted track, controls/masks, proven Autoloop only after T7d, disconnect/shutdown, hard-kill hazard | pending | pending | process death is not accepted as a hard kill; future operator-approved hardware gate |
| pending | Laser MIDI | pending | lifecycle default-on; local ignored config | gated drop impact, 32-beat hold, post-drop/drop fallback cycling, shuffle-bag order, blackout release, and kill switch | pending | pending | lifecycle is software-tested only; verify no drop leak during groove/buildup and no dark initial hit before any hardware-validated claim |
| pending | Govee/LED | pending | pending | pending | pending | pending | no repeatable repo evidence yet; scripted groove/drop/post-drop blackout policy, slot-color strategy, Patch S probabilistic solid-color outcomes, generic groove/post_drop/drop slot cues, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, and Patch F default-bank cleanup are software-tested only; the pure laser lifecycle parity helper does not change live LED behavior; scripted blackout/active-role transitions, Patch D stable-hue sparkle, center-burst 0-2 / 2-4 accent band split, Patch E1/E2/E3 visuals, Patch S solid outcomes, and Patch F generic-default rotation need operator visual sign-off |

## Claim rule

Do not change support/status docs from hardware-unvalidated to hardware-validated unless this file contains a repeatable validation record and the supporting evidence is committed or explicitly referenced.
