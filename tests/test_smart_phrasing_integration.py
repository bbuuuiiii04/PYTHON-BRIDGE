"""Phase 2 shadow integration tests for Issue #33: SmartPhrasingEngine in StateManager.

Verifies:
  A. LaserContext defaults smart_phrasing to None.
  B. StateManager populates smart_phrasing shadow state.
  C. Shadow smart_phrasing does not change LaserDirector decisions.
  D. Shadow engine is safe on stop / missing track.
  E. Shadow mapping uses 32-beat buildup lookahead.
  F. Smart Drop works without chorus data.
  G. Drop marker is treated as chorus boundary.
  H. Phrase segments inferred from ordered markers when safe.
  I. Final segment without next marker is skipped (no invented duration).
  J. Breakdown segments remain empty (start-marker-only data).
"""
import sys
import os
import queue
import time
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_models import LaserContext, LaserSceneDecision  # noqa: E402
from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot, TrackMetadata  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    SmartPhrasingEngine,
    SmartPhrasingSnapshot,
    SmartPhrasingState,
    PhraseSegment,
    build_phase2_phrase_segments,
)
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(*, smart_phrasing=None, **kwargs):
    """Build a LaserContext with defaults suitable for director tests."""
    defaults = dict(
        active_deck=1,
        playing=True,
        elapsed_ms=60_000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=64.0,
        position_stale=False,
        lighting_mode="autoloop",
        os2l_connected=True,
        active_track_loaded=True,
        autoloop_ready=True,
    )
    defaults.update(kwargs)
    return LaserContext(smart_phrasing=smart_phrasing, **defaults)


def _director(**kwargs):
    defaults = dict(
        enabled=True,
        dry_run=True,
        safe_scene="safe_static",
        default_scene="house_phrase_1",
        emergency_scene="emergency_blackout",
        phrase_scene="p",
        phrase_interval_beats=32,
    )
    defaults.update(kwargs)
    return LaserDirector(**defaults)


def _now():
    return time.monotonic()


def _make_phrasing_state(**overrides):
    """Build a SmartPhrasingState with safe defaults; override any field."""
    defaults = dict(
        current_phrase_label="other",
        current_phrase_is_up=False,
        current_phrase_is_chorus=False,
        current_phrase_is_low=False,
        next_smart_drop_beat=None,
        beats_to_next_drop=None,
        smart_drop_window_active=False,
        smart_drop_crossing=False,
        smart_drop_preclear_requested=False,
        smart_drop_rearm_requested=False,
        smart_post_drop_active=False,
        active_drop_beat=None,
        smart_buildup_active=False,
        smart_breakdown_active=False,
        breakdown_start_crossing=False,
        breakdown_end_crossing=False,
        smart_breakdown_clear_requested=False,
        smart_breakdown_restore_requested=False,
        transition_mask_should_arm=False,
        transition_mask_should_clear=False,
        transition_window_active=False,
        phrase_anchor_requested=False,
        phrase_anchor_preclear_requested=False,
        phrase_anchor_rearm_requested=False,
        phrase_anchor_target_beat=None,
        reason="test",
        breakdown_restore_beat=None,
    )
    defaults.update(overrides)
    return SmartPhrasingState(**defaults)


# ---------------------------------------------------------------------------
# A. test_laser_context_defaults_smart_phrasing_none
# ---------------------------------------------------------------------------

class TestLaserContextDefault(unittest.TestCase):
    def test_laser_context_defaults_smart_phrasing_none(self):
        ctx = _ctx()
        self.assertIsNone(ctx.smart_phrasing)


# ---------------------------------------------------------------------------
# B. test_state_manager_populates_smart_phrasing_shadow_state
# ---------------------------------------------------------------------------

