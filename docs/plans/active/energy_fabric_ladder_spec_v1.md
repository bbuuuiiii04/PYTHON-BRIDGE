---
doc_status: draft-for-review
truth_level: planned
last_verified_commit: e76cbbf0
last_verified_date: 2026-07-24
validation_scope: >
  Design spec only (EFSPEC seat, exec4 dispatch 2026-07-24). Authorizes NO
  implementation, no config change, no runtime change; every build stage below
  needs its own Codex spec, review, and operator gate. All code claims verified
  at HEAD e76cbbf0 on 2026-07-24 and labeled confirmed/assumed/unknown.
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Energy-Fabric Ladder — design spec v1 (the 3-layer energy read + cue casting)

This is the queued "energy-ladder spec expands to the full fabric" item from the
operator's 2026-07-22 final-vision addendum. It defines the three-layer energy
fabric (track-in-library × section × drop), the cue-CASTING consumer, and the
breath-hold presentation behavior — LED-first, laser layer untouched.

**Governing vision (operator law, quoted faithfully — never re-solicit):**

1. **Transcription vision (AUTHORITATIVE, ratified 2026-07-22):** "The lights
   are **an instrument playing the track** — not decoration synced to it. …
   The show is **composed per track from what the track actually contains** …
   never merely selected from a pool and garnished. The target is
   **TRANSCRIPTION: music into light, continuously**." Interface law: "the
   mapping runs sound → light DIRECTLY, with no vocabulary bottleneck; his only
   job is vetoing wrong translations." The energy fabric below is a COMPONENT
   mechanism in service of that statement, not the finish line.
2. **Energy-fabric addendum (2026-07-22):** "Energy is a three-layer fabric the
   bridge must read simultaneously: (1) **Track weight** relative to his ENTIRE
   library … (2) **Section energy arcs** — buildups, breakdowns, grooves, not
   just drops (an 'energetic breakdown' in hard techno must read as such).
   (3) **Per-drop energy grade** within the track." Cue selection law: "cues
   are **CAST, never cycled** — right cue, right track, right energy moment."
   Genre-feel anchors: "hypnotic deep house → calm, soothing, hypnotic
   beat-pulse cues; hard-hitting dubstep → strobe-heavy, impactful; relentless
   hard techno → 'suffocating' but tracking the moment; breathing/pulsing
   breakdown → LEDs breathe and pulse with it." Breath-hold rule: "a track
   that holds its breath ~4 bars before a drop must NOT get buildup LEDs
   continuing to sparkle-ramp — the lights hold their breath too. Anticipatory
   silence is part of sync." Lasers: "accents for the track, or grand moments
   that genuinely warrant them — never wallpaper."
3. **Standing laws that bound this design:** no drop ever gets a dim look
   (dim = breakdowns/tails only); a TRUE drop = first marker in a drop section
   with an up-buildup runway (the bridge already encodes it — never re-derive);
   no labeling sessions ever (all descriptor vocabulary is machine-internal;
   validation = normal mixing + operator veto, silence is a pass); whole-catalog
   features only (per-track hand-tuning gets cut).

---

## Part A — Context & current state (verified at HEAD e76cbbf0; read, do not implement)

### A.1 What exists today, per layer

**Layer-1 raw material (track-level features) — EXISTS, no track-weight axis:**
- [confirmed] Per-beat v4 spectral features: `audio_spectral_features.py:24-25`
  (`SCHEMA_VERSION = 3`, `SCHEMA_VERSION_V4 = 4`), cached per track by
  `spectral_cache.py` with a strict versioning convention — every schema version
  owns its own subdirectory, eviction never crosses versions
  (`spectral_cache.py:3-5`), and `RBSS_SPECTRAL_CACHE_DIR` moves all versions
  together (`spectral_cache.py:222`).
- [confirmed] Derived character axes already exist: `identity_axes()` returns
  grit / punch / bass / drama (`spectral_profile.py:118-125`); `bass_duty()`
  (`spectral_profile.py:98`) is a duty fraction derived at load, never stored,
  so thresholds can re-tune without cache desync.
