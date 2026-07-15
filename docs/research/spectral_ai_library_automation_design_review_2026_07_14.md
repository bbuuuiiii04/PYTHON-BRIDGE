---
doc_status: current
truth_level: code-verified adversarial design review with measured local development evidence and current primary-source external research
last_verified_commit: 790c625
last_verified_date: 2026-07-14
validation_scope: >
  Documentation-only review of the current spectral-v4 extractor, cache, derived
  profiles, deterministic decision candidates, AWR-200/AWR-205 benchmark tooling,
  F1/F2/F4 consumers, lighting authorities, portable sidecar, and the tracked
  33-track HTDemucs pilot. Current gitignored gold was scored read-only at this
  HEAD; external candidate facts were checked against primary sources on
  2026-07-14; the operator-supplied SOL4 creative catalog was read as historical
  product-direction evidence. No runtime code, config, cache, label, audio, Rekordbox data,
  generated evidence, bridge process, output, or hardware was changed or contacted.
  Design only; implementation and execution are not authorized.
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Offline library-to-lighting automation — hardened design review

## Evidence language

Every load-bearing statement in this review carries one of these labels:

- **`confirmed-repo`** — verified in current executable code, tests, tracked config,
  or current repository contracts at `790c625`.
- **`confirmed-external`** — verified against a primary external source, linked near
  the claim and checked on 2026-07-14.
- **`measured`** — produced by a named local artifact or experiment. It is not
  automatically generalizable.
- **`operator-decided`** — Brandon must decide, or has already decided, a matter of
  taste or acceptable effort.
- **`inferred`** — a reasoned conclusion not established by current evidence.
- **`proposed`** — a design rule or future experiment, not implemented architecture.
- **`unknown`** — evidence is absent or insufficient.
- **`live-gated`** — cannot be promoted without a separate attended live or hardware
  gate.

A labeled paragraph or table row applies that class to its directly attached list or
schema until the next labeled statement. A bold “Default class for this section” or
“Default class for this subsection” declaration applies to every otherwise-unlabeled
statement, list and schema until the next equal-or-higher-level heading; a closer label
overrides it. Table headers may assign a class to an entire column. No classification
silently carries across such a heading.

**`proposed`** Terms used below have one meaning. A **profile** is an immutable offline evidence blob;
an **eligible field** is one exact field allowed by its approval/qualification scope; a
**compiled plan** is the separate existing-owner-shaped in-memory object. **Frozen**
means byte-immutable and hash-addressed. **Active** means selected by one atomic manifest
generation. **Approved** means only the exact shown field/moment was accepted.
**Corrected** means an operator value is locally locked. **Stale** means a named identity,
schema, policy or provenance check failed. **Rollback** selects an earlier immutable
generation. **Fail open** means ignore only the proposed overlay and retain current HEAD
behavior.

**`proposed`** `AVAILABLE`, model agreement, a development-set win, and an AI-generated prediction
are never synonyms for truth, qualification, approval, or gold.

## 1. Executive verdict

**`proposed` — LIMITED PILOT ONLY.**

**`confirmed-repo`** The repository already has a substantial deterministic spectral
measurement layer, an implemented but weakly validated decision layer, two simpler
offline candidate surfaces (`hardness_v0.py` and `approach_features_v0.py`), and a
read-only benchmark harness. It has no music embedding pipeline, clustering system,
active-learning service, learned profile generator, or learned-profile runtime
consumer.

**`inferred`** There is not yet enough independent Brandon-authored evidence to endorse
an AI architecture. The original “pursue with major safeguards” verdict was too broad:
an 18-lineage family or hardness result could not validate darkness, texture timing,
growl semantics, lasers, motion, color, confidence, full-library generalization, or a
runtime profile contract.

**`proposed`** The only defensible next experiment is a small, prediction-hidden,
lineage-aware pilot that first tests whether Brandon's target judgments are repeatable
and whether existing deterministic evidence can materially beat current F2 while
fitting a strict human-time budget. It uses no external model and no stems. A single
external embedding may be considered only in a later, separately authorized pilot if
the deterministic pilot passes and exposes a named residual.

**`proposed`** This document does **not** authorize:

- an embedding, model, or stem install or run;
- a full-library scan, model sweep, separation sweep, clustering pass, or provisional
  profile generation;
- an active-learning or confidence service;
- a review UI, sidecar extension, F1/F2/F4 change, runtime consumer, live config edit,
  restart, toggle, or hardware check;
- calling any provisional output gold, approved, qualified, or safe.

**`operator-decided`** On 2026-07-14 Brandon answered yes to both pre-pilot
questions: the current F2 plus failure-correction burden justifies a bounded experiment,
and the four-session ceiling of 65 active minutes / 113 atomic decisions is acceptable.
He also assigned Fable 5 as the executive orchestrator and project manager for this
spectral automation product. All product work is to run in separate Claude CLI tmux
sessions managed by Fable; Fable must never use its Agent tool or spawn internal
subagents. This closes the gate to **author a Phase-0 specification only**. It does not
authorize Phase-0 implementation, pilot execution, model or stem work, a library sweep,
or any live/runtime action.

## 2. Current-state truth

### 2.1 Implemented measurement and consumer surfaces

| Class | Current fact | Evidence and limit |
| --- | --- | --- |
| `confirmed-repo` | Spectral v4 stores absolute-dB full/sub/bass/mid/high/air/growl series, harmonic/percussive measures, attacks, onset density, centroid and growl-centroid data, quarter-beat maps, and scalars. | `audio_spectral_features.py::SpectralFeaturesV4`; extraction is deterministic for fixed input/code but not independently proven sufficient for Brandon's judgments. |
| `confirmed-repo` | The strict v4 cache identity includes resolved path, file mtime, file size, and exact beatgrid fingerprint. | `spectral_cache.py::_cache_key`, lines 337-352 at reviewed HEAD. File moves or re-encodes change the key; stale raw JSON counts are not coverage. |
| `confirmed-repo` | `spectral_profile.py` derives explainable views including identity axes, bottom-gone, rolls, stabs, sustained bass/synth, growl, low-mid pulse, sections, and a 16-beat drop-window vector. | These are measurements and heuristics, not operator truth. |
| `confirmed-repo` | F1 derives track color identity and freezes measured records in a content-ID-or-path-keyed `IdentityStore`; Brandon's zone correction is preserved. | `led_identity_v2.py::content_key`, `IdentityStore`; `state_manager.py::_handle_led_track_identity` and zone-correction handlers. A learned profile must not become a second F1 authority. |
| `confirmed-repo` | F2 builds one `DropDecision` per supplied marker with family, tier, darkness, violence, and bass-forward fields on the analysis worker. | `lighting_moments_v2.py::decide_drop` / `build_track_plan`; `state_manager.py::_read_runtime_anlz_data`. It has no genuine-drop classifier, calibrated confidence, growl span, or independent laser-suitability field. |
| `confirmed-repo` | F2 influences LED look narrowing, shared pre-drop darkness, laser tier/presentation inputs, and pre-chorus behavior; it is not LED-only. | `led_dispatch_policy.py::_led_f2_drop_look_names`; `state_manager.py::_f2_laser_tiers`, `_f2_transition_window_beats`, `_f2_transition_release_beats`, `_f2_pre_chorus_beats`; `drop_presentation.py`. |
| `confirmed-repo` | F4 consumes the F2 plan to season parameters and preferences. It does not own scheduling, family, tier, routing, or darkness. | `led_dispatch_policy.py::_led_inject_f4_seasoning` and adjacent helpers. F4-off, F2-off, and scripted paths stand down. |
| `confirmed-repo` | Current analysis and F2 planning are off the 200 Hz push loop; consumers perform bounded in-memory lookups. | `state_manager.py::_read_runtime_anlz_data` and current F2/F4 consumer helpers. |
| `confirmed-repo` | The portable sidecar freezes ANLZ copies, a beatgrid fingerprint, locator metadata, SoundSwitch ID, laser tag beats, and optional v4 payload. | `tools/lighting_sidecar_export.py::_export_track`; `filepath_resolver.py` schema-v1 consumer. It has no audio digest, recording lineage, marker-set fingerprint, or learned profile. |
| `confirmed-repo` | Sidecar fallback may match by title, artist, duration, and BPM after exact-grid matching fails. | `filepath_resolver.py::_select_sidecar_record`. That relaxed locator is acceptable for today's source recovery but is not a safe learned-profile identity contract. |
| `confirmed-repo` | `hardness_v0.py` is an implemented, deterministic, offline-only, in-sample binary-T3 candidate with zero runtime importers. | It has no T1/T2 boundary and is not validated authority. |
| `confirmed-repo` | `approach_features_v0.py` is an implemented, deterministic, offline-only raw approach descriptor. | It produces no class, threshold, darkness length, or runtime decision. |

### 2.2 What is implemented, designed, and validated

**`confirmed-repo`** Implemented and software-tested today: v4 extraction/cache/derived
views, current F1/F2/F4 behavior, the identity correction store, current portable
sidecar, the AWR-200/AWR-205 harness, `hardness_v0`, and raw approach descriptors.

**`confirmed-repo`** Designed or proposed only: curated cross-content lineage identity,
deterministic nearest-neighbour retrieval, external embeddings, candidate agreement,
calibrated per-field confidence, active learning, a learned frozen profile, learned
profile export, and learned profile runtime consumption.

**`confirmed-repo`** The current validation matrix classifies F1/F2/F4 and related
lighting behavior as software-tested and room/hardware-unvalidated. No tracked evidence
qualifies the proposed AI system, learned decisions, or learned runtime profile.

**`unknown`** Other live-session records may show particular current lighting paths
operating in Brandon's local setup, but this review found no controlled live comparison
of current spectral decisions against independent truth. Such observations cannot be
reused as AI accuracy or room-acceptance evidence.

### 2.3 Current benchmark evidence and the bottleneck

**`measured`** A read-only run at `a6ff90a` used
`local/labels/operator_track_labels_2026_07_09.jsonl` (label SHA prefix
`a584dcb1e0293b24`) and `local/labels/gold_drop_labels_2026_07_11.json` (gold SHA
prefix `f47507866f936ff4`). The gitignored gold header records `head: unknown`, so these
are local development artifacts, not a tracked HEAD property.

The run reproduced:

