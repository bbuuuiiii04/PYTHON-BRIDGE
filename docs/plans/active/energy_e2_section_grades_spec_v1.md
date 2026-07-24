---
doc_status: draft-for-review
truth_level: planned
last_verified_commit: d8ff8240
last_verified_date: 2026-07-24
validation_scope: >
  Codex implementation spec for stage E2 of the energy-fabric ladder
  (docs/plans/active/energy_fabric_ladder_spec_v1.md §B.2/§B.6): per-section
  energy grades computed on the existing ANLZ worker thread at track load,
  surfaced in status ONLY — no lighting consumer, default-OFF env flag,
  flag-off byte-identity required (F2 kill-test precedent). Consumes the E1
  track-weight store with refusal-by-construction (E1REV closing law). All
  code claims verified at HEAD d8ff8240. Awaiting exec review + operator gate
  before Codex executes. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Codex Implementation Spec - Energy E2: per-section energy grades (status-only)

Parent design: `energy_fabric_ladder_spec_v1.md` §B.2 (Layer 2) and §B.6 E2:
"layer-2 section grades at track load (pure function + status surface; no
consumer yet)." The ladder stage itself authorizes the bounded runtime touch
(track-load computation + status surface); everything else stays offline
discipline: default-OFF flag, flag-off byte-identity, fail open everywhere,
zero lighting change.

## Part A - Context & Root Cause (verified; read, do not implement)

Every claim re-read at HEAD `d8ff8240` on 2026-07-24; [confirmed] unless
labeled.

### A.1 E1 as-built (the store E2 consumes)

- `track_weight_v0.py` (AWR-286, commit `d8ff8240`): pure, stdlib-only, zero
  runtime importers (static test enforces). API: `components()`, `rank_in()`,
  `build_distribution()`, `track_weight()`, `spearman()`,
  `degenerate_components()`, `acceptance_verdict()` (defs at
  `track_weight_v0.py:58,98,110,121,143,179,193`).
- Store: `<cache_dir>/trackweight_v1/track_weight_store.json`
  (`tools/track_weight_report.py:52-53` `STORE_SUBDIR`/`STORE_NAME`, write at
  `:141-145`). Schema (build at `:120-136`): `schema_version: 1`,
  `accepted: bool`, `acceptance{...}`, `constants{...}`,
  `distribution{component: sorted floats}`,
  `tracks{<v4-cache-key>: {filepath, content_id, title, components,
  track_weight}}`.
- The ONE real run was **ACCEPTED untuned**: by_genre Spearman −0.0431 vs the
  0.50 gate, n=551 (`local/spectral_v5_2026_07_17/E1BUILD_report.md`).
- **E1REV closing law (binding here):** any consumption of the store MUST
  refuse `accepted: false` and missing stores **by construction**.
- Store keys are the v4 cache key: sha1 over (realpath, mtime_ns, size,
  beatgrid fingerprint) (`spectral_cache.py:337-352`). A track whose audio
  file changed since the E1 sweep therefore MISSES → that track's
  library-scaled grade is absent (honest fail-open), until the operator
  re-runs the E1 tool. Cross-module use of `spectral_cache` internals has
  precedent: `filepath_resolver.py:36` imports `_beatgrid_fingerprint` and
  `_features_v4_from_payload`.

### A.2 The runtime integration point (the F2 precedent, copied exactly)

