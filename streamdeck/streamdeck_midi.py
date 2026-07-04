#!/usr/bin/env python3
"""Turn an Elgato Stream Deck (Original, 15 keys) into a MIDI controller.

Creates a virtual MIDI port named "Stream Deck" that any app (Rekordbox,
Ableton, SoundSwitch, the bridge) can receive from. Each pad sends a MIDI
note: press = note_on (vel 127), release = note_off. Pads are labelled 1-15
with their note number so you can map them in your DAW.

Run:        python3 streamdeck_midi.py
Self-test:  python3 streamdeck_midi.py --selftest
Quit:       Ctrl-C  (resets the deck on the way out)

Quit Elgato's Stream Deck app first — only one process can hold the device.
"""
import colorsys
import fcntl
import json
import math
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import mido
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Transport.Transport import TransportError
from PIL import Image, ImageDraw, ImageFont

# --- config: change these to taste -------------------------------------------
PORT_NAME = "Stream Deck"   # name other apps will see this controller as
CHANNEL = 2                 # 2 == MIDI channel 3 (chans 1-2 are the lasers')
NOTE_BASE = 36              # pad 0 (top-left) -> note 36 (C1); pads ascend
VELOCITY = 127
LOCK_PATH = "/tmp/streamdeck_midi.lock"
RETRY_SECONDS = 3
PACK_DIR = Path(__file__).resolve().parents[1] / "local" / "soundswitch" / "rbss_canonical_pack"
BINDING_SIDECAR = PACK_DIR.parent / f".{PACK_DIR.name}.midi_bindings.json"
PALETTE_STATE_PATH = Path("/tmp/rb_ss_bridge_v2_palette_state.json")
FEEDBACK_STALE_S = 10.0
# Watchdog: a wedged HID write (or any main-thread hang) freezes pads silently
# and the watcher only respawns dead processes — so a stalled main loop exits
# hard and lets the watcher bring us back. Main loop ticks every 0.5s (3s while
# waiting for the device); 20s of silence means wedged, not busy.
WATCHDOG_STALL_S = 20.0
SHUTDOWN_STALL_S = 10.0
# Drop 1.png .. 15.png in the icons/ folder beside this file to give pads
# custom pictures (else the pad shows its number + note):
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
# -----------------------------------------------------------------------------
_LOCK_FILE = None
_GESTURE_VERSION_WARNED = False


