---
doc_status: current
truth_level: labeled-evidence-corpus
last_verified_commit: f0b40ba
last_verified_date: 2026-07-09
validation_scope: >
  Operator ear-truth labeling corpus (AWR-182, evening labels session 2026-07-09,
  operator-attended). Each entry pairs the operator's verbatim statement about a named
  track+timestamp with what the v4 spectral analysis + F2 plan measurably see there,
  via the real seams (read_anlz_drops, spectral_cache.get_cached_v4,
  led_identity_v2.identity_scores/assign_zone, lighting_moments_v2.build_track_plan),
  measured read-only at the commit above. Classifications grade the analysis, not the
  operator: his ear is ground truth. Machine layer (same entries as JSONL):
  local/labels/operator_track_labels_2026_07_09.jsonl (gitignored). Labels here change
  no behavior; they are calibration/acceptance evidence for future rounds (P1 growl
  centroid acceptance set, F2/LED/laser/stems tuning).
---

# Operator track labels — 2026-07-09 evening session (AWR-182)

How to read an entry:
- **his words** — verbatim operator statement (ground truth).
- **measured** — what the analysis sees at that timestamp, from the real seams at the
  header commit. All dB values are the v4 corpus-absolute scale.
- **classification** — `AGREES` (analysis sees it) / `PARTIAL` / `BLIND` (analysis
  cannot express it; the missing dimension is named) / `MISREAD` (analysis contradicts
  his ear).
- **systems** — which consumers the statement bears on: `f2` (drop plan), `led`,
  `laser`, `stems` (relayed to the stems session), `p1` (growl-centroid acceptance).

P1 context tonight: `growl_centroid_frames` exists only for fresh extractions; the
library backfill sweep runs after 20:00. Growl statements tonight are measured on
amplitude (`growl_band_db` / `growl_band_frames`) and become the P1 acceptance set
once the backfill lands.

---

## Sexy (Extended Mix) — Matt Sassari (content_id 216468125)

Track dossier (measured 2026-07-09): 708 beats / 5:21, 8 drops, 5 buildups; identity
zone DEEP_POOL (aggression 0.12, luminance 0.02, distortion 0.63); F2 plan: b192 WALL
T2 blackout, b480 HOUSE T2 blackout, remaining six drops T1 snap.

### 3:38 — carried over from the 2026-07-09 live session (executive-measured; re-measured tonight as the session smoke test)

- **his words:** "aggressive tech house bass growl for 8 beats then tapering" — the
  ONLY drop of this track he hears that way (source: AWR-176 spec Part E, operator
  live-labeled 2026-07-09).
- **measured:** 3:38 → beat 479; the drop is b480 (3:38.2). `growl_band_db` next 8
  beats: 24.7, 27.4, 27.3, 27.9, 27.8, 27.8, 27.5, 27.7 — flat ≈27 dB, and flat at
  the same ≈27 dB across ALL 8 drops of the track; frame-level growl mean 26.9 dB
  (n=156 frames). Sub sustained ≈32.6 dB. F2 does rank it: HOUSE T2 (violence 0.620)
  blackout, white_share 0.25. `growl_centroid_frames` = 0 entries (pre-backfill).
- **classification:** BLIND — the growl's aggressive character and its taper are
  timbre movement (WHERE the growl tone sits over time); no stored series can express
  it. Missing dimension = frame-rate growl-band centroid, exactly AWR-176/P1. Tier
  partially compensates (T2 ranks it big) but cannot say "growl".
- **systems:** p1, led
- **notes:** This entry is the session's seam smoke test: values reproduce the
  executive's desk measurements from the AWR-176 spec (growl mean ~27.0, 8 drops,
  bass/sub sustain flat). Becomes a named P1 acceptance case after the backfill.

---

## Utopia — Dombresky (content_id 67676901)

