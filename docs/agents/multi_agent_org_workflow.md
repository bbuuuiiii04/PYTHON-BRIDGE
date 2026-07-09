---
doc_status: current
truth_level: field-proven
last_verified_commit: e46c66c
last_verified_date: 2026-07-09
validation_scope: >
  The multi-agent organization workflow that ran the 2026-07-08/09 overnight program
  (F2, F4, AWR-157..173: ~15 gated ship rounds, 1 ship-blocker found+fixed, zero
  regressions shipped). Model-agnostic: written for ANY agent stack (Claude family,
  Codex/GPT, future models). Every rule here was paid for by a real incident or a
  real save — incident citations inline. This doc is the canonical source; the Claude
  skill `.claude/skills/agent-org-workflow/` and any other agent entrypoints wrap it.
---

# The multi-agent org workflow (executive → manager → orchestrator → implementer)

**Why this exists:** one agent cannot hold a whole program in context, and one
unreviewed agent ships plausible-but-wrong work. This org splits *thinking* from
*throughput* and buys correctness with independent verification at every hop. It is
the single highest-leverage structure in this repo's history: one overnight run
shipped a quarter's worth of gated work with zero regressions reaching the operator.

## 1. The seat ladder

| Seat | Count | Model tier | Owns |
|---|---|---|---|
| **Executive manager** | exactly ONE | strongest reasoning available, highest effort | The operator's only surface. Program design, sequencing, authorization, INDEPENDENT verification gates, ship notices, the morning/session report. Never implements. |
| **Manager** | one per workstream, parallel OK | strongest tier (or one below), high effort | Owns a workstream end-to-end: spec authoring, dispatching orchestrators, ADVERSARIAL review of everything its lanes produce, escalation to the executive. |
| **Orchestrator** | per build round | mid tier (throughput model) | Executes a written spec task-by-task: one commit per task, runs scoped tests, reports honestly, BLOCKS instead of inventing when reality diverges from the spec. |
| **Implementer / subagent** | fan-out | cheapest adequate tier | Bounded single tasks inside an orchestrator's round: searches, file grinds, test runs. Returns conclusions + exact file:line refs, never transcripts. |

Hard rules (operator-pinned, restated repeatedly):
- The top-tier model NEVER appears below the manager seat. Thinking is expensive;
  spend it on judgment, not throughput.
- The operator talks ONLY to the executive. Lanes never report to the operator
  directly, with one exception: operator-attended 1-1 sessions (see §7).
- Layers are collapsible for tasks that cannot surprise (executive → orchestrator
  directly), but idea-sized work gets the full chain.
- Pin the model AND effort explicitly on every seat at spawn, then VERIFY
  (capture the acknowledgment; for high-stakes lanes, verify the transcript's model
  records). Saved defaults drift — the last session's pin becomes the next session's
  boot state.

## 2. Every hop is a written artifact

A seat hands work down via a FILE (kickoff brief / spec), never a chat paraphrase.
Chat gets a short kickstart pointing at the file. The file states: verified ground
truth (with commit pin), scope + explicit non-scope, acceptance criteria, live-safety
constraints, sentinel/signal contract, escalation route. Specs follow the repo's spec
skill format (Part A–E + pre-handoff checklist). Rationale: files survive context
loss, compaction, and seat handoffs; paraphrases do not.

## 3. The review chain — nobody certifies their own work

1. **Implementer/orchestrator** reports WHAT IT DID with evidence (commits, test
   counts, red names). It never declares the round done.
2. **Manager** adversarially reviews: re-derives the load-bearing claims at its own
   desk (re-run the repro, re-run scoped suites, read the diff line by line, verify
   cites at HEAD). Verdict: PASS / PASS-with-required-fixes / redo.
3. **Executive** gates independently: full suite at ITS desk reconciled against the
   NAMED baseline (see §4), spot-checks the claims that carry the most risk, rules.
4. **Operator** activates (config apply, bridge start, live gate). Software-tested
   is never "done" — the operator's live pass is the final gate, always.

