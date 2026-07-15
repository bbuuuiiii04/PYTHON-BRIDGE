"""Schema rejection: missing/unknown fields, wrong enums, nonfinite floats (test D1)."""
import unittest

from tools.spectral_pilot import schemas as S


def _selected_row():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed", created_from_head="abc123",
        track_instance_id="0" * 16, content_id_locator="loc-1", audio_sha256="a" * 64,
        audio_duplicate_group="grp-1", recording_lineage_id="lin-1", split_role="pilot",
        beatgrid_fingerprint="bg", marker_set_fingerprint="ms", label_store_hash="ls",
        exclusion_reason="none", lineage_review_state="confirmed",
        curator_confirmation="not_applicable", family_montage_marker_ids=["m1", "m2"],
    )


def _card_row():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed", card_id="c" * 16,
        card_type="marker_state", session_index="P1", order_index=0,
        track_instance_id="0" * 16, marker_beat=128, display_left_id=None,
        display_right_id=None, anchor_role=None, repeat_of_card_id=None,
        clip_spec={"audio_sha256": "a" * 64, "start_beat": 128, "end_beat": 144}, card_hash="h",
    )


def _response_row():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed", card_id="c" * 16, commit_index=0,
        question="state", displayed_response="genuine", canonical_response="genuine",
        recognized=False, response_seconds=1.5, commit_utc="2026-07-15T00:00:00Z",
        local_date="2026-07-15", session_index="P1",
        segment_index=0, prev_row_hash="0" * 64, card_manifest_hash="m" * 64,
    )


def _contract():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed", method_version="v4_exact_retrieval_v1",
        positive_allowlist=["sub_db"], scaler_population_hash="s", retained_field_hash="r",
        code_hash="c", environment_lock_hash="e", development_manifest_hash="d",
    )


def _prediction():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed", method_version="v4_exact_retrieval_v1",
        axis="genuine", target_id="c" * 16, manifest_hash="m", input_hash="i",
        scaler_population_hash="s", eligible_neighbour_ids=[], excluded_neighbour_ids=[],
        distances=[], prediction=None, abstained=True, raw_score=None,
        reason_codes=["insufficient_lineages"], error_state=None,
    )


def _resource():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed", analysis_wall_seconds=1.0,
        peak_rss_bytes=1, scratch_peak_bytes=1, retained_bytes=1, manual_prep_minutes=1.0,
        human_active_seconds=1.0, decisions_total=0, cleanup_seconds=1.0,
        ceilings={"human_active_seconds": 3900}, breaches=[],
    )


def _verdict():
    return dict(
        schema_version=S.SCHEMA_VERSION, pilot_seed="seed",
        gate_results={"1": {"state": "PASS", "evidence": []}}, integrated="INCONCLUSIVE",
        failed_gates=[], inconclusive_floors=["genuine_availability"], stopped_axes=[],
        input_hashes={}, created_from_head="abc123",
    )


CASES = [
    (S.SelectedRow, _selected_row, ("split_role", "nope"), "family_montage_marker_ids"),
    (S.CardManifestRow, _card_row, ("card_type", "nope"), None),
    (S.ResponseRow, _response_row, ("session_index", "Z"), "response_seconds"),
    (S.CandidateContract, _contract, None, None),
    (S.PredictionRow, _prediction, ("axis", "nope"), "raw_score"),
    (S.ResourceReport, _resource, None, "analysis_wall_seconds"),
    (S.Verdict, _verdict, ("integrated", "nope"), None),
]


class SchemaRejectionTests(unittest.TestCase):
    def test_valid_rows_accept(self):
        for cls, make, _enum, _float in CASES:
            with self.subTest(cls=cls.__name__):
                obj = cls.from_dict(make())
                self.assertEqual(obj.schema_version, S.SCHEMA_VERSION)

    def test_missing_field_rejected(self):
        for cls, make, _enum, _float in CASES:
            d = make()
            d.pop(next(iter(d)))
            with self.subTest(cls=cls.__name__), self.assertRaises((ValueError, TypeError)):
                cls.from_dict(d)

    def test_unknown_field_rejected(self):
        for cls, make, _enum, _float in CASES:
            d = make()
            d["surprise_field"] = 1
            with self.subTest(cls=cls.__name__), self.assertRaises(ValueError):
                cls.from_dict(d)

    def test_wrong_enum_rejected(self):
        for cls, make, enum, _float in CASES:
            if enum is None:
                continue
            key, bad = enum
            d = make()
            d[key] = bad
            with self.subTest(cls=cls.__name__), self.assertRaises(ValueError):
                cls.from_dict(d)

    def test_nonfinite_float_rejected(self):
        for cls, make, _enum, float_key in CASES:
            if float_key is None:
                continue
            d = make()
            if float_key == "family_montage_marker_ids":
                d[float_key] = "not-a-list"  # type check stands in for this row
                with self.subTest(cls=cls.__name__), self.assertRaises(TypeError):
                    cls.from_dict(d)
                continue
            d[float_key] = float("inf")
            with self.subTest(cls=cls.__name__), self.assertRaises(ValueError):
                cls.from_dict(d)


if __name__ == "__main__":
    unittest.main()
