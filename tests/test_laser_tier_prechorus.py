"""AWR-170 pure-seam tests: per-tier chase divisions (B) + pre-chorus laser
blackout (D.2).

All seams are pure functions / in-memory state machines — no disk, no subprocess,
no bridge, no MIDI. Covers: the color-map parser (int unchanged, per-tier dict
resolution + fallbacks + junk fail-closed), the tier-aware CH8 selection, the
smart_phrasing pre-chorus window edges (incl. the collapsed-marker + F2-off cases),
the F2Config schema (absent=0 mirror rule / example ships 4), and the smart_rearm
"pre_chorus" mask owner (arm/release/leaked-window/overlap/cleanup — the AWR-154
latched-dark guard) plus the Part C held-static-ducks-dark behavior.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_color_engine import (  # noqa: E402
    LaserColorEngine,
    LaserColorMap,
    _parse_menus,
    _resolve_chase_tiers,
    _resolve_tier_ch8,
)
from rb_ss_bridge_v2.laser_config import LaserConfig  # noqa: E402
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor  # noqa: E402
from rb_ss_bridge_v2.led_config import load_f2_config  # noqa: E402
from rb_ss_bridge_v2.led_models import F2Config  # noqa: E402
from rb_ss_bridge_v2.models import DeckState, OutputState  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    PhraseSegment,
    SmartPhrasingEngine,
    SmartPhrasingSnapshot,
    SmartPhrasingState,
)
from rb_ss_bridge_v2.smart_rearm import (  # noqa: E402
    SmartRearmContext,
    SmartRearmCoordinator,
)

_EXAMPLE_CONFIG = str(
    Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"
)


# --------------------------------------------------------------------------- #
# Task 2/1: parser + per-tier resolution                                       #
# --------------------------------------------------------------------------- #
class ParserTests(unittest.TestCase):
    def test_int_chase_is_byte_identical(self) -> None:
        # A single-int chase parses to the EXACT pre-AWR-170 tuple shape.
        menus = _parse_menus({"m": ["red", {"chase": 172, "colors": ["blue", "cyan"]}]})
        self.assertEqual(
            menus["m"], (("solid", "red"), ("chase", 172, ("blue", "cyan")))
        )

    def test_dict_chase_parses_to_tiered_entry(self) -> None:
        menus = _parse_menus(
            {
                "c": [
                    "red",
                    "white",
                    {
                        "chase": {"standard": 100, "intense": 116, "monster": 140},
                        "colors": ["red", "white"],
                    },
                ]
            }
        )
        self.assertEqual(
            menus["c"][2],
            ("chase_tiered", {"standard": 100, "intense": 116, "monster": 140},
             ("red", "white")),
        )

    def test_missing_keys_fall_back_to_standard(self) -> None:
        self.assertEqual(
            _resolve_chase_tiers({"standard": 100}),
            {"standard": 100, "intense": 100, "monster": 100},
        )

    def test_missing_standard_falls_back_to_first_present(self) -> None:
        self.assertEqual(
            _resolve_chase_tiers({"intense": 116, "monster": 140}),
            {"standard": 116, "intense": 116, "monster": 140},
        )

    def test_all_junk_per_tier_fails_closed(self) -> None:
        # No valid byte anywhere -> None -> caller skips the entry (never invents).
        self.assertIsNone(_resolve_chase_tiers({"standard": "x", "intense": None}))
        self.assertIsNone(_resolve_chase_tiers({"bogus": 300}))
        # A mood whose only chase is junk (and no other entry) is omitted entirely.
        self.assertFalse(
            _parse_menus({"j": [{"chase": {"standard": "x"}, "colors": ["red"]}]})
        )

    def test_out_of_range_tier_value_dropped_others_kept(self) -> None:
        # 300 is out of 0-255 -> dropped; the valid tiers still resolve.
        self.assertEqual(
            _resolve_chase_tiers({"standard": 100, "intense": 300, "monster": 140}),
            {"standard": 100, "intense": 100, "monster": 140},
        )


# --------------------------------------------------------------------------- #
# Task 2/3: tier-aware CH8 selection at a drop                                  #
# --------------------------------------------------------------------------- #
def _tiered_map() -> LaserColorMap:
    return LaserColorMap.from_dict(
        {
            "enabled": True,
            "fixed": {"red": 10, "white": 70},
            "fixed_ch9": 90,
            "menus": {
                "crimson": [
                    "red",
                    "white",
                    {
                        "chase": {"standard": 100, "intense": 116, "monster": 140},
                        "colors": ["red", "white"],
                    },
                ],
            },
        }
    )


def _snap_ch8(tier):
    engine = LaserColorEngine(_tiered_map())
    engine.update(
        {"palette": "crimson", "live_rgb": (255, 0, 0)},
        white_moment=False,
        drop_phase="drop",
        post_drop_progress=None,
        tier=tier,
    )
    snap = engine.snapshot()
    return None if snap is None else snap.ch8


class TierSelectionTests(unittest.TestCase):
    def test_per_tier_ch8_at_a_drop(self) -> None:
        self.assertEqual(_snap_ch8("standard"), 100)
        self.assertEqual(_snap_ch8("intense"), 116)
        self.assertEqual(_snap_ch8("monster"), 140)

    def test_none_and_unknown_tier_resolve_to_standard(self) -> None:
        # None / small (LEDS-only tier) / junk all fall to standard == today's value.
        self.assertEqual(_snap_ch8(None), 100)
        self.assertEqual(_snap_ch8("small"), 100)
        self.assertEqual(_snap_ch8("bogus"), 100)

    def test_resolve_tier_ch8_helper(self) -> None:
        tiers = {"standard": 100, "intense": 116, "monster": 140}
        self.assertEqual(_resolve_tier_ch8(tiers, "monster"), 140)
        self.assertEqual(_resolve_tier_ch8(tiers, None), 100)

    def test_single_value_menu_ignores_tier(self) -> None:
        # A non-tiered chase menu renders its single value at every tier.
        engine = LaserColorEngine(
            LaserColorMap.from_dict(
                {
                    "enabled": True,
                    "fixed": {"blue": 30, "cyan": 40},
                    "fixed_ch9": 90,
                    "menus": {"bc": [{"chase": 172, "colors": ["blue", "cyan"]}]},
                }
            )
        )
        for tier in (None, "standard", "monster"):
            engine.update(
                {"palette": "bc", "live_rgb": (0, 0, 255)},
                white_moment=False, drop_phase="drop", post_drop_progress=None, tier=tier,
            )
            self.assertEqual(engine.snapshot().ch8, 172)


# --------------------------------------------------------------------------- #
# Task 4: pre-chorus window (smart_phrasing)                                    #
# --------------------------------------------------------------------------- #
def _chorus_segments(*starts) -> tuple[PhraseSegment, ...]:
    segs = []
    for s in starts:
        segs.append(PhraseSegment(start_beat=float(s), end_beat=float(s) + 16.0, label="chorus"))
    return tuple(segs)


def _phr_snap(abs_beat, segments, pre_chorus_beats) -> SmartPhrasingSnapshot:
    return SmartPhrasingSnapshot(
        deck_id="1",
        track_id="t",
        is_playing=True,
        abs_beat=float(abs_beat),
        phrase_segments=segments,
        smart_drop_beats=(),
        breakdown_segments=(),
        phrase_lookahead_beats=32.0,
        drop_window_beats=8.0,
        post_drop_beats=16.0,
        transition_window_beats=8.0,
        pre_chorus_beats=float(pre_chorus_beats),
    )


def _run(engine, beats, segments, pre_chorus_beats):
    """Drive the engine tick-by-tick; return the state list."""
    states = []
    for b in beats:
        res = engine.update(_phr_snap(b, segments, pre_chorus_beats))
        states.append(res.state)
    return states


class PreChorusWindowTests(unittest.TestCase):
    def test_arm_is_a_rising_edge_release_at_marker(self) -> None:
        eng = SmartPhrasingEngine()
        # marker at 100, window = 4 beats (96..99].
        states = _run(eng, [90, 96, 97, 98, 100, 101], _chorus_segments(100), 4)
        arms = [s.pre_chorus_mask_should_arm for s in states]
        active = [s.pre_chorus_window_active for s in states]
        clears = [s.pre_chorus_mask_should_clear for s in states]
        # 90 outside; 96 arms (first active), 97/98 held (no re-arm); 100 releases.
        self.assertEqual(active, [False, True, True, True, False, False])
        self.assertEqual(arms, [False, True, False, False, False, False])
        self.assertEqual(clears, [False, False, False, False, True, False])

    def test_collapsed_markers_each_get_a_window(self) -> None:
        # Two chorus markers 32 beats apart INSIDE one drop section: the AWR-131
        # drop-decision collapse never touched the phrase data, so the SECOND
        # marker still earns its own 4-beat pre-chorus window.
        eng = SmartPhrasingEngine()
        states = _run(
            eng, [96, 100, 116, 128, 132], _chorus_segments(100, 132), 4
        )
        active = {b: s.pre_chorus_window_active for b, s in zip([96, 100, 116, 128, 132], states)}
        self.assertTrue(active[96])    # window before first marker
        self.assertFalse(active[100])  # released at first marker
        self.assertFalse(active[116])  # mid-section, no window
        self.assertTrue(active[128])   # window before SECOND marker
        self.assertFalse(active[132])  # released at second marker

    def test_zero_beats_never_arms(self) -> None:
        # pre_chorus_beats == 0 (absent-key / F2-off gate) -> no window ever.
        eng = SmartPhrasingEngine()
        states = _run(eng, [96, 97, 98, 99], _chorus_segments(100), 0)
        self.assertFalse(any(s.pre_chorus_window_active for s in states))
        self.assertFalse(any(s.pre_chorus_mask_should_arm for s in states))

    def test_no_chorus_segments_no_window(self) -> None:
        eng = SmartPhrasingEngine()
        segs = (PhraseSegment(start_beat=100.0, end_beat=132.0, label="up"),)
        states = _run(eng, [96, 97, 98], segs, 4)
        self.assertFalse(any(s.pre_chorus_window_active for s in states))


# --------------------------------------------------------------------------- #
# Task 4: config schema (F2Config)                                             #
# --------------------------------------------------------------------------- #
class PreChorusConfigTests(unittest.TestCase):
    def test_absent_key_is_zero_mirror_rule(self) -> None:
        self.assertEqual(F2Config.from_dict({"enabled": True}).pre_chorus_laser_beats, 0)

    def test_junk_and_negative_clamp_to_zero(self) -> None:
        self.assertEqual(F2Config.from_dict({"pre_chorus_laser_beats": "x"}).pre_chorus_laser_beats, 0)
        self.assertEqual(F2Config.from_dict({"pre_chorus_laser_beats": -5}).pre_chorus_laser_beats, 0)

    def test_example_config_ships_four(self) -> None:
        self.assertEqual(load_f2_config(_EXAMPLE_CONFIG).pre_chorus_laser_beats, 4)


# --------------------------------------------------------------------------- #
# Task 4: pre_chorus mask owner (smart_rearm) — the AWR-154 latched-dark guard  #
# --------------------------------------------------------------------------- #
def _executor() -> LaserSceneExecutor:
    cfg = LaserConfig(
        enabled=True, dry_run=True, smart_drop_mode="blackout_mask",
        midi_output_port="", scenes={}, personalities={}, default_personality="",
        startup_scene="", stop_scene="", stale_scene="", emergency_scene="",
        fallback_scene="",
    )
    return LaserSceneExecutor(config=cfg, backend=Mock(), personality=None)


def _coord(ex, os):
    return SmartRearmCoordinator(
        output_state_ref=lambda: os,
        deck_ref=lambda n: DeckState(number=n),
        send_direct_autoloop_rearm=Mock(return_value=True),
        send_smart_transition_clear=Mock(),
        hold_blackout_mask=ex.hold_blackout_mask,
        release_blackout_mask=ex.release_blackout_mask,
    )


def _ctx() -> SmartRearmContext:
    # Only _pre_chorus runs: the other three sub-ticks are disabled.
    return SmartRearmContext(
        mirror=2, bpm=130.0, this_beat=0, elapsed_ms=0, abs_beat_pos=0.0,
        blackout_mode=True, smart_drop_enabled=False, smart_breakdown_enabled=False,
        phrase_anchor_enabled=False, lighting_mode_is_autoloop=True,
    )


def _pc_state(*, arm=False, active=False, clear=False) -> SmartPhrasingState:
    return SmartPhrasingState(
        pre_chorus_mask_should_arm=arm,
        pre_chorus_window_active=active,
        pre_chorus_mask_should_clear=clear,
    )


class PreChorusMaskTests(unittest.TestCase):
    def test_arm_holds_release_at_marker(self) -> None:
        ex, os = _executor(), OutputState(lighting_mode="autoloop")
        coord = _coord(ex, os)
        # Arm (rising edge): the mask goes dark and the latch is set.
        coord.tick(1, _pc_state(arm=True, active=True), _ctx())
        self.assertTrue(ex.mask_owners_active())
        self.assertTrue(os.pre_chorus_active)
        # Held (window still active, no re-arm): stays dark.
        coord.tick(1, _pc_state(arm=False, active=True), _ctx())
        self.assertTrue(ex.mask_owners_active())
        # Marker crossing (window inactive + clear edge): releases.
        coord.tick(1, _pc_state(active=False, clear=True), _ctx())
        self.assertFalse(ex.mask_owners_active())
        self.assertFalse(os.pre_chorus_active)

    def test_leaked_window_releases_without_clean_crossing(self) -> None:
        # Scrub/loop/skip out of the window (window inactive, NO clean clear edge)
        # still releases — a leaked owner would latch the lasers dark forever.
        ex, os = _executor(), OutputState(lighting_mode="autoloop")
        coord = _coord(ex, os)
        coord.tick(1, _pc_state(arm=True, active=True), _ctx())
        self.assertTrue(ex.mask_owners_active())
        coord.tick(1, _pc_state(active=False, clear=False), _ctx())
        self.assertFalse(ex.mask_owners_active())
        self.assertFalse(os.pre_chorus_active)

    def test_overlap_with_breakdown_owner_set_holds_both(self) -> None:
        # A chorus landing inside a breakdown/F2 window just adds a SECOND owner;
        # releasing pre_chorus must NOT un-dark while breakdown still holds.
        ex, os = _executor(), OutputState(lighting_mode="autoloop")
        coord = _coord(ex, os)
        ex.hold_blackout_mask("breakdown")
        coord.tick(1, _pc_state(arm=True, active=True), _ctx())
        self.assertTrue(ex.mask_owners_active())
        # pre_chorus window ends; breakdown still holds -> still dark.
        coord.tick(1, _pc_state(active=False, clear=True), _ctx())
        self.assertTrue(ex.mask_owners_active())
        self.assertFalse(os.pre_chorus_active)
        # And breakdown releasing separately clears the last owner.
        ex.release_blackout_mask("breakdown")
        self.assertFalse(ex.mask_owners_active())

    def test_reset_path_releases_pre_chorus(self) -> None:
        # clear_pending_blackout() (the shared reset entry used by track/deck/
        # scripted/transport/stop resets via _release_all_masks) drops the owner.
        ex, os = _executor(), OutputState(lighting_mode="autoloop")
        coord = _coord(ex, os)
        coord.tick(1, _pc_state(arm=True, active=True), _ctx())
        self.assertTrue(ex.mask_owners_active())
        ex.clear_pending_blackout(reason="track_change")
        self.assertFalse(ex.mask_owners_active())

    def test_not_autoloop_mode_does_not_arm(self) -> None:
        ex, os = _executor(), OutputState(lighting_mode="scripted")
        coord = _coord(ex, os)
        ctx = SmartRearmContext(
            mirror=2, bpm=130.0, this_beat=0, elapsed_ms=0, abs_beat_pos=0.0,
            blackout_mode=True, smart_drop_enabled=False, smart_breakdown_enabled=False,
            phrase_anchor_enabled=False, lighting_mode_is_autoloop=False,
        )
        coord.tick(1, _pc_state(arm=True, active=True), ctx)
        self.assertFalse(ex.mask_owners_active())


if __name__ == "__main__":
    unittest.main()
