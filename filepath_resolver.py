"""
lsof-based track filepath resolution.

FilepathResolver.resolve_async() spawns a daemon thread that:
  1. runs lsof on rekordbox
  2. cross-references audio file durations against the track length in PositionCache
  3. queries the RB DB for BPM and content_id
  4. reads the SOUNDSWITCH_ID ID3 tag
  5. pushes a FILEPATH_RESOLVED event to event_queue

The load_gen field in both the trigger and the result lets StateManager
discard results that arrived for a stale track load.
"""
from __future__ import annotations

import logging
import math
import os
import queue
import re
import json
import statistics
import struct
import subprocess
import threading
import time
import unicodedata
import warnings
from pathlib import Path
from typing import Optional, Sequence

from .beat_math import _compute_beatgrid_position
from .config import AUDIO_EXTS, LSOF_LEN_TOLERANCE_MS, LSOF_COOLDOWN_S, RB_DB_PATH
from .led_config import load_drop_presentation_config
from .models import BridgeEvent, Ev, PositionSnapshot
from .spectral_cache import _beatgrid_fingerprint, _features_v4_from_payload
from . import bridge_fmt as bf

log = logging.getLogger("filepath_resolver")

_EMPTY_BEATGRID = {
    "beatgrid_times_ms": [],
    "beatgrid_bpms": [],
    "beatgrid_source": "",
}
_MIN_BEATGRID_INTERVAL_MS = 150.0
_MAX_BEATGRID_INTERVAL_MS = 3000.0
_USB_TWIN_BPM_TOLERANCE = 0.05
_USB_TWIN_DURATION_TOLERANCE_S = 2.0
_VOLUMES_ROOT = Path("/Volumes")
_RB_SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
_SS_PRELOAD_CACHE: dict[str, str] = {}
_SS_SCRIPTED_ID_CACHE: set[str] = set()
_SIDECAR_SCHEMA_VERSION = 1
_INSTALLED_SIDECAR_INDEX = (
    Path.home() / "Library" / "Application Support" / "RBSS Bridge"
    / "lighting_sidecar" / "index.json"
)
_SIDECAR_CACHE: dict[
    Path,
    tuple[tuple[int, int], tuple[Path, tuple[dict, ...]]],
] = {}
_SIDECAR_ONLY_LOGGED = False


# ── Helpers ──────────────────────────────────────────────────────────────────

def seed_soundswitch_id_cache(mapping: dict[str, str]) -> None:
    _SS_PRELOAD_CACHE.update(mapping)


def _normalize_soundswitch_id(ssid: str) -> str:
    ssid = (ssid or "").strip().upper()
    if not ssid:
        return ""
    if not ssid.startswith("{"):
        ssid = "{" + ssid
    if not ssid.endswith("}"):
        ssid = ssid + "}"
    return ssid


def seed_soundswitch_scripted_id_cache(ids: set[str] | list[str] | tuple[str, ...]) -> None:
    _SS_SCRIPTED_ID_CACHE.update(
        normalized for ssid in ids
        if (normalized := _normalize_soundswitch_id(ssid))
    )


def has_soundswitch_scripted_id(ssid: str) -> bool:
    normalized = _normalize_soundswitch_id(ssid)
    return bool(normalized and normalized in _SS_SCRIPTED_ID_CACHE)


def _rb_pid() -> Optional[str]:
    out = subprocess.run(
        ["pgrep", "-x", "rekordbox"],
        capture_output=True, text=True, timeout=3,
    ).stdout.strip()
    return out.splitlines()[0] if out else None


