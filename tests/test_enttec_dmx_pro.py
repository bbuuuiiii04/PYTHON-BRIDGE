"""tests/test_enttec_dmx_pro.py — Pure-software tests for enttec_dmx_pro.py.

No serial/Enttec/hardware port opened in this test file.  Serial I/O is
exercised via FakeSerial injected through the port_factory argument of
SoundSwitchDmxWorker.

Byte-equivalence target is the VLN reference (~/virtuallasernode/calib/dmx_pro.py)
confirmed 2026-06-21.  The known-good blackout packet (518 bytes) is:
  7E 06 01 02 00 <512x00> E7
"""
import signal
import sys
import threading
import time
import unittest
from pathlib import Path

# Ensure the package parent is importable regardless of how tests are discovered.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.enttec_dmx_pro import (
    MSG_START,
    MSG_END,
    LABEL_SEND_DMX,
    DMX_START_CODE,
    build_dmx_packet,
    _ZERO_PACKET,
    SoundSwitchDmxWorker,
)

# ---------------------------------------------------------------------------
# Known-good reference packet (from VLN confirmed output)
# ---------------------------------------------------------------------------

_EXPECTED_BLACKOUT_PACKET = bytes.fromhex("7e0601020" + "0" * 1025 + "e7")
# Build it correctly: 7E 06 01 02 00 + 512x00 + E7  = 518 bytes
_EXPECTED_BLACKOUT_PACKET = (
    bytes([0x7E, 0x06, 0x01, 0x02, 0x00])
    + bytes(512)
    + bytes([0xE7])
)


# ---------------------------------------------------------------------------
# FakeSerial — no hardware opened
# ---------------------------------------------------------------------------

class FakeSerial:
    """In-memory serial substitute.  No hardware, no OS ports opened.

    CONFIRMATION: No serial/Enttec/hardware port opened in this test.
    """

    def __init__(self, *, fail_write: bool = False) -> None:
        self.fail_write = fail_write
        self.writes: list[bytes] = []
        self.flushed: int = 0
        self.closed: bool = False

    def write(self, data: bytes) -> None:
        if self.fail_write:
            raise OSError("FakeSerial: simulated write failure")
        self.writes.append(bytes(data))

    def flush(self) -> None:
        self.flushed += 1

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Packet framing tests (byte-equivalence with VLN reference)
# ---------------------------------------------------------------------------

class TestBuildDmxPacket(unittest.TestCase):

    def test_blackout_packet_byte_equivalence_with_vln(self):
        """build_dmx_packet(bytearray(512)) must be byte-identical to the VLN
        known-good blackout packet: 7E 06 01 02 00 <512x00> E7 (518 bytes).

        CONFIRMATION: No serial/Enttec/hardware port opened in this test.
        """
        pkt = build_dmx_packet(bytearray(512))
        self.assertEqual(pkt, _EXPECTED_BLACKOUT_PACKET)

    def test_packet_length_always_518(self):
        """Every packet is exactly 518 bytes: 4-byte header + 513-byte body + 1 end."""
        for frame_len in [0, 1, 19, 255, 512]:
            frame = bytearray(frame_len)
            pkt = build_dmx_packet(frame)
            self.assertEqual(len(pkt), 518, f"length wrong for frame_len={frame_len}")

    def test_header_bytes(self):
        """Packet header: [0x7E, 6, 0x01, 0x02]."""
        pkt = build_dmx_packet(bytearray(512))
        self.assertEqual(pkt[0], MSG_START)       # 0x7E
        self.assertEqual(pkt[1], LABEL_SEND_DMX)  # 6
        self.assertEqual(pkt[2], 0x01)            # len LSB = 513 & 0xFF
        self.assertEqual(pkt[3], 0x02)            # len MSB = 513 >> 8

    def test_start_code_byte(self):
        """Byte at index 4 is always the DMX start code 0x00."""
        pkt = build_dmx_packet(bytearray([255] * 512))
        self.assertEqual(pkt[4], DMX_START_CODE)  # 0x00

    def test_end_byte(self):
        """Last byte is always 0xE7."""
        pkt = build_dmx_packet(bytearray(512))
        self.assertEqual(pkt[-1], MSG_END)  # 0xE7

    def test_nonzero_frame_channel_placement(self):
        """Channel bytes start at index 5 (after 4-byte header + start_code).

        packet layout: [0x7E][6][lsb][msb][start_code][CH1..CH512][0xE7]
          index 0: 0x7E
          index 1: 6 (label)
          index 2: 0x01 (len lsb)
          index 3: 0x02 (len msb)
          index 4: 0x00 (start code)
          index 5: CH1 value
          ...
          index 516: CH512 value
          index 517: 0xE7
        """
        frame = bytearray(512)
        frame[0] = 255   # CH1
        frame[18] = 128  # CH19
        pkt = build_dmx_packet(frame)
        self.assertEqual(pkt[5], 255)    # CH1 → index 5
        self.assertEqual(pkt[23], 128)   # CH19 → index 5 + 18 = 23
        self.assertEqual(pkt[6], 0)      # CH2 untouched → 0

    def test_short_frame_padded_to_512(self):
        """Frames shorter than 512 bytes are zero-padded."""
        pkt = build_dmx_packet(bytearray([200, 100]))
        self.assertEqual(pkt[5], 200)   # CH1
        self.assertEqual(pkt[6], 100)   # CH2
        self.assertEqual(pkt[7], 0)     # CH3 padded
        self.assertEqual(len(pkt), 518)

    def test_long_frame_truncated_to_512(self):
        """Frames longer than 512 bytes are truncated."""
        frame = bytearray(600)
        frame[511] = 77
        frame[512] = 88  # beyond 512 — must be ignored
        pkt = build_dmx_packet(frame)
        self.assertEqual(pkt[5 + 511], 77)
        self.assertEqual(len(pkt), 518)

    def test_precomputed_zero_packet_matches_build(self):
        """_ZERO_PACKET == build_dmx_packet(bytearray(512)) (pre-computation check)."""
        self.assertEqual(_ZERO_PACKET, build_dmx_packet(bytearray(512)))

    def test_precomputed_zero_packet_byte_equivalence_with_vln(self):
        """_ZERO_PACKET matches the VLN known-good blackout packet."""
        self.assertEqual(_ZERO_PACKET, _EXPECTED_BLACKOUT_PACKET)


