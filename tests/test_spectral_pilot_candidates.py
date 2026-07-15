"""Firewall + candidate determinism + abstention (tests D4, D5, D6)."""
import unittest

from tools.spectral_pilot import candidates as cand
from tools.spectral_pilot.canonical import sha256_hex
from tools.spectral_pilot.firewall import (
    ALLOWLIST, EligibleDevelopmentRow, FrozenFeatureRow,
)


def feats(**over):
    base = {k: 0.0 for k in ALLOWLIST}
    base.update(over)
    return base


def window(**over):
    w = feats(**over)
    w["coverage"] = 16.0
    return w


def query(lineage="qlin", dup="qdup", coverage=16.0, **feat):
    return FrozenFeatureRow(features=feats(**feat), coverage=coverage, marker_beat=128,
                            query_lineage_id=lineage, query_duplicate_group=dup)


def dev_row(lin, tid, *, genuine=None, hardness=None, family=None, beat=128, **feat):
    targets = {}
    if genuine is not None:
        targets["genuine"] = genuine
    if hardness is not None:
        targets["hardness"] = hardness
    if family is not None:
        targets["family"] = family
    return EligibleDevelopmentRow(
        features=feats(**feat), coverage=16.0, recording_lineage_id=lin,
        audio_duplicate_group="dup-" + lin, track_instance_id=tid, marker_beat=beat, targets=targets,
    )


