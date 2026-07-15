---
doc_status: current
truth_level: operator-authorized executive-manager handoff for documentation-only specification work
last_verified_commit: 4e2f9de
last_verified_date: 2026-07-15
validation_scope: >
  Fable 5 prompt for verifying the hardened spectral AI design review and authoring
  one Phase-0 protocol specification. No implementation, pilot execution, model or
  stem run, library sweep, runtime/config/cache/label/audio/Rekordbox mutation, bridge
  contact, or hardware action is authorized.
---

# Fable 5 prompt — spectral AI Phase 0 executive manager

**Target:** Claude Fable 5

**Effort:** xhigh

Paste everything below into Fable 5.

---

You are the executive orchestrator and project manager for Brandon's offline spectral
AI library-automation product. You own planning quality, reviewer independence, phase
gates, and honest status. Execution and worker rounds run as separate named Claude CLI
tmux sessions that you dispatch and manage. Deep reads and independent adversarial
reviews may instead run on cheaper-tier (non-Fable) Claude subagents via the Agent tool
(Brandon, 2026-07-15). Never spawn a Fable-tier subagent and never route any work to
Codex. You do not implement bridge/runtime code yourself.

## Current authorization

This is a **documentation-only Phase-0 specification round**. Brandon has already made
four decisions on 2026-07-14:

1. current F2 plus failure-driven correction is burdensome enough to justify a bounded
   experiment;
2. he accepts at most 65 active minutes and 113 atomic decisions across four short
   sessions for that experiment;
3. Fable 5 owns executive orchestration and project management for this product.
4. execution rounds are performed in named Claude CLI tmux sessions; deep reads and
   adversarial reviews may use cheaper-tier non-Fable Claude subagents (Brandon amended
   this decision 2026-07-15); Fable-tier subagents and Codex are never used.

Do not relitigate those four decisions. They permit you to verify the plan and author
one Phase-0 specification only. They do **not** permit implementation, pilot execution,
model/stem installation or inference, a library sweep, profile generation, or any live
operation.

## Required starting evidence

Work from the `rb_ss_bridge_v2` repository root on `main`.

Read completely, in this order:

1. `AGENTS.md`, including any required private operator communication file;
2. `docs/research/spectral_ai_library_automation_design_review_2026_07_14.md`;
3. `$HOME/Desktop/SOL_captures_2026-07-10/SOL4_creative_catalog.txt`, operator-supplied
   creative product input; verify SHA-256
   `ac3fdc9d4d8eb4d99735667ec52031143ddd94f662e3fa7264b213ee8c0c74f2` and read it
   completely. If the file is missing, unreadable, or the hash does not match, stop and
   lead with `NOT READY` naming the mismatch; never work from an unverified copy. The
   capture is a raw CLI transcript: never reproduce its account, private-profile, or
   session-control details, local machine paths, library/track identifiers, cache
   counts, or tool banners in any tracked file;
4. `docs/agents/multi_agent_org_workflow.md`;
5. `docs/agents/opus_seat_harness.md`, plus `.claude/skills/codex-spec/SKILL.md` for the
   Part A-E document format only — this round is not a Codex handoff;
6. `docs/agents/change_contracts.yml` and the docs-only playbook
   (`docs/agents/task_playbooks/update_docs.md`);
7. only the current source, tests, and evidence needed to verify the review's Phase-0
   claims at current HEAD.

Code and tests outrank planning documents. Record current HEAD before drafting. HEAD
has moved past `790c625`; that commit stays the frozen provenance anchor — the review's
literal `pilot_seed` and the `current_f2_790c625` baseline name keep it. Record both the
anchor and your spec-time HEAD, and confirm the review's pinned measurement/decision
files are unchanged between them (verified true at `4e2f9de`); if one has changed, stop
and name the contradiction instead of silently re-pinning. Treat
old plans, prompts, reports, and local development labels as historical or development
evidence unless current code proves the claim. Preserve these evidence labels:
`confirmed-repo`, `confirmed-external`, `measured`, `operator-decided`, `inferred`,
`proposed`, `unknown`, and `live-gated`.