- 21 usable lineages and 158 current candidate markers;
- 82/158 markers with a genuine/non-genuine answer;
- 26 genuine drops with complete tier/family fields;
- tier: 12/26 exact, ordered MSE 1.231, five missed T3 and six false T3;
- family: 7/26 exact, 26.9%;
- marker shift at plus/minus two beats: family 23.4%, tier 39.2%, darkness 51.3%;
- darkness, growl, laser, and genuine-drop classification still `UNAVAILABLE` for
  like-for-like scoring.

**`confirmed-repo`** The current harness's positive allowlist protects calls to today's
`build_track_plan`; it does not automatically protect a future retrieval or embedding
candidate. Its `_lineage_key` also does not merge remix/edit siblings with different
content IDs. Both gaps must fail closed before comparison.

**`inferred`** The measurements may contain useful signal, but the current results do
not isolate v4 representation quality from decision-rule quality. “V4 is useful” is a
hypothesis for the pilot, not a proven conclusion.

**`measured`** The abandoned comprehensive session asked for 158 marker judgments. The
current local file contains only 82 genuine-state answers and 26 fully scored genuine
drops. This is direct evidence that exhaustive desk labeling is not a sustainable
default workflow.

### 2.4 Stem evidence, stated honestly

**`measured`** The tracked 33-track HTDemucs pilot completed 33/33, measured 1.52 GB
peak RSS, 134.7 seconds median per track, a historical projection of about 27 hours for
716 tracks, and 0.04 dB median re-sum difference.

**`measured`** Its frozen decision scorecard failed. Rolls, screeches, 808s, distorted
kicks, and one sidechain example showed source-separation proxy advantages; they did not
show held-out improvement in a lighting decision. The 0.04 dB result shows that stems
recombine near the mix, not that each source is semantically correct.

**`confirmed-repo`** `tools/stems_pilot.py` called Demucs `apply_model` without a
`shifts` argument. **`confirmed-external`** Demucs defaults that argument to one random
shift. The retained envelopes therefore are not a deterministic qualification artifact.

### 2.5 SOL4 creative catalog provenance and role

**`operator-decided`** Brandon supplied `SOL4_creative_catalog.txt` as creative product
input and requires Fable to preserve it through the program. The exact local artifact
read on 2026-07-14 has SHA-256
`ac3fdc9d4d8eb4d99735667ec52031143ddd94f662e3fa7264b213ee8c0c74f2`.

**`measured`** The 789-line capture contains 35 numbered LED/laser concepts and a ranked
top 10. Its source session measured raw v4 cache JSON at an older moving HEAD and reported
1,306 files / 678,110 beat rows. Those historical raw-file counts are not current-library
coverage: the strict cache can retain duplicate/stale identities, and current claims must
resolve the current library path plus beatgrid fingerprint.

**`proposed`** Concepts such as Growl Jaw, Synth-Sustain Skyrail, Sustained Siege,
Velvet Spark Ceiling and Honest Fuse are a creative backlog, not accepted architecture,
operator gold, or proof that their signal mappings work. The catalog itself distinguishes
measured-groundable proposals from speculative proposals, but even the former still need
current-code verification, independent axis qualification, Brandon's visual judgment,
and any applicable room/hardware gate.

**`proposed`** Phase 0 may test whether prerequisite family/hardness measurements are
reliable; it must not implement or score these visual concepts. Fable's Phase-0 spec must
carry a non-authorizing trace from all 35 concepts to their required measurement/decision
axes and earliest possible later phase, so the creative intent is neither lost nor
silently promoted.

## 3. Problem decomposition

One “AI label” cannot truthfully solve all of these jobs:

| Class | Problem | Machine can establish | Human or live truth still required |
| --- | --- | --- | --- |
| `confirmed-repo` | Acoustic description | dB bands, attacks, harmonic/percussive ratios, centroid, onset and change measurements | Semantic checks when a proxy is claimed to mean growl, vocal, screech, or another musical element |
| `operator-decided` | Structural interpretation | Candidate-marker-local evidence and repeated-section similarity | Genuine drop vs buildup/false marker; marker-wrong/ambiguous is a separate answer |
| `operator-decided` | Lighting-family selection | Similarity to frozen examples may organize choices | WALL/COMET/HOUSE/mixed/none and whether track-level family is useful at all |
| `operator-decided` | Intensity judgment | Continuous body, abrasion, growl duty, onset and arrival measurements | Pairwise intrinsic hardness and the policy mapping it to T1/T2/T3 |
| `operator-decided` | Blackout timing | Approach-floor shape, return, gap, and pickup evidence | Whether darkness is wanted, its approved shape, start, end, and room feel |
| `operator-decided` | Texture-span detection | Frame/beat candidates for aggressive texture | Whether the candidate is musically a growl/screech/texture and its perceptual boundaries |
| `operator-decided` | Growl characterization | Growl-band pressure, flatness and centroid movement | Semantic kind, musical importance, and desired visual response |
| `operator-decided` | Laser musical opportunity | Aggression, space, density and anchor similarity may propose | Whether Brandon wants lasers for that moment |
| `live-gated` | Laser physical safety/acceptance | Audio establishes nothing about fixture geometry, power, occupancy, haze, or scan safety | Existing laser policy, operator, room, and hardware gates only |
| `operator-decided` | Color identity | Current F1 computes a deterministic color zone and dressing | Brandon's color identity and correction; outside this pilot |
| `operator-decided` | Motion character | Acoustic envelope can propose an anchor | Visual/musical preference |
| `live-gated` | Room-specific acceptance | Offline simulation may expose obvious errors | Attended visual acceptance on the actual room and hardware |

## 4. Baseline assumption ledger

| Class | Central assumption | Current ruling | Collapse consequence |
| --- | --- | --- | --- |
| `inferred` | V4 is a useful backbone. | Retain as the cheapest measured representation; sufficiency is unknown. | If deterministic candidates cannot beat current F2, stop rather than add models. |
| `unknown` | Brandon can repeat the target judgments. | Test before comparing methods. | An unstable axis becomes pairwise-only, manual-only, simplified, or rejected. |
| `unknown` | One family across two shown moments is useful. | Test exact two-moment `mixed/none/unsure` rate; whole-track stability remains untested. | Common mixed answers kill even the limited family abstraction; no result establishes a track-wide family. |
| `unknown` | Exact retrieval can reduce corrections. | Pilot only after its vector and lineage rules are frozen. | No gain means retain named deterministic rules and local corrections. |
| `inferred` | A style embedding might add track-family signal. | Deferred; no evidence for drop validity, hardness, spans, or taste. | Failure of a later family-only test rejects the dependency. |
| `measured` | Stems expose some source proxies. | True on a development pilot; downstream value unqualified. | No new separation until a named residual and held-out gate exist. |
| `confirmed-repo` | Current runtime can remain deterministic/model-free. | Required invariant. | Any design needing live model/vector/stem work is rejected. |
| `unknown` | Automation saves more time than failure-driven corrections. | Must be measured, not assumed. | If normal practice corrections fit Brandon's budget, kill the platform. |
| `proposed` | A frozen profile could use existing off-loop seams. | Future schema sketch only; not accepted architecture. | Pilot failure retires the profile proposal without runtime sunk cost. |

## 5. Recommended architecture and stage contracts

**`proposed`** The north-star boundary is retained only to show where information may
flow. It is not an implementation roadmap:

```text
audio + frozen Rekordbox structure
        -> identity/lineage manifest
        -> existing v4 measurements
        -> deterministic candidate judgments
        -> correlated-evidence/disagreement report
        -> limited prediction-hidden human review
        -> lineage-aware benchmark
        -> (future only) immutable field-scoped eligible profile
        -> (future only) deterministic in-memory runtime plan
```

| Ruling | Stage | Input -> output | Schema/provenance/version/invalidation | Owner and error behavior |
| --- | --- | --- | --- | --- |
| `required` / `proposed` | Identity and lineage freeze | Current library rows, audio identity, beatgrid and marker set -> immutable manifest | Manifest schema in §9; hash all identity/split material; any audio/grid/marker/split change creates a new manifest | Offline pilot tool; unresolved duplicate/lineage means exclude, never guess |
| `required` / `confirmed-repo` | V4 feature read | Exact manifest rows -> frozen feature rows | Record extractor schema, cache payload hash and field schema; never enumerate raw cache JSON as library truth | Offline reader; missing/corrupt/short/nonfinite -> named abstention or prespecified exclusion |
| `required` / `proposed` | Deterministic candidates | Frozen feature rows + development anchors -> `PredictionRow` | Candidate name/version, positive input allowlist, scaling population hash, neighbours, distances, reasons and output hash | Pure offline predictor; zero eligible neighbours or ties -> abstain |
| `required` / `proposed` | Agreement/disagreement | Candidate rows -> per-axis comparison and review priority | Group candidates by evidence family; agreement is a raw diagnostic, never confidence | Offline report; missing axes remain unavailable and visible |
| `required` / `operator-decided` | Human review | Opaque audio cards -> immutable response rows | Prediction-hidden card/version/session hashes; store recognition, uncertainty, time and repeat identity | Brandon; `unsure`, marker-wrong, fatigue, and skip are valid outcomes |
| `required` / `proposed` | Benchmark | Frozen predictions + responses + manifest -> machine report | Lineage-macro metrics, raw counts, abstentions, exact hashes and verdict function | Offline scorer; any row loss, leak, overlap or post-label prediction is hard FAIL |
| `optional` / `proposed` | One external embedding | Named residual + separately frozen pilot -> pooled vectors | Exact artifact/code/preprocess/environment hashes and same-machine repeat gate | Disposable offline environment only; no bridge dependency; deferred after deterministic PASS |
| `deferred` / `proposed` | Stems | Named residual and held-out field corpus -> source-specific descriptors | Exact model signature, weights hash, `shifts=0` or frozen seed, environment and resource manifest | Disposable offline environment; never a full sweep before a field-specific PASS |
| `rejected now` / `proposed` | Active-learning/confidence platform | — | Too little independent truth; raw disagreement only | Do not build |
| `future` / `proposed` | Frozen profile | Qualified/approved field rows -> immutable profile version | Boundary sketch in §15; identity, history, overrides, confidence and stale reasons | Offline compiler; provisional or invalid envelope never activates live |
| `future` / `proposed` | Runtime compile/load | Valid active profile -> existing in-memory plan seams | Exact schema/audio/grid/marker match; atomic publish; old version retained | Existing off-loop worker; invalid overlay falls back to current behavior; no push-loop I/O |

