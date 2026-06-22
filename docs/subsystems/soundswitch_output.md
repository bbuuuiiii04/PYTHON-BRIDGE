---
doc_status: current
truth_level: code-verified
last_verified_commit: 3fa4061
last_verified_date: 2026-06-22
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
- T7b loads the config and builds the pack player/controller/Enttec sender at startup; T7c wires them into `StateManager` (default-off — neutral unless `soundswitch_pack_player`+`soundswitch_pack_backend` are passed). Status surfaces and runtime commands (T7e) are still pending.
- **T7c pack driver** (`StateManager._drive_pack_output`, run once per tick via the `_push_tick` wrapper): the **sole caller of `PackOutputBackend.submit_frame`** — do not add another. The executor's `backend.trigger()` is scene-SELECTION only and never emits DMX, so the two never collide. The driver READS `DeckState`; `StateManager` remains the only writer. Automatic scripted base ZEROs on stop/stale/error/track-change/discontinuity via `LaserPackPlayer.clear_selection()`, so a held manual Static Override stands alone while idle (SoundSwitch parity); static still loses to blackout/emergency/pack-disabled/shutdown. Autoloop output stays safe-zero (driver never calls `select_autoloop`) until T7d.
- **T7e runtime control** (`soundswitch_pack_runtime.py`, `soundswitch_pack_controller.py`): the live pack runtime is one immutable `PackRuntime` bundle published to `StateManager` by a single atomic assignment (`set_pack_runtime`), so the push loop reads a consistent snapshot per tick. The `set_soundswitch_pack` runtime command (reload/backend/enable) is validate-first on the command thread via `SoundSwitchPackController`: no implicit hot-enable; stop-before-start on the shared Enttec serial port with an explicit `frame_sender.zero_and_stop()` on the OLD sender (NoneBackend.submit_frame is a no-op, so the bundle swap alone does not darken the rig); no partial swap; pack failure → disabled/none, never MIDI; runtime `backend=midi` deferred. Sanitized `soundswitch_pack` status + sanitized command errors (no paths/ports/aliases/devices/UUIDs/raw messages).
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
