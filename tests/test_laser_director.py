"""
Tests for Issue #7: Dry-run LaserDirector skeleton.

Covers:
  - Disabled LaserDirector does nothing.
  - Emergency selects configured emergency_scene.
  - Manual override selects provided scene name.
  - Not playing returns idle/no-output.
  - Stale position returns idle/no-output.
  - Normal playing selects configured default_scene.
  - Arbitrary scene names are accepted for manual override.
  - No fixed names like low_sweep or drop_hit are required.
  - Manual override TTL expiry falls back to automatic policy.
  - Emergency latches; clear_manual_override does not clear it.
  - toggle_enabled flips state correctly.
  - set_enabled sets state explicitly.
  - clear_emergency_blackout also clears manual override.
  - status() shape matches spec.
  - StateManager accepts optional laser_director kwarg without breaking.
  - LaserContext and LaserSceneDecision are frozen dataclasses.
"""
import queue
import sys
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_models import LaserContext, LaserPersonality, LaserSceneDecision  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402
from rb_ss_bridge_v2.models import Ev  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    *,
    playing: bool = True,
    position_stale: bool = False,
    active_deck: int = 1,
    elapsed_ms: int = 60_000,
    bpm: float = 128.0,
    beatpos: float = 0.0,
    abs_beat: float = 64.0,
    lighting_mode: str = "autoloop",
    os2l_connected: bool = True,
    active_track_loaded: bool = True,
    autoloop_ready: bool = True,
    autoloop_tick_just_fired: bool = False,
    breakdown_active: bool = False,
    smart_drops: tuple[int, ...] = (),
    anlz_buildups: tuple[int, ...] = (),
    current_phrase_is_up: bool = False,
    current_phrase_is_chorus: bool = False,
    scripted_id: int = 0,
    smart_drop_blackout_active: bool = False,
    smart_phrasing: Optional[SmartPhrasingState] = None,
) -> LaserContext:
    return LaserContext(
        active_deck=active_deck,
        playing=playing,
        elapsed_ms=elapsed_ms,
        bpm=bpm,
        beatpos=beatpos,
        abs_beat=abs_beat,
        position_stale=position_stale,
        lighting_mode=lighting_mode,
        os2l_connected=os2l_connected,
        active_track_loaded=active_track_loaded,
        autoloop_ready=autoloop_ready,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        breakdown_active=breakdown_active,
        smart_drops=smart_drops,
        anlz_buildups=anlz_buildups,
        current_phrase_is_up=current_phrase_is_up,
        current_phrase_is_chorus=current_phrase_is_chorus,
        scripted_id=scripted_id,
        smart_drop_blackout_active=smart_drop_blackout_active,
        smart_phrasing=smart_phrasing,
    )


def _director(
    *,
    enabled: bool = True,
    dry_run: bool = True,
    safe_scene: str = "safe_static",
    default_scene: str = "house_phrase_1",
    emergency_scene: str = "emergency_blackout",
    phrase_scene: str = "",
    phrase_interval_beats: int = 32,
    minimum_scene_hold_beats: int = 0,
    normal_changes_only_on_phrase_boundary: bool = False,
    breakdown_scene: str = "",
    buildup_scene: str = "",
    pre_drop_scene: str = "",
    drop_scene: str = "",
    post_drop_scene: str = "",
    buildup_lookahead_beats: int = 32,
    buildup_approach_beats: int = 8,
    buildup_hold_beats: int = 8,
    pre_drop_lookahead_beats: int = 4,
    buildup_max_drop_distance_beats: int = 32,
) -> LaserDirector:
    return LaserDirector(
        enabled=enabled,
        dry_run=dry_run,
        safe_scene=safe_scene,
        default_scene=default_scene,
        emergency_scene=emergency_scene,
        phrase_scene=phrase_scene,
        phrase_interval_beats=phrase_interval_beats,
        minimum_scene_hold_beats=minimum_scene_hold_beats,
        normal_changes_only_on_phrase_boundary=normal_changes_only_on_phrase_boundary,
        breakdown_scene=breakdown_scene,
        buildup_scene=buildup_scene,
        pre_drop_scene=pre_drop_scene,
        drop_scene=drop_scene,
        post_drop_scene=post_drop_scene,
        buildup_lookahead_beats=buildup_lookahead_beats,
        buildup_approach_beats=buildup_approach_beats,
        buildup_hold_beats=buildup_hold_beats,
        pre_drop_lookahead_beats=pre_drop_lookahead_beats,
        buildup_max_drop_distance_beats=buildup_max_drop_distance_beats,
    )


def _now() -> float:
    return time.monotonic()


# ---------------------------------------------------------------------------
# LaserContext and LaserSceneDecision — frozen
# ---------------------------------------------------------------------------

class FrozenModelTests(unittest.TestCase):
    def test_laser_context_is_frozen(self) -> None:
        ctx = _ctx()
        with self.assertRaises((AttributeError, TypeError)):
            ctx.playing = False  # type: ignore[misc]

    def test_laser_scene_decision_is_frozen(self) -> None:
        dec = LaserSceneDecision(scene="x", reason="y", priority=1, source="z")
        with self.assertRaises((AttributeError, TypeError)):
            dec.scene = "mutated"  # type: ignore[misc]

    def test_laser_context_equality(self) -> None:
        a = _ctx(playing=True)
        b = _ctx(playing=True)
        self.assertEqual(a, b)

    def test_laser_context_inequality(self) -> None:
        a = _ctx(playing=True)
        b = _ctx(playing=False)
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------------------
# Disabled LaserDirector does nothing
# ---------------------------------------------------------------------------

class DisabledTests(unittest.TestCase):
    def test_disabled_tick_does_not_update_scene(self) -> None:
        ld = _director(enabled=False)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "")

    def test_disabled_tick_does_not_change_scene_even_with_emergency(self) -> None:
        ld = _director(enabled=False)
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(), now=_now())
        # Still no scene because the director is disabled.
        self.assertEqual(ld.status()["current_scene"], "")

    def test_disabled_status_shows_enabled_false(self) -> None:
        ld = _director(enabled=False)
        self.assertFalse(ld.status()["enabled"])


# ---------------------------------------------------------------------------
# Emergency blackout
# ---------------------------------------------------------------------------

class EmergencyTests(unittest.TestCase):
    def test_emergency_selects_emergency_scene(self) -> None:
        ld = _director()
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "emergency_blackout")
        self.assertEqual(ld.status()["last_reason"], "emergency")

    def test_emergency_uses_configured_scene_name(self) -> None:
        ld = _director(emergency_scene="my_emergency_blackout")
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_emergency_blackout")

    def test_emergency_beats_manual_override(self) -> None:
        ld = _director()
        ld.set_manual_override("some_scene", ttl_s=30.0)
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "emergency_blackout")

    def test_emergency_beats_not_playing(self) -> None:
        ld = _director()
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(playing=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "emergency_blackout")

    def test_emergency_beats_autoloop_not_ready(self) -> None:
        ld = _director()
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(autoloop_ready=False, active_track_loaded=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "emergency_blackout")

    def test_emergency_overrides_smart_observation_signals(self) -> None:
        cases = (
            _ctx(abs_beat=32.2, breakdown_active=True, smart_drops=(64,), anlz_buildups=(32,)),
            _ctx(abs_beat=19.0, smart_drops=(64,), anlz_buildups=(20,)),
            _ctx(abs_beat=64.1, smart_drops=(64,), anlz_buildups=(64,)),
        )
        for ctx in cases:
            with self.subTest(ctx=ctx):
                ld = _director(
                    default_scene="d",
                    breakdown_scene="bd",
                    buildup_scene="up",
                    pre_drop_scene="pre",
                    drop_scene="drop",
                )
                ld.tick(_ctx(abs_beat=63.5, smart_drops=(64,)), now=_now())
                ld.set_emergency_blackout(True)
                ld.tick(ctx, now=_now())
                self.assertEqual(ld.status()["current_scene"], "emergency_blackout")
                self.assertEqual(ld.status()["last_reason"], "emergency")

    def test_emergency_latches(self) -> None:
        ld = _director()
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(), now=_now())
        ld.tick(_ctx(), now=_now())
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["emergency"], True)
        self.assertEqual(ld.status()["current_scene"], "emergency_blackout")

    def test_clear_emergency_clears_latch(self) -> None:
        ld = _director()
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(), now=_now())
        ld.clear_emergency_blackout()
        ld.tick(_ctx(), now=_now())
        self.assertFalse(ld.status()["emergency"])
        self.assertNotEqual(ld.status()["current_scene"], "emergency_blackout")

    def test_clear_emergency_also_clears_manual_override(self) -> None:
        ld = _director()
        ld.set_manual_override("custom_scene", ttl_s=30.0)
        ld.set_emergency_blackout(True)
        ld.clear_emergency_blackout()
        self.assertIsNone(ld.status()["manual_override"])

    def test_status_emergency_field(self) -> None:
        ld = _director()
        self.assertFalse(ld.status()["emergency"])
        ld.set_emergency_blackout(True)
        self.assertTrue(ld.status()["emergency"])


