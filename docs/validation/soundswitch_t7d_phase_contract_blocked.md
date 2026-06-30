---
doc_status: active-validation
truth_level: code-grounded
last_verified_commit: 6c51eb8
last_verified_date: 2026-06-29
validation_scope: T7d blocked report; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# T7d runtime autoloop DMX spec — old six-scenario gate blocked

> Superseded for native Autoloop implementation as of 2026-06-29.
> This file records why the old SoundSwitch-runtime phase proof was incomplete.
> It no longer blocks `docs/plans/active/native_autoloop_dmx_runtime_spec.md`.
> The active native path uses bridge-owned phase, `AUTOLOOP_TICKS_PER_BEAT = 600`,
> `phase_offset_beats`, the offline equivalence oracle, and an operator
> two-flight calibration/A-B run.

Under the old T7d framing, a runtime Autoloop DMX implementation spec could not
honestly be written until SoundSwitch's own hidden phase/origin behavior was
fully proven. That older contract is still incomplete. It has been replaced for
native Autoloop DMX by the bridge-owned phase contract in the native spec.

This is **not** an easy exit: the software workflow exists and four captures
have passed its integrity gate. Remaining work includes physical capture labor
for four scenario pairs plus offline identity reconciliation and oracle analysis.
What is blocked is only the complete old T7d evidence contract, not native
Autoloop DMX implementation.

The 2026-06-29 read-only GhidraMCP pass does not change this blocker. It
confirms SoundSwitch 2.10.3 arm64 Autoloop playback is beatgrid/beat-window/index
based and reaches the shared playback/cache/static/blackout path, but it does
not prove emitted Universe-0 phase, origin, reset/continue/snap/correction, or
identity/holdout coverage for the bridge transition classes. x86_64 parity is
still UNKNOWN.

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
Then update the evidence ledger if the old proof matrix is still useful. Native
Autoloop DMX no longer waits for `PASS_T7D_PHASE_CONTRACT`; current code uses
the bridge-owned native spec instead and remains live/runtime and hardware
unvalidated. Repo status remains **SOFTWARE/WIRE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.
