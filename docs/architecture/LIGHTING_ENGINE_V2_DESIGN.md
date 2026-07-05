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

---

## 5. The rest of the consumer-rule pack (charter item 5: S-3, S-5)

Each rule is a pure function over cached series, with a pinned formula, a walkthrough
calibration anchor, and its own test seam (table-driven unit tests on synthetic series —
the same seam pattern the strict review demanded).

### 5.1 Bass-forward beats (S-3 — the tech-house "growl" answer)

**What the room does.** Inside a tech-house drop, the beats where the bassline leads get
the strobing sparkle, and the kick-driven beats get the driving post-drop chase — the
alternation you narrated on Can't Say Nah — beat by beat, without ever touching when or
whether the drop fires.

**Exact rule (decided).** Within a drop window `W` (16 beats), with
`ceil = p90(growl_band_db[W])`:

```
bass-forward(b) = growl_band_db[b] ≥ ceil − 3.0     # near the drop's own bass ceiling
              and growl_band_db[b] ≥ 18.0            # real bass present
              and attack_low_db[b] < 9.0             # sustained shape, not kick-spiked
kick-driving(b) = attack_low_db[b] ≥ 9.0
```

Calibrated on CSN's drops (confirmed): the pattern at drop 128 reads
`BKBBBKBBBKBBBKBB` — bassline-led beats with the kick accent landing every 4th — the
walkthrough's growl-vs-driving alternation, at beat grain. Consumed only at drop-cue
variant selection (S-2 containment: texture picks *which* drop-family variant seasons the
beat, never whether/when). Honest name: bass-forward, not "growl" — the distortion class
`growl_flags` keeps its own meaning (it measures distorted timbre and correctly reads 0
on CSN — named prior fact). **Live-gated:** the B/K grain vs the operator's felt "~4-beat
growl figures" is a seasoning-density taste call.

### 5.2 Build intensity → white share (S-5.1)

**What the room does.** A modest build gets white mixed into the track's color; a monster
build earns full white at the top. The build's own measured energy sets the mix.

**Exact rule (decided).** Over the buildup window (buildup marker → next drop marker,
capped 64 beats), split the window in half:

```
flux_rise  = mean(fluxsum_midhigh[2nd half]) − mean(fluxsum_midhigh[1st half])
level_rise = med(full_db[2nd half]) − med(full_db[1st half])
E = clip(0.5·clip(flux_rise/40) + 0.5·clip(level_rise/6), 0, 1)
white_share = clip(0.25 + 0.75·E, 0.15, 1.0)          # TUNE-LIVE
```

Anchor (confirmed): CSN's build into drop 128 lands in the low band (the walkthrough's
"white+blue mix instead of full white — this build is not too intense"). Corpus
(confirmed): white share masses at 0.2–0.4 with a long tail — 85 builds ≥ 0.6, 9 ≥ 0.9 —
monsters earn full white, ordinary builds get mixes. Applies to buildup-cue white
fraction through the color-slot contract (slot 5 weight, §8).

### 5.3 Animation-rate rung selector (S-5.2)

**What the room does.** Atmospheric moments move every 4, 2, or 1 beats by how sparse
they are; grooves move every beat; drops move every beat, half-beat, or quarter-beat by
tier. The 30 fps physics stays honored — quarter-beat strobing only where the frame clock
can actually render it.

