---
doc_status: current
truth_level: code-verified + measured-corpus
last_verified_commit: c39bfa3
last_verified_date: 2026-07-04
validation_scope: software-exploration only — code reading at HEAD plus read-only measurements of the local spectral cache, Rekordbox DB, and ANLZ files; no hardware validation, no runtime behavior change, no bridge execution
---

# Spectral Palettes, Land on the One, Mix-Aware Crossfade — Exploration & Verdicts

Fable 5 exploration (2026-07-04) for three crowd-experience workstreams. Every load-bearing
claim is labeled **confirmed / assumed / unknown / rejected** and tied to a file:line at commit
`c39bfa3` or to a measurement run described below. Measurement scripts were run read-only from
the session scratchpad against: the spectral cache (488 files, 43 MB, at
`~/Library/Application Support/RBSS Bridge/spectral_cache/`), the Rekordbox DB
(`~/Library/Pioneer/rekordbox/master.db`, opened exactly as `filepath_resolver.py:331` does),
and sampled ANLZ files under `~/Library/Pioneer/rekordbox/share/`.

---

## Verdicts

| Workstream | Verdict |
|---|---|
| **A — spectral → per-track palettes** | **GO** — coverage, stability, and discrimination all measured and sufficient; one honest constraint on *which* axes the cached data can express (details below) |
| **B — Land on the One (arrival choreography)** | **GO** — every primitive already exists; the change is pure math in an already-safe thread structure |
| **C — track identity + mix-aware crossfade** | **GO WITH CONSTRAINTS** — identity inherits A's GO in full; the fader signal is real but deck-1/2-only, version-pinned to Rekordbox 7.2.11, and its physical smoothness is unmeasured until one recorded blend session exists |

**C's dependency on A, explicitly:** A landed GO with its full spectral tier, so identity quality
does not degrade to the ANLZ-only floor. Everything in C that consumes identity (palette-space
interpolation, harmonic-vs-clash reads) is licensed by A's numbers. The parts of C that would
survive even if A had failed (fader mechanics, hard cuts) were assessed independently and stand
on their own.

**Brandon's trust-bar hypothesis: confirmed by data.** The same features that were rightly
distrusted for smart-drop *timing* are strong for *identity*, and the reason is structural:
timing needed per-beat, per-event precision; palette derivation integrates over the whole track
(median 514 beats per track in the cache). Whole-track summaries are stable at Spearman
0.86–0.96 across resampling, while individual-event placement was never that reliable. Lower
trust bar, and the data clears it.

---

## Locked functionality agreement — LIGHTING ENGINE v2 (operator sessions, 2026-07-05)

Settled with Brandon across two sessions (structured Q&A, then a step-by-step plain-language
walkthrough — the walkthrough's revisions are what stand wherever they differ). **Governance:
design authority is delegated — Claude designs everything; Brandon's approval gate is the live
look on his own hardware.** No further design questions go to Brandon. This supersedes the
report's "Open questions for Brandon" section.

**Packaging (operator-named):**
- The full A+B+C bundle ships as **LIGHTING ENGINE v2**. Today's behavior is
  **LIGHTING ENGINE v1** — frozen, untouched.
- v1 and v2 coexist in the bridge; **one master switch, exactly one engine active at a time**,
  switchable live mid-set. v2 off ⇒ behavior identical to today's, byte for byte.
- Every v2 feature additionally has its **own independent runtime kill switch**.
- Per-feature status is **not "done" until Brandon signs off on the live look**;
  software-tested is a build gate, not an acceptance gate.

**Feature 1 — track identity (colors):**
1. **REVISED hue driver** (supersedes the key→family design and the round-1 Q&A answer;
   operator veto: "I don't want every 2a track to be blue"): **sound character picks the color
   zone** — grit (flatness), punch (kick_cv), bass (sub_duty), drama (dyn_range); aggressive →
   warm zones, smooth/melodic → cool zones — and a **deterministic per-track hash spreads
   tracks within their zone**, so no two tracks need match and **no key owns a color**. Musical
   key is out of the color story entirely.
2. Identity is **permanent across nights**: a pure function of the track's identity + measured
   character. No RNG, no session seed, no deck salt.
3. **Zones pick colors, never power.** Brightness and white usage are owned by in-the-moment
   energy and role; **drops always render full-scale**, every track, every zone.
4. Depth axis = saturation floor + gradient span only.
5. Until Feature 3 exists, track handover = **soft flip** (4–8 beat p-space fade at
   active-deck flip).
6. First-play-of-the-night reveal: **in, with a hold gate** (~8 beats held active before the
   2-bar bloom can fire).
7. Late-drop palette surprise **stays inside the track's own colors**.
8. Track character drives **motion style** (punchy → sharp attacks; smooth → flowing).
9. Long single-zone stretches are **a feature** — the room follows the set's shape.
10. Unmeasurable tracks land in a neutral-safe zone; a simple per-track operator correction
    path must exist (the live-veto counterpart for zone misfires).

**Feature 2 — Land on the One:**
1. Build list: **landing behavior as infrastructure** (existing moves land on the beat instead
   of starting after it) plus the build-move family: **squeeze-explode**, **fuse** (cascade),
   **swell** (phrase). All in.
2. **The track's character picks its build move and its body language** (sharp stabs vs smooth
   glide), per-track consistent — the build becomes part of the track's identity.