- `_read_runtime_anlz_data()` (`state_manager.py:235-313`) runs on the ANLZ
  worker thread (spawned per track load; the F2 comment at `:279-282` is the
  law: "on this worker thread — never the push loop", flag-gated so off
  computes NOTHING — "kill-test byte-identity"). It already: loads/extracts
  v4 (`:250-270`), builds the F2 per-track plan gated by `f2_enabled`
  (`:283-291`, fail toward today's behavior), and computes the energy shadow.
- Caller at `:2358-2369` (inside `_anlz_extract_gate`, stale-generation
  guarded); results ride a `BridgeEvent(kind=Ev.ANLZ_DATA)` payload
  (`:2371-2388`, `"f2_plan": result.f2_plan` at `:2382`); the event consumer
  stores them on deck meta (`f2_plan` read at `:1606`). Worker kwargs
  assembly at `:2612-2620` (`"f2_enabled": self._f2_enabled` from config at
  `:803`).
- `TrackAnlzData` (`anlz_reader.py:143-151`) is the worker's result object;
  `f2_plan: Optional[Any] = None` (`:151`) is the field-addition precedent.
- Phrase segments at runtime: `build_phrase_segments_from_markers(
  anlz_buildups, anlz_drops, anlz_breakdowns, smart_drops, total_beats)`
  (`smart_phrasing.py:634-640`; maps buildups→"up", drops→"chorus",
  breakdowns→"low"). The tick-side builder passes smart drops
  (`state_manager.py:5288-5295`); the worker does not have smart drops at
  compute time — E2's grades therefore CARRY their own section boundaries in
  the output (self-describing), so no consumer can confuse them with the
  tick-side segment list. [confirmed signature; self-describing-output
  decision is this spec's]
- Audio-derived fallback segmentation exists: `section_map(v4, drops,
  buildups, breakdowns)` (`spectral_profile.py:531-536`) — merged
  16-beat-anchored character blocks.
- The within-track level mechanism to reuse: section tiers already compare a
  section's mean `full_db` against `loudness_ref_db + section_quiet_offset_db
  (−8.0) / + section_loud_offset_db (−3.0)` (`spectral_profile.py:63-64`,
  applied `:599-608`). Gain-invariant exactly (per-track offset shifts level
  and ref together).

### A.3 The status surface

- `RuntimeStatus` is a dedicated daemon thread writing
  `/tmp/rb_ss_bridge_v2_status.json` every 0.5 s via `snapshot()` +
  `atomic_write_json` (`runtime_status.py:17,181-194`); per-deck blocks are
  built from `self._sm.snapshot()` (`:191-194`). This is E2's surface — a new
  compact per-deck `section_energy` block. No new runtime command is added
  (the drift check polices STATUS_PATH/COMMANDS_PATH constants and the
  command allowlist, `tools/check_docs_drift.py:27-49` — untouched).

### A.4 The gap

Sections have labels and character but no energy grade; nothing computes
"this section, scaled by what this track is in the library." E1's weight
exists and is ACCEPTED but has zero consumers. E2 joins them: per-section
`within_track` grade (loudness-relative) and `library_scaled` grade
(× track weight, the ladder's product law), computed once per track load on
the worker thread, visible in status, consumed by nothing.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- **Flag-off byte-identity.** New env flag `RBSS_SECTION_ENERGY` (read once at
  startup beside the existing kill-switches, `state_manager.py:227-230`
  precedent), **default OFF**. Off ⇒ zero new computation, zero new payload
  keys, zero new status keys — byte-identical behavior (F2 kill-test
  discipline, `state_manager.py:281-282`). A test enforces it.
- **No lighting consumer.** Nothing in led_*/laser_*/dispatch may read the
  grades in E2. Out of scope: all LED/laser/SoundSwitch modules, config/,
  `runtime_status.py` command handling, `track_weight_v0.py` (READ-ONLY —
  its zero-runtime-importer guard and pinned constants stay untouched; the
  static test keeps passing).
- **Store refusal by construction (E1REV law).** The ONLY store access path
  is the new loader, which returns None unless the file parses,
  `schema_version == 1`, `accepted is True`, and `tracks`/`distribution` are
  present dicts. `accepted: false`, missing file, malformed JSON, wrong
  version ⇒ None ⇒ `library_scaled` is null everywhere; `within_track`
  grades still compute (they never need the store). No second code path may
  open the store file.
- **Push loop untouched.** All new computation and the single store read
  happen on the ANLZ worker thread; the status thread only formats
  already-computed values. The 200 Hz loop (`state_manager.py:499`) gains
  nothing.
- **No tuning to pass gates.** The pinned constants and gate thresholds below
  move only by spec amendment with exec sign-off — never by the implementer
  to make a run or test pass. (Restated in Part D and in the module
  docstring; three independent statements, deliberately.)
- Error handling: narrow try/except at the F2 pattern's granularity
  (`:283-291`) — compute failure logs at DEBUG and yields None (fail open);
  never a fabricated grade; no broad try/except; store loader failures are
  reasoned refusals, not exceptions.

### Task 1 - `section_energy_v0.py` (new; pure grade math + the store loader)

Docstring: honesty block (describes sound, never times/triggers a cue; no
consumer in E2; None/absent on missing data; constants pinned — changing any
is a spec amendment, never an implementation decision). This module IS
runtime-imported (unlike E1's) — so it must stay pure: stdlib only; the only
I/O is `load_track_weight_store()`, documented "worker/offline threads only,
never the push loop."

Pinned constants:

```python
SECTION_QUIET_OFFSET_DB = -8.0   # same values as spectral_profile section tiers
SECTION_LOUD_OFFSET_DB = -3.0    # (do not import them — runtime coupling stays one-way)
MIN_SECTION_BEATS = 4
STORE_SCHEMA_VERSION = 1
COVERAGE_GATE = 0.95             # G1, by_genre (Part D)
SPREAD_GATE_FRACTION = 0.90      # G2, by_genre (Part D)
SPREAD_MIN = 0.10                # G2 per-track within_track max-min
```

Functions (pure; exact signatures):

- `load_track_weight_store(path) -> Optional[dict]` — the refusal gate
  described in Absolute Rules. Returns the parsed store dict or None; never
  raises on bad content (OSError/JSONDecodeError/shape problems ⇒ None).
- `store_track_weight(store: dict, cache_key: str) -> Optional[float]` —
  `store["tracks"][cache_key]["track_weight"]` as float, else None.
- `grade_sections(v4, *, anlz_drops, anlz_buildups, anlz_breakdowns,
  track_weight: Optional[float]) -> list[dict]` — the E2 core:
  1. Segments: `build_phrase_segments_from_markers(anlz_buildups, anlz_drops,
     anlz_breakdowns, smart_drops=[], total_beats=v4.n_beats)`; if that
     yields no segments, fall back to `section_map(v4, drops=anlz_drops,
     buildups=anlz_buildups, breakdowns=anlz_breakdowns)` blocks (label
     "other", tier ignored); if both empty ⇒ `[]`.
  2. Per section (skip sections shorter than `MIN_SECTION_BEATS`):
     `rel = mean(full_db[section beats]) − loudness_ref_db`;
     `within_track = clip01((rel − SECTION_QUIET_OFFSET_DB) /
     (SECTION_LOUD_OFFSET_DB − SECTION_QUIET_OFFSET_DB))` — i.e. −8 dB→0.0,
     −3 dB→1.0, the section-tier span. Exactly gain-invariant (offset cancels
     against ref).
  3. `library_scaled = within_track * track_weight` when `track_weight` is a
     float, else `None` (the ladder's product law, §B.2).
  4. Output element: `{"start_beat", "end_beat", "label", "within_track",
     "library_scaled"}` — self-describing boundaries (A.2 rationale).
  Missing `loudness_ref_db`, empty/short series, non-finite values ⇒ `[]`
  (never a fabricated grade).
- `current_section(grades: list[dict], abs_beat: float) -> Optional[dict]` —
  bisect-free linear scan is fine (≤ dozens of sections), used by the status
  formatter.
- `gates_verdict(n_by_genre_eligible, n_graded, n_spread_ok) ->
  tuple[bool, str]` — G1/G2 verdict for the offline tool (reasons: `ok`,
  `insufficient_coverage`, `flat_grades`, `insufficient_corpus` when
  `n_by_genre_eligible < 100` — same floor as E1's `MIN_ACCEPT_N`).

### Task 2 - runtime wiring (state_manager.py + anlz_reader.py, F2 pattern verbatim)

1. `anlz_reader.py:151` area: add `section_grades: Optional[list] = None` to
   `TrackAnlzData` (beside `f2_plan`).
2. `state_manager.py` startup: read `RBSS_SECTION_ENERGY` once (`:227-230`
   style); store `self._section_energy_enabled`. Thread the flag into the
   worker kwargs (`:2612-2620`) exactly like `f2_enabled`.
3. `_read_runtime_anlz_data()`: after the F2 block (`:283-291`), gated the
   same way:

```python
if section_energy_enabled and v4 is not None:
    try:
        tw = None
        store = _track_weight_store_once()   # memoized module-level loader
        if store is not None and audio_filepath:
            key = spectral_cache._cache_key(audio_filepath, beatgrid_times_ms)
            if key is not None:
                tw = section_energy_v0.store_track_weight(store, key)
        data.section_grades = section_energy_v0.grade_sections(
            v4, anlz_drops=data.drop_beat_indices,
            anlz_buildups=data.buildup_beat_indices,
            anlz_breakdowns=data.breakdown_beat_indices,
            track_weight=tw) or None
    except Exception:
        log.debug("[E2] section-grade-failed", exc_info=True)
        data.section_grades = None
```

   `_track_weight_store_once()`: module-level memo (single attempt per
   process; result — store dict or None — cached). Path =
   `spectral_cache._cache_dir() / "trackweight_v1" / "track_weight_store.json"`.
   A store created after bridge start is picked up at the next bridge
   restart — stated plainly in the status block (`"store"` value), no
   re-polling.
4. ANLZ_DATA payload (`:2371-2388`): add `"section_grades":
   result.section_grades` ONLY when the flag is on (off ⇒ key absent — the
   byte-identity rule); consumer (`:1606` area) stores `meta.section_grades`;
   clear it wherever `f2_plan` is cleared on track change/reset (find every
   `f2_plan` reset site and mirror it — Pre-handoff check 4: cleanup on EVERY
   transition path).
5. StateManager snapshot: include a compact per-deck block (only when flag
   on): `{"sections": len(grades), "store": "loaded"|"refused_or_missing",
   "current": current_section(grades, abs_beat) or None}`; expose to
   `RuntimeStatus.snapshot()`'s per-deck dict (`runtime_status.py:191-194`)
   under key `"section_energy"`. Log one INFO line per track load with the
   outcome (`sections=N store=loaded tw=0.42`), DEBUG for detail — repo log
   style (INFO outcomes only).

### Task 3 - `tools/section_energy_report.py` (new; read-only corpus run + gates)

Mirror `tools/track_weight_report.py`'s enumeration (pyrekordbox read-only,
BY GENRE folder `666898931` minus RAP, ANLZ grid → `get_cached_v4` — pattern
at `tools/spectral_calibration_report.py:54-92,377-397`). For every by_genre
track with a v4 entry: load the E1 store ONCE via
`load_track_weight_store()` (the refusal gate — tool and runtime share the
one loader), compute `grade_sections(...)`, then evaluate:

- **G1 coverage (pinned 0.95):** fraction of by_genre tracks having BOTH a v4
  entry AND a store row that produce a non-empty grade list ≥ `COVERAGE_GATE`.
  Prior grounding: the E1 run scored n=551 by_genre tracks and marker/
  section_map fallback makes segmentation near-universal; a >5% hole means a
  real defect (short tracks, ref missing), not corpus noise.
- **G2 non-degeneracy (pinned 0.90 @ 0.10):** among graded by_genre tracks,
  the fraction whose `max(within_track) − min(within_track) >= SPREAD_MIN`
  must be ≥ `SPREAD_GATE_FRACTION`. Rationale: the −8/−3 dB mapping spans
  5 dB; a track whose sections all sit within 0.10 (= 0.5 dB) has no usable
  arc — the grade would be noise for every future consumer. Thresholds are
  [assumed-reasonable] pins; they move ONLY by spec amendment (no-tuning
  law, third statement).
- Verdict via `gates_verdict(...)`; exit 0 accepted / 1 failed (named
  reason) / 2 environment error. Library-wide numbers printed as
  informational. The tool WRITES NO store (E2 has no sidecar); `--out` copies
  the report text only; `--limit` forces a `partial_run` failure verdict
  (E1 tool precedent).

### Task 4 - `tests/test_section_energy_v0.py` (new)

1. **Gain-invariance (exact):** uniform dB shift (series + recomputed ref,
   E1 test-helper pattern) ⇒ identical `within_track` grades within 1e-9;
   per-track shift with a fixture store ⇒ `library_scaled` unchanged.
2. **Store refusal matrix:** missing path / unparseable / `schema_version` 2 /
   `accepted: false` / `tracks` not a dict ⇒ loader None; `accepted: true`
   well-formed ⇒ dict. `store_track_weight` absent-key ⇒ None.
3. **Product law:** `library_scaled == within_track * tw`; `tw=None` ⇒ null.
4. **Segmentation fallback chain:** markers ⇒ phrase segments; no markers ⇒
   section_map blocks; neither ⇒ `[]`; `MIN_SECTION_BEATS` skip.
5. **Flag-off byte-identity (kill test):** `_read_runtime_anlz_data(...,
   section_energy_enabled=False)` on a rich fixture ⇒ `section_grades is
   None` AND a monkeypatched `grade_sections`/loader assert ZERO calls; the
   ANLZ_DATA payload contains no `section_grades` key.
6. **gates_verdict:** all four outcomes.
7. **current_section:** inside/outside/boundary beats.
8. Pure seams only — no disk (store fixtures are dicts passed to the loader
   via tmp files only in the refusal test), no subprocess, no DB.

### Task 5 - contract + docs (contract-first, apply as text)

1. `docs/agents/change_contracts.yml`:
   - `rekordbox_readers` (line 480): add `anlz_reader.py` to `code_globs`
     (it parses Rekordbox ANLZ files; `state_manager.py` is already there) —
     this covers the `TrackAnlzData` field.
   - `spectral_analysis` (line 698): add `section_energy_v0.py`,
     `tools/section_energy_report.py` to `code_globs`; add `grade_sections`,
     `load_track_weight_store`, `gates_verdict` to `key_symbols`; add a
     forbidden-assumptions entry: "section_energy_v0 (AWR-288) grades are
     STATUS-ONLY at E2: no LED/laser/SS module may read them; the E1 store is
     consumed only through load_track_weight_store, which refuses
     accepted:false / missing / malformed stores by construction; absent
     data ⇒ absent grades, never fabricated; RBSS_SECTION_ENERGY default-off
     ⇒ byte-identical behavior; gate thresholds move only by spec amendment."
2. Update every `docs_update` doc of every touched contract:
   `rekordbox_readers` and `core_bridge` lists (core_bridge:
   `docs/subsystems/core_bridge.md`, `docs/architecture/
   current_architecture.md`, `docs/architecture/runtime_invariants.md` — the
   invariants doc gains the E2 fail-open + worker-thread-only rule), and
   `runtime_commands`'s list for the new status field
   (`docs/subsystems/runtime_commands.md` at minimum documents the
   `section_energy` per-deck block; touch the others in its docs_update only
   where the status surface is actually described).
   `spectral_analysis` docs_update: `docs/research/
   spectral_audio_analysis_redesign.md` (E2 section) + `AGENTS.md` (source
   map: `section_energy_v0.py` joins the phrasing/spectral row — NOT the
   offline-tooling row, it is runtime-imported; the tool joins the offline
   row).
3. Registry: update the AWR-288 row (created by the spec author) to
   IMPLEMENTED / SOFTWARE-TESTED with evidence when done.

## Part C - Invariants That MUST Still Hold (live safety)

- 200 Hz push loop (`state_manager.py:499`): zero new work — grades compute
  on the ANLZ worker (which already runs ~16 s extractions), the store read
  happens there once per process, and the status thread formats cached
  values.
- `StateManager` sole `DeckState` writer; grades ride the existing
  ANLZ_DATA `BridgeEvent`; events immutable after creation; reader threads
  never mutate `DeckState`; ANLZ-before-TRACK_LOADED ordering untouched.
- Flag OFF (the default this stage): byte-identical bridge — no computation,
  no payload key, no status key, proven by the kill test.
- Flag ON, any failure (no store, no v4, no markers, compute error): grades
  absent/null, one DEBUG line, everything else identical — LEDs, lasers,
  SoundSwitch, readers, blackout/emergency all unchanged (nothing reads
  grades in E2 by contract law).
- `track_weight_v0.py` untouched; its zero-runtime-importer static test
  still passes (the runtime imports `section_energy_v0`, never
  `track_weight_v0`).
- Stale-generation discipline: grades ride the same `load_gen`-guarded
  worker/consumer path as f2_plan; a late worker result for an unloaded
  track is dropped by the existing guard (`state_manager.py:2350-2357`).
- Live-mixing walk-through: deck A playing while deck B loads (per-deck meta,
  no bleed); track change mid-compute (load_gen guard drops stale grades);
  seek/loop (grades are static per track — `current` lookup only);
  store file corrupt or half-written (loader refuses ⇒ null library_scaled;
  the E1 tool writes atomically so a torn file is only possible via external
  interference — refused either way); bridge restart after an operator E1
  re-run (fresh memo picks up the new store).

## Part D - Tests & acceptance gates

Unit tests: Task 4. Corpus gates (Task 3, BY GENRE law per the
`spectral_analysis` contract): **G1 coverage ≥ 0.95**, **G2 spread ≥ 0.90 of
tracks at ≥ 0.10**, minimum corpus n ≥ 100. Rationales in Task 3. The
gain-invariance test is the stage's cheap honesty check (same mechanism E1
proved: loudness-relative construction cancels per-track offsets exactly).
**No-tuning law (final statement):** a failed gate is a valid E2 result
reported to the exec; no constant in this spec may be changed to convert a
failure into a pass.

## Part E - Acceptance (definition of done)

1. Files: `section_energy_v0.py`, `tools/section_energy_report.py`,
   `tests/test_section_energy_v0.py`, the Task-2 wiring, the Task-5
   contract/docs edits — nothing else.
2. All four hard checks green; full `python3 -m unittest discover tests`
   green apart from the two PRE-EXISTING unrelated reds documented in
   `E1BUILD_report.md` (hardness venv scan + soundswitch pack self-heal) —
   do not fix or mask them; report the counts.
3. Kill test green: flag off ⇒ byte-identical (Task 4 test 5).
4. **One real corpus run**: `python3 tools/section_energy_report.py --out
   local/spectral_v5_2026_07_17/section_energy_report_2026_07_XX.txt`;
   report the honest verdict (G1/G2 numbers, named failure if any). A FAIL
   stops the lane for exec review — no tuning.
5. One real flag-on bridge smoke is NOT required in E2 (operator runs the
   bridge via the menubar only; the status field is verified by unit tests +
   the next natural bridge session with `RBSS_SECTION_ENERGY=1` when the
   operator chooses).
6. Nothing from `<cache_dir>` or `local/` committed.

## When You Finish

Report: changed files, test/check results, the corpus-run verdict verbatim.

Plain-language operator summary: "The bridge can now grade each part of a
track — how loud that section is for THAT track, and how heavy it is scaled
by the track's weight in your whole library (using the track-weight store we
built last stage; if that store is missing or failed its honesty check, the
library-scaled half simply stays blank). It's OFF by default and changes
nothing you see or hear; when you want it, one switch turns it on and the
grades appear in the bridge's status file only. Nothing about the lights
reads these numbers yet — that's a later stage with its own go-ahead."

### Claim ledger

- [confirmed] every file:line in Part A at HEAD d8ff8240.
- [confirmed] E1 store schema/path/acceptance from as-built code + E1BUILD
  report (run ACCEPTED, ρ=−0.0431, n=551).
- [assumed] G1 0.95 / G2 0.90@0.10 pins are reasonable (rationales in Task 3);
  movable only by amendment.
- [assumed] worker-side segments (smart_drops=[]) differ harmlessly from
  tick-side segments for a status-only stage; grades self-describe their
  boundaries so no consumer can conflate them. E4 must reconcile before any
  lighting consumer reads grades.
- [unknown] whether the real corpus passes G1/G2 — either outcome is a valid
  E2 result (no-tuning law).
