# rb_ss_bridge_v2 logging

Status: CURRENT SUPPORTING

Audited against implementation commit `4f4c1ad` on 2026-07-05 (AWR-125 W1-W7, one JSONL event
stream + `bridge-view` TUI; replaces the retired `logging_manager.py` pipeline).

Current repo-facing status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

This is the canonical runtime logging guide. Historical implementation context for the RETIRED
system (control-file watcher, env-var filter maze, anomaly engine, `LogStats`, three formatters)
is retained in `docs/history/logging_implementation_handoff.md` — read it only for archaeology,
never as current behavior. The operator-authoritative intent contract this system must keep
matching is `docs/architecture/logging_authority.md`.

## One-stream architecture

The bridge writes exactly **one** authoritative JSONL event stream per run. stdlib `logging` stays
the ordinary emission API everywhere (`logging.getLogger(name).info(...)`, `.debug(...)`,
`.warning(...)`) — there was never a 46-file migration; ordinary records flow into the stream
automatically with `cat` = logger name. On top of that, `bridge_log.py` (repo root) adds two
structured intent/health helpers, `perf()` and `health()`, for the ~16 decision/health commit
points that need to reach the operator-facing lenses on purpose. A separate, disposable, read-only
viewer process (`bridge_view.py`, "bridge-view") renders four fixed lenses over that one stream;
the bridge itself never filters, colors, or formats output for a human — that is entirely the
viewer's job, on the read side.

