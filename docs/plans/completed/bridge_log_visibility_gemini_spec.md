# Codex Implementation Spec — Bridge Log Visibility (Gemini-targeted, bridge-core slice)

Status: planned

> **Implementing model: Gemini 3.1 Pro or Gemini 3.5 Flash (High).**
> This spec is written to be implemented with **zero exploration and zero judgement calls.**
> Every edit is given as an exact `OLD → NEW` block. Make only these edits. Do not refactor,
> rename, reorder, "improve", or touch any file not named in a Task. If any `OLD` block does not
> match the file **character-for-character**, STOP and report the mismatch — do not guess.

---

## OPERATING RULES (read first, obey exactly)

1. **Additive only.** Every change adds lines. You are NOT deleting or rewriting logic. If you find
   yourself deleting a line that isn't shown in an `OLD` block, you are doing it wrong — stop.
2. **Do not explore the repo.** Everything you need is in this file. Do not open or edit any
   `led_*.py`, `govee_*.py`, `beat_sync_engine.py`, `laser_director.py`, `state_manager.py`,
   `__main__.py` beyond what a Task explicitly names.
3. **Forward references are intentional.** Tasks 1–2 register logger names like
   `led_look_director`, `led_color_engine`, `govee_runtime_sender`. **Those modules do not log yet
   — that is expected and correct.** Do NOT add logging to them. Do NOT "make them work". Setting a
   DEBUG level on a logger that nothing uses yet is a harmless no-op and is the whole point.
4. **There are TWO different `enable_debug` functions** (Task 1 in `logging_manager.py`, Task 2 in
   `diagnostics.py`). They are NOT the same. Edit BOTH, each exactly as written. Do not assume one.
5. **First-match-wins ordering matters** in Task 3. Insert the block at the exact anchor shown and
   do NOT reorder any existing pattern entries.
6. After each Task: run the verification commands in that Task and **paste the raw output**. If a
   command errors or a test fails, STOP and paste the failure. Do not attempt unlisted fixes.
7. Out of scope (do NOT do, even if tempted): the LED/Govee instrumentation, the `[BEAT]` heartbeat
   line, any new event log lines, docs, change-contracts, YAML. Those are handled separately.

---

## Part A — Context & root cause (verified; read, do not implement)

Goal of the larger effort: make the bridge's laser + LED activity watchable in real time. This spec
is **only the bridge-core, additive slice** that is safe to implement mechanically. The LED
instrumentation and heartbeat are implemented separately and are out of scope here.

- **[confirmed]** Color is applied by `_ColorFormatter._PATTERNS` in `__main__.py:108-215` — a
  first-match-wins list of `(lowercased-substring, ansi-color)` tuples, matched in
  `__main__.py:233-241`. ANSI color constants are defined at `__main__.py:86-97`
  (`_RESET _GREY _WHITE _YELLOW _RED _BRED _BGREEN _BCYAN _BMAGENTA _BPINK _ORANGE _LIME`).
- **[confirmed]** The laser executor's `[LX]` lines (`[LX] fired`, `[LX] mask_on`, etc.) have **no
  color pattern** — they fall through to the default level color. The LED tags `[LED] [COLOR] [RGB]`
  have **no pattern at all** (the LED pipeline is currently silent — verified: `led_look_director.py`,
  `led_color_engine.py`, `beat_sync_engine.py`, `govee_runtime_sender.py`, `govee_frame_renderer.py`,
  `govee_realtime_transport.py`, `govee_owner_state.py` emit 0 log calls).
- **[confirmed]** `LoggingManager._DIAG_MODULES` (`logging_manager.py:246-255`) maps the
  `BRIDGE_LOG_DIAG` / `LoggingManager.enable_debug()` / `disable_debug()` tag shorthands to module
  logger names. It contains **no laser/LED/govee** entries, so those subsystems cannot be targeted
  by `BRIDGE_LOG_DIAG=...` or the control-file `"debug": true` path.
- **[confirmed]** The `--debug` / `BRIDGE_DEBUG=1` path calls a **different** function —
  `diagnostics.enable_debug()` (`diagnostics.py:168-174`) — whose hardcoded tuple also omits all
  laser/LED/govee loggers. Call site: `__main__.py:678-679`.
- **[confirmed]** `laser_executor._record_gate()` (`laser_executor.py:463-466`) increments
  `_gated_count` and stores `_last_error` but logs **nothing**, so "why didn't the laser fire" is
  invisible even at DEBUG. Existing executor lines already log at DEBUG on the same decision path
  (e.g. `[LX] blackout skipped` at `laser_executor.py:130,138`), so adding one DEBUG line here is
  consistent and live-safe.
