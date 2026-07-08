# Implementation Spec - Govee Frame Engine Process (lift runner+renderer+transport into a bridge-owned child process)

status: planned
last_verified_commit: 06d263d
owner: operator (Brandon) via Claude Fable 5 orchestration session 2026-07-08
registry: AWR-146

Execute tasks **in order, one commit per task**. Every file:line below was verified against HEAD
`06d263d` (post-AWR-145 Tasks 0-5) on 2026-07-08. Labels: [confirmed] = read in current code / ran
on this machine / operator-observed, [assumed] = inferred, [unknown] = stated where load-bearing.

> You may be in a dirty git worktree shared with other agents and an auto-sync hook. NEVER revert
> existing changes you did not make. Commit ONLY by explicit file paths (`git add <path> <path>` /
> `git commit -- <path>`), never `-a` or `add -A`. If you notice unexpected changes you didn't
> make, leave them alone. NEVER use destructive commands (`git reset --hard`, `git checkout --`,
> `git clean`). Work directly on `main`; no branches, no worktrees.

> Touch ONLY the files this spec lists. If a change seems to need a file outside the list, STOP
> and report instead of editing it.

## Part A - Context & Root Cause (verified; read, do not implement)

The Govee realtime frame path (`GoveeRealtimeRunner` thread → `GoveeFrameRenderer` →
`GoveeRealtimeTransport` UDP) lives inside the bridge process today and gets starved by the rest
of the bridge. Measured on this machine 2026-07-08 with the production classes:

1. [confirmed, measured] The trio at 60 segments in a clean foreground process delivers **60.0 fps**
   (dry-run and localhost UDP); the renderer costs 0.03-0.54 ms/frame. The live bridge and the
   standalone LED Pad — both long-running faceless processes — deliver only ~28-29 fps, decaying
   to ~16.5 fps when the bridge is busy, with dips to 1-7 fps during reader memory scans (GIL
   starvation: the 628 ms RBMEM scans hold the GIL; no scheduling fix inside one process can cure
   that). Under `taskpolicy -b` (darwin background band) the same code drops to 20.5 fps because
   `time.sleep(1/60)` overshoots to ~88-95 ms; per-thread QoS and an NSActivity assertion do NOT
   rescue a darwin-bg process. **Which macOS mechanism demotes the long-running faceless
   processes is [unknown] — the design controls the band explicitly and self-measures instead of
   depending on knowing.**
2. [confirmed] The process boundary is clean at the runner's edge: `govee_frame_renderer.py` and
   `beat_sync_engine.py` import stdlib only (zero first-party imports; renderer registries are
   module-level constants rebuilt on import — `govee_frame_renderer.py:932-996,1796-1864`).
   `govee_realtime_transport.py` imports stdlib only (`base64, json, socket, threading`, lines
   4-7), owns one non-blocking UDP socket (`:51-52`), all sends fire-and-forget (`:133-147`).
   `govee_realtime_runner.py` imports `.beat_sync_engine`, `.govee_frame_renderer`, `.led_models`
   (BeatAnchor), `.bridge_fmt`, `.bridge_log` (lines 10-20).
3. [confirmed] The bridge touches the runner in exactly two places: `LEDDispatchCoordinator`
   (duck-typed calls: `set_desired`, `fire_trigger`, `request_activate_assert`,
   `request_brightness`, `emergency_stop`, `force_deactivate`, `status`, `stop` —
   `led_dispatch_coordinator.py:85,150-154,168,202,212,227,235`) and `__main__.py` (construct
   `:566-571`, wire into coordinator `:572-578`, `set_beat_provider(sm.get_active_beat_anchor)` +
   `start()` `:1154-1156`, `stop()` at shutdown `:1760-1761`). `tools/led_pad_playback.py` and
   `scripts/direct_rt_groove_chase.py` construct their own runner instances and are untouched.
4. [confirmed] The beat anchor is `led_models.BeatAnchor` (`led_models.py:277-283`): 6 scalars
   `deck:int, abs_beat_pos:float, bpm:float, captured_monotonic:float, playing:bool,
   permitted:bool`. The runner polls the provider each tick on its own thread
   (`govee_realtime_runner.py:220-224`) and extrapolates
   `abs_pos = anchor.abs_beat_pos + (now - anchor.captured_monotonic) * bpm/60` (`:315-318`).
5. [confirmed, ran on this machine 2026-07-08] `time.monotonic()` is `mach_absolute_time()`-based
   (`time.get_clock_info('monotonic').implementation == 'mach_absolute_time()'`) and comparable
   across processes on this Mac (parent/child delta 2 ms including spawn latency). Anchor floats
   and `EffectSpec.applied_monotonic` cross the process boundary unchanged.
6. [confirmed, ran on this machine 2026-07-08] Band-control calls all succeed from Python:
   `libc.setpriority(4 /*PRIO_DARWIN_PROCESS*/, 0, 0)` returns 0 (clears darwin-bg);
   `pthread_set_qos_class_self_np(0x21 /*QOS_CLASS_USER_INTERACTIVE*/, 0)` returns 0; pyobjc
   `Foundation` is installed and `NSProcessInfo.processInfo().beginActivityWithOptions_reason_`
   returns a non-null token. **Gotcha [confirmed]: after `import Foundation` the interpreter can
   hang at normal exit — the child must terminate with `os._exit()` after teardown.**
