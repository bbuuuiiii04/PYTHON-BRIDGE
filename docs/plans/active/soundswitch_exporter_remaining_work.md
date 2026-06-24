---
doc_status: active-plan
truth_level: code-and-test-grounded
last_verified_commit: f6910f9
last_verified_date: 2026-06-24
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
| Saved-project decode/export | Implemented for the bounded 2.10.3 canonical project/RAVE/CH1-CH19 profile. Complete rescans, stable identity, strict validation, and read-only source handling are software-tested. |
| Pack compile/verify/load | Implemented. Deterministic compilation, independent verification, and mutation rejection are software-tested. |
| RW-1 export/publish/reload | Implemented, independently reviewed, and software-tested. Replacement is staged and verified; reload stays conservative and never implies enable/backend/start. Source-fingerprint freshness drives the menubar state. |
| RW-1A shutdown ownership | Implemented, independently reviewed, and software-tested. Graceful shutdown reaches the current runtime-swapped sender and attempts zero before close. Hard process death remains physically unsafe. |
| RW-2 scripted transport | Implemented and software-tested. Pause rerenders/holds the authoritative elapsed frame; confirmed stop/unload/stale authority resolves the base to zero. |
| RW-3 mode authority | Implemented, independently reviewed, and software-tested. Scripted selection requires current bridge-owned scripted authority; Autoloop remains unselected. |
| RW-4 controller health | Implemented, independently reviewed, and software-tested. Degraded controller input releases manual overlays while preserving simultaneous scripted truth; runtime swap resynchronizes static-slot state. |
| RW-5 operational status | Implemented and software-tested. Status is provider-free copied software state; `software_zero_frame` and `frame_count` do not claim serial delivery or physical darkness. |
| Menubar status | Implemented and software-tested. It consumes only the copied status file, bounds the combined row after sanitization, and renders stale status as `Pack: Unknown`. |
| Non-Autoloop hardware procedure | Independent-review revisions are implemented in the procedure/template; fresh implementation review remains pending. No operator evidence run exists. |
| T7d phase evidence | Incomplete. Two accepted arm and two accepted refire integrity captures exist; four scenario pairs, identity/holdout reconciliation, and a unique oracle remain. |
| Native Autoloop DMX | Intentionally not implemented. `StateManager` does not call `select_autoloop`; the automatic base remains software-zero in Autoloop mode. |
| Physical hardware | Unvalidated. No committed real-run evidence file exists. |

The current-project proof record remains 29 PASS / 0 FAIL / 0 INCOMPLETE and
32/32 active scripted tracks exportable at its recorded bounded source snapshot.
That proof is software evidence, not fixture evidence and not a guarantee for
other SoundSwitch versions, projects, profiles, or layouts.

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
- earlier T7/T8 pack-player and offline-shadow records.

Do not resume from a completed spec. Recheck current code and use this roadmap
for remaining scope.

## Remaining work

### 1. Independent implementation review

- [ ] Run the current review-only ChatGPT handoff against the pushed commit
  range.
- [ ] Resolve any blocker/high-severity finding with a separate reviewed change.
- [ ] Keep review conclusions bounded to software/wire evidence.

The review must not edit files, mutate runtime state, inspect live config, start
or stop the bridge, append runtime commands, or open hardware interfaces.

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

### 3. T7d capture evidence

This work remains excluded from the current implementation/review pass.

- [ ] Collect two accepted repetitions for master-switch, drop-hold, buildup,
  and correction using the existing operator-conducted workflow.
- [ ] Reconcile identity/BPM/holdout coverage and unchanged source hashes.
- [ ] Obtain one unique scale/quantizer/origin/reset/continue/snap contract, or
  record FAIL/INCOMPLETE.

The active authority is
`docs/plans/active/soundswitch_t7d_capture_evidence_plan.md`. No phase mapping
may be selected from incomplete evidence.

### 4. Native Autoloop DMX

This work remains excluded and blocked by T7d.

- [ ] Author a separate evidence-grounded implementation spec only after
  `PASS_T7D_PHASE_CONTRACT`.
- [ ] Independently review that spec before implementation.
- [ ] Keep unknown transition classes software-zero.

### 5. Final closeout

- [ ] Rerun the current-project proof against an operator-approved source
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
  `autoloop_phase_blocked`, `software_zero_frame`;
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
   provider, worker-polling, sleep, retry, or blocking work.
3. Source SoundSwitch projects are read-only; complete saved bytes are authority.
4. Identity is exact. Display names, fuzzy paths, and file order are not IDs.
5. Only independently verified packs may publish or load.
6. Reload/export never enables output, changes backend, starts/restarts the
   bridge, or opens hardware.
7. Direct DMX and physical MIDI-laser output remain mutually exclusive.
8. Automatic base output resolves software-zero on unowned mode, stop/unload,
   stale/error, invalid identity, failed render/reload, disable, and shutdown.
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
| Active T7d plan/handoff | `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md`, `soundswitch_t7d_capture_gate_handoff.md` |
| T7d result | `docs/validation/soundswitch_t7d_phase_contract_evidence.md`, `soundswitch_t7d_phase_contract_blocked.md` |
| Hardware procedure/template | `docs/validation/soundswitch_hardware_validation_procedure.md`, `soundswitch_hardware_runs/TEMPLATE.md` |

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
- [ ] T7d uniquely proves the active Autoloop phase contract;
- [ ] native Autoloop DMX uses only that proven contract;
- [ ] final proof, full software gates, and independent review pass;
- [ ] a real operator hardware run is recorded;
- [ ] unchanged behavior outside enabled pack mode is verified at the final
  checkpoint.

Until then: **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