**`proposed`** All pilot inputs must end in exactly one state: `predicted`,
`abstained_with_reason`, `excluded_with_prespecified_reason`, or `hard_failure`. Counts
must reconcile to the frozen manifest.

## 6. Deterministic candidate contracts

### 6.1 Baselines that must precede any external model

**`confirmed-repo`** `current_f2_790c625` is the live-software baseline. It emits
family/tier/darkness at existing markers and abstains for genuine-drop classification,
growl spans, and laser suitability.

**`proposed`** `hardness_v0_all_markers_v1` is diagnostic only. It runs the frozen
`hardness_v0` candidate at every selected marker and emits continuous `H`, binary
T3-path fire, winning path, marker-shift range, or abstention. Its binary output cannot
answer general T1/T2/T3 pairwise questions, does not enter the primary hardness PASS,
and never becomes live authority.

**`proposed`** `approach_v0_diagnostic_v1` emits raw approach/landing descriptors and
plus/minus-two-beat ranges. It makes no genuine/drop/darkness prediction and is scored
only for availability/stability diagnostics.

**`proposed`** `v4_exact_retrieval_v1` uses no learned model:

- marker window: `spectral_profile.drop_window_vector(..., width=16)`;
- positive feature allowlist, in this exact order: `sub_db`, `bass_db`, `mid_db`,
  `high_db`, `air_db`, `full_db`, `low_swing_db`, `attack_low_p90`, `perc_low`,
  `harm_ratio`, `centroid_hz`, `growl_flatness`, `sustain_mid_db_d8`,
  `sustain_high_db_d8`, `onset_density_mh`, `fluxsum_mh`, `pre_gap_beats`;
- `coverage < 16`, a missing key, or a nonfinite value -> abstain;
- each axis consumes one exact `development_training_manifest` listing permitted row
  IDs, target fields, exclusions, anchors, scaler population and its hash; an incomplete
  development row is eligible only for a target it actually contains;
- each field is centered by that axis's frozen median and scaled by its frozen median
  absolute deviation; zero-MAD fields are dropped and the retained-field list is hashed;
- Euclidean distance; first retain only the nearest eligible row from each unrelated
  lineage, then take `k=3` lineages; the query's `recording_lineage_id` and
  `audio_duplicate_group` are excluded;
- fewer than three eligible lineages or zero retained fields -> abstain;
- label vote or ordinal median; a tie abstains;
- deterministic tie-break for equal distances: frozen `track_instance_id`, then marker
  beat;
- OOD when nearest distance exceeds the frozen leave-one-lineage-out nearest-distance
  95th percentile using the pinned NumPy `method="linear"`; OOD abstains;
- family retrieval pools median and interquartile range over exactly the two marker rows
  in that lineage's frozen family montage; its development target uses the matching
  two-row development montage and never a human-selected genuine-only subset.

The candidate interface is:

```text
predict(method_version, frozen_feature_row, eligible_development_rows)
    -> PredictionRow
```

Each `PredictionRow` must record method/version, manifest/input/scaler hashes, eligible
and excluded neighbour IDs, distances, per-axis value or abstention, raw score, reason
codes, and error state. Only canonical decision fields enter its hash. Variable wall
time, RSS and host telemetry live in `resource_report.json`, never in prediction rows or
verdict inputs. Predictions are immutable and hashed before Brandon sees a card.

**`proposed`** For marker hardness, the 36 selected rows are sorted by
`SHA256(pilot_seed || audio_sha256 || marker_beat || "hardness-anchor")`; anchors T1,
T2 and T3 are assigned round-robin, exactly 12 rows each. Pair side uses a separate
frozen hash bit. Each primary method predicts the exact displayed pair: current F2
compares the marker's frozen tier with the anchor's operator-confirmed tier; retrieval
compares its ordinal T1/T2/T3 prediction with the anchor's operator-confirmed tier;
exact equality means `tied`. Missing tier means abstain. `hardness_v0` stays diagnostic
because it has no valid three-tier mapping.

The card stores `display_left_id`, `display_right_id`, the displayed response, and a
canonical `marker_vs_anchor = harder|tied|softer|unsure`. Pair-side answers are converted
to marker-relative orientation before the immutable response hash is computed.

**`proposed`** For the exact two-moment family target, both human and methods use the
same two manifest marker rows. Human truth asks about **those shown moments**, not an
entire track. Current F2 maps `NEUTRAL` to `none`, abstains if either plan row is missing,
returns the common family when both match, and returns `mixed` when they differ.
Retrieval emits the same vocabulary from its matching two-row development targets.
`unsure` is unavailable truth. Even a family PASS does not establish a stable family for
unheard moments or authorize a track-wide profile default.

**`proposed`** No combined v4-plus-embedding vector is allowed in the first external
pilot. A later embedding must first compete as its own view against the frozen v4
retrieval. Concatenation would introduce an unearned weighting/search space.

### 6.2 Simplest-alternative ladder

| Class | Alternative | Current use and kill rule |
| --- | --- | --- |
| `confirmed-repo` | Current F2 plus local manual corrections | Always remains the live baseline. A pilot PASS does not prove that broader automation saves more work. |
| `proposed` | Failure-driven corrections during normal practice | Preferred no-project comparator for later workload measurement. If its correction burden fits Brandon's budget, stop the automation program. |
| `proposed` | Frozen deterministic rules | First pilot candidates; failure blocks embeddings, stems, learned profiles and runtime work. |
| `proposed` | Exact nearest-neighbour retrieval | First pilot similarity method; no learned model and no cluster infrastructure. |
| `proposed` | Representative-cluster review or cluster defaults | Deferred. A reviewed representative creates an anchor only. Do not propagate approval to a cluster until a later lineage-held-out experiment proves the default and review savings. |
| `proposed` | One supervised or pretrained representation | Deferred. Only after a deterministic PASS leaves one named residual; it must beat the frozen simpler comparator. |
| `proposed` | AI-generated labels, stems, active learning, or a full profile platform | Rejected now. They add cost or apparent certainty before independent truth establishes a need. |

## 7. Judge independence

| Evidence class | Judge/evidence | Independence class | Independence ruling | Treatment class | Confidence treatment |
| --- | --- | --- | --- | --- | --- |
| `confirmed-repo` | Current F2 rules | `confirmed-repo` | V4-derived and marker-dependent | `proposed` | Same `v4_full_mix` evidence family |
| `confirmed-repo` | `hardness_v0` and approach descriptors | `confirmed-repo` | V4-derived, often using the same marker windows | `proposed` | Same `v4_full_mix` family; no extra vote |
| `proposed` | V4 exact retrieval | `proposed` | Uses the same v4 measurements plus human development anchors | `proposed` | Same family; comparison, not independent corroboration |
| `confirmed-external` | Discogs-EffNet | `inferred` | A different training objective still shares waveform, windowing, mastering and marker-error exposure | `proposed` | Separate feature view, not an independent truth judge |
| `confirmed-external` | MERT/MAEST/other embeddings | `inferred` | Different weights/objectives may share corpora and acoustic bias | `proposed` | Never count model number as evidence number |
| `measured` | Full-mix plus stems | `inferred` | Stems derive from the same waveform and marker; separator artifacts add another shared failure | `proposed` | Source view only; no correctness vote |
| `operator-decided` | Prediction-hidden Brandon response | `inferred` | Independent of model output if frozen first; familiar-track recognition remains a limitation | `proposed` | Only correctness source for perceptual/taste fields |
| `live-gated` | Room/hardware acceptance | `inferred` | Independent of desk audio accuracy | `live-gated` | Required for visual/laser/room claims; never inferred from acoustic scores |

**`proposed`** Correlated judges may trigger review when they disagree. Their agreement
cannot raise calibrated confidence directly. Confidence comes only from the composite
field decision's observed error on independent calibration lineages.

## 8. Human-truth boundary and sustainable workload

### 8.1 Minimum anchors and lineage diversity

**Default class for this subsection: `proposed`.**

**`proposed`** Freeze exactly seven operator-confirmed development clips from seven
unrelated recording lineages:

- one current WALL, COMET, and HOUSE family reference;
- one T1, T2, and T3 intrinsic-hardness reference;
- one operator-confirmed `mixed` family example.

The same clip may not fill two slots. Anchors use neutral IDs, are versioned, never enter
calibration/test, and cost seven explicit confirmations. If Brandon rejects the current
vocabulary or cannot decisively confirm the `mixed` anchor, the family axis stops before
the pilot.

**`proposed`** The challenge pilot requires 18 distinct `recording_lineage_id` values
and 18 distinct audio-duplicate groups. It makes no representative-library or style-
coverage claim. Genre/style/artist/release diversity is reported after selection, never
used to adjust the sample. Metadata is permitted for sampling audit only and never enters
a predictor.

### 8.2 Questions and blinding

**Default class for this subsection: `proposed`.**

**`proposed`** This is **prediction-hidden**, not listener-blind. Brandon may recognize his music; the
response records that recognition instead of pretending otherwise. Before an answer is
saved, hide title, artist, playlist, cover art, content ID, old notes, prior labels,
predictions, method, explanation, confidence, and neighbour identity.

**`proposed`** Per marker, ask at most:

1. `genuine | not_genuine | marker_wrong_or_ambiguous | unsure`;
2. if genuine: `harder | tied | softer | unsure` against one frozen neutral-ID anchor,
   with pair side randomized.

**`proposed`** Per lineage, once, play the exact two frozen family-montage clips and ask
about those two moments:

`WALL | COMET | HOUSE | mixed | none | unsure`.

**`proposed`** Marker-wrong items are excluded from acoustic accuracy and reported separately. No
Rekordbox marker is edited by this workflow.

### 8.3 Honest workload

**Default class for this subsection: `proposed`.**

**`proposed`** The “36-card” shorthand is retired. The maximum is:

- seven anchor confirmations;
- 36 marker-state calls;
- up to 36 hardness comparisons;
- 18 family calls;
- six repeated marker cards, each carrying up to two repeated answers: up to 12 calls;
- four repeated family montages: four calls;
- **113 atomic decisions maximum**.

Use one anchor session of seven clips/15 minutes and three pilot sessions of six
lineages/roughly 15 minutes. Never run more than one batch per day. The 65-minute timer
starts with first playback and includes all anchor, marker, comparison, montage, repeat,
answer-change and save time; Brandon has no off-clock preparation. Brandon may stop
immediately. Exceeding 65 minutes or 113 decisions is a workload FAIL, not permission to
schedule more sessions.

