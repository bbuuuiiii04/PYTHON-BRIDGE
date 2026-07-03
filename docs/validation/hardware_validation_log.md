---
doc_status: current-incomplete
truth_level: code-and-config-grounded
last_verified_commit: e876cfb
last_verified_date: 2026-07-02
validation_scope: software-validated only, except the Govee/LED color-engine, realtime-comet, and beat-sync paths (AWR-101–104) which carry operator hardware sign-off on Home Govee (2026-06-29); SoundSwitch / laser / Enttec remain hardware-unvalidated
---

# Hardware Validation Log

Current repo-facing hardware validation status:

> **HARDWARE-UNVALIDATED**

The current exporter/importer evidence boundary is **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

The pinned SoundSwitch 2.10.3 project/pack tooling, immutable loader/player,
MIDI-input adapter, output backends, Enttec sender, default-off config/startup,
StateManager scripted driver, runtime controller, and copied RW-5 status have
software validation only. The passive SoundSwitch U0 parity fixtures and static
assertion fallback are software/wire evidence only; they do not validate Enttec
delivery or physical fixture output, and remaining active `unverified_parity`
documents still block trusted direct-DMX publication. Current ignored-config/runtime/device state was not
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
| 2026-06-29 | Govee/LED color/comet/beat-sync (AWR-101–104) | Home Govee (hardware) | bridge HEAD 2026-06-29; live LED config (gitignored) | operator ran the rig and observed M2.5 slot cues (Patch E1/E2/E3), color-engine core (decoupled color/drift/drop-snap), realtime comet (stutter/smoothness/pause), and beat-sync against spec | PASS — operator visual sign-off | this log entry | visual sign-off, not instrumented capture; code-milestone re-audit for AWR-102/103/104 not separately performed |
| pending | Govee/LED remaining (AWR-105/106) | pending | pending | scripted groove/drop/post-drop blackout policy (AWR-105); Patch S solid-color outcomes + Patch F default-bank rotation (AWR-106); Patch D stable-hue sparkle; center-burst 0-2 / 2-4 accent band split | pending | pending | software-tested only; need operator visual sign-off. The AWR-101–104 paths were signed off 2026-06-29 (row above). |
| pending | Govee/LED phrase-aware active-content hold | pending | current StateManager LED automation; live LED config not inspected | active deck switch and active-deck track load landing more than `1.0` beat into phrase should keep the previous look until the incoming track reaches a phrase entry; landing within `1.0` beat should change immediately | pending | pending | software-tested only; needs operator visual sign-off that mid-phrase switch/load no longer pops and that missing phrase data holding the prior look is acceptable live |

## Validation records

```text
Date: 2026-06-29
Commit: docs change in the adb5511 cleanup series
Operator: Brandon
OS version: macOS (Darwin 24.3.0)
Rekordbox version: 7.2.11
SoundSwitch version: n/a — Govee/LED path, SoundSwitch not involved
Lighting hardware: Home Govee strip(s), LAN / realtime path
Config files used, with secrets redacted: live LED look-director + color-engine config (gitignored; Govee key in govee.env)
Test steps: ran the bridge live on the home rig and observed the four LED workstreams during normal play — M2.5 slot cues (Patch E1 nebula, E2 center-comet, E3 ambient twinkle), color-engine core (decoupled color, drift, drop-snap), realtime comet (stutter / smoothness / pause), beat-sync runtime
Observed results: all four behaved per spec on hardware
Pass/fail: PASS
Caveats: operator visual sign-off, not an instrumented capture; covers AWR-101–104 only. AWR-105 (role mapping) and AWR-106 (solid-color + Patch F) were NOT signed off and remain hardware-pending. Code-level milestone audit for AWR-102/103/104 was not separately performed; sign-off is on observed running behavior.
Rollback notes: docs-only record; no runtime/config change.
```

## Claim rule

Do not change support/status docs from hardware-unvalidated to hardware-validated unless this file contains a repeatable validation record and the supporting evidence is committed or explicitly referenced.
