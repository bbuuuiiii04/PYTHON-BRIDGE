import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import DeckState, OutputState  # noqa: E402
from rb_ss_bridge_v2.state_manager import (  # noqa: E402
    _phrase_anchor_tick,
    _send_direct_autoloop_rearm,
    _smart_drop_tick,
)


def _sm(drops=None, filepath="/music/drop.mp3"):
    out = Mock()
    deck = DeckState(number=1)
    deck.meta.filepath = filepath
    deck.meta.bpm = 130.0
    deck.meta.first_beat_ms = 0.0
    deck.meta.beatgrid_times_ms = [i * 500.0 for i in range(160)]
    deck.meta.anlz_drops = list(drops or [])
    sm = SimpleNamespace(
        _os=OutputState(lighting_mode="autoloop"),
        _deck={1: deck, 2: DeckState(number=2)},
        _out=out,
    )
    sm._autoloop_target_elapsed_for_beat = Mock(
        side_effect=lambda beat, _elapsed, _bpm, _meta: (beat * 500, "grid")
    )
    sm._send_autoloop_deck_load = Mock()
    return sm


class SmartDropTests(unittest.TestCase):
    def test_smart_drop_skipped_while_transition_arm_pending(self) -> None:
        sm = _sm([64])
        sm._os.autoloop_arm_pending = True
        _smart_drop_tick(sm, 1, 2, 130.0, 60, 30_000)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_cut_fires_4_beats_before_drop(self) -> None:
        sm = _sm([64])
        _smart_drop_tick(sm, 1, 2, 130.0, 60, 30_000)
        self.assertEqual(sm._out.send_deck_clear.call_count, 4)
        self.assertEqual(sm._out.send_loop_off.call_count, 4)
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 64)

    def test_cut_does_not_fire_before_window(self) -> None:
        sm = _sm([64])
        _smart_drop_tick(sm, 1, 2, 130.0, 55, 27_500)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_rearm_fires_on_drop_beat(self) -> None:
        sm = _sm([64])
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 64
        _smart_drop_tick(sm, 1, 2, 130.0, 64, 32_005)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_past_drops_scanned_but_ignored(self) -> None:
        sm = _sm([32, 64, 128])
        _smart_drop_tick(sm, 1, 2, 130.0, 124, 62_000)
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 128)

    def test_rearm_uses_autoloop_arm_bpm(self) -> None:
        sm = _sm([64])
        sm._os.autoloop_arm_bpm = 130.5
        _send_direct_autoloop_rearm(sm, 1, 2, 131.0, 32_005, "test", target_beat=64)
        arm_meta = sm._send_autoloop_deck_load.call_args.args[3]
        self.assertEqual(arm_meta.bpm, 130.5)

    def test_rearm_uses_target_elapsed_for_drop_beat(self) -> None:
        sm = _sm([64])
        _send_direct_autoloop_rearm(sm, 1, 2, 131.0, 32_125, "test", target_beat=64)
        arm_meta = sm._send_autoloop_deck_load.call_args.args[3]
        self.assertEqual(arm_meta.elapsed_ms, 32_000)


class PhraseAnchorTests(unittest.TestCase):
    def test_phrase_anchor_skipped_while_transition_arm_pending(self) -> None:
        sm = _sm()
        sm._os.autoloop_arm_pending = True
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_fires_at_64(self) -> None:
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)

    def test_phrase_anchor_snaps_to_nearby_future_drop(self) -> None:
        sm = _sm([60])
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 58, 29_000, 58.0)
        sm._send_autoloop_deck_load.assert_not_called()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 60, 30_000, 60.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 60)

    def test_phrase_anchor_does_not_snap_to_past_drop(self) -> None:
        sm = _sm([55])
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 62, 31_000, 62.0)
        sm._send_autoloop_deck_load.assert_not_called()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)

    def test_phrase_anchor_blocked_by_drop_cut(self) -> None:
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        sm._os.drop_cut_armed = True
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_init_sentinel(self) -> None:
        sm = _sm()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 75, 37_500, 75.0)
        sm._send_autoloop_deck_load.assert_not_called()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)


if __name__ == "__main__":
    unittest.main()
