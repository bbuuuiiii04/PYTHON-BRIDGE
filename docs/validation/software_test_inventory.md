---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 56c5f90
last_verified_date: 2026-07-03
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
| Core bridge | state manager, models, smart phrasing, integration tests | verifies software behavior only. Smart-drop selector tests cover cluster collapse, exact-64 raw gaps, intro/outro trimming, and breakdown-selection parity. |
| Runtime commands | parser/handler/status writer tests plus menubar watcher-launch tests and watcher function tests (`tests/test_ss_bridge_watcher.py`: attributable deck stops, bridge-gap respawn) | needed before command changes; menubar/watcher tests do not prove live watcher or bridge process health |
| Logging visibility | `bridge_log`/`bridge_view` pipeline + viewer tests, `bridge_fmt` rate-control tests, and cross-subsystem `perf.*`/`health.*` emit assertions | verifies the JSONL event stream, viewer lens/latch logic, and spam-control behavior only — no lighting-hardware behavior |
| Runtime audit P1 cleanup | `tests/test_runtime_status.py`; compile/docs checks | smart-drop/breakdown queue-full failures surface in command status; dead-code/stale-text cleanup is software-only |
| Rekordbox readers | reader, offset, live BPM, active-deck resolver, StateManager authority, startup wiring, runtime status tests | cannot prove all app versions or hardware-visible behavior. Audit P3 adds ANLZ read-failure cache recovery coverage. |
| SoundSwitch | OS2L/output helpers; project/pack/player/native-Autoloop-resolver/MIDI/backend/Enttec/config/startup/controller/commands/StateManager/status/menubar/shadow/Art-Net truth-check/T7d/parity-lane tests | pack coverage is pinned to SoundSwitch 2.10.3 canonical UUID/RAVE; copied status, native Autoloop rendering, U1 truth-check packets, and passive U0 parity fixtures are software/wire evidence and tests do not prove physical fixtures. Audit P2 adds software coverage for SoundSwitch-connected `overlay_suppressed` status. Audit P3 adds explicit scripted elapsed threading coverage. AWR-135 adds `base_suppressed` status coverage for intentional LED-only drop darkness. |
| Laser | laser config/director/executor/MIDI dry-run tests | cannot prove physical safety. `tests/test_drop_lifecycle.py` covers true smart-drop crossings, the capped chorus-to-chorus second hit, post-cap demotion, per-section reset, single-marker behavior, and LED flat-window parity. Audit P4 adds send-error reopen recovery, bank-gate restore, config fallback/cooldown validation, deprecated `pre_drop_scene` tolerance, blackout-mask refcount, and Laser Pad live-toggle command append coverage. |
| LED/Govee | LED config/director/color/realtime/renderer tests plus StateManager LED automation tests | cannot prove device compatibility or room-visible behavior. `tests/test_led_state_manager.py` covers the mirrored real-crossing drop-impact gate, the capped chorus-to-chorus second hit, post-cap demotion, 32-beat intra-section role-key rotation for long buildup/pre-drop/breakdown/monotonic ambient sections, the bounded active-content hold with hold/reset observability, and no-audible idle ambient dispatch/freewheel cleanup. `tests/test_beat_sync_engine.py` covers the AWR-141 realtime wrap guard: sub-threshold backward jitter holds without wrap/spawn, real loops still wrap, forward crossings stay capped, and continuous effects do not replace their instance on jitter. `tests/test_govee_realtime_runner.py` covers idle-grace blackout-before-deactivate ordering. `tests/test_govee_runtime_sender.py` covers mirror-send health transition logging and status; `tests/test_govee_scene_adapter.py` covers circuit-open degraded-state healing. `tests/test_led_color_engine_integration.py` covers stable section/cycle publication, unchanged drop/groove/post_drop key strings, and a dispatch-path second look across a buildup cycle boundary. Audit P2 adds committed-drop DIY eligibility coverage. Audit P3 adds runner-thread realtime handoff teardown coverage. Audit P5 keeps existing LED state-manager coverage as the behavior oracle for dispatch bookkeeping extraction. AWR-142 adds no new test: it appends `transport=`/`runway_beats=` to the accepted smart-drop-blackout log lines (observability only), and the repo does not unit-test log text, so correctness is "no behavior change" covered by the existing LED suite staying green. AWR-144 adds `LEDSoloPredarkHoldTests` (4 cases) in `tests/test_led_state_manager.py`: a pending `lasers_only` drop suppresses the LED drop look and reports the `solo_predark_hold` gate reason, a `leds_plus_lasers` drop still dispatches its drop look, drop-presentation disabled (`(None, "", None)`) is a byte-identical no-op, and a set `drop_spotlight` blackout owner still masks via the pre-existing `emergency_blackout` gate. AWR-146 adds `tests/test_govee_frame_engine.py` (host + client, 14 pure cases: init/deactivate ordering, anchor staleness, list-param render parity, command fan-out, AWR-145-through-the-boundary brightness/activate/keepalive, EOF/shutdown teardown, heartbeat fps + degraded edge-trigger, `decode_buffer` framing, no-caller-thread-I/O + wire order, respawn intent replay, hung/stuck respawn, emergency queue-jump, status merge, stop escalation) and `tests/test_govee_frame_engine_integration.py` (real subprocess: 60.9 fps this machine, orphan-EOF exit-0; timing-sensitive, skipped under `CI=true`). Task 6 adds a coordinator `blackout_brightness()` test, a StateManager accepted/cloud-only-no-op/rejected blackout-dim test, and a runner inactive-`request_brightness(0)`-reaches-transport-twice test. These prove IPC framing, supervision, and the moved-runner parity in software only — not room-visible smoothness or device behavior. AWR-149 adds `LEDLookDirectorPlanRotationTests` in `tests/test_led_look_director.py`: `plan_backend_sequence()` exact tuples (frozen 6RT+2cloud spacing, 1+1 realtime-first, 3+3 realtime-leads-tie, single-backend, empty, order stability), seed-independent 12-pick backend sequences, the no-latch groove regression, plan-index-0 session phase across seeds, eligibility rebase plus C4 full-bank fallback, preview parity with no cursor/bag/RNG mutation, and paired-post_drop plan bypass. These prove the deterministic transport selection in software only. |
| Replay/session tooling | replay format and smoke tests | software-only |
| Frontend tools | syntax and smoke tests | does not prove live safety |
| Docs/agent workflow | docs metadata, agent contract, drift, and staleness checkers | docs-only validation |

