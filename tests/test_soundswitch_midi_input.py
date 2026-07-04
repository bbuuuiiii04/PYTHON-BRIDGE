"""Tests for soundswitch_midi_input — no MIDI/serial/Art-Net hardware opened."""
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_midi_input import (
    LayerEntry,
    MidiInputSnapshot,
    PackMidiBinding,
    SoundSwitchMidiInputAdapter,
    SoundSwitchMidiInputGroup,
)
from rb_ss_bridge_v2.models import Ev
from rb_ss_bridge_v2.soundswitch_pack import SoundSwitchPackCompileError
from rb_ss_bridge_v2.soundswitch_pack_models import (
    DecodedSoundSwitchProject,
    MidiBinding,
    MidiCollection,
    MidiDevice,
    LearnedMidiMap,
    NoTargetPolicyInput,
    ProjectIdentity,
    ResolvedControlBinding,
    SourceDiagnostic,
    SourceFile,
)
from rb_ss_bridge_v2.soundswitch_project_decoder import (
    CANONICAL_PROJECT_UUID,
    CANONICAL_SOUNDSWITCH_VERSION,
    CANONICAL_VENUE_GUID,
)
from rb_ss_bridge_v2.soundswitch_pack import compile_pack_artifacts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DDJ = "DDJ-800"
IAC = "IAC Driver Bus 1"

_SLOT8 = PackMidiBinding(
    device_name=DDJ, message_type="note",
    channel_zero_based=9, data_byte=122,
    target_kind="static_look", target_slot=8,
)
_SLOT17 = PackMidiBinding(
    device_name=DDJ, message_type="note",
    channel_zero_based=9, data_byte=123,
    target_kind="static_look", target_slot=17,
)
_TOGGLE8 = PackMidiBinding(
    device_name=DDJ, message_type="note",
    channel_zero_based=9, data_byte=122,
    target_kind="static_look", target_slot=8,
    interaction="toggle",
)
_TOGGLE17 = PackMidiBinding(
    device_name=DDJ, message_type="note",
    channel_zero_based=9, data_byte=123,
    target_kind="static_look", target_slot=17,
    interaction="toggle",
)
_BLACKOUT = PackMidiBinding(
    device_name=IAC, message_type="note",
    channel_zero_based=0, data_byte=0,
    target_kind="blackout_mask",
)
_BLACKOUT_TOGGLE = PackMidiBinding(
    device_name=IAC, message_type="note",
    channel_zero_based=0, data_byte=1,
    target_kind="blackout_mask",
    interaction="toggle",
)
_PACK_SEL = PackMidiBinding(
    device_name=IAC, message_type="note",
    channel_zero_based=0, data_byte=32,
    target_kind="pack_selection",
)
_INACTIVE = PackMidiBinding(
    device_name=IAC, message_type="note",
    channel_zero_based=0, data_byte=41,
    target_kind="inactive_report_only",
)


def _adapter(*bindings: PackMidiBinding) -> SoundSwitchMidiInputAdapter:
    return SoundSwitchMidiInputAdapter(list(bindings))


def _note_on(adapter: SoundSwitchMidiInputAdapter,
             binding: PackMidiBinding, velocity: int = 64) -> None:
    """Inject a note-on via _feed_raw_message."""
    status = 0x90 | binding.channel_zero_based
    adapter._feed_raw_message(status, binding.data_byte, velocity)


def _note_off(adapter: SoundSwitchMidiInputAdapter,
              binding: PackMidiBinding) -> None:
    """Inject a note-off via _feed_raw_message."""
    status = 0x80 | binding.channel_zero_based
    adapter._feed_raw_message(status, binding.data_byte, 0)


def _note_on_vel0(adapter: SoundSwitchMidiInputAdapter,
                  binding: PackMidiBinding) -> None:
    """Inject a note-on velocity=0 (must normalize to note-off)."""
    status = 0x90 | binding.channel_zero_based
    adapter._feed_raw_message(status, binding.data_byte, 0)


def _slots(adapter: SoundSwitchMidiInputAdapter) -> tuple[int, ...]:
    return tuple(layer.slot for layer in adapter.snapshot().held_layers)


def _kinds(adapter: SoundSwitchMidiInputAdapter) -> tuple[str, ...]:
    return tuple(layer.kind for layer in adapter.snapshot().held_layers)


# ---------------------------------------------------------------------------
# Real MIDI source (production port factory)
# ---------------------------------------------------------------------------

