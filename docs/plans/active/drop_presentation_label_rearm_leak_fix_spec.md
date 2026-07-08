---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (verified at working tree with AWR-140 staged, 2026-07-07; adversarial-review-found)
last_verified_commit: 63c52e0
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex/Subagent Implementation Spec — AWR-140 follow-up: gate the drop-presentation impact on a real marker (label-re-arm leak)

Contract keys: `laser` + `led_govee` (`state_manager.py` drop-presentation tick). **Bug found by the
AWR-140 adversarial review; confirmed by direct code trace.** AWR-140 restored the capped 2nd-chorus
drop re-arm — correct for the drop look — but that re-arm now leaks into the drop-presentation window
and breaks AWR-139's per-true-drop invariant. This is a one-line gate + one test.

## Part A — Context & Root Cause (verified; read, do not implement)

- AWR-140 makes `DropLifecycle.resolve` return `armed_this_tick=True` at the 2nd-chorus label re-arm
  (`drop_lifecycle.py:59-71,91-96`). [confirmed]
- The Laser Director's mirror path emits `LaserSceneDecision(reason="drop_crossing", role="drop")`
  whenever `res.armed_this_tick and previous_abs_beat is not None and self._drop_scene`
  (`laser_director.py:484-494`) — so post-AWR-140 it emits `drop_crossing` at the label re-arm, which
  it never did before (the 2nd chorus used to return `post_drop`). [confirmed]
- `state_manager.py:4550-4552` computes `drop_crossing_decision_emitted = (decision.reason ==
  "drop_crossing")` and passes it as `impact_now` to `_drop_presentation_tick`
  (`state_manager.py:4565-4566`) — with **no cross-check** against `sp_state.smart_drop_crossing`.
  [confirmed]
- At the label re-arm tick `sp_state.smart_drop_crossing` is **False** (the duplicate anlz marker was
  collapsed by AWR-131; only the chorus phrase-start edge remains), but `active_drop_beat` is still the
  true drop beat because `smart_phrasing.py:355-362` keeps it set for `post_drop_beats` (=32 on the
  live "house" personality, `config/laser_director.json`). So within 32 beats of the true drop,
  `_drop_presentation_tick` sets `eval_beat = active_drop_beat` (`:2604`), `plan.decision_for` exact-
  matches the true drop (`:2605-2609`, `drop_presentation.py:240-243`), `presentation_impact` becomes
  True, and the WindowMachine `in_window` branch **re-enters**: `_enter_window` pushes
  `_window_end_beat` ~`drop_window_cap_beats` (192) later and re-fires the presentation verdict
  (`drop_presentation.py:701-705`); `state_manager.py:2677-2694` also re-runs the per-drop bookkeeping
  for the same beat (`finalize_drop_observation` double-counts; auto-solo/learned re-evaluated).
  [confirmed by trace]
- **Every genuine presentation impact coincides with a smart-drop marker crossing** — confirmed by the
  test suite: all 11 real-impact cases in `tests/test_state_manager_drop_presentation.py` pass
  `impact_now=True` WITH `smart_drop_crossing=True` (the `_sp_state` default, `:60`); only the label-
  re-arm guard test uses `smart_drop_crossing=False`. The presentation system is designed to fire on
  real markers; the leak is that the laser's `drop_crossing` reason is trusted without that check.
  [confirmed]
- A genuine SECOND true drop inside an open window (a real new marker) has `smart_drop_crossing=True`
  and SHOULD still re-enter — `test_true_drop_inside_open_window_reenters_with_own_presentation`
  (`:262-280`, second impact at beat 96 with `smart_drop_crossing=True`). The fix must preserve that.
  [confirmed]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `state_manager.py` (`_drop_presentation_tick`) and
  `tests/test_state_manager_drop_presentation.py`, plus Part E docs.
- Do NOT touch: `drop_lifecycle.py`, `led_dispatch_policy.py` (AWR-140's drop-look re-arm is CORRECT
  and stays), `laser_director.py`, `drop_presentation.py`, `smart_phrasing.py`, config.
- Do NOT change the drop look / role behavior — the 2nd-chorus drop LOOK must still fire (that is the
  point of AWR-140). This fix ONLY stops the label re-arm from being counted as a drop-PRESENTATION
  impact.
- Error handling: pure boolean gate, nothing to catch. No try/except.

