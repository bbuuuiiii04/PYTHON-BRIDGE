"""M2 Phase 2b tests — slot_colors injection and config loading.

Covers (per spec §5):
1. slot look → `decision.params["slot_colors"]` len 6, slot5==(255,255,255)
2. non-slot look → still the `color` path
3. `enabled:false` / exempt / baked ⇒ NO `slot_colors` (byte-identical)
4. engine exception ⇒ decision unmodified + `_led_last_error` set
5. sand scene_ref NOT in `SLOT_EFFECTS`
6. cloud/DIY decisions get no slot coloring
7. Config-load test: the 6 new looks load, `available=True`; bad param -> `available=False`;
   bad color_engine -> `available=True` but engine disabled.
8. Baked-sand negative tests.
"""
from __future__ import annotations

import copy
import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    SLOT_EFFECTS,
    _EFFECTS,
    GoveeFrameRenderer,
)
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
    palettes = {
        "blue_cyan": Palette(range=("cyan", "blue"), white=0.0, spread=0.10, weight=10),
    }
    cfg_kwargs = dict(
        enabled=enabled,
        palettes=palettes,
        palette_dwell_tracks=4,
        set_seed_mode="fixed:12345",
    )
    cfg_kwargs.update(overrides)
    cfg = ColorEngineConfig(**cfg_kwargs)
    return LedColorEngine(cfg, set_seed=12345)

class _DispatchDirector:
    def __init__(self, decision: LEDLookDecision) -> None:
        self._decision = decision

    def tick(self, context: LEDContext | None = None) -> LEDLookDecision | None:
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
    sm._led_enabled_latch = True
    sm._led_automation_enabled_latch = True
    sm._led_scripted_mode_automation_latch = False
    sm._led_manual_override = ""
    sm._led_emergency_blackout = False
    sm._os.lighting_mode = "autoloop"

def _playing_deck(sm: StateManager):
    d = sm._deck[1]
    d.playing = True
    d.scripted_id = 0
    d.load_gen = 11
    d.meta.filepath = "/tracks/current.wav"
    d.meta.content_id = "cid-1"
    d.meta.bpm = 0.0
    return d

