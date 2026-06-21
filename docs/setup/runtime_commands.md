---
doc_status: current
truth_level: code-verified
last_verified_commit: eff532e
last_verified_date: 2026-06-21
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Runtime Commands

Runtime commands are append-only JSONL records read by `CommandReader` in `runtime_status.py`.
The parser, not this document, is authoritative. If this document and `parse_command()` disagree, `parse_command()` wins, because apparently even documentation needs a leash.

Tasks 1–2 add no command or status field for offline SoundSwitch decode, deterministic export, canonical-pack generation, or independent verification. Task 3 loader/player and Task 4+ MIDI/runtime/backend/Enttec controls remain planned and unimplemented; all existing command behavior is unchanged.

## Runtime files

| Purpose | Path | Notes |
| --- | --- | --- |
| Status JSON | `/tmp/rb_ss_bridge_v2_status.json` | Written by `StatusWriter`; includes process, state manager, deck runtime, SoundSwitch, validation, command, laser, and LED sections. |
| Command JSONL | `/tmp/rb_ss_bridge_v2_commands.jsonl` | Created/truncated by `CommandReader` at startup with mode `0600`; append one JSON object per line. |

The status JSON also includes a compact `heartbeat` object. `StatusWriter` logs the same operator
summary as one throttled `[BEAT]` line: deck/master, BPM, phrase, laser scene, LED look, palette, and
RGB health. The heartbeat is status-only observability; it does not send SoundSwitch, laser, LED, or
Govee commands.

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
