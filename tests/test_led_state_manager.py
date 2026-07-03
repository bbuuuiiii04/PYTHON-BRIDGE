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
        scripted_default_role: str = "breakdown",
        scripted_role_map: dict[str, str] | None = None,
        mapped_roles: set[str] | None = None,
    ) -> None:
        self._enabled = enabled
        self._dry_run = dry_run
        self._automation_enabled = automation_enabled
        self._scripted_mode_automation = scripted_mode_automation
        self._scripted_default_role = scripted_default_role
        if scripted_role_map is None:
            scripted_role_map = {
                "ambient": "breakdown",
                "groove": "utility",
                "buildup": "buildup",
                "pre_drop": "buildup",
                "drop": "utility",
                "post_drop": "utility",
                "breakdown": "breakdown",
            }
        self._scripted_role_map = dict(scripted_role_map)
        self.preview_decision: LEDLookDecision | None = None
        self.preview_decisions: dict[str, LEDLookDecision] = {}
        self.role_decisions: dict[str, LEDLookDecision] = {}
        self.commit_calls: list[str] = []
        self._manual_override = ""
        self._emergency_blackout = False
        self.status_calls = 0
        self.tick_calls: list[LEDContext] = []
        self.mapped_roles = mapped_roles or {"ambient", "groove", "buildup", "drop", "breakdown", "utility"}

    def status(self) -> dict:
        self.status_calls += 1
        return {
            "available": True,
            "enabled": self._enabled,
            "dry_run": self._dry_run,
            "automation_enabled": self._automation_enabled,
            "scripted_mode_automation": self._scripted_mode_automation,
            "scripted_mode": {
                "default_role": self._scripted_default_role,
                "role_map": dict(self._scripted_role_map),
            },
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
        if role not in self.mapped_roles:
            return None
        if role in self.role_decisions:
            return self.role_decisions[role]
        return self._default_automation_decision(role)

    def _default_automation_decision(self, role: str) -> LEDLookDecision:
        if role == "utility":
            return LEDLookDecision(
                look="room_blackout",
                target="room_perimeter",
                action="off",
                scene_ref="",
                reason="role_entry:utility",
                source="automation",
                priority=2,
                role=role,
            )
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

    def commit_role(self, role: str) -> LEDLookDecision | None:
        self.commit_calls.append(role)
        if role == "drop" and self.preview_decision is not None:
            return self.preview_decision
        if role in self.preview_decisions:
            return self.preview_decisions[role]
        if role in self.role_decisions:
            return self.role_decisions[role]
        if role in self.mapped_roles:
            return self._default_automation_decision(role)
        return None

    def has_role_look(self, role: str) -> bool:
        return role in self.mapped_roles

    def drop_duration_beats(self, _look: str) -> float:
        return 8.0

    def post_drop_cycle_beats(self) -> float:
        return 32.0

    def reset_for_track(self) -> None:
        pass


def _make_sm(*, director=None, adapter=None) -> StateManager:
    return StateManager(
        queue.Queue(maxsize=64),
        PositionCache(),
        Mock(),
        led_look_director=director,
        led_scene_adapter=adapter,
    )


def _drop_decision(
    look: str,
    *,
    backend: str = "cloud_diy",
    action: str = "diy_scene",
    scene_ref: str = "23254201",
) -> LEDLookDecision:
    return LEDLookDecision(
        look=look,
        target="room_perimeter",
        action=action,
        scene_ref=scene_ref,
        reason="role_preview:drop",
        source="automation",
        priority=2,
        role="drop",
        backend=backend,
        params={},
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


def _ready_led_active_deck(sm: StateManager, deck: int, *, filepath: str = "/tracks/current.wav") -> None:
    d = sm._deck[deck]
    d.playing = True
    d.meta.filepath = filepath
    d.scripted_id = 0
    sm._os.active_deck = deck
    sm._os.lighting_mode = "autoloop"
    sm._led_manual_override = False
    sm._led_emergency_blackout = False


def _groove_sp(beats_into_phrase: float) -> SmartPhrasingState:
    return SmartPhrasingState(
        abs_beat=64.0 + beats_into_phrase,
        current_phrase_label="other",
        current_phrase_start_beat=64.0,
        beats_into_phrase=beats_into_phrase,
    )


def _groove_cross_sp() -> SmartPhrasingState:
    return SmartPhrasingState(
        abs_beat=96.0,
        current_phrase_label="other",
        current_phrase_start_beat=96.0,
        phrase_start_crossing=True,
        beats_into_phrase=0.0,
    )


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

    def test_deck_switch_at_marker_plus_half_beat_changes_immediately(self) -> None:
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=adapter)
        _ready_led_active_deck(sm, 1)

        sm._apply_nonzero_active_deck_switch(1, 2, "test")
        _ready_led_active_deck(sm, 2, filepath="/tracks/next.wav")
        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=_groove_sp(0.5))

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertFalse(sm._led_hold_active)

    def test_deck_switch_at_marker_plus_one_beat_changes_immediately(self) -> None:
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=adapter)
        _ready_led_active_deck(sm, 1)

        sm._apply_nonzero_active_deck_switch(1, 2, "test")
        _ready_led_active_deck(sm, 2, filepath="/tracks/next.wav")
        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=_groove_sp(1.0))

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertFalse(sm._led_hold_active)

    def test_deck_switch_at_marker_plus_1_1_beats_holds_until_next_marker(self) -> None:
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=adapter)
        _ready_led_active_deck(sm, 1)

        sm._apply_nonzero_active_deck_switch(1, 2, "test")
        _ready_led_active_deck(sm, 2, filepath="/tracks/next.wav")
        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=_groove_sp(1.1))

        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertTrue(sm._led_hold_active)

        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=_groove_cross_sp())

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertFalse(sm._led_hold_active)

    def test_same_deck_track_load_at_marker_plus_1_1_beats_holds_until_next_marker(self) -> None:
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=adapter)
        _ready_led_active_deck(sm, 1)
        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_sp(0.5))

        sm._on_track_loaded(
            1,
            "next",
            BridgeEvent(kind=Ev.TRACK_LOADED, deck=1, payload={"title": "next"}, source="test"),
        )
        _ready_led_active_deck(sm, 1, filepath="/tracks/next.wav")
        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_sp(1.1))

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertTrue(sm._led_hold_active)

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_cross_sp())

        self.assertEqual(len(adapter.trigger_calls), 2)
        self.assertFalse(sm._led_hold_active)

    def test_hold_does_not_touch_laser_or_soundswitch_paths(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _ready_led_active_deck(sm, 1)
        sm._led_hold_active = True

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_sp(1.1))

        self.assertEqual(director.tick_calls, [])
        self.assertEqual(adapter.trigger_calls, [])
        self.assertIsNone(sm._laser_director)
        self.assertIsNone(sm._laser_executor)
        self.assertEqual(sm._out.method_calls, [])

    def test_active_deck_switch_arms_led_hold(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        _ready_led_active_deck(sm, 1)

        sm._apply_nonzero_active_deck_switch(1, 2, "test")

        self.assertTrue(sm._led_hold_active)

    def test_active_deck_track_load_arms_hold_inactive_does_not(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        _ready_led_active_deck(sm, 1)

        sm._on_track_loaded(1, "active", BridgeEvent(Ev.TRACK_LOADED, 1, {}, "test"))
        self.assertTrue(sm._led_hold_active)

        sm._led_hold_active = False
        sm._on_track_loaded(2, "inactive", BridgeEvent(Ev.TRACK_LOADED, 2, {}, "test"))

        self.assertFalse(sm._led_hold_active)

    def test_idle_and_stop_clear_led_hold(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        sm._led_hold_active = True

        sm._enter_idle_no_audible(reason="test")
        self.assertFalse(sm._led_hold_active)

        sm._led_hold_active = True
        sm._do_stop(1, 1000)

        self.assertFalse(sm._led_hold_active)

    def test_led_role_mapping_uses_up_to_chorus_for_drop_impact(self) -> None:
        sm = _make_sm()

        self.assertEqual(
            sm._led_role_from_smart_phrasing(
                SmartPhrasingState(
                    abs_beat=64.0,
                    current_phrase_label="chorus",
                    current_phrase_is_chorus=True,
                    current_phrase_start_beat=64.0,
                    phrase_start_crossing=True,
                    previous_phrase_label="up",
                    beats_into_phrase=0.0,
                )
            ),
            "drop",
        )
        self.assertEqual(
            sm._led_role_from_smart_phrasing(
                SmartPhrasingState(
                    abs_beat=80.0,
                    current_phrase_label="chorus",
                    current_phrase_is_chorus=True,
                    current_phrase_start_beat=80.0,
                    phrase_start_crossing=True,
                    previous_phrase_label="chorus",
                    beats_into_phrase=0.0,
                )
            ),
            "post_drop",
        )

    def test_led_role_mapping_priorities_and_baseline(self) -> None:
        sm = _make_sm()

        self.assertEqual(
            sm._led_role_from_smart_phrasing(
                SmartPhrasingState(
                    smart_drop_crossing=True,
                    active_drop_beat=64.0,
                    current_phrase_label="chorus",
                    current_phrase_is_chorus=True,
                    current_phrase_start_beat=64.0,
                    phrase_start_crossing=True,
                    previous_phrase_label="up",
                    beats_into_phrase=20.0,
                )
            ),
            "drop",
        )
        self.assertEqual(
            sm._led_role_from_smart_phrasing(
                SmartPhrasingState(current_phrase_label="other")
            ),
            "groove",
        )
        self.assertEqual(
            sm._led_role_from_smart_phrasing(
                SmartPhrasingState(
                    current_phrase_label="low",
                    current_phrase_is_low=True,
                )
            ),
            "breakdown",
        )
        self.assertEqual(
            sm._led_role_from_smart_phrasing(
                SmartPhrasingState(
                    current_phrase_label="up",
                    current_phrase_is_up=True,
                    next_smart_drop_beat=96.0,
                    beats_to_next_drop=16.0,
                )
            ),
            "buildup",
        )

    def test_led_role_key_anchors_drop_and_cycles_post_drop_every_32(self) -> None:
        sm = _make_sm()
        deck = sm._deck[1]
        deck.load_gen = 11
        sm._led_first_drop_anchor_beat = 64.0

        drop_initial = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(active_drop_beat=64.0),
            "drop",
        )
        drop_hold = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(abs_beat=68.0),
            "drop",
        )
        self.assertEqual(drop_initial, drop_hold)

        post_20 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="chorus",
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            ),
            "post_drop",
        )
        post_28 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=92.0,
                current_phrase_label="chorus",
                current_phrase_start_beat=64.0,
                beats_into_phrase=28.0,
            ),
            "post_drop",
        )
        post_36 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=100.0,
                current_phrase_label="chorus",
                current_phrase_start_beat=64.0,
                beats_into_phrase=36.0,
            ),
            "post_drop",
        )
        self.assertEqual(post_20, post_28)
        self.assertNotEqual(post_20, post_36)

    def test_led_role_key_cycles_groove_every_32_from_phrase_marker(self) -> None:
        sm = _make_sm()
        deck = sm._deck[1]
        deck.load_gen = 11

        groove_20 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            ),
            "groove",
        )
        groove_31 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=95.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                beats_into_phrase=31.0,
            ),
            "groove",
        )
        groove_32 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=96.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                beats_into_phrase=32.0,
            ),
            "groove",
        )
        same_label_new_phrase = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=96.0,
                current_phrase_label="other",
                current_phrase_start_beat=96.0,
                phrase_start_crossing=True,
                beats_into_phrase=0.0,
            ),
            "groove",
        )

        self.assertEqual(groove_20, groove_31)
        self.assertNotEqual(groove_20, groove_32)
        self.assertNotEqual(groove_32, same_label_new_phrase)

    def test_empty_post_drop_bank_does_not_fall_back_to_drop_cycle(self) -> None:
        director = _AutomationLEDLookDirector()
        director.preview_decision = LEDLookDecision(
            look="room_drop",
            target="room_perimeter",
            action="scene",
            scene_ref="Scene-drop",
            reason="role_preview:drop",
            source="automation",
            priority=2,
            role="drop",
        )
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            ),
        )
        sm._led_first_drop_anchor_beat = 64.0

        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=92.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=64.0,
            beats_into_phrase=28.0,
        )
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=100.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=64.0,
            beats_into_phrase=36.0,
        )
        sm._push_tick()

        self.assertEqual(adapter.trigger_calls, [])
        self.assertEqual([call.role for call in director.tick_calls], ["post_drop", "post_drop"])

    def test_mapped_post_drop_keeps_post_drop_role(self) -> None:
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        director.preview_decisions["post_drop"] = LEDLookDecision(
            look="room_post_drop",
            target="room_perimeter",
            action="scene",
            scene_ref="Scene-post_drop",
            reason="role_preview:post_drop",
            source="automation",
            priority=2,
            role="post_drop",
        )
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=84.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=64.0,
                beats_into_phrase=20.0,
            ),
        )
        sm._led_first_drop_anchor_beat = 64.0

        sm._push_tick()

        self.assertEqual(adapter.trigger_calls[0].role, "post_drop")
        self.assertEqual(director.tick_calls[0].role, "post_drop")

    def test_drop_impact_switches_to_post_drop_after_configured_duration(self) -> None:
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=64.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=64.0,
                phrase_start_crossing=True,
                previous_phrase_label="up",
                beats_into_phrase=0.0,
            ),
        )

        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=71.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=64.0,
            beats_into_phrase=7.0,
        )
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=72.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=64.0,
            beats_into_phrase=8.0,
        )
        sm._push_tick()

        self.assertEqual([call.role for call in adapter.trigger_calls], ["drop", "post_drop"])
        self.assertEqual(sm._led_first_drop_anchor_beat, 64.0)
        self.assertEqual(sm._led_drop_impact_until_beat, 72.0)

    def test_second_chorus_marker_fires_one_more_drop(self) -> None:
        # After a buildup-led drop (count==1), a back-to-back Chorus->Chorus
        # marker fires one more drop impact before settling into post_drop.
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_first_drop_anchor_beat = 64.0
        sm._led_drop_impact_until_beat = 72.0
        sm._led_drop_impact_count = 1
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=80.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=80.0,
                phrase_start_crossing=True,
                previous_phrase_label="chorus",
                beats_into_phrase=0.0,
            ),
        )

        sm._push_tick()

        self.assertEqual(adapter.trigger_calls[0].role, "drop")
        # First anchor (post_drop cycle origin) is preserved; the second impact
        # consumes the one-more allowance.
        self.assertEqual(sm._led_first_drop_anchor_beat, 64.0)
        self.assertEqual(sm._led_drop_impact_count, 2)

    def test_chorus_anchor_without_impact_allows_next_two_chorus_drops(self) -> None:
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=32.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=32.0,
                phrase_start_crossing=True,
                previous_phrase_label="other",
                beats_into_phrase=0.0,
            ),
        )

        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=64.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=64.0,
            phrase_start_crossing=True,
            previous_phrase_label="chorus",
            beats_into_phrase=0.0,
        )
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=96.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=96.0,
            phrase_start_crossing=True,
            previous_phrase_label="chorus",
            beats_into_phrase=0.0,
        )
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=128.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=128.0,
            phrase_start_crossing=True,
            previous_phrase_label="chorus",
            beats_into_phrase=0.0,
        )
        sm._push_tick()

        self.assertEqual(
            [call.role for call in adapter.trigger_calls],
            ["post_drop", "drop", "drop", "post_drop"],
        )
        self.assertEqual(sm._led_first_drop_anchor_beat, 32.0)
        self.assertEqual(sm._led_drop_impact_count, 2)

    def test_groove_retriggers_on_32_count_cycle_and_phrase_marker(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=64.0,
                current_phrase_label="other",
                current_phrase_start_beat=64.0,
                phrase_start_crossing=True,
                beats_into_phrase=0.0,
            ),
        )

        # Tick 1: abs_beat=64 (phrase crossing, inside-guard so seq not advanced yet)
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=95.0,
            current_phrase_label="other",
            current_phrase_start_beat=64.0,
            beats_into_phrase=31.0,
        )
        # Tick 2: abs_beat=95 (first tick past GUARD: phrase latch advances seq→1, new key fires)
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=96.0,
            current_phrase_label="other",
            current_phrase_start_beat=64.0,
            beats_into_phrase=32.0,
        )
        # Tick 3: abs_beat=96 (32-beat cycle overflow: cycle 0→1, new key fires)
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=104.0,
            current_phrase_label="other",
            current_phrase_start_beat=104.0,
            phrase_start_crossing=True,
            beats_into_phrase=0.0,
        )
        # Tick 4 (abs_beat=104) now fires immediately on the crossing because GUARD is gone.
        sm._push_tick()

        # This gives 3 fires total: phrase 1 start, 32-beat overflow, phrase 2 start.
        roles = [call.role for call in adapter.trigger_calls]
        self.assertEqual(roles, ["groove", "groove", "groove"])

    def test_third_chorus_marker_falls_to_post_drop_and_keeps_first_anchor(self) -> None:
        # Once the two-in-a-row allowance is spent (count==2), further
        # Chorus->Chorus markers route to post_drop and keep the first anchor.
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_first_drop_anchor_beat = 64.0
        sm._led_drop_impact_until_beat = 72.0
        sm._led_drop_impact_count = 2
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=80.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=80.0,
                phrase_start_crossing=True,
                previous_phrase_label="chorus",
                beats_into_phrase=0.0,
            ),
        )

        sm._push_tick()

        self.assertEqual(adapter.trigger_calls[0].role, "post_drop")
        self.assertEqual(sm._led_first_drop_anchor_beat, 64.0)

    def test_post_drop_rotates_every_32_from_first_drop_anchor(self) -> None:
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_first_drop_anchor_beat = 64.0
        sm._led_drop_impact_until_beat = 72.0
        sm._led_drop_impact_count = 2
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=80.0,
                current_phrase_label="chorus",
                current_phrase_is_chorus=True,
                current_phrase_start_beat=80.0,
                phrase_start_crossing=True,
                previous_phrase_label="chorus",
                beats_into_phrase=0.0,
            ),
        )

        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=88.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=80.0,
            beats_into_phrase=8.0,
        )
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            abs_beat=96.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=96.0,
            phrase_start_crossing=True,
            previous_phrase_label="chorus",
            beats_into_phrase=0.0,
        )
        sm._push_tick()

        # tick 3 (abs_beat=96, cycle 0→1 via drop anchor) → 2nd fire.
        self.assertEqual([call.role for call in adapter.trigger_calls], ["post_drop", "post_drop"])


    def test_phrase_interruption_clears_drop_lifecycle(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_first_drop_anchor_beat = 64.0
        sm._led_drop_impact_until_beat = 72.0
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=68.0,
                current_phrase_label="other",
                beats_into_phrase=None,
            ),
        )

        sm._push_tick()

        self.assertEqual(adapter.trigger_calls[0].role, "groove")
        self.assertIsNone(sm._led_first_drop_anchor_beat)
        self.assertIsNone(sm._led_drop_impact_until_beat)

    def test_smart_drop_crossing_triggers_drop_once_without_tick_spam(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
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
        director.preview_decision = _drop_decision(
            "rt_drop_blue",
            backend="realtime_razer",
            action="realtime",
            scene_ref="drop_chase_blue",
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

    def test_committed_cloud_drop_is_the_look_fired_after_blackout(self) -> None:
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
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
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
        )
        sm._push_tick()

        self.assertEqual(director.commit_calls, ["drop"])
        self.assertEqual([call.look for call in adapter.trigger_calls], ["room_blackout", "cloud_drop"])
        self.assertEqual(adapter.trigger_calls[-1].backend, "cloud_diy")
        self.assertEqual([call.role for call in director.tick_calls], ["pre_drop"])

    def test_drop_fired_anchor_suppresses_redundant_pre_drop_blackout(self) -> None:
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        pre_drop_64 = SmartPhrasingState(
            transition_mask_arm_latched=True,
            transition_window_active=True,
            next_smart_drop_beat=64.0,
        )
        _prepare_playing_push_tick(sm, pre_drop_64)

        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
        )
        sm._push_tick()
        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: pre_drop_64
        sm._push_tick()

        self.assertEqual([call.look for call in adapter.trigger_calls], ["room_blackout", "cloud_drop"])
        self.assertEqual(sm._led_drop_look_fired_anchor, 64.0)

        sm._update_smart_phrasing_state = lambda *_args, **_kwargs: SmartPhrasingState(
            transition_mask_arm_latched=True,
            transition_window_active=True,
            next_smart_drop_beat=96.0,
        )
        sm._push_tick()

        self.assertEqual(adapter.trigger_calls[-1].look, "room_blackout")
        self.assertEqual(len(adapter.trigger_calls), 3)

    def test_emergency_blackout_still_fires_while_drop_anchor_latch_is_set(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._led_drop_look_fired_anchor = 64.0

        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].look, "room_blackout")
        self.assertEqual(adapter.trigger_calls[0].source, "emergency")

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
        director.preview_decision = _drop_decision("cloud_drop")
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
        director.preview_decision = _drop_decision(
            "rt_drop",
            backend="realtime_razer",
            action="realtime",
            scene_ref="drop_chase_blue",
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
            SmartPhrasingState(current_phrase_label="other"),
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

    def test_playing_automation_not_gated_by_autoloop_arm(self) -> None:
        director = _AutomationLEDLookDirector()
        director.mapped_roles.add("post_drop")
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.filepath = "/tracks/current.wav"
        sm._os.lighting_mode = "autoloop"

        # Stale position still gates (unchanged safety).
        sm._dispatch_led_automation(
            active=1,
            d=deck,
            sp_state=SmartPhrasingState(current_phrase_is_chorus=True),
            position_stale=True,
        )
        self.assertEqual(sm.led_status_provider()["automation_gate_reason"], "position_stale")
        self.assertEqual(len(adapter.trigger_calls), 0)

        # A freshly-playing, non-stale track lights immediately even though the
        # SoundSwitch autoloop arm has NOT completed — LEDs are no longer bound
        # to autoloop readiness.
        sm._dispatch_led_automation(
            active=1,
            d=deck,
            sp_state=SmartPhrasingState(current_phrase_is_chorus=True),
            position_stale=False,
        )
        self.assertNotEqual(
            sm.led_status_provider()["automation_gate_reason"], "autoloop_not_ready"
        )
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "post_drop")

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
            current_phrase_label="up",
            current_phrase_is_up=True,
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

        self.assertEqual(adapter.trigger_calls[-1].look, "room_drop")
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
        self.assertEqual(adapter.trigger_calls, [])

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
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
            ),
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
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
            ),
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

    def test_scripted_mode_enabled_bypasses_not_autoloop_gate(self) -> None:
        director = _AutomationLEDLookDirector(scripted_mode_automation=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(sm, SmartPhrasingState(), scripted=True)

        sm._push_tick()

        self.assertNotEqual(sm.led_status_provider()["automation_gate_reason"], "not_autoloop")
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "utility")
        self.assertEqual(adapter.trigger_calls[0].look, "room_blackout")

    def test_scripted_mode_default_role_map_at_dispatch_seam(self) -> None:
        cases = [
            (
                SmartPhrasingState(
                    current_phrase_is_up=True,
                    beats_to_next_drop=16.0,
                ),
                "buildup",
            ),
            (
                SmartPhrasingState(
                    smart_drop_crossing=True,
                    active_drop_beat=64.0,
                    current_phrase_label="up",
                ),
                "utility",
            ),
            (SmartPhrasingState(current_phrase_is_chorus=True), "utility"),
            (SmartPhrasingState(), "utility"),
            (SmartPhrasingState(smart_breakdown_active=True), "breakdown"),
        ]
        for sp_state, expected_role in cases:
            with self.subTest(expected_role=expected_role, sp_state=sp_state):
                director = _AutomationLEDLookDirector(scripted_mode_automation=True)
                adapter = _StubLEDAdapter()
                sm = _make_sm(director=director, adapter=adapter)
                _prepare_playing_push_tick(sm, sp_state, scripted=True)

                sm._push_tick()

                self.assertEqual(len(adapter.trigger_calls), 1)
                self.assertEqual(adapter.trigger_calls[0].role, expected_role)
                if expected_role == "utility":
                    self.assertEqual(adapter.trigger_calls[0].look, "room_blackout")

    def test_scripted_mode_override_allows_groove(self) -> None:
        director = _AutomationLEDLookDirector(
            scripted_mode_automation=True,
            scripted_role_map={"groove": "groove"},
        )
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(sm, SmartPhrasingState(), scripted=True)

        sm._push_tick()

        self.assertEqual(len(director.tick_calls), 1)
        self.assertEqual(director.tick_calls[0].role, "groove")
        self.assertEqual(adapter.trigger_calls[0].role, "groove")

    def test_scripted_mode_override_allows_post_drop(self) -> None:
        director = _AutomationLEDLookDirector(
            scripted_mode_automation=True,
            scripted_role_map={"post_drop": "post_drop"},
            mapped_roles={"ambient", "groove", "buildup", "drop", "post_drop", "breakdown", "utility"},
        )
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(current_phrase_is_chorus=True),
            scripted=True,
        )

        sm._push_tick()

        self.assertEqual(len(director.tick_calls), 1)
        self.assertEqual(director.tick_calls[0].role, "post_drop")
        self.assertEqual(adapter.trigger_calls[0].role, "post_drop")

    def test_scripted_mode_remap_does_not_apply_outside_scripted_lighting(self) -> None:
        director = _AutomationLEDLookDirector(
            scripted_mode_automation=True,
            scripted_role_map={"groove": "breakdown"},
        )
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(sm, SmartPhrasingState())
        sm._deck[1].scripted_id = 7
        sm._os.lighting_mode = "autoloop"

        sm._push_tick()

        self.assertEqual(len(director.tick_calls), 1)
        self.assertEqual(director.tick_calls[0].role, "groove")
        self.assertEqual(adapter.trigger_calls[0].role, "groove")

    def test_scripted_mode_role_helper_uses_policy_only_when_scripted(self) -> None:
        director = _AutomationLEDLookDirector(scripted_mode_automation=True)
        sm = _make_sm(director=director, adapter=_StubLEDAdapter())

        self.assertEqual(sm._led_effective_role_for_dispatch("ambient", scripted=True), "breakdown")
        self.assertEqual(sm._led_effective_role_for_dispatch("buildup", scripted=True), "buildup")
        self.assertEqual(sm._led_effective_role_for_dispatch("pre_drop", scripted=True), "buildup")
        self.assertEqual(sm._led_effective_role_for_dispatch("groove", scripted=True), "utility")
        self.assertEqual(sm._led_effective_role_for_dispatch("drop", scripted=True), "utility")
        self.assertEqual(sm._led_effective_role_for_dispatch("post_drop", scripted=True), "utility")
        self.assertEqual(sm._led_effective_role_for_dispatch("groove", scripted=False), "groove")

    def test_scripted_mode_dispatch_smoke_covers_multiple_phrase_states(self) -> None:
        states = [
            SmartPhrasingState(),
            SmartPhrasingState(current_phrase_is_chorus=True),
            SmartPhrasingState(
                current_phrase_is_up=True,
                beats_to_next_drop=16.0,
            ),
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                current_phrase_label="up",
            ),
        ]
        for sp_state in states:
            with self.subTest(sp_state=sp_state):
                director = _AutomationLEDLookDirector(scripted_mode_automation=True)
                adapter = _StubLEDAdapter()
                sm = _make_sm(director=director, adapter=adapter)
                _prepare_playing_push_tick(sm, sp_state, scripted=True)

                sm._push_tick()

                self.assertGreaterEqual(len(director.tick_calls), 1)

    def test_automation_disabled_is_inert_in_push_tick(self) -> None:
        director = _AutomationLEDLookDirector(automation_enabled=False)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
            ),
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
            SmartPhrasingState(
                smart_drop_crossing=True,
                active_drop_beat=64.0,
                current_phrase_label="up",
                current_phrase_is_up=True,
            ),
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
            SmartPhrasingState(),
        )

        sm._push_tick()

        self.assertEqual(director.status_calls, 1)
        self.assertEqual(adapter.status_calls, 0)
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "groove")


    def test_wi1_clamp_holds_jitter_and_accepts_seek(self):
        sm = _make_sm()
        sm._phrase_monotonic_enabled = True
        out = [sm._clamp_led_beat(v, 1, 0) for v in [100.0, 100.5, 100.49, 100.51, 99.0, 99.2]]
        self.assertEqual(out, [100.0, 100.5, 100.5, 100.51, 99.0, 99.2])
        self.assertEqual(sm._led_phrase_latch_reset_count, 1)

    def test_wi1_clamp_resets_across_load_gen(self):
        sm = _make_sm()
        sm._phrase_monotonic_enabled = True
        sm._clamp_led_beat(100.0, 1, 0)
        self.assertEqual(sm._clamp_led_beat(5.0, 1, 1), 5.0)

    def test_wi1_clamp_flag_off_is_passthrough(self):
        sm = _make_sm()
        sm._phrase_monotonic_enabled = False
        self.assertEqual([sm._clamp_led_beat(v, 1, 0) for v in [100.0, 99.5]], [100.0, 99.5])

    def test_wi2_oscillating_phrase_start_fires_once(self):
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._phrase_monotonic_enabled = True
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=112.0, current_phrase_label="up",
                current_phrase_start_beat=112.0, beats_into_phrase=0.0
            ),
        )
        for start in (112.0, 80.0, 112.0):
            sm._update_smart_phrasing_state = (lambda s: lambda *a, **k: SmartPhrasingState(
                abs_beat=112.0, current_phrase_label="up",
                current_phrase_start_beat=s, beats_into_phrase=112.0 - s))(start)
            sm._push_tick()
        self.assertEqual([c.role for c in adapter.trigger_calls], ["groove"])

    def test_wi2_flag_off_reproduces_flap(self):
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._phrase_monotonic_enabled = False
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=112.0, current_phrase_label="up",
                current_phrase_start_beat=112.0, beats_into_phrase=0.0
            ),
        )
        for start in (112.0, 80.0, 112.0): 
            sm._update_smart_phrasing_state = (lambda s: lambda *a, **k: SmartPhrasingState(
                abs_beat=112.0, current_phrase_label="up",
                current_phrase_start_beat=s, beats_into_phrase=112.0 - s))(start)
            sm._push_tick()
        self.assertGreaterEqual(len([c for c in adapter.trigger_calls if c.role == "groove"]), 2)
if __name__ == "__main__":
    unittest.main()
