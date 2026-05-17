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


def _fake_deps(*, mel=None, load_raises: bool = False):
    class FakeLibrosa:
        def load(self, path, sr=22050, mono=True):
            if load_raises:
                raise RuntimeError("decode failed")
            return np.ones(sr, dtype=float), sr

        def mel_frequencies(self, n_mels, fmin, fmax):
            return np.linspace(fmin, fmax, n_mels)

        def frames_to_time(self, frames, sr, hop_length):
            return frames * hop_length / sr

    fake = FakeLibrosa()
    fake.feature = SimpleNamespace(
        melspectrogram=lambda **kwargs: (
            mel if mel is not None else np.ones((128, 40), dtype=float)
        )
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
        self.assertEqual(len(features.high_band_envelope), 4)

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


if __name__ == "__main__":
    unittest.main()
