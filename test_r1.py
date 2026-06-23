import sys
from pathlib import Path
sys.path.insert(0, str(Path('/Users/bbui')))
import unittest
from rb_ss_bridge_v2.state_manager import StateManager
from rb_ss_bridge_v2.rb_memory import PositionCache
from unittest.mock import Mock
import queue

class TestMock(unittest.TestCase):
    def test_sm(self):
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        print(sm._led_first_drop_anchor_beat)

if __name__ == "__main__":
    unittest.main()
