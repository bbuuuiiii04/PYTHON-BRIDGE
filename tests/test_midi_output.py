"""
Tests for Issue #10: MidiOutput transport for Laser Director.
"""
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_models import LaserMidiMessage  # noqa: E402
from rb_ss_bridge_v2.midi_output import MidiOutput  # noqa: E402


def _wait_until(predicate, timeout_s: float = 0.75, step_s: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return predicate()


class _RecordingPort:
    def __init__(self) -> None:
        self.messages = []
        self.closed = False
        self.first_note_off_at = None

    def send(self, message) -> None:
        now = time.monotonic()
        self.messages.append((now, message))
        if getattr(message, "type", "") == "note_off" and self.first_note_off_at is None:
            self.first_note_off_at = now

    def close(self) -> None:
        self.closed = True


class _FailingPort:
    def send(self, _message) -> None:
        raise OSError("send failed")

    def close(self) -> None:
        return None


def _fake_mido_module(port):
    class _FakeMessage:
        def __init__(self, msg_type, **kwargs):
            self.type = msg_type
            self.kwargs = kwargs

    return SimpleNamespace(
        open_output=lambda _name: port,
        Message=lambda msg_type, **kwargs: _FakeMessage(msg_type, **kwargs),
    )


class MidiOutputTests(unittest.TestCase):
    def test_dry_run_start_does_not_import_mido(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=True)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module") as import_mod:
            out.start()
            out.stop()
        import_mod.assert_not_called()

    def test_dry_run_trigger(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=True)
        out.start()
        try:
            ok = out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=60, velocity=100))
            self.assertTrue(ok)
            self.assertTrue(_wait_until(lambda: out.status()["sent_count"] >= 1))
            status = out.status()
            self.assertEqual(status["trigger_count"], 1)
            self.assertEqual(status["drop_count"], 0)
        finally:
            out.stop()

    def test_queue_full_drop_count_and_false_return(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=True, queue_maxsize=1)
        msg = LaserMidiMessage(kind="note_on", channel=1, note=60, velocity=100)
        self.assertTrue(out.trigger(msg))
        self.assertFalse(out.trigger(msg))
        status = out.status()
        self.assertEqual(status["drop_count"], 1)
        self.assertEqual(status["rejected_count"], 1)

    def test_missing_dependency_dry_run_still_works(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=True)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", side_effect=ImportError("no mido")):
            out.start()
            try:
                self.assertTrue(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=64, velocity=90)))
                self.assertTrue(_wait_until(lambda: out.status()["sent_count"] >= 1))
                self.assertFalse(out.status()["degraded"])
            finally:
                out.stop()

    def test_missing_dependency_live_degrades(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", side_effect=ImportError("no mido")):
            out.start()
            try:
                status = out.status()
                self.assertTrue(status["degraded"])
                self.assertEqual(status["degraded_reason"], "dependency_missing")
                self.assertFalse(
                    out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=64, velocity=90))
                )
                self.assertEqual(out.status()["drop_count"], 1)
            finally:
                out.stop()

    def test_send_error_increments_counter(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(_FailingPort())
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                self.assertTrue(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=65, velocity=110)))
                self.assertTrue(_wait_until(lambda: out.status()["send_error_count"] >= 1))
                status = out.status()
                self.assertTrue(status["degraded"])
                self.assertEqual(status["degraded_reason"], "send_error")
            finally:
                out.stop()

    def test_status_shape(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=True)
        keys = set(out.status().keys())
        expected = {
            "available",
            "running",
            "dry_run",
            "degraded",
            "degraded_reason",
            "port_name",
            "queue_size",
            "queue_max",
            "trigger_count",
            "drop_count",
            "rejected_count",
            "send_error_count",
            "sent_count",
            "panic_count",
            "last_error",
        }
        self.assertEqual(keys, expected)

    def test_panic_not_blocked_by_long_pulse(self) -> None:
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                pulse = LaserMidiMessage(kind="note_pulse", channel=1, note=60, velocity=120, duration_ms=10000)
                self.assertTrue(out.trigger(pulse))
                self.assertTrue(
                    _wait_until(
                        lambda: any(m.type == "note_on" for _, m in port.messages),
                        timeout_s=0.4,
                    ),
                    msg="note_on should be sent before panic timing check",
                )
                panic_started = time.monotonic()
                out.panic()
                ok = _wait_until(lambda: port.first_note_off_at is not None, timeout_s=0.4)
                self.assertTrue(ok, msg="note_off should be sent quickly after panic")
                self.assertLess(port.first_note_off_at - panic_started, 0.25)
            finally:
                out.stop()

        # Panic in live mode must target all 16 channels.
        panic_msgs = [m for _, m in port.messages if m.type == "control_change" and m.kwargs.get("control") == 123]
        self.assertGreaterEqual(len(panic_msgs), 16)
        channels = {m.kwargs.get("channel") for m in panic_msgs}
        self.assertEqual(channels, set(range(16)))

    def test_trigger_returns_false_live_when_degraded(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", side_effect=ImportError("no mido")):
            out.start()
            try:
                ok = out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=61, velocity=100))
                self.assertFalse(ok)
                status = out.status()
                self.assertEqual(status["drop_count"], 1)
                self.assertEqual(status["rejected_count"], 1)
            finally:
                out.stop()

    def test_stop_is_safe_and_idempotent(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=True)
        out.start()
        t0 = time.monotonic()
        out.stop()
        out.stop()
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
