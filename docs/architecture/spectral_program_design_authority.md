---
doc_status: current
truth_level: operator-ratified architecture charter (design authority; not code-derived)
last_verified_commit: f84ed5ce
last_verified_date: 2026-07-19
validation_scope: >
  Design/architecture reconciliation only. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED. Authorizes no implementation, dependency, runtime, or
  lighting change; every build stage needs its own spec, review, and operator
  authorization. Reconciliation inputs (proposals, the four reviews, the Sol
  agreement report) live in gitignored `local/spectral_v5_2026_07_17/`.
---

# Spectral Program Design Authority — the settled architecture (v2, 2026-07-18)

Registry row: AWR-284. Program: AWR-283 (spectral v5) / AWR-195 (spectral AI program).

status: AUTHORITATIVE (operator-ordered convergence; Fable-authored and Sol
AGREED-WITH-EDITS in `local/spectral_v5_2026_07_17/sol_authority_v2_agreement.md`;
supersedes the architecture charter of `local/spectral_v5_2026_07_17/sol_program_design.md`,
whose Stage-1/2 technical content, identities, unlock schedule,
and validation lanes REMAIN in force and are incorporated by reference)
authority note: This document authorizes
NO implementation, NO dependency installation, NO GPU use, NO sweep changes, NO runtime
integration, NO lighting behavior change. Each build stage needs its own spec + review
+ operator authorization.
inputs reconciled: operator proposal (architecture_proposal_2026_07_18.md), ChatGPT
addendum 1 + 2, Fable review (fable_architecture_review.md), three hostile Sol reviews
(sol_architecture_review.md, sol_architecture_addendum_review.md,
sol_architecture_addendum2_review.md). Where this document and those reviews conflict,
this document is the reconciliation and wins; where it is silent, sol_program_design.md
and repo code/tests win.

## 0. North star (operator, verbatim intent)
"Make spectral audio analysis as smart as possible and automated for every track, not
just for lasers. If there is a characteristic of certain tracks that I want to have the
bridge do lighting cues for, I should be able to point AI to it and ask for that."
The bridge is becoming a lighting operating system for Rekordbox. The operator points
at a sound; the system learns to (1) understand which sound, (2) find its occurrences
with honest timing, (3) understand musical context, (4) judge lighting warrant
separately, (5) compile synchronized cues offline. Deliverable #1 of the program
remains the laser-warrant list from the bounded growl/sustain scorer.

## 1. Non-negotiable boundaries (unchanged, restated)
1. Offline only. No v5+ package is ever imported by the bridge runtime; the 200 Hz push
   loop gains no I/O. Runtime may LATER consume versioned precomputed schedules via a
   separately specced adapter (§8) — never models, never file reads in the loop.
2. Labels accrue passively or voluntarily only. No labeling sessions, ever. Silence is
   never approval. A veto means only "not this proposed moment now."
3. Taste is human authority. No acoustic feature proves lighting warrant (verdict item
   12 is the standing counterexample).
4. Global behavior only: no per-track thresholds; artist/title/genre/playlist/path
   never enter acoustic models.
5. Precision before recall; abstention is a first-class output with visible reasons.
6. The unlock schedule (sol_program_design.md §7.2) governs every OPERATOR-LABEL-trained
   component. Synthetic-supervised components (§6) are additionally governed by the
   transfer gates below; they never bypass locked-future evaluation on real evidence.
7. Status language: nothing here is stable/production-ready/hardware-validated.

## 2. The settled target architecture
Seven layers, bottom to top. Layers 1-2 exist; 3-7 are built one gated stage at a time.

### L1. Evidence store (EXISTS — keep exactly as built)
Content-addressed identities (content_id / audio_artifact_id / grid_id), immutable
hashed manifests, Stage-1 high-resolution transient evidence (mixture clock, 2.9 ms
frames), Stage-2 four-stem per-beat/frame features (v12, quality bits, fail-closed),
append-only label events with provenance and tombstones, lineage counting. New evidence
axes append; nothing is rewritten.

