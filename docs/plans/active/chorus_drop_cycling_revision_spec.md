---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: 47c7a32
last_verified_date: 2026-06-22
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Revision Spec — Laser drop-lifecycle: close audit gaps (tests, spec, claims)

> Follow-up to `docs/plans/active/chorus_drop_cycling_spec.md`. Driven by an adversarial audit of
> head `47c7a32` that found **no P0/P1 live-safety defects** and a set of P2/P3 test-accuracy,
> spec-contradiction, and claim-overstatement gaps. This spec closes those gaps. **It must not
> change runtime laser/LED behavior** except the single optional flag-gating in R4 (only if you
> choose option R4-b).

## Status / scope
- Repo: `rb_ss_bridge_v2`, branch `soundswitch/impl`, head `47c7a32` (verify: `git rev-parse HEAD`).
- Accepted repo status: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. Do not upgrade it.
- This is a REVISION of an audited, merged feature. You are closing P2/P3 gaps. **No runtime
  laser/LED behavior change is permitted EXCEPT** the optional flag-gating in R4 (R4-b, one line).
- Read first: `AGENTS.md`; `docs/plans/active/chorus_drop_cycling_spec.md` (original spec);
  `docs/subsystems/laser.md`; `docs/agents/change_contracts.yml`. Then read the code named below.
- House rules: code > tests > config > docs. Locate every edit by surrounding code, not by the line
  numbers quoted here (they drift). Commit after each R-item. Run AGENTS.md §8 hard checks and
  `python3 -m unittest discover tests` before declaring done. Do NOT modify tests to make docs pass.
- **Never touch:** `smart_phrasing.py`, `smart_rearm.py`, `autoloop_controller.py`, the executor
  blackout methods, the `_led_*` runtime path in `state_manager.py`, the push-loop threading.

## Verified context you can rely on (from the audit)
- `drop_lifecycle.py` is pure and correct; `resolve()` correctly returns `armed_this_tick=True`
  **only when `mutate=True`** (the conditional form — this is the SHIPPED, correct behavior; do NOT
  "restore" the verbatim spec form).
- The gated-off-crossing blackout clear is real and safe: the `state_manager.py` SM net
  (`reason="smart_drop_crossing_without_drop_decision"`) clears the blackout for any crossing where
  the director did not emit `reason=="drop_crossing"`. Covered by `tests/test_smart_transitions.py`
  (`test_crossing_clears_pending_blackout_when_non_drop_decision_wins` /
  `test_crossing_does_not_double_clear_when_drop_decision_emitted`).
- `autoloop_tick_just_fired` is a single-tick-per-beat pulse (set only inside `if this_beat>last_beat`
  with `last_beat_elapsed_ms` advanced in-block), so cycling cannot double-fire within a beat.
- Both live and example configs load with 0 errors and default `drop_lifecycle_mirror=True`.

---

## R1 (P2-1) — Add a REAL LED-parity test, or formally downgrade the claim
**Problem:** `tests/test_drop_lifecycle.py` `TestParity` never calls the LED resolver; it only
documents two divergences. Part E criterion 1 and spec A2 promise a parity comparison that does not
exist.

Do this:
1. Investigate feasibility of invoking `StateManager._led_role_from_smart_phrasing` in isolation for
   the FLAT-window case (`max=2`, `impact=8`), WITHOUT the `_led_note_drop_decision_accepted` rewrite
   and WITHOUT touching LED runtime code. Options, in order of preference:
   - **(R1-a)** Construct a minimal `StateManager` (or bind the unbound method to a lightweight object
     carrying only the LED lifecycle attributes + module constants it reads) and drive a shared
     SmartPhrasing timeline through BOTH it and `DropLifecycle.resolve(mutate=True)`, asserting equal
     role per tick across: allowed-predecessor `drop`→hold(impact=8)→`post_drop`; disallowed-predecessor
     →`post_drop`; chorus→chorus cap at `max=2`; lifecycle clear when leaving chorus/post_drop. Map LED
     non-drop roles (breakdown/pre_drop/buildup/low/groove) to `"none"` for the comparison and EXCLUDE
     timelines that hit those LED branches (the resolver intentionally does not port them). A test that
     re-transcribes the LED logic inside the test file is NOT acceptable (circular).
   - **(R1-b)** If R1-a is infeasible without importing/altering LED runtime code, DO NOT force a
     brittle harness. Instead: (i) rename `TestParity` → `TestKnownDivergences`; (ii) edit the original
     spec Part E criterion 1 and A2 to state that parity is established by transcription + per-behavior
     resolver tests, NOT by an executable LED comparison, and say why (LED resolver is not pure /
     extraction is out of scope); (iii) update `docs/subsystems/laser.md` and
     `docs/status/validation_matrix.md` to match.
