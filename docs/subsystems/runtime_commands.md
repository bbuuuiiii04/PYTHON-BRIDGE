---
doc_status: current
truth_level: code-verified
last_verified_commit: eff532e
last_verified_date: 2026-06-18
validation_scope: software-only
---

# Runtime Commands Subsystem

Status:
- implementation: alpha
- software-tested: partial / test inventory pending
- hardware-validated: no
- compatibility: local setup only

Purpose:
- Own local status snapshots, the throttled `[BEAT]` operator heartbeat, and append-only JSONL runtime command handling.

Authoritative code:
- `runtime_status.py`
- `validation_runner.py`
- callback wiring in `__main__.py`

Key symbols:
- `STATUS_PATH`
- `COMMANDS_PATH`
- `StatusWriter`
- `CommandReader`
- `parse_command()`
- `CommandReader.handle_command()`

Runtime flow:
- `StatusWriter` periodically writes `/tmp/rb_ss_bridge_v2_status.json`.
- Each status snapshot includes a compact `heartbeat` block, and `StatusWriter` logs one throttled
  `[BEAT]` line with deck/master, BPM, phrase, laser scene, LED look, color palette, and RGB health.
  This reads existing status/snapshot provider surfaces from the status thread; it does not run in
  the 200 Hz StateManager push loop.
- Optional status provider failures are fail-soft. The status JSON falls back to unavailable/provider
  error fields, and repeated provider-failure warnings are throttled so a persistent provider
  failure does not flood the live-watch stream.
- `CommandReader` creates/truncates `/tmp/rb_ss_bridge_v2_commands.jsonl` at startup with mode `0600`.
- Operators append one JSON object per line.
- `parse_command()` validates command shape and payloads.
- `CommandReader.handle_command()` invokes callbacks when wired.

Accepted commands:
- `run_validation`
- `toggle_smart_drop`
- `toggle_smart_breakdown`
- `toggle_laser_director`
- `set_laser_director`
- `laser_blackout`
- `laser_clear_blackout`
- `laser_scene`
- `laser_clear_scene_override`
- `toggle_record_session`
- `set_led_look_director`
- `led_scene`
- `led_blackout`
- `led_clear_blackout`
- `led_clear_scene_override`

Detailed command table:
- `docs/setup/runtime_commands.md`

Tests:
- inspect `tests/` for runtime command parser/handler coverage
- `tests/test_runtime_status.py` covers the heartbeat payload, throttled log line, and fail-soft
  color-engine provider handling.
- run `python -m unittest discover tests`
- run `python tools/check_docs_drift.py` after command changes

Change contract:
- If `parse_command()` changes, update this file and `docs/setup/runtime_commands.md`.
- If callback wiring changes, inspect `__main__.py` and update this file.
- If status/command paths change, update README, setup docs, and drift checks.

Known risks:
- Accepted command names do not prove callbacks are wired.
- Callback success does not prove hardware-visible behavior.
- Runtime command docs are code-derived; if docs and `runtime_status.py` disagree, code wins.
