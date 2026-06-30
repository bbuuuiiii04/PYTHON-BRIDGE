---
doc_status: active-validation
truth_level: code-grounded
last_verified_commit: 6c51eb8
last_verified_date: 2026-06-23
validation_scope: T7d phase-contract evidence ledger; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# T7d phase-contract evidence ledger

## Current verdict: `INCOMPLETE_T7D_EVIDENCE` for the old six-scenario gate

> Superseded for native Autoloop implementation as of 2026-06-29.
> This ledger remains evidence for the older T7d proof plan, but it no longer
> blocks native Autoloop DMX. The active native path is documented in
> `docs/architecture/native_autoloop_pack_authority.md` and
> `docs/plans/active/native_autoloop_dmx_runtime_spec.md`.

Five live wire-capture runs now exist under the ignored T7d capture corpus. The
capture conductor classifies **four ACCEPTED** integrity runs (two `arm`, two
`refire`) and **one FAIL** run (the first `arm` baseline recorded zero core
bridge processes). Each accepted run has an unchanged project hash, a clean
phase footer, zero recorder drops, the required marker, and more than 20
Universe-0 frames.

`ACCEPTED` here means only that the capture artifact passed the conductor's
fail-closed integrity gate. It is **not** a phase-contract pass and it is not
physical fixture validation. No accepted capture has a checked-in
`PASS_T7D_PHASE_CONTRACT` oracle result. Four scenarios have not been captured,
and identity/holdout coverage has not been reconciled. The only honest corpus
verdict therefore remains `INCOMPLETE_T7D_EVIDENCE`.

**Scope update 2026-06-22:** the pass is **six** scenarios. `phrase-anchor` was
dropped — `_phrase_anchor` only fires with `RBSS_PHRASE_ANCHOR=1`
(`state_manager.py:481`), which the operator's live rig does not set, so its
phase origin is not part of the runtime contract.

This ledger records what is **software-ready** and what real evidence is still
required. It does not fabricate capture results and it does not upgrade hardware
status.

## Capture set

| state | count | notes |
| --- | --- | --- |
| ACCEPTED | 4 | `arm` 2, `refire` 2; conductor integrity classification only |
| REJECTED/FAIL | 1 | initial `arm`; baseline recorded zero core bridge processes |
| INCOMPLETE | 0 | no attempted run has this conductor classification |

| scenario | ACCEPTED | FAIL | still required before corpus oracle |
| --- | ---: | ---: | --- |
| arm | 2 | 1 | capture-count gate met; oracle/identity reconciliation pending |
| refire | 2 | 0 | capture-count gate met; oracle/identity reconciliation pending |
| master-switch | 0 | 0 | 2 accepted runs |
| drop-hold | 0 | 0 | 2 accepted runs |
| buildup | 0 | 0 | 2 accepted runs |
| correction | 0 | 0 | 2 accepted runs |

Required before B6 can pass (plan §A4/§B6): finish the four missing scenario
pairs; reconcile at least three verified IAC/bank-4 identities; prove at least
two BPM/pitch values; and reserve at least one full holdout identity. The
accepted traces contain observed BPM values 130, 138, 141, and 150, but that
does not satisfy B6 until each oracle segment has unambiguous identity ownership
and the cross-validation/holdout split is documented.

## Tooling readiness (software/wire-validated only)

| component | file | sha256 | tests |
| --- | --- | --- | --- |
| Falsifiable oracle (pure) | `tools/ssfmt/re/t7d_phase_contract.py` | `7c1bf719…16bd93c` | `tests/test_t7d_phase_contract.py` (16) |
| Oracle CLI mode | `tools/ssfmt/re/validate_autoloop_capture.py --t7d` | (modified) | glue, real-data only |
| Phase-trace tooling | `session_phase_trace.py` | `6ea6ae94…1670fd6` | `tests/replay/test_phase_trace.py` (7) |
| Schema-2 recorder/replayer | `session_recorder.py`, `session_replayer.py` | (modified) | replay tests |
| Capture conductor | `tools/t7d_capture_conductor.py` | `f648d433…2e4d3cf7a`* | `tests/test_t7d_capture_conductor.py` (18) |

