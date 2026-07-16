---
doc_status: current
truth_level: code-verified
last_verified_commit: 9191c65
last_verified_date: 2026-07-09
validation_scope: software-only; Stream Deck palette control config software-tested; AWR-157 blank_role_hold knob software-tested; AWR-161 LED round 3 config additions software-tested
---

# Configuration

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: local config files and examples only

Purpose:
- Track config sources, config validation, local ignored config behavior, and schema-change obligations.

Audit P1 (2026-07-03): `config/led_look_director.example.json` no longer includes the unread
top-level `metadata` placeholder. No local ignored config was read or changed.

Audit P3 (2026-07-03): the unused zero-valued OS2L timing-compensation constant was removed from
`config.py`; elapsed values are now raw in runtime code. No local ignored config was read or
changed.

Audit P4 (2026-07-03): Laser scene validation now fails closed when `fallback_scene` references an
unknown scene or `cooldown_beats` is negative. Laser personality `pre_drop_scene` was removed from
the tracked schema and example, but leftover keys in ignored local configs are ignored as
deprecated so existing operator configs can still load. Laser `post_drop_cycle_beats` remains as an
operator-reserved future field. No local ignored config was read or changed.

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
- LED `color_engine.locked_palette_by_look` defaults to `{}` and maps look names to existing `color_engine.palettes` names. Unknown palette names, non-string palette names, or non-object values disable the color engine while leaving LED config availability intact.
- LED `color_engine.palettes.*.type` defaults to `journey`; `fixed_rgb` palettes use an explicit
  `rgb: [r, g, b]` value and `rainbow` palettes resolve the full hue wheel manually. The tracked
  example includes weight-0 manual-only `white_sand` and `rainbow` entries for Stream Deck palette
  control.
- LED `color_engine.palette_control` is an optional object. When `enabled: true`, it validates a
  Stream Deck `device`, zero-based MIDI `channel`, `palette_notes` for existing palettes, and
  control-note fields for lock, LED mute, laser mute, Laser Solo, and Rainbow. The loader turns
  those notes into pack MIDI bindings; `laser_solo_note` is parsed/reserved for a later package and
  does not emit a binding yet.
