---
doc_status: current
truth_level: code-verified
last_verified_commit: cb31cf8
last_verified_date: 2026-06-25
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
- Task 2 deterministically exports and independently verifies the repo-local canonical pack for the pinned SoundSwitch 2.10.3 canonical RAVE project, including the seven-class F-3 control crosswalk. Live export reconciles saved-project inventory dynamically; the old exact-count snapshot is proof-only. It does not replace or alter Laser Director policy, MIDI execution, mappings, blackout behavior, or status.
- The pack loader/player, MIDI-input adapter, backend abstraction, and Enttec sender exist. `LaserSceneExecutor` has one injected backend slot; startup selects legacy MIDI, none/dry-run, or verified pack/Enttec from the optional default-off config. Physical MIDI and direct DMX remain mutually exclusive.
- Pack backend startup, `StateManager` scripted frame driving, commands, and copied RW-5 status are implemented in software. RW-5 changes status publication only: laser policy, MIDI execution, blackout, mappings, and selection are unchanged. Native pack Autoloops remain software-zero pending T7d evidence; hardware remains unvalidated.

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
- Blackout-mask migration (forward-looking): the transition blackout — the held `manual_blackout_on/off` note refcounted by `breakdown`/`master_switch` owners in `LaserSceneExecutor`, plus the Smart-Drop drop-window pending and the StateManager SM-net clear (`smart_drop_crossing_without_drop_decision`) — is MIDI *actuation*. When the bridge-native direct-DMX/`PackOutputBackend` lane becomes the live laser output, the held note retires (DMX blacks out by rendering a zero CH1-CH19 frame; `manual_blackout_*` carry no `scene_name`, so the pack backend already no-ops them), but the masking *decision* (which transitions go dark, refcounted overlapping owners, teardown timing) must be ported to the frame-level blackout — not deleted. The known **C2** edge (a gated-off Smart-Drop crossing releasing a held breakdown/master_switch cover via `clear_pending_blackout`) is a MIDI-path-only artifact; settle the owner/teardown semantics when that DMX blackout is designed, not by patching the outgoing MIDI path. See `docs/plans/active/laser_smartnet_mask_preserve_spec.md`.

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
