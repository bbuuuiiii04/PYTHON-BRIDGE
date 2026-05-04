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
    AUTOLOOP_BEATS, TIMING_COMPENSATION_MS,
)
from .models import TrackMetadata

log = logging.getLogger("osl_output")

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
            log.warning("OS2L send queue full — dropping message")

    def _sender_loop(self) -> None:
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
                continue
            try:
                sock.sendall(msg)
            except OSError as exc:
                log.warning("OS2L send error: %s — reconnecting", exc)
                self.disconnect()

    def _reconnect_loop(self) -> None:
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
                log.info("OS2L: connected to SoundSwitch at %s:%d", host, port)
                self.send(_HANDSHAKE)
                if not self.fast_reconnect:
                    self._send_init_defaults()
                self.fast_reconnect = False
            except (OSError, ConnectionRefusedError) as exc:
                log.info("OS2L: connect failed %s:%d (%s) — retry in 3 s", host, port, exc)
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
            log.info("SoundSwitchDiscovery: DNS-SD browser started")
        except Exception as exc:
            log.warning("SoundSwitchDiscovery: could not start DNS-SD: %s — using fallback", exc)

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
                log.info("SoundSwitchDiscovery: service info not ready for %s", name)
                return
            ipv4 = next((addr for addr in info.addresses if len(addr) == 4), None)
            if not ipv4:
                log.info("SoundSwitchDiscovery: no IPv4 address for %s", name)
                return
            host = socket.inet_ntoa(ipv4)
            port = info.port
            log.info("SoundSwitchDiscovery: found %s at %s:%d", name, host, port)
            self._conn.set_endpoint(host, port)
        except Exception as exc:
            log.warning("SoundSwitchDiscovery: service info error: %s", exc)


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
        if bpm_out:
            self._sub(f"{dn} get_bpm", round(bpm_out, 2), verbose=True)

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
        self._sub(f"{dn} get_time elapsed absolute",
                  int(meta.elapsed_ms if hasattr(meta, "elapsed_ms") else 0) + TIMING_COMPENSATION_MS,
                  verbose=True)
        self._sub(f"{dn} play", play, verbose=True)

    def send_elapsed(self, deck: int, elapsed_ms: int, beatpos: float) -> None:
        dn = f"deck {deck}"
        self._sub(f"{dn} get_time elapsed absolute", elapsed_ms + TIMING_COMPENSATION_MS)
        self._sub(f"{dn} get_beatpos", round(beatpos, 4))

    def send_bpm(self, deck: int, bpm: float) -> None:
        self._sub(f"deck {deck} get_bpm", round(bpm, 2), verbose=True)

    def send_loop_on(self, deck: int, beats: int = AUTOLOOP_BEATS) -> None:
        self._sub(f"deck {deck} loop", "on", verbose=True)
        self._sub(f"deck {deck} get_loop", beats, verbose=True)

    def send_loop_off(self, deck: int) -> None:
        self._sub(f"deck {deck} loop", "off", verbose=True)
