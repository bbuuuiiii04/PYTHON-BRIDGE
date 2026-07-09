---
doc_status: current
truth_level: audit-decision-brief
last_verified_commit: 5c327b1
last_verified_date: 2026-07-09
validation_scope: >
  Read-only audit of the v4 spectral analysis system (extraction, derived layer, cache,
  runtime wiring) against code at HEAD plus the two authority docs; five upgrade proposals
  priced (STEMS evaluated seriously per the operator's ask) and one recommended. Analysis
  and web research only — no code, cache, config, or runtime change; implementation gates
  on executive + operator. Machine facts (M2, 8 GB RAM, Python 3.14.6, no torch) verified
  on this Mac 2026-07-09.
---

# Audio spectral analysis upgrade — audit, five proposals, one recommendation (AWR-165)

**Operator ask (verbatim):** "audit and review the audio spectral analysis and determine
if it should be kept as is, or if we could genuinely benefit from changing it to something
else, maybe even STEMS. have it propose 5 changes and recommend one, report back to me."

**Method.** Code read directly at HEAD `5c327b1` (`audio_spectral_features.py`,
`spectral_profile.py`, `spectral_cache.py`, `state_manager.py` spectral sites,
`tools/spectral_sweep.py`); authority docs digested and spot-verified at source
(`docs/research/spectral_audio_analysis_redesign.md`,
`docs/research/spectral_calibration_expansion_2026_07_08.md`); repo-wide consumer sweep;
web research on 2025–2026 source-separation tooling. Code wins over docs throughout.

---

## 1. Audit — what v4 is and what it actually does

One brief-correction up front, from code: the runtime is **not** strictly
cache-read-only. On a cache miss at track load, `state_manager.py:249-253` and `:308-312`
call `extract_spectral_features_v4` directly for grids ≤ 900 s
(`_V4_AT_LOAD_MAX_S`, `state_manager.py:290`) and write the result back — on the ANLZ
background thread (`state_manager.py:2236`), never the 200 Hz push loop. The honest
invariant: **extraction happens at track-load-on-miss or in the offline sweep; nothing
re-analyzes per-tick.** Any proposal whose extraction cannot run in a few seconds per
track (stems cannot) must therefore be optional-at-load and offline-sweep-only.

### 1.1 What v4 does well (evidence)

- **Measurement/interpretation split, enforced in code.** The cache stores only raw
  absolute-dB measurements; every class and threshold lives in the pure-Python derived
  layer (`spectral_profile.py:21-58` `SPECTRAL_V4_CALIBRATION`), so classes re-tune
  without re-extraction, and threshold-dependent scalars are derived at load, never
  persisted (`spectral_profile.py:91-101` — the F-9 hazard closure, redesign doc :188).
- **Ear-validated at scale, zero constants changed.** AWR-147: 41 operator verdicts over
  5 rounds at 545-track/4211-drop scale; every §6.5 corpus claim reconfirmed; all six
  named acceptance anchors reproduce exactly; `SPECTRAL_V4_CALIBRATION` untouched
  (calibration doc :62-88, :159, :268).
- **Corpus-proven discrimination.** Held-out genre discrimination 58.7% vs 16.7% chance
  on 1,086 untouched drop windows (redesign :472-486); identity-axis stability all inside
  or above the v3 band — the F-9 gate (redesign :467-470).
- **Deterministic and compat-frozen.** v3 math frozen verbatim
  (`audio_spectral_features.py:170-177`), run-over-run determinism and 60/60 runtime↔sweep
  cache-key parity measured (redesign :402-438).
- **Operationally proven.** Whole-library sweeps at 100% of decodable gridded tracks with
  ~10× overnight margin (redesign :558-573); 716 v4 entries / 210 MB on disk now; sweep
  tool is resumable-by-skip (`tools/spectral_sweep.py:81-82`), sized for this 8 GB machine
  (`--jobs 2` default, one BLAS thread per worker).
- **Consumption discipline.** At HEAD the runtime consumes exactly three surfaces:
  v3-compat envelopes → smart-drop energy shadow (`state_manager.py:268-284`),
  `identity_axes` + `sustained_synth_flags` → LED color identity
  (`state_manager.py:339-349`). Everything else (drop-window vector, texture flags,
  section map, lowmid_pulse) is design-only until F2/F4 consume it at plan time — exactly
  what the F2 spec does (`docs/plans/active/lighting_engine_v2_f2_spec.md` Part A.1
  consumes `drop_window_vector`; missing cache ⇒ empty plan ⇒ no-op).

### 1.2 Where v4 honestly fails (evidence, verified at source)

1. **Formant/filter wobble is structurally invisible.** capochino's real drop (1:01.7)
   carries a ". wow wow wow" the operator hears clearly; the growl-band **level** there is
   flat (~30 dB across all quarter-slots) — the wows are filter/timbre movement, not level
   movement (redesign :960-973). Girl$ 1:16.1 and 2:25.6 similarly missed. This is a
   *blindness*, not a mis-threshold: no stored series can express it. The design doc names
   the unlock: a frame-rate growl-band **centroid** series — "an additive schema field +
   one overnight re-sweep; deferred per the operator's priority ruling" (redesign
   :971-973).
