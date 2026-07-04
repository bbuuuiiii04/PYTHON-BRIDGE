---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: dc6f062
last_verified_date: 2026-07-04
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Implementation Spec — Logging Overhaul (AWR-125, Phase 3 build)

Executes `docs/plans/active/logging_overhaul_design.md` (design, verdict READY) under the intent
contract `docs/architecture/logging_authority.md`. Implementers are **Sonnet 5 subagents
orchestrated by Fable in-session** (operator-granted exception; Codex not used for this
workstream). Every anchor below was re-verified at `dc6f062`; if a line has drifted when you edit,
trust the named function/format string and the current file.

Baseline at spec time [confirmed]: suite `python3 -m unittest discover tests` = **2954 tests OK
(5 skipped, 1 expected failure)**; worktree clean at `dc6f062`; hard doc checks green.

## Part A — Context & root cause (read, do not implement)

- Today's pipeline: stdlib logging → one stdout `StreamHandler` installed at `__main__.py:297-306`
  (module import time) with `_ColorFormatter` (`__main__.py:107`) or env-gated `JsonFormatter`;
  `logging_manager.py` (596 lines) layers trace contextvars, a runtime module/deck/event filter,
  a control-file watcher thread, an anomaly rule, remediation hints, and `LogStats`. `/tmp/bridge.log`
  is a shell redirect of stdout (`scripts/ss_bridge_watcher.sh:146` auto, `:161` manual via `tee`).
  [confirmed]
- Root problems: hot-path log lines do blocking stream writes under the handler lock (manual mode
  = a `tee` pipe); three formatters + a filter maze nobody sets (census: no `BRIDGE_LOG_*` env var
  is set anywhere; nothing writes the control file); one logical event logs 2–4 duplicate lines;
  intent and health are indistinguishable from noise. [confirmed, design §1–2]
- Target: one JSONL stream via new `bridge_log.py` (bounded queue → writer thread), stdlib
  `logging` stays the ordinary API, ~16 `perf.*` intent emits + `health.*` transition emits,
  viewer `bridge_view.py` (stdlib curses) renders four lenses, watcher opens it as the single
  monitor window. ~820 lines of old machinery deleted at the end.

## Part B — Tasks (implement in order; one commit per task; suite green after each)

### Absolute rules (every task)
- **Never run the bridge or any hardware path**: no `python3 -m rb_ss_bridge_v2`, no watcher
  execution, no osascript, no MIDI/DMX/Govee/OS2L network or device I/O. Tests use pure seams,
  temp dirs, and in-memory handlers only; never bind real ports or touch `/tmp/bridge.log`.
- **Do not touch**: `govee_frame_renderer.py`, Template Lab files/docs (a parallel session owns
  them, AWR-126), `session_recorder.py`, `StatusWriter` snapshot/commands surface (only the one
  heartbeat log call changes), `laser_decision_log.py`, `bridge_fmt.py` (consumed, not modified),
  anything under `tools/ssfmt/`.
- **Light output must be byte-identical.** This is a logging-only change: no decision, timing,
  DMX/MIDI/Govee/OS2L payload, or status.json behavior may change. If a task seems to require it,
  stop and report.
- Error handling: the logging pipeline itself must never raise into callers — drop + count. Do
  not add broad try/except anywhere else; keep existing failure behavior.
- Commit only the files your task names (plus contract/doc lines it names). `git add` explicit
  paths; never `-A`. End commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- This is benign local logging/observability work on a hobby DJ-lighting bridge — normal software
  correctness only.

### Task W1 — `bridge_log.py` (new) + `tests/test_bridge_log.py` (new) + contract line
New module at repo root, ~250 lines, stdlib only. Public surface:

- Contextvars `_DECK = ContextVar("deck", default=0)`, `_TRACE = ContextVar("trace", default="")`.
  `event_scope(kind: str, *, deck: int = 0, trace_id: str = "") -> ContextManager[str]` — sets
  both (generates a 6-hex trace id if empty; `kind` accepted for parity, not stored), restores on
  exit, yields the trace id. `stamp_trace(ev) -> str` — ensures `ev.payload["__trace_id"]`
  (creating payload dict if None) and stamps `ev.payload["__enqueue_mono"] = time.monotonic()`;
  returns the trace id. (Mirrors today's `LoggingEventQueue.put_nowait` stamping,
  `logging_manager.py:216-225`, minus LogStats.)