def log(message: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def _acquire_singleton_lock() -> bool:
    global _LOCK_FILE

    _LOCK_FILE = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("streamdeck_midi: another instance is running, exiting")
        _LOCK_FILE.close()
        _LOCK_FILE = None
        return False
    return True


def _fixed_rows(key_count: int = 15) -> list[dict]:
    return [
        {
            "channel": CHANNEL,
            "note": NOTE_BASE + key,
            "target_kind": "static_look",
            "interaction": "press",
            "name": "",
        }
        for key in range(key_count)
    ]


def _rows_from_payload(payload) -> list[dict]:
    rows = payload.get("bindings", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("channel") != CHANNEL or row.get("target_kind") != "static_look":
            continue
        note = row.get("note")
        interaction = row.get("interaction")
        if type(note) is not int or not 0 <= note <= 127 or interaction not in ("press", "toggle"):
            continue
        cleaned.append({
            "channel": CHANNEL,
            "note": note,
            "target_kind": "static_look",
            "interaction": interaction,
            "name": row.get("name") if isinstance(row.get("name"), str) else "",
        })
    cleaned.sort(key=lambda item: (item["channel"], item["note"], item["name"]))
    return cleaned


def load_sidecar(path: Path = BINDING_SIDECAR, key_count: int = 15) -> list[dict]:
    try:
        rows = _rows_from_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        rows = []
    return (rows or _fixed_rows(key_count))[:key_count]


def load_feedback_state(
    path: Path = PALETTE_STATE_PATH,
    *,
    max_age_s: float = FEEDBACK_STALE_S,
    now: float | None = None,
) -> dict | None:
    try:
        stat = path.stat()
        current = time.time() if now is None else now
        if current - stat.st_mtime > max_age_s:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _feedback_palette(feedback: dict | None, name: str) -> dict | None:
    for row in (feedback or {}).get("palettes", []):
        if isinstance(row, dict) and row.get("name") == name and type(row.get("note")) is int:
            return row
    return None


def _palette_row(row: dict) -> dict:
    # Pass-through-by-default: unknown producer fields survive the projection.
    # A whitelist here silently ate the `ramp` field once (incident 2026-07-04).
    out = dict(row)
    out.update({
        "channel": CHANNEL,
        "note": int(row["note"]),
        "target_kind": "palette_pad",
        "interaction": "press",
        "name": str(row.get("name") or ""),
        "rgb": tuple(row.get("rgb") or (0, 0, 0)),
        "ramp": [tuple(c) for c in row.get("ramp") or []],
        "state": str(row.get("state") or "inactive"),
    })
    return out


def _feedback_long_press_s(feedback: dict | None) -> float:
    value = (feedback or {}).get("long_press_s")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0.5


def _warn_once_if_gesture_skew(feedback: dict | None) -> bool:
    global _GESTURE_VERSION_WARNED
    if feedback is None or feedback.get("gesture") == 2:
        return False
    if not _GESTURE_VERSION_WARNED:
        log("palette feedback gesture version is not 2 - rendering without deck-local hold cue")
        _GESTURE_VERSION_WARNED = True
    return True


def _control_row(feedback: dict | None, key: str, fallback_name: str) -> dict | None:
    controls = (feedback or {}).get("controls", {})
    row = controls.get(key) if isinstance(controls, dict) else None
    if not isinstance(row, dict) or type(row.get("note")) is not int:
        return None
    out = dict(row)  # pass-through-by-default, same rationale as _palette_row
    out.update({
        "channel": CHANNEL,
        "note": int(row["note"]),
        "target_kind": key,
        "interaction": "toggle",
        "name": str(row.get("name") or fallback_name),
        "state": str(row.get("state") or "inactive"),
    })
    return out


def compose_layout(feedback: dict | None, sidecar: list[dict], key_count: int = 15) -> list[dict | None]:
    layout: list[dict | None] = [None] * key_count
    if feedback is not None:
        current_palette = str(feedback.get("current_palette") or "")
        locked = bool(feedback.get("lock", False))
        gesture_skew = _warn_once_if_gesture_skew(feedback)
        long_press_s = _feedback_long_press_s(feedback)
        auto_palettes = [
            row for row in feedback.get("palettes", [])
            if isinstance(row, dict)
            and row.get("name") not in ("white_sand", "rainbow")
            and type(row.get("note")) is int
        ][:5]
        for key, row in enumerate(auto_palettes):
            out = _palette_row(row)
            if not gesture_skew:
                out["gesture"] = 2
                out["long_press_s"] = long_press_s
            if locked and out["name"] == current_palette:
                out["locked_current"] = True
            layout[key] = out
        white_sand = _feedback_palette(feedback, "white_sand")
        if white_sand is not None and key_count > 5:
            out = _palette_row(white_sand)
            if not gesture_skew:
                out["gesture"] = 2
                out["long_press_s"] = long_press_s
            if locked and out["name"] == current_palette:
                out["locked_current"] = True
            layout[5] = out
        controls = [
            (7, "led_mute", "LED Mute"),
            (8, "laser_mute", "Laser Mute"),
            (9, "laser_solo", "Laser Solo"),
            (14, "rainbow", "Rainbow"),
        ]
        for key, control, label in controls:
            if key < key_count:
                row = _control_row(feedback, control, label)
                layout[key] = row

    static_rows = list(sidecar)[:4]
    for offset, row in enumerate(static_rows):
        key = 10 + offset
        if key < key_count:
            layout[key] = dict(row)
    return layout


class FeedbackWatch:
    """Deck-side observability for the feedback link (2026-07-04 incident #5:
    a static-only boot printed one plausible 'live' banner, healed silently,
    and masqueraded as an input fault for days). Tracks transitions across
    supervision ticks and reports:
      - feedback lost/restored (the file going stale/missing and back),
      - the composed layout gaining/losing bound keys (with the note range),
      - a bridge restart (feedback seq regression) — the deck-local toggle
        latches predate the restart and must be cleared or they lie."""

    def __init__(self) -> None:
        self._had_feedback: bool | None = None
        self._last_seq: int | None = None
        self._notes: set[int] | None = None

    def observe(self, feedback: dict | None, layout) -> tuple[list[str], bool]:
        messages: list[str] = []
        clear_latches = False
        have = feedback is not None
        if self._had_feedback is None:
            if not have:
                messages.append(
                    "feedback missing/stale - palette+control pads blank (static looks only)")
        elif have != self._had_feedback:
            messages.append(
                "feedback restored" if have
                else "feedback lost (stale or missing) - palette+control pads blank")
        self._had_feedback = have
        if have:
            seq = feedback.get("seq")
            if isinstance(seq, int):
                if self._last_seq is not None and seq < self._last_seq:
                    messages.append(
                        f"bridge restart detected (feedback seq {self._last_seq} -> {seq})"
                        " - clearing pad latches")
                    clear_latches = True
                self._last_seq = seq
        notes = {row["note"] for row in layout
                 if isinstance(row, dict) and type(row.get("note")) is int}
        if self._notes is not None and notes != self._notes:
            gained = len(notes - self._notes)
            lost = len(self._notes - notes)
            span = f"notes {min(notes)}-{max(notes)}" if notes else "no bound notes"
            messages.append(f"layout changed (+{gained}/-{lost} bound keys) - {span}, "
                            f"ch {CHANNEL + 1}")
        self._notes = notes
        return messages, clear_latches


def _pulse_keys(layout) -> set[int]:
    """Keys whose rendering depends on the 0.5s pulse phase."""
    return {key for key, row in enumerate(layout)
            if isinstance(row, dict) and str(row.get("state")) in ("queued", "fading")}


def _changed_keys(prev_layout, next_layout) -> set[int]:
    count = max(len(prev_layout), len(next_layout))
    return {key for key in range(count)
            if (prev_layout[key] if key < len(prev_layout) else None)
            != (next_layout[key] if key < len(next_layout) else None)}


def _watchdog(stop: threading.Event, tick: list[float]) -> None:
    # ponytail: process suicide + watcher respawn, not in-process recovery —
    # a hang here is wedged C-level USB I/O that no Python except can fix.
    while True:
        time.sleep(5.0)
        if stop.is_set():
            time.sleep(SHUTDOWN_STALL_S)
            log(f"shutdown stalled >{SHUTDOWN_STALL_S:.0f}s - hard exit for watcher respawn")
            os._exit(70)
        if time.monotonic() - tick[0] > WATCHDOG_STALL_S:
            log(f"main loop stalled >{WATCHDOG_STALL_S:.0f}s (wedged USB write?)"
                " - hard exit for watcher respawn")
            os._exit(70)


def led_state(sidecar, pressed_set: set[tuple[int, int]]) -> dict[tuple[int, int], bool]:
    if isinstance(sidecar, list):
        rows = sidecar
    else:
        rows = _rows_from_payload(sidecar) or _fixed_rows()
    return {
        (CHANNEL, row["note"]): (CHANNEL, row["note"]) in pressed_set
        for row in rows
        if isinstance(row, dict) and row.get("channel") == CHANNEL and "note" in row
    }


def _row_for_key(key: int, sidecar=None) -> dict | None:
    rows = sidecar if isinstance(sidecar, list) else _fixed_rows()
    if 0 <= key < len(rows):
        return rows[key]
    return None


def note_for(key: int, sidecar=None) -> int | None:
    row = _row_for_key(key, sidecar)
    return int(row["note"]) if row is not None else None


def key_to_message(key: int, pressed: bool, sidecar=None) -> mido.Message:
    """The one piece of logic worth testing: pad -> MIDI message."""
    note = note_for(key, sidecar)
    if note is None:
        raise ValueError("unbound Stream Deck key")
    kind = "note_on" if pressed else "note_off"
    return mido.Message(kind, channel=CHANNEL, note=note,
                        velocity=VELOCITY if pressed else 0)


def _font(size):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        return ImageFont.load_default()


def _fit_text(draw, text: str, center: tuple[float, float], max_width: int, *, size: int, fill):
    font = _font(size)
    while size > 9 and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        size -= 1
        font = _font(size)
    draw.text(center, text, anchor="mm", font=font, fill=fill)


def _row_active(row: dict | None, pressed: bool, pulse: bool = False) -> bool:
    if pressed:
        return True
    state = str((row or {}).get("state") or "")
    if state in ("active", "fading"):
        return True
    if state == "queued":
        return pulse
    return False


def _normal_rgb(value) -> tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(max(0, min(255, int(part))) for part in value[:3])
    return (60, 60, 60)


def _dim(rgb: tuple[int, int, int], value_scale: float = 0.45, floor: float = 0.30) -> tuple[int, int, int]:
    """Dim by HSV value only — hue and saturation survive, so an idle crimson
    pad still reads red instead of crushing to mud (the old linear 0.22)."""
    h, s, v = colorsys.rgb_to_hsv(*(part / 255.0 for part in rgb))
    r, g, b = colorsys.hsv_to_rgb(h, s, max(floor, v * value_scale))
    return (int(r * 255), int(g * 255), int(b * 255))


_BG = (14, 14, 16)          # idle background for glyph pads
_MUTE_RED = (204, 18, 28)   # mixer convention: lit red = muted
_AMBER = (255, 168, 22)     # solo


def _draw_bulb(draw, w, h, on: bool):
    color = (255, 255, 255) if on else (120, 120, 126)
    cx = w / 2
    draw.ellipse([cx - 14, 12, cx + 14, 40], outline=color, width=4,
                 fill=color if on else None)
    draw.rectangle([cx - 7, 42, cx + 7, 50], outline=color, width=3,
                   fill=color if on else None)
    draw.line([cx - 5, 55, cx + 5, 55], fill=color, width=3)


def _draw_beam(draw, w, h, on: bool):
    color = (255, 255, 255) if on else (120, 120, 126)
    ox, oy = 14, h - 14
    draw.ellipse([ox - 5, oy - 5, ox + 5, oy + 5], fill=color)
    for tx, ty in ((w - 12, 12), (w - 12, 30), (w - 30, 12)):
        draw.line([ox, oy, tx, ty], fill=color, width=4)


def _draw_slash(draw, w, h):
    draw.line([12, h - 12, w - 12, 12], fill=(255, 255, 255), width=6)


def _draw_starburst(draw, w, h, color, spikes: int = 8, r_out: float = 26, r_in: float = 11):
    cx, cy = w / 2, h / 2
    points = []
    for i in range(spikes * 2):
        radius = r_out if i % 2 == 0 else r_in
        angle = math.pi * i / spikes - math.pi / 2
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=color)


def _draw_padlock(draw, w, h, locked: bool, color=(255, 255, 255)):
    cx = w / 2
    body = [cx - 16, 32, cx + 16, 56]
    draw.rounded_rectangle(body, radius=6, fill=color if locked else None,
                           outline=color, width=4)
    if locked:
        draw.arc([cx - 11, 12, cx + 11, 40], 180, 360, fill=color, width=5)
        draw.ellipse([cx - 3, 39, cx + 3, 46], fill=_BG)
    else:
        # open shackle: swung to the side
        draw.arc([cx - 2, 10, cx + 24, 38], 180, 340, fill=color, width=5)


def _draw_rainbow_arc(draw, w, h, vivid: bool):
    bands = [(255, 40, 70), (255, 150, 0), (255, 235, 0),
             (0, 210, 90), (0, 160, 255), (170, 80, 255)]
    cx, base = w / 2, h - 14
    radius = 30
    for idx, color in enumerate(bands):
        c = color if vivid else _dim(color, 0.4, 0.22)
        r = radius - idx * 4
        draw.arc([cx - r, base - r, cx + r, base + r], 180, 360, fill=c, width=4)


def render_key(deck, key: int, pressed: bool, sidecar=None, pulse: bool = False,
               latched: bool = False, hold_cue: bool = False):
    """pressed = PHYSICAL key-down only (renders the ~150ms white ack flash).
    latched = the deck-local toggle latch (led_state) — honored ONLY by
    static-look rows, which have no feedback state. Palette and control pads
    render from the feedback file's `state`; passing the latch as `pressed`
    is the bug that froze control pads white (caller-contract regression,
    2026-07-04)."""
    image = PILHelper.create_image(deck)
    row = _row_for_key(key, sidecar)
    if row is None:
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, image.width, image.height], fill=(8, 8, 8))
        return PILHelper.to_native_format(deck, image)
    icon = os.path.join(ICON_DIR, f"{key + 1}.png")
    if os.path.exists(icon):
        image.paste(Image.open(icon).convert("RGB").resize(image.size))
        if pressed:  # blue tint so you still see the press on a custom icon
            image = Image.blend(image, Image.new("RGB", image.size, (0, 150, 255)), 0.35)
        return PILHelper.to_native_format(deck, image)

    draw = ImageDraw.Draw(image)
    w, h = image.width, image.height
    active = _row_active(row, False, pulse)  # feedback-state truth, never the latch
    kind = row.get("target_kind")
    state = str(row.get("state") or "inactive")

    if pressed:  # tactile ack: full white flash, no glyph needed for ~150 ms
        draw.rectangle([0, 0, w, h], fill=(245, 245, 245))
        return PILHelper.to_native_format(deck, image)

    if kind == "palette_pad":
        # The color IS the label — no text. The pad shows the palette's RANGE
        # as a left-to-right gradient (bridge ships an 8-sample ramp; flat rgb
        # fallback for older feedback payloads). dim = available, bright +
        # border = playing, pulsing border = queued (dim) / arriving (bright).
        ramp = row.get("ramp")
        if isinstance(ramp, list) and len(ramp) >= 2:
            colors = [_normal_rgb(c) for c in ramp]
        else:
            colors = [_normal_rgb(row.get("rgb"))] * 2
        bright = state in ("active", "fading")
        if not bright:
            colors = [_dim(c) for c in colors]
        n = len(colors)
        for x in range(w):
            t = x / max(1, w - 1) * (n - 1)
            i = min(int(t), n - 2)
            f = t - i
            c0, c1 = colors[i], colors[i + 1]
            col = tuple(int(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
            draw.line([x, 0, x, h], fill=col)
        if state == "active":
            draw.rectangle([3, 3, w - 4, h - 4], outline=(255, 255, 255), width=4)
        elif state in ("queued", "fading") and pulse:
            draw.rectangle([3, 3, w - 4, h - 4], outline=(255, 255, 255), width=5)
        if row.get("locked_current") or hold_cue:
            _draw_padlock(draw, w, h, True)
    elif kind == "led_mute":
        muted = active
        draw.rectangle([0, 0, w, h], fill=_MUTE_RED if muted else _BG)
        _draw_bulb(draw, w, h, muted)
        if muted:
            _draw_slash(draw, w, h)
    elif kind == "laser_mute":
        muted = active
        draw.rectangle([0, 0, w, h], fill=_MUTE_RED if muted else _BG)
        _draw_beam(draw, w, h, muted)
        if muted:
            _draw_slash(draw, w, h)
    elif kind == "laser_solo":
        if state == "active":
            draw.rectangle([0, 0, w, h], fill=_AMBER)
            _draw_starburst(draw, w, h, (255, 255, 255))
        elif state == "queued":  # armed: pulsing amber — press to cancel
            draw.rectangle([0, 0, w, h], fill=(70, 46, 8) if pulse else _BG)
            _draw_starburst(draw, w, h, _AMBER if pulse else _dim(_AMBER))
        else:
            draw.rectangle([0, 0, w, h], fill=_BG)
            _draw_starburst(draw, w, h, _dim(_AMBER, 0.4, 0.24))
    elif kind == "rainbow":
        draw.rectangle([0, 0, w, h], fill=_BG)
        _draw_rainbow_arc(draw, w, h, vivid=active)
    else:  # static looks: the name is the identity — one clean label, no note text
        on = latched or active
        draw.rectangle([0, 0, w, h], fill=(0, 120, 210) if on else (26, 26, 30))
        label = str(row.get("name") or key + 1).replace("_", " ")
        _fit_text(draw, label, (w / 2, h / 2), w - 8, size=16,
                  fill=(255, 255, 255) if on else (185, 185, 190))
    return PILHelper.to_native_format(deck, image)


def acquire_deck(log_errors: bool = True):
    # log_errors=False after the first failed attempt: the retry loop runs
    # every 3s and once filled /tmp/streamdeck.log with 3000+ identical lines.
    try:
        decks = DeviceManager().enumerate()
    except Exception as exc:
        if log_errors:
            log(f"Stream Deck enumerate error: {exc}")
        return None

    for deck in decks:
        try:
            deck.open()
            deck.reset()
            deck.set_brightness(60)
            return deck
        except Exception as exc:
            if log_errors:
                log(f"Stream Deck open error: {exc}")
            try:
                deck.close()
            except Exception:
                pass
    return None


def make_on_key(deck, port, sidecar_ref, active_keys: set[tuple[int, int]]):
    def schedule_hold_cue(key: int, row: dict) -> None:
        value = row.get("long_press_s", 0.5)
        delay = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0.5

        def show_if_still_held():
            try:
                latest = sidecar_ref() if callable(sidecar_ref) else sidecar_ref
                latest_row = _row_for_key(key, latest)
                if not isinstance(latest_row, dict) or latest_row.get("target_kind") != "palette_pad":
                    return
                latest_key = (CHANNEL, latest_row["note"])
                if latest_key not in active_keys or latest_row.get("gesture") != 2:
                    return
                deck.set_key_image(
                    key,
                    render_key(deck, key, False, latest, hold_cue=True,
                               latched=latest_key in active_keys),
                )
            except Exception:
                pass

        threading.Timer(delay, show_if_still_held).start()

    def on_key(_deck, key, pressed):
        try:
            sidecar = sidecar_ref() if callable(sidecar_ref) else sidecar_ref
            row = _row_for_key(key, sidecar)
            if row is None:
                return
            pad_key = (CHANNEL, row["note"])
            port.send(key_to_message(key, pressed, sidecar))
            if row["interaction"] == "toggle":
                if pressed:
                    if pad_key in active_keys:
                        active_keys.remove(pad_key)
                    else:
                        active_keys.add(pad_key)
            elif pressed:
                active_keys.add(pad_key)
            else:
                active_keys.discard(pad_key)
            deck.set_key_image(key, render_key(deck, key, pressed, sidecar,
                                               latched=pad_key in active_keys))
            if pressed:
                if row.get("target_kind") == "palette_pad" and row.get("gesture") == 2:
                    schedule_hold_cue(key, row)

                def clear_flash():
                    try:
                        latest = sidecar_ref() if callable(sidecar_ref) else sidecar_ref
                        latest_row = _row_for_key(key, latest)
                        if latest_row is None:
                            return
                        latest_key = (CHANNEL, latest_row["note"])
                        deck.set_key_image(
                            key,
                            render_key(deck, key, False, latest,
                                       latched=latest_key in active_keys),
                        )
                    except Exception:
                        pass

                threading.Timer(0.15, clear_flash).start()
        except Exception as exc:
            # Broad on purpose: this runs on the library's read thread, which
            # only survives TransportError. Any exception we let escape (e.g.
            # an rtmidi send failure, which is NOT an OSError) kills that
            # thread and every pad goes silently dead while the display keeps
            # rendering — the unforgivable failure mode.
            log(f"key callback error: {exc!r}")
    return on_key


def _render_frame(deck, layout, keys, active_keys: set[tuple[int, int]], pulse: bool) -> None:
    for key in sorted(keys):
        row = _row_for_key(key, layout)
        latched = row is not None and (CHANNEL, row["note"]) in active_keys
        deck.set_key_image(key, render_key(deck, key, False, layout, pulse=pulse,
                                           latched=latched))


def main():
    if not _acquire_singleton_lock():
        return

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    # Latches and feedback-link memory deliberately survive device reconnects:
    # the bridge keeps its held layers when only the USB link blips, so a
    # fresh-per-connection latch set would lie about bridge state. A bridge
    # restart (feedback seq regression, seen by FeedbackWatch) clears them.
    active_keys: set[tuple[int, int]] = set()
    watch = FeedbackWatch()
    tick = [time.monotonic()]
    threading.Thread(target=_watchdog, args=(stop, tick), daemon=True,
                     name="streamdeck-watchdog").start()

    waiting_logged = False
    while not stop.is_set():
        tick[0] = time.monotonic()
        deck = acquire_deck(log_errors=not waiting_logged)
        if deck is None:
            if not waiting_logged:
                log("waiting for Stream Deck (absent or held by Elgato app)...")
                waiting_logged = True
            stop.wait(RETRY_SECONDS)
            continue
        waiting_logged = False

        port = None
        try:
            static_rows = load_sidecar(key_count=deck.key_count())
            if len(static_rows) > 4:
                log(f"streamdeck_midi: dropping {len(static_rows) - 4} static-look binding(s) beyond key 13")
            feedback = load_feedback_state()
            sidecar = compose_layout(feedback, static_rows, key_count=deck.key_count())
            boot_messages, clear_latches = watch.observe(feedback, sidecar)
            if clear_latches and active_keys:
                boot_messages.append(f"cleared {len(active_keys)} deck-local pad latch(es)")
                active_keys.clear()
            layout_lock = threading.Lock()

            def current_layout():
                with layout_lock:
                    return list(sidecar)

            port = mido.open_output(PORT_NAME, virtual=True)
            pulse = False
            _render_frame(deck, sidecar, range(deck.key_count()), active_keys, pulse)
            deck.set_key_callback(make_on_key(deck, port, current_layout, active_keys))
            notes = [row["note"] for row in sidecar if isinstance(row, dict) and "note" in row]
            if notes:
                log(f'"{PORT_NAME}" live - notes {min(notes)}-{max(notes)}, '
                    f"ch {CHANNEL + 1}")
            else:
                log(f'"{PORT_NAME}" live - no bound notes, ch {CHANNEL + 1}')
            for message in boot_messages:
                log(message)

            # ponytail: poll-based disconnect detect; also refresh feedback-file rendering.
            while not stop.is_set() and deck.connected():
                reader = getattr(deck, "read_thread", None)
                if reader is not None and not reader.is_alive():
                    # The library reader swallows TransportError by silently
                    # closing the device; connected() can stay True with input
                    # dead. Without this check the pads render fine forever
                    # while presses go nowhere.
                    log("input reader thread died - forcing reconnect")
                    break
                stop.wait(0.5)
                tick[0] = time.monotonic()
                pulse = not pulse
                feedback = load_feedback_state()
                next_layout = compose_layout(feedback, static_rows, key_count=deck.key_count())
                messages, clear_latches = watch.observe(feedback, next_layout)
                for message in messages:
                    log(message)
                if clear_latches and active_keys:
                    log(f"cleared {len(active_keys)} deck-local pad latch(es)")
                if clear_latches:
                    active_keys.clear()
                changed = next_layout != sidecar
                prev_layout = sidecar
                if changed:
                    with layout_lock:
                        sidecar = next_layout
                if clear_latches:
                    to_draw = set(range(deck.key_count()))
                else:
                    # Redraw only what can differ: rows that changed plus rows
                    # whose look depends on the pulse phase — not all 15 keys
                    # every 0.5s tick while one pad pulses.
                    to_draw = _changed_keys(prev_layout, next_layout) if changed else set()
                    to_draw |= _pulse_keys(sidecar)
                _render_frame(deck, sidecar, to_draw, active_keys, pulse)
        except (TransportError, OSError) as exc:
            log(f"device error: {exc} - will reconnect")
        finally:
            try:
                deck.reset()
                deck.close()
            except Exception:
                pass
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass

        if not stop.is_set():
            log("Stream Deck disconnected - waiting for it to come back")

    log("streamdeck_midi: shutdown")


def selftest():
    on = key_to_message(0, True)
    assert on.type == "note_on" and on.note == 36 and on.velocity == 127 and on.channel == CHANNEL
    off = key_to_message(14, False)
    assert off.type == "note_off" and off.note == 50 and off.velocity == 0 and off.channel == CHANNEL
    assert note_for(0) == 36 and note_for(14) == 50
    rows = [
        {"channel": CHANNEL, "note": 40, "target_kind": "static_look",
         "interaction": "toggle", "name": "A"},
        {"channel": CHANNEL, "note": 41, "target_kind": "static_look",
         "interaction": "press", "name": "B"},
        {"channel": 0, "note": 1, "target_kind": "static_look",
         "interaction": "toggle", "name": "wrong"},
    ]
    assert key_to_message(0, True, rows).note == 40
    assert led_state(rows, {(CHANNEL, 40)}) == {(CHANNEL, 40): True, (CHANNEL, 41): False}
    feedback = {
        "gesture": 2,
        "long_press_s": 0.5,
        "lock": True,
        "current_palette": "blue_cyan",
        "palettes": [
            {"name": "blue_cyan", "note": 51, "rgb": [0, 160, 255], "state": "active"},
            {"name": "deep_ocean", "note": 52, "rgb": [0, 80, 160], "state": "queued"},
            {"name": "white_sand", "note": 56, "rgb": [255, 235, 200], "state": "inactive"},
            {"name": "rainbow", "note": 61, "rgb": [255, 0, 255], "state": "inactive"},
        ],
        "controls": {
            "lock": {"name": "Lock", "note": 57, "state": "active"},
            "led_mute": {"name": "LED Mute", "note": 58, "state": "inactive"},
            "laser_mute": {"name": "Laser Mute", "note": 59, "state": "active"},
            "laser_solo": {"name": "Laser Solo", "note": 60, "state": "inactive"},
            "rainbow": {"name": "Rainbow", "note": 61, "state": "inactive"},
        },
    }
    layout = compose_layout(feedback, rows, key_count=15)
    assert [note_for(k, layout) for k in (0, 1, 5, 6, 8, 10, 11, 14)] == [
        51, 52, 56, None, 59, 40, 41, 61,
    ]
    assert layout[6] is None and layout[0]["locked_current"] is True
    blank_layout = compose_layout(None, rows, key_count=15)
    assert blank_layout[0] is None and blank_layout[10]["note"] == 40
    assert _row_active(layout[1], False, pulse=True)
    assert not _row_active(layout[1], False, pulse=False)
    swatches = [(0, 255, 0), (0, 255, 255), (0, 0, 255), (160, 0, 255), (255, 0, 160)]
    hues = [colorsys.rgb_to_hsv(*(part / 255.0 for part in rgb))[0] for rgb in swatches]
    dim_hues = [colorsys.rgb_to_hsv(*(part / 255.0 for part in _dim(rgb)))[0] for rgb in swatches]
    assert dim_hues == sorted(dim_hues) and all(abs(a - b) < 0.001 for a, b in zip(hues, dim_hues))
    assert CHANNEL not in (0, 1)
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
