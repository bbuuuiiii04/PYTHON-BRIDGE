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


class FoldInvariantTests(unittest.TestCase):
    """The real fold invariant (finding 5), replacing the old tautological
    `held.key not in train_keys` assertion + its misleading test: no entry id and
    no RESOLVED amendment lineage may appear in both train and test of any fold."""

    def test_no_entry_or_amendment_lineage_in_both_splits(self):
        rows = _rows() + [
            # amendment tied to Usable A ONLY through `amends` — no content_id and
            # a totally different track string. The hard case: it must still ride
            # with its parent through the fold, never split into train.
            {"track": "Totally Different String", "id": "UA-EDIT", "amends": "UA-1",
             "event": "edit"},
        ]
        entries = m.normalize(rows)
        lineages = m.build_lineages(entries)
        folds = m.build_folds(lineages)
        usable_ids = {eid for ln in lineages if not ln.excluded for eid in ln.entry_ids}
        # every usable entry id is held out in exactly one fold (a partition)
        seen: dict[str, int] = {}
        for f in folds:
            for eid in f["test_entry_ids"]:
                self.assertNotIn(eid, seen, f"{eid} appears in two test folds")
                seen[eid] = f["fold"]
        self.assertEqual(set(seen), usable_ids)
        # the amendment (resolved lineage) is held out WITH Usable A, never in train
        a_ids = {"UA-1", "UA-2", "UA-AMEND", "UA-EDIT"}
        for f in folds:
            test_ids = set(f["test_entry_ids"])
            if test_ids & a_ids:
                self.assertTrue(a_ids.issubset(test_ids),
                                "resolved amendment lineage split across train/test")


class AmendmentLineageTests(unittest.TestCase):
    """Finding 2: amendment grouping follows the `amends` parent link, not the
    amendment's own (possibly absent) content_id / differing track string."""

    def test_amendment_without_cid_and_diff_track_groups_with_parent(self):
        rows = [
            {"track": "Rewind — Artist", "content_id": "900", "id": "P1", "his_words": "drop"},
            # no content_id, different track string — only `amends` ties it back
            {"track": "Rewind (post-reanalysis eight-drop)", "id": "P1-AMEND",
             "amends": "P1", "his_words": "eight drops now"},
        ]
        entries = m.normalize(rows)
        amend = next(e for e in entries if e.label_id == "P1-AMEND")
        parent = next(e for e in entries if e.label_id == "P1")
        self.assertEqual(amend.lineage, parent.lineage)   # grouped via amends
        lineages = m.build_lineages(entries)
        self.assertEqual(len(lineages), 1)                # one lineage, both entries
        self.assertEqual(set(lineages[0].entry_ids), {"P1", "P1-AMEND"})
        self.assertEqual(m.amendment_warnings(entries), [])

    def test_missing_parent_warns_and_stays_ungrouped(self):
        rows = [
            {"track": "Solo — Artist", "content_id": "901", "id": "P2"},
            {"track": "Ghost", "id": "GHOST-AMEND", "amends": "NOPE"},
        ]
        entries = m.normalize(rows)
        warns = m.amendment_warnings(entries)
        self.assertTrue(any("GHOST-AMEND" in w and "unknown id" in w for w in warns))
        amend = next(e for e in entries if e.label_id == "GHOST-AMEND")
        parent = next(e for e in entries if e.label_id == "P2")
        self.assertNotEqual(amend.lineage, parent.lineage)  # not silently merged/split

    def test_cyclic_parent_link_warns(self):
        rows = [
            {"track": "A", "id": "X", "amends": "Y"},
            {"track": "B", "id": "Y", "amends": "X"},
        ]
        warns = m.amendment_warnings(m.normalize(rows))
        self.assertTrue(any("cyclic" in w for w in warns))

    def test_ambiguous_parent_id_warns(self):
        rows = [
            {"track": "Dup — Artist", "content_id": "902", "id": "DUP"},
            {"track": "Dup — Artist", "content_id": "903", "id": "DUP"},  # same id, 2 rows
            {"track": "Note", "id": "DUP-AMEND", "amends": "DUP"},
        ]
        warns = m.amendment_warnings(m.normalize(rows))
        self.assertTrue(any("ambiguous" in w and "DUP" in w for w in warns))

    def test_duplicate_amendment_own_id_warns_and_does_not_corrupt_primary(self):
        # The amendment's OWN id 'X' collides with a PRIMARY's id. Without the
        # own-id guard, normalize()'s by-label_id rewrite would drag Alpha's
        # primary into Gamma's lineage (the finding-2 latent hole caught in the
        # adversarial review). It must warn and leave the primary untouched.
        rows = [
            {"track": "Alpha — Artist", "content_id": "900", "id": "X"},   # primary
            {"track": "Gamma — Artist", "content_id": "902", "id": "P2"},  # primary
            {"track": "note", "id": "X", "amends": "P2"},                  # amendment; id collides
        ]
        entries = m.normalize(rows)
        warns = m.amendment_warnings(entries)
        self.assertTrue(any("shared by 2 rows" in w for w in warns))
        alpha = next(e for e in entries if e.label_id == "X" and e.kind == "primary")
        self.assertEqual(alpha.lineage, "cid:900")     # primary NOT silently mis-grouped
        amend = next(e for e in entries if e.label_id == "X" and e.kind == "amendment")
        self.assertNotEqual(amend.lineage, "cid:902")  # amendment NOT silently merged into Gamma


