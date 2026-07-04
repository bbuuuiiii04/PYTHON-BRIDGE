"""Stream Deck palette-control coordinator.

State mutation is owned by StateManager's thread.  The writer thread only
serializes already-built snapshots to the feedback file.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Mapping, Optional

from .led_color_engine import _p_to_rgb
from .models import BridgeEvent, Ev
from .runtime_status import atomic_write_json

log = logging.getLogger("rbss.palette_control")

PALETTE_STATE_PATH = "/tmp/rb_ss_bridge_v2_palette_state.json"


class PaletteFeedbackWriter(threading.Thread):
    def __init__(self, path: str = PALETTE_STATE_PATH, *, debounce_s: float = 0.10) -> None:
        super().__init__(name="palette-feedback-writer", daemon=True)
        self._path = path
        self._debounce_s = debounce_s
        self._event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._pending: dict[str, Any] | None = None
        self._logged_error = False

    def submit(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._pending = dict(payload)
        self._event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            self._event.wait()
            self._event.clear()
            if self._stop_event.is_set():
                return
            time.sleep(self._debounce_s)
            with self._lock:
                payload = self._pending
                self._pending = None
            if payload is None:
                continue
            try:
                atomic_write_json(self._path, payload)
            except Exception as exc:
                if not self._logged_error:
                    log.warning("[PALETTE] feedback_write_failed err=%s", type(exc).__name__)
                    self._logged_error = True


class LedPaletteControl:
    def __init__(
        self,
        *,
        engine: Any,
        led_event_sink: Callable[[BridgeEvent], None],
        get_abs_beat: Callable[[], Optional[float]],
        get_phrase_anchor: Callable[[float], Optional[float]],
        get_laser_blackout: Callable[[], bool],
        palette_notes: Mapping[str, int] | None = None,
        control_notes: Mapping[str, int] | None = None,
        feedback_path: str = PALETTE_STATE_PATH,
    ) -> None:
        self._engine = engine
        self._led_event_sink = led_event_sink
        self._get_abs_beat = get_abs_beat
        self._get_phrase_anchor = get_phrase_anchor
        self._get_laser_blackout = get_laser_blackout
        self._palette_notes = dict(palette_notes or {})
        self._control_notes = dict(control_notes or {})
        self._led_muted = False
        self._rainbow = False
        self._seq = 0
        self._last_input_healthy = True
        self._last_feedback_body: dict[str, Any] | None = None
        self._logged_snapshot_error = False
        self._writer = PaletteFeedbackWriter(feedback_path)
        self._writer.start()
        self.publish_feedback()

    def stop(self) -> None:
        self._writer.stop()

    def handle_event(self, ev: BridgeEvent) -> None:
        if ev.kind == Ev.LED_PALETTE_PAD:
            self._handle_palette(str(ev.payload.get("name") or ""), str(ev.payload.get("intent") or ""))
        elif ev.kind == Ev.LED_PALETTE_LOCK_PAD:
            self._handle_lock(str(ev.payload.get("intent") or ""))
        elif ev.kind == Ev.LED_MUTE_PAD:
            self._set_led_mute(not self._led_muted)
        elif ev.kind == Ev.LED_RAINBOW_PAD:
            self._set_rainbow(not self._rainbow)
        self.publish_feedback()

    def on_input_health(self, healthy: bool) -> None:
        healthy = bool(healthy)
        if self._last_input_healthy and not healthy and self._led_muted:
            self._set_led_mute(False)
            self.publish_feedback()
        self._last_input_healthy = healthy

    def snapshot(self) -> dict[str, Any]:
        snap = self._engine_snapshot()
        return {
            "led_blackout": self._led_muted,
            "laser_blackout": bool(self._get_laser_blackout()),
            "laser_solo": "off",
            "rainbow": self._rainbow,
            "lock": bool(snap.get("lock", False)),
            "current_palette": str(snap.get("current_palette", "")),
            "queued_palette": str(snap.get("queued_palette", "")),
            "fading": bool(snap.get("fading", False)),
            "fade_target": str(snap.get("fade_target", "")),
        }

    def publish_feedback(self) -> None:
        self._publish_feedback(force=True)

    def maybe_publish(self) -> None:
        self._publish_feedback(force=False)

    def _publish_feedback(self, *, force: bool) -> None:
        body = {
            "schema": 1,
            **self.snapshot(),
            "palettes": self._palette_payload(),
            "controls": self._control_payload(),
        }
        if not force and body == self._last_feedback_body:
            return
        self._last_feedback_body = body
        self._seq += 1
        payload = {**body, "seq": self._seq}
        self._writer.submit(payload)

    def _handle_palette(self, name: str, intent: str) -> None:
        if not name or (self._rainbow and name != "rainbow"):
            return
        if intent == "queue":
            self._engine.queue_palette(name)
            return
        if intent == "override" or self._engine.snapshot().get("queued_palette") == name:
            start = self._get_abs_beat()
            start_beat = float(start if start is not None else 0.0)
            anchor = self._get_phrase_anchor(start_beat)
            end_beat = min(anchor, start_beat + 32.0) if anchor is not None else start_beat + 32.0
            if end_beat <= start_beat:
                end_beat = start_beat + 32.0
            self._engine.override_palette(name, start_beat=start_beat, end_beat=end_beat)
            return
        self._engine.queue_palette(name)

    def _handle_lock(self, intent: str) -> None:
        if self._rainbow:
            return
        if intent == "lock":
            self._engine.lock()
        elif intent == "unlock":
            self._engine.unlock()
        elif self._engine.snapshot().get("lock"):
            self._engine.unlock()
        else:
            self._engine.lock()

    def _set_led_mute(self, enabled: bool) -> None:
        if self._led_muted == bool(enabled):
            return
        self._led_muted = bool(enabled)
        self._led_event_sink(BridgeEvent(
            kind=Ev.LED_BLACKOUT if self._led_muted else Ev.LED_CLEAR_BLACKOUT,
            deck=0,
            payload={"reason": "led_mute_pad"},
            source="palette_control",
        ))

    def _set_rainbow(self, enabled: bool) -> None:
        self._rainbow = bool(enabled)
        if self._rainbow:
            self._engine.set_mode_override({
                "breakdown": "white_sand",
                "buildup": "white_sand",
                "*": "rainbow",
            })
        else:
            self._engine.clear_mode_override()

    def _palette_payload(self) -> list[dict[str, Any]]:
        config = getattr(self._engine, "_config", None)
        palettes = getattr(config, "palettes", {}) if config is not None else {}
        snap = self._engine_snapshot()
        result: list[dict[str, Any]] = []
        for idx, (name, palette) in enumerate(palettes.items()):
            note = self._palette_notes.get(name, 51 + idx)
            state = "inactive"
            if name == snap.get("current_palette"):
                state = "active"
            if name == snap.get("queued_palette"):
                state = "queued"
            if name == snap.get("fade_target"):
                state = "fading"
            result.append({
                "name": name,
                "note": int(note),
                "rgb": list(self._palette_rgb(name, palette)),
                "state": state,
            })
        return result

    def _engine_snapshot(self) -> dict[str, Any]:
        if self._engine is None:
            return {}
        try:
            snap = self._engine.snapshot()
        except Exception as exc:
            if not self._logged_snapshot_error:
                log.warning("[PALETTE] engine_snapshot_failed err=%s", type(exc).__name__)
                self._logged_snapshot_error = True
            return {}
        return snap if isinstance(snap, dict) else {}

    def _control_payload(self) -> dict[str, dict[str, Any]]:
        snap = self.snapshot()
        definitions = {
            "lock": ("Lock", bool(snap.get("lock"))),
            "led_mute": ("LED Mute", bool(snap.get("led_blackout"))),
            "laser_mute": ("Laser Mute", bool(snap.get("laser_blackout"))),
            "laser_solo": ("Laser Solo", str(snap.get("laser_solo")) != "off"),
            "rainbow": ("Rainbow", bool(snap.get("rainbow"))),
        }
        controls: dict[str, dict[str, Any]] = {}
        for key, (label, active) in definitions.items():
            note = self._control_notes.get(key)
            if note is None:
                continue
            state = "active" if active else "inactive"
            if key == "laser_solo" and str(snap.get("laser_solo")) in ("armed", "pending"):
                state = "queued"
            controls[key] = {
                "name": label,
                "note": int(note),
                "state": state,
            }
        return controls

    def _palette_rgb(self, name: str, palette: Any) -> tuple[int, int, int]:
        if getattr(palette, "type", "journey") == "fixed_rgb" and getattr(palette, "rgb", None):
            return tuple(palette.rgb)
        if getattr(palette, "type", "journey") == "rainbow":
            return (255, 0, 255)
        try:
            p = self._engine._palette_center(name)
            config = self._engine._config
            return _p_to_rgb(p, config.scale_stops, self._engine._stop_positions)
        except Exception:
            return (0, 0, 0)
