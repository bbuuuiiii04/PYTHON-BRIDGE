---
doc_status: completed-spec
truth_level: historical-implementation-spec
last_verified_commit: bd23413
last_verified_date: 2026-06-23
validation_scope: implemented RW-1A shutdown-ownership spec; historical evidence only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — RW-1A: zero the live swapped pack sender on shutdown

> **Goal (plain language):** When the bridge is shut down (Ctrl-C, SIGTERM, or
> normal exit), the SoundSwitch pack's DMX output must send a final all-zero
> (blackout) frame and close the serial port. Today that is guaranteed only for
> the sender that existed at startup. If the operator enabled/reloaded the pack
> *while the bridge was running* (a "runtime swap"), the new live sender is never
> told to zero on shutdown, so the Enttec keeps holding the last frame and the
> fixtures stay lit. This closes that gap.

This is roadmap item **RW-1A** in
`docs/plans/active/soundswitch_exporter_remaining_work.md` (§5, §6 Milestone
M2A). It must land before any pack-output enablement or hardware work.

---

## Part A — Context & root cause (verified; read, do not implement)

### What exists today

- `[confirmed]` `__main__.main()` installs an early owner-cleanup closure before
  any pack port opens. `pack_output_owners` is a mutable dict with `"sender"`
  and `"midi_input"` slots (`__main__.py:872`). `_cleanup_pack_outputs()`
  (`__main__.py:874-886`) pops those two slots and calls `.stop()` on each,
  swallowing exceptions.
- `[confirmed]` Those slots are written **only at startup**, around the startup
  worker construction (`__main__.py:906-907` and `:911-912`). Nothing writes
  them again after startup.
- `[confirmed]` `_cleanup_pack_outputs()` is invoked from three places: the
  `_early_shutdown` signal handler used during startup (`__main__.py:888-895`),
  the `atexit` registration (`__main__.py:893`), and the final `_shutdown`
  signal handler installed after the bridge is fully built
  (`__main__.py:1540-1543`). The final `_shutdown` calls it **before** the
  slower watcher/thread joins and `sm.stop()` (`__main__.py:1543-1548`).
- `[confirmed]` At startup the live sender is **already** published into the
  StateManager runtime: `PackRuntime(...)` is built with
  `frame_sender=soundswitch_frame_sender` (`__main__.py:928-935`) and passed as
  `soundswitch_pack_runtime=` to the `StateManager(...)` constructor
  (`__main__.py:1019-1031`). So `sm.get_pack_runtime().frame_sender` holds the
  startup sender from the moment `sm` exists.
- `[confirmed]` `StateManager.get_pack_runtime()` returns the current immutable
  runtime via a single atomic attribute read (`state_manager.py:3242-3244`);
  `set_pack_runtime()` is a single atomic assignment (`state_manager.py:3233-3240`).
- `[confirmed]` A runtime swap (`enable`, `backend=pack`, or `reload` while
  enabled) runs on the command thread through
  `SoundSwitchPackController._swap_to_started()`
  (`soundswitch_pack_controller.py:98-121`). It builds a NEW sender, publishes it
  via `set_pack_runtime` (`publish=sm.set_pack_runtime`, `__main__.py:1250`), and
  `_safe_zero_and_stop`s the OLD sender (`soundswitch_pack_controller.py:107`).
  After a swap, `sm.get_pack_runtime().frame_sender` is the **new** sender and
  `pack_output_owners["sender"]` is still the **old** startup sender.
- `[confirmed]` `StateManager.stop()` only sets the stop event
  (`state_manager.py:614-615`). `_run()` loops until that event and exits with no
  pack zeroing (`state_manager.py:868-900+`). The push loop never zeroes the pack
  on exit.

### Root cause

`[confirmed]` On shutdown, `_cleanup_pack_outputs()` stops only the
**startup-owned** sender/input. After a runtime swap:

1. the startup sender it stops was already zeroed by the swap (so stopping it is
   a harmless near-no-op), and
2. the **live** swapped sender — the one actually still holding the Enttec serial
   port and the last DMX frame — is referenced only by `sm.get_pack_runtime()`,
   which no shutdown path consults.

Result: `[confirmed]` the live swapped sender is never asked to send its final
zero frame or close. Fixtures retain the last lit frame on graceful shutdown.

### Why it is latent, not yet live

- `[confirmed]` Pack output is default-off; the ignored local
  `config/soundswitch_pack_player.json` is absent, so no runtime swap to a
  started sender happens today. The gap becomes real the first time pack output
  is enabled at runtime — which is a prerequisite for RW-6/M5 hardware work.

### Idempotency facts the fix relies on

