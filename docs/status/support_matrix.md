---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 51367a1
last_verified_date: 2026-06-18
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Support Matrix

This matrix is deliberately conservative. If evidence is missing, the answer is `unknown`, not “probably works.” Computers punish “probably.”

## Rekordbox versions

| Version | Status | Evidence | Notes |
| --- | --- | --- | --- |
| My current local version | local-setup-operational | operator-local knowledge, not yet captured as repo validation | Exact version must be recorded. |
| Rekordbox 7.2.11 | code-referenced | `rb_memory.py` comments reference `get-task-allow` confirmation | This is not broad 7.x support. |
| Other Rekordbox 7.x | unknown | no matrix evidence | Offset validation required. |
| Rekordbox 6.x | unknown | app path fallback exists, but support is not proven | Do not claim support. |
| Future versions | unknown/unsupported until validated | none | Offsets may break. |

## Operating systems

| OS | Status | Evidence | Notes |
| --- | --- | --- | --- |
| macOS local setup | local-setup-operational | current project architecture and local use | Exact macOS version matrix needed. |
| Other macOS versions | unknown | no compatibility matrix evidence | Must be tested. |
| Windows | unsupported/unknown | current memory reader is macOS Mach-based | Would require separate reader strategy. |
| Linux | unsupported/unknown | current memory reader is macOS Mach-based | Not current scope. |

## Lighting outputs

| Output | Status | Evidence | Notes |
| --- | --- | --- | --- |
| SoundSwitch OS2L | implemented | code path exists | Exact SoundSwitch version support unknown. |
| Laser MIDI | implemented | code path exists | Broad fixture/safety validation not documented. |
| LED/Govee cloud scene | implemented | code path exists | Device support not generalized. |
| LED/Govee realtime | implemented/experimental | code path exists | Slot-color strategy behavior, Patch S `random_with_mono_chance`, generic M2.5 groove/post_drop/drop/Patch E1 nebula/Patch E2 center-comet/Patch E3 twinkle cues, and Patch F default-bank cleanup are software-tested only; current H612D setup must be validated through hardware log before broad claims. |

## Hardware validation state

| Scope | Status |
| --- | --- |
| My current local rig | locally operational, but repo validation record incomplete |
| Repeatable hardware validation in repo | missing |
| Broad hardware compatibility | not claimed |
| Show-ready claim | not allowed |
| Production-ready claim | not allowed |
