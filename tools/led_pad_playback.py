from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..govee_frame_renderer import (
    GoveeFrameRenderer,
    REALTIME_STROBE_EFFECTS,
    default_beat_division,
    default_sync_mode,
)
from ..govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
from ..govee_realtime_transport import GoveeRealtimeDryRunTransport, GoveeRealtimeTransport
from ..led_models import BeatAnchor, LEDConfig
from ..runtime_status import COMMANDS_PATH, STATUS_PATH

log = logging.getLogger("led_pad_playback")


def stable_seed(value: str) -> int:
    digest = hashlib.blake2b(str(value).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False) & 0x7FFFFFFF


class SyntheticClock:
    def __init__(self, *, bpm: float = 128.0, time_fn: Callable[[], float] | None = None) -> None:
        self._time_fn = time_fn or time.monotonic
        self._bpm = float(bpm)
        self._anchor_time = self._time_fn()
        self._anchor_beat = 0.0
        self.playing = False

    @property
    def bpm(self) -> float:
        return self._bpm

    def beat(self) -> float:
        now = self._time_fn()
        return self._anchor_beat + max(0.0, now - self._anchor_time) * self._bpm / 60.0

    def set_bpm(self, bpm: float) -> None:
        bpm = float(bpm)
        if bpm <= 0:
            raise ValueError("bpm must be > 0")
        self._anchor_beat = self.beat()
        self._anchor_time = self._time_fn()
        self._bpm = bpm

    def play(self) -> None:
        self._anchor_time = self._time_fn()
        self.playing = True

    def stop(self) -> None:
        self._anchor_beat = self.beat()
        self._anchor_time = self._time_fn()
        self.playing = False

    def anchor(self) -> BeatAnchor | None:
        if not self.playing:
            return None
        now = self._time_fn()
        return BeatAnchor(
            deck=0,
            abs_beat_pos=self.beat(),
            bpm=self._bpm,
            captured_monotonic=now,
            playing=True,
            permitted=True,
        )


class CueTimer:
    def __init__(self, *, time_fn: Callable[[], float] | None = None) -> None:
        self._time_fn = time_fn or time.monotonic
        self._start_time = 0.0
        self._start_bpm = 128.0
        self._cue_beats = 0.0
        self.loop = True
        self.active = False

    def start(self, *, cue_beats: float, bpm: float, loop: bool) -> None:
        self._start_time = self._time_fn()
        self._start_bpm = max(1e-6, float(bpm))
        self._cue_beats = max(0.0, float(cue_beats))
        self.loop = bool(loop)
        self.active = self._cue_beats > 0

    def set_bpm(self, bpm: float) -> None:
        if not self.active:
            self._start_bpm = float(bpm)
            return
        elapsed_beats = max(0.0, self._time_fn() - self._start_time) * self._start_bpm / 60.0
        self._start_time = self._time_fn() - (elapsed_beats * 60.0 / max(1e-6, float(bpm)))
        self._start_bpm = float(bpm)

    def should_stop(self) -> bool:
        if not self.active or self.loop:
            return False
        elapsed_beats = max(0.0, self._time_fn() - self._start_time) * self._start_bpm / 60.0
        return elapsed_beats >= self._cue_beats

    def clear(self) -> None:
        self.active = False


