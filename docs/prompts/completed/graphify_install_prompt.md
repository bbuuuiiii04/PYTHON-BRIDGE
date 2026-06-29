---
doc_status: completed-prompt
truth_level: historical-workflow
last_verified_commit: 56a505e
last_verified_date: 2026-06-29
validation_scope: historical agent task prompt; Graphify setup is complete and current workflow lives
  in docs/setup/graphify.md. Dev-tooling only; manual query access, no hooks, no runtime/bridge code,
  no live-bridge interaction. Closed as AWR-112.
---

# Historical Prompt — Install & customize Graphify for rb_ss_bridge_v2

> **COMPLETED 2026-06-29. Do not execute this as an active setup task.**
> Use `docs/setup/graphify.md` for the current Graphify workflow. This file is retained only as
> historical evidence of the install/tuning prompt.

You are the next agent working on `rb_ss_bridge_v2` (local: `/Users/bbui/rb_ss_bridge_v2`, GitHub:
`bbuuuiiii04/PYTHON-BRIDGE`). Your job is to **install Graphify and tune it to this repo**, then prove
it earns its place. This is dev-tooling setup, not bridge code. Judgment is required (pilot
evaluation, hook decision) — bias toward the safe, low-friction config below.

Read `AGENTS.md` first. This is a **live-performance lighting bridge**; do not run, restart, or touch
the running bridge, and do not reorganize code.

## What Graphify is (and why we want it — narrow)
Graphify turns the repo into a queryable relationship map: local tree-sitter AST extraction over the
Python modules → `graphify-out/{graph.html, GRAPH_REPORT.md, graph.json}`, plus a `graphify query`
CLI and (optionally) editor hooks. **We want exactly one thing from it:** let an agent *orient* fast
("what connects to what / where does X live / blast radius of touching Y") before reading many files,
to cut token use on the understand-the-codebase step. Nothing more. It is **not** a memory system and
**not** a source of truth.

