---
doc_status: current
truth_level: code-verified + measured-corpus
last_verified_commit: f3c06bb
last_verified_date: 2026-07-05
validation_scope: software build + corpus validation only — v4 analysis layer built and validated against the local Rekordbox library (BY GENRE playlists as labeled ground truth); no lighting behavior change, no bridge execution, no hardware validation
---

# Spectral Audio Analysis — v3 Audit, v4 Redesign, and Build

Fable 5 one-shot (2026-07-05, `docs/prompts/fable_spectral_audio_redesign.md`, operator-granted
build exception). Audience: Claude (design lead) folding this into the LIGHTING ENGINE v2
record and the Feature 1–4 Codex specs. Every load-bearing claim is labeled
**confirmed / assumed / unknown / rejected / unproven** and tied to a file:line, a measured
run, or a primary source. Companion docs: the v2 design record
(`docs/research/spectral_palettes_arrival_crossfade_exploration.md`) and its review
(`docs/research/lighting_engine_v2_design_review.md`).

Status of this document: complete — every phase of the one-shot ran to completion in the
2026-07-05 session (audit → research → design → adversarial review gate → build → corpus
proofs → whole-library sweep). Audit rulings §2; design §4 (review gate §4.10); coverage
§5; proofs §6; sweep §7; claim labels §7b; operator taste calls §8.

---

## 1. v3 verdict

**NOT FIT** for the LIGHTING ENGINE v2 mission — while its retained summary scalars are
genuinely stable and stay load-bearing.

Plain paragraph: v3 was built to score smart-drop timing, a purpose that is retired. What it
stores — one averaged number per beat per band, each band rescaled so its own loudest moment
is 1.0 — is enough to say "this track's kick pattern is spiky" (the four identity axes are
measured-stable, Spearman 0.86–0.96) and "the bottom fell out here" (ear-validated), and those
survive into v4. But for describing *what a beat sounds like* it is structurally blind: it
cannot compare loudness across bands (normalization destroys it — so "bass-heavy" does not
exist), cannot tell a sustained bass horn from four kick hits (a beat is one number — attack
and sustain average into the same value), cannot see wobble/growl modulation (proven
non-separable 2026-07-05), cannot count snare-roll hits, and has no tone color beyond one
flatness number. Six of the operator's eight seed requirements are unreachable from v3 data
(coverage table §5). The fix is not more averaging — it is a richer per-beat description:
absolute loudness, within-beat shape, percussive/harmonic split, modulation, and brightness.

## 2. v3 audit — rulings on every element

Evidence base: `audio_spectral_features.py` (201 lines, read in full at `2945c52`),
`spectral_cache.py` (203 lines, full), the extraction seam `state_manager.py:207-250,
1852-1899, 2088-2100`, eviction `__main__.py:888-901`, the runtime consumer
(`anlz_reader.py:759-1036` smart-drop scorer, reads all 8 envelope fields via `getattr`),
tests `tests/test_audio_spectral_features.py`, `tests/test_spectral_cache.py`, and the named
measured facts from the v2 record (not re-derived, per prompt).

| # | v3 element | Ruling | Evidence / required change |
|---|---|---|---|
| A1 | Decode at sr=22050 mono (`audio_spectral_features.py:59`) | **KEEP** | Nyquist 11.025 kHz covers every band the lighting story uses (brightness, hats, grit live below that); halves decode+FFT cost vs 44.1k. Decode determinism is a named measured fact (bit-identical re-runs) — **confirmed**. |
| A2 | STFT frame: n_fft=2048, hop=512 (23.2 ms) (`:70-71`) | **KEEP** | ~43 frames/s is fine grain for within-beat descriptors (≈20 frames per beat at 128 BPM) and standard MIR practice. |
| A3 | Mel front-end, n_mels=128, power=2 (`:63-76`) | **KEEP** | Perceptual bin spacing is right for band energies; 128 bins gives ≥4 bins to the narrowest v4 band. |
| A4 | fmax=12000 with sr=22050 (`:65`) | **CHANGE** | fmax exceeds Nyquist 11025; the top mel filters are empty by construction, so "4000–12000" was really 4000–11025 — harmless but dishonest labeling. v4 states band edges that exist: top edge 11025. **Confirmed** (librosa mel filters above Nyquist have no support). |
| A5 | Band set: sub 20–100, kick 60–200, low-mid 200–800, high-mid 800–4000, high 4000–12000 (`:86-100`) | **CHANGE** | Multiband concept is right; edges re-cut in v4 (§4) to separate sub vs kick-punch vs growl-region vs presence vs air for the lighting vocabulary. The deliberate sub/kick overlap is kept (kick fundamentals straddle 60–120). |
| A6 | Per-band **peak normalization** (`:148-150,197-201`) | **REPLACE** | The single most limiting choice: cross-band loudness destroyed (named measured fact; warm-vs-cool-from-bass-balance axis was **rejected** on v3 because of it). Every band's loudest beat is 1.0 by construction, so cross-track absolute thresholds ("is there real sub here?") are impossible — corpus-absolute calibration (v2 review ruling 4.5) has nothing to stand on. v4 stores absolute dB (fixed reference), which also restores cross-band comparison. Normalized shape stays derivable by consumers. |
| A7 | Per-beat grain = **mean of frames in [beat_i, beat_i+1)** (`:153-194`) | **CHANGE** | Beat indexing is the right domain (consumers are beat-denominated), but a beat collapsed to one mean hides attack-vs-sustain entirely — a sustained horn and four kick hits average identically (this is why stab/sustain and growl/bright were unreachable). v4 keeps the beat index and adds within-beat shape: 4 quarter-beat energy slots per band + per-beat attack/flux descriptors computed at frame rate (§4). Nearest-frame fallback for empty windows — **KEEP** (correct, deterministic). |
| A8 | Double normalization in band path (`:149` then `:163`) | **CUT** (by A6) | `_band_envelope_per_beat` normalizes, then `_frame_envelope_per_beat` normalizes again — a no-op after the first (peak already 1.0). Sloppy, harmless; gone with A6. |
| A9 | `kick_max_envelope` (max across mel bins in 60–200, then per-beat mean) (`:101-110`) | **CUT** from v4 measurements | Built for the retired smart-drop scorer (`anlz_reader.py:899`). Max-across-bins-then-mean-across-frames is neither attack nor loudness; v4's kick-band dB + attack descriptors supersede it. Survives only inside the v3-compat view (§4.7) so the scorer keeps its exact input. |
| A10 | `onset_strength_envelope` (global, peak-normalized, per-beat mean) (`:111-116`) | **REPLACE** | Rejected as an identity axis (stability 0.767 — named measured fact). Global aggregated onset also can't tell *which* band moved. v4 uses per-band positive spectral flux plus an onset-density count (serves snare rolls, jab outlines). Kept in the compat view only. |
| A11 | `spectral_flatness_envelope`, **unnormalized** (`:117-123`) | **KEEP** | The one absolute, cross-track-comparable v3 measure, and the grit axis (stability 0.922). v4 keeps per-beat flatness unchanged in concept. |
| A12 | Silent failure → `None` on missing deps / decode error / <2 beats (`:49-56,125-127`) | **KEEP** | Matches the optional-dependency degradation contract (ANLZ-only tier keeps working). "Absent data reads as no signal" is exactly the v2 failure-mode rule. |
| A13 | One-shot full-track load (no streaming) (`:59`) | **KEEP** | 253 s track decodes in ~2.3 s (measured this session); memory ~22 MB float32 at 22050 — fine in the background worker. |
| A14 | v3 computes the STFT three times (mel via `y=`, onset via `y=`, flatness via `y=`) (`:67,113,119`) | **CHANGE** | Pure waste: each call re-runs the STFT internally. v4 computes one STFT and derives everything from it (measured: STFT is 0.10 s of the ~11 s v4 budget; the win is cleanliness more than speed, but it also guarantees all measurements see the same frames). |
| A15 | Cache: JSON per track, atomic write via tempfile+rename+fsync (`spectral_cache.py:75-98`) | **KEEP** | Proven pattern, debuggable, crash-safe. v4 uses the identical write discipline. |
| A16 | Cache key: sha1(realpath + mtime_ns + size + beatgrid fingerprint) (`:129-144`) | **KEEP** | Staleness by mtime+size is the required contract; beatgrid in the key means a re-gridded track re-extracts — correct, since every stored series is beat-indexed. |
| A17 | `evict_stale` deletes any file whose `schema_version` differs (`:175-181`) | **CHANGE** | This is the mechanism that would have silently destroyed all 488 v3 entries on an in-place schema bump. v4 lives in its own subdirectory (`spectral_cache/v4/`) with v4-only eviction; v3 files are never touched by v4 code. Coexistence + cutover design in §4.7. |
| A18 | No summary scalars stored (envelopes only) | **CHANGE** | The identity axes were recomputed ad hoc in exploration scripts. v4 stores canonical per-track summary scalars in the cache entry (single source of truth), because Feature 1 identities freeze on them (review F-9: v4 is the first and only identity epoch). |
| A19 | Extraction gated on `RBSS_SMART_REARM_EXPERIMENT` + `RBSS_SPECTRAL_ENABLE` (`state_manager.py:566-569`) | **KEEP (this build)** | The flag-decoupling decision belongs to the Feature 1 Codex spec (v2 record settled that; review ruling 1.14). This build changes no gating — zero-behavior-change requirement. |
| A20 | Runtime consumer: smart-drop energy shadow scorer reads all 8 fields (`anlz_reader.py:759-1036`) | **KEEP (unchanged)** | Duck-typed `getattr` reads mean any object carrying the same 8 attributes with the same values keeps the scorer bit-identical — that is how v4 feeds it without behavior change (§4.7, proof §6). |