- **[confirmed]** Tests import the package via `sys.path.insert(0, parents[2])` then
  `from rb_ss_bridge_v2.<mod> import ...` (e.g. `tests/test_laser_executor.py:1-19`).

### Canonical tag → color contract (authoritative; Task 3 + future LED work both obey this)

| Tag | Owner module | Color intent |
|---|---|---|
| `[LASER]` | `laser_director` | scene/policy → pink; `personality` applied → green; `buildup-gate` → cyan |
| `[LX]` | `laser_executor` | `fired`/`mask_on`/`mask_off`/`blackout_on sent` → green; `blackout_on rejected` → red; `gate-block`/`blackout skipped`/`blackout arming` (debug) → grey |
| `[LED]` | `led_look_director` | `look` → green; `override` → yellow; `blackout` → red |
| `[COLOR]` | `led_color_engine` | `palette` applied → green; `queue` pending → yellow |
| `[RGB]` | `govee_runtime_sender`/transport | `connected` → green; `error`/`disconnect` → red; `drop`/`retry` → orange; `summary` → cyan |

(The `[LED] [COLOR] [RGB]` patterns are added now even though those lines do not exist yet. They are
harmless until the separate LED instrumentation lands, at which point output is already colored.)

---

## Part B — Tasks (implement exactly, in order)

### Absolute rules
- Touch only: `logging_manager.py`, `diagnostics.py`, `__main__.py`, `laser_executor.py`, and the
  ONE new test file in Task 5. Nothing else.
- **No behavior change** to laser policy, laser execution, the StateManager push loop, or any
  runtime data flow. The only runtime effect permitted is: (a) a new DEBUG log line, and (b) logger
  level configuration.

---

### Task 1 — `logging_manager.py`: register laser/LED/govee diag tags

Find this exact block (around line 246) and replace it.

**OLD:**
```python
_DIAG_MODULES: dict[str, str] = {
    "sm":   "state_manager",
    "mem":  "rb_memory",
    "fres": "filepath_resolver",
    "lbpm": "live_bpm",
    "os2l": "osl_output",
    "mtc":  "mtc_reader",
    "rsr":  "rb_state_reader",
    "main": "bridge",
}
```