3. Fires at **every true drop — multiple per song** — never on a bare 16/32-bar cycle.
4. **Tempo bending never causes a skip.** Per-frame retargeting follows the ridden pitch
   continuously (operator: "the bridge is very sound — no unsureness"). The earlier
   confidence-skip is reframed: **recalculate on backward playhead jumps only**
   (spinback/scratch/seek) — the move re-forms if the drop is still ahead, melts away if the
   jump passed it. It recalculates; it never wonders.
5. LED-first; lasers join later via the established pre-arm pattern.

**Feature 3 — mix-aware crossfade:**
1. **The fader is the boss.** Takeover speed always mirrors actual fader motion — the lights
   never take longer than the operator's hands did.
2. Incoming color enters **rhythmically, accents-first** (bar-quantized presence steps), then
   takes the base.
3. Near colors **glide**; opposite colors **trade ownership hit-by-hit, then commit** — never a
   muddy mid-hue.
4. Quick blend = compressed walk-in; **slam = instant snap; chops = the room chops along.**
5. Abandoned blend **breathes back out** (monotonic-with-hysteresis, no flicker; no completion
   moment fired).
6. **Double-drop moment: CUT** (operator: "i dont do double drops"). One song owns the room,
   no exceptions.
7. Deck 1/2 only; the Rekordbox 7.2.11 offset pin is an accepted operating constraint
   (degrades silently to a time-based proxy elsewhere).
8. Fader smoothing/hysteresis constants get tuned from one `RBSS_RECORD_SESSION` practice
   capture during the build — a build task, not an operator decision.

**Next step:** author the Codex implementation specs (Feature 1 → 2 → 3) per
`.claude/skills/codex-spec/SKILL.md`, on Brandon's go.

---

## Workstream A — spectral features → per-track palettes: GO

### A1. What was measured (all numbers from this session's read-only sweep)

**Coverage — confirmed by measurement:**
- Cache: 488 files → 487 readable at schema v3, **476 distinct tracks**, 454 of them "fresh"
  (audio file still exists with matching mtime+size, the staleness rule at
  `spectral_cache.py:175-192`). 11 tracks have two entries (re-analyzed grids); worst case 2.
- Rekordbox DB: 2,165 content rows, **1,007 active** (non-deleted), 686 with the audio file
  present on disk. **455 of the 476 cached tracks join to active DB rows** — 45.2% of the
  active library, **66.3% of the on-disk library**.
- The cache fills at track load whenever the spectral shadow flags are on
  (`state_manager.py:2004-2016`), so coverage is concentrated on tracks actually played and
  grows with every session. For the catalog Brandon performs from, effective coverage is high.
- Beats per track: min 105 / median 514 / max 1,176.

**Stability — confirmed by measurement:**
- *Measurement noise (even-beats vs odd-beats summaries, 476 tracks):* Spearman 0.86–0.96 on
  the retained scalars; tercile "character hold" 73–86%. Best: sub-bass variability 0.957,
  sub-bass duty 0.929, dynamics range 0.925, spectral flatness 0.922, kick variability 0.902.
  One candidate failed this gate: onset-strength variability (0.767 / 64.5% hold) — **rejected
  as an axis**.
- *Re-extraction determinism:* re-running `extract_spectral_features` twice on 3 cached tracks
  produced **bit-identical** envelopes run-vs-run and **bit-identical values vs the cache
  written on an earlier date** (max abs diff 0.0 on all 8 envelopes × 3 tracks). Same track
  always summarizes the same. (The beatgrid *fingerprint* I reconstructed from ANLZ differed in
  byte representation, so the cache-key check was bypassed and envelope values compared
  directly; the envelope identity is the load-bearing fact.)
- *Within-track homogeneity (first half vs second half):* much weaker, Spearman 0.34–0.74. This
  is the music being real (breakdowns differ from drops), not noise — and it dictates a design
  rule: **derive identity once from the full track, never re-derive per section.**

**Discrimination — confirmed by measurement:** the catalog spreads instead of clumping.
Interquartile-range/median across tracks: flatness 0.51, kick duty 0.48, kick variability 0.42,
sub duty 0.40, dynamics range 0.34. Histograms are single-humped with wide usable tails — no
degenerate two-cluster or all-same collapse. Pairwise correlations leave 3–4 genuinely
independent axes (the largest between retained axes from different groups is |ρ| ≈ 0.6 between
the two kick measures, which are deliberately complementary).

**The one honest constraint — confirmed at `audio_spectral_features.py:148-150,197-201`:** every
band envelope is **peak-normalized against its own maximum** before caching. Cross-band loudness
is destroyed: the cache cannot say "this track has more bass than treble." A literal
warm↔cool-from-bass-balance axis is **rejected** for the current cache schema. What survives —
and what the measured axes above actually are — is *shape and texture*: how sustained, how
spiky, how dynamic each band is, plus spectral flatness, which is stored **unnormalized**
(`audio_spectral_features.py:117-123`) and is therefore the one absolute, cross-track-comparable
spectrum measure. If Brandon ever wants true tonal-balance axes, that is a schema-v4 extension
(store per-band absolute means before normalizing) — a cheap rider, but it re-extracts the
corpus; the design below does not need it.

**Supporting signals:**
- **Musical key: available and universal — confirmed by measurement.** The bridge's own DB layer
  (`pyrekordbox.db6.Rekordbox6Database`, the exact API used at `filepath_resolver.py:281-283`)
  exposes `DjmdContent.Key.ScaleName`, already in Camelot form ("2A", "7A", "4B"…).
  **100% of the 1,007 active tracks have a key**, spread across the whole wheel (top: 2A×125,
  4A×111, 7A×105…). Key→hue is fully licensed, including for workstream C's harmonic reads.
