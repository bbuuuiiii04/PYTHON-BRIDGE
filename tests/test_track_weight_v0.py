"""Tests for the offline library track-weight descriptor (track_weight_v0) and the
report tool's pure store seam. Covers gain-invariance (uniform + per-track shift),
Spearman (monotone/reversed/ties/constant/short), rank_in, component guards,
degenerate detection, the acceptance verdict's four outcomes, store round-trip,
and the static zero-runtime-importer invariant.
"""
import ast
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # /Users/bbui

from rb_ss_bridge_v2 import track_weight_v0  # noqa: E402
from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2.track_weight_v0 import (  # noqa: E402
    COMPONENT_KEYS,
    MIN_BEATS,
    acceptance_verdict,
    build_distribution,
    components,
    degenerate_components,
    rank_in,
    robust_dynamic_range,
    spearman,
    track_weight,
)
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION_V4,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
import track_weight_report as twr  # noqa: E402


def _p95(xs):
    return track_weight_v0._percentile(sorted(xs), 95)


def _mk(n_beats=64, full=None, sub=None, onset_mean=2.0, flat_mean=0.15,
        ref="auto"):
    z = tuple(0.0 for _ in range(n_beats))
    if full is None:
        full = tuple(-6.0 + 0.15 * i for i in range(n_beats))
    if sub is None:
        sub = tuple(-4.0 + 0.10 * i for i in range(n_beats))
    series = {k: z for k in V4_SERIES_KEYS}
    series.update({"full_db": tuple(full), "sub_db": tuple(sub),
                   "onset_density_midhigh": tuple(onset_mean for _ in range(n_beats)),
                   "growl_flatness": tuple(flat_mean for _ in range(n_beats))})
    scalars = {k: 0.5 for k in V4_SCALAR_KEYS}
    if ref == "auto":
        scalars["loudness_ref_db"] = _p95(full)
    elif ref is None:
        del scalars["loudness_ref_db"]
    else:
        scalars["loudness_ref_db"] = ref
    return SpectralFeaturesV4(
        sr=22050, schema_version=SCHEMA_VERSION_V4, n_beats=n_beats,
        duration_s=n_beats * 0.5, frame_hop_s=0.0232,
        sub_bass_envelope=z, kick_envelope=z, low_mid_envelope=z,
        high_mid_envelope=z, high_band_envelope=z, kick_max_envelope=z,
        onset_strength_envelope=z, spectral_flatness_envelope=z,
        series=series,
        sub4={k: tuple((0.0, 0.0, 0.0, 0.0) for _ in range(n_beats))
              for k in V4_SUB4_KEYS},
        growl_band_frames=(0.0, 1.0), scalars=scalars)


def shifted(v4, delta_db):
    """Uniform per-track dB offset: every *_db series shifts by delta_db and
    loudness_ref_db is recomputed as p95(shifted full_db); count/ratio untouched."""
    series = {k: (tuple(x + delta_db for x in v) if k.endswith("_db") else v)
              for k, v in v4.series.items()}
    scalars = dict(v4.scalars)
    scalars["loudness_ref_db"] = _p95(series["full_db"])
    return replace(v4, series=series, scalars=scalars)


