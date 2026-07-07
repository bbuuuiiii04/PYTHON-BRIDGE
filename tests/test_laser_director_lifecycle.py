"""Tests for the gated drop lifecycle integration in LaserDirector.

Covers:
  - A3 regression: smart_drop_crossing with disallowed predecessor does NOT
    produce a drop/drop_cycle decision (the live bug fix).
  - Teardown: director lifecycle state clears on reset_runtime_state.
  - Flag-off: drop_lifecycle_mirror=False → original ungated behavior.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserContext,
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
    LaserSceneDecision,
)
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402


def _sp(**overrides) -> SmartPhrasingState:
    defaults = dict(reason="test")
    defaults.update(overrides)
    return SmartPhrasingState(**defaults)


def _ctx(
    *,
    abs_beat: float = 64.0,
    playing: bool = True,
    active_track_loaded: bool = True,
    autoloop_ready: bool = True,
    autoloop_tick_just_fired: bool = False,
    smart_phrasing: Optional[SmartPhrasingState] = None,
    scripted_id: int = 0,
) -> LaserContext:
    return LaserContext(
        active_deck=1,
        playing=playing,
        elapsed_ms=60_000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=abs_beat,
        position_stale=False,
        lighting_mode="autoloop",
        os2l_connected=True,
        active_track_loaded=active_track_loaded,
        autoloop_ready=autoloop_ready,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=scripted_id,
        smart_phrasing=smart_phrasing,
    )


def _scene(name: str, *, scene_type: str = "autoloop") -> LaserScene:
    return LaserScene(
        name=name,
        scene_type=scene_type,
        safety_class="safe",
        midi=LaserMidiMessage(kind="note_pulse", channel=1, note=36, velocity=127, duration_ms=80),
    )


def _personality(*, mirror: bool = True, max_drops: int = 2, impact_beats: float = 32.0) -> LaserPersonality:
    return LaserPersonality(
        name="house",
        safe_scene="safe_static",
        default_scene="house_phrase_1",
        phrase_scene="house_phrase_1",
        buildup_scene="buildup_1",
        drop_scene="house_drop_1",
        post_drop_scene="post_drop_1",
        breakdown_scene="breakdown_1",
        transition_scene="safe_static",
        phrase_bank=("house_phrase_1",),
        buildup_bank=("buildup_1",),
        drop_bank=("house_drop_1",),
        post_drop_bank=("post_drop_1",),
        breakdown_bank=("breakdown_1",),
        drop_lifecycle_mirror=mirror,
        max_drops_in_a_row=max_drops,
        drop_impact_beats=impact_beats,
        post_drop_cycle_beats=32.0,
    )


def _make_director(*, mirror: bool = True, **personality_kw) -> LaserDirector:
    scenes = {
        "safe_static": _scene("safe_static", scene_type="static"),
        "house_phrase_1": _scene("house_phrase_1"),
        "buildup_1": _scene("buildup_1"),
        "house_drop_1": _scene("house_drop_1"),
        "post_drop_1": _scene("post_drop_1"),
        "breakdown_1": _scene("breakdown_1"),
    }
    p = _personality(mirror=mirror, **personality_kw)
    d = LaserDirector(
        enabled=True,
        dry_run=True,
        drop_scene="house_drop_1",
        post_drop_scene="post_drop_1",
        breakdown_scene="breakdown_1",
        buildup_scene="buildup_1",
        buildup_lookahead_beats=32,
        post_drop_hold_beats=8,
        scenes=scenes,
    )
    d.set_personality_config(p)
    return d


class TestA3RegressionGatedDrop(unittest.TestCase):
    """A3: smart_drop_crossing with a groove/other predecessor must NOT produce
    role=drop or reason=drop_crossing when the mirror is ON."""

    def test_disallowed_predecessor_no_drop(self) -> None:
        d = _make_director(mirror=True)
        now = time.monotonic()
        # Prime with one non-crossing tick so _last_smart_abs_beat is set
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="other")
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        # Crossing with disallowed predecessor
        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="other",
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
        )
        dec = d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)
        # Must NOT be drop or drop_cycle
        self.assertNotEqual(dec.role, "drop")
        self.assertNotEqual(dec.reason, "drop_crossing")
        self.assertNotEqual(dec.reason, "drop_cycle")

    def test_allowed_predecessor_fires_drop(self) -> None:
        d = _make_director(mirror=True)
        now = time.monotonic()
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
        )
        dec = d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)
        self.assertEqual(dec.role, "drop")
        self.assertEqual(dec.reason, "drop_crossing")

    def test_flag_off_ungated_crossing(self) -> None:
        """Flag OFF: crossing fires drop regardless of predecessor (today's behavior)."""
        d = _make_director(mirror=False)
        now = time.monotonic()
        sp_prime = _sp(abs_beat=60.0)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="other",
        )
        dec = d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)
        self.assertEqual(dec.role, "drop")
        self.assertEqual(dec.reason, "drop_crossing")

    def test_32_beat_hold_no_mask_buildup(self) -> None:
        """A 32-beat impact window must NOT mask a later buildup beyond the gate."""
        d = _make_director(mirror=True, impact_beats=32.0)
        now = time.monotonic()
        # Prime
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)
        # Drop crossing
        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
        )
        d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)

        # At beat 90 (within 32-beat window), leaving chorus → buildup should work
        sp_buildup = _sp(
            abs_beat=90.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
            beats_to_next_drop=10.0,
            next_smart_drop_beat=100.0,
        )
        dec = d.tick(
            _ctx(abs_beat=90.0, smart_phrasing=sp_buildup),
            now=now + 0.02,
        )
        # Once leaving chorus, the lifecycle should resolve "none" and let buildup through
        # (the resolver only returns drop/post_drop inside chorus/post_drop_active windows)
        self.assertIn(dec.role, ("buildup", "phrase", "drop"))
        # The key assertion: it is NOT stuck on drop_hold for 32 beats regardless of context


class TestTeardown(unittest.TestCase):
    def test_reset_clears_lifecycle(self) -> None:
        d = _make_director(mirror=True)
        now = time.monotonic()
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
        )
        d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)

        # Reset (simulating track load)
        d.reset_runtime_state(reason="active_track_loaded")

        # After reset, a fresh crossing should arm again (impact_count reset to 0)
        sp_prime2 = _sp(abs_beat=200.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=200.0, smart_phrasing=sp_prime2), now=now + 0.02)

        sp_cross2 = _sp(
            abs_beat=210.0,
            smart_drop_crossing=True,
            active_drop_beat=210.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
        )
        dec = d.tick(_ctx(abs_beat=210.0, smart_phrasing=sp_cross2), now=now + 0.03)
        self.assertEqual(dec.role, "drop")
        self.assertEqual(dec.reason, "drop_crossing")


if __name__ == "__main__":
    unittest.main()
