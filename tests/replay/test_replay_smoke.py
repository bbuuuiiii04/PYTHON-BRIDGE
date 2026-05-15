from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.session_replayer import CapturedSession, ReplayHarness  # noqa: E402


class ReplaySmokeTests(unittest.TestCase):
    def test_replay_harness_steps_state_manager_tick(self) -> None:
        session = CapturedSession(
            events=[BridgeEvent(kind=Ev.PLAY, deck=1, source="test", mono=1.0)],
            positions={
                1: [
                    PositionSnapshot(
                        deck=1,
                        elapsed_ms=1000,
                        playing=True,
                        track_length_ms=180000,
                        updated_at=1.0,
                    )
                ]
            },
            live_bpm={1: [(1.0, 128.0)]},
        )
        harness = ReplayHarness(session)
        sm = harness.make_state_manager()

        for mono_t, inputs in harness.tick_iter():
            for ev in inputs.events:
                harness.event_queue.put_nowait(ev)
            harness.position_cache.now = mono_t
            harness.live_bpm.now = mono_t
            with patch("rb_ss_bridge_v2.state_manager.time.monotonic", return_value=mono_t):
                sm._drain_events()
                sm._push_tick()
                sm._publish_snapshot()

        snapshot = sm.snapshot()
        self.assertTrue(snapshot)
        self.assertEqual(snapshot["deck"]["1"]["elapsed_ms"], 1000)


if __name__ == "__main__":
    unittest.main()