def _lsof_audio_files(rb_pid: str) -> list[str]:
    out = subprocess.run(
        ["lsof", "-p", rb_pid, "-Fn"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    result = []
    for line in out.splitlines():
        if not line.startswith("n"):
            continue
        path = line[1:]
        if os.path.splitext(path.lower())[1] in AUDIO_EXTS and os.path.isfile(path):
            result.append(path)
    return result


def _duration_ms(filepath: str) -> Optional[float]:
    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(filepath)
        if audio and audio.info:
            return audio.info.length * 1000.0
    except Exception:
        pass
    if filepath.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(filepath) as wf:
                return wf.getnframes() / wf.getframerate() * 1000.0
        except Exception:
            pass
    return None


def _read_soundswitch_id(filepath: str) -> str:
    if filepath in _SS_PRELOAD_CACHE:
        return _SS_PRELOAD_CACHE[filepath]
    # mutagen.File auto-detects format — required for WAV (ID3 stored in RIFF chunk,
    # not a bare ID3 header, so mutagen.id3.ID3 raises ID3NoHeaderError on .wav files).
    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(filepath)
        if audio and audio.tags and hasattr(audio.tags, "getall"):
            for tag in audio.tags.getall("TXXX"):
                if tag.desc.lower() == "soundswitch_id":
                    return str(tag.text[0]) if tag.text else ""
        if audio and audio.tags and hasattr(audio.tags, "get"):
            for key in ("soundswitch_id", "SOUNDSWITCH_ID"):
                value = audio.tags.get(key)
                if value:
                    if isinstance(value, (list, tuple)):
                        return str(value[0]) if value else ""
                    return str(value)
    except Exception:
        pass
    # Fallback: raw ID3 scan for formats mutagen.File doesn't auto-detect.
    try:
        from mutagen.id3 import ID3  # type: ignore
        for tag in ID3(filepath).getall("TXXX"):
            if tag.desc.lower() == "soundswitch_id":
                return str(tag.text[0]) if tag.text else ""
    except Exception:
        pass
    return ""


def _candidate_anlz_paths(anlz_path: str) -> list[Path]:
    path = Path(anlz_path)
    candidates = [path]
    if path.suffix.upper() in (".DAT", ".EXT", ".2EX"):
        for suffix in (".2EX", ".EXT", ".DAT"):
            candidates.append(path.with_suffix(suffix))

    seen: set[str] = set()
    result = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen and candidate.exists():
            seen.add(key)
            result.append(candidate)
    return result


def _grid_from_tag(tag, source: str) -> Optional[dict]:  # type: ignore[no-untyped-def]
    try:
        times = [float(t) * 1000.0 for t in tag.get_times()]
        bpms = [float(bpm) for bpm in tag.get_bpms()]
    except Exception as exc:
        log.debug("ANLZ %s beatgrid read failed: %s", source, exc)
        return None

    rows = sorted(
        (time_ms, bpm)
        for time_ms, bpm in zip(times, bpms)
        if time_ms >= 0.0 and bpm > 0.0
    )
    if len(rows) < 2:
        return None

    intervals = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    if (
        any(interval <= 0.0 for interval in intervals)
        or not intervals
        or sorted(intervals)[len(intervals) // 2] < _MIN_BEATGRID_INTERVAL_MS
        or sorted(intervals)[len(intervals) // 2] > _MAX_BEATGRID_INTERVAL_MS
    ):
        log.debug("ANLZ %s rejected implausible beatgrid intervals=%s",
                  source, intervals[:8])
        return None

    return {
        "beatgrid_times_ms": [time_ms for time_ms, _ in rows],
        "beatgrid_bpms": [bpm for _, bpm in rows],
        "beatgrid_source": source,
    }


def _extract_beatgrid_from_anlz(anlz_path: str) -> dict:
    """Return beatgrid fields from ANLZ data, preferring PQT2 over PQTZ."""
    try:
        from pyrekordbox.anlz import AnlzFile  # type: ignore
    except Exception as exc:
        log.debug("ANLZ beatgrid unavailable: pyrekordbox import failed: %s", exc)
        return dict(_EMPTY_BEATGRID)

    parsed = []
    for path in _candidate_anlz_paths(anlz_path):
        try:
            parsed.append((path, AnlzFile.parse_file(path)))
        except Exception as exc:
            log.debug("ANLZ beatgrid parse failed for %s: %s", path, exc)

    for tag_type in ("PQT2", "PQTZ"):
        for path, anlz in parsed:
            for tag in anlz.getall_tags(tag_type):
                grid = _grid_from_tag(tag, f"{tag_type}:{path.name}")
                if grid:
                    log.debug("ANLZ beatgrid %s markers=%d",
                              grid["beatgrid_source"], len(grid["beatgrid_times_ms"]))
                    return grid

    return dict(_EMPTY_BEATGRID)


def _is_device_export_anlz_path(anlz_path: str, captured_id: str = "") -> bool:
    """True for USB/device ANLZ paths, never for local UUID analysis paths."""
    normalized = anlz_path.replace("\\", "/")
    if normalized.startswith("/Volumes/"):
        return True
    if not captured_id:
        match = re.search(r"USBANLZ/([^/]+)/([^/]+)/ANLZ", normalized)
        if match:
            shard, captured_id = match.groups()
            # Rekordbox 7 can split its local UUID across the two directories:
            # USBANLZ/<first 3 UUID chars>/<remaining UUID chars>/ANLZ....
            # Reassemble only this exact local shape. /Volumes paths already
            # returned above, so a real mounted device stays device-export.
            reassembled = shard + captured_id
            if re.fullmatch(r"[0-9a-fA-F]{3}", shard) and re.fullmatch(
                r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                reassembled,
            ):
                captured_id = reassembled
    return bool(captured_id and not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", captured_id,
    ))


def _beatgrids_match(usb_times_ms: Sequence[float], local_times_ms: Sequence[float]) -> bool:
    """Mirror-class identity: the complete grids must be byte-for-byte equivalent."""
    try:
        usb = tuple(float(value) for value in usb_times_ms)
        local = tuple(float(value) for value in local_times_ms)
    except (TypeError, ValueError):
        return False
    if len(usb) < 2 or len(local) < 2:
        return False
    if not all(math.isfinite(value) for value in (*usb, *local)):
        return False
    return len(usb) == len(local) and _beatgrid_fingerprint(usb) == _beatgrid_fingerprint(local)


def _usb_twin_prefilter(contents: Sequence[object], usb_beatgrid: dict) -> list[object]:
    """Cheap BPM/duration filter before any candidate ANLZ file reads."""
    times = [
        float(value) for value in usb_beatgrid.get("beatgrid_times_ms", ())
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    bpms = [
        float(value) for value in usb_beatgrid.get("beatgrid_bpms", ())
        if isinstance(value, (int, float)) and math.isfinite(float(value)) and value > 0
    ]
    if len(times) < 2 or not bpms or times[-1] <= 0:
        return []
    target_bpm = statistics.median(bpms)
    target_duration_s = times[-1] / 1000.0
    candidates: list[object] = []
    for content in contents:
        if getattr(content, "rb_local_deleted", 0):
            continue
        bpm_raw = getattr(content, "BPM", None)
        length = getattr(content, "Length", None)
        analysis_path = str(getattr(content, "AnalysisDataPath", None) or "")
        folder_path = str(getattr(content, "FolderPath", None) or "")
        if not bpm_raw or not length or not analysis_path or not folder_path:
            continue
        bpm = float(bpm_raw) / 100.0
        if (
            abs(bpm - target_bpm) <= _USB_TWIN_BPM_TOLERANCE
            and abs(float(length) - target_duration_s) <= _USB_TWIN_DURATION_TOLERANCE_S
        ):
            candidates.append(content)
    return candidates


def _local_anlz_path(analysis_data_path: str) -> str:
    return str(_RB_SHARE_ROOT / analysis_data_path.lstrip("/"))


def _device_sql_string(data: bytes, offset: int) -> str:
    kind = data[offset]
    if kind == 0x40:
        length = struct.unpack_from("<H", data, offset + 1)[0]
        if length < 4:
            raise ValueError("invalid DeviceSQL ASCII string length")
        return data[offset + 4:offset + length].decode("ascii")
    if kind == 0x90:
        length = struct.unpack_from("<H", data, offset + 1)[0]
        if length < 4:
            raise ValueError("invalid DeviceSQL UTF-16 string length")
        return data[offset + 4:offset + length].decode("utf-16le")
    length = kind >> 1
    if length < 1:
        return ""
    return data[offset + 1:offset + length].decode("ascii")


def _device_pdb_rows(
    data: bytes,
    page_size: int,
    first_page: int,
    last_page: int,
    table_type: int,
):  # type: ignore[no-untyped-def]
    page_index = first_page
    visited: set[int] = set()
    while page_index not in visited:
        visited.add(page_index)
        page_start = page_index * page_size
        if page_start + page_size > len(data):
            raise ValueError("DeviceSQL page outside file")
        if struct.unpack_from("<I", data, page_start + 8)[0] != table_type:
            return
        packed = int.from_bytes(data[page_start + 24:page_start + 27], "little")
        num_offsets = packed & 0x1FFF
        groups = (num_offsets + 15) // 16
        if groups and page_size - ((groups - 1) * 0x24) - 36 < 40:
            raise ValueError("DeviceSQL row index overlaps page header")
        if not data[page_start + 27] & 0x40:
            for group in range(groups):
                base = page_size - group * 0x24
                present = struct.unpack_from("<H", data, page_start + base - 4)[0]
                for row_in_group in range(16):
                    row_index = group * 16 + row_in_group
                    if row_index >= num_offsets:
                        break
                    if not present & (1 << row_in_group):
                        continue
                    row_offset = struct.unpack_from(
                        "<H", data, page_start + base - (6 + 2 * row_in_group)
                    )[0]
                    if row_offset >= page_size - 40:
                        raise ValueError("DeviceSQL row outside page heap")
                    yield page_start + 40 + row_offset
        if page_index == last_page:
            return
        page_index = struct.unpack_from("<I", data, page_start + 12)[0]


def _parse_device_pdb_track(data: bytes, anlz_path: str) -> Optional[dict]:
    """Read only the export.pdb track/artist fields needed for USB identity."""
    page_size, num_tables = struct.unpack_from("<II", data, 4)
    if page_size < 128 or 28 + num_tables * 16 > page_size:
        raise ValueError("invalid DeviceSQL header")
    tables = {
        table_type: (first_page, last_page)
        for table_type, _empty, first_page, last_page in struct.iter_unpack(
            "<IIII", data[28:28 + num_tables * 16]
        )
    }
    if 0 not in tables or 2 not in tables:
        return None

    artists: dict[int, str] = {}
    for row in _device_pdb_rows(data, page_size, *tables[2], 2):
        subtype = struct.unpack_from("<H", data, row)[0]
        name_offset = (
            struct.unpack_from("<H", data, row + 10)[0]
            if subtype & 0x04 else data[row + 9]
        )
        artists[struct.unpack_from("<I", data, row + 4)[0]] = _device_sql_string(
            data, row + name_offset
        )

    normalized_path = anlz_path.replace("\\", "/")
    marker = normalized_path.casefold().find("/pioneer/usbanlz/")
    if marker < 0:
        return None
    wanted = normalized_path[marker:].casefold()
    matches: list[dict] = []
    for row in _device_pdb_rows(data, page_size, *tables[0], 0):
        offsets = struct.unpack_from("<21H", data, row + 94)
        analysis_path = _device_sql_string(data, row + offsets[14])
        if analysis_path.replace("\\", "/").casefold() != wanted:
            continue
        artist_id = struct.unpack_from("<I", data, row + 68)[0]
        matches.append({
            "track_id": struct.unpack_from("<I", data, row + 72)[0],
            "title": _device_sql_string(data, row + offsets[17]),
            "artist": artists.get(artist_id, ""),
            "duration_s": struct.unpack_from("<H", data, row + 84)[0],
            "bpm": struct.unpack_from("<I", data, row + 56)[0] / 100.0,
        })
    return matches[0] if len(matches) == 1 else None


def _read_device_pdb_track(anlz_path: str) -> Optional[dict]:
    match = re.match(r"^(/Volumes/[^/]+)/PIONEER/", anlz_path.replace("\\", "/"), re.I)
    if not match:
        return None
    pdb_path = Path(match.group(1)) / "PIONEER" / "rekordbox" / "export.pdb"
    return _parse_device_pdb_track(pdb_path.read_bytes(), anlz_path)


def _normalize_usb_tag(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _content_artist(content: object) -> str:
    artist = getattr(content, "Artist", None)
    return str(getattr(artist, "Name", None) or artist or "")


def _usb_pdb_candidates(contents: Sequence[object], track: dict) -> list[object]:
    title = _normalize_usb_tag(track.get("title"))
    artist = _normalize_usb_tag(track.get("artist"))
    duration = float(track.get("duration_s") or 0)
    if not title or duration <= 0:
        return []
    return [
        content for content in contents
        if not getattr(content, "rb_local_deleted", 0)
        and _normalize_usb_tag(getattr(content, "Title", "")) == title
        and _normalize_usb_tag(_content_artist(content)) == artist
        and getattr(content, "Length", None) is not None
        and abs(float(getattr(content, "Length")) - duration) <= _USB_TWIN_DURATION_TOLERANCE_S
    ]


def _relaxed_usb_twin_match(content: object, usb_beatgrid: dict) -> bool:
    times = [float(value) for value in usb_beatgrid.get("beatgrid_times_ms", ())]
    bpms = [float(value) for value in usb_beatgrid.get("beatgrid_bpms", ())]
    if len(times) < 2 or not bpms or times[-1] <= 0:
        return False
    bpm_raw = getattr(content, "BPM", None)
    length = getattr(content, "Length", None)
    if not bpm_raw or length is None:
        return False
    return (
        abs(float(bpm_raw) / 100.0 - statistics.median(bpms)) <= _USB_TWIN_BPM_TOLERANCE
        and abs(float(length) - times[-1] / 1000.0) <= _USB_TWIN_DURATION_TOLERANCE_S
    )


def _sidecar_path(root: Path, relpath: str) -> Optional[Path]:
    try:
        resolved_root = root.resolve()
        candidate = (root / relpath).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return candidate


def _load_sidecar_index(index_path: Path) -> Optional[tuple[Path, tuple[dict, ...]]]:
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != _SIDECAR_SCHEMA_VERSION:
        log.info(
            "[FRES] sidecar-schema-unsupported  path=%s  schema=%r",
            index_path, payload.get("schema_version"),
        )
        return None
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or payload.get("track_count") != len(tracks):
        return None
    root = index_path.parent
    validated: list[dict] = []
    for record in tracks:
        if not isinstance(record, dict):
            return None
        anlz_relpaths = record.get("anlz_relpaths")
        v4_relpath = record.get("v4_relpath")
        laser_tag_beats = record.get("laser_tag_beats")
        required_strings = (
            "content_id", "title", "artist", "beatgrid_fingerprint",
            "soundswitch_id", "source_filepath",
        )
        if (
            any(not isinstance(record.get(key), str) for key in required_strings)
            or not re.fullmatch(r"[0-9a-f]{16}", record["beatgrid_fingerprint"])
            or not isinstance(record.get("duration_s"), (int, float))
            or not isinstance(record.get("bpm"), (int, float))
            or not isinstance(anlz_relpaths, list)
            or not anlz_relpaths
            or any(not isinstance(path, str) or _sidecar_path(root, path) is None
                   for path in anlz_relpaths)
            or (v4_relpath is not None and
                (not isinstance(v4_relpath, str) or _sidecar_path(root, v4_relpath) is None))
            or not isinstance(laser_tag_beats, list)
            or any(not isinstance(beat, (int, float)) or not math.isfinite(float(beat))
                   for beat in laser_tag_beats)
        ):
            return None
        validated.append(record)
    return root, tuple(validated)


def _discover_sidecar_indexes(
    mounts: Sequence[Path],
) -> tuple[tuple[Path, tuple[dict, ...]], ...]:
    global _SIDECAR_CACHE
    candidates = {
        *(mount / "RBSS BRIDGE USB" / "lighting_sidecar" / "index.json"
          for mount in mounts),
        _INSTALLED_SIDECAR_INDEX,
    }
    cache = _SIDECAR_CACHE if isinstance(_SIDECAR_CACHE, dict) else {}
    refreshed: dict[
        Path,
        tuple[tuple[int, int], tuple[Path, tuple[dict, ...]]],
    ] = {}
    loaded_indexes: list[tuple[Path, tuple[dict, ...]]] = []
    for index_path in sorted(candidates, key=lambda path: (str(path).casefold(), str(path))):
        try:
            stat = index_path.stat()
        except OSError:
            continue
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = cache.get(index_path)
        loaded = cached[1] if cached is not None and cached[0] == signature else None
        if loaded is None:
            loaded = _load_sidecar_index(index_path)
        if loaded is not None:
            refreshed[index_path] = (signature, loaded)
            loaded_indexes.append(loaded)
    _SIDECAR_CACHE = refreshed
    return tuple(loaded_indexes)


def _discover_sidecar_index(mounts: Sequence[Path]) -> Optional[tuple[Path, tuple[dict, ...]]]:
    """Compatibility helper returning the first deterministic valid root."""
    indexes = _discover_sidecar_indexes(mounts)
    return indexes[0] if indexes else None


def _mounted_sidecar_indexes() -> tuple[tuple[Path, tuple[dict, ...]], ...]:
    try:
        mounts = tuple(Path("/Volumes").iterdir())
    except OSError:
        mounts = ()
    return _discover_sidecar_indexes(mounts)


def _mounted_sidecar_index() -> Optional[tuple[Path, tuple[dict, ...]]]:
    """Compatibility helper returning the first deterministic valid root."""
    indexes = _mounted_sidecar_indexes()
    return indexes[0] if indexes else None


def _sidecar_prefilter(records: Sequence[dict], usb_beatgrid: dict) -> list[dict]:
    times = [float(value) for value in usb_beatgrid.get("beatgrid_times_ms", ())]
    bpms = [float(value) for value in usb_beatgrid.get("beatgrid_bpms", ())]
    if len(times) < 2 or not bpms or times[-1] <= 0:
        return []
    target_bpm = statistics.median(bpms)
    target_duration_s = times[-1] / 1000.0
    return [
        record for record in records
        if abs(float(record["bpm"]) - target_bpm) <= _USB_TWIN_BPM_TOLERANCE
        and abs(float(record["duration_s"]) - target_duration_s)
        <= _USB_TWIN_DURATION_TOLERANCE_S
    ]


def _select_sidecar_record(
    records: Sequence[dict],
    usb_beatgrid: dict,
    device_track: Optional[dict],
) -> tuple[Optional[dict], str, list[str]]:
    candidates = _sidecar_prefilter(records, usb_beatgrid)
    fingerprint = _beatgrid_fingerprint(usb_beatgrid.get("beatgrid_times_ms", ()))
    exact = [
        record for record in candidates
        if record["beatgrid_fingerprint"] == fingerprint
    ]
    if len(exact) == 1:
        return exact[0], "sidecar-mirror-match", []
    if len(exact) > 1:
        return None, "sidecar-mirror-ambiguous", [
            str(record["content_id"]) for record in exact
        ]
    if device_track is None:
        return None, "usb-crossanalysis-unconfirmed", []

    title = _normalize_usb_tag(device_track.get("title"))
    artist = _normalize_usb_tag(device_track.get("artist"))
    duration = float(device_track.get("duration_s") or 0)
    tagged = [
        record for record in candidates
        if _normalize_usb_tag(record["title"]) == title
        and _normalize_usb_tag(record["artist"]) == artist
        and abs(float(record["duration_s"]) - duration)
        <= _USB_TWIN_DURATION_TOLERANCE_S
    ]
    if not tagged:
        return None, "usb-pdb-miss", []
    if len(tagged) > 1:
        return None, "usb-pdb-ambiguous", [str(record["content_id"]) for record in tagged]
    return tagged[0], "sidecar-pdb-match", []


def _device_audio_filepath(anlz_path: str) -> str:
    normalized_anlz = anlz_path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", normalized_anlz):
        return ""
    try:
        volumes_root = _VOLUMES_ROOT.resolve()
        anlz_relative = Path(normalized_anlz).resolve(strict=False).relative_to(volumes_root)
    except (OSError, ValueError):
        return ""
    if len(anlz_relative.parts) < 2 or anlz_relative.parts[1].casefold() != "pioneer":
        return ""
    mount = volumes_root / anlz_relative.parts[0]
    try:
        from pyrekordbox.anlz import AnlzFile  # type: ignore
        relative = str(AnlzFile.parse_file(anlz_path).get("path") or "")
    except (ImportError, OSError, KeyError, TypeError, ValueError):
        return ""
    relative = relative.replace("\\", "/")
    # Rekordbox USB PPTH tags are stick-root-relative and often carry a leading
    # slash (/Contents/...). Strip it so join stays under the mount — same rule
    # as tools/spectral_stick_sweep.py. Absolute-drive and .. escapes still fail.
    if relative.startswith("/"):
        relative = relative.lstrip("/")
    if (
        not relative
        or re.match(r"^[A-Za-z]:", relative)
        or ".." in relative.split("/")
    ):
        return ""
    candidate = mount.joinpath(*(part for part in relative.split("/") if part not in ("", ".")))
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(mount.resolve())
    except (OSError, ValueError):
        return ""
    return str(resolved)


def _payload_for_sidecar(
    root: Path,
    record: dict,
    anlz_path: str,
) -> Optional[dict]:
    dat_paths = [
        path for relpath in record["anlz_relpaths"]
        if relpath.lower().endswith(".dat")
        and (path := _sidecar_path(root, relpath)) is not None
        and path.is_file()
    ]
    audio_filepath = _device_audio_filepath(anlz_path)
    if len(dat_paths) != 1 or not audio_filepath:
        return None
    local_anlz_path = str(dat_paths[0])
    local_grid = _extract_beatgrid_from_anlz(local_anlz_path)
    if len(local_grid.get("beatgrid_times_ms", ())) < 2:
        return None

    sidecar_v4 = None
    v4_relpath = record.get("v4_relpath")
    if v4_relpath:
        v4_path = _sidecar_path(root, v4_relpath)
        if v4_path is None:
            return None
        try:
            sidecar_v4 = _features_v4_from_payload(
                json.loads(v4_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError):
            return None
        if sidecar_v4 is None:
            return None
    return {
        "filepath": audio_filepath,
        "bpm": float(record["bpm"]),
        "content_id": str(record["content_id"]),
        "first_beat_ms": local_grid["beatgrid_times_ms"][0],
        **local_grid,
        "soundswitch_id": str(record["soundswitch_id"]),
        "total_ms": float(record["duration_s"]) * 1000.0,
        "laser_tag_beats": list(record["laser_tag_beats"]),
        "local_anlz_path": local_anlz_path,
        "sidecar_v4": sidecar_v4,
    }


def _sidecar_lookup(anlz_path: str, usb_beatgrid: dict) -> Optional[dict]:
    sidecars = tuple(sorted(
        _mounted_sidecar_indexes(),
        key=lambda item: (str(item[0]).casefold(), str(item[0])),
    ))
    if not sidecars:
        return None
    try:
        device_track = _read_device_pdb_track(anlz_path)
    except (OSError, UnicodeError, ValueError, struct.error, IndexError):
        device_track = None
    matches: list[tuple[Path, dict, dict, str]] = []
    misses: list[str] = []
    for root, records in sidecars:
        record, reason, candidate_ids = _select_sidecar_record(
            records, usb_beatgrid, device_track,
        )
        if candidate_ids:
            log.info(
                "[FRES] %s  source=sidecar root=%s candidate_ids=%s",
                reason, root, ",".join(candidate_ids),
            )
            return None
        if record is None:
            misses.append(reason)
            continue
        payload = _payload_for_sidecar(root, record, anlz_path)
        if payload is None:
            misses.append("sidecar-payload-invalid")
            continue
        matches.append((root, record, payload, reason))
    if len(matches) > 1:
        first_record = matches[0][1]
        if all(record == first_record for _root, record, _payload, _reason in matches[1:]):
            installed_root = _INSTALLED_SIDECAR_INDEX.parent
            selected = next(
                (match for match in matches if match[0] == installed_root),
                matches[0],
            )
            log.info(
                "[FRES] sidecar-root-deduplicated  source=sidecar roots=%s selected=%s",
                ",".join(str(root) for root, _record, _payload, _reason in matches),
                selected[0],
            )
            matches = [selected]
        else:
            log.info(
                "[FRES] sidecar-root-ambiguous  source=sidecar roots=%s candidate_ids=%s",
                ",".join(str(root) for root, _record, _payload, _reason in matches),
                ",".join(str(record["content_id"]) for _root, record, _payload, _reason in matches),
            )
            return None
    if not matches:
        log.info(
            "[FRES] sidecar-no-match  source=sidecar roots=%d reasons=%s",
            len(sidecars), ",".join(misses),
        )
        return None
    root, record, payload, reason = matches[0]
    log.info(
        "[FRES] sidecar-match  content_id=%s  method=%s  source=sidecar root=%s",
        record["content_id"], reason, root,
    )
    return payload


def _note_sidecar_only_mode(exc: Exception) -> None:
    global _SIDECAR_ONLY_LOGGED
    if _SIDECAR_ONLY_LOGGED:
        return
    _SIDECAR_ONLY_LOGGED = True
    log.info(
        "[FRES] no local library — sidecar-only mode  err=%s",
        type(exc).__name__,
    )


def _unique_usb_twin(
    usb_times_ms: Sequence[float],
    candidate_grids: Sequence[tuple[object, dict]],
) -> tuple[Optional[tuple[object, dict]], int]:
    """Return the sole fingerprint match and the total passing count."""
    matches = [
        (content, grid)
        for content, grid in candidate_grids
        if _beatgrids_match(usb_times_ms, grid.get("beatgrid_times_ms", ()))
    ]
    return (matches[0] if len(matches) == 1 else None), len(matches)


def _hotcue_marker() -> str:
    # `load_drop_presentation_config` degrades to a "LASER" default on any
    # failure (missing/malformed config) — never raises, never blocks a load.
    return load_drop_presentation_config().hotcue_marker


def _fetch_laser_tag_beats(db, content_id: str, beatgrid_times_ms: list[float], marker: str) -> list[float]:
    """Drop-presentation hot-cue tags (docs/architecture/drop_presentation_authority.md
    §Solo Source Contracts, tier 3). Reads named hot cues from Rekordbox's
    `DjmdCue` rows via ``db.get_cue()`` (verified live 2026-07-04: 413 named cue
    points library-wide; the on-disk ANLZ cue cache is stale/empty and must
    never be used instead). Converts each matching cue's ``InMsec`` to an
    absolute beat position with the SAME beatgrid math the rest of the bridge
    uses (``beat_math._compute_beatgrid_position``), so a marker beat lands in
    the identical coordinate system as ``drop_beat_indices`` — no parallel
    conversion. The caller (``_db_lookup_by_anlz``) wraps this call in its own
    narrow try/except so a curation-data failure here degrades to "no tags"
    without discarding an otherwise-successful track resolution.
    """
    marker_norm = marker.strip().lower()
    if not marker_norm:
        return []
    beats: list[float] = []
    for cue in db.get_cue(ContentID=content_id, rb_local_deleted=0):
        comment = str(getattr(cue, "Comment", None) or "")
        if marker_norm not in comment.lower():
            continue
        in_msec = getattr(cue, "InMsec", None)
        if not isinstance(in_msec, (int, float)) or in_msec < 0:
            continue
        grid_pos = _compute_beatgrid_position(float(in_msec), beatgrid_times_ms)
        if grid_pos is None:
            continue
        beats.append(grid_pos[1])
    return beats


def _payload_for_content(  # type: ignore[no-untyped-def]
    db,
    content,
    beatgrid: dict,
    *,
    local_anlz_path: str = "",
) -> dict:
    """Build the one FILEPATH_RESOLVED payload shape for local and USB twins."""
    filepath = content.FolderPath or ""
    bpm = (content.BPM / 100.0) if content.BPM else 0.0
    content_id = str(content.ID)
    first_beat_ms = beatgrid["beatgrid_times_ms"][0] if beatgrid["beatgrid_times_ms"] else 0.0
    laser_tag_beats: list[float] = []
    try:
        laser_tag_beats = _fetch_laser_tag_beats(
            db, content_id, beatgrid["beatgrid_times_ms"], _hotcue_marker(),
        )
    except Exception as exc:
        # Curation-data failure only: track identity is already confirmed.
        log.warning(
            "[FRES] laser-tag-read-failed  content_id=%s  err=%s",
            content_id, type(exc).__name__,
        )
    payload = {
        "filepath": filepath,
        "bpm": bpm,
        "content_id": content_id,
        "first_beat_ms": first_beat_ms,
        **beatgrid,
        "soundswitch_id": _read_soundswitch_id(filepath) if filepath else "",
        "total_ms": float((content.Length * 1000) if content.Length else 0),
        "laser_tag_beats": laser_tag_beats,
    }
    if local_anlz_path:
        payload["local_anlz_path"] = local_anlz_path
    return payload


def _db_lookup_by_anlz(anlz_path: str) -> Optional[dict]:
    """Look up track metadata using the ANLZ file path UUID.

    The ANLZ path contains a UUID directory that matches the DB's AnalysisDataPath.
    Returns a payload dict ready for FILEPATH_RESOLVED, or None on failure.
    """
    m = re.search(r'USBANLZ/[^/]+/([^/]+)/ANLZ', anlz_path)
    if not m:
        log.debug("_db_lookup_by_anlz: cannot extract UUID from %s", anlz_path)
        return None
    anlz_uuid = m.group(1)
    beatgrid = _extract_beatgrid_from_anlz(anlz_path)
    device_export = _is_device_export_anlz_path(anlz_path, anlz_uuid)

    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
        contents = list(db.get_content())
        for c in contents:
            anlz_db = getattr(c, 'AnalysisDataPath', None) or ""
            if anlz_uuid in anlz_db:
                return _payload_for_content(db, c, beatgrid)
        if device_export:
            candidates = _usb_twin_prefilter(contents, beatgrid)
            candidate_grids = [
                (content, _extract_beatgrid_from_anlz(_local_anlz_path(
                    str(getattr(content, "AnalysisDataPath", "") or "")
                )))
                for content in candidates
            ]
            twin, match_count = _unique_usb_twin(
                beatgrid["beatgrid_times_ms"], candidate_grids,
            )
            if twin is not None:
                content, local_grid = twin
                local_anlz_path = _local_anlz_path(
                    str(getattr(content, "AnalysisDataPath", "") or "")
                )
                log.info(
                    "[FRES] usb-twin-match  content_id=%s  candidates=%d",
                    content.ID, len(candidates),
                )
                return _payload_for_content(
                    db, content, local_grid, local_anlz_path=local_anlz_path,
                )
            reason = "usb-twin-ambiguous" if match_count > 1 else "usb-twin-miss"
            log.info(
                "[FRES] %s  candidates=%d  fingerprint_matches=%d",
                reason, len(candidates), match_count,
            )
            try:
                device_track = _read_device_pdb_track(anlz_path)
            # IndexError guards a crafted guest export.pdb whose in-bounds page
            # structure still points a string offset past the file heap; without
            # it the outer except mislabels the cause as sidecar-only mode.
            except (OSError, UnicodeError, ValueError, struct.error, IndexError) as exc:
                log.info(
                    "[FRES] usb-crossanalysis-unconfirmed  err=%s",
                    type(exc).__name__,
                )
                return _sidecar_lookup(anlz_path, beatgrid)
            if device_track is None:
                log.info("[FRES] usb-crossanalysis-unconfirmed  reason=no-pdb-tags")
                return _sidecar_lookup(anlz_path, beatgrid)
            pdb_candidates = _usb_pdb_candidates(contents, device_track)
            if not pdb_candidates:
                log.info("[FRES] usb-pdb-miss  candidates=0")
                return _sidecar_lookup(anlz_path, beatgrid)
            if len(pdb_candidates) > 1:
                candidate_ids = ",".join(
                    str(getattr(candidate, "ID", "")) for candidate in pdb_candidates
                )
                log.info(
                    "[FRES] usb-pdb-ambiguous  candidate_ids=%s",
                    candidate_ids,
                )
                return _sidecar_lookup(anlz_path, beatgrid)
            content = pdb_candidates[0]
            if not _relaxed_usb_twin_match(content, beatgrid):
                log.info(
                    "[FRES] usb-pdb-conflict  content_id=%s",
                    getattr(content, "ID", ""),
                )
                return _sidecar_lookup(anlz_path, beatgrid)
            # imported-not-analyzed: the DB tag-matched a local import that has no
            # readable ANLZ. Per AWR-211 source-chaining (local DB -> sidecar ->
            # miss), fall through to the sidecar rather than returning here: on the
            # operator's laptop no sidecar match exists so this stays an honest miss
            # (the log's "finish analysis" advice holds), but a foreign laptop can
            # still resolve the track from his stick's sidecar.
            analysis_path = str(getattr(content, "AnalysisDataPath", "") or "")
            local_anlz_path = _local_anlz_path(analysis_path) if analysis_path else ""
            if not local_anlz_path or not os.path.isfile(local_anlz_path):
                log.info(
                    "[FRES] imported-not-analyzed  content_id=%s"
                    "  action=finish analysis in Rekordbox",
                    getattr(content, "ID", ""),
                )
                return _sidecar_lookup(anlz_path, beatgrid)
            local_grid = _extract_beatgrid_from_anlz(local_anlz_path)
            if len(local_grid.get("beatgrid_times_ms", ())) < 2:
                log.info(
                    "[FRES] imported-not-analyzed  content_id=%s"
                    "  action=finish analysis in Rekordbox",
                    getattr(content, "ID", ""),
                )
                return _sidecar_lookup(anlz_path, beatgrid)
            log.info(
                "[FRES] usb-pdb-match  content_id=%s  track_id=%s",
                getattr(content, "ID", ""), device_track["track_id"],
            )
            return _payload_for_content(
                db, content, local_grid, local_anlz_path=local_anlz_path,
            )
        log.debug("_db_lookup_by_anlz: UUID %s not found in DB", anlz_uuid)
    except Exception as exc:
        log.debug("_db_lookup_by_anlz: %s", exc)
        if device_export:
            _note_sidecar_only_mode(exc)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    return _sidecar_lookup(anlz_path, beatgrid) if device_export else None


def _db_lookup(filepath: str) -> tuple[str, float, float]:
    """Return (content_id, bpm, first_beat_ms). All zeros on failure."""
    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
        norm = filepath.replace("\\", "/")
        for c in db.get_content():
            if not c.FolderPath:
                continue
            if c.FolderPath == filepath or c.FolderPath.replace("\\", "/") == norm:
                content_id = str(c.ID)
                bpm = (c.BPM / 100.0) if c.BPM else 0.0
                return content_id, bpm, 0.0  # first_beat_ms needs ANLZ — 0.0 safe default
    except Exception as exc:
        log.debug("DB lookup error: %s", exc)
    finally:
        # FM-6: always close DB to avoid fd leak
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    return "", 0.0, 0.0


# ── Resolver ─────────────────────────────────────────────────────────────────

class FilepathResolver:
    """Triggers lsof-based track identification for a deck.

    One instance shared between both decks; spawns short-lived daemon threads.
    Uses PositionCache for track-length disambiguation (replaces Frida DPU lengths).
    """

    def __init__(self, event_queue: queue.Queue[BridgeEvent], cache: "PositionCache") -> None:  # type: ignore[name-defined]
        self._queue = event_queue
        self._cache = cache
        self._last_trigger: dict[int, float] = {1: 0.0, 2: 0.0}
        self._lock = threading.Lock()

    def resolve_by_anlz(self, deck: int, load_gen: int, anlz_path: str, *, trace_id: str = "") -> None:
        """Resolve by ANLZ; only non-device misses may fall back to lsof."""
        threading.Thread(
            target=self._resolve_anlz_worker,
            args=(deck, load_gen, anlz_path, trace_id),
            daemon=True,
            name=f"anlz-d{deck}",
        ).start()

    def _resolve_anlz_worker(self, deck: int, load_gen: int, anlz_path: str, trace_id: str) -> None:
        try:
            result = _db_lookup_by_anlz(anlz_path)
            if result:
                log.info("[FRES] resolve  deck=%d  src=anlz  file=%s  bpm=%.1f",
                         deck, bf.short(result['filepath']), result['bpm'])
                payload = {**result, 'load_gen': load_gen}
                if trace_id:
                    payload["__trace_id"] = trace_id
                self._queue.put_nowait(BridgeEvent(
                    kind=Ev.FILEPATH_RESOLVED,
                    deck=deck,
                    source='anlz',
                    payload=payload,
                ))
            else:
                if _is_device_export_anlz_path(anlz_path):
                    log.info(
                        "[FRES] resolve-miss  deck=%d  src=anlz"
                        "  reason=usb-twin-unresolved  action=skip-lsof",
                        deck,
                    )
                    return
                log.debug("[FRES] resolve-miss  deck=%d  src=anlz  action=fallback-lsof", deck)
                self.resolve_async(deck, load_gen, trace_id=trace_id)
        except Exception:
            log.exception("_resolve_anlz_worker deck %d failed", deck)

    def resolve_by_title(self, deck: int, load_gen: int, title: str, *, trace_id: str = "") -> None:
        """Fuzzy DB lookup by TL track title. Runs in a daemon thread.

        Used as fallback when ANLZ is unavailable and lsof can't match by
        track length (e.g. DDJ-800 deck 2 where memory track_length_ms = 0).
        Races with lsof — first to post FILEPATH_RESOLVED wins via load_gen check.
        """
        threading.Thread(
            target=self._resolve_title_worker,
            args=(deck, load_gen, title, trace_id),
            daemon=True,
            name=f"title-d{deck}",
        ).start()

    def _resolve_title_worker(self, deck: int, load_gen: int, title: str, trace_id: str) -> None:
        try:
            words = [w.lower() for w in re.split(r"[\s()\[\]\-]+", title) if len(w) > 2]
            if not words:
                return
            db = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
                db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
                best = None
                for c in db.get_content():
                    fp = (c.FolderPath or "").lower()
                    if not fp:
                        continue
                    if title.lower() in fp or all(w in fp for w in words):
                        best = c
                        break
            except Exception as exc:
                log.debug("resolve_by_title deck %d: DB error: %s", deck, exc)
                return
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

            if best is None:
                log.debug("resolve_by_title deck %d: no DB match for '%s'", deck, title)
                return

            fp   = best.FolderPath or ""
            bpm  = (best.BPM / 100.0) if best.BPM else 0.0
            ssid = _read_soundswitch_id(fp) if fp else ""
            total_ms = float((best.Length * 1000) if best.Length else 0)
            log.info("[FRES] resolve  deck=%d  src=title  file=%s  bpm=%.1f",
                     deck, bf.short(fp), bpm)
            payload = {
                    "filepath":       fp,
                    "bpm":            bpm,
                    "content_id":     str(best.ID),
                    "first_beat_ms":  0.0,
                    **_EMPTY_BEATGRID,
                    "soundswitch_id": ssid,
                    "total_ms":       total_ms,
                    "load_gen":       load_gen,
            }
            if trace_id:
                payload["__trace_id"] = trace_id
            self._queue.put_nowait(BridgeEvent(
                kind=Ev.FILEPATH_RESOLVED,
                deck=deck,
                source="title",
                payload=payload,
            ))
        except Exception:
            log.exception("_resolve_title_worker deck %d failed", deck)

    def resolve_async(
        self,
        deck: int,
        load_gen: int,
        other_deck_path: str = "",
        *,
        trace_id: str = "",
    ) -> None:
        """Fire-and-forget lsof probe for deck. Respects LSOF_COOLDOWN_S."""
        now = time.monotonic()
        with self._lock:
            last = self._last_trigger.get(deck, 0.0)
            remaining = LSOF_COOLDOWN_S - (now - last)
            if remaining > 0:
                # FM-4: schedule retry instead of silently dropping
                log.debug("FilepathResolver: cooldown deck %d — retry in %.1fs", deck, remaining)
                threading.Timer(
                    remaining,
                    self.resolve_async,
                    args=(deck, load_gen, other_deck_path),
                    kwargs={"trace_id": trace_id},
                ).start()
                return
            self._last_trigger[deck] = now

        threading.Thread(
            target=self._resolve,
            args=(deck, load_gen, other_deck_path, trace_id),
            daemon=True,
            name=f"lsof-d{deck}",
        ).start()

    def _resolve(self, deck: int, load_gen: int, other_deck_path: str, trace_id: str) -> None:
        try:
            pid = _rb_pid()
            if not pid:
                log.debug("lsof deck %d: rekordbox not found", deck)
                return

            files = _lsof_audio_files(pid)
            if not files:
                # FM-10: retry once after 500ms (RB may be mid-swap between fds)
                log.debug("lsof deck %d: 0 audio files — retrying in 500ms", deck)
                time.sleep(0.5)
                files = _lsof_audio_files(pid)
            if not files:
                log.warning("[FRES] resolve-fail  deck=%d  src=lsof  reason=no-audio-files", deck)
                return

            # Use track length from memory cache (replaces Frida frida_dpu_lengths)
            snap: Optional[PositionSnapshot] = self._cache.get(deck)
            target_ms = snap.track_length_ms if snap and snap.track_length_ms > 0 else 0

            matched: Optional[str] = None
            if target_ms > 0:
                for fp in files:
                    if fp == other_deck_path:
                        continue
                    dur = _duration_ms(fp)
                    if dur is not None and abs(dur - target_ms) < LSOF_LEN_TOLERANCE_MS:
                        matched = fp
                        break
            elif len(files) == 1 and files[0] != other_deck_path:
                matched = files[0]

            if not matched:
                if target_ms == 0:
                    log.debug(
                        "lsof deck %d: track_length_ms=0 — title DB lookup is primary resolver",
                        deck,
                    )
                else:
                    log.debug("lsof deck %d: no match (target_ms=%d, files=%d)", deck, target_ms, len(files))
                return

            # Guard: if memory track length changed while we ran, the match is stale
            snap2 = self._cache.get(deck)
            new_len = snap2.track_length_ms if snap2 else 0
            if target_ms > 0 and new_len > 0 and abs(new_len - target_ms) > LSOF_LEN_TOLERANCE_MS:
                log.info("[FRES] resolve-stale  deck=%d  reason=length-changed  %dms→%dms",
                         deck, target_ms, new_len)
                return

            log.info("[FRES] match  deck=%d  src=lsof  file=%s", deck, bf.short(matched))

            content_id, bpm, first_beat_ms = _db_lookup(matched)
            ssid = _read_soundswitch_id(matched)
            total_ms = float(target_ms) if target_ms else 0.0

            payload = {
                    "filepath":        matched,
                    "bpm":             bpm,
                    "content_id":      content_id,
                    "first_beat_ms":   first_beat_ms,
                    **_EMPTY_BEATGRID,
                    "soundswitch_id":  ssid,
                    "total_ms":        total_ms,
                    "load_gen":        load_gen,
            }
            if trace_id:
                payload["__trace_id"] = trace_id
            self._queue.put_nowait(BridgeEvent(
                kind=Ev.FILEPATH_RESOLVED,
                deck=deck,
                source="lsof",
                payload=payload,
            ))
        except Exception:
            log.exception("FilepathResolver._resolve deck %d failed", deck)
