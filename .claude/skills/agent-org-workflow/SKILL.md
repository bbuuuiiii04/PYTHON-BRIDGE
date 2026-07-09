---
name: agent-org-workflow
description: Use when running or joining the rb_ss_bridge_v2 multi-agent org — taking an executive/manager seat, dispatching orchestrator/implementer lanes over tmux, arming watchers, gating a round, reconciling suite reds, or handing off a seat. Loads the canonical workflow doctrine; the doc is model-agnostic and this skill is just the Claude-side pointer to it.
---

# Agent org workflow (pointer skill)

The canonical doctrine lives in the repo (single source, model-agnostic — Codex and
other agents read it directly):

1. **Read `docs/agents/multi_agent_org_workflow.md` in full before acting.** It
   defines the seat ladder (executive → manager → orchestrator → implementer), the
   written-artifact rule, the review chain, suite-baseline discipline, the
   dispatch/watch tooling + its four field bugs, shared-tree rules, continuity
   insurance (state briefs + the 60–65% handoff rule), escalation semantics, and the
   live-safety spine.
2. Taking a build-lane seat or dispatching one? Also read
   `docs/agents/opus_seat_harness.md` — the mandatory rails for
   orchestrator/implementer-tier models and the dispatch template.
3. Resuming the program cold (new executive seat, or a non-Claude CLI)? Start from
   the newest `docs/agents/codex_resume_state_*.md`.

Hard reminders that don't wait for the doc read:
- ONE executive; the operator talks only to it. Top-tier models never below the
  manager seat. Pin model + effort explicitly at every spawn and verify by capture.
- Dispatch via `tools/agents/dispatch_lane.sh`; watch via `tools/agents/watch_lane.sh`
  (signal files first; ONE watcher per TAG). After every tmux paste: capture, and
  nudge Enter until the paste chip clears.
- Nobody certifies their own work. Suite claims reconcile BY NAME against the named
  baseline. Blocking on divergence is a success mode.