- **ANLZ mood/structure: near-universal but low-contrast — confirmed by measurement.** Of a
  300-track random sample, 293 parsed with a PSSI tag (97.7%). But mood is heavily skewed:
  92.5% mood=1 ("high"), 6.8% mood=2, 0.7% mood=3. **Mood alone is a weak identity axis**
  (nearly constant); its real value is structural — drop counts (mean 6.6/track, only 1/293
  with zero) and the per-event intensity classes in `energy_model.py:143-213`
  (drop-lift/breakdown-depth/buildup-slope with fixed thresholds at `:17-29`).
- **librosa: installed locally (0.11.0, Python 3.14.6) — confirmed.** Still optional by design
  (`audio_spectral_features.py:29-41` returns None without it), so the ANLZ tier below must and
  does stand alone.

### A2. Settled code questions

- **(a) Is `_journey_rng` seeded per-track? No — confirmed.** It is seeded once per *session*
  from `set_seed` (`led_color_engine.py:266-281`), and the live config uses
  `set_seed_mode: "random"` (verified in `config/led_look_director.json`; parse default
  `led_config.py:1135`). Palette choice is a session journey — dwell countdown then weighted
  re-pick (`led_color_engine.py:386-396`, `_pick_palette` at `:863-878`), plus a drop-snap
  re-pick (`:404-426`). So same-track-same-palette consistency does **not** exist today.
  What half-exists is the *seam*: a per-track deterministic seed is already computed at new-track
  detection — `_current_track_seed = blake2b(f"{set_seed}:{active_deck}:{content_id or filepath}")`
  (`led_color_engine.py:362-373`) — but it only drives the within-palette focus window, and it is
  salted with the random session seed and the deck number, so it is not stable across nights or
  decks. The derivation below replaces the palette *pick* with a pure function keyed on content
  identity only.
- **(b) Is musical key reachable? Yes — confirmed** (measured above, via the DB layer the bridge
  already ships).
- **Hook point / push-loop safety — confirmed.** Track resolve already spawns a daemon worker
  thread per load (`state_manager.py:1781-1814`) which, when spectral is enabled, reads the
  cache / extracts / writes it (`:241-250`) and posts results back as an `ANLZ_DATA` event.
  Identity derivation is a pure function of data that worker already holds (features + key +
  content id), so it runs there — file I/O and librosa stay off the 200 Hz push loop, which
  today only does the cheap in-memory journey math via `begin_dispatch`
  (`led_dispatch_policy.py:735-749`). Same pattern, no new threading.
- **Enable-flag coupling — confirmed, needs one decision.** Extraction currently only happens
  when `RBSS_SMART_REARM_EXPERIMENT=1` **and** `RBSS_SPECTRAL_ENABLE=1`
  (`state_manager.py:566-569`; cache eviction likewise, `__main__.py:888-901`). Palette
  derivation should get its own trigger (or an `or`-condition) so track identity does not ride
  on smart-rearm experiment flags. Design decision for the Codex spec, not a blocker.

### A3. Creative design — the track identity system

**The premise the crowd feels:** *every track wears its own light, and wears it every time.*
Recurring tracks become recognizable; the room learns them.

**Four identity dimensions, each from a measured axis (spectral tier):**

1. **Hue family — "who the track is."** Musical key → Camelot wheel position → one of the
   curated palette families below. Camelot is circular and so is hue: adjacent keys land in
   adjacent families, which is what makes harmonic mixing *look* harmonious in workstream C.
   Minor/major (A/B suffix) modulates within the family: minor = deeper, more saturated end of
   the family's range; major = brighter end with more white headroom.
2. **Texture — "how it moves."** Kick variability (kick_cv, stability 0.902): punchy tracks
   (high) get sharp-attack accent behavior — hard onsets, short decays, strobe-adjacent pulses
   where discipline allows; smooth/rolling tracks (low) get flowing sweeps and washes. This
   plugs into animation parameter selection, not palette choice.
3. **Depth — "how it sits."** Sub-bass duty (0.929): rolling, sustained sub → narrow, deep,
   saturated gradient span with little white; sparse/absent sub → wider gradient span, brighter,
   white as an active ingredient.
4. **Dynamics budget — "how far it travels."** Dynamics range (0.925): a big-arc melodic track
   earns large excursions between its breakdown look and its drop look; a flat techno tool stays
   in a tight lane. **The intensity dimension Brandon asked about is exactly this**: intensity
   moves with the track's arc through the existing role system
   (ambient/groove/buildup/drop/post_drop/breakdown), scaled by the track's own dynamics budget,
   while the hue identity holds. The track stays *itself* across its whole arc — the identity is
   the color and texture; the energy arc is how loudly the identity speaks.

Spectral flatness (0.922) acts as a modifier on texture: high-flatness (noisy, distorted,
peak-time) pushes toward aggressive accent policies; low (clean, tonal, melodic) pushes toward
smooth ones.

**Tiered fallback (same track → same palette at every tier):**
- **Tier 1 — spectral fingerprint:** all four dimensions + key hue. Pure function of
  (content_id, cached summary scalars, key). No RNG anywhere.
