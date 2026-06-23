"""T7d B1 — StateManager 200 Hz autoloop phase-trace wiring.

Drives the real ``StateManager._push_tick`` playing path (harness mirrors
tests/test_led_state_manager.py::_prepare_playing_push_tick) and proves:

  * a session recording attaches the tracer and emits dense schema-2
    ``autoloop_phase`` rows on the playing path,
  * stopping the recording writes a clean integrity footer and drains,
  * no rows are emitted when recording is off,
  * a paused (non-playing) tick emits no autoloop_phase row,
  * the hot-path emitter does not open files/devices (the writer thread does).

No real MIDI/serial/Enttec/DMX/network. Output is a Mock; LED/energy side
effects are stubbed so only the phase-trace wiring is under test.
"""
from __future__ import annotations

import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402
from rb_ss_bridge_v2.session_replayer import CapturedSession  # noqa: E402


def _make_sm() -> StateManager:
    return StateManager(__import__("queue").Queue(maxsize=64), PositionCache(), Mock())


def _isolate(sm: StateManager) -> None:
    # Stub everything that is not the phase-trace wiring under test.
    sm._check_pending_arm = lambda: None
    sm._update_lighting = lambda *a, **k: None
    sm._update_smart_phrasing_state = lambda *a, **k: SmartPhrasingState()
    sm._dispatch_led_automation = lambda **k: None
    sm._dispatch_led_idle_ambient = lambda **k: None
    sm._maybe_log_energy_suggest_would_fire = lambda *a, **k: None
    sm._laser_director = None


def _set_playing(sm: StateManager, *, playing: bool = True) -> None:
    import time

    snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=playing,
                            updated_at=time.monotonic())
    sm._cache.get = lambda deck: snap if deck == 1 else None
    sm._deck[1].playing = playing
    sm._deck[1].scripted_id = 0
    sm._deck[1].load_gen = 11
    sm._deck[1].meta.filepath = "/tracks/current.wav"
    sm._deck[1].meta.bpm = 0.0
    sm._deck[2].playing = False
    sm._os.active_deck = 1
    sm._os.was_playing = True
    sm._os.lighting_mode = "autoloop"
    sm._os.last_armed_filepath = "/tracks/current.wav"
    sm._os.last_beat_elapsed_ms = 1000


def _rows(path: Path):
    lines = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    header = next(r for r in lines if r.get("kind") == "header")
    phase = [r for r in lines if r.get("kind") == "autoloop_phase"]
    footer = next((r for r in lines if r.get("kind") == "phase_trace_footer"), None)
    return header, phase, footer


class WiringTests(unittest.TestCase):
    def test_recording_emits_dense_rows_and_clean_footer(self):
        sm = _make_sm()
        _isolate(sm)
        _set_playing(sm, playing=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cap.jsonl"
            self.assertTrue(sm.start_session_recording(str(path)))
            self.assertIsNotNone(sm._phase_tracer)
            N = 8
            for _ in range(N):
                sm._push_tick()
            self.assertTrue(sm.stop_session_recording())
            self.assertIsNone(sm._phase_tracer)
            header, phase, footer = _rows(path)

        self.assertEqual(header["schema"], 2)
        self.assertEqual(len(phase), N)  # one dense row per playing tick
        for row in phase:
            self.assertEqual(row["active_deck"], 1)
            self.assertTrue(row["playing"])
            self.assertEqual(row["load_gen"], 11)
            self.assertEqual(row["lighting_mode"], "autoloop")
            for key in ("epoch_ns", "mono_ns", "abs_beat_pos",
                        "autoloop_arm_sync_beat", "midi_refire_origin_beat",
                        "phrase_anchor_last_beat", "last_autoloop_status_phrase_beat",
                        "autoloop_tick_just_fired"):
                self.assertIn(key, row)
        self.assertIsNotNone(footer)
        self.assertTrue(footer["close_ok"])
        self.assertEqual(footer["dropped"], 0)
        self.assertEqual(footer["undrained"], 0)

    def test_no_rows_when_recording_off(self):
        sm = _make_sm()
        _isolate(sm)
        _set_playing(sm, playing=True)
        self.assertIsNone(sm._phase_tracer)
        for _ in range(5):
            sm._push_tick()  # must not create a tracer or raise
        self.assertIsNone(sm._phase_tracer)

    def test_paused_tick_emits_no_phase_row(self):
        sm = _make_sm()
        _isolate(sm)
        _set_playing(sm, playing=False)  # transport paused
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cap.jsonl"
            sm.start_session_recording(str(path))
            for _ in range(5):
                sm._push_tick()
            sm.stop_session_recording()
            _, phase, footer = _rows(path)
        self.assertEqual(phase, [])      # non-playing path emits nothing
        self.assertIsNotNone(footer)     # footer still written
        self.assertTrue(footer["close_ok"])

    def test_hot_path_emit_opens_no_files(self):
        sm = _make_sm()
        _isolate(sm)
        _set_playing(sm, playing=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cap.jsonl"
            sm.start_session_recording(str(path))
            real_open = builtins.open

            def boom(*a, **k):
                raise AssertionError("tick emit performed file I/O")

            builtins.open = boom
            try:
                sm._push_tick()  # only a bounded put_nowait may happen on the tick
            finally:
                builtins.open = real_open
            sm.stop_session_recording()

    def test_round_trips_through_replayer(self):
        sm = _make_sm()
        _isolate(sm)
        _set_playing(sm, playing=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cap.jsonl"
            sm.start_session_recording(str(path))
            for _ in range(4):
                sm._push_tick()
            sm.stop_session_recording()
            captured = CapturedSession.from_jsonl(path)
        self.assertEqual(len(captured.autoloop_phase), 4)


if __name__ == "__main__":
    unittest.main()
