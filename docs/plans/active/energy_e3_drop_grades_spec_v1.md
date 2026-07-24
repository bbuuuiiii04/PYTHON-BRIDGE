---
doc_status: draft-for-review
truth_level: planned
last_verified_commit: f3351b47
last_verified_date: 2026-07-24
validation_scope: >
  Codex implementation spec for stage E3 of the energy-fabric ladder
  (docs/plans/active/energy_fabric_ladder_spec_v1.md §B.3/§B.6): per-drop
  energy grades computed on the ANLZ worker thread (the proven E2 wiring
  shape), attached to DropDecision at the tick-side plan build, surfaced in
  status ONLY — no lighting consumer, default-OFF env flag, flag-off
  byte-identity kill test. Consumes the E1 store solely through the as-built
  E2 refusal-by-construction loader/memo. All code claims verified at HEAD
  f3351b47 (E2's landing commit). Awaiting exec review + operator gate before
  Codex executes. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Codex Implementation Spec - Energy E3: per-drop energy grades (status-only)

Parent design: `energy_fabric_ladder_spec_v1.md` §B.3 (Layer 3) and §B.6 E3:
"layer-3 `drop_grade` on `DropDecision` (pure function + status surface; no
consumer yet)." E2's landed discipline is the template: same worker-thread
placement, same store memo, same flag/kill-test/fence laws.

## Part A - Context & Root Cause (verified; read, do not implement)

Every claim re-read at HEAD `f3351b47` on 2026-07-24; [confirmed] unless
labeled.

### A.1 E1 + E2 as-built (the machinery E3 rides)

- E1 store + loader semantics (byte-stable since `d8ff8240`, re-confirmed at
  f3351b47): store at `<cache_dir>/trackweight_v1/track_weight_store.json`
  (`tools/track_weight_report.py:52-53`); the ONLY runtime access path is
  `section_energy_v0.load_track_weight_store()` (`section_energy_v0.py:52`)
  via the memoized `_track_weight_store_once()`
  (`state_manager.py:241-251`, `_SECTION_STORE_MEMO` read directly on the
  status path — no I/O there); refusal-by-construction (missing / torn /
  wrong `schema_version` / `accepted is not True` / non-dict
  tracks|distribution ⇒ None); `store_track_weight()`
  (`section_energy_v0.py:74`) ⇒ finite float or None. E2CREV verified the
  matrix as built.
- E2 wiring shape (the pattern E3 copies verbatim):
  `SECTION_ENERGY_ENV = "RBSS_SECTION_ENERGY"` (`state_manager.py:231`),
  flag read once (`:845`), worker compute block flag-gated with
  `v4 is not None` (`:320-336`), payload key added only when on (`:2455`),
  consumer stores meta beside f2_plan (`:1675-1677`), per-deck status block
  only when on (`:1257-1267`), models.py field + `clear()` mirror
  (`models.py:69`, `:91`). Import fence test: only `state_manager.py`,
  `tools/`, `tests/` may import the module (~3 s robust idiom — skips
  `local/`, catches `UnicodeDecodeError`; E2CREV ran a live fence probe).
- E2 grade element shape (consistency target): `{"start_beat", "end_beat",
  "label", "within_track", "library_scaled"}`
  (`section_energy_v0.py:145-146`); product law `library_scaled =
  within_track × track_weight`.
- E2 corpus verdict: ACCEPTED untuned, G1 = 1.000, G2 = 0.991, 551/552
  eligible/total, suite 5139 zero reds (E2CREV re-run).

### A.2 The drop-side machinery E3 extends

- `DropDecision` (`drop_presentation.py:192-222`): `__slots__ = ("beat",
  "tagged", "learned", "is_finale", "personality_presentation", "runway")`
  (`:199`); `__eq__` iterates `__slots__` (`:215`) so a new slot joins
  equality automatically. NO energy field exists.
- The plan builds tick-side once ANLZ + tags have landed
  (`state_manager.py:2773-2811`): pure reads off published DeckState, no
  I/O; `drop_beats = d.meta.smart_drops` (`:2791` — the SELECTED smart/true
  drops, not raw ANLZ markers), `phrase_roles =
  self._build_phrase_segments(d)` (`:2792`), then `plan_track(drop_beats,
  phrase_roles, tag_beats, learned_beats, config, laser_tiers=…)`
  (`:2798-2802`).
