#!/usr/bin/env python3
"""Compare two SoundSwitch project snapshots without modifying either source.

This research helper is intentionally fail-closed.  It inventories every file,
checks that each source stays stable while read, reports aligned byte-offset
ranges, and compares the byte-verified semantic structures already decoded by
the other helpers in this directory.  It is not a production exporter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyze_scripted_layouts import _select_fallback_candidate, _timeline_summary
from analyze_scripted_ssfile import parse_scripted_structure
from analyze_ssfile_structure import TRAILER_SIZE, parse_autoloop_structure
from analyze_static_looks import parse_static_looks
from analyze_fixture_prefix import ParseError as FixtureParseError
from analyze_fixture_prefix import parse_fixture_prefix
from parse_autoloop_catalogs import parse_catalog
from parse_track_map import _scan_mappings
from parse_venue_cues import parse_venue_cues


_SCRIPT_FILE = re.compile(
    r"^\{([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\}\.ssfile$"
)
_AUTOLOOP_FILE = re.compile(r"^SSAutoLoop(\d+)\.ssfile$")
_REQUIRED_METADATA = {
    "experiment_id",
    "soundswitch_version",
    "scratch_project_path",
    "exact_ui_action",
    "prediction",
    "render_affecting",
}


class SnapshotError(RuntimeError):
    """The source could not be read as one stable, complete snapshot."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stat_signature(stat: os.stat_result) -> tuple[int, int, int, int]:
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _read_stable(path: Path) -> bytes:
    path_before = path.stat(follow_symlinks=False)
    if not path.is_file() or path.is_symlink():
        raise SnapshotError(f"unsupported non-regular source path: {path}")
    with path.open("rb") as handle:
        open_before = os.fstat(handle.fileno())
        data = handle.read()
        open_after = os.fstat(handle.fileno())
    path_after = path.stat(follow_symlinks=False)
    signatures = {
        _stat_signature(path_before),
        _stat_signature(open_before),
        _stat_signature(open_after),
        _stat_signature(path_after),
    }
    if len(signatures) != 1 or len(data) != path_after.st_size:
        raise SnapshotError(f"source changed while being read: {path}")
    return data


def _relative_files(root: Path) -> list[str]:
    if not root.is_dir():
        raise SnapshotError(f"project directory does not exist: {root}")
    relative = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SnapshotError(f"symlink is unsupported in project inventory: {path}")
        if path.is_file():
            relative.append(path.relative_to(root).as_posix())
    return sorted(relative, key=lambda value: value.encode("utf-8"))


def _file_class(relative_path: str) -> str:
    name = Path(relative_path).name
    if relative_path == ".ssproj":
        return "project_manifest"
    if name in {"SoundSwitchAutoLoops.bin", "SoundSwitchAutoLoopsEx.bin"}:
        return "autoloop_catalog"
    if name == "SoundSwitchTrackMap.bin":
        return "track_map"
    if name == "SoundSwitchVenues.bin":
        return "current_venue"
    if name == "SoundSwitchVenues.bin.backup":
        return "non_authoritative_venue_backup"
    if _AUTOLOOP_FILE.match(name):
        return "autoloop"
    if _SCRIPT_FILE.match(name):
        return "scripted_track"
    if relative_path.endswith(".ssa"):
        return "track_analysis_sidecar"
    if relative_path.endswith(".sspreset"):
        return "automation_preset"
    if relative_path.startswith("recordable/"):
        return "recordable_control"
    if relative_path.endswith(".mp4"):
        return "media"
    return "unclassified"


def _project_manifest(blobs: dict[str, bytes]) -> dict[str, Any]:
    data = blobs.get(".ssproj")
    if data is None:
        return {"status": "missing", "unsupported_reason": ".ssproj is absent"}
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {
            "status": "unsupported",
            "sha256": _sha256(data),
            "unsupported_reason": f"invalid .ssproj JSON: {error}",
        }
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), dict):
        return {
            "status": "unsupported",
            "sha256": _sha256(data),
            "unsupported_reason": ".ssproj lacks an object version field",
        }
    version = manifest["version"]
    components = [version.get(key) for key in ("major", "minor", "hotfix")]
    if not all(isinstance(value, int) for value in components):
        return {
            "status": "unsupported",
            "sha256": _sha256(data),
            "unsupported_reason": ".ssproj version components are not integers",
        }
    return {
        "status": "parsed",
        "sha256": _sha256(data),
        "project_id": manifest.get("id"),
        "version": version,
        "version_text": ".".join(str(value) for value in components),
    }


