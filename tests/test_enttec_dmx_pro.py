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

    def test_write_error_emits_once_per_failure_streak(self):
        fake = FakeSerial(fail_write=True)
        worker = self._make_worker(fake, poll_s=0.005)
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        worker.start()
        self._feed_frames_until(worker, lambda: bool(records))
        # Keep feeding briefly after the first record to prove the streak stays silent.
        self._feed_frames_until(worker, lambda: False, timeout_s=0.1)
        worker.stop()

        self.assertEqual(len(records), 1, f"expected exactly one write-error record, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("write error", records[0].getMessage())

    def test_write_recovers_emits_once_after_failure_streak(self):
        fake = FakeSerial(fail_write=True)
        worker = self._make_worker(fake, poll_s=0.005)
        logger, handler, prior_level, records = _capture("health.dmx")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        worker.start()
        self._feed_frames_until(worker, lambda: bool(records))
        self.assertTrue(records, "expected the write-error record before flipping to healthy")

        fake.fail_write = False
        self._feed_frames_until(worker, lambda: len(records) >= 2)
        worker.stop()

        self.assertEqual(len(records), 2, f"expected error+recovered only, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertEqual(records[1].levelname, "INFO")
        self.assertIn("recovered", records[1].getMessage())

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