- `[confirmed]` `SoundSwitchFrameSender.stop()` guards on `self._stopped` and is
  a no-op on the second call (`soundswitch_frame_sender.py:153-159`). `stop()`
  internally calls `zero_and_stop()` which enqueues the zero packet before
  closing (`soundswitch_frame_sender.py:182-190`).
- `[confirmed]` The swap path calls `zero_and_stop()` directly on the old sender,
  which does **not** set `_stopped` (`soundswitch_pack_controller.py:39`,
  `soundswitch_frame_sender.py:182-190`). So a later `.stop()` on that same old
  sender re-runs zero_and_stop once more — a harmless extra zero packet, never an
  error.
- `[confirmed]` `SoundSwitchMidiInputGroup.stop()` iterates its entries inside
  try/except and sets `_started=False` (`soundswitch_midi_input.py:427-433`);
  calling it twice is safe.

### Why this is smaller than the roadmap's option (a)

The roadmap floated re-registering every swapped sender into
`pack_output_owners` from the controller on each publish. That adds cross-thread
writes from the command thread into a dict owned by `main()`. It is unnecessary:
because `sm.get_pack_runtime()` is *already* the single source of truth for the
live sender (startup and post-swap alike), the shutdown path can read it
directly (roadmap option b). **No controller changes. No per-publish
re-registration.**

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Do **not** touch `soundswitch_pack_controller.py`, `state_manager.py`,
  `soundswitch_frame_sender.py`, `soundswitch_midi_input.py`, or
  `soundswitch_pack_runtime.py`. The fix is entirely in `__main__.py` plus a new
  test.
- Do **not** add any blocking/network/MIDI/serial/sleep work to the 200 Hz push
  loop. All work here runs on the shutdown/command path, never in `_push_tick`.
- Do **not** change startup ordering, the existing `pack_output_owners` startup
  writes, or the position of `_cleanup_pack_outputs()` within `_shutdown`
  (an existing source-order test asserts it).
- Do **not** change default-off behavior: when no pack runtime is active,
  `get_pack_runtime()` returns the disabled runtime whose `frame_sender`/
  `midi_input` are `None`, and the new code must be a guarded no-op.

### Task 1 — `__main__.py`: extract a module-level shutdown-zero helper

Add a module-level function (place it just above `def main()` near
`__main__.py:862`, in the `# ── Main ──` region) that zeroes BOTH the
startup-owned outputs and the live (possibly swapped) runtime outputs. It takes
the owners dict and an optional StateManager (None during the pre-`sm` startup
window):

```python
def _shutdown_zero_pack_outputs(
    pack_output_owners: dict[str, Any],
    sm: Any | None,
) -> None:
    """Send a final zero frame + close on shutdown for the pack's DMX output.

    Zeroes the LIVE runtime sender/input (authoritative after any runtime swap)
    AND the startup-owned slots. All calls are idempotent: stop() on an already-
    stopped sender is a no-op, and the no-swap case where the live sender IS the
    startup sender simply stops the same object once. sm is None only during the
    pre-StateManager startup window, where only the startup slots exist.
    """
    # Live runtime first: this is the only handle to a sender installed by a
    # runtime enable/reload/backend swap. Single atomic read of the runtime.
    if sm is not None:
        try:
            rt = sm.get_pack_runtime()
        except Exception:
            rt = None
        if rt is not None:
            live_sender = getattr(rt, "frame_sender", None)
            if live_sender is not None:
                try:
                    live_sender.stop()
                except Exception:
                    pass
            live_input = getattr(rt, "midi_input", None)
            if live_input is not None:
                try:
                    live_input.stop()
                except Exception:
                    pass
    # Startup-owned slots: covers the pre-sm early-shutdown window and is a
    # harmless no-op once the live sender (same object pre-swap) is stopped.
    sender = pack_output_owners.pop("sender", None)
    midi_input = pack_output_owners.pop("midi_input", None)
    if sender is not None:
        try:
            sender.stop()
        except Exception:
            pass
    if midi_input is not None:
        try:
            midi_input.stop()
        except Exception:
            pass
```

> Note: keep the exact two-slot startup-owner behavior identical to the current
> `_cleanup_pack_outputs()` body — it is moved here verbatim, with the live-runtime
> block added above it.

### Task 2 — `__main__.py`: route the cleanup closure through the helper + a mutable `sm` holder

Inside `main()`, replace the body of the existing `_cleanup_pack_outputs()`
closure (`__main__.py:874-886`) so it delegates to the new helper, and give it a
mutable holder for `sm` (which does not exist yet when the closure is defined):