## 3. Lighting requirements inventory

Every requirement the v4 analysis must serve, mapped to its v2 consumers. R1–R8 are the
operator's seed list (prompt); R9+ are the lighting-designer extensions from the v2 record,
review, and the four research-round adoptions. "Consumer" names the v2 feature/finding that
reads the measurement.

| ID | Requirement (plain language) | v2 consumers |
|---|---|---|
| R1 | Percussion clear and distinguished from everything else, per beat | Texture kick-prominence class (record F4 Tier 1); motion style (F1 item 8); drop-type classifier (correction 3) |
| R2 | A euphoric 8-beat synth at a drop start is captured and outlined (sustained, bright, tonal) | Drop-type selection (synth-house family); texture Tier 2 whir class (record F4 Tier 2); build body language (F2 item 2) |
| R3 | An intense dubstep "head bang" drop with scratchy, jabby punches is outlined as exactly that | Drop-type selection (dubstep wall / stutter-burst, addendum 16/17); texture growl class |
| R4 | Bass house punchy, stompy beats are distinguishable as their own thing | Drop-type selection (bass-house pulse-expand); genre-discrimination proof |
| R5 | Buildup snare rolls captured, including acceleration | Buildup cue selection/verification (correction 2 carriers); phrase-end stinger context (item 20) |
| R6 | Emptiness before a drop detected and **sized** (it sizes the blackout) | Audio-matched pre-drop blackout (addendum 3, review 2.7/F-16); texture empty-floor class |
| R7 | A sustained bass horn reads as sustained, never as hits | Festival-tech-house drop character (ODDMOB per operator genre map); texture; build body language |
| R8 | Track color identity: grit / punch / bass / drama (or better) with equal-or-better measured stability | Feature 1 identity zones (record A3); laser personality picker (review 5.9); accent discipline (seed 2) |
| R9 | Drop-window character descriptors that separate the six labeled genres' drop characters | Drop-type cue selection (review 2.9, F-11 neutral default); the required genre proof of this prompt |
| R10 | Within-track bright/dark tilt per beat | Texture sparkle tone (F4 Tier 1) |
| R11 | Thick vs thin texture per beat | Texture (F4 Tier 1); span scaling context (item 21) |
| R12 | Kick-prominence beat match per beat | Texture percussion-locked hits (F4 Tier 1) |
| R13 | Growl vs euphoric-whir separation (the proven v3 failure) | Texture Tier 2 (record F4 Tier 2: growl → dark identity-colored sparkle; whir → cyan/white/violet) |
| R14 | One shared "bottom-gone" silence primitive, corpus-absolute | P-2/F-16: texture darkness + blackout scan + landing eligibility must agree about silence |
| R15 | Per-beat energy arc usable against ANLZ structure (breakdown depth, build rise) | Landing restore (P-3); intra-phrase development (item 19); dynamics budget (F1 axis 4) |
| R16 | Attack sharpness / body language (sharp stabs vs smooth glide) per track and per section | Build-move body language (F2 item 2); motion style (F1 item 8) |
| R17 | Harsh-accent eligibility gate inputs (punch + grit) | Texture-gated accent discipline (record seed 2) |
| R18 | Corpus-absolute calibration constants for every classification threshold, from labeled EDM only | F4 Tier 1 rule (review 4.5); this prompt's track-selection rule |
| R19 | Deterministic, optional-dep-degrading, budgeted extraction (engineering floor) | Build requirements (prompt); CI 3.11 |
| R20 | Off-beat (hat) activity visibility within the beat | Tech-house post-drop chase rides off-beats (item 16) — selection context, not trigger |

Explicitly **not** requirements (containment): no output may time or trigger a cue — drops,
blackout anchors, and phrase boundaries come from ANLZ markers and locked designs. v4
describes; it never decides. Worst-case wrong output = wrong seasoning.

## 4. v4 design

Adversarially reviewed before implementation (gate result recorded in §4.10).

### 4.1 Design principles

1. **Describe, never decide** — v4 stores measurements and derives per-beat descriptions;
   no output is a trigger. Consumers (Features 1–4) map descriptions to cue *choices*;
   timing stays with ANLZ markers and locked designs.
2. **Store raw measurements; derive classes at load.** The v3→v4 epoch pain teaches:
   classification thresholds must be re-tunable *without* re-extraction. The cache holds
   absolute physical measurements; classes (bottom-gone, roll, growl…) are cheap pure
   functions over cached arrays, with calibration constants in code — re-tuning is an edit +
   restart, never a 2-hour re-analysis, and never an identity epoch.
3. **One STFT pass** (A14) — every measurement derives from the same frames.
4. **Absolute dB, fixed reference** — cross-band and cross-track comparable (A6);
   corpus-absolute calibration per review ruling 4.5 (measured viable: Appendix B).
5. **Beat-indexed, quarter-beat sub-grain** where within-beat shape matters (A7).
6. **v3-compat block bit-identical** — computed by the same refactored code path on the same
   decoded audio; the smart-drop scorer keeps its exact inputs (A20; proof gate §6).
7. **Deterministic; optional-dep degradation preserved** (A12; research: every op used has
   no randomness — librosa hpss/onset/spectral/load all deterministic, verified-primary-source).

### 4.2 Extraction parameters

sr=22050 mono (A1), n_fft=2048 / hop=512 (A2), mel n_mels=128 fmin=20 fmax=11025 (A3/A4).
HPSS: `librosa.decompose.hpss(S_power, kernel_size=31, power=2.0, margin=1.0)` on the linear
power STFT (defaults; Fitzgerald 2010 median-filter method — verified-primary-source). HPSS
is the cost center (8.5 s of ~11.5 s/track); kept at full resolution because the harmonic-
domain measures (growl timbre, whir level) are the load-bearing new capability and the budget
fits (§4.6).

### 4.3 Stored schema (cache payload, `schema_version: 4`)

Key/staleness identical to v3 (A16): sha1(realpath + mtime_ns + size + beatgrid fingerprint),
stored under `spectral_cache/v4/` (A17). All v4 series rounded (dB: 0.1; ratios: 3 decimals;
centroid: 1 Hz) — rounding is part of the schema, so determinism includes it. The v3-compat
block is stored at full float precision (bit-identity requirement).

Per-beat series (length = len(beatgrid), v3 beat-window semantics A7):

