"""Tests for the offline intrinsic-hardness shadow descriptor (hardness_v0).

Smallest strong coverage: term math + clipping, 8+8 landed halves and
short/end-of-track boundaries, deterministic reducer/tie-break behavior, path
math + winning-path diagnostics, track median + MIN_STABLE_DROPS, marker-shift
range, malformed/empty -> no result (never a phantom T3), and the static
zero-runtime-importer invariant.
"""
import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import hardness_v0  # noqa: E402
from rb_ss_bridge_v2.hardness_v0 import (  # noqa: E402
    ANCHORS,
    HardnessResult,
    PATH_THRESHOLDS,
    TrackBaseline,
    _abrasion_term,
    _body_term,
    _growl_duty_term,
    _local_terms_at,
    _onset_term,
    _paths,
    _select_offset,
    hardness_result,
    track_baseline,
)
from rb_ss_bridge_v2.spectral_profile import percentile  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION_V4,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# neutral defaults: full_db/high_db mid, growl/onset absent
_DEFAULT_SERIES = {
    "full_db": 15.0,
    "high_db": -1.0,
    "growl_band_db": 0.0,
    "growl_flatness": 0.0,
    "onset_density_midhigh": 0.0,
}


def _ns(overrides=None, n_beats=16):
    """A duck-typed v4 (hardness_v0 reads only .n_beats and .series[key])."""
    ov = dict(overrides or {})
    series = {}
    for key in V4_SERIES_KEYS:
        base = _DEFAULT_SERIES.get(key, 0.0)
        val = ov.get(key, base)
        if isinstance(val, (list, tuple)):
            series[key] = tuple(float(v) for v in val)
        else:
            series[key] = tuple(float(val) for _ in range(n_beats))
    return SimpleNamespace(n_beats=n_beats, series=series)


def _real_v4(overrides=None, n_beats=16):
    """A genuine frozen SpectralFeaturesV4 (guards against dataclass drift)."""
    ov = dict(overrides or {})
    beats = tuple(0.0 for _ in range(n_beats))
    series = {}
    for key in V4_SERIES_KEYS:
        val = ov.get(key, _DEFAULT_SERIES.get(key, 0.0))
        series[key] = (
            tuple(float(v) for v in val)
            if isinstance(val, (list, tuple))
            else tuple(float(val) for _ in range(n_beats))
        )
    sub4 = {key: tuple((0.0, 0.0, 0.0, 0.0) for _ in range(n_beats)) for key in V4_SUB4_KEYS}
    scalars = {key: 0.0 for key in V4_SCALAR_KEYS}
    return SpectralFeaturesV4(
        sr=22050,
        schema_version=SCHEMA_VERSION_V4,
        n_beats=n_beats,
        duration_s=float(n_beats),
        frame_hop_s=0.02,
        sub_bass_envelope=beats,
        kick_envelope=beats,
        low_mid_envelope=beats,
        high_mid_envelope=beats,
        high_band_envelope=beats,
        kick_max_envelope=beats,
        onset_strength_envelope=beats,
        spectral_flatness_envelope=beats,
        series=series,
        sub4=sub4,
        growl_band_frames=(),
        scalars=scalars,
        growl_centroid_frames=(),
    )


class TermMathTests(unittest.TestCase):
    def test_body_anchors_and_clipping(self):
        self.assertAlmostEqual(_body_term([ANCHORS[0]] * 8), 0.0)            # low anchor -> 0
        self.assertAlmostEqual(_body_term([ANCHORS[0] + ANCHORS[1]] * 8), 1.0)  # high -> 1
        self.assertAlmostEqual(_body_term([ANCHORS[0] + ANCHORS[1] / 2] * 8), 0.5)
        self.assertAlmostEqual(_body_term([0.0] * 8), 0.0)                   # clips below
        self.assertAlmostEqual(_body_term([99.0] * 8), 1.0)                  # clips above

    def test_abrasion_anchors(self):
        self.assertAlmostEqual(_abrasion_term([ANCHORS[2]] * 8), 0.0)
        self.assertAlmostEqual(_abrasion_term([ANCHORS[2] + ANCHORS[3]] * 8), 1.0)
        self.assertAlmostEqual(_abrasion_term([ANCHORS[2] + ANCHORS[3] / 2] * 8), 0.5)

    def test_growl_duty_is_per_beat_product_mean(self):
        # full duty: db and flatness both at their high anchors
        self.assertAlmostEqual(
            _growl_duty_term([ANCHORS[4] + ANCHORS[5]] * 8, [ANCHORS[6] + ANCHORS[7]] * 8), 1.0
        )
        # half in each factor -> 0.25 product
        self.assertAlmostEqual(
            _growl_duty_term([ANCHORS[4] + ANCHORS[5] / 2] * 8, [ANCHORS[6] + ANCHORS[7] / 2] * 8),
            0.25,
        )
        self.assertAlmostEqual(_growl_duty_term([], []), 0.0)               # empty -> 0

    def test_onset_anchors(self):
        self.assertAlmostEqual(_onset_term([ANCHORS[8]] * 8), 0.0)
        self.assertAlmostEqual(_onset_term([ANCHORS[8] + ANCHORS[9]] * 8), 1.0)
        self.assertAlmostEqual(_onset_term([]), 0.0)


