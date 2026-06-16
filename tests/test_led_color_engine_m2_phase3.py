"""Tests for M2 Phase 3: Deterministic color fades and step_within_section."""
import pytest
from unittest.mock import Mock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import resolve_fade
from rb_ss_bridge_v2.govee_realtime_runner import GoveeRealtimeRunner, EffectSpec, _COLOR_SIG_KEYS
from rb_ss_bridge_v2.led_color_engine import LedColorEngine
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette


def test_resolve_fade_pure_helper():
    # 1. No abs_pos -> unchanged
    params = {"color_from": (255, 0, 0), "color_to": (0, 0, 255), "fade_beats": 2.0}
    assert resolve_fade(params, None, 10.0) == params
    
    # 2. No fade_beats -> unchanged
    params2 = {"color_from": (255, 0, 0), "color_to": (0, 0, 255)}
    assert resolve_fade(params2, 11.0, 10.0) == params2
    
    # 3. Lerp halfway
    out = resolve_fade(params, 11.0, 10.0)
    assert out["color"] == (128, 0, 128)  # Halfway between red and blue
    
    # 4. Clamping
    out_under = resolve_fade(params, 9.0, 10.0)
    assert out_under["color"] == (255, 0, 0)
    
    out_over = resolve_fade(params, 15.0, 10.0)
    assert out_over["color"] == (0, 0, 255)
    
    # 5. Slots
    dual_params = {
        "slot_colors_from": [(10, 10, 10), (255, 255, 255)],
        "slot_colors_to": [(20, 20, 20), (255, 255, 255)],
        "fade_beats": 1.0,
    }
    out_dual = resolve_fade(dual_params, 10.5, 10.0)
    assert out_dual["slot_colors"] == [(15, 15, 15), (255, 255, 255)]


def test_runner_signature_split():
    runner = GoveeRealtimeRunner(Mock(), Mock())
    spec = EffectSpec(
        effect_name="test",
        params={"speed": 2.0, "color": (255, 0, 0), "fade_beats": 4.0},
        seed=123,
        applied_monotonic=0.0
    )
    motion_sig, color_sig = runner._signature(spec)
    
    # Motion sig should have "speed" but NOT "color" or "fade_beats"
    motion_params = motion_sig[1]
    assert any(k == "speed" for k, v in motion_params)
    assert not any(k == "color" for k, v in motion_params)
    
    # Color sig should have "color" and "fade_beats"
    assert any(k == "color" for k, v in color_sig)
    assert any(k == "fade_beats" for k, v in color_sig)


def test_runner_no_motion_reset():
    engine_mock = Mock()
    transport_mock = Mock()
    runner = GoveeRealtimeRunner(transport_mock, Mock())
    runner._engine = engine_mock
    
    spec1 = EffectSpec("eff", {"speed": 1.0, "color": (255, 0, 0)}, 1, 0.0)
    spec2 = EffectSpec("eff", {"speed": 1.0, "color": (0, 255, 0), "fade_beats": 2.0}, 1, 0.0)
    
    # Setup state
    runner._active = True
    runner._active_signature, runner._color_signature = runner._signature(spec1)
    
    # Re-stamp with only color changes
    runner.set_desired(spec2)
    anchor = Mock(permitted=True, playing=True, bpm=120.0, abs_beat_pos=10.0, captured_monotonic=0.0)
    ir_mock = Mock(local_beat=0, local_t=0, bucket=0)
    engine_mock.on_tick.return_value = [ir_mock]
    runner._renderer = Mock()
    runner._renderer.render.return_value = []
    
    # Should NOT call configure!
    runner._tick_once(anchor, 0.0)
    engine_mock.configure.assert_not_called()
    
    # But color signature SHOULD update
    _, new_color_sig = runner._signature(spec2)
    assert runner._color_signature == new_color_sig
    assert runner._color_applied_abs_beat == 10.0


def test_engine_previous_color_memory():
    config = ColorEngineConfig(
        palettes={"test_pal": Palette(weight=1.0, range=("a", "b"))},
        scale_stops={"a": (255, 0, 0), "b": (0, 0, 255)},
        enabled=True,
        fade_beats_by_role={"drop": 4.0}
    )
    engine = LedColorEngine(config, set_seed=42)
    
    # 1. First call -> no prev
    engine._current_track_key = (1, 123)
    res1 = engine.resolve_color(role="drop", section_id="s1", cycle=0, look_name="look", color_source="engine")
    assert "color_from" not in res1
    assert "color" in res1
    
    # 2. Second call -> prev is injected
    res2 = engine.resolve_color(role="drop", section_id="s1", cycle=0, look_name="look", color_source="engine")
    assert "color_from" in res2
    assert "color_to" in res2
    assert res2["fade_beats"] == 4.0
    assert res2["color_from"] == res1["color"]
    
    # 3. Track change -> prev is cleared
    engine.begin_dispatch(active_deck=1, load_gen=124, content_id="new", filepath="", role="drop", section_id="s1", cycle=0)
    res3 = engine.resolve_color(role="drop", section_id="s1", cycle=0, look_name="look", color_source="engine")
    assert "color_from" not in res3


