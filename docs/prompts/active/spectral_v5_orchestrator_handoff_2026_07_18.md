---
doc_status: current
truth_level: orchestrator seat handoff — spectral v5 program (context-limit rotation)
last_verified_date: 2026-07-18
validation_scope: >
  Seat-state transfer only. Everything referenced is SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED. Nothing here authorizes live behavior changes.
---

# ORCHESTRATOR HANDOFF #3 — spectral v5 (2026-07-18, ~11:30)

You are the NEW Fable 5 orchestrator (orchestrator3), replacing orchestrator2
(context-rotated at operator order). Brandon talks to YOU now. Durable truth
lives in the files named here — read them, never trust summaries over disk.
ALL working artifacts: `local/spectral_v5_2026_07_17/` (gitignored).

## 0. Who you are / how this runs
- You are the executive gate-holder. You NEVER edit code. You author specs,
  dispatch tmux lanes, adjudicate with evidence, gate results, keep memory
  current, and present EVERYTHING fully in chat (Brandon refuses documents).
- GPT-5.6 Sol xhigh (tmux `codex`) = peer brain: hostile reviews, designs,
  adjudications — never implementation. Currently running SANDBOXED
  (`codex -c model_reasoning_effort="xhigh"` — the auto-classifier blocks the
  bypass flag from our shell regardless of chat grants; approve Sol's
  file-write prompts in-pane). /clear codex before EVERY new Sol task; briefs
  must be self-contained (no session memory). Verify paste-chip landed before
  Enter; capture-pane after every send.
- Implementation lane: tmux `v2impl` (Claude Opus xhigh, bypass perms) — ALSO
  context-rotating: its self-written resume doc is
  `local/spectral_v5_2026_07_17/stage2_lane_resume.md` + signal
  `v2impl.HANDOFF.ready`. YOUR FIRST LANE ACT: once that signal exists, /clear
  v2impl and boot the fresh lane from the resume doc (it inherits bypass
  perms; paste-chip discipline applies).
- Signals: `/tmp/rbss_lane_signals/<seat>.<TAG>.done|.blocked`. Watch with
  persistent Monitors that fire on the signal files (never rely on a lane
  ending its turn — lanes have stalled silently; also watch workspace-write
  staleness ~40 min). Approve stuck CLI permission prompts in-pane (one cost
  us 54 min).
- Operator grants (all recorded in memory + sweep_authorization_record.md):
  overnight/day machine autonomy; "APPROVE IT. AND MAKE IT RUN FASTER THAN 28
  HOURS" (sweep launch + speed); allowed to launch parallel/multiple tmux
  sessions for codex AND claude. Operator style: safe defaults + veto-only
  asks, full info in chat, humble reporting, no re-asking settled things.

## 1. Program endpoint (operator charter — verbatim intents in memory)
Deliverable #1: "a fresh list of songs with laser warranted growls and
sustains", scored from stem evidence, calibrated against his 50 ear-verdicts
(`local/laser_drop_spans_2026_07_16/review_verdicts.jsonl`, 27y/21n).
Charter beyond that: spectral analysis as a general per-track intelligence
platform ("point AI at a characteristic → cues"), auto-analysis of new
rekordbox imports (ruled "should be automatic" — build AFTER the list).
Deferred, never re-raise: C1 crack, exemplar handles, A2 batches, lab drafts.

## 2. State RIGHT NOW (2026-07-18 ~11:30)
- **SWEEP RUNNING (serial)**: 723 tracks under `stage2_sweep_spec.md` (hash
  40616be5…, 11 Sol rounds, READY-EXCEPT-OPERATOR-GATE; operator gate closed
  by `sweep_authorization_record.md`). V12 bit-5-free config `01bcb1d08ca5d97e`.
  ~100 s/track measured → ~20 h serial. Journal-driven, per-track atomic,
  crash-proof resume, `sweep_progress.md` every 50 tracks, in-sweep projection
  guard (track 50/every 100, abort > 48 h). Signals `v2impl.V5SWEEP.done|.blocked`.
