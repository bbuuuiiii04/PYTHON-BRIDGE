"""Actor thread that sustains Govee realtime frames off the bridge hot path."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .govee_frame_renderer import GoveeFrameRenderer
from .led_models import BeatAnchor

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class EffectSpec:
    effect_name: str
    params: Mapping[str, Any]
    seed: int
    applied_monotonic: float


class GoveeRealtimeRunner:
    """Realtime frame runner with non-blocking intent updates."""

    def __init__(
        self,
        transport,
        renderer: GoveeFrameRenderer,
        *,
        segments: int = 20,
        fps: int = 30,
        grace_s: float = 0.25,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._transport = transport
        self._renderer = renderer
        self._segments = max(1, int(segments))
        self._fps = max(1, int(fps))
        self._grace_s = max(0.0, float(grace_s))
        self._time_fn = time_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._lock = threading.Lock()
        self._desired_spec: EffectSpec | None = None
        self._beat_provider: Callable[[], Optional[BeatAnchor]] | None = None
        self._stop = threading.Event()
        self._emergency = threading.Event()
        self._thread: threading.Thread | None = None

        self._active = False
        self._active_signature: tuple[Any, ...] | None = None
        self._active_origin_beat = 0.0
        self._active_applied_monotonic = 0.0
        self._idle_since: float | None = None
        self._last_frame: list[RGB] | None = None
        self._frame_index = 0
        self._last_error = ""

    def set_beat_provider(self, provider: Callable[[], Optional[BeatAnchor]] | None) -> None:
        with self._lock:
            self._beat_provider = provider

    def set_desired(self, spec: EffectSpec | None) -> None:
        with self._lock:
            self._desired_spec = spec
            if spec is not None:
                self._emergency.clear()

    def emergency_stop(self) -> None:
        self._emergency.set()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="GoveeRealtimeRunner",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_s: float = 1.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.001, float(timeout_s)))
        self._transport.blackout()
        self._transport.deactivate()
        self._transport.close()
        return thread is None or not thread.is_alive()

    def status(self) -> dict[str, Any]:
        with self._lock:
            desired = self._desired_spec.effect_name if self._desired_spec is not None else ""
            provider_bound = self._beat_provider is not None
        transport_status = {}
        status = getattr(self._transport, "status", None)
        if callable(status):
            transport_status = status()
        return {
            "active": self._active,
            "provider_bound": provider_bound,
            "desired_effect": desired,
            "active_effect": (
                str(self._active_signature[0])
                if self._active_signature is not None
                else ""
            ),
            "frame_index": self._frame_index,
            "idle_since": self._idle_since or 0.0,
            "last_error": self._last_error,
            "transport": transport_status,
        }

    def _loop(self) -> None:
        interval = 1.0 / float(self._fps)
        next_at = self._time_fn()
        while not self._stop.is_set():
            now = self._time_fn()
            provider = None
            with self._lock:
                provider = self._beat_provider
            anchor = provider() if provider is not None else None
            self._tick_once(anchor, now)
            next_at += interval
            sleep_s = max(0.0, next_at - self._time_fn())
            if sleep_s == 0.0:
                next_at = self._time_fn()
            self._sleep_fn(min(interval, sleep_s))

    def _tick_once(self, anchor: BeatAnchor | None, now: float) -> None:
        if self._emergency.is_set():
            self._emergency_teardown()
            return

        with self._lock:
            spec = self._desired_spec

        permitted = bool(
            spec is not None
            and anchor is not None
            and anchor.permitted
            and anchor.playing
            and anchor.bpm > 0.0
        )
        if spec is None or not permitted:
            self._idle_tick(now)
            return

        assert anchor is not None
        signature = self._signature(spec)
        if signature != self._active_signature:
            self._active_signature = signature
            self._active_origin_beat = float(anchor.abs_beat_pos)
            self._active_applied_monotonic = float(now)
            self._idle_since = None
        if not self._active:
            self._transport.activate()
            self._transport.set_brightness(100)
            self._active = True

        abs_pos = float(anchor.abs_beat_pos) + (
            max(0.0, float(now) - float(anchor.captured_monotonic))
            * (float(anchor.bpm) / 60.0)
        )
        effect_beat = max(0.0, abs_pos - self._active_origin_beat)
        local_t = max(0.0, float(now) - self._active_applied_monotonic)
        frame = self._renderer.render(
            spec.effect_name,
            beat_pos=effect_beat,
            local_t=local_t,
            frame_index=self._frame_index,
            params=spec.params,
            segments=self._segments,
            seed=spec.seed,
        )
        if self._emergency.is_set():
            self._emergency_teardown()
            return
        if not self._transport.send_frame(frame):
            self._last_error = "transport_send_failed"
        else:
            self._last_error = ""
        self._last_frame = frame
        self._frame_index += 1

    def _idle_tick(self, now: float) -> None:
        if not self._active:
            self._idle_since = None
            return
        if self._idle_since is None:
            self._idle_since = now
        if now - self._idle_since >= self._grace_s:
            self._transport.deactivate()
            self._active = False
            self._active_signature = None
            self._idle_since = None
            return
        if self._last_frame is not None:
            self._transport.send_frame(self._last_frame)

    def _emergency_teardown(self) -> None:
        if self._active:
            self._transport.blackout()
            self._transport.deactivate()
        self._active = False
        self._active_signature = None
        self._idle_since = None
        self._last_frame = None
        with self._lock:
            self._desired_spec = None

    def _signature(self, spec: EffectSpec) -> tuple[Any, ...]:
        params_key = tuple(sorted((str(k), repr(v)) for k, v in dict(spec.params).items()))
        return (str(spec.effect_name), params_key, int(spec.seed))