class TestRealMidiSource(unittest.TestCase):
    """The production source must use the installed python-rtmidi (``MidiIn``)
    API. Guards against the ``RtMidiIn`` (rtmidi-python) API that the bridge
    environment does not ship, which silently disabled all controller input."""

    @staticmethod
    def _fake_rtmidi(ports, messages):
        class _FakeMidiIn:
            def __init__(self):
                self.opened = None
                self.closed = False
                self.ignored = None
                self._queue = list(messages)

            def ignore_types(self, *, sysex, timing, active_sense):
                self.ignored = (sysex, timing, active_sense)

            def get_ports(self):
                return list(ports)

            def open_port(self, index):
                self.opened = index

            def close_port(self):
                self.closed = True

            def get_message(self):
                return self._queue.pop(0) if self._queue else None

        inst = _FakeMidiIn()
        return types.SimpleNamespace(MidiIn=lambda: inst), inst

    def test_real_source_parses_python_rtmidi_messages(self):
        fake, inst = self._fake_rtmidi(
            ["IAC Driver Bus 1", "DDJ-800"],
            [([0x99, 8, 100], 0.0)],
        )
        with mock.patch.dict(sys.modules, {"rtmidi": fake}):
            gen = SoundSwitchMidiInputAdapter._make_real_source("DDJ-800")()
            self.assertEqual(next(gen), (0x99, 8, 100))
            self.assertIsNone(next(gen))  # empty queue -> poll tick, lets worker stop
            gen.close()
        self.assertEqual(inst.opened, 1)
        self.assertTrue(inst.closed)
        self.assertEqual(inst.ignored, (True, True, True))

    def test_real_source_prefers_exact_port_match(self):
        fake, inst = self._fake_rtmidi(
            ["Other DDJ-800 Port", "DDJ-800"],
            [([0x99, 8, 100], 0.0)],
        )
        with mock.patch.dict(sys.modules, {"rtmidi": fake}):
            gen = SoundSwitchMidiInputAdapter._make_real_source("DDJ-800")()
            self.assertEqual(next(gen), (0x99, 8, 100))
            gen.close()
        self.assertEqual(inst.opened, 1)

    def test_real_source_accepts_backend_numbered_exact_port_name(self):
        fake, inst = self._fake_rtmidi(
            ["DDJ-800 1"],
            [([0x99, 8, 100], 0.0)],
        )
        with mock.patch.dict(sys.modules, {"rtmidi": fake}):
            gen = SoundSwitchMidiInputAdapter._make_real_source("DDJ-800")()
            self.assertEqual(next(gen), (0x99, 8, 100))
            gen.close()
        self.assertEqual(inst.opened, 0)

    def test_real_source_rejects_substring_only_match(self):
        fake, _ = self._fake_rtmidi(["DDJ-800 Port A", "DDJ-800 Port B"], [])
        with mock.patch.dict(sys.modules, {"rtmidi": fake}):
            with self.assertRaises(Exception):
                next(SoundSwitchMidiInputAdapter._make_real_source("DDJ-800")())

    def test_real_source_skips_short_non_note_messages(self):
        fake, _ = self._fake_rtmidi(
            ["DDJ-800"],
            [([0xF8], 0.0), ([0x99, 8, 100], 0.0)],
        )
        with mock.patch.dict(sys.modules, {"rtmidi": fake}):
            gen = SoundSwitchMidiInputAdapter._make_real_source("DDJ-800")()
            self.assertIsNone(next(gen))
            self.assertEqual(next(gen), (0x99, 8, 100))
            gen.close()

    def test_real_source_raises_when_port_absent(self):
        fake, _ = self._fake_rtmidi(["IAC Driver Bus 1"], [])
        with mock.patch.dict(sys.modules, {"rtmidi": fake}):
            with self.assertRaises(Exception):
                next(SoundSwitchMidiInputAdapter._make_real_source("DDJ-800")())

    def test_non_string_port_entry_counts_absent(self):
        self.assertFalse(SoundSwitchMidiInputAdapter._port_present([None], "DDJ-800"))

    def test_present_then_flapping_port_is_present_when_exact_or_numbered_name_exists(self):
        self.assertTrue(SoundSwitchMidiInputAdapter._port_present(
            ["DDJ-800 1", "Other"],
            "DDJ-800",
        ))
        self.assertFalse(SoundSwitchMidiInputAdapter._port_present(
            ["Other DDJ-800 Port"],
            "DDJ-800",
        ))


# ---------------------------------------------------------------------------
# Snapshot API
# ---------------------------------------------------------------------------

class TestSnapshotInitial(unittest.TestCase):
    def test_initial_state(self):
        a = _adapter(_SLOT8)
        s = a.snapshot()
        self.assertEqual(s.held_layers, ())
        self.assertFalse(s.blackout_held)
        self.assertFalse(s.worker_alive)
        self.assertEqual(s.mail_drop_count, 0)


class TestSnapshotImmutable(unittest.TestCase):
    def test_snapshot_is_frozen(self):
        a = _adapter(_SLOT8)
        s = a.snapshot()
        self.assertIsInstance(s, MidiInputSnapshot)
        with self.assertRaises(Exception):
            s.held_layers = ()  # type: ignore[misc]


class TestStartupReadiness(unittest.TestCase):
    def test_async_source_open_failure_is_reported_by_start(self):
        def failed_source():
            raise OSError("synthetic MIDI open failure")
            yield None

        a = _adapter(_SLOT8)
        with self.assertRaisesRegex(RuntimeError, "failed to open"):
            a.start("fake", _message_source=failed_source, readiness_timeout_s=0.5)
        self.assertFalse(a.snapshot().worker_alive)

    def test_start_returns_only_after_source_is_alive(self):
        def live_source():
            yield None
            while True:
                yield None

        a = _adapter(_SLOT8)
        a.start("fake", _message_source=live_source, readiness_timeout_s=0.5)
        self.assertTrue(a.snapshot().worker_alive)
        a.stop()