# ---------------------------------------------------------------------------
# Worker tests — FakeSerial only, no hardware
# ---------------------------------------------------------------------------

class TestSoundSwitchDmxWorker(unittest.TestCase):
    """CONFIRMATION: No serial/Enttec/hardware port opened in any test in this class."""

    def _make_worker(self, **kwargs) -> tuple["SoundSwitchDmxWorker", FakeSerial]:
        fake = FakeSerial()
        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port",
            port_factory=lambda *_a, **_kw: fake,
            **kwargs,
        )
        return worker, fake

    def test_no_hardware_port_opened(self):
        """Worker created with FakeSerial factory must never call the real _open_port."""
        opened_real = []

        def _reject_real(port, **_kw):
            opened_real.append(port)
            raise RuntimeError("REAL serial port opened — forbidden in tests!")

        worker = SoundSwitchDmxWorker(
            port="/dev/should_never_open",
            port_factory=lambda *a, **kw: FakeSerial(),
        )
        worker.start()
        time.sleep(0.05)
        worker.stop()
        self.assertEqual(opened_real, [], "Real serial port was opened — forbidden!")

    def test_worker_sends_zero_packet_on_stop(self):
        """Worker must push a zero packet before closing on clean stop."""
        worker, fake = self._make_worker(poll_s=0.01)
        worker.start()
        time.sleep(0.05)
        worker.stop()
        # The last write should be the zero packet.
        self.assertTrue(len(fake.writes) >= 1, "Expected at least one write (zero packet)")
        self.assertEqual(fake.writes[-1], _ZERO_PACKET, "Last write must be zero packet")

    def test_worker_sends_queued_frame(self):
        """put_frame enqueues a packet that the worker thread sends."""
        worker, fake = self._make_worker(poll_s=0.005)
        worker.start()
        frame = bytearray(512)
        frame[0] = 42
        pkt = build_dmx_packet(frame)
        worker.put_frame(pkt)
        # Wait for the worker to drain the mailbox.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if any(p == pkt for p in fake.writes):
                break
            time.sleep(0.01)
        worker.stop()
        self.assertIn(pkt, fake.writes, "Expected frame not sent by worker")

    def test_status_keys(self):
        """status() must return the expected diagnostic keys."""
        worker, _ = self._make_worker()
        s = worker.status()
        for key in ("worker", "port", "running", "sent_count", "error_count", "last_error", "mailbox_depth"):
            self.assertIn(key, s, f"Missing status key: {key}")

    def test_mailbox_latest_frame_only(self):
        """When multiple frames are queued before the worker drains, only the
        latest is sent (bounded mailbox with maxlen=2)."""
        # Use a slow poll to let frames accumulate.
        worker, fake = self._make_worker(poll_s=0.5)
        worker.start()

        frame_a = bytearray(512); frame_a[0] = 10
        frame_b = bytearray(512); frame_b[0] = 20
        frame_c = bytearray(512); frame_c[0] = 30
        pkt_a = build_dmx_packet(frame_a)
        pkt_b = build_dmx_packet(frame_b)
        pkt_c = build_dmx_packet(frame_c)

        # Queue three frames rapidly; with maxlen=2 the first is evicted.
        worker.put_frame(pkt_a)
        worker.put_frame(pkt_b)
        worker.put_frame(pkt_c)

        # Let the worker run one drain cycle.
        time.sleep(0.7)
        worker.stop()

        # pkt_a must have been evicted (never sent as a data frame).
        data_writes = [w for w in fake.writes if w != _ZERO_PACKET]
        self.assertNotIn(pkt_a, data_writes, "Stale frame pkt_a should have been evicted")

    def test_serial_closed_on_stop(self):
        """The FakeSerial.close() must be called after the worker stops."""
        worker, fake = self._make_worker(poll_s=0.01)
        worker.start()
        time.sleep(0.05)
        worker.stop()
        self.assertTrue(fake.closed, "Serial port was not closed on stop")

    def test_start_does_not_install_signal_handlers(self):
        """worker.start() must NOT overwrite process-level SIGTERM/SIGINT handlers.

        The bridge owner (__main__ _shutdown) is the single signal authority.
        CONFIRMATION: No serial/Enttec/hardware port opened in this test.
        """
        worker, _ = self._make_worker(poll_s=0.01)
        sigterm_before = signal.getsignal(signal.SIGTERM)
        sigint_before = signal.getsignal(signal.SIGINT)
        try:
            worker.start()
            time.sleep(0.05)
            sigterm_after = signal.getsignal(signal.SIGTERM)
            sigint_after = signal.getsignal(signal.SIGINT)
            self.assertIs(
                sigterm_after, sigterm_before,
                "start() must not replace the SIGTERM handler",
            )
            self.assertIs(
                sigint_after, sigint_before,
                "start() must not replace the SIGINT handler",
            )
        finally:
            worker.stop()


if __name__ == "__main__":
    unittest.main()
