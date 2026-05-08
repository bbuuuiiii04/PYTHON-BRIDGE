"""Local status snapshot writer and hardened command reader."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional


STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"
COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
MAX_ARM_TTL_S = 30.0


class StatusWriter(threading.Thread):
    def __init__(self, sm, live_bpm, pos_cache, conn, mirror, validation_runner, command_reader) -> None:
        super().__init__(name="runtime-status", daemon=True)
        self._sm = sm
        self._live_bpm = live_bpm
        self._pos_cache = pos_cache
        self._conn = conn
        self._mirror = mirror
        self._validation_runner = validation_runner
        self._command_reader = command_reader
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
            "recent_errors": [],
        }


class CommandReader(threading.Thread):
    def __init__(self, mirror, validation_runner) -> None:
        super().__init__(name="runtime-command-reader", daemon=True)
        self._mirror = mirror
        self._validation_runner = validation_runner
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
    }
    if cmd not in allowed:
        raise ValueError(f"unknown command: {cmd}")
    if "expires_at" in obj:
        obj = dict(obj)
        obj.pop("expires_at", None)
    return obj


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
