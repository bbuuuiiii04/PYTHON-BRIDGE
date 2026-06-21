# Codex Implementation Spec — Bridge Log Visibility Phase 2 (LED dispatch + Govee realtime)

Status: planned

> **Implementing model: Gemini 3.1 Pro or Gemini 3.5 Flash (High).**
> Implement with **zero exploration and zero judgement calls.** Every edit is an exact `OLD → NEW`
> block. Make only these edits. If any `OLD` block does not match the file **character-for-character**,
> STOP and report the mismatch — do not guess, do not search for a "close" match.

Phase 1 (committed) added the diag tag map, the `--debug` logger coverage, the laser/LED/govee
**color patterns**, and the `[LX] gate-block` line. This Phase 2 adds the actual **LED dispatch**
and **Govee realtime** log lines that those color patterns were prepared for. No `__main__.py` edits
are needed — the color patterns already exist.

---

## OPERATING RULES (read first, obey exactly)

1. **Additive only.** Every change adds lines. You never delete or rewrite existing logic. If you
   are removing a line not shown in an `OLD` block, you are doing it wrong — stop.
2. **Do not explore the repo.** Everything you need is in this file.
3. **Do NOT touch these files** (they have a documented purity / no-I/O contract — logging them is a
   bug): `led_color_engine.py`, `led_look_director.py`, `beat_sync_engine.py`,
   `govee_frame_renderer.py`. Their state is surfaced later via a heartbeat that reads their
   `snapshot()`/`status()` — not by adding log calls inside them.
4. **Do not touch** `__main__.py` (color patterns already present), `state_manager.py`, any
   `laser_*` file, or any rb/SS file.
5. After each Task: run its verification commands and **paste the raw output**. If a command errors
   or a test fails, STOP and paste it. Do not attempt unlisted fixes.
6. **Live safety (read twice):** `govee_realtime_runner.py` runs a **30 fps actor thread**. The new
   log lines there go ONLY at lifecycle transitions and behind a 1/second throttle. You must NOT add
   any log call that runs on every frame, and you must NOT add any log call **inside** a
   `with self._lock:` block. Place log calls AFTER the `with` block closes.

---

## Part A — Context & root cause (verified against current code; read, do not implement)

- **[confirmed]** `bridge_fmt.py` (55 lines) has `log_once` but **no throttle / change-detection
  helper**. The only spam control today is once-per-session. We need "log on change" and "log at
  most 1/sec" primitives. `bridge_fmt.py` imports only stdlib (`os`, `threading`, `typing`) — adding
  these helpers keeps it dependency-free.
- **[confirmed]** `led_dispatch_coordinator.py` `LEDDispatchCoordinator.trigger()` is the single seam
  where a look is actually sent to hardware: the realtime branch ends at `return True`
  (`led_dispatch_coordinator.py:136`); the cloud branch sets `accepted` and returns it
  (`:141-157`). It already logs `[RGB] dwell-suppressed` / `[RGB] transport-cooldown` at DEBUG and
  has logger `led_dispatch_coordinator`. It has **no INFO line for "this look is now live"** — so
  there is no way to watch LED look changes against the rig. This is the highest-value gap.
- **[confirmed]** `govee_realtime_runner.py` is the 30 fps actor thread (`fps: int = 30`,
  `_loop()` at `:225`, `_tick_once()` at `:241`). It has logger `self._log =
  getLogger("govee_realtime_runner")` and exactly one log line, which uses an inconsistent tag:
  `self._log.info("[RT] reconcile-reactivate …")` (`:259`). The runner activates the transport at
  `:324-329`, deactivates on idle grace at `:401-420`, and force-deactivates on realtime→cloud
  handoff at `force_deactivate()` (`:129-155`). None of these transitions are logged, and there is
  no throughput/health summary. `[RT]` has **no color pattern**; `[RGB]` does (added in Phase 1).
- **[confirmed]** Importing `bridge_fmt` from these two modules is safe: `bridge_fmt` imports no
  bridge modules, so there is no import cycle.
