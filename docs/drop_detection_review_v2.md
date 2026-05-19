# Drop-Detection ML — Updated Brief (Stuck at 8 Failures Past Baseline)

I'm an LLM (Opus 4.7) working with a user on an audio-ML refinement problem. We've reached a methodologically interesting impasse: eight consecutive offline experiments past our peak model regress on the only metric we evaluate against (a 21-track holdout), even though several of them improve every other metric (training accuracy, per-track CV, training ±1). I want a fresh independent read. Be willing to tell me I'm pattern-matching wrong.

## Problem statement

Laser-show automation for DJ software (Rekordbox). Rekordbox's analysis ("RB") detects approximate drop positions in tracks. RB is often wrong — by 1 beat, 1 bar (4 beats), or 2 bars (8 beats). My job: given RB's detected drop_beat, **pick the exact correct beat from a 9-beat window starting at drop_beat**.

A linear scorer assigns each candidate beat a score = `sum(weight_i * feature_i)`. Top score wins. 14 features, currently 7 active.

## Corpus

- 66 unique tracks labeled (DJ dropped a hot cue commented "DROP" at the true drop position)
- 367 candidate-window rows after filtering orphans (DROP cues outside the 9-beat window)
- Label distribution: ~37% at drop_beat (RB correct), ~20% +1 beat, ~20% +4 beats (+1 bar), ~20% +8 beats (+2 bars), plus outliers
- 21-track holdout (~32%) selected by sorted-alphabetical every-3rd-track, frozen since corpus generation

## The peak model: PR #87

7 active features, tuned via NNLS on PR #87 (then with two seed-1.0 weights kept un-tuned for the two newest spectral features):

```
pre_valley_depth          0.027
downbeat_alignment        0.138
distance_penalty          0.006
high_mid_pattern_onset    0.262
spectral_balance_shift    0.408
centroid_drop             1.000   (seed, not tuned — NNLS wanted to crush it)
spectral_flux_onset       1.000   (seed, not tuned — same)
```

Performance:
- v1 baseline (mean lift, current production): **37% exact / 60% within ±1 holdout**
- **PR #87: 74% exact / 91% within ±1 holdout**
- Per-track CV (5-fold by track-id, training-only): 75%

vs v1: **+37pp exact / +31pp ±1**. Our original gate was ≥80% absolute, which we're 6pp short of.

## The eight failures

Every offline experiment past PR #87 regressed on holdout exact:

| # | Change | Holdout exact | Δ vs PR #87 | Training metric | Per-track CV |
|---|---|---|---|---|---|
| 1 | Wider scan window (±8 → ±17, distance_penalty rescaled) | regressed | -? | unimproved | N/A |
| 2 | Phase 1 stack: rolloff feature + per-candidate min-max norm + ridge λ 0.01→0.1 + prune 7 dead features | 54% | -20pp | training +1pp | -2pp |
| 3 | Phase 1 retry minus normalization | 63% | -11pp | unchanged | unchanged |
| 4 | Two product features (downbeat_align × flux_onset, valley_depth × balance_shift) | 60% | -14pp | +4pp training, +8pp ±1 | unchanged |
| 5 | Phrase alignment (beat % 32, % 16) | 54% | -20pp | -1pp | -7pp |
| 6 | Naive pairwise rank loss (replaces NNLS) | 60% | -14pp | +4pp exact, +8pp ±1 | +2pp |
| 7 | 50/50 ensemble of PR #87 + rank loss (sum-normalized) | 69% | -5pp | +1pp | +1pp |
| 8 | **Anchored** rank loss: hinge + L2 anchor toward seed + L1 sparsity, non-neg | **60%** | **-14pp** | +4pp exact, +8pp ±1 | **+3pp (best ever)** |

The pattern is overwhelmingly consistent and inverse: **anything that improves training and CV regresses on the holdout by approximately the same magnitude.**

## What I think is happening (my current hypothesis)

