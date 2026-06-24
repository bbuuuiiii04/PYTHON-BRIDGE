---
doc_status: active-review-prompt
truth_level: review-instructions-grounded-in-current-roadmap
last_verified_commit: f6910f9
last_verified_date: 2026-06-24
validation_scope: Opus adversarial review of SoundSwitch exporter remaining-work roadmap; review-only; no live/runtime mutation
---

# Opus adversarial review prompt - SoundSwitch exporter roadmap

Current-code note: RW-5 copied operational status and the hardware procedure/template were added
after this review brief was authored. This remains review-only and is not current implementation or
hardware evidence.

You are the independent adversarial reviewer for the SoundSwitch exporter and
bridge-native DMX roadmap in `/Users/bbui/rb_ss_bridge_v2`.

This is a **review-only** task. Do not implement fixes, edit files, change
configuration, mutate the saved SoundSwitch project, start/restart/stop the
bridge, append runtime commands, open MIDI/serial/Enttec/DMX devices, or perform
fixture-visible testing. You may run read-only inspection and offline tests that
write only to `/tmp`.

Your job is not to approve the roadmap because it is detailed. Try to disprove
it. Find every material overclaim, missing work item, wrong dependency,
incorrect completion mark, unsafe transition, stale code anchor, incomplete
test gate, and documentation-lifecycle problem.

## Primary artifact under review

```text
docs/plans/active/soundswitch_exporter_remaining_work.md
```

The roadmap claims to be the single active landed-versus-remaining authority.
Treat that claim as unproven until current executable evidence supports it.

## Required source order

1. Read `AGENTS.md` completely and `PRIVATE_OPERATOR_PROFILE.md` if present.
2. Read the roadmap under review and
   `docs/plans/active/soundswitch_README.md`.
3. Read `docs/agents/change_contracts.yml`, especially
   `soundswitch_pack_player`, `soundswitch_research`, `runtime_commands`, and
   `docs`.
4. Inspect current executable code and tests named by each roadmap claim.
5. Inspect the tracked example config and current runtime command/status
   surfaces.
6. Read current research authority through
   `docs/research/soundswitch/README.md`; do not use files under `history/` as
   current truth.
7. Inspect T7d conductor summaries and validation ledgers. Raw ignored captures
   may be inspected read-only, but never quoted with private paths or content.
8. Only after code/tests/config/runtime evidence, consult completed plans as
   historical context.

Code and tests beat docs. Re-resolve all line anchors at the current HEAD.

## Baseline claims you must independently verify

Do not assume these are correct merely because the prior audit reported them:

- branch/head and worktree scope;
- current saved-project proof: 29 PASS / 0 FAIL / 0 INCOMPLETE;
- 42/42 Autoloops, 44/45 scripted files, 32/32 active existing-path scripted
  tracks, 19/19 IAC bindings, 32 Static Looks, DDJ slots 8/16/17/24, 232+1
  Venue records, and the 166-cue union;
- deterministic 95-artifact pack and independent verification;
- exporter performs a complete rescan but rejects an existing destination;
- no menubar `Export from SS` action or export/reload transaction exists;
- config/startup/controller/StateManager/backend/Enttec wiring exists and is
  default-off;
- direct DMX and physical MIDI are mutually exclusive in construction and port
  ownership;
- pure scripted rendering is complete for current active content;
- live scripted runtime still has pause-vs-stop, explicit mode-authority,
  controller-health, and operational-status gaps;
- T7d conductor reports arm 2 ACCEPTED / 1 FAIL and refire 2 ACCEPTED, with four
  scenario pairs and the unique oracle still missing;
- `StateManager` never selects native Autoloop output;
- local pack config and hardware validation are absent.

If any claim is only partially supported, downgrade it explicitly. Passing
tests are evidence only for the behavior they actually cover.

## Adversarial review questions

### A. Product boundary and operator workflow

- Does the roadmap faithfully encode the operator requirement: save in
  SoundSwitch, click one menubar button, replace one stable pack location, and
  explicitly reload when possible?
