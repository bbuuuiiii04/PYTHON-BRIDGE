import sys
import queue
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    PhraseLabel,
    PhraseSegment,
    BeatSegment,
    SmartPhrasingSnapshot,
    SmartPhrasingState,
    SmartPhrasingDiagnostic,
    SmartPhrasingResult,
    SmartPhrasingEngine,
)
from rb_ss_bridge_v2.config import SMART_DROP_LOOKAHEAD_BEATS  # noqa: E402
from rb_ss_bridge_v2.models import DeckState, OutputState  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import (  # noqa: E402
    StateManager,
    SmartDropTickResult,
    _smart_drop_tick,
)

class TestSmartPhrasing(unittest.TestCase):
    def setUp(self):
        self.engine = SmartPhrasingEngine()

    def _default_snap(self, **kwargs) -> SmartPhrasingSnapshot:
        defaults = dict(
            deck_id="1",
            track_id="A",
            is_playing=True,
            abs_beat=0.0,
            phrase_segments=(),
            smart_drop_beats=(),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        defaults.update(kwargs)
        return SmartPhrasingSnapshot(**defaults)

    def _legacy_smart_drop_sm(
        self,
        *,
        smart_drops: list[int],
        smart_breakdowns: list[int] | None = None,
        autoloop_arm_pending: bool = False,
        pending_autoloop_arm_meta: object | None = None,
    ) -> SimpleNamespace:
        out = Mock()
        deck = DeckState(number=1)
        deck.meta.filepath = "/music/drop.mp3"
        deck.meta.bpm = 130.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.smart_drops = list(smart_drops)
        deck.meta.smart_breakdowns = list(smart_breakdowns or [])
        sm = SimpleNamespace(
            _os=OutputState(lighting_mode="autoloop"),
            _deck={1: deck, 2: DeckState(number=2)},
            _out=out,
        )
        sm._os.autoloop_arm_pending = autoloop_arm_pending
        sm._os.pending_autoloop_arm_meta = pending_autoloop_arm_meta
        return sm

    def _sp_state(self, **overrides) -> SmartPhrasingState:
        defaults = dict(reason="test")
        defaults.update(overrides)
        return SmartPhrasingState(**defaults)

    def test_default_state_for_missing_track(self):
        snap = self._default_snap(deck_id=None)
        res = self.engine.update(snap)
        self.assertEqual(res.state.current_phrase_label, "other")
        self.assertFalse(res.state.smart_drop_crossing)
        self.assertFalse(res.state.smart_buildup_active)
        self.assertFalse(res.state.smart_breakdown_active)

    def test_resolves_current_phrase_label_and_booleans(self):
        snap = self._default_snap(
            phrase_segments=(
                PhraseSegment(start_beat=0.0, end_beat=32.0, label="up"),
                PhraseSegment(start_beat=32.0, end_beat=64.0, label="chorus"),
                PhraseSegment(start_beat=64.0, end_beat=96.0, label="low"),
            )
        )
        
        res = self.engine.update(replace(snap, abs_beat=16.0))
        self.assertEqual(res.state.current_phrase_label, "up")
        self.assertTrue(res.state.current_phrase_is_up)
        
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertEqual(res.state.current_phrase_label, "chorus")
        self.assertTrue(res.state.current_phrase_is_chorus)
        
        res = self.engine.update(replace(snap, abs_beat=65.0))
        self.assertEqual(res.state.current_phrase_label, "low")
        self.assertTrue(res.state.current_phrase_is_low)
        
        res = self.engine.update(replace(snap, abs_beat=100.0))
        self.assertEqual(res.state.current_phrase_label, "other")
        self.assertTrue(not res.state.current_phrase_is_up and not res.state.current_phrase_is_chorus and not res.state.current_phrase_is_low)

    def test_computes_next_drop_and_beats_to_drop(self):
        snap = self._default_snap(smart_drop_beats=(32.0, 64.0))
        res = self.engine.update(replace(snap, abs_beat=16.0))
        self.assertEqual(res.state.next_smart_drop_beat, 32.0)
        self.assertEqual(res.state.beats_to_next_drop, 16.0)

    def test_drop_crossing_fires_exactly_once(self):
        snap = self._default_snap(smart_drop_beats=(64.0,))
        self.engine.update(replace(snap, abs_beat=63.5))
        
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing)
        
        res2 = self.engine.update(replace(snap, abs_beat=64.25))
        self.assertFalse(res2.state.smart_drop_crossing)

    def test_drop_crossing_is_not_blackout_dependent(self):
        # We did not pass any blackout parameters.
        snap = self._default_snap(smart_drop_beats=(64.0,))
        self.engine.update(replace(snap, abs_beat=63.5))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing)

    def test_buildup_only_in_up_phrase_before_future_drop(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            phrase_segments=(
                PhraseSegment(start_beat=0.0, end_beat=32.0, label="chorus"),
                PhraseSegment(start_beat=32.0, end_beat=64.0, label="up"),
            ),
            phrase_lookahead_beats=32.0
        )
        
        # in chorus
        res = self.engine.update(replace(snap, abs_beat=30.0))
        self.assertFalse(res.state.smart_buildup_active)
        
        # in up, within lookahead
        res = self.engine.update(replace(snap, abs_beat=33.0))
        self.assertTrue(res.state.smart_buildup_active)
        
        # after drop
        self.engine.update(replace(snap, abs_beat=64.0))
        res = self.engine.update(replace(snap, abs_beat=65.0))
        self.assertFalse(res.state.smart_buildup_active)

    def test_breakdown_active_and_crossings(self):
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),)
        )
        self.engine.update(replace(snap, abs_beat=31.0))
        
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.smart_breakdown_active)
        self.assertTrue(res.state.breakdown_start_crossing)
        
        res = self.engine.update(replace(snap, abs_beat=40.0))
        self.assertTrue(res.state.smart_breakdown_active)
        self.assertFalse(res.state.breakdown_start_crossing)
        
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertFalse(res.state.smart_breakdown_active) # Since < end_beat
        self.assertTrue(res.state.breakdown_end_crossing)

    def test_breakdown_end_crossing_fires_outside_segment(self):
        """Crossing fires when jumping from 63.5 to 64.0 (end of 32-64)."""
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),)
        )
        self.engine.update(replace(snap, abs_beat=63.5))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.breakdown_end_crossing)
        self.assertFalse(res.state.smart_breakdown_active)

    def test_breakdown_end_crossing_does_not_fire_inside_segment(self):
        """Crossing should not fire when moving within the segment."""
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),)
        )
        self.engine.update(replace(snap, abs_beat=40.0))
        res = self.engine.update(replace(snap, abs_beat=41.0))
        self.assertFalse(res.state.breakdown_end_crossing)
        self.assertTrue(res.state.smart_breakdown_active)

    def test_breakdown_start_and_end_crossing_fire_when_jumping_over_entire_segment(self):
        """If jumping over an entire breakdown segment, both start and end crossings fire."""
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),)
        )
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=65.0))
        self.assertTrue(res.state.breakdown_start_crossing)
        self.assertTrue(res.state.breakdown_end_crossing)
        self.assertFalse(res.state.smart_breakdown_active)

    def test_breakdown_end_crossing_deduplication(self):
        """Crossing should only fire once."""
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),)
        )
        self.engine.update(replace(snap, abs_beat=63.5))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.breakdown_end_crossing)
        
        res = self.engine.update(replace(snap, abs_beat=64.1))
        self.assertFalse(res.state.breakdown_end_crossing)

    def test_empty_metadata_is_safe(self):
        snap = self._default_snap()
        res = self.engine.update(snap)
        self.assertEqual(res.state.current_phrase_label, "other")
        self.assertFalse(res.state.smart_buildup_active)
        self.assertFalse(res.state.smart_breakdown_active)

    def test_resets_on_stop_no_track_deck_change_track_change(self):
        snap = self._default_snap(smart_drop_beats=(64.0,))
        self.engine.update(replace(snap, abs_beat=63.0))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing)
        
        # Stop
        res = self.engine.update(replace(snap, abs_beat=65.0, is_playing=False))
        self.assertEqual(res.state.reason, "not_playing")
        
        # Start again, same beat
        self.engine.update(replace(snap, abs_beat=63.0))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing) # Should cross again because we reset
        
    def test_playhead_jump_backward_resets(self):
        snap = self._default_snap(smart_drop_beats=(64.0,))
        self.engine.update(replace(snap, abs_beat=63.0))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing)
        
        # Jump backward
        self.engine.update(replace(snap, abs_beat=30.0))
        
        # Forward to drop again
        self.engine.update(replace(snap, abs_beat=63.0))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing) # Should cross again

    def test_transition_mask_arm_and_clear_intents(self):
        snap = self._default_snap(smart_drop_beats=(64.0,), transition_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=50.0))
        
        res = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertTrue(res.state.transition_mask_should_arm)
        self.assertTrue(res.state.transition_window_active)
        
        res = self.engine.update(replace(snap, abs_beat=61.0))
        self.assertFalse(res.state.transition_mask_should_arm)
        self.assertTrue(res.state.transition_window_active)
        
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.transition_mask_should_clear)
        self.assertFalse(res.state.transition_window_active)

    def test_transition_window_beats_equals_smart_drop_lookahead_beats(self):
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        self.assertEqual(sm._sp_transition_window, float(SMART_DROP_LOOKAHEAD_BEATS))

    def test_transition_mask_arm_fires_on_same_tick_as_smart_drop_blackout_armed(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=float(before_arm)))
        arm_state = self.engine.update(replace(snap, abs_beat=float(arm_beat))).state
        self.assertTrue(arm_state.transition_mask_should_arm)

        legacy = self._legacy_smart_drop_sm(smart_drops=[drop_beat])
        legacy_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat),
            int(arm_beat * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=True,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        self.assertTrue(legacy_signal.blackout_armed)
        self.assertFalse(legacy_signal.crossing)
        self.assertEqual(legacy_signal.target_beat, drop_beat)

    def test_transition_mask_arm_latched_sets_on_window_arm(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=4.0,
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        arm_state = self.engine.update(replace(snap, abs_beat=60.0)).state
        self.assertTrue(arm_state.transition_mask_should_arm)
        self.assertTrue(arm_state.transition_mask_arm_latched)

    def test_transition_mask_arm_latched_clears_on_crossing(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=4.0,
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        self.engine.update(replace(snap, abs_beat=60.0))
        crossing_state = self.engine.update(replace(snap, abs_beat=64.0)).state
        self.assertTrue(crossing_state.smart_drop_crossing)
        self.assertFalse(crossing_state.transition_mask_arm_latched)

    def test_transition_mask_arm_latched_clears_on_manual_clear_and_reset(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=4.0,
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        latched = self.engine.update(replace(snap, abs_beat=60.0)).state
        self.assertTrue(latched.transition_mask_arm_latched)

        self.engine.clear_blackout_latch()
        after_api_clear = self.engine.update(replace(snap, abs_beat=60.5)).state
        self.assertFalse(after_api_clear.transition_mask_arm_latched)

        reset_state = self.engine.reset("test-reset")
        self.assertFalse(reset_state.transition_mask_arm_latched)

    def test_transition_mask_arm_breakdown_clears_mid_window_rising_edge_gap(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS

        snap_with_breakdown = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            breakdown_segments=(BeatSegment(start_beat=59.0, end_beat=62.0),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap_with_breakdown, abs_beat=float(arm_beat - 1)))
        suppressed = self.engine.update(replace(snap_with_breakdown, abs_beat=float(arm_beat))).state
        self.assertFalse(suppressed.transition_mask_should_arm)
        self.assertTrue(suppressed.transition_window_active)

        snap_without_breakdown = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        still_in_window = self.engine.update(
            replace(snap_without_breakdown, abs_beat=float(arm_beat + 1))
        ).state
        self.assertTrue(still_in_window.transition_mask_should_arm)
        self.assertTrue(still_in_window.transition_window_active)

    def test_transition_mask_arm_re_fires_mid_window_after_breakdown_clears(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        with_breakdown = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            breakdown_segments=(BeatSegment(start_beat=59.0, end_beat=62.0),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(with_breakdown, abs_beat=float(arm_beat - 1)))
        suppressed = self.engine.update(replace(with_breakdown, abs_beat=float(arm_beat))).state
        self.assertFalse(suppressed.transition_mask_should_arm)

        without_breakdown = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        retried = self.engine.update(
            replace(without_breakdown, abs_beat=float(arm_beat + 1))
        ).state
        self.assertTrue(retried.transition_mask_should_arm)
        self.assertTrue(retried.transition_window_active)

    def test_transition_mask_arm_re_fires_after_breakdown_between_clears(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        with_between = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            breakdown_segments=(BeatSegment(start_beat=float(arm_beat + 1), end_beat=63.0),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(with_between, abs_beat=float(arm_beat - 1)))
        suppressed = self.engine.update(replace(with_between, abs_beat=float(arm_beat))).state
        self.assertFalse(suppressed.transition_mask_should_arm)

        no_between = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        retried = self.engine.update(replace(no_between, abs_beat=float(arm_beat + 1))).state
        self.assertTrue(retried.transition_mask_should_arm)
        self.assertTrue(retried.transition_window_active)

    def test_transition_window_arm_suppressed_resets_on_engine_reset(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            breakdown_segments=(BeatSegment(start_beat=59.0, end_beat=62.0),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        suppressed = self.engine.update(replace(snap, abs_beat=60.0)).state
        self.assertFalse(suppressed.transition_mask_should_arm)
        self.assertTrue(suppressed.transition_window_active)

        self.engine.reset("test-reset")
        no_breakdown = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(no_breakdown, abs_beat=59.0))
        armed = self.engine.update(replace(no_breakdown, abs_beat=60.0)).state
        self.assertTrue(armed.transition_mask_should_arm)

    def test_breakdown_restore_beat_populated_when_active(self):
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),)
        )
        res = self.engine.update(replace(snap, abs_beat=40.0))
        self.assertTrue(res.state.smart_breakdown_active)
        self.assertEqual(res.state.breakdown_restore_beat, 64.0)

    def test_breakdown_restore_beat_populated_on_start_crossing_jump_over(self):
        snap = self._default_snap(
            breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=40.0),)
        )
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=50.0))
        self.assertTrue(res.state.breakdown_start_crossing)
        self.assertTrue(res.state.breakdown_end_crossing)
        self.assertEqual(res.state.breakdown_restore_beat, 40.0)

    def test_transition_mask_arm_pending_autoloop_meta_documents_current_divergence(self):
        """Current behavior doc: revisit in PR 5d before production arm migration."""
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        legacy = self._legacy_smart_drop_sm(
            smart_drops=[drop_beat],
            pending_autoloop_arm_meta=object(),
        )
        legacy_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat),
            int(arm_beat * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=False,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        self.assertEqual(legacy_signal, SmartDropTickResult.none())

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=float(before_arm)))
        arm_state = self.engine.update(replace(snap, abs_beat=float(arm_beat))).state
        self.assertTrue(arm_state.transition_mask_should_arm)

    def test_transition_mask_arm_does_not_fire_before_window_entry(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        no_arm_state = self.engine.update(replace(snap, abs_beat=float(before_arm))).state
        self.assertFalse(no_arm_state.transition_mask_should_arm)

        legacy = self._legacy_smart_drop_sm(smart_drops=[drop_beat])
        legacy_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(before_arm),
            int(before_arm * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=False,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        self.assertEqual(legacy_signal, SmartDropTickResult.none())

    def test_transition_mask_arm_fires_only_once_per_window_entry(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=float(before_arm)))
        first_in_window = self.engine.update(replace(snap, abs_beat=float(arm_beat))).state
        still_in_window = self.engine.update(replace(snap, abs_beat=float(arm_beat + 1))).state

        self.assertTrue(first_in_window.transition_mask_should_arm)
        self.assertFalse(still_in_window.transition_mask_should_arm)
        self.assertTrue(still_in_window.transition_window_active)

        legacy = self._legacy_smart_drop_sm(smart_drops=[drop_beat])
        first_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat),
            int(arm_beat * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=True,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        second_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat + 1),
            int((arm_beat + 1) * 500),
            sp_state=self._sp_state(
                smart_drop_crossing=False,
            ),
        )
        self.assertTrue(first_signal.blackout_armed)
        self.assertFalse(first_signal.crossing)
        self.assertEqual(first_signal.target_beat, drop_beat)
        self.assertEqual(second_signal, SmartDropTickResult.none())
        self.assertTrue(legacy._os.drop_cut_armed)

    def test_transition_mask_arm_breakdown_between_suppresses_arm(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        legacy = self._legacy_smart_drop_sm(
            smart_drops=[drop_beat],
            smart_breakdowns=[arm_beat + 2],
        )
        legacy_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat),
            int(arm_beat * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=False,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        self.assertEqual(legacy_signal, SmartDropTickResult.none())

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            breakdown_segments=(BeatSegment(start_beat=float(arm_beat + 1), end_beat=float(drop_beat + 1)),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=float(before_arm)))
        arm_state = self.engine.update(replace(snap, abs_beat=float(arm_beat))).state
        # Parity confirmed at window entry; mid-window re-arm after breakdown clears is a documented rising-edge gap.
        self.assertFalse(arm_state.transition_mask_should_arm)

    def test_transition_mask_arm_breakdown_active_suppresses_arm(self):
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        legacy = self._legacy_smart_drop_sm(smart_drops=[drop_beat])
        legacy._os.breakdown_active = True
        legacy_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat),
            int(arm_beat * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=False,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        self.assertEqual(legacy_signal, SmartDropTickResult.none())

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            breakdown_segments=(
                BeatSegment(start_beat=float(arm_beat - 1), end_beat=float(arm_beat + 1)),
            ),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=float(before_arm)))
        arm_state = self.engine.update(replace(snap, abs_beat=float(arm_beat))).state
        # Engine suppresses via smart_breakdown_active / musical breakdown segment; legacy suppresses via
        # os.breakdown_active. This confirms aligned suppression behavior, not identical stimulus parity.
        self.assertFalse(arm_state.transition_mask_should_arm)

    def test_transition_mask_arm_autoloop_pending_documents_current_divergence(self):
        """Current behavior doc: revisit in PR 5d before production arm migration."""
        drop_beat = 64
        arm_beat = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        before_arm = arm_beat - 1

        legacy = self._legacy_smart_drop_sm(
            smart_drops=[drop_beat],
            autoloop_arm_pending=True,
        )
        legacy_signal = _smart_drop_tick(
            legacy,
            1,
            2,
            130.0,
            int(arm_beat),
            int(arm_beat * 500),
            sp_state=self._sp_state(
                transition_mask_should_arm=True,
                next_smart_drop_beat=float(drop_beat),
            ),
        )
        self.assertEqual(legacy_signal, SmartDropTickResult.none())

        snap = self._default_snap(
            smart_drop_beats=(float(drop_beat),),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=float(before_arm)))
        arm_state = self.engine.update(replace(snap, abs_beat=float(arm_beat))).state
        self.assertTrue(arm_state.transition_mask_should_arm)

    def test_transition_mask_arm_resets_on_deck_change(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        arm_state = self.engine.update(replace(snap, abs_beat=60.0)).state
        self.assertTrue(arm_state.transition_mask_should_arm)

        reset_state = self.engine.update(
            replace(snap, deck_id="2", track_id="A", abs_beat=30.0)
        ).state
        self.assertFalse(reset_state.transition_mask_should_arm)
        self.assertFalse(reset_state.transition_window_active)

        self.engine.update(replace(snap, deck_id="2", track_id="A", abs_beat=59.0))
        rearm_state = self.engine.update(
            replace(snap, deck_id="2", track_id="A", abs_beat=60.0)
        ).state
        self.assertTrue(rearm_state.transition_mask_should_arm)

    def test_transition_mask_arm_resets_on_track_change(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        arm_state = self.engine.update(replace(snap, abs_beat=60.0)).state
        self.assertTrue(arm_state.transition_mask_should_arm)

        reset_state = self.engine.update(
            replace(snap, deck_id="1", track_id="B", abs_beat=30.0)
        ).state
        self.assertFalse(reset_state.transition_mask_should_arm)
        self.assertFalse(reset_state.transition_window_active)

        self.engine.update(replace(snap, deck_id="1", track_id="B", abs_beat=59.0))
        rearm_state = self.engine.update(
            replace(snap, deck_id="1", track_id="B", abs_beat=60.0)
        ).state
        self.assertTrue(rearm_state.transition_mask_should_arm)

    def test_transition_mask_arm_resets_on_backward_jump_from_inside_window(self):
        snap = self._default_snap(
            smart_drop_beats=(64.0,),
            transition_window_beats=float(SMART_DROP_LOOKAHEAD_BEATS),
        )
        self.engine.update(replace(snap, abs_beat=59.0))
        self.engine.update(replace(snap, abs_beat=60.0))
        inside_window = self.engine.update(replace(snap, abs_beat=61.0)).state
        self.assertTrue(inside_window.transition_window_active)
        self.assertFalse(inside_window.transition_mask_should_arm)

        reset_state = self.engine.update(replace(snap, abs_beat=30.0)).state
        self.assertFalse(reset_state.transition_mask_should_arm)
        self.assertFalse(reset_state.transition_window_active)

        self.engine.update(replace(snap, abs_beat=59.0))
        rearm_state = self.engine.update(replace(snap, abs_beat=60.0)).state
        self.assertTrue(rearm_state.transition_mask_should_arm)

    def test_transition_window_active_resets_on_engine_reset(self):
        def _activate_transition_window(engine: SmartPhrasingEngine, snap: SmartPhrasingSnapshot) -> None:
            engine.update(replace(snap, abs_beat=50.0))
            active = engine.update(replace(snap, abs_beat=61.0))
            self.assertTrue(active.state.transition_window_active)

        base = self._default_snap(smart_drop_beats=(64.0,), transition_window_beats=4.0)

        stop_engine = SmartPhrasingEngine()
        _activate_transition_window(stop_engine, base)
        stop_res = stop_engine.update(replace(base, abs_beat=61.0, is_playing=False))
        self.assertFalse(stop_res.state.transition_window_active)
        self.assertEqual(stop_res.state.reason, "not_playing")

        no_track_engine = SmartPhrasingEngine()
        _activate_transition_window(no_track_engine, base)
        no_track_res = no_track_engine.update(replace(base, abs_beat=61.0, track_id=None))
        self.assertFalse(no_track_res.state.transition_window_active)
        self.assertEqual(no_track_res.state.reason, "no_track")

        deck_change_engine = SmartPhrasingEngine()
        _activate_transition_window(deck_change_engine, base)
        deck_change_res = deck_change_engine.update(
            replace(base, deck_id="2", track_id="A", abs_beat=30.0)
        )
        self.assertFalse(deck_change_res.state.transition_window_active)

        track_change_engine = SmartPhrasingEngine()
        _activate_transition_window(track_change_engine, base)
        track_change_res = track_change_engine.update(
            replace(base, deck_id="1", track_id="B", abs_beat=30.0)
        )
        self.assertFalse(track_change_res.state.transition_window_active)

        playhead_jump_engine = SmartPhrasingEngine()
        _activate_transition_window(playhead_jump_engine, base)
        playhead_jump_res = playhead_jump_engine.update(replace(base, abs_beat=30.0))
        self.assertFalse(playhead_jump_res.state.transition_window_active)

    def test_stop_clears_previous_beat_baseline(self):
        snap = self._default_snap(smart_drop_beats=(64.0,))
        self.engine.update(replace(snap, abs_beat=63.5))
        
        # Stop at 63.5
        self.engine.update(replace(snap, abs_beat=63.5, is_playing=False))
        
        # Resume at 64.0
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertFalse(res.state.smart_drop_crossing)
        
        # Next tick
        res2 = self.engine.update(replace(snap, abs_beat=64.25))
        self.assertFalse(res2.state.smart_drop_crossing)

    def test_reset_diagnostic_event_name(self):
        snap = self._default_snap(is_playing=False)
        res = self.engine.update(snap)
        
        found_reset = False
        for diag in res.diagnostics:
            if diag.event == "smart_phrasing_reset":
                found_reset = True
                self.assertEqual(diag.reason, "not_playing")
        self.assertTrue(found_reset)


    def test_smart_drop_preclear_requested_fires_on_window_entry(self):
        """Preclear intent fires once when smart_drop_window_active transitions to True."""
        snap = self._default_snap(smart_drop_beats=(64.0,), drop_window_beats=4.0)
        # Outside window (beat 59)
        self.engine.update(replace(snap, abs_beat=59.0))
        
        # Enter window (beat 60)
        res = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertTrue(res.state.smart_drop_window_active)
        self.assertTrue(res.state.smart_drop_preclear_requested)

    def test_smart_drop_preclear_requested_does_not_fire_repeatedly(self):
        """Preclear intent does not fire repeatedly while remaining inside the window."""
        snap = self._default_snap(smart_drop_beats=(64.0,), drop_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=59.0))
        
        # Enter window
        res = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertTrue(res.state.smart_drop_preclear_requested)
        
        # Remain in window
        res = self.engine.update(replace(snap, abs_beat=61.0))
        self.assertTrue(res.state.smart_drop_window_active)
        self.assertFalse(res.state.smart_drop_preclear_requested)

    def test_clear_smart_rearm_state_drops_smart_drop_window_latch(self):
        snap = self._default_snap(smart_drop_beats=(64.0,), drop_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=59.0))
        entered = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertTrue(entered.state.smart_drop_window_active)
        self.assertTrue(entered.state.smart_drop_preclear_requested)

        self.engine.clear_smart_rearm_state()
        self.assertFalse(self.engine._smart_drop_window_active)
        self.assertIsNone(self.engine._active_drop_beat)

        next_tick = self.engine.update(replace(snap, abs_beat=60.5))
        self.assertTrue(next_tick.state.smart_drop_window_active)
        self.assertTrue(next_tick.state.smart_drop_preclear_requested)

    def test_smart_drop_rearm_requested_fires_on_crossing(self):
        """Rearm intent fires when smart_drop_crossing fires."""
        snap = self._default_snap(smart_drop_beats=(64.0,), drop_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=63.0))
        
        # Cross drop
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_crossing)
        self.assertTrue(res.state.smart_drop_rearm_requested)

    def test_smart_drop_rearm_requested_deduplicates(self):
        """Rearm intent deduplicates with existing smart_drop_crossing deduplication."""
        snap = self._default_snap(smart_drop_beats=(64.0,), drop_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=63.0))
        
        # Cross drop
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.smart_drop_rearm_requested)
        
        # Cross again (same tick/playhead didn't jump back)
        res = self.engine.update(replace(snap, abs_beat=64.1))
        self.assertFalse(res.state.smart_drop_crossing)
        self.assertFalse(res.state.smart_drop_rearm_requested)

    def test_smart_drop_intents_preserve_next_drop_semantics(self):
        """Preclear and crossing behavior preserve next_smart_drop_beat semantics."""
        snap = self._default_snap(smart_drop_beats=(64.0, 128.0), drop_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=59.0))
        
        # Enter window for drop 64
        res = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertEqual(res.state.next_smart_drop_beat, 64.0)
        
        # Cross drop 64
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertEqual(res.state.next_smart_drop_beat, 128.0)
        
        # Advance to drop 128 window
        self.engine.update(replace(snap, abs_beat=123.0))
        res = self.engine.update(replace(snap, abs_beat=124.0))
        self.assertEqual(res.state.next_smart_drop_beat, 128.0)
        self.assertTrue(res.state.smart_drop_preclear_requested)

    def test_smart_drop_intents_reset_on_playhead_jump(self):
        """Playhead jump clears intent state allowing it to fire again."""
        snap = self._default_snap(smart_drop_beats=(64.0,), drop_window_beats=4.0)
        self.engine.update(replace(snap, abs_beat=59.0))
        
        # Enter window
        res = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertTrue(res.state.smart_drop_preclear_requested)
        
        # Jump backward
        res = self.engine.update(replace(snap, abs_beat=59.0))
        self.assertEqual(res.diagnostics[0].reason, "playhead_jump_backward")
        self.assertFalse(res.state.smart_drop_preclear_requested)
        self.assertFalse(res.state.smart_drop_window_active)
        
        # Enter window again
        res = self.engine.update(replace(snap, abs_beat=60.0))
        self.assertTrue(res.state.smart_drop_preclear_requested)

    def test_smart_breakdown_clear_requested_fires_on_start(self):
        """Clear intent fires on breakdown start crossing."""
        snap = self._default_snap(breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.breakdown_start_crossing)
        self.assertTrue(res.state.smart_breakdown_clear_requested)

    def test_smart_breakdown_clear_requested_does_not_fire_repeatedly(self):
        """Clear intent does not fire repeatedly while inside breakdown."""
        snap = self._default_snap(breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),))
        self.engine.update(replace(snap, abs_beat=31.0))
        self.engine.update(replace(snap, abs_beat=32.0))
        res = self.engine.update(replace(snap, abs_beat=33.0))
        self.assertTrue(res.state.smart_breakdown_active)
        self.assertFalse(res.state.breakdown_start_crossing)
        self.assertFalse(res.state.smart_breakdown_clear_requested)

    def test_smart_breakdown_restore_requested_fires_on_end(self):
        """Restore intent fires on breakdown end crossing."""
        snap = self._default_snap(breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),))
        self.engine.update(replace(snap, abs_beat=63.0))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.breakdown_end_crossing)
        self.assertTrue(res.state.smart_breakdown_restore_requested)

    def test_smart_breakdown_restore_requested_does_not_fire_repeatedly(self):
        """Restore intent does not fire repeatedly after breakdown ends."""
        snap = self._default_snap(breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),))
        self.engine.update(replace(snap, abs_beat=63.0))
        self.engine.update(replace(snap, abs_beat=64.0))
        res = self.engine.update(replace(snap, abs_beat=65.0))
        self.assertFalse(res.state.breakdown_end_crossing)
        self.assertFalse(res.state.smart_breakdown_restore_requested)

    def test_smart_breakdown_intents_fire_simultaneously_on_jump(self):
        """Jumping over an entire breakdown can fire both clear and restore in the same tick."""
        snap = self._default_snap(breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=65.0))
        self.assertTrue(res.state.smart_breakdown_clear_requested)
        self.assertTrue(res.state.smart_breakdown_restore_requested)

    def test_smart_breakdown_intents_reset_on_playhead_jump(self):
        """Reset/playhead jump allows breakdown intents to fire again appropriately."""
        snap = self._default_snap(breakdown_segments=(BeatSegment(start_beat=32.0, end_beat=64.0),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.smart_breakdown_clear_requested)
        
        # Jump backward
        res = self.engine.update(replace(snap, abs_beat=31.0))
        self.assertEqual(res.diagnostics[0].reason, "playhead_jump_backward")
        self.assertFalse(res.state.smart_breakdown_clear_requested)
        
        # Cross again
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.smart_breakdown_clear_requested)

    def test_phrase_anchor_requested_fires_on_segment_start(self):
        """phrase anchor intent fires when crossing a phrase segment start."""
        snap = self._default_snap(phrase_segments=(PhraseSegment(start_beat=32.0, end_beat=64.0, label="up"),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.phrase_anchor_requested)

    def test_phrase_anchor_requested_does_not_fire_repeatedly(self):
        """phrase anchor intent does not fire repeatedly within the same segment."""
        snap = self._default_snap(phrase_segments=(PhraseSegment(start_beat=32.0, end_beat=64.0, label="up"),))
        self.engine.update(replace(snap, abs_beat=31.0))
        self.engine.update(replace(snap, abs_beat=32.0))
        res = self.engine.update(replace(snap, abs_beat=33.0))
        self.assertFalse(res.state.phrase_anchor_requested)

    def test_phrase_anchor_requested_fires_for_later_segment(self):
        """phrase anchor intent can fire for a later phrase segment."""
        snap = self._default_snap(phrase_segments=(
            PhraseSegment(start_beat=32.0, end_beat=64.0, label="up"),
            PhraseSegment(start_beat=64.0, end_beat=96.0, label="chorus"),
        ))
        self.engine.update(replace(snap, abs_beat=31.0))
        self.engine.update(replace(snap, abs_beat=32.0))
        self.engine.update(replace(snap, abs_beat=63.0))
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertTrue(res.state.phrase_anchor_requested)

    def test_phrase_anchor_requested_fires_when_jumping_over_start(self):
        """jumping over a phrase segment start fires the anchor intent."""
        snap = self._default_snap(phrase_segments=(PhraseSegment(start_beat=32.0, end_beat=64.0, label="up"),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=33.0))
        self.assertTrue(res.state.phrase_anchor_requested)

    def test_phrase_anchor_requested_resets_on_playhead_jump(self):
        """reset/playhead jump allows phrase anchor to fire again appropriately."""
        snap = self._default_snap(phrase_segments=(PhraseSegment(start_beat=32.0, end_beat=64.0, label="up"),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.phrase_anchor_requested)
        
        # Jump backward
        res = self.engine.update(replace(snap, abs_beat=31.0))
        self.assertEqual(res.diagnostics[0].reason, "playhead_jump_backward")
        self.assertFalse(res.state.phrase_anchor_requested)
        
        # Cross again
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.phrase_anchor_requested)

    def test_phrase_anchor_preserves_current_phrase_label(self):
        """current phrase label/is_up/is_chorus behavior remains unchanged."""
        snap = self._default_snap(phrase_segments=(PhraseSegment(start_beat=32.0, end_beat=64.0, label="chorus"),))
        self.engine.update(replace(snap, abs_beat=31.0))
        res = self.engine.update(replace(snap, abs_beat=32.0))
        self.assertTrue(res.state.phrase_anchor_requested)
        self.assertEqual(res.state.current_phrase_label, "chorus")
        self.assertTrue(res.state.current_phrase_is_chorus)
        self.assertFalse(res.state.current_phrase_is_up)

    def test_phrase_anchor_periodic_intents_none_when_sentinel(self):
        snap = self._default_snap(phrase_anchor_last_beat=-1)
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertFalse(res.state.phrase_anchor_preclear_requested)
        self.assertFalse(res.state.phrase_anchor_rearm_requested)
        self.assertIsNone(res.state.phrase_anchor_target_beat)

    def test_phrase_anchor_periodic_target_beat_from_last_plus_period(self):
        snap = self._default_snap(phrase_anchor_last_beat=64, phrase_anchor_period_beats=64)
        res = self.engine.update(replace(snap, abs_beat=100.0))
        self.assertEqual(res.state.phrase_anchor_target_beat, 128)
        self.assertFalse(res.state.phrase_anchor_preclear_requested)
        self.assertFalse(res.state.phrase_anchor_rearm_requested)

    def test_phrase_anchor_periodic_preclear_fires_at_target_minus_one(self):
        snap = self._default_snap(phrase_anchor_last_beat=0, phrase_anchor_period_beats=64)
        res = self.engine.update(replace(snap, abs_beat=63.0))
        self.assertEqual(res.state.phrase_anchor_target_beat, 64)
        self.assertTrue(res.state.phrase_anchor_preclear_requested)
        self.assertFalse(res.state.phrase_anchor_rearm_requested)

    def test_phrase_anchor_periodic_rearm_fires_at_target(self):
        snap = self._default_snap(phrase_anchor_last_beat=0, phrase_anchor_period_beats=64)
        res = self.engine.update(replace(snap, abs_beat=64.0))
        self.assertEqual(res.state.phrase_anchor_target_beat, 64)
        self.assertFalse(res.state.phrase_anchor_preclear_requested)
        self.assertTrue(res.state.phrase_anchor_rearm_requested)

    def test_phrase_anchor_periodic_rearm_fires_within_plus_8_window(self):
        snap = self._default_snap(phrase_anchor_last_beat=0, phrase_anchor_period_beats=64)
        res = self.engine.update(replace(snap, abs_beat=70.0))
        self.assertEqual(res.state.phrase_anchor_target_beat, 64)
        self.assertFalse(res.state.phrase_anchor_preclear_requested)
        self.assertTrue(res.state.phrase_anchor_rearm_requested)

    def test_phrase_anchor_periodic_target_emitted_beyond_plus_8_window(self):
        snap = self._default_snap(phrase_anchor_last_beat=0, phrase_anchor_period_beats=64)
        res = self.engine.update(replace(snap, abs_beat=73.0))
        self.assertEqual(res.state.phrase_anchor_target_beat, 64)
        self.assertFalse(res.state.phrase_anchor_preclear_requested)
        self.assertFalse(res.state.phrase_anchor_rearm_requested)

    def test_phrase_anchor_periodic_custom_period(self):
        snap = self._default_snap(phrase_anchor_last_beat=64, phrase_anchor_period_beats=32)
        res = self.engine.update(replace(snap, abs_beat=95.0))
        self.assertEqual(res.state.phrase_anchor_target_beat, 96)
        self.assertTrue(res.state.phrase_anchor_preclear_requested)
        self.assertFalse(res.state.phrase_anchor_rearm_requested)

    def test_phrase_anchor_periodic_period_zero_disables_intents(self):
        snap = self._default_snap(phrase_anchor_last_beat=64, phrase_anchor_period_beats=0)
        res = self.engine.update(replace(snap, abs_beat=96.0))
        self.assertIsNone(res.state.phrase_anchor_target_beat)
        self.assertFalse(res.state.phrase_anchor_preclear_requested)
        self.assertFalse(res.state.phrase_anchor_rearm_requested)
if __name__ == '__main__':
    unittest.main()
