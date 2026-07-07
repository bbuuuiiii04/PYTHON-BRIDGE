---
doc_status: current
truth_level: code-verified
last_verified_commit: b16792a
last_verified_date: 2026-07-07
validation_scope: software-only
---

# Task: laser behavior changes

Use when:
- The requested work is specifically about laser behavior changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/laser.md`
4. `docs/agents/change_contracts.md`

Do not read first:
- archive docs
- old prompts
- old plans
- unrelated subsystem cards

Allowed changes:
- The narrow files required by the task.
- Docs/status/test inventory files required by the change contract.

Forbidden changes:
- unrelated runtime behavior
- local ignored configs or backups
- support/validation claims without evidence
- test modifications just to hide failures

Implementation notes:
- Inspect `laser_*`, `midi_output.py`, `personality_resolver.py`, `state_manager.py` laser seam.
- Keep `MidiOutput.panic()` documented as queue-drain plus live all-notes-off; it is not a separate
  panic-event state machine.
- `MidiOutput` send-error degradation is recoverable on a cooldown reopen path; dependency-missing
  and startup port-missing degradations stay fail-closed.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For drop lifecycle work, keep the real-crossing/predecessor-label gate in
  `DropLifecycle`, cycle selection in `LaserSceneExecutor`, and blackout
  ownership in the existing executor/StateManager paths. Preserve static
  one-shot impact fallback and the default-true `drop_lifecycle_mirror` kill
  switch.
- When changing executor bank selection, preserve the split between policy and execution: skip
  unusable bank entries only inside `LaserSceneExecutor`, and restore cursor/active-scene state on
  gated missing/high-impact selections so the next tick is not stuck dark.
- **Laser color (menu/follow-LED):** color lives in `laser_color_engine.py` (`LaserColorMap`,
  `_target()`, `_BRIGHTNESS`, `_pick_menu_entry`), the LEDs' followed color in
  `led_color_engine.py` (`_last_emitted_rgb`, `color_state()["live_rgb"]`), the re-sync signature in
  `state_manager._sync_laser_color_if_needed`, and the chart/menus in `config/laser_color_map.json`.
  **Never read or write CH3/CH4 anywhere** (chase effects stay authored). Keep `color_state()` a
  pure read (no RNG/journey mutation) and keep `_target()` fail-open (any invalid/missing/disabled
  state → `None` → authored CH8/CH9 pass through). Do not touch the `soundswitch_laser_player.py`
  merge seam or `resolve_slot_colors` for color-follow work. Tests:
  `tests.test_laser_color_engine`.

Required tests:
- Run the targeted tests listed in the subsystem card.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.
- Run `python3 -m unittest tests.test_drop_lifecycle tests.test_laser_director_lifecycle tests.test_laser_executor_lifecycle` for lifecycle changes.
- Run `python3 tools/check_laser_midi_sync.py` when drop/post-drop banks or selection behavior changes.
- Include `tests.test_midi_output`, `tests.test_laser_config`,
  `tests.test_laser_config_deprecation`, and `tests.test_laser_pad_web` when touching MIDI
  degradation, laser config schema/deprecation, or Laser Pad live-toggle behavior.

Required docs updates:
- `docs/subsystems/laser.md`, feature/validation matrices, hardware validation log if manually tested

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
