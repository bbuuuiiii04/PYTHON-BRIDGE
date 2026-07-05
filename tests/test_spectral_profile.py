import sys
import unittest
from pathlib import Path

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

    def test_vector_out_of_range_reports_zero_coverage(self) -> None:
        v4 = _v4()
        self.assertEqual(spectral_profile.drop_window_vector(v4, 99), {"coverage": 0.0})


if __name__ == "__main__":
    unittest.main()
