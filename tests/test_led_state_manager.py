import logging
import queue
import sys
import time
import unittest
from pathlib import Path
from typing import Callable
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import state_manager as state_manager_mod  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import TrackAnlzData, WaveformContext  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import SpectralFeaturesV4, V4_SERIES_KEYS  # noqa: E402
from rb_ss_bridge_v2.govee_owner_state import GoveeOwnerStateMachine, OwnerState  # noqa: E402
from rb_ss_bridge_v2.led_identity_v2 import (  # noqa: E402
    IdentityStore,
    content_hash as led_identity_content_hash,
    content_key as led_identity_content_key,
)
from rb_ss_bridge_v2.drop_presentation import LASERS_ONLY, LEDS_PLUS_LASERS  # noqa: E402
from rb_ss_bridge_v2.led_dispatch_coordinator import LEDDispatchCoordinator  # noqa: E402
from rb_ss_bridge_v2.led_dispatch_policy import LED_IDLE_FREEWHEEL_BPM  # noqa: E402
from rb_ss_bridge_v2.led_models import (  # noqa: E402
    IdentityV2Config,
    LEDContext,
    LEDLookDecision,
    LEDRateLimits,
    ZoneRampConfig,
)
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    SmartPhrasingDiagnostic,
    SmartPhrasingResult,
    SmartPhrasingState,
)
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


class _CoordinatorConfig:
    blackout = "room_blackout"
    rate_limits = LEDRateLimits(min_look_dwell_s=0.0)


class _RecordingRealtimeRunner:
    def __init__(self) -> None:
        self.desired = []
        self.fire_count = 0
        self.emergency_count = 0
        self.assert_count = 0
        self.brightness_requests: list[int] = []

    def set_desired(self, spec) -> None:  # type: ignore[no-untyped-def]
        self.desired.append(spec)

    def fire_trigger(self) -> None:
        self.fire_count += 1

    def emergency_stop(self) -> None:
        self.emergency_count += 1

    def force_deactivate(self) -> None:
        self.desired.append(None)

    def request_activate_assert(self) -> None:
        self.assert_count += 1

    def request_brightness(self, value: int) -> None:
        self.brightness_requests.append(int(value))

    def status(self) -> dict:
        return {"active": bool(self.desired), "last_error": ""}

    def stop(self) -> bool:
        return True


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


class _StageCapableLEDAdapter(_TacticalLEDAdapter):
    """A tactical adapter that also supports AWR-150 cloud staging."""

    def __init__(self) -> None:
        super().__init__()
        self.stage_calls: list[LEDLookDecision] = []
        self.stage_accept = True

    def stage_cloud_takeover(self, decision: LEDLookDecision) -> bool:
        self.stage_calls.append(decision)
        return self.stage_accept


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
        self.substitute_decision: LEDLookDecision | None = None
        self.substitute_calls = 0
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

    def commit_role(
        self,
        role: str,
        *,
        diy_eligible: Callable[[str], bool] | None = None,
        look_preference: Callable[[str], bool] | None = None,
    ) -> LEDLookDecision | None:
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

    def substitute_realtime_drop(
        self,
        *,
        diy_eligible: Callable[[str], bool] | None = None,
        look_preference: Callable[[str], bool] | None = None,
    ) -> LEDLookDecision | None:
        self.substitute_calls += 1
        return self.substitute_decision

    def has_role_look(self, role: str) -> bool:
        return role in self.mapped_roles

    def drop_duration_beats(self, _look: str) -> float:
        return 8.0

    def post_drop_cycle_beats(self) -> float:
        return 32.0

    def reset_for_track(self) -> None:
        pass