### L2. Doctrine of timing and sources (SETTLED — adopted as standing rules)
- The ORIGINAL MIXTURE owns official event timing. Separated or embedded views may
  propose; only mixture-clock refinement (spectral flux, envelopes, trajectories,
  exemplar correlation) sets official boundaries. Any future detector names its
  deterministic mixture alignment rule, tolerance, and abstention behavior.
- Native-rate candidate-window reopening (44.1/48 kHz stereo) is sound hygiene for
  precision work; the source clock is preserved end-to-end; a 48 kHz processing branch
  must measurably beat 44.1 kHz before it earns a cache branch.
- Stems are one sensor. Separation uncertainty is currently representable only as
  quality bits + descriptive stats (the v11 bleed-detector failure is the standing
  proof); no numeric "bleed confidence" exists until a source-truth research arc
  produces one.

### L3. Event envelope + typed family payloads (PROVISIONAL SHAPE; frozen only after two families; replaces every "graph" ambition)
One small COMMON ENVELOPE per event: event_id, content_id, grid_id|null, family
(sustain_v1 | impulse_v1 | later families), start/end in samples + seconds + beats
(half-open), detector_artifact_hash, evidence_refs, quality_flags, decision
(candidate|confirmed|review|rejected), calibration_scope|null, abstention_reason_codes.
EVERYTHING else lives in a typed family payload owned by that family. There is NO
universal confidence field: each family payload stores its own named score, support
count, metric domain, and exact calibration-report hash where one exists; otherwise
calibration_scope is null and the score is explicitly descriptive/ranking-only. A 0.8
impulse score is never compared to a 0.8 texture score. No graph nodes/edges exist until
a real consumer needs a named relation. First provisional instantiation: a family-local
sustain_v1 export from the bounded growl scorer's outputs (renames + one export file; no
scorer behavior change). It does not freeze a shared contract; the shared envelope is
frozen only after impulse_v1 exists and proves what the two families actually share.

### L4. Concepts as versioned recipes (NOT plugins)
A concept is a JSON record: concept_id, version, event_family, positive_exemplars
(content_id + span + provenance), hard_negatives (+ reason), candidate_generator_hash,
detector_artifact_hash|null, presence_evaluation_hash|null, warrant_policy_id|null,
presentation_policy_id|null, status (provisional | shadow | locked_test |
eligible_for_integration | retired), supersedes. No plugin loader, base class,
dispatcher, or generic confidence. The registry is extracted from what the first TWO
genuinely different families (sustain, impulse) actually share — never designed ahead
of them. Concept handles are operator-coined or exemplar-track handles; invented
vocabulary is banned (two naming failures stand).

### L5. Concept lifecycle: how "point at a sound" actually works
1. POINT: the operator highlights a span (or names track+timestamp). This creates a
   PROVISIONAL concept: a search query, not a detector.
2. DISCOVER (multi-view retrieval): candidate windows are retrieved by a UNION of
   views — family-specific DSP shape distance, the single winning encoder's embedding
   distance (§5 Stage-3 discipline), and source-view distance where stem quality is
   clean. Every neighbor is shown with WHY it matched and which view supplied it;
   embedding-only support stays `review`. Hard negatives (including production-style
   twins and same-track negatives) sharpen the query.
3. CONFIRM (only path to durability): explicit presence confirmations via small,
   IGNORABLE offers surfaced in existing workflows (a diverse micro-set: nearest
   match, a style twin, a same-track negative, an out-of-style candidate). Ignored
   offers = the concept simply stays provisional. Vetoes NEVER relabel hearing; they
   feed presentation statistics only (two-channel routing). The offer mechanism itself
   ships only with operator approval.