- `class TraceQueue` — thin wrapper over a `queue.Queue` with `put_nowait` (calls `stamp_trace`
  then inner put; preserves an optional `enqueue_callback` exactly as
  `logging_manager.LoggingEventQueue` does today), `get`, `get_nowait`, `qsize`.
- `emit(cat: str, msg: str, *args, lvl: int = logging.INFO, deck: int | None = None,
  beat: float | None = None, data: dict | None = None, exc_info=None)` — fetches a cached
  `logging.getLogger(cat)` and calls `.log(lvl, msg, *args, extra={"cat": cat, "deck": deck,
  "beat": beat, "data": data}, exc_info=exc_info)`. `perf(sub, msg, *args, **kw)` =
  `emit(f"perf.{sub}", ...)`; `health(sub, msg, *args, lvl=logging.WARNING, **kw)` =
  `emit(f"health.{sub}", ...)`.
- `build_record(record: logging.LogRecord) -> dict` — **pure function** (unit-test seam). Keys in
  this order: `ts` (`record.created`), `mono` (`time.monotonic()`), `lvl` (`record.levelname`),
  `cat` (`getattr(record, "cat", None) or record.name`), `msg` (`record.getMessage()`), `src`
  (`record.name`), then only-if-present: `deck` (explicit extra else `_DECK.get()` if nonzero),
  `beat`, `trace` (`_TRACE.get()` if set), `data`, `exc` (formatted via
  `traceback.format_exception` when `record.exc_info`).
- `class _QueueRecordHandler(logging.Handler)` — `emit()` = `build_record` + `put_nowait` on a
  module-level `queue.Queue(maxsize=8192)`; on `queue.Full` increment a drop counter and return;
  any other exception is swallowed (never propagates). No I/O, no `json`, no locks beyond the
  queue's own.
- Writer thread `bridge-log-writer` (daemon): loop `get(timeout=0.5)`; `_redact` the `data` value
  (port `_redact` from `logging_manager.py:36-48` verbatim); `json.dumps(d, separators=(",", ":"),
  ensure_ascii=False, default=str)`; append + flush when the queue is empty (batch flush
  otherwise); mirror records with `levelno >= WARNING` to `sys.stderr` as
  `HH:MM:SS.mmm [LEVEL] msg`; when the drop counter advanced since last report, write a
  `{"cat": "sys.log", ...}` record directly (not via the queue) with the delta.
- `resolve_log_dir(env: Mapping[str, str]) -> Path` — **pure**: `$RBSS_RUNTIME_DIR/logs` if
  `RBSS_RUNTIME_DIR` set, else `~/Library/Logs/rb_ss_bridge`.
- `prune_runs(dir: Path, keep: int = 20)` — **pure-ish** (takes dir): delete oldest
  `bridge-*.jsonl` beyond `keep`.
- `init()` — idempotent. Resolve dir, mkdir parents, open `bridge-YYYYMMDD-HHMMSS.jsonl`, point
  `current.jsonl` symlink at it, create `/tmp/bridge-events.jsonl` symlink **only when
  `RBSS_RUNTIME_DIR` is unset**, `prune_runs`, write header record
  `{"cat": "sys.boot", "data": {"schema": 1, "pid": ...}}`, set `logging.root.handlers = [handler]`,
  root level INFO, apply `BRIDGE_DEBUG=1` → root DEBUG and `BRIDGE_LOG_LEVELS=name=LEVEL,...`
  per-logger floors, chain-install `sys.excepthook`/`threading.excepthook` wrappers that emit a
  `sys.crash` ERROR record then call the prior hook, start the writer thread, register `atexit`
  `shutdown`.
- `shutdown(timeout: float = 2.0)` — sentinel-stop the writer, drain, write footer
  `{"cat": "sys.shutdown", "data": {"dropped": N}}`, close file. Idempotent.