```python
    pack_output_owners: dict[str, Any] = {"sender": None, "midi_input": None}
    _sm_holder: dict[str, Any] = {"sm": None}  # set after StateManager is built

    def _cleanup_pack_outputs() -> None:
        _shutdown_zero_pack_outputs(pack_output_owners, _sm_holder["sm"])
```

Then, immediately after the `StateManager(...)` is constructed
(`__main__.py:1019-1031`, right after the closing `)` on line 1031), publish the
reference:

```python
    _sm_holder["sm"] = sm
```

Everything else stays unchanged: `_early_shutdown`, the `atexit.register`, the
SIGTERM/SIGINT installs, and the final `_shutdown` ordering are untouched. Before
`sm` exists, `_sm_holder["sm"]` is `None`, so `_early_shutdown` still only
touches the startup slots — exactly as today.

### Task 3 — add the behavioral test (see Part D)

---

## Part C — Invariants that MUST still hold (live safety)

1. **Graceful shutdown zeroes the live DMX output.** After any runtime swap, the
   sender currently holding the Enttec port receives its final zero frame and is
   closed on SIGTERM/SIGINT/atexit. (This is the behavior being added.)
2. **No push-loop regression.** No filesystem/socket/MIDI/serial/sleep/blocking
   work is added to `_push_tick` or `StateManager._run()`. All new work is on the
   shutdown/command path. (`runtime_invariants.md`.)
3. **Atomic runtime read.** The live sender is obtained via a single
   `sm.get_pack_runtime()` call (one atomic attribute read); no iteration over or
   mutation of runtime state. No new writer of `_pack_runtime`.
4. **Default-off neutrality.** With pack output absent/disabled,
   `get_pack_runtime()` yields `None` sender/input and the helper is a no-op; OS2L,
   MIDI lasers, LEDs/Govee, Rekordbox readers, and logs are byte/order-unchanged.
5. **No fallback to MIDI, no implicit enable.** Shutdown only zeroes/closes; it
   never enables, swaps backend, or opens a port.
6. **Mutual exclusivity preserved.** No change to backend construction or port
   ownership; the controller and its swap path are untouched.
7. **Hard-kill caveat unchanged.** This covers graceful shutdown only;
   `kill -9` still cannot be made safe in software and still requires a physical
   kill method. Do not claim otherwise in docs.

---

## Part D — Tests

The roadmap explicitly states the existing
`test_shutdown_zeros_pack_before_slow_bridge_joins` (a static source-order
assertion, `tests/test_soundswitch_pack_startup.py:193-201`) is **not**
acceptance evidence for the runtime-swap case. Keep it (it still passes — Task 2
does not move `_cleanup_pack_outputs()` within `_shutdown`). Add a new
**behavioral** test that exercises `_shutdown_zero_pack_outputs` directly (the
pure seam), with no `main()` run and no real signals.

Add to `tests/test_soundswitch_pack_startup.py`:

```python
def test_shutdown_zeros_live_swapped_sender_not_just_startup(self):
    """After a runtime swap, shutdown must zero the LIVE sender; stopping the
    stale startup sender must be a harmless no-op."""
    calls = []

    class FakeSender:
        def __init__(self, name):
            self.name = name
        def stop(self):
            calls.append(f"{self.name}.stop")

    class FakeInput:
        def __init__(self, name):
            self.name = name
        def stop(self):
            calls.append(f"{self.name}.stop")

    class FakeRuntime:
        def __init__(self, sender, midi_input):
            self.frame_sender = sender
            self.midi_input = midi_input

    class FakeSM:
        def __init__(self, rt):
            self._rt = rt
        def get_pack_runtime(self):
            return self._rt

    startup_sender = FakeSender("startup_sender")
    startup_input = FakeInput("startup_input")
    live_sender = FakeSender("live_sender")        # installed by a runtime swap
    live_input = FakeInput("live_input")
    owners = {"sender": startup_sender, "midi_input": startup_input}
    sm = FakeSM(FakeRuntime(live_sender, live_input))

    bridge_main._shutdown_zero_pack_outputs(owners, sm)

    # The live swapped sender/input MUST be stopped (final zero frame + close).
    self.assertIn("live_sender.stop", calls)
    self.assertIn("live_input.stop", calls)
    # The stale startup sender is still stopped (harmless), proving no path is skipped.
    self.assertIn("startup_sender.stop", calls)
    # Owners dict is drained so a second cleanup is a no-op.
    self.assertIsNone(owners["sender"])
    self.assertIsNone(owners["midi_input"])

def test_shutdown_pre_sm_window_only_touches_startup_owners(self):
    """Before StateManager exists (sm=None), only the startup slots are stopped
    and no live-runtime read is attempted."""
    calls = []

    class FakeSender:
        def stop(self):
            calls.append("startup.stop")

    owners = {"sender": FakeSender(), "midi_input": None}
    bridge_main._shutdown_zero_pack_outputs(owners, None)  # must not raise
    self.assertEqual(calls, ["startup.stop"])

def test_shutdown_disabled_runtime_is_noop(self):
    """Default-off: a runtime with no sender/input must be a guarded no-op."""
    class FakeRuntime:
        frame_sender = None
        midi_input = None
    class FakeSM:
        def get_pack_runtime(self):
            return FakeRuntime()
    owners = {"sender": None, "midi_input": None}
    bridge_main._shutdown_zero_pack_outputs(owners, FakeSM())  # must not raise
```

