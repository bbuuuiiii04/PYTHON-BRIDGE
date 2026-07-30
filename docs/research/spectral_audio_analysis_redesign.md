---
doc_status: current
truth_level: code-verified + measured-corpus
last_verified_commit: 016b3bd
last_verified_date: 2026-07-08
validation_scope: software build + corpus validation only — v4 analysis layer built and validated against the local Rekordbox library (BY GENRE playlists as labeled ground truth); no lighting behavior change, no bridge execution, no hardware validation
---

# Spectral Audio Analysis — v3 Audit, v4 Redesign, and Build

Fable 5 one-shot (2026-07-05, `docs/prompts/completed/fable_spectral_audio_redesign.md`, operator-granted
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
stored under `spectral_cache/v4/` (A17). All v4 series rounded (dB: 0.1; ratios: 4 decimals;
centroid: 0.1 Hz — figures corrected 2026-07-05 S-4 to match code) — rounding is part of the
schema, so determinism includes it. The v3-compat
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
- **Added post-build (operator-approved, Appendix E)**: `lowmid_pulse_flags`/
  `lowmid_pulse_measure` (experimental fast periodic low-mid movement, from
  `growl_band_frames`) and `section_map` (chapter map for pacing consumers).

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
- `tools/spectral_stick_sweep.py` (AWR-183): the same `_sweep_one` worker over a mounted
  rekordbox USB export — enumerates `PIONEER/USBANLZ` ANLZ files, reads each track's
  device-relative audio path from the PPTH tag, and keys v4 entries by the on-stick
  absolute path, so copying the cache folder to a foreign Mac pre-warms every stick
  track. Labeled interim until AWR-165 content-keying lands (the root-cause fix).
- `state_manager.py` seam (`_runtime_spectral_features`): read order v4-cache → v3-cache
  (legacy, read-only) → extract v4 + write v4 cache → return the v3-compat view in every
  path. The scorer receives identical numbers in all three paths (§6 proof). Flag gating
  unchanged (A19).
- `__main__.py`: the existing flag-gated eviction worker additionally calls
  `evict_stale_v4()` — same thread, same flags, no new runtime surface.
  *(Amended 2026-07-24, EVICTFIX: the flags were the bug. See §15.)*

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
  Until then: `unproven`, not shipped. **Superseded by Appendix E (2026-07-05
  follow-up):** three operator labels arrived, the derivation ran from cache as promised,
  and the honest outcome ships as the renamed experimental `lowmid_pulse` class (it cannot
  isolate wobble from rolls/chugs/sirens — all genuinely fast low-mid movement).
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
   identical fingerprints) is part of §6; and `_runtime_spectral_features` logs every
   non-v4-hit path (v3-cache / v4-extract / v3-extract; the steady-state v4 hit stays
   quiet — wording corrected 2026-07-05 S-4) so silent non-convergence is observable.
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
| R6 emptiness detected & sized | `sub_db`+`bass_db` bottom-gone runs, `full_db` true-silence split (the P-2 primitive) | runs primitive validated (App. B) **[CORRECTED 2026-07-05, strict review S-1: the shipped sizing consumer (`pre_drop_gap_beats` strict adjacency + the sub∧bass AND-rule) returns 0 on every walkthrough drop; consumer rules (pickup tolerance, sub-only floor, floor-return abort, relative-dip) are required in the Feature-2 spec — see `lighting_engine_v2_strict_review.md` S-1]** |
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
| — LFO wobble rate | **experimental** — ships as `lowmid_pulse` (fast low-mid movement; wobble/rolls/chugs all fire it; scrub-gated — Appendix E) | honest ruling |
| — section chapter map | `section_map` view (16-beat blocks + marker boundaries + merge) | Appendix E |
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
  docs checks: all pass. **[UPDATE 2026-07-05: that failure was fixed by later work — at
  `f30f1e6` the suite is fully green: 3,264 OK, 6 skipped, 1 deliberate expectedFailure
  (smart-phrasing property test). Measured, strict review S-4.]**

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
  floor through 0:43.0–0:46.9 ending exactly at the DROP (beat 109) **[CORRECTED 2026-07-05
  S-4: the shipped AND-rule run is beats 100–107, ending 2 beats before the drop (pickup at
  108); "exactly at the drop" holds only under a sub-only floor rule (beats 97–108)]**; 2-beat vacuum at
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

**Re-verification at full-library scale (2026-07-08, AWR-147):** the sweep re-ran on the
grown library (731 on-disk tracks, +10 extracted, same 19 `no_grid` + 1 known undecodable
flac), and every §6.5 calibration claim was recomputed on the FULL BY GENRE set (545
tracks / ~3.3k drops vs. the 219-track partial-cache basis above) by the permanent report
tool `tools/spectral_calibration_report.py`. Every claim holds — including the frozen F2
tier cuts landing within 0.0005 of their original percentiles — with two marginal watch
items (roll threshold now exactly at corpus p90; grit even/odd Spearman 0.9016 vs the
0.902 gate floor). No constant was changed. Full numbers, named counterexamples, and the
re-run recipe: `docs/research/spectral_calibration_expansion_2026_07_08.md`.

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
- `lowmid_pulse` firing rates on the 8 labeled tracks + section maps on 4 known tracks —
  **confirmed (measured, Appendix E)**; the class's acceptability for texture seasoning —
  **unproven pending the operator scrub gate** (timestamps listed).
- Suite result — **confirmed**: 3,251 tests at the main build (3,264 after Appendix E),
  zero new failures; the single failure
  (`test_laser_color_engine…fixed_band_values`) is **pre-existing at baseline `2945c52`**
  (unrelated subsystem, untouched by this build). **[UPDATE 2026-07-05 S-4: since fixed;
  suite fully green at `f30f1e6`.]**

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
3. *(Superseded by Appendix E — labels arrived, investigation ran, renamed experimental
   class shipped; the scrub timestamps in Appendix E are the remaining gate.)*
   **Classic LFO-wobble detection: first labeled positive received** — the operator named
   Billie Eilish — LUNCH (Phrva Flip) post-build, and the wobble signature derived cleanly
   from the already-stored cache data (Appendix D item 2 — no re-extraction, as designed).
   **Default: the class still ships only after 2–3 more labeled wobble tracks confirm the
   thresholds generalize** — name them whenever; each is a five-minute cache read.

---

## 9. Stage-1 EAR benchmark (AWR-200, 2026-07-10)

The v4 extractor/cache this report built is the KEEP layer; the SOL review
(`docs/research/sol_spectral_review_2026_07_09.md`) split the *decision* layer into the
AWR-195 refactor program whose blocking first stage is a real ear benchmark. That harness
now exists — read-only offline tooling, no runtime behavior change:

- `tools/spectral_ear_benchmark.py` + `tests/test_spectral_ear_benchmark.py` (56 tests after
  the 2026-07-11 AWR-205 gold-intake pass + its adversarial-review fix; 32 before: single `call_planner` anti-leak
  boundary on every planner call, amendment grouping via the `amends` parent link (with a
  duplicate-id guard against silent primary corruption), an availability gate that now requires
  markers scored AND at least one comparable ±1/±2 perturbation, per-radius comparable
  denominators, real fold-disjointness invariant, identity-collision warnings; the label layer
  now carries content_id locators for all 21 usable lineages).
- Spec: `docs/plans/active/spectral_ear_benchmark_spec_2026_07_10.md`.
- Frozen run: `docs/research/spectral_ear_benchmark_stage1_report_2026_07_10.md`.

