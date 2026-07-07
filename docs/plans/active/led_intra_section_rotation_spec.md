---
doc_status: current
truth_level: code-verified
last_verified_commit: d5cdcd4
last_verified_date: 2026-07-06
validation_scope: Codex implementation spec for intra-section LED look rotation (buildup/pre_drop/breakdown/ambient); software tests only; hardware-unvalidated
---

# Codex Implementation Spec - Intra-section LED look rotation

> You are an autonomous senior engineer: once given this spec, proactively gather context, plan, implement, test, and refine without waiting for additional prompts. Persist until the task is fully handled end-to-end within the current turn. Bias to action; do not end your turn with clarifications unless truly blocked.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make. If you notice unexpected changes you didn't make, STOP and ask how to proceed. NEVER use destructive commands like `git reset --hard` or `git checkout --`.

> Act as a discerning engineer: optimize for correctness and reliability; cover the root cause, not a symptom. Conform to codebase conventions. Tight error handling: no broad try/catch, no success-shaped fallbacks.

## Part A - Context & Root Cause (verified; read, do not implement)

Live-run problem (operator, 2026-07-06 evening set): LEDs get stuck on one look for a whole long section — observed 76 s frozen during one long build ("Runaway (U & I) [Kaskade Remix]", 20:29:40→20:30:54), strips healthy, not idle, not CPU-starved.

Root cause — all **[confirmed]** at HEAD d5cdcd4:

- Looks fire only when `role_key` changes: `_dispatch_led_automation` early-returns at `led_dispatch_policy.py:810-811` when `role_key == self._led_last_auto_role_key`.
- `_led_automation_role_key` (`led_dispatch_policy.py:1631-1734`) gives `groove` and `post_drop` an `elapsed // cycle_beats` term (`:c{cycle}`) so their keys change every N beats — the existing intra-section rotation. The `buildup`/`pre_drop` branch (`:1672-1673`) uses only `next_smart_drop_beat`, the `breakdown` branch (`:1674-1675`) only `breakdown_restore_beat`, and `ambient` (`:1724-1729`) only `label:seq` — none carries a cycle term, so those keys are constant for the entire section and the look freezes however long it runs.
- Downstream needs no change **[confirmed]**: when the key changes, `LEDLookDirector._automation_decision_for_role` (`led_look_director.py:271-344`) advances its per-role cursor (all roles are shuffle-bag ordered via `shuffled_roles=LED_AUTOMATION_ROLE_ORDER`, `__main__.py:496`) and picks the next look in the pool.
- The structured pair `self._led_last_section_cycle = (section_id or marker, cycle)` (`led_dispatch_policy.py:1733`) feeds `engine.begin_dispatch(section_id=..., cycle=...)` (`:814`, `:832-842`). The v2 color engine already distinguishes "same section, new cycle" (groove/post_drop exercise this today), so rotation must keep `section_id` = the stable pre-cycle string and put the cycle only in `marker`/`cycle`.
- `sp_state.beats_to_next_drop` is the canonical remaining-distance value (`smart_phrasing.py:334`, `drop_beat - abs_beat`) — reuse it; do not recompute.
- `LED_DEFAULT_GROOVE_CYCLE_BEATS = 32.0` (`led_dispatch_policy.py:32`) is the existing rotation cadence constant — reuse it; do not add a config knob.

**[known interaction, deliberate]** Each rotation increments `_led_automation_trigger_count`, which recomputes the laser CH8 color (theme-2 fix): the laser color may re-settle at look rotations if the LED palette drifted across a quantization boundary. Accepted; do not add gating.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch only: `led_dispatch_policy.py` (`_led_automation_role_key` only), tests under `tests/`, and the Part E docs.
- Do not touch: the `drop`, `groove`, `post_drop` branches; the dedupe gate at `:810`; `led_look_director.py`; `led_color_engine.py`; any config or example-config file; the non-monotonic legacy branches other than where a task names them.
- Behavior that must not change: `role_key` for `drop` role; section identity semantics (`section_id` stays the stable pre-cycle string); dispatch early-returns for hold/blackout paths that run before role selection; no new I/O/locks/threads on the 200 Hz path (this is pure in-memory arithmetic).
- Error handling: `None` inputs (missing `abs_beat`, missing `beats_to_next_drop`) mean cycle stays `0` and the marker keeps today's exact shape — never raise, never invent a fallback anchor.

### Task 1 - `led_dispatch_policy.py`: cycle term for `buildup`/`pre_drop`
Replace the branch at `:1672-1673`:
```python
elif role in {"buildup", "pre_drop"} and sp_state.next_smart_drop_beat is not None:
    marker = f"{sp_state.next_smart_drop_beat:.3f}"
```
with a countdown cycle anchored on the drop marker itself (rotations land at fixed distances before the drop; immune to phrase-start re-reads):
```python
elif role in {"buildup", "pre_drop"} and sp_state.next_smart_drop_beat is not None:
    section_id = f"{sp_state.next_smart_drop_beat:.3f}"
    if sp_state.beats_to_next_drop is not None:
        cycle = int(max(0.0, float(sp_state.beats_to_next_drop)) // LED_DEFAULT_GROOVE_CYCLE_BEATS)
    marker = f"{section_id}:c{cycle}"
```
Note the cycle counts DOWN as the drop approaches (…2, 1, 0) — each change re-fires the director exactly like groove's ascending cycle does; direction is irrelevant to the dedupe gate.

