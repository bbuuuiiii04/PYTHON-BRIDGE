"""T7c — StateManager SoundSwitch pack driver tests.

No real MIDI/serial/Enttec/DMX/network. A real LaserPackPlayer drives a tiny
synthetic pack; a fake backend records submitted frames; deck/snap state is
synthetic. See docs/plans/active/soundswitch_t7c_pack_driver_spec.md (Part D).
"""
from __future__ import annotations

import queue
import os
import unittest
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.state_manager import StateManager, _pack_operational_state
from rb_ss_bridge_v2.rb_memory import PositionCache
from rb_ss_bridge_v2.models import BridgeEvent, Ev, PositionSnapshot
from rb_ss_bridge_v2.laser_models import LaserResolvedScene
from rb_ss_bridge_v2.soundswitch_laser_player import (
    ZERO_FRAME, LaserPackPlayer,
)
from rb_ss_bridge_v2.soundswitch_midi_input import LayerEntry
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute, LoadedAutoloop, LoadedAutoloopBinding, LoadedDocument,
    LoadedPack, LoadedStaticLook, LoadedScalarValue, LoadedTimelineEvent,
)
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime
from rb_ss_bridge_v2.soundswitch_midi_input import SoundSwitchMidiInputGroup
from rb_ss_bridge_v2.scripted_tracks import SCRIPTED_TRACKS, register
SSID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SSID2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"   # valid UUID, ABSENT from _pack()
FRESH = SimpleNamespace(is_stale=lambda _s: False)
STALE = SimpleNamespace(is_stale=lambda _s: True)


# --- tiny synthetic pack -----------------------------------------------------
def _event(time, order, patch):
    return LoadedTimelineEvent(
        time=time, source_order=order, source_offset=100 + order,
        reference_kind="cue", raw_reference=order + 1,
        patch=tuple(LoadedAttribute(0x493, ch, ch, val) for ch, val in patch))


def _look(slot, values):
    return LoadedStaticLook(
        slot_index=slot, record_version=5, name=f"slot-{slot}",
        generic_attributes=tuple(LoadedAttribute(0x493, i, i, v)
                                 for i, v in enumerate(values, 1)),
        intensity_values=(LoadedScalarValue(1, 1, 0.5),),
        strobe_values=(), colour_values=(), position_values=())


def _pack():
    script = LoadedDocument("synthetic.ssfile", "shared_441_dictionary_timeline",
                            (_event(0, 0, ((1, 5),)), _event(50, 1, ((1, 9),))), (), 19_200)
    return LoadedPack(
        schema_version="1.0.0", manifest_sha256="0" * 64, has_intensity_channel=False,
        scripted=MappingProxyType({SSID: script}), autoloops=MappingProxyType({}),
        static_looks=MappingProxyType({8: _look(8, (200,) + (0,) * 18)}))


def _native_pack(*, empty=False, layout="shared_441_dictionary_timeline"):
    script = LoadedDocument("synthetic.ssfile", "shared_441_dictionary_timeline",
                            (_event(0, 0, ((1, 5),)), _event(50, 1, ((1, 9),))), (), 19_200)
    loop_events = () if empty else (_event(0, 0, ((1, 77),)),)
    loop_doc = LoadedDocument("SSAutoLoop4.ssfile", layout, loop_events, (), 19_200)
    loop = LoadedAutoloop("SSAutoLoop4.ssfile", True, loop_doc)
    return LoadedPack(
        schema_version="1.0.0", manifest_sha256="1" * 64, has_intensity_channel=False,
        scripted=MappingProxyType({SSID: script}),
        autoloops=MappingProxyType({"SSAutoLoop4.ssfile": loop}),
        static_looks=MappingProxyType({8: _look(8, (200,) + (0,) * 18)}),
        autoloop_bindings=MappingProxyType({
            (0, 96): LoadedAutoloopBinding(0, 96, "SSAutoLoop4.ssfile", "House Drop"),
        }),
    )


def _resolved_scene(note=96, *, role="drop", scene="house_drop_1", reason="drop_crossing"):
    return LaserResolvedScene(role, reason, scene, 1, note, "static")


def _layer_tuple(slot: int) -> tuple[LayerEntry, ...]:
    return (LayerEntry(slot, "toggle", 1),)


class _FakeBackend:
    def __init__(self):
        self.frames = []

    def submit_frame(self, frame):
        self.frames.append(tuple(frame))

    def trigger(self, msg, priority="normal"):
        return True

    def status(self):
        return {"backend": "fake"}

    def reset(self):
        pass

    def shutdown(self):
        pass


class _FakeTruthSink:
    def __init__(self):
        self.frames = []
        self.intents = []

    def submit_frame(self, frame, intent):
        self.frames.append(tuple(frame))
        self.intents.append(dict(intent))

    def status(self):
        return {
            "enabled": True,
            "run_id": "fake-run",
            "universe": 1,
            "sidecar_path": "/tmp/fake.jsonl",
            "current_sequence": len(self.frames),
            "dropped_count": 0,
            "overflow_count": 0,
            "send_error_count": 0,
            "sidecar_error": "",
        }


class _FakeInput:
    # The driver reads .blackout_held/.held_layers plus RW-4 health fields
    # (.worker_alive/.error/.mail_drop_count) from the snapshot.
    def __init__(self, *, held_layer_slot=None, held_layers=None, blackout_held=False,
                 worker_alive=True, error=None, mail_drop_count=0,
                 blackout_bindings=()):
        if held_layers is None:
            held_layers = (() if held_layer_slot is None else _layer_tuple(int(held_layer_slot)))
        self._snap = SimpleNamespace(
            held_layers=held_layers, blackout_held=blackout_held,
            worker_alive=worker_alive, error=error, mail_drop_count=mail_drop_count,
            blackout_bindings=tuple(blackout_bindings))
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self._snap


class _RunClock:
    def __init__(self, start=100.0):
        self.now = start
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration

    def spend_tick(self):
        self.now += StateManager._TICK_INTERVAL * 2


def _make_sm(*, player=None, backend=None, midi_input=None, enabled=None,
             os2l_connected_provider=None, truth_sink=None):
    if enabled is None:
        enabled = player is not None and backend is not None
    rt = PackRuntime(
        enabled=enabled, reason="pack" if enabled else "disabled",
        player=player, midi_input=midi_input, backend=backend,
        truth_sink=truth_sink)
    return StateManager(
        queue.Queue(), PositionCache(), mock.Mock(), soundswitch_pack_runtime=rt,
        os2l_connected_provider=os2l_connected_provider)


def _set(sm, *, ssid="", elapsed_ms=0, playing=False, load_gen=1, snap=FRESH,
         active=1, was_playing=None, scripted_id=None, lighting_mode=None):
    if was_playing is None:
        was_playing = playing
    if scripted_id is None:
        scripted_id = 1 if ssid else 0   # ssid present ⇒ bridge-owned scripted, by default
    if lighting_mode is None:
        lighting_mode = "scripted" if scripted_id else "idle"
    sm._os = SimpleNamespace(
        active_deck=active, was_playing=was_playing, lighting_mode=lighting_mode)
    sm._deck = {active: SimpleNamespace(
        meta=SimpleNamespace(soundswitch_id=ssid), elapsed_ms=elapsed_ms,
        playing=playing, load_gen=load_gen, scripted_id=scripted_id)}
    sm._cache = SimpleNamespace(get=lambda _dk: snap)


