"""tests/test_enttec_dmx_pro.py — Pure-software tests for enttec_dmx_pro.py.

No serial/Enttec/hardware port opened in this test file.  Serial I/O is
exercised via FakeSerial injected through the port_factory argument of
SoundSwitchDmxWorker.

Byte-equivalence target is the VLN reference (~/virtuallasernode/calib/dmx_pro.py)
confirmed 2026-06-21.  The known-good blackout packet (518 bytes) is:
  7E 06 01 02 00 <512x00> E7
"""
import logging
import signal
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

# Ensure the package parent is importable regardless of how tests are discovered.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_fmt
from rb_ss_bridge_v2 import enttec_dmx_pro as edp
from rb_ss_bridge_v2.enttec_dmx_pro import (
    MSG_START,
    MSG_END,
    LABEL_SEND_DMX,
    DMX_START_CODE,
    build_dmx_packet,
    _ZERO_PACKET,
    SoundSwitchDmxWorker,
    find_enttec_port,
    resolve_enttec_port,
)


def _capture(logger_name: str):
    logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    prior_level = logger.level
    logger.setLevel(logging.DEBUG)
    return logger, handler, prior_level, records

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
        self.assertEqual(
            set(s),
            {
                "worker", "port", "running", "sent_count", "error_count",
                "last_error", "mailbox_depth", "connected", "reconnect_count",
            },
        )
        self.assertFalse(s["connected"])
        self.assertEqual(s["reconnect_count"], 0)

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