- Live consumers of decisions (must stay byte-identical):
  `state_manager.py:2930/2935/3109` read `.runway`/`.tagged` — [confirmed by
  grep at f3351b47]. The spec touches none of them; they ignore the new
  slot by construction.
- `drop_window_vector(v4, drop_beat, *, width=16, wobble=None)`
  (`spectral_profile.py:619-625`): per-window descriptor means over
  `[drop_beat, drop_beat+16)`; `coverage` counts available beats (`:637-639`).
  E3 reuses its WINDOW convention (start at the drop beat, width 16) but
  computes its own three pinned components — the vector's raw dB means are
  absolute, not loudness-relative, so they cannot enter a grade directly
  (the E1/E2 gain-invariance law).
- `loudness_ref_db` + the −8/−3 dB span and the −12 dB sub offset are the
  proven relative mechanisms (`audio_spectral_features.py:423`,
  `spectral_profile.py:63-64`, E1 `REL_SUB_OFFSET_DB`); per-track
  `onset_mh_p90` exists as a v4 scalar (`audio_spectral_features.py:125-127`,
  value at `:426`).
- **True-drop law (operator law, standing):** only the first marker in a
  drop section with an up-buildup runway is a true drop; raw ANLZ markers
  are never equal candidates. E3's worker grades raw-marker WINDOWS (a
  mechanical necessity — the worker has `data.drop_beat_indices` only), but
  grades are ATTACHED only to plan decisions (which are built from
  `meta.smart_drops`) and ONLY plan-attached grades are surfaced. The raw
  set is never shown anywhere.

### A.3 Banked review obligations folded here (E2CREV)

- **O1:** E3's status block contains NO playhead lookup (static per-drop
  list), so the elapsed×bpm approximation is not used. Restated as binding
  law for E4: any CONSUMER of section or drop grades MUST use the real
  tick-side `abs_beat`, never the status block's approximation.
- **O3 + N4:** the G2 spread gate is weak (E2 measured median spread 1.000 —
  clip-rail saturation). E3 does not consume section grades, so the
  boundary-sanity obligation stays with E4 (restated in Part D and
  non-scope). E3's own honesty gate G3 (drop-vs-breakdown separation,
  Part D) is deliberately built in the same spirit: it checks the grade
  points the right way, not merely that it varies.

### A.4 The gap

Drops have tiers on the laser side and tagged/learned/finale/runway
classification on the LED side, but no energy grade unified with layers 1-2.
`DropDecision` carries no energy field; nothing computes "how hard this drop
is, within this track and scaled by what this track is in the library."

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- **Flag-off byte-identity.** New env flag `RBSS_DROP_ENERGY` (beside
  `SECTION_ENERGY_ENV`, `state_manager.py:231`), default OFF, read once at
  startup (`:845` pattern). Off ⇒ zero new computation, no payload key, no
  status key, `plan_track` receives no grades and every `DropDecision.
  energy_grade` is None ⇒ byte-identical behavior. Kill test enforces all
  four surfaces.
- **No lighting consumer.** `resolve_presentation()`, the drop ladder, laser
  qualifiers, LED dispatch: none may read `energy_grade` in E3 (contract
  forbidden-assumptions law + the import fence). The field is inert data.
- **E1 store law.** Track weight comes ONLY from the as-built
  `_track_weight_store_once()` memo — E3 adds no second loader, no second
  code path to the store file. Refusals ⇒ `library_scaled` None everywhere;
  `within_track` never needs the store.
- **True-drop law.** Raw-marker grades exist only inside
  `meta.drop_grades` as attach material; every surfaced grade (status,
  logs) comes from plan-attached decisions. No surface may enumerate the
  raw set.
- **No tuning.** Pinned constants and gates move only by spec amendment with
  exec sign-off — never to make a run or test pass. (Restated in the module
  docstring and Part D.)
- Out of scope: `track_weight_v0.py`, `section_energy_v0.py` (both
  READ-ONLY), `resolve_presentation` and everything downstream of it,
  `runtime_status.py`, all LED/laser/SS modules, config/. Error handling:
  narrow F2-granularity try/except, DEBUG log, fail open to None — never a
  fabricated grade.