7. [confirmed] The strip HOLDS its last frame when frames stop (fire-and-forget UDP, no timeout
   dark). Going dark is always an explicit act: `blackout()` (all-zero frame,
   `govee_realtime_transport.py:107-108`) works only in razer mode; `set_brightness(0)` (`:84-91`)
   works in any device mode. Fail-dark therefore requires a live code path, not process death.
8. [confirmed] AWR-145 landed (commits `d659354..06d263d`): razer keepalive
   (`RAZER_KEEPALIVE_S=2.0`, `govee_realtime_runner.py:35,245-276`), `request_activate_assert`
   (`:118-125`), `request_brightness` (`:127-135`), brightness-0 on pure-emergency teardown
   (`:453-478`), coordinator asserts on takeover/blackout (`led_dispatch_coordinator.py:154,202`),
   `restore_brightness` (`:206-212`), policy dispatch retry, pad auto-stop. All of it lives in the
   runner/coordinator and **moves wholesale or is forwarded — no AWR-145 logic is reimplemented.**
9. [confirmed] The pad↔bridge mutual exclusion rides on `/tmp/rb_ss_bridge_v2_status.json`
   freshness written by the bridge's StatusWriter thread (`runtime_status.py:17-18,139-147,173`)
   — the bridge process stays the owner-of-record; a bridge-owned child changes nothing in that
   protocol. The in-process `GoveeOwnerStateMachine` (`govee_owner_state.py:8-41`) arbitrates
   cloud vs realtime inside the bridge and is untouched.
10. [confirmed] The pad already runs this exact trio in its own process with bridge_log
    **uninitialized** (no `bridge_log.init()` call anywhere under `tools/led_pad*` or
    `scripts/led_pad.py`) — the runner's `bridge_log.thread_guard`/`bridge_log.health` calls
    degrade gracefully without the file sink. The child does the same: never call
    `bridge_log.init()`; child stderr is inherited from the bridge (watcher window).

Root cause of the fps problem: **same-process GIL contention plus an [unknown] scheduling-band
demotion of long-running faceless processes.** A child process cures the GIL half by construction
and makes the band half controllable + measurable.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `govee_frame_engine.py` (new), `govee_frame_engine_client.py` (new),
  `govee_realtime_runner.py` (one additive constructor arg), `__main__.py` (LED startup wiring),
  `led_dispatch_policy.py` (status-sanitize whitelist only), `docs/agents/change_contracts.yml`
  (Task 1 only — `tools/check_agent_contracts.py` requires contract-named files to exist, so the
  contract edit must land in the SAME commit as the new files; mirror in
  `docs/agents/change_contracts.md` only if that file enumerates the same glob list), the tests
  named in Part D, and the Part E docs. The orchestrator (not you) adds the AWR-146 registry row
  before you start; verify it exists (`rg -n "AWR-146" docs/status/active_work_registry.md`) and
  STOP if it does not.
- Additionally touchable for the NUMBERED task that names them and nothing else:
  `led_dispatch_coordinator.py` (Task 6), `led_models.py` + `led_config.py` +
  `config/led_look_director.example.json` (optional Task 7, only if its precondition proves out).
- Out of scope — must not change: `govee_frame_renderer.py`, `beat_sync_engine.py`,
  `govee_realtime_transport.py`, `govee_owner_state.py`,
  `govee_scene_adapter.py`, `govee_runtime_sender.py`, `govee_lan_discovery.py`, `state_manager.py`,
  `tools/led_pad_playback.py`, `runtime_status.py`, laser/SoundSwitch/reader subsystems, transport
  packet formats, `bridge_log.py`.
- Behavior that must not change: every AWR-145 guarantee (keepalive cadence, assert-on-takeover,
  brightness backstop, cloud-handoff-never-dims, edge-activate brightness 100, dispatch retry,
  pad auto-stop); cloud dispatch stays in-bridge exactly as today; the operator-blackout cloud
  path; the coordinator's public surface (it keeps calling the same duck-typed methods).
- Error handling: blackout paths fail toward dark, never "assume lit"; a dead/hung child is
  respawned, never silently ignored; IPC send failures on the anchor stream drop the anchor (next
  arrives in 20 ms), IPC send failures on commands NEVER drop the command (queue + retry, escalate
  to kill+respawn if stuck >2 s). No new broad try/except; the only tolerated narrow fallback is
  the pyobjc import (log a WARNING and continue with the other two band levers).
- The 200 Hz push loop and all StateManager threads gain no socket/blocking I/O: every client
  method called by the coordinator only mutates state under a lock; all IPC and process I/O runs
  on the client's own thread (same discipline as today's runner methods, AGENTS.md §6).
- No new config keys, no new env flags. Rollback is `git revert` of these commits + menubar
  restart.

### Task 1 - `govee_frame_engine.py` (new): protocol + child host (+ contract, same commit)

In this same commit, extend the `led_govee` contract (`docs/agents/change_contracts.yml:102-123`):
add `govee_frame_engine.py` and `govee_frame_engine_client.py` to `code_globs`, and
`FrameEngineHost` and `GoveeFrameEngineClient` to `key_symbols`; run
`python3 tools/check_agent_contracts.py` before committing.

One flat repo-root module (matches the flat layout, AGENTS.md §4) containing:

