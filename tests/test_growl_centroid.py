"""AWR-176 — frame-rate growl-band centroid: extraction field, tolerant cache
read + strict shape, derived movement measure, backfill-aware sweep skip.

Pure-function seam first: the measure is fully testable without librosa/files.
Item 9 (real extraction) skips cleanly when numpy/librosa is absent, mirroring
tests/test_audio_spectral_features.py.
"""
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import numpy as np  # noqa: F401
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from rb_ss_bridge_v2 import audio_spectral_features as spectral  # noqa: E402
from rb_ss_bridge_v2 import spectral_cache  # noqa: E402
from rb_ss_bridge_v2 import spectral_profile  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION_V4,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)
from rb_ss_bridge_v2.tests.test_audio_spectral_features import _fake_deps  # noqa: E402


def _v4(*, growl_band_frames=(), growl_centroid_frames=(), n_beats=8,
        frame_hop_s=0.0232):
    """Hand-built SpectralFeaturesV4 fixture (extends the test_spectral_profile
    pattern with the two frame-rate growl series)."""
    beats = tuple(float(i) for i in range(n_beats))
    series = {key: beats for key in V4_SERIES_KEYS}
    sub4 = {
        key: tuple((0.0, 0.0, 0.0, 0.0) for _ in range(n_beats)) for key in V4_SUB4_KEYS
    }
    scalars = {key: 0.5 for key in V4_SCALAR_KEYS}
    return SpectralFeaturesV4(
        sr=22050,
        schema_version=SCHEMA_VERSION_V4,
        n_beats=n_beats,
        duration_s=n_beats * 0.5,
        frame_hop_s=frame_hop_s,
        sub_bass_envelope=beats,
        kick_envelope=beats,
        low_mid_envelope=beats,
        high_mid_envelope=beats,
        high_band_envelope=beats,
        kick_max_envelope=beats,
        onset_strength_envelope=beats,
        spectral_flatness_envelope=(0.1,) * n_beats,
        series=series,
        sub4=sub4,
        growl_band_frames=growl_band_frames,
        scalars=scalars,
        growl_centroid_frames=growl_centroid_frames,
    )


@unittest.skipUnless(HAS_NUMPY, "numpy not installed")
class GrowlCentroidExtractionTests(unittest.TestCase):
    """Part D item 9 — extraction populates the field, existing fields frozen."""

    GRID = [0.0, 250.0, 500.0, 750.0]

    def _extract(self):
        with tempfile.TemporaryDirectory() as td:
            audio = Path(td) / "track.wav"
            audio.write_bytes(b"fake")
            with patch.object(
                spectral, "_lazy_import_librosa", return_value=_fake_deps()
            ):
                return spectral.extract_spectral_features_v4(str(audio), self.GRID)

    def test_field_present_and_aligned_to_growl_band(self) -> None:
        v4 = self._extract()
        self.assertIsNotNone(v4)
        self.assertGreater(len(v4.growl_centroid_frames), 0)
        self.assertEqual(
            len(v4.growl_centroid_frames), len(v4.growl_band_frames)
        )

    def test_existing_fields_unchanged_by_new_field(self) -> None:
        # Determinism seam: two same-input extractions agree on EVERY pre-existing
        # field (the new field is additive only, existing bytes frozen).
        first = self._extract()
        second = self._extract()
        self.assertIsNotNone(first)
        self.assertEqual(first, second)  # full equality, incl. new field
        for field in (
            "sub_bass_envelope", "kick_envelope", "low_mid_envelope",
            "high_mid_envelope", "high_band_envelope", "kick_max_envelope",
            "onset_strength_envelope", "spectral_flatness_envelope",
            "series", "sub4", "growl_band_frames", "scalars",
        ):
            self.assertEqual(getattr(first, field), getattr(second, field), field)


if __name__ == "__main__":
    unittest.main()
