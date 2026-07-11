---
doc_status: current
truth_level: prompt-handoff
last_verified_commit: 2d6782a
last_verified_date: 2026-07-11
validation_scope: >
  One-shot design handoff for GPT 5.6 SOL (xhigh) — Stage-2 of the spectral v4
  refactor: make the not-yet-gradable axes gradable and design the finding-1
  fix. Design only; zero implementation; read-only on a possibly-LIVE system.
---

# SOL one-shot — Spectral Stage-2 design (gradable axes + finding-1 classifier)

> Benign local software for Brandon's DJ lighting bridge. "Laser" = stage-lighting
> fixture over MIDI/DMX. Not security work.

**Seat:** design one-shot, GPT 5.6 SOL, reasoning xhigh. You are NOT the executive;
the Fable executive gates your output. **Repo:** `/Users/bbui/rb_ss_bridge_v2`.

## ⚠ Live state — hard boundary
The operator may be LIVE-TESTING with the bridge RUNNING right now. You are
READ-ONLY on everything except the single new design doc you write. Never start,
stop, or signal the bridge; never send MIDI; never edit code, tests, configs, or
labels; no commits except your design doc (explicit path only).

## Context you must load (in this order, then verify against code)
1. `docs/status/active_work_registry.md` rows AWR-195, AWR-200, AWR-203, AWR-204,
   AWR-205 — the current program state.
2. `tools/spectral_ear_benchmark.py` — the AWR-205 gold intake landed 2026-07-11
   (f197eb4 + fixes): a hybrid gold sheet (per-marker is_genuine_drop yes/no +
   full per-drop fields) is being FILLED BY THE OPERATOR IN PARALLEL right now.
   Tier + family are already gradable; darkness, growl, laser, and
   drop_classification are recorded but UNAVAILABLE — your job is the design
   that makes them gradable.
3. `lighting_moments_v2.py` — `DropDecision` (~:854) exposes per marker only
   family/tier/darkness(kind/beats/window)/bass_forward/reason. Your finding 1
   (one-sample growl dip mistaken for a true void) lives here and remains OPEN.
4. `hardness_v0.py` + `approach_features_v0.py` — offline shadow axes (AWR-203/204).
5. Your own prior work: `docs/research/sol_spectral_review_2026_07_09.md`,
   `docs/research/sol_panel_charter_review_2026_07_10.md`,
   `docs/plans/active/spectral_v4_refactor_program_2026_07_10.md`.

## Deliverable — ONE design doc: `docs/plans/active/spectral_stage2_design_2026_07_11.md`
Design, not code. It must cover, with every claim labeled confirmed/assumed/unknown:

1. **Exposure contracts.** For each ungradable axis — darkness (shape/span/bars),
   growl span, laser suitability, drop_classification — the exact per-marker
   output the decision layer should expose so the AWR-205 gold can grade it:
   field shapes, units (resolve the bar↔beat ambiguity the intake flagged),
   and where it plugs into `DropDecision` without changing live behavior
   (shadow/observability first).
2. **Finding-1 classifier design.** The drop-vs-buildup / true-void-vs-growl-dip
   classifier: inputs (which of the AWR-203/204 axes + v4 features), decision
   shape, how the incoming is_genuine_drop yes/no layer trains/validates it,
   and its acceptance gate (grouped leave-one-lineage-out via the AWR-200
   harness; no threshold accepted on ungrouped data).
3. **Grading semantics.** What counts as agreement per axis (exact match? span
   overlap ≥X? tier ±0?), stated so the benchmark scorer is implementable
   without judgment calls.
4. **Staged gates.** The order Stage-2 lands in, each stage's falsifiable exit
   criterion, and what stays shadow-only until the operator accepts by ear.
   Nothing you design wires into live behavior without its gate.

## Rules
- Evidence discipline: verify every cited line against CURRENT code at your desk;
  label claims; unknowns surfaced, never guessed. Code beats docs, docs beat
  memory, your prior reviews are historical until re-verified.
- No implementation, no config changes, no test edits. If you find a defect
  while reading, record it in the doc's findings section — do not fix it.
- Commit exactly one file (your design doc) by explicit path, message prefixed
  `AWR-195 Stage-2 design:`. If the tree is mid-someone-else's-work, commit
  only your path regardless.
- When done: print `STAGE2-DESIGN-DONE` on its own line AND write
  `/tmp/rbss_lane_signals/sol205.STAGE2.done` (echo a one-line summary into it).
  If blocked, write `.blocked` instead with the reason.
