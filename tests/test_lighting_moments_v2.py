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
from unittest import mock

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


def pickup_void_v4(void_lo, void_hi, n=64):
    """AWR-199 spec recipe: sub 20 / growl 18 / full 15 / perc 0.2 everywhere,
    with a deep void (sub −15, full 5) over [void_lo, void_hi] and the growl
    band dark (−4) at the void's last beat."""
    v4 = mk_v4(n=n, perc_full=[0.2] * n, full_db=[15.0] * n,
               growl_band_db=[18.0] * n)
    for i in range(void_lo, void_hi + 1):
        v4.series["sub_db"][i] = -15.0
        v4.series["full_db"][i] = 5.0
    v4.series["growl_band_db"][void_hi] = -4.0
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
        # A GENUINE quiet collapse (perc ~0, full band silent) earns the full
        # 16-beat blackout via the Part-H true-silence branch. That is the only
        # path to a 16 now: PERC_ALIVE_16 (0.30) sits below the balloon split, so
        # every audible sub-gone collapse either balloons (perc<0.35) or reaches
        # the 16 rung and demotes (perc>=0.35). perc is far under 0.30 here.
        r = self._ladder("WALL", gap=16, perc=0.0, full=-30.0)
        self.assertEqual((r.kind, r.beats), ("blackout", 16))
        self.assertTrue(r.cap_inputs.get("silence"))

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