class WindowTests(unittest.TestCase):
    def test_first8_and_following8_are_averaged(self):
        # first 8 beats hit body=1.0, following 8 hit body=0.0 -> average 0.5
        full = [ANCHORS[0] + ANCHORS[1]] * 8 + [ANCHORS[0]] * 8
        v4 = _ns({"full_db": full}, n_beats=16)
        l_b = _local_terms_at(v4, 0, 16)[0]
        expected = (
            _body_term(tuple(full[0:8])) + _body_term(tuple(full[8:16]))
        ) / 2.0
        self.assertAlmostEqual(l_b, expected)
        self.assertAlmostEqual(l_b, 0.5)

    def test_end_of_track_clamps_to_at_least_one_beat(self):
        v4 = _ns({"full_db": [ANCHORS[0] + ANCHORS[1]] * 10}, n_beats=10)
        # drop at the last beat: both halves clamp to the final beat, no crash/empty
        terms = _local_terms_at(v4, 9, 10)
        self.assertAlmostEqual(terms[0], 1.0)

    def test_short_track_following_half_uses_remaining_beats(self):
        full = [15.6] * 8 + [17.5, 17.5]  # first half B=0.5, following half (2 beats) B=1.0
        v4 = _ns({"full_db": full}, n_beats=10)
        l_b = _local_terms_at(v4, 0, 10)[0]
        first = _body_term(tuple(full[0:8]))
        following = _body_term(tuple(full[8:10]))
        self.assertAlmostEqual(l_b, (first + following) / 2.0)


class SelectorTests(unittest.TestCase):
    def _entries(self, scores):
        # (offset, terms, score); terms carry the score in slot 0 for tracing
        return [(off, (sc, 0.0, 0.0, 0.0), sc) for off, sc in scores]

    def test_ranks_pick_expected_offsets(self):
        entries = self._entries([(-2, 0.1), (-1, 0.2), (0, 0.3), (1, 0.4), (2, 0.5)])
        self.assertEqual(_select_offset(entries, "center")[0], 0)
        self.assertEqual(_select_offset(entries, "max")[0], 2)      # top score
        self.assertEqual(_select_offset(entries, "q75")[0], 1)      # index 3 of 5 sorted
        self.assertEqual(_select_offset(entries, "median")[0], 0)   # index 2 of 5 sorted

    def test_tie_break_prefers_smaller_abs_offset(self):
        # all tied -> max picks offset 0 (least alignment cheating)
        entries = self._entries([(-2, 0.5), (-1, 0.5), (0, 0.5), (1, 0.5), (2, 0.5)])
        self.assertEqual(_select_offset(entries, "max")[0], 0)

    def test_tie_break_at_same_abs_prefers_negative(self):
        entries = self._entries([(-2, 0.1), (-1, 0.9), (0, 0.2), (1, 0.9), (2, 0.1)])
        self.assertEqual(_select_offset(entries, "max")[0], -1)  # -1 vs +1 tie -> -1

    def test_unknown_reducer_raises(self):
        with self.assertRaises(ValueError):
            _select_offset(self._entries([(0, 0.5)]), "p50")


class ReducerOrderingTests(unittest.TestCase):
    def test_reducers_are_ordered_and_deterministic(self):
        # Reducers rank the 5 offsets by the COMPOSITE align score
        # (0.40B+0.25A+0.20R+0.15N) -- max=top rank, q75=index 3, median=index 2,
        # center=offset 0. The ordered quantity is that composite, NOT any single
        # term (on multi-term data L_B need not track it). full_db rises with beat
        # index so the composite strictly increases with the center offset here.
        full = [10.0 + 0.5 * i for i in range(32)]
        v4 = _ns({"full_db": full}, n_beats=32)
        drops = list(range(6, 26, 4))  # 5 genuine drops for a stable baseline
        score = {}
        offsets = {}
        for reducer in ("center", "median", "q75", "max"):
            base = track_baseline(v4, drops, reducer=reducer)
            res = hardness_result(v4, 8, base, reducer=reducer)
            score[reducer] = hardness_v0._align_score(res.local_terms)  # the ranked quantity
            offsets[reducer] = res.winning_offset
        self.assertGreaterEqual(score["max"], score["q75"])
        self.assertGreaterEqual(score["q75"], score["median"])
        self.assertGreaterEqual(score["median"], score["center"])
        self.assertGreater(score["max"], score["center"])  # the knob does something
        self.assertEqual(offsets["center"], 0)
        self.assertEqual(offsets["max"], 2)
        self.assertEqual(offsets["q75"], 1)

    def test_constant_series_ties_pick_offset_zero(self):
        v4 = _ns({"full_db": [17.5] * 16}, n_beats=16)
        base = track_baseline(v4, [0, 4, 8], reducer="max")
        res = hardness_result(v4, 4, base, reducer="max")
        self.assertEqual(res.winning_offset, 0)


