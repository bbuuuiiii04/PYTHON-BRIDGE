---
doc_status: current
truth_level: code-verified
last_verified_commit: b629b93
last_verified_date: 2026-07-13
validation_scope: software-only; RB7216 patch/menu/builder/install hardening, immediate grey initial-check repaint, AppleDouble pruning and final mounted-DMG validation ordering, and AWR-207 split-local-UUID classifier regression coverage added 2026-07-13; no physical foreign-Mac, bridge, or hardware action
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
- USB builder changes need `tests/test_make_stick.py`; final package work must
  cover AppleDouble metadata removal before manifest creation and keep the
  mounted-DMG signature/installer validation ordered before publication. Unit
  tests also prove the outer FAT manifest ignores mutable transport companions.
  They do not invoke `hdiutil`, so a real build remains the final image proof.
- Smart-drop/breakdown runtime-command rejection handling is covered in `tests/test_runtime_status.py`
  by callbacks returning `False`, matching the queue-full path in `__main__.py`.
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
- Logging visibility changes need `tests/test_bridge_fmt_rate.py` for spam-control primitives,
  `tests/test_bridge_log.py` for the JSONL record/queue/writer pipeline, `tests/test_bridge_view.py`
  for the pure viewer layer (`parse_record`/`lens_of`/`format_line`/`LatchState`),
  `tests/test_logging_surface.py` for error-visibility/env-var diagnostic coverage, and
  `tests/test_bridge_log_integration.py` for the subprocess init→emit→shutdown round trip. New
  `perf.*`/`health.*` emit sites need one capture-handler assertion in the test module that already
  owns that behavior (see `docs/validation/software_test_inventory.md`'s Logging Visibility
  section), not a new logging test file.
- Docs/agent workflow changes need `tests/test_docs_orphan_check.py` for active-doc
  classification and `tests/test_check_docs_staleness.py` for advisory staleness
  contract parsing, glob expansion, and implementation-file filtering.
- Spectral ear-benchmark (offline tooling) changes need `tests/test_spectral_ear_benchmark.py`
  (AWR-200, 32 tests): row taxonomy, explicit exclusions with reasons, the real fold invariant
  (no entry id / resolved amendment lineage in both train and test), amendment grouping through
  the `amends` parent link with loud missing/cyclic/ambiguous/duplicate-id warnings, the `call_planner`
  boundary rejecting forbidden/unexpected fields, accuracy axes staying UNAVAILABLE (never
  zero/PASS) with the marker axis gated on markers actually scored AND at least one comparable
  ±1/±2 perturbation (baseline decisions with both flip rates None read UNAVAILABLE), per-radius
  comparable denominators for marker sensitivity, same-title/no-content_id identity warnings,
  deterministic output, and marker-sensitivity flip counting against a synthetic planner seam.
  Stdlib-only tests; no real cache/DB/planner.
- Offline intrinsic-hardness (`hardness_v0.py` + `tools/hardness_ablation.py`, AWR-203) changes
  need `tests/test_hardness_v0.py` (28 tests): B/A/R/N term math + clipping, first-8/following-8
  per-term averaging and short/end-of-track boundaries, deterministic reducer selection +
  tie-breaking, three-path math + winning-path diagnostics, per-term track median +
  MIN_STABLE_DROPS, marker-shift range, malformed/empty/non-finite (NaN/±inf)/unshaped inputs
  returning no result (never a phantom T3), and the AST-based zero-runtime-importer invariant (only `tools/`+`tests/` may
  import the offline module). Stdlib-only; duck-typed synthetics + one real `SpectralFeaturesV4`
  fixture, no cache/DB.
- Offline raw approach descriptors (`approach_features_v0.py`, AWR-204) changes need
  `tests/test_approach_features_v0.py` (27 tests): rising/falling/held trajectories (slope + delta
  sign), ringing-layer-independent-of-sub-cut (no min-masking), broad-vs-single-band and
  approach-floor (p10-not-p50) depth, section-relative depth, separate first-8/next-8 landed windows,
  track baseline + across-`genuine_drops` landing reference (incl. no-drops → None and empty-drops →
  zero-ref), the track-referenced void run curve + the `longest_run_below` primitive (a hole breaks
  the run), the ±2 offset bundles (slides for a length window, end-only for an explicit start,
  offset-0 == primary, `descriptor_range` stability), boundary clamp (requested vs available),
  short-window insufficiency (no slope), window `sufficient` requiring finite data not just beat
  slots (all-non-finite/single-finite → `sufficient=False` with a distinct reason), missing series →
  `present=False`, non-finite filtered + counted, top-level availability requiring ≥1 finite approach descriptor (all-non-finite/missing →
  `available=False` + honest reason), empty track unavailable-not-error, inconsistent caller inputs
  raising, determinism, and
  the AST+text zero-runtime-importer invariant. Stdlib-only; duck-typed synthetics, no cache/DB.