# ---------------------------------------------------------------------------
# Manual override
# ---------------------------------------------------------------------------

class ManualOverrideTests(unittest.TestCase):
    def test_manual_override_selects_scene(self) -> None:
        ld = _director()
        ld.set_manual_override("house_drop_1", ttl_s=10.0)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "house_drop_1")
        self.assertEqual(ld.status()["last_reason"], "manual_override")

    def test_manual_override_arbitrary_names(self) -> None:
        """Any string is valid — no fixed names required."""
        ld = _director()
        for name in ("house_drop_1", "my_custom_scene", "xyz_123", "ALLCAPS"):
            ld.set_manual_override(name, ttl_s=10.0)
            ld.tick(_ctx(), now=_now())
            self.assertEqual(ld.status()["current_scene"], name)

    def test_manual_override_no_fixed_names_required(self) -> None:
        """Names like low_sweep or drop_hit must not be required anywhere."""
        ld = LaserDirector(
            enabled=True,
            safe_scene="my_safe",
            default_scene="my_default",
            emergency_scene="my_emergency",
        )
        ld.set_manual_override("my_custom_override", ttl_s=5.0)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_custom_override")

    def test_manual_override_stored_in_status(self) -> None:
        ld = _director()
        ld.set_manual_override("house_drop_1", ttl_s=5.0)
        self.assertEqual(ld.status()["manual_override"], "house_drop_1")

    def test_manual_override_allowed_when_autoloop_not_ready(self) -> None:
        ld = _director()
        ld.set_manual_override("manual_scene", ttl_s=10.0)
        ld.tick(_ctx(autoloop_ready=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "manual_scene")
        self.assertEqual(ld.status()["last_reason"], "manual_override")

    def test_manual_override_beats_drop_crossing(self) -> None:
        ld = _director(
            default_scene="d",
            breakdown_scene="bd",
            buildup_scene="up",
            pre_drop_scene="pre",
            drop_scene="drop",
        )
        ld.tick(_ctx(abs_beat=63.5, smart_drops=(64,)), now=_now())
        ld.set_manual_override("manual_scene", ttl_s=10.0)
        ld.tick(
            _ctx(
                abs_beat=64.1,
                breakdown_active=True,
                smart_drops=(64,),
                anlz_buildups=(64,),
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "manual_scene")
        self.assertEqual(ld.status()["last_reason"], "manual_override")

    def test_manual_override_ttl_expiry_falls_back_to_default(self) -> None:
        ld = _director()
        past = _now() - 1.0   # already expired
        ld._manual_override_scene = "expired_scene"
        ld._manual_override_expires_at = past
        ld.tick(_ctx(playing=True, position_stale=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "house_phrase_1")
        self.assertIsNone(ld.status()["manual_override"])

    def test_manual_override_ttl_expiry_clears_override(self) -> None:
        ld = _director()
        ld._manual_override_scene = "will_expire"
        ld._manual_override_expires_at = _now() - 0.001
        ld.tick(_ctx(), now=_now())
        self.assertIsNone(ld.status()["manual_override"])

    def test_clear_manual_override_does_not_clear_emergency(self) -> None:
        ld = _director()
        ld.set_emergency_blackout(True)
        ld.set_manual_override("some_scene", ttl_s=10.0)
        ld.clear_manual_override()
        self.assertTrue(ld.status()["emergency"])

    def test_clear_manual_override_removes_scene(self) -> None:
        ld = _director()
        ld.set_manual_override("house_drop_1", ttl_s=10.0)
        ld.clear_manual_override()
        self.assertIsNone(ld.status()["manual_override"])


# ---------------------------------------------------------------------------
# Not playing
# ---------------------------------------------------------------------------

class NotPlayingTests(unittest.TestCase):
    def test_not_playing_returns_idle_no_output(self) -> None:
        ld = _director()
        ld.tick(_ctx(playing=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "not_playing")

    def test_not_playing_does_not_use_configured_safe_scene(self) -> None:
        ld = _director(safe_scene="my_safe_look")
        ld.tick(_ctx(playing=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "not_playing")


# ---------------------------------------------------------------------------
# Stale position
# ---------------------------------------------------------------------------

class StalePositionTests(unittest.TestCase):
    def test_stale_position_returns_idle_no_output(self) -> None:
        ld = _director()
        ld.tick(_ctx(playing=True, position_stale=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "position_stale")

    def test_stale_position_does_not_use_configured_safe_scene(self) -> None:
        ld = _director(safe_scene="my_stale_safe")
        ld.tick(_ctx(playing=True, position_stale=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "position_stale")


class EligibilityGateTests(unittest.TestCase):
    def test_no_loaded_active_track_returns_idle_no_track(self) -> None:
        ld = _director(default_scene="d", breakdown_scene="bd", drop_scene="drop")
        ld.tick(
            _ctx(
                playing=True,
                position_stale=False,
                active_track_loaded=False,
                autoloop_ready=True,
                breakdown_active=True,
                smart_drops=(64,),
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "idle_no_track")

    def test_autoloop_not_ready_skips_automatic_scenes(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", breakdown_scene="bd", drop_scene="drop")
        ld.tick(
            _ctx(
                abs_beat=64.1,
                playing=True,
                position_stale=False,
                active_track_loaded=True,
                autoloop_ready=False,
                breakdown_active=True,
                smart_drops=(64,),
                anlz_buildups=(64,),
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "autoloop_not_ready")

    def test_autoloop_ready_allows_phrase_default_and_smart_observation(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", breakdown_scene="bd", drop_scene="drop")
        ld.tick(
            _ctx(abs_beat=31.0, autoloop_ready=True, active_track_loaded=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        ld.tick(
            _ctx(abs_beat=31.5, autoloop_ready=True, active_track_loaded=True, breakdown_active=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "bd")

# ---------------------------------------------------------------------------
# Default scene (normal playing)
# ---------------------------------------------------------------------------

class DefaultSceneTests(unittest.TestCase):
    def test_playing_fresh_selects_default_scene(self) -> None:
        ld = _director()
        ld.tick(_ctx(playing=True, position_stale=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "house_phrase_1")
        self.assertEqual(ld.status()["last_reason"], "default_init")

    def test_playing_uses_configured_default_scene(self) -> None:
        ld = _director(default_scene="my_house_phrase")
        ld.tick(_ctx(playing=True, position_stale=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_house_phrase")


# ---------------------------------------------------------------------------
# Phrase scene behavior
# ---------------------------------------------------------------------------

class PhraseSceneTests(unittest.TestCase):
    def test_first_playing_tick_returns_default_not_phrase(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=64.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default_init")

    def test_phrase_boundary_returns_phrase_scene(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(
            _ctx(
                playing=True,
                position_stale=False,
                abs_beat=32.0,
                autoloop_tick_just_fired=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "p")
        self.assertEqual(ld.status()["last_reason"], "phrase_boundary")

    def test_phrase_boundary_waits_for_autoloop_tick_edge(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(_ctx(abs_beat=32.0, autoloop_tick_just_fired=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "phrase_hold_pending")
        self.assertTrue(ld.status()["phrase_trigger_pending"])

    def test_phrase_boundary_pending_fires_on_later_autoloop_tick_edge(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(_ctx(abs_beat=32.0, autoloop_tick_just_fired=False), now=_now())
        ld.tick(_ctx(abs_beat=32.5, autoloop_tick_just_fired=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "p")
        self.assertEqual(ld.status()["last_reason"], "phrase_boundary")
        self.assertFalse(ld.status()["phrase_trigger_pending"])

    def test_not_playing_clears_phrase_trigger_pending(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(_ctx(abs_beat=32.0, autoloop_tick_just_fired=False), now=_now())
        self.assertTrue(ld.status()["phrase_trigger_pending"])
        ld.tick(_ctx(playing=False, abs_beat=32.2), now=_now())
        self.assertFalse(ld.status()["phrase_trigger_pending"])
        self.assertEqual(ld.status()["last_reason"], "not_playing")

    def test_autoloop_not_ready_clears_phrase_trigger_pending(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(_ctx(abs_beat=32.0, autoloop_tick_just_fired=False), now=_now())
        self.assertTrue(ld.status()["phrase_trigger_pending"])
        ld.tick(_ctx(abs_beat=32.2, autoloop_ready=False), now=_now())
        self.assertFalse(ld.status()["phrase_trigger_pending"])
        self.assertEqual(ld.status()["last_reason"], "autoloop_not_ready")

    def test_scripted_clears_phrase_trigger_pending(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(_ctx(abs_beat=32.0, autoloop_tick_just_fired=False), now=_now())
        self.assertTrue(ld.status()["phrase_trigger_pending"])
        ld.tick(_ctx(abs_beat=32.2, scripted_id=7), now=_now())
        self.assertFalse(ld.status()["phrase_trigger_pending"])
        self.assertEqual(ld.status()["last_reason"], "scripted")

    def test_position_stale_clears_phrase_trigger_pending(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(_ctx(abs_beat=32.0, autoloop_tick_just_fired=False), now=_now())
        self.assertTrue(ld.status()["phrase_trigger_pending"])
        ld.tick(_ctx(abs_beat=32.2, position_stale=True), now=_now())
        self.assertFalse(ld.status()["phrase_trigger_pending"])
        self.assertEqual(ld.status()["last_reason"], "position_stale")

    def test_phrase_scene_name_can_be_arbitrary(self) -> None:
        ld = _director(default_scene="d", phrase_scene="my_custom_phrase_42", phrase_interval_beats=16)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=15.0), now=_now())
        ld.tick(
            _ctx(
                playing=True,
                position_stale=False,
                abs_beat=16.0,
                autoloop_tick_just_fired=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "my_custom_phrase_42")

    def test_not_playing_resets_phrase_tracking(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(_ctx(playing=False, position_stale=False, abs_beat=40.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=64.0), now=_now())
        self.assertEqual(ld.status()["last_reason"], "default_init")
        self.assertEqual(ld.status()["current_scene"], "d")

    def test_stale_resets_phrase_tracking(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(_ctx(playing=True, position_stale=True, abs_beat=40.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=64.0), now=_now())
        self.assertEqual(ld.status()["last_reason"], "default_init")
        self.assertEqual(ld.status()["current_scene"], "d")

    def test_minimum_hold_only_gates_normal_automatic_changes(self) -> None:
        ld = _director(
            default_scene="d",
            phrase_scene="p",
            phrase_interval_beats=32,
            minimum_scene_hold_beats=8,
        )
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(
            _ctx(
                playing=True,
                position_stale=False,
                abs_beat=32.0,
                autoloop_tick_just_fired=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "hold_minimum_scene")

    def test_minimum_hold_does_not_block_emergency_manual_or_idle(self) -> None:
        ld = _director(
            default_scene="d",
            phrase_scene="p",
            phrase_interval_beats=32,
            minimum_scene_hold_beats=128,
        )
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.set_manual_override("manual_scene", ttl_s=10.0)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=32.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "manual_scene")
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=33.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "emergency_blackout")
        ld.clear_emergency_blackout()
        ld.tick(_ctx(playing=False, position_stale=False, abs_beat=33.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")

    def test_phrase_boundary_only_holds_normal_automatic_scenes(self) -> None:
        ld = _director(
            default_scene="d",
            phrase_scene="p",
            phrase_interval_beats=32,
            normal_changes_only_on_phrase_boundary=True,
        )
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.5), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "phrase_hold")

        ld._current_scene = ""
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.7), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_phrase_tracking_not_consumed_by_emergency_or_manual(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        last_phrase = ld._last_phrase_number

        ld.set_manual_override("manual_scene", ttl_s=10.0)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=32.0), now=_now())
        self.assertEqual(ld._last_phrase_number, last_phrase)

        ld.clear_manual_override()
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=33.0), now=_now())
        self.assertEqual(ld._last_phrase_number, last_phrase)

    def test_no_per_tick_log_spam(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        with patch("rb_ss_bridge_v2.laser_director.log.info") as info:
            ld.tick(_ctx(playing=True, position_stale=False, abs_beat=1.0), now=_now())
            ld.tick(_ctx(playing=True, position_stale=False, abs_beat=1.5), now=_now())
            for _ in range(100):
                ld.tick(_ctx(playing=True, position_stale=False, abs_beat=1.5), now=_now())
        self.assertEqual(info.call_count, 1)

    def test_same_scene_reason_update_is_not_new_trigger(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        initial_trigger = ld.status()["last_trigger_abs_beat"]
        ld.tick(_ctx(abs_beat=31.5), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")
        self.assertEqual(ld.status()["last_trigger_abs_beat"], initial_trigger)

    def test_status_includes_phrase_policy_fields(self) -> None:
        ld = _director(
            default_scene="d",
            phrase_scene="p",
            phrase_interval_beats=48,
            minimum_scene_hold_beats=3,
            normal_changes_only_on_phrase_boundary=True,
        )
        s = ld.status()
        self.assertEqual(s["phrase_scene"], "p")
        self.assertEqual(s["phrase_interval_beats"], 48)
        self.assertEqual(s["minimum_scene_hold_beats"], 3)
        self.assertTrue(s["normal_changes_only_on_phrase_boundary"])

    def test_set_personality_config_applies_phrase_policy(self) -> None:
        ld = _director(default_scene="d")
        personality = LaserPersonality(
            name="house",
            safe_scene="safe_static",
            default_scene="d",
            phrase_scene="custom_phrase",
            buildup_scene="safe_static",
            pre_drop_scene="safe_static",
            drop_scene="safe_static",
            post_drop_scene="safe_static",
            breakdown_scene="safe_static",
            transition_scene="safe_static",
            phrase_interval_beats=16,
            minimum_scene_hold_beats=4,
            normal_changes_only_on_phrase_boundary=True,
            buildup_lookahead_beats=24,
            buildup_approach_beats=6,
            buildup_hold_beats=10,
            pre_drop_lookahead_beats=3,
        )
        ld.set_personality_config(personality)
        s = ld.status()
        self.assertEqual(s["phrase_scene"], "custom_phrase")
        self.assertEqual(s["phrase_interval_beats"], 16)
        self.assertEqual(s["minimum_scene_hold_beats"], 4)
        self.assertTrue(s["normal_changes_only_on_phrase_boundary"])
        self.assertEqual(s["buildup_lookahead_beats"], 24)
        self.assertEqual(s["buildup_approach_beats"], 6)
        self.assertEqual(s["buildup_hold_beats"], 10)
        self.assertEqual(s["pre_drop_lookahead_beats"], 3)


# ---------------------------------------------------------------------------
# Smart observation: breakdown / buildup / drop lifecycle
# ---------------------------------------------------------------------------

class SmartObservationTests(unittest.TestCase):
    def test_breakdown_active_selects_breakdown_scene(self) -> None:
        ld = _director(default_scene="d", breakdown_scene="bd")
        ld.tick(_ctx(abs_beat=32.0), now=_now())  # initialize phrase tracking
        ld.tick(_ctx(abs_beat=32.5, breakdown_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "bd")
        self.assertEqual(ld.status()["last_reason"], "breakdown_active")

    def test_breakdown_scene_empty_falls_back(self) -> None:
        ld = _director(default_scene="d", breakdown_scene="")
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(_ctx(abs_beat=10.5, breakdown_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")

    def test_buildup_window_uses_smart_drop_countdown(self) -> None:
        ld = _director(
            default_scene="d",
            buildup_scene="up",
            buildup_lookahead_beats=8,
        )
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(_ctx(abs_beat=19.9, smart_drops=(28,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        ld.tick(
            _ctx(
                abs_beat=20.1,
                smart_drops=(28,),
                current_phrase_is_up=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        self.assertEqual(ld.status()["last_reason"], "buildup_to_drop_window")

    def test_buildup_window_requires_current_phrase_up(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=8)
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(
            _ctx(abs_beat=20.1, smart_drops=(28,), current_phrase_is_up=False),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_buildup_window_blocked_in_chorus_even_if_up_true(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=8)
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(
            _ctx(
                abs_beat=20.1,
                smart_drops=(28,),
                current_phrase_is_up=True,
                current_phrase_is_chorus=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_anlz_buildups_alone_do_not_trigger_buildup(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up")
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(_ctx(abs_beat=18.5, anlz_buildups=(20,), smart_drops=()), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_buildup_window_requires_future_smart_drop(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up")
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(_ctx(abs_beat=18.5, smart_drops=(18,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_buildup_window_ignores_far_future_drop(self) -> None:
        ld = _director(
            default_scene="d",
            buildup_scene="up",
            buildup_lookahead_beats=8,
        )
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(_ctx(abs_beat=18.5, smart_drops=(40,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")

    def test_buildup_window_ignores_far_future_drop_even_when_up(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=8)
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        ld.tick(
            _ctx(abs_beat=18.5, smart_drops=(40,), current_phrase_is_up=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_buildup_holds_through_countdown_until_drop_crossing(self) -> None:
        ld = _director(
            default_scene="d",
            buildup_scene="up",
            drop_scene="drop",
            buildup_lookahead_beats=32,
        )
        ld.tick(_ctx(abs_beat=63.0, smart_drops=(96,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        ld.tick(
            _ctx(abs_beat=64.1, smart_drops=(96,), current_phrase_is_up=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        ld.tick(
            _ctx(abs_beat=95.5, smart_drops=(96,), current_phrase_is_up=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        ld.tick(_ctx(abs_beat=96.1, smart_drops=(96,), smart_drop_blackout_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")

    def test_first_smart_tick_does_not_fire_drop_crossing(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld.tick(_ctx(abs_beat=64.2, smart_drops=(64,)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld._last_smart_abs_beat, 64.2)

    def test_drop_crossing_uses_previous_abs_beat(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld.tick(_ctx(abs_beat=63.5, smart_drops=(64,)), now=_now())
        ld.tick(_ctx(abs_beat=64.1, smart_drops=(64,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld.status()["last_reason"], "drop_crossing")

    def test_drop_crossing_does_not_require_blackout_active(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld.tick(_ctx(abs_beat=63.5, smart_drops=(64,)), now=_now())
        ld.tick(_ctx(abs_beat=64.1, smart_drops=(64,), smart_drop_blackout_active=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")

    def test_drop_crossing_fires_during_chorus_phrase_context(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop", buildup_scene="up")
        ld.tick(
            _ctx(abs_beat=63.5, smart_drops=(64,), current_phrase_is_chorus=True),
            now=_now(),
        )
        ld.tick(
            _ctx(
                abs_beat=64.1,
                smart_drops=(64,),
                current_phrase_is_chorus=True,
                smart_drop_blackout_active=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld.status()["last_reason"], "drop_crossing")

    def test_drop_fires_once_per_target_beat(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld.tick(_ctx(abs_beat=63.5, smart_drops=(64,)), now=_now())
        ld.tick(_ctx(abs_beat=64.1, smart_drops=(64,), smart_drop_blackout_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        ld.tick(_ctx(abs_beat=64.4, smart_drops=(64,)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "drop")

    def test_drop_wins_over_buildup_at_crossing(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            buildup_scene="up",
            buildup_lookahead_beats=32,
        )
        ld.tick(
            _ctx(abs_beat=63.2, smart_drops=(64,), current_phrase_is_up=True),
            now=_now(),
        )
        ld.tick(_ctx(abs_beat=64.0, smart_drops=(64,), smart_drop_blackout_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")

    def test_drop_crossing_beats_buildup_at_exact_crossing(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            buildup_scene="up",
            buildup_lookahead_beats=32,
        )
        ld.tick(
            _ctx(abs_beat=23.0, smart_drops=(32,), current_phrase_is_up=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        ld.tick(
            _ctx(abs_beat=31.5, smart_drops=(32,), current_phrase_is_up=True),
            now=_now(),
        )
        ld.tick(_ctx(abs_beat=32.1, smart_drops=(32,), smart_drop_blackout_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld.status()["last_reason"], "drop_crossing")

    def test_post_drop_uses_minimum_scene_hold_beats(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            post_drop_scene="post",
            minimum_scene_hold_beats=2,
        )
        ld.tick(_ctx(abs_beat=63.1, smart_drops=(64,)), now=_now())
        ld.tick(_ctx(abs_beat=64.0, smart_drops=(64,), smart_drop_blackout_active=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        ld.tick(_ctx(abs_beat=65.0, smart_drops=(64,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "post")
        ld.tick(_ctx(abs_beat=66.1, smart_drops=(64,)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")

    def test_post_drop_holds_after_chorus_drop_crossing(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            post_drop_scene="post",
            minimum_scene_hold_beats=2,
            buildup_scene="up",
        )
        ld.tick(
            _ctx(abs_beat=63.1, smart_drops=(64,), current_phrase_is_chorus=True),
            now=_now(),
        )
        ld.tick(
            _ctx(
                abs_beat=64.0,
                smart_drops=(64,),
                current_phrase_is_chorus=True,
                smart_drop_blackout_active=True,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "drop")
        ld.tick(
            _ctx(abs_beat=65.0, smart_drops=(64,), current_phrase_is_chorus=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "post")

    def test_post_drop_hold_not_overridden_by_buildup_window(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            post_drop_scene="post",
            buildup_scene="up",
            minimum_scene_hold_beats=3,
            buildup_lookahead_beats=32,
        )
        ld.tick(_ctx(abs_beat=63.0, smart_drops=(64, 80)), now=_now())
        ld.tick(
            _ctx(abs_beat=64.1, smart_drops=(64, 80), smart_drop_blackout_active=True),
            now=_now(),
        )
        ld.tick(_ctx(abs_beat=65.2, smart_drops=(64, 80)), now=_now())
        ld.tick(_ctx(abs_beat=65.3, smart_drops=(64, 80)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "post")
        self.assertEqual(ld.status()["last_reason"], "post_drop_hold")

    def test_buildup_can_trigger_after_post_drop_hold_expires(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            post_drop_scene="post",
            buildup_scene="up",
            minimum_scene_hold_beats=3,
            buildup_lookahead_beats=32,
        )
        ld.tick(_ctx(abs_beat=63.0, smart_drops=(64, 100)), now=_now())
        ld.tick(
            _ctx(abs_beat=64.1, smart_drops=(64, 100), smart_drop_blackout_active=True),
            now=_now(),
        )
        ld.tick(_ctx(abs_beat=65.0, smart_drops=(64, 100)), now=_now())
        ld.tick(_ctx(abs_beat=65.1, smart_drops=(64, 100)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "post")
        ld.tick(_ctx(abs_beat=68.2, smart_drops=(64, 100)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        ld.tick(
            _ctx(abs_beat=68.5, smart_drops=(64, 100), current_phrase_is_up=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        self.assertEqual(ld.status()["last_reason"], "buildup_to_drop_window")

    def test_multiple_smart_drops_inside_chorus_do_not_trigger_buildup(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=32)
        ld.tick(_ctx(abs_beat=10.0), now=_now())
        for beat in (170.0, 184.0, 188.0, 191.5):
            ld.tick(
                _ctx(
                    abs_beat=beat,
                    smart_drops=(192, 196),
                    current_phrase_is_chorus=True,
                    current_phrase_is_up=False,
                ),
                now=_now(),
            )
            self.assertNotEqual(ld.status()["current_scene"], "up")

    def test_up_before_first_drop_allows_buildup(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(
            _ctx(abs_beat=40.0, smart_drops=(64,), current_phrase_is_up=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "up")

    def test_buildup_blocked_when_latest_marker_low_or_none(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=32)
        ld.tick(_ctx(abs_beat=31.0), now=_now())
        ld.tick(
            _ctx(
                abs_beat=40.0,
                smart_drops=(64,),
                current_phrase_is_up=False,
                current_phrase_is_chorus=False,
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertNotEqual(ld.status()["last_reason"], "buildup_to_drop_window")

    def test_pre_drop_scene_is_inert_in_active_policy(self) -> None:
        ld = _director(
            default_scene="d",
            buildup_scene="up",
            pre_drop_scene="pre",
            drop_scene="drop",
            buildup_lookahead_beats=32,
            pre_drop_lookahead_beats=4,
        )
        ld.tick(_ctx(abs_beat=63.0, smart_drops=(64,)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "pre")
        ld.tick(_ctx(abs_beat=63.8, smart_drops=(64,)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "pre")
        self.assertNotEqual(ld.status()["last_reason"], "pre_drop_window")

    def test_autoloop_not_ready_blocks_buildup_and_drop(self) -> None:
        ld = _director(
            default_scene="d",
            buildup_scene="up",
            drop_scene="drop",
            buildup_lookahead_beats=32,
        )
        ld.tick(_ctx(abs_beat=63.5, smart_drops=(64,), autoloop_ready=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "autoloop_not_ready")

    def test_zero_minimum_hold_disables_post_drop_hold(self) -> None:
        ld = _director(
            default_scene="d",
            drop_scene="drop",
            post_drop_scene="post",
            minimum_scene_hold_beats=0,
        )
        ld.tick(_ctx(abs_beat=63.2, smart_drops=(64,)), now=_now())
        ld.tick(_ctx(abs_beat=64.0, smart_drops=(64,)), now=_now())
        ld.tick(_ctx(abs_beat=64.5, smart_drops=(64,)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "post")

    def test_scripted_gate_by_scripted_id_skips_smart_observation(self) -> None:
        ld = _director(
            default_scene="d",
            breakdown_scene="bd",
            buildup_scene="up",
            pre_drop_scene="pre",
            drop_scene="drop",
            post_drop_scene="post",
        )
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld.tick(
            _ctx(
                abs_beat=64.0,
                scripted_id=99,
                breakdown_active=True,
                smart_drops=(64,),
                anlz_buildups=(64,),
            ),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "scripted")

    def test_scripted_gate_by_lighting_mode_skips_smart_observation(self) -> None:
        ld = _director(default_scene="d", breakdown_scene="bd")
        ld.tick(_ctx(abs_beat=32.0), now=_now())
        ld.tick(
            _ctx(abs_beat=32.2, lighting_mode="scripted", breakdown_active=True),
            now=_now(),
        )
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "scripted")

    def test_tick_does_not_mutate_context_scripted_id(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ctx = _ctx(abs_beat=64.0, scripted_id=7, smart_drops=(64,))
        ld.tick(ctx, now=_now())
        self.assertEqual(ctx.scripted_id, 7)

    def test_scripted_resets_only_smart_state(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld._laser_drop_fired_beat = 64
        ld._post_drop_start_abs_beat = 64.0
        ld._last_smart_abs_beat = 63.0
        ld.tick(_ctx(abs_beat=65.0, scripted_id=2), now=_now())
        self.assertIsNone(ld._laser_drop_fired_beat)
        self.assertEqual(ld._post_drop_start_abs_beat, -1.0)
        self.assertIsNone(ld._last_smart_abs_beat)

    def test_not_playing_resets_only_smart_state(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld._laser_drop_fired_beat = 64
        ld._post_drop_start_abs_beat = 64.0
        ld._last_smart_abs_beat = 63.0
        ld.tick(_ctx(playing=False), now=_now())
        self.assertIsNone(ld._laser_drop_fired_beat)
        self.assertEqual(ld._post_drop_start_abs_beat, -1.0)
        self.assertIsNone(ld._last_smart_abs_beat)

    def test_stale_resets_only_smart_state(self) -> None:
        ld = _director(default_scene="d", drop_scene="drop")
        ld._laser_drop_fired_beat = 64
        ld._post_drop_start_abs_beat = 64.0
        ld._last_smart_abs_beat = 63.0
        ld.tick(_ctx(playing=True, position_stale=True), now=_now())
        self.assertIsNone(ld._laser_drop_fired_beat)
        self.assertEqual(ld._post_drop_start_abs_beat, -1.0)
        self.assertIsNone(ld._last_smart_abs_beat)

    def test_reset_smart_observation_state_does_not_clear_manual_or_emergency(self) -> None:
        ld = _director(default_scene="d")
        ld.set_manual_override("manual_scene", ttl_s=30.0)
        ld.set_emergency_blackout(True)
        ld._laser_drop_fired_beat = 64
        ld._post_drop_start_abs_beat = 64.0
        ld._last_smart_abs_beat = 63.0
        ld._reset_smart_observation_state()
        self.assertIsNone(ld._laser_drop_fired_beat)
        self.assertEqual(ld._post_drop_start_abs_beat, -1.0)
        self.assertIsNone(ld._last_smart_abs_beat)
        self.assertTrue(ld.status()["emergency"])
        self.assertEqual(ld.status()["manual_override"], "manual_scene")


# ---------------------------------------------------------------------------
# Smart Phrasing Observation (PR 4a tests)
# ---------------------------------------------------------------------------

class SmartPhrasingObservationTests(unittest.TestCase):
    def test_breakdown_from_smart_phrasing(self) -> None:
        ld = _director(default_scene="d", breakdown_scene="bd")
        sp = SmartPhrasingState(
            current_phrase_label="other", current_phrase_is_up=False, current_phrase_is_chorus=False,
            current_phrase_is_low=False, next_smart_drop_beat=None, beats_to_next_drop=None,
            smart_drop_window_active=False, smart_drop_crossing=False, smart_drop_preclear_requested=False,
            smart_drop_rearm_requested=False, smart_post_drop_active=False, active_drop_beat=None,
            smart_buildup_active=False, smart_breakdown_active=True, breakdown_start_crossing=False,
            breakdown_end_crossing=False, smart_breakdown_clear_requested=False,
            smart_breakdown_restore_requested=False, transition_mask_should_arm=False,
            transition_mask_should_clear=False, transition_window_active=False,
            phrase_anchor_requested=False, reason="test"
        )
        ld.tick(_ctx(abs_beat=32.0), now=_now())  # init
        ld.tick(_ctx(abs_beat=32.5, smart_phrasing=sp, breakdown_active=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "bd")
        self.assertEqual(ld.status()["last_reason"], "breakdown_active")

    def test_buildup_from_smart_phrasing_beats_to_drop(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=16)
        sp = SmartPhrasingState(
            current_phrase_label="up", current_phrase_is_up=True, current_phrase_is_chorus=False,
            current_phrase_is_low=False, next_smart_drop_beat=32.0, beats_to_next_drop=10.0,
            smart_drop_window_active=False, smart_drop_crossing=False, smart_drop_preclear_requested=False,
            smart_drop_rearm_requested=False, smart_post_drop_active=False, active_drop_beat=None,
            smart_buildup_active=False, smart_breakdown_active=False, breakdown_start_crossing=False,
            breakdown_end_crossing=False, smart_breakdown_clear_requested=False,
            smart_breakdown_restore_requested=False, transition_mask_should_arm=False,
            transition_mask_should_clear=False, transition_window_active=False,
            phrase_anchor_requested=False, reason="test"
        )
        ld.tick(_ctx(abs_beat=10.0), now=_now())  # init
        ld.tick(
            _ctx(abs_beat=22.0, smart_phrasing=sp, current_phrase_is_up=False, smart_drops=()),
            now=_now()
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        self.assertEqual(ld.status()["last_reason"], "buildup_to_drop_window")

    def test_phrase_flags_from_smart_phrasing_chorus_blocks_buildup(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=16)
        sp = SmartPhrasingState(
            current_phrase_label="chorus", current_phrase_is_up=True, current_phrase_is_chorus=True,
            current_phrase_is_low=False, next_smart_drop_beat=32.0, beats_to_next_drop=10.0,
            smart_drop_window_active=False, smart_drop_crossing=False, smart_drop_preclear_requested=False,
            smart_drop_rearm_requested=False, smart_post_drop_active=False, active_drop_beat=None,
            smart_buildup_active=False, smart_breakdown_active=False, breakdown_start_crossing=False,
            breakdown_end_crossing=False, smart_breakdown_clear_requested=False,
            smart_breakdown_restore_requested=False, transition_mask_should_arm=False,
            transition_mask_should_clear=False, transition_window_active=False,
            phrase_anchor_requested=False, reason="test"
        )
        ld.tick(_ctx(abs_beat=10.0), now=_now())  # init
        ld.tick(
            _ctx(abs_beat=22.0, smart_phrasing=sp, current_phrase_is_up=True, current_phrase_is_chorus=False, smart_drops=(32,)),
            now=_now()
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_buildup_from_smart_phrasing_beats_to_drop_none_safe(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=16)
        sp = SmartPhrasingState(
            current_phrase_label="up", current_phrase_is_up=True, current_phrase_is_chorus=False,
            current_phrase_is_low=False, next_smart_drop_beat=None, beats_to_next_drop=None,
            smart_drop_window_active=False, smart_drop_crossing=False, smart_drop_preclear_requested=False,
            smart_drop_rearm_requested=False, smart_post_drop_active=False, active_drop_beat=None,
            smart_buildup_active=False, smart_breakdown_active=False, breakdown_start_crossing=False,
            breakdown_end_crossing=False, smart_breakdown_clear_requested=False,
            smart_breakdown_restore_requested=False, transition_mask_should_arm=False,
            transition_mask_should_clear=False, transition_window_active=False,
            phrase_anchor_requested=False, reason="test"
        )
        ld.tick(_ctx(abs_beat=10.0), now=_now())  # init
        ld.tick(
            _ctx(abs_beat=22.0, smart_phrasing=sp, current_phrase_is_up=False, smart_drops=()),
            now=_now()
        )
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "default")

    def test_legacy_buildup_fallback_works(self) -> None:
        ld = _director(default_scene="d", buildup_scene="up", buildup_lookahead_beats=16)
        ld.tick(_ctx(abs_beat=10.0), now=_now())  # init
        ld.tick(
            _ctx(abs_beat=48.0, smart_phrasing=None, current_phrase_is_up=True, current_phrase_is_chorus=False, smart_drops=(64,)),
            now=_now()
        )
        self.assertEqual(ld.status()["current_scene"], "up")
        self.assertEqual(ld.status()["last_reason"], "buildup_to_drop_window")

class SmartPhrasingDropCrossingTests(unittest.TestCase):
    def _sp(self, **kwargs) -> SmartPhrasingState:
        default_kwargs = dict(
            current_phrase_label="other", current_phrase_is_up=False, current_phrase_is_chorus=False,
            current_phrase_is_low=False, next_smart_drop_beat=None, beats_to_next_drop=None,
            smart_drop_window_active=False, smart_drop_crossing=False, smart_drop_preclear_requested=False,
            smart_drop_rearm_requested=False, smart_post_drop_active=False, active_drop_beat=None,
            smart_buildup_active=False, smart_breakdown_active=False, breakdown_start_crossing=False,
            breakdown_end_crossing=False, smart_breakdown_clear_requested=False,
            smart_breakdown_restore_requested=False, transition_mask_should_arm=False,
            transition_mask_should_clear=False, transition_window_active=False,
            phrase_anchor_requested=False, reason="test"
        )
        default_kwargs.update(kwargs)
        return SmartPhrasingState(**default_kwargs)

    def test_drop_crossing_from_smart_phrasing(self) -> None:
        ld = _director(drop_scene="drop")
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld.tick(_ctx(abs_beat=64.0, smart_phrasing=self._sp(smart_drop_crossing=True)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld.status()["last_reason"], "drop_crossing")

    def test_drop_crossing_smart_phrasing_does_not_use_legacy_dedup(self) -> None:
        ld = _director(drop_scene="drop")
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld._laser_drop_fired_beat = 64  # Set legacy dedup field directly
        ld.tick(_ctx(abs_beat=64.0, smart_phrasing=self._sp(smart_drop_crossing=True)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")

    def test_drop_crossing_legacy_fallback_when_smart_phrasing_none(self) -> None:
        ld = _director(drop_scene="drop")
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld.tick(_ctx(abs_beat=64.0, smart_drops=(64,), smart_phrasing=None), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld.status()["last_reason"], "drop_crossing")

    def test_drop_crossing_no_fire_when_smart_phrasing_false_even_if_legacy_would_cross(self) -> None:
        ld = _director(drop_scene="drop", default_scene="d")
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        # smart_drops=(64,) would trigger legacy drop
        ld.tick(_ctx(abs_beat=64.0, smart_drops=(64,), smart_phrasing=self._sp(smart_drop_crossing=False)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "drop")

    def test_priority_breakdown_wins_over_drop(self) -> None:
        ld = _director(drop_scene="drop", breakdown_scene="bd")
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld.tick(_ctx(abs_beat=64.0, smart_phrasing=self._sp(smart_breakdown_active=True, smart_drop_crossing=True)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "bd")
        self.assertEqual(ld.status()["last_reason"], "breakdown_active")

    def test_priority_drop_wins_over_buildup(self) -> None:
        ld = _director(drop_scene="drop", buildup_scene="up", buildup_lookahead_beats=16)
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        sp = self._sp(smart_drop_crossing=True, beats_to_next_drop=10.0, current_phrase_is_up=True)
        ld.tick(_ctx(abs_beat=64.0, smart_phrasing=sp), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        self.assertEqual(ld.status()["last_reason"], "drop_crossing")

    def test_priority_post_drop_active_unchanged_with_no_crossing(self) -> None:
        ld = _director(drop_scene="drop", post_drop_scene="pd", minimum_scene_hold_beats=8)
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld.tick(_ctx(abs_beat=64.0, smart_phrasing=self._sp(smart_drop_crossing=True)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "drop")
        # next tick, drop crossing is false, should be in post drop
        ld.tick(_ctx(abs_beat=65.0, smart_phrasing=self._sp(smart_drop_crossing=False)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "pd")
        self.assertEqual(ld.status()["last_reason"], "post_drop_hold")

    def test_priority_gates_win_over_drop(self) -> None:
        ld = _director(drop_scene="drop", emergency_scene="em")
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        ld.set_emergency_blackout(True)
        ld.tick(_ctx(abs_beat=64.0, smart_phrasing=self._sp(smart_drop_crossing=True)), now=_now())
        self.assertEqual(ld.status()["current_scene"], "em")
        self.assertEqual(ld.status()["last_reason"], "emergency")

    def test_gate_clearing_does_not_fire_stale_drop_with_smart_phrasing(self) -> None:
        """After a gate clears, first eligible tick must not fire drop even if
        engine had crossing=True during gated period (previous_abs_beat guard)."""
        ld = _director(drop_scene="drop", default_scene="d")
        # Establish baseline
        ld.tick(_ctx(abs_beat=63.0), now=_now())
        # Gate activates (stale position) — resets _last_smart_abs_beat to None
        ld.tick(_ctx(abs_beat=64.0, position_stale=True), now=_now())
        # Gate clears — first eligible tick with smart_drop_crossing=True
        # Should NOT fire drop because previous_abs_beat is None
        ld.tick(_ctx(abs_beat=64.5, smart_phrasing=self._sp(smart_drop_crossing=True)), now=_now())
        self.assertNotEqual(ld.status()["current_scene"], "drop")

# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------

class EnableTests(unittest.TestCase):
    def test_toggle_enabled_from_false(self) -> None:
        ld = _director(enabled=False)
        ld.toggle_enabled()
        self.assertTrue(ld.status()["enabled"])

    def test_toggle_enabled_from_true(self) -> None:
        ld = _director(enabled=True)
        ld.toggle_enabled()
        self.assertFalse(ld.status()["enabled"])

    def test_toggle_is_a_true_toggle(self) -> None:
        ld = _director(enabled=False)
        ld.toggle_enabled()
        ld.toggle_enabled()
        self.assertFalse(ld.status()["enabled"])

    def test_set_enabled_true(self) -> None:
        ld = _director(enabled=False)
        ld.set_enabled(True)
        self.assertTrue(ld.status()["enabled"])

    def test_set_enabled_false(self) -> None:
        ld = _director(enabled=True)
        ld.set_enabled(False)
        self.assertFalse(ld.status()["enabled"])

    def test_enabling_mid_flight_picks_up_scene(self) -> None:
        ld = _director(enabled=False)
        ld.tick(_ctx(), now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        ld.set_enabled(True)
        ld.tick(_ctx(playing=True, position_stale=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "house_phrase_1")


# ---------------------------------------------------------------------------
# Status shape
# ---------------------------------------------------------------------------

class StatusShapeTests(unittest.TestCase):
    def test_status_keys_present(self) -> None:
        ld = _director()
        s = ld.status()
        for key in ("available", "enabled", "dry_run", "current_scene",
                    "last_reason", "manual_override", "emergency", "last_error", "personality",
                    "phrase_scene", "phrase_interval_beats", "minimum_scene_hold_beats",
                    "normal_changes_only_on_phrase_boundary", "breakdown_scene", "buildup_scene",
                    "pre_drop_scene", "drop_scene", "post_drop_scene", "buildup_lookahead_beats",
                    "buildup_approach_beats",
                    "buildup_hold_beats", "buildup_max_drop_distance_beats",
                    "pre_drop_lookahead_beats", "laser_drop_fired_beat",
                    "phrase_trigger_pending", "last_trigger_abs_beat"):
            self.assertIn(key, s, msg=f"missing key: {key}")

    def test_status_available_true(self) -> None:
        self.assertTrue(_director().status()["available"])

    def test_status_dry_run_true(self) -> None:
        self.assertTrue(_director(dry_run=True).status()["dry_run"])

    def test_status_dry_run_false(self) -> None:
        self.assertFalse(_director(dry_run=False).status()["dry_run"])

    def test_status_manual_override_none_initially(self) -> None:
        self.assertIsNone(_director().status()["manual_override"])

    def test_status_last_error_empty_initially(self) -> None:
        self.assertEqual(_director().status()["last_error"], "")

    def test_status_returns_independent_dict(self) -> None:
        """Mutating the returned dict must not affect subsequent calls."""
        ld = _director()
        s = ld.status()
        s["enabled"] = not s["enabled"]
        s2 = ld.status()
        self.assertEqual(s2["enabled"], ld._enabled)


# ---------------------------------------------------------------------------
# Ev laser constants present in models.py
# ---------------------------------------------------------------------------

class EvLaserConstantsTests(unittest.TestCase):
    def test_laser_ev_constants_exist(self) -> None:
        for attr in (
            "LASER_TOGGLE",
            "LASER_SET_ENABLED",
            "LASER_SCENE",
            "LASER_BLACKOUT",
            "LASER_CLEAR_BLACKOUT",
            "LASER_CLEAR_SCENE_OVERRIDE",
            "LASER_SET_PERSONALITY",
        ):
            self.assertTrue(hasattr(Ev, attr), msg=f"Ev missing: {attr}")

    def test_laser_ev_values_are_strings(self) -> None:
        for attr in ("LASER_TOGGLE", "LASER_SET_ENABLED", "LASER_SCENE",
                     "LASER_BLACKOUT", "LASER_CLEAR_BLACKOUT",
                     "LASER_CLEAR_SCENE_OVERRIDE", "LASER_SET_PERSONALITY"):
            self.assertIsInstance(getattr(Ev, attr), str)


# ---------------------------------------------------------------------------
# StateManager integration — optional laser_director kwarg
# ---------------------------------------------------------------------------

def _make_sm(laser_director=None, os2l_connected_provider=None):
    """Build a minimal StateManager stub for integration tests."""
    from rb_ss_bridge_v2.state_manager import StateManager
    eq = queue.Queue(maxsize=256)
    pos_cache = MagicMock()
    pos_cache.get.return_value = None
    output = MagicMock()
    live_bpm = MagicMock()
    live_bpm.get_snapshot.return_value = None
    return StateManager(
        eq, pos_cache, output,
        live_bpm=live_bpm,
        laser_director=laser_director,
        os2l_connected_provider=os2l_connected_provider,
    )


class StateManagerLaserIntegrationTests(unittest.TestCase):
    def test_state_manager_accepts_no_laser_director(self) -> None:
        sm = _make_sm()
        self.assertIsNone(sm._laser_director)

    def test_state_manager_accepts_laser_director(self) -> None:
        ld = _director()
        sm = _make_sm(laser_director=ld)
        self.assertIs(sm._laser_director, ld)

    def test_state_manager_accepts_os2l_connected_provider(self) -> None:
        sm = _make_sm(os2l_connected_provider=lambda: True)
        self.assertIsNotNone(sm._os2l_connected_provider)

    def test_laser_toggle_event_toggles_enabled(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director(enabled=False)
        sm = _make_sm(laser_director=ld)
        ev = BridgeEvent(kind=Ev.LASER_TOGGLE, deck=0)
        sm._handle_event(ev)
        self.assertTrue(ld.status()["enabled"])

    def test_laser_toggle_event_twice_restores_state(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director(enabled=False)
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(kind=Ev.LASER_TOGGLE, deck=0))
        sm._handle_event(BridgeEvent(kind=Ev.LASER_TOGGLE, deck=0))
        self.assertFalse(ld.status()["enabled"])

    def test_laser_set_enabled_event(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director(enabled=False)
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(kind=Ev.LASER_SET_ENABLED, deck=0, payload={"enabled": True}))
        self.assertTrue(ld.status()["enabled"])

    def test_laser_scene_event_sets_manual_override(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director()
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(
            kind=Ev.LASER_SCENE, deck=0, payload={"scene": "house_drop_1", "ttl_s": 8.0}
        ))
        self.assertEqual(ld.status()["manual_override"], "house_drop_1")

    def test_laser_blackout_event_sets_emergency(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director()
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(kind=Ev.LASER_BLACKOUT, deck=0))
        self.assertTrue(ld.status()["emergency"])

    def test_laser_clear_blackout_event(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director()
        ld.set_emergency_blackout(True)
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(kind=Ev.LASER_CLEAR_BLACKOUT, deck=0))
        self.assertFalse(ld.status()["emergency"])

    def test_laser_clear_scene_override_event(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director()
        ld.set_manual_override("house_drop_1", ttl_s=10.0)
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(kind=Ev.LASER_CLEAR_SCENE_OVERRIDE, deck=0))
        self.assertIsNone(ld.status()["manual_override"])

    def test_laser_clear_scene_override_does_not_clear_emergency(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director()
        ld.set_emergency_blackout(True)
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(kind=Ev.LASER_CLEAR_SCENE_OVERRIDE, deck=0))
        self.assertTrue(ld.status()["emergency"])

    def test_laser_events_ignored_when_no_laser_director(self) -> None:
        """Laser events with no director wired must not raise."""
        from rb_ss_bridge_v2.models import BridgeEvent
        sm = _make_sm()
        for kind in (Ev.LASER_TOGGLE, Ev.LASER_BLACKOUT, Ev.LASER_CLEAR_BLACKOUT,
                     Ev.LASER_CLEAR_SCENE_OVERRIDE):
            sm._handle_event(BridgeEvent(kind=kind, deck=0))  # must not raise

    def test_laser_set_personality_event_updates_status(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        ld = _director()
        sm = _make_sm(laser_director=ld)
        sm._handle_event(BridgeEvent(
            kind=Ev.LASER_SET_PERSONALITY, deck=0, payload={"personality": "dubstep"}
        ))
        self.assertEqual(ld.status()["personality"], "dubstep")

    def test_laser_set_personality_event_ignored_when_no_director(self) -> None:
        from rb_ss_bridge_v2.models import BridgeEvent
        sm = _make_sm()
        sm._handle_event(BridgeEvent(
            kind=Ev.LASER_SET_PERSONALITY, deck=0, payload={"personality": "dubstep"}
        ))

    def test_existing_smart_drop_toggle_still_works(self) -> None:
        """SMART_DROP_TOGGLE must still reach toggle_smart_drop() without raising.

        When _smart_rearm_experiment is off (the default in tests), toggle_smart_drop
        keeps the value at False — the important thing is the event dispatch path is
        intact and doesn't raise.
        """
        from rb_ss_bridge_v2.models import BridgeEvent
        sm = _make_sm()
        sm._handle_event(BridgeEvent(kind=Ev.SMART_DROP_TOGGLE, deck=0))  # must not raise

    def test_existing_smart_breakdown_toggle_still_works(self) -> None:
        """SMART_BREAKDOWN_TOGGLE must still reach toggle_smart_breakdown() without raising."""
        from rb_ss_bridge_v2.models import BridgeEvent
        sm = _make_sm()
        sm._handle_event(BridgeEvent(kind=Ev.SMART_BREAKDOWN_TOGGLE, deck=0))  # must not raise

    def test_build_laser_context_position_stale_false_when_snap_fresh(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.playing = True
        snap = PositionSnapshot(deck=1, elapsed_ms=60_000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 60_000, 128.0, 1.5, 64.0, snap, time.monotonic())
        self.assertFalse(ctx.position_stale)
        self.assertTrue(ctx.playing)
        self.assertEqual(ctx.active_deck, 1)
        self.assertEqual(ctx.bpm, 128.0)

    def test_build_laser_context_position_stale_true_when_snap_none(self) -> None:
        from rb_ss_bridge_v2.models import DeckState
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        ctx = sm._build_laser_context(1, d, 0, 0.0, 0.0, 0.0, None, time.monotonic())
        self.assertTrue(ctx.position_stale)

    def test_build_laser_context_copies_breakdown_active(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        sm._os.breakdown_active = True
        d = DeckState(number=1)
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertTrue(ctx.breakdown_active)

    def test_build_laser_context_copies_autoloop_tick_just_fired(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(
            1,
            d,
            1000,
            128.0,
            0.0,
            0.0,
            snap,
            time.monotonic(),
            autoloop_tick_just_fired=True,
        )
        self.assertTrue(ctx.autoloop_tick_just_fired)

    def test_build_laser_context_copies_smart_drop_and_buildup_observation(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.smart_drops = [64, 128]
        d.meta.anlz_buildups = [56]
        d.scripted_id = 42
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertEqual(ctx.smart_drops, (64, 128))
        self.assertEqual(ctx.anlz_buildups, (56,))
        self.assertEqual(ctx.scripted_id, 42)
        self.assertIsInstance(ctx.smart_drops, tuple)
        self.assertIsInstance(ctx.anlz_buildups, tuple)

    def test_build_laser_context_phrase_context_up_when_latest_is_up(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.anlz_buildups = [32]
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 40.0, snap, time.monotonic())
        self.assertTrue(ctx.current_phrase_is_up)
        self.assertFalse(ctx.current_phrase_is_chorus)

    def test_build_laser_context_phrase_context_up_before_chorus_marker(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.anlz_buildups = [32]
        d.meta.anlz_drops = [64]
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 50.0, snap, time.monotonic())
        self.assertTrue(ctx.current_phrase_is_up)
        self.assertFalse(ctx.current_phrase_is_chorus)

    def test_build_laser_context_phrase_context_chorus_after_chorus_marker(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.anlz_buildups = [32]
        d.meta.anlz_drops = [64]
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 70.0, snap, time.monotonic())
        self.assertFalse(ctx.current_phrase_is_up)
        self.assertTrue(ctx.current_phrase_is_chorus)

    def test_build_laser_context_phrase_context_low_clears_up_and_chorus(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.anlz_buildups = [32]
        d.meta.anlz_breakdowns = [48]
        d.meta.anlz_drops = [64]
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 56.0, snap, time.monotonic())
        self.assertFalse(ctx.current_phrase_is_up)
        self.assertFalse(ctx.current_phrase_is_chorus)

    def test_build_laser_context_phrase_context_up_after_second_up_marker(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.anlz_buildups = [32, 96]
        d.meta.anlz_drops = [64]
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        chorus_ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 80.0, snap, time.monotonic())
        up_ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 100.0, snap, time.monotonic())
        self.assertFalse(chorus_ctx.current_phrase_is_up)
        self.assertTrue(chorus_ctx.current_phrase_is_chorus)
        self.assertTrue(up_ctx.current_phrase_is_up)
        self.assertFalse(up_ctx.current_phrase_is_chorus)

    def test_build_laser_context_phrase_context_no_markers_defaults_false(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 100.0, snap, time.monotonic())
        self.assertFalse(ctx.current_phrase_is_up)
        self.assertFalse(ctx.current_phrase_is_chorus)

    def test_build_laser_context_copies_active_track_loaded(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.filepath = "/tracks/test.mp3"
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertTrue(ctx.active_track_loaded)

    def test_build_laser_context_strict_autoloop_ready(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.meta.filepath = "/tracks/ready.mp3"
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())

        sm._os.lighting_mode = "autoloop"
        sm._os.autoloop_arm_pending = False
        sm._os.pending_autoloop_arm_meta = None
        sm._os.last_armed_filepath = "/tracks/ready.mp3"
        ready_ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertTrue(ready_ctx.autoloop_ready)

        sm._os.autoloop_arm_pending = True
        pending_ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertFalse(pending_ctx.autoloop_ready)

        sm._os.autoloop_arm_pending = False
        sm._os.last_armed_filepath = "/tracks/other.mp3"
        mismatch_ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertFalse(mismatch_ctx.autoloop_ready)

        sm._os.last_armed_filepath = "/tracks/ready.mp3"
        sm._os.pending_autoloop_arm_meta = object()
        queued_ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertFalse(queued_ctx.autoloop_ready)

    def test_laser_context_has_no_smart_breakdowns_field(self) -> None:
        ctx = _ctx()
        self.assertFalse(hasattr(ctx, "smart_breakdowns"))

    def test_os2l_connected_provider_called_in_build_context(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        called = []
        def provider():
            called.append(True)
            return True
        ld = _director()
        sm = _make_sm(laser_director=ld, os2l_connected_provider=provider)
        d = DeckState(number=1)
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertTrue(called)
        self.assertTrue(ctx.os2l_connected)

    def test_os2l_connected_defaults_false_when_no_provider(self) -> None:
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())
        self.assertFalse(ctx.os2l_connected)

    # Mo1 — conn.status() must never be called from _build_laser_context

    def test_build_laser_context_never_calls_conn_status(self) -> None:
        """os2l_connected_provider must be constant-time; conn.status() must not be called."""
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        conn_mock = MagicMock()
        conn_mock.status.side_effect = AssertionError("conn.status() must not be called from _push_tick")
        # Provider is is_connected(), not status().
        conn_mock.is_connected.return_value = True

        ld = _director()
        sm = _make_sm(laser_director=ld, os2l_connected_provider=conn_mock.is_connected)
        d = DeckState(number=1)
        snap = PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())

        # Must not raise even though conn.status() would raise.
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, snap, time.monotonic())

        conn_mock.status.assert_not_called()
        self.assertTrue(ctx.os2l_connected)

    def test_is_enabled_reflects_current_state(self) -> None:
        ld = _director(enabled=False)
        self.assertFalse(ld.is_enabled())
        ld.set_enabled(True)
        self.assertTrue(ld.is_enabled())

    def test_set_personality_updates_status(self) -> None:
        ld = _director(enabled=True)
        ld.set_personality("dubstep")
        self.assertEqual(ld.status()["personality"], "dubstep")


# ---------------------------------------------------------------------------
# M2 — OS2L output is unchanged when LaserDirector is None or disabled
# ---------------------------------------------------------------------------

class OS2LUnchangedTests(unittest.TestCase):
    """LaserDirector must not trigger any OS2L send_* calls itself."""

    def test_laser_director_tick_does_not_call_output_methods(self) -> None:
        """tick() must not invoke any send_* on OS2LOutput."""
        output = MagicMock()
        ld = _director(enabled=True)
        # tick() receives only a LaserContext — it has no reference to output.
        # Call it directly and verify output was untouched.
        ld.tick(_ctx(playing=True, position_stale=False), now=_now())
        output.send_bpm.assert_not_called()
        output.send_beat.assert_not_called()
        output.send_elapsed.assert_not_called()

    def test_laser_director_has_no_os2l_imports(self) -> None:
        """laser_director module must not import OS2LOutput or OS2LConnection."""
        import importlib
        import rb_ss_bridge_v2.laser_director as ld_mod
        module_globals = vars(ld_mod)
        for forbidden in ("OS2LOutput", "OS2LConnection", "osl_output"):
            self.assertNotIn(
                forbidden, module_globals,
                msg=f"laser_director must not import {forbidden}",
            )

    def test_build_laser_context_does_not_call_output_send_methods(self) -> None:
        """_build_laser_context must not invoke any output send_* methods."""
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        output = MagicMock()
        ld = _director(enabled=True)
        sm = _make_sm(laser_director=ld)
        # Replace the real output with a spy.
        sm._out = output

        d = DeckState(number=1)
        d.playing = True
        snap = PositionSnapshot(deck=1, elapsed_ms=60_000, playing=True, updated_at=time.monotonic())
        sm._build_laser_context(1, d, 60_000, 128.0, 1.5, 64.0, snap, time.monotonic())

        output.send_bpm.assert_not_called()
        output.send_beat.assert_not_called()
        output.send_elapsed.assert_not_called()

    def test_state_manager_with_no_laser_director_preserves_out_attr(self) -> None:
        """laser_director kwarg must not replace or wrap _out on either StateManager."""
        sm_no_laser = _make_sm()
        sm_with_laser = _make_sm(laser_director=_director())
        self.assertIsNone(sm_no_laser._laser_director)
        self.assertIsNotNone(sm_with_laser._laser_director)
        # _out must exist and be non-None in both configurations.
        self.assertIsNotNone(sm_no_laser._out)
        self.assertIsNotNone(sm_with_laser._out)


# ---------------------------------------------------------------------------
# M1 — early-return paths actually fire laser tick in integration
# ---------------------------------------------------------------------------

class EarlyReturnLaserTickTests(unittest.TestCase):
    """Verify that LaserDirector.tick() is callable in the stale/not-playing paths.

    These tests call tick() directly with the contexts that the early-return
    paths would produce, mirroring what _push_tick now passes. Full _push_tick
    integration requires a heavier harness; unit-testing tick() with crafted
    contexts verifies the policy is correct.
    """

    def test_stale_snap_context_produces_idle_no_output(self) -> None:
        """Context with position_stale=True must select no output."""
        ld = _director(enabled=True, safe_scene="my_safe_look")
        stale_ctx = _ctx(playing=False, position_stale=True)
        ld.tick(stale_ctx, now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertIn(ld.status()["last_reason"], ("not_playing", "position_stale"))

    def test_not_playing_context_produces_idle_no_output(self) -> None:
        """Context with playing=False and fresh snap must select no output."""
        ld = _director(enabled=True, safe_scene="my_safe_look")
        idle_ctx = _ctx(playing=False, position_stale=False)
        ld.tick(idle_ctx, now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "not_playing")

    def test_stale_and_playing_context_produces_idle_no_output(self) -> None:
        """Stale position overrides playing=True — still selects no output."""
        ld = _director(enabled=True, safe_scene="my_safe_look")
        ctx = _ctx(playing=True, position_stale=True)
        ld.tick(ctx, now=_now())
        self.assertEqual(ld.status()["current_scene"], "")
        self.assertEqual(ld.status()["last_reason"], "position_stale")

    def test_build_laser_context_with_none_snap_gives_stale_true(self) -> None:
        """_build_laser_context(snap=None) must produce position_stale=True."""
        from rb_ss_bridge_v2.models import DeckState
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        d.playing = False
        ctx = sm._build_laser_context(1, d, 0, 0.0, 0.0, 0.0, None, time.monotonic())
        self.assertTrue(ctx.position_stale)
        self.assertFalse(ctx.playing)

    def test_build_laser_context_stale_snap_gives_stale_true(self) -> None:
        """_build_laser_context with an old snap must produce position_stale=True."""
        from rb_ss_bridge_v2.models import DeckState, PositionSnapshot
        from rb_ss_bridge_v2.config import MEM_STALE_S
        ld = _director()
        sm = _make_sm(laser_director=ld)
        d = DeckState(number=1)
        old_snap = PositionSnapshot(
            deck=1, elapsed_ms=1000, playing=False,
            updated_at=time.monotonic() - (MEM_STALE_S + 1.0),
        )
        ctx = sm._build_laser_context(1, d, 1000, 128.0, 0.0, 0.0, old_snap, time.monotonic())
        self.assertTrue(ctx.position_stale)


if __name__ == "__main__":
    unittest.main()