**AWR-205 gold-label intake (2026-07-11, offline, read-only).** Two new modes on the same
harness give the ear benchmark a place to hold structured per-drop gold — the missing layer that
kept every accuracy axis UNAVAILABLE. `--emit-gold-template OUT.json` (requires `--resolve-db`)
reuses the SAME resolved-marker enumeration the marker-sensitivity pass iterates and writes a
deterministic, all-null, provenance-keyed **hybrid** template (operator ruling 2026-07-11): every
enumerated drop marker gets an `is_genuine_drop` yes/no, and the nested `drop` field-set
(tier/family/family_matches_track/darkness{shape,start,end,bars}/growl{start,end}|"none"/laser/
confidence/notes) is filled ONLY on genuine drops; it refuses to clobber a file that already
carries labels. `--gold PATH` runs a strict fail-closed loader — unknown/typo'd fields (positive
allowlists), unmatched provenance keys, bad enums, and insane beat ranges are HARD errors naming
every offending row; `is_genuine_drop: null` = unlabeled (excluded from scoring, counted in a
`labeled/total` coverage line) — and scores it. An accuracy axis flips AVAILABLE only when BOTH a
genuine-drop gold example exists AND a real scorer compares it to a per-marker output verified in
`lighting_moments_v2.DropDecision`. Only **tier** (int) and **family** (str) are cleanly exposed,
so only they score this round; **darkness** (bar↔beat unit / shape-vocab / start-end alignment
unverified), **growl** (no model span) and **laser** (no model suitability) — plus the yes/no
**drop_classification** layer (the planner exposes no genuine-drop/blackout classifier) — stay
UNAVAILABLE with a named blocker (fail toward UNAVAILABLE). Gold never crosses the `call_planner`
boundary; `is_partial` is untouched, so **AWR-200 stays PARTIAL** until every required accuracy
axis has gold + a scorer. Template + filled gold live beside the AWR-182 label layer under
`local/` (gitignored, never committed); the AWR-182 file is read-only. Real-DB read-only spot run:
21 lineages / 158 markers, label sha `a584dcb1e0293b24` unchanged. Spec:
`docs/plans/active/spectral_gold_label_intake_spec_2026_07_11.md`.

It loads the AWR-182 ear-truth labels, validates/normalizes them without mutation, applies
the charter's explicit exclusions with reasons, groups whole track/remix lineages, emits a
deterministic coverage manifest + grouped leave-one-lineage-out fold inventory, and audits
per-axis metric availability. It imports and calls `lighting_moments_v2.build_track_plan`
for the one axis needing no operator gold — marker sensitivity (drop marker ±1/±2 flip
rate) — resolving each track through its current library filepath + beatgrid fingerprint
(never iterating raw cache files) and reading the v4 cache read-only. **AWR-200 is PARTIAL:**
the labels are the operator's free-text verdicts, so every accuracy axis
(tier/family/darkness/growl/laser) is reported UNAVAILABLE — never a fabricated zero/PASS —
blocked on a curation pass. The marker axis now resolves the full usable corpus after the
2026-07-11 content_id enrichment (21/21 usable lineages / 158 markers), still NOT compared
like-for-like to SOL's 15-track/113-marker sample. The growl-centroid values these tracks
carry are present, aligned, and real-valued in the strict v4 cache — no backfill remains; only
their *musical* correctness is an open Stage-2 question.

**2026-07-15 operator closure:** the gold-label curation pass (AWR-205) is permanently
closed by operator ruling — the 1-1 labeling session will never run. Consequence:
AWR-200's accuracy axes stay UNAVAILABLE forever and AWR-200 is FINAL at PARTIAL (the
marker-sensitivity axis delivered its value and fed the AWR-239 pilot). Musical-correctness
questions (growl centroid, lowmid_pulse/wobble thresholds) validate ONLY through normal
live mixing — the operator vetoes wrong-looking moments by timestamp; silence is a pass;
agents correlate against decision logs. No labeling sessions, ear batches, or
"name-me-tracks" asks, ever (operator ruling 2026-07-15). A feature whose validation would
require structured listening from the operator is redesigned or killed at spec time.

---

## 10. Intrinsic-hardness shadow descriptor (AWR-203, offline, 2026-07-11)

`hardness_v0.py` + `tools/hardness_ablation.py` are an **offline, non-authoritative** shadow
axis — the frozen SOL3 "intrinsic hardness" candidate, built to be *benchmarked*, not routed.
Zero runtime importers (only `tools/`+`tests/` may import it; a static AST test enforces it), no
I/O, and it never times or triggers a cue. `violence`/`.tier` stay the sole live authority — this
axis does not replace tier, feed darkness, or drive any output.

- **Formula.** Four landed-sound terms over a first-8 + following-8 landed view (each term
  averaged across the two halves): persistent body `B=clip01((Q25(full_db)-13.7)/3.8)`, sustained
  high-band abrasion `A=clip01((Q25(high_db)+5.5)/10.4)`, distorted-growl duty
  `R=mean clip01((growl_band_db-20)/12)·clip01((growl_flatness-0.10)/0.20)`, mid-high onset density
  `N=clip01((mean(onset_density_midhigh)-1.7)/1.3)`. A marker ±2 alignment search picks the
  descriptor window (the Rekordbox marker stays the cue). Per-term-median track baseline `T*` over
  genuine drops. Three paths `repeated_wall=min(T_B/0.92,T_A/0.80)`,
  `abrasive_hammer=min(T_B/0.70,L_B/0.75,L_A/0.60)`,
  `growling_hammer=min(T_N/0.65,L_B/0.80,L_R/0.40,L_N/0.70)`, `H=max(paths)`.
- **Honesty.** `H≥1.0` is *path-threshold firing*, NOT an independently validated boundary; the
  candidate is in-sample (anchors + thresholds hand-iterated on the same named pins) and
  **binary-T3 only** — there is no T1/T2 split and none may be invented from this formula. Q25
  reuses `spectral_profile.percentile` so it stays bit-identical to the anchor calibration.
- **Reducers.** `center`/`median`/`q75`/`max` alignment reducers make the selection-bias ablation
  a call, not a rewrite (deterministic tie-break; the reducer ranks offsets by the composite
  alignment score).
- **Evaluator.** `tools/hardness_ablation.py` is read-only: it resolves each track content_id →
  current filepath → current ANLZ beatgrid → `get_cached_v4`, then (defense-in-depth over the
  forward key) re-reads the current-key payload and asserts its `audio_filepath` +
  `beatgrid_fingerprint` match — never enumerating raw cache JSON, never extracting or writing. It
  emits descriptive evidence only (coverage, reducer prevalence, manufactured-T3 fraction, per-path
  standalone/unique counts, n_drop strata, micro + track-macro marker flips at ±1/±2,
  boundary-conditioned flips) and makes **no** taste-accuracy, held-out, or readiness claim; group
  bootstrap + accuracy scoring are skipped because no structured independent gold exists yet.
- **Status:** `experimental` / `software-tested` (28 unit tests; the AWR-203 9-lens adversarial
  review reported zero module defects, but a later edge-fix lane (2026-07-11) closed a finiteness gap
  it had missed — the shared `_valid_v4` gate now abstains (returns `None`, never a phantom T3) on a
  non-finite (NaN, +inf which else clip01-saturated to a false T3, −inf) or unshaped/non-numeric
  required series). Offline candidate only — live routing, tier replacement, and the later
  inert-shadow-logging step (Increment B) each require a separate operator gate. The AWR-200
  candidate-planner hook was deliberately NOT built: hardness is a binary shadow descriptor, not a
  production `DropDecision`. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

---

## 11. Raw approach-descriptor layer (AWR-204, offline, 2026-07-11)