- LED `scripted_mode` is an optional top-level object with `default_role` and `role_map`. Source/default roles exclude `utility`, but `utility` is accepted as a destination meaning the configured blackout bank. Absent config maps scripted groove/drop/post-drop to `utility`; a present partial map falls back to `default_role`.
- LED `blank_role_hold` (AWR-157, top-level boolean) defaults to `true` when absent; malformed
  (non-boolean) values fail closed. `true` suppresses the automation blackout dispatch while a
  deck is audibly playing and a look was already accepted this session, whenever the resolved
  role lands on the configured blackout look (e.g. via `scripted_mode`'s `utility` mapping); the
  room holds its current look instead. `false` restores the pre-AWR-157 blackout-on-blank
  behavior byte-for-byte.
- M2.5 slotized generic LED looks such as `rt_groove_chase`, `rt_post_drop_chase`, Patch E1 nebula looks, Patch E2 `rt_post_drop_center_comet`, and Patch E3 `rt_twinkle` are additive config entries. Patch F moves legacy color-suffix looks out of the tracked example `default` bank into `legacy_color_suffix` storage while keeping their look definitions intact.
- Local ignored `config/led_look_director.json` can legitimately lag the tracked example; mirror Patch F to live config only with explicit operator approval and a loader check.
- AWR-156 (2026-07-08) adds to the tracked example: 7 colorway strobe looks (`rt_drop_strobe_blue`/
  `_cyan`/`_green`/`_red`/`_red_white`/`_blue_cyan`/`_cyan_white`, `scene_ref: drop_strobe_colorway`,
  `color_source: baked`), and 3 promoted looks (`rt_buildup_balloon_comet`, `rt_groove_heartbeat`,
  `rt_post_drop_firework_remnants`). `width` is now a genuinely-read renderer param on
  `rt_groove_chase`/`rt_groove_nebula`/`rt_post_drop_center_comet` (previously allowlisted via
  `_SYNC_PARAM_KEYS` but silently ignored by the renderer; a config `width` value on those three had
  no effect before this round). `rt_drop_chase`/`rt_drop_nebula` were renamed to
  `rt_post_drop_remnant_chase`/`rt_post_drop_remnant_nebula` and moved from `banks.default.drop` to
  `banks.default.post_drop` (their `drop_pairs` entries deleted); renderer `scene_ref` for both is
  unchanged. Local ignored `config/led_look_director.json` was not touched by this round — mirror
  with explicit operator approval, same as Patch F.
- AWR-215 (2026-07-11) rebuilds `rt_post_drop_firework_remnants` as the sparse first-eight-beat
  sparkle half of `rt_drop_chase`. Its tracked-example `params` are empty (defaults apply).
- AWR-256 (2026-07-15) wires `ember_hold_beats` / `ember_decay_beats` for that look and removes
  dead `dim_beats` from the allowlist (it was never read by the sparse sparkle path). Tracked
  example params stay empty; a live file that still carried `dim_beats` must drop that key to
  validate.
- AWR-161 (2026-07-09) adds `hz`/`duty` to `REALTIME_EFFECT_PARAM_KEYS` for 18 migrated strobe
  effect names (the last remaining BPM-tied gates, now on the AWR-156 `_hz_strobe_on` gate), and two
  new looks to the tracked example: `rt_rainbow_drop`/`rt_rainbow_post_drop` (`scene_ref:
  rainbow_ordered`, `color_source: baked`, paired via `drop_pairs`) and
  `rt_drop_firework_explosion` (`scene_ref: drop_firework_explosion`, `color_source: baked`, paired
  via `drop_pairs` to the existing `rt_post_drop_firework_remnants`). Local ignored
  `config/led_look_director.json` was not touched by this round — mirror with explicit operator
  approval, same as Patch F/AWR-156.
- LIGHTING ENGINE v2 top-level blocks, both example-ON / absent-OFF so an un-mirrored live config
  stays byte-identical: `f2` (AWR-163, moments/darkness/drop-typing — `load_f2_config`/`F2Config`) and
  `f4` (AWR-164, texture seasoning — `load_f4_config`/`F4Config`). The `f2` block also carries
  `pre_chorus_laser_beats` (AWR-170 D.2, int; ABSENT ⇒ 0 ⇒ pre-chorus laser blackout fully off — the
  mirror rule; the example ships `4`; junk/negative clamp to 0). The `f4` block has `enabled`,
  `busy_pulse_experimental` (default false — `lowmid_pulse` stays computed-not-consumed),
  `variant_seasoning` (`{family+texture key: {param: value}}` merged into the drop cue's params —
  `house_stab`/`house_sustain`/`wall_trap`/`wall_dense`/`<fam>_default`), `euphoric_bright_looks`
  (look names preferred inside euphoric windows, fail-open), and `simmer_seasoning` (sparse-dim params
  for a measured simmer). Validation fails closed (non-finite/bool/nested param values dropped),
  unknown legacy keys are ignored. Seasoning values are TUNE-LIVE; mirror to live config with operator
  approval only. Local ignored `config/led_look_director.json` was not touched by this round.
- LED `color_engine.v2.zones.*.slot5_white` (AWR-152) is an optional per-zone RGB list (3 ints,
  0-255); absent defaults to pure white `(255, 255, 255)`, malformed fails closed with an error and
  disables only the v2 sub-block. It replaces the removed `ZoneRampConfig.white` key (parsed,
  never consumed) and the v1 `Palette.white` blend knob (every palette shipped `white: 0.0`); both
  legacy `white` keys are now silently ignored wherever they still appear (no allowlist rejection).
- Laser scene `fallback_scene` values must name an existing scene, and `cooldown_beats` must be
  non-negative when present. Legacy `pre_drop_scene` personality keys are ignored, not accepted as
  current schema. `post_drop_cycle_beats` is reserved for future post-drop laser behavior.
- Point/mono palette ranges can collapse slot-color entries 0-4 to one solid RGB for any slot cue; `random_with_mono_chance` can also opt individual looks into probabilistic solid slots 0-4; slot 5 remains reserved pure white.
- SoundSwitch pack-player path precedence is explicit argument, then `RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG`, then `config/soundswitch_pack_player.json`; an absent selected file returns `not_configured`.
- Frozen-bundle home parity (AWR-186 M2): `usb_launcher --run-bridge` points each subsystem's existing env seam (`RBSS_LASER_CONFIG`, `RBSS_LED_CONFIG`, `RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG`, new `RBSS_LASER_COLOR_MAP_CONFIG`) at the installed App Support copy when one exists — precedence explicit operator env > App Support copy > default. The `color_engine.v2.store_path` default (`local/state/led_identity_v2.json`) resolves through `launch_profile.resolve_state_path` to the App Support `state/` dir in frozen runs only; source runs are byte-identical.
- Pack-player config defaults are `enabled=false`, `dry_run=true`, and `output_backend=none`. Supported configured backends are `none`, `midi`, and `pack`; runtime command switching to `midi` remains deliberately unsupported. Pack enable/reload/backend actions are explicit and validate-first.
- The ignored local pack config was absent in the 2026-06-23 audit. No pack/Enttec live setup is therefore claimed.
- `fixture_map` must define exactly CH1 through CH19 with unique integer DMX addresses 1 through 512. A non-empty `fixture_map_path` is authoritative over the inline map and resolves relative to the containing config file unless absolute.
- Pack-player timeouts must be positive integers. Paths and the Enttec port field must be strings. `midi_input_aliases` is optional; when present it maps non-empty saved static-controller device identities to non-empty local port-alias strings and overrides the default device-name auto-bind.
- Invalid JSON, unknown keys, duplicate JSON keys, duplicate fixture channels after integer coercion, invalid map files, and invalid field types fail closed as `invalid_config`; the loader never raises.

Tests:
- inspect `tests/` for laser config and LED config tests
- run config-specific tests when schema changes
- `tests/test_color_engine_config.py` covers LED color-engine slot-fill strategy defaults, accepted values, mono-chance parsing, locked-palette parsing, palette-control binding parsing, and invalid-value rejection.
- `tests/test_led_config.py` covers the LED `scripted_mode` blackout defaults, accepted `utility` destinations and partial maps, and invalid role/schema rejection.
- `tests/test_led_config.py` (`BlankRoleHoldConfigTests`, AWR-157) covers `blank_role_hold`
  absent-defaults-true, explicit true/false parsing, non-boolean rejection, and that the shipped
  example config still loads with the new field.
- `tests/test_soundswitch_pack_player_config.py` covers T7a defaults, path precedence, inline/external fixture maps, strict validation, immutability, and the never-raising contract.
- `tests/test_laser_config.py` and `tests/test_laser_config_deprecation.py` cover Laser Audit P4
  scene fallback/cooldown validation and deprecated `pre_drop_scene` load compatibility.

Change contract:
- If schema changes, update loaders, example configs, setup docs, feature/status matrices, and tests.
- Never commit secrets, local device IPs, local API keys, or backup files.

Known risks:
- schema docs drifting from validators
- local config copied into repo
- examples claiming live readiness without validation evidence