class IdentityWarningTests(unittest.TestCase):
    """Finding 6: same-title / no-content_id rows can collide. The harness does
    NOT guess identity — it surfaces a deterministic warning/limitation."""

    def test_same_title_two_content_ids_flagged(self):
        rows = [
            {"track": "Give It To Me Good", "content_id": "500", "id": "G1"},
            {"track": "Give It To Me Good", "content_id": "501", "id": "G2"},
        ]
        warns = m.identity_warnings(m.build_lineages(m.normalize(rows)))
        self.assertTrue(any("identity ambiguity" in w and "give it to me good" in w for w in warns))

    def test_no_content_id_limitation_surfaced(self):
        rows = [{"track": "Some Track — Artist", "id": "S1"}]   # usable, no content_id
        warns = m.identity_warnings(m.build_lineages(m.normalize(rows)))
        self.assertTrue(any("identity limitation" in w and "1 usable" in w for w in warns))


class PlannerBoundaryTests(unittest.TestCase):
    """Finding 1: EVERY planner call routes through call_planner, and the guard
    fails if a forbidden label/locator field OR an unexpected field reaches it."""

    @staticmethod
    def _fake(v4, drops, buildups, *, beatgrid_times_ms=()):
        return "PLAN"

    def test_rejects_forbidden_label_field(self):
        with self.assertRaises(ValueError):
            m.call_planner(self._fake, {"v4": object(), "drops": [], "buildups": [],
                                        "beatgrid_times_ms": [], "track": "Utopia"})

    def test_rejects_unexpected_field(self):
        with self.assertRaises(ValueError):
            m.call_planner(self._fake, {"v4": object(), "drops": [], "buildups": [],
                                        "beatgrid_times_ms": [], "n_beats": 600})

    def test_clean_call_passes_only_model_inputs(self):
        seen: dict = {}

        def fake(v4, drops, buildups, *, beatgrid_times_ms=()):
            seen.update(v4=v4, drops=drops, buildups=buildups, grid=beatgrid_times_ms)
            return "PLAN"

        out = m.call_planner(fake, {"v4": 1, "drops": [5], "buildups": [], "beatgrid_times_ms": []})
        self.assertEqual(out, "PLAN")
        self.assertEqual(seen["drops"], [5])


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
        # markers scored AND at least one comparable perturbation -> AVAILABLE
        self.assertTrue({a["axis"]: a for a in m.axis_availability(7, 5)}["marker_sensitivity"]["available"])
        # markers scored but ZERO comparable perturbations at both radii -> UNAVAILABLE
        # (finding: baseline decisions alone can't score the axis; both flip rates are None).
        zero = {a["axis"]: a for a in m.axis_availability(7, 0)}["marker_sensitivity"]
        self.assertFalse(zero["available"])
        self.assertIn("comparable", zero["blocker"])
        # default (no comparable count) fails closed toward UNAVAILABLE
        self.assertFalse({a["axis"]: a for a in m.axis_availability(7)}["marker_sensitivity"]["available"])