Track dossier (measured 2026-07-09): 590 beats / 4:40, ~126.0 BPM; 8 ANLZ drops in two
phrase groups (1:01–1:47 and 3:02–3:48 — the operator hears TWO drop sections, ANLZ
marks 8 phrase-level drops); 5 buildups (b16/b48/b64/b256/b320); identity zone ION
(aggression 0.44, luminance 0.78, distortion 0.00); build_move fuse; the ONLY T2 drop
is b384 @3:02.9 (all others T1) — the plan agrees the final section opener is the
track's peak. 1 bar = 4 beats ≈ 1.90 s at this tempo.

### UT-1 · 0:00–1:00 intro

- **his words:** "from beginning to 1:00 — empty atmospheric section with vocals and
  general ambiance"
- **measured:** @0:30 (b62): full_db 3.3–7.5 (vs ~15–16 in drops), perc_full ~0.1,
  onset_mh 0–2/beat, sustain_mid 15–20 dB (held tonal content), centroid ~1.0–1.5 kHz,
  growl_flatness 0.0 (tonal, not noisy). ANLZ marks buildups INSIDE the intro
  (b16@0:07.6, b48@0:22.9, b64@0:30.5). No vocal dimension exists in v4.
- **classification:** PARTIAL — "empty/atmospheric" is clearly visible (very low full
  energy, near-zero percussion, sustained tonal content); "with vocals" is invisible —
  missing dimension = vocal presence (no vocal detector in v4; stems separation is the
  path that could express it).
- **systems:** stems, led
- **notes:** vocal-PRESENT window 0:00–1:00 relayed to the stems session.

### UT-2 · 1:00 drop

- **his words:** "1:00 drop groove section"
- **measured:** ANLZ drop b128 @1:01.0. Entry slam measured: sub −0.7 → +32.5 dB,
  full 2.7 → 16.4 dB, attack_low spikes 29.6/45.1 dB at entry. F2: NEUTRAL T1
  (violence 0.535), balloon darkness, white 0.32; groove bass pattern
  `BB......BB.BB.B.` (syncopated 16ths).
- **classification:** AGREES — drop seen within 1 s of his call; groove (syncopated
  bass-forward pattern) expressed.
- **systems:** f2, led

### UT-3 · 1:27 "2 bar blackout"

- **his words:** "1:27 2 bar blackout"
- **measured:** real musical void, exactly 2 bars: sub collapses 30.7 → −28.7 dB
  (b184–b191, ≈1:28–1:31.4), bass 24.7 → −26, full 15.1 → ~3, growl fades to −4.3;
  resolves into ANLZ drop b192 @1:31.4. The analysis SEES the void plainly. The F2
  plan's answer at b192 is balloon-shrink ("melodic build", perc 0.21 < 0.35) — NOT
  blackout.
- **classification:** AGREES (the musical cut is fully measurable) — with a flagged
  PLAN GAP: the operator's word is "blackout", the plan's darkness kind there is
  balloon-shrink. Relayed to the executive as a possible behavior verdict (this lane
  changes nothing).
