from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor
from rb_ss_bridge_v2.laser_models import LaserMidiMessage
from rb_ss_bridge_v2.soundswitch_laser_player import ZERO_FRAME, LaserPackPlayer

from test_laser_executor import _config, _ctx, _decision, _personality
from test_state_manager_pack_driver import (
    FRESH,
    SSID,
    _FakeBackend,
    _FakeInput,
    _make_sm,
    _pack,
    _set,
)


class _Backend:
    def __init__(self, *, result: bool) -> None:
        self.result = result
        self.calls: list[tuple[LaserMidiMessage, str]] = []

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((msg, priority))
        return self.result

    def status(self) -> dict:
        return {"backend": "test"}


class _SmartMask:
    def __init__(self, active: bool) -> None:
        self.active = active

    def mask_owners_active(self) -> bool:
        return self.active


def _blackout_messages() -> tuple[LaserMidiMessage, LaserMidiMessage]:
    return (
        LaserMidiMessage(kind="note_on", behavior="note_on", channel=1, note=89),
        LaserMidiMessage(kind="note_off", behavior="note_off", channel=1, note=89),
    )


def _executor(*, backend_result: bool = True) -> tuple[LaserSceneExecutor, _Backend]:
    on, off = _blackout_messages()
    backend = _Backend(result=backend_result)
    return (
        LaserSceneExecutor(
            config=_config(dry_run=False, manual_blackout_on=on, manual_blackout_off=off),
            backend=backend,
            personality=_personality(),
        ),
        backend,
    )


def _pack_sm(*, midi_input: _FakeInput | None = None, executor=None):
    be = _FakeBackend()
    sm = _make_sm(
        player=LaserPackPlayer(_pack()),
        backend=be,
        midi_input=midi_input,
    )
    sm._laser_executor = executor
    _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)
    return sm, be


class LaserBlackoutRewireTests(unittest.TestCase):
    def test_pack_rejecting_backend_hold_still_latches_owner(self) -> None:
        ex, _backend = _executor(backend_result=False)

        ex.hold_blackout_mask("breakdown")
        self.assertTrue(ex.mask_owners_active())

        ex.release_blackout_mask("breakdown")
        self.assertFalse(ex.mask_owners_active())

    def test_rejected_pending_blackout_latches_until_resolved(self) -> None:
        ex, _backend = _executor(backend_result=False)

        ex.trigger_blackout_on(_ctx())
        self.assertTrue(ex.mask_owners_active())

        ex._resolve_pending_blackout(reason="test")
        self.assertFalse(ex.mask_owners_active())

    def test_pack_writer_ors_smart_mask_into_frame_blackout(self) -> None:
        sm, be = _pack_sm(midi_input=_FakeInput(blackout_held=False), executor=_SmartMask(True))

        sm._drive_pack_output(now=10.0)

        self.assertEqual(be.frames[-1], ZERO_FRAME)
        self.assertTrue(sm._pack_status_snapshot["blackout"])

    def test_manual_blackout_survives_smart_wipes_and_ss_present_suppression(self) -> None:
        ex, _backend = _executor()
        ex.hold_blackout_mask("breakdown")
        manual = _FakeInput(blackout_held=True)
        provider = lambda: True
        be = _FakeBackend()
        sm = _make_sm(
            player=LaserPackPlayer(_pack()),
            backend=be,
            midi_input=manual,
            os2l_connected_provider=provider,
        )
        sm._laser_executor = ex
        _set(sm, ssid=SSID, elapsed_ms=50, playing=True, snap=FRESH)

        ex.reset_runtime_state(reason="track_load")
        sm._drive_pack_output(now=10.0)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

        ex.clear_pending_blackout(reason="smart_drop_resolve")
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

        sm._os2l_connected_provider = lambda: False
        sm._drive_pack_output(now=10.2)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

        manual._snap.blackout_held = False
        sm._drive_pack_output(now=10.3)
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)

    def test_manual_and_smart_overlap_clear_only_after_both_release(self) -> None:
        ex, _backend = _executor()
        ex.hold_blackout_mask("breakdown")
        manual = _FakeInput(blackout_held=True)
        sm, be = _pack_sm(midi_input=manual, executor=ex)

        sm._drive_pack_output(now=10.0)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

        ex.release_blackout_mask("breakdown")
        sm._drive_pack_output(now=10.1)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

        ex.hold_blackout_mask("breakdown")
        manual._snap.blackout_held = False
        sm._drive_pack_output(now=10.2)
        self.assertEqual(be.frames[-1], ZERO_FRAME)

        ex.release_blackout_mask("breakdown")
        sm._drive_pack_output(now=10.3)
        self.assertNotEqual(be.frames[-1], ZERO_FRAME)

    def test_accepting_backend_midi_sequence_stays_on_off(self) -> None:
        ex, backend = _executor()

        ex.hold_blackout_mask("breakdown")
        ex.hold_blackout_mask("master_switch")
        ex.release_blackout_mask("breakdown")
        ex.release_blackout_mask("master_switch")

        self.assertEqual([call[0].behavior for call in backend.calls], ["note_on", "note_off"])

    def test_accepting_backend_pending_sequence_stays_on_scene_off(self) -> None:
        ex, backend = _executor()

        ex.trigger_blackout_on(_ctx(abs_beat=319.0))
        ex.on_decision(
            _decision("drop_a", "drop_crossing", "drop"),
            _ctx(abs_beat=320.0),
        )

        self.assertEqual([call[0].note for call in backend.calls], [89, 41, 89])


if __name__ == "__main__":
    unittest.main()
