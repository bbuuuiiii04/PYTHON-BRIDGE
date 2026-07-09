"""Tests for tools/stems_pilot_metrics.py — pure STEMS PILOT metrics + gate.

No torch, no network, no audio files. numpy + the bridge's own v4 beat-span /
Goertzel helpers only.
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # rb_ss_bridge_v2 package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # the metrics module

import stems_pilot_metrics as spm  # noqa: E402
import stems_pilot as sp  # noqa: E402  (must import with no torch/demucs installed)


class StemBeatEnvelopesTests(unittest.TestCase):
    def test_per_beat_and_quarter_db_with_empty_span_fallback(self):
        # 3 beats: [0,1000),[1000,2000),[2000,3000). Frames every 500 ms.
        frame_times_ms = [0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0]
        power = [1.0, 1.0, 10.0, 10.0, 100.0, 100.0]
        beatgrid = [0.0, 1000.0, 2000.0]
        env = spm.stem_beat_envelopes({"full": power}, frame_times_ms, beatgrid)
        # arithmetic mean of linear power per beat -> dB
        self.assertEqual(env["full"]["beat"], (0.0, 10.0, 20.0))
        # first beat's quarter slots [250,500) and [750,1000) hold no frame ->
        # nearest-frame fallback (both land on a power-1.0 frame -> 0.0 dB).
        self.assertEqual(env["full"]["quarter"][0], (0.0, 0.0, 0.0, 0.0))


class ReconstructionDeltaTests(unittest.TestCase):
    def setUp(self):
        self.frame_times_ms = [0.0, 500.0, 1000.0, 1500.0]
        self.beatgrid = [0.0, 1000.0, 2000.0]

    def test_identical_arrays_zero(self):
        frames = [1.0, 1.0, 1.0, 1.0]
        delta = spm.reconstruction_delta_db(frames, frames, self.frame_times_ms, self.beatgrid)
        self.assertTrue(all(d == 0.0 for d in delta))

    def test_three_db_offset(self):
        mix = [1.0, 1.0, 1.0, 1.0]
        summed = [10.0 ** 0.3] * 4  # +3.0 dB in power
        delta = spm.reconstruction_delta_db(mix, summed, self.frame_times_ms, self.beatgrid)
        for d in delta:
            self.assertAlmostEqual(d, 3.0, places=3)


class PumpVisibilityTests(unittest.TestCase):
    def test_pumped_sub_at_kick(self):
        # drum kick leads slot 0; bass sub ducked on slot 0, recovers 1..3.
        drums = [[10.0, 0.0, 0.0, 0.0], [10.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 0.0]]
        bass = [[0.0, 5.0, 5.0, 5.0], [0.0, 5.0, 5.0, 5.0], [0.0, 5.0, 5.0, 5.0]]
        # third beat is not slot-0-led (kick in slot 1) -> skipped.
        self.assertAlmostEqual(spm.pump_visibility(bass, drums), 5.0, places=2)

    def test_flat_sustain_no_pump(self):
        drums = [[10.0, 0.0, 0.0, 0.0]] * 4
        bass = [[5.0, 5.0, 5.0, 5.0]] * 4
        self.assertEqual(spm.pump_visibility(bass, drums), 0.0)


class GhostMarginTests(unittest.TestCase):
    def test_quiet_instrumental_windows_negative_margin(self):
        vocal = [-10.0] * 10 + [-40.0] * 5 + [-10.0] * 5
        margin = spm.ghost_margin_db(vocal, [(10, 15)])
        self.assertLess(margin, -12.0)
        self.assertAlmostEqual(margin, -30.0, places=1)

    def test_no_windows_zero(self):
        self.assertEqual(spm.ghost_margin_db([-10.0, -12.0], []), 0.0)


class ModulationStrengthTests(unittest.TestCase):
    def _synth(self, target_cpb):
        # 4-beat window at 120 BPM; 128 analysis frames across the window.
        beatgrid = [0.0, 500.0, 1000.0, 1500.0, 2000.0]
        n = 160
        hop_ms = 2000.0 / 128.0
        cycles_total = target_cpb * 4.0
        frames = [
            -20.0 + 3.0 * math.sin(2.0 * math.pi * cycles_total * i / 128.0)
            for i in range(n)
        ]
        return frames, hop_ms / 1000.0, beatgrid

    def test_slow_one_cpb_readable_ungated(self):
        frames, hop_s, grid = self._synth(1.0)
        rate, conc = spm.modulation_strength(frames, hop_s, grid, (0, 4))
        self.assertLess(abs(rate - 1.0) / 1.0, 0.12)  # nearest grid cell ~1.028
        self.assertGreater(conc, 0.0)

    def test_fast_five_cpb(self):
        frames, hop_s, grid = self._synth(5.0)
        rate, conc = spm.modulation_strength(frames, hop_s, grid, (0, 4))
        self.assertLess(abs(rate - 5.0) / 5.0, 0.12)
        self.assertGreater(conc, 0.0)

    def test_short_data_returns_zero(self):
        self.assertEqual(spm.modulation_strength([0.0] * 4, 0.01, [0, 500, 1000, 1500], (0, 3)), (0.0, 0.0))


class EvaluateGatesTests(unittest.TestCase):
    def _clean_pass(self):
        return {
            "operational": {"separated_ok_frac": 0.95, "peak_rss_gb": 5.9},
            "reconstruction": {"tracks_within_frac": 0.95},
            "sidechain": {"anchors_pumped": 3},
            "vocal": {"pair_separates": True, "ghost_margin_db": -15.0},
            "wobble": {"moments_detected": 3},
            "elements": {
                "wobble": "PASS", "sidechain_sub": "PASS", "rolls": "PASS",
                "eight08s": "PASS", "screeches": "PASS", "distorted_kicks": "PASS",
                "claps_snares": "PASS", "offbeat_hats": "PARTIAL", "vocal_axis": "PARTIAL",
            },
        }

    def test_clean_pass(self):
        res = spm.evaluate_gates(self._clean_pass(), {})
        self.assertEqual(res["verdict"], "PASS")
        self.assertEqual(res["call_off_reasons"], [])
        self.assertEqual(res["elements_pass"], 7)

    def test_single_criterion_fails(self):
        cases = {
            "operational": {"operational": {"separated_ok_frac": 0.5, "peak_rss_gb": 5.9}},
            "operational_rss": {"operational": {"separated_ok_frac": 0.95, "peak_rss_gb": 7.0}},
            "reconstruction": {"reconstruction": {"tracks_within_frac": 0.5}},
            "sidechain": {"sidechain": {"anchors_pumped": 1}},
            "vocal_pair": {"vocal": {"pair_separates": False, "ghost_margin_db": -15.0}},
            "vocal_ghost": {"vocal": {"pair_separates": True, "ghost_margin_db": -5.0}},
            "wobble": {"wobble": {"moments_detected": 1}},
        }
        expected_reason = {
            "operational": "operational", "operational_rss": "operational",
            "reconstruction": "reconstruction", "sidechain": "sidechain",
            "vocal_pair": "vocal", "vocal_ghost": "vocal", "wobble": "wobble",
        }
        for name, override in cases.items():
            sc = self._clean_pass()
            sc.update(override)
            res = spm.evaluate_gates(sc, {})
            self.assertEqual(res["verdict"], "FAIL", name)
            self.assertIn(expected_reason[name], res["call_off_reasons"], name)

    def test_named_element_floor_below_six_fails(self):
        sc = self._clean_pass()
        # drop to 5 PASS (no outright FAIL) -> named_element_floor fails.
        sc["elements"]["rolls"] = "PARTIAL"
        sc["elements"]["screeches"] = "PARTIAL"
        res = spm.evaluate_gates(sc, {})
        self.assertEqual(res["verdict"], "FAIL")
        self.assertIn("named_element_floor", res["call_off_reasons"])

    def test_any_element_full_fail_blocks_floor(self):
        sc = self._clean_pass()
        sc["elements"]["vocal_axis"] = "FAIL"  # still 7 PASS but one fails everywhere
        res = spm.evaluate_gates(sc, {})
        self.assertEqual(res["verdict"], "FAIL")
        self.assertIn("named_element_floor", res["call_off_reasons"])


class RunnerGuardTests(unittest.TestCase):
    def test_disk_floor_refuses_below_and_runs_above(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        with patch.object(sp.shutil, "disk_usage", return_value=SimpleNamespace(free=3.0e9)):
            self.assertFalse(sp._disk_ok(4.0))
            self.assertFalse(sp._disk_ok(10.0))
        with patch.object(sp.shutil, "disk_usage", return_value=SimpleNamespace(free=12.0e9)):
            self.assertTrue(sp._disk_ok(4.0))
            self.assertTrue(sp._disk_ok(10.0))

    def test_existing_envelope_json_is_resumable_skip(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            env_dir = Path(d)
            # a real file so _cache_key can stat it (any bytes; grid is fixed).
            audio = env_dir / "track.wav"
            audio.write_bytes(b"\x00\x01")
            grid = [0.0, 500.0, 1000.0]
            key = sp._cache_key(str(audio), grid)
            self.assertIsNotNone(key)
            env_path = env_dir / f"{key}.json"
            self.assertFalse(bool(key and env_path.exists()))   # nothing cached yet
            env_path.write_text(json.dumps({"n_beats": 3}))
            self.assertTrue(bool(key and env_path.exists()))    # now the loop would skip + reload


if __name__ == "__main__":
    unittest.main()
