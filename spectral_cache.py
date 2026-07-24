"""Disk cache for optional per-beat spectral analysis (v3 flat dir + v4 subdir).

Versioning convention (do not regress): every schema version owns its own
subdirectory (v3 = the top-level dir for historical reasons, v4 = ``v4/``, a
future v5 = ``v5/``). Eviction never crosses versions — ``evict_stale`` globs
only top-level v3 files, ``evict_stale_v4`` only ``v4/``. v4 code never
modifies or deletes v3 entries.

Two eviction rules that are equally non-negotiable: foreign files (macOS
``._*`` AppleDouble twins) are never read and never deleted, and an entry
whose audio lives on an unmounted ``/Volumes`` root is unknown, not stale —
eviction must never wipe the USB pre-warm because the stick is unplugged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import struct
import tempfile
from typing import Optional, Sequence

from .audio_spectral_features import (
    SCHEMA_VERSION,
    SCHEMA_VERSION_V4,
    SpectralFeatures,
    SpectralFeaturesV4,
    V4_SCALAR_KEYS,
    V4_SERIES_KEYS,
    V4_SUB4_KEYS,
)

log = logging.getLogger("spectral_cache")

_DEFAULT_CACHE_DIR = (
    "~/Library/Application Support/RBSS Bridge/spectral_cache"
)

_COMPAT_FIELDS = (
    "sub_bass_envelope",
    "kick_envelope",
    "low_mid_envelope",
    "high_mid_envelope",
    "high_band_envelope",
    "kick_max_envelope",
    "onset_strength_envelope",
    "spectral_flatness_envelope",
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
            kick_max_envelope=tuple(float(v) for v in payload["kick_max_envelope"]),
            onset_strength_envelope=tuple(
                float(v) for v in payload["onset_strength_envelope"]
            ),
            spectral_flatness_envelope=tuple(
                float(v) for v in payload["spectral_flatness_envelope"]
            ),
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
        if _is_foreign_file(path):
            continue
        if _cache_file_is_stale(path):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def get_cached_v4(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
) -> Optional[SpectralFeaturesV4]:
    key = _cache_key(audio_filepath, beatgrid_times_ms)
    if key is None:
        return None
    path = _cache_dir_v4() / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.debug("v4 spectral cache miss/corrupt key=%s: %s", key, exc)
        return None
    return _features_v4_from_payload(payload)


def put_cached_v4(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
    features: SpectralFeaturesV4,
) -> None:
    key = _cache_key(audio_filepath, beatgrid_times_ms)
    if key is None:
        return
    cache_dir = _cache_dir_v4()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    payload = _payload_v4_for_write(audio_filepath, beatgrid_times_ms, features)
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
        log.debug("v4 spectral cache write failed key=%s: %s", key, exc)
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass


def evict_stale_v4() -> int:
    cache_dir = _cache_dir_v4()
    if not cache_dir.exists():
        return 0
    removed = 0
    for path in cache_dir.glob("*.json"):
        if _is_foreign_file(path):
            continue
        if _cache_file_is_stale_v4(path):
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


def _cache_dir_v4() -> Path:
    # Derived from _cache_dir() so RBSS_SPECTRAL_CACHE_DIR moves both versions.
    return _cache_dir() / "v4"


def _features_v4_from_payload(payload: dict) -> Optional[SpectralFeaturesV4]:
    if payload.get("schema_version") != SCHEMA_VERSION_V4:
        return None
    try:
        n_beats = int(payload["n_beats"])
        compat = {
            field: tuple(float(v) for v in payload[field]) for field in _COMPAT_FIELDS
        }
        series = {
            key: tuple(float(v) for v in payload["series"][key])
            for key in V4_SERIES_KEYS
        }
        sub4 = {
            key: tuple(
                tuple(float(v) for v in slot) for slot in payload["sub4"][key]
            )
            for key in V4_SUB4_KEYS
        }
        scalars = {key: float(payload["scalars"][key]) for key in V4_SCALAR_KEYS}
        frames = tuple(float(v) for v in payload["growl_band_frames"])
        # Tolerant read: pre-AWR-176 entries lack this key and parse as () — no
        # signal. Present-but-wrong-length fails closed below (treated as a miss).
        cframes = tuple(float(v) for v in payload.get("growl_centroid_frames", ()))
        for field, values in compat.items():
            if len(values) != n_beats:
                raise ValueError(f"compat length mismatch: {field}")
        for key, values in series.items():
            if len(values) != n_beats:
                raise ValueError(f"series length mismatch: {key}")
        for key, slots in sub4.items():
            if len(slots) != n_beats or any(len(s) != 4 for s in slots):
                raise ValueError(f"sub4 shape mismatch: {key}")
        if cframes and len(cframes) != len(frames):
            raise ValueError("growl_centroid length mismatch")
        return SpectralFeaturesV4(
            sr=int(payload["sr"]),
            schema_version=SCHEMA_VERSION_V4,
            n_beats=n_beats,
            duration_s=float(payload["duration_s"]),
            frame_hop_s=float(payload["frame_hop_s"]),
            series=series,
            sub4=sub4,
            growl_band_frames=frames,
            scalars=scalars,
            growl_centroid_frames=cframes,
            **compat,
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.debug("v4 spectral cache payload invalid: %s", exc)
        return None


def _payload_v4_for_write(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
    features: SpectralFeaturesV4,
) -> Optional[dict[str, object]]:
    try:
        realpath = os.path.realpath(audio_filepath)
        stat = os.stat(realpath)
    except OSError:
        return None
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION_V4,
        "audio_filepath": realpath,
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
        "beatgrid_fingerprint": _beatgrid_fingerprint(beatgrid_times_ms),
        "sr": int(features.sr),
        "n_beats": int(features.n_beats),
        "duration_s": float(features.duration_s),
        "frame_hop_s": float(features.frame_hop_s),
        "series": {key: list(features.series[key]) for key in V4_SERIES_KEYS},
        "sub4": {
            key: [list(slot) for slot in features.sub4[key]] for key in V4_SUB4_KEYS
        },
        "scalars": {key: float(features.scalars[key]) for key in V4_SCALAR_KEYS},
        "growl_band_frames": list(features.growl_band_frames),
        "growl_centroid_frames": list(features.growl_centroid_frames),
    }
    for field in _COMPAT_FIELDS:
        payload[field] = list(getattr(features, field))
    return payload


def _is_foreign_file(path: Path) -> bool:
    """True for files in the cache dir that are not ours to read or delete.

    macOS writes a binary AppleDouble twin (``._<name>``) beside every file
    copied off a FAT/exFAT volume, and ``Path.glob("*.json")`` returns those
    twins (unlike ``glob.glob``). They are not cache entries: never read them,
    never delete them (macOS just recreates them on the next stick copy).
    """
    return path.name.startswith("._")


def _audio_on_unmounted_volume(audio_filepath: str) -> bool:
    """True when the audio path lives on a ``/Volumes`` root that is not mounted.

    "I cannot stat it" then means unknown, not stale.
    ``tools/spectral_stick_sweep.py`` deliberately pre-warms the cache with
    entries keyed by the on-stick absolute path so a bridge on any Mac that
    mounts the same stick gets full spectral data from the first beat. Those
    entries stat-fail whenever the stick is unplugged; deleting them would
    silently destroy the pre-warm (587 entries / ~229 MB measured 2026-07-24).
    """
    parts = Path(audio_filepath).parts
    if len(parts) < 4 or parts[0] != os.sep or parts[1] != "Volumes":
        return False
    # ismount(), not exists(): a leftover empty /Volumes/<name> dir from a bad
    # eject must still read as "not mounted" so the entry is kept.
    return not os.path.ismount(os.path.join(os.sep, "Volumes", parts[2]))


def _entry_is_stale(path: Path, schema_version: int) -> bool:
    """Shared staleness rule for both versions; callers must skip foreign files.

    ValueError covers UnicodeDecodeError as well as JSONDecodeError. Returning
    stale for an undecodable file is safe ONLY because _is_foreign_file()
    already excluded the AppleDouble twins upstream — what is left is one of
    our own entries, and one of ours that will not decode is genuinely dead.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    if not isinstance(payload, dict) or payload.get("schema_version") != schema_version:
        return True
    audio_filepath = payload.get("audio_filepath")
    if not isinstance(audio_filepath, str):
        return True
    try:
        stat = os.stat(audio_filepath)
    except OSError:
        return not _audio_on_unmounted_volume(audio_filepath)
    return (
        int(payload.get("mtime_ns", -1)) != int(stat.st_mtime_ns)
        or int(payload.get("size", -1)) != int(stat.st_size)
    )


def _cache_file_is_stale_v4(path: Path) -> bool:
    return _entry_is_stale(path, SCHEMA_VERSION_V4)


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
        "kick_max_envelope": list(features.kick_max_envelope),
        "onset_strength_envelope": list(features.onset_strength_envelope),
        "spectral_flatness_envelope": list(features.spectral_flatness_envelope),
    }


def _cache_file_is_stale(path: Path) -> bool:
    return _entry_is_stale(path, SCHEMA_VERSION)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
