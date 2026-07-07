"""M1b integration tests for the LED color engine.

Covers the WI-1..WI-5 wiring that injects the pure ``LedColorEngine`` into the
live dispatch path:

  1. Engine None / disabled ⇒ byte-identical dispatch (no ``color`` injected).
  2. ``_led_automation_role_key`` byte-identity + ``_led_last_section_cycle``
     population across both ``RBSS_LED_PHRASE_MONOTONIC`` settings.
  3. Renderer ``_drop_chase`` / ``_post_drop_chase`` prefer injected
     ``params["color"]`` and fall back to the suffix color when absent.
  4. Director DIY-eligibility filter (full-bank fallback + subset selection).
  5. Injection merge preserves ``sync_mode`` / ``beat_division`` and only
     colors engine-tagged, non-exempt looks.

These tests do NOT modify the pure engine (M1a) — they exercise the M1b seam.
"""
from __future__ import annotations

import copy
import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_config import (  # noqa: E402
    load_led_look_director_config_from_dict,
)
from rb_ss_bridge_v2.led_look_director import LEDLookDirector  # noqa: E402
from rb_ss_bridge_v2.led_models import (  # noqa: E402
    ColorEngineConfig,
    LEDContext,
    LEDLookDecision,
    Palette,
)
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(*, enabled: bool = True, **overrides) -> LedColorEngine:
    """Build a deterministic engine with a tiny two-palette library."""
    palettes = {
        "blue_cyan": Palette(range=("cyan", "blue"), white=0.0, spread=0.10, weight=10),
        "red": Palette(range=("red", "red"), white=0.0, spread=0.10, weight=10),
    }
    cfg_kwargs = dict(
        enabled=enabled,
        palettes=palettes,
        palette_dwell_tracks=4,
        set_seed_mode="fixed:12345",
    )
    cfg_kwargs.update(overrides)
    cfg = ColorEngineConfig(**cfg_kwargs)
    # set_seed pinned for deterministic palette/focus draws
    return LedColorEngine(cfg, set_seed=12345)


class _DispatchDirector:
    """Minimal director stub returning a single fixed automation decision."""

    def __init__(self, decision: LEDLookDecision) -> None:
        self._decision = decision
        self.tick_calls: list[LEDContext] = []

    def tick(self, context: LEDContext | None = None) -> LEDLookDecision | None:
        if context is not None:
            self.tick_calls.append(context)
        return self._decision

    def status(self) -> dict:
        return {"available": True, "enabled": True, "automation_enabled": True}


class _RecordingAdapter:
    def __init__(self) -> None:
        self.trigger_calls: list[LEDLookDecision] = []

    def trigger(self, decision: LEDLookDecision) -> bool:
        self.trigger_calls.append(decision)
        return True

    def status(self) -> dict:
        return {"available": True}


def _make_sm(*, director, adapter, engine=None) -> StateManager:
    return StateManager(
        queue.Queue(maxsize=64),
        PositionCache(),
        Mock(),
        led_look_director=director,
        led_scene_adapter=adapter,
        led_color_engine=engine,
    )


def _arm_automation(sm: StateManager) -> None:
    """Open all the gates so _dispatch_led_automation reaches the seam."""
    sm._led_enabled_latch = True
    sm._led_automation_enabled_latch = True
    sm._led_scripted_mode_automation_latch = False
    sm._led_manual_override = ""
    sm._led_emergency_blackout = False
    sm._os.lighting_mode = "autoloop"


def _playing_deck(sm: StateManager, *, load_gen: int = 11, content_id: str = "cid-1"):
    d = sm._deck[1]
    d.playing = True
    d.scripted_id = 0
    d.load_gen = load_gen
    d.meta.filepath = "/tracks/current.wav"
    d.meta.content_id = content_id
    d.meta.bpm = 0.0
    return d


def _groove_decision(
    look: str,
    *,
    color_source: str = "engine",
    scene_ref: str = "drop_chase_blue",
    params: dict | None = None,
) -> LEDLookDecision:
    return LEDLookDecision(
        look=look,
        target="room_perimeter",
        action="realtime",
        scene_ref=scene_ref,
        reason="role_entry:groove",
        source="automation",
        priority=2,
        role="groove",
        backend="realtime_razer",
        params=params if params is not None else {},
        color_source=color_source,
    )


