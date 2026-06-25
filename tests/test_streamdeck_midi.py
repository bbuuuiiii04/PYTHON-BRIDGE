from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.streamdeck import streamdeck_midi as sd


class FakeDeck:
    def __init__(self) -> None:
        self.images = []

    def key_image_format(self):
        return {"size": (72, 72)}

    def set_key_image(self, key, image):
        self.images.append((key, image))


class FakePort:
    def __init__(self) -> None:
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class StreamDeckPartialSidecarTests(unittest.TestCase):
    def test_load_sidecar_keeps_partial_rows_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".pack.midi_bindings.json"
            path.write_text(json.dumps([
                {"channel": sd.CHANNEL, "note": 40, "target_kind": "static_look",
                 "interaction": "toggle", "name": "Blue"},
            ]), encoding="utf-8")

            rows = sd.load_sidecar(path, key_count=3)

        self.assertEqual(len(rows), 1)
        self.assertEqual(sd.note_for(0, rows), 40)
        self.assertIsNone(sd.note_for(2, rows))

    def test_missing_partial_sidecar_keys_are_inactive_noops(self):
        rows = [
            {"channel": sd.CHANNEL, "note": 40, "target_kind": "static_look",
             "interaction": "toggle", "name": "Blue"},
        ]
        deck = FakeDeck()
        port = FakePort()
        active_keys = set()
        with mock.patch.object(
            sd, "render_key", side_effect=lambda _deck, key, pressed, _sidecar: (key, pressed),
        ):
            on_key = sd.make_on_key(deck, port, rows, active_keys)
            on_key(deck, 0, True)
            on_key(deck, 2, True)
            on_key(deck, 2, False)

        self.assertEqual([message.note for message in port.messages], [40])
        self.assertEqual(active_keys, {(sd.CHANNEL, 40)})
        self.assertEqual(deck.images, [(0, (0, True))])
        with self.assertRaises(ValueError):
            sd.key_to_message(2, True, rows)

    def test_missing_partial_sidecar_key_renders_blank_dim_tile(self):
        rows = [
            {"channel": sd.CHANNEL, "note": 40, "target_kind": "static_look",
             "interaction": "press", "name": "Blue"},
        ]
        with mock.patch.object(sd.PILHelper, "to_native_format",
                               side_effect=lambda _deck, image: image):
            image = sd.render_key(FakeDeck(), 2, False, rows)

        self.assertEqual(image.getextrema(), ((8, 8), (8, 8), (8, 8)))

    def test_missing_file_keeps_existing_fixed_note_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = sd.load_sidecar(Path(tmp) / "missing.json", key_count=3)
        self.assertEqual([row["note"] for row in rows], [36, 37, 38])


if __name__ == "__main__":
    unittest.main()