1. **Protocol** (pure functions, top of file):
   - `encode_msg(msg: dict) -> bytes`: `json.dumps(msg, separators=(",", ":")).encode() + b"\n"`.
   - `decode_buffer(buf: bytes) -> tuple[list[dict], bytes]`: split on `\n`, JSON-parse complete
     lines, return (messages, remainder). A malformed line logs WARNING and is skipped (do not
     kill the stream over one bad line).
   - Message types, parent→child: `{"t":"init", "dry_run":bool, "ip":str, "port":int,
     "segments":int, "fps":int, "grace_s":float, "header_bytes":..., "stretch":...,
     "activate_pt":str, "deactivate_pt":str}` (field values exactly as `__main__.py:530-571`
     passes them today — read that block and mirror it); `{"t":"anchor", "a": null | {"deck":int,
     "abs_beat_pos":float, "bpm":float, "captured_monotonic":float, "playing":bool,
     "permitted":bool}}`; `{"t":"set_desired", "spec": null | {"effect_name":str, "params":dict,
     "seed":int, "applied_monotonic":float, "sync_mode":str, "beat_division":float}}`;
     `{"t":"fire_trigger"}`; `{"t":"activate_assert"}`; `{"t":"brightness", "value":int}`;
     `{"t":"emergency_stop"}`; `{"t":"force_deactivate"}`; `{"t":"shutdown"}`.
   - Child→parent: `{"t":"hb", "pid":int, "achieved_fps":float, "streaming":bool,
     "fps_degraded":bool, "status":{...runner.status()...}}` every `HEARTBEAT_S`.
   - Constants: `HEARTBEAT_S = 1.0`, `ANCHOR_STALE_S = 0.5`, `SELECT_TIMEOUT_S = 0.25`.
2. **`FrameEngineHost`** class — testable with injected fakes, no real sockets/processes:
   `__init__(self, conn, *, transport_factory, runner_factory=GoveeRealtimeRunner, time_fn=time.monotonic)`
   where `conn` is any object with `recv(n) -> bytes` (b"" = EOF), `send(bytes) -> int`, `fileno()`.
   - Holds `self._anchor: BeatAnchor | None` under a `threading.Lock`; method
     `beat_provider() -> BeatAnchor | None` returns the stored anchor, or `None` when
     `time_fn() - anchor.captured_monotonic > ANCHOR_STALE_S` (a bridge that stops streaming
     anchors must read as "not playing" within half a second — pause/permission changes propagate
     as explicit `null` anchors anyway; the staleness guard only covers a hung parent).
   - `handle_message(msg: dict) -> bool` (False = shutdown requested): `anchor` → store
     (`null` → `None`); `set_desired` → build `EffectSpec(**spec_fields)` (params dict as-is; JSON
     already normalized tuples to lists — see Part D test) and call `runner.set_desired(...)`,
     `null` spec → `runner.set_desired(None)`; `fire_trigger`/`activate_assert`/`brightness`/
     `emergency_stop`/`force_deactivate` → call the matching runner method; `shutdown` → return
     False. Unknown `t` → WARNING, continue.
   - `run(self) -> None`: on entry build transport via `transport_factory(init_msg)` from the
     first message (which MUST be `init`; anything else → log ERROR, return), then
     `transport.deactivate()` once when `not dry_run` (mirrors `__main__.py:565`), build runner
     `runner_factory(transport, GoveeFrameRenderer(), segments=init.segments, fps=init.fps,
     grace_s=init.grace_s, on_thread_start=<qos hook, see Task 2>)`, `set_beat_provider(self.beat_provider)`,
     `runner.start()`. Then loop: `select([conn], [], [], SELECT_TIMEOUT_S)`; on readable,
     `recv(65536)`; EOF (`b""`) → break; feed `decode_buffer`, dispatch each message, stop looping
     if any returned False. Every `HEARTBEAT_S`, send one `hb` message (non-blocking; on
     BlockingIOError skip this heartbeat). On loop exit (EOF, shutdown, or exception):
     `runner.stop()` — which sends `blackout() + deactivate() + close()`
     (`govee_realtime_runner.py:159-179`), the same dark-on-shutdown the bridge performs today;
     deliberately NO brightness-0 here (a healthy cloud look must survive a bridge restart —
     razer frames are ignored outside razer mode, brightness-0 is not).
   - fps self-measure: at each heartbeat compute
     `achieved_fps = (frame_index - prev_frame_index) / max(dt, 1e-6)` from
     `runner.status()["frame_index"]`; `streaming = status["active"]`;
     `fps_degraded = streaming and achieved_fps < 0.8 * init.fps` for 3 consecutive heartbeats
     (keep a small counter). While degraded, log one WARNING per transition (edge-triggered, not
     per-heartbeat — log discipline: high-frequency detail stays at DEBUG).
3. **Band control** — module function `raise_scheduling_band() -> dict` called from `main()`
   before building the host; returns a report dict logged once at INFO:
   ```python
   def raise_scheduling_band() -> dict:
       report = {"setpriority": False, "nsactivity": False}
       libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
       # PRIO_DARWIN_PROCESS=4: clear any darwin background band on this process.
       report["setpriority"] = libc.setpriority(4, 0, 0) == 0
       try:
           import Foundation  # pyobjc — confirmed installed on this machine
           info = Foundation.NSProcessInfo.processInfo()
           # NSActivityUserInitiated | NSActivityLatencyCritical
           global _ACTIVITY_TOKEN  # keep alive for process lifetime
           _ACTIVITY_TOKEN = info.beginActivityWithOptions_reason_(
               0x00FFFFFF | 0xFF00000000, "govee frame engine realtime frames")
           report["nsactivity"] = _ACTIVITY_TOKEN is not None
       except ImportError:
           logging.getLogger("govee_frame_engine").warning(
               "[ENGINE] pyobjc missing — running without NSActivity assertion")
       return report
   ```
   [confirmed] both calls succeed on this machine (Part A.6). Which lever actually prevents the
   faceless-process decay is [unknown] — that is exactly why `achieved_fps` is in every heartbeat.
