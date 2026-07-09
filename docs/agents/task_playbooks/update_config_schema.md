---
doc_status: current
truth_level: code-verified
last_verified_commit: 96923d3
last_verified_date: 2026-07-08
validation_scope: software-only
---

# Task: config schema changes

Use when:
- The requested work is specifically about config schema changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/config.md`
4. `docs/agents/change_contracts.md`

Do not read first:
- archive docs
- old prompts
- old plans
- unrelated subsystem cards

Allowed changes:
- The narrow files required by the task.
- Docs/status/test inventory files required by the change contract.
- Removing unused constants in `config.py` still requires updating config docs when the removed name
  looked like a tunable operator knob.

Forbidden changes:
- unrelated runtime behavior
- local ignored configs or backups
- support/validation claims without evidence
- test modifications just to hide failures

Implementation notes:
- Inspect `config.py`, `laser_config.py`, `led_config.py`, `config/*.example.json`.
- Remove unread example-only placeholders instead of documenting them as schema.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For LED `scripted_mode`, document that source/default roles exclude `utility`, destinations may use `utility` for blackout, absent-block defaults turn groove/drop/post-drop off, and `safety.scripted_mode_automation` remains the separate master switch (the shipped example config enables it; the `LEDSafety` dataclass default stays `false`).
- For LED `blank_role_hold` (AWR-157, top-level boolean, default `true`), document that it's a
  dispatch-layer guard, not a role-mapping knob: it decides whether a blackout dispatch produced
  by a blank/scripted-mapped role is suppressed while the deck is audibly playing, never whether
  the mapping itself changes. Absent key parses `true`; malformed values fail closed.
- For LED `color_engine` strategy fields, document defaults, accepted values, `slot_mono_chance_by_look` range validation, `locked_palette_by_look` palette-name validation when relevant, and invalid-config behavior in the setup and subsystem docs.
- For LED `color_engine.palette_control`, document Stream Deck device/channel/note validation,
  reserved notes, generated MIDI bindings, tracked-example status, and hardware-unvalidated scope.
- For M2.5 slot-cue example changes, keep legacy color-suffix looks defined until the gated cleanup patch and document that solid slots 0-4 remain possible through point/mono palettes.
- For Laser scene schema changes, keep `fallback_scene` references validated against known scenes and
  `cooldown_beats` non-negative. Treat leftover `pre_drop_scene` personality keys as deprecated
  load-compat only unless a new operator decision reintroduces them.
- A LOOK-NAME rename (the config dict key + every bank list entry + any `drop_pairs` reference) is a
  different operation from a renderer `scene_ref` rename — the two need not move together (AWR-156
  T6.4: `rt_drop_chase`/`rt_drop_nebula` were renamed as look names to
  `rt_post_drop_remnant_chase`/`_nebula` while their `scene_ref` stayed exactly `rt_drop_chase`/
  `rt_drop_nebula`, since `SLOT_EFFECTS`/`REALTIME_EFFECT_NAMES`/`REALTIME_EFFECT_PARAM_KEYS` are all
  keyed by `scene_ref`, not look name). Grep every test file for the OLD look name, not just the
  config — regression-lock tests frequently assume `look.scene_ref == look_name`.

Required tests:
- Run the targeted tests listed in the subsystem card.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.

Required docs updates:
- `docs/subsystems/config.md`
- `docs/setup/configuration.md`
- `docs/status/feature_status_matrix.md`
- tracked config examples
- config tests
- `docs/agents/task_playbooks/update_config_schema.md` if workflow guidance changes

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
