---
doc_status: draft-for-review
truth_level: planned
last_verified_commit: 5cd2fda7
last_verified_date: 2026-07-24
validation_scope: >
  Codex implementation spec for stage E1 of the energy-fabric ladder
  (docs/plans/active/energy_fabric_ladder_spec_v1.md §B.1/§B.6, EFREV ruling
  READY with note N3 applied). Offline tooling ONLY: a pure descriptor module +
  a read-only report tool + tests. ZERO runtime changes — the bridge stays
  byte-identical. Authored by the E1SPEC seat (exec4 dispatch 2026-07-24); all
  code claims verified at HEAD 5cd2fda7. Awaiting exec review + operator gate
  before Codex executes. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Codex Implementation Spec - Energy E1: library track weight (offline, gain-invariant)

Parent design: `docs/plans/active/energy_fabric_ladder_spec_v1.md` §B.1 (Layer 1)
and §B.6 stage E1. Review input: `local/spectral_v5_2026_07_17/EFREV_review.md`
note N3 — this spec (a) corrects the parent's "percentile absorbs offsets"
wording and (b) pins a NUMERIC acceptance threshold for the loudness-vs-weight
correlation check. Nothing here may touch runtime behavior.

## Part A - Context & Root Cause (verified; read, do not implement)

Every claim below was re-read at HEAD `5cd2fda7` on 2026-07-24 and is
[confirmed] unless labeled otherwise.

### A.1 What exists

- **The v4 feature store.** Per-track, per-beat spectral features cached on
  disk: entries at `<cache_dir>/v4/<sha1-key>.json`, where `<cache_dir>` is
  `~/Library/Application Support/RBSS Bridge/spectral_cache` or the
  `RBSS_SPECTRAL_CACHE_DIR` override (`spectral_cache.py:32-34, 214-223`).
  The key is sha1 over (realpath, mtime_ns, size, beatgrid fingerprint)
  (`spectral_cache.py:337-352`). Reader API: `get_cached_v4(audio_filepath,
  beatgrid_times_ms)` (`spectral_cache.py:142-155`). Versioning convention:
  every schema version owns its own subdirectory and eviction never crosses
  versions (`spectral_cache.py:3-7`).
- **The v4 shape.** `V4_SERIES_KEYS` (`audio_spectral_features.py:116-123`):
  per-beat `sub_db, bass_db, lowmid_db, mid_db, high_db, air_db, full_db,
  growl_band_db, sustain_mid_db, sustain_high_db, growl_flatness, centroid_hz,
  perc_low, perc_mid, perc_high, perc_full, attack_db, attack_low_db,
  onset_density, onset_density_midhigh, fluxsum_midhigh`. `V4_SCALAR_KEYS`
  (`:125-127`) include `loudness_ref_db`.
- **The per-track loudness reference already exists.**
  `loudness_ref_db = p95(full_db_beats)` (`audio_spectral_features.py:423`).
  The repo already builds loudness-RELATIVE measures on it:
  `section_map()` tiers sections by `level < ref + section_quiet_offset_db`
  (offsets −8.0 / −3.0 dB, `spectral_profile.py:63-64`, use at `:599-608`).
  This is the canonical in-repo gain-invariance mechanism E1 must reuse.
- **Structurally level-independent series exist.** `onset_density` /
  `onset_density_midhigh` are onset COUNTS per beat
  (`audio_spectral_features.py:408-409`, `_onset_counts`), and
  `growl_flatness` is a spectral-flatness RATIO (`:369-372`). [confirmed at
  construction level; extractor-level level-independence of onset picking is
  [assumed] to first order — the unit test in Part D operates on cached
  features, where it is exact.]
