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

1. Every row of the completion-audit matrix in the evidence packet is closed at the
   software/code level, **except** the small set of explicitly-named non-closure
   exceptions below. The matrix — the section titled **"Completion audit against the
   original greenlight surface"** in `soundswitch_truth_exam_live_blockers_2026_07_02.md`
   — has **15 rows**. Do not re-count or re-partition it; here is the canonical list and
   the required disposition for each row:

   | # | Row | Disposition |
   | --- | --- | --- |
   | 1 | Official U0/U1 comparator verdict | **TOOLING — OUT OF SCOPE.** This is validation tooling, not the runtime under test. Do not fix it (see "Comparator note"); build confidence from code review + existing valid captures + offline time-domain evidence. |
   | 2 | Scripted output values | SOFTWARE-CLOSE |
   | 3 | Scripted timeline timing | SOFTWARE-CLOSE |
   | 4 | Autoloop output values | SOFTWARE-CLOSE |
   | 5 | Autoloop cycling/wrap timing | SOFTWARE-CLOSE |
   | 6 | Static looks | SOFTWARE-CLOSE |
   | 7 | Manual blackout / static overlap | SOFTWARE-CLOSE |
   | 8 | Playback edges | SOFTWARE-CLOSE |
   | 9 | Rewinds/seeks | SOFTWARE-CLOSE |
   | 10 | BPM/pitch changes | SOFTWARE-CLOSE |
   | 11 | Transitions / active deck | SOFTWARE-CLOSE |
   | 12 | Idle/zero-frame behavior | SOFTWARE-CLOSE |
   | 13 | MIDI/control bindings | SOFTWARE-CLOSE |
   | 14 | Unsupported/inactive inventory | SOFTWARE-CLOSE |
   | 15 | Enttec/hardware parity | **HARDWARE EXCEPTION** — structurally impossible to close without a physical serial device (see procedure step 8). |

   That is **13 rows you must close in software with evidence** (rows 2-14), plus two
   named non-closure exceptions: the comparator/tooling row (1) and the Enttec/hardware
   row (15). "All rows closed" means all 13 software rows closed-with-evidence and both
   exceptions explicitly reported with their stated reason — not silently dropped, not
   merged, not re-counted.
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
way." Operationalize this as: closing the 13 software rows of the completion-audit matrix
(rows 2-14, see the Deliverable table), at the value + timing level where applicable, and
correctly reporting the two named non-closure exceptions (comparator/tooling row 1, and
Enttec/hardware row 15).

## Evidence packet

Primary evidence (read these first, in full):

- `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md` — live
  truth-check diagnostic evidence and the 15-row completion-audit matrix (near the end of
  the doc) that defines the target surfaces — see the canonical enumeration and per-row
  disposition in the Deliverable section above; that table governs, not any re-count of the
  doc. Also documents a known comparator topology bug (see "Comparator note" below).
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
- `docs/research/soundswitch/soundswitch_live_capture_findings_2026_07_02_evening.md` —
  **read this and treat it as superseding the truth-exam doc on the 4 rows it covers.** A
  fresh live capture session (same day, after the truth-exam doc was written) closed 4 of
  the previously-GAP rows: static/manual look hold (was "never observed," now **confirmed
  working** with a named interruption mechanism, `smart_drop_blackout`, to check against
  the manual-static policy invariant), autoloop BPM/pitch movement (now confirmed),
  scripted-to-scripted transition with no autoloop deck involved (now confirmed, and
  isolates the deck-split bug to autoloop-sourced handoffs specifically), and drag-seek
  forward/backward (now confirmed for drag-seeks specifically; a large discrete
  jump/hotcue-style seek is still unverified). Do not start from the truth-exam doc's
  "static_held never observed" claim — it is out of date as of this newer doc.
  **Important on what "closed" means here:** this newer doc removes the *capture/observation*
  gap on those 4 rows (the behavior is now witnessed live), but it does **not** by itself
  verify DMX value/timing parity for them — e.g. autoloop still shows heavy byte mismatches
  in the truth-exam data, and static hold surfaces an open question about whether
  `smart_drop_blackout` should be able to interrupt a held static look. Those 4 rows
  (6/7 static, 9 seeks, 10 BPM, 11 transitions, as they map to the matrix) still require
  code-level closure per the Deliverable; treat the newer doc as evidence you now have,
  not as rows already done.

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
  — require it to show the test/check that proves it, and verify every row's closing claim
  yourself before including it in your final report. Do not use severity to decide which
  claims to check; a "minor" row reported closed on a false claim is still a false claim in
  your final report.
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
- Do not modify, weaken, delete, skip, or `xfail` an existing test to make the suite pass
  (`AGENTS.md` §8: "Do not modify tests to make [them] pass"). Adding new tests is expected;
  editing an existing test's assertions/inputs to turn red green is not. If an existing test
  is genuinely wrong (asserts behavior the current code/spec contradicts), say so explicitly
  in your report with the evidence and fix the test's *correctness* — never silence it, and
  never edit it solely to reach a green run.

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
- SoundSwitch pack-runtime safety invariants (from `soundswitch_pack_controller.py`, the
  surface you are authorized to change — preserve every one while closing rows 2-14):
  validate-first / no partial swap (build+verify the new `PackRuntime` before touching the
  live one; on failure keep the old verified runtime or force safe disabled — never a
  half-swapped state); stop-before-start on the shared Enttec serial port (publish disabled,
  `zero_and_stop` the OLD sender, then start the new); a pack/start/verify failure must fail
  closed to disabled/none and **never fall back to MIDI**; no implicit hot-enable
  (`reload`/`backend` must never enable a disabled pack); and all runtime error details stay
  sanitized (class/category strings, never paths/ports/aliases/UUIDs). If a fix to rows 2-14
  appears to require relaxing any of these, treat it as the rare invariant-conflict case, not
  a free edit.