- **Tier 2 — ANLZ-only (librosa absent or cache miss):** key hue (100% coverage) + structure:
  drop count and `energy_model` intensity classes give a coarse dynamics budget; mood nudges
  texture (weakly — measured 92.5% mood=1, so this tier's texture is mostly neutral). Identity
  quality here: hue family and dynamics remain solid; texture flattens toward default. Since key
  is universal, tier 2 is only visibly weaker on texture — "recurring tracks look like
  themselves" survives intact because hue is the recognition carrier.
- **Tier 3 — deterministic hash (no key, no ANLZ):** `blake2b(content_id or filepath)` → family.
  Arbitrary but permanent; a weird untagged track gets a consistent, safe-neutral identity.
- Failure of everything → today's journey behavior (which remains as the "no identity" mode).

**Generalization gate:** all inputs are per-track offline data or backbone signals; zero
per-track authoring; every tier degrades to a safe-neutral default; hue mapping is a fixed
function, not tuning. Clears the gate at every tier.

**The palette family library the curated config needs.** Today's library (live config,
verified) is 5 weighted families — blue_cyan 10, indigo 6, deep_ocean 4, violet 3, crimson 2 —
all cool-side, plus zero-weight white_sand and rainbow utilities. The default color line only
has six stops, green→cyan→blue→purple→magenta→red (`led_models.py:72-79`): **there is no warm
sector — orange/amber/gold do not exist in the scale.** Key→hue needs the full wheel. Proposed
family board (~10, each with its feel, for Brandon to react to):

| Family | Range (stops) | Feel | Camelot neighborhood |
|---|---|---|---|
| Glacier | cyan→blue | clean, icy, driving | 12A/12B–1A/1B |
| Ocean | green→blue | deep, rolling, hypnotic | 11A/11B |
| Emerald | green→teal | lush, organic, springy | 10A/10B |
| Indigo | blue→purple | nocturnal, heads-down | 2A/2B |
| Ultraviolet | purple→magenta | dark euphoria | 3A/3B |
| Fuchsia | magenta→pink | playful, vocal, cheeky | 4A/4B |
| Crimson | magenta→red | aggressive, peak-time | 5A/5B |
| Ember | red→orange *(new stops)* | warm grit, late-night | 6A/6B–7A/7B |
| Gold | orange→amber *(new stops)* | anthem warmth, hands-up | 8A/8B |
| Solar | amber→yellow-green *(new stops)* | daylight, festival | 9A/9B |

Adding Ember/Gold/Solar means extending `scale_stops` with orange/amber/yellow entries — the
existing machinery supports arbitrary stops (`led_color_engine.py:57-90`); this is config plus
palette rows, not engine surgery. Camelot assignments above are illustrative; the fixed rule is
*adjacency preservation*, and the exact rotation (which key anchors which family) is a taste
call listed for Brandon.

**The identity reveal (first play of the night).** Worth having, kept humble: the first time a
given content_id becomes the audible track tonight, the strip does a single 2-bar "bloom" —
base hue emerges from the current ambient and widens into the track's full gradient. It is one
generic animation parameterized by identity (no per-track authoring), it reuses the new-track
detection seam that already exists (`led_color_engine.py:364`), and on every later play of the
same track it simply doesn't fire. Listed as a taste call — the system is complete without it.

---

## Workstream B — Land on the One: GO

### B1. Evidence: what exists and what drifts

- **The drift is real and located — confirmed.** Every animation instance freezes BPM at spawn:
  `local_beat = (now − born_monotonic) × born_bpm/60` (`beat_sync_engine.py:190-201`,
  `born_bpm` at `:26`). Ride the pitch fader mid-flight and the motion falls off the beat.
- **Why it was built that way — confirmed and must be preserved.** The engine's own header says
  it: instances run on wall-time so they are *immune to Rekordbox loop wraps* — `abs_beat_pos`
  jumping backward (`beat_sync_engine.py:1-6`). The wrap detector exists in `TriggerClock.advance`
  (`:50-68`, backward jump → `wrapped=True`, forward jumps capped by `MAX_CATCHUP`).
- **Live retargeting data already arrives every frame — confirmed.** The Govee realtime runner
  (own thread, default 30 fps, `govee_realtime_runner.py:53,207-219`) calls a provider *every
  tick* and gets a fresh `BeatAnchor` (deck, abs_beat_pos, bpm, captured_monotonic, playing —
  `led_models.py:244-251`), built by `get_active_beat_anchor`
  (`led_dispatch_policy.py:259-273`) from `_led_rt_beat`, which the 200 Hz push loop refreshes
  with the *live* BPM and a monotonic-clamped playhead every tick (`state_manager.py:3546-3555`).
  The runner already extrapolates current beat position from it
  (`govee_frame_renderer` consumers via `govee_realtime_runner.py:277-280`). **Only the
  per-instance frozen `born_bpm` is stale; the pipe for live beat/BPM is already there.**
- **The future-beat primitive — confirmed.** `beat_math.py:51-68` maps an absolute beat to
  elapsed ms (grid, then grid-extrapolated), and the autoloop controller already pre-arms with
  it (`autoloop_controller.py:397-417`). Note: the *LED* side doesn't even need the ms mapping —
  the runner lives in beat-space already; beat_math matters when lasers join later.
- **Reset machinery — confirmed.** Deck change / track change / backward playhead jump all
  reset smart phrasing (`smart_phrasing.py:206-214`); pause parks LEDs in designed idle-ambient
  (`state_manager.py:3688-3693`) while the runner's `animate()` path lets in-flight instances
  finish and expire (`beat_sync_engine.py:159-166`).
- **Renderer phase math is modulo-based today — confirmed** (`govee_frame_renderer.py:262,342,
  399-405,429,511` etc. all phase via `beat % N`): triggered looks, not arriving ones.

### B2. The design: an arrival scheduler that is just arithmetic

