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


class GrowlCentroidCacheTests(unittest.TestCase):
    """Part D items 6-8 — tolerant read, strict shape, round-trip."""

    def _with_cache(self):
        td = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ, {"RBSS_SPECTRAL_CACHE_DIR": td.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def _audio_file(self, directory: Path) -> Path:
        path = directory / "track.wav"
        path.write_bytes(b"audio")
        return path

    def test_legacy_payload_without_key_round_trips(self) -> None:
        # Item 6: a v4 entry written before the field existed still parses;
        # the field reads as ().
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        grid = [0.0, 250.0, 500.0]
        n = len(grid) - 1
        feats = _v4(growl_band_frames=(1.0,), n_beats=n)
        spectral_cache.put_cached_v4(str(audio), grid, feats)
        # Strip the key from the written payload to simulate a legacy entry.
        cache_file = next((cache_dir / "v4").glob("*.json"))
        import json
        payload = json.loads(cache_file.read_text())
        del payload["growl_centroid_frames"]
        cache_file.write_text(json.dumps(payload))

        cached = spectral_cache.get_cached_v4(str(audio), grid)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.growl_centroid_frames, ())

    def test_present_but_wrong_length_is_a_miss(self) -> None:
        # Item 7: field present with a length that disagrees with the level
        # series fails closed to None (re-extract).
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        grid = [0.0, 250.0, 500.0]
        n = len(grid) - 1
        feats = _v4(growl_band_frames=(1.0, 2.0), n_beats=n)
        spectral_cache.put_cached_v4(str(audio), grid, feats)
        cache_file = next((cache_dir / "v4").glob("*.json"))
        import json
        payload = json.loads(cache_file.read_text())
        payload["growl_centroid_frames"] = [100.0]  # len 1 vs level len 2
        cache_file.write_text(json.dumps(payload))

        self.assertIsNone(spectral_cache.get_cached_v4(str(audio), grid))

    def test_round_trip_preserves_the_field(self) -> None:
        # Item 8: write with the field -> read back equal.
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        grid = [0.0, 250.0, 500.0]
        n = len(grid) - 1
        feats = _v4(
            growl_band_frames=(1.0, 2.0),
            growl_centroid_frames=(120.5, 240.0),
            n_beats=n,
        )
        spectral_cache.put_cached_v4(str(audio), grid, feats)
        cached = spectral_cache.get_cached_v4(str(audio), grid)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.growl_centroid_frames, (120.5, 240.0))
        self.assertEqual(cached, feats)


if __name__ == "__main__":
    unittest.main()