def _decision(
    look: str,
    *,
    color_source: str = "engine",
    scene_ref: str,
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
# Config Loader Helpers
# ---------------------------------------------------------------------------

def _base_config() -> dict:
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
                "realtime": {
                    "enabled": True,
                    "ip": "192.168.1.100",
                    "header_bytes": [1, 2, 3, 4, 5],
                    "activate_pt": "pt1",
                    "deactivate_pt": "pt2"
                },
            }
        },
        "color_engine": {
            "enabled": True,
            "palettes": {
                "blue_cyan": {"range": ["cyan", "blue"]}
            },
            "exempt_looks": ["rt_breakdown_star_twinkle_sand"],
        },
        "looks": {
            "room_blackout": {
                "target": "room_perimeter", "action": "off",
                "fallback": "", "safety_class": "blackout",
            },
            "rt_room_blackout": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "blackout",
                "fallback": "", "safety_class": "blackout",
            },
            "rt_groove_center_chase": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "groove_center_chase",
                "fallback": "rt_room_blackout", "safety_class": "safe",
                "brightness": 100, "allow_strobe": False, "color_source": "engine",
            },
            "rt_groove_center_burst_retract": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "groove_center_burst_retract",
                "fallback": "rt_room_blackout", "safety_class": "safe",
                "brightness": 100, "allow_strobe": False, "color_source": "engine",
            },
            "rt_post_drop_firework_chase": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "post_drop_firework_chase",
                "fallback": "rt_room_blackout", "safety_class": "strobe",
                "brightness": 100, "allow_strobe": True, "color_source": "engine",
            },
            "rt_breakdown_full_breathing": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "breakdown_full_breathing",
                "fallback": "rt_room_blackout", "safety_class": "safe",
                "brightness": 100, "allow_strobe": False, "color_source": "engine",
            },
            "rt_breakdown_star_twinkle": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "breakdown_star_twinkle",
                "fallback": "rt_room_blackout", "safety_class": "safe",
                "brightness": 100, "allow_strobe": False, "color_source": "engine",
            },
            "rt_breakdown_star_twinkle_sand": {
                "target": "room_perimeter", "action": "realtime",
                "backend": "realtime_razer", "scene_ref": "breakdown_star_twinkle_sand",
                "fallback": "rt_room_blackout", "safety_class": "safe",
                "brightness": 100, "allow_strobe": False, "color_source": "baked",
            },
        },
        "banks": {
            "default": {
                "ambient": [],
                "groove": [],
                "buildup": [],
                "pre_drop": [],
                "drop": [],
                "post_drop": [],
                "breakdown": [],
                "utility": ["room_blackout"],
            }
        },
        "safe_default": "room_blackout",
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

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class SlotInjectionTests(unittest.TestCase):
    def _dispatch(self, dec: LEDLookDecision, *, engine):
        director = _DispatchDirector(dec)
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

    def test_slot_look_gets_slot_colors(self) -> None:
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",  # in SLOT_EFFECTS
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(dec, engine=_engine())
        params = dict(dispatched.params)
        self.assertNotIn("color", params)
        self.assertIn("slot_colors", params)
        self.assertEqual(len(params["slot_colors"]), 6)
        self.assertEqual(tuple(params["slot_colors"][5]), (255, 255, 255))
        self.assertEqual(params["sync_mode"], "beat")

    def test_non_slot_look_gets_color(self) -> None:
        dec = _decision(
            "rt_drop_chase_blue",
            scene_ref="drop_chase_blue",  # NOT in SLOT_EFFECTS
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(dec, engine=_engine())
        params = dict(dispatched.params)
        self.assertIn("color", params)
        self.assertNotIn("slot_colors", params)
        self.assertEqual(params["sync_mode"], "beat")

    def test_enabled_false_byte_identical(self) -> None:
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(dec, engine=_engine(enabled=False))
        params = dict(dispatched.params)
        self.assertNotIn("color", params)
        self.assertNotIn("slot_colors", params)
        self.assertEqual(params, {"sync_mode": "beat"})

    def test_exempt_look_no_slot_colors(self) -> None:
        engine = _engine(exempt_looks=("rt_groove_center_chase",))
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(dec, engine=engine)
        params = dict(dispatched.params)
        self.assertNotIn("slot_colors", params)
        self.assertNotIn("color", params)

    def test_baked_look_no_slot_colors(self) -> None:
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",
            color_source="baked",
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(dec, engine=_engine())
        params = dict(dispatched.params)
        self.assertNotIn("slot_colors", params)
        self.assertNotIn("color", params)

    def test_cloud_diy_decisions_get_no_slot_colors(self) -> None:
        dec = LEDLookDecision(
            look="diy_red",
            target="room_perimeter",
            action="diy_scene",
            scene_ref="111",
            reason="role_entry:groove",
            source="automation",
            priority=2,
            role="groove",
            backend="cloud_diy",
            params={"sync_mode": "beat"},
            color_source="engine",
        )
        dispatched = self._dispatch(dec, engine=_engine())
        params = dict(dispatched.params)
        # Because scene_ref "111" is not in SLOT_EFFECTS, it falls to resolve_color
        # which ignores cloud_diy if not specifically supported. Actually resolve_color
        # might inject color for DIY if it's eligible, but it shouldn't inject slot_colors.
        self.assertNotIn("slot_colors", params)

    def test_engine_exception_unmodified_and_error_set(self) -> None:
        engine = _engine()
        engine.resolve_slot_colors = Mock(side_effect=ValueError("Test engine error"))
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",
            params={"sync_mode": "beat"},
        )
        director = _DispatchDirector(dec)
        
        captured_error = []
        
        class _TestAdapter:
            def __init__(self, sm_ref):
                self.sm_ref = sm_ref
                self.trigger_calls = []
            def trigger(self, decision):
                captured_error.append(self.sm_ref._led_last_error)
                self.trigger_calls.append(decision)
                return True
            def status(self):
                return {"available": True}

        sm = _make_sm(director=director, adapter=None, engine=engine)
        adapter = _TestAdapter(sm)
        sm._led_scene_adapter = adapter

        _arm_automation(sm)
        sm._dispatch_led_automation(active=1, d=_playing_deck(sm), sp_state=SmartPhrasingState())
        
        # Decision must be unmodified
        self.assertEqual(len(adapter.trigger_calls), 1)
        dispatched = adapter.trigger_calls[0]
        params = dict(dispatched.params)
        self.assertNotIn("slot_colors", params)
        self.assertEqual(params, {"sync_mode": "beat"})
        # Error logged in sm before cleared
        self.assertEqual(captured_error[0], "color_engine_error:ValueError")

    def test_exception_during_snapshot_leaves_decision_unmodified(self) -> None:
        engine = _engine()
        engine.resolve_slot_colors = Mock(return_value={"slot_colors": [[10, 10, 10]] * 6})
        engine.snapshot = Mock(side_effect=RuntimeError("Test snapshot error"))
        
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",
            params={"sync_mode": "beat"},
        )
        director = _DispatchDirector(dec)
        
        captured_error = []
        
        class _TestAdapter:
            def __init__(self, sm_ref):
                self.sm_ref = sm_ref
                self.trigger_calls = []
            def trigger(self, decision):
                captured_error.append(self.sm_ref._led_last_error)
                self.trigger_calls.append(decision)
                return True
            def status(self):
                return {"available": True}

        sm = _make_sm(director=director, adapter=None, engine=engine)
        adapter = _TestAdapter(sm)
        sm._led_scene_adapter = adapter

        _arm_automation(sm)
        sm._dispatch_led_automation(active=1, d=_playing_deck(sm), sp_state=SmartPhrasingState())
        
        # Decision must be unmodified
        self.assertEqual(len(adapter.trigger_calls), 1)
        dispatched = adapter.trigger_calls[0]
        params = dict(dispatched.params)
        self.assertNotIn("slot_colors", params)
        self.assertEqual(params, {"sync_mode": "beat"})
        # Error logged in sm before cleared
        self.assertEqual(captured_error[0], "color_engine_error:RuntimeError")

    def test_end_to_end_slot_render_with_palette(self) -> None:
        dec = _decision(
            "rt_groove_center_chase",
            scene_ref="groove_center_chase",
            params={"sync_mode": "beat"},
        )
        dispatched = self._dispatch(dec, engine=_engine())
        params = dict(dispatched.params)
        
        # Assert slot_colors length 6
        self.assertIn("slot_colors", params)
        slot_colors = params["slot_colors"]
        self.assertEqual(len(slot_colors), 6)
        
        # Assert slot 5 is (255,255,255)
        self.assertEqual(tuple(slot_colors[5]), (255, 255, 255))
        
        # Assert slots 0-4 are not all default white/black and include palette-derived non-white values
        non_default = [c for c in slot_colors[:5] if tuple(c) not in ((0, 0, 0), (255, 255, 255))]
        self.assertTrue(len(non_default) > 0, "Slots 0-4 must contain palette-derived colors")
        
        # Call GoveeFrameRenderer.render(...)
        r = GoveeFrameRenderer()
        frame = r.render(
            "groove_center_chase",
            beat_pos=1.0, local_t=1.0, frame_index=0,
            params=params, segments=20, seed=1,
        )
        
        # Assert rendered frame contains non-black, non-default-white palette-colored pixels
        non_default_pixels = [px for px in frame if tuple(px) not in ((0, 0, 0), (255, 255, 255))]
        self.assertTrue(len(non_default_pixels) > 0, "Rendered frame must contain palette colors")

