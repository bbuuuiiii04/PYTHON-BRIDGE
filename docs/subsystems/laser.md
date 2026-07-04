---
doc_status: current
truth_level: code-verified
last_verified_commit: 26d357f
last_verified_date: 2026-07-04
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

Audit P1 (2026-07-03): `MidiOutput.panic()` documentation now matches the queue-drain/all-notes-off
mechanism, and `LaserConfigResult` no longer documents the obsolete `dependency_missing` loader
reason. Laser runtime behavior is unchanged in this patch.

Audit P2 (2026-07-03): pack-status overlay diagnostics are SoundSwitch/pack-driver reporting only;
Laser Director policy and laser MIDI execution are unchanged.

Audit P4 (2026-07-03): laser MIDI send-error degradation can recover by reopening the output port
after a 5-second cooldown; startup/dependency degradations stay fail-closed. Executor bank
selection skips disallowed high-impact or missing bank entries when a usable replacement exists,
and blocked/missing selections restore the previous cursor/active-scene state before reporting the
failure. Scene config now rejects unknown `fallback_scene` references and negative
`cooldown_beats`. `pre_drop_scene` is removed from the live personality model and tracked example,
but leftover keys in ignored local configs are tolerated as deprecated. Laser Pad's master enable
toggle now also appends the live `set_laser_director` runtime command while saving the draft.
All of this is software-tested only; no laser hardware, MIDI device, SoundSwitch, Rekordbox, LED,
Govee, DMX, or Enttec validation was performed.

Offline SoundSwitch pack boundary:
- Task 2 deterministically exports and independently verifies the repo-local canonical pack for the pinned SoundSwitch 2.10.3 canonical RAVE project, including the seven-class F-3 control crosswalk. Live export reconciles saved-project inventory dynamically; the old exact-count snapshot is proof-only. It does not replace or alter Laser Director policy, MIDI execution, mappings, blackout behavior, or status.
- The pack loader/player, MIDI-input adapter, backend abstraction, and Enttec sender exist. `LaserSceneExecutor` has one injected backend slot; startup selects legacy MIDI, none/dry-run, or verified pack/Enttec from the optional default-off config. Physical MIDI and direct DMX remain mutually exclusive.
- Pack backend startup, `StateManager` scripted frame driving, commands, copied RW-5 status, and native pack Autoloop scene-edge handoff are implemented in software. Laser policy, MIDI execution, blackout, and configured mappings stay unchanged; the executor now exposes the already-selected Autoloop scene so the pack driver can resolve canonical Autoloop bindings even on no-new-edge ticks when SoundSwitch is absent. Hardware remains unvalidated.
- Blackout-mask migration Package 1 is implemented/software-tested: smart-side blackout owners and pending drop-window latches survive pack-backend note rejection, and `StateManager` ORs that smart-side state with the existing manual MIDI-input blackout at the single pack-player mask writer. Manual blackouts remain owned by the MIDI-input binding refcount and survive smart-side lifecycle wipes. MIDI-mode accepting-backend note on/off sequences are unchanged. No laser hardware, SoundSwitch, Rekordbox, LED, Govee, MIDI device, DMX, or Enttec validation was performed.
- Laser color plumbing Package 4 is implemented/software-tested: StateManager samples LED color state into a pure `LaserColorSnapshot` and the pack player can overwrite CH8/CH9 only on healthy native Autoloop frames. The shipped `config/laser_color_map.json` is `enabled: false` with an all-null table, so live output remains authored pass-through and should be byte-identical to pre-package behavior until the operator CH8/CH9 chart lands. Scripted, diagnostic, masked, static-override, and CH11 behavior stay unchanged. Hardware remains unvalidated.
- Smart Drop exact cue landings are handled in the shared `SmartPhrasingEngine`: the first live tick after a reset fires an exact drop beat once, without rounding near-misses forward.

Authoritative code:
- `laser_config.py`
- `drop_lifecycle.py`
- `laser_models.py`
- `laser_director.py`
- `laser_executor.py`
- `laser_decision_log.py`
- `laser_color_engine.py`
- `midi_output.py`
- `personality_resolver.py`

Key symbols:
- `LaserConfig`
- `DropLifecycle`
- `LaserScene`
- `LaserDirector`
- `LaserSceneExecutor`
- `LaserColorEngine`
- `MidiOutput`
- `PersonalityResolver`