- `thread_guard(name: str)` — contextmanager for thread run-loops: emits `sys.thread` INFO
  `started`/`exited` records; if an exception escapes, emits ERROR with traceback and re-raises.
- Import of `bridge_log` must have **no side effects** (viewer imports it for `resolve_log_dir`
  only); everything starts in `init()`.

Tests (`tests/test_bridge_log.py`, unittest style like siblings): `build_record` field
order/optional-key omission/contextvar pickup/exc formatting; drop-on-full with a `maxsize=2`
queue; writer thread writes valid JSONL to a tmpdir and mirrors WARNING to a captured stderr;
`_redact` masks `key`/`token`/`secret`/`password` keys; `resolve_log_dir` both branches;
`prune_runs`; `event_scope` restore semantics; `stamp_trace` preserves an existing trace id and
never mutates other payload keys; `TraceQueue` callback passthrough; `init`+`shutdown` in a
tmpdir (env-patched) produce header+footer records; idempotent double-`init`.

Same commit: in `docs/agents/change_contracts.yml` `logging_visibility`, add `bridge_log.py` to
`code_globs`, add `emit`/`perf`/`health` to `key_symbols`, and add
`python3 -m unittest tests.test_bridge_log` to `tests`. Run the three hard doc checks + new tests
+ full suite.

### Task W2 — cutover (`__main__.py`, `state_manager.py`, `filepath_resolver.py`, 2 test files)
After this task `logging_manager` has **zero importers** but still exists (deleted in W5).

- `__main__.py`: delete the `_ColorFormatter` class (`:107-294`) and the module-init block
  `:297-305` (`LOG = get_logging_manager()`, `basicConfig`, `LOG.configure`, `reload_from_env`,
  formatter swap); replace with `from . import bridge_log` + `bridge_log.init()` (module level,
  same position, so early boot lines still capture). Keep `log = logging.getLogger("bridge")`.
  Replace `LOG.wrap_queue(...)` with `bridge_log.TraceQueue(...)` preserving any
  `enqueue_callback` argument exactly. Replace the two `LOG.log_error(log, ...)` calls (OSC
  listener region) with `log.error(...)` (append `exc_info=True` only where log_error passed it).
  Delete `LOG.start_control_watcher(log)` (`:1823`), replace `LOG.stop_control_watcher()`
  (`:1896`) with `bridge_log.shutdown()`, delete the `_reload_logging` SIGHUP handler block
  (`:1923-1929`) and the `log_control=` field from the `[MAIN] running` banner. Keep
  `diagnostics.enable_debug()` (`:1125`) working for now (dies in W5).
- `state_manager.py`: replace `from .logging_manager import get_logging_manager` / `LOG = ...`
  (`:102`, `:135`) with `from . import bridge_log`. In `_drain_events`/`_handle_event`
  (`:1085-1140` region): delete `LOG.detect_anomaly(ev)`; `LOG.event_scope(...)` →
  `bridge_log.event_scope(kind, deck=..., trace_id=payload.get("__trace_id",""))`;
  `LOG.finish_event(ev)` → inline latency: pop `"__enqueue_mono"` from payload, compute
  `latency_ms`, keep the existing `[SM] event-late` WARNING thresholds unchanged. Delete the four
  `LOG.stats.record_transition(...)` calls; `LOG.log_error(log, ...)` (`:1108` region) →
  `log.error(..., exc_info=...)` matching current args.
- `filepath_resolver.py`: replace the `LOG = get_logging_manager()` usage (`:30`, `:35`; its call
  sites are `LOG.log_error` style — verify and swap to plain `log.error`).
- Tests: `tests/test_main_mixer_authority_wiring.py:104` slices source between `"[MAIN] running"`
  and `"LOG.start_control_watcher"` — repoint the end anchor to a stable post-banner symbol that
  still exists (verify the function's intent: it checks ordering in `main()`; choose the nearest
  following stable call). `tests/test_soundswitch_pack_startup.py:411` asserts
  `"LOG.stop_control_watcher()"` in shutdown source — change to `"bridge_log.shutdown()"`.
