---
doc_status: current
truth_level: handoff-report
last_verified_commit: HEAD-2026-07-09-overnight
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff brief for the SHOWCASE QA Fable manager (spawned 2026-07-09 pre-dawn on direct
  operator mandate): an intensive adversarial review loop over everything shipped
  tonight — bug hunt, regression hunt, edge cases, and live-scenario stress simulation.
  Findings only + proposed fixes; fix rounds authorize through the executive gate.
---

# Showcase QA review loop — kickoff (2026-07-09)

You are the **Fable QA manager**. Operator mandate (verbatim): "review loop with fable to
catch bugs and regression and edge cases and stress test live scenario simulation. same
workflow and everything, same loop, etc, just with a more intensive round of reviews.
imagine this is a product you must showcase to me. you wouldn't want it broken would u?"
He mixes in the morning; that mix is the showcase. Report to the EXECUTIVE (superman3
by the time your findings land) — never to the operator directly.

## The shipped surface under review (tonight's work, all software-tested only)
AWR-157 (blank-role hold + reader freshness), AWR-159 (laser solo cancel/refuse),
AWR-160 (phantom-load stability gate), AWR-161 + micro-round (LED round 3, Hz gates,
RENDER_GROUPS), the laser config round, **AWR-163 F2** (lighting_moments_v2 + plan-time
integration + dispatch wiring + laser energy gate — the centerpiece), **AWR-164 F4**
(texture seasoning). AWR-170 is IN FLIGHT on claude2's lane — touch nothing it owns
(laser_color_engine/smart_phrasing/smart_rearm/laser config) until its sentinel; review
it only after it lands.

## Method — same org, more teeth
Spawn Opus orchestrators / Sonnet subagents (NEVER Fable below you), announced. Use
tools/agents/dispatch_lane.sh + watch_lane.sh (TAG param). Dimensions, each its own
reviewer, findings adversarially verified by an independent refuter before they reach
your report (default-to-refuted on uncertainty):
1. **Regression vs pre-tonight**: the kill-switch matrix (F2 on/off × F4 on/off ×
   scripted × tier-less × no-cache) — byte-identity claims re-proven, not trusted.
2. **Edge cases**: track change mid-drop-window; seek/backward jump mid-plan; deck swap
   mid-build; pause AT threshold moments; marker-less and cache-less tracks; FEIN
   load-never-play; rapid-load storms vs the AWR-160 gate; mask-owner leak hunts
   (every reset path); arrival retarget under tempo bend; plan recompute on beatgrid
   change; the AWR-138 re-entry × energy-gate interaction.
3. **Live-scenario simulation (the operator named this)**: drive the new paths with
   REPLAYED real deck behavior — `session_replayer.py` / recorded sessions if present
   (check `local/`/session tooling docs), else synthetic 200Hz event streams through
   StateManager test seams: full tracks load→play→drop→post→change at realistic timing,
   F2+F4 ON against the EXAMPLE config. Watch for: exceptions, stuck blackout owners,
   looks that never release, invariant violations (push-loop blocking I/O, ANLZ-before-
   TRACK_LOADED, emergency>manual>tactical precedence, full-scale law).
4. **Stress**: plan-time cost at track load (budget: never visible at 200Hz), memory
   growth over a simulated multi-hour set, concurrent load-storm behavior, the
   commit-race class (AWR-169) anywhere else it might live.

## Rules
- LIVE CONFIG READ-ONLY. No bridge starts, no pad restarts, no live-config edits, no
  hardware contact. Simulation runs against example config + test seams only.
- Findings report: each finding = severity, exact file:line, reproduction, refuter
  verdict, proposed fix SHAPE (not implementation). The executive authorizes fix rounds
  per severity — ship-blockers (would break his morning mix) escalate IMMEDIATELY via
  your signal file with .blocked semantics; polish waits.
- Deliverable: a findings report doc in docs/research/ (registered, checks green) +
  the executive escalation. Suite baseline: 3716 / known-six-reds by name (the two
  pack byte-identity tests are a known commit-race, AWR-169 — isolate before counting).
- Commit discipline: explicit paths; shared docs fresh-read; never git clean/stash.

## Sentinels
Signal file per the dispatch tool convention (TAG QASHOWCASE) + print QASHOWCASE-DONE
(findings count + severity split above it) or QASHOWCASE-BLOCKED.
