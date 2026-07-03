---
name: codex-spec
description: Use when Brandon asks Codex or Claude to author, tighten, or review a Codex implementation or review spec for rb_ss_bridge_v2 — docs/plans/active/*_spec.md handoffs, Part A–E implementation prompts, live-safety handoffs, or Claude-to-Codex planning artifacts. Scaffolds the verified spec format and pre-handoff checklist so Codex can implement without guessing and without live-show risk. For Fable 5 prompts use fable-prompt-writer; for Opus 4.8 prompts use opus-prompt-writer.
---

# Codex Implementation / Review Spec

Claude (or Codex itself) authors the spec; **Codex implements bridge code.** The goal is a spec Codex can execute without guessing — and that cannot break the live show.

This file is the single source of truth for Codex spec authoring; the old `~/.claude/skills/codex-spec` and `~/.codex/skills/rbss-codex-spec` copies are retired redirects. Claude loads it as a repo skill; Codex reads it as a document via the `AGENTS.md` §3 pointer. Ready-to-paste blocks live in `docs/prompts/snippets/codex_gpt5_snippets.md`.

## Pick the right sibling first

- **Codex/GPT-5 (this skill):** the implementation or review spec Codex executes on bridge code.
- **Fable 5** (`.claude/skills/fable-prompt-writer/SKILL.md`): the hardest / most ambiguous / long-horizon / safety-sensitive reasoning, planning, and review one-shots.
- **Opus 4.8** (`.claude/skills/opus-prompt-writer/SKILL.md`): Brandon's default Claude coding / agentic / knowledge / frontend / code-review work.

## Output

Default target: `docs/plans/active/<slug>_spec.md`, with the repo doc frontmatter header, classified in `docs/architecture/doc_index.md` or `docs/status/active_work_registry.md`, using only §10-allowed status language. If Brandon asked only for a prompt/spec in chat, paste it there instead of creating a file. Match the tone of existing active specs, but never copy their claims without re-verification.

## How Codex behaves (write the spec around this)

- **It is an autonomous senior engineer.** Given a direction, it gathers context, plans, implements, tests, and refines end-to-end within the turn, with a bias to action and reasonable assumptions. So front-load everything: full task, intent, constraints, and root cause in the first handoff. Ambiguous or progressively revealed scope wastes its autonomy; a trickle of micro-steps wastes its persistence.
- **Scope must be absolute.** Codex may work in a dirty worktree and will act on whatever the spec permits. State out-of-scope files/subsystems and behavior-that-must-not-change explicitly; include the `dirty-worktree` snippet so it never reverts unrelated changes or uses destructive git.
- **Error-handling expectations are load-bearing.** Codex's own guidance bans broad try/catch, success-shaped fallbacks, and silent early-returns — but a spec that hand-waves failure paths invites them anyway. State the expected failure behavior per task: propagate, fail closed, or surface, never swallow.
- **It conforms to existing code.** It follows repo conventions, searches for prior art before adding helpers, and batches parallel reads. Name the exact files, existing helpers, and authority variables the task must reuse so its first read batch and its reuse decisions are right.
- **Plan discipline:** it skips plans for trivial work, never makes single-step plans, updates the plan per substep, and must reconcile every TODO to Done/Blocked/Cancelled before finishing. A concrete Part E acceptance list is what makes that closure checkable.
- **Effort:** `medium` is a good interactive default; `high`/`xhigh` for the hardest tasks. Codex spends fewer thinking tokens than Claude models — the spec's precision substitutes for rumination.

## Spec skeleton (Part A–E)

```markdown
# Codex Implementation Spec - <Title>

## Part A - Context & Root Cause (verified; read, do not implement)
- What happens today, why, and the root cause. Cite real file:line.
- Label every claim: [confirmed] (read in current code / ran), [assumed], or [unknown].

## Part B - Tasks (implement exactly, in order; commit after each if requested)
### Absolute Rules
- Out-of-scope files/subsystems Codex must not touch.
- Behavior that must not change.
- Expected error handling: propagate/fail closed/surface — no broad try/catch, no silent fallbacks.
### Task 1 - `path/to/file.py`: <change>
<exact code or diff; exact function/attribute/iteration names — no "use the X tag" hand-waving>
### Task 2 - ...

## Part C - Invariants That MUST Still Hold (live safety)
- Runtime/live-mixing invariants that cannot regress (AGENTS.md §6, docs/architecture/runtime_invariants.md).

## Part D - Tests
- New/extended tests. Require a pure-function seam for any algorithm (no on-disk/subprocess dependency).

## Part E - Acceptance (definition of done)
- Checklist Codex must satisfy before calling it done, including contract docs_update + required checks.

## When You Finish
- What to report back: changed files, tests/checks run, review targets.
- Plain-language operator summary: expected live behavior, unchanged behavior, visible watchpoints,
  verification evidence, unverified hardware assumptions, rollback/toggle/restart notes.
```

## Pre-handoff checklist

Do **not** call a spec ready for Codex until all applicable checks pass:

1. **Every claim labeled** confirmed / assumed / unknown; unknowns surfaced, not buried.
2. **Verified against CURRENT code** — re-check every file:line now; memories and old specs may be stale.
3. **Pending-state guard** — if two features can modify output in the same tick, the spec checks ALL pending-state fields that could be active, not just the new features against each other.
4. **Mode-transition cleanup** — every new state field is cleaned up on EVERY transition path (idle / scripted / autoloop / …), not only the path that introduces it.
5. **Third-party API completeness** — exact call sequence (attribute names, iteration method, endpoint, headers, payload shape), not just the data format.
6. **Reuse existing authority variables and resolution logic** — e.g. the canonical `autoloop_arm_bpm`, not a local `bpm`; do not invent parallel file-resolution or extension logic.
7. **Pure-function test seam** — algorithm correctness testable without files or subprocess.
8. **Live safety explicit** — Part C invariants stated; directional/edge safety (e.g. snap forward only); hot paths gain no blocking I/O; never clobber live BPM-follow or pending transition-arm state.
9. **Adversarial self-review** — attack the spec ("find how this breaks"), name a concrete failure scenario and how the spec prevents it, before handoff. "Does this look good?" is not a review.

## Review specs

When the ask is a Codex **review**, use Codex's review mindset: findings first, ordered by severity, each with file/line references; open questions and assumptions after; a brief change summary last; if there are no findings, say so explicitly and name residual risks and testing gaps (snippet `review-mindset`). Tell Codex to report everything, including uncertain and low-severity findings, when coverage matters — filter downstream, not in the review.

## Repo constraints

- **Contract-first:** before bridge code behavior changes, identify the matching contract in `docs/agents/change_contracts.yml`; the spec's Part E must include updating every `docs_update` doc and running that contract's checks.
- **Docs-only work must not change runtime behavior.**
- **Status language:** §10-allowed terms only; never upgrade beyond SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED without evidence.
- **Scope exactness:** if Brandon asks for Step 1, Phase 1, read-only diagnosis, or a prompt only, the spec stays there.
- **No hidden reasoning:** a spec never asks any model to reveal, transcribe, or explain its private chain-of-thought.

## Snippets

`docs/prompts/snippets/codex_gpt5_snippets.md` holds OpenAI's verbatim GPT-5/Codex blocks: autonomy and persistence; implementation discipline; batched parallel reads; dirty-worktree safety; plan discipline/closure; review mindset. Paste only the blocks the spec needs.
