---
doc_status: active-prompt
truth_level: code-grounded
last_verified_commit: 9095cef
last_verified_date: 2026-06-23
validation_scope: Codex kickoff prompt for the RW-1 export review-fixes; points at the spec; no implementation performed here
---

# Codex kickoff — RW-1 `Export from SS` review fixes

Implement this spec exactly and in order (commit after each task):
`docs/plans/active/soundswitch_rw1_export_fixes_spec.md` (Part B Tasks 1 → 3).

## Read first (smallest path)
- `AGENTS.md` — §1 code-wins, §6 invariants, §7 anti-drift, §8 hard checks, §10 status language.
- the spec above (Parts A–E) — it contains the exact before/after code blocks.

## What this is
Three small, additive corrections to the just-landed RW-1 feature, from an
independent review of `88a9815..9095cef`:
1. `tools/export_soundswitch_pack.py::_recover_orphan_backup` — never promote a
   non-directory (symlink/file) backup into the canonical pack location.
2. `scripts/bridge_menubar.py::_run_export` — conservative reload-ack: never fire a
   blind reload on a stale/unknown bridge snapshot, and don't re-send a reload when
   the live pack already serves the exported content.
3. Docs + change-contract verification (anti-drift).

## Hard constraints (do not violate)
- No new runtime command; no `parse_command` or status-schema change; menubar sends
  only `set_soundswitch_pack reload`.
- Do not touch `export_pack`, the swap/lock primitives, `runtime_status.py`,
  `soundswitch_pack_controller.py`, `__main__.py`, or the 200 Hz push loop.
- No path/UUID/port/device/raw-exception leak in any UI string, result file, log, or
  committed file (the canonical `~/Music/SoundSwitch/...` constant is the one
  intentional exception).

## Gates to run and report (spec Part D4)
Full suite + `tests.test_soundswitch_pack` + `tests.test_bridge_menubar`; proof gate
(expect `29/0/0`); `check_docs_metadata` / `check_agent_contracts` / `check_docs_drift`
(hard) + `check_docs_staleness --report`; `git diff --check`. Run the two changed
modules under Python 3.11 too (CI is 3.11; local is 3.14).

## Report back
Tests run + counts, proof verdict, the three hard doc checks, the staleness line, and
explicit confirmation that the menubar still sends only `reload` and that no
non-directory backup can become canonical. Do not claim complete until an independent
review of the orphan-recovery type-check and the reload-ack pre-check passes.
