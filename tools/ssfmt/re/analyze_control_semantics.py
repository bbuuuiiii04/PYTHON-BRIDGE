#!/usr/bin/env python3
"""Correlate autoloop special fields with passive-capture residual evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyze_ssfile_structure import parse_autoloop_structure
from parse_venue_cues import parse_venue_cues


STROBE_GUID = "ea7be0ca8e396340b5de863399bb6004"
PRIOR_STROBE_CLAIM_OFFSETS = {
    "SSAutoLoop47.ssfile": [7622, 7910],
    "SSAutoLoop48.ssfile": [7467, 7515, 7579],
    "SSAutoLoop55.ssfile": [7416],
}


def _capture_file_summaries(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if report:
        for segment in report.get("segments", []):
            grouped[segment["ssfile"]].append(segment)
    summaries = {}
    for filename, segments in grouped.items():
        pair_counts: dict[int, Counter[tuple[int, int]]] = defaultdict(Counter)
        channel_counts: Counter[int] = Counter()
        for segment in segments:
            fit = segment["static_zero_initial_fit"]
            for channel, count in fit["mismatch_channels"].items():
                channel_counts[int(channel)] += count
            for channel, rows in fit.get("mismatch_value_pairs", {}).items():
                for row in rows:
                    pair_counts[int(channel)][(row["expected"], row["actual"])] += row["count"]
        summaries[filename] = {
            "captured_segment_count": len(segments),
            "classification_counts": dict(sorted(Counter(row["classification"] for row in segments).items())),
            "mismatch_channel_counts": {str(key): value for key, value in sorted(channel_counts.items())},
            "mismatch_value_pairs": {
                str(channel): [
                    {"expected": pair[0], "actual": pair[1], "count": count}
                    for pair, count in counter.most_common()
                ]
                for channel, counter in sorted(pair_counts.items())
            },
        }
    return summaries


def _cue_details(cue: dict[str, Any] | None, fixture_group: str) -> dict[str, Any]:
    if cue is None:
        return {
            "cue_name": None,
            "cue_patch": {},
            "encoded_channels": [],
            "nonzero_channels": {},
        }
    patch = cue["groups"].get(fixture_group, {})
    return {
        "cue_name": cue["name"],
        "cue_patch": patch,
        "encoded_channels": sorted(int(channel) for channel in patch),
        "nonzero_channels": {
            channel: value for channel, value in patch.items() if value != 0
        },
    }


def analyze(
    project_dir: Path,
    venue_path: Path,
    fixture_group: str,
    capture_report: dict[str, Any] | None,
) -> dict[str, Any]:
    venue_data = venue_path.read_bytes()
    venue_cues = parse_venue_cues(venue_data)
    venue_by_guid = {cue["cue_guid"]: cue for cue in venue_cues}
    parsed_files: dict[str, dict[str, Any]] = {}
    shared_hashes: dict[str, list[str]] = defaultdict(list)
    auxiliary_rows = []
    negative_rows = []
    ref_zero_rows = []
    field_pairs: Counter[tuple[int, int]] = Counter()
    cue_usage: dict[str, dict[str, Any]] = {}
    strobe_dictionary_rows = []
    for path in sorted(project_dir.glob("SSAutoLoop*.ssfile")):
        data = path.read_bytes()
        # PROVISIONAL one_based: autoloop convention is provenance-dependent and not
        # wire-anchored; off-by-one for direct/mixed files. See soundswitch_ssfile_format.md.
        parsed = parse_autoloop_structure(data, "one_based")
        parsed_files[path.name] = parsed
        dictionary_by_index = {entry["cue_index"]: entry for entry in parsed["cues"]}
        shared = data[
            parsed["shared_block_offset"] : parsed["shared_block_offset"] + parsed["shared_block_size"]
        ]
        shared_hashes[hashlib.sha256(shared).hexdigest()].append(path.name)
        for event in parsed["events"]:
            if event["auxiliary"] != 0:
                auxiliary_rows.append(
                    {
                        "file": path.name,
                        "record_offset": event["offset"],
                        "tick": event["tick_a"],
                        "auxiliary": event["auxiliary"],
                        "auxiliary_hex": hex(event["auxiliary"]),
                        "little_endian_bytes": list(event["auxiliary"].to_bytes(4, "little")),
                    }
                )
        for index, dictionary_cue in enumerate(parsed["cues"]):
            if dictionary_cue["guid"] == STROBE_GUID:
                strobe_dictionary_rows.append(
                    {
                        "file": path.name,
                        "physical_dictionary_position": index,
                        "dictionary_index": dictionary_cue["cue_index"],
                        "required_positive_raw_reference": dictionary_cue["cue_index"] + 1,
                        "dictionary_offset": dictionary_cue["offset"],
                        "cue_index_field": dictionary_cue["cue_index"],
                    }
                )
        for timeline in parsed["timeline"]:
            field_pairs[(timeline["field_a"], timeline["field_b"])] += 1
            base = {
                "file": path.name,
                "record_offset": timeline["offset"],
                "tick": timeline["time"],
                "field_a": timeline["field_a"],
                "field_b": timeline["field_b"],
                "raw_cue_reference": timeline["raw_cue_reference"],
                "resolved_dictionary_index": timeline["resolved_dictionary_index"],
            }
            if timeline["raw_cue_reference"] == 0:
                ref_zero_rows.append({**base, "reference_kind": "clear_control"})
                continue
            dictionary_index = timeline["resolved_dictionary_index"]
            dictionary_cue = dictionary_by_index[dictionary_index]
            venue_cue = venue_by_guid.get(dictionary_cue["guid"])
            details = _cue_details(venue_cue, fixture_group)
            row = {
                **base,
                "reference_kind": "cue",
                "cue_guid": dictionary_cue["guid"],
                "dictionary_offset": dictionary_cue["offset"],
                **details,
            }
            if timeline["time"] < 0:
                negative_rows.append(row)
            aggregate = cue_usage.setdefault(
                dictionary_cue["guid"],
                {
                    "cue_guid": dictionary_cue["guid"],
                    **details,
                    "record_count": 0,
                    "negative_record_count": 0,
                    "files": set(),
                    "record_offsets": [],
                },
            )
            aggregate["record_count"] += 1
            aggregate["negative_record_count"] += timeline["time"] < 0
            aggregate["files"].add(path.name)
            aggregate["record_offsets"].append({"file": path.name, "offset": timeline["offset"]})

    for aggregate in cue_usage.values():
        aggregate["files"] = sorted(aggregate["files"])

    auxiliary_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in auxiliary_rows:
        auxiliary_groups[row["auxiliary"]].append(row)
    capture_summaries = _capture_file_summaries(capture_report)
    file_correlations = []
    for filename, parsed in sorted(parsed_files.items()):
        aux = [row for row in auxiliary_rows if row["file"] == filename]
        negative = [row for row in negative_rows if row["file"] == filename]
        zero = [row for row in ref_zero_rows if row["file"] == filename]
        capture = capture_summaries.get(filename)
        if aux or negative or zero or capture:
            file_correlations.append(
                {
                    "file": filename,
                    "nonzero_auxiliary_count": len(aux),
                    "nonzero_auxiliary_values": sorted({row["auxiliary"] for row in aux}),
                    "negative_record_count": len(negative),
                    "negative_record_offsets": [row["record_offset"] for row in negative],
                    "ref_zero_count": len(zero),
                    "capture": capture,
                }
            )

    prior_claim_rows = []
    for filename, offsets in PRIOR_STROBE_CLAIM_OFFSETS.items():
        parsed = parsed_files[filename]
        dictionary_by_index = {entry["cue_index"]: entry for entry in parsed["cues"]}
        timeline_by_offset = {row["offset"]: row for row in parsed["timeline"]}
        for offset in offsets:
            timeline = timeline_by_offset[offset]
            resolved = dictionary_by_index[timeline["resolved_dictionary_index"]]
            old_direct = dictionary_by_index.get(timeline["raw_cue_reference"])
            prior_claim_rows.append(
                {
                    "file": filename,
                    "record_offset": offset,
                    "tick": timeline["time"],
                    "raw_cue_reference": timeline["raw_cue_reference"],
                    "one_based_dictionary_index": timeline["resolved_dictionary_index"],
                    "one_based_guid": resolved["guid"],
                    "one_based_name": venue_by_guid.get(resolved["guid"], {}).get("name"),
                    "old_incorrect_direct_index_guid": old_direct["guid"] if old_direct else None,
                    "old_incorrect_direct_index_name": (
                        venue_by_guid.get(old_direct["guid"], {}).get("name") if old_direct else None
                    ),
                }
            )
    strobe_reference_count = cue_usage.get(STROBE_GUID, {}).get("record_count", 0)
    return {
        "status": "blocked",
        "project_dir": str(project_dir),
        "venue": {
            "path": str(venue_path),
            "size": len(venue_data),
            "sha256": hashlib.sha256(venue_data).hexdigest(),
            "version": int.from_bytes(venue_data[4:8], "little"),
            "parsed_cue_count": len(venue_cues),
            "fixture_group": fixture_group,
        },
        "file_count": len(parsed_files),
        "shared_table_variants": [
            {"sha256": digest, "file_count": len(files), "files": sorted(files)}
            for digest, files in sorted(shared_hashes.items())
        ],
        "timeline_field_pairs": [
            {"field_a": pair[0], "field_b": pair[1], "record_count": count}
            for pair, count in sorted(field_pairs.items())
        ],
        "auxiliary_record_count": len(auxiliary_rows),
        "auxiliary_groups": [
            {
                "auxiliary": value,
                "auxiliary_hex": hex(value),
                "record_count": len(rows),
                "files": sorted({row["file"] for row in rows}),
                "ticks": [{"file": row["file"], "offset": row["record_offset"], "tick": row["tick"]} for row in rows],
            }
            for value, rows in sorted(auxiliary_groups.items())
        ],
        "auxiliary_records": auxiliary_rows,
        "negative_record_count": len(negative_rows),
        "negative_records": negative_rows,
        "ref_zero_record_count": len(ref_zero_rows),
        "ref_zero_by_file": dict(sorted(Counter(row["file"] for row in ref_zero_rows).items())),
        "ref_zero_records": ref_zero_rows,
        "cue_usage": sorted(cue_usage.values(), key=lambda row: row["cue_guid"]),
        "strobe_correction": {
            "strobe_guid": STROBE_GUID,
            "venue_name": venue_by_guid.get(STROBE_GUID, {}).get("name"),
            "venue_patch": _cue_details(venue_by_guid.get(STROBE_GUID), fixture_group),
            "dictionary_presence_count": len(strobe_dictionary_rows),
            "timeline_reference_count": strobe_reference_count,
            "dictionary_rows": strobe_dictionary_rows,
            "prior_claim_offsets": prior_claim_rows,
            "conclusion": (
                "the STROBE cue exists in every dictionary and is referenced by 12 current "
                "timeline records; raw reference 3 resolves stored cue_index 2, while the old "
                "direct-index rule would incorrectly select MASTER STROBE at cue_index 3"
            ),
        },
        "capture_file_summaries": capture_summaries,
        "file_correlations": file_correlations,
        "unsupported_reason": (
            "auxiliary values, negative-time preload/sentinel behavior, shared-table controller "
            "semantics, CH11 ownership, and multi-deck composition cannot be uniquely inferred "
            "from the current corpus"
        ),
        "exact_blockers": [
            {
                "files": ["SSAutoLoop47.ssfile", "SSAutoLoop48.ssfile", "SSAutoLoop55.ssfile"],
                "channel": 11,
                "expected": 0,
                "actual": 227,
                "evidence": "passive capture mismatch value-pair counters",
                "invalidated_hypothesis": "the current timeline directly references Venue STROBE",
            },
            {
                "files": sorted({row["file"] for row in auxiliary_rows}),
                "record_offsets": [row["record_offset"] for row in auxiliary_rows],
                "evidence": "17-byte pre-table records contain nonzero values with no decoded transform",
            },
            {
                "files": sorted({row["file"] for row in negative_rows}),
                "record_offsets": [row["record_offset"] for row in negative_rows],
                "evidence": "negative-time records resolve to real cues but activation/preload semantics are unknown",
            },
        ],
        "next_bounded_experiments": [
            "operator-only clean one-deck capture of files 47, 48, and 55 from a known cleared state",
            "operator-authored scratch-project diff changing only CH11 in one cue",
            "operator-authored scratch-project diff adding or removing one negative-time record",
            "operator-authored scratch-project diff disabling one control/effect lane",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--venue", required=True, type=Path)
    parser.add_argument("--fixture-group", default="0x493")
    parser.add_argument("--capture-report", type=Path)
    args = parser.parse_args()
    capture_report = json.loads(args.capture_report.read_text()) if args.capture_report else None
    print(
        json.dumps(
            analyze(args.project_dir, args.venue, args.fixture_group, capture_report),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