# ---------------------------------------------------------------------------
# Test 1 — enabled:false / engine None regression (MOST IMPORTANT)
# ---------------------------------------------------------------------------

class EngineOffRegressionTests(unittest.TestCase):
    def _run_dispatch(self, *, engine):
        decision = _groove_decision(
            "rt_groove_chase_blue",
            params={"sync_mode": "beat", "beat_division": 4},
        )
        director = _DispatchDirector(decision)
        adapter = _RecordingAdapter()
        sm = _make_sm(director=director, adapter=adapter, engine=engine)
        _arm_automation(sm)
        d = _playing_deck(sm)
        sp = SmartPhrasingState(
            abs_beat=84.0,
            current_phrase_label="other",
            current_phrase_start_beat=64.0,
            beats_into_phrase=20.0,
        )
        sm._dispatch_led_automation(active=1, d=d, sp_state=sp)
        return adapter.trigger_calls

    def test_engine_none_no_color_injected(self) -> None:
        calls = self._run_dispatch(engine=None)
        self.assertEqual(len(calls), 1)
        dispatched = calls[0]
        self.assertNotIn("color", dict(dispatched.params))
        # params byte-identical to the original decision's params
        self.assertEqual(
            dict(dispatched.params),
            {"sync_mode": "beat", "beat_division": 4},
        )

    def test_engine_disabled_no_color_injected(self) -> None:
        calls = self._run_dispatch(engine=_engine(enabled=False))
        self.assertEqual(len(calls), 1)
        self.assertNotIn("color", dict(calls[0].params))
        self.assertEqual(
            dict(calls[0].params),
            {"sync_mode": "beat", "beat_division": 4},
        )


# ---------------------------------------------------------------------------
# Test 2 — role_key byte-identity + _led_last_section_cycle population
# ---------------------------------------------------------------------------

class RoleKeyByteIdentityTests(unittest.TestCase):
    def _sm(self) -> StateManager:
        sm = _make_sm(director=Mock(), adapter=Mock(), engine=None)
        return sm

    def _deck(self, sm: StateManager):
        d = sm._deck[1]
        d.load_gen = 11
        return d

    def _role_key_and_struct(self, sm, d, sp, role):
        key = sm._led_automation_role_key(1, d, sp, role)
        section_id, cycle = sm._led_last_section_cycle
        return key, section_id, cycle

    def test_role_key_strings_unchanged_and_struct_consistent(self) -> None:
        # Expected strings are exactly what _led_automation_role_key produced
        # before M1b (no marker f-string was altered). We assert the marker is
        # the trailing field of the key and section_id is a prefix of it.
        for monotonic in (True, False):
            sm = self._sm()
            sm._phrase_monotonic_enabled = monotonic
            d = self._deck(sm)

            # drop (no :c cycle → section_id == marker, cycle 0)
            sm._led_first_drop_anchor_beat = 64.0
            key, sid, cyc = self._role_key_and_struct(
                sm, d, SmartPhrasingState(active_drop_beat=64.0), "drop"
            )
            marker = key.split(":", 3)[3]
            self.assertEqual(key, "1:11:drop:64.000")
            self.assertEqual(cyc, 0)
            self.assertEqual(sid, marker)
            self.assertTrue(marker.startswith(sid) or sid == marker)

            # groove (has :c cycle → section_id is a prefix of marker)
            sp = SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            )
            key, sid, cyc = self._role_key_and_struct(sm, d, sp, "groove")
            marker = key.split(":", 3)[3]
            expected_groove = (
                "1:11:groove:other:seq0:c0"
                if monotonic
                else "1:11:groove:other:64.000:c0"
            )
            self.assertEqual(key, expected_groove)
            self.assertTrue(
                marker.startswith(sid),
                msg=f"groove section_id={sid!r} not prefix of marker={marker!r}",
            )
            self.assertEqual(marker, f"{sid}:c{cyc}")

            # post_drop (has :c cycle)
            sm._led_first_drop_anchor_beat = 64.0
            sp = SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="chorus",
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            )
            key, sid, cyc = self._role_key_and_struct(sm, d, sp, "post_drop")
            marker = key.split(":", 3)[3]
            expected_post = (
                "1:11:post_drop:seq0:c0"
                if monotonic
                else "1:11:post_drop:64.000:c0"
            )
            self.assertEqual(key, expected_post)
            self.assertEqual(marker, f"{sid}:c{cyc}")

            # ambient: monotonic path rotates inside the section; legacy does not.
            sp = SmartPhrasingState(current_phrase_label="intro")
            key, sid, cyc = self._role_key_and_struct(sm, d, sp, "ambient")
            marker = key.split(":", 3)[3]
            self.assertEqual(cyc, 0)
            if monotonic:
                self.assertEqual(key, "1:11:ambient:intro:seq0:c0")
                self.assertEqual(sid, "intro:seq0")
                self.assertEqual(marker, f"{sid}:c{cyc}")
            else:
                self.assertEqual(key, "1:11:ambient:intro")
                self.assertEqual(sid, marker)

    def test_groove_holds_within_cycle_and_steps_across(self) -> None:
        # Same section across the 32-beat cycle → same cycle int; new cycle
        # bumps it. (Mirrors the existing role_key cycle test, but asserts the
        # structured cycle field tracks it.)
        sm = self._sm()
        sm._phrase_monotonic_enabled = False
        d = self._deck(sm)

        _, sid20, cyc20 = self._role_key_and_struct(
            sm,
            d,
            SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            ),
            "groove",
        )
        _, sid40, cyc40 = self._role_key_and_struct(
            sm,
            d,
            SmartPhrasingState(
                abs_beat=104.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                beats_into_phrase=40.0,
            ),
            "groove",
        )
        self.assertEqual(sid20, sid40)  # same section
        self.assertEqual(cyc20, 0)
        self.assertEqual(cyc40, 1)  # crossed a 32-beat boundary


