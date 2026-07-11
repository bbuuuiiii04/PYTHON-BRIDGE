"""Unit tests for approach_features_v0 — the raw four-view approach descriptors.

These prove the descriptor layer is pure, deterministic, fail-safe, and marker-
robust WITHOUT asserting any class, threshold, or darkness length (there are
none — that is the point of this layer). Synthetic v4 stubs in the mk_v4 style of
test_lighting_moments_v2.py, extended to carry every series the module reads.
"""

import ast
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import approach_features_v0 as A  # noqa: E402

# every series the module summarizes
_ALL = A.APPROACH_SERIES
_DEFAULTS = {
    "full_db": 15.0,
    "sub_db": 20.0,
    "growl_band_db": 10.0,
    "sustain_mid_db": 10.0,
    "sustain_high_db": 8.0,
    "perc_full": 0.3,
}


def mk_v4(n=48, **overrides):
    """Synthetic SpectralFeaturesV4-shaped stub with flat non-trivial defaults for
    every series the descriptor reads. Override any series with a full list."""
    series = {k: [_DEFAULTS[k]] * n for k in _ALL}
    for k, v in overrides.items():
        series[k] = v
    return SimpleNamespace(series=series, scalars={"loudness_ref_db": 16.0}, n_beats=n)


def ramp(lo, hi, n):
    if n == 1:
        return [float(lo)]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


class TrajectoryTests(unittest.TestCase):
    def test_rising_vs_falling_full(self):
        n, drop = 48, 32
        v_rise = mk_v4(n=n)
        v_rise.series["full_db"][24:32] = ramp(0.0, 14.0, 8)
        r = A.approach_features(v_rise, drop, approach_len=8)
        self.assertGreater(r.approach.series["full_db"].slope, 0.0)
        self.assertGreater(r.approach.series["full_db"].delta, 0.0)

        v_fall = mk_v4(n=n)
        v_fall.series["full_db"][24:32] = ramp(14.0, 0.0, 8)
        f = A.approach_features(v_fall, drop, approach_len=8)
        self.assertLess(f.approach.series["full_db"].slope, 0.0)
        self.assertLess(f.approach.series["full_db"].delta, 0.0)

    def test_held_vs_collapsing_growl(self):
        n, drop = 48, 32
        v_hold = mk_v4(n=n, growl_band_db=[18.0] * n)
        h = A.approach_features(v_hold, drop, approach_len=8)
        self.assertEqual(h.approach.series["growl_band_db"].slope, 0.0)
        self.assertEqual(h.approach.series["growl_band_db"].delta, 0.0)

        v_coll = mk_v4(n=n)
        v_coll.series["growl_band_db"][24:32] = ramp(25.0, -5.0, 8)
        c = A.approach_features(v_coll, drop, approach_len=8)
        self.assertLess(c.approach.series["growl_band_db"].slope, 0.0)
        self.assertLess(c.approach.series["growl_band_db"].delta, 0.0)

    def test_ringing_layer_independent_of_sub_cut(self):
        # SIGNAL/Cocaine shape: sub is cut to the floor while a growl pad RINGS.
        # The two must be summarized independently — no min-masking.
        n, drop = 48, 32
        v = mk_v4(n=n)
        v.series["sub_db"][24:32] = [-15.0] * 8
        v.series["growl_band_db"][24:32] = [25.0] * 8
        r = A.approach_features(v, drop, approach_len=8)
        self.assertEqual(r.approach.series["sub_db"].p50, -15.0)
        self.assertEqual(r.approach.series["growl_band_db"].p50, 25.0)


