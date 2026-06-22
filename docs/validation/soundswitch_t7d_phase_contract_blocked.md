---
doc_status: active-validation
truth_level: code-grounded
last_verified_commit: 37fffa4
last_verified_date: 2026-06-22
validation_scope: T7d blocked report; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# T7d runtime autoloop DMX spec — BLOCKED

**A runtime autoloop DMX implementation spec cannot honestly be written yet.**
The phase contract it would encode (TICKS_PER_BEAT, integer quantizer, and the
per-transition origin/reset/continue/snap rules) is **unknown** and is provable
only from live capture evidence that does not yet exist. Writing a spec now would
mean inventing a beat-to-animation mapping — exactly what plan §A3/§B6 forbid.
Per the mission's own rule, no fabricated spec is produced.

This is **not** an easy exit: the full software workflow was built and exhausted
to the point where only physical operator labor remains. What is blocked is the
evidence, not the tooling.

## What is DONE (software/wire-validated only)

- Plan §B4.5 active-wait workflow; B1 phase-trace tooling + tests; B2 falsifiable
  oracle + 16 synthetic tests + `--t7d` CLI; capture conductor + 18 tests. All 89
  focused tests pass; hard doc checks + `git diff --check` pass. See
  `docs/validation/soundswitch_t7d_phase_contract_evidence.md`.

## Exactly what evidence is missing

The oracle returns `INCOMPLETE_T7D_EVIDENCE` because there are **zero** captures.
To reach `PASS_T7D_PHASE_CONTRACT`, the following must be produced on the live
bridge (plan §B6):

1. **A running bridge + present operator.** At session time the bridge core
   process was not running and the status file was stale. Nothing downstream can
   proceed until Brandon starts the bridge (one core process) and is at the
   decks.
2. **Two ACCEPTED repetitions of each of the seven scenarios** — arm, refire,
   master-switch, drop-hold, buildup, phrase-anchor, correction — each with the
   scenario's required bridge-log markers, no recorder drops, unchanged project
   before/after hashes, and ≥20 Universe-0 frames.
3. **Identity/BPM coverage:** ≥3 verified IAC/bank-4 identities with distinct
   transition spacing, ≥2 materially different BPM/pitch values, and ≥1 full
   holdout identity (so a wall-clock fit cannot masquerade as a beat-domain fit).
4. **The reviewed B1 `_push_tick` integration**, so `session.jsonl` actually
   contains schema-2 `autoloop_phase` rows. This single hot-path edit is
   live-critical and is deferred for plan-first review (plan §B1 status note). No
   phase trace ⇒ no beat authority per pcap frame ⇒ no falsifiable fit.
5. **An approved flag restart** for phrase-anchor (`RBSS_SMART_REARM_EXPERIMENT=1`,
   `RBSS_PHRASE_ANCHOR=1`), and possibly for correction. Until approved+performed,
   those captures stay INCOMPLETE; no synthetic event may be substituted.
6. **A unique fit:** one TICKS_PER_BEAT and one integer-boundary rule passing both
   cross-validation directions, every alternative rejected with a reported margin,
   the report stating explicitly whether 600 passed; and a deterministic
   reset/continue/snap rule pinned for all seven transition classes with no
   per-segment fitted offset.

## What action unblocks it

Follow `docs/plans/active/soundswitch_t7d_capture_gate_handoff.md`:
`prepare` → `run-scenario <name>` (active-wait, two accepted reps each) →
`summarize-corpus` → `validate_autoloop_capture.py --t7d` per accepted segment.
Then update the evidence ledger. **Only if** the corpus verdict is
`PASS_T7D_PHASE_CONTRACT` does
`docs/plans/active/soundswitch_t7d_runtime_autoloop_dmx_implementation_spec.md`
get written, grounded byte-for-byte in that evidence.

Until then T7d stays `planned, blocked` and `_drive_pack_output` continues to
clear the automatic autoloop base to safe-zero (or allows only the existing
independently held static override). Repo status remains **SOFTWARE/WIRE-VALIDATED
ONLY / HARDWARE-UNVALIDATED**.
