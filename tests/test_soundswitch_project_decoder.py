"""Focused tests for the strict, read-only SoundSwitch project decoder."""
from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import soundswitch_project_decoder as decoder
from rb_ss_bridge_v2.soundswitch_pack_models import (
    AutoloopCatalog,
    AutoloopCatalogEntry,
    AutoloopCategory,
    LearnedMidiMap,
    ControlLabelState,
    MidiBinding,
    MidiCollection,
    MidiDevice,
    StaticLook,
    TrackMapRecord,
)


def _trailer(field_a: int = 0, bool_a: int = 0, field_b: int = 0, bool_b: int = 1) -> bytes:
    return struct.pack("<IBIB", field_a, bool_a, field_b, bool_b)


def _ssfile(*, cue_count: int = 3, timeline_count: int = 3,
            raw_references: tuple[int, ...] = (0, 1, 3),
            stored_keys: tuple[int, ...] | None = None,
            trailer: bytes | None = None) -> bytes:
    if stored_keys is None:
        # Real fresh exports write 0-based writer-index keys; timeline
        # references resolve EXACTLY to a matching stored key (0 = clear
        # sentinel).
        stored_keys = tuple(range(cue_count))
    if len(stored_keys) != cue_count:
        raise ValueError("stored_keys must match cue_count")
    data = bytearray(44)
    data[:16] = decoder._MAGIC + struct.pack("<III", 3, 0, 0)
    data[28:44] = bytes.fromhex(decoder.CANONICAL_VENUE_GUID)
    data += struct.pack("<II", 1, cue_count)
    for index in range(cue_count):
        data += index.to_bytes(16, "little") + struct.pack("<I", stored_keys[index])
    data += struct.pack("<I", timeline_count)
    for index in range(timeline_count):
        data += struct.pack("<IIiI", 1, 1, index - 1, raw_references[index])
    data += _trailer() if trailer is None else trailer
    return bytes(data)


def _plain_string(value: str) -> bytes:
    raw = (value + "\0").encode("utf-16le")
    return struct.pack("<I", len(value) + 1) + raw


def _caf_string(value: str) -> bytes:
    raw = (value + "\0").encode("utf-16le")
    return struct.pack("<II", 1, len(value) + 1) + raw


def _venue_identity(guid: str = decoder.CANONICAL_VENUE_GUID) -> bytes:
    data = bytearray(44)
    struct.pack_into("<II", data, 20, 1, 4)
    data[28:44] = bytes.fromhex(guid)
    data += _caf_string("RAVE")
    return bytes(data)


def _fixture_cue(index: int, attributes: tuple[tuple[int, int, int], ...] = ()) -> bytes:
    """Build one scanned Venue cue record: name + guid + attribute rows.

    ``attributes`` is ``(fixture_group, channel_id, value)`` rows written
    physically after this record's own name/guid -- i.e. the block a
    ``decode_venue_cues`` linear scan would (pre-correction) have attached to
    THIS record, but which byte-proven precede-association reassigns to the
    NEXT scanned record.
    """
    name = _plain_string(f"C{index}")
    header = bytearray(60)
    header[4:20] = index.to_bytes(16, "little")
    struct.pack_into("<III", header, 20, 0, 1, 1)
    header[32:48] = b"P" * 16
    struct.pack_into("<III", header, 48, 1, 1, len(attributes))
    rows = b"".join(
        struct.pack("<III", 1, group, channel_id) + bytes([value]) * 4
        for group, channel_id, value in attributes
    )
    return name + bytes(header) + rows


def _tail_cue(index: int = 999) -> bytes:
    name = _plain_string("Default")
    count = 233
    return (name + b"TAIL" + index.to_bytes(16, "little") + b"\xff" * 4
            + struct.pack("<I", count) + struct.pack(f"<{count}I", *range(count)))


def _empty_look(index: int) -> bytes:
    return struct.pack("<I", 5) + _caf_string(f"slot {index}") + struct.pack("<IIIII", 0, 0, 0, 0, 0)


def _typed_string(value: str) -> bytes:
    return struct.pack("<I", 0x01380305) + value.encode() + b"\0"