- `tests/test_logging_diag_coverage.py` will still pass (logging_manager untouched); leave it.

Behavior note (intended, do not "fix"): console output becomes banner prints + WARNING+ mirror;
INFO text lines stop appearing on stdout. Rollback = revert this single commit.

### Task W3a — laser perf emits (`laser_director.py`, `laser_executor.py`)
- `laser_director.py` `tick()` commit block: replace the `[LASER] scene` INFO (`:250-255`) with
  `bridge_log.perf("laser.scene", "scene %s->%s (%s)", prev, scene, reason, deck=ctx.active_deck,
  beat=ctx.abs_beat, data={"scene":..., "prev":..., "reason":..., "role":..., "dry_run":...})` —
  exact locals per current code. Keep the `reason-update` DEBUG (`:264`) as-is. Replace
  `[LASER] personality` INFO (`:676`) with `perf("laser.personality", ...)`.
- `laser_executor.py`: replace `[LX] fired` INFO (`:277`) and `same-scene-refire` INFO (`:233`)
  with `perf("laser.fired", ...)` records (`data` incl. role, scene, note, reason, cursor,
  `refire: bool`). All DEBUG gate/blackout lines stay.
- Tests: extend the existing laser director/executor test modules (find them via
  `rg -l "LaserDirector" tests/`) with assertions that a scene change / fire emits one record with
  `cat="perf.laser.scene"` / `"perf.laser.fired"` — capture via a test handler on
  `logging.getLogger("perf.laser.scene")` etc. No behavior assertions change.

### Task W3b — LED + palette perf emits (`led_dispatch_policy.py`, `led_color_engine.py`)
- `_led_send_decision` (`led_dispatch_policy.py:1092`): on the accepted path emit
  `perf("led.look", ...)` with role, look, scene_ref, reason, role_key, backend/via, phase (when
  present), active_deck; delete the three `trigger-accepted` INFO lines (`:621`, `:904`, `:1012`)
  — the emit replaces them (keep their counters/state updates untouched). `adapter-error` /
  `adapter-rejected` WARNINGs stay.
- `[RGB] color-inject` INFO lines (`:834`-region and sibling) → demote to DEBUG; add the current
  palette name into the `perf.led.look` `data`.
- `led_color_engine.py` `_apply_palette_now(name)` (`:892`): add a `reason: str` keyword param
  (default `"dwell"`); all internal callers pass their trigger (`"new_track"`, `"drop_snap"`,
  `"dwell"`, fade-completion as `"fade"`); emit `perf("led.palette", ...)` with palette, prev,
  reason, locked. Operator entry points `set_palette`/`queue_palette`/`override_palette`
  (`:770/:780/:790`) emit `perf("led.palette", ...)` with `reason="operator"` at their commit
  points (queue = when applied, not when queued — the apply path already routes through
  `_apply_palette_now`; only emit at true palette-change commits, never per-tick).
- Tests: extend existing color-engine/dispatch tests with one emit assertion per new record; the
  pure engine tests must not require `init()` (capture handler pattern).

### Task W3c — autoloop / SS / scripted perf emits (`autoloop_controller.py`, `osl_output.py`, `state_manager.py`)
- `autoloop_controller.py`: convert to single `perf("autoloop", ...)` records (one per logical
  event, `data.action` field): arm (merge INFO+DEBUG pair `:182`+`:190`), clear (`:202`),
  arm-pending (merge `:241`+`:249`; also `:592`), arm-immediate (`:269`), grace-late (`:295`,
  `lvl=WARNING`), correction-pending (`:500`), correction-clear (`:626`), lock (merge `:639` +
  `:699` into ONE record; include lateness; `arm-late`/`arm-phrase-miss` WARNINGs `:669`/`:682`
  stay WARNING as `perf("autoloop", ..., lvl=WARNING)`), rearm (`:747` module fn). Demote
  `log_autoloop_tick` (`:341`) body to DEBUG (rich diagnostics retained for MAX DEBUG).