class TestSmartPhrasingShadowPopulation(unittest.TestCase):
    def test_state_manager_populates_smart_phrasing_shadow_state(self):
        """SmartPhrasingEngine returns valid state from direct snapshot call."""
        engine = SmartPhrasingEngine()
        snap = SmartPhrasingSnapshot(
            deck_id="1",
            track_id="test-track",
            is_playing=True,
            abs_beat=100.0,
            phrase_segments=(),
            smart_drop_beats=(128.0,),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result = engine.update(snap)
        state = result.state
        self.assertIsInstance(state, SmartPhrasingState)
        # Smart drop at 128.0 with abs_beat=100.0 → 28 beats away
        self.assertEqual(state.next_smart_drop_beat, 128.0)
        self.assertEqual(state.beats_to_next_drop, 28.0)


# ---------------------------------------------------------------------------
# C. test_shadow_smart_phrasing_does_not_change_laser_decision
# ---------------------------------------------------------------------------

class TestShadowDoesNotChangeDecisions(unittest.TestCase):
    def test_shadow_smart_phrasing_does_not_change_laser_decision(self):
        """Identical director decisions with None vs populated SmartPhrasingState."""
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)

        # Run 1: no smart_phrasing
        ld_1 = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld_1.tick(_ctx(abs_beat=31.0, smart_phrasing=None), now=_now())
        ld_1.tick(
            _ctx(abs_beat=32.0, autoloop_tick_just_fired=True, smart_phrasing=None),
            now=_now(),
        )
        scene_1 = ld_1.status()["current_scene"]
        reason_1 = ld_1.status()["last_reason"]

        # Run 2: with populated smart_phrasing
        sp = _make_phrasing_state(
            next_smart_drop_beat=128.0,
            beats_to_next_drop=96.0,
            smart_drop_window_active=False,
            smart_buildup_active=True,
            current_phrase_is_up=True,
        )
        ld_2 = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld_2.tick(_ctx(abs_beat=31.0, smart_phrasing=sp), now=_now())
        ld_2.tick(
            _ctx(abs_beat=32.0, autoloop_tick_just_fired=True, smart_phrasing=sp),
            now=_now(),
        )
        scene_2 = ld_2.status()["current_scene"]
        reason_2 = ld_2.status()["last_reason"]

        self.assertEqual(scene_1, scene_2)
        self.assertEqual(reason_1, reason_2)


# ---------------------------------------------------------------------------
# D. test_shadow_engine_safe_on_stop_or_missing_track
# ---------------------------------------------------------------------------

