from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.artnet_truth import ArtNetTruthSink, TruthCheckEnv, load_truth_check_env
from rb_ss_bridge_v2.soundswitch_frame_sender import _build_artdmx


FULL_FIXTURE_MAP = {ch: ch for ch in range(1, 20)}


class _FakeSocket:
    def __init__(self) -> None:
        self.sends: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, packet: bytes, target: tuple[str, int]) -> None:
        self.sends.append((bytes(packet), target))

    def close(self) -> None:
        self.closed = True


class _FakeSidecar:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.closed = False

    def write(self, text: str) -> None:
        self.lines.append(text)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class ArtNetTruthTests(unittest.TestCase):
    def test_build_artdmx_packet_structure_with_sequence(self) -> None:
        frame = bytes([1, 2, 3])
        packet = _build_artdmx(1, frame, sequence=7)
        self.assertEqual(packet[:8], b"Art-Net\x00")
        self.assertEqual(packet[8:10], b"\x00\x50")
        self.assertEqual(packet[10:12], b"\x00\x0e")
        self.assertEqual(packet[12], 7)
        self.assertEqual(int.from_bytes(packet[14:16], "little"), 1)
        self.assertEqual(int.from_bytes(packet[16:18], "big"), 512)
        self.assertEqual(len(packet), 530)
        self.assertEqual(packet[18:21], b"\x01\x02\x03")

    def test_env_requires_truth_check_flag_and_valid_universe(self) -> None:
        self.assertFalse(load_truth_check_env({"RBSS_ARTNET_UNIVERSE": "1"}).enabled)
        self.assertEqual(
            load_truth_check_env({
                "RBSS_ARTNET_TRUTH_CHECK": "1",
                "RBSS_ARTNET_UNIVERSE": "bad",
            }).reason,
            "invalid_universe",
        )
        enabled = load_truth_check_env({
            "RBSS_ARTNET_TRUTH_CHECK": "1",
            "RBSS_ARTNET_UNIVERSE": "1",
            "RBSS_ARTNET_TARGETS": "127.0.0.1",
        })
        self.assertTrue(enabled.enabled)
        self.assertEqual(enabled.targets, ("127.0.0.1",))

    def test_sink_writes_sidecar_and_sends_fake_udp(self) -> None:
        fake_socket = _FakeSocket()
        fake_sidecar = _FakeSidecar()
        sink = ArtNetTruthSink(
            universe=1,
            fixture_map=FULL_FIXTURE_MAP,
            targets=("127.0.0.1",),
            sidecar_path="/tmp/fake.jsonl",
            pack_sha256="a" * 64,
            queue_bound=8,
            socket_factory=lambda: fake_socket,
            sidecar_opener=lambda *_a, **_kw: fake_sidecar,
            run_id="run1",
        )
        sink.start()
        sink.submit_frame((9,) + (0,) * 18, {"mode": "scripted", "scripted_active": True})
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not fake_socket.sends:
            time.sleep(0.01)
        sink.stop()

        self.assertEqual(len(fake_socket.sends), 1)
        self.assertEqual(fake_socket.sends[0][1], ("127.0.0.1", 6454))
        header = json.loads(fake_sidecar.lines[0])
        row = json.loads(fake_sidecar.lines[1])
        self.assertEqual(header["type"], "header")
        self.assertEqual(header["run_id"], "run1")
        self.assertEqual(row["type"], "frame")
        self.assertEqual(row["run_id"], "run1")
        self.assertEqual(row["sequence"], 1)
        self.assertEqual(row["visible_gate_dmx_address"], 1)
        self.assertEqual(row["visible_gate_value"], 9)
        self.assertTrue(row["visible"])
        self.assertEqual(row["mode"], "scripted")
        self.assertEqual(len(row["dmx_sha256"]), 64)

    def test_sequence_wrap_and_queue_overflow_are_statused(self) -> None:
        sink = ArtNetTruthSink(
            universe=1,
            fixture_map=FULL_FIXTURE_MAP,
            targets=("127.0.0.1",),
            sidecar_path="/tmp/fake.jsonl",
            queue_bound=300,
            socket_factory=_FakeSocket,
            sidecar_opener=lambda *_a, **_kw: _FakeSidecar(),
            run_id="run2",
        )
        for _ in range(256):
            sink.submit_frame((0,) * 19, {})
        self.assertEqual(sink.status()["current_sequence"], 1)

        tiny = ArtNetTruthSink(
            universe=1,
            fixture_map=FULL_FIXTURE_MAP,
            targets=("127.0.0.1",),
            sidecar_path="/tmp/fake.jsonl",
            queue_bound=1,
            socket_factory=_FakeSocket,
            sidecar_opener=lambda *_a, **_kw: _FakeSidecar(),
            run_id="run3",
        )
        tiny.submit_frame((0,) * 19, {})
        tiny.submit_frame((0,) * 19, {})
        self.assertEqual(tiny.status()["overflow_count"], 1)


if __name__ == "__main__":
    unittest.main()