class TestSoundSwitchDmxWorkerHealthTransitions(unittest.TestCase):
    """AWR-125 W4: health.dmx edge-triggered emits + thread_guard coverage.

    CONFIRMATION: No serial/Enttec/hardware port opened in any test in this class.
    """

    def setUp(self) -> None:
        bridge_fmt.reset_rate_state()

    def _make_worker(self, fake, **kwargs) -> "SoundSwitchDmxWorker":
        return SoundSwitchDmxWorker(
            port="/dev/fake_test_port",
            port_factory=lambda *_a, **_kw: fake,
            **kwargs,
        )

    def _feed_frames_until(self, worker, predicate, *, timeout_s: float = 1.0) -> None:
        """Keep queuing frames (mailbox maxlen=2, worker drains repeatedly) until
        *predicate* is satisfied or *timeout_s* elapses."""
        pkt = build_dmx_packet(bytearray(512))
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and not predicate():
            worker.put_frame(pkt)
            time.sleep(0.01)

    def _wait_until(self, predicate, *, timeout_s: float = 1.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and not predicate():
            time.sleep(0.005)
        self.assertTrue(predicate(), "timed out waiting for worker state")

    def test_write_error_emits_once_per_failure_streak(self):
        """One write-error edge per outage; reconnect failures must not re-arm it."""
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError("FakeSerial: simulated write failure"))
        factory_calls = 0

        def factory(_port: str):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 1:
                return dead
            raise OSError("still disconnected")

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.005,
        )
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            self._feed_frames_until(
                worker, lambda: any("write error" in r.getMessage() for r in records),
            )
            # Keep feeding briefly after the first record to prove the streak stays silent.
            self._feed_frames_until(worker, lambda: False, timeout_s=0.15)
            worker.stop()

        write_errors = [r for r in records if "write error" in r.getMessage()]
        self.assertEqual(len(write_errors), 1, f"expected one write-error record, got {records!r}")
        self.assertEqual(write_errors[0].levelname, "WARNING")

    def test_write_error_closes_dead_handle_and_reconnects(self):
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        fresh = FakeSerial()
        factory_calls: list[str] = []

        def factory(port: str):
            factory_calls.append(port)
            return dead if len(factory_calls) == 1 else fresh

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        packet = build_dmx_packet(bytearray([42]))
        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            try:
                worker.put_frame(packet)
                self._wait_until(lambda: dead.closed)
                worker.put_frame(packet)
                self._wait_until(lambda: packet in fresh.writes)
            finally:
                worker.stop()

        self.assertEqual(factory_calls, ["/dev/fake_test_port", "/dev/fake_reconnected"])
        self.assertIn(packet, fresh.writes)

    def test_one_outage_logs_single_reconnect_not_write_recovered(self):
        """Write error → N failed reconnects → success → next good write:
        exactly one write-error, one reconnect-pending, one reconnected; zero write-recovered.
        """
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        fresh = FakeSerial()
        factory_calls = 0

        def factory(_port: str):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 1:
                return dead
            if factory_calls <= 3:
                raise OSError(6, "Device not configured")
            return fresh

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        packet = build_dmx_packet(bytearray([42]))
        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            try:
                worker.put_frame(packet)
                self._wait_until(lambda: dead.closed)
                self._feed_frames_until(
                    worker,
                    lambda: any("reconnected" in r.getMessage() for r in records),
                    timeout_s=2.0,
                )
                worker.put_frame(packet)
                self._wait_until(lambda: packet in fresh.writes)
                # Give one more drain cycle so a sticky write-recovered would appear.
                time.sleep(0.05)
            finally:
                worker.stop()

        msgs = [r.getMessage() for r in records]
        write_errors = [m for m in msgs if "write error" in m]
        pending = [m for m in msgs if "reconnect pending" in m]
        reconnected = [m for m in msgs if "reconnected" in m]
        recovered = [m for m in msgs if "write recovered" in m]
        self.assertEqual(len(write_errors), 1, f"expected one write-error, got {msgs!r}")
        self.assertEqual(len(pending), 1, f"expected one reconnect-pending, got {msgs!r}")
        self.assertEqual(len(reconnected), 1, f"expected one reconnected, got {msgs!r}")
        self.assertEqual(len(recovered), 0, f"expected zero write-recovered, got {msgs!r}")
        self.assertTrue(
            any(r.levelname == "INFO" and "reconnected" in r.getMessage() for r in records),
        )

    def test_two_workers_do_not_suppress_each_others_reconnect_edges(self):
        """Per-instance edge keys: worker A's pending edge must not hide worker B's."""
        dead_a = FakeSerial()
        dead_a.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        dead_b = FakeSerial()
        dead_b.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        calls_a = 0
        calls_b = 0

        def factory_a(_port: str):
            nonlocal calls_a
            calls_a += 1
            if calls_a == 1:
                return dead_a
            raise OSError(6, "Device not configured")

        def factory_b(_port: str):
            nonlocal calls_b
            calls_b += 1
            if calls_b == 1:
                return dead_b
            raise OSError(6, "Device not configured")

        worker_a = SoundSwitchDmxWorker(
            port="/dev/fake_a", port_factory=factory_a, poll_s=0.002,
        )
        worker_b = SoundSwitchDmxWorker(
            port="/dev/fake_b", port_factory=factory_b, poll_s=0.002,
        )
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", side_effect=lambda p: p):
            worker_a.start()
            worker_b.start()
            try:
                worker_a.put_frame(build_dmx_packet(bytearray([1])))
                self._wait_until(lambda: calls_a >= 2)
                worker_b.put_frame(build_dmx_packet(bytearray([2])))
                self._wait_until(
                    lambda: sum(1 for r in records if "reconnect pending" in r.getMessage()) >= 2,
                )
            finally:
                worker_a.stop()
                worker_b.stop()

        pending = [r for r in records if "reconnect pending" in r.getMessage()]
        self.assertGreaterEqual(
            len(pending), 2,
            f"expected both workers to emit reconnect-pending, got {records!r}",
        )

    def test_stop_during_blocked_reconnect_sends_only_zero_on_fresh_handle(self):
        """stop() while reconnect factory is in-flight must not send a live frame."""
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        fresh = FakeSerial()
        entered = threading.Event()
        release = threading.Event()
        factory_calls = 0

        def factory(_port: str):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 1:
                return dead
            entered.set()
            self.assertTrue(release.wait(timeout=2.0), "factory release timed out")
            return fresh

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        nonzero = build_dmx_packet(bytearray([99]))
        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            worker.put_frame(nonzero)
            self._wait_until(lambda: dead.closed)
            worker.put_frame(nonzero)  # sits in mailbox while factory blocks
            self._wait_until(entered.is_set)

            stop_done = threading.Event()
            stop_exc: list[BaseException] = []

            def _stop():
                try:
                    worker.stop()
                except BaseException as exc:  # noqa: BLE001 — capture for assertion
                    stop_exc.append(exc)
                finally:
                    stop_done.set()

            stopper = threading.Thread(target=_stop, name="stop-during-reconnect")
            stopper.start()
            # Give stop() a moment to set the event before releasing the factory.
            time.sleep(0.05)
            release.set()
            self.assertTrue(stop_done.wait(timeout=2.0), "stop() did not complete")
            stopper.join(timeout=1.0)

        self.assertEqual(stop_exc, [])
        self.assertFalse(worker.status()["running"])
        self.assertEqual(
            fresh.writes, [_ZERO_PACKET],
            f"fresh handle must receive only the shutdown zero, got {fresh.writes!r}",
        )
        self.assertTrue(fresh.closed)

    def test_mailbox_frame_not_sent_after_stop_drain_check(self):
        """A frame drained after stop is set must not be transmitted (path b)."""
        fake = FakeSerial()
        worker = self._make_worker(fake, poll_s=0.002)
        drained = threading.Event()
        release_send = threading.Event()
        original_drain = worker._drain_mailbox

        def gated_drain():
            packet = original_drain()
            if packet is not None and not drained.is_set():
                drained.set()
                self.assertTrue(release_send.wait(timeout=2.0), "send-gate release timed out")
            return packet

        worker._drain_mailbox = gated_drain  # type: ignore[method-assign]
        nonzero = build_dmx_packet(bytearray([77]))
        worker.start()
        try:
            worker.put_frame(nonzero)
            self._wait_until(drained.is_set)
            # Arm stop while the worker is held between drain and send, then release.
            worker._stop_event.set()
            release_send.set()
            worker.stop()
        finally:
            release_send.set()
            if worker.status()["running"]:
                worker.stop()

        data_writes = [w for w in fake.writes if w != _ZERO_PACKET]
        self.assertNotIn(nonzero, data_writes, f"nonzero frame sent after stop: {fake.writes!r}")
        self.assertIn(_ZERO_PACKET, fake.writes)

    def test_reconnect_failure_retries_and_updates_status(self):
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        fresh = FakeSerial()
        factory_calls = 0

        def factory(_port: str):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 1:
                return dead
            if factory_calls == 2:
                raise OSError(6, "Device not configured")
            return fresh

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.05), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            try:
                worker.put_frame(build_dmx_packet(bytearray([42])))
                self._wait_until(lambda: factory_calls >= 2)
                self.assertFalse(worker.status()["connected"])
                self._feed_frames_until(
                    worker,
                    lambda: worker.status()["connected"]
                    and worker.status()["reconnect_count"] == 1,
                )
                self.assertTrue(worker.status()["connected"])
                self.assertEqual(worker.status()["reconnect_count"], 1)
            finally:
                worker.stop()

        self.assertEqual(factory_calls, 3)

    def test_reconnect_resolves_port_before_factory(self):
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        fresh = FakeSerial()
        factory_calls: list[str] = []

        def factory(port: str):
            factory_calls.append(port)
            return dead if len(factory_calls) == 1 else fresh

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        packet = build_dmx_packet(bytearray([42]))
        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(
                    edp, "resolve_enttec_port", return_value="/dev/cu.usbserial-NEW",
                ) as resolve:
            worker.start()
            try:
                worker.put_frame(packet)
                self._wait_until(lambda: dead.closed)
                worker.put_frame(packet)
                self._wait_until(lambda: packet in fresh.writes)
            finally:
                worker.stop()

        resolve.assert_called_once_with("/dev/fake_test_port")
        self.assertEqual(factory_calls, ["/dev/fake_test_port", "/dev/cu.usbserial-NEW"])

    def test_stop_during_outage_joins_cleanly(self):
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        factory_calls = 0

        def factory(_port: str):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 1:
                return dead
            raise OSError(6, "Device not configured")

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            worker.put_frame(build_dmx_packet(bytearray([42])))
            self._wait_until(lambda: factory_calls >= 2)
            started = time.monotonic()
            worker.stop()

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertFalse(worker.status()["running"])

    def test_reconnect_pending_logs_once_per_outage(self):
        dead = FakeSerial()
        dead.write = mock.Mock(side_effect=OSError(6, "Device not configured"))
        factory_calls = 0

        def factory(_port: str):
            nonlocal factory_calls
            factory_calls += 1
            if factory_calls == 1:
                return dead
            raise OSError(6, "Device not configured")

        worker = SoundSwitchDmxWorker(
            port="/dev/fake_test_port", port_factory=factory, poll_s=0.002,
        )
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        with mock.patch.object(edp, "_RECONNECT_INTERVAL_S", 0.01), \
                mock.patch.object(edp, "resolve_enttec_port", return_value="/dev/fake_reconnected"):
            worker.start()
            try:
                worker.put_frame(build_dmx_packet(bytearray([42])))
                self._wait_until(lambda: factory_calls >= 4)
            finally:
                worker.stop()

        pending = [r for r in records if "reconnect pending" in r.getMessage()]
        self.assertEqual(len(pending), 1, f"expected one reconnect-pending record, got {records!r}")

    def test_port_open_failure_emits_health_dmx_error(self):
        def _boom(*_a, **_kw):
            raise RuntimeError("synthetic open failure")

        worker = SoundSwitchDmxWorker(port="/dev/fake_failure", port_factory=_boom)
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        worker.start()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not records:
            time.sleep(0.01)
        worker.stop()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "ERROR")
        self.assertIn("failed to open port", records[0].getMessage())

    def test_run_loop_thread_guard_emits_started_and_exited(self):
        worker = self._make_worker(FakeSerial(), poll_s=0.01)
        logger, handler, prior_level, records = _capture("sys.thread")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        worker.start()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not any(
            "SoundSwitchDmxWorker started" in r.getMessage() for r in records
        ):
            time.sleep(0.01)
        worker.stop()

        self.assertTrue(any("SoundSwitchDmxWorker started" in r.getMessage() for r in records))
        self.assertTrue(any("SoundSwitchDmxWorker exited" in r.getMessage() for r in records))