**NEW:**
```python
_DIAG_MODULES: dict[str, str] = {
    "sm":   "state_manager",
    "mem":  "rb_memory",
    "fres": "filepath_resolver",
    "lbpm": "live_bpm",
    "os2l": "osl_output",
    "mtc":  "mtc_reader",
    "rsr":  "rb_state_reader",
    "main": "bridge",
    # Laser
    "laser": "laser_director",
    "lx":    "laser_executor",
    "lcfg":  "laser_config",
    # LED / Govee (forward references: some of these loggers do not emit yet)
    "led":   "led_look_director",
    "color": "led_color_engine",
    "bsync": "beat_sync_engine",
    "disp":  "led_dispatch_coordinator",
    "scene": "govee_scene_adapter",
    "rgb":   "govee_runtime_sender",
    "rtrun": "govee_realtime_runner",
    "rtx":   "govee_realtime_transport",
    "frame": "govee_frame_renderer",
    "owner": "govee_owner_state",
}
```

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile logging_manager.py && echo "OK py_compile"
grep -nE '"laser":|"led":|"color":|"rgb":|"owner":' logging_manager.py
```

---

### Task 2 — `diagnostics.py`: extend the `--debug` logger tuple

Find this exact function (around line 168) and replace it.

**OLD:**
```python
def enable_debug() -> None:
    """Set all bridge loggers to DEBUG level."""
    for name in ("rb_memory", "filepath_resolver",
                 "scripted_tracks", "osl_output", "state_manager",
                 "diagnostics", "bridge", "logging_manager"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    log.info("Verbose debug mode enabled")
```

**NEW:**
```python
def enable_debug() -> None:
    """Set all bridge loggers to DEBUG level."""
    for name in ("rb_memory", "filepath_resolver",
                 "scripted_tracks", "osl_output", "state_manager",
                 "diagnostics", "bridge", "logging_manager",
                 # Laser
                 "laser_director", "laser_executor", "laser_config",
                 # LED / Govee
                 "led_look_director", "led_color_engine", "beat_sync_engine",
                 "led_dispatch_coordinator", "govee_scene_adapter",
                 "govee_runtime_sender", "govee_realtime_runner",
                 "govee_realtime_transport", "govee_frame_renderer",
                 "govee_owner_state"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    log.info("Verbose debug mode enabled")
```

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile diagnostics.py && echo "OK py_compile"
grep -nE 'laser_director|led_color_engine|govee_owner_state' diagnostics.py
```

---

### Task 3 — `__main__.py`: add laser/LED/govee color patterns

Insert a block into `_ColorFormatter._PATTERNS`. The anchor is the existing
`("[sm] energy-suggest", _LIME),` line followed by the blank line and the `# Red:` comment.
**Do not reorder or modify any existing pattern. Insert exactly between them.**

**OLD:**
```python
        ("[sm] energy-suggest",     _LIME),

        # Red: requires attention / playback stopped.
```

**NEW:**
```python
        ("[sm] energy-suggest",     _LIME),

        # ── Laser / LED / Govee subsystem tags (bridge log visibility) ──────────
        # First-match-wins: each specific state line MUST stay above its generic
        # tag fallback. Do not reorder.
        ("[laser] personality",       _BGREEN),
        ("[laser] buildup-gate",      _BCYAN),
        ("[laser]",                   _BPINK),
        ("[lx] fired",                _BGREEN),
        ("[lx] same-scene-refire",    _BGREEN),
        ("[lx] blackout_on sent",     _BGREEN),
        ("[lx] mask_on",              _BGREEN),
        ("[lx] mask_off",             _BGREEN),
        ("[lx] blackout_on rejected", _BRED),
        ("[lx] gate-block",           _GREY),
        ("[lx] blackout skipped",     _GREY),
        ("[lx] blackout arming",      _GREY),
        ("[lx]",                      _BCYAN),
        ("[led] blackout",            _BRED),
        ("[led] override",            _YELLOW),
        ("[led] look",                _BGREEN),
        ("[led]",                     _BCYAN),
        ("[color] queue",             _YELLOW),
        ("[color] palette",           _BGREEN),
        ("[color]",                   _BCYAN),
        ("[rgb] connected",           _BGREEN),
        ("[rgb] error",               _BRED),
        ("[rgb] disconnect",          _BRED),
        ("[rgb] drop",                _ORANGE),
        ("[rgb] retry",               _ORANGE),
        ("[rgb] summary",             _BCYAN),
        ("[rgb]",                     _BCYAN),

        # Red: requires attention / playback stopped.
```

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile __main__.py && echo "OK py_compile"
grep -nE '\("\[lx\] fired"|\("\[rgb\]"|\("\[color\] palette"' __main__.py
```

---

### Task 4 — `laser_executor.py`: surface gate-blocks at DEBUG

Find this exact method (around line 463) and replace it. You are adding ONE line at the end.

**OLD:**
```python
    def _record_gate(self, reason: str) -> None:
        with self._lock:
            self._gated_count += 1
            self._last_error = reason
```

**NEW:**
```python
    def _record_gate(self, reason: str) -> None:
        with self._lock:
            self._gated_count += 1
            self._last_error = reason
        log.debug("[LX] gate-block  reason=%s", reason)
```

> The new line is **outside** the `with self._lock:` block (do not indent it under the `with`). It
> is DEBUG-level, so it is silent unless diagnostics are enabled. Do not change anything else in
> this file.

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m py_compile laser_executor.py && echo "OK py_compile"
grep -n 'gate-block' laser_executor.py
```

---

### Task 5 — NEW FILE `tests/test_logging_diag_coverage.py`

Create this file with **exactly** this content (it is self-contained and fixes its own import path):

```python
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.logging_manager import LoggingManager, _DIAG_MODULES  # noqa: E402
from rb_ss_bridge_v2 import diagnostics  # noqa: E402

# Logger names every laser/LED/govee diagnostic path must be able to reach.
_REQUIRED_SUBSYSTEM_LOGGERS = (
    "laser_director", "laser_executor",
    "led_look_director", "led_color_engine", "beat_sync_engine",
    "govee_runtime_sender", "govee_realtime_runner",
    "govee_realtime_transport", "govee_frame_renderer", "govee_owner_state",
    "led_dispatch_coordinator", "govee_scene_adapter",
)


class DiagModuleCoverageTest(unittest.TestCase):
    def test_diag_modules_cover_laser_led_govee(self) -> None:
        mapped = set(_DIAG_MODULES.values())
        for name in _REQUIRED_SUBSYSTEM_LOGGERS:
            self.assertIn(name, mapped, f"{name} missing from _DIAG_MODULES")

    def test_manager_enable_debug_sets_named_subsystems(self) -> None:
        mgr = LoggingManager()
        for name in ("laser_director", "led_color_engine", "govee_runtime_sender"):
            logging.getLogger(name).setLevel(logging.INFO)
        mgr.enable_debug("laser", "color", "rgb")
        self.assertEqual(logging.getLogger("laser_director").level, logging.DEBUG)
        self.assertEqual(logging.getLogger("led_color_engine").level, logging.DEBUG)
        self.assertEqual(logging.getLogger("govee_runtime_sender").level, logging.DEBUG)

    def test_diagnostics_enable_debug_covers_subsystems(self) -> None:
        for name in _REQUIRED_SUBSYSTEM_LOGGERS:
            logging.getLogger(name).setLevel(logging.INFO)
        diagnostics.enable_debug()
        for name in _REQUIRED_SUBSYSTEM_LOGGERS:
            self.assertEqual(
                logging.getLogger(name).level, logging.DEBUG,
                f"{name} not set to DEBUG by diagnostics.enable_debug()",
            )


if __name__ == "__main__":
    unittest.main()
```

**Verify (paste output):**
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m unittest tests.test_logging_diag_coverage -v
```
All three tests must report `ok`.

---

## Part C — Invariants that MUST still hold (live safety)

- **No laser policy / execution behavior change.** Tasks 1–4 add only logger-level config, one
  DEBUG log line, and display color. No gate, scene-selection, rotation, MIDI, or timing logic is
  altered. `laser_executor.on_decision` / `_select_scene` / `_record_gate` semantics are unchanged
  except for the trailing DEBUG line.
- **Push loop stays non-blocking.** The Task 4 line is `log.debug(...)` to the existing stream
  handler — identical mechanism to the `[LX] blackout skipped` DEBUG lines already on this path. No
  network, socket, MIDI, filesystem, subprocess, or lock-held I/O is added (the log call is outside
  `self._lock`).
- **Default output is unchanged.** All new color patterns key off tag substrings; the Task 4 line
  is DEBUG (suppressed at the default INFO level). With no diagnostics enabled, runtime output is
  byte-for-byte the same as before except for color of already-emitted `[LX]`/`[LASER]` lines.
- **One-process invariant untouched.** No threads, processes, or sockets are created or changed.

## Part D — Tests

- Task 5 adds `tests/test_logging_diag_coverage.py` — a pure, no-I/O, no-subprocess test seam that
  asserts (a) `_DIAG_MODULES` covers every laser/LED/govee logger, (b) `LoggingManager.enable_debug`
  tag shorthands set the right loggers to DEBUG, (c) `diagnostics.enable_debug()` (the `--debug`
  path) covers the same loggers.
- The color-pattern change (Task 3) is display-only and is verified by `grep` presence +
  `py_compile`, not a unit test (importing `__main__` to test formatting triggers logging-config
  side effects; not worth the risk for a static pattern list).
- Regression guard — confirm the laser executor suite still passes:
  ```bash
  cd /Users/bbui/rb_ss_bridge_v2
  python3 -m unittest tests.test_laser_executor 2>&1 | tail -5
  ```

## Part E — Acceptance (definition of done)

- [ ] All 4 `OLD → NEW` edits applied verbatim; no other lines changed in those files.
- [ ] `tests/test_logging_diag_coverage.py` created verbatim; all 3 tests pass.
- [ ] `python3 -m py_compile logging_manager.py diagnostics.py __main__.py laser_executor.py`
      prints nothing (no errors).
- [ ] `python3 -m unittest tests.test_laser_executor` still passes (no regression).
- [ ] No `led_*.py`, `govee_*.py`, `beat_sync_engine.py`, `laser_director.py`, `state_manager.py`
      file was modified.
- [ ] All verification command outputs pasted back.

## When you finish

Commit the changes in this order with these exact messages (commit after the tasks are verified):

1. Tasks 1+2 together:
   `Wire laser/LED/govee loggers into diag + --debug paths`
2. Task 3:
   `Add laser/LED/govee color patterns to bridge log formatter`
3. Tasks 4+5 together:
   `Surface laser executor gate-blocks at DEBUG + diag coverage test`

If a pre-commit hook blocks the commit, **paste its full output and stop** — do not use
`--no-verify` and do not edit docs/contracts to satisfy it (Claude handles docs/contracts
separately). Then report: which tasks landed, all verification output, and anything that did not
match the `OLD` blocks exactly.
