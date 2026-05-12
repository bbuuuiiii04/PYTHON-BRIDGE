import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.sound_switch_engine import SoundSwitchEngine  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


class DeckRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sse = SoundSwitchEngine(Mock())

    def test_deck_route_deck1(self) -> None:
        self.assertEqual(self.sse.deck_route(1), (1, 2, 3, 4))

    def test_deck_route_deck2(self) -> None:
        self.assertEqual(self.sse.deck_route(2), (2, 1, 3, 4))

    def test_deck_route_always_four_decks(self) -> None:
        self.assertEqual(len(self.sse.deck_route(1)), 4)
        self.assertEqual(len(self.sse.deck_route(2)), 4)


class StateManagerWiringTests(unittest.TestCase):
    def _sm(self) -> StateManager:
        return StateManager(queue.Queue(), PositionCache(), Mock())

    def test_state_manager_init_creates_sse(self) -> None:
        sm = self._sm()
        self.assertIsInstance(sm._sse, SoundSwitchEngine)

    def test_state_manager_sse_shares_output(self) -> None:
        sm = self._sm()
        self.assertIs(sm._sse._out, sm._out)

    def test_push_tick_does_not_invoke_sse(self) -> None:
        sm = self._sm()
        mock_sse = Mock(spec=SoundSwitchEngine)
        sm._sse = mock_sse
        sm._os.was_playing = False
        sm._deck[1].playing = False
        sm._push_tick()
        self.assertEqual(mock_sse.method_calls, [])


if __name__ == "__main__":
    unittest.main()
