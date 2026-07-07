"""LED dispatch policy mixed into StateManager.

This mixin runs entirely on the StateManager thread. It owns no threads,
locks, or blocking I/O. All ``_led_*`` fields live on the StateManager
instance because tests and ``led_status_provider`` depend on that shape.
The backend-routing adapter is ``led_dispatch_coordinator.py``; dispatch
policy must stay separate from that adapter.
"""
from __future__ import annotations

import logging
import os as _os
import re
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Optional

from . import bridge_log
from .config import LED_BACKSTEP_SEEK_BEATS
from .govee_frame_renderer import REALTIME_EFFECT_PARAM_KEYS, SLOT_EFFECTS, MAX_SLOTS
from .led_models import BeatAnchor, LEDContext
from .models import Ev
from .smart_phrasing import SmartPhrasingState

if TYPE_CHECKING:
    from .models import BridgeEvent, DeckState

# Same logger name as state_manager.py so moved log lines stay byte-identical.
log = logging.getLogger("state_manager")

LED_PHRASE_MONOTONIC_ENV   = "RBSS_LED_PHRASE_MONOTONIC"
LED_DEFAULT_DROP_IMPACT_BEATS = 8.0
LED_DEFAULT_GROOVE_CYCLE_BEATS = 32.0
LED_DEFAULT_POST_DROP_CYCLE_BEATS = 32.0
# After an active content change, allow the incoming look immediately only near
# the current phrase entry; otherwise hold the previous look until a crossing.
LED_HOLD_RELEASE_BEATS = 1.0
LED_IDLE_FREEWHEEL_BPM = 120.0
LED_HOLD_BACKSTOP_BEATS = 16.0
LED_HOLD_BACKSTOP_S = 8.0
_LED_DROP_IMPACT_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})
# Max drop impacts per drop lifecycle. The first fires off an Up/Low buildup;
# this allows one extra back-to-back Chorus->Chorus drop before settling into
# post_drop (i.e. up to two drop hits in a row, then post_drop).
LED_MAX_DROP_IMPACTS = 2
_LED_ADAPTER_STATUS_SAFE_KEYS = {
    "available",
    "running",
    "dry_run",
    "degraded",
    "degraded_reason",
    "queue_depth",
    "queue_max",
    "accepted_count",
    "rejected_count",
    "dropped_count",
    "queue_full_count",
    "deduped_count",
    "rate_limited_count",
    "send_count",
    "send_error_count",
    "malformed_response_count",
    "consecutive_send_failures",
    "circuit_open",
    "last_error",
    "last_command_at",
    "last_command_look",
}


