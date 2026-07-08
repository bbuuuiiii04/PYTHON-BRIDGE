"""In-bridge client + supervisor for the Govee frame engine child (AWR-146).

``GoveeFrameEngineClient`` is a drop-in replacement for ``GoveeRealtimeRunner``
from the coordinator's and ``__main__``'s point of view: same public method
names, same ``stop() -> bool`` contract. It owns none of the frame work — it
spawns the child process (``govee_frame_engine.main``), streams beat anchors and
commands to it over a JSON-lines ``AF_UNIX`` socketpair, and supervises it
(respawn on death/hang with intent replay).

Live-safety discipline: every public method the coordinator calls is
lock-and-flag with ZERO I/O on the caller's thread. All socket/process I/O,
spawning, waiting, and IP re-resolution run on the client's own thread — the
200 Hz push loop and StateManager threads never block (AGENTS.md §6).
"""
from __future__ import annotations

import collections
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import bridge_log
from .bridge_fmt import log_changed
from .govee_frame_engine import decode_buffer, encode_msg
from .govee_realtime_runner import EffectSpec

CLIENT_TICK_S = 0.02          # 50 Hz — matches the "tens of Hz" anchor cadence
HEARTBEAT_STALE_S = 5.0       # no heartbeat this long → hung child → respawn
COMMAND_STUCK_S = 2.0         # oldest unsent command this old → hung child → respawn
RESPAWN_BACKOFF_S = 0.5
RESPAWN_BACKOFF_MAX_S = 5.0
CHILD_SURVIVE_RESET_S = 30.0  # a child alive this long resets the backoff to 0.5

_LOG = logging.getLogger("govee_frame_engine_client")


