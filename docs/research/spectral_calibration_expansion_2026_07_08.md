---
doc_status: current
truth_level: measured
last_verified_commit: 3399231
last_verified_date: 2026-07-08
validation_scope: offline corpus analysis plus the operator listening pass (7/7 answered 2026-07-08, §6b) — recomputes the v4 spectral calibration + F2 rule-pack claims on the refreshed whole-library cache; no calibration constant changed, no runtime/hardware action; darkness-pack level-term finding is F2-spec input only, not implemented
---

# AWR-147 Phase 1 — Spectral calibration expansion: corpus refresh + calibration report

**What this is.** I refreshed the whole-library v4 spectral cache, then built a
permanent, re-runnable report tool (`tools/spectral_calibration_report.py`) that
recomputes every corpus-scale calibration claim on the expanded library and names
concrete counterexamples. This doc records the measured numbers. **Phase 1 measures
only — no threshold, constant, or cache entry was changed.** The manager (Fable
`claude3`) decides tuning separately.

Claim labels: **confirmed** = I computed it, command cited; **assumed** = inferred
from a documented modeling choice; **unknown** = could not compute, reason given.

- **HEAD at run:** `179c95c` (confirmed — `git log --oneline -1`).
- **Bridge offline gate:** `pgrep -f 'rb_ss_bridge_v2$' | wc -l` = **0** before every heavy run (confirmed).
- **Report tool run:** `python3 tools/spectral_calibration_report.py --json /tmp/awr147/report.json --markdown /tmp/awr147/report.md` (93.4 s, 4211 drop records exported — confirmed).

---

## 1. Corpus sweep refresh (Task 1) — confirmed

Command: `caffeinate -i python3 tools/spectral_sweep.py --jobs 2`. Final block verbatim:

```json
{ "tracks": 731,
  "counts": { "cached": 701, "no_grid": 19, "extract_failed": 1, "ok": 10 },
  "elapsed_min": 1.4, "v4_entries": 714, "v4_cache_mb": 218.4 }
```

- **Scope:** 731 on-disk active tracks (prior 2026-07-05: 686). **10 newly extracted**, 701 already cached.
- **Failure categories (every one counted):**
  - `no_grid` = **19** — tracks with an ANLZ set but < 2 beatgrid points (FX one-shots / ungridded). Prior sweep: 19. Unchanged.
  - `extract_failed` = **1**, named: **`I Remember - Deadmau5 & Kaskade (GRiZ flip)`** — the known undecodable flac (confirmed; exactly the ≈1 the task expected, nothing new broke).
