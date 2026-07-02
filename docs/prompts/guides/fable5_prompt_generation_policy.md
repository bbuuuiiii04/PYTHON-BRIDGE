---
doc_status: current
truth_level: official-docs-and-support-grounded-workflow-adapted
last_verified_commit: c59d78c
last_verified_date: 2026-07-02
validation_scope: Fable 5 prompt-generation policy only; no production bridge behavior, no runtime action, no hardware validation
---

# Fable 5 Prompt Generation Policy

Sources read:
- Anthropic's official "Prompting Claude Fable 5" guide, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5.
- Claude Help Center, "Why Claude switched models in your conversation with Fable 5", https://support.claude.com/en/articles/15363606-why-claude-switched-models-in-your-conversation-with-fable-5.
- Anthropic, "Redeploying Fable 5", https://www.anthropic.com/news/redeploying-fable-5.

This guide adapts that model guidance to Brandon's repo workflow. It is for writing prompts for Fable 5, not for running the Fable task. Brandon has Claude model auto-switching disabled, so Fable prompts should be written to stay on Fable 5. If safeguards trigger, Fable may produce no useful output for that prompt; avoid false positives before sending the prompt.

## When Fable 5 Is Worth It

Use Fable 5 when the prompt needs unusual depth: long-horizon planning, multi-source synthesis, adversarial review, final sufficiency, complex debugging strategy, broad ambiguity, or a one-shot handoff that has to preserve scope and evidence discipline.

Fable 5 is especially useful when Brandon needs the agent to determine next steps from a dense packet, hold instructions over a long run, manage independent subagents, or find subtle code-review/debugging gaps. It is overkill for routine edits.

## When Not To Use Fable 5

Do not spend Fable quota on:
- routine implementation tasks Codex can do directly
- short summaries or copy edits
- exact command lookups
- small prompt polish that can be done locally
- tasks where the evidence packet is missing
- requests that ask for hidden reasoning or chain-of-thought
- offensive cybersecurity, most biology/chemistry/life-sciences requests, model-thinking extraction, or frontier LLM infrastructure tasks that may trigger Fable blocking/refusal

If the job is small, make a compact Codex/Sonnet/Opus prompt instead, or tell Brandon Fable is not buying anything.

## Fable Safeguards And False-Positive Reduction

Do not write prompts intended to bypass, jailbreak, disable, evade, or work around Fable 5 safeguards. Anthropic treats bypass/jailbreak techniques as a safety target. For Brandon's bridge repo, the useful goal is narrower: make legitimate, benign prompt/spec/review work clearly safe so it is less likely to be misclassified.

Fable 5 may block requests in these areas. If model auto-switching is enabled, Claude may rerun the request on Opus 4.8; Brandon has auto-switching disabled, so assume the request pauses/refuses instead:
- offensive cybersecurity techniques, including exploit, malware, and attack tooling requests
- most biology, chemistry, and life-sciences requests
- attempts to extract Fable's summarized thinking
- a narrow set of frontier LLM development tasks, including distributed training infrastructure, ML accelerator design, and kernel development for certain non-standard chips

The checks can inspect everything Fable reads, not just the latest message. Memory, connector content, web results, and files can accidentally trigger blocking. Keep evidence packets narrow and relevant.

For benign bridge prompts, include a short safety-context block:

```text
This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.
```

Trim or replace high-risk wording when it is not necessary. Prefer "adversarial review for correctness" over "attack this system"; "regression risk" over "exploit"; "boundary violation" over "bypass"; "test fixture" over "payload". If the source artifact itself contains risky wording, quote only the minimum needed and explain why it is benign context.

If Fable still blocks or refuses, do not keep retrying with jailbreak wording and do not route the same task to Opus unless Brandon explicitly asks. Ask the next agent to report the visible trigger if available and suggest a narrower Fable retry prompt.

## Preflight Checklist Before Brandon Runs Fable

Run this before giving Brandon a Fable prompt:
1. Remove unrelated conversation history, memory, old prompts, broad search output, or attachments.
2. Keep only the exact files, commits, snippets, logs, screenshots, or evidence rows needed for the prompt.
3. Replace risky words when they are not essential: use "strict review" instead of "attack", "boundary violation" instead of "bypass", "test input" instead of "payload", "bug" instead of "vulnerability", and "normal software correctness" instead of "cybersecurity".
4. If risky source text must be included, quote the smallest necessary excerpt and state why it is benign evidence.
5. Put the benign safety-context block in the first screen of the prompt.
6. Do not ask Fable to reveal summarized thinking or chain-of-thought.
7. Do not ask Fable to perform offensive security, biology/chemistry/life-sciences, model distillation, or frontier LLM infrastructure work.
8. If the prompt needs code review, define it as read-only normal software correctness, tests, maintainability, runtime behavior, and operator safety.
9. Provide a separate Brandon-facing retry note outside the Fable prompt: if Fable blocks, run a narrower prompt with fewer files and less ambiguous wording.