class PartialGateTests(unittest.TestCase):
    """A resolved marker pilot must NEVER flip AWR-200 out of PARTIAL while the
    accuracy axes are unavailable (executive gate fix)."""

    def test_is_partial_true_even_when_marker_available(self):
        # marker AVAILABLE (7 markers scored, 5 comparable) but accuracy axes all unavailable
        self.assertTrue(m.is_partial(m.axis_availability(7, 5)))
        self.assertTrue(m.is_partial(m.axis_availability(0)))
        self.assertTrue(m.is_partial(m.axis_availability(None)))

    def test_is_partial_false_only_when_all_accuracy_axes_available(self):
        avail = m.axis_availability(0)
        for a in avail:
            if a["axis"] in m.REQUIRED_ACCURACY_AXES:
                a["available"] = True   # simulate a future curated corpus
        self.assertFalse(m.is_partial(avail))
        # one missing accuracy axis is enough to stay PARTIAL
        avail[0]["available"] = False
        self.assertTrue(m.is_partial(avail))

    def test_report_stays_partial_with_marker_available(self):
        entries = m.normalize(_rows())
        manifest = m.build_manifest(entries, m.build_lineages(entries))
        marker = {"markers": 16, "tracks": 2, "skipped": 0,
                  "pm1": {"family": 25.0, "tier": 6.2, "darkness": 0.0},
                  "pm2": {"family": 43.8, "tier": 12.5, "darkness": 18.8}}
        report = m.render_report(
            head="x", labels_path="p", label_sha="s", manifest=manifest,
            warnings=[], folds=[], availability=m.axis_availability(2, 2),
            marker=marker, resolution_summary={"resolved": 2, "not_in_db": 19})
        self.assertIn("AWR-200 status: PARTIAL", report)
        self.assertNotIn("baseline-complete", report)


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

    def test_resolved_but_zero_markers_scored_reads_unavailable(self):
        # Finding 3: a track resolves and HAS drops, but the plan has no entry
        # near any drop, so every baseline decision is None -> markers==0 while
        # tracks==1. Availability must key off markers SCORED, not tracks.
        def plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
            return _Plan([])   # for_drop returns None for every marker

        res = m.Resolution(lineage="cid:1", track="T", status="resolved",
                           v4=_V4(600), drops=(100, 200), buildups=(), grid=())
        out = m.marker_sensitivity([res], plan_fn)
        self.assertEqual(out["tracks"], 1)      # resolved with drops
        self.assertEqual(out["markers"], 0)     # but nothing scored
        self.assertEqual(out["skipped"], 2)     # both drops had no baseline decision
        axis = {a["axis"]: a for a in m.axis_availability(out["markers"])}["marker_sensitivity"]
        self.assertFalse(axis["available"])     # NOT a hollow AVAILABLE on tracks>0


