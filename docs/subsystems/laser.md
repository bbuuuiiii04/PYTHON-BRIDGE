---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-21
validation_scope: software-only
---

# Laser Subsystem

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: configured local rig only

Purpose:
- Choose laser roles/scenes and execute configured MIDI triggers with blackout, cooldown, and override behavior.

Offline SoundSwitch pack boundary:
- Task 2 deterministically exports and independently verifies a canonical 95-artifact pack for the pinned SoundSwitch 2.10.3 canonical RAVE project, including the seven-class F-3 control crosswalk. It does not replace or alter Laser Director policy, MIDI execution, mappings, blackout behavior, or status.
- Task 3 loader/player and Task 4+ MIDI/runtime/backend/Enttec work remain planned and unimplemented; no laser or Enttec hardware was validated.

Authoritative code:
- `laser_config.py`
- `laser_models.py`
- `laser_director.py`
- `laser_executor.py`
- `laser_decision_log.py`
- `midi_output.py`
- `personality_resolver.py`

Key symbols:
- `LaserConfig`
- `LaserScene`
- `LaserDirector`
- `LaserSceneExecutor`
- `MidiOutput`
- `PersonalityResolver`

Runtime flow:
- inputs: `LaserContext`, smart phrasing state, runtime laser commands, config scenes/personalities
- decisions: role selection, manual override, blackout, cooldown, bank/personality rotation
- outputs: MIDI note/CC/pulse/hold events through `MidiOutput`

Config:
- `config/laser_director.example.json`
- local ignored `config/laser_director.json`
- launcher environment for `RBSS_LASER_CONFIG`

Tests:
- `python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q` if pytest is available
- otherwise inspect `tests/` and run relevant unittest equivalents

Change contract:
- If modifying policy, inspect `laser_director.py`, `laser_models.py`, and smart phrasing state usage.
- If modifying execution, inspect `laser_executor.py`, `midi_output.py`, and blackout behavior.
- Update this card, feature status, validation matrix, and hardware validation log if manual testing occurs.

Known risks:
- laser safety assumptions
- MIDI mapping drift
- blackout override mistakes
- treating one fixture/mapping as generic laser support
