from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rb_ss_bridge_v2.live_bpm import LiveBPMStatus  # noqa: E402
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.session_recorder import SessionRecorder  # noqa: E402
from rb_ss_bridge_v2.session_replayer import CapturedSession  # noqa: E402


class ReplayFormatTests(unittest.TestCase):
    def test_recorder_round_trips_core_inputs(self) -> None:
        ev = BridgeEvent(
            kind=Ev.PLAY,
            deck=1,
            payload={"trace": "abc"},
            source="test",
            mono=12.5,
        )
        snap = PositionSnapshot(
            deck=1,
            elapsed_ms=1024,
            playing=True,
            track_length_ms=240000,
            ddj_mode=True,
            updated_at=12.6,
        )
        status = LiveBPMStatus(
            deck=1,
            bpm=128.25,
            pid=123,
            base=456,
            addr=789,
            type_name="float",
            source="direct",
            updated_at=12.7,
            valid=True,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.jsonl"
            recorder = SessionRecorder(path)
            recorder.record_event(ev)
            recorder.record_position(1, snap)
            recorder.record_live_bpm(1, 128.25, status)
            recorder.close()

            captured = CapturedSession.from_jsonl(path)

        self.assertEqual(captured.events, [ev])
        self.assertEqual(captured.positions, {1: [snap]})
        self.assertEqual(captured.live_bpm[1][0][1], 128.25)
        self.assertEqual(captured.live_bpm_status[1][0][1], status)


if __name__ == "__main__":
    unittest.main()
