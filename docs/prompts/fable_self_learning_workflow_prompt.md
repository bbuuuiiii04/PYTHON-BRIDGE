---
doc_status: current
truth_level: prompt-artifact
last_verified_date: 2026-07-04
validation_scope: Fable 5 prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Fable 5 Prompt — Design & Challenge a Self-Learning System for Brandon's AI Workflow

Paste everything below the line into a fresh Fable 5 session. Effort: **xhigh**.

Brandon-facing note (not part of the prompt): if this prompt gets blocked, retry with a narrower evidence packet (e.g. drop transcript access, keep only memory stores) and neutral wording — never jailbreak phrasing.

---

Target: Claude Fable 5, effort xhigh.

This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

## Mission

Brandon (project owner/operator, not a software engineer; solo hobby setup, macOS) runs most of his work through AI agents: Claude (Fable/Opus) for analysis, planning, specs, and review; Codex for implementation. Agents keep making mistakes that repeat across sessions — and the current defense is manual: Brandon notices a mistake, complains, and an agent hand-writes a memory file. That loop depends entirely on Brandon catching the error and paying a correction cost he specifically wants to avoid (inattentive ADHD; context-switching and correction loops are expensive for him).

Your mission: **brainstorm, plan, and adversarially challenge a self-learning system for Brandon's global AI workflow** — a system that analyzes past conversations and repeated mistakes and turns them into durable improvements (rules, memories, hooks, checks) without depending on Brandon to notice and correct each failure by hand.

The output is for Brandon to read and decide with. It may later feed a Codex implementation spec, but that is a separate step. **Do not implement anything; the deliverable is the design analysis only.**

## What exists today (verified 2026-07-04 — re-verify anything load-bearing before relying on it)

- **Global rules:** `~/.claude/CLAUDE.md` — Brandon's communication preferences and operating rules for all agents/repos.
- **Per-project memory stores:** `~/.claude/projects/<project-slug>/memory/` — one fact per file with frontmatter, indexed by a `MEMORY.md` loaded each session. The largest and most active store is the bridge repo's: `~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/memory/`.
- **Session transcripts:** JSONL session files under `~/.claude/projects/<project-slug>/` — the raw record of past conversations. Large; sweep with read-only subagents, not by reading everything into your own context.
- **Hooks infrastructure:** Claude Code supports session/turn hooks (the bridge repo already uses a Stop hook for auto-sync), so mechanical enforcement points exist.
- **A concrete recent failure**, recorded at `~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/memory/feedback_answered_scope_is_the_scope.md`: Fable asked Brandon a scope question ("all 3 rounds or one at a time?"), Brandon answered "all 3", and Fable delivered only round 1. Brandon had to correct it.
- **Known repeat-failure classes** (from memory files and Brandon's reports; treat as leads, verify against transcripts): stale memories asserted as current truth; scope decay across long turns; overconfident hypotheses in reverse-engineering work later falsified by evidence; detail erosion after context compaction.

Source-of-truth order: transcripts and current files beat memory files; memory files beat your assumptions. Label every important claim **confirmed / assumed / unknown / rejected**, tied to what you actually inspected.

## Deliverable

One markdown design document, written to `~/rb_ss_bridge_v2/docs/plans/active/self_learning_workflow_design.md`, containing:

1. **Evidence base.** What the transcripts and memory stores actually show about repeated mistakes: the top recurring failure patterns, each with at least one concrete cited instance (file + enough location detail to find it). If the transcripts are too thin or noisy to support a pattern, say so — do not force findings.
2. **Brainstorm.** The credible design space for a self-learning system, from minimal (e.g. a periodic "mistake retrospective" prompt over recent transcripts that proposes memory/CLAUDE.md updates for Brandon's approval) to ambitious (automated hooks that mine transcripts, cluster failures, and maintain rules autonomously). For each option: what it catches, what it misses, what it costs (tokens, Brandon's attention, complexity), and how it can go wrong.
3. **Recommendation.** One recommended design with a phased plan — smallest useful first phase, clear completion markers per phase, and exactly which decisions Brandon must make. Respect the existing division of labor: Claude designs and reviews; Codex implements any code.
4. **Challenge.** Genuinely try to kill your own recommendation before presenting it. At minimum, pressure-test: Does this need to exist at all, or is stricter memory hygiene plus a handful of hooks sufficient? Can a system that learns from its own transcripts amplify wrong lessons (a bad memory teaching future sessions the same error)? Who audits the learner — does this just move the "Brandon must notice" problem up a level? Does the maintenance cost of the system exceed the cost of the mistakes it prevents, for a solo hobby operator? Keep whatever survives; report what didn't and why.
5. **Verdict:** `BUILD` / `BUILD SMALLER` / `DON'T BUILD`, with the one-paragraph justification, followed by the open questions only Brandon can answer.

Lead the document with the verdict and a plain-language summary Brandon can read cold — outcome first, complete sentences, no working shorthand or invented labels.

## Boundaries

- Read-only everywhere except the single deliverable file above. Allowed reads: `~/.claude/**` (CLAUDE.md, memory stores, session transcripts) and `~/rb_ss_bridge_v2/docs/**`. Do not read bridge source code — this task is about the workflow, not the bridge internals.
- Do not modify any memory file, `CLAUDE.md`, hook, or setting. Proposals about them belong in the deliverable, not applied.
- Do not touch the running bridge, any config under `~/rb_ss_bridge_v2/config/`, git state, or hardware.
- Transcripts contain private material. Quote the minimum needed to evidence a pattern; never copy secrets, API keys, IPs, or device IDs into the deliverable.
- Delegate large transcript sweeps to read-only subagents that return conclusions plus exact file references; verify any load-bearing subagent claim yourself before building on it.
- When you have enough information to act, act. If you are weighing a choice, give a recommendation, not an exhaustive survey. Do not re-litigate decisions Brandon has already made (Codex implements code; no branches/PRs; no production framing for a solo hobby project).
- You are operating autonomously; Brandon is not watching. Pause only if blocked on input only he can provide — otherwise finish the deliverable in this run.

## Success criteria

The run succeeds only if all of these hold, and fails otherwise:

- Every claimed failure pattern cites at least one concrete transcript or memory-file instance, or is explicitly labeled assumed/unknown.
- The brainstorm contains at least one serious minimal option and at least one serious ambitious option, each with real costs and failure modes — not strawmen.
- The challenge section changes something: it kills, shrinks, or visibly hardens the recommendation, and says how.
- The verdict is one of the three allowed values and the phased plan's first phase is small enough to ship and evaluate on its own.
- No file other than the deliverable was created or modified.
