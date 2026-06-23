"""T7c — StateManager SoundSwitch pack driver tests.

No real MIDI/serial/Enttec/DMX/network. A real LaserPackPlayer drives a tiny
synthetic pack; a fake backend records submitted frames; deck/snap state is
synthetic. See docs/plans/active/soundswitch_t7c_pack_driver_spec.md (Part D).
"""
from __future__ import annotations

import queue
import unittest
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.state_manager import StateManager
from rb_ss_bridge_v2.rb_memory import PositionCache
from rb_ss_bridge_v2.soundswitch_laser_player import (
    ZERO_FRAME, LaserPackPlayer,
)
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute, LoadedDocument, LoadedPack, LoadedStaticLook, LoadedScalarValue,
    LoadedTimelineEvent,
)
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime
SSID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
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


class _FakeInput:
    # The driver only reads .blackout_held and .held_static_slot from the snapshot.
    def __init__(self, *, held_static_slot=None, blackout_held=False):
        self._snap = SimpleNamespace(held_static_slot=held_static_slot,
                                     blackout_held=blackout_held)
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self._snap


def _make_sm(*, player=None, backend=None, midi_input=None, enabled=None):
    if enabled is None:
        enabled = player is not None and backend is not None
    rt = PackRuntime(
        enabled=enabled, reason="pack" if enabled else "disabled",
        player=player, midi_input=midi_input, backend=backend)
    return StateManager(
        queue.Queue(), PositionCache(), mock.Mock(), soundswitch_pack_runtime=rt)


def _set(sm, *, ssid="", elapsed_ms=0, playing=False, load_gen=1, snap=FRESH, active=1):
    sm._os = SimpleNamespace(active_deck=active)
    sm._deck = {active: SimpleNamespace(
        meta=SimpleNamespace(soundswitch_id=ssid), elapsed_ms=elapsed_ms,
        playing=playing, load_gen=load_gen)}
    sm._cache = SimpleNamespace(get=lambda _dk: snap)


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
        inp = _FakeInput(held_static_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        self.assertEqual(be.frames[-1][0], 200)  # CH1 of static look slot 8

    # D4
    def test_no_track_no_static_is_zero(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=_FakeInput())
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # D5
    def test_stop_does_not_retain_old_scripted_frame(self):
        be = _FakeBackend()
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
        sm._drive_pack_output()
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1], ZERO_FRAME)

    # D6
    def test_blackout_held_with_static_is_zero(self):
        be = _FakeBackend()
        inp = _FakeInput(held_static_slot=8, blackout_held=True)
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
        inp = _FakeInput(held_static_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=STALE)
        sm._drive_pack_output()
        self.assertEqual(be.frames[-1][0], 200)  # static look slot 8 stands alone

    def test_track_change_with_held_static_shows_static(self):
        be = _FakeBackend()
        inp = _FakeInput(held_static_slot=8)
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
        inp = _FakeInput(held_static_slot=8)
        sm = _make_sm(player=LaserPackPlayer(_pack()), backend=be, midi_input=inp)
        sm.set_pack_runtime(PackRuntime())  # simulate disable/rollback (inactive)
        _set(sm, ssid="", playing=False, snap=FRESH)
        sm._drive_pack_output()
        self.assertEqual(be.frames, [])

    # D10
    def test_autoloop_never_called(self):
        be = _FakeBackend()
        player = LaserPackPlayer(_pack())
        player.select_autoloop = mock.Mock(side_effect=AssertionError("select_autoloop banned"))
        sm = _make_sm(player=player, backend=be)
        for playing, snap in ((True, FRESH), (False, FRESH), (True, STALE)):
            _set(sm, ssid=SSID, elapsed_ms=10, playing=playing, snap=snap)
            sm._drive_pack_output()
        player.select_autoloop.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