class DepthTests(unittest.TestCase):
    def test_broad_vs_single_band_depth_raw_values(self):
        n, drop = 48, 40
        # single band: only sub cut; other bands stay at their track level.
        v_single = mk_v4(n=n)
        v_single.series["sub_db"][32:40] = [-15.0] * 8
        s = A.approach_features(v_single, drop, approach_len=8)
        self.assertLess(s.depth_vs_track["sub_db"], 0.0)
        self.assertEqual(s.depth_vs_track["full_db"], 0.0)
        self.assertEqual(s.depth_vs_track["growl_band_db"], 0.0)

        # broad: everything collapses -> every band sits below its track floor.
        v_broad = mk_v4(n=n)
        for k in _ALL:
            v_broad.series[k][32:40] = [_DEFAULTS[k] - 12.0] * 8
        b = A.approach_features(v_broad, drop, approach_len=8)
        for k in _ALL:
            self.assertLess(b.depth_vs_track[k], 0.0, k)

    def test_depth_uses_approach_floor_not_typical(self):
        # a non-flat approach (one deep beat) so approach p10 << p50 — pins that
        # depth reads the approach FLOOR (p10), not its typical level (p50).
        n, drop = 48, 40
        v = mk_v4(n=n)                     # sub_db default 20.0
        v.series["sub_db"][39] = -15.0    # one deep beat inside approach [32,40)
        r = A.approach_features(v, drop, approach_len=8)
        appr = r.approach.series["sub_db"]
        trk = r.track.series["sub_db"]
        self.assertNotEqual(appr.p10, appr.p50)
        self.assertEqual(r.depth_vs_track["sub_db"], round(appr.p10 - trk.p50, 4))
        self.assertNotEqual(r.depth_vs_track["sub_db"], round(appr.p50 - trk.p50, 4))

    def test_section_relative_depth(self):
        n, drop = 64, 56
        v = mk_v4(n=n)
        # a loud section, then a cut approach
        v.series["sub_db"][32:48] = [22.0] * 16   # section [32,48)
        v.series["sub_db"][48:56] = [-10.0] * 8   # approach [48,56)
        r = A.approach_features(v, drop, approach_len=8, section_len=16)
        self.assertIsNotNone(r.section)
        self.assertEqual((r.section.start, r.section.end), (32, 48))
        self.assertLess(r.depth_vs_section["sub_db"], 0.0)


class LandedTests(unittest.TestCase):
    def test_first8_and_next8_are_separate_windows(self):
        n, drop = 56, 32
        v = mk_v4(n=n)
        v.series["full_db"][32:40] = [5.0] * 8    # first 8: still quiet
        v.series["full_db"][40:48] = [15.0] * 8   # next 8: music returns
        r = A.approach_features(v, drop, approach_len=8)
        self.assertEqual((r.landed_first8.start, r.landed_first8.end), (32, 40))
        self.assertEqual((r.landed_next8.start, r.landed_next8.end), (40, 48))
        self.assertEqual(r.landed_next8.req_start, drop + r.landed_len)
        self.assertEqual(r.landed_first8.series["full_db"].p50, 5.0)
        self.assertEqual(r.landed_next8.series["full_db"].p50, 15.0)
        self.assertNotEqual(
            r.landed_first8.series["full_db"].p50,
            r.landed_next8.series["full_db"].p50,
        )


class BaselineTests(unittest.TestCase):
    def test_track_baseline_and_drop_landing_ref(self):
        n = 64
        v = mk_v4(n=n)
        # two genuine drops whose first-8 landings sit at 12 dB
        v.series["full_db"][16:24] = [12.0] * 8
        v.series["full_db"][40:48] = [12.0] * 8
        r = A.approach_features(
            v, 56, approach_len=8, genuine_drops=[16, 40]
        )
        self.assertEqual(r.track.n_available, n)
        self.assertIsNotNone(r.drop_landing_ref)
        self.assertEqual(r.drop_landing_ref["full_db"].n_drops, 2)
        self.assertEqual(r.drop_landing_ref["full_db"].p50, 12.0)

    def test_no_genuine_drops_leaves_ref_none(self):
        r = A.approach_features(mk_v4(n=48), 32, approach_len=8)
        self.assertIsNone(r.drop_landing_ref)

    def test_empty_genuine_drops_yields_zero_drop_ref(self):
        r = A.approach_features(mk_v4(n=48), 32, approach_len=8, genuine_drops=[])
        self.assertIsNotNone(r.drop_landing_ref)
        self.assertEqual(r.drop_landing_ref["full_db"].n_drops, 0)
        self.assertIsNone(r.drop_landing_ref["full_db"].p50)