class MarkerRadiusDenominatorTests(unittest.TestCase):
    """Finding 4: a marker with no comparable perturbation at a radius must leave
    that radius's denominator. Per-radius comparable counts are reported."""

    def test_uncomparable_marker_excluded_from_pm1_denominator(self):
        # drops 9,10,11,100. Marker 10's +-1 neighbours (9,11) are BOTH occupied
        # by other drops, so it has no comparable +-1 perturbation; it stays in
        # +-2 (8,12 free). tier flips only at marker 100 (base tier 3 there).
        def plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
            return _Plan([_Entry(d, _Dec("WALL", 3 if d == 100 else 1, "balloon", 0)) for d in drops])

        res = m.Resolution(lineage="cid:1", track="T", status="resolved",
                           v4=_V4(600), drops=(9, 10, 11, 100), buildups=(), grid=())
        out = m.marker_sensitivity([res], plan_fn)
        self.assertEqual(out["markers"], 4)
        self.assertEqual(out["comparable_pm1"], 3)   # marker 10 dropped from +-1 denom
        self.assertEqual(out["comparable_pm2"], 4)   # all comparable at +-2
        # 1 tier flip (marker 100) / 3 comparable => 33.3, NOT 25.0 (/4 markers)
        self.assertEqual(out["pm1"]["tier"], 33.3)
        self.assertEqual(out["pm2"]["tier"], 25.0)   # 1 / 4 comparable at +-2
        self.assertEqual(out["pm1"]["family"], 0.0)

    def test_baseline_decisions_but_zero_comparable_reads_unavailable(self):
        # Finding: a marker can HAVE a baseline decision yet have NO comparable
        # perturbation at either radius (here a lone drop at beat 0 with n_beats=1:
        # -1/-2 fall below 0 and +1/+2 fall out of range). markers>0 but
        # comparable_pm1==comparable_pm2==0, so both flip rates are None and nothing
        # was measured. Availability must read UNAVAILABLE, not a hollow AVAILABLE on
        # markers>0 alone.
        def plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
            return _Plan([_Entry(d, _Dec("WALL", 2, "balloon", 0)) for d in drops])

        res = m.Resolution(lineage="cid:1", track="T", status="resolved",
                           v4=_V4(1), drops=(0,), buildups=(), grid=())
        out = m.marker_sensitivity([res], plan_fn)
        self.assertEqual(out["markers"], 1)          # baseline decision exists
        self.assertEqual(out["comparable_pm1"], 0)   # no comparable +-1 perturbation
        self.assertEqual(out["comparable_pm2"], 0)   # nor +-2
        self.assertIsNone(out["pm1"]["tier"])        # both flip rates None
        self.assertIsNone(out["pm2"]["tier"])
        comparable = out["comparable_pm1"] + out["comparable_pm2"]
        axis = {a["axis"]: a for a in m.axis_availability(out["markers"], comparable)}["marker_sensitivity"]
        self.assertFalse(axis["available"])          # NOT a hollow AVAILABLE
        self.assertIn("comparable", axis["blocker"])


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

    def test_core_run_surfaces_identity_limitation(self):
        # the identity collision limitation (finding 6) is loud in the run, not
        # silent: the synthetic corpus has a no-content_id usable lineage.
        path = self._tmp_labels()
        report, _ = m.run(path, resolve_db=False, head="abc123")
        self.assertIn("identity limitation", report)


# --- AWR-205 gold-label intake ---------------------------------------------

def _resolutions():
    """Synthetic resolved lineages (+ one cache_miss) for template/loader/scoring.
    grid on cid:111 lets mm:ss derive; cid:222 has an empty grid (time -> None)."""
    grid = tuple(float(i * 500) for i in range(300))
    return [
        m.Resolution(lineage="cid:111", track="Alpha — Artist", status="resolved",
                     v4=_V4(600), drops=(100, 200), buildups=(), grid=grid),
        m.Resolution(lineage="cid:222", track="Beta — Artist", status="resolved",
                     v4=_V4(600), drops=(50,), buildups=(), grid=()),
        # cache_miss: has a drop but NO v4 — the enumeration guard must skip it.
        m.Resolution(lineage="cid:333", track="Gamma — Artist", status="cache_miss",
                     v4=None, drops=(10,), buildups=(), grid=()),
    ]


def _marker_index(res):
    return {(mk.lineage, mk.beat): mk for mk in m.enumerate_markers(res)}


