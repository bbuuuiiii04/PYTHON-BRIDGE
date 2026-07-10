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

---

## Review batch B1 — operator verdicts on machine-picked AWR-184 edge cases

Mode switch (operator-approved ~18:35): the lane sweeps the library offline for
moments where the system is most likely wrong, the operator verdicts them. Sweep
evidence: 707 tracks scanned through live `build_track_plan` at `1e8ac71`; the
AWR-184 deep-sub-void rung fires on 104 drops / 80 tracks (bo4=46, bo8=34, bo16=24;
void lengths 2–64 beats). Executive ruling on the results: all three suspect classes
cleared by ear, NO AWR-186; misread evidence below hands to the successor.

### B1-1 · Ray Volpe - Laserbeam (TiDo Edit) · 0:12 · intro firing, 1-bar blackout

- **his words:** "it's fine, hardly a drop since there's no bridge defined buildup
  runway"
- **classification:** PARTIAL — behavior ACCEPTED as-is; the underlying ANLZ drop
  marker is not a real drop to his ear (marker quality, not rule defect).
- **systems:** f2, led

### B1-2 · ESSE - Work It x Dom Dolla - Take It (Bellevue Rework) · 0:15 · intro, 4-bar blackout (bo16)

- **his words:** "same scenario, rekordbox labels it as a drop but it's not really,
  just has bass coming in for the intro. fine how it is"
- **classification:** PARTIAL — behavior ACCEPTED as-is; same marker-quality root
  note as B1-1. The feared blackout-during-blend class is BENIGN per his ear.
- **systems:** f2, led

### B1-3 · House x Pressure — Matroda · 2:42.5 · breakdown-tail bo16 (64-beat void)

- **his words:** "yeah that's fine. could even warrant a 32 beat blackout. ur
  question is too ambiguous"
- **classification:** AGREES — long-void bo16 is right, and the cap may be RAISABLE
  (32-beat blackout named as acceptable there): a cap-raise datum, not a defect.
  Meta: batch questions must state exactly when black starts/ends (his ambiguity
  flag; tightened for future batches).
- **systems:** f2, led

### B1-4 · Scary Monsters and Nice Sprites (Levex Remix) · 1:12.7 · FIRST TRUE MISREAD

- **his words:** "yes 1 bar blackout is right, but tier 3 wall is wayy to aggressive
  for this track. probably more like a tier one wall. also what's the visual
  difference between wall tiers. this track reads as a bass house track"
- **measured:** drop b160 @1:12.7 WALL T3, violence 0.753 — a local spike (the
  track's other WALL drops sit T2 at 0.62–0.66); blackout 4 via deep-sub-void (sub
  voided 2 beats, growl min −15.1). Track identity: zone GLACIER (aggression 0.37,
  luminance 0.42, distortion 0.50), 132 BPM.
- **classification:** blackout AGREES; tier MISREAD — his ear: ~T1 wall, bass-house
  track; the scorer put its violence at 0.753/T3. First MISREAD of the session;
  tier-scorer evidence (F2/AWR-163 lineage), successor batch per executive ruling.
- **systems:** f2, led

### B1-5 · REWIND — Ray Volpe, Sullivan King · 0:52 · INPUT DEFECT, operator-fixed live

- **his words:** "track analysis for this was wrong and had the beatgrid misaligned
  by 2 beats. just fixed it. this track is probably one the most aggressive and hard
  hitting tracks in my library. this has a 4 bar blackout. wall tier 3"
- **his words (follow-up, 19:45):** "not even joking rewind is an absolute fucking
  monster of a track and rips people heads off. i expect full energy throughout
  every drop when playing that track" — intensity expectation: FULL ENERGY at every
  drop; treat as the acceptance bar for the post-re-analysis re-measure.
- **event:** he corrected the Rekordbox beatgrid mid-review (2-beat misalignment).
  The v4 cache key is the beatgrid fingerprint, so the old entry is orphaned; this
  lane re-extracted on the fixed grid via the system's own at-load path
  (`extract_spectral_features_v4` + `put_cached_v4`, atomic write — the same thing
  the overnight sweep would do; disclosed, not hidden). Old-grid plan read T1 WALL
  bo4 at 0:52 — vs his declaration WALL T3 + 4-bar blackout.
- **classification:** MISREAD on the old grid, root cause = input defect (beatgrid),
  NOT the scorer; post-fix re-measure = successor's first check (one command,
  tooling in the handoff).
