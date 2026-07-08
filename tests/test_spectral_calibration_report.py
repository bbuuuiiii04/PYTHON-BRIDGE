"""Table-driven tests for the F2 rule pack inside tools/spectral_calibration_report.py.

Synthetic series only — no cache, DB, or audio dependency. Covers the tolerant
sub-only scan, busy-kill, floor-returned abort (incl. zero-dark at entry), the
relative dip and perc-flick branches, the family classifier's first-match
ordering, the violence/tier arithmetic, and the bass-forward B/K/. flags.
Hand-computed expectations follow the pins in LIGHTING_ENGINE_V2_DESIGN.md §§3-5.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[0]))     # rb_ss_bridge_v2 package
sys.path.insert(0, str(ROOT / "tools"))      # the report module

import spectral_calibration_report as scr  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION_V4,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)


def _seq(n, default, overrides=None):
    vals = [float(default)] * n
    for i, v in (overrides or {}).items():
        vals[i] = float(v)
    return tuple(vals)


def _mk_v4(n_beats=24, **series_over):
    base = tuple(0.0 for _ in range(n_beats))
    series = {k: base for k in V4_SERIES_KEYS}
    for k, v in series_over.items():
        assert len(v) == n_beats, f"{k}: {len(v)} != {n_beats}"
        series[k] = tuple(float(x) for x in v)
    sub4 = {k: tuple((0.0, 0.0, 0.0, 0.0) for _ in range(n_beats)) for k in V4_SUB4_KEYS}
    scalars = {k: 0.0 for k in V4_SCALAR_KEYS}
    return SpectralFeaturesV4(
        sr=22050, schema_version=SCHEMA_VERSION_V4, n_beats=n_beats,
        duration_s=n_beats * 0.5, frame_hop_s=0.0232,
        sub_bass_envelope=base, kick_envelope=base, low_mid_envelope=base,
        high_mid_envelope=base, high_band_envelope=base, kick_max_envelope=base,
        onset_strength_envelope=base, spectral_flatness_envelope=base,
        series=series, sub4=sub4, growl_band_frames=base, scalars=scalars,
    )


def _vec(**over):
    v = {"coverage": 16.0, "attack_low_p90": 0.0, "bpm": 128.0, "air_db": 0.0,
         "sub_db": 0.0, "onset_density_mh": 0.0, "growl_flatness": 0.0,
         "high_db": 0.0, "mid_db": 0.0, "low_swing_db": 0.0, "bass_db": 0.0,
         "full_db": 0.0}
    v.update(over)
    return v


class TolerantScanTests(unittest.TestCase):
    def test_gone_run_ending_at_drop(self):
        sub = _seq(24, 30, {i: 0 for i in range(10, 16)})  # gone 10..15
        v4 = _mk_v4(sub_db=sub, bass_db=_seq(24, 0))
        e, start, raw_gap, duty = scr.tolerant_scan(v4, 16)
        self.assertEqual((e, start, raw_gap), (15, 10, 6))
        self.assertEqual(duty, 0.0)

    def test_no_gone_beat_in_pickup_window(self):
        v4 = _mk_v4(sub_db=_seq(24, 30), bass_db=_seq(24, 0))
        self.assertIsNone(scr.tolerant_scan(v4, 16))

    def test_run_bass_duty(self):
        sub = _seq(24, 30, {i: 0 for i in range(10, 16)})
        bass = _seq(24, 0, {10: 10, 11: 10, 12: 10})  # 3 of 6 run beats >= 8
        v4 = _mk_v4(sub_db=sub, bass_db=bass)
        _, _, _, duty = scr.tolerant_scan(v4, 16)
        self.assertAlmostEqual(duty, 0.5)


class DarknessTests(unittest.TestCase):
    def test_plain_blackout(self):
        sub = _seq(24, 30, {i: 0 for i in range(10, 16)})
        v4 = _mk_v4(sub_db=sub, bass_db=_seq(24, 0))
        d = scr.darkness_decision(v4, 16)
        self.assertEqual(d["kind"], "blackout")
        self.assertEqual((d["gap"], d["dark_beats"]), (6, 6))
        self.assertIsNone(d["abort_at"])
        self.assertFalse(d["capped"])

    def test_capped_at_16(self):
        sub = _seq(40, 30, {i: 0 for i in range(4, 32)})  # 28-beat run ending at 31
        v4 = _mk_v4(40, sub_db=sub, bass_db=_seq(40, 0))
        d = scr.darkness_decision(v4, 32)
        self.assertEqual(d["kind"], "blackout")
        self.assertEqual(d["gap"], 16)
        self.assertTrue(d["capped"])

    def test_floor_returned_abort(self):
        # gone 10..13, floor back (present) at 14,15 -> abort inside window
        sub = _seq(24, 30, {10: 0, 11: 0, 12: 0, 13: 0})
        v4 = _mk_v4(sub_db=sub, bass_db=_seq(24, 0))
        d = scr.darkness_decision(v4, 16)
        self.assertEqual(d["kind"], "blackout")
        self.assertEqual(d["abort_at"], 14)
        self.assertEqual(d["dark_beats"], 2)  # window [12,16): 12,13 dark; 14,15 present

    def test_zero_dark_at_entry(self):
        # 2-beat gone run ending at D-4 -> short window lands entirely on the pickup
        sub = _seq(24, 30, {11: 0, 12: 0})   # e=12 (in [12,15]), raw_gap=2, window [14,16)
        v4 = _mk_v4(sub_db=sub, bass_db=_seq(24, 0))
        d = scr.darkness_decision(v4, 16)
        self.assertEqual(d["kind"], "blackout")
        self.assertEqual(d["dark_beats"], 0)
        self.assertTrue(d["zero_dark"])

    def test_busy_build_kill(self):
        sub = _seq(24, 30, {i: 0 for i in range(10, 16)})
        bass = _seq(24, 30)  # every run beat >= 8 -> duty 1.0 > 0.85
        v4 = _mk_v4(sub_db=sub, bass_db=bass, growl_band_db=_seq(24, 30))
        d = scr.darkness_decision(v4, 16)
        self.assertTrue(d["busy_kill"])
        self.assertEqual(d["kind"], "snap")  # no gone-blackout, no dip, flat growl

    def test_relative_dip(self):
        full = _seq(24, 30, {15: 20})   # 10 dB duck at D-1, floor present
        v4 = _mk_v4(sub_db=_seq(24, 30), full_db=full)
        d = scr.darkness_decision(v4, 16)
        self.assertEqual(d["kind"], "dip")

    def test_perc_flick(self):
        growl = _seq(24, 30, {15: 20})  # growl[15] <= growl[14]-5
        v4 = _mk_v4(sub_db=_seq(24, 30), full_db=_seq(24, 30), growl_band_db=growl)
        d = scr.darkness_decision(v4, 16)
        self.assertEqual(d["kind"], "perc-flick")

    def test_snap(self):
        v4 = _mk_v4(sub_db=_seq(24, 30), full_db=_seq(24, 30), growl_band_db=_seq(24, 30))
        d = scr.darkness_decision(v4, 16)
        self.assertEqual(d["kind"], "snap")


class FamilyClassifierTests(unittest.TestCase):
    def test_thin_coverage_neutral(self):
        self.assertEqual(scr.classify_family(_vec(coverage=4), 0.0, 0), "NEUTRAL")

    def test_marker_without_hit_neutral(self):
        self.assertEqual(
            scr.classify_family(_vec(attack_low_p90=3), -8.0, 0), "NEUTRAL")

    def test_comet(self):
        v = _vec(bpm=150, air_db=-2, sub_db=25, onset_density_mh=3.0)
        self.assertEqual(scr.classify_family(v, -3.0, 0), "COMET")

    def test_wall_growl(self):
        v = _vec(growl_flatness=0.30, high_db=5)
        self.assertEqual(scr.classify_family(v, -3.0, 0), "WALL")

    def test_wall_trap_vacuum(self):
        v = _vec(sub_db=27, onset_density_mh=2.0)
        self.assertEqual(scr.classify_family(v, -3.0, 2), "WALL")

    def test_wall_dense(self):
        v = _vec(onset_density_mh=4.0, high_db=6)
        self.assertEqual(scr.classify_family(v, -3.0, 0), "WALL")

    def test_house_stab(self):
        v = _vec(bpm=128, low_swing_db=11, attack_low_p90=8)
        self.assertEqual(scr.classify_family(v, -3.0, 0), "HOUSE")

    def test_house_growl_bar(self):
        v = _vec(bpm=128, growl_flatness=0.20, sub_db=22, low_swing_db=9, bass_db=15)
        self.assertEqual(scr.classify_family(v, -3.0, 0), "HOUSE")

    def test_first_match_wins_comet_over_wall_trap(self):
        # satisfies both COMET (checked first) and the trap-vacuum WALL rule
        v = _vec(bpm=150, air_db=-2, sub_db=27, onset_density_mh=2.0)
        self.assertEqual(scr.classify_family(v, -3.0, 2), "COMET")

    def test_otherwise_neutral(self):
        self.assertEqual(scr.classify_family(_vec(bpm=100), -3.0, 0), "NEUTRAL")


class ViolenceTierTests(unittest.TestCase):
    def test_max_violence_tier3(self):
        v = _vec(full_db=18, attack_low_p90=16, onset_density_mh=4)
        score, tier = scr.violence_tier(v, 1.0, 8)  # every clip term saturates to 1.0
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(tier, 3)

    def test_low_violence_tier1(self):
        v = _vec(full_db=8, attack_low_p90=8, onset_density_mh=2)
        # 0 + 0 + 0.25*0.5 + 0.15*0.5 + 0 = 0.125+0.075 = 0.20
        score, tier = scr.violence_tier(v, -4.0, 0)
        self.assertAlmostEqual(score, 0.20)
        self.assertEqual(tier, 1)

    def test_tier_cut_boundaries(self):
        # craft exact scores by the attack term alone (0.25*clip(a/16))
        v_lo = _vec(full_db=13, attack_low_p90=8, onset_density_mh=2)  # 0.15+0.125+0.075=0.35
        self.assertEqual(scr.violence_tier(v_lo, -4.0, 0)[1], 1)
        v_hi = _vec(full_db=18, attack_low_p90=16, onset_density_mh=3)
        # 0.30 + 0 + 0.25 + 0.15*0.75 = 0.30+0.25+0.1125 = 0.6625 -> tier 2
        self.assertEqual(scr.violence_tier(v_hi, -4.0, 0)[1], 2)


class BassForwardTests(unittest.TestCase):
    def test_bk_pattern(self):
        n = 24
        growl = _seq(n, 20)
        attack = _seq(n, 5, {1: 10})  # beat index 1 kick-driven
        v4 = _mk_v4(n, growl_band_db=growl, attack_low_db=attack)
        self.assertEqual(scr.bass_forward_pattern(v4, 0, width=4), "BKBB")

    def test_neither_when_growl_below_floor(self):
        n = 24
        growl = _seq(n, 10)      # below the 18 dB real-bass floor
        attack = _seq(n, 5)      # not kick-driven
        v4 = _mk_v4(n, growl_band_db=growl, attack_low_db=attack)
        self.assertEqual(scr.bass_forward_pattern(v4, 0, width=4), "....")

    def test_kick_precedence(self):
        n = 24
        growl = _seq(n, 25)          # would be B on growl alone
        attack = _seq(n, 12)         # but attack >= 9 -> K wins
        v4 = _mk_v4(n, growl_band_db=growl, attack_low_db=attack)
        self.assertEqual(scr.bass_forward_pattern(v4, 0, width=4), "KKKK")


if __name__ == "__main__":
    unittest.main()
