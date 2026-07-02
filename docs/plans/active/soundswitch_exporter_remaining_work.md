---
doc_status: active-plan
truth_level: code-and-test-grounded
last_verified_commit: 3f4bcc0
last_verified_date: 2026-07-02
validation_scope: SoundSwitch 2.10.3 canonical-project/RAVE-profile implementation status; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch Exporter and Bridge-Native DMX - Current Status and Remaining Work

This is the single current implementation-status authority for the SoundSwitch
exporter and bridge-native DMX project. Code and tests win if this file drifts.
Completed implementation details live under `docs/plans/completed/soundswitch/`;
they are history, not active instructions.

The bounded operator workflow remains:

1. Save lighting in SoundSwitch 2.10.3.
2. Click `Export from Soundswitch` in the bridge menubar.
3. Publish one verified canonical pack without damaging the prior verified pack.
4. Conservatively reload an already-enabled pack runtime without enabling output,
   changing backend, or starting the bridge.
5. Render scripted tracks and manual static/blackout controls through the
   bridge-owned CH1-CH19 path.

Accepted status is **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
No document in this route authorizes a restart, config toggle, runtime command,
MIDI/serial/Enttec/DMX open, fixture connection, or hardware action.

## Current status

| Area | Current evidence |
| --- | --- |
| Saved-project decode/export | Implemented for the bounded 2.10.3 canonical project/RAVE/CH1-CH19 profile. Complete dynamic rescans, stable identity, strict semantic validation, dynamic inventory reconciliation, and read-only source handling are software-tested. |
| Pack compile/verify/load | Implemented. Deterministic compilation, independent verification, and mutation rejection are software-tested. |
| Parity evidence lanes | Implemented from passive SoundSwitch U0 capture `parity_20260701T185231Z`. Scripted and Autoloop registry fixtures are venue/source-hash pinned; Static Looks use the documented unavailable-window fallback plus the C6 non-generic assertion and export as `algorithm_generalized`. Segment-aware Autoloop reduction records capture-diverged non-PASS segments outside the positive registry; supported scripted layout variants generalize only when every positive reference resolves into the current cue set. Fresh export now reports active lanes `algorithm_generalized: 69`, `oracle_proven: 14`, `unverified_parity: 0`; inactive lanes `algorithm_generalized: 29`, `oracle_proven: 0`, `unverified_parity: 6`. Trusted publication is software-gated green. |
| RW-1 export/publish/reload | Implemented, independently reviewed, and software-tested. Replacement is staged and verified; the required binding sidecar is staged before swap, and pre-swap sidecar failure preserves the prior pack. Reload stays conservative and never implies enable/backend/start. Source-fingerprint freshness drives the menubar state. Stable opaque backup/media/preset rewrites are ignored, but `recordable/*.dat` remains fingerprinted because it can later decode into learned-MIDI/control-state content; older sidecars that listed it fail open. |
| RW-1A shutdown ownership | Implemented, independently reviewed, and software-tested. Graceful shutdown reaches the current runtime-swapped sender and attempts zero before close. Hard process death remains physically unsafe. |
| RW-2 scripted transport | Implemented and software-tested. Pause rerenders/holds the authoritative elapsed frame; confirmed stop/unload/stale authority resolves the base to zero. |
| RW-3 mode authority | Implemented, independently reviewed, and software-tested. Scripted selection requires current bridge-owned scripted authority; Autoloop selection is native-only when SoundSwitch is absent and no scripted identity owns the base. |
| RW-4 controller health | Implemented, independently reviewed, and software-tested. Degraded controller input releases manual overlays while preserving simultaneous scripted truth; missing/ambiguous static-controller input no longer disables pack DMX; runtime swap resynchronizes static-slot state. |
| RW-5 operational status | Implemented and software-tested. Status is provider-free copied software state; `software_zero_frame` and `frame_count` do not claim serial delivery or physical darkness. |
| Menubar status | Implemented and software-tested. It consumes only the copied status file, bounds the combined row after sanitization, and renders stale status as `Lighting: no status yet`. |
| Menubar auto-switch | Implemented and software-tested. `_auto_set_soundswitch_pack()` (`scripts/bridge_menubar.py:883`) flips pack output by SoundSwitch connection using `set_soundswitch_pack action=enable`; a fresh disconnected `pack_start_failed` auto-enable gets one bounded retry. No manual pack button; no implicit hot-enable; enabling still requires a real `output_backend=pack` + `dry_run=false` + Enttec port. |
| Static Press/Toggle interaction mode | Implemented and software-tested. The decoder reads the SoundSwitch-saved Press/Toggle byte (`PushButton+0xc1`, `soundswitch_project_decoder.py:855-888`); the pack model/loader carry `interaction_mode ∈ {press, toggle}` (`soundswitch_pack_models.py:250`, `soundswitch_pack_loader.py:53,283`); the MIDI input adapter latches toggle slots and ignores note-off for toggles (`soundswitch_midi_input.py:220-252`). Unknown saved mode fails closed to momentary. |
| Canonical pack location | Repo-local ignored path `local/soundswitch/rbss_canonical_pack` (`git check-ignore` confirmed). The tracked example config names the absolute local checkout path; old `~/Music/SoundSwitch/...` references survive only in historical completed specs. |
| Non-Autoloop hardware procedure | Independent-review revisions are implemented in the procedure/template; the latest software/wire implementation review is complete. No operator evidence run exists. |
| T7d phase evidence | Historical/incomplete under the old six-scenario gate. It no longer blocks native Autoloop DMX; the active native path uses bridge-owned phase, `AUTOLOOP_TICKS_PER_BEAT = 600`, `phase_offset_beats`, the offline equivalence oracle, and an operator two-flight calibration/A-B run. |
| Native Autoloop DMX | Implemented and software-tested under `docs/architecture/native_autoloop_pack_authority.md` and `docs/plans/active/native_autoloop_dmx_runtime_spec.md`. StateManager resolves the already-selected laser scene edge through canonical pack note bindings, latches across no-edge ticks, phases an 8-bar/32-beat timeline at 600 ticks/beat with `phase_offset_beats`, preserves scripted/static/blackout/SoundSwitch-present precedence, and fails closed on missing binding/file/layout. Live/runtime validation, oracle calibration, and hardware evidence remain open. |
| Art-Net truth-check gate | Implemented as a temporary default-off final-retirement measurement path. `RBSS_ARTNET_TRUTH_CHECK=1` plus a valid `RBSS_ARTNET_UNIVERSE` builds pack rendering without Enttec, emits bridge shadow-render ArtDMX U1 with JSONL sidecar evidence, and keeps production pack output software-zero while SoundSwitch is connected. `tools/artnet_compare.py --self-check` is software-tested with synthetic traces, and the live coverage ledger now requires matched sidecar rows for normalized scripted timeline events/rapid pairs, Autoloop visible/authored-dark phase buckets based on each loop's cycle, static/blackout overlay-release combinations, and active-deck/mode transition directions. Denser U1 streams are allowed only through ordered nearest-neighbor matches with valid sidecar evidence for every captured U1 packet, and extra U1 rows do not satisfy coverage. The actual U0/U1 capture exam is not yet run, so no PASS or hardware claim exists. |
| Physical hardware | Unvalidated. No committed real-run evidence file exists. |

