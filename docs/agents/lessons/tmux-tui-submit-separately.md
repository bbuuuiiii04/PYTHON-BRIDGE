---
doc_status: current
truth_level: evidence-cited
last_verified_commit: 9705363
last_verified_date: 2026-07-03
---

# Tmux TUI Submit Separately

When driving the Codex TUI through tmux, send the text and Enter as two
separate `send-keys` calls.
A trailing Enter in one call can be swallowed as paste input instead of
submitting the prompt.
Evidence: 2026-07-03 phase-4 audit.
