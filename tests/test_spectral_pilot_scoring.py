"""Scoring reconciliation, verdict truth table, deterministic replay (D7, D9, D13)."""
import unittest

from tools.spectral_pilot import candidates as cand
from tools.spectral_pilot import scoring, verdict
from tools.spectral_pilot.canonical import canonical_bytes
from tools.spectral_pilot.firewall import ALLOWLIST, EligibleDevelopmentRow, FrozenFeatureRow
from tools.spectral_pilot.schemas import PredictionRow, SCHEMA_VERSION


def pred(target_id, prediction, abstained=False, error_state=None):
    return PredictionRow(
        schema_version=SCHEMA_VERSION, pilot_seed="", method_version="v4_exact_retrieval_v1",
        axis="genuine", target_id=target_id, manifest_hash="m", input_hash="i",
        scaler_population_hash="s", eligible_neighbour_ids=[], excluded_neighbour_ids=[],
        distances=[], prediction=prediction, abstained=abstained, raw_score=None,
        reason_codes=[], error_state=error_state,
    )


# --- default gate inputs: all PASS ------------------------------------------
def base_inputs():
    return dict(
        pilot_seed="seed", created_from_head="head", input_hashes={},
        setup_failures=[],
        repeatability=dict(marker_repeats=6, hardness_repeats=6, family_repeats=4,
                           marker_contradictions=0, hardness_contradictions=0, family_contradictions=0),
        workload=dict(active_seconds=3000, decisions_total=100, operator_stop_exhausting=False),
        genuine=dict(comparable_calls=30, comparable_lineages=16, correct_delta=6,
                     lineage_win_margin=4, candidate_abstentions=2, stopped=False),
        hardness=dict(comparable_calls=26, comparable_lineages=14, correct_delta=6,
                      lineage_win_margin=4, candidate_abstentions=2, stopped=False),
        family=dict(comparable_lineages=14, correct_delta=4, lineage_win_margin=4,
                    candidate_abstentions=2, decisive_noncommittal_human=2, stopped=False),
        stability=dict(genuine_central_rows=28, hardness_central_rows=28,
                       genuine_flip_gap_pp=0.0, hardness_flip_gap_pp=0.0),
        seed_pool_eligible_lineages=18,
    )


class ReconciliationTests(unittest.TestCase):
    def test_every_row_lands_in_one_state(self):
        rows = [pred("a", "genuine"), pred("b", None, abstained=True), pred("c", None, error_state="boom")]
        states = scoring.reconcile_axis(
            ["a", "b", "c", "d"], rows, excluded_ids={"d"},
            human_states={"a": "answered", "b": "human_unavailable", "c": "answered", "d": "human_unavailable"})
        self.assertEqual(states["a"], "predicted")
        self.assertEqual(states["b"], "abstained_with_reason")
        self.assertEqual(states["c"], "hard_failure")
        self.assertEqual(states["d"], "excluded_with_prespecified_reason")
        self.assertEqual(scoring.state_counts(states)["predicted"], 1)

    def test_predicted_without_human_state_fails(self):
        with self.assertRaises(scoring.ReconcileError):
            scoring.reconcile_axis(["a"], [pred("a", "genuine")], set(), {"a": None})

    def test_missing_prediction_fails(self):
        with self.assertRaises(scoring.ReconcileError):
            scoring.reconcile_axis(["a", "b"], [pred("a", "genuine")], set(), {"a": "answered"})

    def test_both_predicted_and_excluded_fails(self):
        with self.assertRaises(scoring.ReconcileError):
            scoring.reconcile_axis(["a"], [pred("a", "genuine")], {"a"}, {"a": "answered"})

    def test_paired_scoring_win_loss(self):
        rows = [
            {"lineage": "L1", "truth": "genuine", "candidate_pred": "genuine", "baseline_pred": "not_genuine"},
            {"lineage": "L2", "truth": "genuine", "candidate_pred": None, "baseline_pred": "genuine"},
        ]
        s = scoring.paired_scoring(rows)
        self.assertEqual(s["correct_delta"], 0)       # +1 on L1, -1 on L2
        self.assertEqual(s["lineage_win_margin"], 0)  # one win, one loss
        self.assertEqual(s["candidate_abstentions"], 1)

    def test_repeatability_contradictions(self):
        reps = [
            {"axis": "marker", "answers": ["genuine", "not_genuine"]},   # contradiction
            {"axis": "marker", "answers": ["genuine", "unsure"]},        # not a contradiction
            {"axis": "hardness", "answers": ["harder", "softer"]},       # contradiction
            {"axis": "family", "answers": ["WALL", "COMET"]},            # contradiction
            {"axis": "family", "answers": ["WALL", "unsure"]},           # not
        ]
        c = scoring.repeatability_counters(reps)
        self.assertEqual(c["marker_contradictions"], 1)
        self.assertEqual(c["hardness_contradictions"], 1)
        self.assertEqual(c["family_contradictions"], 1)

    def test_stability_flip_rate(self):
        rows = [
            {"central": "genuine", "shifts": ["genuine", "genuine", "not_genuine", "invalid"]},
            {"central": "abstain", "shifts": ["genuine", "genuine", "genuine", "genuine"]},  # excluded
            {"central": "genuine", "shifts": ["genuine", "invalid", "invalid", "invalid"]},   # <3 valid
        ]
        s = scoring.stability_flips(rows)
        self.assertEqual(s["comparable_rows"], 1)
        self.assertEqual(s["valid_shifts"], 3)
        self.assertAlmostEqual(s["flip_rate"], 1 / 3)


