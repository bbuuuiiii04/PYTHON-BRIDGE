---
doc_status: active-review-prompt
truth_level: review handoff; read-only
last_verified_commit: 74706f4
last_verified_date: 2026-06-29
validation_scope: review prompt only; no bridge run/restart, no SoundSwitch/MIDI/serial/Enttec/DMX/laser/LED/Govee/Rekordbox, no hardware
---

# Codex Review — Native Autoloop DMX spec readiness

You are doing a **read-only adversarial readiness review** of a revised
implementation spec. Your job is to decide whether it is ready to hand to an
implementer, and to catch anything still wrong. Do not implement. Do not trust
the spec's own claims — re-verify each against current code and report
`file:line`.

## Absolute rules
- Read-only. Do **not** edit files, implement, or "fix" anything.
- Do **not** run or restart the bridge.
- Do **not** open SoundSwitch, Rekordbox, MIDI, serial, Enttec, Art-Net, DMX,
  laser, LED/Govee, or any hardware-adjacent path.
- Running the static doc checkers and `git diff`/`git show` is allowed.
  Running the unit test files read-only is allowed; do not add or change tests.

## What changed (review target)
A prior review found bugs in the original spec; it was then revised and greenlit.
Review these changes for readiness:
- `docs/plans/active/native_autoloop_dmx_runtime_spec.md` — full rewrite.
- `docs/architecture/doc_index.md` — registered the spec + the equivalence-oracle
  spec; relabeled the T7d row.
Authoritative intended behavior: `docs/architecture/native_autoloop_pack_authority.md`.
Scope decision: native Autoloop DMX is **greenlit**; the six-scenario T7d capture
plan is **superseded** by an operator all-in two-flight capture; the phase
mapping is the working contract with a `phase_offset_beats` calibration input.
Use `git diff`/`git show` if it helps see exactly what changed.

## Verify these load-bearing claims against current code (do not assume)
For each, return CONFIRMED / REFUTED / UNCERTAIN with `file:line`:

1. **Channel base.** Laser scene `scene_def.midi.channel` is 1-based (1–16) and
   the pack key `channel_zero_based` is 0-based, so the spec's mandated
   `(scene.channel - 1, scene.note)` lookup is correct and necessary; a raw lookup
   would miss for every note and render the whole show dark.
   (`laser_models.py`, `midi_output.py:251`, `soundswitch_pack.py` `BRIDGE_SCENES`
   + `_selection_map`, `config/laser_director.json`.)
2. **Edge-triggered selection + latch.** `LaserSceneExecutor.on_decision` returns
   `None` on the large majority of 200 Hz ticks (idle / no decision /
   `same_scene_skip`), so the spec's latched hold-across-`None` design is required
   to avoid one-tick-per-32-beat flicker, and re-anchoring on each executor edge
   (not on scene-name change) is required because a single-look bank re-returns the
   same name. (`laser_executor.py` `on_decision`, `_select_scene`,
   `_choose_bank_scene_locked`.)
3. **Phase unit.** `AUTOLOOP_TICKS_PER_BEAT = AUTOLOOP_CYCLE_TICKS //
   AUTOLOOP_ARM_PHRASE_BEATS = 600`, the 19,200-tick / 32-beat cycle is enforced
   by the decoder `bars == 8` gate (not merely assumed), the renderer wraps
   `phase_tick % cycle_ticks`, and `phase_offset_beats` (default 0.0) is the right
   shape for capture calibration. (`soundswitch_pack_loader.py:26`,`:493-494`;
   `config.py:7-8`; `soundswitch_project_decoder.py` bars gate;
   `soundswitch_laser_player.py:125-147`; oracle `tools/ssfmt/re/autoloop_oracle/diff.py:11,83-88`.)
4. **Return contract.** The spec's exit-line map for `on_decision` is accurate:
   `LaserResolvedScene` returned on the success path and the `midi_trigger_rejected`
   path, `None` on every selection-gate path. Confirm each cited line.
