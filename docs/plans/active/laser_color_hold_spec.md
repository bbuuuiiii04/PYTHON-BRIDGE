---
doc_status: current
truth_level: code-verified
last_verified_commit: d5cdcd4
last_verified_date: 2026-07-06
validation_scope: Codex implementation spec for holding the laser color-engine CH8 override on every autoloop frame; software tests only; hardware-unvalidated
---

# Codex Implementation Spec - Hold laser engine color on every autoloop frame (CH8)

> You are an autonomous senior engineer: once given this spec, proactively gather context, plan, implement, test, and refine without waiting for additional prompts. Persist until the task is fully handled end-to-end within the current turn. Bias to action; do not end your turn with clarifications unless truly blocked.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make. If you notice unexpected changes you didn't make, STOP and ask how to proceed. NEVER use destructive commands like `git reset --hard` or `git checkout --`.

> Act as a discerning engineer: optimize for correctness and reliability; cover the root cause, not a symptom. Conform to codebase conventions. Tight error handling: no broad try/catch, no success-shaped fallbacks, no silent early-returns on invalid input.

## Part A - Context & Root Cause (verified; read, do not implement)

Live-run problem (operator, 2026-07-06 evening set): lasers keep their baked autoloop colors and ignore the LED palette. Bridge was in v2 direct-DMX pack mode (bridge owned the Enttec box).

Root cause — all **[confirmed]** against HEAD d5cdcd4:

- The color merge already works: `soundswitch_laser_player.py:124` (`_merge_color_snapshot`) overwrites CH8 (`merged[7]`) — and CH9 (`merged[8]`) only when the snapshot carries a non-None ch9 — and it is called at exactly one site, `soundswitch_laser_player.py:462`, inside the autoloop-base render. When `self._color_snapshot` is None the frame passes through untouched (baked pack color).
- `LaserColorEngine` (`laser_color_engine.py:78-112`) already **persists** its snapshot: `update()` sets `self._snapshot`, and `snapshot()` returns it until the next `update()` call. `update()` is called only on the tick an accepted automation-driven LED look fires (`state_manager.py:4171-4178`, gated by `_led_automation_trigger_count` and `d.playing`).
- The bug is pure consumption-side: `_drive_pack_output` (`state_manager.py:3390-3396`) forwards the snapshot to the player **only on the trigger tick** (`_laser_color_updated_this_tick` gate) and `_push_tick` resets the per-tick fields every tick (`state_manager.py:3050`, `_reset_laser_color_tick` at `:3067-3069`; a second reset at `:3396`). Net: `player._color_snapshot` is non-None for ~1 tick per LED trigger out of a 200 Hz loop, so ~every autoloop frame shows the pack's baked CH8.
- CH9 (color speed) is **[confirmed]** currently inert: live `config/laser_color_map.json` has `fixed_ch9: null` and `effects.rainbow_family.ch9: null`, and white moments return `ch9=None` (`laser_color_engine.py:129`), so `_target()` never yields a non-None ch9 with this config. Movement stays baked with no code change.
- Safety of a persistent snapshot is proven by the render path **[confirmed]**: `render()` returns ZERO_FRAME on emergency/blackout before any base (`soundswitch_laser_player.py:467-468`); reload-wait and base-suppression return diagnostics before the base; the scripted branch (`_scripted_base`) never calls the merge; the autoloop branch rejects stale/ambiguous authority, missing phase, unknown/inactive identity, unsupported layout, and unverified parity (`:432-459`) before the merge at `:462`. A held snapshot can therefore only color fresh, clean autoloop base frames.

**[assumed]** Holding the last engine color across track transitions (until the next LED automation trigger) is acceptable operator taste — the LED engine's color state is continuous across a live mix, so the held laser color tracks the room palette. No cross-track reset is wanted; do not add one.

**[known behavior, deliberate]** After this fix, the laser color still only *recomputes* at LED automation triggers (today ≈ section entries). If future work adds more triggers, the color re-settles at those triggers too; that is accepted. Do not add section-identity gating.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch only: `state_manager.py`, tests under `tests/`, and the Part E docs. Do not touch `soundswitch_laser_player.py`, `laser_color_engine.py`, `led_color_engine.py`, `led_dispatch_policy.py`, or any config file.
- Behavior that must not change: scripted/diagnostic/idle/masked frames never gain color; blackout/emergency still render ZERO; `enabled:false` or missing/invalid config stays byte-identical pass-through (engine `update()` already sets `_snapshot=None` when disabled); CH11 untouched; `_update_laser_color_from_led` still called only on LED-trigger ticks.
- No new locks, I/O, sleeps, threads, or allocations-per-tick beyond an attribute read on the push-tick path.
- Error handling: keep the existing narrow try/except in `_update_laser_color_from_led`; on exception the engine simply keeps its previous held snapshot (do not force-clear, do not broaden the except).