- [confirmed] Offline energy utilities: `energy_model.py` is pure and
  side-effect-free (header, lines 1-7) with `IntensityClass`
  low/medium/high/peak/low_confidence and calibrated drop-lift / breakdown-depth
  / buildup-slope constants (`energy_model.py:15-28`).
- [confirmed] Offline hardness shadow: `hardness_v0.py` (header) — zero runtime
  importers, non-authoritative, offline only.
- [confirmed] The stage2/v12 research feature store lives at
  `local/spectral_v5_2026_07_17/` — `stage2_pilot.py:39-45` (versioned
  `stage2_*_results.json`, regeneration keyed by `feature_config_hash`),
  `stage2_pilot.py:94-95` (v12 = `vocal_copy_gain` on the frozen 2.0 s tiled
  window clock, descriptive-only), artifacts under `stage2_artifacts/`
  (`stage2_pilot.py:601`). It is research-local, not a runtime input.
- **Gap:** nothing computes a track's energy weight **relative to the whole
  library**. `identity_axes` are absolute per-track numbers; no library-wide
  normalization exists anywhere at HEAD. [confirmed by absence — repo-wide
  search found no consumer ranking tracks against a corpus distribution]

**Layer-2 raw material (sections) — EXISTS, no per-section energy grade:**
- [confirmed] Phrase segmentation: `smart_phrasing.py:23`
  `PhraseLabel = Literal["up", "chorus", "low", "other"]`;
  `build_phrase_segments_from_markers()` (`smart_phrasing.py:634`);
  `SmartPhrasingEngine` (`smart_phrasing.py:158`) tracks
  current/previous phrase label live (`smart_phrasing.py:312-338`).
- [confirmed] Audio-derived section structure: `section_map()`
  (`spectral_profile.py:531`) segments a track by spectral character with
  per-section character vectors (`character()` at `spectral_profile.py:562`).
- **Gap:** sections have *labels* and *character*, but no energy grade — nothing
  says "this breakdown is energetic for a breakdown" or scales a section
  against the track's own arc or the library.

**Layer-3 raw material (drops) — TRUE-drop machinery EXISTS, no LED energy grade:**
- [confirmed] True-drop selection + runway: `runway_beats()` now lives at
  `smart_phrasing.py:714` (AWR-257 moved it there; `drop_presentation.py:33-36`
  imports it), counting contiguous "up"/"low" beats before a drop
  (`_RUNWAY_LABELS`, `smart_phrasing.py:20`).
- [confirmed] Per-drop static classification: `DropDecision`
  (`drop_presentation.py:192`) carries beat / tagged / learned / is_finale /
  personality_presentation / runway — **no energy-grade field**. `TrackPlan`
  (`drop_presentation.py:225`), `plan_track()` (`drop_presentation.py:247`),
  `resolve_presentation()` (`drop_presentation.py:356`).
- [confirmed] Live consumers of runway: `state_manager.py:2855` (drop
  qualifier), `:2860` (record-breaking), `:3034` (session observation).
- [confirmed] A drop-window descriptor already exists offline:
  `drop_window_vector()` (`spectral_profile.py:619`).
- **Gap:** the laser side has a tier ladder; the LED side has no per-drop energy
  grade unified with layers 1-2.

**Breath-hold precursor — detector EXISTS, has NO consumer:**
- [confirmed] `pre_drop_gap_beats()` (`spectral_profile.py:183-199`) measures
  the bottom-gone run immediately before a drop beat, purely descriptive, drop
  beat always from ANLZ markers. Its docstring says "consumer caps it, e.g. ~4
  bars" — but a repo-wide search finds **no callers outside
  `tests/test_spectral_profile.py`**. The consumer is aspirational, not built.
- [confirmed] The laser side has a *fixed* `pre_drop_blackout_beats: 4`
  (`laser_config.py:73`) — fixed-length, not audio-matched, and laser-only.
  The LED side has no breath-hold behavior at all.

