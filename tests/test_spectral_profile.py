import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_profile  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION,
    SCHEMA_VERSION_V4,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)


def _v4(series_overrides=None, sub4_overrides=None, scalars_overrides=None, n_beats=8):
    beats = tuple(float(i) for i in range(n_beats))
    series = {key: beats for key in V4_SERIES_KEYS}
    if series_overrides:
        series.update(series_overrides)
    sub4 = {
        key: tuple((0.0, 0.0, 0.0, 0.0) for _ in range(n_beats)) for key in V4_SUB4_KEYS
    }
    if sub4_overrides:
        sub4.update(sub4_overrides)
    scalars = {key: 0.5 for key in V4_SCALAR_KEYS}
    if scalars_overrides:
        scalars.update(scalars_overrides)
    return SpectralFeaturesV4(
        sr=22050,
        schema_version=SCHEMA_VERSION_V4,
        n_beats=n_beats,
        duration_s=n_beats * 0.5,
        frame_hop_s=0.0232,
        sub_bass_envelope=beats,
        kick_envelope=(0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0)[:n_beats],
        low_mid_envelope=beats,
        high_mid_envelope=beats,
        high_band_envelope=beats,
        kick_max_envelope=beats,
        onset_strength_envelope=beats,
        spectral_flatness_envelope=(0.1,) * n_beats,
        series=series,
        sub4=sub4,
        growl_band_frames=(0.0, 1.0),
        scalars=scalars,
    )


class CompatViewTests(unittest.TestCase):
    def test_compat_features_is_the_v3_view(self) -> None:
        v4 = _v4()
        compat = spectral_profile.compat_features(v4)
        self.assertEqual(compat.schema_version, SCHEMA_VERSION)
        self.assertEqual(compat.sub_bass_envelope, v4.sub_bass_envelope)
        self.assertEqual(compat.kick_envelope, v4.kick_envelope)
        self.assertEqual(compat.spectral_flatness_envelope, v4.spectral_flatness_envelope)


class PercentileTests(unittest.TestCase):
    def test_linear_interpolation(self) -> None:
        self.assertEqual(spectral_profile.percentile([0.0, 10.0], 50.0), 5.0)
        self.assertEqual(spectral_profile.percentile([1.0, 2.0, 3.0], 0.0), 1.0)
        self.assertEqual(spectral_profile.percentile([1.0, 2.0, 3.0], 100.0), 3.0)
        self.assertEqual(spectral_profile.percentile([], 50.0), 0.0)


class SilencePrimitiveTests(unittest.TestCase):
    def test_empty_floor_vs_true_silence(self) -> None:
        # beats 0-2: loud; 3-4 bottom gone but music playing; 5-7 literal silence
        sub = (30.0, 30.0, 30.0, -20.0, -20.0, -60.0, -60.0, -60.0)
        bass = (20.0, 20.0, 20.0, -10.0, -10.0, -60.0, -60.0, -60.0)
        full = (15.0, 15.0, 15.0, 8.0, 8.0, -80.0, -80.0, -80.0)
        v4 = _v4({"sub_db": sub, "bass_db": bass, "full_db": full})
        runs = spectral_profile.empty_floor_runs(v4)
        self.assertEqual(runs, [(3, 4, "empty_floor"), (5, 7, "true_silence")])

    def test_no_floor_absence_yields_no_runs(self) -> None:
        v4 = _v4({
            "sub_db": (30.0,) * 8,
            "bass_db": (20.0,) * 8,
            "full_db": (15.0,) * 8,
        })
        self.assertEqual(spectral_profile.empty_floor_runs(v4), [])

    def test_pre_drop_gap_beats(self) -> None:
        sub = (30.0, 30.0, 30.0, 30.0, -20.0, -20.0, -20.0, 30.0)
        bass = (20.0, 20.0, 20.0, 20.0, -10.0, -10.0, -10.0, 20.0)
        v4 = _v4({"sub_db": sub, "bass_db": bass})
        self.assertEqual(spectral_profile.pre_drop_gap_beats(v4, 7), 3)
        self.assertEqual(spectral_profile.pre_drop_gap_beats(v4, 4), 0)
        self.assertEqual(spectral_profile.pre_drop_gap_beats(v4, 0), 0)


