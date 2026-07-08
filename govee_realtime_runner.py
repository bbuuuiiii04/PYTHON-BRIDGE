"""Actor thread that sustains Govee realtime frames off the bridge hot path."""
from __future__ import annotations

import logging
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
from .bridge_fmt import log_changed, log_throttled
from . import bridge_log

_COLOR_SIG_KEYS = frozenset({
    "color", "color2", "color_a", "color_b",
    "color_from", "color_to",
    "color_a_from", "color_a_to",
    "color_b_from", "color_b_to",
    "fade_beats", "gradient_stops",
    "slot_colors", "slot_colors_from", "slot_colors_to"
})

RGB = tuple[int, int, int]

# A cloud DIY scene silently knocks the strip out of razer mode; while streaming,
# re-assert razer this often so a knockout (or a single lost activate) heals in <=2 s.
RAZER_KEEPALIVE_S = 2.0


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
        on_thread_start: Callable[[], None] | None = None,
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
        # Optional per-thread hook (child process sets frame-thread QoS here,
        # AWR-146). Default None = today's behavior exactly.
        self._on_thread_start = on_thread_start
        self._lock = threading.Lock()
        self._desired_spec: EffectSpec | None = None
        self._beat_provider: Callable[[], Optional[BeatAnchor]] | None = None
        self._stop = threading.Event()
        self._emergency = threading.Event()
        self._handoff_deactivate_pending = False
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

        # Razer keepalive + on-demand asserts (replaces WI-6 reconcile). Flags are
        # set by other threads and consumed on the runner thread so no transport I/O
        # ever runs on the caller's thread.
        self._assert_pending = False
        self._brightness_request: int | None = None
        self._brightness_repeat = 0
        self._last_activate_mono: float = 0.0
        self._razer_assert_count = 0
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

    def request_activate_assert(self) -> None:
        """Ask the runner thread to re-assert razer mode on its next tick.

        Used on realtime takeover and blackout so a strip that a cloud scene
        knocked out of razer mode is recovered before the frames matter.
        """
        with self._lock:
            self._assert_pending = True

    def request_brightness(self, value: int) -> None:
        """Ask the runner thread to send a LAN brightness command (any device mode).

        Sent on 2 consecutive ticks — idempotent insurance against a single lost
        UDP packet. This darkens/restores the strip even while a cloud scene plays.
        """
        with self._lock:
            self._brightness_request = int(value)
            self._brightness_repeat = 2

    def emergency_stop(self) -> None:
        self._emergency.set()

    def force_deactivate(self) -> None:
        """Request immediate realtime teardown on the runner thread."""
        with self._lock:
            self._desired_spec = None
            self._handoff_deactivate_pending = True
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
            razer_assert_count = self._razer_assert_count
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
            "razer_assert_count": razer_assert_count,
        }

    def _loop(self) -> None:
        if self._on_thread_start is not None:
            self._on_thread_start()
        interval = 1.0 / float(self._fps)
        next_at = self._time_fn()
        with bridge_log.thread_guard("GoveeRealtimeRunner"):
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

    def _note_rt_send_health(self, sent_ok: bool, was_failing: bool) -> None:
        """Edge-triggered health.govee.rt transition on transport send success/failure."""
        if sent_ok:
            if was_failing and log_changed("govee_rt_ok", True):
                bridge_log.health("govee.rt", "recovered", lvl=logging.INFO)
        elif log_changed("govee_rt_ok", False):
            bridge_log.health("govee.rt", "send failing — can't reach the led strip; retrying")

    def _tick_once(self, anchor: BeatAnchor | None, now: float) -> None:
        # Drain any pending LAN brightness request FIRST — before the emergency
        # short-circuit below (Task 2b). set_brightness works in any device mode,
        # so an operator blackout must darken the strip even with the runner
        # inactive (a cloud look showing) and the emergency Event latched — which
        # would otherwise skip this send for the whole held blackout. Same
        # 2-consecutive-tick resend semantics; the repeat counter is what bounds
        # the send, so this never spams the device while emergency stays latched.
        with self._lock:
            brightness = self._brightness_request
            if brightness is not None:
                self._brightness_repeat -= 1
                if self._brightness_repeat <= 0:
                    self._brightness_request = None
        if brightness is not None:
            self._transport.set_brightness(brightness)

        if self._emergency.is_set():
            self._emergency_teardown()
            return

        # Razer keepalive + on-demand assert (runs on the runner thread only). A cloud
        # DIY scene silently knocks the strip out of razer mode, after which realtime
        # frames — including blackout — are ignored. Re-assert activate() on demand
        # (takeover/blackout) and, while streaming, unconditionally every
        # RAZER_KEEPALIVE_S so a knockout or a lost activate heals in <=2 s.
        with self._lock:
            assert_now = self._assert_pending
            self._assert_pending = False
            desired = self._desired_spec
        if assert_now:
            self._transport.activate()
            self._last_activate_mono = now
            with self._lock:
                self._razer_assert_count += 1
            self._log.debug("[RGB] razer-assert reason=on_demand now=%.3f", now)
        elif (
            self._active and desired is not None
            and (now - self._last_activate_mono) >= RAZER_KEEPALIVE_S
        ):
            self._transport.activate()
            self._last_activate_mono = now
            with self._lock:
                self._razer_assert_count += 1
            self._log.debug("[RGB] razer-assert reason=keepalive now=%.3f", now)

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
                was_failing = bool(self._last_error)
                sent_ok = self._transport.send_frame(frame)
                self._last_frame = frame
                with self._lock:
                    self._last_error = "" if sent_ok else "transport_send_failed"
                    self._frame_index += 1
                    self._idle_since = None
                self._note_rt_send_health(sent_ok, was_failing)
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
            self._log.info("[RGB] activate effect=%s", spec.effect_name)

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
        was_failing = bool(self._last_error)
        sent_ok = self._transport.send_frame(frame)
        self._last_frame = frame
        with self._lock:
            self._last_error = "" if sent_ok else "transport_send_failed"
            self._frame_index += 1
        self._note_rt_send_health(sent_ok, was_failing)
        self._publish_engine_status(cleared=False)
        if log_throttled("rgb_rt_summary", 1.0, now):
            self._log.info(
                "[RGB] summary effect=%s frames=%d err=%s",
                spec.effect_name, self._frame_index, self._last_error or "none",
            )

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
            self._transport.blackout()
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
            self._log.info("[RGB] deactivate reason=idle_grace blackout_sent=1")
            return
        if self._last_frame is not None:
            self._transport.send_frame(self._last_frame)

    def _emergency_teardown(self) -> None:
        with self._lock:
            handoff = self._handoff_deactivate_pending
        if self._active or handoff:
            if not handoff:
                # Operator/pure emergency must hold dark in ANY device mode (even if
                # a cloud scene knocked the strip out of razer mode). Blackout > beauty:
                # a crash mid-blackout leaves the strip dark. The cloud handoff path is
                # untouched — cloud looks must never dim.
                self._transport.set_brightness(0)
            self._transport.blackout()
            self._transport.deactivate()
            if handoff:
                self._log.info("[RGB] deactivate reason=handoff_to_cloud")
        self._last_frame = None
        with self._lock:
            self._active = False
            self._active_signature = None
            self._color_signature = None
            self._color_applied_abs_beat = None
            self._idle_since = None
            self._desired_spec = None
            self._pending_manual = 0
            self._handoff_deactivate_pending = False
        self._engine.reset()
        self._publish_engine_status(cleared=True)

    def _signature(self, spec: EffectSpec) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
        motion_params = tuple(sorted((str(k), repr(v)) for k, v in dict(spec.params).items() if k not in _COLOR_SIG_KEYS))
        color_params = tuple(sorted((str(k), repr(v)) for k, v in dict(spec.params).items() if k in _COLOR_SIG_KEYS))
        motion_sig = (str(spec.effect_name), motion_params, int(spec.seed),
                str(spec.sync_mode), float(spec.beat_division))
        return motion_sig, color_params