**Where it lives: `BeatSyncEngine`, not the renderer.** The engine already owns instance
lifecycle, the runner already feeds it `(abs_pos, now, bpm)` per frame
(`govee_realtime_runner.py:319`); the renderer stays a pure function of instance renders. No new
threads, no I/O, no locks beyond the runner's existing one.

**How a motion is specified to arrive.** An instance gains an optional arrival contract:
`target_abs_beat` (chosen as the next boundary of a requested division: `ceil(abs_pos/N)×N` —
one line of pure math; N=4 for the bar, 16/32 for phrase scale) and `travel_beats`. Spawn at
`target − travel_beats` in beat-space.

**Per-frame retargeting (drift is expected behavior):** every frame, progress is recomputed from
the *live* extrapolated position: `progress = 1 − (target_abs_beat − abs_pos)/travel_beats`,
clamped to [0, 1+trail]. Because `abs_pos` is re-derived each frame from the freshest anchor
(which carries live BPM), riding the pitch retargets the motion automatically — there is nothing
to "update," the stale quantity simply stops being stored. BPM changes stretch or compress the
remaining flight so the landing stays pinned to the musical one.

**Fallback when the grid is broken or prediction unstable (invisible degrade):**
- Backward jump (loop wrap / seek): `TriggerClock` already flags it; arrival instances convert
  on that frame to today's wall-clock behavior (freeze `born_bpm` semantics) and finish
  gracefully, or expire if past target — never a negative-progress glitch. This *preserves* the
  wrap-immunity the engine was built for; beat-space is only trusted while time moves forward.
- Anchor invalid / not playing / BPM ≤ 0: `get_active_beat_anchor` already returns None
  (`led_dispatch_policy.py:261-265`) and the runner idles — arrivals pause with everything else.
- Prediction jitter: if the recomputed time-to-target changes by more than a threshold between
  frames (deck switch mid-flight, grid glitch), degrade that instance to trigger-on-beat. The
  crowd sees a normal triggered look; nobody sees a scheduler.
- No-grid tracks: the anchor's abs_beat_pos already comes from the BPM-extrapolated fallback
  path; arrivals work identically, just with the same (acceptable) drift as everything else.

**Push-loop safety argument:** the scheduler adds zero work to the 200 Hz loop — the push loop
already publishes `_led_rt_beat`; all arrival math runs on the runner thread at 30 fps, and it
is arithmetic on floats already in hand. No blocking I/O, no new threads, no syscalls in the
render path.

**Which looks convert first — LED-first, and specifically comets/sweeps.** Rationale: the LED
runner already has the live anchor pipe and per-frame render; the laser path runs through
SoundSwitch pack playback and MIDI with its own latency model and no equivalent per-frame
retarget seam. Lasers join in a later phase via `beat_math`-scheduled pre-arms (the autoloop
pre-arm pattern at `autoloop_controller.py:397-417` is the template).

### B3. Creative expansion — the choreography vocabulary arrival unlocks

Trigger-on-beat gives flashes; arrival gives phrasing. The vocabulary, ranked by crowd impact
per unit of build:

1. **Landing comets/sweeps (engine capability — build first).** The entire existing comet/sweep
   library upgraded from "starts on the beat" to "*lands* on the one." Highest impact per line
   of code because it retrofits every current template; the room stops seeing effects that react
   and starts seeing effects that *know what's coming*.
2. **The Gather (template family — ship as the demonstration).** Over the last 4 beats before a
   bar-16/32 boundary, light contracts toward the strip center (or dims toward a single point),
   then releases outward exactly on the one. Anticipatory pull → release is the physical shape
   of tension → drop; pairs naturally with buildup roles the bridge already detects.
3. **Cascade-to-one (template family).** Strip segments ignite in sequence, each an arrival
   offset by one step, final segment landing on the downbeat — a fuse burning toward the one.
   Same primitive, staggered targets.
4. **Phrase-scale swells (template family, cheap).** 8-bar brightness/spread swell that
   *completes* at the phrase boundary instead of starting there — uses smart phrasing's grid,
   reads as the room breathing with the phrase.
5. **Call-and-response LED↔laser (engine capability, deferred).** LED states a figure in bar A;
   lasers answer in bar B resolving on the downbeat. Needs the laser-side scheduling seam —
   explicitly *not* in the first spec.

**Template Lab vs engine:** arrival scheduling itself = engine capability (new instance fields +
render math + spec params like `arrive_division`, `travel_beats`, `gather_shape`). Gather,
Cascade, and phrase swells = Template Lab families built on it. **The first Codex spec should
make #1 possible as infrastructure and ship #2 (and optionally #3) as the visible proof** — even
if other families come later through Template Lab.

---

## Workstream C — track identity + mix-aware crossfade: GO WITH CONSTRAINTS

**Condition on A, restated:** A = GO with the full spectral tier, so identity enters the blend
at full quality — hue family, texture, depth, dynamics all available. Nothing below silently
assumes spectral strength A didn't prove; where a claim rests on unmeasured physics (fader
smoothness), it is labeled unknown.

### C1. The fader signal, assessed on its own

- **What is read — confirmed.** Per-deck upfader raw + low-EQ raw for **decks 1 and 2 only**:
  the offset table defines exactly four mixer chains (`rb_offsets.py:180-183`, required label
  set `:196-201`), read per poll in `_tick_mixer` (`rb_state_reader.py:464-513`), normalized
  raw/1023 (upfader) and raw/255 (low EQ) into `MixerDeckReading` (`models.py:116-125`,
  `rb_state_reader.py:515-526`).
