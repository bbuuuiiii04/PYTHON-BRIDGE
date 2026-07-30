"""Tests for the E1 spectral-tilt / harness watchdog battery (AWR-291 §5, Task 4c).

Per the spec: unit-test ONLY the pure comparison seam (given two grade vectors + a
probe class, produce the per-probe rho / displacement and the pass/fail verdict against
the pinned floors). These tests decode NO audio, extract NO features, and touch NO
cache — the expensive half is exercised by running the tool, never by the suite.

Also covers the two claims the tool makes about itself that would rot silently: that
its carried probe ops are verbatim copies of the E1SCRAMBLE prototype, and that it has
zero runtime importers.
"""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import energy_scramble_watchdog as W  # noqa: E402


def _vec(*vals):
    """{'P001': v1, 'P002': v2, …} in the tool's panel_id convention."""
    return {"P%03d" % (i + 1): v for i, v in enumerate(vals)}


class RankAndDisplacementTests(unittest.TestCase):
    def test_ranks_are_one_based_ascending(self):
        w = _vec(0.9, 0.1, 0.5)
        self.assertEqual(W.ranks(w, sorted(w)), {"P001": 3, "P002": 1, "P003": 2})

    def test_displacement_zero_when_order_preserved(self):
        a = _vec(0.1, 0.2, 0.3, 0.4)
        b = _vec(0.15, 0.25, 0.35, 0.45)      # same order, different values
        self.assertEqual(W.max_displacement(a, b, sorted(a)), 0)

    def test_displacement_counts_the_largest_single_move(self):
        a = _vec(0.1, 0.2, 0.3, 0.4)
        b = _vec(0.9, 0.2, 0.3, 0.4)          # P001 goes rank 1 -> 4
        self.assertEqual(W.max_displacement(a, b, sorted(a)), 3)

    def test_displacement_none_on_empty_population(self):
        self.assertIsNone(W.max_displacement({}, {}, []))


