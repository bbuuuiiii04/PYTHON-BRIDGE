"""Local status snapshot writer and hardened command reader."""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Any, Callable, Optional

from . import bridge_log
from .active_deck_resolver import RB_MASTER_STALE_AFTER_S
from .bridge_fmt import log_throttled


STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"
COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
log = logging.getLogger("runtime_status")
HEARTBEAT_LOG_INTERVAL_S = 2.0


_DEFAULT_LASER_STATUS: dict[str, Any] = {
    "available": False,
    "enabled": False,
    "reason": "not_configured",
}


# Sanitized — no paths/ports/aliases/devices/UUIDs/raw error messages (T7e §B1).
_DEFAULT_PACK_STATUS: dict[str, Any] = {
    "available": False,
    "enabled": False,
    "backend": "disabled",
    "pack_loaded": False,
    "parity_lanes": {
        "algorithm_generalized": 0,
        "oracle_proven": 0,
        "unverified_parity": 0,
    },
    "unverified_parity_count": 0,
    "unverified_documents": [],
    "static_binding_gap": False,
    "static_binding_gap_count": 0,
    "pack_sha12": "",
    "pack_sha256": "",
    "operational_state": "disabled",
    "scripted_active": False,
    "input_degraded": False,
    "static_held": False,
    "blackout": False,
    "parity_live_blocked": False,
    "autoloop_phase_blocked": False,
    "software_zero_frame": True,
    "native_autoloop": {
        "status": "software_zero_frame",
        "role": "",
        "scene": "",
        "note": None,
        "soundswitch_name": "",
        "target_identity": "",
        "anchor_beat": None,
        "phase_tick": None,
        "reason": "",
        "diagnostic": "",
    },
    "frame_count": 0,
    "has_active_identity": False,
    "truth_check": {
        "enabled": False,
        "reason": "not_configured",
        "run_id": "",
        "universe": None,
        "targets": [],
        "sidecar_path": "",
        "current_sequence": 0,
        "dropped_count": 0,
        "overflow_count": 0,
        "send_error_count": 0,
        "sidecar_error": "",
        "pack_sha256": "",
        "ch1_dmx_address": None,
    },
    "reason": "not_configured",
}


_DEFAULT_LED_STATUS: dict[str, Any] = {
    "available": False,
    "enabled": False,
    "reason": "not_configured",
    "manual_override": "",
    "emergency_blackout": False,
    "last_error": "",
    "trigger_count": 0,
    "rejected_count": 0,
}

_DEFAULT_COLOR_STATUS: dict[str, Any] = {
    "available": False,
    "enabled": False,
    "reason": "not_configured",
}


