---
doc_status: current
truth_level: handoff-report
last_verified_commit: e46c66c
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the FABLE LEGACY manager (tmux `legacy`, Fable/HIGH, spawned 2026-07-09
  — the operator's last Fable-access day). The executive seat already BUILT the core
  legacy artifacts; this lane's job is adversarial verification, cold-boot testing,
  and closing the remaining transfer gaps. The operator will forward his own mandate
  text to this session; treat it as the charter and this brief as the state.
---

# Fable legacy manager — kickoff (2026-07-09, last Fable day)

You are the **legacy manager** (Fable, HIGH). Mission: make sure Fable's workflow
survives Fable — in the repo, for any agent family, with a smooth Codex resume.

## Already built by the executive (verify, don't rebuild)
All committed at/after `e46c66c` (git log for the "Fable legacy:" commit):
1. `docs/agents/multi_agent_org_workflow.md` — canonical org doctrine (executive →
   manager → orchestrator → implementer), model-agnostic, incident-cited.
2. `docs/agents/opus_seat_harness.md` — build-seat rails + dispatch template
   (8 observed failure modes → 8 structural counters).
3. `docs/agents/codex_resume_state_2026_07_09.md` — full workstream transfer state
   + Codex boot kickstart.
4. `.claude/skills/agent-org-workflow/SKILL.md` — Claude-side pointer skill
   (gitignore-whitelisted).
5. `tools/agents/guard_footguns.sh` + local PreToolUse wiring — mechanically blocks
   `git clean -f*` and raw bridge launches (tested: 3 block / 3 allow + prose-vs-
   command false-positive fixed and retested). NOTE: the settings.local.json hook
   wiring is machine-local (gitignored) — document the wiring line in your review if
   you judge it worth a setup doc.
6. AGENTS.md + doc_index routing to all of the above. Hard checks green at commit.

## Your tasks
1. **Adversarial review of 1–3** — the executive wrote them from deep context; you
   verify them from evidence: every incident citation must trace to a real record
   (registry rows, state briefs in docs/prompts/active/, git log); every rule must
   be actionable without tonight's context. Fix what fails, contract-first.
2. **COLD-BOOT TEST (the real acceptance).** Spawn a fresh throwaway lane
   (`claude`, any mid tier, /clear) and give it ONLY the resume-doc kickstart. It
   must correctly answer: the seat ladder + who talks to the operator; how to
   dispatch and watch a lane; what to do with a suite showing "6 reds"; the current
   state of AWR-173 and the D1-F1 deferral. Gaps it reveals = edits you make.
3. **Codex-side dry run description.** Verify the resume doc's Codex boot path
   against reality you can check (Codex reads repo docs standalone; the tmux/signal
   tooling is CLI-agnostic; note anything Claude-specific that leaked in).
4. **Sweep the remaining Fable-only knowledge.** The Claude memory store
   (~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/memory/) does NOT transfer to
   Codex. Audit its STANDING items (feedback + open project rulings) against the
   repo docs: anything load-bearing and repo-relevant that lives ONLY in memory gets
   a repo home (docs/agents/lessons/ or the resume doc). Do not copy noise —
   operator-personal items stay in memory.
5. **Registry + bookkeeping.** Give this legacy work a registry row; run the three
   hard checks; explicit-path commits.

## Rules
- Org doctrine applies to you: written artifacts per hop, Opus/Sonnet below you,
  dispatch/watch via tools/agents/, report evidence not verdicts, escalate to the
  executive seat (tmux `superman3`) while it lives — after today, escalations go to
  the operator in your own chat.
- The operator's mandate text (when he pastes it) wins over this brief on conflict.
- Today is time-boxed: he loses Fable access after today. Ship the verified core
  over a polished everything.