class PathMathTests(unittest.TestCase):
    def test_repeated_wall_uses_only_track_terms(self):
        # two different local tuples, same track terms -> identical repeated_wall
        t = (1.0, 1.0, 0.0, 0.0)
        a = _paths((0.1, 0.1, 0.1, 0.1), t)[0]
        b = _paths((0.9, 0.9, 0.9, 0.9), t)[0]
        self.assertAlmostEqual(a, b)
        self.assertAlmostEqual(a, min(1.0 / PATH_THRESHOLDS[0], 1.0 / PATH_THRESHOLDS[1]))

    def test_h_ge_one_iff_a_path_fires(self):
        # repeated_wall fires (T_B, T_A high), others do not
        base = TrackBaseline(1.0, 1.0, 0.0, 0.0, 8, True, "max")
        v4 = _ns({"high_db": [-50.0] * 16}, n_beats=16)  # kill local abrasion
        res = hardness_result(v4, 4, base, reducer="max")
        self.assertTrue(res.t3)
        self.assertGreaterEqual(res.h, 1.0)
        self.assertEqual(res.winning_path, "repeated_wall")
        # nothing fires -> no phantom T3
        weak = TrackBaseline(0.1, 0.1, 0.1, 0.1, 8, True, "max")
        res2 = hardness_result(v4, 4, weak, reducer="max")
        self.assertFalse(res2.t3)
        self.assertLess(res2.h, 1.0)

    def test_winning_path_is_argmax_of_the_three(self):
        rw, ab, gr = _paths((0.9, 0.9, 0.9, 0.9), (1.0, 1.0, 1.0, 1.0))
        # abrasive should win on a saturated wall (documents the workhorse path)
        self.assertGreater(ab, rw)


class MarkerShiftTests(unittest.TestCase):
    def test_repeated_wall_win_is_offset_invariant(self):
        # hard track median (high T_B/T_A) but this drop's local A is dead and
        # local B varies across offsets -> repeated_wall (track-only) wins and H
        # is identical across marker-2..marker+2 (the per-track stamp arithmetic).
        base = TrackBaseline(1.0, 1.0, 0.0, 0.0, 8, True, "max")
        full = [10.0 + 0.5 * i for i in range(32)]  # L_B varies with offset
        v4 = _ns({"full_db": full, "high_db": [-50.0] * 32}, n_beats=32)
        res = hardness_result(v4, 12, base, reducer="max")
        self.assertEqual(res.winning_path, "repeated_wall")
        lo, hi = res.marker_shift_range
        self.assertAlmostEqual(lo, hi)          # offset-invariant
        self.assertAlmostEqual(res.h, hi)

    def test_marker_shift_range_brackets_h(self):
        full = [10.0 + 0.5 * i for i in range(32)]
        v4 = _ns({"full_db": full}, n_beats=32)
        base = track_baseline(v4, list(range(6, 26, 4)), reducer="max")
        res = hardness_result(v4, 12, base, reducer="max")
        lo, hi = res.marker_shift_range
        self.assertLessEqual(lo, res.h + 1e-9)
        self.assertGreaterEqual(hi, res.h - 1e-9)


class TrackBaselineTests(unittest.TestCase):
    def test_median_over_drops(self):
        # build a track whose per-drop L_B differs; T_B is their median
        full = [15.6] * 40  # constant -> L_B = 0.5 at every drop
        v4 = _ns({"full_db": full}, n_beats=40)
        base = track_baseline(v4, [0, 8, 16, 24, 32], reducer="max")
        self.assertAlmostEqual(base.t_body, 0.5, places=3)
        self.assertEqual(base.n_drops, 5)

    def test_min_stable_drops_flag(self):
        v4 = _ns({"full_db": [15.6] * 40}, n_beats=40)
        self.assertFalse(track_baseline(v4, [0, 8], reducer="max").stable)          # 2 < 5
        self.assertTrue(track_baseline(v4, [0, 8, 16, 24, 32], reducer="max").stable)  # 5 >= 5

    def test_no_valid_drops_returns_none(self):
        v4 = _ns(n_beats=16)
        self.assertIsNone(track_baseline(v4, [], reducer="max"))
        self.assertIsNone(track_baseline(v4, [99, -3], reducer="max"))  # all out of range


