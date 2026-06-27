"""Task 2 tests for canonical SoundSwitch pack export and verification."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack import (
    BRIDGE_SCENES,
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
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    SoundSwitchPackLoadError, load_pack,
)
from rb_ss_bridge_v2 import soundswitch_pack_verifier as verifier_module
from rb_ss_bridge_v2.tools.export_soundswitch_pack import (
    ExportAlreadyRunningError, export_pack, publish_pack,
)
from rb_ss_bridge_v2.tools import export_soundswitch_pack as export_module
from rb_ss_bridge_v2.soundswitch_project_decoder import SoundSwitchDecodeError


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

    def test_render_static_look_ignores_out_of_range_dmx_channel(self):
        look = StaticLook(0, 1, 0, 5, "x", (), (), (), (), (
            CueAttribute(0, 0x493, 82, 0, 99),))
        frame = render_static_look_frame(look)
        self.assertEqual(frame, tuple([0]*19), "dmx_channel=0 corrupted CH19 via frame[-1]")
        look20 = StaticLook(0, 1, 0, 5, "x", (), (), (), (), (
            CueAttribute(0, 0x493, 82, 20, 5),))
        render_static_look_frame(look20)  # must not raise IndexError

        cue = AttributeCue(1, 2, "fixture_payload", "a", "a" * 32, "p",
                           (CueAttribute(1, 0x493, 82, 0, 77),))
        doc = LightingDocument("SSAutoLoop1.ssfile", "0" * 64, 1, 3, "p", "x", 1, (), (
            TimelineRecord(100, 1, -1, 1, "cue", 0, cue.cue_guid),), (), 1,
            b"0123456789", "1" * 64, None)
        self.assertEqual(render_document_boundaries(doc, {cue.cue_guid: cue})[0]["frame"],
                         [0] * 19)

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
        self._write_json_artifact(pack, relative, value)

    def _write_json_artifact(self, pack: Path, relative: str, value) -> None:
        path = pack / relative
        data = _canonical(value)
        path.write_bytes(data)
        manifest_path = pack / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        row = next(item for item in manifest["artifact_hashes"] if item["path"] == relative)
        row["size"] = len(data); row["sha256"] = _sha(data)
        manifest_path.write_bytes(_canonical(manifest))

    def _mutate_manifest(self, pack: Path, mutate) -> None:
        manifest_path = pack / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        mutate(manifest)
        manifest_path.write_bytes(_canonical(manifest))

    def _active_union(self, pack: Path) -> tuple[int, str]:
        selection = json.loads((pack / "selection_map.json").read_text())
        track = json.loads((pack / "track_map.json").read_text())
        active_loops = {row["target_identity"] for row in selection["iac_selections"]
                        if row.get("active") and row.get("target_kind") == "autoloop"}
        active_scripts = {row["relative_path"] for row in track["scripted_inventory"]
                          if row.get("active_existing_path")}
        refs: set[str] = set()
        for path in (pack / "autoloops").glob("*.json"):
            document = json.loads(path.read_text())["document"]
            if document["relative_path"] in active_loops:
                refs.update(row["resolved_cue_guid"].lower() for row in document["timeline"]
                            if row.get("resolved_cue_guid"))
        for path in (pack / "scripted").glob("*.json"):
            document = json.loads(path.read_text()).get("document")
            if isinstance(document, dict) and document["relative_path"] in active_scripts:
                refs.update(row["resolved_cue_guid"].lower() for row in document["timeline"]
                            if row.get("resolved_cue_guid"))
        union = sorted(refs)
        return len(union), hashlib.sha256("\n".join(union).encode("ascii")).hexdigest()

    @staticmethod
    def _selection_classification(row: dict) -> str:
        if not row.get("active") or row.get("target_kind") == "non_render":
            return "inactive_report_only"
        if row.get("device_name") == "IAC Driver Bus 1" \
                and row.get("channel_zero_based") == 0 \
                and row.get("data_byte") == 0 \
                and row.get("message_type") == "note":
            return "blackout_mask"
        if row.get("target_kind") == "static_look":
            return "static_override"
        return "pack_selection"

    def _refresh_selection_map(self, selection: dict) -> None:
        controls = selection["learned_controls"]
        for row in controls:
            row["control_classification"] = self._selection_classification(row)
        controls.sort(key=lambda row: (row["device_name"], row["channel_zero_based"],
                                       row["data_byte"], row["control_path"],
                                       row["source_offset"]))
        event_targets = {}
        for row in controls:
            if row["active"] and row["device_name"] == "IAC Driver Bus 1" \
                    and row["message_type"] == "note":
                event_targets[(row["device_name"], row["channel_zero_based"],
                               row["data_byte"])] = row
        scenes = []
        for name, channel, note in BRIDGE_SCENES:
            target = event_targets.get(("IAC Driver Bus 1", channel, note))
            if name == "house_post_drop_1":
                classification = "inactive_report_only"
            elif target:
                classification = "pack_selection"
            elif channel == 1 and note in (0, 1, 2):
                classification = "bridge_owned_safety"
            else:
                classification = "no_project_target"
            scenes.append({
                "channel_zero_based": channel,
                "control_classification": classification,
                "data_byte": note,
                "policy_name": name,
                "resolution": "project_target" if target else "no_project_target",
                "target_identity": target["target_identity"] if target else None,
                "target_kind": target["target_kind"] if target else None,
            })
        blackout = event_targets.get(("IAC Driver Bus 1", 0, 0))
        selection["bridge_scenes"] = scenes
        selection["manual_blackout"] = {
            "channel_zero_based": 0,
            "control_classification": "blackout_mask",
            "data_byte": 0,
            "resolution": "project_target" if blackout else "no_project_target",
            "target_identity": blackout["target_identity"] if blackout else None,
        }
        selection["iac_selections"] = [
            row for row in controls if row["active"]
            and row["device_name"] == "IAC Driver Bus 1"
            and row["target_kind"] == "autoloop"
        ]
        selection["ddj_static_overrides"] = [
            row for row in controls if row["active"]
            and row["device_name"] == "DDJ-800"
            and row["target_kind"] == "static_look"
        ]

    def _update_midi_binding(self, pack: Path, control_path: str, **fields) -> None:
        registry = json.loads((pack / "midi_mappings.json").read_text())
        found = False
        for mapping in registry["maps"]:
            for device in mapping["devices"]:
                for collection in device["collections"]:
                    for binding in collection["bindings"]:
                        if binding["control_path"] == control_path:
                            binding.update(fields)
                            found = True
        if not found:
            self.fail(f"binding not found: {control_path}")
        self._write_json_artifact(pack, "midi_mappings.json", registry)

    def _move_midi_binding_device(self, pack: Path, control_path: str, new_device: str) -> None:
        registry = json.loads((pack / "midi_mappings.json").read_text())
        moved = None
        feedback_hex = ""
        for mapping in registry["maps"]:
            for device in mapping["devices"]:
                for collection in device["collections"]:
                    for index, binding in enumerate(list(collection["bindings"])):
                        if binding["control_path"] == control_path:
                            moved = dict(binding)
                            feedback_hex = device["feedback_hex"]
                            del collection["bindings"][index]
                            break
                    if moved is not None:
                        break
                if moved is not None:
                    break
            if moved is not None:
                moved["device_name"] = new_device
                target = next((device for device in mapping["devices"]
                               if device["name"] == new_device), None)
                if target is None:
                    target = {"name": new_device, "feedback_hex": feedback_hex,
                              "collections": []}
                    mapping["devices"].append(target)
                collection = next((row for row in target["collections"]
                                   if row["collection_id"] == moved["collection_id"]), None)
                if collection is None:
                    collection = {"collection_id": moved["collection_id"], "bindings": []}
                    target["collections"].append(collection)
                collection["bindings"].append(moved)
                collection["bindings"].sort(key=lambda row: row["source_offset"])
                target["collections"].sort(key=lambda row: row["collection_id"])
                mapping["devices"].sort(key=lambda row: row["name"])
                break
        if moved is None:
            self.fail(f"binding not found: {control_path}")
        self._write_json_artifact(pack, "midi_mappings.json", registry)

    def _recompute_manifest_runtime_totals(self, pack: Path) -> None:
        selection = json.loads((pack / "selection_map.json").read_text())
        count, sha = self._active_union(pack)
        self._mutate_manifest(pack, lambda manifest: (
            manifest.__setitem__("active_cue_union", {"count": count, "sha256": sha}),
            manifest["totals"].__setitem__("active_cue_union", count),
            manifest["totals"].__setitem__("iac_autoloop_bindings",
                                           len(selection["iac_selections"])),
            manifest["totals"].__setitem__("ddj_static_overrides",
                                           len(selection["ddj_static_overrides"])),
        ))

    def assertRejected(self, pack: Path):
        with self.assertRaises(SoundSwitchPackVerificationError):
            verify_pack(pack)

    def assertVerifierAndLoaderRejected(self, pack: Path, message: str):
        with self.assertRaisesRegex(SoundSwitchPackVerificationError, message):
            verify_pack(pack)
        with self.assertRaises(SoundSwitchPackLoadError) as raised:
            load_pack(pack)
        self.assertIsInstance(raised.exception.__cause__, SoundSwitchPackVerificationError)

    def test_current_totals_crosswalk_and_catalog_tail(self):
        result = verify_pack(self.pack, source_project=self.project)
        self.assertTrue(result["verified"])
        manifest = json.loads((self.pack / "manifest.json").read_text())
        venue = json.loads((self.pack / "venue_cues.json").read_text())
        render = [row for row in venue["records"] if row["record_kind"] == "fixture_payload"]
        tails = [row for row in venue["records"]
                 if row["record_kind"] == "minimal_default_catalog_tail"]
        self.assertEqual(manifest["totals"]["total_venue_records"], len(venue["records"]))
        self.assertEqual(manifest["totals"]["render_cues"], len(render))
        self.assertEqual(manifest["totals"]["catalog_tail_records"], len(tails))
        self.assertEqual(manifest["totals"]["static_looks"], 32)
        self.assertEqual(
            manifest["totals"]["total_autoloops"],
            len(list((self.pack / "autoloops").glob("*.json"))),
        )
        track = json.loads((self.pack / "track_map.json").read_text())
        self.assertEqual(manifest["totals"]["scripted_inventory"],
                         len(track["scripted_inventory"]))
        self.assertEqual(
            manifest["totals"]["parsed_scripted"],
            sum(1 for path in (self.pack / "scripted").glob("*.json")
                if json.loads(path.read_text()).get("document") is not None),
        )
        union_count, union_sha = self._active_union(self.pack)
        self.assertEqual(manifest["active_cue_union"],
                         {"count": union_count, "sha256": union_sha})
        selection = json.loads((self.pack / "selection_map.json").read_text())
        self.assertTrue(any(row["resolution"] == "no_project_target"
                            for row in selection["bridge_scenes"]))
        self.assertEqual(sorted(row["target_index"] for row in selection["learned_controls"]
                                if row["active"] and row["target_kind"] == "static_look"
                                and row["device_name"] == "DDJ-800"),
                         [8, 16, 17, 24])
        self.assertEqual(set(selection["classification_policy"]), {
            "pack_selection", "static_override", "blackout_mask", "bridge_owned_safety",
            "no_project_target", "inactive_report_only", "unsupported_fail_export"})
        self.assertEqual(selection["manual_blackout"]["control_classification"], "blackout_mask")
        blackout_controls = [row for row in selection["learned_controls"]
                             if row["active"]
                             and row["device_name"] == "IAC Driver Bus 1"
                             and row["channel_zero_based"] == 0
                             and row["data_byte"] == 0]
        self.assertEqual([row["control_classification"] for row in blackout_controls],
                         ["blackout_mask"])
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
                     if row["target_kind"] == "static_look" and row["active"]
                     and row["control_classification"] == "static_override"]
        self.assertTrue(all(row["control_classification"] == "static_override" for row in overrides))
        self.assertEqual(
            {row["target_index"]: row["interaction_mode"] for row in overrides},
            {8: "press", 16: "press", 17: "press", 24: "press"},
        )
        self.assertFalse(any("interaction_mode" in row for row in selection["learned_controls"]
                             if row["target_kind"] != "static_look"))

    def test_import_report_surfaces_runtime_reclassifications_without_source_paths(self):
        result = verify_pack(self.pack, source_project=self.project)
        self.assertTrue(result["verified"])
        report = json.loads((self.pack / "import_report.json").read_text())
        track = json.loads((self.pack / "track_map.json").read_text())
        selection = json.loads((self.pack / "selection_map.json").read_text())
        self.assertEqual(
            report["scripted_deactivated_missing_file"],
            sorted(row["relative_path"] for row in track["scripted_inventory"]
                   if row["status"] == "supported_mapped_primary"
                   and not row["active_existing_path"]),
        )
        expected_reserved = sorted(
            ({
                "control_path": row["control_path"],
                "note": "treated as momentary blackout, not a static look",
                "target_index": row["target_index"],
            } for row in selection["learned_controls"]
             if row["control_classification"] == "blackout_mask"
             and row["target_kind"] == "static_look"),
            key=lambda row: (row["control_path"], row["target_index"] or -1),
        )
        self.assertEqual(report["reserved_event_reclassifications"], expected_reserved)
        self.assertFalse(any("target_identity" in row or "relative_path" in row
                             for row in report["reserved_event_reclassifications"]))

    def test_dynamic_verifier_accepts_extra_unused_venue_cue_but_strict_proof_rejects(self):
        pack = self._copy("dynamic-extra-venue-cue")
        venue = json.loads((pack / "venue_cues.json").read_text())
        used = {row["cue_guid"] for row in venue["records"]}
        guid = next(f"{index:032x}" for index in range(1, 1000) if f"{index:032x}" not in used)
        source_offset = max(row["source_offset"] for row in venue["records"]) + 1
        row = json.loads(json.dumps(next(item for item in venue["records"]
                                         if item["record_kind"] == "fixture_payload")))
        row["cue_guid"] = guid
        row["name"] = "unused saved edit"
        row["source_offset"] = source_offset
        row["end_offset"] = source_offset + 1
        venue["records"].append(row)
        venue["records"].sort(key=lambda item: item["source_offset"])
        venue["render_cue_count"] += 1
        venue["total_record_count"] += 1
        self._write_json_artifact(pack, "venue_cues.json", venue)
        self._mutate_manifest(pack, lambda manifest: (
            manifest["totals"].__setitem__("render_cues", venue["render_cue_count"]),
            manifest["totals"].__setitem__("total_venue_records", venue["total_record_count"]),
        ))

        self.assertTrue(verify_pack(pack)["verified"])

    def test_dynamic_verifier_accepts_inactive_scripted_row_with_recomputed_union(self):
        pack = self._copy("dynamic-inactive-script")
        track = json.loads((pack / "track_map.json").read_text())
        row = next(item for item in track["scripted_inventory"]
                   if item["active_existing_path"])
        row["active_existing_path"] = False
        self._write_json_artifact(pack, "track_map.json", track)
        count, sha = self._active_union(pack)
        self._mutate_manifest(pack, lambda manifest: (
            manifest.__setitem__("active_cue_union", {"count": count, "sha256": sha}),
            manifest["totals"].__setitem__("active_existing_path_scripted",
                                           manifest["totals"]["active_existing_path_scripted"] - 1),
            manifest["totals"].__setitem__("active_cue_union", count),
        ))

        self.assertTrue(verify_pack(pack)["verified"])

    def test_dynamic_verifier_accepts_removed_unreferenced_autoloop_artifact(self):
        pack = self._copy("dynamic-removed-autoloop")
        selection = json.loads((pack / "selection_map.json").read_text())
        referenced = {row["target_identity"] for row in selection["iac_selections"]
                      if row.get("active") and row.get("target_kind") == "autoloop"}
        referenced.update(row["target_identity"] for row in selection["bridge_scenes"]
                          if row.get("resolution") == "project_target")
        if selection["manual_blackout"].get("target_identity"):
            referenced.add(selection["manual_blackout"]["target_identity"])
        removable = None
        for path in sorted((pack / "autoloops").glob("*.json")):
            document = json.loads(path.read_text())["document"]
            if document["relative_path"] not in referenced:
                removable = path
                break
        if removable is None:
            self.skipTest("no unreferenced autoloop artifact in the current saved project")
        relative = removable.relative_to(pack).as_posix()
        removable.unlink()
        self._mutate_manifest(pack, lambda manifest: (
            manifest.__setitem__(
                "artifact_hashes",
                [row for row in manifest["artifact_hashes"] if row["path"] != relative],
            ),
            manifest["totals"].__setitem__("total_autoloops",
                                           manifest["totals"]["total_autoloops"] - 1),
        ))

        self.assertTrue(verify_pack(pack)["verified"])

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

    def test_publish_pack_first_replace_and_repeat_match_fresh_export(self):
        destination = self.root / "published"
        first = publish_pack(self.project, destination)
        self.assertTrue(first["first_export"])
        self.assertEqual(self._copy_bytes(destination), self._copy_bytes(self.pack))

        (destination / "obsolete.json").write_bytes(b"obsolete\n")
        second = publish_pack(self.project, destination)
        self.assertFalse(second["first_export"])
        self.assertEqual(self._copy_bytes(destination), self._copy_bytes(self.pack))

        before = self._copy_bytes(destination)
        publish_pack(self.project, destination)
        self.assertEqual(self._copy_bytes(destination), before)

    def test_publish_verify_failure_preserves_loadable_pack_byte_identical(self):
        destination = self._copy("publish-verify-failure")
        before = self._copy_bytes(destination)
        with mock.patch.object(
            export_module, "verify_pack",
            side_effect=SoundSwitchPackVerificationError("synthetic verification failure"),
        ):
            with self.assertRaises(SoundSwitchPackVerificationError):
                publish_pack(self.project, destination)
        self.assertEqual(self._copy_bytes(destination), before)
        load_pack(destination)
        self.assertEqual(list(self.root.glob(".publish-verify-failure.tmp-*")), [])
        self.assertEqual(list(self.root.glob(".publish-verify-failure.bak-*")), [])

    def test_loader_expands_canonical_tilde_path(self):
        home = self.root / "home"
        home.mkdir()
        shutil.copytree(self.pack, home / "canonical-pack")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            loaded = load_pack("~/canonical-pack")
        self.assertEqual(loaded.manifest_sha256, verify_pack(self.pack)["manifest_sha256"])

    def test_one_byte_artifact_mutation_is_rejected(self):
        pack = self._copy("mut-byte")
        path = pack / "static_looks.json"
        data = bytearray(path.read_bytes()); data[len(data) // 2] ^= 1; path.write_bytes(data)
        self.assertRejected(pack)

    @staticmethod
    def _copy_bytes(directory: Path) -> dict[str, bytes]:
        return {path.relative_to(directory).as_posix(): path.read_bytes()
                for path in directory.rglob("*") if path.is_file()}

    def test_one_byte_artifact_mutation_is_rejected_by_the_runtime_loader(self):
        # A corrupted pack must never load into the bridge: load_pack runs the
        # verifier first and surfaces the rejection as a load error.
        pack = self._copy("mut-byte-loader")
        path = pack / "static_looks.json"
        data = bytearray(path.read_bytes()); data[len(data) // 2] ^= 1; path.write_bytes(data)
        with self.assertRaises(SoundSwitchPackLoadError) as raised:
            load_pack(pack)
        self.assertIsInstance(raised.exception.__cause__, SoundSwitchPackVerificationError)

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
        missing_mode = self._copy("mut-missing-static-mode")
        def remove_mode(value):
            row = next(r for r in value["learned_controls"] if r["active"] and r["target_kind"] == "static_look")
            del row["interaction_mode"]
        self._semantic_mutation(missing_mode, "selection_map.json", remove_mode); cases.append(missing_mode)
        bad_mode = self._copy("mut-bad-static-mode")
        def corrupt_mode(value):
            row = next(r for r in value["learned_controls"] if r["active"] and r["target_kind"] == "static_look")
            row["interaction_mode"] = "momentary"
        self._semantic_mutation(bad_mode, "selection_map.json", corrupt_mode); cases.append(bad_mode)
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

    def test_catalog_tail_guid_collision_is_rejected_after_canonical_rehash(self):
        pack = self._copy("mut-catalog-tail-guid-collision")
        def collide_with_render_cue(value):
            render_guid = next(row["cue_guid"] for row in value["records"]
                               if row["record_kind"] == "fixture_payload")
            tail = next(row for row in value["records"]
                        if row["record_kind"] == "minimal_default_catalog_tail")
            tail["cue_guid"] = render_guid
        self._semantic_mutation(pack, "venue_cues.json", collide_with_render_cue)
        with self.assertRaisesRegex(SoundSwitchPackVerificationError, "globally unique"):
            verify_pack(pack)

    def test_active_script_reclassification_is_rejected_after_canonical_rehash(self):
        track = json.loads((self.pack / "track_map.json").read_text())
        active = next(row for row in track["scripted_inventory"]
                      if row["active_existing_path"])
        relative = f"scripted/{active['soundswitch_id'].lower()}.json"
        pack = self._copy("mut-active-script-reclassified")
        self._semantic_mutation(
            pack, relative,
            lambda value: value["classification"].__setitem__(
                "status", "unsupported_inactive_layout"))
        with self.assertRaisesRegex(SoundSwitchPackVerificationError,
                                    "does not reconcile to active inventory"):
            verify_pack(pack)

        coordinated = self._copy("mut-active-script-inventory-and-artifact")
        def deactivate_inventory(value):
            row = next(item for item in value["scripted_inventory"]
                       if item["soundswitch_id"] == active["soundswitch_id"])
            row["status"] = "unsupported_inactive_layout"
        self._semantic_mutation(coordinated, "track_map.json", deactivate_inventory)
        self._semantic_mutation(
            coordinated, relative,
            lambda value: value["classification"].__setitem__(
                "status", "unsupported_inactive_layout"))
        with self.assertRaisesRegex(SoundSwitchPackVerificationError,
                                    "unsupported or non-renderable"):
            verify_pack(coordinated)

    def test_malformed_semantic_rows_and_document_are_typed_rejections_after_rehash(self):
        venue = self._copy("mut-malformed-venue-row")
        self._semantic_mutation(
            venue, "venue_cues.json",
            lambda value: value["records"].__setitem__(0, "bad"))
        self.assertVerifierAndLoaderRejected(venue, "Venue cue records")

        static = self._copy("mut-malformed-static-row")
        self._semantic_mutation(
            static, "static_looks.json",
            lambda value: value["records"].__setitem__(0, "bad"))
        self.assertVerifierAndLoaderRejected(static, "Static Look records")

        inventory = self._copy("mut-malformed-scripted-inventory-row")
        self._semantic_mutation(
            inventory, "track_map.json",
            lambda value: value["scripted_inventory"].__setitem__(0, "bad"))
        self.assertVerifierAndLoaderRejected(inventory, "scripted inventory")

        autoloop = self._copy("mut-malformed-autoloop-document")
        self._semantic_mutation(
            autoloop, "autoloops/1.json",
            lambda value: value.__setitem__("document", []))
        self.assertVerifierAndLoaderRejected(autoloop, "SSAutoLoop1.ssfile")

    def test_boolean_cue_attribute_integer_fields_are_rejected_after_rehash(self):
        for field in ("dmx_channel", "channel_id"):
            pack = self._copy(f"mut-boolean-cue-{field}")
            def mutate(value, key=field):
                render = next(row for row in value["records"]
                              if row["record_kind"] == "fixture_payload")
                render["attributes"][0][key] = True
            self._semantic_mutation(pack, "venue_cues.json", mutate)
            with self.subTest(field=field):
                self.assertVerifierAndLoaderRejected(pack, "invalid/duplicate cue attribute")

    def test_loader_primitive_schema_parity_rejects_canonical_rehash_mutations(self):
        def timeline_field(field, replacement):
            def mutate(value):
                value["document"]["timeline"][0][field] = replacement
            return mutate

        def boundary_field(field, replacement):
            def mutate(value):
                value["document"]["pre_rendered_boundaries"][0][field] = replacement
            return mutate

        def intensity_field(field, replacement):
            def mutate(value):
                value["document"]["intensity_nodes"][0][field] = replacement
            return mutate

        def static_field(field, replacement, *, index=0):
            def mutate(value):
                value["records"][index][field] = replacement
            return mutate

        def retained_field(collection, field, replacement):
            def mutate(value):
                row = next(item for item in value["records"] if item[collection])
                row[collection][0][field] = replacement
            return mutate

        def add_timeline_field(value):
            value["document"]["timeline"][0]["invented"] = 1

        cases = (
            ("timeline-raw-bool", "autoloops/1.json", timeline_field("raw_reference", True),
             "timeline primitive"),
            ("timeline-version-bool", "autoloops/1.json", timeline_field("record_version", True),
             "timeline primitive"),
            ("timeline-unknown-field", "autoloops/1.json", add_timeline_field,
             "timeline/boundary field"),
            ("boundary-order-bool", "autoloops/1.json", boundary_field("source_order", True),
             "boundary primitive"),
            ("intensity-offset-bool", "autoloops/1.json", intensity_field("source_offset", True),
             "intensity node"),
            ("static-slot-bool", "static_looks.json", static_field("slot_index", True, index=1),
             "Static Look"),
            ("static-version-bool", "static_looks.json", static_field("record_version", True),
             "Static Look"),
            ("static-frame-bool", "static_looks.json",
             lambda value: value["records"][8]["pre_rendered_frame_ch1_ch19"].__setitem__(0, True),
             "Static Look record"),
            ("static-scalar-bool", "static_looks.json",
             retained_field("intensity_values", "source_offset", True), "Static Look intensity"),
            ("static-colour-bool", "static_looks.json",
             retained_field("colour_values", "fixture_instance_id", True), "Static Look colour"),
            ("static-position-bool", "static_looks.json",
             retained_field("position_values", "source_offset", True), "Static Look position"),
        )
        for name, relative, mutate, message in cases:
            pack = self._copy(f"mut-loader-parity-{name}")
            self._semantic_mutation(pack, relative, mutate)
            with self.subTest(name=name):
                self.assertVerifierAndLoaderRejected(pack, message)

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

    def test_verifier_mirrors_loader_runtime_metadata_rejections(self):
        baseline = json.loads((self.pack / "selection_map.json").read_text())
        active_iac = [row for row in baseline["learned_controls"]
                      if row["active"] and row["device_name"] == "IAC Driver Bus 1"
                      and row["target_kind"] == "autoloop"]
        active_static = [row for row in baseline["learned_controls"]
                         if row["active"] and row["target_kind"] == "static_look"
                         and row["control_classification"] == "static_override"]
        if len(active_iac) < 2 or len(active_static) < 2:
            self.skipTest("current SoundSwitch project lacks enough active controls")

        duplicate_static = self._copy("mut-runtime-duplicate-static-slot")
        selection = json.loads((duplicate_static / "selection_map.json").read_text())
        statics = [row for row in selection["learned_controls"]
                   if row["active"] and row["control_classification"] == "static_override"]
        statics[1]["target_identity"] = statics[0]["target_identity"]
        statics[1]["target_index"] = statics[0]["target_index"]
        statics[1]["target_name"] = statics[0]["target_name"]
        self._refresh_selection_map(selection)
        self._write_json_artifact(duplicate_static, "selection_map.json", selection)
        self.assertVerifierAndLoaderRejected(
            duplicate_static, "duplicate active static_override slot ownership")

        duplicate_event = self._copy("mut-runtime-duplicate-event")
        selection = json.loads((duplicate_event / "selection_map.json").read_text())
        iac = [row for row in selection["learned_controls"]
               if row["active"] and row["device_name"] == "IAC Driver Bus 1"
               and row["target_kind"] == "autoloop"]
        iac[1]["channel_zero_based"] = iac[0]["channel_zero_based"]
        iac[1]["data_byte"] = iac[0]["data_byte"]
        self._update_midi_binding(
            duplicate_event, iac[1]["control_path"],
            channel_zero_based=iac[0]["channel_zero_based"],
            data_byte=iac[0]["data_byte"],
        )
        self._refresh_selection_map(selection)
        self._write_json_artifact(duplicate_event, "selection_map.json", selection)
        self.assertVerifierAndLoaderRejected(
            duplicate_event, "duplicate active learned controller event")

        reserved_scene = self._copy("mut-runtime-reserved-scene")
        selection = json.loads((reserved_scene / "selection_map.json").read_text())
        row = next(item for item in selection["learned_controls"]
                   if item["active"] and item["device_name"] == "IAC Driver Bus 1"
                   and item["target_kind"] == "autoloop")
        row["data_byte"] = 41
        self._update_midi_binding(reserved_scene, row["control_path"], data_byte=41)
        self._refresh_selection_map(selection)
        self._write_json_artifact(reserved_scene, "selection_map.json", selection)
        self.assertVerifierAndLoaderRejected(
            reserved_scene, "project-target bridge scene is not pack_selection")

        invalid_static = self._copy("mut-runtime-invalid-static-target")
        selection = json.loads((invalid_static / "selection_map.json").read_text())
        row = next(item for item in selection["learned_controls"]
                   if item["active"] and item["control_classification"] == "static_override")
        row["device_name"] = "OTHER Controller"
        row["target_identity"] = "SSStaticLook99"
        row["target_index"] = 99
        row["target_name"] = "slot 99"
        self._move_midi_binding_device(invalid_static, row["control_path"], "OTHER Controller")
        self._refresh_selection_map(selection)
        self._write_json_artifact(invalid_static, "selection_map.json", selection)
        self.assertVerifierAndLoaderRejected(
            invalid_static, "invalid static_override controller target")

        missing_autoloop = self._copy("mut-runtime-missing-autoloop")
        selection = json.loads((missing_autoloop / "selection_map.json").read_text())
        row = next(item for item in selection["learned_controls"]
                   if item["active"] and item["device_name"] == "IAC Driver Bus 1"
                   and item["target_kind"] == "autoloop")
        row["target_identity"] = "SSAutoLoop999999.ssfile"
        row["target_index"] = 999998
        row["target_name"] = "missing autoloop"
        self._refresh_selection_map(selection)
        self._write_json_artifact(missing_autoloop, "selection_map.json", selection)
        self._recompute_manifest_runtime_totals(missing_autoloop)
        self.assertVerifierAndLoaderRejected(
            missing_autoloop, "active IAC selection references a missing Autoloop")

        empty_crosswalk = self._copy("mut-runtime-empty-crosswalk")
        selection = json.loads((empty_crosswalk / "selection_map.json").read_text())
        disabled_paths = []
        for row in selection["learned_controls"]:
            if row["active"] and row["device_name"] == "IAC Driver Bus 1" \
                    and row["target_kind"] == "autoloop":
                row["active"] = False
                disabled_paths.append(row["control_path"])
        for control_path in disabled_paths:
            self._update_midi_binding(empty_crosswalk, control_path, enabled=False)
        self._refresh_selection_map(selection)
        self._write_json_artifact(empty_crosswalk, "selection_map.json", selection)
        self._recompute_manifest_runtime_totals(empty_crosswalk)
        self.assertVerifierAndLoaderRejected(
            empty_crosswalk, "bridge scene crosswalk has no project targets")

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


class ExportPackLaunchSafetyTests(unittest.TestCase):
    """export_pack() atomic-publish + rollback contract — the launch path.

    These exercise the dangerous paths directly: bad destinations are rejected
    BEFORE any work, and any failure after staging begins leaves NO destination
    and NO leftover staging dir (no partial/corrupt output ever published).
    """

    def _staging_leftovers(self, parent: Path) -> list:
        # Staging dirs are created as `.{dest.name}.tmp-XXXX` in the parent.
        return list(parent.glob(".pack.tmp-*"))

    def test_existing_destination_is_rejected_before_any_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            dest.mkdir()
            with self.assertRaises(FileExistsError):
                export_pack(root / "ignored.ssproj", dest)
            self.assertEqual(self._staging_leftovers(root), [])

    def test_dangling_symlink_destination_is_rejected_before_any_work(self):
        # A dangling symlink reports exists()==False; only the is_symlink()
        # guard catches it. Publishing onto it would corrupt the link target.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            dest.symlink_to(root / "absent_target")
            self.assertFalse(dest.exists())
            self.assertTrue(dest.is_symlink())
            with self.assertRaises(FileExistsError):
                export_pack(root / "ignored.ssproj", dest)
            self.assertEqual(self._staging_leftovers(root), [])

    def test_missing_parent_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "missing_subdir" / "pack"
            with self.assertRaises(ValueError):
                export_pack(Path(tmp) / "ignored.ssproj", dest)

    def test_file_as_parent_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent_file = Path(tmp) / "iamafile"
            parent_file.write_text("not a directory")
            dest = parent_file / "pack"
            with self.assertRaises(ValueError):
                export_pack(Path(tmp) / "ignored.ssproj", dest)

    def test_symlinked_parent_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_dir = root / "real"
            real_dir.mkdir()
            linked_parent = root / "linked"
            linked_parent.symlink_to(real_dir)
            dest = linked_parent / "pack"
            with self.assertRaises(ValueError):
                export_pack(root / "ignored.ssproj", dest)

    def test_missing_project_file_aborts_with_typed_error_and_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            with self.assertRaises(SoundSwitchDecodeError):
                export_pack(root / "does_not_exist.ssproj", dest)
            self.assertFalse(dest.exists())
            self.assertEqual(self._staging_leftovers(root), [])

    def test_generator_commit_failure_aborts_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            with mock.patch.object(export_module, "decode_project", return_value=object()), \
                 mock.patch.object(export_module, "_generator_commit",
                                   side_effect=RuntimeError("cannot determine generator git commit")):
                with self.assertRaises(RuntimeError):
                    export_pack(root / "ignored.ssproj", dest)
            self.assertFalse(dest.exists())
            self.assertEqual(self._staging_leftovers(root), [])

    def test_verification_failure_rolls_back_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            observed = {}

            def _verify_raises(staging, *args, **kwargs):
                # Prove the pack really was fully staged before the launch is
                # aborted — then fail verification (the publish gate).
                staging = Path(staging)
                observed["staging_existed"] = staging.is_dir()
                observed["artifact_written"] = (staging / "manifest.json").read_bytes()
                raise SoundSwitchPackVerificationError("synthetic verification failure")

            with mock.patch.object(export_module, "decode_project", return_value=object()), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value={"manifest.json": b"{}\n"}), \
                 mock.patch.object(export_module, "verify_pack", side_effect=_verify_raises):
                with self.assertRaises(SoundSwitchPackVerificationError):
                    export_pack(root / "ignored.ssproj", dest)

            self.assertTrue(observed.get("staging_existed"), "pack was never staged")
            self.assertEqual(observed.get("artifact_written"), b"{}\n")
            self.assertFalse(dest.exists(), "destination created despite verify failure")
            self.assertEqual(self._staging_leftovers(root), [], "staging left behind")

    def test_publish_failure_rolls_back_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            with mock.patch.object(export_module, "decode_project", return_value=object()), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value={"manifest.json": b"{}\n"}), \
                 mock.patch.object(export_module, "verify_pack",
                                   return_value={"manifest_sha256": "x", "artifact_count": 1}), \
                 mock.patch.object(export_module.os, "replace",
                                   side_effect=OSError("synthetic publish failure")):
                with self.assertRaises(OSError):
                    export_pack(root / "ignored.ssproj", dest)
            self.assertFalse(dest.exists(), "destination present after failed publish")
            self.assertEqual(self._staging_leftovers(root), [], "staging left behind")

    def test_export_pack_writes_sibling_binding_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            decoded = SimpleNamespace(resolved_controls=(
                SimpleNamespace(
                    binding=SimpleNamespace(
                        enabled=True, message_type="note", channel_zero_based=2,
                        data_byte=44, device_name="private-device",
                    ),
                    target_kind="static_look",
                    interaction_mode="press",
                    target_name="White",
                ),
            ))
            artifacts = {"manifest.json": b'{"keep":true}\n'}
            with mock.patch.object(export_module, "decode_project", return_value=decoded), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value=artifacts), \
                 mock.patch.object(
                     export_module, "verify_pack",
                     return_value={"verified": True, "manifest_sha256": "a" * 64,
                                   "artifact_count": len(artifacts)},
                 ):
                export_pack(root / "ignored.ssproj", dest)

            self.assertEqual((dest / "manifest.json").read_bytes(), artifacts["manifest.json"])
            self.assertFalse(any(dest.rglob("*midi_bindings.json")))
            self.assertEqual(
                json.loads(export_module._binding_sidecar_path(dest).read_text()),
                [{"channel": 2, "interaction": "press", "name": "White",
                  "note": 44, "target_kind": "static_look"}],
            )

    def test_export_pack_sidecar_failure_removes_new_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            decoded = SimpleNamespace(resolved_controls=())
            with mock.patch.object(export_module, "decode_project", return_value=decoded), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value={"manifest.json": b"{}\n"}), \
                 mock.patch.object(
                     export_module, "verify_pack",
                     return_value={"verified": True, "manifest_sha256": "a" * 64,
                                   "artifact_count": 1},
                 ), \
                 mock.patch.object(export_module, "_write_binding_sidecar",
                                   side_effect=OSError("disk full")):
                with self.assertRaises(export_module.BindingSidecarWriteError):
                    export_pack(root / "ignored.ssproj", dest)

            self.assertFalse(dest.exists())
            self.assertFalse(export_module._binding_sidecar_path(dest).exists())

    def test_artifact_write_failure_rolls_back_and_publishes_nothing(self):
        # A mid-write failure (e.g. disk error) must not leave a partial pack
        # nor reach the verify/publish gates.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            verify_called = {"value": False}

            def _verify_should_not_run(*args, **kwargs):
                verify_called["value"] = True
                return {"manifest_sha256": "x", "artifact_count": 1}

            # Second artifact is not bytes -> stream.write() raises TypeError mid-loop.
            artifacts = {"manifest.json": b"{}\n", "broken.json": "not-bytes"}
            with mock.patch.object(export_module, "decode_project", return_value=object()), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts", return_value=artifacts), \
                 mock.patch.object(export_module, "verify_pack", side_effect=_verify_should_not_run):
                with self.assertRaises(TypeError):
                    export_pack(root / "ignored.ssproj", dest)
            self.assertFalse(verify_called["value"], "verify ran despite a write failure")
            self.assertFalse(dest.exists())
            self.assertEqual(self._staging_leftovers(root), [])


class ExportDurabilityTests(unittest.TestCase):
    """export_pack() crash-durability: directory entries and the atomic rename
    must be fsync'd, not just file contents. Uses mocks so it runs on CI without
    the real (skip-gated) SoundSwitch project."""

    def test_fsync_dir_syncs_the_directory_fd(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(export_module.os, "fsync") as fsync:
                export_module._fsync_dir(Path(tmp))
            self.assertEqual(fsync.call_count, 1)

    def test_fsync_dir_is_best_effort_when_unsupported(self):
        # On platforms where opening a directory fd is unsupported (e.g. Windows)
        # the helper must degrade to a no-op, never raise.
        with mock.patch.object(export_module.os, "open", side_effect=OSError("no dir fd")):
            export_module._fsync_dir(Path("/nonexistent"))  # must not raise
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(export_module.os, "fsync", side_effect=OSError("fsync fail")):
                export_module._fsync_dir(Path(tmp))  # must not raise

    def test_export_fsyncs_staging_dirs_then_parent_after_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "pack"
            artifacts = {"manifest.json": b"{}\n", "sub/doc.json": b"[]\n"}
            calls: list[Path] = []
            real_replace = export_module.os.replace
            replaced_at = {"index": None}

            def spy_fsync_dir(path):
                calls.append(Path(path))

            def tracking_replace(src, dst):
                replaced_at["index"] = len(calls)
                return real_replace(src, dst)

            decoded = SimpleNamespace(resolved_controls=())
            with mock.patch.object(export_module, "decode_project", return_value=decoded), \
                 mock.patch.object(export_module, "compile_pack_artifacts", return_value=artifacts), \
                 mock.patch.object(export_module, "verify_pack", return_value={"manifest_sha256": "x", "artifact_count": 2}), \
                 mock.patch.object(export_module, "_fsync_dir", side_effect=spy_fsync_dir), \
                 mock.patch.object(export_module.os, "replace", side_effect=tracking_replace):
                export_pack(root / "ignored.ssproj", dest)

            # Parent dir fsync'd AFTER the rename (durable publish).
            self.assertIn(root, calls)
            self.assertIsNotNone(replaced_at["index"])
            self.assertEqual(calls[-1], root)
            self.assertGreater(len(calls), replaced_at["index"],
                               "parent dir must be fsync'd after os.replace")
            # Staging dirs fsync'd BEFORE the rename (durable dir entries).
            self.assertGreater(replaced_at["index"], 0,
                               "staging dirs must be fsync'd before os.replace")


class PublishPackReplaceTests(unittest.TestCase):
    def _patch_export(self, artifacts=None):
        artifacts = artifacts or {"manifest.json": b"{}\n", "old.json": b"old\n"}
        decoded = SimpleNamespace(resolved_controls=())
        return (
            mock.patch.object(export_module, "decode_project", return_value=decoded),
            mock.patch.object(export_module, "_generator_commit", return_value="0" * 40),
            mock.patch.object(export_module, "compile_pack_artifacts", return_value=artifacts),
            mock.patch.object(
                export_module, "verify_pack",
                return_value={"verified": True, "manifest_sha256": "a" * 64,
                              "artifact_count": len(artifacts)},
            ),
        )

    def _publish_mocked(self, root: Path, destination: Path, artifacts=None):
        patches = self._patch_export(artifacts)
        with patches[0], patches[1], patches[2], patches[3]:
            return publish_pack(root / "source.ssproj", destination)

    def _files(self, directory: Path) -> dict[str, bytes]:
        return {path.relative_to(directory).as_posix(): path.read_bytes()
                for path in directory.rglob("*") if path.is_file()}

    def _leftovers(self, root: Path) -> list[Path]:
        return list(root.glob(".pack.tmp-*")) + list(root.glob(".pack.bak-*"))

    def test_first_publish_matches_new_path_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            published = root / "pack"
            fresh = root / "fresh"
            patches = self._patch_export()
            with patches[0], patches[1], patches[2], patches[3]:
                result = publish_pack(root / "source.ssproj", published)
                export_pack(root / "source.ssproj", fresh)
            self.assertTrue(result["first_export"])
            self.assertEqual(self._files(published), self._files(fresh))

    def test_replace_nonempty_pack_removes_old_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            destination.mkdir()
            (destination / "obsolete.json").write_bytes(b"obsolete\n")
            new_artifacts = {"manifest.json": b"{}\n", "new.json": b"new\n"}
            result = self._publish_mocked(root, destination, new_artifacts)
            self.assertFalse(result["first_export"])
            self.assertEqual(self._files(destination), new_artifacts)
            self.assertEqual(self._leftovers(root), [])

    def test_same_source_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            self._publish_mocked(root, destination)
            before = self._files(destination)
            self._publish_mocked(root, destination)
            self.assertEqual(self._files(destination), before)

    def test_verify_failure_preserves_existing_pack_and_removes_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            destination.mkdir()
            (destination / "manifest.json").write_bytes(b"old\n")
            before = self._files(destination)
            patches = self._patch_export()
            with patches[0], patches[1], patches[2], \
                 mock.patch.object(export_module, "verify_pack",
                                   side_effect=SoundSwitchPackVerificationError("synthetic")):
                with self.assertRaises(SoundSwitchPackVerificationError):
                    publish_pack(root / "source.ssproj", destination)
            self.assertEqual(self._files(destination), before)
            self.assertEqual(self._leftovers(root), [])

    def test_fallback_second_rename_failure_restores_old_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            destination.mkdir()
            (destination / "manifest.json").write_bytes(b"old\n")
            before = self._files(destination)
            real_replace = os.replace
            replace_count = 0

            def fail_second_swap_rename(source, target):
                nonlocal replace_count
                replace_count += 1
                if replace_count == 2:
                    raise OSError("synthetic swap failure")
                return real_replace(source, target)

            patches = self._patch_export({"manifest.json": b"new\n"})
            with patches[0], patches[1], patches[2], patches[3], \
                 mock.patch.object(export_module, "_renamex_np_swap",
                                   side_effect=NotImplementedError), \
                 mock.patch.object(export_module.os, "replace",
                                   side_effect=fail_second_swap_rename):
                with self.assertRaises(OSError):
                    publish_pack(root / "source.ssproj", destination)
            self.assertEqual(self._files(destination), before)
            self.assertEqual(self._leftovers(root), [])

    def test_sidecar_failure_before_swap_preserves_prior_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            destination.mkdir()
            (destination / "manifest.json").write_bytes(b"old\n")
            before = self._files(destination)
            prior_sidecar = export_module._binding_sidecar_path(destination)
            prior_sidecar.write_bytes(b'[{"prior":true}]\n')
            patches = self._patch_export({"manifest.json": b"new\n"})
            with patches[0], patches[1], patches[2], patches[3], \
                 mock.patch.object(export_module, "_binding_sidecar_rows",
                                   side_effect=OSError("synthetic sidecar failure")):
                with self.assertRaises(export_module.BindingSidecarWriteError):
                    publish_pack(root / "source.ssproj", destination)
            # The required sidecar could not be produced, so the canonical pack and
            # its prior sidecar must be left exactly as they were (no half-publish).
            self.assertEqual(self._files(destination), before)
            self.assertEqual(prior_sidecar.read_bytes(), b'[{"prior":true}]\n')
            self.assertEqual(self._leftovers(root), [])

    def test_symlink_destination_and_invalid_parents_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            destination.symlink_to(root / "missing")
            with self.assertRaises(ValueError):
                publish_pack(root / "source.ssproj", destination)
            destination.unlink()
            destination.write_text("not a directory")
            with self.assertRaises(ValueError):
                publish_pack(root / "source.ssproj", destination)
            with self.assertRaises(ValueError):
                publish_pack(root / "source.ssproj", root / "missing-parent" / "pack")
            parent_file = root / "parent-file"
            parent_file.write_text("x")
            with self.assertRaises(ValueError):
                publish_pack(root / "source.ssproj", parent_file / "pack")
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent)
            with self.assertRaises(ValueError):
                publish_pack(root / "source.ssproj", linked_parent / "pack")

    def test_unavailable_renamex_uses_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            destination.mkdir()
            (destination / "manifest.json").write_bytes(b"old\n")
            with mock.patch.object(export_module, "_renamex_np_swap",
                                   side_effect=AttributeError("unavailable")):
                self._publish_mocked(root, destination, {"manifest.json": b"new\n"})
            self.assertEqual((destination / "manifest.json").read_bytes(), b"new\n")

    def test_orphan_backup_recovery_restores_newest_or_discards_when_dest_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / ".pack.bak-older"
            newer = root / ".pack.bak-newer"
            older.mkdir(); (older / "value").write_text("older")
            newer.mkdir(); (newer / "value").write_text("newer")
            os.utime(older, (1, 1)); os.utime(newer, (2, 2))
            export_module._recover_orphan_backup(root, "pack")
            self.assertEqual((root / "pack" / "value").read_text(), "newer")
            self.assertFalse(older.exists())

            backup = root / ".pack.bak-extra"
            backup.mkdir(); (backup / "value").write_text("backup")
            export_module._recover_orphan_backup(root, "pack")
            self.assertEqual((root / "pack" / "value").read_text(), "newer")
            self.assertFalse(backup.exists())

    def test_orphan_backup_is_retained_when_destination_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / ".pack.bak-valid"
            backup.mkdir()
            (backup / "manifest.json").write_bytes(b"old\n")
            destination = root / "pack"
            destination.symlink_to(root / "missing")
            with self.assertRaises(ValueError):
                export_module._recover_orphan_backup(root, "pack")
            self.assertTrue(backup.is_dir())

    def test_orphan_backup_never_promotes_symlink_or_file_to_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / ".pack.bak-real"; real.mkdir(); (real / "value").write_text("REAL")
            target = root / "evil"; target.mkdir(); (target / "x").write_text("evil")
            sym = root / ".pack.bak-zzz"; sym.symlink_to(target)
            os.utime(real, (1, 1)); os.utime(sym, (9, 9), follow_symlinks=False)
            destination = root / "pack"  # missing: simulates a crash mid-swap
            export_module._recover_orphan_backup(root, "pack")
            self.assertTrue(destination.is_dir() and not destination.is_symlink())
            self.assertEqual((destination / "value").read_text(), "REAL")
            self.assertFalse(sym.exists())            # stray symlink junk removed
            self.assertTrue(target.is_dir())          # its target untouched

    def test_orphan_backup_with_only_junk_leaves_destination_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stray_file = root / ".pack.bak-file"; stray_file.write_text("not a pack")
            target = root / "evil"; target.mkdir()
            stray_link = root / ".pack.bak-link"; stray_link.symlink_to(target)
            export_module._recover_orphan_backup(root, "pack")
            self.assertFalse((root / "pack").exists())   # never fabricated from junk
            self.assertFalse(stray_file.exists())
            self.assertFalse(stray_link.exists())

    def test_lock_rejects_concurrent_export_and_steals_stale_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with export_module._export_lock(root, "pack"):
                with self.assertRaises(ExportAlreadyRunningError):
                    with export_module._export_lock(root, "pack"):
                        pass

            lock = root / ".pack.export.lock"
            lock.write_text("999999999\n0\n")
            with export_module._export_lock(root, "pack"):
                self.assertTrue(lock.exists())
            self.assertFalse(lock.exists())

    def test_publish_garbage_collects_orphan_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orphan = root / ".pack.tmp-orphan"
            orphan.mkdir()
            (orphan / "partial.json").write_bytes(b"partial\n")
            self._publish_mocked(root, root / "pack")
            self.assertFalse(orphan.exists())

    def test_lock_write_failure_removes_owned_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(export_module.os, "write", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    with export_module._export_lock(root, "pack"):
                        pass
            self.assertFalse((root / ".pack.export.lock").exists())

    def test_publish_output_contains_no_absolute_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            self._publish_mocked(root, destination)
            home = str(Path.home()).encode()
            for path in destination.rglob("*"):
                if path.is_file():
                    self.assertNotIn(home, path.read_bytes(), path)

    def test_publish_writes_sibling_binding_sidecar_without_mutating_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "pack"
            artifacts = {"manifest.json": b'{"keep":true}\n'}
            decoded = SimpleNamespace(resolved_controls=(
                SimpleNamespace(
                    binding=SimpleNamespace(
                        enabled=True, message_type="note", channel_zero_based=2,
                        data_byte=40, device_name="private-device",
                    ),
                    target_kind="static_look",
                    interaction_mode="toggle",
                    target_name="Blue Chase",
                ),
                SimpleNamespace(
                    binding=SimpleNamespace(
                        enabled=True, message_type="cc", channel_zero_based=2,
                        data_byte=41, device_name="private-device",
                    ),
                    target_kind="static_look",
                    interaction_mode="press",
                    target_name="Ignored CC",
                ),
            ))
            with mock.patch.object(export_module, "decode_project", return_value=decoded), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value=artifacts), \
                 mock.patch.object(
                     export_module, "verify_pack",
                     return_value={"verified": True, "manifest_sha256": "a" * 64,
                                   "artifact_count": len(artifacts)},
                 ):
                publish_pack(root / "source.ssproj", destination)

            self.assertEqual(self._files(destination), artifacts)
            self.assertFalse(any(destination.rglob("*midi_bindings.json")))
            sidecar = export_module._binding_sidecar_path(destination)
            self.assertEqual(sidecar.parent, destination.parent)
            self.assertEqual(json.loads(sidecar.read_text(encoding="utf-8")), [{
                "channel": 2,
                "note": 40,
                "target_kind": "static_look",
                "interaction": "toggle",
                "name": "Blue Chase",
            }])
            self.assertNotIn("device_name", sidecar.read_text(encoding="utf-8"))


class PublishPackCliTests(unittest.TestCase):
    def test_canonical_cli_writes_sanitized_success_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "result.json"
            publish_result = {
                "verified": True,
                "manifest_sha256": "a" * 64,
                "artifact_count": 95,
                "first_export": False,
            }
            with mock.patch.object(export_module, "publish_pack", return_value=publish_result), \
                 mock.patch.object(export_module, "_write_source_sidecar"):
                return_code = export_module.main([
                    "--publish-canonical", "--result-json", str(result_path),
                ])
            self.assertEqual(return_code, 0)
            self.assertEqual(json.loads(result_path.read_text()), {
                "ok": True,
                "verdict": "published",
                "manifest_sha256": "a" * 64,
                "artifact_count": 95,
                "first_export": False,
                "error_category": "",
            })

    def test_canonical_publish_writes_sibling_source_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.ssproj"
            source.mkdir()
            (source / "project.ssfile").write_bytes(b"source bytes")
            destination = root / "pack"
            destination.mkdir()
            publish_result = {
                "verified": True,
                "manifest_sha256": "a" * 64,
                "artifact_count": 95,
                "first_export": False,
            }
            with mock.patch.object(export_module, "CANONICAL_SOURCE_PROJECT", source), \
                 mock.patch.object(export_module, "CANONICAL_PACK_DIR", destination), \
                 mock.patch.object(export_module, "publish_pack", return_value=publish_result), \
                 mock.patch.object(export_module, "_generator_commit", return_value="b" * 40):
                result = export_module._canonical_publish_result()

            self.assertTrue(result["ok"])
            sidecar = export_module._sidecar_path(destination)
            self.assertEqual(sidecar.parent, destination.parent)
            self.assertFalse(sidecar.is_relative_to(destination))
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(payload, {
                "source_fingerprint": export_module._source_content_fingerprint(source),
                "generator_commit": "b" * 40,
                "pack_manifest_sha256": "a" * 64,
                "ignored_paths": [],
            })
            self.assertFalse(any(destination.rglob("*.source.json")))
            self.assertNotIn(str(Path.home()), sidecar.read_text(encoding="utf-8"))

    def test_opaque_source_paths_keeps_recordable_dat_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "pack"
            destination.mkdir()
            (destination / "manifest.json").write_text(json.dumps({
                "source_inventory": [
                    {
                        "path": "SoundSwitchVenues.bin.backup",
                        "parse_status": "retained_opaque",
                    },
                    {
                        "path": "recordable/01bede4d8ea57b3b58574d71826dc1f5.dat",
                        "parse_status": "retained_opaque",
                    },
                    {
                        "path": "automation_presets/PRESET 1.sspreset",
                        "parse_status": "retained_opaque",
                    },
                    {"path": "project.ssfile", "parse_status": "parsed"},
                ],
            }), encoding="utf-8")

            self.assertEqual(export_module._opaque_source_paths(destination), frozenset({
                "SoundSwitchVenues.bin.backup",
                "automation_presets/PRESET 1.sspreset",
            }))

    def test_write_binding_sidecar_is_sibling_and_manifest_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "pack"
            destination.mkdir()
            manifest = destination / "manifest.json"
            manifest.write_text('{"manifest_sha256":"keep"}\n', encoding="utf-8")
            before = hashlib.sha256(manifest.read_bytes()).hexdigest()
            decoded = SimpleNamespace(resolved_controls=(
                SimpleNamespace(
                    binding=SimpleNamespace(
                        enabled=True, message_type="note", channel_zero_based=2,
                        data_byte=40, device_name="private-device",
                    ),
                    target_kind="static_look",
                    interaction_mode="toggle",
                    target_name="Blue Chase",
                ),
                SimpleNamespace(
                    binding=SimpleNamespace(
                        enabled=True, message_type="note", channel_zero_based=1,
                        data_byte=41, device_name="ignored-device",
                    ),
                    target_kind="autoloop",
                    interaction_mode=None,
                    target_name="Ignored",
                ),
            ))

            export_module._write_binding_sidecar(destination, decoded)

            sidecar = export_module._binding_sidecar_path(destination)
            self.assertEqual(sidecar.parent, destination.parent)
            self.assertFalse(sidecar.is_relative_to(destination))
            self.assertFalse(any(destination.rglob("*midi_bindings.json")))
            self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), before)
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(payload, [{
                "channel": 2,
                "note": 40,
                "target_kind": "static_look",
                "interaction": "toggle",
                "name": "Blue Chase",
            }])
            self.assertNotIn("device_name", sidecar.read_text(encoding="utf-8"))

    def test_canonical_publish_reuses_decoded_project_for_binding_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.ssproj"
            destination = root / "pack"
            decoded = SimpleNamespace(resolved_controls=(
                SimpleNamespace(
                    binding=SimpleNamespace(
                        enabled=True, message_type="note", channel_zero_based=2,
                        data_byte=40,
                    ),
                    target_kind="static_look",
                    interaction_mode="press",
                    target_name="Blue",
                ),
            ))
            artifacts = {"manifest.json": b"{}\n"}

            with mock.patch.object(export_module, "CANONICAL_SOURCE_PROJECT", source), \
                 mock.patch.object(export_module, "CANONICAL_PACK_DIR", destination), \
                 mock.patch.object(export_module, "decode_project", return_value=decoded) as decode, \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value=artifacts), \
                 mock.patch.object(
                     export_module, "verify_pack",
                     return_value={"verified": True, "manifest_sha256": "a" * 64,
                                   "artifact_count": len(artifacts)},
                 ), \
                 mock.patch.object(export_module, "_write_source_sidecar"):
                result = export_module._canonical_publish_result()

            self.assertTrue(result["ok"])
            decode.assert_called_once_with(source)
            self.assertEqual(
                json.loads(export_module._binding_sidecar_path(destination).read_text()),
                [{"channel": 2, "interaction": "press", "name": "Blue",
                  "note": 40, "target_kind": "static_look"}],
            )

    def test_canonical_publish_binding_sidecar_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.ssproj"
            destination = root / "pack"
            decoded = SimpleNamespace(resolved_controls=())
            artifacts = {"manifest.json": b"{}\n"}

            with mock.patch.object(export_module, "CANONICAL_SOURCE_PROJECT", source), \
                 mock.patch.object(export_module, "CANONICAL_PACK_DIR", destination), \
                 mock.patch.object(export_module, "decode_project", return_value=decoded), \
                 mock.patch.object(export_module, "_generator_commit", return_value="0" * 40), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   return_value=artifacts), \
                 mock.patch.object(
                     export_module, "verify_pack",
                     return_value={"verified": True, "manifest_sha256": "a" * 64,
                                   "artifact_count": len(artifacts)},
                 ), \
                 mock.patch.object(export_module, "_binding_sidecar_rows",
                                   side_effect=OSError("disk full")), \
                 mock.patch.object(export_module, "_write_source_sidecar") as source_sidecar:
                result = export_module._canonical_publish_result()

            self.assertFalse(result["ok"])
            self.assertEqual(result["verdict"], "sidecar_failed")
            self.assertEqual(result["error_category"], "BindingSidecarWriteError")
            source_sidecar.assert_not_called()

    def test_canonical_publish_creates_repo_local_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "local" / "soundswitch" / "pack"
            publish_result = {
                "verified": True,
                "manifest_sha256": "a" * 64,
                "artifact_count": 95,
                "first_export": True,
            }

            def fake_publish(_source, pack_dir):
                self.assertTrue(Path(pack_dir).parent.is_dir())
                return publish_result

            with mock.patch.object(export_module, "CANONICAL_PACK_DIR", destination), \
                 mock.patch.object(export_module, "publish_pack", side_effect=fake_publish), \
                 mock.patch.object(export_module, "_write_source_sidecar"):
                result = export_module._canonical_publish_result()

        self.assertTrue(result["ok"])

    def test_source_sidecar_failure_does_not_fail_canonical_publish(self):
        publish_result = {
            "verified": True,
            "manifest_sha256": "a" * 64,
            "artifact_count": 95,
            "first_export": False,
        }
        with mock.patch.object(export_module, "publish_pack", return_value=publish_result), \
             mock.patch.object(
                 export_module, "_write_source_sidecar", side_effect=OSError("disk full"),
             ):
            result = export_module._canonical_publish_result()
        self.assertTrue(result["ok"])
        self.assertEqual(result["manifest_sha256"], "a" * 64)

    def test_canonical_cli_failure_exposes_only_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "result.json"
            raw_message = "/private/path device UUID port details"
            with mock.patch.object(
                export_module, "publish_pack",
                side_effect=SoundSwitchPackVerificationError(raw_message),
            ):
                return_code = export_module.main([
                    "--publish-canonical", "--result-json", str(result_path),
                ])
            self.assertEqual(return_code, 1)
            result = json.loads(result_path.read_text())
            self.assertEqual(result["verdict"], "verify_failed")
            self.assertEqual(result["error_category"], "SoundSwitchPackVerificationError")
            self.assertNotIn(raw_message, result_path.read_text())
            self.assertNotIn(str(Path.home()), result_path.read_text())

    def test_canonical_cli_classifies_lock_source_and_swap_failures(self):
        cases = (
            (ExportAlreadyRunningError("busy"), "locked"),
            (SoundSwitchDecodeError("source", "unavailable"), "source_error"),
            (export_module.PackSwapError("swap"), "swap_failed"),
            (RuntimeError("other"), "unknown_error"),
        )
        for exception, verdict in cases:
            with self.subTest(verdict=verdict), \
                 mock.patch.object(export_module, "publish_pack", side_effect=exception):
                result = export_module._canonical_publish_result()
            self.assertFalse(result["ok"])
            self.assertEqual(result["verdict"], verdict)
            self.assertEqual(result["error_category"], type(exception).__name__)

    def test_legacy_cli_still_accepts_project_and_output(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(
                 export_module, "export_pack",
                 return_value={"manifest_sha256": "a" * 64, "artifact_count": 95},
             ) as export:
            output = Path(tmp) / "pack"
            return_code = export_module.main([
                "--project", "source.ssproj", "--output", str(output),
            ])
        self.assertEqual(return_code, 0)
        export.assert_called_once_with(Path("source.ssproj"), output)


if __name__ == "__main__":
    unittest.main()
