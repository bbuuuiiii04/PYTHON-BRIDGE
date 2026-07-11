---
doc_status: current
truth_level: implemented-and-software-tested
last_verified_commit: 8256402
last_verified_date: 2026-07-10
validation_scope: >
  Stage-1 EAR benchmark harness (AWR-200 / AWR-195 stage 1). Describes the as-built
  tools/spectral_ear_benchmark.py + tests/test_spectral_ear_benchmark.py: a read-only
  harness over the AWR-182 ear-truth labels and the existing v4 cache. Software-tested
  only (15 unit tests green; core run + --resolve-db run exercised against the local
  41-row label layer). No runtime lighting behavior changes. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.
---

# Spectral EAR benchmark — Stage-1 spec (AWR-200)

This documents the harness that already exists at `tools/spectral_ear_benchmark.py`
(tested by `tests/test_spectral_ear_benchmark.py`). It is the substrate every Stage-2
decision-layer round must eventually beat. Code wins over this doc if they ever
disagree.

## Part A — purpose, scope, context

The spectral v4 refactor program (AWR-195, charter
`docs/plans/active/spectral_v4_refactor_program_2026_07_10.md`) makes Stage 1 —
"lock one real ear benchmark first" — blocking. The independent SOL review
(`docs/research/sol_spectral_review_2026_07_09.md`) and its charter follow-up
(`docs/research/sol_panel_charter_review_2026_07_10.md`, §C five committed answers +
§D exact charter edits) fixed the metric shapes and anti-leak rules.

This harness is **offline tooling only**. It changes no runtime lighting decision, writes
no cache/config, and never contacts the bridge/hardware. It reads the operator's AWR-182
ear-truth labels (the gitignored machine layer
`local/labels/operator_track_labels_2026_07_09.jsonl`), validates/normalizes/groups them,
audits per-axis metric availability, and — when asked and when tracks resolve — computes
the one axis that needs no operator gold (marker sensitivity) by re-running the real
production planner.

**The honest Stage-1 finding:** the AWR-182 labels are the operator's *free-text* ear
verdicts. They carry no structured per-drop gold field. So every accuracy axis
(tier/family/darkness/growl/laser) is UNAVAILABLE today and the harness reports it as
such — never a fabricated zero or PASS. Stage 1 is therefore **PARTIAL**: the harness,
manifest, grouping, folds, and a proof-of-function marker pilot ship and run; the numeric
accuracy baseline is blocked on a label-curation pass, not on tooling.

## Part B — exact exclusions and coverage limits

Row taxonomy (from the 41-row layer): 33 primary moment entries + 3 amendments + 5 meta
rows (`SESSION-1-CLOSE`, `B2-HYPOTHESIS`, `B3-HYPOTHESIS-UPDATE`, `B4-THRESHOLD-TALLY`,
`B5-QUEUED`). Amendments fold into their parent lineage; meta rows are never examples.

Explicit, cited exclusions (charter §D + the AWR-182 label doc), applied at the
track/lineage level:

| Reason | Members today | Source |
| --- | --- | --- |
| `scripted` | BLACKPINK - JUMP (B3-8) | classification N/A-SCRIPTED; charter B3 rule |
| `unusable_grid` | Toxic (Britney, B2-5) | broken Rekordbox analysis; charter "unusable grids" |
| `variable_bpm` | s.o.s (B3-3) | changes BPM; charter "variable-tempo … until local-tempo support" |
| `marker_blocked_pending_remap` | OCHO (B2-3), Latch (B4-5) | charter §D: marker-indexed cases blocked until remapped against current ANLZ |
| `unresolved_version` | (0 today) | reserved; the Give It To Me Good duplicate becomes a member when B5 is verdicted |

**NOT excluded — REWIND (B1-5).** Charter §D: "Include REWIND's post-reanalysis eight-drop
result now" and "Exclude invalid observations, not repaired tracks." The old-grid snapshot
in `B1-5.measured` is stale but never used for scoring; REWIND resolves live and stays a
usable lineage. Cross-check: any row whose structured `classification` shouts
EXCLUDED/SCRIPTED but is not in the table above raises a surfaced validation warning.

Coverage limits stated plainly:

- **No structured gold** → accuracy axes cannot score (Part D/E).
- **Marker axis coverage** is capped by the label layer: only Sexy and Utopia carry a
  Rekordbox `content_id`; the 19 other usable lineages store track names only and cannot be
  DB-resolved. So the marker axis is currently a **2-track / 16-marker proof-of-function
  pilot, NOT SOL's 15-track / 113-marker baseline**. Adding content_ids to the B-row labels
  is a curation task.