class RunCurveTests(unittest.TestCase):
    def test_sub_void_run_curve_track_referenced(self):
        n, drop = 48, 40
        v = mk_v4(n=n)
        v.series["sub_db"][32:40] = [-15.0] * 8   # deep 8-beat void
        r = A.approach_features(v, drop, approach_len=8)
        rc = r.run_curves["sub_db"]
        self.assertEqual(rc.ref_view, "track")
        self.assertEqual(rc.floor_p50, 20.0)          # track median sub
        self.assertEqual(rc.run_p50, 8)               # whole approach below it
        self.assertEqual(rc.run_p10, 0)               # floor == void level, not below

    def test_longest_run_below_primitive(self):
        self.assertEqual(A.longest_run_below([0, 0, 5, 0, 0], 1.0), 2)
        self.assertEqual(A.longest_run_below([0, 0, float("nan"), 0, 0], 1.0), 2)
        self.assertEqual(A.longest_run_below([5, 5, 5], 1.0), 0)
        self.assertEqual(A.longest_run_below([], 1.0), 0)


class OffsetTests(unittest.TestCase):
    def test_pm2_offset_bundles_present_and_ordered(self):
        r = A.approach_features(mk_v4(n=48), 32, approach_len=8, offset_radius=2)
        offs = [o for o, _ in r.approach_offsets]
        self.assertEqual(offs, [-2, -1, 0, 1, 2])
        # offset 0 must match the primary approach window
        zero = dict(r.approach_offsets)[0]
        self.assertEqual((zero.start, zero.end), (r.approach.start, r.approach.end))

    def test_length_window_slides_with_marker(self):
        r = A.approach_features(mk_v4(n=48), 32, approach_len=8, offset_radius=2)
        m2 = dict(r.approach_offsets)[-2]
        self.assertEqual((m2.start, m2.end), (32 - 2 - 8, 32 - 2))  # (22, 30)

    def test_explicit_start_window_end_moves_only(self):
        r = A.approach_features(
            mk_v4(n=48), 32, approach_start=24, offset_radius=2
        )
        p2 = dict(r.approach_offsets)[2]
        self.assertEqual((p2.start, p2.end), (24, 34))  # start fixed, end moves

    def test_descriptor_range_flat_vs_edge(self):
        # flat track -> descriptor is marker-stable (min == max)
        flat = A.approach_features(mk_v4(n=48), 32, approach_len=8, offset_radius=2)
        rng_flat = A.descriptor_range(flat.approach_offsets, "full_db", "p50")
        self.assertIsNotNone(rng_flat)
        self.assertEqual(rng_flat[0], rng_flat[1])
        # an edge inside the offset span -> the descriptor moves across offsets
        v = mk_v4(n=48)
        v.series["full_db"][24:32] = ramp(0.0, 14.0, 8)
        edge = A.approach_features(v, 32, approach_len=8, offset_radius=2)
        rng_edge = A.descriptor_range(edge.approach_offsets, "full_db", "p50")
        self.assertGreater(rng_edge[1], rng_edge[0])


