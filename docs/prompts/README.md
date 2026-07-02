---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: c59d78c
last_verified_date: 2026-07-02
validation_scope: prompt-directory routing only; no production bridge behavior, runtime action, or hardware validation
---

# Prompt Artifacts

Before generating a Claude Fable 5 prompt, handoff, review prompt, or final-sufficiency prompt for Brandon, use:

- `.claude/skills/fable-prompt-writer/SKILL.md`
- `docs/prompts/guides/fable5_prompt_generation_policy.md`

The Fable prompt-writer skill is prompt-only. It does not run Fable tasks, implement code, review code, inspect binaries, audit the repo, or perform live/runtime work.

## Directories

- `active/` - prompts that may still be actionable after branch, file, and status validation.
- `completed/` - historical or superseded prompt artifacts.
- `reviews/` - review and audit handoffs.
- `guides/` - reusable prompt-authoring policy.
- `templates/` - compact reusable prompt templates.

Old prompts are context, not authority. Verify current files, commits, and status before reusing them.