4. HARDEN: a stabilized concept becomes a FROZEN family-specific detector (the
   detector-v3 pattern: single mechanistic configuration, full identity hashing,
   frozen_diagnostic evaluation, executable gates). Optionally challenged by the
   synthetic-augmentation pathway (§6) when its family passes the transfer probe.
5. EVALUATE: three lanes always (development / frozen_diagnostic / locked_future);
   retrieval anecdotes are never promotion evidence; every consumed future set is
   consumed forever.
6. PRESENT: warrant and presentation live OUTSIDE the detector (L7).

### L6. Family roadmap (one at a time, each earned by a named concept)
- sustain_v1: the bounded growl scorer (in spec review now). BOUNDED: it stays
  no-learning, growl/sustained-harmonic-only, ≥3 candidate beats, transductive
  diagnostic. It is the SEED of L3/L4 by export only; nothing is added to it.
- impulse_v1: Stage-1 transient evidence + de-duplication; target concepts: screech
  stabs / horn hits (verdict items 26/28/40 are the fixture anchors). Second family;
  proves what the envelope/registry genuinely share.
- rhythm_v1: beat-normalized Stage-1 onset patterns. After impulse.
- gesture_v1: spectral centroid/band trajectories first; pitch trajectories only where
  harmonic pitch confidence exists. Deferred until a named concept demands it.
- motif_v1, texture_v1: deferred (motif needs a trustworthy melodic representation
  that no current artifact stores; texture rides on Stage-3 retrieval and never sets
  boundaries alone).

### L7. Warrant + presentation (existing machinery, new interface)
Three separately versioned judgments: acoustic presence (detector), musical warrant
(context policy), presentation (fixture family, tier, duration, repetition, cooldown).
Presentation authority is the EXISTING dispatch machinery (led_dispatch_policy,
LaserDirector/LaserSceneExecutor, blackout/emergency masks, balance law). An offline
CUE COMPILER (later, own spec) consumes confirmed events + a versioned presentation
policy and emits immutable schedules (cue id, event id, target time, role, tier,
duration, allowed timing error, priority, dedupe group, cooldown, safe fallback) that FEED the existing
authority — never pre-baked MIDI bypassing it. Density limits, overlap resolution,
seek/replay semantics are compiler responsibilities, evaluated first in shadow mode.

## 3. What is REJECTED (settled; do not re-propose without new evidence)
1. Universal audio event graph / universal ontology / cross-family confidence.
2. One universal model inferring identity AND lighting warrant.
3. Plugin framework, base classes, generic detector contract ahead of two families.
4. Passive-use-as-concept-truth (silence ≈ approval; veto ≈ hearing label).
5. Six expert heads built as a platform; multi-encoder + multi-seed ensembles in the
   first bake-off; disagreement presented as calibrated confidence.
6. DETR-style span training at current label counts.
7. Separator-extracted exemplars as clean training truth; commercial sample packs
   WITHOUT explicit ML-training rights as training data.
8. Synthetic-holdout success presented as natural-transfer proof.
9. Real held-out recall / confidence calibration / false-cues-per-hour claims from
   passive, non-exhaustive evidence.
10. Per-stab LIVE timing promises before end-to-end measured proof (§8 gates).
11. Threshold-search revisions of v2-style detectors on the same 48 labels.

## 4. What is DEFERRED (with explicit reopen conditions)
- Query-conditioned separation (SAM Audio / CLAPSep / Banquet class): reopen only when
  (a) a locked raw+stem event-local error set shows a specific confusion separation
  could resolve, (b) a named checkpoint passes modality, artifact, license, 8 GB memory,
  and speed gates on this Mac or an operator-approved external GPU, (c) scope remains
  candidate-window-only, and (d) the frozen challenger beats raw mixture + four stems on
  that locked error set by a predeclared margin without inventing target energy,
  worsening original-mixture timing, or costing more wall time than its gain justifies.
  Until then: stems + mixture only.
