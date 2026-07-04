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
import os
import fcntl
import json
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
# Drop 1.png .. 15.png in the icons/ folder beside this file to give pads
# custom pictures (else the pad shows its number + note):
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
# -----------------------------------------------------------------------------
_LOCK_FILE = None


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
    return {
        "channel": CHANNEL,
        "note": int(row["note"]),
        "target_kind": "palette_pad",
        "interaction": "press",
        "name": str(row.get("name") or ""),
        "rgb": tuple(row.get("rgb") or (0, 0, 0)),
        "state": str(row.get("state") or "inactive"),
    }


def _control_row(feedback: dict | None, key: str, fallback_name: str) -> dict | None:
    controls = (feedback or {}).get("controls", {})
    row = controls.get(key) if isinstance(controls, dict) else None
    if not isinstance(row, dict) or type(row.get("note")) is not int:
        return None
    return {
        "channel": CHANNEL,
        "note": int(row["note"]),
        "target_kind": key,
        "interaction": "toggle",
        "name": str(row.get("name") or fallback_name),
        "state": str(row.get("state") or "inactive"),
    }


def compose_layout(feedback: dict | None, sidecar: list[dict], key_count: int = 15) -> list[dict | None]:
    layout: list[dict | None] = [None] * key_count
    if feedback is not None:
        current_palette = str(feedback.get("current_palette") or "")
        current_palette_row = _feedback_palette(feedback, current_palette)
        current_rgb = current_palette_row.get("rgb") if current_palette_row is not None else None
        auto_palettes = [
            row for row in feedback.get("palettes", [])
            if isinstance(row, dict)
            and row.get("name") not in ("white_sand", "rainbow")
            and type(row.get("note")) is int
        ][:5]
        for key, row in enumerate(auto_palettes):
            layout[key] = _palette_row(row)
        white_sand = _feedback_palette(feedback, "white_sand")
        if white_sand is not None and key_count > 5:
            layout[5] = _palette_row(white_sand)
        controls = [
            (6, "lock", "Lock"),
            (7, "led_mute", "LED Mute"),
            (8, "laser_mute", "Laser Mute"),
            (9, "laser_solo", "Laser Solo"),
            (14, "rainbow", "Rainbow"),
        ]
        for key, control, label in controls:
            if key < key_count:
                row = _control_row(feedback, control, label)
                if row is not None and control == "lock" and current_rgb is not None:
                    row["rgb"] = tuple(current_rgb)
                layout[key] = row

    static_rows = list(sidecar)[:4]
    for offset, row in enumerate(static_rows):
        key = 10 + offset
        if key < key_count:
            layout[key] = dict(row)
    return layout


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