class ComparePureSeamTests(unittest.TestCase):
    def test_exact_null_passes_only_on_perfect_agreement(self):
        a = _vec(*[0.1 * i for i in range(1, 11)])
        r = W.compare_probe("c0b_invert", a, dict(a))
        self.assertEqual(r["n"], 10)
        self.assertAlmostEqual(r["rho"], 1.0, places=9)
        self.assertEqual(r["max_displacement"], 0)
        self.assertTrue(r["gated"])
        self.assertTrue(r["passed"])

    def test_exact_null_fails_on_any_rank_movement(self):
        # one swapped pair: rho drops below 1.0 and displacement becomes non-zero.
        # This is the E1SCRAMBLE gate-2 failure mode (displacement 6 vs ceiling 2 when
        # the null op was not an exact null) reproduced in the pure seam.
        a = _vec(*[0.1 * i for i in range(1, 11)])
        b = dict(a)
        b["P001"], b["P002"] = a["P002"], a["P001"]
        r = W.compare_probe("c0b_invert", a, b)
        self.assertLess(r["rho"], 1.0)
        self.assertEqual(r["max_displacement"], 1)
        self.assertFalse(r["passed"])

    def test_exact_null_fails_when_rho_is_one_but_ranks_moved(self):
        """Both halves of the c0b floor are enforced, not just rho: a monotone but
        rank-shifting perturbation must still fail."""
        a = _vec(0.1, 0.2, 0.3)
        b = _vec(0.1, 0.2, 0.3)
        r = W.compare_probe("c0b_invert", a, b)
        self.assertTrue(r["passed"])                        # baseline sanity
        r2 = W.compare_probe("c0b_invert", a, _vec(0.3, 0.1, 0.2))
        self.assertFalse(r2["passed"])

    def test_gain_gate_boundary_is_inclusive_at_the_pinned_floor(self):
        """rho >= 0.999 — the floor sits ON the measured 0.9990, so >= must be
        inclusive or the accepted instrument would fail its own gate."""
        self.assertEqual(W.GATE_GAIN_RHO, 0.999)
        r = W.compare_probe("c1a_gain", _vec(1, 2, 3), _vec(1, 2, 3))
        self.assertAlmostEqual(r["rho"], 1.0, places=9)
        self.assertTrue(r["passed"])

    def test_gain_gate_fails_below_the_floor(self):
        a = _vec(*range(1, 21))
        b = dict(a)
        for k in ("P001", "P002", "P003", "P004", "P005", "P006"):
            b[k] = a[k] + 12          # shuffle the bottom third upward
        r = W.compare_probe("c1a_gain", a, b)
        self.assertLess(r["rho"], W.GATE_GAIN_RHO)
        self.assertFalse(r["passed"])

    def test_tilt_probes_are_informational_never_gated(self):
        a = _vec(*range(1, 11))
        b = _vec(*reversed(range(1, 11)))          # maximally inverted
        for probe in W.INFORMATIONAL_PROBES:
            r = W.compare_probe(probe, a, b)
            self.assertFalse(r["gated"], "%s must not be gated" % probe)
            self.assertIsNone(r["passed"], "%s must have no pass/fail" % probe)
            self.assertIn("INFORMATIONAL", r["floor"])

    def test_population_is_the_intersection_and_n_reports_it(self):
        """A probe that lost tracks must compare the intersection and SAY how many —
        never silently score a different population against the baseline."""
        a = _vec(0.1, 0.2, 0.3, 0.4, 0.5)
        b = {"P001": 0.1, "P003": 0.3, "P005": 0.5}      # two extractions failed
        r = W.compare_probe("c1a_gain", a, b)
        self.assertEqual(r["n"], 3)

    def test_non_numeric_and_none_weights_are_excluded(self):
        a = {"P001": 0.1, "P002": None, "P003": 0.3, "P004": "x"}
        b = {"P001": 0.1, "P002": 0.2, "P003": 0.3, "P004": 0.4}
        self.assertEqual(W.compare_probe("c1a_gain", a, b)["n"], 2)

    def test_fails_closed_on_too_few_pairs(self):
        """Fewer than 3 usable pairs ⇒ rho None ⇒ a GATED probe fails. Refusal beats
        a fabricated pass."""
        r = W.compare_probe("c1a_gain", {"P001": 0.1}, {"P001": 0.1})
        self.assertIsNone(r["rho"])
        self.assertFalse(r["passed"])
        r0 = W.compare_probe("c0b_invert", {}, {})
        self.assertIsNone(r0["rho"])
        self.assertFalse(r0["passed"])


class BatteryVerdictTests(unittest.TestCase):
    def _res(self, probe, passed):
        return {"probe": probe, "passed": passed, "gated": probe in W.GATED_PROBES}

    def test_accepts_only_when_both_gated_probes_pass(self):
        self.assertEqual(
            W.battery_verdict([self._res("c0b_invert", True),
                               self._res("c1a_gain", True)]), (True, "ok"))

    def test_a_failed_gated_probe_fails_the_battery(self):
        self.assertEqual(
            W.battery_verdict([self._res("c0b_invert", True),
                               self._res("c1a_gain", False)]),
            (False, "failed:c1a_gain"))

    def test_a_missing_gated_probe_fails_closed(self):
        self.assertEqual(W.battery_verdict([self._res("c0b_invert", True)]),
                         (False, "missing_gated_probe:c1a_gain"))
        self.assertEqual(W.battery_verdict([]),
                         (False, "missing_gated_probe:c0b_invert"))

    def test_informational_probes_cannot_fail_the_battery(self):
        """The whole point of the trade: the tilt channel is comparative-only, so no
        tilt result can fail this battery. If this ever changes, the 'adds ZERO gates'
        sentence in the report header becomes false."""
        res = [self._res("c0b_invert", True), self._res("c1a_gain", True)]
        res += [{"probe": p, "passed": None, "gated": False}
                for p in W.INFORMATIONAL_PROBES]
        self.assertEqual(W.battery_verdict(res), (True, "ok"))