2. State explicitly in your final report which option you took and why.

## R2 (P2-2) — Add the promised A4 blackout + mask-owner equivalence test
**File:** `tests/test_laser_executor_lifecycle.py` (or new `tests/test_laser_blackout_equivalence.py`).
Using the existing `_FakeMidiOutput` + `_make_config(smart_drop_mode="blackout_mask")` harness:
1. **Allowed crossing, flag-on vs flag-off:** arm a Smart Drop blackout (set the ctx arm signal the
   executor reads), then deliver a `drop_crossing` decision in each mode; assert the manual_blackout
   ON and OFF MIDI messages are byte-identical across modes (channel/note/velocity/kind). The SCENE
   note may differ (flag-on shuffles) — assert ONLY the blackout pair.
2. **Disallowed crossing, flag-on:** deliver the gated-off equivalent (a `post_drop_cycle`/`drop_cycle`
   decision with `autoloop_tick_just_fired=False`, i.e., the blackout-mode crossing tick) and assert
   that after the clear the executor ends with `blackout_pending_for_drop_window=False` and empty
   `mask_owners` (no stranded dark). If exercising the SM net requires `StateManager`, assert the
   executor-level invariant directly (`clear_pending_blackout` leaves it clear).
3. Read-only of production code; no behavior change.

## R3 (P3-1) — Strengthen `TestA7Regression`
**File:** `tests/test_laser_executor_lifecycle.py`, `TestA7Regression`.
Add assertions that actually prove non-sequential, non-"+1-per-track" behavior:
1. Over one full bag pass (`len(usable)` cycles, seeded rng, autoloop ticks), assert every usable note
   appears exactly once AND the sequence is not the monotonically-increasing note order.
2. With two different seeds (or a reset between), assert the two passes are not identical.
Keep `randomize_cursors=False` so the cursor starts at a reshuffle boundary (as the existing test does).

## R4 (P2-4) — Resolve the resume executor-reset vs C1 "byte-identical" contradiction
Pick ONE and apply it (do NOT do both); state which you chose:
- **(R4-a, docs-only, recommended)** Edit the original spec C1 and Part E criterion 2, plus
  `docs/subsystems/laser.md`, to say: "flag-OFF is byte-identical to pre-change EXCEPT the resume
  transition, which now also resets the executor (a benign phrase-bank reshuffle + active-scene clear;
  no dark, no drop leak)." No code change.
- **(R4-b, code)** In `state_manager.py` `_do_resume`, gate ONLY the executor reset behind the mirror
  flag (the director reset stays unconditional), so flag-OFF resume is truly byte-identical. If you do
  this, add/extend a test proving flag-OFF resume does NOT reshuffle the executor while flag-ON does.

## R5 (P2-5 / SD-1) — Fix the spec's Task-1 verbatim block (docs-only)
**File:** `docs/plans/active/chorus_drop_cycling_spec.md`, Task 1 code block. Replace the unconditional
`return DropResult(role="drop", armed_this_tick=True)` with the shipped conditional form
(`armed_this_tick` set True only inside `if mutate:` after `arm()`), so the verbatim block matches
`drop_lifecycle.py` and the prose at the end of Task 1.

## R6 (P2-3 / SD-5) — Correct the "instant kill switch" claim (docs-only)
**Files:** `docs/plans/active/chorus_drop_cycling_spec.md` (kill-switch lines), `docs/subsystems/laser.md`.
Reword to the verified reality: `drop_lifecycle_mirror` is a config-driven kill switch applied on the
next personality re-apply via the hot-reloader (`__main__.py` `_on_laser_config_reload`); it is
restart-dependent if hot-reload is disabled (`HOT_RELOAD_DISABLE_ENV`) and is NOT a single runtime
command. Note the genuine instant escapes (emergency blackout / disabling the laser director).

## R7 (P3-2) — Focused config-validation tests
**File:** `tests/test_laser_config.py`. Add cases that hit `laser_config.py` `_validate_personality`'s
new branches: `drop_lifecycle_mirror` non-bool (e.g. `1`) → error; `max_drops_in_a_row = 0` and
`= True` (bool) → error; `drop_impact_beats = -1` and `= True`, `post_drop_cycle_beats = 0` → error;
and a valid case with all four knobs set to non-defaults that loads clean.