Field results 2026-07-09: the chain caught 3 suite-red misattributions, a pad-server
crash, 5 stale tests, a wrong-file spec cite, an unspecced fold-in, and a
self-reported false-positive — every one before ship. This is why the chain exists.

## 4. Suite-baseline discipline (the #1 source of false alarms)

- The test suite has a NAMED environmental-red baseline (names, not counts, and the
  expected count differs by working directory). Every red/green claim MUST reconcile
  BY NAME against it. "N reds" without names is not evidence.
- Known flappers (e.g. pack byte-identity tests that embed `git rev-parse HEAD`)
  flap when ANY commit lands mid-run — and auto-sync commits land constantly.
  Rule: isolate the flapper; if green in isolation, count it as baseline; never
  chase it, never let it gate, never let a lucky green become the new expectation.
- A red that is genuinely new: reproduce at YOUR desk before routing a fix.
  Full-suite-only reds under multi-lane CPU load are a known TEST-flake class
  (timing-margin assertions) — reproduce in isolation ×8 and at file scope before
  blaming a code round (incident: two drop_presentation reds wrongly attributed to
  a landed round; executive desk showed 8/8 green; refuter later proved
  load-dependent test flake).
- When a landed config change flips config-reading tripwire tests: re-pin the tests
  to the APPROVED values as explicit literals — never blind-read the live file, and
  never leave a red board "documented" when a re-pin restores truth.

## 5. Dispatch + watch mechanics (agent-CLI-agnostic: tmux + files)

The tooling is deliberately model-agnostic — any CLI agent in a tmux pane works the
same way (Claude, Codex, anything):
- **Dispatch:** `tools/agents/dispatch_lane.sh` — does the whole ritual: hands-off
  check, model/effort pin verification, paste-trap clearing, run-straight-through
  clause, mandatory signal-file instruction. Use it instead of hand-rolling.
- **Watch:** `tools/agents/watch_lane.sh SESSION [SENTINEL_RE] [DEADLINE] [WAITBUSY] [TAG]`
  — file-first: the machine channel is `/tmp/rbss_lane_signals/<session>.<TAG>.done|.blocked`
  (consumed on read); the pane regex is only a fallback. ONE watcher per dispatch —
  a second watcher on the same TAG steals the signal file.
- **Completion contract in every dispatch:** print sentinel on its own line AND
  write the signal file; pre-authorize run-straight-through (never idle at a
  checkpoint awaiting acknowledgment).

Field bugs, all hit in production the same night (avoid re-learning them):
1. Collapsed paste: a `[Pasted text #N]` chip sitting unsubmitted at a prompt looks
   idle forever. After EVERY dispatch, capture the pane; nudge Enter until the chip
   clears ("paste again to expand" = send Enter again).
2. Checkpoint idling: an orchestrator waiting mid-build for acknowledgment is
   silent-stall — dispatches must pre-authorize running straight through, and
   watchers must alert on IDLE, not just sentinels.
3. Sentinel echo: your own dispatch text containing the sentinel string false-fires
   pane-regex watchers (wraps in narrow panes defeat anchoring too). Prefer signal
   files; if using pane regex, line-anchor it and never put the literal sentinel in
   relay messages.
4. Same-TAG block-and-resume poisons the pane channel permanently (the old
   TAG-BLOCKED line stays in scrollback) — watch resumed rounds by signal file ONLY.
- Hands-off rule: capture the pane BEFORE any send-keys; real typed text at the
  prompt (not the dim `\033[2m` autosuggest ghost) = a human mid-thought, ABORT.
  Never send keys to an operator-attended lane without the operator's OK. Proactive
  `/clear` of idle lanes is BANNED (`/clear` only as step 1 of your own dispatch).
- `tmux list-sessions` immediately before creating any session (stale lists have
  mis-routed kickstarts). Operator-facing sessions get descriptive names; worker
  lanes get generic ones.
- Watchers on manager lanes that HOLD (waiting on their own sub-lanes) churn on
  pane-idle detection — watch holding lanes by signal file only.

## 6. Shared-tree reality (auto-sync + parallel lanes)

