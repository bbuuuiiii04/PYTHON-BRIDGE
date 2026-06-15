from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_realtime_transport import (  # noqa: E402
    DEFAULT_HEADER_BYTES,
    GoveeRealtimeTransport,
)


class _FakeSocket:
    def __init__(self) -> None:
        self.blocking = True
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def setblocking(self, value: bool) -> None:
        self.blocking = value

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        return len(data)

    def close(self) -> None:
        self.closed = True


class GoveeRealtimeTransportTests(unittest.TestCase):
    def test_build_packet_matches_probe_vector(self) -> None:
        packet = GoveeRealtimeTransport.build_packet(
            DEFAULT_HEADER_BYTES,
            [(255, 0, 0)] * 20,
        )

        self.assertEqual(len(packet), 67)
        self.assertEqual(
            packet,
            bytes([0xBB, 0x00, 0xFA, 0xB0, 0x00, 0x14] + [0xFF, 0x00, 0x00] * 20 + [0xE5]),
        )

    def test_send_frame_uses_razer_json_wrapper(self) -> None:
        sock = _FakeSocket()
        transport = GoveeRealtimeTransport(
            "192.168.0.219",
            segments=2,
            header_bytes=DEFAULT_HEADER_BYTES,
            sock=sock,
        )

        self.assertTrue(transport.send_frame([(300, -1, 1), (2, 3, 4)]))

        self.assertFalse(sock.blocking)
        data, address = sock.sent[-1]
        self.assertEqual(address, ("192.168.0.219", 4003))
        payload = json.loads(data.decode("utf-8"))
        packet = base64.b64decode(payload["msg"]["data"]["pt"])
        self.assertEqual(payload["msg"]["cmd"], "razer")
        self.assertEqual(packet[6:12], bytes([255, 0, 1, 2, 3, 4]))

    def test_send_frame_rejects_wrong_segment_count(self) -> None:
        transport = GoveeRealtimeTransport(
            "192.168.0.219",
            segments=2,
            sock=_FakeSocket(),
        )

        self.assertFalse(transport.send_frame([(1, 2, 3)]))
        self.assertEqual(transport.status()["last_error"], "segment_count_mismatch")

    def test_activate_deactivate_and_brightness_are_udp_json(self) -> None:
        sock = _FakeSocket()
        transport = GoveeRealtimeTransport(
            "192.168.0.219",
            segments=1,
            sock=sock,
        )

        self.assertTrue(transport.activate())
        self.assertTrue(transport.set_brightness(100))
        self.assertTrue(transport.deactivate())

        commands = [json.loads(data.decode("utf-8"))["msg"]["cmd"] for data, _ in sock.sent]
        self.assertEqual(commands, ["razer", "brightness", "razer"])
        self.assertEqual(transport.status()["command_count"], 3)


if __name__ == "__main__":
    unittest.main()
