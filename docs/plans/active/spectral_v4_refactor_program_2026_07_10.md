# Spectral v4 Decision-Layer Refactor — program charter (2026-07-10)

doc_status: current
truth_level: program charter (founding doc for the Fable/MAX refactor owner seat)
provenance: built from the independent SOL review (docs/research/sol_spectral_review_2026_07_09.md,
verdict NEEDS REFACTORING), the AWR-182 ear-truth corpus (33 entries), and tonight's
live evidence. Verified against HEAD lineage 2a370d2+.

## Mission (the operator's bar)

The lighting OS must HEAR what the operator hears: drop intensity ("rips heads
off" = top tier), real voids answered with bar-accurate darkness, per-track
character driving a distinct visual language, the growl axis driving lasers,
texture as timed musical spans. KEEP the v4 extractor/cache (sound foundation,
per SOL and the incumbent audit alike); REBUILD the decision layer that turns
measurements into family / tier / darkness / texture / growl / laser choices.

## Stage 1 — the ear benchmark (FIRST, blocking everything)

- Corpus: AWR-182's 33 entries + all usable prior labels. EXCLUDE: scripted
  tracks (B3 protocol rule), broken/fixed-grid tracks pending re-analysis
  (REWIND, OCHO, Latch re-measures), variable-BPM failures (s.o.s), unresolved
  versions (Girl$ until per-version re-labels).
- Anti-leak rules: models/formulas never see title, artist, content id, or any
  per-track threshold; held-out splits are GROUPED (a track and its edits/
  remixes leave together).
- Metrics (per SOL, adopted verbatim): tier error (ordered), family flapping
  rate (within-track transitions vs operator judgment), darkness start/end
  error in beats, growl span duration error, laser false-alarm/miss, and
  ±1/±2-beat marker-sensitivity (the 46%/63% tier/darkness flip rates are the
  baseline to beat).
- Deliverable: a runnable benchmark harness (minutes over the existing cache;
  no re-extraction) + the frozen baseline scores of TODAY's decision layer.
  Every subsequent stage must beat it on held-out tracks BEFORE acceptance.

## Stage 2 — decision-layer refactor over existing v4 data (the core)

Represent every drop with four separate views: (a) track-wide character across
genuine drops; (b) current section (~preceding 32–64 beats); (c) the approach
before the marker; (d) first-8 and following-8 landed beats separately.

- FAMILY: one stable track baseline from all genuine drops; local override only
  on strong per-drop evidence (kills SIGNAL's 4-flap; TOXIC's dark-tech-house
  misread is a baseline case). raw_gap leaves character (it is arrival, not
  identity).
- TIER: split **intrinsic hardness** (distortion — currently unread!, sustained
  growl duty, thickness, high-band abrasion, drum/bass density, track-relative
  rank, persistence) from **arrival impact** (attack, suddenness, lift,
  pre-gap). Arrival may shape landing drama; it must not masquerade as
  hardness. Zone/character-context damping per the B3 hypothesis. Both-direction
  pins: REWIND+SIGNAL up, Scary Monsters/TOXIC/OMG/Radiohead/Cocaine/Latch/
  Rude Boy down; the 0.698–0.700 threshold-edge set (B4) = the sharpening stone.
- DARKNESS: classify the approach SHAPE (true void / melodic swell / vocal-or-
  effect stop / relative dip / continuous / uncertain) from sub/full/perc/
  sustain shape over time; choose length from context with whole-bar results
  through 20/32 beats (OCHO tight-vs-Matroda long = context, not a global cap).
  Both-side boundary pins: SIGNAL b72 false-negative (melodic layer over a real
  void) vs the B2-4 false positive; Caramelle stays balloon; Killa/Utopia pins
  frozen; the unreachable 16-beat branch gets a real path or an honest death.
- TEXTURE: timed spans (growl 7 beats, sustain 11 beats), never 16-beat
  majority booleans (the vote that erased Sexy 3:38 — 1-of-16 — dies here).
  Add eighth/16th-note mid-high onset patterning for rattle + sparkle grain.
- MARKER ROBUSTNESS: ±2-beat descriptor pooling around markers (cue timing
  stays marker-authoritative); a marker-confidence field surfaces "this answer
  leans on the marker".
- GROWL/LASERS: independent `growl_strength` + timed growl spans +
  `laser_suitability` axes. Laser choice must never be inferable-only from
  family+tier (Utopia b384 "warranted" vs OMG "zero lasers" both violate that
  inference today). More laser labels wanted before the suitability output
  gates anything live.
- WOBBLE: two named outputs — amplitude_wobble, tone_wobble (the measured
  dominance conjunction: span≥0.3oct ∧ cconc≥0.15 ∧ cconc≥2×lconc) — neither
  drives lights until an operator scrub passes.

## Stage 3 — stems only where they beat refactored v4

Improved 33-track pilot first (~75 min, 1.52GB peak, measured); full 27h
resumable sweep ONLY after the pilot beats v4-only on held-out elements.
Audio-keyed storage projected onto separately-keyed beatgrids (grid fixes
re-bin, never re-separate). Per-stem 12–24 log-band tone shapes over time
(de-confounds vocals from bass growl). HTDemucs pinned + offline-only.

## Stage 4 — small explainable models, later

After ~75–150 independent track judgments: ordered tier model, family
classifier, darkness-shape classifier — trained offline, exported as a few
coefficients/tiny trees, runtime stays plain and explainable. NO end-to-end
lighting AI. MERT-v1-95M only as a disposable benchmark (pinned env,
transformers==4.38) if "rips heads off" stays unreachable — keep only if it
clearly beats the explainable hybrid on grouped holdouts.

## Governance

- Operator gates every stage; his mixes are the only live validation.
- Generalization law: whole-library features only; per-track tuning is death.
- Frozen constants (AWR-147 class) move only WITH the benchmark as evidence.
- Every consumer change ships staged + kill-switched; fail-open beats fail-dark.
- The owner seat runs its own org (tmux lanes only, NO Fable Agent-tool
  subagents), full adversarial review on all runtime-behavior rounds.

## OPEN DESIGN QUESTIONS (for the SOL one-shot review, 00:35)

1. Benchmark loss shape: how should tier error weight adjacent-tier misses vs
   two-tier misses, and should darkness length error be bar-quantized before
   scoring (his labels are bars) or scored raw in beats?
2. The intrinsic-hardness feature set: is track-relative rank (within-track
   normalization) compatible with the corpus-absolute violence philosophy, or
   does mixing relative+absolute reintroduce the contrast trap through the back
   door?
3. Approach-shape classifier: rules-first (explainable thresholds over the
   four-view shapes) or tiny-model-first with rule extraction after — which
   converges faster given ~33 usable labeled tracks TODAY?
4. Family baseline: what evidence bar justifies a local per-drop family
   override, and should override frequency itself feed back as a "family
   uncertain" signal to the look router (guaranteeing class stability)?
5. Marker pooling: is ±2 beats the right pool radius everywhere, or should the
   radius scale with the marker-confidence field (wider when confident-wrong
   markers are suspected)? What measurement decides?

## Sequencing note

Wave-2 of the look-authoring campaign (AWR-194's successor) keys off THIS
program's new tier/family semantics — the refactor owner announces when axes
are stable enough to author against.
