---
doc_status: completed-spec
truth_level: historical-implementation-spec
last_verified_commit: ef46de1
last_verified_date: 2026-06-24
validation_scope: implemented RW-4 static-slot runtime-swap regression fix; historical evidence only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — RW-4: resync carried static slot across a pack runtime swap

## Part A — Context & root cause (verified; read, do not implement)

The RW-4 controller-input health logic in `_drive_pack_output`
(`state_manager.py:3304-3334`) tracks the last static slot it pushed to the player in
`self._pack_last_static_slot`, and only (re)syncs the player when the wanted slot differs:

```python
slot = held_slot if input_healthy else None
player.set_masks(blackout=blackout, emergency=False)
if slot != self._pack_last_static_slot:          # state_manager.py:3329
    if slot is not None:
        player.hold_static(int(slot))
    elif self._pack_last_static_slot is not None:
        player.release_static(int(self._pack_last_static_slot))
    self._pack_last_static_slot = slot
```

- [confirmed] `_pack_last_static_slot` is written ONLY in `__init__` (`state_manager.py:360`)
  and at `:3334` (the push loop). Grep: no other writers.
- [confirmed] `set_pack_runtime` (`state_manager.py:3247-3254`) is a pure atomic assignment of
  the runtime ref. It does NOT reset `_pack_last_static_slot`.
- [confirmed] A runtime swap (`soundswitch_pack_controller.py:98-121 _swap_to_started`) publishes
  a **disabled** bundle first (so the driver returns early at `:3273-3274` and the tracker is left
  untouched), then publishes a NEW enabled bundle with a **new** `LaserPackPlayer` (always boots
  `_active_static_slot=None`, `soundswitch_laser_player.py:186`) and a **freshly built** midi_input
  group (`__main__.py:1273-1286`; adapters boot `_held_static_slot=None`,
  `soundswitch_midi_input.py:79`).

**Root cause [confirmed].** After a swap, `_pack_last_static_slot` can still hold the OLD player's
slot (e.g. 8) while the NEW player holds nothing. If the first post-swap snapshot reports that same
slot while healthy, `slot != self._pack_last_static_slot` is False, so `hold_static` is skipped and
the fresh player renders the scripted base instead of the static look. The tracker (StateManager-
level) and the player's actual state have diverged across the swap.

**Repro (ran, confirmed):** old runtime drives static 8 → `CH1=200`, `tracker=8`, latch False; swap
to new player + new input reporting `held=8` → first post-swap tick renders `CH1=9` (scripted base;
static suppressed), `tracker` still 8.

**Severity [confirmed LOW].** Reachable only if a genuine fresh note-on for the same slot is
processed by the new worker inside the sub-tick window between `start()` and the next ≤5 ms push
tick (the new group boots `held=None`, and a continuously-held button sends no new note-on across a
reload, so the realistic path self-heals in one tick). Failure direction is "scripted base instead
of static" — the same safe direction as the RW-4 degraded policy. Still a real divergence worth
closing for ~zero cost.

**Test gap [confirmed].** H8 leaves the tracker at default `None` (`8 != None` fires the hold); H10
pre-sets the latch (forces `slot=None`, so the inequality fires and heals). Neither exercises a
HEALTHY swap where the carried `_pack_last_static_slot` equals the new reported slot.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Touch ONLY `state_manager.py` and `tests/test_state_manager_pack_driver.py`.
- Do NOT reset `_pack_input_degraded_latched` — the latch MUST survive a swap (H10).
- Do NOT reset `_pack_last_mail_drop_count` — `:3316` re-baselines it every tick; leave it.
- No behavior change to the scripted-base gate (`:3336-3408`), the latch logic (`:3315-3325`), or
  any other subsystem. No new blocking I/O in `set_pack_runtime`.

### Task 1 — `state_manager.py`: reset the static-slot tracker on runtime swap
In `set_pack_runtime` (`:3247-3254`), after the runtime assignment, reset the static-slot tracker so
it can never diverge from the fresh player (which always boots `_active_static_slot=None`). Update
the docstring so it no longer claims "a single attribute assignment".

