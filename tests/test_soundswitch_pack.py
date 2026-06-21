"""Task 2 tests for canonical SoundSwitch pack export and verification."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack import (
    canonical_json_bytes,
    render_document_boundaries,
    render_static_look_frame,
)
from rb_ss_bridge_v2.soundswitch_pack_models import (
    AttributeCue, CueAttribute, LightingDocument, StaticLook, TimelineRecord,
)
from rb_ss_bridge_v2.soundswitch_pack_verifier import (
    SoundSwitchPackVerificationError, verify_pack,
)
from rb_ss_bridge_v2 import soundswitch_pack_verifier as verifier_module
from rb_ss_bridge_v2.tools.export_soundswitch_pack import export_pack


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode()


class PurePackCompilerTests(unittest.TestCase):
    def test_boundary_renderer_preserves_equal_time_source_order_and_control_clear(self):
        cue_a = AttributeCue(1, 2, "fixture_payload", "a", "a" * 32, "p",
                             (CueAttribute(1, 0x493, 82, 1, 9),
                              CueAttribute(2, 0x493, 263, 8, 77)))
        cue_b = AttributeCue(3, 4, "fixture_payload", "b", "b" * 32, "p",
                             (CueAttribute(3, 0x493, 82, 1, 12),))
        timeline = (
            TimelineRecord(100, 1, -1, 1, "cue", 0, cue_a.cue_guid),
            TimelineRecord(116, 1, 0, 2, "cue", 1, cue_b.cue_guid),
            TimelineRecord(132, 1, 0, 0, "clear_control", None, None),
        )
        doc = LightingDocument("SSAutoLoop1.ssfile", "0" * 64, 1, 3, "p", "x", 1,
                               (), timeline, (), 1, b"0123456789", "1" * 64, None)
        rows = render_document_boundaries(doc, {cue_a.cue_guid: cue_a, cue_b.cue_guid: cue_b})
        self.assertEqual([row["source_order"] for row in rows], [0, 1, 2])
        self.assertEqual(rows[1]["frame"][0], 12)
        self.assertEqual(rows[2]["frame"][0], 0)
        self.assertEqual(rows[2]["frame"][7], 77)  # CH8 control persists

    def test_static_renderer_uses_primary_group_only(self):
        look = StaticLook(0, 1, 0, 5, "x", (), (), (), (), (
            CueAttribute(0, 0x493, 82, 1, 7), CueAttribute(1, 0x494, 83, 2, 99)))
        self.assertEqual(render_static_look_frame(look), (7,) + (0,) * 18)

    def test_canonical_json_is_stable_and_rejects_nan(self):
        self.assertEqual(canonical_json_bytes({"b": 1, "a": 2}), b'{"a":2,"b":1}\n')
        with self.assertRaises(ValueError):
            canonical_json_bytes({"bad": float("nan")})


@unittest.skipUnless((Path.home() / "Music/SoundSwitch/default.ssproj/.ssproj").is_file(),
                     "canonical read-only SoundSwitch project is unavailable")
class CurrentProjectPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        cls.project = Path.home() / "Music/SoundSwitch/default.ssproj"
        cls.pack = cls.root / "pack"
        export_pack(cls.project, cls.pack)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def _copy(self, name: str) -> Path:
        target = self.root / name
        shutil.copytree(self.pack, target)
        return target

    def _semantic_mutation(self, pack: Path, relative: str, mutate) -> None:
        path = pack / relative
        value = json.loads(path.read_text())
        mutate(value)
        data = _canonical(value)
        path.write_bytes(data)
        manifest_path = pack / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        row = next(item for item in manifest["artifact_hashes"] if item["path"] == relative)
        row["size"] = len(data); row["sha256"] = _sha(data)
        manifest_path.write_bytes(_canonical(manifest))

    def assertRejected(self, pack: Path):
        with self.assertRaises(SoundSwitchPackVerificationError):
            verify_pack(pack)

    def test_current_totals_crosswalk_and_catalog_tail(self):
        result = verify_pack(self.pack, source_project=self.project)
        self.assertTrue(result["verified"])
        manifest = json.loads((self.pack / "manifest.json").read_text())
        self.assertEqual(manifest["totals"]["total_venue_records"], 233)
        self.assertEqual(manifest["totals"]["render_cues"], 232)
        self.assertEqual(manifest["totals"]["catalog_tail_records"], 1)
        self.assertEqual(manifest["totals"]["static_looks"], 32)
        self.assertEqual(manifest["totals"]["total_autoloops"], 42)
        self.assertEqual(manifest["totals"]["scripted_inventory"], 45)
        self.assertEqual(manifest["totals"]["parsed_scripted"], 44)
        selection = json.loads((self.pack / "selection_map.json").read_text())
        self.assertTrue(any(row["resolution"] == "no_project_target"
                            for row in selection["bridge_scenes"]))
        self.assertEqual(sorted(row["target_index"] for row in selection["learned_controls"]
                                if row["active"] and row["target_kind"] == "static_look"),
                         [8, 16, 17, 24])
        self.assertEqual(set(selection["classification_policy"]), {
            "pack_selection", "static_override", "blackout_mask", "bridge_owned_safety",
            "no_project_target", "inactive_report_only", "unsupported_fail_export"})
        self.assertEqual(selection["manual_blackout"]["control_classification"], "blackout_mask")
        scenes = {row["policy_name"]: row for row in selection["bridge_scenes"]}
        self.assertEqual(scenes["house_post_drop_1"]["control_classification"],
                         "inactive_report_only")
        self.assertEqual(scenes["house_breakdown_1"]["control_classification"],
                         "no_project_target")
        for name in ("safe_static", "transition_safe_1", "emergency_blackout"):
            self.assertEqual(scenes[name]["control_classification"], "bridge_owned_safety")
        selected = [row for row in selection["learned_controls"]
                    if row["target_kind"] == "autoloop" and row["data_byte"] != 0]
        self.assertTrue(selected)
        self.assertTrue(all(row["control_classification"] == "pack_selection" for row in selected))
        overrides = [row for row in selection["learned_controls"]
                     if row["target_kind"] == "static_look" and row["active"]]
        self.assertTrue(all(row["control_classification"] == "static_override" for row in overrides))

    def test_two_exports_are_byte_identical(self):
        second = self.root / "pack-second"
        export_pack(self.project, second)
        first_rows = {p.relative_to(self.pack).as_posix(): p.read_bytes()
                      for p in self.pack.rglob("*") if p.is_file()}
        second_rows = {p.relative_to(second).as_posix(): p.read_bytes()
                       for p in second.rglob("*") if p.is_file()}
        self.assertEqual(first_rows, second_rows)

    def test_atomic_publish_requires_new_destination(self):
        with self.assertRaises(FileExistsError):
            export_pack(self.project, self.pack)

    def test_one_byte_artifact_mutation_is_rejected(self):
        pack = self._copy("mut-byte")
        path = pack / "static_looks.json"
        data = bytearray(path.read_bytes()); data[len(data) // 2] ^= 1; path.write_bytes(data)
        self.assertRejected(pack)

    def test_missing_extra_case_and_symlink_artifacts_are_rejected(self):
        missing = self._copy("mut-missing"); (missing / "fixture_profile.json").unlink(); self.assertRejected(missing)
        extra = self._copy("mut-extra"); (extra / "extra.json").write_text("{}\n"); self.assertRejected(extra)
        case = self._copy("mut-case")
        with mock.patch.object(verifier_module.os, "walk",
                               return_value=[(str(case), [], ["manifest.json", "Manifest.json"])]):
            with self.assertRaisesRegex(SoundSwitchPackVerificationError, "case-colliding"):
                verifier_module._regular_files(case)
        link = self._copy("mut-link"); os.symlink(link / "manifest.json", link / "linked.json"); self.assertRejected(link)

    def test_noncanonical_json_and_timeline_order_are_rejected(self):
        pack = self._copy("mut-noncanonical")
        path = pack / "fixture_profile.json"; value = json.loads(path.read_text())
        data = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"; path.write_bytes(data)
        manifest = json.loads((pack / "manifest.json").read_text())
        row = next(r for r in manifest["artifact_hashes"] if r["path"] == "fixture_profile.json")
        row["size"] = len(data); row["sha256"] = _sha(data)
        (pack / "manifest.json").write_bytes(_canonical(manifest)); self.assertRejected(pack)

        order = self._copy("mut-order")
        relative = next(p.relative_to(order).as_posix() for p in (order / "autoloops").glob("*.json")
                        if len(json.loads(p.read_text())["document"]["timeline"]) > 1)
        self._semantic_mutation(order, relative,
                                lambda v: v["document"]["timeline"].__setitem__(slice(0, 2),
                                    list(reversed(v["document"]["timeline"][:2]))))
        self.assertRejected(order)

    def test_count_uuid_union_profile_source_and_active_semantics_are_rejected(self):
        cases = []
        count = self._copy("mut-count")
        self._semantic_mutation(count, "venue_cues.json", lambda v: v.__setitem__("render_cue_count", 231)); cases.append(count)
        uuid = self._copy("mut-uuid"); manifest = json.loads((uuid / "manifest.json").read_text())
        manifest["project"]["project_uuid"] = "{E34F6DCD-EBB9-4088-BD28-7BC0272D011A}"
        (uuid / "manifest.json").write_bytes(_canonical(manifest)); cases.append(uuid)
        union = self._copy("mut-union"); manifest = json.loads((union / "manifest.json").read_text())
        manifest["active_cue_union"]["sha256"] = "0" * 64
        (union / "manifest.json").write_bytes(_canonical(manifest)); cases.append(union)
        profile = self._copy("mut-profile")
        self._semantic_mutation(profile, "fixture_profile.json",
                                lambda v: v.__setitem__("fixture_profile_guid", "0" * 32)); cases.append(profile)
        source = self._copy("mut-source")
        relative = next(p.relative_to(source).as_posix() for p in (source / "autoloops").glob("*.json"))
        self._semantic_mutation(source, relative,
                                lambda v: v["document"].__setitem__("source_sha256", "0" * 64)); cases.append(source)
        semantic = self._copy("mut-semantic")
        def make_cc(value):
            row = next(r for r in value["learned_controls"] if r["active"] and r["target_kind"] == "static_look")
            row["message_type"] = "control_change"
        self._semantic_mutation(semantic, "selection_map.json", make_cc); cases.append(semantic)
        for pack in cases:
            with self.subTest(pack=pack.name): self.assertRejected(pack)

    def test_semantically_mutated_prerendered_frames_are_rejected_after_rehash(self):
        boundary = self._copy("mut-boundary-frame")
        relative = next(p.relative_to(boundary).as_posix() for p in (boundary / "autoloops").glob("*.json")
                        if json.loads(p.read_text())["document"]["pre_rendered_boundaries"])
        def mutate_boundary(value):
            frame = value["document"]["pre_rendered_boundaries"][0]["frame"]
            frame[0] = (frame[0] + 1) % 256
        self._semantic_mutation(boundary, relative, mutate_boundary)
        self.assertRejected(boundary)

        static = self._copy("mut-static-frame")
        def mutate_static(value):
            frame = value["records"][8]["pre_rendered_frame_ch1_ch19"]
            frame[0] = (frame[0] + 1) % 256
        self._semantic_mutation(static, "static_looks.json", mutate_static)
        self.assertRejected(static)

    def test_midi_registry_removal_binding_mutation_and_crosswalk_classification_are_rejected(self):
        empty = self._copy("mut-midi-empty")
        self._semantic_mutation(empty, "midi_mappings.json", lambda value: value.__setitem__("maps", []))
        self.assertRejected(empty)

        binding = self._copy("mut-midi-binding")
        def mutate_binding(value):
            value["maps"][0]["devices"][0]["collections"][0]["bindings"][0]["data_byte"] -= 1
        self._semantic_mutation(binding, "midi_mappings.json", mutate_binding)
        self.assertRejected(binding)

        crosswalk = self._copy("mut-f3-classification")
        def mutate_classification(value):
            row = next(item for item in value["learned_controls"]
                       if item["control_classification"] == "static_override")
            row["control_classification"] = "pack_selection"
        self._semantic_mutation(crosswalk, "selection_map.json", mutate_classification)
        self.assertRejected(crosswalk)

    def test_midi_registry_rejects_parent_mismatch_raw_type_and_retained_field_mutations(self):
        mutations = {
            "child-device": lambda b: b.__setitem__("device_name", "wrong-device"),
            "child-collection": lambda b: b.__setitem__("collection_id", 99),
            "raw-type": lambda b: b.__setitem__("message_type_raw", "0"),
            "enabled-type": lambda b: b.__setitem__("enabled", 1),
            "unknown-field": lambda b: b.__setitem__("invented", 1),
            "missing-field": lambda b: b.pop("control_path"),
            "source-offset": lambda b: b.__setitem__("source_offset", -1),
        }
        for name, mutate in mutations.items():
            pack = self._copy(f"mut-midi-{name}")
            def apply(value, operation=mutate):
                operation(value["maps"][0]["devices"][0]["collections"][0]["bindings"][0])
            self._semantic_mutation(pack, "midi_mappings.json", apply)
            with self.subTest(name=name):
                self.assertRejected(pack)

    def test_verifier_rejects_source_project_drift(self):
        empty = self.root / "different-source"; empty.mkdir()
        with self.assertRaisesRegex(SoundSwitchPackVerificationError, "source project drift"):
            verify_pack(self.pack, source_project=empty)

    def test_pack_contains_no_absolute_source_or_audio_path(self):
        home = str(Path.home()).encode()
        for path in self.pack.rglob("*.json"):
            self.assertNotIn(home, path.read_bytes(), path)


if __name__ == "__main__":
    unittest.main()
