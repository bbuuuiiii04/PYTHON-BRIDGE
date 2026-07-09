from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from types import SimpleNamespace

from rb_ss_bridge_v2.led_color_engine import LedColorEngine
from rb_ss_bridge_v2.led_dispatch_policy import LEDDispatchPolicyMixin
from rb_ss_bridge_v2.led_models import ColorEngineConfig, IdentityV2Config, Palette, ZoneRampConfig
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


def _v2_config() -> ColorEngineConfig:
    zones = {
        name: ZoneRampConfig(
            base_ramp=((10, 40, 120), (0, 120, 255), (0, 220, 255)),
            accent_ramp=((120, 240, 255), (210, 250, 255)),
        )
        for name in ("GLACIER", "DEEP_POOL", "TWILIGHT", "ION", "VOLT", "EMBERCORE", "NEUTRAL")
    }
    return ColorEngineConfig(
        enabled=True,
        scale_stops=_config().scale_stops,
        palettes=_config().palettes,
        v2=IdentityV2Config(enabled=True, zones=zones),
    )


class _WriterStub:
    instances: list["_WriterStub"] = []

    def __init__(self, path: str = "", *_args, **_kwargs) -> None:
        # Mirrors the real PaletteFeedbackWriter's `_path` attribute name so
        # tests can assert on the path LedPaletteControl resolved without
        # spinning up a real writer thread.
        self._path = path
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

    def _pad_phase(self, name: str, phase: str, now: float) -> None:
        with mock.patch("rb_ss_bridge_v2.led_palette_control.time.monotonic",
                        return_value=now):
            self.control.handle_event(BridgeEvent(
                kind=Ev.LED_PALETTE_PAD,
                deck=0,
                payload={"name": name, "phase": phase},
                source="test",
            ))

    def test_v2_zone_manual_and_max_energy_controls(self) -> None:
        engine = LedColorEngine(_v2_config(), set_seed=7)
        engine.begin_dispatch(
            active_deck=1,
            load_gen=1,
            content_id="track-a",
            filepath="/tmp/a.mp3",
            role="groove",
            section_id="s1",
            cycle=1,
        )
        applied: list[str] = []
        cleared: list[bool] = []
        max_energy: list[bool] = []
        control = LedPaletteControl(
            engine=engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: 8.0,
            get_phrase_anchor=lambda _beat: 16.0,
            get_laser_blackout=lambda: False,
            get_engine_mode=lambda: "v2",
            apply_zone_correction=applied.append,
            clear_zone_correction=lambda: cleared.append(True),
            toggle_max_energy=lambda: max_energy.append(True),
            palette_notes={"white_sand": 56},
            zone_notes={"GLACIER": 62, "ION": 65},
            manual_notes={"red": 68},
            max_energy_note=71,
        )
        self.addCleanup(control.stop)

        with mock.patch("rb_ss_bridge_v2.led_palette_control.time.monotonic", return_value=1.0):
            control.handle_event(BridgeEvent(kind=Ev.LED_ZONE_PAD, deck=0, payload={"name": "GLACIER", "phase": "down"}))
        with mock.patch("rb_ss_bridge_v2.led_palette_control.time.monotonic", return_value=1.1):
            control.handle_event(BridgeEvent(kind=Ev.LED_ZONE_PAD, deck=0, payload={"name": "GLACIER", "phase": "up"}))
        self.assertEqual(engine.snapshot()["staged_zone"], "GLACIER")

        with mock.patch("rb_ss_bridge_v2.led_palette_control.time.monotonic", return_value=2.0):
            control.handle_event(BridgeEvent(kind=Ev.LED_ZONE_PAD, deck=0, payload={"name": "ION", "phase": "down"}))
        with mock.patch("rb_ss_bridge_v2.led_palette_control.time.monotonic", return_value=3.0):
            control.handle_event(BridgeEvent(kind=Ev.LED_ZONE_PAD, deck=0, payload={"name": "ION", "phase": "up"}))
        self.assertEqual(applied, ["ION"])

        control.handle_event(BridgeEvent(kind=Ev.LED_MANUAL_PAD, deck=0, payload={"name": "red"}))
        self.assertEqual(engine.snapshot()["manual"], "red")
        control.handle_event(BridgeEvent(kind=Ev.LED_MANUAL_PAD, deck=0, payload={"name": "red"}))
        self.assertEqual(engine.snapshot()["manual"], "")

        control.handle_event(BridgeEvent(kind=Ev.LED_MAX_ENERGY_PAD, deck=0))
        self.assertEqual(max_energy, [True])

    def _tap_v2(self, name: str, *, down: float = 10.0, up: float = 10.1) -> None:
        self._pad_phase(name, "down", down)
        self._pad_phase(name, "up", up)

    def _hold_v2(self, name: str, *, down: float = 10.0, up: float = 10.6) -> None:
        self._pad_phase(name, "down", down)
        self._pad_phase(name, "up", up)

    def test_tap_same_pad_unqueues_without_fade(self) -> None:
        self._pad("violet")
        self.assertEqual(self.engine.snapshot()["queued_palette"], "violet")

        self._pad("violet")
        snap = self.engine.snapshot()

        self.assertEqual(snap["queued_palette"], "")
        self.assertFalse(snap["fading"])
        self.assertEqual(snap["fade_target"], "")

    def test_phase_tap_queues_and_replaces_existing_queue(self) -> None:
        self._tap_v2("violet")
        self.assertEqual(self.engine.snapshot()["queued_palette"], "violet")

        self._tap_v2("blue_cyan", down=11.0, up=11.1)

        self.assertEqual(self.engine.snapshot()["queued_palette"], "blue_cyan")

    def test_phase_tap_again_unqueues_and_next_boundary_does_not_apply_it(self) -> None:
        self._tap_v2("violet")
        self._tap_v2("violet", down=11.0, up=11.1)

        self.assertEqual(self.engine.snapshot()["queued_palette"], "")
        self.engine.begin_dispatch(
            active_deck=1,
            load_gen=2,
            content_id="track-b",
            filepath="",
            role="groove",
            section_id="groove-1",
            cycle=0,
        )

        self.assertEqual(self.engine.snapshot()["current_palette"], "blue_cyan")
        self.assertEqual(self.engine.snapshot()["queued_palette"], "")

    def test_phase_tap_locked_active_pad_unlocks_without_repick(self) -> None:
        self.engine.set_palette("violet")
        self.engine.lock()

        self._tap_v2("violet")

        snap = self.engine.snapshot()
        self.assertFalse(snap["lock"])
        self.assertEqual(snap["current_palette"], "violet")
        self.assertEqual(snap["queued_palette"], "")

    def test_phase_tap_different_pad_under_lock_queues_and_keeps_lock(self) -> None:
        self.engine.set_palette("blue_cyan")
        self.engine.lock()

        self._tap_v2("violet")

        snap = self.engine.snapshot()
        self.assertTrue(snap["lock"])
        self.assertEqual(snap["current_palette"], "blue_cyan")
        self.assertEqual(snap["queued_palette"], "violet")

    def test_phase_long_press_overrides_then_locks(self) -> None:
        calls: list[str] = []
        original_override = self.engine.override_palette
        original_lock = self.engine.lock

        def override_wrapper(*args, **kwargs):
            calls.append("override")
            return original_override(*args, **kwargs)

        def lock_wrapper():
            calls.append("lock")
            return original_lock()

        with mock.patch.object(self.engine, "override_palette",
                               side_effect=override_wrapper), \
                mock.patch.object(self.engine, "lock", side_effect=lock_wrapper):
            self._hold_v2("violet")

        snap = self.engine.snapshot()
        self.assertEqual(calls, ["override", "lock"])
        self.assertTrue(snap["lock"])
        self.assertTrue(snap["fading"])
        self.assertEqual(snap["fade_target"], "violet")
        self.assertEqual(snap["queued_palette"], "")

    def test_phase_long_press_consumes_existing_queue(self) -> None:
        self._tap_v2("blue_cyan")
        self.assertEqual(self.engine.snapshot()["queued_palette"], "blue_cyan")

        self._hold_v2("violet")

        snap = self.engine.snapshot()
        self.assertTrue(snap["lock"])
        self.assertEqual(snap["queued_palette"], "")
        self.assertEqual(snap["fade_target"], "violet")

    def test_phase_long_press_transfers_lock_to_another_palette(self) -> None:
        self.engine.set_palette("blue_cyan")
        self.engine.lock()

        self._hold_v2("violet")
        self.engine.advance_fade(16.0)

        snap = self.engine.snapshot()
        self.assertTrue(snap["lock"])
        self.assertEqual(snap["current_palette"], "violet")
        self.assertEqual(snap["fade_target"], "")

    def test_override_fade_ends_on_phrase_grid_not_press_plus_32(self) -> None:
        # Operator rule 2026-07-05: the override-fade must finish on the 32-beat
        # grid measured from the last phrase marker (phrase midpoint or next
        # phrase), NOT a fixed 32 beats from wherever the press landed.
        # PHRASE_ANCHOR_BEATS=64, so next phrase anchor 64 => midpoint 32.
        captured: dict[str, float] = {}

        def spy(_name, *, start_beat, end_beat):
            captured["start"], captured["end"] = start_beat, end_beat

        with mock.patch.object(self.engine, "override_palette", side_effect=spy):
            # Press in the FIRST half of the phrase -> finish at the midpoint
            # (32), not press+32 (10+32=42).
            self.control._get_abs_beat = lambda: 10.0
            self.control._get_phrase_anchor = lambda _b: 64.0
            self.control._override_palette_now("violet")
            self.assertEqual(captured["end"], 32.0)

            # Press in the SECOND half -> finish at the next phrase (64), not 72.
            self.control._get_abs_beat = lambda: 40.0
            self.control._override_palette_now("violet")
            self.assertEqual(captured["end"], 64.0)

    def test_phase_long_press_same_locked_palette_noops(self) -> None:
        self.engine.set_palette("violet")
        self.engine.lock()

        with mock.patch.object(self.engine, "override_palette") as override, \
                mock.patch.object(self.engine, "set_palette") as set_palette, \
                mock.patch.object(self.engine, "lock") as lock:
            self._hold_v2("violet")

        override.assert_not_called()
        set_palette.assert_not_called()
        lock.assert_not_called()
        self.assertEqual(self.engine.snapshot()["current_palette"], "violet")
        self.assertTrue(self.engine.snapshot()["lock"])

    def test_phase_long_press_without_beat_authority_applies_and_locks(self) -> None:
        engine = LedColorEngine(_config(), set_seed=3)
        control = LedPaletteControl(
            engine=engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: None,
            get_phrase_anchor=lambda _beat: None,
            get_laser_blackout=lambda: False,
            palette_notes={"blue_cyan": 51, "violet": 52},
            control_notes={},
        )
        self.addCleanup(control.stop)

        def phase(name: str, value: str, now: float) -> None:
            with mock.patch("rb_ss_bridge_v2.led_palette_control.time.monotonic",
                            return_value=now):
                control.handle_event(BridgeEvent(
                    kind=Ev.LED_PALETTE_PAD,
                    deck=0,
                    payload={"name": name, "phase": value},
                    source="test",
                ))

        phase("violet", "down", 20.0)
        phase("violet", "up", 20.6)

        snap = engine.snapshot()
        self.assertEqual(snap["current_palette"], "violet")
        self.assertTrue(snap["lock"])
        self.assertFalse(snap["fading"])

    def test_phase_subthreshold_release_and_missing_down_record_are_taps(self) -> None:
        self._tap_v2("violet", down=10.0, up=10.49)
        self.assertEqual(self.engine.snapshot()["queued_palette"], "violet")
        self.engine.unqueue_palette("violet")

        self._pad_phase("violet", "up", 12.0)

        self.assertEqual(self.engine.snapshot()["queued_palette"], "violet")

    def test_legacy_shape_empty_intent_is_a_tap(self) -> None:
        self._pad("violet", intent="")

        self.assertEqual(self.engine.snapshot()["queued_palette"], "violet")

    def test_rainbow_makes_phase_pads_inert(self) -> None:
        self.control.handle_event(BridgeEvent(kind=Ev.LED_RAINBOW_PAD, deck=0, payload={}, source="test"))
        before = self.engine.snapshot()

        self._pad_phase("violet", "down", 10.0)
        self._pad_phase("violet", "up", 11.0)

        self.assertEqual(self.engine.snapshot(), before)

    def test_runtime_command_intents_keep_legacy_noops_and_no_beat_fallback(self) -> None:
        self.control.handle_event(BridgeEvent(
            kind=Ev.LED_PALETTE_PAD,
            deck=0,
            payload={"name": "", "intent": "queue"},
            source="test",
        ))
        self.assertEqual(self.engine.snapshot()["queued_palette"], "")

        engine = LedColorEngine(_config(), set_seed=3)
        control = LedPaletteControl(
            engine=engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: None,
            get_phrase_anchor=lambda _beat: None,
            get_laser_blackout=lambda: False,
            palette_notes={"blue_cyan": 51, "violet": 52},
            control_notes={},
        )
        self.addCleanup(control.stop)
        control.handle_event(BridgeEvent(
            kind=Ev.LED_PALETTE_PAD,
            deck=0,
            payload={"name": "violet", "intent": "override"},
            source="test",
        ))

        snap = engine.snapshot()
        self.assertEqual(snap["current_palette"], "violet")
        self.assertFalse(snap["lock"])

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

        # AWR-159 Task 3/5: "pending" (auto-tier queued) reads the same as
        # "armed" for display; "refused" is its own distinct state.
        state["value"] = "pending"
        self.assertEqual(control._control_payload()["laser_solo"]["state"], "queued")

        state["value"] = "refused"
        self.assertEqual(control._control_payload()["laser_solo"]["state"], "refused")

    def test_static_held_payload_reflects_supplied_getter(self) -> None:
        control = LedPaletteControl(
            engine=self.engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: 8.0,
            get_phrase_anchor=lambda _beat: 16.0,
            get_laser_blackout=lambda: False,
            get_static_held=lambda: ((2, 36, "toggle"),),
        )
        self.addCleanup(control.stop)
        writer = _WriterStub.instances[-1]
        self.assertEqual(
            writer.payloads[-1]["static_held"],
            [{"channel": 2, "note": 36, "kind": "toggle"}],
        )

    def test_static_held_payload_empty_when_getter_absent(self) -> None:
        writer = _WriterStub.instances[-1]
        self.assertEqual(writer.payloads[-1]["static_held"], [])

    def test_static_held_change_gate_fires_when_held_set_changes(self) -> None:
        state = {"held": ()}
        control = LedPaletteControl(
            engine=self.engine,
            led_event_sink=self.events.append,
            get_abs_beat=lambda: 8.0,
            get_phrase_anchor=lambda _beat: 16.0,
            get_laser_blackout=lambda: False,
            get_static_held=lambda: state["held"],
        )
        self.addCleanup(control.stop)
        writer = _WriterStub.instances[-1]
        before = len(writer.payloads)
        control.maybe_publish()
        self.assertEqual(len(writer.payloads), before)

        state["held"] = ((2, 36, "toggle"),)
        control.maybe_publish()
        self.assertEqual(len(writer.payloads), before + 1)
        self.assertEqual(
            writer.payloads[-1]["static_held"],
            [{"channel": 2, "note": 36, "kind": "toggle"}],
        )

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
        control.handle_event(BridgeEvent(
            kind=Ev.LED_PALETTE_PAD, deck=0,
            payload={"name": "blue_cyan", "intent": "override"}, source="test",
        ))
        snap = control._engine.snapshot()
        self.assertEqual(snap["current_palette"], "blue_cyan")
        self.assertFalse(snap["fading"])
        self.assertEqual(snap["queued_palette"], "")
        self.assertFalse(snap["lock"])

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

    def test_default_feedback_path_never_falls_back_to_live_file(self) -> None:
        # Ghost-writer regression (2026-07-04): an ad-hoc script that never
        # imports tests/ (so tests/__init__.py's env override never runs)
        # must still be structurally unable to default to the live operator
        # feedback file. With RBSS_PALETTE_STATE_PATH absent, construction
        # must fall back to a per-pid throwaway; with it present, the
        # override must win.
        live_path = "/tmp/rb_ss_bridge_v2_palette_state.json"
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RBSS_PALETTE_STATE_PATH", None)
            control = LedPaletteControl(
                engine=self.engine,
                led_event_sink=self.events.append,
                get_abs_beat=lambda: 8.0,
                get_phrase_anchor=lambda _beat: 16.0,
                get_laser_blackout=lambda: False,
            )
            try:
                resolved = control._writer._path
                self.assertNotEqual(resolved, live_path)
                self.assertIn(str(os.getpid()), resolved)
            finally:
                control.stop()

            os.environ["RBSS_PALETTE_STATE_PATH"] = "/tmp/rbss_test_override_marker.json"
            control2 = LedPaletteControl(
                engine=self.engine,
                led_event_sink=self.events.append,
                get_abs_beat=lambda: 8.0,
                get_phrase_anchor=lambda _beat: 16.0,
                get_laser_blackout=lambda: False,
            )
            try:
                self.assertEqual(control2._writer._path, "/tmp/rbss_test_override_marker.json")
            finally:
                control2.stop()


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


