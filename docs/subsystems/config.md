---
doc_status: current
truth_level: code-verified
last_verified_commit: cb31cf8
last_verified_date: 2026-06-25
validation_scope: software-only
---

# Configuration

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: local config files and examples only

Purpose:
- Track config sources, config validation, local ignored config behavior, and schema-change obligations.

SoundSwitch pack-player boundary:
- `soundswitch_pack_player_config.py` implements the T7a startup-only, never-raising config loader.
- `config/soundswitch_pack_player.example.json` is tracked, disabled, dry-run, and `output_backend: "none"` by default. The ignored local copy is `config/soundswitch_pack_player.json`.
- This config is loaded by startup/reload orchestration. When explicitly enabled with backend `pack`, it builds the verified player, controller inputs, fixture-map-bound Enttec sender, and StateManager runtime bundle. Absent/disabled config preserves legacy MIDI; dry-run/none opens no physical pack output.
- RW-5 adds copied operational status only. It does not change this schema, the tracked inert defaults,
  or live ignored config. Current live-config state was not inspected.

Authoritative code:
- `config.py`
- `laser_config.py`
- `led_config.py`
- `soundswitch_pack_player_config.py`
- `config/*.example.json`
- `.gitignore` for local config expectations

Key symbols:
- config defaults in `config.py`
- `load_laser_config`
- `load_led_config`
- `load_soundswitch_pack_player_config`
- schema validation helpers

Runtime flow:
- startup loads defaults and optional local config
- config examples define tracked templates
- local secrets/configs must remain ignored

Config:
- `config/laser_director.example.json`
- `config/led_look_director.example.json`
- `config/soundswitch_pack_player.example.json`
- local ignored `config/laser_director.json`
- local ignored `config/led_look_director.json`
- local ignored `config/soundswitch_pack_player.json`
- known backup `config/led_look_director.json.backup_1781599611` must not be committed
- LED `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` default to empty objects when absent.
- Accepted LED slot-fill strategy values are `gradient_even`, `random_with_replacement`, and `random_with_mono_chance`; invalid values disable the color engine while leaving LED config availability intact.
- LED `color_engine.slot_mono_chance_by_look` defaults to `{}` and accepts per-look numeric probabilities in `[0, 1]`; invalid, bool, or non-object values disable the color engine while leaving LED config availability intact.
- LED `scripted_mode` is an optional top-level object with `default_role` and `role_map`. Source/default roles exclude `utility`, but `utility` is accepted as a destination meaning the configured blackout bank. Absent config maps scripted groove/drop/post-drop to `utility`; a present partial map falls back to `default_role`.
- M2.5 slotized generic LED looks such as `rt_groove_chase`, `rt_post_drop_chase`, Patch E1 nebula looks, Patch E2 `rt_post_drop_center_comet`, and Patch E3 `rt_twinkle` are additive config entries. Patch F moves legacy color-suffix looks out of the tracked example `default` bank into `legacy_color_suffix` storage while keeping their look definitions intact.
- Local ignored `config/led_look_director.json` can legitimately lag the tracked example; mirror Patch F to live config only with explicit operator approval and a loader check.
- Point/mono palette ranges can collapse slot-color entries 0-4 to one solid RGB for any slot cue; `random_with_mono_chance` can also opt individual looks into probabilistic solid slots 0-4; slot 5 remains reserved pure white.
- SoundSwitch pack-player path precedence is explicit argument, then `RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG`, then `config/soundswitch_pack_player.json`; an absent selected file returns `not_configured`.
- Pack-player config defaults are `enabled=false`, `dry_run=true`, and `output_backend=none`. Supported configured backends are `none`, `midi`, and `pack`; runtime command switching to `midi` remains deliberately unsupported. Pack enable/reload/backend actions are explicit and validate-first.
- The ignored local pack config was absent in the 2026-06-23 audit. No pack/Enttec live setup is therefore claimed.
- `fixture_map` must define exactly CH1 through CH19 with integer DMX addresses 1 through 512. A non-empty `fixture_map_path` is authoritative over the inline map and resolves relative to the containing config file unless absolute.
- Pack-player timeouts must be positive integers. Paths and the Enttec port field must be strings. `midi_input_aliases` is optional; when present it maps non-empty saved static-controller device identities to non-empty local port-alias strings and overrides the default device-name auto-bind.
- Invalid JSON, unknown keys, duplicate JSON keys, duplicate fixture channels after integer coercion, invalid map files, and invalid field types fail closed as `invalid_config`; the loader never raises.

Tests:
- inspect `tests/` for laser config and LED config tests
- run config-specific tests when schema changes
- `tests/test_color_engine_config.py` covers LED color-engine slot-fill strategy defaults, accepted values, mono-chance parsing, and invalid-value rejection.
- `tests/test_led_config.py` covers the LED `scripted_mode` blackout defaults, accepted `utility` destinations and partial maps, and invalid role/schema rejection.
- `tests/test_soundswitch_pack_player_config.py` covers T7a defaults, path precedence, inline/external fixture maps, strict validation, immutability, and the never-raising contract.

Change contract:
- If schema changes, update loaders, example configs, setup docs, feature/status matrices, and tests.
- Never commit secrets, local device IPs, local API keys, or backup files.

Known risks:
- schema docs drifting from validators
- local config copied into repo
- examples claiming live readiness without validation evidence
