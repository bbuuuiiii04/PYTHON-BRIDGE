---
doc_status: active-design
truth_level: design, code-grounded
last_verified_commit: 02250de
last_verified_date: 2026-07-04
validation_scope: design only; no code changed; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Logging Overhaul — Phase 1 Design

**Status: planned (design). Spec-readiness verdict: READY WITH GAPS — see §4 (two operator
defaults to confirm, two line-level pins Phase 2 must re-verify; none block drafting the spec).**

This is the Phase 1 deliverable of the three-phase logging overhaul
(design → spec → build). It replaces today's `logging_manager.py` pipeline with:

- **one JSONL event stream** written by the bridge (the authoritative record of every meaningful
  decision and health transition),
- **four lenses** (PERFORMANCE / OPERATOR / SYSTEM / MAX DEBUG) implemented as **read-side filters
  in a separate viewer process** (`bridge_view.py`, working name `bridge-view`), auto-launched by
  the existing watcher monitor window,
- and a **hard teardown** of the current machinery: control-file watcher, env-var filter maze,
  anomaly engine, remediation hints, LogStats, three competing formatters, and the runtime
  module/deck/event filter.

Bridge-side logging code shrinks from ~900 lines across three files to one ~250-line module.
The 200 Hz push loop's logging cost goes **down**: today every hot-path log line does a blocking
`stream.write()+flush()` to a stdout pipe under the handler lock; in this design the hot path does
a bounded, non-blocking queue put and nothing else.

**Phase 3 operator role exception (recorded per operator instruction):** Brandon granted a
per-workstream exception for this overhaul — **Fable-family subagents implement directly** rather
than Codex. The build runs software and tests only; Brandon performs any bridge restart and
`bridge-verify` himself. This exception is scoped to the logging overhaul and expires with it.

---

## 1. What changed about the spine, and why

The four-lens model, the PERFORMANCE/OPERATOR split, the single JSONL stream, the separate
auto-launched viewer, and the TUI delivery all survive contact with the code. Both hard locks are
honored unchanged. What I changed:

**1.1 The "~46 file migration" is mostly a no-op — keep stdlib `logging` as the ordinary emission
API.** Census [confirmed]: 41 non-test files import `logging` (442 `log.<level>()` call sites);
`scripts/` and `streamdeck/` have zero. Only **3 files** import the `logging_manager` facade at all
(`__main__.py:62`, `state_manager.py:102`, `filepath_resolver.py:35`), and most of its public API
is used by exactly one caller or is dead (`bind_event`, `log_event_scope`, `LoggingEventQueue` by
name — no external callers). So the overhaul does **not** rewrite 41 files onto a new API: ordinary
code keeps calling `logging.getLogger(name)` + `log.info(...)`, and those records flow into the new
stream automatically with `cat` = logger name. Only the **handler/formatter layer** (3 files) and
the **~20 decision/health commit points** (new structured emits) change. This is a correction of
the migration premise, not a reversal of an operator decision — nothing Brandon decided required
rewriting call sites.

**1.2 PERFORMANCE records both the decision and the executed selection.** The laser chain
deliberately logs different scene values at the director ("intended") and the executor ("actually
rotated from the role bank") — [confirmed] `laser_executor.py:273-276` comment and code. Brandon's
eyes check the rig against the *executed* selection, so PERFORMANCE must carry both: `perf.laser.scene`
(director commit) and `perf.laser.fired` (executor resolution). Same one event, two facts, both
intent-side (pre-hardware). This refines the spine's "emitted at the decision point" — there are
two decision points per laser event, and hiding the second would make the lens lie.

**1.3 OPERATOR is passive-plus, not active** (§2.6 — the biggest deferred decision, resolved with
per-backend evidence: no output path has any acknowledgement channel today).

**1.4 The default viewer screen is a composite SHOW view, not one-tab-per-lens.** The spine said
"a tab or pane per lens." Mid-set, Brandon needs PERFORMANCE intent, a current-state header, and
the OPERATOR alert strip *simultaneously* — flipping tabs mid-mix is the failure mode. So the
default screen composes those three; keys 1–4 still give each lens its own full tab. Flagged as a
UX refinement of an operator choice, not a reversal: all four lenses exist exactly as designed.

**1.5 The heartbeat moves from a text line to a structured record.** Today `runtime_status.py:223`
logs a `[BEAT]` INFO line every 2 s [confirmed]. That line becomes `perf.heartbeat` (same cadence,
same fields as `_heartbeat_payload`, `runtime_status.py:713-777`), and the viewer renders it as the
sticky header instead of a scrolling line. Net effect: the single most repetitive INFO line in the
log becomes zero scrolling lines and a permanently-visible header.

**1.6 `/tmp/bridge.log` survives, demoted to crash-catcher.** [confirmed] Nothing in Python writes
it — it is the watcher's shell redirect of bridge stdout (`scripts/ss_bridge_watcher.sh:146` auto
mode; `:161` manual mode via `tee`). It stays exactly that: startup banner prints, a WARNING+
plain-text mirror (see §2.3), and uncaught tracebacks. It is a console capture, not a second event
log — the JSONL stream is the only source of truth. Existing tooling that greps `/tmp/bridge.log`
for errors keeps working.

**1.7 What I did *not* change:** the four lenses and their audiences; the one-stream lock; the
separate viewer process; watcher auto-launch; TUI delivery; the live-safety lock. `StatusWriter` /
`/tmp/rb_ss_bridge_v2_status.json` and the command reader are untouched (they are a *state
snapshot* surface for the menubar/pads, not a log — complementary, not duplicative). The
`laser_decision_log.py` in-RAM ring stays untouched (it feeds `status()["recent_decisions"]`
[confirmed `laser_director.py:869`]; behavior-neutral to this overhaul, and its schema was the
prototype for the record design below).

---

## 2. The resolved design

### 2.1 Lens model and routing rules

