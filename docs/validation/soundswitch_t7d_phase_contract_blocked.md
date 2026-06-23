---
doc_status: active-validation
truth_level: code-grounded
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
validation_scope: T7d blocked report; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# T7d runtime autoloop DMX spec — BLOCKED

**A runtime autoloop DMX implementation spec cannot honestly be written yet.**
The phase contract it would encode (TICKS_PER_BEAT, integer quantizer, and the
per-transition origin/reset/continue/snap rules) is **unknown** and is provable
only from a complete live capture corpus and unique oracle result that do not
yet exist. Writing a spec now would mean inventing a beat-to-animation mapping
— exactly what plan §A3/§B6 forbid.
Per the mission's own rule, no fabricated spec is produced.

This is **not** an easy exit: the software workflow exists and four captures
have passed its integrity gate. Remaining work includes physical capture labor
for four scenario pairs plus offline identity reconciliation and oracle analysis.
What is blocked is the complete evidence contract, not the tooling.

## What is DONE (software/wire-validated only)

- Plan §B4.5 active-wait workflow; B1 phase-trace tooling + tests; B2 falsifiable
  oracle + 16 synthetic tests + `--t7d` CLI; capture conductor + 18 tests. All 89
  focused tests pass; hard doc checks + `git diff --check` pass. See
  `docs/validation/soundswitch_t7d_phase_contract_evidence.md`.

## Exactly what evidence is missing

The corpus remains `INCOMPLETE_T7D_EVIDENCE`. The conductor has accepted two
`arm` and two `refire` integrity runs and failed one earlier `arm` run. There is
no complete, documented real-capture oracle verdict. To reach
`PASS_T7D_PHASE_CONTRACT`, the following still must be produced or verified
(plan §B6):

1. **A running bridge + present operator for the remaining captures.** Recheck
   exactly one core process, pack output disabled, and fixtures/Enttec safe
   immediately before the next run.
2. **Two ACCEPTED repetitions of each remaining scenario** — master-switch,
   drop-hold, buildup, correction. The arm/refire count gate is met. Every new
   run still needs the
   scenario's required bridge-log markers, no recorder drops, unchanged project
   before/after hashes, and ≥20 Universe-0 frames.
3. **Identity/BPM coverage:** ≥3 verified IAC/bank-4 identities with distinct
   transition spacing, ≥2 materially different BPM/pitch values, and ≥1 full
   holdout identity (so a wall-clock fit cannot masquerade as a beat-domain fit).
4. **A smoke-verified running B1 trace for the next session.** Existing accepted
   runs contain schema-2 `autoloop_phase` rows and clean footers. Reverify after
   any restart; a stale process or invalid footer makes a new run INCOMPLETE.
5. **No special flag restart is required by the active six-scenario pass.**
   Phrase-anchor was dropped because the live launch does not enable it. No
   synthetic event may substitute for an active scenario.
6. **A unique fit:** one TICKS_PER_BEAT and one integer-boundary rule passing both
   cross-validation directions, every alternative rejected with a reported margin,
   the report stating explicitly whether 600 passed; and a deterministic
   reset/continue/snap rule pinned for all six active transition classes with no
   per-segment fitted offset.

## What action unblocks it

Follow `docs/plans/active/soundswitch_t7d_capture_gate_handoff.md`:
`prepare` → `run-scenario <remaining-name>` (active-wait, two accepted reps) →
`summarize-corpus` → `validate_autoloop_capture.py --t7d` per accepted segment.
Then update the evidence ledger. **Only if** the corpus verdict is
`PASS_T7D_PHASE_CONTRACT` does
`docs/plans/active/soundswitch_t7d_runtime_autoloop_dmx_implementation_spec.md`
get written, grounded byte-for-byte in that evidence.

Until then T7d stays `planned, blocked` and `_drive_pack_output` continues to
clear the automatic autoloop base to safe-zero (or allows only the existing
independently held static override). Repo status remains **SOFTWARE/WIRE-VALIDATED
ONLY / HARDWARE-UNVALIDATED**.