## Required documentation update

When adding or changing tests, update:

- `docs/status/validation_matrix.md`
- `docs/subsystems/tests.md`

## SoundSwitch Offline Decode And Export Tasks 1–2

`tests/test_soundswitch_project_decoder.py` covers frozen source-model use and strict, read-only decoding: physical document bounds/trailers, venue/static-look parsing, canonical identity and stable inventory gates, learned MIDI/control reconciliation, catalog/script classification, malformed and unsupported-source rejection, render-vs-catalog-tail semantics, and at least one render-bearing cue. When the canonical local project is available, the current-corpus test also verifies decoded classifications.

`tests/test_soundswitch_pack.py` covers deterministic export, independent verification, dynamic saved-project inventory reconciliation, proof-only strict snapshot rejection, byte-identical repeat export, atomic publish, source sidecar ignored-path derivation/sanitization, source/inventory/hash/canonicalization/semantic mutation rejection, the seven-class F-3 crosswalk, loader-superset runtime metadata rejections, report-only import diagnostics, active/inactive parity-lane scoping, and export threading of scripted/Autoloop/Static Look parity registries. `tests/test_soundswitch_project_decoder.py` covers typed truncated-catalog rejection. `tests/test_prove_soundswitch_pack_generation.py` covers the proof-gate seams, including F9, F10, and structural Static Look frame validation without pinning operator recolours.

`tests/test_shadow_soundswitch_pack.py` (Task 8 offline shadow proof) drives a synthetic verified `LaserPackPlayer` through scripted/static/blackout transitions with the physical backend forced to `none` (`tools/shadow_soundswitch_pack.py`), recording ONLY frame SHA-256 hashes and comparing each against an independently hand-computed expected frame. It proves stop/blackout/emergency/reload-wait resolve to a zero frame, that a held Static Override stands alone over a cleared base, twice-run hash determinism, report sanitization (no raw frames/paths/identities), backend-`none` enforcement (a frame sender is rejected), slots 8/16/17/24 plus a controlled slot-7 create/edit, and that the removed non-functional `--project` option is rejected. Pure explicit-`phase_tick` autoloop rendering is covered by `tests/test_soundswitch_laser_player.py`; only runtime beat-to-phase shadow coverage remains reported `deferred_t7d_phase_origin`. Software/offline only — no hardware claim.