def test_step_within_section_deterministic():
    config = ColorEngineConfig(
        palettes={"test_pal": Palette(weight=1.0, range=("a", "b"), spread=0.5)},
        scale_stops={"a": (255, 0, 0), "b": (0, 0, 255)},
        enabled=True,
        step_within_section={"drop": True}
    )
    engine = LedColorEngine(config, set_seed=42)
    engine._current_track_key = (1, 123)
    
    # Cycle 0
    res_c0 = engine.resolve_color(role="drop", section_id="s1", cycle=0, look_name="look", color_source="engine")
    # Cycle 1 -> different seed
    res_c1 = engine.resolve_color(role="drop", section_id="s1", cycle=1, look_name="look", color_source="engine")
    
    # Because step_within_section is True for drop, cycle matters, color should be different
    # (assuming rng produces different values and spread is > 0)
    assert res_c0["color"] != res_c1["color"]

def test_resolve_fade_dual_color():
    params = {
        "color_a_from": (255, 0, 0), "color_a_to": (0, 0, 255),
        "color_b_from": (0, 255, 0), "color_b_to": (255, 0, 255),
        "fade_beats": 2.0
    }
    out = resolve_fade(params, 11.0, 10.0) # halfway
    assert out["color_a"] == (128, 0, 128)
    assert out["color_b"] == (128, 128, 128)

def test_runner_all_color_keys_no_motion_reset():
    engine_mock = Mock()
    transport_mock = Mock()
    runner = GoveeRealtimeRunner(transport_mock, Mock())
    runner._engine = engine_mock
    
    spec1 = EffectSpec("eff", {"speed": 1.0, "color": (255, 0, 0)}, 1, 0.0)
    
    # 15 keys
    all_color_keys = {k: (0, 0, 0) if "color" in k else 1.0 for k in _COLOR_SIG_KEYS}
    all_color_keys["speed"] = 1.0 # keep motion same
    
    spec2 = EffectSpec("eff", all_color_keys, 1, 0.0)
    
    runner._active = True
    runner._active_signature, runner._color_signature = runner._signature(spec1)
    
    runner.set_desired(spec2)
    anchor = Mock(permitted=True, playing=True, bpm=120.0, abs_beat_pos=10.0, captured_monotonic=0.0)
    ir_mock = Mock(local_beat=0, local_t=0, bucket=0)
    engine_mock.on_tick.return_value = [ir_mock]
    runner._renderer = Mock()
    runner._renderer.render.return_value = []
    
    runner._tick_once(anchor, 0.0)
    engine_mock.configure.assert_not_called()

def test_state_manager_fade_memory_reset():
    from rb_ss_bridge_v2.state_manager import StateManager
    
    sm = StateManager(Mock(), Mock(), Mock())
    color_engine_mock = Mock()
    sm._led_color_engine = color_engine_mock
    sm._led_rt_permitted = True
    
    # 1. Manual blackout command DOES call reset
    sm._dispatch_led_manual_command(reason="blackout")
    assert color_engine_mock.reset_fade_memory.call_count == 1
    color_engine_mock.reset_fade_memory.reset_mock()
    
    # 2. Gate with ordinary transient reason does NOT call reset
    sm._gate_led_automation(reason="position_stale", active_deck=1)
    sm._gate_led_automation(reason="not_autoloop", active_deck=1)
    assert color_engine_mock.reset_fade_memory.call_count == 0
    
    # 3. Gate with emergency_blackout DOES call reset (on edge transition)
    sm._gate_led_automation(reason="emergency_blackout", active_deck=1)
    assert color_engine_mock.reset_fade_memory.call_count == 1
    color_engine_mock.reset_fade_memory.reset_mock()
    
    # It does NOT call it on duplicate tick
    sm._gate_led_automation(reason="emergency_blackout", active_deck=1)
    assert color_engine_mock.reset_fade_memory.call_count == 0
    
    # 4. Idle transition DOES call reset, but not on duplicate tick
    # Need to give it a mock look director to avoid it gate-short-circuiting
    sm._led_look_director = Mock()
    sm._led_scene_adapter = Mock()
    sm._led_enabled_latch = True
    sm._led_automation_enabled_latch = True
    sm._led_emergency_blackout = False
    
    d = Mock(load_gen=1, meta=Mock(filepath="path"), scripted_id="")
    sm._dispatch_led_idle_ambient(active=1, d=d, reason="test")
    assert color_engine_mock.reset_fade_memory.call_count == 1
    color_engine_mock.reset_fade_memory.reset_mock()
    
    sm._dispatch_led_idle_ambient(active=1, d=d, reason="test")
    assert color_engine_mock.reset_fade_memory.call_count == 0