- **post-fix re-read (19:44):** fixed grid = 497 beats, v4 re-extracted + cached OK —
  but the ANLZ carries **0 drop markers** right now (Rekordbox drops phrase data on a
  grid edit until re-analysis completes). Until markers return, the bridge has NO F2
  plan for this track: no drop presentation, no blackout, on one of his hardest
  tracks. LIVE NOTE for the operator: let Rekordbox finish (or re-analyze the track)
  before playing it in a mix; successor re-measures after markers return.
- **post-re-analysis re-measure (~19:50, operator re-analyzed; markers restored):**
  8 drops, all WALL (family AGREES) — but ALL EIGHT read **tier 1** (violence
  0.53–0.61) against his "wall tier 3 / full energy throughout every drop". The grid
  fix did NOT recover it: the tier scorer itself underrates this track on clean
  input. Diagnostic clue recorded, not theorized: identity distortion is MAXED at
  1.00 while aggression reads 0.39 — the aggression formula
  (`led_identity_v2.py:98-103`: punch/attack_low/grit/onset_mh) takes no input from
  the distortion/growl-timbre signal. Darkness at head: mostly blackout-1/dip, one
  blackout-4 @2:46.4 vs his "4 bar blackout". Paired with B1-4 (over-rated T3), the
  successor tier round now has pins in BOTH directions. Footnote: this re-extraction
  ran post-AWR-176 code, so REWIND is the first library track carrying
  `growl_centroid_frames` (8,562 frames).
- **systems:** f2, led, stems (grid fixes invalidate caches library-wide — pipeline
  note)

---

## Review batch B2 — post-close continuation at operator order (verdicts bank as briefs)

### B2-1 · TOXIC EVIL EDIT - SNAPT · 1:13.8 · blackout AGREES, tier+family MISREAD

- **his words:** "toxic is having wall hits, not good, this track is like a dark
  tech house track. blackout is perfect, definitely not a tier-3 WALL"
- **measured:** WALL T3 bo4 (2-beat void). Ear: dark tech house — WALL presentation
  firing is wrong (family), T3 inflated (tier).
