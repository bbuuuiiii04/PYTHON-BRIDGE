import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


def _mark_track_loaded(sm: StateManager, deck: int = 1) -> None:
    d = sm._deck[deck]
    d.load_gen += 1
    d.playing = True
    d.meta.content_id = f"track-{d.load_gen}"
    d.meta.filepath = f"/music/track-{d.load_gen}.mp3"
    d.meta.beatgrid_times_ms = [float(i * 500) for i in range(256)]
    d.meta.anlz_buildups = [64]
    d.meta.anlz_drops = [128]
    d.meta.smart_drops = [128]
    d.meta.anlz_breakdowns = [32]


class PhraseSegmentCacheTests(unittest.TestCase):
    def test_phrase_segments_build_once_per_load_gen(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        _mark_track_loaded(sm)
        d = sm._deck[1]

        with patch.object(
            sm,
            "_build_phrase_segments",
            wraps=sm._build_phrase_segments,
        ) as phrase_spy, patch.object(
            sm,
            "_build_smart_drop_beats",
            wraps=sm._build_smart_drop_beats,
        ) as smart_drop_spy, patch.object(
            sm,
            "_build_breakdown_segments",
            wraps=sm._build_breakdown_segments,
        ) as breakdown_spy:
            for beat in (1.0, 2.0, 3.0, 4.0, 5.0):
                sm._update_smart_phrasing_state(1, d, beat, 128.0)

            self.assertEqual(phrase_spy.call_count, 1)
            self.assertEqual(smart_drop_spy.call_count, 1)
            self.assertEqual(breakdown_spy.call_count, 1)

            _mark_track_loaded(sm)
            d = sm._deck[1]
            sm._update_smart_phrasing_state(1, d, 6.0, 128.0)

            self.assertEqual(phrase_spy.call_count, 2)
            self.assertEqual(smart_drop_spy.call_count, 2)
            self.assertEqual(breakdown_spy.call_count, 2)


if __name__ == "__main__":
    unittest.main()
