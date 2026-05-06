"""
File-driven OS2L injection for controlled SoundSwitch validation.

This is intentionally small and operational: append one JSON object per line to
the command file and the running bridge sends those packets through its existing
OS2LConnection.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from .config import AUTOLOOP_BEATS
from .osl_output import OS2LConnection

log = logging.getLogger("os2l_injector")

DEFAULT_INJECT_PATH = "/tmp/rbss_os2l_inject.jsonl"
INJECT_PATH_ENV = "RBSS_OS2L_INJECT_PATH"


class OS2LInjector:
    """Watches a jsonl command file and sends packets through the bridge socket."""

    def __init__(self, conn: OS2LConnection, path: str | None = None) -> None:
        self._conn = conn
        self.path = path or os.environ.get(INJECT_PATH_ENV, DEFAULT_INJECT_PATH)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset = 0

    def start(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        open(self.path, "a", encoding="utf-8").close()
        self._offset = os.path.getsize(self.path)
        self._thread = threading.Thread(target=self._watch_loop, name="os2l-injector", daemon=True)
        self._thread.start()
        log.info("[INJECT] watching %s", self.path)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _watch_loop(self) -> None:
        while not self._stop.is_set():
            try:
                size = os.path.getsize(self.path)
                if size < self._offset:
                    self._offset = 0
                if size > self._offset:
                    with open(self.path, "r", encoding="utf-8") as fh:
                        fh.seek(self._offset)
                        for raw in fh:
                            line = raw.strip()
                            if line:
                                self._handle_line(line)
                        self._offset = fh.tell()
            except FileNotFoundError:
                open(self.path, "a", encoding="utf-8").close()
                self._offset = 0
            except Exception:
                log.exception("[INJECT] watcher error")
            time.sleep(0.1)

    def _handle_line(self, line: str) -> None:
        try:
            command = json.loads(line)
        except json.JSONDecodeError as exc:
            log.warning("[INJECT] invalid json: %s", exc)
            return
        try:
            packets = self._packets_for(command)
        except Exception as exc:
            log.warning("[INJECT] invalid command %s: %s", command, exc)
            return
        for packet in packets:
            self._conn.send(packet, verbose=True)
        log.info("[INJECT] sent cmd=%s packets=%d", command.get("cmd", "raw"), len(packets))

    def _packets_for(self, command: dict[str, Any]) -> list[dict[str, Any]]:
        if "packet" in command:
            return [dict(command["packet"])]
        if "packets" in command:
            return [dict(packet) for packet in command["packets"]]

        cmd = str(command.get("cmd", "")).lower()
        decks = _decks(command.get("decks"))
        if cmd == "clear":
            return _clear_packets(decks)
        if cmd == "bpm":
            return [{"evt": "subscribed", "trigger": f"deck {d} get_bpm", "value": float(command["bpm"])}
                    for d in decks]
        if cmd == "loop_on":
            beats = int(command.get("beats", AUTOLOOP_BEATS))
            return _loop_on_packets(decks, beats)
        if cmd == "beat_change":
            bpm = float(command["bpm"])
            pos = int(command["pos"])
            return [{"evt": "beat", "deck": d, "bpm": round(bpm, 2), "pos": pos, "change": True}
                    for d in decks]
        if cmd == "arm":
            return _arm_packets(command, decks)
        raise ValueError("expected packet, packets, or known cmd")


def _decks(value: Any) -> list[int]:
    if value is None:
        return [1, 2, 3, 4]
    decks = [int(deck) for deck in value]
    if not decks:
        raise ValueError("decks must not be empty")
    return decks


def _clear_packets(decks: list[int]) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for deck in decks:
        dn = f"deck {deck}"
        packets.extend([
            {"evt": "subscribed", "trigger": f"{dn} get_text '%SOUNDSWITCH_ID'", "value": ""},
            {"evt": "subscribed", "trigger": f"{dn} get_filepath", "value": ""},
            {"evt": "subscribed", "trigger": f"{dn} loop", "value": "off"},
            {"evt": "subscribed", "trigger": f"{dn} play", "value": "off"},
        ])
    return packets


def _loop_on_packets(decks: list[int], beats: int) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for deck in decks:
        packets.extend([
            {"evt": "subscribed", "trigger": f"deck {deck} loop", "value": "on"},
            {"evt": "subscribed", "trigger": f"deck {deck} get_loop", "value": beats},
        ])
    return packets


def _arm_packets(command: dict[str, Any], decks: list[int]) -> list[dict[str, Any]]:
    filepath = str(command["filepath"])
    title = str(command.get("title") or os.path.basename(filepath).rsplit(".", 1)[0])
    bpm = float(command.get("bpm", 0.0))
    firstbeat = int(command.get("firstbeat", 0))
    elapsed = int(command.get("elapsed_ms", 0))
    total = command.get("total_ms")
    beats = int(command.get("beats", AUTOLOOP_BEATS))
    packets: list[dict[str, Any]] = []
    for deck in decks:
        dn = f"deck {deck}"
        packets.extend([
            {"evt": "subscribed", "trigger": f"{dn} get_text '%SOUNDSWITCH_ID'",
             "value": "{00000000-0000-0000-0000-000000000000}"},
            {"evt": "subscribed", "trigger": f"{dn} get_firstbeat", "value": firstbeat},
        ])
        if bpm > 0:
            packets.append({"evt": "subscribed", "trigger": f"{dn} get_bpm", "value": round(bpm, 2)})
        packets.extend([
            {"evt": "subscribed", "trigger": f"{dn} song_title", "value": title},
            {"evt": "subscribed", "trigger": f"{dn} song_artist", "value": ""},
            {"evt": "subscribed", "trigger": f"{dn} loop", "value": "on"},
            {"evt": "subscribed", "trigger": f"{dn} get_loop", "value": beats},
            {"evt": "subscribed", "trigger": f"{dn} get_filepath", "value": filepath},
        ])
        if total is not None:
            packets.append({"evt": "subscribed", "trigger": f"{dn} get_time total absolute",
                            "value": int(total)})
        packets.extend([
            {"evt": "subscribed", "trigger": f"{dn} get_time elapsed absolute", "value": elapsed},
            {"evt": "subscribed", "trigger": f"{dn} play", "value": str(command.get("play", "on"))},
        ])
    return packets