class IdentityAxesTests(unittest.TestCase):
    def test_axes_read_scalars_and_derive_bass(self) -> None:
        sub = (30.0, 30.0, -20.0, -20.0, 30.0, 30.0, 30.0, 30.0)
        v4 = _v4(
            {"sub_db": sub},
            scalars_overrides={"grit": 0.12, "punch": 0.9, "drama": 14.0},
        )
        axes = spectral_profile.identity_axes(v4)
        self.assertEqual(axes["grit"], 0.12)
        self.assertEqual(axes["punch"], 0.9)
        self.assertEqual(axes["drama"], 14.0)
        self.assertEqual(axes["bass"], 0.75)  # 6 of 8 beats above threshold


class TextureClassTests(unittest.TestCase):
    def test_roll_flags_and_acceleration(self) -> None:
        v4 = _v4({
            "onset_density_midhigh": (0.0, 0.0, 1.0, 1.0, 3.0, 4.0, 5.0, 6.0),
            "fluxsum_midhigh": (10.0, 10.0, 10.0, 10.0, 40.0, 50.0, 60.0, 70.0),
        })
        flags = spectral_profile.roll_flags(v4)
        self.assertEqual(flags, [False, False, False, False, True, True, True, True])
        self.assertGreater(spectral_profile.roll_acceleration(v4, 7), 0.0)

    def test_stab_and_sustain_are_mutually_sensible(self) -> None:
        sub = (30.0,) * 8
        bass = (20.0,) * 8
        stab_sub4 = tuple((10.0, 22.0, 10.0, 8.0) for _ in range(8))
        v4 = _v4(
            {
                "sub_db": sub,
                "bass_db": bass,
                "attack_low_db": (15.0,) * 8,
            },
            sub4_overrides={"bass": stab_sub4},
        )
        self.assertTrue(all(spectral_profile.stab_flags(v4)))
        self.assertFalse(any(spectral_profile.sustained_bass_flags(v4)))

        flat_sub4 = tuple((20.0, 20.5, 20.0, 20.2) for _ in range(8))
        v4b = _v4(
            {
                "sub_db": sub,
                "bass_db": bass,
                "attack_low_db": (2.0,) * 8,
            },
            sub4_overrides={"bass": flat_sub4},
        )
        self.assertFalse(any(spectral_profile.stab_flags(v4b)))
        self.assertTrue(all(spectral_profile.sustained_bass_flags(v4b)))

    def test_growl_and_sustained_synth_flags(self) -> None:
        v4 = _v4({
            "growl_flatness": (0.35,) * 8,
            "growl_band_db": (20.0,) * 8,
            "sustain_mid_db": (18.0,) * 8,
        })
        self.assertTrue(all(spectral_profile.growl_flags(v4)))
        self.assertFalse(any(spectral_profile.sustained_synth_flags(v4)))

        v4b = _v4({
            "growl_flatness": (0.05,) * 8,
            "growl_band_db": (20.0,) * 8,
            "sustain_mid_db": (18.0,) * 8,
        })
        self.assertFalse(any(spectral_profile.growl_flags(v4b)))
        self.assertTrue(all(spectral_profile.sustained_synth_flags(v4b)))