### Task 1 - `drop_energy_v0.py` (new; pure grade math)

Runtime-imported (state_manager only), stdlib-only, pure; docstring carries
the honesty block (describes sound, never times/triggers a cue, no consumer
in E3, None on missing data, constants pinned — no-tuning statement #1).

Pinned constants:

```python
DROP_WINDOW_BEATS = 16          # drop_window_vector's own width convention
MIN_WINDOW_BEATS = 8            # thinner coverage ⇒ that drop ungraded (None entry omitted)
BODY_QUIET_OFFSET_DB = -8.0     # the proven section-tier span (E2 constants)
BODY_LOUD_OFFSET_DB = -3.0
SUB_OFFSET_DB = -12.0           # E1's REL_SUB_OFFSET_DB
IQR_GATE = 0.05                 # G2 (Part D)
SEPARATION_GATE = 0.15          # G3 (Part D)
COVERAGE_GATE = 0.95            # G1 (Part D)
MIN_ACCEPT_N = 100              # E1/E2 floor
```

Functions (pure, exact signatures):

- `grade_drops(v4, *, drop_beats, track_weight) -> list[dict]` — for each
  int beat in `drop_beats` with window coverage ≥ `MIN_WINDOW_BEATS` over
  `[beat, beat+DROP_WINDOW_BEATS)` clamped to `n_beats`:
  - `ref = v4.scalars["loudness_ref_db"]` (missing/non-finite ⇒ `[]`).
  - `body = clip01((mean(full_db[window]) − ref − BODY_QUIET_OFFSET_DB) /
    (BODY_LOUD_OFFSET_DB − BODY_QUIET_OFFSET_DB))`
  - `sub_duty = fraction of window beats with sub_db >= ref + SUB_OFFSET_DB`
  - `onset_ratio = clip01(mean(onset_density_midhigh[window]) /
    scalars["onset_mh_p90"])` (p90 ≤ 0 or non-finite ⇒ term omitted and the
    mean taken over the remaining two — never a division blowup).
  - `within_track = mean(present terms)`;
    `library_scaled = within_track * track_weight` when `track_weight` is a
    float else `None` (the ladder's product law, E2-consistent).
  - Element: `{"drop_beat": int, "within_track": float,
    "library_scaled": float|None, "coverage": int}`.
  All three terms are gain-invariant (loudness-relative dB, duty, count
  ratio vs the track's own p90) — the proven E1/E2 mechanism; the exact
  uniform-shift test applies unchanged.
- `grades_by_beat(grades: list[dict]) -> dict[int, dict]` — attach lookup.
- `gates_verdict(n_by_genre_eligible, n_graded, iqr, separation) ->
  tuple[bool, str]` — reasons `ok | insufficient_corpus |
  insufficient_coverage | degenerate_distribution | inverted_or_flat_
  separation`. **Pinned definition (the E2 F1 lesson, applied from birth):**
  `n_by_genre_eligible` = by_genre tracks with a v4 entry AND a row in the
  accepted E1 store AND ≥ 1 ANLZ drop marker; G1 =
  `n_graded / n_by_genre_eligible ≥ COVERAGE_GATE` where `n_graded` counts
  eligible tracks yielding ≥ 1 graded drop. The denominator is NOT all
  by_genre tracks; the report must print
  `n_by_genre_eligible / n_by_genre_total` as an INFORMATIONAL
  absolute-coverage line.

Deliberate deviations from the parent §B.3 wording, stated for the record:
(a) `energy_model.py` drop-lift measures are NOT consumed — they ride the
ANLZ waveform-heights path coupled to `spectral_enabled` and the
smart-drop shadow, would couple E3 to a second flag, and their signal is
substantially the `body` term; the shadow's lift stays independently
visible in `SmartDropEnergyShadow`. (b) Runway is NOT recomputed — the
attached decision already carries the canonical `.runway`
(reuse-authority rule); the grade dict deliberately excludes it.

### Task 2 - runtime wiring (state_manager.py + anlz_reader.py + models.py + drop_presentation.py)

1. `anlz_reader.py`: `drop_grades: Optional[list] = None` on `TrackAnlzData`
   beside `section_grades`.
2. `models.py`: `drop_grades: Optional[list] = None` on `TrackMetadata`
   beside `section_grades` (`:69`) + `self.drop_grades = None` in `clear()`
   beside its mirror (`:91`) — `clear()` is the complete reset obligation
   (E2REV enumeration, unchanged at f3351b47).
3. `state_manager.py`: `DROP_ENERGY_ENV = "RBSS_DROP_ENERGY"` beside `:231`;
   read once beside `:845`; thread `drop_energy_enabled` through the worker
   kwargs (the five kwarg-pinning assertions in
   `tests/test_smart_transitions.py` gain the same one-line default-off pin
   E2 added — disclosed existing-test edit, F2/E2 precedent). Worker block
   after E2's (`:320-336` pattern), gated `if drop_energy_enabled and v4 is
   not None and data.drop_beat_indices:` — reuse `tw` from
   `_track_weight_store_once()` + `store_track_weight` exactly as E2's block
   does, then `data.drop_grades = drop_energy_v0.grade_drops(v4,
   drop_beats=data.drop_beat_indices, track_weight=tw) or None`. Payload key
   `"drop_grades"` beside `:2455`, flag-gated; consumer beside `:1675-1677`.
4. `drop_presentation.py`: extend `DropDecision` — append `"energy_grade"`
   to `__slots__` (`:199`), keyword-only ctor param `energy_grade=None`,
   include in `__repr__`; `__eq__` needs no edit (iterates slots, `:215`).
   `plan_track(...)` gains keyword-only `drop_grades: Optional[dict] = None`
   (the `grades_by_beat` mapping); each decision gets
   `energy_grade=drop_grades.get(int(beat))` when the mapping is present,
   else None. **Unmatched beats ⇒ None, logged once at DEBUG** — smart-drop
   selection may adjust beats away from raw markers; [unknown] how often —
   the implementer measures it in the corpus run (report prints the
   attach-match rate) rather than guessing. No other drop_presentation
   function changes.
5. Plan build (`:2798-2802`): pass `drop_grades=
   drop_energy_v0.grades_by_beat(d.meta.drop_grades)` when the flag is on
   AND `d.meta.drop_grades` is non-empty; omit the kwarg entirely when off
   (byte-identity).
6. Status: per-deck block ONLY when the flag is on, beside E2's
   (`:1257-1267`): `"drop_energy": {"drops": <len of plan-attached non-None
   grades>, "store": "loaded"|"refused_or_missing", "grades": [{"beat",
   "within_track", "library_scaled"}...]}` — built from the CURRENT plan's
   decisions (true drops only; ≤ a handful), never from `meta.drop_grades`.
   NO playhead lookup (O1 stays out of E3 by construction). One INFO line
   per plan build with the outcome (`drops=N graded=M store=loaded`).

### Task 3 - `tools/drop_energy_report.py` (new; read-only corpus run + gates)

E1/E2 enumeration pattern (pyrekordbox read-only, BY GENRE folder minus RAP,
ANLZ grid → `get_cached_v4`). Per eligible track (definition in Task 1):
`grade_drops(...)` on the raw ANLZ markers; ALSO `section_energy_v0.
grade_sections(...)` for G3's comparison set. Gates (BY GENRE law):

- **G1 coverage ≥ 0.95** (eligible denominator per Task 1; informational
  absolute-coverage line REQUIRED).
- **G2 non-degeneracy:** IQR of `within_track` across all graded by_genre
  drops ≥ 0.05. Rationale: the body term alone spans 5 dB, so 0.05 ≈
  0.25 dB resolution — below that the grade cannot separate anything.
- **G3 separation (the honesty gate):** median `within_track` over graded
  drops MINUS median `within_track` of "low"-labeled section grades
  (E2's output, same tracks) ≥ 0.15. Rationale: drops sit at the track
  ceiling and breakdowns at/below the quiet offset by construction; E2's
  corpus measured sections saturating both clip rails (median spread
  1.000), so a healthy drop grade should clear 0.15 with a wide margin — a
  failure means the window math points the wrong way, which no spread gate
  would catch (the O3/N4 lesson applied to E3's own layer).
- `n_by_genre_eligible ≥ 100` floor; `--limit` forces `partial_run` FAIL;
  exit 0/1/2; writes NO store; report prints the attach-relevant
  smart-vs-raw beat match rate (Task 2.4) as informational. **No-tuning
  statement #3: a failed gate stops the lane for exec review.**

### Task 4 - `tests/test_drop_energy_v0.py` (new)

1. Gain-invariance exact: uniform dB shift (series + recomputed ref) ⇒
   identical `within_track` within 1e-9; per-track shift with fixture
   weight ⇒ `library_scaled` unchanged.
2. Product law + None degradation (`tw=None` ⇒ null library_scaled).
3. Window edges: coverage floor (`MIN_WINDOW_BEATS`), end-of-track clamp,
   `onset_mh_p90 ≤ 0` term-omission path, missing ref ⇒ `[]`.
4. `grades_by_beat` + plan attach: matched beat ⇒ grade dict on
   `DropDecision.energy_grade`; unmatched ⇒ None; flag-off plan (no kwarg)
   ⇒ None; `DropDecision` equality/repr with and without grades.
5. **Kill test (all four surfaces):** flag off ⇒ zero `grade_drops` calls
   (monkeypatch), no `"drop_grades"` payload key, no `"drop_energy"` status
   key, plan decisions all `energy_grade is None`; flag-on mirrors prove the
   gate discriminates.
6. `gates_verdict` all five outcomes.
7. **Import fence:** only `state_manager.py`, `tools/`, `tests/` import
   `drop_energy_v0` — copy E2's as-built robust scan (local/ skip +
   `UnicodeDecodeError` catch, ~3 s).
8. Pure seams only; store fixtures via the E2 loader in tmp files only
   where refusal paths are exercised.

### Task 5 - contract + docs (contract-first, apply as text)

1. `docs/agents/change_contracts.yml`:
   - `spectral_analysis`: add `drop_energy_v0.py`,
     `tools/drop_energy_report.py` to code_globs; add `grade_drops`,
     `grades_by_beat` (drop-energy), `gates_verdict` reference to
     key_symbols; add a forbidden-assumptions entry: "drop_energy_v0
     (AWR-290) grades are STATUS-ONLY at E3: no presentation/laser/LED path
     may read DropDecision.energy_grade; the E1 store is reached only via
     the E2 loader/memo; raw-marker grades are attach material only — every
     surfaced grade comes from plan-attached true-drop decisions;
     RBSS_DROP_ENERGY default-off ⇒ byte-identical; gates move only by spec
     amendment."
   - `drop_presentation` (covers `drop_presentation.py`, `state_manager.py`,
     `models.py` already — verified): no glob change needed; its
     forbidden-assumptions law "enabled false must render every drop …
     byte-identical" now also binds the E3 flag — note this in the entry
     text if the exec wants it explicit.
   - `rekordbox_readers` already carries `anlz_reader.py` (E2's cure).
2. docs_update per touched contract: `drop_presentation`'s list
   (`docs/architecture/drop_presentation_authority.md`,
   `docs/subsystems/led_govee.md`, `docs/subsystems/laser.md`,
   `docs/plans/active/streamdeck_palette_control_design_spec.md`,
   `docs/status/active_work_registry.md`) — the authority doc gains the
   inert `energy_grade` field note; `core_bridge`'s list for the wiring
   (`runtime_invariants.md` gains E3's worker-only/fail-open/flag rule
   beside E2's); `spectral_analysis`'s list
   (`docs/research/spectral_audio_analysis_redesign.md` E3 section +
   `AGENTS.md` source-map rows — module joins the phrasing/spectral row,
   tool joins the offline row).
3. Registry: AWR-290 row → IMPLEMENTED / SOFTWARE-TESTED with evidence when
   done.

## Part C - Invariants That MUST Still Hold (live safety)

- 200 Hz push loop: zero new work (worker-thread compute; plan build is the
  existing tick-side pure-read path gaining one dict lookup per decision;
  status thread formats cached values).
- StateManager sole DeckState writer; grades ride the existing
  load_gen-guarded ANLZ_DATA event; events immutable; ANLZ-before-
  TRACK_LOADED untouched.
- Flag OFF (default): byte-identical — proven by the four-surface kill test.
- Flag ON, any failure (no store/v4/markers, thin coverage, compute error):
  grades absent/None, DEBUG line, everything else identical; the drop
  presentation ladder, laser tiers, masks, and every existing qualifier
  behave byte-identically because nothing reads the new field.
- `drop_presentation`'s standing law (enabled-false renders byte-identical)
  is not weakened: `plan_track`'s new kwarg defaults to None and the
  legacy call shape is preserved when the flag is off.
- True-drop law: no surface enumerates raw-marker grades.
- Live-mixing walk-through: deck switch mid-plan (plan rebuild attaches from
  that deck's meta; per-deck isolation via existing plan bookkeeping);
  track change mid-worker (load_gen guard drops stale grades); store absent
  (nulls, visible in status vocabulary); seek/loop (grades static per
  track); E2 flag and E3 flag in all four combinations (independent gates —
  a test asserts no cross-flag coupling).

## Part D - Tests & acceptance gates

Unit tests: Task 4. Corpus gates (Task 3, BY GENRE law): G1 ≥ 0.95 on the
pinned eligible denominator, G2 IQR ≥ 0.05, G3 separation ≥ 0.15, n ≥ 100.
The gain-invariance test is the stage's honesty check; G3 is its
direction-of-truth check (the O3/N4 lesson applied at birth). **E4's banked
obligations, restated as law for that stage:** (1) consumers use the real
tick-side `abs_beat`, never the status approximation (O1); (2) the first
stage that CONSUMES section grades owes a boundary-sanity validation, not
just spread (O3+N4). **No-tuning (final statement): a failed gate is a valid
E3 result owned by the exec; no constant may move to convert it.**

## Part E - Acceptance (definition of done)

1. Files: `drop_energy_v0.py`, `tools/drop_energy_report.py`,
   `tests/test_drop_energy_v0.py`, wiring (`state_manager.py`,
   `anlz_reader.py`, `models.py`, `drop_presentation.py`), the Task-5
   contract/docs edits, the disclosed one-line-per-assert
   `tests/test_smart_transitions.py` kwarg pins — nothing else.
2. Four hard checks green; full suite green up to the pre-existing reds
   documented in E1BUILD (the suite may be greener — at E2's close it was
   5139/0 reds).
3. Kill test green on all four surfaces; import fence green; fence probe
   optional but recommended (E2CREV precedent).
4. One real corpus run: `python3 tools/drop_energy_report.py --out
   local/spectral_v5_2026_07_17/drop_energy_report_2026_07_XX.txt`; report
   the verdict verbatim (G1/G2/G3, eligible/total, attach-match rate). FAIL
   ⇒ stop for exec review.
5. No bridge start required; nothing from `<cache_dir>`/`local/` committed.

## When You Finish

Report: changed files, test/check counts, corpus verdict verbatim,
attach-match rate.

Plain-language operator summary: "Each true drop now gets an energy grade —
how hard it hits within its own track, and that number scaled by the track's
weight in your whole library (blank if the track-weight store is missing or
failed its honesty check). It's OFF by default; turning it on adds the
grades to the bridge's status file and changes nothing else — no light reads
these numbers yet. The tool's report also checks the math points the right
way: drops must grade far above breakdowns across your whole BY GENRE
library, or the stage fails and we stop."

### Claim ledger

- [confirmed] every file:line in Part A at HEAD f3351b47, incl. E2 as-built
  wiring lines and the E2CREV-verified refusal matrix.
- [assumed] the three-term window grade (body/sub-duty/onset-ratio) is a
  reasonable first pin; G2/G3 exist to catch it lying; movable only by
  amendment.
- [assumed] smart-drop beats mostly coincide with raw marker beats (exact
  int match); the corpus run MEASURES the attach-match rate instead of
  trusting this — a low rate is exec-review material, not a silent hole.
- [unknown] G1/G2/G3 outcomes on the real corpus — either result is a valid
  E3 result (no-tuning law).
- [deviation, stated] energy_model lift measures and runway recomputation
  deliberately not consumed (Task 1 rationale); the parent ladder's §B.3
  named them as inputs — this spec narrows to the proven v4 mechanisms.
