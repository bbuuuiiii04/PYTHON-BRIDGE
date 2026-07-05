import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from rb_ss_bridge_v2 import audio_spectral_features as spectral  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import SpectralFeatures  # noqa: E402


def _fake_deps(*, mel=None, load_raises: bool = False, n_frames: int = 40):
    class FakeLibrosa:
        def load(self, path, sr=22050, mono=True):
            if load_raises:
                raise RuntimeError("decode failed")
            return np.ones(sr, dtype=float), sr

        def mel_frequencies(self, n_mels, fmin, fmax):
            return np.linspace(fmin, fmax, n_mels)

        def frames_to_time(self, frames, sr, hop_length):
            return frames * hop_length / sr

        def stft(self, y, n_fft=2048, hop_length=512):
            return np.ones((n_fft // 2 + 1, n_frames), dtype=float)

        def fft_frequencies(self, sr=22050, n_fft=2048):
            return np.linspace(0.0, sr / 2.0, n_fft // 2 + 1)

        def power_to_db(self, S, **kwargs):
            return 10.0 * np.log10(np.maximum(S, 1e-10))

    def _onset_strength(**kwargs):
        S = kwargs.get("S")
        if S is not None:
            return np.ones(S.shape[-1], dtype=float)
        return np.ones(n_frames, dtype=float)

    fake = FakeLibrosa()
    fake.onset = SimpleNamespace(
        onset_strength=_onset_strength,
        onset_detect=lambda **kwargs: np.asarray([5, 20], dtype=int),
    )
    fake.feature = SimpleNamespace(
        melspectrogram=lambda **kwargs: (
            mel if mel is not None else np.ones((128, n_frames), dtype=float)
        ),
        spectral_flatness=lambda **kwargs: np.ones((1, n_frames), dtype=float) * 0.25,
    )
    fake.filters = SimpleNamespace(
        mel=lambda **kwargs: np.full(
            (kwargs.get("n_mels", 128), kwargs.get("n_fft", 2048) // 2 + 1),
            1e-3,
            dtype=float,
        ),
    )
    fake.decompose = SimpleNamespace(
        hpss=lambda S, **kwargs: (S * 0.6, S * 0.4),
    )
    return fake, np, SimpleNamespace()


@unittest.skipUnless(HAS_NUMPY, "numpy not installed")
class AudioSpectralFeatureTests(unittest.TestCase):
    def test_extract_spectral_features_returns_per_beat_envelopes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(spectral, "_lazy_import_librosa", return_value=_fake_deps()):
                features = spectral.extract_spectral_features(
                    str(audio),
                    [0.0, 500.0, 1000.0, 1500.0],
                )

        self.assertIsInstance(features, SpectralFeatures)
        self.assertEqual(len(features.sub_bass_envelope), 4)
        self.assertEqual(len(features.kick_envelope), 4)
        self.assertEqual(len(features.low_mid_envelope), 4)
        self.assertEqual(len(features.high_mid_envelope), 4)
        self.assertEqual(len(features.high_band_envelope), 4)
        self.assertEqual(len(features.kick_max_envelope), 4)
        self.assertEqual(len(features.onset_strength_envelope), 4)
        self.assertEqual(len(features.spectral_flatness_envelope), 4)
        self.assertEqual(features.schema_version, spectral.SCHEMA_VERSION)

    def test_extract_spectral_features_normalizes_band_envelopes(self) -> None:
        mel = np.ones((128, 40), dtype=float)
        mel[:, 20:] = 10.0
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(spectral, "_lazy_import_librosa", return_value=_fake_deps(mel=mel)):
                features = spectral.extract_spectral_features(
                    str(audio),
                    [0.0, 250.0, 500.0, 750.0],
                )

        self.assertIsNotNone(features)
        self.assertLessEqual(max(features.kick_envelope), 1.0)
        self.assertGreaterEqual(min(features.kick_envelope), 0.0)

    def test_extract_spectral_features_populates_richer_envelopes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(spectral, "_lazy_import_librosa", return_value=_fake_deps()):
                features = spectral.extract_spectral_features(
                    str(audio),
                    [0.0, 250.0, 500.0, 750.0],
                )

        self.assertIsNotNone(features)
        self.assertTrue(
            all(isinstance(value, float) for value in features.kick_max_envelope)
        )
        self.assertTrue(
            all(isinstance(value, float) for value in features.onset_strength_envelope)
        )
        self.assertTrue(
            all(isinstance(value, float) for value in features.spectral_flatness_envelope)
        )

    def test_extract_spectral_features_returns_none_for_missing_audio(self) -> None:
        with patch.object(spectral, "_lazy_import_librosa", return_value=_fake_deps()):
            self.assertIsNone(
                spectral.extract_spectral_features(
                    "/tmp/rbss-missing-audio.wav",
                    [0.0, 500.0],
                )
            )

    def test_lazy_import_returns_none_on_import_error(self) -> None:
        original = spectral._LAZY_IMPORTS
        spectral._LAZY_IMPORTS = None

        def fake_import(name, *args, **kwargs):
            if name == "librosa":
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        real_import = __import__
        try:
            with patch("builtins.__import__", side_effect=fake_import):
                self.assertIsNone(spectral._lazy_import_librosa())
        finally:
            spectral._LAZY_IMPORTS = original

    def test_extract_spectral_features_returns_none_on_decode_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(
                spectral,
                "_lazy_import_librosa",
                return_value=_fake_deps(load_raises=True),
            ):
                self.assertIsNone(
                    spectral.extract_spectral_features(
                        str(audio),
                        [0.0, 500.0],
                    )
                )

    def test_optional_real_audio_fixture(self) -> None:
        fixture_dir = os.environ.get("RBSS_SPECTRAL_FIXTURE_DIR")
        if not fixture_dir:
            self.skipTest("RBSS_SPECTRAL_FIXTURE_DIR not set")
        candidates = []
        for suffix in ("*.wav", "*.mp3", "*.flac", "*.aiff", "*.m4a"):
            candidates.extend(Path(fixture_dir).glob(suffix))
        if not candidates:
            self.skipTest("no audio fixtures found")

        features = spectral.extract_spectral_features(
            str(candidates[0]),
            [i * 500.0 for i in range(16)],
        )
        self.assertIsNotNone(features)


@unittest.skipUnless(HAS_NUMPY, "numpy not installed")
class SpectralV4ExtractionTests(unittest.TestCase):
    GRID = [0.0, 250.0, 500.0, 750.0]

    def _extract(self, **fake_kwargs):
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(
                spectral, "_lazy_import_librosa", return_value=_fake_deps(**fake_kwargs)
            ):
                v4 = spectral.extract_spectral_features_v4(str(audio), self.GRID)
                v3 = spectral.extract_spectral_features(str(audio), self.GRID)
        return v4, v3

    def test_v4_shapes_and_schema(self) -> None:
        v4, _ = self._extract()
        self.assertIsNotNone(v4)
        self.assertEqual(v4.schema_version, spectral.SCHEMA_VERSION_V4)
        self.assertEqual(v4.n_beats, len(self.GRID))
        for key in spectral.V4_SERIES_KEYS:
            self.assertEqual(len(v4.series[key]), v4.n_beats, key)
        for key in spectral.V4_SUB4_KEYS:
            self.assertEqual(len(v4.sub4[key]), v4.n_beats, key)
            self.assertTrue(all(len(slot) == 4 for slot in v4.sub4[key]), key)
        for key in spectral.V4_SCALAR_KEYS:
            self.assertIn(key, v4.scalars)
        self.assertGreater(len(v4.growl_band_frames), 0)
        self.assertGreater(v4.frame_hop_s, 0.0)

    def test_v4_compat_block_matches_v3_extractor(self) -> None:
        v4, v3 = self._extract()
        self.assertIsNotNone(v4)
        self.assertIsNotNone(v3)
        for field in (
            "sub_bass_envelope", "kick_envelope", "low_mid_envelope",
            "high_mid_envelope", "high_band_envelope", "kick_max_envelope",
            "onset_strength_envelope", "spectral_flatness_envelope",
        ):
            self.assertEqual(getattr(v4, field), getattr(v3, field), field)

    def test_v4_is_deterministic(self) -> None:
        first, _ = self._extract()
        second, _ = self._extract()
        self.assertEqual(first, second)

    def test_v4_returns_none_without_enough_beats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(
                spectral, "_lazy_import_librosa", return_value=_fake_deps()
            ):
                self.assertIsNone(
                    spectral.extract_spectral_features_v4(str(audio), [0.0])
                )

    def test_v4_returns_none_on_decode_failure(self) -> None:
        v4, _ = self._extract(load_raises=True)
        self.assertIsNone(v4)

    def test_v4_returns_none_for_missing_audio(self) -> None:
        with patch.object(spectral, "_lazy_import_librosa", return_value=_fake_deps()):
            self.assertIsNone(
                spectral.extract_spectral_features_v4(
                    "/tmp/rbss-missing-audio.wav", self.GRID
                )
            )

    def test_optional_real_audio_bit_identity(self) -> None:
        """Retained bit-identity gate (design §4.10 change 1) — local only.

        Proves the v4 compat block equals the v3 extractor exactly on real
        audio. Skips on CI (no librosa/fixture).
        """
        fixture_dir = os.environ.get("RBSS_SPECTRAL_FIXTURE_DIR")
        if not fixture_dir:
            self.skipTest("RBSS_SPECTRAL_FIXTURE_DIR not set")
        candidates = []
        for suffix in ("*.wav", "*.mp3", "*.flac", "*.aiff"):
            candidates.extend(Path(fixture_dir).glob(suffix))
        if not candidates:
            self.skipTest("no audio fixtures found")
        grid = [i * 500.0 for i in range(16)]
        v3 = spectral.extract_spectral_features(str(candidates[0]), grid)
        v4 = spectral.extract_spectral_features_v4(str(candidates[0]), grid)
        if v3 is None or v4 is None:
            self.skipTest("librosa unavailable for real decode")
        for field in (
            "sub_bass_envelope", "kick_envelope", "low_mid_envelope",
            "high_mid_envelope", "high_band_envelope", "kick_max_envelope",
            "onset_strength_envelope", "spectral_flatness_envelope",
        ):
            self.assertEqual(getattr(v4, field), getattr(v3, field), field)


if __name__ == "__main__":
    unittest.main()
