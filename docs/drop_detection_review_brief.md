# Drop-Detection ML Review — Multi-Model Brief

I'm stuck on an audio-ML refinement problem. Please give me an independent, critical read. Push back hard if my reasoning is wrong or if there's an obvious thing I'm missing. The constraint isn't compute — it's whether I should keep iterating offline or ship what I have.

## Problem

Laser-show automation for DJ software (Rekordbox). Rekordbox's track analysis ("RB") detects approximate drop positions. RB is often wrong — sometimes off by 1 beat, often by 1 bar (4 beats), often by 2 bars (8 beats).

My task: given RB's detected drop beat, **pick the exact correct beat from a 9-beat window** starting at RB's pick (drop_beat through drop_beat+8).

Scoring: a linear model assigns each candidate beat a score = `sum(weight_i * feature_i)`. Top score wins.

## Corpus

- 66 unique tracks labeled (a DJ dropped a hot cue commented "DROP" at the true drop position)
- 367 labeled candidate-windows after filtering orphans (cases where the labeled drop fell outside the 9-beat window)
- Label distribution (rough): ~37% at drop_beat exactly, ~20% at +1 beat, ~20% at +4 beats (+1 bar), ~20% at +8 beats (+2 bars), plus outliers
- 21 of 66 tracks held out (~32%)

## Current model: PR #87 — the working peak

14 features, 7 active after NNLS tuning. Tuned weights:

```
pre_valley_depth          0.027    # waveform: was there a quiet section before this beat
downbeat_alignment        0.138    # beat % 4 == 0 -> 1.0
distance_penalty          0.006    # decay from RB's pick (regularizer)
high_mid_pattern_onset    0.262    # 800-4kHz energy entered here (synth lead, vocal)
spectral_balance_shift    0.408    # low/high spectral energy ratio shifted toward lows
centroid_drop             1.000    # SEED weight — spectral centroid fell going into this beat
spectral_flux_onset       1.000    # SEED weight — peak total energy at this beat vs prior 8
```

Note: `centroid_drop` and `spectral_flux_onset` are at seed weight 1.0, not tuned. NNLS refitting all 14 features regressed: per-track CV 75% → 73%, holdout exact 74% → 63%. Empirically, keeping seed weights for the two newest features on top of partially-tuned weights for others generalizes better than full NNLS refit. Strange but real.

The remaining 7 features all got zero weight after tune:
`onset_score`, `broad_onset_score`, `post_lift`, `kick_pattern_onset`, `bass_pattern_onset`, `low_mid_pattern_onset`, `phrase_energy_step`.

## Performance

- v1 baseline (mean-lift, currently shipped to production): **37% exact / 60% within ±1 on holdout**
- v2 PR #87: **74% exact / 91% within ±1 on holdout**
- Per-track 5-fold CV (grouped by track-id, training-only): 75%

Original ship gate I set: ≥80% absolute holdout exact AND ≥+20pp over v1. v2 clears the "+20pp" half (+37pp) but is 6pp short of "80% absolute."

## Five consecutive failed attempts past PR #87

Every post-PR-#87 feature iteration regressed holdout exact when tuned:

1. **Wider scan window** (drop_beat..+17 instead of +9, distance_penalty rescaled): regressed
2. **Phase 1 stack** (added spectral_rolloff_shift + per-candidate min-max normalization + ridge λ 0.01 → 0.1 + pruned 7 dead features): **-20pp holdout exact**
3. **Phase 1 retry** (same minus per-candidate normalization): **-11pp**
4. **Product features** (drop_signature = downbeat_alignment × spectral_flux_onset; pre_quiet_then_low = pre_valley_depth × spectral_balance_shift): **-14pp**
5. **Phrase alignment** (beat % 32 == 0 scores 1.0, % 16 == 0 scores 0.5): **-20pp**

Failure mechanism, exemplified by #4: before adding product features, `downbeat_alignment` had weight 0.138 and `spectral_flux_onset` had seed 1.000. After tuning with the new `drop_signature` product added, NNLS gave `drop_signature` weight 0.710, crushed `downbeat_alignment` to 0.054 (-61%), and zeroed `spectral_flux_onset`. On training the loss looked better; on holdout it regressed by 14pp. Consistent across all five attempts: tuner gives the new feature high weight, shrinks existing ones, and generalizes worse.

Multicollinearity is high: feature matrix condition number is 500-550. Ridge bumps from 0.01 to 0.1 made the tuner over-conservative and zeroed genuinely contributing features.

## Independent agent's diagnosis (received this morning)

A different LLM reviewing this proposed a structural fix: the bug is the **loss function**, not the features.

The tune mode currently does NNLS on a regression target: each candidate window emits 9 rows with target 1.0 for the correct beat and 0.0 for the other 8. NNLS minimizes mean squared error. But the evaluation metric is **argmax-correctness** — does the correct beat outscore the other 8 in its window?

These objectives diverge. A feature that bumps the correct beat by +0.5 AND bumps two neighbors by +0.3 still wins argmax but hurts MSE. NNLS crushes that feature's weight to fix MSE — even though it was helping the metric we actually grade on.