class GoveeFrameEngineClient:
    def __init__(
        self,
        engine_init: dict,
        *,
        resolve_ip_fn: Callable[[], str] | None = None,
        spawn_fn: Callable[[dict], tuple[Any, Any]] | None = None,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._engine_init = dict(engine_init)
        self._resolve_ip_fn = resolve_ip_fn
        self._spawn_fn = spawn_fn or self._default_spawn
        self._time_fn = time_fn
        self._log = _LOG

        self._lock = threading.Lock()
        self._provider: Callable[[], Any] | None = None
        self._outbox: collections.deque = collections.deque()  # (enqueued_at, msg)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # Mirrored intent — replay reproduces the operator's CURRENT intent.
        self._desired: EffectSpec | None = None
        self._emergency = False
        self._handoff = False
        self._brightness_pending: int | None = None
        self._assert_pending = False

        # Child / connection state (touched only on the client thread, except
        # _alive_cached / _last_hb_msg / _respawn_count which status() reads).
        self._proc: Any = None
        self._conn: Any = None
        self._eof_seen = False
        self._recv_buf = b""
        self._child_started_at: float | None = None
        self._last_hb: float | None = None
        self._last_hb_msg: dict | None = None
        self._alive_cached = False
        self._respawn_count = 0
        self._ever_spawned = False
        self._pending_respawn = False
        self._respawn_ready_at: float | None = None
        self._backoff = RESPAWN_BACKOFF_S

    # ── Public surface (lock-and-flag, ZERO I/O on the caller thread) ───────────
    def set_beat_provider(self, provider: Callable[[], Any] | None) -> None:
        with self._lock:
            self._provider = provider

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="GoveeFrameEngineClient", daemon=True)
            self._thread.start()

    def set_desired(self, spec: EffectSpec | None) -> None:
        with self._lock:
            self._desired = spec
            if spec is not None:
                # Mirror runner :108-112 — a new look clears emergency; and clears
                # handoff: once a look is desired the intent is the look.
                self._emergency = False
                self._handoff = False
            self._enqueue({"t": "set_desired",
                           "spec": None if spec is None else _spec_to_wire(spec)})
        self._wake.set()

    def fire_trigger(self) -> None:
        with self._lock:
            self._enqueue({"t": "fire_trigger"})
        self._wake.set()

    def request_activate_assert(self) -> None:
        with self._lock:
            self._assert_pending = True
            self._enqueue({"t": "activate_assert"})
        self._wake.set()

    def request_brightness(self, value: int) -> None:
        with self._lock:
            self._brightness_pending = int(value)
            self._enqueue({"t": "brightness", "value": int(value)})
        self._wake.set()

    def emergency_stop(self) -> None:
        with self._lock:
            self._emergency = True
            # Blackout must never wait behind a queued look — promote to the front.
            self._promote_emergency({"t": "emergency_stop"})
        self._wake.set()

    def force_deactivate(self) -> None:
        with self._lock:
            # Mirror runner :140-145 — clear desired, set handoff, set emergency.
            self._desired = None
            self._handoff = True
            self._emergency = True
            self._enqueue({"t": "force_deactivate"})
        self._wake.set()

    def status(self) -> dict[str, Any]:
        now = self._time_fn()
        with self._lock:
            hb = self._last_hb_msg
            provider_bound = self._provider is not None
            alive = self._alive_cached
            respawn_count = self._respawn_count
            last_hb_at = self._last_hb
        if hb is None:
            return {
                "engine_alive": False, "achieved_fps": 0.0,
                "respawn_count": respawn_count, "active": False,
                "provider_bound": provider_bound, "desired_effect": "",
                "last_error": "",
            }
        age = (now - last_hb_at) if last_hb_at is not None else 0.0
        return {
            "engine_alive": alive,
            "achieved_fps": float(hb.get("achieved_fps", 0.0)),
            "respawn_count": respawn_count,
            "heartbeat_age_s": round(age, 3),
            "fps_degraded": bool(hb.get("fps_degraded", False)),
            **(hb.get("status") or {}),
        }

    def stop(self, timeout_s: float = 3.0) -> bool:
        # Runs on the shutting-down bridge's main thread. Stop the client thread
        # first so nothing else touches the socket, then do the child handshake.
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.1, float(timeout_s)))
        proc = self._proc
        if proc is None:
            self._close_conn()
            return True
        self._write({"t": "shutdown"})
        graceful = self._wait_exit(proc, 2.0)
        if not graceful:
            proc.terminate()  # child SIGTERM handler runs the same teardown
            graceful = self._wait_exit(proc, 0.5)
            if not graceful:
                proc.kill()
                self._wait_exit(proc, 0.5)
        self._close_conn()
        return graceful

    # ── Intent-state helpers (call under self._lock) ────────────────────────────
    def _enqueue(self, msg: dict) -> None:
        self._outbox.append((self._time_fn(), msg))

    def _promote_emergency(self, msg: dict) -> None:
        # Drop queued looks/commands (init is never queued — sent directly at
        # spawn), then put the emergency at the front.
        self._outbox = collections.deque(
            (ts, m) for ts, m in self._outbox if m.get("t") == "init")
        self._outbox.appendleft((self._time_fn(), msg))

    # ── Client thread ───────────────────────────────────────────────────────────
    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(CLIENT_TICK_S)
            self._wake.clear()
            self._tick(self._time_fn())

    def _tick(self, now: float) -> None:
        self._ensure_child(now)
        self._alive_cached = self._child_running()
        if self._conn is None:
            return
        self._pump_anchor(now)
        self._drain_outbox(now)
        self._read_heartbeats(now)
        self._alive_cached = self._child_running()

    def _child_running(self) -> bool:
        return (
            self._proc is not None
            and self._conn is not None
            and self._proc.poll() is None
            and not self._eof_seen
        )

    def _ensure_child(self, now: float) -> None:
        alive = self._child_running()
        # A child that never sends a first heartbeat within HEARTBEAT_STALE_S of
        # start is treated as hung too (ref = last hb, else start time).
        hb_ref = self._last_hb if self._last_hb is not None else self._child_started_at
        hung = alive and hb_ref is not None and (now - hb_ref) > HEARTBEAT_STALE_S
        stuck = alive and bool(self._outbox) and (now - self._outbox[0][0]) > COMMAND_STUCK_S
        if alive and not hung and not stuck:
            if (self._child_started_at is not None
                    and (now - self._child_started_at) >= CHILD_SURVIVE_RESET_S):
                self._backoff = RESPAWN_BACKOFF_S
            return

        if self._proc is not None:
            reason = "hung" if hung else ("stuck-command" if stuck else "dead")
            self._kill_child()
            self._pending_respawn = True
            self._respawn_ready_at = now + self._backoff
            self._log.info("[ENGINE] frame engine child %s; scheduling respawn", reason)

        if self._respawn_ready_at is not None and now < self._respawn_ready_at:
            return  # honor the backoff window (enforced by clock, no blocking sleep)

        self._do_spawn(now)
        if self._pending_respawn:
            self._respawn_count += 1
            self._backoff = min(self._backoff * 2, RESPAWN_BACKOFF_MAX_S)
            self._log.info(
                "[ENGINE] respawned frame engine child (count=%d, next_backoff=%.1fs)",
                self._respawn_count, self._backoff)
        self._pending_respawn = False
        self._respawn_ready_at = None
        self._replay_intent(now)

    def _do_spawn(self, now: float) -> None:
        if self._resolve_ip_fn is not None:
            # Client thread may block briefly here — it is not the push loop.
            self._engine_init = {**self._engine_init, "ip": self._resolve_ip_fn()}
        proc, conn = self._spawn_fn(self._engine_init)
        self._proc = proc
        self._conn = conn
        self._eof_seen = False
        self._recv_buf = b""
        self._child_started_at = now
        self._last_hb = None
        self._ever_spawned = True
        init_msg = {**self._engine_init, "t": "init"}
        self._write(init_msg)  # init is sent first, directly (never queued)

    def _replay_intent(self, now: float) -> None:
        # Replay state IS the source of truth — drop any stale queued commands
        # that were meant for the dead child, then reconstruct current intent.
        with self._lock:
            self._outbox.clear()
            handoff = self._handoff
            emergency = self._emergency
            desired = self._desired
            brightness = self._brightness_pending
        if handoff:
            self._write({"t": "force_deactivate"})
        elif emergency:
            self._write({"t": "emergency_stop"})
            # Unconditional: a fresh runner is never _active, so its
            # _emergency_teardown sends nothing — brightness-0 is what darkens.
            self._write({"t": "brightness", "value": 0})
        elif desired is not None:
            self._write({"t": "set_desired", "spec": _spec_to_wire(desired)})
            self._write({"t": "activate_assert"})  # heal razer after the gap
        if brightness is not None:
            self._write({"t": "brightness", "value": brightness})

    def _pump_anchor(self, now: float) -> None:
        with self._lock:
            provider = self._provider
        anchor = provider() if provider is not None else None
        # Explicit null propagates pause/unpermitted. Anchors are never queued —
        # a dropped one (BlockingIOError) is replaced by the next in 20 ms.
        self._write({"t": "anchor", "a": None if anchor is None else _anchor_to_wire(anchor)})

    def _drain_outbox(self, now: float) -> None:
        while not self._stop.is_set():
            with self._lock:
                if not self._outbox:
                    break
                ts, msg = self._outbox.popleft()
            if not self._write(msg):
                # BlockingIOError (buffer full) or EOF — retry next tick, keep age.
                with self._lock:
                    self._outbox.appendleft((ts, msg))
                break
            if msg.get("t") == "brightness":
                with self._lock:
                    self._brightness_pending = None

    def _read_heartbeats(self, now: float) -> None:
        if self._conn is None:
            return
        try:
            chunk = self._conn.recv(65536)
        except BlockingIOError:
            return
        except OSError:
            self._eof_seen = True
            self._child_dead_health()
            return
        if chunk == b"":
            self._eof_seen = True
            self._child_dead_health()
            return
        self._recv_buf += chunk
        msgs, self._recv_buf = decode_buffer(self._recv_buf)
        got_hb = False
        for msg in msgs:
            if msg.get("t") == "hb":
                with self._lock:
                    self._last_hb_msg = msg
                self._last_hb = now
                got_hb = True
        if got_hb:
            self._child_alive_health()

    # ── Health edge-trigger (client thread only) ────────────────────────────────
    def _child_alive_health(self) -> None:
        if log_changed("govee_frame_engine_alive", True):
            bridge_log.health("govee.frame_engine", "recovered", lvl=logging.INFO)

    def _child_dead_health(self) -> None:
        if log_changed("govee_frame_engine_alive", False):
            bridge_log.health("govee.frame_engine", "child down — respawning")

    # ── Process I/O helpers (client / shutdown thread only) ─────────────────────
    def _write(self, msg: dict) -> bool:
        conn = self._conn
        if conn is None:
            return False
        try:
            conn.send(encode_msg(msg))
            return True
        except BlockingIOError:
            return False
        except OSError:
            self._eof_seen = True
            return False

    def _kill_child(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            if not self._wait_exit(proc, 0.5):
                proc.kill()
                self._wait_exit(proc, 0.5)
        self._close_conn()
        self._proc = None
        self._alive_cached = False

    def _close_conn(self) -> None:
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
        self._conn = None

    @staticmethod
    def _wait_exit(proc: Any, timeout: float) -> bool:
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def _default_spawn(self, engine_init: dict) -> tuple[Any, Any]:
        import socket
        parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        child_fd = child_sock.fileno()
        proc = subprocess.Popen(
            [sys.executable, "-m", "rb_ss_bridge_v2.govee_frame_engine",
             "--fd", str(child_fd)],
            pass_fds=(child_fd,),
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=None,  # inherit the bridge's stderr → child lines in the watcher
        )
        child_sock.close()          # parent closes the child end after spawn
        parent_sock.setblocking(False)
        return proc, parent_sock


# ── Wire helpers (pure) ─────────────────────────────────────────────────────────

def _spec_to_wire(spec: EffectSpec) -> dict:
    return {
        "effect_name": spec.effect_name,
        "params": dict(spec.params),
        "seed": spec.seed,
        "applied_monotonic": spec.applied_monotonic,
        "sync_mode": spec.sync_mode,
        "beat_division": spec.beat_division,
    }


def _anchor_to_wire(anchor: Any) -> dict:
    return {
        "deck": anchor.deck,
        "abs_beat_pos": anchor.abs_beat_pos,
        "bpm": anchor.bpm,
        "captured_monotonic": anchor.captured_monotonic,
        "playing": anchor.playing,
        "permitted": anchor.permitted,
    }