def _snapshot(root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    start_paths = _relative_files(root)
    blobs: dict[str, bytes] = {}
    files = []
    for relative_path in start_paths:
        data = _read_stable(root / relative_path)
        blobs[relative_path] = data
        files.append(
            {
                "relative_path": relative_path,
                "file_class": _file_class(relative_path),
                "size": len(data),
                "sha256": _sha256(data),
            }
        )
    end_paths = _relative_files(root)
    if start_paths != end_paths:
        raise SnapshotError(
            f"project inventory changed during scan: start={start_paths!r}, end={end_paths!r}"
        )
    return (
        {
            "project_path": str(root),
            "file_count": len(files),
            "inventory_order": "normalized project-relative UTF-8 byte order",
            "files": files,
        },
        blobs,
    )


def _aligned_diff_ranges(before: bytes, after: bytes) -> dict[str, Any]:
    common = min(len(before), len(after))
    ranges = []
    start = None
    changed = 0
    for offset in range(common):
        differs = before[offset] != after[offset]
        if differs:
            changed += 1
            if start is None:
                start = offset
        elif start is not None:
            ranges.append(
                {
                    "kind": "aligned_byte_difference",
                    "start_offset": start,
                    "before_end_offset_exclusive": offset,
                    "after_end_offset_exclusive": offset,
                }
            )
            start = None
    if start is not None:
        ranges.append(
            {
                "kind": "aligned_byte_difference",
                "start_offset": start,
                "before_end_offset_exclusive": common,
                "after_end_offset_exclusive": common,
            }
        )
    if len(before) != len(after):
        ranges.append(
            {
                "kind": "length_tail",
                "start_offset": common,
                "before_end_offset_exclusive": len(before),
                "after_end_offset_exclusive": len(after),
            }
        )
    return {
        "before_size": len(before),
        "after_size": len(after),
        "aligned_changed_byte_count": changed,
        "range_count": len(ranges),
        "ranges": ranges,
    }


def _map_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_keys = set(before)
    after_keys = set(after)
    changed = []
    for key in sorted(before_keys & after_keys):
        if before[key] != after[key]:
            changed.append({"identity": key, "before": before[key], "after": after[key]})
    return {
        "added": [
            {"identity": key, "after": after[key]}
            for key in sorted(after_keys - before_keys)
        ],
        "removed": [
            {"identity": key, "before": before[key]}
            for key in sorted(before_keys - after_keys)
        ],
        "changed": changed,
    }


def _diff_has_changes(diff: dict[str, Any]) -> bool:
    return any(diff[key] for key in ("added", "removed", "changed"))


def _without_fields(row: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    """Remove diagnostic source-location fields from semantic comparison."""
    return {key: value for key, value in row.items() if key not in fields}


def _catalog_semantics(
    catalogs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        identity: _without_fields(row, {"record_offset"})
        for identity, row in catalogs.items()
    }


def _venue_semantics(
    venue: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        identity: _without_fields(row, {"offset"})
        for identity, row in venue.items()
    }


def _track_map_semantics(
    by_soundswitch_id: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    result = {}
    for soundswitch_id, rows in by_soundswitch_id.items():
        semantic_rows = [
            _without_fields(row, {"marker_offset"}) for row in rows
        ]
        result[soundswitch_id] = sorted(
            semantic_rows,
            key=lambda row: (row["filepath"], row["title"], row["artist"]),
        )
    return result


def _single_record_offset_changes(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    *,
    offset_field: str,
    ignored_fields: set[str],
) -> list[dict[str, Any]]:
    changes = []
    for identity in sorted(set(before) & set(after)):
        before_row = before[identity]
        after_row = after[identity]
        if _without_fields(before_row, ignored_fields) != _without_fields(
            after_row, ignored_fields
        ):
            continue
        if before_row.get(offset_field) == after_row.get(offset_field):
            continue
        changes.append(
            {
                "identity": identity,
                "before_offset": before_row.get(offset_field),
                "after_offset": after_row.get(offset_field),
                "classification": "serialization_location_only",
            }
        )
    return changes


def _track_map_offset_changes(
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    changes = []

    def grouped(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[int]]:
        result: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        for row in rows:
            key = (row["filepath"], row["title"], row["artist"])
            result[key].append(row["marker_offset"])
        return {key: sorted(offsets) for key, offsets in result.items()}

    for soundswitch_id in sorted(set(before) & set(after)):
        before_groups = grouped(before[soundswitch_id])
        after_groups = grouped(after[soundswitch_id])
        for record_key in sorted(set(before_groups) & set(after_groups)):
            before_offsets = before_groups[record_key]
            after_offsets = after_groups[record_key]
            if before_offsets == after_offsets:
                continue
            if len(before_offsets) != len(after_offsets):
                continue
            changes.append(
                {
                    "soundswitch_id": soundswitch_id,
                    "record": {
                        "filepath": record_key[0],
                        "title": record_key[1],
                        "artist": record_key[2],
                    },
                    "before_offsets": before_offsets,
                    "after_offsets": after_offsets,
                    "classification": "serialization_location_only",
                }
            )
    return changes


def _changed_field_names(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


def _operations(
    artifact_class: str,
    diff: dict[str, Any],
    *,
    rename_field: str | None = None,
) -> list[dict[str, Any]]:
    operations = [
        {
            "artifact_class": artifact_class,
            "identity": row["identity"],
            "operation": "add",
        }
        for row in diff["added"]
    ]
    operations.extend(
        {
            "artifact_class": artifact_class,
            "identity": row["identity"],
            "operation": "remove",
        }
        for row in diff["removed"]
    )
    for row in diff["changed"]:
        changed_fields = (
            _changed_field_names(row["before"], row["after"])
            if isinstance(row["before"], dict) and isinstance(row["after"], dict)
            else []
        )
        operation = (
            "rename"
            if rename_field is not None and changed_fields == [rename_field]
            else "replace"
        )
        operations.append(
            {
                "artifact_class": artifact_class,
                "identity": row["identity"],
                "operation": operation,
                "changed_fields": changed_fields,
            }
        )
    return operations


def _track_map_operations(diff: dict[str, Any]) -> list[dict[str, Any]]:
    operations = _operations("track_map_identity", diff)
    changed_by_identity = {row["identity"]: row for row in diff["changed"]}
    for operation in operations:
        row = changed_by_identity.get(operation["identity"])
        if row is None:
            continue
        before_rows = row["before"]
        after_rows = row["after"]
        before_counter = Counter(
            json.dumps(record, sort_keys=True, separators=(",", ":"))
            for record in before_rows
        )
        after_counter = Counter(
            json.dumps(record, sort_keys=True, separators=(",", ":"))
            for record in after_rows
        )
        if before_counter != after_counter and not (before_counter - after_counter):
            operation["operation"] = "add_locator"
            operation["changed_fields"] = ["mapping_records"]
            operation["added_records"] = [
                json.loads(serialized)
                for serialized, count in sorted((after_counter - before_counter).items())
                for _ in range(count)
            ]
            continue
        if before_counter != after_counter and not (after_counter - before_counter):
            operation["operation"] = "remove_locator"
            operation["changed_fields"] = ["mapping_records"]
            operation["removed_records"] = [
                json.loads(serialized)
                for serialized, count in sorted((before_counter - after_counter).items())
                for _ in range(count)
            ]
            continue
        if len(before_rows) != len(after_rows):
            operation["changed_fields"] = ["mapping_records"]
            continue
        paths_only = True
        case_only = True
        path_changes = []
        for before, after in zip(before_rows, after_rows):
            before_without_path = {
                key: value for key, value in before.items() if key != "filepath"
            }
            after_without_path = {
                key: value for key, value in after.items() if key != "filepath"
            }
            if before_without_path != after_without_path:
                paths_only = False
                break
            if before["filepath"] != after["filepath"]:
                path_changes.append(
                    {"before": before["filepath"], "after": after["filepath"]}
                )
                case_only = case_only and (
                    before["filepath"].casefold() == after["filepath"].casefold()
                )
        if paths_only and path_changes:
            operation["operation"] = "relocate"
            operation["changed_fields"] = ["filepath"]
            operation["case_only_locator_change"] = case_only
            operation["path_changes"] = path_changes
        elif operation.get("changed_fields") == []:
            operation["changed_fields"] = ["mapping_records"]
    return operations


def _component_diff(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    before_map = {str(row["offset"]): row for row in before}
    after_map = {str(row["offset"]): row for row in after}
    return _map_diff(before_map, after_map)


def _dictionary_component_diff(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> dict[str, Any]:
    def semantic(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key != "offset"}

    return _map_diff(
        {row["guid"]: semantic(row) for row in before},
        {row["guid"]: semantic(row) for row in after},
    )


_TIMELINE_DERIVED_FIELDS = {
    "offset",
    "reference_rule",
    "resolved_dictionary_index",
    "direct_dictionary_index",
    "one_based_dictionary_index",
}


def _timeline_semantic(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in _TIMELINE_DERIVED_FIELDS
    }


def _timeline_component_diff(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare timeline records by meaning, not serialization offset.

    Exact semantic matches are consumed first. Remaining records are paired by
    cue/control identity so an insertion before an existing record does not
    masquerade as a change to every shifted record.
    """

    before_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    after_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)

    def group_key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            row.get("raw_cue_reference"),
            row.get("reference_kind"),
            row.get("field_a"),
            row.get("field_b"),
        )

    for row in before:
        before_groups[group_key(row)].append(row)
    for row in after:
        after_groups[group_key(row)].append(row)

    added = []
    removed = []
    changed = []
    for key in sorted(set(before_groups) | set(after_groups), key=repr):
        before_rows = before_groups.get(key, [])
        after_rows = after_groups.get(key, [])
        after_by_semantic: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in after_rows:
            serialized = json.dumps(
                _timeline_semantic(row), sort_keys=True, separators=(",", ":")
            )
            after_by_semantic[serialized].append(row)

        unmatched_before = []
        for row in before_rows:
            serialized = json.dumps(
                _timeline_semantic(row), sort_keys=True, separators=(",", ":")
            )
            matches = after_by_semantic.get(serialized)
            if matches:
                matches.pop()
            else:
                unmatched_before.append(row)
        unmatched_after = [
            row
            for rows in after_by_semantic.values()
            for row in rows
        ]

        time_field = "time" if any("time" in row for row in before_rows + after_rows) else "elapsed"
        unmatched_before.sort(key=lambda row: (row.get(time_field, 0), row["offset"]))
        unmatched_after.sort(key=lambda row: (row.get(time_field, 0), row["offset"]))
        paired = min(len(unmatched_before), len(unmatched_after))
        identity_prefix = ":".join(str(part) for part in key)
        for index in range(paired):
            changed.append(
                {
                    "identity": f"{identity_prefix}:{index}",
                    "before": unmatched_before[index],
                    "after": unmatched_after[index],
                }
            )
        removed.extend(
            {
                "identity": f"{identity_prefix}:removed:{index}",
                "before": row,
            }
            for index, row in enumerate(unmatched_before[paired:])
        )
        added.extend(
            {
                "identity": f"{identity_prefix}:added:{index}",
                "after": row,
            }
            for index, row in enumerate(unmatched_after[paired:])
        )

    return {"added": added, "removed": removed, "changed": changed}


def _catalogs(blobs: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    result = {}
    for relative_path in ("SoundSwitchAutoLoops.bin", "SoundSwitchAutoLoopsEx.bin"):
        if relative_path not in blobs:
            continue
        try:
            parsed = parse_catalog(blobs[relative_path])
        except ValueError as error:
            result[f"unsupported:{relative_path}"] = {
                "source_path": relative_path,
                "status": "unsupported",
                "size": len(blobs[relative_path]),
                "sha256": _sha256(blobs[relative_path]),
                "unsupported_reason": str(error),
            }
            continue
        for entry in parsed["entries"]:
            identity = str(entry["app_log_index"])
            if identity in result:
                raise SnapshotError(f"duplicate autoloop AppLog index {identity}")
            result[identity] = {
                "source_path": relative_path,
                "record_offset": entry["record_offset"],
                "file_number": entry["file_number"],
                "display_name": entry["display_name"],
                "category_index": entry["category_index"],
                "category": entry["category"],
                "ordering": entry["ordering"],
                "bars": entry["bars"],
                "enabled": entry["enabled"],
            }
    return result


def _venue(blobs: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    data = blobs.get("SoundSwitchVenues.bin")
    if data is None:
        return {}
    result = {}
    for cue in parse_venue_cues(data):
        guid = cue["cue_guid"]
        if guid in result:
            raise SnapshotError(f"duplicate Venue cue GUID {guid}")
        result[guid] = {
            "offset": cue["offset"],
            "name": cue["name"],
            "fixture_profile_guid": cue["fixture_profile_guid"],
            "groups": cue["groups"],
        }
    return result


def _static_looks(blobs: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    data = blobs.get("SoundSwitchVenues.bin")
    if data is None:
        return {}
    result = {}
    for look in parse_static_looks(data):
        identity = str(look["slot_ordinal"])
        result[identity] = {
            "offset": look["offset"],
            "end_offset": look["end_offset"],
            "name": look["name"],
            "enabled": look["enabled"],
            "fixture_instance_ids": look["fixture_instance_ids"],
            "primary_values": [
                {
                    "fixture_instance_id": row["fixture_instance_id"],
                    "value": row["value"],
                }
                for row in look["primary_values"]
            ],
            "secondary_values": [
                {
                    "fixture_instance_id": row["fixture_instance_id"],
                    "value": row["value"],
                }
                for row in look["secondary_values"]
            ],
            "states": [
                {
                    "fixture_instance_id": row["fixture_instance_id"],
                    "state": row["state"],
                    "reserved": row["reserved"],
                }
                for row in look["states"]
            ],
            "positions": [
                {
                    "fixture_instance_id": row["fixture_instance_id"],
                    "position_reference_guid": row["position_reference_guid"],
                }
                for row in look["positions"]
            ],
            "groups": look["groups"],
        }
    return result


def _static_look_operations(diff: dict[str, Any]) -> list[dict[str, Any]]:
    operations = []
    for row in diff["added"]:
        operations.append(
            {"artifact_class": "static_look_slot", "identity": row["identity"], "operation": "add"}
        )
    for row in diff["removed"]:
        operations.append(
            {"artifact_class": "static_look_slot", "identity": row["identity"], "operation": "remove"}
        )
    for row in diff["changed"]:
        changed_fields = _changed_field_names(row["before"], row["after"])
        if not row["before"]["name"] and row["after"]["name"]:
            operation = "create_in_slot"
        elif row["before"]["name"] and not row["after"]["name"]:
            operation = "clear_slot"
        elif changed_fields == ["name"]:
            operation = "rename"
        else:
            operation = "replace"
        operations.append(
            {
                "artifact_class": "static_look_slot",
                "identity": row["identity"],
                "operation": operation,
                "changed_fields": changed_fields,
            }
        )
    return operations


def _track_map(blobs: dict[str, bytes]) -> dict[str, Any]:
    data = blobs.get("SoundSwitchTrackMap.bin")
    if data is None:
        return {"status": "missing", "by_soundswitch_id": {}}
    mappings, rejected = _scan_mappings(data)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        grouped[mapping["soundswitch_id"]].append(
            {
                "marker_offset": mapping["marker_offset"],
                "title": mapping["title"],
                "artist": mapping["artist"],
                "filepath": mapping["filepath"],
            }
        )
    return {
        "status": "partial",
        "mapping_count": len(mappings),
        "rejected_prefix_candidates": rejected,
        "unsupported_reason": "top-level TrackMap object graph remains unnamed",
        "by_soundswitch_id": {
            ssid: sorted(rows, key=lambda row: row["marker_offset"])
            for ssid, rows in sorted(grouped.items())
        },
    }


def _autoloops(blobs: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    result = {}
    for relative_path, data in sorted(blobs.items()):
        match = _AUTOLOOP_FILE.match(Path(relative_path).name)
        if not match:
            continue
        try:
            # PROVISIONAL one_based (provenance-dependent); change-detection is
            # convention-robust since both snapshots use the same rule.
            parsed = parse_autoloop_structure(data, "one_based")
        except ValueError as error:
            result[relative_path] = {
                "file_number": int(match.group(1)),
                "size": len(data),
                "sha256": _sha256(data),
                "version": (
                    struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else None
                ),
                "status": "unsupported",
                "unsupported_reason": str(error),
            }
            continue
        shared_start = parsed["shared_block_offset"]
        shared_end = shared_start + parsed["shared_block_size"]
        if parsed["layout"] == "compact_shared441_dictionary_timeline":
            fixture_summary: dict[str, Any] = {
                "status": "not_embedded",
                "reason": (
                    "compact newly-created autoloop inherits project/Venue fixture context"
                ),
            }
        else:
            try:
                fixture = parse_fixture_prefix(data)
                fixture_summary = {
                    "status": "parsed",
                    "fixture_profile_guid_raw_hex": fixture["fixture_profile_guid_raw_hex"],
                    "groups_sha256": fixture["groups_sha256"],
                    "groups": [
                        {
                            "record_offset": group["record_offset"],
                            "group_id": group["group_id"],
                            "parent_or_owner_reference": group["parent_or_owner_reference"],
                            "positions": group["positions"],
                        }
                        for group in fixture["groups"]
                    ],
                }
            except FixtureParseError as error:
                fixture_summary = {"status": "unsupported", "reason": str(error)}
        result[relative_path] = {
            "file_number": int(match.group(1)),
            "size": len(data),
            "sha256": _sha256(data),
            "status": "parsed",
            "layout": parsed["layout"],
            "version": parsed["version"],
            "fixture": fixture_summary,
            "shared_block_sha256": _sha256(data[shared_start:shared_end]),
            "events": parsed["events"],
            "cues": parsed["cues"],
            "timeline": parsed["timeline"],
            "trailer_hex": parsed["trailer_hex"],
            "unparsed_extra_size": parsed["extra_size"],
        }
    return result


def _shared_table(blobs: dict[str, bytes]) -> bytes | None:
    candidates = sorted(
        path for path in blobs if _AUTOLOOP_FILE.match(Path(path).name)
    )
    preferred = "SSAutoLoop5.ssfile"
    ordered = ([preferred] if preferred in blobs else []) + [
        path for path in candidates if path != preferred
    ]
    for relative_path in ordered:
        try:
            parsed = parse_autoloop_structure(blobs[relative_path], "one_based")
        except ValueError:
            continue
        start = parsed["shared_block_offset"]
        return blobs[relative_path][start : start + parsed["shared_block_size"]]
    return None


def _scripted(blobs: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    result = {}
    shared_table = _shared_table(blobs)
    for relative_path, data in sorted(blobs.items()):
        match = _SCRIPT_FILE.match(Path(relative_path).name)
        if not match:
            continue
        ssid = match.group(1).upper()
        base = {
            "source_path": relative_path,
            "size": len(data),
            "sha256": _sha256(data),
            "version": struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else None,
        }
        if shared_table is not None:
            try:
                # PROVISIONAL one_based; scripted convention is provenance-dependent
                # (legacy=one_based wire-proven, new=direct, edited=MIXED).
                parsed = parse_scripted_structure(data, shared_table, "one_based")
            except ValueError:
                parsed = None
            if parsed is not None:
                result[ssid] = {
                    **base,
                    "status": "structurally_parsed",
                    "layout": "shared_441_table_dictionary_timeline",
                    "shared_block_offset": parsed["shared_block_offset"],
                    "cues": parsed["cues"],
                    "timeline": parsed["timeline"],
                    "trailer_hex": parsed["trailer_hex"],
                    "unparsed_extra_size": parsed["extra_size"],
                }
                continue
        try:
            candidate = _select_fallback_candidate(data)
        except ValueError as error:
            result[ssid] = {
                **base,
                "status": "unsupported",
                "layout": "unclassified_v3",
                "unsupported_reason": str(error),
            }
            continue
        footer_offset = struct.unpack_from("<I", data, 8)[0] if len(data) >= 12 else 0
        result[ssid] = {
            **base,
            "status": "structurally_parsed_not_wire_validated",
            "layout": (
                "dictionary_timeline_then_addressed_footer"
                if footer_offset
                else "dictionary_timeline_no_shared_anchor"
            ),
            "cue_count_offset": candidate["cue_count_offset"],
            "cue_count": candidate["cue_count"],
            "timeline_count_offset": candidate["timeline_count_offset"],
            "timeline_count": candidate["timeline_count"],
            "timeline_summary": _timeline_summary(candidate["timeline"]),
            "trailer_hex": data[
                candidate["timeline_end_offset"] : candidate["timeline_end_offset"]
                + TRAILER_SIZE
            ].hex(),
            "footer_sha256": _sha256(data[footer_offset:]) if footer_offset else None,
            "footer_size": len(data) - footer_offset if footer_offset else 0,
            "semantic_limit": "fallback layout internals remain structural-only",
        }
    return result


def _path_changes(
    before_inventory: dict[str, Any],
    after_inventory: dict[str, Any],
    before_blobs: dict[str, bytes],
    after_blobs: dict[str, bytes],
) -> dict[str, Any]:
    before = {row["relative_path"]: row for row in before_inventory["files"]}
    after = {row["relative_path"]: row for row in after_inventory["files"]}
    before_paths = set(before)
    after_paths = set(after)
    added = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)
    changed = sorted(
        path
        for path in before_paths & after_paths
        if before[path]["sha256"] != after[path]["sha256"]
    )
    rename_candidates = []
    for old_path in removed:
        for new_path in added:
            if before[old_path]["sha256"] == after[new_path]["sha256"]:
                rename_candidates.append(
                    {
                        "old_path": old_path,
                        "new_path": new_path,
                        "sha256": before[old_path]["sha256"],
                        "identity_authority": "diagnostic content match only",
                    }
                )
    return {
        "added": [after[path] for path in added],
        "removed": [before[path] for path in removed],
        "changed": [
            {
                "relative_path": path,
                "file_class": before[path]["file_class"],
                "before_sha256": before[path]["sha256"],
                "after_sha256": after[path]["sha256"],
                "byte_changes": _aligned_diff_ranges(
                    before_blobs[path], after_blobs[path]
                ),
            }
            for path in changed
        ],
        "exact_content_rename_candidates": rename_candidates,
    }


def _autoloop_diff(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    top = _map_diff(
        {
            key: {
                name: value
                for name, value in row.items()
                if name not in {"events", "cues", "timeline"}
            }
            for key, row in before.items()
        },
        {
            key: {
                name: value
                for name, value in row.items()
                if name not in {"events", "cues", "timeline"}
            }
            for key, row in after.items()
        },
    )
    components = []
    for key in sorted(set(before) & set(after)):
        if before[key] == after[key]:
            continue
        if "events" not in before[key] or "events" not in after[key]:
            components.append(
                {
                    "source_path": key,
                    "status": "unknown",
                    "reason": (
                        "one or both autoloop layouts are unsupported by the strict parser"
                    ),
                }
            )
            continue
        components.append(
            {
                "source_path": key,
                "events": _component_diff(before[key]["events"], after[key]["events"]),
                "dictionary": _dictionary_component_diff(
                    before[key]["cues"], after[key]["cues"]
                ),
                "timeline": _timeline_component_diff(
                    before[key]["timeline"], after[key]["timeline"]
                ),
            }
        )
    return {**top, "component_changes": components}


def _scripted_diff(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    top = _map_diff(
        {key: {name: value for name, value in row.items() if name not in {"cues", "timeline"}}
         for key, row in before.items()},
        {key: {name: value for name, value in row.items() if name not in {"cues", "timeline"}}
         for key, row in after.items()},
    )
    components = []
    for key in sorted(set(before) & set(after)):
        if before[key] == after[key]:
            continue
        if "cues" not in before[key] or "cues" not in after[key]:
            components.append(
                {
                    "soundswitch_id": key,
                    "status": "unknown",
                    "reason": "changed fallback or unsupported layout lacks full semantic decode",
                }
            )
            continue
        components.append(
            {
                "soundswitch_id": key,
                "status": "confirmed",
                "dictionary": _dictionary_component_diff(
                    before[key]["cues"], after[key]["cues"]
                ),
                "timeline": _timeline_component_diff(
                    before[key]["timeline"], after[key]["timeline"]
                ),
            }
        )
    return {**top, "component_changes": components}


def _snapshot_consistency(
    catalogs: dict[str, dict[str, Any]],
    autoloops: dict[str, dict[str, Any]],
    scripted: dict[str, dict[str, Any]],
    track_map: dict[str, Any],
    venue: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    catalog_errors = [
        row for identity, row in catalogs.items() if identity.startswith("unsupported:")
    ]
    catalog_entries = [
        row for identity, row in catalogs.items() if not identity.startswith("unsupported:")
    ]
    catalog_file_numbers = {row["file_number"] for row in catalog_entries}
    actual_file_numbers = {row["file_number"] for row in autoloops.values()}
    venue_fixture_profiles = {
        row["fixture_profile_guid"]
        for row in venue.values()
        if row["fixture_profile_guid"] is not None
    }
    autoloop_fixture_profiles = {
        row["fixture"]["fixture_profile_guid_raw_hex"]
        for row in autoloops.values()
        if row.get("fixture", {}).get("status") == "parsed"
    }
    fixture_profiles_without_venue_cues = sorted(
        autoloop_fixture_profiles - venue_fixture_profiles
    )
    unresolved_positive_references = []
    missing_current_venue_cues = []

    def check_timeline(
        artifact_class: str,
        identity: str,
        row: dict[str, Any],
    ) -> None:
        if "cues" not in row or "timeline" not in row:
            return
        dictionary = {entry["cue_index"]: entry for entry in row["cues"]}
        for event in row["timeline"]:
            dictionary_index = event["resolved_dictionary_index"]
            if dictionary_index is None:
                continue
            cue = dictionary.get(dictionary_index)
            if cue is None:
                unresolved_positive_references.append(
                    {
                        "artifact_class": artifact_class,
                        "identity": identity,
                        "record_offset": event["offset"],
                        "raw_cue_reference": event["raw_cue_reference"],
                        "resolved_dictionary_index": dictionary_index,
                    }
                )
            elif cue["guid"] not in venue:
                missing_current_venue_cues.append(
                    {
                        "artifact_class": artifact_class,
                        "identity": identity,
                        "record_offset": event["offset"],
                        "cue_guid": cue["guid"],
                    }
                )

    for source_path, row in autoloops.items():
        check_timeline("autoloop", source_path, row)
    for ssid, row in scripted.items():
        check_timeline("scripted_track", ssid, row)

    scripted_ids = set(scripted)
    mapped_ids = set(track_map["by_soundswitch_id"])
    duplicate_track_map_ids = {
        ssid: rows
        for ssid, rows in track_map["by_soundswitch_id"].items()
        if len(rows) > 1
    }
    paths_to_ids: dict[str, list[str]] = defaultdict(list)
    for ssid, rows in track_map["by_soundswitch_id"].items():
        for row in rows:
            paths_to_ids[row["filepath"]].append(ssid)
    duplicate_track_map_paths = {
        path: ids for path, ids in sorted(paths_to_ids.items()) if len(ids) > 1
    }
    fatal = bool(
        catalog_errors
        or catalog_file_numbers - actual_file_numbers
        or actual_file_numbers - catalog_file_numbers
        or unresolved_positive_references
        or missing_current_venue_cues
        or fixture_profiles_without_venue_cues
    )
    return {
        "status": "failed_closed" if fatal else "consistent_with_known_partial_scope",
        "catalog_parse_errors": catalog_errors,
        "catalog_file_numbers": sorted(catalog_file_numbers),
        "actual_autoloop_file_numbers": sorted(actual_file_numbers),
        "catalog_entries_missing_autoloop_file": sorted(
            catalog_file_numbers - actual_file_numbers
        ),
        "uncataloged_autoloop_files": sorted(
            actual_file_numbers - catalog_file_numbers
        ),
        "unresolved_positive_references": unresolved_positive_references,
        "referenced_cues_missing_from_current_venue": missing_current_venue_cues,
        "venue_fixture_profiles": sorted(venue_fixture_profiles),
        "autoloop_fixture_profiles": sorted(autoloop_fixture_profiles),
        "fixture_profiles_without_venue_cues": fixture_profiles_without_venue_cues,
        "scripted_ids_missing_from_track_map": sorted(scripted_ids - mapped_ids),
        "track_map_ids_missing_current_script": sorted(mapped_ids - scripted_ids),
        "duplicate_track_map_ids": duplicate_track_map_ids,
        "duplicate_track_map_paths": duplicate_track_map_paths,
        "identity_scope_limit": (
            "TrackMap top-level graph and fallback scripted layouts remain partial; "
            "missing/orphan SSIDs are reported but are not fuzzy-matched"
        ),
    }


def _load_metadata(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    data = _read_stable(path)
    metadata = json.loads(data.decode("utf-8"))
    if not isinstance(metadata, dict):
        raise SnapshotError("experiment metadata must be a JSON object")
    missing = sorted(_REQUIRED_METADATA - set(metadata))
    if missing:
        raise SnapshotError(f"experiment metadata lacks required fields: {missing}")
    return metadata


def compare(before_root: Path, after_root: Path, metadata: dict[str, Any] | None) -> dict[str, Any]:
    before_inventory, before_blobs = _snapshot(before_root)
    after_inventory, after_blobs = _snapshot(after_root)
    before_manifest = _project_manifest(before_blobs)
    after_manifest = _project_manifest(after_blobs)
    path_changes = _path_changes(
        before_inventory, after_inventory, before_blobs, after_blobs
    )
    before_autoloops = _autoloops(before_blobs)
    after_autoloops = _autoloops(after_blobs)
    before_scripted = _scripted(before_blobs)
    after_scripted = _scripted(after_blobs)
    before_track_map = _track_map(before_blobs)
    after_track_map = _track_map(after_blobs)
    before_catalogs = _catalogs(before_blobs)
    after_catalogs = _catalogs(after_blobs)
    before_venue = _venue(before_blobs)
    after_venue = _venue(after_blobs)
    before_static_looks = _static_looks(before_blobs)
    after_static_looks = _static_looks(after_blobs)
    catalog_diff = _map_diff(
        _catalog_semantics(before_catalogs),
        _catalog_semantics(after_catalogs),
    )
    autoloop_diff = _autoloop_diff(before_autoloops, after_autoloops)
    scripted_diff = _scripted_diff(before_scripted, after_scripted)
    venue_diff = _map_diff(
        _venue_semantics(before_venue),
        _venue_semantics(after_venue),
    )
    static_look_diff = _map_diff(
        {
            identity: _without_fields(row, {"offset", "end_offset"})
            for identity, row in before_static_looks.items()
        },
        {
            identity: _without_fields(row, {"offset", "end_offset"})
            for identity, row in after_static_looks.items()
        },
    )
    track_map_diff = _map_diff(
        _track_map_semantics(before_track_map["by_soundswitch_id"]),
        _track_map_semantics(after_track_map["by_soundswitch_id"]),
    )
    semantic = {
        "autoloop_catalog_by_app_log_index": catalog_diff,
        "autoloop_files": autoloop_diff,
        "scripted_tracks_by_soundswitch_id": scripted_diff,
        "venue_cues_by_guid": venue_diff,
        "static_looks_by_slot_ordinal": static_look_diff,
        "track_map_by_soundswitch_id": track_map_diff,
        "track_map_parse_scope": {
            "before": {
                key: value
                for key, value in before_track_map.items()
                if key != "by_soundswitch_id"
            },
            "after": {
                key: value
                for key, value in after_track_map.items()
                if key != "by_soundswitch_id"
            },
        },
        "diagnostic_source_offset_changes": {
            "catalog_records": _single_record_offset_changes(
                before_catalogs,
                after_catalogs,
                offset_field="record_offset",
                ignored_fields={"record_offset"},
            ),
            "venue_cues": _single_record_offset_changes(
                before_venue,
                after_venue,
                offset_field="offset",
                ignored_fields={"offset"},
            ),
            "track_map_records": _track_map_offset_changes(
                before_track_map["by_soundswitch_id"],
                after_track_map["by_soundswitch_id"],
            ),
        },
    }
    unsupported = []
    for side, catalogs in (("before", before_catalogs), ("after", after_catalogs)):
        for identity, row in catalogs.items():
            if identity.startswith("unsupported:"):
                unsupported.append(
                    {
                        "side": side,
                        "source_path": row["source_path"],
                        "artifact_class": "autoloop_catalog",
                        "reason": row["unsupported_reason"],
                    }
                )
    for side, autoloops in (
        ("before", before_autoloops),
        ("after", after_autoloops),
    ):
        for source_path, row in autoloops.items():
            if row["status"] == "unsupported":
                unsupported.append(
                    {
                        "side": side,
                        "source_path": source_path,
                        "artifact_class": "autoloop",
                        "reason": row["unsupported_reason"],
                    }
                )
    for side, scripts in (("before", before_scripted), ("after", after_scripted)):
        for ssid, row in scripts.items():
            if row["status"] == "unsupported":
                unsupported.append(
                    {
                        "side": side,
                        "source_path": row["source_path"],
                        "artifact_class": "scripted_track",
                        "soundswitch_id": ssid,
                        "reason": row["unsupported_reason"],
                    }
                )
    opaque_classes = {
        "track_analysis_sidecar",
        "automation_preset",
        "recordable_control",
        "unclassified",
    }
    opaque_source_changes = []
    operation_names = {"added": "add", "removed": "remove", "changed": "replace"}
    for operation in ("added", "removed", "changed"):
        for row in path_changes[operation]:
            if row["file_class"] in opaque_classes:
                opaque_source_changes.append(
                    {
                        "operation": operation_names[operation],
                        "relative_path": row["relative_path"],
                        "file_class": row["file_class"],
                        "confidence": "unknown",
                    }
                )
    changed_paths = {row["relative_path"] for row in path_changes["changed"]}
    partial_semantic_sources = []
    if "SoundSwitchVenues.bin" in changed_paths:
        partial_semantic_sources.append(
            {
                "source_path": "SoundSwitchVenues.bin",
                "confidence": "unknown",
                "reason": (
                    "Venue parser covers attribute cue records only; fixture instances, "
                    "routing, positions, effects, and top-level objects remain partial"
                ),
                "parsed_semantic_change_found": (
                    _diff_has_changes(venue_diff) or _diff_has_changes(static_look_diff)
                ),
            }
        )
    if "SoundSwitchTrackMap.bin" in changed_paths:
        partial_semantic_sources.append(
            {
                "source_path": "SoundSwitchTrackMap.bin",
                "confidence": "unknown",
                "reason": "TrackMap parser covers repeated identity subrecords only",
                "parsed_semantic_change_found": _diff_has_changes(track_map_diff),
            }
        )
    for relative_path in sorted(changed_paths):
        file_class = _file_class(relative_path)
        if file_class == "autoloop":
            component = next(
                (
                    row
                    for row in autoloop_diff["component_changes"]
                    if row["source_path"] == relative_path
                ),
                None,
            )
            partial_semantic_sources.append(
                {
                    "source_path": relative_path,
                    "confidence": "unknown",
                    "reason": (
                        "autoloop structure is parsed, but shared-table, auxiliary, sentinel, "
                        "control-layer, and fixture-transform semantics remain incomplete"
                    ),
                    "parsed_semantic_change_found": component is not None,
                }
            )
        elif file_class == "scripted_track":
            ssid_match = _SCRIPT_FILE.match(Path(relative_path).name)
            ssid = ssid_match.group(1).upper() if ssid_match else None
            component = next(
                (
                    row
                    for row in scripted_diff["component_changes"]
                    if row["soundswitch_id"] == ssid
                ),
                None,
            )
            partial_semantic_sources.append(
                {
                    "source_path": relative_path,
                    "confidence": "unknown",
                    "reason": (
                        "scripted layout/render semantics are not fully wire-validated across "
                        "transport, control layers, and all observed layouts"
                    ),
                    "parsed_semantic_change_found": component is not None,
                }
            )
        elif file_class == "project_manifest":
            partial_semantic_sources.append(
                {
                    "source_path": relative_path,
                    "confidence": "unknown",
                    "reason": "manifest bytes changed; project-field semantics require review",
                    "parsed_semantic_change_found": False,
                }
            )
    artifact_operations = []
    artifact_operations.extend(
        _operations("autoloop_catalog_entry", catalog_diff, rename_field="display_name")
    )
    artifact_operations.extend(_operations("autoloop_file", autoloop_diff))
    artifact_operations.extend(_operations("scripted_track", scripted_diff))
    artifact_operations.extend(
        _operations("venue_cue", venue_diff, rename_field="name")
    )
    artifact_operations.extend(_static_look_operations(static_look_diff))
    artifact_operations.extend(_track_map_operations(track_map_diff))
    metadata_validation = {
        "status": "not_provided" if metadata is None else "matched",
        "declared_soundswitch_version": (
            metadata.get("soundswitch_version") if metadata is not None else None
        ),
        "after_manifest_version": after_manifest.get("version_text"),
    }
    if metadata is not None and (
        metadata.get("soundswitch_version") != after_manifest.get("version_text")
    ):
        metadata_validation["status"] = "failed_closed"
        metadata_validation["reason"] = (
            "declared SoundSwitch version does not match after-project manifest"
        )
    source_consistency = {
        "before": _snapshot_consistency(
            before_catalogs,
            before_autoloops,
            before_scripted,
            before_track_map,
            before_venue,
        ),
        "after": _snapshot_consistency(
            after_catalogs,
            after_autoloops,
            after_scripted,
            after_track_map,
            after_venue,
        ),
    }
    has_changes = any(
        path_changes[key] for key in ("added", "removed", "changed")
    )
    fail_closed = bool(
        unsupported
        or opaque_source_changes
        or partial_semantic_sources
        or any(
            row["status"] == "failed_closed" for row in source_consistency.values()
        )
        or before_manifest["status"] != "parsed"
        or after_manifest["status"] != "parsed"
        or metadata_validation["status"] == "failed_closed"
    )
    return {
        "schema_version": 1,
        "status": "partial_fail_closed" if fail_closed else "compared",
        "confidence_legend": {
            "confirmed": "directly reproduced from current bytes and strict parser output",
            "assumed": "plausible but not isolated",
            "unknown": "requires a controlled experiment or additional decoder",
        },
        "experiment": metadata,
        "before": before_inventory,
        "after": after_inventory,
        "project_manifest": {
            "before": before_manifest,
            "after": after_manifest,
            "changed": before_manifest != after_manifest,
        },
        "experiment_metadata_validation": metadata_validation,
        "has_changes": has_changes,
        "path_changes": path_changes,
        "semantic_changes": semantic,
        "artifact_operations": artifact_operations,
        "source_consistency": source_consistency,
        "unsupported_structures": unsupported,
        "opaque_source_changes": opaque_source_changes,
        "partial_semantic_source_changes": partial_semantic_sources,
        "identity_rules": {
            "autoloop": "catalog AppLog index and file_number; display path is not identity",
            "scripted_track": "normalized SSID; TrackMap path is a locator only",
            "venue_cue": "cue GUID; display name is not identity",
            "static_look": "observed Venue static-look slot ordinal; name is mutable",
            "content_hash": "integrity and diagnostic rename evidence only",
        },
        "scope_limit": (
            "read-only research comparison; fallback scripted layouts, fixture instance "
            "routing, TrackMap top-level fields, and opaque sidecars remain fail-closed"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("before_project", type=Path)
    parser.add_argument("after_project", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    try:
        report = compare(
            args.before_project.resolve(),
            args.after_project.resolve(),
            _load_metadata(args.metadata),
        )
    except (SnapshotError, ValueError, OSError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "failed_closed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2) from error
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