(Use the existing `bridge_main` import alias already present in that test file.)

---

## Part E — Acceptance (definition of done)

- [ ] `_shutdown_zero_pack_outputs(...)` exists at module level in `__main__.py`
      and zeroes the live runtime sender/input AND the startup-owner slots, all
      guarded and idempotent.
- [ ] `_cleanup_pack_outputs()` delegates to it; `_sm_holder["sm"] = sm` is set
      immediately after `StateManager(...)` construction.
- [ ] No changes outside `__main__.py` and `tests/test_soundswitch_pack_startup.py`.
- [ ] New behavioral test proves the LIVE swapped sender/input are stopped and
      the stale startup sender stop is a harmless no-op; pre-sm and disabled-runtime
      no-op tests pass.
- [ ] Existing `test_shutdown_zeros_pack_before_slow_bridge_joins` still passes
      (source order unchanged).
- [ ] Gates green:
      ```bash
      cd /Users/bbui
      python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
        --project ~/Music/SoundSwitch/default.ssproj \
        --output-dir /tmp/rbss-rw1a-proof
      cd /Users/bbui/rb_ss_bridge_v2
      python3 -m unittest discover tests
      python3 tools/check_docs_metadata.py
      python3 tools/check_agent_contracts.py
      python3 tools/check_docs_drift.py
      python3 tools/check_docs_staleness.py --report
      git diff --check
      ```
      Also run the startup/shutdown module under Python 3.11 (CI is 3.11; local is
      3.14) since this touches `__main__` startup wiring:
      `python3.11 -m unittest tests.test_soundswitch_pack_startup`.
- [ ] No restart, device open, output enable, or hardware action performed.

---

## When you finish

- Commit per task (Task 1+2 together is acceptable since the helper is unused
  until wired; Task 3 separately). Suggested final message:
  `fix(soundswitch): zero live swapped pack sender on shutdown (RW-1A)`.
- Report back: the unittest summary line, the proof-gate `final_verdict` + counts,
  the four docs-check result lines, and confirm no files outside `__main__.py` +
  the test file changed. Provide an updated independent-review prompt in your
  final response (reviewer attacks: pre-sm vs post-sm window correctness, the
  no-swap double-stop idempotency claim, default-off neutrality, and that no
  blocking work entered the push loop).

---

## Adversarial self-review (done before handoff)

- **"What if no swap ever happens?"** Then `get_pack_runtime().frame_sender` IS
  the startup sender. The helper stops it once via the live branch (`_stopped`
  set), then the startup-owner branch `.stop()`s the same object → guarded no-op.
  One zero frame, correct. ✓
- **"What if a swap happened?"** Live branch stops the NEW sender (the one on the
  port). Startup branch `.stop()`s the OLD sender, which the swap already
  `zero_and_stop`'d but did not mark `_stopped`, so it re-zeros once — harmless. ✓
- **"What about the pre-`sm` early-shutdown window?"** `_sm_holder["sm"]` is
  `None` until after `StateManager(...)`; the helper skips the live branch and
  behaves exactly like today's `_cleanup_pack_outputs()`. ✓
- **"Could this run twice (signal then atexit)?"** Yes — and it is idempotent:
  the owners dict is drained (`pop`), `stop()` is `_stopped`-guarded, and a second
  `get_pack_runtime()` read returns the same already-stopped sender. ✓
- **"Does it touch the push loop?"** No. It runs only from the shutdown/command
  path. The 200 Hz loop and `StateManager._run()` are unchanged. ✓
- **"Could `get_pack_runtime()` raise or return a weird object?"** Wrapped in
  try/except and every attribute is `getattr(..., None)`-guarded. ✓
- **Known residual (out of scope):** `kill -9` still strands the last frame; that
  is unchanged and called out in Part C.7. RW-1A is graceful-shutdown only.
