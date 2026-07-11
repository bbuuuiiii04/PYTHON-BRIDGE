---
doc_status: current
truth_level: design proposal with confirmed/assumed/unknown claim labels
last_verified_commit: f0da6b1
last_verified_date: 2026-07-11
validation_scope: >
  Design-only Stage-2 contract for gradable spectral axes and the SOL finding-1
  classifier. Current code and the named program documents were read at this
  commit. No implementation, runtime, configuration, label, or hardware state
  was changed or contacted.
---

# Spectral Stage-2 design — gradable axes and finding-1 classifier

## 1. Boundary and current truth

- **[CONFIRMED]** The live decision remains `DropDecision(drop_beat, family,
  violence, tier, darkness, bass_forward, reason)`; it has no per-marker
  genuine-drop, timed-growl, or laser-suitability output
  (`lighting_moments_v2.py:854-882`).
- **[CONFIRMED]** Current darkness exposes `kind`, integer `beats`, an optional
  half-open beat window, optional early abort, inputs, and a reason
  (`lighting_moments_v2.py:414-421`). Its deep-sub-void path qualifies the
  growl side with `min(growl[...]) < GROWL_DARK_DB`, so one low growl sample can
  satisfy that side of the rule (`lighting_moments_v2.py:537-565`). This is the
  still-open SOL finding 1.
- **[CONFIRMED]** AWR-205 already keys one gold row to each resolved marker and
  records `is_genuine_drop`, darkness, growl, and laser fields, but its scorer
  intentionally leaves darkness, growl, laser, and drop classification
  unavailable because `DropDecision` has no verified like-for-like outputs
  (`tools/spectral_ear_benchmark.py:775-813`,
  `tools/spectral_ear_benchmark.py:965-1048`).
- **[CONFIRMED]** AWR-203 exposes local landed body, abrasion, growl-duty, and
  onset terms plus track-relative path results, but its track baseline is built
  from a caller-supplied list of genuine drops (`hardness_v0.py:70-101`,
  `hardness_v0.py:260-281`). Using that gold-derived baseline as an input to the
  genuine-drop classifier would leak the answer.
- **[CONFIRMED]** AWR-204 already exposes robust per-series quantiles, trends,
  run curves, track/section-relative depths, separate first-8 and following-8
  landed windows, and marker-offset bundles (`approach_features_v0.py:117-215`,
  `approach_features_v0.py:416-552`). It decides no class and has no runtime
  importer.
- **[CONFIRMED]** The Stage-1 harness already supplies grouped
  leave-one-lineage-out folds and a single guarded production-planner call
  boundary (`tools/spectral_ear_benchmark.py:430-453`,
  `tools/spectral_ear_benchmark.py:555-576`). Stage 2 extends those seams; it
  does not create a second evaluator.
- **[CONFIRMED]** All work described below starts offline and shadow-only.
  Rekordbox markers remain the cue time. Existing family, tier, darkness,
  SoundSwitch, laser, LED/Govee, and bridge-log behavior remains unchanged until
  a later operator-approved live activation.
- **[UNKNOWN]** The operator is filling the gold file in parallel, so current
  class counts, lineage coverage, and the exact free-text darkness vocabulary
  are not known to this design seat. No acceptance threshold may be claimed met
  until the filled file is validated.

## 2. One shadow bundle on `DropDecision`

- **[ASSUMED]** The smallest compatible exposure is one new optional final
  field on `DropDecision`: `stage2: Optional[Stage2ShadowDecision] = None`.
  Existing fields, constructor order, and consumers stay untouched.
- **[ASSUMED]** The offline Stage-2 planner populates the bundle. The existing
  `build_track_plan()` continues to produce `stage2=None` until an explicit
  observability gate is accepted. This preserves the present zero-runtime-
  importer promises of `hardness_v0.py` and `approach_features_v0.py`.
- **[ASSUMED]** All Stage-2 records are frozen value objects. `unavailable` is
  distinct from a musical negative: missing data must not become “no growl,”
  “continuous,” “not genuine,” or “no laser.”

**[ASSUMED]** The exact logical shape is:

```text
BeatSpan:
  start_beat: int
  end_beat: int

AxisBool:
  value: bool | null
  confidence: float | null
  reason_codes: tuple[str, ...]

SpanAxis:
  state: "present" | "absent" | "unavailable"
  span: BeatSpan | null
  confidence: float | null
  reason_codes: tuple[str, ...]

DarknessAxis:
  state: "present" | "absent" | "unavailable"
  shape: "true_void" | "growl_dip" | "melodic_swell" |
         "vocal_effect_stop" | "relative_dip" | "continuous" |
         "uncertain" | null
  span: BeatSpan | null
  span_beats: int | null
  beats_per_bar: 4 | null
  bars: float | null
  confidence: float | null
  reason_codes: tuple[str, ...]

LaserAxis:
  value: "yes" | "no" | "unknown"
  confidence: float | null
  reason_codes: tuple[str, ...]

Stage2ShadowDecision:
  schema_version: 1
  drop_classification: AxisBool
  darkness: DarknessAxis
  growl: SpanAxis
  laser: LaserAxis
  marker_offsets: tuple[-2, -1, 0, 1, 2]
  marker_confidence: float | null
```

- **[ASSUMED]** `BeatSpan` uses absolute, zero-based Rekordbox beat indices and
  half-open `[start_beat, end_beat)` semantics. Both bounds are integers,
  `0 <= start_beat < end_beat <= n_beats`, and `span_beats = end_beat -
  start_beat`.
- **[CONFIRMED]** Current darkness windows already use half-open
  `[start, drop)` beat ranges (`lighting_moments_v2.py:415-419`,
  `lighting_moments_v2.py:556-557`). Keeping that convention avoids a second
  boundary meaning.
- **[ASSUMED]** Raw beats are authoritative. For this Stage-2 benchmark only,
  `beats_per_bar` is explicitly frozen to 4 and `bars = span_beats / 4.0`.
  Bars are derived display/scoring data, never an independent model output and
  never used to move a boundary.
- **[CONFIRMED]** The current blackout ladder itself treats 4/8/16 beats as
  one/two/four-bar-scale rungs (`lighting_moments_v2.py:239-246`).
- **[UNKNOWN]** The current gold schema carries no time-signature or
  beats-per-bar field. Any non-4/4 example must remain darkness-span
  `unavailable` until provenance carries its meter; silently assuming 4/4 for
  such an example is forbidden.

## 3. Axis exposure contracts

### 3.1 Drop classification

- **[ASSUMED]** `drop_classification.value` is the model answer compared directly
  with gold `is_genuine_drop`: `true` means a genuine landed drop, `false` means
  a buildup/continuation/false marker, and `null` means the model abstained or
  lacked sufficient data.
- **[ASSUMED]** A false or unavailable drop classification forces the other
  three Stage-2 axes to `unavailable` for that model row. It does not alter or
  delete the legacy `DropDecision`.
- **[CONFIRMED]** The gold loader already distinguishes real booleans from null
  and rejects integer aliases (`tools/spectral_ear_benchmark.py:896-962`).

### 3.2 Darkness shape, span, and bars

- **[ASSUMED]** Gold `drop.darkness.shape` is normalized to the exact vocabulary
  in `DarknessAxis.shape`. The current validator accepts any string
  (`tools/spectral_ear_benchmark.py:882-890`); Stage-2 implementation must add
  this allowlist before scoring.
- **[ASSUMED]** `true_void`, `vocal_effect_stop`, `relative_dip`, and
  `melodic_swell` are `state="present"` and require a span. `continuous` is
  `state="absent"` with no span and zero derived bars. `growl_dip` is an acoustic
  counterexample class with no darkness span: it records that a brief growl
  depression was observed but did not justify blackout. `uncertain` is
  `state="unavailable"`, never a safe synonym for continuous.
- **[ASSUMED]** For a true void, the span begins at the first beat of the
  sustained multi-band void and ends at the authoritative drop marker. It is
  not rounded before scoring. A later presentation rule may quantize only after
  the raw span has passed its gate.
- **[ASSUMED]** `DarknessAxis` plugs into the optional shadow bundle only.
  `DropDecision.darkness` remains the sole live authority until a later spec
  explicitly replaces or maps it.

### 3.3 Growl span

- **[ASSUMED]** `growl` describes the primary contiguous growl run intersecting
  the 16 landed beats `[drop_beat, drop_beat + 16)`, matching the separate
  first-8 and following-8 Stage-2 views. `present` requires a half-open absolute
  beat span; `absent` maps to gold `"none"`; `unavailable` maps to no score.
