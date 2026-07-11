---
doc_status: current
truth_level: implemented-and-software-tested
last_verified_commit: 311f407
last_verified_date: 2026-07-11
validation_scope: >
  Stage-1 EAR benchmark harness (AWR-200 / AWR-195 stage 1). Describes the as-built
  tools/spectral_ear_benchmark.py + tests/test_spectral_ear_benchmark.py: a read-only
  harness over the AWR-182 ear-truth labels and the existing v4 cache. Software-tested
  only (32 unit tests green after the 2026-07-11 marker-availability + content_id-coverage
  pass — single call_planner anti-leak boundary, amendment-via-parent grouping with a
  duplicate-id guard, availability gate that now requires markers scored AND at least one
  comparable ±1/±2 perturbation, per-radius comparable denominators, real fold-disjointness
  invariant, identity-collision warnings; core run + --resolve-db run exercised against the
  local 41-row label layer, which now carries proven content_id locators for all 21 usable
  lineages so the marker axis resolves 21/21 / 158 markers). No runtime lighting behavior
  changes. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
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
- **Marker axis coverage** now spans the **full usable corpus**: the label layer carries a
  proven Rekordbox `content_id` for all 21 usable lineages (Sexy/Utopia already had one; the
  19 B-rows were mechanically enriched from the read-only resolution lane's uniqueness-swept
  IDs), so the marker axis resolves **21/21 lineages / 158 markers**. It is still **NOT
  like-for-like with SOL's 15-track / 113-marker sample** — a different track/marker set and
  possibly a different roll-up; do not compare the percentages. OCHO/Latch also have recorded
  content_ids but stay excluded `marker_blocked_pending_remap` (a locator does not un-block a
  marker case). The growl-centroid values these tracks rely on are already present, aligned,
  and real-valued in the strict v4 cache — no backfill remains; only their *musical*
  correctness is an open Stage-2 question.
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
  Every production-planner call routes through the single `call_planner()` boundary, which
  enforces a positive allowlist (`PLANNER_ALLOWED_FIELDS` = v4 + beat indices only) AND the
  `LEAK_FORBIDDEN_FIELDS`/`assert_no_leak()` guard, then unpacks and calls — so the base and
  every perturbed call are guarded at the real invocation point, not by a one-off check on a
  hand-built dict. IDs never enter a formula. No benchmark-owned copy of any runtime
  formula/constant exists — the harness *imports and calls*
  `lighting_moments_v2.build_track_plan` for the only metric it computes.
- **Grouping.** One lineage per track (content_id, else normalized track). A track and its
  amendments/edits leave together: an amendment's lineage is resolved through its `amends`
  parent chain to the primary ancestor, so an amendment with no content_id or a different
  track string still rides with its parent. Missing/cyclic/ambiguous/non-primary parent links —
  and a duplicated amendment own-id (which would otherwise let the by-id rewrite corrupt a
  primary's lineage) — are never silently split: they raise a loud validation warning and the
  amendment is left ungrouped. Same-title/no-content_id identity collisions cannot be resolved
  without curation;
  the harness surfaces a deterministic identity warning/limitation rather than guessing.
- **Folds.** Grouped leave-one-lineage-out. `build_folds` asserts the real invariant — the
  held-out lineage's entry ids (already including its resolved amendment lineage) never appear
  in any train lineage — replacing the earlier tautological `held.key not in train_keys` check.
  AWR-182 is development/regression data, not a blind holdout — the harness makes no
  unseen-holdout claim. Stage-2 acceptance additionally requires the new 20-group blind batch
  (charter §D), which this harness does not fabricate.

## Part E — acceptance tests and what this slice can / cannot score today

`tests/test_spectral_ear_benchmark.py` (32 tests, all green) proves, on small synthetic
fixtures (no real cache/DB/planner):

- meta and amendment rows are not primary examples;
- exclusions are explicit and each carries a cited reason; the manifest counts them;
  an undeclared EXCLUDED row is flagged;
- the real fold invariant: no entry id and no resolved amendment lineage appears in both
  train and test of any fold — including the hard case of an amendment carrying no
  content_id and a different track string, which still rides with its parent;
- amendment grouping follows the `amends` parent link; missing / cyclic / ambiguous parent
  links AND a duplicated amendment own-id (which would else corrupt a primary's lineage) warn
  loudly and leave the amendment ungrouped (never silently merged/split);
- accuracy axes stay UNAVAILABLE — never zero, never PASS; the marker axis is gated on
  markers actually SCORED **and** at least one comparable ±1/±2 perturbation existing (a
  resolved track that scores zero markers, OR scores markers whose every ±1/±2 offset falls
  out of range or collides with another drop so both flip rates come back None, reads
  UNAVAILABLE — not a hollow AVAILABLE on track or baseline-decision count);
- `call_planner` — the single boundary every base and perturbed planner call routes through —
  rejects any forbidden label/locator field OR unexpected field, and passes clean model inputs;
- marker-sensitivity flip counting is correct against a synthetic planner seam, the seam
  receives only model inputs, a marker with no comparable perturbation at a radius is dropped
  from that radius's denominator (per-radius `comparable_pm1`/`comparable_pm2`), and unresolved
  tracks never reach the planner;
- same-title/no-content_id identity collisions surface a deterministic warning/limitation
  (identity is flagged for curation, never guessed);
- the report is byte-deterministic and the core run is PARTIAL with the marker axis
  UNAVAILABLE and the identity limitation surfaced;
- **the completion gate holds**: with a resolved marker pilot AVAILABLE but the accuracy axes
  unavailable, `is_partial` and the report status both stay PARTIAL (regression test — a
  marker pilot never flips Stage 1 to complete).

**CAN score today:** the validated/grouped/leak-safe corpus manifest, the LOLO fold
inventory, and (with `--resolve-db`) the marker-sensitivity axis via the real planner —
now across the full 21-lineage usable corpus (21/21 resolved, 158 markers), not a 2-track
pilot.

**CANNOT score today:** any accuracy axis (tier/family/darkness/growl/laser) — no structured
per-drop operator gold exists in the labels. Blocked on a curation pass (structured
operator tier/family/darkness/growl/laser fields), plus the OCHO/Latch ear decisions
(blackout lengths / drop-vs-buildup + tier). Content_ids on the B-rows are DONE, and the
growl-centroid values are already present/aligned/real-valued in the strict v4 cache — no
backfill remains, though their *musical* correctness is a separate Stage-2 validation item.
Until the curation pass and OCHO/Latch decisions land, AWR-200 stays PARTIAL and no Stage-2
round can be accepted on an accuracy number this harness cannot yet produce.