class _IdentityColorEngine:
    enabled = True

    def __init__(self) -> None:
        self.identity_calls: list[tuple[int, int, str, dict]] = []
        self.begin_calls: list[dict] = []
        self.reset_calls = 0
        self.advance_calls: list[float] = []
        self.stand_down_calls: list[bool] = []

    def set_track_identity(self, deck: int, load_gen: int, key: str, record: dict) -> None:
        self.identity_calls.append((deck, load_gen, key, dict(record)))

    def diy_eligible(self, _look_name: str) -> bool:
        return True

    def begin_dispatch(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.begin_calls.append(dict(kwargs))

    def resolve_color(self, **_kwargs) -> dict:  # type: ignore[no-untyped-def]
        return {}

    def resolve_slot_colors(self, **_kwargs) -> dict:  # type: ignore[no-untyped-def]
        return {}

    def reset_fade_memory(self) -> None:
        self.reset_calls += 1

    def advance_fade(self, abs_beat: float) -> None:
        self.advance_calls.append(float(abs_beat))

    def set_scripted_stand_down(self, scripted: bool) -> None:
        self.stand_down_calls.append(bool(scripted))

    def snapshot(self) -> dict:
        return {"engine": "v2"}


class _ManualColorEngine:
    enabled = True

    def __init__(self) -> None:
        self._manual = ""
        self._config = type(
            "ManualColorConfig",
            (),
            {"palettes": {}, "v2": IdentityV2Config(enabled=False)},
        )()
        self.begin_calls: list[dict] = []

    def set_v2_active(self, _active: bool) -> None:
        pass

    def diy_eligible(self, _look_name: str) -> bool:
        return True

    def begin_dispatch(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.begin_calls.append(dict(kwargs))

    def resolve_color(self, **_kwargs) -> dict:  # type: ignore[no-untyped-def]
        colors = {
            "": (1, 2, 3),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "white_sand": (255, 235, 200),
            "rainbow": (255, 0, 255),
        }
        return {"color": colors.get(self._manual, (1, 2, 3))}

    def resolve_slot_colors(self, **_kwargs) -> dict:  # type: ignore[no-untyped-def]
        return {}

    def set_manual(self, name: str) -> None:
        self._manual = name

    def clear_manual(self) -> None:
        self._manual = ""

    def reset_fade_memory(self) -> None:
        pass

    def advance_fade(self, _abs_beat: float) -> None:
        pass

    def snapshot(self) -> dict:
        return {
            "engine": "v2",
            "manual": self._manual,
            "current_palette": self._manual or "neutral",
        }


def _make_sm(*, director=None, adapter=None, led_color_engine=None, led_identity_store=None) -> StateManager:
    return StateManager(
        queue.Queue(maxsize=64),
        PositionCache(),
        Mock(),
        led_look_director=director,
        led_scene_adapter=adapter,
        led_color_engine=led_color_engine,
        led_identity_store=led_identity_store,
    )


def _identity_record(key: str, zone: str = "GLACIER", *, base: str = "measured") -> dict:
    return {
        "zone": zone,
        "hue_slot": 0,
        "depth_variant": 0,
        "sat_floor": 0.7,
        "span": 0.5,
        "budget": 0.65,
        "style": "flowing",
        "base": base,
        "scores": {},
        "analysis_rev": "v4",
        "correction": None,
        "norm_inputs": {"bass": 0.5, "drama": 0.5, "punch": 0.0},
        "key_hash": led_identity_content_hash(key),
    }


def _identity_v2_config() -> IdentityV2Config:
    zone = ZoneRampConfig(
        base_ramp=((0, 80, 200), (0, 160, 230), (0, 220, 255)),
        accent_ramp=((0, 255, 255), (140, 220, 255)),
    )
    return IdentityV2Config(
        enabled=True,
        zones={
            name: zone
            for name in ("GLACIER", "DEEP_POOL", "TWILIGHT", "ION", "VOLT", "EMBERCORE", "NEUTRAL")
        },
    )


def _spectral_v4_fixture() -> SpectralFeaturesV4:
    n = 4
    series = {name: tuple(0.0 for _ in range(n)) for name in V4_SERIES_KEYS}
    series["sub_db"] = (-20.0, -19.0, -18.0, -17.0)
    series["bass_db"] = (-18.0, -17.0, -16.0, -15.0)
    series["sustain_mid_db"] = (20.0, 20.0, 20.0, 20.0)
    series["growl_flatness"] = (0.1, 0.1, 0.1, 0.1)
    return SpectralFeaturesV4(
        sr=22050,
        schema_version=4,
        n_beats=n,
        duration_s=2.0,
        frame_hop_s=0.01,
        sub_bass_envelope=tuple(0.0 for _ in range(n)),
        kick_envelope=tuple(0.0 for _ in range(n)),
        low_mid_envelope=tuple(0.0 for _ in range(n)),
        high_mid_envelope=tuple(0.0 for _ in range(n)),
        high_band_envelope=tuple(0.0 for _ in range(n)),
        kick_max_envelope=tuple(0.0 for _ in range(n)),
        onset_strength_envelope=tuple(0.0 for _ in range(n)),
        spectral_flatness_envelope=tuple(0.0 for _ in range(n)),
        series=series,
        sub4={},
        growl_band_frames=(),
        scalars={
            "grit": 0.2,
            "punch": 0.7,
            "drama": 0.4,
            "attack_low_p90": 0.5,
            "onset_mh_p90": 0.5,
            "brightness_med": 0.5,
            "growl_timbre_p90": 0.2,
        },
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


def _rt_decision(look: str = "rt_groove") -> LEDLookDecision:
    return LEDLookDecision(
        look=look,
        target="room_perimeter",
        action="realtime",
        scene_ref="groove_chase_blue",
        reason="role_entry:groove",
        source="automation",
        priority=2,
        role="groove",
        backend="realtime_razer",
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


def _make_realtime_color_sm():
    engine = _ManualColorEngine()
    director = _AutomationLEDLookDirector()
    director.role_decisions["groove"] = _rt_decision()
    runner = _RecordingRealtimeRunner()
    owner = GoveeOwnerStateMachine()
    coordinator = LEDDispatchCoordinator(
        _StubLEDAdapter(),
        runner,
        owner,
        _CoordinatorConfig(),
        time_fn=lambda: 1000.0,
    )
    coordinator._min_dwell_enabled = False
    sm = _make_sm(director=director, adapter=coordinator, led_color_engine=engine)
    sm._led_v2_latch = True
    _ready_led_active_deck(sm, 1)
    sm._deck[1].load_gen = 33
    sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_sp(2.0))
    return sm, engine, runner, owner


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


def _capture_perf(test: unittest.TestCase, logger_name: str) -> list[logging.LogRecord]:
    """Attach a capture handler to a perf.* logger for one test (AWR-125).

    No bridge_log.init(); propagate stays default so root is untouched.
    """
    logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    prior_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    test.addCleanup(logger.setLevel, prior_level)
    test.addCleanup(logger.removeHandler, handler)
    return records


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

    def test_pad_clear_blackout_removes_only_pad_owner(self) -> None:
        """AWR-154: pad release (reason=led_pad) must discard exactly the
        led_pad owner, leaving any other owner's claim on the darkness."""
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={"reason": "led_pad"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        self.assertEqual(sm._led_blackout_owners, {"led_pad", "legacy"})

        sm._handle_event(BridgeEvent(kind=Ev.LED_CLEAR_BLACKOUT, deck=0, payload={"reason": "led_pad"}, source="test"))

        self.assertEqual(sm._led_blackout_owners, {"legacy"})
        status = sm.led_status_provider()
        self.assertTrue(status["emergency_blackout"])

    def test_bare_clear_blackout_clears_all_owners_and_logs_once(self) -> None:
        """AWR-155: a bare led_clear_blackout (no reason) is operator
        authority and clears every blackout owner at once, with exactly one
        INFO outcome log naming what was cleared."""
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_SCENE, deck=0, payload={"look": "room_drop_a"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={"reason": "led_pad"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={"reason": "drop_spotlight"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        self.assertEqual(sm._led_blackout_owners, {"led_pad", "drop_spotlight", "legacy"})

        with self.assertLogs("state_manager", level="INFO") as captured:
            sm._handle_event(BridgeEvent(kind=Ev.LED_CLEAR_BLACKOUT, deck=0, payload={}, source="test"))

        self.assertEqual(sm._led_blackout_owners, set())
        status = sm.led_status_provider()
        self.assertFalse(status["emergency_blackout"])
        clear_all_lines = [line for line in captured.output if "blackout-clear-all" in line]
        self.assertEqual(len(clear_all_lines), 1)
        self.assertIn("led_pad", clear_all_lines[0])
        self.assertIn("drop_spotlight", clear_all_lines[0])
        self.assertIn("legacy", clear_all_lines[0])

    def test_restore_brightness_fires_when_clear_all_empties_owners(self) -> None:
        """AWR-155: a bare clear-all that empties the owner set fires the
        same brightness-restore backstop as any other now-clear transition."""

        class _RestoreAdapter(_StubLEDAdapter):
            def __init__(self, **kw) -> None:
                super().__init__(**kw)
                self.restore_calls = 0

            def restore_brightness(self) -> None:
                self.restore_calls += 1

        adapter = _RestoreAdapter()
        sm = _make_sm(director=_StubLEDLookDirector(enabled=True), adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={"reason": "led_pad"}, source="test"))
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={"reason": "drop_spotlight"}, source="test"))
        self.assertEqual(adapter.restore_calls, 0)

        sm._handle_event(BridgeEvent(kind=Ev.LED_CLEAR_BLACKOUT, deck=0, payload={}, source="test"))

        self.assertEqual(adapter.restore_calls, 1)
        self.assertFalse(sm.led_status_provider()["emergency_blackout"])

    def test_blackout_brightness_backstop_fires_on_accept_only(self) -> None:
        """AWR-146 Task 6: an accepted LED_BLACKOUT dims via the adapter's
        blackout_brightness; a cloud-only adapter without the method is a safe
        no-op; a rejected (unknown-target) blackout does NOT dim."""

        class _DimAdapter(_StubLEDAdapter):
            def __init__(self, **kw) -> None:
                super().__init__(**kw)
                self.dim_calls = 0

            def blackout_brightness(self) -> None:
                self.dim_calls += 1

        # 1. accepted blackout invokes blackout_brightness exactly once
        adapter = _DimAdapter()
        sm = _make_sm(director=_StubLEDLookDirector(enabled=True), adapter=adapter)
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        self.assertEqual(adapter.dim_calls, 1)

        # 2. cloud-only adapter WITHOUT the method → safe no-op (no exception)
        plain = _StubLEDAdapter()
        sm2 = _make_sm(director=_StubLEDLookDirector(enabled=True), adapter=plain)
        sm2._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        self.assertTrue(sm2.led_status_provider()["emergency_blackout"])

        # 3. rejected (unknown-target) blackout must NOT dim
        adapter3 = _DimAdapter()
        sm3 = _make_sm(director=_StubLEDLookDirector(enabled=True), adapter=adapter3)
        sm3._handle_event(BridgeEvent(
            kind=Ev.LED_BLACKOUT, deck=0,
            payload={"target": "missing_strip"}, source="test"))
        self.assertEqual(adapter3.dim_calls, 0)
        self.assertIn("unknown_target", sm3.led_status_provider()["last_error"])

    def test_sanitize_preserves_frame_engine_health_keys(self) -> None:
        """AWR-146 REQUIRED-4e: engine_alive/achieved_fps/respawn_count/fps_degraded
        survive `_sanitize_led_adapter_status`, so the frame-engine self-report
        reaches the runtime status surface."""
        sm = _make_sm(director=_StubLEDLookDirector(enabled=True), adapter=_StubLEDAdapter())
        safe = sm._sanitize_led_adapter_status({
            "realtime": {
                "owner": "realtime_razer", "active": True,
                "engine_alive": True, "achieved_fps": 60.9,
                "respawn_count": 2, "fps_degraded": False,
            }
        })
        rt = safe["realtime"]
        self.assertEqual(rt["engine_alive"], True)
        self.assertEqual(rt["achieved_fps"], 60.9)
        self.assertEqual(rt["respawn_count"], 2)
        self.assertEqual(rt["fps_degraded"], False)

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

    def test_dwell_rejected_automation_retries_same_decision_without_reticking(self) -> None:
        """A coordinator-rejected automation dispatch is re-sent with the SAME
        cached decision after ~0.35 s, without the role_key changing and without
        re-ticking the director (AWR-145 latch-on-accept retry)."""
        clock = [1000.0]

        class _RejectOnceAdapter(_StubLEDAdapter):
            def trigger(self, decision: LEDLookDecision) -> bool:
                self.trigger_calls.append(decision)
                return len(self.trigger_calls) > 1  # reject the 1st, accept after

        director = _AutomationLEDLookDirector()
        director.role_decisions["groove"] = _rt_decision()
        adapter = _RejectOnceAdapter(accept=True)
        sm = _make_sm(director=director, adapter=adapter)
        _ready_led_active_deck(sm, 1)
        sm._deck[1].load_gen = 33
        sp = _groove_sp(2.0)

        with patch("rb_ss_bridge_v2.led_dispatch_policy.time.monotonic", lambda: clock[0]):
            # 1st dispatch: director ticks, decision sent, adapter rejects → retry cached.
            sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=sp)
            self.assertEqual(len(adapter.trigger_calls), 1)
            self.assertIsNotNone(sm._led_auto_retry)
            director_ticks = len(director.tick_calls)

            # Same role_key, retry not yet due (<0.35 s): no re-send.
            clock[0] = 1000.2
            sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=sp)
            self.assertEqual(len(adapter.trigger_calls), 1)

            # Retry now due: same decision re-sent, adapter accepts, director NOT re-ticked.
            clock[0] = 1000.4
            sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=sp)

        self.assertEqual(len(adapter.trigger_calls), 2)
        self.assertEqual(len(director.tick_calls), director_ticks)  # cursor unchanged
        self.assertIsNone(sm._led_auto_retry)  # cleared on accept

    def test_dwell_rejected_idle_retries_and_starts_freewheel(self) -> None:
        """A rejected idle look retries and, once accepted with a realtime backend,
        starts the idle freewheel (AWR-145)."""
        clock = [500.0]

        class _RejectOnceAdapter(_StubLEDAdapter):
            def trigger(self, decision: LEDLookDecision) -> bool:
                self.trigger_calls.append(decision)
                return len(self.trigger_calls) > 1

        director = _AutomationLEDLookDirector()
        director.role_decisions["ambient"] = LEDLookDecision(
            look="rt_twinkle", target="room_perimeter", action="realtime",
            scene_ref="rt_twinkle", reason="role_entry:ambient", source="automation",
            priority=2, role="ambient", backend="realtime_razer", params={},
        )
        adapter = _RejectOnceAdapter(accept=True)
        sm = _make_sm(director=director, adapter=adapter)
        d = sm._deck[1]
        d.load_gen = 11
        d.meta.filepath = "/tracks/current.wav"

        with patch("rb_ss_bridge_v2.led_dispatch_policy.time.monotonic", lambda: clock[0]):
            sm._dispatch_led_idle_ambient(active=1, d=d, reason="test")  # rejected → cached
            self.assertEqual(len(adapter.trigger_calls), 1)
            self.assertIsNotNone(sm._led_idle_retry)
            self.assertIsNone(sm._led_idle_freewheel_since)

            clock[0] = 500.2  # not yet due
            sm._dispatch_led_idle_ambient(active=1, d=d, reason="test")
            self.assertEqual(len(adapter.trigger_calls), 1)

            clock[0] = 500.4  # due → accept → freewheel starts
            sm._dispatch_led_idle_ambient(active=1, d=d, reason="test")

        self.assertEqual(len(adapter.trigger_calls), 2)
        self.assertIsNone(sm._led_idle_retry)
        self.assertIsNotNone(sm._led_idle_freewheel_since)

    def test_retry_slots_cleared_on_transitions(self) -> None:
        """Both retry slots clear on deck switch, idle reset, LED_BLACKOUT, and gate
        transition — a stale retry must never fire across a mode change (AWR-145)."""
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())

        def _arm_retries() -> None:
            sm._led_auto_retry = ("k", "groove", _rt_decision(), 1)
            sm._led_idle_retry = ("k", _rt_decision(), 1)

        # Deck switch.
        _arm_retries()
        sm._reset_for_active_deck_entry(2, "test")
        self.assertIsNone(sm._led_auto_retry)
        self.assertIsNone(sm._led_idle_retry)

        # Idle reset.
        _arm_retries()
        sm._enter_idle_no_audible(reason="test")
        self.assertIsNone(sm._led_auto_retry)
        self.assertIsNone(sm._led_idle_retry)

        # LED_BLACKOUT event.
        _arm_retries()
        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))
        self.assertIsNone(sm._led_auto_retry)
        self.assertIsNone(sm._led_idle_retry)

        # Automation gate transition.
        _arm_retries()
        sm._gate_led_automation("manual_override", active_deck=1)
        self.assertIsNone(sm._led_auto_retry)
        self.assertIsNone(sm._led_idle_retry)

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

    def test_missing_phrase_data_hold_releases_on_beat_backstop(self) -> None:
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=adapter)
        _ready_led_active_deck(sm, 1)

        sm._apply_nonzero_active_deck_switch(1, 2, "test")
        _ready_led_active_deck(sm, 2, filepath="/tracks/next.wav")

        no_phrase = SmartPhrasingState(abs_beat=64.0, current_phrase_label="other")
        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=no_phrase)
        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertTrue(sm._led_hold_active)

        before_bound = SmartPhrasingState(
            abs_beat=64.0 + state_manager_mod.LED_HOLD_BACKSTOP_BEATS - 0.1,
            current_phrase_label="other",
        )
        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=before_bound)
        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertTrue(sm._led_hold_active)

        at_bound = SmartPhrasingState(
            abs_beat=64.0 + state_manager_mod.LED_HOLD_BACKSTOP_BEATS,
            current_phrase_label="other",
        )
        sm._dispatch_led_automation(active=2, d=sm._deck[2], sp_state=at_bound)
        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertFalse(sm._led_hold_active)
        self.assertEqual(sm._led_hold_started_mono, 0.0)
        self.assertIsNone(sm._led_hold_started_beat)

    def test_missing_phrase_data_hold_releases_on_time_backstop_without_beat(self) -> None:
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=adapter)
        _ready_led_active_deck(sm, 1)
        sm._led_hold_active = True

        no_beat = SmartPhrasingState(current_phrase_label="other")
        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=no_beat)
        self.assertEqual(len(adapter.trigger_calls), 0)
        self.assertTrue(sm._led_hold_active)

        sm._led_hold_started_mono -= state_manager_mod.LED_HOLD_BACKSTOP_S
        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=no_beat)

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertFalse(sm._led_hold_active)
        self.assertEqual(sm._led_hold_started_mono, 0.0)
        self.assertIsNone(sm._led_hold_started_beat)

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
        sm._led_hold_started_mono = 123.0
        sm._led_hold_started_beat = 456.0

        sm._apply_nonzero_active_deck_switch(1, 2, "test")

        self.assertTrue(sm._led_hold_active)
        self.assertEqual(sm._led_hold_started_mono, 0.0)
        self.assertIsNone(sm._led_hold_started_beat)

    def test_active_deck_track_load_arms_hold_inactive_does_not(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        _ready_led_active_deck(sm, 1)
        sm._led_hold_started_mono = 123.0
        sm._led_hold_started_beat = 456.0

        sm._on_track_loaded(1, "active", BridgeEvent(Ev.TRACK_LOADED, 1, {}, "test"))
        self.assertTrue(sm._led_hold_active)
        self.assertEqual(sm._led_hold_started_mono, 0.0)
        self.assertIsNone(sm._led_hold_started_beat)

        sm._led_hold_active = False
        sm._on_track_loaded(2, "inactive", BridgeEvent(Ev.TRACK_LOADED, 2, {}, "test"))

        self.assertFalse(sm._led_hold_active)

    def test_idle_and_stop_clear_led_hold(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        sm._led_hold_active = True
        sm._led_hold_started_mono = 123.0
        sm._led_hold_started_beat = 456.0

        sm._enter_idle_no_audible(reason="test")
        self.assertFalse(sm._led_hold_active)
        self.assertEqual(sm._led_hold_started_mono, 0.0)
        self.assertIsNone(sm._led_hold_started_beat)

        sm._led_hold_active = True
        sm._led_hold_started_mono = 123.0
        sm._led_hold_started_beat = 456.0
        sm._do_stop(1, 1000)

        self.assertFalse(sm._led_hold_active)
        self.assertEqual(sm._led_hold_started_mono, 0.0)
        self.assertIsNone(sm._led_hold_started_beat)

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
                SmartPhrasingState(
                    smart_drop_crossing=True,
                    active_drop_beat=96.0,
                    current_phrase_label="other",
                    previous_phrase_label="groove",
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

    def test_led_role_key_cycles_buildup_by_remaining_drop_distance(self) -> None:
        sm = _make_sm()
        deck = sm._deck[1]
        deck.load_gen = 11

        observed = []
        for remaining in (100.0, 64.0, 63.999, 32.0, 31.999, 0.0):
            key = sm._led_automation_role_key(
                1,
                deck,
                SmartPhrasingState(
                    next_smart_drop_beat=128.0,
                    beats_to_next_drop=remaining,
                ),
                "buildup",
            )
            observed.append((key, sm._led_last_section_cycle))

        self.assertEqual(
            observed,
            [
                ("1:11:buildup:128.000:c3", ("128.000", 3)),
                ("1:11:buildup:128.000:c2", ("128.000", 2)),
                ("1:11:buildup:128.000:c1", ("128.000", 1)),
                ("1:11:buildup:128.000:c1", ("128.000", 1)),
                ("1:11:buildup:128.000:c0", ("128.000", 0)),
                ("1:11:buildup:128.000:c0", ("128.000", 0)),
            ],
        )

        missing_distance = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(next_smart_drop_beat=128.0),
            "buildup",
        )
        self.assertEqual(missing_distance, "1:11:buildup:128.000:c0")
        self.assertEqual(sm._led_last_section_cycle, ("128.000", 0))

    def test_led_role_key_cycles_pre_drop_with_same_marker_shape(self) -> None:
        sm = _make_sm()
        deck = sm._deck[1]
        deck.load_gen = 11

        before = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(next_smart_drop_beat=128.0, beats_to_next_drop=64.0),
            "pre_drop",
        )
        after = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(next_smart_drop_beat=128.0, beats_to_next_drop=31.999),
            "pre_drop",
        )

        self.assertEqual(before, "1:11:pre_drop:128.000:c2")
        self.assertEqual(after, "1:11:pre_drop:128.000:c0")
        self.assertEqual(sm._led_last_section_cycle, ("128.000", 0))

    def test_led_role_key_cycles_breakdown_by_restore_distance(self) -> None:
        sm = _make_sm()
        deck = sm._deck[1]
        deck.load_gen = 11

        observed = []
        for abs_beat in (60.0, 96.0, 96.001, 128.0, 128.001, 160.0):
            key = sm._led_automation_role_key(
                1,
                deck,
                SmartPhrasingState(
                    abs_beat=abs_beat,
                    breakdown_restore_beat=160.0,
                ),
                "breakdown",
            )
            observed.append((key, sm._led_last_section_cycle))

        self.assertEqual(
            observed,
            [
                ("1:11:breakdown:160.000:c3", ("160.000", 3)),
                ("1:11:breakdown:160.000:c2", ("160.000", 2)),
                ("1:11:breakdown:160.000:c1", ("160.000", 1)),
                ("1:11:breakdown:160.000:c1", ("160.000", 1)),
                ("1:11:breakdown:160.000:c0", ("160.000", 0)),
                ("1:11:breakdown:160.000:c0", ("160.000", 0)),
            ],
        )

        missing_abs_beat = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(breakdown_restore_beat=160.0),
            "breakdown",
        )
        self.assertEqual(missing_abs_beat, "1:11:breakdown:160.000:c0")
        self.assertEqual(sm._led_last_section_cycle, ("160.000", 0))

    def test_led_role_key_cycles_monotonic_ambient_by_phrase_elapsed(self) -> None:
        sm = _make_sm()
        sm._phrase_monotonic_enabled = True
        sm._led_phrase_seq = 5
        sm._led_phrase_committed_start = 64.0
        deck = sm._deck[1]
        deck.load_gen = 11

        ambient_31 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=95.0,
                current_phrase_label="intro",
                current_phrase_start_beat=64.0,
            ),
            "ambient",
        )
        ambient_32 = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=96.0,
                current_phrase_label="intro",
                current_phrase_start_beat=64.0,
            ),
            "ambient",
        )
        self.assertEqual(ambient_31, "1:11:ambient:intro:seq5:c0")
        self.assertEqual(ambient_32, "1:11:ambient:intro:seq5:c1")
        self.assertEqual(sm._led_last_section_cycle, ("intro:seq5", 1))

        sm._led_phrase_seq = 6
        sm._led_phrase_committed_start = 96.0
        next_seq = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=96.0,
                current_phrase_label="intro",
                current_phrase_start_beat=96.0,
            ),
            "ambient",
        )
        self.assertEqual(next_seq, "1:11:ambient:intro:seq6:c0")
        self.assertNotEqual(ambient_32, next_seq)

    def test_led_role_key_keeps_legacy_ambient_without_monotonic_cycle(self) -> None:
        sm = _make_sm()
        sm._phrase_monotonic_enabled = False
        deck = sm._deck[1]
        deck.load_gen = 11

        key = sm._led_automation_role_key(
            1,
            deck,
            SmartPhrasingState(
                abs_beat=96.0,
                current_phrase_label="intro",
                current_phrase_start_beat=64.0,
            ),
            "ambient",
        )

        self.assertEqual(key, "1:11:ambient:intro")
        self.assertEqual(sm._led_last_section_cycle, ("intro", 0))

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

    def test_label_only_second_chorus_marker_fires_capped_drop(self) -> None:
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
        self.assertEqual(sm._led_first_drop_anchor_beat, 64.0)
        self.assertEqual(sm._led_drop_impact_count, 2)
        self.assertEqual(sm._led_drop_impact_until_beat, 88.0)

    def test_chorus_anchor_without_impact_allows_two_later_chorus_hits(self) -> None:
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

    def test_cloud_previewed_drop_still_gets_realtime_tactical_blackout(self) -> None:
        """Interim guard (live 2026-07-08): the pre-drop blackout must never ride
        the internet. A cloud-previewed drop on a tactical-capable adapter takes
        the realtime tactical branch — razer black frames, no cloud scene."""
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
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
        self.assertEqual(adapter.tactical_calls[0].look, "cloud_drop")
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

    def test_awr150_cloud_drop_stages_and_substitutes_realtime(self) -> None:
        """AWR-150: a cloud-picked drop on a stage-capable adapter fires a
        realtime substitute ON the beat and stages the committed cloud scene to
        take over mid-drop; the drop is recorded under the committed identity."""
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")  # committed pick is cloud
        director.substitute_decision = _drop_decision(
            "rt_sub", backend="realtime_razer", action="realtime", scene_ref="drop_chase_blue",
        )
        adapter = _StageCapableLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                transition_mask_arm_latched=True,
                transition_window_active=True,
                next_smart_drop_beat=64.0,
            ),
        )

        sm._push_tick()  # pre-drop blackout -> realtime tactical (never cloud)
        self.assertEqual(len(adapter.tactical_calls), 1)
        self.assertEqual(len(adapter.trigger_calls), 0)

        sm._update_smart_phrasing_state = lambda *_a, **_k: SmartPhrasingState(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
        )
        sm._push_tick()  # impact -> RT substitute on the beat + stage committed cloud

        # The realtime substitute was dispatched through the normal trigger path.
        self.assertEqual([c.look for c in adapter.trigger_calls], ["rt_sub"])
        self.assertEqual(adapter.trigger_calls[-1].backend, "realtime_razer")
        # The committed cloud scene was staged exactly once (no realtime teardown).
        self.assertEqual([c.look for c in adapter.stage_calls], ["cloud_drop"])
        self.assertEqual(adapter.stage_calls[-1].backend, "cloud_diy")
        # Drop lifecycle recorded under the COMMITTED cloud identity, pending cleared.
        self.assertEqual(sm._led_active_drop_look, "cloud_drop")
        self.assertIsNone(sm._led_drop_cloud_stage_pending)

    def test_awr150_cloud_only_adapter_keeps_cloud_dispatch(self) -> None:
        """A cloud-only adapter (no stage_cloud_takeover) fires the cloud drop
        directly and never consults the substitute, even when one is available."""
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
        director.substitute_decision = _drop_decision(
            "rt_sub", backend="realtime_razer", action="realtime", scene_ref="drop_chase_blue",
        )
        adapter = _StubLEDAdapter()  # no stage_cloud_takeover, no tactical_blackout
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
        sm._update_smart_phrasing_state = lambda *_a, **_k: SmartPhrasingState(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
        )
        sm._push_tick()

        self.assertEqual([c.look for c in adapter.trigger_calls], ["room_blackout", "cloud_drop"])
        self.assertEqual(adapter.trigger_calls[-1].backend, "cloud_diy")
        self.assertEqual(director.substitute_calls, 0)  # substitute never consulted

    def test_awr150_substitute_retry_then_accept_stages_once(self) -> None:
        """A coordinator-rejected substitute retries the SAME substitute; the
        committed cloud scene is staged only on the accepted retry, exactly once."""
        clock = [1000.0]
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
        director.substitute_decision = _drop_decision(
            "rt_sub", backend="realtime_razer", action="realtime", scene_ref="drop_chase_blue",
        )

        class _RejectSubOnce(_StageCapableLEDAdapter):
            def trigger(self, decision: LEDLookDecision) -> bool:
                self.trigger_calls.append(decision)
                return len(self.trigger_calls) > 1  # reject 1st substitute, accept the retry

        adapter = _RejectSubOnce()
        sm = _make_sm(director=director, adapter=adapter)
        crossing = SmartPhrasingState(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
        )

        with patch("rb_ss_bridge_v2.led_dispatch_policy.time.monotonic", lambda: clock[0]):
            _prepare_playing_push_tick(
                sm,
                SmartPhrasingState(
                    transition_mask_arm_latched=True,
                    transition_window_active=True,
                    next_smart_drop_beat=64.0,
                ),
            )
            sm._push_tick()  # blackout tactical + commit cloud_drop
            sm._update_smart_phrasing_state = lambda *_a, **_k: crossing
            sm._push_tick()  # impact: substitute rejected -> retry cached, nothing staged
            self.assertEqual(len(adapter.stage_calls), 0)
            self.assertIsNotNone(sm._led_auto_retry)
            clock[0] = 1000.4  # retry now due
            sm._push_tick()  # retry: substitute accepted -> stage committed once

        self.assertEqual([c.look for c in adapter.trigger_calls], ["rt_sub", "rt_sub"])
        self.assertEqual([c.look for c in adapter.stage_calls], ["cloud_drop"])
        self.assertEqual(sm._led_active_drop_look, "cloud_drop")
        self.assertIsNone(sm._led_drop_cloud_stage_pending)

    def test_awr150_stage_capable_but_cloud_only_bank_keeps_cloud_dispatch(self) -> None:
        """Stage-CAPABLE adapter but a cloud-only drop bank (substitute returns None):
        the committed cloud decision dispatches through the existing cloud path and
        nothing is staged."""
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
        director.substitute_decision = None  # cloud-only drop bank -> no RT substitute
        adapter = _StageCapableLEDAdapter()  # can stage, but there is nothing to substitute
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                transition_mask_arm_latched=True,
                transition_window_active=True,
                next_smart_drop_beat=64.0,
            ),
        )
        sm._push_tick()  # blackout tactical (adapter has tactical_blackout)
        sm._update_smart_phrasing_state = lambda *_a, **_k: SmartPhrasingState(
            smart_drop_crossing=True, active_drop_beat=64.0,
            current_phrase_label="up", current_phrase_is_up=True,
        )
        sm._push_tick()  # impact: substitute is None -> today's cloud dispatch

        self.assertEqual([c.look for c in adapter.trigger_calls], ["cloud_drop"])
        self.assertEqual(adapter.trigger_calls[-1].backend, "cloud_diy")
        self.assertEqual(adapter.stage_calls, [])         # nothing staged
        self.assertEqual(director.substitute_calls, 1)    # substitute WAS consulted, returned None
        self.assertEqual(sm._led_active_drop_look, "cloud_drop")
        self.assertIsNone(sm._led_drop_cloud_stage_pending)

    def test_awr150_stage_raises_still_completes_the_impact(self) -> None:
        """If stage_cloud_takeover RAISES, the accepted realtime substitute already
        owns the beat — the impact completes (logged, not failed) and the drop is
        still recorded under the committed identity."""
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
        director.substitute_decision = _drop_decision(
            "rt_sub", backend="realtime_razer", action="realtime", scene_ref="drop_chase_blue",
        )

        class _RaisingStageAdapter(_StageCapableLEDAdapter):
            def stage_cloud_takeover(self, decision: LEDLookDecision) -> bool:
                self.stage_calls.append(decision)
                raise RuntimeError("cloud staging boom")

        adapter = _RaisingStageAdapter()
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
        sm._update_smart_phrasing_state = lambda *_a, **_k: SmartPhrasingState(
            smart_drop_crossing=True, active_drop_beat=64.0,
            current_phrase_label="up", current_phrase_is_up=True,
        )
        sm._push_tick()  # impact: RT substitute dispatched, stage raises but is swallowed

        self.assertEqual([c.look for c in adapter.trigger_calls], ["rt_sub"])  # impact completed
        self.assertEqual(len(adapter.stage_calls), 1)                          # stage was attempted
        self.assertEqual(sm._led_active_drop_look, "cloud_drop")               # recorded under committed
        self.assertIsNone(sm._led_drop_cloud_stage_pending)                    # cleared, no leak

    def test_awr150_retry_exhaustion_clears_stage_pending_no_leak(self) -> None:
        """When the substitute is rejected until the AWR-145 retry gives up, the
        stage-pending slot is cleared and never leaks into a later drop. Driven
        through _dispatch_led_automation directly (like the existing retry tests)
        so the fake clock does not trip _push_tick's deck-staleness path."""
        clock = [1000.0]
        director = _AutomationLEDLookDirector()
        director.preview_decision = _drop_decision("cloud_drop")
        director.substitute_decision = _drop_decision(
            "rt_sub", backend="realtime_razer", action="realtime", scene_ref="drop_chase_blue",
        )

        class _RejectableStageAdapter(_StageCapableLEDAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.reject_trigger = True

            def trigger(self, decision: LEDLookDecision) -> bool:
                self.trigger_calls.append(decision)
                return not self.reject_trigger

        adapter = _RejectableStageAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _ready_led_active_deck(sm, 1)
        sm._deck[1].load_gen = 33
        d = sm._deck[1]
        pre_drop = SmartPhrasingState(
            transition_mask_arm_latched=True, transition_window_active=True,
            next_smart_drop_beat=64.0,
        )
        crossing = SmartPhrasingState(
            smart_drop_crossing=True, active_drop_beat=64.0,
            current_phrase_label="up", current_phrase_is_up=True,
        )

        with patch("rb_ss_bridge_v2.led_dispatch_policy.time.monotonic", lambda: clock[0]):
            sm._dispatch_led_smart_drop_blackout(active=1, d=d, sp_state=pre_drop, phase="pre_drop")  # commit cloud_drop
            sm._dispatch_led_automation(active=1, d=d, sp_state=crossing)  # impact: substitute rejected
            self.assertIsNotNone(sm._led_auto_retry)
            self.assertIsNotNone(sm._led_drop_cloud_stage_pending)

            guard = 0
            while sm._led_auto_retry is not None and guard < 20:
                clock[0] += 0.4  # past LED_DISPATCH_RETRY_S each time -> retry path fires
                sm._dispatch_led_automation(active=1, d=d, sp_state=crossing)
                guard += 1

            # Retry gave up; the pending cloud stage is cleared, nothing ever staged.
            self.assertIsNone(sm._led_auto_retry)
            self.assertIsNone(sm._led_drop_cloud_stage_pending)
            self.assertEqual(adapter.stage_calls, [])

            # A fresh drop that ACCEPTS its substitute must stage its OWN committed
            # decision exactly once — proving the cleared slot leaked nothing stale.
            adapter.reject_trigger = False
            sm._deck[1].load_gen = 34  # new load_gen -> fresh role_key, not the old retry
            d = sm._deck[1]
            pre_drop2 = SmartPhrasingState(
                transition_mask_arm_latched=True, transition_window_active=True,
                next_smart_drop_beat=96.0,
            )
            crossing2 = SmartPhrasingState(
                smart_drop_crossing=True, active_drop_beat=96.0,
                current_phrase_label="up", current_phrase_is_up=True,
            )
            sm._dispatch_led_smart_drop_blackout(active=1, d=d, sp_state=pre_drop2, phase="pre_drop")  # commit cloud_drop
            sm._dispatch_led_automation(active=1, d=d, sp_state=crossing2)  # impact accepts

        self.assertEqual([c.look for c in adapter.stage_calls], ["cloud_drop"])  # exactly one, the NEW drop
        self.assertEqual(sm._led_active_drop_look, "cloud_drop")

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

    def test_realtime_idle_ambient_freewheels_beat_anchor(self) -> None:
        now = 100.0

        def fake_monotonic() -> float:
            return now

        director = _AutomationLEDLookDirector()
        director.role_decisions["ambient"] = LEDLookDecision(
            look="rt_twinkle",
            target="room_perimeter",
            action="realtime",
            scene_ref="rt_twinkle",
            reason="role_entry:ambient",
            source="automation",
            priority=2,
            role="ambient",
            backend="realtime_razer",
            params={},
        )
        sm = _make_sm(director=director, adapter=_StubLEDAdapter())
        d = sm._deck[1]
        d.load_gen = 11
        d.meta.filepath = "/tracks/current.wav"

        with patch("rb_ss_bridge_v2.led_dispatch_policy.time.monotonic", fake_monotonic):
            sm._dispatch_led_idle_ambient(active=1, d=d, reason="test")
            now = 100.25
            first = sm.get_active_beat_anchor()
            now = 100.75
            second = sm.get_active_beat_anchor()

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None
        assert second is not None
        self.assertEqual(first.deck, 0)
        self.assertEqual(first.bpm, LED_IDLE_FREEWHEEL_BPM)
        self.assertTrue(first.playing)
        self.assertTrue(first.permitted)
        self.assertGreater(second.abs_beat_pos, first.abs_beat_pos)

    def test_idle_freewheel_clears_on_blackout(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        sm._led_idle_freewheel_since = 100.0

        sm._handle_event(BridgeEvent(kind=Ev.LED_BLACKOUT, deck=0, payload={}, source="test"))

        self.assertIsNone(sm.get_active_beat_anchor())

    def test_playing_automation_clears_idle_freewheel(self) -> None:
        sm = _make_sm(director=_AutomationLEDLookDirector(), adapter=_StubLEDAdapter())
        d = sm._deck[1]
        d.playing = True
        d.load_gen = 11
        d.meta.filepath = "/tracks/current.wav"
        sm._os.lighting_mode = "autoloop"
        sm._led_idle_freewheel_since = 100.0
        sm._led_rt_beat = (1, 64.5, 128.0, 1000.0, True)

        sm._dispatch_led_automation(active=1, d=d, sp_state=_groove_sp(0.0))
        anchor = sm.get_active_beat_anchor()

        self.assertIsNone(sm._led_idle_freewheel_since)
        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual(anchor.deck, 1)
        self.assertEqual(anchor.bpm, 128.0)

    def test_manual_pad_color_queues_until_next_realtime_automation_dispatch(self) -> None:
        sm, engine, runner, owner = _make_realtime_color_sm()

        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)
        initial_desired_count = len(runner.desired)
        self.assertEqual(len(runner.desired), 1)
        self.assertEqual(runner.desired[-1].params["color"], (1, 2, 3))
        self.assertEqual(runner.fire_count, 1)

        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_MANUAL_PAD,
                deck=0,
                payload={"name": "red"},
                source="test",
            )
        )

        self.assertEqual(engine.snapshot()["manual"], "red")
        self.assertEqual(len(runner.desired), initial_desired_count)
        self.assertEqual(runner.fire_count, 1)
        self.assertEqual(runner.desired[-1].params["color"], (1, 2, 3))

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_cross_sp())

        self.assertEqual(len(runner.desired), initial_desired_count + 1)
        self.assertEqual(runner.desired[-1].params["color"], (255, 0, 0))
        self.assertEqual(runner.desired[-1].effect_name, "groove_chase_blue")
        self.assertEqual(runner.fire_count, 2)
        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)

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

    def test_no_audible_idle_entry_dispatches_ambient_once_from_last_audible_deck(self) -> None:
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        sm._rerun_active_deck_resolver = lambda _reason: None
        sm._last_audible_deck = 2
        sm._deck[2].load_gen = 22
        sm._deck[2].meta.filepath = "/tracks/last.wav"
        sm._os.active_deck = 0
        sm._os.was_playing = True
        sm._os.lighting_mode = "autoloop"

        sm._push_tick()
        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "ambient")
        self.assertEqual(director.tick_calls[0].active_deck, 2)
        self.assertEqual(sm._led_last_event, "automation:idle_ambient:idle_no_audible")
        self.assertEqual(sm._led_last_idle_role_key, "2:22:idle_ambient:True")

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
                abs_beat=80.5,
                smart_buildup_active=True,
                current_phrase_label="up",
                current_phrase_start_beat=64.0,
                current_phrase_is_up=True,
                beats_into_phrase=16.5,
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

    def test_smart_phrasing_reset_reason_logs_only_on_change(self) -> None:
        def diag(reason: str, abs_beat: float | None) -> SmartPhrasingDiagnostic:
            return SmartPhrasingDiagnostic(
                event="smart_phrasing_reset",
                level="info",
                reason=reason,
                deck_id="1",
                track_id="/tracks/current.wav",
                abs_beat=abs_beat,
                previous_abs_beat=None,
            )

        class _FakeSmartPhrasingEngine:
            def __init__(self) -> None:
                self.results = [
                    SmartPhrasingResult(SmartPhrasingState(), (diag("no_beat", None),)),
                    SmartPhrasingResult(SmartPhrasingState(), (diag("no_beat", None),)),
                    SmartPhrasingResult(SmartPhrasingState(), (diag("track_change", 12.0),)),
                    SmartPhrasingResult(SmartPhrasingState(abs_beat=13.0), ()),
                ]

            def update(self, _snapshot):  # type: ignore[no-untyped-def]
                return self.results.pop(0)

        sm = _make_sm()
        sm._smart_phrasing_engine = _FakeSmartPhrasingEngine()
        d = sm._deck[1]
        d.playing = True
        d.meta.filepath = "/tracks/current.wav"

        with self.assertLogs("state_manager", level="INFO") as captured:
            sm._update_smart_phrasing_state(1, d, 10.0, 120.0)
            sm._update_smart_phrasing_state(1, d, 11.0, 120.0)
            sm._update_smart_phrasing_state(1, d, 12.0, 120.0)
            sm._update_smart_phrasing_state(1, d, 13.0, 120.0)

        reset_logs = [
            line
            for line in captured.output
            if "[SP] reset-reason-change" in line
        ]
        self.assertEqual(len(reset_logs), 3)
        self.assertIn("reason=no_beat prev=-", reset_logs[0])
        self.assertIn("reason=track_change prev=no_beat", reset_logs[1])
        self.assertIn("reason=- prev=track_change", reset_logs[2])

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

    def test_led_track_identity_measured_freezes_once_store_hit_does_not_write(self) -> None:
        key = "identity:fresh"
        store = IdentityStore()
        engine = _IdentityColorEngine()
        sm = _make_sm(led_identity_store=store, led_color_engine=engine)
        sm._led_identity_writer = Mock()
        sm._deck[1].load_gen = 12
        record = _identity_record(key, "GLACIER")
        event = BridgeEvent(
            kind=Ev.LED_TRACK_IDENTITY,
            deck=1,
            payload={"deck": 1, "load_gen": 12, "key": key, "record": record},
            source="test",
        )

        sm._handle_event(event)

        self.assertEqual(store.get(key)["base"], "measured")
        self.assertEqual(len(engine.identity_calls), 1)
        self.assertEqual(engine.identity_calls[-1][3]["base"], "measured")
        sm._led_identity_writer.submit.assert_called_once()

        sm._led_identity_writer.submit.reset_mock()
        sm._handle_event(event)

        self.assertEqual(len(engine.identity_calls), 2)
        sm._led_identity_writer.submit.assert_not_called()

    def test_led_track_identity_stale_load_gen_is_dropped(self) -> None:
        key = "identity:stale"
        store = IdentityStore()
        engine = _IdentityColorEngine()
        sm = _make_sm(led_identity_store=store, led_color_engine=engine)
        sm._led_identity_writer = Mock()
        sm._deck[1].load_gen = 8

        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_TRACK_IDENTITY,
                deck=1,
                payload={"deck": 1, "load_gen": 7, "key": key, "record": _identity_record(key)},
                source="test",
            )
        )

        self.assertIsNone(store.get(key))
        self.assertEqual(engine.identity_calls, [])
        sm._led_identity_writer.submit.assert_not_called()

    def test_led_identity_correct_early_then_measured_then_clear_keeps_measured_base(self) -> None:
        store = IdentityStore()
        engine = _IdentityColorEngine()
        sm = _make_sm(led_identity_store=store, led_color_engine=engine)
        sm._led_identity_writer = Mock()
        sm._os.active_deck = 1
        sm._deck[1].load_gen = 22
        sm._deck[1].meta.content_id = "cid-22"
        sm._deck[1].meta.filepath = "/tracks/cid-22.wav"
        key = led_identity_content_key("cid-22", "/tracks/cid-22.wav")

        sm._apply_led_zone_correction("VOLT")
        self.assertEqual(store.get(key)["base"], "provisional")
        self.assertEqual(store.get(key)["correction"], {"zone": "VOLT"})

        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_TRACK_IDENTITY,
                deck=1,
                payload={"deck": 1, "load_gen": 22, "key": key, "record": _identity_record(key, "GLACIER")},
                source="test",
            )
        )

        upgraded = store.get(key)
        self.assertEqual(upgraded["base"], "measured")
        self.assertEqual(upgraded["zone"], "GLACIER")
        self.assertEqual(upgraded["correction"], {"zone": "VOLT"})

        sm._clear_led_zone_correction()

        final = store.get(key)
        self.assertEqual(final["base"], "measured")
        self.assertEqual(final["zone"], "GLACIER")
        self.assertIsNone(final["correction"])
        self.assertEqual(engine.identity_calls[-1][3]["base"], "measured")

    def test_led_max_energy_consumes_only_when_role_mapping_mutates(self) -> None:
        sm = _make_sm()
        sm._led_v2_latch = True
        sm._led_max_energy_armed = True
        sp_state = SmartPhrasingState(
            abs_beat=64.0,
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
            current_phrase_start_beat=64.0,
            phrase_start_crossing=True,
            previous_phrase_label="up",
            beats_into_phrase=0.0,
        )

        self.assertEqual(sm._led_role_from_smart_phrasing(sp_state, mutate=False), "drop")
        self.assertTrue(sm._led_max_energy_armed)

        self.assertEqual(sm._led_role_from_smart_phrasing(sp_state, mutate=True), "drop")
        self.assertFalse(sm._led_max_energy_armed)

    def test_moments_blocked_reaches_engine_during_active_predark(self) -> None:
        engine = _IdentityColorEngine()
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter, led_color_engine=engine)
        _ready_led_active_deck(sm, 1)
        sm._deck[1].load_gen = 33
        sm._led_smart_drop_blackout_key = "1:33:smart_drop_blackout:pre_dark:96.0"

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_groove_sp(2.0))

        self.assertEqual(len(engine.begin_calls), 1)
        self.assertTrue(engine.begin_calls[0]["moments_blocked"])

    def test_read_runtime_anlz_data_uses_v4_cache_for_identity(self) -> None:
        data = TrackAnlzData(
            [4],
            waveform_context=WaveformContext(
                heights=(1, 2, 3, 4),
                ms_per_entry=50.0,
                beatgrid_times_ms=(0.0, 500.0, 1000.0, 1500.0),
            ),
        )
        cached_v4 = _spectral_v4_fixture()

        with (
            patch.object(state_manager_mod, "read_anlz_drops", return_value=data) as read_mock,
            patch.object(state_manager_mod.spectral_cache, "get_cached_v4", return_value=cached_v4) as cache_mock,
            patch.object(state_manager_mod, "extract_spectral_features_v4") as extract_mock,
        ):
            result = state_manager_mod._read_runtime_anlz_data(
                "/tmp/test.DAT",
                audio_filepath="/tmp/audio.wav",
                identity_enabled=True,
                identity_key="identity:cache",
                identity_config=_identity_v2_config(),
            )

        read_mock.assert_called_once_with("/tmp/test.DAT")
        cache_mock.assert_called_once_with("/tmp/audio.wav", [0.0, 500.0, 1000.0, 1500.0])
        extract_mock.assert_not_called()
        self.assertIsNotNone(result.led_identity)
        self.assertEqual(result.led_identity["base"], "measured")

    # ── AWR-125 W3b: perf("led.look") emit assertions ─────────────────────

    def test_accepted_automation_dispatch_emits_perf_led_look(self) -> None:
        records = _capture_perf(self, "perf.led.look")
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(
            sm,
            SmartPhrasingState(
                abs_beat=80.5,
                smart_buildup_active=True,
                current_phrase_label="up",
                current_phrase_start_beat=64.0,
                current_phrase_is_up=True,
                beats_into_phrase=16.5,
                next_smart_drop_beat=96.0,
                beats_to_next_drop=16.0,
            ),
        )

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.cat, "perf.led.look")
        self.assertEqual(rec.deck, 1)
        data = rec.data
        self.assertEqual(data["role"], "buildup")
        self.assertEqual(data["look"], "room_buildup")
        self.assertEqual(data["scene_ref"], "Scene-buildup")
        self.assertEqual(data["reason"], "role_entry:buildup")
        self.assertEqual(data["backend"], "cloud_diy")
        self.assertEqual(data["active_deck"], 1)
        self.assertEqual(data["abs_beat"], 80.5)
        self.assertEqual(data["bip"], 16.5)
        self.assertEqual(data["phrase_label"], "up")
        self.assertEqual(data["seq"], sm._led_phrase_seq)
        self.assertTrue(data["role_key"])
        self.assertNotIn("phase", data)

    def test_idle_ambient_accepted_emits_perf_led_look(self) -> None:
        records = _capture_perf(self, "perf.led.look")
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_paused_push_tick(sm)

        sm._push_tick()
        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].cat, "perf.led.look")
        self.assertEqual(records[0].data["role"], "ambient")
        self.assertEqual(records[0].data["look"], "room_ambient")
        self.assertNotIn("abs_beat", records[0].data)
        self.assertNotIn("bip", records[0].data)
        self.assertNotIn("phrase_label", records[0].data)
        self.assertNotIn("seq", records[0].data)

    def test_smart_drop_blackout_accepted_emits_perf_led_look_with_phase(self) -> None:
        records = _capture_perf(self, "perf.led.look")
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
        self.assertEqual(len(records), 1)
        data = records[0].data
        self.assertEqual(data["role"], "smart_drop_blackout")
        self.assertEqual(data["look"], "room_blackout")
        self.assertEqual(data["phase"], "pre_drop")
        # scene_ref "23259999" is digits-only → sanitizer parity with old lines
        self.assertEqual(data["scene_ref"], "<redacted>")
        self.assertNotIn("abs_beat", data)
        self.assertNotIn("bip", data)
        self.assertNotIn("phrase_label", data)
        self.assertNotIn("seq", data)

    def test_rejected_dispatch_emits_no_perf_led_look(self) -> None:
        records = _capture_perf(self, "perf.led.look")
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter(accept=False)
        sm = _make_sm(director=director, adapter=adapter)
        _prepare_playing_push_tick(sm, SmartPhrasingState())

        sm._push_tick()

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(len(records), 0)

    # ── AWR-125 W3d: perf("override") emit assertions ─────────────────────

    def test_manual_scene_event_emits_perf_override(self) -> None:
        records = _capture_perf(self, "perf.override")
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)

        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_SCENE,
                deck=0,
                payload={"look": "room_drop_white_burst", "target": "strip_light_mirror"},
                source="stream_deck",
            )
        )

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.cat, "perf.override")
        data = rec.data
        self.assertEqual(data["surface"], "led")
        self.assertEqual(data["action"], "scene")
        self.assertEqual(data["source"], "stream_deck")
        self.assertEqual(data["target"], "strip_light_mirror")
        self.assertNotIn("reason", data)

    def test_blackout_event_emits_perf_override_with_reason(self) -> None:
        records = _capture_perf(self, "perf.override")
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)

        sm._handle_event(
            BridgeEvent(
                kind=Ev.LED_BLACKOUT,
                deck=0,
                payload={"reason": "operator"},
                source="pad",
            )
        )

        self.assertEqual(len(records), 1)
        data = records[0].data
        self.assertEqual(data["action"], "blackout")
        self.assertEqual(data["source"], "pad")
        self.assertEqual(data["reason"], "operator")

    def test_each_led_override_kind_emits_exactly_one_record(self) -> None:
        records = _capture_perf(self, "perf.override")
        director = _StubLEDLookDirector(enabled=True)
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)

        for kind in (
            Ev.LED_SET_ENABLED,
            Ev.LED_SCENE,
            Ev.LED_BLACKOUT,
            Ev.LED_CLEAR_BLACKOUT,
            Ev.LED_CLEAR_SCENE_OVERRIDE,
        ):
            payload = {"look": "room_drop_a"} if kind == Ev.LED_SCENE else (
                {"enabled": True} if kind == Ev.LED_SET_ENABLED else {}
            )
            sm._handle_event(BridgeEvent(kind=kind, deck=0, payload=payload, source="test"))

        self.assertEqual(len(records), 5)
        actions = [r.data["action"] for r in records]
        self.assertEqual(
            actions,
            ["set_enabled", "scene", "blackout", "clear_blackout", "clear_scene_override"],
        )