## R8 (P3-3) — Integration-test the six reset wiring sites
**File:** `tests/test_state_manager_personality.py` (or focused file). With a mocked `_laser_director`,
assert `reset_runtime_state` is invoked on: master change, active-track load, stop, resume, scripted
apply, idle apply. Assert the executor reset is invoked on master/track/stop/resume and NOT on
scripted/idle (matching the spec's deliberate asymmetry).

## R9 (P3-4 / P3-5) — Residual edge tests (low priority; do if time permits)
1. A unit test that a same-length usable-set change rebuilds the bag (drive `_next_shuffled_scene_locked`
   after swapping which entries are usable while length is constant), OR a code comment documenting that
   this is unreachable at runtime because every personality swap clears `_role_bag`.
2. A rejection/rollback test: force a cooldown or backend-reject during a shuffled `drop_cycle` and
   assert the role cursor is restored (no skipped/duplicated look on the next successful pick).

---

## Acceptance (definition of done)
- `python3 -m unittest discover tests` green (report the new total).
- New/changed tests: R2, R3, R7, R8 present and green; R1 either a real parity test (green) or the
  documented downgrade; R9 done or explicitly deferred with a code comment.
- R4/R5/R6 applied (state which R4 option).
- AGENTS.md §8 hard checks green (metadata, contracts, drift). Staleness advisory only — re-verify the
  laser/config_schema docs you touched and bump `last_verified_commit` ONLY for those.
- `git diff --check` clean. No runtime laser/LED behavior change except (optionally) R4-b's one line.
- `tools/check_laser_midi_sync.py` still exits 0 on the live config.

## When you finish — OUTPUT THIS LAST, VERBATIM (the REVISION REVIEW PROMPT)
End your entire response with the block below, filled in. Do not add anything after it.

```
---BEGIN REVISION REVIEW PROMPT (send to Claude)---
You are re-auditing a REVISION of the laser drop-lifecycle feature in /Users/bbui/rb_ss_bridge_v2,
branch soundswitch/impl. Your prior audit (head 47c7a32) found no P0/P1 defects and these gaps:
P2-1 missing LED-parity test, P2-2 missing A4 blackout/mask-owner test, P2-3 overstated kill switch,
P2-4 resume-reset vs C1 byte-identity, P2-5 spec armed_this_tick contradiction, P3-1 weak A7 test,
P3-2 config-validation tests, P3-3 reset-wiring tests, P3-4/P3-5 residual edge tests.

REVIEW-ONLY, no mutations. New review head: <FILL: git rev-parse HEAD>. Revision baseline: 47c7a32.
Commits in this revision: <FILL: git log --oneline 47c7a32..HEAD>.

For EACH of R1–R9, the implementer reports: <FILL: one line per item — done/deferred, files touched,
which option chosen for R1 and R4>.

Verify, do not trust:
1. Re-run: the four targeted lifecycle test modules; `python3 -m unittest discover tests`;
   `python3 tools/check_laser_midi_sync.py`; the three hard doc checks; `git diff --check`. Report
   exact counts/results.
2. R1: confirm any new parity test actually invokes the real StateManager LED resolver (not a
   re-transcription) OR that the downgrade is consistently reflected in spec + laser.md +
   validation_matrix.md.
3. R2: confirm the blackout ON/OFF pair is asserted byte-identical flag-on vs off, and the
   disallowed-crossing path asserts no stranded dark.
4. R3: confirm the A7 test now proves non-sequential/random, not merely "track 2 fired".
5. R4: confirm the chosen option is internally consistent (no remaining C1 contradiction); if R4-b,
   confirm flag-OFF resume no longer resets the executor and a test proves it.
6. R5/R6: confirm spec/docs now match shipped code (armed_this_tick conditional; kill-switch wording).
7. R7/R8/R9: confirm the validation, six-site wiring, and residual tests exist and are meaningful.
8. Confirm NO unintended runtime laser/LED behavior change crept in (diff 47c7a32..HEAD of
   laser_director.py, laser_executor.py, drop_lifecycle.py, state_manager.py).

Output: findings first (P0–P3) with file:line, consequence, proof, smallest fix, and type; then a
per-R-item PASS/FAIL/PARTIAL matrix; then commands run + results; then a short operator summary and
the residual hardware-unvalidated risks. Do not implement fixes.
---END REVISION REVIEW PROMPT---
```
