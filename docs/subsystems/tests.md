---
doc_status: current
truth_level: code-verified
last_verified_commit: fe51608
last_verified_date: 2026-07-03
validation_scope: software-only
---

# Tests

Status:
- implementation: partial
- software-tested: partial
- hardware-validated: no
- compatibility: local test environment only

Purpose:
- Route agents to relevant tests without making them inspect the entire suite first.

Authoritative locations:
- `tests/`
- `requirements-dev.txt`
- `pyproject.toml`

Common commands:
- `python -m unittest discover tests`
- `python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q` when pytest is available and relevant
- `node --check tools/laser_pad_assets/pad-state.js tools/laser_pad_assets/pad-selectors.js tools/laser_pad_assets/pad-actions.js tools/laser_pad_assets/pad-ui.js` when touching Laser Pad frontend assets

Coverage expectations:
- Core/state changes need state manager or integration tests.
- Runtime command changes need parser/handler tests.
- Runtime status heartbeat changes need `tests/test_runtime_status.py` coverage for payload shape,
  log formatting, throttling seam, show-deck versus Rekordbox-master separation,
  StateManager-published color status, and fail-soft provider behavior.
- Rekordbox mixer active-deck authority changes need `tests/test_rb_offsets.py`,
  `tests/test_rb_state_reader.py`, `tests/test_active_deck_resolver.py`,
  `tests/test_state_manager_active_deck_authority.py`,
  `tests/test_main_mixer_authority_wiring.py`, and `tests/test_runtime_status.py`
  coverage for offset fail-closed behavior, finite mixer reads and invalid
  reasons, direct-master refresh/invalidation, raw Deck C/D no-aliasing, lost
  transport fail-closed pause, resolver policy, StateManager bypass gates,
  default-on startup wiring, heartbeat/status stale-master separation, and
  deck-0 idle clear safety.
- Logging visibility changes need `tests/test_bridge_fmt_rate.py` for spam-control primitives and
  `tests/test_logging_diag_coverage.py` for diagnostic coverage and the live-watch preset.
- Docs/agent workflow changes need `tests/test_docs_orphan_check.py` for active-doc
  classification and `tests/test_check_docs_staleness.py` for advisory staleness
  contract parsing, glob expansion, and implementation-file filtering.
- Config schema changes need validation tests.
- LED/Govee rendering changes need deterministic renderer/runner tests where practical.
- Laser changes need config/executor/director tests.
- `tests/test_soundswitch_project_decoder.py` covers the strict decoder/frozen models, including typed truncated-catalog failures. `tests/test_soundswitch_pack.py` covers deterministic export, independent verification, dynamic saved-project inventory reconciliation, proof-only strict snapshot rejection, the seven-class F-3 crosswalk, canonical note-to-Autoloop bindings, loader-superset runtime metadata rejections, report-only import diagnostics, byte-identical repeat export, source sidecar ignored-path derivation/sanitization, active/inactive parity-lane summaries, registry loading, and mutation rejection. `tests/test_build_parity_fixture.py`, `tests/test_soundswitch_parity_oracle.py`, `tests/test_soundswitch_scripted_parity.py`, and `tests/test_static_looks.py` cover passive capture fixture seams, U0 oracle classifications, registry freshness/generalization, zero-seeded Autoloop-cycle replay, and the Static Look unavailable-window/C6 assertion fallback. F9 and F10 proof seams remain covered. Config/startup/controller/commands, StateManager driver, player, native Autoloop resolver, MIDI input, frame sender, Enttec, shadow, Art-Net truth-check, and T7d tooling have focused suites. StateManager pack-driver tests cover ordinary `_run` drain/tick/snapshot/profiler exceptions, preserved 200 Hz throttle sleeps, bounded loop-error logs, no duplicate pack ZERO after `_push_tick()` inner failures, and `KeyboardInterrupt`/`SystemExit` escape. Native Autoloop tests cover latching, executor-latched no-edge seeding, phase/refire/re-anchor, missing binding/file/layout, all-zero dark looks, post-drop fallback/mapped behavior, scripted/static/SoundSwitch-present precedence, reload stale clearing, and the single submit path. MIDI/startup tests cover python-rtmidi `MidiIn`, static-controller auto-bind, explicit alias override, ambiguous/missing controller degradation, output-bus exclusion, and blackout hold/release behavior. RW-5 adds falsifiable coverage for provider-free copied status, state precedence/simultaneous truths, fresh-dict publication, lifecycle snapshots, render/submit failure sanitization, stale menubar handling, export phases, and the unchanged reload command. Art-Net truth-check tests cover pure ArtDMX building, env gating, fake sidecar/socket emission, sequence wrap, queue overflow, Enttec-free startup, connected shadow render with production zero, and `tools/artnet_compare.py --self-check`. These remain software/wire tests and do not prove physical fixtures.

Change contract:
- Do not modify tests just to make docs changes pass.
- If tests cannot run due local environment or optional dependencies, report that explicitly.
- Hardware behavior requires validation logs/checklists, not only unit tests.

M2.5 LED slot-color workstream adds patch-specific tests through `tests/test_led_color_engine_m2_patch_f.py`.
Focused M2.5 subsets should include the color config test, `tests/test_led_color_engine.py`, the phase tests, and every existing `tests/test_led_color_engine_m2_patch_*.py` file.

Known risks:
- tests proving software behavior but not actual hardware behavior
- optional pytest/unittest mismatch
- local dependency gaps
