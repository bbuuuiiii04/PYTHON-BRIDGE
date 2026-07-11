---
doc_status: current
truth_level: frozen software baseline + coverage/blocker report
last_verified_commit: @@CODECOMMIT@@
last_verified_date: 2026-07-11
validation_scope: >
  Frozen Stage-1 EAR-benchmark run (AWR-200) of tools/spectral_ear_benchmark.py at code
  HEAD @@CODECOMMIT@@ over the local AWR-182 label layer (label sha256[:16] a584dcb1e0293b24,
  41 rows) after the 2026-07-11 marker-availability + content_id-coverage pass. Records
  usable/excluded counts, cache/beatgrid resolution identity, per-axis metric availability,
  and the marker-sensitivity axis now measured across the FULL 21-lineage usable corpus
  (21/21 resolved). Read-only run: no extraction, no cache/config/runtime writes, no
  bridge/hardware contact. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Spectral EAR benchmark — Stage-1 frozen baseline / coverage report (AWR-200)

This is the frozen result of the Stage-1 harness (`tools/spectral_ear_benchmark.py`, spec
`docs/plans/active/spectral_ear_benchmark_spec_2026_07_10.md`). It is **both** a baseline
(the one axis that scored) and a coverage/blocker report (what the current labels cannot
support). **AWR-200 is PARTIAL.**

## Run identity

- Harness HEAD at run: `@@CODECOMMIT@@` — the committed code after the 2026-07-11
  marker-availability + content_id-coverage pass (marker-sensitivity availability now
  requires at least one COMPARABLE ±1/±2 perturbation, not just a scored marker; the
  frozen report/spec/registry blocker wording corrected). This report is committed
  immediately after so it cites the precise code it was run against.
- Labels: `local/labels/operator_track_labels_2026_07_09.jsonl` (gitignored machine layer).
- Label revision hash: sha256[:16] = `a584dcb1e0293b24`, 41 rows. (This layer was
  mechanically enriched with proven Rekordbox `content_id` locators for the 19 usable B-row
  lineages plus OCHO/Latch — a pure locator addition; no structured musical gold was added,
  and OCHO/Latch stay excluded `marker_blocked_pending_remap`. Prior hash was
  `bda63553da99cb9e`.)
- v4 cache identity: resolved live through each track's **current** Rekordbox filepath +
  ANLZ beatgrid fingerprint (`spectral_cache.get_cached_v4` = audio filepath + beatgrid
  fingerprint, strict load). Raw cache files were never iterated (stale duplicates exist by
  design).
- pyrekordbox 0.4.4; master.db opened READ-ONLY (the same read the runtime bridge does).
- Bridge/hardware: untouched. Bridge core (`python3 -m rb_ss_bridge_v2` push loop) verified
  0 processes before and after. Nothing started, restarted, or written.

## Coverage / group manifest

- Rows: 41 — primary 33, amendment 3, meta 5.
- Lineages (tracks): 26 — **usable 21**, excluded 5.
- Usable entries: 31.
- Exclusions by reason:
  - `marker_blocked_pending_remap`: 2 — OCHO, Latch (charter §D: blocked until remapped).
    Both now carry a recorded `content_id` (OCHO 247353885, Latch 114671300) for provenance,
    but remain excluded — recording a locator does not un-block a marker case.
  - `scripted`: 1 — BLACKPINK - JUMP.
  - `unusable_grid`: 1 — Toxic (Britney).
  - `variable_bpm`: 1 — s.o.s.
- **No identity-limitation warning fires:** all 21 usable lineages now carry a Rekordbox
  `content_id`, so the earlier "19 usable lineages grouped by normalized title only" warning
  is gone. No same-title/no-content_id collision remains, and no amendment parent-link
  warnings fired (all 3 amendments resolve cleanly to their parent).
- REWIND is **usable** (charter §D includes its post-reanalysis eight-drop result); its
  primary + amendment form one lineage under `content_id` 51640855 and never split.
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
| growl | **UNAVAILABLE** | no structured `operator_growl_span`; growl-centroid values are present/aligned/real-valued in the cache, but that is not the missing gold |
| laser | **UNAVAILABLE** | no structured `operator_laser_suitability`; more laser labels wanted (charter D) |
| marker_sensitivity | **AVAILABLE (full corpus)** | model-only; needs no operator gold — now 21/21 resolved |

Every UNAVAILABLE axis is reported as such — **never a fabricated zero or PASS**. AWR-200's
PARTIAL/complete status is a single shared `is_partial` predicate over these accuracy axes;
marker-sensitivity availability is deliberately excluded, so the marker axis can never flip
Stage 1 to complete. The loss shapes are already encoded for when gold arrives: squared
ordered tier error (adjacent=1, T1↔T3=4) + missed-T3/false-T3 counts; darkness detection then
raw-beat start/end + exact bar-length agreement; family correctness + flapping; growl span
overlap/boundary; laser pins (charter §C.1/§D).

**On growl-centroid, precisely:** the strict `get_cached_v4` load proves the
`growl_centroid_frames` field is present, aligned to `growl_band_frames`, non-NaN, and
real-valued (plausible ~65–495 Hz band) for all 21 usable lineages and for OCHO/Latch — so
there is **no backfill gap**. That is a data-shape fact, not a correctness proof: whether
those centroid values are **musically** right is a Stage-2 acceptance question, still open.
The growl *axis* stays UNAVAILABLE because the labels carry no structured `operator_growl_span`,
not because of any missing centroid data.