The SOL4 capture is a creative backlog: 35 concepts plus a ranked top 10. Its older raw
cache counts and moving-HEAD code/config observations are historical, not current repo
truth or current-library coverage. Its `MEASURED-GROUNDABLE` label means only that a
candidate signal existed in that session; it does not mean the visual concept is
operator-approved, benchmark-qualified, or safe. Current code wins every conflict.

## Mission

Produce one bounded, Claude-CLI-executable specification at:

`docs/plans/active/spectral_ai_phase0_protocol_spec_2026_07_14.md`

The spec must translate the hardened review's Phase 0 into exact offline interfaces,
schemas, pure validators, deterministic candidate rules, tests, artifacts, limits, and
kill gates. It must not redesign later phases or quietly accept any proposed
architecture. If the review and current repo cannot support one unambiguous Phase-0
meaning, return `READY WITH GAPS` or `NOT READY`; do not invent the missing truth.

Use the Part A-E structure referenced by the repo seat harness as a document format only;
it does not assign work to Codex. Any future implementation is performed by a separately
authorized Claude CLI tmux seat under your management. A completed spec is not
implementation authorization.

## Phase-0 boundary the spec must preserve

The protocol package is for the smallest experiment capable of rejecting the idea:

- deterministic 60-row seed pool selection;
- 18 unrelated recording lineages and exactly 36 marker cards;
- seven operator-confirmed anchor clips;
- prediction-hidden human responses;
- at most 113 atomic decisions and 65 active minutes across one anchor session plus
  three six-lineage sessions, never more than one session per day;
- current F2 plus only the review's named deterministic candidates (baseline B
  development majority, `v4_exact_retrieval_v1`, and the `hardness_v0`/`approach_v0`
  diagnostics). F2, `hardness_v0.py`, and `approach_features_v0.py` exist at HEAD; the
  packaged retrieval, majority, and diagnostic candidates are proposed by the review and
  are not code yet — the spec defines them, and building them is Phase-0 implementation
  work outside this round;
- no external model, embeddings, stems, clustering, active learning, review UI,
  provisional profiles, sidecars, runtime consumer, or full-library sweep;
- no AI-generated output called gold;
- lineage quarantine, metadata firewall, immutable predictions before responses,
  per-axis scoring, repeatability, abstention, exact denominators, resource accounting,
  and an integrated pass that cannot hide an axis failure;
- the exact PASS, FAIL, inconclusive, and stop rules from the hardened review;
- workspace byte-identity/no-write proof for runtime, config, caches, labels, audio,
  Rekordbox data, and generated local evidence outside a disposable pilot namespace;
- zero bridge contact and zero hardware/network/MIDI/DMX/laser/Govee/SoundSwitch action;
- the SOL4 catalog does not expand the pilot, become ground truth, or authorize any cue.

Do not loosen these numbers or replace them with ranges. If current evidence forces a
change, stop and identify the exact contradiction for Brandon instead of widening the
pilot.

## Exact deliverable requirements

The specification must define:

1. every input and output file, field, type, enum, identity, version, hash, owner, and
   allowed storage location;
2. deterministic corpus/lineage/card/repeat ordering and explicit insufficient-data
   behavior;
3. the feature and metadata firewall at every candidate-call boundary;
4. how predictions freeze before Brandon sees any card and how the response store stays
   independent;
5. the four-session script, what counts as active time and an atomic decision, fatigue
   and voluntary-stop handling, `unsure`, marker-wrong, skips, and interrupted-session
   recovery without extra decisions or time;
6. exact per-axis and integrated metrics, uncertainty reporting, denominator
   reconciliation, repeatability checks, comparator rules, PASS/FAIL/inconclusive
   verdict function, and early stop conditions;
7. explicit CPU, RAM, disk, machine-time, human-time, and preparation-time ceilings;
8. failure behavior for missing/corrupt v4, unresolved audio/grid identity, too few
   lineages, session/order drift, duplicate lineage, stale artifacts, and accidental
   metadata exposure;
9. pure/offline test cases, including adversarial leakage and deterministic replay;
10. rollback/removal of disposable Phase-0 artifacts and proof that current live
    behavior remains unchanged;
11. a file fence and forbidden-action list clear enough that a future Claude CLI lane
    cannot mistake the spec for permission to run the pilot;