class PackOperationalStateTests(unittest.TestCase):
    def test_precedence_table(self):
        defaults = dict(
            enabled=True,
            blackout=False,
            input_degraded=False,
            static_held=False,
            scripted_active=False,
            autoloop_phase_blocked=False,
            software_zero_frame=True,
        )
        cases = (
            ({"enabled": False, "blackout": True}, "disabled"),
            ({"blackout": True, "input_degraded": True}, "blackout"),
            ({"input_degraded": True, "static_held": True}, "input_degraded"),
            ({"static_held": True, "scripted_active": True}, "static_held"),
            ({"parity_live_blocked": True, "scripted_active": True}, "unverified_parity"),
            ({"scripted_active": True, "autoloop_phase_blocked": True}, "scripted_active"),
            ({"autoloop_phase_blocked": True}, "autoloop_phase_blocked"),
            ({}, "software_zero_frame"),
            ({"input_degraded": True, "scripted_active": True}, "input_degraded"),
        )
        for updates, expected in cases:
            with self.subTest(expected=expected, updates=updates):
                self.assertEqual(
                    _pack_operational_state(**(defaults | updates)),
                    expected,
                )


class PackDriverTests(unittest.TestCase):
    # D1
    def test_default_off_is_neutral(self):
        sm = _make_sm()  # no pack params -> disabled runtime
        self.assertFalse(sm._pack_runtime.active)
        sm._drive_pack_output()  # inactive -> no-op, no raise

    # D2
    def test_scripted_playing_fresh_submits_nonzero(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(len(be.frames), 1)
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        self.assertEqual(be.frames[-1][0], 9)  # CH1 of the scripted frame at 50ms

    # D3
    def test_no_track_with_held_static_submits_static(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        self.assertEqual(be.frames[-1][0], 200)  # CH1 of static look slot 8

    def test_dead_controller_does_not_block_stream_deck_static_in_pack(self):
        # End-to-end regression for the group-health poison: a held Stream Deck static
        # look renders in the pack DMX even though a co-learned DDJ-800 controller is
        # absent (port-gone). Before the group overlay-trust fix this frame was ZERO
        # (one dead controller dropped every controller's held look).
        from rb_ss_bridge_v2.soundswitch_midi_input import SoundSwitchMidiInputAdapter
        from rb_ss_bridge_v2.soundswitch_pack_loader import PackMidiBinding
        sd = PackMidiBinding(device_name="Stream Deck", message_type="note",
                             channel_zero_based=2, data_byte=36,
                             target_kind="static_look", target_slot=8, interaction="toggle")
        ddj = PackMidiBinding(device_name="DDJ-800", message_type="note",
                              channel_zero_based=9, data_byte=123,
                              target_kind="static_look", target_slot=17)
        made: dict = {}

        def factory(bindings, *, stale_timeout_ms):
            adapter = SoundSwitchMidiInputAdapter(bindings, stale_timeout_ms=stale_timeout_ms)
            made[bindings[0].device_name] = adapter
            return adapter

        group = SoundSwitchMidiInputGroup((sd, ddj), {}, adapter_factory=factory)
        made["Stream Deck"]._worker_alive = True
        made["Stream Deck"]._feed_raw_message(0x90 | 2, 36, 100)  # operator holds slot 8
        made["DDJ-800"]._mark_port_gone()                          # absent controller

        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=group)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)   # Stream Deck static slot 8 rendered
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)

    def test_soundswitch_connected_suppresses_pack_output(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(
            player=LaserPackPlayer(_pack()),
            backend=be,
            midi_input=inp,
            os2l_connected_provider=lambda: True,
        )
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        sm._pack_play_hold_key = (1, 1, 1, SSID)
        sm._pack_play_hold_deadline = 999.0

        sm._drive_pack_output(now=10.0)

        self.assertEqual(be.frames, [ZERO_FRAME])
        self.assertEqual(inp.calls, 0)
        self.assertEqual(sm._pack_last_static_layers, ())
        self.assertIsNone(sm._pack_play_hold_key)
        self.assertEqual(sm._pack_play_hold_deadline, 0.0)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "soundswitch_present_native_suppressed")
        self.assertEqual(status["native_autoloop"]["status"], "soundswitch_present_native_suppressed")
        self.assertTrue(status["autoloop_phase_blocked"])
        self.assertTrue(status["software_zero_frame"])
        self.assertFalse(status["scripted_active"])
        self.assertFalse(status["static_held"])
        self.assertFalse(status["blackout"])

    def test_truth_check_shadow_renders_scripted_while_production_suppressed(self):
        be = _FakeBackend()
        truth = _FakeTruthSink()
        sm = _make_sm(
            player=LaserPackPlayer(_pack()),
            backend=be,
            truth_sink=truth,
            os2l_connected_provider=lambda: True,
        )
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)

        sm._drive_pack_output(now=10.0)

        self.assertEqual(be.frames, [ZERO_FRAME])
        self.assertEqual(truth.frames[-1][0], 9)
        self.assertEqual(truth.intents[-1]["mode"], "scripted")
        self.assertEqual(truth.intents[-1]["elapsed_ms"], 50)
        self.assertEqual(truth.intents[-1]["transport"], "playing")
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "soundswitch_present_native_suppressed")
        self.assertTrue(status["software_zero_frame"])
        self.assertEqual(status["truth_check"]["run_id"], "fake-run")

    def test_truth_check_shadow_renders_static_look_while_production_suppressed(self):
        be = _FakeBackend()
        truth = _FakeTruthSink()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(
            player=LaserPackPlayer(_pack()),
            backend=be,
            midi_input=inp,
            truth_sink=truth,
            os2l_connected_provider=lambda: True,
        )
        _set(sm, ssid="", playing=False, snap=FRESH)

        sm._drive_pack_output(now=10.0)

        self.assertEqual(be.frames, [ZERO_FRAME])
        self.assertEqual(truth.frames[-1][0], 200)
        self.assertEqual(truth.intents[-1]["mode"], "static")
        self.assertEqual(truth.intents[-1]["static_slots"], [8])

    def test_truth_check_intent_carries_blackout_binding_keys(self):
        be = _FakeBackend()
        truth = _FakeTruthSink()
        inp = _FakeInput(blackout_held=True, blackout_bindings=("0:0",))
        sm = _make_sm(
            player=LaserPackPlayer(_pack()),
            backend=be,
            midi_input=inp,
            truth_sink=truth,
            os2l_connected_provider=lambda: True,
        )
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)

        sm._drive_pack_output(now=10.0)

        self.assertEqual(be.frames, [ZERO_FRAME])
        self.assertEqual(truth.frames[-1], ZERO_FRAME)
        self.assertEqual(truth.intents[-1]["mode"], "blackout")
        self.assertEqual(truth.intents[-1]["blackout_bindings"], ["0:0"])

    def test_truth_check_shadow_renders_native_autoloop_while_production_suppressed(self):
        be = _FakeBackend()
        truth = _FakeTruthSink()
        sm = _make_sm(
            player=LaserPackPlayer(_native_pack()),
            backend=be,
            truth_sink=truth,
            os2l_connected_provider=lambda: True,
        )
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output(now=10.0)

        self.assertEqual(be.frames, [ZERO_FRAME])
        self.assertEqual(truth.frames[-1][0], 77)
        self.assertEqual(truth.intents[-1]["mode"], "autoloop")
        self.assertEqual(
            truth.intents[-1]["native_autoloop"]["target_identity"],
            "SSAutoLoop4.ssfile",
        )

    def test_native_autoloop_phase_advances_across_hold_ticks(self):
        """Regression: with a HELD autoloop (laser executor keeps reporting the
        active scene, but on_decision returns no fresh edge so
        _native_captured_scene is None on hold ticks), phase_tick must ADVANCE
        instead of re-anchoring to 0 every tick. Guards the
        current_autoloop_scene() bootstrap fallback (state_manager.py:4013) from
        manufacturing a fake edge each tick. See the 2026-07-01 all_surface
        capture: every Autoloop row had phase_tick=0."""
        be = _FakeBackend()
        truth = _FakeTruthSink()
        sm = _make_sm(
            player=LaserPackPlayer(_native_pack()),
            backend=be,
            truth_sink=truth,
            os2l_connected_provider=lambda: True,
        )
        # Live-like laser executor: HOLDS the active autoloop scene every call.
        sm._laser_executor = SimpleNamespace(
            current_autoloop_scene=lambda: _resolved_scene())
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")

        # Edge tick: captured scene delivers the trigger; anchor latches at 64.0.
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0
        sm._drive_pack_output(now=10.0)
        self.assertEqual(truth.intents[-1]["native_autoloop"]["phase_tick"], 0)

        # Hold tick: no fresh edge, laser still holds the scene, beat advanced +1.5.
        sm._native_captured_scene = None
        sm._native_abs_beat_pos = 65.5
        sm._drive_pack_output(now=10.1)
        self.assertEqual(truth.intents[-1]["native_autoloop"]["phase_tick"], 900)

    # D4
    def test_no_track_no_static_is_zero(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=_FakeInput())
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # D5 / RW-2 T2
    def test_confirmed_stop_zeros_scripted_base(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        sm._drive_pack_output(now=10.0)
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=False, snap=FRESH)
        sm._drive_pack_output(now=10.6)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-2 T1
    def test_pause_holds_current_scripted_frame(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        playing_frame = be.frames[-1]
        self.assertEqual(playing_frame[0], 9)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], playing_frame)

    # RW-2 T3
    def test_paused_frame_derives_from_events_not_cache(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=60, playing=True)
        sm._drive_pack_output(now=10.0)
        self.assertEqual(be.frames[-1][0], 9)
        _set(sm, ssid=SSID, elapsed_ms=30, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1][0], 5)

    def test_pause_hold_expires_to_zero(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.6)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    def test_loaded_unplayed_track_not_held(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, load_gen=1)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True, load_gen=2)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)
        self.assertIsNone(sm._pack_play_hold_key)
        self.assertEqual(sm._pack_play_hold_deadline, 0.0)

    # RW-2 T4
    def test_pause_then_resume_continues(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        _set(sm, ssid=SSID, elapsed_ms=60, playing=True)
        sm._drive_pack_output(now=10.2)
        self.assertEqual(be.frames[-1][0], 9)
        self.assertEqual(sm._pack_play_hold_deadline, 10.7)

    # RW-2 T5
    def test_pause_with_held_static_shows_static(self):
        be = _FakeBackend()
        inp = _FakeInput()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        inp._snap.held_layers = _layer_tuple(8)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1][0], 200)

    # RW-2 T6
    def test_pause_then_blackout_is_zero(self):
        be = _FakeBackend()
        inp = _FakeInput()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        inp._snap.blackout_held = True
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-2 T7
    def test_stale_while_paused_zeros(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True, snap=STALE)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-2 T8
    def test_unloaded_paused_zeros(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid="", elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-2 T9
    def test_track_change_while_paused_zeros(self):
        for held_static, expected in ((False, ZERO_FRAME), (True, 200)):
            with self.subTest(held_static=held_static):
                be = _FakeBackend()
                inp = _FakeInput()
                sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
                _set(sm, ssid=SSID, elapsed_ms=50, playing=True, load_gen=1)
                sm._drive_pack_output(now=10.0)
                if held_static:
                    inp._snap.held_layers = _layer_tuple(8)
                _set(sm, ssid=SSID, elapsed_ms=50, playing=False,
                     was_playing=True, load_gen=2)
                sm._drive_pack_output(now=10.1)
                if held_static:
                    self.assertEqual(be.frames[-1][0], expected)
                else:
                    self.assertEqual(be.frames[-1], expected)

    # RW-2 T10
    def test_seek_discontinuity_while_paused_zeros(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.1)
        _set(sm, ssid=SSID, elapsed_ms=3000, playing=False, was_playing=True)
        sm._drive_pack_output(now=10.2)
        self.assertEqual(be.frames[-1], ZERO_FRAME)
        sm._drive_pack_output(now=10.3)
        self.assertEqual(be.frames[-1][0], 9)

    # RW-2 T11
    def test_master_switch_zeros_until_new_deck_confirmed(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, active=1)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False,
             was_playing=True, active=1)
        sm._drive_pack_output(now=10.1)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False,
             was_playing=False, active=2)
        sm._drive_pack_output(now=10.2)
        self.assertEqual(be.frames[-1], ZERO_FRAME)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, active=2)
        sm._drive_pack_output(now=10.3)
        self.assertEqual(be.frames[-1][0], 9)
        self.assertEqual(sm._pack_play_hold_key, (2, 1, 1, SSID))

    # RW-3 R1
    def test_valid_ssid_but_unscripted_playing_zeros(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, scripted_id=0)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-3 R2
    def test_scripted_owned_playing_still_renders(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, scripted_id=7)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)

    # RW-3 R3
    def test_unscripted_pause_does_not_hold(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, scripted_id=7)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False,
             was_playing=True, scripted_id=0)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)
        self.assertIsNone(sm._pack_play_hold_key)
        self.assertEqual(sm._pack_play_hold_deadline, 0.0)

    # RW-3 R4
    def test_scripted_id_set_but_ssid_empty_zeros(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=7)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-3 R5
    def test_unscripted_in_pack_with_held_static_shows_static(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, playing=True, scripted_id=0)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    # RW-3 R7
    def test_pause_hold_not_resurrected_by_scripted_id_change(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True,
             load_gen=1, scripted_id=1)
        sm._drive_pack_output(now=10.0)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False,
             was_playing=True, load_gen=1, scripted_id=2)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)
        self.assertIsNone(sm._pack_play_hold_key)

    # RW-3 R9
    def test_mode_only_ignores_registry_identity(self):
        self.addCleanup(lambda: SCRIPTED_TRACKS.pop(7, None))
        register(7, {"name": "x", "ssid": SSID2})
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)

        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, scripted_id=7)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)

        _set(sm, ssid=SSID2, playing=True, scripted_id=7)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-3 R10
    def test_valid_uuid_missing_from_pack_with_held_static(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        # Pre-RW-3 the missing scripted selection suppressed static; the mode gate lets
        # the held authoritative overlay stand over the unowned ZERO base (A.6/C.5).
        _set(sm, ssid=SSID2, playing=True, scripted_id=0)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    # RW-3 R10b: an OWNED scripted track (scripted_id != 0) whose ssid is absent from
    # the pack can't render its scripted base; a held manual Static Look must stand
    # alone instead of the rig going dark.
    def test_owned_scripted_pack_miss_with_held_static_stands_alone(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID2, elapsed_ms=50, playing=True, scripted_id=7, snap=FRESH)
        sm._drive_pack_output(now=10.0)
        self.assertEqual(be.frames[-1][0], 200)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "static_held")

    # Same case must STILL go dark under blackout — static never beats blackout.
    def test_owned_scripted_pack_miss_with_held_static_loses_to_blackout(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, blackout_held=True)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID2, elapsed_ms=50, playing=True, scripted_id=7, snap=FRESH)
        sm._drive_pack_output(now=10.0)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # RW-3 R11
    def test_mirror_deck_clear_does_not_drop_active_hold(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, scripted_id=7)
        sm._drive_pack_output(now=10.0)
        active_hold = sm._pack_play_hold_key
        sm._deck[2] = SimpleNamespace(
            meta=SimpleNamespace(soundswitch_id=SSID2), scripted_id=9)

        sm._handle_event(BridgeEvent(
            kind=Ev.SCRIPTED_CLEAR, deck=2, payload={}, source="rw3-test",
        ))
        self.assertEqual(sm._deck[2].scripted_id, 0)
        self.assertEqual(sm._pack_play_hold_key, active_hold)

        _set(sm, ssid=SSID, elapsed_ms=50, playing=False,
             was_playing=True, scripted_id=7)
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1][0], 9)

    # D6
    def test_blackout_held_with_static_is_zero(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, blackout_held=True)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # D7
    def test_pack_disabled_emits_no_dmx(self):
        be = _FakeBackend()
        # A disabled runtime (player+backend present but enabled=False) drives nothing.
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, enabled=False)
        self.assertFalse(sm._pack_runtime.active)
        sm._drive_pack_output()
        self.assertEqual(be.frames, [])

    # D8
    def test_stale_authority_does_not_retain_old_frame(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        sm._drive_pack_output()
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=STALE)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # D9
    def test_track_change_zeros_base_for_that_tick(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, load_gen=1, snap=FRESH)
        sm._drive_pack_output()
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, load_gen=2, snap=FRESH)
        sm._drive_pack_output()  # load_gen changed -> track_changed -> ZERO this tick
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # Manual-static policy (explicit): manual static is operator-controlled via the
    # MIDI controller, an independent channel. It stays visible during stale/error/
    # track-change/discontinuity (deck-authority problems), and loses ONLY to
    # blackout/emergency/pack-disabled/shutdown. The controller's own hold-timeout
    # auto-releases it if the operator lets go.
    def test_stale_authority_with_held_static_shows_static(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=STALE)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)  # static look slot 8 stands alone

    def test_track_change_with_held_static_shows_static(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, load_gen=1, snap=FRESH)
        sm._drive_pack_output()
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, load_gen=2, snap=FRESH)
        sm._drive_pack_output()  # track changed -> automatic base ZERO, static stands alone
        self.assertEqual(be.frames[-1][0], 200)

    def test_shutdown_style_disable_drops_even_held_static(self):
        # Pack disabled (player/backend cleared) -> driver no-ops -> no DMX even with
        # a (previously) held static. (Shutdown ZEROs via the frame sender at __main__.)
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        sm.set_pack_runtime(PackRuntime())  # simulate disable/rollback (inactive)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames, [])

    def test_unverified_scripted_parity_live_fails_closed_with_status(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack(), parity_live=True), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1], ZERO_FRAME)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "unverified_parity")
        self.assertTrue(status["parity_live_blocked"])
        self.assertTrue(status["scripted_active"])
        self.assertTrue(status["software_zero_frame"])

    def test_unverified_scripted_parity_live_keeps_held_static_over_zero_base(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(
            player=LaserPackPlayer(_pack(), parity_live=True),
            backend=be,
            midi_input=inp,
        )
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1][0], 200)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "unverified_parity")
        self.assertTrue(status["parity_live_blocked"])
        self.assertTrue(status["static_held"])
        self.assertFalse(status["software_zero_frame"])

    def test_unverified_parity_does_not_change_soundswitch_present_shadow_path(self):
        be = _FakeBackend()
        sm = _make_sm(
            player=LaserPackPlayer(_pack(), parity_live=True),
            backend=be,
            os2l_connected_provider=lambda: True,
        )
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1], ZERO_FRAME)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "soundswitch_present_native_suppressed")
        self.assertFalse(status["parity_live_blocked"])

    # D10
    def test_native_autoloop_renders_from_captured_scene_and_latches_phase(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output()
        sm._native_captured_scene = None
        sm._native_abs_beat_pos = 65.5
        sm._drive_pack_output()

        self.assertEqual(be.frames[0][0], 77)
        self.assertEqual(be.frames[1][0], 77)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "rendering_active")
        self.assertFalse(status["autoloop_phase_blocked"])
        self.assertEqual(status["native_autoloop"]["target_identity"], "SSAutoLoop4.ssfile")
        self.assertEqual(status["native_autoloop"]["soundswitch_name"], "House Drop")
        self.assertEqual(status["native_autoloop"]["phase_tick"], 900)

    def test_native_autoloop_seeds_from_executor_latched_scene_without_new_edge(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        sm._laser_executor = SimpleNamespace(
            current_autoloop_scene=lambda: _resolved_scene(reason="latched_active")
        )
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = None
        sm._native_abs_beat_pos = 65.5

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1][0], 77)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "rendering_active")
        self.assertEqual(status["native_autoloop"]["reason"], "latched_active")

    def test_native_autoloop_empty_dark_look_is_not_missing_binding(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack(empty=True)), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1], ZERO_FRAME)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "empty_dark_look")
        self.assertEqual(status["native_autoloop"]["status"], "empty_dark_look")
        self.assertFalse(status["autoloop_phase_blocked"])

    def test_unverified_native_autoloop_parity_live_fails_closed_with_status(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack(), parity_live=True), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1], ZERO_FRAME)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "unverified_parity")
        self.assertTrue(status["parity_live_blocked"])
        self.assertEqual(status["native_autoloop"]["status"], "unverified_parity")
        self.assertTrue(status["autoloop_phase_blocked"])

    def test_native_missing_binding_fails_closed_and_does_not_select_autoloop(self):
        be = _FakeBackend()
        player = LaserPackPlayer(_native_pack())
        player.select_autoloop = mock.Mock(side_effect=AssertionError("select_autoloop banned"))
        sm = _make_sm(player=player, backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene(note=97, scene="house_drop_2")
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1], ZERO_FRAME)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "missing_binding")
        self.assertTrue(status["autoloop_phase_blocked"])
        player.select_autoloop.assert_not_called()

    def test_scripted_track_beats_native_autoloop(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, scripted_id=1, lighting_mode="scripted")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1][0], 9)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "scripted_active")
        self.assertTrue(status["scripted_active"])
        self.assertEqual(status["native_autoloop"]["status"], "software_zero_frame")

    def test_static_override_layers_over_native_autoloop(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be, midi_input=inp)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0

        sm._drive_pack_output()

        self.assertEqual(be.frames[-1][0], 200)
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "static_held")
        self.assertTrue(status["static_held"])
        self.assertEqual(status["native_autoloop"]["status"], "rendering_active")

    def test_reload_clears_stale_native_state_before_new_edge(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0
        sm._drive_pack_output()
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)

        new_backend = _FakeBackend()
        sm.set_pack_runtime(PackRuntime(
            enabled=True,
            reason="pack",
            player=LaserPackPlayer(_native_pack()),
            backend=new_backend,
            pack_sha12="newpack",
        ))
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = None
        sm._native_abs_beat_pos = 65.0
        sm._drive_pack_output()

        self.assertIsNone(sm._native_autoloop.state)
        self.assertEqual(new_backend.frames[-1], ZERO_FRAME)
        status = sm.get_pack_status()
        self.assertEqual(status["native_autoloop"]["reason"], "waiting_for_edge")

    def test_personality_change_resets_native_autoloop(self):
        # Authority doc reset boundary: "personality application, where role banks
        # change". A latched native look must be dropped when a personality applies.
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0
        sm._drive_pack_output()
        self.assertIsNotNone(sm._native_autoloop.state)  # latched look present

        sm._apply_personality_change("aggressive", None)

        self.assertIsNone(sm._native_autoloop.state)
        self.assertIsNone(sm._native_captured_scene)

    def test_native_autoloop_log_includes_soundswitch_display_name(self):
        # Operator observability: the throttled native-autoloop log must carry the
        # SoundSwitch display name (doc: display name available at runtime), without
        # adding phase_tick (which would spam the 200 Hz log).
        import logging
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")
        sm._native_captured_scene = _resolved_scene()
        sm._native_abs_beat_pos = 64.0
        with self.assertLogs("state_manager", level=logging.INFO) as cm:
            sm._drive_pack_output()
        blob = "\n".join(cm.output)
        self.assertIn("native-autoloop", blob)
        self.assertIn("name=House Drop", blob)
        self.assertNotIn("phase_tick=", blob)

    def test_native_autoloop_push_tick_uses_single_submit_path(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_native_pack()), backend=be)
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")

        def inner():
            sm._native_captured_scene = _resolved_scene()
            sm._native_abs_beat_pos = 64.0

        sm._push_tick_inner = inner
        sm._push_tick()

        self.assertEqual(len(be.frames), 1)
        self.assertEqual(be.frames[-1][0], 77)

    # D11 + D12
    def test_push_tick_drives_once_through_early_return(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._push_tick_inner = lambda: None  # simulate an early-returning inner tick
        sm._push_tick()
        self.assertEqual(len(be.frames), 1)  # exactly one submit_frame per tick

    # D13
    def test_inner_exception_submits_zero_and_reraises(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)

        def boom():
            raise ValueError("inner crash")

        sm._push_tick_inner = boom
        with self.assertRaises(ValueError):
            sm._push_tick()
        self.assertEqual(be.frames, [ZERO_FRAME])  # direct ZERO, driver not run

    def test_run_loop_drain_exception_sleeps_zero_logs_then_recovers(self):
        clock = _RunClock()
        be = _FakeBackend()
        with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
             mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep):
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
            drains = 0
            snapshots = []

            def drain():
                nonlocal drains
                drains += 1
                if drains == 1:
                    raise RuntimeError("drain crash")

            def publish(now):
                snapshots.append(now)
                clock.spend_tick()
                sm._stop.set()
                return False

            sm._drain_events = drain
            sm._push_tick = mock.Mock()
            sm._maybe_publish_snapshot = publish
            with self.assertLogs("state_manager", level="ERROR") as captured:
                sm._run()

        self.assertEqual(drains, 2)
        sm._push_tick.assert_called_once()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(be.frames, [ZERO_FRAME])
        self.assertEqual(len(clock.sleeps), 1)
        self.assertEqual(len(captured.output), 1)
        self.assertIn("RuntimeError", "\n".join(captured.output))

    def test_run_loop_push_tick_inner_exception_does_not_double_zero(self):
        clock = _RunClock()
        be = _FakeBackend()
        with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
             mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep):
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
            _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
            pushes = 0

            def inner():
                nonlocal pushes
                pushes += 1
                if pushes == 1:
                    raise ValueError("inner crash")

            def publish(_now):
                clock.spend_tick()
                sm._stop.set()
                return False

            sm._push_tick_inner = inner
            sm._maybe_publish_snapshot = publish
            with self.assertLogs("state_manager", level="ERROR") as captured:
                sm._run()

        self.assertEqual(pushes, 2)
        self.assertEqual(be.frames[0], ZERO_FRAME)
        self.assertNotEqual(be.frames[1], ZERO_FRAME)
        self.assertEqual(be.frames.count(ZERO_FRAME), 1)
        self.assertEqual(len(clock.sleeps), 1)
        self.assertEqual(len(captured.output), 1)
        self.assertIn("ValueError", "\n".join(captured.output))

    def test_run_loop_snapshot_exception_zeros_after_normal_output_then_recovers(self):
        clock = _RunClock()
        be = _FakeBackend()
        with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
             mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep):
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
            _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
            sm._push_tick_inner = lambda: None
            snapshots = 0

            def publish(_now):
                nonlocal snapshots
                snapshots += 1
                if snapshots == 1:
                    raise RuntimeError("snapshot crash")
                clock.spend_tick()
                sm._stop.set()
                return False

            sm._maybe_publish_snapshot = publish
            with self.assertLogs("state_manager", level="ERROR") as captured:
                sm._run()

        self.assertEqual(snapshots, 2)
        self.assertNotEqual(be.frames[0], ZERO_FRAME)
        self.assertEqual(be.frames[1], ZERO_FRAME)
        self.assertNotEqual(be.frames[2], ZERO_FRAME)
        self.assertEqual(be.frames.count(ZERO_FRAME), 1)
        self.assertEqual(len(clock.sleeps), 1)
        self.assertEqual(len(captured.output), 1)
        self.assertIn("RuntimeError", "\n".join(captured.output))

    def test_run_loop_persistent_drain_exception_sleeps_and_bounds_logs_under_profiler(self):
        clock = _RunClock()
        be = _FakeBackend()
        failures = 50
        with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
             mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep):
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
            sm._profiler = SimpleNamespace(record=mock.Mock(), maybe_log=mock.Mock())
            seen = 0

            def drain():
                nonlocal seen
                seen += 1
                if seen == failures:
                    sm._stop.set()
                raise RuntimeError("persistent drain crash")

            sm._drain_events = drain
            sm._push_tick = mock.Mock()
            with self.assertLogs("state_manager", level="ERROR") as captured:
                sm._run()

        self.assertEqual(seen, failures)
        sm._push_tick.assert_not_called()
        self.assertEqual(be.frames, [ZERO_FRAME] * failures)
        self.assertEqual(len(clock.sleeps), failures)
        self.assertEqual(len(captured.output), 1)
        sm._profiler.record.assert_not_called()

    def test_run_loop_profiler_record_exception_sleeps_and_recovers(self):
        clock = _RunClock()
        be = _FakeBackend()
        with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
             mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep):
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
            _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
            sm._push_tick_inner = lambda: None
            records = 0
            publishes = 0

            def record(**_kwargs):
                nonlocal records
                records += 1
                if records == 1:
                    raise RuntimeError("profiler record crash")

            def publish(_now):
                nonlocal publishes
                publishes += 1
                if publishes == 2:
                    clock.spend_tick()
                    sm._stop.set()
                return False

            sm._profiler = SimpleNamespace(record=record, maybe_log=mock.Mock())
            sm._maybe_publish_snapshot = publish
            with self.assertLogs("state_manager", level="ERROR") as captured:
                sm._run()

        self.assertEqual(records, 2)
        self.assertEqual(publishes, 2)
        self.assertNotEqual(be.frames[0], ZERO_FRAME)
        self.assertEqual(be.frames[1], ZERO_FRAME)
        self.assertNotEqual(be.frames[2], ZERO_FRAME)
        self.assertEqual(be.frames.count(ZERO_FRAME), 1)
        self.assertEqual(len(clock.sleeps), 1)
        self.assertEqual(len(captured.output), 1)
        self.assertIn("RuntimeError", "\n".join(captured.output))

    def test_control_exceptions_escape_before_push_tick_without_error_log(self):
        for exc_type in (KeyboardInterrupt, SystemExit):
            with self.subTest(exc_type=exc_type.__name__):
                clock = _RunClock()
                be = _FakeBackend()
                with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
                     mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep), \
                     mock.patch("rb_ss_bridge_v2.state_manager.log.error") as log_error:
                    sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
                    sm._drain_events = mock.Mock(side_effect=exc_type())
                    with self.assertRaises(exc_type):
                        sm._run()

                log_error.assert_not_called()
                self.assertEqual(clock.sleeps, [])
                self.assertEqual(be.frames, [])

    def test_control_exceptions_escape_from_push_tick_after_single_zero(self):
        for exc_type in (KeyboardInterrupt, SystemExit):
            with self.subTest(exc_type=exc_type.__name__):
                clock = _RunClock()
                be = _FakeBackend()
                with mock.patch("rb_ss_bridge_v2.state_manager.time.monotonic", clock.monotonic), \
                     mock.patch("rb_ss_bridge_v2.state_manager.time.sleep", clock.sleep), \
                     mock.patch("rb_ss_bridge_v2.state_manager.log.error") as log_error:
                    sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
                    _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
                    sm._push_tick_inner = mock.Mock(side_effect=exc_type())
                    with self.assertRaises(exc_type):
                        sm._run()

                log_error.assert_not_called()
                self.assertEqual(clock.sleeps, [])
                self.assertEqual(be.frames, [ZERO_FRAME])

    # D14
    def test_driver_does_no_blocking_io(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=_FakeInput())
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        import builtins
        import socket
        with mock.patch.object(builtins, "open", side_effect=AssertionError("no open")), \
             mock.patch.object(socket, "socket", side_effect=AssertionError("no socket")):
            sm._drive_pack_output()
        self.assertEqual(len(be.frames), 1)

    def test_driver_exception_resolves_zero_without_raising(self):
        be = _FakeBackend()
        player = LaserPackPlayer(_pack())
        player.render = mock.Mock(side_effect=RuntimeError("render boom"))
        sm = _make_sm(player=player, backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        sm._drive_pack_output()  # must not raise
        self.assertEqual(be.frames[-1], ZERO_FRAME)


class PackDriverInputHealthTests(unittest.TestCase):
    # H1
    def test_worker_not_alive_drops_held_static(self):
        be = _FakeBackend()
        # Models source closure, which can leave a held slot reported. Exception death
        # clears held state in _clear_held and is not the fail-open gap.
        inp = _FakeInput(held_layer_slot=8, worker_alive=False, error=None)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)

    # H2
    def test_worker_not_alive_drops_held_blackout(self):
        be = _FakeBackend()
        inp = _FakeInput(blackout_held=True, worker_alive=False, error=None)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)

    # H3
    def test_no_aliases_scripted_renders(self):
        with self.subTest("real empty group"):
            be = _FakeBackend()
            inp = SoundSwitchMidiInputGroup(bindings=[], aliases={})
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
            _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
            sm._drive_pack_output()
            self.assertEqual(be.frames[-1][0], 9)
            self.assertEqual(sm._pack_last_static_layers, ())

        with self.subTest("midi input none"):
            be = _FakeBackend()
            sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=None)
            _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
            sm._drive_pack_output()
            self.assertEqual(be.frames[-1][0], 9)

    # H4
    def test_new_mailbox_drop_does_not_latch_overlay_drop(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, mail_drop_count=0)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)
        inp._snap.mail_drop_count = 1
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    # H5
    def test_transient_error_string_does_not_release_blackout(self):
        be = _FakeBackend()
        inp = _FakeInput(blackout_held=True, error="input_error", worker_alive=True)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # H6
    def test_transient_error_string_does_not_clear_layers(self):
        be = _FakeBackend()
        inp = _FakeInput(
            error="input_error",
            held_layer_slot=8,
            worker_alive=True,
        )
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    # H7
    def test_worker_recovery_requires_clean_release_before_rehonor(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, worker_alive=False, error=None)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)
        self.assertTrue(sm._pack_input_degraded_latched)

        inp._snap.worker_alive = True
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)
        self.assertTrue(sm._pack_input_degraded_latched)

        inp._snap.held_layers = ()
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)
        self.assertFalse(sm._pack_input_degraded_latched)

        inp._snap.held_layers = _layer_tuple(8)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    # H8
    def test_reload_no_false_drop_no_latch(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, mail_drop_count=0)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        sm._pack_last_mail_drop_count = 5
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)
        self.assertFalse(sm._pack_input_degraded_latched)

    # H9
    def test_mailbox_drop_does_not_drop_live_layers(self):
        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, mail_drop_count=0)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)
        inp._snap.mail_drop_count = 1
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)
        self.assertFalse(sm._pack_input_degraded_latched)

        inp._snap.held_layers = ()
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)
        self.assertFalse(sm._pack_input_degraded_latched)

        inp._snap.held_layers = _layer_tuple(8)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    # H10
    def test_latch_survives_runtime_swap(self):
        old_be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=old_be)
        sm._pack_input_degraded_latched = True
        sm._pack_last_mail_drop_count = 5

        be = _FakeBackend()
        inp = _FakeInput(held_layer_slot=8, mail_drop_count=0)
        sm.set_pack_runtime(PackRuntime(
            enabled=True,
            reason="pack",
            player=LaserPackPlayer(_pack()),
            midi_input=inp,
            backend=be,
        ))
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)
        self.assertTrue(sm._pack_input_degraded_latched)

        inp._snap.held_layers = ()
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 9)
        self.assertFalse(sm._pack_input_degraded_latched)

        inp._snap.held_layers = _layer_tuple(8)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)

    def test_set_pack_runtime_resets_logged_error_latch(self):
        sm = _make_sm()
        sm._pack_logged_error = True                  # simulate prior runtime logged an error
        sm._pack_input_degraded_latched = True        # H10 latch must survive swaps
        sm.set_pack_runtime(PackRuntime(reason="disabled"))
        self.assertFalse(sm._pack_logged_error,
                         "post-reload first driver error would be silently swallowed")
        self.assertTrue(sm._pack_input_degraded_latched)

    # H11 — regression: static layers carried in _pack_last_static_layers across a
    # runtime swap must NOT suppress set_static_layers on the fresh player when the
    # new snapshot reports the same tuple while healthy.
    def test_runtime_swap_resyncs_carried_static_slot(self):
        old_be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=old_be,
                      midi_input=_FakeInput(held_layer_slot=8))
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(old_be.frames[-1][0], 200)          # old player honors static 8
        self.assertEqual(tuple(layer.slot for layer in sm._pack_last_static_layers), (8,))
        self.assertFalse(sm._pack_input_degraded_latched)    # healthy swap, not latched

        new_be = _FakeBackend()
        sm.set_pack_runtime(PackRuntime(
            enabled=True, reason="pack", player=LaserPackPlayer(_pack()),
            midi_input=_FakeInput(held_layer_slot=8), backend=new_be))
        self.assertEqual(sm._pack_last_static_layers, ())     # tracker reset on swap
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(new_be.frames[-1][0], 200)           # fresh player honors static 8