- Config schema changes need validation tests.
- LED/Govee rendering changes need deterministic renderer/runner tests where practical.
- Laser changes need config/executor/director tests.
- `tests/test_soundswitch_project_decoder.py` covers the strict decoder/frozen models, including typed truncated-catalog failures. `tests/test_soundswitch_pack.py` covers deterministic export, independent verification, dynamic saved-project inventory reconciliation, proof-only strict snapshot rejection, the seven-class F-3 crosswalk, canonical note-to-Autoloop bindings, loader-superset runtime metadata rejections, report-only import diagnostics, byte-identical repeat export, source sidecar ignored-path derivation/sanitization, active/inactive parity-lane summaries, registry loading, and mutation rejection. `tests/test_build_parity_fixture.py`, `tests/test_soundswitch_parity_oracle.py`, `tests/test_soundswitch_scripted_parity.py`, and `tests/test_static_looks.py` cover passive capture fixture seams, U0 oracle classifications, registry freshness/generalization, zero-seeded Autoloop-cycle replay, and the Static Look unavailable-window/C6 assertion fallback. `tests/test_export_pack_parity_self_heal.py` covers the export-time parity self-heal; its fixtures-absent fallback asserts the structural fail-closed invariant (every document `unverified_parity` on venue-sha mismatch, trusted lanes on match — count derived from the staged pack) rather than a hard-coded lane split, so it stays green as the operator's live venue sha drifts. F9 and F10 proof seams remain covered. Config/startup/controller/commands, StateManager driver, player, native Autoloop resolver, MIDI input, frame sender, Enttec, shadow, Art-Net truth-check, and T7d tooling have focused suites. StateManager pack-driver tests cover ordinary `_run` drain/tick/snapshot/profiler exceptions, preserved 200 Hz throttle sleeps, bounded loop-error logs, no duplicate pack ZERO after `_push_tick()` inner failures, and `KeyboardInterrupt`/`SystemExit` escape. Native Autoloop tests cover latching, executor-latched no-edge seeding, phase/refire/re-anchor, missing binding/file/layout, all-zero dark looks, post-drop fallback/mapped behavior, scripted/static/SoundSwitch-present precedence, reload stale clearing, and the single submit path. MIDI/startup tests cover python-rtmidi `MidiIn`, static-controller auto-bind, explicit alias override, ambiguous/missing controller degradation, output-bus exclusion, and blackout hold/release behavior. RW-5 adds falsifiable coverage for provider-free copied status, state precedence/simultaneous truths, fresh-dict publication, lifecycle snapshots, render/submit failure sanitization, stale menubar handling, export phases, and the unchanged reload command. Art-Net truth-check tests cover pure ArtDMX building, env gating, fake sidecar/socket emission, sequence wrap, queue overflow, Enttec-free startup, connected shadow render with production zero, and `tools/artnet_compare.py --self-check`. These remain software/wire tests and do not prove physical fixtures.
- Audit P2 adds `tests/test_state_manager_pack_driver.py` coverage for SoundSwitch-connected ZERO
  output with `soundswitch_pack.overlay_suppressed.static_held`, and
  `tests/test_led_look_director.py` coverage for committed-drop DIY eligibility filtering.
- Audit P3 adds `tests/test_govee_realtime_runner.py` coverage for runner-thread handoff teardown,
  `tests/test_rb_state_reader.py` coverage for transient ANLZ read-failure recovery, and
  `tests/test_sound_switch_engine.py` coverage for explicit scripted elapsed threading.
- Audit P4 adds `tests/test_midi_output.py` send-error reopen recovery coverage,
  `tests/test_laser_executor.py` high-impact/missing bank restore and blackout-mask refcount
  coverage, `tests/test_laser_config.py` fallback/cooldown validation coverage,
  `tests/test_laser_config_deprecation.py` `pre_drop_scene` tolerance coverage, and
  `tests/test_laser_pad_web.py` live-toggle command append/error coverage.

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