- **[ASSUMED]** If multiple candidate runs exist, choose the run with the
  greatest summed finite growl evidence; ties choose the earlier run. This
  makes one deterministic per-marker output match the one-span AWR-205 gold
  shape without inventing a list the intake cannot grade.
- **[CONFIRMED]** Existing v4 data contains per-beat growl level and flatness,
  per-beat sustain bands, quarter-beat growl-band levels, and frame-rate growl
  level/centroid (`audio_spectral_features.py:77-124`,
  `audio_spectral_features.py:347-372`). No new extraction is required to test
  this span design.
- **[CONFIRMED]** The current live texture collapses per-beat growl flags to a
  16-beat majority (`lighting_moments_v2.py:737-795`); Stage-2 must score the
  timed span itself rather than that boolean.

### 3.4 Laser suitability

- **[ASSUMED]** `laser.value` is exactly `yes`, `no`, or `unknown`, matching the
  gold enum. `unknown` is an abstention, not a negative and not a pass.
- **[CONFIRMED]** Laser suitability is independent from family/tier. Current
  `laser_tier()` derives energy from only those two fields
  (`lighting_moments_v2.py:321-338`); Stage-2 does not replace that live path.
- **[ASSUMED]** Candidate inputs may include genuine-drop confidence, intrinsic
  landed hardness, timed growl evidence, sustain/brightness, and darkness
  shape, but no single growl or family/tier condition may grant suitability.
- **[ASSUMED]** Laser remains shadow-only until gold contains at least five
  positive and five negative independent lineages, grouped evaluation passes,
  and the operator accepts an ear review. Until then the only permitted model
  output is `unknown`.

## 4. Finding-1 classifier

### 4.1 Shape: two transparent heads, not one opaque score

- **[ASSUMED]** Head A answers `is_genuine_drop`; Head B answers the approach
  shape only when Head A is true. This prevents a non-drop marker from gaining
  a darkness or laser decision merely because one pre-marker value crossed a
  threshold.
- **[ASSUMED]** Both heads are rules-first. The rule form and candidate feature
  list are frozen before threshold fitting; thresholds are fitted only inside
  grouped training folds. A tiny learned model remains out of Stage 2 until
  class coverage is materially larger.

### 4.2 Head A — drop versus buildup/continuation

- **[ASSUMED]** Use these AWR-203 local, label-free landed axes: body `L_B`,
  abrasion `L_A`, growl duty `L_R`, onset density `L_N`, and their five-offset
  ranges. Do not use `T_*`, `H`, `t3`, or a `TrackBaseline` in this head because
  current `T_*` construction requires a genuine-drop list.
- **[ASSUMED]** Use these AWR-204 axes from both landed halves: full/sub/growl/
  sustain/percussion p50, finite coverage, slope, early-to-late delta, and
  persistence from first-8 to following-8. Use the approach-to-landing change
  in full/sub/percussion as arrival evidence.
- **[ASSUMED]** Use existing v4 attack and mid-high onset density only through
  those predeclared landed summaries. Titles, content IDs, lineage keys,
  operator fields, and per-track thresholds remain forbidden inputs.
- **[ASSUMED]** The rule returns true only when at least one landed-body clue
  and one independent arrival-or-persistence clue agree. Missing required data
  returns null. This exact conjunction shape is fixed before numeric threshold
  search.

### 4.3 Head B — true void versus growl dip and other approaches

- **[ASSUMED]** Use AWR-204 approach run curves and track/section-relative
  depths for `sub_db`, `full_db`, `growl_band_db`, `sustain_mid_db`,
  `sustain_high_db`, and `perc_full`; also use their slope/delta and all five
  marker-offset bundles.
- **[ASSUMED]** A true-void candidate requires persistent, overlapping evidence
  in sub plus at least two independent non-sub views from full, growl, sustain,
  and percussion. An isolated minimum in any one series can never satisfy the
  rule.
- **[ASSUMED]** A growl-dip candidate is the counter-shape: sub/full/sustain do
  not show a sustained aligned void, while growl evidence is brief or unstable
  across offsets. A single low growl beat may support `growl_dip`; it may not
  support `true_void`.
- **[ASSUMED]** `melodic_swell` requires sustained harmonic energy while the
  sub falls; `vocal_effect_stop` requires low percussion with audible full or
  sustain energy; `relative_dip` is a multi-beat track/section-relative fall
  without a true void; `continuous` has no qualifying fall; conflicting or
  insufficient evidence returns `uncertain`.
