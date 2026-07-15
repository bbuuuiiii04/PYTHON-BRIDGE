---
doc_status: current
truth_level: Fable-authored Phase-0 protocol specification, verified against current code; specification only
last_verified_commit: 882d8c7
last_verified_date: 2026-07-15
validation_scope: >
  Documentation-only Phase-0 protocol specification for the bounded offline spectral
  AI falsification pilot defined by
  docs/research/spectral_ai_library_automation_design_review_2026_07_14.md. Authored
  under docs/prompts/active/spectral_ai_phase0_fable_manager_kickoff_2026_07_14.md.
  This document authorizes NOTHING: no implementation, no pilot execution, no model
  or stem install/run, no library sweep, no profile, no runtime/config/cache/label/
  audio/Rekordbox mutation, no bridge contact, no hardware action. A separate explicit
  operator authorization is required before any code in Part B is written.
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Phase-0 protocol specification — offline spectral AI falsification pilot

**Format note.** This uses the repo Part A–E spec structure as a *document format
only*. It is not a Codex handoff: any future implementation runs in a separately
authorized, named Claude CLI tmux seat under Fable's management
(`docs/agents/multi_agent_org_workflow.md`; kickoff §Management, operator amendment
2026-07-15).

**Evidence labels** are the review's: `confirmed-repo`, `confirmed-external`,
`measured`, `operator-decided`, `inferred`, `proposed`, `unknown`, `live-gated`.
Unlabeled statements in Parts B–E are `proposed` protocol rules.

---

## Part A — Context and verified current state (read; do not implement)

**`proposed`** Phase 0 packages the smallest experiment able to reject this idea:

> Can repeatable Brandon-authored judgments plus existing deterministic v4 evidence
> beat current F2 enough to justify one more offline experiment within 65 minutes of
> human work? (review §11.1)

**`operator-decided`** Closed 2026-07-14: the burden justifies a bounded experiment;
the ceiling is 65 active minutes / 113 atomic decisions across four sessions. Closed
2026-07-15: Fable orchestrates; non-Fable subagents may do deep reads/adversarial
reviews; execution rounds run in named Claude CLI tmux seats; never Codex. Also
closed 2026-07-15: the family vocabulary stays `WALL|COMET|HOUSE|mixed|none|unsure`
(4 families, 3 tiers — no expansion before the pilot) and the seven anchors are
fixed in B3.7.

**Verified repo facts at `882d8c7`** (each checked this round; pinned files are
byte-identical to the `790c625` anchor):

| Label | Fact | Evidence |
| --- | --- | --- |
| `confirmed-repo` | F2 is `build_track_plan` producing per-marker family/tier/darkness on the analysis worker; it has no genuine-drop classifier, growl-span, or laser-suitability output. | `lighting_moments_v2.py:1013` (`build_track_plan`), `:258` (`classify_family`), `:298` (`violence_tier`); worker call `state_manager.py:281` |
| `confirmed-repo` | The 16-beat drop-window vector exists. | `spectral_profile.py:619` (`drop_window_vector`) |
| `confirmed-repo` | Strict v4 cache identity = resolved path + mtime + size + beatgrid fingerprint. | `spectral_cache.py:288–292`, `:331–352` |
| `confirmed-repo` | `hardness_v0.py` (binary-T3 shadow, offline-only) and `approach_features_v0.py` (raw four-view descriptors, offline-only) exist with zero runtime importers, enforced by tests. | `tests/test_hardness_v0.py:415–440`, `tests/test_approach_features_v0.py:367–395` |
| `confirmed-repo` | All 17 retrieval-allowlist fields exist in the v4/profile surface. | `audio_spectral_features.py`, `spectral_profile.py` (grep-verified this round) |
| `confirmed-repo` | The packaged candidates `v4_exact_retrieval_v1`, `hardness_v0_all_markers_v1`, `approach_v0_diagnostic_v1`, and baseline B do **not** exist as code. Phase-0 implementation builds them to this spec. | zero grep hits across `*.py` at `882d8c7` |
| `confirmed-repo` | `local/` is gitignored; current operator/gold labels live there as development-only artifacts with `head: unknown` provenance. | `.gitignore:46`; review §2.3 |
| `operator-decided` | The SOL4 catalog (SHA-256 `ac3fdc9d4d8eb4d99735667ec52031143ddd94f662e3fa7264b213ee8c0c74f2`) is durable, non-authorizing creative input; its trace is §13 below. | review §2.5 |

**Provenance anchors (`proposed`, frozen):**

- `pilot_seed = spectral-ai-pilot-v1-790c625-2026-07-14` — a literal string. It keeps
  `790c625` even though HEAD has moved; it is an identity token, not a HEAD claim.
- Baseline A is named `current_f2_790c625`; its behavior is pinned by the fact above
  that F2's files are unchanged `790c625..882d8c7`. If any pinned file changes before
  Phase-1 execution, the implementing seat stops and reports the contradiction; it
  does not silently re-pin.
- `created_from_head` in every artifact records the implementing seat's actual HEAD.

---

## Part B — The protocol package (implement exactly; only when separately authorized)

### B0. Absolute rules — file fence and forbidden actions

Allowed writes, exhaustively (nothing else, ever):

1. New offline package `tools/spectral_pilot/` (modules in B1).
2. New tests `tests/test_spectral_pilot_*.py`.
3. Gitignored pilot workspace `local/spectral_ai_pilot/spectral-ai-pilot-v1-790c625-2026-07-14/`
   (artifacts in B7) plus a scratch subdirectory `…/scratch/` (deleted at cleanup).
4. The bookkeeping rows this spec's contract requires (doc_index, work registry,
   optional `spectral_analysis` inspect line).

