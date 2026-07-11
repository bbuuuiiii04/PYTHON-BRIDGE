---
doc_status: current
truth_level: spec
last_verified_commit: 007b5d3
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-205 — the structured gold-label intake for the
  AWR-200 Stage-1 ear benchmark: an empty provenance-keyed labeling template
  (hybrid unit, operator-ruled 2026-07-11) plus a strict fail-closed loader.
  Offline tooling only; zero runtime behavior change.
---

# Implementation Spec — AWR-205 Spectral gold-label intake (template emitter + strict loader)

## Part A — Context & Root Cause (verified; read, do not implement)

- [confirmed] `tools/spectral_ear_benchmark.py` (902 lines) is the AWR-200 Stage-1
  harness. Every accuracy axis (tier/family/darkness/growl/laser) reports
  UNAVAILABLE because the AWR-182 labels are the operator's free text — no
  structured per-drop gold exists (`AXES` comment ~:109–114; `axis_availability`
  :424; `is_partial` :478).
- [confirmed] Lineage identity: `_lineage_key` :195 (`cid:{content_id}` else
  `trk:{normalized title}`); last `--resolve-db` run resolved 21/21 usable
  lineages / 158 markers (registry AWR-200 row).
- [confirmed] Leak discipline: `RESOLUTION_ONLY_FIELDS` :70, `assert_no_leak`
  :490, `call_planner` :498 — the single guarded boundary into the production
  planner. No label/gold field may ever reach model inputs.
- [confirmed] `run()` :824 computes `label_sha = sha256(labels)[:16]` and reports
  it; current label layer sha `a584dcb1e0293b24`.
- [confirmed] **Operator ruling 2026-07-11 (executive session, binding):**
  - Labeling unit = **HYBRID**: every enumerated marker gets a quick
    `is_genuine_drop` yes/no; the full field set is filled **only** on genuine
    drops. The yes/no layer is the ground truth for the drop-vs-buildup
    (false-blackout, SOL2 finding 1) work later — record it faithfully.
  - Field set per genuine drop = SOL's proposal **approved as-is**: tier
    (1/2/3/unknown), family (WALL/COMET/HOUSE/NEUTRAL/free text/unknown),
    family_matches_track (bool/unknown), darkness (shape + desired start/end
    beats + bar length), growl (start/end beats or none), laser suitability
    (yes/no/unknown), confidence + free-text notes. `unknown` is always valid.
- [unknown → lane verifies] Exactly which per-marker decision fields
  `_decision_at` :595 / `build_track_plan` expose for gold comparison (family?
  tier? darkness length? genuine-drop bit?). Verify in code before wiring any
  scorer; anything not exposed stays UNAVAILABLE (see T3).

## Part B — Tasks (implement in order; commit by explicit paths after each)

### Absolute Rules
- Offline tooling only. Out of scope: `lighting_moments_v2.py` and every runtime
  module, `spectral_cache.py`, caches, configs, the bridge process (never start
  or contact it), the AWR-182 label file (read-only, never mutated).
- The filled/empty gold files live beside the gitignored label layer and are
  gitignored — never committed.
- Error handling: fail closed and loud. No broad try/except, no
  success-shaped fallbacks, no silently skipped rows.
- `is_partial` :478 must NOT be weakened. AWR-200 flips to complete only when
  real gold + real scorers make axes genuinely AVAILABLE.
- Dirty-worktree safety: touch only the files this spec names; never revert or
  clean unrelated changes; no destructive git.

### Task 1 — `tools/spectral_ear_benchmark.py`: template emitter
Add an `--emit-gold-template OUT.json` mode (requires `--resolve-db`). Enumerate
exactly the marker set the existing marker-sensitivity pass scores (reuse the
same resolution + enumeration code path — do not invent a parallel one). Emit a
deterministic JSON template:
- header: HEAD short-sha, label sha, generated-at note, and the ruling summary
  ("hybrid unit; nulls = unlabeled");
- one row per marker keyed by provenance: lineage key, content_id, track title,
  marker beat (+ mm:ss if cheaply derivable from the same data already loaded);
- fields: `is_genuine_drop: null`, and a nested `drop` object with every
  approved field set to null (growl uses `{"start_beat": null, "end_beat":
  null}` with the string `"none"` accepted on load).
Rows must carry human context (title, time) so a chat transcription session can
fill them. Refuse to overwrite an existing OUT.json that contains any non-null
`is_genuine_drop` (fail closed; tell the operator to move it).