def _solo_drop_sp() -> SmartPhrasingState:
    """A chorus phrase-start crossing off an 'up' predecessor — the anchor that
    resolves role='drop' ~0.6 s before the smart-drop marker (RC4 flash window)."""
    return SmartPhrasingState(
        abs_beat=64.0,
        current_phrase_label="chorus",
        current_phrase_is_chorus=True,
        current_phrase_start_beat=64.0,
        phrase_start_crossing=True,
        previous_phrase_label="up",
        beats_into_phrase=0.0,
    )


class LEDSoloPredarkHoldTests(unittest.TestCase):
    """RC4 (AWR-144): on a pending Laser Solo drop, the LED drop-look anchor must
    hold the current look instead of flashing a bright drop look before the
    marker's solo blackout owner is set. Lasers/solo length untouched (LED-only)."""

    def _armed_solo_sm(self, pending):
        director = _AutomationLEDLookDirector()
        adapter = _StubLEDAdapter()
        sm = _make_sm(director=director, adapter=adapter)
        _ready_led_active_deck(sm, 1)
        sm._deck[1].load_gen = 11
        sm._drop_presentation_last_pending = pending
        return sm, adapter

    def test_solo_pending_drop_look_is_suppressed_and_held(self) -> None:
        sm, adapter = self._armed_solo_sm((LASERS_ONLY, "solo_learned", 64.0))

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_solo_drop_sp())

        # No drop look reaches the device — the current look is held through the gap.
        self.assertEqual(adapter.trigger_calls, [])
        self.assertEqual(sm._led_automation_gate_reason, "solo_predark_hold")
        self.assertEqual(
            sm.led_status_provider()["automation_gate_reason"], "solo_predark_hold"
        )

    def test_non_solo_drop_look_dispatched_unchanged(self) -> None:
        sm, adapter = self._armed_solo_sm((LEDS_PLUS_LASERS, "both_finale", 64.0))

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_solo_drop_sp())

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "drop")

    def test_disabled_drop_presentation_is_a_noop(self) -> None:
        sm, adapter = self._armed_solo_sm((None, "", None))

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_solo_drop_sp())

        self.assertEqual(len(adapter.trigger_calls), 1)
        self.assertEqual(adapter.trigger_calls[0].role, "drop")

    def test_post_marker_blackout_owner_still_masks_everything(self) -> None:
        # After the marker, drop_presentation sets a blackout owner. That mask must
        # still own the darkness and pre-empt the RC4 hold (pre-existing behavior).
        sm, adapter = self._armed_solo_sm((LASERS_ONLY, "solo_learned", 64.0))
        sm._led_blackout_owners.add("drop_spotlight")

        sm._dispatch_led_automation(active=1, d=sm._deck[1], sp_state=_solo_drop_sp())

        self.assertEqual(adapter.trigger_calls, [])
        self.assertEqual(sm._led_automation_gate_reason, "emergency_blackout")


class LedDiyEligiblePredicateTests(unittest.TestCase):
    """AWR-152 T6: DIY color-tag filtering is stale under v2 (frozen v1 palette)."""

    def test_returns_none_when_v2_latch_truthy(self) -> None:
        engine = _IdentityColorEngine()
        sm = _make_sm(led_color_engine=engine)
        sm._led_v2_latch = True
        self.assertIsNone(sm._led_diy_eligible_predicate())

    def test_returns_engine_predicate_when_v2_latch_falsy(self) -> None:
        engine = _IdentityColorEngine()
        sm = _make_sm(led_color_engine=engine)
        sm._led_v2_latch = False
        self.assertEqual(sm._led_diy_eligible_predicate(), engine.diy_eligible)

    def test_v2_latched_automation_tick_passes_no_diy_filter(self) -> None:
        # A v2-latched automation tick must not filter cloud looks by color
        # tag: the predicate is None, so every banked look rotates evenly.
        sm, _engine, _runner, _owner = _make_realtime_color_sm()
        director = sm._led_look_director
        self.assertTrue(director.tick_calls)
        self.assertIsNone(director.tick_calls[-1].diy_eligible)


if __name__ == "__main__":
    unittest.main()
