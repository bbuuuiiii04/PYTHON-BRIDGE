---
doc_status: active-prompt
truth_level: code-grounded
last_verified_commit: 1a9112d
last_verified_date: 2026-06-23
validation_scope: Codex kickoff prompt for RW-1 implementation; points at the spec + review prompt; no implementation performed here
---

# Codex task — implement RW-1 "Export from SS" (rb_ss_bridge_v2)

Implement the spec exactly and in order:
`docs/plans/active/soundswitch_rw1_export_from_ss_spec.md` (Part B Tasks 1→4, commit per task).

## Read first (smallest path)
- `AGENTS.md` — §1 code-wins, §6 invariants, §8 hard checks, §10 status language.
- the spec above (Parts A–E).
- `docs/prompts/reviews/soundswitch_rw1_export_from_ss_review_prompt.md` — the 5 review surfaces you must satisfy.

## Touch these files (named by the spec)
- `tools/export_soundswitch_pack.py` — add `publish_pack` + swap/lock/recover; **do not change `export_pack`'s observable behavior**.
- `scripts/bridge_menubar.py` — `Export from SS` item + worker + reload handshake; imports **AppKit + stdlib only**.
- `config/soundswitch_pack_player.example.json`.
- `docs/agents/change_contracts.yml`, `docs/subsystems/soundswitch_output.md`,
  `docs/subsystems/runtime_commands.md`, `docs/setup/runtime_commands.md`,
  `docs/plans/active/soundswitch_exporter_remaining_work.md`.
- `tests/test_soundswitch_pack.py` (`PublishPackReplaceTests`), `tests/test_bridge_menubar.py`.

## Apply these review revisions BEFORE coding
1. **[must]** Resolve the `export_pack` contradiction: a behavior-preserving extraction of the shared
   write+fsync loop into `_stage_artifacts` **is allowed**, provided
   `test_atomic_publish_requires_new_destination` and `test_two_exports_are_byte_identical` stay green.
2. **[should]** Harden the swap: deterministic multi-`.bak-*` selection (newest); atomic lock-steal
   (unlink + `O_EXCL` recreate; a lost race ⇒ "already running"); GC orphaned `.{name}.tmp-*` staging dirs.
   `_recover_orphan_backup` must not discard a backup unless `dest` is present.
3. **[minor]** Scope the "no path in committed files" rule to runtime-surfaced strings; the canonical
   `~/Music/SoundSwitch/...` constant in source + example config is intentional.

## Hard constraints (live safety — do not violate)
- No new runtime command; no `parse_command` or status-schema change. Reload reuses
  `set_soundswitch_pack reload`; the ack reads the existing `soundswitch_pack.pack_sha12`.
- The menubar sends **only** `reload` — never `enable`/`backend`; opens no device; never imports the bridge package.
- A failed decode/compile/verify/swap leaves the prior canonical pack **byte-identical and `load_pack`-able**.
- Reload never enables output, changes backend, starts/restarts the bridge, or opens MIDI/serial/Enttec/DMX.
- No path/UUID/port/device/raw-exception in any UI string, result JSON, log, or committed file —
  only verdict / error-category / content-sha / count.
- Push loop / `StateManager` / OS2L / lasers / LEDs / readers / scripted / T7d / static / blackout / RW-1A untouched.

## Gates to run and report (spec Part D3)
- full suite + `tests.test_soundswitch_pack` + `tests.test_bridge_menubar`.
- proof gate (expect `29/0/0`).
- `check_docs_metadata` / `check_agent_contracts` / `check_docs_drift` (hard) + `check_docs_staleness --report`.
- `git diff --check`.
- Run the new/changed modules under **Python 3.11** (CI is 3.11; local is 3.14).

## Report back
Tests run + counts, proof verdict, the three hard checks, the staleness line, and explicit confirmation that
no device was opened and no path/identifier is surfaced. **Do not claim RW-1 complete** until an independent
review of swap safety / UI concurrency / reload ack / sanitization / no-implicit-enable passes.
