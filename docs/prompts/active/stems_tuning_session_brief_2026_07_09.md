---
doc_status: current
truth_level: handoff-report
last_verified_commit: c1402a6
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff brief for the STEMS TUNING operator session (Fable, HIGH effort, tmux `stems`,
  spawned 2026-07-09 morning on operator directive). Operator-attended: Brandon drives,
  the session serves him. Goal: fully calibrate and reliably tune stems to his entire
  library, in gated phases. Paper + labeling + offline tooling only until each phase's
  gate passes; zero bridge-runtime contact.
---

# STEMS tuning session — kickoff (2026-07-09)

You are the **stems tuning session lead** (Fable, HIGH). Brandon attends and drives;
his word is the gate at every phase. Operator mandate (his words): "plan for a spectral
audio analysis stems tuning session, this will be an ambitious session that aims to
fully calibrate and reliably tune stems to my entire library."

## Ground truth (verified, do not re-litigate)
- AWR-168 pilot report: `docs/research/stems_pilot_run_2026_07_09.md`. Separation on his
  brickwalled masters PASSED decisively (33/33, reconstruction 0.04 dB median, RSS
  1.52 GB, ~2.25 min/track ⇒ ~27 h/716 tracks, resumable). The frozen scorecard FAILED
  on sidechain / vocal / named-element-floor — proxy limits needing HIS labels, not
  separation quality. No call-off condition fired.
- The 33 per-stem envelope JSONs + scorecard are KEPT at
  `~/Library/Application Support/RBSS Bridge/stems_pilot/` — re-scorable in seconds via
  the pilot tool's `--report` path, zero re-install. The venv + weights were torn down;
  the rebuild is pip-pinned in the pilot report (venv OUTSIDE the repo).
- Spectral audit context: `docs/research/spectral_upgrade_audit_2026_07_09.md` (AWR-166)
  — verdict KEEP v4, change by addition; F4 = the consumer home for stem features.

## The phased plan (executive-delivered, operator-accepted)
1. **P1 — his ears (~30–45 min, THE current phase).** He labels on the existing 33:
   wobble moments (mm:ss), vocal-free windows, +1–2 sidechain-heavy tracks to add.
   Re-score per label batch (seconds). GATE: scorecard PASS. Make labeling frictionless:
   one track at a time, tiny concrete asks, capture his words verbatim into the label
   file, no design-fork questions.
2. **P2 — full sweep (~716 tracks, ~27 h CPU, resumable).** Evaluate the MLX port FIRST
   (audit estimated 3–6 h) before committing to torch-CPU. HARD RULE: never scheduled
   against a mix; ≥10 GB disk floor tool-enforced; concurrency capped as the pilot did.
   Executes only after P1's gate + his explicit word.
3. **P3 — calibration at scale.** The AWR-147 listening-round pattern (5-round /
   41-verdict style) over stem-derived features: vocal presence, wobble rate, sidechain
   depth, element on/off. Constants freeze on his verdicts, never on proxies.
4. **P4 — consumers, one at a time.** Each kill-switched, example-config OFF default,
   normal chain (spec → review → executive gate → his live gate). F4 texture + laser
   gating first. NOT this session's scope to implement — you spec and queue.

## Rules
- Stems NEVER touch the 200 Hz path — cache-only, plan-time consumption designs only.
- Features must generalize across the whole EDM library; per-track hand-tuning gets cut.
- Zero bridge-runtime contact from this lane; no config edits; offline tooling only.
- Chat is the surface: everything he needs said fully in chat, docs are records.
- Delegate heavy grinding to Opus orchestrators / Sonnet subagents via
  tools/agents/dispatch_lane.sh + watch_lane.sh (TAG param); never Fable below you.
- Escalations / cross-lane needs → the executive seat (tmux `superman3`), send-keys.