Forbidden, exhaustively closing the review's ceilings: any write to runtime modules,
`config/`, the v4 cache, `local/labels/`, sidecars, audio files, any Rekordbox
database or ANLZ file, any `docs/` file beyond the bookkeeping rows; any import of
`tools/spectral_pilot` from runtime modules; any bridge process contact; any
network, download, model install, embedding, stem run, clustering, active learning,
review UI, provisional profile, full-library audio/feature sweep; any MIDI/DMX/
laser/Govee/SoundSwitch output; running anything during a live show. **This spec is
not permission to run the pilot** — Phase-1 execution needs its own operator
authorization after independent review of the implemented package.

Reality check for the implementing seat: the repo Stop hook auto-commits and pushes
dirty work at turn end. Diff-review every turn's tree before ending it; pause
mid-flight only behind `/tmp/rbss_orchestration.lock`
(`docs/agents/lessons/stop-hook-autosync-races-agents.md`).

### B1. Package layout (ordinary engineering, `proposed`)

```text
tools/spectral_pilot/
  __init__.py        # empty; no side effects
  schemas.py         # dataclasses + validators for every artifact row (B7)
  canonical.py       # canonical JSON bytes + SHA-256 helpers (B2)
  selection.py       # seed pool, eligibility, lineage/marker/repeat/anchor ordering (B3)
  candidates.py      # baseline B, v4_exact_retrieval_v1, diagnostics (B4)
  firewall.py        # FrozenFeatureRow + eligible-development-row types (B5)
  session.py         # card runner: sessions, timing, decision ledger, recovery (B6)
  scoring.py         # metrics, denominators, repeatability (B8)
  verdict.py         # pure verdict function (B8)
```

Pure functions everywhere; the only I/O lives in `session.py` (workspace files,
audio playback) and thin CLI entrypoints (`python3 -m tools.spectral_pilot.…`).
No module here may be imported by any repo-root runtime module; enforce with an
AST guard test copied from the `tests/test_hardness_v0.py:415` pattern.

### B2. Canonical bytes and hashing (ordinary engineering, `proposed`)

- Canonical JSON: UTF-8, `sort_keys=True`, separators `(",", ":")`, no NaN/Inf
  (nonfinite floats are protocol errors). Numbers cross the serialization boundary
  only as Python `int`/`float` (NumPy scalar types are rejected there); `-0.0` is
  normalized to `0.0`; floats serialize via `repr` round-trip.
- JSONL: one canonical JSON object per line, `\n` terminated.
- `sha256_hex(obj)` = SHA-256 over canonical bytes. For any artifact that embeds its
  own digest, compute with digest fields omitted, then insert (review §15.1 pattern).
- Every hash mentioned below is SHA-256 hex, lower-case; `[:16]` means the first 16
  lower-case hex characters.
- Selection-hash inputs (`SHA256(a || b || …)`): each field is rendered as a UTF-8
  string (numbers per the canonical rules above) and the fields are joined with the
  single byte `0x1F`. No other concatenation is permitted.
- The environment lock records the Python, NumPy, and `unicodedata.unidata_version`
  versions; text normalization's "punctuation" means Unicode general category `P*`.

### B3. Deterministic selection (review §§8–9, exact)

Insufficient-data rule used throughout: a floor miss yields `INCONCLUSIVE`; the pool
or budget is **never** expanded after any prediction or answer exists.

1. **Seed pool (60 rows).** Input: a read-only listing of current PDB locator rows +
   scripted IDs (no audio decode, no cache enumeration). Remove current development
   content IDs and scripted rows. Sort remaining locator IDs by
   `SHA256(pilot_seed || content_id_locator)`; take the first 60. Only these 60 may
   incur audio hashing and v4/grid/marker validation.
2. **Suspicious pairs.** Over the 60-row pool ∪ development manifest ∪ anchors:
   normalize text (Unicode NFKC, casefold, punctuation→space, collapse whitespace);
   version-token lexicon frozen as
   `remix|edit|bootleg|extended|radio|instrumental|vip|dub|mix|version|rework`.
   Emit a pair when: equal `audio_sha256`; or equal normalized artist + base title
   (bracketed/version-token suffix removed); or equal base title and duration within
   3.0 s; or equal normalized artist, duration within 3.0 s, and BPM within 0.10.
   Sort pair IDs by hash; record exactly
   `confirmed_related|confirmed_unrelated|unresolved`. Unresolved ⇒ every affected
   row excluded (prespecified exclusion).
3. **Eligibility (frozen before any candidate output):** not in current development
   lineages; non-scripted; exact current v4 payload present and valid; ≥2 existing
   Rekordbox candidate drop markers with full 16-beat coverage; no unresolved
   duplicate/lineage ambiguity; no cross-partition related group. Lineage curation
   is a per-row requirement independent of pair emission: every selected row needs
   `lineage_review_state = confirmed` from the 30-minute manual prep; a row whose
   lineage cannot be confidently assigned inside that cap (including a
   metadata-stripped or re-encoded sibling that no suspicious-pair rule catches) is
   `unresolved` and excluded.
4. **Lineages and markers.** Sort eligible lineages by
   `SHA256(pilot_seed || recording_lineage_id)`; take the first 18 (need 18 distinct
   `recording_lineage_id` AND 18 distinct `audio_duplicate_group`). When a lineage
   has more than one eligible row, its representative is the row with the lowest
   `SHA256(pilot_seed || content_id_locator)` — never input order. Per lineage,
   sort eligible markers by `SHA256(audio_sha256 || marker_beat)`; take the first
   two. Those same two markers are that lineage's family montage. Fewer than 18
   surviving lineages ⇒ `INCONCLUSIVE`.
5. **Hardness anchors.** Sort the 36 selected marker rows by
   `SHA256(pilot_seed || audio_sha256 || marker_beat || "hardness-anchor")`; assign
   anchors T1, T2, T3 round-robin, exactly 12 each. Pair side (which clip plays
   first) uses a separate frozen hash bit
   (`SHA256(pilot_seed || card_id || "pair-side")` low bit).
6. **Repeats.** Sort cards by `SHA256(pilot_seed || card_id || "repeat")`; choose 6
   marker cards and 4 family montages; place them non-adjacently with two marker
   repeats per pilot session and family repeats distributed 1/1/2. Repeats never add
   sample size.