- An auto-commit hook may sweep ANY dirty file into ANY lane's turn-end commit.
  Consequences, all field-proven: (a) HEAD content is authoritative — check
  `git log`/HEAD before calling a commit failed or a file lost; (b) commits by
  EXPLICIT PATHS only, never `-a`; (c) a lane's files riding another lane's commit
  is NORMAL — note the misattribution in the registry, verify content at HEAD,
  NEVER rewrite pushed history to "fix" it.
- Re-read shared docs (work registry, contracts yml, doc index) fresh immediately
  before editing — parallel lanes move them.
- Each round takes the next work-registry ID; re-check the current max right before
  writing (parallel lanes race).
- File fences between concurrent rounds: a lane touches ONLY its spec-listed files;
  overlapping lanes get landing gates (one lands + gates before the other's
  overlapping task dispatches).

## 7. Continuity insurance (context is a consumable)

- **Every manager keeps an on-disk state brief** (docs/prompts/active/…_state_….md),
  updated as things land — a seat crash or compaction must cost minutes, not the
  night.
- **The executive keeps a live seat-state file** (in its memory store or the repo)
  updated per round: scoreboard, open gates, directives verbatim, fallback clocks.
- **Handoff rule (operator-pinned): at 60–65% context, the seat hands off** — write
  the lossless brief, spawn the successor, verify it boots and takes the watch,
  announce, retire. A successor's first duty: verify every lane FRESH against
  reality ("never notes over reality") — timestamps in inherited notes may be wrong
  (one seat's clock ran 3h hot; trust `date`, treat stamps as sequence markers).
- Self-check trigger: ≥3 self-caught mistakes in a short window OR degraded recall
  of the program's decisions = hand off now.
- Operator-attended 1-1 sessions get a brief capturing everything the operator
  already said (they must NEVER have to re-explain), the communication rules
  (AGENTS.md §0), and hard boundaries.

## 8. Escalation + operator surface

- Ship-blockers (would break a live session) escalate IMMEDIATELY via `.blocked`
  signal with evidence: severity, exact file:line, reproduction, refuter verdict,
  proposed fix SHAPE. The executive verifies AT ITS DESK before authorizing a fix
  round. Polish waits for the operator's word.
- Findings that survive an independent refuter (default-to-refuted) are the only
  findings that reach the executive. Adversarial verification kills
  plausible-but-wrong findings before they cost anyone time.
- The executive notifies the operator per feature ship (plain language, mechanism
  kept, evidence class stated: software-tested vs live-validated) and delivers the
  session report at the end. Chat is the operator's only surface — never "see the
  doc".

## 9. Live-safety spine (this repo specifically)

Every seat, every model: reason the live-mixing scenario before any change; the
bridge is started ONLY by the operator (menubar); after any start verify exactly one
process; fail-open beats fail-dark (a room that re-lights early is recoverable, a
stuck-dark room is the failure); masks/emergency precedence wins over features;
frozen gates don't get overridden at 6am on the implementing lane's own nuance.
Full invariants: `docs/architecture/runtime_invariants.md`, AGENTS.md §6.

## 10. Replicating this org on Codex (or any other agent CLI)

Nothing above is Claude-specific except the skill wrapper. The mapping:
- Seats = tmux sessions running the agent CLI. The signal-file protocol, dispatch/
  watch scripts, written-artifact rule, review chain, and baseline discipline are
  byte-identical.
- Model tiering maps to whatever tiers exist (e.g. strongest reasoning model at
  executive/manager seats, faster/cheaper models at orchestrator/implementer).
  The invariant is the SHAPE: judgment at the top, throughput at the bottom,
  independent verification at every hop.
- Codex reads this doc + AGENTS.md as standalone files (no skill autoload): a Codex
  executive session's kickstart = "read AGENTS.md, then
  docs/agents/multi_agent_org_workflow.md, then the current resume-state doc, then
  take the watch."
- Seat harness for orchestrator/implementer-tier models (drift compensation):
  `docs/agents/opus_seat_harness.md` — written for Opus, applies to any
  non-frontier seat model.
- Current program state for resuming: `docs/agents/codex_resume_state_2026_07_09.md`.
