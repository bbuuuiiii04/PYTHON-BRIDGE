import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


class StateManagerSnapshotTests(unittest.TestCase):
    def test_snapshot_returns_copy_of_published_state(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._deck[1].playing = True
        sm._deck[1].meta.filepath = "/music/a.mp3"
        sm._deck[1].meta.bpm = 128.0
        sm._deck[1].scripted_id = 12
        sm._os.active_deck = 1
        sm._os.lighting_mode = "scripted"
        sm._publish_snapshot()

        first = sm.snapshot()
        first["deck"]["1"]["filepath"] = "mutated"
        second = sm.snapshot()

        self.assertEqual(second["active_deck"], 1)
        self.assertEqual(second["lighting_mode"], "scripted")
        self.assertEqual(second["deck"]["1"]["filepath"], "/music/a.mp3")
        self.assertEqual(second["deck"]["1"]["scripted_id"], 12)


if __name__ == "__main__":
    unittest.main()