# ---------------------------------------------------------------------------
# Test 3 — dispatch-path intra-section rotation
# ---------------------------------------------------------------------------

class IntraSectionDispatchRotationTests(unittest.TestCase):
    def _director(self) -> LEDLookDirector:
        cfg = copy.deepcopy(_diy_director_config())
        cfg["banks"]["default"]["buildup"] = ["diy_red", "diy_blue"]
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        director = LEDLookDirector(result.config)
        director._role_cursors["buildup"] = 0
        return director

    def test_buildup_cycle_boundary_dispatches_next_director_look(self) -> None:
        director = self._director()
        adapter = _RecordingAdapter()
        sm = _make_sm(director=director, adapter=adapter, engine=None)
        _arm_automation(sm)
        sm._sp_phrase_lookahead = 128.0
        d = _playing_deck(sm)

        sm._dispatch_led_automation(
            active=1,
            d=d,
            sp_state=SmartPhrasingState(
                abs_beat=64.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
                next_smart_drop_beat=164.0,
                beats_to_next_drop=100.0,
            ),
        )
        sm._dispatch_led_automation(
            active=1,
            d=d,
            sp_state=SmartPhrasingState(
                abs_beat=104.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
                next_smart_drop_beat=164.0,
                beats_to_next_drop=60.0,
            ),
        )

        self.assertEqual(
            [call.look for call in adapter.trigger_calls],
            ["diy_red", "diy_blue"],
        )
        self.assertEqual(director._role_cursors["buildup"], 2)


# ---------------------------------------------------------------------------
# Test 4 — Renderer prefer params["color"]
# ---------------------------------------------------------------------------

class RendererPreferParamsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = GoveeFrameRenderer()

    def _lit_colors(self, frame):
        return {px for px in frame if px != (0, 0, 0)}

    def _has_red(self, frame) -> bool:
        # color1-driven comets carry red when red is injected.
        return any(px[0] > 0 for px in frame)

    def _has_blue(self, frame) -> bool:
        return any(px[2] > 0 for px in frame)

    def test_drop_chase_prefers_injected_color(self) -> None:
        # color1 (the injected slot) drives even-index comets; color2 stays the
        # baked suffix color (blue) per the brief. So injecting red must make
        # red appear in a look whose suffix has NO red at all.
        injected = self.renderer.render(
            "drop_chase_blue",
            beat_pos=12.0, local_t=0.0, frame_index=0,
            params={"color": [255, 0, 0]}, segments=20, seed=7,
        )
        suffix = self.renderer.render(
            "drop_chase_blue",
            beat_pos=12.0, local_t=0.0, frame_index=0,
            params={}, segments=20, seed=7,
        )
        self.assertTrue(self._lit_colors(injected))
        self.assertTrue(self._lit_colors(suffix))
        # Suffix-only (blue) frame has zero red; injected frame introduces red.
        self.assertFalse(self._has_red(suffix), msg="blue suffix unexpectedly red")
        self.assertTrue(self._has_red(injected), msg="injected red did not appear")

    def test_post_drop_chase_prefers_injected_color(self) -> None:
        injected = self.renderer.render(
            "post_drop_chase_blue",
            beat_pos=4.0, local_t=0.0, frame_index=0,
            params={"color": [255, 0, 0]}, segments=20, seed=7,
        )
        suffix = self.renderer.render(
            "post_drop_chase_blue",
            beat_pos=4.0, local_t=0.0, frame_index=0,
            params={}, segments=20, seed=7,
        )
        self.assertTrue(self._lit_colors(injected))
        self.assertTrue(self._lit_colors(suffix))
        self.assertFalse(self._has_red(suffix), msg="blue suffix unexpectedly red")
        self.assertTrue(self._has_red(injected), msg="injected red did not appear")

    def test_post_drop_chase_empty_params_unchanged(self) -> None:
        # Regression: empty params must reproduce the suffix-color behavior
        # exactly (engine-off byte-identity at the renderer level).
        with_empty = self.renderer.render(
            "post_drop_chase_cyan",
            beat_pos=4.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=7,
        )
        # cyan suffix → lit pixels have g and b high, r ~0
        lit = [px for px in with_empty if px != (0, 0, 0)]
        self.assertTrue(lit)
        self.assertTrue(all(px[1] >= px[0] and px[2] >= px[0] for px in lit))


# ---------------------------------------------------------------------------
# Test 5 — Director DIY-eligibility filter
# ---------------------------------------------------------------------------

def _diy_director_config() -> dict:
    return {
        "schema_version": 1,
        "enabled": True,
        "dry_run": True,
        "automation_enabled": True,
        "targets": {
            "room_perimeter": {
                "label": "Strip Light",
                "device_ref": "local-ref",
                "expected_model": "H612D",
                "control_route": "govee_platform_dynamic_scene",
                "capabilities": ["scene", "off"],
            }
        },
        "looks": {
            "diy_red": {
                "target": "room_perimeter", "action": "diy_scene",
                "scene_ref": "111", "fallback": "room_blackout",
                "safety_class": "safe", "backend": "cloud_diy",
            },
            "diy_blue": {
                "target": "room_perimeter", "action": "diy_scene",
                "scene_ref": "222", "fallback": "room_blackout",
                "safety_class": "safe", "backend": "cloud_diy",
            },
            "room_blackout": {
                "target": "room_perimeter", "action": "off",
                "fallback": "", "safety_class": "blackout",
            },
            "room_safe_default": {
                "target": "room_perimeter", "action": "scene",
                "scene_ref": "Release-A", "fallback": "room_blackout",
                "safety_class": "safe",
            },
        },
        "banks": {
            "default": {
                "ambient": ["room_safe_default"],
                "groove": ["diy_red", "diy_blue"],
                "buildup": ["room_safe_default"],
                "pre_drop": [],
                "drop": ["room_safe_default"],
                "post_drop": [],
                "breakdown": ["diy_red", "diy_blue"],
                "utility": ["room_safe_default", "room_blackout"],
            }
        },
        "safe_default": "room_safe_default",
        "blackout": "room_blackout",
        "rate_limits": {
            "queue_maxsize": 8, "scene_retrigger_cooldown_s": 4.0,
            "high_impact_cooldown_s": 4.0, "request_timeout_s": 2.0,
            "worker_shutdown_timeout_s": 1.0,
        },
        "safety": {
            "max_brightness": 100, "allow_strobe": True,
            "max_strobe_duration_ms": 750, "high_impact_cooldown_s": 4.0,
            "drop_flash_duration_ms": 750,
            "emergency_blackout_always_available": True,
            "scripted_mode_automation": False,
        },
    }