| Field | What it is | Primary requirements |
|---|---|---|
| `band_db` ×6: sub 20–60, bass 60–150, lowmid 150–500, mid 500–2000, high 2000–6000, air 6000–11025 | mean absolute dB per beat per band | R1 R6 R9 R10 R11 R14 R15 |
| `band_sub4` ×6 | 4 quarter-beat mean-dB slots per beat per band | R3 R4 R7 R16 R20 |
| `growl_band_db` + `growl_band_sub4` | harmonic-component 60–500 Hz level (beat + quarter-beat) | R7 R13 |
| `growl_band_frames` (+ `frame_hop_s`) | the same harmonic 60–500 Hz envelope at full frame rate (43 Hz), 0.1 dB — future wobble/modulation derivations run from cache (review-gate change 2) | §4.9 provisioning |
| `sustain_mid_db` (200–2000 H), `sustain_high_db` (2000–8000 H) | harmonic ("sustained/tonal") levels | R2 R7 R13 |
| `growl_flatness` | spectral flatness of the harmonic 500–4000 band — distortion/growl timbre without kick pollution | R3 R13 (Appendix B round 2) |
| `centroid_hz` | brightness | R2 R10 R13 |
| `perc_low/mid/high/full` | HPSS percussive energy fraction per macro band (low <200, mid 200–2000, high >2000) | R1 R2 R7 R12 R16 |
| `attack_db`, `attack_low_db` | max positive frame-to-frame dB rise within beat (full band; 20–200 band) | R3 R4 R16 R17 |
| `onset_density`, `onset_density_midhigh` | onset counts per beat — superflux `max_size=3` on percussive mel (≥500 Hz variant for rolls), peak-picked on the raw dB-flux scale (`normalize=False`, delta=1.5 — the corpus-absolute rule applied to onsets; Appendix C) | R1 R3 R5 R9 |
| `fluxsum_midhigh` | per-beat sum of the ≥500 Hz percussive superflux envelope — threshold-free roll/crescendo energy; R5's acceleration = its trailing slope | R5 R9 |
| `full_db` | mean full-band dB per beat | R6 R14 R15 |
| v3-compat block: the 8 v3 envelope fields | bit-identical values (A20) | zero-behavior-change; grit + punch axes |

