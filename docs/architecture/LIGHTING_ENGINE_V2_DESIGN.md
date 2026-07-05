---
doc_status: current
truth_level: operator-authoritative intended behavior (design) + measured library audit (read-only)
last_verified_commit: 6bf2474
last_verified_date: 2026-07-05
validation_scope: design intent + read-only measurement only — the complete LIGHTING ENGINE v2 experience design, calibrated and dry-run-audited against the shipped v4 spectral cache (666 tracks), the Rekordbox DB, and ANLZ markers; no behavior change, no code change, no hardware validation
---

# LIGHTING ENGINE v2 — THE DESIGN

**This is the complete LIGHTING ENGINE v2 experience design — the single document the
Feature 1–4 Codex specs are authored from.** It expands the operator contract
(`lighting_engine_v2_authority.md`) into concrete, testable rules: the zone map, drop
families and intensity tiers, the darkness rule pack, the moment arbiter, the kill matrix,
the color-slot contract, the build moves, the new template roadmap, the laser package, and
observability — every rule proven by a dry-run audit over all 666 analyzed tracks in
Brandon's real library.

**Where this file lives and why:** `docs/architecture/`, because it is a standing
authoritative design document — the detailed companion to
`lighting_engine_v2_authority.md`, not a consumed-once plan. It stays authoritative after
the specs are written and after the build: post-build, behavior that differs from this
document is a regression unless this document is intentionally updated, and the library
audit defined in §13 re-runs through the real code as the regression tool. The all-caps
filename is deliberate: it sorts to the top of `docs/architecture/` and is unmistakable.

**How to read it:** every major section opens with *What the room does* — plain language,
no jargon, written for Brandon. The *Exact rules* block after it is for the spec authors
(Claude/Codex): formulas, constants, anchors, file:line seams. Constants marked
**TUNE-LIVE** are starting values; Brandon's eyes on the room are the only acceptance gate.

Charter: `lighting_engine_v2_strict_review.md` §6 (items 1–11 are §2–§12 here; item 9's
audit is §13). Operator locks are never overridden — challenges sit veto-shaped in §15.

---

## 1. The show this document builds

**What the room does.** Every track wears its own colors and wears them every night. The
room follows the music's shape — simmering when the track goes atmospheric, grooving in
color through the body, climbing through builds with white rising as the build gets
meaner — and when a drop comes, the room *knows*: the lights squeeze or cascade or swell
into the downbeat, the room goes truly black for exactly as long as the track's own floor
is empty, and the drop explodes at full power, dressed to match how hard that specific
drop actually hits. Lasers stay quiet through the verses and cut through the haze on the
track's biggest moments, in colors chosen to contrast the walls. Your hands always win.

Seven laws govern everything below (operator-locked, from the authority doc §1): one
engine at a time; manual always wins; markers are authoritative; texture decorates and
never decides; drops always render full-scale; total darkness is a designed tool; no
double drops.

**Evidence discipline.** Every load-bearing claim here is labeled **confirmed** (measured
this session against the shipped v4 cache / current ANLZ / code at HEAD, or a named prior
measured fact), **decided** (a design call delegated to this phase — reason given),
**live-gated** (taste; the live pass decides), or **unknown**. The full dry-run audit
(§13) ran the complete decision pipeline below over every one of the 666 cached tracks;
the headline: **every track gets a defined outcome at every decision point** — a zone, a
family (neutral counts) and tier per drop, a darkness decision per drop, a texture read
(none counts), a section/rate read, and a white share per build. No track falls off the
map.

---

## 2. The zone map (charter item 1)