# ---------------------------------------------------------------------------
# Note-on velocity-0 normalization
# ---------------------------------------------------------------------------

class TestNoteOnVelocityZero(unittest.TestCase):
    def test_vel0_treated_as_note_off(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)                 # select
        self.assertEqual(_slots(a), (8,))
        _note_on_vel0(a, _SLOT8)            # must behave as note-off
        self.assertEqual(_slots(a), ())

    def test_vel0_without_prior_select_is_noop(self):
        a = _adapter(_SLOT8)
        _note_on_vel0(a, _SLOT8)
        self.assertEqual(_slots(a), ())


# ---------------------------------------------------------------------------
# Static Override select / release / idempotency
# ---------------------------------------------------------------------------

class TestStaticOverride(unittest.TestCase):
    def test_note_on_selects_slot(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        self.assertEqual(_slots(a), (8,))

    def test_note_off_releases_current(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        _note_off(a, _SLOT8)
        self.assertEqual(_slots(a), ())

    def test_repeated_press_note_on_stacks(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT8)
        self.assertEqual(_slots(a), (8, 8, 8))
        self.assertEqual(_kinds(a), ("press", "press", "press"))

    def test_note_off_noop_when_not_held(self):
        a = _adapter(_SLOT8)
        _note_off(a, _SLOT8)
        self.assertEqual(_slots(a), ())

    def test_slot17_layers_over_slot8(self):
        a = _adapter(_SLOT8, _SLOT17)
        _note_on(a, _SLOT8)
        self.assertEqual(_slots(a), (8,))
        _note_on(a, _SLOT17)
        self.assertEqual(_slots(a), (8, 17))

    def test_release_old_slot_does_not_clear_new(self):
        """Adversarial target #1: slot 8 → slot 17 → release 8 must leave slot 17."""
        a = _adapter(_SLOT8, _SLOT17)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT17)
        _note_off(a, _SLOT8)              # release the old (non-current) slot
        self.assertEqual(_slots(a), (17,))

    def test_release_slot17_after_layering_slot8_reveals_slot8(self):
        """Correct note-off for the top slot reveals the layer underneath."""
        a = _adapter(_SLOT8, _SLOT17)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT17)
        _note_off(a, _SLOT17)
        self.assertEqual(_slots(a), (8,))

    def test_toggle_note_on_latches_and_same_note_unlatches(self):
        a = _adapter(_TOGGLE8)
        _note_on(a, _TOGGLE8)
        self.assertEqual(_slots(a), (8,))
        _note_on(a, _TOGGLE8)
        self.assertEqual(_slots(a), ())

    def test_toggle_note_off_and_velocity_zero_do_not_unlatch(self):
        a = _adapter(_TOGGLE8)
        _note_on(a, _TOGGLE8)
        _note_off(a, _TOGGLE8)
        self.assertEqual(_slots(a), (8,))
        _note_on_vel0(a, _TOGGLE8)
        self.assertEqual(_slots(a), (8,))

    def test_toggle_is_exempt_from_stale_timeout(self):
        a = SoundSwitchMidiInputAdapter([_TOGGLE8], stale_timeout_ms=1)
        _note_on(a, _TOGGLE8)
        with mock.patch("rb_ss_bridge_v2.soundswitch_midi_input.time.monotonic",
                        return_value=time.monotonic() + 10):
            self.assertEqual(_slots(a), (8,))

    def test_different_toggle_slot_layers_on_top(self):
        a = _adapter(_TOGGLE8, _TOGGLE17)
        _note_on(a, _TOGGLE8)
        _note_on(a, _TOGGLE17)
        self.assertEqual(_slots(a), (8, 17))

    def test_press_over_toggle_reverts_to_toggle_on_release(self):
        a = _adapter(_TOGGLE8, _SLOT17)
        _note_on(a, _TOGGLE8)
        _note_on(a, _SLOT17)
        self.assertEqual(_slots(a), (8, 17))
        _note_off(a, _SLOT17)
        self.assertEqual(_slots(a), (8,))


# ---------------------------------------------------------------------------
# Blackout mask
# ---------------------------------------------------------------------------

class TestBlackoutMask(unittest.TestCase):
    def test_note_on_holds_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        self.assertTrue(a.snapshot().blackout_held)
        self.assertEqual(a.snapshot().blackout_bindings, ("0:0",))

    def test_note_off_releases_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        _note_off(a, _BLACKOUT)
        self.assertFalse(a.snapshot().blackout_held)
        self.assertEqual(a.snapshot().blackout_bindings, ())

    def test_vel0_releases_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        _note_on_vel0(a, _BLACKOUT)
        self.assertFalse(a.snapshot().blackout_held)

    def test_toggle_blackout_flips_on_note_on_and_ignores_note_off(self):
        a = _adapter(_BLACKOUT_TOGGLE)
        _note_on(a, _BLACKOUT_TOGGLE)
        self.assertTrue(a.snapshot().blackout_held)
        _note_off(a, _BLACKOUT_TOGGLE)
        self.assertTrue(a.snapshot().blackout_held)
        _note_on(a, _BLACKOUT_TOGGLE)
        self.assertFalse(a.snapshot().blackout_held)

    def test_toggle_blackout_coexists_with_press_hold(self):
        a = _adapter(_BLACKOUT, _BLACKOUT_TOGGLE)
        _note_on(a, _BLACKOUT_TOGGLE)
        _note_on(a, _BLACKOUT)
        _note_off(a, _BLACKOUT)
        self.assertTrue(a.snapshot().blackout_held)
        _note_on(a, _BLACKOUT_TOGGLE)
        self.assertFalse(a.snapshot().blackout_held)