- `state_manager.py` midi-refire (`:3846`): replace the INFO with `perf("ss", "midi-refire ...")`
  (deck, beat, source); it fires adjacent to the autoloop tick — with the tick line now DEBUG the
  phrase event produces exactly one INFO-level record.
- `osl_output.py` `send_deck_load` (`:297`): replace INFO with `perf("ss", "deck-load ...")`
  (deck, active, file basename via `bridge_fmt.short`, ssid, bpm, loop, play).
- `state_manager.py` scripted: `:2376` arm-fail → `perf("scripted", ..., lvl=WARNING)`; `:2413`
  arm commit + `:2448` phase2 → `perf("scripted", ...)`.
- Tests: one emit assertion per record class in the existing autoloop/scripted test modules.

### Task W3d — deck / drop / override / heartbeat perf emits (`state_manager.py`, `led_dispatch_policy.py`, `runtime_status.py`)
- Deck switches → `perf("deck", "switch %d->%d (%s)", old, new, reason_or_src, ...)` at ALL FIVE
  sites: `state_manager.py:1560` (resolver commit; src+reason available) and the four auto sites
  `:3441`, `:3591`, `:3623`, `:4208` (reasons: `idle+mirror-playing`, `stopped+mirror-playing`,
  `idle+mirror-playing`, `empty-deck`). Replace the existing `[SM] switch` INFO lines.
- Drop → at the `smart_drop_result.crossing` consumption (`:3791` region) emit one
  `perf("drop", ...)` per crossing tick with deck, beat, and `blackout` (from
  `smart_drop_blackout_mode` / `blackout_armed` locals — verify in current code). Emit exactly
  once per crossing (the `crossing` flag is already edge-shaped; do not add per-tick emits).
- Overrides → in `led_dispatch_policy._handle_led_event` (`:375`) emit `perf("override", ...)`
  per consumed LED command (surface="led", action from event kind, source=`ev.source`, target/
  reason fields when present). In `state_manager._handle_event`'s laser command branches
  (`LASER_TOGGLE`, `LASER_SET_ENABLED`, `LASER_SCENE`, `LASER_BLACKOUT`, `LASER_CLEAR_BLACKOUT`,
  `LASER_CLEAR_SCENE_OVERRIDE`, `LASER_SET_PERSONALITY` — locate via `rg "Ev.LASER_"
  state_manager.py`) emit `perf("override", ...)` with surface="laser".
- Heartbeat → `runtime_status.py:216-233`: replace the `[BEAT]` INFO with
  `bridge_log.perf("heartbeat", "beat", data=heartbeat)` keeping the existing throttle exactly.
- Tests: emit assertions per class (deck switch via resolver-commit path test; heartbeat via
  StatusWriter test with tiny throttle; override via `_handle_led_event` test).

### Task W4 — health emits, demotions, hot-path hygiene (multiple files)
Every `health.*` emit is edge-triggered: guard with `bridge_fmt.log_changed(key, state)` (or an
existing streak counter transition), never per-instance. Recategorize = replace the logging call;
keep message content equivalent.

- `osl_output.py`: `connected` (`:169`) → `health("os2l", ..., lvl=INFO)`; `connect-fail` (`:175`)
  → `health("os2l", ...)` guarded by `log_changed("os2l_conn_fail", (host, port, type(exc).__name__))`
  so a retry loop emits once per failure streak; `send-error` (`:148`) → `health("os2l", ...)`;
  `queue-full` (`:128`) → `health("queue", ...)` with `log_throttled("os2l_queue_full", 5.0)`.
- `midi_output.py`: `_record_send_error` (`:429`) → `health("midi", ...)` (degraded enter, reason);
  successful recovery in `_attempt_send_error_recovery` (`:440`) → `health("midi", "recovered",
  lvl=INFO)` on the actual degraded→ok transition (verify where `_degraded` clears). Demote the
  three `[MIDI] tx` INFO lines (`:267`, `:336`, `:351`) to DEBUG.
- `enttec_dmx_pro.py`: write error (`:218`) → `health("dmx", ...)` guarded by
  `log_changed("dmx_write_err", bool)`; port-open failure in `_run` (`:179` region) →
  `health("dmx", ..., lvl=ERROR)`.
