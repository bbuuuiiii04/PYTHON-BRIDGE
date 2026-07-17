---
doc_status: current
truth_level: program-design brief for GPT-5.6 Sol turn 3 (spectral v5, operator mandate 2026-07-17)
last_verified_commit: a6ef4120
last_verified_date: 2026-07-17
validation_scope: >
  Read-only design task. Deliverable is a program-design document; no code,
  no repo edits, nothing live.
---

# SOLV5 — spectral analysis v5 feature program design

You are GPT-5.6 Sol at xhigh, third turn on this program, again as senior
reasoning peer — design only, no implementation, no repo edits, no git.

## Operator mandate (verbatim, 2026-07-17)

"i'm willing to invest anything to make spectral audio analysis as accurate
and smart as possible. there is a way i'm sure."

That is the mission. Your v2 review (sol_review.md §4) proved the current
per-beat cached band features hit a structural ceiling: sub-beat transients
absent, vocal/synth inseparable, taste unencodable. The operator has now
removed the resource constraint. Design the feature program that breaks the
feature-poverty part of that ceiling — while staying honest that taste stays
an abstention, not a prediction.

## Evidence packet

- Your own `local/laser_detector_v2_2026_07_17/sol_review.md` (§4.2[b] is the
  seed you now expand into a full program), `validation_report.md`,
  `SEAT_REPORT.md`, the verdict corpus at
  `local/laser_drop_spans_2026_07_16/review_verdicts.jsonl`.
- Current feature stack: `audio_spectral_features.py`, `spectral_cache.py`,
  `spectral_profile.py` (v4: per-beat + quarter-beat bands, frame-rate 60-500Hz
  harmonic, HPSS-derived, 22050Hz/512 hop; cache keyed per track).
- Consumers to eventually serve (design for generality, laser evidence first):
  `lighting_moments_v2.py` families/tiers, drop texture evidence,
  energy/hardness offline stacks.
- Hardware: operator's Apple Silicon MacBook Air. Library ≈ 1,000 tracks.
  His music library is personal — prefer local inference; any cloud step must
  be justified explicitly and be optional.
- Ground-truth reality: 48 selection-biased decided records + 4 volunteered
  gold; TWO tracks he already hand-scripts to lasers are free positive labels;
  future labels accrue ONLY passively (timestamped vetoes during normal
  mixing, voluntary volunteered examples) — structured listening sessions are
  permanently banned. Design the label-accrual story accordingly.

## Design axes (answer each explicitly)

1. **Windowed high-resolution transient re-analysis** — your §8.1 sketch,
   now fully specified: exact extraction, storage schema, cost per track,
   what it provably recovers (the 3.7dB stab case is the acceptance example).
2. **Source separation stems** — model choice (Demucs family or better;
   license, local speed on M-series, quality trade-offs), what per-stem
   spectral features unlock (vocal rejection becomes vocal-share; bass-stem
   growl purity; synth-stem sustains), full-library feasibility, v5 cache
   schema for stem features.
3. **Pretrained music-understanding embeddings** — candidates (MERT, CLAP
   family, or better as of 2026), local inference feasibility, beat/window-
   synchronous pooling design, and precisely what they buy: character labels
   (aggressive/euphoric/soft) as embedding-space neighbors of his labeled
   examples, retrieval-style scoring vs small-classifier risk at n≈50.
   Address overfit honestly — what usage of embeddings is defensible at this
   label count, what must wait for label growth.
4. **Passive corpus growth** — how each live veto/volunteered timestamp flows
   into the immutable label store; what label count unlocks what (thresholds
   for enabling learned components); zero operator burden by design.
5. **Validation architecture** — repaired evaluator lineage (the fix round is
   addressing your findings), track-grouped protocol extended to growing
   labels, promotion gates for each stage.
6. **Staging** — order stages by certainty-of-payoff per unit effort; each
   stage independently shippable into the evidence engine; name what stage 1
   is and why. Dependencies isolated from runtime (separate venv under
   `local/` or `tools/`, zero runtime importers — the bridge's 200Hz loop and
   its dependency set must be untouchable by this program).

## Boundaries

- Design only; one deliverable file; read-only otherwise; no git.
- Offline stack only — nothing here may import into or change bridge runtime.
- No per-track/per-genre tuning; global, generalizing features only.
- Taste/musical-warrant remains abstention-honest: design where human
  authority stays, never a hidden genre hack.

## Deliverable

Write EXACTLY ONE file: `local/spectral_v5_2026_07_17/sol_program_design.md`
(create the directory) — findings-first, claim-labeled ([confirmed]/[assumed]/
[unknown]), pseudocode/schemas where an implementer needs them, staged plan
with per-stage acceptance gates. A parallel adversarially-verified web
research pass on the same SOTA landscape is running; mark model-choice claims
that deserve cross-checking against it with [verify-vs-research].

## Completion signal (mandatory)

`touch /tmp/rbss_lane_signals/codex.SOLV5.done`
(blocked: `echo "<reason>" > /tmp/rbss_lane_signals/codex.SOLV5.blocked`)
Print SOLV5-DONE (or SOLV5-BLOCKED) on its own line. Run straight through.