def _learned_map(bindings: tuple[tuple[int, int, int, str, int], ...]) -> bytes:
    data = bytearray(struct.pack("<IHB", 0xDEADBEEF, 1, 0))
    data += struct.pack("<IQ", 0x01380308, 1)
    data += _typed_string("Device") + struct.pack("<IQ", 0x01380306, 1)
    data += struct.pack("<IIQ", 7, 0x01380306, len(bindings))
    for message, byte, channel, path, enabled in bindings:
        data += struct.pack("<IBBB", 0x01380307, message, byte, channel)
        data += _typed_string(path) + bytes([enabled])
    data += struct.pack("<IQ", 0x01380306, 2) + b"\x11\x22"
    data += struct.pack("<I", 0xDEADBEEF)
    return bytes(data)


def _control_label_state(rows: tuple[tuple[str, int, int], ...]) -> bytes:
    data = bytearray(struct.pack("<IH", 0xDEADBEEF, 1))
    data += struct.pack("<IQ", 0x01380308, len(rows))
    for path, rgba, mode in rows:
        data += _typed_string(path) + struct.pack("<IB", rgba, mode)
    data += struct.pack("<I", 0xDEADBEEF)
    return bytes(data)


def _state(path: str, mode: str) -> ControlLabelState:
    return ControlLabelState(0, "recordable/labels.dat", "0" * 64, path, 0, mode)  # type: ignore[arg-type]


def _empty_catalog(version: int = 3, layout: int = 2) -> bytes:
    return (decoder._MAGIC + struct.pack("<IIIII", version, 0, 0, layout, 1)
            + struct.pack("<I", 1) + _plain_string("bank")
            + struct.pack("<I", 0) + struct.pack("<I", 0) + b"\x01")


class PhysicalDocumentTests(unittest.TestCase):
    def test_count_257_and_exact_ten_byte_trailer(self):
        # stored_keys=(1,) so the shared raw_reference=1 matches exactly
        # (0 missing) and this is the unambiguous best physical candidate.
        data = _ssfile(cue_count=1, timeline_count=257, raw_references=(1,) * 257,
                       stored_keys=(1,), trailer=_trailer(8, 1, 0, 1))
        parsed = decoder.decode_ssfile(data, "synthetic.ssfile")
        self.assertEqual(len(parsed.timeline), 257)
        self.assertEqual(len(parsed.trailer), 10)
        self.assertEqual(parsed.trailer, _trailer(8, 1, 0, 1))

    def test_raw_zero_and_positive_references_resolve_exact_key(self):
        # References resolve EXACTLY against the file's own stored keys
        # (byte-proven 2026-07-02, capture parity_20260701T185231Z, 261/261).
        parsed = decoder.decode_ssfile(
            _ssfile(cue_count=3, timeline_count=3, raw_references=(0, 1, 2)),
            "synthetic.ssfile",
        )
        self.assertEqual(
            [(row.reference_kind, row.resolved_stored_key) for row in parsed.timeline],
            [("clear_control", None), ("cue", 1), ("cue", 2)],
        )
        self.assertEqual(parsed.timeline[1].resolved_cue_guid, (1).to_bytes(16, "little").hex())
        self.assertEqual(parsed.timeline[2].resolved_cue_guid, (2).to_bytes(16, "little").hex())

    def test_positive_raw_one_resolves_key_one(self):
        parsed = decoder.decode_ssfile(
            _ssfile(cue_count=2, timeline_count=1, raw_references=(1,)), "cold.ssfile"
        )
        self.assertEqual(parsed.timeline[0].resolved_stored_key, 1)
        self.assertIsNotNone(parsed.timeline[0].resolved_cue_guid)

    def test_actual_dictionary_maximum_raw_232_resolves_to_key_232(self):
        parsed = decoder.decode_ssfile(
            _ssfile(cue_count=233, timeline_count=1, raw_references=(232,)),
            "maximum.ssfile",
        )
        self.assertEqual(parsed.timeline[0].resolved_stored_key, 232)
        self.assertIsNotNone(parsed.timeline[0].resolved_cue_guid)

    def test_key_lookup_ignores_dictionary_order(self):
        # Keys are a per-file permutation ({FC10FC02}: 214/216 rows have
        # key != position); only exact stored_key == R may match, never
        # position.
        parsed = decoder.decode_ssfile(
            _ssfile(
                cue_count=3,
                timeline_count=2,
                raw_references=(43, 98),
                stored_keys=(43, 7, 98),
            ),
            "permuted.ssfile",
        )
        self.assertEqual([row.resolved_stored_key for row in parsed.timeline], [43, 98])
        self.assertEqual(parsed.timeline[0].resolved_cue_guid, (0).to_bytes(16, "little").hex())
        self.assertEqual(parsed.timeline[1].resolved_cue_guid, (2).to_bytes(16, "little").hex())

    def test_missing_key_is_preserved_as_unresolved_cue(self):
        parsed = decoder.decode_ssfile(
            _ssfile(cue_count=1, timeline_count=1, raw_references=(99,)),
            "missing-key.ssfile",
        )
        self.assertEqual(parsed.timeline[0].reference_kind, "cue")
        self.assertEqual(parsed.timeline[0].resolved_stored_key, 99)
        self.assertIsNone(parsed.timeline[0].resolved_cue_guid)

    def test_count_offset_eof_and_trailer_bounds_fail_closed(self):
        good = bytearray(_ssfile(cue_count=1, timeline_count=1, raw_references=(1,)))
        corrupt_count = bytearray(good)
        struct.pack_into("<I", corrupt_count, 48, 0xFFFFFFFF)
        with self.assertRaises(decoder.SoundSwitchDecodeError):
            decoder.decode_ssfile(bytes(corrupt_count), "count.ssfile")
        with self.assertRaises(decoder.SoundSwitchDecodeError):
            decoder.decode_ssfile(bytes(good[:-1]), "eof.ssfile")
        bad_bool = bytearray(good); bad_bool[-6] = 2
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "ssfile_trailer"):
            decoder.decode_ssfile(bytes(bad_bool), "trailer.ssfile")