**Exact rule (decided).** Sections (from `section_map`, marker-forced): tier `quiet` →
rung 4 if simmer (§5.4), rung 2 if `med(attack_low_db) < 6`, else rung 1; tier `mid` →
rung 1; tier `loud` → rung 1 (drop cues override with their own rung). Drops: tier 1 → 1;
tier 2 → 0.5; tier 3 → 0.25 **only when BPM ≤ 113** (0.25-beat events at higher BPM fall
between the 30 fps frame-divisible rates and alias — T2-10/F-6), else 0.5. Audit
(confirmed): drop rungs 1.0/0.5/0.25 = 2159/1775/2 — the 0.25 rung is honestly rare in a
128–160 BPM library; tier-3 aggression at high BPM is carried by intensity/width and
micro-darkness instead (F-6's stepped-rate + rising-intensity design).

### 5.4 Atmospheric simmer (S-5.3)

**What the room does.** Percussion-free stretches read as a low simmer — the room breathes
near-dark in the track's colors instead of playing a groove nobody hears.

**Exact rule (decided).** A `quiet` section is a simmer when `med(attack_low_db) < 2.5`
and `med(onset_density) < 0.5`. Anchors (named prior facts): Girl$ 1:32–2:12.4 (attack
median 0.7 dB), STARsound's intro (2.3 dB). Audit (confirmed): 236 of 666 tracks carry at
least one simmer section. Simmer rendering = the sparse-and-dim floor (OLC-A): dimmest
zone colors, rung 4, near-black excursions allowed, never true black.

### 5.5 Bright-euphoric treatment eligibility (S-5.4)

**What the room does.** When a euphoric synth wall is playing — STARsound's "pack of
swordfish" sustain, Chemicals' pads — the room is allowed the bright cyan/white sustain
treatment at reasonable speed.

**Exact rule (decided).** A window is euphoric-eligible when `sustained_synth_flags` runs
≥ 8 consecutive beats (the class already requires clean timbre + real harmonic mids —
`spectral_profile.py:245-255`); **never** `bright_tilt` (measured False on STARsound's
euphoric sections — named prior fact). Treatment = selection-only within the scheduled
moment (S-2): it flavors the playing role cue toward the zone's bright/white end, it
schedules nothing. Audit (confirmed): 572 of 666 tracks have ≥1 eligible run — a
selection signal, deliberately permissive; the moment's owner still decides.

### 5.6 Relative dip (S-1d — standalone)

Defined in §4.1 step 5. Standalone runs fire only outside `loud` sections, cap 4 beats,
rendered as a short cut of the *current* look (not the blackout look). Audit (confirmed):
median 4 dip runs per track; the dip-storm tail (≥12 runs) is outlier-flagged (§13).

### 5.7 What is never promised (charter §6.3 — designed around, honestly)

Chorus-vs-drop softness (measures identical on primary energy); growl-intensity ranking
(ear ranks, levels read equal — drop growls treated uniformly); slow/formant "wow-wow"
wobble (level-invisible; the named frame-rate-centroid schema extension stays deferred);
kick-prominence under sidechained walls and `sustained_synth` on thick layered walls (two
recorded limitations — scrub-gated, not retuned here); `lowmid_pulse` breadth (wobble,
rolls, chugs, sirens all fire it — used strictly as busy/aggressive seasoning, never
"wobble" semantics). No rule above reads any of these as a promise.

---

## 6. The moment arbiter (charter item 2, F-4 + S-1/S-2 members)

**What the room does.** When designed moments collide on the same bars, exactly one wins
and the losers are skipped — never queued, never stacked. Your hands and the emergency
blackout beat everything, always.

**Exact rules (decided).** One precedence list, applied at dispatch. A *claim* is a beat
window `[start, end)`; while a claim is active, lower-ranked moments whose window overlaps
are skipped outright (moments, not tasks). Mode/engine flips act at the next look
boundary, never mid-move.

| Rank | Moment | Claim window | Notes |
|---|---|---|---|
| 0 | Emergency blackout / manual holds / static overrides / LED mute | absolute, unchanged authority | never contested; a held manual look survives every v2 moment |
| 1 | Pre-drop blackout + drop cue | `[D − gap, D + drop_hold)` | the floor-return abort acts *inside* this window (it ends darkness early; it never yields the window); the drop-cue variant seasoning (S-2, §5.1) rides inside the cue, claiming nothing |
| 2 | Landing build move (squeeze/fuse/swell, landing restore) | `[target − travel, target)` | if rank 1's blackout window overlaps, the build move ends where darkness begins (squeeze-into-black is the composed arc, §9) |
| 3 | Blend resolve (one-bar bloom at blend cross-and-hold) | 1 bar | skipped entirely if it lands inside rank 1–2 claims |
| 4 | Palate reset (hard genre pivot neutral dip) | 1–2 s | |
| 5 | First-play bloom | 2 bars (after ~8-beat hold gate) | a bloom never brightens into a blackout — rank 1 wins (the F-4 scenario) |
| 6 | Phrase step / turnaround stinger | phrase boundary ±1 bar | own short cooldown class (F-12): stingers/bursts get a short cooldown; drop-scale impacts keep the 12 s class |
| 7 | Texture seasoning + simmer + euphoric flavoring | none (selection-only) | reads at cue selection/parameterization inside whatever the schedule chose; the scheduler never sees texture (S-2); simmer is the lowest-priority *look*, claimed only when nothing above is active in a quiet section |

Skip-not-queue is literal: a skipped bloom does not fire late; a skipped stinger waits for
the next phrase end. The arbiter is engine-side and pure (testable as a table of
overlapping claims → surviving moment).

---

## 7. The kill matrix (charter item 3, F-3)

**What the room does.** Every behavior in this design belongs to exactly one switch. Kill
a feature mid-night and the room degrades to something coherent — never undefined colors,
never a stuck look, never a new dark-room failure.

**Exact rules (decided).** Master switch: v1/v2, live-switchable; v2 off ⇒ v1
byte-identical (teardown through the existing reset/idle machinery; the newly active brain
takes over at next dispatch — no cross-engine blending). Every row lands in exactly one
owning switch; flips take effect at the next look boundary.

| Behavior (this document) | Owning switch | Off ⇒ |
|---|---|---|
| Zone map, hash spread, depth/dynamics axes (§2) | **F1 identity** | today's journey palettes (`_pick_palette`); texture keeps shapes with v1 colors |
| Identity permanence store + palette-pad correction path (§2.3) | F1 | store unread; pads keep their v1 palette-override meaning |
| First-play bloom (authority §3) | F1 | no bloom |
| Identity handover soft flip on active-deck flip (F-10) | F1 | v1 deque behavior |
| Motion-style + dynamics-budget selection (§2.3) | F1 | v1 look selection |
| Arrival scheduler: landing comets/sweeps (authority §4) | **F2 landing** | cues trigger on the beat as today |
| Build-move family + landing restore (§9) | F2 | no build moves; role changes as today |
| Pre-drop blackout pack — all of §4 (blackout, abort, busy test, dips, flicks) | F2 | the fixed `led_predark_beats: 4` predark in live config (confirmed present) |
| Drop family classifier + intensity tier + aggression profile (§3) | F2 | v1 drop cues (role banks / drop_pairs) |
| White-share formula (§5.2) | F2 | buildup cues keep baked white behavior |
| Rate-rung selector (§5.3) | F2 | cues' own baked rates |
| Phrase-end turnaround stinger + cooldown classes (§6 rank 6) | F2 | no stingers; 12 s class untouched |
| Blend painter: accents-first entry, base morph, resolve, dipless, abandon breathing (authority §7) | **F3 blend** | handover = F1's soft flip only |
| Texture classes (kick-prominence, thick/thin, tilt, stab/sustain, darkness, simmer §5.4, euphoric §5.5, bass-forward §5.1, busy-pulse) | **F4 texture** | role cues untouched by construction (containment); drop cues use family default variant |
| WILD OUT / SET mode (authority §9) | mode toggle (not a kill) | n/a — WILD OUT is default; SET withholds slot-5/strobe/span on T1–T2 drops |
| Laser personality-by-zone + complement pairs (§11) | laser director config (existing enable/dry-run) | today's alias/default resolution (`personality_resolver.py`) |

**Dependency rules (the three from F-3, plus one new):**
1. **F1 off + F3 on** ⇒ blend auto-collapses to the soft flip (no identities to blend);
   the blend scalar keeps computing (cheap), paints nothing.
2. **F2 off** ⇒ blackout reverts to fixed 4-beat predark; landing moves and drop typing
   off; F4's drop-variant seasoning has no v2 drop cue to season — v1 drop cues run
   untouched.
3. **F4 off** ⇒ §5.1/§5.4/§5.5 selection inputs read as "no texture" — family default
   variants everywhere; nothing else changes (containment guarantees coherence).
4. **F1 off + F2 on** (new, decided) ⇒ drop families/tiers still classify and fire, but
   render through v1 palette colors (the family shapes take whatever color the v1 journey
   supplies through the slot contract's defaults) — landing stays useful without identity.
- **Scripted tracks:** v2 stands down completely — no identity repaint, no landing, no
  audio-matched blackout, no texture, no drop typing; v1 scripted rendering exactly as
  today (authority §11 boundary ruling; operator veto stays open).
- **Realtime transport loss:** v2 features suspend to the existing v1 fallback; status
  shows `engine=v2 (suspended: transport)`; nothing v2 adds may create a new dark-room
  failure mode (authority §11).
- **Mid-move master flip:** teardown through reset/idle machinery
  (`beat_sync_engine.py:128-131` seam, confirmed by the design review); arrivals melt or
  finish wall-clock; no v2 instance survives into v1 frames.

---

## 8. The color-slot contract (charter item 4, F-8)

**What the room does.** Every look the engine can play takes its colors from six named
slots instead of baking them in — so the track's identity, the blend painter, and SET
mode all speak one language to every shape in the library.

**Exact rules (decided).** The renderer already carries the seam: slot-parameterized
shapes read `params["slot_colors"]` through `universal_colorizer`
(`govee_frame_renderer.py:1026-1056`, validated by `_slots()` at `:42-62`; six-entry
convention already in live use — confirmed by the renderer inventory this session). The
contract formalizes it:

| Slot | Meaning | Supplied by |
|---|---|---|
| 0–2 | **base ramp** (dark → core of the zone's base family) | identity (zone + hash) |
| 3–4 | **accent ramp** (the zone's accent pair) | identity; the blend painter takes these FIRST (accents-first entry) |
| 5 | **white** (the power channel) | white-share (§5.2) scales its weight; SET withholding removes it on held drops; sustained white banned outside manual looks (white-is-a-burst lock) |

- **Authoring rule:** every NEW v2 shape (all of §10) is authored against slots only —
  Template Lab supplies shapes, the engine supplies colors (locked design 5.12/5.14). No
  new baked-color cue is ever added.
- **Blend painter:** paints slots 3–4 from the incoming identity as presence steps rise,
  morphs slots 0–2 in palette space past the midpoint, snap-commits distant identities
  (no muddy midpoint — lock). The runner's `resolve_fade` already interpolates
  `slot_colors_from/to` per frame (`govee_frame_renderer.py:74-97`, confirmed) — the
  blend's per-frame color path exists.
- **Legacy looks:** the 15 color-suffix names (3 shapes × 5 colors) and other baked cues
  (e.g. `_drop_center_burst_blue_cyan`, hardcoded cyan/white nebulas — inventory,
  confirmed) carry forward for v1 byte-identity and become selection-eligible in v2 only
  through their slot-based siblings (`_slot_*` twins already exist for most). The
  `color_source: engine|baked` flag (`led_models.py:54,241`, confirmed) marks
  eligibility, exactly as today.
- **Spec-author warnings (from the renderer inventory, confirmed):** (a) comet-family
  names bypass `renderer.render()` on the live rig — `_compose_frame` routes them
  straight to `render_comet` (`govee_realtime_runner.py:357-374`), so the slot contract
  must be honored in `render_comet`'s color resolution too, not just `render()`;
  (b) `render_comet`'s name-based color fallback freezes beat-dependent suffix colors at
  beat 0 (`govee_frame_renderer.py:1882`) — engine-supplied slot colors make the fallback
  dead weight rather than a bug; (c) buildup shapes currently have NO slot-parameterized
  variants (6 baked white-only shapes — the §10 roadmap fills this); (d) `EffectSpec`
  lives at `govee_realtime_runner.py:36-42` and `params` is the single conduit — the
  color engine reaches every shape through it.

---

## 9. The build-move family, in detail (charter item 7)

**What the room does.** Builds stop reacting and start aiming. Three physical shapes, all
landing exactly on the one: **squeeze-explode** — the light contracts toward the strip's
center and compresses brighter as the build climbs, then detonates outward on the
downbeat; **fuse** — segments ignite one by one, a burning line racing the build, the
last segment igniting exactly on the drop; **swell** — an 8-bar breath that rises and
completes precisely at the phrase turn. And the marquee moment, **landing restore**: in a
breakdown the room eases down within the track's dynamics budget, then light flies back in
and lands on the drop's first beat — the one moment guests will describe out loud.

**Exact rules.**
- **Machinery:** all four are arrival-contract instances on `BeatSyncEngine`
  (`target_abs_beat` = the drop marker / phrase boundary, `travel_beats` per move);
  per-frame retarget from the live anchor (riding the pitch bends the flight, the landing
  stays pinned); backward jumps degrade to wall-clock completion or melt; instances stamp
  (deck, load_gen) and never retarget across decks (F-5). All seams confirmed by the
  design review at HEAD.
- **Per-track move selection (decided — from measured character, per-track permanent):**

```
norm(punch) ≥ 0.60 and norm(attack_low_p90) ≥ 0.45              -> squeeze-explode
norm(onset_mh_p90) ≥ 0.5 and p50(within-beat low swing) ≥ 10 dB -> fuse
otherwise                                                        -> swell
```

  The move is part of the track's identity (locked design F2 item 2); the white share it
  carries comes from §5.2's per-build measurement.
- **Squeeze + blackout compose:** when §4 sizes a blackout, the squeeze contracts INTO the
  blackout window (light compresses to center, then to black, then the drop detonates) —
  rank 1/2 composition per §6. Fuse and swell simply end where darkness begins.
- **Landing restore eligibility (P-3):** a `quiet`/`mid` section run of ≥ 16 beats ending
  at a drop marker, with the room already eased down (dynamics budget), arms a restore:
  travel = min(16, section remainder), target = the drop beat. Marker absent ⇒ no move
  (safe absence). Owned by F2.
- **Strobe acceleration stays inside buildup cues** (operator correction 2): the §10
  buildup shapes own their acceleration; the role system schedules them; §5.2 sets their
  white; §5.3 sets their rung ceiling.

---

## 10. The new-template roadmap (charter item 10 — v2 is not v1 repainted)

**What the room does.** Every role gets genuinely new shapes, not recolors. Below is the
authoring menu — each described visually, authored in Template Lab against the color-slot
contract (§8), and selected by measured character/energy, never hand-assigned per track.
Authoring and tuning happen in the build + live phase through the existing Template Lab
flow; this is the binding menu.

**Selection inputs** (per §2/§3/§5): zone, motion style, drop family + tier, texture
classes, section tier + rung.

| Role | New shape | Visual (what you see) | Selected when |
|---|---|---|---|
| Groove | **Undertow** | the base wash flows slowly one direction while accent ticks ride the opposite way — quiet tension in motion | smooth motion style, mid sections |
| Groove | **Heartbeat** | a two-pulse lub-dub swell on the kick, color-only, no white | kick-prominent texture, DEEP_POOL/TWILIGHT |
| Groove | **Offbeat skip** | the chase head lands between the beats — the room rides the "and" like a hi-hat | HOUSE-family tracks, groove sections (round-4 off-beat idiom, TUNE-LIVE) |
| Buildup | **Squeeze** (§9) | light contracts to center, compressing brighter | squeeze-explode tracks |
| Buildup | **Fuse** (§9) | segment-by-segment ignition racing to the one | fuse tracks |
| Buildup | **Riser stack** | sparkle density + white share climb the measured build energy; rate steps 1 → 0.5 → 0.25 beat as the drop nears | any build; white from §5.2; gives buildup its first slot-authored shapes (today's six are baked white-only — inventory, confirmed) |
| Drop | **Wall-stutter** | full-strip white bursts with true black between hits — each hit lands harder for the darkness | WALL, tier 2–3 (micro-darkness per §3.3) |
| Drop | **Red-line** | one relentless beat-locked comet, white slamming every downbeat, zero gaps | COMET (red only where the zone permits: EMBERCORE keeps red; other zones run their base-ramp core) |
| Drop | **Shockwave** | center-out expanding hit on every beat — the strip breathes outward like a struck surface | HOUSE stab body |
| Drop | **Sparkle-burst → groove** | one bright burst on the one, settling immediately into the off-beat groove chase | HOUSE growl-bar body (CSN's walkthrough drop) |
| Post-drop | **Ember decay** | the drop's white hits cool into the zone color over 8 beats — the room exhales | any family, tier ≥ 2 |
| Post-drop | **Afterglow ripple** | each hit leaves a slow-fading pool that drifts outward | smooth motion style |
| Breakdown / atmospheric | **Simmer floor** | near-black shimmer in the zone's dimmest colors, moving every 4 beats | simmer sections (§5.4) |
| Breakdown / atmospheric | **Tide** | one ultra-slow luminance wave crossing the room per 2–4 bars | quiet non-simmer sections, smooth tracks |
| Breakdown / atmospheric | **Deep drift** | the base ramp itself slowly rotates hue within the zone — the room breathes color instead of brightness | long breakdowns, dynamics-budget-rich tracks |

Carried forward as-is: the existing ~14 slot shapes and the validated comet/sweep idiom
(landing-upgraded per §9), bloom, stingers, the blend painter. Banned stays banned: busy
multi-color segment chases; sustained white outside manual looks.

---

## 11. The laser package (charter item 6 — haze era, gated on the hardware catalog)

**What the room does.** Lasers rest through verses and fire on the track's biggest
moments (the drop-presentation ladder already guarantees scarcity — unchanged). With haze
confirmed, beams are the design material: aerial fans, sky effects, beam chases. Each
color zone carries a fixed laser accent pair chosen to cut against the LED wash — deep
blue walls get amber beams, neon walls get cyan/magenta, the extreme gets red/white. The
exact beam vocabulary waits for one working session with the hardware.

**Exact rules.**
- **Picker replacement only** (authority §6): the same zone from §2 picks the laser
  personality; scenes, safety classes, cooldowns, fallbacks, and the MIDI executor all
  keep. Today's resolver order is alias → BPM band → default
  (`personality_resolver.py:76-111`, confirmed), and the BPM tier is currently inert
  (`bpm_priority: []` in `config/laser_director.json:236` — confirmed this session), so
  v2's zone input replaces a resolution path that today only ever falls through to
  `house`. Clean seam.
- **Zone → personality map (decided):** GLACIER/DEEP_POOL/TWILIGHT → `smooth` personality
  (accent pair deep blue + amber; TWILIGHT may ride violet + amber); ION/VOLT → `neon`
  (cyan + magenta); EMBERCORE → `extreme` (red + white); NEUTRAL/unmeasured → existing
  default (`house`) exactly as today (safe fallback confirmed,
  `personality_resolver.py:107-111`).
- **Color plumbing exists:** lasers already follow the LED engine on non-scripted tracks
  (CH8 color / CH9 speed overwrite through `_merge_color_snapshot`,
  `soundswitch_laser_player.py:124-129,462`; RGB→fixed-color quantizer — confirmed). The
  complement pairs ride this: with a v2 identity active, the laser color engine quantizes
  toward the zone's accent pair instead of nearest-LED-color. Scripted tracks stay
  sovereign (untouched).
- **Personality package skeletons (the config shape a new package must fill — from
  `laser_models.py:80-118` + `laser_config.py:611-753`, confirmed):** per personality:
  seven required role→scene refs (`safe/default/phrase/buildup/drop/breakdown/
  transition_scene`), optional per-role rotation banks, `allow_high_impact`, timing knobs
  (`phrase_interval_beats`, `pre_drop_blackout_beats`, `post_drop_hold_beats`,
  `drop_impact_beats`, …). Three new packages (`smooth`, `neon`, `extreme`) are drafted
  with today's 19 scenes as placeholders and **named TBD beam-scene slots**:

  - `TBD smooth_beam_slow_fan` — wide slow aerial fan, amber/deep blue, phrase-scale sweep
  - `TBD smooth_beam_liquid` — slow liquid-sky drift for breakdowns
  - `TBD neon_beam_crossfire` — two fast crossing fans, cyan × magenta, drop-only
  - `TBD neon_beam_chase` — beat-locked beam step-chase for post-drop
  - `TBD extreme_beam_slam` — hard white/red center slam on the one, tier-3 drops
  - `TBD extreme_beam_strobe_fan` — strobing fan burst inside WALL micro-darkness gaps

  **Every TBD slot is gated on the operator+Claude hardware-vocabulary session**
  (correction 6a): catalog the real MIDI-reachable patterns, size, motion/rotation speed,
  color, strobe on CH8 (color/effects), CH9 (speed), CH11 (strobe). **No MIDI values are
  invented here**; the session's catalog fills the slots, then packages are auditioned
  live Template-Lab-style and locked. Beams-above-heads stays an authoring guideline
  (S-6), never an engine rule.
- **Rest vs fire:** unchanged drop-presentation authority (v1 carryover): LEDs carry most
  drops; the top ~40% ranked drops earn lasers; Laser Solo stays operator-traceable-only;
  damper/finale/fail-open rules untouched (confirmed at
  `drop_presentation.py:100,293-311,326-377,628-745` by this session's inventory).

---

## 12. Observability (charter item 8)

**What the room does.** When something looks wrong, the status screen says exactly what
the engine decided and why — a live veto becomes one sentence, not a bug hunt.

**Exact rules (decided).** Per track at load, one log line:
`engine=v2 zone=<zone> colors=<hue-slot,depth> corrected=<bool> move=<squeeze|fuse|swell>`
— zone misfires become precisely reportable. Per drop at classification:
`family=<F> reason="<plain text>" tier=<1|2|3> rung=<r>` plus the darkness decision:
`dark=<kind> gap=<n> window=[a,b) abort_at=<beat|-> reason="<plain text>"` (§4's
decisions already carry reasons). Live: mode (WILD/SET), per-feature kill states, blend
scalar, active texture class + why, transport-suspend state. LED Pad gains the
"now playing identity" chip (authority §14). Everything is read-side and cheap; the
dry-run audit (§13) prints the same fields, so audit lines and runtime lines stay
comparable by construction.

---

## 13. The library-wide dry-run audit (charter item 9 — ran this session, read-only)

**What the room does (for Brandon).** Before anything gets built, the whole decision
pipeline above already ran over your entire analyzed library — 666 tracks, 3,936 drops —
as pure math over the cached analysis. Every track got a zone; every drop got a family, a
tier, and a darkness decision; every build got a white share; every quiet stretch got its
simmer read. The strangest tracks are ranked below so your ear goes where the data is
weirdest, not to random samples.

**Method (confirmed, reproducible).** Read-only scripts in the session scratchpad:
stage 1 enumerated tracks exactly like `tools/spectral_sweep.py` (same DB fields, same
`read_anlz_drops`, same `get_cached_v4`) and extracted per-track decision records through
the shipped `spectral_profile` code paths; stage 2 applied §2–§5's rules exactly as
written above (same constants); stage 3 ranked outliers. Coverage: 686 on-disk tracks →
**666 with v4 entries (100% of the shipped cache)**, 19 `no_grid` FX one-shots, 1 corrupt
file (GRiZ — known) — matching the sweep's counts exactly. Wall-clock ~90 s for stage 1,
seconds per rule pass. Post-build, the same audit re-runs through the real engine code as
the regression tool — the constants and formulas in this document are the spec for it.

**Headline distributions (confirmed):**

- **Zones:** GLACIER 119 / DEEP_POOL 133 / TWILIGHT 81 / ION 125 / VOLT 125 /
  EMBERCORE 83 — six zones at 12–20% each; aggressive-half max share **37%** (≤ ~40%
  criterion); every track assigned.
- **Drop families:** HOUSE 1628 / WALL 812 / COMET 439 / NEUTRAL 1057 (a 27% safety
  net). Genre lens (the classifier never sees genres): HARD TECHNO → 74% COMET;
  DUBSTEP/ISOXO/TRAPSTEP → 41–45% WALL; every house playlist → 50–65% HOUSE.
- **Tiers:** T1 2159 / T2 1176 / T3 601 (frozen p55/p85 cuts). DROP EM spans T1–T2 ✅.
- **Darkness:** 1,320 blackouts (dark beats spread 1→16; 219 at the 16 cap), 1,145
  relative dips, 1,366 snap flicks, 105 perc-cut flicks, 150 floor-return aborts. Every
  drop decided.
- **Builds:** white share masses at 0.2–0.4 with a long tail — 85 builds ≥ 0.6, 9 ≥ 0.9.
- **Texture / sections:** 236 tracks carry simmer sections; 572 have euphoric-eligible
  runs; drop rungs 1.0×2159 / 0.5×1775 / 0.25×2.
- **Charter criterion 7 ✅:** no cached track lacks a defined outcome at any decision
  point (zone; family — neutral counts; darkness — snap flick counts; texture — none
  counts; section/rung; build white share). Six tracks have zero drop markers: they never
  fire drop machinery — defined absence.

**The ranked outlier scrub list (confirmed): 330 tracks flagged; the top 48 (score ≥ 3)
are the recommended ear-check set.** Top 15 by weirdness:

| # | Track | Zone | Why it's weird |
|---|---|---|---|
| 1 | Odd Mob, OMNOM, HYPERBEAM — System | TWILIGHT | ALL 10 drops NEUTRAL; a 94-beat sub-only pre-drop run; 10 markers |
| 2 | Ray Volpe — Laserbeam (Carlo Kalu Edit) | DEEP_POOL | all 3 drops NEUTRAL; 12 dip runs (the known riser-only oddball reads exactly this way) |
| 3 | Jay Lumen — Bang To The Beat | DEEP_POOL | all 11 drops NEUTRAL; marker spam |
| 4 | Ye/JAY-Z x Osamason x ISOxo edit | ION | all drops NEUTRAL; 14 dip runs |
| 5 | fukumean (Crankdat Remix) | TWILIGHT | all drops NEUTRAL; sits on the aggression boundary |
| 6 | Drake & Sexxy Redd x Viperactive — Sticky | VOLT | all drops NEUTRAL; dip storm |
| 7 | Borne — Can I | EMBERCORE | all drops NEUTRAL; 15 dip runs |
| 8 | Odd Mob — XTC | DEEP_POOL | all 9 drops NEUTRAL; a 63-beat pre-drop run |
| 9 | Anti Up — Maximum | DEEP_POOL | all 8 drops NEUTRAL; a 60-beat run |
| 10 | Lobsta B — UP TO NO GOOD | VOLT | all 6 drops NEUTRAL; 15 dip runs |
| 11 | Fuckin' Problems x Type Shit | ION | all drops NEUTRAL; BPM 175 |
| 12 | Rae Sremmurd x Knock2 x 4B — No Type (BENZI) | VOLT | single NEUTRAL drop; BPM 72 (half-time grid) |
| 13 | Kesha x FTP x Twinsick — Die Young | GLACIER | single NEUTRAL drop; 13 dip runs |
| 14 | EYES CUT DEEPER (VIRX REMIX) | GLACIER | all drops NEUTRAL; 15 dip runs |
| 15 | BLACKPINK — JUMP (JAY ESKAR REMIX) | DEEP_POOL | ALL 15 drops NEUTRAL; 15 markers |

The tail pattern is itself a finding: all-NEUTRAL tracks are overwhelmingly mashups/edits
with unusual masters or marker spam — exactly where a neutral, identity-painted drop is
the safe right answer, and exactly where the ear should confirm. (Full 330-row list with
per-track reasons: `audit_out/outliers.json` in the session scratchpad; the audit re-runs
from this document's constants at any time.)

---

## 14. Walkthrough coverage map (charter criterion 1 — zero unmapped lines)

Every behavior in the strict review's §3 one-line list, mapped. Trigger "marker" =
Rekordbox ANLZ marker; rank = arbiter rank (§6); switch per §7.

| Walkthrough behavior | Cue/behavior | Trigger | Inputs | Switch | Rank |
|---|---|---|---|---|---|
| Groove chase in track colors | groove shapes (§10) in zone colors | role schedule | zone, hash, motion style | F1 | base look |
| Buildup hue shift on "lows out" | buildup-cue hue shift | buildup marker | sub-only floor signal (§4.1-1) | F2 | inside build look |
| White share scales with build intensity | buildup-cue slot-5 weight | buildup marker | §5.2 formula | F2 | — |
| 1-beat pre-drop cut on percussive cut | perc-cut flick / pre-drop dip | drop-marker context | §4.1-5/6 | F2 | 1 |
| Growl-vs-driving alternation in drop | drop-cue variant seasoning | drop marker fires the cue | bass-forward pattern (§5.1) | F4 (selection) | inside 1 |
| 3rd-chorus softness | **not promised** (§5.7) | — | measured indistinguishable | — | — |
| Breakdown "lows cut, drums persist" | busy-build refusal → build/groove cues ride | markers | §4.1-3 bass duty | F2 | — |
| Implosion build "sparse and dim" | simmer floor + dips | section + dip rule | §5.4 + §5.6 | F4/F2 | 7 / 1 |
| Room blackout before CSN 2:42.5 | capped 16-beat blackout | drop marker 352 | §4.1-2/4 (run 99 → 16) | F2 | 1 |
| 4-beat full-strobe drop; growl ranked more intense | WALL cue, tier profile; ranking **cut** | drop marker | §3 family+tier; §5.7 | F2 | 1 |
| Twinkle/simmer atmospheric intro | simmer floor | quiet section | §5.4 medians | F4 | 7 |
| Hidden-energy ramp | buildup cues + §5.2 | buildup marker | full_db step (prior fact: 9→15 dB) | F2 | — |
| Blackout→explosion at STARsound 0:52.9 | 2-beat relative-dip cut into the drop | drop-marker context | §4.1-5 (score 8.4 at 128–129) | F2 | 1 |
| Bright cyan/white sustain sections | euphoric flavoring | scheduled look | §5.5 eligibility | F4 (selection) | 7 |
| Lights-cut dips (2:12.4 / 2:16.5) | standalone relative dips | dip rule | §4.1-5 / §5.6 | F2 | 1 (short claim) |
| Swordfish chase at 0.5-beat rate | drop cue at rung 0.5 | drop marker | tier→rung (§5.3) | F2 | 1 |

---

## 15. Corrections, proposed amendments, and veto-shaped items (never silently applied)

### 15.1 Correction (confirmed): the strict review's STARsound rows measured a sibling file

Two independent signatures prove it: (a) T2-9's anchor axes (brightness_med 1059, drama
14.2, punch .85) match **"stargirl interlude starsound"** exactly; the walkthrough track
**"kohta x Bafu — STARsound (pt3)"** measures 671.3 / 9.2 / 0.851 (this session).
(b) S-1's STARsound row (gap at beats 126–127 before the drop) matches the stargirl
file's data — it has precisely a 2-beat sub-only gap at 126–127 before its own drop at
128; the (pt3) file's beats 126–127 read sub 24.2/28.3 dB (floor fully present).
Consequences absorbed here: the zone map calibrates on the correct (pt3) file and still
reproduces the anchor call (§2.2); the (pt3) 0:52.9 blackout reproduces as a relative dip
(§4.2). **Proposed amendment** to `lighting_engine_v2_strict_review.md` (T2-9 + the S-1
STARsound row) and to the authority doc §3's "twice as bright, far punchier, and more
dramatic" sentence: correct to the (pt3) numbers (brighter ×1.29, far punchier .85 vs
.51, drama ~equal 9.2 vs 8.7 — the separation carries on punch + luminance, not drama).
Not applied by me — records stay untouched per the charter.

### 15.2 Proposed amendment: CSN 352 acceptance figure

Authority §4.1 acceptance names "Can't Say Nah (26 → capped 16 at drop 352)". Under the
final sub-only floor rule the run measures **99 beats** (the AND-rule read 26); both cap
to the identical 16-beat window [336,352). Proposed wording: "99 sub-only (26 under the
AND-rule) → capped 16".

### 15.3 Proposed amendment: STARsound acceptance line

Authority §4.1 acceptance names "STARsound (2 beats at 131 with the abort)". From the
current cache the 2 dark beats at 128–129 come from the **relative-dip class** (a
full-band duck with the sub tail ringing above the gone threshold; §4.2), and darkness
still ends before the marker — the same protective outcome. The floor-return abort stays
a required mechanism (OLC-B confirmed) and demonstrably fires at 150 drops corpus-wide.
Proposed wording: "STARsound (pt3): a 2-beat relative-dip cut at beats 128–129 ending
before the marker; the floor-return abort demonstrated corpus-wide (e.g. crank the bass
drop 96: gap 4, abort at 95)".

### 15.4 Veto-shaped design calls (defaults chosen; say the word to flip any)

1. **Hard techno wears dark zones** (mostly DEEP_POOL/TWILIGHT), with red arriving
   through the COMET drop cue rather than the identity — keeps true red rare and earned.
   Veto shape: "hard techno should read red all night" → one aggression-side re-split by
   BPM.
2. **NEUTRAL drop share ~27%.** Ties land invisible by design (F-11). Veto shape: "too
   many plain drops" → loosen §3.1 gates; the outlier list shows exactly which tracks
   move.
3. **The busy-build rule (§4.1-3) can refuse a blackout your ear wants.** Calibrated so
   CSN's builds never black out while ILL's and CUT TF UP's gaps do. Veto shape: name a
   track+drop where you wanted black and didn't get it — the 0.85 duty threshold is one
   constant.
4. **The quarter-beat rung is nearly extinct at your BPMs** (2 drops) — tier-3 aggression
   at 140+ BPM rides 0.5-beat + intensity + micro-darkness instead (30 fps physics, F-6).
   Not a veto item; noted so the live pass isn't surprised.
5. **SET-mode peak reservation keys on tier 3 only** (§3.3). Veto shape: "peak-time
   should be rarer/looser" → the tier-3 cut is one constant.

### 15.5 Analysis gaps never promised (§6.3 restated as a hard boundary)

Chorus softness; growl-intensity ranking; slow/formant wobble (the deferred
centroid-series extension stays deferred); the two Appendix-F class limitations
(sidechained kick-prominence, thick-wall sustained-synth — scrub-gated, not retuned
here); busy-pulse breadth (seasoning only). Nothing in §2–§12 reads any of them.

---

## 16. Provenance and claim labels

- **Decision sources:** `lighting_engine_v2_authority.md` (operator contract),
  `lighting_engine_v2_strict_review.md` (charter §6; S-1..S-7; T2-1..T2-11; OLC-A..C),
  `lighting_engine_v2_design_review.md` (rulings 1.1–5.20, F-1..F-17, P-2..P-5 as
  amended), `spectral_palettes_arrival_crossfade_exploration.md` (locked agreement +
  addenda 1–21 + corrections; superseded passages marked in place),
  `spectral_audio_analysis_redesign.md` (v4 layer; Appendices A–G operator ground truth,
  S-4 corrections applied). Research rounds 1–4: **lore only** — every number imported
  from them is TUNE-LIVE with no citation; the two known-fabricated safety citations are
  not imported.
- **Measured this session (confirmed):** all §13 audit numbers; the §4.2 acceptance
  table; §2.2 zone distributions and anchor placements; per-beat values quoted for
  ILL / CSN / STARsound (pt3) / stargirl / DROP EM / crank the bass; the corpus
  normalization anchors and frozen splits; the renderer and laser inventories
  (subagent-gathered, line-cited). Method: read-only scripts over the shipped v4 cache
  (666 entries), the Rekordbox DB (opened exactly as `filepath_resolver.py` does), and
  current ANLZ markers via `read_anlz_drops`, through the shipped
  `spectral_profile`/`spectral_cache` code paths.
- **Named prior facts (not re-derived):** identity-axes corpus stability
  (.929/.935/.967/.928, n=219); held-out genre discrimination 58.7% vs 16.7%; the
  sub<5 dB corpus valley; cache 666 entries / 203.5 MB; LUNCH pulse timestamps; CSN
  drop@128 swing 9.2 dB (reproduced exactly this session); DROP EM attack span
  2.7→16.1 dB (reproduced exactly this session).
- **Decided (this document's delegated design authority):** the zone set, splits, and
  palette families; family gates; tier cuts and profile knobs; the busy-build
  discriminator; the dip score; the perc-cut flick; move selection; arbiter windows;
  kill-matrix rows; slot semantics; the template menu; the laser zone→personality map.
  Each carries its reason in place.
- **Live-gated:** every perceptual claim (what reads bright/violent/comfortable), all
  TUNE-LIVE constants, seasoning densities, palette RGB ramps, beam looks. Brandon's
  eyes are the acceptance gate — software tests are build gates only.
- **Unknown (inherited, unchanged):** fader physical smoothness (the one recorded
  practice session, F3), Govee device latency, the Rekordbox 7.2.11 mixer-offset pin,
  DB-rebuild content-id stability (filepath fallback pinned).
- **Status:** everything here is design intent — `planned`. The audit is read-only
  measurement. Nothing is implemented, and nothing above claims otherwise.

**Road from here** (authority §15): this document → the laser hardware-catalog session
(fills §11's TBD slots) → Codex specs Feature 1 → 2 → 3 (texture rides 1/2), each with
tests, contracts, kill switches; Codex implements; Brandon gates live.

