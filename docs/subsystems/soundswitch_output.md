---
doc_status: current
truth_level: code-verified
last_verified_commit: b7e0e66
last_verified_date: 2026-06-21
validation_scope: software-only
---

# SoundSwitch Output

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: my local SoundSwitch setup only

Purpose:
- Send VirtualDJ-shaped OS2L messages and helper fanout to SoundSwitch.

Offline project export:
- `soundswitch_pack_models.py`, `soundswitch_project_decoder.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`, and `tools/export_soundswitch_pack.py` implement frozen source models, strict read-only decode, deterministic export of a canonical 95-artifact pack, and independent verification for the pinned SoundSwitch 2.10.3 canonical project UUID/RAVE profile. Software tests cover the 232 render + 1 catalog-tail cues, 32 Static Looks, 42 autoloops, 45 scripted inventory records, seven-class F-3 crosswalk, and F9 mutation rejection.
- The immutable pack loader/player, MIDI-input adapter, output-backend abstraction, and Enttec frame sender are implemented and software-tested components. T7a adds a validated, default-off pack-player config loader and tracked inert example.
- The T7a config is not loaded by `__main__`; the pack player, controller input, and Enttec sender are not wired into `StateManager`, status, or runtime commands. Existing OS2L and MIDI-laser output remain the live paths.
- Live SoundSwitch OS2L behavior and all other bridge outputs remain unchanged; no hardware validation was performed.

Authoritative code:
- `osl_output.py`
- `sound_switch_engine.py`
- `os2l_injector.py`

Key symbols:
- `OS2LConnection`
- `OS2LOutput`
- `SoundSwitchEngine`

Runtime flow:
- inputs: `StateManager` send intents, active/mirror deck routing, BPM/beat/elapsed
- decisions: fanout routing and send order
- outputs: TCP OS2L messages to SoundSwitch

Config:
- OS2L host/port values in `config.py`
- local SoundSwitch setup outside repo

Tests:
- inspect `tests/` for OS2L, SoundSwitch engine, and injector tests
- broad command: `python -m unittest discover tests`

Change contract:
- If changing OS2L payloads or routing, inspect `state_manager.py` and `sound_switch_engine.py` together.
- Update `docs/status/feature_status_matrix.md` and this card.

Known risks:
- breaking deck fanout
- changing send order without tests
- assuming another SoundSwitch version behaves the same