## Marker-sensitivity — full-corpus baseline (NOT the SOL baseline)

Model-only metric: hold audio fixed, perturb each drop marker ±1/±2 beats, re-run the real
`lighting_moments_v2.build_track_plan`, count family/tier/darkness flips.

- Resolution: **21 of 21** usable lineages resolved (`resolved` 21; 0 `not_in_db`, 0
  `cache_miss`, 0 `no_anlz`, 0 `no_drops`). This is the direct result of adding the proven
  content_ids to the B-row labels — the axis went from a 2-track pilot to the full corpus.
- Measured over 21 resolved tracks / **158 scored markers** (0 skipped — every drop had a
  baseline decision to perturb):
  - ±1 beat flips over 158 markers comparable at ±1 (0 not comparable) — **family 11.4%,
    tier 22.8%, darkness 24.7%**.
  - ±2 beat flips over 158 markers comparable at ±2 (0 not comparable) — **family 23.4%,
    tier 39.2%, darkness 51.3%**.
- SOL published reference (**different sample** — 15 tracks / 113 markers): ±1 family 6.2%,
  tier 32.7%, darkness 23.0%; ±2 family 23.9%, tier 46.0%, darkness 62.8%.
- **NOT like-for-like.** This is a DIFFERENT track/marker set (and possibly a different
  roll-up) than SOL's 15/113 sample. Do NOT compare the percentages or claim
  improvement/regression against SOL. The aggregation is documented in `marker_sensitivity()`
  (a marker is ±k-sensitive on an axis if the output differs at −k OR +k). This run proves the
  harness computes the axis end-to-end across the whole usable corpus through the real planner,
  cache-safe.

## Content_id resolution provenance (one soft pick to eyeball)

The 19 usable B-row content_ids were resolved by the read-only resolution lane
(`sol46spectral_resolution`) against the current Rekordbox DB, with a uniqueness sweep proving
no hidden sibling version for every flagged title. Eighteen are hard picks (literal
string-equal, exact title+artist, DB-side version suffix the operator omitted, or an explicit
remix token). **One is a soft locator pick worth an eyeball: B3-1 "Like I Like It — Mau P" →
87057007 (Original Mix).** Exactly two "Like I Like It" rows exist — Original (87057007) and a
"Dave Summer Edit" (245796494); the label carries no edit tag (the operator's convention always
tags edits) and his cited drop at ~0:58 lands on the Original's first drop (@0:58.13), while the
Edit has no drop near 0:58. High-confidence, but it is the single row resolved by drop-time
rather than a string match. This caveat is preserved here deliberately; its unique
original-vs-edit / time evidence is sufficient for this mechanical locator step.

## What blocks a full baseline (Stage-1 exit criteria)

1. **Structured gold curation.** Turn the operator's free-text verdicts into per-drop
   structured fields (`operator_tier`, `operator_family`, `operator_darkness_shape` +
   start/end/bars, `operator_growl_span`, `operator_laser_suitability`). Operator-gated. This
   is the real Stage-1 exit blocker; content_ids alone do NOT flip AWR-200 out of PARTIAL —
   the harness's own `is_partial` gate keys off accuracy-axis availability, not the marker
   pilot.
2. **OCHO/Latch ear decisions.** OCHO's markers now time-align to every cited event (including
   the 3:24 the operator thought was empty); only its two blackout *lengths* (1:59.6 → 4 beats;
   3:24 → 20 beats) and confirmation the live phrase fix is in the current ANLZ remain — taste
   calls, not derivable from a marker. Latch has no cited time and no mechanical anchor
   (drop-vs-buildup is an audio-energy property the grid cannot settle), so confirming its
   drop/buildup assignment and "this is T1" tier call needs the operator's ear or a re-measure.
   Both stay excluded until then.

**Resolved since the prior frozen run (no longer blockers):**
- **content_ids on the B-row labels** — DONE. All 19 usable B-rows now carry a proven,
  uniqueness-swept `content_id`, so the marker axis resolves the full 21-lineage corpus.
- **growl-centroid backfill** — not a gap. The strict v4 cache already holds present, aligned,
  non-NaN, real-valued `growl_centroid_frames` for all 21 usable lineages plus OCHO/Latch.
  Their *musical* correctness remains a Stage-2 validation item (see the growl note above),
  but there is nothing to backfill.

Until the two remaining blockers land, AWR-200 stays PARTIAL: the harness, manifest, grouping,
folds, and now the full-corpus marker baseline are real and runnable; the numeric accuracy
baseline every Stage-2 round must beat does not yet exist because the labels cannot yet express
it.

## Reproduce

```bash
python3 tools/spectral_ear_benchmark.py --head "$(git rev-parse HEAD)"                 # core, stdout
python3 tools/spectral_ear_benchmark.py --head "$(git rev-parse HEAD)" --resolve-db    # + marker baseline (READ-ONLY DB + cache)
python3 -m unittest tests.test_spectral_ear_benchmark                                  # 32 tests
```