### Task 1 — `state_manager.py`: require a real marker for a presentation impact
In `_drop_presentation_tick`, in the MAIN body (after the scripted early-return that ends at the
`return` around `:2571`, before the `session = self._drop_presentation_session` line), gate the
incoming `impact_now` on a genuine smart-drop crossing:

```python
# AWR-140 follow-up: the Laser Director now emits reason="drop_crossing" for the capped
# 2nd-chorus LABEL re-arm too (armed_this_tick without a smart-drop marker). A label re-arm
# is NOT a drop-presentation impact — presentation stays per true drop / smart-drop marker
# (AWR-139). Require a real marker crossing this tick so a 2nd-chorus re-arm cannot re-enter
# or extend the window, re-fire the presentation verdict, or double-count drop stats.
impact_now = bool(impact_now and sp_state.smart_drop_crossing)
```

This flows through every downstream use in the function (`eval_beat`, `presentation_impact`, and the
`if impact_now and decision is not None` bookkeeping at `:2677`), so the label re-arm is excluded
everywhere at once, while a genuine true drop (`smart_drop_crossing=True`) is unaffected.

### Task 2 — Tests: prove the leak is closed AND genuine re-entry survives
In `tests/test_state_manager_drop_presentation.py` add a case mirroring
`test_label_rearm_without_active_drop_does_not_reenter_window` but with `active_drop_beat` **still
set** (the live-reachable shape the existing test misses):
1. First tick: a true drop opens a window (`abs_beat=32.0, active_drop_beat=32.0,
   smart_drop_crossing=True, impact_now=True`); capture `_window_end_beat`.
2. Second tick: a label re-arm INSIDE the post-drop hold — `abs_beat=56.0, active_drop_beat=32.0`
   (still the true drop, unchanged), `smart_drop_crossing=False, current_phrase_is_chorus=True,
   phrase_start_crossing=True, impact_now=True`.
3. Assert `_window_end_beat` is UNCHANGED (no re-entry / no ~192-beat extension) and the presentation
   reason/verdict did not re-fire for this tick.
Confirm the existing `test_true_drop_inside_open_window_reenters_with_own_presentation` still passes
(a real second marker `smart_drop_crossing=True` MUST still re-enter) — do not weaken it.

## Part C — Invariants That MUST Still Hold (live safety)
- AWR-140's 2nd-chorus drop LOOK still fires (drop_lifecycle / led_dispatch unchanged).
- AWR-139 per-true-drop presentation restored: a window opens/re-enters ONLY on a real smart-drop
  marker; a genuine second true drop still re-enters with its own presentation.
- No blackout can latch dark and no fixture behavior changes beyond removing the erroneous re-entry;
  no new tick-path I/O; pure boolean added.

## Part D — Tests
Task 2. Pure in-memory via the existing `_sm_with_plan` / `_sp_state` harness (no files/subprocess).

## Part E — Acceptance (definition of done)
- [ ] Tasks 1–2 exact; `laser` + `led_govee` contract suites + `discover tests` at the known ~3-red
      baseline (from `/Users/bbui`: `python3 -m unittest discover rb_ss_bridge_v2.tests`).
- [ ] Hard checks pass: `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] `docs_update`: correct the AWR-140 spec's Part C note (the "label re-arm is NOT a presentation
      impact" invariant is now ENFORCED, via a dated addendum — do not rewrite history); note the gate
      in the `laser` + `led_govee` subsystem cards' drop-impact descriptions; add an AWR-143 row to
      `docs/status/active_work_registry.md` (implemented / software-tested; HARDWARE-UNVALIDATED), and
      annotate the AWR-140 row "presentation-leak closed by AWR-143".
- [ ] Status language §10 only.

## When You Finish
Report the exact `state_manager.py` diff, the new test, and the verbatim tail of the test/checks
output. Operator summary: "AWR-140 correctly brought back the second-chorus drop look, but that
re-arm was also being mistaken for a brand-new drop by the laser/LED-vs-lasers 'who lights the room'
system — so at the second chorus it could re-decide the room split and stretch that decision most of
the way to the end of the track. Now only a real drop marker triggers that decision, so the split
stays fixed per drop like it should; the second-chorus drop look is unchanged." Rollback = remove the
one gate line and its test. End with the literal line SUBAGENT-LEAKFIX-DONE.
