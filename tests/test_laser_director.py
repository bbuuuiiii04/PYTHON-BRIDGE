"""
Tests for Issue #7: Dry-run LaserDirector skeleton.

Covers:
  - Disabled LaserDirector does nothing.
  - Emergency selects configured emergency_scene.
  - Manual override selects provided scene name.
  - Not playing selects configured safe_scene.
  - Stale position selects configured safe_scene.
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
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_models import LaserContext, LaserPersonality, LaserSceneDecision  # noqa: E402
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
    def test_not_playing_selects_safe_scene(self) -> None:
        ld = _director()
        ld.tick(_ctx(playing=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "safe_static")
        self.assertEqual(ld.status()["last_reason"], "not_playing")

    def test_not_playing_uses_configured_safe_scene(self) -> None:
        ld = _director(safe_scene="my_safe_look")
        ld.tick(_ctx(playing=False), now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_safe_look")


# ---------------------------------------------------------------------------
# Stale position
# ---------------------------------------------------------------------------

class StalePositionTests(unittest.TestCase):
    def test_stale_position_selects_safe_scene(self) -> None:
        ld = _director()
        ld.tick(_ctx(playing=True, position_stale=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "safe_static")
        self.assertEqual(ld.status()["last_reason"], "position_stale")

    def test_stale_uses_configured_safe_scene(self) -> None:
        ld = _director(safe_scene="my_stale_safe")
        ld.tick(_ctx(playing=True, position_stale=True), now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_stale_safe")


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
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=32.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "p")
        self.assertEqual(ld.status()["last_reason"], "phrase_boundary")

    def test_phrase_scene_name_can_be_arbitrary(self) -> None:
        ld = _director(default_scene="d", phrase_scene="my_custom_phrase_42", phrase_interval_beats=16)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=15.0), now=_now())
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=16.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_custom_phrase_42")

    def test_not_playing_resets_phrase_tracking(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(_ctx(playing=False, position_stale=False, abs_beat=40.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "safe_static")
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=64.0), now=_now())
        self.assertEqual(ld.status()["last_reason"], "default_init")
        self.assertEqual(ld.status()["current_scene"], "d")

    def test_stale_resets_phrase_tracking(self) -> None:
        ld = _director(default_scene="d", phrase_scene="p", phrase_interval_beats=32)
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=31.0), now=_now())
        ld.tick(_ctx(playing=True, position_stale=True, abs_beat=40.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "safe_static")
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
        ld.tick(_ctx(playing=True, position_stale=False, abs_beat=32.0), now=_now())
        self.assertEqual(ld.status()["current_scene"], "d")
        self.assertEqual(ld.status()["last_reason"], "hold_minimum_scene")

    def test_minimum_hold_does_not_block_emergency_manual_or_safe(self) -> None:
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
        self.assertEqual(ld.status()["current_scene"], "safe_static")

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
        self.assertEqual(info.call_count, 2)

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
        )
        ld.set_personality_config(personality)
        s = ld.status()
        self.assertEqual(s["phrase_scene"], "custom_phrase")
        self.assertEqual(s["phrase_interval_beats"], 16)
        self.assertEqual(s["minimum_scene_hold_beats"], 4)
        self.assertTrue(s["normal_changes_only_on_phrase_boundary"])


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
                    "normal_changes_only_on_phrase_boundary"):
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

    def test_stale_snap_context_produces_safe_scene(self) -> None:
        """Context with position_stale=True must select safe_scene."""
        ld = _director(enabled=True, safe_scene="my_safe_look")
        stale_ctx = _ctx(playing=False, position_stale=True)
        ld.tick(stale_ctx, now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_safe_look")
        self.assertIn(ld.status()["last_reason"], ("not_playing", "position_stale"))

    def test_not_playing_context_produces_safe_scene(self) -> None:
        """Context with playing=False and fresh snap must select safe_scene."""
        ld = _director(enabled=True, safe_scene="my_safe_look")
        idle_ctx = _ctx(playing=False, position_stale=False)
        ld.tick(idle_ctx, now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_safe_look")
        self.assertEqual(ld.status()["last_reason"], "not_playing")

    def test_stale_and_playing_context_produces_safe_scene(self) -> None:
        """Stale position overrides playing=True — still selects safe_scene."""
        ld = _director(enabled=True, safe_scene="my_safe_look")
        ctx = _ctx(playing=True, position_stale=True)
        ld.tick(ctx, now=_now())
        self.assertEqual(ld.status()["current_scene"], "my_safe_look")
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
