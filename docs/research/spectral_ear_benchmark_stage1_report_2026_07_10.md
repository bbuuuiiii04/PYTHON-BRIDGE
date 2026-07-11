---
doc_status: current
truth_level: frozen software baseline + coverage/blocker report
last_verified_commit: 808391f
last_verified_date: 2026-07-11
validation_scope: >
  Frozen Stage-1 EAR-benchmark run (AWR-200) of tools/spectral_ear_benchmark.py at code
  HEAD 1a51431 over the local AWR-182 label layer (label sha256[:16] bda63553da99cb9e).
  Records
  usable/excluded counts, cache/beatgrid resolution identity, per-axis metric availability,
  and the marker-sensitivity proof-of-function pilot. Read-only run: no extraction, no
  cache/config/runtime writes, no bridge/hardware contact. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.
---

# Spectral EAR benchmark — Stage-1 frozen baseline / coverage report (AWR-200)

This is the frozen result of the first real run of the Stage-1 harness
(`tools/spectral_ear_benchmark.py`, spec
`docs/plans/active/spectral_ear_benchmark_spec_2026_07_10.md`). It is **both** a baseline
(the one axis that scored) and a coverage/blocker report (what the current labels cannot
support). **AWR-200 is PARTIAL.**

## Run identity

- Harness HEAD at run: `808391fe749d2f9ebeff286e9dff44834a3c9eab` (the exact committed code
  after the 2026-07-11 trust-repair pass — single `call_planner` anti-leak boundary,
  amendment-via-parent grouping, markers-scored availability gate, per-radius comparable
  denominators, real fold-disjointness invariant, identity-collision warnings). This report is
  committed immediately after so it cites the precise code it was run against. The pilot numbers
  below are unchanged from the earlier `1a51431` run (all 16 markers were comparable at both
  radii), so the frozen baseline value is preserved; only the code identity and honesty wording
  moved.
- Labels: `local/labels/operator_track_labels_2026_07_09.jsonl` (gitignored machine layer).
- Label revision hash: sha256[:16] = `bda63553da99cb9e`, 41 rows.
- v4 cache identity: resolved live through each track's **current** Rekordbox filepath +
  ANLZ beatgrid fingerprint (`spectral_cache._cache_key` = audio filepath + beatgrid
  fingerprint). Raw cache files were never iterated (stale duplicates exist by design).
- pyrekordbox 0.4.4; master.db opened READ-ONLY (the same read the runtime bridge does).
- Bridge/hardware: untouched. Nothing started, restarted, or written.

## Coverage / group manifest

- Rows: 41 — primary 33, amendment 3, meta 5.
- Lineages (tracks): 26 — **usable 21**, excluded 5.
- Usable entries: 31.
- Exclusions by reason:
  - `marker_blocked_pending_remap`: 2 — OCHO, Latch (charter §D: blocked until remapped).
  - `scripted`: 1 — BLACKPINK - JUMP.
  - `unusable_grid`: 1 — Toxic (Britney).
  - `variable_bpm`: 1 — s.o.s.
- REWIND is **usable** (charter §D includes its post-reanalysis eight-drop result).
- Grouped leave-one-lineage-out inventory: 21 folds (one per usable lineage); Utopia's 10
  entries (8 UT-* + 2 amendments) form one lineage and never split. Full inventory in the
  harness output.

## Per-axis metric availability (frozen)

No blended score is emitted; each axis stands alone (charter §D: "No blended score may hide
a failed axis").

| Axis | Status | Why |
| --- | --- | --- |
| tier | **UNAVAILABLE** | no structured `operator_tier` (ordinal per drop) in labels — verdicts are free text |
| family | **UNAVAILABLE** | no structured `operator_family` + per-drop within-track judgment |
| darkness | **UNAVAILABLE** | no structured shape + start/end beat + bar count per drop |
| growl | **UNAVAILABLE** | no structured `operator_growl_span`; growl centroid also pending backfill |
| laser | **UNAVAILABLE** | no structured `operator_laser_suitability`; more laser labels wanted (charter D) |
| marker_sensitivity | **AVAILABLE (pilot only)** | model-only; needs no operator gold — but coverage-limited (below) |

Every UNAVAILABLE axis is reported as such — **never a fabricated zero or PASS**. AWR-200's
PARTIAL/complete status is a single shared `is_partial` predicate over these accuracy axes;
marker-sensitivity availability is deliberately excluded, so the 2-track marker pilot can
never flip Stage 1 to complete. The loss shapes are already encoded for when gold arrives: squared ordered tier error (adjacent=1,
T1↔T3=4) + missed-T3/false-T3 counts; darkness detection then raw-beat start/end + exact
bar-length agreement; family correctness + flapping; growl span overlap/boundary; laser
pins (charter §C.1/§D).

## Marker-sensitivity — proof-of-function pilot (NOT the SOL baseline)

Model-only metric: hold audio fixed, perturb each drop marker ±1/±2 beats, re-run the real
`lighting_moments_v2.build_track_plan`, count family/tier/darkness flips.

- Resolution: **2 of 21** usable lineages resolved (`resolved` 2, `not_in_db` 19).
- **Coverage limit:** only Sexy and Utopia carry a Rekordbox `content_id` in the label
  layer; the 19 other usable lineages store track names only and cannot be DB-resolved.
  Adding content_ids to the B-row labels is a curation task.
- Measured over 2 resolved tracks / 16 markers (0 skipped):
  - ±1 beat flips — family 25.0%, tier 6.2%, darkness 0.0%.
  - ±2 beat flips — family 43.8%, tier 12.5%, darkness 18.8%.
- SOL published reference (**different sample** — 15 tracks / 113 markers): ±1 family 6.2%,
  tier 32.7%, darkness 23.0%; ±2 family 23.9%, tier 46.0%, darkness 62.8%.
- **NOT like-for-like.** This pilot resolved far fewer tracks/markers than SOL's 15/113. Do
  NOT compare the percentages or claim improvement/regression. The aggregation is documented
  in `marker_sensitivity()` (a marker is ±k-sensitive on an axis if the output differs at −k
  OR +k). This run only proves the harness computes the axis end-to-end through the real
  planner and is cache-safe.

## What blocks a full baseline (Stage-1 exit criteria)

1. **Structured gold curation.** Turn the operator's free-text verdicts into per-drop
   structured fields (`operator_tier`, `operator_family`, `operator_darkness_shape` +
   start/end/bars, `operator_growl_span`, `operator_laser_suitability`). Operator-gated.
2. **content_ids on the B-row labels** so the marker axis (and later accuracy axes) can
   resolve the full corpus, not just Sexy/Utopia.
3. **OCHO/Latch marker remaps** against current ANLZ, and the **growl-centroid backfill**,
   before their axes count.

Until 1–3 land, AWR-200 stays PARTIAL: the harness, manifest, grouping, folds, and the
marker pilot are real and runnable; the numeric accuracy baseline every Stage-2 round must
beat does not yet exist because the labels cannot yet express it.

## Reproduce

```bash
python3 tools/spectral_ear_benchmark.py --head "$(git rev-parse HEAD)"                 # core, stdout
python3 tools/spectral_ear_benchmark.py --head "$(git rev-parse HEAD)" --resolve-db    # + marker pilot
python3 -m unittest tests.test_spectral_ear_benchmark                                  # 15 tests
```
