import io
import logging
import queue
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import DeckState, PositionSnapshot, SmartDropEnergyShadow  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


def _energy_logs(fn) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("state_manager")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        fn()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    return stream.getvalue()


def _shadow(
    *,
    suggested_elapsed_ms: int = 10_000,
    confidence: float = 3.35,
) -> SmartDropEnergyShadow:
    return SmartDropEnergyShadow(
        64,
        72,
        8_000,
        suggested_elapsed_ms,
        -7.69,
        -4.34,
        confidence,
    )


def _manager(lighting_mode: str = "autoloop") -> StateManager:
    sm = StateManager(queue.Queue(), PositionCache(), Mock())
    d = sm._deck[1]
    d.playing = True
    d.meta.filepath = "/music/energy.mp3"
    d.meta.bpm = 120.0
    d.meta.first_beat_ms = 0.0
    if lighting_mode == "scripted":
        d.scripted_id = 123
    sm._os.active_deck = 1
    sm._os.lighting_mode = lighting_mode
    sm._os.lighting_desired = lighting_mode
    sm._os.was_playing = True
    sm._os.last_sent_bpm = 120.0
    return sm


class EnergySuggestWouldFireLogTests(unittest.TestCase):
    def test_energy_suggest_would_fire_on_crossing(self) -> None:
        sm = _manager()
        d = DeckState(number=1)
        d.meta.smart_drop_energy_shadow = [_shadow()]

        logs = _energy_logs(
            lambda: sm._maybe_log_energy_suggest_would_fire(1, 9_990, 10_005, d)
        )

        self.assertIn("[SM] energy-suggest ★ deck=1 would-fire-now@0:10.000", logs)
        self.assertIn("conf=3.35", logs)

    def test_energy_suggest_would_fire_no_double(self) -> None:
        sm = _manager()
        d = DeckState(number=1)
        d.meta.smart_drop_energy_shadow = [_shadow()]

        logs = _energy_logs(
            lambda: (
                sm._maybe_log_energy_suggest_would_fire(1, 9_990, 10_005, d),
                sm._maybe_log_energy_suggest_would_fire(1, 10_005, 10_020, d),
            )
        )

        self.assertEqual(logs.count("would-fire-now@0:10.000"), 1)

    def test_energy_suggest_would_fire_silent_confidence_zero(self) -> None:
        sm = _manager()
        d = DeckState(number=1)
        d.meta.smart_drop_energy_shadow = [_shadow(confidence=0.0)]

        logs = _energy_logs(
            lambda: sm._maybe_log_energy_suggest_would_fire(1, 9_990, 10_005, d)
        )

        self.assertNotIn("energy-suggest", logs)

    def test_energy_suggest_would_fire_gated_to_autoloop(self) -> None:
        sm = _manager(lighting_mode="scripted")
        sm._deck[1].elapsed_ms = 9_990
        sm._deck[1].meta.smart_drop_energy_shadow = [_shadow()]
        sm._cache.update(
            PositionSnapshot(
                1,
                elapsed_ms=10_005,
                playing=True,
                updated_at=time.monotonic(),
            )
        )

        with patch.object(sm, "_maybe_log_energy_suggest_would_fire") as hook:
            sm._push_tick()

        hook.assert_not_called()

    def test_energy_suggest_would_fire_reset_on_load(self) -> None:
        sm = _manager()
        d = DeckState(number=1)
        d.meta.smart_drop_energy_shadow = [_shadow()]

        first_logs = _energy_logs(
            lambda: sm._maybe_log_energy_suggest_would_fire(1, 9_990, 10_005, d)
        )
        d.load_gen += 1
        d.elapsed_ms = 0
        d.meta.clear()
        d.meta.smart_drop_energy_shadow = [_shadow(suggested_elapsed_ms=10_000)]
        second_logs = _energy_logs(
            lambda: sm._maybe_log_energy_suggest_would_fire(1, 9_990, 10_005, d)
        )

        self.assertEqual(first_logs.count("would-fire-now@0:10.000"), 1)
        self.assertEqual(second_logs.count("would-fire-now@0:10.000"), 1)


if __name__ == "__main__":
    unittest.main()
