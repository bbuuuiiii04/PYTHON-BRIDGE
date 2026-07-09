---
doc_status: current
truth_level: handoff-report
last_verified_commit: f9396be
last_verified_date: 2026-07-09
validation_scope: >
  Build-phase orchestration brief for the USB launcher Milestone 1, executed by an Opus 4.8
  orchestrator in tmux claude8 under the Fable build manager (claude6). Amends
  docs/plans/active/usb_bridge_launcher_m1_codex_spec.md per the executive green light of
  2026-07-09 (~03:30): Opus implements instead of Codex, three operator decisions locked,
  file fence while F2/F4 build in parallel, frame-engine re-exec task gated last.
  Retire when M1 closes.
---

# USB M1 build — Opus orchestrator brief (2026-07-09)

**Target: Claude Opus 4.8, effort xhigh, large output budget.** You are the M1 BUILD
ORCHESTRATOR in tmux `claude8`. You implement; the Fable build manager (claude6) reviews
adversarially after you; the executive gates after that. You MAY fan out Sonnet subagents
for parallelizable grind (announce each spawn and what it owns); keep every code decision
yourself.

## Mission

Execute Milestone 1 of `docs/plans/active/usb_bridge_launcher_m1_codex_spec.md` — read it
FULLY first; it is the specification (Part A context, Part B tasks, Part C invariants,
Part D tests, Part E acceptance). This brief AMENDS it; where they conflict, this brief
wins. Re-verify every file:line cite in the spec against YOUR checkout's HEAD before
relying on it — a parallel F2/F4 build is landing commits while you work.

## Amendments (binding)

**A1 — Decisions locked (operator, verbatim tonight):**
- Guest-first is SETTLED (operator: his MacBook is already the permanent install; the
  stick is a guest/venue tool). Build no first-run mode fork.
- "Test the lights" replay button is IN SCOPE ("yes test the lights button is good") —
  new Task 5b below.
- Signing = **Apple Development certificate** ("yes ill do the cert right now"). At the
  signing task's turn run `security find-identity -v -p codesigning`: an Apple
  Development identity present ⇒ sign with it; absent ⇒ build unsigned, ship
  `packaging/sign.sh` as a re-runnable final step, and NEVER block on the cert.

**A2 — FILE FENCE (hard, while F2/F4 build on claude4): ZERO edits to
`state_manager.py`, `led_dispatch_policy.py`, `govee_frame_renderer.py`,
`lighting_moments_v2.py`, or ANY laser/reader file** (`laser_*.py`, `drop_lifecycle.py`,
`soundswitch_laser_player.py`, `rb_state_reader.py`, `rb_memory.py`, `rb_offsets.py`,
`live_bpm.py`, `mtc_reader.py`, `filepath_resolver.py`, `anlz_reader.py`). Consequences:
- Spec Task 4 (frozen frame-engine re-exec in `govee_frame_engine_client.py`) is
  **SEQUENCED LAST and DISPATCH-GATED**: do NOT touch it until claude6 relays the
  executive's confirmation that F4 has landed. Everything else builds now. When you
  finish the ungated tasks, report and WAIT — do not start the gated task on your own.
- `__main__.py` is NOT fenced but is parallel-risk: before and after any `__main__.py`
  edit, run `git log --oneline -3 -- __main__.py`; keep edits small and additive; if you
  hit merge friction with an F2 commit, stop and report rather than resolving creatively.

**A3 — AWR-107 dependency RE-SCOPED (operator correction on record):** the pack path is
proven by use at every mix. M1's must-prove is **frozen-bundle equivalence** (the bundled
pack path behaves identically to source-run), not fixture validation. Update the spec's
dependency framing where your work touches it.

**A4 — Live safety (absolute):** no bridge starts, no pad restarts, live config files
untouched (`config/laser_director.json`, `config/led_look_director.json`,
`config/soundswitch_pack_player.json` — examples/templates only), no launchctl
load/unload, no MIDI/DMX/Govee/network output. The end-of-M1 hardware parity run is
OPERATOR-gated and is not yours to perform. Building and code-signing an .app and DMG is
allowed; RUNNING the bundled bridge is not (a smoke `--help`/arg-dispatch exec that exits
before bridge startup is fine).

**A5 — Task 5b (NEW): "Test the lights" replay button.**
- Read `session_replayer.py` and `session_recorder.py` first and verify what exists; the
  design claim is that the replayer already injects recorded events at the StateManager
  boundary and only the runtime selection is missing — verify, then build the smallest
  honest version: a `--replay-session <file>` entry path in `usb_launcher.py` (and the
  matching menubar action "Test the Lights") that runs the bridge with the replayer as
  the event source instead of the Rekordbox readers.
