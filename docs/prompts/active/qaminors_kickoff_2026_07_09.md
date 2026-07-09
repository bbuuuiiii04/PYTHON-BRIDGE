---
doc_status: current
truth_level: handoff-report
last_verified_commit: d106492
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the QA-MINORS cleanup manager (Fable/HIGH, tmux qaminors, final Fable
  afternoon 2026-07-09): one gated round clearing the six confirmed MINOR findings
  from the AWR-172 showcase QA program. Full chain: spec -> Opus implementer ->
  adversarial review -> executive gate.
---

# QA minors cleanup — kickoff (2026-07-09)

You are the **QA-minors manager** (Fable/HIGH). The AWR-172 registry row carries six
CONFIRMED MINOR findings with file:line + refuter verdicts (source of truth — read it
plus `docs/research/qa_showcase_review_2026_07_09.md`). Clear them in ONE scoped
round through the normal chain.

## The six (verify each at HEAD before speccing — the tree moved all day)
1. D2-F1 `abort_at` computed-never-consumed (`lighting_moments_v2.py`) — the F2
   early-darkness-release the docstring claims. ⚠️ BEHAVIOR-AFFECTING: wiring it
   changes pre-drop darkness on hard-family collapses (≤3 fewer dark beats when the
   low end returns early). Root-cause fix = wire it as designed; ship it as part of
   F2's existing config surface (F2-off ⇒ untouched) and NAME the behavior delta in
   the registry + a pinned test. The executive gate will rule on it explicitly —
   spec it so it can be dropped from the round without unraveling the rest.
2. D2-F2 plan reassignment gated on `markers_changed` not plan-inputs-changed
   (`state_manager.py` — stale darkness/tiers after beatgrid-only re-analysis).
3. D4-F1 `tools/govee_manual_trigger.py` provenance gate hard-aborts on ANY HEAD
   drift within 24h (auto-sync makes drift constant; fails safe but the tool is
   unusable) — fix the mechanism, keep it failing safe.
4. D4-F2 unbounded anlz-worker `Thread().start()` per load (`state_manager.py`) —
   bound it (small pool or in-flight cap; push-loop untouched; cache-miss storms are
   the trigger).
5. D4-F3 pack export double `git rev-parse HEAD` read (`tools/export_soundswitch_pack.py`)
   — read once, thread through; currently inert but it is the AWR-169 class.
6. D4-F4 three per-load structures grow monotonically
   (`state_manager.py` ×2, `led_color_engine.py` ×1) — bound or trim; prove no
   mask/loop consequence in the test.

## Rules
- ONE round, one Opus implementer (dispatch via tools/agents/dispatch_lane.sh), one
  commit per finding, explicit paths. File fence = exactly the files the six name +
  their tests + contract-listed docs.
- Suite acceptance: repo-root, EXACTLY the named five environmental reds (AWR-172
  row names them); three hard checks green; contract-first for anything touching
  led_govee / core_bridge surfaces.
- Your adversarial review re-derives each fix at your desk (run the new tests, read
  every diff, re-check the finding's original repro where one exists) before the
  executive gate (tmux superman3).
- Live session is running: ZERO runtime contact from this lane; the operator's
  override does not extend to you.
- Completion: signal file + sentinel per dispatch convention.