class VenueAndStaticLookTests(unittest.TestCase):
    def test_all_233_venue_records_are_render_bearing_cues(self):
        # Under the byte-proven precede-association model (2026-07-02) every
        # venue record is a fixture_payload cue: the last record inherits the
        # 232nd fixture block, and the trailing 0xffffffff catalog-index
        # structure is file metadata, not a cue (the old "232 render + 1
        # catalog-tail" split was an artifact of the double off-by-one).
        data = b"".join(
            _fixture_cue(index, ((0x493, 82, index % 200),)) for index in range(232)
        ) + _tail_cue()
        cues = decoder.decode_venue_cues(data)
        self.assertEqual(len(cues), 233)
        self.assertTrue(all(cue.render_bearing for cue in cues))
        self.assertTrue(all(cue.record_kind == "fixture_payload" for cue in cues))
        # The tail-named record keeps its own identity but takes the last
        # fixture block's content; the catalog indices never become a cue's.
        self.assertEqual(cues[-1].name, "Default")
        self.assertEqual(
            [(row.fixture_group, row.dmx_channel, row.value) for row in cues[-1].attributes],
            [(0x493, 1, 231 % 200)],
        )
        self.assertEqual(cues[-1].catalog_indices, ())

    def test_precede_association_reassigns_attributes_to_next_record(self):
        # Byte-proven 2026-07-02 (capture parity_20260701T185231Z, 261/261):
        # each Venue cue's true content is the block physically PRECEDING
        # its own name/guid record.  A 3-record stream where scanner record
        # i is written with distinct payload P_i must decode so cue i's
        # attributes are record (i - 1)'s payload; record 0 has no
        # predecessor in this synthetic stream, so it recovers nothing
        # (empty attributes, not a decode failure). Anchor: MASTER STROBE
        # (guid 9b5b1d84cefdb041886c7def04d494fa, record at offset 100981)
        # truly carries the block scanned as the PRIOR record's (WHITE DOT
        # STROBE's) attributes.
        payload_a = ((0x493, 82, 11),)
        payload_b = ((0x493, 83, 22),)
        payload_c = ((0x493, 84, 33),)
        data = (_fixture_cue(0, payload_a) + _fixture_cue(1, payload_b)
                + _fixture_cue(2, payload_c))
        cues = decoder.decode_venue_cues(data)
        self.assertEqual([cue.cue_guid for cue in cues],
                         [(0).to_bytes(16, "little").hex(), (1).to_bytes(16, "little").hex(),
                          (2).to_bytes(16, "little").hex()])
        self.assertEqual(cues[0].attributes, ())
        self.assertEqual(cues[0].record_kind, "fixture_payload")
        self.assertEqual(
            [(row.fixture_group, row.dmx_channel, row.value) for row in cues[1].attributes],
            [(0x493, 1, 11)],
        )
        self.assertEqual(
            [(row.fixture_group, row.dmx_channel, row.value) for row in cues[2].attributes],
            [(0x493, 2, 22)],
        )

    def test_unique_primary_guid_collection_retains_all_32_empty_slots(self):
        marker = bytes.fromhex(decoder.CANONICAL_VENUE_GUID) + struct.pack("<II", 1, 32)
        data = b"prefix" + marker + b"".join(_empty_look(index) for index in range(32))
        looks = decoder.decode_static_looks(data)
        self.assertEqual(tuple(row.slot_index for row in looks), tuple(range(32)))
        self.assertTrue(all(not row.generic_attributes for row in looks))
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "expected one"):
            decoder.decode_static_looks(data + data)
        malformed_duplicate = data + marker + b"\x05\x00"
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "header, found 2"):
            decoder.decode_static_looks(malformed_duplicate)


