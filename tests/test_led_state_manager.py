import queue
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_models import LEDContext, LEDLookDecision  # noqa: E402
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


class _StubLEDLookDirector:
    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._manual_override = ""
        self._emergency_blackout = False
        self.tick_calls: list[LEDContext] = []
        self._config = Mock()
        self._config.targets = {
            "room_perimeter": Mock(),
            "strip_light_mirror": Mock(),
        }

    def status(self) -> dict:
        return {
            "available": True,
            "enabled": self._enabled,
            "dry_run": True,
            "automation_enabled": False,
            "scripted_mode_automation": False,
            "current_look": "",
            "last_reason": "",
            "last_source": "",
            "manual_override": self._manual_override,
            "emergency_blackout": self._emergency_blackout,
        }

    def set_manual_override(self, look_name: str | None) -> bool:
        if look_name and look_name.startswith("bad_"):
            return False
        self._manual_override = look_name or ""
        return True

    def set_emergency_blackout(self, enabled: bool) -> None:
        self._emergency_blackout = bool(enabled)

    def tick(self, context: LEDContext | None = None) -> LEDLookDecision | None:
        if context is not None:
            self.tick_calls.append(context)
        if not self._enabled:
            return None
        if context is not None and context.emergency_blackout:
            target = "room_perimeter"
            if context.target_override:
                target = context.target_override
            return LEDLookDecision(
                look="room_blackout",
                target=target,
                action="diy_scene",
                scene_ref="23259999",
                reason="emergency_blackout",
                source="emergency",
                priority=0,
                role="emergency",
            )
        look = context.manual_look if context is not None else None
        if look:
            target = "room_perimeter"
            if context is not None and context.target_override:
                target = context.target_override
            return LEDLookDecision(
                look=look,
                target=target,
                action="scene",
                scene_ref=look,
                reason="manual_override",
                source="manual",
                priority=1,
                role="manual",
            )
        return LEDLookDecision(
            look="room_safe_default",
            target="room_perimeter",
            action="scene",
            scene_ref="room_safe_default",
            reason="safe_default",
            source="policy",
            priority=2,
            role="utility",
        )


class _StubLEDAdapter:
    def __init__(self, *, accept: bool = True, last_error: str = "") -> None:
        self.accept = accept
        self.last_error = last_error
        self.trigger_calls: list[LEDLookDecision] = []
        self.status_calls = 0

    def trigger(self, decision: LEDLookDecision) -> bool:
        self.trigger_calls.append(decision)
        return self.accept

    def status(self) -> dict:
        self.status_calls += 1
        return {
            "available": True,
            "running": False,
            "dry_run": True,
            "degraded": not self.accept,
            "degraded_reason": self.last_error if not self.accept else "",
            "queue_depth": 0,
            "queue_max": 8,
            "accepted_count": len(self.trigger_calls) if self.accept else 0,
            "rejected_count": 0 if self.accept else len(self.trigger_calls),
            "dropped_count": 0 if self.accept else len(self.trigger_calls),
            "last_error": self.last_error if not self.accept else "",
            "provider": {"device_ref": "hidden-raw-id"},
        }


class _TacticalLEDAdapter(_StubLEDAdapter):
    def __init__(self) -> None:
        super().__init__(accept=True)
        self.tactical_calls: list[LEDLookDecision] = []

    def tactical_blackout(self, decision: LEDLookDecision) -> bool:
        self.tactical_calls.append(decision)
        return True

    def status(self) -> dict:
        payload = super().status()
        payload["realtime"] = {
            "owner": "realtime_razer",
            "active": bool(self.tactical_calls),
            "provider_bound": True,
            "desired_effect": "blackout" if self.tactical_calls else "",
            "active_effect": "blackout" if self.tactical_calls else "",
            "transport": {
                "ip": "192.168.0.219",
                "frames_sent": len(self.tactical_calls),
                "send_error_count": 0,
            },
        }
        return payload


class _ExplodingAdapter:
    def __init__(self) -> None:
        self.trigger_called = 0
        self.status_called = 0

    def trigger(self, _decision) -> bool:  # type: ignore[no-untyped-def]
        self.trigger_called += 1
        raise AssertionError("trigger should not be called in _push_tick")

    def status(self) -> dict:
        self.status_called += 1
        raise AssertionError("status should not be called in _push_tick")


