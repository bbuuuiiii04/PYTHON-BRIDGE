import io
import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import (  # noqa: E402
    DeckState,
    OutputState,
    SmartDropEnergyShadow,
    TrackMetadata,
)
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.smart_rearm import (  # noqa: E402
    SmartDropTickResult,
    SmartRearmContext,
    SmartRearmCoordinator,
)


def _sp_state(**overrides) -> SmartPhrasingState:
    defaults = dict(reason="test")
    defaults.update(overrides)
    return SmartPhrasingState(**defaults)


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
    anlz_beat: int = 64,
    suggested_beat: int = 72,
    anlz_elapsed_ms: int = 32_000,
    suggested_elapsed_ms: int = 36_000,
    confidence: float = 3.35,
) -> SmartDropEnergyShadow:
    return SmartDropEnergyShadow(
        anlz_beat,
        suggested_beat,
        anlz_elapsed_ms,
        suggested_elapsed_ms,
        -7.69,
        -4.34,
        confidence,
    )


class _Harness:
    def __init__(self) -> None:
        self.os = OutputState(lighting_mode="autoloop")
        self.deck = {
            1: DeckState(number=1, meta=TrackMetadata(filepath="/music/a.mp3", bpm=128.0)),
            2: DeckState(number=2, meta=TrackMetadata(filepath="/music/b.mp3", bpm=128.0)),
        }
        self.direct_calls: list[tuple[tuple, dict]] = []
        self.clear_calls: list[int] = []
        self.direct_return = True
        self.coordinator = SmartRearmCoordinator(
            output_state_ref=lambda: self.os,
            deck_ref=lambda d: self.deck[d],
            send_direct_autoloop_rearm=self._send_direct,
            send_smart_transition_clear=self._send_clear,
        )

    def ctx(
        self,
        *,
        mirror: int = 2,
        bpm: float = 128.0,
        this_beat: int = 60,
        elapsed_ms: int = 30_000,
        abs_beat_pos: float | None = None,
        blackout_mode: bool = True,
        smart_drop_enabled: bool = False,
        smart_breakdown_enabled: bool = False,
        phrase_anchor_enabled: bool = False,
        lighting_mode_is_autoloop: bool = True,
    ) -> SmartRearmContext:
        return SmartRearmContext(
            mirror=mirror,
            bpm=bpm,
            this_beat=this_beat,
            elapsed_ms=elapsed_ms,
            abs_beat_pos=float(this_beat) if abs_beat_pos is None else abs_beat_pos,
            blackout_mode=blackout_mode,
            smart_drop_enabled=smart_drop_enabled,
            smart_breakdown_enabled=smart_breakdown_enabled,
            phrase_anchor_enabled=phrase_anchor_enabled,
            lighting_mode_is_autoloop=lighting_mode_is_autoloop,
        )

    def tick(self, sp: SmartPhrasingState, ctx: SmartRearmContext):
        return self.coordinator.tick(1, sp, ctx)

    def _send_direct(self, *args, **kwargs) -> bool:
        self.direct_calls.append((args, kwargs))
        return self.direct_return

    def _send_clear(self, active: int) -> None:
        self.clear_calls.append(active)