class PaletteFeedbackWriterTransitionTests(unittest.TestCase):
    def test_write_failures_and_recovery_log_once_per_transition(self) -> None:
        writer = PaletteFeedbackWriter("/tmp/unused_transition_test.json")

        with mock.patch("rb_ss_bridge_v2.led_palette_control.atomic_write_json",
                        side_effect=OSError("disk")):
            with self.assertLogs("rbss.palette_control", level="WARNING") as captured:
                writer._write_once({"seq": 1})
                writer._write_once({"seq": 2})  # steady failure: silent
        self.assertEqual(len(captured.output), 1)
        self.assertIn("feedback_write_failed", captured.output[0])

        with mock.patch("rb_ss_bridge_v2.led_palette_control.atomic_write_json"):
            with self.assertLogs("rbss.palette_control", level="INFO") as captured:
                writer._write_once({"seq": 3})
                writer._write_once({"seq": 4})  # steady success: silent
        self.assertEqual(len(captured.output), 1)
        self.assertIn("feedback_write_recovered", captured.output[0])
        self.assertEqual(writer._last_payload, {"seq": 4})


class FeedbackProducerDeckContractTests(unittest.TestCase):
    """Every field the producer publishes must survive the deck projection —
    the class of bug that silently dropped `ramp` between the producer and
    the renderer (2026-07-04 incident 3)."""

    def test_all_producer_fields_survive_deck_projection(self) -> None:
        _WriterStub.instances.clear()
        events: list[BridgeEvent] = []
        with mock.patch("rb_ss_bridge_v2.led_palette_control.PaletteFeedbackWriter",
                        _WriterStub):
            control = LedPaletteControl(
                engine=LedColorEngine(_config(), set_seed=3),
                led_event_sink=events.append,
                get_abs_beat=lambda: 8.0,
                get_phrase_anchor=lambda _beat: 16.0,
                get_laser_blackout=lambda: False,
                palette_notes={"blue_cyan": 51, "violet": 52, "white_sand": 56},
                control_notes={"lock": 57, "led_mute": 58, "laser_mute": 59,
                               "laser_solo": 60, "rainbow": 61},
            )
            self.addCleanup(control.stop)
        payload = _WriterStub.instances[-1].payloads[-1]

        layout = sd.compose_layout(payload, [], key_count=15)
        rows_by_note = {row["note"]: row
                        for row in layout if isinstance(row, dict)}

        for producer_row in payload["palettes"]:
            deck_row = rows_by_note[producer_row["note"]]
            dropped = set(producer_row) - set(deck_row)
            self.assertFalse(dropped, f"palette fields dropped: {dropped}")
        for key, producer_row in payload["controls"].items():
            if key == "lock":
                self.assertNotIn(producer_row["note"], rows_by_note)
                continue
            deck_row = rows_by_note[producer_row["note"]]
            dropped = set(producer_row) - set(deck_row)
            self.assertFalse(dropped, f"control '{key}' fields dropped: {dropped}")


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