class GoldTemplateTests(unittest.TestCase):
    def test_one_row_per_resolved_marker_all_null(self):
        res = _resolutions()
        obj = m.build_gold_template(res, "HEAD1", "labsha0")
        # 3 markers (cid:111@100, @200, cid:222@50); cache_miss cid:333 excluded
        self.assertEqual(obj["_header"]["markers"], 3)
        self.assertEqual(obj["_header"]["lineages"], 2)
        self.assertEqual(len(obj["rows"]), 3)
        self.assertNotIn("cid:333", {r["lineage_key"] for r in obj["rows"]})
        for r in obj["rows"]:
            self.assertIsNone(r["is_genuine_drop"])
            d = r["drop"]
            self.assertIsNone(d["tier"])
            self.assertIsNone(d["family"])
            self.assertIsNone(d["laser"])
            self.assertEqual(d["darkness"], {"shape": None, "start_beat": None,
                                             "end_beat": None, "bars": None})
            self.assertEqual(d["growl"], {"start_beat": None, "end_beat": None})

    def test_header_and_mmss_context(self):
        obj = m.build_gold_template(_resolutions(), "HEAD1", "labsha0")
        self.assertEqual(obj["_header"]["head"], "HEAD1")
        self.assertEqual(obj["_header"]["label_sha"], "labsha0")
        self.assertIn("hybrid unit", obj["_header"]["ruling"])
        by_key = {(r["lineage_key"], r["marker_beat"]): r for r in obj["rows"]}
        self.assertEqual(by_key[("cid:111", 100)]["marker_time"], "0:50")  # grid[100]=50000ms
        self.assertIsNone(by_key[("cid:222", 50)]["marker_time"])          # empty grid
        self.assertEqual(by_key[("cid:111", 100)]["content_id"], "111")

    def test_deterministic(self):
        res = _resolutions()
        self.assertEqual(m.build_gold_template(res, "H", "s"),
                         m.build_gold_template(res, "H", "s"))

    def test_overwrite_protection_trips_on_filled_template(self):
        res = _resolutions()
        obj = m.build_gold_template(res, "H", "s")
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        tmp.close()
        # all-null template: writing is allowed (no labels yet)
        m.write_gold_template(obj, tmp.name)
        self.assertFalse(m._template_has_labels(tmp.name))
        # now the file has a real label -> refuse to clobber
        filled = m.build_gold_template(res, "H", "s")
        filled["rows"][0]["is_genuine_drop"] = True
        Path(tmp.name).write_text(json.dumps(filled), encoding="utf-8")
        self.assertTrue(m._template_has_labels(tmp.name))
        with self.assertRaises(ValueError) as ctx:
            m.write_gold_template(obj, tmp.name)
        self.assertIn("refusing to overwrite", str(ctx.exception))


def _valid_gold(res):
    """A schema-valid filled gold over _resolutions(): one genuine, one not, one null."""
    obj = m.build_gold_template(res, "H", "s")
    by_key = {(r["lineage_key"], r["marker_beat"]): r for r in obj["rows"]}
    g = by_key[("cid:111", 100)]
    g["is_genuine_drop"] = True
    g["drop"].update(tier=2, family="WALL", family_matches_track=True,
                     laser="yes", confidence="high", notes="clean wall")
    g["drop"]["darkness"].update(shape="blackout", start_beat=90, end_beat=100, bars=2)
    g["drop"]["growl"] = "none"
    by_key[("cid:111", 200)]["is_genuine_drop"] = False   # ruled a non-drop
    # cid:222@50 stays fully null (unlabeled)
    return obj