- Does it correctly distinguish a stable pack *directory* from the operator's
  phrase “one file,” without silently redesigning the format or accumulating
  exports?
- Are unsaved SoundSwitch state, concurrent source drift, wrong project/version,
  unsupported active content, and no-watcher boundaries explicit and correct?
- Is the stated completion definition sufficient to call the full project
  complete, or are importer/authoring/runtime behaviors missing?

### B. Export/publish/reload transaction

- Confirm current `export_pack()` safety and its exact limitation for an
  existing non-empty destination.
- Attack RW-1 for crash windows, symlink/path attacks, cross-filesystem behavior,
  directory fsync semantics, concurrent clicks/processes, stale locks, cleanup
  failure, old-pack preservation, and first-export versus replacement paths.
- Challenge the assumption that disk publication and runtime reload can be
  safely sequenced. What happens when publish succeeds but command append,
  acknowledgement, load, input start, or sender start fails?
- Does the roadmap require a real acknowledgement/correlation mechanism, or
  could the menubar falsely report success after merely appending a command?
- Does any proposed result accidentally enable output, change backend, start or
  restart the bridge, or open hardware?

### C. Scripted runtime completeness

- Trace a real event path from track load and filepath resolution through
  `scripted_id`, `soundswitch_id`, lighting mode, transport, position freshness,
  player selection, frame submission, and safe zero.
- Verify whether `PAUSE` is truly indistinguishable from stop in the current
  driver and whether the pure player's paused support is usable live.
- Look for additional gaps beyond the four listed: end-of-track, unload,
  ambiguous authority, seek/backstep thresholds, deck/master transitions,
  position-source recovery, metadata replacement, reload wait, sender failure,
  exception latching, shutdown ordering, emergency masking, or stale cached
  state.
- Determine whether manual Static Override policy and blackout/emergency
  precedence are accurately described and fully wired.
- Determine whether MIDI input health/drop/error fields are sufficient for the
  proposed fail-to-zero policy or whether the roadmap is missing state/latch
  design.

### D. Native Autoloop/T7d evidence boundary

- Independently run `python3 tools/t7d_capture_conductor.py summarize-corpus`.
- Verify that conductor `ACCEPTED` proves integrity only, not phase correctness
  or physical fixtures.
- Inspect accepted summaries/traces for project hash, frame count, marker,
  footer, drops, playing span, BPM, identity fields, and segmentation issues.
- Challenge whether two accepted arm/refire runs are truly usable oracle
  segments; do not promote them if identity ownership or track changes are
  ambiguous.
- Verify the four remaining scenario pairs and coverage requirements.
- Attack the oracle gate for circular 600 assumptions, free offsets,
  scale/quantizer/origin aliasing, insufficient discriminating transitions,
  cross-validation leakage, clock alignment, multi-deck contamination, and
  holdout validity.
- Confirm the roadmap prohibits writing a runtime spec or selecting a phase
  constant before a unique corpus verdict.

### E. Runtime and hardware safety

- Trace every claimed nonblocking boundary. Confirm no planned filesystem,
  subprocess, status-provider, MIDI, serial, socket, sleep, retry, or contended
  lock enters the 200 Hz push loop.
- Verify exactly where direct DMX and physical MIDI are mutually exclusive and
  whether any reload/startup failure can violate that invariant.
- Attack graceful zero/stop assumptions, including Enttec last-frame behavior on
  process death or `kill -9`.
- Confirm local config, fixture map, controller aliases, Enttec port, physical
  kill method, and repeatable hardware evidence are honestly unvalidated.
- Check that the roadmap requires explicit operator approval immediately before
  every restart, enable, device open, or fixture-visible test.

### F. Roadmap structure and sequencing

- Are RW-1 through RW-11 complete, non-overlapping, and dependency ordered?
- Is RW-1 really the safest/highest-value next design task, independent of T7d?
- Should RW-2 through RW-5 be one spec or separate reviewable specs?
- Are any tasks marked done based only on a narrow proof gate or historical
  review?
