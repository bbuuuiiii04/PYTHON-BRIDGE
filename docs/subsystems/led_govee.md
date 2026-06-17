---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
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
- decisions: manual override, blackout, role-entry look selection, cloud/realtime ownership, beat sync instances
- outputs: cloud scene commands or realtime UDP frame packets

Config:
- `config/led_look_director.example.json`
- local ignored `config/led_look_director.json`
- env secrets such as `GOVEE_API_KEY`
- realtime enable flag if present in startup

Tests:
- inspect `tests/` for LED color engine, Govee realtime runner, frame renderer, state manager LED integration, and config tests
- broad command: `python -m unittest discover tests`

Change contract:
- If changing look policy, inspect director, models, config validation, and state manager dispatch seam.
- If changing realtime output, inspect runner, transport, renderer, owner state, and beat sync engine.
- If changing cloud output, inspect scene adapter and runtime sender.
- Update this card, feature matrix, validation matrix, active work registry, and config docs.

Known risks:
- API/cloud rate limits
- realtime protocol/device specificity
- confusing local H612D behavior with all Govee devices
- beat-synced motion smoothness issues
- config schema drift
