#!/bin/bash
# PreToolUse hook (Claude Code): blocks the two banned footguns mechanically.
# Wired in .claude/settings.local.json. Reads the tool-call JSON on stdin, exits 2
# with a reason on stderr to BLOCK, exits 0 to allow. Any agent family running via
# Claude Code inherits this; Codex/other CLIs get the same rules via AGENTS.md.
# 1) `git clean -fd` — already destroyed multi-GB gitignored capture corpora once.
# 2) raw `python -m rb_ss_bridge_v2` bridge launches — the bridge starts via the
#    operator's menubar/watcher ONLY (single-process invariant, operator visibility).
# ponytail: string match on the command field; a parser is overkill for two rules.
cmd=$(cat | /opt/homebrew/bin/python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)
[[ -z "$cmd" ]] && exit 0
# Strip quoted strings first: banned text inside a commit message / echo is prose,
# not a command (field false-positive: this guard blocked its own commit message).
cmd=$(printf '%s' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
if echo "$cmd" | grep -qE 'git[^|;&]*clean[[:space:]]+-[a-zA-Z]*f'; then
  echo "BLOCKED (repo rule): git clean -f* is banned here — it destroyed gitignored capture corpora once. Delete specific paths explicitly instead." >&2
  exit 2
fi
if echo "$cmd" | grep -qE 'python3?[^|;&]*-m[[:space:]]+rb_ss_bridge_v2([[:space:]]|$)' && ! echo "$cmd" | grep -q 'pgrep'; then
  echo "BLOCKED (repo rule): raw bridge launches are banned — the operator starts the bridge via the menubar (scripts/ss_bridge_watcher.sh). See AGENTS.md live-safety rules." >&2
  exit 2
fi
exit 0
