"""
OS2L TCP connection and protocol helpers.

OS2LConnection: persistent TCP socket to SoundSwitch with auto-reconnect and
a dedicated sender thread so socket.send() never blocks the push loop.

OS2LOutput: higher-level helpers that take explicit arguments (no global state).
"""
from __future__ import annotations

import json
import logging
import math
import os
import queue
import socket
import threading
import time
from typing import Optional

from .config import (
    OS2L_FALLBACK_HOST, OS2L_FALLBACK_PORT,
    AUTOLOOP_BEATS,
)
from .models import TrackMetadata
from . import bridge_fmt as bf
from . import bridge_log

log = logging.getLogger("osl_output")

# ── Live-safety: emit-boundary tempo clamp ───────────────────────────────────
# A garbage/out-of-range memory read — from the direct reader OR the live-BPM
# memory scanner — must never feed SoundSwitch an absurd tempo, which SS would
# turn into a dangerously fast flash. Every BPM the bridge emits to SS funnels
# through send_bpm / send_beat / send_deck_load below (the scanner-follow path
# send_live_bpm_follow -> send_bpm included, which bypasses d.meta.bpm), so one
# clamp at those emits bounds all of them. Operator-tunable; the UPPER bound is
# the load-bearing safety limit (a real high reading is capped, not eaten).


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


BPM_EMIT_MIN = _env_float("RBSS_BPM_EMIT_MIN", 20.0)
BPM_EMIT_MAX = _env_float("RBSS_BPM_EMIT_MAX", 300.0)


def clamp_emit_bpm(bpm: float) -> float:
    """Bound an outgoing tempo before it reaches SoundSwitch.

    Non-finite or <=0 -> 0.0 (SS treats 0 as "no tempo"); otherwise clamp into
    [BPM_EMIT_MIN, BPM_EMIT_MAX]. One choke at the emit boundary, not a guard at
    every caller, so it covers the scanner-follow path and any future caller.
    """
    if not math.isfinite(bpm) or bpm <= 0.0:
        return 0.0
    if bpm < BPM_EMIT_MIN:
        return BPM_EMIT_MIN
    if bpm > BPM_EMIT_MAX:
        return BPM_EMIT_MAX
    return bpm


# ── Handshake sent on every new connection ───────────────────────────────────

_HANDSHAKE = {
    "evt": "subscribe",
    "name": "VirtualDJ",
    "trigger": [
        *[f"deck {d} get_text '%SOUNDSWITCH_ID'" for d in range(1, 5)],
        *[f"deck {d} get_filepath"               for d in range(1, 5)],
        *[f"deck {d} level"                      for d in range(1, 5)],
        "crossfader",
        *[f"deck {d} get_time elapsed absolute"  for d in range(1, 5)],
        *[f"deck {d} get_time total absolute"    for d in range(1, 5)],
        *[f"deck {d} get_beatpos"                for d in range(1, 5)],
        *[f"deck {d} get_firstbeat"              for d in range(1, 5)],
        *[f"deck {d} get_bpm"                    for d in range(1, 5)],
        *[f"deck {d} play"                       for d in range(1, 5)],
        *[f"deck {d} loop"                       for d in range(1, 5)],
        *[f"deck {d} get_loop"                   for d in range(1, 5)],
    ],
    "frequency": "25",
}