class PinnedConstantsTests(unittest.TestCase):
    def test_floors_and_panel_bound_are_the_pinned_values(self):
        self.assertEqual(W.GATE_INVERT_RHO, 1.0000)
        self.assertEqual(W.GATE_INVERT_DISP, 0)
        self.assertEqual(W.GATE_GAIN_RHO, 0.999)
        self.assertEqual((W.PANEL_N, W.PANEL_CELLS, W.RUN_SEED), (100, 66, 20260724))
        self.assertEqual(W.GATED_PROBES, ("c0b_invert", "c1a_gain"))
        self.assertEqual(W.INFORMATIONAL_PROBES, ("c1c_tilt_mild", "c1b_tilt"))

    def test_trade_sentence_is_present_verbatim(self):
        """The spec requires this sentence printed in the report header so the trade is
        never mistaken for gate-for-gate."""
        for phrase in ("removes one acceptance gate and adds ZERO",
                       "both new gates test the",
                       "gate-for-diagnostic, not gate-for-gate"):
            self.assertIn(phrase, W.TRADE_SENTENCE)

    def test_c1a_label_uses_the_corrected_wording_not_the_shorthand(self):
        """ER3REV F18: the inherited 'gain to -12 dB' shorthand is wrong — the gain is
        DRAWN per track. The tool must print the corrected wording."""
        label = W.PROBE_LABELS["c1a_gain"]
        self.assertIn("DRAWN in [-12, 0] dB", label)
        self.assertIn("TPDF dither at -90 dBFS", label)
        self.assertIn("c1_static seed stream", label)


class VerbatimOpsTests(unittest.TestCase):
    def test_carried_probe_ops_match_the_prototype(self):
        """The tool carries copies of the E1SCRAMBLE chain ops. This asserts they are
        AST-body identical to `local/e1_scramble_2026_07_24/scripts/chains.py` with NO
        normalisation, so the two cannot silently diverge. When the machine-local
        prototype is absent (it is gitignored) the check reports that explicitly rather
        than passing vacuously — and this test SKIPS rather than claiming agreement."""
        diff = W.verbatim_op_diff()
        if diff == ["<prototype unavailable>"]:
            self.skipTest("E1SCRAMBLE prototype chains.py not present on this machine")
        self.assertEqual(diff, [], "carried ops diverged from the prototype: %s" % diff)


class ImportFenceTests(unittest.TestCase):
    SKIP_DIRS = {".git", "graphify-out", "__pycache__", "node_modules", "build",
                 "dist", "local"}

    def test_zero_runtime_importers(self):
        """The watchdog is an offline tool: nothing outside tools/ + tests/ may import
        it. (Same shape as the E1/E2/E3 fences.)"""
        offenders = []
        for path in sorted(REPO_ROOT.rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in self.SKIP_DIRS or part.startswith(".")
                   for part in rel.split("/")):
                continue
            if rel.startswith("tools/") or rel.startswith("tests/"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                    names += [a.name for a in node.names]
                elif isinstance(node, ast.Import):
                    names += [a.name for a in node.names]
                if any("energy_scramble_watchdog" in n for n in names):
                    offenders.append(rel)
                    break
        self.assertEqual(offenders, [],
                         "energy_scramble_watchdog has runtime importers: %s"
                         % offenders)

    def test_tool_never_calls_put_cached_v4(self):
        """Hard safety rule: a perturbed entry in the real v4 cache would poison every
        future energy run. Asserted statically on the tool's own source."""
        src = (REPO_ROOT / "tools" / "energy_scramble_watchdog.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        for c in calls:
            fn = c.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            self.assertNotEqual(name, "put_cached_v4",
                                "the watchdog must never call put_cached_v4")


if __name__ == "__main__":
    unittest.main()