class _AutomationLEDLookDirector:
    def __init__(
        self,
        *,
        enabled: bool = True,
        dry_run: bool = True,
        automation_enabled: bool = True,
        scripted_mode_automation: bool = False,
    ) -> None:
        self._enabled = enabled
        self._dry_run = dry_run
        self._automation_enabled = automation_enabled
        self._scripted_mode_automation = scripted_mode_automation
        self.preview_decision: LEDLookDecision | None = None
        self.preview_decisions: dict[str, LEDLookDecision] = {}
        self._manual_override = ""
        self._emergency_blackout = False
        self.status_calls = 0
        self.tick_calls: list[LEDContext] = []

    def status(self) -> dict:
        self.status_calls += 1
        return {
            "available": True,
            "enabled": self._enabled,
            "dry_run": self._dry_run,
            "automation_enabled": self._automation_enabled,
            "scripted_mode_automation": self._scripted_mode_automation,
            "current_look": "",
            "last_reason": "",
            "last_source": "",
            "manual_override": self._manual_override,
            "emergency_blackout": self._emergency_blackout,
        }

    def set_manual_override(self, look_name: str | None) -> bool:
        self._manual_override = look_name or ""
        return True

    def set_emergency_blackout(self, enabled: bool) -> None:
        self._emergency_blackout = bool(enabled)

    def tick(self, context: LEDContext | None = None) -> LEDLookDecision | None:
        if context is not None:
            self.tick_calls.append(context)
        if not self._enabled:
            return None
        if context is not None and context.emergency_blackout:
            return LEDLookDecision(
                look="room_blackout",
                target="room_perimeter",
                action="diy_scene",
                scene_ref="23259999",
                reason="emergency_blackout",
                source="emergency",
                priority=0,
                role="emergency",
            )
        manual = context.manual_look if context is not None else None
        if manual:
            return LEDLookDecision(
                look=manual,
                target="room_perimeter",
                action="scene",
                scene_ref=manual,
                reason="manual_override",
                source="manual",
                priority=1,
                role="manual",
            )
        if not self._automation_enabled or context is None:
            return None
        role = context.role
        return LEDLookDecision(
            look=f"room_{role}",
            target="room_perimeter",
            action="scene",
            scene_ref=f"Scene-{role}",
            reason=f"role_entry:{role}",
            source="automation",
            priority=2,
            role=role,
        )

    def preview_role(self, role: str) -> LEDLookDecision | None:
        if role in self.preview_decisions:
            return self.preview_decisions[role]
        if role == "drop" and self.preview_decision is not None:
            return self.preview_decision
        return None


def _make_sm(*, director=None, adapter=None) -> StateManager:
    return StateManager(
        queue.Queue(maxsize=64),
        PositionCache(),
        Mock(),
        led_look_director=director,
        led_scene_adapter=adapter,
    )


def _prepare_playing_push_tick(
    sm: StateManager,
    sp_state: SmartPhrasingState,
    *,
    scripted: bool = False,
) -> None:
    snap = PositionSnapshot(
        deck=1,
        elapsed_ms=1000,
        playing=True,
        updated_at=time.monotonic(),
    )
    sm._check_pending_arm = lambda: None
    sm._update_lighting = lambda *_args, **_kwargs: None
    sm._update_smart_phrasing_state = lambda *_args, **_kwargs: sp_state
    sm._cache.get = lambda deck: snap if deck == 1 else None
    sm._laser_director = None
    sm._deck[1].playing = True
    sm._deck[1].scripted_id = 7 if scripted else 0
    sm._deck[1].load_gen = 11
    sm._deck[1].meta.filepath = "/tracks/current.wav"
    sm._deck[1].meta.bpm = 0.0
    sm._deck[2].playing = False
    sm._os.active_deck = 1
    sm._os.was_playing = True
    sm._os.lighting_mode = "scripted" if scripted else "autoloop"
    sm._os.last_armed_filepath = "/tracks/current.wav"
    sm._os.last_beat_elapsed_ms = 1000


def _prepare_paused_push_tick(sm: StateManager) -> None:
    snap = PositionSnapshot(
        deck=1,
        elapsed_ms=1000,
        playing=False,
        updated_at=time.monotonic(),
    )
    sm._check_pending_arm = lambda: None
    sm._update_lighting = lambda *_args, **_kwargs: None
    sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState()
    sm._cache.get = lambda deck: snap if deck == 1 else None
    sm._laser_director = None
    sm._deck[1].playing = False
    sm._deck[1].scripted_id = 0
    sm._deck[1].load_gen = 11
    sm._deck[1].meta.filepath = "/tracks/current.wav"
    sm._deck[1].meta.bpm = 0.0
    sm._deck[2].playing = False
    sm._os.active_deck = 1
    sm._os.was_playing = True
    sm._os.lighting_mode = "autoloop"
    sm._os.last_armed_filepath = "/tracks/current.wav"
    sm._os.last_beat_elapsed_ms = 1000