class StatusWriter(threading.Thread):
    def __init__(
        self,
        sm,
        live_bpm,
        pos_cache,
        conn,
        validation_runner,
        command_reader,
        *,
        laser_status_provider: Optional[Callable[[], dict]] = None,
        led_status_provider: Optional[Callable[[], dict]] = None,
        color_engine_status_provider: Optional[Callable[[], dict]] = None,
        pack_status_provider: Optional[Callable[[], dict]] = None,
        heartbeat_interval_s: float = HEARTBEAT_LOG_INTERVAL_S,
    ) -> None:
        super().__init__(name="runtime-status", daemon=True)
        self._sm = sm
        self._live_bpm = live_bpm
        self._pos_cache = pos_cache
        self._conn = conn
        self._validation_runner = validation_runner
        self._command_reader = command_reader
        self._laser_status_provider = laser_status_provider
        self._led_status_provider = led_status_provider
        self._pack_status_provider = pack_status_provider
        self._color_engine_status_provider = color_engine_status_provider
        self._heartbeat_interval_s = max(0.5, float(heartbeat_interval_s))
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        with bridge_log.thread_guard("runtime-status"):
            while not self._stop_event.is_set():
                self.write_once()
                self._stop_event.wait(0.5)

    def write_once(self) -> None:
        data = self.snapshot()
        atomic_write_json(STATUS_PATH, data)

    def snapshot(self) -> dict[str, Any]:
        state = self._sm.snapshot()
        decks = {}
        for deck in (1, 2):
            pos = self._pos_cache.get(deck)
            live = self._live_bpm.get_status(deck) if self._live_bpm is not None else None
            summary = self._live_bpm.get_summary(deck) if self._live_bpm is not None else None
            decks[str(deck)] = {
                "memory": _position_snapshot(pos),
                "live_bpm": _live_bpm_status(live),
                "live_bpm_summary": _obj_dict(summary),
            }
        laser = (
            dict(_DEFAULT_LASER_STATUS)
            if self._laser_status_provider is None
            else self._safe_laser_status()
        )
        led = (
            dict(_DEFAULT_LED_STATUS)
            if self._led_status_provider is None
            else self._safe_led_status()
        )
        data = {
            "schema": 1,
            "written_at": time.time(),
            "process": {"state": "on", "pid": os.getpid()},
            "state_manager": state,
            "deck_runtime": decks,
            "soundswitch": self._conn.status(),
            "validation": self._validation_runner.last_result().to_dict(),
            "commands": self._command_reader.status(),
            "laser_director": laser,
            "led_look_director": led,
            "soundswitch_pack": (
                dict(_DEFAULT_PACK_STATUS)
                if self._pack_status_provider is None
                else self._safe_pack_status()
            ),
            "recent_errors": [],
        }
        state_color = _dict_or_empty(state.get("led_color_engine"))
        color = (
            state_color
            if self._color_engine_status_provider is None and state_color
            else _safe_provider_snapshot(
                self._color_engine_status_provider,
                provider_name="color_engine_status_provider",
                default=_DEFAULT_COLOR_STATUS,
            )
        )
        heartbeat = _heartbeat_payload(
            state=state,
            deck_runtime=decks,
            laser=laser,
            led=led,
            color=color,
        )
        data["heartbeat"] = heartbeat
        self._maybe_log_heartbeat(heartbeat)
        return data

    def _safe_laser_status(self) -> dict[str, Any]:
        return _safe_provider_snapshot(
            self._laser_status_provider,
            provider_name="laser_status_provider",
            throttle_key=f"laser_status_provider.{id(self)}",
            default=_DEFAULT_LASER_STATUS,
        )

    def _maybe_log_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        if not log_throttled(
            f"runtime_status.beat_heartbeat.{id(self)}",
            self._heartbeat_interval_s,
            time.monotonic(),
        ):
            return
        bridge_log.perf("heartbeat", "beat", data=heartbeat)

    def _safe_led_status(self) -> dict[str, Any]:
        return _safe_provider_snapshot(
            self._led_status_provider,
            provider_name="led_status_provider",
            throttle_key=f"led_status_provider.{id(self)}",
            default=_DEFAULT_LED_STATUS,
        )

    def _safe_pack_status(self) -> dict[str, Any]:
        try:
            payload = self._pack_status_provider()
            if isinstance(payload, dict):
                return payload
        except Exception as exc:
            if log_throttled(
                f"runtime_status.provider_failure.pack_status_provider.{id(self)}", 5.0
            ):
                log.warning("[STATUS] pack_status_provider_failed err=%s", type(exc).__name__)
        fallback = dict(_DEFAULT_PACK_STATUS)
        fallback["reason"] = "provider_error"
        return fallback