The corpus is too small for the 21-track holdout to reliably distinguish a real improvement from noise. At n=21 windows × ~5 drops/track = ~100 holdout evaluations, the statistical CI on a single accuracy measurement is wide. Opus (prior consultation) estimated 95% CI ≈ ±8pp. A -14pp swing is on the boundary of significance.

But this is a hypothesis. We have NOT run the bootstrap CI to confirm. I should have done this 6 experiments ago.

## What we know

1. **The 21-track holdout is the only metric we ever evaluate against for ship decisions.** Per-track CV uses training data; everything else is training-side.
2. **Per-track CV and holdout disagree systematically.** Every change that improves CV regresses holdout. This either means (a) CV is overfitting because it uses training data and the model finds training-specific patterns that don't generalize, or (b) the holdout is too noisy to trust at this corpus size. Most likely both.
3. **PR #87's CV-to-holdout gap is small (75% CV vs 74% holdout)**, suggesting PR #87 generalizes cleanly. Every alternative has a larger gap (CV 77-78%, holdout 60-69%).

## Key open questions

1. **Should we bootstrap CI on the holdout BEFORE trying anything else?** If 74% has CI [66%, 82%] and anchored's 60% has CI [52%, 68%], the regression is real. If CIs overlap heavily, our 8 "failures" might be noise we've been over-interpreting. We could even arrive at the conclusion that anchored rank loss is genuinely better and we've been wrongly preferring PR #87.

2. **Is per-track CV actually the more reliable metric here?** It uses 45 training tracks vs 21 holdout. The variance should be lower. But it's contaminated by the fact that the model fit on the same data. What's the right way to reason about CV-vs-holdout disagreement when n is this small?

3. **Are there tuning-level improvements we should run before declaring saturation?** My current ranking, in case it helps you push back:

   **A. Bootstrap CI on the holdout (highest EV).** Resample the 21-track holdout with replacement 1000×, compute holdout exact each iteration, report 95% CI. ~30 lines. Tells us whether 74% vs 60% is real signal or statistical noise. Should have been done after experiment #2. The most important thing we haven't measured.

   **B. Hyperparameter grid search via per-track CV.** Grid over (margin ∈ {0.05, 0.1, 0.2, 0.5}, λ_anchor_seed ∈ {0.1, 1.0, 10.0}, λ_anchor_tuned ∈ {0.01, 0.1, 1.0}, λ_l1 ∈ {0, 0.001, 0.01}). ~108 combos. Currently I hand-picked one point. Could be 2-3pp suboptimal on hyperparameters alone.

   **C. Bagging across CV folds.** Run tune 5× on different CV training subsets, average weights. Reduces single-tune variance.

   **D. K-fold holdout reshuffling.** Resample the 66 tracks into 5 different train/holdout splits. Evaluate PR #87 weights AND any candidate on each. Tells us if PR #87's win is robust or specific to this holdout.

   **E. Different optimizer.** L-BFGS-B with squared hinge isn't the only choice. Adam, coordinate descent, proximal gradient for true L1. Probably lower EV than A-D.

   My instinct: do A first, then either ship (if it confirms saturation) or do B if CI overlaps suggest we've been misreading noise as signal.

4. **Should we ship at 74%/91% or keep iterating?** The user is patient and willing to keep going. Live gig data is the obvious next signal source. But we've also never properly characterized our own noise floor.

## What I want from you

Be willing to push back hard on any of these:

1. **Is my "8 failures = corpus saturated" diagnosis correct, or am I confusing real signal with noise?** What's the right statistical procedure to decide this?

2. **Specifically, would you trust 60% < 74% as a real regression at n=21 holdout tracks?** Walk me through your reasoning.

3. **If you had to pick ONE more experiment before shipping, what would it be?**
   - Bootstrap CI on holdout
   - Hyperparameter grid search via CV
   - K-fold holdout reshuffling
   - Bagging across CV folds
   - Different non-linear architecture (small tree ensemble on residuals)
   - Failure-cluster analysis (look at the ~95 training-set failures, design features targeted to specific error types)
   - Something we haven't tried
   - Just ship

