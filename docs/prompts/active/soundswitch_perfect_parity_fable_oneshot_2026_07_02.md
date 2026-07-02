---
doc_status: active-prompt
truth_level: current-evidence-packet-grounded
last_verified_commit: ca365dc
last_verified_date: 2026-07-02
validation_scope: Fable 5 one-shot implementation-authorized handoff for SoundSwitch exporter/runtime software-side finalization. Supersedes docs/prompts/active/soundswitch_truth_exam_fable_fix_prompt.md for this workstream. No hardware validation performed by Fable; hardware gate is Brandon-owned and out of Fable's execution authority.
---

# Fable Prompt: SoundSwitch Exporter + DMX Pack Runtime — One-Shot Finalization

Target model: Claude Fable 5
Effort: xhigh

You are Fable 5 working from evidence in `/Users/bbui/rb_ss_bridge_v2`.

## Mission

Diagnose and close every remaining software-side gap between the SoundSwitch exporter/DMX
lighting pack runtime and SoundSwitch's own output, then implement the fixes yourself
(directly, and by delegating the expensive implementation subtasks to your own
subagent(s)), so the runtime is ready for Brandon to run one final live hardware
validation pass and have it fully pass.

This is a one-shot handoff. There is no back-and-forth with Brandon mid-task. Use the
evidence packet below, verify it, act on it, and produce a finished, working result.

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge: an exporter/runtime
correctness and parity finalization task on a personal Python project. It is not a
cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry,
life-sciences, model-distillation, or hidden-reasoning extraction task. Treat all review
and implementation work as normal software correctness, testing, maintainability, and
runtime safety — nothing here is offensive-security or dual-use work.

## Why this matters

Brandon has been chasing SoundSwitch parity for a long time across multiple capture and
fix rounds. He needs one complete, decisive pass that actually finishes the software side,
not another round of partial discoveries or another spec that only describes the fix.
The only remaining step after your deliverable is Brandon personally running live hardware
validation once. He expects that run to fully pass based on your fixes and your reasoning
from the code and the existing captures.

## Special override — read before applying default repo conventions