One stream; a lens is a **predicate over `(cat, lvl)`** evaluated in the viewer. Records never
carry lens tags. Membership can overlap (deliberately — health belongs to both OPERATOR and
SYSTEM). New-API categories are namespaced (`perf.*`, `health.*`, `sys.*`); legacy stdlib records
get `cat` = logger name (e.g. `state_manager`), which cannot collide with the namespaces.

| Lens | Predicate | The question it answers | Example line (as rendered) |
|---|---|---|---|
| **PERFORMANCE** | `cat.startswith("perf.")` | What *should* the rig be doing right now? (authoritative intent; never discusses health) | `21:14:03.5 D1 ▶ laser strobe_sync (drop_crossing) @b129` |
| **OPERATOR** | `levelno >= WARNING` **or** `cat.startswith("health.")` | Is it working? What's breaking? (quiet when all is well) | `21:14:07.2 ⚠ health.midi degraded reason=send_error port=IAC1` |
| **SYSTEM** | `cat.startswith(("sys.", "health."))` **or** `src in LEGACY_INFRA` | Infra story: threads, attach, queues, timing, connections | `21:02:11.0 sys.thread exit name=rb-state-reader expected=false` |
| **MAX DEBUG** | `True` (everything captured) | Forensic firehose for root-causing | every record, plus `/`-filter |

`LEGACY_INFRA` is one tuple in `bridge_view.py` (`rb_memory`, `rb_state_reader`, `live_bpm`,
`mtc_reader`, `osl_output`, `os2l_injector`, `runtime_status`, `bridge`, `diagnostics`) that routes
not-yet-migrated infra module records into SYSTEM. It shrinks as emits migrate; it lives in exactly
one place, on the read side.

**Why the noise class is structurally dead** (the `[RBMEM][CANDIDATE]`/`[REJECT]` 50-INFO-lines
problem):

1. PERFORMANCE admits only `perf.*`, and `perf.*` can only be produced by the narrow `perf()`
   helper called at commit points — a resolution loop physically cannot spam this lens no matter
   what level or text it logs.
2. OPERATOR admits only WARNING+ and `health.*`; candidate/reject lines are DEBUG/INFO domain
   records — excluded by predicate, not by discipline.
3. Per-candidate lines are already DEBUG today [confirmed `rb_memory.py:322-838` CANDIDATE,
   `:529-914` REJECT]; outcomes (`[RBMEM][VALIDATED]` `:542,906,909`, `[RBMEM][D2COMMIT]` `:1166`)
   stay INFO — the validated log-level lesson is now also enforced by the lens predicates, so a
   future regression to INFO spam pollutes only MAX DEBUG, never the operator-facing lenses.
4. `health.*` emits are transition-edge-triggered by construction (`log_changed`/first-in-streak
   guards, §2.6) — a failing backend produces one record per state change, not one per failure.

### 2.2 The record schema

One JSON object per line. Field order fixed for eyeball-ability; compact separators; unknown fields
tolerated by the viewer (forward compatibility). Producer builds a plain dict; the listener thread
serializes.

```json
{"ts": 1751685243.512, "mono": 8123.402, "lvl": "INFO", "cat": "perf.laser.fired",
 "msg": "fired role=drop scene=strobe_sync note=52 reason=drop_crossing",
 "src": "laser_executor", "deck": 1, "beat": 129.02, "trace": "a3f91c",
 "data": {"role": "drop", "scene": "strobe_sync", "note": 52, "cursor": 3}}
```