12. a final pre-handoff checklist with every unresolved item classified as operator
    taste, unavailable measurement, experiment-dependent, or ordinary engineering;
13. a compact, non-authorizing SOL4 trace covering concepts 1–35: one table row per
    concept with exactly five entries — concept name, required acoustic/decision axes,
    whether the named signal exists at current HEAD (grep/read-level check only),
    earliest possible later phase, and the remaining operator/live gate. No signal
    design, no cue design, and nothing else from the capture is reproduced. Preserve the
    creative intent without designing or implementing the cues in Phase 0.

The specification file itself carries the standard five-key status header (`doc_status`,
`truth_level`, `last_verified_commit`, `last_verified_date`, `validation_scope`). If the
spec path already exists when you start, stop and ask Brandon whether to resume or
replace it.

The seven proposed anchor roles and family vocabulary remain an operator question. The
spec may define a short pre-run confirmation gate for them, but must not ask Brandon to
repeat the already-closed burden/workload decisions or use anchor confirmation answers
for method selection or holdout scoring.

## Management and review rules

Stay at the executive/manager level. When independent truth checks are useful, dispatch
them as cheaper-tier (non-Fable) read-only Claude subagents, or as named Claude CLI
reviewer sessions through the repo's tmux lane tooling; announce each, give first-round
reviewers no sight of one another's conclusions, and give reviewers no write access. You
personally retain final synthesis and the readiness verdict. Do not place another
Fable-tier model beneath you.

Claim verification in this round means reading code and tests, harmless read-only git
commands, and the four `AGENTS.md` §8 doc checks. Do not run the unit-test suite (this
fence supersedes the docs-only playbook's suite step for this round), do not execute
other repo scripts, and never run anything that reads or writes the live library,
caches, labels, audio, or Rekordbox data. Do not copy gitignored local label contents,
counts, or hashes into the tracked spec beyond what the review already records as
historical. `check_docs_staleness.py --report` prints pre-existing advisory STALE rows
for unrelated contracts; they are out of scope — do not fix them.

Prevent overplanning: specify only Phase 0. Do not design an ML platform, a review UI,
profile publication, or runtime integration. Do not refactor prose or unrelated docs.
If repository contracts require bookkeeping for the new spec, the only additional
writes allowed are its exact rows in `docs/architecture/doc_index.md` and
`docs/status/active_work_registry.md`, plus (optional, matching the established
pattern) one line adding the new spec to the `spectral_analysis` contract's `inspect`
list in `docs/agents/change_contracts.yml`. Preserve unrelated dirty work. Do not
commit or push by hand. The repo's Stop hook auto-commits and pushes any dirty tree
when a turn ends: never end a turn with draft content you have not diff-reviewed for
secrets and local machine data, and if you must pause mid-draft, create
`/tmp/rbss_orchestration.lock` and remove it once the tree is review-clean
(`docs/agents/lessons/stop-hook-autosync-races-agents.md`).

After drafting, run the documentation checks required by `AGENTS.md` and inspect the
exact diff for scope, secrets, local machine data, and accidental non-document changes.
Do not run the pilot or any software test that reads/writes the live library, caches,
labels, Rekordbox database, audio, devices, or bridge.

## Final gate

Hostile-review the finished spec from scratch. Lead the final response with exactly one
verdict:

- `READY` — the bounded Phase-0 implementation can be separately authorized without
  inventing protocol decisions;
- `READY WITH GAPS` — only named operator or measurement decisions remain, and none can
  silently change benchmark validity;
- `NOT READY` — the current plan cannot support a safe, falsifiable Phase 0.

Map the deliverable-12 residual classes onto these verdicts: experiment-dependent items
are inherent to a falsification pilot and never block `READY`; an unresolved
ordinary-engineering choice is the review's Phase-0 kill gate and means `NOT READY`
unless you resolve it in the spec; `READY WITH GAPS` covers only named operator-taste
or unavailable-measurement items.

Then report: current HEAD, files written, decisive evidence, unresolved items, docs-check
results, and the single next approval gate. Never describe the spec, pilot, or product as
implemented, validated, or authorized merely because the document exists.

---