`approach_features_v0.py` is the **offline raw measuring layer** for the SOL2 finding-1 refactor:
pre-drop "go dark vs balloon vs stop" must be read from the *shape of the approach over time*, not
the single lowest growl beat (a one-sample gate — the exact fragility being replaced). This layer
**decides nothing** — no class, no threshold, no darkness length, no label. It is the raw material a
later rules-first-vs-tiny-model bake-off will read. Zero runtime importers (only `tools/`+`tests/`
may import it; a static AST+text test enforces it), no I/O, and it never times or triggers a cue.
**SOL2 finding-1 is NOT fixed by this layer** — only its measuring surface exists.

- **What it computes.** One pure function `approach_features(v4, drop_beat, ...)` returns a frozen
  `ApproachFeatures` bundle over the four AWR-195 charter views of one drop: **(a)** track-wide
  quantiles + an across-`genuine_drops` first-landing reference; **(b)** an explicit current section
  (`section_start` XOR `section_len`, honestly unavailable when neither is given); **(c)** the
  pre-drop approach (`approach_start` XOR `approach_len`); **(d)** `landed_first8` and `landed_next8`
  kept **separate**. Per window, per series (`full/sub/growl_band/sustain_mid/sustain_high/perc_full`)
  a `SeriesStats` carries robust quantiles `p05..p95` (p05 is the robust floor — **not** `min`),
  `mean`, early/late half means + their `delta`, an OLS `slope`/beat, and finite-data coverage.
- **Void + depth, raw.** `run_curves` reports the longest below-floor run in the approach at a
  reference view's own p10/p25/p50 (data-derived quantiles, precedence track→section→self) — no
  musical floor baked in — plus a `longest_run_below(values, floor)` primitive for a caller-supplied
  floor (a non-finite beat BREAKS the run, never counted as below). `depth_vs_track`/`depth_vs_section`
  are the approach FLOOR (p10) minus the reference's TYPICAL level (p50), a raw subtraction that stays
  a true "deep for this track" signal (median-referenced so a long void does not contaminate it).
- **Marker robustness.** The approach + both landed bundles are recomputed at drop ±k (k∈0..radius,
  default 2); a length window slides with the marker, an explicit-start window keeps its start and
  only its end moves; `descriptor_range(bundles, series, stat)` gives the (min,max) across offsets.
  The Rekordbox marker stays authoritative — the module never re-times a cue.
- **Fail-safe / honest.** Missing series → `present=False`, all stats `None`. Non-finite (NaN/±inf)
  filtered before any `sorted()`/percentile; an all-hole half → `None`, never `0`. `sufficient` is
  true only when the window has ≥2 in-range beats AND some series has ≥2 finite samples (so at least
  one OLS trend is actually computable) — a short window OR an all-hole/single-finite window →
  `sufficient=False`, `slope=None`, with a reason distinguishing too-few-beats from
  no-finite-data. Out-of-range → clamped, `n_requested` vs
  `n_available` reported honestly. Empty track → `available=False` with a reason, **no exception**.
  Top-level `available` additionally requires at least one finite approach descriptor, so a window
  that intersects the track but is entirely missing/non-finite reads `available=False` with an honest
  reason (per-series partial availability is unchanged). Only inconsistent CALLER inputs raise
  `ValueError` (both/neither of an XOR pair, non-positive length, negative radius).
  **Missing/short/non-finite data can never fabricate a darkness event.**
  Reuses `spectral_profile.percentile` (no new dependency); deterministic (repeated calls compare
  equal, pinned by a test).
- **Status:** `experimental` / `software-tested` (27 unit tests; the AWR-204 independent ULTRACODE
  review found zero per-series defects, but a later edge-fix lane (2026-07-11) corrected a hollow
  top-level flag it did not examine — `ApproachFeatures.available` now requires at least one finite
  approach descriptor (all-missing/all-non-finite → `available=False` with an honest reason;
  per-series partial availability unchanged) — and a follow-up sufficient-fix lane (2026-07-11)
  closed the same-class hollow in the per-window flag: `WindowStats.sufficient` now needs ≥2 finite
  samples in some series, not just ≥2 beat slots, so an all-hole window reads `sufficient=False`
  with a reason distinct from the too-few-beats case). Offline raw layer only — **no
  classifier, no tool, no live wiring, no hardware validation.** The taste calls (class boundaries,
  darkness lengths, the uncertain fall-back, marker-radius policy, rules-vs-model promotion) are
  deliberately left open for the operator. `tools/approach_feature_report.py` was NOT built (the raw
  module + tests suffice until structured gold / classifier evaluation exists).
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

---

## 12. Library track-weight layer (AWR-286/291, energy E1, offline, 2026-07-24)

`track_weight_v0.py` (repo root, pure, stdlib-only, **zero runtime importers** — a
static test enforces `tools/`+`tests/`-only imports) is energy-fabric stage E1
(`docs/plans/active/energy_e1_track_weight_spec_v1.md`; formulation revised by
AWR-291, `docs/plans/active/energy_formulation_revision_spec_v1.md`). It scores
each track's energy **against the whole library** in a way that ignores mastering
loudness.

- **What it computes (v2 component set).** Four per-track components — `body_duty`
  (fraction of beats with `full_db ≥ ref−8`), `brightness_med` (the track's median
  spectral centroid in Hz, `audio_spectral_features.py:422`), `onset_mh_mean`,
  `growl_flatness_mean` — then `track_weight` = the mean of each component's
  mid-rank percentile across the library (equal weights, pinned). AWR-291 replaced
  `sub_duty`, which duplicated `body_duty` (measured rho +0.578) and read the
  compression confound; `brightness_med` is far less redundant (0.242) and less
  compression-coupled (−0.480 vs −0.675).
- **Why no absolute-dB feature enters the aggregate.** `ref = loudness_ref_db =
  p95(full_db)` (`:423`). `body_duty` compares each track's own beats against that
  track's own `ref`, so a uniform per-track offset shifts numerator and reference
  together; `brightness_med` is a power-weighted centroid (`:374`) carrying no
  absolute dB, so a level change cannot move it; `onset_density_midhigh` /
  `growl_flatness` are count / ratio series. Gain-invariant by construction in
  exact arithmetic; in the shipped pipeline the cancellation is exact to ~±0.005
  grade units (every stored dB is rounded to 0.1 dB, `:307-311`) and fails on beats
  pinned at the −100.0 dB power floor (`:35`, `:313-314`), ~19% of BY GENRE tracks
  — checked by re-extraction (`tools/energy_perturbation_check.py`), not by an
  offset to cached values.
- **TWO pinned gating acceptance controls + one printed diagnostic.**
  `tools/track_weight_report.py` sweeps the library read-only, writes a version-owned
  sidecar `<cache_dir>/trackweight_v1/track_weight_store.json` (**schema_version 2**,
  now carrying `drop_body_distribution` — E3's body-term corpus fallback;
  machine-local, never committed), and on the BY GENRE split (contract law: BY GENRE
  tracks only, `n ≥ 100`) ACCEPTS iff loudness proxy
  `|Spearman(loudness_ref_db, weight)| ≤ 0.50`, worst component-pair `|rho| ≤ 0.60`,
  and no component is degenerate. Every constant moves only by spec amendment — never
  by the implementer to make a run pass. A failed acceptance is a valid, reported
  result.