- **[ASSUMED]** Marker pooling uses the fixed offsets -2/-1/0/+1/+2. Each raw
  descriptor uses the robust middle value; `marker_confidence` is a monotone
  function of disagreement across the five outputs. Cue timing stays at offset
  zero.

### 4.4 How the incoming gold fits and validates thresholds

- **[CONFIRMED]** Every non-null `is_genuine_drop` row is available to Head A;
  nested drop fields are valid only for genuine drops in the hybrid intake
  (`tools/spectral_ear_benchmark.py:148-167`,
  `tools/spectral_ear_benchmark.py:928-958`).
- **[ASSUMED]** Gold `is_genuine_drop=true/false` is the Head-A target. Gold
  darkness shape provides the Head-B target after normalization to the frozen
  vocabulary. Gold growl and laser fields grade their separate outputs; they do
  not become predictor inputs.
- **[ASSUMED]** Evaluation is nested grouped LOLO. For each outer held-out
  lineage, feature selection and numeric threshold choice use only the remaining
  lineages, with an inner grouped split. The outer lineage is predicted once.
  Marker rows from one lineage are never divided between train and test.
- **[ASSUMED]** Each lineage has equal weight, then each class has equal weight
  inside that lineage. A track with many markers cannot dominate threshold
  selection.
- **[ASSUMED]** No threshold is accepted from an ungrouped marker split, a
  whole-corpus fit, named-pin tuning alone, or a score that exposed the held-out
  lineage during selection.

### 4.5 Classifier acceptance gate

- **[ASSUMED]** Head A remains UNAVAILABLE unless both true and false gold occur
  in at least five independent lineages. Head B remains UNAVAILABLE unless
  `true_void` and at least five non-void counterexample lineages are present,
  including at least one labeled `growl_dip` lineage.
- **[ASSUMED]** A head passes development only if outer-LOLO prediction coverage
  is at least 90%, lineage-macro balanced accuracy is at least 0.70, each class
  recall is at least 0.70, and balanced accuracy beats its frozen legacy
  baseline by at least 0.10. An abstention on known gold counts as wrong for
  these agreement metrics and is also reported separately.
- **[ASSUMED]** Head B additionally must not increase the legacy false-blackout
  count on any `is_genuine_drop=false`, `growl_dip`, `melodic_swell`, or
  `continuous` gold row; it must strictly reduce either false blackouts or
  missed true voids overall. A synthetic one-low-growl-sample pin must always
  return `growl_dip` or `uncertain`, never `true_void`.
- **[ASSUMED]** Passing grouped development admits only a frozen shadow candidate.
  Live consideration still requires predictions frozen before a new blind
  operator batch, the blind scorecard meeting the same thresholds, and explicit
  operator ear acceptance.

## 5. Implementable grading semantics

- **[ASSUMED]** Null/unlabeled gold and literal gold `unknown` are excluded from
  that axis's denominator. Known gold paired with model `unavailable`, null, or
  `unknown` counts as disagreement and as an abstention. This prevents a model
  from winning by refusing difficult rows.
- **[ASSUMED]** All comparisons use the exact marker provenance key already
  enforced by AWR-205. No nearest-marker fallback is allowed.

- **[ASSUMED]** The following table is the complete agreement contract; its
  thresholds and companion reports are required rather than illustrative.

| Axis | Scorable gold | Agreement rule | Required companion report |
|---|---|---|---|
| Drop classification | `is_genuine_drop` is true/false | Exact boolean match. Null model value disagrees. | Confusion matrix, per-class recall, balanced accuracy, macro F1, abstention rate, lineage-macro versions. |
| Darkness shape | Genuine row with a normalized, non-`uncertain` shape | Exact enum match. | Per-shape confusion matrix and lineage-macro accuracy. |
| Darkness span | Gold shape requires a span and both beat bounds exist | Shape matches, span IoU >= 0.50, `abs(start error) <= 1` beat, and `abs(end error) <= 1` beat. | Raw signed and absolute start/end error, IoU distribution, false-positive and missed-span counts. |
| Darkness bars | Gold bars and beat bounds both exist under 4 beats/bar | Gold must satisfy `bars * 4 == end_beat - start_beat`; inconsistency is a hard validation error. Model agrees only when its raw span length is identical. | Exact bar-length rate; never use bar rounding in the span score. |
| Growl | Gold is `"none"` or has both span bounds | `none` agrees only with model `absent`. Two spans agree when IoU >= 0.50 and both boundary errors are <= 1 beat. | Detection confusion, boundary MAE, IoU distribution, duration error, abstention rate. |
| Laser | Gold is `yes` or `no` | Exact enum match; model `unknown` disagrees. | Positive/negative recall, balanced accuracy, false-positive count, false-negative count, lineage coverage. |

