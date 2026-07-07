"""Task 4/6 (drop_presentation): state_manager.py wiring integration tests.

Exercises _maybe_build_drop_plan / _drop_presentation_tick / the Ev.LASER_SOLO_PAD
event / the darkness guard / the master enabled:false regression gate directly
against a StateManager instance, reusing the pack-driver test fixtures (the
established cross-file pattern; see test_laser_blackout_rewire.py). This does
NOT drive the full _push_tick_inner()/_run() loop -- it calls the narrow
drop-presentation methods directly with controlled inputs, the same style
test_state_manager_pack_driver.py already uses for _drive_pack_output().
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rb_ss_bridge_v2.drop_presentation import (  # noqa: E402
    LEDS_ONLY,
    LEDS_PLUS_LASERS,
    LASERS_ONLY,
    DropPresentationConfig,
)
from rb_ss_bridge_v2.models import BridgeEvent, Ev  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import PhraseSegment, SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.soundswitch_laser_player import LaserPackPlayer  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime  # noqa: E402

from test_state_manager_pack_driver import (  # noqa: E402
    SSID,
    _FakeBackend,
    _FakeInput,
    _make_sm,
    _pack,
    _set,
)


def _deck_state(*, playing=True, load_gen=7, content_id="content-1", smart_drops=(64,),
                 scripted_id=0):
    return SimpleNamespace(
        meta=SimpleNamespace(content_id=content_id, smart_drops=list(smart_drops)),
        playing=playing,
        load_gen=load_gen,
        scripted_id=scripted_id,
    )


def _sp_state(**overrides):
    defaults = dict(
        abs_beat=64.0,
        next_smart_drop_beat=None,
        beats_to_next_drop=None,
        active_drop_beat=64.0,
        smart_drop_crossing=True,
        current_phrase_is_chorus=False,
        smart_post_drop_active=False,
    )
    defaults.update(overrides)
    return SmartPhrasingState(**defaults)


def _enable_drop_presentation(sm, **overrides) -> None:
    sm._drop_presentation_config = DropPresentationConfig(**{
        "enabled": True, "laser_ratio": 0.4, "opening_tracks": 3,
        "led_predark_beats": 4, "drop_window_cap_beats": 192,
        "hotcue_marker": "LASER", "solo_learn_threshold": 1,
        "gearshift_bpm_jump": 10.0, "record_min_drops": 5,
        "ws_handoff_enabled": False, **overrides,
    })
    # WindowMachine snapshots its config at construction time.
    from rb_ss_bridge_v2.drop_presentation import WindowMachine
    sm._drop_presentation_window = WindowMachine(sm._drop_presentation_config)


class WsHandoffNoOpGuardTests(unittest.TestCase):
    """Task 5: ws_handoff_enabled is parsed but its ritual tier is not
    implemented in this package; a named no-op guard must log a clear signal
    if an operator ever flips it on, rather than doing silently nothing."""

    def test_enabling_ws_handoff_logs_a_named_not_implemented_warning(self) -> None:
        with mock.patch(
            "rb_ss_bridge_v2.state_manager.load_drop_presentation_config",
            return_value=DropPresentationConfig(ws_handoff_enabled=True),
        ), self.assertLogs("state_manager", level="WARNING") as logs:
            sm = _make_sm()
        self.assertTrue(sm._drop_presentation_config.ws_handoff_enabled)
        self.assertTrue(
            any("ws-handoff-not-implemented" in r.getMessage() for r in logs.records)
        )

    def test_default_config_does_not_log_the_guard(self) -> None:
        with mock.patch(
            "rb_ss_bridge_v2.state_manager.load_drop_presentation_config",
            return_value=DropPresentationConfig(ws_handoff_enabled=False),
        ), self.assertNoLogs("state_manager", level="WARNING"):
            _make_sm()


class MasterRegressionGateTests(unittest.TestCase):
    """With /drop_presentation enabled: false, this package must be inert."""

    def test_disabled_config_never_touches_blackout_owner_or_suppression(self) -> None:
        sm = _make_sm()
        sm._drop_presentation_config = DropPresentationConfig(enabled=False)
        d = _deck_state()
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        sm._drop_presentation_tick(active=1, d=d, sp_state=_sp_state(), impact_now=True)

        self.assertEqual(sm._led_blackout_owners, set())
        self.assertFalse(sm._drop_presentation_led_dark_held)
        self.assertFalse(sm._drop_presentation_base_suppressed_held)

    def test_disabled_config_solo_pad_press_is_a_noop(self) -> None:
        sm = _make_sm()
        sm._drop_presentation_config = DropPresentationConfig(enabled=False)
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        sm._deck = {1: _deck_state()}
        sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))
        self.assertIsNone(sm._drop_presentation_armed_key)


class ScriptedExemptionIntegrationTests(unittest.TestCase):
    def test_scripted_lighting_mode_never_applies_suppression_or_blackout(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(scripted_id=999)
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="scripted")
        sm._drop_presentation_tick(
            active=1, d=d, sp_state=_sp_state(), impact_now=True,
        )
        self.assertEqual(sm._led_blackout_owners, set())
        self.assertFalse(sm._drop_presentation_base_suppressed_held)


class DamperAudibleLatchIntegrationTests(unittest.TestCase):
    """Task 4 item 3: the >=16-beat audible latch lives inside
    _drop_presentation_tick itself (distinct from SessionState.mark_track_counted's
    own idempotency, which tests/test_drop_presentation.py already covers)."""

    def test_track_counts_only_after_16_beats_of_actual_playback(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(load_gen=6, playing=True)
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")

        sm._drop_presentation_tick(
            active=1, d=d, sp_state=_sp_state(abs_beat=100.0, smart_drop_crossing=False),
            impact_now=False,
        )
        self.assertEqual(sm._drop_presentation_session.opening_tracks_counted, 0)

        # 10 beats in: still short of the 16-beat threshold.
        sm._drop_presentation_tick(
            active=1, d=d, sp_state=_sp_state(abs_beat=110.0, smart_drop_crossing=False),
            impact_now=False,
        )
        self.assertEqual(sm._drop_presentation_session.opening_tracks_counted, 0)

        # 16 beats in: now counted, exactly once.
        sm._drop_presentation_tick(
            active=1, d=d, sp_state=_sp_state(abs_beat=116.0, smart_drop_crossing=False),
            impact_now=False,
        )
        self.assertEqual(sm._drop_presentation_session.opening_tracks_counted, 1)
        sm._drop_presentation_tick(
            active=1, d=d, sp_state=_sp_state(abs_beat=120.0, smart_drop_crossing=False),
            impact_now=False,
        )
        self.assertEqual(sm._drop_presentation_session.opening_tracks_counted, 1)

    def test_loaded_but_never_playing_deck_never_counts(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(load_gen=6, playing=False)
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        for beat in (100.0, 116.0, 140.0):
            sm._drop_presentation_tick(
                active=1, d=d, sp_state=_sp_state(abs_beat=beat, smart_drop_crossing=False),
                impact_now=False,
            )
        self.assertEqual(sm._drop_presentation_session.opening_tracks_counted, 0)


class PlanAndTickIntegrationTests(unittest.TestCase):
    def _sm_with_plan(
        self, *, drops=(64.0,), tags=(), learned=(), with_player=False,
        phrase_segments=None,
    ):
        if with_player:
            backend = _FakeBackend()
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=backend)
            self.backend = backend
        else:
            sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(load_gen=3, smart_drops=[int(b) for b in drops])
        sm._deck = {1: d}
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        sm._drop_presentation_anlz_ready[1] = 3
        sm._drop_presentation_tags_ready[1] = 3
        sm._drop_presentation_tag_beats[1] = tuple(tags)
        sm._drop_presentation_learned_store._entries["content-1"] = list(learned)
        if phrase_segments is None:
            phrase_segments = tuple(
                PhraseSegment(float(beat) - 16.0, float(beat), "up") for beat in drops
            )
        sm._build_phrase_segments = lambda _d: tuple(phrase_segments)
        sm._maybe_build_drop_plan(1)
        return sm, d

    def test_runway_less_drop_from_idle_does_not_open_window(self) -> None:
        sm, d = self._sm_with_plan(
            drops=(64.0,),
            phrase_segments=(PhraseSegment(0.0, 16.0, "up"),),
        )
        self.assertEqual(sm._drop_presentation_plan.decision_for(64.0).runway, 0.0)
        sm._drop_presentation_session.opening_tracks_counted = 3

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=64.0, active_drop_beat=64.0, smart_drop_crossing=True),
            impact_now=True,
        )

        self.assertIsNone(sm._drop_presentation_last_actions.presentation)
        self.assertFalse(sm._drop_presentation_last_actions.base_suppressed)
        self.assertEqual(sm._led_blackout_owners, set())

    def test_runway_less_marker_inside_leds_only_window_does_not_reenter(self) -> None:
        sm, d = self._sm_with_plan(
            drops=(32.0, 96.0),
            with_player=True,
            phrase_segments=(PhraseSegment(16.0, 32.0, "up"),),
        )
        self.assertGreater(sm._drop_presentation_plan.decision_for(32.0).runway, 0.0)
        self.assertEqual(sm._drop_presentation_plan.decision_for(96.0).runway, 0.0)
        sm._drop_presentation_session.opening_tracks_counted = 3
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        original_end = sm._drop_presentation_window._window_end_beat

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=96.0, active_drop_beat=96.0, smart_drop_crossing=True),
            impact_now=True,
        )

        self.assertEqual(sm._drop_presentation_last_actions.presentation, LEDS_ONLY)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "leds_only_personality")
        self.assertTrue(sm._drop_presentation_base_suppressed_held)
        self.assertEqual(sm._drop_presentation_window._window_end_beat, original_end)

    def test_true_drop_inside_open_window_reenters_with_own_presentation(self) -> None:
        sm, d = self._sm_with_plan(drops=(32.0, 96.0))
        sm._drop_presentation_session.opening_tracks_counted = 3
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertEqual(sm._drop_presentation_last_actions.presentation, LEDS_ONLY)

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=96.0, active_drop_beat=96.0, smart_drop_crossing=True),
            impact_now=True,
        )

        self.assertEqual(sm._drop_presentation_last_actions.presentation, LEDS_PLUS_LASERS)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "both_finale")
        self.assertEqual(sm._drop_presentation_window._window_end_beat, 288.0)

    def test_runway_less_hotcue_tag_still_opens_window(self) -> None:
        sm, d = self._sm_with_plan(
            drops=(64.0,),
            tags=(64.5,),
            phrase_segments=(PhraseSegment(0.0, 16.0, "up"),),
        )
        sm._drop_presentation_base_live = True
        sm._laser_director = mock.Mock()
        sm._laser_director.is_enabled.return_value = True

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=64.0, active_drop_beat=64.0, smart_drop_crossing=True),
            impact_now=True,
        )

        self.assertEqual(sm._drop_presentation_last_actions.presentation, LASERS_ONLY)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "solo_hotcue")
        self.assertIn("drop_spotlight", sm._led_blackout_owners)

    def test_manual_armed_runway_less_drop_still_fires_lasers_only(self) -> None:
        sm, d = self._sm_with_plan(
            drops=(64.0,),
            phrase_segments=(PhraseSegment(0.0, 16.0, "up"),),
        )
        sm._drop_presentation_armed_key = (1, 3)
        sm._drop_presentation_base_live = True
        sm._laser_director = mock.Mock()
        sm._laser_director.is_enabled.return_value = True

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=64.0, active_drop_beat=64.0, smart_drop_crossing=True),
            impact_now=True,
        )

        self.assertEqual(sm._drop_presentation_last_actions.presentation, LASERS_ONLY)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "solo_manual")
        self.assertIsNone(sm._drop_presentation_armed_key)

    def test_runway_less_raw_impact_still_updates_session_bookkeeping(self) -> None:
        sm, d = self._sm_with_plan(
            drops=(64.0,),
            phrase_segments=(PhraseSegment(0.0, 16.0, "up"),),
        )
        self.assertEqual(sm._drop_presentation_session.observed_drop_count, 0)

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=64.0, active_drop_beat=64.0, smart_drop_crossing=True),
            impact_now=True,
        )

        self.assertEqual(sm._drop_presentation_session.observed_drop_count, 1)
        self.assertEqual(sm._drop_presentation_session.runway_record, 0.0)

    def test_leds_only_drop_suppresses_base_without_touching_blackout(self) -> None:
        # Single drop track -> personality gives it lasers (ceil(0.4*1)=1) AND
        # it's the finale, so use two drops so the FIRST one is leds_only.
        sm, d = self._sm_with_plan(drops=(32.0, 96.0), with_player=True)
        plan = sm._drop_presentation_plan
        self.assertEqual(plan.decision_for(32.0).personality_presentation, LEDS_ONLY)
        # A fresh session starts with the opening damper active; clear it so
        # this test demonstrates the PERSONALITY reason, not the damper one
        # (both render leds_only -- the damper interaction has its own test
        # coverage in tests/test_drop_presentation.py).
        sm._drop_presentation_session.opening_tracks_counted = 3

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertEqual(sm._drop_presentation_last_actions.reason, "leds_only_personality")
        self.assertTrue(sm._drop_presentation_last_actions.base_suppressed)
        self.assertTrue(sm._drop_presentation_base_suppressed_held)
        self.assertEqual(sm._led_blackout_owners, set())
        # Verify the REAL player actually applied it, not just the bookkeeping flag.
        self.assertEqual(sm._pack_runtime.player.render().diagnostic.code, "base_suppressed")

    def test_finale_drop_outside_damper_is_leds_plus_lasers_no_suppression_no_blackout(self) -> None:
        sm, d = self._sm_with_plan(drops=(32.0, 96.0))
        # Clear the opening damper: the finale guarantee (rung 8) applies only
        # OUTSIDE the damper (rung 7 precedes it, first match wins).
        sm._drop_presentation_session.opening_tracks_counted = 3
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=96.0, active_drop_beat=96.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertFalse(sm._drop_presentation_base_suppressed_held)
        self.assertEqual(sm._led_blackout_owners, set())
        self.assertEqual(sm._drop_presentation_last_actions.presentation, LEDS_PLUS_LASERS)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "both_finale")

    def test_finale_drop_under_damper_is_leds_only_and_suppresses(self) -> None:
        # Rung 7 precedes rung 8: a fresh session's damper forces the last true
        # drop of a non-exempt track to leds_only like every other non-exempt
        # drop ("save the night's first laser moment").
        sm, d = self._sm_with_plan(drops=(32.0, 96.0), with_player=True)
        self.assertTrue(sm._drop_presentation_session.damper_active(3))
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=96.0, active_drop_beat=96.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertEqual(sm._drop_presentation_last_actions.reason, "leds_only_damper")
        self.assertTrue(sm._drop_presentation_base_suppressed_held)
        self.assertEqual(sm._led_blackout_owners, set())

    def test_hotcue_tagged_drop_engages_led_blackout_owner_when_laser_visible(self) -> None:
        sm, d = self._sm_with_plan(drops=(32.0, 96.0), tags=(32.5,))
        sm._drop_presentation_base_live = True
        laser_director = mock.Mock()
        laser_director.is_enabled.return_value = True
        sm._laser_director = laser_director

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertIn("drop_spotlight", sm._led_blackout_owners)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "solo_hotcue")
        self.assertFalse(sm._drop_presentation_base_suppressed_held)

        # Fail-open: role drops out of drop/post_drop -> window ends, LED
        # blackout owner releases (never touching any OTHER owner).
        sm._led_blackout_owners.add("led_mute_pad")
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=40.0, active_drop_beat=None, smart_drop_crossing=False,
                                current_phrase_is_chorus=False, smart_post_drop_active=False),
            impact_now=False,
        )
        self.assertNotIn("drop_spotlight", sm._led_blackout_owners)
        self.assertIn("led_mute_pad", sm._led_blackout_owners)

    def test_darkness_guard_downgrades_when_laser_masked(self) -> None:
        sm, d = self._sm_with_plan(drops=(32.0, 96.0), tags=(32.5,))
        sm._drop_presentation_base_live = True
        laser_director = mock.Mock()
        laser_director.is_enabled.return_value = True
        sm._laser_director = laser_director
        laser_executor = mock.Mock()
        laser_executor.mask_owners_active.return_value = True  # laser muted/blacked out
        sm._laser_executor = laser_executor

        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertEqual(sm._drop_presentation_last_actions.presentation, LEDS_PLUS_LASERS)
        self.assertEqual(sm._drop_presentation_last_actions.reason, "guard_fallback_both")
        self.assertEqual(sm._led_blackout_owners, set())

    def test_plan_unavailable_at_impact_fails_open_without_suppression(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(load_gen=9)
        sm._deck = {1: d}
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        # Deliberately do NOT build a plan (ANLZ/tags never marked ready).
        sm._drop_presentation_tick(
            active=1, d=d, sp_state=_sp_state(), impact_now=True,
        )
        self.assertIsNone(sm._drop_presentation_last_actions.presentation)
        self.assertFalse(sm._drop_presentation_last_actions.base_suppressed)
        self.assertEqual(sm._led_blackout_owners, set())
        self.assertEqual(sm._drop_presentation_last_pending[:2], (LEDS_PLUS_LASERS, "plan_unavailable"))


class SoloPadIntegrationTests(unittest.TestCase):
    def test_solo_arm_then_disarm_logs_feedback_transitions(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        sm._deck = {1: _deck_state(load_gen=5)}
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")

        with self.assertLogs("perf.override", level="INFO") as logs:
            sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))
            sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))

        records = [
            record for record in logs.records
            if (getattr(record, "data", None) or {}).get("action") == "solo_feedback"
        ]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].getMessage(), "laser solo armed (was off)")
        self.assertEqual(records[0].data["state"], "armed")
        self.assertEqual(records[0].data["prev"], "off")
        self.assertTrue(records[0].data["armed_manual"])
        self.assertEqual(records[1].getMessage(), "laser solo off (was armed)")
        self.assertEqual(records[1].data["state"], "off")
        self.assertEqual(records[1].data["prev"], "armed")
        self.assertFalse(records[1].data["armed_manual"])

    def test_solo_feedback_does_not_log_when_state_is_unchanged(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)

        with self.assertNoLogs("perf.override", level="INFO"):
            sm._drop_presentation_update_solo_feedback()

    def test_arm_fire_learn_disarm_round_trip_via_real_event_dispatch(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(load_gen=5, smart_drops=[32, 96])
        sm._deck = {1: d}
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        sm._drop_presentation_anlz_ready[1] = 5
        sm._drop_presentation_tags_ready[1] = 5
        sm._build_phrase_segments = lambda _d: ()
        sm._maybe_build_drop_plan(1)
        sm._drop_presentation_base_live = True
        laser_director = mock.Mock()
        laser_director.is_enabled.return_value = True
        sm._laser_director = laser_director

        # Press: nothing pending -> arms.
        sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))
        self.assertEqual(sm._drop_presentation_armed_key, (1, 5))

        # Impact on the FIRST drop (32.0, otherwise leds_only by personality)
        # -> manual arm wins the ladder and fires.
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertEqual(sm._drop_presentation_last_actions.reason, "solo_manual")
        self.assertIsNone(sm._drop_presentation_armed_key)  # one-shot, consumed
        self.assertEqual(sm._drop_presentation_learned_store.beats_for_track("content-1"), (32.0,))

        # Second press with nothing pending now arms again for the NEXT drop.
        sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))
        self.assertEqual(sm._drop_presentation_armed_key, (1, 5))
        # Disarm: pressing again while armed clears it.
        sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))
        self.assertIsNone(sm._drop_presentation_armed_key)

    def test_veto_of_pending_learned_solo_unlearns_it(self) -> None:
        sm = _make_sm()
        _enable_drop_presentation(sm)
        d = _deck_state(load_gen=11, smart_drops=[64])
        sm._deck = {1: d}
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        sm._drop_presentation_anlz_ready[1] = 11
        sm._drop_presentation_tags_ready[1] = 11
        sm._drop_presentation_tag_beats[1] = ()
        sm._drop_presentation_learned_store._entries["content-1"] = [64.0]
        sm._build_phrase_segments = lambda _d: ()
        sm._maybe_build_drop_plan(1)

        # Lookahead tick (not yet impact) caches the pending learned solo.
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(
                abs_beat=60.0, active_drop_beat=None, smart_drop_crossing=False,
                next_smart_drop_beat=64.0, beats_to_next_drop=4.0,
            ),
            impact_now=False,
        )
        self.assertEqual(sm._drop_presentation_last_pending[:2], (LASERS_ONLY, "solo_learned"))

        with self.assertLogs("perf.override", level="INFO") as logs:
            sm._handle_event(BridgeEvent(kind=Ev.LASER_SOLO_PAD, deck=0, source="test"))
        veto_records = [
            record for record in logs.records
            if (getattr(record, "data", None) or {}).get("action") == "solo_veto"
        ]
        self.assertEqual(len(veto_records), 1)
        self.assertEqual(veto_records[0].getMessage(), "laser solo veto (solo_learned)")
        self.assertEqual(veto_records[0].data["pending_reason"], "solo_learned")
        self.assertEqual(veto_records[0].data["pending_beat"], 64.0)
        self.assertTrue(veto_records[0].data["unlearned"])
        self.assertEqual(sm._drop_presentation_learned_store.beats_for_track("content-1"), ())
        self.assertTrue(sm._drop_presentation_session.is_vetoed((1, 11), 64.0))
        self.assertIsNone(sm._drop_presentation_armed_key)

        # The vetoed drop now falls through to personality/finale at impact.
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=64.0, active_drop_beat=64.0, smart_drop_crossing=True),
            impact_now=True,
        )
        self.assertNotEqual(sm._drop_presentation_last_actions.reason, "solo_learned")


class ByteIdentityRegressionTests(unittest.TestCase):
    def _drive(self, *, enabled: bool) -> tuple:
        backend = _FakeBackend()
        midi_input = _FakeInput()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=backend, midi_input=midi_input)
        _enable_drop_presentation(sm, enabled=enabled)
        _set(sm, ssid=SSID, elapsed_ms=100, playing=True, load_gen=1, active=1,
             scripted_id=1, lighting_mode="scripted")
        for _ in range(3):
            sm._drive_pack_output()
        return tuple(backend.frames)

    def test_scripted_track_frames_are_byte_identical_regardless_of_enabled(self) -> None:
        self.assertEqual(self._drive(enabled=True), self._drive(enabled=False))

    def test_disabled_config_is_the_default_master_regression_gate(self) -> None:
        # enabled: false must restore pre-policy behavior exactly -- confirm the
        # ONLY seam (set_base_suppressed) is provably never reached when
        # disabled, for a track that WOULD otherwise suppress if enabled.
        backend = _FakeBackend()
        midi_input = _FakeInput()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=backend, midi_input=midi_input)
        _enable_drop_presentation(sm, enabled=False)
        d = _deck_state(load_gen=4, smart_drops=[32, 96])
        sm._deck = {1: d}
        sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        sm._drop_presentation_tick(
            active=1, d=d,
            sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
            impact_now=True,
        )
        with mock.patch.object(sm._pack_runtime.player, "set_base_suppressed") as suppressed:
            sm._drop_presentation_tick(
                active=1, d=d,
                sp_state=_sp_state(abs_beat=32.0, active_drop_beat=32.0, smart_drop_crossing=True),
                impact_now=True,
            )
            suppressed.assert_not_called()


class LearnedStorePersistenceTests(unittest.TestCase):
    def test_fire_enqueues_to_a_background_writer_not_the_tick_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "learned.json"
            sm = _make_sm()
            _enable_drop_presentation(sm)
            sm._drop_presentation_learned_writer.stop()
            sm._drop_presentation_learned_writer.join(timeout=1.0)
            from rb_ss_bridge_v2.led_palette_control import PaletteFeedbackWriter
            sm._drop_presentation_learned_writer = PaletteFeedbackWriter(str(path), debounce_s=0.01)
            sm._drop_presentation_learned_writer.start()
            self.addCleanup(sm._drop_presentation_learned_writer.stop)

            d = _deck_state(load_gen=2, smart_drops=[64])
            sm._deck = {1: d}
            sm._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
            sm._drop_presentation_anlz_ready[1] = 2
            sm._drop_presentation_tags_ready[1] = 2
            sm._build_phrase_segments = lambda _d: ()
            sm._maybe_build_drop_plan(1)
            sm._drop_presentation_armed_key = (1, 2)
            sm._drop_presentation_base_live = True
            laser_director = mock.Mock()
            laser_director.is_enabled.return_value = True
            sm._laser_director = laser_director

            sm._drop_presentation_tick(
                active=1, d=d,
                sp_state=_sp_state(abs_beat=64.0, active_drop_beat=64.0, smart_drop_crossing=True),
                impact_now=True,
            )

            import time
            deadline = time.time() + 1.0
            while time.time() < deadline and not path.exists():
                time.sleep(0.01)
            self.assertTrue(path.exists())
            import json
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("content-1:64", on_disk)


class StopFailOpenReleaseTests(unittest.TestCase):
    """DD1 regression: a held Laser-Solo / pre-dark LED dark-hold must fail-open
    on stop -- including the reader-stale stop branch that returns before
    _drop_presentation_tick, whose owner-clear was previously the only release."""

    def _held_sm(self):
        # Real player so base suppression is exercised end-to-end, not just the
        # bookkeeping flag.
        backend = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=backend)
        _enable_drop_presentation(sm)
        sm._deck = {1: _deck_state(playing=True), 2: _deck_state(playing=False)}
        # Simulate a live solo window holding the Govees dark + laser base
        # suppressed (the exact state _drop_presentation_apply_actions leaves).
        sm._handle_led_event(BridgeEvent(
            kind=Ev.LED_BLACKOUT, deck=0,
            payload={"reason": "drop_spotlight"}, source="drop_presentation"))
        sm._drop_presentation_led_dark_held = True
        sm._pack_runtime.player.set_base_suppressed(True)
        sm._drop_presentation_base_suppressed_held = True
        return sm

    def test_release_clears_dark_hold_and_base_suppression_but_not_other_owners(self):
        sm = self._held_sm()
        # A manually-held mute must survive the fail-open (owner isolation).
        sm._handle_led_event(BridgeEvent(
            kind=Ev.LED_BLACKOUT, deck=0,
            payload={"reason": "led_mute_pad"}, source="palette_control"))
        self.assertIn("drop_spotlight", sm._led_blackout_owners)
        self.assertEqual(
            sm._pack_runtime.player.render().diagnostic.code, "base_suppressed")

        sm._drop_presentation_release_on_stop()

        self.assertNotIn("drop_spotlight", sm._led_blackout_owners)
        self.assertIn("led_mute_pad", sm._led_blackout_owners)  # isolation
        self.assertFalse(sm._drop_presentation_led_dark_held)
        self.assertFalse(sm._drop_presentation_base_suppressed_held)
        self.assertNotEqual(
            sm._pack_runtime.player.render().diagnostic.code, "base_suppressed")

    def test_do_stop_fails_open_a_held_dark_hold(self):
        # The real bug path: _do_stop is the single stop chokepoint; every stop
        # (stale or healthy) must release the hold through it.
        sm = self._held_sm()
        self.assertIn("drop_spotlight", sm._led_blackout_owners)
        sm._do_stop(1, 0)
        self.assertNotIn("drop_spotlight", sm._led_blackout_owners)
        self.assertFalse(sm._drop_presentation_led_dark_held)

    def test_enabled_release_without_a_held_hold_emits_no_led_event(self):
        # The common case: a normal stop with no solo window active must not
        # emit a spurious LED_CLEAR or churn owners -- the release only clears
        # when a dark hold is actually held (_drop_presentation_led_dark_held).
        sm = _make_sm()
        _enable_drop_presentation(sm)
        sm._deck = {1: _deck_state(playing=True), 2: _deck_state(playing=False)}
        self.assertFalse(sm._drop_presentation_led_dark_held)
        emitted = []
        sm._handle_led_event = lambda ev: emitted.append(ev.kind)
        sm._drop_presentation_release_on_stop()
        self.assertEqual(emitted, [])
        self.assertFalse(sm._drop_presentation_led_dark_held)

    def test_disabled_release_is_a_noop(self):
        # enabled:false byte-identity gate: the helper returns before building
        # any WindowInputs or touching an owner.
        sm = _make_sm()
        _enable_drop_presentation(sm, enabled=False)
        self.assertFalse(sm._drop_presentation_config.enabled)
        before = set(sm._led_blackout_owners)
        sm._drop_presentation_release_on_stop()
        self.assertEqual(sm._led_blackout_owners, before)
        self.assertFalse(sm._drop_presentation_led_dark_held)


if __name__ == "__main__":
    unittest.main()