- Does each milestone have a falsifiable entrance gate, exit gate, rollback, and
  required docs/tests?
- Does the roadmap identify Python-version/CI compatibility and all change
  contracts that implementation will trigger?

### G. Markdown authority and lifecycle

- Verify the physical organization matches the declared lifecycle:
  - current planning under `docs/plans/active/`;
  - material implementation history under
    `docs/plans/completed/soundswitch/`;
  - current research authority in `docs/research/soundswitch/`;
  - superseded research drafts/handoffs in
    `docs/research/soundswitch/history/`;
  - current prompts only under `docs/prompts/active/` or
    `docs/prompts/reviews/`.
- Find broken references to deleted prompts or pre-move paths.
- Verify compatibility pointers are justified and do not masquerade as active
  authority.
- Identify duplicate or conflicting current status statements outside the
  roadmap.
- Confirm deleted prompts contained no unique safety constraint or unresolved
  requirement that failed to migrate into current authority.

## Offline verification you may run

Use the smallest set needed to substantiate findings. Allowed examples:

```bash
git status --short
git rev-parse --short HEAD
rg ...
python3 tools/t7d_capture_conductor.py summarize-corpus
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

You may rerun focused unit tests or the current-project proof into `/tmp` if the
local project is present. Do not treat an unavailable optional project/capture
as a pass. Do not write proof artifacts into the repo.

## Required review output

Return the review in chat. Do not edit the repo.

### 1. Verdict

Choose exactly one:

- `ACCEPT` - no material correction is required before using the roadmap;
- `ACCEPT WITH REQUIRED CORRECTIONS` - the roadmap is usable only after listed
  corrections;
- `REJECT` - its authority/completeness/order is materially unreliable.

State whether RW-1 is ready for Opus design/spec after those corrections.

### 2. Findings, severity first

List `CRITICAL`, `HIGH`, `MEDIUM`, then `LOW`. For each finding provide:

- exact file/symbol/line or command evidence;
- the roadmap claim challenged;
- why the evidence contradicts or fails to prove it;
- concrete required correction;
- live/runtime risk if left unchanged.

If there are no findings at a severity, omit that heading. Do not use “looks
good” or generalized praise as evidence.

### 3. Claim audit

For every completion-matrix row classify the roadmap claim as:

- `PROVEN`;
- `PARTIAL`;
- `CONTRADICTED`;
- `UNKNOWN`.

Name the strongest evidence and missing evidence. Pay special attention to the
difference between content exportability, pure rendering, live scripted
behavior, wire captures, and physical fixtures.

### 4. Missing-work and dependency audit

Return an exact list of missing roadmap items, wrongly combined tasks, wrongly
ordered dependencies, and acceptance gates that cannot falsify failure.

### 5. Documentation-organization audit

Report broken links, misclassified active/completed/history files, deleted
prompt constraints that were not migrated, duplicate authorities, and any file
that should move or be removed.

### 6. Required roadmap patch list

Give a minimal, line-addressable correction list. Do not rewrite the whole
roadmap unless its structure is unsalvageable.

### 7. Operator closeout

Explain in plain language:

- what the finished bridge is supposed to do differently;
- what must remain unchanged;
- how healthy export/scripted/Autoloop behavior would be recognized;
- what to watch in SoundSwitch, lasers, LEDs/Govee, Rekordbox state, and logs;
- what remains software/wire-only versus hardware-unvalidated;
- every exact approval gate required before live operations.

## Non-negotiable review standards

- No assumption is upgraded because it is plausible.
- No test result is generalized beyond its test surface.
- No passive Art-Net capture becomes physical fixture evidence.
- No historical prompt/spec becomes current authority.
- No absence of a failing test proves behavior complete.
- No T7d phase value/origin is chosen during review.
- No implementation or live mutation is authorized by this prompt.
