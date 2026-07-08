"""Govee frame engine child process — protocol + host (AWR-146).

The realtime frame trio (``GoveeRealtimeRunner`` → ``GoveeFrameRenderer`` →
``GoveeRealtimeTransport``) is lifted out of the bridge into this child process
so the bridge's GIL contention (628 ms RBMEM scans, two-deck loads) can no
longer starve LED animation timing. The bridge-side ``GoveeFrameEngineClient``
(``govee_frame_engine_client.py``) spawns and supervises one of these over a
JSON-lines socketpair.

This module contains only the protocol (pure functions), the ``FrameEngineHost``
(testable with injected fakes — no real sockets or processes), the macOS
scheduling-band levers, and ``main()`` (the ``python3 -m
rb_ss_bridge_v2.govee_frame_engine`` entrypoint). No AWR-145 logic is
reimplemented here — the runner moves in wholesale.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import logging
import os
import select
import signal
import socket
import sys
import threading
import time
from typing import Any, Callable

from .govee_frame_renderer import GoveeFrameRenderer
from .govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
from .govee_realtime_transport import (
    GoveeRealtimeDryRunTransport,
    GoveeRealtimeTransport,
)
from .led_models import BeatAnchor

HEARTBEAT_S = 1.0
ANCHOR_STALE_S = 0.5
SELECT_TIMEOUT_S = 0.25

_LOG = logging.getLogger("govee_frame_engine")

# NSActivity token — kept alive for the process lifetime (a released token drops
# the assertion). Module-global so it outlives raise_scheduling_band().
_ACTIVITY_TOKEN: Any = None


# ── Protocol (pure) ────────────────────────────────────────────────────────────

def encode_msg(msg: dict) -> bytes:
    return json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n"


def decode_buffer(buf: bytes) -> tuple[list[dict], bytes]:
    """Split newline-framed JSON. Returns (messages, trailing remainder).

    A malformed line logs a WARNING and is skipped — one bad line never kills
    the stream.
    """
    *lines, remainder = buf.split(b"\n")
    messages: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            messages.append(json.loads(line))
        except (ValueError, TypeError):
            _LOG.warning("[ENGINE] dropping malformed IPC line: %r", line[:120])
    return messages, remainder


# ── Scheduling band (macOS) ────────────────────────────────────────────────────

def _qos_user_interactive() -> None:
    """Frame-thread QoS hook passed to the runner via on_thread_start.

    This runs as the runner thread's first statement, so a raised exception would
    silently kill the frame thread while heartbeats keep flowing (streaming stays
    False). A missing symbol is therefore a WARNING-and-continue, not a crash — the
    band still has setpriority + NSActivity, and fps self-measure catches any decay.
    """
    lib = ctypes.CDLL(
        ctypes.util.find_library("pthread") or ctypes.util.find_library("c")
    )
    fn = getattr(lib, "pthread_set_qos_class_self_np", None)
    if fn is None:
        _LOG.warning(
            "[ENGINE] pthread_set_qos_class_self_np missing — frame-thread QoS not set")
        return
    fn.argtypes = [ctypes.c_uint, ctypes.c_int]
    fn(0x21, 0)  # QOS_CLASS_USER_INTERACTIVE — confirmed returns 0 on this machine


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


# ── Host ───────────────────────────────────────────────────────────────────────

class FrameEngineHost:
    """Owns the runner inside the child; bridges the IPC stream to it.

    ``conn`` is any object exposing recv(n)->bytes (b"" == EOF), send(bytes)->int,
    and fileno(). No real socket or process is required, so the host is unit
    testable with an in-memory duplex fake.
    """

    def __init__(
        self,
        conn,
        *,
        transport_factory: Callable[[dict], Any],
        runner_factory: Callable[..., Any] = GoveeRealtimeRunner,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._conn = conn
        self._transport_factory = transport_factory
        self._runner_factory = runner_factory
        self._time_fn = time_fn
        self._log = _LOG

        self._anchor_lock = threading.Lock()
        self._anchor: BeatAnchor | None = None
        self._shutdown = threading.Event()

        self._transport: Any = None
        self._runner: Any = None
        self._fps = 1
        self._recv_buf = b""
        self._pending: list[dict] = []

        # fps self-measure / heartbeat state
        self._hb_prev_at: float | None = None
        self._hb_prev_index = 0
        self._low_hb_count = 0
        self._degraded_latched = False

    # -- anchor / beat provider --------------------------------------------------
    def beat_provider(self) -> BeatAnchor | None:
        with self._anchor_lock:
            anchor = self._anchor
        if anchor is None:
            return None
        if self._time_fn() - anchor.captured_monotonic > ANCHOR_STALE_S:
            return None
        return anchor

    # -- message dispatch --------------------------------------------------------
    def handle_message(self, msg: dict) -> bool:
        """Return False iff shutdown was requested."""
        t = msg.get("t")
        if t == "anchor":
            a = msg.get("a")
            anchor = None if a is None else BeatAnchor(
                deck=int(a["deck"]),
                abs_beat_pos=float(a["abs_beat_pos"]),
                bpm=float(a["bpm"]),
                captured_monotonic=float(a["captured_monotonic"]),
                playing=bool(a["playing"]),
                permitted=bool(a["permitted"]),
            )
            with self._anchor_lock:
                self._anchor = anchor
            return True
        if t == "set_desired":
            spec = msg.get("spec")
            if spec is None:
                self._runner.set_desired(None)
            else:
                self._runner.set_desired(EffectSpec(
                    effect_name=str(spec["effect_name"]),
                    params=spec.get("params") or {},
                    seed=int(spec["seed"]),
                    applied_monotonic=float(spec["applied_monotonic"]),
                    sync_mode=str(spec.get("sync_mode", "")),
                    beat_division=float(spec.get("beat_division", 0.0)),
                ))
            return True
        if t == "fire_trigger":
            self._runner.fire_trigger()
            return True
        if t == "activate_assert":
            self._runner.request_activate_assert()
            return True
        if t == "brightness":
            self._runner.request_brightness(int(msg["value"]))
            return True
        if t == "emergency_stop":
            self._runner.emergency_stop()
            return True
        if t == "force_deactivate":
            self._runner.force_deactivate()
            return True
        if t == "shutdown":
            return False
        self._log.warning("[ENGINE] unknown IPC message type %r", t)
        return True

    # -- lifecycle ---------------------------------------------------------------
    def request_shutdown(self) -> None:
        self._shutdown.set()

    def _setup(self, init: dict) -> None:
        dry_run = bool(init["dry_run"])
        self._fps = int(init["fps"])
        transport = self._transport_factory(init)
        if not dry_run:
            # Mirror __main__.py:565 — clear any lingering razer mode before frames.
            transport.deactivate()
        self._transport = transport
        self._runner = self._runner_factory(
            transport, GoveeFrameRenderer(),
            segments=int(init["segments"]), fps=self._fps,
            grace_s=float(init["grace_s"]), on_thread_start=_qos_user_interactive,
        )
        self._runner.set_beat_provider(self.beat_provider)

    def run(self) -> None:
        init = self._read_init()
        if init is None or init.get("t") != "init":
            self._log.error("[ENGINE] first IPC message was not 'init'; aborting")
            return
        self._setup(init)
        self._runner.start()
        try:
            self._serve()
        finally:
            # blackout + deactivate + close — the same dark-on-shutdown the bridge
            # performs today. Deliberately NO brightness-0: a healthy cloud look
            # must survive a bridge restart.
            self._runner.stop()

    def _read_init(self) -> dict | None:
        buf = b""
        while not self._shutdown.is_set():
            readable, _, _ = select.select([self._conn], [], [], SELECT_TIMEOUT_S)
            if not readable:
                continue
            chunk = self._conn.recv(65536)
            if chunk == b"":
                return None
            buf += chunk
            msgs, buf = decode_buffer(buf)
            if msgs:
                self._recv_buf = buf
                self._pending = msgs[1:]
                return msgs[0]
        return None

    def _serve(self) -> None:
        buf = self._recv_buf
        for msg in self._pending:
            if not self.handle_message(msg):
                return
        self._pending = []
        self._hb_prev_at = self._time_fn()
        self._hb_prev_index = self._runner_frame_index()
        last_hb_at = self._time_fn()
        while not self._shutdown.is_set():
            readable, _, _ = select.select([self._conn], [], [], SELECT_TIMEOUT_S)
            if readable:
                chunk = self._conn.recv(65536)
                if chunk == b"":
                    break
                buf += chunk
                msgs, buf = decode_buffer(buf)
                stop = False
                for msg in msgs:
                    if not self.handle_message(msg):
                        stop = True
                        break
                if stop:
                    break
            now = self._time_fn()
            if now - last_hb_at >= HEARTBEAT_S:
                self._send_heartbeat(now)
                last_hb_at = now

    # -- heartbeat / fps self-measure --------------------------------------------
    def _runner_frame_index(self) -> int:
        if self._runner is None:
            return 0
        return int(self._runner.status().get("frame_index", 0))

    def _send_heartbeat(self, now: float) -> None:
        status = self._runner.status() if self._runner is not None else {}
        frame_index = int(status.get("frame_index", 0))
        streaming = bool(status.get("active", False))
        if self._hb_prev_at is None:
            achieved = 0.0
        else:
            dt = now - self._hb_prev_at
            achieved = (frame_index - self._hb_prev_index) / max(dt, 1e-6)
        self._hb_prev_at = now
        self._hb_prev_index = frame_index

        low = streaming and achieved < 0.8 * self._fps
        self._low_hb_count = self._low_hb_count + 1 if low else 0
        degraded = self._low_hb_count >= 3
        if degraded and not self._degraded_latched:
            self._degraded_latched = True
            self._log.warning(
                "[ENGINE] fps degraded: %.1f < %.1f target", achieved, float(self._fps))
        elif not degraded and self._degraded_latched:
            self._degraded_latched = False
            self._log.info("[ENGINE] fps recovered: %.1f", achieved)

        hb = {
            "t": "hb", "pid": os.getpid(),
            "achieved_fps": round(achieved, 2),
            "streaming": streaming, "fps_degraded": degraded,
            "status": status,
        }
        try:
            self._conn.send(encode_msg(hb))
        except BlockingIOError:
            pass  # parent slow to drain — skip this heartbeat, the next is in 1 s


# ── Entrypoint ─────────────────────────────────────────────────────────────────

def _make_transport(init: dict) -> Any:
    if init["dry_run"]:
        return GoveeRealtimeDryRunTransport(
            ip=init["ip"], port=init["port"], segments=init["segments"])
    return GoveeRealtimeTransport(
        init["ip"], port=init["port"], segments=init["segments"],
        header_bytes=init["header_bytes"], stretch=init["stretch"],
        activate_pt=init["activate_pt"], deactivate_pt=init["deactivate_pt"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fd", type=int, required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)  # NEVER bridge_log.init()
    report = raise_scheduling_band()
    _LOG.info("[ENGINE] scheduling band report=%s pid=%d", report, os.getpid())

    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=args.fd)
    conn.setblocking(False)
    host = FrameEngineHost(conn, transport_factory=_make_transport)

    def _on_sigterm(_signum: int, _frame: Any) -> None:
        host.request_shutdown()

    signal.signal(signal.SIGTERM, _on_sigterm)
    host.run()
    # REQUIRED: pyobjc can hang normal interpreter exit after import Foundation.
    os._exit(0)


if __name__ == "__main__":
    main()