**`proposed`** Repeat IDs, order and session placement are frozen before any response:
sort cards by `SHA256(pilot_seed || card_id || "repeat")`, choose six marker cards and
four family montages, place them non-adjacently with two marker repeats per pilot session
and family repeats distributed 1/1/2. A direct marker-state contradiction is
`genuine <-> not_genuine`; a direct hardness contradiction is `harder <-> softer`; a
direct family contradiction is any change among two decisive
`WALL|COMET|HOUSE|mixed|none` answers. `tied`, `marker_wrong_or_ambiguous` and `unsure`
transitions are reported but not called direct opposites.

At least four marker-state repeats, three hardness repeats and three family repeats must
be comparable; otherwise the pilot is INCONCLUSIVE. More than one direct contradiction
in the **marker-state counter**, more than one in the separate **hardness counter**, or
any direct contradiction in the **family counter** is a repeatability FAIL. Repeats never add independent sample size.
`Unsure` is valid and never forced into a class.

### 8.4 Later truth, holdout, and drift

**Default class for this subsection: `proposed`.**

**`proposed`** If the pilot passes, later evaluation may freeze 15 independent
calibration lineages and an immutable minimum 30-lineage final test. That size can
falsify or support continued assist-only work; it cannot qualify every field for
automatic acceptance.

**`proposed`** Two rotating anchors reappear in each later six-track session using a
frozen round-robin order. The first seven slots cover all seven anchors; the eighth slot
is anchor one starting the next cycle. Two direct reversals in one full cycle pause that axis and require an
operator decision on a new `taste_policy_version`. Historical results remain attached
to the old version.

**`proposed`** Each later six-track review session reserves two random control slots and at most four
disagreement/OOD/high-impact slots. Practice corrections remain development evidence,
never blind QC.

## 9. Anti-leak benchmark contract

### 9.1 Immutable partitions

| Class | Partition | Allowed use |
| --- | --- | --- |
| `confirmed-repo` | Current AWR-182/AWR-205 labels | Development only |
| `proposed` | 18-lineage challenge pilot | Disposable development/model-selection set; never called holdout |
| `proposed` | 15-lineage calibration set | Fit only the frozen score-to-error mapping and abstention threshold |
| `proposed` | Minimum 30-lineage final test | Open once for a frozen candidate; no rule, anchor, threshold, feature, or method selection |

**`proposed`** If a calibration/test lineage or any related duplicate/edit receives practice feedback,
active-learning input, or model-selection use before opening, quarantine the entire
related group and replace it **before** prediction. If a test result changes anything,
the test is retired into development; the changed system needs a new independently
frozen test. Repeated test replacement is reported as repeated model selection, not a
fresh clean claim.

### 9.2 Manifest schema and exact pilot sampling

**Default class for this subsection: `proposed`.**

**`proposed`** Phase 0 freezes the literal
`pilot_seed = spectral-ai-pilot-v1-790c625-2026-07-14` before any row selection. Every
seed-pool or selected-manifest row must include:

```text
schema_version, pilot_seed, created_from_head, track_instance_id,
content_id_locator, audio_sha256, audio_duplicate_group,
recording_lineage_id, split_role, beatgrid_fingerprint,
marker_set_fingerprint, label_store_hash, exclusion_reason,
lineage_review_state, curator_confirmation, family_montage_marker_ids
```

**`proposed`** `content_id_locator`, title, artist, playlist and path are locator/audit fields, never
predictor fields. `audio_sha256` identifies exact bytes; a re-encode is a different
audio identity even when a human later groups it into the same recording lineage.

**`proposed`** The bounded seed pool is created without decoding or hashing the full
library: read the current PDB locator rows and scripted IDs, remove current development
content IDs and scripted rows, sort the remaining locator IDs by
`SHA256(pilot_seed || content_id_locator)`, and take the first 60. Only those 60 may incur
audio hashing, v4/grid/marker validation or duplicate/lineage curation. This permits a
read-only locator listing; it does not authorize a library-wide audio, feature, model,
stem, identity or lineage sweep.

**`proposed`** Suspicious-pair generation is deterministic across the 60-row seed pool,
the frozen development-training manifest and anchors. Normalize text with Unicode NFKC,
case-folding, punctuation-to-space and collapsed whitespace. Freeze the version-token
lexicon as `remix|edit|bootleg|extended|radio|instrumental|vip|dub|mix|version|rework`.
Emit a pair when audio SHA-256 is equal; or normalized artist plus base title (with
bracketed/version-token suffix removed) is equal; or base title is equal and duration is
within 3.0 seconds; or normalized artist is equal, duration is within 3.0 seconds and BPM
is within 0.10. Sort pair IDs by hash and record exactly
`confirmed_related|confirmed_unrelated|unresolved`. Unreviewed/time-cap-exhausted pairs
are `unresolved`; every affected row is excluded, and fewer than 18 surviving lineages
yields INCONCLUSIVE.

**`proposed`** Thirty non-operator minutes covers **all** manual protocol preparation:
seed/development/anchor lineage review, suspicious-pair adjudication, and duplicate
review. Brandon receives none of it. Seed-pool hashing/v4/grid/marker validation is
included in the same 30-minute machine-analysis, 2-GB RSS and 500-MB scratch ceilings as
the pilot. Exceeding either manual or machine ceiling stops Phase 0; it does not expand
the pool or budget.

**`proposed`** Pilot eligibility is frozen before any candidate output:

1. not present in current label development lineages;
2. non-scripted for this acoustic pilot;
3. exact current v4 payload available and valid;
4. at least two existing Rekordbox candidate drop markers with full 16-beat coverage;
5. no unresolved duplicate or lineage ambiguity;
6. no cross-partition related group.

**`proposed`** Within that bounded candidate-neutral eligible pool, sort by
`SHA256(pilot_seed || recording_lineage_id)` and take the first 18. For each lineage,
sort eligible markers by `SHA256(audio_sha256 || marker_beat)` and take the first two.
Those same two are the family montage. This is not uncertainty, style, cluster, artist,
candidate-selected or post-label sampling. If fewer than 18 lineages survive, the pilot
is INCONCLUSIVE and the pool is not expanded after seeing predictions or answers.

**`proposed`** Only after canonical selected rows are finalized is `manifest_id` derived
as their SHA-256. The manifest must rebuild byte-identically, have unique instance IDs,
keep every related group in one split, and produce one immutable hash. Unresolved rows
inside the seed pool are prespecified exclusions; an unresolved relationship or overlap
discovered in the selected manifest or cross-partition audit is a hard FAIL. Close pairs
are grouped or excluded, never guessed.

**`proposed`** A separate `development_training_manifest` freezes the exact current
development and seven-anchor row IDs, per-axis permitted target, exclusions, duplicate/
lineage groups, scaler population, current label-file hashes, and output hash. The local
gold header's unknown HEAD is retained as a provenance limitation; no row is admitted by
filename alone. Incomplete rows may train only fields they contain. Each lineage has one
vote after the nearest-row reduction in §6.

### 9.3 Predictor firewall

**Default class for this subsection: `proposed`.**

**`proposed`** Each candidate declares a positive feature allowlist. The predictor process may receive
only the frozen acoustic/structure row and eligible development rows. It may not receive:

- title, artist, playlist, genre, cover art, content ID, path text, notes, or marker
  names/types beyond the numeric locator needed to slice audio;
- old human labels except the explicitly eligible development targets;
- weak/provisional predictions from another method unless the method contract names
  that input and an audio-only ablation exists;
- calibration/test answers or split-selection scores.

**`proposed`** Predictions, candidate code hash, environment hash and all input hashes are frozen before
human responses. The existing planner allowlist is retained but is not treated as proof
that a new candidate is safe.

### 9.4 Metrics and invalidators

**Default class for this subsection: `proposed`.**

**`proposed`** Report every axis separately:

- genuine-marker state: raw confusion counts, balanced accuracy when both classes exist,
  abstention, marker-wrong rate, and lineage-macro accuracy;
- hardness: pairwise agreement, tie/unsure rate, within-lineage ordering, false/missed
  T3 where comparable;
- family: exact counts, confusion counts, `mixed/none/unsure`, and lineage accuracy;
- marker stability: the exact primary-method contract in §11.4; family and diagnostics
  report sensitivity separately and do not enter integrated PASS;
- operator burden: seconds and atomic decisions per lineage, session position, fatigue,
  recognition and unsure rates; where counts permit, split results by recognized versus
  unrecognized tracks, otherwise state that recognition may have influenced truth;
- all intervals resample whole lineages; marker-micro results are secondary.

**`proposed`** No blended score can hide a failed axis. Challenge/enriched samples never enter a
random-headline metric. Hidden repeats measure human consistency only.

**`proposed`** Invalidate the affected result if any of these occurs: cross-split related audio; a
post-label prediction; a changed feature/pool/anchor/threshold after label access;
human exposure to hidden metadata or prediction; same-lineage neighbours; candidate-
selected test samples; provisional labels in truth; calibration on test; multiple test
opens; unreconciled rows; unreported abstention; model/extractor/anchor/taste changes
without invalidation; or correlated votes used as confidence.

## 10. Confidence semantics

**Default class for this section: `proposed`.**

**`proposed`** The limited pilot emits `raw_score`, `distance`, `agreement`, and
`abstain`; it emits no calibrated confidence.

**`proposed`** Later, confidence is per field and may be `unavailable` or `calibrated`. A calibrated
record must contain:

```text
field, candidate_version, calibration_manifest_hash, taste_policy_version,
calibration_method, bucket_bounds, calibration_lineages_n,
observed_error, interval_method, interval_lower, interval_upper,
coverage, abstention_threshold, ood_status
```

**`proposed`** Freeze score buckets on development data, then estimate each bucket on
separate calibration lineages. Use exact one-sided 95% Clopper-Pearson bounds for binary
correctness; report ordered absolute-error distributions separately for tier. Sparse
buckets merge according to a predeclared adjacent-bin rule or remain unavailable—never
after looking at test outcomes.

**`proposed`** The independent unit is one recording lineage per field. Multiple markers
from one lineage are reduced by a predeclared lineage outcome or evaluated with a
cluster-aware method; they are never counted as independent Bernoulli trials.

**`proposed`** “High confidence” means the field's one-sided 95% lower bound on correctness is at least
90%, on independent lineages from the declared population, with OOD false and the field's
coverage reported. With zero observed errors, at least 29 independent cases are needed;
any error requires more. A 30-lineage test at 30% high-confidence coverage yields only
about nine high-confidence cases and cannot qualify that bucket. Roughly 97 test lineages
would be needed merely to obtain 29 high-confidence cases at 30% coverage.

