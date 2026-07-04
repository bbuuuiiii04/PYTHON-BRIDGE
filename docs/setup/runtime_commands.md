---
doc_status: current
truth_level: code-verified
last_verified_commit: 74febec
last_verified_date: 2026-06-29
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Runtime Commands

Runtime commands are append-only JSONL records read by `CommandReader` in `runtime_status.py`.
The parser, not this document, is authoritative. If this document and `parse_command()` disagree, `parse_command()` wins, because apparently even documentation needs a leash.

Audit P1 (2026-07-03): smart-drop and smart-breakdown runtime callbacks now return explicit
success/failure booleans, so a full event queue is surfaced through `commands.last_error` instead
of reporting a success-shaped command result.

SoundSwitch T7e adds the accepted `set_soundswitch_pack` command and a sanitized
`soundswitch_pack` status block. The callback is wired through
`SoundSwitchPackController` on the command thread; blocking load/verify/serial
work never enters the 200 Hz push loop. The menubar `Export from SS` action adds
no command: after a verified publish it reuses only the existing `reload` action
when the bridge is running and pack output is enabled, and waits for a fresh
`soundswitch_pack.pack_sha12` match. That export/reload action never sends `enable` or `backend`;
stopped or disabled pack runtime receives no reload command. The SoundSwitch-connection auto-switch
does send `set_soundswitch_pack action=enable`, with one bounded retry after a fresh disconnected
`pack_start_failed`; there is no manual pack button and no implicit hot-enable.

The additive schema-1 `soundswitch_pack` object is:

| Key | Bounded meaning |
| --- | --- |
| `available`, `enabled`, `pack_loaded` | Bundle booleans. |
| `backend` | `pack` or `disabled`. |
| `pack_sha12` | Existing public manifest prefix used for reload acknowledgement. |
| `pack_sha256` | Full public manifest hash used by the Art-Net compare tool to reject stale/mismatched runs. |
| `reason` | Sanitized runtime category. |
| `phase_offset_beats` | Finite native Autoloop calibration value; default `0.0`. |
| `operational_state` | `disabled`, `blackout`, `input_degraded`, `static_held`, `scripted_active`, native Autoloop states (`rendering_active`, `empty_dark_look`, `missing_binding`, `missing_autoloop_file`, `unsupported_layout`, `soundswitch_present_native_suppressed`), `autoloop_phase_blocked`, or `software_zero_frame`. |
| `scripted_active`, `input_degraded`, `static_held`, `blackout`, `autoloop_phase_blocked` | Authoritative companion booleans; more than one may be true. `input_degraded` can mean manual Static Look input is unavailable while scripted pack DMX continues. |
| `overlay_suppressed` | Stable diagnostic object with `static_held`, `blackout`, and `input_degraded` booleans. These are true only when SoundSwitch-connected suppression forces the pack lane to software ZERO while a manual overlay/degraded-input condition was present. |
| `software_zero_frame` | The rendered CH1-CH19 software frame equals zero; not serial or physical proof. |
| `frame_count` | Non-negative attempted normal software-frame count; not confirmed sends. |
| `has_active_identity` | Boolean derived from the in-memory accepted-identity property; no identity is exposed. |
| `native_autoloop` | Bounded copied state for native Autoloop role/scene/note, SoundSwitch display name, target identity, anchor beat, phase tick, reason, and diagnostic. Values are absent when no native Autoloop is selected. |
| `truth_check` | Temporary validation-only Art-Net status: enabled flag, run ID, universe, targets, sidecar path, current U1 sequence, queue drop/overflow counts, send/sidecar errors, pack SHA, and fixture-map CH1 DMX address. It is default-off and does not prove physical output. |

`StateManager.get_pack_status()` returns a copy of its published dict and overlays truth-check worker
counters only on the status-reader path, not the 200 Hz render path. Sender health is deliberately
absent. A stale status file renders `Lighting: no status yet` in the menubar.

## Runtime files

| Purpose | Path | Notes |
| --- | --- | --- |
| Status JSON | `/tmp/rb_ss_bridge_v2_status.json` | Written by `StatusWriter`; includes process, state manager, deck runtime, SoundSwitch, validation, command, laser, and LED sections. |
| Command JSONL | `/tmp/rb_ss_bridge_v2_commands.jsonl` | Created/truncated by `CommandReader` at startup with mode `0600`; append one JSON object per line. |

The status JSON also includes a compact `heartbeat` object. `StatusWriter` logs the same operator
summary as one throttled `[BEAT]` line: show deck, separate Rekordbox master deck when valid and
non-stale, BPM, phrase, laser scene, LED look, palette, and RGB health. The heartbeat is status-only
observability; it does not send SoundSwitch, laser, LED, or Govee commands.

If an optional status provider fails, the status snapshot falls back to provider-error fields instead
of crashing the status thread. Repeated provider-failure warnings are throttled for live-watch
readability.

Example command append:

```bash
echo '{"cmd":"run_validation"}' >> /tmp/rb_ss_bridge_v2_commands.jsonl
```

## Accepted commands

