---
doc_status: current
truth_level: implementation spec for the V5STAGE01 lane — offline tooling only (spectral v5 Stages 0+1)
last_verified_commit: a6ef4120
last_verified_date: 2026-07-17
validation_scope: >
  Offline analysis tooling under gitignored local/. No bridge runtime, laser,
  LED, or config behavior changes. SOFTWARE-VALIDATED ONLY when done.
---

# Implementation Spec — spectral v5 Stage 0 + Stage 1 (V5STAGE01)

## Part A - Context (verified; read, do not re-design)

- [confirmed] Design authority: `local/spectral_v5_2026_07_17/sol_program_design.md`
  (Sol xhigh, gated), amended by
  `local/spectral_v5_2026_07_17/fable_gate_reconciliation.md` (amendments
  A1-A4; A2 affects Stage 1's schema: window records must be re-runnable
  against stem inputs later without schema change). Research context:
  `local/spectral_v5_2026_07_17/sota_research_report.md`.
- [confirmed] You built detector v2 + its evaluator; Sol's review of your work
  is at `local/laser_detector_v2_2026_07_17/sol_review.md`. Stage 0 is the
  permanent, repaired successor of that evaluator lineage per design §8.
- [confirmed] Verdict corpus + v1/v2 artifacts as before; scratch DB at
  `local/laser_drop_spans_2026_07_16/master_copy.db`.

## Part B - Tasks (implement exactly; design §§3,4,7,8,9 are the authority)

### Absolute Rules
- Write ONLY under `local/spectral_v5_2026_07_17/` (code in `pipeline/`,
  cache under `spectral-cache/v5/` INSIDE that dir for now). Read-only
  everywhere else; no runtime imports; no commits; no branches; never touch
  the live rekordbox DB or any bridge/laser/LED/pad service. Fail closed and
  loud; no broad try/except in algorithm cores.
- Stage 1 uses ONLY stdlib + numpy/scipy/soundfile/librosa-class deps already
  importable locally — check what exists before assuming; if a needed audio
  decode path is missing, STOP and signal blocked rather than pip-installing
  into the system environment.

### Task 1 - Stage 0: label store + evaluator foundation (design §7.1, §8.1)
`pipeline/label_store.py`: append-only JSONL event store exactly per the §7.1
schema (content_id sha256 of audio bytes, lineage registry, supersedes/
tombstone semantics, resolver as separate projection). Import the existing
corpus ONCE with correct provenance (`legacy_selected`, `volunteered`,
`scripted_existing`).
`pipeline/evaluator.py`: three explicit report lanes (`development_cv`,
`frozen_diagnostic`, `locked_future`), three-way outcomes with abstention
accounting per §8.1, track-group bootstrap CIs, full auxiliary-span coverage,
artifact-hash on every metric row. Golden-failure fixtures: deliberately
faulty inputs MUST fail the right gate (§8.2 prerequisite-0 row).

### Task 2 - Stage 1: high-resolution transient extractor (design §4, all of it)
`pipeline/transients.py`: dual-branch STFT extraction, channel views, band
prominence/flux_z/attack_ms per §4.1 formulas, proposal thresholds as written
(3.0 dB floor — the 6 dB floor is FORBIDDEN for the item-40 gate), storage
per §4.2 schema (npz + manifest with every §3.3 manifest field), float16 only
after the §4.2 float32-equivalence pilot gate passes, candidate windows per
§3.1, identities per §3.2. Algorithm core = pure functions over arrays.

### Task 3 - Stage 1 gates (design §4.4) — run and report
`pipeline/stage1_gates.py` + run: item-40 representability gate (both stabs,
±100 ms, locked reference timestamps you derive from the corpus correction),
synthetic weak-injection gates (3/4/6/10 dB, ≥95% recovery of 3-4 dB within
50 ms, p90 ≤30 ms, no double-fire), negative-window inflation gate (≤25% vs
6 dB floor), cost recorder (wall-s/track, peak RSS, cache bytes vs §4.3
budgets). Then run the full-corpus extraction over all true-drop windows
(735 tracks) and write `stage1_report.md` with every gate PASS/FAIL + budgets
measured-vs-provisional.

### Task 4 - tests
`pipeline/test_v5_stage01.py`: pure-function tests for label-store append/
supersede/tombstone/lineage-grouping, evaluator three-way accounting +
golden failures, transient peak/merge/prominence math, and the injection
harness. Runnable standalone via unittest. Repo suite untouched.

## Part C - Invariants
- Zero runtime imports of anything under `pipeline/`; repo `git status` clean
  outside `local/` at finish; bridge dependency files unchanged.

## Part D - Tests
Task 4 is the seam; evaluator matching logic pure and covered.

## Part E - Acceptance
- [ ] Stage 0 golden-failure suite green (faulty fixtures fail correctly).
- [ ] Stage 1 gates all stated PASS/FAIL with numbers in stage1_report.md;
      full-corpus extraction coverage listed with per-track failure reasons.
- [ ] Measured budgets reported against §4.3 provisional budgets.
- [ ] SEAT_REPORT_V5.md: built/deviations/limits, plain-language summary.
- [ ] No repo diffs outside local/; no commits.

## When You Finish
Signal exactly: `touch /tmp/rbss_lane_signals/v2impl.V5STAGE01.done`
(blocked: `echo "<reason>" > /tmp/rbss_lane_signals/v2impl.V5STAGE01.blocked`).
Print V5STAGE01-DONE / V5STAGE01-BLOCKED on its own line. If a design
ambiguity is load-bearing, STOP and block with the precise question — that
served us well last time.
