---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (operator scenario 2026-07-07 afternoon; verified vs 08c0b81+)
last_verified_commit: 08c0b81
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — drop windows re-enter on new impacts; backstop above real sections

Contract key: `drop_presentation` (`docs/agents/change_contracts.yml:346`). Follow-up to AWR-135
(implemented earlier today). Operator scenario that exposed both gaps: "what if I have a 128-beat
drop section, and drop presentation prevents lasers from firing at the true drop."

## Part A — Context & Root Cause (verified; read, do not implement)

1. **Stale-window shadow (the sharper gap).** `WindowMachine.tick()`'s `in_window` branch
   (`drop_presentation.py:699-712`) never checks `inputs.impact_now` — a NEW true-drop impact while
   any window is open is ignored, and the OLD presentation keeps ruling until role-exit or the cap.
   Concretely: an LED-only drop opens a window (`base_suppressed=True`); if a second true drop —
   planned `LEDS_PLUS_LASERS` or `LASERS_ONLY` — lands while the role is still `drop`/`post_drop`
   (one continuous chorus label, double-drop tracks), the lasers do NOT fire at that second drop's
   impact. AWR-135's cap change (32→96) tripled the length of this shadow. [confirmed at
   `drop_presentation.py:699-712`: only `drop_role`, `_window_end_beat`, `lost_visibility` are
   consulted; `impact_now` is consulted only in the `pre_dark` (`:683`) and `idle` (`:715`)
   branches.]
2. **Backstop below a real section.** `drop_window_cap_beats=96` (AWR-135) assumed no real drop
   section exceeds 96 beats. Operator states 128-beat drop sections exist in his catalog — at 128,
   the backstop releases suppression at beat 96, lasers pop back 32 beats early (the exact behavior
   AWR-135 was meant to kill, at a higher threshold). The true hang cases are already covered by
   the universal fail-opens (`scripted_mode | stopped | track_changed | active_deck_changed |
   manual_interaction`, `drop_presentation.py:671-676`), so the beat backstop can safely sit far
   above any real section. [confirmed]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `drop_presentation.py`, `config/led_look_director.example.json`, the live gitignored
  `config/led_look_director.json` (local edit, never committed), `tests/`, Part E docs.
- Contract `drop_presentation` forbidden assumptions hold verbatim (zero RNG; suppression ≠
  blackout; no tick-path I/O; scripted zero-activity; `enabled:false` byte-identical
  leds_plus_lasers).
- Do not change: the fail-opens, `_WINDOW_ACTIVE_ROLES`, the role-exit release, `pre_dark` entry
  from idle, `laser_ratio`, `_guarded` downgrade logic.

### Task 1 — `in_window` impact re-entry
At the TOP of the `in_window` branch (before the `window_ended` computation at `:700`), add:
```python
if inputs.impact_now and pending_presentation is not None:
    presentation, reason = self._guarded(pending_presentation, pending_reason, inputs)
    self._enter_window(presentation, reason, inputs.abs_beat)
    return self._window_actions()
```
Semantics: every true-drop impact asserts its OWN planned presentation and re-stamps the cap from
its own impact beat — identical to the idle-entry code at `:715-718`. `_guarded` still downgrades
a `LASERS_ONLY` verdict when the laser is not visible at impact. Known accepted limit (document in
the docs update, do not "fix"): a `LASERS_ONLY` solo re-entered this way gets no `pre_dark` LED
countdown (that phase only runs from idle); the solo fires at impact without the LED pre-dip.

### Task 2 — backstop 96 → 192
- `drop_presentation.py:92` default `96.0` → `192.0`; keep/extend the hang-guard comment: the
  release is role-exit or a newer impact (Task 1); 192 exists only so a stuck phrasing flag cannot
  hold lasers dark indefinitely, and must stay above the longest real drop section (operator
  reports 128-beat sections).
- Both JSON configs (`config/led_look_director.example.json` drop_presentation block; live
  gitignored `config/led_look_director.json` locally): `"drop_window_cap_beats": 192`.

### Task 3 — Tests (pure WindowMachine, existing style in `tests/test_drop_presentation.py`)
1. **Laser drop fires inside an LED-only shadow:** open LEDS_ONLY window at beat 0; at beat 64
   (role still `post_drop`) tick with `impact_now=True`, `pending_presentation=LEDS_PLUS_LASERS` →
   actions flip to `base_suppressed=False`, presentation `LEDS_PLUS_LASERS`, and the cap re-stamps
   from beat 64.
2. **LED-only follow-up drop re-stamps:** same but second drop LEDS_ONLY → still suppressed, new
   `_window_end_beat = 64 + cap`.
3. **128-beat section stays suppressed:** LEDS_ONLY window, role held `post_drop` through beat 128,
   no second impact → `base_suppressed` True at beat 127 (would fail at the old 96 cap), released
   by role-exit at 128.
4. **Backstop still works:** role stuck in `post_drop` forever, no impacts → released at 192.
5. **No re-entry without a pending presentation:** `impact_now=True, pending_presentation=None`
   in-window → old window continues unchanged.
6. Update any assertions pinning 96 (from today's AWR-135 test edits: `tests/test_led_config.py`,
   `tests/test_drop_presentation.py`, `tests/test_state_manager_drop_presentation.py`).

## Part C — Invariants That MUST Still Hold
- Fail-opens release in any phase; `_drop_presentation_release_on_stop()` untouched.
- Suppression ≠ blackout; scripted zero-activity; `enabled:false` byte-identical.
- Role-exit remains the normal release; the cap remains an OR'd hang guard.
- No RNG, no tick-path I/O.

## Part D — Tests
Task 3; all pure in-memory.

## Part E — Acceptance
- [ ] Tasks 1–3 exact; `python3 -m unittest tests.test_drop_presentation` + the contract's sibling
      suites + full `discover tests` (known-3-reds baseline), `check_docs_metadata.py`,
      `check_agent_contracts.py`, `check_docs_drift.py` all pass.
- [ ] Contract `drop_presentation` `docs_update` docs updated (incl.
      `docs/architecture/drop_presentation_authority.md` — window re-entry semantics + the no-pre-dark
      solo limit — and `docs/status/active_work_registry.md`: this spec AWR-138 implemented, AWR-135
      row noted as amended by AWR-138).
- [ ] Status language: `implemented`/`software-tested`; laser-visible outcomes HARDWARE-UNVALIDATED.

## When You Finish
Report changed files, tests/checks, operator summary (plain: "every real drop now asserts its own
laser plan at its own impact, even mid-window; the safety timer is 192 beats and only exists for
software hangs; a solo landing mid-window skips its LED pre-dip"), rollback (revert + restore both
config values to 96 + restart). End with the literal line CODEX-SPEC7-DONE.