- **[confirmed]** Tests import via `sys.path.insert(0, parents[2])` then `from rb_ss_bridge_v2.<mod>`
  (e.g. `tests/test_laser_executor.py:1-19`). There are existing `govee_realtime_runner` tests.

### Tag/color contract (already in `__main__._ColorFormatter._PATTERNS` from Phase 1 — do not edit)
- `[LED] look=…` → green (look applied/live). `[RGB] …` → cyan; `[RGB] error` → red.
- Use these exact tag prefixes so the existing patterns color the new lines. No `__main__` change.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Touch only: `bridge_fmt.py`, `led_dispatch_coordinator.py`, `govee_realtime_runner.py`, and the
  ONE new test file in Task 1. Nothing else.
- No behavior change beyond emitting log lines and adding two pure helper functions.

---

### Task 1 — `bridge_fmt.py`: add `log_throttled` + `log_changed` primitives

**Edit 1a — imports.** Find this block at the top of the file:

**OLD:**
```python
from __future__ import annotations

import os as _os
import threading
from typing import Optional
```

**NEW:**
```python
from __future__ import annotations

import os as _os
import threading
import time as _time
from typing import Any, Optional
```

**Edit 1b — append the primitives.** Find the current end of the file:

**OLD:**
```python
_ONCE = _OnceLog()


def log_once(key: str) -> bool:
    """Return True the first time *key* is seen this session; False thereafter."""
    return _ONCE.should_log(key)
```

**NEW:**
```python
_ONCE = _OnceLog()


def log_once(key: str) -> bool:
    """Return True the first time *key* is seen this session; False thereafter."""
    return _ONCE.should_log(key)


class _RateState:
    """Process-scoped throttle + change-detection state for log gating.

    Thread-safe; every method holds the lock only for an O(1) dict access, so it
    is safe to call from high-frequency threads (e.g. the 30 fps Govee runner).
    """

    _MISSING = object()

    def __init__(self) -> None:
        self._last_emit: dict[str, float] = {}
        self._last_value: dict[str, Any] = {}
        self._lock = threading.Lock()

    def throttled(self, key: str, min_interval_s: float, now: Optional[float] = None) -> bool:
        ts = _time.monotonic() if now is None else float(now)
        with self._lock:
            last = self._last_emit.get(key)
            if last is not None and (ts - last) < float(min_interval_s):
                return False
            self._last_emit[key] = ts
            return True

    def changed(self, key: str, value: Any) -> bool:
        with self._lock:
            prev = self._last_value.get(key, self._MISSING)
            if prev is not self._MISSING and prev == value:
                return False
            self._last_value[key] = value
            return True


_RATE = _RateState()


def log_throttled(key: str, min_interval_s: float, now: Optional[float] = None) -> bool:
    """Return True at most once per *min_interval_s* for *key* (first call True).

    Pass *now* (monotonic seconds) from a thread that already has a timestamp to
    avoid an extra clock read.
    """
    return _RATE.throttled(key, min_interval_s, now)


def log_changed(key: str, value: Any) -> bool:
    """Return True only when *value* differs from the last value seen for *key*.

    First call for a key returns True. Use to log state transitions once instead
    of every tick.
    """
    return _RATE.changed(key, value)
```

**Edit 1c — create NEW FILE `tests/test_bridge_fmt_rate.py`** with exactly this content:

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.bridge_fmt import log_changed, log_throttled  # noqa: E402


class LogChangedTest(unittest.TestCase):
    def test_first_true_then_false_until_change(self) -> None:
        k = "t_changed_1"
        self.assertTrue(log_changed(k, "a"))
        self.assertFalse(log_changed(k, "a"))
        self.assertTrue(log_changed(k, "b"))
        self.assertFalse(log_changed(k, "b"))

    def test_independent_keys(self) -> None:
        self.assertTrue(log_changed("t_changed_2", 1))
        self.assertTrue(log_changed("t_changed_3", 1))
        self.assertFalse(log_changed("t_changed_2", 1))


