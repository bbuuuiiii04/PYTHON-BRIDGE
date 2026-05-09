"""Contextual bridge validation checks for the operator dashboard."""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .scripted_tracks import SCRIPTED_TRACKS


STATUS_PASS = "pass"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_NA = "not_applicable"
STATUS_WARMING = "warming"


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class ValidationResult:
    state: str
    ran_at: float
    current_step: str
    checks: list[ValidationCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        counts = {s: 0 for s in (STATUS_PASS, STATUS_WARN, STATUS_FAIL, STATUS_NA, STATUS_WARMING)}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        latest = next((c.detail for c in reversed(self.checks) if c.status in (STATUS_FAIL, STATUS_WARN)), "")
        return {
            "state": self.state,
            "ran_at": self.ran_at,
            "current_step": self.current_step,
            "checks": [c.to_dict() for c in self.checks],
            "pass_count": counts[STATUS_PASS],
            "warn_count": counts[STATUS_WARN],
            "fail_count": counts[STATUS_FAIL],
            "not_applicable_count": counts[STATUS_NA],
            "warming_count": counts[STATUS_WARMING],
            "latest_issue": latest,
        }


class ValidationRunner:
    def __init__(
        self,
        conn,
        pos_cache,
        live_bpm,
        sm=None,
        *,
        scripted_registry=None,
        bridge_pattern: str = "rb_ss_bridge_v2",
        rb_pattern: str = "rekordbox",
    ) -> None:
        self._conn = conn
        self._pos_cache = pos_cache
        self._live_bpm = live_bpm
        self._sm = sm
        self._scripted_registry = scripted_registry if scripted_registry is not None else SCRIPTED_TRACKS
        self._bridge_pattern = bridge_pattern
        self._rb_pattern = rb_pattern
        self._lock = threading.Lock()
        self._last = ValidationResult("idle", 0.0, "idle", [])

    def run(self) -> ValidationResult:
        checks: list[ValidationCheck] = []

        def add(name: str, status: str, detail: str = "") -> None:
            checks.append(ValidationCheck(name, status, detail))

        add("bridge_singleton", *self._check_singleton())
        add("soundswitch_connection", *self._check_soundswitch())
        add("rekordbox_process", *self._check_process(self._rb_pattern, "rekordbox"))
        self._check_memory(add)
        self._check_live_bpm(add)
        self._check_autoloop(add)
        self._check_scripted(add)
        add("os2l_queue", *self._check_queue())
        self._check_laser(add)

        result = ValidationResult("done", time.time(), checks[-1].name if checks else "done", checks)
        with self._lock:
            self._last = result
        return result

    def last_result(self) -> ValidationResult:
        with self._lock:
            return self._last

    def mark_running(self, step: str = "starting") -> None:
        with self._lock:
            self._last = ValidationResult("running", time.time(), step, [])

    def mark_failed(self, detail: str) -> None:
        with self._lock:
            self._last = ValidationResult(
                "failed",
                time.time(),
                "failed",
                [ValidationCheck("validation_runner", STATUS_FAIL, detail)],
            )

    def _snapshot(self) -> dict[str, Any]:
        if self._sm is None:
            return {}
        try:
            return self._sm.snapshot()
        except Exception:
            return {}

    def _check_singleton(self) -> tuple[str, str]:
        status, detail = self._check_process(self._bridge_pattern, "bridge")
        if status != STATUS_PASS:
            return status, detail
        count = _pgrep_count(self._bridge_pattern)
        if count == 1:
            return STATUS_PASS, "one bridge process"
        if count <= 0:
            return STATUS_FAIL, "bridge process not found"
        return STATUS_FAIL, f"{count} bridge processes"

    def _check_process(self, pattern: str, label: str) -> tuple[str, str]:
        count = _pgrep_count(pattern)
        if count > 0:
            return STATUS_PASS, f"{label} process found"
        return STATUS_FAIL, f"{label} process not found"

    def _check_soundswitch(self) -> tuple[str, str]:
        if bool(getattr(self._conn, "_connected", False)):
            return STATUS_PASS, "connected"
        return STATUS_WARN, "not connected"

    def _check_memory(self, add) -> None:
        snap = self._snapshot()
        decks = snap.get("deck", {})
        for deck in (1, 2):
            pos = self._pos_cache.get(deck)
            deck_state = decks.get(str(deck)) or decks.get(deck) or {}
            loaded = bool(deck_state.get("filepath"))
            playing = bool(deck_state.get("playing"))
            name = f"memory_deck_{deck}"
            if pos is None:
                add(name, STATUS_WARMING if loaded or playing else STATUS_NA, "no memory snapshot")
            elif pos.is_stale():
                add(name, STATUS_FAIL if playing else STATUS_WARN, f"stale age={pos.age_s():.1f}s")
            else:
                add(name, STATUS_PASS, f"fresh age={pos.age_s():.1f}s")

    def _check_live_bpm(self, add) -> None:
        snap = self._snapshot()
        decks = snap.get("deck", {})
        for deck in (1, 2):
            deck_state = decks.get(str(deck)) or decks.get(deck) or {}
            loaded = bool(deck_state.get("filepath"))
            playing = bool(deck_state.get("playing"))
            status = self._live_bpm.get_status(deck) if self._live_bpm is not None else None
            summary = self._live_bpm.get_summary(deck) if self._live_bpm is not None else None
            name = f"live_bpm_deck_{deck}"
            if status is not None and getattr(status, "valid", False):
                add(name, STATUS_PASS, f"{status.bpm:.2f} source={status.source}")
            elif playing:
                add(name, STATUS_WARN, "playing but no validated live BPM")
            elif loaded:
                source = getattr(summary, "current_source", "unknown") if summary is not None else "unknown"
                add(name, STATUS_WARMING, f"loaded, awaiting validation source={source}")
            else:
                add(name, STATUS_NA, "deck idle")

    def _check_autoloop(self, add) -> None:
        snap = self._snapshot()
        mode = snap.get("lighting_mode", "idle")
        if mode != "autoloop":
            add("autoloop", STATUS_NA, f"mode={mode}")
            return
        if snap.get("autoloop_arm_pending"):
            add("autoloop", STATUS_WARMING, "arm pending")
        else:
            add("autoloop", STATUS_PASS, "autoloop active")

    def _check_scripted(self, add) -> None:
        count = len(self._scripted_registry)
        snap = self._snapshot()
        scripted_loaded = any((d.get("scripted_id") or 0) > 0 for d in (snap.get("deck") or {}).values())
        if count > 0:
            add("scripted_registry", STATUS_PASS, f"{count} registered")
        elif scripted_loaded:
            add("scripted_registry", STATUS_FAIL, "scripted deck loaded but registry empty")
        else:
            add("scripted_registry", STATUS_NA, "no scripted tracks registered")

    def _check_queue(self) -> tuple[str, str]:
        send_q = getattr(self._conn, "_send_q", None)
        if send_q is None:
            return STATUS_WARN, "queue unavailable"
        size = send_q.qsize()
        maxsize = send_q.maxsize or 0
        drops = int(getattr(self._conn, "_drop_count", 0))
        if maxsize and size >= maxsize * 0.8:
            return STATUS_WARN, f"queue high {size}/{maxsize} drops={drops}"
        return STATUS_PASS, f"queue {size}/{maxsize} drops={drops}"

    def _check_laser(self, add) -> None:
        """Placeholder laser checks — all not_applicable until LaserDirector is wired in."""
        _laser_checks = (
            "laser_config",
            "laser_safe_scene",
            "laser_emergency_scene",
            "laser_personality_refs",
            "laser_midi_dependency",
            "laser_midi_port",
            "laser_midi_queue",
        )
        for name in _laser_checks:
            add(name, STATUS_NA, "not_configured")


def _pgrep_count(pattern: str) -> int:
    try:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=1)
    except Exception:
        return 0
    if result.returncode != 0:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])
