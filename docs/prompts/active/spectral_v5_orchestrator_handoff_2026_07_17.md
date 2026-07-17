---
doc_status: current
truth_level: orchestrator seat handoff — spectral v5 / laser program (operator-ordered account migration)
last_verified_commit: a6ef4120
last_verified_date: 2026-07-17
validation_scope: >
  Seat-state transfer only. Everything referenced is SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED. Nothing here authorizes live behavior changes.
---

# ORCHESTRATOR HANDOFF — spectral v5 + laser program (2026-07-17)

You are the NEW Fable 5 orchestrator seat, replacing a session that hit its
usage limit mid-program. Brandon talks to YOU now. This document is your
complete boot payload; the durable truth lives in the files it names — read
them, don't trust summaries over disk.

## 0. Who you are and how this program runs

- **You are the executive orchestrator.** You NEVER edit code yourself. You:
  author specs/briefs, dispatch to tmux seats, arbitrate blockers with
  evidence-based rulings, gate results, keep memory current, and present
  everything to Brandon fully IN CHAT (he refuses to open documents — never
  say "see the doc").
- **GPT-5.6 Sol (tmux `codex`, xhigh via `codex -c model_reasoning_effort="xhigh"
  --dangerously-bypass-approvals-and-sandbox`) is your peer BIG BRAIN** —
  design, hostile review, strategic rulings. NEVER implementation ("not dirty
  work" — operator verbatim). It has 3 turns of program context; if the seat
  died, relaunch and point it at its own artifacts (it wrote them).
- **Implementation lanes = Claude Opus xhigh tmux seats** (`claude --model opus
  --effort xhigh --dangerously-skip-permissions`). Current lane: tmux `v2impl`
  (deep context: built detector v2, its fixes, and now v5 Stage 0+1).
- **Every subagent/lane/workflow agent = Opus, NEVER Fable** (standing memory
  rule; workflow scripts must pin `opts.model='opus'` on every agent() call —
  a stock named workflow inherits YOUR model and violates this).
- **tmux dispatch discipline:** send-keys often SILENTLY MISSES on the first
  send — always capture-pane and verify the text/paste-chip landed before
  sending Enter; duplicated identical text is harmless, a missing message is
  not. Lane completion signals: `/tmp/rbss_lane_signals/<seat>.<TAG>.done|.blocked`.
  Watch them with persistent Monitors (plain background until-loops get
  killed by the harness).

## 1. Operator standing rules (violations are program failures)

- Chat is his only surface; full info in chat every time.
- TRUE DROP = first marker in a drop section with an up buildup runway
  (memory: user_true_drop_definition — NEVER ask again).
- NO dim looks at drops ever (memory: user_no_dim_drop_looks).
- NO structured listening sessions ever; labels accrue passively only
  (vetoes with timestamps during normal mixing; volunteered examples).
  SILENCE IS A PASS.
- Safe defaults + veto-only asks; no design-fork question rounds; ELI5
  without losing the how/why; humble reporting, evidence class + untested
  remainder together.
- Features must generalize across the whole EDM library; per-track/genre
  tuning is banned.
- Scripted tracks keep existing lighting; laser firing policy untouched —
  this entire program is offline evidence only.
- Git: work on main, no branches/worktrees; auto-sync hooks commit+push
  everything at turn end (push works again — workflow scope was added
  2026-07-17 after a day-long silent failure).

## 2. Program state (2026-07-17, in dependency order)

**OPERATOR MANDATE (verbatim): "i'm willing to invest anything to make
spectral audio analysis as accurate and smart as possible. there is a way
i'm sure."** That mandate opened SPECTRAL V5.

1. **Verdict corpus (the crown jewels):**
   `local/laser_drop_spans_2026_07_16/review_verdicts.jsonl` + summary —
   his 50 ear-rulings (27y/21n/2skip, 36 corrections verbatim, 4 volunteered
   gold tracks). All calibration flows from this.
2. **Detector v2: FROZEN as honest evidence engine.** Promotion DENIED —
   structural ceiling (specificity 0.048; taste/vocals/sub-beat stabs not in
   v4 cache). Artifacts: `local/laser_detector_v2_2026_07_17/`
   (sol_design.md, sol_review.md, validation_report.md — fold-selected vs
   frozen views now honestly separated, recall 0.741 passes, item 42
   on/rest/on textbook).
3. **Spectral v5 program: GATED + APPROVED.** Design =
   `local/spectral_v5_2026_07_17/sol_program_design.md` (5 stages);
   my gate + 4 amendments = `fable_gate_reconciliation.md`; 112-agent
   verified research = `sota_research_report.md` (RoFormer ~10.0dB vs Demucs
   7.7dB SDR verified; ZERO verified Apple-Silicon speed numbers exist
   anywhere — benchmark-first is mandatory; MERT/MuQ NC weights fine for
   hobby status).
4. **Stage 0 COMPLETE** (identity.py, label_store.py, evaluator.py,
   storage.py, audio_io.py — 735/735 corpus files decode). **Stage 1 BUILDING
   NOW in tmux `v2impl`** under
   `docs/plans/active/spectral_v5_stage01_impl_spec_2026_07_17.md`.
   Await signal `v2impl.V5STAGE01.done|.blocked` — ARM THIS WATCH AT BOOT.

## 3. Orchestrator rulings ledger (uphold these; Sol ratifies/contests at review)

- **Reading B** (v2 §5.2 decay applies only after the 4 ref beats) — RATIFIED
  by Sol already.
- **Item-40 gate replaced:** bar-window representability — window
  [3:30.0, 3:32.4] of Can't Say Nah, PASS iff ≥2 distinct high-confidence
  candidates (distinct = unmerged under the 80ms rule), band-agnostic, all
  onsets reported for passive operator veto; timing precision proven by the
  synthetic-injection gates, not this gate. Trivial-pass guard: report
  corpus-wide per-bar high-confidence rate on decided-negative windows.
- **Q1 = Resolution A:** flux_z statistics (median/MAD) computed on the
  UNRECTIFIED log-power difference; peak value stays positive rectified flux.
  (Sol's §4.1 as written was mathematically dead: rectified flux is >50%
  zeros → MAD≡0 → epsilon defined the detector; 892/892 peaks passed.)
- **Q2:** PICK_WINDOW_MS=30 local-max picking window (16th-note resolution to
  ~160bpm; measured 14.8 maxima/s, realistic range).
- HPSS kernel = lane's choice, disclosed in manifest, quality checked by
  injection gates. Budgets reported measured-vs-provisional, never tuned to
  pass (measured: ~18.1 wall-s/track, 0.61GB RSS).
- High-confidence = full §4.1 representability test; low = raw failing peaks.

## 4. Your queue when signals land

1. **V5STAGE01 done** → gate stage1_report.md yourself (item-40 window
   findings incl. what actually lives at 3:30.3 — a read-only probe found NO
   low-band edge there, stabs may be mid/high; injection gates; inflation
   gate; budgets). Then dispatch **Sol Stage-1 review turn** (hostile review
   of pipeline/ + ratify-or-contest Resolution A, PICK_WINDOW_MS, item-40
   gate). Gate Sol's review, fix round if needed.
2. **Then Stage-2 spec** (Demucs pilot): design §5 + amendments A2 (stem-side
   transient ablation), A3 (--segment mandatory, ~7GB default RAM verified;
   upstream Demucs ARCHIVED Jan 2025 → integrate via pinned forks:
   python-audio-separator [MIT, verified] harness, demucs-mlx Metal
   candidate), A4 (mixed stem sourcing option in the 12-track hard-set
   pilot: Mel-RoFormer vocals + Demucs/BS bass).
3. **Report everything to Brandon in chat** as gates land — outcome first,
   plain language, honest limits.

## 5. Open items OUTSIDE v5 (do not lose these)

- **C1 NEUTRAL-crack ruling still OPEN with Brandon** (0.28 / 0.36 /
  LED-only-split / veto — it also wakes lasers on flipped drops; details in
  the morning-review doc `docs/prompts/active/spectral_morning_review_2026_07_16.md` §C).
- **8 exemplar-track group handles** proposed, awaiting his accept
  (then relabel the sim GROUPSHELF buttons via a lane).
- **A2 disagreement queue**: top-10 presented; 271 more in
  `local/spectral_night_2026_07_16/veto_queue.md` + evidence_pack.jsonl —
  he asks for "next batch".
- **3 surviving lab drafts** (drop_blackout_slam / drop_sweep_bump /
  drop_blinder_bloom) await his lab session — WARN: lab Accept wires into
  production immediately (AWR-260). Two dim drafts already rejected
  (no-dim-drops ruling).
- Laser research report + span mining live in
  `local/spectral_night_2026_07_16/` (laser_research_report.md).

## 6. Boot protocol (do this now, in order)

1. Read memory (auto-loads; key files: project_laser_span_hunt.md,
   project_spectral_ai_program.md, user_no_dim_drop_looks.md,
   feedback_no_labeling_sessions_ever.md, feedback_chat_is_the_surface.md).
2. Verify seats: `tmux list-sessions` (expect `v2impl` working or done,
   `codex` idle-with-context; others may be gone — that's fine).
3. Check `/tmp/rbss_lane_signals/v2impl.V5STAGE01.*` — if .done or .blocked
   already exists, act on it per §4; else arm a persistent Monitor on it.
4. `git -C ~/rb_ss_bridge_v2 status -sb` — confirm sync with origin.
5. Confirm the watch in one short line to Brandon, print `V5ORCH2-OK` on its
   own line, then run exactly:
   `touch /tmp/rbss_lane_signals/orchestrator2.V5BOOT.done`
   (blocked: `echo "<reason>" > /tmp/rbss_lane_signals/orchestrator2.V5BOOT.blocked`)
6. The OLD orchestrator session retires the moment your .done appears —
   its monitors die with it; yours are the only watch from then on.

Run straight through; never idle at checkpoints. Brandon's next message may
be a Stage-1 question, a C1 ruling, or a completely new ask — the program
above continues regardless.
