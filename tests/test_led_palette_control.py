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

from rb_ss_bridge_v2.led_color_engine import LedColorEngine
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette
from rb_ss_bridge_v2.led_palette_control import LedPaletteControl, PaletteFeedbackWriter
from rb_ss_bridge_v2.models import BridgeEvent, Ev
from rb_ss_bridge_v2.streamdeck import streamdeck_midi as sd


def _config() -> ColorEngineConfig:
    return ColorEngineConfig(
        enabled=True,
        scale_stops={
            "cyan": (0, 255, 255),
            "blue": (0, 0, 255),
            "purple": (160, 0, 255),
            "magenta": (255, 0, 160),
            "red": (255, 0, 0),
        },
        palettes={
            "blue_cyan": Palette(range=("cyan", "blue"), weight=2.0, dwell=1),
            "violet": Palette(range=("blue", "purple"), weight=1.0, dwell=1),
            "white_sand": Palette(type="fixed_rgb", weight=0.0, rgb=(255, 235, 200)),
            "rainbow": Palette(type="rainbow", weight=0.0),
        },
    )


class _WriterStub:
    instances: list["_WriterStub"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.payloads: list[dict] = []
        self.stopped = False
        _WriterStub.instances.append(self)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True

    def submit(self, payload: dict) -> None:
        self.payloads.append(payload)


class LedPaletteControlTests(unittest.TestCase):
    def setUp(self) -> None:
        _WriterStub.instances.clear()
        self.events: list[BridgeEvent] = []
        self.engine = LedColorEngine(_config(), set_seed=3)
        patcher = mock.patch("rb_ss_bridge_v2.led_palette_control.PaletteFeedbackWriter", _WriterStub)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.control = LedPaletteControl(
            engine=self.engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: 8.0,
            get_phrase_anchor=lambda _beat: 16.0,
            get_laser_blackout=lambda: False,
            palette_notes={"blue_cyan": 51, "violet": 52, "white_sand": 56, "rainbow": 61},
            control_notes={"lock": 57, "led_mute": 58, "laser_mute": 59, "laser_solo": 60, "rainbow": 61},
        )

    def tearDown(self) -> None:
        self.control.stop()

    def _pad(self, name: str, intent: str = "") -> None:
        self.control.handle_event(BridgeEvent(
            kind=Ev.LED_PALETTE_PAD,
            deck=0,
            payload={"name": name, "intent": intent},
            source="test",
        ))

    def test_queue_same_pad_overrides_consumes_queue_and_fades(self) -> None:
        self._pad("violet")
        self.assertEqual(self.engine.snapshot()["queued_palette"], "violet")

        self._pad("violet")
        snap = self.engine.snapshot()

        self.assertEqual(snap["queued_palette"], "")
        self.assertTrue(snap["fading"])
        self.assertEqual(snap["fade_target"], "violet")

    def test_queue_applies_under_lock_and_lock_transfers(self) -> None:
        self.control.handle_event(BridgeEvent(
            kind=Ev.LED_PALETTE_LOCK_PAD,
            deck=0,
            payload={"intent": "lock"},
            source="test",
        ))
        self._pad("violet")

        self.engine.begin_dispatch(
            active_deck=1,
            load_gen=1,
            content_id="track-a",
            filepath="",
            role="groove",
            section_id="groove-1",
            cycle=0,
        )
        snap = self.engine.snapshot()

        self.assertEqual(snap["current_palette"], "violet")
        self.assertTrue(snap["lock"])
        self.assertEqual(snap["queued_palette"], "")

    def test_mute_owner_isolated_and_input_health_releases_only_pad_owner(self) -> None:
        self.control.handle_event(BridgeEvent(kind=Ev.LED_MUTE_PAD, deck=0, payload={}, source="test"))
        self.assertEqual(self.events[-1].kind, Ev.LED_BLACKOUT)
        self.assertEqual(self.events[-1].payload["reason"], "led_mute_pad")

        self.control.on_input_health(False)

        self.assertEqual(self.events[-1].kind, Ev.LED_CLEAR_BLACKOUT)
        self.assertEqual(self.events[-1].payload["reason"], "led_mute_pad")

    def test_rainbow_freezes_palette_pads_and_feedback_carries_notes(self) -> None:
        self.control.handle_event(BridgeEvent(kind=Ev.LED_RAINBOW_PAD, deck=0, payload={}, source="test"))
        before = self.engine.snapshot()
        self._pad("violet")
        after = self.engine.snapshot()

        self.assertEqual(after["queued_palette"], before["queued_palette"])
        payload = _WriterStub.instances[-1].payloads[-1]
        controls = payload["controls"]
        self.assertEqual(controls["rainbow"]["note"], 61)
        self.assertEqual(controls["rainbow"]["state"], "active")
        self.assertEqual(controls["lock"]["note"], 57)
        ws = next(row for row in payload["palettes"] if row["name"] == "white_sand")
        self.assertEqual(ws["note"], 56)
        self.assertEqual(ws["rgb"], [255, 235, 200])
        self.assertEqual(ws["state"], "inactive")
        # fixed_rgb palettes ship a flat ramp; journey palettes span their range
        self.assertEqual(len(ws["ramp"]), 8)
        self.assertTrue(all(c == [255, 235, 200] for c in ws["ramp"]))
        bc = next(row for row in payload["palettes"] if row["name"] == "blue_cyan")
        self.assertNotEqual(bc["ramp"][0], bc["ramp"][-1])

    def test_laser_solo_defaults_to_off_when_no_callback_supplied(self) -> None:
        self.assertEqual(self.control.snapshot()["laser_solo"], "off")
        self.assertEqual(self.control._control_payload()["laser_solo"]["state"], "inactive")

    def test_laser_solo_reads_the_supplied_callback_live(self) -> None:
        state = {"value": "off"}
        control = LedPaletteControl(
            engine=self.engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: 8.0,
            get_phrase_anchor=lambda _beat: 16.0,
            get_laser_blackout=lambda: False,
            get_laser_solo=lambda: state["value"],
            control_notes={"laser_solo": 60},
        )
        self.addCleanup(control.stop)
        self.assertEqual(control.snapshot()["laser_solo"], "off")
        self.assertEqual(control._control_payload()["laser_solo"]["state"], "inactive")

        state["value"] = "armed"
        self.assertEqual(control.snapshot()["laser_solo"], "armed")
        self.assertEqual(control._control_payload()["laser_solo"]["state"], "queued")

        state["value"] = "active"
        self.assertEqual(control.snapshot()["laser_solo"], "active")
        self.assertEqual(control._control_payload()["laser_solo"]["state"], "active")

    def test_maybe_publish_only_submits_when_feedback_snapshot_changes(self) -> None:
        writer = _WriterStub.instances[-1]
        initial_count = len(writer.payloads)

        self.control.maybe_publish()
        self.assertEqual(len(writer.payloads), initial_count)

        self._pad("violet")
        queued_count = len(writer.payloads)
        self.engine.begin_dispatch(
            active_deck=1,
            load_gen=1,
            content_id="track-a",
            filepath="",
            role="groove",
            section_id="groove-1",
            cycle=0,
        )

        self.control.maybe_publish()
        self.assertEqual(len(writer.payloads), queued_count + 1)
        self.assertEqual(writer.payloads[-1]["current_palette"], "violet")
        self.assertEqual(writer.payloads[-1]["queued_palette"], "")

        self.control.maybe_publish()
        self.assertEqual(len(writer.payloads), queued_count + 1)

    def test_override_with_no_beat_authority_applies_instantly(self) -> None:
        # Idle / nothing playing: advance_fade never ticks (dispatch runs only
        # while a deck plays), so an armed fade would freeze at 0% forever.
        # The coordinator must apply instantly instead (manual wins NOW).
        control = LedPaletteControl(
            engine=LedColorEngine(_config(), set_seed=3),
            led_event_sink=self.events.append,
            get_abs_beat=lambda: None,
            get_phrase_anchor=lambda _beat: None,
            get_laser_blackout=lambda: False,
            palette_notes={"blue_cyan": 51, "violet": 52},
            control_notes={},
        )
        self.addCleanup(control.stop)
        for _ in range(2):  # tap to queue, tap again to override (v1 gesture)
            control.handle_event(BridgeEvent(
                kind=Ev.LED_PALETTE_PAD, deck=0,
                payload={"name": "blue_cyan"}, source="test",
            ))
        snap = control._engine.snapshot()
        self.assertEqual(snap["current_palette"], "blue_cyan")
        self.assertFalse(snap["fading"])
        self.assertEqual(snap["queued_palette"], "")

    def test_palette_payload_never_invents_notes_for_unconfigured_palettes(self) -> None:
        control = LedPaletteControl(
            engine=LedColorEngine(_config(), set_seed=3),
            led_event_sink=self.events.append,
            get_abs_beat=lambda: 8.0,
            get_phrase_anchor=lambda _beat: 16.0,
            get_laser_blackout=lambda: False,
            palette_notes={"blue_cyan": 51, "violet": 52, "white_sand": 56},
            control_notes={"lock": 57},
        )
        self.addCleanup(control.stop)
        payload = _WriterStub.instances[-1].payloads[-1]
        names = [row["name"] for row in payload["palettes"]]
        self.assertNotIn("rainbow", names)  # no configured note -> not a pad
        self.assertIn("white_sand", names)
        allowed = {51, 52, 56}
        self.assertTrue(all(row["note"] in allowed for row in payload["palettes"]))


class PaletteFeedbackWriterTests(unittest.TestCase):
    def test_writer_uses_background_thread_and_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "palette.json"
            writer = PaletteFeedbackWriter(str(path), debounce_s=0.01)
            writer.start()
            caller = threading.get_ident()
            writer.submit({"schema": 1, "seq": 1})
            deadline = time.time() + 1.0
            while time.time() < deadline and not path.exists():
                time.sleep(0.01)
            writer.stop()
            writer.join(timeout=1.0)

            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["seq"], 1)
            self.assertNotEqual(writer.ident, caller)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_heartbeat_refreshes_mtime_with_identical_payload_while_idle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "palette.json"
            writer = PaletteFeedbackWriter(str(path), debounce_s=0.01, heartbeat_s=0.05)
            writer.start()
            try:
                # No submit yet: heartbeat must not invent a file.
                time.sleep(0.15)
                self.assertFalse(path.exists())

                writer.submit({"schema": 1, "seq": 7})
                deadline = time.time() + 1.0
                while time.time() < deadline and not path.exists():
                    time.sleep(0.01)
                first_mtime = path.stat().st_mtime_ns

                # Idle across several heartbeats: mtime advances, content identical
                # (this is what keeps streamdeck_midi's FEEDBACK_STALE_S check alive).
                deadline = time.time() + 2.0
                while time.time() < deadline and path.stat().st_mtime_ns == first_mtime:
                    time.sleep(0.02)
                self.assertGreater(path.stat().st_mtime_ns, first_mtime)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["seq"], 7)
            finally:
                writer.stop()
                writer.join(timeout=1.0)


class StreamDeckPaletteLayoutTests(unittest.TestCase):
    def test_feedback_blank_leaves_static_looks_only(self) -> None:
        static = [
            {"channel": sd.CHANNEL, "note": 36, "target_kind": "static_look", "interaction": "press", "name": "A"},
            {"channel": sd.CHANNEL, "note": 37, "target_kind": "static_look", "interaction": "press", "name": "B"},
            {"channel": sd.CHANNEL, "note": 38, "target_kind": "static_look", "interaction": "press", "name": "C"},
            {"channel": sd.CHANNEL, "note": 39, "target_kind": "static_look", "interaction": "press", "name": "D"},
            {"channel": sd.CHANNEL, "note": 40, "target_kind": "static_look", "interaction": "press", "name": "E"},
        ]

        layout = sd.compose_layout(None, static, key_count=15)

        self.assertIsNone(layout[0])
        self.assertEqual([sd.note_for(k, layout) for k in range(10, 14)], [36, 37, 38, 39])
        self.assertIsNone(sd.note_for(14, layout))


if __name__ == "__main__":
    unittest.main()