7. **Anchors (7) — `operator-decided` 2026-07-15.** Brandon fixed the seven
   anchors directly (chat veto rounds over his own development labels); the
   deterministic candidate ordering that previously stood here is retired:

   | Role | Anchor (development lineage) | Clip provenance |
   | --- | --- | --- |
   | WALL family ref | REWIND — Ray Volpe, Sullivan King | gold row, first labeled drop (beat 128) |
   | COMET family ref | Laserbeam (TiDo Edit) — Ray Volpe | gold row, third labeled drop (beat 472) |
   | HOUSE family ref | Utopia — Dombresky | gold row, second labeled drop (beat 384) |
   | `mixed` example | Sexy (Extended Mix) — Matt Sassari | gold rows, first + second labeled drops (beats 192 + 288; HOUSE vs COMET) |
   | T1 hardness ref | ESSE – Work It x Dom Dolla – Take It (Bellevue Rework) | gold row, first labeled drop (beat 128) |
   | T2 hardness ref | Like I Like It — Mau P | its single phrase-drop marker (beat 124, ≈0:58) operator-confirmed a genuine drop 2026-07-15 |
   | T3 hardness ref | I Cannot (Extended Mix) — Anti Up | operator-named moment 1:19.4 (nearest beatgrid beat, ≈176), decided 2026-07-15; the track's phrase-drop marker at beat 64 (≈0:29) was operator-ruled NOT a genuine drop — anchors are operator-confirmed clips and need not sit on phrase markers; no Rekordbox data is created or moved |

   An anchor that proves ineligible at implementation time (missing audio, invalid
   v4, no usable marker) stops with a report — never a silent substitute.
   One clip may not fill two roles; anchor lineages must be unrelated to each other
   and to the 18 pilot lineages. No substitution mid-session: a rejected anchor
   stops the axes that depend on it (family axis per review §8.1; a rejected tier
   anchor stops the hardness axis) — recorded, not worked around. No eligible
   candidate for a role is recorded and treated exactly like a rejection.
8. **`manifest_id`** is derived only after canonical selected rows are final: the
   SHA-256 of the selected-row canonical bytes. The manifest must rebuild
   byte-identically, keep every related group in one split, and have unique IDs. An
   unresolved relationship or overlap discovered **after** selection is a hard FAIL
   (not an exclusion).

Row schema (every seed-pool and selected row; review §9.2 verbatim):
`schema_version, pilot_seed, created_from_head, track_instance_id,
content_id_locator, audio_sha256, audio_duplicate_group, recording_lineage_id,
split_role, beatgrid_fingerprint, marker_set_fingerprint, label_store_hash,
exclusion_reason, lineage_review_state, curator_confirmation,
family_montage_marker_ids`. `track_instance_id =
SHA256(pilot_seed || content_id_locator)[:16]` (ordinary engineering; 64-bit
truncation, uniqueness enforced by B3.8). Locator/title/artist/path are audit
fields and never reach a predictor.

Enum domains (exact): `split_role ∈ {pilot, development, anchor}`;
`lineage_review_state ∈ {confirmed, unresolved}`; `curator_confirmation ∈
{confirmed_related, confirmed_unrelated, unresolved, not_applicable}`;
`exclusion_reason ∈ {none, development_overlap, scripted, missing_v4, invalid_v4,
insufficient_markers, unresolved_duplicate, unresolved_lineage,
cross_partition_related, pool_cap}`.

Card identity (exact): marker cards
`card_id = SHA256(pilot_seed || audio_sha256 || marker_beat || "marker-card")[:16]`;
family montage cards `SHA256(pilot_seed || recording_lineage_id ||
"family-card")[:16]`; anchor cards `SHA256(pilot_seed || "anchor-card" ||
anchor_role)[:16]`; repeat instances `SHA256(source_card_id ||
"repeat-instance")[:16]` with `repeat_of_card_id = source_card_id`. A marker card
carries both the marker-state question and (if genuine) its hardness pair; the
B3.6 repeat lottery draws over original marker and montage card IDs.

A separate `development_training_manifest` freezes development + anchor row IDs,
per-axis permitted targets, exclusions, duplicate/lineage groups, scaler population,
current label-file hashes (provenance limitation `head: unknown` retained), and its
own output hash. Incomplete rows are eligible only for targets they contain.

### B4. Candidate contracts (review §6, exact)

Interface (all candidates):
`predict(method_version, frozen_feature_row, eligible_development_rows) -> PredictionRow`.
`PredictionRow` records method/version, manifest/input/scaler hashes, eligible and
excluded neighbour IDs, distances, per-axis value or abstention, raw score, reason
codes, error state. Only canonical decision fields enter its hash; wall time/RSS
telemetry goes to `resource_report.json` only. All prediction files and
`prediction_hashes.json` are written and frozen **before any card is shown**.

