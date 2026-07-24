"""Tests for the PURE comparison seam of the energy perturbation check (Task 8).
No audio decode, no feature extraction, no cache — just max_grade_delta and
perturbation_verdict, the two functions that decide pass/fail from two grade lists.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
import energy_perturbation_check as epc  # noqa: E402


class MaxGradeDeltaTests(unittest.TestCase):
    def test_paired_max_abs(self):
        self.assertAlmostEqual(
            epc.max_grade_delta([0.10, 0.50, 0.90], [0.11, 0.50, 0.86]),
            0.04, places=9)

    def test_zero_when_identical(self):
        self.assertEqual(epc.max_grade_delta([0.5, 0.5], [0.5, 0.5]), 0.0)

    def test_none_on_empty_or_length_mismatch(self):
        self.assertIsNone(epc.max_grade_delta([], [0.5]))
        self.assertIsNone(epc.max_grade_delta([0.5], []))
        self.assertIsNone(epc.max_grade_delta([0.5, 0.5], [0.5]))


class PerturbationVerdictTests(unittest.TestCase):
    def test_expected_drift_passes(self):
        self.assertEqual(epc.perturbation_verdict(0.005), (True, "ok"))
        self.assertEqual(epc.perturbation_verdict(epc.HARD_FAIL_DELTA), (True, "ok"))

    def test_break_fails(self):
        self.assertEqual(epc.perturbation_verdict(epc.HARD_FAIL_DELTA + 1e-6),
                         (False, "invariance_break"))

    def test_none_fails_closed(self):
        self.assertEqual(epc.perturbation_verdict(None), (False, "no_comparison"))

    def test_delta_db_is_attenuation(self):
        # a positive gain could clip; the shift must stay negative (A.4 / Task 8)
        self.assertLess(epc.DELTA_DB, 0.0)


if __name__ == "__main__":
    unittest.main()