class OS2LConnection:
    """Persistent TCP connection to SoundSwitch.

    Maintains an internal sender queue so that callers never block on I/O.
    Auto-reconnects on any socket error.
    """

    def __init__(self) -> None:
        self.host = OS2L_FALLBACK_HOST
        self.port = OS2L_FALLBACK_PORT
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()
        self._send_q: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=500)
        self._stop = threading.Event()
        self.fast_reconnect = False   # skip init defaults on reconnect
        self._drop_count = 0
        self._no_socket_drop_count = 0
        self._send_error_count = 0
        self._sent_count = 0

    def is_connected(self) -> bool:
        """Constant-time connectivity check safe to call from hot paths."""
        with self._lock:
            return self._connected

    def status(self) -> dict:
        with self._lock:
            connected = self._connected
            host = self.host
            port = self.port
        return {
            "connected": connected,
            "endpoint": f"{host}:{port}",
            "queue_size": self._send_q.qsize(),
            "queue_max": self._send_q.maxsize,
            "queue_full_drops": self._drop_count,
            "no_socket_drops": self._no_socket_drop_count,
            "send_errors": self._send_error_count,
            "sent_count": self._sent_count,
        }

    def set_endpoint(self, host: str, port: int) -> None:
        with self._lock:
            changed = (host != self.host or port != self.port)
            self.host, self.port = host, port
        if changed:
            self.disconnect()

    def start(self) -> None:
        threading.Thread(target=self._sender_loop, name="os2l-sender", daemon=True).start()
        threading.Thread(target=self._reconnect_loop, name="os2l-reconnect", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._send_q.put_nowait(None)   # unblock sender

    def disconnect(self) -> None:
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
                self._connected = False

    def send(self, obj: dict, verbose: bool = False) -> None:
        payload = (json.dumps(obj) + "\n").encode()
        if verbose:
            log.debug("OS2L → %s", json.dumps(obj))
        try:
            self._send_q.put_nowait(payload)
        except queue.Full:
            self._drop_count += 1
            if bf.log_throttled("os2l_queue_full", 5.0):
                bridge_log.health("queue", "soundswitch send queue full; dropping updates")

    def _sender_loop(self) -> None:
        with bridge_log.thread_guard("os2l-sender"):
            while not self._stop.is_set():
                try:
                    msg = self._send_q.get(timeout=1)
                except queue.Empty:
                    continue
                if msg is None:
                    break
                with self._lock:
                    sock = self._sock if self._connected else None
                if sock is None:
                    self._no_socket_drop_count += 1
                    continue
                try:
                    sock.sendall(msg)
                    self._sent_count += 1
                except OSError as exc:
                    self._send_error_count += 1
                    bridge_log.health("os2l", "soundswitch send failed (%s); reconnecting", exc)
                    self.disconnect()

    def _reconnect_loop(self) -> None:
        with bridge_log.thread_guard("os2l-reconnect"):
            while not self._stop.is_set():
                with self._lock:
                    connected = self._connected
                if connected:
                    time.sleep(0.5)
                    continue

                with self._lock:
                    host, port = self.host, self.port
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    sock.connect((host, port))
                    sock.settimeout(None)
                    with self._lock:
                        self._sock = sock
                        self._connected = True
                    bridge_log.health("os2l", "soundswitch link connected (%s:%d)", host, port, lvl=logging.INFO)
                    # Re-arm the connect-fail edge guard so the NEXT outage
                    # (even with the same error signature) emits again.
                    bf.log_changed("os2l_conn_fail", None)
                    self.send(_HANDSHAKE)
                    if not self.fast_reconnect:
                        self._send_init_defaults()
                    self.fast_reconnect = False
                except (OSError, ConnectionRefusedError) as exc:
                    if bf.log_changed("os2l_conn_fail", (host, port, type(exc).__name__)):
                        bridge_log.health(
                            "os2l", "soundswitch not reachable at %s:%d (%s); retrying every 3s", host, port, exc,
                        )
                    time.sleep(3)

    def _send_init_defaults(self) -> None:
        for d in range(1, 5):
            self.send({"evt": "subscribed", "trigger": f"deck {d} play",  "value": "off"})
            self.send({"evt": "subscribed", "trigger": f"deck {d} loop",  "value": "off"})
            self.send({"evt": "subscribed", "trigger": f"deck {d} get_bpm", "value": 0.0})
            self.send({"evt": "subscribed", "trigger": f"deck {d} get_filepath", "value": ""})
            self.send({"evt": "subscribed",
                       "trigger": f"deck {d} get_text '%SOUNDSWITCH_ID'",
                       "value": ""})


# ── Discovery ─────────────────────────────────────────────────────────────────

class SoundSwitchDiscovery:
    """DNS-SD browser for _os2l._tcp; updates OS2LConnection endpoint on find."""

    def __init__(self, conn: OS2LConnection) -> None:
        self._conn = conn
        self._zc = None
        self._browser = None

    def start(self) -> None:
        try:
            from zeroconf import ServiceBrowser, Zeroconf  # type: ignore
            self._zc = Zeroconf()
            self._browser = ServiceBrowser(self._zc, "_os2l._tcp.local.", handlers=[self._on_service])
            log.info("[OS2L] dns-sd  started")
        except Exception as exc:
            log.warning("[OS2L] dns-sd-fail  err=%s  action=fallback", exc)

    def stop(self) -> None:
        if self._zc is not None:
            try:
                self._zc.close()
            except Exception:
                pass
            self._zc = None
            self._browser = None

    def _on_service(self, zeroconf, service_type, name, state_change) -> None:  # type: ignore
        from zeroconf import ServiceStateChange  # type: ignore
        if state_change not in (ServiceStateChange.Added, ServiceStateChange.Updated):
            return
        try:
            info = zeroconf.get_service_info(service_type, name, timeout=3000)
            if not info:
                log.info("[OS2L] dns-sd  info-not-ready  name=%s", name)
                return
            ipv4 = next((addr for addr in info.addresses if len(addr) == 4), None)
            if not ipv4:
                log.info("[OS2L] dns-sd  no-ipv4  name=%s", name)
                return
            host = socket.inet_ntoa(ipv4)
            port = info.port
            log.info("[OS2L] dns-sd  found  name=%s  host=%s:%d", name, host, port)
            self._conn.set_endpoint(host, port)
        except Exception as exc:
            log.warning("[OS2L] dns-sd-error  err=%s", exc)


# ── Higher-level output helpers ───────────────────────────────────────────────

class OS2LOutput:
    """Wraps OS2LConnection with protocol-level helpers.

    All methods take explicit arguments — no global state accessed here.
    """

    def __init__(self, conn: OS2LConnection) -> None:
        self._conn = conn

    def _sub(self, trigger: str, value, verbose: bool = False) -> None:
        self._conn.send({"evt": "subscribed", "trigger": trigger, "value": value}, verbose=verbose)

    def send_beat(self, deck: int, bpm: float, beat_index: int, change: bool = False) -> None:
        """Fire a beat event to SS for the given deck."""
        bpm = clamp_emit_bpm(bpm)
        self._conn.send({
            "evt":   "beat",
            "deck":  deck,
            "bpm":   round(bpm, 2),
            "pos":   beat_index,
            "change": change,
        })

    def send_deck_play(self, deck: int, state: str) -> None:
        self._sub(f"deck {deck} play", state, verbose=True)

    def send_deck_clear(self, deck: int) -> None:
        dn = f"deck {deck}"
        self._sub(f"{dn} get_text '%SOUNDSWITCH_ID'", "", verbose=True)
        self._sub(f"{dn} get_filepath", "", verbose=True)
        self._sub(f"{dn} play", "off", verbose=True)

    def send_deck_load(
        self,
        deck: int,
        meta: TrackMetadata,
        active_deck: int,
        play: str = "on",
        include_loop: bool = True,
        fallback_bpm: float = 0.0,
        elapsed_ms: int = 0,
    ) -> None:
        """Register a track with SoundSwitch.

        Wireshark-confirmed VDJ behavior:
          Active deck:  NO SOUNDSWITCH_ID (SS derives show from filepath).
          Mirror decks: null UUID SOUNDSWITCH_ID sent first, then track data.
        """
        dn = f"deck {deck}"
        # Always force play=on when this deck is master
        if deck == active_deck and play != "off":
            play = "on"

        ss_id = meta.soundswitch_id or "{00000000-0000-0000-0000-000000000000}"
        self._sub(f"{dn} get_text '%SOUNDSWITCH_ID'", ss_id, verbose=True)
        self._sub(f"{dn} get_firstbeat", int(round(meta.first_beat_ms)), verbose=True)

        bpm_out = meta.bpm if meta.bpm > 0 else fallback_bpm
        loop_val = AUTOLOOP_BEATS if include_loop and not meta.soundswitch_id else "off"
        bridge_log.perf(
            "ss",
            "deck-load deck=%d active=%d file=%s bpm=%.2f loop=%s play=%s",
            deck, active_deck,
            bf.short(meta.filepath),
            bpm_out,
            loop_val,
            play,
            deck=deck,
            data={
                "action": "deck-load",
                "deck": deck,
                "active": active_deck,
                "file": bf.short(meta.filepath),
                "ssid": ss_id,
                "bpm": bpm_out,
                "loop": loop_val,
                "play": play,
            },
        )
        if bpm_out:
            self._sub(f"{dn} get_bpm", round(clamp_emit_bpm(bpm_out), 2), verbose=True)

        title = os.path.basename(meta.filepath).rsplit(".", 1)[0] if meta.filepath else ""
        self._sub(f"{dn} song_title", title, verbose=True)
        self._sub(f"{dn} song_artist", "", verbose=True)

        # Loop state before filepath so SS is in correct mode when filepath arrives
        if include_loop:
            if meta.soundswitch_id:
                self._sub(f"{dn} loop", "off", verbose=True)
            else:
                self._sub(f"{dn} loop", "on", verbose=True)
                self._sub(f"{dn} get_loop", AUTOLOOP_BEATS, verbose=True)

        self._sub(f"{dn} get_filepath", meta.filepath, verbose=True)
        if meta.total_ms:
            self._sub(f"{dn} get_time total absolute", int(meta.total_ms), verbose=True)
        self._sub(f"{dn} get_time elapsed absolute", int(elapsed_ms), verbose=True)
        self._sub(f"{dn} play", play, verbose=True)

    def send_elapsed(self, deck: int, elapsed_ms: int, beatpos: float) -> None:
        dn = f"deck {deck}"
        self._sub(f"{dn} get_time elapsed absolute", elapsed_ms)
        self._sub(f"{dn} get_beatpos", round(beatpos, 4))

    def send_bpm(self, deck: int, bpm: float) -> None:
        self._sub(f"deck {deck} get_bpm", round(clamp_emit_bpm(bpm), 2), verbose=True)

    def send_loop_on(self, deck: int, beats: int = AUTOLOOP_BEATS) -> None:
        self._sub(f"deck {deck} loop", "on", verbose=True)
        self._sub(f"deck {deck} get_loop", beats, verbose=True)

    def send_loop_off(self, deck: int) -> None:
        self._sub(f"deck {deck} loop", "off", verbose=True)