- **The dynamic-range control is a DIAGNOSTIC, not a gate (AWR-291 §5, the E1SCRAMBLE
  demotion).** `|Spearman(robust_dynamic_range = p95−p25 full_db, weight)|` is still
  computed and printed against the same `0.55` reference (`DRAMA_ACCEPT_MAX`), but it
  decides nothing: the compression-family secondaries showed that a formulation
  correlating with dynamic range is most likely reading **arrangement** — the thing E1
  is asked to rank — so gating there gates against real signal. The primary
  predeclared statistic fired SCRAMBLE on an **EQ** op, not a compressor, so the
  demotion rests on named secondaries. Mastering is not free either (median tax
  **+0.044** weight, p90 **~0.11**, up to **32/100** ranks under a full chain), which
  is why the line stays printed forever — it just stops deciding. The demotion was
  specified to land only alongside its replacement,
  `tools/energy_scramble_watchdog.py` (below), because demote-without-replacement is
  out of scope by construction. **What actually happened, recorded rather than
  smoothed over:** the repo's auto-sync hook published two intermediate commits
  (`d1c30cf0`, `5887c503`) carrying the demotion *without* the watchdog, which arrived
  nine minutes later in `51a7e639` — so the same-change rule was VIOLATED in published
  history. That split is accepted by explicit exec amendment, with the rule
  re-specified in a form this repo can actually satisfy: see
  `local/spectral_v5_2026_07_17/EBUILD4_coupling_adjudication.md`. Coupling is now
  discharged by **WRITE-ORDER** — the replacement is written to the working tree,
  complete with tests, *before* the removal edit — so no auto-sync snapshot can hold a
  removal without its replacement. (The earlier claim that the split was
  "structurally impossible" was false and is withdrawn.)
- **The replacement watchdog battery.** `tools/energy_scramble_watchdog.py` (offline,
  zero runtime importers, temp-dir extractions only) runs four E1SCRAMBLE probe
  classes on the frozen 100-track / 66-cell / seed-20260724 panel: `c0b_invert`
  (polarity-only exact null — GATE `rho == 1.0` by **literal equality, no rounding**,
  plus displacement `0`; it first shipped comparing `round(rho, 4)`, which admitted
  `rho = 0.999996999695469` on a tied pair, and that false pass is now pinned as a
  regression),
  `c1a_gain` (per-track gain **drawn** in `[-12, 0]` dB + TPDF dither at −90 dBFS,
  reproduced from the `c1_static` seed stream — GATE `rho ≥ 0.999`, a floor sitting ON
  its single measured `0.9990` with no margin, so a marginal miss is reported as
  instrument drift and never re-floored), and `c1c_tilt_mild` / `c1b_tilt` (±1 dB and
  ±3 dB shelves — **INFORMATIONAL, comparative-only**, because the incumbent measurably
  sits at `0.9673` / `0.7938` and any pinned floor would either fail the accepted
  formulation or be tuned to pass it). **Stated plainly and printed verbatim in the
  tool's own report header: this trade removes one acceptance gate and adds ZERO** —
  both new gates test the INSTRUMENT (harness integrity, extraction fidelity), so it
  is gate-for-diagnostic, not gate-for-gate.
- **No live consumer.** E1 decides nothing live; nothing runtime reads the store
  (E2+ consumers arrive under their own specs). The bridge is byte-identical.
- **Status:** `implemented` / `software-tested` (unit tests incl. the exact
  uniform-shift + a rounding-aware sibling, `robust_dynamic_range`, the full
  acceptance precedence table, the schema-skew check, and the importer guard).
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

---

## 13. Per-section energy grades (AWR-288/291, energy E2, status-only, 2026-07-24)

`section_energy_v0.py` (repo root, pure, stdlib-only) is energy-fabric stage E2
(`docs/plans/active/energy_e2_section_grades_spec_v1.md`; formulation revised by
AWR-291). Unlike E1's offline descriptor, this module IS runtime-imported — by
`state_manager.py` on the ANLZ worker thread at track load — but it grades sound and
**decides nothing live**: at E2 there is no consumer. A static import-fence test
allows only `state_manager.py` + `tools/` + `tests/` to import it.