- **PARALLEL SPEED-UP GATED**: Sol post-hoc review
  (`sol_posthoc_amendments_review.md`) RATIFIED the cost-evidence acceptance
  but CONTESTED the 2-child pool (real gaps: single-group RSS guard, disk
  double-admission, thermal race, journal races). Lane is building Sol's
  five-item minimum gate → signals `v2impl.V5POOL.ready` → dispatch Sol
  hostile check of the implementation → only then admit the second child
  (mid-run switch is safe; expect remainder ~2× pace). The operator's speed
  order STANDS — finish this.
- **Stage-2 science ledger** (reports: stage2_pilot_report.md,
  stage2_fix_report.md, stage2_v12_report.md): GATE-2 PASS (official, v12),
  GATE-3a PASS, A2 PASS (0 regressions, ST40, LIFT=0 honest), GATE-5 PASS;
  GATE-1 INSUFFICIENT (frozen, never tune); GATE-3 FAIL (v11 bleed warning
  REJECTED + withdrawn — vocal_copy_gain is descriptive-only, real leakage
  detector deferred to a source-truth research arc needing ground-truth
  stems); GATE-4 INSUFFICIENT by construction (categorical-label ban).
  Verdict FAIL(GATE-3) stands honestly; sweep is measurement-only/not
  promoted. Cost: run1 formally-gated median 100.035 s/track = 27.79 h/1000
  (append-only stage2_cost_history.jsonl); two-pass ritual never completed
  (machine can't hold two ≤2.0 windows while hosting agents) — operator
  accepted the evidence.
- **Protected**: Stage-1 promoted evidence (11/11, extractor v2.1.0) under
  pre/post hash inventory; 96 promoted tests; pilot payloads all retained.

## 3. Rulings ledger (uphold; documented in specs/records)
Q1 Resolution A; PICK_WINDOW_MS 30; segment_size 7 (v8); memory guard
5.5/6.0 GB (v9, operator "lift the gb ceiling"); spec_utils.normalize
identity-patched (v10 — the wrapper clamps supra-unity stems); bit-5
withdrawn system-wide (v12); condition-3 amendment (warning not a sweep
gate); condition-4 amendment (accepted run1 evidence + in-sweep guard);
2-child pool gated on Sol's five items. Sol's operator-gate contest +
override are documented in sweep_authorization_record.md (never silent).

## 4. Your queue (in order)
1. Boot: memory auto-loads → verify tmux seats (`v2impl`, `codex`) → check
   `/tmp/rbss_lane_signals/` for v2impl.HANDOFF.ready, V5POOL.ready,
   V5SWEEP.* → arm Monitors (sweep signals + sweep_progress.md staleness) →
   rotate the v2impl lane from its resume doc when HANDOFF.ready exists →
   confirm to Brandon in one line, print V5ORCH3-OK, touch
   /tmp/rbss_lane_signals/orchestrator3.V5BOOT.done.
2. V5POOL.ready → Sol hostile check (self-contained brief; cite
   sol_posthoc_amendments_review.md §minimum-gate) → if clean, order the
   lane to admit the second child; report the new ETA.
3. Track-50 checkpoint → report BOTH numbers to Brandon (frozen serial cost
   comparand vs 48 h; actual pool ETA vs his 28 h order).
4. DURING the sweep: author the SCORER spec (detector v3 on stem evidence;
   spans of sustained bass/other harmonic content + growl-purity features;
   calibration = frozen evaluation against the 50 verdicts via the promoted
   Stage-0 evaluator, lineage-isolated; NO threshold tuning on the verdict
   corpus without holdout discipline — Sol designs/reviews). Sol-review it
   to READY so the build starts the moment the sweep lands.
5. Sweep done → gate the report (reconciliation, coverage, baseline diff) →
   scorer build lane → calibrate → present THE LIST in chat (target Sun-Mon).
6. Post-list: auto-import automation spec; source-truth detector arc;
   platform charter work. All operator-ruled, all in memory.

## 5. Boot protocol
Run straight through; never idle at checkpoints. Brandon's next message may
be anything — the program continues regardless. FIRST message to Brandon:
one-line seat confirmation + current sweep progress (read sweep_progress.md
+ journal tail), then V5ORCH3-OK on its own line, then touch the boot signal.