The old 29 PASS / 0 FAIL / 0 INCOMPLETE proof record remains closure evidence
for its recorded source snapshot only. Live export now reconciles the saved
project dynamically, while the old snapshot totals are enforced only when proof
tooling explicitly asks for strict snapshot mode. That proof is software
evidence, not fixture evidence and not a guarantee for other SoundSwitch
versions, projects, profiles, or layouts.

## Completed implementation records

Material specifications are retained only under
`docs/plans/completed/soundswitch/`:

- RW-1 export, post-review fixes, and freshness detection;
- RW-1A graceful shutdown ownership;
- RW-2 pause/stop transport;
- RW-3 mode authority;
- RW-4 input degradation and static-slot swap resynchronization;
- RW-5 copied operational status and menubar visibility;
- the non-Autoloop hardware procedure/template implementation;
- earlier T7/T8 pack-player and offline-shadow records;
- the completed menubar connection auto-switch spec (`soundswitch_pack_menu_enable_spec.md`);
- the repo-local canonical pack move (`soundswitch_pack_repo_local_handoff.md`);
- the SoundSwitch Static Override Press/Toggle parity spec (`soundswitch_static_toggle_spec.md`);
- the roadmap/registry reconciliation spec (`soundswitch_roadmap_registry_reconciliation_spec.md`)
  and the read-only remaining-software scoping snapshot
  (`soundswitch_remaining_software_scope.md`).

Do not resume from a completed spec. Recheck current code and use this roadmap
for remaining scope.

## Label crosswalk (one scheme, three names)

Three label sets name the same items; they are not separate work:

| Scheme | Origin | Covers |
| --- | --- | --- |
| Roadmap items 1-5 + T7d | this file | the live naming used here |
| `RW-1 … RW-10` | original workstream phase order | survives only in completed RW-1…RW-5 specs and the `rw7` capture-prompt filename |
| `Task 7/8/9` → `T7c/T7d/T7e` | product/format spec | pack-driver / Autoloop-evidence / runtime-control lineage |

## Remaining work

### 1. Independent implementation review