Replace:
```python
    def set_pack_runtime(self, runtime: PackRuntime) -> None:
        """Atomically publish a new pack runtime bundle (command thread → push loop).

        A single attribute assignment; the push loop reads one reference per tick, so
        it never sees a mixed old/new runtime. All blocking work (load_pack, serial
        open/close, old-sender zero_and_stop) must already be done by the caller.
        """
        self._pack_runtime = runtime or DISABLED_PACK_RUNTIME
```
with:
```python
    def set_pack_runtime(self, runtime: PackRuntime) -> None:
        """Atomically publish a new pack runtime bundle (command thread → push loop).

        The runtime ref is published in one assignment, so the push loop never sees a
        mixed old/new runtime. All blocking work (load_pack, serial open/close,
        old-sender zero_and_stop) must already be done by the caller.

        RW-4: a swapped-in bundle always carries a FRESH player (boots
        _active_static_slot=None) and a fresh input group (boots held=None), so the
        push loop's last-pushed static-slot tracker is reset here. Otherwise a slot
        carried from the old player could equal the new snapshot's slot, the
        `slot != _pack_last_static_slot` guard (:3329) would skip hold_static, and the
        new player would render the scripted base instead of the static. A single
        None reference assignment is atomic under the GIL; the push loop at worst reads
        it one tick stale and re-syncs. The degradation latch is deliberately NOT reset
        (it must survive a swap; see H10).
        """
        self._pack_runtime = runtime or DISABLED_PACK_RUNTIME
        self._pack_last_static_slot = None
```

### Task 2 — `tests/test_state_manager_pack_driver.py`: add H11 regression test
Add to the `PackDriverInputHealthTests` class (after H10), using the existing helpers
(`_make_sm`, `_FakeBackend`, `_FakeInput`, `LaserPackPlayer`, `_pack`, `_set`, `SSID`, `PackRuntime`
— all already imported in this file):

```python
    # H11 — regression: a static slot carried in _pack_last_static_slot across a
    # runtime swap must NOT suppress hold_static on the fresh player when the new
    # snapshot reports the same slot while healthy.
    def test_runtime_swap_resyncs_carried_static_slot(self):
        old_be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=old_be,
                      midi_input=_FakeInput(held_static_slot=8))
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(old_be.frames[-1][0], 200)          # old player honors static 8
        self.assertEqual(sm._pack_last_static_slot, 8)
        self.assertFalse(sm._pack_input_degraded_latched)    # healthy swap, not latched

        new_be = _FakeBackend()
        sm.set_pack_runtime(PackRuntime(
            enabled=True, reason="pack", player=LaserPackPlayer(_pack()),
            midi_input=_FakeInput(held_static_slot=8), backend=new_be))
        self.assertIsNone(sm._pack_last_static_slot)          # tracker reset on swap
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(new_be.frames[-1][0], 200)           # fresh player honors static 8
```

## Part C — Invariants that MUST still hold (live safety)
- Degradation latch survives a runtime swap (H10 stays green) — the fix must not touch
  `_pack_input_degraded_latched`.
- `set_pack_runtime` stays non-blocking (no I/O); the runtime ref is still published in a single
  assignment so the push loop never sees a half-swapped bundle.
- The scripted base keeps running on a degraded controller (RW-4 policy unchanged); static/blackout
  still lose to the latch.
- Mail-drop baseline behavior unchanged (`:3315-3316`).
- No DeckState/OutputState mutation introduced.

## Part D — Tests
- New: H11 above (pure in-memory; fake backend/input/player; no files/serial/MIDI). It fails before
  Task 1 (renders `CH1=9`) and passes after (`CH1=200`).
- Regression: full `tests/test_state_manager_pack_driver.py` (currently 54 tests; 55 after).

## Part E — Acceptance (definition of done)
- [ ] Task 1 applied; `set_pack_runtime` resets `_pack_last_static_slot` and the docstring matches.
- [ ] Latch reset is NOT added; mail-drop baseline is NOT reset.
- [ ] H11 added and passes; it provably fails if Task 1 is reverted.
- [ ] `python3 -m unittest rb_ss_bridge_v2.tests.test_state_manager_pack_driver` → all pass (55).
- [ ] H10 (`test_latch_survives_runtime_swap`) still passes.
- [ ] Only `state_manager.py` and `tests/test_state_manager_pack_driver.py` changed.

## When you finish
- Commit message: `RW-4: reset static-slot tracker on pack runtime swap (+ H11 regression)`.
- Report back: the H11 before/after CH1 values (9 → 200) and the full pack-driver test count (55 OK).
