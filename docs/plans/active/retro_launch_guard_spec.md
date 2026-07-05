---
doc_status: current
truth_level: code-verified spec
last_verified_date: 2026-07-04
validation_scope: Claude Code agent-tooling guard only (hook script + tests + settings registration); no bridge runtime behavior change, no live process, no hardware action authorized
---

# Codex Implementation Spec - Raw Bridge-Launch Guard (AWR-127 Phase 2)

> You may be in a dirty git worktree. NEVER revert existing changes you did not make unless
> explicitly requested. If asked to make edits and there are unrelated changes in those files, do
> not revert them. If you notice unexpected changes you didn't make, STOP and ask how to proceed.
> NEVER use destructive commands like `git reset --hard` or `git checkout --` unless specifically
> requested.

> Act as a discerning engineer: optimize for correctness, clarity, and reliability over speed;
> avoid risky shortcuts, speculative changes, and messy hacks; cover the root cause or core ask,
> not just a symptom. Tight error handling: no broad try/catch and no success-shaped fallbacks —
> except where this spec explicitly mandates fail-open behavior for the guard itself.

## Part A - Context & Root Cause (verified; read, do not implement)

Agents have repeatedly launched the bridge with a raw `python3 -m rb_ss_bridge_v2` command instead
of the visible menubar/watcher path. The operator cannot see raw launches and has corrected this at
least twice, ~26 days apart: 2026-06-04 ("why cant i just launch it through the menubar like
normal") and 2026-06-30 ("why do you keep launching the bridge without the menu bar script?").
[confirmed — both verified at their transcript lines during the AWR-127 evidence run 2026-07-04]

A prose rule exists (bridge memory `feedback_bridge_launch_via_menubar_only`) and was violated
anyway — this is a compliance failure, not a capture gap, so AWR-127
(`docs/plans/active/self_learning_workflow_design.md`, §2 Option D / §3 Phase 2) promotes it to the
strongest enforcement tier: a deterministic PreToolUse hook that denies the raw launch command and
echoes the correct path. [confirmed — design doc exists at that path]

Facts Codex must build on:
- Canonical watcher: `/Users/bbui/rb_ss_bridge_v2/scripts/ss_bridge_watcher.sh` (repo copy; the old
  home-dir copy was deleted 2026-07-03). Correct launch:
  `RBSS_BRIDGE_MANUAL=1 nohup /Users/bbui/rb_ss_bridge_v2/scripts/ss_bridge_watcher.sh &`.
  [confirmed — script read 2026-07-04]
- Registration target is the GLOBAL `~/.claude/settings.json`, not the bridge repo's
  `.claude/settings.local.json`: both historical violations happened in home-directory sessions,
  outside bridge-repo hook scope. [confirmed — transcript store locations checked 2026-07-04]
- `~/.claude/settings.json` already contains a `hooks.PreToolUse` array with ONE entry
  (matcher `""`, vibeyard telemetry). It also holds Stop/SessionStart/etc. vibeyard hooks, model,
  statusLine, plugins. All of it must survive untouched. [confirmed — file read 2026-07-04]
- Claude Code PreToolUse hook contract: hook receives JSON on stdin (fields include `tool_name`,
  `tool_input.command` for Bash); exit code 2 blocks the tool call and feeds stderr back to the
  model; exit 0 allows; other nonzero = non-blocking error. [confirmed per Claude Code hooks
  documentation; runtime-verified only at the operator probe in Part E]
- Python entrypoint: `python3 -m rb_ss_bridge_v2` (package name, flat modules). Submodule runs like
  `python3 -m rb_ss_bridge_v2.probe_live_bpm` are legitimate tooling and MUST NOT be blocked.
  [confirmed — AGENTS.md §4]

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `tools/claude_hooks/deny_raw_bridge_launch.py` (new),
  `tests/test_deny_raw_bridge_launch.py` (new), `~/.claude/settings.json` (surgical insertion).
- Do NOT touch bridge runtime code, `config/`, the watcher script, the bridge repo's
  `.claude/settings.local.json`, or any other key in `~/.claude/settings.json` (model, statusLine,
  plugins, vibeyard hook entries).
- Do NOT launch the bridge, any watcher, or any live process. No `git reset`/`git checkout --`.
- Error handling: the guard itself is MANDATED fail-open — any exception while parsing input exits
  0. A broken guard must never block unrelated work. Everywhere else, normal discipline (no broad
  try/catch).

### Task 1 - `tools/claude_hooks/deny_raw_bridge_launch.py` (new file, exact code)

```python
#!/usr/bin/env python3
"""PreToolUse guard: deny raw `python -m rb_ss_bridge_v2` launches.

Registered globally (~/.claude/settings.json, matcher "Bash"). The bridge must be
launched via the menubar/watcher path so the operator can see it (bridge memory
feedback_bridge_launch_via_menubar_only; AWR-127 Phase 2).
Fail-open: any parse error exits 0 — a broken guard must never block work.
"""
import json
import re
import sys

# python/python3, optional flag tokens (e.g. -u), then -m rb_ss_bridge_v2 as the
# exact module. Submodules (rb_ss_bridge_v2.probe_live_bpm) stay allowed, as do
# pgrep/ps/grep commands that merely mention the module string.
_RAW_LAUNCH = re.compile(
    r"(?<![\w-])python3?(?:\s+-[A-Za-z]\S*)*\s+-m\s+rb_ss_bridge_v2(?![\w.])"
)

DENY_MESSAGE = (
    "Blocked: raw `python -m rb_ss_bridge_v2` launches are banned "
    "(feedback_bridge_launch_via_menubar_only - the operator cannot see raw launches). "
    "Launch via the watcher instead: RBSS_BRIDGE_MANUAL=1 nohup "
    "/Users/bbui/rb_ss_bridge_v2/scripts/ss_bridge_watcher.sh & "
    "Then verify exactly one bridge: ps -ef | grep '\\-m rb_ss_bridge_v2$'"
)


def should_deny(command: str) -> bool:
    return bool(_RAW_LAUNCH.search(command))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") != "Bash":
            return 0
        command = payload.get("tool_input", {}).get("command", "")
    except Exception:
        return 0  # ponytail: fail-open by design — guard bugs must not block unrelated work
    if should_deny(command):
        print(DENY_MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Known, accepted ceiling (do not "fix"): a command that merely quotes the launch string after a real
`python3` invocation with only flag-shaped tokens in between could false-positive; the deny message
explains itself and the agent rewrites. Do not widen the regex, do not add an allowlist env var.

### Task 2 - `tests/test_deny_raw_bridge_launch.py` (new file)

Load the script via `importlib.util.spec_from_file_location` (the `tools/claude_hooks/` dir is not
a package; resolve the path as `Path(__file__).resolve().parents[1] / "tools" / "claude_hooks" /
"deny_raw_bridge_launch.py"`). Test `should_deny` (the pure seam) directly:

MUST deny:
- `python3 -m rb_ss_bridge_v2`
- `python -m rb_ss_bridge_v2`
- `python3 -u -m rb_ss_bridge_v2`
- `nohup python3 -m rb_ss_bridge_v2 &`
- `cd /Users/bbui/rb_ss_bridge_v2 && python3 -m rb_ss_bridge_v2 2>&1 | tee /tmp/bridge.log`
- `RBSS_PLAY_DIRECT=1 python3 -m rb_ss_bridge_v2`

MUST allow:
- `RBSS_BRIDGE_MANUAL=1 nohup /Users/bbui/rb_ss_bridge_v2/scripts/ss_bridge_watcher.sh &`
- `pgrep -f rb_ss_bridge_v2 | wc -l`
- `ps -ef | grep "\-m rb_ss_bridge_v2$"`
- `python3 -m rb_ss_bridge_v2.probe_live_bpm`
- `python3 -m unittest discover tests`
- `python3 -c 'print(1)' && grep -- "-m rb_ss_bridge_v2" tools/claude_hooks/deny_raw_bridge_launch.py`

Also test `main()` behavior with stdin fed via `io.StringIO`/subprocess or by refactoring nothing —
minimum: malformed JSON on stdin exits 0 (fail-open), a denied Bash payload returns 2, a non-Bash
payload returns 0.

### Task 3 - Register in `~/.claude/settings.json`

1. Copy the file to `~/.claude/settings.json.retro_bak` first (leave the backup in place; the
   operator deletes it after confirming).
2. Validate current JSON parses (`python3 -c "import json;json.load(open(...))"`).
3. APPEND a second element to the existing `hooks.PreToolUse` array (do not modify the vibeyard
   element):

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "type": "command",
      "command": "/usr/bin/python3 /Users/bbui/rb_ss_bridge_v2/tools/claude_hooks/deny_raw_bridge_launch.py"
    }
  ]
}
```

4. Validate JSON parses again and diff shows ONLY this addition.
If the repo ever moves, the hook command fails as a non-blocking error (not exit 2) — acceptable,
note it in the report, do not engineer around it.

## Part C - Invariants That MUST Still Hold (live safety)

- Zero bridge runtime behavior change: no bridge module, config, or watcher file is touched; the
  200 Hz push loop and all runtime invariants (AGENTS.md §6) are untouched by construction.
- The guard is fail-open: parser errors, missing fields, or non-Bash tools always exit 0.
- The correct watcher launch command (`...scripts/ss_bridge_watcher.sh`) must NOT match the deny
  regex (it contains no `python … -m rb_ss_bridge_v2` text).
- Every existing hook in `~/.claude/settings.json` (vibeyard telemetry, Stop, SessionStart, …)
  keeps firing exactly as before — the edit is append-only inside `hooks.PreToolUse`.

## Part D - Tests

`tests/test_deny_raw_bridge_launch.py` per Task 2 — pure-function seam (`should_deny`) requires no
files, subprocesses, or hook runtime. Run the full suite: `python3 -m unittest discover tests`.

## Part E - Acceptance (definition of done)

- [ ] `python3 -m unittest tests.test_deny_raw_bridge_launch` green; full
      `python3 -m unittest discover tests` green (no existing test regressions).
- [ ] `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
      `python3 tools/check_docs_drift.py` all pass (no docs changed by this spec, so these must
      stay green as-is).
- [ ] `~/.claude/settings.json` parses; only change is the appended PreToolUse element; backup
      `~/.claude/settings.json.retro_bak` exists.
- [ ] No change contract applies (agent tooling, no bridge runtime behavior change) — confirm no
      `change_contracts.yml` entry claims `tools/claude_hooks/` and say so in the report.
- [ ] NOT part of Codex's run: the live probe. The operator (or a fresh Claude session in any
      directory) later attempts `python3 -m rb_ss_bridge_v2` and must see the deny message; record
      the result in the AWR-127 registry row. Codex must NOT attempt a bridge launch to test this.

## When You Finish

Report: files created, the settings.json diff (before/after of the PreToolUse array only), test and
check results, and the residual risks named above (quoted-string false positive; repo-move breaks
hook as non-blocking error). Plain-language operator summary: after the next new Claude session
starts, any agent that tries a raw bridge launch gets blocked with instructions pointing at the
menubar/watcher path; nothing about the bridge itself, its launch behavior, or any hardware changed;
rollback = delete the appended PreToolUse element (or restore the `.retro_bak` backup).