2. **Slow beat-locked wub invisible to `lowmid_pulse`.** You&Me's "straight wobbly bass"
   fires 0/32 window beats: duty passes (0.79–0.94) but the dominant modulation rate
   measures 0.5–1.9 cyc/beat, under the 2.5 cyc/beat gate that exists to reject the kick
   confound (calibration :227). The measure itself already sees these rates — the grid
   spans 0.5–8.0 cyc/beat (`spectral_profile.py:306-308`) — the *class* gates them out.
   Breadth is also honest: rolls/chugs/sirens all fire it (redesign :938-947). F4 ships it
   computed-not-consumed behind a flag (F4 spec :38-44, :136).
3. **Chorus-softness and growl-intensity ranking unproven.** CSN chorus-3 reads nearly
   identical to drop-1 on window means where his ear hears softer; two growls measure
   27–29 dB near-equal where his ear ranks one clearly harder (redesign :858-871).
4. **kick_prominence under-reads sidechained four-on-floor** (1/28 drop beats on the App F
   track — it keys on attack *rise*; pumped kicks are soft-edged/level-dominant). App F
   names the better signature: slot-0 dominance in the stored `sub4` pattern, "derivable
   without re-extraction" (redesign :1064-1069). **sustained_synth's flatness gate
   excludes thick layered walls** (0.169 vs the 0.12 gate, redesign :1069-1070) and its
   semantics diverge from operator "synth" in both directions — it counts vocals; valid
   only as a clean-euphoric proxy (calibration :229). Both consumed as weak signals only.
5. **Tier scorer misses (~6 of ~15 graded, both directions, era/hardness-clustered).**
   Under-reads cluster on older/quieter masters (Tremor: corpus-absolute level terms
   suppressed). The consumer redesign is already owned by F2 (AWR-163 Part A.2,
   family-conditional percentiles + runway damping). The *feature-side* question — do the
   stored measures suffice for that redesign? — is answered yes with one watch-item: the
   per-track `loudness_ref_db` scalar (p95 full-band) is stored and enables track-relative
   level terms; if A.2's Tremor fixture still under-reads after family conditioning, a
   loudness/era-robust feature becomes a real gap (today it is not proven to be one).
6. **ANLZ marker quality:** 14/1,264 (1.1%) flagrantly false drop markers (redesign
   :813-824). Operator ruling stands: markers are authoritative for WHEN; analysis
   dresses, never schedules. Not an analysis defect; containment is F2's neutral default.
7. **No vocal axis exists at all.** Nothing in v4 can distinguish vocal harmonic energy
   from synth harmonic energy — the root of gap 4's semantics and a plausible ingredient
   in gap 3 (chorus softness ≈ vocal-led, layer-thin sections). This is the one gap that
   band-level features cannot close even in principle; it is the honest case for stems.

---

## 2. Verdict: KEEP v4 as the backbone — change by addition, not replacement

Argued: (a) the calibration bedrock — 41 ear verdicts + the corpus proofs — anchors to
v4's stored measures; replacing the measurement layer re-opens all of it, and operator
listening time is the scarcest resource this repo has. (b) The architecture was built for
exactly this moment: raw measures in cache, interpretation pure and re-tunable, additive
fields explicitly anticipated (versioned cache subdirs, `spectral_cache.py:1-8`).
(c) Every named gap except the vocal axis is closable *additively* — two of them without
touching extraction at all. (d) The system is not under-delivering at runtime: what the
bridge renders from today (identity + energy shadow) works; the wider surface is waiting
on F2/F4 consumers, not on better analysis.

One structural note for any additive field: the v4 payload reader is strict-keyed —
adding a key to `V4_SERIES_KEYS` makes every existing cache entry fail closed on read
(`spectral_cache.py:234-251`), falling back to at-load extraction per track. An additive
field therefore ships with either (i) a tolerant `.get()` read + absent-means-no-signal,
or (ii) a planned overnight re-sweep (proven cheap, ~10× margin) — the design doc already
prices the re-sweep path. There is no epoch field beyond `schema_version: 4`, so changing
the *semantics* of an existing field would silently mix old/new entries — forbidden; new
semantics ⇒ new key or v5 subdir (this is the F-9 identity-drift concern made concrete).

