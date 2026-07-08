# Fable 5 Prompt — P5: Extract the LED dispatch subsystem from state_manager.py and orchestrate the migration

Target: Claude Fable 5, effort **high**.

## Mission

Design and orchestrate the extraction of the LED dispatch logic that has grown inside
`state_manager.py`, so future changes to LED behavior touch one place instead of five. You are the
architect and orchestrator: investigate, design the smallest safe boundary, write the
Codex-executable spec, then drive implementation and verify it. **Do not implement bridge code
yourself — Codex implements.** Codex runs in tmux session `codex` (send it work with
`tmux send-keys -t codex '<text>'` then a separate `Enter`; verify submission with
`tmux capture-pane`). If Codex is rate-limited or its session is unusable, the operator-sanctioned
fallback for this workstream is a Sonnet 5 subagent implementing under your review.

This is for Brandon (project owner, not a software engineer). The output he cares about: the bridge
behaves identically, `state_manager.py` gets meaningfully smaller, and the five duplicated LED
bookkeeping blocks become one.

## Evidence packet (verified 2026-07-03 at the audit; re-verify anchors against HEAD before relying)

- The tangle: `state_manager.py` (~5,100 lines at HEAD) holds ~1,200 lines of LED dispatch policy
  around lines 1595–2800 — `_handle_led_event`, `_dispatch_led_manual_command`,
  `_dispatch_led_smart_drop_blackout`, `_dispatch_led_automation`, `_dispatch_led_idle_ambient`,
  `_gate_led_automation`, `_led_role_from_smart_phrasing`, the role-key builders, drop-lifecycle
  and phrase-latch state, `_led_sp_state_for_next_backend`, plus ~30 `_led_*` instance fields.
- The core defect: one trigger/accept/reject/log bookkeeping ritual (~60–120 lines) is copy-pasted
  five times (manual path; twice inside the smart-drop blackout path — realtime tactical + cloud;
  automation path; idle-ambient path) and has already drifted between copies. These counters and
  gate reasons feed `led_status_provider` — the operator's "why aren't my LEDs changing" surface.
- Everything runs on the StateManager thread (event drain + 200 Hz push tick). The extraction must
  not add threads, locks, or blocking I/O to the push loop, and StateManager must remain the only
  `DeckState` writer (AGENTS.md §6, `docs/architecture/runtime_invariants.md`).
- `led_dispatch_coordinator.py` is the backend-routing *adapter* (cloud vs realtime), not the
  policy — do not merge policy into it.
- Test net: `tests/test_led_state_manager.py`, `tests/test_led_color_engine_integration.py`, and
  the `test_led_color_engine_m2_*` files exercise this logic through StateManager. Suite baseline
  at HEAD: **2762 OK (5 skipped, 1 expected failure)** via `python3 -m unittest discover tests`.
- Context from today's audit (already implemented, do not redo): commits `42653b3`, `87125da`,
  `708429a`, `f1310fa`; audit spec `docs/plans/active/audit_2026_07_03_fix_queue_spec.md`.
- Operator-reserved code you must not remove: `LEDColorEngine.lock/unlock/set_palette/
  queue_palette/shift` (future LED Pad + Stream Deck controls) and the laser-side
  `post_drop_cycle_beats` knob.
- Known hazard: turn-end auto-sync hooks may commit/push mid-run and can diverge origin (it
  happened twice today). If origin diverges, reconcile with a plain merge (`-s ours` was today's
  correct call after verifying content subsumption) — never force-push, never rewrite pushed
  history, never create branches.

## Decisions already made (do not re-litigate)

Extraction is wanted; a rewrite/redesign of LED behavior is not. Behavior must be preserved
byte-for-byte on the status surface (counters, gate reasons, role keys, log lines may keep their
exact formats). The five bookkeeping copies become one shared path. Whether the result is a
same-file consolidation, a new module owned by StateManager, or a staged combination is yours to
design — pick the smallest boundary that removes the duplication and the future-agent trap, and
say why.

## Deliverables, in order

1. A short design note (in chat) with claims labeled confirmed / assumed / unknown: the chosen
   boundary, what moves, what stays, and the risk you most expect during migration.
2. The Codex spec at `docs/plans/active/led_dispatch_extraction_spec.md`, written per
   `.claude/skills/codex-spec/SKILL.md` (Part A–E, pre-handoff checklist, change contract per
   AGENTS.md §7, phased with one commit per phase).
3. Orchestrated implementation via Codex (Sonnet 5 fallback), monitored to completion.
4. Independent verification you run yourself: the three hard checks
   (`tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`), the full
   suite, and a line review of the riskiest hunks. Then a plain-language report to Brandon.

## Boundaries

Allowed: read-only exploration of this repo; running the test suite and the three check scripts;
`git` status/log/diff/show; tmux interaction with the `codex` session; spawning read-only or
implementation subagents per the fallback rule; writing the spec file and docs the change
contracts require. Forbidden: implementing bridge code in this session; touching the running
bridge, Rekordbox, SoundSwitch, lasers, LEDs, Govee devices, or any hardware; force-push, history
rewrites, branches, `git clean`; changing LED behavior semantics; upgrading status language beyond
software-tested.

## Success criteria (falsifiable)

- Full suite green (≥2762 OK, same skips/xfails) and all three hard checks pass after every phase.
- The trigger/accept/reject/log ritual exists in exactly one place; the five call paths route
  through it; `led_status_provider` output fields and semantics are unchanged (tests prove it).
- `state_manager.py` shrinks by a stated line count; no new threads/locks/blocking I/O on the push
  path (state a check you ran, e.g. targeted diff review of `_push_tick*`).
- Nothing operator-reserved was deleted; change contracts and their `docs_update` lists are
  satisfied.
- Stop conditions: if at any point behavior preservation cannot be proven by tests, stop that
  phase and report rather than widening scope; if Codex and the Sonnet fallback are both
  unavailable, deliver the spec and stop.