### Task 1 - `state_manager.py`: forward the engine's held snapshot every drive
In `_drive_pack_output`, replace the gated lookup (currently `state_manager.py:3390-3396`):
```python
color_snapshot = (
    self._laser_color_snapshot_for_tick
    if self._laser_color_updated_this_tick
    else None
)
player.set_color_snapshot(color_snapshot)
self._reset_laser_color_tick()
```
with an unconditional read of the engine's persistent snapshot:
```python
laser_color_engine = self._laser_color_engine
player.set_color_snapshot(
    laser_color_engine.snapshot() if laser_color_engine is not None else None
)
```
`snapshot()` is a plain in-memory field read (`laser_color_engine.py:111-112`) — safe on the 200 Hz path.

### Task 2 - `state_manager.py`: delete the now-dead per-tick plumbing
- Remove the `self._reset_laser_color_tick()` call in `_push_tick` (`state_manager.py:3050`) and the `_reset_laser_color_tick` method (`:3067-3069`).
- In `_update_laser_color_from_led` (`:3071-3094`): keep the `led_engine.color_state()` + `laser_engine.update(...)` calls and the narrow try/except, but remove the four writes to `_laser_color_snapshot_for_tick` / `_laser_color_updated_this_tick` (both in the happy path and the except path; the except body becomes `pass` with a one-line comment that the engine holds its previous color on a read failure).
- Remove the `_laser_color_snapshot_for_tick` / `_laser_color_updated_this_tick` attribute initializations (find them in `__init__` via grep) and any other remaining references. `grep -n "_laser_color_updated_this_tick\|_laser_color_snapshot_for_tick\|_reset_laser_color_tick" state_manager.py tests/ -r` must return zero code hits when done (test updates in Part D).

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop gains no blocking network/socket/MIDI/filesystem/subprocess I/O and no locks (AGENTS.md §6).
- `StateManager` remains the only writer of `DeckState`; events immutable.
- Blackout and emergency masks always yield ZERO frames; a crash in the tick body still submits the direct ZERO frame (`_push_tick` except path — do not restructure `_push_tick` beyond deleting the one reset call).
- Scripted, diagnostic, idle, stale-authority, and masked frames must not inject color (guaranteed by the untouched player render path).
- `enabled:false` / all-null tables / missing snapshot = byte-identical pass-through.
- CH11 (strobe) is never written by laser color plumbing.

## Part D - Tests

Contract `laser_color` test seam is pure (player + engine are plain objects; no files/subprocess needed).

1. Update any existing tests that assert the old one-tick semantics (likely in `tests/test_state_manager_pack_driver.py` / `tests/test_laser_color_engine.py` — find with the grep above): they must now assert the snapshot is forwarded on **every** drive while the engine holds one.
2. New/extended coverage, minimal:
   - After one LED trigger tick sets an engine color, N subsequent drive ticks (no new trigger) all render autoloop frames with CH8 = engine byte (hold), CH9 = baked value unchanged.
   - Blackout tick during a held color renders ZERO; releasing blackout returns to the held-color autoloop frame.
   - Engine disabled (config `enabled:false`) or engine None: frames byte-identical to baked pack output across many ticks.
3. Run: `python3 -m unittest tests.test_laser_color_engine tests.test_soundswitch_laser_player tests.test_led_color_engine tests.test_led_palette_control tests.test_state_manager_pack_driver`, then the full `python3 -m unittest discover tests`.

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-2 landed; grep for the three dead names returns zero hits in code.
- [ ] Full suite green: `python3 -m unittest discover tests`.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Contract `laser_color` docs updated to describe hold-on-every-frame semantics: `docs/subsystems/laser.md`, `docs/architecture/laser_color_authority.md`, `docs/plans/active/laser_color_engine_design_spec.md`, `docs/status/active_work_registry.md` (register this spec there too).
- [ ] Status language stays §10-allowed (`implemented`, `software-tested`, `hardware-unvalidated`).
- [ ] Do not commit; leave changes in the worktree for review.

## When You Finish

Report: changed files, exact test/check commands run with pass counts, and any test whose expectations you inverted (old one-tick assertions). Plain-language summary for the operator: lasers now hold the palette-driven color on every autoloop frame instead of flashing it for 1/200th of a second; movement (CH9) stays as authored; blackout/emergency/scripted behavior unchanged; one watchpoint — CH8 also carries some baked color-effects, so a pack cue whose look depended on its own baked CH8 color-effect will now show the engine's solid color instead (intended, but worth eyes at the next live run); hardware-unvalidated until then.