class TestPadEvents(unittest.TestCase):
    def test_new_pad_kinds_emit_bridge_events_and_note_off_noops(self):
        seen = []
        palette = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=51,
            target_kind="palette_pad", target_name="blue_cyan",
        )
        lock = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=57,
            target_kind="palette_lock_pad",
        )
        mute = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=58,
            target_kind="led_mute_pad",
        )
        rainbow = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=61,
            target_kind="rainbow_pad",
        )
        laser_solo = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=60,
            target_kind="laser_solo_pad",
        )
        a = SoundSwitchMidiInputAdapter(
            [palette, lock, mute, rainbow, laser_solo],
            event_sink=seen.append,
        )

        for binding in (palette, lock, mute, rainbow, laser_solo):
            _note_on(a, binding)
            _note_off(a, binding)

        self.assertEqual(
            [event.kind for event in seen],
            [
                Ev.LED_PALETTE_PAD, Ev.LED_PALETTE_LOCK_PAD, Ev.LED_MUTE_PAD,
                Ev.LED_RAINBOW_PAD, Ev.LASER_SOLO_PAD,
            ],
        )
        self.assertEqual(seen[0].payload["name"], "blue_cyan")


# ---------------------------------------------------------------------------
# Non-render controls do not mutate player state
# ---------------------------------------------------------------------------

class TestNonRenderControls(unittest.TestCase):
    def test_pack_selection_does_not_set_static_slot(self):
        a = _adapter(_PACK_SEL)
        _note_on(a, _PACK_SEL)
        s = a.snapshot()
        self.assertEqual(s.held_layers, ())
        self.assertFalse(s.blackout_held)

    def test_inactive_report_only_is_noop(self):
        a = _adapter(_INACTIVE)
        _note_on(a, _INACTIVE)
        s = a.snapshot()
        self.assertEqual(s.held_layers, ())
        self.assertFalse(s.blackout_held)


# ---------------------------------------------------------------------------
# Panic / reload / stop clears held state
# ---------------------------------------------------------------------------