class TestDeepSubVoidBlackout(unittest.TestCase):
    """AWR-184 (operator-directed): a deep sub void with the growl band ALSO dead →
    blackout, not balloon. The growl gate is what separates Utopia's real voids
    (growl dies, everything cuts) from Caramelle's filtered melodic swell (growl
    sustains → still balloon). Thresholds verified against the real spectral cache."""

    def _v4(self, drop, void_beats, sub_val, growl_val, perc, n=48, full=3.0):
        v4 = mk_v4(n=n, perc_full=[perc] * n, full_db=[full] * n,
                   growl_band_db=[20.0] * n)
        for i in range(drop - void_beats, drop):
            v4.series["sub_db"][i] = sub_val
            v4.series["growl_band_db"][i] = growl_val
        return v4

    def test_two_bar_void_blackouts(self):
        # Utopia b192-shape: 6 deep beats (sub ≈−27) + growl dead → blackout, 2 bars.
        r = M.darkness_ladder(self._v4(44, 6, -27.0, -4.0, 0.28), 44,
                              "NEUTRAL", buildup_beat=28)
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertEqual(r.cap_inputs.get("sub_void"), 6)

    def test_one_bar_void_blackouts(self):
        # Utopia b384-shape: 2 deep beats (sub ≈−16) + growl dead → blackout, 1 bar.
        r = M.darkness_ladder(self._v4(44, 2, -16.0, -4.0, 0.29), 44,
                              "NEUTRAL", buildup_beat=28)
        self.assertEqual((r.kind, r.beats), ("blackout", 4))

    def test_growl_alive_stays_balloon(self):
        # Caramelle @2:07-shape: sub voided just as deep (≈−30) but the growl SUSTAINS
        # (≈18 dB, melody keeps ringing) → still balloon, never blackout.
        r = M.darkness_ladder(self._v4(44, 6, -30.0, 18.0, 0.16), 44,
                              "HOUSE", buildup_beat=28)
        self.assertEqual(r.kind, "balloon")

    def test_shallow_sub_stays_balloon(self):
        # Utopia b128-shape: sub only dips to −4 (filter edge, not a void) → balloon.
        r = M.darkness_ladder(self._v4(44, 4, -4.0, -4.0, 0.18), 44,
                              "NEUTRAL", buildup_beat=28)
        self.assertEqual(r.kind, "balloon")

    def test_single_deep_beat_not_enough(self):
        # A lone 1-beat deep dropout does not qualify (VOID_MIN_BEATS=2) → balloon.
        r = M.darkness_ladder(self._v4(44, 1, -27.0, -4.0, 0.20), 44,
                              "NEUTRAL", buildup_beat=28)
        self.assertNotEqual(r.reason.startswith("deep-sub-void"), True)

    def test_vocal_stop_yields_to_stop_rung(self):
        # AWR-185: an ambiguous-class case (Cruel Summer 418-shape: 51-beat deep sub
        # void, growl 0.3, full band still audible at ref−9.4, perc done). Rung 0b
        # would round the 51-beat run UP to a 16-beat blackout, but the calibrated
        # STOP rung must win → 8-beat length. ref=16 → full 6.6 gives lift −9.4.
        v4 = mk_v4(n=480, ref=16.0, perc_full=[0.10] * 480,
                   full_db=[6.6] * 480, growl_band_db=[20.0] * 480)
        for i in range(418 - 51, 418):
            v4.series["sub_db"][i] = -16.0
            v4.series["growl_band_db"][i] = 0.3
        r = M.darkness_ladder(v4, 418, "NEUTRAL", buildup_beat=418 - 16)
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertTrue(r.cap_inputs.get("stop"))
        self.assertNotIn("sub_void", r.cap_inputs)   # 0b yielded, did not fire

    # --- AWR-199 pickup abort: the void may END before the drop (tolerant_scan
    # --- accepts e in [D-4, D-1]) — only a >=3-beat returned-music pickup
    # --- releases; the operator-verdicted gap-0/1/2 shapes stay dark.

    def test_pickup_ended_dip_releases_early(self):
        # SOL2 repro shape: deep run 39-44 ends at D-4 → 3 audible pickup beats
        # (45-47) that were planned dark; the guard releases at the first.
        r = M.darkness_ladder(pickup_void_v4(39, 44), 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertEqual(r.abort_at, 45)
        self.assertIn("pickup abort@45", r.reason)
        self.assertEqual(r.cap_inputs["growl_tail"], -4.0)

    def test_two_beat_pickup_stays_dark(self):
        # Void ends at D-3 → 2-beat pickup: the TOXIC b159 / OMG b400
        # operator-verdicted shape ("blackout is perfect") — no release.
        r = M.darkness_ladder(pickup_void_v4(40, 45), 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertIsNone(r.abort_at)

    def test_lone_pickup_transient_stays_dark(self):
        # Void ends at D-2, single present beat 47: the UT-6 / Utopia-b384
        # semantics (a lone transient counts inside "1 bar blackout").
        r = M.darkness_ladder(pickup_void_v4(44, 46), 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 4))
        self.assertIsNone(r.abort_at)

    def test_void_into_drop_no_abort(self):
        # Void runs 42-47 straight into the drop (ends at D-1) → nothing returns.
        v4 = pickup_void_v4(42, 47)
        for i in range(42, 48):
            v4.series["growl_band_db"][i] = -4.0
        r = M.darkness_ladder(v4, 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertIsNone(r.abort_at)

    def test_kill_switch_restores_none(self):
        # RBSS_F2_VOID_PICKUP_ABORT=0 restores today's exact decision.
        with mock.patch.object(M, "_PICKUP_ABORT_ON", False):
            r = M.darkness_ladder(pickup_void_v4(39, 44), 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertIsNone(r.abort_at)
        self.assertNotIn("pickup abort", r.reason)

    def test_utopia_pin_fixtures_hold(self):
        # The frozen AWR-184 pins, MEASURED real-cache window values (AWR-199
        # spec Part A) placed into the synthetic grid: both keep abort None
        # (lone pickup transients), decisions unchanged.
        b192_sub = [12.8, -28.7, -28.2, -25.1, -25.7, -27.6, -28.1, 5.3]
        b192_growl = [20.6, 17.7, 14.7, 11.8, 7.8, -4.3, -1.7, 5.7]
        v4 = mk_v4(n=64, perc_full=[0.2] * 64, growl_band_db=[18.0] * 64)
        for i, (s, g) in enumerate(zip(b192_sub, b192_growl)):
            v4.series["sub_db"][40 + i] = s
            v4.series["growl_band_db"][40 + i] = g
        r = M.darkness_ladder(v4, 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertIsNone(r.abort_at)

        b384_sub = [-4.9, -10.9, -16.7, 13.7]
        b384_growl = [3.3, -1.5, -4.4, -3.1]
        v4 = mk_v4(n=64, perc_full=[0.2] * 64, growl_band_db=[18.0] * 64)
        for i, (s, g) in enumerate(zip(b384_sub, b384_growl)):
            v4.series["sub_db"][44 + i] = s
            v4.series["growl_band_db"][44 + i] = g
        r = M.darkness_ladder(v4, 48, "NEUTRAL")
        self.assertEqual((r.kind, r.beats), ("blackout", 4))
        self.assertIsNone(r.abort_at)


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


class TestF2Config(unittest.TestCase):
    """Task 5: the /f2 config block — absent ⇒ off (kill test), fail-closed."""

    def test_absent_or_empty_is_disabled(self):
        from rb_ss_bridge_v2.led_models import F2Config
        self.assertFalse(F2Config.from_dict(None).enabled)     # absent block
        self.assertFalse(F2Config.from_dict({}).enabled)
        self.assertFalse(F2Config.from_dict("garbage").enabled)

    def test_routing_str_tier_keys_coerced_to_int(self):
        from rb_ss_bridge_v2.led_models import F2Config
        c = F2Config.from_dict({"enabled": True,
                                "drop_look_routing": {"WALL": {"2": ["a", "b"], "3": ["c"]}}})
        self.assertTrue(c.enabled)
        self.assertEqual(c.drop_look_routing["WALL"][2], ("a", "b"))
        self.assertEqual(c.drop_look_routing["WALL"][3], ("c",))

    def test_junk_ignored_and_burndown_defaults(self):
        from rb_ss_bridge_v2.led_models import F2Config
        c = F2Config.from_dict({"enabled": True, "bogus": 1,
                                "drop_look_routing": {"X": "notdict"},
                                "impact_burndown": {"enabled": True, "ease_beats": 12}})
        self.assertEqual(c.drop_look_routing, {})              # bad cell dropped
        self.assertTrue(c.impact_burndown_enabled)
        self.assertEqual(c.impact_burndown_ease_beats, 12)

    def test_example_config_ships_enabled(self):
        from rb_ss_bridge_v2.led_config import load_f2_config
        ex = load_f2_config(str(Path(__file__).resolve().parents[1]
                                / "config" / "led_look_director.example.json"))
        self.assertTrue(ex.enabled)


class TestLaserEnergyGate(unittest.TestCase):
    """AWR-162 (A): tier → laser energy mapping + the plan_track energy gate."""

    def test_laser_tier_mapping(self):
        self.assertEqual(M.laser_tier("NEUTRAL", 3), "small")   # flagged veto item
        self.assertEqual(M.laser_tier("NEUTRAL", 1), "small")
        self.assertEqual(M.laser_tier("WALL", 1), "standard")
        self.assertEqual(M.laser_tier("HOUSE", 2), "intense")
        self.assertEqual(M.laser_tier("COMET", 3), "monster")

    def test_plan_track_energy_gate(self):
        from rb_ss_bridge_v2 import drop_presentation as DP
        cfg = DP.load_drop_presentation_config("/nonexistent")   # fails open to defaults
        drops = [100.0, 200.0, 300.0]
        tiers = {100.0: "small", 200.0: "intense", 300.0: "monster"}
        plan = DP.plan_track(drops, [], [], [], cfg, laser_tiers=tiers)
        got = {d.beat: d.personality_presentation for d in plan.decisions}
        self.assertEqual(got[100.0], DP.LEDS_ONLY)          # small → lasers silent
        self.assertEqual(got[200.0], DP.LEDS_PLUS_LASERS)
        self.assertEqual(got[300.0], DP.LEDS_PLUS_LASERS)

    def test_tier_less_is_legacy(self):
        # laser_tiers=None ⇒ the legacy laser_ratio ranking runs unchanged.
        from rb_ss_bridge_v2 import drop_presentation as DP
        cfg = DP.load_drop_presentation_config("/nonexistent")
        legacy = DP.plan_track([100.0, 200.0], [], [], [], cfg)
        self.assertEqual(len(legacy.decisions), 2)   # builds, no tier gate applied


class TestTransitionWindow(unittest.TestCase):
    """Task 3.1: the pre-drop dark-window length override (LED+laser shared)."""

    def _plan(self, kind, beats, drop_beat=32):
        dark = M.DarknessDecision(kind, beats, (drop_beat - beats, drop_beat), None, {}, "x")
        dec = M.DropDecision(drop_beat, "WALL", 0.7, 3, dark, "", "x")
        entry = M.DropPlanEntry(drop_beat, dec, 0.5, 0)
        return M.F2TrackPlan((entry,), "swell")

    def test_blackout_uses_planned_length(self):
        plan = self._plan("blackout", 16)
        self.assertEqual(M.transition_window_for(plan, 20.0, [32], default=4.0), 16.0)

    def test_perc_flick_is_one(self):
        plan = self._plan("perc-flick", 1)
        self.assertEqual(M.transition_window_for(plan, 31.0, [32], default=4.0), 1.0)

    def test_balloon_and_snap_have_no_black_window(self):
        for kind in ("balloon", "snap", "dip"):
            plan = self._plan(kind, 8)
            self.assertEqual(M.transition_window_for(plan, 20.0, [32], default=4.0), 0.0)

    def test_no_plan_or_no_upcoming_returns_default(self):
        self.assertEqual(M.transition_window_for(None, 20.0, [32], default=4.0), 4.0)
        plan = self._plan("blackout", 16)
        self.assertEqual(M.transition_window_for(plan, 40.0, [32], default=4.0), 4.0)  # drop passed
        self.assertEqual(M.transition_window_for(plan, None, [32], default=4.0), 4.0)  # no beat


class TestTransitionRelease(unittest.TestCase):
    """AWR-179 D2-F1 (OLC-B): the early-release bound for the pre-drop dark window."""

    def _plan(self, kind, beats, drop_beat=32, abort_at=None):
        dark = M.DarknessDecision(kind, beats, (drop_beat - beats, drop_beat), abort_at, {}, "x")
        dec = M.DropDecision(drop_beat, "WALL", 0.7, 3, dark, "", "x")
        entry = M.DropPlanEntry(drop_beat, dec, 0.5, 0)
        return M.F2TrackPlan((entry,), "swell")

    def test_blackout_with_abort_releases_at_drop_minus_abort(self):
        plan = self._plan("blackout", 16, drop_beat=32, abort_at=29)
        self.assertEqual(M.transition_release_for(plan, 20.0, [32]), 3.0)  # 32 - 29

    def test_blackout_without_abort_is_zero(self):
        plan = self._plan("blackout", 16, drop_beat=32, abort_at=None)
        self.assertEqual(M.transition_release_for(plan, 20.0, [32]), 0.0)

    def test_non_blackout_families_are_zero(self):
        for kind in ("balloon", "dip", "snap", "perc-flick"):
            plan = self._plan(kind, 8, drop_beat=32, abort_at=20)
            self.assertEqual(M.transition_release_for(plan, 20.0, [32]), 0.0)

    def test_no_plan_no_beat_or_drop_passed_is_zero(self):
        plan = self._plan("blackout", 16, drop_beat=32, abort_at=29)
        self.assertEqual(M.transition_release_for(None, 20.0, [32]), 0.0)
        self.assertEqual(M.transition_release_for(plan, None, [32]), 0.0)
        self.assertEqual(M.transition_release_for(plan, 40.0, [32]), 0.0)  # drop passed

    def test_abort_at_window_start_equals_window_length(self):
        # abort_at == window start (drop - beats) => release == window length => zero dark beats.
        plan = self._plan("blackout", 16, drop_beat=32, abort_at=16)
        self.assertEqual(M.transition_release_for(plan, 20.0, [32]), 16.0)

    def test_deep_sub_void_pickup_abort_releases(self):
        # AWR-199: a REAL deep-sub-void decision carrying the pickup abort
        # feeds the shared release surface as drop_beat - abort_at.
        dark = M.darkness_ladder(pickup_void_v4(39, 44), 48, "NEUTRAL")
        self.assertEqual((dark.kind, dark.abort_at), ("blackout", 45))
        dec = M.DropDecision(48, "NEUTRAL", 0.7, 3, dark, "", "x")
        entry = M.DropPlanEntry(48, dec, 0.5, 0)
        plan = M.F2TrackPlan((entry,), "swell")
        self.assertEqual(M.transition_release_for(plan, 40.0, [48]), 3.0)  # 48 - 45


class TestKillSwitchByteIdentity(unittest.TestCase):
    """MANDATORY kill test (Part C): with F2 OFF, every F2 hook passes through to
    the v1 default even when a plan is present — so F2-off is byte-identical to v1.
    Scripted tracks stand down the same way (D§7). Exercised via the real
    StateManager methods (the OFF / scripted branch early-returns before any heavy
    state), so this pins the actual gating code, not a copy."""

    def _plan(self):
        dark = M.DarknessDecision("blackout", 16, (16, 32), None, {}, "x")
        dec = M.DropDecision(32, "WALL", 0.7, 3, dark, "", "x")
        return M.F2TrackPlan((M.DropPlanEntry(32, dec, 0.5, 0),), "swell")

    def _deck(self, scripted_id=0):
        return SimpleNamespace(scripted_id=scripted_id,
                               meta=SimpleNamespace(f2_plan=self._plan()))

    def _sm(self):
        from rb_ss_bridge_v2.state_manager import StateManager
        return StateManager

    def test_f2_off_transition_window_is_the_fixed_default(self):
        SM = self._sm()
        off = SimpleNamespace(_f2_enabled=False)
        # plan present, but F2 off → the fixed predark default, unchanged from v1.
        self.assertEqual(
            SM._f2_transition_window_beats(off, self._deck(), 20.0, [32], 4.0), 4.0)

    def test_f2_off_laser_tiers_is_none_legacy(self):
        SM = self._sm()
        off = SimpleNamespace(_f2_enabled=False)
        self.assertIsNone(SM._f2_laser_tiers(off, self._deck(), [32]))

    def test_scripted_stands_down_even_with_f2_on(self):
        SM = self._sm()
        on = SimpleNamespace(_f2_enabled=True)
        scripted = self._deck(scripted_id=7)
        self.assertEqual(
            SM._f2_transition_window_beats(on, scripted, 20.0, [32], 4.0), 4.0)
        self.assertIsNone(SM._f2_laser_tiers(on, scripted, [32]))

    def test_f2_on_no_plan_falls_back(self):
        SM = self._sm()
        on = SimpleNamespace(_f2_enabled=True)
        no_plan = SimpleNamespace(scripted_id=0, meta=SimpleNamespace(f2_plan=None))
        self.assertEqual(
            SM._f2_transition_window_beats(on, no_plan, 20.0, [32], 4.0), 4.0)
        self.assertIsNone(SM._f2_laser_tiers(on, no_plan, [32]))

    def _abort_plan(self):
        # blackout drop@32, window [16,32], abort_at=29 -> release bound 3.0.
        dark = M.DarknessDecision("blackout", 16, (16, 32), 29, {}, "x")
        dec = M.DropDecision(32, "WALL", 0.7, 3, dark, "", "x")
        return M.F2TrackPlan((M.DropPlanEntry(32, dec, 0.5, 0),), "swell")

    def test_transition_release_gate_off_scripted_and_plumbed(self):
        # AWR-179 D2-F1: same gate as the window method — F2 off / scripted => 0.0;
        # F2 on + plan with abort => the delegated release bound is plumbed through.
        SM = self._sm()
        deck = SimpleNamespace(scripted_id=0, meta=SimpleNamespace(f2_plan=self._abort_plan()))
        off = SimpleNamespace(_f2_enabled=False)
        on = SimpleNamespace(_f2_enabled=True)
        scripted = SimpleNamespace(scripted_id=7, meta=SimpleNamespace(f2_plan=self._abort_plan()))
        self.assertEqual(SM._f2_transition_release_beats(off, deck, 20.0, [32]), 0.0)
        self.assertEqual(SM._f2_transition_release_beats(on, scripted, 20.0, [32]), 0.0)
        self.assertEqual(SM._f2_transition_release_beats(on, deck, 20.0, [32]), 3.0)


class TestBalloonBoundary(unittest.TestCase):
    """C§6f perc split pinned at 0.35: melodic riser → balloon; drums driving → 4."""

    def _ladder(self, perc):
        n = 48
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[perc] * n, full_db=[8.0] * n, bass_db=[2.0] * n)
        gone_run(v4, drop, 8)
        return M.darkness_ladder(v4, drop, "HOUSE", buildup_beat=drop - 16)

    def test_below_boundary_balloons(self):
        self.assertEqual(self._ladder(0.30).kind, "balloon")   # melodic riser

    def test_at_or_above_boundary_blacks(self):
        self.assertEqual(self._ladder(0.35).kind, "blackout")  # gray zone → black
        self.assertEqual(self._ladder(0.60).kind, "blackout")  # drums driving


class TestPercAliveGuard(unittest.TestCase):
    """Part H2 (AWR-180 batch 2): the 16 rung requires ACTUAL quiet. A snare-driven
    build carries no sub — tolerant_scan reads it as a long collapse — but pounds
    percussion, so perc_build above PERC_ALIVE_16 demotes 16 to the short (4)
    hard-drop emphasis. Acceptance = Sexy 1:27 / Shiny 3:12 (snare walls) drop to
    small rungs; a genuinely quiet collapse still earns 16; the Part-H true-silence
    case (perc ~0) still gets its full-span blackout — the two rules compose."""

    def _ladder(self, perc, full=10.0):
        n = 48
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[perc] * n, full_db=[full] * n, bass_db=[2.0] * n)
        gone_run(v4, drop, 16)            # sub gone 16 beats → hard collapse gap
        return M.darkness_ladder(v4, drop, "WALL", buildup_beat=drop - 16)

    def test_sexy_1_27_founding_case_demotes(self):
        # FOUNDING CASE. Executive-measured: Sexy 1:27 ladder window [128,192)
        # perc_full median = 0.386 (a heavy loud snare-filled build, no sub, so
        # tolerant_scan reads it as a long collapse). Hard family + 16-beat
        # sub-gone run reaches the 16 rung; the perc-alive guard demotes it → 4.
        r = self._ladder(0.386)
        self.assertEqual((r.kind, r.beats), ("blackout", 4))

    def test_snare_wall_demotes_to_four(self):
        # Louder snare wall (perc_build 0.45) → also demoted, NOT 16.
        r = self._ladder(0.45)
        self.assertEqual((r.kind, r.beats), ("blackout", 4))

    def test_genuinely_quiet_collapse_earns_16_via_silence(self):
        # A genuine quiet collapse (perc ~0, full band silent) still earns a
        # 16-beat blackout — through the Part-H true-silence branch (checked before
        # the rung), so the perc guard never touches it. The two rules compose.
        r = self._ladder(0.0, full=-30.0)
        self.assertEqual((r.kind, r.beats), ("blackout", 16))
        self.assertTrue(r.cap_inputs.get("silence"))

    def test_killa_true_silence_still_full_span_with_guard(self):
        # The Part-H silence branch runs BEFORE the 16 rung, so the perc guard
        # never touches Killa (perc ~0). Full-span blackout composes unchanged.
        v4 = mk_v4(n=528, ref=16.0, full_db=[10.0] * 528)
        collapse = [-4.6, -14.0, -23.0, -30.0, -36.7]
        for k, b in enumerate(range(513, 518)):
            v4.series["sub_db"][b] = 1.0
            v4.series["full_db"][b] = collapse[k]
        r = M.darkness_ladder(v4, 521, "WALL", buildup_beat=505)
        self.assertEqual((r.kind, r.window, r.beats), ("blackout", (513, 521), 8))
        self.assertTrue(r.cap_inputs.get("silence"))


class TestTrueSilenceBranch(unittest.TestCase):
    """Part H (AWR-180 batch 2): a genuine FULL-band silence blacks the whole span
    from the silence onset to the drop, checked BEFORE the stop/balloon split.
    Named acceptance = Killa (Original Mix) 513-521."""

    def _killa(self):
        # full_db collapses -4.6/-14/-23/-30/-36.7 over beats 513-517 (sub gone),
        # sub flickers back 518-520, WALL T3 drop at 521.
        v4 = mk_v4(n=528, ref=16.0, full_db=[10.0] * 528)
        collapse = [-4.6, -14.0, -23.0, -30.0, -36.7]
        for k, b in enumerate(range(513, 518)):
            v4.series["sub_db"][b] = 1.0          # sub gone across the collapse
            v4.series["full_db"][b] = collapse[k]
        return v4

    def test_killa_full_span_blackout_from_silence_onset(self):
        r = M.darkness_ladder(self._killa(), 521, "WALL", buildup_beat=505)
        self.assertEqual(r.kind, "blackout")
        self.assertEqual(r.window, (513, 521))    # silence onset → drop
        self.assertEqual(r.beats, 8)              # RAW span 521-513, NOT quantized
        self.assertIsNone(r.abort_at)             # no early release across the span
        self.assertTrue(r.cap_inputs.get("silence"))

    def test_residual_audibility_still_stops(self):
        # Percussion done but the band is still audible (full 12, lift -4): the
        # silence floor is nowhere near, so the stop branch fires unchanged → 8.
        n = 48
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[0.10] * n, full_db=[12.0] * n)
        gone_run(v4, drop, 8)
        r = M.darkness_ladder(v4, drop, "HOUSE", buildup_beat=drop - 16)
        self.assertEqual((r.kind, r.beats), ("blackout", 8))
        self.assertFalse(r.cap_inputs.get("silence"))

    def test_melodic_swell_still_balloons(self):
        # Melodic swell (full 2, perc 0.16): audible enough to clear the silence
        # floor, so the balloon branch still wins.
        n = 48
        drop = n - 4
        v4 = mk_v4(n=n, perc_full=[0.16] * n, full_db=[2.0] * n)
        gone_run(v4, drop, 16)
        r = M.darkness_ladder(v4, drop, "HOUSE", buildup_beat=drop - 16)
        self.assertEqual(r.kind, "balloon")


if __name__ == "__main__":
    unittest.main()