Their proposed fix: pairwise hinge-rank loss with non-negative weights. For each window, emit 8 pairs `(correct_features - wrong_features)` and minimize `sum(hinge(margin - w·diff))` subject to `w >= 0`. Optimizes argmax-correctness directly. Multicollinearity matters less because pairwise diffs cancel shared baselines (the diff matrix's effective condition number is lower than 500).

Predicted gain: **+5-10pp holdout exact** with the current 14 features unchanged.

I'm about to ship that change as a Codex task. Want your opinion before it lands.

## Questions for you

1. **Is the loss-function diagnosis correct?** Will pairwise rank loss actually solve the failure mode, or is there a more fundamental problem I'm missing?
2. **Is the "corpus saturated for linear models" framing correct?** Or could the right linear model still hit 80% with this data?
3. **What's the highest-EV move you'd recommend** — pairwise rank loss, gradient-boosted trees, a different architecture entirely, more labeled data, fixing the wrong RB analyses (~30 tracks remain on the priority list), or just shipping at 74% and collecting live failure cases?
4. **Are there feature classes I'm not considering?** I've tried: waveform onsets, spectral band onsets (5 bands), spectral balance shift, centroid drop, spectral flux, rolloff, phrase alignment, product features. What am I blind to?
5. **Is ±1-beat at 91% (≈470ms perceptual lag at 120 BPM) actually a problem for a laser show?** Maybe I'm chasing the wrong metric and the system is already good enough.

Files for reference (you don't need to read them; this brief should be self-contained):
- `anlz_reader.py` — features + scorer + weights
- `tools/eval_smart_drop_algorithm.py` — harness with `evaluate` + `tune` modes
- `~/smart_drop_corpus_filtered.yaml` — labeled corpus (367 rows × 66 tracks)

Give me your honest read in under 600 words. Specific recommendations preferred over general advice. If you think I'm chasing the wrong problem, say so directly.

---

## Resolution (2026-05-18) — what actually happened

The reviewer LLMs (Opus 4.7, Sonnet 4.5) converged on the same diagnosis and we acted on it. Recording it here so future readers don't re-litigate the call.

### Methodological errors the reviewers flagged

1. **Holdout used as validation set.** The 21-track alphabetical-every-3rd holdout had been scored against nine models. PR #87 was the *max* of those nine, not a clean test result. Selection bias on a single split.
2. **Bootstrap CI resampled drops, not tracks.** Drops within a track share BPM, mix engineer, and RB analyzer behavior. The right unit of independence is the track. Effective `n` is ~21, not ~100. Naive drop-level CIs were ~3× too tight.
3. **Sorted-alphabetical split is not random.** Track names correlate with label, year, remixer, BPM conventions. The asymmetric "every CV gain regresses on holdout" pattern is consistent with a non-random split, not pure noise.

### Validation re-run

**Track-level bootstrap (1000 iter) on the original holdout:**

- PR #87 holdout exact: 74.6% with 95% CI [58.3%, 90.3%] (width 32pp)
- Anchored holdout exact: 60.4% with 95% CI [40.5%, 80.0%]
- Difference CI: [+0.0%, +31.2%] — includes zero, statistically indistinguishable.

**K-fold reshuffle (10 random 32/68 track splits), frozen weights, no re-tune:**

- PR #87 wins: 5/10 (avg +6.8pp when winning)
- Anchored wins: 4/10 (avg +5.3pp when winning)
- Ties: 1/10
- Mean diff across splits: +1.3pp (essentially zero)

The reviewer was right. The "8 failures past PR #87" were largely PR #87 winning a noise lottery on the alphabetical split, not real signal.

### Decision: ship anchored (PR #88)

Two weight sets are empirically equivalent on this corpus, so the tiebreaker is principle, not performance:

- **Right objective.** Pairwise hinge rank loss optimizes argmax-correctness — the metric we actually evaluate on. NNLS minimizes squared error on binary 1.0/0.0 targets, a different objective.
- **Mechanical protection against the failure mode.** L2 anchor on seed features + L1 sparsity prevents "new feature crushes seed weight" — the exact failure that produced eight regressions in a row.
- **Higher per-track CV.** Anchored 78%, PR #87 NNLS-tuned 73%, PR #87 with seed hack 75%. Per-track CV is the most reliable signal we have at n=66.
- **Removes the seed hack.** PR #87 had two features manually fixed at weight=1.0 because NNLS wanted to crush them. Anchored handles the same features without manual override.

PR #88 is a 1-file, 10-line change in `anlz_reader.py` — just the weights. The anchored-rank-loss tuner that produced these weights ships in a follow-up PR (`tools/eval_smart_drop_algorithm.py`).

### Roadmap

1. Merge PR #88 (weights only).
2. Tuner-code PR — move anchored-rank-loss + track-level bootstrap + K-fold reshuffle into the harness so future re-tunes use the right objective and the right validation by default.
3. Pre-ship polish — earlier-beat tiebreaker + top-2 abstain (~50 lines, perceptual wins).
4. Step 6 — runtime wiring behind `RBSS_SPECTRAL_ENABLE=1`.
5. Real gig test. Live failures become the next dataset.
6. Eventually, label tracks to ~150+. At that size bootstrap CI tightens enough to actually distinguish models, and we can revisit feature engineering with valid statistics.

### Meta-lesson

**Never trust a single holdout split at n<100 tracks.** K-fold reshuffle should be standard from experiment #1, not added after eight stuck experiments. Bootstrap CI must resample at the unit of independence (tracks), not at the row level. If we'd done both from the start, we'd have shipped two months earlier and skipped the eight "failures."