# ---------------------------------------------------------------------------
# Port auto-detection — no serial/Enttec/hardware port opened
# ---------------------------------------------------------------------------

def _fake_port(device: str, vid=None, manufacturer=None, product=None,
               description=None, hwid=None, serial_number=None):
    """A stand-in for a pyserial ListPortInfo.

    Only the attributes find_enttec_port reads are populated; unset identity
    fields default to None, exactly as pyserial reports them when the OS can't
    supply a descriptor string.  (vid / serial_number are kept for realistic
    fakes; positive identity is decided by the manufacturer/product/description/
    hwid strings, never by the generic FTDI VID or the device name.)
    """
    return types.SimpleNamespace(
        device=device, vid=vid, manufacturer=manufacturer, product=product,
        description=description, hwid=hwid, serial_number=serial_number,
    )


# A realistic positively-identified Enttec DMX USB Pro (macOS descriptor strings).
def _enttec_port(device: str, **overrides):
    kw = dict(vid=0x0403, manufacturer="ENTTEC", product="DMX USB PRO",
              serial_number="EN123456")
    kw.update(overrides)
    return _fake_port(device, **kw)


def _fake_serial_tools(ports):
    """Return a sys.modules patch that makes ``from serial.tools import
    list_ports`` resolve to a fake whose ``comports()`` yields *ports*.

    Works whether or not pyserial is actually installed — the fake fully
    overrides the ``serial`` import chain for the duration of the patch.
    """
    fake_list_ports = types.ModuleType("serial.tools.list_ports")
    fake_list_ports.comports = lambda: list(ports)
    fake_tools = types.ModuleType("serial.tools")
    fake_tools.list_ports = fake_list_ports
    fake_serial = types.ModuleType("serial")
    fake_serial.tools = fake_tools
    return mock.patch.dict(sys.modules, {
        "serial": fake_serial,
        "serial.tools": fake_tools,
        "serial.tools.list_ports": fake_list_ports,
    })