5. **Reset asymmetry.** Master/active-deck/active-track/stop/resume reset both
   director and executor, but **scripted and idle reset only the director**, so the
   spec is right to add native resets explicitly at the scripted/idle sites and at
   `set_pack_runtime()`. (`state_manager.py` reset sites + `set_pack_runtime`.)
6. **Status migration.** `autoloop_phase_blocked` currently == `rt.active and
   lighting_mode == "autoloop"` and feeds the operational-state enum; the spec
   correctly requires it to stop reporting blocked while `rendering_active`, and
   names the enum doc surface, menubar label, and the three tests that must change.
   (`state_manager.py:137,151-152,3820-3822`; `docs/setup/runtime_commands.md`;
   `scripts/bridge_menubar.py:439`; `tests/test_state_manager_pack_driver.py:164-165,1102-1103`;
   `tests/test_bridge_menubar.py:488`.)
7. **Player API + diagnostics mapping.** `select_autoloop(identity, phase_tick, *,
   authority)` exists, and the spec's mapping of `_autoloop_base` diagnostics
   (`autoloop_not_found`→`missing_autoloop_file`, `inactive_autoloop`/
   `unsupported_layout`→`unsupported_layout`, all-zero→`empty_dark_look`) is sound.
   (`soundswitch_laser_player.py:270-276,352-378`.)
8. **Contracts/docs.** The change triggers both the `soundswitch_pack_player` and
   `laser` contracts; the new `native_autoloop_resolver.py` is not yet covered by
   any contract glob (Task 7 must add it); the spec + oracle spec are now indexed.
   Confirm the three hard checks pass at the current checkout. (`docs/agents/change_contracts.yml`,
   `tools/check_agent_contracts.py`.)

## Adversarial checks (find what's still wrong)
- **Task 0 gate.** The spec cannot confirm from in-repo files alone that the
  exported pack maps each role note (drops/post_drop/groove/etc.) to
  `target_kind == "autoloop"` rather than a SoundSwitch Static Look — that lives in
  the operator's exported `selection_map.json`, not in the repo. This is
  **independent of the laser-side `scene_type`**: `house_drop_1` is a laser
  `scene_type: "static"` scene that still sends MIDI `note 96` (`midi.kind:
  note_pulse`), and the laser `scene_type` (static/autoloop/utility, a refire knob)
  does **not** determine the SoundSwitch `target_kind`. The native resolver keys the
  binding by `(channel-1, note)` only, so by design note 96 should resolve to a
  drop Autoloop. Is the read-only Task 0 pre-check enough to confirm the export
  matches that design, or is a stronger gate needed before native drops are claimed
  renderable?
- **post_drop→drop fallback.** The authority doc requires "no post_drop look →
  cycle drop looks, not go dark." The spec implements "reuse the last drop
  identity." Is that faithful enough, or does it diverge from the authority doc in
  a way that matters live? Does it ever go dark when the doc says it shouldn't?
- **Hot path / 200 Hz.** Confirm the resolver stays I/O-free, that nothing adds
  blocking work to the push loop, and that the pack driver keeps exactly one
  normal `submit_frame` caller (no dual-driver with SoundSwitch present).
- **Live safety.** Scripted priority, Static Override Press/Toggle, and
  blackout/emergency precedence unchanged; fail-closed on missing/invalid bindings
  is complete; reload clears stale native state.
- **Completeness.** Missing tests, missing status fields, missing mode-transition
  cleanup, any `file:line` in the spec that is now stale, any internal
  contradiction, and anything the prior reviewer missed.

## Run (read-only) and report results
```
python3 tools/check_agent_contracts.py
python3 tools/check_docs_metadata.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
```

## Return
1. **Readiness verdict:** READY / READY_WITH_MINOR_NOTES / NOT_READY.
2. Per-claim verification table (claims 1–8 above): CONFIRMED/REFUTED/UNCERTAIN +
   `file:line`.
3. Any implementation blockers (with the exact spec section to amend).
4. Minimal amendments needed before implementation.
5. Tests/checks the implementer must run, and the result of the four doc checks
   above.
6. Anything the prior review missed.
