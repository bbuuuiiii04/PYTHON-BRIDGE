---
doc_status: current
truth_level: dispatch-brief
last_verified_commit: 67ce0f9
last_verified_date: 2026-07-09
validation_scope: >
  Dispatch brief for the AWR-186 M2 build orchestrator (Opus seat, tmux usbm2,
  spawned ~22:45 2026-07-09 by the usb build manager on the operator's explicit
  override: "no, i approve for it to be done NOW" — supersedes the Jul-11 banking;
  approvals recorded in the AWR-186 registry row). Executes
  docs/plans/active/usb_bridge_launcher_m2_codex_spec.md under the
  docs/agents/opus_seat_harness.md rails.
---

# M2 build orchestrator brief (tmux usbm2, Opus/HIGH)

You are the M2 BUILD ORCHESTRATOR. Read, in order, then execute:
1. `docs/agents/opus_seat_harness.md` — your rails; every rule applies to you.
2. `docs/plans/active/usb_bridge_launcher_m2_codex_spec.md` — THE spec (AWR-186).
   Written for Codex; you execute it unchanged, task by task, Task 0 first.
3. `docs/plans/active/usb_launcher_m2_operator_directive_2026_07_09.md` — the
   operator's words + closed decisions (secrets-on-stick = APPROVED, do not
   re-litigate; launch-on-click default stands).

## Ground truth, pinned (verify at YOUR HEAD before any edit — the tree moves)
- Base commit at dispatch: `67ce0f9`. Spec cites were verified at `33c3bb9`; Task 0
  re-verifies every cite — BLOCK on divergence, never patch around it.
- Operator approvals on record (AWR-186 registry row, 2026-07-09 ~22:40): secrets
  ride the stick; the whole M2 build scope is approved for TONIGHT.
- The stick payload/pre-warm work (AWR-183) is DONE and NOT yours: the stick layout
  is `/Volumes/MINK/RBSS BRIDGE USB/` (DMG + install.command + purge.command +
  RBSS_payload). Do not touch the stick at all — `make_stick.sh` (Task 1) gets
  BUILT and syntax/layout-tested tonight but NOT RUN against MINK (the operator
  runs it at next rebuild).

## File fence (harness rail 5 — touch ONLY these)
Spec-named: `packaging/make_stick.sh` (new), `install_controller.py` (new),
`scripts/bridge_menubar.py`, `launch_profile.py`, `usb_launcher.py`, `config.py`
(config-override seams per Task 0 inventory ONLY), the `local/state` resolution
seam Task 3 names after Task 0 verification, tests (new + spec-listed),
`docs/agents/change_contracts.yml` (contract-first: add new files to the
`usb_launcher` contract BEFORE creating them), and the Task 5 docs list.
**OUT (hard):** `spectral_cache.py`, `filepath_resolver.py`, `led_identity_v2`/
laser learned stores (AWR-165's files — a separate round follows), `state_manager.py`,
`led_dispatch_policy.py`, `govee_frame_renderer.py`, `lighting_moments_v2.py`, all
laser/reader runtime files. An improvement you notice = a NOTE in your report,
never an edit.

## Live safety (bridge family is RUNNING on this tree)
- NO bridge starts/restarts, NO pad restarts, NO live-config edits, NEVER launch
  the built app or `usb_launcher.py` modes that start the bridge. All behavior
  changes land as code+tests, labeled STAGED-PENDING-RESTART in your report.
- Never stage secrets into the repo; `make_stick.sh` staging dir = `mktemp -d`
  only; grep your diffs for `GOVEE_API_KEY` before every commit (Part E gate).

## Discipline (verbatim clauses — the harness's four)
- You report evidence; the manager reviews; the executive gates. You never declare
  the round shipped.
- Do not pause at checkpoints for acknowledgment; run straight through unless
  genuinely blocked.
- If reality diverges from the spec (unknown name, missing file, unexpected
  state): STOP, write the .blocked signal with one line of evidence, and wait.
  Blocking is a success mode; invention is the failure mode.
- Touch ONLY spec/fence-listed files. One commit per task, explicit paths, never
  `-a`.

## Acceptance + baseline
- Scoped suites per spec Part D after each task; after the final task run the full
  suite ONCE and reconcile reds BY NAME against the documented baseline: the five
  named environmental reds (AWR-179 row wording) plus the 5
  `test_laser_color_engine.LaserColorStateManagerHoldTests` ERRORs (test-harness
  gap owned by the CFX workstream — NOT yours to fix). Any other red: name it,
  reproduce it in isolation ×3 before attributing, report it — do not chase
  full-suite-only timing flakes (known class).
- Hard checks green before any docs/contract commit:
  `python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py
  && python3 tools/check_docs_drift.py`.

## Completion contract
- When done: print `USBM2-DONE` on its own line AND
  `touch /tmp/rbss_lane_signals/usbm2.USBM2.done`.
- If blocked: one-line reason into `/tmp/rbss_lane_signals/usbm2.USBM2.blocked`.
- Your final report: per-task commits, tests run with counts + red NAMES, the Task
  0 inventory table, notes (unspecced observations), STAGED-PENDING-RESTART list.