- **[ASSUMED]** Span IoU uses half-open integer beat sets:
  `max(0, min(end) - max(start)) / (max(end) - min(start))`. Two absent spans
  are handled by the detection rule, not assigned an artificial IoU.
- **[ASSUMED]** Axis availability flips to AVAILABLE only when at least one
  scorable gold example and one real `Stage2ShadowDecision` output were compared.
  A recorded gold value without a scorer remains UNAVAILABLE, matching the
  current AWR-205 honesty rule (`tools/spectral_ear_benchmark.py:460-540`).

## 6. Landing order and falsifiable gates

1. **[ASSUMED] Contract normalization.** Freeze the exact enums and beat-span
   validation above in AWR-205. Exit only when typos, inconsistent bars, invalid
   spans, and non-4/4-without-meter examples fail closed. **Live:** unchanged.
2. **[ASSUMED] Shadow exposure.** Add the optional bundle and an offline builder
   that reuses production decision seams. Exit only when every resolved marker
   deterministically emits either a valid axis record or an explicit unavailable
   reason; legacy `build_track_plan()` output remains identical with
   `stage2=None`; no runtime consumer imports or reads the bundle. **Live:**
   unchanged.
3. **[ASSUMED] Scorers.** Add the exact per-axis comparisons in Section 5 to the
   AWR-200 harness. Exit only when synthetic cases pin every boundary, unknowns
   cannot inflate scores, grouped folds remain disjoint, and each axis stays
   UNAVAILABLE without both gold and a real model output. **Live:** unchanged.
4. **[ASSUMED] Finding-1 bake-off.** Fit only the frozen rules-first classifier
   inside nested grouped folds. Exit only when Section 4.5 passes and the frozen
   report records feature version, thresholds per fold, label hash, cache/grid
   provenance, coverage, and every outer prediction. **Live:** candidate remains
   shadow-only; AWR-199 stays in force.
5. **[ASSUMED] Growl and laser shadow rounds.** Growl may advance when its span
   agreement gate passes grouped and blind data. Laser may advance only after
   its separate coverage and balanced-error gate passes. **Live:** neither axis
   is consumed; laser defaults to `unknown`.
6. **[ASSUMED] Operator blind/ear gate.** Freeze predictions on a new independent
   batch before labels are revealed. Exit only when grouped/blind scores pass,
   named safety pins do not regress, and the operator accepts the side-by-side
   old/new behavior by ear. **Live:** still unchanged.
7. **[ASSUMED] Separate activation spec.** Only a later Codex implementation
   spec may map accepted shadow fields to live darkness, growl, or laser
   consumers. It must keep the frozen legacy fallback and an explicit live
   enable gate. Restart, toggle, and hardware checks require operator approval.

## 7. Findings and unresolved items

- **[CONFIRMED] Finding 1 remains open.** The current `min(growl)` qualification
  is a one-sample statistic; AWR-204 supplies the multi-beat measurements needed
  to replace it, but no classifier consumes them.
- **[CONFIRMED] The gold shape vocabulary is not yet fail-closed.** AWR-205 checks
  only that darkness shape is a string, so normalization must land before shape
  scoring.
- **[CONFIRMED] AWR-203's track baseline is unsafe as a genuine-drop classifier
  input without a label-free construction.** Stage 2 therefore uses only its
  local landed axes in Head A.
- **[UNKNOWN]** Current section boundaries are not supplied automatically to
  `approach_features()`; its section view is optional. Until a code-verified
  boundary source is chosen, section-relative descriptors may be unavailable
  and may not silently fall back to track-relative values.
- **[UNKNOWN]** The filled gold may not contain enough false markers, true voids,
  growl dips, or independent laser positives/negatives to meet coverage gates.
  The correct result in that case is UNAVAILABLE, not relaxed thresholds.
- **[UNKNOWN]** This design is software reasoning only. No SoundSwitch, laser,
  LED/Govee, Rekordbox-reader runtime, bridge process, bridge log, or room-visible
  behavior was contacted or hardware-validated.
