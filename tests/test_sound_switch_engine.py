import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.sound_switch_engine import SoundSwitchEngine  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager, _send_direct_autoloop_rearm  # noqa: E402


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

    def test_send_loop_off_delegates_to_output(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_loop_off(3)
        out.send_loop_off.assert_called_once_with(3)

    def test_send_deck_clear_delegates_to_output(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_deck_clear(4)
        out.send_deck_clear.assert_called_once_with(4)

    def test_send_autoloop_deck_load_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_autoloop_deck_load(1, 2, 1, arm_meta)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(deck, arm_meta, 1, play="on") for deck in (1, 2, 3, 4)],
        )

    def test_send_autoloop_clear_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_autoloop_clear(2)
        self.assertEqual(
            out.send_deck_clear.call_args_list,
            [call(deck) for deck in (2, 1, 3, 4)],
        )
        self.assertEqual(
            out.send_loop_off.call_args_list,
            [call(deck) for deck in (2, 1, 3, 4)],
        )

    def test_send_autoloop_bpm_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_autoloop_bpm(1, 130.0)
        self.assertEqual(
            out.send_bpm.call_args_list,
            [call(deck, 130.0) for deck in (1, 2, 3, 4)],
        )

    def test_send_scripted_arm_phase0_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_scripted_arm_phase0(2)
        self.assertEqual(
            out._sub.call_args_list,
            [call(f"deck {dk} get_filepath", "", verbose=True) for dk in (2, 1, 3, 4)],
        )
        self.assertEqual(out.send_loop_off.call_args_list, [call(dk) for dk in (2, 1, 3, 4)])
        self.assertEqual(
            out.send_deck_play.call_args_list,
            [call(dk, "off") for dk in (2, 1, 3, 4)],
        )

    def test_send_scripted_arm_phase0_deck1_route_order(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_scripted_arm_phase0(1)
        self.assertEqual(out.send_loop_off.call_args_list, [call(dk) for dk in (1, 2, 3, 4)])

    def test_send_scripted_arm_phase1_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(2, arm_meta, 2)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 2, play="on") for dk in (2, 1, 3, 4)],
        )

    def test_send_scripted_arm_phase1_deck1_route_order(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(1, arm_meta, 1)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 1, play="on") for dk in (1, 2, 3, 4)],
        )

    def test_send_scripted_arm_phase1_active_differs_from_armed_deck(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(1, arm_meta, 2)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 2, play="on") for dk in (1, 2, 3, 4)],
        )


class StateManagerWiringTests(unittest.TestCase):
    def _sm(self) -> StateManager:
        return StateManager(queue.Queue(), PositionCache(), Mock())

    def test_state_manager_init_creates_sse(self) -> None:
        sm = self._sm()
        self.assertIsInstance(sm._sse, SoundSwitchEngine)

    def test_state_manager_sse_shares_output(self) -> None:
        sm = self._sm()
        self.assertIs(sm._sse._out, sm._out)


class StateManagerRouteFanoutTests(unittest.TestCase):
    def _sm(self) -> StateManager:
        return StateManager(queue.Queue(), PositionCache(), Mock())

    def _configure_active_deck(self, sm: StateManager, active: int, bpm: float) -> None:
        d = sm._deck[active]
        d.meta.filepath = f"/music/deck-{active}.mp3"
        d.meta.bpm = bpm
        d.meta.first_beat_ms = 0.0
        d.meta.beatgrid_times_ms = [i * 500.0 for i in range(256)]
        d.meta.beatgrid_bpms = [bpm for _ in range(256)]
        d.meta.total_ms = 180_000.0

    def _assert_fanout(self, sm: StateManager, expected_decks: list[int], bpm: float) -> None:
        self.assertEqual(sm._out.send_deck_clear.call_args_list, [call(deck) for deck in expected_decks])
        self.assertEqual(sm._out.send_loop_off.call_args_list, [call(deck) for deck in expected_decks])
        self.assertEqual(sm._out.send_bpm.call_args_list, [call(deck, bpm) for deck in expected_decks])

    def test_direct_autoloop_rearm_fanout_uses_deck1_route_order(self) -> None:
        sm = self._sm()
        sm._send_autoloop_deck_load = Mock()
        self._configure_active_deck(sm, active=1, bpm=130.0)
        ok = _send_direct_autoloop_rearm(
            sm, active=1, mirror=2, bpm=130.0, elapsed_ms=32_005, reason="test", target_beat=64
        )
        self.assertTrue(ok)
        self._assert_fanout(sm, [1, 2, 3, 4], 130.0)

    def test_direct_autoloop_rearm_fanout_uses_deck2_route_order(self) -> None:
        sm = self._sm()
        sm._send_autoloop_deck_load = Mock()
        self._configure_active_deck(sm, active=2, bpm=131.0)
        ok = _send_direct_autoloop_rearm(
            sm, active=2, mirror=1, bpm=131.0, elapsed_ms=32_005, reason="test", target_beat=64
        )
        self.assertTrue(ok)
        self._assert_fanout(sm, [2, 1, 3, 4], 131.0)


if __name__ == "__main__":
    unittest.main()
