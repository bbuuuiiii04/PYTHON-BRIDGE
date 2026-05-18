"""Disk cache for optional per-beat spectral envelopes."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import struct
import tempfile
from typing import Optional, Sequence

from .audio_spectral_features import SCHEMA_VERSION, SpectralFeatures

log = logging.getLogger("spectral_cache")

_DEFAULT_CACHE_DIR = (
    "~/Library/Application Support/RBSS Bridge/spectral_cache"
)


def get_cached(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
) -> Optional[SpectralFeatures]:
    key = _cache_key(audio_filepath, beatgrid_times_ms)
    if key is None:
        return None
    path = _cache_dir() / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.debug("spectral cache miss/corrupt key=%s: %s", key, exc)
        return None

    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    try:
        return SpectralFeatures(
            sr=int(payload["sr"]),
            schema_version=int(payload["schema_version"]),
            sub_bass_envelope=tuple(float(v) for v in payload["sub_bass_envelope"]),
            kick_envelope=tuple(float(v) for v in payload["kick_envelope"]),
            low_mid_envelope=tuple(float(v) for v in payload["low_mid_envelope"]),
            high_mid_envelope=tuple(float(v) for v in payload["high_mid_envelope"]),
            high_band_envelope=tuple(float(v) for v in payload["high_band_envelope"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.debug("spectral cache payload invalid key=%s: %s", key, exc)
        return None


def put_cached(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
    features: SpectralFeatures,
) -> None:
    key = _cache_key(audio_filepath, beatgrid_times_ms)
    if key is None:
        return
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    payload = _payload_for_write(audio_filepath, beatgrid_times_ms, features)
    if payload is None:
        return

    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=cache_dir,
            prefix=f".{key}.",
            suffix=".tmp",
            delete=False,
        ) as fp:
            tmp_name = fp.name
            json.dump(payload, fp, sort_keys=True)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_name, path)
        _fsync_dir(cache_dir)
    except OSError as exc:
        log.debug("spectral cache write failed key=%s: %s", key, exc)
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass


def evict_stale() -> int:
    cache_dir = _cache_dir()
    if not cache_dir.exists():
        return 0
    removed = 0
    for path in cache_dir.glob("*.json"):
        if _cache_file_is_stale(path):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _cache_dir() -> Path:
    override = os.environ.get("RBSS_SPECTRAL_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path(_DEFAULT_CACHE_DIR).expanduser()


def _beatgrid_fingerprint(beatgrid_times_ms: Sequence[float]) -> str:
    grid = [float(value) for value in beatgrid_times_ms]
    blob = struct.pack(f"<{len(grid)}d", *grid) if grid else b""
    return hashlib.sha256(blob).hexdigest()[:16]


def _cache_key(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
) -> Optional[str]:
    try:
        realpath = os.path.realpath(audio_filepath)
        stat = os.stat(realpath)
    except OSError:
        return None
    material = "\0".join((
        realpath,
        str(int(stat.st_mtime_ns)),
        str(int(stat.st_size)),
        _beatgrid_fingerprint(beatgrid_times_ms),
    ))
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def _payload_for_write(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
    features: SpectralFeatures,
) -> Optional[dict[str, object]]:
    try:
        realpath = os.path.realpath(audio_filepath)
        stat = os.stat(realpath)
    except OSError:
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "audio_filepath": realpath,
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
        "beatgrid_fingerprint": _beatgrid_fingerprint(beatgrid_times_ms),
        "sr": int(features.sr),
        "sub_bass_envelope": list(features.sub_bass_envelope),
        "kick_envelope": list(features.kick_envelope),
        "low_mid_envelope": list(features.low_mid_envelope),
        "high_mid_envelope": list(features.high_mid_envelope),
        "high_band_envelope": list(features.high_band_envelope),
    }


def _cache_file_is_stale(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if payload.get("schema_version") != SCHEMA_VERSION:
        return True
    audio_filepath = payload.get("audio_filepath")
    if not isinstance(audio_filepath, str):
        return True
    try:
        stat = os.stat(audio_filepath)
    except OSError:
        return True
    return (
        int(payload.get("mtime_ns", -1)) != int(stat.st_mtime_ns)
        or int(payload.get("size", -1)) != int(stat.st_size)
    )


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
