"""Pure coverage for the Test-the-Lights replay source (replay_event_source.py).

Timeline ordering, live-clock re-stamping, real-time pacing, and the fail-closed
preflight -- no bridge, no real threads, no wall-clock waits. End-to-end "lights
respond" is the operator's Task-7 parity run.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import replay_event_source as res  # noqa: E402
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.session_replayer import CapturedSession  # noqa: E402


def _event(mono: float) -> BridgeEvent:
    return BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={}, source="test", mono=mono)


def _snap(updated_at: float) -> PositionSnapshot:
    return PositionSnapshot(
        deck=1, elapsed_ms=0, playing=True, track_length_ms=1000,
        ddj_mode=False, updated_at=updated_at,
    )


def _session() -> CapturedSession:
    return CapturedSession(
        events=[_event(100.0), _event(100.5)],
        positions={1: [_snap(100.2)]},
        live_bpm={1: [(100.1, 128.0)]},
    )


class _Queue:
    def __init__(self) -> None:
        self.items = []

    def put_nowait(self, ev) -> None:
        self.items.append(ev)


class _PosCache:
    def __init__(self) -> None:
        self.updates = []

    def update(self, snap) -> None:
        self.updates.append(snap)


class _LiveBpm:
    def __init__(self) -> None:
        self.hints = []

    def update_hint(self, deck, bpm) -> None:
        self.hints.append((deck, bpm))


class TimelineTests(unittest.TestCase):
    def test_timeline_is_time_sorted_across_kinds(self) -> None:
        rows = res._timeline(_session())
        self.assertEqual([r[0] for r in rows], [100.0, 100.1, 100.2, 100.5])
        self.assertEqual([r[1] for r in rows], ["event", "live_bpm", "position", "event"])

    def test_empty_session_replays_nothing(self) -> None:
        empty = CapturedSession(events=[], positions={}, live_bpm={})
        self.assertEqual(res.run_replay(empty, _Queue(), _PosCache(), _LiveBpm()), 0)


class RunReplayTests(unittest.TestCase):
    def test_restamps_to_live_clock_and_paces(self) -> None:
        q, pc, lb = _Queue(), _PosCache(), _LiveBpm()
        sleeps: list[float] = []
        # Fixed clock at 1000.0 -> each row's delay is its offset from origin,
        # and re-stamped monos are 1000.0 + offset.
        injected = res.run_replay(
            _session(), q, pc, lb,
            clock=lambda: 1000.0,
            sleep=sleeps.append,
        )
        self.assertEqual(injected, 4)
        # events re-stamped to the live clock, not their recorded 100.x monos
        self.assertEqual([ev.mono for ev in q.items], [1000.0, 1000.5])
        self.assertNotIn(100.0, [ev.mono for ev in q.items])
        # position re-stamped too (staleness gate would drop the old updated_at)
        self.assertEqual(pc.updates[0].updated_at, 1000.2)
        self.assertEqual(pc.updates[0].deck, 1)
        # bpm hint passes through
        self.assertEqual(lb.hints, [(1, 128.0)])
        # paced by recorded spacing (origin row sleeps 0 and is skipped)
        self.assertEqual(len(sleeps), 3)
        for got, want in zip(sleeps, [0.1, 0.2, 0.5]):
            self.assertAlmostEqual(got, want, places=6)

    def test_stop_event_halts_injection(self) -> None:
        import threading

        stop = threading.Event()
        stop.set()
        injected = res.run_replay(
            _session(), _Queue(), _PosCache(), _LiveBpm(),
            stop=stop, clock=lambda: 0.0, sleep=lambda _s: None,
        )
        self.assertEqual(injected, 0)

    def test_none_bpm_is_skipped_not_crashed(self) -> None:
        lb = _LiveBpm()
        session = CapturedSession(events=[], positions={}, live_bpm={1: [(1.0, None)]})
        res.run_replay(session, _Queue(), _PosCache(), lb, clock=lambda: 0.0, sleep=lambda _s: None)
        self.assertEqual(lb.hints, [])


class PreflightTests(unittest.TestCase):
    def test_refuses_when_rekordbox_running(self) -> None:
        msg = res.replay_preflight("/whatever.jsonl", rekordbox_pid=4242)
        self.assertIsNotNone(msg)
        self.assertIn("Rekordbox", msg)

    def test_refuses_when_no_session_file(self) -> None:
        msg = res.replay_preflight("/no/such/session.jsonl", rekordbox_pid=None)
        self.assertIsNotNone(msg)
        self.assertIn("No test session", msg)

    def test_passes_when_clear_and_file_exists(self) -> None:
        self.assertIsNone(res.replay_preflight(__file__, rekordbox_pid=None))

    def test_rekordbox_takes_priority_over_missing_file(self) -> None:
        # live-safety first: refuse for Rekordbox even if the file is also missing
        msg = res.replay_preflight("/no/such.jsonl", rekordbox_pid=1)
        self.assertIn("Rekordbox", msg)


class MaybeStartFromEnvTests(unittest.TestCase):
    @staticmethod
    def _replay_thread_running() -> bool:
        import threading

        return any(t.name == "test-lights-replay" for t in threading.enumerate())

    def test_unset_env_starts_nothing(self) -> None:
        os.environ.pop(res.REPLAY_SESSION_ENV, None)
        self.assertIsNone(res.maybe_start_from_env(_Queue(), _PosCache(), _LiveBpm()))

    def test_rekordbox_present_starts_no_thread(self) -> None:
        # F1 live-safety: a stray RBSS_REPLAY_SESSION on a bridge with Rekordbox
        # running must NOT start the pump (two drivers racing). Even a valid,
        # existing session path is refused because Rekordbox is up.
        from unittest import mock

        with mock.patch.dict(os.environ, {res.REPLAY_SESSION_ENV: __file__}), \
             mock.patch.object(res, "_rekordbox_pid", return_value=4242):
            result = res.maybe_start_from_env(_Queue(), _PosCache(), _LiveBpm())
        self.assertIsNone(result)
        self.assertFalse(self._replay_thread_running())

    def test_missing_file_starts_no_thread(self) -> None:
        # Bad/missing path fails closed to None (no crash) via the preflight,
        # not by raising -- so a stray env var can't blow up a normal bridge start.
        from unittest import mock

        with mock.patch.dict(os.environ, {res.REPLAY_SESSION_ENV: "/no/such/session.jsonl"}), \
             mock.patch.object(res, "_rekordbox_pid", return_value=None):
            result = res.maybe_start_from_env(_Queue(), _PosCache(), _LiveBpm())
        self.assertIsNone(result)
        self.assertFalse(self._replay_thread_running())


if __name__ == "__main__":
    unittest.main()