- Direct set/span prediction: reopen only after exemplar/frame similarity and one tiny
  cached-frozen-feature head fail specifically on overlapping/multiple-event assignment
  and thousands of in-domain strongly labeled spans exist. A failed tiny head does not
  authorize DETR to "try harder."
- M2D-CLAP: evaluation-license research challenger only; enters a bake-off only after
  the MERT-vs-MuQ winner exists and only if license/use permissions are frozen first.
- Full synthetic-data generator platform: only after the two-family transfer probe
  (§6) passes.
- Motif/gesture specialists; second encoder; confidence calibration; shadow
  false-cues/hour; runtime promotion; hardware validation — each behind its named gate.
- External GPU: not required for any currently authorized stage; becomes a question
  only if the §6 probe passes and scale-up is operator-approved.

## 5. Stage-3 embeddings discipline (restated, unchanged)
MERT-v1-95M vs MuQ, mixture audio, frozen final hidden state, predeclared pooling,
lineage-excluded retrieval, support floors frozen in grouped folds, ONE winner (or
NEITHER — deletion on failure is a designed outcome), Mac cost gates, CPU/device
stability gates. The QbE interaction contract does NOT depend on embeddings winning:
if Stage 3 rejects both encoders, multi-view retrieval proceeds on engineered
DSP/stem views alone.

## 6. The synthetic-augmentation pathway (addendum-2's surviving bet, gated)
CLAIM under test: exact-boundary synthetic supervision (isolated exemplars inserted
into real library backgrounds with production-realistic rendering) can harden concept
detectors without operator labeling. Honest split of that claim: fixtures/augmentation/
pretraining = likely useful; material transfer to naturally PRODUCED events = unproven
(the seam-shortcut risk is the central danger: a model can learn the rendering recipe,
not the sound).
THE TWO-FAMILY TRANSFER PROBE (predeclared; Sol-specified; the only authorized entry):
1. Freeze event-local real positives + hard negatives from ≥3 exact-byte lineages per
   family (one stab, one growl), presence-truth only; if existing text cannot supply
   unambiguous spans → stop INSUFFICIENT_EVIDENCE (never invent or request truth).
2. ≥3 isolated exemplars per family WITH explicit ML-training rights; no separator
   extraction in the primary arm.
3. Target-absent real backgrounds from ≥12 lineages; raw overlay + joint-bus +
   sidechain-shaped + occluded variants; frozen synthetic holdouts (1 exemplar, 4
   background lineages, 1 whole render chain).
4. Equal-count SEAM CONTROLS: identical insertion/render with silence, phase-scrambled
   target, and near-miss non-targets.
   All train/test splits are grouped by exemplar source, background lineage, declared
   artist/remix family, separator version where used, and render recipe; no such group
   crosses train/test.
5. Exactly three systems compared on shared candidate windows + the same raw-mixture
   boundary refiner: (i) existing v5 mechanics, (ii) frozen exemplar similarity,
   (iii) ONE tiny frozen-feature head trained on synthetic renders. No DETR, no
   separation, no ensembles, no per-track tuning.
6. Report synthetic F1/boundary error; real pairwise concordance + P@K on known spans;
   same-artist/other-context ranks; seam-control fire rate; time/RSS/cache. NEVER real
   recall, calibration, or false-cues/hour.
STOP RULE (predeclared): abandon the synthetic-grounding/direct-span/ensemble roadmap
if both families reach ≥0.80 synthetic event-F1 yet fail to beat the v5/exemplar real
ordering by ≥0.05 absolute, or real concordance ≤0.55, or seam-control fire rate ≥10%.
One family passing → keep only that family's method; the universal architecture is
rejected. The tiny head failing → DETR is NOT authorized to "try harder".
TRANSFER GATE for any later synthetic-trained component (research gate): the upper 95%
CI bound of (synthetic - real) metric is at most 0.10 absolute AND the lower 95% CI bound
of the real result beats the simplest accepted no-synthetic baseline by at least 0.05;
boundary median error is no worse than the raw-mixture refiner and no more than 2 times
the synthetic error. A synthetic-real gap from 0.10 through 0.15 is INCONCLUSIVE. Reject
transfer if the lower 95% bound of real degradation exceeds 0.15, the real result fails
to beat the no-synthetic baseline, or seam controls show material activation.