Runtime flow:
- inputs: `LaserContext`, smart phrasing state, runtime laser commands, config scenes/personalities
- decisions: role selection, gated drop/post-drop lifecycle, manual override, blackout, cooldown, bank/personality rotation
- outputs: MIDI note/CC/pulse/hold events through `MidiOutput`
- `drop_lifecycle_mirror` defaults on. Allowed phrase-context impacts hold for the configured flat `drop_impact_beats`, then `post_drop`/fallback drop cycles fire only on autoloop ticks. Drop and post-drop cycle banks use usable-only shuffle bags that reset per track; a static configured drop scene remains valid for the at-anchor impact so an empty cyclable bank does not make the hit dark.
- Setting `drop_lifecycle_mirror` to false preserves the previous ungated crossing and fixed post-drop-hold path (flag-OFF is byte-identical to pre-change EXCEPT the resume transition, which now also resets the executor: a benign phrase-bank reshuffle + active-scene clear; no dark, no drop leak). Director and executor lifecycle state reset on master/track/stop/resume transitions; director state also resets on scripted/idle transitions and personality application rebuilds it.
- Blackout-mask migration: the transition blackout — the held `manual_blackout_on/off` note refcounted by `breakdown`/`master_switch` owners in `LaserSceneExecutor`, plus the Smart-Drop drop-window pending — now also drives the pack player's frame-level blackout through `StateManager._drive_pack_output`. Backend note rejection no longer discards smart owners; accepted MIDI backends still receive the same note on/off sequence. The manual laser-pad/web blackout stays in the separate MIDI-input binding refcount and must not be routed through executor `_mask_owners`, because executor lifecycle wipes intentionally clear only smart-side covers.
- Laser color Package 4: the mapper is pure in-memory math and publishes an immutable same-tick snapshot. `LaserPackPlayer` merges that snapshot by copying the rendered Autoloop frame and writing only CH8/CH9; absence of a same-tick snapshot, disabled config, null table entries, scripted tracks, diagnostics, blackout, and static override all fall back to authored pack output.

Config:
- `config/laser_director.example.json`
- `config/laser_color_map.json` ships disabled/all-null; later CH8/CH9 chart updates are config-only and require operator validation before enabling.
- local ignored `config/laser_director.json`
- launcher environment for `RBSS_LASER_CONFIG`
- personality knobs: `drop_lifecycle_mirror` (default `true`), `max_drops_in_a_row`, `drop_impact_beats`, and operator-reserved future `post_drop_cycle_beats`; laser cycle cadence still comes from autoloop ticks. Deprecated leftover `pre_drop_scene` keys are ignored for load compatibility.

Laser Pad (operator companion tool):
- `tools/laser_pad_web.py` (local web service), `tools/laser_config_ops.py` (config read/write
  helpers), `tools/laser_pad_assets/` (UI assets), `scripts/laser_pad.py` (launcher), LaunchAgent
  `launchagents/com.bbui.laser-pad.plist` (always-on background launch), operator guide
  `docs/guides/laser_pad.md`. Tracked under the `laser_pad` change contract in
  `docs/agents/change_contracts.yml`.
- The pad edits laser config and personality selection through a local browser UI. Most changes
  write config that the bridge picks up separately (hot-reload or restart), the same way any other
  config edit does. The master `enabled` toggle is the exception: it also appends a
  `set_laser_director` runtime command to the bridge command file so the live director follows the
  draft toggle immediately; append failure returns an error instead of success.
- Status: implemented / software-tested / hardware-unvalidated.

Tests:
- `python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q` if pytest is available
- otherwise inspect `tests/` and run relevant unittest equivalents
- lifecycle coverage: `tests/test_drop_lifecycle.py`, `tests/test_laser_director_lifecycle.py`, and `tests/test_laser_executor_lifecycle.py`
- blackout re-wire coverage: `tests/test_laser_blackout_rewire.py`
- laser color plumbing coverage: `tests/test_laser_color_engine.py`
- transitional mapping check: `python3 tools/check_laser_midi_sync.py`
- Audit P4 coverage: `tests/test_midi_output.py`, `tests/test_laser_executor.py`,
  `tests/test_laser_config.py`, `tests/test_laser_config_deprecation.py`,
  `tests/test_laser_pad_web.py`, and lifecycle/status regression suites cover send-error recovery,
  bank-gate cursor restore, config validation/deprecation, blackout-mask refcounting, and Laser Pad
  live-toggle command append behavior.

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