- **Two grades per section (v2).** `within_track` = the section's **median**
  `full_db` (AWR-291: median, not mean — one silent beat pinned at the −100 dB
  floor no longer drags a whole drop section to zero) mapped through the
  loudness-relative span **−12 dB → 0.0, 0 dB → 1.0** against the track's own
  `loudness_ref_db`. The span is NO LONGER the −8/−3 section tiers: the old top
  rail sat on the corpus median and pinned ~49% of sections at 1.000, so AWR-291
  re-placed it from the measured section-level distribution. Gain-invariant by
  construction (exact to ~±0.005 grade units after 0.1 dB rounding). `library_scaled`
  = `within_track × track_weight` (the ladder's §B.2 product law), or `null` when
  the E1 store is missing / refused.
- **Store consumed by construction.** `load_track_weight_store()` is the ONE store
  access; it returns None unless the file parses, `schema_version == 2` (AWR-291),
  `accepted is True`, and `tracks`/`distribution` are dicts. A v1 / `accepted:false`
  / missing / malformed store refuses to **library-scale** (every `library_scaled`
  null) but `within_track` still computes — it never needs the store (EREV1 N6).
- **Segments self-describe.** Section boundaries come from
  `build_phrase_segments_from_markers` (markers → up/chorus/low), falling back to
  `section_map` blocks (label "other"), then `[]`. Grades carry their own
  `start_beat`/`end_beat`.
- **Facets published (§2/§3), recorded not surfaced.** Two facets are on **every**
  grade dict: `segmentation_basis` in {`markers`, `section_map`} (WHICH lawful basis
  drew the boundaries — `_normalized_segments` now RETURNS it) and `contrast_class`
  in {`flat`, `normal`} (`flat` iff the unclipped per-section `rel` range < 5.0 dB;
  the `label` stays the runway authority).
- **`slope` — a CONDITIONAL third facet (present when derivable, ABSENT otherwise —
  never fabricated).** The within-section loudness-trajectory channel: the mean
  POSITIVE per-beat slope (`t_pos`) of the smoothed `full_db` over a ~3 s attentional
  window, published RAW in dB per window, NON-negative and NOT mapped to [0,1] (that
  presentation belongs to E4). The beat clock is derived IN-MODULE
  (`60 × n_beats / duration_s`) so `grade_sections` keeps its signature; the windowed
  math is a byte-copy of the C3 prototype; only the in-section window is offered (the
  trailing window inverts the sign). **The key is OMITTED — not `0.0`, not `null` —**
  whenever the clock is underivable (`n_beats ≤ 0`, or `duration_s` non-finite/≤ 0)
  or no finite windowed slope lands inside the section, so a reader must treat
  `slope` as optional and MUST NOT read its absence as a zero rise. `within_track` /
  `library_scaled` are unaffected by an absent slope.
- **Facets are recorded, never surfaced.** All three ride the ANLZ payload record but
  NEVER the status block: `current_section` PROJECTS the per-deck E2 block to the
  frozen `{start_beat, end_beat, label, within_track, library_scaled}`, so the status
  shape is unchanged while the grade dicts grow.
- **Flag-off byte-identity.** `RBSS_SECTION_ENERGY` defaults OFF ⇒ zero new
  computation, zero new payload keys, zero new status keys — proven by the kill
  test (UNCHANGED by AWR-291). All compute + the single memoized store read run on
  the ANLZ worker.
- **Push-loop cost: one disclosed exception, not "nothing".** With the flag OFF the
  push loop gains nothing at all (the path does not execute). With the flag ON, the
  facet round adds exactly one thing to a push-loop-thread path: `current_section`'s
  projection BUILDS a five-key dict per deck per status publish (`_publish_snapshot`,
  up to 20 Hz at `_SNAPSHOT_PUBLISH_INTERVAL_S = 0.05`) where it previously returned
  an existing dict. Constant-size, allocation-only — no I/O, no lock, no growth with
  track length, on a call that already scans a few dozen sections. It is stated here
  rather than quietly excepted, because an invariant this program asserts has to stay
  literally true: the honest claim is "no I/O and no blocking work in the push loop",
  not "no work of any kind".
- **Pinned gates (offline `tools/section_energy_report.py`):** G1 coverage
  `n_graded / n_by_genre_eligible ≥ 0.95`, **G2 saturation** (railed fraction of
  all graded sections `≤ 0.20` — the gate that would have caught the v1 collapse),
  **G3 rankability** (`≥ 0.90` of tracks with ≥3 chorus sections have ≥2 distinct
  chorus grades), **G4 separation** (`median(chorus) − median(low) ≥ 0.25`), corpus
  floor `n ≥ 100`. The report also prints a boundary-jitter diagnostic (±1/±2/±4
  beats) and the bottom-rail chorus fraction, both INFORMATIONAL. Thresholds move
  only by spec amendment; a failed gate is a valid, reported result.
- **Status:** `implemented` / `software-tested`. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

---

## 14. Per-drop energy grades (AWR-290/291, energy E3, status-only, 2026-07-24)

`drop_energy_v0.py` (repo root, pure, stdlib-only, runtime-imported by
`state_manager.py` on the ANLZ worker) is energy-fabric stage E3
(`docs/plans/active/energy_e3_drop_grades_spec_v1.md`; formulation revised by
AWR-291). It grades each drop and **decides nothing live**: at E3 there is no
consumer — no presentation/laser/LED path may read `DropDecision.energy_grade` (a
static import-fence test enforces the allowlist).

- **Four REQUIRED terms** over the `[beat, beat+16)` window, all ranks or ratios
  (so all inherently level-invariant): `body` = mid-rank of this window's level
  (mean `full_db` − ref) among the track's OWN drop-window levels when it has ≥2
  (`body_basis = "track_drops"`, ranked against the RAW ANLZ marker set) else the
  corpus drop-level distribution from the v2 store (`body_basis = "corpus"`, ~2.18%
  of tracks) — a rank cannot saturate, unlike the v1 level term (pinned at 1.000 on
  94% of drops); `activity` = clip(mean `fluxsum_midhigh` / the track's own
  `fluxsum_midhigh` p90) (R4: replaced the v1 `onset` count term, whose cached
  `onset_mh_p90` normaliser sat in {2,3,4} on 98.2% of tracks — `onset_mh_p90` is
  retired from the required set); `perc_high` = clip(mean `perc_high` / the track's
  own `perc_high` p90); `growl` =
  clip(mean `growl_flatness` / `growl_timbre_p90`). `within_track` = mean of ALL
  FOUR — if any normaliser is absent/non-finite/≤0 the drop is **omitted**, never a
  re-weighted mean over fewer terms (cures a latent v1 silent-reweight). The single
  term-math implementation is `score_windows`; `grade_drops` wraps it and the report
  / G7 reuse it. `library_scaled` = `within_track × track_weight` or null.
- **Facet publication (§2).** Every grade dict also carries the four term VALUES
  (`body`, `activity`, `perc_high`, `growl`) beside
  `within_track`/`library_scaled`/`coverage`/`body_basis` — computed per window,
  previously discarded, now RECORDED on the grade and in the ANLZ payload but NEVER
  surfaced (the per-deck status block projects only `beat`/`within_track`/
  `library_scaled`). `body_basis` is the E3 basis record; no new basis field.
- **True-drop law honored structurally.** The worker grades RAW ANLZ-marker
  windows, but grades ATTACH to plan decisions built from `meta.smart_drops` and
  ONLY plan-attached true-drop grades are surfaced; `body_basis` is recorded on
  every grade but never surfaced. No surface enumerates the raw set.
- **Store consumed by construction.** Track weight AND the corpus fallback
  `drop_body_distribution` come ONLY from E2's memoized `_track_weight_store_once()`
  (the ONE authorized wiring delta reads the fallback off the same already-loaded
  object) — E3 opens no store file. Refusals ⇒ `library_scaled` null.
- **Flag-off byte-identity (four surfaces).** `RBSS_DROP_ENERGY` default OFF ⇒ no
  computation, no ANLZ_DATA payload key, no `drop_energy` status key, and every
  `DropDecision.energy_grade` is None. Kill test proves all four (UNCHANGED by
  AWR-291). All compute + the single store read run on the ANLZ worker; the 200 Hz
  push loop gains nothing.
- **Seven pinned gates (offline `tools/drop_energy_report.py`):** G1 coverage
  ≥ 0.95; **G2 term-saturation** (worst term railed `≤ 0.20`); **G3 term-correlation**
  (worst term-pair `|rho| ≤ 0.60`); **G4 composite IQR ≥ 0.10** (raised from v1's
  0.05); **G5 rankability ≥ 0.90**; **G6 level-separation** (median drop-window
  rel-dB − median 'low' rel-dB `≥ 3.0` dB — a dB sanity check on the window
  indexing, NOT a grade check); **G7 GRADE-SPACE separation** (median drop composite
  − median 'low' composite `≥ 0.10`) — the one gate that reads the grade itself,
  added because a pure `random.random()` composite passed all six of the first
  draft's gates (EREV1 F3); a regression test requires the all-random composite be
  rejected with G7's reason specifically. Report also prints the corpus-basis drop
  count and both `library_scaled` correlations (INFORMATIONAL). Thresholds move only
  by spec amendment; a failed gate is a valid, reported result.
- **Status:** `implemented` / `software-tested`. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

---

## 15. Cache eviction repair (EVICTFIX, 2026-07-24)

Diagnosis: `local/spectral_v5_2026_07_17/CACHEDIAG_report.md` (read-only, measured against
the live cache dir). Eviction had never run on this machine, and would have destroyed the
USB pre-warm if it had. Four defects, all now closed; none of them could ever have served
wrong data — the cache filename *is* the key (`sha1(realpath + mtime_ns + size +
beatgrid fingerprint)`), so a changed track lands on a different filename and re-extracts.
This was a disk-space bug (547 MB, growing on every new track), never a live-safety one.

- **The gate never opened** *(confirmed)*. The worker demanded
  `RBSS_SPECTRAL_ENABLE=1`, which no launch path sets — not `launch_profile.BRIDGE_ENV`,
  not `scripts/ss_bridge_watcher.sh`, not `usb_launcher.py` — while the ANLZ worker
  *writes* entries under a different condition entirely (`state_manager` extracts and
  caches when the gated v3 spectral path **or** LED identity-v2 is on, and identity-v2
  comes from the colour-engine config). Zero `spectral-cache-evict` lines across 23 bridge
  logs. Eviction now runs under that same write condition
  (`__main__._spectral_cache_writes_enabled`), so the collector runs exactly when the
  garbage is produced. Adding the env flag to the launch profile was rejected: it would
  have flipped the gated v3 spectral path as a side effect.
- **Foreign files killed the sweep** *(confirmed, reproduced)*. macOS AppleDouble `._*`
  twins arrive with every copy off a FAT/exFAT stick (1794 of them, all dated 2026-07-10,
  the signature of one bulk stick/install copy). `Path.glob("*.json")` returns them, unlike
  `glob.glob`; they are binary; `UnicodeDecodeError` is a `ValueError`, not a
  `JSONDecodeError`, so the old handler missed it and the exception escaped the loop, the
  function and the thread — on file index 0 in **both** directories, and a v3 abort also
  stopped the v4 sweep, which ran in the same worker. Both sweeps now skip `._*` names:
  never read, never deleted (macOS just recreates them).
- **Undecodable entries** now read as stale via a widened `ValueError` handler. That is
  safe *only* because the foreign-file skip runs first — what reaches the handler is one
  of our own entries, and one of ours that will not decode is genuinely dead.
- **The mount guard — the one that mattered** *(confirmed)*. 599 v4 entries referenced
  audio that does not exist right now, but **587 of them were the deliberate USB pre-warm**
  written by `tools/spectral_stick_sweep.py`, keyed by the on-stick `/Volumes/MINK`,
  `/Volumes/USB` path. With no stick mounted, a merely un-crashed sweep would have deleted
  ≈229 MB of pre-warm and the operator would have found out at the next foreign-Mac gig, as
  ~15 s of extraction per track. `os.stat` failure on a path under an unmounted `/Volumes`
  root now reads as **unknown → keep** (`_audio_on_unmounted_volume`, `os.path.ismount` so a
  leftover empty mount dir still counts as unplugged). The honest yield of a correct sweep
  today is ≈46 entries / ≈8.9 MB, not 229 MB.
- **Worker hardening.** `_worker` gained a `try` — no future exception can kill the thread
  silently; the abort logs at DEBUG.

Tests: `tests/test_spectral_cache.py` (sidecar survival, unmounted-kept vs dead-collected,
stale-still-collected-beside-a-sidecar) and `tests/test_spectral_eviction_gate.py` (the
write-condition gate + worker exception containment). Live safety: nothing here touches the
200 Hz push loop, eviction stays a separate daemon thread, cache reads on the ANLZ worker
are unchanged, and the sweep is now strictly more conservative than the code it replaced.

Queued follow-ups (out of EVICTFIX scope, recorded): `tools/calibrate_identity_v2.py` has
the identical uncaught-decode defect and dies on file #1 (it is not in the
`spectral_analysis` contract's `code_globs`); `tools/spectral_sweep.py` counts sidecars in
its entry/MB totals (≈5.3 MB of inflation); `install_controller._copy_managed_payload`
re-imports the sidecars on every install (different contract).

- **Status:** `implemented` / `software-tested`. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

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
  before drop 141 **[CORRECTED 2026-07-05 S-4: these are sub-only prototype readings — the
  shipped sub∧bass rule yields 8 beats (100–107) at drop 109, nothing visible at 141, and
  the vacuum before 261 measures 2 beats (258–259) from the shipped cache under either
  rule]**; and the 2:18–2:25 run is literal end-of-file silence (full-band −80 dB),
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

## Appendix G — operator lighting walkthroughs (2026-07-05; creative direction for the Feature 1–4 specs — recorded verbatim in intent, annotated with measured beats)

The operator narrated how lighting should behave through two tracks, beat by beat, with the
explicit framing: **generalizable, not hard-coded** — "not every tech house song should
follow this EXACT pattern"; these are windows into how the engine should think. His close:
"This is just my general idea in mind and does not replace all the context we've built up."

**General principles (operator's own):**
- The LED strips light the entire room, **paired with the 2 DMX lasers in a haze setting** —
  ⚠️ this answers the v2 review's standing open question 3 (haze was UNKNOWN): haze is IN,
  so beam-based laser designs are in scope. Must be folded into the v2 record.
- **Amount of light in the room ≈ strength of the audio.**
- **Animation-rate ladder:** atmospheric/slow-breakdown moments animate every 1/2/4 beats
  (by musical character); regular grooves every beat; drops every 1 / 0.5 / 0.25 beats.
- Fast color changes *within the track's palette* can also signal energy/musical elements.
- Track palettes as examples: STARsound = blue/cyan/white, typically brighter; Can't Say
  Nah = cool darker tones, primarily blue/cyan.

**Walkthrough 1 — Odd Mob, Walker, Royce — Can't Say Nah** (annotated: his timestamps land
on his own markers almost exactly):
- 0:00→0:29.6 (beats 0–64, groove): beat-synced groove effect, cool blue/cyan — "basically
  my rt groove chase looks."
- 0:29.6 (buildup marker 64): lows drop out; groove looks continue with a **hue shift** to
  signal the missing low end and slow build (darker or brighter — operator undecided).
- 32 beats before the drop: buildup cues, but **white+blue mix instead of full white**
  (this build is not too intense — build intensity should scale the white share).
- 1 beat before the drop: a minor percussive cut → **1-beat blackout**.
- Drop 0:59.1 (marker 128): a slightly intense low-end growl, ~4 beats, recurring (another
  at 1:13.9 = marker 160) — "a lot of tech house drops have this characteristic."
  **Growl beats get the strobing sparkle (rt drop chase); the regular driving beat gets
  rt post drop chase (beat-synced strobing comets).** [Texture-reactive seasoning *within*
  the drop — the growl/pulse classes are the natural inputs; role scheduling unchanged.]
- 3rd chorus 1:28.7→1:58.2 (markers 192–256): **"not as intense (should be recognized by
  spectral analysis)"** — honest verification note: the window vectors currently read
  chorus 3 nearly identical to drop 1 (full 15.0 vs 14.9 dB, sub 31.0 vs 31.2, attack 12.5
  vs 13.6) — the softness his ear hears is NOT yet shown by the primary energy measures;
  open analysis question, candidate axes (layer thickness, mid/high content) unexplored.