class GoldLoaderTests(unittest.TestCase):
    def test_valid_roundtrip_counts_coverage(self):
        res = _resolutions()
        result = m.validate_gold(_valid_gold(res), _marker_index(res))
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["labeled"], 2)          # one true + one false
        self.assertEqual(len(result["genuine_rows"]), 1)

    def test_unknown_row_field_is_hard_error(self):
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][2]["typo_field"] = 1
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("unknown field", str(ctx.exception))

    def test_unknown_drop_field_is_hard_error(self):
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][0]["drop"]["tierr"] = 3
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("drop unknown field", str(ctx.exception))

    def test_unmatched_provenance_names_the_row(self):
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][0]["marker_beat"] = 999   # no cid:111@999 marker exists
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        msg = str(ctx.exception)
        self.assertIn("no currently-enumerable marker", msg)
        self.assertIn("cid:111", msg)   # the offending row is named by provenance

    def test_null_is_genuine_drop_excluded_but_counted(self):
        res = _resolutions()
        obj = m.build_gold_template(res, "H", "s")   # all null
        result = m.validate_gold(obj, _marker_index(res))
        self.assertEqual(result["labeled"], 0)       # nothing ruled
        self.assertEqual(result["total"], 3)         # still counted in coverage
        self.assertEqual(result["genuine_rows"], [])

    def test_invalid_enum_is_hard_error(self):
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][0]["drop"]["tier"] = 5
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("tier must be", str(ctx.exception))

    def test_invalid_beat_range_is_hard_error(self):
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][0]["drop"]["darkness"].update(start_beat=100, end_beat=90)
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("start_beat", str(ctx.exception))

    def test_bad_is_genuine_drop_value_is_hard_error(self):
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][2]["is_genuine_drop"] = "yes"   # must be true/false/null
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("is_genuine_drop must be", str(ctx.exception))

    def test_bool_tier_is_hard_error(self):
        # True == 1 in Python, so a bare membership test would accept tier:true as
        # tier 1 and silently score it. It must be a HARD error (fail closed).
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][0]["drop"]["tier"] = True
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("tier must be", str(ctx.exception))

    def test_int_is_genuine_drop_is_hard_error(self):
        # 1 == True, so `1 in (None, True, False)` is True; without a type guard a
        # `1` would be counted as labeled yet dropped from scoring. Must be rejected.
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][2]["is_genuine_drop"] = 1
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("is_genuine_drop must be", str(ctx.exception))

    def test_int_family_matches_track_is_hard_error(self):
        # same bool/int aliasing on family_matches_track: reject int 1/0.
        res = _resolutions()
        obj = _valid_gold(res)
        obj["rows"][0]["drop"]["family_matches_track"] = 1
        with self.assertRaises(ValueError) as ctx:
            m.validate_gold(obj, _marker_index(res))
        self.assertIn("family_matches_track must be", str(ctx.exception))

    def test_unknown_still_valid_on_genuine_drop(self):
        res = _resolutions()
        obj = m.build_gold_template(res, "H", "s")
        by_key = {(r["lineage_key"], r["marker_beat"]): r for r in obj["rows"]}
        g = by_key[("cid:111", 100)]
        g["is_genuine_drop"] = True
        g["drop"].update(tier="unknown", family="unknown", family_matches_track="unknown",
                         laser="unknown")
        m.validate_gold(obj, _marker_index(res))   # must not raise


# deterministic per-beat model for scoring: cid:111@100 -> WALL/T3, @200 -> HOUSE/T1,
# cid:222@50 -> COMET/T2. Any unknown beat -> NEUTRAL/T1.
def _scoring_plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
    table = {100: ("WALL", 3, "blackout", 4), 200: ("HOUSE", 1, "snap", 0),
             50: ("COMET", 2, "dip", 2)}
    return _Plan([_Entry(d, _Dec(*table.get(d, ("NEUTRAL", 1, "snap", 0)))) for d in drops])