### Task 2 - `led_dispatch_policy.py`: cycle term for `breakdown`
Replace the branch at `:1674-1675` with the same shape, remaining distance computed inline from the restore marker (no canonical helper exists for it):
```python
elif role == "breakdown" and sp_state.breakdown_restore_beat is not None:
    section_id = f"{sp_state.breakdown_restore_beat:.3f}"
    abs_beat = self._led_abs_beat(sp_state)
    if abs_beat is not None:
        remaining = max(0.0, float(sp_state.breakdown_restore_beat) - float(abs_beat))
        cycle = int(remaining // LED_DEFAULT_GROOVE_CYCLE_BEATS)
    marker = f"{section_id}:c{cycle}"
```

### Task 3 - `led_dispatch_policy.py`: cycle term for `ambient` (monotonic path only)
In the `ambient` branch (`:1724-1729`), extend only the `_phrase_monotonic_enabled` arm, mirroring groove's committed-start pattern (`:1689-1696`):
```python
if self._phrase_monotonic_enabled:
    abs_beat = self._led_abs_beat(sp_state)
    section_id = f"{sp_state.current_phrase_label}:seq{self._led_phrase_seq}"
    if abs_beat is not None:
        committed = self._led_phrase_committed_start
        if committed is None:
            committed = sp_state.current_phrase_start_beat
        elapsed = max(0.0, float(abs_beat) - float(committed or 0.0))
        cycle = int(elapsed // LED_DEFAULT_GROOVE_CYCLE_BEATS)
    marker = f"{section_id}:c{cycle}"
else:
    marker = str(sp_state.current_phrase_label)
```
Leave the legacy (non-monotonic) arm exactly as today.

Line `:1733` (`self._led_last_section_cycle = (section_id or marker, cycle)`) already publishes correctly once the three branches set `section_id` and `cycle` — do not change it; update its comment (the "unlisted branches" note at `:1730-1732` is now wrong for buildup/pre_drop/breakdown/ambient).

## Part C - Invariants That MUST Still Hold (live safety)

- 200 Hz push loop gains no blocking I/O, locks, or per-tick allocations beyond string building already done today (AGENTS.md §6).
- `StateManager` remains the only `DeckState` writer.
- `section_id` stays stable across a section while only `cycle` moves — the color engine's per-section journey state must not reset on rotation (same contract groove/post_drop rely on).
- Blackout/hold/pre-drop-blackout early returns in `_dispatch_led_automation` still run before role_key is consulted — rotation never fights a blackout.
- Scripted mode and manual-override behavior unchanged.

## Part D - Tests

Pure seam: `_led_automation_role_key` and `_led_last_section_cycle` are directly drivable with synthetic `SmartPhrasingState` — no files/subprocess. Existing coverage lives in `tests/test_led_state_manager.py` and `tests/test_led_color_engine_integration.py` (grep for role_key / section_cycle tests and extend beside them).

1. buildup: fixed `next_smart_drop_beat`, advance `beats_to_next_drop` 100→0: key changes exactly at the 32-beat boundaries; `section_id` constant; `cycle` descends; `beats_to_next_drop=None` reproduces today's key shape with `:c0`.
2. breakdown: same via `breakdown_restore_beat` and abs_beat advancing; `abs_beat=None` → cycle 0.
3. ambient (monotonic): elapsed crossing 32 beats changes the key; `seq` change still changes the section as before.
4. Regression: `groove`, `post_drop`, `drop` keys byte-identical to before for identical inputs.
5. Integration: driving dispatch across a cycle boundary fires a second look for the same role (cursor advances) — extend an existing dispatch-path test rather than building a new harness.
6. Run `python3 -m unittest tests.test_led_state_manager tests.test_led_color_engine_integration`, then `python3 -m unittest discover tests`. Known pre-existing full-suite failures at this HEAD, NOT yours to fix and NOT acceptable to worsen: `tests.test_led_color_engine_m2_patch_d` (live-config dependent) and `tests.test_export_pack_parity_self_heal` (fixture-dependent).

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-3 landed; comment at `:1730-1732` corrected.
- [ ] Full suite green: `python3 -m unittest discover tests`.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Contract `led_govee` docs updated for the new rotation semantics: `docs/subsystems/led_govee.md` (describe the rotation + the 32-beat cadence), `docs/status/feature_status_matrix.md`, `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`, `docs/status/active_work_registry.md` (register this spec). Inspect the remaining contract docs (`docs/status/support_matrix.md`, `docs/validation/hardware_validation_log.md`, `docs/architecture/palette_control_authority.md`, `docs/plans/active/streamdeck_palette_control_design_spec.md`, `docs/agents/task_playbooks/change_led_govee_behavior.md`) and update only if their described behavior changed; report which you checked and left unchanged.
- [ ] Status language §10-allowed only (`implemented`, `software-tested`, `hardware-unvalidated`).
- [ ] Do not commit; leave changes in the worktree for review.

## When You Finish

Report: changed files, exact test/check commands with pass counts, and which contract docs you inspected but left unchanged. Plain-language operator summary: long builds, breakdowns, and unclassified stretches now switch to a fresh look every 32 beats instead of freezing on one; drops and short sections behave exactly as before; the room's color story per section is unchanged (only the shape/pattern rotates); one watchpoint — the laser's held color may re-settle at those same rotation moments if the palette has drifted; hardware-unvalidated until the next live run.