## 7. Validation doctrine (what may ever be claimed)
- Measurable today: descriptive retrieval P@K on structured known spans; pairwise
  concordance; timing error where authored spans exist; synthetic holdout metrics
  (labeled synthetic); shortcut probes (same-artist-without-sound,
  sound-outside-drop, other-genre similars, stem corruption) as rank-shift reports.
- Not measurable without future exhaustive truth: real recall, calibrated confidence,
  false cues per hour. Claiming them is a review-blocking defect.
- Isolation honesty: exact-byte lineage isolation is stated as such until a
  near-duplicate/edit/remaster audit exists; artist/production-family isolation is a
  stress test, not a default claim.
- Retrieval isolation and shortcut discipline: before any generalization claim,
  fingerprint and group near-duplicates, edits, remasters, and declared remix/mashup
  families; state exact-byte-only limits; and, where metadata permits, run
  leave-artist/producer/release-family-out stress tests, codec/loudness-matched controls,
  same-genre hard negatives, same-track negatives, and production-style twins. Report
  results with and without those nuisance groups. Embedding pilots also test sharp- vs
  soft-attack twins, same pitch/different roughness, same roughness/different pitch,
  same-artist target-absent windows, the same target across artists/masters, and within-
  beat time shifts. If a simple descriptor wins, keep it.
- Every promotion path ends in ONE chronological locked-future evaluation on evidence
  never touched during development, per family, per concept.

## 8. Runtime and hardware gates (far end; unchanged in spirit, made explicit)
No v5+ result influences live lighting until ALL of: separate reviewed integration
spec + change contract; immutable schedule identity (content/grid/detector/policy/
compiler hashes); async load outside the push loop with fallback-to-current-behavior;
seek/loop/hot-cue/pitch/deck-switch/stop-resume/stale-position/duplicate-cue/
schedule-version tests; end-to-end MEASURED timing
(intended event → decision log → wire → visible fixture; median/p90/p99 + misses,
per backend, under show-like load) against an operator-defined visible tolerance;
supervised safe-rig validation; default-off rollout; operator acceptance. Offline
timestamp precision (Stage-1 p90 8.5 ms) is never cited as live firing precision.
Any backend timing offset may be applied only if its delay is measured and stable. With
the feature disabled or a schedule missing/stale/hash-mismatched, SoundSwitch, lasers,
LEDs/Govee, Rekordbox reader state, blackout/emergency behavior, and bridge logging
remain unchanged.