class GainInvarianceTests(unittest.TestCase):
    def test_uniform_shift_is_exact(self):
        v4 = _mk()
        base = components(v4)
        self.assertIsNotNone(base)
        for d in (6.0, -6.0):
            c = components(shifted(v4, d))
            self.assertIsNotNone(c)
            for k in COMPONENT_KEYS:
                self.assertAlmostEqual(base[k], c[k], places=9, msg="%s d=%s" % (k, d))

    def test_per_track_shift_preserves_weight(self):
        lib = [_mk(onset_mean=float(i + 1), flat_mean=0.1 + 0.02 * i,
                   full=tuple(-6.0 + (0.10 + 0.01 * i) * b for b in range(64)))
               for i in range(5)]
        comps = [components(v) for v in lib]
        self.assertTrue(all(c is not None for c in comps))
        dist = build_distribution(comps)
        w_before = track_weight(comps[2], dist)
        for d in (6.0, -6.0):
            c2 = components(shifted(lib[2], d))
            for k in COMPONENT_KEYS:
                self.assertAlmostEqual(comps[2][k], c2[k], places=9)
            self.assertAlmostEqual(track_weight(c2, dist), w_before, places=9)

    def test_uniform_shift_rounded_within_tolerance(self):
        # The honest tolerance (A.4 item 3): the real pipeline rounds every stored
        # dB value to 0.1 dP, so exact places=9 cannot hold end-to-end. Round the
        # shifted series to 1 dP and recompute; components must stay within 0.01.
        full = tuple((-1.0 if i < 32 else -15.0) for i in range(64))  # far from thr
        v4 = _mk(full=full)
        base = components(v4)
        for d in (6.0, -6.0):
            sv = shifted(v4, d)
            series = {k: (tuple(round(x, 1) for x in v) if k.endswith("_db") else v)
                      for k, v in sv.series.items()}
            scalars = dict(sv.scalars)
            scalars["loudness_ref_db"] = round(_p95(series["full_db"]), 1)
            c = components(replace(sv, series=series, scalars=scalars))
            for k in COMPONENT_KEYS:
                self.assertLessEqual(abs(base[k] - c[k]), 0.01,
                                     msg="%s d=%s" % (k, d))


class SpearmanTests(unittest.TestCase):
    def test_monotone_reversed_constant_short(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0, places=9)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0, places=9)
        self.assertIsNone(spearman([1, 1, 1], [1, 2, 3]))       # constant xs
        self.assertIsNone(spearman([1, 2], [3, 4]))             # len < 3
        self.assertIsNone(spearman([1, 2, 3], [1, 2]))          # length mismatch

    def test_ties_hand_computed(self):
        # xs=[1,2,2,3] -> mid-ranks [1,2.5,2.5,4]; ys=[4,4,5,6] -> [1.5,1.5,3,4];
        # Pearson on ranks = 3.75 / 4.5 = 0.83333...
        self.assertAlmostEqual(spearman([1, 2, 2, 3], [4, 4, 5, 6]),
                               3.75 / 4.5, places=9)


class RankInTests(unittest.TestCase):
    def test_midrank_on_ties(self):
        self.assertAlmostEqual(rank_in([1, 2, 2, 3], 2), (1 + 0.5 * 2) / 4, places=12)
        self.assertAlmostEqual(rank_in([1, 2, 3], 1), 0.5 / 3, places=12)

    def test_empty_distribution_raises(self):
        with self.assertRaises(ValueError):
            rank_in([], 0.5)


class ComponentGuardTests(unittest.TestCase):
    def test_missing_loudness_ref_returns_none(self):
        self.assertIsNone(components(_mk(ref=None)))

    def test_short_track_returns_none(self):
        self.assertIsNone(components(_mk(n_beats=MIN_BEATS - 1)))

    def test_nonfinite_returns_none_never_a_number(self):
        bad = list(-6.0 + 0.15 * i for i in range(64))
        bad[10] = float("nan")
        self.assertIsNone(components(_mk(full=bad)))

    def test_components_have_brightness_not_sub_duty(self):
        c = components(_mk())
        self.assertIn("brightness_med", c)
        self.assertNotIn("sub_duty", c)

    def _with_scalar(self, **over):
        v = _mk()
        scalars = dict(v.scalars)
        scalars.update(over)
        return replace(v, scalars=scalars)

    def test_missing_brightness_returns_none(self):
        v = _mk()
        scalars = {k: val for k, val in v.scalars.items() if k != "brightness_med"}
        self.assertIsNone(components(replace(v, scalars=scalars)))

    def test_nonnumeric_brightness_returns_none(self):
        self.assertIsNone(components(self._with_scalar(brightness_med="loud")))

    def test_nonfinite_brightness_returns_none(self):
        self.assertIsNone(components(self._with_scalar(brightness_med=float("inf"))))


class RobustDynamicRangeTests(unittest.TestCase):
    def test_exact_p95_minus_p25(self):
        full = tuple(float(i) for i in range(64))       # 0..63
        v4 = _mk(full=full)
        ordered = sorted(full)
        expect = _p95(full) - track_weight_v0._percentile(ordered, 25)
        self.assertAlmostEqual(robust_dynamic_range(v4), expect, places=9)

    def test_short_absent_nonfinite_none(self):
        self.assertIsNone(robust_dynamic_range(_mk(n_beats=MIN_BEATS - 1)))
        bad = list(float(i) for i in range(64))
        bad[3] = float("nan")
        self.assertIsNone(robust_dynamic_range(_mk(full=bad)))