| Field | Req | Type | Content |
|---|---|---|---|
| `ts` | yes | float | `time.time()` epoch seconds (wall clock, ms precision in practice) |
| `mono` | yes | float | `time.monotonic()` — ordering + latency math (matches `BridgeEvent.mono`, `models.py:148-154`) |
| `lvl` | yes | str | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` (stdlib names) |
| `cat` | yes | str | dotted category; `perf.*` / `health.*` / `sys.*` from the new helpers, logger name for legacy records |
| `msg` | yes | str | human-readable one-liner (already %-merged) |
| `src` | yes | str | logger/module name |
| `deck` | opt | int | explicit arg, else ambient deck contextvar (set by the event scope) |
| `beat` | opt | float | absolute beat when in scope at the emit site |
| `trace` | opt | str | trace id from the per-event contextvar (kept from today's system) |
| `data` | opt | obj | structured payload; passed through `_redact()` (key-name secret scrub, kept from `logging_manager.py:36-48`) |
| `exc` | opt | str | formatted traceback when the call carried `exc_info` |

A **run-header record** (`cat="sys.boot"`, `data={"schema": 1, "pid": ..., "flags": {...}}`) opens
every file and a **run-footer** (`cat="sys.shutdown"`, includes dropped-record count) closes clean
runs — same pattern as `session_recorder.py`'s schema-versioned header/footer rows [confirmed
`session_recorder.py:62,198`].

**Lens membership derivation, answered explicitly:** by `cat` namespace (explicit at emit time for
the three new namespaces, logger-name fallback for legacy) **plus** severity (OPERATOR's WARNING+
clause). Records may appear in multiple lenses; they carry no lens field.

### 2.3 Emit strategy — how a record leaves the bridge without touching the push loop

New module **`bridge_log.py`** (repo root, flat-module convention). One pipeline for both record
kinds:

- **Legacy path (unchanged call sites):** `logging.getLogger(name).info(...)` → root logger →
  the one installed handler, `_QueueRecordHandler`.
- **Structured path (new):** `emit(cat, msg, *, lvl=INFO, deck=None, beat=None, **data)` →
  `logging.getLogger(cat).log(lvl, msg, extra={...})` → same handler. Thin wrappers:
  `perf(sub, msg, **kw)` = `emit(f"perf.{sub}", ...)`; `health(sub, msg, lvl=WARNING, **kw)`.
  Reusing the stdlib logger per category keeps standard level machinery (a category can be
  silenced with normal `setLevel`) and keeps ONE pipeline.

`_QueueRecordHandler.emit(record)` does, in the calling thread:

1. `record.getMessage()` (%-merge — same cost the formatter pays today),
2. read the two contextvars (deck, trace) and `time.monotonic()`,
3. build the plain dict above (traceback formatting only when `exc_info` present),
4. `queue.put_nowait(d)` on a **bounded `queue.Queue(maxsize=8192)`**; on `queue.Full`, drop the
   record and increment an atomic drop counter. Nothing raises; nothing blocks; no I/O.

A single **`bridge-log-writer` daemon thread** (the listener) owns everything slow: `json.dumps`
(with `default=str` so an exotic object can never raise in serialization), `_redact()` on `data`,
buffered file append + per-batch flush, a plain-text mirror of WARNING+ records to stderr (which
the watcher already redirects into `/tmp/bridge.log`), and a periodic `sys.log` record whenever the
drop counter is non-zero. At init (not on the hot path) it also prunes old run files.

**Level gating:** root level INFO. `BRIDGE_DEBUG=1` → DEBUG everywhere (absorbing
`diagnostics.enable_debug()`); `BRIDGE_LOG_LEVELS=name=DEBUG,...` kept verbatim for per-module
floors (6 lines of code, the main agent debugging tool). Those are the **only two** logging env
vars that survive (of today's nine, census §2.9).

**Event trace context, kept but trimmed:** the six contextvars
(`logging_manager.py:24-29`) become two — `deck`, `trace`. `event_scope(kind, deck, trace_id)`
survives in `bridge_log.py` (~15 lines) because `state_manager._drain_events` uses it per event
[confirmed `state_manager.py:1089-1095`] and the one-trace-id-across-TRACK_LOADED→FILEPATH_RESOLVED→
SCRIPTED_ARM workflow is the documented agent debugging pattern. The queue trace-stamping that
`LoggingEventQueue.put_nowait` does today (`logging_manager.py:216-225`) shrinks to a ~10-line
`stamp_trace(ev)` function (trace id only — the enqueue-timestamp/latency stats die with LogStats).

### 2.4 PERFORMANCE and health emit-site inventory

Line numbers are as of `02250de` and must be re-pinned by Phase 2 (concurrent sessions are editing
this repo). Functions are the stable anchors.

**`perf.*` — intent commits (~16 sites).** Each emits exactly one record; the legacy INFO lines it
absorbs are deleted in the same chunk (no double logging):

| cat | Emit site (function) | Data | Absorbs / replaces |
|---|---|---|---|
| `perf.deck` | `StateManager._apply_resolved_active_deck` (`state_manager.py:1536`) + auto idle+mirror switch (`:3542`) | old, new, src, authority_reason | `[SM] switch` INFO ×2 sites |
| `perf.drop` | smart-rearm crossing consumption in `_push_tick_inner` (`state_manager.py:3709-3719` region) | deck, beat, crossing type, blackout_armed | (new — silent today) |
| `perf.laser.scene` | `LaserDirector.tick` commit block (`laser_director.py:240-282`) | scene, prev, reason, role, dry_run | `[LASER] scene` INFO `:249` |
| `perf.laser.fired` | `LaserSceneExecutor.on_decision` fire/refire (`laser_executor.py:276`, `:232`) | role, scene, note, reason, cursor | `[LX] fired` / `same-scene-refire` INFO |
| `perf.led.look` | `_led_send_decision` accepted branch (`led_dispatch_policy.py:1092`; today logs at `:904`) | look, role, role_key, reason, backend, scene_ref | `[RGB] trigger-accepted` INFO; coordinator `[LED] via=` lines demote to DEBUG |
| `perf.led.palette` | `LedColorEngine._apply_palette_now` (`led_color_engine.py:886`) + operator overrides (`:769-828`) | palette, prev, trigger (new_track/drop_snap/dwell/operator), locked | (new — the palette layer is silent today [confirmed]) |
| `perf.autoloop` | `AutoloopController`: arm (`:181`), lock (`:638`+`:698` → one record), clear (`:202`), correction (`:499`), rearm (`:747`) | deck, bpm, bpm_src, target_beat, lateness, mirror | the INFO+DEBUG duplicate pairs (`:181`+`:189`, `:240`+`:248`) and the `arm-locked`/`arm-locked-final` double INFO |
| `perf.scripted` | `_arm_scripted` commit/fail (`state_manager.py:2389`, `:2352`), phase-2 (`:2424`) | deck, id, path, phase, reason | `[SM] arm-scripted` / `arm-fail` INFO/WARNING |
| `perf.ss` | `send_deck_load` (`osl_output.py:297`), midi-refire (`state_manager.py:3764`) | deck, file, ssid, bpm, loop / beat, source | `[OS2L] deck-load` INFO; `[SM] midi-refire`+`[SS][AUTOLOOP-TICK]` double INFO merge into one record |
| `perf.override` | `_handle_led_event` (`led_dispatch_policy.py:376-426`) and the laser command handlers in `StateManager._handle_event` | surface (led/laser), action (scene/blackout/clear/palette), source, ttl | (mostly new — the setters are silent today [confirmed `laser_director.py:140-177`]) |
| `perf.heartbeat` | `StatusWriter._maybe_log_heartbeat` (`runtime_status.py:216-233`), same 2 s throttle | deck, master, bpm, phrase, laser_scene, led_look, palette, rgb_health | the `[BEAT]` INFO line |

**`health.*` — reconciliation/health transitions (~10 groups).** Every emit is edge-triggered
(`bridge_fmt.log_changed` on the state value, or first-failure-in-streak), never per-instance:

| cat | Signal (all confirmed in code) | Today |
|---|---|---|
| `health.os2l` | connected (`osl_output.py:169`), connect-fail (`:175`), send-error→disconnect (`:148`), queue-full (`:128`); no-socket drops counter (`:141`) surfaces in the next transition record's data | INFO/WARNING text, disconnect transition itself unlogged |
| `health.midi` | degraded enter/exit + reason (`midi_output.py:429-470`), port_unavailable | WARNING text, recovery partially silent |
| `health.dmx` | serial write error (`enttec_dmx_pro.py:218`), port-open failure + worker exit (`:183-187`) | WARNING/ERROR text |
| `health.govee.cloud` | circuit breaker open/close (`govee_runtime_sender.py:345-347,457-458`), first send-failure per streak with reason (`http_status:`/`network_error:`/`network_timeout` `:470-494`) | **completely silent — counters only** [confirmed] |
| `health.govee.rt` | transport send_error transitions (`govee_realtime_runner.py:328`, `govee_realtime_transport.py:137-141`) | silent — counters only |
| `health.rb` | attach (`rb_state_reader.py:200`), attach-fail (`:193-199`), RB gone / RB_RESTARTED (`rb_memory.py:1073,1081-1088`) | INFO/WARNING/exception text; the RB_RESTARTED enqueue swallows `queue.Full` silently — **fixed here** (emit on drop) |
| `health.reader` | position stale force-stop (`state_manager.py:3327-3329`), drift warnings (`rb_memory.py:1184,1193,1198` — already carry `deck=`) | WARNING text |
| `health.queue` | event-queue drops (`rb_state_reader.py:653-655`) | WARNING text / partially silent |
| `health.tick` | push-loop tick error (`state_manager.py:836-842`); optional: sustained-overrun counter (see §2.5) | rate-limited ERROR |
| `health.thread` | unexpected exit of any named bridge thread (new; §2.5) | **nothing — silent feature loss today** |

The existing WARNINGs listed above are *recategorized* (message text preserved or improved), not
duplicated. Anything still logging WARNING+ outside `health.*` reaches OPERATOR anyway via the
severity clause — `health.*` is for making good-news transitions (reconnected, circuit closed,
re-attached) visible and for giving failures stable categories.

### 2.5 SYSTEM taxonomy

Everything infra, grounded in what the code already tracks:

- **`sys.boot`** — run-header record; config loads (`laser`/`led`/pack); feature-flag summary
  (absorbs the `[MAIN] running ...` mega-line, `__main__.py:1773-1798`); RB version + offsets
  resolution outcome (`rsr-direct`/`rsr-skip`, `:1725,1681,1711`).
- **`sys.shutdown`** — shutdown steps (absorbs `[MAIN] shutdown`, `__main__.py:1868-1894`);
  run-footer with drop counters and clean/unclean flag.
- **`sys.thread`** — start/exit of the ~14 named daemon threads (thread map confirmed:
  `state-manager`, `rb-state-reader`, `rb-memory-reader`, `live-bpm-service`, `mtc-reader`,
  `runtime-status`, `runtime-command-reader`, `os2l-sender`, `os2l-reconnect`, `os2l-injector`,
  `osc-server`, Govee realtime runner, DMX worker, MIDI sender). Unexpected exit → ERROR (also
  lands in OPERATOR via severity, mirrored as `health.thread`). **This is the single genuinely new
  observation mechanism in the design**, and it earns its place: today `RBStateReader.run` returns
  silently on attach failure or unsupported offsets and *nothing ever notices the thread is gone*
  [confirmed `rb_state_reader.py:183-199`; no `is_alive`/watchdog anywhere]. Cost: a `try/finally`
  + one `emit()` per thread run-loop — zero hot-path cost, no watchdog thread.
- **`sys.cmd`** — runtime command accepted/rejected in `CommandReader.handle_command`
  (`runtime_status.py:331`); today only a status-file field, never in the log.
- **`sys.tick`** — the opt-in profiler summary (absorbs `[SM][PROFILE]`, `state_manager.py:323-333`,
  still gated on `RBSS_SM_PROFILE`). Optional cheap add (flagged, not required): an
  unconditional 10 s overrun counter in `_run` (3 lines) so "the loop is drowning" is visible
  without the profiler — today overruns are invisible unless profiling [confirmed `:822-829`].
- **`sys.config`** — laser/LED config reloads (absorbs `[MAIN] laser-config-reload`).
- **`sys.log`** — the pipeline's own health: dropped-record count, writer errors.

SYSTEM also displays `health.*` (predicate includes it) — the infra story is incomplete without
connection/reader health, and OPERATOR shows the same records with different framing. Deliberate
overlap, one source.

### 2.6 OPERATOR ruling: passive-plus (active reconciliation rejected)

**Ruling: OPERATOR = severity + health transitions. No per-decision intent-vs-outcome
reconciliation engine.**

Evidence that active reconciliation is impossible without new machinery — none of the four output
paths can observe its own effect [all confirmed by direct read]:

- **MIDI (laser):** `MidiOutput.trigger()` returns *enqueue* success only; the actual
  `outport.send()` is fire-and-forget on the sender thread; failures surface asynchronously as
  degraded-state counters (`midi_output.py:114-142`, `:238-303`, `:429-438`). No device ack exists.
- **DMX (Enttec):** `put_frame()` returns `None`; serial write errors are counters + WARNING on the
  worker thread (`enttec_dmx_pro.py:158-161`, `:208-218`). Write-only hardware; the widget even
  autonomously re-transmits the last frame after a host kill (`:8-16`) — software cannot see it.
- **Govee cloud:** HTTP status *is* known on the sender thread (`govee_runtime_sender.py:470-494`)
  but is aggregated into counters and a circuit breaker, severed from the originating look by the
  queue boundary (`govee_scene_adapter.py:164` returns True at enqueue). Correlating it back
  per-decision would require threading decision identity through the queue and worker — new
  machinery.
- **Govee LAN (realtime):** non-blocking UDP `sendto`; a True return means "handed to the OS"
  (`govee_realtime_transport.py:133-147`). Delivery/apply is unknowable. The one existing
  "reconcile" (`reconcile-reactivate`, `govee_realtime_runner.py:230-240`) is open-loop re-assertion
  on a timer, not observation.
- **OS2L/SoundSwitch:** one-way TCP; "success" = bytes queued; disconnects detected lazily on the
  next failed send (`osl_output.py:120-149`). SS never acks cue application
  (and per operator memory, SS's UI shows nothing but VDJ connection status).

Building read-back (MIDI echo devices, DMX RDM, Govee state polling, SS log scraping) is exactly
the over-engineering this overhaul exists to delete, for a solo rig whose fallback is "open
SoundSwitch by hand." Brandon's stated workflow already assigns the reconciliation job to his eyes:
PERFORMANCE says what should be happening; he looks up.

**What OPERATOR does instead — surface every failure signal the code already computes, plus the
three that are computed but currently silent:** the `health.*` table in §2.4. That yields exactly
the detectable-failure story the spine asked for ("laser scene issued but no MIDI acknowledgement
followed" is not observable; "laser backend entered degraded: send_error" *is*, and today it
scrolls away as one WARNING among noise — or, for Govee cloud, never appears at all). Quiet when
healthy: zero records match the predicate; the viewer strip shows green + "all quiet since HH:MM".

### 2.7 The viewer — `bridge_view.py`

**Zero new dependencies** [confirmed: pyproject runtime deps are mido, pyobjc-Cocoa, pyrekordbox,
python-osc, zeroconf — no TUI lib anywhere]. Stdlib `curses` (present in the Homebrew Python the
watcher pins, `scripts/ss_bridge_watcher.sh:15`). One file at repo root; rendering/parsing helpers
are pure functions so tests never need a terminal. Read-only consumer: opens the current run file,
reads to EOF, then follows by polling (~100 ms); reopens on inode change. It can never write to the
stream or touch the bridge — a viewer crash is cosmetically annoying and nothing else, and the
watcher reopens it (§2.8).

**Screens** (number keys switch; the lens predicates are §2.1 verbatim):

```
┌ SHOW ────────────────────────────────────────────────────────────────┐
│ D1 ● 128.3bpm  phrase=chorus  laser=strobe_sync  led=drop_wash       │  ← sticky header:
│ palette=neon_night  rgb=realtime_active  master=1  last rec 0.4s ago │    latest perf.heartbeat
├──────────────────────────────────────────────────────────────────────┤
│ 21:14:03.5  D1 ▶ deck   switch 2→1 (fader_top)                       │  ← PERFORMANCE feed
│ 21:14:03.5  D1 ▶ drop   crossing type=main blackout=armed @b128      │    (perf.* only,
│ 21:14:03.5  D1 ▶ laser  strobe_sync (drop_crossing) @b129            │     newest at bottom,
│ 21:14:03.6  D1 ▶ led    look=drop_wash role=drop via=realtime        │     auto-follow)
│ 21:14:03.6  D1 ▶ ss     midi-refire beat=128 src=phrase_anchor       │
├─ OPERATOR ───────────────────────────────────────────────────────────┤
│ ✓ all quiet since 20:58:12                                           │  ← alert strip: green when
└──────────────────────────────────────────────────────────────────────┘    empty; last 3 WARN+/health
                                                                             + red flash + bell on ERROR
