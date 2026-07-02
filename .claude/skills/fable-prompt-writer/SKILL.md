---
name: fable-prompt-writer
description: Use when Brandon asks Codex or Claude to make, write, revise, or review a Claude Fable 5 prompt, Fable handoff, Fable code-review prompt, Fable audit prompt, final-sufficiency prompt, quota-safe Fable prompt, or Fable safeguard-aware prompt that should stay on Fable 5. Generates prompt text only; does not run Fable tasks, implement code, inspect binaries, perform the review/audit, or mutate repo/runtime state.
---

# Fable Prompt Writer

Create high-quality Fable 5 prompts for Brandon's agent workflow. The output is the prompt or prompt file only.

## Read First

For repo work, read:
1. `AGENTS.md`
2. `docs/prompts/guides/fable5_prompt_generation_policy.md`
3. The smallest relevant prompt template under `docs/prompts/templates/`
4. Only the user-named docs, commits, files, evidence packets, or status docs needed to ground the prompt

Do not inspect production bridge code unless the prompt needs exact code evidence and the user scope allows it.

## Use Fable 5 When

- The task is hard, ambiguous, multi-source, or long-horizon.
- Brandon needs adversarial review, spec synthesis, final sufficiency, cross-agent orchestration, or a one-shot handoff that must be unusually rigorous.
- The prompt must preserve scope boundaries, evidence labels, and exact success criteria across many moving parts.
- A weaker/cheaper model would likely miss subtle contradictions, hidden risk, or incomplete proof.

## Do Not Use Fable 5 When

- The task is a routine edit, small bugfix, shell lookup, summary, copy edit, or narrow code review.
- Brandon wants Codex to implement now; then write a Codex task or implement directly instead of escalating to Fable.
- The task would ask Fable to expose hidden reasoning or chain-of-thought.
- The subject sits in a high-blocking area for Fable 5: offensive cybersecurity, most biology/chemistry/life-sciences requests, extraction of summarized thinking, or frontier LLM infrastructure such as distributed training, accelerator design, or kernel work for non-standard chips.
- The evidence packet is too thin for a useful Fable result; first ask for or gather the missing concrete inputs.

## Effort

- `low`: prompt polish, compression, or a small quota-safe rewrite.
- `medium`: normal prompt drafting, small review prompts, or clear evidence packets.
- `high`: default for Brandon's serious Fable prompts.
- `xhigh`: adversarial review, final sufficiency, high ambiguity, safety-sensitive planning, or work that must survive one-shot execution.
- `max`: only when Brandon explicitly asks for maximum depth or the failure cost clearly justifies quota burn.

If using Fable is questionable, write a quota-safe prompt that first asks Fable to either proceed or recommend a cheaper model with reasons.

## Default Boundary Policy

For prompt-generation or spec-only Fable tasks, default to:
- no tools
- no shell
- no broad repo search
- no accidental skill invocation
- no implementation
- no live/runtime/hardware mutation

Do not encode that as "Fable must never use tools." If the generated prompt needs tools, state exactly:
- which tools or commands are allowed
- whether they are read-only or can write
- which paths, files, commits, or artifacts are in scope
- why tool use is necessary for the deliverable
- which actions remain forbidden

For `rb_ss_bridge_v2`, bridge code implementation remains Codex-owned unless the current repo instructions say otherwise. Fable reasons, plans, audits, or reviews; Codex implements.

## Safeguard Preflight

Never write a prompt that tries to bypass, jailbreak, disable, evade, or work around Fable safeguards. For benign bridge work, reduce false positives by making the request clearly safe:
- State the concrete benign domain: local DJ lighting bridge, prompt/spec/review workflow, or repo documentation.
- State that the task is not cybersecurity, exploit development, malware, vulnerability discovery, biological lab work, chemistry, life sciences, model distillation, or hidden-reasoning extraction.
- Avoid unnecessary words that make the request look like cyber or bio work. Do not use "exploit", "attack", "payload", "malware", "bypass", "jailbreak", "vulnerability", "bioweapon", or similar terms unless the user-provided evidence truly requires them.
- If reviewing code, scope it as normal software correctness, maintainability, tests, runtime safety, and operator behavior. Do not ask for offensive security analysis unless Brandon explicitly asks and the prompt routes to an appropriate model/program.
- Keep connectors, memory, web results, and repo files narrow. Fable safeguards review what the model reads, not only the latest user text.
- Brandon has model auto-switching disabled. Do not design prompts that rely on Opus fallback after a Fable block.

Before delivering a Fable prompt, do this preflight:
1. Remove unrelated memory, old prompt text, web snippets, or files that mention high-blocking topics.
2. Replace high-risk words with neutral repo-work terms when the meaning stays accurate.
3. Keep only the exact evidence Fable needs; do not attach broad logs or search results.
4. Put the benign-scope block near the top of the prompt.
5. If the prompt must include high-blocking terms because they are in source evidence, explain they are quoted evidence for benign software review and quote the minimum needed.
6. Keep any "if blocked" retry instructions outside the Fable prompt in Brandon-facing notes, because a blocked Fable prompt may produce no output.

If Fable blocks anyway, generate a new, narrower Fable prompt by reducing evidence scope, removing ambiguous wording, and restating the benign task. Do not retry by adding jailbreak language.

If Brandon says "bypass safeguards," translate that into "avoid accidental false positives for legitimate bridge work." Do not generate jailbreak instructions.

## Prompt Shape

Use this order unless the user's requested format is stricter:
1. Target model and effort.
2. One-line mission.
3. Why this task matters and who the output is for.
4. Deliverable: exact artifact, verdict, spec, prompt, or review output.
5. Evidence packet: files, commits, logs, captures, docs, and what each proves.
6. Source-of-truth order and stale-source warnings.
7. Benign-scope statement.
8. Scope and forbidden actions.
9. Allowed tools, if any, with exact limits.
10. Work procedure: read, verify, attack assumptions, produce the deliverable.
11. Claim discipline: label confirmed, assumed, unknown, and rejected claims.
12. Success criteria and stop conditions.
13. Output format.

Keep the prompt as short as the task allows. Do not re-litigate decisions Brandon already made.

## Hidden Reasoning

Never ask Fable to show, reveal, print, transcribe, or explain its private reasoning. Ask for:
- concise rationale
- evidence-backed findings
- assumptions
- uncertainty labels
- verdicts
- next actions

If reasoning visibility matters, ask for a short evidence trail tied to sources and tool results, not internal chain-of-thought.

## Brandon Workflow Rules

- Lead with the useful prompt, not a lecture about prompt design.
- Preserve Brandon's explicit no-touch, no-live, docs-only, review-only, no-subagent, or no-hardware boundaries.
- Avoid vague praise and soft approvals. Require severity-first findings or a concrete verdict when reviewing.
- Make success criteria falsifiable: files changed, checks run, proof required, ship gate, or rejection condition.
- Separate verified facts from memory, prior prompts, and assumptions.
- If the Fable output will feed Codex, say so plainly and include "Do not implement; write the Codex-executable spec/review only."

## Templates

Use and trim these as starting points:
- `docs/prompts/templates/fable5_prompt_writer_spec_synthesis.md`
- `docs/prompts/templates/fable5_prompt_writer_adversarial_review.md`
- `docs/prompts/templates/fable5_prompt_writer_final_sufficiency.md`
- `docs/prompts/templates/fable5_prompt_writer_quota_safe.md`
