---
doc_status: current
truth_level: code-verified
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
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
- The immutable pack loader/player, MIDI-input adapter, output-backend abstraction, Enttec frame sender, validated default-off config, startup bundle, atomic runtime controller, status block, and runtime commands are implemented and software-tested components.
- T7b loads config and builds the player/controller/sender; T7c wires the sole per-tick frame driver into `StateManager`; T7e adds validate-first reload/backend/enable commands and sanitized status. All remain default-off and hardware-unvalidated.
- **T7c pack driver** (`StateManager._drive_pack_output`, run once per tick via the `_push_tick` wrapper): the **sole caller of `PackOutputBackend.submit_frame`** — do not add another. The executor's `backend.trigger()` is scene-SELECTION only and never emits DMX, so the two never collide. The driver READS `DeckState`; `StateManager` remains the only writer. Automatic scripted base ZEROs on stop/stale/error/track-change/discontinuity via `LaserPackPlayer.clear_selection()`, so a held manual Static Override stands alone while idle (SoundSwitch parity); static still loses to blackout/emergency/pack-disabled/shutdown. Autoloop output stays safe-zero (driver never calls `select_autoloop`) until T7d.
- **T7e runtime control** (`soundswitch_pack_runtime.py`, `soundswitch_pack_controller.py`): the live pack runtime is one immutable `PackRuntime` bundle published to `StateManager` by a single atomic assignment (`set_pack_runtime`), so the push loop reads a consistent snapshot per tick. The `set_soundswitch_pack` runtime command (reload/backend/enable) is validate-first on the command thread via `SoundSwitchPackController`: no implicit hot-enable; stop-before-start on the shared Enttec serial port with an explicit `frame_sender.zero_and_stop()` on the OLD sender (NoneBackend.submit_frame is a no-op, so the bundle swap alone does not darken the rig); no partial swap; pack failure → disabled/none, never MIDI; runtime `backend=midi` deferred. Sanitized `soundswitch_pack` status + sanitized command errors (no paths/ports/aliases/devices/UUIDs/raw messages).
- **Confirmed active gaps:** no menubar `Export from SS` or canonical in-place replacement/reload workflow; runtime pause currently clears the scripted base because `PAUSE` and stop both present `playing=false`; the driver does not explicitly require scripted mode/id; controller snapshot health/error/drop fields are not applied to the output gate; pack status is too narrow for final operations; T7d has four conductor-accepted integrity captures across arm/refire, but four scenario pairs and the unique oracle remain, so there is no native Autoloop phase mapping. See `docs/plans/active/soundswitch_exporter_remaining_work.md`.
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
- inspect `tests/` for OS2L, SoundSwitch engine/injector, pack decoder/compiler/verifier/player, startup/controller, StateManager driver, MIDI input, frame sender, Enttec, shadow, and T7d tooling
- broad command: `python -m unittest discover tests`

Change contract:
- If changing OS2L payloads or routing, inspect `state_manager.py` and `sound_switch_engine.py` together.
- Update `docs/status/feature_status_matrix.md` and this card.

Known risks:
- breaking deck fanout
- changing send order without tests
- assuming another SoundSwitch version behaves the same