- `govee_scene_adapter.py`: on `_consecutive_send_failures` 0→1 transition emit
  `health("govee.cloud", ..., data={"reason": self._last_error})`; on first success after a
  failure streak (`:185` region clears `_last_error`) emit `health("govee.cloud", "recovered",
  lvl=INFO)`. Use `log_changed("govee_cloud_ok", bool)`.
- `govee_realtime_runner.py`: `last_error` transitions at `:268`/`:328` — emit
  `health("govee.rt", ...)` on ""→error and error→"" transitions via `log_changed`.
- `rb_state_reader.py`: attached (`:200`) → `health("rb", ..., lvl=INFO)`; attach-fail (`:194`) →
  `health("rb", ..., lvl=ERROR)` (keep `log.exception` traceback by passing `exc_info=True`);
  no-offsets (`:185`) → `health("rb", ...)`; queue drop (`:655`) → `health("queue", ...)`.
- `rb_memory.py`: RB gone (`:1073`) → `health("rb", ...)`; in the RB_RESTARTED enqueue
  `except Exception:` swallow (`:1087` region) add `log.warning("[RBMEM] rb-restart enqueue failed")`
  (bounded — fires at most once per restart). Drift warnings (`:1184` region) →
  `health("reader", ...)` keeping `deck=`.
- `state_manager.py`: `stop-stale` (`:3410`) → `health("reader", ...)`; push-loop error (`:862`)
  → `health("tick", ..., lvl=ERROR)` keeping the 1/s rate limit; guard the per-event payload
  dict-comprehension + debug (`:1138-1139`) with `if log.isEnabledFor(logging.DEBUG):`.
- Thread liveness: wrap each long-lived thread run-loop body with `bridge_log.thread_guard(name)`:
  `state_manager._run`, `rb_state_reader.run`, `rb_memory` reader loop, `live_bpm` service loop,
  `mtc_reader.run`, `runtime_status.StatusWriter.run` + `CommandReader.run`, `osl_output`
  `_sender_loop` + `_reconnect_loop`, `govee_realtime_runner._loop`, `enttec_dmx_pro` worker
  `_run`, `midi_output` sender loop. Locate each `def run(`/thread target; the guard adds no
  per-iteration cost (wraps the whole loop).
- Tests: transition-edge tests per backend (fail streak emits once; recovery emits once);
  `thread_guard` exception → ERROR record + re-raise; demotion assertions ([MIDI] tx now DEBUG);
  `isEnabledFor` guard covered by asserting no comprehension side effects at INFO (existing event
  tests keep passing).

### Task W5 — teardown (delete `logging_manager.py` + residue)
Preconditions: W2–W4 landed; `rg -l "logging_manager" --type py` shows only `logging_manager.py`
and `tests/test_logging_diag_coverage.py`.

- Delete `logging_manager.py`. Delete `tests/test_logging_diag_coverage.py`; create
  `tests/test_logging_surface.py` preserving the still-meaningful assertions: errors always
  visible (ERROR records pass regardless of logger levels), `BRIDGE_LOG_LEVELS` parsing,
  `BRIDGE_DEBUG` behavior (port these against `bridge_log`).
- `diagnostics.py`: delete `enable_debug`/`is_debug` (keep `DriftDetector`); `__main__.py`: drop
  the `enable_debug` import/call (`:1125` region) — `bridge_log.init()` already honors
  `BRIDGE_DEBUG`; keep the `--debug` CLI flag working by setting `os.environ["BRIDGE_DEBUG"]="1"`
  before `init()` runs or calling root-level set (verify flag plumbing; behavior: `--debug` still
  yields DEBUG everywhere).
- Delete `docs/setup/logging_live_watch.json`. Update `logging_visibility` contract: remove that
  file from `code_globs`/`inspect`, remove `LoggingManager` from `key_symbols`, swap
  `tests.test_logging_diag_coverage` → `tests.test_logging_surface`.
- Sweep: `rg -n "BRIDGE_LOG_(JSON|MODULES|DECKS|EVENTS|DIAG|ANOMALIES|CONTROL)|logging_manager|log_event_scope|get_logging_manager"`
  across `*.py` and docs — code hits must be zero; doc hits get fixed in W7 (list them in your
  report).

