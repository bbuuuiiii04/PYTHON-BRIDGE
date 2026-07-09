---
doc_status: current
truth_level: manager-state-brief
last_verified_commit: d93f047
last_verified_date: 2026-07-09
validation_scope: >
  Live state brief for the QA-minors manager seat (Fable/HIGH, tmux qaminors, AWR-179).
  Updated as milestones land. A successor seat boots from this file + the AWR-179
  registry row + the spec.
---

# QA-minors manager — seat state (AWR-179)

## Mission
Clear the six CONFIRMED MINOR findings from AWR-172 in ONE gated round:
spec → Opus implementer → manager adversarial review → executive gate (tmux superman3).
Kickoff: `docs/prompts/active/qaminors_kickoff_2026_07_09.md`. ZERO runtime contact
(live session running; the operator's override does not extend to this lane).

## Scoreboard
- [x] Kickoff + AWR-172 row + findings report read fully.
- [x] All six findings re-verified at HEAD `d93f047`:
  - D2-F2 ALREADY FIXED at HEAD (`f95a53b`: F2 plan attach hoisted out of
    `markers_changed` + 2 regression tests in `tests/test_smart_transitions.py`) —
    dropped from the round, evidence in the AWR-179 registry row.
  - D2-F1, D4-F1, D4-F2, D4-F3, D4-F4 confirmed present; symbol-anchored cites in the spec.
- [x] Pre-round baseline suite at manager desk (`d93f047`, repo root): 3812 tests,
  4F/6E — the five NAMED environmental reds reproduce, PLUS 5 NEW errors:
  `test_laser_color_engine.LaserColorStateManagerHoldTests` (all 5) —
  `_FakeLEDColorEngine` lacks `v2_darkest_rgb`, called by the CFX lane's
  `_compute_led_cfx_sweep`; landed via `967ea15` 12:31 (commit-race sweep).
  TEST-HARNESS-ONLY (real engine has the method, `led_color_engine.py:1281`).
  Owned by CFX/ledtune workstream. MUST be reported at the executive gate.
- [x] Spec authored: `docs/plans/active/awr179_qa_minors_cleanup_spec.md`
  (renumbered from 175 — the F3 design lane holds AWR-175 per `doc_index.md:48`).
- [x] Registry row AWR-179 inserted.
- [x] Build lane DISPATCHED: tmux `claude11`, Opus/high, tag QM179, dispatch via
  `dispatch_lane.sh` (model pin verified by script), paste-chip check clean.
  Signals: `/tmp/rbss_lane_signals/claude11.QM179.done|.blocked`. One watcher armed
  (signal-file-first).
- [ ] Build complete (5 commits, one per finding; D2-F1 LAST + droppable).
- [ ] Manager adversarial review at this desk: re-run new tests, read every diff,
  re-check each finding's original repro, diff commit stats vs spec file fence,
  full suite reconcile BY NAME (expect the 10 named in spec Part E item 3).
- [ ] Executive gate at superman3 (explicit D2-F1 ruling — droppable by reverting the
  last commit). Report the laser_color_engine baseline divergence there too.
- [ ] Registry row updated to round outcome; completion signal
  `touch /tmp/rbss_lane_signals/qaminors.QAMINORS.done` + sentinel.

## Key design rulings baked into the spec (don't re-derive)
- D2-F1 = EARLY LEVEL DEACTIVATION in `smart_phrasing.py` (:411-414 condition gains a
  lower bound `beats_to_next_drop > transition_release_beats`), riding the EXISTING
  falling-edge `transition_mask_should_clear`. NOT a shortened window length (that would
  move the darkness START — wrong direction). Fail-open: releases early, never darker.
- D4-F2 = `BoundedSemaphore(2)` inside the worker + stale-gen early-exit; keep daemon
  threads; NO ThreadPoolExecutor (interpreter-exit join risk).
- D4-F3 = read-once-thread-through; NO lru_cache (long-lived caller staleness).
- D4-F1 = commit mismatch demoted to warning; freshness/branch/artifact gates keep
  failing safe; contract-first: tool added to led_govee code_globs.
- D4-F4 = pop prior-gen key on track_changed; one-line 2.0s prune in `_arm_scripted`;
  512-cap clear on `_v2_bloomed` (re-bloom is a benign claim-ranked color breath).
