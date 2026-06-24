# RW-1A revision — disposable Codex spec (DELETE THIS FILE WHEN DONE)

Revision of the already-merged RW-1A shutdown-ownership work, from independent
review. **Only two files** may change: `__main__.py` and
`tests/test_soundswitch_pack_startup.py`. Commit per task. **As your final
action, delete this file (`RW1A_REVISION_CODEX.md`) and include that deletion in
your last commit.**

Do not touch other modules. Do not restart the bridge, open MIDI/serial/Enttec,
enable pack output, or run hardware. Offline unit tests only.

## Context (verified — read, do not re-derive)
- `_shutdown` calls `_cleanup_pack_outputs()` at `__main__.py:1582` (fast blackout),
  but `command_reader.stop()` is at `__main__.py:1586`.
- `CommandReader.stop()` (`runtime_status.py:248-249`) only sets an event; it does
  **not** join. The command thread can finish a swap and publish a new started
  sender via `sm.set_pack_runtime` (`__main__.py:1289`, controller
  `_swap_to_started`) **after** the first cleanup's single `get_pack_runtime()`
  read — stranding that live sender unclosed on shutdown (no graceful zero).
- `CommandReader` is a `threading.Thread` subclass (`runtime_status.py:206`), so it
  has `.join()`.
- `_cleanup_pack_outputs()` and `_shutdown_zero_pack_outputs(...)` are idempotent:
  owner slots are `pop`'d; `SoundSwitchFrameSender.stop()` is `_stopped`-guarded
  (`soundswitch_frame_sender.py:155`); MIDI-group `stop()` is documented safe to
  call repeatedly (`soundswitch_midi_input.py:174-187, 427-433`).

## Task 1 — `__main__.py`: close the concurrent-swap race in `_shutdown`
Keep the existing fast `_cleanup_pack_outputs()` at line 1582 (immediate blackout).
After the command reader is stopped, **join it, then re-zero** so any swap that was
in flight at signal time is caught. Insert immediately after the existing
`command_reader.stop()` line (currently `__main__.py:1586`) and before `sm.stop()`:

```python
        command_reader.stop()
        command_reader.join(timeout=2.0)   # quiesce the command thread: no more swaps can publish
        _cleanup_pack_outputs()            # authoritative re-zero of the final live runtime (idempotent)
        sm.stop()
```

Rationale: the first cleanup blacks out fast; the join ensures no further
`set_pack_runtime` publish can occur; the second cleanup zeros whatever sender is
actually live last. Both cleanups are idempotent, so the no-swap case just
re-stops an already-stopped sender (no-op). Do not move the first cleanup; do not
add blocking work to `_push_tick` or `StateManager._run()`.

## Task 2 — `tests/test_soundswitch_pack_startup.py`: cover the revision + the gaps
Add to `StartupMatrixTests`:

1. **Source-order guard for the race fix** (mirror the existing
   `test_shutdown_zeros_pack_before_slow_bridge_joins` style with
   `inspect.getsource(bridge_main.main)`): assert that within `def _shutdown`,
   `command_reader.join(` appears after `command_reader.stop()`, that a second
   `_cleanup_pack_outputs()` appears after `command_reader.join(`, and that this
   second `_cleanup_pack_outputs()` appears before `sm.stop()`.

2. **No-swap same-object double-stop** (direct call to
   `bridge_main._shutdown_zero_pack_outputs`): one `FakeSender` and one
   `FakeInput` that count calls; put the SAME objects in both the owners dict and
   the `FakeSM`'s runtime; assert each object's `stop()` is called and that a
   second `_shutdown_zero_pack_outputs(owners, sm)` does not raise (idempotent
   repeat cleanup, e.g. signal-then-atexit).

3. **Repeat-cleanup drains owners**: after one call, assert `"sender"`/
   `"midi_input"` keys are gone from the owners dict and a second call is a no-op.

## Gates (must pass before done)
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3   -m unittest tests.test_soundswitch_pack_startup
python3.11 -m unittest tests.test_soundswitch_pack_startup
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
git diff --check
```

## Report back
- unittest summary lines (3.14 + 3.11 + full suite), the four docs-check results,
  confirm only `__main__.py` + the test file changed (plus this file's deletion),
  and confirm `RW1A_REVISION_CODEX.md` is deleted.

(Subsystem-card / roadmap doc updates are handled separately by Claude — do not
touch docs.)