- **Enumeration prior art.** `tools/spectral_calibration_report.py` is the
  read-only offline corpus tool to mirror: runs from the parent directory
  (`sys.path.insert(0, …parents[2])`, `:36`), imports the package (`:38-40`),
  opens the Rekordbox DB read-only via pyrekordbox (`_open_db`, `:54-60`),
  enumerates on-disk non-deleted tracks + the BY GENRE playlist folder
  (`_enumerate`, `:63-92`; folder id `666898931`, `RAP` excluded, `:44-45`),
  reads each track's beatgrid from ANLZ (`read_anlz_drops`, `:383-387`), and
  loads features with `get_cached_v4(t["filepath"], grid)` (`:389`).
- **The zero-runtime-importer pattern.** `hardness_v0.py` (repo root, offline,
  zero runtime importers) is enforced by a static test that scans every repo
  `*.py` and fails if any non-`tools/`/`tests/` module imports it
  (`tests/test_hardness_v0.py:399-419`). `approach_features_v0.py` follows the
  same discipline. E1's module copies this pattern exactly.
- **Contract.** `docs/agents/change_contracts.yml` key `spectral_analysis`
  (line 698): code_globs cover the spectral modules and offline tools;
  `docs_update` = `docs/research/spectral_audio_analysis_redesign.md` +
  `AGENTS.md`; forbidden assumptions include "analysis outputs describe sound;
  no output may time or trigger a cue", "every future schema version gets its
  own cache subdirectory", and "**calibration statistics and validation claims
  use BY GENRE playlist tracks only**" — which binds this spec's acceptance
  statistic to the by_genre split.

### A.2 What does NOT exist (the gap E1 fills)

- No code anywhere computes a track's energy weight relative to the whole
  library; `identity_axes()` (`spectral_profile.py:118-125`) is absolute
  per-track. [confirmed by absence at the parent-spec round, re-checked]
