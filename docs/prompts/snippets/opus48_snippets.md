---
doc_status: current
truth_level: official-docs-grounded
last_verified_commit: 141480a
last_verified_date: 2026-07-02
validation_scope: reusable Claude Opus 4.8 prompt snippet library; prompt text only; no production bridge behavior, runtime action, or hardware validation
---

# Opus 4.8 Snippets

Canonical drop-in blocks for prompts targeting Claude Opus 4.8, verbatim from Anthropic's official "Prompting Claude Opus 4.8" guide (platform.claude.com). Paste only what the task needs; see `.claude/skills/opus-prompt-writer/SKILL.md` for when and how.

## `concise-output` — when the use case needs short responses

> Provide concise, focused responses. Skip non-essential context, and keep examples minimal.

## `low-effort-multistep` — low-effort prompt that still needs real reasoning

> This task involves multi-step reasoning. Think carefully through the problem before responding.

## `reduce-thinking` — latency-sensitive prompts where thinking over-triggers

> Thinking adds latency and should only be used when it will meaningfully improve answer quality — typically for problems that require multi-step reasoning. When in doubt, respond directly.

## `warmer-tone` — if Opus's direct default tone is too blunt for the use case

> Use a warm, collaborative tone. Acknowledge the user's framing before answering.

## `subagent-control` — steer subagent spawning (Opus fans out less than Fable)

> Do not spawn a subagent for work you can complete directly in a single response (e.g. refactoring a function you can already see).
>
> Spawn multiple subagents in the same turn when fanning out across items or reading multiple files.

## `apply-broadly` — counter literal instruction-following

> Apply this formatting to every section, not just the first one.

## `frontend-aesthetics` — avoid generic-AI styling in frontend prompts

> \<frontend_aesthetics\>
> NEVER use generic AI-generated aesthetics like overused font families (Inter, Roboto, Arial, system fonts), cliched color schemes (particularly purple gradients on white or dark backgrounds), predictable layouts and component patterns, and cookie-cutter design that lacks context-specific character. Use unique fonts, cohesive colors and themes, and animations for effects and micro-interactions.
> \</frontend_aesthetics\>

## `design-options-first` — break the cream/serif house style deliberately

> Before building, propose 4 distinct visual directions tailored to this brief (each as: bg hex / accent hex / typeface — one-line rationale). Ask the user to pick one, then implement only that direction.

## `review-coverage` — code review where recall matters (filter downstream)

> Report every issue you find, including ones you are uncertain about or consider low-severity. Do not filter for importance or confidence at this stage - a separate verification step will do that. Your goal here is coverage: it is better to surface a finding that later gets filtered out than to silently drop a real bug. For each finding, include your confidence level and an estimated severity so a downstream filter can rank them.

## `review-concrete-bar` — single-pass review with a concrete severity bar

> report any bugs that could cause incorrect behavior, a test failure, or a misleading result; only omit nits like pure style or naming preferences.