class LogThrottledTest(unittest.TestCase):
    def test_one_per_interval_injected_clock(self) -> None:
        k = "t_throttle_1"
        self.assertTrue(log_throttled(k, 1.0, now=100.0))
        self.assertFalse(log_throttled(k, 1.0, now=100.5))
        self.assertTrue(log_throttled(k, 1.0, now=101.0))
        self.assertFalse(log_throttled(k, 1.0, now=101.2))

    def test_independent_keys(self) -> None:
        self.assertTrue(log_throttled("t_throttle_2", 5.0, now=0.0))
        self.assertTrue(log_throttled("t_throttle_3", 5.0, now=0.0))
        self.assertFalse(log_throttled("t_throttle_2", 5.0, now=1.0))


if __name__ == "__main__":
    unittest.main()
```

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile bridge_fmt.py && echo "OK py_compile"
python3 -m unittest tests.test_bridge_fmt_rate -v
```
All four tests must report `ok`.

---

### Task 2 — `led_dispatch_coordinator.py`: log `[LED] look=` when a look goes live

**Edit 2a — import.** Find this block (top of file):

**OLD:**
```python
from .govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
from .led_models import LEDConfig, LEDLookDecision

log = logging.getLogger("led_dispatch_coordinator")
```

**NEW:**
```python
from .govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
from .led_models import LEDConfig, LEDLookDecision
from .bridge_fmt import log_changed

log = logging.getLogger("led_dispatch_coordinator")
```

**Edit 2b — realtime branch.** Find this block (it ends with `return True`, unique to the realtime
branch):

**OLD:**
```python
            self._runner.set_desired(self._spec_from_decision(decision))
            self._runner.fire_trigger()
            self._realtime_trigger_count += 1
            self._last_dispatch_mono = now
            self._last_dispatch_role = role
            self._last_transport = backend
            self._last_transport_mono = now
            return True
```

**NEW:**
```python
            self._runner.set_desired(self._spec_from_decision(decision))
            self._runner.fire_trigger()
            self._realtime_trigger_count += 1
            self._last_dispatch_mono = now
            self._last_dispatch_role = role
            self._last_transport = backend
            self._last_transport_mono = now
            if log_changed("led_live", (getattr(decision, "look", ""), "realtime", role)):
                log.info(
                    "[LED] look=%s role=%s via=realtime",
                    getattr(decision, "look", ""), role,
                )
            return True
```

**Edit 2c — cloud branch.** Find this block (the `# WI-6:` comment makes it unique to the cloud
branch):

**OLD:**
```python
            self._last_dispatch_mono = now
            self._last_dispatch_role = role
            self._last_transport = backend
            self._last_transport_mono = now
            # WI-6: notify runner that a cloud DIY was dispatched so it can
```

**NEW:**
```python
            self._last_dispatch_mono = now
            self._last_dispatch_role = role
            self._last_transport = backend
            self._last_transport_mono = now
            if log_changed("led_live", (getattr(decision, "look", ""), "cloud", role)):
                log.info(
                    "[LED] look=%s role=%s via=cloud",
                    getattr(decision, "look", ""), role,
                )
            # WI-6: notify runner that a cloud DIY was dispatched so it can
```

> Both branches share the key `"led_live"` with the transport in the value tuple, so a steady look
> stays quiet but a realtime↔cloud switch (or look/role change) re-logs once. This is intentional.

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile led_dispatch_coordinator.py && echo "OK py_compile"
grep -nE '\[LED\] look=%s role=%s via=' led_dispatch_coordinator.py
python3 -m unittest discover -s tests -p "test_led*" 2>&1 | tail -4
```

---

### Task 3 — `govee_realtime_runner.py`: `[RGB]` lifecycle + 1/sec summary (LIVE-SAFETY CARE)

**Edit 3a — import.** Find this line:

**OLD:**
```python
from .led_models import BeatAnchor
```

**NEW:**
```python
from .led_models import BeatAnchor
from .bridge_fmt import log_throttled
```

**Edit 3b — standardize the existing tag** from `[RT]` to `[RGB]`. Find:

**OLD:**
```python
            self._log.info("[RT] reconcile-reactivate now=%.3f", now)