def _draw_rainbow(draw, box):
    colors = [(255, 0, 70), (255, 170, 0), (255, 245, 0), (0, 220, 90), (0, 170, 255), (160, 70, 255)]
    x0, y0, x1, y1 = box
    step = max(1, (x1 - x0) // len(colors))
    for idx, color in enumerate(colors):
        draw.rectangle([x0 + idx * step, y0, x0 + (idx + 1) * step, y1], fill=color)


def render_key(deck, key: int, pressed: bool, sidecar=None, pulse: bool = False):
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
    else:
        draw = ImageDraw.Draw(image)
        w, h = image.width, image.height
        active = _row_active(row, pressed, pulse)
        kind = row.get("target_kind")
        state = str(row.get("state") or "inactive")
        if pressed:
            draw.rectangle([0, 0, w, h], fill=(245, 245, 245))
            fg = (10, 10, 10)
        elif kind == "palette_pad":
            rgb = _normal_rgb(row.get("rgb"))
            fill = rgb if active else tuple(max(12, int(part * 0.22)) for part in rgb)
            draw.rectangle([0, 0, w, h], fill=fill)
            fg = "white"
            if state in ("queued", "fading"):
                draw.rectangle([4, 4, w - 5, h - 5], outline=(255, 255, 255), width=3)
        elif kind == "led_mute":
            draw.rectangle([0, 0, w, h], fill=(190, 0, 25) if active else (45, 12, 16))
            draw.line([16, h - 16, w - 16, 16], fill=(255, 235, 235), width=7)
            fg = "white"
        elif kind == "laser_mute":
            draw.rectangle([0, 0, w, h], fill=(190, 0, 25) if active else (45, 12, 16))
            draw.line([12, h - 14, w - 10, 14], fill=(255, 235, 235), width=7)
            fg = "white"
        elif kind == "laser_solo":
            draw.rectangle([0, 0, w, h], fill=(245, 150, 20) if active else (52, 35, 12))
            draw.regular_polygon((w / 2, h / 2 - 4, 21), n_sides=8, rotation=0, fill=(255, 205, 80))
            fg = (30, 20, 0)
        elif kind == "rainbow":
            draw.rectangle([0, 0, w, h], fill=(20, 20, 22))
            _draw_rainbow(draw, (10, 14, w - 10, 34))
            fg = "white"
        elif kind == "lock":
            base = _normal_rgb(row.get("rgb"))
            draw.rectangle([0, 0, w, h], fill=base if active else (32, 32, 34))
            draw.rounded_rectangle([22, 30, w - 22, h - 14], radius=5, outline="white", width=3)
            draw.arc([24, 14, w - 24, 46], 180, 360, fill="white", width=3)
            fg = "white"
        else:
            draw.rectangle([0, 0, w, h],
                           fill=(0, 150, 255) if active else (35, 35, 35))
            fg = "white"
        label = str(row.get("name") or key + 1).replace("_", " ")
        _fit_text(draw, label, (w / 2, h / 2 + 10), w - 10, size=15, fill=fg)
        draw.text((w / 2, h - 8), f"n{row['note']}", anchor="mm",
                  font=_font(11), fill=(210, 210, 210) if not pressed else (50, 50, 50))
    return PILHelper.to_native_format(deck, image)


def acquire_deck():
    try:
        decks = DeviceManager().enumerate()
    except Exception as exc:
        log(f"Stream Deck enumerate error: {exc}")
        return None

    for deck in decks:
        try:
            deck.open()
            deck.reset()
            deck.set_brightness(60)
            return deck
        except Exception as exc:
            log(f"Stream Deck open error: {exc}")
            try:
                deck.close()
            except Exception:
                pass
    return None


def make_on_key(deck, port, sidecar_ref, active_keys: set[tuple[int, int]]):
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
            deck.set_key_image(key, render_key(deck, key, led_state(sidecar, active_keys)[pad_key],
                                               sidecar))
            if pressed:
                def clear_flash():
                    try:
                        latest = sidecar_ref() if callable(sidecar_ref) else sidecar_ref
                        latest_row = _row_for_key(key, latest)
                        if latest_row is None:
                            return
                        latest_key = (CHANNEL, latest_row["note"])
                        deck.set_key_image(
                            key,
                            render_key(deck, key, led_state(latest, active_keys).get(latest_key, False), latest),
                        )
                    except Exception:
                        pass

                threading.Timer(0.15, clear_flash).start()
        except (TransportError, OSError) as exc:
            log(f"key callback error: {exc}")
    return on_key


def main():
    if not _acquire_singleton_lock():
        return

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    while not stop.is_set():
        deck = acquire_deck()
        if deck is None:
            log("waiting for Stream Deck (absent or held by Elgato app)...")
            stop.wait(RETRY_SECONDS)
            continue

        port = None
        try:
            static_rows = load_sidecar(key_count=deck.key_count())
            if len(static_rows) > 4:
                log(f"streamdeck_midi: dropping {len(static_rows) - 4} static-look binding(s) beyond key 14")
            feedback = load_feedback_state()
            sidecar = compose_layout(feedback, static_rows, key_count=deck.key_count())
            active_keys: set[tuple[int, int]] = set()
            layout_lock = threading.Lock()

            def current_layout():
                with layout_lock:
                    return list(sidecar)

            port = mido.open_output(PORT_NAME, virtual=True)
            pulse = False
            for k in range(deck.key_count()):
                deck.set_key_image(k, render_key(deck, k, False, sidecar, pulse=pulse))
            deck.set_key_callback(make_on_key(deck, port, current_layout, active_keys))
            notes = [row["note"] for row in sidecar if isinstance(row, dict) and "note" in row]
            if notes:
                log(f'"{PORT_NAME}" live - notes {min(notes)}-{max(notes)}, '
                    f"ch {CHANNEL + 1}")
            else:
                log(f'"{PORT_NAME}" live - no bound notes, ch {CHANNEL + 1}')

            # ponytail: poll-based disconnect detect; also refresh feedback-file rendering.
            while not stop.is_set() and deck.connected():
                stop.wait(0.5)
                pulse = not pulse
                feedback = load_feedback_state()
                next_layout = compose_layout(feedback, static_rows, key_count=deck.key_count())
                changed = next_layout != sidecar
                if changed:
                    with layout_lock:
                        sidecar = next_layout
                if changed or any(str((row or {}).get("state")) in ("queued", "fading") for row in sidecar):
                    for k in range(deck.key_count()):
                        row = _row_for_key(k, sidecar)
                        pad_key = (CHANNEL, row["note"]) if row is not None else None
                        active = pad_key in active_keys if pad_key is not None else False
                        deck.set_key_image(k, render_key(deck, k, active, sidecar, pulse=pulse))
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
        51, 52, 56, 57, 59, 40, 41, 61,
    ]
    assert layout[6]["rgb"] == (0, 160, 255)
    blank_layout = compose_layout(None, rows, key_count=15)
    assert blank_layout[0] is None and blank_layout[10]["note"] == 40
    assert _row_active(layout[1], False, pulse=True)
    assert not _row_active(layout[1], False, pulse=False)
    assert CHANNEL not in (0, 1)
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
