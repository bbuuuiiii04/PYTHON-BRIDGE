---
name: opus-prompt-writer
description: Use when Brandon asks Codex or Claude to write, revise, or review a Claude Opus 4.8 prompt — a coding or agentic handoff, code-review prompt, frontend/design prompt, knowledge task, or any prompt that should run on Opus 4.8 rather than Fable 5. Produces prompt text only; does not run the Opus task, implement code, or mutate repo/runtime state. For Fable 5 prompts use fable-prompt-writer; for Codex implementation/review specs use codex-spec.
---

# Opus Prompt Writer

Write the prompt Brandon will hand to Claude Opus 4.8. The deliverable is the prompt text or prompt file, never execution of the task itself.

This file is the single source of truth for Opus 4.8 prompt authoring in this repo. Claude loads it as a repo skill; Codex reads it as a document via the `AGENTS.md` §3 pointer. Ready-to-paste blocks live in `docs/prompts/snippets/opus48_snippets.md`.

## Pick the right sibling first

- **Opus 4.8 (this skill):** Brandon's default Claude for coding, agentic, knowledge, frontend, and code-review work.
- **Fable 5** (`.claude/skills/fable-prompt-writer/SKILL.md`): only the hardest / most ambiguous / long-horizon / safety-sensitive reasoning, planning, and review one-shots.
- **Codex/GPT-5** (`.claude/skills/codex-spec/SKILL.md`): authoring the implementation or review spec Codex executes on bridge code.

## When Opus 4.8 is the right target

Opus is the workhorse: everyday coding, agentic runs, knowledge questions, frontend/design, and code review. It is also the practical fallback when legitimate benign work keeps tripping Fable safeguards — Opus 4.8 carries no aggressive safety-classifier blocking, so **do not copy Fable's benign-scope block or safeguard preflight into an Opus prompt**; that ceremony is dead weight here. A plain statement of the task is enough.

## How Opus 4.8 behaves (write the prompt around this)

The sharpest difference from Fable 5: **Opus follows instructions literally, especially at lower effort.** It does not silently generalize one example to the rest of the task and does not infer unrequested work. State scope explicitly — write "apply this to every section, not just the first" (snippet `apply-broadly`) rather than trusting the model to extrapolate.

- **Effort matters more than on any prior Opus.** `xhigh` is the best default for coding and agentic prompts; `high` is the minimum for anything intelligence-sensitive; `max` can overthink with diminishing returns; `medium` for cost-sensitive routine work; `low` only for short, tightly scoped, latency-sensitive tasks (real under-thinking risk). Raise effort rather than prompting around shallow reasoning. At `xhigh`/`max`, note in the prompt packet that Brandon should set a large max-output-token budget (~64k).
- **Adaptive thinking is off unless enabled, and steerable.** Large or complex system prompts can over-trigger thinking; add `reduce-thinking` when latency matters, or `low-effort-multistep` when a low-effort prompt still needs multi-step reasoning.
- **It favors reasoning over tool calls.** If the task needs the model to actually run, search, or verify things, raise effort or state explicitly when and how to use tools.
- **It spawns fewer subagents by default** (the opposite of Fable). To fan out, instruct it explicitly (snippet `subagent-control`).
- **Progress updates are strong by default.** Delete forced interim-status scaffolding from older prompts; if calibration is off, describe the desired updates and give one example.
- **Response length calibrates to task complexity.** If the use case needs a fixed style or length, say so with positive concision examples (snippet `concise-output`) — they beat "don't be verbose" instructions.
- **Tone is direct and opinionated** with minimal validation-forward phrasing and sparing emoji. Re-check any voice/persona prompt written for an older model.
- **Code review is literal about severity bars.** "Only report high-severity issues" is followed faithfully and silently drops real low-severity findings. For coverage, paste `review-coverage` and filter downstream; for a single pass, give a concrete bar (`review-concrete-bar`).
- **Design/frontend has a persistent house style** — cream/off-white (~`#F4F1EA`), serif display faces, italic accents, terracotta/amber. Override it with a concrete alternative spec, or have it propose options first (snippet `design-options-first`); a bare "don't use cream" just shifts to another fixed palette. Use `frontend-aesthetics` to steer away from generic-AI styling.

## Prompt skeleton

Same shape as the Fable skeleton, minus the safeguard ceremony, plus explicit breadth. Include what the task needs, cut the rest:

1. Target model + effort (and the ~64k max-output note at `xhigh`/`max`).
2. Mission in one line, then why it matters and who the output is for.
3. Deliverable and output format — with scope stated explicitly ("every X", "all Y in Z"), never implied by an example.
4. Evidence packet: exact files/commits/logs and what each proves; source-of-truth order; explicit unknowns.
5. Scope, forbidden actions, and allowed tools with exact limits.
6. Claim discipline: label claims confirmed / assumed / unknown, tied to evidence.
7. Falsifiable success criteria and stop conditions.

## Non-negotiables (every Opus prompt)

- **No hidden reasoning.** Never ask Opus to show, transcribe, or explain private chain-of-thought. Evidence-tied rationale, labels, and verdicts only.
- **Opus reasons, plans, reviews, and designs; Codex implements bridge code** unless a current repo instruction explicitly says otherwise. A prompt whose output feeds Codex says: "Do not implement; write the Codex-executable spec/review only."
- **Claim labels and falsifiable success criteria**, same discipline as every other prompt in this suite.
- **Brandon's explicit boundaries survive verbatim** — no-touch, no-live, docs-only, review-only, no-subagent, no-hardware, whichever apply.
- **No safety ceremony.** Do not import Fable's benign-scope/preflight blocks; do not write bypass/jailbreak instructions for any model.

## Snippets

`docs/prompts/snippets/opus48_snippets.md` holds Anthropic's verbatim Opus 4.8 blocks: concise output; low-effort multi-step; reduce thinking; warmer tone; subagent control; apply broadly; frontend aesthetics; design options first; review coverage; review concrete bar. Paste only the blocks the task needs.
