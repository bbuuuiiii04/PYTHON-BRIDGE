---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 141480a
last_verified_date: 2026-07-02
validation_scope: prompt-directory routing only; no production bridge behavior, runtime action, or hardware validation
---

# Prompt Artifacts

One prompt/spec-authoring skill per agent Brandon drives. Claude autoloads them as repo skills; Codex reads them as standalone documents via `AGENTS.md` §3:

- `.claude/skills/fable-prompt-writer/SKILL.md` — Claude Fable 5 prompts: the hardest / most ambiguous / long-horizon / safety-sensitive reasoning, planning, and review one-shots.
- `.claude/skills/opus-prompt-writer/SKILL.md` — Claude Opus 4.8 prompts: default coding, agentic, knowledge, frontend, and code-review work.
- `.claude/skills/codex-spec/SKILL.md` — Codex/GPT-5 implementation and review specs.

All three are prompt-only: they produce prompt/spec text and never run the task, implement code, inspect binaries, or touch runtime state.

## Directories

- `active/` - prompts that may still be actionable after branch, file, and status validation.
- `completed/` - historical or superseded prompt artifacts.
- `reviews/` - review and audit handoffs.
- `snippets/` - canonical per-model drop-in blocks (Fable 5, Opus 4.8, Codex/GPT-5) from each vendor's official prompting guide.

Old prompts are context, not authority. Verify current files, commits, and status before reusing them.
