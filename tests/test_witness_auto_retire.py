from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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


if __name__ == "__main__":
    unittest.main()