class TestClearOnEvent(unittest.TestCase):
    def test_blackout_hold_does_not_self_expire_without_note_off(self):
        a = SoundSwitchMidiInputAdapter([_SLOT8, _BLACKOUT], stale_timeout_ms=1)
        _note_on(a, _SLOT8)
        _note_on(a, _BLACKOUT)
        with mock.patch("rb_ss_bridge_v2.soundswitch_midi_input.time.monotonic",
                        return_value=time.monotonic() + 10):
            snapshot = a.snapshot()
        self.assertEqual(tuple(layer.slot for layer in snapshot.held_layers), (8,))
        self.assertTrue(snapshot.blackout_held)
        self.assertIsNone(snapshot.error)

    def test_input_port_gone_clears_blackout_and_static(self):
        a = SoundSwitchMidiInputAdapter([_SLOT8, _BLACKOUT], stale_timeout_ms=1)
        _note_on(a, _SLOT8)
        _note_on(a, _BLACKOUT)
        a._mark_port_gone()
        snapshot = a.snapshot()
        self.assertEqual(snapshot.held_layers, ())
        self.assertFalse(snapshot.blackout_held)
        self.assertEqual(snapshot.error, "input_port_gone")

    def test_fresh_matched_input_recovers_port_gone_error_only_when_worker_healthy(self):
        a = SoundSwitchMidiInputAdapter([_SLOT8], stale_timeout_ms=100)
        with a._lock:
            a._worker_alive = True
            a._error = "input_port_gone"
            a._refresh_snapshot_locked()
        _note_on(a, _SLOT8)
        fresh = a.snapshot()
        self.assertIsNone(fresh.error)
        self.assertEqual(tuple(layer.slot for layer in fresh.held_layers), (8,))

    def test_panic_clears_static_slot(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        a.panic()
        s = a.snapshot()
        self.assertEqual(s.held_layers, ())
        self.assertFalse(s.worker_alive)

    def test_panic_clears_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        a.panic()
        self.assertFalse(a.snapshot().blackout_held)

    def test_on_pack_reload_clears_state(self):
        a = _adapter(_SLOT8, _BLACKOUT)
        _note_on(a, _SLOT8)
        _note_on(a, _BLACKOUT)
        a.on_pack_reload()
        s = a.snapshot()
        self.assertEqual(s.held_layers, ())
        self.assertFalse(s.blackout_held)

    def test_stop_clears_state(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        a.stop()
        self.assertEqual(_slots(a), ())

    def test_worker_death_clears_state(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        a._clear_held("worker_death")       # simulate worker dying
        self.assertEqual(_slots(a), ())
        self.assertFalse(a.snapshot().worker_alive)

    def test_port_gone_clears_stack_and_reopens_without_restart(self):
        ports = ["fake-port"]

        def live_source():
            while True:
                time.sleep(0.01)
                yield None

        def checker():
            return list(ports)

        def wait_for(predicate):
            deadline = time.time() + 1.0
            while time.time() < deadline:
                if predicate():
                    return
                time.sleep(0.01)
            self.fail("condition not reached")

        a = _adapter(_SLOT8)
        a.start(
            "fake-port",
            _message_source=live_source,
            _port_checker=checker,
            readiness_timeout_s=0.5,
        )
        try:
            _note_on(a, _SLOT8)
            self.assertEqual(_slots(a), (8,))

            ports[:] = [None]
            wait_for(lambda: a.snapshot().error == "input_port_gone")
            self.assertEqual(_slots(a), ())
            self.assertFalse(a.snapshot().worker_alive)

            ports[:] = ["fake-port"]
            wait_for(lambda: a.snapshot().worker_alive and a.snapshot().error is None)
            _note_on(a, _SLOT8)
            self.assertEqual(_slots(a), (8,))
        finally:
            a.stop()

    def test_port_never_found_backs_off_to_slow_retry(self):
        """A device that never appears must not hammer the MIDI client open/close
        cycle. Proved live (2026-06-30) that fast retries on a never-found device
        (e.g. DDJ-800 absent) corrupt port enumeration on a SEPARATE, already-
        connected adapter (Stream Deck) sharing the process."""
        from rb_ss_bridge_v2 import soundswitch_midi_input as ssmi
        attempts = []

        def never_found_source():
            attempts.append(time.monotonic())
            raise ssmi._InputPortGone("fake-port")
            yield None  # pragma: no cover - unreachable, makes this a generator

        a = _adapter(_SLOT8)
        with mock.patch.object(ssmi, "_PORT_RETRY_INTERVAL_S", 0.05), \
             mock.patch.object(ssmi, "_PORT_NEVER_SEEN_RETRY_INTERVAL_S", 0.4):
            a.start("fake-port", _message_source=never_found_source, readiness_timeout_s=0.5)
            time.sleep(0.25)  # several multiples of the fast interval, short of the slow one
            a.stop()
        self.assertEqual(len(attempts), 1)

    def test_port_lost_after_connecting_still_retries_fast(self):
        """A device that WAS connected and then drops must keep retrying fast —
        only a never-found device gets the slow backoff."""
        from rb_ss_bridge_v2 import soundswitch_midi_input as ssmi
        attempts = []

        def flaky_source():
            attempts.append(time.monotonic())
            if len(attempts) == 1:
                yield None
                raise ssmi._InputPortGone("fake-port")
            while True:
                yield None

        a = _adapter(_SLOT8)
        with mock.patch.object(ssmi, "_PORT_RETRY_INTERVAL_S", 0.05), \
             mock.patch.object(ssmi, "_PORT_NEVER_SEEN_RETRY_INTERVAL_S", 5.0):
            a.start("fake-port", _message_source=flaky_source, readiness_timeout_s=0.5)
            deadline = time.time() + 1.0
            while time.time() < deadline and len(attempts) < 2:
                time.sleep(0.01)
            a.stop()
        self.assertGreaterEqual(len(attempts), 2)


# ---------------------------------------------------------------------------
# Disabled bindings / unknown messages
# ---------------------------------------------------------------------------

class TestDeviceNameDispatch(unittest.TestCase):
    """Device-name filtering: spec requires exact device identity match."""

    def test_connected_device_filters_other_devices(self):
        """Messages from a device other than connected_device must be ignored."""
        # Binding is for DDJ-800 but we tell adapter we're connected to IAC.
        a = SoundSwitchMidiInputAdapter([_SLOT8])
        a._connected_device = IAC  # simulate start(device_name=IAC)
        _note_on(a, _SLOT8)  # _SLOT8 is DDJ-800 → should be ignored
        self.assertEqual(_slots(a), ())

    def test_connected_device_accepts_matching_device(self):
        """Messages from the connected device are processed normally."""
        a = SoundSwitchMidiInputAdapter([_SLOT8])
        a._connected_device = DDJ  # _SLOT8 is DDJ-800
        _note_on(a, _SLOT8)
        self.assertEqual(_slots(a), (8,))

    def test_no_connected_device_accepts_all(self):
        """None connected device accepts all devices (test-injection mode)."""
        a = SoundSwitchMidiInputAdapter([_SLOT8])
        # _connected_device stays None (default)
        _note_on(a, _SLOT8)
        self.assertEqual(_slots(a), (8,))


class TestDisabledAndUnknown(unittest.TestCase):
    def test_unregistered_note_is_silently_ignored(self):
        a = _adapter(_SLOT8)
        # Note 99 on ch9 is not registered
        a._feed_raw_message(0x99, 99, 64)
        self.assertEqual(_slots(a), ())

    def test_cc_message_on_non_render_does_not_crash(self):
        cc_binding = PackMidiBinding(
            device_name=IAC, message_type="control_change",
            channel_zero_based=0, data_byte=7,
            target_kind="inactive_report_only",
        )
        a = _adapter(cc_binding)
        # CC on ch0 data1=7
        a._feed_raw_message(0xB0, 7, 64)
        s = a.snapshot()
        self.assertEqual(s.held_layers, ())
        self.assertFalse(s.blackout_held)


# ---------------------------------------------------------------------------
# Input group auto-detection / degradation
# ---------------------------------------------------------------------------

class TestInputGroupAutoDetection(unittest.TestCase):
    class Adapter:
        def __init__(self, bindings, *, stale_timeout_ms, fail=False, events=None):
            self.bindings = tuple(bindings)
            self.fail = fail
            self.events = events if events is not None else []
            self._snap = MidiInputSnapshot((), False, True, None, 0)

        def start(self, port, *, device_name):
            self.events.append(("start", port, device_name, tuple(b.device_name for b in self.bindings)))
            if self.fail:
                raise OSError("synthetic missing port")

        def stop(self):
            self.events.append(("stop",))

        def mark_unavailable(self):
            self._snap = MidiInputSnapshot((), False, False, "input_unavailable", 0)

        def panic(self):
            pass

        def on_pack_reload(self):
            pass

        def snapshot(self):
            return self._snap

    def test_empty_aliases_auto_bind_static_device_only(self):
        events = []

        def factory(bindings, *, stale_timeout_ms):
            return self.Adapter(bindings, stale_timeout_ms=stale_timeout_ms, events=events)

        group = SoundSwitchMidiInputGroup(
            (_SLOT8, _BLACKOUT),
            {},
            adapter_factory=factory,
        )
        group.start()

        self.assertEqual(group.worker_count, 1)
        self.assertEqual(events, [("start", DDJ, DDJ, (DDJ,))])

    def test_explicit_alias_overrides_auto_detected_device_name(self):
        events = []

        def factory(bindings, *, stale_timeout_ms):
            return self.Adapter(bindings, stale_timeout_ms=stale_timeout_ms, events=events)

        group = SoundSwitchMidiInputGroup(
            (_SLOT8,),
            {DDJ: "Local Controller Port"},
            adapter_factory=factory,
        )
        group.start()

        self.assertEqual(events, [("start", "Local Controller Port", DDJ, (DDJ,))])

    def test_extra_bindings_create_streamdeck_adapter(self):
        events = []
        palette = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=51,
            target_kind="palette_pad", target_name="blue_cyan",
        )

        def factory(bindings, *, stale_timeout_ms):
            return self.Adapter(bindings, stale_timeout_ms=stale_timeout_ms, events=events)

        group = SoundSwitchMidiInputGroup(
            (_SLOT8,),
            {},
            extra_bindings=(palette,),
            adapter_factory=factory,
        )
        group.start()

        self.assertEqual(group.worker_count, 2)
        self.assertIn(("start", "Stream Deck", "Stream Deck", ("Stream Deck",)), events)

    def test_laser_solo_pad_only_binding_still_opens_its_own_adapter(self):
        events = []
        laser_solo = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=60,
            target_kind="laser_solo_pad",
        )

        def factory(bindings, *, stale_timeout_ms):
            return self.Adapter(bindings, stale_timeout_ms=stale_timeout_ms, events=events)

        group = SoundSwitchMidiInputGroup(
            (_SLOT8,),
            {},
            extra_bindings=(laser_solo,),
            adapter_factory=factory,
        )
        group.start()

        self.assertEqual(group.worker_count, 2)
        self.assertIn(("start", "Stream Deck", "Stream Deck", ("Stream Deck",)), events)

    def test_missing_controller_degrades_without_raising(self):
        def factory(bindings, *, stale_timeout_ms):
            return self.Adapter(bindings, stale_timeout_ms=stale_timeout_ms, fail=True)

        group = SoundSwitchMidiInputGroup(
            (_SLOT8,),
            {},
            adapter_factory=factory,
        )
        group.start()

        snapshot = group.snapshot()
        # No overlay is held, so the overlay-trust snapshot is vacuously healthy (there
        # is nothing to distrust)...
        self.assertTrue(snapshot.worker_alive)
        self.assertIsNone(snapshot.error)
        # ...but raw controller health still flags the missing controller for diagnostics.
        self.assertFalse(group.status()["worker_alive"])
        self.assertTrue(group.status()["has_error"])

    def test_dead_controller_does_not_drop_a_healthy_controllers_held_look(self):
        # Bigger-fix regression: two static-look controllers on distinct ports; one is
        # holding a look, the other's port is gone. The dead controller must NOT poison
        # the group's overlay-trust verdict, so the live look keeps rendering. Mirrors
        # the live case: operator holds a Stream Deck static look while the DDJ-800 is
        # absent (2026-07-01 all_surface capture: static_held_rows=0).
        sd = PackMidiBinding(
            device_name="Stream Deck", message_type="note",
            channel_zero_based=2, data_byte=36,
            target_kind="static_look", target_slot=8, interaction="toggle")
        ddj = PackMidiBinding(
            device_name="DDJ-800", message_type="note",
            channel_zero_based=9, data_byte=123,
            target_kind="static_look", target_slot=17)
        made: dict[str, SoundSwitchMidiInputAdapter] = {}

        def factory(bindings, *, stale_timeout_ms):
            adapter = SoundSwitchMidiInputAdapter(bindings, stale_timeout_ms=stale_timeout_ms)
            made[bindings[0].device_name] = adapter
            return adapter

        group = SoundSwitchMidiInputGroup((sd, ddj), {}, adapter_factory=factory)
        made["Stream Deck"]._worker_alive = True
        _note_on(made["Stream Deck"], sd)     # operator holds slot 8
        made["DDJ-800"]._mark_port_gone()     # co-controller absent/dead

        snap = group.snapshot()
        self.assertEqual(tuple(l.slot for l in snap.held_layers), (8,))  # look surfaced
        self.assertTrue(snap.worker_alive)     # NOT poisoned by the dead DDJ-800
        self.assertIsNone(snap.error)
        self.assertFalse(group.status()["worker_alive"])  # raw health still flags it

    def test_group_merges_layers_by_global_recency(self):
        other = PackMidiBinding(
            device_name="Other Controller", message_type="note",
            channel_zero_based=9, data_byte=123,
            target_kind="static_look", target_slot=17,
            interaction="toggle",
        )
        created = []

        def factory(bindings, *, stale_timeout_ms):
            adapter = SoundSwitchMidiInputAdapter(bindings, stale_timeout_ms=stale_timeout_ms)
            created.append(adapter)
            return adapter

        group = SoundSwitchMidiInputGroup((_TOGGLE8, other), {}, adapter_factory=factory)
        self.assertEqual(group.worker_count, 2)
        _note_on(created[0], _TOGGLE8)
        _note_on(created[1], other)

        snapshot = group.snapshot()
        self.assertEqual(tuple(layer.slot for layer in snapshot.held_layers), (8, 17))
        self.assertLess(snapshot.held_layers[0].seq, snapshot.held_layers[1].seq)

    def test_unknown_static_alias_reports_binding_gap_without_adapter(self):
        group = SoundSwitchMidiInputGroup(
            (_BLACKOUT,),
            {IAC: "IAC Driver Bus 1"},
            adapter_factory=lambda *args, **kwargs: self.fail("must not construct"),
        )
        self.assertEqual(group.worker_count, 0)
        self.assertEqual(group.status()["static_binding_gap_count"], 1)
        self.assertTrue(group.status()["static_binding_gap"])


# ---------------------------------------------------------------------------
# F10: active CC/pitch render control → compile_pack_artifacts must raise
# ---------------------------------------------------------------------------

def _minimal_project_identity() -> ProjectIdentity:
    from rb_ss_bridge_v2.soundswitch_project_decoder import CANONICAL_CONTAINER_VERSION
    return ProjectIdentity(
        project_uuid=CANONICAL_PROJECT_UUID,
        soundswitch_version=CANONICAL_SOUNDSWITCH_VERSION,
        container_version=CANONICAL_CONTAINER_VERSION,
        venue_guid=CANONICAL_VENUE_GUID,
        venue_name="RAVE Venue",
    )


def _make_binding(message_type: str) -> MidiBinding:
    msg_raw = {"note": 0, "control_change": 1, "pitch_bend": 2}[message_type]
    return MidiBinding(
        source_offset=0,
        device_name=DDJ,
        collection_id=0,
        message_type=message_type,  # type: ignore[arg-type]
        message_type_raw=msg_raw,
        data_byte=106,
        channel_zero_based=6,
        control_path="SoundSwitch.Controls.StaticOverride16",
        enabled=True,
    )


def _project_with_binding(message_type: str, target_kind: str) -> DecodedSoundSwitchProject:
    binding = _make_binding(message_type)
    midi_map = LearnedMidiMap(
        relative_path="SoundSwitchMIDIMap.bin",
        source_sha256="0" * 64,
        version=1,
        status=0,
        devices=(MidiDevice(
            name=DDJ,
            collections=(MidiCollection(collection_id=0, bindings=(binding,)),),
            feedback_bytes=b"",
        ),),
    )
    resolved = ResolvedControlBinding(
        binding=binding,
        target_kind=target_kind,  # type: ignore[arg-type]
        target_identity="SoundSwitch.Controls.StaticOverride16",
        target_index=16,
        target_name="Static Override 16",
    )
    return DecodedSoundSwitchProject(
        identity=_minimal_project_identity(),
        source_inventory=(),
        fixture_channels=(),
        attribute_cues=(),
        static_looks=(),
        autoloop_catalogs=(),
        autoloops=(),
        scripted_tracks=(),
        scripted_track_classifications=(),
        track_map=(),
        learned_midi_maps=(midi_map,),
        resolved_controls=(resolved,),
        no_target_policy_inputs=(),
        diagnostics=(),
    )


class TestF10ExportFail(unittest.TestCase):
    """F10: active CC/pitch render control must fail export with a relearn instruction."""

    def _assert_export_fails_with_relearn(self, project: DecodedSoundSwitchProject) -> None:
        with self.assertRaises(SoundSwitchPackCompileError) as cm:
            compile_pack_artifacts(project, generator_commit="test")
        msg = str(cm.exception)
        self.assertIn("relearn", msg)
        self.assertIn("note-capable", msg)

    def test_cc_static_look_fails_export(self):
        project = _project_with_binding("control_change", "static_look")
        self._assert_export_fails_with_relearn(project)

    def test_pitch_bend_static_look_fails_export(self):
        project = _project_with_binding("pitch_bend", "static_look")
        self._assert_export_fails_with_relearn(project)

    def test_cc_autoloop_fails_export(self):
        binding = MidiBinding(
            source_offset=0,
            device_name=IAC,
            collection_id=0,
            message_type="control_change",
            message_type_raw=1,
            data_byte=32,
            channel_zero_based=0,
            control_path="SoundSwitch.Controls.Autoloop1",
            enabled=True,
        )
        resolved = ResolvedControlBinding(
            binding=binding,
            target_kind="autoloop",
            target_identity="SSAutoLoop1.ssfile",
            target_index=None,
        )
        from rb_ss_bridge_v2.soundswitch_project_decoder import CANONICAL_CONTAINER_VERSION
        project = DecodedSoundSwitchProject(
            identity=_minimal_project_identity(),
            source_inventory=(), fixture_channels=(), attribute_cues=(),
            static_looks=(), autoloop_catalogs=(), autoloops=(),
            scripted_tracks=(), scripted_track_classifications=(), track_map=(),
            learned_midi_maps=(), resolved_controls=(resolved,),
            no_target_policy_inputs=(), diagnostics=(),
        )
        self._assert_export_fails_with_relearn(project)

    def test_note_static_look_does_not_fail_export(self):
        """Note-type bindings on static_look must NOT trigger F10."""
        project = _project_with_binding("note", "static_look")
        # Should not raise (may raise for other compile errors, but not F10)
        try:
            compile_pack_artifacts(project, generator_commit="test")
        except SoundSwitchPackCompileError as exc:
            self.assertNotIn("relearn", str(exc), "F10 must not fire for note type")

    def test_live_export_path_compiles_dynamically(self):
        """Live export compiles saved-project totals dynamically."""
        project = _project_with_binding("note", "static_look")  # valid identity, empty totals
        compile_pack_artifacts(project, generator_commit="test")

    def test_disabled_cc_binding_does_not_fail_export(self):
        """Disabled CC binding on static_look must not trigger F10."""
        binding = MidiBinding(
            source_offset=0, device_name=DDJ, collection_id=0,
            message_type="control_change", message_type_raw=1,
            data_byte=106, channel_zero_based=6,
            control_path="SoundSwitch.Controls.StaticOverride16",
            enabled=False,  # disabled
        )
        resolved = ResolvedControlBinding(
            binding=binding, target_kind="static_look",
            target_identity="SoundSwitch.Controls.StaticOverride16",
            target_index=16,
        )
        midi_map = LearnedMidiMap(
            relative_path="SoundSwitchMIDIMap.bin", source_sha256="0" * 64,
            version=1, status=0,
            devices=(MidiDevice(name=DDJ,
                                collections=(MidiCollection(collection_id=0, bindings=(binding,)),),
                                feedback_bytes=b""),),
        )
        project = DecodedSoundSwitchProject(
            identity=_minimal_project_identity(),
            source_inventory=(), fixture_channels=(), attribute_cues=(),
            static_looks=(), autoloop_catalogs=(), autoloops=(),
            scripted_tracks=(), scripted_track_classifications=(), track_map=(),
            learned_midi_maps=(midi_map,), resolved_controls=(resolved,),
            no_target_policy_inputs=(), diagnostics=(),
        )
        try:
            compile_pack_artifacts(project, generator_commit="test")
        except SoundSwitchPackCompileError as exc:
            self.assertNotIn("relearn", str(exc),
                             "F10 must not fire for disabled CC binding")

    def test_non_render_cc_does_not_fail_export(self):
        """CC binding with non-render target (no_target) must not trigger F10."""
        binding = MidiBinding(
            source_offset=0, device_name=IAC, collection_id=0,
            message_type="control_change", message_type_raw=1,
            data_byte=7, channel_zero_based=0,
            control_path="SoundSwitch.Controls.CueBeat",
            enabled=True,
        )
        resolved = ResolvedControlBinding(
            binding=binding, target_kind="no_target",
            target_identity=None, target_index=None,
        )
        project = DecodedSoundSwitchProject(
            identity=_minimal_project_identity(),
            source_inventory=(), fixture_channels=(), attribute_cues=(),
            static_looks=(), autoloop_catalogs=(), autoloops=(),
            scripted_tracks=(), scripted_track_classifications=(), track_map=(),
            learned_midi_maps=(), resolved_controls=(resolved,),
            no_target_policy_inputs=(), diagnostics=(),
        )
        try:
            compile_pack_artifacts(project, generator_commit="test")
        except SoundSwitchPackCompileError as exc:
            self.assertNotIn("relearn", str(exc),
                             "F10 must not fire for non-render CC binding")


if __name__ == "__main__":
    unittest.main()