class GoldScoringAvailabilityTests(unittest.TestCase):
    def _gold_two_examples(self, res):
        obj = m.build_gold_template(res, "H", "s")
        by_key = {(r["lineage_key"], r["marker_beat"]): r for r in obj["rows"]}
        # genuine, model AGREES on tier+family
        a = by_key[("cid:111", 100)]
        a["is_genuine_drop"] = True
        a["drop"].update(tier=3, family="WALL", family_matches_track=True, laser="yes")
        # genuine, model DISAGREES (gold T2/COMET, model T1/HOUSE)
        b = by_key[("cid:111", 200)]
        b["is_genuine_drop"] = True
        b["drop"].update(tier=2, family="COMET", family_matches_track=False, laser="no")
        return obj

    def test_tier_family_available_others_unavailable(self):
        res = _resolutions()
        gold = m.validate_gold(self._gold_two_examples(res), _marker_index(res))
        scores = m.score_accuracy_axes(gold, res, _scoring_plan_fn)
        self.assertTrue(scores["tier"]["available"])
        self.assertEqual(scores["tier"]["gold_examples"], 2)
        self.assertEqual(scores["tier"]["score"]["exact"], 1)      # 100 agrees, 200 flips
        self.assertTrue(scores["family"]["available"])
        self.assertEqual(scores["family"]["score"]["correct"], 1)  # WALL agrees, COMET!=HOUSE
        for axis in ("darkness", "growl", "laser", "drop_classification"):
            self.assertFalse(scores[axis]["available"])
            self.assertTrue(scores[axis]["blocker"])

    def test_axis_availability_reflects_scores_and_stays_partial(self):
        res = _resolutions()
        gold = m.validate_gold(self._gold_two_examples(res), _marker_index(res))
        scores = m.score_accuracy_axes(gold, res, _scoring_plan_fn)
        avail = {a["axis"]: a for a in m.axis_availability(7, 5, accuracy_scores=scores)}
        self.assertTrue(avail["tier"]["available"])
        self.assertTrue(avail["family"]["available"])
        self.assertFalse(avail["darkness"]["available"])
        self.assertIn("drop_classification", avail)
        self.assertFalse(avail["drop_classification"]["available"])
        # tier+family available but darkness/growl/laser are not -> still PARTIAL
        self.assertTrue(m.is_partial(m.axis_availability(7, 5, accuracy_scores=scores)))

    def test_gold_present_but_no_scorable_example_reads_unavailable(self):
        res = _resolutions()
        obj = m.build_gold_template(res, "H", "s")
        by_key = {(r["lineage_key"], r["marker_beat"]): r for r in obj["rows"]}
        g = by_key[("cid:111", 100)]
        g["is_genuine_drop"] = True
        g["drop"].update(tier="unknown", family="unknown", family_matches_track="unknown",
                         laser="unknown")
        gold = m.validate_gold(obj, _marker_index(res))
        scores = m.score_accuracy_axes(gold, res, _scoring_plan_fn)
        self.assertFalse(scores["tier"]["available"])      # only 'unknown' tier -> 0 examples
        self.assertIn("no genuine-drop tier example", scores["tier"]["blocker"])
        self.assertFalse(scores["family"]["available"])

    def test_no_model_decision_at_marker_is_not_comparable(self):
        res = _resolutions()
        gold = m.validate_gold(self._gold_two_examples(res), _marker_index(res))

        def empty_plan(v4, drops, buildups, *, beatgrid_times_ms=()):
            return _Plan([])   # for_drop returns None -> no model output anywhere

        scores = m.score_accuracy_axes(gold, res, empty_plan)
        self.assertFalse(scores["tier"]["available"])      # nothing comparable
        self.assertEqual(scores["tier"]["gold_examples"], 0)

    def test_no_gold_leaves_existing_behavior_unchanged(self):
        # accuracy_scores=None -> the 5 accuracy axes stay UNAVAILABLE with the
        # free-text-labels blocker, exactly as before AWR-205.
        axes = {a["axis"]: a for a in m.axis_availability(None)}
        self.assertNotIn("drop_classification", axes)
        for name in ("tier", "family", "darkness", "growl", "laser"):
            self.assertFalse(axes[name]["available"])
            self.assertIn("curation pass", axes[name]["blocker"])


class GoldLeakTests(unittest.TestCase):
    def test_gold_field_cannot_reach_planner(self):
        # positive allowlist: a gold field in model inputs is rejected at the boundary
        with self.assertRaises(ValueError):
            m.call_planner(lambda *a, **k: "P",
                           {"v4": object(), "drops": [], "buildups": [],
                            "beatgrid_times_ms": [], "is_genuine_drop": True})

    def test_assert_no_leak_rejects_smuggled_gold_field(self):
        with self.assertRaises(ValueError):
            m.assert_no_leak({"v4": object(), "is_genuine_drop": True})
        with self.assertRaises(ValueError):
            m.assert_no_leak({"v4": object(), "drop": {"tier": 3}})

    def test_scorer_only_ever_sends_model_inputs_to_planner(self):
        res = _resolutions()
        obj = m.build_gold_template(res, "H", "s")
        by_key = {(r["lineage_key"], r["marker_beat"]): r for r in obj["rows"]}
        g = by_key[("cid:111", 100)]
        g["is_genuine_drop"] = True
        g["drop"].update(tier=3, family="WALL", family_matches_track=True, laser="yes")
        gold = m.validate_gold(obj, _marker_index(res))
        calls = []

        def plan_fn(v4, drops, buildups, *, beatgrid_times_ms=()):
            calls.append({"v4": v4, "drops": list(drops), "buildups": list(buildups)})
            return _Plan([_Entry(d, _Dec("WALL", 3, "blackout", 4)) for d in drops])

        m.score_accuracy_axes(gold, res, plan_fn)
        self.assertTrue(calls)
        for c in calls:
            self.assertEqual(set(c) & m.LEAK_FORBIDDEN_FIELDS, set())


if __name__ == "__main__":
    unittest.main()