```

**NEW:**
```python
            self._log.info("[RGB] reconcile-reactivate now=%.3f", now)
```

**Edit 3c — log activation.** Find this block in `_tick_once`:

**OLD:**
```python
        if not self._active:
            self._transport.activate()
            self._transport.set_brightness(100)
            self._last_activate_mono = now
            with self._lock:
                self._active = True
```

**NEW:**
```python
        if not self._active:
            self._transport.activate()
            self._transport.set_brightness(100)
            self._last_activate_mono = now
            with self._lock:
                self._active = True
            self._log.info("[RGB] activate effect=%s", spec.effect_name)
```

**Edit 3d — 1/sec throughput summary.** Find this exact block (the main send path, 8-space indent,
with NO `self._idle_since = None` and NO `return` — that distinguishes it from the paused-comet
branch):

**OLD:**
```python
        sent_ok = self._transport.send_frame(frame)
        self._last_frame = frame
        with self._lock:
            self._last_error = "" if sent_ok else "transport_send_failed"
            self._frame_index += 1
        self._publish_engine_status(cleared=False)
```

**NEW:**
```python
        sent_ok = self._transport.send_frame(frame)
        self._last_frame = frame
        with self._lock:
            self._last_error = "" if sent_ok else "transport_send_failed"
            self._frame_index += 1
        self._publish_engine_status(cleared=False)
        if log_throttled("rgb_rt_summary", 1.0, now):
            self._log.info(
                "[RGB] summary effect=%s frames=%d err=%s",
                spec.effect_name, self._frame_index, self._last_error or "none",
            )
```

**Edit 3e — log idle deactivation.** Find this block in `_idle_tick`:

**OLD:**
```python
            self._engine.reset()
            self._publish_engine_status(cleared=True)
            return
        if self._last_frame is not None:
            self._transport.send_frame(self._last_frame)
```

**NEW:**
```python
            self._engine.reset()
            self._publish_engine_status(cleared=True)
            self._log.info("[RGB] deactivate reason=idle_grace")
            return
        if self._last_frame is not None:
            self._transport.send_frame(self._last_frame)
```

**Edit 3f — log realtime→cloud handoff.** Find this block in `force_deactivate`:

**OLD:**
```python
        if self._active:
            self._transport.blackout()
            self._transport.deactivate()
        with self._lock:
            self._active = False
            self._active_signature = None
            self._color_signature = None
            self._color_applied_abs_beat = None
            self._idle_since = None
            self._pending_manual = 0
            self._engine_status = {"sync_mode": "", "beat_division": 0.0, "instance_count": 0, "spawn_count": 0}
            self._desired_spec = None
```

**NEW:**
```python
        if self._active:
            self._transport.blackout()
            self._transport.deactivate()
            self._log.info("[RGB] deactivate reason=handoff_to_cloud")
        with self._lock:
            self._active = False
            self._active_signature = None
            self._color_signature = None
            self._color_applied_abs_beat = None
            self._idle_since = None
            self._pending_manual = 0
            self._engine_status = {"sync_mode": "", "beat_division": 0.0, "instance_count": 0, "spawn_count": 0}
            self._desired_spec = None
```

> Every new line here is OUTSIDE a `with self._lock:` block and fires only on a transition (activate
> / idle-deactivate / handoff) or behind the 1/sec throttle (summary). None run per-frame.

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile govee_realtime_runner.py && echo "OK py_compile"
grep -nE '\[RGB\] (activate|deactivate|summary|reconcile)' govee_realtime_runner.py
grep -nc '\[RT\]' govee_realtime_runner.py   # must print 0 (tag standardized)
python3 -m unittest discover -s tests -p "test_govee*" 2>&1 | tail -4
```