| Command | Required fields | Optional fields | Validation notes | Runtime effect |
| --- | --- | --- | --- | --- |
| `run_validation` | none | none | Parser only requires `cmd`. | Starts the validation runner asynchronously. |
| `toggle_smart_drop` | none | none | Parser only requires `cmd`. | Invokes the smart-drop toggle callback if wired. |
| `toggle_smart_breakdown` | none | none | Parser only requires `cmd`. | Invokes the smart-breakdown toggle callback if wired. |
| `toggle_laser_director` | none | none | Parser only requires `cmd`. | Toggles Laser Director through callback if wired. |
| `set_laser_director` | `enabled` | none | `enabled` must be boolean. | Sets Laser Director enabled state through callback if wired. |
| `laser_blackout` | none | none | Parser only requires `cmd`. | Invokes laser blackout callback if wired. |
| `laser_clear_blackout` | none | none | Parser only requires `cmd`. | Clears laser blackout callback if wired. |
| `laser_scene` | `scene` | `ttl_s` | `scene` must be a non-empty string. `ttl_s` defaults to `4.0`, must be numeric and finite, and is clamped to `0.0..30.0`. | Sets a temporary laser scene override through callback if wired. |
| `laser_clear_scene_override` | none | none | Parser only requires `cmd`. | Clears laser scene override callback if wired. |
| `toggle_record_session` | none | `path`, `dedup` | `path`, when present, must be a non-empty string. `dedup` defaults to `false` and must be boolean. | Toggles session recording through callback if wired. |
| `set_led_look_director` | `enabled` | none | Rejects unknown fields. `enabled` must be boolean. | Sets LED Look Director enabled state through callback if wired. |
| `led_scene` | `look` or `scene` | `ttl_s`, `target` | Rejects unknown fields. `look`/`scene` must identify the same non-empty string if both are provided. Stored as normalized `look`. `ttl_s`, when present, must be numeric, finite, positive, and `<= 300.0`. `target`, when present, must be a non-empty string. | Sets a temporary/manual LED look through callback if wired. |
| `led_blackout` | none | `reason`, `target` | Rejects unknown fields. `reason` and `target`, when present, must be non-empty strings. | Invokes LED blackout callback if wired. |
| `led_clear_blackout` | none | none | Rejects all payload fields except `cmd`. | Clears LED blackout callback if wired. |
| `led_clear_scene_override` | none | none | Rejects all payload fields except `cmd`. | Clears LED scene override callback if wired. |
| `led_palette_queue` | `name` | none | `name` must be a non-empty palette name string. | Queues a palette through the StateManager event rail when wired; software command surface only. |
| `led_palette_override` | `name` | none | `name` must be a non-empty palette name string. | Overrides/fades to a palette through the StateManager event rail when wired; software command surface only. |
| `led_palette_lock` | none | none | Rejects all payload fields except `cmd`. | Locks the current LED palette through the palette-control event rail when wired. |
| `led_palette_unlock` | none | none | Rejects all payload fields except `cmd`. | Unlocks LED palette automation through the palette-control event rail when wired. |
| `led_rainbow_toggle` | none | none | Rejects all payload fields except `cmd`. | Toggles Rainbow mode through the palette-control event rail when wired. |
| `set_soundswitch_pack` | `action` | `backend`, `enabled` | Rejects unknown fields. `action` must be `reload`\|`backend`\|`enable`. `backend` action requires `backend` ∈ `pack`\|`none`\|`midi`. `enable` action requires boolean `enabled`. | Validate-first pack reload/backend/enable via `SoundSwitchPackController` (command thread). Runtime `backend=midi` is deferred (sanitized `unsupported_action`). No implicit hot-enable; pack failure falls back to disabled/none, never MIDI. Status/errors are sanitized. |

## Parser behavior

- Each line must be valid JSON.
- Each command must be a JSON object.
- Every command must include a non-empty string `cmd`.
- Unknown command names are rejected.
- Some callbacks may be absent depending on startup wiring; accepted commands can therefore parse successfully without producing hardware-visible behavior.
- Callback failures are captured in the command status section instead of crashing the command reader.

## Examples

```bash
# Run diagnostics
echo '{"cmd":"run_validation"}' >> /tmp/rb_ss_bridge_v2_commands.jsonl

# Enable Laser Director
echo '{"cmd":"set_laser_director","enabled":true}' >> /tmp/rb_ss_bridge_v2_commands.jsonl

# Temporary laser override for four seconds
echo '{"cmd":"laser_scene","scene":"drop_white_strobe","ttl_s":4.0}' >> /tmp/rb_ss_bridge_v2_commands.jsonl

# LED look override for 30 seconds
echo '{"cmd":"led_scene","look":"rt_groove_center_chase","ttl_s":30.0}' >> /tmp/rb_ss_bridge_v2_commands.jsonl

# LED blackout with operator reason
echo '{"cmd":"led_blackout","reason":"operator_test"}' >> /tmp/rb_ss_bridge_v2_commands.jsonl
```

## Current limitation

This document describes the software command surface only. It does not prove any hardware action occurred. Hardware-visible behavior still depends on local config, startup wiring, connected devices, and manual validation.