class OwnershipGate:
    def __init__(
        self,
        *,
        status_path: Path | str = STATUS_PATH,
        command_path: Path | str = COMMANDS_PATH,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        appender: Callable[[dict[str, Any]], None] | None = None,
        status_reader: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self.status_path = Path(status_path)
        self.command_path = Path(command_path)
        self._time_fn = time_fn or time.time
        self._sleep_fn = sleep_fn or time.sleep
        self._appender = appender or self._append_command_file
        self._status_reader = status_reader or self._read_status_file
        self.state = "free"
        self.last_warning = ""

    def _append_command_file(self, command: dict[str, Any]) -> None:
        raw = json.dumps(command, separators=(",", ":")) + "\n"
        fd = os.open(str(self.command_path), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fp:
            fp.write(raw)

    def _read_status_file(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _fresh_status(self) -> dict[str, Any] | None:
        data = self._status_reader()
        if not data:
            self.state = "free" if self.state != "pad_owned" else self.state
            return None
        written_at = float(data.get("written_at", 0.0) or 0.0)
        if not written_at or self._time_fn() - written_at > 5.0:
            self.state = "free" if self.state != "pad_owned" else self.state
            return None
        return data

    @staticmethod
    def _blackout_latched(data: dict[str, Any]) -> bool:
        led = data.get("led_look_director")
        return isinstance(led, dict) and bool(led.get("emergency_blackout"))

    def refresh(self) -> str:
        data = self._fresh_status()
        if self.state != "pad_owned":
            self.state = "bridge_owned" if data is not None else "free"
        return self.state

    def request_takeover(self) -> None:
        data = self._fresh_status()
        if data is not None:
            self._appender({"cmd": "led_blackout", "reason": "led_pad"})
            self._sleep_fn(1.5)
        self.state = "pad_owned"

    def poll_owned(self) -> None:
        if self.state != "pad_owned":
            return
        data = self._fresh_status()
        if data is not None and not self._blackout_latched(data):
            self._appender({"cmd": "led_blackout", "reason": "led_pad"})
            self.last_warning = "bridge_reasserted_takeover"

    def release(self) -> None:
        if self.state == "pad_owned":
            self._appender({"cmd": "led_clear_blackout"})
        self.state = "free"


class PadPlayback:
    def __init__(
        self,
        config: LEDConfig,
        *,
        dry_run: bool = False,
        renderer: GoveeFrameRenderer | None = None,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        ownership_gate: OwnershipGate | None = None,
    ) -> None:
        target = next((item for item in config.targets.values() if item.realtime.enabled), None)
        if target is None:
            raise ValueError("no realtime-enabled LED target")
        rt = target.realtime
        self._time_fn = time_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._clock = SyntheticClock(time_fn=self._time_fn)
        self._timer = CueTimer(time_fn=self._time_fn)
        self._loop = True
        self._playing_look = ""
        self._last_error = ""
        self._lock = threading.RLock()
        self._ownership = ownership_gate or OwnershipGate(sleep_fn=self._sleep_fn)
        self._runner = GoveeRealtimeRunner(
            GoveeRealtimeDryRunTransport(ip=rt.ip, port=rt.port, segments=rt.segments)
            if dry_run
            else GoveeRealtimeTransport(
                rt.ip,
                port=rt.port,
                segments=rt.segments,
                header_bytes=rt.header_bytes,
                stretch=rt.stretch,
                activate_pt=rt.activate_pt,
                deactivate_pt=rt.deactivate_pt,
            ),
            renderer or GoveeFrameRenderer(),
            segments=rt.segments,
            fps=rt.fps,
            time_fn=self._time_fn,
            sleep_fn=self._sleep_fn,
        )
        self._runner.set_beat_provider(self._clock.anchor)
        self._runner.start()
        self._stop_poll = threading.Event()
        self._poll_thread = threading.Thread(target=self._poll_loop, name="LedPadOwnership", daemon=True)
        self._poll_thread.start()
        atexit.register(self.release)

    @property
    def clock(self) -> SyntheticClock:
        return self._clock

    @staticmethod
    def build_spec(spec: dict[str, Any], now: float) -> EffectSpec:
        effect = str(spec.get("scene_ref") or spec.get("effect_name") or "")
        params = spec.get("params")
        if not isinstance(params, dict):
            params = {}
        look_name = str(spec.get("look_name") or spec.get("name") or effect)
        return EffectSpec(
            effect_name=effect,
            params=dict(params),
            seed=stable_seed(look_name),
            applied_monotonic=now,
            sync_mode=str(params.get("sync_mode") or default_sync_mode(effect)),
            beat_division=float(params.get("beat_division") or default_beat_division(effect)),
        )

    @staticmethod
    def validate_strobe(spec: dict[str, Any]) -> None:
        scene_ref = str(spec.get("scene_ref") or spec.get("effect_name") or "")
        if scene_ref not in REALTIME_STROBE_EFFECTS:
            return
        if not bool(spec.get("allow_strobe")):
            raise ValueError("strobe playback requires look.allow_strobe=true")
        if not bool(spec.get("safety_allow_strobe")):
            raise ValueError("strobe playback requires safety.allow_strobe=true")

    def _poll_loop(self) -> None:
        counter = 0
        while not self._stop_poll.wait(0.25):
            counter = self._poll_once(counter)

    def _poll_once(self, counter: int) -> int:
        self.tick()
        if counter % 8 == 7:
            self._ownership.poll_owned()
            # Yield to the bridge: an already-running pad playback checks ownership
            # only inside play(), so it would otherwise stream forever as a second
            # writer once the bridge comes alive (ghost comet + flicker). If we are
            # playing and NOT in a deliberate pad takeover, and a fresh bridge status
            # says the bridge owns the strip, bow out. "pad_owned" (legit takeover)
            # and "free" (bridge down — pad is the only writer) both keep playing.
            if self._clock.playing and self._ownership.state != "pad_owned":
                if self._ownership.refresh() == "bridge_owned":
                    self.stop()
                    self._ownership.last_warning = "auto_stopped_bridge_active"
                    log.info("[PAD] auto-stopped playback: bridge owns the strip")
        return counter + 1

    def request_takeover(self) -> None:
        self._ownership.request_takeover()

    def play(self, spec: dict[str, Any], *, cue_beats: float, loop: bool) -> None:
        with self._lock:
            self.validate_strobe(spec)
            self._ownership.refresh()
            if self._ownership.state == "bridge_owned":
                raise PermissionError("ownership_required")
            now = self._time_fn()
            self._loop = bool(loop)
            self._timer.start(cue_beats=cue_beats, bpm=self._clock.bpm, loop=loop)
            self._clock.play()
            self._runner.set_desired(self.build_spec(spec, now))
            self._runner.fire_trigger()
            self._playing_look = str(spec.get("look_name") or spec.get("name") or "")
            self._last_error = ""

    def update(self, spec: dict[str, Any]) -> None:
        with self._lock:
            self.validate_strobe(spec)
            if not self._clock.playing:
                return
            self._runner.set_desired(self.build_spec(spec, self._time_fn()))
            self._last_error = ""

    def set_bpm(self, bpm: float) -> None:
        with self._lock:
            self._clock.set_bpm(float(bpm))
            self._timer.set_bpm(float(bpm))

    def set_loop(self, loop: bool) -> None:
        with self._lock:
            self._loop = bool(loop)
            self._timer.loop = bool(loop)

    def tick(self) -> None:
        with self._lock:
            if self._timer.should_stop():
                self.stop()

    def stop(self) -> None:
        with self._lock:
            self._runner.set_desired(None)
            self._clock.stop()
            self._timer.clear()
            self._playing_look = ""

    def emergency_stop(self) -> None:
        with self._lock:
            self._runner.emergency_stop()
            self._runner.force_deactivate()
            self._clock.stop()
            self._timer.clear()
            self._playing_look = ""

    def release(self) -> None:
        with self._lock:
            self.stop()
            self._ownership.release()

    def shutdown(self) -> None:
        self.release()
        self._stop_poll.set()
        self._runner.stop()

    def ownership(self) -> dict[str, Any]:
        return {"state": self._ownership.refresh(), "warning": self._ownership.last_warning}

    def status(self) -> dict[str, Any]:
        self.tick()
        st = self._runner.status()
        st.update(
            {
                "playing": self._clock.playing,
                "playing_look": self._playing_look,
                "bpm": self._clock.bpm,
                "loop": self._loop,
                "last_error": self._last_error,
            }
        )
        return st
