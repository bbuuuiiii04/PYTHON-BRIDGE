#!/usr/bin/env python3
"""Build deterministic 42-autoloop and 45-scripted research coverage rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyze_scripted_layouts import analyze as analyze_scripted_layouts
from analyze_ssfile_structure import parse_autoloop_structure
from parse_autoloop_catalogs import parse_catalog
from parse_track_map import analyze as analyze_track_map
from parse_venue_cues import parse_venue_cues


def _capture_by_file(report: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if report is not None:
        for segment in report.get("segments", []):
            result[segment["ssfile"]].append(segment)
    return result


def _capture_summary(segments: list[dict[str, Any]]) -> dict[str, Any]:
    if not segments:
        return {
            "captured_segment_count": 0,
            "static_exact_frames": 0,
            "static_compared_frames": 0,
            "static_exact_frame_ratio": None,
            "transition_only_exact_frames": 0,
            "transition_only_compared_frames": 0,
            "transition_only_exact_frame_ratio": None,
            "maximum_transition_residual_ms": None,
            "mismatched_channels": [],
            "other_deck_change_segment_count": 0,
            "capture_status": "no_capture_evidence",
        }
    static_exact = sum(row["static_zero_initial_fit"]["exact_frames"] for row in segments)
    static_compared = sum(row["static_zero_initial_fit"]["compared_frames"] for row in segments)
    transition_exact = sum(row["transition_only_wire_initial_fit"]["exact_frames"] for row in segments)
    transition_compared = sum(row["transition_only_wire_initial_fit"]["compared_frames"] for row in segments)
    residuals = [
        row["static_zero_initial_fit"]["max_abs_transition_residual_ms"]
        for row in segments
        if row["static_zero_initial_fit"]["max_abs_transition_residual_ms"] is not None
    ]
    channels = sorted(
        {
            int(channel)
            for row in segments
            for channel in row["static_zero_initial_fit"]["mismatch_channels"]
        }
    )
    classifications = Counter(row["classification"] for row in segments)
    if classifications.get("source_decode_error"):
        status = "source_decode_error"
    elif static_exact == static_compared:
        status = "byte_exact_static_render"
    elif classifications.get("possible_other_deck_ownership_change"):
        status = "ownership_or_layer_unresolved"
    else:
        status = "layer_or_field_unresolved"
    return {
        "captured_segment_count": len(segments),
        "static_exact_frames": static_exact,
        "static_compared_frames": static_compared,
        "static_exact_frame_ratio": static_exact / static_compared if static_compared else None,
        "transition_only_exact_frames": transition_exact,
        "transition_only_compared_frames": transition_compared,
        "transition_only_exact_frame_ratio": (
            transition_exact / transition_compared if transition_compared else None
        ),
        "maximum_transition_residual_ms": max(residuals, default=None),
        "mismatched_channels": channels,
        "other_deck_change_segment_count": sum(bool(row["other_deck_changes"]) for row in segments),
        "segment_classification_counts": dict(sorted(classifications.items())),
        "capture_status": status,
    }


def autoloop_report(
    project_dir: Path,
    venue_path: Path,
    catalog_paths: list[Path],
    capture_report: dict[str, Any] | None,
) -> dict[str, Any]:
    catalog_entries = []
    catalogs = []
    for path in catalog_paths:
        data = path.read_bytes()
        parsed = parse_catalog(data)
        catalogs.append(
            {
                "path": str(path),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "version": parsed["version"],
                "layout": parsed["layout"],
                "entry_count": parsed["entry_count"],
                "category_index_table_offset": parsed["category_index_table_offset"],
                "unparsed_size": parsed["unparsed_size"],
            }
        )
        catalog_entries.extend(parsed["entries"])
    entries_by_file = {entry["file_number"]: entry for entry in catalog_entries}
    venue_data = venue_path.read_bytes()
    venue_guids = {cue["cue_guid"] for cue in parse_venue_cues(venue_data)}
    capture_by_file = _capture_by_file(capture_report)
    rows = []
    for file_number in sorted(entries_by_file):
        catalog = entries_by_file[file_number]
        path = project_dir / f"SSAutoLoop{file_number}.ssfile"
        data = path.read_bytes()
        parsed = parse_autoloop_structure(data)
        dictionary_by_index = {entry["cue_index"]: entry for entry in parsed["cues"]}
        referenced_indices = {
            row["resolved_dictionary_index"]
            for row in parsed["timeline"]
            if row["resolved_dictionary_index"] is not None
        }
        referenced_guids = {
            dictionary_by_index[index]["guid"]
            for index in referenced_indices
            if index in dictionary_by_index
        }
        dictionary_guids = {entry["guid"] for entry in parsed["cues"]}
        missing_referenced = sorted(referenced_guids - venue_guids)
        stale_unused = sorted((dictionary_guids - venue_guids) - referenced_guids)
        timeline = parsed["timeline"]
        capture = _capture_summary(capture_by_file.get(path.name, []))
        blocker = None
        if missing_referenced:
            blocker = "referenced cue GUID is absent from current Venue"
        elif capture["capture_status"] not in {"byte_exact_static_render", "no_capture_evidence"}:
            blocker = "captured output retains unresolved layer/control/ownership state"
        elif capture["capture_status"] == "no_capture_evidence":
            blocker = "no clean captured segment for byte comparison"
        rows.append(
            {
                "file": path.name,
                "path": str(path),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "version": parsed["version"],
                "app_log_index": catalog["app_log_index"],
                "file_number": file_number,
                "catalog_ordering": catalog["ordering"],
                "catalog_name": catalog["display_name"],
                "catalog_category": catalog["category"],
                "catalog_enabled": catalog["enabled"],
                "event_count_offset": parsed["event_count_offset"],
                "event_count": parsed["event_count"],
                "cue_count_offset": parsed["cue_count_offset"],
                "cue_count": parsed["cue_count"],
                "timeline_count_offset": parsed["timeline_count_offset"],
                "timeline_count": parsed["timeline_count"],
                "declared_timeline_count": parsed["declared_timeline_count"],
                "continuation_timeline_count": parsed["continuation_timeline_count"],
                "negative_record_count": sum(row["time"] < 0 for row in timeline),
                "ref_zero_count": sum(row["raw_cue_reference"] == 0 for row in timeline),
                "nonzero_auxiliary_values": sorted(
                    {row["auxiliary"] for row in parsed["events"] if row["auxiliary"] != 0}
                ),
                "referenced_missing_guids": missing_referenced,
                "unused_stale_guids": stale_unused,
                "trailer_offset": parsed["trailer_offset"],
                "trailer_hex": parsed["trailer_hex"],
                **capture,
                "status": (
                    "byte_exact_captured"
                    if capture["capture_status"] == "byte_exact_static_render" and not missing_referenced
                    else "structurally_parsed_blocked"
                ),
                "blocker": blocker,
            }
        )
    status_counts = Counter(row["status"] for row in rows)
    return {
        "status": "partial",
        "project_dir": str(project_dir),
        "venue": {
            "path": str(venue_path),
            "size": len(venue_data),
            "sha256": hashlib.sha256(venue_data).hexdigest(),
            "parsed_cue_count": len(venue_guids),
        },
        "catalogs": catalogs,
        "file_count": len(rows),
        "structurally_parsed_count": len(rows),
        "byte_exact_captured_file_count": sum(row["status"] == "byte_exact_captured" for row in rows),
        "captured_file_count": sum(row["captured_segment_count"] > 0 for row in rows),
        "uncaptured_file_count": sum(row["captured_segment_count"] == 0 for row in rows),
        "status_counts": dict(sorted(status_counts.items())),
        "unsupported_reason": (
            "control/effect and deck-ownership semantics remain unresolved for captured residuals; "
            "uncaptured files have no byte-exact wire evidence"
        ),
        "files": rows,
    }


def scripted_report(
    project_dir: Path,
    autoloop_reference: Path,
    track_map_path: Path,
    validation: dict[str, Any] | None,
) -> dict[str, Any]:
    paths = sorted(project_dir.glob("{*.ssfile"))
    layouts = analyze_scripted_layouts(paths, autoloop_reference)
    track_map = analyze_track_map(track_map_path, project_dir, False)
    mappings_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in track_map["mappings"]:
        mappings_by_id[mapping["soundswitch_id"]].append(mapping)
    validated_id = None
    if validation:
        name = Path(validation["scripted_file"]).name
        validated_id = name[1:-8].upper() if name.startswith("{") and name.endswith("}.ssfile") else None
    rows = []
    for source in layouts["files"]:
        row = dict(source)
        ssid = row["soundswitch_id"]
        mappings = mappings_by_id.get(ssid, [])
        row["track_map_mapping_count"] = len(mappings)
        row["track_map_titles"] = sorted({item["title"] for item in mappings if item["title"]})
        row["track_map_filepaths"] = sorted({item["filepath"] for item in mappings})
        row["track_map_existing_filepath_count"] = sum(item["filepath_exists"] for item in mappings)
        if ssid == validated_id and validation is not None:
            row["wire_validation"] = {
                key: validation[key]
                for key in (
                    "fit_mode",
                    "checked_event_count",
                    "exact_event_frames",
                    "positive_reference_event_count",
                    "exact_positive_reference_event_frames",
                    "ref_zero_event_count",
                    "exact_ref_zero_event_frames",
                    "rms_transition_residual_ms",
                    "max_abs_transition_residual_ms",
                )
            }
            row["coverage_status"] = "byte_exact_captured"
            row["blocker"] = None
        elif row["status"] == "unsupported":
            row["wire_validation"] = None
            row["coverage_status"] = "unsupported"
            row["blocker"] = row["unsupported_reason"]
        else:
            row["wire_validation"] = None
            row["coverage_status"] = "structurally_parsed_not_wire_validated"
            row["blocker"] = "no representative wire capture for this file/layout"
        rows.append(row)
    return {
        "status": "partial",
        "file_count": len(rows),
        "structurally_parsed_count": sum(row["status"] != "unsupported" for row in rows),
        "byte_exact_captured_file_count": sum(row["coverage_status"] == "byte_exact_captured" for row in rows),
        "unsupported_file_count": sum(row["coverage_status"] == "unsupported" for row in rows),
        "layout_counts": layouts["layout_counts"],
        "track_map_mapped_script_count": sum(row["track_map_mapping_count"] > 0 for row in rows),
        "track_map_unmapped_script_count": sum(row["track_map_mapping_count"] == 0 for row in rows),
        "unsupported_reason": (
            "44 files are structurally parsed but only A5 has byte-exact wire validation; one "
            "demo layout and all transport semantics remain unsupported"
        ),
        "files": rows,
    }


def _load(path: Path | None) -> dict[str, Any] | None:
    return json.loads(path.read_text()) if path is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--venue", required=True, type=Path)
    parser.add_argument("--catalog", action="append", required=True, type=Path)
    parser.add_argument("--autoloop-capture-report", type=Path)
    parser.add_argument("--autoloop-reference", required=True, type=Path)
    parser.add_argument("--track-map", required=True, type=Path)
    parser.add_argument("--scripted-validation", type=Path)
    args = parser.parse_args()
    output = {
        "autoloops": autoloop_report(
            args.project_dir,
            args.venue,
            args.catalog,
            _load(args.autoloop_capture_report),
        ),
        "scripted": scripted_report(
            args.project_dir,
            args.autoloop_reference,
            args.track_map,
            _load(args.scripted_validation),
        ),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
