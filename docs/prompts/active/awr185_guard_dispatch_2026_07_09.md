# AWR-185 dispatch — rung-0b yields to the stop rung (AWR-184 parked-finding fix)

doc_status: current
truth_level: dispatch-brief
date: 2026-07-09 ~19:35 (superman4; operator deadline 21:30, handoff after)

## Part A — verified ground truth

- AWR-184 (788a358 + docs 1e8ac71) added rung 0b (deep sub-void blackout) to
  `lighting_moments_v2.darkness_ladder`, checked BEFORE the stop/balloon split. LIVE
  since the 19:05:52 bounce.
- ledtune's post-gate finding, CONFIRMED REAL by executive sweep
  (`docs/research/awr184_stop_ambiguity_sweep_2026_07_09.md`): rung 0b reads no
  full-band audibility, so a vocal-stop shape (deep sub void + dark growl band +
  full band still audible: vocals sit above the 60–500 Hz growl band) resolves
  blackout-4 where the calibrated stop rung gave 8. 55/716 v4 cache tracks contain
  the class (superset any-beat scan; per-drop unconfirmed). Taste-LENGTH only —
  both outcomes are blackouts.
- Utopia (Dombresky) is NOT among the 55 (its voids kill the full band below
  ref−10) — the fix must PROVE its b192/b384 operator pins survive, not assume.
- Stop-rung audibility shape at HEAD: `med(full_db[window]) >= ref - 10`
  (`STOP_LIFT_FLOOR`, lighting_moments_v2.py:127); ref =
  `v4.scalars["loudness_ref_db"]` (:394).

## Part B — scope (ONE precedence guard, no new thresholds)

In `darkness_ladder`, compute the stop-rung eligibility BEFORE rung 0b fires; when
the stop rung would fire on the same approach, rung 0b yields (the stop rung's
calibrated length wins). Implementation shape is the reviewer's one-liner — evaluate
stop first, gate 0b on `not stop` — but land it as the code actually reads at HEAD;
if the stop decision is computed further down today, hoist the minimal predicate,
do not duplicate threshold logic.

## Part C — non-scope

- NO threshold/constant changes (SUB_VOID_DB, VOID_MIN_BEATS, GROWL_DARK_DB,
  STOP_LIFT_FLOOR, BALLOON_PERC_BOUNDARY all stay).
- NO consumer changes; staged-only (no restart/config/process signals — the
  executive owns the bounce).
- F2-off/scripted paths byte-identical.

## Part D — acceptance

1. NEW pin: a synthetic ambiguous-class case (sub<−10 run ≥2 beats into the drop,
   growl min <5 over the run, med(full) ≥ ref−10) resolves via the STOP rung
   (8-class length), NOT rung 0b's run-length rounding. Shape it from the sweep
   doc's measured examples (e.g. the Cruel Summer 418-beat run: 51 beats,
   growl 0.3, full ref−9.4).
2. Utopia b192 → blackout 8 and b384 → blackout 4 UNCHANGED (explicit).
3. Killa 513-521 true-silence pins UNCHANGED; Caramelle stays balloon; the
   existing TestDeepSubVoidBlackout suite stays green (edit expectations ONLY where
   the new precedence is the tested subject).
4. Scoped file suite green; three hard doc checks green.
5. Docs: extend the AWR-184 paragraph in `docs/subsystems/led_govee.md` with the
   precedence sentence + this round's registry row AWR-185 (re-check max id at
   write time). software_test_inventory: one sentence for the new pin.
6. Commits by explicit paths.

## Part E — chain + signals

Build: ledfix3 (this dispatch, Opus/high). Review+gate: superman4 compressed
(executive line-read + desk reruns; ledtune is parked — its finding IS this round's
spec, its lane memory already holds the item). On completion write
`/tmp/rbss_lane_signals/ledfix3.A184B.done` AND message tmux session superman4 (one
line: commit + which pins hold). Blocked → `.blocked` + evidence. Run straight
through; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED language.