- **The crossfader itself: no offset exists — confirmed absent.** The required-label set is
  closed (exactly the four labels above; any other/missing label disables mixer authority,
  `rb_offsets.py:236-237`), and no crossfader chain appears anywhere in the table. Any blend
  progress must come from the **upfaders**, which matches how Brandon actually mixes on club
  mixers; a crossfader read would need new offset RE work — out of scope, not assumed.
- **Deck 3/4 fader coverage: none — confirmed** (same four-label evidence; additionally the
  resolver treats only raw decks 0/1 as resolver-capable when mixer authority is on,
  `rb_state_reader.py:461-462`). Blend visuals are a deck-1↔2 feature. Decks 3/4 fall back to
  the hard-cut grammar.
- **Update rate — confirmed:** the reader thread polls at `MEM_POLL_HZ // 2` = **30 Hz**
  (`rb_state_reader.py:134`, `config.py:60`). Ample for a visual morph (the LED runner renders
  at 30 fps).
- **Staleness — confirmed:** snapshots older than **1.0 s** are distrusted
  (`active_deck_resolver.py:12`, checked at `:75-76`); invalid/stale snapshots arrive as
  explicit reasoned events (`rb_state_reader.py:474-499`). The blend consumer inherits a clean
  degrade signal.
- **Current consumption is coarse labels only — confirmed:** down ≤ 0.02 / top ≥ 0.98 /
  "audible" between (`active_deck_resolver.py:7-8,45-50`), used for active-deck resolution
  (`:125-136`). The raw/norm values ride along unused — the blend scalar is new consumption of
  an existing signal, not a new reader.
- **Version pin — confirmed, new finding:** mixer chains exist **only in the 7.2.11 block** of
  the embedded offset table (`rb_offsets.py:108-111`; the 7.2.14/7.2.13/7.2.10/7.2.8 blocks have
  none). The installed Rekordbox is **7.2.11.0342** (app bundle Info.plist) — so the signal is
  live *today*, but a Rekordbox upgrade silently drops mixer authority (and with it blend
  visuals) until offsets are re-derived for the new version. The feature must degrade invisibly
  to the time-based proxy in that world — which the design below does by construction.
- **Smoothness of raw/norm during a physical fader ride — unknown.** No session recordings with
  `MIXER_STATE` events exist on disk (searched; the recorder is env-gated via
  `RBSS_RECORD_SESSION`, `session_recorder.py:18,71-75`, and does capture generic bridge
  events). The float read is fine-grained (0–1023) at 30 Hz, so the *prior* is smooth-enough,
  but whether the DDJ-800 reports continuous intermediate values or coarse steps is exactly the
  kind of physical fact this repo doesn't assert without data. **How to get it:** one ordinary
  practice session launched with `RBSS_RECORD_SESSION=<path>`, riding a few blends; the
  recording contains every `MIXER_STATE` snapshot for offline analysis. Until then the design
  mandates smoothing + hysteresis regardless (below), so the unknown gates *tuning constants*,
  not viability.

### C2. Data-model reality and the smallest honest shape

- **Single-deck LED context — confirmed:** `LEDContext` carries one `active_deck` and no second
  palette reference (`led_models.py:213-226`, constructed at `led_dispatch_policy.py:753-762`);
  nothing downstream blends across decks. The color engine likewise tracks one current palette.
- **Mixer data already reaches the runtime owner — confirmed:** `MIXER_STATE` events store the
  snapshot on StateManager and re-run the resolver (`state_manager.py:1137-1141`). The blend
  scalar can be computed where all authority context already lives.
- **Smallest honest shape of the change:** (1) StateManager derives `blend = f(upfader_norm of
  the non-active deck)` with smoothing/hysteresis, alongside the incoming deck's identity (from
  A) when that deck has a loaded track; (2) the LED context/frame-spec path gains *two* fields —
  `incoming_palette_ref` + `blend` (0..1); (3) color resolution interpolates in the color
  engine's existing 1-D p-space / palette-family space rather than raw RGB (the scale-stop line
  at `led_color_engine.py:57-90` makes palette-space interpolation natural and keeps every
  intermediate color inside the curated gamut). No second full context, no dual dispatch — one
  scalar and one reference threaded through an existing frozen dataclass.
- **Authority interactions (unchanged winners):** manual static override, blackout owners, and
  emergency blackout keep absolute priority — blend only modulates the automated palette path
  (`led_dispatch_policy.py:251-252` blackout gate; runner-side emergency teardown
  `govee_realtime_runner.py:322-324`; the standing Static-Override rules in AGENTS.md §6).
  Blend never overrides a held look; it colors what automation was already allowed to show.
- **Degraded paths:** mixer stale/invalid (or post-upgrade absent) → hold last blend briefly,
  then decay to the active deck's identity on the staleness timeout — visually a slightly
  earlier completion, never a flicker. Hard cut (fader slam, deck switch, instant swap) →
  **instant snap is correct** and is what the existing wrap/reset machinery already produces.

### C3. Creative expansion — the blend as a designed scene

The crossfade is the most-watched, least-lit moment in DJing. The grammar, for the three real
cases plus the special one:

