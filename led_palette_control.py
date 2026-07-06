"""Stream Deck palette-control coordinator.

State mutation is owned by StateManager's thread.  The writer thread only
serializes already-built snapshots to the feedback file.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Optional

from .led_color_engine import _p_to_rgb
from .models import BridgeEvent, Ev
from .runtime_status import atomic_write_json

log = logging.getLogger("rbss.palette_control")

# An override-fade completes on this beat grid measured from the last phrase
# marker (operator rule 2026-07-05: "finish by the next phrase or at a 32-beat
# boundary from the last phrase marker"). PHRASE_ANCHOR_BEATS is 64, so the
# in-phrase grid points are the phrase marker, its midpoint (+32), and the next
# phrase (+64): the fade completes within 32 beats of the marker and always
# lands on a phrase-relative boundary, never a fixed 32 beats from where the
# press landed. (It can run slightly past 32 beats from the *press* when the
# phrase marker sits a few beats ahead of the playhead at a rearm — still a real
# phrase boundary, still self-correcting.)
FADE_GRID_BEATS = 32.0

# The real operator-facing feedback path the Stream Deck DECK script
# (streamdeck/streamdeck_midi.py) reads. Ownership contract: only the real
# bridge process pins this into RBSS_PALETTE_STATE_PATH -- __main__.main(),
# immediately after it wins the single-instance flock, long before any
# StateManager/LedPaletteControl is constructed. Every other construction
# path (ad-hoc verification scripts, direct test-module runs, subagent
# scratch runs) never sets that env var and falls through to a per-pid
# throwaway file in _resolve_palette_state_path() below, so a stray process
# is structurally unable to write the live file and fight the real bridge's
# PaletteFeedbackWriter over it (2026-07-04 ghost-writer incident).
LIVE_PALETTE_STATE_PATH = "/tmp/rb_ss_bridge_v2_palette_state.json"

# Backward-compat name: no importer outside this module reads it (checked
# via rg 2026-07-04). Nothing below defaults to it any more -- see
# _resolve_palette_state_path().
PALETTE_STATE_PATH = LIVE_PALETTE_STATE_PATH


def _resolve_palette_state_path() -> str:
    """Resolve the palette feedback path at CONSTRUCTION time, never at
    import time -- at import time no caller has had a chance to set
    RBSS_PALETTE_STATE_PATH yet, which is exactly how a stray process used
    to inherit the literal live path. Honors an explicit env override
    first (set by __main__.main() for the real bridge, or by an operator /
    tests/__init__.py for anything else); otherwise falls back to a per-pid
    throwaway so concurrent stray processes can't even collide with each
    other, let alone the live bridge.
    """
    override = os.environ.get("RBSS_PALETTE_STATE_PATH")
    if override:
        return override
    return os.path.join(tempfile.gettempdir(), f"rbss_palette_state_{os.getpid()}.json")


class PaletteFeedbackWriter(threading.Thread):
    def __init__(
        self,
        path: str | None = None,
        *,
        debounce_s: float = 0.10,
        heartbeat_s: float | None = None,
    ) -> None:
        super().__init__(name="palette-feedback-writer", daemon=True)
        # None (rather than a live-path default) so a caller that ever
        # forgets to pass a path -- there is none in this repo today, but
        # this class is public -- gets a per-pid throwaway, never the live
        # operator feedback file.
        self._path = path or _resolve_palette_state_path()
        self._debounce_s = debounce_s
        # When set, the last payload is rewritten every heartbeat_s while idle
        # so mtime-based staleness checks (streamdeck_midi FEEDBACK_STALE_S)
        # keep reading the file as live even when nothing changes. The
        # learned-store writer instance passes None: a persistent store must
        # only be written on real mutations.
        self._heartbeat_s = heartbeat_s
        self._event = threading.Event()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._pending: dict[str, Any] | None = None
        self._last_payload: dict[str, Any] | None = None
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
            fired = self._event.wait(timeout=self._heartbeat_s)
            self._event.clear()
            if self._stop_event.is_set():
                return
            if fired:
                time.sleep(self._debounce_s)
            with self._lock:
                payload = self._pending
                self._pending = None
            if payload is None:
                # Heartbeat wake with nothing new: refresh mtime with the last
                # written content (never invents a payload before first submit).
                payload = self._last_payload
            if payload is None:
                continue
            self._write_once(payload)

    def _write_once(self, payload: dict[str, Any]) -> None:
        # Log transitions, not ticks: one line when writes start failing, one
        # when they recover (a steady failure otherwise blanks every feedback
        # pad within FEEDBACK_STALE_S with a single log line ever).
        try:
            atomic_write_json(self._path, payload)
        except Exception as exc:
            if not self._logged_error:
                log.warning("[PALETTE] feedback_write_failed err=%s", type(exc).__name__)
                self._logged_error = True
            return
        self._last_payload = payload
        if self._logged_error:
            log.info("[PALETTE] feedback_write_recovered")
            self._logged_error = False


class LedPaletteControl:
    def __init__(
        self,
        *,
        engine: Any,
        led_event_sink: Callable[[BridgeEvent], None],
        get_abs_beat: Callable[[], Optional[float]],
        get_phrase_anchor: Callable[[float], Optional[float]],
        get_laser_blackout: Callable[[], bool],
        get_laser_solo: Callable[[], str] | None = None,
        get_static_held: Callable[[], tuple] | None = None,
        palette_notes: Mapping[str, int] | None = None,
        control_notes: Mapping[str, int] | None = None,
        feedback_path: str | None = None,
        long_press_s: float = 0.5,
    ) -> None:
        self._engine = engine
        self._led_event_sink = led_event_sink
        self._get_abs_beat = get_abs_beat
        self._get_phrase_anchor = get_phrase_anchor
        self._get_laser_blackout = get_laser_blackout
        # Pull, not push (mirrors get_laser_blackout): the drop presentation
        # policy's CURRENT arm/pending/active state is read fresh on every
        # publish, so a state change is picked up by the next maybe_publish()
        # tick without a dedicated setter call to remember to make.
        self._get_laser_solo = get_laser_solo
        self._get_static_held = get_static_held
        self._palette_notes = dict(palette_notes or {})
        self._control_notes = dict(control_notes or {})
        self._long_press_s = float(long_press_s)
        self._pad_down: dict[str, float] = {}
        self._led_muted = False
        self._rainbow = False
        self._seq = 0
        self._last_input_healthy = True
        self._last_feedback_body: dict[str, Any] | None = None
        self._logged_snapshot_error = False
        # Resolve at construction time, not import time: only main() (the
        # real bridge, after it wins the single-instance lock) pins
        # RBSS_PALETTE_STATE_PATH to LIVE_PALETTE_STATE_PATH before this
        # constructor ever runs; every other caller (ad-hoc scripts, tests,
        # a StateManager built by a stray process) falls through to a
        # per-pid throwaway -- see _resolve_palette_state_path().
        resolved_feedback_path = feedback_path or _resolve_palette_state_path()
        self._writer = PaletteFeedbackWriter(resolved_feedback_path, heartbeat_s=5.0)
        self._writer.start()
        self.publish_feedback()

    def stop(self) -> None:
        self._writer.stop()

    def handle_event(self, ev: BridgeEvent) -> None:
        if ev.kind == Ev.LED_PALETTE_PAD:
            raw_intent = ev.payload.get("intent")
            raw_phase = ev.payload.get("phase")
            self._handle_palette(
                str(ev.payload.get("name") or ""),
                raw_intent if isinstance(raw_intent, str) else "",
                raw_phase if raw_phase in ("down", "up") else None,
            )
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
            "laser_solo": str(self._get_laser_solo()) if self._get_laser_solo is not None else "off",
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
            "gesture": 2,
            "long_press_s": self._long_press_s,
            **self.snapshot(),
            "palettes": self._palette_payload(),
            "controls": self._control_payload(),
            "static_held": sorted(
                (
                    {"channel": int(c), "note": int(n), "kind": str(k)}
                    for (c, n, k) in (self._get_static_held() if self._get_static_held else ())
                ),
                key=lambda row: (row["channel"], row["note"]),
            ),
        }
        if not force and body == self._last_feedback_body:
            return
        self._last_feedback_body = body
        self._seq += 1
        payload = {**body, "seq": self._seq}
        self._writer.submit(payload)

    def _handle_palette(self, name: str, intent: str, phase: str | None = None) -> None:
        if intent:
            self._handle_palette_intent(name, intent)
            return
        if phase in ("down", "up"):
            if not name or self._rainbow:
                return
            if phase == "down":
                self._pad_down[name] = time.monotonic()
                return
            # Accepted edges: Rainbow can eat a release, full Rainbow blips can
            # still count as holds, and a track boundary may consume a tap's
            # queue before release; all are bounded/operator-visible.
            now = time.monotonic()
            held_s = now - self._pad_down.pop(name, now)
            if held_s >= self._long_press_s:
                self._handle_palette_hold(name)
            else:
                self._handle_palette_tap(name)
            return
        self._handle_palette_tap(name)

    def _handle_palette_intent(self, name: str, intent: str) -> None:
        if not name or (self._rainbow and name != "rainbow"):
            return
        if intent == "queue":
            self._engine.queue_palette(name)
            return
        if intent == "override" or self._engine.snapshot().get("queued_palette") == name:
            self._override_palette_now(name)
            return
        self._engine.queue_palette(name)

    def _handle_palette_tap(self, name: str) -> None:
        if not name or self._rainbow:
            return
        snap = self._engine.snapshot()
        if snap.get("lock") and snap.get("current_palette") == name:
            self._engine.unlock()
        elif snap.get("queued_palette") == name:
            self._engine.unqueue_palette(name)
        else:
            self._engine.queue_palette(name)

    def _handle_palette_hold(self, name: str) -> None:
        snap = self._engine.snapshot()
        if snap.get("lock") and snap.get("current_palette") == name:
            return
        self._override_palette_now(name)
        self._engine.lock()

    def _override_palette_now(self, name: str) -> None:
        start = self._get_abs_beat()
        if start is None:
            # No beat authority (idle / nothing playing): there is no beat to
            # sync a fade to, and advance_fade only ticks while a deck plays.
            self._engine.set_palette(name)
            return
        start_beat = float(start)
        anchor = self._get_phrase_anchor(start_beat)
        if anchor is not None and anchor > start_beat:
            # Land on the phrase grid: the next phrase anchor is one grid step
            # (the phrase marker + 64); its midpoint (anchor - 32 = marker + 32)
            # is the other. Finish at the midpoint if the press is in the first
            # half of the phrase, else at the next phrase — never press + 32.
            midpoint = anchor - FADE_GRID_BEATS
            end_beat = midpoint if start_beat < midpoint else anchor
        else:
            # No phrase authority: fall back to a plain grid-length fade.
            end_beat = start_beat + FADE_GRID_BEATS
        if end_beat <= start_beat:
            end_beat = start_beat + FADE_GRID_BEATS
        self._engine.override_palette(name, start_beat=start_beat, end_beat=end_beat)

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
        for name, palette in palettes.items():
            note = self._palette_notes.get(name)
            if note is None:
                # Not a pad (e.g. the rainbow-type mode target): never invent
                # notes — an invented note can collide with a control pad.
                continue
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
                "ramp": [list(c) for c in self._palette_ramp(name, palette)],
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

    def _palette_ramp(self, name: str, palette: Any, samples: int = 8) -> list[tuple[int, int, int]]:
        """Colors sampled across the palette's own p-interval — the pad shows
        the palette's actual RANGE as a gradient, not one center point."""
        if getattr(palette, "type", "journey") == "fixed_rgb" and getattr(palette, "rgb", None):
            return [tuple(palette.rgb)] * samples
        try:
            lo, hi = self._engine._palette_p_interval(name)
            config = self._engine._config
            stops = self._engine._stop_positions
            return [
                _p_to_rgb(lo + (hi - lo) * i / (samples - 1), config.scale_stops, stops)
                for i in range(samples)
            ]
        except Exception:
            return [self._palette_rgb(name, palette)] * samples

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
