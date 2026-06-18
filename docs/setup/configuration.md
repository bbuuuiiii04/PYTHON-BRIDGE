---
doc_status: current
truth_level: code-verified
last_verified_commit: 51367a1
last_verified_date: 2026-06-18
validation_scope: software-only
---

# Configuration Setup

This repo uses tracked example configs plus local ignored configs. Do not commit local device secrets, local IPs, API keys, or backup files.

## Tracked examples

- `config/laser_director.example.json`
- `config/led_look_director.example.json`

## Local configs

Expected local files may include:

- `config/laser_director.json`
- `config/led_look_director.json`

These are local setup files, not public support evidence.

## Known backup warning

Do not commit:

```text
config/led_look_director.json.backup_1781599611
```

## Schema changes

Use `docs/agents/task_playbooks/update_config_schema.md` before changing config schema or examples.

## LED color-engine notes

- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` default to empty objects when absent.
- Strategy maps accept only `gradient_even`, `random_with_replacement`, and `random_with_mono_chance`; invalid values disable the color engine while keeping the LED config loadable.
- `color_engine.slot_mono_chance_by_look` defaults to `{}` and accepts per-look numeric probabilities in `[0, 1]`; bools, non-numbers, out-of-range values, and non-object values disable only the color engine.
- M2.5 slot cues always resolve six slot colors; slot 5 is reserved pure white.
- Point or mono palette selections can make slots 0-4 one solid RGB for any slot cue, including realtime chase/comet/twinkle cues. `random_with_mono_chance` can opt individual looks into probabilistic solid slots 0-4 without changing shipped behavior when its chance map is empty or zero.
- In the tracked LED example, Patch F keeps generic slot looks in `banks.default` and stores legacy color-suffix realtime looks in `banks.legacy_color_suffix`. The director selects `banks.default`; the legacy bank is preservation storage unless future code explicitly selects it.
- Do not mirror Patch F into ignored live LED config without explicit operator approval, because live config may be behind the tracked example and is hardware-adjacent.