## 9. Program roadmap from today (each step separately authorized)
Every stage's own spec freezes wall-time, RSS, cache, artifact-retention/invalidation,
and operator-attention budgets before work begins. Exceeding a budget stops that branch;
it does not justify hidden platform work.
R0. Finish the 721-track Stage-2 sweep (running; untouched by this document).
R1. Growl scorer to READY → build → THE LIST (deliverable #1). Bounded forever.
R2. A family-local sustain_v1 export from R1 artifacts (mini-spec; renames + one export;
    no concept registry, scorer behavior change, or shared-contract freeze).
R3. One-concept QbE micro-experiment on growls: use only pre-existing volunteered or
    corrected event-local truth from at least 3 exact-byte lineages; freeze one query
    exemplar, one same-track hard negative, and positives/negatives on at least 2 other
    lineages; request no new judgments and surface no labeling offers. Report only
    descriptive pair ordering/P@K and sample-clock start error where exact prior spans
    exist. Stop INSUFFICIENT_EVIDENCE if that ledger cannot be formed. Falsify the
    experiment if positives do not outrank same-track and cross-track hard negatives,
    results cluster by artist/mastering, or success requires per-track tuning.
R4. Stage-3 embeddings pilot (MERT vs MuQ) per §5.
R5. impulse_v1 offline experiment (Stage-1 evidence, stab concepts); THEN freeze the
    shared event envelope and extract the minimal concept records/registry from what
    sustain_v1 + impulse_v1 actually share.
R6. Two-family synthetic transfer probe (§6) — the addendum-2 bet lives or dies here.
R7. Presence-confirmation offers UX (operator-gated) + passive accrual per the unlock
    schedule; auto-import watcher spec (already operator-ruled: build after the list).
R8. Offline cue compiler in shadow mode for ONE concept; density/conflict metrics.
R9. Locked-future gates → runtime integration spec → hardware timing validation →
    operator live approval. Nothing skips a step.

## 10. Falsifiers for the whole direction (standing stop rules)
1. R3/R4: retrieval clusters by artist/mastering after isolation work AND engineered
   views also fail → the similarity premise dies; program remains deterministic
   detectors + evidence cache (still valuable; deliverable #1 unaffected).
2. R1 diagnostic ≈ chance concordance on the 48 → Stage-2 evidence insufficient for
   even the flagship concept; rebuild evidence before any platform work.
3. R5/R6 two-family results share only boilerplate → no platform layer; independent
   tools over the common store.
4. §6 stop rule fires → synthetic pathway dies; retrieval + mechanistic detectors
   remain the roadmap.
5. Passive accrual never approaches unlock counts → concepts stay
   provisional/retrieval-only indefinitely (accepted outcome; the operator's manual
   scripting path remains).
6. Live timing gates unachievable within the operator's visible tolerance → offline
   intelligence still serves scripted/prep workflows; live per-event firing is dropped.
7. Per-axis cost cannot be amortized on this host, or explicit corrections do not
   converge and review burden exceeds direct scripting → stop expanding that concept;
   keep the deterministic/manual path.
8. Acoustic presence and lighting warrant remain too weakly related for a context policy
   to beat explicit/manual choices → do not learn warrant; operator policy remains final.
9. Query-conditioned separation fails to improve locked mixture/four-stem errors within
   budget, or invents/smears target energy → reject the separator branch.
10. Shadow cue schedules produce unacceptable density, conflicts, or presentation errors
    on available explicit evidence even when detection is correct → do not promote that
    concept to runtime.

## 11. Confidence ledger (reviewer priors, not measured probabilities)
These values are subjective reviewer priors, not confidence intervals, calibrated
probabilities, or benchmark truth. They remain separate because averaging them would
create a number neither reviewer gave. Agreement on this architecture means the document
faithfully states the gated program; it does not prove that every research bet will pass.

| claim | Fable prior | Sol prior |
|---|---:|---:|
| reconciled direction | about 75-80%, later about 80% with the gated synthetic pathway | no merged reconciliation probability; addendum-1 direction 62%, addendum-2 broad direction 58% as written |
| identity / timing / warrant separation | about 95% | 99% |
| high-resolution raw timing refinement | about 90% | 98% |
| stems are auxiliary, not truth | about 90% | 99% |
| QbE as an interaction contract | about 95% | 65% |
| few examples + hard negatives make useful detectors | 60-75% | 35-55% |
| embeddings improve retrieval | about 70% | 45-60% |
| query-conditioned separation adds useful evidence | 40-55% | 20-40% |
| passive actions teach presentation | about 70% coarse / about 30% fine | 15-30% overall |
| one example generalizes an arbitrary concept | below 25% | 5-15% |
| synthetic training materially improves natural cross-production detection | 55-65% | 30% |
| synthetic fixtures / augmentation / pretraining help | not separately scored | 70% |
| one universal model infers identity and warrant | very low | 1-5% |