---

## 3. Five proposed changes

### P1 — Frame-rate growl-band centroid series (the named App-E unlock)

- **What:** one additive extraction field: the spectral centroid of the harmonic 60–500 Hz
  band per STFT frame (~43 Hz rate), stored alongside the existing `growl_band_frames`
  level series; plus a derived-layer wobble-timbre measure over it (same Goertzel
  machinery `spectral_profile.py:287-302` reused on centroid movement instead of level).
- **Gap closed:** the formant/filter-wobble blindness (§1.2-1) — the only gap the operator
  has directly *heard* the analysis miss on named tracks; also gives Girl$ 1:16.1/2:25.6
  a signal, and a timbre-movement channel that P2's level-based class cannot see.
- **Cost:** ~1 band-masked centroid per frame inside the existing single-STFT pass
  (extraction already computes full-spectrum `centroid_hz`; this is the same math on the
  H-component band mask) + one schema key + one overnight re-sweep (proven: 711 tracks
  with ~10× margin). Cache: measured +≈19% per entry (~+40 MB library-wide; frame-rate
  series are 19% of today's 317 KB average entry). No new dependencies.
- **Calibration risk:** additive. No existing field changes; identity axes untouched (no
  F-9 drift); all 41 verdicts preserved by construction. New class needs its own operator
  scrub gate before anything consumes it (same path App E used for lowmid_pulse).
- **F2 interaction:** none required now — F2 reads existing fields only. The re-swept
  entries remain byte-compatible for F2 if the new key reads tolerantly (`.get()`), which
  is the recommended shape; stragglers fill by at-load extraction.
- **Falsifiable acceptance test:** on capochino 1:01.7 and Girl$ 1:16.1/2:25.6 the
  centroid series shows periodic movement at the heard wow rate where the level series is
  flat; on the App-E negative set (rolls, chugs, sirens, static sustained bass) the
  centroid-movement measure stays below threshold; operator scrub verdict confirms the
  flagged spans are the wows he hears.

### P2 — Slow-wub class extension (derived layer only, zero extraction change)

- **What:** a second, separately-named class over the *existing* cached
  `growl_band_frames`: extend classification below the 2.5 cyc/beat gate (the measure
  already returns 0.5–1.9 cyc/beat rates) with an explicit kick-confound rejector —
  e.g. exclude modulation bins at/near 1.0 and 2.0 cyc/beat when the beat-locked kick
  pattern (sub4 slot-0 dominance) is simultaneously present, or require the modulation to
  persist through bottom-gone beats where no kick exists.
- **Gap closed:** the named false negative (You&Me 0/32, §1.2-2) — classic slow
  beat-locked wub becomes visible as its own class; the existing `lowmid_pulse` class and
  its constants stay untouched.
- **Cost:** pure Python in `spectral_profile.py` + a calibration pass on the existing
  labeled set (You&Me positive; App-E negatives + four-on-floor tracks). No re-sweep, no
  cache change, no dependencies, no schema key.
- **Calibration risk:** zero to existing verdicts (new function, pinned constants
  untouched). Honest ceiling: it sees amplitude wub only — formant wobble (P1's target)
  stays invisible; and the kick confound below 2.5 cyc/beat is exactly why the original
  gate exists, so the rejector is the make-or-break and may fail (that is the experiment).
- **F2 interaction:** none — F4 (not F2) owns this surface and already ships it
  computed-not-consumed behind `texture.busy_pulse_experimental` (F4 spec :38-44); the new
  class rides the same flag.
- **Falsifiable acceptance test:** You&Me drop window fires on ≥half its beats; all App-E
  negatives and a four-on-floor control set fire 0 beats; the operator scrub confirms
  flagged spans are wub, not kick.

### P3 — Kick/untz signature from stored sub4 patterns (derived layer only)

- **What:** the App-F-named "slot-0 dominance" class: per beat, kick presence read from
  the quarter-beat shape of the stored `sub4["sub"]`/`sub4["bass"]` slots (slot 0 loud,
  slots 2–3 decayed = untz; flat = sustained; pumped-but-periodic = sidechained
  four-on-floor) instead of attack-rise alone.
- **Gap closed:** kick_prominence's sidechain under-read (1/28 on the App F track,
  §1.2-4); also hands F2's family/tier machinery a cleaner four-on-floor recognizer and
  P2 its kick-rejector input.
- **Cost:** pure Python in `spectral_profile.py`; calibration against a handful of labeled
  tracks (the App-F wall track, classic big-room, trap sparse-kick controls). No re-sweep,
  no cache change, no deps.
- **Calibration risk:** zero to existing verdicts — additive class; the existing
  `kick_prominence_flags` and its constants stay as-is (consumed as weak signals only).
- **F2 interaction:** optional and additive — A.2's redesigned tier scorer may take it as
  an input later; nothing in the released F2 spec depends on it.
- **Falsifiable acceptance test:** the App-F sidechained track flags kick-led on most drop
  beats (vs 1/28 today) while trap tracks with sparse kicks and bass-sustain tracks with
  no kick stay unflagged; even/odd-beat split stability across the corpus ≥ the 0.902
  identity bar for a per-track kick-duty scalar derived from it.

### P4 — STEMS: per-stem envelopes from an offline separation sweep (evaluated seriously)

- **What:** a one-time offline sweep separating each track into 4 stems
  (drums/bass/vocals/other) with an HTDemucs-class model, then storing only coarse
  per-stem per-beat + quarter-beat dB envelopes as additive cache fields (stem audio
  discarded per track). Runtime never separates; at-load behavior unchanged
  (absent-means-no-signal).
- **Gaps closed (this is real):** the only proposal that creates a **vocal axis**
  (§1.2-7) — fixing `sustained_synth`'s vocal-counting semantics and giving
  chorus-softness (§1.2-3) its most plausible ingredients (vocal-led + layer-thin);
  drums-stem envelopes replace the HPSS `perc_full` proxy where it misreads melodic
  plucks as percussive; drums+bass stems see the sidechained kick directly (§1.2-4).
- **Cost (measured against THIS machine — Apple M2 base, 8 GB RAM, Python 3.14.6):**
  [PENDING-RESEARCH]
- **Calibration risk:** additive if stored as new fields in a separate namespace (stems
  fields must never share keys with v4 measures; own subdir or tolerant keys) — the 41
  verdicts stand because no v4 field changes. But every stem-derived class starts
  unvalidated: new operator listening rounds are the gate, and separation artifacts
  (bleed, vocal ghosting) are a new error source the ear never signed off on.
- **F2 interaction:** none now (F2 consumes existing v4 fields). Future consumers gain a
  vocal/drums channel. Identity axes untouched — no F-9 drift.
- **Falsifiable acceptance test:** on AWR-147's already-labeled tracks: (i) vocals-stem
  presence separates the pad-wall track the operator called "not really synth heavy" from
  the gritty tracks he called synth-heavy (the both-directions semantic failure,
  calibration :229); (ii) drums-stem envelope flags the sidechained four-on-floor beats
  the attack measure missed (1/28 → majority); (iii) a chorus-softness measure built on
  vocal-share + layer-thickness ranks CSN chorus-3 softer than drop-1, matching his ear.
- **Verdict on stems:** [PENDING-RESEARCH]

### P5 — Replace the measurement layer with learned audio embeddings (the "something else" pole)

- **What:** swap hand-built band measures for a pretrained music tagger/embedding model
  (PANNs/CLAP-class): per-window embeddings + tag probabilities as the feature surface,
  classes learned or thresholded on top.
- **Gap closed:** in principle, semantic gaps (vocalness, softness, aggression) without
  hand-built proxies.
- **Cost:** heavy — a torch-class dependency for every future sweep, embedding cache,
  and a full rebuild of every class and threshold.
- **Calibration risk:** **breaking.** Every one of the 41 verdicts and all corpus proofs
  anchor to v4's stored measures; an embedding surface restarts calibration from zero and
  its axes are opaque — when a class misfires, there is no "the growl band was flat"
  explanation to debug against, and no operator-explainable knob to re-tune. The
  identity-epoch problem lands in full: Feature-1 zone colors would drift unless the v4
  identity path is preserved anyway (making this an add-on, not a replacement, at which
  point P4 covers the same semantic ground cheaper and more explainably).
- **F2 interaction:** F2's released spec consumes v4 fields; a replacement forces a
  respec. Rejected on the evidence; documented because the operator asked what "something
  else" would cost.
- **Falsifiable acceptance test (if ever revisited):** an embedding-based classifier must
  beat the v4-derived classes on the SAME held-out labeled set (genre discrimination,
  tier agreement, the 41-verdict fixtures) by a margin that pays for re-validating the
  full calibration — measurable, and today unmet by any evidence in this repo.

---

## 4. Recommendation

[PENDING-RESEARCH]

---

## 5. Plain-English summary (operator-readable, relay verbatim)

[PENDING-RESEARCH]

---

## Bookkeeping

- Registry row: AWR-165 (this audit), `docs/status/active_work_registry.md`.
- Doc index row: this file, RESEARCH / AUDIT.
- Hard checks: `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`
  — run green before commit.
