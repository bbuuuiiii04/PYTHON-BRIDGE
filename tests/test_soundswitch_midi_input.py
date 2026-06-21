"""Tests for soundswitch_midi_input — no MIDI/serial/Art-Net hardware opened."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_midi_input import (
    MidiInputSnapshot,
    PackMidiBinding,
    SoundSwitchMidiInputAdapter,
)
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
_BLACKOUT = PackMidiBinding(
    device_name=IAC, message_type="note",
    channel_zero_based=0, data_byte=0,
    target_kind="blackout_mask",
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


# ---------------------------------------------------------------------------
# Snapshot API
# ---------------------------------------------------------------------------

class TestSnapshotInitial(unittest.TestCase):
    def test_initial_state(self):
        a = _adapter(_SLOT8)
        s = a.snapshot()
        self.assertIsNone(s.held_static_slot)
        self.assertFalse(s.blackout_held)
        self.assertFalse(s.worker_alive)
        self.assertEqual(s.mail_drop_count, 0)


class TestSnapshotImmutable(unittest.TestCase):
    def test_snapshot_is_frozen(self):
        a = _adapter(_SLOT8)
        s = a.snapshot()
        self.assertIsInstance(s, MidiInputSnapshot)
        with self.assertRaises(Exception):
            s.held_static_slot = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Note-on velocity-0 normalization
# ---------------------------------------------------------------------------

class TestNoteOnVelocityZero(unittest.TestCase):
    def test_vel0_treated_as_note_off(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)                 # select
        self.assertEqual(a.snapshot().held_static_slot, 8)
        _note_on_vel0(a, _SLOT8)            # must behave as note-off
        self.assertIsNone(a.snapshot().held_static_slot)

    def test_vel0_without_prior_select_is_noop(self):
        a = _adapter(_SLOT8)
        _note_on_vel0(a, _SLOT8)
        self.assertIsNone(a.snapshot().held_static_slot)


# ---------------------------------------------------------------------------
# Static Override select / release / idempotency
# ---------------------------------------------------------------------------

class TestStaticOverride(unittest.TestCase):
    def test_note_on_selects_slot(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        self.assertEqual(a.snapshot().held_static_slot, 8)

    def test_note_off_releases_current(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        _note_off(a, _SLOT8)
        self.assertIsNone(a.snapshot().held_static_slot)

    def test_repeated_note_on_idempotent(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT8)
        self.assertEqual(a.snapshot().held_static_slot, 8)

    def test_note_off_noop_when_not_held(self):
        a = _adapter(_SLOT8)
        _note_off(a, _SLOT8)
        self.assertIsNone(a.snapshot().held_static_slot)

    def test_slot17_replaces_slot8(self):
        a = _adapter(_SLOT8, _SLOT17)
        _note_on(a, _SLOT8)
        self.assertEqual(a.snapshot().held_static_slot, 8)
        _note_on(a, _SLOT17)
        self.assertEqual(a.snapshot().held_static_slot, 17)

    def test_release_old_slot_does_not_clear_new(self):
        """Adversarial target #1: slot 8 → slot 17 → release 8 must leave slot 17."""
        a = _adapter(_SLOT8, _SLOT17)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT17)
        _note_off(a, _SLOT8)              # release the old (non-current) slot
        self.assertEqual(a.snapshot().held_static_slot, 17)

    def test_release_slot17_after_replacing_slot8(self):
        """Correct note-off for the new slot clears it."""
        a = _adapter(_SLOT8, _SLOT17)
        _note_on(a, _SLOT8)
        _note_on(a, _SLOT17)
        _note_off(a, _SLOT17)
        self.assertIsNone(a.snapshot().held_static_slot)


# ---------------------------------------------------------------------------
# Blackout mask
# ---------------------------------------------------------------------------

class TestBlackoutMask(unittest.TestCase):
    def test_note_on_holds_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        self.assertTrue(a.snapshot().blackout_held)

    def test_note_off_releases_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        _note_off(a, _BLACKOUT)
        self.assertFalse(a.snapshot().blackout_held)

    def test_vel0_releases_blackout(self):
        a = _adapter(_BLACKOUT)
        _note_on(a, _BLACKOUT)
        _note_on_vel0(a, _BLACKOUT)
        self.assertFalse(a.snapshot().blackout_held)


# ---------------------------------------------------------------------------
# Non-render controls do not mutate player state
# ---------------------------------------------------------------------------

class TestNonRenderControls(unittest.TestCase):
    def test_pack_selection_does_not_set_static_slot(self):
        a = _adapter(_PACK_SEL)
        _note_on(a, _PACK_SEL)
        s = a.snapshot()
        self.assertIsNone(s.held_static_slot)
        self.assertFalse(s.blackout_held)

    def test_inactive_report_only_is_noop(self):
        a = _adapter(_INACTIVE)
        _note_on(a, _INACTIVE)
        s = a.snapshot()
        self.assertIsNone(s.held_static_slot)
        self.assertFalse(s.blackout_held)


# ---------------------------------------------------------------------------
# Panic / reload / stop clears held state
# ---------------------------------------------------------------------------

class TestClearOnEvent(unittest.TestCase):
    def test_panic_clears_static_slot(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        a.panic()
        s = a.snapshot()
        self.assertIsNone(s.held_static_slot)
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
        self.assertIsNone(s.held_static_slot)
        self.assertFalse(s.blackout_held)

    def test_stop_clears_state(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        a.stop()
        self.assertIsNone(a.snapshot().held_static_slot)

    def test_worker_death_clears_state(self):
        a = _adapter(_SLOT8)
        _note_on(a, _SLOT8)
        a._clear_held("worker_death")       # simulate worker dying
        self.assertIsNone(a.snapshot().held_static_slot)
        self.assertFalse(a.snapshot().worker_alive)


# ---------------------------------------------------------------------------
# Disabled bindings / unknown messages
# ---------------------------------------------------------------------------

class TestDisabledAndUnknown(unittest.TestCase):
    def test_unregistered_note_is_silently_ignored(self):
        a = _adapter(_SLOT8)
        # Note 99 on ch9 is not registered
        a._feed_raw_message(0x99, 99, 64)
        self.assertIsNone(a.snapshot().held_static_slot)

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
        self.assertIsNone(s.held_static_slot)
        self.assertFalse(s.blackout_held)


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


def _make_binding(message_type: str, target_kind: str) -> MidiBinding:
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
    binding = _make_binding(message_type, target_kind)
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
            compile_pack_artifacts(project, generator_commit="test", enforce_pinned_totals=False)
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
        # Should not raise (may raise on pinned-totals mismatch, not F10)
        try:
            compile_pack_artifacts(project, generator_commit="test",
                                   enforce_pinned_totals=False)
        except SoundSwitchPackCompileError as exc:
            self.assertNotIn("relearn", str(exc), "F10 must not fire for note type")

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
            compile_pack_artifacts(project, generator_commit="test",
                                   enforce_pinned_totals=False)
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
            compile_pack_artifacts(project, generator_commit="test",
                                   enforce_pinned_totals=False)
        except SoundSwitchPackCompileError as exc:
            self.assertNotIn("relearn", str(exc),
                             "F10 must not fire for non-render CC binding")


if __name__ == "__main__":
    unittest.main()