- **Long blend (the designed scene).** The incoming identity enters **as accents first,
  rhythmically**: accent hits (offbeats, fills, comet spawns) start drawing from the incoming
  family while the base wash stays the outgoing identity — the new color gains "beats of
  presence" per bar as the smoothed blend scalar rises. Past a midpoint the base itself morphs
  in palette-space; when the blend crosses ~0.85 *and holds*, a one-bar **resolve** marks the
  handover (a single bloom in the new identity — the room registers "we're in the new track
  now"). Quantizing accent-presence to bar steps is deliberate: it reads as musical, and it
  masks any fader-step coarseness (the smoothness unknown above). Spatial entry (new identity
  walking in from one strip end) is a variant worth having as a template flag for the long
  venue strip, but rhythmic-accent entry is the default — on short strips spatial splits can
  read as malfunction.
- **Harmonic mix vs clash (needs A's key axis).** Adjacent Camelot keys → adjacent families →
  the base-morph passes through the families *between* them: the blend reads as one color
  evolving — visually consonant, the room feels the mix "working." Distant keys → **do not
  morph through the mud** (interpolating far hues crosses grey/brown); instead the grammar
  switches to alternation: outgoing and incoming identities trade accent ownership with rising
  incoming share, then the base **snap-commits** at the resolve threshold. Tension reads as
  tension, and no frame shows a muddy in-between.
- **Quick cut.** Blend rises faster than ~2 s or the active deck switches outright → skip the
  ceremony: instant identity snap, exactly today's behavior plus the new palette. Confirmed
  correct choice per the existing reset design (`smart_phrasing.py:206-214`).
- **Botched / abandoned blend (the grammar must fail gracefully — it does by shape).** The
  scalar is monotonic-with-hysteresis: presence steps gained per bar are only *released* one
  bar at a time when the fader retreats and stays retreated. A blend that rises to 40% and
  comes back simply breathes in and back out — no identity flapping, no resolve moment fired
  (the resolve requires cross-and-hold). Stale data mid-blend freezes, then decays, as above.
- **The double drop.** Both decks beat-aligned (per-deck beat state exists for both), both
  upfaders top, and both tracks inside a drop section within ~a bar of each other — the one
  moment two identities *deserve* to coexist: interleaved dual-palette accents at full
  intensity with white peaks marking the shared downbeats. Rare by construction (the gate is
  strict and all-backbone), high-impact, and it degrades to the ordinary blend grammar whenever
  any condition fails.

---

## What a Codex spec must pin (bullets, not the spec)

**Workstream A — identity derivation:**
- Derivation function: pure, deterministic, keyed on `content_id` (fallback filepath) only — no
  set_seed, no active_deck, no RNG; fixed published mapping from the four axes + key to family
  and texture/depth/dynamics parameters.
- Integration: derive inside the existing resolve worker
  (`state_manager.py:1781-1814,2004-2016`), publish with `ANLZ_DATA`-pattern event → deck meta;
  color engine consumes at `begin_dispatch` (`led_dispatch_policy.py:735-749`,
  `led_color_engine.py:346-399`), replacing the journey `_pick_palette` at track boundary when
  an identity is present; journey behavior remains the no-identity fallback and the drop-snap
  (`led_color_engine.py:404-426`) must respect identity (snap within family or to designated
  accent family, decision to pin).
- Enable path: decouple from `RBSS_SMART_REARM_EXPERIMENT` (`state_manager.py:566-569`,
  `__main__.py:888-901`) — own flag or unconditional-with-cache.
- Config: extend `scale_stops` with warm stops + new family rows; schema validation already in
  `led_config.py:951-954,1253`.
- Test seams: derivation is a pure function → table-driven tests on synthetic scalar vectors;
  determinism test (same input twice); tier-fallback tests (no librosa / no key / no ANLZ);
  push-loop guard: no file I/O in `begin_dispatch` path (assert via existing no-I/O conventions).
- Invariants: same track same palette across sessions; ANLZ tier stands alone; identity never
  overrides blackout/emergency/manual; docs contract `led_govee` + config contract.

**Workstream B — arrival scheduler:**
- `AnimInstance` gains optional `target_abs_beat`/`travel_beats`; render path
  (`beat_sync_engine.py:190-201`) computes arrival progress from live `abs_pos`; wall-clock TTL
  expiry stays as the safety net (`:183-188`).
- Wrap/jitter degrade rules exactly as §B2 (wrap → wall-clock completion; jitter threshold →
  trigger-on-beat; anchor None → idle path `govee_realtime_runner.py:240-274`).
- Target selection helper: pure `next_boundary(abs_pos, division)`; no beat_math/elapsed-ms
  dependency on the LED side.
- Spec params surface: `arrive_division`, `travel_beats`, shape params — through
  `EffectSpec.params` (`govee_realtime_runner.py:284-298` configure seam).
- Test seams: `BeatSyncEngine` is already pure and thread-free (`beat_sync_engine.py:1-6`) —
  unit tests drive `on_tick` with synthetic (abs_beat, now, bpm) sequences: drifting BPM lands
  on target; backward jump degrades; pause/resume finishes flight.
- Invariants: no new I/O or threads; runner remains sole caller under its lock; existing
  triggered templates render byte-identically when no arrival is requested.

**Workstream C — blend:**
- Blend scalar: from `MixerAuthoritySnapshot` deck 1/2 `upfader_norm`
  (`state_manager.py:1137-1141`, `models.py:116-136`); EMA + hysteresis constants pinned after
  the recorded-session measurement; bar-quantized presence steps for accents.
- Data shape: `incoming_palette_ref` + `blend` through the LED context/frame path
  (`led_models.py:213-226`, `led_dispatch_policy.py:753-762`); interpolation in p-space
  (`led_color_engine.py:57-90,579-591`); never raw-RGB lerp across distant hues (clash rule).
- Authority: blackout/emergency/manual-static precedence unchanged
  (`led_dispatch_policy.py:251-252`; AGENTS.md §6 Static Override rules); blend applies only to
  automated palette resolution.
- Degrades: stale (>1.0 s, `active_deck_resolver.py:12`) → freeze-then-decay; mixer authority
  absent (non-7.2.11 Rekordbox, `rb_offsets.py:108-111`) → time-based proxy from deck-switch
  events; hard cut → snap.
- Test seams: blend-scalar state machine as a pure function (fader series in → presence steps
  out): long blend, retreat/abandon, slam, staleness, double-drop gate.
- Invariants: deck 1/2 only; no push-loop I/O; resolve fires once per completed blend;
  decks 3/4 and stale worlds indistinguishable from today's behavior.

---

## Beyond the three — seeds (bounded to three)

1. **Drop-landing restore.** During a detected breakdown, ease the room down (within the
   track's dynamics budget), then use the arrival scheduler to have light *return and land
   exactly on the drop's first beat* — the ANLZ drop beat is known ahead of time
   (`anlz_reader.py:142-149`), and pre-arming against a future beat is the proven autoloop
   pattern. Signals: ANLZ structure + arrival engine (both verified above). Gate: degrades to
   today's role change if the drop marker is absent/unstable. Lift: small (one template family
   on B's engine). Risk: low — worst case the restore is a normal role transition.
2. **Texture-gated accent discipline.** Use kick-variability + flatness (A's measured axes) to
   gate which tracks are *eligible* for the harshest accent behaviors (strobe-adjacent pulses,
   hard whites): punchy/noisy peak-time tracks earn them, smooth melodic tracks never show them
   — a per-track taste guardrail with zero authoring. Signals: cached spectral summaries.
   Gate: absent data → conservative default (no harsh accents). Lift: config + one predicate in
   look eligibility (the `diy_eligible` seam at `led_color_engine.py:432-459` is the template).
   Risk: low.
3. **Key-neighborhood pre-echo.** When the incoming deck has a track loaded and cued (before
   any fader movement), let ambient accents drift one step toward the incoming track's hue
   family — the room subtly foreshadows the next chapter. Signals: track-load events + key (100%
   coverage) + A's family map. Gate: no key/no identity → no drift; any blend/authority state
   overrides it. Lift: small (an accent-bias input to the existing ambient role). Risk: low,
   but it is a *taste* feature — listed for Brandon's veto.

---

## Open questions for Brandon (only ones he can answer)

1. **Palette family board (A):** react to the 10-family table — names, feels, and especially
   the three new warm families (Ember/Gold/Solar). Which families feel wrong for your rooms?
   And one rotation choice: which Camelot region should anchor the cool core (the current
   blue-heavy look) so the wheel mapping starts from taste, not arbitrariness?
2. **Identity reveal (A):** want the first-play-of-the-night 2-bar bloom, or is it too precious?
   The system is complete without it.
3. **Blend default (C):** accent-first rhythmic entry as the default grammar, with spatial
   end-to-end entry as a per-template variant — agree, or do you want spatial as the venue-strip
   default?
4. **Double drop (C):** keep the dual-identity + white-peaks moment, or is any dual-palette
   frame off-brand for your rooms?
5. **One recorded blend session (C, cheap hardware gate):** run a practice session with
   `RBSS_RECORD_SESSION=<path>` and ride a few long blends on the DDJ-800 — that single file
   turns the fader-smoothness unknown into measured smoothing constants for the Codex spec.
6. **Rekordbox pin (C):** the fader features ride on Rekordbox 7.2.11 offsets; upgrading
   Rekordbox drops them (invisibly, by design) until offsets are re-derived. Acceptable
   operating constraint?

---

## Claim-label index (load-bearing claims)

- Spectral cache coverage/stability/discrimination numbers — **confirmed (measured this
  session; scripts in session scratchpad, read-only)**.
- Per-band peak normalization destroys cross-band loudness — **confirmed**
  (`audio_spectral_features.py:148-150,197-201`); warm↔cool-from-bass-balance axis —
  **rejected** for schema v3.
- Onset-strength variability as an axis — **rejected** (measured stability 0.767/64.5%).
- Key availability 100% via bridge's DB layer — **confirmed (measured; API per
  `filepath_resolver.py:281-283`)**.
- Mood coverage 97.7% but 92.5% mood=1 — **confirmed (measured, n=300)**; mood as identity
  axis — **rejected as primary**, retained as weak texture nudge.
- `_journey_rng` session-seeded, not per-track — **confirmed**
  (`led_color_engine.py:266-281`; live `set_seed_mode: "random"`).
- Arrival data path (anchor per frame, live BPM) — **confirmed**
  (`state_manager.py:3546-3555`, `led_dispatch_policy.py:259-273`,
  `govee_realtime_runner.py:207-219,277-280`).
- Spawn-frozen BPM drift — **confirmed** (`beat_sync_engine.py:190-201`).
- Crossfader offset — **confirmed absent**; deck 3/4 faders — **confirmed absent**
  (`rb_offsets.py:108-111,180-183,196-201,236-237`).
- Mixer offsets only for Rekordbox 7.2.11; installed version 7.2.11.0342 — **confirmed**.
- Fader physical smoothness during a ride — **unknown** (no recording exists; acquisition path
  named).
- LED context single-deck — **confirmed** (`led_models.py:213-226`).
- Extraction determinism — **confirmed (measured: bit-identical ×3 tracks, run-vs-run and
  run-vs-cache)**.
- "Palette use has a lower trust bar than drop timing" — **confirmed** (stability numbers +
  the structural integration argument in §Verdicts).
