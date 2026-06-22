"""Tests for the B1 schema-2 autoloop_phase trace seam.

Covers the evidence-only phase trace used by the capture pass:
  * pure row builder performs no I/O and carries the required primitive fields,
  * the bounded tracer enqueues without blocking and counts dropped samples,
  * the hot-path emit() opens no files/devices even with open() patched to raise,
  * schema-2 round-trips phase rows through the recorder/replayer,
  * schema-1 sessions remain byte-compatible.

The actual 200 Hz StateManager call-site is intentionally NOT wired here: that
is a live-critical hot-path edit gated on plan-first review (see the capture
plan §B1 integration note). These tests prove the tooling in isolation.
"""
from __future__ import annotations

import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.session_phase_trace import (  # noqa: E402
    AutoloopPhaseTracer,
    PhaseTracerCloseResult,
    build_autoloop_phase_row,
)
from rb_ss_bridge_v2.session_recorder import SessionRecorder  # noqa: E402
from rb_ss_bridge_v2.session_replayer import CapturedSession  # noqa: E402


REQUIRED_FIELDS = (
    "epoch_ns",
    "mono_ns",
    "active_deck",
    "load_gen",
    "playing",
    "position_stale",
    "elapsed_ms",
    "bpm",
    "abs_beat_pos",
    "beatgrid_source",
    "lighting_mode",
    "autoloop_arm_pending",
    "autoloop_arm_sync_beat",
    "midi_refire_origin_beat",
    "phrase_anchor_last_beat",
    "drop_cut_armed",
    "role",
    "reason",
    "autoloop_tick_just_fired",
    "accepted_scene",
    "accepted_note",
    "accepted_trigger_gen",
)


def _row(**over):
    base = {name: 0 for name in REQUIRED_FIELDS}
    base.update(mono_ns=1_000, epoch_ns=2_000)
    base.update(over)
    return build_autoloop_phase_row(**base)


class BuildRowTests(unittest.TestCase):
    def test_row_is_tagged_and_carries_required_fields(self):
        row = _row(active_deck=1, bpm=128.0, abs_beat_pos=12.5, role="autoloop")
        self.assertEqual(row["kind"], "autoloop_phase")
        for name in REQUIRED_FIELDS:
            self.assertIn(name, row)
        self.assertEqual(row["active_deck"], 1)
        self.assertEqual(row["abs_beat_pos"], 12.5)
        # carries a monotonic replay timestamp derived from mono_ns
        self.assertAlmostEqual(row["t"], 1_000 / 1e9)

    def test_row_is_json_serializable(self):
        json.dumps(_row())  # must not raise


class TracerOrderingTests(unittest.TestCase):
    def test_rows_written_in_emit_order(self):
        written = []
        tracer = AutoloopPhaseTracer(written.append, maxsize=64)
        for i in range(5):
            tracer.emit(_row(accepted_trigger_gen=i))
        tracer.close()
        self.assertEqual([r["accepted_trigger_gen"] for r in written], [0, 1, 2, 3, 4])
        self.assertEqual(tracer.dropped, 0)


class TracerDropAccountingTests(unittest.TestCase):
    def test_overflow_is_dropped_and_counted_without_blocking(self):
        # Writer thread paused (autostart=False) so the bounded queue fills.
        tracer = AutoloopPhaseTracer(lambda r: None, maxsize=4, autostart=False)
        for i in range(10):
            tracer.emit(_row(accepted_trigger_gen=i))  # must never block or raise
        self.assertEqual(tracer.queued, 4)
        self.assertEqual(tracer.dropped, 6)
        tracer.close()


class TracerHotPathTests(unittest.TestCase):
    def test_emit_opens_no_files_even_when_open_raises(self):
        tracer = AutoloopPhaseTracer(lambda r: None, maxsize=8, autostart=False)
        real_open = builtins.open

        def boom(*a, **k):  # any file I/O from the hot path must blow up the test
            raise AssertionError("emit() performed file I/O on the tick path")

        builtins.open = boom
        try:
            tracer.emit(_row())  # only a bounded put_nowait may happen here
        finally:
            builtins.open = real_open
        tracer.close()


