---
doc_status: current
truth_level: implementation spec for the V2IMPL lane (AWR-195 laser path) — offline tooling only
last_verified_commit: a379740b
last_verified_date: 2026-07-17
validation_scope: >
  Offline detector tooling under gitignored local/. No bridge runtime, laser,
  LED, or config behavior changes. SOFTWARE-VALIDATED ONLY when done.
---

# Implementation Spec — laser drop-span detector v2 (V2IMPL)

## Part A - Context (verified; read, do not re-design)

- [confirmed] Design authority: `local/laser_detector_v2_2026_07_17/sol_design.md`
  (GPT-5.6 Sol xhigh, gated PASS by the Fable orchestrator 2026-07-17). It
  specifies the full algorithm, constants, output record, and validation
  protocol. Implement it EXACTLY; where it marks [unknown]/fallback, implement
  the stated fallback. You make ZERO design decisions — if the design is
  ambiguous or contradictory somewhere, STOP and write the blocker signal.
- [confirmed] Ground truth: `local/laser_drop_spans_2026_07_16/review_verdicts.jsonl`
  (+ `review_verdicts_summary.md`) — 27 yes / 21 no / 2 skip + 4 volunteered
  positives; corrections verbatim.
- [confirmed] v1 reference machinery (data path, beatgrid, drop anchors):
  `local/laser_drop_spans_2026_07_16/drop_span_hunt.py` (pyrekordbox on the
  scratch `master_copy.db`, ANLZ drops, strict v4 cache) and
  `local/spectral_night_2026_07_16/evidence_pack.jsonl` (1,665 TRUE drops).
- [confirmed at gate] Cache support for the design: `sub4` quarter-beat series
  (spectral_cache.py:238-300, V4_SUB4_KEYS), `growl_band_frames` frame-rate
  60-500 Hz harmonic envelope (audio_spectral_features.py:84), stock
  `sustained_synth_flags` (spectral_profile.py:252).
- [confirmed] I Cannot's 0:28 marker is operator-rejected; its TRUE drops are
  1:19/3:00 (already handled in v1's sweep — reuse that substitution).

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Write ONLY under `local/laser_detector_v2_2026_07_17/`. No repo file edits,
  no tests/ additions, no imports FROM the new code into any runtime module.
  Read-only everywhere else. Never touch the live rekordbox master.db, bridge
  runtime, configs, or pad/lab/sim services. No git commits, no branches; the
  worktree may be dirty with other seats' work — never revert or clean anything.
- Error handling: fail closed and loud. A track/drop that cannot be measured is
  reported in coverage output with a reason — never silently skipped, never
  guessed. No broad try/except around the algorithm core.
- Constants: one module, names and values exactly as sol_design §4. Only the
  four grid-tunable constants may vary, only inside the evaluator's LOTO loop.

### Task 1 - `local/laser_detector_v2_2026_07_17/detector_v2.py`
Implement sol_design §2-§5: primitive generators (growl_continuous,
synth_continuous, stab_burst), honest core segmentation (§5.2 pseudocode),
quarter-slot stab masks (§5.3), local arrival gate (§5.4), motif matcher +
on/rest/on grouping (§5.5), synth/vocal/fakeout gates (§5.6), wall-of-sound
risk (§5.7), character labels (§5.8), score + decision (§5.9). The algorithm
core must be pure functions over in-memory feature arrays (no disk/DB access
inside them); a thin loader reuses drop_span_hunt.py's resolution path.

### Task 2 - `local/laser_detector_v2_2026_07_17/evaluate_v2.py`
Implement sol_design §6 exactly: immutable correction table built first
(§6.1, transcribed from review_verdicts.jsonl; low_confidence flags per §6.1),
leave-one-track-out over the 81-combination grid (§6.2), matching + metrics
(§6.3), pass/fail gates (§6.4 incl. every mandatory shape/rejection gate by
item number), residual-disagreement listing (§6.5).

### Task 3 - Run
1. Self-tests (Task 4) green.
2. Full evaluation → `validation_report.md` (every §6.4 gate PASS/FAIL stated
   explicitly, metrics with intervals, per-track accuracy, residuals).
3. Full-library sweep over all TRUE drops → `candidates_v2.jsonl` +
   `candidates_v2_top.md` (top 40 per decision=detect by score, character
   labels shown; review-decision items listed separately) + `coverage_v2.json`.
   Run the sweep regardless of gate outcome, but the top-list header must state
   the gate verdict honestly.

### Task 4 - `local/laser_detector_v2_2026_07_17/test_detector_v2.py`
Pure-function unit tests: synthetic feature arrays exercising (a) taper ends
core at DECAY_DB drop with END_CONFIRM=2, (b) 1-beat holes preserved / 2-beat
rest splits records, (c) 16-beat cap + continues_after_core, (d) stab-burst
quarter-mask detection incl. the 3-of-4-bars cadence path, (e) arrival window
0..+8 with +9 excluded, (f) item-30 3-beat exception requires score>=7, (g)
motif distance threshold, (h) fakeout rule prefers later growl. Runnable via
`python3 -m unittest` from that directory. Do NOT touch the repo suite.

## Part C - Invariants that must still hold
- Zero runtime imports of the new code; `python3 -m unittest discover tests`
  from repo root shows the same baseline as before your run (do not run the
  full suite more than once; reconcile by name if reds appear).
- `git status` shows no changes outside `local/` when you finish.
- Laser/LED/SS behavior unchanged (nothing you write is imported by them).

## Part D - Tests
Task 4 is the required seam. The evaluator itself must expose its matching
logic as pure functions covered by at least two of the unit tests.

## Part E - Acceptance (definition of done)
- [ ] detector_v2.py + evaluate_v2.py + test_detector_v2.py + constants module exist; self-tests green.
- [ ] validation_report.md states every sol_design §6.4 gate with PASS/FAIL and numbers.
- [ ] candidates_v2.jsonl / candidates_v2_top.md / coverage_v2.json produced; coverage lists every excluded drop with reason.
- [ ] No repo diffs outside local/; no commits made.
- [ ] SEAT_REPORT.md: what was built, deviations (should be none), gate verdicts, honest limits.

## When You Finish
Signal exactly: `touch /tmp/rbss_lane_signals/v2impl.V2BUILD.done`
(blocked: `echo "<reason>" > /tmp/rbss_lane_signals/v2impl.V2BUILD.blocked`).
Print V2BUILD-DONE (or V2BUILD-BLOCKED) on its own line. Run straight through.
