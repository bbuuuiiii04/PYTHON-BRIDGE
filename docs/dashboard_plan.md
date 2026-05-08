# Implementation Plan: Bridge Operator Dashboard + Validation/Replay System

## Context

rb_ss_bridge_v2 has no observability beyond `tail -f /tmp/bridge.log`. The bridge_menubar shows only on/off state. This plan adds a live status dashboard, OS2L packet mirror, validation runner, scripted show inspector, and rehearsal capture — surfaced through an extended rumps menu bar. The bridge process owns all diagnostic state; the menu bar is a read-only consumer of a status snapshot file.

---

## Gap Resolutions

### Gap 1 — Command bus coexists with `os2l_injector.py`

`os2l_injector.py` watches `/tmp/rbss_os2l_inject.jsonl` for raw packet injection (manual testing, unchanged). The new command bus watches `/tmp/rb_ss_bridge_v2_commands.jsonl` for higher-level control commands. These serve different purposes and different callers — no coordination needed. For send-capable commands (live replay), the command bus calls `conn.send()` directly, same as the injector does. The arm gate lives in the command bus only; the injector remains ungated (manual-test tool, not menu-bar accessible).

### Gap 2 — StateManager snapshot API

Add `snapshot() -> dict` to `StateManager`, called under the existing `self._lock`. Returns exactly these fields (no more):

```python
{
    "active_deck": int,           # _out.active_deck
    "lighting_mode": str,         # _out.lighting_mode  ("idle"/"scripted"/"autoloop")
    "autoloop_arm_pending": bool, # _out.autoloop_arm_pending
    "drop_cut_armed": bool,       # _out.drop_cut_armed
    "was_playing": bool,          # _out.was_playing
    "deck": {
        1: {
            "playing": bool,         # _decks[1].playing
            "filepath": str,         # _decks[1].meta.filepath
            "scripted_id": int,      # _decks[1].scripted_id
            "elapsed_ms": int,       # _decks[1].elapsed_ms
        },
        2: { ... }                   # same
    }
}
```

No OutputState fields beyond these six are exposed. The snapshot writer enriches the dict with data from other components (BPM, position, connection state) without touching StateManager internals.

### Gap 3 — Snapshot write cadence

`runtime_status.py` starts a daemon thread that loops at 500 ms. Each tick:
1. Calls `sm.snapshot()` (acquires `self._lock` internally, holds it briefly)
2. Calls `live_bpm.get_status(d)` for each deck (thread-safe, already locked internally)
3. Calls `pos_cache.get(d).is_stale()` for each deck (thread-safe)
4. Reads `conn._connected`, `conn._send_q.qsize()`, `conn._drop_count` (plain attrs, GIL-protected for reads)
5. Serializes full dict to a temp path, `os.replace()` to `/tmp/rb_ss_bridge_v2_status.json`

The 200 Hz push loop is never touched. The snapshot lock hold is < 1 ms (dict copy, no I/O).

### Gap 4 — Stay with rumps, no AppKit rewrite

Use dynamic `rumps.MenuItem` titles updated in the existing `@rumps.timer(2)` callback. No PyObjC threading work needed; rumps schedules timer callbacks on the AppKit main run loop. The menu bar reads `/tmp/rb_ss_bridge_v2_status.json` in the timer callback (absent or stale file = show "bridge: off").

Menu layout (all rows are `rumps.MenuItem` with `.title` updated each tick):

```
● Bridge: on | SS: connected
  Deck 1: filename.wav | BPM: 128.4
  Deck 2: --
  Mode: autoloop | Drop in: 4b
  Valid: 8/8  Mirror: off  Cap: idle
  ─────────────────────
  Bridge: On (click to stop)        ← existing toggle
  ─────────────────────
  ☐ Arm Live Actions  (30s timeout)
  Run Validation
  Toggle Mirror
  Start Capture
```

### Gap 5 — Validation runs in-process

`validation_runner.py` lives inside the bridge process. It is triggered by a command `{"cmd": "run_validation"}` written to the command file. The runner accesses live objects directly (`conn._connected`, `pos_cache.get(d).is_stale()`, `live_bpm.get_status(d)`, `scripted_tracks.SCRIPTED_TRACKS`, `sm.snapshot()`). Results are written into the next status snapshot under `"validation"` key. The menu bar reads them from the snapshot. The command file reader runs validation in a daemon thread (non-blocking to the push loop).

