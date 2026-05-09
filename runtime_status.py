"""Local status snapshot writer and hardened command reader."""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Any, Callable, Optional


STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"
COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
MAX_ARM_TTL_S = 30.0
log = logging.getLogger("runtime_status")


_DEFAULT_LASER_STATUS: dict[str, Any] = {
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
        mirror,
        validation_runner,
        command_reader,
        *,
        laser_status_provider: Optional[Callable[[], dict]] = None,
    ) -> None:
        super().__init__(name="runtime-status", daemon=True)
        self._sm = sm
        self._live_bpm = live_bpm
        self._pos_cache = pos_cache
        self._conn = conn
        self._mirror = mirror
        self._validation_runner = validation_runner
        self._command_reader = command_reader
        self._laser_status_provider = laser_status_provider
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
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
        return {
            "schema": 1,
            "written_at": time.time(),
            "process": {"state": "on", "pid": os.getpid()},
            "state_manager": state,
            "deck_runtime": decks,
            "soundswitch": self._conn.status(),
            "mirror": self._mirror.get_summary(),
            "validation": self._validation_runner.last_result().to_dict(),
            "commands": self._command_reader.status(),
            "laser_director": laser,
            "recent_errors": [],
        }

    def _safe_laser_status(self) -> dict[str, Any]:
        try:
            return self._laser_status_provider()
        except Exception as exc:
            log.warning("[STATUS] laser_status_provider_failed err=%s", exc)
            fallback = dict(_DEFAULT_LASER_STATUS)
            fallback["reason"] = "provider_error"
            fallback["last_error"] = f"{type(exc).__name__}: {exc}"
            return fallback


class CommandReader(threading.Thread):
    def __init__(
        self,
        mirror,
        validation_runner,
        smart_drop_toggle_callback: Optional[Callable[[], None]] = None,
        smart_breakdown_toggle_callback: Optional[Callable[[], None]] = None,
        laser_toggle_callback: Optional[Callable[[], Any]] = None,
        laser_set_enabled_callback: Optional[Callable[[bool], Any]] = None,
        laser_blackout_callback: Optional[Callable[[], Any]] = None,
        laser_clear_blackout_callback: Optional[Callable[[], Any]] = None,
        laser_scene_callback: Optional[Callable[[str, float], Any]] = None,
        laser_clear_scene_override_callback: Optional[Callable[[], Any]] = None,
        laser_set_personality_callback: Optional[Callable[[str], Any]] = None,
    ) -> None:
        super().__init__(name="runtime-command-reader", daemon=True)
        self._mirror = mirror
        self._validation_runner = validation_runner
        self._smart_drop_toggle_callback = smart_drop_toggle_callback
        self._smart_breakdown_toggle_callback = smart_breakdown_toggle_callback
        self._laser_toggle_callback = laser_toggle_callback
        self._laser_set_enabled_callback = laser_set_enabled_callback
        self._laser_blackout_callback = laser_blackout_callback
        self._laser_clear_blackout_callback = laser_clear_blackout_callback
        self._laser_scene_callback = laser_scene_callback
        self._laser_clear_scene_override_callback = laser_clear_scene_override_callback
        self._laser_set_personality_callback = laser_set_personality_callback
        self._stop_event = threading.Event()
        self._arm_expires = 0.0
        self._last_command = ""
        self._last_error = ""
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()

    def status(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            return {
                "armed": now < self._arm_expires,
                "arm_expires_at": self._arm_expires,
                "last_command": self._last_command,
                "last_error": self._last_error,
            }

    def run(self) -> None:
        _prepare_command_file()
        with open(COMMANDS_PATH, "r", encoding="utf-8") as fp:
            fp.seek(0, os.SEEK_END)
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
        if cmd == "arm_live":
            ttl = min(float(command.get("ttl_s", MAX_ARM_TTL_S)), MAX_ARM_TTL_S)
            with self._lock:
                self._arm_expires = time.time() + max(0.0, ttl)
            return
        if cmd == "disarm_live":
            with self._lock:
                self._arm_expires = 0.0
            return
        if cmd == "toggle_mirror":
            self._mirror.toggle()
            return
        if cmd == "set_mirror":
            self._mirror.set_enabled(bool(command.get("enabled")))
            return
        if cmd == "start_capture":
            self._mirror.start_capture(str(command.get("name") or "capture"))
            return
        if cmd == "stop_capture":
            self._mirror.stop_capture()
            return
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
        if cmd == "laser_set_personality":
            if self._laser_set_personality_callback:
                personality = str(command["personality"])
                ok, detail = _invoke_callback(lambda: self._laser_set_personality_callback(personality))
                if not ok:
                    with self._lock:
                        self._last_error = f"laser_set_personality callback failed: {detail}"
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
        "arm_live",
        "disarm_live",
        "toggle_mirror",
        "set_mirror",
        "start_capture",
        "stop_capture",
        "run_validation",
        "toggle_smart_drop",
        "toggle_smart_breakdown",
        "toggle_laser_director",
        "set_laser_director",
        "laser_blackout",
        "laser_clear_blackout",
        "laser_scene",
        "laser_clear_scene_override",
        "laser_set_personality",
    }
    if cmd not in allowed:
        raise ValueError(f"unknown command: {cmd}")
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
    if cmd == "laser_set_personality":
        personality = obj.get("personality")
        if not isinstance(personality, str) or not personality:
            raise ValueError("laser_set_personality requires non-empty personality")
    if "expires_at" in obj:
        obj = dict(obj)
        obj.pop("expires_at", None)
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
