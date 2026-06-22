# SoundSwitch finisher — session handoff (for the next Opus session)

status: active handoff
last_updated: 2026-06-22
author: Claude Opus 4.8 (finisher session 1)
branch/PR: `soundswitch/impl` / #116 → base `main`

## TL;DR
Steps 0 (CI green), 1 (export crash-durability), and **2 / T7c (StateManager pack driver)** are
**done, committed, pushed, CI-verified**. T7c was implemented from the ChatGPT-reviewed spec rev 2
(`docs/plans/active/soundswitch_t7c_pack_driver_spec.md`); implemented at `1adbe5c`, **current PR
head `212cb50`, CI green at that head** (ChatGPT review: ACCEPT as software checkpoint; manual-static
policy resolved 3a + tested).
Steps 3 (T7e status/commands), 4 (Task 8 offline/shadow proof), 5 (Task 9 hardware handoff doc) are
NOT started. T7d still blocks autoloop DMX (safe-zero only). Status stays **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**. Do not claim show/rig-ready.

**T7c shape (implemented):** `LaserPackPlayer.clear_selection()` added; StateManager injects
`soundswitch_pack_player/midi_input/pack_backend` (default None = neutral); read-only
`_drive_pack_output()` runs once per tick via a `_push_tick` wrapper (covers 5 early returns; inner
exception → ZERO direct + re-raise); driver is the SOLE `submit_frame` caller; idle held-static
stands alone via `clear_selection()`; autoloop safe-zero. Tests: 4 player tests +
`tests/test_state_manager_pack_driver.py` (D1–D14).

## Operator working agreement for this task (important)
- Operator **overrode** the standing "Codex implements bridge code" rule for THIS task: Claude
  implements directly (confirmed via question in session 1). The override is task-scoped; it does
  NOT generalize.
- Operator wants **plan-first, review-before-implement** for the live-critical pieces. Session 1
  erred by starting T7c implementation before the plan was reviewed; the partial work was reverted.
  → For T7c: wait for the ChatGPT review of `soundswitch_t7c_pack_driver_spec.md`, then implement.
- CI fact that bit session 1: **CI `unit` job runs Python 3.11; local dev runs 3.14.** Always run
  `python3.11 -m unittest …` for anything touching dataclasses/imports. The `unit` job only runs on
  PRs (not on push to main), so latent failures surface only on PR CI.
- Proof gate invocation must be from the PARENT dir:
  `cd /Users/bbui && python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation`
  (running it from inside the repo fails with ModuleNotFound).

## Commits on the branch (this session), all pushed to origin
- `47017ed` Step 0 — green the unit job under 3.11 (mappingproxy→default_factory in
  `soundswitch_pack_loader.py`; PatchC/D live-config skip-guards; phase3 dead `import pytest`
  removed; runtime_status heartbeat de-flake via new `bridge_fmt.reset_rate_state()`).
- `42bc654` Step 0 — de-flake `test_midi_output` worker-timing waits (`_WAIT_SCALE` in `_wait_until`);
  corrected review-prompt target commit (97f2553 → d1d952a).
- `74d2d2c` ledger — Step 0 CI-green close-out.
- `490f1ab` Step 1 — export crash-durability: `_fsync_dir` helper in
  `tools/export_soundswitch_pack.py` (staging dirs before replace, parent after); 3 new tests.
- `974ef2f` docs — the T7c plan (this is what ChatGPT should review).
- (this handoff commit)

**CI:** `unit` job GREEN at `42bc654` (verified via `gh run watch`). Re-run CI after pushing the
later commits to confirm green at HEAD. Proof gate: `PASS_IMPLEMENTATION_MAY_BEGIN` (29/0/0,
foundation 27/27) at finisher head.

## Verification done (evidence, not assertion)
- Full unit suite green on **3.14** (2063 tests, 3 skipped, 1 expected failure) AND the
  previously-failing modules green on **3.11**.
- Step 1: 3 new durability tests pass on 3.14; existing atomic/rollback contract tests unchanged.
- Hard checks pass: `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`.

## Remaining work (operator's execution order)
- **Step 2 — T7c — DONE** (implemented `1adbe5c`, CI green at head `212cb50`; ChatGPT ACCEPT as
  software checkpoint; manual-static policy resolved 3a + tested). Not remaining.
- **Step 3 — T7e** (NEXT): sanitized pack status (no paths/ports/aliases) + validate-first
  `set_soundswitch_pack` reload/backend/enable commands (no implicit hot-enable; stop-before-start;
  no partial swap). Lower risk than T7c.
- **Step 4 — Task 8**: re-run proof gate at final commit; twice-export byte-identity; adversarial
  artifact mutation rejection; shadow backend (physical=none) logging frame hashes only; autoloop
  coverage deferred while T7d blocked. Pinned totals to assert are in the original task prompt
  (42 autoloops, 45/44/32 scripted, 233 venue records, 32 static looks, 19 IAC, 4 DDJ,
  active-cue union 166 + pinned SHA).
- **Step 5 — Task 9**: author `docs/plans/active/soundswitch_t9_hardware_handoff.md` (review-only;
  open no devices). Operator-executed hardware gate only.

## T7d dependency (blocks autoloop DMX)
Autoloop pack output must stay safe-zero/held-static until capture evidence proves (1) ticks/beat
(~600 likely) AND (2) universal phase origin across arm/refire/master-switch/drop-hold/buildup/
phrase-anchor/correction. Not proven. Do not implement autoloop DMX.

## Hard constraints (unchanged — see original task prompt)
No real MIDI/serial/Enttec/DMX/Art-Net/hardware in tests. Preserve default-off neutrality. No
blocking I/O in `_push_tick` or the 40 fps Govee path. StateManager is the only DeckState writer.
Every stop/stale/error/reload/disable/deck-change/track-change/mode-transition/shutdown path resolves
the **automatic base** to ZERO. Nuance (resolved in T7c): a held manual Static Override is
operator-controlled and may visibly stand alone during idle/stop/stale/error/track-change/
discontinuity; it loses only to blackout/emergency/pack-disabled/shutdown. Never claim hardware/show
readiness. Hardware validation is operator-executed only.

## Immediate next actions for the next session
1. Pull the branch; confirm CI green at HEAD (current PR head `212cb50`); re-run proof gate (parent dir).
2. **Step 3 — T7e:** sanitized pack status (no paths/ports/aliases) + validate-first
   `set_soundswitch_pack` reload/backend/enable commands (no implicit hot-enable; stop-before-start;
   no partial swap). Operator wants plan-first review for anything touching live runtime commands.
3. **Step 4 — Task 8:** offline/shadow proof (proof gate at final commit; twice-export byte-identity;
   adversarial mutation rejection; shadow backend physical=none logging frame hashes; pinned totals).
4. **Step 5 — Task 9:** author the operator hardware-gate handoff doc (review-only; open no devices).
5. T7d remains blocked → autoloop DMX stays safe-zero. Keep status HARDWARE-UNVALIDATED throughout.