This is software validation only. Separate focused suites cover the immutable
pack loader/player, native Autoloop resolver, MIDI adapter, backend abstraction,
Enttec framing/sender, pack-player config, startup matrix, atomic controller,
runtime commands/status, StateManager driver, and menubar. Native Autoloop tests
cover note-to-Autoloop binding/display names, 600 ticks/beat phase, latching,
same-look refire and role re-anchor, missing binding/file/layout, all-zero dark
looks, post-drop fallback and mapped post-drop behavior,
scripted/static/SoundSwitch-present precedence, reload stale clearing, and the
single submit path. MIDI/startup tests cover static-controller auto-bind, alias
override, missing/ambiguous controller degradation, and output-bus exclusion.
RW-5 tests fail on backend/provider re-query,
published-dict mutation/reuse, incorrect precedence or simultaneous truths,
unsafe lifecycle snapshots, raw render/submit errors, 200 Hz loop error death,
missing throttle sleeps, duplicate ZERO submits after `_push_tick()` inner failures,
process-control exception swallowing, blackout self-release drift, stale active UI, export phase races,
reload-command drift, missed one-shot auto-enable retry, or
private-data leaks. The tests use fake/
injected hardware seams. They do not prove Enttec/fixture behavior.

The 2026-07-02 parity-finalization fixes add: idle manual-overlay driver tests
(`PackDriverIdleManualOverlayTests`) proving static press/release and blackout
stay operator-controlled at `active_deck` 0 with truthful status/truth-intent;
a playing-scrub latch test (`PackDriverScrubLatchTests`) proving a waveform
drag holds the automatic base dark and resumes after settling; playing-sibling
load-guard tests (`PlayingSiblingLoadGuardTests`) proving an idle-sibling
`TRACK_LOADED`/`ANLZ_PATH` cannot clobber a playing deck while owner loads and
fail-open cases still pass (all in `tests/test_state_manager_pack_driver.py`);
and selection-beat anchor tests in `tests/test_native_autoloop_resolver.py`
(mid-grid trigger anchors phase 0 at the selection beat, negative-beat clamp,
plus the corrected latch/non-32-cycle expectations).

Art-Net truth-check tests add `tests/test_artnet_truth.py`,
`tests/test_artnet_compare.py`, startup coverage in
`tests/test_soundswitch_pack_startup.py`, and connected-shadow coverage in
`tests/test_state_manager_pack_driver.py`. `python3 tools/artnet_compare.py
--self-check` is the non-network validator measurement test; it uses synthetic
traces only. The comparator now fails closed on stale/missing/unmatched sidecar
rows, sequence wrap, unmatched sidecar frames, and U1 packets missing sidecar
evidence. It allows denser U1 streams only through ordered nearest-neighbor
matches, and extra U1 rows never satisfy coverage. In live streaming mode it
reconciles only a settled prefix — deferring the newest frames and tolerating
the sidecar (written before send) leading received U1 — so a denser/leading
stream is pending rather than a setup error, while a genuine byte mismatch on a
settled frame still fails. Its coverage ledger includes
normalized scripted timeline events/rapid pairs, matched Autoloop
visible/authored-dark phase buckets based on each loop's cycle, static and
blackout overlay/release combinations, and active-deck/mode transition
directions.

Parity evidence tests add `tests/test_build_parity_fixture.py`,
`tests/test_soundswitch_parity_oracle.py`,
`tests/test_soundswitch_scripted_parity.py`, and `tests/test_static_looks.py`.
They cover ordered capture joins, scripted divergence ledgers, Autoloop sample
classification, zero-seeded Autoloop-cycle replay, static unavailable-window
fixture generation, registry hash freshness, same-layout generalization,
active/inactive lane summaries, and static non-generic assertion fallback.
`tests/test_witness_auto_retire.py` covers edited-witness evidence retirement,
including doc-sha retirement, identical-sha regression pinning, synthetic
publish fallback to `algorithm_generalized`, and unchanged-source publish
blocking through `UnverifiedParityPublishError`.
These are passive capture/software
oracle tests only; remaining active `unverified_parity` documents block trusted
publication.
- relevant subsystem card
- relevant task playbook if test workflow changed

Hardware behavior still needs manual validation logs.

## Docs / Agent Workflow

`tests/test_docs_orphan_check.py` covers active-doc classification matching for
`tools/check_agent_contracts.py`. `tests/test_check_docs_staleness.py` covers
`tools/check_docs_staleness.py` contract parsing, recursive glob expansion,
contract-globbed tooling under `tools/`, literal/star glob behavior, and the
`docs/data/*.yaml` implementation-data exception.

## Rekordbox Mixer Active-Deck Authority

The active-deck authority implementation is covered by focused software tests:

- `tests/test_rb_offsets.py` covers named optional mixer offset parsing, exact
  labels, duplicate/malformed/partial required label fail-closed behavior, and
  unknown/anonymous trailing line rejection for authority.
- `tests/test_rb_state_reader.py` covers finite range-checked mixer f32 reads,
  valid endpoints, concrete invalid reasons, direct-master refresh and
  invalidation, raw Deck C/D no-aliasing, transport-unavailable fail-closed
  pause, immutable mixer snapshots, and default resolver-support event emission.
- `tests/test_active_deck_resolver.py` covers fader eligibility, top-fader
  dominance, LOW/BASS dominance and tie cases, rb-master tie/fallback,
  neutral-labeled LOW/BASS tie behavior, Deck 1/2-only candidate filtering,
  invalid/stale mixer fallback, recovery, no-audible idle behavior, and
  stability/no-flicker policy.
- `tests/test_state_manager_active_deck_authority.py` covers StateManager
  integration, `rb_master_deck` separation, MASTER/OSC/mirror/resume bypass
  gates, invalid-to-valid recovery, invalid/stale master handling, lost
  transport fail-closed behavior, immutable snapshot ownership, and deck-0
  idle clear safety.
- `tests/test_main_mixer_authority_wiring.py` covers startup default-on mixer
  authority, raw Deck A/B direct seed, raw Deck C/D fallback/no-aliasing, and
  required `RBStateReader.authoritative_kinds` when old direct flags are
  disabled.
- `tests/test_runtime_status.py` covers show-deck versus Rekordbox-master
  heartbeat/status separation, stale-master suppression, and mixer authority
  visibility.

This is software validation only. It does not validate live Rekordbox behavior,
loaded-track play/stop survival, SoundSwitch, laser, LED/Govee, DMX, MIDI,
Enttec, or hardware-visible output.

## LED Phrase-Aware Active-Content Hold

`tests/test_led_state_manager.py` covers the StateManager-only LED hold that is
armed by nonzero active-deck switches and active-deck track loads. The focused
tests cover immediate release within `0.5` and `1.0` beats of the incoming
phrase entry, hold at `1.1` beats until the next phrase marker, same-active-deck
track replacement, missing-phrase-data release at the 16-beat backstop,
8-second release when no beat is readable, inactive-deck load exclusion,
idle/stop cleanup, hold stamp cleanup, SmartPhrasing reset-reason change
logging, automation-only `perf.led.look` beat/phrase enrichment, and no
director/adapter or laser/SoundSwitch calls during the hold return.

This is software validation only. It does not prove Govee device behavior or
the room-visible absence of a mid-phrase pop.

## LED Idle/Pause Ambient

`tests/test_led_state_manager.py` covers no-audible idle entry dispatching one
ambient decision from the last audible deck, accepted realtime ambient decisions
starting a synthetic 120 BPM idle beat anchor, blackout clearing that anchor,
and playing automation returning to the normal realtime beat branch.
`tests/test_govee_realtime_runner.py` covers idle-grace teardown sending
`blackout()` before `deactivate()`.

This is software validation only. It does not prove the Govee firmware fallback
explanation or the room-visible pause behavior.

## Govee Health Reporting

`tests/test_govee_runtime_sender.py` covers mirror target failure and recovery
as edge-triggered log transitions, keeps the sender's primary return value
unchanged, and asserts `mirror_send_ok` in sender status. `tests/test_govee_scene_adapter.py`
covers a three-failure circuit-breaker trip followed by a successful emergency
send clearing `degraded_reason="circuit_open"` and returning status to
non-degraded when no other fault exists.

This is software validation only. It does not prove cloud API behavior,
physical strip behavior, or room-visible output.

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
| tests/test_color_engine_config.py, tests/test_led_color_engine.py, tests/test_govee_frame_renderer.py, tests/test_led_pad_service.py | Locked Palette config/engine/pad playback plus Phase 3 renderer param default parity and changed-value coverage | LED Pad Phase 3 |
| tests/test_led_identity_v2.py, tests/test_led_color_engine.py, tests/test_color_engine_config.py, tests/test_led_palette_control.py, tests/test_runtime_status.py, tests/test_soundswitch_midi_input.py, tests/test_streamdeck_midi.py, tests/test_led_state_manager.py, tests/test_bridge_menubar.py | LIGHTING ENGINE v2 F1 identity helpers/store, v1/v2 engine behavior (incl. v2-off byte-identity + flip-back journey-state golden, abs-beat bloom/palate-reset windows, moments_blocked gating, scripted stand-down), config gates, Stream Deck zone/manual/max-energy control, runtime commands, MIDI bindings, deck layout, identity-event consumer (stale load_gen drop, provisional-to-measured upgrade, writer submit), real-worker v4 cache-hit path, max-energy mutate-only consume, and the temporary menubar engine toggle | AWR-128 F1 incl. Part F fix round |