- **Cache after sweep:** 714 v4 entries / 218.4 MB (the tool's summed-JSON figure; `du -sh` = 210 MB actual on disk). Pre-sweep: 704 entries. **+10 = the 10 new extractions** (confirmed by cache-key diff, `/tmp/awr147/new_keys.txt`).

## 2. Report coverage (Task 3) — confirmed

`tools/spectral_calibration_report.py` counts: `{scope: 731, has_v4: 711, no_grid: 19, no_v4: 1, drops_library: 4211}`.

- **711 tracks resolve to a v4 entry** via (filepath, current beatgrid). Cache holds 714 → **3 orphan entries** don't map to a current track (stale beatgrid or off-disk duplicate) — harmless, flagged only for hygiene (confirmed).
- **1 `no_v4`** = the GRiZ flip (has a grid, no cache entry — the extract-fail surfaced again; confirmed).
- **4211 drop markers** across the 711 v4 tracks (the F2 audit basis; the 2026-07-07 audit used 3,936 from the then-shipped cache — the corpus grew by the 10 new tracks + marker/grid changes; **I report 4211 as the new basis**).

### The BY GENRE calibration set is now ~2.5× larger than the priors were computed on

- **by_genre split = 545 tracks / 3265 drops with v4 entries** (24 child playlists of folder `666898931`, RAP excluded, deduped by ContentID; 691 total playlist ContentIDs, 545 on-disk with v4). Confirmed.
- The design-doc priors (`spectral_audio_analysis_redesign.md §6`, line 453) were computed on **219 BY GENRE tracks with v4 entries** — a *partial-cache snapshot* from 2026-07-05 before the whole-library sweep finished. The per-playlist on-disk counts in that doc's Appendix A (ODDMOB 66, TECH HOUSE 56, ISOXO 52, …) sum to ~545, matching my count. **Headline: the calibration now verifies on the full BY GENRE set, not a partial slice, and the priors hold (below).** (confirmed; the 219→545 reconciliation is **assumed** to be the partial-vs-full-cache difference.)

---

## 3. Metric table — prior → new by_genre → new-split → verdict

by_genre is the **only split used for calibration claims** (BY GENRE rule). "new" = the 10 tracks / 80 drops absent from the pre-sweep cache (held-out drift check; small-n, not calibration-grade). All numbers **confirmed** (from `report.json`).

| # | Metric | Prior (2026-07-05/07) | new **by_genre** | new-split (n=10 trk / 80 drops) | Verdict |
|---|---|---|---|---|---|
| 1 | sub_db beats within 8 dB below / above the 5.0 threshold | 4.7% / 5.7% (density valley) | **5.5% / 6.35%** | 3.89% / 7.44% | **holds** — density at threshold stays ~1.5%/2-dB-bin, a flat low valley below the bass-present mode at ~32 dB (21% of beats). Moving 5.0 by ±a few dB reclassifies few beats. |
| 2 | full_db corpus p1 vs true-silence −30 | p1 = −26 (thr below p1) | **p1 = −22.4** | −10.85 | **holds** — −30 stays well below p1 on every split (near-silence stays rare). p1 drifted +3.6 dB (fewer near-silent beats in the fuller corpus). |
| 3 | corpus percentile rank of growl_flatness 0.25 | ≈ p78 | **p81.6** | p86.7 | **holds** — 0.25 still sits high in the distribution (distortion stays uncommon). |
| 4 | onset_density_midhigh p90 vs roll threshold 3.0 | thr > p90 (rolls rare) | **p90 = 3.0 (equal)** | p90 = 4.0 | **drifts (marginal)** — the threshold now sits *at* p90 (was strictly above); on the new tracks p90 = 4.0 > 3.0. Rolls read slightly less rare. Worth a look, not broken. |
| 5 | loudness_ref_db p5–p95 spread | 15.3–19.3 dB | **15.0–19.0 dB** | 15.58–18.11 | **holds** — spread essentially unchanged. |
| 6 | identity even/odd Spearman grit/punch/bass/drama (by_genre) | .929/.935/.967/.928; gate .902–.957 | **.9016 / .9308 / .9697 / .9292** (n=545) | — | **holds** — punch/bass/drama inside the v3 stability band; **grit = 0.9016 sits 0.0004 below the 0.902 floor** — at the boundary, flag as marginal (still a stable axis, just grazing the gate). |
| 7 | per-track bass_duty p5/p95 (observation only; `led_identity_v2.py:4` pins 0.5856/0.9688 — another lane's file, unchanged) | 0.5856 / 0.9688 | **0.5831 / 0.9674** | 0.783 / 0.9733 | **holds** — within 0.003 of the pinned anchors on by_genre. New tracks read bassier (p5 0.783) but n=10. No change made. |
| 8 | family distribution over all drops | HOUSE 41 / WALL 21 / COMET 11 / NEUTRAL 27 (n=3936) | **library: 41.6 / 20.8 / 10.8 / 26.8** (n=4211) | 48.8 / 11.2 / 27.5 / 12.5 | **holds** — library near-exact. New skews COMET (fast material: Lock 'N Load, Cirez D), small n=80. |
| 9 | violence p55/p85 vs frozen cuts 0.616/0.698; tier counts | p55=.616, p85=.698; tiers 2159/1176/601 | **library p55=.6158, p85=.6983; tiers 2322/1251/638** | p55=.6113, p85=.6746; 46/26/8 | **holds** — the frozen cuts still land essentially at p55/p85; tier counts scale with the +275 drops. |
| 10 | darkness decisions: blackout/dip/snap/perc-flick/abort; 16-cap; zero-dark; busy-kills; duty-band | 1320 / 1145 / 1366 / 105 / 150; 219 cap; 48 zero-dark | **library 1416 / 1237 / 1451 / 107 / 116; 254 cap; 31 zero-dark; 701 busy-kills; 64 in duty [0.80,0.90]** | 22/30/26/2; 3 abort; 2 cap; 7 busy | **holds in shape** — blk/dip/snap/perc scale ~+7% with the +275 drops. **abort (116 vs 150) and zero-dark (31 vs 48) read lower** — reproduction-sensitive (see §5 assumption on the dip/abort window). |
| 11 | bass-forward: % windows with ≥1 B; B-rate dist; all-B/all-K | no prior (first corpus measurement); CSN drop 128 = `BKBBBKBBBKBBBKBB` | **library 98.3% ≥1 B; B-rate p25/50/75 = .50/.81/.94; all-B 890, all-K 42** | 100% ≥1 B; all-B 27, all-K 0 | **anchor reproduces EXACTLY** — CSN drop 128 = `BKBBBKBBBKBBBKBB` (confirmed, §4). First corpus-wide numbers. |
| 12 | lowmid_pulse per-track firing rate + top-10 | experimental grade | **library p50/p90/max = .055 / .222 / .634** | p50 .079, max .283 | **N/A prior** — experimental. Top firer: `Hollaback girl (Tavatli Remix)` 0.634. |

### Named-anchor reproduction (Task acceptance) — confirmed

Every named acceptance anchor from `LIGHTING_ENGINE_V2_DESIGN.md §4.2` reproduces on the refreshed cache (command in §4):

| Anchor | Design expectation | Measured now | Match |
|---|---|---|---|
| ILL drop 109 | blackout 12 (sub-only), duty 0.17 | blackout gap 12, raw 12, dark 12, duty **0.167** | ✅ exact |
| ILL drop 141 | blackout 3, duty 0.67 survives busy test | blackout gap 3, dark 3, duty **0.667** | ✅ exact |
| ILL drop 261 | blackout 2 | blackout gap 2, dark 2, duty 0.0 | ✅ exact |
| CSN drop 352 | capped 16, sub-only run = 99 beats | blackout gap 16 (**raw_gap 99**), dark 16 | ✅ exact |
| CSN drop 128 | busy-build refuses 63-beat run → perc-cut 1-beat flick | **perc-flick** (raw_gap 63, busy-killed) | ✅ exact |
| CSN drop 128 bass-forward | `BKBBBKBBBKBBBKBB` | `BKBBBKBBBKBBBKBB` | ✅ exact |

### Per-playlist genre lens (metric 8, by_genre playlists n≥20) — confirmed

The classifier never sees genre labels; these are the family mix per playlist. The design's genre-lens claims reproduce closely:

| Playlist | n | HOUSE | WALL | COMET | NEUTRAL | Prior claim |
|---|---|---|---|---|---|---|
| HARD TECHNO | 198 | 2.5 | 10.1 | **73.7** | 13.6 | ~74% COMET ✅ |
| TECHNO | 71 | 0.0 | 4.2 | **50.7** | 45.1 | (COMET-heavy) |
| DNB | 37 | 0.0 | 5.4 | **64.9** | 29.7 | (COMET-heavy) |
| ISOXO | 201 | 17.9 | **41.3** | 13.4 | 27.4 | 41–45% WALL ✅ |
| DUBSTEP | 109 | 29.4 | **45.0** | 0.9 | 24.8 | 41–45% WALL ✅ |
| TRAPSTEP | 60 | 31.7 | **45.0** | 0.0 | 23.3 | 41–45% WALL ✅ |
| BASS HOUSE | 161 | **64.0** | 28.0 | 0.0 | 8.1 | 64% HOUSE ✅ |
| SYNTH HOUSE | 105 | **64.8** | 15.2 | 0.0 | 20.0 | 65% HOUSE ✅ |
| TECH HOUSE | 395 | **57.5** | 18.2 | 0.0 | 24.3 | 57% HOUSE ✅ |
| ODDMOB | 494 | **53.2** | 21.5 | 0.0 | 25.3 | 53% HOUSE ✅ |
| UKG | 140 | **71.4** | 10.0 | 3.6 | 15.0 | (house-heavy) |
| DEEP HOUSE | 96 | **62.5** | 15.6 | 0.0 | 21.9 | (house-heavy) |
| GROOVE HOUSE | 129 | **51.9** | 12.4 | 0.0 | 35.7 | (house-heavy) |

Full per-playlist table (all 24) is in `report.json → metrics.8_per_playlist`.

---

## 4. Named counterexamples (Task counterexample list) — confirmed

Concrete tracks with measured values, up to 10 each (full lists in `report.json → counterexamples`). Reproduce: `python3 tools/spectral_calibration_report.py --json /tmp/awr147/report.json` then read `records`/`counterexamples`.

**(i) NEUTRAL-classified drops with violence ≥ 0.698** (10 found — genuinely violent drops the classifier leaves undressed; the top tuning candidates):
- `Sticky x Rich Baby Daddy x Night Owl (OK JAYE! Edit)` @196 — v**0.898** (POP BASS HOUSE, TRAPSTEP)
- `ISOxo, Brutalismus 3000 - SPIRAL (BELPHË SCHRANZ REWORK)` @400 — v0.844
- `BLACKPINK - JUMP [JAY ESKAR EXT REMIX]` @496 — v0.827 (TECHNO)
- `Can I (Original Mix)` @96 — v0.794 (SKRILLEX); `Super Shy (CHAOSX REMIX)` @408 — v0.781 (TECHNO); `Rihanna - Don't Stop The Music (SPORTMODE Flip)` @111 — v0.778 (TRAPSTEP); `JUELZ - DRIFT FM` @184 — v0.773; `SAMMY VIRJI - I GUESS WE'RE NOT THE SAME (JAUZ BOOTLEG)` @351 — v0.768 (UKG).

**(ii) tier-3 drops in DEEP HOUSE / GROOVE HOUSE / UKG** (10 — maximal aggression on groovy playlists; lift ≈ 0, i.e. loud landed drops):
- `Drake x Central Cee x longstoryshort - WHICH ONE` @4 — HOUSE T3 v0.872 (UKG)
- `Michael Jackson - Bad (Bask Edit)` @32 — v0.832 (GROOVE HOUSE); `Lights On (Extended Mix)` @416/160 — v0.83/.82 (UKG); `Mau P - MERTHER (JustLuke Edit)` @128/328 — v0.800 (DEEP HOUSE); `Kendrick Lamar - DNA (UKG flip)` @99 — v0.822 (UKG).

**(iii) blackout runs with raw_gap ≥ 40 (cap-distortion size)** — 10 found, the 16-cap is doing heavy lifting:
- `Hide and Seek (What You Say) [VERDES VIP]` @272 — **raw_gap 200 → capped 16**
- `Lean On (Tiesto & MOTi)` @496 — raw_gap 167; `Odd Mob 'Never Alone'` @448 — 164; `Where You Are (Millero)` @512 — 159; `Walker & Royce, Odd Mob - Can't Say Nah` @448 — 131. (All → 16 dark beats. The sub-only floor stays gone for whole breakdowns; the cap + sparse-and-dim simmer own the rest.)

**(iv) busy-kill near-misses (run bass_duty 0.80–0.90)** — 64 in-band; the 0.85 cliff's neighbours (these landed as blackout at duty ≤ 0.85):
- `Wanna Go Dancin'` @224, `Drake - NOKIA [Kelland]` @287, `Michael Jackson - Bad` @224, `INNERBLOOM (BUNT EDIT)` @431, `Feel So Close` @384 — all duty **0.80**; `RADAR - CONTROL MOVEMENT` @192 (0.809), `Rufus du Sol - On My Knees` @192 (0.812).

**(v) identity axis saturated at exactly 0.0 or 1.0** — **1 track corpus-wide**:
- `Hotel Room Service (2FACE VIP Edit)` — **bass = 1.000** (every beat's sub present); other axes normal (grit 0.041, punch 0.336, drama 4.8). No 0.0/1.0 saturation anywhere else.

**(vi) NEW tracks whose family/tier/darkness reads implausible (my judgment)** — **none clearly wrong.** The 10 new tracks read sensibly: `Lock 'N Load - Blow Ya Mind` → all COMET (fast rave), `Playboy (Extended Mix)` → HOUSE/NEUTRAL with one T3, `California Dreamin' (Benassi)` → HOUSE/WALL. The one worth naming: **`Cirez D - On Off (Kapuchon Edit)`** (a dark-techno name) reads WALL/NEUTRAL, **not** COMET — expected, because the Kapuchon edit sits below the 146-BPM COMET gate; correct behaviour, not a miss. New-track reads sampled from `report.json → records` (assumed judgment, values confirmed).

---

## 5. Modeling assumptions the manager should adversarially check

The shipped code (`spectral_profile`, `spectral_cache`, `anlz_reader`) is **imported**, not re-implemented. The **F2 rule pack is design-only** (not in the codebase yet) and implemented in the report tool from the pinned formulas. Two per-drop *scan windows* the design pins in formula but not in exact trigger extent — my documented choices:

1. **Dip trigger window (metric 10).** The design pins `dip_score`, the ≥4.0 fire and the 4-beat cap, but not the exact per-drop window scanned for a firing dip. I scan the **pickup-tolerance window [D−4, D−1]** (same tolerance as the sub-only gone scan; matches the STARsound [128,129]@D=131 anchor). A wider/narrower window shifts the dip-vs-snap split. **Assumed.**
2. **Floor-returned abort (metric 10).** Implemented as: darkness covers the window until a **2-consecutive floor-present run starts**; a lone pickup-present beat stays dark ("dark through the pickup"); floor present at window entry → zero dark beats. This reproduces the zero-dark case but gives **abort 116 / zero-dark 31** vs the audit's 150 / 48 — the gap is this abort/window definition, not a data change. **Assumed.**

Everything else (family classifier order, violence arithmetic, tier cuts, tolerant sub-only scan, busy-build kill, bass-forward B/K) is verbatim from the pins and unit-tested (`tests/test_spectral_calibration_report.py`, 27 tests, table-driven synthetic series).

---

## 6. What this does NOT show (honest limits)

- **No listening validation.** Every number is measured off the cache; nobody ear-checked whether a HOUSE-classified drop *looks* right in the room. The family/tier/darkness reads are descriptor arithmetic, not taste.
- **The F2 rules are design-only.** They are not wired into the runtime; this tool is the first thing that runs them at corpus scale. A number holding here does not mean the engine ships it.
- **Hardware unvalidated.** No frames went anywhere; the bridge never ran.
- **new-split is small (10 tracks / 80 drops).** Its numbers are a drift *smoke test*, not calibration evidence.
- **No calibration constant was changed.** Phase 1 measures; tuning (e.g. the metric-4 onset threshold now sitting at p90, the metric-6 grit axis grazing its gate floor, the metric-10 abort-count reproduction) is the manager's separate decision.
- **3 orphan cache entries** (714 on disk, 711 mapped) are noise, not analyzed.

## 6b. Operator listening pass — 7/7 answered (2026-07-08, same day; verdicts verbatim-in-substance, measurements confirmed this session)

The 7-track boundary sheet came back. Ear verdicts against the measured reads:

1. **Sticky x Rich Baby Daddy (OK JAYE! Edit) @196** (NEUTRAL, violence 0.898): operator calls the song itself neutral — strong syncopated bass, submissive high rattle. **NEUTRAL family read VALIDATED**; high violence + NEUTRAL is not a defect class. Counterexample list (i) is defanged as an automatic tuning target.
2. **WHICH ONE @4** (HOUSE T3 at track start): "kinda — it's just an intro; UKG is not that insane vs dubstep/hard techno/trap." **Tier-3 overshoot datapoint**: corpus-absolute violence can max out on a loud punchy UKG intro. F2 spec should consider runway/track-start damping (cf. AWR-139's true-drop runway rule for lasers) and/or family-relative aggression. One label — direction, not a pin.
3. **Hide and Seek (VERDES VIP) @272** (capped-16 blackout): "warrants like a literal 1 beat blackout" — light percussive pattern still playing. **REJECTED at 16 beats.** Measured: window [256,272) full_db med 10.4 (lift **−6.4** vs ref 16.9), onsets_mh 1.81/beat, run duty 0.22.
4. **Wanna Go Dancin' @224** (5-beat blackout, duty 0.80 busy near-miss): "wouldn't black out — LED getting ready to explode, balloon inflating until the drop." **REJECTED entirely**; the correct treatment is the F2 landing build (squeeze/swell), which the design already has — the darkness decision mis-routed it. Measured: lift **−4.9**, duty 0.80.
5. **Can't Say Nah @128** bass-forward alternation: "sounds about right." **Ear-CONFIRMED.**
6. **Hollaback Girl (Tavatli Remix)**: no verdict possible — busy-pulse seasoning has no visual yet ("dark heavy tech house, borderline house techno"). `lowmid_pulse` stays experimental; scrub gate remains open until a consumer renders something.
7. **Cirez D — On Off (Kapuchon Edit) @478**: "yeah — festival heavy tech house borderline techno." Non-COMET read accepted; the 146-BPM COMET gate stands.

**The load-bearing finding (#3 + #4, cross-checked against the approved anchors):** the darkness pack's emptiness notion (sub-only gone + bass-duty busy test) over-darkens stretches where the full band is still loud. Relative full-band level separates ALL four ear-labeled cases monotonically — approved blackouts: ILL@109 lift −14.0, CSN@352 lift −8.3; rejected: Hide and Seek −6.4, Wanna Go Dancin' −4.9 (window med(full_db) − loudness_ref_db; confirmed, measured this session). Onset density does NOT separate (ILL's approved window carries 2.17 onsets/beat — rolls riding the vacuum): a percussion/onset term is the WRONG fix; a relative-level term is the right shape. **REQUIRED F2-spec input:** add a window-level term to the darkness decision (e.g. full blackout only when lift ≤ ~−8; shortened/flick above), pin the exact boundary and grading there — 4 labels are direction, not a calibration; the boundary sits in a thin margin (−8.3 approved vs −6.4 rejected), so gather 2–3 more labels at spec time if cheap. No analysis-layer change needed: every input is already in the cached series (`full_db`, `loudness_ref_db`).

**Net for this lane:** analysis layer measured everything faithfully (operator descriptions match the vectors); zero `SPECTRAL_V4_CALIBRATION` changes remain the right call. All rule changes land in the F2 consumer spec, not in `spectral_profile.py`.

> **§6b's level-term recommendation is SUPERSEDED by §6c below** (round-2 labels falsified the monotonic level rule). The measurements stand; the proposed rule shape does not.

## 6c. Operator listening pass, round 2 — 10/10 answered (2026-07-08, same day; targeted boundary probes)

Ten more labeled moments (5 blackout-length probes spanning window lift −12.0→−4.9, one busy-kill, two family, one tier-contrast, one NEUTRAL re-check). Verdicts with the measured values:

| Case (lift = window med full_db − ref) | Rule said | Operator said |
|---|---|---|
| FE!N (Chris Lorenzo) @2:22, lift −12.0 | 16 dark | **2 beats** |
| ONE CHANCE (HIVE FLIP) @1:55, lift −9.5 | 14 dark | agree — but he re-marked that drop as an UP phrase in Rekordbox mid-review; separately wants **8 beats at the 2:36.9 hard dubstep-trap drop "to emphasize… even though it goes against the rules"** |
| Can't Say Nah (Benni Ola) @1:28, lift −8.0 | 16 dark | **1 beat** |
| Cruel Summer (Proppa) @1:17, lift −6.5 | 14 dark | **8 beats — "percussive elements done, with just vocals (and some other effects)"** |
| Take It @1:20, lift −4.9 | 16 dark | **1 beat** |
| Diamond Therapy (VIP) @1:15, busy-killed (duty 0.93) | stay lit | **1 bar (4 beats) blackout** — busy-kill reversed here (vs Wanna Go Dancin' round 1, where no-blackout was right) |
| Show Me Love x Perfect @0:11, COMET T3 | full relentless show | **"Not really no"** — third early-track overshoot datapoint |
| kidstopbreathing (ionika) @3:31, lift −4.9 | WALL T2, 13 dark | **WALL yes; 16-beat blackout** — at the LOUDEST window on the sheet; also: chorus marker was mis-placed 2 bars early by a fake drop (he corrected it) |
| STFU 0:39 (T1) vs 0:59 (T3) | different tiers | **same drop section** — the 2nd chorus marker is Rekordbox phrasing, not a real drop; the track is "one of the hardest hitting… relentless" |
| Can I @0:41, NEUTRAL v0.79 | plain look | **"Yeah it's plain"** — NEUTRAL validated again. Creative anchor recorded verbatim: LEDs should be *"sparkly and dancy, not too intensive and strobey, like glitter with a groove"* (whistly tune, groovy bassline) |

**Standing operator rule (verbatim in substance): blackout lengths are QUANTIZED — 1, 2, 4, 8, or 16 beats before the drop only. No 13s/14s.**

**What the combined 11 labels actually show (confirmed pattern, formula deliberately NOT fitted at n=11):**
1. **The "audio-matched gap length" premise of §4.1 is overturned.** Both the raw-gap length AND window loudness fail to predict his lengths (quietest window → 2 beats; loudest → 16). Blackout is drop *emphasis*, not gap mirroring.
2. What long blacks (8/16) have in common: **a monster WALL-grade drop incoming** (kidstopbreathing 16, ONE CHANCE 2:36.9 wish 8) or **a true stop — percussion done, vocals/effects only** (Cruel Summer 8). Groove/tech-house contexts where music keeps moving default SHORT (1-2), regardless of how quiet the mix measures. CSN 352's approved 16 (halftime lows-out breakdown, round 1) is consistent: a real stop into an ODDMOB monster.
3. The measured gap still plausibly CAPS the length (nobody asked for dark over landed music), and the busy test is not a hard veto (Diamond Therapy: 4 beats over a 0.93-duty build) nor a hard pass (Wanna Go Dancin': 0). The discriminator between those two is unknown at n=2.
4. **Marker hygiene is a first-class input:** three early-track/fake-drop/phrase-artifact cases (WHICH ONE intro, Show Me Love 0:11, kidstopbreathing fake drop; STFU chorus-remark = same section). The operator actively corrects markers when reviewing — consecutive chorus markers inside one drop section must read as ONE drop (matches the existing smart-drop main-vs-continuation design note), and track-start drops need damping (matches AWR-139's runway rule for lasers).
5. Rekordbox phrase edits made mid-review (ONE CHANCE, kidstopbreathing) mean those tracks' drop lists changed after this report's run — the report tool re-runs cheaply and picks them up; cache entries stay valid (beatgrids unchanged).

**F2-spec input (replaces §6b's level-term ask):** pre-drop blackout = quantized {1,2,4,8,16}, chosen by incoming-drop family/tier and a pre-window "true stop" class (percussion gone + vocals/effects only — derivable from cached `perc_full`/band series), capped by the measured gap, defaulting SHORT; drop markers de-duplicated per section (continuation markers) and damped near track start. These 11 labels are the calibration set; gather more only if the spec author needs a specific boundary.

## 7. Re-run

```bash
pgrep -f 'rb_ss_bridge_v2$' | wc -l            # must be 0
python3 tools/spectral_sweep.py --jobs 2       # refresh cache (idempotent; only uncached extract)
python3 tools/spectral_calibration_report.py \
    --json /tmp/awr147/report.json --markdown /tmp/awr147/report.md
```

The tool is read-only (never writes a cache entry, DB, ANLZ, or audio) and re-runnable by anyone later; per-drop records are exported so any single number can be spot-verified.
