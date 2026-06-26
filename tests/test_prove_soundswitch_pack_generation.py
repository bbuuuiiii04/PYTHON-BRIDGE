"""Unit tests for the SoundSwitch pack-generation proof gate's pure logic.

These run WITHOUT the live SoundSwitch project, without network, and without any
MIDI/serial/Art-Net/Enttec/DMX device. They lock the load-bearing guards:
identity rejection (wrong UUID / version / Venue), the primary-laser CH1-CH19
renderer, and the verdict state machine.
"""
from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_static_looks import venue_fixture

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "prove_soundswitch_pack_generation.py"
_SPEC = importlib.util.spec_from_file_location("prove_soundswitch_pack_generation", _TOOL)
prove = importlib.util.module_from_spec(_SPEC)
sys.modules["prove_soundswitch_pack_generation"] = prove
assert _SPEC.loader is not None
_SPEC.loader.exec_module(prove)


def _make_project(tmp: Path, uuid: str, version: dict, venue: bytes) -> Path:
    project = tmp / "p.ssproj"
    project.mkdir()
    (project / ".ssproj").write_text(json.dumps({"id": uuid, "version": version}))
    (project / "SoundSwitchVenues.bin").write_bytes(venue)
    return project


_GOOD_VERSION = {"major": 2, "minor": 10, "hotfix": 3, "build": 0}


class SourceIdentityGateTests(unittest.TestCase):
    def test_canonical_project_is_authorized(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp), prove.CANONICAL_PROJECT_UUID, _GOOD_VERSION, venue_fixture())
            gate = prove.assert_source_identity(project)
        self.assertTrue(gate["authorized"], gate["reasons"])
        self.assertEqual(gate["venue_guid"], prove.CANONICAL_VENUE_GUID)

    def test_wrong_uuid_same_venue_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Same RAVE Venue GUID, different project UUID -> must reject (R1).
            project = _make_project(Path(tmp), "{E34F6DCD-EBB9-4088-BD28-7BC0272D011A}", _GOOD_VERSION, venue_fixture())
            gate = prove.assert_source_identity(project)
        self.assertFalse(gate["authorized"])
        self.assertEqual(gate["venue_guid"], prove.CANONICAL_VENUE_GUID)
        self.assertTrue(any("UUID" in reason for reason in gate["reasons"]))

    def test_wrong_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(
                Path(tmp), prove.CANONICAL_PROJECT_UUID,
                {"major": 2, "minor": 9, "hotfix": 0, "build": 0}, venue_fixture())
            gate = prove.assert_source_identity(project)
        self.assertFalse(gate["authorized"])
        self.assertTrue(any("version" in reason for reason in gate["reasons"]))

    def test_wrong_venue_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = bytearray(venue_fixture())
            data[28:44] = bytes(reversed(data[28:44]))  # corrupt primary GUID
            project = _make_project(Path(tmp), prove.CANONICAL_PROJECT_UUID, _GOOD_VERSION, bytes(data))
            gate = prove.assert_source_identity(project)
        self.assertFalse(gate["authorized"])


class PrimaryFrameRendererTests(unittest.TestCase):
    def test_renders_primary_group_into_19_byte_frame(self):
        frame = prove._render_primary_ch_frame({"0x493": {"1": 0x26, "3": 0x1d}, "0x496": {"1": 0xff}})
        self.assertEqual(len(frame), 19)
        self.assertEqual(frame[0], 0x26)
        self.assertEqual(frame[2], 0x1d)
        self.assertEqual(sum(frame[3:]), 0)  # mirror group 0x496 ignored for primary frame

    def test_frame_hex_roundtrip(self):
        self.assertEqual(prove._frame_hex([0, 0x15, 0xff] + [0] * 16), "0015ff" + "00" * 16)


class VerdictStateMachineTests(unittest.TestCase):
    def _chk(self, status, foundation):
        return {"status": status, "foundation": foundation}

    def test_any_fail_blocks(self):
        checks = [self._chk("PASS", True), self._chk("FAIL", True)]
        self.assertEqual(prove.compute_verdict(checks), "FAIL_DO_NOT_IMPLEMENT")

    def test_foundation_incomplete_blocks(self):
        checks = [self._chk("PASS", True), self._chk("INCOMPLETE", True)]
        self.assertEqual(prove.compute_verdict(checks), "INCOMPLETE_PROOF_BLOCKER")

    def test_deferred_incomplete_allows_pass(self):
        checks = [self._chk("PASS", True), self._chk("INCOMPLETE", False)]
        self.assertEqual(prove.compute_verdict(checks), "PASS_IMPLEMENTATION_MAY_BEGIN")

    def test_all_foundation_pass(self):
        checks = [self._chk("PASS", True), self._chk("PASS", True)]
        self.assertEqual(prove.compute_verdict(checks), "PASS_IMPLEMENTATION_MAY_BEGIN")


class CanonicalConstantsTests(unittest.TestCase):
    def test_ddj_golden_frames_are_19_bytes(self):
        for slot, (_note, _control, _name, hex_frame) in prove.GOLDEN_DDJ.items():
            self.assertEqual(len(hex_frame), 38, slot)  # 19 bytes


class PackMutationGateTests(unittest.TestCase):
    def test_f9_requires_fresh_verify_and_mutation_rejection(self):
        def fake_export(_project, pack):
            pack.mkdir()
            (pack / "static_looks.json").write_bytes(b'{"x":1}\n')
            return {"verified": True}
        with mock.patch.object(prove, "export_pack", side_effect=fake_export), \
                mock.patch.object(prove, "verify_pack", side_effect=[
                    {"verified": True}, prove.SoundSwitchPackVerificationError("mutation")]):
            result = prove._prove_pack_mutation(Path("unused"))
        self.assertTrue(result["ok"])
        self.assertTrue(result["one_byte_mutation_rejected"])


class ExitCodeTests(unittest.TestCase):
    def test_pass_exits_zero(self):
        self.assertEqual(prove.verdict_exit_code("PASS_IMPLEMENTATION_MAY_BEGIN"), 0)

    def test_incomplete_blocker_fails_closed(self):
        self.assertNotEqual(prove.verdict_exit_code("INCOMPLETE_PROOF_BLOCKER"), 0)

    def test_fail_fails_closed(self):
        self.assertNotEqual(prove.verdict_exit_code("FAIL_DO_NOT_IMPLEMENT"), 0)


if __name__ == "__main__":
    unittest.main()