class FailSafeTests(unittest.TestCase):
    def test_malformed_or_empty_never_phantom_t3(self):
        good_base = TrackBaseline(1.0, 1.0, 1.0, 1.0, 8, True, "max")
        # zero-length track
        self.assertIsNone(hardness_result(_ns(n_beats=0), 0, good_base))
        # missing required series key
        bad = SimpleNamespace(n_beats=16, series={"full_db": (15.0,) * 16})
        self.assertIsNone(hardness_result(bad, 0, good_base))
        self.assertIsNone(track_baseline(bad, [0], reducer="max"))
        # series length mismatch
        mism = SimpleNamespace(
            n_beats=16, series={k: (0.0,) * 4 for k in V4_SERIES_KEYS}
        )
        self.assertIsNone(track_baseline(mism, [0], reducer="max"))
        # out-of-range drop
        self.assertIsNone(hardness_result(_ns(n_beats=16), 50, good_base))
        # missing baseline
        self.assertIsNone(hardness_result(_ns(n_beats=16), 0, None))

    def test_unknown_reducer_raises_not_phantom(self):
        v4 = _ns(n_beats=16)
        with self.assertRaises(ValueError):
            hardness_result(v4, 0, TrackBaseline(1, 1, 1, 1, 8, True, "max"), reducer="p90")
        with self.assertRaises(ValueError):
            track_baseline(v4, [0], reducer="p90")


class IntegrationTests(unittest.TestCase):
    def test_runs_on_real_spectralfeaturesv4(self):
        v4 = _real_v4({"full_db": [16.5] * 24, "high_db": [1.0] * 24}, n_beats=24)
        base = track_baseline(v4, [0, 6, 12, 18], reducer="max")
        res = hardness_result(v4, 6, base, reducer="max")
        self.assertIsInstance(res, HardnessResult)
        self.assertIn(res.winning_path, hardness_v0.PATHS)

    def test_deterministic(self):
        v4 = _real_v4({"full_db": [10.0 + 0.3 * i for i in range(24)]}, n_beats=24)
        base = track_baseline(v4, [0, 6, 12, 18], reducer="max")
        a = hardness_result(v4, 6, base, reducer="max")
        b = hardness_result(v4, 6, base, reducer="max")
        self.assertEqual(a, b)


def _imports_hardness_v0(text: str) -> bool:
    """AST-robust: catches single-line, multiline-paren, aliased, dotted, and
    importlib.import_module / __import__ string forms. Falls back to a substring
    scan (conservative -> over-flags, never under-flags) on unparseable files.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "hardness_v0" in text
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "hardness_v0" in node.module:
                return True
            if any("hardness_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any("hardness_v0" in a.name for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if fname in ("import_module", "__import__"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and "hardness_v0" in arg.value:
                        return True
    return False


class ZeroRuntimeImporterTests(unittest.TestCase):
    """The machine-checkable shadow boundary: only tools/ and tests/ may import it."""

    SKIP_DIRS = {".git", "graphify-out", "__pycache__", "node_modules", "build", "dist"}

    def test_no_runtime_module_imports_hardness_v0(self):
        importers = []
        for path in REPO_ROOT.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in self.SKIP_DIRS or part.startswith(".") for part in rel.split("/")):
                continue
            if rel == "hardness_v0.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if _imports_hardness_v0(text):
                importers.append(rel)
        offenders = [r for r in importers if not (r.startswith("tools/") or r.startswith("tests/"))]
        self.assertEqual(offenders, [], f"hardness_v0 imported by non-tools/tests modules: {offenders}")

    def test_guard_detects_all_import_forms(self):
        # the guard must catch the forms the old regex missed
        for src in (
            "from rb_ss_bridge_v2 import hardness_v0",
            "from rb_ss_bridge_v2.hardness_v0 import hardness_result",
            "import rb_ss_bridge_v2.hardness_v0",
            "from rb_ss_bridge_v2 import (\n    spectral_cache,\n    hardness_v0,\n)",
            "importlib.import_module('rb_ss_bridge_v2.hardness_v0')",
            "__import__('rb_ss_bridge_v2.hardness_v0')",
        ):
            self.assertTrue(_imports_hardness_v0(src), src)
        self.assertFalse(_imports_hardness_v0("from rb_ss_bridge_v2 import spectral_cache"))


if __name__ == "__main__":
    unittest.main()