class LEDDispatchPolicyMixin:
    def _init_led_dispatch_state(self, led_look_director, led_scene_adapter, led_color_engine) -> None:
        self._led_look_director = led_look_director
        self._led_scene_adapter = led_scene_adapter
        # M1b WI-1: optional LED color engine (None ⇒ no color injection).
        self._led_color_engine = led_color_engine
        self._led_manual_override = ""
        self._led_manual_target_override = ""
        self._led_emergency_blackout = False
        self._led_blackout_owners: set[str] = set()
        self._led_last_error = ""
        self._led_last_event = ""
        self._led_last_look = ""
        self._led_trigger_count = 0
        self._led_rejected_count = 0
        self._led_enabled_latch = False
        self._led_dry_run_latch = True
        self._led_automation_enabled_latch = False
        self._led_scripted_mode_automation_latch = False
        self._led_scripted_default_role = "breakdown"
        self._led_scripted_role_map: dict[str, str] = {}
        self._led_last_auto_role_key = ""
        # M1b WI-2: structured (section_id, cycle) published alongside the
        # string role_key so the color engine seeds on stable fields without
        # parsing the marker text.
        self._led_last_section_cycle: tuple[str, int] = ("", 0)
        self._led_automation_gate_reason = "not_configured"
        self._led_automation_trigger_count = 0
        self._led_automation_gated_count = 0
        self._led_smart_drop_blackout_key = ""
        self._led_first_drop_anchor_beat: float | None = None
        self._led_drop_impact_until_beat: float | None = None
        self._led_drop_impact_count = 0
        self._led_active_drop_look = ""
        self._led_max_energy_armed = False
        self._led_committed_drop_anchor_beat: float | None = None
        self._led_committed_drop_decision: Any | None = None
        self._led_drop_look_fired_anchor: float | None = None
        self._led_automation_offset_s = 0.0
        self._led_cloud_automation_offset_s = 0.0
        self._led_realtime_automation_offset_s = 0.0
        self._led_last_idle_role_key = ""
        # Armed on active deck switch or active-deck track load; released by LED phrase timing.
        self._led_hold_active: bool = False
        self._led_hold_started_mono: float = 0.0
        self._led_hold_started_beat: Optional[float] = None
        self._led_rt_permitted = False
        self._led_rt_beat: tuple[int, float, float, float, bool] | None = None
        self._led_idle_freewheel_since: Optional[float] = None
        self._led_color_engine_status: dict[str, Any] = {
            "available": bool(led_color_engine is not None),
            "enabled": bool(getattr(led_color_engine, "enabled", False)),
            "reason": "ok" if led_color_engine is not None else "not_configured",
        }
        # WI-1 monotonic beat clamp state
        self._led_beat_monotonic: Optional[float] = None
        self._led_beat_monotonic_key: Optional[tuple[int, int]] = None
        self._phrase_monotonic_enabled: bool = (
            _os.environ.get(LED_PHRASE_MONOTONIC_ENV, "1") != "0"
        )
        # WI-2 phrase latch state
        self._led_phrase_seq: int = 0
        self._led_phrase_committed_start: Optional[float] = None
        # WI-8 observability counters
        self._led_phrase_latch_reset_count: int = 0
        if self._led_look_director is not None:
            try:
                status_payload = self._led_look_director.status()
                self._led_enabled_latch = bool(status_payload.get("enabled", False))
                self._led_dry_run_latch = bool(status_payload.get("dry_run", True))
                self._led_automation_enabled_latch = bool(
                    status_payload.get("automation_enabled", False)
                )
                self._led_scripted_mode_automation_latch = bool(
                    status_payload.get("scripted_mode_automation", False)
                )
                sm_policy = status_payload.get("scripted_mode", {}) or {}
                if not isinstance(sm_policy, dict):
                    sm_policy = {}
                self._led_scripted_default_role = str(
                    sm_policy.get("default_role", "breakdown")
                )
                self._led_scripted_role_map = dict(sm_policy.get("role_map", {}))
                cloud_offset = float(
                    status_payload.get(
                        "automation_cloud_offset_s",
                        status_payload.get("automation_offset_s", 0.0),
                    )
                )
                realtime_offset = float(
                    status_payload.get("automation_realtime_offset_s", 0.0)
                )
                self._led_cloud_automation_offset_s = max(0.0, cloud_offset)
                self._led_realtime_automation_offset_s = max(0.0, realtime_offset)
                # Backward-compatible status alias; cloud keeps the legacy lead.
                self._led_automation_offset_s = self._led_cloud_automation_offset_s
                self._led_automation_gate_reason = (
                    "" if self._led_automation_enabled_latch else "automation_disabled"
                )
            except Exception:
                self._led_enabled_latch = False
                self._led_dry_run_latch = True
                self._led_automation_enabled_latch = False
                self._led_scripted_mode_automation_latch = False
                self._led_scripted_default_role = "breakdown"
                self._led_scripted_role_map = {}
                self._led_automation_gate_reason = "status_unavailable"

    def led_status_provider(self) -> dict[str, Any]:
        available = self._led_look_director is not None and self._led_scene_adapter is not None
        reason = "ok"
        if not available:
            reason = "not_configured"
        elif not self._led_enabled_latch:
            reason = "disabled"
        elif self._led_last_error:
            reason = "degraded"

        payload: dict[str, Any] = {
            "available": bool(available),
            "enabled": bool(self._led_enabled_latch),
            "reason": reason,
            "manual_override": self._led_manual_override,
            "manual_target_override": self._led_manual_target_override,
            "emergency_blackout": self._led_blackout_active(),
            "blackout_owners": tuple(sorted(self._led_blackout_owners)),
            "last_error": self._led_last_error,
            "last_event": self._led_last_event,
            "last_look": self._led_last_look,
            "trigger_count": int(self._led_trigger_count),
            "rejected_count": int(self._led_rejected_count),
            "dry_run": bool(self._led_dry_run_latch),
            "automation_enabled": bool(self._led_automation_enabled_latch),
            "automation_gate_reason": self._led_automation_gate_reason,
            "automation_last_role_key": self._led_last_auto_role_key,
            "automation_trigger_count": int(self._led_automation_trigger_count),
            "automation_gated_count": int(self._led_automation_gated_count),
            "automation_offset_s": float(self._led_automation_offset_s),
            "automation_cloud_offset_s": float(self._led_cloud_automation_offset_s),
            "automation_realtime_offset_s": float(
                self._led_realtime_automation_offset_s
            ),
            "smart_drop_blackout_active": bool(self._led_smart_drop_blackout_key),
            # WI-8 observability
            "phrase_latch_seq": int(self._led_phrase_seq),
            "phrase_latch_reset_count": int(self._led_phrase_latch_reset_count),
            "max_energy_armed": bool(getattr(self, "_led_max_energy_armed", False)),
            "identity_store": (
                "degraded"
                if bool(getattr(getattr(self, "_led_identity_store", None), "degraded", False))
                else "ok"
            ),
        }
        engine = getattr(self, "_led_color_engine", None)
        if engine is not None:
            try:
                snap = engine.snapshot()
            except AttributeError as exc:
                payload["engine_snapshot_error"] = type(exc).__name__
            else:
                if isinstance(snap, dict):
                    for key in ("engine", "zone", "corrected", "staged_zone", "manual"):
                        if key in snap:
                            payload[key] = snap[key]

        if self._led_look_director is not None:
            try:
                raw_director = self._led_look_director.status()
                if isinstance(raw_director, dict):
                    payload["director"] = {
                        "available": bool(raw_director.get("available", True)),
                        "enabled": bool(raw_director.get("enabled", False)),
                        "dry_run": bool(raw_director.get("dry_run", True)),
                        "automation_enabled": bool(raw_director.get("automation_enabled", False)),
                        "automation_offset_s": float(
                            raw_director.get("automation_offset_s", 0.0)
                        ),
                        "automation_cloud_offset_s": float(
                            raw_director.get("automation_cloud_offset_s", 0.0)
                        ),
                        "automation_realtime_offset_s": float(
                            raw_director.get("automation_realtime_offset_s", 0.0)
                        ),
                        "scripted_mode_automation": bool(
                            raw_director.get("scripted_mode_automation", False)
                        ),
                        "current_look": str(raw_director.get("current_look", "")),
                        "last_reason": str(raw_director.get("last_reason", "")),
                        "last_source": str(raw_director.get("last_source", "")),
                        "manual_override": str(raw_director.get("manual_override", "")),
                        "emergency_blackout": bool(raw_director.get("emergency_blackout", False)),
                    }
            except Exception as exc:
                payload["reason"] = "provider_error"
                payload["last_error"] = f"director_status_error:{type(exc).__name__}"

        if self._led_scene_adapter is not None:
            try:
                raw_adapter = self._led_scene_adapter.status()
                payload["adapter"] = self._sanitize_led_adapter_status(raw_adapter)
            except Exception as exc:
                payload["reason"] = "provider_error"
                payload["last_error"] = f"adapter_status_error:{type(exc).__name__}"

        return payload

    def _led_blackout_active(self) -> bool:
        return bool(self._led_blackout_owners or self._led_emergency_blackout)

    def color_engine_status_provider(self) -> dict[str, Any]:
        """Return the latest StateManager-published color engine status copy."""
        with self._snapshot_lock:
            return dict(self._led_color_engine_status)

    def get_active_beat_anchor(self) -> Optional[BeatAnchor]:
        """Return the LED realtime beat snapshot when automation is permitted."""
        if self._led_idle_freewheel_since is not None:
            now = time.monotonic()
            elapsed = now - self._led_idle_freewheel_since
            return BeatAnchor(
                deck=0,
                abs_beat_pos=elapsed * (LED_IDLE_FREEWHEEL_BPM / 60.0),
                bpm=LED_IDLE_FREEWHEEL_BPM,
                captured_monotonic=now,
                playing=True,
                permitted=True,
            )
        if not self._led_rt_permitted or self._led_rt_beat is None:
            return None
        deck, abs_beat_pos, bpm, captured_monotonic, playing = self._led_rt_beat
        if not playing or bpm <= 0.0:
            return None
        return BeatAnchor(
            deck=deck,
            abs_beat_pos=abs_beat_pos,
            bpm=bpm,
            captured_monotonic=captured_monotonic,
            playing=playing,
            permitted=True,
        )

    def _sanitize_led_adapter_status(self, raw_status: Any) -> dict[str, Any]:
        if not isinstance(raw_status, dict):
            return {}
        safe: dict[str, Any] = {}
        for key in _LED_ADAPTER_STATUS_SAFE_KEYS:
            if key not in raw_status:
                continue
            value = raw_status.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
        provider = raw_status.get("provider")
        if isinstance(provider, dict):
            provider_safe: dict[str, Any] = {}
            for key in ("api_key_present", "target_count", "scene_count"):
                value = provider.get(key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    provider_safe[key] = value
            if provider_safe:
                safe["provider"] = provider_safe
        realtime = raw_status.get("realtime")
        if isinstance(realtime, dict):
            realtime_safe: dict[str, Any] = {}
            for key in (
                "owner",
                "active",
                "provider_bound",
                "desired_effect",
                "active_effect",
                "frame_index",
                "idle_since",
                "last_error",
                "realtime_trigger_count",
                "tactical_blackout_count",
            ):
                value = realtime.get(key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    realtime_safe[key] = value
            transport = realtime.get("transport")
            if isinstance(transport, dict):
                transport_safe: dict[str, Any] = {}
                for key in (
                    "ip",
                    "port",
                    "segments",
                    "frames_sent",
                    "command_count",
                    "send_error_count",
                    "last_error",
                    "last_payload_bytes",
                ):
                    value = transport.get(key)
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        transport_safe[key] = value
                if transport_safe:
                    realtime_safe["transport"] = transport_safe
            if realtime_safe:
                safe["realtime"] = realtime_safe
        return safe

    def _sanitize_led_scene_ref(self, scene_ref: Any) -> str:
        text = str(scene_ref or "").strip()
        if not text:
            return ""
        if re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5,}", text):
            return "<redacted>"
        if len(text) > 80:
            return "<redacted>"
        if any(ch in text for ch in ("\n", "\r", "\t")):
            return "<redacted>"
        if not any(ch.isalpha() for ch in text):
            return "<redacted>"
        allowed_punct = {" ", "_", "-", ".", "/", ":"}
        if not all(ch.isalnum() or ch in allowed_punct for ch in text):
            return "<redacted>"
        return text

    def _set_led_automation_gate_reason(
        self,
        reason: str,
        *,
        active_deck: Optional[int] = None,
        role: str = "",
        role_key: str = "",
    ) -> None:
        previous = self._led_automation_gate_reason
        self._led_automation_gate_reason = reason
        if reason == previous:
            return
        log.info(
            "[RGB] gate-reason-change reason=%s prev=%s enabled=%s dry_run=%s automation_enabled=%s active_deck=%d role=%s role_key=%s",
            reason or "clear",
            previous or "clear",
            bool(self._led_enabled_latch),
            bool(self._led_dry_run_latch),
            bool(self._led_automation_enabled_latch),
            int(active_deck if active_deck is not None else self._os.active_deck),
            role or "-",
            role_key or "-",
        )

    def _handle_led_event(self, ev: BridgeEvent) -> None:
        override_action = ev.kind[4:] if ev.kind.startswith("led_") else ev.kind
        override_data: dict[str, Any] = {
            "surface": "led",
            "action": override_action,
            "source": ev.source,
        }
        if "target" in ev.payload:
            override_data["target"] = ev.payload.get("target")
        if "reason" in ev.payload:
            override_data["reason"] = ev.payload.get("reason")
        bridge_log.perf(
            "override",
            "led %s (from %s)",
            override_action,
            ev.source,
            data=override_data,
        )

        if ev.kind == Ev.LED_SET_ENABLED:
            self._led_enabled_latch = bool(ev.payload.get("enabled", False))
            self._dispatch_led_manual_command(reason="set_enabled")
            return

        if ev.kind == Ev.LED_SCENE:
            look = str(ev.payload.get("look", "")).strip()
            if not look:
                self._led_last_event = "manual_scene"
                self._led_last_error = "led_scene_missing_look"
                self._led_rejected_count += 1
                return
            if "target" in ev.payload:
                target = str(ev.payload.get("target", "")).strip()
                if target and not self._led_target_exists(target):
                    self._led_last_event = "manual_scene"
                    self._led_last_error = f"unknown_target:{target}"
                    self._led_rejected_count += 1
                    return
                self._led_manual_target_override = target
            else:
                self._led_manual_target_override = ""
            self._led_manual_override = look
            self._dispatch_led_manual_command(reason="manual_scene")
            return

        if ev.kind == Ev.LED_BLACKOUT:
            self._led_idle_freewheel_since = None
            if "target" in ev.payload:
                target = str(ev.payload.get("target", "")).strip()
                if target and not self._led_target_exists(target):
                    self._led_last_event = "blackout"
                    self._led_last_error = f"unknown_target:{target}"
                    self._led_rejected_count += 1
                    return
                self._led_manual_target_override = target
            self._led_blackout_owners.add(str(ev.payload.get("reason") or "legacy"))
            self._led_emergency_blackout = bool(self._led_blackout_owners)
            self._dispatch_led_manual_command(reason="blackout")
            return

        if ev.kind == Ev.LED_CLEAR_BLACKOUT:
            self._led_blackout_owners.discard(str(ev.payload.get("reason") or "legacy"))
            self._led_emergency_blackout = bool(self._led_blackout_owners)
            self._dispatch_led_manual_command(reason="clear_blackout")
            return

        if ev.kind == Ev.LED_CLEAR_SCENE_OVERRIDE:
            self._led_manual_override = ""
            self._led_manual_target_override = ""
            self._dispatch_led_manual_command(reason="clear_scene_override")
            return

    def _led_target_exists(self, target_name: str) -> bool:
        director = self._led_look_director
        if director is None:
            return False
        config = getattr(director, "_config", None)
        if config is None:
            return False
        targets = getattr(config, "targets", None)
        if not isinstance(targets, dict):
            return False
        return target_name in targets

    def _dispatch_led_manual_command(self, *, reason: str) -> None:
        self._led_idle_freewheel_since = None
        if self._led_color_engine is not None and reason in ("blackout", "manual_scene"):
            self._led_color_engine.reset_fade_memory()
        self._led_last_event = reason
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""

        if self._led_look_director is None or self._led_scene_adapter is None:
            self._led_last_error = "not_configured"
            return
        if not self._led_enabled_latch:
            self._led_last_error = ""
            return

        manual_look = self._led_manual_override or None
        try:
            set_manual_override = getattr(self._led_look_director, "set_manual_override", None)
            if callable(set_manual_override):
                accepted = set_manual_override(manual_look)
                if accepted is False and manual_look:
                    self._led_manual_override = ""
                    self._led_last_error = f"unknown_look:{manual_look}"
                    self._led_rejected_count += 1
                    return
            set_emergency_blackout = getattr(self._led_look_director, "set_emergency_blackout", None)
            if callable(set_emergency_blackout):
                set_emergency_blackout(self._led_blackout_active())
            decision = self._led_look_director.tick(
                LEDContext(
                    role="manual",
                    manual_look=manual_look,
                    emergency_blackout=self._led_blackout_active(),
                    target_override=self._led_manual_target_override,
                )
            )
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            return

        if decision is None:
            self._led_last_error = ""
            self._led_last_look = ""
            return

        self._led_send_decision(
            decision,
            look=str(getattr(decision, "look", "")),
            role="",
            role_key="",
            automation=False,
        )

    def _dispatch_led_smart_drop_blackout(
        self,
        *,
        active: int,
        d: DeckState,
        sp_state: SmartPhrasingState,
        phase: str,
    ) -> None:
        marker = ""
        if sp_state.active_drop_beat is not None:
            marker = f"{sp_state.active_drop_beat:.3f}"
        elif sp_state.next_smart_drop_beat is not None:
            marker = f"{sp_state.next_smart_drop_beat:.3f}"
        drop_anchor = self._led_drop_anchor_for_blackout(sp_state)
        if self._led_same_drop_anchor(drop_anchor, self._led_drop_look_fired_anchor):
            return
        blackout_key = f"{active}:{d.load_gen}:smart_drop_blackout:{phase}:{marker}"
        if blackout_key == self._led_smart_drop_blackout_key:
            return

        drop_preview = self._led_drop_decision_for_anchor(sp_state, commit=True)
        tactical_blackout = getattr(self._led_scene_adapter, "tactical_blackout", None)
        if (
            drop_preview is not None
            and str(getattr(drop_preview, "backend", "")) == "realtime_razer"
            and callable(tactical_blackout)
        ):
            self._led_last_auto_role_key = blackout_key
            self._led_last_event = f"automation:smart_drop_blackout:{phase}:realtime"
            outcome = self._led_send_decision(
                drop_preview,
                look="realtime_blackout",
                role="smart_drop_blackout",
                role_key=blackout_key,
                automation=True,
                active_deck=active,
                trigger_fn=tactical_blackout,
                phase=phase,
            )
            if outcome == "error":
                log.warning(
                    "[RGB] tactical-blackout-error phase=%s look=%s role_key=%s active_deck=%d err=%s",
                    phase,
                    str(getattr(drop_preview, "look", "")) or "-",
                    blackout_key,
                    active,
                    self._led_last_error.removeprefix("adapter_error:"),
                )
                return
            if outcome == "accepted":
                self._led_smart_drop_blackout_key = blackout_key
                log.info(
                    "[RGB] tactical-blackout-accepted phase=%s next_drop=%s role_key=%s trigger_count=%d active_deck=%d",
                    phase,
                    str(getattr(drop_preview, "look", "")) or "-",
                    blackout_key,
                    self._led_automation_trigger_count,
                    active,
                )
                return
            return

        context = LEDContext(
            role="pre_drop",
            manual_look=None,
            emergency_blackout=True,
            active_deck=active,
            playing=d.playing,
            lighting_mode=self._os.lighting_mode,
            scripted_id=d.scripted_id,
        )
        decision, ok = self._led_tick_director(
            context,
            role="smart_drop_blackout",
            role_key=blackout_key,
            automation=True,
            active_deck=active,
        )
        if not ok:
            log.warning(
                "[RGB] director-error role=%s phase=%s role_key=%s active_deck=%d err=%s",
                "smart_drop_blackout",
                phase,
                blackout_key,
                active,
                self._led_last_error.removeprefix("director_error:"),
            )
            self._led_last_auto_role_key = blackout_key
            return

        self._led_last_auto_role_key = blackout_key
        self._led_last_event = f"automation:smart_drop_blackout:{phase}"
        if decision is None:
            self._led_gate_no_look(
                reason="no_look:smart_drop_blackout",
                active_deck=active,
                role="smart_drop_blackout",
                role_key=blackout_key,
            )
            return

        look = str(getattr(decision, "look", ""))
        scene_ref = self._sanitize_led_scene_ref(getattr(decision, "scene_ref", ""))
        decision_reason = str(getattr(decision, "reason", ""))
        outcome = self._led_send_decision(
            decision,
            look=look,
            role="smart_drop_blackout",
            role_key=blackout_key,
            automation=True,
            active_deck=active,
            phase=phase,
        )
        if outcome == "error":
            log.warning(
                "[RGB] adapter-error role=%s phase=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d err=%s",
                "smart_drop_blackout",
                phase,
                look or "-",
                scene_ref or "-",
                decision_reason or "-",
                blackout_key,
                active,
                self._led_last_error.removeprefix("adapter_error:"),
            )
            return

        if outcome == "accepted":
            self._led_smart_drop_blackout_key = blackout_key
            return

        log.warning(
            "[RGB] adapter-rejected role=%s phase=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d",
            "smart_drop_blackout",
            phase,
            look or "-",
            scene_ref or "-",
            decision_reason or "-",
            blackout_key,
            active,
        )

    def _advance_palette_fade_and_publish(self, sp_state: SmartPhrasingState) -> None:
        """Advance the color engine's override-fade every playing tick, then
        mirror any engine-driven palette change onto the deck feedback file.

        Deliberately decoupled from _dispatch_led_automation: that method
        early-returns on a stable role-key, an LED hold, or a pre-drop blackout,
        so keeping fade advancement there froze operator override-fades
        mid-slide — they only committed when a section boundary happened to fire
        (2026-07-05). And the feedback file is otherwise republished only on
        operator pad events, so the pad stayed frozen on the last press even
        after the engine committed the fade. Both are cheap: advance_fade is a
        no-op when no fade is active, and maybe_publish only builds+writes a
        frame when the change-signature actually moves.
        """
        engine = self._led_color_engine
        if engine is None or not engine.enabled:
            return
        os_state = getattr(self, "_os", None)
        decks = getattr(self, "_deck", {})
        active = int(getattr(os_state, "active_deck", 0) or 0)
        d = decks.get(active) if active and hasattr(decks, "get") else None
        scripted_led_mode = bool(
            d is not None
            and d.scripted_id
            and getattr(os_state, "lighting_mode", "") == "scripted"
            and self._led_scripted_mode_automation_latch
        )
        set_stand_down = getattr(engine, "set_scripted_stand_down", None)
        if callable(set_stand_down):
            set_stand_down(scripted_led_mode)
        abs_beat = self._led_abs_beat(sp_state)
        if abs_beat is not None:
            try:
                engine.advance_fade(abs_beat)
            except Exception as exc:
                # Fade math must never crash the 200 Hz push loop.
                self._led_last_error = f"color_engine_error:{type(exc).__name__}"
        sync_laser_color = getattr(self, "_sync_laser_color_if_needed", None)
        if callable(sync_laser_color):
            sync_laser_color(sp_state)
        control = self._led_palette_control
        if control is None:
            return
        try:
            snap = engine.snapshot()
            sig = (
                snap.get("current_palette"),
                snap.get("fade_target"),
                snap.get("fading"),
                snap.get("lock"),
                snap.get("queued_palette"),
            )
            if sig != self._palette_feedback_sig:
                self._palette_feedback_sig = sig
                control.maybe_publish()
        except Exception as exc:
            # Deck-feedback mirroring must never crash the 200 Hz push loop.
            self._led_last_error = f"palette_feedback_error:{type(exc).__name__}"

    def _led_inject_engine_colors(
        self,
        decision: Any,
        *,
        role: str,
        section_id: str,
        cycle: int,
        role_key: str,
    ) -> Any:
        # M1b WI-5: inject the engine-resolved color into the finalized decision
        # (merge, never replace — preserves sync_mode/beat_division and any other
        # static params).  Exempt/baked looks and disabled engine inject nothing.
        # Any engine error leaves the decision unmodified (engine-off behavior).
        engine = self._led_color_engine
        if engine is not None and engine.enabled:
            try:
                scene_ref_for_multi = str(getattr(decision, "scene_ref", ""))
                slot_based = scene_ref_for_multi in SLOT_EFFECTS
                
                if slot_based:
                    computed = engine.resolve_slot_colors(
                        role=role,
                        section_id=section_id,
                        cycle=cycle,
                        look_name=decision.look,
                        color_source=getattr(decision, "color_source", "engine"),
                        slot_count=MAX_SLOTS,
                    )
                    if computed:
                        palette_name = engine.snapshot().get("current_palette", "")
                        slot_colors = computed.get("slot_colors", [])
                        slot_count = len(slot_colors)
                        if slot_count >= 6:
                            first_rgb = tuple(slot_colors[0])
                            last_grad = tuple(slot_colors[4])
                            slot5_white = (tuple(slot_colors[5]) == (255, 255, 255))
                            log_msg = f"first={first_rgb} last_grad={last_grad} slot5_white={slot5_white}"
                        else:
                            log_msg = f"slot_colors={slot_count}"
                        
                        log.debug(
                            "[RGB] color-inject look=%s palette=%s %s role=%s role_key=%s",
                            decision.look,
                            palette_name,
                            log_msg,
                            role,
                            role_key,
                        )
                        decision = replace(
                            decision,
                            params={**decision.params, **computed},
                        )
                else:
                    multi = "color_a" in REALTIME_EFFECT_PARAM_KEYS.get(
                        scene_ref_for_multi, frozenset()
                    )
                    computed = engine.resolve_color(
                        role=role,
                        section_id=section_id,
                        cycle=cycle,
                        look_name=decision.look,
                        color_source=getattr(decision, "color_source", "engine"),
                        multi=multi,
                    )
                    if computed:
                        palette_name = engine.snapshot().get("current_palette", "")
                        log.debug(
                            "[RGB] color-inject look=%s palette=%s color=%s role=%s role_key=%s",
                            decision.look,
                            palette_name,
                            computed.get("color"),
                            role,
                            role_key,
                        )
                        decision = replace(
                            decision,
                            params={**decision.params, **computed},
                        )
            except Exception as exc:
                self._led_last_error = f"color_engine_error:{type(exc).__name__}"
        return decision

    def _dispatch_led_automation(
        self,
        *,
        active: int,
        d: DeckState,
        sp_state: SmartPhrasingState,
        position_stale: bool = False,
    ) -> None:
        if self._led_look_director is None or self._led_scene_adapter is None:
            self._gate_led_automation("not_configured", active_deck=active)
            return
        if not self._led_enabled_latch:
            self._gate_led_automation("disabled", active_deck=active)
            return
        if not self._led_automation_enabled_latch:
            self._gate_led_automation("automation_disabled", active_deck=active)
            return
        if self._led_blackout_active():
            self._gate_led_automation("emergency_blackout", active_deck=active)
            return
        if not d.playing or not d.meta.filepath:
            self._gate_led_automation("not_ready", active_deck=active)
            return
        if position_stale:
            self._gate_led_automation("position_stale", active_deck=active)
            return

        if self._led_manual_override:
            self._gate_led_automation("manual_override", active_deck=active, rt_permitted=True)
            return
        scripted_led_mode = bool(
            d.scripted_id
            and self._os.lighting_mode == "scripted"
            and self._led_scripted_mode_automation_latch
        )
        if d.scripted_id and not self._led_scripted_mode_automation_latch:
            self._gate_led_automation("scripted_mode", active_deck=active, rt_permitted=True)
            return

        if self._os.lighting_mode != "autoloop" and not scripted_led_mode:
            self._gate_led_automation("not_autoloop", active_deck=active)
            return
        # NOTE: LED automation is intentionally NOT gated on the SoundSwitch
        # autoloop *arm* completion. Govee looks are a separate path from SS
        # scenes, so a freshly-playing track lights immediately instead of
        # waiting for the SS arm (which only completes on a phrase boundary).
        # The laser director keeps its own autoloop_ready coupling separately.

        self._led_rt_permitted = True
        self._led_idle_freewheel_since = None
        self._led_last_idle_role_key = ""
        if self._led_hold_active:
            # Keep rendering the previous look; do not dispatch a new one until
            # the incoming track is at/crossing a phrase entry, with a bounded
            # backstop for phrase-less stretches.
            now = time.monotonic()
            bip = sp_state.beats_into_phrase
            if self._led_hold_started_mono == 0.0:
                self._led_hold_started_mono = now
                self._led_hold_started_beat = self._led_abs_beat(sp_state)
                log.info(
                    "[RGB] hold-engaged deck=%d bip=%s crossing=%s abs_beat=%s",
                    active,
                    bip if bip is not None else "-",
                    sp_state.phrase_start_crossing,
                    self._led_hold_started_beat if self._led_hold_started_beat is not None else "-",
                )
            at_phrase_entry = bip is not None and bip <= LED_HOLD_RELEASE_BEATS
            current_beat = self._led_abs_beat(sp_state)
            beat_backstop = (
                current_beat is not None
                and self._led_hold_started_beat is not None
                and current_beat - self._led_hold_started_beat >= LED_HOLD_BACKSTOP_BEATS
            )
            time_backstop = now - self._led_hold_started_mono >= LED_HOLD_BACKSTOP_S
            release_reason = ""
            if at_phrase_entry:
                release_reason = "phrase_entry"
            elif sp_state.phrase_start_crossing:
                release_reason = "crossing"
            elif beat_backstop:
                release_reason = "beat_backstop"
            elif time_backstop:
                release_reason = "time_backstop"

            if release_reason:
                held_s = now - self._led_hold_started_mono
                self._led_hold_active = False
                self._led_hold_started_mono = 0.0
                self._led_hold_started_beat = None
                log.info(
                    "[RGB] hold-released deck=%d reason=%s held_s=%.1f",
                    active,
                    release_reason,
                    held_s,
                )
            else:
                return
        if sp_state.smart_drop_crossing:
            # Pre-drop blackout may already be active; at the crossing beat the
            # state-aware LED role resolver decides whether this is an impact or
            # an immediate post-drop continuation.
            self._led_smart_drop_blackout_key = ""
        elif self._led_should_smart_drop_blackout(sp_state):
            self._dispatch_led_smart_drop_blackout(
                active=active,
                d=d,
                sp_state=sp_state,
                phase="pre_drop",
            )
            return

        # WI-2: advance the phrase latch before building role_key so the seq is
        # current when groove/ambient/post_drop embed it into their marker.
        if self._phrase_monotonic_enabled:
            self._advance_led_phrase_latch(sp_state)

        role = self._led_role_from_smart_phrasing(sp_state, mutate=True)
        original_role = role
        role = self._led_effective_role_for_dispatch(role, scripted=scripted_led_mode)
        role_key = self._led_automation_role_key(active, d, sp_state, original_role)
        if role_key == self._led_last_auto_role_key:
            return

        # M1b WI-5: structured section/cycle published by the role_key builder.
        section_id, cycle = self._led_last_section_cycle

        # M1b WI-1/WI-5: advance the color engine's journey state.  Guarded so a
        # missing/disabled engine is a complete no-op, and any engine exception
        # is swallowed (behave as engine-off for this tick — never crash dispatch).
        engine = self._led_color_engine
        if engine is not None and engine.enabled:
            try:
                # NOTE: advance_fade is NOT called here. Fade advancement moved
                # to StateManager._advance_palette_fade_and_publish (per playing
                # tick) because this method early-returns on a stable role-key,
                # LED hold, or pre-drop blackout — any of which would otherwise
                # freeze an operator's override-fade mid-slide (2026-07-05).
                moments_blocked = bool(
                    self._led_blackout_active()
                    or self._led_manual_override
                    or self._led_smart_drop_blackout_key
                )
                engine.begin_dispatch(
                    active_deck=active,
                    load_gen=d.load_gen,
                    content_id=str(d.meta.content_id or ""),
                    filepath=str(d.meta.filepath or ""),
                    role=role,
                    section_id=section_id,
                    cycle=cycle,
                    moments_blocked=moments_blocked,
                    scripted=scripted_led_mode,
                )
            except Exception as exc:
                self._led_last_error = f"color_engine_error:{type(exc).__name__}"

        context = LEDContext(
            role=role,
            manual_look=None,
            emergency_blackout=False,
            active_deck=active,
            playing=d.playing,
            lighting_mode=self._os.lighting_mode,
            scripted_id=d.scripted_id,
            diy_eligible=self._led_diy_eligible_predicate(),
            look_preference=self._led_look_preference_predicate(),
        )
        decision = None
        if role == "drop":
            decision = self._consume_led_committed_drop_decision(sp_state)
        if decision is None:
            decision, ok = self._led_tick_director(
                context,
                role=role,
                role_key=role_key,
                automation=True,
                active_deck=active,
            )
            if not ok:
                log.warning(
                    "[RGB] director-error role=%s role_key=%s active_deck=%d err=%s",
                    role,
                    role_key,
                    active,
                    self._led_last_error.removeprefix("director_error:"),
                )
                self._led_last_auto_role_key = role_key
                return

        self._led_last_auto_role_key = role_key
        self._led_last_event = f"automation:{role}"
        if decision is None:
            no_look_reason = f"no_look:{role}"
            self._led_gate_no_look(
                reason=no_look_reason,
                active_deck=active,
                role=role,
                role_key=role_key,
            )
            log.info(
                "[RGB] no-look role=%s role_key=%s reason=%s active_deck=%d",
                role,
                role_key,
                no_look_reason,
                active,
            )
            return

        decision = self._led_inject_engine_colors(
            decision,
            role=role,
            section_id=section_id,
            cycle=cycle,
            role_key=role_key,
        )

        look = str(getattr(decision, "look", ""))
        scene_ref = self._sanitize_led_scene_ref(getattr(decision, "scene_ref", ""))
        decision_reason = str(getattr(decision, "reason", ""))
        outcome = self._led_send_decision(
            decision,
            look=look,
            role=role,
            role_key=role_key,
            automation=True,
            active_deck=active,
            sp_state=sp_state,
        )
        if outcome == "error":
            log.warning(
                "[RGB] adapter-error role=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d err=%s",
                role,
                look,
                scene_ref or "-",
                decision_reason or "-",
                role_key,
                active,
                self._led_last_error.removeprefix("adapter_error:"),
            )
            return

        if outcome == "accepted":
            self._led_smart_drop_blackout_key = ""
            if role == "drop":
                self._led_note_drop_decision_accepted(decision, sp_state)
            return

        log.warning(
            "[RGB] adapter-rejected role=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d",
            role,
            look or "-",
            scene_ref or "-",
            decision_reason or "-",
            role_key,
            active,
        )

    def _dispatch_led_idle_ambient(
        self,
        *,
        active: int,
        d: DeckState,
        reason: str,
    ) -> None:
        self._led_rt_permitted = False
        self._led_idle_freewheel_since = None
        self._led_smart_drop_blackout_key = ""

        role_key = f"{active}:{d.load_gen}:idle_ambient:{bool(d.meta.filepath)}"
        if self._led_look_director is None or self._led_scene_adapter is None:
            self._gate_led_automation("not_configured", active_deck=active, role="ambient")
            return
        if not self._led_enabled_latch:
            self._gate_led_automation("disabled", active_deck=active, role="ambient")
            return
        if not self._led_automation_enabled_latch:
            self._gate_led_automation("automation_disabled", active_deck=active, role="ambient")
            return
        if self._led_blackout_active():
            self._gate_led_automation("emergency_blackout", active_deck=active, role="ambient")
            return
        if self._led_manual_override:
            self._gate_led_automation("manual_override", active_deck=active, role="ambient")
            return
        if role_key == self._led_last_idle_role_key:
            return

        if self._led_color_engine is not None:
            self._led_color_engine.reset_fade_memory()

        context = LEDContext(
            role="ambient",
            manual_look=None,
            emergency_blackout=False,
            active_deck=active,
            playing=False,
            lighting_mode="idle",
            scripted_id=d.scripted_id,
        )
        decision, ok = self._led_tick_director(
            context,
            role="ambient",
            role_key=role_key,
            automation=True,
            active_deck=active,
        )
        if not ok:
            self._led_last_auto_role_key = role_key
            self._led_last_idle_role_key = role_key
            return

        self._led_last_auto_role_key = role_key
        self._led_last_idle_role_key = role_key
        self._led_last_event = f"automation:idle_ambient:{reason}"
        if decision is None:
            self._led_gate_no_look(
                reason="no_look:ambient",
                active_deck=active,
                role="ambient",
                role_key=role_key,
            )
            return

        look = str(getattr(decision, "look", ""))
        outcome = self._led_send_decision(
            decision,
            look=look,
            role="ambient",
            role_key=role_key,
            automation=True,
            active_deck=active,
        )
        if outcome == "error":
            log.warning(
                "[RGB] adapter-error role=ambient look=%s reason=%s role_key=%s active_deck=%d err=%s",
                look or "-",
                reason,
                role_key,
                active,
                self._led_last_error.removeprefix("adapter_error:"),
            )
            return

        if outcome == "accepted":
            if getattr(decision, "backend", "") == "realtime_razer":
                self._led_idle_freewheel_since = time.monotonic()
                log.info("[RGB] idle-freewheel-start look=%s", look)
            else:
                self._led_idle_freewheel_since = None
            return


    def _gate_led_automation(
        self,
        reason: str,
        *,
        active_deck: Optional[int] = None,
        role: str = "",
        role_key: str = "",
        rt_permitted: bool = False,
    ) -> None:
        self._led_rt_permitted = rt_permitted
        self._led_idle_freewheel_since = None
        if reason != self._led_automation_gate_reason:
            self._led_automation_gated_count += 1
            if self._led_color_engine is not None and reason in ("emergency_blackout", "manual_override"):
                self._led_color_engine.reset_fade_memory()
        self._set_led_automation_gate_reason(
            reason,
            active_deck=active_deck,
            role=role,
            role_key=role_key,
        )
        self._led_last_auto_role_key = ""

    def _led_tick_director(
        self,
        context: LEDContext,
        *,
        role: str,
        role_key: str,
        automation: bool,
        active_deck: Optional[int] = None,
    ) -> tuple[Any, bool]:
        """Single director.tick error ritual. Returns (decision, ok).

        On director exception: records director_error bookkeeping (and, for
        automation paths, the gated count + gate reason) and returns (None, False).
        Per-path post-error effects (role-key latches, warning logs) stay at the
        call sites because they intentionally differ per path.
        """
        try:
            return self._led_look_director.tick(context), True
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            if automation:
                self._led_automation_gated_count += 1
                self._set_led_automation_gate_reason(
                    "director_error",
                    active_deck=active_deck,
                    role=role,
                    role_key=role_key,
                )
            return None, False

    def _led_gate_no_look(
        self,
        *,
        reason: str,
        role: str,
        role_key: str,
        active_deck: Optional[int] = None,
    ) -> None:
        """Single decision-is-None gating ritual for automation-family paths."""
        self._led_automation_gated_count += 1
        self._set_led_automation_gate_reason(
            reason,
            active_deck=active_deck,
            role=role,
            role_key=role_key,
        )

    def _led_send_decision(
        self,
        decision: Any,
        *,
        look: str,
        role: str,
        role_key: str,
        automation: bool,
        active_deck: Optional[int] = None,
        trigger_fn: Any = None,
        phase: str = "",
        sp_state: SmartPhrasingState | None = None,
    ) -> str:
        """Single adapter trigger/accept/reject bookkeeping ritual.

        Returns "accepted", "rejected", or "error". Counters, _led_last_error,
        _led_last_look, and the automation gate reason mutate ONLY here for
        trigger outcomes. The accepted path emits the one perf("led.look")
        record (AWR-125); *phase* is a log-only field for pre-drop blackout
        callers. Per-path side effects (blackout keys, drop-lifecycle notes,
        warning logs) stay at the call sites because they intentionally differ
        per path; none of them log between these field writes, so the
        observable stream is unchanged.
        """
        if trigger_fn is None:
            trigger_fn = self._led_scene_adapter.trigger
        try:
            accepted = bool(trigger_fn(decision))
        except Exception as exc:
            self._led_last_error = f"adapter_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            if automation:
                self._led_automation_gated_count += 1
                self._set_led_automation_gate_reason(
                    "adapter_error",
                    active_deck=active_deck,
                    role=role,
                    role_key=role_key,
                )
            return "error"

        if accepted:
            self._led_trigger_count += 1
            if automation:
                self._led_automation_trigger_count += 1
            self._led_last_error = ""
            self._led_last_look = look
            if automation:
                self._set_led_automation_gate_reason(
                    "",
                    active_deck=active_deck,
                    role=role,
                    role_key=role_key,
                )
            scene_ref = self._sanitize_led_scene_ref(getattr(decision, "scene_ref", ""))
            reason = str(getattr(decision, "reason", ""))
            data: dict[str, Any] = {
                "role": role,
                "look": look,
                "scene_ref": scene_ref,
                "reason": reason,
                "role_key": role_key,
                "backend": str(getattr(decision, "backend", "")),
            }
            if phase:
                data["phase"] = phase
            engine = getattr(self, "_led_color_engine", None)
            if engine is not None and engine.enabled:
                try:
                    data["palette"] = str(engine.snapshot().get("current_palette", ""))
                except Exception:
                    pass
            if active_deck is not None:
                data["active_deck"] = active_deck
            if sp_state is not None:
                abs_beat = self._led_abs_beat(sp_state)
                if abs_beat is not None:
                    data["abs_beat"] = abs_beat
                if sp_state.beats_into_phrase is not None:
                    data["bip"] = sp_state.beats_into_phrase
                data["phrase_label"] = sp_state.current_phrase_label
                data["seq"] = self._led_phrase_seq
            bridge_log.perf(
                "led.look",
                "look %s role=%s (%s)",
                look or "-",
                role or "-",
                reason or "-",
                deck=active_deck,
                data=data,
            )
            return "accepted"

        self._led_rejected_count += 1
        if automation:
            self._led_automation_gated_count += 1
        self._led_last_error = "adapter_rejected"
        if automation:
            self._set_led_automation_gate_reason(
                "adapter_rejected",
                active_deck=active_deck,
                role=role,
                role_key=role_key,
            )
        return "rejected"

    def _led_should_smart_drop_blackout(self, sp_state: SmartPhrasingState) -> bool:
        """True when Govee should be in pre-drop blackout for Smart Drop."""
        return bool(
            sp_state.transition_mask_arm_latched
            or sp_state.transition_mask_should_arm
            or sp_state.transition_window_active
        )

    def _preview_led_drop_decision(
        self,
        sp_state: SmartPhrasingState | None = None,
    ) -> Any:
        if sp_state is not None:
            return self._led_drop_decision_for_anchor(sp_state, commit=False)
        return self._preview_led_decision_for_role("drop")

    def _preview_led_decision_for_role(self, role: str) -> Any:
        preview_role = getattr(self._led_look_director, "preview_role", None)
        if not callable(preview_role):
            return None
        try:
            return preview_role(role)
        except Exception:
            return None

    def _led_drop_anchor_for_blackout(
        self,
        sp_state: SmartPhrasingState,
    ) -> float | None:
        if sp_state.active_drop_beat is not None:
            return float(sp_state.active_drop_beat)
        if sp_state.next_smart_drop_beat is not None:
            return float(sp_state.next_smart_drop_beat)
        return self._led_drop_marker_anchor(sp_state)

    def _led_same_drop_anchor(
        self,
        left: float | None,
        right: float | None,
    ) -> bool:
        if left is None or right is None:
            return False
        return float(left) == float(right)

    def _led_drop_decision_for_anchor(
        self,
        sp_state: SmartPhrasingState,
        *,
        commit: bool,
    ) -> Any:
        anchor = self._led_drop_anchor_for_blackout(sp_state)
        if (
            self._led_same_drop_anchor(anchor, self._led_committed_drop_anchor_beat)
            and self._led_committed_drop_decision is not None
        ):
            return self._led_committed_drop_decision
        if not commit or anchor is None:
            return self._preview_led_decision_for_role("drop")

        commit_role = getattr(self._led_look_director, "commit_role", None)
        decision = None
        if callable(commit_role):
            try:
                decision = commit_role(
                    "drop",
                    diy_eligible=self._led_diy_eligible_predicate(),
                    look_preference=self._led_look_preference_predicate(),
                )
            except Exception:
                decision = None
        if decision is None:
            decision = self._preview_led_decision_for_role("drop")
        if decision is not None:
            self._led_committed_drop_anchor_beat = float(anchor)
            self._led_committed_drop_decision = decision
        return decision

    def _led_diy_eligible_predicate(self) -> Any:
        engine = self._led_color_engine
        return engine.diy_eligible if (engine is not None and engine.enabled) else None

    def _led_look_preference_predicate(self) -> Any:
        if not bool(getattr(self, "_led_v2_latch", False)):
            return None
        engine = self._led_color_engine
        director = self._led_look_director
        if engine is None or director is None:
            return None
        active_dressing = getattr(engine, "_v2_active_dressing", None)
        cfg = getattr(engine, "_v2_cfg", None)
        if not callable(active_dressing) or cfg is None:
            return None
        dressing = active_dressing()
        if dressing is None:
            return None
        looks = getattr(getattr(director, "_config", None), "looks", {})
        threshold = float(getattr(cfg, "budget_wide_threshold", 0.5))

        def _passes(name: str) -> bool:
            look = looks.get(name)
            if look is None:
                return True
            motion_style = str(getattr(look, "motion_style", ""))
            travel = str(getattr(look, "travel", ""))
            if motion_style and motion_style != dressing.style:
                return False
            if travel == "wide":
                return dressing.budget >= threshold
            if travel == "calm":
                return dressing.budget < threshold
            return True

        return _passes

    def _consume_led_committed_drop_decision(
        self,
        sp_state: SmartPhrasingState,
    ) -> Any:
        anchor = self._led_drop_anchor_for_blackout(sp_state)
        if not self._led_same_drop_anchor(anchor, self._led_committed_drop_anchor_beat):
            return None
        decision = self._led_committed_drop_decision
        self._led_committed_drop_anchor_beat = None
        self._led_committed_drop_decision = None
        return decision

    def _led_effective_role_for_dispatch(
        self,
        role: str,
        *,
        scripted: bool = False,
    ) -> str:
        if not scripted:
            return role
        return self._led_scripted_role_map.get(role, self._led_scripted_default_role)

    def _led_role_has_mapped_look(self, role: str) -> bool:
        has_role_look = getattr(self._led_look_director, "has_role_look", None)
        if callable(has_role_look):
            try:
                return bool(has_role_look(role))
            except Exception:
                return False
        return self._preview_led_decision_for_role(role) is not None

    def _led_role_from_smart_phrasing(
        self,
        sp_state: SmartPhrasingState,
        *,
        mutate: bool = False,
    ) -> str:
        if mutate and self._led_drop_lifecycle_should_clear(sp_state):
            self._clear_led_drop_lifecycle()

        drop_anchor = self._led_drop_marker_anchor(sp_state)
        if drop_anchor is not None:
            if self._led_drop_impact_allowed(sp_state):
                if mutate:
                    self._led_arm_drop_lifecycle(drop_anchor)
                return "drop"
            if mutate and self._led_first_drop_anchor_beat is None:
                self._led_first_drop_anchor_beat = drop_anchor
            return "post_drop"

        if sp_state.smart_breakdown_active or sp_state.breakdown_start_crossing:
            return "breakdown"
        if sp_state.transition_window_active:
            return "pre_drop"
        if self._led_buildup_active(sp_state):
            return "buildup"

        if sp_state.current_phrase_is_chorus or sp_state.smart_post_drop_active:
            abs_beat = self._led_abs_beat(sp_state)
            if (
                abs_beat is not None
                and self._led_drop_impact_until_beat is not None
                and abs_beat < self._led_drop_impact_until_beat
            ):
                return "drop"
            return "post_drop"
        if sp_state.current_phrase_is_low:
            return "breakdown"
        return "groove"

    def _led_buildup_active(self, sp_state: SmartPhrasingState) -> bool:
        """Match laser_director: buildup only in up phrase within lookahead of next drop."""
        beats_to_next_drop = sp_state.beats_to_next_drop
        if beats_to_next_drop is None or beats_to_next_drop <= 0:
            return False
        if beats_to_next_drop > self._sp_phrase_lookahead:
            return False
        return bool(
            sp_state.current_phrase_is_up
            and not sp_state.current_phrase_is_chorus
        )

    def _led_drop_marker_anchor(self, sp_state: SmartPhrasingState) -> float | None:
        if sp_state.current_phrase_is_chorus and sp_state.phrase_start_crossing:
            if sp_state.current_phrase_start_beat is not None:
                return float(sp_state.current_phrase_start_beat)
        if sp_state.smart_drop_crossing:
            if sp_state.active_drop_beat is not None:
                return float(sp_state.active_drop_beat)
            return self._led_abs_beat(sp_state)
        return None

    def _led_drop_impact_allowed(self, sp_state: SmartPhrasingState) -> bool:
        previous = str(sp_state.previous_phrase_label or "other")
        if previous in _LED_DROP_IMPACT_PREDECESSORS:
            return True
        if sp_state.smart_drop_crossing:
            return True
        return False

    def _led_drop_lifecycle_should_clear(self, sp_state: SmartPhrasingState) -> bool:
        if sp_state.smart_drop_crossing:
            return False
        if sp_state.current_phrase_is_chorus or sp_state.smart_post_drop_active:
            return False
        return self._led_first_drop_anchor_beat is not None

    def _led_arm_drop_lifecycle(self, anchor_beat: float) -> None:
        if getattr(self, "_led_max_energy_armed", False):
            self._led_max_energy_armed = False
            log.info("[LED] max_energy consumed (render unchanged until F2)")
        if self._led_first_drop_anchor_beat is None:
            self._led_first_drop_anchor_beat = float(anchor_beat)
        self._led_drop_impact_until_beat = (
            float(anchor_beat) + LED_DEFAULT_DROP_IMPACT_BEATS
        )
        self._led_drop_impact_count += 1
        self._led_active_drop_look = ""

    def _led_note_drop_decision_accepted(
        self,
        decision: Any,
        sp_state: SmartPhrasingState,
    ) -> None:
        look = str(getattr(decision, "look", "") or "")
        anchor = self._led_drop_marker_anchor(sp_state)
        if anchor is None:
            anchor = self._led_first_drop_anchor_beat
        if anchor is None:
            anchor = self._led_abs_beat(sp_state)
        if anchor is None:
            return
        duration = LED_DEFAULT_DROP_IMPACT_BEATS
        duration_fn = getattr(self._led_look_director, "drop_duration_beats", None)
        if callable(duration_fn):
            try:
                duration = float(duration_fn(look))
            except Exception:
                duration = LED_DEFAULT_DROP_IMPACT_BEATS
        duration = max(0.001, duration)
        if self._led_first_drop_anchor_beat is None:
            self._led_first_drop_anchor_beat = float(anchor)
        self._led_drop_impact_until_beat = float(anchor) + duration
        self._led_active_drop_look = look
        self._led_drop_look_fired_anchor = float(anchor)

    def _clear_led_drop_lifecycle(self) -> None:
        self._led_first_drop_anchor_beat = None
        self._led_drop_impact_until_beat = None
        self._led_drop_impact_count = 0
        self._led_active_drop_look = ""
        self._led_max_energy_armed = False
        self._led_committed_drop_anchor_beat = None
        self._led_committed_drop_decision = None
        self._led_drop_look_fired_anchor = None
        clear_queued = getattr(
            self._led_look_director, "clear_queued_post_drop", None
        )
        if callable(clear_queued):
            try:
                clear_queued()
            except Exception:
                pass

    def _led_abs_beat(self, sp_state: SmartPhrasingState) -> float | None:
        if sp_state.abs_beat is not None:
            return float(sp_state.abs_beat)
        if (
            sp_state.current_phrase_start_beat is not None
            and sp_state.beats_into_phrase is not None
        ):
            return float(sp_state.current_phrase_start_beat) + float(sp_state.beats_into_phrase)
        if sp_state.active_drop_beat is not None:
            return float(sp_state.active_drop_beat)
        return None

    def _led_post_drop_cycle_beats(self) -> float:
        cycle_fn = getattr(self._led_look_director, "post_drop_cycle_beats", None)
        if callable(cycle_fn):
            try:
                return max(0.001, float(cycle_fn()))
            except Exception:
                pass
        return LED_DEFAULT_POST_DROP_CYCLE_BEATS

    # ── WI-1/2 phrase latch helpers ───────────────────────────────────────────

    def _reset_led_phrase_latch(self, reason: str) -> None:
        """Clear the phrase-start latch on a genuine backward seek.

        Called by the WI-1 monotonic clamp when a real seek (delta >=
        LED_BACKSTEP_SEEK_BEATS beats backward) is detected.  Bumps the
        reset counter for WI-8 observability.
        """
        self._led_phrase_committed_start = None
        self._led_phrase_latch_reset_count += 1
        log.debug("[RGB] phrase-latch reset reason=%s", reason)

    def _clamp_led_beat(self, abs_beat_pos: float, active: int, load_gen: int) -> float:
        """WI-1 monotonic LED/phrasing playhead clamp.
        
        Sub-beat backward jitter (delta in (-LED_BACKSTEP_SEEK_BEATS, 0)) is held to
        the previous value so phrasing never crosses a segment boundary backwards.
        A backstep >= LED_BACKSTEP_SEEK_BEATS is a real seek/cue/reload: accept it and
        reset the phrase latch. Keyed on (active, load_gen) so a reload/deck-switch
        resets cleanly. No-op (pass-through) when the flag is off.
        """
        key = (active, load_gen)
        if key != self._led_beat_monotonic_key:
            self._led_beat_monotonic_key = key
            self._led_beat_monotonic = abs_beat_pos
            return abs_beat_pos
        prev = self._led_beat_monotonic
        if self._phrase_monotonic_enabled and prev is not None:
            delta = abs_beat_pos - prev
            if -LED_BACKSTEP_SEEK_BEATS < delta < 0.0:
                log.debug("[RGB] beat-clamp deck=%d abs=%.3f→%.3f delta=%.4f", active, abs_beat_pos, prev, delta)
                abs_beat_pos = prev
            elif delta <= -LED_BACKSTEP_SEEK_BEATS:
                log.debug("[RGB] beat-seek deck=%d abs=%.3f→%.3f delta=%.4f", active, prev, abs_beat_pos, delta)
                self._reset_led_phrase_latch("seek")
        self._led_beat_monotonic = abs_beat_pos
        return abs_beat_pos

    def _advance_led_phrase_latch(self, sp_state: SmartPhrasingState) -> None:
        """Advance the phrase-seq latch on a forward phrase change. WI-1 guarantees
        abs_beat (and thus current_phrase_start_beat) is monotonic, so this fires
        exactly once per phrase entry. Never retreats; retreat only via
        _reset_led_phrase_latch on a real seek."""
        start = sp_state.current_phrase_start_beat
        if start is None:
            return
        committed = self._led_phrase_committed_start
        if committed is None or start > committed:
            self._led_phrase_committed_start = start
            self._led_phrase_seq += 1
            log.debug("[RGB] phrase-latch advance seq=%d start=%.3f", self._led_phrase_seq, start)

    def _led_automation_role_key(
        self,
        active: int,
        d: DeckState,
        sp_state: SmartPhrasingState,
        role: str,
    ) -> str:
        marker = ""
        # M1b WI-2: structured section/cycle derived from the SAME source
        # expressions that build `marker` (never by parsing the marker string).
        section_id = ""
        cycle = 0
        if role == "drop":
            anchor = self._led_drop_marker_anchor(sp_state)
            if anchor is None:
                anchor = self._led_first_drop_anchor_beat
            if anchor is not None:
                marker = f"{float(anchor):.3f}"
        elif role == "post_drop":
            anchor = self._led_first_drop_anchor_beat
            if anchor is None:
                anchor = (
                    sp_state.current_phrase_start_beat
                    if sp_state.current_phrase_start_beat is not None
                    else sp_state.active_drop_beat
                )
            if anchor is not None:
                abs_beat = self._led_abs_beat(sp_state)
                elapsed = max(0.0, float(abs_beat or anchor) - float(anchor))
                cycle = int(elapsed // self._led_post_drop_cycle_beats())
                if self._phrase_monotonic_enabled:
                    # WI-2: embed phrase_seq instead of raw anchor to prevent
                    # A→B→A oscillation from different phrase start reads.
                    marker = f"seq{self._led_phrase_seq}:c{cycle}"
                    section_id = f"seq{self._led_phrase_seq}"
                else:
                    marker = f"{float(anchor):.3f}:c{cycle}"
                    section_id = f"{float(anchor):.3f}"
            else:
                marker = str(sp_state.current_phrase_label)
                section_id = marker
        elif role in {"buildup", "pre_drop"} and sp_state.next_smart_drop_beat is not None:
            section_id = f"{sp_state.next_smart_drop_beat:.3f}"
            if sp_state.beats_to_next_drop is not None:
                cycle = int(
                    max(0.0, float(sp_state.beats_to_next_drop))
                    // LED_DEFAULT_GROOVE_CYCLE_BEATS
                )
            marker = f"{section_id}:c{cycle}"
        elif role == "breakdown" and sp_state.breakdown_restore_beat is not None:
            section_id = f"{sp_state.breakdown_restore_beat:.3f}"
            abs_beat = self._led_abs_beat(sp_state)
            if abs_beat is not None:
                remaining = max(0.0, float(sp_state.breakdown_restore_beat) - float(abs_beat))
                cycle = int(remaining // LED_DEFAULT_GROOVE_CYCLE_BEATS)
            marker = f"{section_id}:c{cycle}"
        elif role == "groove":
            abs_beat = self._led_abs_beat(sp_state)
            if self._phrase_monotonic_enabled:
                # WI-2: embed monotonically-advancing seq instead of raw
                # current_phrase_start_beat.  The cycle still uses abs_beat
                # (which is itself clamped by WI-1) so a 112→80→112 wobble
                # maps to a single seq and the key does not change.
                if abs_beat is not None:
                    # When the latch hasn't been advanced yet (committed_start is
                    # None), fall back to current_phrase_start_beat so the cycle
                    # is still computed correctly.  The seq already disambiguates
                    # which phrase we are in; the committed_start only anchors the
                    # intra-phrase cycle offset.
                    committed = self._led_phrase_committed_start
                    if committed is None:
                        committed = sp_state.current_phrase_start_beat
                    elapsed_from_seq = max(
                        0.0,
                        float(abs_beat) - float(committed or 0.0),
                    )
                    cycle = int(elapsed_from_seq // LED_DEFAULT_GROOVE_CYCLE_BEATS)
                    marker = (
                        f"{sp_state.current_phrase_label}:"
                        f"seq{self._led_phrase_seq}:c{cycle}"
                    )
                    section_id = (
                        f"{sp_state.current_phrase_label}:"
                        f"seq{self._led_phrase_seq}"
                    )
                else:
                    marker = str(sp_state.current_phrase_label)
                    section_id = marker
            else:
                anchor = sp_state.current_phrase_start_beat
                if anchor is not None and abs_beat is not None:
                    elapsed = max(0.0, float(abs_beat) - float(anchor))
                    cycle = int(elapsed // LED_DEFAULT_GROOVE_CYCLE_BEATS)
                    marker = (
                        f"{sp_state.current_phrase_label}:"
                        f"{float(anchor):.3f}:c{cycle}"
                    )
                    section_id = (
                        f"{sp_state.current_phrase_label}:"
                        f"{float(anchor):.3f}"
                    )
                else:
                    marker = str(sp_state.current_phrase_label)
                    section_id = marker
        elif role == "ambient":
            if self._phrase_monotonic_enabled:
                # WI-2: use phrase_seq for ambient too — same class of oscillation risk
                abs_beat = self._led_abs_beat(sp_state)
                section_id = f"{sp_state.current_phrase_label}:seq{self._led_phrase_seq}"
                if abs_beat is not None:
                    committed = self._led_phrase_committed_start
                    if committed is None:
                        committed = sp_state.current_phrase_start_beat
                    elapsed = max(0.0, float(abs_beat) - float(committed or 0.0))
                    cycle = int(elapsed // LED_DEFAULT_GROOVE_CYCLE_BEATS)
                marker = f"{section_id}:c{cycle}"
            else:
                marker = str(sp_state.current_phrase_label)
        # M1b WI-2: publish structured section/cycle for the color engine.
        # `section_id or marker` keeps drop and legacy fallback branches on
        # section_id = marker / cycle = 0.
        self._led_last_section_cycle = (section_id or marker, cycle)
        return f"{active}:{d.load_gen}:{role}:{marker}"

    def _led_sp_state_with_offset(
        self,
        sp_state: SmartPhrasingState,
        bpm: float,
        offset_s: float | None = None,
    ) -> SmartPhrasingState:
        if offset_s is None:
            offset_s = self._led_automation_offset_s
        if offset_s <= 0.0 or bpm <= 0.0 or self._last_sp_snapshot is None:
            return sp_state
        snapshot = self._last_sp_snapshot
        if snapshot.abs_beat is None or not snapshot.is_playing:
            return sp_state
        offset_beats = (bpm / 60.0) * offset_s
        return self._smart_phrasing_engine.preview_with_beat_offset(
            snapshot,
            offset_beats,
        )

    def _led_sp_state_for_next_backend(
        self,
        sp_state: SmartPhrasingState,
        bpm: float,
    ) -> SmartPhrasingState:
        cloud_offset_s = self._led_cloud_automation_offset_s
        realtime_offset_s = self._led_realtime_automation_offset_s
        if cloud_offset_s == realtime_offset_s:
            return self._led_sp_state_with_offset(sp_state, bpm, cloud_offset_s)

        cloud_sp_state = self._led_sp_state_with_offset(sp_state, bpm, cloud_offset_s)
        if self._led_should_smart_drop_blackout(cloud_sp_state):
            drop_preview = self._led_drop_decision_for_anchor(
                cloud_sp_state,
                commit=True,
            )
            if (
                drop_preview is not None
                and str(getattr(drop_preview, "backend", "cloud_diy") or "cloud_diy")
                == "realtime_razer"
            ):
                return self._led_sp_state_with_offset(sp_state, bpm, realtime_offset_s)
            return cloud_sp_state

        cloud_role = self._led_role_from_smart_phrasing(cloud_sp_state)
        if cloud_role == "drop":
            cloud_preview = self._led_drop_decision_for_anchor(
                cloud_sp_state,
                commit=True,
            )
        else:
            cloud_preview = self._preview_led_decision_for_role(cloud_role)
        if cloud_preview is not None:
            backend = str(getattr(cloud_preview, "backend", "cloud_diy") or "cloud_diy")
            if backend == "realtime_razer":
                return self._led_sp_state_with_offset(sp_state, bpm, realtime_offset_s)
            return cloud_sp_state

        realtime_sp_state = self._led_sp_state_with_offset(
            sp_state,
            bpm,
            realtime_offset_s,
        )
        realtime_role = self._led_role_from_smart_phrasing(realtime_sp_state)
        if realtime_role == "drop":
            realtime_preview = self._led_drop_decision_for_anchor(
                realtime_sp_state,
                commit=True,
            )
        else:
            realtime_preview = self._preview_led_decision_for_role(realtime_role)
        if (
            realtime_preview is not None
            and str(getattr(realtime_preview, "backend", "cloud_diy") or "cloud_diy")
            == "realtime_razer"
        ):
            return realtime_sp_state
        return cloud_sp_state