Current checkpoint complete at `e48092d`; see
`docs/validation/soundswitch_exporter_player_software_review.md` and
`docs/validation/soundswitch_publish_sidecar_review.md`. No blocker/high
findings were found; one medium menubar parser mismatch was fixed.

- [x] Run the current review-only ChatGPT handoff against the current `main`
  range.
- [x] Resolve any blocker/high-severity finding with a separate reviewed change.
- [x] Keep review conclusions bounded to software/wire evidence.

The review must not edit files, mutate runtime state, inspect live config, start
or stop the bridge, append runtime commands, or open hardware interfaces.

Ready-to-paste handoff:
`docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md`.

### 2. Non-Autoloop operator hardware run

- [ ] The operator prepares ignored local configuration while the exact bridge
  process detector reports zero real bridge processes.
- [ ] The operator confirms a reachable physical kill path before any non-zero
  output.
- [ ] The operator explicitly approves menubar startup and verifies exactly one
  real bridge process afterward.
- [ ] The operator proves a dark idle baseline, executes only the bounded
  non-Autoloop matrix, performs the emergency rehearsal, and restores config to
  default-off.
- [ ] A sanitized evidence file is created from
  `docs/validation/soundswitch_hardware_runs/TEMPLATE.md`.

The controlling document is
`docs/validation/soundswitch_hardware_validation_procedure.md`. Status cannot
prove physical kill reachability, controller release, in-room Rekordbox
transport, fixture darkness, or Enttec output darkness; those remain operator
observations/actions. If a known-dark baseline cannot be proven after an
emergency zero failure or unknown result, the run is FAIL or INCOMPLETE.

### 3. Autoloop phase/equivalence evidence

The old six-scenario T7d gate is no longer required for the native bridge-owned
Autoloop runtime. It tried to prove SoundSwitch's hidden runtime phase/origin
behavior before choosing a bridge phase formula. The native plan now chooses the
bridge-owned formula directly and keeps one operator calibration input:
`phase_offset_beats`.

- [x] Retire T7d as a blocker for native Autoloop DMX.
- [ ] Use the offline Autoloop equivalence oracle to compare bridge-rendered
  Autoloop frames against captured SoundSwitch output.
- [ ] Run the operator two-flight calibration/A-B pass before making any
  hardware-validated or show-ready claim.

The old T7d files remain useful historical evidence/tooling, but they are not
the active implementation gate for native Autoloop DMX.

### 4. Native Autoloop DMX

This work is implemented and software-tested, but not live/runtime or hardware
validated.

- [x] Author the operator-authoritative behavior document:
  `docs/architecture/native_autoloop_pack_authority.md`.
- [x] Author and adversarially review the implementation spec:
  `docs/plans/active/native_autoloop_dmx_runtime_spec.md`.
- [x] Implement native Autoloop DMX from exported pack mappings only when
  SoundSwitch is absent.
- [x] Replace the old software-zero-only Autoloop base with fail-closed native
  rendering through the existing pack submit path.
- [x] Confirm canonical-pack role-note mappings before implementation: no
  post_drop maps means post-drop falls back to 32-beat drop-bank cycling; mapped
  post_drop looks cycle inside the post_drop bank every 32 beats.
- [ ] Run live/runtime validation against Rekordbox transport, role changes,
  pack reload, SoundSwitch-present suppression, Static Override, and scripted
  precedence before any operator-use claim.

### 5. Final closeout

- [x] Build the current passive-capture parity evidence fixtures/registries for
  scripted tracks, native Autoloops, and Static Looks.
- [x] Resolve the active `unverified_parity` blockers before trusted
  publication. Fresh export now reports active lanes `algorithm_generalized: 69`,
  `oracle_proven: 14`, `unverified_parity: 0`; inactive unverified documents
  remain reported under `parity_lanes_inactive`.
- [ ] Run the Art-Net U0/U1 truth-check capture exam with SoundSwitch U0 as
  ground truth, bridge U1 shadow output, fresh sidecar/run ID, full coverage, and
  `tools/artnet_compare.py --self-check` already passing.
- [ ] Rerun the proof-only snapshot gate or refresh its approved source
  snapshot after all software work, including any future Autoloop work.
- [ ] Run focused tests, full tests, docs gates, and adversarial review at the
  final software checkpoint.
- [ ] Complete and commit a real operator hardware evidence record before any
  bounded local hardware-validation claim.
- [ ] Keep all broader compatibility and maturity claims explicitly unsupported.

## RW-5 status contract

The copied pack status contains only:

- bundle facts: `available`, `enabled`, `backend`, `pack_loaded`, `pack_sha12`,
  and bounded `reason`;
- `operational_state` with precedence `disabled`, `blackout`,
  `input_degraded`, `static_held`, `scripted_active`,
  native Autoloop states (`rendering_active`, `empty_dark_look`,
  `missing_binding`, `missing_autoloop_file`, `unsupported_layout`,
  `soundswitch_present_native_suppressed`), `autoloop_phase_blocked`,
  `software_zero_frame`;