**Cue selection today — CYCLED, not cast:**
- [confirmed] `led_look_director.py:89-101`: look picks come from seeded RNG
  bags/cursors per (role, backend); the deterministic transport plan picks WHICH
  transport, the RNG bag picks WHICH look inside it. Roles in play include
  "utility", "emergency", "manual", "post_drop" plus a config `role_map`
  (`led_look_director.py:179-233, 278-279, 299`). This is exactly the
  "selected from a pool" behavior the vision retires.
- [confirmed] Color already has a journey: `led_color_engine.py` palette
  selection with rarity-compressed weights (`led_color_engine.py:158-163`) —
  color is spectrally-informed (Lighting Engine v2 F1), but *look/cue* choice
  is not.
- [confirmed] F4 is seasoning, not energy casting: `_f4_drop_seasoning_key`
  (`led_dispatch_policy.py:162`), F4 plan/beat helpers
  (`led_dispatch_policy.py:1171-1215`) — per-texture parameter nudges to the
  base cue. It fires no discrete events and reads no track-weight/section
  grade. The fabric is a NEW capability, not an F4 tune-up.

### A.2 Root statement of the gap

All three layers have their *raw material* at HEAD, and none has its *grade*:
no library-relative track weight, no section energy grade, no LED-consumable
drop grade — and the one consumer law the vision names (CAST, never cycled) is
structurally the opposite of today's RNG bag. The breath-hold detector exists
and is orphaned. This spec designs the grades, the casting consumer, and the
breath-hold behavior on top of the existing machinery — no new analysis
runtime, no new detectors, no re-derivation of true drops.

---

## Part B — Design (implement in stages, each with its own Codex spec + gate)

### B.0 Absolute rules

- LED-first. The laser chain (`laser_director.py`, `laser_config.py`, tiers,
  `violence`) is untouched by every stage below.
- Layer-1 computation is **offline** (tools lane, like
  `tools/spectral_calibration_report.py`) — the runtime only ever *reads* a
  precomputed per-track sidecar. No new analysis in the bridge process.
- No new operator vocabulary, no labeling: every descriptor below is
  machine-internal. Operator contact = normal mixing + veto; silence is a pass.