All M2.5 slot cue, strategy, Locked Palette, and renderer-param tests: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Runtime Status Heartbeat

`tests/test_runtime_status.py` covers the status JSON `heartbeat` payload, the throttled `[BEAT]`
log line and immediate repeat suppression, show-deck versus Rekordbox-master separation,
StateManager-published color-engine status, fail-soft provider behavior, and throttling for
repeated provider-failure warnings. This is software-only observability coverage and does not
validate SoundSwitch, laser, LED, Govee, or Rekordbox hardware behavior.

## Logging Visibility (AWR-125 overhaul)

The retired `logging_manager.py` control-file/env-var-maze pipeline and its
`tests/test_logging_diag_coverage.py` suite are gone, replaced by the one-JSONL-stream design
(`bridge_log.py`) and its `bridge-view` curses viewer (`bridge_view.py`):

- `tests/test_bridge_log.py` (45 tests) covers `build_record()` field order/optional-key
  omission/contextvar pickup/exc formatting, drop-on-full queue behavior, the writer thread's JSONL
  output and stderr WARNING+ mirror, `_redact()` secret masking, `resolve_log_dir()`/`prune_runs()`,
  `event_scope()`/`stamp_trace()` semantics, `TraceQueue` callback passthrough, and idempotent
  `init()`/`shutdown()` header/footer records.
- `tests/test_bridge_view.py` (96 tests) covers the pure viewer layer: `parse_record` (tolerant of
  truncated/malformed lines), `lens_of` (all four lens predicates, including the legacy-infra
  DEBUG-record-routes-to-DEBUG-only case), `format_line`/truncation, `format_age`, filter
  parsing/matching, and `LatchState` latch/clear/ack semantics.
- `tests/test_logging_surface.py` (7 tests, replaces `test_logging_diag_coverage.py`) covers
  errors-always-visible regardless of logger level, `BRIDGE_LOG_LEVELS` parsing, and `BRIDGE_DEBUG`
  behavior against `bridge_log`.
- `tests/test_bridge_log_integration.py` (9 tests) proves a real subprocess init→emit→shutdown round
  trip, with real JSONL read back through the viewer's lens layer.
- `tests/test_bridge_fmt_rate.py` continues to cover `log_changed()`/`log_throttled()` spam-control
  primitives, including a threaded independent-key throttle check.

The new `perf.*`/`health.*` emit sites added one assertion each to the tests already owning that
behavior, rather than to the logging test files above: `tests/test_laser_director.py` (`perf.laser.
scene`, `perf.laser.personality`, `perf.override`), `tests/test_laser_executor.py`
(`perf.laser.fired`), `tests/test_led_color_engine.py` (`perf.led.palette`),
`tests/test_led_state_manager.py` (`perf.led.look`, `perf.override`),
`tests/test_state_manager_active_deck_authority.py` (`perf.deck`), `tests/test_smart_transitions.py`
(`perf.drop`), `tests/test_autoloop_controller.py` / `tests/test_live_bpm_service.py`
(`perf.autoloop`), `tests/test_live_bpm_service.py` / `tests/test_smart_phrasing_integration.py` /
`tests/test_sound_switch_engine.py` (`perf.ss`), `tests/test_sound_switch_engine.py`
(`perf.scripted`, `health.os2l`, `health.queue`), `tests/test_runtime_status.py`
(`perf.heartbeat`), `tests/test_midi_output.py` (`health.midi`), `tests/test_enttec_dmx_pro.py`
(`health.dmx`), `tests/test_govee_scene_adapter.py` (`health.govee.cloud`),
`tests/test_govee_realtime_runner.py` (`health.govee.rt`), `tests/test_rb_state_reader.py`
(`health.rb`, `health.queue`), `tests/test_rb_memory_skip_objc.py` (`health.rb`,
`health.reader`), and `tests/test_state_manager_pack_driver.py` (`health.tick`).
`tests/test_enttec_dmx_pro.py` / `tests/test_midi_output.py` / `tests/test_govee_realtime_runner.py`
also cover `bridge_log.thread_guard()` wrapping those backends' worker-thread run loops.

This is software-only observability coverage: it proves the log pipeline, the viewer's read-side
lens/latch logic, and the watcher's monitor-window launch, and does not validate physical lighting
outputs.
