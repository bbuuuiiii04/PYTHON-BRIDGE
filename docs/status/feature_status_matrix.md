---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 9ed183f
last_verified_date: 2026-06-18
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Feature Status Matrix

Status vocabulary:

- `implemented`: runtime path exists in code.
- `software-tested`: tests exist or deterministic validation exists.
- `local-setup-operational`: I have it working locally, but repo hardware evidence is incomplete.
- `hardware-unvalidated`: no repeatable hardware-validation record in this repo.
- `experimental`: implemented or prototyped, but behavior may change.
- `partial`: some pieces exist, but important gaps remain.
- `planned`: not implemented yet.
- `unknown`: not enough evidence.
- `unsupported`: out of current scope.
- `stale/superseded`: old docs or plans no longer match code.

| Feature area | Implementation status | Validation status | Compatibility scope | Notes |
| --- | --- | --- | --- | --- |
| Core startup | implemented | software-tested indirectly | local setup | `__main__.py` wires the runtime components. |
| StateManager event/push loop | implemented | software-tested indirectly | local setup | Central owner for deck/runtime/lighting state. |
| SoundSwitch OS2L output | implemented | software-tested partially | local setup | Uses OS2L TCP and VirtualDJ-shaped messages. |
| Rekordbox memory position reader | implemented | software-tested partially | macOS local setup | macOS Mach APIs. Other OSes unsupported/unknown. |
| Rekordbox direct state reader | implemented | software-tested partially | current local Rekordbox only | Offset/version assumptions require validation per version. |
| Live BPM | implemented | software-tested partially | current local Rekordbox only | Direct offset-table path plus discovery fallback. |
| MTC fallback | implemented | software-tested unknown | local setup | Fallback path, not primary compatibility proof. |
| Smart phrasing/drop/breakdown | implemented | software-tested partially | local setup | Must remain StateManager-owned at runtime. |
| Laser Director policy | implemented | software-tested partially | local setup | Policy only, execution is separate. |
| Laser MIDI executor | implemented | software-tested partially | hardware-unvalidated in repo evidence | Local rig may work, but broad safety/fixture support is not claimed. |
| Laser Pad web UI | implemented | software/frontend tested partially | local setup | Operator tool, not broad support claim. |
| LED Look Director | implemented | software-tested partially | local setup | Active bank behavior must be checked against code before changing docs. |
| LED color engine M2 work | implemented/partial | software-tested partially | local setup | Current code includes color engine paths, fixed six-slot slot-color output, configurable slot-fill strategies including Patch S `random_with_mono_chance`, software-tested generic groove/post_drop/drop chase, drop center-burst, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, and Patch E3 ambient twinkle slot cue; Patch F bank cleanup remains gated active work. Patch D/E/S remain SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| Govee cloud scene adapter | implemented | software-tested partially | local setup | Single API-key path, device compatibility not generalized. |
| Govee realtime runner/transport | implemented/experimental | software-tested partially | local setup | H612D evidence exists in config examples, broad Govee support unknown. |
| SoundSwitch catalog/import/UI | uncertain/active-work | unknown | unknown | Must be verified against current main before claiming current support. |
| Multi-Rekordbox-version support | unknown | unvalidated | unknown | Needs explicit compatibility expansion tasks. |
| Windows/Linux support | unsupported/unknown | unvalidated | unsupported currently | Current reader architecture is macOS-bound. |