```

- **1 SHOW** (default): header (latest `perf.heartbeat` + stream-staleness age) + PERFORMANCE feed
  + OPERATOR strip. This is the mid-set screen; it answers "what should be happening" and "is
  anything broken" in one glance without keys.
- **2 OPERATOR**: full health/error feed with per-category last-state summary at top (one line per
  `health.*` category: current state + when it last changed).
- **3 SYSTEM**: infra feed.
- **4 DEBUG**: everything, with `/` filter (substring match on `cat`/`msg`, plus `deck=N` and
  `cat=prefix` tokens), `c` clears.
- **Global keys:** `space` freeze/follow (buffering continues while frozen), `j`/`k` scroll when
  frozen, `q` quit. Repaint ≤10 Hz and on keypress; per-lens ring buffers (`deque(maxlen=2000)`).
- **Alerting:** a new ERROR-level record flashes the header bar red for 3 s and rings the terminal
  bell — Terminal.app bounces the Dock icon when unfocused, which is the actually-useful mid-set
  alert. The OPERATOR strip keeps the last WARN+/health lines visible on every screen so an alert
  can't scroll away.
- **Glanceable grammar for PERFORMANCE lines:** `HH:MM:SS.s  D<deck> ▶ <surface>  <value> (<reason>) @b<beat>`
  — deck first (which side of the booth), surface second (where to look), value third (what to
  expect), reason parenthesized, beat last. Rendered from `data`, so wording improves without
  touching the bridge.
- **Stream staleness:** header shows age of the newest record; yellow >5 s, red >15 s (the
  heartbeat guarantees ≥1 record/2 s from a healthy bridge). This is the honest liveness check for
  "bridge hung / writer died" — detectable from the read side with zero bridge-side machinery.

### 2.8 Files, retention, launch integration

**Operator decisions folded in 2026-07-04:** (1) log location must fit the USB portability
workstream (AWR-122); (2) one window, not two, in manual mode. **Same-day operator update:
AWR-122 and the cross-platform project (AWR-120/AWR-124) are parked until further notice — nothing
in this build depends on, waits for, or implements anything for either. The `RBSS_RUNTIME_DIR`
support below is three dormant lines with the default path as the live behavior; it simply means
the parked projects inherit a compatible log surface whenever (if ever) they resume.**

- **Directory — one resolver, USB-aware.** `bridge_log.py` (and the viewer, via the same function)
  resolves the log dir as: **`$RBSS_RUNTIME_DIR/logs/` when `RBSS_RUNTIME_DIR` is set, else
  `~/Library/Logs/rb_ss_bridge/`**. `RBSS_RUNTIME_DIR` is not invented here — it is exactly the
  knob the USB launcher design already names for relocating all fixed-path runtime state
  (AWR-123 F8, `docs/plans/active/usb_bridge_launcher_design.md:159-162`); this design adopts it
  for logs from day one, so the bundle's temporary mode ("stick is a key": payload staged to
  `$TMPDIR/rbss-<version>/`, all run state under that prefix, wiped by End Set) gets correct log
  placement by setting one env var. On Brandon's Mac (source runs, no env set) logs land in
  `~/Library/Logs/rb_ss_bridge/` — survives reboots, standard location, easy for agents.
- **Files:** one per bridge run, `bridge-YYYYMMDD-HHMMSS.jsonl`, plus a `current.jsonl` symlink in
  the log dir. Retention: newest **20** runs, pruned at listener init. The `/tmp/bridge-events.jsonl`
  convenience symlink is created **only in the default-dir case** — under `RBSS_RUNTIME_DIR` it
  would add another fixed /tmp path to the USB End-Set cleanup list, defeating the one-prefix rule.
- **USB post-mortem story (interface for AWR-122, not implemented here):** a run's diary is one
  self-contained file; "carry the post-mortem home" = copy the `logs/` dir to the stick, a natural
  step for AWR-122's explicit End Set action. Without that export, guest-Mac diaries are wiped by
  End Set — deliberate, that's the no-trace goal. AWR-122 owns that flow decision; this design only
  guarantees the copy-one-dir interface.
- **Watcher integration — one window in both modes** (shell-only change, W7):
  - `open_monitor` (`scripts/ss_bridge_watcher.sh:223-232`): the Terminal command swaps
    `tail -n 100 -F /tmp/bridge.log` → `"$PYTHON" "$REPO_ROOT/bridge_view.py"`; the
    `RBSS_BRIDGE_MONITOR` title marker and `close_monitor` logic stay. `monitor_open` (`:105-108`)
    matches `bridge_view.py` instead of the tail pattern.
  - **Manual mode collapses onto the auto launch path.** `start_manual_terminal_bridge`
    (`:154-165`) is deleted; manual mode starts the bridge via the same `start_bridge` (background,
    stdout → `/tmp/bridge.log`) and opens the same single viewer window. This kills a live defect
    for free: the manual path's hand-copied env list has already drifted from the auto path's
    (missing six `RBSS_LED_*` flags — found by the AWR-122 review,
    `usb_bridge_launcher_design.md:58-63`), and it removes the manual-mode `tee` pipeline, which
    was the one remaining stdout-pipe stall risk on the hot path (§2.10). Manual mode keeps its
    lifecycle meaning: no crash-restart backoff, watcher exits when the bridge exits.
  - **Closing the viewer window no longer stops the bridge** (it can't — the viewer is a
    crash-isolated reader; a display crash must never end the show, and "window closed" is
    indistinguishable from "viewer crashed" from the watcher's side). Stopping the bridge is the
    menubar's job, which it already does (`bridge_menubar.py` start/stop). The watcher reopens a
    missing viewer window within ~3 s, same self-healing as today's tail monitor. [Behavior change
    from today's manual mode, consequence of the operator's one-window decision — flagged in §4.]
  - **Bundle mode (AWR-122) integration point:** the bundled launcher opens no Terminal at all and
    plans "menubar status/log access" instead (`usb_bridge_launcher_design.md:80-81`). The viewer
    is stdlib-only and reads the log dir via the shared resolver, so a later `--run-viewer`
    entrypoint / menubar "Open Viewer" item satisfies that — AWR-122's milestone, not this build's.
- **Other processes:** `streamdeck_midi.py`, the pad web tools, and the menubar keep their own
  stdout logs (`/tmp/streamdeck.log`, plists) — out of scope; the stream is the *bridge process's*
  event log. (Their actions reach the stream anyway at the bridge boundary: `sys.cmd` +
  `perf.override` records.)

### 2.9 Teardown ledger

**Dies (bridge side):**

| Machinery | Where | Evidence it's safe |
|---|---|---|
| Control-file watcher thread + `reload_from_file` + `/tmp/rb_ss_bridge_v2_logging.json` + preset `docs/setup/logging_live_watch.json` | `logging_manager.py:505-531,459-481` | nothing in the repo writes the control file; operators manually `cp` a preset [census confirmed]. Live filtering is now the viewer's job — the bridge stops filtering its own output |
| Env-var filter maze: `BRIDGE_LOG_MODULES/DECKS/EVENTS/DIAG/ANOMALIES/JSON/CONTROL` + `reload_from_env` + `_DIAG_MODULES` + SIGHUP reload | `logging_manager.py:244-270,434-457`; `__main__.py:1899-1905` | nothing in the repo sets any of them [census confirmed]; the watcher launch path sets none |
| Runtime filter: `RuntimeLogFilter`, `should_emit`, `set_runtime_filter` | `logging_manager.py:189-197,405-429` | filtering moves read-side; ERROR-always-passes semantics preserved trivially (viewer shows WARN+ in OPERATOR regardless of filter) |
| Anomaly engine (1 rule) + `anomaly` contextvar + `detect_anomaly` per event | `logging_manager.py:533-543`; `state_manager.py:1088` | one caller, zero tests, one rule since inception |
| Remediation hints + `log_error` wrapper | `logging_manager.py:290-299,545-566` | 3 call sites → plain `log.error(..., exc_info=)`; hints table is stale prose in code |
| `LogStats` + `EventSample` + latency stamping + `record_transition` sites + `log_stats` | `logging_manager.py:98-186,376-383`; `state_manager.py:1538,1725,1988,2392` | zero tests; only surfaced via SIGHUP dump; the profiler covers timing, the stream covers event history |
| `JsonFormatter`, `_BridgeFormatter`, `install_record_factory`/`BridgeLogRecord`, `annotate`/`indent` | `logging_manager.py:51-95,273-284,385-403` | replaced by the one listener serializer; contextvars attach in the handler instead of a record factory |
| `_ColorFormatter` + hand-maintained pattern→color table | `__main__.py:107-305` | presentation moves to the viewer; the color *conventions* (green=applied, orange=retry, red=stop) carry into the viewer's level/cat palette |
| `LoggingEventQueue` (as a class) | `logging_manager.py:200-241` | replaced by ~10-line `stamp_trace(ev)`; latency stamping dies with LogStats |
| `diagnostics.enable_debug` + `is_debug` | `diagnostics.py:56-74` | absorbed by `BRIDGE_DEBUG` handling in `bridge_log.init()`; `DriftDetector` **stays** (it's detection, not logging) |
| `[BEAT]` text line | `runtime_status.py:216-233` | becomes `perf.heartbeat` (§1.5) |

**Survives:** `bridge_fmt.py` wholesale (`elapsed`, `short`, `log_once`, `log_throttled`,
`log_changed` — the noise-gating primitives are load-bearing and tested); deck+trace contextvars +
trimmed `event_scope`; `BRIDGE_DEBUG` + `BRIDGE_LOG_LEVELS`; the tick profiler (`RBSS_SM_PROFILE`);
`StatusWriter`/status JSON/command reader untouched; `laser_decision_log.py` ring untouched;
`session_recorder.py` untouched (different artifact: high-rate session capture vs. event log).

**Tests affected** [census confirmed]: `test_logging_diag_coverage.py` pins `_DIAG_MODULES`,
`should_emit`, `reload_from_file` + the preset — dies with the features, replaced by `bridge_log`
tests; the two source-string asserts on the control watcher
(`test_main_mixer_authority_wiring.py:104`, `test_soundswitch_pack_startup.py:374`) are updated to
assert the new init/shutdown calls; `test_bridge_fmt_rate.py` unchanged. Anomaly, hints,
JsonFormatter, LogStats have **zero** test coverage — deletable without breakage.

**Net ledger:** `logging_manager.py` (596) + `__main__.py` color/setup block (~200) +
`diagnostics.py` debug plumbing (~25) ≈ **820 lines die**; `bridge_log.py` ≈ **250 lines** arrives.
Bridge-side pipeline: 3 formatters → 1 serializer; 9 env vars → 2; 6 contextvars → 2; 1 config
thread → 1 writer thread; runtime filter → none (read-side). The viewer (~450 lines) is new but
lives in a process that cannot touch the bridge. Simpler to reason about: the entire bridge-side
contract is "loggers → one handler → bounded queue → writer thread → one file."

### 2.10 Live-safety invariant, end to end

**What the bridge process does on the hot path, exhaustively:** level check → %-merge message →
read 2 contextvars + 2 clocks → build one dict → `put_nowait` into a bounded in-memory queue
(drop + count if full). **What it never does on the hot path:** open/write/flush any file, format
JSON, write to any stream or socket, take any lock a slow consumer can hold, sleep, or raise.

This is **strictly safer than today**, not merely equal: today every hot-path log line runs
`StreamHandler.emit` → `stream.write() + flush()` to stdout **under the handler lock**, and in
manual mode stdout is a pipe through `tee` [confirmed `__main__.py:298`;
`scripts/ss_bridge_watcher.sh:161`] — a stalled reader can back-pressure the 200 Hz loop. The
overhaul removes that class entirely. Two additional hot-path fixes ride along (Phase 3, W4):
the unconditional per-event payload dict-comprehension at `state_manager.py:1114-1115` gets an
`isEnabledFor(DEBUG)` guard [confirmed it runs regardless of level today], and the per-event
`detect_anomaly`/`stats` calls disappear with their features — the event drain gets *cheaper* per
event than today.

Failure modes, stated honestly: **queue full** (pathological DEBUG storm) → records drop, counter
reported via `sys.log`, loop unaffected — bounded memory, no blocking. **Writer thread dies** →
records accumulate to the bound then drop; stderr mirror stops; detection is the viewer's staleness
indicator (heartbeat guarantees a fresh record every 2 s from a healthy pipeline) — accepted for a
solo rig; no supervisor thread. **Viewer dies** → nothing: separate process, file keeps being
written, watcher reopens it. **Unclean bridge death** → file is line-buffered JSONL; at most the
tail line is truncated (viewer tolerates a partial last line); no footer record is itself the
post-mortem signal. **Shutdown** → `_shutdown` stops the listener with a 2 s drain-join (same
pattern as `command_reader.join(timeout=2.0)`, `__main__.py:1876`).

Unchanged invariants (AGENTS.md §6): `StateManager` remains the only `DeckState` writer; events
stay immutable (trace stamping writes only the payload's `__trace_id` key exactly as today);
`ANLZ_PATH`-before-`TRACK_LOADED` untouched; secrets redaction preserved (the `_redact` scrub moves
into the listener, and the RW-5 rule — pack errors expose exception categories only — is a
call-site property this design does not alter).

---

## 3. Build decomposition (Phase 3 order, migration plan)

Ground rules the decomposition already respects: Fable-family subagents implement (operator
exception, §1 header); the suite stays green after every chunk; fresh-context verifiers gate each
chunk (plan before code, diff after); **hard live boundary** — software and tests only, no bridge
restart, no hardware, Brandon runs `bridge-verify` after adopting any chunk live.

**Contract first (AGENTS.md §7):** W0 extends the existing `logging_visibility` contract
(`docs/agents/change_contracts.yml:68-94`) before any code: `code_globs` += `bridge_log.py`,
`bridge_view.py`, `scripts/ss_bridge_watcher.sh`; `key_symbols` += `emit`, `perf`, `health`;
`tests` updated to the new test module names as they land. Its existing forbidden assumption
("hot-path logging helpers must not add blocking I/O or per-frame INFO spam") is exactly this
design's lock. The `runtime_commands` contract also names `docs/subsystems/logging.md` in
`docs_update` — kept consistent in W7.

| # | Chunk | Contents | Depends on | Risk |
|---|---|---|---|---|
| W0 | Contract + doc registration | extend `logging_visibility`; register this design in the active-work registry | — | none (docs-only, hard checks green) |
| W1 | `bridge_log.py` + tests | handler, queue, listener, `emit`/`perf`/`health`, `event_scope`, `stamp_trace`, excepthooks, run files + retention, redaction. Pure seams: record-build fn, serializer fn, drop behavior with a tiny queue, header/footer records | W0 | none (additive, unwired) |
| W2 | Flip the wiring | `__main__.py`: `bridge_log.init()` replaces `basicConfig`/`LOG.configure`/`reload_from_env`/`_ColorFormatter`/control-watcher start-stop/SIGHUP-stats; `_shutdown` drains the listener; update the 2 source-string tests | W1 | **highest** (operator-visible output change); single isolated commit = single-revert rollback |
| W3a-d | `perf.*` emits, one subsystem each: (a) laser, (b) LED+palette, (c) autoloop+SS+scripted, (d) deck+drop+override+heartbeat | add emits at §2.4 sites; delete the absorbed duplicate lines in the same diff | W2 | low, mechanical; 4 independent chunks — parallelizable across subagents after W2 |
| W4 | `health.*` + demotions + hot-path hygiene | recategorize existing WARNINGs; add the 4 silent-signal emits (govee circuit, rt send-error, rb_memory queue swallow, thread-liveness try/finally); demote `[MIDI] tx` INFO→DEBUG (`midi_output.py:266,335,350` — 2+ lines per fired scene today); guard `state_manager.py:1114` | W2 | low |
| W5 | Teardown | delete `logging_manager.py` (state_manager/filepath_resolver imports → `bridge_log`), `diagnostics` debug plumbing, preset JSON; rewrite `test_logging_diag_coverage.py` → `test_bridge_log.py` | W3, W4 | medium (wide mechanical diff, no behavior) |
| W6 | `bridge_view.py` + tests | curses TUI per §2.7; pure helpers (`parse_record`, `lens_of` — incl. an explicit test that a CANDIDATE/REJECT-style DEBUG record routes to MAX DEBUG only —, `format_line`) | W1 (schema only) | none for the bridge; **parallelizable with W2-W5** |
| W7 | Watcher + docs | watcher swap (§2.8); rewrite `docs/subsystems/logging.md`; update status matrices, software test inventory, tests card per contract; delete stale doc sections (control file, env maze, color table) | W2, W6 | low |

**Migration rule for the 41 stdlib files (the "~46-file" plan, made concrete):** default = **no
change**. A file is touched only if it (a) hosts a §2.4 emit site (≈10 files), (b) has a duplicate
line absorbed by a `perf.*` record (same ≈10), (c) needs a level demotion per the validated lesson
(`midi_output.py`; spot-audit in W4 for any remaining per-candidate INFO), or (d) imports
`logging_manager` (3 files, W2/W5). Everything else migrates by definition: its records flow into
the stream with `cat` = logger name and route via §2.1. No big-bang rewrite exists in this plan.

Each W-chunk maps 1:1 onto a Part B task group in the Phase 2 spec (codex-spec skeleton); §2.10 is
Part C verbatim; the pure seams in W1/W6 are Part D; the contract's `docs_update` + hard checks +
`python3 -m unittest discover tests` are Part E. That translation is mechanical.

---

## 4. Spec-readiness verdict: **READY**

The two operator gaps from the first draft were answered 2026-07-04 and are folded into §2.8:

1. **Log location (resolved):** USB-aware single resolver — `$RBSS_RUNTIME_DIR/logs/` when set
   (the AWR-122/AWR-123-F8 knob, adopted here rather than invented), else
   `~/Library/Logs/rb_ss_bridge/`; 20-run retention; `/tmp` symlink only in the default case.
2. **Window count (resolved):** one window in both modes; the viewer *is* the monitor window;
   `start_manual_terminal_bridge` dies; **consequence the operator should be aware of:** closing
   the viewer window no longer stops the bridge (menubar stop does, as in auto mode today) —
   accepted as the price of one-window + crash isolation, and it removes the manual-path env drift
   and the `tee` stall risk.

Non-blocking pins Phase 2 must do (normal spec work, listed so they aren't lost):

3. **Re-pin every §2.4 line number against then-current HEAD** — concurrent sessions are editing
   these files; functions are the anchors, lines will have drifted.
4. **`perf.drop` emit site** — confirm the exact smart-rearm crossing consumption point and the
   fields available on `smart_drop_result` (`state_manager.py:3709-3719` region at `02250de`);
   the drop *type* taxonomy (main vs continuation) is future work per operator memory — the record
   carries `type` as free text for now. [unknown: final type vocabulary]
5. **Coordination note, not a blocker:** AWR-122 and AWR-120/AWR-124 are parked until further
   notice (operator, 2026-07-04) — no coordination is needed or expected during this build. If a
   resumed AWR-122 ever renames or reshapes `RBSS_RUNTIME_DIR`, the log-dir resolver is one
   constant in `bridge_log.py`; the End-Set "copy diaries to stick" export is that project's flow
   to spec, at pickup, against the copy-one-dir interface (§2.8).
6. **Explicitly out of scope, named to prevent drift:** no read-back/reconciliation machinery
   (§2.6); no changes to `StatusWriter`/commands/menubar; no session_recorder changes; no
   streamdeck/pad logging changes; `sys.tick` unconditional overrun counter is optional — include
   or drop at spec time, either is fine.

Falsifiable success criteria, self-checked: simpler than today — §2.9 names ~820 deleted lines and
the machinery counts; four lenses each have a predicate, an example line, and a routing rule
(§2.1); the hot path is enumerated positively and negatively (§2.10); the candidate-spam class is
dead by predicate, not discipline (§2.1); the decomposition is chunked, ordered, parallelizable,
and maps mechanically onto the codex-spec skeleton (§3); no code, config, tests, or runtime were
touched in this phase — this document is the only artifact.
