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


def led_state(sidecar, pressed_set: set[tuple[int, int]]) -> dict[tuple[int, int], bool]:
    rows = _rows_from_payload(sidecar) or _fixed_rows()
    return {
        (CHANNEL, row["note"]): (CHANNEL, row["note"]) in pressed_set
        for row in rows
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


def render_key(deck, key: int, pressed: bool, sidecar=None):
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
        draw.rectangle([0, 0, image.width, image.height],
                       fill=(0, 150, 255) if pressed else (35, 35, 35))
        w, h = image.width, image.height
        draw.text((w / 2, h / 2 - 8), str(key + 1), anchor="mm",
                  font=_font(30), fill="white")
        draw.text((w / 2, h - 14), f"n{row['note']}", anchor="mm",
                  font=_font(13), fill=(170, 170, 170))
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


def make_on_key(deck, port, sidecar, active_keys: set[tuple[int, int]]):
    def on_key(_deck, key, pressed):
        try:
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
            sidecar = load_sidecar(key_count=deck.key_count())
            active_keys: set[tuple[int, int]] = set()
            port = mido.open_output(PORT_NAME, virtual=True)
            for k in range(deck.key_count()):
                deck.set_key_image(k, render_key(deck, k, False, sidecar))
            deck.set_key_callback(make_on_key(deck, port, sidecar, active_keys))
            notes = [row["note"] for row in sidecar]
            log(f'"{PORT_NAME}" live - notes {min(notes)}-{max(notes)}, '
                f"ch {CHANNEL + 1}")

            # ponytail: poll-based disconnect detect at 1 Hz; switch to events if a frozen-deck gap appears.
            while not stop.is_set() and deck.connected():
                stop.wait(1.0)
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
    assert CHANNEL not in (0, 1)
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
