---
doc_status: current
truth_level: implementation spec (AWR-197 finish round; executive seat authored)
last_verified_commit: 97ebc6f
last_verified_date: 2026-07-10
validation_scope: >
  Finish the half-done AWR-197 speed/size-law round: tripwire tests pinning the
  law, the patch_b re-pin the paused lane never made, docs paragraph + registry
  row + test-inventory names. The codified law is already on disk (example
  config + tools/apply_speed_size_law.py, landed via auto-sync 4008de2). The
  LIVE-config apply was verified taken and was subsequently DESTROYED by the
  2026-07-10 14:29 LED-Pad clobber incident - re-applying to the live config is
  an OPERATOR decision and is NOT in this round's scope. Staged only.
---

# Codex Implementation Spec - AWR-197 speed/size law: finish round

> You are autonomous senior engineer: gather context, plan, implement, test, and refine end-to-end within this turn. Bias to action. Do the work yourself - do NOT spawn subagents of any kind.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make. NEVER use destructive git commands.

## Part A - Context (verified; read, do not implement)

- The law [confirmed on disk]: `tools/apply_speed_size_law.py` codifies the
  operator-ordered speed/size convention - explicit beat-speed params
  (`SPEED_PARAMS`: 12 looks x loop_beats/travel_beats/burst_beats/breath_beats/
  drift_beats values) on the groove/breakdown/drop/post_drop realtime looks,
  set-if-missing, plus deletion of the two DEAD legacy `drop_pairs` entries
  (`rt_drop_chase`, `rt_drop_nebula`). The tracked example config
  (`config/led_look_director.example.json`) already carries the law (six
  loop_beats entries et al., landed via auto-sync `4008de2`).
- The paused lane completed: example-config codification + the live-config
  apply (verified correct at the time via the backup trail). It did NOT finish:
  the tripwire test, the docs, the registry row, and one test re-pin.
- The patch_b red [confirmed at this desk]: `tests/test_led_color_engine_m2_patch_b.py`
  `test_tracked_config_validates` (line ~104) asserts `look.params == {"width": 2.5}`
  for a look that now legitimately carries `{"width": 2.5, "loop_beats": 4.0}`.
  Re-pin to the approved literal (per suite-baseline doctrine: explicit
  literals, never blind-read the config).
- HONEST STATUS to carry into the docs: the live config's law params and dead-
  pair deletions were WIPED at 14:29 on 2026-07-10 when a LED Pad commit
  overwrote the live config with a stale draft (the two dead pairs are back and
  the params are gone in the live file right now). The apply script is
  idempotent and re-runnable, but re-applying to the live config awaits the
  operator's restore ruling - do NOT run it against the live config.

## Part B - Tasks (in order; one commit per task, explicit paths)

### Absolute Rules
- Touch ONLY: `tests/test_speed_size_law.py` (new),
  `tests/test_led_color_engine_m2_patch_b.py`, `docs/subsystems/led_govee.md`,
  `docs/status/active_work_registry.md`,
  `docs/validation/software_test_inventory.md`.
- Do NOT touch `config/led_look_director.json` (live, gitignored), any
  `*.backup*`/`*.bak-*` file, `tools/apply_speed_size_law.py` itself, or the
  example config (already correct).
- Concurrent-lane fence - do NOT touch: `tools/led_pad_web.py`, `tests/test_led_pad_*.py`,
  `docs/guides/led_pad.md`, `packaging/make_stick.sh`, `install_controller.py`,
  `usb_launcher.py`, `enttec_dmx_pro.py`, `__main__.py`, and their tests.
- Commits by EXPLICIT PATHS only; never `git commit -a`; no branches; no
  process contact.
- Error handling: pure test/docs work - no try/except.