- **Lineage grouping** uses `content_id` when present, else the normalized track string. It
  collapses same-track entries (all of Utopia's UT-*, REWIND primary+amendment). It does
  NOT merge remix siblings under different content_ids — none exist in this corpus; when
  they arrive a curated lineage map must precede trustworthy folds.

## Part C — input and output schema

**Input.** A labels JSONL path (default `local/labels/operator_track_labels_2026_07_09.jsonl`
if present). Each non-blank line is a JSON object. Rows are validated and normalized but
**never mutated**. Recognized fields: `track`, `title_exact`, `content_id`, `id`, `amends`,
`his_words`, `measured`, `classification`, `systems`, plus free-form notes. No field is
required beyond enough to classify a row.

**Output.** A deterministic markdown report (stdout or `--report PATH`), sections:

1. Header — HEAD (caller-stamped), labels path, label sha256[:16], AWR-200 status, evidence
   class. **Status is a single shared predicate** (`is_partial`) over accuracy-axis
   availability: PARTIAL until EVERY required accuracy axis (tier/family/darkness/growl/laser)
   is scorable. Marker-sensitivity availability is deliberately excluded — a marker pilot can
   never, on its own, complete Stage 1.
2. Coverage/group manifest — rows by kind; lineages (usable/excluded); usable entries;
   exclusions by reason with tracks; validation warnings.
3. Grouped LOLO fold inventory — one fold per usable lineage; held-out track, test entry
   ids, train lineage/entry counts.
4. Per-axis availability — tier/family/darkness/growl/laser (UNAVAILABLE + named missing
   field + loss shape) and marker_sensitivity (AVAILABLE only when tracks resolved).
5. Marker-sensitivity axis — resolution breakdown, coverage limit, measured ±1/±2 flip
   rates (when resolved), the SOL published reference labelled as a *different sample*
   (not for comparison), and the aggregation caveat.
6. What Stage 1 can and cannot score today.

CLI: `--labels PATH`, `--resolve-db` (opt-in; READ-ONLY master.db + v4 cache),
`--report PATH`, `--head SHA` (determinism stamp). No RNG, no wall-clock in output.

## Part D — anti-leak, grouping, and fold rules

- **Anti-leak.** Label fields that locate or describe an example
  (`content_id`/`title_exact`/`track`/`id`/`his_words`/`measured`/`classification`/notes)
  may be used to LOCATE an example and as ground truth, but must NEVER enter a predictor.
  `LEAK_FORBIDDEN_FIELDS` + `assert_no_leak()` enforce this; the production planner is only
  ever called with v4 features + beat indices. IDs never enter a formula. No benchmark-owned
  copy of any runtime formula/constant exists — the harness *imports and calls*
  `lighting_moments_v2.build_track_plan` for the only metric it computes.
- **Grouping.** One lineage per track (content_id, else normalized track). A track and its
  amendments/edits leave together.
- **Folds.** Grouped leave-one-lineage-out. `build_folds` asserts a lineage never appears in
  both train and test. AWR-182 is development/regression data, not a blind holdout — the
  harness makes no unseen-holdout claim. Stage-2 acceptance additionally requires the new
  20-group blind batch (charter §D), which this harness does not fabricate.

## Part E — acceptance tests and what this slice can / cannot score today

`tests/test_spectral_ear_benchmark.py` (15 tests, all green) proves, on small synthetic
fixtures (no real cache/DB/planner):

- meta and amendment rows are not primary examples;
- exclusions are explicit and each carries a cited reason; the manifest counts them;
  an undeclared EXCLUDED row is flagged;
- grouped lineages never split across a LOLO fold (multi-entry lineage moves together);
- accuracy axes stay UNAVAILABLE — never zero, never PASS; the marker axis is gated on
  resolution (unavailable at 0 resolved, available at >0);
- `assert_no_leak` rejects forbidden fields and passes clean model inputs;
- marker-sensitivity flip counting is correct against a synthetic planner seam, the seam
  receives only model inputs, and unresolved tracks never reach the planner;
- the report is byte-deterministic and the core run is PARTIAL with the marker axis
  UNAVAILABLE;
- **the completion gate holds**: with a resolved marker pilot AVAILABLE but the accuracy axes
  unavailable, `is_partial` and the report status both stay PARTIAL (regression test — a
  marker pilot never flips Stage 1 to complete).

**CAN score today:** the validated/grouped/leak-safe corpus manifest, the LOLO fold
inventory, and (with `--resolve-db`) the marker-sensitivity axis via the real planner —
currently a 2-track proof-of-function pilot.

**CANNOT score today:** any accuracy axis (tier/family/darkness/growl/laser) — no structured
per-drop operator gold exists in the labels. Blocked on a curation pass (structured
operator tier/family/darkness/growl/laser fields + content_ids on the B-rows), plus the
OCHO/Latch marker remaps and the growl-centroid backfill. Until then AWR-200 stays PARTIAL
and no Stage-2 round can be accepted on an accuracy number this harness cannot yet produce.