## Locked decisions (do NOT re-litigate — these came from an explicit brainstorm)
1. **Code-only. No cloud / no API key.** Code AST extraction is fully local. Do NOT configure
   `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/etc. for doc/PDF/image semantic extraction — we don't want it
   (live rig, no outbound calls, no cost). Map the code, not the prose.
2. **Manual query for BOTH Claude and Codex; no read-interception hooks.** Use `graphify query`,
   `graphify explain`, or `graphify path` deliberately for broad orientation before reading many
   files. Do not install PreToolUse/read hooks or post-commit graph hooks unless the operator
   explicitly changes this policy. Decision #5 still governs — the map points where to look; it never
   authorizes editing on the map alone, and code/tests stay the source of truth.
3. **Do NOT commit `graphify-out/`.** It is a build artifact derived from code (the real source of
   truth); committing it invites drift and merge conflicts on a large JSON/HTML. Gitignore it and
   regenerate on demand.
4. **Do NOT reorganize the Python files.** `AGENTS.md §4`: the 69 modules are intentionally flat at
   repo root (package run as `python3 -m rb_ss_bridge_v2`); ~478 intra-package imports depend on it.
   Graphify maps the flat layout fine. Moving files is out of scope and forbidden.
5. **The map is a lead, never authority.** Code + tests win. Never act on a `graphify query` result
   for a live-critical change without opening the actual file. `INFERRED`/`AMBIGUOUS` edges are
   guesses — treat them as such.

## Phase 0 — Verify before installing (no changes yet)
- **Do not trust the install commands recalled below — verify them against Graphify's CURRENT README**
  (`github.com/safishamsi/graphify`) before running anything; package name/flags may have changed
  since this prompt was written. Report any divergence.
  - Recalled (verify!): prereqs Python 3.10+ and `uv` or `pipx`; install `uv tool install graphifyy`;
    then `graphify install` (Claude), `graphify codex install` (Codex), `graphify install --project`
    (writes committed skill files to `.claude/skills/graphify/`); build `graphify .` /
    `graphify . --update`; query `graphify query "…"`.
- Confirm `python3 --version` ≥ 3.10 and use the install path in the current README. If macOS/Homebrew
  blocks direct `pip install`, use the README fallback: `pipx install graphifyy`.
- Confirm you're on `main` with a clean-enough tree. **No new branches.**

## Phase 1 — Install (local, code-only)
- Install Graphify with the verified command. No cloud key.
- Confirm the `graphify` CLI runs (`graphify --help` or equivalent).

## Phase 2 — `.graphifyignore` (the core customization)
Create `.graphifyignore` (gitignore syntax, `!` negation; it already respects `.gitignore`). Keep the
graph about **code** (the flat `*.py` modules + `tests/` + tracked example configs). Exclude noise:
- `graphify-out/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`
- generated/exported data: `cues_*.md`-style dumps, `docs/data/`, any large exported JSON, capture
  corpora, VirtualLaserNode captures, `soundswitch_laser_cues.json`-type artifacts, `*.log`
- non-code docs that would only add prose noise to a code map: `docs/prompts/completed/`,
  `docs/archive/`, `docs/history/`, `docs/plans/completed/`
- scratch/throwaway dirs: `experiments/`, `local/`, `artifacts/`, `work/`
Verify by listing what Graphify will ingest (if it has a dry-run/scan-list mode) and confirm it's
overwhelmingly the Python modules + tests, not data.

## Phase 3 — Build the graph
- Build (`graphify .` or verified equivalent), code-only.
- Sanity-check `graph.json` / `GRAPH_REPORT.md`: does it surface the real structure? Expect
  `StateManager` (`state_manager.py`) as a central hub (it owns the 200 Hz loop and is the only writer
  of `DeckState`), and clear clusters for laser (`laser_*`), Govee/LED (`govee_*`/`led_*`),
  SoundSwitch (`soundswitch_*`/`os2l`/`osl`), and Rekordbox readers (`rb_*`/`anlz`/`mtc`). If the
  report's "god nodes" / top-connected nodes look wrong, the ignore set or build is off — fix before
  proceeding.

## Phase 4 — Integration for both tools (Claude + Codex)
- The operator uses **both Claude and Codex** heavily. Set up manual query access for both tools via
  `AGENTS.md`, `CLAUDE.md`, and `docs/setup/graphify.md`.
- Do **not** enable Graphify PreToolUse hooks or the post-commit hook. Record the hook decision and the
  exact commands that remain available. Decision #5 still holds — the map is a lead; it never
  authorizes acting on the map alone.

## Phase 5 — gitignore + secrets
- Add `graphify-out/` to `.gitignore`. Do not commit it.
- Confirm no API key / secret / local IP / device ID is written into any committed file (skill files,
  config). `AGENTS.md §6`: secrets, local IPs, device IDs, live config must never be committed. If the
  project-scoped skill files are committed, inspect them — they must contain no secrets or absolute
  local paths.

## Phase 6 — Pilot validation (PASS/FAIL gate)
Ask Graphify **3 architecture questions whose answers you can independently confirm from code**, e.g.:
1. "What writes `DeckState`?" (expect: only `StateManager`).
2. "What connects `LaserDirector` policy to MIDI output?" (expect a path through `laser_executor` /
   `midi_output`; `LaserDirector` policy and `LaserSceneExecutor` execution are separate).
3. "Blast radius if I change `soundswitch_frame_sender.py` — who depends on it?"
For each: open the files it names and check. **PASS if** answers are correct (or wrong edges are
honestly tagged `INFERRED`/`AMBIGUOUS`) AND query-then-open reached the right code in fewer reads than
blind grep would. **FAIL if** it asserts a wrong dependency without a hedge, or setup friction means
you wouldn't reach for it.

## Phase 7 — Document & report
- If PASS: add a short `docs/setup/graphify.md` (how to rebuild with `--update`; when to query vs read
  source; the rule "map = where to look, code/tests = truth, never act on the map alone for
  live-critical"). Add a one-line pointer in `AGENTS.md` §2 (token-budget / smallest-reading-path
  section) so agents know the map exists and how to use it. Classify the new doc in
  `docs/architecture/doc_index.md` (do not create an orphan), then run the three hard checks
  (`check_docs_metadata`, `check_agent_contracts`, `check_docs_drift`) green before committing.
- If FAIL: uninstall / disable cleanly, leave the repo as you found it, and report why with evidence.
- Either way: report to the operator in plain language — what you installed, the `.graphifyignore`
  scope, the hook decision, the 3 pilot results (correct? read-count saved?), and the verdict. Keep it
  short; no walls of text or status blocks.

## Guardrails (throughout)
- Work on `main`. No new branches/worktrees.
- Never run, restart, or touch the live bridge. This is tooling setup only.
- Verify Graphify's real commands before running them; don't trust recalled commands.
- Code/tests are the source of truth; the map is a lead. Never act on it alone for live-critical work.
- No secrets, local IPs, device IDs, or live config committed. No cloud API key.
- If you touch any doc under `docs/`, follow the doc system: classify it in `doc_index.md` and run the
  three hard checks. Commit incrementally with real messages.
- Update AWR-112 in `docs/status/active_work_registry.md` when done (mark the pilot result).
