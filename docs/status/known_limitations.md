---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
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
- Frozen source models, strict decoding, deterministic new-path export, independent verification, immutable pack loading/rendering, MIDI-input routing, backend abstraction, Enttec sending, config/startup, `StateManager` scripted frame driving, validate-first commands, and basic sanitized status are implemented for the pinned project boundary.
- The menubar `Export from SS` action, safe replacement of one canonical pack, automatic post-export reload, and operator result feedback are not implemented.
- Scripted runtime remains partial: the pure player supports paused rendering, but the StateManager driver collapses pause and stop through `playing=false`; it does not explicitly require scripted mode/id; and it ignores MIDI-input health/error/drop snapshot fields. These are software implementation gaps, not hardware-only caveats.
- Native-DMX Autoloops remain evidence-blocked and zero-safe. T7d has four conductor-accepted integrity captures (two arm, two refire), but four scenario pairs, identity/holdout reconciliation, and a unique corpus oracle verdict remain; no phase mapping can be implemented honestly yet.
- The ignored local pack config was absent in the 2026-06-23 audit; no live pack/Enttec setup is claimed.
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