class TracerCloseResultTests(unittest.TestCase):
    def test_clean_close_drains_all_and_reports_ok(self):
        written = []
        tracer = AutoloopPhaseTracer(written.append, maxsize=64)
        for i in range(20):
            tracer.emit(_row(accepted_trigger_gen=i))
        result = tracer.close()
        self.assertIsInstance(result, PhaseTracerCloseResult)
        self.assertTrue(result.ok)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.dropped, 0)
        self.assertEqual(result.undrained, 0)
        self.assertIsNone(result.writer_error)
        # deterministic drain: every emitted row was written before close returned
        self.assertEqual(len(written), 20)

    def test_close_is_idempotent(self):
        tracer = AutoloopPhaseTracer(lambda r: None, maxsize=8)
        first = tracer.close()
        second = tracer.close()
        self.assertIs(first, second)

    def test_writer_exception_does_not_hang_and_marks_not_ok(self):
        def boom(_row):
            raise RuntimeError("disk full")

        tracer = AutoloopPhaseTracer(boom, maxsize=64)
        for i in range(5):
            tracer.emit(_row(accepted_trigger_gen=i))
        result = tracer.close(timeout=5.0)  # must not hang
        self.assertFalse(result.ok)
        self.assertFalse(result.timed_out)
        self.assertIsNotNone(result.writer_error)
        self.assertIn("disk full", result.writer_error)
        self.assertGreaterEqual(result.undrained, 1)

    def test_dropped_rows_make_close_not_ok(self):
        # Writer paused so the bounded queue overflows on the hot path.
        tracer = AutoloopPhaseTracer(lambda r: None, maxsize=2, autostart=False)
        for i in range(6):
            tracer.emit(_row(accepted_trigger_gen=i))
        self.assertEqual(tracer.dropped, 4)
        tracer.start()
        result = tracer.close()
        self.assertFalse(result.ok)
        self.assertEqual(result.dropped, 4)


class Schema2RoundTripTests(unittest.TestCase):
    def test_phase_rows_round_trip_and_core_inputs_preserved(self):
        ev = BridgeEvent(kind=Ev.PLAY, deck=1, payload={}, source="t", mono=5.0)
        snap = PositionSnapshot(
            deck=1, elapsed_ms=10, playing=True, track_length_ms=1000, updated_at=5.1
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cap.jsonl"
            recorder = SessionRecorder(path, schema=2)
            recorder.record_event(ev)
            recorder.record_position(1, snap)
            tracer = AutoloopPhaseTracer(recorder.write_phase_row, maxsize=64)
            tracer.emit(_row(abs_beat_pos=1.0, accepted_trigger_gen=1))
            tracer.emit(_row(abs_beat_pos=2.0, accepted_trigger_gen=2))
            tracer.close()
            recorder.close()

            captured = CapturedSession.from_jsonl(path)

        self.assertEqual(captured.events, [ev])
        self.assertEqual(captured.positions, {1: [snap]})
        self.assertEqual(len(captured.autoloop_phase), 2)
        self.assertEqual(
            [r["accepted_trigger_gen"] for r in captured.autoloop_phase], [1, 2]
        )


class Schema1CompatibilityTests(unittest.TestCase):
    def test_schema1_session_has_no_phase_rows(self):
        ev = BridgeEvent(kind=Ev.PLAY, deck=1, payload={}, source="t", mono=1.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.jsonl"
            recorder = SessionRecorder(path)  # default schema 1
            recorder.record_event(ev)
            recorder.close()
            header = json.loads(path.read_text().splitlines()[0])
            captured = CapturedSession.from_jsonl(path)
        self.assertEqual(header["schema"], 1)
        self.assertEqual(captured.events, [ev])
        self.assertEqual(captured.autoloop_phase, [])


if __name__ == "__main__":
    unittest.main()