---

## Part C — Invariants that MUST still hold (live safety)

- **30 fps runner thread is not slowed or blocked.** New log calls run only on state transitions or
  behind `log_throttled(..., 1.0)`; none run every frame. The existing `[RT] reconcile-reactivate`
  line already logged INFO on this thread, so this matches established behavior. No log call is added
  inside a `with self._lock:` block.
- **No frame-path semantics change.** `send_frame`, `activate`, `deactivate`, `blackout`,
  signatures, idle grace, emergency teardown, and ownership handoff are unchanged — only INFO lines
  are added next to the existing transitions.
- **`log_throttled` / `log_changed` are O(1) and thread-safe** (a single short-held lock around a
  dict access). They add no blocking I/O to any thread.
- **Pure/no-I/O modules untouched.** `led_color_engine.py` (documented "no side-effects, no I/O")
  and `led_look_director.py` (`tick()` "no I/O") are NOT modified. Their state is surfaced by the
  Phase-3 heartbeat instead.
- **200 Hz StateManager push loop is untouched** (no file it owns is edited).

## Part D — Tests

- Task 1 adds `tests/test_bridge_fmt_rate.py` — a pure, no-I/O, injected-clock test seam for both
  primitives (4 tests).
- Tasks 2–3 are observability-only; correctness is verified by `py_compile`, grep presence, and the
  **existing** `test_led*` / `test_govee*` suites passing unchanged (regression guard).
- Final regression gate (run after all tasks):
  ```bash
  cd /Users/bbui/rb_ss_bridge_v2
  python3 -m unittest discover tests 2>&1 | tail -5
  ```

## Part E — Acceptance (definition of done)

- [ ] All `OLD → NEW` edits applied verbatim; no other lines changed in those files.
- [ ] `tests/test_bridge_fmt_rate.py` created; 4/4 pass.
- [ ] `python3 -m py_compile bridge_fmt.py led_dispatch_coordinator.py govee_realtime_runner.py`
      prints nothing.
- [ ] `grep -nc '\[RT\]' govee_realtime_runner.py` prints `0`.
- [ ] `python3 -m unittest discover tests` shows no new failures vs. before this change.
- [ ] `led_color_engine.py`, `led_look_director.py`, `beat_sync_engine.py`,
      `govee_frame_renderer.py`, `__main__.py`, `state_manager.py`, and all `laser_*` files are
      UNCHANGED.
- [ ] All verification command outputs pasted back.

## When you finish

Commit after each task with these exact messages:
1. `Add log_throttled + log_changed spam-control primitives`
2. `Log [LED] look-live on realtime + cloud dispatch`
3. `Add [RGB] lifecycle + 1/sec summary to Govee realtime runner`

If a pre-commit hook blocks a commit, **paste its output and stop** — do not use `--no-verify` and
do not edit docs/contracts (Claude handles those). Report: which tasks landed, all verification
output, and anything that did not match an `OLD` block exactly.

---

## Deferred to Phase 3 (implemented separately in runtime status)

Phase 3 landed as a status-writer heartbeat in `runtime_status.StatusWriter`: status JSON now
contains `heartbeat`, and the status thread logs one throttled `[BEAT]` line. It reads
`StateManager.snapshot()`, laser status, LED status, and `LedColorEngine.snapshot()` provider
surfaces; it does not add work to the 200 Hz push loop.

- **`[COLOR]` palette visibility** and **current-look summary** must come from a heartbeat that
  reads `LedColorEngine.snapshot()` and `LEDLookDirector.status()` — NOT from log calls inside those
  modules (purity / no-I/O contracts).
- **`[BEAT]` heartbeat line** (deck · master · BPM · phrase · laser scene · LED look · palette · RGB
  health) — a single throttled status line assembled in the runtime status/push path. Needs its own
  spec because it reads cross-subsystem `status()`/`snapshot()` surfaces and touches the status
  writer.