- 1:58.2 (breakdown marker 256): lows cut, drums persist.
- 2:27.7: percussion cuts out into the build — LEDs **sparse and dim** into the drop; "this
  buildup is more like an implosion waiting to happen."
- 2:40.7: room blackout (measured: a 2-beat bottom-gone run at beats 348–349 — shorter than
  the described ~4-beat window; partial agreement). Drop 2:42.5 (marker 352): **intense
  full-LED strobe for 4 beats** complementing a growl *more intense than the first drop* —
  verification note: the analysis reads the two growls near-equal in level (27–29 dB both)
  with only slightly higher distortion late; his ear ranks late > first — a divergence the
  analysis cannot currently rank; his ear wins for design.
- 4 beats after: intense strobing post-drop chase. 2:49.8: another intense growl → full
  blue/cyan strobe.

**Walkthrough 2 — kohta x Bafu — STARsound (pt3)** (hard-hitting euphoric dubstep/trap):
- 0:00→0:52.9 atmospheric: LEDs **twinkle and simmer** (measured: percussion-light, low-band
  attack median 2.3 dB).
- 0:28.1: hidden energy rise begins (= his buildup marker at beat 67, and full-band steps
  9→15 dB — measurable): LEDs ramp and progress (exact animation open).
- 0:52.9: blackout → **explosion of LEDs at the drop** (marker 131): strip fills with
  blue/cyan/white intense strobe sparkles; the drop carries a loud driving low-mid melodic
  element → a dubstep/trap drop variation strobing the room in the track's colors.
- 1:21→1:34.3: atmospheric again (breakdown). 1:34.3: hidden ramp (= buildup marker 195).
- 1:47.5 (breakdown marker 259): "low ends cut out + loud synthy mid-high sustained melodic
  element" → room goes **bright cyan/white with reasonable animation speed** — measured
  note: the sustain is confirmed (sustained-mid 20.4 dB) but the sub reads present
  (29.2 dB) at that exact beat; the "cut" may be the kick (not sub) or sit at a nearby beat.
- 2:00.8 (buildup marker 291): build with the low-profile percussion → buildup cue,
  progressing.
- 2:12.4: **lights cut for 4 beats on an audio dip** — measured note: this dip is a
  RELATIVE full-band drop (~10.3 dB vs ~17 typical), NOT a bottom-gone event (sub still
  25 dB): his "dip" vocabulary sometimes means relative energy drops, which the stored
  `full_db` series shows directly — the blackout/dip consumer needs the relative-dip
  reading alongside the bottom-gone primitive (both derivable from cache, no schema
  change).
- Next 8 beats: **very sparse cyan/white sparkles** until 2:16.5, where the just-introduced
  bass cuts again for 2 beats → **2-beat blackout** (same relative-dip note), then the
  drop at 2:17 (marker 331 ✓).