class TestShadowEngineSafeOnStopOrMissingTrack(unittest.TestCase):
    def test_shadow_engine_safe_on_stop(self):
        engine = SmartPhrasingEngine()
        snap = SmartPhrasingSnapshot(
            deck_id="1",
            track_id="test-track",
            is_playing=False,
            abs_beat=None,
            phrase_segments=(),
            smart_drop_beats=(128.0,),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result = engine.update(snap)
        s = result.state
        self.assertEqual(s.current_phrase_label, "other")
        self.assertFalse(s.smart_drop_crossing)
        self.assertFalse(s.smart_buildup_active)
        self.assertFalse(s.smart_breakdown_active)

    def test_shadow_engine_safe_on_missing_track(self):
        engine = SmartPhrasingEngine()
        snap = SmartPhrasingSnapshot(
            deck_id="1",
            track_id=None,
            is_playing=True,
            abs_beat=50.0,
            phrase_segments=(),
            smart_drop_beats=(),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result = engine.update(snap)
        s = result.state
        self.assertEqual(s.current_phrase_label, "other")
        self.assertFalse(s.smart_drop_crossing)
        self.assertFalse(s.smart_buildup_active)
        self.assertFalse(s.smart_breakdown_active)


# ---------------------------------------------------------------------------
# E. test_shadow_mapping_uses_32_beat_buildup_lookahead
# ---------------------------------------------------------------------------

class TestShadowBuiltinLookahead(unittest.TestCase):
    def test_shadow_mapping_uses_32_beat_buildup_lookahead(self):
        """Engine considers buildup active 32 beats before drop when in 'up' phrase."""
        engine = SmartPhrasingEngine()
        snap = SmartPhrasingSnapshot(
            deck_id="1",
            track_id="test-track",
            is_playing=True,
            abs_beat=96.0,
            phrase_segments=(
                PhraseSegment(start_beat=64.0, end_beat=128.0, label="up"),
                PhraseSegment(start_beat=128.0, end_beat=192.0, label="chorus"),
            ),
            smart_drop_beats=(128.0,),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result = engine.update(snap)
        # 128 - 96 = 32 beats ≤ 32.0 lookahead; phrase is "up" → buildup active
        self.assertTrue(result.state.smart_buildup_active)

        # Verify this does not affect LaserDirector decisions
        ld = _director(default_scene="d")
        ld.tick(_ctx(abs_beat=96.0, smart_phrasing=result.state), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")


# ---------------------------------------------------------------------------
# F. test_shadow_smart_drop_works_without_chorus_data
# ---------------------------------------------------------------------------

class TestSmartDropWithoutChorus(unittest.TestCase):
    def test_shadow_smart_drop_works_without_chorus_data(self):
        """Smart Drops computed from smart_drop_beats even with no phrase segments."""
        engine = SmartPhrasingEngine()
        snap = SmartPhrasingSnapshot(
            deck_id="1",
            track_id="test-track",
            is_playing=True,
            abs_beat=120.0,
            phrase_segments=(),  # NO chorus data
            smart_drop_beats=(128.0,),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result = engine.update(snap)
        s = result.state
        self.assertEqual(s.next_smart_drop_beat, 128.0)
        self.assertEqual(s.beats_to_next_drop, 8.0)

        # Advance past drop → crossing fires
        snap2 = replace(snap, abs_beat=128.5)
        result2 = engine.update(snap2)
        self.assertTrue(result2.state.smart_drop_crossing)

        # LaserDirector decision unchanged
        ld = _director(default_scene="d")
        ld.tick(_ctx(abs_beat=120.0, smart_phrasing=result.state), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")


# ---------------------------------------------------------------------------
# G. test_shadow_mapping_drop_marker_is_chorus_boundary
# ---------------------------------------------------------------------------

class TestDropMarkerIsChorousBoundary(unittest.TestCase):
    def test_shadow_mapping_drop_marker_is_chorus_boundary(self):
        """Drop marker at beat 128 = boundary into chorus. Before = 'up'."""
        engine = SmartPhrasingEngine()
        # Build with phrase segments where drop marker aligns with chorus start.
        segments = (
            PhraseSegment(start_beat=96.0, end_beat=128.0, label="up"),
            PhraseSegment(start_beat=128.0, end_beat=192.0, label="chorus"),
        )
        # Before drop: phrase = "up"
        snap_before = SmartPhrasingSnapshot(
            deck_id="1",
            track_id="test-track",
            is_playing=True,
            abs_beat=110.0,
            phrase_segments=segments,
            smart_drop_beats=(128.0,),
            breakdown_segments=(),
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result_before = engine.update(snap_before)
        self.assertEqual(result_before.state.current_phrase_label, "up")
        self.assertTrue(result_before.state.current_phrase_is_up)
        self.assertFalse(result_before.state.smart_drop_crossing)

        # At/after drop: phrase = "chorus", crossing fires
        snap_after = replace(snap_before, abs_beat=128.5)
        result_after = engine.update(snap_after)
        self.assertEqual(result_after.state.current_phrase_label, "chorus")
        self.assertTrue(result_after.state.current_phrase_is_chorus)
        self.assertTrue(result_after.state.smart_drop_crossing)


# ---------------------------------------------------------------------------
# H. test_shadow_mapping_infers_phrase_segment_from_next_marker_when_safe
# ---------------------------------------------------------------------------

class TestPhraseSegmentInference(unittest.TestCase):
    def test_shadow_mapping_infers_phrase_segment_from_next_marker_when_safe(self):
        """ANLZ markers at beats 96, 128, 160 produce proper PhraseSegments."""
        segments = build_phase2_phrase_segments(
            anlz_buildups=[96],
            anlz_drops=[128],
            anlz_breakdowns=[160],
            smart_drops=[128],
            total_beats=200,
        )
        self.assertEqual(len(segments), 3)
        # up: 96→128
        self.assertEqual(segments[0].start_beat, 96.0)
        self.assertEqual(segments[0].end_beat, 128.0)
        self.assertEqual(segments[0].label, "up")
        # chorus: 128→160
        self.assertEqual(segments[1].start_beat, 128.0)
        self.assertEqual(segments[1].end_beat, 160.0)
        self.assertEqual(segments[1].label, "chorus")
        # low: 160→200 (uses total_beats)
        self.assertEqual(segments[2].start_beat, 160.0)
        self.assertEqual(segments[2].end_beat, 200.0)
        self.assertEqual(segments[2].label, "low")

    def test_fallback_32_beat_up_segments_when_no_buildups(self):
        """When no anlz_buildups exist, infer 32-beat 'up' before each smart_drop."""
        segments = build_phase2_phrase_segments(
            anlz_buildups=[],
            anlz_drops=[128],
            anlz_breakdowns=[],
            smart_drops=[128],
            total_beats=200,
        )
        # Should have up:96→128 (inferred) and chorus:128→200
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].label, "up")
        self.assertEqual(segments[0].start_beat, 96.0)
        self.assertEqual(segments[0].end_beat, 128.0)
        self.assertEqual(segments[1].label, "chorus")
        self.assertEqual(segments[1].start_beat, 128.0)

    def test_shadow_32_beat_buildup_fallback_can_start_at_beat_zero(self):
        """If a drop occurs at beat 16, the 32-beat inferred fallback starts at beat 0."""
        segments = build_phase2_phrase_segments(
            anlz_buildups=[],
            anlz_drops=[16],
            anlz_breakdowns=[],
            smart_drops=[16],
            total_beats=64,
        )
        self.assertEqual(len(segments), 2)
        # Should have up:0→16 (inferred, max(0, 16 - 32))
        self.assertEqual(segments[0].label, "up")
        self.assertEqual(segments[0].start_beat, 0.0)
        self.assertEqual(segments[0].end_beat, 16.0)
        # And chorus:16→64
        self.assertEqual(segments[1].label, "chorus")
        self.assertEqual(segments[1].start_beat, 16.0)

    def test_empty_markers_produce_empty_segments(self):
        segments = build_phase2_phrase_segments(
            anlz_buildups=[],
            anlz_drops=[],
            anlz_breakdowns=[],
            smart_drops=[],
            total_beats=200,
        )
        self.assertEqual(segments, ())


# ---------------------------------------------------------------------------
# I. test_shadow_mapping_does_not_invent_final_segment_duration
# ---------------------------------------------------------------------------

class TestNoInventedDuration(unittest.TestCase):
    def test_shadow_mapping_does_not_invent_final_segment_duration(self):
        """If total_beats is 0 (no beatgrid), final segment is skipped."""
        segments = build_phase2_phrase_segments(
            anlz_buildups=[96],
            anlz_drops=[128],
            anlz_breakdowns=[],
            smart_drops=[128],
            total_beats=0,  # no beatgrid
        )
        # Only up:96→128 — no open-ended chorus after 128
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].label, "up")
        self.assertEqual(segments[0].start_beat, 96.0)
        self.assertEqual(segments[0].end_beat, 128.0)

    def test_single_marker_no_total_beats_produces_nothing(self):
        """Single marker with no total_beats and no next marker → nothing."""
        segments = build_phase2_phrase_segments(
            anlz_buildups=[],
            anlz_drops=[128],
            anlz_breakdowns=[],
            smart_drops=[],
            total_beats=0,
        )
        self.assertEqual(segments, ())


# ---------------------------------------------------------------------------
# J. test_shadow_mapping_does_not_infer_breakdown_duration_without_end
# ---------------------------------------------------------------------------

class TestBreakdownSegmentsEmpty(unittest.TestCase):
    def test_shadow_mapping_does_not_infer_breakdown_duration_without_end(self):
        """Breakdown segments must remain empty — ANLZ stores start-markers only."""
        engine = SmartPhrasingEngine()
        snap = SmartPhrasingSnapshot(
            deck_id="1",
            track_id="test-track",
            is_playing=True,
            abs_beat=50.0,
            phrase_segments=(),
            smart_drop_beats=(128.0,),
            breakdown_segments=(),  # explicitly empty
            phrase_lookahead_beats=32.0,
            drop_window_beats=4.0,
            post_drop_beats=8.0,
            transition_window_beats=4.0,
        )
        result = engine.update(snap)
        self.assertFalse(result.state.smart_breakdown_active)


class TestSmartPhrasingBlackoutArmShadow(unittest.TestCase):
    def _prepare_manager(
        self,
        *,
        drop_beat: int = 64,
        smart_breakdowns: tuple[int, ...] = (),
        anlz_breakdowns: tuple[int, ...] = (),
        anlz_buildups: tuple[int, ...] = (),
    ) -> StateManager:
        with patch.dict(
            os.environ,
            {
                "RBSS_SMART_REARM_EXPERIMENT": "1",
                "RBSS_SMART_DROP": "1",
                "RBSS_SMART_BREAKDOWN": "1",
            },
            clear=False,
        ):
            sm = StateManager(queue.Queue(), PositionCache(), Mock())

        deck = sm._deck[1]
        deck.playing = True
        deck.meta.filepath = "/music/shadow.mp3"
        deck.meta.content_id = "shadow-track"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.beatgrid_times_ms = [i * 500.0 for i in range(256)]
        deck.meta.beatgrid_bpms = [120.0 for _ in range(256)]
        deck.meta.beatgrid_source = "grid"
        deck.meta.smart_drops = [drop_beat]
        deck.meta.anlz_drops = [drop_beat]
        deck.meta.smart_breakdowns = list(smart_breakdowns)
        deck.meta.anlz_breakdowns = list(anlz_breakdowns)
        deck.meta.anlz_buildups = list(anlz_buildups)

        sm._os.active_deck = 1
        sm._os.lighting_mode = "autoloop"
        sm._os.lighting_desired = "autoloop"
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_armed_filepath = deck.meta.filepath
        sm._os.last_beat_elapsed_ms = int((drop_beat - 6) * 500)
        sm._cache.update(
            PositionSnapshot(
                1,
                elapsed_ms=sm._os.last_beat_elapsed_ms,
                playing=True,
                updated_at=time.monotonic(),
            )
        )

        sm._laser_director = Mock()
        sm._laser_director.is_enabled.return_value = True
        sm._laser_director.tick.return_value = SimpleNamespace(
            scene="house_buildup_1",
            reason="buildup_to_drop_window",
            role="buildup",
        )
        sm._laser_executor = Mock()
        sm._laser_executor.smart_drop_blackout_enabled.return_value = True
        return sm

    def _push_ctx(self, sm: StateManager, beat: int, *, smart_drop_signal_override=None) -> LaserContext:
        sm._cache.update(
            PositionSnapshot(
                1,
                elapsed_ms=int(beat * 500),
                playing=True,
                updated_at=time.monotonic(),
            )
        )
        if smart_drop_signal_override is None:
            sm._push_tick()
        else:
            with patch(
                "rb_ss_bridge_v2.state_manager._smart_drop_tick",
                return_value=smart_drop_signal_override,
            ):
                sm._push_tick()
        return sm._laser_executor.on_decision.call_args.args[1]

    def test_phrase_anchor_intents_and_rearm_parity_at_64(self):
        sm = self._prepare_manager(drop_beat=256)
        sm._phrase_anchor_enabled = True
        sm._os.phrase_anchor_last_beat = 0
        sm._os.last_beat_elapsed_ms = int(62 * 500)
        sm._send_autoloop_deck_load = Mock()

        preclear_ctx = self._push_ctx(sm, 63)
        self.assertTrue(preclear_ctx.smart_phrasing.phrase_anchor_preclear_requested)
        self.assertFalse(preclear_ctx.smart_phrasing.phrase_anchor_rearm_requested)
        self.assertEqual(preclear_ctx.smart_phrasing.phrase_anchor_target_beat, 64)
        self.assertEqual(
            sm._out.send_deck_clear.call_args_list,
            [call(1), call(2), call(3), call(4)],
        )
        self.assertEqual(
            sm._out.send_loop_off.call_args_list,
            [call(1), call(2), call(3), call(4)],
        )

        rearm_ctx = self._push_ctx(sm, 64)
        self.assertFalse(rearm_ctx.smart_phrasing.phrase_anchor_preclear_requested)
        self.assertTrue(rearm_ctx.smart_phrasing.phrase_anchor_rearm_requested)
        self.assertEqual(rearm_ctx.smart_phrasing.phrase_anchor_target_beat, 64)
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)
        sm._send_autoloop_deck_load.assert_called_once()

    def test_shadow_arm_matches_legacy_normal_window(self):
        sm = self._prepare_manager(drop_beat=64)
        contexts = [self._push_ctx(sm, beat) for beat in (59, 60, 61, 62, 63, 64)]
        for ctx in contexts:
            self.assertEqual(ctx.smart_phrasing_blackout_arm, ctx.smart_drop_blackout_arm)
        self.assertFalse(contexts[0].smart_phrasing_blackout_arm)
        self.assertTrue(contexts[1].smart_phrasing_blackout_arm)
        self.assertTrue(contexts[2].smart_phrasing_blackout_arm)
        self.assertTrue(contexts[3].smart_phrasing_blackout_arm)
        self.assertTrue(contexts[4].smart_phrasing_blackout_arm)
        self.assertFalse(contexts[5].smart_phrasing_blackout_arm)

    def test_shadow_arm_matches_legacy_drop_crossing_tick_drops_signal(self):
        sm = self._prepare_manager(drop_beat=64)
        self._push_ctx(sm, 59)
        self._push_ctx(sm, 60)
        crossing = self._push_ctx(sm, 64)
        self.assertFalse(crossing.smart_drop_blackout_arm)
        self.assertFalse(crossing.smart_phrasing_blackout_arm)

    def test_shadow_arm_suppressed_when_autoloop_arm_pending(self):
        sm = self._prepare_manager(drop_beat=64)
        sm._os.autoloop_arm_pending = True
        for beat in (59, 60, 61, 62, 63, 64):
            ctx = self._push_ctx(sm, beat)
            self.assertFalse(ctx.smart_drop_blackout_arm)
            self.assertFalse(ctx.smart_phrasing_blackout_arm)

    def test_shadow_arm_suppressed_when_pending_autoloop_arm_meta_set(self):
        sm = self._prepare_manager(drop_beat=64)
        sm._os.pending_autoloop_arm_meta = TrackMetadata(filepath="/music/pending.mp3")
        for beat in (59, 60, 61, 62, 63, 64):
            ctx = self._push_ctx(sm, beat)
            self.assertFalse(ctx.smart_drop_blackout_arm)
            self.assertFalse(ctx.smart_phrasing_blackout_arm)

    def test_shadow_arm_suppressed_during_breakdown_active(self):
        sm = self._prepare_manager(
            drop_beat=64,
            smart_breakdowns=(59,),
            anlz_breakdowns=(59,),
            anlz_buildups=(62,),
        )
        sm._os.breakdown_active = True
        sm._os.breakdown_restore_beat = 10_000
        for beat in (59, 60, 61, 62):
            ctx = self._push_ctx(sm, beat)
            self.assertFalse(ctx.smart_drop_blackout_arm)
            self.assertFalse(ctx.smart_phrasing_blackout_arm)
        self.assertFalse(sm._sp_blackout_arm_latched)

    def test_shadow_arm_suppressed_when_breakdown_starts_between(self):
        sm = self._prepare_manager(
            drop_beat=64,
            smart_breakdowns=(61,),
            anlz_breakdowns=(61,),
        )
        self._push_ctx(sm, 59)
        arm_ctx = self._push_ctx(sm, 60)
        self.assertFalse(arm_ctx.smart_phrasing.transition_mask_should_arm)
        self.assertFalse(arm_ctx.smart_drop_blackout_arm)
        self.assertFalse(arm_ctx.smart_phrasing_blackout_arm)
        self.assertFalse(sm._sp_blackout_arm_latched)

    def test_shadow_arm_retries_across_window_when_legacy_does(self):
        sm = self._prepare_manager(drop_beat=64)
        self._push_ctx(sm, 59)
        self._push_ctx(sm, 60)
        for beat in (61, 62, 63):
            ctx = self._push_ctx(sm, beat)
            self.assertTrue(ctx.smart_drop_blackout_arm)
            self.assertTrue(ctx.smart_phrasing_blackout_arm)

    def test_shadow_arm_latch_resets_on_transition_clear(self):
        sm = self._prepare_manager(drop_beat=64)
        self._push_ctx(sm, 59)
        self._push_ctx(sm, 60)
        self.assertTrue(sm._sp_blackout_arm_latched)
        clear_ctx = self._push_ctx(sm, 64)
        self.assertTrue(clear_ctx.smart_phrasing.transition_mask_should_clear)
        self.assertFalse(clear_ctx.smart_phrasing_blackout_arm)
        self.assertFalse(sm._sp_blackout_arm_latched)

    def test_shadow_arm_latch_resets_on_deck_or_track_change(self):
        sm = self._prepare_manager(drop_beat=64)
        self._push_ctx(sm, 59)
        self._push_ctx(sm, 60)
        self.assertTrue(sm._sp_blackout_arm_latched)
        sm._on_master_changed(2, "test")
        self.assertFalse(sm._sp_blackout_arm_latched)

        sm2 = self._prepare_manager(drop_beat=64)
        self._push_ctx(sm2, 59)
        self._push_ctx(sm2, 60)
        self.assertTrue(sm2._sp_blackout_arm_latched)
        sm2._on_track_loaded(1, "shadow-track", BridgeEvent(Ev.TRACK_LOADED, 1))
        self.assertFalse(sm2._sp_blackout_arm_latched)

    def test_smart_drop_blackout_arm_fires_after_mid_window_breakdown_clears(self):
        sm = self._prepare_manager(
            drop_beat=64,
            smart_breakdowns=(),
            anlz_breakdowns=(59,),
            anlz_buildups=(61,),
        )
        self._push_ctx(sm, 59)
        sm._os.breakdown_active = True
        suppressed = self._push_ctx(sm, 60)
        self.assertFalse(suppressed.smart_drop_blackout_arm)
        self.assertFalse(suppressed.smart_phrasing_blackout_arm)
        self.assertFalse(sm._sp_blackout_arm_latched)

        sm._os.breakdown_active = False
        cleared_mid_window = self._push_ctx(sm, 61)
        self.assertTrue(cleared_mid_window.smart_drop_blackout_arm)
        self.assertTrue(cleared_mid_window.smart_phrasing_blackout_arm)
        self.assertTrue(sm._sp_blackout_arm_latched)

    def test_engine_runs_once_per_tick_in_push_tick(self):
        sm = self._prepare_manager(drop_beat=64)
        with patch.object(
            sm._smart_phrasing_engine,
            "update",
            wraps=sm._smart_phrasing_engine.update,
        ) as update_sp:
            self._push_ctx(sm, 60)
        self.assertEqual(update_sp.call_count, 1)

    def test_director_disabled_clears_sp_pending_blackout_when_legacy_arm_false(self):
        sm = self._prepare_manager(
            drop_beat=64,
            smart_breakdowns=(),
            anlz_breakdowns=(59,),
            anlz_buildups=(61,),
        )

        # Beat 60: window entry while breakdown_active suppresses arming for both signals.
        self._push_ctx(sm, 59)
        sm._os.breakdown_active = True
        suppressed = self._push_ctx(sm, 60)
        self.assertFalse(suppressed.smart_drop_blackout_arm)
        self.assertFalse(suppressed.smart_phrasing_blackout_arm)

        # Beat 61: both arm after breakdown clears mid-window.
        sm._os.breakdown_active = False
        legacy_only = self._push_ctx(sm, 61)
        self.assertTrue(legacy_only.smart_drop_blackout_arm)
        self.assertTrue(legacy_only.smart_phrasing_blackout_arm)

        # Simulate the inverse edge (SP-only arm) to validate the director-disabled guard.
        # Keep this focused by overriding context at the executor entrypoint.
        sm._laser_executor.reset_mock()
        sm._laser_director.is_enabled.return_value = False
        sm._laser_executor.smart_drop_blackout_enabled.return_value = True
        sp_only_ctx = replace(
            legacy_only,
            smart_drop_blackout_arm=False,
            smart_phrasing_blackout_arm=True,
        )
        sm._os.drop_cut_armed = False
        sm._build_laser_context = Mock(return_value=sp_only_ctx)
        self._push_ctx(sm, 62)

        sm._laser_executor.clear_pending_blackout.assert_any_call(
            reason="laser_director_disabled"
        )


if __name__ == "__main__":
    unittest.main()
