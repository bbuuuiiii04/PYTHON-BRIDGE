import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import resolve_fade, GoveeFrameRenderer
from rb_ss_bridge_v2.govee_realtime_runner import GoveeRealtimeRunner, EffectSpec, _COLOR_SIG_KEYS
from rb_ss_bridge_v2.led_color_engine import LedColorEngine
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette
from unittest.mock import Mock

def _make_runner():
    engine_mock = Mock()
    transport_mock = Mock()
    runner = GoveeRealtimeRunner(transport_mock, Mock())
    runner._engine = engine_mock
    return runner, engine_mock

def test_runner_motion_reset():
    runner, engine_mock = _make_runner()
    spec1 = EffectSpec("eff", {"speed": 1.0, "color": (255, 0, 0)}, 1, 0.0)
    spec2 = EffectSpec("eff", {"speed": 2.0, "color": (255, 0, 0)}, 1, 0.0)
    runner._active = True
    runner._active_signature, _ = runner._signature(spec1)
    
    runner.set_desired(spec2)
    anchor = Mock(permitted=True, playing=True, bpm=120.0, abs_beat_pos=10.0, captured_monotonic=0.0)
    ir_mock = Mock(local_beat=0, local_t=0, bucket=0)
    engine_mock.on_tick.return_value = [ir_mock]
    runner._renderer = Mock()
    runner._renderer.render.return_value = []
    
    runner._tick_once(anchor, 0.0)
    engine_mock.configure.assert_called()

def test_runner_stop_clears_state():
    runner, _ = _make_runner()
    runner._active = True
    runner._active_signature = ("a", "b")
    runner._color_signature = ("c",)
    runner._color_applied_abs_beat = 10.0
    runner._idle_since = 5.0
    
    runner.stop(timeout_s=0.0)
    assert not runner._active
    assert runner._active_signature is None
    assert runner._color_signature is None
    assert runner._color_applied_abs_beat is None
    assert runner._idle_since is None

def test_runner_emergency_and_idle_reset():
    runner, engine_mock = _make_runner()
    
    # Emergency
    runner._active = True
    runner._active_signature = ("a", "b")
    runner._color_signature = ("c",)
    runner._color_applied_abs_beat = 10.0
    runner._idle_since = 5.0
    runner._emergency_teardown()
    assert runner._color_signature is None
    assert runner._color_applied_abs_beat is None
    engine_mock.reset.assert_called()
    
    # Idle
    runner._active = True
    runner._active_signature = ("a", "b")
    runner._color_signature = ("c",)
    runner._color_applied_abs_beat = 10.0
    runner._idle_since = 0.0
    engine_mock.reset.reset_mock()
    runner._idle_tick(10.0)  # past grace period
    assert runner._color_signature is None
    assert runner._color_applied_abs_beat is None
    engine_mock.reset.assert_called()

def test_fade_beats_zero_is_byte_identical():
    r = GoveeFrameRenderer()
    params_no_fade = {"color": (255, 0, 0)}
    params_fade_zero = {"color_from": (0, 0, 255), "color_to": (255, 0, 0), "fade_beats": 0.0}
    
    out1 = r.render("groove_center_chase", beat_pos=0.5, local_t=0.5, frame_index=0, params=params_no_fade, segments=20, seed=123)
    
    params_fade_zero["color"] = (255, 0, 0)
    out2 = r.render("groove_center_chase", beat_pos=0.5, local_t=0.5, frame_index=0, params=resolve_fade(params_fade_zero, 10.5, 10.0), segments=20, seed=123)
    
    assert [list(x) for x in out1] == [list(x) for x in out2]

def test_engine_disabled_no_fade_params():
    config = ColorEngineConfig(
        enabled=False,
        palettes={"test_pal": Palette(weight=1.0, range=("a", "b"), spread=0.5)},
        scale_stops={"a": (255, 0, 0), "b": (0, 0, 255)}
    )
    engine = LedColorEngine(config, set_seed=42)
    res = engine.resolve_color(role="drop", section_id="s1", cycle=0, look_name="look", color_source="engine")
    assert res == {}

def test_step_within_section_false_cycle_independent():
    config = ColorEngineConfig(
        palettes={"test_pal": Palette(weight=1.0, range=("a", "b"), spread=0.5)},
        scale_stops={"a": (255, 0, 0), "b": (0, 0, 255)},
        enabled=True,
        step_within_section={"drop": False}
    )
    engine = LedColorEngine(config, set_seed=42)
    engine._current_track_key = (1, 123)
    
    res_c0 = engine.resolve_color(role="drop", section_id="s1", cycle=0, look_name="look", color_source="engine")
    engine._prev_color.clear() # clear memory so it computes fresh
    res_c1 = engine.resolve_color(role="drop", section_id="s1", cycle=1, look_name="look", color_source="engine")
    
    assert res_c0["color"] == res_c1["color"]