Checks (all run each time):
1. Bridge singleton — `pgrep` count == 1
2. SoundSwitch connection — `conn._connected`
3. Rekordbox process alive — `pgrep -f rekordbox`
4. Memory freshness — `pos_cache.get(1).is_stale()` and `pos_cache.get(2).is_stale()`
5. Live BPM deck 1 — `live_bpm.get_status(1).valid`
6. Live BPM deck 2 — `live_bpm.get_status(2).valid` (warn not fail if deck 2 idle)
7. Scripted registry — `len(scripted_tracks.SCRIPTED_TRACKS) >= 3` (hardcoded minimum)
8. OS2L queue health — `conn._send_q.qsize() < conn._send_q.maxsize * 0.8`

### Gap 6 — Arm flag mechanics

Arm is embedded in the command stream, not a separate file. To arm:
```json
{"cmd": "arm_live", "expires_at": 1234567890.123}
```
Menu bar sets `expires_at = time.time() + 30`. Bridge stores `_arm_expires: float` in the command reader. For every send-capable command, the bridge checks `time.time() < _arm_expires`; if expired, refuses and logs `[CMD] live send refused — arm expired`. Bridge restart: `_arm_expires` initializes to 0 (disarmed); no file state carries over. Menu bar: timer callback compares `time.time()` against its own `_arm_until`; unchecks the menu item and stops showing armed state when expired. Re-arm requires another menu click.

---

## Files to Create (bridge process — `/Users/bbui/rb_ss_bridge_v2/`)

### `runtime_status.py` — snapshot writer + command reader

```
class StatusWriter(threading.Thread):
    def __init__(self, sm, live_bpm, pos_cache, conn, mirror, validation_runner): ...
    def run(self): ...  # 500ms loop, atomic JSON write
    STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"

class CommandReader(threading.Thread):
    def __init__(self, conn, output, mirror, validation_runner): ...
    def run(self): ...  # tail /tmp/rb_ss_bridge_v2_commands.jsonl
    COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
    # handles: run_validation, arm_live, toggle_mirror, start_capture, stop_capture, dry_run_replay
```

### `os2l_mirror.py` — packet ring buffer

```
class OS2LMirror:
    RING_SIZE = 200
    def record(self, obj: dict, sent: bool, dropped: bool): ...
    def get_summary(self) -> dict: ...  # last_packet, rate_per_s, drop_count, enabled
    def set_enabled(self, on: bool): ...
    def start_capture(self, path: str): ...
    def stop_capture(self): ...
```

Wired into `OS2LConnection`: add `mirror: Optional[OS2LMirror] = None` field. `send()` calls `self.mirror.record(obj, sent=True, dropped=False)` before enqueue; when queue full, calls `record(..., sent=False, dropped=True)` and increments `self._drop_count`.

### `validation_runner.py` — validation state machine

```
@dataclass
class ValidationResult:
    ran_at: float
    checks: list[dict]  # [{name, status: "pass"/"warn"/"fail", detail}]
    pass_count: int
    warn_count: int
    fail_count: int

class ValidationRunner:
    def __init__(self, conn, pos_cache, live_bpm): ...
    def run(self) -> ValidationResult: ...  # synchronous, called from daemon thread
    def last_result(self) -> Optional[ValidationResult]: ...
```

### `rehearsal.py` — event + packet capture, dry-run replay

```
class RehearsalManager:
    def start_capture(self, name: str): ...   # begins buffering BridgeEvents + mirror records
    def stop_capture(self) -> dict: ...        # returns counts, saves to /tmp/rb_ss_bridge_v2_captures/
    def dry_run_replay(self, name: str) -> dict: ...  # replay through FakeOutput, return result
    def status(self) -> dict: ...              # idle/capturing/replaying/done/failed + counts
```

---

## Files to Modify

### `state_manager.py`
- Add `snapshot(self) -> dict` method (under `self._lock`, copies the 12 fields listed in Gap 2)

