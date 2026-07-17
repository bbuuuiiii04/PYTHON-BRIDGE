---
doc_status: current
truth_level: design-consultation brief for GPT-5.6 Sol (codex seat, xhigh) — AWR-195 laser path
last_verified_commit: a379740b
last_verified_date: 2026-07-17
validation_scope: >
  Read-only design task. Deliverable is a design document; no code is written,
  no repo file is edited, nothing live changes.
---

# SOLDESIGN — laser drop-span detector v2, algorithm design

You are GPT-5.6 Sol at xhigh, acting as a senior reasoning peer — NOT an
implementer. You read, you think, you design. You do not write code beyond
pseudocode, you do not edit any repo file, you do not run git commands. Your
single output file is stated below.

## Mission

Design detector v2 for laser-warranting drop textures in a DJ lighting bridge.
Detector v1 found candidate drops; the operator (a DJ) then personally ruled on
the top 50 by ear and corrected 36 of them. Your job: turn his verdict corpus
into the strongest honest detection algorithm the available features can
support. A Fable orchestrator gates your design and a separate cheap lane will
implement it afterward — write for that implementer: precise, feature-by-
feature, pseudocode where it helps, zero hand-waving.

## Evidence packet (read all of it before designing)

Ground truth (the crown jewels):
- `local/laser_drop_spans_2026_07_16/review_verdicts.jsonl` — 50 ear verdicts:
  27 yes / 21 no / 2 skip, `correction` fields verbatim from the operator.
- `local/laser_drop_spans_2026_07_16/review_verdicts_summary.md` — human copy,
  plus 4 volunteered gold tracks (2 of which he already hand-scripts to lasers).

Detector v1 (what you are replacing — understand its failure modes):
- `local/laser_drop_spans_2026_07_16/drop_span_hunt.py` — per-beat flag runs,
  gap-tolerant chains, growl = flatness>=0.14 & growl_band>=24dB & bass>=18dB;
  synth = stock sustained-synth rule. Anchor must start <=4 beats after drop.
- `local/laser_drop_spans_2026_07_16/rerank.py` — prominence scoring (duty ×
  length + arrival + recurrence + strong-span chains, weak spans = rests).
- `local/laser_drop_spans_2026_07_16/candidates.jsonl` — v1's full sweep output
  (628 primary + long-sustain records with per-span measurements).
- `local/spectral_night_2026_07_16/evidence_pack.jsonl` — all 1,665 TRUE drops
  (735 tracks) with per-drop spectral summary fields.

Feature source (what a detector can actually see):
- `spectral_profile.py`, `spectral_cache.py`, `audio_spectral_features.py` —
  the v4 per-beat cached features and flag definitions. Inspect what exists at
  what resolution; do not assume features that are not there. Raw audio
  re-analysis offline is permissible in principle but expensive — treat it as a
  last resort you must explicitly justify per feature.
- `local/laser_drop_spans_2026_07_16/master_copy.db` + `drop_span_hunt.py` show
  the track/beatgrid resolution machinery (pyrekordbox on a scratch DB copy;
  the live rekordbox DB is never touched).

## What the operator's corrections established (treat as fact)

1. True laser accents are mostly 4–8 beats and TAPER — v1's chains measured
   8-beat accents as 28-53 beat spans. Length honesty is the #1 failure.
2. On/rest/on cadence is common (8-8-8, 16-16-16) and recurrence across the
   section/other drops is confirmed signal.
3. STABS are first-class laser events his strongest yes ("1000% lasers") is a
   stab pattern: 4-beat growl, 2 stabs, growl again. Other confirmed stab
   shapes: 6 stabs in one bar; 3-beat per-bar sustains held every 4th bar;
   low bass horns stabbing. v1 structurally cannot see these.
4. Events may start up to +8 beats after the drop and often skip the drop's
   first beat.
5. Confirmed false-positive causes: sustained VOCALS ("ahhhh" read as texture),
   high-synth drop fakeouts, and wall-of-distortion hard techno where nothing
   stands out (the operator himself called hard techno a genuinely hard case).
6. A euphoric-synth class (non-growl) also warrants lasers, and laser character
   should follow texture character (aggressive vs soft vs wavy) — v2 should
   emit a texture-character label per detection, not just fire/no-fire.

## Hard questions your design must answer explicitly

- Taper-aware length: how to measure the accent's honest length (envelope decay
  on which feature(s)) so "8 beats then tapers" reads 8, not 28.
- Stab detection at per-beat cache resolution: what is detectable (per-bar
  repeating 1-2 beat hits?) and what genuinely needs sub-beat data; if sub-beat
  is required, say exactly what new offline feature extraction would be needed
  and whether a per-beat approximation is honest enough for v2.
- Arrival window 0..+8 beats without exploding false positives.
- Vocal rejection: which available features separate "ahhh" vocals from synth
  sustains; if none can, say so and propose the cheapest honest discriminator.
- Fakeout rejection (high-synth non-drop textures).
- Per-track normalization vs global thresholds: v1's salience-vs-track-norm
  diluted texture-rich tracks (the operator's New Sky lesson), yet hard techno
  needs some notion of "stands out". Resolve this tension explicitly.
- Anti-overfit: 31 positives / 21 negatives is small. Global parameters only —
  per-track or per-genre hand-tuning is banned (standing operator rule:
  features must generalize across his whole EDM library). Design the validation
  protocol: what must fit, what residual disagreement is honestly reported
  instead of tuned away, and how to detect memorization (e.g. leave-one-out on
  thresholds).
- Scoring: critique and improve rerank.py's prominence model (duty×length +
  arrival + recurrence) in light of the corpus.

## Deliverable

Write EXACTLY ONE file:
`local/laser_detector_v2_2026_07_17/sol_design.md` containing:
1. Findings first: v1 failure-mode analysis grounded in the corpus (cite item
   numbers), ordered by severity.
2. The v2 algorithm design: features used, per-stage logic, thresholds with
   rationale, pseudocode precise enough that an implementer needs zero design
   decisions. Label every claim [confirmed] (you read it in code/data),
   [assumed], or [unknown].
3. Validation protocol vs the corpus with anti-overfit guardrails and explicit
   pass/fail criteria.
4. Open questions / what only the operator's ear can settle.
5. Explicit list of anything you judged infeasible with current features and
   the honest fallback.

## Boundaries (non-negotiable)

- Read-only everywhere except the single deliverable file above.
- No implementation, no repo edits, no git commands, no commits, no branches.
- Never touch the live rekordbox master.db, the bridge runtime, laser/LED
  configs, or the pad/lab/sim services.
- Scripted tracks keep their existing lighting behavior — your design targets
  detection evidence only; WHEN lasers fire remains governed by the existing
  drop-presentation policy and is out of scope.
- The 4–16 beat window is the operator's; stabs and tapers refine it, they do
  not license minutes-long pad detection (a separate long-sustain list already
  exists).

## Completion signal (mandatory)

When the design file is written, run exactly:
`touch /tmp/rbss_lane_signals/codex.SOLDESIGN.done`
If blocked: `echo "<one-line reason>" > /tmp/rbss_lane_signals/codex.SOLDESIGN.blocked`
Also print SOLDESIGN-DONE (or SOLDESIGN-BLOCKED) on its own line. Run straight
through; do not pause for approval.