class FailSafeTests(unittest.TestCase):
    def test_boundary_clamp_reports_requested_vs_available(self):
        # drop near the very start: window requests 8 beats, only 2 exist
        r = A.approach_features(mk_v4(n=48), 2, approach_len=8)
        self.assertEqual(r.approach.n_requested, 8)
        self.assertEqual(r.approach.n_available, 2)
        self.assertEqual(r.approach.start, 0)
        self.assertTrue(r.approach.available)

    def test_short_window_is_insufficient_no_slope(self):
        r = A.approach_features(mk_v4(n=48), 32, approach_len=1)
        self.assertFalse(r.approach.sufficient)
        self.assertIsNone(r.approach.series["full_db"].slope)
        self.assertEqual(r.approach.reason, "insufficient beats for trend")

    def test_sufficient_requires_finite_data_not_just_beats(self):
        # A window can span >= 2 beat positions yet be all-hole: no series can
        # yield an OLS trend, so `sufficient` must be False with an honest reason
        # DISTINCT from the too-few-beats case. One finite sample is still not
        # enough (a slope needs two); two finite samples in a single series is.
        n, drop = 48, 32                                    # approach [24,32) = 8 beats
        # (a) every series entirely NaN: 8 beat positions, 0 finite -> not sufficient
        v_none = mk_v4(n=n, **{k: [float("nan")] * n for k in _ALL})
        r_none = A.approach_features(v_none, drop, approach_len=8)
        self.assertTrue(r_none.approach.available)          # window intersects track
        self.assertFalse(r_none.approach.sufficient)        # but no trend computable
        self.assertEqual(r_none.approach.reason, "insufficient finite data for trend")
        # (b) exactly one finite sample across every series: still no slope
        v_one = mk_v4(n=n, **{k: [float("nan")] * n for k in _ALL})
        v_one.series["full_db"][30] = 12.0                  # one finite beat in [24,32)
        r_one = A.approach_features(v_one, drop, approach_len=8)
        self.assertEqual(r_one.approach.series["full_db"].n_finite, 1)
        self.assertFalse(r_one.approach.sufficient)
        self.assertEqual(r_one.approach.reason, "insufficient finite data for trend")
        # (c) two finite samples in ONE series -> an OLS trend is computable
        v_two = mk_v4(n=n, **{k: [float("nan")] * n for k in _ALL})
        v_two.series["full_db"][28] = 4.0
        v_two.series["full_db"][30] = 8.0                   # two finite beats in [24,32)
        r_two = A.approach_features(v_two, drop, approach_len=8)
        self.assertEqual(r_two.approach.series["full_db"].n_finite, 2)
        self.assertTrue(r_two.approach.sufficient)
        self.assertEqual(r_two.approach.reason, "")
        self.assertIsNotNone(r_two.approach.series["full_db"].slope)  # trend really computed
        # the too-few-beats path keeps its own distinct reason (regression guard)
        r_short = A.approach_features(mk_v4(n=n), drop, approach_len=1)
        self.assertFalse(r_short.approach.sufficient)
        self.assertEqual(r_short.approach.reason, "insufficient beats for trend")

    def test_missing_series_is_present_false_no_guess(self):
        v = mk_v4(n=48)
        v.series.pop("sustain_mid_db")
        r = A.approach_features(v, 32, approach_len=8)
        ss = r.approach.series["sustain_mid_db"]
        self.assertFalse(ss.present)
        self.assertIsNone(ss.p50)
        self.assertIsNone(ss.slope)

    def test_non_finite_filtered_and_counted(self):
        v = mk_v4(n=48)
        v.series["full_db"][26] = float("nan")
        r = A.approach_features(v, 32, approach_len=8)  # approach [24,32)
        ss = r.approach.series["full_db"]
        self.assertEqual(ss.n_finite, 7)
        self.assertEqual(ss.finite_frac, round(7 / 8, 4))
        self.assertTrue(all(math.isfinite(x) for x in (ss.p50, ss.mean)))

    def test_all_nonfinite_top_level_unavailable_but_series_partial(self):
        # The approach window intersects the track, but every series is entirely
        # NaN: the TOP-LEVEL result must be honestly unavailable with a reason,
        # while per-series partial availability (present / n_finite and the
        # per-window WindowStats.available) is retained.
        v = mk_v4(n=48, **{k: [float("nan")] * 48 for k in _ALL})
        r = A.approach_features(v, 32, approach_len=8)
        self.assertTrue(r.approach.available)          # window still intersects
        self.assertFalse(r.available)                  # but no finite descriptor
        self.assertEqual(r.reason, "approach window has no finite data in any series")
        for k in _ALL:
            self.assertTrue(r.approach.series[k].present)   # key WAS present
            self.assertEqual(r.approach.series[k].n_finite, 0)
        # every series missing -> also top-level unavailable, same honest reason
        v2 = SimpleNamespace(series={}, scalars={}, n_beats=48)
        r2 = A.approach_features(v2, 32, approach_len=8)
        self.assertFalse(r2.available)
        self.assertEqual(r2.reason, "approach window has no finite data in any series")
        # a SINGLE finite beat inside the approach window is enough -> available
        v3 = mk_v4(n=48, **{k: [float("nan")] * 48 for k in _ALL})
        v3.series["full_db"][30] = 12.0            # approach [24,32) contains beat 30
        r3 = A.approach_features(v3, 32, approach_len=8)
        self.assertTrue(r3.available)
        self.assertEqual(r3.reason, "")

    def test_empty_track_is_unavailable_not_error(self):
        v = mk_v4(n=0)
        r = A.approach_features(v, 0, approach_len=4)
        self.assertFalse(r.available)
        self.assertFalse(r.approach.available)
        self.assertTrue(r.reason.startswith("approach window"))

    def test_section_unavailable_when_no_window_supplied(self):
        r = A.approach_features(mk_v4(n=48), 32, approach_len=8)
        self.assertIsNone(r.section)

    def test_inconsistent_caller_inputs_raise(self):
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_start=24, approach_len=8)
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32)  # neither
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_len=0)
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_len=8, offset_radius=-1)
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_len=8, section_start=0, section_len=8)
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_len=8, landed_len=0)
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_len=8, landed_len=-3)
        with self.assertRaises(ValueError):
            A.approach_features(mk_v4(), 32, approach_len=8, section_len=0)


