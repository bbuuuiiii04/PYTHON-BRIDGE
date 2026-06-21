---
doc_status: current
truth_level: code-verified
last_verified_commit: 51367a1
last_verified_date: 2026-06-21
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

Task 1 boundary:
- The strict read-only SoundSwitch decoder has no bridge config schema or tracked example-config keys. Exporter, pack, verifier/player, backend, and Enttec configuration remain planned and unimplemented.
- Existing OS2L, laser, LED/Govee, Rekordbox, and runtime-status configuration is unchanged.

Authoritative code:
- `config.py`
- `laser_config.py`
- `led_config.py`
- `config/*.example.json`
- `.gitignore` for local config expectations

Key symbols:
- config defaults in `config.py`
- `load_laser_config`
- `load_led_config`
- schema validation helpers

Runtime flow:
- startup loads defaults and optional local config
- config examples define tracked templates
- local secrets/configs must remain ignored

Config:
- `config/laser_director.example.json`
- `config/led_look_director.example.json`
- local ignored `config/laser_director.json`
- local ignored `config/led_look_director.json`
- known backup `config/led_look_director.json.backup_1781599611` must not be committed
- LED `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` default to empty objects when absent.
- Accepted LED slot-fill strategy values are `gradient_even`, `random_with_replacement`, and `random_with_mono_chance`; invalid values disable the color engine while leaving LED config availability intact.
- LED `color_engine.slot_mono_chance_by_look` defaults to `{}` and accepts per-look numeric probabilities in `[0, 1]`; invalid, bool, or non-object values disable the color engine while leaving LED config availability intact.
- LED `scripted_mode` is an optional top-level object with `default_role` and `role_map`. Source/default roles exclude `utility`, but `utility` is accepted as a destination meaning the configured blackout bank. Absent config maps scripted groove/drop/post-drop to `utility`; a present partial map falls back to `default_role`.
- M2.5 slotized generic LED looks such as `rt_groove_chase`, `rt_post_drop_chase`, Patch E1 nebula looks, Patch E2 `rt_post_drop_center_comet`, and Patch E3 `rt_twinkle` are additive config entries. Patch F moves legacy color-suffix looks out of the tracked example `default` bank into `legacy_color_suffix` storage while keeping their look definitions intact.
- Local ignored `config/led_look_director.json` can legitimately lag the tracked example; mirror Patch F to live config only with explicit operator approval and a loader check.
- Point/mono palette ranges can collapse slot-color entries 0-4 to one solid RGB for any slot cue; `random_with_mono_chance` can also opt individual looks into probabilistic solid slots 0-4; slot 5 remains reserved pure white.

Tests:
- inspect `tests/` for laser config and LED config tests
- run config-specific tests when schema changes
- `tests/test_color_engine_config.py` covers LED color-engine slot-fill strategy defaults, accepted values, mono-chance parsing, and invalid-value rejection.
- `tests/test_led_config.py` covers the LED `scripted_mode` blackout defaults, accepted `utility` destinations and partial maps, and invalid role/schema rejection.

Change contract:
- If schema changes, update loaders, example configs, setup docs, feature/status matrices, and tests.
- Never commit secrets, local device IPs, local API keys, or backup files.

Known risks:
- schema docs drifting from validators
- local config copied into repo
- examples claiming live readiness without validation evidence