## Effort Guidance

Use `high` as the default for serious Fable prompts. Use `xhigh` for adversarial review, final sufficiency, safety-sensitive planning, one-shot spec synthesis, or tasks where missing one contradiction is expensive.

Use `medium` for normal prompt generation with a clear packet. Use `low` for compression or a small quota-safe rewrite. Use `max` only when Brandon asks for maximum depth or the cost of a miss clearly justifies it.

Lower effort on Fable can still be strong. If a task is simple but Brandon still wants Fable, make the prompt quota-safe and bounded.

## Quota Discipline

Every Fable prompt should earn its cost. Keep the prompt focused on the hard part:
- Do not ask Fable to rediscover facts already provided.
- Do not bundle unrelated workstreams.
- Do not make it read the whole repo unless that is truly the task.
- Prefer one evidence packet over broad search.
- Give Fable the reason for the request so it can prioritize.
- Tell Fable to act once it has enough information, not to survey options it will not pursue.

For a quota-safe prompt, make Fable first decide whether the task deserves Fable. If not, it should return a smaller prompt for a cheaper agent.

## Tool, Shell, Skill, And Repo Boundaries

Default for prompt-generation/spec-only Fable tasks:
- no tools
- no shell
- no broad repo search
- no accidental skill invocation
- no implementation
- no runtime, hardware, restart, export, capture, process-memory, or config mutation

This is a default, not a permanent ban. If the Fable prompt needs tool use, name the exact allowed access and why it is necessary:
- allowed commands or tools
- read-only versus write access
- allowed paths, files, commits, logs, or evidence directories
- forbidden files and live actions
- expected proof from each allowed tool result

Do not leave tool authority implied. In this repo, a prompt that says "inspect the repo" is too broad unless the task truly needs broad inspection.

## Evidence Grounding

Give Fable a concrete evidence packet:
- exact files and sections
- commits or diff ranges
- command outputs already run
- logs, captures, reports, or review findings
- source-of-truth order
- known stale or historical sources
- explicit unknowns

Require Fable to label claims as confirmed, assumed, unknown, or rejected. Progress and final claims must be tied to evidence from the prompt or from allowed tool results.

Do not let old prompts, memory, or summaries become current truth. They are context unless re-verified.

## Prompt Structure

Use this shape:
1. Target model and effort.
2. Mission in one sentence.
3. Context and why Brandon needs the result.
4. Deliverable and output format.
5. Evidence packet.
6. Source-of-truth order.
7. Benign safety-context block.
8. Scope boundaries and forbidden actions.
9. Allowed tools, if any.
10. Required analysis or review procedure.
11. Claim-labeling rules.
12. Success criteria, verdict taxonomy, and stop conditions.
13. Final self-check.

Make the success criteria falsifiable. Avoid phrases like "be thorough" unless paired with specific surfaces to check.

## Hidden Reasoning

Do not ask Fable to show chain-of-thought, private reasoning, scratchpad, or internal deliberation. Ask for concise rationale, source-tied evidence, uncertainty labels, and verdicts.

If the workflow needs progress visibility, ask for evidence-grounded progress summaries or direct user-facing messages. Do not request hidden thinking.

## Fable Plans, Codex Implements

For Brandon's bridge workflow, keep this split explicit:
- Fable reasons, plans, synthesizes specs, audits, or reviews.
- Codex implements bridge code and runs software checks.

A Fable prompt that should not edit files must say so. If the output is for Codex, ask Fable for a Codex-executable spec with exact files, tasks, tests, no-touch areas, and acceptance criteria.

## Communication Rules

Brandon values direct, concrete prompts:
- lead with the deliverable
- avoid vague praise
- avoid overclaiming
- preserve no-live/no-hardware/no-restart/no-subagent boundaries
- call out uncertainty without burying it
- require severity-first findings for reviews
- require a verdict when a decision is needed
- make the next agent's allowed actions unambiguous

## Templates

Start from:
- `docs/prompts/templates/fable5_prompt_writer_spec_synthesis.md`
- `docs/prompts/templates/fable5_prompt_writer_adversarial_review.md`
- `docs/prompts/templates/fable5_prompt_writer_final_sufficiency.md`
- `docs/prompts/templates/fable5_prompt_writer_quota_safe.md`

Trim templates aggressively. The best Fable prompt is the shortest prompt that preserves the hard constraints and the evidence.