**`operator-decided`** Brandon must decide whether that eventual qualification workload
is worth the automation. Until then, every field is assist-only.

**`proposed`** Any extractor, preprocessing, candidate, anchor, taste policy, decision rule, or
calibration mapping change invalidates the affected confidence. OOD, missing evidence,
too-small calibration, or disagreement outside calibrated support forces abstention.
There is no blanket whole-profile confidence score. High confidence is explicitly
unavailable through the 15-lineage calibration / 30-lineage test Phase 3. Any later
qualification phase computes its required lineage count from observed field coverage
and the frozen error bound before Brandon decides whether to continue.

## 11. Minimal falsification pilot

### 11.1 Question and scope

**Default class for this subsection: `proposed`.**

**`proposed`** Test one question only:

> Can repeatable Brandon-authored judgments plus existing deterministic v4 evidence
> beat current F2 enough to justify one more offline experiment within 65 minutes of
> human work?

**`proposed`** The pilot covers genuine-marker state, pairwise intrinsic hardness, exact two-shown-
moment family, and marker stability. Genuine state may later prioritize or exclude an
offline proposal card; it remains audit-only live and never changes a marker or current
F2 fallback. Family success applies only to the shown-moment unit. Darkness, growl spans,
lasers, motion, color, room appearance, whole-track family, profile generation and
runtime are not inferred from a PASS.

### 11.2 Exact corpus, candidates and baselines

**Default class for this subsection: `proposed`.**

**`proposed`** The frozen comparison set is:

- corpus: the exact 18 lineages / 36 markers selected by §9.2;
- human anchors: the exact seven in §8.1;
- baseline A: `current_f2_790c625`;
- baseline B: candidate-neutral development majority for genuine-marker state;
- candidate C: `v4_exact_retrieval_v1` for genuine, hardness and family;
- diagnostic only: `hardness_v0_all_markers_v1` and `approach_v0_diagnostic_v1`;
- no embedding, stems, trained model, cluster default, active learning, or confidence.

**`proposed`** Baseline B is the exact majority of comparable genuine/not-genuine
targets in the frozen development-training manifest; an exact tie abstains. All
candidate and baseline mappings are materialized and hashed before human review.

### 11.3 Budgets and artifacts

**Default class for this subsection: `proposed`.**

**`proposed`** Hard ceilings:

- no download and no new model/dependency environment;
- analysis wall time <= 30 minutes on the pilot corpus;
- peak RSS <= 2 GB;
- scratch <= 500 MB and immutable retained artifacts <= 50 MB;
- 0 decode/manifest rows silently dropped;
- two identical runs produce byte-identical canonical prediction rows and verdict inputs;
- variable timing/RSS telemetry is excluded from those hashes and compared to ceilings;
- human active time <= 65 minutes and 113 atomic decisions;
- cleanup <= 10 minutes; no cache, label, audio, Rekordbox, config, sidecar, or runtime
  write.

**`proposed`** A future implementation spec may place immutable machine artifacts under a new
gitignored `local/spectral_ai_pilot/<pilot_id>/` directory. Required artifacts are:

```text
artifact_manifest.json
lineage_manifest.jsonl
card_manifest.jsonl
candidate_contracts.json
predictions/<method>.jsonl
prediction_hashes.json
responses.jsonl
metrics.json
resource_report.json
verdict.json
report.md
```

**`proposed`** Every artifact manifest row records type/schema/path/producer/consumer/input hashes,
output hash, HEAD, environment-lock hash, timestamp and `mutable:false`. Markdown is a
view; machine JSON is authority.

### 11.4 Frozen gates

**Default class for this subsection: `proposed`.**

**`proposed`** The thresholds below are screening gates, not qualification claims.
For every comparable truth row, `correct(method)` is 1 only for an exact answer match
and otherwise 0; abstention is 0 and remains separately reported. The paired row delta
is `correct(candidate) - correct(baseline)`. A lineage is a win/loss/tie when the sum of
its frozen row deltas is positive/negative/zero. Baseline and candidate use the same
truth rows. Candidate abstention caps count all candidate abstentions on those rows;
truth `unsure`/marker-wrong rows are unavailable, not candidate errors.

**`proposed`** Integrated stability gates only `v4_exact_retrieval_v1` genuine and
hardness. Recompute each central marker at beat deltas `-2,-1,+1,+2` with the frozen
feature/method contract. Genuine compares against constant majority baseline B;
hardness compares against current F2's pairwise output at the same shifted marker and
same frozen anchor. A decisive central candidate output that changes class or becomes
abstain at a valid shifted window is a flip. A central abstention is unavailable. An
out-of-range or invalid shifted window is reported and excluded by reason. A central row
is stability-comparable only with at least three valid shifts; the flip denominator is
all valid shifts on those rows. Family, `hardness_v0`, and approach sensitivity are
diagnostic only and never enter integrated stability PASS.

The exact gates are:

1. **Setup hard FAIL:** any leak, split overlap or unresolved relationship in the
   selected/cross-partition manifest, post-label
   prediction, nondeterminism, missing row, resource breach, or predictor-firewall
   breach.
2. **Human repeatability:** §8.3 comparison floors apply. Exceeding its direct-
   contradiction limit is hard FAIL; falling below a comparable-repeat floor is
   INCONCLUSIVE. The result is not learned around.
3. **Workload FAIL:** active time >65 minutes, more than 113 atomic decisions, or the
   operator stops because the workflow is exhausting.
4. **Genuine-marker availability:** at least 28 comparable calls across at least 16
   lineages; otherwise INCONCLUSIVE. **PASS:** v4 retrieval has at least six more correct
   calls than
   the frozen majority baseline, gains in at least four more lineages than it loses, and
   has no more than four candidate abstentions.
5. **Hardness availability:** at least 24 comparable calls across at least 14 lineages;
   otherwise INCONCLUSIVE. **PASS:** v4 retrieval has at least six more correct exact-
   pair calls than current F2 tier ordering, gains in at least four more lineages than it
   loses, and has no more than four candidate abstentions.
6. **Family availability:** at least 14 comparable lineage answers; otherwise
   INCONCLUSIVE. **PASS:** v4 retrieval has at least four more correct lineages than the
   exact-two-row current-F2 mapping in §6 and gains in at least four more lineages than it
   loses, with no more than four candidate abstentions. More than four total
   `mixed|none|unsure` human answers makes even the two-moment family abstraction FAIL
   regardless of predictor score.
7. **Stability availability:** each gated axis has at least 28 comparable central marker
   rows under the contract above. **PASS:** neither primary v4 axis's flip rate is more
   than ten percentage points worse than its named baseline.

The integrated verdict is deterministic:

```text
FAIL         if setup, repeatability, workload, genuine, hardness, family, or stability fails;
PASS         only if every named availability floor and every axis PASS is satisfied;
INCONCLUSIVE only for a named repeatability/availability floor or <18 eligible seed-pool
             lineages, and only when no FAIL condition fired.
```

**`inferred`** The net-win thresholds are intentionally demanding but not statistical qualification.
They prevent a one-card improvement from opening a platform program.

### 11.5 Outcome actions

**Default class for this subsection: `proposed`.**

- **After PASS (`proposed`):** authorize nothing automatically. The single next design task may be a
  bounded family-only challenger spec for exactly one pinned external embedding, plus a
  no-project/failure-correction comparator. Other axes remain deterministic/assist-only.
- **After FAIL (`proposed`):** retain current F2, local corrections, and any axis-specific simple
  result that passed; reject external models, stems, profiles, and runtime work for the
  failed integrated proposal.
- **After INCONCLUSIVE (`proposed`):** permit one protocol correction only if the cause was a frozen
  availability assumption. Do not answer ambiguity by adding a bigger model or more
  labels.

**`proposed`** The pilot leaves runtime code/config, caches, existing labels, sidecars, audio,
Rekordbox, bridge process, SoundSwitch, lasers and LEDs/Govee untouched.

## 12. Model and tool candidate matrix

The table separates source facts, unknowns, inferred value and proposed rulings so no
model fact silently endorses its use.