\* sha256 truncated for readability; full digests in this session's tool output.
Test-file digests: oracle `3923daea…655dd22`, conductor `f650ba6a…9209e3d`,
phase-trace `e3f617f5…b22c93f2`. All 89 focused tests pass; the three hard doc
checks (metadata, agent-contracts, drift) and `git diff --check` pass.

## Ticks/beat candidates the oracle tests

The oracle's default candidate set is a broad rational search: `19200 / b` for
integer beats-per-cycle `b ∈ [8, 128]` that divide evenly, plus {480, 600, 720}.
**600 is always included but never assumed.** The circular `rate = bpm * 10.0`
premise (equivalent to assuming 600) was removed from the fit path.

- **Did 600 pass on real data?** Unknown — the accepted captures have not been
  run through a complete, documented corpus oracle. On synthetic data
  the oracle correctly *recovers* 600 when 600 is the truth and *rejects* 600
  when 480 is the truth (`test_recovers_480_and_explicitly_rejects_600`).
- **Winning quantizer:** Unknown on real data. Synthetic tests show floor can be
  distinguished from round only with boundary-straddling samples; at realistic
  Art-Net spacing the quantizer may be undetermined, in which case the oracle
  returns FAIL (ambiguous) rather than guessing.

## Per-scenario origin / reset / continue / snap

| scenario | result |
| --- | --- |
| arm | CAPTURED 2/2; phase origin still UNKNOWN until oracle |
| refire | CAPTURED 2/2; phase origin still UNKNOWN until oracle |
| master-switch | UNKNOWN — requires capture |
| drop-hold | UNKNOWN — requires capture |
| buildup | UNKNOWN — requires capture |
| correction | UNKNOWN — requires capture |
| ~~phrase-anchor~~ | DROPPED — `RBSS_PHRASE_ANCHOR` off in live rig; not in runtime contract |

The oracle selects the origin **only** from recorded-state hypotheses
(arm-sync target, MIDI/refire origin, phrase anchor, accepted-selection beat,
continuous global); there is no free-offset path. Synthetic tests confirm it
selects continuous, snap, and arm-sync origins correctly when they are
distinguishable, and reports aliasing (e.g. 32-beat-multiple origins at tpb=600)
as ambiguity rather than a guess.

## Other required fields

- **Transition timing tolerance / clock residual:** not yet documented for the
  accepted runs; it must be measured from dual timestamps before oracle use.
- **Identity ownership:** not yet reconciled for the accepted runs; resolve
  offline from the verified
  scene→identity map + AppLog; the oracle requires unambiguous ownership.
- **Universe-0 verification:** conductor counts pass for the four accepted runs
  (1,530; 1,813; 2,617; and 2,871 frames). Ownership/segment alignment still
  requires oracle review.
- **Project before/after hash:** matched for all four accepted runs.
- **Recorder drops:** zero and footer clean for all four accepted runs.

## Ambiguities and rejected hypotheses (synthetic coverage)

The oracle is proven on synthetic data to reject these failure modes:
circular 600 assumption (removed); free per-segment phase offset (no such code
path); blackout/zero frames as free skips (counted as hard mismatches);
quantizer/origin aliasing presented as a guess (reported as FAIL); a
constant/low-transition timeline proving scale (INCOMPLETE below 4 discriminating
transitions); a wall-clock fit masquerading as beat-domain (two-BPM invariance
test).

## Why this is INCOMPLETE, precisely

The phase contract is a property of the **live** bridge → SoundSwitch animation
pipeline. It can only be measured by observing real Universe-0 frames against a
real beat authority. Four integrity-accepted runs are useful progress, but they
cover only two of six scenarios and have not produced a unique corpus oracle
fit. The honest verdict remains `INCOMPLETE_T7D_EVIDENCE`. See
`docs/validation/soundswitch_t7d_phase_contract_blocked.md` for the exact missing
evidence and `…_capture_gate_handoff.md` for how the next agent obtains it.