class ConfigLoadTests(unittest.TestCase):
    def test_config_load_success(self) -> None:
        cfg = _base_config()
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg=f"Valid config failed to load: {result.errors}")

    def test_bad_look_param_fails_config_load(self) -> None:
        cfg = _base_config()
        cfg["looks"]["rt_groove_center_chase"]["params"] = {"bad_param": 123}
        result = load_led_look_director_config_from_dict(cfg)
        self.assertFalse(result.available, msg="Bad param should fail the whole LED config")

    def test_malformed_color_engine_disables_only_engine(self) -> None:
        cfg = _base_config()
        cfg["color_engine"]["palettes"] = "not_a_dict"  # malformed
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available, msg="Malformed color_engine should keep director available")
        self.assertIsNone(result.config.color_engine, msg="Engine should be None due to parsing failure")

class BakedSandNegativeTests(unittest.TestCase):
    def test_sand_negative_assertions(self) -> None:
        cfg = _base_config()
        result = load_led_look_director_config_from_dict(cfg)
        self.assertTrue(result.available)

        # (a) its scene_ref is NOT in SLOT_EFFECTS
        self.assertNotIn("breakdown_star_twinkle_sand", SLOT_EFFECTS)

        look = result.config.looks["rt_breakdown_star_twinkle_sand"]
        # (b) the look's color_source == "baked"
        self.assertEqual(look.color_source, "baked")

        # (c) the look name is in color_engine.exempt_looks
        self.assertIn("rt_breakdown_star_twinkle_sand", result.config.color_engine.exempt_looks)

        # (d) there is NO diy_color_tags entry for it (not present in base_config looks definition anyway)
        self.assertIsNone(getattr(look, "diy_color_tags", None))

        # (e) the dispatch seam injects NO slot_colors (and no color) into its decision.params
        engine = _engine(exempt_looks=("rt_breakdown_star_twinkle_sand",))
        dec = _decision(
            "rt_breakdown_star_twinkle_sand",
            scene_ref="breakdown_star_twinkle_sand",
            color_source="baked",
            params={"sync_mode": "beat"},
        )
        director = _DispatchDirector(dec)
        adapter = _RecordingAdapter()
        sm = _make_sm(director=director, adapter=adapter, engine=engine)
        _arm_automation(sm)
        sm._dispatch_led_automation(active=1, d=_playing_deck(sm), sp_state=SmartPhrasingState())
        
        dispatched = adapter.trigger_calls[0]
        params = dict(dispatched.params)
        self.assertNotIn("slot_colors", params)
        self.assertNotIn("color", params)

        # (f) it renders through the normal Frame path (_EFFECTS), not the slot colorizer path
        self.assertIn("breakdown_star_twinkle_sand", _EFFECTS)
        r = GoveeFrameRenderer()
        frame = r.render(
            "breakdown_star_twinkle_sand",
            beat_pos=1.0, local_t=1.0, frame_index=0,
            params={}, segments=20, seed=1,
        )
        # Should return a frame (list of tuples) and not raise exception
        self.assertEqual(len(frame), 20)
        self.assertIsInstance(frame[0], tuple)

if __name__ == "__main__":
    unittest.main()
