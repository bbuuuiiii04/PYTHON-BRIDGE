"""tests/test_soundswitch_frame_sender.py — Tests for soundswitch_frame_sender.py.

No serial/Enttec/hardware port opened in this test file.  All serial I/O is
stubbed via FakeSerial injected through port_factory.

CONFIRMATION: No serial/Enttec/hardware port opened in this test.

SoundSwitch pack semantic proof comes from the pack-generation proof gate
(Task 0.5), not from this module or from VLN.
"""
import sys
import time
import unittest
from pathlib import Path

# Ensure the package parent is importable regardless of how tests are discovered.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.enttec_dmx_pro import build_dmx_packet, _ZERO_PACKET
from rb_ss_bridge_v2.soundswitch_frame_sender import expand_ch1_ch19_to_512, SoundSwitchFrameSender


# ---------------------------------------------------------------------------
# FakeSerial (same pattern as test_enttec_dmx_pro.py)
# ---------------------------------------------------------------------------

class FakeSerial:
    """In-memory serial substitute.  No hardware, no OS ports opened.

    CONFIRMATION: No serial/Enttec/hardware port opened in this test.
    """

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flushed: int = 0
        self.closed: bool = False

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))

    def flush(self) -> None:
        self.flushed += 1

    def close(self) -> None:
        self.closed = True


def _fake_factory(fake: FakeSerial):
    """Return a port_factory that always yields the given FakeSerial."""
    def factory(port, **_kw):
        return fake
    return factory


# ---------------------------------------------------------------------------
# Fixture map used across tests
#
# A minimal 2-fixture map:
#   CH1 (SoundSwitch channel 1)  → DMX address 1
#   CH8 (SoundSwitch channel 8)  → DMX address 8
#   CH19 (SoundSwitch channel 19) → DMX address 19
# ---------------------------------------------------------------------------

SIMPLE_FIXTURE_MAP = {
    1: 1,
    8: 8,
    19: 19,
}

# A denser fixture map reflecting a real 19-channel fixture block at base 1.
FULL_FIXTURE_MAP = {ch: ch for ch in range(1, 20)}  # CH1→DMX1 … CH19→DMX19


# ---------------------------------------------------------------------------
# Tests for expand_ch1_ch19_to_512 (pure function)
# ---------------------------------------------------------------------------

class TestExpandCh1Ch19To512(unittest.TestCase):

    def test_output_is_512_bytes(self):
        """Output is always exactly 512 bytes."""
        out = expand_ch1_ch19_to_512((0,) * 19, FULL_FIXTURE_MAP)
        self.assertIsInstance(out, bytearray)
        self.assertEqual(len(out), 512)

    def test_known_values_placed_correctly(self):
        """Channel values are placed at the correct 0-based DMX byte offset."""
        frame = tuple(range(1, 20))  # CH1=1, CH2=2, ..., CH19=19
        out = expand_ch1_ch19_to_512(frame, FULL_FIXTURE_MAP)
        for ch in range(1, 20):
            dmx_addr = FULL_FIXTURE_MAP[ch]
            byte_idx = dmx_addr - 1  # 1-based → 0-based
            expected = ch  # frame[ch-1] == ch
            self.assertEqual(
                out[byte_idx], expected,
                f"CH{ch} → DMX{dmx_addr} (idx {byte_idx}): expected {expected}, got {out[byte_idx]}"
            )

    def test_zero_frame_produces_all_zeros(self):
        """A zero frame produces a 512-byte buffer of zeros."""
        out = expand_ch1_ch19_to_512((0,) * 19, FULL_FIXTURE_MAP)
        self.assertEqual(out, bytearray(512))

    def test_sparse_fixture_map_leaves_others_zero(self):
        """Only mapped channels are written; all other DMX addresses are 0."""
        frame = (255,) + (0,) * 18  # CH1=255, rest 0
        fixture_map = {1: 100}  # CH1 → DMX address 100
        out = expand_ch1_ch19_to_512(frame, fixture_map)
        self.assertEqual(out[99], 255)   # DMX address 100 → index 99
        self.assertEqual(out[0], 0)      # DMX address 1 not in map
        self.assertEqual(out[98], 0)     # DMX address 99 not in map
        self.assertEqual(out[100], 0)    # DMX address 101 not in map

    def test_addresses_from_fixture_map_only_not_from_names(self):
        """Physical address comes from fixture_map only.  CH8 at DMX address 42."""
        frame = (0,) * 7 + (200,) + (0,) * 11  # CH8 = 200
        fixture_map = {8: 42}  # CH8 → DMX address 42, NOT address 8
        out = expand_ch1_ch19_to_512(frame, fixture_map)
        self.assertEqual(out[41], 200)  # address 42 → index 41
        self.assertEqual(out[7], 0)     # natural index 7 (address 8) must be 0

    def test_ch19_boundary(self):
        """CH19 is the last valid channel; higher ch_numbers are ignored."""
        frame = (0,) * 18 + (99,)  # CH19 = 99
        fixture_map = {19: 512}
        out = expand_ch1_ch19_to_512(frame, fixture_map)
        self.assertEqual(out[511], 99)  # DMX address 512 → index 511

    def test_out_of_range_channel_ignored(self):
        """ch_number > 19 or dmx_address > 512 must be silently ignored."""
        frame = (0,) * 19
        fixture_map = {20: 1, 1: 600}  # both out of valid range
        out = expand_ch1_ch19_to_512(frame, fixture_map)
        self.assertEqual(out, bytearray(512))

    def test_short_frame_tuple_treated_as_zero(self):
        """Missing channel values default to 0."""
        frame = (77,)  # only CH1 provided; CH2..CH19 default to 0
        out = expand_ch1_ch19_to_512(frame, FULL_FIXTURE_MAP)
        self.assertEqual(out[0], 77)   # CH1 → index 0
        self.assertEqual(out[1], 0)    # CH2 → index 1 (missing → 0)

    def test_max_value_255(self):
        """Channel value 255 is passed through unchanged."""
        frame = (255,) * 19
        out = expand_ch1_ch19_to_512(frame, FULL_FIXTURE_MAP)
        for ch in range(1, 20):
            self.assertEqual(out[ch - 1], 255)