- **Live-safety rule verbatim from the design: replay refuses to start while Rekordbox is
  running** — check via the existing process-detection helpers; fail closed with a clear
  message.
- If no recorded session file exists on disk, the button ships anyway with a graceful
  "no test session recorded yet" path and the runbook tells the operator how to record
  one (`session_recorder.py`). Do not fabricate a session file; do not block M1 on one.
- The fence applies: if wiring the replay source genuinely requires editing a fenced
  file, STOP and report the exact line you needed — do not touch it.

**A6 — Task 7 (NEW): plist generation.** A pure generator (in `usb_launcher.py` or
`packaging/`) that renders the launcher's LaunchAgent plist with
**`ProcessType=Interactive`** (AWR-151 lesson, non-negotiable), stable label, and correct
program arguments; validate the GENERATED file with `tools/check_launch_agents.py` logic
(point it at the generated file or replicate its assertions in a unit test). Do NOT
install/load anything (A4). Pure-function test seam required.

**A7 — Dependency declaration:** fix `pyproject.toml` — declare the known-undeclared
runtime deps (`python-elgato-streamdeck`, `Pillow`, `python-rtmidi`, `pyserial`) in an
appropriate optional-extras group (e.g. `bundle`), AND carry the PyInstaller
hidden-imports list anyway (belt and suspenders). Verify `build/`, `dist/`, and any build
venv are gitignored before the first build; commit only source (spec files, scripts,
plist templates).

## Execution order (respects the fence)

1. Spec Task 1 — `usb_launcher` contract in `docs/agents/change_contracts.yml`
   (docs-first; extend code_globs to cover the new files this brief adds: `packaging/*`,
   `usb_launcher.py`, `launch_profile.py`).
2. Spec Task 0 — build-env gate: PyInstaller × Python 3.14.6 (try current first; on
   failure provision a python.org arm64 3.12/3.13 in a LOCAL gitignored venv). Record
   the outcome + suite baseline on the chosen interpreter in the runbook. STOP conditions
   per spec.
3. Spec Task 2 — `launch_profile.py` single source + watcher consumes it (copy the env
   set from `scripts/ss_bridge_watcher.sh` `start_bridge()` at YOUR HEAD — code wins over
   every doc) + equality/reference tests.
4. Spec Task 3 — `usb_launcher.py` entrypoint (`--run-bridge` in-process,
   `--run-streamdeck`, `--run-frame-engine` DISPATCHER ONLY (new-file side is safe; the
   fenced client-side edit waits), `--replay-session` (A5), menubar default with
   frozen-mode owned-child-pid control; unfrozen behavior byte-identical).
5. A5 Task 5b — test-lights replay wiring + menubar action.
6. Spec Task 5 — `packaging/rbss_launcher.spec` + hidden imports + Info.plist keys
   (`NSLocalNetworkUsageDescription`, `LSUIElement`, stable `CFBundleIdentifier`) + A7
   deps + DMG via `hdiutil`; A6 plist generator; then the A1 signing step (identity check
   at its turn).
7. Spec Task 6 — `docs/setup/usb_launcher_runbook.md` (build commands, interpreter
   decision, replay-button usage + recording instructions, signing re-run step,
   coexistence warning, deliberately-absent dev features).
8. REPORT AND WAIT — spec Task 4 (frame-engine re-exec) only on relayed F4 confirmation.

Commit after each task, explicit paths only, never `git clean`, never revert files you
did not author this session (parallel lanes are dirty-committing around you; check
`git log` before treating any commit as failed). Run the three hard checks
(`tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`) +
the contract-named test suites before calling any task done. Full-suite baseline: record
the known-reds count BEFORE your first change; never regress it.

## Claim discipline + report

Label claims confirmed / assumed / unknown. When you finish the ungated tasks, print a
report: changed files per task, tests/checks run with counts, the Task 0 interpreter
decision, the signing outcome (identity found or deferred), any STOP hit, and a
plain-language operator summary (what double-clicking does now, what the Test the Lights
button does, what is deliberately not built: install flows, foreign-Mac, frame-engine
freeze fix pending F4). End the report with `M1-UNGATED-COMPLETE` on its own line (or
`M1-BLOCKED: <reason>`). claude6 reads your pane.
