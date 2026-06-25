---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: e48092d
last_verified_date: 2026-06-25
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
- Frozen source models, strict decoding, deterministic canonical replacement, independent verification, immutable pack loading/rendering, MIDI-input routing, backend abstraction, Enttec sending, config/startup, `StateManager` scripted frame driving, validate-first commands, and copied sanitized operational status are implemented for the pinned project boundary.
- The menubar `Export from SS` action and conservative post-export reload are implemented and software-tested. The SoundSwitch-connection auto-switch sends `set_soundswitch_pack action=enable` and retries one fresh disconnected `pack_start_failed`, but there is no manual pack button and no implicit hot-enable without a real pack backend + Enttec port. The combined pack row reads only the copied status file; stale data renders `Lighting: no status yet`.
- Static Override Press/Toggle behavior follows the SoundSwitch-saved interaction mode (decoded byte), not operator config; a saved mode the decoder cannot identify fails closed to momentary. Static-controller input auto-binds from pack bindings unless `midi_input_aliases` overrides it; missing or ambiguous controller input degrades manual Static Looks while pack DMX can continue. The canonical pack is published to and loaded from the repo-local ignored path `local/soundswitch/rbss_canonical_pack`.
- RW-5 does not report sender health. `software_zero_frame=true` means only that software rendered zero, and `frame_count` counts attempted normal software frames. Neither proves serial delivery, Enttec acceptance, or fixture darkness.
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
- The hardware procedure/template exist, but no completed operator evidence file exists. Emergency
  restore requires default-off config plus an operator-confirmed known-dark Enttec/DMX baseline
  before physical output is restored.
- Old docs and prompts may describe plans that are already stale.

## Documentation limitations

- Existing docs before this refactor may overuse “current authoritative.”
- Historical docs are useful evidence, not truth.
- Any doc without a status header or inventory entry should be treated cautiously.
