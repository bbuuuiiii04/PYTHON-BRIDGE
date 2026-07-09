---
doc_status: current
truth_level: field-proven
last_verified_commit: e46c66c
last_verified_date: 2026-07-09
validation_scope: >
  Operating harness for orchestrator/implementer-tier seat models (written from Opus
  4.8 field evidence, 2026-07-08/09 overnight; applies to ANY mid-tier model in those
  seats, including GPT-family under Codex). Honest framing: this does not change the
  model — it changes the structure around it so the observed failure modes stop
  reaching the ship gate. Every rail below maps to a real incident.
---

# Seat harness for orchestrator/implementer-tier models ("the Opus harness")

**The honest premise.** Mid-tier models in build seats are not "lobotomized" — they
are unreliable in SPECIFIC, PREDICTABLE ways, and every one of those ways is
containable with structure. On 2026-07-08/09 the org shipped ~15 Opus-built rounds
with zero regressions reaching the operator — not because Opus was flawless (it made
every mistake below) but because the harness caught each one before ship. Give this
doc (or its rules inlined) to every orchestrator/implementer dispatch.

## Observed failure modes → the rail that contains each

| # | Failure mode (field incident) | Mandatory rail |
|---|---|---|
| 1 | **Misattributing suite reds** — 3 lanes in one night attributed their extra reds to "other overnight work" / a prior round, wrongly | Every red/green claim reconciles BY NAME against the named baseline (org doc §4). "N reds, pre-existing" without names is an INVALID report — the dispatch must demand names, the reviewer must re-derive them. |
| 2 | **Self-certification** — lanes declaring a moved baseline / "done" on their own authority | The dispatch states verbatim: "You report evidence; the manager reviews; the executive gates. You never declare the round shipped." A moved-baseline conclusion needs the executive's sign-off, full stop. |
| 3 | **Checkpoint idling** — orchestrator sat 17 min at a mid-build checkpoint awaiting acknowledgment nobody would send | Every dispatch pre-authorizes run-straight-through: "Do not pause at checkpoints for acknowledgment; run straight through unless genuinely blocked." Watchers alert on idle. |
| 4 | **Inventing instead of blocking** — the risk class; the good counter-example: a lane BLOCKED on an unfamiliar config member instead of guessing an approval | State it verbatim in the dispatch: "If reality diverges from the spec (unknown name, missing file, unexpected state): STOP, write the .blocked signal with one line of evidence, and wait. Blocking is a success mode; invention is the failure mode." |
| 5 | **Scope creep / unspecced fold-ins** — a lane folded an unspecced fix into a task mid-round | Spec lists files + tasks exhaustively; dispatch says "touch ONLY spec-listed files; an improvement you notice = a NOTE in your report, never an edit." Reviewer diff-checks the commit stat against the spec's file list. |
| 6 | **Plausible-but-wrong findings** (review seats) — a finder hand-built a repro for an unreachable state | Findings pass an independent refuter (default-to-refuted) before they reach anyone who acts on them. A finding = severity + file:line + reproduction + refuter verdict, or it doesn't exist. |
| 7 | **Stale-context claims** — citing line numbers / behavior from an outdated read | "Verify every cite at HEAD immediately before writing it. The tree moves under you (auto-sync, parallel lanes)." Reviewer spot-checks cites at HEAD. |
| 8 | **Timing/echo mechanics** — collapsed pastes, sentinel echo false-fires | Handled by the dispatch/watch tooling (org doc §5) — not the model's job to remember; the tooling does the ritual. |

## The dispatch template (inline these sections, always)

1. **Ground truth, pinned:** the exact commit, the verified facts, the named
   baseline (by name), the file fence.
2. **Tasks, numbered, one commit each** (explicit paths, never `-a`).
3. **Acceptance:** scoped tests per task + the final suite expectation stated as
   NAMES, + hard checks if docs/contracts moved.
4. **The four verbatim clauses:** report-don't-certify (#2), run-straight-through
   (#3), block-don't-invent (#4), spec-files-only (#5).
5. **Completion contract:** sentinel line + signal file
   (`/tmp/rbss_lane_signals/<session>.<TAG>.done|.blocked`).
6. **Live-safety lines** relevant to the touched surface (org doc §9).

`tools/agents/dispatch_lane.sh` automates the ritual parts; the spec content is the
manager's job. The repo spec skill (`.claude/skills/codex-spec/SKILL.md`) has the
full Part A–E format — it was written for Codex and works unchanged for any
build-seat model.

## For the reviewer above the seat

- Re-derive, don't re-read: run the repro yourself, run the scoped suite yourself,
  diff the commit stat against the spec's file list, check 2-3 cites at HEAD.
- Treat confidence language ("all green", "done", "as expected") as a flag to
  verify, not a reason to relax — the field incidents above all arrived wrapped in
  confident wording.
- Praise blocking. A lane that blocks correctly (incident #4's counter-example) is
  the harness working — say so in the review, it reinforces the behavior for the
  session's remaining tasks.
