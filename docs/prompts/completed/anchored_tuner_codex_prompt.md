# Codex Prompt — Anchored Rank-Loss Tuner + Validation Tooling

This prompt asks Codex to land the tuner code that produced PR #88's weights, plus the validation utilities (track-level bootstrap CI, K-fold reshuffle) that we used ad-hoc to make the ship decision. Goal: future re-tunes use the right objective and the right validation by default, and never recreate the methodological errors that produced our eight-failure stretch.

Hand this to Codex with the repo checked out at `main` (PR #88 already merged) on a fresh branch like `anchored-tuner-harness`.

---

## Task

Extend `tools/eval_smart_drop_algorithm.py` with three additions:

1. A new `rank_loss` objective for the existing `tune` subcommand (anchored pairwise hinge with L2 anchor + L1 sparsity, non-negative weights).
2. A new `bootstrap-ci` subcommand that does **track-level** bootstrap on a frozen weight set.
3. A new `reshuffle` subcommand that does K-fold random splits and reports per-split exact-correctness for one or two frozen weight sets.

Plus extend `evaluate` so reviewers can score arbitrary saved weights.

Stay self-contained on `numpy + scipy` (already in the `[analysis]` extra). Do not add new top-level dependencies.

## Context the agent needs

- Linear scoring model. Each beat in a 9-beat window gets `score = sum(w_i * f_i)`. Top score wins. Metric is **exact match** to labeled `correct_beat`.
- 14 features in `FEATURE_NAMES` (do not change the list or order).
- Production weights live in `anlz_reader.py::MULTI_FEATURE_WEIGHTS_V2`.
- Existing `_cmd_tune` does NNLS on a binary 0/1 regression target. That objective minimizes squared error on labels, which is the wrong objective — we evaluate on argmax-correctness within a window. Eight offline experiments past the previous peak regressed because of the objective mismatch (the tuner would crush "noisy but discriminative" features to fix MSE).
- The replacement objective is anchored pairwise hinge rank loss with L2 anchor on named features and L1 sparsity. Empirically equivalent to NNLS on holdout exact, higher per-track CV, no seed-pinning hack required.
- `_load_corpus`, `_labeled_drops`, `_training_matrix`, `_multi_feature_breakdown`, `_accuracy`, `_predict_v2_spectral`, `_format_per_track_holdout` already exist. Reuse them.

## Implementation: `tune --objective rank_loss`

Add `--objective {nnls,rank_loss}` to the `tune` subparser. **Default `rank_loss`** going forward; keep `nnls` reachable for backward compatibility.

For `rank_loss`, add these flags:

- `--margin FLOAT` (default `0.1`).
- `--anchor-l2 FLOAT` (default `1.0`). L2 strength on anchored features.
- `--l1 FLOAT` (default `0.01`). L1 sparsity strength on all features.
- `--anchor NAME=VALUE` (repeatable, default empty list). Anchors feature `NAME` toward `VALUE`. Unspecified features are not anchored.
- `--seed INT` (default `0`). Used for deterministic init.

Build the design from training-split rows only. For each labeled window where `correct_beat` lies in `[rekordbox_beat, rekordbox_beat+8]`, emit one pair `diff = features(correct_beat) - features(wrong_beat)` for each of the eight wrong beats in the window. Stack into `D` of shape `(P, F)` where `P` is total pairs, `F` is `len(FEATURE_NAMES)`.

Loss to minimize over `w >= 0`:

```
L(w) = (1/P) * sum_p max(0, margin - dot(w, D[p]))^2          # squared hinge
     + lambda_anchor * sum_{i in anchors} (w_i - anchor_i)^2  # L2 anchor
     + lambda_l1 * sum_i w_i                                  # L1 == sum since w >= 0
```

Optimize with `scipy.optimize.minimize(method='L-BFGS-B', bounds=[(0.0, None)] * F)` and an analytic gradient. Initialize `w_0` from the current `MULTI_FEATURE_WEIGHTS_V2` (so the optimizer starts from production, not from zero).

Output exactly the same format as the current `_cmd_tune`:

```
Tuned weights:
MULTI_FEATURE_WEIGHTS_V2 = {
    "feature_name": 0.123456,
    ...
}
```

Plus a footer with: number of pairs, final loss, count of zero-weight features, the per-track CV/holdout summary that the existing harness prints. **Do not** print condition number for `rank_loss` (it's a property of the regression matrix, not the rank-loss objective). Do print it for `nnls`, as today.

## Implementation: `bootstrap-ci`

```
python tools/eval_smart_drop_algorithm.py bootstrap-ci \
    --corpus PATH \
    --weights {shipped,nnls,FILE} \
    --split {holdout,training,all} \
    --n-iter 1000 \
    --seed 0 \
    --metric {exact,near}
```

- `--weights`: `shipped` reads from `anlz_reader.MULTI_FEATURE_WEIGHTS_V2`; `FILE` is a JSON or YAML file mapping feature name to float; `nnls` runs `_cmd_tune --objective nnls` once on training and uses the result.
- Resample at the **track level**: for each iteration, sample `N` track ids with replacement (where `N` is the number of unique tracks in the chosen split), aggregate all drops belonging to the sampled tracks, score them, compute the chosen metric.
- Output:

```
bootstrap-ci (track-level, n_iter=1000, split=holdout, metric=exact)
  point estimate: 60.4%
  95% CI:         [40.5%, 80.0%]
  mean:           60.5%
  std:            10.1pp
  unique tracks:  21
```

If `--weights` accepts two values (e.g., `--weights shipped --weights-b FILE`), also report the **paired difference CI** (resample tracks once per iteration, score both weight sets on the same sampled tracks, take the diff). The paired CI is what determines whether two weight sets are statistically distinguishable.

## Implementation: `reshuffle`

```
python tools/eval_smart_drop_algorithm.py reshuffle \
    --corpus PATH \
    --weights-a {shipped,FILE} \
    --weights-b {nnls,FILE} \
    --n-splits 10 \
    --holdout-frac 0.32 \
    --seed 0 \
    --retune-b   # optional flag
```

- Treat the corpus as a flat list of tracks ignoring its original `split` field.
- For each of `--n-splits` iterations, randomly partition tracks into train/holdout using `--holdout-frac`. Score both weight sets on holdout. Compute per-track exact accuracy.
- If `--retune-b` is set, re-run the rank-loss tuner on each split's training subset and use the resulting weights for B (this answers "did B win because the original training favored it, or because B's tuner is genuinely better?"). Default off — frozen weights only.
- Output:

```
reshuffle (n_splits=10, holdout_frac=0.32, retune_b=False)
  split  weights_a  weights_b  diff
   1      72.1%      69.8%     -2.3pp
   ...
   10     65.4%      71.2%     +5.8pp
  --
  weights_a wins: 5/10 (avg +6.8pp when winning)
  weights_b wins: 4/10 (avg +5.3pp when winning)
  ties:           1/10
  mean diff:      +1.3pp (a - b)
```

## Implementation: `evaluate --weights`

Add an optional `--weights {shipped,nnls,FILE}` flag to `evaluate`. Default behavior unchanged (uses `MULTI_FEATURE_WEIGHTS_V2`). With `--weights`, the v2-spectral variant in the summary table uses the supplied weights instead of the shipped ones. This makes ad-hoc reviewer comparisons cheap.

## Loading saved weights from a file

Accept JSON (`{"feature_name": 0.123, ...}`) or simple YAML (one `key: value` per line). Reject any file that contains a feature name not in `FEATURE_NAMES`. Missing names default to `0.0`. Print which features defaulted, if any.

## Tests

Extend `tests/test_eval_smart_drop_algorithm.py`. The fixture `FIXTURE` already supplies a synthetic corpus.

Add:

- `test_tune_rank_loss_runs_on_synthetic_corpus` — invokes `tune --objective rank_loss` on `FIXTURE`, asserts the output contains `MULTI_FEATURE_WEIGHTS_V2 = {`, asserts all weights are finite and non-negative, asserts at least one weight is positive.
- `test_tune_rank_loss_respects_anchor` — runs with `--anchor centroid_drop=1.0 --anchor-l2 100.0`, asserts the resulting `centroid_drop` weight is within 0.1 of 1.0.
- `test_tune_rank_loss_respects_l1` — runs with `--l1 10.0` (very high), asserts most features end up at zero.
- `test_bootstrap_ci_deterministic` — `bootstrap-ci ... --seed 0 --n-iter 50`, asserts the output is reproducible across runs.
- `test_bootstrap_ci_paired_ci_includes_zero_for_identical_weights` — passes the same weight set as both A and B, asserts paired diff CI contains 0.
- `test_reshuffle_deterministic` — `reshuffle ... --seed 0 --n-splits 3`, asserts reproducible output.
- `test_reshuffle_zero_diff_for_identical_weights` — A and B identical, asserts mean diff is 0 and ties == n_splits.
- `test_evaluate_with_weights_file` — writes a JSON weights file to a tmpdir, invokes `evaluate --corpus FIXTURE --weights tmpdir/w.json`, asserts exit 0 and summary contains the v2-spectral row.

Skip the rank-loss tests with `unittest.SkipTest` if `scipy` import fails (mirror the existing `test_tune_runs_when_analysis_extra_is_available` pattern).

## Backward compatibility

- `tune` with no `--objective` flag must keep working. Pick a default that does not silently change existing CI: keep current behavior (`nnls`) as the default if Codex is uncertain, and emit a deprecation warning to stderr telling future invocations to pass `--objective rank_loss`. Final default switch to `rank_loss` is a one-line follow-up after we confirm CI green.
- All existing tests must pass unchanged.
- `_cmd_evaluate` output without `--weights` must be byte-identical to the current output.

## Out of scope

- Do not change `anlz_reader.py` or any of the runtime scorers.
- Do not change `FEATURE_NAMES` or its order.
- Do not add new features.
- Do not touch any other harness subcommand (`scaffold`, `label-from-cues`).
- Do not add a build system, package, or new CLI entry point.

## Acceptance criteria

1. `python tools/eval_smart_drop_algorithm.py tune --corpus ~/smart_drop_corpus_filtered.yaml --objective rank_loss` produces weights for which `_format_per_track_holdout` reports per-track 5-fold CV ≥ 76%. (Anchored produced 78% in our run; allow 2pp tolerance for optimizer/seed variance.)
2. `bootstrap-ci ... --weights shipped --split holdout --n-iter 1000 --seed 0` reports a 95% CI whose width is between 25pp and 40pp on the real corpus. (Track-level CIs at n=21 are wide; if Codex reports a width <15pp, it is almost certainly resampling drops not tracks — that is the bug the whole subcommand exists to prevent.)
3. `reshuffle ... --n-splits 10 --seed 0` runs in under 30 seconds on the real corpus.
4. All existing tests in `tests/test_eval_smart_drop_algorithm.py` pass. New tests pass.
5. `python -m pytest tests/test_eval_smart_drop_algorithm.py -x -q` exits 0.

## Methodology guardrails (do not violate)

- **Bootstrap must resample tracks, not drops.** Every drop within a track shares BPM/mix/RB-quirks. Drop-level resampling overstates independence by ~3×. This is the single most important rule of this prompt.
- **Reshuffle must split tracks, not drops.** Same reason. A track must be entirely in train or entirely in holdout for a given split.
- **L1 must use `sum(w)` not `sum(|w|)` because we have `w >= 0`.** This keeps the objective smooth and lets L-BFGS-B converge cleanly.
- **Anchor only applies to features named in `--anchor`.** Unspecified features get no L2 penalty (they get L1 only). Do not silently anchor everything.
- **Tuner must not print to stdout from non-final outputs** (no progress bars, no per-iteration loss prints). Stdout is parsed by other tools; stderr is fine for diagnostics.

## Reference: weights produced by this tuner that shipped as PR #88

```
high_mid_pattern_onset    1.023799
centroid_drop             0.663423
kick_pattern_onset        0.352444
spectral_flux_onset       0.251814
phrase_energy_step        0.121384
downbeat_alignment        0.085715
distance_penalty          0.019825
post_lift                 0.018090
pre_valley_depth          0.004451
spectral_balance_shift    0.000000   (driven to 0 by L1)
onset_score               0.000000
broad_onset_score         0.000000
bass_pattern_onset        0.000000
low_mid_pattern_onset     0.000000
```

These were produced with anchors on the two then-newest features (`centroid_drop`, `spectral_flux_onset`) at seed=1.0 with `--anchor-l2 1.0` and `--l1 0.01`. The optimizer did not preserve those anchors at seed; it used the anchor as a soft prior and let the data move them to 0.66 / 0.25 respectively. That behavior is correct.

If your implementation lands within ~0.05 absolute of these weights given the same hyperparameters and seed, the tuner is faithful.