class VerdictTruthTableTests(unittest.TestCase):
    def test_all_pass_is_pass(self):
        v = verdict.compute_verdict(**base_inputs())
        self.assertEqual(v.integrated, "PASS")

    def test_setup_failure_is_fail(self):
        inp = base_inputs()
        inp["setup_failures"] = ["firewall breach"]
        v = verdict.compute_verdict(**inp)
        self.assertEqual(v.integrated, "FAIL")
        self.assertIn("1", v.failed_gates)

    def test_family_contradiction_fails(self):
        inp = base_inputs()
        inp["repeatability"]["family_contradictions"] = 1
        self.assertEqual(verdict.compute_verdict(**inp).integrated, "FAIL")

    def test_workload_breach_fails(self):
        inp = base_inputs()
        inp["workload"]["decisions_total"] = 200
        self.assertEqual(verdict.compute_verdict(**inp).integrated, "FAIL")

    def test_hidden_axis_failure_never_passes(self):
        inp = base_inputs()
        inp["genuine"]["correct_delta"] = 0     # gate 4 FAIL hidden behind other PASSes
        v = verdict.compute_verdict(**inp)
        self.assertEqual(v.integrated, "FAIL")
        self.assertIn("4", v.failed_gates)

    def test_stopped_axis_is_inconclusive_not_pass(self):
        inp = base_inputs()
        inp["family"]["stopped"] = True
        v = verdict.compute_verdict(**inp)
        self.assertEqual(v.integrated, "INCONCLUSIVE")
        self.assertIn("family", v.stopped_axes)
        self.assertIn("6", v.inconclusive_floors)

    def test_availability_floor_is_inconclusive(self):
        inp = base_inputs()
        inp["genuine"]["comparable_calls"] = 10
        v = verdict.compute_verdict(**inp)
        self.assertEqual(v.integrated, "INCONCLUSIVE")

    def test_family_noncommittal_over_four_fails(self):
        inp = base_inputs()
        inp["family"]["decisive_noncommittal_human"] = 5
        self.assertEqual(verdict.compute_verdict(**inp).integrated, "FAIL")

    def test_stability_flip_gap_fails(self):
        inp = base_inputs()
        inp["stability"]["genuine_flip_gap_pp"] = 11.0
        self.assertEqual(verdict.compute_verdict(**inp).integrated, "FAIL")

    def test_seed_pool_under_18_inconclusive(self):
        inp = base_inputs()
        inp["seed_pool_eligible_lineages"] = 12
        v = verdict.compute_verdict(**inp)
        self.assertEqual(v.integrated, "INCONCLUSIVE")
        self.assertIn("seed_pool_lt_18", v.inconclusive_floors)


class DeterministicReplayTests(unittest.TestCase):
    """A full synthetic scoring+verdict pass twice -> byte-identical (test D13)."""

    def _run(self):
        # deterministic candidate C predictions over a synthetic corpus
        def feats(v):
            base = {k: 0.0 for k in ALLOWLIST}
            base["sub_db"] = v
            return base

        dev = [
            EligibleDevelopmentRow(features=feats(1.0), coverage=16.0, recording_lineage_id="A",
                                   audio_duplicate_group="da", track_instance_id="ta", marker_beat=128,
                                   targets={"genuine": "genuine"}),
            EligibleDevelopmentRow(features=feats(1.1), coverage=16.0, recording_lineage_id="B",
                                   audio_duplicate_group="db", track_instance_id="tb", marker_beat=128,
                                   targets={"genuine": "genuine"}),
            EligibleDevelopmentRow(features=feats(9.0), coverage=16.0, recording_lineage_id="C",
                                   audio_duplicate_group="dc", track_instance_id="tc", marker_beat=128,
                                   targets={"genuine": "not_genuine"}),
        ]
        scaler = cand.fit_scaler(dev)
        q = FrozenFeatureRow(features=feats(1.0), coverage=16.0, marker_beat=128,
                             query_lineage_id="Q", query_duplicate_group="dq")
        p = cand.predict_retrieval_genuine(q, dev, scaler, "card-1")
        rep = scoring.repeatability_counters([{"axis": "marker", "answers": ["genuine", "genuine"]}] * 6
                                             + [{"axis": "hardness", "answers": ["harder", "harder"]}] * 6
                                             + [{"axis": "family", "answers": ["WALL", "WALL"]}] * 4)
        inp = base_inputs()
        inp["repeatability"] = rep
        v = verdict.compute_verdict(**inp)
        return p, v

    def test_replay_byte_identical(self):
        p1, v1 = self._run()
        p2, v2 = self._run()
        self.assertEqual(canonical_bytes(p1.to_dict()), canonical_bytes(p2.to_dict()))
        self.assertEqual(canonical_bytes(v1.to_dict()), canonical_bytes(v2.to_dict()))
        self.assertEqual(v1.integrated, "PASS")


if __name__ == "__main__":
    unittest.main()