**What the room does.** Each track lands in one of six color *zones* by its measured
character, then a per-track fingerprint picks its exact colors inside that zone — so two
tech-house tracks are neighbors, never twins. Smooth tracks live in the cool families:
icy bright blue/cyan with white headroom (**GLACIER**), deep dark blues (**DEEP POOL**),
or nocturnal violets (**TWILIGHT**). Aggressive tracks go electric: acid cyan/lime neon
(**ION**), hot magenta/electric violet (**VOLT**), and the distorted extreme earns deep
red and purple with white violence (**EMBERCORE**) — true red stays rare because only the
library's most distorted slice can reach it. Anything unmeasurable lands in a safe
neutral. Your two reference calls both reproduce from measurements alone: STARsound (pt3)
comes out bright cool — blue/cyan/white — and Can't Say Nah comes out dark cool.

### 2.1 Exact rules — axes and scores

All inputs are per-track values already stored in (or derived at load from) the v4 cache:
the identity axes `grit`/`punch`/`bass`/`drama` (`spectral_profile.py:111-118`), scalars
`brightness_med`/`attack_low_p90`/`onset_mh_p90`/`growl_timbre_p90`
(`audio_spectral_features.py:118-121`), and the track's sustained-synth rate (fraction of
beats with `sustained_synth_flags` true, `spectral_profile.py:245-255`).

Normalization anchors are the library's p5–p95, measured on the 666-track corpus
(2026-07-05) and **frozen as absolute constants** (corpus-absolute rule, review 4.5 —
these are constants now, not live percentiles):

```
norm(v, lo, hi) = clip((v − lo) / (hi − lo), 0, 1)
punch          lo 0.4298  hi 1.2
attack_low_p90 lo 6.7     hi 38.875
grit           lo 0.0137  hi 0.0776
onset_mh_p90   lo 2.0     hi 4.0
brightness_med lo 341.8   hi 1456.5
synth_rate     lo 0.053   hi 0.725
growl_timbre_p90 lo 0.1528 hi 0.377
```

Three scores per track:

```
aggression = 0.35·norm(punch) + 0.25·norm(attack_low_p90)
           + 0.25·norm(grit)  + 0.15·norm(onset_mh_p90)
luminance  = 0.60·norm(brightness_med) + 0.40·norm(synth_rate)
distortion = norm(growl_timbre_p90)
```

The luminance blend is the S-5.4 lesson applied at track scale: "bright/euphoric" is
harmonic-sustain presence plus spectral brightness, never centroid alone (STARsound's
euphoric sections measure `bright_tilt` = False — named prior fact).

### 2.2 Exact rules — zone assignment (frozen splits)

```
if unmeasurable (no v4 entry)          -> NEUTRAL
elif aggression >= 0.418:                             # corpus median, frozen
    if   distortion >= 0.75            -> EMBERCORE
    elif luminance  >= 0.52            -> ION
    else                               -> VOLT
else:
    if   luminance  >= 0.40            -> GLACIER
    elif luminance  <  0.28            -> DEEP_POOL
    else                               -> TWILIGHT
```

**Zone palette families** (decided; realized through the color-slot contract §8; exact
RGB ramps are Template-Lab/live work):

| Zone | Base ramp (slots 0–2) | Accent ramp (slots 3–4) | White (slot 5) | Laser pair (§11) |
|---|---|---|---|---|
| GLACIER | ice blue → bright cyan | cyan → near-white | generous | deep blue + amber |
| DEEP_POOL | deep blue → dark cyan | indigo → blue | scarce | deep blue + amber |
| TWILIGHT | violet → purple | purple → magenta edge | moderate | violet + amber |
| ION | electric blue → acid cyan | lime → white-hot | violent at peaks | cyan + magenta |
| VOLT | hot magenta → electric violet | acid cyan accents | violent at peaks | cyan + magenta |
| EMBERCORE | deep red → dark purple | red → white | white violence | red + white |
| NEUTRAL | today's blue_cyan journey family | — | default | default personality |

