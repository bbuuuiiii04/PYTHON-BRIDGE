---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
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