- Drop 2:17: "mid-high pitched euphoric elements cutting through. Imagine a pack of
  swordfish speeding past you in the ocean." → **energetic strobing cyan/white chase,
  fast, chasing every 0.5 beats.**

**Spec-mapping notes (for the fold-in, not decisions):** his cue vocabulary maps to the
existing v1 library names (rt groove chase / buildup cues / rt drop chase / rt post drop
chase) exactly as the v2 record's shape-vs-color split anticipates; growl-timed accents
within drops = texture seasoning over role cues (operator correction 4 layering holds); the
white-share-scales-with-build-intensity idea gives the buildup cue its measured input; the
animation-rate ladder is the concrete form of "intensity moves with the arc." Three honest
analysis gaps surfaced: chorus-softness recognition (unproven), growl-intensity ranking
(unproven), and relative-dip detection (derivable from stored full_db, needs a consumer
rule — no schema change).

## Appendix E — second follow-up build (2026-07-05): fast low-mid pulse + section map

Operator session: two more wobble labels (Devault — Feels Like Us capochino flip; Dom Dolla —
Girl$ YDG Remix), a ruling that **trap and dubstep get the same lighting expression** (the
drop-type selector's families collapse to three + neutral; the weakest genre distinction
leaves the consumer problem), stereo width deferred, **section-level understanding approved**,
and Murdah (CELO & MO$HCA REMIX) named as a jersey-beat reference (its syncopated kick
placement is visible in the stored quarter-beat slots — patterns like X..X / .XXX; a
syncopation descriptor is derivable later without re-extraction; not built now). Operator
instruction: plan → review → implement. A fresh-context Fable-tier review of the design ran
before implementation: **APPROVE-WITH-REQUIRED-CHANGES**, two blockers both confirmed real
(the persistence constant contradicted the design's own evidence table; the design cited beat
times the cached dataclass does not carry) — every finding folded.

**The wobble investigation, honestly.** The two new labels did NOT pass the LUNCH-validated
fast-LFO rule at 16-beat windows (dilution: their wobble is localized). Hypotheses tested and
rejected on the way: the distortion axis and growl-band *centroid* modulation both fail to
separate slow "grinding wobble" from held bass (the negative control scored higher on
centroid modulation). A 4-beat re-scan found the wobble in both (capochino beats 160–166,
Girl$ 184–188, 2.5–4 cycles/beat). The mandatory re-derivation — running the SHIPPED rule
per-beat on all 8 labeled tracks — then showed the fuller truth: **snare rolls (ILL beats
86–96; Wanna Be's 448–471 build), briddim chug, and SIGNAL's siren all fire the same
detector**, because they genuinely are fast periodic low-mid movement; and the reviewer's
candidate rate-stability gate is *anti*-discriminative (steady rolls hold rate perfectly;
real wobble varies its LFO — the positives would fail it; rejected per its own adoption
condition). Ruling (the class-semantics rule §Appendix C applied again): the detector ships
renamed for what it measures — **`lowmid_pulse_flags` / `lowmid_pulse_measure`**, experimental
— "fast periodic low-mid harmonic movement, ≥2.5 cycles/beat, sustained tone, persistence
≥2 beats (Girl$ fires in 2-beat bursts)". Wobble basses, dense rolls, chugs, and siren sweeps
all exhibit it; for texture seasoning (busy/aggressive), that breadth is arguably correct
behavior; whether it is *acceptable* is the operator scrub gate. Preprocessing is pinned to
the validated math (linearize → mean-remove → Hann → Goertzel at a cycles/beat-native
24-point log grid 0.5–8 c/b, local-window beat conversion, silence guards); constants were
derived from the shipped rule's own outputs on the 8 tracks, not transplanted. The pure-python
scan costs ~0.1 s per track on demand, never at load, never on the push loop.

Measured firing rates (shipped rule): LUNCH 15.1% of beats (drop sections dominate — 0:42.4,
0:45.9, 0:49.7), capochino 4.9% (1:19.3–1:27, 2:21–2:28), Girl$ 4.0% (0:46–0:58, 2:19+);
Can't Say Nah 3.8% (short runs — the known-uncertain case), Wanna Be 4.0% (almost entirely
its 2:48 snare-roll build — the roll confound, visible), ILL 12.1% (chug + rolls).
**Scrub timestamps for the operator (the acceptance gate):** LUNCH 0:42.4 (expect yes),
capochino 1:19.3 (expect yes), Girl$ 0:46.3 (expect yes), Can't Say Nah 0:22.7 (uncertain —
ear rules), Wanna Be 2:48.0 (roll firing the class — is busy-pulse seasoning acceptable
there?).

**SCRUB RESULTS (operator ear, 2026-07-05):** LUNCH 0:42.4 — *dead on* (fast amplitude
wobble confirmed). capochino 1:19.3 — the flag fired on a 2-bar mini-buildup that *does*
sound wobbly (sound-accurate, structural role differs from a drop). Girl$ 0:46.3 — **wrong:
a percussive snare buildup** (the roll confound, now ear-confirmed as a false positive for
wobble semantics). Two ear-identified wobble moments the shipped class MISSES: Girl$ 1:16.1
(high-pitched wobble — the raw measure fires there in isolated windows but the persistence
pass drops them) and the low-end wobbly drop at Girl$ 2:25.6 (flags land 5–6 beats early,
none at the drop itself). Deeper miss, measured: capochino's real drop (1:01.7, after the
0:54.8 rumbly *fake* drop) carries a ". wow wow wow" pattern the operator hears clearly —
the growl-band level there is FLAT (~30 dB across all quarter-slots): the wows are
formant/filter movement (timbre), not level movement, structurally invisible to v4's level
envelopes. **Net class verdict: honest for fast AMPLITUDE wobble only (LUNCH-style);
rolls ear-confirmed as false positives; slow/formant wobble is an open family.** The named
unlock if lights ever need it: a frame-rate growl-band *centroid* series (timbre movement) —
an additive schema field + one overnight re-sweep; deferred per the operator's priority
ruling below.

**LANDED as AWR-176 (implementer p1impl, 2026-07-09; awaiting manager adversarial review +
executive gate + operator scrub):** the frame-rate growl-band centroid series is now
extracted and cached, with a pure derived movement measure over it. Additive only — zero
existing fields or calibration constants changed; pre-AWR-176 entries read the field as
`()` (no signal) until one overnight re-sweep backfills them. Computed-not-consumed: no
consumer wired yet (the lowmid_pulse precedent). New schema field:

| Field | Where | Type | Meaning |
|---|---|---|---|
| `growl_centroid_frames` | `SpectralFeaturesV4` (v4 cache payload) | `tuple[float, ...]` (Hz, frame-rate) | Spectral centroid of the harmonic growl band (60–500 Hz) per STFT frame — WHERE the growl tone sits, same frame clock as `growl_band_frames`. Absent ⇒ no signal. |

Derived layer (`spectral_profile.py`, pure, no numpy): `growl_centroid_movement_measure`
(span_oct / dominant c/b / concentration over a 4-beat window) and `growl_centroid_wobble_flags`;
provisional gates `growl_centroid_min_*` in `SPECTRAL_V4_CALIBRATION` (the only numbers the
named-track calibration pass may tune).

**Operator rulings from the same session (load-bearing for Feature specs):**
1. **Phrase markings are authoritative** — setting them correctly is the operator's own
   responsibility (he fixed Girl$'s markers during this session; the fix flowed through
   immediately with the cache intact, since markers live in ANLZ files, not in the v4
   cache). This refines Appendix D item 4: consumers TRUST markers; no marker-veto logic;
   the F-11 neutral default remains as a safety net only.
