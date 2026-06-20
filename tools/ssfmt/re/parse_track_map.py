#!/usr/bin/env python3
"""Discover and validate SoundSwitch TrackMap identity subrecords.

This is a research parser.  It names only the repeated mapping subrecord that
has been byte-verified in the current v3 TrackMap; it deliberately does not
invent names for the surrounding top-level object graph.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


_MAPPING_PREFIX = b"\x04\x00\x00\x00\x01"
_SCRIPT_FILENAME = re.compile(
    r"^\{([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\}\.ssfile$"
)
_AUDIO_SUFFIXES = {
    ".aac",
    ".aif",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}


class ParseError(ValueError):
    """A candidate mapping subrecord failed a structural check."""


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ParseError(f"u32 outside file at offset {offset}")
    return struct.unpack_from("<I", data, offset)[0]


def _qstring(data: bytes, offset: int) -> tuple[str, int, dict[str, int]]:
    units = _u32(data, offset)
    if not 1 <= units <= 32768:
        raise ParseError(f"invalid QString length {units} at offset {offset}")
    raw_offset = offset + 4
    end = raw_offset + units * 2
    if end > len(data):
        raise ParseError(f"QString outside file at offset {offset}")
    try:
        decoded = data[raw_offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise ParseError(f"invalid UTF-16LE at offset {offset}") from exc
    if not decoded.endswith("\0") or "\0" in decoded[:-1]:
        raise ParseError(f"QString lacks one trailing NUL at offset {offset}")
    value = decoded[:-1]
    if any(character not in "\r\n\t" and ord(character) < 32 for character in value):
        raise ParseError(f"QString contains a control character at offset {offset}")
    return value, end, {
        "length_offset": offset,
        "data_offset": raw_offset,
        "end_offset": end,
        "code_units_including_nul": units,
    }


def _optional_qstring(
    data: bytes, offset: int, field_name: str
) -> tuple[str | None, int, dict[str, Any]]:
    flag = _u32(data, offset)
    metadata: dict[str, Any] = {"flag_offset": offset, "present": bool(flag)}
    offset += 4
    if flag == 0:
        metadata["end_offset"] = offset
        return None, offset, metadata
    if flag != 1:
        raise ParseError(f"invalid {field_name} presence flag {flag} at offset {offset - 4}")
    value, offset, string_metadata = _qstring(data, offset)
    metadata.update(string_metadata)
    return value, offset, metadata


def _qt_uuid(raw: bytes) -> str:
    if len(raw) != 16:
        raise ParseError("UUID must be exactly 16 bytes")
    first, second, third = struct.unpack_from("<IHH", raw, 0)
    tail = raw[8:]
    return (
        f"{first:08X}-{second:04X}-{third:04X}-"
        f"{tail[0]:02X}{tail[1]:02X}-"
        f"{''.join(f'{byte:02X}' for byte in tail[2:])}"
    )


def _normalize_ssid(value: str) -> str:
    return value.strip().strip("{}").upper()


def _scan_mappings(data: bytes) -> tuple[list[dict[str, Any]], int]:
    mappings: list[dict[str, Any]] = []
    rejected_candidates = 0
    search_offset = 0
    while True:
        marker_offset = data.find(_MAPPING_PREFIX, search_offset)
        if marker_offset < 0:
            break
        search_offset = marker_offset + 1
        uuid_offset = marker_offset + len(_MAPPING_PREFIX)
        try:
            ssid = _qt_uuid(data[uuid_offset : uuid_offset + 16])
            offset = uuid_offset + 16
            title, offset, title_meta = _optional_qstring(data, offset, "title")
            artist, offset, artist_meta = _optional_qstring(data, offset, "artist")
            filepath, offset, filepath_meta = _optional_qstring(data, offset, "filepath")
            if not filepath or Path(filepath).suffix.casefold() not in _AUDIO_SUFFIXES:
                raise ParseError("candidate does not end with an audio filepath")
        except ParseError:
            rejected_candidates += 1
            continue
        mappings.append(
            {
                "mapping_index": len(mappings),
                "marker_offset": marker_offset,
                "uuid_offset": uuid_offset,
                "metadata_end_offset": offset,
                "soundswitch_id": ssid,
                "title": title,
                "artist": artist,
                "filepath": filepath,
                "filepath_exists": Path(filepath).is_file(),
                "field_offsets": {
                    "title": title_meta,
                    "artist": artist_meta,
                    "filepath": filepath_meta,
                },
            }
        )
    return mappings, rejected_candidates


def _read_audio_tag(filepath: Path) -> dict[str, Any]:
    if not filepath.is_file():
        return {"status": "stale_filepath", "value": None}
    value = ""
    errors: list[str] = []
    try:
        from mutagen import File as MutagenFile  # type: ignore

        audio = MutagenFile(filepath)
        if audio and audio.tags and hasattr(audio.tags, "getall"):
            for tag in audio.tags.getall("TXXX"):
                if str(getattr(tag, "desc", "")).casefold() == "soundswitch_id":
                    text = getattr(tag, "text", None)
                    value = str(text[0]) if text else ""
                    break
        if not value and audio and audio.tags and hasattr(audio.tags, "get"):
            for key in ("soundswitch_id", "SOUNDSWITCH_ID"):
                tagged = audio.tags.get(key)
                if tagged:
                    if isinstance(tagged, (list, tuple)):
                        value = str(tagged[0]) if tagged else ""
                    else:
                        value = str(tagged)
                    break
    except Exception as exc:  # pragma: no cover - depends on local media codecs
        errors.append(f"mutagen.File: {type(exc).__name__}: {exc}")
    if not value:
        try:
            from mutagen.id3 import ID3  # type: ignore

            for tag in ID3(filepath).getall("TXXX"):
                if str(tag.desc).casefold() == "soundswitch_id":
                    value = str(tag.text[0]) if tag.text else ""
                    break
        except Exception as exc:  # pragma: no cover - format-specific fallback
            errors.append(f"ID3: {type(exc).__name__}: {exc}")
    if value:
        return {"status": "present", "value": _normalize_ssid(value), "raw_value": value}
    return {"status": "missing", "value": None, "read_errors": errors}


def _duplicates(mappings: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        groups[str(mapping[field])].append(mapping)
    return [
        {
            field: value,
            "count": len(group),
            "mapping_indices": [item["mapping_index"] for item in group],
            "marker_offsets": [item["marker_offset"] for item in group],
        }
        for value, group in sorted(groups.items())
        if len(group) > 1
    ]


def _casefold_collisions(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for mapping in mappings:
        filepath = str(mapping["filepath"])
        groups[filepath.casefold()].add(filepath)
    return [
        {"casefold_path": key, "spellings": sorted(values)}
        for key, values in sorted(groups.items())
        if len(values) > 1
    ]


def _project_script_ids(project_dir: Path | None) -> list[str]:
    if project_dir is None:
        return []
    ids = []
    for path in project_dir.glob("*.ssfile"):
        match = _SCRIPT_FILENAME.match(path.name)
        if match:
            ids.append(match.group(1).upper())
    return sorted(ids)


def _tag_report(mappings: list[dict[str, Any]]) -> dict[str, Any]:
    by_path: dict[str, dict[str, Any]] = {}
    rows = []
    for mapping in mappings:
        filepath = str(mapping["filepath"])
        if filepath not in by_path:
            by_path[filepath] = _read_audio_tag(Path(filepath))
        tag = by_path[filepath]
        match = tag.get("value") == mapping["soundswitch_id"] if tag.get("value") else None
        rows.append(
            {
                "mapping_index": mapping["mapping_index"],
                "soundswitch_id": mapping["soundswitch_id"],
                "filepath": filepath,
                "tag": tag,
                "tag_matches_mapping_id": match,
            }
        )
    statuses = Counter(row["tag"]["status"] for row in rows)
    comparisons = Counter(
        "not_comparable"
        if row["tag_matches_mapping_id"] is None
        else "exact_match"
        if row["tag_matches_mapping_id"]
        else "mismatch"
        for row in rows
    )
    return {
        "mapping_status_counts": dict(sorted(statuses.items())),
        "mapping_comparison_counts": dict(sorted(comparisons.items())),
        "unique_paths_read": len(by_path),
        "rows": rows,
    }


def analyze(
    track_map: Path, project_dir: Path | None, check_tags: bool
) -> dict[str, Any]:
    data = track_map.read_bytes()
    if len(data) < 8:
        raise ParseError("TrackMap is shorter than its magic/version header")
    mappings, rejected_candidates = _scan_mappings(data)
    if not mappings:
        raise ParseError("no structurally valid identity mapping subrecords found")
    project_ids = _project_script_ids(project_dir)
    mapped_ids = sorted({mapping["soundswitch_id"] for mapping in mappings})
    project_set = set(project_ids)
    mapped_set = set(mapped_ids)
    result: dict[str, Any] = {
        "path": str(track_map),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "magic_hex": data[:4].hex(),
        "version": _u32(data, 4),
        "parse_scope": "repeated identity mapping subrecords",
        "status": "partial",
        "unsupported_reason": (
            "top-level TrackMap object-graph fields outside the repeated mapping "
            "subrecords remain unnamed"
        ),
        "mapping_prefix_hex": _MAPPING_PREFIX.hex(),
        "mapping_count": len(mappings),
        "rejected_prefix_candidates": rejected_candidates,
        "unique_soundswitch_id_count": len(mapped_ids),
        "unique_filepath_count": len({mapping["filepath"] for mapping in mappings}),
        "existing_filepath_mapping_count": sum(
            1 for mapping in mappings if mapping["filepath_exists"]
        ),
        "stale_filepath_mapping_count": sum(
            1 for mapping in mappings if not mapping["filepath_exists"]
        ),
        "duplicate_soundswitch_ids": _duplicates(mappings, "soundswitch_id"),
        "duplicate_filepaths": _duplicates(mappings, "filepath"),
        "casefold_filepath_collisions": _casefold_collisions(mappings),
        "project_relationship": {
            "project_dir": str(project_dir) if project_dir else None,
            "project_scripted_id_count": len(project_ids),
            "project_scripted_ids": project_ids,
            "mapped_project_id_count": len(project_set & mapped_set),
            "project_ids_missing_from_track_map": sorted(project_set - mapped_set),
            "track_map_ids_without_current_script_file": sorted(mapped_set - project_set),
        },
        "mappings": mappings,
    }
    if check_tags:
        result["audio_tag_checks"] = _tag_report(mappings)
    else:
        result["audio_tag_checks"] = {
            "status": "not_requested",
            "enable_with": "--check-tags",
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("track_map", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument(
        "--check-tags",
        action="store_true",
        help="read metadata tags from mapped audio files; never modifies them",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(args.track_map, args.project_dir, args.check_tags),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
