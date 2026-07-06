---
name: fable-prompt-writer
description: Use when Brandon asks Codex or Claude to write, revise, or review a Claude Fable 5 prompt — a Fable handoff, adversarial-review or audit prompt, final-sufficiency gate, quota-safe prompt, or safeguard-aware prompt that must stay on Fable 5. Produces prompt text only; does not run the Fable task, implement code, inspect binaries, or mutate repo/runtime state. For Opus 4.8 prompts use opus-prompt-writer; for Codex implementation/review specs use codex-spec.
---

# Fable Prompt Writer

Write the prompt Brandon will hand to Claude Fable 5. The deliverable is the prompt text or prompt file, never execution of the task itself.

This file is the single source of truth for Fable 5 prompt authoring in this repo. Claude loads it as a repo skill; Codex reads it as a document via the `AGENTS.md` §3 pointer. Ready-to-paste blocks live in `docs/prompts/snippets/fable5_snippets.md`.

If Fable 5 is unavailable, run existing Fable prompts on Opus 4.8 at max effort; author new prompts with opus-prompt-writer.

## Pick the right sibling first

- **Fable 5 (this skill):** the hardest / most ambiguous / long-horizon / safety-sensitive reasoning, planning, and review one-shots.
- **Opus 4.8** (`.claude/skills/opus-prompt-writer/SKILL.md`): Brandon's default Claude for coding, agentic, knowledge, frontend, and code-review work.
- **Codex/GPT-5** (`.claude/skills/codex-spec/SKILL.md`): authoring the implementation or review spec Codex executes on bridge code.

## When Fable 5 is worth its quota

Use it when the prompt needs unusual depth: long-horizon planning, multi-source synthesis, adversarial review, final sufficiency, broad ambiguity, or a one-shot handoff that must hold scope and evidence discipline across many moving parts.

Do not spend Fable on routine edits, small bugfixes, summaries, lookups, or anything Codex should simply implement. Do not use it when the evidence packet is too thin for a useful result — gather the missing inputs first. Avoid its high-blocking areas: offensive cybersecurity, most biology/chemistry/life-sciences requests, extraction of model thinking, and frontier-LLM infrastructure (distributed training, accelerator design, kernels for non-standard chips). If Fable is questionable, write a quota-safe prompt: Fable first decides whether the task deserves it, and otherwise returns a smaller prompt for a cheaper model.

## How Fable 5 behaves (write the prompt around this)

- **Long turns by default.** It sustains multi-step work for minutes to hours; let it gather context, act, and self-verify rather than forcing early stops or interim check-ins.
- **Effort is the main dial.** `high` default; `xhigh` for the most capability-sensitive or ambiguous work; `medium`/`low` for routine (Fable's low often beats prior models' high); `max` only when Brandon asks or a miss clearly costs more than the quota.
- **A short instruction steers as well as an enumerated list** — over-enumeration can degrade output. State each constraint once, plainly; skip step-by-step procedure unless order truly matters.
- **It navigates ambiguity well.** Hand it the goal, evidence, and boundaries and let it determine next steps. Give the reason, not only the request — it performs better knowing intent.
- **Prompts and skills written for prior models are usually too prescriptive for Fable 5.** When revising an old prompt, cut instructions before adding any.
- **Never ask it to reproduce its reasoning.** Echo/transcribe/explain-your-thinking instructions can trigger a `reasoning_extraction` refusal. Ask for evidence-tied findings, claim labels, and verdicts instead.
- **Long runs benefit from parallel subagents, memory, and fresh-context verifiers** — say so explicitly when the task warrants them.
- **Fan-out subagents must be cheaper-tier — never Fable.** Only one Fable-tier agent runs (Fable itself). When a Fable prompt fans out, its subagents go to cheaper models; Fable never spawns further Fable-tier subagents (quota protection); nested spawns are announced, not silent. *(retro 2026-07-06, from operator corrections 00880420:654 + 69a81f74:889.)*