This repo's normal rule is "Fable/Claude plans, Codex implements bridge code"
(`AGENTS.md` §0, and this repo's Fable-prompt policy). Brandon has explicitly authorized a
scoped override of that rule for this workstream only, in the same category as the
existing LED color-engine (M2.5) Claude-implementation exception. For this task:

- You are authorized to implement code directly and/or delegate implementation to your own
  subagent(s).
- You are authorized to edit files inside this repo's software surface (see Scope below).
- This authorization does not extend to any other workstream, and does not remove the
  live-safety invariants below.

This prompt **supersedes** `docs/prompts/active/soundswitch_truth_exam_fable_fix_prompt.md`
for the SoundSwitch parity workstream. That earlier prompt forbade implementation; this one
does not. Do not defer to the earlier prompt's "spec only" instruction if you encounter it.

## Deliverable

A finished, working SoundSwitch exporter + DMX lighting pack runtime with every
software-closable gap below resolved, such that:

1. All 14 rows of the completion-audit matrix in the evidence packet (full list below) are
   closed at the software/code level, or explicitly and individually justified as
   structurally impossible to close without hardware (only the Enttec/hardware row
   qualifies for this).
2. Relevant tests pass (`python3 -m unittest discover tests`) and the repo's hard doc/CI
   checks still pass if you touch docs (`tools/check_docs_metadata.py`,
   `tools/check_agent_contracts.py`, `tools/check_docs_drift.py`).
3. You provide Brandon a single final report: what changed, why, what evidence backs each
   fix, and your calibrated confidence that live hardware validation will pass — not a
   generic "looks good."

Do not stop at a spec or a plan. A document describing the fix is not sufficient — you must
make the code change.

## Perfect parity definition (Brandon's own words — do not redefine this)

"Bridge lighting pack perfectly mimics bridge + SoundSwitch runtime in every important
way." Operationalize this as: closing all 14 rows of the completion-audit matrix below,
at the value + timing level where applicable.

## Evidence packet

Primary evidence (read these first, in full):

- `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md` — live
  truth-check diagnostic evidence and the 14-row completion-audit matrix (near the end of
  the doc) that defines the target surfaces. Also documents a known comparator topology
  bug (see "Comparator note" below).
- `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md` — offline
  passive-capture timing report: scripted timing (436 boundaries, median 15.841ms, p95
  28.229ms, 5 over one 40ms wire frame), autoloop timing (1377 transitions, median
  14.682ms, p95 93.783ms, 230 over one 40ms wire frame), autoloop wrap timing, scripted
  handoff gaps, U1 zero-frame runs.
- `docs/plans/active/soundswitch_exporter_remaining_work.md` — current known remaining
  work items for the exporter.
- `docs/plans/active/soundswitch_perfect_parity_finisher_spec.md` — prior finisher spec
  work; treat as historical context to verify against current code, not as already-true.
- `local/soundswitch/rbss_canonical_pack/manifest.json` — current canonical pack state:
  SoundSwitch 2.10.3, universe 0, CH1-19, 42 autoloops, 45 scripted inventory entries, 233
  render cues/venue records, 32 static looks, active parity lanes
  `algorithm_generalized=67`, `oracle_proven=16`, `unverified_parity=0`; inactive lanes
  `algorithm_generalized=29`, `unverified_parity=6`.

Fuller capture evidence — do not assume the truth-exam doc's excerpts are the only
captures that exist:

- Brandon made multiple valid capture sessions beyond what is excerpted in the truth-exam
  doc. Only the very last capture attempt had SoundSwitch's own Art-Net output drop out
  mid-session, and that specific session was non-load-bearing extra coverage, not the
  primary evidence base. Do not treat "SoundSwitch wasn't emitting Art-Net" as true of the
  whole evidence base — it is true of one late, non-critical session only.
- Inventory and use whatever `/tmp/rbss_*` artifacts are still present on this machine
  (parity fixtures, capture JSON/JSONL files, project inventory dumps, lane-check exports,
  publish manifests, etc.) as additional live-captured ground truth alongside the repo
  docs above. Treat repo docs as the durable/primary source and `/tmp/rbss_*` files as
  supporting raw evidence — verify each `/tmp` file you rely on actually exists and is
  readable before citing it; do not assume file names from the doc excerpts still exist
  verbatim.

Comparator note (read this, then do not spend budget here):

- The official U0/U1 live comparator has a known topology bug: duplicate/interleaved U1 on
  loopback causes `missing_u0` / `sequence_gap:*` invalidity before byte/timing comparison
  can run. This is validation tooling, not the runtime under test.
- Brandon has explicitly decided not to allocate this task's budget to fixing the
  comparator/validation tooling itself. Do not attempt to fix the live comparator. Build
  your confidence from code review, the existing valid captures, and the offline
  time-domain evidence instead. If a fix to the runtime is impossible to verify without a
  working live comparator, say so explicitly as a residual risk rather than silently
  skipping it or silently trying to fix the comparator anyway.

## Evidence skepticism — do not blindly trust any single source

Brandon's explicit instruction: do not blindly trust the evidence packet, the canonical
pack manifest's self-reported lane numbers, prior spec/plan docs, or your own subagents'
reports.

- Treat every doc, manifest field, and `/tmp/rbss_*` artifact as a claim to verify against
  current code and against each other, not as ground truth by default. The manifest
  reporting `unverified_parity=0` on active lanes is itself a claim from prior tooling —
  confirm what that lane actually checked before treating "0 unverified" as "0 wrong."
- Actively look for contradictions between sources (e.g. a doc claiming a row is fixed vs.
  code that still shows the old behavior; two capture artifacts disagreeing with each
  other; a prior plan/spec claiming something is done that tests don't confirm). When you
  find one, resolve it by reading code and re-running verification, not by picking whichever
  source is more convenient.
- If a subagent you delegate to reports a fix as complete, do not accept that at face value
  — require it to show the test/check that proves it, and spot-check at least the
  high-severity ones yourself before including them in your final report.
- Use the `rejected` claim label in your final report for anything in the evidence packet
  or prior docs that you checked and found stale, wrong, or unsupported by current code —
  don't silently drop it, say what was wrong and what you found instead.

## Source-of-truth order

1. Current repo code and tests (`*.py`, `tests/`) — code wins over any doc below if they
   conflict.
2. `local/soundswitch/rbss_canonical_pack/manifest.json` and other current machine-generated
   artifacts you verify are current.
3. The evidence docs listed above.
4. `/tmp/rbss_*` capture artifacts, verified to exist before citing.
5. `docs/plans/active/soundswitch_perfect_parity_finisher_spec.md` and any other prior
   plan/spec/history docs — historical context only, re-verify every claim against current
   code before relying on it.

## Scope and forbidden actions

Allowed:

- Read and modify this repo's SoundSwitch exporter/runtime source, tests, and directly
  related docs required by this repo's change-contract rules
  (`docs/agents/change_contracts.yml`) for whatever you touch.
- Delegate implementation subtasks to your own subagent(s).
- Run the repo's offline test suite and any read-only or non-live analysis tooling already
  present in the repo (e.g. `tools/ssfmt/*`, `tools/prove_soundswitch_pack_generation.py`,
  doc-check tools) against existing captures/fixtures/exports.

Forbidden, no exceptions:

- Do not start, restart, or stop the live bridge process.
- Do not open, control, or send commands to SoundSwitch, Rekordbox, DDJ-800, MIDI/IAC
  ports, Enttec, or any other live/hardware device.
- Do not run a new live capture session or attempt to fix the live comparator topology.
- Do not perform the final hardware validation — that step is explicitly Brandon's, done
  after your deliverable.
- Do not touch `config/led_look_director.json.backup_1781599611`, commit secrets
  (`GOVEE_API_KEY`), local IPs, or device IDs.
- Do not create a new git branch; work on `main` per `AGENTS.md` §0 git workflow rules.

## Live-safety invariants your implementation (and any subagent's implementation) must not violate

These are hard invariants from `AGENTS.md` §6, verified at current HEAD — preserve them in
every change:

- `StateManager` remains the only writer of `DeckState` and owns the 200Hz push loop
  (`_TICK_INTERVAL = 1.0/200`); the push loop must gain no blocking network, socket, MIDI,
  filesystem, or subprocess I/O.
- Runtime mutations flow through immutable `BridgeEvent`s; reader threads publish
  events/snapshots and never mutate `DeckState` directly.
- `RBStateReader._tick_deck()` must keep enqueuing `ANLZ_PATH` before `TRACK_LOADED`.
- Memory play bits must not override `DeckState.playing` directly; direct flags alone must
  not circumvent TL logic.
- Scripted/autoloop arm, clear, BPM, beat, elapsed, and beatpos sends must keep covering
  decks active, mirror, 3, and 4 as appropriate.
- `LaserDirector` (policy) and `LaserSceneExecutor` (MIDI execution) must remain separate
  responsibilities.
- Manual-static policy: held static stays operator-controlled and visible during
  idle/stop/stale/error/track-change, and loses only to blackout/emergency/pack-disabled/
  shutdown — do not regress this while fixing static-look or idle/zero-frame gaps.

If closing a gap in the matrix below would require violating one of these invariants, do
not violate it — implement the smallest safe alternative and flag the conflict explicitly
in your final report instead of silently choosing one over the other.

## Required work procedure

1. Read the evidence packet in full. Verify current code state against every claim you
   plan to rely on — do not treat doc excerpts as current truth without checking.
2. Inventory the actually-available capture evidence (repo docs + existing `/tmp/rbss_*`
   artifacts + canonical pack manifest) before deciding what's provable from what you have.
3. For each of the 14 completion-audit matrix rows, diagnose root cause from code + evidence,
   not just symptom. Group root causes (e.g. deck/mode state-authority bugs vs. exporter
   value-selection bugs vs. zero-frame/timing bugs) rather than patching each symptom
   independently — if one root cause explains multiple matrix rows, say so and fix it once.
4. Implement the fix for each closable row, directly or via your own subagent(s). Prioritize
   by evidence severity, not row order.
5. For every fix, identify or write the smallest test/check that would fail if the fix were
   wrong or regressed later.
6. Re-run the offline verification tooling you have available (unit tests, offline
   time-domain/parity tooling against existing fixtures) to build evidence for your
   confidence claim. Do not claim confidence without re-running what you can.
7. For the Enttec/hardware row specifically: get the software/pack-runtime side into a
   state where hardware output should work correctly once a serial device is present
   (do not attempt to fix the missing `/dev/cu.usbserial-EN396681` device itself — that is
   a physical connection Brandon must make), and state your confidence for that row
   separately from the other 13.

## Claim discipline

Label every load-bearing claim in your final report `confirmed`, `assumed`, `unknown`, or
`rejected`. A claim is `confirmed` only if you verified it against current code, a test
you ran, or an evidence artifact you actually read this session. Do not upgrade an
`assumed` claim to `confirmed` because it seems likely.

## Success criteria and stop conditions

Stop and finalize your report only when:

- Every one of the 14 matrix rows is either closed-in-code-with-evidence, or explicitly
  marked as the hardware-only exception with a stated reason it cannot be closed without a
  physical device.
- `python3 -m unittest discover tests` passes (report the exact result; if something fails
  and you judge it pre-existing/unrelated, say so explicitly with evidence, don't hide it).
- Any docs you touched still pass `tools/check_docs_metadata.py`,
  `tools/check_agent_contracts.py`, and `tools/check_docs_drift.py`.
- You have not violated any live-safety invariant above.

Do not stop early with a partial fix presented as complete. If you run out of budget before
closing all 14 rows, say so plainly, rank what's left by risk, and do not claim readiness
you have not earned.

## Output format

1. **Verdict**: `SOFTWARE-COMPLETE, HARDWARE-VALIDATION-EXPECTED-TO-PASS`,
   `SOFTWARE-COMPLETE, HARDWARE-VALIDATION-UNCERTAIN` (with reasons), or
   `NOT COMPLETE` (with what's left and why).
2. **Matrix closeout**: all 14 rows, each with: root cause, fix made (file(s) touched),
   evidence/test that proves it, and a confidence label.
3. **Root-cause groupings**: which matrix rows shared a root cause and were fixed together.
4. **Diff summary**: files changed, and why each change was necessary (not a raw diff dump
   unless Brandon's next step needs it).
5. **Tests/checks run and their results.**
6. **Residual risk for the hardware gate**: exact reasoning for why you expect Brandon's
   live hardware validation to pass, tied to evidence — not a generic assurance.
7. **Anything you explicitly did not do and why** (forbidden action, missing evidence,
   live-safety conflict, or genuinely out of budget).
