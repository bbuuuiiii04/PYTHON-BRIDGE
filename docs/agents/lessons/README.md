---
doc_status: current
truth_level: code-and-history-grounded
last_verified_commit: 9705363
last_verified_date: 2026-07-03
validation_scope: agent workflow lessons only; verify before reuse
---

# Agent Lessons

Durable cross-agent corrections live here when a mistake is likely to recur.
Verify every lesson against current code, docs, and git history before relying
on it. One lesson per file; keep each lesson to 15 lines or fewer. Link lessons
from future specs only when they are actually relied on.

This store never overrides executable code, change contracts, the active-work
registry, subsystem cards, or git history.

| File | Hook |
|---|---|
| `checker-glob-blindspots.md` | Sanity-check advisory checker resolved-file counts. |
| `registry-rows-are-indexes.md` | Keep registry cells as pointers, not changelogs. |
| `prompts-live-in-the-repo.md` | Do not strand agent prompts in `$HOME`. |
| `awr-ids-grep-before-assign.md` | Grep existing AWR IDs before assigning the next one. |
| `index-labels-need-grep-gates.md` | Pair doc-index truth work with explicit grep gates. |
| `tmux-tui-submit-separately.md` | Send tmux Codex TUI text and Enter separately. |
| `stop-hook-autosync-races-agents.md` | Guard against global Stop-hook auto-sync races. |
