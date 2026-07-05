---
doc_status: current
truth_level: strict-review — code-verified at HEAD + measured (read-only)
last_verified_commit: f30f1e6
last_verified_date: 2026-07-05
validation_scope: strict review only — read-only verification of the v4 analysis layer and the LIGHTING ENGINE v2 design; code reading at HEAD, test-suite execution, and read-only computations against the v4 cache / Rekordbox DB / ANLZ files; no behavior change, no hardware validation
---

# LIGHTING ENGINE v2 — Strict Review (v4 capability + v2 feasibility/creative phase gate)

Fable 5 strict review (2026-07-05, `docs/prompts/fable_lighting_engine_v2_strict_review.md`).
Two targets: **(1)** the schema-v4 spectral analysis as built — implementation correctness and
whether its measurements carry what every v2 feature needs; **(2)** LIGHTING ENGINE v2 as
designed — feasibility and creative design, now that the built v4, the operator's beat-by-beat
walkthroughs (Appendices D–G of the build record), and the haze answer exist. This document is
the gate for the expansion phase (the full v2 experience design one-shot); §6 is its charter.

Evidence: all v4 code read in full at `f30f1e6` (`audio_spectral_features.py`,
`spectral_profile.py`, `spectral_cache.py`, `tools/spectral_sweep.py`, the
`state_manager.py:250-273` seam, the `anlz_reader.py` scorer consumer, `__main__.py:896-897`
eviction, all three test files); the full unit suite executed; the build record
(`docs/research/spectral_audio_analysis_redesign.md`), design record
(`docs/research/spectral_palettes_arrival_crossfade_exploration.md`), and first review
(`docs/research/lighting_engine_v2_design_review.md`) read in full; v1-stack seams re-verified
at HEAD (two build waves landed since the first review's `4a24209`); read-only measurement
scripts run against the real v4 cache + Rekordbox DB + ANLZ files (results inline, labeled
**measured (this review)**). Named measured facts from the build record were not re-derived;
several were independently spot-reproduced.

---

## 1. Verdicts

### Target 1 — the v4 analysis as built: **PASS WITH REQUIRED FIXES**

Plain language: the v4 layer is real, honest, and well-built. Everything I could re-measure
reproduced exactly — the cache is 666 entries / 203.5 MB to the decimal; the v3-compat block
is bit-identical to the old extractor on a real library track (I ran the retained gate
myself); the stored per-track scalars recompute exactly from the stored series; Can't Say
Nah's drop vector, Chemicals' giant sustained-synth blocks, and LUNCH's wobble timestamps all
come out of the shipped code the way the report says. The suite is green (the one failure the
report called pre-existing has since been fixed). The required fixes are not in the
extraction layer — they are in the last inch between the stored data and the lighting
behaviors it exists to drive: the shipped pre-drop-blackout sizing chain returns **zero** on
every single drop of the three walkthrough tracks (S-1), the tech-house "growl" the operator
described gets no growl flag at all (S-3), and a handful of report claims are worded stronger
than the shipped code delivers (S-4). All fixes are consumer-side rules over data that is
already stored — no re-extraction, no schema change, no identity epoch.

### Target 2 — LIGHTING ENGINE v2 as designed: **PASS WITH REQUIRED CHANGES**

Plain language: the design holds up against the built reality better than most paper designs
do — the backfill gap the first review flagged (F-2) is now closed by the sweep, the identity
epoch hazard (F-9) was closed by v4's own design, the silence primitive (P-2/F-16) exists as
one shared function, and the drop-type vector the classifier needs is shipped and proven
discriminative. The walkthroughs confirm the design's shape: the operator's cue vocabulary
maps onto the existing role system, and his palette instincts for the two anchor tracks match
the measured axes. Haze being IN re-opens beam-based laser design — the biggest creative
unlock since the record was written. The required changes: the first review's structural
texture gate contradicts the walkthroughs and must be revised (S-2); the blackout feature
must be specified against the real consumer rules S-1 names, not the idealized "scan
backwards from the drop" prose; the walkthroughs surfaced four consumers the design has not
yet named as derivations (S-5); and the kill matrix, moment arbiter, and color-slot contract
the first review demanded are still unwritten paper — they remain required, and the arbiter
gains new members from the walkthrough behaviors.

---

## 2. Findings (severity-first)

Severity reflects consequence for the expansion phase and the Feature 1–4 specs, not code
risk — nothing here executes at runtime yet (the derived views have no runtime callers at
HEAD; only the compat view feeds the scorer, verified `state_manager.py:255,268`).

### S-1 (High, both targets) — The pre-drop blackout chain returns 0 on every validated drop; the data is sufficient, the shipped consumer rules are not.

**Location:** `spectral_profile.py:121-129` (`bottom_gone_flags`, sub<5 AND bass<8),
`spectral_profile.py:176-192` (`pre_drop_gap_beats`, strict backward scan from `drop_beat-1`);
build record §4.4, §5 R6, §6.5, Appendix B.

**Measured (this review):** running the shipped chain on the shipped cache + real ANLZ drop
markers:

| Track | Drops (ANLZ) | `pre_drop_gap_beats` | Nearest empty-floor run (shipped rule) |
|---|---|---|---|
| Kai Wachi — ILL | 109, 141, 261 | **0, 0, 0** | (100–107) ×8 ends 2 beats early; nothing near 141; (258–259) ×2 ends 2 beats early |
| Can't Say Nah | 128, 160, 192, 224, 352, 384, 416 | **0 ×7** | (324–349) ×26 ends 3 beats early at 352; nothing at 128 (sub gone beats 120–126 but bass band 9–13 dB → AND-rule sees floor present) |
| STARsound (pt3) | 131, 163, 227, 331 | **0 ×4** | (126–127) ×2, but sub returns at beats 128–130 **before** the marker; at 331 sub-only gap sits at 321–325 with bass band present, sub back at 326 |

Three distinct failure modes, all consumer-side:

1. **Strict adjacency breaks on pickups.** Real drops carry a 1–2 beat pickup/riser hit right
   before the marker (ILL beat 108: sub 3.3 but bass 13.0; ILL beat 260: bass 27.0; CSN beat
   350: bass back to 11.3 with sub still gone at −11.3, then beat 351: sub back to 19.5). A
   scan that requires the gap to touch `drop_beat-1` finds nothing on any of these.
2. **The AND-rule under-reads the operator's "lows out".** In build bars the sub floor is
   genuinely gone while 60–150 Hz percussive/riser content keeps the bass band above 8 dB.
   Every Appendix B gap claim reproduces only under a **sub-only** rule: ILL 97–108 = the
   exact "12-beat empty floor ending exactly at drop beat 109" (measured: beats 97–108 all
   sub<5; beats 99 and 108 have bass 13.6/13.0 so the shipped AND-rule truncates to 8 beats
   and breaks adjacency); ILL 138–140 = the exact "3-beat gap before drop 141" (bass 14.7/14.4
   at 139–140 kills it under AND, leaving a 1-beat run below `min_len`).
3. **Audio can lead the marker.** STARsound's sub returns at beat 128 with the drop marker at
   131 (operator's own marker; markers are authoritative). A marker-anchored blackout that
   ignores the audio would hold darkness over three beats of full sub.

**Why it matters:** this is the flagship Feature-2 moment ("audio-matched pre-drop blackout",
addendum 3, review 2.7/F-16) and the single behavior the operator described in *both*
walkthroughs. As shipped, the chain would produce zero blackout on every one of his examples
— worse than the fixed 4-beat predark v1 already has.

**Required fix (consumer rules, no schema change — every input is already stored per beat):**
the Feature-2 spec must define the blackout scan as: (a) find the last floor-absent run ending
within a small tolerance (2–3 beats) of the drop marker, not strictly adjacent — the pickup
beats stay lit (or dark; taste call) but the gap is *found and sized*; (b) the floor-absence
notion for this consumer is **sub-only** (`sub_db < threshold`), matching the operator's ear
on all three tracks, with the AND-rule retained for the texture-darkness consumer if the live
pass prefers it; (c) a **floor-returned abort**: blackout ends early the moment `sub_db`
returns, regardless of marker (covers STARsound); (d) the **relative-dip** reading (the report
already names this gap honestly): a full-band drop of ~4+ dB against the local context with
the floor still present (CSN beat 127: full 10.4 vs 14.8, sub present — the operator's "minor
percussive cut → 1-beat blackout"; STARsound 2:12.4) is a second, distinct darkness trigger
class. Also correct the report claims (S-4).

**Label:** confirmed (measured this review; script results above; exact band values printed
per beat).

### S-2 (High, target 2) — The first review's structural texture gate contradicts the operator's walkthroughs; revise the mechanism, keep the containment.

**Location:** first review ruling 4.2 ("gate texture application at the dispatch policy on
role ∈ {groove, ambient} so it *cannot* touch drop/buildup/landing cues"); build record
Appendix G walkthrough 1.

**The conflict:** the operator's Can't Say Nah walkthrough explicitly asks for
texture-reactive seasoning **inside the drop phrase**: "growl beats get the strobing sparkle
(rt drop chase); the regular driving beat gets rt post drop chase." Under ruling 4.2 as
written, texture cannot touch anything scheduled at a drop — the walkthrough behavior is
structurally impossible. The design record's own layering rule (operator correction 4) says
texture "seasons groove/ambient stretches only," yet the record's spec-mapping notes read the
same walkthrough as "growl-timed accents within drops = texture seasoning over role cues …
layering holds." The two documents genuinely disagree, and the walkthrough is the operator's
direct instruction.

**Ruling: CHANGE.** Containment ("decorate, never decide" — operator-locked) is about
*scheduling*: texture must never trigger, suppress, retime, or replace a role cue, and must
never touch brightness at drops (drops always full-scale, locked). Within an
already-scheduled role cue's window, texture MAY select among that role's cue variants /
modulate flavor parameters — which is exactly what the walkthrough describes (both candidate
looks are drop-family cues; the growl beats pick the sparkle variant). The structural
enforcement moves from "role ∈ {groove, ambient}" to: texture input is read only at cue
selection/parameterization inside the role the scheduler already chose; the scheduler itself
never sees texture. Worst-case wrong output remains wrong seasoning, never a missed/phantom
cue — the containment guarantee is unchanged.

**Label:** confirmed conflict (both passages quoted from the records at HEAD).

### S-3 (Medium, target 1) — The operator's tech-house "growl" gets zero growl flags; the timbre class cannot drive the walkthrough's growl-vs-driving-beat alternation.

**Location:** `spectral_profile.py:236-242` (`growl_flags` = harmonic 500–4000 flatness > 0.25
AND growl-band level > 10 dB); build record Appendix G walkthrough 1 annotation ("the
growl/pulse classes are the natural inputs").

**Measured (this review):** `growl_flags` on Can't Say Nah = **all False** at beats 128–137,
160–169, and 352–361 — every drop the operator narrated growls in. Measured growl_flatness at
128–131: 0.026–0.094, far below the 0.25 distortion gate. The class is honest for what it
measures (distorted timbre — dubstep/riddim screams; it fires correctly on ILL/DROP EM per
the report), but a tech-house bass "growl" is a *clean-timbre* low-mid bassline. The report's
own §Appendix G verification note measured the CSN growls by growl-band *level* (27–29 dB),
not by the flag — the annotation "the growl/pulse classes are the natural inputs" oversells.

**Why it matters:** the walkthrough behavior (growl beats → sparkle strobe, driving beats →
post-drop chase) is the concrete texture-seasoning example for the entire tech-house/ODDMOB
half of the catalog.

**Required fix (consumer rule, data already stored):** define a "bass-forward beat" derivation
for drop windows: growl-band level elevated + sustained within-beat shape (from
`growl_band_db`/`sub4`) distinguishing the bassline-led beats from kick-led driving beats
(`attack_low_db`/`perc_low`), calibrated on CSN's drops as the anchor. Rename honestly (the
class-semantics rule): it describes bass-forward texture, not "growl". The distortion
`growl_flags` class stays for what it actually measures.

**Label:** confirmed (measured this review).

### S-4 (Medium, target 1) — Report claims worded stronger than the shipped code delivers; corrections needed at the fold-in.

All in `docs/research/spectral_audio_analysis_redesign.md`; none change the architecture; the
fold-in pass must correct them so the Feature specs aren't written against idealized prose:

1. §5 R6 "emptiness detected & **sized** … **validated** on the ear-validated reference
   track": the sizing chain returns 0 on that track's drops as shipped (S-1). The *runs* are
   validated; the *sizing consumer* is not.
2. §6.5 ILL outline "empty floor through 0:43.0–0:46.9 **ending exactly at the DROP**
   (beat 109)": the shipped run is (100–107), ending at beat 108's start ≈ 0:46.3, two beats
   shy of the drop; "exactly" only holds under the prototype's sub-only rule (97–108).
3. Appendix B "a **4-beat vacuum** immediately before drop 261": measured beats 257–260 =
   sub 25.2 / −12.2 / −11.6 / 12.2 — a 2-beat vacuum (258–259) under either rule; not
   reproducible as 4 from the shipped cache. Appendix B "3-beat gap before drop 141":
   reproduces under sub-only only (S-1).
4. §6.1/§7b suite note is stale in a good way: the laser-color loader failure the report
   lists as the one pre-existing failure has since been fixed — at `f30f1e6` the full suite
   is **3,264 tests, OK** (6 skipped, 1 deliberate `expectedFailure` in
   `test_smart_phrasing_properties.py:214`). Measured this review.
5. §4.3 says centroid rounding "1 Hz"; code rounds to 0.1 Hz (`audio_spectral_features.py:364`).
   Cosmetic; determinism unaffected (rounding is part of the schema either way).
6. §4.10 change 3 says the seam "logs its path (v4-hit / v3-fallback / fresh-extract)"; the
   code logs only the three non-v4-hit paths (`state_manager.py:258,267,272`) — which matches
   §6.3's wording and is the right behavior (steady state stays quiet; any non-v4 path is
   visible). Fix the §4.10 sentence.

**Label:** all confirmed (measured/read this review).

### S-5 (Medium, target 2) — Four walkthrough behaviors have no named derivation yet; the expansion phase must design them as consumer rules, not rediscover them.

From the Appendix G capability walk (§3 table below), the behaviors whose measurement chain
exists in the stored data but has no named derivation in either record:

1. **Build-intensity → white share** (walkthrough 1: "white+blue mix instead of full white —
   build intensity should scale the white share"). Inputs stored: `fluxsum_midhigh` rise,
   `full_db` slope over the build section, `onset_density_midhigh`. Needs a pinned formula
   (e.g. normalized flux+level rise over the buildup window → white fraction).
2. **Animation-rate ladder selection** (general principle: atmospheric 1/2/4-beat, groove
   1-beat, drops 1/0.5/0.25). The *ladder* is locked design; the *selector* (which rung, from
   section tier + texture + BPM) is undesigned.
3. **Atmospheric-simmer recognition** (Appendix E ruling 3): percussion-free sections →
   "lights simmer". The signature is measured (low-band attack median ~0.7 dB vs 8–15 in
   drops); needs a named class over `attack_low_db`/`onset_density` within quiet sections.
4. **"Bright euphoric" treatment selection ≠ `bright_tilt_flags`** (walkthrough 2, 1:47.5 and
   drop 2:17): measured this review, STARsound's euphoric sustain sections read
   `sustained_synth` = True with `sustain_mid_db` 20–27 dB, but `bright_tilt` = False
   (centroid 420–980 Hz < the 1500 Hz gate). The cyan/white treatment must key on harmonic
   sustain presence (+ cleanliness, + `sustain_high_db`), not spectral centroid alone.

**Label:** confirmed gaps (both records read in full; chains measured this review).

### S-6 (Low, target 2) — Research rounds contain fabricated safety-flavored citations; they must not enter specs as verified numbers.

A read-only sweep of the four Gemini rounds (subagent, spot-checked) confirms the known
mixed-citation caveat and flags two spots a spec author could wrongly treat as authoritative:
round 2's "strobes >15 Hz must decay after 3–4 s … Source: **Safety standards**" (a
synthesized citation — real photosensitivity guidance is shaped around ≤3 flashes/s, a
different number entirely), and round 3's "Indoor laser safety standards" cite on beam
height. Consequence for the expansion phase: strobe/beam comfort numbers from the rounds are
**lore, tune-live**, exactly as the record already says — and with haze IN, the one
worth keeping as an authoring guideline (not an engine rule, no safety theater) is: beams aim
above heads / at surfaces in a living room. The 15–30 Hz "drop strobe" range is additionally
physically unreachable — the 30 fps pipeline caps realizable strobes at 15 Hz (first review
F-6, re-verified at HEAD: frame-sampled 16th-note gates at `govee_frame_renderer.py:423,460,481,492`).

**Label:** confirmed (files read; renderer re-verified at HEAD).

### S-7 (Low, target 1) — Two mechanical nits in the derived views.

1. `drop_window_vector` derives `bpm` from `duration_s / n_beats` (`spectral_profile.py:531`)
   — the track-average, not the local grid spacing at the drop. Fine for this catalog's
   constant grids; will misreport on any variable-BPM edit. One-line fix if it ever matters
   (pass the local beat span).
2. `pre_drop_gap_beats` accepts `drop_beat == len(gone)` (`spectral_profile.py:184`) — a
   drop marker one past the last beat scans from the final beat. Harmless; worth a comment.

**Label:** confirmed (code read).

---

## 3. Target 1 — capability walk: every v2 consumer, its measurement chain, its ruling

Rulings: **SUFFICIENT** (stored data + shipped views carry it) / **CONSUMER RULE** (stored
data suffices; a derivation must be named in the feature spec — no re-extraction) /
**SCHEMA EXTENSION** (needs a new stored field + re-sweep) / **INFEASIBLE** (cannot be driven
from audio analysis as designed).

| Consumer (v2 feature) | Measurement chain | Ruling |
|---|---|---|
| Identity zones (F1) | `identity_axes()` — grit/punch from compat block (inherits v3 stability 0.922/0.902), bass duty derived at load, drama stored; corpus stability .928–.967 (n=219, report §6.5, not re-derived) | **SUFFICIENT** — measured this review: CSN (punch .51, drama 8.7, brightness 521) vs STARsound (punch .85, drama 14.2, brightness 1059) separate exactly the way the operator's palette descriptions demand |
| Identity permanence / F-9 epoch | v4 = the declared first epoch; scalars stored in-entry; threshold-free only | **SUFFICIENT** — the freeze-and-store of derived zone per content-id remains Feature-1 spec work (charter) |
| Drop-type selection (F2, correction 3) | `drop_window_vector()` — 19 descriptors + coverage + `pre_gap_beats` + optional `pulse_frac`; held-out 6-way 58.7% vs 16.7% chance; selector needs only 3 families + neutral (trap/dubstep merged, Appendix E) | **SUFFICIENT** — F-11 neutral-default rule is the consumer's, fed by `coverage`; note `pre_gap_beats` inside the vector inherits S-1's adjacency fix |
| Pre-drop blackout sizing (F2, addendum 3) | `empty_floor_runs()` + `pre_drop_gap_beats()` | **CONSUMER RULE (required)** — S-1: tolerance window, sub-only floor notion, floor-returned abort, relative-dip class. All inputs stored per beat |
| Blackout kind split (musical empty floor vs literal silence) | `empty_floor_runs()` kind + `level_db` | **SUFFICIENT** — measured this review: ILL end-of-file (325–338) `true_silence` ×14; intro riff gaps 4–5 beats reproduce exactly |
| Build moves / body language (F2 item 2) | `attack_db`/`attack_low_db`, `sub4` swing, `perc_*` + identity axes | **SUFFICIENT** for character selection; the *build-intensity* input for white share is S-5.1 **CONSUMER RULE** |
| Snare-roll / crescendo context (R5) | `roll_flags` (≥3 onsets/beat), `fluxsum_midhigh` + `roll_acceleration` | **SUFFICIENT** (ear-confirmed rolls fire it; also fires `lowmid_pulse` — known false positive for wobble semantics, honest per Appendix E) |
| Texture seasoning Tier 1 (F4) | `kick_prominence_flags`, `thick_flags`, `bright_tilt_flags`, `stab_flags`, `sustained_bass_flags`, bottom-gone | **SUFFICIENT** with two recorded limitations (report Appendix F, deliberately not retuned): kick-prominence under-reads sidechained four-on-floor under walls (slot-0 dominance in `sub4` is the named derivable alternative); `sustained_synth` cleanliness gate (0.12) excludes thick layered walls (0.169). Scrub/live phase gates any retune |
| Texture Tier 2 growl vs whir (F4) | `growl_flags` (distortion timbre) + `sustained_synth_flags` | **SUFFICIENT for dubstep-family growl** (ILL/DROP EM measured); **CONSUMER RULE** for tech-house bass-forward beats — S-3 (the walkthrough's actual ask) |
| Tech-house drop alternation (walkthrough 1) | growl-band level pattern within drop window | **CONSUMER RULE (required)** — S-3 |
| Section pacing (F4/E) | `section_map()` — 16-beat blocks, marker-forced boundaries, merge, energy tiers | **SUFFICIENT** (4-track eyeball validation in the report; deterministic; false drop markers force phantom boundaries — accepted, recorded) |
| Chorus-softness recognition (walkthrough 1, 3rd chorus) | none — primary energy measures read chorus 3 ≈ drop 1 (report Appendix G, honest) | **INFEASIBLE as designed today** — expansion phase must not promise it; candidate axes (layer thickness, mid/high content) are future exploration, possibly SCHEMA EXTENSION |
| Growl-intensity ranking (walkthrough 1, drop 352 "more intense") | levels read near-equal; ear ranks late > first | **INFEASIBLE (cut)** — do not rank growls; treat drop growls uniformly; ear wins |
| Slow/formant wobble (Appendix E scrub) | growl-band *level* flat where the ear hears "wow wow" | **SCHEMA EXTENSION (named, deferred)** — frame-rate growl-band *centroid* series + one overnight re-sweep; deferred per operator priority ruling |
| Fast amplitude wobble / busy pulse | `lowmid_pulse_flags` (experimental; rolls/chugs/sirens fire it too) | **SUFFICIENT as experimental** — measured this review: LUNCH 15.1% firing, runs at 42.4/45.9/49.7 s, exact reproduction; operator scrub gate stands |
| Laser personality picking (5.9/P-4) | identity axes → zone → personality; `personality_resolver.py` seam confirmed at HEAD ({dubstep, house}, default house) | **SUFFICIENT** on the analysis side; gated on the hardware-vocabulary catalog (correction 6a), not on measurements |
| Landing restore eligibility (P-3) | breakdown depth via `full_db`/section tiers + bottom-gone + drop markers | **SUFFICIENT** |
| Off-beat/hat context (R20, item 16) | `sub4` high/air slots 2–3 vs 0–1 | **SUFFICIENT** (selection context only) |
| Relative-dip lights-cut (walkthrough 2, 2:12.4/2:16.5; CSN beat 127) | `full_db` vs local context | **CONSUMER RULE (required)** — part of S-1(d); report already names it honestly |
| Atmospheric simmer (Appendix E ruling 3) | `attack_low_db` median + onset density within quiet sections | **CONSUMER RULE** — S-5.3 |
| Animation-rate ladder rung selection | section tier + texture classes + BPM | **CONSUMER RULE** — S-5.2 (the ladder itself is locked design) |
| "Bright euphoric" treatment (walkthrough 2) | `sustained_synth` + `sustain_mid/high_db` (NOT `bright_tilt` — measured False on STARsound's euphoric sections) | **CONSUMER RULE** — S-5.4 |

**Appendix G walkthrough behaviors, one line each (chain → status):** groove chase in track
colors → identity+role (**exists**); buildup hue shift on "lows out" → sub-only floor signal
(**S-1b rule**); white share scales with build intensity → **S-5.1 rule**; 1-beat pre-drop
blackout on percussive cut → relative-dip (**S-1d rule**); growl-vs-driving alternation in
drop → **S-3 rule**; 3rd-chorus softness → **infeasible today, honest**; breakdown
"lows cut, drums persist" → sub-only + `perc_low`/kick flags (**rules above**); implosion
build "sparse and dim" → simmer + relative-dip (**S-5.3/S-1d**); room blackout before 2:42.5
→ **S-1a/b**; 4-beat full-strobe drop + more-intense growl → drop cue (exists) + ranking
(**cut**); twinkle/simmer atmospheric intro → **S-5.3**; hidden-energy ramp → buildup marker +
`full_db` step (**exists, measured 9→15 dB**); blackout→explosion at 0:52.9 → **S-1c**
(floor-returned abort; audio leads marker); bright cyan/white sustain sections → **S-5.4**;
lights-cut dips → **S-1d**; swordfish chase at 0.5-beat rate → drop cue family + rate ladder
(**S-5.2**).

The capability bottom line: **nothing the walkthroughs describe requires new stored data**
except the two honestly-cut items (chorus softness, formant wobble) — every gap is a
derivation over series already in the 666-entry cache. That is the strongest possible
validation of the store-raw-derive-at-load architecture — and the reason S-1/S-3/S-5 are
spec-blocking but not build-invalidating.

---

## 4. Target 2 — design rulings (deltas on the first review, given v4 + walkthroughs + haze)

The first review's rulings stand except where amended here. Its line-number claims were
re-verified at `f30f1e6` where load-bearing (two build waves landed since `4a24209`): frozen
`born_bpm` + wrap detection (`beat_sync_engine.py:26,51-68`), 30 fps runner +
`set_brightness(100)` (`govee_realtime_runner.py:54,208,319`), push-loop anchor publish
(`state_manager.py:3694`), journey RNG/salted track seed/deque-3/drop-snap
(`led_color_engine.py:265-284,318-321,374-375,399`), six cool-only scale stops
(`led_models.py:72-79` — unchanged by the color packages; warm stops still must be added),
mixer offsets 7.2.11-only (`rb_offsets.py:90,108-111`), laser personalities {dubstep, house}
default house (`config/laser_director.json` + `personality_resolver.py:20,41-68`), live config
`led_predark_beats: 4` + safety `high_impact_cooldown_s: 12.0`, pad kinds
(`soundswitch_midi_input.py:307,343-368`), phrasing reset triggers (`smart_phrasing.py:206-216`),
frame-sampled strobes + baked `_blue/_cyan/_red` names (`govee_frame_renderer.py:347-351,423-506`),
buildup acceleration cues exist (`_buildup_zone_strobe`/`_buildup_ramp_3`,
`govee_frame_renderer.py:644,712`). All confirmed.

| # | Element | Ruling | Basis |
|---|---|---|---|
| T2-1 | First review F-2 (backfill; Tier-2 collapse) | **RESOLVED** | The sweep covered 666/686 on-disk tracks (100% of decodable+gridded; 19 no-grid FX one-shots + 1 corrupt file are permanently uncoverable). Tier 1 is now effectively total; a brand-new purchase pays ~12 s at first load (seam verified `state_manager.py:263-268`) and has identity from that load onward. Tier 2 (ANLZ-structure-only) shrinks to: the 20 uncoverable tracks + the first minutes of a brand-new file. Expansion phase treats fallback tiers as corner cases, not architecture. |
| T2-2 | First review F-9 (identity epoch) | **RESOLVED at the analysis layer** | v4 is the declared epoch; grit/punch computed from the bit-identical compat block; stability re-proven at corpus scale; thresholds never stored. The remaining half — freeze-and-store the derived zone per content-id at first derivation — is Feature-1 spec work (charter item). |
| T2-3 | First review F-16/P-2 (one silence primitive) | **PARTIALLY RESOLVED → amended by S-1** | `empty_floor_runs()` exists as the single shared primitive with the kind split and `level_db`. But "one primitive" now needs a second axis: the *floor notion* differs by consumer (sub-only for the operator's "lows out" moments; AND-rule acceptable for texture darkness). The primitive stays one function; the spec pins which threshold set each consumer reads. The blackout scan additionally gets tolerance + abort + relative-dip (S-1). |
| T2-4 | First review 4.2 (structural texture gate) | **CHANGE** | S-2: enforcement moves from role-set exclusion to selection-only access. Containment (locked) unchanged. |
| T2-5 | First review F-3 (kill matrix), F-4 (moment arbiter), F-8 (color-slot contract) | **STILL REQUIRED — unbuilt paper** | Nothing landed since; the expansion phase must produce all three before Codex specs. The arbiter's member list grows: add the blackout-abort (floor return beats everything below emergency/manual), the drop-cue variant seasoning (S-2 — subordinate to the drop cue itself), and the simmer treatment (lowest, with texture). F-4's precedence list otherwise stands. |
| T2-6 | Haze answer (was UNKNOWN; now IN — operator, Appendix G) | **NEW — design space reopened** | Invalidates: addendum 12's surface-pattern-only conclusion and every "hazeless reality" qualifier. Unlocks: beam-based looks (aerial fans, sky/liquid effects, beam chases) as first-class personality vocabulary; rest-vs-fire discipline and zone-complement coloring (P-4) apply to beams unchanged and get *stronger* (beams in air read as a second light system contrasting the strip wash). Invalidated assumptions to strike at fold-in: none of the laser personality scenes were designed for beams — the "catalog the hardware vocabulary" step (correction 6a) is now the gating dependency for the whole laser side and should catalog *beam-relevant* controls (pattern, size, rotation/motion speed, color, strobe on CH8/CH9/CH11) explicitly. One authoring guideline (not an engine rule): beams above heads in a living room (S-6). |
| T2-7 | Drop-type classifier (2.9, F-11) | **KEEP, now concretely fed** | `drop_window_vector` + held-out proof + Appendix E family merge (trap+dubstep) → three families + neutral. The spec keys on descriptors, never genre labels (class-semantics rule). `pre_gap_beats` input inherits S-1's fix. |
| T2-8 | Walkthrough cue-vocabulary mapping | **CONFIRMED feasible** | The operator's cue names map onto existing v1 looks (rt groove chase / buildup cues / rt drop chase / rt post drop chase — all present in the live library); the shape/color split (5.12) turns them into paintable shapes. No new renderer machinery demanded by the walkthroughs beyond the already-ruled build-move family. |
| T2-9 | Anchor-palette examples | **NEW charter anchor (measured)** | STARsound (bright cool, white-heavy) vs Can't Say Nah (dark cool): measured axes separate them cleanly (brightness_med 1059 vs 521, punch .85 vs .51, drama 14.2 vs 8.7). The zone mapping the expansion phase designs must reproduce these two calls from the axes alone — a falsifiable acceptance test. |
| T2-10 | SET-mode layer withholding (5.2), strobe physics (F-6), cooldown classes (F-12), identity handover seam (F-10), deck-binding for arrivals (F-5) | **KEEP as ruled** | Re-verified seams at HEAD (above); nothing in v4 or the walkthroughs changes them. The walkthrough's animation-rate ladder gives F-6's stepped-rate design its musical form (rate rungs are beat divisions, not Hz — inherently frame-friendly at common BPMs; the 15 Hz ceiling still applies to 0.25-beat rungs above ~112 BPM, where the intensity/width channel carries the acceleration illusion). |
| T2-11 | Lore numbers in specs | **CHANGE (hygiene)** | S-6: every numeric constant imported from the research rounds enters specs marked tune-live with no citation; the two fabricated safety cites are named so nobody re-imports them as standards. |

---

## 5. Operator-locked challenges (veto-shaped; none silently overridden)

**OLC-A — "Amount of light ≈ strength of the audio" vs total-darkness moments (locks: total
darkness fine; drops full-scale; light≈strength is the operator's own general principle).**
No challenge to any single lock — a note that two of them meet head-on in one place: a
measured 26-beat empty floor (Can't Say Nah 324–349, ~12 s at 130 BPM) under
light-follows-audio yields ~12 s of near-black in a room where the strips are the only light,
*before* the pre-drop blackout even starts. The 16-beat blackout cap (report §8 Q1 default)
governs the blackout; nothing yet governs how dark the *breakdown before it* is allowed to
ride. Default chosen for the expansion phase: breakdown floor-absence maps to "sparse and
dim" (the operator's own walkthrough words), reserving true black for the blackout window
itself. Veto if long full-dark breakdowns are wanted as-is. **[Operator 2026-07-05: no veto —
default confirmed.]**

**OLC-B — Markers are authoritative vs audio leading the marker (lock: phrase markers are
operator-owned truth).** STARsound's sub returns 3 beats before its drop marker (measured;
S-1c). The lock stands — no marker-veto logic — but the blackout consumer must be allowed to
*end darkness early* on measured floor return, or the room stays black over a landed drop.
This is framed as an audio-abort on one cue, not as distrusting the marker (the drop cue
still fires at the marker). Veto shape: if the operator prefers markers to control darkness
end-to-end even against the audio, say so; the default is the abort. **[Operator 2026-07-05:
no veto — the abort stands.]**

**OLC-C — Trap and dubstep share one expression (lock, Appendix E) vs walkthrough 2's
distinct trap-vacuum imagery.** No conflict in substance (STARsound is a hybrid and the
operator narrated it with dubstep vocabulary) — recorded only so the expansion phase doesn't
re-split the family on its own: the drop-type selector keeps three families + neutral, and
any trap-specific *variant* lives inside the shared family as texture-driven variation
(sparse-hits vs dense-stutter from `onset_density_mh`/`pre_gap`), never as a fourth family.

---

## 6. The expansion-phase charter (the gate deliverable)

The next phase is a Fable one-shot that expands the lighting intentions into the full v2
experience design, from which the Feature 1–4 Codex specs are authored. It reads this
document, the design record, the first review, and the build record. It does not touch code,
tests, config, or contracts; it has **read-only access to the v4 cache, the Rekordbox
DB/ANLZ files, and a scratchpad for pure verification scripts** (criterion 6.4.2 requires
running its blackout rules against the shipped cache) and writes only its own design
document. Precondition (may run as the same session's first act): the **fold-in pass** —
apply the S-4 corrections to the build record and mark the haze-invalidated passages (T2-6)
in the design record — so the expansion designs from corrected prose, never the idealized
originals.

### 6.1 Settled — treat as decided, do not re-open

- v4 is the analysis layer and the identity epoch. No schema change is needed for any v2
  feature; the two named cuts (chorus softness, formant wobble) stay cut; the one named
  future extension (frame-rate growl-band centroid) stays deferred.
- The locked functionality agreement + addenda 1–21 as amended by operator corrections, the
  first review's rulings as amended by §4 above, and every operator lock (darkness OK, no
  double drops, WILD OUT default + SET selectable, key out of color, neon zones,
  palette-pads-plus-lock correction path, drops full-scale, decorate-never-decide, markers
  authoritative, trap=dubstep expression, stereo width deferred, expression-over-taxonomy,
  LEDs primary + two DMX lasers in haze).
- Haze is IN. Beam-based laser design is in scope; surface-pattern-only framing is dead.
- The brain/body split and the v1 seams: arrival scheduler in `BeatSyncEngine`; blend through
  the LED context; identity consumed at `begin_dispatch`; personality picker replacement on
  the laser side; all re-verified at HEAD in §4.
- The texture containment mechanism per S-2 (selection-only access, scheduler never sees
  texture).
- The blackout consumer-rule family per S-1 (tolerance, sub-only floor, floor-returned abort,
  relative-dip class, 16-beat cap, snap flick on gap 0 *after* the tolerance search).
- Breakdown floor-absence rides "sparse and dim" (the operator's own walkthrough words); true
  black is reserved for the blackout window itself (OLC-A default — operator confirmed
  2026-07-05, no veto; OLC-B's floor-return abort likewise confirmed).

### 6.2 Must design (the open creative questions, each with its anchor)

1. **The zone map**: axes → zones → palette families (neon-anchored per the lock), hash
   spread within zone, warm `scale_stops` additions. Falsifiable anchor: reproduces
   STARsound-bright-cool vs CSN-dark-cool from measured axes (T2-9); the first review's
   OLC-3 sameness engineering (spread wide on the aggressive side).
2. **The moment arbiter** (F-4 + S-2 + S-1 members): one precedence list, skip-not-queue.
3. **The kill matrix** (F-3): every addendum behavior + walkthrough behavior → owning switch;
   the three dependency degrades; boundary-only flips.
4. **The color-slot contract** (F-8): base/accent/white slots across the render library;
   Template Lab authors shapes against them.
5. **The consumer-rule pack** (S-1, S-3, S-5): pre-drop blackout scan; bass-forward beats;
   build-intensity → white share; animation-rate rung selector; atmospheric simmer; bright
   euphoric treatment selection; relative-dip. Each: pinned formula, calibration anchor
   (walkthrough beats), pure function over cache, own test seam.
6. **The laser package**: beam-era personality design per zone (P-4 pairing), rest-vs-fire,
   gated on the correction-6a hardware-vocabulary catalog (operator + Claude session; the CH8
   color/effects + CH9 speed + CH11 strobe observability notes exist in repo memory/docs).
7. **The build-move family detail** (squeeze-explode, fuse, swell + landing restore P-3),
   with body-language selection from measured character (`attack_*`, swing, `perc_*`).
8. **Observability** (5.17 as amended): per-feature kills, drop-type + reason, blend scalar,
   identity log line, plus the S-1 blackout decision (gap found, length, rule fired) so live
   vetoes are precise.
9. **The library-wide dry-run audit (operator ask 2026-07-05):** run the complete v2
   decision pipeline as pure functions over every cached track (all 666) — zone + palette,
   every drop's family + reason, every blackout decision + gap, texture-class firing rates,
   section tiers, rate-ladder rungs — and report the distributions plus a ranked outlier
   list (tracks with the strangest readings: all-neutral drops, zero texture anywhere,
   extreme zone crowding, odd blackout gaps). The outliers become the targeted scrub-check
   list — the ear goes where the data is weirdest, not to random samples. The same audit
   re-runs through the real code after the build as a regression tool.
10. **The new-template roadmap (operator ask 2026-07-05 — new animation templates are an
    explicit v2 deliverable, not just repainted v1 shapes):** beyond the already-new build
    family (squeeze-explode, fuse, swell), landing restore, stingers, bloom, and the blend
    painter, the expansion phase designs at least 2–3 genuinely new shapes per role family
    (groove, buildup, drop, post-drop, breakdown/atmospheric) — each described visually,
    authored as Template Lab shapes against the color-slot contract, and selected by
    measured character/energy, never hand-assigned per track. Authoring and tuning happen
    in the build + live phase through the existing Template Lab flow.
11. **The drop intensity tier + aggression profile (operator ask 2026-07-05):** define the
    per-drop measured intensity tier (corpus-absolute over the drop-window vector: absolute
    level, lift vs the track's `loudness_ref_db`, `attack_low_p90`, onset density,
    `pre_gap_beats`) and the mapping tier × family → profile knobs: strobe density/burst
    structure, animation-rate rung, white share, motion violence, inter-hit micro-darkness.
    The full-scale law is untouched — the tier shapes aggression, never the brightness
    ceiling. Anchors: hard-techno relentless pound vs ISOxo-grade maximal strobe vs
    groovy-house bounce; falsifiable: Ray Volpe — DROP EM's four drops (measured attack
    2.7→16.1 dB, flatness 0.30→0.42) must not all land in one tier. SET mode's peak-time
    ceiling reservation reads this same tier.

### 6.3 Analysis gaps to design around (never promise these)

- Chorus-vs-drop softness (measured indistinguishable on primary energy — walkthrough 1).
- Growl-intensity ranking (ear ranks, measurements read near-equal).
- Slow/formant wobble (level-invisible; the named centroid-series extension is the unlock if
  lights ever need it).
- Kick-prominence under sidechained walls and `sustained_synth` on thick layered walls (both
  recorded in Appendix F; slot-0 dominance and a relaxed-cleanliness variant are the derivable
  alternatives — scrub-gated, not spec-blocking).
- `lowmid_pulse` breadth (rolls/chugs/sirens fire it): use as busy-pulse seasoning only,
  never as "wobble" semantics.

### 6.4 Falsifiable success criteria for the expansion phase

1. Every walkthrough behavior in §3's one-line list maps to (cue/behavior, trigger, inputs,
   owning kill switch, arbiter rank) — zero unmapped lines.
2. The blackout chain, run on the shipped cache with the spec's rules, yields nonzero
   correctly-sized gaps at: ILL 109 (12 beats, sub-only), ILL 261 (2), CSN 352 (26 → capped
   16), STARsound 131 (2, with abort at floor return) — and snap-flick classifications where
   the operator described none.
3. The zone map reproduces the two anchor palette calls (T2-9) and assigns all 666 cached
   tracks a zone with the distribution visibly spread (no zone > ~40% of the aggressive half
   — the first review's OLC-3).
4. Every research-round number entering a spec carries tune-live provenance (S-6/T2-11).
5. The kill matrix covers: F1 off + F3 on; F2 off (blackout reverts to fixed
   `led_predark_beats: 4`); v2 off mid-move (teardown through existing reset/idle machinery);
   arbiter behaviors under each single-feature kill.
6. Codex specs for Features 1–4 can be authored from the expansion document + the records
   without reading this review's measurement scripts.
7. The library-wide dry-run audit (§6.2 item 9) exists with distributions and a ranked
   outlier list, and **no cached track lacks a defined outcome at any decision point**
   (a zone, a drop family — neutral counts, a blackout decision — "none/snap flick"
   counts, a texture read — "none" counts). Applicability to the whole library is
   demonstrated, not assumed.

---

## 7. Claim-label index (load-bearing claims of this review)

- v4 code/tests/seams read in full at `f30f1e6`; architecture matches the build record —
  **confirmed** (files and line refs in §Evidence and §2).
- Suite at HEAD: 3,264 tests OK, 6 skipped, 1 deliberate expectedFailure; the report's
  known laser-loader failure now passes — **confirmed (measured this review)**.
- Cache 666 entries / 203.5 MB; stored scalars recompute exactly from stored series (3
  random entries) — **confirmed (measured this review)**.
- v3-compat bit-identity on a real library track via the retained env-gated test —
  **confirmed (measured this review, PASS)**.
- CSN drop@128 vector (sub 31.2, swing 9.2, mid 3.1), Chemicals sustained-synth runs
  ×189/×138/×42/×36, LUNCH pulse 15.1% at 42.4/45.9/49.7 s — **confirmed (measured this
  review; exact reproduction of report claims)**.
- `pre_drop_gap_beats` = 0 at all 14 drops of ILL / CSN / STARsound; per-beat band values as
  tabulated in S-1 — **confirmed (measured this review)**.
- Appendix B's 12-beat@109 and 3-beat@141 reproduce under sub-only; 4-beat@261 reproduces
  under neither rule (2 beats) — **confirmed (measured this review)**.
- `growl_flags` all-False at CSN drop beats; growl_flatness 0.026–0.094 there — **confirmed
  (measured this review)**.
- STARsound sustained_synth True / bright_tilt False on euphoric sections; identity axes
  separate the two anchor tracks — **confirmed (measured this review)**.
- Corpus stability .928–.967, held-out 58.7%, sweep 48.6 min / 203.5 MB, key parity 60/60,
  ear-scrub results — **confirmed as the build record's named measured facts (not
  re-derived, per prompt)**.
- v1 seam re-verification at HEAD (all items in §4 preamble) — **confirmed (read this
  review)**.
- First-review rulings not amended here — **inherited (confirmed at `4a24209` by that
  review; spot-re-verified where load-bearing)**.
- Research-round citation quality, fabricated safety cites — **confirmed (files read;
  subagent sweep spot-checked)**; the ≤3 flashes/s real-world reference — **assumed
  (well-known guidance; not load-bearing — no spec number rides on it)**.
- Haze IN, walkthrough content, operator rulings — **operator ground truth (Appendix G/E of
  the build record)**.
- Perceptual/treatment claims (what reads bright/euphoric/comfortable) — **assumed;
  live-look gate is the arbiter** (unchanged from both prior reviews).
- Rekordbox 7.2.11 pin, fader smoothness unknown, Govee device latency unknown — **inherited
  unknowns (unchanged; first review §7)**.
