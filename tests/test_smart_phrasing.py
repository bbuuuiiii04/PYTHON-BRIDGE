import sys
import unittest
from dataclasses import replace
from pathlib import Path

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
if __name__ == '__main__':
    unittest.main()
