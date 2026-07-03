from __future__ import annotations

import unittest
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import export_soundswitch_pack as export_module
from rb_ss_bridge_v2.tools.export_soundswitch_pack import (
    UnverifiedParityPublishError,
    publish_pack,
)
from rb_ss_bridge_v2.tools.ssfmt.update_parity_registry import reconcile_edited_witnesses


def _record(verdict: str, source: object = "doc-a", venue: object = "venue-a") -> dict[str, object]:
    return {
        "capture_id": "cap-1",
        "source_sha256": source,
        "venue_source_sha256": venue,
        "verdict": verdict,
    }


class ReconcileEditedWitnessesTests(unittest.TestCase):
    def test_fail_committed_pass_doc_sha_changed_is_retired(self) -> None:
        fresh = {"song": _record("FAIL", source="doc-b")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {"song": _record("PASS")})
        self.assertEqual(reconciled, {})
        self.assertEqual(retired, [{
            "identity": "song",
            "reason": "witness_source_edited",
            "committed_source_sha256": "doc-a",
            "fresh_source_sha256": "doc-b",
            "committed_venue_source_sha256": "venue-a",
            "fresh_venue_source_sha256": "venue-a",
            "capture_id": "cap-1",
        }])

    def test_fail_committed_pass_venue_sha_changed_is_retired(self) -> None:
        fresh = {"loop": _record("FAIL", venue="venue-b")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {"loop": _record("PASS")})
        self.assertEqual(reconciled, {})
        self.assertEqual(retired[0]["identity"], "loop")

    def test_fail_committed_pass_identical_shas_is_kept(self) -> None:
        fresh = {"song": _record("FAIL")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {"song": _record("PASS")})
        self.assertEqual(reconciled, fresh)
        self.assertEqual(retired, [])

    def test_fail_without_committed_record_is_kept(self) -> None:
        fresh = {"song": _record("FAIL")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {})
        self.assertEqual(reconciled, fresh)
        self.assertEqual(retired, [])

    def test_fail_committed_fail_is_kept(self) -> None:
        fresh = {"song": _record("FAIL", source="doc-b")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {"song": _record("FAIL")})
        self.assertEqual(reconciled, fresh)
        self.assertEqual(retired, [])

    def test_pass_records_are_untouched(self) -> None:
        fresh = {"song": _record("PASS", source="doc-b")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {"song": _record("PASS")})
        self.assertEqual(reconciled, fresh)
        self.assertEqual(retired, [])

    def test_missing_fresh_sha_fields_are_kept(self) -> None:
        fresh = {"song": _record("FAIL", source=None, venue="")}
        reconciled, retired = reconcile_edited_witnesses(fresh, {"song": _record("PASS")})
        self.assertEqual(reconciled, fresh)
        self.assertEqual(retired, [])


class EditedWitnessPublishTests(unittest.TestCase):
    def _compile_artifacts(self, *args, **kwargs) -> dict[str, bytes]:
        registry = kwargs["parity_registry"]["scripted"]
        record = registry.get("song")
        verdict = record.get("verdict") if isinstance(record, dict) else ""
        lane = "unverified_parity" if verdict == "FAIL" else (
            "oracle_proven" if verdict == "PASS" else "algorithm_generalized"
        )
        return {
            "manifest.json": (
                '{"parity_lanes":{"algorithm_generalized":%d,'
                '"oracle_proven":%d,"unverified_parity":%d}}\n'
                % (
                    lane == "algorithm_generalized",
                    lane == "oracle_proven",
                    lane == "unverified_parity",
                )
            ).encode("ascii"),
            "scripted/song.json": (
                '{"document":{"parity_lane":"%s",'
                '"parity_evidence":{"reason":"synthetic"}}}\n' % lane
            ).encode("ascii"),
        }

    def _publish_with_fresh_record(self, fresh_record: dict[str, object], destination: Path):
        fixture = destination.parent / "scripted_reduced.json"
        fixture.write_text("{}", encoding="utf-8")
        committed = {"scripted": {"song": _record("PASS")}, "autoloop": {}, "static": {}}
        decoded = SimpleNamespace(resolved_controls=())
        patches = (
            mock.patch.object(export_module, "SCRIPTED_FIXTURE", fixture),
            mock.patch.object(
                export_module, "AUTOLOOP_FIXTURE", destination.parent / "missing-auto.json",
            ),
            mock.patch.object(
                export_module, "STATIC_FIXTURE", destination.parent / "missing-static.json",
            ),
            mock.patch.object(export_module, "_load_parity_registries", return_value=committed),
            mock.patch.object(export_module, "decode_project", return_value=decoded),
            mock.patch.object(export_module, "_generator_commit", return_value="0" * 40),
            mock.patch.object(
                export_module, "build_scripted_registry", return_value={"song": fresh_record},
            ),
            mock.patch.object(
                export_module, "compile_pack_artifacts", side_effect=self._compile_artifacts,
            ),
            mock.patch.object(
                export_module,
                "verify_pack",
                return_value={"verified": True, "manifest_sha256": "a" * 64, "artifact_count": 2},
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            return publish_pack(destination.parent / "source.ssproj", destination)

    def test_edited_witness_publishes_with_retired_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "pack"
            result = self._publish_with_fresh_record(_record("FAIL", source="doc-b"), destination)
            manifest = (destination / "manifest.json").read_text(encoding="utf-8")
            document = (destination / "scripted/song.json").read_text(encoding="utf-8")
        self.assertIn('"unverified_parity":0', manifest)
        self.assertIn('"parity_lane":"algorithm_generalized"', document)
        self.assertEqual(result["parity_evidence_retired"][0]["identity"], "song")

    def test_identical_sha_fail_still_blocks_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "pack"
            with self.assertRaises(UnverifiedParityPublishError):
                self._publish_with_fresh_record(_record("FAIL"), destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