class CommandReader(threading.Thread):
    def __init__(
        self,
        validation_runner,
        smart_drop_toggle_callback: Optional[Callable[[], None]] = None,
        smart_breakdown_toggle_callback: Optional[Callable[[], None]] = None,
        laser_toggle_callback: Optional[Callable[[], Any]] = None,
        laser_set_enabled_callback: Optional[Callable[[bool], Any]] = None,
        laser_blackout_callback: Optional[Callable[[], Any]] = None,
        laser_clear_blackout_callback: Optional[Callable[[], Any]] = None,
        laser_scene_callback: Optional[Callable[[str, float], Any]] = None,
        laser_clear_scene_override_callback: Optional[Callable[[], Any]] = None,
        led_set_enabled_callback: Optional[Callable[[bool], Any]] = None,
        led_scene_callback: Optional[Callable[[str, Optional[float], Optional[str]], Any]] = None,
        led_blackout_callback: Optional[Callable[[Optional[str], Optional[str]], Any]] = None,
        led_clear_blackout_callback: Optional[Callable[[Optional[str]], Any]] = None,
        led_clear_scene_override_callback: Optional[Callable[[], Any]] = None,
        led_palette_callback: Optional[Callable[[str, Optional[str]], Any]] = None,
        record_session_toggle_callback: Optional[Callable[[Optional[str], bool], Any]] = None,
        pack_command_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        super().__init__(name="runtime-command-reader", daemon=True)
        self._validation_runner = validation_runner
        self._smart_drop_toggle_callback = smart_drop_toggle_callback
        self._smart_breakdown_toggle_callback = smart_breakdown_toggle_callback
        self._laser_toggle_callback = laser_toggle_callback
        self._laser_set_enabled_callback = laser_set_enabled_callback
        self._laser_blackout_callback = laser_blackout_callback
        self._laser_clear_blackout_callback = laser_clear_blackout_callback
        self._laser_scene_callback = laser_scene_callback
        self._laser_clear_scene_override_callback = laser_clear_scene_override_callback
        self._led_set_enabled_callback = led_set_enabled_callback
        self._led_scene_callback = led_scene_callback
        self._led_blackout_callback = led_blackout_callback
        self._led_clear_blackout_callback = led_clear_blackout_callback
        self._led_clear_scene_override_callback = led_clear_scene_override_callback
        self._led_palette_callback = led_palette_callback
        self._record_session_toggle_callback = record_session_toggle_callback
        self._pack_command_callback = pack_command_callback
        self._stop_event = threading.Event()
        self._last_command = ""
        self._last_error = ""
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "last_command": self._last_command,
                "last_error": self._last_error,
            }

    def run(self) -> None:
        _prepare_command_file()
        with open(COMMANDS_PATH, "r", encoding="utf-8") as fp:
            fp.seek(0, os.SEEK_END)
            with bridge_log.thread_guard("runtime-command-reader"):
                while not self._stop_event.is_set():
                    line = fp.readline()
                    if not line:
                        self._stop_event.wait(0.2)
                        continue
                    self.handle_line(line)

    def handle_line(self, line: str) -> None:
        try:
            command = parse_command(line)
            self.handle_command(command)
        except ValueError as exc:
            with self._lock:
                self._last_error = str(exc)

    def handle_command(self, command: dict[str, Any]) -> None:
        cmd = command["cmd"]
        with self._lock:
            self._last_command = cmd
            self._last_error = ""
        if cmd == "run_validation":
            self._run_validation_async()
            return
        if cmd == "toggle_smart_drop":
            if self._smart_drop_toggle_callback:
                ok, detail = _invoke_callback(self._smart_drop_toggle_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"toggle_smart_drop callback failed: {detail}"
            return
        if cmd == "toggle_smart_breakdown":
            if self._smart_breakdown_toggle_callback:
                ok, detail = _invoke_callback(self._smart_breakdown_toggle_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"toggle_smart_breakdown callback failed: {detail}"
            return
        if cmd == "toggle_laser_director":
            if self._laser_toggle_callback:
                ok, detail = _invoke_callback(self._laser_toggle_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"toggle_laser_director callback failed: {detail}"
            return
        if cmd == "set_laser_director":
            if self._laser_set_enabled_callback:
                enabled = bool(command["enabled"])
                ok, detail = _invoke_callback(lambda: self._laser_set_enabled_callback(enabled))
                if not ok:
                    with self._lock:
                        self._last_error = f"set_laser_director callback failed: {detail}"
            return
        if cmd == "laser_blackout":
            if self._laser_blackout_callback:
                ok, detail = _invoke_callback(self._laser_blackout_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"laser_blackout callback failed: {detail}"
            return
        if cmd == "laser_clear_blackout":
            if self._laser_clear_blackout_callback:
                ok, detail = _invoke_callback(self._laser_clear_blackout_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"laser_clear_blackout callback failed: {detail}"
            return
        if cmd == "laser_scene":
            if self._laser_scene_callback:
                scene = str(command["scene"])
                ttl_s = float(command["ttl_s"])
                ok, detail = _invoke_callback(lambda: self._laser_scene_callback(scene, ttl_s))
                if not ok:
                    with self._lock:
                        self._last_error = f"laser_scene callback failed: {detail}"
            return
        if cmd == "laser_clear_scene_override":
            if self._laser_clear_scene_override_callback:
                ok, detail = _invoke_callback(self._laser_clear_scene_override_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"laser_clear_scene_override callback failed: {detail}"
            return
        if cmd == "toggle_record_session":
            if self._record_session_toggle_callback:
                path = command.get("path")
                dedup = bool(command.get("dedup", False))
                ok, detail = _invoke_callback(lambda: self._record_session_toggle_callback(path, dedup))
                if not ok:
                    with self._lock:
                        self._last_error = f"toggle_record_session callback failed: {detail}"
            return
        if cmd == "set_led_look_director":
            if self._led_set_enabled_callback:
                enabled = bool(command["enabled"])
                ok, detail = _invoke_callback(lambda: self._led_set_enabled_callback(enabled))
                if not ok:
                    with self._lock:
                        self._last_error = f"set_led_look_director callback failed: {detail}"
            return
        if cmd == "led_scene":
            if self._led_scene_callback:
                look = str(command["look"])
                ttl_raw = command.get("ttl_s")
                ttl_s = float(ttl_raw) if ttl_raw is not None else None
                target_raw = command.get("target")
                target = str(target_raw) if target_raw is not None else None
                ok, detail = _invoke_callback(
                    lambda: self._led_scene_callback(look, ttl_s, target)
                )
                if not ok:
                    with self._lock:
                        self._last_error = f"led_scene callback failed: {detail}"
            return
        if cmd == "led_blackout":
            if self._led_blackout_callback:
                reason_raw = command.get("reason")
                reason = str(reason_raw) if reason_raw is not None else None
                target_raw = command.get("target")
                target = str(target_raw) if target_raw is not None else None
                ok, detail = _invoke_callback(
                    lambda: self._led_blackout_callback(reason, target)
                )
                if not ok:
                    with self._lock:
                        self._last_error = f"led_blackout callback failed: {detail}"
            return
        if cmd == "led_clear_blackout":
            if self._led_clear_blackout_callback:
                reason_raw = command.get("reason")
                reason = str(reason_raw) if reason_raw is not None else None
                ok, detail = _invoke_callback(
                    lambda: self._led_clear_blackout_callback(reason)
                )
                if not ok:
                    with self._lock:
                        self._last_error = f"led_clear_blackout callback failed: {detail}"
            return
        if cmd == "led_clear_scene_override":
            if self._led_clear_scene_override_callback:
                ok, detail = _invoke_callback(self._led_clear_scene_override_callback)
                if not ok:
                    with self._lock:
                        self._last_error = f"led_clear_scene_override callback failed: {detail}"
            return
        if cmd in {
            "led_palette_queue",
            "led_palette_override",
            "led_palette_lock",
            "led_palette_unlock",
            "led_rainbow_toggle",
            "led_engine",
            "led_manual_override",
            "led_manual_clear",
            "led_max_energy_toggle",
        }:
            if self._led_palette_callback:
                name_raw = command.get("mode") if cmd == "led_engine" else command.get("name")
                name = str(name_raw) if name_raw is not None else None
                ok, detail = _invoke_callback(
                    lambda: self._led_palette_callback(cmd, name)
                )
                if not ok:
                    with self._lock:
                        self._last_error = f"{cmd} callback failed: {detail}"
            return
        if cmd == "set_soundswitch_pack":
            if self._pack_command_callback:
                kwargs = {k: command[k] for k in ("backend", "enabled") if k in command}
                # SANITIZED: the controller returns (ok, class/category); if it raises we
                # store ONLY the exception class name. Never a raw message (paths/ports).
                try:
                    result = self._pack_command_callback(command["action"], **kwargs)
                    ok = result[0] if isinstance(result, tuple) else bool(result)
                    detail = (result[1] if isinstance(result, tuple) and len(result) > 1
                              else "")
                except Exception as exc:
                    ok, detail = False, type(exc).__name__
                if not ok:
                    with self._lock:
                        self._last_error = f"set_soundswitch_pack callback failed: {detail}"
            return
        raise ValueError(f"unknown command: {cmd}")

    def _run_validation_async(self) -> None:
        def _target() -> None:
            self._validation_runner.mark_running("starting")
            try:
                self._validation_runner.run()
            except Exception as exc:
                self._validation_runner.mark_failed(str(exc))

        threading.Thread(target=_target, name="validation-runner", daemon=True).start()


def parse_command(line: str) -> dict[str, Any]:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("command must be an object")
    cmd = obj.get("cmd")
    if not isinstance(cmd, str) or not cmd:
        raise ValueError("command requires cmd")
    allowed = {
        "run_validation",
        "toggle_smart_drop",
        "toggle_smart_breakdown",
        "toggle_laser_director",
        "set_laser_director",
        "laser_blackout",
        "laser_clear_blackout",
        "laser_scene",
        "laser_clear_scene_override",
        "toggle_record_session",
        "led_scene",
        "led_blackout",
        "led_clear_blackout",
        "led_clear_scene_override",
        "set_led_look_director",
        "led_palette_queue",
        "led_palette_override",
        "led_palette_lock",
        "led_palette_unlock",
        "led_rainbow_toggle",
        "led_engine",
        "led_manual_override",
        "led_manual_clear",
        "led_max_energy_toggle",
        "set_soundswitch_pack",
    }
    if cmd not in allowed:
        raise ValueError(f"unknown command: {cmd}")
    if cmd == "set_soundswitch_pack":
        action = obj.get("action")
        if action not in {"reload", "backend", "enable"}:
            raise ValueError("set_soundswitch_pack action must be reload|backend|enable")
        extra = set(obj) - {"cmd", "action", "backend", "enabled"}
        if extra:
            raise ValueError(f"set_soundswitch_pack unexpected keys: {sorted(extra)}")
        if action == "backend":
            if obj.get("backend") not in {"pack", "none", "midi"}:
                raise ValueError("set_soundswitch_pack backend must be pack|none|midi")
        elif action == "enable":
            if not isinstance(obj.get("enabled"), bool):
                raise ValueError("set_soundswitch_pack enabled must be boolean")
    if cmd == "set_laser_director":
        if "enabled" not in obj:
            raise ValueError("set_laser_director requires enabled")
        if not isinstance(obj["enabled"], bool):
            raise ValueError("set_laser_director enabled must be boolean")
    if cmd == "laser_scene":
        scene = obj.get("scene")
        if not isinstance(scene, str) or not scene:
            raise ValueError("laser_scene requires non-empty scene")
        ttl_s = obj.get("ttl_s", 4.0)
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)):
            raise ValueError("laser_scene ttl_s must be numeric")
        ttl_s = float(ttl_s)
        if not math.isfinite(ttl_s):
            raise ValueError("laser_scene ttl_s must be finite")
        obj = dict(obj)
        obj["ttl_s"] = min(30.0, max(0.0, ttl_s))
    if cmd == "toggle_record_session":
        path = obj.get("path")
        if path is not None and (not isinstance(path, str) or not path):
            raise ValueError("toggle_record_session path must be a non-empty string")
        dedup = obj.get("dedup", False)
        if not isinstance(dedup, bool):
            raise ValueError("toggle_record_session dedup must be boolean")
    if cmd == "led_scene":
        extra = set(obj.keys()) - {"cmd", "look", "scene", "ttl_s", "target"}
        if extra:
            raise ValueError("led_scene has unknown fields")
        look = obj.get("look")
        scene = obj.get("scene")
        if look is None and scene is None:
            raise ValueError("led_scene requires non-empty look")
        if look is not None and scene is not None and look != scene:
            raise ValueError("led_scene look and scene must match when both provided")
        selected = look if look is not None else scene
        if not isinstance(selected, str) or not selected.strip():
            raise ValueError("led_scene requires non-empty look")
        normalized = selected.strip()
        obj = dict(obj)
        obj["look"] = normalized
        obj.pop("scene", None)
        if "ttl_s" in obj:
            ttl_s = obj["ttl_s"]
            if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)):
                raise ValueError("led_scene ttl_s must be numeric")
            ttl_s = float(ttl_s)
            if not math.isfinite(ttl_s):
                raise ValueError("led_scene ttl_s must be finite")
            if ttl_s <= 0.0:
                raise ValueError("led_scene ttl_s must be positive")
            if ttl_s > 300.0:
                raise ValueError("led_scene ttl_s must be <= 300.0")
            obj["ttl_s"] = ttl_s
        target = obj.get("target")
        if target is not None:
            if not isinstance(target, str) or not target.strip():
                raise ValueError("led_scene target must be a non-empty string")
            obj = dict(obj)
            obj["target"] = target.strip()
    if cmd == "led_blackout":
        extra = set(obj.keys()) - {"cmd", "reason", "target"}
        if extra:
            raise ValueError("led_blackout has unknown fields")
        reason = obj.get("reason")
        if reason is not None:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("led_blackout reason must be a non-empty string")
            obj = dict(obj)
            obj["reason"] = reason.strip()
        target = obj.get("target")
        if target is not None:
            if not isinstance(target, str) or not target.strip():
                raise ValueError("led_blackout target must be a non-empty string")
            obj = dict(obj)
            obj["target"] = target.strip()
    if cmd == "led_clear_blackout":
        extra = set(obj.keys()) - {"cmd", "reason"}
        if extra:
            raise ValueError("led_clear_blackout has unknown fields")
        reason = obj.get("reason")
        if reason is not None:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("led_clear_blackout reason must be a non-empty string")
            obj = dict(obj)
            obj["reason"] = reason.strip()
    if cmd == "led_clear_scene_override":
        extra = set(obj.keys()) - {"cmd"}
        if extra:
            raise ValueError(f"{cmd} does not accept payload fields")
    if cmd in {"led_palette_queue", "led_palette_override"}:
        extra = set(obj.keys()) - {"cmd", "name"}
        if extra:
            raise ValueError(f"{cmd} has unknown fields")
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{cmd} requires non-empty name")
        obj = dict(obj)
        obj["name"] = name.strip()
    if cmd in {"led_palette_lock", "led_palette_unlock", "led_rainbow_toggle"}:
        extra = set(obj.keys()) - {"cmd"}
        if extra:
            raise ValueError(f"{cmd} does not accept payload fields")
    if cmd == "led_engine":
        extra = set(obj.keys()) - {"cmd", "mode"}
        if extra:
            raise ValueError("led_engine has unknown fields")
        mode = obj.get("mode")
        if mode not in {"v1", "v2"}:
            raise ValueError("led_engine mode must be v1|v2")
    if cmd == "led_manual_override":
        extra = set(obj.keys()) - {"cmd", "name"}
        if extra:
            raise ValueError("led_manual_override has unknown fields")
        name = obj.get("name")
        if name not in {"white_sand", "red", "green", "blue"}:
            raise ValueError("led_manual_override name must be white_sand|red|green|blue")
    if cmd in {"led_manual_clear", "led_max_energy_toggle"}:
        extra = set(obj.keys()) - {"cmd"}
        if extra:
            raise ValueError(f"{cmd} does not accept payload fields")
    if cmd == "set_led_look_director":
        extra = set(obj.keys()) - {"cmd", "enabled"}
        if extra:
            raise ValueError("set_led_look_director has unknown fields")
        if "enabled" not in obj:
            raise ValueError("set_led_look_director requires enabled")
        if not isinstance(obj["enabled"], bool):
            raise ValueError("set_led_look_director enabled must be boolean")
    return obj


def _invoke_callback(cb: Callable[[], Any]) -> tuple[bool, str]:
    """Call *cb* and return (ok, detail).

    Used by CommandReader so every callback slot gets consistent failure
    reporting without repeating try/except at each call site.
    """
    try:
        result = cb()
        if result is False:
            return False, "callback returned False"
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def atomic_write_json(path: str, data: dict[str, Any]) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, sort_keys=True)
        fp.write("\n")
    os.replace(tmp, path)


def _prepare_command_file() -> None:
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    fd = os.open(COMMANDS_PATH, flags, 0o600)
    os.close(fd)
    try:
        os.chmod(COMMANDS_PATH, 0o600)
    except OSError:
        pass


def _safe_provider_snapshot(
    provider: Optional[Callable[[], dict]],
    *,
    provider_name: str,
    default: dict[str, Any],
    throttle_key: Optional[str] = None,
) -> dict[str, Any]:
    if provider is None:
        return dict(default)
    try:
        payload = provider()
        if isinstance(payload, dict):
            return payload
        fallback = dict(default)
        fallback["reason"] = "provider_error"
        fallback["last_error"] = f"{provider_name} returned {type(payload).__name__}"
        return fallback
    except Exception as exc:
        key = throttle_key or provider_name
        if log_throttled(f"runtime_status.provider_failure.{key}", 5.0):
            log.warning("[STATUS] %s_failed err=%s", provider_name, exc)
        fallback = dict(default)
        fallback["reason"] = "provider_error"
        fallback["last_error"] = f"{type(exc).__name__}: {exc}"
        return fallback


def _heartbeat_payload(
    *,
    state: dict[str, Any],
    deck_runtime: dict[str, Any],
    laser: dict[str, Any],
    led: dict[str, Any],
    color: dict[str, Any],
) -> dict[str, Any]:
    active_deck = _as_int(state.get("active_deck"), default=0)
    rb_master_valid = bool(state.get("rb_master_deck_valid", False))
    try:
        rb_master_age = float(state.get("rb_master_deck_age_s"))
    except (TypeError, ValueError):
        rb_master_age = None
    if (
        rb_master_age is not None
        and math.isfinite(rb_master_age)
        and rb_master_age > RB_MASTER_STALE_AFTER_S
    ):
        rb_master_valid = False
    rb_master = state.get("rb_master_deck") if rb_master_valid else None
    deck_key = str(active_deck)
    deck_state = (
        _dict_or_empty(_dict_or_empty(state.get("deck")).get(deck_key))
        if active_deck in (1, 2)
        else {}
    )
    deck_status = _dict_or_empty(deck_runtime.get(deck_key)) if active_deck in (1, 2) else {}
    live_bpm = _dict_or_empty(deck_status.get("live_bpm"))
    smart_phrasing = _dict_or_empty(state.get("smart_phrasing"))

    bpm_value = live_bpm.get("bpm") if live_bpm.get("valid") else None
    bpm_source = "live" if bpm_value is not None else "deck"
    if bpm_value is None:
        bpm_value = deck_state.get("bpm")

    laser_scene = str(laser.get("current_scene") or "")
    executor = _dict_or_empty(laser.get("executor"))
    if not laser_scene:
        laser_scene = str(executor.get("last_scene") or "")

    led_look = str(led.get("last_look") or "")
    director = _dict_or_empty(led.get("director"))
    if not led_look:
        led_look = str(director.get("current_look") or "")

    return {
        "deck": active_deck,
        "show_deck": active_deck,
        "master": rb_master,
        "rb_master_deck": rb_master,
        "rb_master_deck_valid": rb_master_valid,
        "active_deck_authority_reason": str(
            state.get("active_deck_authority_reason") or ""
        ),
        "mixer_authority_valid": bool(state.get("mixer_authority_valid", False)),
        "mixer_fallback_reason": str(state.get("mixer_fallback_reason") or ""),
        "bpm": _fmt_float(bpm_value),
        "bpm_source": bpm_source,
        "phrase": str(smart_phrasing.get("phrase_label") or "unknown"),
        "laser_scene": laser_scene or "none",
        "led_look": led_look or "none",
        "palette": str(color.get("current_palette") or "none"),
        "rgb_health": _rgb_health(led),
    }


def _rgb_health(led: dict[str, Any]) -> str:
    if not bool(led.get("available", False)):
        return str(led.get("reason") or "not_configured")
    if not bool(led.get("enabled", False)):
        return "disabled"
    if led.get("last_error"):
        return "degraded"
    adapter = _dict_or_empty(led.get("adapter"))
    realtime = _dict_or_empty(adapter.get("realtime"))
    if adapter.get("last_error") or realtime.get("last_error"):
        return "degraded"
    if realtime:
        active = bool(realtime.get("active", False))
        transport = _dict_or_empty(realtime.get("transport"))
        send_errors = _as_int(transport.get("send_error_count"), default=0)
        if send_errors > 0:
            return "degraded"
        return "realtime_active" if active else "realtime_idle"
    return str(led.get("reason") or "ok")


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fmt_float(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if not math.isfinite(number) or number <= 0:
        return "unknown"
    return f"{number:.1f}"


def _position_snapshot(pos) -> Optional[dict[str, Any]]:
    if pos is None:
        return None
    return {
        "deck": pos.deck,
        "elapsed_ms": pos.elapsed_ms,
        "playing": pos.playing,
        "track_length_ms": pos.track_length_ms,
        "updated_at": pos.updated_at,
        "age_s": pos.age_s(),
        "stale": pos.is_stale(),
    }


def _live_bpm_status(status) -> Optional[dict[str, Any]]:
    return _obj_dict(status)


def _obj_dict(obj) -> Optional[dict[str, Any]]:
    if obj is None:
        return None
    if hasattr(obj, "__dataclass_fields__"):
        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
    return dict(obj)
