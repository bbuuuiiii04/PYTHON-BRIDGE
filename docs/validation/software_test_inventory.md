---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 944bc83
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
| Core bridge | state manager, models, smart phrasing, integration tests | verifies software behavior only |
| Runtime commands | parser/handler/status writer tests | needed before command changes |
| Logging visibility | bridge formatting/rate helpers and logging diagnostic coverage tests | verifies software-only log filtering and spam-control behavior |
| Rekordbox readers | reader, offset, live BPM, active-deck resolver, StateManager authority, startup wiring, runtime status tests | cannot prove all app versions or hardware-visible behavior |
| SoundSwitch | OS2L/output helpers; project/pack/player/native-Autoloop-resolver/MIDI/backend/Enttec/config/startup/controller/commands/StateManager/status/menubar/shadow/Art-Net truth-check/T7d/parity-lane tests | pack coverage is pinned to SoundSwitch 2.10.3 canonical UUID/RAVE; copied status, native Autoloop rendering, U1 truth-check packets, and passive U0 parity fixtures are software/wire evidence and tests do not prove physical fixtures |
| Laser | laser config/director/executor/MIDI dry-run tests | cannot prove physical safety |
| LED/Govee | LED config/director/color/realtime/renderer tests plus StateManager LED automation tests | cannot prove device compatibility or room-visible behavior |
| Replay/session tooling | replay format and smoke tests | software-only |
| Frontend tools | syntax and smoke tests | does not prove live safety |
| Docs/agent workflow | docs metadata, agent contract, and drift checkers | docs-only validation |

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
track replacement, missing-phrase-data indefinite hold until a crossing,
inactive-deck load exclusion, idle/stop cleanup, and no director/adapter or
laser/SoundSwitch calls during the hold return.

This is software validation only. It does not prove Govee device behavior or
the room-visible absence of a mid-phrase pop.

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

All M2.5 slot cue, strategy, Locked Palette, and renderer-param tests: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Runtime Status Heartbeat

`tests/test_runtime_status.py` covers the status JSON `heartbeat` payload, the throttled `[BEAT]`
log line and immediate repeat suppression, show-deck versus Rekordbox-master separation,
StateManager-published color-engine status, fail-soft provider behavior, and throttling for
repeated provider-failure warnings. This is software-only observability coverage and does not
validate SoundSwitch, laser, LED, Govee, or Rekordbox hardware behavior.

## Logging Visibility

`tests/test_bridge_fmt_rate.py` covers `log_changed()` and `log_throttled()` spam-control behavior,
including a threaded independent-key throttle check. `tests/test_logging_diag_coverage.py` covers
laser/LED/Govee debug coverage and the `docs/setup/logging_live_watch.json` preset, including
`runtime_status` heartbeat visibility and error pass-through. This is software-only observability
coverage and does not validate physical outputs.