class DeterminismTests(unittest.TestCase):
    def test_repeated_calls_identical(self):
        v = mk_v4(n=48)
        v.series["full_db"][24:32] = ramp(0.0, 14.0, 8)
        a = A.approach_features(v, 32, approach_len=8, genuine_drops=[8, 40])
        b = A.approach_features(v, 32, approach_len=8, genuine_drops=[8, 40])
        self.assertEqual(a, b)


class NoRuntimeImporterTests(unittest.TestCase):
    def test_zero_runtime_importers(self):
        """Only tests/ and tools/ may import approach_features_v0 — no runtime
        module (repo root, scripts/, streamdeck/, ...) may. Offline unused code."""
        repo_root = Path(__file__).resolve().parents[1]
        target = "approach_features_v0"
        skip_dirs = {"tests", "tools", ".git", "graphify-out", "local",
                     ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
        offenders = set()
        for path in repo_root.rglob("*.py"):
            rel = path.relative_to(repo_root)
            if set(rel.parts) & skip_dirs:
                continue
            if rel.name == "approach_features_v0.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            try:
                tree = ast.parse(text)
            except (SyntaxError, ValueError):
                tree = None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        if any(a.name.split(".")[-1] == target for a in node.names):
                            offenders.add(str(rel))
                    elif isinstance(node, ast.ImportFrom):
                        mod = (node.module or "").split(".")[-1]
                        if mod == target or any(a.name == target for a in node.names):
                            offenders.add(str(rel))
            # catch-all for dynamic imports the AST walk cannot see
            # (importlib.import_module, __import__, string loaders) AND any bare
            # runtime reference to the offline module — a raw-text mention in
            # non-test/tool code is itself a smell. tests/ + tools/ excluded above.
            if target in text:
                offenders.add(str(rel))
        self.assertEqual(sorted(offenders), [], f"runtime importers of {target}: {sorted(offenders)}")


if __name__ == "__main__":
    unittest.main()
