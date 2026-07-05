import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.audio_spectral_features import SCHEMA_VERSION, SpectralFeatures
from rb_ss_bridge_v2 import spectral_cache


def _features() -> SpectralFeatures:
    return SpectralFeatures(
        sr=22050,
        schema_version=SCHEMA_VERSION,
        sub_bass_envelope=(0.1, 0.2, 0.3),
        kick_envelope=(0.4, 0.5, 0.6),
        low_mid_envelope=(0.2, 0.3, 0.4),
        high_mid_envelope=(0.5, 0.6, 0.7),
        high_band_envelope=(0.7, 0.8, 0.9),
        kick_max_envelope=(0.8, 0.9, 1.0),
        onset_strength_envelope=(0.3, 0.4, 0.5),
        spectral_flatness_envelope=(0.1, 0.2, 0.3),
    )


class SpectralCacheTests(unittest.TestCase):
    def _with_cache(self):
        td = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ, {"RBSS_SPECTRAL_CACHE_DIR": td.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def _audio_file(self, directory: Path, content: bytes = b"audio") -> Path:
        path = directory / "track.wav"
        path.write_bytes(content)
        return path

    def test_cache_hit_round_trips_features(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]

        spectral_cache.put_cached(str(audio), beatgrid, _features())
        cached = spectral_cache.get_cached(str(audio), beatgrid)

        self.assertEqual(cached, _features())

    def test_cache_misses_when_mtime_changes(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached(str(audio), beatgrid, _features())

        stat = audio.stat()
        os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        self.assertIsNone(spectral_cache.get_cached(str(audio), beatgrid))

    def test_cache_misses_when_size_changes(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached(str(audio), beatgrid, _features())

        audio.write_bytes(b"audio-longer")

        self.assertIsNone(spectral_cache.get_cached(str(audio), beatgrid))

    def test_cache_misses_when_beatgrid_changes(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)

        spectral_cache.put_cached(str(audio), [0.0, 500.0, 1000.0], _features())

        self.assertIsNone(
            spectral_cache.get_cached(str(audio), [0.0, 501.0, 1000.0])
        )

    def test_schema_version_mismatch_returns_none(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached(str(audio), beatgrid, _features())
        cache_file = next(cache_dir.glob("*.json"))
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        payload["schema_version"] = 999
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        self.assertIsNone(spectral_cache.get_cached(str(audio), beatgrid))

    def test_atomic_write_failure_leaves_no_cache_hit(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)

        with patch("rb_ss_bridge_v2.spectral_cache.os.replace", side_effect=OSError("boom")):
            spectral_cache.put_cached(str(audio), [0.0, 500.0, 1000.0], _features())

        self.assertEqual(list(cache_dir.glob("*.json")), [])
        self.assertEqual(list(cache_dir.glob("*.tmp")), [])
        self.assertIsNone(
            spectral_cache.get_cached(str(audio), [0.0, 500.0, 1000.0])
        )

    def test_corruption_fallback_returns_none(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached(str(audio), beatgrid, _features())
        cache_file = next(cache_dir.glob("*.json"))
        cache_file.write_text("{bad json", encoding="utf-8")

        self.assertIsNone(spectral_cache.get_cached(str(audio), beatgrid))


def _features_v4(n_beats: int = 3) -> "spectral_cache.SpectralFeaturesV4":
    from rb_ss_bridge_v2.audio_spectral_features import (
        SCHEMA_VERSION_V4,
        SpectralFeaturesV4,
        V4_SCALAR_KEYS,
        V4_SERIES_KEYS,
        V4_SUB4_KEYS,
    )

    beats = tuple(float(i) for i in range(n_beats))
    return SpectralFeaturesV4(
        sr=22050,
        schema_version=SCHEMA_VERSION_V4,
        n_beats=n_beats,
        duration_s=180.0,
        frame_hop_s=0.0232,
        sub_bass_envelope=beats,
        kick_envelope=beats,
        low_mid_envelope=beats,
        high_mid_envelope=beats,
        high_band_envelope=beats,
        kick_max_envelope=beats,
        onset_strength_envelope=beats,
        spectral_flatness_envelope=beats,
        series={key: beats for key in V4_SERIES_KEYS},
        sub4={key: tuple((0.0, 1.0, 2.0, 3.0) for _ in range(n_beats)) for key in V4_SUB4_KEYS},
        growl_band_frames=(0.0, 1.0, 2.0, 3.0, 4.0),
        scalars={key: 0.5 for key in V4_SCALAR_KEYS},
    )


class SpectralCacheV4Tests(unittest.TestCase):
    def _with_cache(self):
        td = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ, {"RBSS_SPECTRAL_CACHE_DIR": td.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def _audio_file(self, directory: Path, content: bytes = b"audio") -> Path:
        path = directory / "track.wav"
        path.write_bytes(content)
        return path

    def test_v4_round_trip(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]

        spectral_cache.put_cached_v4(str(audio), beatgrid, _features_v4())
        cached = spectral_cache.get_cached_v4(str(audio), beatgrid)

        self.assertEqual(cached, _features_v4())
        self.assertTrue((cache_dir / "v4").is_dir())

    def test_v4_dir_follows_env_override(self) -> None:
        cache_dir = self._with_cache()
        self.assertEqual(
            spectral_cache._cache_dir_v4(), Path(cache_dir) / "v4"
        )

    def test_v4_length_mismatch_returns_none(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached_v4(str(audio), beatgrid, _features_v4())
        cache_file = next((cache_dir / "v4").glob("*.json"))
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        payload["series"]["sub_db"] = [0.0]
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        self.assertIsNone(spectral_cache.get_cached_v4(str(audio), beatgrid))

    def test_v4_corruption_returns_none(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached_v4(str(audio), beatgrid, _features_v4())
        cache_file = next((cache_dir / "v4").glob("*.json"))
        cache_file.write_text("{bad json", encoding="utf-8")

        self.assertIsNone(spectral_cache.get_cached_v4(str(audio), beatgrid))

    def test_v4_misses_when_mtime_changes(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached_v4(str(audio), beatgrid, _features_v4())

        stat = audio.stat()
        os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        self.assertIsNone(spectral_cache.get_cached_v4(str(audio), beatgrid))

    def test_evictions_never_cross_schema_versions(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)
        beatgrid = [0.0, 500.0, 1000.0]
        spectral_cache.put_cached(str(audio), beatgrid, _features())
        spectral_cache.put_cached_v4(str(audio), beatgrid, _features_v4())
        v3_files = set(cache_dir.glob("*.json"))
        v4_files = set((cache_dir / "v4").glob("*.json"))
        self.assertEqual(len(v3_files), 1)
        self.assertEqual(len(v4_files), 1)

        # Fresh entries: neither eviction removes anything, and neither can
        # see the other version's files.
        self.assertEqual(spectral_cache.evict_stale(), 0)
        self.assertEqual(spectral_cache.evict_stale_v4(), 0)
        self.assertEqual(set(cache_dir.glob("*.json")), v3_files)
        self.assertEqual(set((cache_dir / "v4").glob("*.json")), v4_files)

        # Make the audio stale: v4 eviction removes only its own entry,
        # v3 files stay untouched by v4 code.
        stat = audio.stat()
        os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        self.assertEqual(spectral_cache.evict_stale_v4(), 1)
        self.assertEqual(set(cache_dir.glob("*.json")), v3_files)
        self.assertEqual(list((cache_dir / "v4").glob("*.json")), [])

    def test_v4_atomic_write_failure_leaves_no_cache_hit(self) -> None:
        cache_dir = self._with_cache()
        audio = self._audio_file(cache_dir)

        with patch("rb_ss_bridge_v2.spectral_cache.os.replace", side_effect=OSError("boom")):
            spectral_cache.put_cached_v4(str(audio), [0.0, 500.0, 1000.0], _features_v4())

        self.assertEqual(list((cache_dir / "v4").glob("*.json")), [])
        self.assertEqual(list((cache_dir / "v4").glob("*.tmp")), [])
        self.assertIsNone(
            spectral_cache.get_cached_v4(str(audio), [0.0, 500.0, 1000.0])
        )


if __name__ == "__main__":
    unittest.main()
