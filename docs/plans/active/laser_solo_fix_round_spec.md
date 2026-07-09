---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-08
last_verified_commit: HEAD-2026-07-08-overnight
validation_scope: implementation spec for overnight fixes round 2 (executive-released order); grounded in docs/research/laser_solo_triage_2026_07_08.md whose cites were verified at 96d0e07 — git confirms state_manager.py and drop_presentation.py untouched since, so every cite holds at HEAD; bridge DOWN, stays down
---

# Codex Implementation Spec - Laser Solo fix round: cancel wire + honest arms (AWR-159)

Round 2 of the overnight fixes queue, from
`docs/research/laser_solo_triage_2026_07_08.md` (read it FIRST — it carries
the full mechanism, log evidence, and the authority-doc limitation mapping).
Two confirmed defects: (1) a manual solo arm fires only when four fragile
conditions coincide on one 200 Hz tick and fails SILENTLY otherwise — a dice
roll from the operator's seat; (2) an ACTIVE solo (window open, Govees dark)
has no cancel — the tested `manual_interaction` fail-open hook exists in the
window machine but nothing runtime ever sets it. New operator evidence for
this round: **the pad blinked for the entire mix after one arm** — the pad
feedback latched a stale armed state.

## Part A - Context (verified; the triage doc is the authority)

Key cites, all confirmed intact at HEAD (files untouched since the triage's
`96d0e07`): manual-arm resolve chain `state_manager.py:2622-2665` (armed key
check :2622, plan_unavailable downgrade :2643-2646, laser_visible gate
:2657-2665, arm cleared at impact :2690); pad-press branches
`state_manager.py:2786, :2801-2841` (press-during-active falls through to
re-arm :2841); window machine pre-dark reset `drop_presentation.py:689-696`,
release conditions `:701-718`, the UNWIRED `manual_interaction` fail-open
`:672-678` (runtime callers: none; tests exist); exact-float plan match
`drop_presentation.py:240`; `solo_manual` checked first `:361-363`;
`base_live` forced False at `state_manager.py:3839, :3888, :3927`.

Design authority: `drop_presentation_authority.md:36` — a solo is "never a
dice roll — every solo traces to an operator signal." Limitations #1/#2 in
that doc map to these defects and must be updated when fixed.

## Part B - Tasks (implement exactly, in order; one commit per task)

### Absolute Rules

- NO bridge starts; live config read-only; `config/led_lab/**` untouched.
- Behavior that must not change: auto-tier solos (hotcue/learned/gear-shift/
  record-breaker ladders) keep today's gates EXACTLY — only MANUAL arms get
  the honesty upgrade; the pre-impact disarm/veto branches
  (`state_manager.py:2801-2839`) stay; scripted-mode Required Behavior
  Test 9; the 200 Hz push loop gains no I/O; SoundSwitch pack/laser output
  behavior unchanged except the solo paths named below.
- Fail direction: a broken cancel must fail toward the EXISTING automatic
  releases (never toward a stuck-dark window); a refused manual arm must be
  VISIBLE, never silent.

### Task 1 - Wire the active-solo cancel (the nearly-free fix)

In `_drop_presentation_solo_pad_pressed` (`state_manager.py:2786`): when the
current presentation feedback state is `active` (window open), set a
one-tick `self._drop_presentation_manual_cancel = True` instead of falling
through to the re-arm branch (`:2841`). In `_drop_presentation_tick`, pass
it as `manual_interaction=True` into `WindowInputs` (consume + reset the
flag same tick; it must also clear on every teardown path that clears other
presentation state). The window machine's existing fail-open
(`drop_presentation.py:672-678`) does the rest — LEDs restore, base
suppression releases, machine idles. Log one INFO `[LASER] solo-cancelled
by=pad`. The pad becomes the documented four-state: arm / disarm /
veto-pending / cancel-active.

### Task 2 - Honor a manual arm without the exact plan-beat match

At `state_manager.py:2643-2646`: when `armed` (manual) and `impact_now` but
`plan.decision_for(beat)` returned `None`, resolve as `solo_manual` instead
of `LEDS_PLUS_LASERS/"plan_unavailable"`. Auto tiers keep the plan
requirement. (Kills the exact-float-equality dependency for exactly the one
case the operator explicitly requested.)

### Task 3 - Manual arms are deterministic-or-visibly-refused

For MANUAL arms only, replace the silent `laser_visible` downgrade:

1. Drop the `laser_director.is_enabled()` term from the manual-arm
   visibility check (the physical lasers run on the SoundSwitch pack path
   independent of the Director flag — triage §Defect 1). Manual visibility =
   `base_live` AND not masked AND role ∈ {drop, post_drop}.
2. When even that fails at impact (lasers genuinely unpresentable), REFUSE
   VISIBLY: clear the arm, emit one operator-facing INFO log
   (`[LASER] solo-refused reason=<base_live_false|masked|role>`), and drive
   the pad feedback to a distinct brief `refused` state (reuse the existing
   feedback-file mechanism; a red flash if the surface supports it,
   otherwise a state string the deck script already renders distinctly).
   NEVER silently downgrade a manual arm to leds+lasers.

### Task 4 - Reset-reason logging on the pre-dark reset

`drop_presentation.py:689-696`: the `predark → clear` reset line gains its
reason — `passed_without_drop` vs `not_visible`, and for `not_visible` which
gate (`director_disabled` / `base_live_false` / `masked`). Edge-triggered,
one line per reset. This closes the triage's open unknown for every future
miss.

### Task 5 - Pad feedback truth (the blinked-all-mix evidence)

The arm is keyed to `(active_deck, load_gen)`; when the key goes stale
(track/deck change, re-cue bumping load_gen) the arm silently stops matching
while the pad keeps blinking "armed" — tonight it blinked the entire mix
after one arm. Fix: on every event that changes the arm key's referents
(track load on the armed deck, active-deck change, stop), CLEAR the stale
manual arm explicitly (one INFO log `[LASER] solo-arm-cleared
reason=track_changed|deck_changed|stopped`) and drive the pad feedback back
to idle. The feedback state must be derived from live presentation state,
never latched. Verify the feedback writer covers all five states (idle /
armed / pending / active / refused-flash) and transitions on each.

### Task 6 - Tests

`tests/test_drop_presentation.py` + `tests/test_state_manager_drop_presentation.py`:
1. Cancel: press-while-active → fail-open reset (LEDs restore, base
   suppression released, idle), one-tick flag consumed; press-while-armed
   still disarms; press-while-pending-auto still vetoes; press-while-idle
   still arms.
2. Manual arm with `decision=None` at impact → `solo_manual` (not
   plan_unavailable); auto tier with `decision=None` → unchanged.
3. Manual visibility without Director enable → fires when base_live+unmasked;
   refusal path: base_live False at impact → arm cleared + refused feedback +
   log, LEDs untouched.
4. Reset-reason strings for each gate.
5. Feedback truth: arm then track-load on armed deck → arm cleared, feedback
   idle; arm then deck flip → same; full state-cycle transitions.
6. Auto-tier regression pins: existing ladder tests stay green untouched.

### Task 7 - Contract docs (final commit)

Contract: `drop_presentation` (per `docs/agents/change_contracts.yml`) —
update its full `docs_update` list; `drop_presentation_authority.md`
limitations #1/#2 flip to fixed-with-behavior-description (solo = 
deterministic-or-visibly-refused; active solos cancellable; feedback
truthful); registry row AWR-159 (implemented / software-tested); run the
contract's test list + full suite (known six environmental reds) + three
hard checks.

## Part C - Invariants That MUST Still Hold

- Auto-tier solo behavior byte-identical (only manual-arm paths change).
- An active solo still releases on ALL existing automatic conditions —
  cancel is additive.
- The refusal path never leaves base suppression engaged or LEDs dark — it
  refuses BEFORE darkening (or restores atomically if pre-dark already
  engaged).
- No new blocking I/O on the 200 Hz tick; feedback writes stay on the
  existing feedback-writer path.
- Emergency blackout and AWR-154/155 blackout-owner semantics untouched.

## Part E - Acceptance

- [ ] Tasks 1-7 in order, one commit each, explicit paths; auto-sync
  fragmentation noted-never-rewritten.
- [ ] Suite at the known-six-reds baseline; contract tests + 3 hard checks
  green.
- [ ] Operator summary in plain words: the solo pad now always does
  something you can see — it fires, or it tells you why not (brief refused
  flash + log); pressing it during a live solo brings the lights back;
  arming then changing tracks un-arms visibly instead of blinking forever.
- [ ] Print exactly AWR159-DONE with real suite numbers above it, or
  AWR159-BLOCKED plus the reason.