If closing a gap in the matrix below would require violating one of these invariants, do
not violate it. But this is not a shortcut: before treating anything as an irreconcilable
invariant conflict, you must first try every alternative implementation you can find — this
exception should be rare to the point of almost never firing. A "smallest safe alternative"
implementation must still fully close the underlying row; it is not permission to ship a
partial or cosmetic fix and call the row closed. Only if you have genuinely exhausted
alternatives is this an additional non-closure path (beyond the comparator/tooling and
Enttec/hardware rows, which already have their own dispositions) — and it requires the same
rigor: you must **list the specific alternative implementations you actually tried** and give
a specific, evidenced reason why each failed and why no safe implementation exists — not a
generic "this conflicts with an invariant." Expect to use this zero times.

## Required work procedure

1. Read the evidence packet in full. Verify current code state against every claim you
   plan to rely on — do not treat doc excerpts as current truth without checking.
2. Inventory the actually-available capture evidence (repo docs + existing `/tmp/rbss_*`
   artifacts + canonical pack manifest) before deciding what's provable from what you have.
3. For each software-close row (rows 2-14 of the completion-audit matrix), diagnose root cause from code + evidence,
   not just symptom. Group root causes (e.g. deck/mode state-authority bugs vs. exporter
   value-selection bugs vs. zero-frame/timing bugs) rather than patching each symptom
   independently — if one root cause explains multiple matrix rows, **fix that root cause**,
   not just name it. A grouped root cause is not closed until every row it touches is
   closed.
4. Implement the fix for each closable row, directly or via your own subagent(s). Prioritize
   by evidence severity, not row order.
5. For every fix, write the smallest test/check that would fail if the fix were wrong or
   regressed later, **then actually run it and confirm it currently passes**. A test that
   exists but was never executed does not count as verification.