class DirectorDIYFilterTests(unittest.TestCase):
    def _director(self) -> LEDLookDirector:
        cfg = copy.deepcopy(_diy_director_config())
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=result.errors)
        return LEDLookDirector(result.config)

    def test_reject_all_falls_back_to_full_bank(self) -> None:
        director = self._director()
        # Predicate rejects everything → empty subset → full-bank fallback.
        ctx = LEDContext(role="groove", diy_eligible=lambda _name: False)
        decision = director.tick(ctx)
        self.assertIsNotNone(decision)
        self.assertIn(decision.look, {"diy_red", "diy_blue"})

    def test_breakdown_diy_only_bank_never_emptied(self) -> None:
        # C4 invariant: a DIY-only bank with no matching palette must still
        # return a candidate (full-bank fallback).
        director = self._director()
        ctx = LEDContext(role="breakdown", diy_eligible=lambda _name: False)
        decision = director.tick(ctx)
        self.assertIsNotNone(decision)
        self.assertIn(decision.look, {"diy_red", "diy_blue"})

    def test_subset_selection_stays_within_eligible(self) -> None:
        director = self._director()
        ctx = LEDContext(
            role="groove",
            diy_eligible=lambda name: name == "diy_blue",
        )
        for _ in range(6):
            decision = director.tick(ctx)
            self.assertIsNotNone(decision)
            self.assertEqual(decision.look, "diy_blue")

    def test_none_predicate_no_filtering(self) -> None:
        director = self._director()
        ctx = LEDContext(role="groove", diy_eligible=None)
        decision = director.tick(ctx)
        self.assertIsNotNone(decision)
        self.assertIn(decision.look, {"diy_red", "diy_blue"})


# ---------------------------------------------------------------------------
# Test 6 — Injection merge
# ---------------------------------------------------------------------------

class InjectionMergeTests(unittest.TestCase):
    def _dispatch(self, decision: LEDLookDecision, *, engine):
        director = _DispatchDirector(decision)
        adapter = _RecordingAdapter()
        sm = _make_sm(director=director, adapter=adapter, engine=engine)
        _arm_automation(sm)
        d = _playing_deck(sm)
        sp = SmartPhrasingState(
            abs_beat=84.0,
            current_phrase_label="other",
            current_phrase_start_beat=64.0,
            beats_into_phrase=20.0,
        )
        sm._dispatch_led_automation(active=1, d=d, sp_state=sp)
        self.assertEqual(len(adapter.trigger_calls), 1)
        return adapter.trigger_calls[0]

    def test_engine_look_gets_color_and_keeps_sync_params(self) -> None:
        decision = _groove_decision(
            "rt_groove_chase_blue",
            color_source="engine",
            scene_ref="drop_chase_blue",
            params={"sync_mode": "beat", "beat_division": 4},
        )
        dispatched = self._dispatch(decision, engine=_engine())
        params = dict(dispatched.params)
        self.assertIn("color", params)
        self.assertEqual(len(params["color"]), 3)
        # MERGE — pre-existing static params survive.
        self.assertEqual(params["sync_mode"], "beat")
        self.assertEqual(params["beat_division"], 4)

    def test_baked_look_gets_no_color(self) -> None:
        decision = _groove_decision(
            "rt_groove_chase_blue",
            color_source="baked",
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(decision, engine=_engine())
        self.assertNotIn("color", dict(dispatched.params))
        self.assertEqual(dict(dispatched.params), {"sync_mode": "beat"})

    def test_exempt_look_gets_no_color(self) -> None:
        engine = _engine(exempt_looks=("rt_exempt_look",))
        decision = _groove_decision(
            "rt_exempt_look",
            color_source="engine",
            params={"beat_division": 2},
        )
        dispatched = self._dispatch(decision, engine=engine)
        self.assertNotIn("color", dict(dispatched.params))
        self.assertEqual(dict(dispatched.params), {"beat_division": 2})

    def test_gradient_sweep_gets_color_a_b(self) -> None:
        # gradient_sweep is the only effect whose param-keys include color_a,
        # so multi=True only there → color_a/color_b injected.
        decision = _groove_decision(
            "rt_gradient",
            color_source="engine",
            scene_ref="gradient_sweep",
            params={},
        )
        dispatched = self._dispatch(decision, engine=_engine())
        params = dict(dispatched.params)
        self.assertIn("color", params)
        self.assertIn("color_a", params)
        self.assertIn("color_b", params)

    def test_non_gradient_look_gets_no_color_a_b(self) -> None:
        decision = _groove_decision(
            "rt_groove_chase_blue",
            color_source="engine",
            scene_ref="drop_chase_blue",
            params={},
        )
        dispatched = self._dispatch(decision, engine=_engine())
        params = dict(dispatched.params)
        self.assertIn("color", params)
        self.assertNotIn("color_a", params)
        self.assertNotIn("color_b", params)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