**Hot path (the 200 Hz push loop's logging cost, exhaustively):** level check → `build_record()`
(a pure dict build, no I/O) → non-blocking `queue.Queue.put_nowait` onto a bounded queue
(`maxsize=8192`; full queue drops the record and increments a counter, never blocks, never raises).
One daemon writer thread (`bridge-log-writer`) owns everything slow: JSON serialization, `_redact()`
secret scrubbing, buffered disk append, and mirroring WARNING+ records to stderr (which the watcher
redirects into `/tmp/bridge.log` — a crash-catcher/banner file now, never a second event log).

## The four lenses

Lenses are read-side predicates evaluated by `bridge_view.py`'s `lens_of()` — verbatim
(`bridge_view.py:114-155`); a record carries no lens field, and membership can overlap:

```python
def lens_of(rec: dict[str, Any]) -> set[str]:
    cat = _str_field(rec, "cat")
    src = _str_field(rec, "src")
    levelno = _level_no(rec)

    lenses = {"DEBUG"}
    if cat.startswith("perf."):
        lenses.add("PERFORMANCE")
    if levelno >= _LEVEL_NO["WARNING"] or cat.startswith("health."):
        lenses.add("OPERATOR")
    if cat.startswith(("sys.", "health.")) or (
        src in LEGACY_INFRA and levelno >= _LEVEL_NO["INFO"]
    ):
        lenses.add("SYSTEM")
    return lenses
```

`LEGACY_INFRA` (`bridge_view.py:108-111`) is one read-side tuple of not-yet-namespaced infra
loggers: `rb_memory`, `rb_state`, `live_bpm`, `mtc_reader`, `osl_output`, `os2l_injector`,
`runtime_status`, `bridge`, `diagnostics`. Note `rb_state_reader.py`'s logger is actually named
`"rb_state"` (`rb_state_reader.py:58`), not `rb_state_reader` — that is the literal string in the
tuple. It shrinks as more infra modules migrate to explicit `perf.*`/`health.*` emits.

**Approved deviation (W6, 2026-07-04):** the design's literal SYSTEM predicate had no level
qualifier on the `LEGACY_INFRA` clause, which would let a DEBUG-level record from, say,
`rb_memory`'s per-candidate spam route into SYSTEM alongside real `sys.*`/`health.*` signal. That
contradicted both the design's own noise guarantee ("a chatty subsystem can pollute MAX DEBUG
only") and W6's own required test (a DEBUG record with `cat="rb_memory"` must route to DEBUG only).
The legacy-infra branch above is gated on `levelno >= INFO`; every named SYSTEM-relevant legacy
event (attach, RB gone, drift, queue drops) is already INFO/WARNING/ERROR, or has migrated to an
explicit `health.*` cat that matches the first clause directly regardless of level.

| Lens | Predicate | Answers | Screen |
|---|---|---|---|
| PERFORMANCE | `cat` starts with `perf.` | What should the rig be doing right now? | 1 SHOW (feed) |
| OPERATOR | level ≥ WARNING, or `cat` starts with `health.` | Is it working? What broke / recovered? | 1 SHOW (strip) + 2 OPERATOR |
| SYSTEM | `cat` starts with `sys.`/`health.`, or (`src` legacy-infra AND level ≥ INFO) | Threads, attach, queues, timing, connections | 3 SYSTEM |
| DEBUG | always | Forensic firehose | 4 DEBUG |

Structural noise protection: PERFORMANCE can only be reached through the narrow `perf()` helper, so
a badly-logged resolution loop cannot spam it regardless of level or text; OPERATOR only admits
WARNING+ and `health.*`. The old `[RBMEM][CANDIDATE]`/`[REJECT]` 50-INFO-lines noise class is dead
by predicate now, not by discipline.

## The record schema

One JSON object per line, built by `bridge_log.build_record()` — a pure function
(`bridge_log.py:184-215`):

```json
{"ts": 1751685243.512, "mono": 8123.402, "lvl": "INFO", "cat": "perf.laser.fired",
 "msg": "fired role=drop scene=strobe_sync note=52 reason=drop_crossing",
 "src": "laser_executor", "deck": 1, "beat": 129.02, "trace": "a3f91c",
 "data": {"role": "drop", "scene": "strobe_sync", "note": 52, "cursor": 3}}
```

| Field | Required | Content |
|---|---|---|
| `ts` | yes | `record.created` (epoch seconds, wall clock) |
| `mono` | yes | `time.monotonic()` at record-build time — ordering/latency math |
| `lvl` | yes | stdlib level name: `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |
| `cat` | yes | the emit-site category (`perf.*`/`health.*`/`sys.*`) or the logger name for ordinary stdlib records |
| `msg` | yes | `record.getMessage()` (already %-merged) |
| `src` | yes | `record.name` (logger/module name) |
| `deck` | optional | explicit `deck=` kwarg, else the ambient deck contextvar when nonzero |
| `beat` | optional | explicit `beat=` kwarg |
| `trace` | optional | the ambient trace-id contextvar, when set |
| `data` | optional | structured payload dict, passed through `_redact()` (masks `token`/`secret`/`password`/`key`-named entries) |
| `exc` | optional | formatted traceback, when the call carried `exc_info` |

A run opens with a header record (`cat="sys.boot"`, schema version + pid) and closes cleanly with a
footer (`cat="sys.shutdown"`, dropped-record count). Every reader — the viewer, `jq`, an agent —
must tolerate unknown fields/categories and a truncated trailing line (an unclean bridge death can
leave the last JSONL line partial); this is a forward-compatibility rule enforced by
`bridge_view.parse_record()`, not a suggestion.

## The only two logging env vars

- `BRIDGE_DEBUG=1` — root logger to DEBUG everywhere.
- `BRIDGE_LOG_LEVELS=name=LEVEL,name2=LEVEL2` — per-logger level floors (e.g.
  `BRIDGE_LOG_LEVELS=state_manager=DEBUG,filepath_resolver=DEBUG`).

Both are read once, inside `bridge_log.init()`, at process start. The old nine-env-var maze
(`BRIDGE_LOG_MODULES/DECKS/EVENTS/DIAG/ANOMALIES/JSON/CONTROL`), the `/tmp/rb_ss_bridge_v2_logging.json`
control file, and `SIGHUP` reload are gone — nothing in the repo sets, reads, or reloads them
anymore, and there is no live-watch preset file to copy.

## Log files

`bridge_log.resolve_log_dir()` (pure): `$RBSS_RUNTIME_DIR/logs` when that env var is set (the
parked USB-launcher relocation knob, dormant until that project resumes), else
`~/Library/Logs/rb_ss_bridge/`. Per run: `bridge-YYYYMMDD-HHMMSS.jsonl` plus a `current.jsonl`
symlink pointed at the live file — always read `current.jsonl`, not a dated file, unless you are
deliberately reading a past run. Retention: newest 20 runs kept (`prune_runs()`, run at `init()`).
The `/tmp/bridge-events.jsonl` convenience symlink exists **only** when `RBSS_RUNTIME_DIR` is unset
(the default case) — under the USB runtime dir it would add another fixed `/tmp` path outside that
project's one-prefix cleanup rule.

`/tmp/bridge.log` still exists, demoted to a plain console crash-catcher: it is the watcher's shell
redirect of bridge stdout/stderr (startup banner prints, a WARNING+ text mirror, uncaught
tracebacks). It carries no INFO lines and is not a second event log — the JSONL stream is the only
source of truth for what the bridge decided.

## Viewer (`bridge_view.py`, "bridge-view")

Read-only, disposable, crash-isolated from the bridge: it opens `current.jsonl`, reads to EOF, then
polls (~100 ms) and reopens on inode change (log rotation / bridge restart). It never writes to the
stream and never touches the bridge process — closing or crashing it has zero effect on the show.

Screens (number keys switch):

- **1 SHOW** (default, zero keys pressed): sticky header from the latest `perf.heartbeat` record
  in plain words — "deck 1 · 124.0 bpm · chorus · laser wave · led warm · palette sunset", or
  "idle — no deck playing · …" when no deck is audible (never the "D0" code); the heartbeat's
  `rgb_health` summary rides the staleness line — plus stream-staleness age (green ≤5s, yellow
  >5s, red >15s — a healthy bridge produces a fresh heartbeat every ~2-3s; the 2.0s
  `HEARTBEAT_LOG_INTERVAL_S` is a minimum-gap throttle, not a timer) + the PERFORMANCE feed +
  a bottom OPERATOR strip (green "✓ all quiet since HH:MM:SS" when healthy). The heartbeat record
  itself is header-only: it never scrolls through the feed (a steady show is a still screen); it
  stays visible in DEBUG.
- **2 OPERATOR**: a per-`health.*`-category last-state summary line (colored by severity), then
  the full OPERATOR feed. Acks (`a`) persist across viewer restarts within one run via a
  `viewer_acks.json` sidecar in the log dir — the viewer's only write anywhere; run files stay
  untouched. A new bridge run starts with a clean latch slate.
- **3 SYSTEM**: the infra feed.
- **4 DEBUG**: everything, with a `/`-filter (substring match on cat/msg, plus `deck=N` and
  `cat=prefix` tokens), `c` clears the filter.

Keys: `1`-`4` switch screens, `space` freezes/resumes (buffering continues while frozen), `j`/`k`
scroll when frozen, `a` acknowledges latched alerts, `q` quits.

**Latching, never transient.** A new WARNING/ERROR rings the terminal bell once and latches the
OPERATOR strip red with that problem text until it clears or is acknowledged. A `health.*` category
clears its own latch on the matching recovery record (e.g. `health("midi", "recovered",
lvl=INFO)`); a plain WARNING/ERROR outside `health.*` has no recovery signal and stays latched until
`a`. Nothing important is ever conveyed by a flash alone, and nothing important can scroll away.

Readability rules baked into the renderer (the design's nine-rule ADHD-first contract, all
acceptance criteria): stillness means healthy — repaint ≤10 Hz and only on change, no spinners; state
lives in fixed screen positions, never only in scrollback; one fact per line, fixed columns,
truncate with `…`, never wrap; plumbing (time/reason/beat) renders dim, payload (deck/surface/
value) renders bright — the most important word is the most visible word; a fixed color vocabulary
where red only ever means broken; plain words (`laser`, `led`, `autoloop`) never legacy codes
(`[LX]`, `[RBMEM]`, `[SM]`) — unmapped categories fall back to their raw name, never a new code;
ages shown relative ("2m ago") outside the feed's own absolute timestamps; the newest feed line
carries a static `▸` marker, no animation; screen 1 requires zero keys and the viewer never steals
focus or requires acknowledgment to keep functioning.

## Watcher behavior (`scripts/ss_bridge_watcher.sh`)

One monitor window, in both auto and manual launch modes. `open_monitor()` launches `"$PYTHON"
"$REPO_ROOT/bridge_view.py"` inside a Terminal.app window tagged `RBSS_BRIDGE_MONITOR`, sized to
140×40 (Terminal's default 80×24 truncated most real messages);
`monitor_open()` counts a viewer only if the matched process (marker or full-path
`bridge_view.py`) still owns a terminal (`ps -o tty=` not `??`) — a headless orphan viewer must
not suppress reopening (2026-07-05 no-window regression). `close_monitor()` kills both the
marker-bearing wrapper and the full-path viewer process, then closes the Terminal tab; the viewer
itself also exits when its terminal dies (tty-hangup check in `_run`), so no close path can leave
an orphan behind.

Manual mode (`RBSS_BRIDGE_MANUAL=1`) now starts the bridge through the exact same `start_bridge()`
the auto path uses, instead of a separately hand-maintained launch string — this closes a real
env-drift bug where the old manual path was missing several `RBSS_LED_*` flags present in the auto
path — and opens the same single viewer window. It keeps its own lifecycle meaning: no
crash-restart backoff (a bridge exit ends the watcher, not a retry loop, same as before).

**Closing the viewer window never stops the bridge.** The viewer is a separate, disposable, crash-
isolated process; a display crash or an operator closing the window must never end the show. Only
the menubar (auto mode's bridge lifecycle owner) or the bridge process itself exiting (manual mode)
stops the bridge. The watcher's own job is only to reopen a missing viewer.

## Extension rule (per new feature)

No lens, viewer, schema, or config work is ever required for a new feature — categories route
themselves by namespace. Three questions at the commit point:

1. **Decides what the rig does right now?** → one `bridge_log.perf(<cat>, ...)` call at the commit
   point. Appears on the PERFORMANCE feed as-is.
2. **Can fail/recover?** → one `bridge_log.health(<cat>, ...)` transition pair, edge-triggered
   (guard with `bridge_fmt.log_changed()`/`log_throttled()` or an existing streak counter — never
   per-instance). Appears on OPERATOR, latched.
3. **Everything else** → ordinary `logging.getLogger(name).info/debug/warning(...)`, which remains
   the normal API for all code and lands in the stream automatically (MAX DEBUG; WARNING+ reaches
   OPERATOR on severity alone, with no extra work).

Every new emit site inherits the hot-path rule: no blocking I/O, no per-frame INFO. A badly-logged
feature can pollute MAX DEBUG only — it structurally cannot reach the mid-set screens. Optional
polish: one entry in `bridge_view.py`'s single `FRIENDLY` name map; unmapped categories already
render their raw name rather than a new code, so this is never required.

## Agent post-mortem guidance

Read the current run directly — there is no control file, no live-watch preset, no reload to
apply:

```bash
# Tail the live stream, pretty-printed
tail -f ~/Library/Logs/rb_ss_bridge/current.jsonl | jq -c .

# Everything at WARNING+ (the OPERATOR lens, offline)
jq -c 'select(.lvl == "WARNING" or .lvl == "ERROR" or .lvl == "CRITICAL")' \
  ~/Library/Logs/rb_ss_bridge/current.jsonl

# One subsystem's intent records
jq -c 'select(.cat | startswith("perf.laser"))' ~/Library/Logs/rb_ss_bridge/current.jsonl

# Plain-text search still works — one JSON object per line
rg '"cat":"health\.' ~/Library/Logs/rb_ss_bridge/current.jsonl
```

If `RBSS_RUNTIME_DIR` is set (parked USB-launcher mode), read `$RBSS_RUNTIME_DIR/logs/current.jsonl`
instead; otherwise `/tmp/bridge-events.jsonl` is a convenience symlink to the same file.

**Trace-id workflow.** `TRACK_LOADED` → `FILEPATH_RESOLVED` → `SCRIPTED_ARM` share one `trace` id
when the chain runs, so a bad arm can be reconstructed end to end:

```bash
jq -c 'select(.trace == "a3f91c")' ~/Library/Logs/rb_ss_bridge/current.jsonl
```

How the id actually gets there (verified against code, `state_manager.py:1820-1850`,
`filepath_resolver.py:367-396,556-573`): within the single-threaded event-drain loop,
`bridge_log.event_scope()`'s contextvar carries the id automatically across nested handling in the
*same* call — e.g. `SCRIPTED_ARM`'s enqueue never sets `__trace_id` explicitly, it inherits the
ambient trace via `stamp_trace()`'s contextvar fallback. Across the filepath-resolver's
worker-thread hop the propagation is **explicit, not automatic**: `_on_track_loaded` reads
`ev.payload["__trace_id"]` and passes it as a `trace_id=` keyword through `resolve_by_anlz`/
`resolve_by_title`/`resolve_async`, and each resolver worker thread re-stamps
`payload["__trace_id"]` before enqueuing `FILEPATH_RESOLVED` — Python contextvars do not cross
thread boundaries on their own, so any future cross-thread hop that skips this explicit parameter
threading would silently break the chain for that hop.

Other useful greps:

- `jq -c 'select(.cat == "sys.thread")'` — thread start/exit/crash records: the design's one
  genuinely new observation, since an unexpectedly-dead thread used to be invisible.
- `jq -c 'select(.deck == 1)'` — everything for one deck.
- `jq -c 'select(.cat | startswith("health."))'` — every edge-triggered health transition
  (fail → one record, recover → one record; never per-failure spam).

## Historical context

`docs/history/logging_implementation_handoff.md` documents the retired `logging_manager.py`
pipeline (control-file watcher, env-var filter maze, anomaly engine, `LogStats`, three competing
formatters) — evidence of what this system replaced, never current behavior.
