---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
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

The SoundSwitch project/pack tooling is not a live lighting-output claim. For
the pinned SoundSwitch 2.10.3 canonical UUID/RAVE profile, strict decode,
deterministic new-path export, independent verification, immutable pack
loading/rendering, MIDI-input routing, backend abstraction, config/startup,
StateManager scripted driving, commands/status, and Enttec framing/sending have
software tests. The current proof gate is 29 PASS / 0 FAIL / 0 INCOMPLETE.
Direct-DMX code exists but is default-off, locally unconfigured, and
hardware-unvalidated. Scripted runtime gaps and T7d capture/native-Autoloop work
remain listed in the active roadmap.

| Output | Status | Evidence | Notes |
| --- | --- | --- | --- |
| SoundSwitch OS2L | implemented | code path exists | Exact SoundSwitch version support unknown. |
| SoundSwitch scripted pack/direct DMX | partial, default-off | current-project proof plus player/startup/driver/sender tests | 32/32 active scripts supported; pause/mode/input-health/status closure and physical validation remain. |
| SoundSwitch native-DMX Autoloops | blocked | pure renderer/capture-tool tests plus 4 conductor-integrity-accepted live wire captures | Arm/refire each have two accepted captures, but four scenario pairs and the unique corpus oracle remain; no phase contract; automatic base remains zero. |
| Laser MIDI | implemented | code path plus lifecycle unit/integration tests | Default-on gated drop/post-drop cycling, shuffle-bag selection, static-impact fallback, and kill-switch-OFF legacy behavior are software-tested. Broad fixture/safety validation is not documented. |
| LED/Govee cloud scene | implemented | code path exists | Scripted groove/drop/post-drop blackout mapping is software-tested and the shipped example config now enables the master switch (`true`) with the conservative blackout policy; device support and room-visible behavior are not generalized. |
| LED/Govee realtime | implemented/experimental | code path exists | Slot-color strategy behavior, Patch S `random_with_mono_chance`, generic M2.5 groove/post_drop/drop/Patch E1 nebula/Patch E2 center-comet/Patch E3 twinkle cues, and Patch F default-bank cleanup are software-tested only; current H612D setup must be validated through hardware log before broad claims. |

## Hardware validation state

| Scope | Status |
| --- | --- |
| My current local rig | locally operational, but repo validation record incomplete |
| Repeatable hardware validation in repo | missing |
| Broad hardware compatibility | not claimed |
| Show-ready claim | not allowed |
| Production-ready claim | not allowed |