### `osl_output.py`
- `OS2LConnection.__init__`: add `self._drop_count: int = 0` and `self.mirror: Optional[OS2LMirror] = None`
- `OS2LConnection.send()`: call `self.mirror.record(...)` if mirror set; increment `_drop_count` on `queue.Full`
- `OS2LConnection.set_mirror(mirror)`: setter called from `__main__.py` after both are constructed

### `__main__.py`
- After constructing `conn`, `sm`, `live_bpm`, `pos_cache`:
  - Construct `mirror = OS2LMirror()`; call `conn.set_mirror(mirror)`
  - Construct `val = ValidationRunner(conn, pos_cache, live_bpm)`
  - Construct `rehearsal = RehearsalManager(event_queue, mirror)`
  - Construct and start `cmd_reader = CommandReader(conn, output, mirror, val)`
  - Construct and start `status_writer = StatusWriter(sm, live_bpm, pos_cache, conn, mirror, val)`
- Add to graceful shutdown: `cmd_reader.stop()`, `status_writer.stop()`

### `/Users/bbui/bridge_menubar.py`
- Keep rumps, keep all existing lifecycle logic (LaunchAgent plist unchanged — file path stays the same)
- Add `_status_rows: list[rumps.MenuItem]` (6 rows) inserted above the toggle separator
- Add `_arm_until: float = 0` field
- Extend existing 2s timer callback to read `/tmp/rb_ss_bridge_v2_status.json` and update row titles
- Add menu items: "Arm Live Actions", "Run Validation", "Toggle Mirror", "Start Capture"
- "Run Validation" appends `{"cmd": "run_validation"}` to command file
- "Arm Live Actions" appends `{"cmd": "arm_live", "expires_at": time.time()+30}` and sets `_arm_until`

---

## IPC File Paths

| File | Owner | Purpose |
|------|-------|---------|
| `/tmp/rb_ss_bridge_v2_status.json` | bridge writes, menubar reads | live snapshot at 500ms |
| `/tmp/rb_ss_bridge_v2_commands.jsonl` | menubar appends, bridge tails | control commands |
| `/tmp/rb_ss_bridge_v2_captures/` | bridge writes | named rehearsal captures |
| `/tmp/rbss_os2l_inject.jsonl` | manual writes, bridge tails | raw packet injection (unchanged) |

---

## Tests to Add (bridge process, `tests/`)

- `test_runtime_status.py`: snapshot serialization, atomic write, stale snapshot detection, command parsing
- `test_os2l_mirror.py`: ring buffer limits, drop counting, JSONL capture format, rate calculation
- `test_validation_runner.py`: pass/warn/fail outcomes with mocked conn/pos_cache/live_bpm
- `test_rehearsal.py`: capture start/stop, dry-run replay ordering, live-replay arm gate
- `test_state_manager_snapshot.py`: snapshot() returns correct fields under concurrent push-loop simulation

Menu bar: no unit tests added. Smoke test: start bridge, open menu, confirm rows update; click "Run Validation", confirm result row changes within 2s.

---

## Verification

1. Start bridge normally via menu bar toggle.
2. Confirm `/tmp/rb_ss_bridge_v2_status.json` appears within 1s and updates every ~500ms.
3. Open menu bar — confirm 6 status rows show live deck info, BPM, mode.
4. Click "Run Validation" — confirm result row shows "8/8 pass" (or specific warn/fail) within 2s.
5. Click "Toggle Mirror" — confirm `"mirror_enabled": true` in status snapshot.
6. Play a track — confirm mirror ring buffer populates (visible in status as `mirror_rate > 0`).
7. Click "Start Capture", play 10s, click "Stop Capture" — confirm JSONL file in `/tmp/rb_ss_bridge_v2_captures/`.
8. Click "Arm Live Actions" — confirm arm expires after 30s (menu item unchecks) without re-clicking.
9. Run bridge tests: `python -m pytest tests/test_runtime_status.py tests/test_os2l_mirror.py tests/test_validation_runner.py tests/test_rehearsal.py -v`
10. Confirm single bridge process after all operations: `pgrep -f rb_ss_bridge_v2 | wc -l` → 1.
