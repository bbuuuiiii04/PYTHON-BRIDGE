---
doc_status: active-spec
truth_level: implementation-spec, operator-directed revert (Brandon 2026-07-07 afternoon)
last_verified_commit: 08c0b81
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — restore queued pad-color semantics (revert AWR-134 instant-apply)

Contract key: `led_govee` (`docs/agents/change_contracts.yml:101`). **Operator decision
(2026-07-07): pad color changes SHOULD queue to the next look boundary — that is the intended
musical behavior.** The AWR-134 instant-apply (implemented earlier today from
`docs/plans/active/led_pad_color_immediacy_spec.md`) misread the symptom: the real problem was the
queue firing late/never, which the AWR-132 hold-starvation fix already cured (dispatch boundaries
are now bounded at ≤32 beats). This spec removes the instant-apply behavior while keeping the
harmless pure refactor underneath it.

## Part A — Context (verified; read, do not implement)

AWR-134 (landed in the auto-sync range ending `a26921e`..`f636862`) added:
1. A pure refactor: color injection extracted into `_led_inject_engine_colors(...)` in
   `led_dispatch_policy.py` — **KEEP** (no behavior change).
2. Instant-apply plumbing — **REMOVE**:
   - policy mixin cache `self._led_live_rt_auto` (+ its writes on accepted realtime automation
     dispatch, and clears on idle entry / `Ev.LED_BLACKOUT`),
   - policy method `_led_refresh_manual_color()` (+ its `[RGB] manual-color-refresh` log line),
   - coordinator method `refresh_realtime_colors(...)` in `led_dispatch_coordinator.py`,
   - the `state_manager.py` call to `_led_refresh_manual_color()` after routing
     `Ev.LED_MANUAL_PAD` / `Ev.LED_RAINBOW_PAD` / `Ev.LED_PALETTE_PAD` to
     `self._led_palette_control.handle_event(ev)`.
3. Tests asserting instant-apply (`tests/test_led_state_manager.py`,
   `tests/test_led_dispatch_coordinator.py` additions from AWR-134) — remove or invert per Part D.

Desired end state = pre-AWR-134 behavior exactly: a color pad press mutates the color engine only;
the strip repaints with the new color at the NEXT automation dispatch (role_key change), which
AWR-132 now bounds. Laser instant-follow behavior is untouched (it was never part of AWR-134).

## Part B — Tasks

### Absolute Rules
- Touch ONLY: `led_dispatch_policy.py`, `led_dispatch_coordinator.py`, `state_manager.py`,
  `tests/`, Part E docs. Keep the `_led_inject_engine_colors` refactor and ALL AWR-132/133 changes
  (hold backstop, idle ambient, freewheel, reset-reason logging) intact — verify you are not
  reverting those lines when removing adjacent AWR-134 code.
- No config or env changes.

### Task 1 — remove the instant-apply plumbing
Remove every item listed in Part A item 2. `git log -p` over today's auto-sync commits
(`a26921e..f636862` window) shows the exact AWR-134 hunks; do a surgical removal, not a commit
revert (auto-sync commits bundle unrelated work).

### Task 2 — tests
- Remove/replace the AWR-134 instant-apply tests.
- Add one regression test asserting the QUEUE semantics: with a live realtime look, a manual pad
  event does NOT reach the runner (`set_desired` not called on the stub), and the next automation
  dispatch (new role_key) carries the NEW engine color in its injected params.

## Part C — Invariants That MUST Still Hold
- AWR-132 hold backstop + logging, AWR-133 idle/ambient/freewheel, AWR-135 drop gate, AWR-136
  health reporting: byte-untouched.
- Laser pad color path: untouched (still instant by design).
- `_led_inject_engine_colors` refactor stays; automation color injection behavior unchanged.

## Part D — Tests
Task 2 above; then `python3 -m unittest tests.test_led_state_manager tests.test_led_dispatch_coordinator`
and full `discover tests` (documented env reds excepted).

## Part E — Acceptance
- [ ] Instant-apply fully removed; queue regression test green.
- [ ] Focused suites + full discovery at the known-3-reds baseline; `check_docs_metadata.py`,
      `check_agent_contracts.py`, `check_docs_drift.py` pass.
- [ ] Docs: update `docs/subsystems/led_govee.md` (remove instant-recolor claim),
      `docs/status/active_work_registry.md` (AWR-134 row → superseded-by-operator-decision,
      AWR-137 row → implemented), and mark
      `docs/plans/active/led_pad_color_immediacy_spec.md` frontmatter `doc_status: superseded`
      (move to `docs/plans/completed/` if the repo convention prefers; follow existing precedent).
- [ ] Operator summary: "color pads queue again — the color lands at the next look change, which
      the hold fix now guarantees arrives within ~32 beats."

## When You Finish
Report changed files, tests/checks, operator summary, rollback note (re-apply the removed hunks).
End with the literal line CODEX-SPEC6-DONE.