class AdvancePaletteFadeAndPublishTests(unittest.TestCase):
    """Fix 1/2 (2026-07-05): the per-tick fade advance + feedback republish that
    replaced the role-key-gated advance_fade inside _dispatch_led_automation."""

    def _harness(self, snap: dict, *, abs_beat=32.0, enabled=True):
        engine = SimpleNamespace(enabled=enabled, advance_calls=[], _snap=snap)
        engine.advance_fade = lambda b: engine.advance_calls.append(b)
        engine.snapshot = lambda: engine._snap
        control = SimpleNamespace(publishes=0)
        control.maybe_publish = lambda: setattr(control, "publishes", control.publishes + 1)
        sm = SimpleNamespace(
            _led_color_engine=engine,
            _led_palette_control=control,
            _palette_feedback_sig=None,
            _led_last_error="",
            _led_abs_beat=lambda _sp: abs_beat,
        )
        return sm, engine, control

    def _run(self, sm):
        LEDDispatchPolicyMixin._advance_palette_fade_and_publish(sm, sp_state=None)

    def test_advances_every_tick_and_publishes_only_on_change(self):
        sm, engine, control = self._harness(
            {"current_palette": "blue_cyan", "fade_target": "crimson",
             "fading": True, "lock": True, "queued_palette": ""})

        self._run(sm)
        self.assertEqual(engine.advance_calls, [32.0])   # advanced this tick
        self.assertEqual(control.publishes, 1)           # None -> set: republish

        self._run(sm)                                    # same palette state
        self.assertEqual(engine.advance_calls, [32.0, 32.0])  # still advances
        self.assertEqual(control.publishes, 1)           # unchanged: no republish

        # Fade commits inside the engine (snapshot flips to crimson, no fade).
        engine._snap = {"current_palette": "crimson", "fade_target": "",
                        "fading": False, "lock": True, "queued_palette": ""}
        self._run(sm)
        self.assertEqual(control.publishes, 2)           # commit mirrored to deck

    def test_disabled_or_missing_engine_is_noop(self):
        sm, engine, control = self._harness({"current_palette": "x"}, enabled=False)
        self._run(sm)
        self.assertEqual(engine.advance_calls, [])
        self.assertEqual(control.publishes, 0)

    def test_no_abs_beat_skips_advance_but_still_mirrors_state(self):
        sm, engine, control = self._harness(
            {"current_palette": "crimson", "fade_target": "", "fading": False,
             "lock": False, "queued_palette": ""}, abs_beat=None)
        self._run(sm)
        self.assertEqual(engine.advance_calls, [])       # no beat: no advance
        self.assertEqual(control.publishes, 1)           # but deck still synced


if __name__ == "__main__":
    unittest.main()