class IdentityInventoryAndMidiTests(unittest.TestCase):
    def test_truncated_catalog_entry_header_fails_closed_as_decode_error(self):
        data = (decoder._MAGIC + struct.pack("<IIIII", 3, 0, 0, 2, 1)
                + struct.pack("<I", 1) + _plain_string("bank")
                + struct.pack("<I", 1) + b"\x00" * 15)
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "bounds"):
            decoder.decode_catalog(data, "SoundSwitchAutoLoops.bin")

    def test_wrong_uuid_same_venue_rejects_before_deeper_decode(self):
        manifest = json.dumps({
            "id": "{E34F6DCD-EBB9-4088-BD28-7BC0272D011A}",
            "version": {"major": 2, "minor": 10, "hotfix": 3},
        }).encode()
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "source_identity"):
            decoder._identity_gate({
                ".ssproj": manifest,
                "SoundSwitchVenues.bin": _venue_identity(),
                "broken-deeper.ssfile": b"malformed",
            })

    def test_public_decode_identity_preflight_precedes_symlink_inventory_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p.ssproj"; root.mkdir()
            (root / ".ssproj").write_text(json.dumps({
                "id": "{E34F6DCD-EBB9-4088-BD28-7BC0272D011A}",
                "version": {"major": 2, "minor": 10, "hotfix": 3},
            }))
            (root / "SoundSwitchVenues.bin").write_bytes(_venue_identity())
            target = root / "target"; target.write_bytes(b"x")
            os.symlink(target, root / "later-symlink")
            with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "source_identity"):
                decoder.decode_project(root)

    def test_stable_read_source_drift_symlink_and_case_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p.ssproj"; root.mkdir()
            source = root / "a.bin"; source.write_bytes(b"one")
            inventory, blobs = decoder._snapshot_tree(root)
            self.assertEqual(blobs, {"a.bin": b"one"})
            decoder._assert_stable(root, inventory)
            source.write_bytes(b"two")
            with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "source_drift"):
                decoder._assert_stable(root, inventory)
            source.unlink()
            with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "source_drift"):
                decoder._assert_stable(root, inventory)
            source.write_bytes(b"one")
            inventory, _ = decoder._snapshot_tree(root)
            (root / "extra.bin").write_bytes(b"extra")
            with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "source_drift"):
                decoder._assert_stable(root, inventory)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p.ssproj"; root.mkdir()
            target = root / "target"; target.write_bytes(b"x")
            os.symlink(target, root / "link")
            with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "symlink"):
                decoder._snapshot_tree(root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p.ssproj"; root.mkdir()
            first = root / "first"; second = root / "second"
            first.write_bytes(b"a"); second.write_bytes(b"b")
            class Entry:
                def __init__(self, name: str, path: Path) -> None:
                    self.name = name; self.path = str(path)
                def is_symlink(self) -> bool: return False
                def is_dir(self, *, follow_symlinks: bool) -> bool: return False
                def is_file(self, *, follow_symlinks: bool) -> bool: return True
            entries = [Entry("Straße", first), Entry("STRASSE", second)]
            with mock.patch.object(decoder.os, "scandir", return_value=entries):
                with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "case_collision"):
                    decoder._snapshot_tree(root)

    def test_complete_learned_map_preserves_fields_and_eof(self):
        data = _learned_map(((0, 99, 3, "SoundSwitch.Controls.StaticOverride7", 1),))
        mapping = decoder.decode_learned_midi(data, "recordable/map.dat")
        self.assertIsNotNone(mapping)
        assert mapping is not None
        binding = mapping.devices[0].collections[0].bindings[0]
        self.assertEqual((binding.message_type, binding.data_byte, binding.channel_zero_based),
                         ("note", 99, 3))
        self.assertEqual(mapping.devices[0].feedback_bytes, b"\x11\x22")
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "trailing"):
            decoder.decode_learned_midi(data + b"x", "recordable/map.dat")

    def test_control_label_state_decodes_press_and_toggle_modes(self):
        press = "SoundSwitch.Controls.StaticOverride8"
        toggle = "SoundSwitch.Controls.StaticOverride9"
        data = _control_label_state(((press, 0xFF66B14C, 0), (toggle, 0xFFA500FF, 1)))

        states = decoder.decode_control_label_states(data, "recordable/labels.dat")

        self.assertIsNotNone(states)
        assert states is not None
        by_path = {row.control_path: row for row in states}
        self.assertEqual(by_path[press].interaction_mode, "press")
        self.assertEqual(by_path[toggle].interaction_mode, "toggle")
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "trailing"):
            decoder.decode_control_label_states(data + b"x", "recordable/labels.dat")

    def test_catalog_version_is_pinned_to_three(self):
        parsed = decoder.decode_catalog(_empty_catalog(), "synthetic.bin")
        self.assertEqual(parsed.version, 3)
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "catalog_header"):
            decoder.decode_catalog(_empty_catalog(version=999), "synthetic.bin")

    def test_catalog_and_static_resolution_and_render_collision(self):
        entry = AutoloopCatalogEntry(0, 0, 42, 43, 32, True, "renamable", 0, "bank")
        catalog = AutoloopCatalog("catalog", "0" * 64, 3, 2,
                                  (AutoloopCategory(0, 0, "bank", True, (42,)),), (entry,))
        empty_look = lambda index: StaticLook(0, 0, index, 5, f"look-{index}", (), (), (), (), ())
        looks = tuple(empty_look(index) for index in range(32))
        bindings = (
            MidiBinding(0, "Device", 1, "note", 0, 77, 0,
                        "SoundSwitch.Controls.AutoLoopsPlayAutoloop0", True),
            MidiBinding(1, "Device", 1, "note", 0, 78, 0,
                        "SoundSwitch.Controls.StaticOverride9", True),
        )
        mapping = LearnedMidiMap("map", "0" * 64, 1, 0,
                                 (MidiDevice("Device", (MidiCollection(1, bindings),), b""),))
        states = {
            "SoundSwitch.Controls.StaticOverride8": _state("SoundSwitch.Controls.StaticOverride8", "toggle"),
            "SoundSwitch.Controls.StaticOverride9": _state("SoundSwitch.Controls.StaticOverride9", "press"),
            "SoundSwitch.Controls.StaticOverride31": _state("SoundSwitch.Controls.StaticOverride31", "toggle"),
            "SoundSwitch.Controls.StaticOverride0": _state("SoundSwitch.Controls.StaticOverride0", "press"),
        }
        rows = decoder._resolve_controls(
            (mapping,), (catalog,), looks, {"SSAutoLoop43.ssfile"}, states,
        )
        self.assertEqual((rows[0].target_identity, rows[0].target_index), ("SSAutoLoop43.ssfile", 42))
        self.assertEqual(
            (rows[1].target_identity, rows[1].target_index, rows[1].target_name,
             rows[1].interaction_mode),
            (f"{decoder.CANONICAL_VENUE_GUID}:slot:9", 9, "look-9", "press"),
        )

        collision = bindings + (
            MidiBinding(2, "Device", 1, "note", 0, 77, 0,
                        "SoundSwitch.Controls.StaticOverride8", True),
        )
        mapping = LearnedMidiMap("map", "0" * 64, 1, 0,
                                 (MidiDevice("Device", (MidiCollection(1, collision),), b""),))
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "midi_collision"):
            decoder._resolve_controls((mapping,), (catalog,), looks, {"SSAutoLoop43.ssfile"}, states)

        disabled = MidiBinding(3, "Device", 1, "note", 0, 79, 0,
                               "SoundSwitch.Controls.StaticOverride31", False)
        disabled_map = LearnedMidiMap("map", "0" * 64, 1, 0,
                                      (MidiDevice("Device", (MidiCollection(1, (disabled,)),), b""),))
        disabled_row = decoder._resolve_controls(
            (disabled_map,), (catalog,), looks[:1], {"SSAutoLoop43.ssfile"}, states,
        )[0]
        self.assertFalse(disabled_row.binding.enabled)
        self.assertEqual(disabled_row.target_identity,
                         f"{decoder.CANONICAL_VENUE_GUID}:slot:31")

        cc = MidiBinding(4, "Device", 1, "control_change", 1, 80, 0,
                         "SoundSwitch.Controls.StaticOverride0", True)
        cc_map = LearnedMidiMap("map", "0" * 64, 1, 0,
                                (MidiDevice("Device", (MidiCollection(1, (cc,)),), b""),))
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "unsupported_active_control"):
            decoder._resolve_controls((cc_map,), (catalog,), looks, {"SSAutoLoop43.ssfile"}, states)

    def test_catalog_autoloop_reconciliation_detects_missing_and_orphan_files(self):
        entry = AutoloopCatalogEntry(0, 0, 0, 1, 32, True, "one", 0, "bank")
        catalog = AutoloopCatalog("catalog", "0" * 64, 3, 2,
                                  (AutoloopCategory(0, 0, "bank", True, (0,)),), (entry,))
        document = decoder.decode_ssfile(
            _ssfile(cue_count=1, timeline_count=1, raw_references=(1,)),
            "SSAutoLoop1.ssfile",
        )
        decoder._reconcile_catalog_autoloops((catalog,), (document,))
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "missing"):
            decoder._reconcile_catalog_autoloops((catalog,), ())
        orphan = decoder.decode_ssfile(
            _ssfile(cue_count=1, timeline_count=1, raw_references=(1,)),
            "SSAutoLoop2.ssfile",
        )
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "orphaned"):
            decoder._reconcile_catalog_autoloops((catalog,), (document, orphan))

        alternate = bytearray(_ssfile(cue_count=1, timeline_count=1, raw_references=(0,)))
        alternate[28:44] = bytes.fromhex("b7527f4d5debc6499fb9cdb82b591239")
        alternate_document = decoder.decode_ssfile(
            bytes(alternate), "SSAutoLoop1.ssfile"
        )
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "unsupported_active_layout"):
            decoder._reconcile_catalog_autoloops((catalog,), (alternate_document,))

    def test_missing_cue_surfaces_active_diagnostic_and_unsupported_layout_fails_closed(self):
        # cue_count=2 so raw_reference=1 resolves EXACTLY to stored_key=1
        # (present), matching but outside the (empty) venue cue GUID set.
        document = decoder.decode_ssfile(
            _ssfile(cue_count=2, timeline_count=1, raw_references=(1,)),
            "{025C1DDF-2CDC-4E54-BD8C-156B90DD8247}.ssfile",
        )
        diagnostics = decoder._validate_document_cues(
            (document,), set(), decoder.CANONICAL_VENUE_GUID
        )
        self.assertEqual(diagnostics[0].code, "active_missing_cue")
        self.assertTrue(diagnostics[0].active)
        with self.assertRaises(decoder.SoundSwitchDecodeError):
            decoder.decode_ssfile(b"unsupported", document.relative_path)
        normal = TrackMapRecord(0, "025C1DDF-2CDC-4E54-BD8C-156B90DD8247",
                                "normal", "artist", "/saved/normal.wav")
        self.assertFalse(decoder._is_bounded_in_app_demo(normal.soundswitch_id, (normal,), {}))

    def test_saved_trackmap_mapping_add_remove_changes_script_activity(self):
        ssid = "025C1DDF-2CDC-4E54-BD8C-156B90DD8247"
        relative = f"{{{ssid}}}.ssfile"
        alternate_guid = "b7527f4d5debc6499fb9cdb82b591239"
        mapping = TrackMapRecord(0, ssid, "saved", "artist", "/saved/source.wav")

        removed = decoder._classify_script_source(relative, alternate_guid, (), {})
        self.assertEqual(removed.status, "inactive_unmapped_alternate_profile")
        with self.assertRaisesRegex(decoder.SoundSwitchDecodeError, "unsupported_active_layout"):
            decoder._classify_script_source(relative, alternate_guid, (mapping,), {})

        primary_unmapped = decoder._classify_script_source(
            relative, decoder.CANONICAL_VENUE_GUID, (), {}
        )
        self.assertEqual(primary_unmapped.status, "inactive_unmapped_primary")
        primary_mapped = decoder._classify_script_source(
            relative, decoder.CANONICAL_VENUE_GUID, (mapping,), {}
        )
        self.assertEqual(primary_mapped.status, "supported_mapped_primary")


