---
doc_status: current
truth_level: code-verified
last_verified_commit: d93f047
last_verified_date: 2026-07-09
validation_scope: >
  Codex implementation spec for AWR-176 (P1 of the AWR-166 spectral upgrade audit):
  one additive extraction field (frame-rate growl-band harmonic centroid), tolerant
  cache read + shape validation, a derived-layer centroid-movement measure
  (computed-not-consumed), and a backfill-aware sweep skip check. Every file:line
  verified at d93f047. Paper only — nothing implemented; implementation gates on
  executive dispatch; any consumer additionally gates on an operator scrub pass.
---

# Codex Implementation Spec - Frame-rate growl-band centroid series (AWR-176 / audit P1)

The v4 analysis stores how LOUD the 60–500 Hz harmonic growl is
(`growl_band_frames`) but not WHERE its tone sits — so filter wobble ("wow wow
wow" wows: the loudness barely moves, the timbre sweeps) is structurally
invisible. This spec adds the one field the design doc itself named as the
unlock: the spectral centroid of the harmonic growl band per STFT frame, plus a
pure derived-layer movement measure over it. Additive only: **zero existing
calibration constants change, zero consumers change, all 41 AWR-147 ear
verdicts are preserved by construction.**

Authority: `docs/research/spectral_upgrade_audit_2026_07_09.md` (P1, §4
recommendation), `docs/research/spectral_audio_analysis_redesign.md` (:960-973
names the blindness and the unlock). Contract: `spectral_analysis` in
`docs/agents/change_contracts.yml` (extension is Task 5 below).

## Part A - Context & Root Cause (verified; read, do not implement)

1. **The blindness [confirmed]** — capochino's real drop (1:01.7) carries wows
   the operator hears; the growl-band *level* there is flat (~30 dB across all
   quarter-slots). Girl$ 1:16.1 / 2:25.6 same. No stored series can express
   timbre movement (redesign :960-973; audit §1.2-1). This is the only audit
   gap the operator has personally heard the system miss on named tracks.
2. **The extraction already has everything needed [confirmed]**:
   - The single-STFT v4 pass computes the HPSS harmonic component `H`
     (`audio_spectral_features.py:294`) and the growl-band power over it
     (`:350-353`, producing `growl_band_frames` at frame rate, `r1` dB).
   - Full-spectrum centroid math already exists one shape away:
     `centroid_frames = (freqs @ S) / max(S.sum(axis=0), floor)` at `:362`.
     The new field is the same formula with `H` band-masked to
     `BAND_RANGES["growl_band"]` (60–500 Hz, `:46`).
   - `frame_hop_s` is already stored (`:422`), so any frame-rate series aligns
     to beats exactly the way `growl_band_frames` does.
3. **Cache mechanics [confirmed]**:
   - `growl_band_frames` is a top-level payload key, not a `V4_SERIES_KEYS`
     entry (`spectral_cache.py:245`, `:297`). The new field mirrors it.
   - The series reader is strict-keyed (`:234-237`) — but a **top-level
     `.get()` read is tolerant by construction**: old entries parse fine and
     simply lack the field. Absent ⇒ no signal (repo invariant).
   - No epoch field exists beyond `schema_version: 4`; changing existing
     field *semantics* is forbidden (audit §2). This change adds a new key
     only — no version bump, no subdir change.
4. **The tolerant-read/backfill trap [confirmed]** — the sweep skips any track
   whose entry parses (`tools/spectral_sweep.py:81-82`). With a tolerant read,
   every old entry still parses, so a plain re-run would skip all 716 entries
   and **backfill nothing**. Task 4 makes the skip check require the new field,
   which turns the ordinary sweep into the backfill run (re-extract →
   `put_cached_v4` overwrites the same key).
5. **Runtime touch points [confirmed]** — at-load extraction on cache miss runs
   on the ANLZ background worker, never the 200 Hz push loop
   (`state_manager.py:252-261`, `:320-335`; grid ≤ `_V4_AT_LOAD_MAX_S = 900.0`
   at `:312`). Old entries (without the field) still load as valid v4 ⇒ the
   runtime does NOT re-extract for them; they gain the field only via the
   sweep or a track/grid change. Acceptable: absent = no signal, and no
   consumer exists yet.
6. **Derived-layer template [confirmed]** — `_goertzel_power`
   (`spectral_profile.py:287-302`), the BPM-independent rate grid
   `PULSE_RATE_GRID_CPB` (`:305-308`), and `lowmid_pulse_measure` (`:311-379`)
   are the validated preprocessing pattern (window slicing by `frame_hop_s`,
   <32-frame guard, silence gate, Hann, Goertzel, concentration).
7. **Scale [confirmed 2026-07-09 on this machine]** — 716 v4 entries / 210 MB;
   32 GiB free disk. Audit's measured estimate: +≈19-25% per entry
   (~+40-55 MB library-wide) **[assumed — an estimate; measure after the
   sweep]**. Sweep margin proven ~10× overnight at library scale (redesign
   :558-573).
8. **[unknown]** — the provisional thresholds in Task 3 (span/concentration
   gates) have never met real data. They are deliberately conservative and are
   the ONLY numbers the named-track calibration pass (Part E) may tune.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- **Out of scope:** every v3 code path; every existing `SPECTRAL_V4_CALIBRATION`
  key/value; `V4_SERIES_KEYS` / `V4_SUB4_KEYS` / `V4_SCALAR_KEYS` contents;
  `SCHEMA_VERSION_V4`; all consumers (`state_manager.py`,
  `lighting_moments_v2.py`, `led_*`, `spectral_profile.py` existing functions
  incl. `lowmid_pulse_*`); cache subdir layout / eviction; the Rekordbox DB,
  ANLZ files, audio files, v3 entries.
- **Behavior that must not change:** every existing field's bytes for a
  re-extracted track except the one new key (determinism: re-extraction of an
  unchanged track must produce identical existing-field values); v3-compat
  block bit-identical; at-load flow shape in `state_manager.py` untouched.
- **Error handling:** extraction failure → `None` (existing contract); cache
  payload with the new key present but mis-shaped → fail closed to `None`
  (entry treated as miss); derived measure over absent/short/silent data →
  `(0.0, 0.0, 0.0)` / all-False, never an exception. No broad try/except
  beyond the existing module patterns.
- No new dependencies. Pure Python in `spectral_profile.py` (no numpy there —
  module rule, `spectral_profile.py:1`).

### Task 1 - `audio_spectral_features.py`: the extraction field
1. Append to `SpectralFeaturesV4` (after `scalars`, `:106`) a **defaulted**
   field so every existing constructor call site (tests, cache reader for
   legacy entries) keeps working:
   ```python
   # frame-rate spectral centroid (Hz) of the harmonic growl band (60-500 Hz);
   # same frame clock as growl_band_frames. () on pre-AWR-176 cache entries —
   # absent reads as no signal. Near-silent frames read ~0.0 Hz by the power
   # floor; the derived layer's level gate excludes them.
   growl_centroid_frames: tuple[float, ...] = ()
   ```
2. In `_extract_v4_measurements`, immediately after `growl_band_frames`
   (`:353`), from the SAME `H` and `freqs` already in scope:
   ```python
   g_lo, g_hi = BAND_RANGES["growl_band"]
   g_mask = (freqs >= g_lo) & (freqs < g_hi)
   Hg = H[g_mask, :]
   growl_centroid = (freqs[g_mask] @ Hg) / np.maximum(Hg.sum(axis=0), _DB_FLOOR_POWER)
   growl_centroid_frames = tuple(r1(v) for v in growl_centroid)
   ```
   and pass `growl_centroid_frames=growl_centroid_frames` in the returned
   dataclass (`:417-435`). Same rounding (`r1`) as the level series.
3. Update the class docstring (`:79-86`) with one line for the new field.

### Task 2 - `spectral_cache.py`: tolerant read, strict shape
1. `_payload_v4_for_write` (`:272-301`): add
   `"growl_centroid_frames": list(features.growl_centroid_frames)`.
2. `_features_v4_from_payload` (`:226-269`), next to the `frames` read
   (`:245`):
   ```python
   cframes = tuple(float(v) for v in payload.get("growl_centroid_frames", ()))
   ```
   After the existing shape checks: if `cframes` is non-empty and
   `len(cframes) != len(frames)`, `raise ValueError("growl_centroid length mismatch")`
   (caught by the existing handler → `None` → treated as a miss → re-extract).
   Pass `growl_centroid_frames=cframes` to the constructor.
3. Nothing else: no version bump, no eviction change, v3 paths untouched.

### Task 3 - `spectral_profile.py`: derived movement measure (new keys ONLY)
1. Append to `SPECTRAL_V4_CALIBRATION` (never touching existing keys):
   ```python
   # Growl-band centroid movement (AWR-176, computed-not-consumed until the
   # operator scrub gate closes — same App-E path lowmid_pulse took).
   # Provisional values; the named-track calibration pass may tune ONLY these.
   "growl_centroid_min_level_db": -70.0,  # growl level p90 silence guard (same convention as lowmid_pulse)
   "growl_centroid_min_span_oct": 0.15,   # p90-p10 travel of log2(centroid), octaves
   "growl_centroid_min_conc": 0.10,       # dominant share of rate-grid power
   "growl_centroid_min_run": 2.0,         # consecutive flagged beats to count
   ```
   Deliberately NO `min_cpb` gate: the 2.5 c/b floor on `lowmid_pulse` exists
   to reject the beat-locked kick, a *level* confound; the centroid series is
   harmonic-component timbre, where that confound does not transfer — the
   negative set in Part E is the check on this assumption.
2. New pure function, mirroring `lowmid_pulse_measure`'s structure exactly
   (`:311-379` is the template — same window slicing, same guards):
   ```python
   def growl_centroid_movement_measure(v4, beatgrid_times_ms, beat) -> tuple[float, float, float]:
       """(span_oct, dominant cycles/beat, concentration) of growl-band
       centroid MOVEMENT over a 4-beat window centered on ``beat``.
       Timbre travel, not level: sees filter wobble the level series is
       blind to. Absent/short/silent data -> (0, 0, 0), never an error."""
   ```
   Pinned math, in order:
   - Guards identical to `lowmid_pulse_measure` (`grid` present, `len == n_beats`,
     `n >= 4`), PLUS: `v4.growl_centroid_frames` non-empty and
     `len(v4.growl_centroid_frames) == len(v4.growl_band_frames)`, else zeros.
   - Same window: beats `[beat-2, beat+2]` clamped; frame slice `i0:i1` via
     `frame_hop_s`; `< 32` frames → zeros.
   - Silence gate on the LEVEL series (the centroid of a silent band is
     meaningless): `percentile(level_seg, 90.0) < cal["growl_centroid_min_level_db"]`
     → zeros, where `level_seg = v4.growl_band_frames[i0:i1]`.
   - Movement series: `o = [math.log2(max(c, 20.0)) for c in v4.growl_centroid_frames[i0:i1]]`
     (20 Hz clamp keeps the ~0.0 Hz silent-frame sentinel finite).
   - `span_oct = percentile(o, 90.0) - percentile(o, 10.0)`.
   - DC removal + Hann + Goertzel exactly as `:355-369`:
     `x[i] = (o[i] - mean(o)) * hann(i)`, powers over `PULSE_RATE_GRID_CPB`
     with the same `cycles < 1.5 or cycles > 0.45*m` skip.
   - `total <= 0` → `(round(span_oct,4), 0.0, 0.0)`; else return
     `(round(span_oct,4), PULSE_RATE_GRID_CPB[top], round(powers[top]/total,4))`.
3. New `growl_centroid_wobble_flags(v4, beatgrid_times_ms) -> list[bool]`
   mirroring `lowmid_pulse_flags` (`:382-411`): per-beat flag when
   `span_oct >= min_span_oct and conc >= min_conc`, then the same
   `min_run` persistence pass. Docstring must say **experimental /
   computed-not-consumed; operator scrub is the acceptance gate** (same wording
   discipline as `:37-41`).
4. NOTHING calls these at runtime in this round.

### Task 4 - `tools/spectral_sweep.py`: backfill-aware skip
Replace `:81-82` with:
```python
cached = spectral_cache.get_cached_v4(track["filepath"], grid)
if cached is not None and cached.growl_centroid_frames:
    return ("cached", track["title"], time.perf_counter() - started)
```
so the standard sweep re-extracts (and overwrites, same key) exactly the
entries missing the new field. No new CLI flag. Update the module docstring's
one-line description of the skip rule.

### Task 5 - Contract + docs (contract-first bookkeeping)
1. `docs/agents/change_contracts.yml` → `spectral_analysis.key_symbols`: add
   `growl_centroid_movement_measure` and `growl_centroid_wobble_flags`.
2. Per that contract's `docs_update`: update
   `docs/research/spectral_audio_analysis_redesign.md` (the :960-973 App-E
   deferral note gains a "landed as AWR-176" pointer + the field's one-line
   schema row) and re-verify `AGENTS.md` (no source-map change expected — same
   files; confirm, don't assume).
3. `docs/status/active_work_registry.md`: flip the AWR-176 row to
   implemented / software-tested wording per §10 status language.

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop gains no I/O and no new work — extraction stays
  at-load-on-miss (ANLZ worker) or offline sweep; nothing re-analyzes per tick.
- v3 cache entries, the v3 extractor, and the v4 compat block stay
  bit-identical (`audio_spectral_features.py:170-177` freeze).
- Absent analysis data reads as no signal, never a false event: pre-AWR-176
  entries keep loading as valid v4 (tolerant read) — the library must NOT
  fail-closed at track load, or every load becomes a 16 s re-extraction.
- Analysis describes sound; no output times or triggers a cue. The new measure
  is computed-not-consumed until the operator scrub gate closes.
- Identity axes and every existing stored field untouched ⇒ no F-9 color
  drift; all 41 AWR-147 verdicts preserved by construction.
- Re-sweep discipline: **never against a mix** (never while the bridge is
  performing), under `caffeinate -i`, `--jobs 2` (8 GB RAM sizing), disk floor
  ≥ 2 GB free before starting (currently 32 GiB — trivially met).
- v4 code never modifies/deletes v3 entries, the Rekordbox DB, ANLZ files, or
  audio files.

## Part D - Tests

Pure-function seam first — the algorithm must be fully testable without
librosa, files, or subprocesses. Follow the hand-built-`SpectralFeaturesV4`
fixture pattern in `tests/test_spectral_profile.py:20-33` (extend `_v4` with a
`growl_centroid_frames` argument defaulting to `()`).

New `tests/test_growl_centroid.py` (or extend `test_spectral_profile.py` /
`test_spectral_cache.py` — Codex's call, match repo convention):

1. **Measure detects synthetic wobble:** centroid frames =
   `2**(7 + 0.3*sin(2π · r · t_beats))` sampled at the fixture frame rate
   (r = 1.0 c/b), level frames flat and loud → `span_oct ≥ 0.4`, dominant
   ≈ 1.0 c/b (nearest grid bin), conc above gate. THE App-E scenario: level
   flat, timbre moving.
2. **Static centroid → no signal:** constant frames → span ≈ 0, flags all
   False.
3. **Silence gate:** level frames below `growl_centroid_min_level_db` → zeros
   even with a moving centroid.
4. **Absent/mismatched field → no signal, never an error:** `()` frames →
   zeros + all-False; length ≠ level series → zeros.
5. **Flags persistence:** a single-beat blip does not flag; a
   `min_run`-length run does (mirror `lowmid_pulse_flags` tests).
6. **Cache tolerant read:** a legacy payload WITHOUT the key round-trips to a
   valid `SpectralFeaturesV4` with `growl_centroid_frames == ()`.
7. **Cache shape validation:** payload with the key present but wrong length
   → `get_cached_v4` returns `None`.
8. **Cache round-trip:** write with the field → read back equal (use
   `RBSS_SPECTRAL_CACHE_DIR` tmpdir, the `tests/test_spectral_cache.py`
   pattern).
9. **Extraction (skip-if-no-librosa, mirroring
   `tests/test_audio_spectral_features.py`'s optional-deps guard):** field
   present, `len == len(growl_band_frames)`, and every pre-existing field of
   the result identical to an extraction of the same input at the parent
   commit's math (determinism check can be a same-process double-extraction
   equality on all pre-existing fields).
10. **Sweep skip logic:** unit-test the new condition — entry with empty
    frames is treated as a miss, entry with frames is "cached" (pure test on
    the condition, no subprocess).

## Part E - Acceptance (definition of done)

- [ ] All new tests green; `python3 -m unittest discover tests` shows ZERO new
  reds vs the named five-environmental-reds baseline (see the AWR-174 registry
  row for the names).
- [ ] Three hard checks green: `check_docs_metadata.py`,
  `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] Task 5 contract + docs updates done (anti-drift rule §7).
- [ ] **Backfill sweep executed** (operator/manager action, NOT Codex; never
  against a mix): `caffeinate -i python3 tools/spectral_sweep.py --jobs 2`.
  Accept when the final counts show the previously-cached library re-extracted
  (`ok` ≈ entry count) and a re-run immediately after reports ≈ all `cached`.
  Record the cache MB delta against the +40-55 MB estimate.
- [ ] **Named-track falsifiable check** (offline, after the sweep — the audit's
  acceptance): capochino's 1:01.7 window and Girl$ 1:16.1 / 2:25.6 show
  centroid movement at the heard wow rate where the level series is flat
  (measure fires); the App-E negative set (rolls, chugs, sirens, static
  sustained bass) stays below the gates. If the provisional constants fail
  this, tune ONLY the four new keys and re-run — existing keys are frozen.
- [ ] **Operator scrub gate before ANY consumer** — flagged spans must be the
  wows he hears. Until then the surface ships computed-not-consumed (the
  lowmid_pulse precedent, F4's `busy_pulse_experimental` containment).

## Future consumer seam (sketch only — OUT OF SCOPE this round)

The wobble-following seasoning consumer arrives in a later round, after the
scrub gate: `DropPlanEntry` grows a `growl_wobble_duty`-style field exactly
like `busy_pulse_duty` (`lighting_moments_v2.py:746` — recorded in the plan,
rendered by nothing), behind an F4-config experimental flag
(`F4Config.busy_pulse_experimental` is the shape, `led_models.py:198`); the
eventual renderer effect is F4 variant-seasoning params (the
`led_dispatch_policy.py:1239-1257` params-only containment). Nothing in THIS
spec builds any of that.

## When You Finish

Report: changed files; full test/check output; the sweep command handed to the
operator with the never-against-a-mix rule restated; which acceptance boxes
remain open (sweep, named-track check, scrub gate).

Plain-language operator summary to relay: "The analysis now also records WHERE
the bass growl's tone sits moment to moment, not just how loud it is — that's
the thing that was blind to your 'wow wow wow' filter wobbles. Nothing the
lights do changes yet: this is the measurement landing first, one overnight
re-scan of the library fills it in, and you get a listening pass before
anything consumes it. Zero risk to anything your ear already signed off —
every existing number is untouched."
