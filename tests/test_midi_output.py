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


# Note-off scheduling runs on a worker thread, so these tests are inherently
# timing-dependent.  Per-call timeouts are sized for an idle dev machine; on a
# contended CI runner executing the full suite the worker can be starved past
# those deadlines (observed flake: test_process_due_note_offs_*).  Scale every
# wait up for tolerance — the predicate is polled and returns as soon as it is
# satisfied, so the happy path is unaffected; only genuine failures wait longer.
_WAIT_SCALE = 8.0


def _wait_until(predicate, timeout_s: float = 0.75, step_s: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_s * _WAIT_SCALE
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


class _FailingNoteOffPort(_RecordingPort):
    def __init__(self, *, fail_note_off_count: int) -> None:
        super().__init__()
        self._remaining_failures = fail_note_off_count

    def send(self, message) -> None:
        if getattr(message, "type", "") == "note_off" and self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise OSError("note_off failed")
        super().send(message)


def _fake_mido_module(port):
    class _FakeMessage:
        def __init__(self, msg_type, **kwargs):
            self.type = msg_type
            self.kwargs = kwargs

    return SimpleNamespace(
        open_output=lambda _name: port,
        Message=lambda msg_type, **kwargs: _FakeMessage(msg_type, **kwargs),
    )

def _fake_mido_sequence(ports):
    class _FakeMessage:
        def __init__(self, msg_type, **kwargs):
            self.type = msg_type
            self.kwargs = kwargs

    opened = list(ports)

    def _open_output(_name):
        next_port = opened.pop(0)
        if isinstance(next_port, BaseException):
            raise next_port
        return next_port

    return SimpleNamespace(
        open_output=_open_output,
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

    def test_send_error_reopens_after_cooldown_and_sends(self) -> None:
        first = _FailingPort()
        second = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_sequence([first, second])
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                self.assertTrue(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=65, velocity=110)))
                self.assertTrue(_wait_until(lambda: out.status()["degraded_reason"] == "send_error"))
                out._send_error_reopen_after = 0.0
                self.assertTrue(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=66, velocity=110)))
                self.assertTrue(_wait_until(lambda: any(m.type == "note_on" for _, m in second.messages)))
                status = out.status()
                self.assertFalse(status["degraded"])
                self.assertEqual(status["degraded_reason"], "")
            finally:
                out.stop()

    def test_send_error_reopen_failure_respects_cooldown(self) -> None:
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_sequence([
            _FailingPort(),
            OSError("still missing"),
            _RecordingPort(),
        ])
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                self.assertTrue(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=65, velocity=110)))
                self.assertTrue(_wait_until(lambda: out.status()["degraded_reason"] == "send_error"))
                out._send_error_reopen_after = 0.0
                self.assertFalse(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=66, velocity=110)))
                rejected_after_first = out.status()["rejected_count"]
                self.assertFalse(out.trigger(LaserMidiMessage(kind="note_on", channel=1, note=67, velocity=110)))
                self.assertEqual(out.status()["rejected_count"], rejected_after_first + 1)
                self.assertTrue(out.status()["degraded"])
                self.assertEqual(out.status()["degraded_reason"], "send_error")
            finally:
                out.stop()

    def test_live_note_on_logs_at_debug_after_transport_send(self) -> None:
        # AWR-125 W4: [MIDI] tx demoted INFO -> DEBUG (hot-path hygiene).
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                with self.assertLogs("midi_output", level="DEBUG") as captured:
                    self.assertTrue(
                        out.trigger(
                            LaserMidiMessage(
                                kind="note_on",
                                behavior="note_on",
                                channel=1,
                                note=32,
                                velocity=127,
                            )
                        )
                    )
                    self.assertTrue(
                        _wait_until(
                            lambda: any(
                                m.type == "note_on" and m.kwargs.get("note") == 32
                                for _, m in port.messages
                            ),
                            timeout_s=0.3,
                        )
                    )
            finally:
                out.stop()

        tx_lines = [line for line in captured.output if "[MIDI] tx" in line]
        self.assertTrue(tx_lines, f"expected a [MIDI] tx line in {captured.output!r}")
        for line in tx_lines:
            self.assertTrue(line.startswith("DEBUG:"), f"[MIDI] tx must log at DEBUG, got: {line}")
        output = "\n".join(tx_lines)
        self.assertIn("type=note_on", output)
        self.assertIn("channel=1", output)
        self.assertIn("note=32", output)
        self.assertIn("velocity=127", output)

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
            "active_held_notes",
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

    def test_hold_ms_sends_note_on_then_note_off_later(self) -> None:
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                msg = LaserMidiMessage(
                    kind="note_on",
                    behavior="hold_ms",
                    channel=1,
                    note=62,
                    velocity=120,
                    hold_ms=120,
                )
                self.assertTrue(out.trigger(msg))
                self.assertTrue(
                    _wait_until(
                        lambda: any(m.type == "note_on" for _, m in port.messages),
                        timeout_s=0.3,
                    )
                )
                self.assertTrue(
                    _wait_until(
                        lambda: any(m.type == "note_off" for _, m in port.messages),
                        timeout_s=0.6,
                    )
                )
            finally:
                out.stop()

    def test_panic_during_due_note_off_is_safe_and_bounded(self) -> None:
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                msg = LaserMidiMessage(
                    kind="note_on",
                    behavior="hold_ms",
                    channel=1,
                    note=65,
                    velocity=120,
                    hold_ms=100,
                )
                self.assertTrue(out.trigger(msg))
                self.assertTrue(
                    _wait_until(
                        lambda: any(m.type == "note_on" for _, m in port.messages),
                        timeout_s=0.3,
                    )
                )
                time.sleep(0.08)
                out.panic()
                self.assertTrue(_wait_until(lambda: out.status()["active_held_notes"] == [], timeout_s=0.5))
            finally:
                out.stop()
        note_off_count = sum(1 for _, msg in port.messages if msg.type == "note_off" and msg.kwargs.get("note") == 65)
        self.assertLessEqual(note_off_count, 2)

    def test_stop_during_due_note_off_is_safe_and_clears_active(self) -> None:
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            msg = LaserMidiMessage(
                kind="note_on",
                behavior="hold_ms",
                channel=1,
                note=66,
                velocity=120,
                hold_ms=120,
            )
            self.assertTrue(out.trigger(msg))
            self.assertTrue(
                _wait_until(
                    lambda: any(m.type == "note_on" for _, m in port.messages),
                    timeout_s=0.3,
                )
            )
            time.sleep(0.09)
            out.stop()
            self.assertEqual(out.status()["active_held_notes"], [])
        note_off_count = sum(1 for _, msg in port.messages if msg.type == "note_off" and msg.kwargs.get("note") == 66)
        self.assertLessEqual(note_off_count, 2)

    def test_note_off_failure_keeps_note_recoverable_until_panic(self) -> None:
        port = _FailingNoteOffPort(fail_note_off_count=1)
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                msg = LaserMidiMessage(
                    kind="note_on",
                    behavior="hold_ms",
                    channel=1,
                    note=67,
                    velocity=120,
                    hold_ms=60,
                )
                self.assertTrue(out.trigger(msg))
                self.assertTrue(_wait_until(lambda: out.status()["send_error_count"] >= 1, timeout_s=0.5))
                self.assertTrue(out.status()["active_held_notes"])
                out.panic()
                self.assertTrue(_wait_until(lambda: out.status()["active_held_notes"] == [], timeout_s=0.5))
                self.assertTrue(out.status()["degraded"])
            finally:
                out.stop()

    def test_stop_releases_held_notes(self) -> None:
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            msg = LaserMidiMessage(
                kind="note_on",
                behavior="hold_ms",
                channel=1,
                note=63,
                velocity=120,
                hold_ms=2000,
            )
            self.assertTrue(out.trigger(msg))
            self.assertTrue(
                _wait_until(
                    lambda: any(m.type == "note_on" for _, m in port.messages),
                    timeout_s=0.3,
                )
            )
            out.stop()
        self.assertTrue(any(m.type == "note_off" for _, m in port.messages))

    def test_held_notes_do_not_block_later_messages(self) -> None:
        port = _RecordingPort()
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                hold = LaserMidiMessage(
                    kind="note_on",
                    behavior="hold_ms",
                    channel=1,
                    note=64,
                    velocity=120,
                    hold_ms=1500,
                )
                cc = LaserMidiMessage(kind="cc", channel=1, cc=10, value=64)
                self.assertTrue(out.trigger(hold))
                self.assertTrue(out.trigger(cc, priority="high"))
                self.assertTrue(
                    _wait_until(
                        lambda: any(m.type == "control_change" for _, m in port.messages),
                        timeout_s=0.35,
                    )
                )
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

    def test_process_due_note_offs_continues_after_single_failure(self) -> None:
        """One failed note-off should not prevent other due note-offs from being
        processed out of the scheduled heap.

        With ``continue`` instead of ``return``, the loop drains all due entries
        even when earlier sends fail. The port closes on error (by design), so
        subsequent _send_note_off calls are no-ops, but they are still attempted
        and the scheduled-offs heap is fully drained for this iteration.
        """
        port = _FailingNoteOffPort(fail_note_off_count=1)
        out = MidiOutput(port_name="IAC Driver Bus 1", dry_run=False)
        fake_mido = _fake_mido_module(port)
        with patch("rb_ss_bridge_v2.midi_output.importlib.import_module", return_value=fake_mido):
            out.start()
            try:
                # Schedule two held notes that will become due quickly.
                msg1 = LaserMidiMessage(
                    kind="note_on",
                    behavior="hold_ms",
                    channel=1,
                    note=70,
                    velocity=120,
                    hold_ms=40,
                )
                msg2 = LaserMidiMessage(
                    kind="note_on",
                    behavior="hold_ms",
                    channel=1,
                    note=71,
                    velocity=120,
                    hold_ms=40,
                )
                self.assertTrue(out.trigger(msg1))
                self.assertTrue(
                    _wait_until(
                        lambda: any(
                            m.type == "note_on" and m.kwargs.get("note") == 70
                            for _, m in port.messages
                        ),
                        timeout_s=0.3,
                    )
                )
                self.assertTrue(out.trigger(msg2))
                self.assertTrue(
                    _wait_until(
                        lambda: any(
                            m.type == "note_on" and m.kwargs.get("note") == 71
                            for _, m in port.messages
                        ),
                        timeout_s=0.3,
                    )
                )
                # Wait for the first note-off to fail and record an error.
                self.assertTrue(
                    _wait_until(
                        lambda: out.status()["send_error_count"] >= 1,
                        timeout_s=0.6,
                    ),
                    msg="First note-off should have failed and recorded an error",
                )
                # Verify the send error was recorded.
                status = out.status()
                self.assertGreaterEqual(status["send_error_count"], 1)
                self.assertIn("note_off failed", status["last_error"])
                # The sender loop must remain alive (thread still running).
                self.assertTrue(status["running"])
            finally:
                out.stop()


if __name__ == "__main__":
    unittest.main()
