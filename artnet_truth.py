"""Default-off Art-Net truth-check sink for SoundSwitch pack validation.

This is not a production lighting backend. It exists only to emit bridge shadow
render frames on Art-Net U1 for a one-shot SoundSwitch U0 comparison run.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .soundswitch_frame_sender import _build_artdmx, expand_ch1_ch19_to_512


ARTNET_PORT = 6454
TRUTH_CHECK_ENV = "RBSS_ARTNET_TRUTH_CHECK"
UNIVERSE_ENV = "RBSS_ARTNET_UNIVERSE"
TARGETS_ENV = "RBSS_ARTNET_TARGETS"
SIDECAR_ENV = "RBSS_ARTNET_TRUTH_SIDECAR"
QUEUE_BOUND_ENV = "RBSS_ARTNET_TRUTH_QUEUE_BOUND"
DEFAULT_SIDECAR_PATH = "/tmp/rbss_artnet_truth_frames.jsonl"
DEFAULT_QUEUE_BOUND = 2048


@dataclass(frozen=True)
class TruthCheckEnv:
    enabled: bool
    reason: str
    universe: int | None = None
    targets: tuple[str, ...] = ()
    sidecar_path: str = DEFAULT_SIDECAR_PATH
    queue_bound: int = DEFAULT_QUEUE_BOUND


@dataclass(frozen=True)
class _TruthFrame:
    sequence: int
    frame_512: bytes
    row: dict[str, Any]


def load_truth_check_env(
    env: Mapping[str, str] | None = None,
    *,
    lan_ip_resolver: Callable[[], str] | None = None,
) -> TruthCheckEnv:
    data = os.environ if env is None else env
    if data.get(TRUTH_CHECK_ENV, "0") != "1":
        return TruthCheckEnv(False, "disabled")
    universe_raw = data.get(UNIVERSE_ENV, "")
    try:
        universe = int(universe_raw)
    except (TypeError, ValueError):
        return TruthCheckEnv(False, "invalid_universe")
    if not 0 <= universe <= 0x7FFF:
        return TruthCheckEnv(False, "invalid_universe")
    targets = _targets(data.get(TARGETS_ENV), lan_ip_resolver=lan_ip_resolver)
    if not targets:
        return TruthCheckEnv(False, "invalid_targets")
    try:
        queue_bound = int(data.get(QUEUE_BOUND_ENV, str(DEFAULT_QUEUE_BOUND)))
    except (TypeError, ValueError):
        return TruthCheckEnv(False, "invalid_queue_bound")
    if queue_bound <= 0:
        return TruthCheckEnv(False, "invalid_queue_bound")
    sidecar_path = data.get(SIDECAR_ENV, DEFAULT_SIDECAR_PATH) or DEFAULT_SIDECAR_PATH
    return TruthCheckEnv(True, "artnet_truth_check", universe, targets, sidecar_path, queue_bound)


def _targets(
    raw: str | None,
    *,
    lan_ip_resolver: Callable[[], str] | None,
) -> tuple[str, ...]:
    if raw:
        candidates = tuple(part.strip() for part in raw.split(",") if part.strip())
    else:
        resolver = lan_ip_resolver or _default_lan_ip
        candidates = ("127.0.0.1", resolver())
    out: list[str] = []
    for item in candidates:
        if not item:
            continue
        try:
            ipaddress.ip_address(item)
        except ValueError:
            return ()
        if item not in out:
            out.append(item)
    return tuple(out)


def _default_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        return "127.0.0.1"


class ArtNetTruthSink:
    """Bounded non-blocking U1 Art-Net validation sink."""

    def __init__(
        self,
        *,
        universe: int,
        fixture_map: Mapping[int, int],
        targets: tuple[str, ...],
        sidecar_path: str,
        pack_sha256: str = "",
        queue_bound: int = DEFAULT_QUEUE_BOUND,
        socket_factory: Callable[[], Any] | None = None,
        sidecar_opener: Callable[..., Any] = open,
        run_id: str | None = None,
    ) -> None:
        self._universe = int(universe)
        self._fixture_map = dict(fixture_map)
        self._targets = tuple(targets)
        self._sidecar_path = str(sidecar_path)
        self._pack_sha256 = str(pack_sha256 or "")
        self._pack_sha12 = self._pack_sha256[:12]
        self._queue: queue.Queue[_TruthFrame] = queue.Queue(maxsize=max(1, int(queue_bound)))
        self._socket_factory = socket_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        self._sidecar_opener = sidecar_opener
        self._run_id = run_id or uuid.uuid4().hex
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sock = None
        self._sidecar = None
        self._sequence = 0
        self._frame_index = 0
        self._submitted_count = 0
        self._sent_count = 0
        self._dropped_count = 0
        self._overflow_count = 0
        self._send_error_count = 0
        self._sidecar_error = ""
        self._started = False
        self._lock = threading.Lock()
        self._visible_gate_dmx_address = int(self._fixture_map.get(1, 1))

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def pack_sha256(self) -> str:
        return self._pack_sha256

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        try:
            self._sock = self._socket_factory()
        except Exception as exc:
            self._send_error_count += 1
            self._sock = None
            self._sidecar_error = self._sidecar_error or f"socket:{type(exc).__name__}"
        try:
            self._sidecar = self._sidecar_opener(self._sidecar_path, "w", encoding="utf-8")
            self._write_sidecar({
                "type": "header",
                "run_id": self._run_id,
                "timestamp": time.time(),
                "pid": os.getpid(),
                "universe": self._universe,
                "targets": list(self._targets),
                "pack_sha256": self._pack_sha256,
                "pack_sha12": self._pack_sha12,
                "visible_gate_channel": 1,
                "visible_gate_dmx_address": self._visible_gate_dmx_address,
                "queue_bound": self._queue.maxsize,
            })
        except Exception as exc:
            self._sidecar = None
            self._sidecar_error = f"sidecar:{type(exc).__name__}"
        self._thread = threading.Thread(target=self._run, name="artnet-truth-check", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        if self._sidecar is not None:
            try:
                self._sidecar.close()
            except Exception:
                pass
            self._sidecar = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def submit_frame(self, frame_19: tuple[int, ...], intent: Mapping[str, Any] | None = None) -> None:
        frame_512 = bytes(expand_ch1_ch19_to_512(tuple(frame_19), self._fixture_map))
        with self._lock:
            sequence = self._next_sequence_locked()
            self._frame_index += 1
            frame_index = self._frame_index
            self._submitted_count += 1
        dmx_hash = hashlib.sha256(frame_512).hexdigest()
        gate_idx = max(1, min(512, self._visible_gate_dmx_address)) - 1
        gate_value = frame_512[gate_idx]
        row = {
            "type": "frame",
            "run_id": self._run_id,
            "sequence": sequence,
            "frame_index": frame_index,
            "dmx_sha256": dmx_hash,
            "visible_gate_channel": 1,
            "visible_gate_dmx_address": self._visible_gate_dmx_address,
            "visible_gate_value": gate_value,
            "visible": bool(gate_value),
            "active_dark": bool(not gate_value and _truthy_content(intent)),
            "pack_sha256": self._pack_sha256,
        }
        row.update(_jsonable_mapping(intent or {}))
        try:
            self._queue.put_nowait(_TruthFrame(sequence, frame_512, row))
        except queue.Full:
            with self._lock:
                self._dropped_count += 1
                self._overflow_count += 1

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": True,
                "run_id": self._run_id,
                "universe": self._universe,
                "targets": list(self._targets),
                "sidecar_path": self._sidecar_path,
                "current_sequence": self._sequence,
                "submitted_count": self._submitted_count,
                "sent_count": self._sent_count,
                "dropped_count": self._dropped_count,
                "overflow_count": self._overflow_count,
                "send_error_count": self._send_error_count,
                "sidecar_error": self._sidecar_error,
                "queue_depth": self._queue.qsize(),
                "queue_bound": self._queue.maxsize,
                "pack_sha256": self._pack_sha256,
                "pack_sha12": self._pack_sha12,
                "ch1_dmx_address": self._visible_gate_dmx_address,
                "running": bool(self._thread and self._thread.is_alive()),
            }

    def _next_sequence_locked(self) -> int:
        self._sequence = 1 if self._sequence >= 255 else self._sequence + 1
        return self._sequence

    def _run(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._write_sidecar(item.row)
            packet = _build_artdmx(self._universe, item.frame_512, sequence=item.sequence)
            if self._sock is not None:
                for target in self._targets:
                    try:
                        self._sock.sendto(packet, (target, ARTNET_PORT))
                    except Exception:
                        with self._lock:
                            self._send_error_count += 1
            with self._lock:
                self._sent_count += 1
            self._queue.task_done()

    def _write_sidecar(self, row: Mapping[str, Any]) -> None:
        handle = self._sidecar
        if handle is None:
            return
        try:
            handle.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
        except Exception as exc:
            self._sidecar_error = f"sidecar:{type(exc).__name__}"


def _truthy_content(intent: Mapping[str, Any] | None) -> bool:
    if not intent:
        return False
    return bool(
        intent.get("scripted_active")
        or intent.get("static_held")
        or intent.get("blackout")
        or str(intent.get("mode", "")) in {"scripted", "autoloop", "static", "blackout"}
    )


def _jsonable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if item is None or isinstance(item, (str, int, float, bool)):
            out[key] = item
        elif isinstance(item, Mapping):
            out[key] = _jsonable_mapping(item)
        elif isinstance(item, (list, tuple)):
            out[key] = [
                x if x is None or isinstance(x, (str, int, float, bool)) else str(x)
                for x in item
            ]
        else:
            out[key] = str(item)
    return out


def disabled_truth_status(reason: str = "disabled") -> dict[str, Any]:
    return {
        "enabled": False,
        "reason": reason,
        "run_id": "",
        "universe": None,
        "targets": [],
        "sidecar_path": "",
        "current_sequence": 0,
        "dropped_count": 0,
        "overflow_count": 0,
        "send_error_count": 0,
        "sidecar_error": "",
        "pack_sha256": "",
        "ch1_dmx_address": None,
    }


__all__ = [
    "ARTNET_PORT",
    "ArtNetTruthSink",
    "DEFAULT_QUEUE_BOUND",
    "DEFAULT_SIDECAR_PATH",
    "QUEUE_BOUND_ENV",
    "SIDECAR_ENV",
    "TARGETS_ENV",
    "TRUTH_CHECK_ENV",
    "TruthCheckEnv",
    "UNIVERSE_ENV",
    "disabled_truth_status",
    "load_truth_check_env",
]
