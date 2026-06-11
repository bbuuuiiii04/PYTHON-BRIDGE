# PR #88 Review Prompt — Anchored Rank-Loss Weights

Self-contained prompt for a code-review LLM (or human reviewer who hasn't seen the prior thread). Copy/paste into a fresh chat with PR #88's diff attached, or hand to a human alongside the docs below.

---

You are reviewing PR #88 for `rb_ss_bridge_v2`, a project that automates DJ laser shows by picking the exact drop beat for a track inside a 9-beat candidate window. Be willing to push back hard. We have already ignored several review cycles to get here, so we want adversarial scrutiny, not validation.

## What the PR does

Single change: replace the seven-active / two-seed weight set in `anlz_reader.py::MULTI_FEATURE_WEIGHTS_V2` with a nine-active weight set produced by an anchored pairwise hinge rank-loss tuner. **One file, ten lines.** No code changes, no test changes, no runtime behavior change beyond the new weights.

```
post_lift                  0.000000 -> 0.018090
pre_valley_depth           0.026830 -> 0.004451
downbeat_alignment         0.138414 -> 0.085715
distance_penalty           0.006134 -> 0.019825
kick_pattern_onset         0.000000 -> 0.352444
high_mid_pattern_onset     0.261845 -> 1.023799
phrase_energy_step         0.033573 -> 0.121384
spectral_balance_shift     0.407899 -> 0.000000
centroid_drop              1.000000 -> 0.663423   (was a manually-pinned seed)
spectral_flux_onset        1.000000 -> 0.251814   (was a manually-pinned seed)
```

The tuner that produced these weights is **not in this PR**. It will land separately in `tools/eval_smart_drop_algorithm.py`. This PR is *just* the weight swap so it can be reverted by reverting one commit if live performance regresses.

## Why we are doing this when the holdout number went down

This is the part you should challenge.

- PR #87 holdout exact: **74.6%** (1 alphabetical 21-track holdout)
- Anchored holdout exact: **60.4%** (same holdout)
- Naive read: -14pp regression, do not ship.

We claim that read is wrong because the holdout is contaminated as a test set. Nine models had been scored against it and PR #87 was the max; selection bias is unaccounted-for. Two pieces of evidence support shipping anchored anyway:

**Track-level bootstrap (1000 iter) on the same holdout:**

- PR #87: 74.6%, 95% CI [58.3%, 90.3%]
- Anchored: 60.4%, 95% CI [40.5%, 80.0%]
- Difference CI: [+0.0%, +31.2%] — **includes zero**, statistically indistinguishable.

(Note: the original bootstrap that produced ±8pp was resampling at the *drop* level. That overstated independence — drops within a track share BPM, mix engineer, and RB analyzer behavior. Track-level resampling, which is what we report above, gives ~3× wider CIs.)

**K-fold reshuffle (10 random 32/68 track splits, frozen weights, no re-tune):**

- PR #87 wins 5/10 by avg +6.8pp.
- Anchored wins 4/10 by avg +5.3pp.
- 1 tie.
- Mean diff across splits: +1.3pp.

The two weight sets are empirically equivalent on this corpus.

## Why anchored as the tiebreak

When two models are statistically indistinguishable, the tiebreak is principle:

1. **Right objective.** Anchored rank loss optimizes argmax-correctness (the metric). NNLS minimizes squared error on binary 1.0/0.0 targets (a proxy). The proxy disagreed with the metric on every recent experiment.
2. **Mechanical protection.** L2 anchor on seed features + L1 sparsity prevents "new feature crushes the seed weight" — the failure mode behind all eight prior regressions.
3. **Per-track 5-fold CV.** Anchored 78%, PR #87 NNLS-tuned 73%, PR #87 with seed hack 75%. At n=66 tracks, per-track CV is the most reliable signal we have.
4. **Removes a seed hack.** PR #87 manually pinned two features at weight=1.0 because NNLS wanted to crush them. Anchored handles those features without an override.

## What we want you to challenge

Rank these from most-to-least concerning, and add anything we missed:

1. **Is the "holdout is contaminated, treat the regression as noise" argument actually valid?** Or are we rationalizing a real regression away with statistics?
2. **Is per-track CV trustworthy at n=66 tracks?** It uses training data; PR #87 with the seed hack also did fine on it. Could anchored's 78% be artifact of the loss shape rather than generalization?
3. **The K-fold reshuffle uses frozen weights and re-evaluates on each split, but does not re-tune anchored on each split's training subset.** Is that the right comparison, or should anchored re-tune per fold to give it a fair shake on splits where the original training data was different?
4. **Active feature count grew from 7 to 9.** `kick_pattern_onset` (0.352) and `phrase_energy_step` (0.121) are now non-zero where they were zero under PR #87 NNLS. Is that a model-richness improvement or overfitting to the original training subset?
5. **`spectral_balance_shift` went from 0.408 to exactly 0.000.** That's a feature we believed was meaningful. The anchored tuner with L1 sparsity disagrees. Is the L1 too aggressive, or was `spectral_balance_shift` a false positive of NNLS?
6. **Are we conflating "PR #87 won the noise lottery" with "anchored is therefore safe to ship"?** The reshuffle shows neither dominates. That's an argument for *equivalence*, not for swap. We claim the principled tiebreaks (objective, regularizer, no seed hack) justify the swap. Push back if that reasoning is hand-wavy.
7. **Are there scenarios where anchored systematically loses to PR #87?** Look at the four splits anchored loses on — are they correlated by genre, BPM, year? If yes, anchored may be regressing on a specific track class even if it averages out.

## What is out of scope for this review

- The tuner code itself (separate PR).
- Bootstrap CI / K-fold reshuffle scripts (also separate PR — were ad-hoc here).
- Runtime wiring behind `RBSS_SPECTRAL_ENABLE=1` (Step 6, separate PR).
- Earlier-beat tiebreaker / top-2 abstain (pre-ship polish, separate PR).
- Whether the corpus needs more tracks (yes, but doesn't block this swap).

## Decision options

- **Approve.** The swap is justified, ship.
- **Approve with conditions.** Ship after we add X (specify).
- **Block.** The argument for swap is not solid; specify which step of the reasoning fails.
- **Block on missing data.** We'd need experiment Y before swapping; specify Y.

Give us your honest read in under 600 words. Specific is better than general. If you think we're rationalizing, say so directly — that is in fact the failure mode this whole PR exists to correct.

## Reference docs

- `docs/prompts/reviews/drop_detection_review_brief.md` — original problem statement, current shipped weights, history of failed attempts.
- `docs/prompts/reviews/drop_detection_review_v2.md` — the "stuck at 8 failures" framing that the reviewer LLMs ultimately reframed.
- Both docs include a "Resolution (2026-05-18)" section with the bootstrap/reshuffle numbers above.
- PR #88 commit message has the same numbers and the full feature list.