class PackOperationalStatusTests(unittest.TestCase):
    def test_initial_enable_swap_reload_disable_snapshots(self):
        disabled = _make_sm()
        self.assertEqual(disabled.get_pack_status()["operational_state"], "disabled")
        self.assertTrue(disabled.get_pack_status()["software_zero_frame"])

        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=_FakeBackend())
        initial = sm.get_pack_status()
        self.assertTrue(initial["enabled"])
        self.assertEqual(initial["backend"], "pack")
        self.assertEqual(initial["operational_state"], "software_zero_frame")
        self.assertEqual(initial["frame_count"], 0)

        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        sm._drive_pack_output()
        self.assertEqual(sm.get_pack_status()["frame_count"], 1)

        sm.set_pack_runtime(PackRuntime(reason="swapping"))
        self.assertEqual(sm.get_pack_status()["operational_state"], "disabled")
        self.assertEqual(sm.get_pack_status()["frame_count"], 0)

        for reason in ("pack", "pack"):
            sm.set_pack_runtime(PackRuntime(
                enabled=True,
                reason=reason,
                player=LaserPackPlayer(_pack()),
                backend=_FakeBackend(),
            ))
            status = sm.get_pack_status()
            self.assertEqual(status["operational_state"], "software_zero_frame")
            self.assertEqual(status["backend"], "pack")
            self.assertEqual(status["frame_count"], 0)

        sm.set_pack_runtime(PackRuntime(reason="disabled"))
        self.assertEqual(sm.get_pack_status()["operational_state"], "disabled")
        self.assertTrue(sm.get_pack_status()["software_zero_frame"])

    def test_operational_flags_preserve_simultaneous_truths(self):
        cases = (
            (
                _FakeInput(),
                dict(ssid=SSID, elapsed_ms=50, playing=True),
                "scripted_active",
                {"scripted_active": True, "software_zero_frame": False},
            ),
            (
                _FakeInput(worker_alive=False),
                dict(ssid=SSID, elapsed_ms=50, playing=True),
                "input_degraded",
                {
                    "input_degraded": True,
                    "scripted_active": True,
                    "software_zero_frame": False,
                },
            ),
            (
                _FakeInput(held_layer_slot=8),
                dict(ssid="", playing=False),
                "static_held",
                {"static_held": True, "software_zero_frame": False},
            ),
            (
                _FakeInput(blackout_held=True),
                dict(ssid="", playing=False),
                "blackout",
                {"blackout": True, "software_zero_frame": True},
            ),
        )
        for midi_input, state, expected_state, expected_flags in cases:
            with self.subTest(expected_state=expected_state):
                sm = _make_sm(
                    player=LaserPackPlayer(_pack()),
                    backend=_FakeBackend(),
                    midi_input=midi_input,
                )
                _set(sm, **state)
                sm._drive_pack_output()
                status = sm.get_pack_status()
                self.assertEqual(status["operational_state"], expected_state)
                for key, value in expected_flags.items():
                    self.assertIs(status[key], value)

    def test_autoloop_waiting_for_first_edge_is_zero_and_not_selected(self):
        player = LaserPackPlayer(_native_pack())
        player.select_autoloop = mock.Mock(side_effect=AssertionError("select_autoloop banned"))
        sm = _make_sm(player=player, backend=_FakeBackend())
        _set(sm, ssid="", playing=True, scripted_id=0, lighting_mode="autoloop")

        sm._drive_pack_output()

        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "software_zero_frame")
        self.assertEqual(status["native_autoloop"]["reason"], "waiting_for_edge")
        self.assertTrue(status["autoloop_phase_blocked"])
        self.assertTrue(status["software_zero_frame"])
        player.select_autoloop.assert_not_called()

    def test_get_status_is_provider_free_and_returns_a_copy(self):
        backend = _FakeBackend()
        backend.status = mock.Mock(side_effect=AssertionError("backend status banned"))
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=backend, midi_input=_FakeInput())
        sm._pack_runtime = object()

        first = sm.get_pack_status()
        first["enabled"] = False
        second = sm.get_pack_status()

        self.assertTrue(second["enabled"])
        backend.status.assert_not_called()

    def test_each_publication_uses_a_fresh_unmutated_dict(self):
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=_FakeBackend())
        initial = sm._pack_status_snapshot
        initial_value = dict(initial)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()
        first_tick = sm._pack_status_snapshot
        sm._drive_pack_output()
        second_tick = sm._pack_status_snapshot

        self.assertIsNot(initial, first_tick)
        self.assertIsNot(first_tick, second_tick)
        self.assertEqual(initial, initial_value)
        self.assertEqual(first_tick["frame_count"], 1)
        self.assertEqual(second_tick["frame_count"], 2)

    def test_submit_failure_sees_published_intent_then_bounded_zero(self):
        backend = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=backend)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)
        observed = []

        def fail_submit(_frame):
            observed.append(sm.get_pack_status())
            raise RuntimeError("/private/device/raw submit failure")

        backend.submit_frame = fail_submit
        with self.assertLogs("state_manager", level="ERROR") as captured:
            sm._drive_pack_output()

        self.assertEqual(observed[0]["operational_state"], "scripted_active")
        self.assertFalse(observed[0]["software_zero_frame"])
        self.assertEqual(observed[0]["frame_count"], 1)
        self.assertEqual(observed[1]["operational_state"], "software_zero_frame")
        final = sm.get_pack_status()
        self.assertEqual(final["frame_count"], 1)
        self.assertNotIn("private", repr(final))
        self.assertNotIn("device", repr(final))
        self.assertNotIn("private", "\n".join(captured.output))
        self.assertNotIn("device", "\n".join(captured.output))

    def test_render_exception_publishes_bounded_zero_and_attempts_zero(self):
        backend = _FakeBackend()
        player = LaserPackPlayer(_pack())
        player.render = mock.Mock(side_effect=RuntimeError("/private/raw render failure"))
        sm = _make_sm(player=player, backend=backend)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True)

        sm._drive_pack_output()

        self.assertEqual(backend.frames, [ZERO_FRAME])
        status = sm.get_pack_status()
        self.assertEqual(status["operational_state"], "software_zero_frame")
        self.assertTrue(status["software_zero_frame"])
        self.assertEqual(status["frame_count"], 0)
        self.assertNotIn("private", repr(status))


class PackDriverInnerTickTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.clock = mock.patch(
            "rb_ss_bridge_v2.state_manager.time.monotonic",
            side_effect=lambda: self.now,
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.backend = _FakeBackend()
        self.sm = _make_sm(player=LaserPackPlayer(_pack()), backend=self.backend)

    def _event(self, kind, deck=1, payload=None):
        self.sm._handle_event(BridgeEvent(
            kind=kind, deck=deck, payload=payload or {}, source="rw2-test",
        ))

    def _resolve_scripted(self, deck=1, title="track"):
        load_gen = self.sm._deck[deck].load_gen
        self.sm._on_filepath_resolved(deck, {
            "filepath": f"/music/{title}.wav",
            "bpm": 0.0,
            "content_id": title,
            "first_beat_ms": 0.0,
            "soundswitch_id": SSID,
            "total_ms": 19_200,
            "load_gen": load_gen,
        })
        self._event(Ev.SCRIPTED_ARM, deck, {"scripted_id": load_gen})

    def _load_scripted(self, deck=1, title="track"):
        self._event(Ev.TRACK_LOADED, deck, {"title": title})
        self._resolve_scripted(deck, title)

    def _tick(self, *, deck=1, elapsed_ms=50, snap_playing=False):
        self.sm._cache.update(PositionSnapshot(
            deck=deck,
            elapsed_ms=elapsed_ms,
            playing=snap_playing,
            updated_at=self.now,
        ))
        self.sm._push_tick()
        return self.backend.frames[-1]

    def _start_playing(self, deck=1, elapsed_ms=50):
        self._event(Ev.PLAY, deck)
        frame = self._tick(deck=deck, elapsed_ms=elapsed_ms, snap_playing=True)
        self.now += 0.4
        frame = self._tick(deck=deck, elapsed_ms=elapsed_ms, snap_playing=True)
        self.assertTrue(self.sm._os.was_playing)
        return frame

    # RW-3 R6
    def test_inner_autoloop_uuid_stays_zero(self):
        with mock.patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"}):
            self._event(Ev.TRACK_LOADED, payload={"title": "autoloop"})
            load_gen = self.sm._deck[1].load_gen
            self.sm._on_filepath_resolved(1, {
                "filepath": "/music/autoloop.wav",
                "bpm": 0.0,
                "content_id": "autoloop",
                "first_beat_ms": 0.0,
                "soundswitch_id": SSID,
                "total_ms": 19_200,
                "load_gen": load_gen,
            })
            frame = self._start_playing()
            self.assertEqual(self.sm._os.lighting_mode, "autoloop")
            self.assertEqual(frame, ZERO_FRAME)

    # RW-3 R8
    def test_inner_same_identity_clear_resolve_arm_while_paused_zeros(self):
        with mock.patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"}):
            self._load_scripted()
            self._event(Ev.SCRIPTED_ARM, payload={"scripted_id": 7})
            self.assertEqual(self._start_playing()[0], 9)
            self._event(Ev.PAUSE)
            self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False)[0], 9)

            load_gen = self.sm._deck[1].load_gen
            self._event(Ev.SCRIPTED_CLEAR)
            self.sm._on_filepath_resolved(1, {
                "filepath": "/music/track.wav",
                "bpm": 0.0,
                "content_id": "track",
                "first_beat_ms": 0.0,
                "soundswitch_id": SSID,
                "total_ms": 19_200,
                "load_gen": load_gen,
            })
            self._event(Ev.SCRIPTED_ARM, payload={"scripted_id": 7})

            self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False), ZERO_FRAME)
            self.assertIsNone(self.sm._pack_play_hold_key)

    def test_inner_pause_hold_matches_osl_idle(self):
        self._load_scripted()
        self.assertEqual(self._start_playing()[0], 9)
        last_play = self.now

        self.now += 0.005
        self._event(Ev.PAUSE)
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False)[0], 9)
        self.assertEqual(self.sm._os.lighting_mode, "scripted")

        boundary = last_play + 0.5
        self.now = boundary - 0.001
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False)[0], 9)
        self.now = boundary
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False), ZERO_FRAME)
        self.assertEqual(self.sm._os.lighting_mode, "scripted")

        self.now = boundary + 0.005000001
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False), ZERO_FRAME)
        self.assertEqual(self.sm._os.lighting_mode, "idle")
        self.assertLessEqual(self.now - boundary, 0.005001)

    def test_inner_replacement_while_paused_not_held(self):
        self._load_scripted(title="old")
        self._start_playing()
        self.now += 0.01
        self._event(Ev.PAUSE)
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False)[0], 9)

        self.now += 0.01
        self._event(Ev.TRACK_LOADED, payload={"title": "replacement"})
        load_gen = self.sm._deck[1].load_gen
        self.sm._on_filepath_resolved(1, {
            "filepath": "/music/replacement.wav",
            "bpm": 0.0,
            "content_id": "replacement",
            "first_beat_ms": 0.0,
            "soundswitch_id": SSID,
            "total_ms": 19_200,
            "load_gen": load_gen,
        })
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False), ZERO_FRAME)
        self.now += 0.005
        self.assertEqual(self._tick(elapsed_ms=50, snap_playing=False), ZERO_FRAME)
        self.assertIsNone(self.sm._pack_play_hold_key)

    def test_inner_pause_before_snapshot_settles(self):
        self._load_scripted()
        self._start_playing(elapsed_ms=60)
        snap_updated_at = self.now
        self._event(Ev.PAUSE)

        self.now += 0.03
        self.sm._cache.update(PositionSnapshot(
            deck=1, elapsed_ms=30, playing=True, updated_at=snap_updated_at,
        ))
        self.sm._push_tick()
        self.assertEqual(self.sm._deck[1].elapsed_ms, 60)
        self.assertEqual(self.backend.frames[-1][0], 9)

        self.now += 0.01
        self.assertEqual(self._tick(elapsed_ms=30, snap_playing=False)[0], 5)
        self.assertEqual(self.sm._deck[1].elapsed_ms, 30)

    def test_event_chain_load_play_pause_resume_master_replace_stop(self):
        self._event(Ev.TRACK_LOADED, 1, {"title": "deck1"})
        self.assertEqual(self._tick(deck=1, elapsed_ms=0, snap_playing=False), ZERO_FRAME)
        self._resolve_scripted(deck=1, title="deck1")
        self.assertEqual(self._tick(deck=1, elapsed_ms=0, snap_playing=False), ZERO_FRAME)
        self.assertEqual(self._start_playing(deck=1)[0], 9)

        self.now += 0.01
        self._event(Ev.PAUSE, 1)
        self.assertEqual(self._tick(deck=1, elapsed_ms=50, snap_playing=False)[0], 9)
        self.now += 0.01
        self._event(Ev.PLAY, 1)
        self.assertEqual(self._tick(deck=1, elapsed_ms=60, snap_playing=True)[0], 9)

        self.now += 0.01
        self._event(Ev.MASTER_CHANGED, 2)
        self.assertEqual(self._tick(deck=2, elapsed_ms=0, snap_playing=False), ZERO_FRAME)
        self._event(Ev.TRACK_LOADED, 2, {"title": "replacement"})
        self.assertEqual(self._tick(deck=2, elapsed_ms=0, snap_playing=False), ZERO_FRAME)
        self._resolve_scripted(deck=2, title="replacement")
        self.now += 0.01
        self.assertEqual(self._tick(deck=2, elapsed_ms=0, snap_playing=False), ZERO_FRAME)

        self.assertEqual(self._start_playing(deck=2)[0], 9)
        last_play = self.now
        self.now += 0.005
        self._event(Ev.PAUSE, 2)
        self.assertEqual(self._tick(deck=2, elapsed_ms=50, snap_playing=False)[0], 9)
        self.now = last_play + 0.5
        self.assertEqual(self._tick(deck=2, elapsed_ms=50, snap_playing=False), ZERO_FRAME)
        self.now += 0.005000001
        self.assertEqual(self._tick(deck=2, elapsed_ms=50, snap_playing=False), ZERO_FRAME)
        self.assertEqual(self.sm._os.lighting_mode, "idle")


if __name__ == "__main__":
    unittest.main()