class CurrentCorpusTests(unittest.TestCase):
    def test_current_canonical_corpus_when_available(self):
        project = Path.home() / "Music" / "SoundSwitch" / "default.ssproj"
        if not project.is_dir():
            self.skipTest("canonical local SoundSwitch project is unavailable")
        decoded = decoder.decode_project(
            project,
            no_target_policy_inputs=("channel-2-safe", "breakdown", "post-drop"),
        )
        self.assertGreater(len(decoded.render_cues), 0)
        self.assertTrue(all(row.record_kind == "fixture_payload" for row in decoded.render_cues))
        # Under precede-association (byte-proven 2026-07-02) every venue
        # record is a render-bearing fixture_payload cue; the file-tail
        # catalog-index structure is metadata, not a cue.
        self.assertEqual(decoded.catalog_tail_cues, ())
        self.assertEqual(len(decoded.render_cues), len(decoded.attribute_cues))
        # Recovered head block: the 'OFF' cue truly writes 0 everywhere.
        off = decoded.attribute_cues[0]
        self.assertEqual(off.name, "OFF")
        self.assertTrue(off.attributes)
        self.assertTrue(all(row.value == 0 for row in off.attributes))
        self.assertEqual(len(decoded.static_looks), 32)
        self.assertGreater(len(decoded.autoloops), 0)
        statuses = [row.status for row in decoded.scripted_track_classifications]
        self.assertGreater(statuses.count("supported_mapped_primary"), 0)
        self.assertEqual(len(decoded.no_target_policy_inputs), 3)
        self.assertTrue(any(row.code == "unsupported_inactive_script" for row in decoded.diagnostics))
        enabled = [row for row in decoded.resolved_controls if row.binding.enabled]
        self.assertTrue(any(row.target_kind == "autoloop" for row in enabled))
        static_rows = [row for row in enabled if row.target_kind == "static_look"]
        self.assertTrue(static_rows)
        self.assertTrue(all(isinstance(row.target_index, int) and 0 <= row.target_index < 32
                            for row in static_rows))
        self.assertTrue(all(row.interaction_mode in ("press", "toggle") for row in static_rows))
        inventory_script_ids = {
            match.group(1).upper()
            for row in decoded.source_inventory
            if (match := decoder._SCRIPT_NAME.fullmatch(row.relative_path))
        }
        mapped_ids = {row.soundswitch_id for row in decoded.track_map}
        unmapped_ids = inventory_script_ids - mapped_ids
        alternate_profile_ids = {
            decoder._SCRIPT_NAME.fullmatch(row.relative_path).group(1).upper()
            for row in decoded.scripted_tracks
            if row.fixture_profile_guid != decoder.CANONICAL_VENUE_GUID
        }
        self.assertEqual(unmapped_ids, alternate_profile_ids)
        self.assertTrue(all(row.locator_state == "saved_unverified" for row in decoded.track_map))
        opaque_paths = {row.relative_path for row in decoded.diagnostics if row.code == "opaque_artifact"}
        self.assertIn("automation_presets/PRESET 1.sspreset", opaque_paths)
        self.assertIn("SoundSwitchVenues.bin.backup", opaque_paths)


if __name__ == "__main__":
    unittest.main()
