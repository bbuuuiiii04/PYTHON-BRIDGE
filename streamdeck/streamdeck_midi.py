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
import signal
import sys
import threading

import mido
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from PIL import Image, ImageDraw, ImageFont

# --- config: change these to taste -------------------------------------------
PORT_NAME = "Stream Deck"   # name other apps will see this controller as
CHANNEL = 2                 # 2 == MIDI channel 3 (chans 1-2 are the lasers')
NOTE_BASE = 36              # pad 0 (top-left) -> note 36 (C1); pads ascend
VELOCITY = 127
# Drop 1.png .. 15.png in the icons/ folder beside this file to give pads
# custom pictures (else the pad shows its number + note):
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
# -----------------------------------------------------------------------------


def note_for(key: int) -> int:
    return NOTE_BASE + key


def key_to_message(key: int, pressed: bool) -> mido.Message:
    """The one piece of logic worth testing: pad -> MIDI message."""
    kind = "note_on" if pressed else "note_off"
    return mido.Message(kind, channel=CHANNEL, note=note_for(key),
                        velocity=VELOCITY if pressed else 0)


def _font(size):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        return ImageFont.load_default()


def render_key(deck, key: int, pressed: bool):
    image = PILHelper.create_image(deck)
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
        draw.text((w / 2, h - 14), f"n{note_for(key)}", anchor="mm",
                  font=_font(13), fill=(170, 170, 170))
    return PILHelper.to_native_format(deck, image)


def main():
    decks = DeviceManager().enumerate()
    if not decks:
        sys.exit("No Stream Deck found. Plug it in and quit Elgato's app.")

    deck = decks[0]  # one physical Original enumerates twice on macOS; first is fine
    deck.open()
    deck.reset()
    deck.set_brightness(60)

    port = mido.open_output(PORT_NAME, virtual=True)

    for k in range(deck.key_count()):
        deck.set_key_image(k, render_key(deck, k, False))

    def on_key(_deck, key, pressed):
        port.send(key_to_message(key, pressed))
        deck.set_key_image(key, render_key(deck, key, pressed))

    deck.set_key_callback(on_key)

    print(f'"{PORT_NAME}" MIDI port is live — {deck.key_count()} pads, '
          f"notes {NOTE_BASE}-{NOTE_BASE + deck.key_count() - 1}, "
          f"channel {CHANNEL + 1}. Ctrl-C to quit.")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()

    deck.reset()
    deck.close()
    port.close()
    print("\nClosed.")


def selftest():
    on = key_to_message(0, True)
    assert on.type == "note_on" and on.note == 36 and on.velocity == 127 and on.channel == CHANNEL
    off = key_to_message(14, False)
    assert off.type == "note_off" and off.note == 50 and off.velocity == 0 and off.channel == CHANNEL
    assert note_for(0) == 36 and note_for(14) == 50
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