class DegenerateTests(unittest.TestCase):
    def test_flat_component_flagged_healthy_not(self):
        # body_duty constant across the library, the others varied.
        comps = [{"body_duty": 0.5, "brightness_med": 100.0 * i,
                  "onset_mh_mean": float(i), "growl_flatness_mean": 0.05 * i}
                 for i in range(5)]
        dist = build_distribution(comps)
        self.assertIn("body_duty", degenerate_components(dist))
        self.assertNotIn("brightness_med", degenerate_components(dist))

    def test_healthy_distribution_none_degenerate(self):
        comps = [{k: 0.1 * i + 0.01 * j for j, k in enumerate(COMPONENT_KEYS)}
                 for i in range(6)]
        self.assertEqual(degenerate_components(build_distribution(comps)), [])


class AcceptanceVerdictTests(unittest.TestCase):
    def test_precedence_every_branch(self):
        # signature: (n_by_genre, rho, rho_drama, rho_components_max, degenerate)
        self.assertEqual(acceptance_verdict(50, 0.1, 0.1, 0.1, []),
                         (False, "insufficient_corpus"))
        self.assertEqual(acceptance_verdict(120, 0.6, 0.1, 0.1, []),
                         (False, "loudness_proxy"))
        self.assertEqual(acceptance_verdict(120, None, 0.1, 0.1, []),
                         (False, "loudness_proxy"))
        # the compression_proxy branch is GONE (E1SCRAMBLE demotion, Task 4b): a
        # drama value over the old 0.55 ceiling, and a None drama, both now fall
        # through to the next control instead of failing.
        self.assertEqual(acceptance_verdict(120, 0.3, 0.7, 0.1, []), (True, "ok"))
        self.assertEqual(acceptance_verdict(120, 0.3, None, 0.1, []), (True, "ok"))
        self.assertEqual(acceptance_verdict(120, 0.3, 0.4, 0.7, []),
                         (False, "redundant_components"))
        self.assertEqual(acceptance_verdict(120, 0.3, 0.4, None, []),
                         (False, "redundant_components"))        # None fails closed
        self.assertEqual(acceptance_verdict(120, 0.3, 0.4, 0.2, ["body_duty"]),
                         (False, "degenerate_component"))
        self.assertEqual(acceptance_verdict(120, 0.3, 0.4, 0.2, []), (True, "ok"))
        self.assertEqual(acceptance_verdict(120, -0.50, -0.55, 0.60, []),
                         (True, "ok"))                           # all boundaries

    def test_verdict_does_not_read_the_drama_input(self):
        """Task 4b (§5 drama-gate demotion): `rho_drama` is accepted-and-ignored — the
        parameter STAYS in the signature so no caller changes, but the verdict must be
        identical for None / 0.0 / 0.99. RED before the demotion (today's code returned
        (False, 'compression_proxy') at 0.99 and at None), green after."""
        base = dict(n_by_genre=200, rho=0.2, rho_components_max=0.3, degenerate=[])
        verdicts = {acceptance_verdict(rho_drama=d, **base)
                    for d in (None, 0.0, 0.99, -0.99, 1.0)}
        self.assertEqual(verdicts, {(True, "ok")},
                         "the verdict still depends on rho_drama: %r" % (verdicts,))
        # and it is ignored on a FAILING path too — the reason must come from the
        # surviving controls, never from the drama value.
        self.assertEqual(
            {acceptance_verdict(n_by_genre=200, rho=0.9, rho_drama=d,
                                rho_components_max=0.3, degenerate=[])
             for d in (None, 0.0, 0.99)},
            {(False, "loudness_proxy")})

    def test_drama_constant_stays_as_a_printed_reference(self):
        """`DRAMA_ACCEPT_MAX` stays in the module as the diagnostic's reference ceiling
        (spec 4b: it is not deleted, it stops deciding). Its VALUE is still pinned."""
        self.assertEqual(track_weight_v0.DRAMA_ACCEPT_MAX, 0.55)