True red is EMBERCORE-only — "rare and earned" is structural: only distortion ≥ 0.75
(the corpus's top quarter) can wear it. Warm stops (orange/amber/gold) are **added to
`scale_stops`** (today six cool-only stops, `led_models.py:72-79` — confirmed) so amber
accents and laser pairing exist; they are accents, never zone families (lock honored).

**Audit result (confirmed, all 666 tracks):** GLACIER 119 · DEEP_POOL 133 · TWILIGHT 81 ·
ION 125 · VOLT 125 · EMBERCORE 83. Aggressive half = 334 tracks; largest aggressive zone
share = 37% (ION and VOLT tie at 125/334) — inside the charter's ≤ ~40% line (OLC-3
sameness engineering). Anchors: **STARsound (pt3) → GLACIER** (aggression 0.268,
luminance 0.436) and **Can't Say Nah → DEEP_POOL** (0.233, 0.267) — both anchor palette
calls reproduced from measurements alone (charter criterion 3 ✅). Kai Wachi — ILL and
Ray Volpe — DROP EM land EMBERCORE (both distortion 1.0); Knock2 — crank the bass lands
ION; LUNCH lands VOLT (aggressive + dark, luminance 0.19). Genre lens (validation only,
never an input): the six BY GENRE playlists pool coherently — hard techno pools
DEEP_POOL/TWILIGHT dark; dubstep/trap pools EMBERCORE/ION; house spreads across the
smooth half.

**Note on the anchor axes (correction, confirmed):** the strict review's T2-9 anchor
numbers (brightness_med 1059, drama 14.2) match the file "stargirl interlude starsound",
not the walkthrough's "kohta x Bafu — STARsound (pt3)" (671.3, 9.2, punch 0.851 — measured
this session). Two independent signatures prove the mixup (see §15.1). The anchor
separation survives on the correct file — STARsound (pt3) reads brighter and far punchier
than CSN — and the zone map above reproduces both calls from the correct file's data.

### 2.3 Exact rules — within-zone spread, depth, dynamics, permanence

- **Hash spread (decided):** `blake2b(content_id, fallback realpath)` → 16 hue slots
  across the zone's base-ramp hue range × 3 depth variants = 48 distinct dressings per
  zone. Neighbors differ visibly by construction (OLC-3): hue slot AND depth variant must
  both collide before two tracks twin (~1.4% chance per same-zone pair).
- **Depth axis** (saturation floor + gradient span): from `bass` duty — rolling sub →
  narrow, deep, saturated span; sparse sub → wider span, brighter, more white headroom
  (locked design, F1 item 4).
- **Dynamics budget** (how far looks travel between breakdown and drop): from `drama`
  normalized against corpus anchors (p5 7.0, p95 23.375, frozen). Budget drives excursion,
  never the drop ceiling (law 5).