class TestFindEnttecPort(unittest.TestCase):
    """find_enttec_port returns a device ONLY on positive ENTTEC identity, and
    only when exactly one such device is present.

    CONFIRMATION: No serial/Enttec/hardware port opened in any test in this class.
    """

    def test_no_ports_returns_none(self):
        """No ports at all -> None."""
        with _fake_serial_tools([]):
            self.assertIsNone(find_enttec_port())

    def test_lone_generic_ftdi_is_rejected(self):
        """A single generic FTDI adapter (VID 0x0403, generic descriptor) is NOT
        positive ENTTEC identity -> None (fail closed, require configured port).

        This is the core wrong-device guard: FTDI is a generic vendor, so a bare
        0x0403 VID must never be opened as the DMX output.
        """
        ports = [_fake_port(
            "/dev/cu.usbserial-A50285BI", vid=0x0403,
            manufacturer="FTDI", product="FT232R USB UART",
            description="FT232R USB UART",
            hwid="USB VID:PID=0403:6001 SER=A50285BI LOCATION=20-1",
        )]
        with _fake_serial_tools(ports):
            self.assertIsNone(find_enttec_port())

    def test_lone_generic_usbserial_name_is_rejected(self):
        """A single device whose node is named 'usbserial' but carries NO ENTTEC
        identity string is rejected -> None. The device name is not identity."""
        ports = [_fake_port(
            "/dev/cu.usbserial-1420", vid=None,
            manufacturer="Silicon Labs", product="CP2102 USB to UART Bridge",
            description="CP2102 USB to UART Bridge Controller",
        )]
        with _fake_serial_tools(ports):
            self.assertIsNone(find_enttec_port())

    def test_lone_positive_enttec_returns_device(self):
        """A single positively-identified Enttec (ENTTEC manufacturer + DMX USB
        PRO product) -> its device path."""
        ports = [
            _fake_port("/dev/cu.Bluetooth-Incoming-Port", vid=None),
            _enttec_port("/dev/cu.usbserial-EN123456"),
        ]
        with _fake_serial_tools(ports):
            self.assertEqual(find_enttec_port(), "/dev/cu.usbserial-EN123456")

    def test_positive_by_product_string_only(self):
        """Product 'DMX USB PRO' alone is positive identity even if manufacturer
        is missing (OS-dependent descriptor availability)."""
        ports = [_fake_port(
            "/dev/cu.usbserial-EN777777", vid=0x0403,
            product="DMX USB PRO", description="DMX USB PRO",
        )]
        with _fake_serial_tools(ports):
            self.assertEqual(find_enttec_port(), "/dev/cu.usbserial-EN777777")

    def test_positive_by_manufacturer_string_only(self):
        """Manufacturer 'ENTTEC' alone is positive identity."""
        ports = [_fake_port(
            "/dev/cu.usbmodemEN888888", vid=0x0403, manufacturer="Enttec",
        )]
        with _fake_serial_tools(ports):
            self.assertEqual(find_enttec_port(), "/dev/cu.usbmodemEN888888")

    def test_positive_enttec_wins_over_generic_ftdi_sibling(self):
        """One positively-identified Enttec alongside a generic FTDI adapter is
        unambiguous -> the Enttec. The generic FTDI is not a candidate at all."""
        ports = [
            _fake_port("/dev/cu.usbserial-A50285BI", vid=0x0403,
                       manufacturer="FTDI", product="FT232R USB UART"),
            _enttec_port("/dev/cu.usbserial-EN123456"),
        ]
        with _fake_serial_tools(ports):
            self.assertEqual(find_enttec_port(), "/dev/cu.usbserial-EN123456")

    def test_two_positive_enttec_are_ambiguous_returns_none(self):
        """Two positively-identified Enttec devices are genuinely ambiguous ->
        None (never guess which is the real output)."""
        ports = [
            _enttec_port("/dev/cu.usbserial-EN111111"),
            _enttec_port("/dev/cu.usbserial-EN222222"),
        ]
        with _fake_serial_tools(ports):
            self.assertIsNone(find_enttec_port())

    def test_missing_pyserial_returns_none(self):
        """If pyserial is not importable, find_enttec_port fails closed to None."""
        with mock.patch.dict(sys.modules, {
            "serial": None,
            "serial.tools": None,
            "serial.tools.list_ports": None,
        }):
            self.assertIsNone(find_enttec_port())


