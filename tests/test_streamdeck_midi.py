from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.streamdeck import streamdeck_midi as sd


class FakeDeck:
    """Satisfies PILHelper so tests drive the REAL render_key through the
    REAL on_key. The old mock-based smoke tests passed hand-built values
    straight into render_key and missed the caller-contract regression that
    froze every toggle pad white (2026-07-04)."""

    def __init__(self) -> None:
        self.images: dict[int, bytes] = {}
        self.writes: list[int] = []
        self.callback = None
        self.connected_flag = True

    def key_image_format(self):
        return {"size": (72, 72), "format": "JPEG", "rotation": 0,
                "flip": (False, False)}

    def key_count(self) -> int:
        return 15

    def set_key_image(self, key, image) -> None:
        self.images[key] = image
        self.writes.append(key)

    def set_key_callback(self, callback) -> None:
        self.callback = callback

    def connected(self) -> bool:
        return self.connected_flag

    def reset(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakePort:
    def __init__(self) -> None:
        self.messages = []
        self.fail_next: Exception | None = None

    def send(self, message):
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        self.messages.append(message)


STATIC_ROWS = [
    {"channel": sd.CHANNEL, "note": 36, "target_kind": "static_look",
     "interaction": "toggle", "name": "Blue Wash"},
    {"channel": sd.CHANNEL, "note": 37, "target_kind": "static_look",
     "interaction": "press", "name": "Strobe"},
    {"channel": sd.CHANNEL, "note": 38, "target_kind": "static_look",
     "interaction": "press", "name": "Amber"},
    {"channel": sd.CHANNEL, "note": 39, "target_kind": "static_look",
     "interaction": "press", "name": "Red"},
]


def _feedback(seq: int = 5, current: str = "blue_cyan") -> dict:
    return {
        "schema": 1,
        "seq": seq,
        "current_palette": current,
        "palettes": [
            {"name": "blue_cyan", "note": 51, "rgb": [0, 160, 255],
             "ramp": [[0, 200, 255], [0, 80, 255]], "state": "active"},
            {"name": "violet", "note": 52, "rgb": [120, 0, 255],
             "ramp": [[140, 40, 255], [90, 0, 230]], "state": "queued"},
            {"name": "white_sand", "note": 56, "rgb": [255, 235, 200],
             "ramp": [[255, 235, 200], [255, 235, 200]], "state": "inactive"},
        ],
        "controls": {
            "lock": {"name": "Lock", "note": 57, "state": "inactive"},
            "led_mute": {"name": "LED Mute", "note": 58, "state": "inactive"},
            "laser_mute": {"name": "Laser Mute", "note": 59, "state": "active"},
            "laser_solo": {"name": "Laser Solo", "note": 60, "state": "queued"},
            "rainbow": {"name": "Rainbow", "note": 61, "state": "inactive"},
        },
    }


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
        rows = [STATIC_ROWS[0]]
        deck = FakeDeck()
        port = FakePort()
        active_keys: set = set()
        with mock.patch.object(sd.threading, "Timer"):
            on_key = sd.make_on_key(deck, port, rows, active_keys)
            on_key(deck, 0, True)
            on_key(deck, 2, True)
            on_key(deck, 2, False)

        self.assertEqual([message.note for message in port.messages], [36])
        self.assertEqual(active_keys, {(sd.CHANNEL, 36)})
        self.assertEqual(deck.writes, [0])  # unbound keys never rendered
        self.assertIsInstance(deck.images[0], bytes)
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


class StreamDeckRealCallerPathTests(unittest.TestCase):
    """Drive the real on_key -> render_key -> set_key_image path over a
    composed layout (feedback fixture + sidecar), not hand-built rows."""

    def _wire(self, feedback=None):
        layout = sd.compose_layout(
            feedback if feedback is not None else _feedback(),
            STATIC_ROWS, key_count=15)
        deck = FakeDeck()
        port = FakePort()
        active_keys: set = set()
        on_key = sd.make_on_key(deck, port, lambda: list(layout), active_keys)
        return layout, deck, port, active_keys, on_key

    def test_every_bound_key_press_and_release_renders_and_sends(self):
        layout, deck, port, active_keys, on_key = self._wire()
        clear_flashes = []

        def fake_timer(_delay, fn):
            clear_flashes.append(fn)
            return mock.MagicMock()

        with mock.patch.object(sd.threading, "Timer", side_effect=fake_timer):
            for key in range(15):
                on_key(deck, key, True)
                on_key(deck, key, False)

        bound = [k for k in range(15) if layout[k] is not None]
        expected = [n for k in bound for n in (layout[k]["note"], layout[k]["note"])]
        self.assertEqual([m.note for m in port.messages], expected)
        for k in bound:
            self.assertIsInstance(deck.images[k], bytes)
        self.assertEqual(len(clear_flashes), len(bound))  # one flash-clear per press
        for fn in clear_flashes:
            fn()  # re-render from the latest layout must not raise

    def test_toggle_latch_flips_on_press_only_and_press_rows_follow_the_finger(self):
        layout, deck, port, active_keys, on_key = self._wire()
        with mock.patch.object(sd.threading, "Timer"):
            on_key(deck, 10, True)   # STATIC_ROWS[0]: toggle, note 36
            on_key(deck, 10, False)
            self.assertIn((sd.CHANNEL, 36), active_keys)
            on_key(deck, 10, True)
            on_key(deck, 10, False)
            self.assertNotIn((sd.CHANNEL, 36), active_keys)
            on_key(deck, 11, True)   # STATIC_ROWS[1]: press, note 37
            self.assertIn((sd.CHANNEL, 37), active_keys)
            on_key(deck, 11, False)
            self.assertNotIn((sd.CHANNEL, 37), active_keys)

    def test_callback_exception_is_contained_and_input_keeps_flowing(self):
        # The library read thread only survives TransportError: anything else
        # escaping on_key kills all pad input silently while the display keeps
        # rendering. RuntimeError stands in for an rtmidi send failure (which
        # is NOT an OSError).
        layout, deck, port, active_keys, on_key = self._wire()
        with mock.patch.object(sd.threading, "Timer"):
            port.fail_next = RuntimeError("rtmidi: send failed")
            on_key(deck, 0, True)   # must not raise
            on_key(deck, 0, False)
        self.assertEqual(len(port.messages), 1)  # the release still went out


class FeedbackWatchTests(unittest.TestCase):
    def _static_layout(self):
        return sd.compose_layout(None, STATIC_ROWS, key_count=15)

    def _full_layout(self, feedback):
        return sd.compose_layout(feedback, STATIC_ROWS, key_count=15)

    def test_degraded_boot_is_named_not_implied(self):
        watch = sd.FeedbackWatch()
        messages, clear = watch.observe(None, self._static_layout())
        self.assertTrue(any("static looks only" in m for m in messages))
        self.assertFalse(clear)

    def test_heal_and_loss_log_transitions_with_note_range(self):
        watch = sd.FeedbackWatch()
        watch.observe(None, self._static_layout())
        feedback = _feedback(seq=10)
        messages, clear = watch.observe(feedback, self._full_layout(feedback))
        self.assertTrue(any("feedback restored" in m for m in messages))
        self.assertTrue(any("notes 36-61" in m for m in messages))
        self.assertFalse(clear)

        self.assertEqual(watch.observe(feedback, self._full_layout(feedback)),
                         ([], False))  # steady state stays quiet

        messages, clear = watch.observe(None, self._static_layout())
        self.assertTrue(any("feedback lost" in m for m in messages))
        self.assertTrue(any("notes 36-39" in m for m in messages))
        self.assertFalse(clear)

    def test_bridge_restart_seq_regression_clears_latches(self):
        watch = sd.FeedbackWatch()
        old = _feedback(seq=50)
        watch.observe(old, self._full_layout(old))
        watch.observe(None, self._static_layout())  # bridge-restart gap
        fresh = _feedback(seq=1)
        messages, clear = watch.observe(fresh, self._full_layout(fresh))
        self.assertTrue(clear)
        self.assertTrue(any("bridge restart" in m for m in messages))

    def test_writer_stall_heal_without_restart_keeps_latches(self):
        watch = sd.FeedbackWatch()
        watch.observe(_feedback(seq=50), self._full_layout(_feedback(seq=50)))
        watch.observe(None, self._static_layout())  # stale blip, bridge alive
        _messages, clear = watch.observe(_feedback(seq=51),
                                         self._full_layout(_feedback(seq=51)))
        self.assertFalse(clear)


class RedrawScopeTests(unittest.TestCase):
    def test_pulse_keys_are_only_queued_or_fading_rows(self):
        layout = sd.compose_layout(_feedback(), STATIC_ROWS, key_count=15)
        # violet queued at key 1, laser_solo queued at key 9
        self.assertEqual(sd._pulse_keys(layout), {1, 9})

    def test_changed_keys_finds_only_differing_positions(self):
        a = sd.compose_layout(_feedback(current="blue_cyan"), STATIC_ROWS, key_count=15)
        b = sd.compose_layout(_feedback(current="violet"), STATIC_ROWS, key_count=15)
        # only the lock pad (key 6) wears the current palette's color
        self.assertEqual(sd._changed_keys(a, b), {6})
        self.assertEqual(sd._changed_keys(a, a), set())


class ProjectionPassThroughTests(unittest.TestCase):
    def test_unknown_producer_fields_survive_projection(self):
        feedback = _feedback()
        feedback["palettes"][0]["sparkle"] = {"speed": 3}
        feedback["controls"]["led_mute"]["icon_hint"] = "bulb"
        layout = sd.compose_layout(feedback, STATIC_ROWS, key_count=15)
        self.assertEqual(layout[0]["sparkle"], {"speed": 3})
        self.assertEqual(layout[7]["icon_hint"], "bulb")

    def test_projection_still_normalizes_the_contract_fields(self):
        feedback = _feedback()
        feedback["palettes"][0]["interaction"] = "toggle"  # producer cannot override
        layout = sd.compose_layout(feedback, STATIC_ROWS, key_count=15)
        self.assertEqual(layout[0]["interaction"], "press")
        self.assertEqual(layout[0]["target_kind"], "palette_pad")
        self.assertEqual(layout[0]["ramp"], [(0, 200, 255), (0, 80, 255)])


class WatchdogTests(unittest.TestCase):
    def _run_watchdog(self, stop, tick):
        exits = []

        def fake_exit(code):
            exits.append(code)
            raise SystemExit

        with mock.patch.object(sd.os, "_exit", side_effect=fake_exit), \
                mock.patch.object(sd.time, "sleep", lambda _s: None), \
                mock.patch.object(sd, "log", lambda _m: None):
            with self.assertRaises(SystemExit):
                sd._watchdog(stop, tick)
        return exits

    def test_stalled_main_loop_hard_exits_for_watcher_respawn(self):
        stop = threading.Event()
        tick = [time.monotonic() - (sd.WATCHDOG_STALL_S + 1.0)]
        self.assertEqual(self._run_watchdog(stop, tick), [70])

    def test_stalled_shutdown_hard_exits(self):
        stop = threading.Event()
        stop.set()
        tick = [time.monotonic()]
        self.assertEqual(self._run_watchdog(stop, tick), [70])


if __name__ == "__main__":
    unittest.main()