4. **`main()`**: `argparse` with `--fd <int>` (the socketpair fd inherited via `pass_fds`);
   `logging.basicConfig(level=logging.INFO, stream=sys.stderr)`; NEVER `bridge_log.init()`;
   install a `SIGTERM` handler that requests shutdown (set an event the run-loop checks / make
   `handle_message`-equivalent path run teardown); `raise_scheduling_band()`; build
   `socket.socket(fileno=fd)`; choose `transport_factory`: `dry_run` →
   `GoveeRealtimeDryRunTransport(ip=..., port=..., segments=...)`, else `GoveeRealtimeTransport(
   ip, port=..., segments=..., header_bytes=..., stretch=..., activate_pt=..., deactivate_pt=...)`
   (exact kwargs as `__main__.py:533-564`); `FrameEngineHost(...).run()`; then `os._exit(0)` —
   REQUIRED, not optional: pyobjc can hang normal interpreter exit (Part A.6). `if __name__ ==
   "__main__": main()` so the child runs as `python3 -m rb_ss_bridge_v2.govee_frame_engine`.

### Task 2b (review round 2, 2026-07-08) - `govee_realtime_runner.py`: brightness drain must precede the emergency short-circuit

Implementer-found defect, confirmed by the orchestrator: `_tick_once` returns at the emergency
short-circuit (`govee_realtime_runner.py:241-243`) BEFORE the brightness drain, and the emergency
Event stays latched for the whole held blackout (only a non-None `set_desired` clears it). A
Task 6 `request_brightness(0)` arriving alongside `emergency_stop` therefore starves forever on
an inactive runner — the drain code runs "regardless of `_active`" but is unreachable while the
emergency latch is set. Fix: move the brightness-drain block (read+decrement under lock, then
`transport.set_brightness(value)`) ABOVE the emergency check at the top of `_tick_once`, so a
pending brightness request always sends on the next tick in ANY runner state, preserving the
exact 2-consecutive-tick resend semantics. Do NOT bake a brightness send into
`_emergency_teardown` — teardown runs every tick while the latch is held and would spam the
device at 60 Hz (or need a new idempotence flag). Required tests: (a) runner never active +
emergency latched + `request_brightness(0)` → fake transport sees `set_brightness(0)` on 2
consecutive ticks; (b) host end-to-end: `emergency_stop` message then `brightness` 0 message →
transport sees `set_brightness(0)`; (c) handoff teardown still never dims.

### Task 2 - `govee_realtime_runner.py`: one additive constructor arg

Add keyword-only `on_thread_start: Callable[[], None] | None = None` to `__init__`
(`govee_realtime_runner.py:51-61`), store it, and invoke it as the first statement inside `_loop`
(`:215`), before the `bridge_log.thread_guard` context. Default `None` = today's behavior
exactly; the bridge, the pad, and every existing test construct the runner without it. The child
passes a hook that sets the frame thread's QoS:

```python
def _qos_user_interactive() -> None:
    lib = ctypes.CDLL(ctypes.util.find_library("pthread") or ctypes.util.find_library("c"))
    fn = lib.pthread_set_qos_class_self_np
    fn.argtypes = [ctypes.c_uint, ctypes.c_int]
    fn(0x21, 0)  # QOS_CLASS_USER_INTERACTIVE — confirmed returns 0 on this machine
```

(hook lives in `govee_frame_engine.py`; the runner change is ONLY the arg + call site). If the
hook raises, let it propagate — a broken hook is a bug to surface, not swallow; the child exits
non-zero and the client respawns + logs.

### Task 3 - `govee_frame_engine_client.py` (new): in-bridge client + supervisor

