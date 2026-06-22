---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: b7e0e66
last_verified_date: 2026-06-21
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Software Test Inventory

This inventory routes agents to tests without pretending software tests validate physical lighting hardware.

## Broad command

```bash
python -m unittest discover tests
```

If using pytest-specific tests or fixtures:

```bash
python -m pytest tests
```

## Subsystem routing

| Area | What to look for in `tests/` | Notes |
| --- | --- | --- |
| Core bridge | state manager, models, smart phrasing, integration tests | verifies software behavior only |
| Runtime commands | parser/handler/status writer tests | needed before command changes |
| Logging visibility | bridge formatting/rate helpers and logging diagnostic coverage tests | verifies software-only log filtering and spam-control behavior |
| Rekordbox readers | reader, offset, live BPM tests | cannot prove all app versions |
| SoundSwitch | OS2L/output helpers; project/pack/player/MIDI/backend/Enttec tests; `test_soundswitch_pack_player_config.py` | pack coverage is pinned to SoundSwitch 2.10.3 canonical UUID/RAVE; T7a config tests do not prove runtime wiring or hardware |
| Laser | laser config/director/executor/MIDI dry-run tests | cannot prove physical safety |
| LED/Govee | LED config/director/color/realtime/renderer tests | cannot prove device compatibility |
| Replay/session tooling | replay format and smoke tests | software-only |
| Frontend tools | syntax and smoke tests | does not prove live safety |
| Docs/agent workflow | docs metadata, agent contract, and drift checkers | docs-only validation |

## Required documentation update

When adding or changing tests, update:

- `docs/status/validation_matrix.md`
- `docs/subsystems/tests.md`

## SoundSwitch Offline Decode And Export Tasks 1–2

`tests/test_soundswitch_project_decoder.py` covers frozen source-model use and strict, read-only decoding: physical document bounds/trailers, venue/static-look parsing, canonical identity and stable inventory gates, learned MIDI/control reconciliation, catalog/script classification, malformed and unsupported-source rejection, and the 232 render-cue plus one catalog-tail split. When the canonical local project is available, the current-corpus test also verifies its expected decoded counts and classifications.

`tests/test_soundswitch_pack.py` covers deterministic export, the canonical 95-artifact pack, independent verification, exact 232+1/32/42/45 inventory, byte-identical repeat export, atomic publish, source/inventory/hash/canonicalization/semantic mutation rejection, and the seven-class F-3 crosswalk. `tests/test_prove_soundswitch_pack_generation.py` covers the proof-gate seams. The current proof result is 29 PASS / 0 FAIL / 0 INCOMPLETE with foundation 27/27 PASS; F9 and F10 pass.

`tests/test_shadow_soundswitch_pack.py` (Task 8 offline shadow proof) drives a synthetic verified `LaserPackPlayer` through scripted/static/blackout transitions with the physical backend forced to `none` (`tools/shadow_soundswitch_pack.py`), recording ONLY frame SHA-256 hashes and comparing each against an independently hand-computed expected frame. It proves stop/blackout/emergency/reload-wait resolve to a zero frame, that a held Static Override stands alone over a cleared base, twice-run hash determinism, report sanitization (no raw frames/paths/identities), backend-`none` enforcement (a frame sender is rejected), slots 8/16/17/24 plus a controlled slot-7 create/edit, and that the removed non-functional `--project` option is rejected. Pure explicit-`phase_tick` autoloop rendering is covered by `tests/test_soundswitch_laser_player.py`; only runtime beat-to-phase shadow coverage remains reported `deferred_t7d_phase_origin`. Software/offline only — no hardware claim.

This is software validation only. Separate focused suites cover the immutable pack loader/player, MIDI adapter, backend abstraction, Enttec framing/sender, and the T7a pack-player config loader. T7a config tests exercise defaults, explicit/env/default path precedence, inline and external fixture maps, invalid schemas, and never-raising failure results. They do not test startup/`StateManager`/commands/status integration, open devices, prove Enttec hardware behavior, or validate physical fixtures.
- relevant subsystem card
- relevant task playbook if test workflow changed

Hardware behavior still needs manual validation logs.

## M2.5 LED slot-color workstream test files

| File | Covers | Added in |
|---|---|---|
| tests/test_led_color_engine_m2_phase1.py | Phase 2a/b engine cues, renderer byte-identity, resolve_slot_colors | Phase 1 |
| tests/test_led_color_engine_m2_patch_b.py | rt_groove_chase slotization | Patch B |
| tests/test_led_color_engine_m2_patch_c.py | rt_post_drop_chase slotization | Patch C |
| tests/test_led_color_engine_m2_patch_d.py | rt_drop_chase, rt_drop_center_burst slotization | Patch D |
| tests/test_led_color_engine_m2_patch_e1.py | rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula slot fns plus rt_drop_nebula pairing | Patch E1 |
| tests/test_led_color_engine_m2_patch_e2.py | rt_post_drop_center_comet slot fn, rt_drop_center_burst pairing, legacy center-comet regression, solid slot-color selection for slot cues | Patch E2 |
| tests/test_led_color_engine_m2_patch_e3.py | rt_twinkle slot fn, generic ambient config, legacy twinkle_blue regression, solid slot-color selection for rt_twinkle | Patch E3 |
| tests/test_led_color_engine_m2_patch_s.py | random_with_mono_chance mono hit/miss behavior, chance 0 equality with random_with_replacement, determinism, stepping, fade tail, journey RNG isolation, allowlist regression | Patch S |
| tests/test_led_color_engine_m2_patch_f.py | Patch F default-bank cleanup, legacy_color_suffix storage bank, scene_ref registration, generic drop pairing, no static slot_colors params, solid reachability through default generics | Patch F |

All M2.5 slot cue and strategy tests: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Runtime Status Heartbeat

`tests/test_runtime_status.py` covers the status JSON `heartbeat` payload, the throttled `[BEAT]`
log line and immediate repeat suppression, StateManager-published color-engine status, fail-soft
provider behavior, and throttling for repeated provider-failure warnings. This is software-only
observability coverage and does not validate SoundSwitch, laser, LED, Govee, or Rekordbox hardware
behavior.

## Logging Visibility

`tests/test_bridge_fmt_rate.py` covers `log_changed()` and `log_throttled()` spam-control behavior,
including a threaded independent-key throttle check. `tests/test_logging_diag_coverage.py` covers
laser/LED/Govee debug coverage and the `docs/setup/logging_live_watch.json` preset, including
`runtime_status` heartbeat visibility and error pass-through. This is software-only observability
coverage and does not validate physical outputs.