### Task W6 — `bridge_view.py` (new) + `tests/test_bridge_view.py` (new) + contract line
Stdlib-only (curses, json, argparse, pathlib, collections). Import `bridge_log` for
`resolve_log_dir` only. Two layers:

1. **Pure layer (unit-tested, no terminal):** `parse_record(line) -> dict|None` (tolerates
   truncated last line, unknown fields); `lens_of(rec) -> set[str]` implementing exactly:
   PERFORMANCE = `cat.startswith("perf.")`; OPERATOR = `levelno >= WARNING or
   cat.startswith("health.")` (map `lvl` names); SYSTEM = `cat.startswith(("sys.", "health."))
   or src in LEGACY_INFRA` (tuple: `rb_memory`, `rb_state_reader`, `live_bpm`, `mtc_reader`,
   `osl_output`, `os2l_injector`, `runtime_status`, `bridge`, `diagnostics`); DEBUG = always.
   `format_line(rec, width) -> str` implementing the readability contract: fixed columns
   `HH:MM:SS.s  D<deck>  <surface>  <payload> (<reason>) @b<beat>`, truncate with `…`, never
   wrap; `FRIENDLY = {"perf.laser.scene": "laser", ...}` single map (unmapped → logger name
   verbatim, no invented codes). `LatchState` class: `note(rec)` latches WARNING+ / `health.*`
   records; `health.*` INFO with the same category clears its latch (recovery); `ack()` clears
   all; exposes current latched list + "all quiet since". Age formatting helper (`"2m ago"`).
2. **Curses layer (not unit-tested):** screens 1-SHOW (heartbeat header from latest
   `perf.heartbeat` + staleness age with yellow >5s / red >15s; PERFORMANCE feed; latched
   OPERATOR strip, green when empty), 2-OPERATOR (per-category last-state summary + feed),
   3-SYSTEM, 4-DEBUG with `/` substring + `deck=N` + `cat=prefix` filter, `c` clear. Keys:
   `1-4`, `space` freeze (buffering continues), `j/k` scroll frozen, `a` ack, `q` quit. Terminal
   bell once per new latch. Repaint ≤10 Hz and only on change (stillness rule); per-lens
   `deque(maxlen=2000)`. Follow `current.jsonl`: read to EOF, poll ~100 ms, reopen on inode
   change. Red is used only for broken/stale states. Any exception: restore terminal, print
   traceback, exit nonzero (watcher reopens).

Same commit: add `bridge_view.py` to the `logging_visibility` contract `code_globs`, add
`python3 -m unittest tests.test_bridge_view` to its `tests`. Include an explicit test that a
DEBUG record with cat `rb_memory` (candidate-spam shape) routes to DEBUG lens only.