class LEDStateManagerTests(unittest.TestCase):
    def test_manual_scene_sets_override_and_triggers_adapter_once(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_SCENE,
                deck=0,
                payload={"look": "room_drop_white_burst", "ttl_s": 5.0},
                source="test",
            )
        )
        status = sm.led_status_provider()
        self.assertEqual(status["manual_override"], "room_drop_white_burst")
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].look, "room_drop_white_burst")
        self.assertEqual(status["trigger_count"], 1)

    def test_manual_scene_can_target_original_strip_only(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_SCENE,
                deck=0,
                payload={"look": "room_drop_a", "target": "strip_light_mirror"},
                source="test",
            )
        )
        status = sm.led_status_provider()
        self.assertEqual(status["manual_target_override"], "strip_light_mirror")
        self.assertEqual(adapter.trigger_calls[0].target, "strip_light_mirror")
        self.assertEqual(director.tick_calls[0].target_override, "strip_light_mirror")

    def test_manual_scene_rejects_unknown_target(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_SCENE,
                deck=0,
                payload={"look": "room_drop_a", "target": "missing_strip"},
                source="test",
            )
        )
        status = sm.led_status_provider()
        self.assertIn("unknown_target", status["last_error"])
        self.assertEqual(len(adapter.trigger_calls), 0)

    def test_blackout_beats_manual_scene(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        status = sm.led_status_provider()
        self.assertTrue(status["emergency_blackout"])
        self.assertEqual(len(adapter.trigger_calls), 2)
        self.assertEqual(adapter.trigger_calls[-1].look, "room_blackout")
        self.assertEqual(adapter.trigger_calls[-1].action, "diy_scene")

    def test_clear_scene_override_does_not_clear_blackout(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_CLEAR_SCENE_OVERRIDE, deck=0, payload={}, source="test"))
        status = sm.led_status_provider()
        self.assertEqual(status["manual_override"], "")
        self.assertTrue(status["emergency_blackout"])
        self.assertEqual(adapter.trigger_calls[-1].look, "room_blackout")

    def test_clear_blackout_reemits_manual_when_present(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_CLEAR_BLACKOUT, deck=0, payload={}, source="test"))
        status = sm.led_status_provider()
        self.assertFalse(status["emergency_blackout"])
        self.assertEqual(status["manual_override"], "room_drop_a")
        self.assertEqual(adapter.trigger_calls[-1].look, "room_drop_a")
        self.assertEqual(len(adapter.trigger_calls), 3)

    def test_disabled_led_layer_is_inert_and_status_visible(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SET_ENABLED, deck=0, payload={"enabled": False}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        status = sm.led_status_provider()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["reason"], "disabled")
        self.assertEqual(len(adapter.trigger_calls), 0)

    def test_not_configured_led_layer_is_inert_and_visible(self) -> None:
        sm = _make_sm(director=None, adapter=None)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        status = sm.led_status_provider()
        self.assertFalse(status["available"])
        self.assertEqual(status["reason"], "not_configured")
        self.assertEqual(status["last_error"], "not_configured")

    def test_adapter_rejection_is_non_fatal_and_visible(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter(accept=False, last_error="queue_full")
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        status = sm.led_status_provider()
        self.assertEqual(status["last_error"], "adapter_rejected")
        self.assertEqual(status["rejected_count"], 1)
        self.assertEqual(status["adapter"]["last_error"], "queue_full")

    def test_push_tick_does_not_call_led_adapter_methods(self) -> None:
        director = _StubLEDLookDirector(enabled=True)
        adapter = _ExplodingAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._check_pending_arm = lambda: None
        sm._update_lighting = lambda *_args, **_kwargs: None
        sm._cache.get = lambda _deck: None
        sm._laser_director = None
        sm._deck[1].playing = False
        sm._deck[2].playing = False
        sm._os.was_playing = False

        for _ in range(3):
            sm._push_tick()

        self.assertEqual(adapter.trigger_called, 0)
        self.assertEqual(adapter.status_called, 0)

    def test_smart_drop_crossing_triggers_drop_once_without_tick_spam(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
            ),
        )

        for _ in range(3):
            sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "drop")
        self.assertEqual(adapter.trigger_calls[0].look, "room_drop")
        self.assertEqual(director.tick_calls[0].role, "drop")
        self.assertFalse(director.tick_calls[0].emergency_blackout)
        self.assertFalse(sm.led_status_provider()["smart_drop_blackout_active"])

    def test_smart_drop_arm_blacks_out_leds_once_until_drop_crossing(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                transition_mask_arm_latched=True,
                transition_window_active=True,
                next_smart_drop_beat=64.0,
            ),
        )

        sm._push_tick()
        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].look, "room_blackout")
        self.assertEqual(adapter.trigger_calls[0].action, "diy_scene")
        self.assertTrue(sm.led_status_provider()["smart_drop_blackout_active"])

    def test_realtime_drop_uses_tactical_blackout_not_cloud_blackout(self) -> None:
        director = _AutomationLEDLookDirector()
        director.preview_decision = LEDLookDecision(
            look="rt_drop_blue",
            target="room_perimeter",
            action="realtime",
            scene_ref="drop_chase_blue",
            reason="role_preview:drop",
            source="automation",
            priority=2,
            role="drop",
            backend="realtime_razer",
            params={},
        )
        adapter = _TacticalLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                transition_mask_arm_latched=True,
                transition_window_active=True,
                next_smart_drop_beat=64.0,
            ),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(len(adapter.tactical_calls), 1)
        self.assertEqual(adapter.tactical_calls[0].look, "rt_drop_blue")
        status = sm.led_status_provider()
        self.assertTrue(status["smart_drop_blackout_active"])
        self.assertEqual(status["adapter"]["realtime"]["desired_effect"], "blackout")

    def test_beat_anchor_requires_realtime_permission(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        sm._led_rt_beat = (1, 64.5, 128.0, 1000.0, True)

        self.assertIsNone(sm.get_active_beat_anchor())

        sm._led_rt_permitted = True
        anchor = sm.get_active_beat_anchor()

        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.deck, 1)
        self.assertEqual(anchor.abs_beat_pos, 64.5)
        self.assertEqual(anchor.bpm, 128.0)

    def test_gate_clears_realtime_permission(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        sm._led_rt_permitted = True
        sm._led_rt_beat = (1, 64.5, 128.0, 1000.0, True)

        sm._gate_led_automation("manual_override", active_deck=1)

        self.assertIsNone(sm.get_active_beat_anchor())

    def test_smart_drop_blackout_arms_early_with_automation_offset(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_automation_offset_s = 1.0
        sm._os.lighting_mode = "autoloop"
        d = sm._deck[1]
        d.playing = True
        d.meta.filepath = "/tracks/current.wav"
        d.meta.smart_drops = [64]
        d.meta.beatgrid_times_ms = list(range(0, 200 * 500, 500))
        d.load_gen = 11

        sm._update_smart_phrasing_state(1, d, 57.0, 120.0)
        live_sp = sm._update_smart_phrasing_state(1, d, 58.0, 120.0)
        led_sp = sm._led_sp_state_with_offset(live_sp, 120.0)

        self.assertFalse(sm._led_should_smart_drop_blackout(live_sp))
        self.assertTrue(sm._led_should_smart_drop_blackout(led_sp))

        sm._dispatch_led_automation(active=1, d=d, sp_state=led_sp)
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].look, "room_blackout")
        self.assertTrue(director.tick_calls[0].emergency_blackout)

    def test_cloud_drop_uses_cloud_automation_offset(self) -> None:
        director = _AutomationLEDLookDirector()
        director.preview_decision = LEDLookDecision(
            look="cloud_drop",
            target="room_perimeter",
            action="diy_scene",
            scene_ref="23254201",
            reason="role_preview:drop",
            source="automation",
            priority=2,
            role="drop",
            backend="cloud_diy",
        )
        sm = _make_sm(director=director, adapter=_StubLEDAdapter())
        sm._led_automation_offset_s = 1.0
        sm._led_cloud_automation_offset_s = 1.0
        sm._led_realtime_automation_offset_s = 0.0
        d = sm._deck[1]
        d.playing = True
        d.meta.filepath = "/tracks/current.wav"
        d.meta.smart_drops = [64]
        d.meta.beatgrid_times_ms = list(range(0, 200 * 500, 500))

        sm._update_smart_phrasing_state(1, d, 57.0, 120.0)
        live_sp = sm._update_smart_phrasing_state(1, d, 58.0, 120.0)
        selected_sp = sm._led_sp_state_for_next_backend(live_sp, 120.0)

        self.assertFalse(sm._led_should_smart_drop_blackout(live_sp))
        self.assertTrue(sm._led_should_smart_drop_blackout(selected_sp))

    def test_realtime_drop_uses_realtime_automation_offset(self) -> None:
        director = _AutomationLEDLookDirector()
        director.preview_decision = LEDLookDecision(
            look="rt_drop",
            target="room_perimeter",
            action="realtime",
            scene_ref="drop_chase_blue",
            reason="role_preview:drop",
            source="automation",
            priority=2,
            role="drop",
            backend="realtime_razer",
        )
        sm = _make_sm(director=director, adapter=_StubLEDAdapter())
        sm._led_automation_offset_s = 1.0
        sm._led_cloud_automation_offset_s = 1.0
        sm._led_realtime_automation_offset_s = 0.0
        d = sm._deck[1]
        d.playing = True
        d.meta.filepath = "/tracks/current.wav"
        d.meta.smart_drops = [64]
        d.meta.beatgrid_times_ms = list(range(0, 200 * 500, 500))

        sm._update_smart_phrasing_state(1, d, 57.0, 120.0)
        live_sp = sm._update_smart_phrasing_state(1, d, 58.0, 120.0)
        selected_sp = sm._led_sp_state_for_next_backend(live_sp, 120.0)

        self.assertFalse(sm._led_should_smart_drop_blackout(live_sp))
        self.assertFalse(sm._led_should_smart_drop_blackout(selected_sp))

    def test_pause_dispatches_idle_ambient_once(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_paused_push_tick(sm)

        sm._push_tick()
        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "ambient")
        self.assertEqual(adapter.trigger_calls[0].look, "room_ambient")
        self.assertFalse(director.tick_calls[0].playing)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "")

    def test_resume_after_idle_ambient_waits_for_playing_tick(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_paused_push_tick(sm)
        sm._push_tick()
        self.assertEqual(adapter.trigger_calls[-1].role, "ambient")

        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(current_phrase_is_chorus=True),
        )
        sm._do_resume(1, 1000, 120.0)
        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 2)
        self.assertEqual(adapter.trigger_calls[-1].role, "groove")
        self.assertEqual(adapter.trigger_calls[-1].look, "room_groove")

    def test_manual_override_suppresses_idle_ambient(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_manual_override = "room_manual"
        _prepare_paused_push_tick(sm)

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "manual_override")

    def test_emergency_blackout_suppresses_idle_ambient(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_emergency_blackout = True
        _prepare_paused_push_tick(sm)

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "emergency_blackout")

    def test_playing_automation_requires_fresh_autoloop_ready_state(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.filepath = "/tracks/current.wav"
        sm._os.lighting_mode = "autoloop"

        sm._dispatch_led_automation(
            active=1,
            d=deck,
            sp_state=SmartPhrasingState(current_phrase_is_chorus=True),
            position_stale=True,
            autoloop_ready=True,
        )
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "position_stale")

        sm._dispatch_led_automation(
            active=1,
            d=deck,
            sp_state=SmartPhrasingState(current_phrase_is_chorus=True),
            position_stale=False,
            autoloop_ready=False,
        )
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "autoloop_not_ready")
        self.assertEqual(len(adapter.trigger_calls), 0)

    def test_smart_drop_crossing_reasserts_led_blackout(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                transition_mask_arm_latched=True,
                transition_window_active=True,
                next_smart_drop_beat=64.0,
            ),
        )
        sm._push_tick()
        self.assertEqual(adapter.trigger_calls[-1].look, "room_blackout")

        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
        )
        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 2)
        self.assertEqual(adapter.trigger_calls[-1].look, "room_drop")
        self.assertEqual(adapter.trigger_calls[-1].role, "drop")
        self.assertFalse(sm.led_status_provider()["smart_drop_blackout_active"])

        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            current_phrase_is_chorus=True,
        )
        sm._push_tick()

        self.assertEqual(adapter.trigger_calls[-1].look, "room_groove")
        self.assertFalse(sm.led_status_provider()["smart_drop_blackout_active"])

    def test_buildup_role_entry_triggers_one_look(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                smart_buildup_active=True,
                current_phrase_is_up=True,
                next_smart_drop_beat=96.0,
                beats_to_next_drop=16.0,
            ),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "buildup")
        self.assertEqual(adapter.trigger_calls[0].look, "room_buildup")

    def test_buildup_outside_32_beat_window_does_not_trigger(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                current_phrase_is_up=True,
                next_smart_drop_beat=96.0,
                beats_to_next_drop=40.0,
            ),
        )

        sm._push_tick()

        buildup_calls = [c for c in adapter.trigger_calls if c.role == "buildup"]
        self.assertEqual(len(buildup_calls), 0)

    def test_buildup_in_chorus_phrase_inside_window_does_not_trigger(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                current_phrase_is_chorus=True,
                next_smart_drop_beat=96.0,
                beats_to_next_drop=16.0,
            ),
        )

        sm._push_tick()

        buildup_calls = [c for c in adapter.trigger_calls if c.role == "buildup"]
        self.assertEqual(len(buildup_calls), 0)
        self.assertEqual(adapter.trigger_calls[0].role, "groove")

    def test_breakdown_role_entry_triggers_one_look(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                smart_breakdown_active=True,
                breakdown_restore_beat=128.0,
            ),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "breakdown")
        self.assertEqual(adapter.trigger_calls[0].look, "room_breakdown")

    def test_manual_override_suppresses_automatic_role_entry(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_manual_override = "room_manual"
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(smart_drop_crossing=True, active_drop_beat=64.0),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "manual_override")

    def test_blackout_suppresses_automatic_role_entry(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_emergency_blackout = True
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(smart_drop_crossing=True, active_drop_beat=64.0),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "emergency_blackout")

    def test_scripted_mode_is_conservative_by_default(self) -> None:
        director = _AutomationLEDLookDirector(scripted_mode_automation=False)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(smart_buildup_active=True, next_smart_drop_beat=96.0),
            scripted=True,
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "scripted_mode")

    def test_automation_disabled_is_inert_in_push_tick(self) -> None:
        director = _AutomationLEDLookDirector(automation_enabled=False)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(smart_drop_crossing=True, active_drop_beat=64.0),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertEqual(len(director.tick_calls), 0)
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "automation_disabled")

    def test_dry_run_false_automation_triggers_in_push_tick(self) -> None:
        director = _AutomationLEDLookDirector(dry_run=False, automation_enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(smart_drop_crossing=True, active_drop_beat=64.0),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(len(director.tick_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "drop")
        self.assertEqual(adapter.trigger_calls[0].look, "room_drop")
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "")

    def test_automation_gate_reason_logs_only_on_change(self) -> None:
        director = _AutomationLEDLookDirector(automation_enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        deck = sm._deck[1]
        deck.playing = False
        deck.meta.filepath = ""
        with self.assertLogs("state_manager", level="INFO") as captured:
            sm._dispatch_led_automation(
                active=1,
                d=deck,
                sp_state=SmartPhrasingState(),
            )
            sm._dispatch_led_automation(
                active=1,
                d=deck,
                sp_state=SmartPhrasingState(),
            )
            deck.playing = True
            deck.meta.filepath = "/tracks/current.wav"
            sm._os.lighting_mode = "autoloop"
            sm._os.last_armed_filepath = "/tracks/current.wav"
            sm._dispatch_led_automation(
                active=1,
                d=deck,
                sp_state=SmartPhrasingState(),
            )

        gate_logs = [
            line
            for line in captured.output
            if "[RGB] gate-reason-change" in line
        ]
        self.assertEqual(len(gate_logs), 2)

    def test_led_scene_ref_log_sanitizer_redacts_device_like_values(self) -> None:
        sm = _make_sm(director=None, adapter=None)

        self.assertEqual(sm._sanitize_led_scene_ref("Meteor"), "Meteor")
        self.assertEqual(
            sm._sanitize_led_scene_ref("54:2C:DA:B9:81:C6:3C:38"),
            "<redacted>",
        )

    def test_push_tick_does_not_call_led_status_providers_for_automation(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        self.assertEqual(director.status_calls, 1)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(current_phrase_is_chorus=True),
        )

        sm._push_tick()

        self.assertEqual(director.status_calls, 1)
        self.assertEqual(adapter.status_calls, 0)
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "groove")


if __name__ == "__main__":
    unittest.main()