# ---------------------------------------------------------------------------
# Tests for SoundSwitchFrameSender
# ---------------------------------------------------------------------------

class TestSoundSwitchFrameSender(unittest.TestCase):
    """CONFIRMATION: No serial/Enttec/hardware port opened in any test here."""

    def _make_sender(self, **kwargs) -> tuple["SoundSwitchFrameSender", FakeSerial]:
        fake = FakeSerial()
        kwargs.setdefault("poll_s", 0.005)
        fixture_map = kwargs.pop("fixture_map", FULL_FIXTURE_MAP)
        sender = SoundSwitchFrameSender(
            port="/dev/fake_test_port",
            fixture_map=fixture_map,
            port_factory=_fake_factory(fake),
            **kwargs,
        )
        return sender, fake

    def test_no_hardware_port_opened(self):
        """Sender created with FakeSerial factory must never open a real port."""
        opened_real = []

        def _reject_real(port, **_kw):
            opened_real.append(port)
            raise RuntimeError("REAL serial port opened — forbidden in tests!")

        sender = SoundSwitchFrameSender(
            port="/dev/should_never_open",
            fixture_map=FULL_FIXTURE_MAP,
            port_factory=lambda *a, **kw: FakeSerial(),
        )
        sender.start()
        time.sleep(0.05)
        sender.stop()
        self.assertEqual(opened_real, [], "Real serial port was opened — forbidden!")

    def test_async_port_open_failure_is_reported_by_start(self):
        """start() must not report pack-ready before the worker opens its port."""
        def _fail_after_thread_starts(_port, **_kw):
            time.sleep(0.01)
            raise OSError("synthetic open failure")

        sender = SoundSwitchFrameSender(
            port="/dev/fake_failure",
            fixture_map=FULL_FIXTURE_MAP,
            port_factory=_fail_after_thread_starts,
        )
        with self.assertRaisesRegex(RuntimeError, "failed to open"):
            sender.start(readiness_timeout_s=0.5)
        self.assertTrue(sender.status()["stopped"])
        self.assertFalse(sender.status()["worker"]["running"])

    def test_stop_before_start_is_safe_for_startup_rollback(self):
        """A constructed-but-never-started sender must stop cleanly (no port open).

        This is the partial-start rollback path: when controller input fails to
        start, __main__ calls frame_sender.stop() on a sender whose worker thread
        never ran.  It must not open the serial port, hang, or raise.
        """
        opened_real = []

        def _tracking_factory(port, **_kw):
            opened_real.append(port)
            return FakeSerial()

        sender = SoundSwitchFrameSender(
            port="/dev/should_never_open",
            fixture_map=FULL_FIXTURE_MAP,
            port_factory=_tracking_factory,
        )
        sender.stop()  # never started — must be safe and idempotent
        sender.stop()
        self.assertEqual(opened_real, [], "Serial port opened during rollback — forbidden!")
        self.assertTrue(sender.status()["stopped"])
        self.assertFalse(sender.status()["worker"]["running"])

    def test_submit_sends_expanded_frame(self):
        """submit() must expand CH1-CH19 and transmit the correct DMX packet."""
        fixture_map = {channel: 100 + channel for channel in range(1, 20)}
        sender, fake = self._make_sender(fixture_map=fixture_map)
        sender.start()

        frame = (200,) + (0,) * 18  # CH1=200
        sender.submit(frame)

        # Wait for worker to drain mailbox.
        deadline = time.monotonic() + 1.0
        expected_dmx = expand_ch1_ch19_to_512(frame, fixture_map)
        expected_pkt = build_dmx_packet(expected_dmx)
        while time.monotonic() < deadline:
            if any(w == expected_pkt for w in fake.writes):
                break
            time.sleep(0.01)
        sender.stop()
        self.assertIn(expected_pkt, fake.writes, "Expected expanded DMX packet not found in writes")

    def test_zero_and_stop_pushes_zero_packet(self):
        """zero_and_stop() must enqueue the zero packet before stopping."""
        sender, fake = self._make_sender()
        sender.start()
        time.sleep(0.05)
        sender.zero_and_stop()
        # Give the worker a moment to drain.
        time.sleep(0.1)
        self.assertIn(_ZERO_PACKET, fake.writes, "zero_and_stop() did not push a zero packet")

    def test_stop_closes_serial(self):
        """stop() must close the underlying serial handle."""
        sender, fake = self._make_sender()
        sender.start()
        time.sleep(0.05)
        sender.stop()
        self.assertTrue(fake.closed, "Serial port was not closed after stop()")

    def test_mailbox_latest_frame_only(self):
        """When multiple frames are submitted rapidly, only the latest is sent
        (bounded mailbox with maxlen=2 in the worker)."""
        sender, fake = self._make_sender(poll_s=0.5)  # slow drain
        sender.start()

        fm = FULL_FIXTURE_MAP
        frame_a = (10,) + (0,) * 18
        frame_b = (20,) + (0,) * 18
        frame_c = (30,) + (0,) * 18
        pkt_a = build_dmx_packet(expand_ch1_ch19_to_512(frame_a, fm))
        pkt_b = build_dmx_packet(expand_ch1_ch19_to_512(frame_b, fm))
        pkt_c = build_dmx_packet(expand_ch1_ch19_to_512(frame_c, fm))

        sender.submit(frame_a)
        sender.submit(frame_b)
        sender.submit(frame_c)

        time.sleep(0.7)
        sender.stop()

        data_writes = [w for w in fake.writes if w != _ZERO_PACKET]
        self.assertNotIn(pkt_a, data_writes, "Stale frame pkt_a should have been evicted")

    def test_status_keys(self):
        """status() must return the expected diagnostic keys."""
        sender, _ = self._make_sender()
        s = sender.status()
        for key in ("sender", "stopped", "submit_count", "zero_count",
                    "idle_blackout_s", "seconds_since_last_submit", "worker"):
            self.assertIn(key, s, f"Missing status key: {key}")
        self.assertNotIn("port", s)
        self.assertNotIn("/dev/fake_test_port", repr(s))
        self.assertNotIn("last_error", s["worker"])

    def test_submit_count_increments(self):
        """status()['submit_count'] increments on each submit() call."""
        sender, fake = self._make_sender()
        sender.start()
        fm = FULL_FIXTURE_MAP
        sender.submit((0,) * 19)
        sender.submit((0,) * 19)
        sender.submit((0,) * 19)
        sender.stop()
        self.assertEqual(sender.status()["submit_count"], 3)

    def test_submit_after_stop_is_noop(self):
        """Calling submit() after stop() must not raise and must not increment count."""
        sender, fake = self._make_sender()
        sender.start()
        sender.stop()
        # submit after stop — must not raise
        sender.submit((50,) + (0,) * 18)
        self.assertEqual(sender.status()["submit_count"], 0)

    def test_idle_blackout_fires(self):
        """With idle_blackout_s set, a zero packet is pushed after the idle timeout."""
        sender, fake = self._make_sender(idle_blackout_s=0.2)
        sender.start()
        # Do not call submit() — let the idle watchdog fire.
        time.sleep(0.6)
        sender.stop()
        # We expect at least one zero packet from the idle watchdog.
        zero_writes = [w for w in fake.writes if w == _ZERO_PACKET]
        self.assertTrue(len(zero_writes) >= 1, "Idle blackout zero packet never fired")

    def test_zero_frame_expansion_produces_zero_packet(self):
        """A zero 19-channel frame expands to the standard zero DMX packet."""
        frame = (0,) * 19
        dmx = expand_ch1_ch19_to_512(frame, FULL_FIXTURE_MAP)
        pkt = build_dmx_packet(dmx)
        self.assertEqual(pkt, _ZERO_PACKET)

    def test_constructor_rejects_incomplete_or_invalid_fixture_map(self):
        with self.assertRaisesRegex(ValueError, "exactly CH1..CH19"):
            SoundSwitchFrameSender(port="unused", fixture_map={1: 1})
        invalid = dict(FULL_FIXTURE_MAP)
        invalid[1] = True
        with self.assertRaisesRegex(ValueError, "integers from 1 to 512"):
            SoundSwitchFrameSender(port="unused", fixture_map=invalid)


if __name__ == "__main__":
    unittest.main()
