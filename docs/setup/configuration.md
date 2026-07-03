---
doc_status: current
truth_level: code-verified
last_verified_commit: 944bc83
last_verified_date: 2026-07-03
validation_scope: software-only
---

# Configuration Setup

This repo uses tracked example configs plus local ignored configs. Do not commit local device secrets, local IPs, API keys, or backup files.

Audit P1 (2026-07-03): the tracked LED Look Director example removed an unread top-level
`metadata` placeholder. This does not change local config semantics.

Audit P3 (2026-07-03): the old zero-valued OS2L timing-compensation constant was removed from
runtime code; there is no supported user config knob for elapsed compensation.

Audit P4 (2026-07-03): Laser `pre_drop_scene` is no longer a current personality field. Old local
configs that still contain it continue to load because the loader ignores it as deprecated. Laser
scene `fallback_scene` must point at an existing scene, and `cooldown_beats` must not be negative.
`post_drop_cycle_beats` remains reserved for future laser post-drop behavior.

SoundSwitch Tasks T7a/T7b/T7c/T7e add a validated pack-player config schema,
tracked inert example, startup construction, StateManager frame driver,
validate-first runtime controls, and sanitized status. The default remains
absent/disabled/dry-run/none, so no pack hardware opens unless a reviewed local
config explicitly enables backend `pack`.

RW-5 adds copied operational status only. It does not alter this schema or tracked defaults, and no
ignored live config was read or changed during implementation.

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

The tracked example is inert: `enabled=false`, `dry_run=true`, and
`output_backend=none`. Copy it to the ignored local filename only when preparing
a reviewed local setup. Current local-file state was not inspected during RW-5 implementation.

`fixture_map` must contain exactly the string keys `1` through `19`, each mapped to a unique integer DMX address from 1 through 512. `fixture_map_path` is an optional alternative: when non-empty it takes precedence over the inline map. Relative map paths resolve against the directory containing the selected config file; absolute paths remain absolute. Map files contain the mapping object itself.

Supported `output_backend` values are `none`, `midi`, and `pack`. Both timeout fields must be positive integers. `pack_path`, `fixture_map_path`, and `enttec_port` are strings. `midi_input_aliases` is optional; when present it maps non-empty saved static-controller device identities to non-empty local port aliases and overrides device-name auto-bind. Do not put actual device identifiers or live port details in the tracked example or docs.

When config is explicitly enabled with `output_backend=pack`, startup loads and
verifies `pack_path`, constructs controller inputs and the fixture-map-bound
sender, and confirms serial readiness. Missing or ambiguous controller input
degrades manual Static Looks while pack DMX can continue; serial/sender failure
still disables output and never falls back to physical MIDI. Runtime `set_soundswitch_pack` supports explicit
reload/backend/enable actions, with runtime `backend=midi` intentionally
unsupported.

Temporary Art-Net truth-check mode is controlled by environment variables, not a
new config file:

- `RBSS_ARTNET_TRUTH_CHECK=1` enables validation-only U1 shadow emission.
- `RBSS_ARTNET_UNIVERSE=1` selects the bridge truth universe; this variable alone emits nothing.
- `RBSS_ARTNET_TARGETS` optionally overrides comma-separated IP-literal targets.
- `RBSS_ARTNET_TRUTH_SIDECAR` optionally overrides `/tmp/rbss_artnet_truth_frames.jsonl`.

In truth-check mode startup can render the pack without Enttec/serial by using a
sender-free pack backend plus the validation sink. Production pack output still
submits software zero while SoundSwitch is connected.

This remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**. Do not create
or enable the local config until the active remaining-work roadmap reaches its
reviewed deployment/hardware gate.

## LED color-engine notes

- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` default to empty objects when absent.
- Strategy maps accept only `gradient_even`, `random_with_replacement`, and `random_with_mono_chance`; invalid values disable the color engine while keeping the LED config loadable.
- `color_engine.slot_mono_chance_by_look` defaults to `{}` and accepts per-look numeric probabilities in `[0, 1]`; bools, non-numbers, out-of-range values, and non-object values disable only the color engine.
- `color_engine.locked_palette_by_look` defaults to `{}` and maps look names to existing palette names; unknown palette names, non-string values, and non-object values disable only the color engine.
- M2.5 slot cues always resolve six slot colors; slot 5 is reserved pure white.
- Point or mono palette selections can make slots 0-4 one solid RGB for any slot cue, including realtime chase/comet/twinkle cues. `random_with_mono_chance` can opt individual looks into probabilistic solid slots 0-4 without changing shipped behavior when its chance map is empty or zero.
- In the tracked LED example, Patch F keeps generic slot looks in `banks.default` and stores legacy color-suffix realtime looks in `banks.legacy_color_suffix`. The director selects `banks.default`; the legacy bank is preservation storage unless future code explicitly selects it.
- Do not mirror Patch F into ignored live LED config without explicit operator approval, because live config may be behind the tracked example and is hardware-adjacent.

## LED scripted-mode notes

- `safety.scripted_mode_automation` is the master enable switch for automatic LED output during SoundSwitch scripted tracks. The shipped `config/led_look_director.example.json` enables it (`true`) paired with the conservative blackout `scripted_mode` policy, so out-of-box scripted tracks black out LEDs except during buildup/pre-drop and breakdown. Set it to `false` to keep LEDs fully inert during scripted tracks. (The code-level `LEDSafety` dataclass default in `led_models.py` is still `false`, but the loader requires the JSON key, so the example value governs.)
- The top-level `scripted_mode` block controls role remapping when that master switch is enabled. Source roles and `default_role` exclude `utility`; `role_map` destinations may use `utility` to select the configured blackout bank.
- If `scripted_mode` is absent, the loader maps `groove`, `drop`, and `post_drop` to `utility` (off), `buildup` and `pre_drop` to `buildup`, and `ambient` and `breakdown` to `breakdown`.
- A present partial `role_map` is operator opt-in. Missing roles fall back to `default_role`, which defaults to `breakdown`.
