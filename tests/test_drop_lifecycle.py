"""Tests for drop_lifecycle.py — the pure, renderer-agnostic drop/post_drop resolver.

Covers: drop held for drop_impact_beats then post_drop; predecessor gate
(up/low/buildup/breakdown -> drop; groove/other label-only anchors -> NOT drop);
real smart-drop crossings always fire; capped chorus-to-chorus re-arms; lifecycle clear when
chorus/post-drop ends; flat-vs-flat LED parity (WITHOUT _led_note_drop_decision_accepted rewrite).

NOTE: This proves FLAT-WINDOW parity only. The live LED window is per-look-duration
(rewritten by _led_note_drop_decision_accepted); the laser window is the flat
drop_impact_beats. They are NOT equal in production.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.drop_lifecycle import (  # noqa: E402
    DropLifecycle,
    DropLifecycleConfig,
    DropResult,
)

_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})


def _cfg(
    *,
    max_drops: int = 2,
    impact_beats: float = 8.0,
    cycle_beats: float = 32.0,
) -> DropLifecycleConfig:
    return DropLifecycleConfig(
        max_drops_in_a_row=max_drops,
        drop_impact_beats=impact_beats,
        post_drop_cycle_beats=cycle_beats,
        impact_predecessors=_PREDECESSORS,
    )


def _sp(**kw) -> types.SimpleNamespace:
    """Build a duck-typed SmartPhrasing namespace with safe defaults."""
    defaults = dict(
        abs_beat=None,
        current_phrase_start_beat=None,
        beats_into_phrase=None,
        active_drop_beat=None,
        current_phrase_is_chorus=False,
        phrase_start_crossing=False,
        smart_drop_crossing=False,
        previous_phrase_label="other",
        current_phrase_label="other",
        smart_post_drop_active=False,
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


class TestDropAnchor(unittest.TestCase):
    def test_chorus_phrase_start_crossing(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(
            current_phrase_is_chorus=True,
            phrase_start_crossing=True,
            current_phrase_start_beat=128.0,
        )
        self.assertEqual(lc.drop_anchor(sp), 128.0)

    def test_smart_drop_crossing_with_active_drop_beat(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(smart_drop_crossing=True, active_drop_beat=256.0)
        self.assertEqual(lc.drop_anchor(sp), 256.0)

    def test_smart_drop_crossing_fallback_to_abs_beat(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(smart_drop_crossing=True, abs_beat=300.0)
        self.assertEqual(lc.drop_anchor(sp), 300.0)

    def test_no_anchor(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp()
        self.assertIsNone(lc.drop_anchor(sp))


class TestImpactAllowed(unittest.TestCase):
    def test_allowed_predecessors(self) -> None:
        for pred in ("up", "low", "buildup", "breakdown"):
            lc = DropLifecycle(_cfg())
            sp = _sp(previous_phrase_label=pred)
            self.assertTrue(lc.impact_allowed(sp), f"predecessor={pred}")

    def test_disallowed_predecessors(self) -> None:
        for pred in ("chorus", "other", "groove"):
            lc = DropLifecycle(_cfg())
            sp = _sp(previous_phrase_label=pred)
            self.assertFalse(lc.impact_allowed(sp), f"predecessor={pred}")

    def test_smart_drop_crossing_allows_after_groove(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(
            previous_phrase_label="groove",
            smart_drop_crossing=True,
            current_phrase_label="other",
        )
        self.assertTrue(lc.impact_allowed(sp))

    def test_label_only_chorus_to_chorus_allowed_after_anchor_until_cap(self) -> None:
        lc = DropLifecycle(_cfg(max_drops=2))
        lc._first_drop_anchor_beat = 64.0
        lc._impact_count = 1
        sp = _sp(previous_phrase_label="chorus")
        self.assertTrue(lc.impact_allowed(sp))

        lc._impact_count = 2
        self.assertFalse(lc.impact_allowed(sp))

    def test_chorus_to_chorus_requires_first_anchor(self) -> None:
        """chorus-to-chorus label-only re-arm needs an existing lifecycle anchor."""
        lc = DropLifecycle(_cfg(max_drops=2))
        sp = _sp(previous_phrase_label="chorus")
        self.assertFalse(lc.impact_allowed(sp))


class TestResolve(unittest.TestCase):
    def test_baseline_lifecycle(self) -> None:
        """A real crossing fires even when the previous label is not a predecessor."""
        lifecycle = DropLifecycle(_cfg(impact_beats=8.0))
        sp = _sp(
            smart_drop_crossing=True,
            active_drop_beat=62.0,
            current_phrase_is_chorus=False,
            current_phrase_label="pre_drop",
            previous_phrase_label="groove",
            abs_beat=60.0,
        )
        self.assertEqual(lifecycle.resolve(sp, mutate=True).role, "drop")
        self.assertFalse(lifecycle._first_drop_anchor_beat is None)

    def test_resolve_no_mutate(self) -> None:
        """resolve with mutate=False does NOT alter state."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        sp = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
            abs_beat=64.0,
        )

        # Initial state
        self.assertIsNone(lc._first_drop_anchor_beat)
        self.assertIsNone(lc._impact_until_beat)
        self.assertEqual(lc._impact_count, 0)

        # Resolve without mutate
        res = lc.resolve(sp, mutate=False)
        self.assertEqual(res.role, "drop")

        # State should be unchanged
        self.assertIsNone(lc._first_drop_anchor_beat)
        self.assertIsNone(lc._impact_until_beat)
        self.assertEqual(lc._impact_count, 0)

    def test_drop_impact_then_hold_then_post_drop(self) -> None:
        """Anchor fires drop, holds for impact_beats, then transitions to post_drop."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        # Drop crossing at beat 64
        sp_cross = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
            abs_beat=64.0,
        )
        res = lc.resolve(sp_cross, mutate=True)
        self.assertEqual(res.role, "drop")
        self.assertTrue(res.armed_this_tick)

        # Sustained inside impact window (beat 68 < 64+8=72)
        sp_hold = _sp(
            current_phrase_is_chorus=True,
            smart_post_drop_active=True,
            abs_beat=68.0,
        )
        res = lc.resolve(sp_hold, mutate=True)
        self.assertEqual(res.role, "drop")
        self.assertFalse(res.armed_this_tick)

        # After impact window (beat 80 >= 72)
        sp_post = _sp(
            current_phrase_is_chorus=True,
            smart_post_drop_active=True,
            abs_beat=80.0,
        )
        res = lc.resolve(sp_post, mutate=True)
        self.assertEqual(res.role, "post_drop")
        self.assertFalse(res.armed_this_tick)

    def test_smart_drop_crossing_after_groove_yields_drop(self) -> None:
        """A smart_drop_crossing with predecessor=groove yields drop."""
        lc = DropLifecycle(_cfg())
        sp = _sp(
            smart_drop_crossing=True,
            active_drop_beat=128.0,
            previous_phrase_label="groove",
            abs_beat=128.0,
        )
        res = lc.resolve(sp, mutate=True)
        self.assertEqual(res.role, "drop")
        self.assertTrue(res.armed_this_tick)

    def test_lifecycle_clears_when_chorus_ends(self) -> None:
        """After leaving chorus/post_drop, lifecycle state resets."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        # Arm
        sp_arm = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            abs_beat=64.0,
        )
        lc.resolve(sp_arm, mutate=True)
        self.assertIsNotNone(lc._first_drop_anchor_beat)

        # Leave chorus (no anchor, not chorus, not post_drop_active)
        sp_groove = _sp(abs_beat=200.0, current_phrase_label="other")
        lc.resolve(sp_groove, mutate=True)
        self.assertIsNone(lc._first_drop_anchor_beat)
        self.assertEqual(lc._impact_count, 0)

    def test_none_role_when_not_in_chorus(self) -> None:
        """Outside the chorus window, resolver returns 'none'."""
        lc = DropLifecycle(_cfg())
        sp = _sp(abs_beat=64.0, current_phrase_label="up")
        res = lc.resolve(sp, mutate=True)
        self.assertEqual(res.role, "none")

    def test_armed_this_tick_only_on_impact(self) -> None:
        """armed_this_tick is True ONLY when arm() runs (impact_allowed + anchor)."""
        lc = DropLifecycle(_cfg())
        # Allowed predecessor
        sp1 = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            abs_beat=64.0,
        )
        res1 = lc.resolve(sp1, mutate=True)
        self.assertTrue(res1.armed_this_tick)

        # Sustained chorus (no new anchor)
        sp2 = _sp(
            current_phrase_is_chorus=True,
            abs_beat=66.0,
        )
        res2 = lc.resolve(sp2, mutate=True)
        self.assertFalse(res2.armed_this_tick)

    def test_abs_beat_fallback_composition(self) -> None:
        """_abs_beat prefers abs_beat, then phrase+offset, then active_drop_beat."""
        lc = DropLifecycle(_cfg())
        # Priority 1: abs_beat
        sp1 = _sp(abs_beat=100.0, current_phrase_start_beat=50.0, beats_into_phrase=10.0)
        self.assertEqual(lc._abs_beat(sp1), 100.0)
        # Priority 2: phrase + offset
        sp2 = _sp(current_phrase_start_beat=50.0, beats_into_phrase=10.0)
        self.assertEqual(lc._abs_beat(sp2), 60.0)
        # Priority 3: active_drop_beat
        sp3 = _sp(active_drop_beat=200.0)
        self.assertEqual(lc._abs_beat(sp3), 200.0)
        # None
        sp4 = _sp()
        self.assertIsNone(lc._abs_beat(sp4))

    def test_operator_32_beat_impact_window(self) -> None:
        """With operator's 32-beat window, drop holds until beat anchor+32."""
        lc = DropLifecycle(_cfg(impact_beats=32.0))
        sp_cross = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
            abs_beat=64.0,
        )
        lc.resolve(sp_cross, mutate=True)

        # Beat 95: still in window (64+32=96)
        sp_95 = _sp(current_phrase_is_chorus=True, abs_beat=95.0)
        self.assertEqual(lc.resolve(sp_95, mutate=True).role, "drop")

        # Beat 96: window expired
        sp_96 = _sp(current_phrase_is_chorus=True, abs_beat=96.0)
        self.assertEqual(lc.resolve(sp_96, mutate=True).role, "post_drop")

    def test_two_hit_chorus_rearm_cap_sequence(self) -> None:
        lc = DropLifecycle(_cfg(impact_beats=8.0, max_drops=2))
        sequence = [
            _sp(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                previous_phrase_label="up",
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=64.0,
                phrase_start_crossing=True,
                abs_beat=64.0,
            ),
            _sp(
                previous_phrase_label="chorus",
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=96.0,
                phrase_start_crossing=True,
                abs_beat=96.0,
            ),
            _sp(
                previous_phrase_label="chorus",
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=128.0,
                phrase_start_crossing=True,
                abs_beat=128.0,
            ),
            _sp(
                previous_phrase_label="chorus",
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=160.0,
                phrase_start_crossing=True,
                abs_beat=160.0,
            ),
        ]

        results = [lc.resolve(sp, mutate=True) for sp in sequence]

        self.assertEqual([res.role for res in results], ["drop", "drop", "post_drop", "post_drop"])
        self.assertEqual([res.armed_this_tick for res in results], [True, True, False, False])
        self.assertEqual(lc._impact_count, 2)
        self.assertEqual(lc._first_drop_anchor_beat, 64.0)

    def test_cap_resets_after_section_clear(self) -> None:
        lc = DropLifecycle(_cfg(impact_beats=8.0, max_drops=2))
        for sp in (
            _sp(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                previous_phrase_label="up",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=64.0,
                phrase_start_crossing=True,
                abs_beat=64.0,
            ),
            _sp(
                previous_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=96.0,
                phrase_start_crossing=True,
                abs_beat=96.0,
            ),
        ):
            self.assertEqual(lc.resolve(sp, mutate=True).role, "drop")
        self.assertEqual(lc._impact_count, 2)

        self.assertEqual(lc.resolve(_sp(abs_beat=200.0), mutate=True).role, "none")
        self.assertEqual(lc._impact_count, 0)
        fresh = lc.resolve(
            _sp(
                smart_drop_crossing=True,
                active_drop_beat=224.0,
                previous_phrase_label="up",
                current_phrase_is_chorus=True,
                abs_beat=224.0,
            ),
            mutate=True,
        )
        self.assertEqual((fresh.role, fresh.armed_this_tick), ("drop", True))
        self.assertEqual(lc._impact_count, 1)

    def test_single_marker_track_stays_one_impact(self) -> None:
        lc = DropLifecycle(_cfg(impact_beats=8.0, max_drops=2))
        self.assertEqual(
            lc.resolve(
                _sp(
                    smart_drop_crossing=True,
                    active_drop_beat=64.0,
                    previous_phrase_label="up",
                    current_phrase_is_chorus=True,
                    abs_beat=64.0,
                ),
                mutate=True,
            ).role,
            "drop",
        )
        self.assertEqual(lc.resolve(_sp(current_phrase_is_chorus=True, abs_beat=68.0), mutate=True).role, "drop")
        self.assertEqual(lc.resolve(_sp(current_phrase_is_chorus=True, abs_beat=80.0), mutate=True).role, "post_drop")
        self.assertEqual(lc._impact_count, 1)