class DropWindowVectorTests(unittest.TestCase):
    def test_vector_reports_coverage_and_descriptors(self) -> None:
        v4 = _v4({
            "sub_db": (30.0,) * 8,
            "bass_db": (20.0,) * 8,
        })
        vec = spectral_profile.drop_window_vector(v4, 2, width=4)
        self.assertEqual(vec["coverage"], 4.0)
        self.assertIn("attack_low_p90", vec)
        self.assertIn("pre_gap_beats", vec)
        self.assertGreater(vec["bpm"], 0.0)
        self.assertNotIn("pulse_frac", vec)  # omitted unless flags supplied

    def test_vector_includes_pulse_frac_when_flags_supplied(self) -> None:
        v4 = _v4()
        flags = [False, False, True, True, False, False, False, False]
        vec = spectral_profile.drop_window_vector(v4, 2, width=4, wobble=flags)
        self.assertEqual(vec["pulse_frac"], 0.5)

    def test_vector_out_of_range_reports_zero_coverage(self) -> None:
        v4 = _v4()
        self.assertEqual(spectral_profile.drop_window_vector(v4, 99), {"coverage": 0.0})


def _flat_series(n_beats):
    return {
        "full_db": (14.0,) * n_beats,
        "sub_db": (30.0,) * n_beats,
        "bass_db": (20.0,) * n_beats,
        "perc_full": (0.3,) * n_beats,
        "centroid_hz": (700.0,) * n_beats,
        "growl_flatness": (0.1,) * n_beats,
        "onset_density_midhigh": (1.0,) * n_beats,
        "sustain_mid_db": (12.0,) * n_beats,
    }


def _pulse_v4(n_beats=32, frames_per_beat=20, mod_cpb=0.0, mod_db=3.0,
              mod_range=None, base_db=20.0):
    """Consistent fixture: beat = 0.5 s, frame hop = 25 ms, synthetic frames."""
    n_frames = n_beats * frames_per_beat
    frames = []
    for i in range(n_frames):
        beat_pos = i / frames_per_beat
        level = base_db
        in_mod = mod_range is None or (mod_range[0] <= beat_pos < mod_range[1])
        if mod_cpb > 0.0 and in_mod:
            level += mod_db * math.sin(2.0 * math.pi * mod_cpb * beat_pos)
        frames.append(round(level, 1))
    v4 = _v4(_flat_series(n_beats), n_beats=n_beats)
    object.__setattr__(v4, "growl_band_frames", tuple(frames))
    object.__setattr__(v4, "frame_hop_s", 0.025)
    object.__setattr__(v4, "duration_s", n_beats * 0.5)
    return v4, [i * 500.0 for i in range(n_beats)]