Beat aggregation rule for every dB series (incl. sub4 slots): **arithmetic mean of linear
power over the frames in the window, then dB** — energy semantics (v3's), not a log-domain
mean (Appendix C stability finding). Frame-native measures keep their own aggregation:
attack = max positive frame-to-frame dB rise in the beat; flatness/centroid = mean of frame
values (v3-identical for flatness).

Per-track summary scalars (stored in the entry — the Feature 1 identity freeze source, F-9):

- The four axes, exact formulas pinned in code: `grit` = median of the compat block's
  `spectral_flatness_envelope` and `punch` = CV (std/mean) of the compat block's
  `kick_envelope` — computed from bit-identical v3 series, so they provably inherit v3's
  measured stability (0.922 / 0.902); `bass` = fraction of beats with `sub_db` above the
  pinned absolute threshold; `drama` = p95 − p5 of `full_db` — these two are new-semantics
  (absolute dB) and carry their own stability gate: even/odd Spearman on the BY GENRE corpus
  ≥ the v3 band (smoke: 0.906 / 0.967 at n=36; corpus-scale numbers in §7).
- New character scalars (threshold-free only, per review-gate change 4): `loudness_ref_db`
  (p95 full_db), `brightness_med`, `growl_timbre_p90` (growl_flatness p90),
  `attack_low_p90`, `onset_mh_p90`, `duration_s`, `n_beats`. Threshold-dependent scalars
  (the `bass` duty axis, sub-weight) are **derived at load** by `spectral_profile` from the
  stored raw series — never persisted, so threshold re-tuning can never desynchronize
  cache entries (F-9 hazard closed).

Estimated entry size: ~48 rounded values/beat + 8 full-precision compat values/beat ≈
~240 KB at the median 514 beats → **~165 MB for the 686-track library** (measured actuals in
§7; v3 baseline 43 MB/476). Acceptable on this machine; rounding widths are the knob if it
ever matters.

### 4.4 Derived views (computed at load; pure stdlib, no numpy)

`spectral_profile.py` (new module) exposes:
- **v3-compat view**: a `SpectralFeatures` built from the compat block — feeds
  `anlz_reader`'s scorer unchanged.
- **The silence primitive (P-2/F-16)**: `empty_floor_runs()` — per-beat `bottom_gone`
  (sub_db AND bass_db below calibrated thresholds) merged into runs; `true_silence` (full_db
  below threshold) separated from *musical* empty floor. One function, three consumers
  (texture darkness, blackout sizing, landing eligibility).
- **Per-beat texture descriptors**: kick-prominence (R12), thick/thin via band occupancy
  (R11), bright/dark tilt (R10), stab vs sustain via within-beat swing + attack (R4/R7),
  roll flag + acceleration (R5), growl (flat_midH × midH_db) and bright-whir (centroid ×
  highH_db × low flat_midH × low perc) classes (R13).
- **Drop-window character vector** (R9): given a drop beat, the descriptor dict the
  drop-type classifier (Feature 2 spec) consumes; neutral-on-thin-data per F-11 is the
  consumer's rule, fed by an explicit `coverage` count.
- **Calibration constants**: one `SPECTRAL_V4_CALIBRATION` mapping with every threshold,
  each carrying its provenance (BY GENRE corpus percentile, 2026-07-05). Constants are
  consumer-retunable without re-extraction (principle 2).

### 4.5 Module layout & seam changes

- `audio_spectral_features.py`: internal refactor `_extract_v3_features(y, sr, grid)` (the
  existing math, unchanged); public `extract_spectral_features` (v3) delegates to it —
  byte-identical behavior; new `extract_spectral_features_v4()` decodes once and computes
  compat block (same helper) + v4 measurements from one STFT. New frozen dataclass
  `SpectralFeaturesV4` exposing the 8 v3 attribute names (compat) + v4 fields.
- `spectral_cache.py`: `get_cached_v4` / `put_cached_v4` / `evict_stale_v4` operating on
  `spectral_cache/v4/`; same atomic-write discipline (A15), same key function (A16). v3
  functions untouched. (v3 `evict_stale` globs only the top-level `*.json` — verified it
  cannot see the v4 subdirectory.)
- `spectral_profile.py`: new, pure stdlib (importable and testable without numpy/librosa —
  CI 3.11 safe).
- `tools/spectral_sweep.py`: offline sweep CLI — enumerates tracks from the Rekordbox DB
  (the `filepath_resolver` pyrekordbox pattern), resolves ANLZ beatgrids via
  `read_anlz_drops`, extracts v4 (skips fresh cache hits), reports coverage/duration/size.
  `--jobs N` process pool (spawn; `OMP_NUM_THREADS=1` per worker — research §9). Run under
  `caffeinate -i` (documented in the tool's usage text).
- `state_manager.py` seam (`_runtime_spectral_features`): read order v4-cache → v3-cache
  (legacy, read-only) → extract v4 + write v4 cache → return the v3-compat view in every
  path. The scorer receives identical numbers in all three paths (§6 proof). Flag gating
  unchanged (A19).
- `__main__.py`: the existing flag-gated eviction worker additionally calls
  `evict_stale_v4()` — same thread, same flags, no new runtime surface.

### 4.6 Budget (measured basis, Appendix A/B)

- Per track ≈ 11.5–12.5 s (decode 2.3 + STFT 0.10 + mel 0.02 + HPSS 8.5 + v3-compat
  recompute ≈ 0.4 + v4 aggregation ≈ 0.5). At-load extraction stays in the background ANLZ
  worker (seconds-range requirement: met; and after the sweep, load-time extraction only
  ever happens for brand-new files).
- Honest timing note: on a cache-miss load (with the spectral flags on), the ANLZ_DATA
  event already waits for extraction today (`state_manager.py:207-250` computes the energy
  shadow from the features before posting); v4 moves that first-play-only wait from ~3–4 s
  to ~12 s. Values are identical; only the arrival time of the background enrichment on a
  never-before-analyzed track shifts. The whole-library sweep removes the case for every
  existing track; a brand-new purchase pays it once. Consumers of ANLZ_DATA are async
  enrichment consumers by design (they tolerate late/absent data — that is the existing v3
  contract).
- Whole-library sweep: 686 tracks ≈ 2.2 h serial, ≈ 40 min at `--jobs 4` — the overnight
  requirement is met with ~10× margin either way.
- Cache: ~165 MB estimate for the full library (measured in §7).

### 4.7 Coexistence & cutover

v3 entries: never read-modified or deleted by v4 code; v3 eviction continues to govern only
top-level v3 files (verified glob scope). Runtime prefers v4, falls back to reading v3 for
tracks the sweep hasn't covered (pre-sweep world), and extracts v4 on full miss. After this
one-shot's sweep, every on-disk track has a v4 entry, so the v3 fallback is a vestigial
safety path. Deleting v3 files is a later operator-approved cleanup, deliberately not part
of this build.

### 4.8 Failure modes

Missing librosa/numpy → `extract_spectral_features_v4` returns None → ANLZ-only tier
(unchanged v3 contract). Decode error / <2 beats / corrupt or stale cache → None → same.
Derived classes on absent data → absent (no darkness, no growl, no roll — never a false
event). m4a (≤8 files) decodes only if an audioread fallback exists; otherwise those tracks
live at the ANLZ tier like any decode failure.

### 4.9 Explicitly cut or deferred (honest rulings)

- **Per-beat LFO wobble rate/depth: CUT from shipped classes, storage-provisioned.**
  Round-1/round-2 prototyping (Appendix B) showed naive and beat-excluded modulation
  measures both fail to separate wobble from offbeat-bass/kick pulsing on real tracks — and
  this catalog's dubstep is stab/scream-dominated (briddim/tearout era), so a wobble class
  has almost no labeled positive examples to calibrate against. `growl_band_frames` (the
  frame-rate 43 Hz harmonic low-mid envelope — review-gate change 2; quarter-beat slots
  alone cannot resolve 1/8–1/16-note LFO rates) is stored precisely so a future wobble
  measure can be derived from cache without re-extraction. The missing experiment, exactly:
  a labeled set of known LFO-wobble drops (operator-supplied or new tracks), then a
  duty-gated modulation-spectrum measure over `growl_band_frames` validated against it.
  Until then: `unproven`, not shipped.
- **Roughness (20–150 Hz modulation)**: unreachable at 43 Hz frame rate (Nyquist 21.5 Hz);
  the distortion axis (`flat_midH`) is the stand-in. Would require a dedicated band-passed
  waveform envelope pass (Hilbert) — priced but not needed by any current requirement.
- **Stem-level percussion isolation**: out of scope; HPSS macro-band ratios are the honest
  full-mix approximation.
- **K-weighted LUFS loudness normalization**: rejected as unnecessary — measured master
  spread at drop windows is ~2.5 dB (Appendix B), well within threshold tolerances;
  `loudness_ref_db` (p95 full_db) is stored per track so any consumer needing
  loudness-relative reads has the reference without a new dependency.

### 4.10 Adversarial review gate — result and folded changes

Fresh-context Fable-tier adversarial review ran 2026-07-05 against this design + the prompt +
the code at `2945c52`. **Verdict: APPROVE-WITH-REQUIRED-CHANGES** — architecture confirmed
(absolute dB + within-beat shape + HPSS harmonic measures as the answer to v3's blindnesses;
subdirectory coexistence verified safe; containment clean; compat-view seam correct for the
duck-typed scorer). Every finding adopted:

1. **Bit-identity carve-out (was a latent contradiction):** the v3-compat block is exempt
   from the one-STFT principle. `_extract_v3_features(y, sr, grid)` keeps v3's exact three
   librosa calls verbatim — mel with `fmax=12000.0`, `onset_strength(y=…)` and
   `spectral_flatness(y=…)` with their own internal STFTs, the double normalization, the
   `<2 beats` precondition, and the exact `librosa.load(str(path), sr=22050, mono=True)`
   decode. The bit-identity check ships as a retained, locally-runnable test (skipped on CI
   without librosa), not a one-time proof.
2. **Real wobble provisioning:** quarter-beat slots cannot carry 1/8–1/16-note LFO rates
   (Nyquist ≈ 4.7 Hz at 140 BPM). v4 stores the **frame-rate growl-band harmonic envelope**
   (`growl_band_frames`, 0.1 dB rounding, with hop metadata; ~55–65 KB/track ≈ +40 MB
   library) so any future wobble/roughness-adjacent derivation runs from cache. The wobble
   *class* stays cut (§4.9).
3. **Key parity proven, not assumed:** the sweep resolves audio paths from the same DB field
   the runtime resolver uses (`DjmdContent.FolderPath`) and beatgrids via the same
   `read_anlz_drops` (whose `_candidate_anlz_paths` expands any sibling to the same ordered
   set); a parity check on real tracks (DB-derived path vs each sibling candidate →
   identical fingerprints) is part of §6; and `_runtime_spectral_features` logs its path
   (v4-hit / v3-fallback / fresh-extract) so silent non-convergence is observable.
4. **No threshold-dependent stored scalars:** the `bass` axis and `sub_weight_med` are
   derived at load from the stored raw series by `spectral_profile` (pure functions);
   stored scalars are threshold-free only (grit, punch, drama, brightness_med,
   loudness_ref_db, growl_timbre_p90, attack_low_p90, onset_mh_p90). Identity freezing
   stays the consumer's job (review F-9 freeze-and-store), fed by these measurements.
5. **At-load resource guard:** a process-wide single-flight lock (one v4 extraction at a
   time — two decks can load simultaneously), plus a duration cap: tracks whose beatgrid
   spans longer than the cap take the legacy v3 extraction path at load exactly as today
   (zero behavior change for the pathological hour-long-file case) and leave v4 to the
   sweep. Measured peak RSS reported in §4.6.
6. **Uncontaminated final proof:** rounds 1–2 iterated features on the same 36 tracks, so
   the final genre proof (§6) re-runs on the disjoint remainder of the six BY GENRE
   playlists (held-out tracks the design never saw), and the bottom-gone threshold is
   re-validated against corpus-scale sub-band bimodality before `empty_floor_runs()` ships
   as the shared primitive.
7. **Pinned details:** `onset_density` base band = full percussive mel (20–11025);
   the v4 dir is derived `_cache_dir() / "v4"` so `RBSS_SPECTRAL_CACHE_DIR` moves both
   (test isolation intact); scalar rounding pinned (dB 0.1, ratios/CV 4 decimals, Hz 1);
   `get_cached_v4` validates every series length against the beat count before returning;
   v4 extraction keeps v3's catch-all-Exception→None discipline; the `spectral_analysis`
   change contract lands with the build.
8. Eviction convention documented in code: every future schema gets its own subdirectory;
   eviction never crosses versions (no A17 recurrence at v5).
9. Stability contingency pinned: if `bass`/`drama` corpus-scale stability lands below the
   v3 band, `bass` recomputes from the compat `sub_bass_envelope` duty (v3 semantics,
   known-stable) — the absolute-dB series stays stored either way.
10. Band-name hygiene: one `BAND_RANGES` table in code is the single source; harmonic aux
    series are role-named (`growl_band_*` = H 60–500, `growl_flatness` = H-flatness
    500–4000, `sustain_mid_db` = H 200–2000, `sustain_high_db` = H 2000–8000).
11. Sweep memory priced: one worker's peak RSS measured before choosing the default
    `--jobs` (machine RAM checked); overnight margin absorbs a conservative default.
12. Zero-behavior-change scope stated precisely: v4's extra at-load seconds delay only the
    energy-shadow *diagnostic* upgrade (drop/buildup markers arrive from the fast ANLZ
    worker, verified `state_manager.py:1835-1842,1237`; the shadow's sole runtime consumer
    is a log line, `state_manager.py:4155-4169`); a track where v4 fails but v3 would have
    succeeded degrades the shadow source label only (log-visible, light-invisible).

## 5. Requirements coverage table

| ID | Served by (v4 measurements / views) | Status |
|---|---|---|
| R1 percussion distinguished | `perc_low/mid/high/full`, `onset_density*`, `attack_*` | measured round 1; proof §6 |
| R2 euphoric synth captured | `midH_db`+`highH_db` sustained runs, `centroid_hz`, low `flat_midH`, low `perc_full` | round 2 validation; proof §6 |
| R3 dubstep jab/scratch outline | `attack_db`, `onset_density_midhigh`, `flat_midH`, `high_db`/`air_db`, `band_sub4` swing | round 1 signal confirmed; proof §6 |
| R4 bass-house stab distinct | `attack_low_db`, low-band `band_sub4` swing, `perc_low`, `onset_density` | round 1 signal confirmed; proof §6 |
| R5 snare rolls + acceleration | `onset_density_midhigh` + beat-to-beat rise (view) | round 2 validation; proof §6 |
| R6 emptiness detected & sized | `sub_db`+`bass_db` bottom-gone runs, `full_db` true-silence split (the P-2 primitive) | validated on the ear-validated reference track (App. B) |
| R7 sustained horn ≠ hits | `growlH_db` duty + `band_sub4` flatness-of-shape + `perc_low` | proof §6 |
| R8 identity axes stability | stored scalars `grit/punch/bass/drama` (formulas §4.3) | stability gate in §7 (≥ v3's 0.902–0.957) |
| R9 drop-window genre separation | drop-window character vector (view over band/attack/onset/timbre series) | 53.3% LOO round 1 → final proof §6 |
| R10 bright/dark tilt | `centroid_hz`, `high_db`−`low` tilt | trivially derived; §6 |
| R11 thick/thin | band occupancy count + `full_db` | derived view; §6 |
| R12 kick-prominence | `attack_low_db`, `perc_low`, `bass_db` pattern | derived view; §6 |
| R13 growl vs whir | `flat_midH` × `midH_db` (growl); `centroid` × `highH_db` × low `flat_midH` (whir) | round 2 validation; §6 |
| R14 shared silence primitive | one `empty_floor_runs()` view, three consumers | design §4.4 |
| R15 energy arc vs ANLZ structure | `full_db`, band series per beat | inherent; §6 outlines |
| R16 attack shape / body language | `attack_*`, `band_sub4` swing, `perc_*` | round 1 signal; §6 |
| R17 accent discipline inputs | scalars `punch`, `grit`, `attack_low_p90` | stored scalars |
| R18 corpus-absolute calibration | `SPECTRAL_V4_CALIBRATION` from BY GENRE stats only | §7 |
| R19 determinism/degrade/budget | design §4.1/4.6/4.8 | proofs §6/§7 |
| R20 off-beat activity visibility | `band_sub4` (high/air bands: slots 2–3 vs 0–1) | derived view; §6 |
| — LFO wobble rate | **unproven — cut, storage-provisioned** (§4.9) | honest ruling |
| — 20–150 Hz roughness | **unreachable at v4 frame rate** (§4.9) | honest ruling |

## 6. Proofs on the operator's music

All **confirmed (measured this session)** unless labeled otherwise.

### 6.1 Zero-behavior-change proofs

- **v3-compat bit-identity on real audio, three formats**: v4's compat block equals the v3
  extractor exactly (all 8 envelope fields, `==` on full-precision tuples) on Odd Mob —
  "Dancing Boys, Dancing Girls" (wav, 480 beats), Odd Mob — "CUT TF UP" (mp3, 513 beats),
  Odd Mob OMNOM — "Losing Control" (flac, 592 beats). The smart-drop scorer receives
  identical numbers through every seam path.
- **The bit-identity gate is a retained test, not a one-time run**
  (`tests/test_audio_spectral_features.py::test_optional_real_audio_bit_identity`,
  env-gated on `RBSS_SPECTRAL_FIXTURE_DIR`, skips cleanly on CI): exercised end-to-end this
  session against real audio — PASS. Any future refactor that breaks compat bit-identity
  fails this test locally.
- **Structural compat test with fake deps** runs everywhere (CI-safe), asserting
  v4-compat == v3 output on the same injected inputs.
- **Suite**: 3,251 tests (was 3,226), 1 failure — `test_laser_color_engine.
  LaserColorMapperTests.test_loader_ships_disabled_with_calibrated_fixed_band_values`,
  **pre-existing at baseline `2945c52` before any edit of this session** (laser color
  engine config loader; unrelated subsystem, not touched). Zero new failures. Three hard
  docs checks: all pass.

### 6.2 Determinism

- Same file + same beatgrid → `SpectralFeaturesV4` dataclass equality (every rounded series,
  sub4 slot, frame envelope, and scalar) across repeated runs, on wav, mp3, and flac real
  tracks — **confirmed**. All operations used are documented-deterministic (librosa
  hpss/onset/spectral/load; no RNG anywhere in the path — research §8, verified-primary-source).

### 6.3 Runtime↔sweep cache-key parity (review-gate change 3)

- `tools/spectral_sweep.py --verify 60`: for 60 real tracks, every ANLZ sibling candidate
  (.DAT/.EXT/.2EX) yields the identical beatgrid fingerprint → identical cache keys from
  the DB-derived path (sweep) and any runtime-provided sibling path — **60/60 consistent**.
  Tracks with no beatgrid at all (FX one-shots: scratch/cymbal samples) produce no key on
  either side — consistent absence. The runtime seam additionally logs `[SM] spectral-path`
  whenever it takes a non-v4-hit path, so silent non-convergence is observable in the log.
- Audio-path parity holds by construction: both sides read `DjmdContent.FolderPath` and the
  key uses `os.path.realpath` of it.

### 6.4 Budget measurements

- Per-track v4 extraction on this machine: 8.1–9.8 s measured across the three formats
  (v3 alone: 0.7–2.2 s). At-load extraction runs in the existing background ANLZ worker,
  single-flight-locked, with grids >15 min taking the legacy v3 path (§4.10 change 5).
- Peak RSS: ≤ ~1.0 GB for a process that ran three consecutive v4 extractions plus three
  v3 extractions (upper bound on a single extraction's footprint). With the sweep default
  `--jobs 2` on this 8 GB machine: ~2 GB worst case — sized deliberately (§4.10 change 11).
- m4a decodes via the installed audioread fallback (deprecation-warned by librosa;
  works today — observed decoding during the sweep). If that fallback ever disappears,
  those ≤8 files degrade to the ANLZ-only tier per A12.

### 6.5 Corpus proofs — all computed from the shipped extractor's cache entries via the
shipped `spectral_profile` code paths (219 BY GENRE tracks with v4 entries; the RAP playlist
excluded per the track-selection rule)

**Corpus-scale calibration (review-gate change 6b).** Over ~112k beats of labeled EDM:
the sub-band dB distribution is decisively bimodal — main mass at 25–36 dB (sub present),
long sparse tail below, and the bottom-gone threshold (5 dB) sits in a genuine density
valley (only 4.7% of beats within 8 dB below it, 5.7% within 8 dB above). The single-track
ILL validation generalizes. True-silence threshold (−30 dB full-band) lies below the corpus
p1 (−26) — only literal silence crosses it. Growl threshold 0.25 ≈ corpus p78 of harmonic
mid-band flatness (a top-quartile distortion gate); roll threshold 3/beat > corpus p90
(rolls are rare, as they should be). Mastering spread: per-track `loudness_ref_db` p5–p95 =
15.3–19.3 dB — a 4 dB corpus spread, comfortably inside threshold tolerances (the
corpus-absolute rule is sound).

**Identity-axes stability at corpus scale (n=219, even/odd-beat Spearman)** — the F-9 gate:
**grit 0.929, punch 0.935, bass 0.967, drama 0.928** — all four inside/above the v3 band
(0.902–0.957). The prototype's punch failure (0.769) was fixed by the compat-block CV
formula, confirmed here. The stability contingency (§4.10 change 9) was not needed.

**Held-out genre-discrimination proof (review-gate change 6a).** 1,266 drop windows from
the six operator-named playlists; **1,086 of them from tracks the design process never
touched**. Nearest-centroid, leave-one-track-out: **58.7% vs 16.7% chance (3.5×)** on the
held-out windows — *higher* than the design-set number (53.1%), so the features generalize
rather than overfit. Per-genre: HARD TECHNO 76%, DUBSTEP 71%, ODDMOB 65%, BASS HOUSE 54%,
SYNTH HOUSE 48%, ISOXO 29% — every genre beats chance 2–4.5×, and the confusion structure
is musically honest (ISOXO bleeds mostly into DUBSTEP: the catalog's ISOxo-era
trap/dubstep hybridity; ODDMOB into the other ~130 BPM house styles). The operator's own
descriptors are the measurable medians (held-out windows): BASS HOUSE = highest low-band
attack (11.4 dB p90) and within-beat swing (14.5 dB) — *stabby, jumpy*; DUBSTEP = highest
mid/high/air (12.3/6.6/1.7 dB) with top-quartile growl flatness — *scratchy, jabby*;
HARD TECHNO = most bass (27.2 dB), darkest top (air −4.2 dB), 155 BPM — *pounding,
driving*; ODDMOB = strong sub with the *lowest* mids (5.6 dB) — *bassy sustains, dark*;
SYNTH HOUSE = cleanest harmonic timbre (flatness 0.12) — *euphoric sustain*; ISOXO = heavy
consistent sub with sparse low-band attacks — *heavy but sparse*.

**Within-dubstep drop characters (the operator's specific dubstep bar).** Per-drop vectors
separate drop characters across and even within tracks: Ray Volpe — DROP EM's four drops
span attack 2.7→16.1 dB and growl-flatness 0.30→0.42 (its growliest drop is measurably its
own thing); Crankdat — STFU's seven drops cluster tightly (0.24–0.27 flatness, ~2.2
onsets/beat — consistent stutter character); SPITFIRE reads cleaner/brighter; the trap-edit
end (Fuckin' Problems x Type Shit) reads low-flatness sparse. Distinct drop characters are
distinguishable in v4 output — requirement met.

**Timestamped event outlines (the operator scrub test)** — final outlines from shipped
code, for six named tracks (full listings preserved in the session's validation log;
representative excerpts):

- *Kai Wachi — ILL (DUBSTEP, 140):* intro riff gaps 0:00–0:16 (4–5-beat empty floors);
  growl sections 0:30/0:33; percussion roll ×8 at 0:37.9 into the BUILDUP at 0:41.7; empty
  floor through 0:43.0–0:46.9 ending exactly at the DROP (beat 109); 2-beat vacuum at
  1:50.7 before the 1:52.0 DROP; growl blocks through both drop phrases; 1:44.3 growl ×15
  through the buildup; **2:19.4 true silence ×14 (literal end-of-file)** — kind-split from
  musical empty floor.
- *Knock2 — crank the bass (BASS HOUSE, 132):* growl bass tease 0:35.9/0:39.1 before the
  0:43.6 DROP with a roll ×3 riding in at 0:41.8; sustained-synth reads on the intro/mid
  vocal-pad sections; 0:41.8 2-beat pre-drop vacuum; 34-beat outro empty floor at 3:12.7.
- *ISOxo — just let da muzik TALK! (ISOXO, 140):* the trap verse signature — alternating
  6–7-beat empty floors every other bar from 0:06 to 0:37; a 24-beat empty floor at 0:37.3
  carrying a percussion roll ×10 (0:38.6) into the 0:47.6 DROP; screech-lead growl blocks
  after both drops (×21 at 1:03.9, ×35 at 1:28.3).
- *Pitch Mad Attak — Wanna Be (HARD TECHNO, 160):* sustained-synth reads throughout (the
  rave hook — the class-semantics ruling in Appendix C); percussion roll ×14 at 2:48.0
  through the buildup into the 3:00.0 DROP; sustained bass floor ×8 blocks in the intro
  and mid-section; end-of-file true silence.
- *it's murph — Lift Me Up (SYNTH HOUSE, 132):* solo-kick intro reads as heavy low-end
  stabs ×32; **DROP at 0:29.1 opens a sustained-synth run ×77 beats — the euphoric wall
  captured and outlined**; breakdown at 0:58.2 with sustained bass floor and a second
  sustained-synth block ×63.
- *Odd Mob — CUT TF UP (ODDMOB, 136):* heavy low-end stab blocks through the intro riff
  (0:00–0:13, 5–6-beat runs) and again ×14 at 0:42.8 into the buildup; **a 15-beat empty
  floor at 0:49.4 ending exactly at the 0:56.5 DROP** (the blackout sizer's input); a
  sustained-synth block ×28 after the 1:10.6 DROP and ×76 through the 1:52.5 buildup
  (the track's melodic mid-section); stabs ×35 at 2:15.5 driving into the 2:21.2 buildup;
  percussion rolls at 2:38.0/3:11.5 near the late drops.

**Operator anchor tracks** (the two reference drops from the design sessions; outlines from
shipped code):

- *it's murph — Chemicals (Feat. Nat Slater) (Extended) (SYNTH HOUSE, 132) — THE euphoric
  synth reference:* the analysis captures it exactly — **sustained-synth blocks of ×138
  beats (0:48.6 through the mid-build) and ×189 beats (2:44.1 through the long breakdown
  build)**, a ×42 block after the 2:15.5 drop and a ×36 block landing at the 4:36.8 drop;
  snare rolls at 2:02.7/2:17.7/4:00.5/4:13.6 riding the builds; solo-kick intro reads as
  low-end stabs. Scrub 0:48.6 and 2:44.1 to hear the pads the class is naming.
- *Odd Mob, Walker, Royce — Can't Say Nah (ODDMOB, 130) — THE bassy-sustain reference:*
  the halftime mid-breakdown (2:13–2:33) shows the alternating empty-floor pattern ending
  in a 26-beat empty floor into the 2:42.6 drop. At the drops themselves the character
  lives in the **drop-window vector**, compared here against a bass-house stab reference
  (Nikko — Gimme That): Can't Say Nah drop\@128: sub 31.2 dB, within-beat low swing 9.2 dB,
  mid 3.1 dB (dark), vs Gimme That drop\@101/229: swing 12.6 dB, mid 11+ dB (bright),
  attack p90 up to 35.8 dB — *held dark bass weight vs bright jumpy stabs*, measurably.
  An honest class-semantics note recorded: the per-beat `sustained_bass` class (swing
  < 4.5 dB) names only true continuous drones — a four-on-floor kick pumps the bass band
  ~9 dB every beat, so "bassy sustain at the drop" in house music is a *relative,
  window-level* property served by the vector (exactly where drop-type selection reads it,
  review 2.9), not a per-beat absolute.

Every event above is a description; ANLZ markers remain the only structural triggers.

## 7. Whole-library sweep results (2026-07-05, `caffeinate -i python3 tools/spectral_sweep.py --jobs 2`)

- **Scope**: 686 on-disk active tracks (whole library — every track the operator can play,
  regardless of playlist filing, per the track-selection rule).
- **Coverage**: **666 extracted OK (100% of decodable tracks with beatgrids)**; 19 `no_grid`
  (FX one-shots — scratch noises, cymbals, airhorns with no ANLZ beatgrid; correctly absent
  on both runtime and sweep sides); 1 `extract_failed` — GRiZ — "I Remember (flip)" flac,
  which **also fails v3 extraction identically** (undecodable file; lives at the ANLZ-only
  tier under both schemas — zero behavior change holds exactly).
- **Duration**: **48.6 minutes** wall-clock at `--jobs 2` on the 8 GB MacBook Air — the
  overnight budget is met with ~10× margin. Slowest single track: 23.7 s (RÜFÜS DU SOL —
  Innerbloom, a 9+ minute file).
- **Cache size**: **203.5 MB / 666 entries** (~306 KB median track) under
  `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/`. Above the design estimate
  (~165 MB) by ~23% — the full-precision compat block plus the frame-rate growl envelope
  cost more than the back-of-envelope; acceptable (v3 baseline 43 MB stays untouched
  alongside). Startup eviction now parses ~204 MB of JSON in its existing background
  thread — measured acceptable, never on the push loop.
- **m4a**: decoded via the installed audioread fallback during the sweep (deprecation-
  warned; works today). If it ever disappears, those ≤8 tracks degrade to the ANLZ tier.
- Calibration, stability, and discrimination numbers from these entries: §6.5.

## 7b. Claim-label index (load-bearing claims of this report)

- v3 audit rulings (A1–A20) — **confirmed** (code read in full at `2945c52`; file:line cited
  per ruling).
- Measured facts reused from the v2 record (stability band, normalization destruction,
  growl/bright non-separability, coverage counts, PSSI stats, empty-floor ear validation) —
  **confirmed as the record's named measured facts** (not re-derived, per prompt).
- librosa/scipy/MIR method claims — **confirmed (verified-primary-source)** where labeled in
  Appendices B/C and §4 (research notes with URLs in the session log); production-lore items
  (LFO-rate ranges, EDM mastering levels) — **assumed**, used only for non-load-bearing
  framing.
- v3-compat bit-identity (wav/mp3/flac real tracks + retained local test) — **confirmed
  (measured §6.1)**.
- v4 determinism run-over-run — **confirmed (measured §6.2)**.
- Runtime↔sweep key parity — **confirmed (measured 60/60, §6.3)**; residual risk covered by
  the `[SM] spectral-path` observability log.
- Identity-axes corpus stability (grit 0.929 / punch 0.935 / bass 0.967 / drama 0.928,
  n=219) — **confirmed (measured §6.5)**.
- Held-out genre discrimination 58.7% vs 16.7% chance (1,086 held-out windows) —
  **confirmed (measured §6.5)**.
- Bottom-gone/silence calibration at corpus scale — **confirmed (measured §6.5)**.
- Sweep coverage/duration/size — **confirmed (measured §7)**.
- Per-beat LFO wobble rate/depth as a shipped class — **unproven → cut** (§4.9; storage-
  provisioned via `growl_band_frames`; missing experiment named).
- 20–150 Hz roughness — **unreachable** at the v4 frame rate (§4.9).
- Perceptual/lighting-treatment claims (what reads "euphoric", what seasoning fits a class)
  — **assumed**, deliberately left to consumers + the operator's live/scrub gates.
- Suite result — **confirmed**: 3,251 tests, zero new failures; the single failure
  (`test_laser_color_engine…fixed_band_values`) is **pre-existing at baseline `2945c52`**
  (unrelated subsystem, untouched by this build).

## 8. Open questions for Brandon (taste calls only — defaults chosen, veto if wrong)

1. **How long may a pre-drop blackout get?** The analysis now measures each drop's real
   empty-floor gap (e.g. ILL has a 12-beat one). The v2 design caps the blackout at ~4 bars
   (16 beats ≈ 7 s at 140 BPM). **Default: the 16-beat cap stands** — a 12-beat measured gap
   means up to ~5 s of true black in the living room. Veto with a shorter cap if that ever
   feels too long; it is one constant, no re-analysis.
2. **The scrub test is your veto surface.** §6.5 lists timestamped events for six named
   tracks. If any listed event reads wrong when you scrub there in Rekordbox, say which
   timestamp — every class threshold is a code constant, re-tunable in minutes without
   re-analyzing the library. **Default: calibrated thresholds ship as-is.**
3. **Classic LFO-wobble detection: first labeled positive received** — the operator named
   Billie Eilish — LUNCH (Phrva Flip) post-build, and the wobble signature derived cleanly
   from the already-stored cache data (Appendix D item 2 — no re-extraction, as designed).
   **Default: the class still ships only after 2–3 more labeled wobble tracks confirm the
   thresholds generalize** — name them whenever; each is a five-minute cache read.

---

## Appendix A — corpus recon (2026-07-05, this session, read-only)

- Rekordbox DB opened exactly as `filepath_resolver.py:281-283` does (pyrekordbox
  `Rekordbox6Database`, `unlock=True`). Two playlist nodes named "BY GENRE" exist —
  **confirmed**; the correct one (ID 666898931) is the folder whose 25 children are the
  per-genre playlists, including every genre the operator's map names: ODDMOB (66 tracks on
  disk), MODERN TECH HOUSE (64), TECH HOUSE (56), ISOXO (52), POP BASS HOUSE (39), BASS HOUSE
  (36), BASS (34), MAINSTAGE (29), UKG (26), EXPERTS ONLY (25), DUBSTEP (24), HARD TECHNO
  (23), GROOVE HOUSE (21), SYNTH HOUSE (19), TRAPSTEP (14), DEEP HOUSE (13), DRUMCODE (10),
  SKRILLEX (9), plus smaller lists. RAP (1 track) exists in the folder and is excluded from
  all sampling/calibration per the track-selection rule. The other BY GENRE node (13 children,
  incl. HIP HOP / POP BANG / ACAPELLAS) is not used.
- ANLZ coverage: every BY GENRE playlist row resolves to an ANLZ set on disk
  (`~/Library/Pioneer/rekordbox/share` + `DjmdContent.AnalysisDataPath`) — **confirmed** by
  existence check on all rows.
- Whole-library sweep scope: 1,007 active DB rows, **686 with the audio file on disk**
  (formats: wav 355, mp3 215, flac 96, aiff/aif 12, m4a 8) — **confirmed by filesystem check**.
  m4a decode depends on an audioread fallback; if absent, those ≤8 tracks degrade to the
  ANLZ-only tier exactly like any decode failure (A12).
- Pipeline derisk (one ODDMOB track, Luke Dean & Omar+ — "Make Believe (Twin Diplomacy
  Extended Remix)", 130 BPM, 253 s wav): ANLZ parse 0.37 s → 9 drops / 4 buildups /
  1 breakdown / mood 1 / 549-beat grid; decode 2.3 s; STFT 0.10 s; mel 0.02 s; HPSS 8.5 s;
  onset 0.01 s — **confirmed (measured this session)**. HPSS dominates the budget; sizing in §4.

## Appendix B — prototype round 1 (36 sample tracks, 6 per operator genre, read-only)

Candidate v4 measurements were extracted for 36 BY GENRE tracks (6 each from ODDMOB,
BASS HOUSE, DUBSTEP, ISOXO, HARD TECHNO, SYNTH HOUSE — titles listed in §6 when the proofs
land). Findings that shaped the v4 design:

**What worked immediately (confirmed by measurement this session):**
- **Absolute-dB cross-band structure discriminates the operator's genres** in exactly his
  words: at drop windows, ISOXO (trap) shows the heaviest and most consistent sub floor
  (sub p10 28 dB — 808 weight) with the *sparsest* low-band attacks (halftime); HARD TECHNO
  is the bass-heaviest (24.6 dB median) and darkest (centroid 341 Hz, air −9.4 dB);
  DUBSTEP is the brightest/most mid-heavy (mid 11.9 dB, high 6.6 dB, air 1.6 dB, flatness
  0.06 — "scratchy"); BASS HOUSE and ODDMOB both show strong within-beat low-band swing and
  attack (stab/punch), with BASS HOUSE brighter in mid/high.
- **Mastering spread is small enough for corpus-absolute thresholds**: median drop-window
  full-band level sits within ~2.5 dB across all six genres (14.7–17.1 dB) — the corpus-
  absolute calibration rule (review 4.5) is viable on raw fixed-reference dB.
- **The bottom-gone primitive works on absolute dB, validated on the ear-validated reference
  track** (Kai Wachi — ILL, DUBSTEP): sub-band dB is strongly bimodal (present ≈ 20–35 dB,
  gone ≲ 5 dB with a sparse gap between); a sub<5 dB rule recovers: the 12-beat empty floor
  ending exactly at drop beat 109; a 4-beat vacuum immediately before drop 261 (the
  operator's "4 silent beats → 4-beat blackout" example, now measurable); a 3-beat gap
  before drop 141; and the 2:18–2:25 run is literal end-of-file silence (full-band −80 dB),
  cleanly separable from *musical* empty floor (full-band +1..+11 dB, other instruments
  playing) — the same distinction the 2026-07-05 ear test established.
- **First genre-discrimination pass: 53.3% leave-one-out nearest-centroid accuracy over 180
  drop windows vs 16.7% chance** — with two measures still broken (below) and no mid/high
  bands in the drop vector yet. HARD TECHNO 26/36 correct; the one systematic failure was
  SYNTH HOUSE→HARD TECHNO confusion (both dark + bass-sustained at the window level), fixed
  in round 2 by adding the harmonic mid/high sustain measures the synth signature needs.

**What round 1 proved broken (and round 2 fixes):**
- **Naive modulation depth does not separate wobble**: percentile-swing depth on the
  harmonic 60–500 Hz envelope reads 0.77–0.88 *everywhere* — note-gap pulsing (offbeat
  basslines, kick bleed) counts as modulation, and the rate estimator locks onto 2× beat
  frequency in techno/house (measured: HARD TECHNO drop mod-rate median 5.1 Hz ≈ 2×fb at
  155 BPM). Round 2 adds a **sustained-tone duty gate** (wobble is modulation of a
  continuous tone; note patterns have gaps) and a **mid-band flatness "growl timbre" axis**
  (distortion), per the MIR research (modulation-spectrum practice; McKinney & Breebaart).
- **Onset peak-picking was mis-parameterized** (density ≈ 1/beat everywhere; snare rolls
  invisible). Round 2 uses superflux-style onset strength (`max_size=3`, suppresses wobble
  AM being counted as onsets — verified-primary-source librosa behavior) on the percussive
  mid/high mel with retuned peak-picking, validated against known buildup rolls.
- **Full-band spectral flatness is kick-poisoned** (broadband transients dominate); the
  growl/whir timbre axis needs **mid-band (500–4000 Hz) flatness** computed from the same
  STFT (MIR research recommendation adopted).

**Honest ceiling noted:** 20–150 Hz *roughness* modulation (the perceptual "grit" band) is
not measurable from 43 Hz STFT frames (Nyquist 21.5 Hz); v4's wobble range is 0.5–16 Hz and
the distortion axis stands in for roughness. Labeled as a v4 limitation, not hidden.

## Appendix C — prototype round 2 (same 36 tracks, harmonic-domain measures; all confirmed-measured)

- **Growl timbre works on the harmonic mid band**: `flat_midH` (flatness of the HPSS
  harmonic component, 500–4000 Hz) at drop windows — DUBSTEP median 0.267 (ILL 0.365 and
  DROP EM 0.326 top the list, the growliest tracks in the sample) vs SYNTH HOUSE 0.089
  (lowest) at comparable harmonic levels. The axis describes *sound*, not genre: the one
  high hard-techno track (Brain, 0.316) genuinely is distorted-industrial — "gritty" is the
  correct seasoning for it. Full-spectrum flatness could not make this separation (kick
  pollution, round 1).
- **Whir re-anchored by data**: the euphoric synth-house signature is *warm sustained
  harmonic mids with clean (low-flatness) timbre* — not treble brightness (measured: synth
  house `highH` at drop start ≈ 0.5 dB vs dubstep 11.6 dB; its flat_midH 0.089 and its
  mid-band within-beat swing 6.85 dB are both the lowest of all six genres = most sustained,
  cleanest). Whir class = sustained `midH_db` + low `flat_midH` + low percussive fraction.
- **Onset density needed the corpus-absolute lesson too**: librosa's default
  `normalize=True` min-max scales the onset envelope per track — a peak-relative trap
  (Laserbeam's counts collapsed to zero everywhere). Final: superflux envelope
  (`max_size=3`) on percussive ≥500 Hz mel, `peak_pick` on the raw dB-flux scale
  (`normalize=False`, delta=1.5, wait=1, pre/post_avg=8). Validated: real snare rolls read
  3–6/beat with a clear pre-drop rise (ILL beats 98–108: flux sum 11→75 into the drop;
  crank the bass 28→79), while Laserbeam's riser-only build correctly reads ~0 (no roll —
  honest absence). A per-beat `fluxsum_midhigh` series is stored alongside counts as the
  threshold-free crescendo/roll-energy signal (R5 acceleration = its trailing slope).
- **Trap's rhythmic vacuum is measurable**: ISOXO is the only genre with a nonzero median
  pre-drop bottom-gone gap (1.5 beats) across its drop windows — the operator's "heavy but
  sparse" trap signature (addendum 16/17) directly confirmed.
- **Genre-discrimination proof (final protocol)**: 179 drop windows, 18-descriptor vector,
  nearest-centroid with **leave-one-track-out** (all windows of the test track excluded from
  the centroids — round 1's 53.3% used plain leave-one-window-out and was inflated by
  sibling drops of the same track): **53.1% vs 16.7% chance (3.2×)**. Confusion structure is
  musically honest: HARD TECHNO 29/36 (81%); remaining confusion sits between genuinely
  adjacent styles (ISOXO↔DUBSTEP — the catalog's ISOxo-era trap/dubstep hybridity;
  ODDMOB↔BASS HOUSE/SYNTH HOUSE — all ~130 BPM house). Per-genre median signatures match the
  operator's own genre map axis-by-axis (§6 table). The shipped drop-type selector (review
  2.9) maps to four archetype families with a neutral default on ambiguity (F-11) — an
  easier, safer problem than this 6-way benchmark.
- **Identity-axes stability smoke (36 tracks, even/odd Spearman)**: grit 0.911, bass_duty
  0.906, drama 0.967, brightness 0.914 pass the v3 band already at this small n; punch at
  0.769 exposed a design error — log-domain beat aggregation (geometric mean) compresses
  peaks. Two design corrections adopted: **(1) beat aggregation = arithmetic mean of linear
  power within the beat, stored as dB** (v3's energy semantics, and what blackout sizing
  wants); **(2) the punch and grit axes are computed from the v3-compat block itself**
  (CV of `kick_envelope`, median of `spectral_flatness_envelope`) — bit-identical series,
  so they provably inherit v3's measured 0.902/0.922 stability; bass_duty and drama come
  from the v4 absolute series and are re-measured at corpus scale in §7.
- **Outline rehearsal + a class-semantics ruling**: rehearsal outlines on six named tracks
  read scrub-ready (ILL's is textbook: intro riff gaps, growl sections, roll into the
  12-beat empty floor, both pre-drop vacuums; the ISOxo track shows the halftime
  every-other-bar bottom-gone pattern of trap verses). One deliberate ruling came out of the
  rehearsal: Pitch Mad Attak — "Wanna Be" (HARD TECHNO) reads `sustained synth` through its
  drops, which initially looked like a rumble misread — measurement showed the track
  genuinely carries a clean sustained rave-synth hook there (500–2500 Hz harmonic level
  15.3 dB, flat_midH 0.093 — as synth-rich as the synth-house medians), while Brain
  (rumble-only techno) correctly stays out of the class via its distorted timbre (0.316).
  Ruling: **per-beat classes describe sound, never genre or emotion** — the class is named
  `sustained_synth` (not "euphoric"); which *treatment* a sustained synth in a 160 BPM
  pounding track earns belongs to the consumer reading the whole vector. This is the
  containment rule expressing itself at the naming level.

## Appendix D — operator follow-up session (2026-07-05, post-build; all measured from the shipped cache)

The operator supplied four pieces of ground truth after the build; each was chased to a
measurement the same session.

1. **GRiZ — "I Remember" flip (the one failed extraction): the file itself is corrupt** —
   libsndfile aborts mid-stream ("flac decoder lost sync") and CoreAudio's decoder errors
   too; the header is valid (44.1 kHz/16-bit, 4:33) but frames are damaged. v3 fails
   identically, so zero-behavior-change holds. Fix is operator-side: replace the file —
   the cache keys off mtime+size, so the new copy analyzes automatically at next load or
   sweep. **confirmed (measured)**.
2. **Billie Eilish — LUNCH (Phrva Flip): the first labeled wobble positive — and the
   derive-from-cache promise validated.** The operator named it as "the exact bass wobble
   drop." The §4.9 experiment ran immediately, reading ONLY `growl_band_frames` from the
   cache (no audio decode anywhere): LUNCH's drops show *concentrated* modulation-spectrum
   peaks at **3.0, 4.0, and 6.0 cycles/beat** (6.99/9.35/14.03 Hz at 140 BPM — triplet,
   16th, and sextuplet LFO, changing rate per drop: the "talking bass"), with sustained-tone
   duty 0.72–0.79. Every negative behaves: Can't Say Nah / SIGNAL peak at the metric
   1.0–2.0 cycles/beat (kick pattern), Wanna Be's techno offbeat pumps at exactly 2.0,
   Gimme That's stabs fail the duty gate (0.39–0.41), ILL's briddim chug shows bar-level
   phrasing. Candidate rule separating this set: duty ≥ 0.6 AND dominant rate ≥ 2.5
   cycles/beat AND peak concentration ≥ 0.10. **Status upgrade: derivation-from-cache
   proven on the operator's labeled example (no re-extraction — the F-9 insurance paid
   off); the class remains unshipped until a few more labeled positives pin thresholds
   that generalize.** confirmed (measured).
3. **ISOKNOCK — SIGNAL (Party Foul Remix) reads exactly as the operator described**
   ("full bassy but clear trap hit with a siren"): main drops show growl-flatness
   0.017–0.035 (among the cleanest timbre in the corpus — *clear*), within-beat low-band
   swing 19–20 dB with attack p90 14–19 dB (*discrete heavy hits*), sub 23.2 dB at the
   main drop (*full bassy*), sparse mid/high onsets (~2/beat, halftime), and
   sustained-synth runs riding straight through the drop sections (beats 140–149, 156–163,
   172–186 — *the siren*). Bonus finding: its beat-12 intro "drop" marker carries sub
   −12.7 dB — a concrete instance of item 4. **confirmed (measured)**.
4. **Operator ground truth recorded: some ANLZ "chorus up" (drop) markers are not genuine
   drops.** Corpus check over all 1,264 BY GENRE drop markers: only 14 (1.1%) are
   *flagrantly* false by audio evidence (no ≥1 dB energy lift AND no real sub after the
   marker — clustered in ISOXO intros/outros). The operator's caveat covers more than
   those: a section can lift energetically yet not be a musical drop, which audio evidence
   alone cannot adjudicate. Consequence for Feature 2 (recorded for its spec): the
   drop-window character vector gives the classifier per-marker descriptive evidence
   (sub weight, lift, coverage), so weak markers naturally land in the F-11
   neutral/conservative default; whether to *suppress* any cue on a weak marker is a
   Feature-2 locked-design decision, deliberately not this layer's call (containment).
   **marker-quality rate confirmed (measured); the musical-falseness remainder: operator
   ground truth, unquantifiable from audio alone.**
