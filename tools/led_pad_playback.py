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
from .led_pad_mirror import FrameMirrorRing, TeeTransport

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
        if not self.playing:
            return self._anchor_beat
        now = self._time_fn()
        return self._anchor_beat + max(0.0, now - self._anchor_time) * self._bpm / 60.0

    def set_bpm(self, bpm: float) -> None:
        bpm = float(bpm)
        if bpm <= 0:
            raise ValueError("bpm must be > 0")
        if bpm == self._bpm:
            return
        # AWR-275: re-anchor at the CURRENT beat before changing rate so the
        # animation only changes speed — there is no phase jump. beat() right
        # after this call equals beat() right before it (continuity), then the
        # beat count advances at the new bpm.
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
        # A non-loop ("Play once") cue always arms the auto-stop guard — even when
        # the requested length is nonpositive. In that case should_stop() fires
        # immediately (see below) so a one-shot can NEVER stream forever if a bad
        # cue length ever slips past the server clamp (AWR-279 #2 belt). Looping
        # playback never auto-stops regardless of length.
        self.active = (not self.loop) or (self._cue_beats > 0)

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
        if self._cue_beats <= 0:
            # One-shot armed with no runway → stop now, never stream forever.
            return True
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

    def read_fresh_status(self) -> dict[str, Any] | None:
        """Fresh bridge status dict (AWR-261 5s window) with NO ownership side effect.

        Returns the raw status dict when it exists and its ``written_at`` is
        younger than 5s, else None. Used by the tempo-follow path (AWR-275),
        which must read the heartbeat bpm without mutating ownership state.
        """
        data = self._status_reader()
        if not data:
            return None
        written_at = float(data.get("written_at", 0.0) or 0.0)
        if not written_at or self._time_fn() - written_at > 5.0:
            return None
        return data

    def _fresh_status(self) -> dict[str, Any] | None:
        data = self.read_fresh_status()
        if data is None:
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
        # AWR-279 #6: a fresh, deliberate takeover supersedes any stale warning.
        self.last_warning = ""

    def poll_owned(self) -> None:
        if self.state != "pad_owned":
            return
        data = self._fresh_status()
        if data is not None and not self._blackout_latched(data):
            self._appender({"cmd": "led_blackout", "reason": "led_pad"})
            self.last_warning = "bridge_reasserted_takeover"
        else:
            # AWR-279 #6: healthy pad-owned tick (bridge is down, or our blackout is
            # still latched). A prior "bridge reasserted" warning has done its job —
            # let it expire on this next healthy state so it stops masking newer
            # errors instead of sticking forever.
            self.last_warning = ""

    def release(self) -> None:
        if self.state == "pad_owned":
            self._appender({"cmd": "led_clear_blackout", "reason": "led_pad"})
        self.state = "free"
        # AWR-279 #6: releasing back to the bridge clears any stale warning.
        self.last_warning = ""


class PadPlayback:
    # AWR-275: how much the live bpm must move before we re-anchor the clock.
    # The live tap wobbles by a fraction of a bpm; anything at or below this is
    # ignored so the animation does not micro-jitter.
    _FOLLOW_DEBOUNCE_BPM = 0.3

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
        # AWR-275 tempo-follow: the operator's manual Preview tempo is remembered
        # so we can fall back to it the moment the live music stops. While the
        # bridge heartbeat is fresh with a valid bpm, the clock follows the music
        # instead of the manual value.
        self._manual_bpm = float(self._clock.bpm)
        self._following = False
        self._follow_bpm: float | None = None
        self._loop = True
        self._playing_look = ""
        self._last_error = ""
        self._lock = threading.RLock()
        self._ownership = ownership_gate or OwnershipGate(sleep_fn=self._sleep_fn)
        # AWR-269: tee at the transport boundary — runner thread only O(1)-appends.
        self._mirror = FrameMirrorRing(time_fn=self._time_fn)
        inner = (
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
            )
        )
        self._runner = GoveeRealtimeRunner(
            TeeTransport(inner, self._mirror),
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

    @property
    def mirror(self) -> FrameMirrorRing:
        """Pad-process send ring for the live-play mirror (read-only for clients)."""
        return self._mirror

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
        # AWR-275: reuse this existing 0.25s poll (no new loop). Every other tick
        # (~0.5s, the heartbeat write cadence) pull the live bpm and follow it.
        if counter % 2 == 0:
            self._follow_tempo_from_status()
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
        # Manual Preview tempo. Remember it always, but only drive the clock when
        # we are NOT following the live music (AWR-275) — otherwise a manual set
        # would fight the heartbeat.
        with self._lock:
            self._manual_bpm = float(bpm)
            if not self._following:
                self._clock.set_bpm(float(bpm))
                self._timer.set_bpm(float(bpm))

    @staticmethod
    def _extract_status_bpm(status: dict[str, Any] | None) -> float | None:
        """Parse a usable bpm from a bridge status dict, or None.

        The live bpm lives at ``heartbeat.bpm`` (NOT top-level) as a formatted
        string from ``runtime_status._fmt_float`` — and it is the literal string
        ``"unknown"`` when no deck is active. Reject missing/blank/``"unknown"``/
        non-numeric values and anything outside a sane musical range so a bad
        read never yanks the animation to a nonsense tempo.
        """
        if not isinstance(status, dict):
            return None
        heartbeat = status.get("heartbeat")
        if not isinstance(heartbeat, dict):
            return None
        raw = heartbeat.get("bpm")
        if raw is None or raw == "":
            return None
        try:
            bpm = float(raw)  # "unknown" / any non-numeric string raises → rejected
        except (TypeError, ValueError):
            return None
        if bpm <= 0.0 or bpm > 400.0:
            return None
        return bpm

    def apply_tempo_follow(self, status: dict[str, Any] | None) -> None:
        """AWR-275: follow the live music's bpm from the bridge status heartbeat.

        ``status`` is a FRESH bridge status dict (caller applies the AWR-261 5s
        freshness window) or None when the bridge is stale/absent. Fresh + valid
        bpm → the clock and cue timer follow that tempo, debounced so sub-0.3-bpm
        wobble is ignored. Stale/absent → release follow and revert to the
        operator's manual Preview tempo. Beat continuity is preserved by
        SyntheticClock.set_bpm (re-anchor, no phase jump).
        """
        bpm = self._extract_status_bpm(status)
        with self._lock:
            if bpm is not None:
                self._follow_bpm = bpm
                self._following = True
                if abs(bpm - self._clock.bpm) > self._FOLLOW_DEBOUNCE_BPM:
                    self._clock.set_bpm(bpm)
                    self._timer.set_bpm(bpm)
            elif self._following:
                self._following = False
                self._follow_bpm = None
                self._clock.set_bpm(self._manual_bpm)
                self._timer.set_bpm(self._manual_bpm)

    def _follow_tempo_from_status(self) -> None:
        self.apply_tempo_follow(self._ownership.read_fresh_status())

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
                "beat": float(self._clock.beat()),
                "loop": self._loop,
                "last_error": self._last_error,
                # AWR-275 tempo-follow surface for the pad/lab UI mode chip.
                "tempo_source": "following" if self._following else "manual",
                "following": self._following,
                "follow_bpm": self._follow_bpm,
                "manual_bpm": self._manual_bpm,
            }
        )
        return st