class LowmidPulseTests(unittest.TestCase):
    def test_fast_pulse_fires_and_slow_metric_pump_does_not(self) -> None:
        fast, grid = _pulse_v4(mod_cpb=4.0)
        flags = spectral_profile.lowmid_pulse_flags(fast, grid)
        self.assertTrue(any(flags))
        # 2.0 cycles/beat is a metric-rate pump (kick pattern) — must NOT flag
        slow, grid2 = _pulse_v4(mod_cpb=2.0)
        self.assertFalse(any(spectral_profile.lowmid_pulse_flags(slow, grid2)))

    def test_measure_reads_correct_rate(self) -> None:
        v4, grid = _pulse_v4(mod_cpb=4.0)
        duty, cpb, conc = spectral_profile.lowmid_pulse_measure(v4, grid, 16)
        self.assertGreaterEqual(duty, 0.9)
        self.assertAlmostEqual(cpb, 3.881, delta=0.6)  # nearest grid bins to 4.0
        self.assertGreaterEqual(conc, 0.10)

    def test_silent_and_constant_windows_produce_no_flags(self) -> None:
        silent, grid = _pulse_v4(mod_cpb=0.0, base_db=-100.0)
        self.assertFalse(any(spectral_profile.lowmid_pulse_flags(silent, grid)))
        constant, grid2 = _pulse_v4(mod_cpb=0.0, base_db=20.0)
        self.assertFalse(any(spectral_profile.lowmid_pulse_flags(constant, grid2)))

    def test_edge_beats_do_not_raise(self) -> None:
        v4, grid = _pulse_v4(mod_cpb=4.0)
        for b in (0, 1, v4.n_beats - 2, v4.n_beats - 1, -5, 999):
            duty, cpb, conc = spectral_profile.lowmid_pulse_measure(v4, grid, b)
            self.assertGreaterEqual(duty, 0.0)

    def test_absent_grid_means_no_flags(self) -> None:
        v4, _ = _pulse_v4(mod_cpb=4.0)
        self.assertFalse(any(spectral_profile.lowmid_pulse_flags(v4, [])))
        self.assertEqual(
            spectral_profile.lowmid_pulse_measure(v4, [1.0, 2.0], 5), (0.0, 0.0, 0.0)
        )

    def test_persistence_drops_isolated_blips(self) -> None:
        v4, grid = _pulse_v4()
        firing = {5: (1.0, 4.0, 0.5), 10: (1.0, 4.0, 0.5), 11: (1.0, 4.0, 0.5)}

        def fake_measure(_v4, _grid, beat):
            return firing.get(beat, (0.0, 0.0, 0.0))

        with patch.object(spectral_profile, "lowmid_pulse_measure", fake_measure):
            flags = spectral_profile.lowmid_pulse_flags(v4, grid)
        self.assertFalse(flags[5])          # isolated single beat: dropped
        self.assertTrue(flags[10] and flags[11])  # 2-beat run: kept (min_run 2)

    def test_goertzel_matches_direct_dft_at_non_integer_bin(self) -> None:
        x = [0.3, -0.7, 1.1, 0.2, -0.4, 0.9, -1.2, 0.5, 0.1, -0.6]
        cycles = 2.37  # deliberately not an integer bin
        w = 2.0 * math.pi * cycles / len(x)
        direct = abs(sum(v * complex(math.cos(w * n), -math.sin(w * n))
                         for n, v in enumerate(x))) ** 2
        self.assertAlmostEqual(
            spectral_profile._goertzel_power(x, cycles), direct, places=6
        )

    def test_flags_are_deterministic(self) -> None:
        v4, grid = _pulse_v4(mod_cpb=4.0, mod_range=(8, 20))
        self.assertEqual(
            spectral_profile.lowmid_pulse_flags(v4, grid),
            spectral_profile.lowmid_pulse_flags(v4, grid),
        )


class SectionMapTests(unittest.TestCase):
    def _two_character_v4(self, n_beats=64):
        half = n_beats // 2
        overrides = dict(_flat_series(n_beats))
        overrides["full_db"] = (0.0,) * half + (16.0,) * half
        overrides["centroid_hz"] = (400.0,) * half + (1400.0,) * half
        return _v4(
            overrides,
            scalars_overrides={"loudness_ref_db": 16.0},
            n_beats=n_beats,
        )

    def test_two_characters_yield_two_sections_with_tiers(self) -> None:
        v4 = self._two_character_v4()
        sections = spectral_profile.section_map(v4)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["start_beat"], 0)
        self.assertEqual(sections[0]["energy_tier"], "quiet")
        self.assertEqual(sections[1]["start_beat"], 32)
        self.assertEqual(sections[1]["energy_tier"], "loud")

    def test_uniform_track_merges_to_one_section(self) -> None:
        v4 = _v4(_flat_series(64), n_beats=64)
        self.assertEqual(len(spectral_profile.section_map(v4)), 1)

    def test_drop_marker_splits_identical_blocks(self) -> None:
        v4 = _v4(_flat_series(64), n_beats=64)
        sections = spectral_profile.section_map(v4, drops=[32])
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[1]["start_beat"], 32)

    def test_section_map_is_deterministic(self) -> None:
        v4 = self._two_character_v4()
        self.assertEqual(
            spectral_profile.section_map(v4, drops=[40]),
            spectral_profile.section_map(v4, drops=[40]),
        )


if __name__ == "__main__":
    unittest.main()
