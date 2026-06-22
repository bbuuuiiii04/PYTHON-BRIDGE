---
doc_status: active-validation
truth_level: code-grounded
last_verified_commit: 37fffa4
last_verified_date: 2026-06-22
validation_scope: T7d phase-contract evidence ledger; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# T7d phase-contract evidence ledger

## Final verdict (this session): `INCOMPLETE_T7D_EVIDENCE`

No hardware captures were taken. The bridge core process was not running at the
start of this session and the runtime status file was stale (frozen at
2026-06-21 19:53; session date 2026-06-22), so the passive-capture reference
path (live OS2L → SoundSwitch → Universe-0 Art-Net) could not be observed. The
capture matrix therefore has **zero accepted, zero rejected, zero
incomplete** real captures. The live capture gate was handed off
(`docs/plans/active/soundswitch_t7d_capture_gate_handoff.md`) so it runs when the
operator is physically present at the decks.

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
| ACCEPTED | 0 | no live bridge; no captures taken |
| REJECTED/FAIL | 0 | — |
| INCOMPLETE | 0 | — (none attempted; gate handed off) |

Required before B6 can pass (plan §A4/§B6): two ACCEPTED repetitions for each of
arm, refire, master-switch, drop-hold, buildup, correction; ≥3
verified IAC/bank-4 identities; ≥2 BPM/pitch values; ≥1 full holdout identity.

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

- **Did 600 pass on real data?** Unknown — no real captures. On synthetic data
  the oracle correctly *recovers* 600 when 600 is the truth and *rejects* 600
  when 480 is the truth (`test_recovers_480_and_explicitly_rejects_600`).
- **Winning quantizer:** Unknown on real data. Synthetic tests show floor can be
  distinguished from round only with boundary-straddling samples; at realistic
  Art-Net spacing the quantizer may be undetermined, in which case the oracle
  returns FAIL (ambiguous) rather than guessing.

## Per-scenario origin / reset / continue / snap

| scenario | result |
| --- | --- |
| arm | UNKNOWN — requires capture |
| refire | UNKNOWN — requires capture |
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

## Other required fields (all pending real capture)

- **Transition timing tolerance / clock residual:** n/a — measured per capture
  from dual timestamps; the oracle's `compare_wire_frames` enforces it.
- **Identity ownership:** n/a — resolved offline from the verified
  scene→identity map + AppLog; the oracle requires unambiguous ownership.
- **Universe-0 verification:** n/a — `count_universe0_frames` /
  `parse_artnet_pcap.universe_frames` ready; `MIN_UNIVERSE0_FRAMES = 20`.
- **Project before/after hash:** n/a — conductor + plan §B4 hash before/after;
  any drift → FAIL.
- **Recorder drops:** n/a — schema-2 tracer counts dropped samples; any drop
  spanning a segment → INCOMPLETE.

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
real beat authority. No amount of software testing substitutes for that
observation. With the bridge down and the operator not at the decks, the honest
verdict is `INCOMPLETE_T7D_EVIDENCE`. See
`docs/validation/soundswitch_t7d_phase_contract_blocked.md` for the exact missing
evidence and `…_capture_gate_handoff.md` for how the next agent obtains it.
