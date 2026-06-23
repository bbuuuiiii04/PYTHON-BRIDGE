---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 9918dd4
last_verified_date: 2026-06-22
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
| Runtime `[BEAT]` heartbeat | implemented | software-tested partially | local setup | `StatusWriter` emits a throttled status-only heartbeat and writes the same summary into status JSON. Hardware-visible output is unchanged and unvalidated. |
| Logging visibility live watch | implemented | software-tested partially | local setup | `docs/setup/logging_live_watch.json` provides a curated control-file preset for `[BEAT]`, laser, LED/Govee, SoundSwitch, and master/deck logs using existing `LoggingManager` filters. It changes logging visibility only and remains hardware-unvalidated. |
| SoundSwitch OS2L output | implemented | software-tested partially | local setup | Uses OS2L TCP and VirtualDJ-shaped messages. |
| SoundSwitch offline decoder/exporter/pack/verifier | implemented | software-tested | pinned SoundSwitch 2.10.3 canonical UUID/RAVE profile only | Strict read-only decode, deterministic canonical 95-artifact export, and independent verification. Exact inventory is 232 render + 1 catalog-tail cues, 32 Static Looks, 42 autoloops, and 45 scripted records; seven-class F-3 crosswalk and F9 mutation rejection pass. No project mutation or live bridge integration. |
| SoundSwitch loader/player/MIDI/runtime/backend/Enttec | partial | software-tested components; runtime unvalidated | pinned pack/local setup only | Loader/player, MIDI adapter, backend abstraction, Enttec sender, and the T7a validated default-off config loader exist. Config is not wired into startup, `StateManager`, status, or commands; no hardware validation is claimed. |
| Rekordbox memory position reader | implemented | software-tested partially | macOS local setup | macOS Mach APIs. Other OSes unsupported/unknown. |
| Rekordbox direct state reader | implemented | software-tested partially | current local Rekordbox only | Offset/version assumptions require validation per version. |
| Live BPM | implemented | software-tested partially | current local Rekordbox only | Direct offset-table path plus discovery fallback. |
| MTC fallback | implemented | software-tested unknown | local setup | Fallback path, not primary compatibility proof. |
| Smart phrasing/drop/breakdown | implemented | software-tested partially | local setup | Must remain StateManager-owned at runtime. |
| Laser Director policy | implemented | software-tested partially | local setup | The default-on gated drop/post-drop lifecycle is software-tested and mirrors the LED flat-window role gate, with configurable impact/cap values and a default-true runtime kill switch. Execution remains separate. |
| Laser MIDI executor | implemented | software-tested partially | hardware-unvalidated in repo evidence | Drop/post-drop cycles use usable-only shuffle bags on autoloop ticks; static initial-impact fallback and deterministic Laser Pad Verify are covered. Local rig may work, but broad safety/fixture support is not claimed. |
| Laser Pad web UI | implemented | software/frontend tested partially | local setup | Operator tool, not broad support claim. |
| LED Look Director | implemented | software-tested partially | local setup | Active bank behavior must be checked against code before changing docs. The live LED lifecycle is unchanged; a pure flat-window parity resolver is used by laser policy only. |
| LED scripted-track automation policy | implemented | software-tested partially | hardware-unvalidated | When enabled during `lighting_mode == "scripted"`, groove/drop/post-drop select the existing `utility` blackout bank while buildup/pre-drop and breakdown remain active. The shipped example config now enables the master switch (`true`) with the conservative blackout policy, so out-of-box scripted LED automation is active; room-visible behavior still needs hardware validation. |
| LED color engine M2 work | implemented/partial | software-tested partially | local setup | Current code includes color engine paths, fixed six-slot slot-color output, configurable slot-fill strategies including Patch S `random_with_mono_chance`, software-tested generic groove/post_drop/drop chase, drop center-burst, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, and Patch F default-bank cleanup into generic slot looks plus `legacy_color_suffix` storage. Patch D/E/S/F remain SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| Govee cloud scene adapter | implemented | software-tested partially | local setup | Single API-key path, device compatibility not generalized. |
| Govee realtime runner/transport | implemented/experimental | software-tested partially | local setup | H612D evidence exists in config examples, broad Govee support unknown. |
| SoundSwitch catalog/import/UI | partial/planned | offline export and pack player software-tested; UI unvalidated | pinned offline pack only | Decode/export/verification and the immutable pack loader/player exist. Project mutation/import UI remains planned; T7a does not wire the player into live runtime. |
| Multi-Rekordbox-version support | unknown | unvalidated | unknown | Needs explicit compatibility expansion tasks. |
| Windows/Linux support | unsupported/unknown | unvalidated | unsupported currently | Current reader architecture is macOS-bound. |
