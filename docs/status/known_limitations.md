---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: b7e0e66
last_verified_date: 2026-06-21
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Known Limitations

Current SoundSwitch exporter/importer work remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

## Compatibility limitations

- Rekordbox version support is not broadly validated.
- OS support is macOS-local only in current evidence.
- Windows and Linux are not current supported targets.
- SoundSwitch version/interface compatibility is not broadly documented.
- The offline SoundSwitch decoder is deliberately limited to SoundSwitch 2.10.3, the canonical project UUID, and the RAVE Venue profile. It is read-only; other projects/versions/profiles are unsupported unless explicitly added and tested.
- Frozen source models, strict decoding, deterministic export, independent verification, immutable pack loading/rendering, MIDI-input routing, backend abstraction, Enttec sending, and the T7a config loader are implemented for the pinned project boundary. Pack startup, commands/status, `StateManager` frame driving, direct-DMX enablement, and hardware work remain unimplemented.
- The pack proof is 29 PASS / 0 FAIL / 0 INCOMPLETE with foundation 27/27 PASS; F9 mutation rejection and F10 active CC/pitch rejection both pass.
- Laser support depends on local MIDI mapping and fixture behavior.
- Govee support is not generalized across devices.

## Runtime limitations

- Direct Rekordbox readers depend on app memory layout, permissions, offsets, and platform behavior.
- Local config and secrets are intentionally not committed.
- Hardware behavior can drift from software tests.
- Enttec owner-driven stop sends a zero packet, but process death/`kill -9` can leave the last DMX frame latched. A physical kill path and explicit hardware gate remain mandatory before use.
- Old docs and prompts may describe plans that are already stale.

## Documentation limitations

- Existing docs before this refactor may overuse “current authoritative.”
- Historical docs are useful evidence, not truth.
- Any doc without a status header or inventory entry should be treated cautiously.
