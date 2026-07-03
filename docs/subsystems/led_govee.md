---
doc_status: current
truth_level: code-verified
last_verified_commit: fc56bb5
last_verified_date: 2026-07-03
validation_scope: software-only; LED Pad Phases 1-3, Template Lab Phase 2, QR same-network access, and the pad editor unset-param-defaults fix software-tested, hardware-unvalidated
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
- `govee_lan_discovery.py`
- `beat_sync_engine.py`
- `state_manager.py` LED automation dispatch seam
- `led_pad_controls.py` LED Pad render/control catalog. `CONTROL_META[key]["default"]` mirrors
  each renderer's actual unset-param fallback in `govee_frame_renderer.py` (hand-extracted, `None`
  when no single static fallback exists); `PARAM_DEFAULT_OVERRIDES` covers the two keys
  (`travel_beats`, `width`) whose real default differs by scene_ref. See `docs/guides/led_pad.md`
  for the operator-facing summary and `tests/test_led_pad_controls.py` for the source-text pin.
- `tools/led_pad_playback.py` standalone LED Pad realtime playback shell
- `tools/led_pad_web.py` local LED Pad web service
- `tools/led_pad_lab.py` Template Lab draft registry and pad-only renderer overlay
- `tools/led_pad_assets/` vanilla LED Pad UI assets
- `scripts/led_pad.py` LED Pad launcher

Key symbols:
- `StateManager`
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
- The live LED drop/post-drop resolver remains in `StateManager` and is unchanged. `drop_lifecycle.py` reproduces its flat-window drop-region state machine for laser use; `tests/test_drop_lifecycle.py` parity-checks that seam without routing LED output through the new module.
- Active content changes now arm a phrase-aware LED hold in `StateManager`: a nonzero active-deck switch or active-deck track replacement keeps the previously shown look if the incoming track is more than `1.0` beat into its current phrase, then releases at the next phrase crossing. If the incoming track is already within the first beat of a phrase, it changes immediately. Missing phrase segments can keep the prior look for the whole track; this is software-tested only and still needs operator visual sign-off.

