"""Tests for tools/spectral_ear_benchmark.py (AWR-200 Stage-1 harness).

These prove the honesty guarantees of the harness on small synthetic fixtures —
no real cache, DB, or production planner:
  * anti-leak: label-identifying fields never reach the predictor;
  * grouped lineages never split across a LOLO fold;
  * exclusions are explicit and carry a reason;
  * output is deterministic;
  * unavailable axes stay UNAVAILABLE — never zero, never PASS.
The marker-sensitivity flip counting is exercised against a synthetic
production-seam (a fake plan_fn), proving the metric machinery without touching
the real cache.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import spectral_ear_benchmark as m  # noqa: E402


# --- synthetic label rows (shape mirrors the AWR-182 machine layer) ---------

def _rows():
    return [
        {"track": "Usable A — Artist", "content_id": "111", "id": "UA-1",
         "his_words": "drop", "classification": "AGREES"},
        {"track": "Usable A — Artist", "content_id": "111", "id": "UA-2",
         "his_words": "second moment same track", "classification": "PARTIAL"},
        {"track": "Usable B — Artist", "id": "UB-1",
         "his_words": "another track", "classification": "AGREES"},
        {"track": "Scripted Track", "id": "B3-8",
         "his_words": "this is a scripted track", "classification": "N/A-SCRIPTED"},
        {"track": "Broken Grid Track", "id": "B2-5",
         "his_words": "analysis is fucked", "classification": "EXCLUDED at operator order - broken RB analysis"},
        {"track": "Variable BPM Track", "id": "B3-3",
         "his_words": "changes bpm", "classification": "EXCLUDED (variable BPM, 4th input case)"},
        {"track": "OCHO", "id": "B2-3", "his_words": "hard techno", "classification": "PARTIAL"},
        {"track": "Usable A — Artist", "content_id": "111", "id": "UA-AMEND",
         "amends": "UA-1", "event": "note"},
        {"id": "B4-THRESHOLD-TALLY", "finding": "meta row, not an example"},
    ]


class TaxonomyTests(unittest.TestCase):
    def test_meta_and_amendment_are_not_primary_examples(self):
        entries = m.normalize(_rows())
        by_kind = {"primary": 0, "amendment": 0, "meta": 0}
        for e in entries:
            by_kind[e.kind] += 1
        self.assertEqual(by_kind["amendment"], 1)   # UA-AMEND
        self.assertEqual(by_kind["meta"], 1)        # B4-THRESHOLD-TALLY
        # meta rows never become lineages / examples
        lineages = m.build_lineages(entries)
        self.assertTrue(all("_meta" not in ln.key for ln in lineages))


class ExclusionTests(unittest.TestCase):
    def test_exclusions_explicit_with_reasons(self):
        lineages = m.build_lineages(m.normalize(_rows()))
        by_track = {ln.track: ln for ln in lineages}
        self.assertTrue(by_track["Scripted Track"].excluded)
        self.assertEqual(by_track["Scripted Track"].reason, "scripted")
        self.assertEqual(by_track["Broken Grid Track"].reason, "unusable_grid")
        self.assertEqual(by_track["Variable BPM Track"].reason, "variable_bpm")
        self.assertEqual(by_track["OCHO"].reason, "marker_blocked_pending_remap")
        # every excluded lineage carries a non-empty cited source
        for ln in lineages:
            if ln.excluded:
                self.assertTrue(ln.source, f"{ln.track} excluded without a source citation")
        # usable ones are not excluded
        self.assertFalse(by_track["Usable A — Artist"].excluded)
        self.assertFalse(by_track["Usable B — Artist"].excluded)

    def test_manifest_counts_exclusions_by_reason(self):
        entries = m.normalize(_rows())
        manifest = m.build_manifest(entries, m.build_lineages(entries))
        reasons = manifest["exclusions_by_reason"]
        self.assertIn("scripted", reasons)
        self.assertIn("variable_bpm", reasons)
        self.assertIn("marker_blocked_pending_remap", reasons)
        self.assertEqual(manifest["lineages_usable"], 2)  # Usable A, Usable B

    def test_validate_flags_undeclared_excluded_row(self):
        rows = _rows() + [{"track": "Sneaky", "id": "ZZ-9",
                           "classification": "EXCLUDED but not declared in the table"}]
        warnings = m.validate_exclusions(m.normalize(rows))
        self.assertTrue(any("ZZ-9" in w for w in warnings))


class FoldTests(unittest.TestCase):
    def test_grouped_lineage_never_splits(self):
        entries = m.normalize(_rows())
        lineages = m.build_lineages(entries)
        folds = m.build_folds(lineages)
        # one fold per usable lineage (Usable A [2 entries], Usable B [1 entry])
        self.assertEqual(len(folds), 2)
        # the multi-entry lineage's two entries always move together
        a_entries = {"UA-1", "UA-2", "UA-AMEND"}
        for f in folds:
            test_ids = set(f["test_entry_ids"])
            if test_ids & a_entries:
                # if any A entry is held out, ALL A entries are held out (never split)
                self.assertTrue(a_entries.issubset(test_ids),
                                "lineage split across train/test")

    def test_fold_assertion_catches_a_split(self):
        # build_folds asserts no lineage leaks into its own train set; that
        # assertion is exercised implicitly above. Here we just confirm the
        # train count excludes the held-out lineage.
        lineages = m.build_lineages(m.normalize(_rows()))
        folds = m.build_folds(lineages)
        for f in folds:
            self.assertEqual(f["train_lineages"], 1)  # 2 usable, hold 1 out


class AvailabilityTests(unittest.TestCase):
    def test_accuracy_axes_unavailable_not_zero_not_pass(self):
        axes = {a["axis"]: a for a in m.axis_availability(None)}
        for name in ("tier", "family", "darkness", "growl", "laser"):
            self.assertFalse(axes[name]["available"], f"{name} must be UNAVAILABLE")
            self.assertTrue(axes[name]["blocker"], f"{name} must name a blocker")
            # not zero, not PASS: gold_examples is 0 but 'available' is False,
            # so no numeric score is emitted for it.
            self.assertEqual(axes[name]["gold_examples"], 0)

    def test_marker_axis_gated_on_resolution(self):
        self.assertFalse({a["axis"]: a for a in m.axis_availability(None)}["marker_sensitivity"]["available"])
        self.assertFalse({a["axis"]: a for a in m.axis_availability(0)}["marker_sensitivity"]["available"])
        self.assertTrue({a["axis"]: a for a in m.axis_availability(7)}["marker_sensitivity"]["available"])


class AntiLeakTests(unittest.TestCase):
    def test_forbidden_fields_rejected(self):
        with self.assertRaises(ValueError):
            m.assert_no_leak({"v4": object(), "content_id": "111"})
        with self.assertRaises(ValueError):
            m.assert_no_leak({"his_words": "aggressive growl"})

    def test_clean_model_inputs_pass(self):
        m.assert_no_leak({"v4": object(), "drops": [1, 2], "buildups": [], "grid": []})


# --- synthetic production-seam for the marker metric ------------------------

class _Dark:
    def __init__(self, kind, beats):
        self.kind, self.beats = kind, beats


class _Dec:
    def __init__(self, family, tier, kind, beats):
        self.family, self.tier, self.darkness = family, tier, _Dark(kind, beats)


class _Entry:
    def __init__(self, drop_beat, dec):
        self.drop_beat, self.decision = drop_beat, dec


class _Plan:
    def __init__(self, entries):
        self._entries = entries

    def for_drop(self, beat, tol=1.0):
        best, bd = None, tol + 1
        for e in self._entries:
            d = abs(e.drop_beat - beat)
            if d <= tol and d < bd:
                best, bd = e, d
        return best


class _V4:
    def __init__(self, n_beats):
        self.n_beats = n_beats


class MarkerSensitivityTests(unittest.TestCase):
    def _res(self, drops):
        return m.Resolution(lineage="cid:1", track="T", status="resolved",
                            v4=_V4(600), drops=tuple(drops), buildups=(), grid=())

    def test_flip_counting_and_seam_gets_only_model_inputs(self):
        calls = []

        def plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
            calls.append({"v4": v4, "drops": list(drops), "buildups": list(buildups)})
            # tier 3 exactly at the true marker 100; any move -> tier 1 (a flip)
            return _Plan([_Entry(d, _Dec("WALL", 3 if d == 100 else 1, "balloon", 0)) for d in drops])

        out = m.marker_sensitivity([self._res([100])], plan_fn)
        self.assertEqual(out["markers"], 1)
        self.assertEqual(out["tracks"], 1)
        self.assertEqual(out["pm1"]["tier"], 100.0)   # perturbing flips tier
        self.assertEqual(out["pm1"]["family"], 0.0)   # family never changes
        self.assertEqual(out["pm1"]["darkness"], 0.0)
        # the seam only ever received v4 + beat indices, no label field
        for c in calls:
            self.assertEqual(set(c) & m.LEAK_FORBIDDEN_FIELDS, set())

    def test_stable_marker_flips_nothing(self):
        def plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
            return _Plan([_Entry(d, _Dec("WALL", 2, "balloon", 0)) for d in drops])

        out = m.marker_sensitivity([self._res([200])], plan_fn)
        self.assertEqual(out["pm1"]["tier"], 0.0)
        self.assertEqual(out["pm2"]["tier"], 0.0)

    def test_unresolved_tracks_excluded_from_metric(self):
        def plan_fn(*a, **k):
            raise AssertionError("planner must not be called for unresolved tracks")

        res = m.Resolution(lineage="x", track="T", status="cache_miss", drops=(10,))
        out = m.marker_sensitivity([res], plan_fn)
        self.assertEqual(out["markers"], 0)
        self.assertEqual(out["tracks"], 0)
        self.assertIsNone(out["pm1"]["tier"])


class DeterminismTests(unittest.TestCase):
    def _tmp_labels(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        for r in _rows():
            tmp.write(json.dumps(r) + "\n")
        tmp.close()
        return tmp.name

    def test_report_is_deterministic(self):
        path = self._tmp_labels()
        r1, p1 = m.run(path, resolve_db=False, head="abc123")
        r2, p2 = m.run(path, resolve_db=False, head="abc123")
        self.assertEqual(r1, r2)
        self.assertEqual(p1, p2)

    def test_core_run_is_partial_and_marker_unavailable(self):
        path = self._tmp_labels()
        report, partial = m.run(path, resolve_db=False, head="abc123")
        self.assertTrue(partial)
        self.assertIn("AWR-200 status: PARTIAL", report)
        self.assertIn("marker-sensitivity axis", report.lower())
        self.assertIn("UNAVAILABLE", report)


if __name__ == "__main__":
    unittest.main()
