---
doc_status: current
truth_level: research-note
last_verified_commit: 353dfa7
last_verified_date: 2026-07-09
validation_scope: >
  Analysis-only feasibility assessment (superman4 dispatch to the stems session): can a
  tone-tracking discriminator separate filter-sweep ("tone") wobble from loudness wobble,
  using ONLY the 33 kept stems-pilot envelope JSONs plus existing v4 cache series? All
  numbers measured this evening on real cache/envelope data via existing repo functions
  called read-only (growl_centroid_movement_measure, growl_centroid_wobble_flags,
  stems_pilot_metrics.modulation_strength). Zero code, config, cache, or runtime change;
  scratch scripts lived in the session scratchpad and are not committed. Findings are
  measurement evidence, NOT a consumable detector; any gate/class change needs its own
  spec + operator scrub round.
---

# Tone-wobble vs loudness-wobble: feasibility from kept envelopes + v4 cache (stems lane)

**Dispatch question.** The audit (AWR-166) and tonight's stems labeling found wobbles that
are TONE movement, not loudness (You&Me). What signal separates filter-sweep wobble from
loudness wobble, and would P1 centroid data unlock it?

**One-line answer.** The separator is *which channel carries the periodicity*: loudness
wobble = periodic growl-band LEVEL modulation (stems envelopes see it — LUNCH proved it);
tone wobble = periodic growl-band CENTROID movement while level stays flat — and the P1
centroid field is not hypothetical: **AWR-176 already landed and 905/950 v4 cache entries
carry real `growl_centroid_frames`**. Measured on that real data, a
centroid-dominates-level rule catches both of the operator's You&Me moments at ~5%
background fire-rate. The stems envelopes alone can never express tone movement; the
centroid series is the unlock. One sharp caveat: **the AWR-176 flags as currently gated
fire on 92–99% of beats on every track measured** — they need re-gating before the
operator scrub.

## Data used (confirmed)

- 33 kept stems-pilot envelopes (`stems_pilot/envelopes/`): per-stem band LEVELS only
  (beat + quarter-beat), plus frame-rate growl-band LEVEL for bass/other stems. No
  frequency-position series of any kind — bands split at fixed edges (bass stem: 20–60,
  60–150 Hz), quarter-beat sampling Nyquist-caps modulation reading at 2 cyc/beat.
- v4 cache: 950 entries, **905 with `growl_centroid_frames`** (AWR-176 backfill has run);
  frame-rate (~86 fps) harmonic 60–500 Hz centroid + the level series on the same clock.
- Anchors: operator session labels (You&Me Flume 1:20/3:05; LUNCH spans 42.4–68 /
  1:36–2:03), the documented capochino 1:01.7 and Girl$ 1:16.1/2:25.6 moments, and three
  no-wobble corpus controls (Tremor, One Chance, Temperature MERCO).

## Findings (all measured 2026-07-09 evening)

**F1 — The two families are real and live in different channels.**
LUNCH first drop (operator span, loudness wobble): stems level conc **0.349** @ 0.636
cyc/beat vs centroid conc median 0.149 — level channel wins. You&Me moments (tone
wobble): level conc 0.22/0.17 (below the 0.30 floor, why the stems gate missed them) vs
centroid conc **0.19/0.41** with 0.86/1.70-octave sweeps at 0.5 cyc/beat — centroid
channel wins, exactly where his ear said wobble.

**F2 — Raw centroid movement is ubiquitous, not discriminating.**
`growl_centroid_wobble_flags` (span ≥ 0.15 oct, conc ≥ 0.10, run ≥ 2) fires on 92.6–98.8%
of beats on ALL nine tracks measured — including the three no-wobble controls (Temperature
shows spans to 4.6 octaves). Cause: the full-mix growl centroid follows *musical content*
— basslines, note changes, kick harmonics — and a two-note bassline IS periodic tone
movement. Span+conc alone cannot gate wobble; the current AWR-176 acceptance test would
not separate as-is.

**F3 — The cheap conjunction works where the operator labeled.**
Candidate rule measured per 4-beat window: `span ≥ 0.3 oct AND centroid_conc ≥ 0.15 AND
centroid_conc ≥ 2 × level_conc` (tone periodicity DOMINATES level periodicity — a filter
sweep moves tone without loudness; a melody note-change moves both). Result: background
fire-rate collapses ~95% → **3.1–10.7%** across all nine tracks, and it **fires at both
You&Me operator moments** (0.19 vs 0.09; 0.41 vs 0.20) while LUNCH (loudness-type)
correctly does not fire it. The ~4–5% residual windows on controls are unlabeled-truth
(bass melodies vs real wobble unknown) — an operator-scrub question, not resolvable here.

**F4 — capochino and Girl$ documented moments stay marginal/uncaught.**
capochino 1:01.7: centroid conc 0.126→0.211 as the window widens ±2→±16 beats (level
0.07→0.16; ~1 octave span throughout) — the tone channel consistently reads *more* than
level but never decisively (dominance ratio ~1.4×, not 2×). The wows there are sparse and
quasi-periodic; a point-window periodicity measure dilutes them. Girl$ misses carry an
anchor caveat: 1:16.1/2:25.6 were measured on ONE unspecified Girl$ file and were applied
here to three different edits (YDG / W&R / RESET intro edit) whose timelines differ —
these are unreliable anchors until re-labeled per version (AWR-182 successor batch is the
right home).

**F5 — Stems envelopes alone cannot do this, in principle and in measurement.**
No stored stems series expresses frequency position (F1 data shapes above); empirically
all five tone-moments read stems level conc 0.10–0.27 — blind, as the pilot predicted.
The stems' contribution to a future tone channel is *scoping*, not detection: bass-stem
isolation would remove the vocals/lead confound the full-mix centroid carries.

**F6 — Answer to "would P1 unlock it": yes, and it already shipped.**
`growl_centroid_frames` (AWR-176, implemented + backfilled 905/950) is the necessary
signal and is sufficient *in conjunction with the level series* for the You&Me-class tone
wobble. It is not yet sufficient as-gated (F2), and capochino-class sparse wows need
wider windows and/or span-labels in the scrub round (F4).

## Recommendations (gated; none executed from this lane)

1. **Relay to the AWR-176 owner before its operator scrub:** current flag gates are
   non-selective on real data (F2). The scrub round should evaluate the
   centroid-dominates-level conjunction (F3) — it is pure derived-layer, zero extraction
   change — and score capochino with wider windows / operator span-labels (F4).
2. **P2 stems sweep schema (when authorized):** store per-stem `growl_centroid_frames`
   for bass/other alongside the level frames — same STFT pass, a few KB/track — so the
   tone channel gets stem-scoped and the melody/vocal confound drops (F5).
3. **Stems pilot wobble criterion:** keep the stems gate's wobble channel level-based
   (LUNCH validated it); tone-type labeled moments (You&Me) should be scored by the
   centroid lane, not held against the stems gate — a gate-design decision for the
   executive + operator, flagged in the lane report.
4. **Girl$ anchors:** re-label per version with the operator before using them as
   acceptance evidence anywhere (F4).

## Claim labels

- confirmed: F1–F6 numbers (measured this evening at `353dfa7` on live cache/envelopes).
- assumed: melody-vs-wobble explanation of control-track centroid movement (mechanistic
  reading of F2; consistent, not ear-verified).
- unknown: whether the ~4–5% residual F3 windows on controls are false fires or real
  wobble-ish texture; whether capochino clears any honest gate without span-labels.
