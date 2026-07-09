"""Unit tests for lighting_moments_v2 — the F2 pure rule engine (AWR-163).

The AWR-147 desk-calibration verdicts (C§6b-6f, 41 verdicts) ARE the fixtures.
These are the module-level unit tests (pure functions over synthetic v4 series);
the plan/dispatch/kill-test integration tests live in the F2 integration suite.

Executive condition 4 is proven structurally here: `darkness_ladder` takes NO
tier argument and every darkness assertion below is keyed on family-grade +
collapse only. Condition 2: the six known tier failure cases are PINNED to their
CURRENT (corpus-absolute) tier and labelled known-under-read, so any future tier
change surfaces in the diff.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import lighting_moments_v2 as M  # noqa: E402

_SERIES = ("sub_db", "bass_db", "full_db", "growl_band_db", "perc_full",
           "attack_low_db", "onset_density_midhigh", "fluxsum_midhigh")


def mk_v4(n=48, ref=16.0, **overrides):
    """A synthetic SpectralFeaturesV4-shaped stub: flat series the tests poke."""
    series = {k: [0.0] * n for k in _SERIES}
    series["sub_db"] = [20.0] * n           # floor present by default
    for k, v in overrides.items():
        series[k] = v
    return SimpleNamespace(series=series, scalars={"loudness_ref_db": ref}, n_beats=n)


def gone_run(v4, drop, beats, sub_val=1.0):
    """Carve a sub-only-gone run of `beats` immediately before `drop`."""
    for i in range(drop - beats, drop):
        v4.series["sub_db"][i] = sub_val
    return v4


class TestHelpers(unittest.TestCase):
    def test_quantize_down_caps_to_rung(self):
        self.assertEqual(M._quantize_down(10), 8)
        self.assertEqual(M._quantize_down(16), 16)
        self.assertEqual(M._quantize_down(3), 2)
        self.assertEqual(M._quantize_down(1), 1)

    def test_family_grade(self):
        self.assertEqual(M.family_grade("WALL"), "hard")
        self.assertEqual(M.family_grade("COMET"), "hard")
        self.assertEqual(M.family_grade("HOUSE"), "soft")
        self.assertEqual(M.family_grade("NEUTRAL"), "soft")


class TestTierCurrentBehavior(unittest.TestCase):
    """Frozen corpus-absolute cuts + track-start damping (current shipped tier)."""

    def _vec(self, full_db, attack, onset, lift_full=None):
        return {"full_db": full_db, "attack_low_p90": attack, "onset_density_mh": onset}

    def test_frozen_cuts(self):
        # violence just under / over each frozen cut → tier boundary holds.
        hot = {"full_db": 18.0, "attack_low_p90": 16.0, "onset_density_mh": 4.0}
        v, t = M.violence_tier(hot, lift=10.0, raw_gap=8)
        self.assertEqual(t, 3)
        cold = {"full_db": 8.0, "attack_low_p90": 0.0, "onset_density_mh": 0.0}
        v, t = M.violence_tier(cold, lift=-10.0, raw_gap=0)
        self.assertEqual(t, 1)

    def test_track_start_damping_only_lowers(self):
        self.assertEqual(M.damp_track_start(3, drop_beat=20), 1)          # within runway
        self.assertEqual(M.damp_track_start(3, drop_beat=200), 3)         # past runway
        self.assertEqual(M.damp_track_start(3, drop_beat=20, hotcue_tagged=True), 3)
        self.assertEqual(M.damp_track_start(1, drop_beat=200), 1)         # never raises


class TestDarknessLadder(unittest.TestCase):
    """C§6f ladder anchors — TIER-INDEPENDENT (no tier arg exists)."""

    def _ladder(self, family, gap, perc, full=10.0, bass=2.0, n=48):
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[perc] * n, full_db=[full] * n, bass_db=[bass] * n)
        gone_run(v4, drop, gap)
        return M.darkness_ladder(v4, drop, family, buildup_beat=drop - 16)

    def test_16_hard_collapse_only(self):
        # kidstopbreathing / Satisfaction / Age Of Love: hard family + long run.
        r = self._ladder("WALL", gap=16, perc=0.5)
        self.assertEqual((r.kind, r.beats), ("blackout", 16))

    def test_soft_deep_never_16(self):
        # FE!N -12 dB: soft family, deep+quiet, non-driving → 2, NEVER 16.
        r = self._ladder("HOUSE", gap=16, perc=0.5, full=2.0)
        self.assertEqual(r.kind, "blackout")
        self.assertEqual(r.beats, 2)

    def test_true_stop_8(self):
        # Cruel Summer: percussion done (perc<=0.15) but audible (lift>=-10) → 8.
        r = self._ladder("HOUSE", gap=8, perc=0.10, full=12.0)
        self.assertEqual((r.kind, r.beats), ("blackout", 8))

    def test_balloon_melodic(self):
        # Caramelle -14 dB, perc 0.16: melodic swell → balloon, never 16.
        r = self._ladder("HOUSE", gap=16, perc=0.16, full=2.0)
        self.assertEqual(r.kind, "balloon")

    def test_balloon_wins_over_hard_16(self):
        # Stereo Love: melodic balloon build INTO a hard (WALL) drop → balloon.
        r = self._ladder("WALL", gap=16, perc=0.20, full=4.0)
        self.assertEqual(r.kind, "balloon")

    def test_soft_driving_4(self):
        # GNARLY / Tremor / Diamond Therapy: soft, drums driving (perc>=0.55) → 4.
        r = self._ladder("HOUSE", gap=6, perc=0.6)
        self.assertEqual((r.kind, r.beats), ("blackout", 4))

    def test_groove_capped_by_gap(self):
        # Take It / You&Me / Hide&Seek: soft, music runs straight in, 1-beat gap → 1.
        r = self._ladder("HOUSE", gap=1, perc=0.5, full=8.0)
        self.assertEqual((r.kind, r.beats), ("blackout", 1))

    def test_ladder_takes_no_tier(self):
        # Structural proof of executive condition 4: the ladder signature has no
        # tier parameter — a tier value cannot leak in.
        import inspect
        params = inspect.signature(M.darkness_ladder).parameters
        self.assertNotIn("tier", params)
        self.assertEqual(list(params), ["v4", "drop", "family", "buildup_beat"])


class TestDipAndFlick(unittest.TestCase):
    def test_perc_cut_flick(self):
        # No gone run, but growl cuts >=5 dB at D-1 → 1-beat perc-flick.
        n = 48
        drop = n - 4
        growl = [20.0] * n
        growl[drop - 1] = 10.0   # 10 dB below D-2's 20 → cut
        v4 = mk_v4(n=n, growl_band_db=growl)
        r = M.darkness_ladder(v4, drop, "HOUSE")
        self.assertEqual((r.kind, r.beats), ("perc-flick", 1))

    def test_snap_default(self):
        v4 = mk_v4()
        r = M.darkness_ladder(v4, 44, "HOUSE")
        self.assertEqual(r.kind, "snap")


class TestAbort(unittest.TestCase):
    def test_floor_return_aborts_early(self):
        # Newest gone beat e = D-4, then the floor returns present for D-3..D-1
        # (2+ consecutive) → darkness aborts inside the window instead of sitting
        # dark over the landed pickup.
        n = 48
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[0.6] * n, full_db=[10.0] * n)
        # gone run [drop-11 .. drop-4], present pickup [drop-3 .. drop-1]
        for i in range(drop - 11, drop - 3):
            v4.series["sub_db"][i] = 1.0
        r = M.darkness_ladder(v4, drop, "HOUSE")   # soft+driving → emphasis 4, window [drop-4, drop)
        self.assertEqual(r.kind, "blackout")
        self.assertEqual(r.abort_at, drop - 3)     # first of the 2 consecutive present beats

    def test_lone_pickup_does_not_abort(self):
        # Only D-1 present (a single pickup beat) → dark through the pickup, no abort.
        n = 48
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[0.6] * n, full_db=[10.0] * n)
        for i in range(drop - 11, drop - 1):
            v4.series["sub_db"][i] = 1.0           # gone through D-2; D-1 present
        r = M.darkness_ladder(v4, drop, "HOUSE")
        self.assertIsNone(r.abort_at)


class TestKnownTierFailures(unittest.TestCase):
    """Executive condition 2: the six AWR-147 tier misses stay PINNED to their
    current corpus-absolute tier, each labelled known-under-read. The corpus
    values come from /tmp/awr147/report.json; here we pin the mapping law that
    produced them so a future tier redesign shows up as a diff.

    Family-percentile redesign is DEAD (0/5 fixtures — docs AWR-163). These pins
    document the CURRENT behavior; they are NOT targets to flip.
    """

    # (label, violence, current_tier) — known-under-read / known-over-read.
    PINS = [
        ("Satisfaction (Hardwell&Maddix) @128  [known-under-read]", 0.567, 1),
        ("ONE CHANCE @2:36 trap monster        [known-under-read]", 0.516, 1),
        ("Age Of Love @1:30                     [known-over-read]", 0.698, 3),
        ("I COULD BE THE ONE @1:18 HOUSE        [validated-hold]", 0.709, 3),
        ("DROP EM @168                          [validated-hold]", 0.619, 2),
        ("You & Me @1:19 WALL                   [known-over-read]", 0.743, 3),
    ]

    def test_current_tier_pins(self):
        for label, viol, expected in self.PINS:
            with self.subTest(label=label):
                tier = 3 if viol >= M.TIER_P85 else 2 if viol >= M.TIER_P55 else 1
                self.assertEqual(tier, expected,
                                 f"{label}: current corpus-absolute tier drifted")


class TestTrackPlan(unittest.TestCase):
    """Task 2: build_track_plan over a real-shaped v4 (uses the sibling _v4)."""

    def _v4(self, n=48):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_spectral_profile import _v4 as mk
        v4 = mk(n_beats=n, scalars_overrides={"loudness_ref_db": 16.0})
        v4.series["sub_db"] = tuple(20.0 if not (28 <= i < 32) else 1.0 for i in range(n))
        v4.series["perc_full"] = tuple(0.6 for _ in range(n))
        v4.series["full_db"] = tuple(10.0 for _ in range(n))
        v4.series["bass_db"] = tuple(2.0 for _ in range(n))
        return v4

    def test_plan_has_one_entry_per_drop(self):
        plan = M.build_track_plan(self._v4(), drops=[16, 32], buildups=[0, 16])
        self.assertEqual(len(plan.entries), 2)
        e = plan.for_drop(32)
        self.assertIsNotNone(e)
        self.assertIn(e.decision.tier, (1, 2, 3))
        self.assertGreaterEqual(e.white_share, M.WHITE_MIN)
        self.assertIsNotNone(plan.for_drop(33, tol=1))   # tolerance lookup
        self.assertIsNone(plan.for_drop(40))

    def test_empty_drops_is_empty_plan(self):
        plan = M.build_track_plan(self._v4(), drops=[], buildups=[])
        self.assertEqual(plan.entries, ())

    def test_summary_string(self):
        plan = M.build_track_plan(self._v4(), drops=[16, 32], buildups=[0, 16])
        self.assertIn("drops=2", plan.summary())


if __name__ == "__main__":
    unittest.main()