### Task W7 — watcher + docs closeout (`scripts/ss_bridge_watcher.sh`, docs)
- Watcher: `open_monitor` (`:223-232`) Terminal command → `"$PYTHON" "$REPO_ROOT/bridge_view.py"`
  (keep the `RBSS_BRIDGE_MONITOR` title printf + custom-title line; optional: target a Terminal
  profile if one named "RBSS Monitor" exists — one-line `set current settings` guarded, else skip).
  `monitor_open` (`:105-108`) → pgrep for `bridge_view.py` (drop the tail pattern). Delete
  `start_manual_terminal_bridge` (`:154-165`); manual-mode branch (`:286-304`) now: ensure bridge
  via `start_bridge` (same as auto; keeps env parity), `start_streamdeck` when bridge alive,
  `open_monitor` once, and keep manual semantics: no crash-restart backoff (do not call
  `ensure_bridge`'s backoff path; if the bridge exits in manual mode, log and `exit 0` as today);
  **closing the viewer window must NOT stop the bridge** — delete the
  "manual terminal closed; stopping bridge" branch. `close_monitor` unchanged. Add
  `scripts/ss_bridge_watcher.sh` to the `logging_visibility` contract `code_globs`.
- Shell-check the script (`bash -n scripts/ss_bridge_watcher.sh` minimum).
- Docs (per `logging_visibility` + `runtime_commands` contracts `docs_update`): rewrite
  `docs/subsystems/logging.md` (new pipeline, four lenses + predicates, record schema, the two
  surviving env vars, viewer usage/keys, extension rule, file locations/retention, watcher
  behavior, post-mortem/agent guidance: `current.jsonl` + `jq`/`rg` examples); update
  `docs/status/feature_status_matrix.md`, `docs/status/validation_matrix.md`,
  `docs/validation/software_test_inventory.md`, `docs/subsystems/tests.md` (new test modules,
  removed one); fix every stale doc reference from W5's sweep list; re-verify
  `docs/architecture/logging_authority.md` against as-built and bump its header; update the
  AWR-125 registry row (implemented/software-tested; hardware-unvalidated). `AGENTS.md` §4 source
  map: add `bridge_log.py` + `bridge_view.py` to the runtime status/commands row (or a new row)
  — smallest accurate edit.

## Part C — Invariants that MUST hold (live safety)

1. The 200 Hz push loop gains no blocking I/O: on the hot path logging does level-check →
   `build_record` → bounded `put_nowait` only. No file/socket/JSON work handler-side.
2. `BridgeEvent`s stay immutable after creation except the pre-existing payload stamping keys
   (`__trace_id`, `__enqueue_mono`) — identical to today's behavior.
3. `RBStateReader._tick_deck` ANLZ_PATH-before-TRACK_LOADED ordering untouched; `StateManager`
   remains the only `DeckState` writer; reader threads publish events only.
4. Light output byte-identical: no change to any decision, DMX/MIDI/Govee/OS2L payload, timing,
   status.json schema/content (heartbeat *log line* moves to a record; the `heartbeat` dict in
   status.json is unchanged).
5. Secrets: `_redact` applies to all record `data`; RW-5 pack sanitization untouched; never log
   `GOVEE_API_KEY`, device ids beyond what today's lines carry.
6. No bridge process, hardware, MIDI, DMX, Govee, SoundSwitch, or network I/O from any task or
   test. The operator performs any restart + `bridge-verify` himself, later.
7. Suite green after every task; the three hard doc checks green after every task that touches
   docs/contracts.

## Part D — Tests

Named per task above. Global rules: unittest style (match `tests/` conventions), pure seams (no
tmp-file logging in hot-path tests — capture handlers), no sleeps >0.2s, no real network/ports,
`bridge_fmt.reset_rate_state()` in setUp where `log_changed`/`log_throttled` guards are asserted.
The emit-assertion pattern: attach a `logging.Handler` subclass capturing `build_record`-shaped
dicts to the specific `perf.*`/`health.*` logger (propagate=True default keeps root untouched).

## Part E — Acceptance (definition of done, whole workstream)

- [ ] W1–W7 landed as separate commits, suite green after each (final count ≥ baseline 2954 minus
      the one deleted module's tests plus new ones).
- [ ] `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`
      all pass at the end (and at W1/W5/W6/W7 boundaries).
- [ ] `rg -n "logging_manager|BRIDGE_LOG_(JSON|MODULES|DECKS|EVENTS|DIAG|ANOMALIES|CONTROL)"
      --type py` → zero hits.
- [ ] Every §Part-B emit site verified present: `rg -n "perf\(\"" | wc -l` ≥ 16 across the named
      files; every `health(` site edge-guarded.
- [ ] `bridge_view.py` pure functions fully tested; candidate-noise routing test present.
- [ ] `/tmp/bridge.log` path still written by the watcher redirect (stderr mirror) — no doc claims
      it carries INFO lines anymore.
- [ ] Docs updated per contracts; registry row updated; authority doc header bumped.
- [ ] Final fresh-context review of the cumulative diff (hot-path safety + behavior-identity
      focus) completed with findings resolved.

## When you finish (each implementer)

Report: files changed, tests added/updated + counts, commands run with results, any anchor that
had drifted and how you resolved it, any deviation from this spec with reasoning. Do not push;
the orchestrator commits/pushes.