- Cast, never cycle: where a cast is defined, an RNG fallback may only fire
  when cast inputs are missing (fail-open to today's behavior), never as a
  variety mechanism within a defined cast.
- No dim drop looks ever — the fabric may grade a drop LOW, and the floor of
  what a low-grade drop receives is still a full-brightness drop treatment.
  Dim belongs to breakdowns/tails only.
- Whole-catalog only: every grade formula must be computable for every track in
  the library from the v4 cache; anything needing per-track hand-tuning is out.

### B.1 Layer 1 — track weight (library-relative, gain-invariant, offline)

**What it is:** one scalar `track_weight` ∈ [0,1] (percentile rank of the
track's energy character against the whole library) plus the existing
grit/punch/bass/drama axes carried alongside as the track's *feel coordinates*.

**Design:**
- An offline tool (new, `tools/` lane, zero runtime importers — same discipline
  as `hardness_v0.py`) sweeps the v4 cache for the library, computes per-track
  aggregate descriptors, and writes (a) one library distribution file and (b) a
  per-track sidecar entry holding the track's percentile ranks. Storage follows
  the `spectral_cache.py` versioning convention (own namespace/version dir, no
  cross-version eviction — `spectral_cache.py:3-5`).
- **Gain-invariance constraint:** absolute-dB features (e.g. `sub_db` against
  calibrated dB thresholds, `spectral_profile.py:104,113`) are level-sensitive;
  a hot-mastered track must not outrank a quiet-mastered harder track. The
  aggregate therefore prefers, in order: duty/fraction measures
  (`bass_duty`-style), within-track relative measures (drop-lift,
  breakdown-depth, buildup-slope per `energy_model.py:17-27`), density/rate
  measures (onset density, flag duties), and rank-normalized scalars — and the
  final `track_weight` is a **percentile against the library**, which absorbs
  monotone level offsets by construction. [assumed] the existing duty/relative
  measures carry enough signal; the offline tool must report a
  loudness-vs-weight correlation check so this assumption is tested with data
  before any consumer ships.
- The genre-feel anchors (deep house calm ↔ dubstep strobe-heavy ↔ hard techno
  suffocating) are **acceptance targets for where known tracks should land in
  the distribution**, not a genre classifier: the offline report names where
  exemplar tracks fall so the operator can veto obviously wrong placements.
  No genre taxonomy is built or asked for.

### B.2 Layer 2 — section energy arcs

**What it is:** per phrase-segment energy grade = *within-track shape* scaled
by *track weight*, so "an energetic breakdown in hard techno reads as such":
a hard-techno breakdown can out-grade a deep-house groove because layer 1
multiplies in, while still reading as the track's own valley because the
within-track shape says so.

**Design:**
- Computed at track load (off the hot path, where the v4 cache is already
  loaded), pure function over: `PhraseSegment` boundaries
  (`smart_phrasing.py:634`) × per-beat v4 series × the layer-1 sidecar. Where
  phrase data is absent, `section_map()` (`spectral_profile.py:531`) is the
  fallback segmentation; where both are absent, layer 2 is absent (fail open —
  consumers behave as today).
- Output per section: `section_energy` ∈ [0,1] (two components kept separate
  for consumers: `within_track` and `library_scaled`), plus the section's
  existing label ("up"/"chorus"/"low"/"other") untouched. Labels stay the
  runway/true-drop authority — layer 2 grades sections, it never relabels them.

### B.3 Layer 3 — per-drop energy grade

**What it is:** each TRUE drop (existing selection law — first marker in a drop
section with an up-buildup runway; unchanged, not re-derived) gets
`drop_grade` ∈ [0,1]: the drop's energy within the track's set of drops,
scaled against library-typical drop energy via layer 1.

**Design:**
- Computed offline/at-load from `drop_window_vector()`
  (`spectral_profile.py:619`) + runway context + `energy_model.py` drop-lift
  measures; surfaced as a NEW field on the per-drop static classification
  (extending `DropDecision`, `drop_presentation.py:192`, which today has no
  energy field). Which drops are true drops, runway math, tag/learned/finale
  logic: all unchanged.
- `drop_grade` is presentation input only: it biases which cue is cast and how
  hard the accent/impact reads — it never gates whether a drop is treated as a
  drop (that stays `resolve_presentation()`'s ladder), and per B.0 it can never
  produce a dim drop.

### B.4 Consumer — cue CASTING (the R8 cue-compiler content)

**What it is:** replace "RNG bag inside the chosen transport" with "best-match
cast under the three-layer coordinate," keeping everything around it intact.

**Design:**
- Each look/cue gains descriptive **cast coordinates** (energy floor/ceiling it
  suits, character tags like beat-pulse / strobe-impact / breathe) — authored
  as metadata in the existing look config surface and Template Lab flow.
  [unknown] whether the current look-metadata shape can host this without
  schema change — the casting-stage Codex spec must read
  `led_config.py`/Template Lab metadata first and extend the `config_schema`
  contract if needed.
- Cast resolver = pure function: (candidate looks for the role/backend, cast
  coordinates, current fabric state {track_weight, section_energy + label,
  drop_grade, feel axes}) → one look + a reason string. Deterministic
  tie-break (stable hash of track + section index — no RNG in the cast path).
  The existing deterministic transport plan, role_map, bank/palette filters,
  emergency/manual roles (`led_look_director.py:179-233`) all stay; only the
  *pick inside the surviving candidate set* changes from bag to cast.
- Variety without cycling: the fabric state itself varies (sections change,
  drops differ, tracks differ), which is the vision's own answer — the right
  cue for the moment, repeated when the moment repeats. The known risk is a
  thin cue pool making casts repetitive; the operator has already ruled the
  pool "way too small" with expansion as a standing Template Lab need — pool
  thinness is NOT a reason to reintroduce cycling.
- Fail open: any missing coordinate or absent fabric state for the current
  track → the existing bag pick, logged with a reason (DEBUG-level for
  per-pick detail, INFO only for outcomes, per repo log style).

### B.5 Breath-hold (named presentation behavior)

**What it is:** the operator's litmus test, as a first-class named behavior:
`breath_hold` — when the track audibly holds its breath before a true drop,
buildup LED ramps freeze/quiet instead of continuing to sparkle-ramp.

**Design:**
- Detection is the existing orphan: `pre_drop_gap_beats()`
  (`spectral_profile.py:183`) per true drop, computed at track load, capped
  (~4 bars per its own docstring; exact cap is a config knob with a calibrated
  default — hardware/rooms need tuning). Gap of 0 → no hold (music runs
  straight in). No new detector is built.
- Window: `[drop_beat − min(gap, cap), drop_beat)`. During it the LED layer
  holds — suppresses buildup ramp/sparkle escalation in favor of a quiet hold
  (hold ≠ mandatory blackout; "the lights hold their breath" — the exact held
  look is a presentation choice for the stage spec, biased toward near-dark
  stillness). At `drop_beat` the normal drop impact fires unchanged.
- Precedence (explicit, checked against ALL pending state per the pre-handoff
  rules): breath_hold loses to emergency/blackout masks and manual overrides;
  it must never delay, replace, or dim the drop impact itself; it must clean up
  on every exit path (track change, seek/jump past the window, stop, mode
  transition) — not just the path that armed it.
- The laser `pre_drop_blackout_beats` stays as-is (laser untouched); a later
  unification is possible but out of scope.

### B.6 Staging (each stage = its own Codex spec, review, operator gate)

1. **E1** — offline layer-1 tool + library distribution + per-track sidecar +
   the loudness-correlation and exemplar-placement report. (No runtime change.)
2. **E2** — layer-2 section grades at track load (pure function + status
   surface; no consumer yet).
3. **E3** — layer-3 `drop_grade` on `DropDecision` (pure function + status
   surface; no consumer yet).
4. **E4** — cast coordinates on looks + the cast resolver replacing the bag
   pick (the behavior change; biggest gate).
5. **E5** — breath_hold consumer wiring.

E1-E3 are read/compute-only and independently verifiable in status output
before any visible behavior changes in E4/E5. Order of E4 vs E5 may swap at the
exec's discretion; both require E1-E3.

---

## Part C — Invariants that MUST still hold (live safety)

- The 200 Hz push loop (`state_manager.py:499`, `_TICK_INTERVAL = 1.0/200`)
  gains NO blocking network, socket, MIDI, filesystem, or subprocess I/O.
  Layer 1 is offline; layers 2-3 and cast-coordinate loading happen at
  track-load off the push loop; the cast resolver and breath-hold check are
  pure in-memory functions.
- `StateManager` remains the only writer of `DeckState`; fabric state rides the
  existing event/snapshot flow (`BridgeEvent`s immutable after creation);
  reader threads never mutate `DeckState`.
- `ANLZ_PATH` before `TRACK_LOADED` ordering unchanged
  (`rb_state_reader.py::_tick_deck`).
- True-drop selection, runway math, and every existing drop qualifier
  (`state_manager.py:2855`) byte-for-byte unchanged through E1-E3; E4/E5 change
  *presentation choice*, never drop detection or timing.
- Held Static Override, blackout/emergency masks, pack-disabled/shutdown
  zeroing keep their existing precedence; breath_hold and casting both sit
  BELOW all of them.
- Fail open everywhere: missing sidecar, stale cache version, absent phrase
  data, unmetadata'd looks → today's exact behavior. A broken fabric must
  degrade to the current show, never to darkness. No broad try/except, no
  silent success-shaped fallbacks — the fallback is explicit, logged, and
  status-visible.
- Laser subsystem: zero diffs, all stages.
- Live-mixing walk-through (required in each stage spec): deck A playing with
  fabric state while deck B loads (per-deck state, no cross-deck bleed);
  operator jumps into/out of a breath-hold window mid-phrase (window re-check
  from current beat, cleanup on seek); track without ANLZ/phrase data mixed in
  (fail open); cache version bump mid-library (per-version namespace means old
  entries simply miss → fail open).

---

## Part D — Tests (pure-function seams; no on-disk/subprocess dependency)

- Layer-1 aggregate + percentile ranking: pure over synthetic
  `SpectralFeaturesV4` fixtures (existing pattern in
  `tests/test_spectral_profile.py`); explicit gain-invariance test — same
  fixture with a constant dB offset must keep its rank direction on the
  duty/relative aggregate.
- Layer-2 grades: pure over synthetic PhraseSegments × v4 series; absent-data
  fail-open cases.
- Layer-3 `drop_grade`: pure over drop_window_vector fixtures; asserts
  DropDecision extension changes no existing field semantics (equality/repr).
- Cast resolver: pure; determinism test (same inputs → same pick, twice);
  tie-break stability; fail-open-to-bag when coordinates missing; no-dim-drop
  floor asserted for drop-role casts.
- breath_hold window: pure window math incl. cap, gap=0, seek-into-window,
  and precedence table (mask beats hold, hold never crosses drop_beat).
- Invariant test: the offline layer-1 tool has zero runtime importers (same
  guard style as `hardness_v0.py`'s).

---

## Part E — Acceptance / definition of done (per stage, and for this doc)

**For this document (now):** exec review → operator gate on the DESIGN
(especially B.4's cast-replaces-bag and B.5's held-look choice, both
veto-first: the defaults above stand unless vetoed). Registration in
`docs/status/active_work_registry.md` + `docs/architecture/doc_index.md` is the
exec's landing step (out of this seat's write scope).

**For every implementation stage (later, non-negotiable):**
- Contract-first: identify the matching keys in
  `docs/agents/change_contracts.yml` before code — expected: `led_govee`
  (line 101), `drop_presentation` (line 430), `spectral_analysis` (line 698),
  `config_schema` (line 670) for cast metadata, `tests` (line 785); extend
  contracts first if a change has no match.
- Update every `docs_update` doc those contracts list; run the hard checks
  (`tools/check_docs_metadata.py`, `check_agent_contracts.py`,
  `check_docs_drift.py`, `check_ui_jargon.py`) + `python3 -m unittest discover
  tests`.
- Status language stays §10-allowed; nothing here ever claims beyond
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED without a validation matrix.
- Operator verification = normal mixing + veto; no labeling sessions, ever.

### Non-scope (explicit)

- The **accent layer** (base + event-locked overlay; SPIRAL/ANIMALS/GODSPEED
  exemplars) — a sibling capability class with its own future spec; the fabric
  feeds it later but nothing here builds it.
- Laser behavior, tiers, warrants, and the Stage-A retriever/veto-list
  deliverable (separate lane).
- Template Lab pool expansion (standing need, separate lane).
- Any runtime embedding/encoder work (R4 lane CLOSED; Stage A engineered
  baseline is the standing retriever — not consumed here).
- Rewriting F4 (stays as seasoning, untouched).

### Claim ledger

- [confirmed] every file:line in Part A, re-read at HEAD e76cbbf0 on 2026-07-24.
- [assumed] duty/relative/rank measures suffice for a gain-invariant
  track_weight (E1's correlation report is the test).
- [assumed] the ~545-track calibration-era corpus ≈ current library scale for
  percentile stability (E1 recomputes against the actual library; nothing pins
  the old corpus).
- [unknown] look-metadata schema fit for cast coordinates (E4 spec must read
  `led_config.py` + Template Lab metadata first).
- [unknown] end-to-end LED latency budget for tight breath-hold releases at
  high BPM (no measurement exists; measure before promising sub-beat
  precision — honest-confidence note in the ratified vision record).
