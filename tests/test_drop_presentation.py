"""tests/test_drop_presentation.py

Implements docs/architecture/drop_presentation_authority.md's Required Behavior
Tests 1-9 verbatim (one test class per numbered test, named to match), plus the
additional coverage docs/plans/active/drop_presentation_impl_spec.md Task 6 asks
for beyond the numbered list.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.drop_presentation import (  # noqa: E402
    LEDS_ONLY,
    LEDS_PLUS_LASERS,
    LASERS_ONLY,
    DropDecision,
    DropPresentationConfig,
    LearnedStore,
    SessionState,
    WindowActions,
    WindowInputs,
    WindowMachine,
    gearshift_qualifies,
    load_drop_presentation_config,
    plan_track,
    resolve_presentation,
    runway_beats,
)
from rb_ss_bridge_v2.runtime_status import atomic_write_json  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import PhraseSegment  # noqa: E402


def _seg(start: float, end: float, label: str) -> PhraseSegment:
    return PhraseSegment(start_beat=float(start), end_beat=float(end), label=label)

def _cfg(**overrides) -> DropPresentationConfig:
    defaults = dict(
        enabled=True, laser_ratio=0.4, opening_tracks=3, led_predark_beats=4,
        drop_window_cap_beats=192, hotcue_marker="LASER", solo_learn_threshold=1,
        gearshift_bpm_jump=10.0, record_min_drops=5, ws_handoff_enabled=False,
    )
    defaults.update(overrides)
    return DropPresentationConfig(**defaults)


def _impact(abs_beat: float, *, laser_visible: bool = True, **overrides) -> WindowInputs:
    defaults = dict(
        abs_beat=abs_beat, beats_to_next_drop=0.0, next_drop_beat=abs_beat,
        drop_role="drop", impact_now=True, laser_visible=laser_visible,
    )
    defaults.update(overrides)
    return WindowInputs(**defaults)


# ---- Required Behavior Test 1: personality -----------------------------


class RequiredTest1Personality(unittest.TestCase):
    def test_single_drop_track_is_finale_and_gets_lasers(self) -> None:
        plan = plan_track([64.0], [], [], [], _cfg())
        decision = plan.decision_for(64.0)
        self.assertTrue(decision.is_finale)
        self.assertEqual(decision.personality_presentation, LEDS_PLUS_LASERS)

    def test_two_drop_track_only_last_gets_personality_lasers(self) -> None:
        plan = plan_track([32.0, 96.0], [], [], [], _cfg())
        self.assertEqual(plan.decision_for(32.0).personality_presentation, LEDS_ONLY)
        last = plan.decision_for(96.0)
        self.assertEqual(last.personality_presentation, LEDS_PLUS_LASERS)
        self.assertTrue(last.is_finale)

    def test_four_drop_track_ranks_last_first_then_longest_runway(self) -> None:
        segs = [
            _seg(16, 32, "up"),     # runway for drop@32 -> 16
            _seg(64, 96, "low"),    # runway for drop@96 -> 32 (longest of the non-last)
            _seg(144, 160, "up"),   # runway for drop@160 -> 16
        ]
        plan = plan_track([32.0, 96.0, 160.0, 224.0], segs, [], [], _cfg())
        # ceil(0.4*4) = 2 -> last (224) + longest-runway non-last (96).
        self.assertEqual(plan.decision_for(224.0).personality_presentation, LEDS_PLUS_LASERS)
        self.assertEqual(plan.decision_for(96.0).personality_presentation, LEDS_PLUS_LASERS)
        self.assertEqual(plan.decision_for(32.0).personality_presentation, LEDS_ONLY)
        self.assertEqual(plan.decision_for(160.0).personality_presentation, LEDS_ONLY)

    def test_finale_guarantee_applies_outside_damper_even_at_zero_ratio(self) -> None:
        # Required Behavior Test 1: OUTSIDE the opening damper, the last true
        # drop always renders at least leds_plus_lasers. (Under the damper it
        # renders leds_only like every other non-exempt drop -- rung 7 precedes
        # rung 8, first match wins; see RequiredTest6Damper.)
        plan = plan_track([32.0, 96.0], [], [], [], _cfg(laser_ratio=0.0))
        last = plan.decision_for(96.0)
        self.assertEqual(last.personality_presentation, LEDS_ONLY)  # ranking alone picks no one
        presentation, reason, _ = resolve_presentation(
            last, armed=False, gearshift_pending=False, record_breaking=False,
            auto_solo_used=False, damper_active=False,
        )
        self.assertEqual((presentation, reason), (LEDS_PLUS_LASERS, "both_finale"))

    def test_identical_plan_across_repeated_plays(self) -> None:
        segs = [_seg(0, 16, "up"), _seg(48, 96, "low")]
        args = ([32.0, 96.0], segs, [95.5], [30.0], _cfg())
        self.assertEqual(plan_track(*args).decisions, plan_track(*args).decisions)


# ---- Required Behavior Test 2: ladder precedence -----------------------


class RequiredTest2LadderPrecedence(unittest.TestCase):
    def test_tagged_learned_and_record_breaking_fires_exactly_one_highest_tier(self) -> None:
        decision = DropDecision(
            beat=64.0, tagged=True, learned=True, is_finale=False,
            personality_presentation=LEDS_ONLY, runway=40.0,
        )
        presentation, reason, auto_solo_fired = resolve_presentation(
            decision, armed=False, gearshift_pending=True, record_breaking=True,
            auto_solo_used=False, damper_active=False,
        )
        self.assertEqual((presentation, reason), (LASERS_ONLY, "solo_hotcue"))
        self.assertFalse(auto_solo_fired)  # hotcue is not one of the capped auto-solo tiers

    def test_manual_arm_outranks_every_other_tier(self) -> None:
        decision = DropDecision(
            beat=1.0, tagged=True, learned=True, is_finale=True,
            personality_presentation=LEDS_PLUS_LASERS, runway=99.0,
        )
        presentation, reason, fired = resolve_presentation(
            decision, armed=True, gearshift_pending=True, record_breaking=True,
            auto_solo_used=True, damper_active=True,
        )
        self.assertEqual((presentation, reason, fired), (LASERS_ONLY, "solo_manual", False))

    def test_veto_suppresses_tiers_1_6_but_never_finale(self) -> None:
        tagged = DropDecision(beat=1.0, tagged=True, learned=False, is_finale=False,
                               personality_presentation=LEDS_ONLY, runway=0.0)
        presentation, reason, fired = resolve_presentation(
            tagged, armed=False, gearshift_pending=False, record_breaking=False,
            auto_solo_used=False, damper_active=False, vetoed=True,
        )
        self.assertEqual((presentation, reason, fired), (LEDS_ONLY, "leds_only_personality", False))

        finale = DropDecision(beat=1.0, tagged=True, learned=True, is_finale=True,
                               personality_presentation=LEDS_ONLY, runway=0.0)
        presentation, reason, _ = resolve_presentation(
            finale, armed=True, gearshift_pending=True, record_breaking=True,
            auto_solo_used=False, damper_active=False, vetoed=True,
        )
        self.assertEqual((presentation, reason), (LEDS_PLUS_LASERS, "both_finale"))

    def test_learned_outranks_gearshift_and_record(self) -> None:
        decision = DropDecision(
            beat=1.0, tagged=False, learned=True, is_finale=False,
            personality_presentation=LEDS_ONLY, runway=1.0,
        )
        presentation, reason, fired = resolve_presentation(
            decision, armed=False, gearshift_pending=True, record_breaking=True,
            auto_solo_used=False, damper_active=False,
        )
        self.assertEqual((presentation, reason, fired), (LASERS_ONLY, "solo_learned", True))


# ---- Required Behavior Test 3: learned lifecycle -----------------------


class RequiredTest3LearnedLifecycle(unittest.TestCase):
    def test_fire_learn_replay_veto_unlearn(self) -> None:
        store = LearnedStore()
        content_id = "track-1"

        # FIRE: an armed solo actually fired on this drop -> learn it.
        self.assertTrue(store.record(content_id, 64.0))
        self.assertEqual(store.beats_for_track(content_id), (64.0,))

        # NEXT PLAY: a shifted re-analysis beat (1.4 beats away) still matches
        # within tolerance and marks the drop `learned`.
        learned_keys = store.beats_for_track(content_id)
        plan = plan_track([65.4], [], [], learned_keys, _cfg())
        decision = plan.decision_for(65.4)
        self.assertTrue(decision.learned)
        presentation, reason, auto_solo_fired = resolve_presentation(
            decision, armed=False, gearshift_pending=False, record_breaking=False,
            auto_solo_used=False, damper_active=False,
        )
        self.assertEqual((presentation, reason), (LASERS_ONLY, "solo_learned"))
        self.assertTrue(auto_solo_fired)

        # VETO: pressing the pad on a pending learned solo cancels AND un-learns.
        self.assertTrue(store.remove(content_id, 65.4))
        self.assertEqual(store.beats_for_track(content_id), ())

    def test_arm_without_fire_teaches_nothing(self) -> None:
        store = LearnedStore()
        # There is no separate "arm" call on LearnedStore at all -- only
        # .record() (fire) mutates it. A never-fired arm leaves it untouched.
        self.assertEqual(store.beats_for_track("track-1"), ())

    def test_firing_on_an_already_learned_drop_records_nothing_new(self) -> None:
        store = LearnedStore()
        store.record("track-1", 64.0)
        self.assertFalse(store.record("track-1", 64.3))
        self.assertEqual(store.beats_for_track("track-1"), (64.0,))

    def test_corrupt_store_is_empty_with_one_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "corrupt.json"
            path.write_text("{not valid json", encoding="utf-8")
            with self.assertLogs("drop_presentation", level="WARNING") as logs:
                store = LearnedStore.load(path)
        self.assertEqual(store.to_dict(), {})
        self.assertEqual(len(logs.records), 1)

    def test_missing_store_file_is_empty_without_a_spurious_warning(self) -> None:
        # A brand-new install has no learned store yet -- this is normal, not
        # an anomaly, and must not warn every single launch.
        with tempfile.TemporaryDirectory() as td:
            store = LearnedStore.load(Path(td) / "never-written.json")
        self.assertEqual(store.to_dict(), {})

    def test_index_style_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "indexstyle.json"
            path.write_text(json.dumps({"track-1": True, "0": True}), encoding="utf-8")
            store = LearnedStore.load(path)
        self.assertEqual(store.to_dict(), {})

    def test_round_trip_via_atomic_write_json(self) -> None:
        store = LearnedStore()
        store.record("track-1", 64.0)
        store.record("track-2", 128.0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "learned.json"
            atomic_write_json(str(path), store.to_dict())
            reloaded = LearnedStore.load(path)
        self.assertEqual(reloaded.beats_for_track("track-1"), (64.0,))
        self.assertEqual(reloaded.beats_for_track("track-2"), (128.0,))


# ---- Required Behavior Test 4: gear-shift -------------------------------


class RequiredTest4Gearshift(unittest.TestCase):
    def test_fires_at_exactly_plus_10(self) -> None:
        self.assertTrue(gearshift_qualifies(120.0, 130.0, 10.0))

    def test_does_not_fire_at_plus_9(self) -> None:
        self.assertFalse(gearshift_qualifies(120.0, 129.0, 10.0))

    def test_does_not_fire_across_two_mixes_of_plus_5(self) -> None:
        self.assertFalse(gearshift_qualifies(120.0, 125.0, 10.0))
        # A second, separate handover compares THIS mix's outgoing (125, the
        # previous incoming) against its own incoming -- deltas never accrue.
        self.assertFalse(gearshift_qualifies(125.0, 130.0, 10.0))

    def test_never_fires_on_sessions_first_master(self) -> None:
        self.assertFalse(gearshift_qualifies(None, 130.0, 10.0))

    def test_pitched_deck_live_bpm_decides_not_tag_bpm(self) -> None:
        # A meta-only comparison (128 tag vs 126 tag) would see -2 and miss it;
        # the incoming deck is pitched to a live 138.6, which correctly fires.
        self.assertFalse(gearshift_qualifies(128.0, 126.0, 10.0))
        self.assertTrue(gearshift_qualifies(128.0, 138.6, 10.0))

    def test_session_state_consumes_the_pending_flag_once(self) -> None:
        session = SessionState()
        session.set_gearshift_pending((1, 5))
        self.assertTrue(session.consume_gearshift_pending((1, 5)))
        self.assertFalse(session.consume_gearshift_pending((1, 5)))
        self.assertFalse(session.consume_gearshift_pending((2, 9)))

    def test_session_state_pending_peek_does_not_mutate(self) -> None:
        session = SessionState()
        session.set_gearshift_pending((1, 5))
        self.assertTrue(session.gearshift_pending_for((1, 5)))
        self.assertTrue(session.gearshift_pending_for((1, 5)))  # peeking twice is safe
        self.assertTrue(session.consume_gearshift_pending((1, 5)))
        self.assertFalse(session.gearshift_pending_for((1, 5)))


class SessionStateVetoTests(unittest.TestCase):
    def test_veto_beat_is_scoped_to_its_track_key(self) -> None:
        session = SessionState()
        session.veto_beat((1, 5), 64.0)
        self.assertTrue(session.is_vetoed((1, 5), 64.0))
        self.assertFalse(session.is_vetoed((1, 5), 96.0))
        self.assertFalse(session.is_vetoed((1, 6), 64.0))  # a new load_gen is a fresh track


# ---- Required Behavior Test 5: record-breaker ---------------------------


class RequiredTest5RecordBreaker(unittest.TestCase):
    def test_strict_greater_semantics(self) -> None:
        session = SessionState()
        for _ in range(5):
            session.finalize_drop_observation(10.0, has_phrase_data=True)
        self.assertFalse(session.is_record_breaking(10.0, record_min_drops=5))
        self.assertTrue(session.is_record_breaking(10.1, record_min_drops=5))

    def test_min_observation_gate(self) -> None:
        session = SessionState()
        for _ in range(4):
            session.finalize_drop_observation(5.0, has_phrase_data=True)
        self.assertFalse(session.is_record_breaking(100.0, record_min_drops=5))
        session.finalize_drop_observation(5.0, has_phrase_data=True)
        self.assertTrue(session.is_record_breaking(100.0, record_min_drops=5))

    def test_groove_resets_runway_contiguity(self) -> None:
        segs = [_seg(0, 16, "up"), _seg(16, 32, "other"), _seg(32, 64, "up")]
        self.assertEqual(runway_beats(64.0, segs), 32.0)

    def test_records_tracked_under_damper_without_firing(self) -> None:
        decision = DropDecision(
            beat=1.0, tagged=False, learned=False, is_finale=False,
            personality_presentation=LEDS_ONLY, runway=50.0,
        )
        presentation, reason, fired = resolve_presentation(
            decision, armed=False, gearshift_pending=False, record_breaking=True,
            auto_solo_used=False, damper_active=True,
        )
        self.assertEqual((presentation, reason, fired), (LEDS_ONLY, "leds_only_damper", False))

        session = SessionState()
        for _ in range(5):
            session.finalize_drop_observation(1.0, has_phrase_data=True)
        session.finalize_drop_observation(50.0, has_phrase_data=True)  # unconditional bookkeeping
        self.assertEqual(session.runway_record, 50.0)

    def test_tracks_without_phrase_data_are_invisible(self) -> None:
        session = SessionState()
        for _ in range(10):
            session.finalize_drop_observation(999.0, has_phrase_data=False)
        self.assertEqual(session.observed_drop_count, 0)
        self.assertEqual(session.runway_record, 0.0)
        # The 10 phrase-data-less "drops" never advanced observed_drop_count,
        # so the min-observation gate (record_min_drops=5) is still unmet.
        self.assertFalse(session.is_record_breaking(0.5, record_min_drops=5))


# ---- Required Behavior Test 6: damper -----------------------------------


class RequiredTest6Damper(unittest.TestCase):
    def test_blocks_tiers_5_and_6_and_personality_lasers(self) -> None:
        decision = DropDecision(
            beat=1.0, tagged=False, learned=False, is_finale=False,
            personality_presentation=LEDS_PLUS_LASERS, runway=1.0,
        )
        presentation, reason, _ = resolve_presentation(
            decision, armed=False, gearshift_pending=True, record_breaking=True,
            auto_solo_used=False, damper_active=True,
        )
        self.assertEqual((presentation, reason), (LEDS_ONLY, "leds_only_damper"))

    def test_damper_blocks_even_the_finale_guarantee(self) -> None:
        # Rung 7 precedes rung 8, first match wins: during the damper a
        # non-exempt track's LAST true drop renders leds_only like every other
        # non-exempt drop -- the damper's exemption list (manual, hot-cue,
        # learned) deliberately excludes the finale ("save the night's first
        # laser moment"). Operator-approved ruling 2026-07-04.
        finale = DropDecision(
            beat=96.0, tagged=False, learned=False, is_finale=True,
            personality_presentation=LEDS_PLUS_LASERS, runway=8.0,
        )
        presentation, reason, fired = resolve_presentation(
            finale, armed=False, gearshift_pending=False, record_breaking=False,
            auto_solo_used=False, damper_active=True,
        )
        self.assertEqual((presentation, reason, fired), (LEDS_ONLY, "leds_only_damper", False))
        # Outside the damper the same decision gets its guarantee back.
        presentation, reason, _ = resolve_presentation(
            finale, armed=False, gearshift_pending=False, record_breaking=False,
            auto_solo_used=False, damper_active=False,
        )
        self.assertEqual((presentation, reason), (LEDS_PLUS_LASERS, "both_finale"))

    def test_manual_hotcue_and_learned_fire_anyway(self) -> None:
        tagged = DropDecision(beat=1.0, tagged=True, learned=False, is_finale=False,
                               personality_presentation=LEDS_ONLY, runway=0.0)
        self.assertEqual(
            resolve_presentation(tagged, armed=False, gearshift_pending=False,
                                  record_breaking=False, auto_solo_used=False,
                                  damper_active=True)[:2],
            (LASERS_ONLY, "solo_hotcue"),
        )
        learned = DropDecision(beat=1.0, tagged=False, learned=True, is_finale=False,
                                personality_presentation=LEDS_ONLY, runway=0.0)
        self.assertEqual(
            resolve_presentation(learned, armed=False, gearshift_pending=False,
                                  record_breaking=False, auto_solo_used=False,
                                  damper_active=True)[:2],
            (LASERS_ONLY, "solo_learned"),
        )
        self.assertEqual(
            resolve_presentation(learned, armed=True, gearshift_pending=False,
                                  record_breaking=False, auto_solo_used=False,
                                  damper_active=True)[:2],
            (LASERS_ONLY, "solo_manual"),
        )

    def test_track_counting_threshold_obeyed(self) -> None:
        session = SessionState()
        for i in range(3):
            self.assertTrue(session.mark_track_counted(1, i))
            self.assertFalse(session.mark_track_counted(1, i))  # idempotent per (deck, load_gen)
            if i < 2:
                self.assertTrue(session.damper_active(3))
        self.assertFalse(session.damper_active(3))

    def test_loaded_but_never_audible_counts_nothing(self) -> None:
        session = SessionState()
        self.assertEqual(session.opening_tracks_counted, 0)
        self.assertTrue(session.damper_active(3))


# ---- Required Behavior Test 7: darkness guard ---------------------------


class RequiredTest7DarknessGuard(unittest.TestCase):
    def test_guard_failure_falls_back_to_both_no_pre_dark(self) -> None:
        machine = WindowMachine(_cfg(led_predark_beats=4))
        inputs = WindowInputs(
            abs_beat=98.0, beats_to_next_drop=2.0, next_drop_beat=100.0,
            drop_role="none", impact_now=False, laser_visible=False,
        )
        actions = machine.tick(inputs, pending_presentation=LASERS_ONLY, pending_reason="solo_manual")
        self.assertFalse(actions.led_dark_hold)
        self.assertIsNone(actions.presentation)

    def test_guard_rechecked_at_impact_downgrades_to_both(self) -> None:
        machine = WindowMachine(_cfg())
        pre_dark = WindowInputs(
            abs_beat=98.0, beats_to_next_drop=2.0, next_drop_beat=100.0,
            drop_role="none", impact_now=False, laser_visible=True,
        )
        actions = machine.tick(pre_dark, pending_presentation=LASERS_ONLY, pending_reason="solo_manual")
        self.assertTrue(actions.led_dark_hold)

        impact = _impact(100.0, laser_visible=False)
        actions = machine.tick(impact, pending_presentation=LASERS_ONLY, pending_reason="solo_manual")
        self.assertEqual((actions.presentation, actions.reason), (LEDS_PLUS_LASERS, "guard_fallback_both"))
        self.assertFalse(actions.led_dark_hold)


# ---- Required Behavior Test 8: fail-open --------------------------------


class RequiredTest8FailOpen(unittest.TestCase):
    def _enter_window(self, machine: WindowMachine, *, abs_beat: float = 100.0) -> None:
        machine.tick(_impact(abs_beat), pending_presentation=LASERS_ONLY, pending_reason="solo_manual")

    def test_window_end_by_role_change(self) -> None:
        machine = WindowMachine(_cfg())
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=105.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="none", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertEqual(actions, WindowActions(led_dark_hold=False, base_suppressed=False, presentation=None, reason=""))

    def test_window_end_by_beat_cap(self) -> None:
        machine = WindowMachine(_cfg(drop_window_cap_beats=8))
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=108.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(actions.led_dark_hold)

    def test_track_change(self) -> None:
        machine = WindowMachine(_cfg())
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=True, track_changed=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(actions.led_dark_hold)

    def test_active_deck_change(self) -> None:
        machine = WindowMachine(_cfg())
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=True, active_deck_changed=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(actions.led_dark_hold)

    def test_stop(self) -> None:
        machine = WindowMachine(_cfg())
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=True, stopped=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(actions.led_dark_hold)

    def test_manual_interaction(self) -> None:
        machine = WindowMachine(_cfg())
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=True, manual_interaction=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(actions.led_dark_hold)

    def test_laser_output_loss_mid_window(self) -> None:
        machine = WindowMachine(_cfg())
        self._enter_window(machine)
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=False),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(actions.led_dark_hold)

    def test_leds_only_window_survives_laser_visibility_flapping(self) -> None:
        # laser_visible only matters for a LASERS_ONLY window; a leds_only
        # window must not be disturbed by it.
        machine = WindowMachine(_cfg())
        machine.tick(_impact(100.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=False),
            pending_presentation=None, pending_reason="",
        )
        self.assertTrue(actions.base_suppressed)
        self.assertEqual(actions.presentation, LEDS_ONLY)

    def test_laser_drop_fires_inside_leds_only_shadow(self) -> None:
        cfg = _cfg()
        machine = WindowMachine(cfg)
        machine.tick(_impact(0.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=64.0, beats_to_next_drop=0.0, next_drop_beat=64.0,
                         drop_role="post_drop", impact_now=True, laser_visible=True),
            pending_presentation=LEDS_PLUS_LASERS, pending_reason="both_personality",
        )
        self.assertFalse(actions.base_suppressed)
        self.assertFalse(actions.led_dark_hold)
        self.assertEqual(actions.presentation, LEDS_PLUS_LASERS)
        self.assertEqual(actions.reason, "both_personality")
        self.assertEqual(machine._window_end_beat, 64.0 + cfg.drop_window_cap_beats)

    def test_leds_only_followup_drop_restamps_window(self) -> None:
        cfg = _cfg()
        machine = WindowMachine(cfg)
        machine.tick(_impact(0.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=64.0, beats_to_next_drop=0.0, next_drop_beat=64.0,
                         drop_role="post_drop", impact_now=True, laser_visible=True),
            pending_presentation=LEDS_ONLY, pending_reason="leds_only_followup",
        )
        self.assertTrue(actions.base_suppressed)
        self.assertEqual(actions.presentation, LEDS_ONLY)
        self.assertEqual(actions.reason, "leds_only_followup")
        self.assertEqual(machine._window_end_beat, 64.0 + cfg.drop_window_cap_beats)

    def test_128_beat_section_stays_suppressed_until_role_exit(self) -> None:
        machine = WindowMachine(_cfg())
        machine.tick(_impact(0.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=127.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="post_drop", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertTrue(actions.base_suppressed)
        self.assertEqual(actions.presentation, LEDS_ONLY)
        actions = machine.tick(
            WindowInputs(abs_beat=128.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="none", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertEqual(actions, WindowActions(led_dark_hold=False, base_suppressed=False, presentation=None, reason=""))

    def test_leds_only_window_releases_when_role_leaves_before_backstop(self) -> None:
        machine = WindowMachine(_cfg())
        machine.tick(_impact(100.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=148.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="none", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertEqual(actions, WindowActions(led_dark_hold=False, base_suppressed=False, presentation=None, reason=""))

    def test_leds_only_window_releases_at_backstop_if_role_sticks(self) -> None:
        machine = WindowMachine(_cfg())
        machine.tick(_impact(0.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=191.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="post_drop", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertTrue(actions.base_suppressed)
        actions = machine.tick(
            WindowInputs(abs_beat=192.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="post_drop", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertEqual(actions, WindowActions(led_dark_hold=False, base_suppressed=False, presentation=None, reason=""))

    def test_impact_without_pending_presentation_keeps_old_window(self) -> None:
        machine = WindowMachine(_cfg())
        machine.tick(_impact(0.0), pending_presentation=LEDS_ONLY, pending_reason="leds_only_personality")
        actions = machine.tick(
            WindowInputs(abs_beat=64.0, beats_to_next_drop=0.0, next_drop_beat=64.0,
                         drop_role="post_drop", impact_now=True, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertTrue(actions.base_suppressed)
        self.assertEqual((actions.presentation, actions.reason), (LEDS_ONLY, "leds_only_personality"))
        self.assertEqual(machine._window_end_beat, 192.0)

    def test_predicted_impact_passing_without_a_confirmed_drop(self) -> None:
        machine = WindowMachine(_cfg(led_predark_beats=4))
        armed = machine.tick(
            WindowInputs(abs_beat=96.0, beats_to_next_drop=4.0, next_drop_beat=100.0,
                         drop_role="none", impact_now=False, laser_visible=True),
            pending_presentation=LASERS_ONLY, pending_reason="solo_manual",
        )
        self.assertTrue(armed.led_dark_hold)
        passed = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="none", impact_now=False, laser_visible=True),
            pending_presentation=None, pending_reason="",
        )
        self.assertFalse(passed.led_dark_hold)


# ---- Required Behavior Test 9: scripted exemption -----------------------


class RequiredTest9ScriptedExemption(unittest.TestCase):
    def test_scripted_mode_is_a_universal_noop_even_mid_window(self) -> None:
        machine = WindowMachine(_cfg())
        machine.tick(_impact(100.0), pending_presentation=LASERS_ONLY, pending_reason="solo_manual")
        actions = machine.tick(
            WindowInputs(abs_beat=101.0, beats_to_next_drop=None, next_drop_beat=None,
                         drop_role="drop", impact_now=False, laser_visible=True, scripted_mode=True),
            pending_presentation=LASERS_ONLY, pending_reason="solo_manual",
        )
        self.assertEqual(actions, WindowActions(led_dark_hold=False, base_suppressed=False, presentation=None, reason=""))

    def test_scripted_mode_never_arms_pre_dark(self) -> None:
        machine = WindowMachine(_cfg(led_predark_beats=4))
        actions = machine.tick(
            WindowInputs(abs_beat=96.0, beats_to_next_drop=4.0, next_drop_beat=100.0,
                         drop_role="none", impact_now=False, laser_visible=True, scripted_mode=True),
            pending_presentation=LASERS_ONLY, pending_reason="solo_manual",
        )
        self.assertFalse(actions.led_dark_hold)


# ---- Additional Task 6 coverage -----------------------------------------


class RunwayMathTests(unittest.TestCase):
    def test_missing_phrase_data_is_zero(self) -> None:
        self.assertEqual(runway_beats(64.0, []), 0.0)

    def test_contiguous_breakdown_then_buildup_accumulates(self) -> None:
        segs = [_seg(0, 32, "low"), _seg(32, 64, "up")]
        self.assertEqual(runway_beats(64.0, segs), 64.0)

    def test_gap_before_drop_breaks_contiguity(self) -> None:
        segs = [_seg(0, 16, "up"), _seg(20, 32, "up")]  # gap 16-20
        self.assertEqual(runway_beats(32.0, segs), 12.0)

    def test_chorus_between_breakdown_and_drop_breaks_contiguity(self) -> None:
        segs = [_seg(0, 16, "up"), _seg(16, 48, "chorus"), _seg(48, 64, "low")]
        self.assertEqual(runway_beats(64.0, segs), 16.0)


class PlannerDeterminismTests(unittest.TestCase):
    def test_repeated_calls_are_byte_identical(self) -> None:
        segs = [_seg(0, 32, "up"), _seg(64, 96, "low")]
        drops = [32.0, 96.0, 160.0]
        tags = [95.0]
        learned = [160.5]
        plan_a = plan_track(drops, segs, tags, learned, _cfg())
        plan_b = plan_track(drops, segs, tags, learned, _cfg())
        self.assertEqual(plan_a.decisions, plan_b.decisions)
        self.assertEqual(plan_a.unmatched_tag_beats, plan_b.unmatched_tag_beats)

    def test_unmatched_hotcue_is_surfaced_not_dropped(self) -> None:
        plan = plan_track([32.0], [], [200.0], [], _cfg())
        self.assertEqual(plan.unmatched_tag_beats, (200.0,))
        self.assertFalse(plan.decision_for(32.0).tagged)


class DropPresentationConfigTests(unittest.TestCase):
    def test_from_dict_reads_every_field(self) -> None:
        cfg = DropPresentationConfig.from_dict({
            "enabled": False, "laser_ratio": 0.5, "opening_tracks": 2,
            "led_predark_beats": 8, "drop_window_cap_beats": 16,
            "hotcue_marker": "LZR", "solo_learn_threshold": 2,
            "gearshift_bpm_jump": 12.0, "record_min_drops": 3,
            "ws_handoff_enabled": True,
        })
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.laser_ratio, 0.5)
        self.assertEqual(cfg.opening_tracks, 2)
        self.assertEqual(cfg.led_predark_beats, 8)
        self.assertEqual(cfg.drop_window_cap_beats, 16)
        self.assertEqual(cfg.hotcue_marker, "LZR")
        self.assertEqual(cfg.solo_learn_threshold, 2)
        self.assertEqual(cfg.gearshift_bpm_jump, 12.0)
        self.assertEqual(cfg.record_min_drops, 3)
        self.assertTrue(cfg.ws_handoff_enabled)

    def test_defaults_match_the_spec(self) -> None:
        cfg = DropPresentationConfig.from_dict({})
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.laser_ratio, 0.4)
        self.assertEqual(cfg.opening_tracks, 3)
        self.assertEqual(cfg.led_predark_beats, 4)
        self.assertEqual(cfg.drop_window_cap_beats, 192)
        self.assertEqual(cfg.hotcue_marker, "LASER")
        self.assertEqual(cfg.solo_learn_threshold, 1)
        self.assertEqual(cfg.gearshift_bpm_jump, 10.0)
        self.assertEqual(cfg.record_min_drops, 5)
        self.assertFalse(cfg.ws_handoff_enabled)

    def test_missing_config_file_degrades_to_defaults(self) -> None:
        cfg = load_drop_presentation_config("/tmp/definitely-does-not-exist-drop-pres.json")
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.hotcue_marker, "LASER")

    def test_loader_reads_the_block_from_a_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            path.write_text(json.dumps({
                "drop_presentation": {"enabled": False, "laser_ratio": 0.25},
            }), encoding="utf-8")
            cfg = load_drop_presentation_config(path)
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.laser_ratio, 0.25)


if __name__ == "__main__":
    unittest.main()