class FirewallTests(unittest.TestCase):
    def test_from_window_rejects_forbidden_key(self):
        for bad in ("title", "artist", "path", "content_id", "label"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                FrozenFeatureRow.from_window({**window(), bad: "x"},
                                             query_lineage_id="l", query_duplicate_group="d",
                                             marker_beat=128)

    def test_missing_allowlist_field_rejected(self):
        w = window()
        del w["sub_db"]
        with self.assertRaises(ValueError):
            FrozenFeatureRow.from_window(w, query_lineage_id="l", query_duplicate_group="d", marker_beat=128)

    def test_nonfinite_feature_rejected(self):
        with self.assertRaises(ValueError):
            query(sub_db=float("inf"))

    def test_dev_row_rejects_forbidden_target(self):
        with self.assertRaises(ValueError):
            EligibleDevelopmentRow.from_window(
                window(), recording_lineage_id="l", audio_duplicate_group="d",
                track_instance_id="t", marker_beat=128, targets={"human_label": "genuine"})

    def test_str_feature_rejected(self):
        with self.assertRaises(TypeError):
            query(sub_db="loud")  # type: ignore[arg-type]


def _genuine_population():
    # Only sub_db varies -> 16 of 17 fields have zero MAD and are dropped.
    rows = [
        dev_row("A", "t-a", genuine="genuine", sub_db=1.0),
        dev_row("B", "t-b", genuine="genuine", sub_db=1.2),
        dev_row("C", "t-c", genuine="genuine", sub_db=0.8),
        dev_row("D", "t-d", genuine="not_genuine", sub_db=9.0),
        dev_row("E", "t-e", genuine="not_genuine", sub_db=9.2),
    ]
    return rows


class CandidateDeterminismTests(unittest.TestCase):
    def test_zero_mad_fields_dropped_and_hashed(self):
        scaler = cand.fit_scaler(_genuine_population())
        self.assertEqual(scaler.retained, ("sub_db",))
        self.assertEqual(scaler.retained_field_hash, sha256_hex(["sub_db"]))

    def test_permuted_dev_order_identical_prediction_hash(self):
        rows = _genuine_population()
        q = query(sub_db=1.0)
        scaler = cand.fit_scaler(rows)
        a = cand.predict_retrieval_genuine(q, rows, scaler, "card-1")
        scaler2 = cand.fit_scaler(list(reversed(rows)))
        b = cand.predict_retrieval_genuine(q, list(reversed(rows)), scaler2, "card-1")
        self.assertEqual(sha256_hex(a.to_dict()), sha256_hex(b.to_dict()))
        self.assertEqual(a.prediction, "genuine")

    def test_equal_distance_tie_break_by_track_instance_id(self):
        # two equidistant lineages, distinct tids -> smaller tid ranks first
        rows = [
            dev_row("A", "t-zzz", genuine="genuine", sub_db=2.0),
            dev_row("B", "t-aaa", genuine="genuine", sub_db=0.0),
            dev_row("C", "t-mmm", genuine="not_genuine", sub_db=5.0),
        ]
        scaler = cand.fit_scaler(rows)
        q = query(sub_db=1.0)  # equidistant from A (2.0) and B (0.0)
        p = cand.predict_retrieval_genuine(q, rows, scaler, "card-1")
        # A and B both distance |1| after scaling; tie-break puts t-aaa before t-zzz
        self.assertEqual(p.eligible_neighbour_ids[0], "t-aaa")

    def test_ood_query_abstains(self):
        rows = _genuine_population()
        scaler = cand.fit_scaler(rows)
        p = cand.predict_retrieval_genuine(query(sub_db=1000.0), rows, scaler, "card-1")
        self.assertTrue(p.abstained)
        self.assertIn("ood", p.reason_codes)

    def test_hardness_mapping(self):
        rows = [
            dev_row("A", "t-a", hardness="T3", sub_db=1.0),
            dev_row("B", "t-b", hardness="T3", sub_db=1.1),
            dev_row("C", "t-c", hardness="T3", sub_db=0.9),
        ]
        scaler = cand.fit_scaler(rows)
        harder = cand.predict_retrieval_hardness(query(sub_db=1.0), rows, scaler, "card-1", "T1")
        softer = cand.predict_retrieval_hardness(query(sub_db=1.0), rows, scaler, "card-1", "T3")
        self.assertEqual(harder.prediction, "harder")
        self.assertEqual(softer.prediction, "tied")


class AbstentionTests(unittest.TestCase):
    def test_short_coverage_abstains(self):
        rows = _genuine_population()
        scaler = cand.fit_scaler(rows)
        p = cand.predict_retrieval_genuine(query(coverage=8.0, sub_db=1.0), rows, scaler, "c")
        self.assertTrue(p.abstained)
        self.assertEqual(p.reason_codes, ["coverage_lt_16"])

    def test_fewer_than_three_lineages_abstains(self):
        rows = [dev_row("A", "t-a", genuine="genuine", sub_db=1.0),
                dev_row("B", "t-b", genuine="genuine", sub_db=2.0)]
        scaler = cand.fit_scaler(rows)
        p = cand.predict_retrieval_genuine(query(sub_db=1.0), rows, scaler, "c")
        self.assertTrue(p.abstained)
        self.assertIn("lt_3_eligible_lineages", p.reason_codes)

    def test_family_three_way_vote_tie_abstains(self):
        descs = [
            _family_desc("A", "t-a", "WALL", 1.0),
            _family_desc("B", "t-b", "COMET", 1.05),
            _family_desc("C", "t-c", "HOUSE", 0.95),
        ]
        scaler = cand.fit_scaler(descs, allowlist=cand.FAMILY_ALLOWLIST)
        q = _family_query(1.0)
        p = cand.predict_retrieval_family(q, descs, scaler, "c")
        self.assertTrue(p.abstained)
        self.assertIn("vote_tie", p.reason_codes)

    def test_baseline_b_majority_and_tie(self):
        rows = [dev_row("A", "t-a", genuine="genuine"), dev_row("B", "t-b", genuine="genuine"),
                dev_row("C", "t-c", genuine="not_genuine")]
        self.assertEqual(cand.predict_baseline_b_genuine("c", rows).prediction, "genuine")
        tie = [dev_row("A", "t-a", genuine="genuine"), dev_row("B", "t-b", genuine="not_genuine")]
        p = cand.predict_baseline_b_genuine("c", tie)
        self.assertTrue(p.abstained)
        self.assertIn("dev_majority_tie", p.reason_codes)

    def test_baseline_a_family_and_genuine(self):
        self.assertEqual(cand.predict_baseline_a_family("c", "WALL", "WALL").prediction, "WALL")
        self.assertEqual(cand.predict_baseline_a_family("c", "WALL", "COMET").prediction, "mixed")
        self.assertEqual(cand.predict_baseline_a_family("c", "NEUTRAL", "NEUTRAL").prediction, "none")
        self.assertTrue(cand.predict_baseline_a_family("c", None, "WALL").abstained)
        self.assertTrue(cand.predict_baseline_a_genuine("c").abstained)
        self.assertEqual(cand.predict_baseline_a_hardness("c", "T3", "T1").prediction, "harder")


def _family_desc(lin, tid, family, val):
    from tools.spectral_pilot.candidates import montage_descriptor_features
    row_a = feats(sub_db=val)
    row_b = feats(sub_db=val + 0.2)
    f = montage_descriptor_features(row_a, row_b)

    class _D:
        features = f
        recording_lineage_id = lin
        audio_duplicate_group = "dup-" + lin
        track_instance_id = tid
        marker_beat = 128
        targets = {"family": family}
    return _D()


def _family_query(val):
    from tools.spectral_pilot.candidates import montage_descriptor_features

    class _Q:
        features = montage_descriptor_features(feats(sub_db=val), feats(sub_db=val + 0.2))
        recording_lineage_id = "qlin"
        audio_duplicate_group = "qdup"
    return _Q()


if __name__ == "__main__":
    unittest.main()
