---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 944bc83
last_verified_date: 2026-07-03
validation_scope: software-validated only plus Rekordbox 7.2.11 passive mixer RE evidence routing; hardware-unvalidated in repo evidence
---

# Validation Matrix

This page separates software tests from hardware validation. They are not the same thing, because reality remains rude.

Current repo-facing status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

## Validation levels

| Level | Meaning |
| --- | --- |
| software-tested | Unit/integration/replay/static tests exist. |
| docs-checkable | Lightweight repo/docs checks can verify routing, metadata, and selected code/doc consistency. |
| operator-local | I have run it locally, but the repo does not contain repeatable validation evidence. |
| hardware-validated | A repeatable hardware validation log exists in `docs/validation/hardware_validation_log.md`. |
| unvalidated | No useful evidence yet. |
| unknown | Not inspected or not enough evidence. |

## Current validation summary

| Area | Software validation | Hardware validation | Notes |
| --- | --- | --- | --- |
| Core runtime/event/state | partial | unvalidated | Tests exist across state snapshots and runtime behavior, but hardware is separate. |
| Runtime command docs | docs-checkable | not applicable | `tools/check_docs_drift.py` checks command docs against `runtime_status.py`. |
| Runtime `[BEAT]` heartbeat | partial | unvalidated | `tests/test_runtime_status.py` covers heartbeat payload/log assembly and suppression, show-deck versus non-stale Rekordbox-master separation, stale-master suppression, idle deck-0 safety, StateManager-published color-engine status, fail-soft provider handling, and throttled provider-failure warnings; no hardware behavior changes are implied. |
| Runtime audit P1 cleanup | software-tested | unvalidated | `tests/test_runtime_status.py` covers smart-drop/breakdown callback failure surfacing. Compile/docs checks cover the confirmed dead-code and stale-text cleanup. |
| Logging visibility live watch | partial | unvalidated | `tests/test_logging_diag_coverage.py` covers preset parseability, heartbeat visibility, module filtering, and error pass-through. `tests/test_bridge_fmt_rate.py` covers throttle/change primitives, including a small threaded throttle check. |
| Agent routing/contracts | docs-checkable | not applicable | `tools/check_agent_contracts.py` checks key routes and referenced files. `tests/test_docs_orphan_check.py` covers active-doc classification, and `tests/test_check_docs_staleness.py` covers advisory staleness contract parsing, glob expansion, and implementation-file filtering. |
| Rekordbox readers | partial | unvalidated | Reader correctness depends on live app/version/permissions. `tests/test_rb_state_reader.py` covers transient ANLZ read failures preserving the last successful cache entry and later recovery emission. |
| Rekordbox mixer active-deck authority | software-tested implementation plus static/passive RE proof for local Rekordbox 7.2.11 Deck 1/2 upfader and LOW/BASS chains | unvalidated | Unit/integration tests cover named offset parsing, finite mixer reads with `unreadable`/`non_finite`/`out_of_range` reasons, immutable mixer snapshots, resolver cases including neutral LOW/BASS tie handling and Deck 1/2-only candidates, StateManager bypass gates, direct-master refresh/invalidation, lost transport support, raw Deck C/D suppression/no-aliasing, default-on startup wiring, status/heartbeat stale-master separation, invalid/stale fallback, and idle deck-0 clear safety. RE proof confirms local Deck 1/2 channel ownership, upfader chains, LOW/BASS chains, EQ band 2 = LOW/BASS, CFX FILTER tracking chains, relaunch reacquire, and mixer-chain readability after labeled master-button actions. CFX FILTER is not active-deck authority. Direct-master byte authority is existing bridge code behavior, not a field proven by the mixer JSONL artifact. This does not prove SoundSwitch, laser, LED/Govee, DMX, MIDI, Enttec, bridge-output behavior, other Rekordbox versions, live loaded-track play/stop survival, or hardware-visible behavior. Resolver thresholds and stability timing are implementation policy only. |
| SoundSwitch OS2L | partial | unvalidated | OS2L output code exists; hardware/app validation log needed. Audit P2 adds default-off injector gating and pack-status `overlay_suppressed` software coverage only. Audit P3 removes the unused timing-compensation constant and covers explicit scripted elapsed threading in software tests. |
| SoundSwitch offline decoder/exporter/pack/verifier | software-tested | not applicable | Pinned to SoundSwitch 2.10.3 plus the canonical UUID/RAVE profile. Tests verify deterministic export, independent semantic verification, dynamic saved-project inventory reconciliation, proof-only strict snapshot rejection, required binding-sidecar publication/recovery, source sidecar ignored-path derivation/sanitization, the seven-class F-3 crosswalk, loader-superset runtime metadata rejections, report-only import diagnostics, and typed truncated-catalog decode failure. F9 and F10 proof seams remain covered. No project mutation or live output. |
| SoundSwitch scripted loader/player/MIDI/runtime/backend/Enttec | substantial partial software/wire-tested | unvalidated | Loader/player, input adapter (including SoundSwitch-saved Static Override Press/Toggle interaction mode and held-blackout release semantics), backend, sender, default-off config/startup, StateManager driver, commands, copied RW-5 status, and Art-Net truth-check gate have focused tests. Tests cover python-rtmidi `MidiIn`, static-controller auto-bind, alias override, missing/ambiguous input degradation, output-bus exclusion, provider-free reads, precedence, simultaneous degraded/scripted truth, fresh dict publication, lifecycle snapshots, stale menubar state, one-shot auto-enable retry, bounded render/submit failures, connected SoundSwitch shadow-render U1 with production software-zero, fake-only truth sink sidecar/sequence/overflow behavior, ordered sidecar matching across sequence wrap and denser U1 streams, normalized scripted timeline/rapid-pair coverage, Autoloop visible/authored-dark phase buckets based on each loop's cycle, static/blackout overlay-release coverage, active-deck/mode transitions, capture-derived scripted/Autoloop/Static Look parity registries, static fallback lane generalization, supported-layout-family scripted generalization, and 200 Hz loop skip-and-continue on ordinary errors with throttle preserved and no duplicate ZERO after `_push_tick()` inner failures. Fresh generated-pack export now has zero active `unverified_parity` documents and passes the trusted publication software gate. `tools/artnet_compare.py --self-check` covers synthetic parser/matcher/sidecar/timing/order/coverage verdicts without sockets or hardware. `software_zero_frame` and `frame_count` are software intent only; no physical output is validated. |
| SoundSwitch native-DMX Autoloops/T7d | software-tested implementation plus historical evidence partial | unvalidated | Native resolver/player/loader/StateManager tests cover note-to-Autoloop binding, latching, phase, refire/re-anchor, missing binding/file/layout, all-zero dark looks, post-drop fallback, scripted/static/SoundSwitch-present precedence, stale reload clearing, and single submit path. Historical T7d tracer/conductor/oracle tests and captures remain evidence/tooling only; live runtime and hardware validation are still required. |
| Laser policy/executor | partial; lifecycle software-tested | unvalidated | Pure flat-window parity, A3 phrase gating, A4 blackout arm/clear preservation, lifecycle teardown, autoloop-tick cycling, usable-only shuffle bags, static-impact fallback, send-error reopen recovery, high-impact/missing bank skip and restore behavior, blackout-mask refcounting, Laser Pad live-toggle command append, config fallback/cooldown validation, deprecated `pre_drop_scene` tolerance, and kill-switch-OFF behavior have deterministic tests. `tools/check_laser_midi_sync.py` reports 0 errors on the live config. Fixture validation must be recorded separately. |
| LED/Govee cloud | partial | unvalidated | Cloud path exists; device behavior must be logged. The new pure lifecycle resolver does not replace or alter live LED dispatch. |
| LED committed-drop eligibility | partial | unvalidated | `tests/test_led_look_director.py` covers `commit_role("drop", diy_eligible=...)` filtering like normal tick automation. |
| LED phrase-aware active-content hold | software-tested partial | unvalidated | `tests/test_led_state_manager.py` covers immediate release at `0.5` and `1.0` beats into phrase, hold at `1.1` beats until the next phrase marker, active-deck switch arming, active-deck track-load arming, inactive-deck exclusion, idle/stop cleanup, and no laser/SoundSwitch calls from the hold gate. This does not prove room-visible Govee behavior. |
| LED scripted-track automation policy | partial | unvalidated | `tests/test_led_config.py` covers the JSON blackout defaults and `utility` destination validation; `tests/test_led_state_manager.py` covers groove/drop/post-drop blackout mapping, active buildup/breakdown, opt-in overrides, and non-scripted identity behavior. This does not prove room-visible Govee behavior during scripted SoundSwitch tracks. |
| LED/Govee realtime | partial/experimental | unvalidated | Realtime path exists; slot-color strategy behavior, locked-palette resolution, Patch S `random_with_mono_chance`, generic groove/post_drop/drop slot cues, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, Phase 3 renderer param unlocks, Patch F default-bank cleanup, and runner-thread handoff teardown have software tests, but a repeatable instrumented validation record is still pending. AWR-101–104 (M2.5 slot cues incl. Patch E1/E2/E3, color-engine core, realtime comet, beat-sync) have operator hardware sign-off — 2026-06-29, Home Govee, visual; see `docs/validation/hardware_validation_log.md`. The solid-color strategy (Patch S), role-mapping v2 (AWR-105/106), Patch D sparkle, Locked Palette, and Phase 3 renderer param unlock visual outcomes remain SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| LED Pad + Template Lab | software-tested | unvalidated | `tests/test_led_pad_controls.py`, `tests/test_led_pad_playback.py`, `tests/test_led_pad_service.py`, and `tests/test_led_pad_lab.py` cover pad metadata/playback/service/lab behavior. Phase 3 adds locked-palette service coverage plus config/engine/renderer regressions in `tests/test_color_engine_config.py`, `tests/test_led_color_engine.py`, and `tests/test_govee_frame_renderer.py`. This does not prove Govee device behavior or strip restore behavior. |
| Laser Pad/frontend | partial | unvalidated | Syntax/frontend smoke tests do not prove live safety. |

## Required hardware validation record

Use `docs/validation/soundswitch_hardware_validation_procedure.md` and copy
`docs/validation/soundswitch_hardware_runs/TEMPLATE.md` for the SoundSwitch local-setup slice. Their
existence is not hardware evidence; only a completed operator run can change hardware status.

A hardware validation entry must include:

- commit SHA
- date
- OS version
- Rekordbox version
- SoundSwitch version
- device/fixture models
- config file path or redacted config hash
- exact test steps
- observed result
- pass/fail
- caveats
- rollback notes