- **Baseline A `current_f2_790c625`:** call the existing
  `lighting_moments_v2.build_track_plan` path read-only at the frozen markers.
  Family mapping for the two-moment target: `NEUTRAL`→`none`; abstain if either
  plan row is missing; both match → that family; differ → `mixed`. Hardness: compare
  the marker's frozen tier with the anchor's **assigned role tier from B3.5/B3.7**
  (frozen at selection; session A only confirms the anchor or stops the axis — it
  never feeds a prediction input, so all predictions freeze before any card
  including session A's); equality → `tied`; missing tier → abstain. F2 abstains
  for genuine-marker state.
- **Baseline B `development_majority_v1`:** exact majority of comparable
  genuine/not-genuine targets in the development-training manifest; an exact tie
  abstains. Genuine-marker axis only.
- **Candidate C `v4_exact_retrieval_v1`:** no learned model. Marker window
  `spectral_profile.drop_window_vector(..., width=16)`. Positive allowlist, exact
  order: `sub_db, bass_db, mid_db, high_db, air_db, full_db, low_swing_db,
  attack_low_p90, perc_low, harm_ratio, centroid_hz, growl_flatness,
  sustain_mid_db_d8, sustain_high_db_d8, onset_density_mh, fluxsum_mh,
  pre_gap_beats`. `coverage < 16`, missing key, or nonfinite ⇒ abstain. Per-axis
  frozen median centering and MAD scaling from the manifest's scaler population;
  zero-MAD fields dropped and the retained list hashed. Euclidean distance; first
  retain only the nearest eligible row per unrelated lineage, then `k=3` lineages;
  the query's `recording_lineage_id` and `audio_duplicate_group` are excluded.
  Fewer than three eligible lineages or zero retained fields ⇒ abstain. Label vote
  or ordinal median; ties abstain. Equal-distance tie-break: frozen
  `track_instance_id`, then marker beat. OOD: nearest distance above the frozen
  leave-one-lineage-out nearest-distance 95th percentile (NumPy
  `method="linear"`) ⇒ abstain. Hardness pair mapping: retrieval's ordinal
  T1/T2/T3 prediction compares against the anchor's assigned role tier — higher →
  `harder`, equal → `tied`, lower → `softer`, missing/abstained → abstain. Family retrieval pools median + IQR over exactly
  the two frozen family-montage rows per lineage; its development target uses the
  matching two-row development montage, never a genuine-only subset.
- **Diagnostics (never in integrated PASS):** `hardness_v0_all_markers_v1` runs
  frozen `hardness_v0` at every selected marker (continuous `H`, binary T3-path
  fire, winning path, marker-shift range, or abstention). `approach_v0_diagnostic_v1`
  emits raw approach/landing descriptors and ±2-beat ranges; no class output.

No combined v4-plus-anything vector. No embedding, stems, trained model, cluster
default, active learning, or confidence surface anywhere in Phase 0/1.

### B5. Feature and metadata firewall (review §9.3, exact)

`firewall.FrozenFeatureRow` is a frozen dataclass holding **only** the allowlisted
acoustic/structure fields plus the numeric marker locator needed to slice audio.
Its constructor rejects unknown keys. Candidates receive only `FrozenFeatureRow` +
eligible development rows. They may never receive: title, artist, playlist, genre,
cover art, content ID, path text, notes, marker names/types; old human labels
beyond the explicitly eligible development targets; another method's weak/
provisional predictions; calibration/test answers or split-selection scores.
Predictions, candidate code hash, environment hash and all input hashes freeze
before human responses. The existing planner allowlist is not treated as proof a
new candidate is safe.

### B6. Human sessions (review §8, exact) — the four-session script

**Prediction-hidden, not listener-blind.** Before an answer is saved, the runner
hides title, artist, playlist, cover art, content ID, old notes, prior labels,
predictions, method, explanation, confidence, and neighbour identity. Cards carry
neutral IDs; recognition is recorded, never prevented.

- **Session A — anchors (≈15 min, 7 decisions):** the seven fixed anchors from
  B3.7, one confirm/reject decision each (the ear-check of the exact clips; roles,
  vocabulary, and anchor identities were already decided 2026-07-15). A family-vocabulary rejection or an
  indecisive `mixed` anchor stops the family axis before the pilot; a rejected tier
  anchor stops the hardness axis. This is the review's operator gate (§20 Q1) — it
  never re-asks the closed burden/workload decisions and its answers are never used
  for method selection or holdout scoring.
- **Sessions P1–P3 — six lineages each (≈15 min):** per marker card, at most:
  1. `genuine | not_genuine | marker_wrong_or_ambiguous | unsure`;
  2. if genuine: `harder | tied | softer | unsure` against that card's frozen
     neutral-ID anchor clip, pair side per B3.5.
  Per lineage, once: play the two frozen montage clips; ask
  `WALL | COMET | HOUSE | mixed | none | unsure` about those two moments only.
  Display-only note (ordinary engineering): cards may render `none` as
  "none (calm / NEUTRAL)" — the stored enum value stays `none`.
  Two marker-repeat cards per session (each up to two repeated answers) and family
  montage repeats 1/1/2 per B3.6.

**Atomic decision** = one committed answer to one question (anchor confirmation,
marker-state call, hardness comparison, family call, or any repeat). Answers are
editable before commit (that time counts, per the review) and **immutable after
commit — there are no re-commits** (review §5: immutable response rows). The
decision count is therefore the count of committed answers, ≤113 by construction;
the runner refuses commits past 113 total and past any per-card maximum.

**Active time** = wall clock from a session's first audio playback to its last
durable row, summed across sessions and resumed segments; there is no off-clock
preparation for Brandon. Every first playback of a card appends a durable
`playback` row (card_id, UTC), so a crashed segment's elapsed time is
reconstructed from its own rows — a crash never erases listened time; at most the
tail between the last durable row and the crash goes uncounted, and every crashed
segment is reported as such in the burden ledger. The runner displays and records
both counters; crossing 65 minutes or 113 decisions ends intake immediately and
gate 3 evaluates it.

**Rules:** `unsure` is always valid, never forced into a class. `marker_wrong_or_
ambiguous` rows are excluded from acoustic accuracy and reported separately; no
Rekordbox marker is edited. A skipped card is recorded `skipped` with zero
decisions and becomes unavailable truth. Fatigue/voluntary stop: Brandon may stop
any session immediately; the stop reason is recorded; "stopped because exhausting"
is a workload FAIL by gate 3. Never more than one session per calendar day —
machine-local date, recorded alongside each commit's UTC timestamp; a resumed
segment belongs to its origin session regardless of date, and a **new** session
may not start on a local date that already holds any commit.

**Interrupted-session recovery:** every commit is durable (append-only
`responses.jsonl` with per-row hash chaining to the frozen card manifest). Resume
re-opens at the first unanswered card in frozen order; committed answers are
immutable and never re-asked, so recovery adds zero decisions and only the new
segment's active time. Card order, repeats, and pair sides come from the frozen
manifest, so drift between segments is impossible; a detected order mismatch is a
hard FAIL (gate 1). A torn trailing record (final line unterminated or invalid) is
dropped and logged `torn_tail`; an **interior** chain break is gate-1 tampering.
A card whose audio played without a commit before an interrupt is `re_exposed` on
resume; if a re-exposed card is a repeat source or instance, that repeat pair is
excluded from the gate-2 consistency counters (the comparability floors still
apply).

**Response independence:** `responses.jsonl` lives apart from predictions; the
session runner reads only `card_manifest.jsonl` + audio and verifies
`prediction_hashes.json` exists and is complete before the first card, without
reading prediction contents. Scoring later verifies the prediction files still
match their frozen hashes.

### B7. Workspace artifacts (review §11.3, exact names)

All under `local/spectral_ai_pilot/spectral-ai-pilot-v1-790c625-2026-07-14/`:

```text
artifact_manifest.json      lineage_manifest.jsonl      card_manifest.jsonl
candidate_contracts.json    predictions/<method>.jsonl  prediction_hashes.json
responses.jsonl             playbacks.jsonl             metrics.json
resource_report.json        verdict.json                report.md
```

`playbacks.jsonl` is the durable playback/skip ledger backing the B6 time
accounting; it rows into `artifact_manifest.json` like every other artifact.

Every artifact-manifest row: type/schema/path/producer/consumer/input hashes,
output hash, HEAD, environment-lock hash, timestamp, `mutable:false`. `report.md`
is a view; machine JSON is authority. Immutable retained artifacts ≤ 50 MB;
`scratch/` ≤ 500 MB and deleted at cleanup.

Row schemas (exact; all rows also carry `schema_version` and `pilot_seed`):

- `card_manifest.jsonl`: `card_id, card_type
  (anchor_confirm|marker_state|hardness_pair|family_montage|marker_repeat|family_repeat),
  session_index (A|P1|P2|P3), order_index, track_instance_id, marker_beat` (null for
  montage/anchor cards), `display_left_id, display_right_id` (hardness pairs, else
  null), `anchor_role` (anchor/hardness cards, else null), `repeat_of_card_id`
  (repeats, else null), `clip_spec` (audio_sha256 + exact beat window), `card_hash`.
- `responses.jsonl` (append-only): `card_id, commit_index` (the global atomic-
  decision counter), `question` (which of the card's questions this answers),
  `displayed_response, canonical_response` (pair answers converted to
  marker-relative `harder|tied|softer|unsure` before hashing), `recognized`
  (bool), `response_seconds, commit_utc, local_date` (machine-local date backing
  the one-session-per-day rule), `session_index, segment_index, prev_row_hash,
  card_manifest_hash`.
- `candidate_contracts.json`: per method — `method_version, positive_allowlist,
  scaler_population_hash, retained_field_hash, code_hash, environment_lock_hash,
  development_manifest_hash`.
- `prediction_hashes.json`: `{method_version: prediction_file_sha256}`,
  `card_manifest_hash, lineage_manifest_hash, freeze_utc`.
- `metrics.json`: one block per B8 reporting item (per-axis counts/accuracies/
  abstentions, four-state denominators per method and axis, repeat counters,
  stability flip rates, burden ledger), each with raw counts, never only ratios.
- `verdict.json`: `gate_results` (1–7 each `PASS|FAIL|INCONCLUSIVE` + evidence
  refs), `integrated (PASS|FAIL|INCONCLUSIVE), failed_gates, inconclusive_floors,
  stopped_axes, input_hashes, created_from_head`.
- `resource_report.json`: `analysis_wall_seconds, peak_rss_bytes,
  scratch_peak_bytes, retained_bytes, manual_prep_minutes, human_active_seconds,
  decisions_total, cleanup_seconds, ceilings, breaches`.

**Clip rule (`operator-decided` 2026-07-15):** every audio clip in the pilot —
marker card, hardness pair side, family-montage element, anchor — plays a
16-beat **run-in** followed by the marker's 16-beat window:
`[max(0, marker−16), marker+16)`. Brandon raised the run-in mid-session-A
(before any commit; ledger empty): his development labels and anchor picks were
all made hearing builds/blackouts in context, so context-free slices would
generate truth from a different listening process than the labels the methods
train on. The **machine-scored window is unchanged** — `drop_window_vector`
stays 16 beats from the marker forward plus the frozen `pre_gap_beats` scalar;
the run-in is presentation-only and no candidate/feature contract moves. Clips
render read-only from the source file; playback temp files live in `scratch/`. Every card's `clip_spec`
must locate its clip(s) exactly: anchor rows carry their anchor marker beat (the
B3.7 gold beats now; Mau P and Anti Up pinned at Phase-1), and a family-montage
card's `clip_spec` carries **both** marker windows. The `mixed` anchor card is
montage-style: its `clip_spec` carries both of its lineage's B3.7 windows (Sexy
beats 192 + 288), since confirming "mixed" requires hearing both moments.

### B8. Metrics, reconciliation, and the verdict function (review §§9.4, 11.4, exact)

Every pilot input ends in exactly one state — `predicted`,
`abstained_with_reason`, `excluded_with_prespecified_reason`, or `hard_failure` —
and the counts must reconcile to the frozen manifest per method and axis. The
human ledger reconciles the same way: per axis, frozen truth rows = answered +
`human_unavailable` (skipped, `unsure`, marker-wrong, axis stopped), and the two
ledgers cross-check — a predicted row with no human state, or the reverse, fails
reconciliation.

Per-axis reporting: genuine-marker state (raw confusion, balanced accuracy when
both classes exist, abstention, marker-wrong rate, lineage-macro accuracy);
hardness (pairwise agreement, tie/unsure rate, within-lineage ordering,
false/missed T3 where comparable); family (exact counts, confusion,
`mixed/none/unsure`, lineage accuracy); marker stability (contract below); operator
burden (seconds and decisions per lineage, session position, fatigue, recognition
and unsure rates; split by recognized/unrecognized where counts permit, else state
that recognition may have influenced truth). Intervals resample whole lineages;
marker-micro results are secondary. No blended score may hide a failed axis.
Hidden repeats measure human consistency only.

Scoring rule: `correct(method)` is 1 only on exact answer match, else 0; abstention
scores 0 and is reported separately. Paired row delta =
`correct(candidate) − correct(baseline)`; a lineage is win/loss/tie by the sign of
its summed row deltas. Truth `unsure`/marker-wrong rows are unavailable, not
candidate errors.

Stability contract: gates only `v4_exact_retrieval_v1` genuine and hardness.
Recompute each central marker at beat deltas −2, −1, +1, +2 with the frozen
contract. Genuine compares against constant baseline B; hardness against current
F2's pairwise output at the same shifted marker and same frozen anchor. A decisive
central output that changes class or becomes abstain at a valid shifted window is a
flip; central abstention is unavailable; invalid shifted windows are excluded by
reason; a central row is stability-comparable only with ≥3 valid shifts; the flip
denominator is all valid shifts on those rows. Family and diagnostics report
sensitivity separately and never enter integrated PASS.

Repeatability (review §8.3): comparable floors — ≥4 marker-state, ≥3 hardness,
≥3 family repeats; below a floor ⇒ `INCONCLUSIVE`. Direct contradictions —
`genuine↔not_genuine`; `harder↔softer`; any change between two decisive family
answers (`WALL|COMET|HOUSE|mixed|none`). More than one direct contradiction in the
marker-state counter, more than one in the hardness counter, or **any** in the
family counter ⇒ repeatability FAIL. `tied`/`marker_wrong_or_ambiguous`/`unsure`
transitions are reported, not opposites.

The exact gates (verdict.py implements these and nothing else):

1. **Setup hard FAIL:** any leak, split overlap or unresolved relationship in the
   selected/cross-partition manifest, post-label prediction, nondeterminism,
   missing row, resource breach, or predictor-firewall breach.
2. **Human repeatability:** floors and contradiction limits above.
3. **Workload FAIL:** active time > 65 min, > 113 atomic decisions, or an
   operator stop because the workflow is exhausting.
4. **Genuine availability:** ≥28 comparable calls across ≥16 lineages, else
   `INCONCLUSIVE`. **PASS:** retrieval ≥6 more correct calls than baseline B, wins
   in ≥4 more lineages than it loses, ≤4 candidate abstentions.
5. **Hardness availability:** ≥24 comparable calls across ≥14 lineages, else
   `INCONCLUSIVE`. **PASS:** retrieval ≥6 more correct exact-pair calls than
   current F2 tier ordering, wins in ≥4 more lineages than it loses, ≤4 candidate
   abstentions.
6. **Family availability:** ≥14 comparable lineage answers, else `INCONCLUSIVE`.
   **PASS:** retrieval ≥4 more correct lineages than the exact-two-row F2 mapping,
   wins in ≥4 more lineages than it loses, ≤4 candidate abstentions. More than four
   total `mixed|none|unsure` human answers fails the two-moment family abstraction
   regardless of predictor score.
7. **Stability availability:** each gated axis ≥28 comparable central rows,
   otherwise `INCONCLUSIVE` (an availability miss here is a floor, never the FAIL
   branch). **PASS:** neither primary axis's flip rate is more than ten percentage
   points worse than its named baseline.

```text
FAIL         if setup, repeatability, workload, genuine, hardness, family, or stability fails;
PASS         only if every named availability floor and every axis PASS is satisfied;
INCONCLUSIVE only for a named repeatability/availability floor or <18 eligible seed-pool
             lineages, and only when no FAIL condition fired.
```

Early stops: any gate-1 event stops the pilot immediately; a workload breach stops
intake immediately; an anchor rejection stops the dependent axis before P1. An axis
stopped at session A leaves its availability floor unmet: that gate reports
`INCONCLUSIVE`, so the integrated verdict is at best `INCONCLUSIVE` (never `PASS`)
while unaffected axes still report per-axis results — this follows the review's
verdict function directly, it is not a new rule. A PASS authorizes nothing
automatically (review §11.5).

### B9. Resource ceilings (review §§9.2, 11.3, exact)

No download; no new model/dependency environment. Machine analysis (including
seed-pool audio hashing and v4/grid/marker validation): ≤30 min wall on one local
CPU process (no GPU), peak RSS ≤2 GB, scratch ≤500 MB, retained ≤50 MB, zero rows
silently dropped. Two identical runs produce byte-identical canonical prediction
rows and verdict inputs; timing/RSS telemetry stays out of those hashes and is
compared to ceilings in `resource_report.json`. Manual protocol preparation
(lineage review, suspicious-pair adjudication, duplicate review — none of it
Brandon's) ≤30 non-operator minutes. Human: ≤65 active minutes, ≤113 decisions.
Cleanup ≤10 min. Exceeding any ceiling stops Phase 0/1; it never expands a pool or
budget.

### B10. Failure behavior (exhaustive, fail closed)

| Condition | Behavior |
| --- | --- |
| Missing/corrupt/short/nonfinite v4 payload | Named abstention or prespecified exclusion; never re-extract |
| Unresolved audio/grid identity (path moved, mtime/size/grid mismatch) | Row excluded with reason before selection; after selection ⇒ gate-1 hard FAIL |
| Fewer than 18 surviving lineages | `INCONCLUSIVE`; pool never expanded post-hoc |
| Duplicate lineage / cross-split related group found after selection | Gate-1 hard FAIL |
| Session/card order drift, missing frozen card, hash-chain break | Gate-1 hard FAIL |
| Stale artifacts (input hash mismatch at any stage) | Refuse to run that stage; report the named hash mismatch |
| Accidental metadata exposure to Brandon or a predictor | Invalidate the affected axis (review §9.4 invalidators); record the event |
| Anchor rejected / vocabulary rejected | Dependent axis stops; remaining axes proceed; recorded |
| Resource ceiling breach | Stop; gate-1/gate-3 as applicable |
| SOL4 or any input artifact hash mismatch at implementation time | Stop and report; never proceed on unverified input |

### B11. Rollback and no-write proof

Rollback = delete `tools/spectral_pilot/`, its tests, and the pilot workspace
directory; no other file changed, so current live behavior is untouched by
construction. Proof obligations (implemented as tests + a runtime check in the
pilot CLI): (a) AST no-runtime-importer guard; (b) a workspace fence — every write
path asserts it resolves under the pilot namespace, and audio decode/playback
temp files are created only in `scratch/`; (c) byte-identity check — the pilot run
records SHA-256 of canonically **sorted** directory listings (names+mtimes+sizes)
of the v4 cache, `local/labels/`, resolved config files, the 60 pool audio files'
stat identity, the Rekordbox database paths, the sidecar export directory, and
`~/Library/Logs/rb_ss_bridge/`, before and after a run, and fails on any
difference; it also asserts zero new files under the repo tree outside the B0
fence; (d) zero bridge contact — the package never imports runtime modules except
the read-only F2/`spectral_profile`/`spectral_cache` call surfaces named in B4,
configures logging into `scratch/` **before** those imports so import-time logger
setup cannot write outside the namespace, and never opens sockets, MIDI, or
subprocesses (asserted by test-time audit of imports and a no-network guard in the
CLI).

---

## Part C — Invariants that must still hold

- Nothing in this package runs in, is imported by, or contacts the bridge runtime;
  the 200 Hz push loop, `StateManager` ownership, event immutability, and every
  AGENTS.md §6 invariant are untouched because no runtime file changes.
- SoundSwitch, lasers, LEDs/Govee, Rekordbox readers, F1 corrections, F2/F4,
  scripted tracks, marker timing, manual controls and blackout keep their current
  authorities exactly (review §16).
- Current labels remain development-only; no pilot response enters `local/labels/`
  or any gold store; no AI output is ever called gold.
- Secrets, local IPs, device IDs, machine paths, and live config stay out of
  tracked files.

---

## Part D — Test matrix (pure/offline; review §21 Phase-0 tests)

1. **Schema rejection:** every schema in B7 rejects missing fields, unknown fields,
   wrong enums, nonfinite floats.
2. **Deterministic manifest:** synthetic locator fixtures → two builds are
   byte-identical; `manifest_id` reproduces; every related group in one split;
   unique IDs.
3. **Lineage disjointness:** adversarial fixtures with duplicate `audio_sha256`,
   remix titles, near-duration/BPM pairs → correct pair emission, exclusion of
   `unresolved`, hard FAIL on post-selection discovery.
4. **Feature firewall (adversarial leakage):** constructing `FrozenFeatureRow` with
   a title/path/label key raises; a candidate fed a row carrying any forbidden
   field raises; predictions built after a response exists ⇒ gate-1 FAIL.
5. **Candidate determinism:** tie fixtures → deterministic tie-break; permuted
   input order → identical `PredictionRow` hashes; zero-MAD field dropped and
   hashed; OOD threshold honored with `method="linear"`.
6. **Abstention:** missing/corrupt/short v4 fixtures → named abstention; <3
   eligible lineages → abstain; vote tie → abstain.
7. **Denominator reconciliation:** every fixture row lands in exactly one of the
   four states; counts reconcile per method and axis; an unreconciled row fails.
8. **Repeat placement:** frozen repeat selection is non-adjacent, 2/session marker
   repeats, 1/1/2 family repeats; contradiction counters match §B8 definitions.
9. **Verdict truth table:** every gate combination in B8 → exact
   PASS/FAIL/INCONCLUSIVE; a hidden axis failure can never yield PASS.
10. **Session recovery:** simulated interrupt mid-session → resume at first
    unanswered card, zero extra decisions, active-time segments sum correctly;
    tampered `responses.jsonl` hash chain → hard FAIL.
11. **Workspace fence + byte identity:** attempted write outside the namespace
    raises; pre/post listing hashes equal on a clean run.
12. **No-runtime-importer AST guard** for `tools/spectral_pilot/`.
13. **Deterministic replay:** a full synthetic end-to-end run twice → byte-identical
    canonical predictions, metrics, verdict inputs.

All tests run on synthetic fixtures only — no live library, cache, label, audio, or
Rekordbox access.

---

## Part E — Acceptance and pre-handoff checklist

Implementation (when separately authorized) is done only when:

- [ ] Every Part B module exists with the exact interfaces above; Part D tests pass.
- [ ] The four AGENTS.md §8 checks pass; bookkeeping rows updated per the `docs`
      contract in `docs/agents/change_contracts.yml` (cite the key, not a line —
      the file moves).
- [ ] No file outside the B0 fence changed (diff-stat proof against the fence).
- [ ] Status language: `planned` → `software-tested offline tooling`; never
      `validated`; the pilot itself stays unexecuted until its own authorization.
- [ ] The implementing seat reports evidence; the manager adversarially reviews;
      Brandon gates Phase-1 execution separately (org doc §3).

**Unresolved items, classified (kickoff deliverable 12):**

| Item | Class |
| --- | --- |
| Session-A ear-check of the seven fixed anchors (confirm/reject; axis stops on rejection) | operator taste — roles, vocabulary, and anchor identities were decided 2026-07-15 (B3.7); only the in-protocol clip listen remains |
| Actual analysis wall time / RSS on the real 60-row pool | unavailable measurement until Phase-1 runs; ceilings are frozen either way |
| Whether ≥18 lineages survive eligibility; repeatability floors; availability floors | experiment-dependent — the pilot exists to measure them |
| Canonical JSON details, ID formats, module layout, recovery mechanics, anchor-candidate ordering | ordinary engineering — resolved in this spec (B1–B7) |

No unresolved ordinary-engineering choice remains ambiguous (the review's Phase-0
kill gate is therefore not tripped by this spec).

---

## §13. SOL4 concept trace (non-authorizing; kickoff deliverable 13)

**`operator-decided`** input; **`proposed`** trace. One row per concept: required
acoustic/decision axes → do the named driving signals exist at `882d8c7`
(grep/read-level) → earliest possible later phase for the *prerequisite axis* →
remaining gate. "Program phases" qualify measurement axes only; building any cue is
separate lighting-engine work needing its own spec, operator visual approval, and
any room/hardware gate. Nothing here authorizes, designs, or schedules a cue.
`P2:x` marks a named not-yet-existing extraction field (absent at HEAD,
grep-verified). Axis keys: FAM (family), HRD (intrinsic hardness/tier), GEN
(genuine-marker state), GRW (growl span/motion), SUS (sustain envelope), BLD
(build shape), DEC (post-drop decay), TEX (texture/pattern motif).

| # | Concept | Axes | Signals at HEAD | Earliest phase | Remaining gate |
| --- | --- | --- | --- | --- | --- |
| 1 | Pressure Door | FAM, HRD | yes | Phase 1 (FAM/HRD axes) | operator visual + room |
| 2 | Sawtooth Barrage | FAM, HRD | yes | Phase 1 | operator visual + room |
| 3 | Sustained Siege | FAM, HRD (sustained) | yes | Phase 1 | hardness-axis PASS + operator visual |
| 4 | Black-Iron Cathedral | FAM, HRD, GRW | yes | Phase 1 (FAM/HRD); GRW later protocol | growl-span truth protocol + operator visual |
| 5 | Needle Rain | FAM | yes | outside program (config-only cue) | operator visual |
| 6 | Twin Rail Launch | FAM, SUS | yes | Phase 1 (FAM) | operator visual + room |
| 7 | Supernova Relay | FAM, HRD | yes | Phase 1 | operator visual + room |
| 8 | Shrapnel Wake | FAM, HRD | yes | Phase 1 | operator visual + room |
| 9 | Kickback Halo | FAM, TEX (kick) | yes | Phase 1 (FAM) | operator visual |
| 10 | Stab & Glide | FAM, TEX (stab/sustain) | yes | Phase 1 (FAM) | texture-span truth protocol + operator visual |
| 11 | Growl Conveyor | FAM, GRW | yes | Phase 1 (FAM); GRW later protocol | growl-span truth + operator visual |
| 12 | Velvet Spark Ceiling | FAM, HRD | yes | Phase 1 | operator visual |
| 13 | Silk Current | FAM, SUS | yes | Phase 1 (FAM) | operator visual |
| 14 | Glass Ribbon | FAM, SUS | yes | Phase 1 (FAM) | operator visual |
| 15 | Breath Bloom | FAM, SUS | yes | Phase 1 (FAM) | operator visual |
| 16 | Rattle Thread | TEX (motif) | **P2:midhigh_onset_periodicity / midhigh_pattern_signature absent** | after a separately authorized extraction change | new field + operator visual |
| 17 | Honest Fuse | BLD | yes | later build-shape protocol (not Phase 0/1) | build-shape truth + operator visual |
| 18 | Pressure Staircase | BLD | yes | later build-shape protocol | build-shape truth + operator visual |
| 19 | Sustain Veil | SUS | yes | later sustain protocol | operator visual |
| 20 | Airglass Constellation | SUS | yes | later sustain protocol | operator visual |
| 21 | Impact Afterimage | DEC | yes | later decay protocol | operator visual |
| 22 | Growl Ghost | GRW, DEC | yes | growl/decay protocols | growl-span truth + operator visual |
| 23 | Warehouse Jaw | FAM, HRD, GRW | yes | Phase 1 (FAM/HRD); GRW later | growl truth + laser policy + room |
| 24 | Pocket Piston | FAM, TEX | yes (fields; signature unlabeled) | Phase 1 (FAM); signature needs labels | texture labels + operator visual |
| 25 | Head-Rip Furnace | FAM, HRD (sustained) | yes | Phase 1 | hardness PASS + laser policy + room |
| 26 | Trap Fracture | FAM, TEX (motif) | fields yes; motif signature absent | after texture-motif evidence | more labels + operator visual |
| 27 | Euphoric Canopy | FAM, SUS | yes (source-agnostic; **P2:synth_presence absent** for literal synth-only) | Phase 1 (FAM); SUS later | sustain truth + laser policy + room |
| 28 | Festival Horizon | FAM, BLD | yes (boundary unlabeled) | later build-shape protocol | more labels + operator visual |
| 29 | Synth-Sustain Skyrail | SUS (laser) | yes as harmonic-sustain proxy; **P2:synth_presence absent** | later sustain protocol | sustain truth + laser policy + room |
| 30 | Growl Jaw | GRW (laser) | yes | growl protocol after Phase 1 | growl truth + laser policy + room |
| 31 | Roll Charge / Vacuum | BLD (laser) | yes | later build-shape protocol | build truth + laser policy + room |
| 32 | Comet Needlework | FAM (laser) | yes | Phase 1 (FAM) | laser policy + room |
| 33 | Wall Lattice | FAM, HRD (laser) | yes | Phase 1 | hardness PASS + laser policy + room |
| 34 | Afterburn Ease | DEC (laser) | yes | later decay protocol | laser policy + room |
| 35 | Switchblade Fill | TEX (motif, laser) | **P2:midhigh_pattern_change_score / snare_pattern_signature absent** | after a separately authorized extraction change | new field + laser policy + room |

The catalog's ranked top 10 (concepts 30, 29, 3, 12, 17, 7, 21, 9, 5, 33) is
preserved as creative priority only; ranking confers no authorization. Phase 0/1
tests only FAM/HRD/GEN prerequisites; no visual concept is implemented, scored, or
promoted by any Phase-0/1 outcome.
