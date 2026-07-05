---
doc_status: current
truth_level: code-verified + measured-corpus
last_verified_commit: 2945c52
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

Status of this document: written incrementally as the one-shot progresses; a section marked
`PENDING` means that phase has not completed yet in this session.

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

PENDING — written after the research synthesis and prototype measurements on BY GENRE tracks,
then adversarially reviewed before implementation (per prompt execution shape).

## 5. Requirements coverage table

PENDING — every R-item above → the v4 measurements that serve it, or an honest `unreachable`.

## 6. Proofs on the operator's music

PENDING — per-measurement validation on named BY GENRE tracks, timestamped event outlines,
determinism and stability runs, v3-compat bit-identity proof.

## 7. Whole-library sweep results

PENDING — coverage, duration, cache size, stability spot-checks.

## 8. Open questions for Brandon

PENDING — taste calls only, each with a chosen default.

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