`GoveeFrameEngineClient` — drop-in for `GoveeRealtimeRunner` from the coordinator's and
`__main__`'s point of view. Public surface (exact method names, all lock-and-flag, ZERO I/O on
the caller's thread): `set_beat_provider(provider)`, `start()`, `stop(timeout_s: float = 3.0) ->
bool`, `status() -> dict`, `set_desired(spec: EffectSpec | None)`, `fire_trigger()`,
`request_activate_assert()`, `request_brightness(value: int)`, `emergency_stop()`,
`force_deactivate()`.

1. `__init__(self, engine_init: dict, *, resolve_ip_fn: Callable[[], str] | None = None,
   spawn_fn=None, time_fn=time.monotonic)`. `engine_init` is the full init-message payload
   (Task 1 shape) built by `__main__`; `resolve_ip_fn` re-resolves the strip IP on respawn
   (None → keep configured ip); `spawn_fn(fd: int) -> subprocess.Popen` defaults to the real
   spawner and is injected in tests.
   Real spawner: `socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)` → child end passed via
   `subprocess.Popen([sys.executable, "-m", "rb_ss_bridge_v2.govee_frame_engine", "--fd",
   str(child_fd)], pass_fds=(child_fd,), cwd=str(Path(__file__).resolve().parent.parent),
   stdout=subprocess.DEVNULL, stderr=None)` — stderr=None inherits the bridge's stderr (child
   lines land in the watcher window); cwd = the package's parent dir so `-m rb_ss_bridge_v2.…`
   imports the same code the bridge runs; parent closes the child end after spawn, sets its own
   end non-blocking, sends the init message first.
   Why a socketpair and not loopback UDP or a pipe: SOCK_STREAM preserves command ordering
   (set_desired → fire_trigger → activate_assert must arrive in order), the kernel closes the fd
   on ANY process death including SIGKILL so each side gets EOF (this is the whole crash/orphan
   story — no heartbeat protocol needed for death detection), no ports to collide, no packets to
   lose, nothing another LAN host could inject.
2. Mirrored intent state (under `self._lock`), updated by the public methods so respawn replay
   reproduces the operator's CURRENT intent: `_desired: EffectSpec | None` (`set_desired`; a
   non-None spec also clears `_emergency` — mirror of `govee_realtime_runner.py:108-112` — AND
   clears `_handoff`: once a new look is desired, the intent is the look, not the stale
   handoff), `_emergency: bool` (`emergency_stop` sets; `force_deactivate` sets it AND clears
   `_desired` and sets `_handoff` — mirror of `:140-145`), `_handoff: bool`,
   `_brightness_pending: int | None` + repeat counter (cleared once the command message is
   written to the socket — the runner's own 2-tick repeat happens child-side),
   `_assert_pending: bool`. Every public command method: mutate mirror state + append the wire
   message to `self._outbox: deque` + set the wake `threading.Event`. NOTHING else on the
   caller's thread.
3. Client thread (`start()` spawns it, name `"GoveeFrameEngineClient"`, daemon): loop at
   `CLIENT_TICK_S = 0.02` (50 Hz, matches "tens of Hz" anchor cadence; wake early on the Event
   for command latency ≈ ms, i.e. `event.wait(CLIENT_TICK_S)`):
   a. Ensure child alive: if no child or `poll() is not None` or EOF/EPIPE was seen or
      `time_fn() - last_hb > HEARTBEAT_STALE_S (= 5.0)` with the child supposedly alive (hung
      child) → supervise: kill remnant (`terminate()`, 0.5 s, `kill()`), wait
      `RESPAWN_BACKOFF_S` (0.5 doubling to `RESPAWN_BACKOFF_MAX_S = 5.0`, reset to 0.5 after a
      child survives 30 s), re-resolve ip via `resolve_ip_fn` when set (client thread may block
      here briefly — it is not the push loop), spawn, send init, then **replay intent**: if
      `_handoff` → send `force_deactivate`; elif `_emergency` → send `emergency_stop` AND
      `brightness` 0 — the explicit brightness-0 is REQUIRED, not belt-and-braces: a fresh
      child's runner is never `_active`, so `_emergency_teardown` skips ALL transport sends
      (`govee_realtime_runner.py:456`) and a replayed emergency alone would leave the room LIT
      if the old child died before its teardown finished; the brightness request runs regardless
      of `_active` (`:275-276`); elif `_desired is not None` → send `set_desired` +
      `activate_assert` (heals razer after the gap); always also resend a still-pending
      brightness request. `respawn_count += 1`; log one INFO line. This means a child that dies
      mid-operator-blackout comes back and goes dark again, and a child that dies mid-look
      resumes the look — the room recovers either way.
   b. Sample `provider()` (the same `sm.get_active_beat_anchor` bound at `__main__.py:1155`) and
      send an `anchor` message (including explicit `null` — pause/unpermitted must propagate).
      On `BlockingIOError` drop the anchor (next in 20 ms). Anchor messages are never queued.
   c. Drain `self._outbox` in order; on `BlockingIOError` stop draining (retry next tick); if the
      oldest queued command is older than `COMMAND_STUCK_S = 2.0`, treat the child as hung →
      kill + respawn (replay covers the intent, so the stuck command can be dropped with the
      queue: replay state IS the source of truth).
   d. Read heartbeats (non-blocking recv, `decode_buffer`); store latest under lock; EOF → mark
      dead (next tick respawns).
4. `status()` [no I/O, cached]: `{"engine_alive": child_alive, "achieved_fps": <from last hb,
   0.0 if none>, "respawn_count": n, "heartbeat_age_s": age, "fps_degraded": <from hb>,
   **last_hb["status"]}` — the embedded runner-status dict keeps every key the coordinator's
   status merge (`led_dispatch_coordinator.py:227`) and the policy sanitize whitelist already
   read (`active`, `provider_bound`, `desired_effect`, `frame_index`, `last_error`,
   `razer_assert_count`, …). Before the first heartbeat, return
   `{"engine_alive": False, "achieved_fps": 0.0, "respawn_count": 0, "active": False,
   "provider_bound": provider is not None, "desired_effect": "", "last_error": ""}`.
   Edge-trigger a `bridge_log.health("govee.frame_engine", ...)` transition (use `log_changed`
   from `bridge_fmt`, same pattern as `govee_realtime_runner.py:232-238`) on child
   dead↔alive from the client thread.
5. `stop(timeout_s=3.0)`: send `shutdown`, wait for child exit up to 2.0 s, then `terminate()`
   (child's SIGTERM handler runs the same teardown), wait 0.5 s, then `kill()`; join the client
   thread; return True iff the child exited before `kill()` was needed (mirrors the runner's
   `stop() -> bool` contract the coordinator's `shutdown()` returns,
   `led_dispatch_coordinator.py:234-238`).
6. `emergency_stop()` extra: besides the mirror+enqueue, also PROMOTE it to the front of
   `_outbox` (appendleft after clearing any queued non-init messages except an unsent init) —
   blackout must never wait behind a queued look.

### Task 4 - `__main__.py`: wire the client in place of the in-process runner

In the LED startup block (`__main__.py:520-578`):
- Keep the realtime-enabled detection, IP resolution (`resolve_realtime_ip`, `:541-546`), and
  logging exactly as today. Build `engine_init = {"t": "init", "dry_run": cfg.dry_run,
  "ip": resolved_ip, "port": rt.port, "segments": rt.segments, "fps": rt.fps, "grace_s": 0.25,
  "header_bytes": rt.header_bytes, "stretch": rt.stretch, "activate_pt": rt.activate_pt,
  "deactivate_pt": rt.deactivate_pt}` (grace_s: the runner default today — `govee_realtime_runner.py:58`
  — pass it explicitly so the child matches; dry-run passes ip/port/segments as
  `GoveeRealtimeDryRunTransport` takes them, `__main__.py:533-537`).
- Replace the `GoveeRealtimeTransport`/`GoveeRealtimeRunner` construction (`:532-571`) with
  `realtime_runner = GoveeFrameEngineClient(engine_init, resolve_ip_fn=<partial of
  resolve_realtime_ip with the same args as :541-546 but timeout_s=1.0>)`. In dry-run,
  `resolve_ip_fn=None`. The `transport.deactivate()` at `:565` moves into the child (Task 1) —
  delete it here. Do NOT rename the `realtime_runner` variable or the `LEDStartupBundle` field;
  the coordinator constructor call (`:572-578`), `set_beat_provider`/`start` (`:1154-1156`) and
  shutdown `stop()` (`:1760-1761`) stay textually identical.
- Type annotations referencing `GoveeRealtimeRunner | None` on the bundle/locals
  (`:96,151,521`) widen to `GoveeRealtimeRunner | GoveeFrameEngineClient | None` (or `Any` —
  match file style); imports updated accordingly.

### Task 5 - `led_dispatch_policy.py`: expose the engine health in status

In `_sanitize_led_adapter_status`, extend the realtime key tuple
(`led_dispatch_policy.py:422-433`) with `"engine_alive"`, `"achieved_fps"`, `"respawn_count"`,
`"fps_degraded"` so the runtime status surface shows the self-report. No other policy change.

### Task 6 - operator blackout sends the LAN brightness-0 backstop regardless of runner state (operator review finding, 2026-07-08)

Gap found by the operator's independent AWR-145 review, folded into this workstream because it
lives on the exact surface being moved: `_emergency_teardown` guards its whole transport block
with `if self._active or handoff:` (`govee_realtime_runner.py:456`), so a pure operator/emergency
blackout while the runner is INACTIVE — the common case when the strip is showing a cloud look —
never sends the LAN brightness-0 backstop, and darkness relies on the internet cloud `off`
command alone. The fix goes in at the policy/coordinator level so it is independent of runner
active state (the runner drains brightness requests regardless of `_active`,
`govee_realtime_runner.py:275-276`) — and, moved into the child, independent of the frame
process's streaming state too:

1. `led_dispatch_coordinator.py`: add method `blackout_brightness() -> None` next to
   `restore_brightness` (`led_dispatch_coordinator.py:206-212`), body
   `self._runner.request_brightness(0)`, docstring naming the inactive-runner gap.
2. `led_dispatch_policy.py`: in the `Ev.LED_BLACKOUT` handler (`led_dispatch_policy.py:545-559`),
   after `self._led_emergency_blackout = bool(self._led_blackout_owners)` (`:557`) and before
   `_dispatch_led_manual_command`, add the duck-typed mirror of the existing clear-side restore
   (`:561-574`): `dim = getattr(self._led_scene_adapter, "blackout_brightness", None);
   if callable(dim): dim()`. Fires only after the blackout is accepted (the unknown-target
   early-return at `:548-553` must NOT dim). Repeat blackouts (second owner) re-request — the
   2-tick resend is idempotent.
3. Do NOT touch the tactical (pre-drop) blackout — it must never dim (AWR-145 rule,
   `led_dispatch_coordinator.py:199-201`).

### Task 7 (OPTIONAL — skip unless the precondition proves out) - remove the dead WI-6 config surface

`rt_reconcile_window_s` / `rt_reconcile_interval_s` in `LEDRateLimits` (`led_models.py:187-188`)
are dead config after AWR-145 removed WI-6. Remove them from `led_models.py`, any
`led_config.py` parsing/validation references, and `config/led_look_director.example.json` ONLY
if you first prove BOTH: (a) `rg -n "rt_reconcile" --type py` shows no reader outside the
dataclass definition and config parsing, and (b) the loader IGNORES unknown keys inside
`rate_limits` (read `_validate_rate_limits`, `led_config.py:682`, and the `LEDRateLimits`
construction site) — the operator's live gitignored config may still carry the keys, and a
strict loader would refuse to start the bridge over a cosmetic cleanup. If either check fails,
SKIP with one reported line. This task must not change any parsed value or default.

## Part C - Invariants That MUST Still Hold (live safety)

- **Single realtime writer:** the child process is the only holder of a realtime UDP socket to
  the strip; the bridge keeps zero realtime transports. Pad mutual exclusion
  (status-file freshness + auto-stop, `tools/led_pad_playback.py:275-290`) is untouched.
- **200 Hz push loop / StateManager threads gain no blocking or socket I/O:** every
  `GoveeFrameEngineClient` method the coordinator calls is lock-and-flag; IPC, spawning,
  waiting, and IP re-resolution happen only on the client thread (AGENTS.md §6).
- **Fail dark, never assume lit:** bridge death → kernel closes the socketpair → child sees EOF →
  `runner.stop()` → blackout + deactivate + close, then `os._exit`. Child death → EOF/waitpid at
  the client → respawn with intent replay (emergency replays as emergency + brightness-0; look
  replays as look + razer assert). A hung child (heartbeats stop or a command stuck >2 s) is
  killed and respawned. No zombie writer is possible: the only frame source is the runner inside
  the child, and the child cannot outlive the socketpair EOF handling.
- **AWR-145 guarantees, unmodified code:** keepalive, edge-activate + brightness 100,
  pure-emergency brightness-0, handoff-never-dims all execute inside the child's runner — the
  same `govee_realtime_runner.py` code, moved not rewritten. `request_activate_assert`,
  `request_brightness`, `restore_brightness` arrive as ordered stream messages. Dispatch-retry
  (policy) and pad auto-stop are bridge-side and untouched.
- **Cloud path untouched:** cloud dispatch, `GoveeSceneAdapter`, `GoveeRuntimeSender`, the
  owner state machine, and the operator-blackout cloud `off` command work exactly as today.
- **Operator blackout darkens in ANY state (Task 6):** the LAN brightness-0 backstop fires from
  the policy blackout handler regardless of runner/frame-process streaming state — it no longer
  depends on the runner's teardown branch at all. Tactical (pre-drop) blackout still never dims.
- **Child shutdown does not dim cloud looks:** EOF/shutdown teardown is `runner.stop()`
  (blackout + deactivate — ignored by a strip showing a cloud scene outside razer mode), never
  brightness-0 unless the emergency path latched it. Mirrors today's bridge-shutdown behavior.
- **Beat correctness:** anchors stream at 50 Hz including explicit `null`; the child's provider
  returns `None` for anchors staler than 0.5 s; the runner's extrapolation math is unchanged and
  the monotonic clock is cross-process comparable on this machine (Part A.5).
- `BridgeEvent`s stay immutable; reader threads never mutate `DeckState`; scripted/static
  SoundSwitch, laser paths, and the Held Static Override contract are untouched.

## Part D - Tests

New suite `tests/test_govee_frame_engine.py` (pure — injected fakes, no real sockets, processes,
sleeps, or files) + `tests/test_govee_frame_engine_integration.py` (real subprocess — precedent:
`tests/test_bridge_log_integration.py`, `tests/test_ss_bridge_watcher.py`). Existing suites must
stay green untouched except where named.

Pure host tests (`FrameEngineHost` with a `FakeConn` duplex object + fake transport + real
runner with injected `time_fn`/`sleep_fn`, or a recording fake runner where noted):
1. init → `transport_factory` called with the init msg; non-dry-run sends exactly one
   `deactivate()` before the runner starts (mirror of `__main__.py:565`).
2. `anchor` message → `beat_provider()` returns an equal `BeatAnchor`; `null` anchor → `None`;
   an anchor older than `ANCHOR_STALE_S` (fake clock) → `None`.
3. `set_desired` msg with params containing lists (JSON-normalized tuples) → runner receives an
   `EffectSpec` and — with a real renderer — `GoveeFrameRenderer.render` output for list-form
   color params equals the output for tuple-form (params round-trip safety).
4. Command fan-out: each of `fire_trigger`/`activate_assert`/`brightness`/`emergency_stop`/
   `force_deactivate` messages invokes exactly the matching runner method (recording fake runner).
5. AWR-145 through the boundary: `brightness` value 0 message → fake transport sees
   `set_brightness(0)` on 2 consecutive runner ticks; `activate_assert` → `activate()` on next
   tick; keepalive still re-activates after 2.0 s of active streaming (fake clock) — proving the
   moved runner behaves identically inside the host.
6. EOF from `FakeConn` → `runner.stop()` ran: fake transport records `blackout()` then
   `deactivate()` then `close()`, and NO `set_brightness(0)`; `shutdown` message → same teardown,
   run() returns.
7. Heartbeats: with a fake clock advancing past `HEARTBEAT_S`, `FakeConn` captured an `hb`
   whose `achieved_fps` matches the frame_index delta and whose `fps_degraded` goes True only
   after 3 consecutive low-fps heartbeats while streaming.
8. `decode_buffer`: split lines, partial-line remainder, malformed line skipped.

Pure client tests (`GoveeFrameEngineClient` with injected `spawn_fn` returning a fake child +
fake conn, fake `time_fn`):
9. Coordinator-facing methods do no I/O on the caller's thread (fake conn asserts writes happen
   only from the client thread) and preserve order on the wire: `set_desired` → `fire_trigger` →
   `activate_assert` arrive in that order.
10. Child EOF → respawn: init resent; mid-look intent replays as `set_desired` + `activate_assert`;
    mid-emergency replays as `emergency_stop` + an UNCONDITIONAL `brightness` 0 (see Task 3.3a —
    fresh runner is not `_active`, teardown alone sends nothing); `force_deactivate` state
    replays as `force_deactivate` only; a `set_desired` AFTER a `force_deactivate` replays as the
    look (handoff cleared); `respawn_count` increments.
11. Hung child: no heartbeat for >5 s (fake clock) → kill + respawn; a command stuck unsent
    >2 s → kill + respawn.
12. `emergency_stop` jumps the outbox queue ahead of a queued `set_desired`.
13. `status()` merges the last heartbeat and reports `engine_alive=False` + safe defaults before
    any heartbeat.
14. `stop()` sends `shutdown` and returns True when the fake child exits in time; escalation
    path returns False only when `kill()` was required.

Integration tests (real `subprocess` + real socketpair, dry-run transport only,
`@unittest.skipIf(os.environ.get("CI") == "true", "timing-sensitive")`):
15. **The 60 fps proof on this machine:** spawn the child (`fps=60, segments=60, dry_run=True`),
    stream synthetic anchors at 50 Hz (bpm 128, playing, permitted, advancing abs_beat_pos) and a
    `set_desired` for effect `"blackout"` (a real registered effect — production uses it,
    `led_dispatch_coordinator.py:191-198`); after ~3 s, the latest heartbeat reports
    `streaming=True` and `achieved_fps >= 55.0`; then `shutdown` → exit code 0 within 2 s.
16. Orphan safety: close the parent socket end → child exits 0 within 2 s (EOF teardown ran).

Task 6 tests (pure):
17. `tests/test_led_dispatch_coordinator.py`: `blackout_brightness()` calls
    `runner.request_brightness(0)` (recording fake runner).
18. `tests/test_led_state_manager.py`: an `Ev.LED_BLACKOUT` event invokes the adapter's
    `blackout_brightness` (recording fake adapter); a cloud-only adapter WITHOUT the method is a
    safe no-op (no exception); the unknown-target rejected blackout does NOT invoke it.
19. `tests/test_govee_realtime_runner.py`: a runner that was NEVER active receives
    `request_brightness(0)` and the fake transport sees `set_brightness(0)` on 2 consecutive
    ticks — the emergency-while-inactive darkness proof at the runner level. Extend pure host
    test 5 to drive the same brightness message with the runner inactive through the IPC path.

Run: `python3 -m unittest tests.test_govee_frame_engine
tests.test_govee_frame_engine_integration tests.test_govee_realtime_runner
tests.test_led_dispatch_coordinator tests.test_led_state_manager tests.test_led_pad_playback`
then `python3 -m unittest discover tests`.

## Part E - Acceptance (definition of done)

1. All Part D tests pass (including Task 6 tests 17-19); every AWR-145 test stays green
   (`tests/test_govee_realtime_runner.py`, `tests/test_led_dispatch_coordinator.py`,
   `tests/test_led_state_manager.py`, `tests/test_led_pad_playback.py`);
   `python3 -m unittest discover tests` green except the three known environmental reds
   (live-config LED test, export-pack parity fixtures fallback, SoundSwitch golden
   `test_ddj_slots_8_16_17_24_exact_ch1_ch19`) — do not fix or mask those. If optional Task 7
   ran, the LED config suite proves example config still loads and no parsed value changed; if
   skipped, say so in one line.
2. Integration test 15 passed on THIS machine with `achieved_fps >= 55.0` — record the measured
   number in your final report.
3. Contract checks green: `python3 tools/check_docs_metadata.py`,
   `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