2. **Priority: "what really matters is how the lights capitalize on this"** — expression
   over taxonomy; analysis accuracy stays important but is in service of the looks.
3. **Atmospheric-simmer design intent:** Girl$ 1:32–2:12.4 has no percussive elements at
   all (measured: low-band attack median 0.7 dB across those 97 beats vs ~8–15 dB in drop
   sections — the percussion-free signature is derivable from cache) — sections like this
   should read as "lights simmer, more atmospheric" in the v2 feature specs.

**Section map (approved feature).** `section_map()` ships: 16-beat blocks with forced
boundaries at ANLZ markers, single left-to-right merge on a normalized character distance
(engineering scale constants in SPECTRAL_V4_CALIBRATION, annotated), never merging across a
drop marker (a false "chorus up" marker therefore forces a spurious boundary — accepted,
cross-ref Appendix D item 4; a phantom chapter break is a pacing hiccup, not a cue error),
per-section `energy_tier` relative to the track's stored loudness reference (can read
top-heavy on brickwalled masters — stated). Validated by eyeball against known structure on
four tracks: ILL (16 sections — the intro riff blocks, the 97–108 pre-drop empty floor as its
own quiet chapter, both drop phrases loud, the end-of-file silence separated), Chemicals
(12 — the long pad build one coherent section, all drop phrases loud), crank the bass (15 —
quiet intro/breakdown, loud drop phrases split at drop markers by design), LUNCH (10).
Boundaries describe character change; cue timing stays with ANLZ markers and locked designs.

Build state: +13 tests (suite 3,264, zero new failures — the laser-color loader failure
remains the pre-existing baseline one), three docs checks green, contract `key_symbols`
extended (`lowmid_pulse_flags`, `section_map`). `drop_window_vector` accepts precomputed
pulse flags (`pulse_frac`) so consumers pay the scan once. §8 question 3 is superseded by
this appendix: the wobble-class ship condition (more labels) was met, the investigation ran,
and the honest outcome is the renamed experimental class above, gated on the scrub test.

## Appendix F — operator reference descriptions round 2 (2026-07-05; four ear-described tracks checked against shipped measurements, all from cache)

The operator described four tracks' moments in his own words; each description was tested
against the shipped cache data. Agreement is strong on three, partial on one — the miss is a
documented structural limitation, not a threshold bug, and no constants were changed.

1. **Katy Perry vs. SIDEPIECE — I Kissed Girl (Netgate Edit) — near-exact agreement.**
   Operator: tech house, thumpy drums; 4 beats of vocal-filled silence before the drop, then
   a 4-beat bassy horn/wail/growl, then thumpy drums. Measured: `pre_gap_beats = 4` at the
   main drop (beat 192, 1:31.5) — beats 188–191 read bottom-gone with full-band 5–10 dB and
   mids 8–13 dB (music present = the vocals; correctly *not* true silence); beat 191 carries
   the 37.9 dB pickup hit; from beat 192 the growl band jumps to 30–32 dB sustained with
   growl flags on (the horn/wail — flatness 0.29, top-quartile distortion) and the drum
   thump shows as attack spikes (31.5/18.7 dB at beats 199–200). One nuance: the growl-band
   level stays high past his "4 beats" (the bassline continues under the drums) — the
   horn→drums handoff is visible in the attack pattern, not as a growl-flag flip.
2. **Bangarang (BRLLNT Edit) — agreement.** Operator: energetic fast jabby quick horns over
   a syncopating beat rhythm. Measured: onset density 2.8–3.6/beat at every drop (at or
   above the corpus p90 — "fast jabby"), horn body in the mids (sustained-mid 13–15 dB,
   centroid ~350 Hz: brassy-low horns, not bright), and the quarter-beat kick placement
   shifts slot almost every beat (X.../..X./..X./.X../XX.. — the same syncopation signature
   Murdah showed for jersey; his "syncopating rhythm" is directly visible in stored data).
3. **Tomorrow Always Comes (Matias Faint Rmx) — strong agreement, one placement nuance.**
   Operator: 2nd half = long breakdown → long loud synth-heavy build lacking low end →
   4-beat silence with a "woww woww" + snare → grinding gritty bass roar over heavy kicks.
   Measured chapter map: a 96-beat mid-tier section (2:53.9–3:35.7) = the long breakdown;
   section 560–591 has the highest sustained-mid of the track (21 dB, synth-heavy) with the
   sub dropping out through beats 580–586 (the low-end-lacking climax); the roar section
   (4:17.4, beats 592–639) reads growl-flagged throughout with flatness 0.321–0.345 — among
   the highest distortion readings in the corpus — over sub 32 dB and onset density 3–4
   ("grinding gritty roar over thumpy kicks"). Correction from the operator (same day): there is **no audible dip**
   at 4:13–4:14 — that section marks a buildup. The measurement agrees: beats 584–586 are
   bottom-gone but the full-band level holds at ~9–10 dB with the synth wall at ~20 dB
   sustained-mid — only the BASS is absent, the music never dips. The earlier "empty-floor
   stretch" wording overstated it. Consequence folded into the primitive:
   `empty_floor_runs` now returns each run's median full-band level (`level_db`) — a corpus
   scan of all 912 bottom-gone runs showed a smooth unimodal continuum from vocal-over-
   silence (~5 dB, IKG — operator: "silence") to loud bass-less builds (~10 dB, this track —
   operator: "no dip"), so no hard class boundary was drawn (it would overfit two labeled
   points 4 dB apart); darkness consumers set their own level cutoff at the live pass, and
   build sections are excluded by authoritative markers regardless.
4. **Rock Ur World X Lights (Knock2 vs Dabin) — agreement after the operator corrected his
   own description.** Original phrasing ("upper range traveling at light speed in a 4-beat
   pattern") was initially read as melodic arp patterning and reported as a pitch-domain
   gap; the operator then clarified: the "4-beat pattern" is a consistent untz-untz kick
   grid, and "light speed travel" is his metaphor for the mid/high SUSTAIN. Both are
   measured: the drop-1 kick grid is metronomic in the stored quarter-beat slots — every
   beat 112–121 peaks on slot 0 at ~27.7 dB with ~15 dB clearance over the inter-kick
   slots (a perfect four-on-floor) — and the sustain is the window's 20.9 dB sustained-mid
   reading (among the highest drop values in the corpus). Drop 2 (28 beats later) reads
   3.4× the attack (7.5 dB), brighter (centroid 1295 vs 771 Hz), same harmonic content,
   *clean* timbre (flatness 0.156) — a hard-hitting BRIGHT euphoric dubstep drop, not a
   dark growl wall: exactly the distinction his "fan that shoots rainbows" image needs the
   cue selector to see. Recorded as operator design intent for Feature 2: this track
   should be expressed distinctly.

   Two class-threshold observations came out of this check (recorded, deliberately NOT
   retuned on a single track): (a) `kick_prominence_flags` under-reads sidechain-pumped
   four-on-floor under sustained walls (1/28 drop beats flagged) because it keys on attack
   *rise* and this kick is soft-edged (1.5–2.2 dB) while being *level*-dominant on slot 0 —
   the slot-0 dominance pattern in `sub4` is the better untz signature there and is
   derivable without re-extraction; (b) `sustained_synth_flags` misses this wall (2/28)
   because its cleanliness gate (flatness < 0.12) excludes thick layered walls at 0.169.
   Both go to the scrub/live phase before any constant changes.

Cross-cutting: these four descriptions all validated against cache data alone — no
re-analysis. Melodic/pitch-domain structure (note patterns) remains out of v4's scope by
design, but after the operator's correction no described moment in any validation round has
actually required it; everything amplitude/timbre/structure-domain was measurable.