6. For rows where the evidence packet shows no existing capture ever exercised the behavior
   (e.g. static-hold windows were "never observed," forward seek across a cue boundary was
   "not cleanly covered," the full deck-transition matrix wasn't captured) — you cannot get
   new live evidence, and the absence of a live capture is not a reason to leave the row
   under-verified. Construct new offline/unit-level tests that exercise the logic directly
   (simulate the relevant `BridgeEvent`/state transitions and assert the expected behavior)
   so the row is verified by construction even without a fresh live capture.
7. Re-run the offline verification tooling you have available (unit tests, offline
   time-domain/parity tooling against existing fixtures) to build evidence for your
   confidence claim. Do not claim confidence without re-running what you can.
8. For the Enttec/hardware row specifically: get the software/pack-runtime side into a
   state where hardware output should work correctly once a serial device is present
   (do not attempt to fix the missing `/dev/cu.usbserial-EN396681` device itself — that is
   a physical connection Brandon must make), and state your confidence for that row
   separately from the other 13.
9. **Keep working until every row is actually closed.** If a fix doesn't work, doesn't fully
   resolve the row, or surfaces a new problem, debug it and try again yourself. A row that
   is diagnosed but not fixed, or fixed but not verified, is not done — keep iterating on it.
   You have the authority and the capability to keep debugging; use it instead of stopping.
10. **Once every row is individually fixed, run one final full integration pass**: the
    complete test suite plus every offline verification tool you used along the way, all
    together, in one pass. A fix for one row that quietly regresses an already-closed row
    is not acceptable — this final pass is what catches that before you report done.

## Claim discipline

Label every load-bearing claim in your final report `confirmed`, `assumed`, `unknown`, or
`rejected`. A claim is `confirmed` only if you verified it against current code, a test
you ran, or an evidence artifact you actually read this session. Do not upgrade an
`assumed` claim to `confirmed` because it seems likely.

A matrix row cannot be reported as closed while any claim its closure depends on is labeled
`unknown` or `assumed`. `unknown`/`assumed` on a row-closing claim means that row is not
actually closed yet — go verify it (write the test, run the code, read the source) until
the claim earns `confirmed`, or keep debugging per the work procedure above. Do not let an
`unknown` label stand in for real verification in the final report.

## Success criteria and stop conditions

This is a one-shot handoff with no back-and-forth. Brandon is not going to review a partial
result and send you back in for round 1.5 — finishing is your job, not his. The only
acceptable final deliverable is:

- All 13 software rows (rows 2-14) closed-in-code-with-evidence. The comparator/tooling row
  (1) and the Enttec/hardware row (15) are reported as their named exceptions with the stated
  reason, per the Deliverable table. The only additional non-closure path is a genuinely
  irreconcilable live-safety invariant conflict (see below) — expected to fire zero times and
  subject to the same evidence bar; it is not a general escape and does not apply to the
  comparator or Enttec rows, which already have their own dispositions.
- `python3 -m unittest discover tests` passing (report the exact result). If a failing test
  predates your changes, prove it — check it against the pre-change state (e.g. `git stash`
  your diff and confirm the same test already failed, or `git log`/`git blame` the test) —
  do not simply assert "pre-existing" without checking. A test you introduced or a test that
  only started failing after your changes is your bug to fix, not a footnote.
- Any docs you touched still passing `tools/check_docs_metadata.py`,
  `tools/check_agent_contracts.py`, and `tools/check_docs_drift.py`.
- No live-safety invariant violated.

**`NOT COMPLETE` and "hardware validation uncertain" are not acceptable resting states.**
If a fix fails, doesn't fully close a row, or reveals a new problem, that is expected —
debug it and keep going. Do not stop to ask Brandon "what would you like me to do next" or
hand back a list of open questions; you have everything you need in this packet and full
authority to keep implementing and delegating to your own subagents until every row is
genuinely closed. Do not present a diagnosis as if it were a fix, and do not present an
untested fix as if it were verified.

The only legitimate reason this deliverable could end up incomplete is being cut off by a
rate limit or quota exhaustion before you finish — that is an external constraint, not a
choice, and not something to plan around or use as an early exit. If it happens, do not
frame the result as a considered `NOT COMPLETE` verdict; report it plainly as
`CUT OFF BEFORE COMPLETION` with exact progress state (which rows are actually closed and
verified vs. which were mid-fix), so the next session can resume precisely instead of
re-diagnosing from scratch.

## Output format

1. **Verdict**: `SOFTWARE-COMPLETE, HARDWARE-VALIDATION-EXPECTED-TO-PASS` is the only
   acceptable completed verdict. If you were cut off before reaching it, use
   `CUT OFF BEFORE COMPLETION` instead, with the exact resume state (see above) — do not
   substitute `NOT COMPLETE` or a "hardware validation uncertain" verdict for a result you
   simply stopped working on.
2. **Matrix closeout**: all 15 rows, in the canonical order/numbering of the Deliverable
   table. For each software row (2-14): root cause, fix made (file(s) touched), evidence/test
   that proves it, and a confidence label. For the comparator row (1) and Enttec row (15):
   the named-exception disposition and its stated reason. Do not omit, merge, or renumber
   rows.
3. **Root-cause groupings**: which matrix rows shared a root cause and were fixed together —
   this must describe a completed fix, not an open finding.
4. **Diff summary**: files changed, and why each change was necessary (not a raw diff dump
   unless Brandon's next step needs it).
5. **Tests/checks run and their results.**
6. **Residual risk for the hardware gate**: exact reasoning for why you expect Brandon's
   live hardware validation to pass, tied to evidence — not a generic assurance.
7. **Anything you explicitly did not do and why** — limited to: a forbidden action you
   correctly declined, or (extremely rare, see the live-safety section) a genuinely
   irreconcilable invariant conflict. "Out of budget" is not a valid entry here; if a rate
   limit or quota cutoff actually terminates you before finishing, that produces a
   `CUT OFF BEFORE COMPLETION` report instead of this output format, not an entry in this list.