4. **Reality check on the perceptual metric.** v2 is 91% within ±1 beat (≈470ms at 120 BPM). For a laser show, is this actually a problem? Or am I optimizing the wrong number?

5. **Is there a methodological error in how we've been evaluating?** Specifically: we tune on training, evaluate on per-track CV (using training data) AND on holdout (separate 21 tracks). The hyperparameters were hand-picked, not optimized. The holdout was selected by sorted-alphabetical every-3rd, not randomized. Any of these is a textbook bias source.

Files for reference (you don't need to read them; this brief should be self-contained):
- `anlz_reader.py` — features, scoring function, weights
- `tools/eval_smart_drop_algorithm.py` — harness with `evaluate` + `tune` modes
- `~/smart_drop_corpus_filtered.yaml` — labeled corpus

Honest 600-word read preferred over generalities. If you think we should just ship, say so. If you think we're missing a category of move, name it specifically.

---

## Resolution (2026-05-18) — what we did and why

The reviewer LLMs (Opus 4.7, Sonnet 4.5) independently converged on the same critique and we acted on it before iterating further. Documenting here so the v2 framing above isn't read in isolation.

### What the reviewers caught that this brief missed

The brief frames the question as "is the regression real or noise?" The reviewers reframed it as "**you've been using your test set as a validation set.**" PR #87 was the max of nine models scored on the same 21-track alphabetical holdout. It had not been evaluated against an uncontaminated split — it *defined* the contamination. Every subsequent comparison was paying selection-bias tax.

Two adjacent errors:

- **Bootstrap CI was resampling drops, not tracks.** Drops within a track share BPM, mix engineer, and RB analyzer quirks. The unit of independence is the track. The Opus ±8pp estimate quoted above turned out to be ~3× too tight. Track-level CIs are ±15-16pp wide.
- **Sorted-alphabetical every-3rd-track is not random.** Names correlate with label, year, remixer, sometimes BPM. The asymmetric "every CV gain regresses on holdout" pattern is what biased splits look like, not what pure noise looks like.

### What the data actually says (re-run with the right stats)

**Track-level bootstrap (1000 iter, original holdout):**

- PR #87: 74.6% exact, 95% CI [58.3%, 90.3%].
- Anchored rank loss: 60.4% exact, 95% CI [40.5%, 80.0%].
- Difference CI: [+0.0%, +31.2%] — includes zero. Statistically indistinguishable.

**K-fold reshuffle (10 random 32/68 splits, frozen weights, no re-tune):**

- PR #87 wins 5/10 by avg 6.8pp; anchored wins 4/10 by avg 5.3pp; 1 tie.
- Mean diff: +1.3pp (essentially zero).

**The eight "failures" past PR #87 were largely regression to the mean** of a single biased split — not evidence the corpus was saturated and not evidence the experiments were bad.

### Why anchored ships anyway (PR #88)

When two models are empirically equivalent, ship the one with better priors:

- **Right objective.** Pairwise hinge rank loss optimizes argmax-correctness, the metric we evaluate on. NNLS minimizes squared error on binary targets — a proxy. The proxy disagreed with the metric on roughly every recent experiment.
- **Mechanical protection.** L2 anchor on seed features + L1 sparsity prevents "new feature crushes seed weight." This is the exact failure mode of all eight regressions — when the right loss is applied with the right regularizer, the failure mechanism stops happening.
- **Per-track 5-fold CV.** Anchored 78%, PR #87 NNLS-tuned 73%, PR #87 with seed hack 75%. CV is the most reliable signal we have at n=66.
- **No seed hack.** PR #87 manually pinned two features at weight=1.0 because NNLS wanted to crush them. Anchored handles those features without manual override.

PR #88 is a 1-file, 10-line weight swap in `anlz_reader.py`. The tuner code is a follow-up PR.

### What the v2 brief above got right and wrong

- **Right:** "8 failures = corpus saturated" was *partially* correct. The corpus is too small for the holdout to distinguish 5-10pp differences. But the failure mode wasn't only saturation; it was selection bias on a contaminated holdout.
- **Wrong:** The brief lists hyperparameter grid search and bagging as candidate next moves. With a contaminated holdout those just add more selection bias. The right next move was K-fold reshuffle, which the brief lists as option D and doesn't elevate.
- **Right:** 91% within ±1 was probably already the metric that matters. The 9% catastrophic-error tail is what to attack next, with live gig data, not more offline tuning on n=66.

### Roadmap from here

1. Merge PR #88 (weights only, this branch).
2. Tuner-code PR — anchored rank loss + track-level bootstrap + K-fold reshuffle land in `tools/eval_smart_drop_algorithm.py` so future re-tunes use the right objective and the right validation by default.
3. Pre-ship polish — earlier-beat tiebreaker + top-2 abstain.
4. Step 6 — runtime wiring behind `RBSS_SPECTRAL_ENABLE=1`.
5. Live gig test. Failures become the next dataset.
6. Label more tracks (target ~150+) before any further offline feature work.

### Meta-lesson

**Never trust a single holdout split at n<100 tracks.** K-fold reshuffle is mandatory from experiment 1. Bootstrap must resample at the unit of independence (tracks). If those two had been the default, we'd have shipped two months earlier and skipped the eight "failures."

---

## Update (2026-05-18 evening) — multi-seed reshuffle and retune

After the tuner harness landed (separate PR — anchored rank loss + bootstrap-CI + reshuffle into `tools/eval_smart_drop_algorithm.py`), we used it to do two things the original PR #88 analysis hadn't done: re-run the K-fold reshuffle across multiple seeds, and tune from a clean state to test whether PR #88 was actually optimal.

Both came back uncomfortable.

### Multi-seed reshuffle says PR #88 was statistical noise

Original PR #88 K-fold reshuffle: 10 splits at seed=0, 5/4/1 wins for PR #87 vs PR #88, mean diff +1.3pp toward anchored. Resolution above called this "essentially zero" and shipped anchored on prior-quality grounds.

Re-run across 5 seeds × 20 splits = **100 split-comparisons**:

```
PR #88 vs PR #87:           40/55/5  wins, mean diff -0.8pp
                            (PR #87 slightly better; PR #88's
                            advantage at seed=0 was the most
                            favorable seed of the five)
```

The original 5/4/1 at seed=0 was real, but seed=42 reproduces 13/6/1 in PR #87's favor. Seeds 100, 1234, 7777 fall in between. The mean across all 100 splits has PR #87 ahead by 0.8pp — within noise but the opposite direction of the merge-justifying number.

**Implication:** the PR #88 merge was made on a single-seed K-fold that happened to be the seed most favorable to anchored. The resolution above treated +1.3pp at one seed as "essentially zero" and shipped on right-priors grounds. With multi-seed data, anchored is not even nominally ahead. The merge isn't *wrong* (the two are statistically indistinguishable either way) but the analytical case for it is gone.

### A clean retune dominates PR #88 and beats PR #87

`tune --objective rank_loss --margin 0.1 --l1 0.01 --seed 0` (no anchors) on the same 367-window training set produces weights that drop `centroid_drop` to 0.000 and `spectral_flux_onset` to 0.004 — the data does not want those features under the right loss. The weight mass moves to `kick_pattern_onset` (0.96), `high_mid_pattern_onset` (1.66), and `phrase_energy_step` (0.34).

Same multi-seed reshuffle methodology, same 100 splits per pair:

```
Retune vs PR #88 (shipped): 68/26/6  wins, mean diff +1.5pp
                            (consistent across all 5 seeds:
                            +1.4 / +1.3 / +1.5 / +2.3 / +1.1pp)
Retune vs PR #87:           50/40/10 wins, mean diff +0.7pp
```

Bootstrap-CI paired diff vs shipped on the full corpus (n=56 unique tracks, 1000 iter):

```
mean +1.6pp, 95% CI [-2.3pp, +5.5pp]
```

The K-fold signal is robust across seeds. The bootstrap-CI is mostly positive but includes zero. The retune dominates PR #88 (clear) and marginally beats PR #87 (within noise).

### What the resolution above got wrong

- **"Mechanical protection prevents new feature crushes seed weight."** Wrong as a generalization. NNLS does crush via squared-error fit, but the pairwise hinge rank loss does not — it's already the right objective and doesn't need anchor priors to keep features alive. The right way to read PR #87's "seed hack at 1.0" was: *NNLS is the wrong objective, fix the objective.* PR #88 fixed the objective AND added priors. The priors were the un-needed half of the change. Once the objective is right, the data drives `centroid_drop` and `spectral_flux_onset` to ~0; forcing them positive measurably hurt generalization.
- **"Anchored 78% per-track CV vs PR #87 75%."** Both still true. But the no-anchor retune also lands at 78% CV, so CV doesn't distinguish the two anchored points. The resolution presented CV as the deciding evidence; in retrospect it can't decide between them.
- **"Per-track CV is the most reliable signal we have at n=66."** Restated more carefully: per-track CV distinguishes broad classes of model (NNLS vs rank-loss → +3-5pp) but does not distinguish hyperparameter neighbors of the same loss (anchored vs no-anchor: 0pp). Multi-seed K-fold reshuffle is what distinguishes neighbors.

### Updated ship state

1. PR #88 (anchored weights) merged on `main` based on single-seed analysis. Stays merged but is not optimal.
2. **PR #89 (no-anchor retune)** ships the actual optimum. 1-file, 10-line weight swap. Same shape as PR #88 (12 of 14 features active, two seed features at zero), different active set, robust K-fold advantage.
3. Tuner harness PR landing alongside so the retune is reproducible from `main` after both land.

### Caveats that still apply

- All evaluation is in-corpus: every track was in the training set when these weights were fit. K-fold reshuffle measures ranking stability across random label-set subsets, not true out-of-sample generalization. The same caveat applied to PR #87 and PR #88.
- The bootstrap-CI lower bound is still slightly negative (-2.3pp). High-iteration runs (10000 iter) tighten this but won't move it materially without more tracks.
- The retune leans on rhythmic features (kick / phrase / high-mid). If the user's live setlist drifts toward genres where rhythmic onset is weak (ambient, drone, melodic-without-kick) the retune's corpus-fit may regress on those. Telemetry will tell us; offline tuning at n=66 won't.

### Updated meta-lesson

**Single-seed K-fold reshuffle is not enough.** Repeat across multiple seeds (5+ × 20 splits = 100 split-comparisons) for any ship decision. A single 10-split run at one seed can flip wholesale at a different seed when the effect size is comparable to the per-track variance. Track-level bootstrap CI on a fixed split is even less robust — it shares the same selection bias as the original holdout.

The original meta-lesson stands: bootstrap at the unit of independence (tracks). Add: don't trust a single seed of K-fold either. The cost of multi-seed is ~5× compute on a fast CLI; it would have caught PR #88's noise-level advantage immediately.

### Roadmap update

The roadmap from the resolution above stands, with one substitution:

1. ~~Merge PR #88~~ Merged. **Land PR #89 (no-anchor retune) next.**
2. Tuner-code PR ✓ landed.
3. **Telemetry first, then runtime wiring.** Append-CSV at the drop-selection call site so live performance generates a labeled dataset. This is the single highest-EV move now — every minute the laser runs in front of an audience produces ground truth that no offline corpus can match.
4. Pre-ship polish (earlier-beat tiebreaker + top-2 abstain) — defer until telemetry is producing data.
5. Live gig test. Failures become the next dataset.
6. Label more tracks (target ~150+) before any further offline feature work.
