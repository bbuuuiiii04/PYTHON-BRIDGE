---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
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
- Accepted LED slot-fill strategy values are `gradient_even` and `random_with_replacement`; invalid values disable the color engine while leaving LED config availability intact.
- M2.5 slotized generic LED looks such as `rt_groove_chase`, `rt_post_drop_chase`, Patch E1 nebula looks, Patch E2 `rt_post_drop_center_comet`, and Patch E3 `rt_twinkle` are additive config entries; legacy color-suffix looks stay defined until the gated cleanup patch.
- Point/mono palette ranges can collapse slot-color entries 0-4 to one solid RGB for any slot cue; slot 5 remains reserved pure white.

Tests:
- inspect `tests/` for laser config and LED config tests
- run config-specific tests when schema changes
- `tests/test_color_engine_config.py` covers LED color-engine slot-fill strategy defaults, accepted values, and invalid-value rejection.

Change contract:
- If schema changes, update loaders, example configs, setup docs, feature/status matrices, and tests.
- Never commit secrets, local device IPs, local API keys, or backup files.

Known risks:
- schema docs drifting from validators
- local config copied into repo
- examples claiming live readiness without validation evidence