class TestParity(unittest.TestCase):
    """Flat-vs-flat parity with the LED resolver.

    This proves the pure resolver reproduces the StateManager LED drop/post_drop
    region with LED-equivalent config (max=2, impact=8). It maps LED non-drop roles
    (breakdown, pre_drop, buildup, low, groove) to 'none'.
    It does NOT prove live-LED-window parity (the LED rewrite via
    _led_note_drop_decision_accepted is out of scope).
    """

    def setUp(self) -> None:
        # Source the flat-window config from the REAL LED module constants so this
        # comparison stays valid if the LED defaults ever change, and fails loudly
        # if they ever diverge from the resolver's expectation.
        from rb_ss_bridge_v2 import state_manager as sm_mod
        self.assertEqual(sm_mod.LED_MAX_DROP_IMPACTS, 2)
        self.assertEqual(sm_mod.LED_DEFAULT_DROP_IMPACT_BEATS, 8.0)
        self.lc = DropLifecycle(_cfg(
            impact_beats=sm_mod.LED_DEFAULT_DROP_IMPACT_BEATS,
            max_drops=sm_mod.LED_MAX_DROP_IMPACTS,
        ))

        # Construct a minimal StateManager to drive the REAL LED resolver
        # (_led_role_from_smart_phrasing reads the module-level constants above —
        # NOT instance attributes, so do not try to override them on self.sm).
        from rb_ss_bridge_v2.state_manager import StateManager
        from rb_ss_bridge_v2.rb_memory import PositionCache
        from unittest.mock import Mock
        import queue

        self.sm = StateManager(queue.Queue(), PositionCache(), Mock())

    def assertParity(self, sp, msg="") -> None:
        from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState
        # Convert SimpleNamespace to SmartPhrasingState since StateManager requires it
        if isinstance(sp, types.SimpleNamespace):
            sp_kwargs = {k: v for k, v in sp.__dict__.items() if not k.startswith('_')}
            sp_state = SmartPhrasingState(**sp_kwargs)
        else:
            sp_state = sp

        res = self.lc.resolve(sp, mutate=True)
        led_role = self.sm._led_role_from_smart_phrasing(sp_state, mutate=True)

        # Map LED non-drop roles to 'none'
        if led_role in ("breakdown", "pre_drop", "buildup", "low", "groove"):
            led_role = "none"

        self.assertEqual(res.role, led_role, f"{msg}: pure={res.role}, led={led_role}")

    def test_parity_allowed_predecessor_flow(self) -> None:
        """Allowed-predecessor drop -> hold(impact=8) -> post_drop"""
        sp1 = _sp(smart_drop_crossing=True, active_drop_beat=64.0, previous_phrase_label="up", current_phrase_is_chorus=True, abs_beat=64.0)
        self.assertParity(sp1, "Allowed cross")

        sp2 = _sp(current_phrase_is_chorus=True, smart_post_drop_active=True, abs_beat=68.0)
        self.assertParity(sp2, "Hold impact")

        sp3 = _sp(current_phrase_is_chorus=True, smart_post_drop_active=True, abs_beat=80.0)
        self.assertParity(sp3, "Post drop")

    def test_parity_real_crossing_after_groove_flow(self) -> None:
        """Real smart-drop crossing after groove -> drop"""
        sp1 = _sp(smart_drop_crossing=True, active_drop_beat=300.0, previous_phrase_label="groove", abs_beat=300.0, current_phrase_is_chorus=True)
        self.assertParity(sp1, "Groove-to-crossing drop")

    def test_parity_repeated_real_crossings_after_chorus_still_fire(self) -> None:
        """Real crossings still fire after a long chorus stretch."""
        sp1 = _sp(smart_drop_crossing=True, active_drop_beat=500.0, previous_phrase_label="up", abs_beat=500.0, current_phrase_is_chorus=True)
        self.assertParity(sp1, "Chorus 1")

        sp2 = _sp(smart_drop_crossing=True, active_drop_beat=600.0, previous_phrase_label="chorus", abs_beat=600.0, current_phrase_is_chorus=True)
        self.assertParity(sp2, "Chorus 2")

        sp3 = _sp(smart_drop_crossing=True, active_drop_beat=700.0, previous_phrase_label="chorus", abs_beat=700.0, current_phrase_is_chorus=True)
        self.assertParity(sp3, "Chorus 3")

    def test_parity_lifecycle_clear(self) -> None:
        """Lifecycle clears when leaving chorus/post_drop"""
        sp1 = _sp(smart_drop_crossing=True, active_drop_beat=64.0, previous_phrase_label="up", current_phrase_is_chorus=True, abs_beat=64.0)
        self.assertParity(sp1, "Allowed cross")

        sp2 = _sp(abs_beat=200.0, current_phrase_label="other")
        self.assertParity(sp2, "Clear leaving")

    def test_parity_two_hit_chorus_cap_sequence(self) -> None:
        from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState

        sequence = [
            _sp(smart_drop_crossing=True, active_drop_beat=64.0, previous_phrase_label="up", current_phrase_is_chorus=True, current_phrase_start_beat=64.0, phrase_start_crossing=True, abs_beat=64.0),
            _sp(previous_phrase_label="chorus", current_phrase_is_chorus=True, current_phrase_start_beat=96.0, phrase_start_crossing=True, abs_beat=96.0),
            _sp(previous_phrase_label="chorus", current_phrase_is_chorus=True, current_phrase_start_beat=128.0, phrase_start_crossing=True, abs_beat=128.0),
            _sp(previous_phrase_label="chorus", current_phrase_is_chorus=True, current_phrase_start_beat=160.0, phrase_start_crossing=True, abs_beat=160.0),
        ]
        laser_roles = []
        led_roles = []

        for sp in sequence:
            laser_roles.append(self.lc.resolve(sp, mutate=True).role)
            sp_state = SmartPhrasingState(**sp.__dict__)
            role = self.sm._led_role_from_smart_phrasing(sp_state, mutate=True)
            led_roles.append("none" if role in ("breakdown", "pre_drop", "buildup", "low", "groove") else role)

        self.assertEqual(laser_roles, ["drop", "drop", "post_drop", "post_drop"])
        self.assertEqual(led_roles, laser_roles)


class TestResolveMutateFalse(unittest.TestCase):
    def test_breakdown_start_crossing_yields_post_drop(self) -> None:
        """breakdown_start_crossing + smart_post_drop_active returns post_drop without mutation."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        # Arm a lifecycle first so the chorus window is active
        lc._first_drop_anchor_beat = 64.0
        lc._impact_until_beat = 72.0
        lc._impact_count = 1
        sp = _sp(
            current_phrase_is_chorus=True,
            smart_post_drop_active=True,
            abs_beat=80.0,
        )
        res = lc.resolve(sp, mutate=False)
        self.assertEqual(res.role, "post_drop")

    def test_transition_window_active_yields_post_drop(self) -> None:
        """transition_window_active returns post_drop without mutation."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        lc._first_drop_anchor_beat = 64.0
        lc._impact_until_beat = 72.0
        lc._impact_count = 1
        sp = _sp(
            current_phrase_is_chorus=True,
            abs_beat=80.0,
        )
        res = lc.resolve(sp, mutate=False)
        self.assertEqual(res.role, "post_drop")


if __name__ == "__main__":
    unittest.main()