class TestResolveEnttecPort(unittest.TestCase):
    """resolve_enttec_port prefers an existing configured port, else a lone
    auto-detected Enttec, else the configured value unchanged (fail-closed).

    CONFIRMATION: No serial/Enttec/hardware port opened in any test in this class.
    """

    def test_prefers_existing_configured_path(self):
        """An on-disk configured port wins and auto-detect is never consulted."""
        ports = [_fake_port("/dev/cu.usbserial-OTHER", vid=0x0403)]
        with mock.patch.object(edp.Path, "exists", return_value=True), \
                _fake_serial_tools(ports):
            self.assertEqual(
                resolve_enttec_port("/dev/cu.usbserial-CONFIGURED"),
                "/dev/cu.usbserial-CONFIGURED",
            )

    def test_falls_back_to_autodetect_when_configured_missing(self):
        """A configured path that is not on disk falls back to the lone,
        positively-identified Enttec."""
        ports = [_enttec_port("/dev/cu.usbserial-EN999999")]
        with mock.patch.object(edp.Path, "exists", return_value=False), \
                _fake_serial_tools(ports):
            self.assertEqual(
                resolve_enttec_port("/dev/cu.usbserial-GONE"),
                "/dev/cu.usbserial-EN999999",
            )

    def test_generic_ftdi_does_not_satisfy_autodetect_fallback(self):
        """When the configured port is gone and the only device present is a
        generic FTDI (no ENTTEC identity), resolve fails closed to the configured
        value unchanged — it never adopts a stranger's adapter."""
        ports = [_fake_port("/dev/cu.usbserial-A50285BI", vid=0x0403,
                             manufacturer="FTDI", product="FT232R USB UART")]
        with mock.patch.object(edp.Path, "exists", return_value=False), \
                _fake_serial_tools(ports):
            self.assertEqual(
                resolve_enttec_port("/dev/cu.usbserial-GONE"),
                "/dev/cu.usbserial-GONE",
            )

    def test_fails_closed_to_configured_when_nothing_found(self):
        """No on-disk port and no lone auto-detect -> configured value unchanged."""
        with mock.patch.object(edp.Path, "exists", return_value=False), \
                _fake_serial_tools([]):
            self.assertEqual(
                resolve_enttec_port("/dev/cu.usbserial-GONE"),
                "/dev/cu.usbserial-GONE",
            )


if __name__ == "__main__":
    unittest.main()