| Candidate | Classed facts | `unknown` | `inferred` unique value vs simplest alternative | `proposed` ruling |
| --- | --- | --- | --- | --- |
| Current v4 + exact retrieval | `confirmed-repo`: existing v4 measurements/cache and NumPy/SciPy analysis are reused. `proposed`: exact retrieval produces named neighbours under §6 | Pilot time/RSS | Explainable deltas and anchors; current rules are simpler | **Pilot first** |
| `hardness_v0` | `confirmed-repo`: v4 + markers produce deterministic continuous H/binary path fire; no runtime importer or new dependency; in-sample binary-T3 only | Pilot resource cost | Existing explainable hardness diagnostic | **Diagnostic first** |
| `approach_features_v0` | `confirmed-repo`: v4/grid/marker produce deterministic raw four-view descriptors; no classifier/runtime importer/new dependency | Pilot resource cost | Marker/darkness-shape diagnostic | **Diagnostic first** |
| [Discogs-EffNet `discogs-effnet-bs64-1`](https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.json) | `confirmed-external`: 16 kHz -> 400 style outputs + 1280-D embedding; about 18 MB; catalog/license pages conflict between CC BY-NC-SA and CC BY-NC-ND; Essentia library is AGPL/noncommercial or proprietary; ONNX Runtime supports macOS Arm; current official Essentia arm64 wheel index stops at CPython 3.12 | Local time/RSS/preprocess parity | Plausible family/style view only; v4 retrieval is simpler | **Defer; sole eligible external challenger after PASS, license acceptance, and artifact hashing** |
| [MERT-v1-95M](https://huggingface.co/m-a-p/MERT-v1-95M) | `confirmed-external`: 24 kHz -> 75 Hz, 12-layer/768-D representations; trained on five-second crops; 95M params/about 378 MB; checkpoint CC BY-NC 4.0, code Apache-2.0, custom code; official repo pins `transformers==4.38`; PyTorch MPS exists | Model-specific Apple support/RSS/time/determinism | Broader representation only if a named EffNet/v4 residual survives | **Defer** |
| [MAEST](https://github.com/palonso/MAEST), exact artifact TBD | `confirmed-external`: 16 kHz Discogs-style transformer; roughly 344–350 MB weights; code AGPL-3.0; Essentia weight-license pages conflict | Exact artifact, Apple cost and pooling parity | Longer context; may share Discogs/style bias with EffNet | **Reject from first two pilots** |
| [OpenL3 music-512](https://github.com/marl/openl3) | `confirmed-external`: audio-visual correspondence embedding; code MIT; TensorFlow stack; official repo documents a training-pair alignment bug | Exact weight terms/local Apple run | Generic diversity view with no named current residual | **Reject now** |
| [musicnn](https://github.com/jordipons/musicnn) | `confirmed-external`: three-second audio -> 50-tag auto-tagging/embedding; code ISC; official setup documents legacy TensorFlow/Python/NumPy constraints | Current Apple cost | Readable tags, but no unique need over v4/EffNet | **Reject** |
| [LAION-CLAP](https://github.com/LAION-AI/CLAP) | `confirmed-external`: audio/text contrastive embedding in a PyTorch/text-query stack | Exact checkpoint terms and Apple cost | Text retrieval is not current acoustic truth | **Reject** |
| [VGGish](https://github.com/tensorflow/models/tree/master/research/audioset/vggish) | `confirmed-external`: 16 kHz 0.96-second general-audio -> 128-D; TensorFlow Models code Apache-2.0 | Exact checkpoint terms/local Apple run | No demonstrated unique EDM/taste value | **Reject** |
| [HTDemucs `htdemucs`](https://github.com/facebookresearch/demucs) | `confirmed-external`: code MIT, original repo archived, pretrained-weight terms unresolved. `measured`: 80.2 MB weights/~1 GB environment, 1.52 GB RSS, 134.7 s/track, random-shift default in tracked pilot | Future macOS/dependency maintenance | Source-specific evidence only after a named v4 failure | **Deferred, targeted pilot-only** |

**`confirmed-external`** Primary sources checked on 2026-07-14:

- Essentia [model catalog](https://essentia.upf.edu/models.html),
  [Discogs-EffNet metadata](https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.json),
  [licensing](https://essentia.upf.edu/licensing_information.html), and
  [macOS arm64 wheels](https://essentia.upf.edu/downloads/python-wheels/macosx/arm64/);
- [ONNX Runtime Python support](https://onnxruntime.ai/docs/get-started/with-python.html);
- [MERT model card](https://huggingface.co/m-a-p/MERT-v1-95M) and
  [official repository](https://github.com/yizhilll/MERT);
- Apple [PyTorch/MPS support](https://developer.apple.com/metal/pytorch/);
- [MAEST](https://github.com/palonso/MAEST),
  [OpenL3](https://github.com/marl/openl3),
  [musicnn](https://github.com/jordipons/musicnn),
  [LAION-CLAP](https://github.com/LAION-AI/CLAP), and
  [VGGish](https://github.com/tensorflow/models/tree/master/research/audioset/vggish);
- Demucs [repository](https://github.com/facebookresearch/demucs),
  [`apply_model`](https://github.com/facebookresearch/demucs/blob/main/demucs/apply.py),
  and the unresolved [pretrained-weight license issue](https://github.com/facebookresearch/demucs/issues/327).

## 13. Stems ruling

**`proposed`** Stems ruling: **DEFERRED; TARGETED PILOT-ONLY.**

**`proposed`** Stems are not required for the limited pilot, not eligible for a full-library sweep,
and not an independent judge. Clean re-sum and proxy visibility do not prove lighting
benefit.

**`proposed`** Reopen stems only when a passed deterministic system leaves a named error class that
cannot be measured adequately from full mix. Before any new run, freeze:

- the one field and its human target;
- 12 lineage-disjoint held-out cases with positive and matched random-negative examples;
- v4-only and v4-plus-stem predictions before labels;
- a minimum six net-correct improvement across the 12 lineage units on that field, no
  regression on matched negatives, and deterministic boundary tolerance;
- `htdemucs` signature/weights/package/environment hashes, `shifts=0` or a frozen seed,
  two-run repeatability, <=2 GB RSS, <=45 minutes per track, and <=20 GB temporary disk;
- teardown and artifact-retention rules.

**`proposed`** Failure or inconclusive evidence rejects that stem field. No other field inherits a win.

## 14. New-track lifecycle

**`proposed`** This lifecycle is a future contract, not current behavior:

1. An off-show worker identifies exact audio bytes, current beatgrid and marker set.
2. Existing v4 is loaded or produced under the existing cache contract; learned-model
   absence never triggers a live download or inference.
3. Offline candidate fields are generated with per-field score/abstention and provenance.
4. OOD, missing evidence, disagreement and random controls enter a review queue; no
   profile is live merely because it exists.
5. Brandon's correction locks only the exact track/profile field by default.
6. An immutable profile version may be compiled only according to the field-eligibility
   scopes below; provisional high-impact fields remain out.
7. One explicit active pointer is published atomically; the previous active version is
   retained for rollback without re-analysis.
8. Audio-byte, beatgrid, marker-set, schema, taste-policy or decision-policy changes mark
   affected fields stale. File moves alone do not if exact audio identity remains.
9. Re-encodes become new audio identities. Whether a human correction follows the
   recording lineage is an explicit operator decision, never automatic.
10. USB/local locator changes may locate evidence, but a learned profile binds only
    after exact audio/grid/marker validation; current relaxed sidecar PDB matching is not
    sufficient.
11. A model upgrade creates new provisional versions. Human locks and the last-known-good
    active profile remain intact until a separately approved activation.
12. Missing model packages do not matter to live playback because frozen decisions,
    not models, are consumed. Missing/stale/corrupt profiles fall back to current
    behavior with a named reason.

## 15. Frozen profile contract sketch

This is a **`proposed` boundary sketch**, not an executable schema. It is sufficient to
bound a later Phase-5 spec, but canonical encoding, compile rules and measured size/load
ceilings remain explicit blockers. Every field may be removed after the pilot.

### 15.1 Envelope

**Default class for this subsection: `proposed`.**

**`proposed`** The envelope fields are:

| Field | Type / rule |
| --- | --- |
| `profile_schema_version` | integer; unknown major version rejects the overlay |
| `canonicalization_version`, `consumer_contract_version` | exact byte and runtime interpretation contracts |
| `profile_id`, `blob_sha256`, `profile_version` | `profile_id == blob_sha256`; compute SHA-256 over canonical payload with both digest fields omitted, then insert the same digest; immutable and never overwritten |
| `runtime_plan_hash` | separately computed over canonical compiled-plan bytes; replay oracle |
| `manifest_generation_id`, `parent_generation_id` | one atomic active generation and rollback chain |
| `created_at`, `producer_head` | UTC timestamp and exact code commit |
| `audio_sha256` | exact audio-byte identity; required |
| `content_id_locator`, `path_hint` | non-authoritative locators only |
| `audio_duplicate_group`, `recording_lineage_id` | provenance/audit IDs; never runtime match by themselves |
| `beatgrid_fingerprint`, `marker_set_fingerprint` | exact required runtime validity |
| `analysis_schema`, `analysis_payload_hash` | v4/extractor provenance |
| `candidate_versions`, `artifact_hashes`, `environment_lock_hash` | complete offline provenance |
| `anchor_set_version`, `taste_policy_version`, `calibration_version` | human-policy provenance |
| `operator_state` | `unreviewed | partially_reviewed | approved_shown_fields | corrected | vetoed` |
| `active_eligible` | false unless every required envelope and bundle rule passes |
| `supersedes`, `history_hash` | immutable version chain |
| `stale_reasons` | list; any envelope identity mismatch disables the overlay |
| `fallback_policy` | fixed enum naming current-behavior fallback; not arbitrary prose |

### 15.2 Decision fields

**Default class for this subsection: `proposed`.**

**`proposed`** Each field record contains:

```text
value, value_type, unit, coordinate_system,
source, source_version, evidence_family, reason_codes,
confidence_status, confidence_record_id, ood_status,
human_state, override_value, override_reason, lock_scope,
created_at, supersedes, stale_reason
```

Track scope may include `family = WALL|COMET|HOUSE|mixed|none|unknown` and its displayed
approval scope. Marker rows are keyed to the exact frozen marker identity and may include
`genuine_state`, continuous intrinsic hardness, tier, arrival impact, darkness evidence
and chosen beat span, aggressive/growl beat spans, musical laser opportunity, and motion
anchor.

**`proposed`** `genuine_state` is audit/review information only. It may not add, delete, move, or
suppress a Rekordbox marker live. Laser musical opportunity is not hardware safety or a
direct laser command. Color identity is absent: current F1 and Brandon's F1 corrections
remain sovereign.

**`proposed`** Eligibility is field-scoped:

| Evidence class | Field state | Maximum activation scope |
| --- | --- | --- |
| `operator-decided` | Human-corrected | Exact audio/profile/marker/field lock only |
| `operator-decided` | Approved shown field | Exact shown field and approval scope only; unseen moments remain unreviewed |
| `proposed` | Automatically generated unseen field | Ineligible until its own independent qualification bound and operator policy permit it |
| `live-gated` | Darkness, laser influence, motion, color or room-visible high-impact behavior | Also requires its existing authority plus separate attended live/room gate; audio never certifies safety |

### 15.3 Coupling, partial profiles and rollback

**Default class for this subsection: `proposed`.**

**`proposed`** Coupling and rollback rules are:

- Profile versions are immutable; one active pointer changes atomically.
- The current and previous active versions remain readable; rollback changes the pointer
  without rerunning analysis.
- An invalid envelope disables the entire learned overlay.
- Within a marker, coupled F2 fields `family+tier+darkness` are atomic: never mix a stale
  profile family with a freshly computed tier.
- Optional F4 texture spans may abstain independently and then leave current F4 behavior
  unchanged.
- Unreviewed/provisional fields never run live. A correction clears inherited model
  confidence for that field and remains locked across regeneration.
- Corrupt or partially published versions are quarantined and never partially consumed.
- A model/license disappearance cannot break playback of an already valid frozen
  decision, but it blocks regeneration.

**`confirmed-repo`** The current sidecar's fixed per-content paths are not a rollback-safe
learned-profile store because payload files can be replaced before the index swap.
**`proposed`** Any future export must use immutable content-addressed blobs plus an
atomically replaced manifest; this is not authorized here.

**`proposed`** Exact audio identity is established off-show during install/export and
bound to file-instance stat evidence. Track load may reuse only a still-valid binding; it
never hashes an entire audio file or waits for revalidation. If the binding cannot be
proved within the future measured off-loop load ceiling, the overlay stays unavailable,
current behavior continues, and offline revalidation is queued. A thin active manifest
references one immutable content-addressed blob per track; evidence does not live in the
all-track index.

## 16. Runtime invariants and consumer map

| Class | Field/owner | Future translation and invariant |
| --- | --- | --- |
| `confirmed-repo` | Rekordbox markers | Remain timing authority. Learned `genuine_state` never creates/cancels/moves markers. |
| `confirmed-repo` | F1 color identity | Unchanged and sovereign; profile carries no color identity. Existing human corrections survive. |
| `proposed` | F2 core bundle | If ever authorized, compile approved/qualified `family+tier+darkness` into the existing plan shape off-loop. Invalid envelope or track-level field disables the whole learned overlay for that track. With a valid envelope, an invalid marker bundle falls back to current F2 for that exact marker; other valid immutable marker bundles may remain usable. Never assemble a mixed marker bundle. |
| `proposed` | F4 texture | May season only existing F4-owned parameters/preferences; absence -> current F4. |
| `confirmed-repo` | Drop presentation / lasers | Current hot-cue, learned, finale, runway, ratio, qualifier, manual and policy gates stay above any musical proposal. No audio profile certifies safety. |
| `confirmed-repo` | Scripted tracks | Scripted-track sovereignty: learned profile stands down completely. |
| `confirmed-repo` | Manual/emergency | Manual authority and emergency blackout always win. |
| `confirmed-repo` | Engine ownership | One active engine/owner path; no parallel AI scheduler or output writer. |

**`proposed`** The following future rules preserve the `confirmed-repo` authorities in
the table above:

- no live generative AI, embedding inference, stem separation, vector search, training or
  cloud requirement;
- no blocking network, filesystem, subprocess, model or database I/O in the 200 Hz push
  loop;
- profile load/validation/compile occurs on an existing off-loop worker and publishes one
  immutable in-memory object;
- deterministic replay freezes canonical track-load inputs, consumer-contract version,
  enum/numeric/rounding rules and activation boundary, then compares the compiled
  `runtime_plan_hash` and golden output trace;
- a default-off kill switch restores current behavior; v2/profile-off byte identity must
  be tested where the current contract requires it;
- “fail open” means fail toward current HEAD behavior: current F1 store/correction,
  current F2 computation when enabled, current F4 containment, current presentation
  policy, and existing missing-data fallbacks—not fail to darkness or lasers;
- a missing/stale/corrupt/unreviewed profile emits one named reason and contributes no
  **profile-derived** darkness or laser influence; current HEAD fallback may still
  produce its existing darkness and laser decisions;
- no runtime activation before separate implementation authorization, software tests,
  visual gates, and explicit operator approval for a restart/hardware-adjacent check.

## 17. Operator experience

### The limited pilot

**Default class for this subsection: `proposed`.**

**`proposed`** Brandon experiences four short prediction-hidden sessions, not a model
dashboard: one anchor session and three six-lineage sessions. He answers neutral-ID
audio questions, can choose `unsure` or `marker wrong`, and may stop at any time. He does
not label features, confidence, model quality, or every lighting field.

**`proposed`** The machine automatically freezes candidate-neutral cards, computes deterministic
predictions, hides them, times responses, checks repeats, and produces an explanation
after answers are immutable. It does not write to Rekordbox, alter audio, change lights,
or generate a live profile.

### Any later proposal workflow

**Default class for this subsection: `proposed`.**

**`proposed`** Only disagreements, OOD cases, high-impact fields, random controls, and
practice failures enter review. “Accept” means accept the exact shown fields/moments for
profile version X; unseen moments stay unreviewed. Approving a cluster representative
creates an anchor, not automatic approval for neighbours.

**`proposed`** A practice “veto now” capture should record track/profile/marker/version/decision and ask
only for a small correction category. Corrections are local locks by default. They may
affect other tracks only through a new offline candidate version and fresh evaluation—
never immediate neighbour propagation and never live learning.

**`proposed`** The explanation surface should show named v4 evidence, frozen neighbour IDs/distances,
which evidence families agreed/disagreed, calibration population when available, and
why the system abstained. Opaque embedding dimensions are never presented as reasons.

**`unknown`** The eventual number of production reviews is not yet known. The pilot must
measure seconds/decisions per lineage before any claim that automation reduces work.

## 18. Risk register

Every risk and residual-risk statement below is **`inferred`**; every mitigation and
detection is **`proposed`**.

| Risk | Mitigation | Detection | Residual risk |
| --- | --- | --- | --- |
| Self-training loop | Separate human-development, prediction-hidden, weak and provisional stores | Hash/import firewall tests | Human development answers can still reflect remembered prior work |
| Shared-model bias | Evidence-family grouping; no vote-count confidence | Common-error audit and random controls | Models may share unknown training corpora |
| False confidence | Independent calibration, exact bounds, sample floors, abstention | Reliability/raw-count report | Qualification may demand unacceptable labor |
| Genre imbalance | Candidate-neutral hash sampling and lineage-macro metrics | Post-selection diversity counts/errors | Small pilot cannot cover the whole library |
| Remix/edit leakage | Audio duplicate + recording lineage groups; fail closed | Cross-split and neighbour audits | Ambiguous bootlegs may require human curation |
| Marker sensitivity | Exact marker fingerprint and +/-1/2 tests | Flip-rate gate | Beatgrid changes can invalidate otherwise good audio evidence |
| Anchor overfit | Seven unrelated versioned anchors; separate test | Leave-one-lineage anchor checks | Seven anchors cannot represent all future taste |
| Subjective labels treated as truth | Explicit objective/perceptual/taste/live layers | Per-field provenance | Brandon's taste can be context-dependent |
| Preference drift | Rotating anchor repeats and taste-policy version | Reversal trigger | Drift can be gradual and hard to detect |
| License/model disappearance | Artifact and term hashes; no live dependency | Regeneration preflight | Future distribution rights may stay unclear |
| Dependency rot | Disposable locked environment, one challenger maximum | Clean rebuild/repeat test | Old frameworks may stop running on new macOS |
| Apple incompatibility | Local RSS/time/repeat gate before comparison | Two-run smoke and parity report | CPU/GPU updates may alter numerics |
| Compute/disk growth | Corpus and resource ceilings; pooled-only retention | Resource report | Full-library costs remain unknown until later |
| Stem artifacts | Matched negatives, deterministic shifts, semantic human targets | Re-sum plus field error/boundary checks | Separation can sound plausible while swapping/bleeding sources |
| Stale profiles | Exact audio/grid/marker/schema/taste validation | Named stale reason and log | Exact identity may reject harmless re-encodes |
| Corrupt caches/profiles | Schema/hash checks and immutable versions | Fail-closed loader tests | Existing cache corruption may reduce coverage |
| Silent fallback | Named reason, reconciled counts, status/log surface | Missing/stale/corrupt tests | Operators can miss logs during performance |
| New-library distribution shift | OOD abstention and random audits | Distance/coverage drift report | OOD detector shares representation bias |
| Generic lighting | Brandon anchors, local vetoes, room gate | Cluster-by-cluster visual audit | Automation may converge on safe but bland defaults |
| Hidden operator labor | Atomic-decision and wall-time ledger | 65-minute gate; later cumulative budget | Lineage disputes and visual review remain real work |
| Second authority | Preserve F1/F2/F4/manual/scripted ownership; compile only | Authority/precedence tests | Future schema pressure may reintroduce duplication |
| Unsafe laser inference | Separate musical desire from hardware safety | Existing laser gates and attended validation | Audio can never certify physical safety |

## 19. Decision ledger

“Decision confidence” below is the lead's stated confidence in a **`proposed`** ruling,
not an evidence class or calibrated model confidence.

| Class | Decision | Rationale/evidence | Alternatives rejected | Decision confidence | Reopen trigger |
| --- | --- | --- | --- | --- | --- |
| `proposed` | Verdict is limited pilot only | Round-1 project and testability blockers; current independent truth is small | Pursue architecture; reject everything now | High | A valid pilot result |
| `proposed` | Deterministic methods first | Existing v4/hardness/approach surfaces are cheaper and explainable | Embedding-first | High | They pass yet leave a named residual |
| `proposed` | No external model in first pilot | Prevents a weak-baseline comparison and dependency sunk cost | EffNet in first run | High | Integrated deterministic PASS |
| `proposed` | Current labels are development only | Selected/used during rule work; gitignored provenance | Treat as holdout/gold | High | Never; new independent data required |
| `proposed` | Prediction-hidden, not “blind” | Familiar-track recognition is unavoidable | Claim listener blindness | High | Different operator/library |
| `proposed` | Seven anchors | Minimal used family/hardness/mixed set | 8–12 anchors; unused restraint anchor; no anchors | Medium | Repeatability or coverage failure |
| `proposed` | 18 lineages / 36 markers | Small falsification corpus with lineage grouping | Full library; 158-marker form | Medium | Valid-data attrition below gate |
| `proposed` | 65-minute/113-decision ceiling | Honest count including repeats and montages | “36 cards/one hour” shorthand | Medium | Brandon sets a lower ceiling |
| `operator-decided` | The pre-pilot burden and workload gates passed on 2026-07-14 | Brandon answered yes after the four-session/65-minute/113-decision breakdown was explained | Stop before Phase 0 | High | Brandon withdraws or lowers the workload authorization |
| `operator-decided` | Fable 5 is executive orchestrator and project manager for this spectral automation product | Brandon assigned ownership on 2026-07-14 | Codex or an implementation agent silently managing architecture | High | Brandon reassigns the role |
| `operator-decided` | All work uses Claude CLI tmux seats; Fable never spawns internal subagents | Brandon corrected the execution topology on 2026-07-14 | Fable Agent-tool fan-out; Codex execution | High | Brandon changes the operating model |
| `operator-decided` | SOL4's 35-concept catalog is durable creative product input | Brandon supplied the exact capture on 2026-07-14 | Ignore the catalog; treat it as accepted architecture | High | Brandon replaces or retires the catalog |
| `proposed` | Per-axis PASS and integrated all-axis PASS | Prevents family success from licensing unrelated fields | Blended score | High | Pilot shows an axis should be removed entirely |
| `proposed` | Whole-track stable family remains unproven | Human and method unit is exactly two shown moments | Presume one track family | High | A later whole-track protocol |
| `proposed` | No AI prediction is gold | Correctness requires independent human truth | Consensus gold | High | Never |
| `proposed` | Per-field confidence only | Error differs by decision field | Whole-profile confidence | High | Never without strong new evidence |
| `proposed` | F1/color out of scope | Existing F1 authority/corrections; room taste not acoustic | Learned color identity | High | Brandon explicitly reopens color study |
| `proposed` | Stems deferred | Tracked gate failed; random default; high cost | Full sweep; required stems | High | Named residual + field-specific spec |
| `proposed` | Exact audio+grid+marker profile identity | Current relaxed locator is unsafe for learned decisions | Content ID/title match | High | A verified portable fingerprint contract |
| `proposed` | Provisional profiles never live | Prevents silent high-impact behavior | Unreviewed auto-activation | High | Never; approval/qualification remains required |
| `proposed` | Fail open means current behavior | Preserves current authorities and byte-identity expectation | Fail dark or partial mixed plan | High | A separately approved runtime contract |

## 20. Open questions

Only these genuinely require operator truth, unavailable live evidence, or an experiment:

**`operator-decided`** Closed 2026-07-14: Brandon confirmed that the current burden
justifies a bounded experiment and accepted the four-session, 65-minute/113-decision
ceiling. These decisions permit specification work only.

1. **`operator-decided`** Are the seven proposed anchor roles and current family
   vocabulary meaningful, or should an axis be simplified before testing?
2. **`operator-decided`** What later per-field error ceiling and review coverage would
   justify more human qualification work?
3. **`operator-decided`** Should a correction ever follow a re-encoded recording
   lineage, or remain exact-audio-only?
4. **`unknown`** Can Brandon repeat genuine/hardness/family judgments within the frozen
   threshold?
5. **`unknown`** Do deterministic v4/retrieval candidates beat current F2 and
   save review work on unrelated lineages?
6. **`unknown`** Does a later Discogs-EffNet family-only view add unique value after
   deterministic retrieval, within its license/resource constraints?
7. **`unknown`** Is exact SHA-256 plus grid/marker identity operationally sufficient for
   move/USB workflows, or is a verified perceptual fingerprint also needed?
8. **`live-gated`** Do any future darkness, motion, laser or color proposals look right
   in Brandon's room and remain within existing safety/authority rules?

## 21. Future implementation sequence

**Default class for this section: `proposed`.**

Every phase below is **`proposed`** and unauthorized by this review. Each needs a
separate bounded spec and explicit dispatch. **`operator-decided`** Every authorized
round is executed in a named Claude CLI tmux session under Fable's management; Fable
does not use its Agent tool or spawn internal subagents.

### Phase 0 — Protocol package

- **Purpose:** turn §§6, 8, 9 and 11 into schemas and pure validation code.
- **Inputs:** this review and current read-only development artifacts.
- **Outputs:** manifest/card/prediction/response/artifact schemas; verdict function;
  candidate contracts; test matrix.
- **Preconditions:** **`operator-decided`** satisfied 2026-07-14: Brandon answered yes
  to both pre-pilot kill questions; Fable 5 owns executive orchestration and project
  management; no model install.
- **Kill gate:** any ordinary engineering choice remains ambiguous or any schema cannot
  reconcile all rows.
- **Tests:** schema rejection, deterministic manifest, lineage disjointness, feature
  firewall, no-write/runtime-import checks.
- **Rollback:** delete the new disposable pilot namespace/code; current repo behavior is
  unchanged.
- **Status language:** `planned` -> `software-tested offline tooling`; never `validated`.
- **Next trigger:** independent review confirms the package implements one meaning.

### Phase 1 — Deterministic limited pilot

- **Purpose:** run the exact falsification experiment in §11.
- **Inputs:** frozen protocol, 18-lineage manifest, seven anchors, existing v4.
- **Outputs:** immutable predictions/responses/metrics/resources/verdict artifacts.
- **Preconditions:** predictions frozen before human review; operator explicitly starts
  each session.
- **Kill gate:** §11.4 exactly.
- **Tests:** candidate unit tests, permutation/tie determinism, missing/corrupt abstention,
  denominator reconciliation, repeatability, workspace byte-identity, no bridge contact.
- **Rollback:** remove disposable pilot artifacts after retaining the hashed report if
  Brandon chooses; no live rollback exists because nothing runs live.
- **Status language:** `measured development pilot`, not qualified.
- **Next trigger:** integrated PASS only.

### Phase 2 — One family-only embedding challenger

- **Purpose:** test whether pinned `discogs-effnet-bs64-1` adds family value beyond the
  frozen v4 retrieval.
- **Inputs:** named Phase-1 residual, new lineage-disjoint challenge set, fixed v4
  comparator.
- **Outputs:** environment/model/license manifest, pooled vectors, family predictions,
  resources and paired result.
- **Preconditions:** exact artifact terms accepted for local use; weight/code/preprocess
  hashes; predictions frozen before new answers.
- **Kill gate:** reuse §11.4's exact per-lineage paired delta, abstention and family-
  availability mapping: at least four more correct lineage calls and at least four more
  lineage wins than losses over v4 retrieval, <=1 GB environment/download, <=2 GB RSS,
  <=30-minute corpus run, and two-run decision identity. Otherwise reject the embedding.
  Its separate spec must freeze exact audio windows/pooling and a relevant perturbation
  test before predictions; no undefined Phase-1 marker-stability rule is inherited.
- **Tests:** backend/preprocess parity, deterministic pooling, no metadata, related-
  neighbour exclusion, clean teardown.
- **Rollback:** delete disposable environment and vectors; Phase 1 remains readable.
- **Status language:** `experimental measured`, never general model validation.
- **Next trigger:** family-only PASS plus measured operator benefit.

### Phase 3 — Calibration and one-open test

- **Purpose:** decide whether the surviving assist-only field merits more work.
- **Inputs:** one frozen candidate; 15 calibration and minimum 30 test lineages.
- **Outputs:** calibration records, one-open test report, workload comparison against
  current behavior plus failure-driven corrections.
- **Preconditions:** split quarantine/retirement rules active; no test access during
  selection; a field-specific gate document with operator-decided error/coverage/
  workload thresholds is hashed before calibration predictions.
- **Kill gate:** field error, coverage, workload or drift fails its frozen rule; any test
  use changing the system retires the claim.
- **Tests:** split registry, single-open audit, exact intervals, confidence unavailable
  below sample floor.
- **Rollback:** retire candidate; keep current behavior and local corrections.
- **Status language:** `assist-only measured`; high confidence is unavailable in this
  phase regardless of result.
- **Next trigger:** operator decides measured benefit justifies proposal generation.

### Phase 4 — Offline proposal generator

- **Purpose:** generate versioned, non-live cards for passed fields only.
- **Inputs:** qualified/assist-only field policies and immutable evidence.
- **Outputs:** provisional profile rows and explanation/review reports.
- **Preconditions:** no high-impact field inherits another field's PASS.
- **Kill gate:** review burden exceeds current correction burden; outputs become generic;
  corrections do not stay local.
- **Tests:** field provenance, lock preservation, abstention, no profile activation.
- **Rollback:** discard provisional rows.
- **Status language:** `provisional offline`.
- **Next trigger:** separate operator decision about a runtime profile spec.

### Phase 5 — Profile/export/runtime specification

- **Purpose:** formalize §15 against current F1/F2/F4/sidecar code at then-HEAD.
- **Inputs:** passed fields and current runtime contracts.
- **Outputs:** formal schema, immutable publication/rollback design, consumer mapping,
  kill switches, logs and tests.
- **Preconditions:** profile identity and current sidecar/USB behavior reverified; exact
  field authority approved.
- **Kill gate:** second authority, push-loop I/O, relaxed identity match, partial coupled
  bundle, scripted/manual/emergency regression, or no byte-identity proof.
- **Tests:** schema/version/stale/corrupt/atomic publication/rollback/replay/fallback,
  F1 correction preservation, scripted stand-down and v2-off byte identity.
- **Rollback:** pointer to previous immutable profile; one-code-revert shape specified.
- **Status language:** `designed` until implementation and software tests; always
  hardware-unvalidated until attended proof.
- **Next trigger:** explicit implementation authorization, then a separate explicit
  live-operation approval before any restart/toggle/hardware check.

## 22. Final recommendation

**`operator-decided`** The single next action is to give Fable 5 the bounded executive-
manager handoff in
`docs/prompts/active/spectral_ai_phase0_fable_manager_kickoff_2026_07_14.md`. Fable may
verify this review and author one Claude-CLI-executable Phase-0 protocol specification.
Any later work is dispatched through named Claude CLI tmux sessions, never Fable's Agent
tool or internal subagents. Fable may
not implement the protocol, dispatch pilot execution, or widen the product scope.

**`proposed`** Do not install or run an embedding, run stems, fill the remaining
158-marker form, build a review UI, generate a profile, touch runtime, implement Phase 0,
or run the pilot. After Fable returns a reviewed Phase-0 spec, Brandon must separately
authorize any implementation.

## Operator closeout

**`confirmed-repo`** This review changes nothing live. SoundSwitch, lasers, LEDs/Govee, Rekordbox readers,
F1 corrections, F2/F4, scripted tracks, marker timing, manual controls and blackout
remain exactly under their current authorities.

**`proposed`** Healthy future behavior, if later implemented, would be recognizable because the bridge
would load one exact profile version off-loop, log its audio/grid/marker match, abstain
with a named reason when invalid, leave scripted/manual/emergency paths untouched, and
run no model during a show. SoundSwitch, lasers and LEDs/Govee should behave exactly as
they do now whenever the profile feature is off or invalid.

**`confirmed-repo`** Verified here: current code and contracts at `790c625`, current
F1/F2/F4/sidecar seams, and existing deterministic candidates. **`measured`** The local
development-score counts/hashes and tracked stem resource/result record were reproduced
or checked. **`confirmed-external`** The model/tool facts are linked to their checked
primary sources.

**`live-gated`** Not hardware-validated: every proposed method, future profile, future runtime mapping,
visual result, laser result, SoundSwitch result, LED/Govee result, and new-track flow.
Representation sufficiency, operator repeatability, operator burden, content identity
portability, and all independent accuracy remain unknown until the bounded experiments.

**`proposed`** No live command, restart, toggle, cache rebuild, model install, or hardware
approval is needed now. The two-answer workload gate has passed; only Fable's Phase-0
specification round is open. Phase-0 implementation and pilot execution remain blocked
on later review and explicit authorization. Any future runtime work requires separate
implementation and live-operation approvals.
