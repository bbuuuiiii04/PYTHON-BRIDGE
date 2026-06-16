"""Actor thread that sustains Govee realtime frames off the bridge hot path."""
from __future__ import annotations

import logging
import os as _os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .beat_sync_engine import BeatSyncEngine, MAX_MANUAL_PENDING
from .govee_frame_renderer import (
    GoveeFrameRenderer,
    default_sync_mode,
    default_beat_division,
    is_comet_effect,
    resolve_fade,
)
from .led_models import BeatAnchor

_COLOR_SIG_KEYS = frozenset({
    "color", "color2", "color_a", "color_b",
    "color_from", "color_to",
    "color_a_from", "color_a_to",
    "color_b_from", "color_b_to",
    "fade_beats", "gradient_stops",
    "slot_colors", "slot_colors_from", "slot_colors_to"
})

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class EffectSpec:
    effect_name: str
    params: Mapping[str, Any]
    seed: int
    applied_monotonic: float
    sync_mode: str = ""
    beat_division: float = 0.0


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
        self._engine = BeatSyncEngine()
        self._pending_manual = 0
        self._engine_status = {
            "sync_mode": "", "beat_division": 0.0,
            "instance_count": 0, "spawn_count": 0,
        }
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
        self._color_signature: tuple[Any, ...] | None = None
        self._color_applied_abs_beat: float | None = None
        self._active_origin_beat = 0.0
        self._active_applied_monotonic = 0.0
        self._idle_since: float | None = None
        self._last_frame: list[RGB] | None = None
        self._frame_index = 0
        self._last_error = ""

        # WI-6 reconcile: track when a cloud DIY dispatch may have displaced razer mode
        self._reconcile_enabled: bool = _os.environ.get("RBSS_LED_RT_RECONCILE", "1") != "0"
        self._reconcile_window_s: float = 5.0  # overridden by note_cloud_dispatch caller
        self._reconcile_interval_s: float = 1.0  # overridden by note_cloud_dispatch caller
        self._cloud_suspect_until: float = 0.0
        self._last_activate_mono: float = 0.0
        self._rt_reconcile_count: int = 0
        self._log = logging.getLogger("govee_realtime_runner")

    def set_beat_provider(self, provider: Callable[[], Optional[BeatAnchor]] | None) -> None:
        with self._lock:
            self._beat_provider = provider

    def set_desired(self, spec: EffectSpec | None) -> None:
        with self._lock:
            self._desired_spec = spec
            if spec is not None:
                self._emergency.clear()

    def fire_trigger(self) -> None:
        with self._lock:
            self._pending_manual = min(self._pending_manual + 1, MAX_MANUAL_PENDING)

    def note_cloud_dispatch(self, now: float, *, window_s: float = 5.0, interval_s: float = 1.0) -> None:
        """Signal that a cloud DIY command was just dispatched.

        Opens a reconcile window during which _tick_once will periodically
        re-assert razer activate() to self-heal from a late cloud command that
        might flip the strip out of razer mode.

        Only takes effect when RBSS_LED_RT_RECONCILE=1 (default).
        """
        with self._lock:
            self._reconcile_window_s = float(window_s)
            self._reconcile_interval_s = max(0.01, float(interval_s))
            self._cloud_suspect_until = float(now) + self._reconcile_window_s


    def emergency_stop(self) -> None:
        self._emergency.set()

    def force_deactivate(self) -> None:
        """Synchronously blackout and deactivate the transport.

        Called by the dispatch coordinator when transitioning from realtime to
        cloud DIY.  Unlike the normal idle grace period (0.25 s of stale
        frames), this cuts the realtime stream immediately so the cloud command
        doesn't fight the UDP stream for the strip.
        """
        with self._lock:
            self._desired_spec = None
        # Synchronously stop the transport so no more frames leak out while
        # the runner thread processes the emergency on its next tick.
        if self._active:
            self._transport.blackout()
            self._transport.deactivate()
        with self._lock:
            self._active = False
            self._active_signature = None
            self._color_signature = None
            self._color_applied_abs_beat = None
            self._idle_since = None
            self._pending_manual = 0
            self._engine_status = {"sync_mode": "", "beat_division": 0.0, "instance_count": 0, "spawn_count": 0}
            self._desired_spec = None
        self._last_frame = None
        self._engine.reset()
        self._publish_engine_status(cleared=True)

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
        with self._lock:
            self._active = False
            self._active_signature = None
            self._color_signature = None
            self._color_applied_abs_beat = None
            self._idle_since = None
            self._pending_manual = 0
            self._engine_status = {"sync_mode": "", "beat_division": 0.0, "instance_count": 0, "spawn_count": 0}
            self._desired_spec = None
        self._last_frame = None
        self._engine.reset()
        self._publish_engine_status(cleared=True)
        return thread is None or not thread.is_alive()

    def status(self) -> dict[str, Any]:
        with self._lock:
            desired = self._desired_spec.effect_name if self._desired_spec is not None else ""
            provider_bound = self._beat_provider is not None
            active = self._active
            active_effect = (
                str(self._active_signature[0])
                if self._active_signature is not None
                else ""
            )
            frame_index = self._frame_index
            idle_since = self._idle_since or 0.0
            last_error = self._last_error
            engine_status = dict(self._engine_status)
            pending_manual = self._pending_manual
            rt_reconcile_count = self._rt_reconcile_count
        transport_status = {}
        status = getattr(self._transport, "status", None)
        if callable(status):
            transport_status = status()
        return {
            "active": active,
            "provider_bound": provider_bound,
            "desired_effect": desired,
            "active_effect": active_effect,
            "frame_index": frame_index,
            "idle_since": idle_since,
            "last_error": last_error,
            "transport": transport_status,
            **engine_status,
            "pending_manual": pending_manual,
            "rt_reconcile_count": rt_reconcile_count,
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

        # WI-6 reconcile: if a cloud DIY may have flipped the device out of razer
        # mode, periodically re-assert activate() while we are still active.
        # Gated by RBSS_LED_RT_RECONCILE (default ON).
        if (
            self._active and self._desired_spec is not None
            and self._reconcile_enabled
            and now < self._cloud_suspect_until
            and (now - self._last_activate_mono) >= self._reconcile_interval_s
        ):
            self._transport.activate()
            self._last_activate_mono = now
            with self._lock:
                self._rt_reconcile_count += 1
            self._log.info("[RT] reconcile-reactivate now=%.3f", now)

        with self._lock:
            spec = self._desired_spec

        permitted = bool(
            spec is not None
            and anchor is not None
            and anchor.permitted
            and anchor.playing
            and anchor.bpm > 0.0
        )
        if spec is None:
            self._idle_tick(now)
            return
        if not permitted:
            # Paused / momentarily unpermitted: let any launched comet finish its flight
            # on its own locked clock (free-running, untied to the beat grid). No new
            # spawns while paused. When the last comet expires, fall through to idle.
            if self._active and is_comet_effect(spec.effect_name) and self._engine.instance_count > 0:
                instances = self._engine.animate(float(now))
                frame = self._compose_frame(spec, instances, abs_pos=None, anchor_beat=None)
                if self._emergency.is_set():
                    self._emergency_teardown()
                    return
                sent_ok = self._transport.send_frame(frame)
                self._last_frame = frame
                with self._lock:
                    self._last_error = "" if sent_ok else "transport_send_failed"
                    self._frame_index += 1
                    self._idle_since = None
                self._publish_engine_status(cleared=False)
                return
            self._idle_tick(now)
            return

        assert anchor is not None
        abs_pos = float(anchor.abs_beat_pos) + (
            max(0.0, float(now) - float(anchor.captured_monotonic))
            * (float(anchor.bpm) / 60.0)
        )

        motion_sig, color_sig = self._signature(spec)
        if motion_sig != self._active_signature:
            mode = spec.sync_mode or default_sync_mode(spec.effect_name)
            division = spec.beat_division if spec.beat_division > 0 else default_beat_division(spec.effect_name)
            with self._lock:
                self._active_signature = motion_sig
                self._active_applied_monotonic = float(now)
                self._idle_since = None
            self._engine.configure(
                effect_name=spec.effect_name,
                sync_mode=mode,
                beat_division=division,
                params=spec.params,
                seed=spec.seed,
                now=float(now),
                abs_beat=abs_pos,
                bpm=float(anchor.bpm),
            )

        if color_sig != self._color_signature:
            self._color_signature = color_sig
            self._color_applied_abs_beat = abs_pos

        if not self._active:
            self._transport.activate()
            self._transport.set_brightness(100)
            self._last_activate_mono = now
            with self._lock:
                self._active = True

        with self._lock:
            pending = self._pending_manual
            self._pending_manual = 0
        for _ in range(pending):
            self._engine.fire_manual(float(now), abs_pos, float(anchor.bpm))

        instances = self._engine.on_tick(abs_pos, float(now), float(anchor.bpm))
        frame = self._compose_frame(spec, instances, abs_pos=abs_pos, anchor_beat=self._color_applied_abs_beat)

        if self._emergency.is_set():
            self._emergency_teardown()
            return
        sent_ok = self._transport.send_frame(frame)
        self._last_frame = frame
        with self._lock:
            self._last_error = "" if sent_ok else "transport_send_failed"
            self._frame_index += 1
        self._publish_engine_status(cleared=False)

    def _compose_frame(self, spec: EffectSpec, instances: list, abs_pos: float | None = None, anchor_beat: float | None = None) -> list[RGB]:
        # Runs on the runner thread; reading self._engine here is safe.
        segments = self._segments
        if not instances:
            return self._renderer.blank(segments)
        params = resolve_fade(spec.params, abs_pos, anchor_beat)
        if is_comet_effect(spec.effect_name):
            # Comet effects always render through the traveling-head primitive.
            # In retrigger/continuous there is only one instance; overlap folds
            # the active comet heads together.
            width = float(params.get("width", 0.8))
            direction = self._engine.direction
            frames = [
                self._renderer.render_comet(
                    spec.effect_name,
                    progress=ir.progress,
                    segments=segments,
                    width=width,
                    direction=direction,
                    params=params,
                )
                for ir in instances
            ]
            return self._renderer.fold_additive(frames, segments)
        ir = instances[0]
        return self._renderer.render(
            spec.effect_name,
            beat_pos=ir.local_beat,
            local_t=ir.local_t,
            frame_index=self._frame_index,
            params=params,
            segments=segments,
            seed=spec.seed ^ ir.bucket,
        )

    def _publish_engine_status(self, *, cleared: bool) -> None:
        # Called ONLY from the runner thread. Publishes a lock-guarded snapshot that
        # status() (a different thread) reads, so status never touches the engine.
        if cleared:
            snap = {"sync_mode": "", "beat_division": 0.0,
                    "instance_count": 0, "spawn_count": self._engine.spawn_count}
        else:
            snap = {
                "sync_mode": self._engine.mode,
                "beat_division": self._engine.division,
                "instance_count": self._engine.instance_count,
                "spawn_count": self._engine.spawn_count,
            }
        with self._lock:
            self._engine_status = snap

    def _idle_tick(self, now: float) -> None:
        if not self._active:
            with self._lock:
                self._idle_since = None
            return
        if self._idle_since is None:
            with self._lock:
                self._idle_since = now
        if now - self._idle_since >= self._grace_s:
            self._transport.deactivate()
            with self._lock:
                self._active = False
                self._active_signature = None
                self._color_signature = None
                self._color_applied_abs_beat = None
                self._idle_since = None
                self._pending_manual = 0
            self._engine.reset()
            self._publish_engine_status(cleared=True)
            return
        if self._last_frame is not None:
            self._transport.send_frame(self._last_frame)

    def _emergency_teardown(self) -> None:
        if self._active:
            self._transport.blackout()
            self._transport.deactivate()
        self._last_frame = None
        with self._lock:
            self._active = False
            self._active_signature = None
            self._color_signature = None
            self._color_applied_abs_beat = None
            self._idle_since = None
            self._desired_spec = None
            self._pending_manual = 0
        self._engine.reset()
        self._publish_engine_status(cleared=True)

    def _signature(self, spec: EffectSpec) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
        motion_params = tuple(sorted((str(k), repr(v)) for k, v in dict(spec.params).items() if k not in _COLOR_SIG_KEYS))
        color_params = tuple(sorted((str(k), repr(v)) for k, v in dict(spec.params).items() if k in _COLOR_SIG_KEYS))
        motion_sig = (str(spec.effect_name), motion_params, int(spec.seed),
                str(spec.sync_mode), float(spec.beat_division))
        return motion_sig, color_params