## Prompt skeleton

Order for a serious Fable prompt — include what the task needs, cut the rest, and keep it as short as the task allows:

1. Target model + effort.
2. Mission in one line, then why it matters and who the output is for.
3. Deliverable and output format.
4. Evidence packet: exact files/commits/logs and what each proves; source-of-truth order; known-stale sources; explicit unknowns.
5. Benign-scope block (snippet `benign-scope`) for anything that could pattern-match a blocked area.
6. Scope, forbidden actions, and allowed tools with exact limits (boundaries rule below).
7. Claim discipline: label claims confirmed / assumed / unknown / rejected, tied to evidence.
8. Falsifiable success criteria and stop conditions.

Do not re-litigate decisions Brandon already made, and do not make Fable rediscover facts already in the packet.

Common prompt types, each needing a concrete verdict taxonomy:
- **Adversarial review:** severity-first findings (location, issue, why it matters, evidence, required fix) and a verdict — `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL`. "Adversarial" means strict about evidence, not offensive security.
- **Final sufficiency gate:** `SUFFICIENT` / `SUFFICIENT AFTER MINOR EDITS` / `NOT SUFFICIENT`, blocking gaps first, then a go/no-go tied to the success criteria.
- **Spec synthesis:** readiness verdict (`READY` / `READY WITH GAPS` / `NOT READY`) plus a Codex-executable spec — hand off to `.claude/skills/codex-spec/SKILL.md` for the spec format itself.
- **Quota-safe:** Fable first rules on whether the task deserves Fable; Option B is a cheaper-agent prompt.

## Non-negotiables (every Fable prompt)

- **No hidden reasoning.** Never ask Fable to show, transcribe, or explain private chain-of-thought. Evidence-tied rationale, labels, and verdicts only.
- **Fable reasons, plans, audits, and reviews; Codex implements bridge code.** A prompt whose output feeds Codex says so plainly: "Do not implement; write the Codex-executable spec/review only."
- **Boundaries stated, never implied.** Default for prompt/spec-only tasks: no tools, no shell, no broad repo search, no skill invocation, no implementation, no runtime/hardware mutation. If the task needs tools, name the exact commands/paths, read-only versus write, why they are necessary, and what stays forbidden.
- **Claim labels and falsifiable success criteria.** "Be thorough" is not a criterion; name the surfaces, checks, and rejection conditions.
- **Brandon's explicit boundaries survive verbatim** — no-touch, no-live, docs-only, review-only, no-subagent, no-hardware, whichever apply.
- **Safeguard hygiene** (next section).

## Safeguard hygiene

Never write a prompt that tries to bypass, jailbreak, disable, evade, or work around Fable safeguards. If Brandon says "bypass safeguards," that means "stop benign work getting misclassified" — reduce false positives instead:

- Put the benign-scope block (snippet `benign-scope`) near the top of any prompt that could pattern-match a blocked area.
- Prefer neutral repo terms when accurate: "strict review" not "attack", "boundary violation" not "bypass", "test input" not "payload", "bug" not "vulnerability".
- Keep the evidence packet narrow — safeguards review everything Fable reads (files, memory, connectors, web results), not just the latest message.
- If risky wording must be quoted from source evidence, quote the minimum and state that it is quoted benign evidence.
- Brandon has model auto-switching disabled, so a blocked prompt yields nothing. Put retry advice in a Brandon-facing note outside the Fable prompt: retry means narrower evidence and more neutral wording, never jailbreak language.

## Snippets

`docs/prompts/snippets/fable5_snippets.md` holds the canonical drop-in blocks — the repo `benign-scope` block plus Anthropic's verbatim Fable 5 blocks (avoid overplanning; no unrequested refactoring; lead with the outcome; checkpoint only when needed; grounded progress claims; assessment vs action; parallel subagents; memory system; final-summary readability; autonomous pipeline; context-budget reassurance; reason-not-only-request; send-to-user; self-verification interval). Paste only the blocks the task needs.