- **resolved (same evening):** AWR-184 (`788a358`) added a deep-sub-void blackout
  rung; re-measured through the live seams at `1e8ac71`: b192 now reads **blackout 8**
  ("sub voided 6 beats (< −10.0 dB) with the growl band dark (min −4.3 < 5.0) into
  the drop") — 8 beats = his exact "2 bar" count. Software-verified only; the room
  going black is proven at his next mix.
- **systems:** f2, led, laser

### UT-4 · 2:02 breakdown

- **his words:** "2:02 atmospheric breakdown section with percussive elements
  dissipating. this section mirrors the beginning section"
- **measured:** ANLZ marks b256 @2:01.9 as a BUILDUP (its phrase vocab has no
  "breakdown starts here" that fires at this boundary; no breakdown markers extracted
  for this track at all). Energy fade measured: sub 18.4 → 12.6, full 6.5 → 2.4 over
  8 beats; perc_full still 0.3–0.5 at 2:02 (dissipation not yet complete in-window).
  Values DO rhyme with the intro (@0:30: full 3–7, sub 13–16, sustain 15–20,
  centroid 1–1.5 kHz vs @2:02: full 2–7, sub 12–18, sustain 10–18, centroid
  1.2–2.8 kHz).
- **classification:** PARTIAL — the fade is measurable and the section's character
  matches the intro numerically, but (a) the structure vocab calls the boundary a
  buildup, not a breakdown, and (b) "mirrors the beginning" is inexpressible —
  missing dimension = section-similarity / reprise recognition.
- **systems:** f2, led

### UT-5 · quiet buildup into the second drop section

- **his words:** "very quiet buildup leading up to the second drop section"
- **measured:** ANLZ buildup b320 @2:32.4 → drop b384. The approach is the quietest
  measured stretch of the whole track: full_db reaches −2.6 (negative — nowhere else
  measured this low), sub slides to −16.7, growl to −4.4 (beats ~379–382).
- **classification:** AGREES — buildup marker exists and "very quiet" is literally
  the track's measured minimum.
- **systems:** f2, led

### UT-6 · 3:00 "1 bar blackout"

- **his words:** "3:00 1 bar blackout"
- **measured:** deepest trough of the track, ≈1 bar: beats 379–382 (3:00.5–3:02.4)
  full −2.6…+1.1 dB, sub −10.9…−16.7, growl −4.4; pickup transient at b383
  (attack_low 33.0 dB) then drop b384 @3:02.9 slams (sub +32.4). F2's answer at b384
  is again balloon-shrink ("melodic build", perc 0.28 < 0.35) — NOT blackout.
- **classification:** AGREES (musical cut measured at 1-bar scale) — same flagged
  PLAN GAP as UT-3 (balloon vs his "blackout"); relayed together.
- **resolved (same evening):** AWR-184 (`788a358`): b384 re-measured at `1e8ac71`
  reads **blackout 4** ("sub voided 2 beats (< −10.0 dB) with the growl band dark
  (min −4.4 < 5.0) into the drop") — 4 beats = his exact "1 bar" count.
  Software-verified only; room proof = next mix.
- **systems:** f2, led, laser

### UT-7 · 3:02.5 final drop — eighth-note rattle

- **his words:** "3:02.5 drop section with unique eight note rattle"
- **measured:** drop b384 @3:02.9 = the track's ONLY T2 (violence 0.632), white_share
  0.66 (highest of the 8), NEUTRAL family, balloon darkness. Mid/high onset density
  runs 4/3/4/3 alternating per beat through the section (vs 3/2/3 at the first drop) —
  the rattle raises measurable onset activity, but v4 has no rhythmic-pattern
  signature to say "eighth-note rattle" as a motif.
- **classification:** PARTIAL — the drop, its peak rank, and elevated mid/high onset
  activity are seen; the rattle AS A RHYTHMIC MOTIF is inexpressible — missing
  dimension = rhythm-pattern/periodicity signature over mid-high percussion (adjacent
  to the audit's P3 kick-signature rider, but for hats/rattle).
- **systems:** f2, led, stems
- **notes:** rattle = percussion-element label; relayed to stems (element floor).

### UT-8 · 3:02.5 — lasers warranted (BEHAVIOR VERDICT)

- **his words:** "lasers are warranted here (compliments melodic element, last drop
  section in song, other variables)"
- **measured context:** b384 is the track's peak (only T2), melodic character
  (perc 0.28 → "melodic build" rule fired; growl_flatness ~0.0–0.1 tonal), zone ION
  (bright/melodic: luminance 0.78, distortion 0.00) — the system's own reading of the
  moment is consistent with every justification he named.
- **classification:** BEHAVIOR VERDICT (not a perception gap) — recorded verbatim and
  relayed to the executive seat; no config/code/laser change from this lane.
- **systems:** laser