class SchemaSkewTests(unittest.TestCase):
    def test_e1_and_e2_schema_agree(self):        # EREV1 N5: two literals, no skew
        self.assertEqual(track_weight_v0.STORE_SCHEMA_VERSION,
                         section_energy_v0.STORE_SCHEMA_VERSION)


class StoreRoundTripTests(unittest.TestCase):
    def test_build_and_write_store(self):
        scored = [
            {"cache_key": "k1", "filepath": "/a.mp3", "content_id": "1",
             "title": "T1", "components": {k: 0.2 for k in COMPONENT_KEYS},
             "track_weight": 0.4},
            {"cache_key": "k2", "filepath": "/b.mp3", "content_id": "2",
             "title": "T2", "components": {k: 0.8 for k in COMPONENT_KEYS},
             "track_weight": 0.6}]
        dist = build_distribution([r["components"] for r in scored])
        acc = {"accepted": True, "reason": "ok", "rho_by_genre": 0.2,
               "n_by_genre": 123, "rho_library": 0.25, "rho_drama": -0.48,
               "rho_components_max": 0.24, "degenerate": []}
        store = twr.build_store(scored, dist, acc, 1234567,
                                drop_body_levels_by_genre=[-3.0, -1.0, 0.0])
        with tempfile.TemporaryDirectory() as td:
            path = twr.write_store(store, Path(td))
            self.assertTrue(path.exists())
            re = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(re["schema_version"], 2)               # AWR-291 bump
        self.assertEqual(set(re["tracks"]), {"k1", "k2"})
        self.assertIs(re["accepted"], True)
        self.assertEqual(re["acceptance"]["threshold"], 0.5)
        self.assertEqual(re["acceptance"]["n_by_genre"], 123)
        self.assertEqual(sorted(re["distribution"]), sorted(COMPONENT_KEYS))
        self.assertEqual(re["drop_body_distribution"], [-3.0, -1.0, 0.0])
        self.assertEqual(re["tracks"]["k1"]["title"], "T1")


# --------------------------------------------------------------------------- #
# Zero-runtime-importer guard (verbatim pattern from tests/test_hardness_v0.py) #
# --------------------------------------------------------------------------- #
def _imports_track_weight_v0(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "track_weight_v0" in text
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "track_weight_v0" in node.module:
                return True
            if any("track_weight_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any("track_weight_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if fname in ("import_module", "__import__"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and "track_weight_v0" in arg.value:
                        return True
    return False


class ZeroRuntimeImporterTests(unittest.TestCase):
    """Only tools/ and tests/ may import track_weight_v0 — enforced forever."""

    # "local" = the gitignored scratch/venv tree (never repo code); skipping it
    # avoids non-utf8 third-party fixtures and cuts the scan to ~1.5s (was ~75s;
    # not sub-second — the rglob walk over local/ is the floor). E1 review O1.
    SKIP_DIRS = {".git", "graphify-out", "__pycache__", "node_modules", "build",
                 "dist", "local"}

    def test_no_runtime_module_imports_track_weight_v0(self):
        importers = []
        for path in REPO_ROOT.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in self.SKIP_DIRS or part.startswith(".")
                   for part in rel.split("/")):
                continue
            if rel == "track_weight_v0.py":
                continue
            try:
                # errors="replace" keeps a non-utf8 file IN SCOPE (it can't
                # match an ASCII import path, but the invariant should still see
                # it) while OSError still skips a genuinely unreadable file —
                # matching the elder test_approach_features_v0.py sibling (O2).
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _imports_track_weight_v0(text):
                importers.append(rel)
        offenders = [r for r in importers
                     if not (r.startswith("tools/") or r.startswith("tests/"))]
        self.assertEqual(offenders, [],
                         "track_weight_v0 imported by non-tools/tests: %s" % offenders)

    def test_import_form_detector(self):
        self.assertTrue(_imports_track_weight_v0(
            "from rb_ss_bridge_v2.track_weight_v0 import components"))
        self.assertTrue(_imports_track_weight_v0("import track_weight_v0"))
        self.assertTrue(_imports_track_weight_v0(
            "importlib.import_module('track_weight_v0')"))
        self.assertFalse(_imports_track_weight_v0("import spectral_cache"))


if __name__ == "__main__":
    unittest.main()
