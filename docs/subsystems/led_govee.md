---
doc_status: current
truth_level: code-verified
last_verified_commit: 51367a1
last_verified_date: 2026-06-18
validation_scope: software-only
---

# LED / Govee Subsystem

Status:
- implementation: alpha/experimental by path
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: current local setup only

Purpose:
- Select LED room looks, resolve colors, coordinate cloud/realtime ownership, and send Govee-style cloud or realtime output.

Authoritative code:
- `led_config.py`
- `led_models.py`
- `led_look_director.py`
- `led_color_engine.py`
- `led_dispatch_coordinator.py`
- `govee_scene_adapter.py`
- `govee_runtime_sender.py`
- `govee_realtime_runner.py`
- `govee_realtime_transport.py`
- `govee_frame_renderer.py`
- `govee_owner_state.py`
- `beat_sync_engine.py`

Key symbols:
- `LEDConfig`
- `LEDLookDirector`
- `LedColorEngine`
- `LEDDispatchCoordinator`
- `GoveeSceneAdapter`
- `GoveeRuntimeSender`
- `GoveeRealtimeRunner`
- `GoveeRealtimeTransport`
- `BeatSyncEngine`

Runtime flow:
- inputs: phrase/role state, runtime LED commands, LED config, color engine state, beat/BPM state
- decisions: manual override, blackout, role-entry look selection, color/slot-color resolution, cloud/realtime ownership, beat sync instances
- outputs: cloud scene commands or realtime UDP frame packets

Config:
- `config/led_look_director.example.json`
- local ignored `config/led_look_director.json`
- env secrets such as `GOVEE_API_KEY`
- realtime enable flag if present in startup
- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` are optional objects; values must be `gradient_even`, `random_with_replacement`, or `random_with_mono_chance`.
- `color_engine.slot_mono_chance_by_look` is an optional object mapping look names to numeric probabilities in `[0, 1]`; it defaults to `{}` and only affects looks using `random_with_mono_chance`.
- `LedColorEngine.resolve_slot_colors()` returns exactly six slot colors for slot effects; caller `slot_count` is ignored and slot index 5 is reserved as pure white.
- Solid palette slots remain possible for every slot cue: a point/mono palette can collapse slots 0-4 to one RGB while slot 5 remains pure white, and `random_with_mono_chance` can opt individual looks into probabilistic solid slots 0-4 without changing the white slot.
- Patch F collapses the tracked example `default` bank onto generic engine-colored slot looks and moves legacy color-suffix realtime looks into the storage-only `legacy_color_suffix` bank. `LEDLookDirector` still selects only `banks.default`, so the legacy bank preserves definitions without runtime rotation.

Tests:
- inspect `tests/` for LED color engine, Govee realtime runner, frame renderer, state manager LED integration, and config tests
- slot-color coverage lives in `tests/test_led_color_engine.py`, `tests/test_led_color_engine_m2_phase1.py`, `tests/test_led_color_engine_m2_patch_b.py`, `tests/test_led_color_engine_m2_patch_c.py`, `tests/test_led_color_engine_m2_patch_d.py`, `tests/test_led_color_engine_m2_patch_e1.py`, `tests/test_led_color_engine_m2_patch_e2.py`, `tests/test_led_color_engine_m2_patch_e3.py`, `tests/test_led_color_engine_m2_patch_s.py`, `tests/test_led_color_engine_m2_patch_f.py`, and config validation coverage in `tests/test_color_engine_config.py`
- broad command: `python -m unittest discover tests`

Change contract:
- If changing look policy, inspect director, models, config validation, and state manager dispatch seam.
- If changing realtime output, inspect runner, transport, renderer, owner state, and beat sync engine.
- If changing cloud output, inspect scene adapter and runtime sender.
- Update this card, feature matrix, validation matrix, active work registry, and config docs.

M2.5 slot cues in SLOT_EFFECTS (govee_frame_renderer.py):

| Scene ref | Fn | Safety class | Strobe | Status |
|---|---|---|---|---|
| groove_center_chase | _slot_groove_center_chase | groove | no | software-validated |
| groove_center_burst_retract | _slot_groove_center_burst_retract | groove | no | software-validated |
| post_drop_firework_chase | _slot_post_drop_firework_chase | post_drop | yes (slot 5) | software-validated |
| breakdown_full_breathing | _slot_breakdown_full_breathing | breakdown | no | software-validated |
| breakdown_star_twinkle | _slot_breakdown_star_twinkle | breakdown | no | software-validated |
| rt_groove_chase | _slot_groove_chase | groove | no | software-validated |
| rt_groove_nebula | _slot_groove_nebula | groove | no | software-validated (Patch E1) |
| rt_post_drop_chase | _slot_post_drop_chase | post_drop | yes | software-validated |
| rt_post_drop_nebula | _slot_post_drop_nebula | post_drop | yes | software-validated (Patch E1) |
| rt_drop_chase | _slot_drop_chase | drop | yes | software-validated |
| rt_drop_nebula | _slot_drop_nebula | drop | yes | software-validated (Patch E1) |
| rt_drop_center_burst | _slot_drop_center_burst | drop | no | software-validated |
| rt_post_drop_center_comet | _slot_post_drop_center_comet | post_drop | yes | software-validated (Patch E2) |
| rt_twinkle | _slot_twinkle | ambient | no | software-validated (Patch E3) |

Patch E pairings:
- rt_drop_nebula pairs explicitly to rt_post_drop_nebula through `drop_pairs`.
- rt_drop_center_burst pairs explicitly to rt_post_drop_center_comet through `drop_pairs`.

All slot cues, `random_with_mono_chance`, and Patch F bank cleanup: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
The stable-hue sparkle (rt_drop_chase), center-burst 0-2/2-4 accent band split (rt_drop_center_burst), Patch E1 looks (rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula), Patch E2 center-comet (rt_post_drop_center_comet), Patch E3 ambient twinkle (rt_twinkle), Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation still need operator hardware visual sign-off.

Known risks:
- API/cloud rate limits
- realtime protocol/device specificity
- confusing local H612D behavior with all Govee devices
- beat-synced motion smoothness issues
- config schema drift