- authoritative companion booleans for those simultaneous truths;
- `frame_count`, meaning attempted normal software frames;
- `has_active_identity`, derived from in-memory backend state.

`software_zero_frame` means only `frame == _PACK_ZERO_FRAME`. It does not prove
that submit succeeded, serial sent, Enttec accepted a packet, fixtures are dark,
or a hard-killed Enttec stopped retransmitting a stale frame. Submit/render
failures expose only bounded software state; raw exceptions and private data do
not enter status or the menubar.

## Invariants

1. `StateManager` remains the only writer of `DeckState` and the sole per-tick
   pack-frame submit owner.
2. The 200 Hz path gains no filesystem, subprocess, MIDI, serial, socket,
   provider, worker-polling, retry, or blocking work, and no sleeps beyond the
   existing StateManager tick throttle.
3. Source SoundSwitch projects are read-only; complete saved bytes are authority.
4. Identity is exact. Display names, fuzzy paths, and file order are not IDs.
5. Only independently verified packs may publish or load.
6. Reload/export never enables output, changes backend, starts/restarts the
   bridge, or opens hardware.
7. Direct DMX and physical MIDI-laser output remain mutually exclusive.
8. Automatic base output resolves software-zero or a native fail-closed state on
   unowned mode, stop/unload, stale/error, invalid identity, missing
   binding/file/layout, failed render/reload, disable, and shutdown.
9. Blackout wins; manual Static Override behavior changes only under an
   explicit reviewed policy.
10. Existing OS2L, lasers, LEDs/Govee, Rekordbox readers, and default-off bridge
    behavior remain unchanged outside explicitly enabled pack mode.
11. Status, logs, docs, and evidence never expose local paths, ports, aliases,
    device names, fixture serials, project UUIDs, raw frames/hashes/errors,
    config contents, or raw status files.
12. Graceful zero is a software attempt. Hard-kill safety still requires a
    physical kill path and a known-dark restore baseline.
13. Software tests and passive wire evidence never become fixture validation.

## Document map

| Purpose | Authority |
| --- | --- |
| Current implementation status | this file |
| Project routing | `docs/plans/active/soundswitch_README.md` |
| Product/format contract | `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` |
| Current RE routing | `docs/research/soundswitch/README.md` |
| Completed implementation specs | `docs/plans/completed/soundswitch/` |
| Historical T7d plan/handoff | `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md`, `soundswitch_t7d_capture_gate_handoff.md` |
| Historical T7d result | `docs/validation/soundswitch_t7d_phase_contract_evidence.md`, `soundswitch_t7d_phase_contract_blocked.md` |
| Native Autoloop authority/spec | `docs/architecture/native_autoloop_pack_authority.md`, `docs/plans/active/native_autoloop_dmx_runtime_spec.md` |
| Autoloop equivalence oracle | `docs/plans/active/soundswitch_autoloop_equivalence_oracle_spec.md` |
| Hardware procedure/template | `docs/validation/soundswitch_hardware_validation_procedure.md`, `soundswitch_hardware_runs/TEMPLATE.md` |
| Latest independent review | `docs/validation/soundswitch_exporter_player_software_review.md`, `docs/validation/soundswitch_publish_sidecar_review.md` |
| Reusable review prompt | `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` |

The separately scoped roadmap/registry reconciliation spec is not part of this
route or this implementation pass.

## Required software gates

```bash
python3 -m unittest \
  tests.test_state_manager_pack_driver \
  tests.test_soundswitch_pack_commands \
  tests.test_runtime_status \
  tests.test_bridge_menubar \
  tests.test_soundswitch_frame_sender \
  tests.test_enttec_dmx_pro \
  tests.test_soundswitch_pack_startup
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

All tests must use fake/injected interfaces. These commands do not authorize
live configuration, process control, runtime commands, or hardware access.

## Project completion definition

The full project is not complete until all of the following are proven:

- [x] one-click saved-project export safely replaces one canonical pack and
  reports bounded operator state;
- [x] RW-1A through RW-5 scripted transport, mode, input-health, shutdown, and
  copied-status work is implemented and software-tested;
- [x] native Autoloop DMX implements the greenlit bridge-owned phase contract,
  canonical-pack role-note checks, and `phase_offset_beats` calibration path;
- [ ] the offline equivalence oracle and operator two-flight/A-B pass are
  recorded before any hardware-validated claim;
- [ ] final proof, full software gates, and independent review pass;
- [ ] a real operator hardware run is recorded;
- [ ] unchanged behavior outside enabled pack mode is verified at the final
  checkpoint.

Until then: **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