class SmartRearmDropTests(unittest.TestCase):
    def test_drop_blackout_arm_sets_output_state_without_clear(self) -> None:
        h = _Harness()
        result = h.tick(
            _sp_state(transition_mask_should_arm=True, next_smart_drop_beat=64.0),
            h.ctx(smart_drop_enabled=True, this_beat=60, blackout_mode=True),
        )

        self.assertEqual(result.drop, SmartDropTickResult(False, True, 64))
        self.assertTrue(h.os.drop_cut_armed)
        self.assertEqual(h.os.drop_rearm_beat, 64)
        self.assertEqual(h.clear_calls, [])
        self.assertEqual(h.direct_calls, [])

    def test_drop_legacy_cut_sends_clear_before_arm(self) -> None:
        h = _Harness()
        result = h.tick(
            _sp_state(transition_mask_should_arm=True, next_smart_drop_beat=64.0),
            h.ctx(smart_drop_enabled=True, this_beat=60, blackout_mode=False),
        )

        self.assertEqual(result.drop, SmartDropTickResult(False, True, 64))
        self.assertEqual(h.clear_calls, [1])
        self.assertTrue(h.os.drop_cut_armed)
        self.assertEqual(h.os.drop_rearm_beat, 64)

    def test_drop_blackout_crossing_reports_target_without_clearing_arm(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 64

        result = h.tick(
            _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
            h.ctx(smart_drop_enabled=True, this_beat=64, blackout_mode=True),
        )

        self.assertEqual(result.drop, SmartDropTickResult(True, False, 64))
        self.assertTrue(h.os.drop_cut_armed)
        self.assertEqual(h.os.drop_rearm_beat, 64)
        self.assertEqual(h.direct_calls, [])

    def test_drop_legacy_rearm_clears_arm_and_rebases_phrase_anchor(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 64

        result = h.tick(
            _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
            h.ctx(smart_drop_enabled=True, this_beat=64, elapsed_ms=32_000, blackout_mode=False),
        )

        self.assertEqual(result.drop, SmartDropTickResult(True, False, 64))
        self.assertFalse(h.os.drop_cut_armed)
        self.assertEqual(h.os.drop_rearm_beat, 0)
        self.assertEqual(h.os.phrase_anchor_last_beat, 64)
        self.assertEqual(
            h.direct_calls,
            [((1, 2, 128.0, 32_000, "smart-drop"), {"target_beat": 64})],
        )

    def test_energy_suggest_fires_on_crossing_with_confidence(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 64
        h.deck[1].meta.smart_drop_energy_shadow = [_shadow()]

        logs = _energy_logs(
            lambda: h.tick(
                _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
                h.ctx(smart_drop_enabled=True, this_beat=64, blackout_mode=True),
            )
        )

        self.assertIn("[SM] energy-suggest ★ deck=1 fired@0:32.000", logs)
        self.assertIn("+4000ms had higher lift (-7.69→-4.34 conf=3.35)", logs)

    def test_energy_suggest_silent_when_confidence_zero(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 64
        h.deck[1].meta.smart_drop_energy_shadow = [_shadow(confidence=0.0)]

        logs = _energy_logs(
            lambda: h.tick(
                _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
                h.ctx(smart_drop_enabled=True, this_beat=64, blackout_mode=True),
            )
        )

        self.assertNotIn("energy-suggest", logs)

    def test_energy_suggest_silent_when_no_shadow(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 64

        logs = _energy_logs(
            lambda: h.tick(
                _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
                h.ctx(smart_drop_enabled=True, this_beat=64, blackout_mode=True),
            )
        )

        self.assertNotIn("energy-suggest", logs)

    def test_energy_suggest_silent_when_anlz_beat_mismatch(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 64
        h.deck[1].meta.smart_drop_energy_shadow = [_shadow(anlz_beat=96)]

        logs = _energy_logs(
            lambda: h.tick(
                _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
                h.ctx(smart_drop_enabled=True, this_beat=64, blackout_mode=True),
            )
        )

        self.assertNotIn("energy-suggest", logs)

    def test_energy_suggest_fires_in_blackout_and_rearm_paths(self) -> None:
        for blackout_mode in (True, False):
            with self.subTest(blackout_mode=blackout_mode):
                h = _Harness()
                h.os.drop_cut_armed = True
                h.os.drop_rearm_beat = 64
                h.deck[1].meta.smart_drop_energy_shadow = [_shadow()]

                logs = _energy_logs(
                    lambda: h.tick(
                        _sp_state(smart_drop_crossing=True, active_drop_beat=64.0),
                        h.ctx(
                            smart_drop_enabled=True,
                            this_beat=64,
                            blackout_mode=blackout_mode,
                        ),
                    )
                )

                self.assertIn("[SM] energy-suggest ★ deck=1 fired@0:32.000", logs)

    def test_drop_path_is_gated_by_pending_autoloop_arm(self) -> None:
        h = _Harness()
        h.os.autoloop_arm_pending = True

        result = h.tick(
            _sp_state(transition_mask_should_arm=True, next_smart_drop_beat=64.0),
            h.ctx(smart_drop_enabled=True),
        )

        self.assertEqual(result.drop, SmartDropTickResult.none())
        self.assertFalse(h.os.drop_cut_armed)
        self.assertEqual(h.clear_calls, [])


class SmartRearmBreakdownTests(unittest.TestCase):
    def test_breakdown_start_clears_and_sets_restore_state(self) -> None:
        h = _Harness()
        result = h.tick(
            _sp_state(breakdown_start_crossing=True, breakdown_restore_beat=64.0),
            h.ctx(smart_breakdown_enabled=True, this_beat=32, elapsed_ms=16_000),
        )

        self.assertFalse(result.breakdown_fired)
        self.assertTrue(h.os.breakdown_active)
        self.assertEqual(h.os.breakdown_restore_beat, 64)
        self.assertEqual(h.clear_calls, [1])
        self.assertEqual(h.direct_calls, [])

    def test_breakdown_restore_rearms_and_clears_state(self) -> None:
        h = _Harness()
        h.os.breakdown_active = True
        h.os.breakdown_restore_beat = 64

        result = h.tick(
            _sp_state(breakdown_end_crossing=True),
            h.ctx(smart_breakdown_enabled=True, this_beat=64, elapsed_ms=32_000),
        )

        self.assertTrue(result.breakdown_fired)
        self.assertFalse(h.os.breakdown_active)
        self.assertEqual(h.os.breakdown_restore_beat, 0)
        self.assertEqual(h.os.phrase_anchor_last_beat, 64)
        self.assertEqual(
            h.direct_calls,
            [((1, 2, 128.0, 32_000, "smart-breakdown"), {"target_beat": 64})],
        )

    def test_breakdown_start_is_blocked_by_drop_arm(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True

        result = h.tick(
            _sp_state(breakdown_start_crossing=True, breakdown_restore_beat=64.0),
            h.ctx(smart_breakdown_enabled=True, this_beat=32),
        )

        self.assertFalse(result.breakdown_fired)
        self.assertFalse(h.os.breakdown_active)
        self.assertEqual(h.clear_calls, [])

    def test_breakdown_path_is_gated_by_pending_autoloop_arm(self) -> None:
        h = _Harness()
        h.os.autoloop_arm_pending = True

        result = h.tick(
            _sp_state(breakdown_start_crossing=True, breakdown_restore_beat=64.0),
            h.ctx(smart_breakdown_enabled=True, this_beat=32),
        )

        self.assertFalse(result.breakdown_fired)
        self.assertFalse(h.os.breakdown_active)
        self.assertEqual(h.os.breakdown_restore_beat, 0)
        self.assertEqual(h.clear_calls, [])
        self.assertEqual(h.direct_calls, [])


class SmartRearmPhraseAnchorTests(unittest.TestCase):
    def test_phrase_anchor_initializes_last_beat_sentinel(self) -> None:
        h = _Harness()
        result = h.tick(
            _sp_state(),
            h.ctx(phrase_anchor_enabled=True, this_beat=75, abs_beat_pos=75.0),
        )

        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.os.phrase_anchor_last_beat, 64)
        self.assertEqual(h.direct_calls, [])

    def test_phrase_anchor_preclear_sends_clear_only(self) -> None:
        h = _Harness()
        h.os.phrase_anchor_last_beat = 0

        result = h.tick(
            _sp_state(
                phrase_anchor_preclear_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(phrase_anchor_enabled=True, this_beat=63, elapsed_ms=31_500),
        )

        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.clear_calls, [1])
        self.assertEqual(h.direct_calls, [])
        self.assertEqual(h.os.phrase_anchor_last_beat, 0)

    def test_phrase_anchor_rearm_updates_last_beat(self) -> None:
        h = _Harness()
        h.os.phrase_anchor_last_beat = 0

        result = h.tick(
            _sp_state(
                phrase_anchor_rearm_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(phrase_anchor_enabled=True, this_beat=64, elapsed_ms=32_000),
        )

        self.assertTrue(result.phrase_anchor_fired)
        self.assertEqual(h.os.phrase_anchor_last_beat, 64)
        self.assertEqual(
            h.direct_calls,
            [((1, 2, 128.0, 32_000, "phrase-anchor"), {"target_beat": 64})],
        )

    def test_phrase_anchor_missed_target_rebases_from_current_beat(self) -> None:
        h = _Harness()
        h.os.phrase_anchor_last_beat = 0

        result = h.tick(
            _sp_state(phrase_anchor_target_beat=64),
            h.ctx(phrase_anchor_enabled=True, this_beat=120, elapsed_ms=60_000),
        )

        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.os.phrase_anchor_last_beat, 120)
        self.assertEqual(h.direct_calls, [])

    def test_phrase_anchor_is_blocked_by_breakdown_active(self) -> None:
        h = _Harness()
        h.os.breakdown_active = True
        h.os.breakdown_restore_beat = 96

        result = h.tick(
            _sp_state(
                phrase_anchor_rearm_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(phrase_anchor_enabled=True, this_beat=64, elapsed_ms=32_000),
        )

        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.direct_calls, [])

    def test_phrase_anchor_path_is_gated_by_pending_autoloop_arm(self) -> None:
        h = _Harness()
        h.os.autoloop_arm_pending = True
        h.os.phrase_anchor_last_beat = 0

        result = h.tick(
            _sp_state(
                phrase_anchor_rearm_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(phrase_anchor_enabled=True, this_beat=64, elapsed_ms=32_000),
        )

        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.os.phrase_anchor_last_beat, 0)
        self.assertEqual(h.direct_calls, [])
        self.assertEqual(h.clear_calls, [])

    def test_phrase_anchor_is_blocked_by_drop_cut_armed(self) -> None:
        h = _Harness()
        h.os.drop_cut_armed = True
        h.os.drop_rearm_beat = 96
        h.os.phrase_anchor_last_beat = 0

        result = h.tick(
            _sp_state(
                phrase_anchor_rearm_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(phrase_anchor_enabled=True, this_beat=64, elapsed_ms=32_000),
        )

        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.os.phrase_anchor_last_beat, 0)
        self.assertTrue(h.os.drop_cut_armed)
        self.assertEqual(h.os.drop_rearm_beat, 96)
        self.assertEqual(h.direct_calls, [])
        self.assertEqual(h.clear_calls, [])


class SmartRearmCoordinatorOrderTests(unittest.TestCase):
    def test_drop_then_breakdown_then_phrase_anchor_order_preserves_suppression(self) -> None:
        h = _Harness()

        result = h.tick(
            _sp_state(
                transition_mask_should_arm=True,
                next_smart_drop_beat=64.0,
                breakdown_start_crossing=True,
                breakdown_restore_beat=96.0,
                phrase_anchor_preclear_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(
                smart_drop_enabled=True,
                smart_breakdown_enabled=True,
                phrase_anchor_enabled=True,
                this_beat=60,
                blackout_mode=True,
            ),
        )

        self.assertEqual(result.drop, SmartDropTickResult(False, True, 64))
        self.assertFalse(result.breakdown_fired)
        self.assertFalse(result.phrase_anchor_fired)
        self.assertTrue(h.os.drop_cut_armed)
        self.assertFalse(h.os.breakdown_active)
        self.assertEqual(h.clear_calls, [])
        self.assertEqual(h.direct_calls, [])

    def test_lighting_mode_gate_skips_all_paths(self) -> None:
        h = _Harness()

        result = h.tick(
            _sp_state(
                transition_mask_should_arm=True,
                next_smart_drop_beat=64.0,
                breakdown_start_crossing=True,
                breakdown_restore_beat=96.0,
                phrase_anchor_preclear_requested=True,
                phrase_anchor_target_beat=64,
            ),
            h.ctx(
                smart_drop_enabled=True,
                smart_breakdown_enabled=True,
                phrase_anchor_enabled=True,
                lighting_mode_is_autoloop=False,
            ),
        )

        self.assertEqual(result.drop, SmartDropTickResult.none())
        self.assertFalse(result.breakdown_fired)
        self.assertFalse(result.phrase_anchor_fired)
        self.assertEqual(h.clear_calls, [])
        self.assertEqual(h.direct_calls, [])


if __name__ == "__main__":
    unittest.main()