4. `led_govee` contract `docs_update` satisfied where content is affected:
   `docs/subsystems/led_govee.md` (new "frame engine process" section: architecture, IPC protocol
   summary, supervision/fail-dark story, band control + fps self-report),
   `docs/status/feature_status_matrix.md`, `docs/status/support_matrix.md`,
   `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`,
   `docs/agents/task_playbooks/change_led_govee_behavior.md` (module list gains the two new
   files), registry row AWR-146 in `docs/status/active_work_registry.md` updated to
   implemented/software-tested. Status language: `implemented` / `software-tested` /
   `hardware-unvalidated` only — the live-mix fps number does not exist yet and must not be
   claimed.
5. No changes outside the Part B file list; commits by explicit file paths only.

## When You Finish

Report: changed files, tests/checks run with results (including the measured integration fps),
anything Blocked with a one-sentence reason. Then a plain-language operator summary: the LED
animation loop now runs in its own small helper program that the bridge starts and supervises,
so heavy bridge work (track scans, two-deck mixes) can no longer steal its timing; if the helper
ever dies the bridge restarts it within about a second and the look (or blackout) comes back on
its own; if the bridge dies the helper notices immediately and turns the strip dark before
exiting; all the AWR-145 blackout/keepalive behavior rides along unchanged; the achieved
frame rate is now a number in the status output, so a slowdown is visible evidence, not a
feeling. Unchanged: every look's colors/motion, cloud scenes, pad behavior, lasers, SoundSwitch.
Unproven until his next mix: the live fps under real load and on real hardware. Rollback:
`git revert` these commits + bridge restart via the menubar.