- **classification:** blackout AGREES; tier + family MISREAD (over-rate #2).
- **systems:** f2, led

### B2-2 · OMG (BRLLNT Remix) — NewJeans · 3:09.0 · blackout AGREES, tier MISREAD, laser exclusion

- **his words:** "this is literally one of the most chill tracks i have. its a calm
  piano track and reads more like deep house. 1 bar blackout is perfect for this.
  wouldnt have any lasers on this track. super inflated"
- **measured:** HOUSE T3 bo4 (2-beat void). Ear: chill/deep house, "super inflated".
- **classification:** blackout AGREES; tier MISREAD (over-rate #3); PLUS a laser
  BEHAVIOR VERDICT: zero lasers on this track — relayed to executive.
- **systems:** f2, led, laser

### B2-3 · BEAUZ - OCHO (LAXTER HARD EDIT) · whole-track darkness density · precise tuning verdict

- **his words:** "this is a HARD techno track. 1:11 is correct, 1 bar for 1:59.6,
  5 bar blackout for 3:24, and then before each chorus there is a 1 bar blackout
  during the drop. darkness is warranted. btw, this track had phrase labels shifted
  by 1 beat, just fixed it."
- **decoded against the plan:** 1:11.6 bo16 CONFIRMED · 1:59.6 bo16 → TOO LONG,
  should be 1 bar (16→4) · **3:24 wants a 5-bar (20-beat) blackout the system does
  not have at all** (no firing there — successor measures what's at 3:24 post-fix) ·
  the three 1-bar blacks into 3:47.6/3:59.6/4:11.6 CONFIRMED ("before each chorus").
  Density verdict: five-plus blackouts in one hard techno track is RIGHT.
- **input defect #2 (operator-fixed live):** phrase labels were shifted 1 beat; he
  fixed them mid-review. Phrase-marker edit (not grid), so the v4 cache likely
  survives, but ANLZ markers may be absent until Rekordbox re-analysis completes —
  successor re-measures OCHO before trusting tonight's beat indices.
- **classification:** PARTIAL (density + most windows right; one too-long window;
  one wanted blackout entirely missing).
- **systems:** f2, led

### B2-4 · Everything In Its Right Place (SCRIPT Remix) — Radiohead · 3:05.8 · FIRST VOID-RULE FALSE POSITIVE

- **his words:** "this is a balloon buildup at 3:05.8 and this track is like a dark
  techno track, not t3 more like t1"
- **measured:** WALL T3, blackout 8 via deep-sub-void (5-beat void). Ear: the moment
  is a balloon buildup (he used the system's own darkness vocabulary), the track is
  dark techno, tier ~T1.
- **classification:** MISREAD ×3 — darkness kind (the AWR-184 rung's FIRST false
  positive: a buildup-shaped quiet is not a cut-shaped quiet; balloon was right,
  blackout wrong), tier (over-rate #4), family (dark techno vs WALL, misread #2).
- **systems:** f2, led

### B2-5 · Toxic (Levity Remix) — Britney Spears · 0:43.9 · EXCLUDED

- **his words:** "the track analysis on this song is completely fucked lmao
  rekordbox is struggling to compute this one skip this one or actually exclude it
  from the corpus"
- **classification:** EXCLUDED at operator order — input analysis (Rekordbox
  grid/phrases) is broken beyond use; THIRD input-defect track tonight (REWIND grid,
  OCHO phrases, Toxic total). ANLZ input quality is a real error source; entries
  from this track carry no calibration weight.
- **systems:** f2 (input-quality note)

## Review batch B3 — rapid tier audit (void-approached T3s) + LED routing finding

**Routing-table finding (measured in live config, `drop_look_routing`):** the LED
look pools are IDENTICAL across all four families at the same tier, and T2 ≡ T3
(same 11-look aggressive pool). Family currently differentiates LEDs only via F4
HOUSE seasoning; the real family/tier consequences live in darkness + lasers. Named
desk item queued: per-family visual languages (his "wall hits on a tech house
track" complaint + B3-4 "big bright sparkles" want).

### B3-1 · Like I Like It — Mau P · HOUSE T3 @0:58
- **his words:** "maybe t2" — soft over-rate (T3→T2).

### B3-2 · I Cannot (Extended Mix) — Anti Up · HOUSE T3 @1:19 · T3 CONFIRMED + P1 GOLD
- **his words:** "this track has the GROWL and EUPHORIC SUSTAIN that the bridge
  should be able to recognize T3 is warranted. from 1:20 1 beat after the drop there
  is a distorted mid growl about 7 beats long and then a euphoric synth sustain at
  1:27 for approx 11 beats and then repeats the loop once more until breakdown. same
  for drop 2 / 3."
- **measured:** zone ION (aggression 0.59). @1:20 (b177, 1 beat after drop b176 —
  matches his count): growl_band 32.8–33.9 dB across 8 beats — the HOTTEST growl
  amplitude of the night. @1:27: sustain_mid 18.6–20.9 sustained. Amplitude sees the
  growl plainly; the growl↔euphoric-sustain alternation (7bt/11bt, looping, drops
  2/3 same) is timbre structure = the P1 centroid's job. Richest P1 acceptance case
  in the corpus (durations given).
- **classification:** tier AGREES; growl structure PARTIAL pending P1 backfill.
- **systems:** f2, led, p1, stems (wobble/growl window)

### B3-3 · s.o.s (extended) — Jigitz, Tabi · HOUSE T3 @1:54 · EXCLUDED (4th input case)
- **his words:** "this track changes bpm for some reason, exclude but yes the bridge
  got the energy right at 1:54" — variable BPM; excluded from calibration weight,
  energy read noted as right.

### B3-4 · FETISH x Haluna - Taste That · HOUSE T3 @1:45 · T3 CONFIRMED + look verdict + growl
- **his words:** "yes house t3 but a wall look is not warranted, more like big
  bright sparkles. 1:45 is also where the bridge should recognize the 4 beat bass
  growl"
- **measured:** zone VOLT. @1:45 (1 beat before drop b224): growl_band 3.1 →
  25.6/29.1/28.9/33.0 — rises exactly at the drop, hot for ~4 beats then eases
  (his "4 beat bass growl" visible on amplitude).
- **classification:** tier AGREES; growl amplitude AGREES (timbre pending P1);
  LOOK verdict = presentation want ("big bright sparkles", not wall slams) —
  feeds the per-family routing desk item above.
- **systems:** f2, led, p1

### B3-5 · White Wine & Adderall (YUSSI Remix) — Chainsmokers · NEUTRAL T3 @1:08
- **his words:** "yes t3 neutral i think" — CONFIRMED (soft).

### B3-6 · Show Me Love x Perfect (Exceeder) (DANČI) · COMET T3 @2:06 · LIVE BEHAVIOR OBSERVATION
- **his words:** "big problem, the track plays differently whenever i re run the same
  drop. i dont see a comet at 2:06. well i did, but then i didnt."
- **mechanism (code-read, `led_dispatch_policy.py:2045-2054`):** the F2 family×tier
  set only NARROWS a preference and the director applies it FAIL-OPEN (empty subset ⇒
  full bank), with the look director rotating for variety — so different looks across
  re-runs of the same drop are design, not corruption. The sharper finding: the
  COMET-family T2/T3 pools contain NO comet-class look at all (same 11 strobe/burst
  looks as every family) — a comet can only arrive via fail-open to the full bank,
  which is exactly an intermittent comet. Config semantics, not scorer: family name ≠
  look content in the live routing. Relayed to executive; pairs with the per-family
  visual-language desk item.
- **classification:** OBSERVATION (behavior), not a perception grade.

### B3-7 · What Did I Miss (Hills Remix) — Drake · WALL T3 @1:28
- **his words:** "not exactly, maybe t2. this track also has a 4 beat growl the
  bridge should recognize."
- **measured:** @1:28 growl_band 3.7 → 16.1 → 28.5/30.5/31.4/31.5 (rises into drop
  b192, hot ~4 beats = his count) — GROWL PIN #3. Zone DEEP_POOL, aggression 0.33:
  another calm-zone soft over-rate (T3→T2), hypothesis-consistent.
- **classification:** soft tier over-rate; growl amplitude AGREES (timbre pending P1).
- **systems:** f2, led, p1

### B3-8 · BLACKPINK - JUMP (JAY ESKAR) · NEUTRAL T3 @2:45 · SCRIPTED
- **his words:** "this is a scripted track"
- **classification:** N/A-SCRIPTED — the room runs its SoundSwitch scripted timeline
  there (F2 stands down), so F2 tier has no live consequence on this track. Corpus
  rule derived: scripted tracks are EXCLUDED from tier-calibration acceptance sets.
- **systems:** f2 (calibration-set rule)

## Review batch B4 — threshold-edge T3s (violence 0.698–0.700)

### B4-1 · Age Of Love (Dave Summer Edit) · WALL T3 @1:30
- **his words:** "played the track and it didn't do a wall3 look. doesn't warrant one
  anyways since it's calmer dark techno track"
- **classification:** tier over-rate (calm dark techno — pattern-consistent) + a
  second live look-delivery non-fire observation (see B4-2 escalation).
- **systems:** f2, led

### B4-2 · SIGNAL — ISOKNOCK, Isoxo, Knock2, London Mars · UNDER-RATE #2 + AWR-184 FALSE NEGATIVE #1 + look-reliability escalation
- **his words:** "I LOVE TJIS TRACK. EVERY DROP WARRANTS WALL T3. also there is
  supposed to be a 2 bar blackout at 27s. and also it took me playing the first drop
  3 times to get the wall drop at the beginning. the third drop section of this
  track should be full wall drop strobe. and replaying the 3rd drop section multiple
  times didn't give me the wall drop"
- **measured (plan at HEAD):** 8 drops, only ONE T3 (b360 @2:34.3, v0.698 —
  borderline); rest T1/T2 with family FLAPPING WALL↔HOUSE within the track (his ear:
  all WALL T3). Second REWIND-class under-rate; zone ION aggression only 0.46.
- **AWR-184 false negative, mechanism CONFIRMED by measurement:** @0:27 the sub is
  voided to −52 dB for ~6 beats into drop b72 (@0:30.9 — his "2 bar" count matches
  at 140 BPM), but growl_band stays 19–28 dB (melodic layer over the void), so the
  rung's "growl dark (min < 5.0)" gate blocks the blackout. Plan gives balloon.
  Paired with B2-4 (false positive: buildup-shaped quiet), the rule's boundary is
  now pinned from BOTH sides: cut = sub void regardless of melodic overlay riding
  above it; buildup-quiet = not a cut even when sub+growl both fade.
- **look-delivery reliability (escalated):** 3 replays needed for the wall look on
  drop 1; the 3rd drop section never produced it across multiple replays. Consistent
  with rotation + fail-open preference (policy:2045-2054) making the T3 look class a
  lottery draw; note b328 (the 3rd section's first drop) is HOUSE T1 whose pool has
  NO wall-strobe at all. Operator expectation now explicit: family+tier should
  GUARANTEE the look CLASS, not merely prefer it.
- **systems:** f2, led, laser

### B4-3 · Cocaine Inside My Blunts — Disco Lines · WALL T3 @1:28 · over-rate + FALSE NEGATIVE #2
- **his words:** "absolutely not. played the track and it didn't do a wall t3, but it
  doesn't deserve one anyways at 1:28 or anywhere in the track. also should've been a
  1 bar blackout before 1:28"
- **measured:** approach to drop b192: sub sags −9/−11/−12 (hovering AT the −10
  threshold) then −28, growl holds 11–25 dB — the growl-dark gate blocks again, and
  the void-depth margin is borderline. AWR-184 FALSE NEGATIVE #2, same mechanism as
  SIGNAL plus a threshold-margin note. Tier: hard over-rate (calm-character pattern).
  Look non-fire observation #3.
- **systems:** f2, led

### B4-4 · Never Be Like You (it's murph Remix) · HOUSE T3 @1:41 · DESIGN WANT (no-void blackout)
- **his words:** "should've done a 1 bar blackout before the drop at 1:41. track is
  also colorful track. also at this track has synth sustains throughout the drop
  except for the first drop section"
- **measured:** NO void before b224 — sub climbs back to +27 dB before the drop.
  This blackout want is NOT a rule miss: it's a design want (pre-drop darkness where
  the music does not cut) — distinct bucket from SIGNAL/Cocaine. Palette note
  ("colorful track") + structure label: synth sustains through all drop sections
  except the first (euphoric-sustain / F4 material).
- **classification:** no tier verdict given; blackout = DESIGN WANT; structure PARTIAL.
- **systems:** f2, led, p1

### B4-5 · Latch — Disclosure/Sam Smith · HOUSE T3 @1:35 · over-rate (→T1) + input defect #5
- **his words:** "phrase analysis swapped a drop section with an up, fixed.
  absolutely not t3 btw this is t1."
- **classification:** hard over-rate T3→T1 (melodic house, calm-character pattern);
  FIFTH live input-defect fix (phrase drop↔buildup swap) — re-measure post-re-analysis.
- **systems:** f2

### B4-6 · Rude Boy (AANSE Remix) — Rihanna · HOUSE T3 @1:01
- **his words:** "no definitely not." — hard over-rate.

### B4 threshold tally (violence 0.698–0.700 = the current T3 line)
Of 6 judged: 4 hard over-rates (Age Of Love, Cocaine, Latch→T1, Rude Boy) + 1 no-tier
answer + SIGNAL confirmed-and-then-some (whole track under-rated). The 0.70 T3
threshold is TOO LOW as a pure violence cut; true T3 either sits higher or needs the
character/zone context term. Placement data for the successor tier round.

### Hypothesis update after B3 (honest revision)
B3 weakens the simple contrast story: 3 of 5 void-approached T3s CONFIRMED (Anti Up
ION, FETISH VOLT, Chainsmokers), 1 soft over-rate, 1 excluded. Over-rates so far
cluster on tracks whose CHARACTER is chill/dark-groovy (Scary Monsters GLACIER,
OMG chill piano, Radiohead dark techno, TOXIC dark tech house) while energetic-zone
T3s hold. Refined candidate: tier needs zone/character context (calm-zone tracks
reaching T3 = suspect), NOT a blanket void-contrast damp. Counter-note: REWIND is
GLACIER *because* the same aggression under-read drags its zone — zone is
downstream of the defect, not independent. Successor tests both.

All three tier over-rates tonight (Scary Monsters, TOXIC EVIL, OMG) are drops
approached through a deep sub void; the under-rate (REWIND) is a continuous
wall-of-sound track. Violence terms (punch/attack) are contrast-shaped, so a
silent approach may inflate them while sustained loudness suppresses them.
Testable: do void-preceded drops systematically score higher violence than
same-track non-void drops? (Selection-bias caveat: B-cases were drawn from the
void-firing list.)

14 primary entries across 3 fully-labeled tracks + 5 machine-picked review verdicts:
AGREES 5 · PARTIAL 5 · BLIND 1 · MISREAD 2 · BEHAVIOR VERDICT 1. Shipped from
labels tonight: AWR-184 (deep-sub-void blackout rung; both Utopia pins verified
through live seams) + blast-radius sweep clearing all three suspect classes (NO
AWR-186 needed). Successor batch (executive-pinned in handoff FINAL-STATE):
Scary Monsters tier misread · REWIND post-grid-fix re-measure · 32-beat cap-raise
datum · ANLZ intro-marker quality note. Protocol (sweep → operator verdicts →
bounded round) is the standing shape for label batches under the successor.