- **Why `bass_duty` cannot be the weight input (N3's trap, made explicit):**
  `bass_duty()` counts beats over an ABSOLUTE calibrated dB threshold
  (`SPECTRAL_V4_CALIBRATION["bottom_gone_sub_db"]`,
  `spectral_profile.py:98-108`). A per-track mastering offset moves every
  beat relative to that fixed threshold, so a quieter-mastered harder track
  scores a lower duty. This is a deliberate, explained deviation from the
  reuse-existing-measures default: E1 defines loudness-RELATIVE duties
  instead, reusing the `loudness_ref_db` + relative-offset mechanism the repo
  already uses for section tiers.
- **Corrected invariance statement (fixes the parent's B.1 wording per N3):**
  ranking against the library absorbs only LIBRARY-WIDE level offsets.
  Per-track mastering offsets are handled one level down: every dB-based
  component is computed relative to the track's own `loudness_ref_db`, so a
  uniform per-track offset shifts numerator and reference together and cancels
  exactly. The percentile rank then only ever sees gain-invariant component
  values. No absolute-dB feature may enter the aggregate.

### A.3 Deliverable shape (three new files, one artifact namespace)

1. `track_weight_v0.py` — repo root, PURE math, no I/O, zero runtime
   importers (hardness_v0-style).
2. `tools/track_weight_report.py` — read-only enumeration + store writer +
   human report (calibration-report-style).
3. `tests/test_track_weight_v0.py` — unit tests incl. the gain-invariance
   test and the importer guard.
Artifact: `<cache_dir>/trackweight_v1/track_weight_store.json` — a NEW
version-owned namespace beside `v4/`, per the cache versioning convention.
Nothing runtime reads it in E1 (consumers arrive in E2+ under their own
specs).

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- **ZERO runtime changes.** Do not edit any existing repo-root runtime module,
  any `led_*`/`laser_*`/`state_manager`/`config` file, or anything under
  `config/`. The bridge process must be byte-identical after this work. Do not
  start the bridge.
- Out of scope: `spectral_cache.py`, `spectral_profile.py`,
  `audio_spectral_features.py` (READ their APIs, change nothing);
  the Rekordbox DB (read-only via pyrekordbox, never write); ANLZ files and
  audio files (read-only); the v3/v4 cache dirs (never write/delete there —
  the tool creates ONLY `trackweight_v1/`).
- No new dependencies. pyrekordbox is imported lazily inside the tool exactly
  like `tools/spectral_calibration_report.py:54-60`; its absence is a clear
  startup error, not a silent skip. `track_weight_v0.py` imports stdlib only.
- Error handling: per-track failures (no grid, no v4 entry, insufficient
  beats, non-finite values) are COUNTED and reported, never fabricated around;
  missing DB/deps fail the run with a named error; the store is written
  atomically (tempfile + `os.replace`, the `put_cached_v4` pattern,
  `spectral_cache.py:173-196`) or not at all. No broad try/except.
- **No threshold tuning to pass acceptance.** If the Part-D acceptance gate
  fails on the real library, report the failure and stop — changing any pinned
  constant is a spec amendment for the exec, not an implementation decision.
- Do not use destructive git; work tree may be dirty with others' files —
  never revert or clean anything you did not author.

### Task 1 - `track_weight_v0.py` (new; pure descriptor math)

Module docstring must carry the hardness_v0-grade honesty block: OFFLINE
ONLY, zero runtime importers (tools/ + tests/ only, static test enforces),
describes sound, never times or triggers a cue, decides nothing live;
`None` on missing/short/malformed data — never a fabricated weight.

Constants (pinned; changing any is a spec amendment):

```python
REL_BODY_OFFSET_DB = -8.0    # reuse of the section_quiet_offset_db precedent
REL_SUB_OFFSET_DB = -12.0    # [assumed] sub-presence floor below the track's own p95
MIN_BEATS = 64               # tracks shorter than 16 bars yield None
COMPONENT_KEYS = ("body_duty", "sub_duty", "onset_mh_mean", "growl_flatness_mean")
SPEARMAN_ACCEPT_MAX = 0.50   # |rho| gate, by_genre split (Part D rationale)
MIN_ACCEPT_N = 100           # by_genre tracks required for the gate to be meaningful
```

Functions (exact signatures; all pure, stdlib only, no numpy):

- `components(v4: SpectralFeaturesV4) -> Optional[dict[str, float]]`
  - `ref = float(v4.scalars["loudness_ref_db"])`; return `None` if the key is
    missing, `v4.n_beats < MIN_BEATS`, or any consumed value is non-finite.
  - `body_duty` = fraction of beats with `full_db[i] >= ref + REL_BODY_OFFSET_DB`
  - `sub_duty` = fraction of beats with `sub_db[i] >= ref + REL_SUB_OFFSET_DB`
  - `onset_mh_mean` = arithmetic mean of `series["onset_density_midhigh"]`
  - `growl_flatness_mean` = arithmetic mean of `series["growl_flatness"]`
  - Gain-invariance by construction: the two duties compare dB series against
    the track's OWN reference (offset cancels); the other two are count/ratio
    series untouched by level.
- `rank_in(sorted_values: Sequence[float], value: float) -> float` —
  mid-rank percentile in [0,1]: `(count_less + 0.5 * count_equal) / n`;
  `0.5` when `n == 0` is FORBIDDEN — return `None`? No: callers must not call
  it with an empty distribution; raise `ValueError` (programming error, not
  data condition).
- `build_distribution(all_components: Sequence[dict[str, float]]) -> dict[str, list[float]]`
  — per component key, the sorted list of library values.
- `track_weight(comp: dict[str, float], distribution: dict[str, list[float]]) -> float`
  — mean of the four `rank_in` percentiles. Equal weights, pinned.
- `spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]` —
  Spearman rho with average ranks for ties (rank both lists with mid-ranks,
  then Pearson on the ranks). Return `None` if `len < 3`, lengths differ, or
  either side is constant (zero variance). Pure stdlib (CI runs Python 3.11,
  so `statistics.correlation(method="ranked")` — 3.12+ — must NOT be used).
- `degenerate_components(distribution: dict[str, list[float]]) -> list[str]` —
  component keys whose sorted library values have `p25 == p75` (zero IQR:
  ranking on them is noise). Uses `spectral_profile.percentile`-equivalent
  logic reimplemented locally (do NOT import spectral_profile — that would
  couple the shadow module to runtime code; a 6-line local percentile is
  correct here).

### Task 2 - `tools/track_weight_report.py` (new; read-only sweep + store + report)

Mirror `tools/spectral_calibration_report.py` structure exactly:

- Same parent-dir bootstrap (`sys.path.insert(0, str(Path(__file__).resolve().parents[2]))`),
  then `from rb_ss_bridge_v2 import spectral_cache` and
  `from rb_ss_bridge_v2.track_weight_v0 import …` and
  `from rb_ss_bridge_v2.anlz_reader import read_anlz_drops`.
- Reuse the enumeration verbatim-in-pattern: `_open_db()` (pyrekordbox lazy
  import, `unlock=True`, read-only usage), `_enumerate()` (on-disk non-deleted
  tracks; BY GENRE folder id `666898931`, exclude `RAP`) — copy the shapes
  from `tools/spectral_calibration_report.py:54-92`; per track read the ANLZ
  beatgrid and call `spectral_cache.get_cached_v4(filepath, grid)`
  (pattern at `:377-397`).
- Per track with a v4 entry: `comp = components(v4)`; count and list
  `no_grid` / `no_v4` / `insufficient` (comp is None) separately.
- Build `distribution` over ALL scored tracks (the vision's axis is the ENTIRE
  library); compute each track's `track_weight`.
- **Acceptance gate (pinned, N3):** on the by_genre split only (contract law:
  calibration statistics use BY GENRE tracks only), compute
  `rho = spearman([loudness_ref_db per track], [track_weight per track])`.
  The run is **ACCEPTED** iff ALL of:
  1. `n_by_genre_scored >= MIN_ACCEPT_N` (else named failure
     `insufficient_corpus`);
  2. `rho is not None and abs(rho) <= SPEARMAN_ACCEPT_MAX` (else
     `loudness_proxy`);
  3. `degenerate_components(distribution) == []` (else `degenerate_component`).
  Library-wide rho is computed and printed as INFORMATIONAL only.
- Store write (atomic, `put_cached_v4` tempfile+replace pattern) to
  `spectral_cache._cache_dir() / "trackweight_v1" / "track_weight_store.json"`:

```json
{
  "schema_version": 1,
  "generated_unix": <int time.time()>,
  "accepted": true|false,
  "acceptance": {"reason": "ok|insufficient_corpus|loudness_proxy|degenerate_component",
                  "spearman_by_genre": <float|null>, "threshold": 0.5,
                  "n_by_genre": <int>, "spearman_library": <float|null>,
                  "degenerate": []},
  "constants": {"rel_body_offset_db": -8.0, "rel_sub_offset_db": -12.0,
                 "min_beats": 64, "component_keys": [...]},
  "distribution": {"<component>": [sorted floats]},
  "tracks": {"<cache_key>": {"filepath": "...", "content_id": "...",
              "title": "...", "components": {...}, "track_weight": <float>}}
}
```

  The store is ALWAYS written (accepted true or false) so the evidence is
  inspectable; E2+ consumers are specified to refuse `accepted: false` stores
  (their specs, not this one). Keyed by the v4 cache key so a later at-load
  lookup is the same key computation the cache already does; `filepath` +
  `content_id` ride along for debuggability. The store lives in the cache dir
  (machine-local), NEVER in the repo; never commit it.
- Report to stdout (and `--out <path>` optional copy): counts, acceptance
  verdict + reason + both rhos, five-number summaries (min/p25/p50/p75/max)
  per component and for track_weight, top 15 / bottom 15 tracks by weight
  (title + weight), and per-BY-GENRE-playlist median weight (descriptive
  genre-anchor sanity — the operator can eyeball that e.g. dubstep playlists
  sit high and deep-house ones low; no labels are solicited, reading it is
  optional, silence is a pass).
- Exit code: 0 when ACCEPTED, 1 when not (named reason printed), 2 on
  environment errors (no DB, pyrekordbox missing, cache dir absent).
- CLI: `--cache-dir` (defaults to the env/default resolution the package
  already does — pass through by setting nothing and letting
  `spectral_cache._cache_dir()` resolve; an explicit flag sets
  `RBSS_SPECTRAL_CACHE_DIR` in-process before use), `--out`, `--limit N`
  (dev-only truncation of the track list, clearly marked in output as a
  NON-ACCEPTABLE partial run: acceptance is forced false with reason
  `partial_run` when `--limit` is set).

### Task 3 - `tests/test_track_weight_v0.py` (new)

Fixtures: build synthetic `SpectralFeaturesV4` in-memory (reuse the fixture
helper style already in `tests/test_spectral_profile.py`; if a shared helper
exists, import it rather than redefining). A helper
`shifted(v4, delta_db)` returns a copy with every `*_db` series shifted by
`delta_db` and `loudness_ref_db` recomputed as p95 of the shifted `full_db`
(mirroring `audio_spectral_features.py:423`) — count/ratio series untouched.

Required tests:

1. **Gain-invariance, uniform shift (exact):** for `delta_db` in
   `(+6.0, -6.0)`: `components(shifted(v4, d)) == components(v4)` within
   1e-9 per key.
2. **Gain-invariance, per-track shift preserves rank (the N3 case):** build a
   5-track synthetic library with distinct components; shift ONE track by
   ±6 dB; assert its components (hence `track_weight` against the same
   distribution) are unchanged within 1e-9 — a per-track mastering offset
   cannot move a track's weight.
3. **spearman correctness:** perfect monotone → 1.0; reversed → −1.0; a known
   ties case (hand-computed average-rank value); constant input → None;
   len<3 → None.
4. **rank_in:** mid-rank behavior on ties; ValueError on empty distribution.
5. **components guards:** missing `loudness_ref_db` → None; `n_beats <
   MIN_BEATS` → None; NaN in a consumed series → None (never a number).
6. **degenerate_components:** flat distribution flagged; healthy not.
7. **Acceptance logic seam:** factor the tool's accept decision as a pure
   function `acceptance_verdict(n_by_genre, rho, degenerate) -> tuple[bool, str]`
   in `track_weight_v0.py` and test all four outcomes.
8. **Store round-trip:** the tool's store build/write factored as
   `build_store(...) -> dict` (pure) + `write_store(dict, dir)` — write to a
   tmpdir, re-read, byte-stable keys, atomicity by construction (no partial
   file on injected `os.replace` failure is NOT required — keep it simple;
   assert tempfile pattern used by reading the source is not required either).
9. **Zero-runtime-importer guard:** copy
   `tests/test_hardness_v0.py:399-419`'s scan verbatim, retargeted at
   `track_weight_v0` (same SKIP_DIRS, same offender rule: only `tools/` and
   `tests/` may import it), plus the import-form detector test.

## Part C - Invariants That MUST Still Hold (live safety)

- The bridge runtime is BYTE-IDENTICAL: no runtime module, config, or contract
  behavior changes; `python3 -m unittest discover tests` must show only
  additions. The 200 Hz push loop (`state_manager.py:499`) is untouched by
  construction (nothing runtime imports the new module — the static test
  enforces it forever).
- The tool never writes outside `<cache_dir>/trackweight_v1/` + `--out`; never
  touches v3/v4 entries, the Rekordbox DB, ANLZ, or audio (contract's
  forbidden assumptions, verified in review).
- Weight output describes sound; it may never time or trigger a cue (contract
  law) — E1 has no consumer at all.
- Absent data reads as no signal (`None`/counted skip), never a fabricated
  weight.
- Cache versioning law: `trackweight_v1/` is its own namespace; nothing
  evicts across versions.
- Live-mixing scenario: the tool is offline and read-only against live
  surfaces; running it during a set only adds disk reads. Advisory in the
  report header: run it after mixing sessions, not during (solo-hobby scale,
  no enforcement).

## Part D - Tests

The full list is Task 3. The two design-critical ones:

- **The gain-invariance unit test** (Tests 1-2) is the machine check of the
  parent spec's [assumed] claim, at cached-feature level it is EXACT: relative
  duties cancel the offset, count/ratio series don't move.
- **The pinned correlation acceptance** (N3): `|Spearman rho| <= 0.50` between
  `loudness_ref_db` and `track_weight` on the by_genre split, with
  `n >= 100` and no degenerate component. Rationale for 0.50: the library's
  mastering-level spread is real but modest (calibration metric 5, prior
  p5-p95 spread 15.3-19.3 dB, `tools/spectral_calibration_report.py:494-495,
  655`), and loudness legitimately correlates with genre energy (harder
  genres are mastered hotter), so demanding rho ~ 0 would reject a correct
  weight; 0.50 caps "the weight is mostly a loudness meter" while allowing
  genuine loud-genre correlation. The number is pinned [assumed-reasonable];
  it may only move via spec amendment with the exec's sign-off, never by the
  implementer to make a run pass.

## Part E - Acceptance (definition of done)

1. Three new files exactly as specified; no other repo file modified EXCEPT
   the contract/docs updates below.
2. Contract-first (anti-drift): extend `docs/agents/change_contracts.yml`
   key `spectral_analysis` — add `track_weight_v0.py`,
   `tools/track_weight_report.py` to `code_globs`; add `components`,
   `track_weight`, `spearman`, `acceptance_verdict` to `key_symbols`; add a
   forbidden-assumptions entry mirroring the hardness_v0/approach_features_v0
   language (OFFLINE, zero runtime importers enforced by static test, decides
   nothing live, None on missing data, store never committed, acceptance
   thresholds move only by spec amendment).
3. Update every `docs_update` doc the contract lists:
   `docs/research/spectral_audio_analysis_redesign.md` (E1 section: what the
   weight is, the loudness-relative construction, the pinned gate) and
   `AGENTS.md` (add the two files to the "Offline analysis tooling (no runtime
   importers)" source-map row).
4. Registry: update the `AWR-286` row in
   `docs/status/active_work_registry.md` (this spec's row) to IMPLEMENTED /
   SOFTWARE-TESTED with the evidence summary.
5. Checks green: `python3 tools/check_docs_metadata.py`,
   `check_agent_contracts.py`, `check_docs_drift.py`, `check_ui_jargon.py`;
   full `python3 -m unittest discover tests` green (report the count).
6. **One real run** on this machine:
   `python3 tools/track_weight_report.py --out local/spectral_v5_2026_07_17/track_weight_report_2026_07_XX.txt`
   (gitignored local dir). Report the honest verdict: counts, both rhos, and
   ACCEPTED or the named failure. If it fails, STOP — do not tune; the exec
   owns the next move.
7. Nothing committed from `<cache_dir>`; `git status` shows only the intended
   repo files.

## When You Finish

Report back: changed files; test counts and check results; the real-run
verdict verbatim (accepted/reason, rho values, track counts).

Plain-language operator summary to include: "I built the offline
track-weight measure — a small tool that reads the spectral data the bridge
already caches and scores every track's energy against your whole library,
in a way that ignores how loud a track happens to be mastered. Nothing about
the live show changed; the bridge doesn't read this yet — that comes in later
stages, each with its own go-ahead. The tool's own report says whether the
measure passed its honesty check (that it isn't secretly just a loudness
meter): [verdict here]. Watch for nothing at the next mix — this stage is
invisible by design."

### Claim ledger

- [confirmed] all file:line citations in Part A (HEAD 5cd2fda7, 2026-07-24).
- [assumed] `REL_SUB_OFFSET_DB = -12.0` and equal component weights are
  reasonable first pins; the report's distributions + degenerate gate expose
  pathologies; changes are spec amendments.
- [assumed] onset picking is level-independent at extractor level (exact at
  cached-feature level, where all E1 math runs).
- [unknown] whether the real library passes the 0.50 gate — that is the point
  of the run; either outcome is a valid E1 result.
