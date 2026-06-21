---
doc_status: current-incomplete
truth_level: code-and-config-grounded
last_verified_commit: 51367a1
last_verified_date: 2026-06-21
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Hardware Validation Log

Current repo-facing hardware validation status:

> **HARDWARE-UNVALIDATED**

The current exporter/importer evidence boundary is **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

Tasks 1–2 provide strict read-only decode, deterministic canonical 95-artifact export, and independent verification for the pinned SoundSwitch 2.10.3 canonical project. They are software/wire-validated only and do not mutate a project or drive OS2L, MIDI lasers, LED/Govee, Rekordbox, or Enttec hardware. Task 3 loader/player and Task 4+ MIDI/runtime/backend integration remain planned and unimplemented. Enttec process death must not be treated as a hard kill because its last frame may remain latched; explicit blackout/hard-kill behavior is future work requiring hardware validation.

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
| pending | Enttec exporter/player backend | pending | unimplemented | explicit blackout/hard-kill and last-frame behavior | pending | pending | process death is not accepted as a hard kill; future hardware-validation gate |
| pending | Laser MIDI | pending | pending | pending | pending | pending | no repeatable repo evidence yet |
| pending | Govee/LED | pending | pending | pending | pending | pending | no repeatable repo evidence yet; scripted groove/drop/post-drop blackout policy, slot-color strategy, Patch S probabilistic solid-color outcomes, generic groove/post_drop/drop slot cues, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, and Patch F default-bank cleanup are software-tested only; scripted blackout/active-role transitions, Patch D stable-hue sparkle, center-burst 0-2 / 2-4 accent band split, Patch E1/E2/E3 visuals, Patch S solid outcomes, and Patch F generic-default rotation need operator visual sign-off |

## Claim rule

Do not change support/status docs from hardware-unvalidated to hardware-validated unless this file contains a repeatable validation record and the supporting evidence is committed or explicitly referenced.
