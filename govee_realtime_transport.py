"""UDP transport for Govee DreamView/Razer realtime frames."""
from __future__ import annotations

import base64
import json
import socket
import threading
from typing import Any, Iterable, Sequence

RGB = tuple[int, int, int]

DEFAULT_HEADER_BYTES = (0xBB, 0x00, 0xFA, 0xB0, 0x00)
DEFAULT_ACTIVATE_PT = "uwABsQEK"
DEFAULT_DEACTIVATE_PT = "uwABsQAL"


def _clamp_byte(value: Any) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(255, numeric))


class GoveeRealtimeTransport:
    """Small non-blocking UDP sender for realtime segment frames."""

    def __init__(
        self,
        ip: str,
        *,
        port: int = 4003,
        segments: int = 20,
        header_bytes: Sequence[int] = DEFAULT_HEADER_BYTES,
        stretch: bool = False,
        activate_pt: str = DEFAULT_ACTIVATE_PT,
        deactivate_pt: str = DEFAULT_DEACTIVATE_PT,
        sock: socket.socket | None = None,
    ) -> None:
        self.ip = str(ip)
        self.port = int(port)
        self.segments = int(segments)
        header = [_clamp_byte(v) for v in header_bytes]
        if len(header) < 5:
            header = list(DEFAULT_HEADER_BYTES)
        if stretch:
            header[4] = 0x01
        self.header_bytes = tuple(header)
        self.activate_pt = str(activate_pt or DEFAULT_ACTIVATE_PT)
        self.deactivate_pt = str(deactivate_pt or DEFAULT_DEACTIVATE_PT)
        self._sock = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._lock = threading.Lock()
        self.frames_sent = 0
        self.command_count = 0
        self.send_error_count = 0
        self.last_error = ""
        self.last_payload_bytes = 0

    @staticmethod
    def xor_checksum(data: bytes | Iterable[int]) -> int:
        result = 0
        for byte in data:
            result ^= int(byte) & 0xFF
        return result & 0xFF

    @staticmethod
    def build_packet(
        header_bytes: Sequence[int],
        segments: Sequence[RGB],
    ) -> bytes:
        packet = [_clamp_byte(v) for v in header_bytes] + [len(segments) & 0xFF]
        for r, g, b in segments:
            packet.extend([_clamp_byte(r), _clamp_byte(g), _clamp_byte(b)])
        packet.append(GoveeRealtimeTransport.xor_checksum(packet))
        return bytes(packet)

    def activate(self) -> bool:
        return self._send_razer_pt(self.activate_pt, command=True)

    def deactivate(self) -> bool:
        return self._send_razer_pt(self.deactivate_pt, command=True)

    def set_brightness(self, value: int) -> bool:
        payload = {
            "msg": {
                "cmd": "brightness",
                "data": {"value": max(0, min(100, int(value)))},
            }
        }
        return self._send_json(payload, command=True)

    def send_frame(self, rgb_list: Sequence[RGB]) -> bool:
        if len(rgb_list) != self.segments:
            with self._lock:
                self.send_error_count += 1
                self.last_error = "segment_count_mismatch"
            return False
        clean = [(_clamp_byte(r), _clamp_byte(g), _clamp_byte(b)) for r, g, b in rgb_list]
        packet = self.build_packet(self.header_bytes, clean)
        ok = self._send_razer_pt(base64.b64encode(packet).decode("utf-8"), command=False)
        if ok:
            with self._lock:
                self.frames_sent += 1
        return ok

    def blackout(self) -> bool:
        return self.send_frame([(0, 0, 0)] * max(0, self.segments))

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ip": self.ip,
                "port": self.port,
                "segments": self.segments,
                "frames_sent": self.frames_sent,
                "command_count": self.command_count,
                "send_error_count": self.send_error_count,
                "last_error": self.last_error,
                "last_payload_bytes": self.last_payload_bytes,
            }

    def _send_razer_pt(self, pt: str, *, command: bool) -> bool:
        payload = {"msg": {"cmd": "razer", "data": {"pt": pt}}}
        return self._send_json(payload, command=command)

    def _send_json(self, payload: dict[str, Any], *, command: bool) -> bool:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            self._sock.sendto(data, (self.ip, self.port))
        except (BlockingIOError, OSError) as exc:
            with self._lock:
                self.send_error_count += 1
                self.last_error = f"send_error:{exc.__class__.__name__}"
            return False
        with self._lock:
            self.last_payload_bytes = len(data)
            self.last_error = ""
            if command:
                self.command_count += 1
        return True


class GoveeRealtimeDryRunTransport:
    """No-network transport with the same surface for dry-run startup/tests."""

    def __init__(self, *, ip: str = "", port: int = 4003, segments: int = 20) -> None:
        self.ip = str(ip)
        self.port = int(port)
        self.segments = int(segments)
        self.frames_sent = 0
        self.command_count = 0
        self.send_error_count = 0
        self.last_error = ""
        self.last_payload_bytes = 0

    def activate(self) -> bool:
        self.command_count += 1
        return True

    def deactivate(self) -> bool:
        self.command_count += 1
        return True

    def set_brightness(self, value: int) -> bool:
        self.command_count += 1
        return True

    def send_frame(self, rgb_list: Sequence[RGB]) -> bool:
        if len(rgb_list) != self.segments:
            self.send_error_count += 1
            self.last_error = "segment_count_mismatch"
            return False
        self.frames_sent += 1
        self.last_error = ""
        return True

    def blackout(self) -> bool:
        return self.send_frame([(0, 0, 0)] * max(0, self.segments))

    def close(self) -> None:
        return None

    def status(self) -> dict[str, Any]:
        return {
            "ip": self.ip,
            "port": self.port,
            "segments": self.segments,
            "frames_sent": self.frames_sent,
            "command_count": self.command_count,
            "send_error_count": self.send_error_count,
            "last_error": self.last_error,
            "last_payload_bytes": self.last_payload_bytes,
        }