### Task 1 - `tests/test_speed_size_law.py` (new): the tripwire
1. `test_example_config_carries_the_speed_law` - load the EXAMPLE config JSON
   directly; for every entry in `apply_speed_size_law.SPEED_PARAMS` assert the
   look exists, its `scene_ref` matches, and each law param is present with the
   exact literal value (import SPEED_PARAMS from the tool - the tool is the
   single source of the law's terms; the example config must satisfy it).
2. `test_example_config_has_no_dead_pairs` - `rt_drop_chase` and
   `rt_drop_nebula` absent from the example config's `drop_pairs`.
3. Apply-script behavior over a tmp copy of the example config (pure, tmp-dir):
   `test_apply_is_idempotent` (first run: no changes needed on the example -
   assert apply() returns False; then delete one param, run, assert True and
   the param restored at the law value); `test_apply_never_clobbers_existing`
   (set a look's law param to a different explicit value, apply, assert it is
   NOT overwritten - set-if-missing semantics); `test_apply_aborts_on_missing_look`
   (remove a SPEED_PARAMS look entirely, assert ValueError before any
   mutation).
Commit: `AWR-197: speed/size-law tripwire tests` + explicit path.

### Task 2 - patch_b re-pin
In `tests/test_led_color_engine_m2_patch_b.py` `test_tracked_config_validates`,
re-pin the params assertion to the approved literal
`{"width": 2.5, "loop_beats": 4.0}`. Touch nothing else in the file. Run the
module green. Commit: `AWR-197: re-pin patch_b tracked-config params to the
approved speed-law literal` + explicit path.

### Task 3 - docs + registry
- `docs/subsystems/led_govee.md`: add the AWR-197 paragraph the apply script's
  docstring already references - the speed/size law in one short paragraph
  (explicit beat-speed params on realtime looks by role; big-drop ->
  small-post_drop pairing convention; the law's terms live in
  `tools/apply_speed_size_law.py` SPEED_PARAMS; example config carries it; the
  live config is applied via the script, set-if-missing, idempotent).
- `docs/status/active_work_registry.md`: RE-READ fresh immediately before
  editing (parallel lanes append). UPDATE the existing AWR-197 row IN PLACE
  (the executive already inserted a CLAIMED row - do NOT add a second row or
  take a new id): codified in example config +
  apply script; tests by name; and the honest live-state note from Part A
  (live apply taken, then wiped by the 14:29 pad incident; re-apply awaits the
  operator's ruling; STAGED ONLY; SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED).
- `docs/validation/software_test_inventory.md`: add the new test names
  (fresh-read first).
Commit: `AWR-197: docs paragraph + registry row + test inventory` + explicit
paths.

## Part C - Invariants
- Docs-only + tests-only round: zero runtime behavior change.
- The example config is NOT edited (it already carries the law; if your Task 1
  test finds it does not, STOP and report - do not "fix" the config).

## Part D - Tests
- `python3 -m unittest tests.test_speed_size_law tests.test_led_color_engine_m2_patch_b`
  green from repo root.
- Full `python3 -m unittest discover tests` reconciled BY NAME; known reds NOT
  yours to chase: patch_d `drop_slot_color_smoke_and_snap`,
  `export_pack_parity_self_heal` x2, laser_player golden slot=16,
  parity_oracle capture_rows, patch_c `test_live_config_slot_color_smoke` +
  `test_tracked_and_live_configs_validate`, patch_d
  `test_tracked_and_live_configs_validate` (live-config incident, another
  round). Your Task 2 re-pin must REMOVE the patch_b red. Pack byte-identity
  flappers: isolate; green in isolation = baseline.
- Hard checks: `python3 tools/check_docs_metadata.py`,
  `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.

## Part E - Acceptance
- [ ] Tripwire tests green; patch_b module green (red removed); discover
  reconciled; hard checks green.
- [ ] Registry row + led_govee paragraph + inventory names landed with the
  honest live-state note.
- [ ] Three commits by explicit paths with the `AWR-197:` prefix.
- [ ] Live config and example config untouched.

## When You Finish
Report changed files, commit ids, test counts (with red names), and one
plain-language operator line: "the LED speed rules (how fast looks loop/travel
per musical role, and big-drop-to-small-echo pairing) are now written down in
the config and pinned by tests, so nothing can silently drift them; the copy in
your live config was lost in today's pad incident and comes back whenever you
approve the restore."
