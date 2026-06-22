---
doc_status: current
truth_level: code-verified
last_verified_commit: b7e0e66
last_verified_date: 2026-06-21
validation_scope: software-only
---

# Configuration Setup

This repo uses tracked example configs plus local ignored configs. Do not commit local device secrets, local IPs, API keys, or backup files.

SoundSwitch Task 7a adds a validated, startup-only pack-player config schema and tracked example. It is not wired into bridge startup or runtime yet, so existing SoundSwitch OS2L, laser, LED/Govee, Rekordbox, status, MIDI, and Enttec behavior remains unchanged.

## Tracked examples

- `config/laser_director.example.json`
- `config/led_look_director.example.json`
- `config/soundswitch_pack_player.example.json`

## Local configs

Expected local files may include:

- `config/laser_director.json`
- `config/led_look_director.json`
- `config/soundswitch_pack_player.json`

These are local setup files, not public support evidence.

## Known backup warning

Do not commit:

```text
config/led_look_director.json.backup_1781599611
```

## Schema changes

Use `docs/agents/task_playbooks/update_config_schema.md` before changing config schema or examples.

## SoundSwitch pack-player config

`soundswitch_pack_player_config.py` resolves the selected config in this order:

1. explicit loader path;
2. `RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG`;
3. `config/soundswitch_pack_player.json`.

If the selected file is absent, the result is `available=false`, `reason=not_configured`. Any read, JSON, schema, or fixture-map error returns `reason=invalid_config`; the loader does not raise.

The tracked example is inert: `enabled=false`, `dry_run=true`, and `output_backend=none`. Copy it to the ignored local filename only when preparing a local setup. T7a does not start MIDI, serial, Enttec, DMX, or controller-input workers.

`fixture_map` must contain exactly the string keys `1` through `19`, each mapped to an integer DMX address from 1 through 512. `fixture_map_path` is an optional alternative: when non-empty it takes precedence over the inline map. Relative map paths resolve against the directory containing the selected config file; absolute paths remain absolute. Map files contain the mapping object itself.

Supported `output_backend` values are `none`, `midi`, and `pack`. Both timeout fields must be positive integers. `pack_path`, `fixture_map_path`, and `enttec_port` are strings. `midi_input_aliases` maps non-empty saved device identities to non-empty local port aliases. Do not put actual device identifiers or live port details in the tracked example or docs.

This remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**. Backend selection and runtime ownership are later Task 7 work.

## LED color-engine notes

- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` default to empty objects when absent.
- Strategy maps accept only `gradient_even`, `random_with_replacement`, and `random_with_mono_chance`; invalid values disable the color engine while keeping the LED config loadable.
- `color_engine.slot_mono_chance_by_look` defaults to `{}` and accepts per-look numeric probabilities in `[0, 1]`; bools, non-numbers, out-of-range values, and non-object values disable only the color engine.
- M2.5 slot cues always resolve six slot colors; slot 5 is reserved pure white.
- Point or mono palette selections can make slots 0-4 one solid RGB for any slot cue, including realtime chase/comet/twinkle cues. `random_with_mono_chance` can opt individual looks into probabilistic solid slots 0-4 without changing shipped behavior when its chance map is empty or zero.
- In the tracked LED example, Patch F keeps generic slot looks in `banks.default` and stores legacy color-suffix realtime looks in `banks.legacy_color_suffix`. The director selects `banks.default`; the legacy bank is preservation storage unless future code explicitly selects it.
- Do not mirror Patch F into ignored live LED config without explicit operator approval, because live config may be behind the tracked example and is hardware-adjacent.

## LED scripted-mode notes

- `safety.scripted_mode_automation` is the master enable switch for automatic LED output during SoundSwitch scripted tracks. The shipped `config/led_look_director.example.json` enables it (`true`) paired with the conservative blackout `scripted_mode` policy, so out-of-box scripted tracks black out LEDs except during buildup/pre-drop and breakdown. Set it to `false` to keep LEDs fully inert during scripted tracks. (The code-level `LEDSafety` dataclass default in `led_models.py` is still `false`, but the loader requires the JSON key, so the example value governs.)
- The top-level `scripted_mode` block controls role remapping when that master switch is enabled. Source roles and `default_role` exclude `utility`; `role_map` destinations may use `utility` to select the configured blackout bank.
- If `scripted_mode` is absent, the loader maps `groove`, `drop`, and `post_drop` to `utility` (off), `buildup` and `pre_drop` to `buildup`, and `ambient` and `breakdown` to `breakdown`.
- A present partial `role_map` is operator opt-in. Missing roles fall back to `default_role`, which defaults to `breakdown`.