Config:
- `config/led_look_director.example.json`
- local ignored `config/led_look_director.json`
- env secrets such as `GOVEE_API_KEY`
- realtime enable flag if present in startup
- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` are optional objects; values must be `gradient_even`, `random_with_replacement`, or `random_with_mono_chance`.
- `color_engine.slot_mono_chance_by_look` is an optional object mapping look names to numeric probabilities in `[0, 1]`; it defaults to `{}` and only affects looks using `random_with_mono_chance`.
- `color_engine.locked_palette_by_look` is an optional object mapping look names to existing palette names. Locked looks resolve color and slot-color injection from that palette's full p-interval and white value without changing the color-engine journey palette, dwell, focus, or RNG state.
- `LedColorEngine.resolve_slot_colors()` returns exactly six slot colors for slot effects; caller `slot_count` is ignored and slot index 5 is reserved as pure white.
- Solid palette slots remain possible for every slot cue: a point/mono palette can collapse slots 0-4 to one RGB while slot 5 remains pure white, and `random_with_mono_chance` can opt individual looks into probabilistic solid slots 0-4 without changing the white slot.
- Patch F collapses the tracked example `default` bank onto generic engine-colored slot looks and moves legacy color-suffix realtime looks into the storage-only `legacy_color_suffix` bank. `LEDLookDirector` still selects only `banks.default`, so the legacy bank preserves definitions without runtime rotation.
- `safety.scripted_mode_automation` remains the master switch for scripted-track LED automation. The shipped example config sets it `true` (paired with the conservative blackout `scripted_mode` policy); set it to `false` to keep LEDs inert during scripted tracks. The code-level `LEDSafety` dataclass default stays `false`, but the loader requires the JSON key. When it is true and `StateManager` is in `lighting_mode == "scripted"`, automatic LED dispatch may proceed through the `scripted_mode` role-remap policy.
- The top-level LED `scripted_mode` block defines `default_role` plus `role_map` for scripted-track automation. If the block is absent, groove, drop, and post-drop map to the `utility` blackout bank; buildup/pre-drop map to `buildup`, and breakdown maps to `breakdown`. `utility` is allowed only as a destination, and partial maps fall back to `default_role`.
- LED Pad persists its edit draft in `config/led_look_director.draft.json` and commits only after the full draft passes `load_led_look_director_config_from_dict()`. In the UI this draft commit is labeled **Apply** (2026-07-03 visual reskin; the `/api/commit` route name is unchanged, and the reskin — design tokens plus a vendored Archivo font in `tools/led_pad_assets/` — changes no runtime behavior). The pad-only Drafts bank lives in root `_pad_meta.drafts`, so those looks are automation-invisible unless moved into `banks.default`.
- LED Pad Locked Palette writes through `color_engine.locked_palette_by_look`; playback of a locked look ignores the session Test Palette. Renderer param unlocks are frame-identical when omitted: `loop_beats` on `rt_groove_chase`/`rt_groove_nebula`; `travel_beats` + `width` on `rt_drop_chase`, `rt_post_drop_chase`, `rt_drop_nebula`, and `rt_post_drop_nebula`; `travel_beats` on `groove_center_chase` and `post_drop_firework_chase`.
- Template Lab persists draft metadata under gitignored `config/led_lab/drafts.json` and loads gitignored `config/led_lab/effects_lab.py` only inside the pad process. Lab scenes play as `lab_<name>` through `LabRenderer`; bridge runtime modules never import lab code, and production renderer registries are not mutated by lab playback.
- LED Pad exposes `GET /api/access` (shared with Laser Pad via `tools/pad_access.py`), which reports the pad's current bind address/loopback state and, when non-loopback, a best-effort LAN URL for a QR "Open on another device" affordance. It never changes bind behavior itself; exposing the pad to the LAN stays an explicit `--host` operator action.

Tests:
- inspect `tests/` for LED color engine, Govee realtime runner, frame renderer, state manager LED integration, and config tests
- slot-color coverage lives in `tests/test_led_color_engine.py`, `tests/test_led_color_engine_m2_phase1.py`, `tests/test_led_color_engine_m2_patch_b.py`, `tests/test_led_color_engine_m2_patch_c.py`, `tests/test_led_color_engine_m2_patch_d.py`, `tests/test_led_color_engine_m2_patch_e1.py`, `tests/test_led_color_engine_m2_patch_e2.py`, `tests/test_led_color_engine_m2_patch_e3.py`, `tests/test_led_color_engine_m2_patch_s.py`, `tests/test_led_color_engine_m2_patch_f.py`, and config validation coverage in `tests/test_color_engine_config.py`
- scripted-mode LED policy coverage lives in `tests/test_led_config.py` and `tests/test_led_state_manager.py`, including blackout mapping for groove/drop/post-drop; this is software validation only and does not prove room-visible Govee behavior during scripted SoundSwitch tracks.
- phrase-aware active-content hold coverage lives in `tests/test_led_state_manager.py`, including active deck switch, active-deck track load, the inclusive `1.0` beat release boundary, hold-until-next-marker behavior, missing-phrase-data indefinite hold until a crossing, idle/stop cleanup, inactive-deck load exclusion, and laser/SoundSwitch path confinement. This is software validation only.
- shared flat-window lifecycle parity coverage lives in `tests/test_drop_lifecycle.py`; live LED per-look duration rewriting and backend latency offsets remain separate by design.
- LED Pad Phase 1/3 coverage lives in `tests/test_led_pad_controls.py`, `tests/test_led_pad_playback.py`, and `tests/test_led_pad_service.py`. It validates metadata coverage, synthetic playback clock/ownership/strobe gates, draft mutation, commit blocking, color injection, Locked Palette playback, ownership-required replies, and one HTTP smoke path. Template Lab Phase 2 coverage lives in `tests/test_led_pad_lab.py` and validates registry persistence, name-collision rejection, hot reload, broken-module errors, lab rendering, and shared playback-slot preemption. It uses fakes or dry-run paths only. Phase 3 color-engine and renderer regressions live in `tests/test_led_color_engine.py`, `tests/test_color_engine_config.py`, and `tests/test_govee_frame_renderer.py`.
- The shared `tools/pad_access.py` LAN-access payload (used by both pads' `GET /api/access`) is covered by `tests/test_pad_access.py` (pure-function, loopback/specific-IP/`0.0.0.0` detection cases), plus one HTTP smoke test each in `tests/test_led_pad_service.py` and `tests/test_laser_pad_web.py`.
- broad command: `python -m unittest discover tests`

Change contract:
- If changing look policy, inspect director, models, config validation, and state manager dispatch seam.
- If changing active-content timing or LED role gating in `StateManager`, keep the hot path non-blocking and update `tests/test_led_state_manager.py`.
- If changing realtime output, inspect runner, transport, renderer, owner state, and beat sync engine.
- If changing cloud output, inspect scene adapter and runtime sender.
- If changing the shared drop resolver, prove parity against the existing StateManager LED resolver and do not assume that pure-resolver parity changes live LED output.
- If changing LED Pad, follow the `led_pad` contract in `docs/agents/change_contracts.yml` and update `docs/guides/led_pad.md`, this card, `docs/architecture/doc_index.md`, and `docs/status/active_work_registry.md`.
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
Phase 3 renderer params: `rt_groove_chase`/`rt_groove_nebula` accept `loop_beats`; `rt_drop_chase`/`rt_post_drop_chase`/`rt_drop_nebula`/`rt_post_drop_nebula` accept `travel_beats` and `width`; `groove_center_chase`/`post_drop_firework_chase` accept `travel_beats`. Missing params preserve previous frames.
The stable-hue sparkle (rt_drop_chase), center-burst 0-2/2-4 accent band split (rt_drop_center_burst), Patch E1 looks (rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula), Patch E2 center-comet (rt_post_drop_center_comet), Patch E3 ambient twinkle (rt_twinkle), Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation still need operator hardware visual sign-off.

Known risks:
- API/cloud rate limits
- realtime protocol/device specificity
- confusing local H612D behavior with all Govee devices
- beat-synced motion smoothness issues
- config schema drift
- un-analyzed tracks with no phrase segments can hold the previous LED look after an active content change until stop/idle or another content change
