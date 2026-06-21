---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: c678788
last_verified_date: 2026-06-21
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Known Limitations

Current SoundSwitch exporter/importer work remains **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

## Compatibility limitations

- Rekordbox version support is not broadly validated.
- OS support is macOS-local only in current evidence.
- Windows and Linux are not current supported targets.
- SoundSwitch version/interface compatibility is not broadly documented.
- The offline SoundSwitch decoder is deliberately limited to SoundSwitch 2.10.3, the canonical project UUID, and the RAVE Venue profile. It is read-only; other projects/versions/profiles are unsupported unless explicitly added and tested.
- Only frozen source models and strict decoding are implemented. Production exporter/pack builder/verifier/player, project mutation, bridge config/commands/status, `StateManager` integration, backend selection, and Enttec output remain planned and unimplemented.
- Laser support depends on local MIDI mapping and fixture behavior.
- Govee support is not generalized across devices.

## Runtime limitations

- Direct Rekordbox readers depend on app memory layout, permissions, offsets, and platform behavior.
- Local config and secrets are intentionally not committed.
- Hardware behavior can drift from software tests.
- Enttec process death is not a proven hard kill and may leave the last DMX frame latched. A future Enttec backend must implement and hardware-validate an explicit hard-kill/blackout path before use.
- Old docs and prompts may describe plans that are already stale.

## Documentation limitations

- Existing docs before this refactor may overuse “current authoritative.”
- Historical docs are useful evidence, not truth.
- Any doc without a status header or inventory entry should be treated cautiously.