- **Motion style**: punchy (norm(punch) ≥ 0.6) → sharp attacks, hard onsets; smooth →
  flowing sweeps (locked design; feeds §9's build-move selection).
- **Permanence:** identity = pure function of (content_id, frozen v4 measurements) —
  no RNG, no session seed, no deck salt (replaces the salted seed at
  `led_color_engine.py:374-375`, confirmed still salted at HEAD). The derived
  (zone, hue slot, depth variant) freezes into a file-backed per-track store at first v2
  derivation; analysis upgrades can never silently repaint (F-9/T2-2). The same store
  holds palette-pad corrections (palette lock while an override is active = permanent
  correction; unlock while that track plays clears it — post-review decision 2).
- **Fallbacks:** no v4 entry → NEUTRAL zone with the same hash spread (Tier 2 corner
  case: a brand-new purchase before first load; the 19 no-grid FX one-shots + 1 corrupt
  file). First load of a new purchase pays the one-time ~12 s analysis and has full
  identity from that load onward (seam confirmed, `state_manager.py:263-268` per the
  strict review).

---

## 3. Drop families and intensity tiers (authority §4.2 + charter item 11)

**What the room does.** Every drop cue is fired by your Rekordbox marker — never by the
analysis — but the *dressing* is chosen by how the drop actually sounds. Three families:
a distorted or trap-sparse monster gets the **WALL** treatment (full-strip stutter bursts
with darkness between hits); a fast, dark, pounding four-on-the-floor gets the **COMET**
(a relentless beat-locked chase, red where the zone allows it, white slamming the one); a
groove drop gets the **HOUSE** treatment (stab drops get the center-out pulse-expand
shockwave; growl-bar drops get the sparkle-burst that settles into the off-beat groove
chase). Anything thin or ambiguous stays **NEUTRAL** — an invisible miss instead of a loud
wrong guess. Separately, every drop gets an intensity **tier** — how violently the family
reads: tier 1 hits clean, tier 2 hits heavy, tier 3 is maximal. Full power every time
regardless (law 5) — the tier shapes aggression, never brightness.

### 3.1 Exact rules — family classifier (descriptors only, never genre labels)

Inputs: `drop_window_vector(v4, D, width=16)` (`spectral_profile.py:502-556`) with
`pre_gap` recomputed by §4's tolerant scan (S-1 inheritance, T2-7). `lift` =
`full_db − loudness_ref_db`.

```
coverage < 8                                   -> NEUTRAL (thin window)
lift < −7 and attack_low_p90 < 5               -> NEUTRAL (marker without a real hit)
bpm ≥ 146 and air_db < 0 and sub_db ≥ 24
      and onset_density_mh ≤ 3.2               -> COMET  (fast, dark-topped, pounding)
growl_flatness ≥ 0.27 and (high_db ≥ 4 or mid_db ≥ 8)   -> WALL (distorted bright jabs)
sub_db ≥ 26 and onset_density_mh ≤ 2.2 and pre_gap ≥ 1  -> WALL (trap vacuum: heavy sparse hits)
onset_density_mh ≥ 3.4 and high_db ≥ 5                  -> WALL (dense jab bursts)
116 ≤ bpm ≤ 144:
    low_swing_db ≥ 10.5 and attack_low_p90 ≥ 7          -> HOUSE (stab body → pulse-expand)
    growl_flatness < 0.24 and sub_db ≥ 20
        and low_swing_db < 10.5 and bass_db ≥ 14        -> HOUSE (growl-bar body → sparkle→groove)
otherwise                                      -> NEUTRAL (ties land neutral, F-11)
```

Trap and dubstep share the WALL family (operator lock, Appendix E / OLC-C); the trap
variant (sparse-hits vs dense-stutter) is texture-driven *variation inside* the family
(`onset_density_mh`, `pre_gap`), never a fourth family. The classification and its
plain-text reason are published per drop (§12).

**Audit result (confirmed, 3,936 drop windows):** HOUSE 1628 (41%) · WALL 812 (21%) ·
COMET 439 (11%) · NEUTRAL 1057 (27%). Genre lens (classifier never sees genres): HARD
TECHNO drops → 74% COMET; DUBSTEP/ISOXO/TRAPSTEP → 41–45% WALL; every house playlist →
50–65% HOUSE. A house-heavy library reading house-heavy, with a ~27% honest safety net.

### 3.2 Exact rules — the intensity tier (corpus-absolute)

Violence score per drop window:

```
violence = 0.30·clip((full_db − 8)/10) + 0.20·clip((lift + 4)/5)
         + 0.25·clip(attack_low_p90/16) + 0.15·clip(onset_density_mh/4)
         + 0.10·clip(pre_gap/8)
tier 3 (maximal)  violence ≥ 0.698     # frozen corpus p85
tier 2 (heavy)    violence ≥ 0.616     # frozen corpus p55
tier 1 (standard) otherwise
```

**Audit result (confirmed):** tiers 1/2/3 = 2159/1176/601. **Ray Volpe — DROP EM's four
drops land T2, T1, T1, T2** (violence .619/.481/.586/.653; attack spans 2.7→16.1 dB as
the strict review measured) — not all in one tier: **charter criterion "Done when #2"
passes.** Post-drop cues inherit their drop's tier (settled expansion note, charter §6.1).

### 3.3 Exact rules — tier × family → aggression profile (the violence knobs)

Full-scale always; the tier sets *how the power reads* (authority §4.2). SET mode's
peak-reservation reads this same tier (only T3 drops get the true ceiling while SET is
held; WILD OUT ignores the reservation — every drop uses its own tier's profile).

| Knob | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| Strobe structure | none / single accents | burst clusters | continuous wall (WALL) / hard slams (COMET) / dense sparkle (HOUSE) |
| Animation rung (§5.2) | 1 beat | 0.5 beat | 0.25 beat where BPM ≤ 113, else 0.5 |
| White share | accents riding zone color | white-hot core, color edges | maximal white per family idiom |
| Motion violence | family baseline | wider, harder attacks | full-span, hardest attacks |
| Inter-hit micro-darkness | none | brief (WALL only) | full vacuum between hits (WALL); none for COMET (relentless is the point); HOUSE keeps color floor |

Family anchors (operator archetypes, confirmed against measured drops): hard-techno
**relentless** (COMET T2/T3 — driving red comet, white slamming the one, no gaps),
ISOxo-grade **maximal** (WALL T3 — full-strip white stutter at half/quarter rates,
darkness between hits), groovy-house **bounce** (HOUSE any tier — color-forward pulse,
white as accents, never a wall).

---

## 4. The darkness rule pack — pre-drop blackout + dips + flicks (charter item 5, S-1)

**What the room does.** Before a drop, the engine reads the track's own emptiness from
the cached analysis. If the floor genuinely empties, the room goes truly black for
exactly that long — capped at 16 beats — running dark through the pickup hit and
exploding at your marker. If the floor comes back early and stays back, the blackout lets
go instead of sitting black over landed music. If the "empty" stretch is actually a busy
build (drums pounding over a missing sub), the room does NOT black out — the buildup cues
own it with a hue shift. If the whole mix ducks for a moment (your "lights cut"
moments), a short relative-dip cut fires, up to 4 beats. And when music slams straight
in, you get the snap-to-black flick — stretched to a full beat when the analysis sees a
percussive cut right before the marker. Long empty breakdowns ride *sparse and dim*, never
black — true black belongs to the blackout window alone (your confirmed call, OLC-A).

### 4.1 Exact rules — the per-drop decision (pure function over cached series)

For drop marker `D`, with per-beat `sub_db`, `bass_db`, `full_db`, `growl_band_db`:

1. **Floor notion is sub-only** (S-1b): `gone[i] = sub_db[i] < 5.0` (the corpus-calibrated
   bimodal valley — named prior fact). The AND-rule (`bottom_gone_flags`,
   `spectral_profile.py:121-129`) stays for the texture-darkness consumer only.
2. **Tolerant scan** (S-1a): find the newest `gone` beat `e` with `D−4 ≤ e ≤ D−1`
   (pickup tolerance 3 beats); walk back to the run start; `raw_gap = e − start + 1`.
   No `e` found → step 6.
3. **Busy-build test (decided — the discriminator the anchors demanded):**
   `bass_duty` = fraction of run beats with `bass_db ≥ 8.0`. If `bass_duty > 0.85` the
   run is a build riding a gone sub (drums/riser fully busy) — **no blackout**; the
   buildup cues + "lows out" hue shift own the stretch; check step 5 then step 6.
   Calibration: CSN's builds before drops 128/160/…/416 read duty 1.00 (killed —
   walkthrough wants groove/buildup looks there, not black); ILL's 12-beat gap reads
   duty 0.17 and its 3-beat gap before 141 reads 0.67 (both survive); CUT TF UP's
   long empty floor before its 128 drop reads 0.78 (survives → capped blackout — the
   build record's own outline calls this gap "the blackout sizer's input"). All
   confirmed measured this session.
4. **Blackout**: `gap = min(raw_gap, 16)`; window `[D − gap, D)` — dark *through the
   pickup into the hit* (authority 4.1 rule 2); drop cue fires at `D` (markers
   authoritative, always). **Floor-returned abort** (S-1c/OLC-B): darkness ends at the
   2nd consecutive floor-present beat inside (or immediately entering) the window —
   precomputed from the cache, reported as `abort_at`. A 1-beat pickup never aborts
   (dark through the pickup); a genuinely returned floor does.
5. **Relative dip** (S-1d): for beat `b`,
   `dip_score(b) = (med(full_db[b−16..b−1]) − full_db[b]) + 0.25·clip(med(sub[..]) − sub_db[b], 0, 8)`,
   fires at `dip_score ≥ 4.0` with the floor present (`sub_db[b] ≥ 5`), capped 4 beats
   (**TUNE-LIVE**; the sub-assist term is why STARsound's 2:16.5 cut fires — its
   full-band drop alone measures 3.1 dB). Standalone dip runs also fire outside loud
   sections anywhere in the track (the 2:12.4 "lights cut" case).
6. **Snap flick**: no gap, no dip → snap-to-black flick, 125–250 ms (**TUNE-LIVE**),
   **upgraded to a full 1-beat cut** when the pre-marker beat carries a measured
   percussive cut: `growl_band_db[D−1] ≤ growl_band_db[D−2] − 5.0` (decided; calibrated
   on CSN beat 127, which cuts 6.5 dB — the walkthrough's "minor percussive cut →
   1-beat blackout"; fires at 105 of 3,936 drops corpus-wide, appropriately rare).
7. **Breakdowns ride sparse-and-dim** (OLC-A, operator-confirmed): floor-out beats
   inside quiet sections get the simmer floor (§5.4) — near-black, never true black —
   so a 99-beat empty breakdown reads as a low simmer sliding into the capped 16-beat
   true blackout.

Everything above is arithmetic over already-cached series — no re-analysis, ever
(authority 4.1). Each decision publishes `(kind, gap, window, abort_at, reason)` (§12).

### 4.2 Acceptance — the named gaps, from the shipped cache (charter criterion 2)

Measured this session by running exactly the rules above on the shipped v4 cache + current
ANLZ markers (confirmed):

| Case | Criterion | Measured result | Verdict |
|---|---|---|---|
| ILL drop 109 | 12 beats, sub-only | blackout **12** — window [97,109), no abort (run bass_duty 0.17) | ✅ exact |
| ILL drop 261 | 2 beats | blackout **2** — window [259,261), the beat-260 riser pickup rides dark | ✅ exact |
| ILL drop 141 | (Appendix B: 3-beat gap) | blackout **3** — window [138,141), duty 0.67 survives the busy test | ✅ |
| CSN drop 352 | 26 → capped 16 | blackout **capped 16** — window [336,352); the sub-only run measures **99 beats** (the whole lows-out breakdown; the review's 26 was the AND-rule figure); preceding beats ride sparse-and-dim | ✅ same window, number corrected (§15.2) |
| CSN drop 128 | walkthrough: 1-beat cut at 127 | busy build correctly refuses a 7-beat blackout (duty 1.00); **relative-dip/perc-cut 1-beat** fires at 127 | ✅ walkthrough behavior |
| STARsound (pt3) drop 131 | 2 beats with floor-return abort | **relative-dip 2 beats** at [128,129] (score 8.4), light released before the marker; the sub never crosses the gone threshold there in the current cache (the review's gap-at-126–127 row matches the *stargirl interlude* file — §15.1). The abort mechanism itself is kept and fires at **150 drops corpus-wide** (e.g. crank the bass drop 96: gap 4, abort at 95 → 3 dark beats) | ✅ in substance; provenance corrected |
| Snap-flick coverage | classifications where the operator described none | 1,366 snap flicks + 105 perc-cut flicks across the library | ✅ |

Corpus distribution (confirmed): 1,320 blackouts (dark-beat histogram spreads 1→16 with
219 at the 16-cap), 1,145 relative dips, 1,366 snap flicks, 105 perc-cut flicks, 150
aborts — every one of 3,936 drops has a defined darkness decision.
