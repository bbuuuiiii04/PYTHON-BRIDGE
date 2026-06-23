---
doc_status: current
truth_level: code-verified
last_verified_commit: 9918dd4
last_verified_date: 2026-06-22
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
- The pack loader/player, MIDI-input adapter, backend abstraction, and Enttec sender exist. `LaserSceneExecutor` now has one injected backend slot; current startup still constructs the existing MIDI backend, so output remains MIDI-equivalent.
- T7a adds only an inert config loader/example. Pack backend selection, direct-DMX startup, `StateManager` frame driving, status, and commands remain unimplemented; no laser or Enttec hardware was validated.

Authoritative code:
- `laser_config.py`
- `drop_lifecycle.py`
- `laser_models.py`
- `laser_director.py`
- `laser_executor.py`
- `laser_decision_log.py`
- `midi_output.py`
- `personality_resolver.py`

Key symbols:
- `LaserConfig`
- `DropLifecycle`
- `LaserScene`
- `LaserDirector`
- `LaserSceneExecutor`
- `MidiOutput`
- `PersonalityResolver`

Runtime flow:
- inputs: `LaserContext`, smart phrasing state, runtime laser commands, config scenes/personalities
- decisions: role selection, gated drop/post-drop lifecycle, manual override, blackout, cooldown, bank/personality rotation
- outputs: MIDI note/CC/pulse/hold events through `MidiOutput`
- `drop_lifecycle_mirror` defaults on. Allowed phrase-context impacts hold for the configured flat `drop_impact_beats`, then `post_drop`/fallback drop cycles fire only on autoloop ticks. Drop and post-drop cycle banks use usable-only shuffle bags that reset per track; a static configured drop scene remains valid for the at-anchor impact so an empty cyclable bank does not make the hit dark.
- Setting `drop_lifecycle_mirror` to false preserves the previous ungated crossing and fixed post-drop-hold path (flag-OFF is byte-identical to pre-change EXCEPT the resume transition, which now also resets the executor: a benign phrase-bank reshuffle + active-scene clear; no dark, no drop leak). Director and executor lifecycle state reset on master/track/stop/resume transitions; director state also resets on scripted/idle transitions and personality application rebuilds it.

Config:
- `config/laser_director.example.json`
- local ignored `config/laser_director.json`
- launcher environment for `RBSS_LASER_CONFIG`
- personality knobs: `drop_lifecycle_mirror` (default `true`), `max_drops_in_a_row`, `drop_impact_beats`, and renderer-intent-only `post_drop_cycle_beats`; laser cycle cadence still comes from autoloop ticks

Tests:
- `python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q` if pytest is available
- otherwise inspect `tests/` and run relevant unittest equivalents
- lifecycle coverage: `tests/test_drop_lifecycle.py`, `tests/test_laser_director_lifecycle.py`, and `tests/test_laser_executor_lifecycle.py`
- transitional mapping check: `python3 tools/check_laser_midi_sync.py`

Change contract:
- If modifying policy, inspect `laser_director.py`, `laser_models.py`, and smart phrasing state usage.
- If modifying execution, inspect `laser_executor.py`, `midi_output.py`, and blackout behavior.
- If modifying the shared drop resolver, preserve flat-window parity with the existing StateManager LED resolver without redirecting live LED behavior through it.
- Update this card, feature status, validation matrix, and hardware validation log if manual testing occurs.

Known risks:
- laser safety assumptions
- MIDI mapping drift
- blackout override mistakes
- drop/post-drop gate or teardown drift between director and executor
- treating one fixture/mapping as generic laser support