### Task 2 — `tools/spectral_ear_benchmark.py`: strict gold loader
Add `--gold PATH`:
- schema-validate every row; unknown/typo'd fields are hard errors (mirror the
  :70 allowlist discipline);
- every gold row must match a currently-enumerable marker by provenance key;
  unmatched rows are a hard error listing each one;
- `is_genuine_drop: null` = unlabeled → excluded from scoring but counted in a
  coverage line (labeled/total);
- genuine-drop rows: enum fields must be a valid value or `"unknown"`; beat
  fields sane (start < end, non-negative); violations are hard errors naming
  the row;
- report `gold sha256[:16]` next to the label sha;
- gold fields must be provably unable to reach the planner: they flow only into
  scoring, never into `call_planner` inputs; extend the leak tests to prove it.

### Task 3 — availability + scoring wiring (fail toward UNAVAILABLE)
An accuracy axis flips AVAILABLE only when BOTH hold: (a) ≥1 genuine-drop gold
example exists for it, and (b) a real scorer compares that gold to an actual
per-marker model output verified to exist in `_decision_at`/the plan object.
Implement scoring in this round ONLY for axes the planner already exposes;
every other axis (and any axis whose gold exists but scorer doesn't) reports
UNAVAILABLE with an exact blocker string (e.g. "gold present; no model scorer —
Stage-2"). If the planner exposes a genuine-drop/blackout decision per marker,
also wire a `drop_classification` axis against the yes/no layer the same way —
if not exposed, record the gold and report UNAVAILABLE with the blocker.

### Task 4 — tests: extend `tests/test_spectral_ear_benchmark.py` (currently 32 green)
Pure-function seams, no DB/filesystem beyond tmp files:
- template built from synthetic lineages/markers: determinism, one row per
  marker, all-null fields, header content;
- overwrite-protection trips on a filled template;
- loader: valid roundtrip; unknown field → error; unmatched provenance → error
  naming the row; null is_genuine_drop → excluded + counted; invalid enum/beat
  → error;
- availability: gold+scorer → AVAILABLE with gold_examples count; gold w/o
  scorer → UNAVAILABLE with blocker; no gold → UNAVAILABLE (existing behavior
  unchanged);
- leak: a gold field smuggled into model inputs makes `assert_no_leak` raise;
- `is_partial` regression: gold for ONE axis does not flip status to complete
  unless the predicate's own rule says so (do not touch the predicate).

### Task 5 — docs + contract
- `docs/agents/change_contracts.yml`: extend the `spectral_analysis` contract
  FIRST if this surface isn't covered; then update every `docs_update` doc it
  lists.
- Add the AWR-205 registry row (`docs/status/active_work_registry.md`; re-check
  the current max ID immediately before writing — parallel lanes race).
- Run the three hard checks + the scoped suite (Part E).

## Part C — Invariants That MUST Still Hold
- Zero runtime behavior change; no runtime module is edited or newly imported.
- Bridge stays OFF; never started or contacted (`pgrep -f 'm rb_ss_bridge_v2'`
  core runtime count stays 0).
- AWR-182 label file byte-identical before/after (its sha is the proof).
- No secrets, no live config, no gitignored label/gold layer committed.
- The `call_planner`/`assert_no_leak` boundary remains the ONLY path into the
  planner, and gold never crosses it.

## Part D — Tests
Task 4 above. All new logic reachable through pure functions; the CLI is a thin
shell over them.

## Part E — Acceptance (definition of done)
- [ ] Template emitter produces a deterministic, all-null, provenance-keyed
      hybrid template over the full resolved marker set (spot-run against the
      real DB read-only; report lineage/marker counts — expect 21/158 unless
      the DB moved).
- [ ] Strict loader + leak proof + availability wiring as specced, failing
      toward UNAVAILABLE everywhere.
- [ ] `tests/test_spectral_ear_benchmark.py` green with the new cases; report
      exact count (was 32). Hardness (28) + approach (27) suites still green.
- [ ] 3 hard doc checks green; contract docs_update honored; AWR-205 row added.
- [ ] Commits by explicit paths only; label file sha unchanged; no gitignored
      file staged.

## When You Finish
Report: changed files, per-suite test counts by name, hard-check results, the
real-DB spot-run counts, honest ceilings (what stays UNAVAILABLE and why), and
any divergence from this spec (BLOCK instead of inventing if reality differs).
Plain-language operator summary: what the template is, what filling it unlocks,
what does NOT change live (everything).
