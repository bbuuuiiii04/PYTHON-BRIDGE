#!/usr/bin/env python3
"""Classify all observed scripted SoundSwitch v3 container layouts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from analyze_scripted_ssfile import (
    parse_scripted_structure,
    shared_table_from_autoloop,
    timeline_record,
)
from analyze_ssfile_structure import MAGIC, TRAILER_SIZE


_SCRIPT_FILENAME = re.compile(r"^\{([0-9A-Fa-f-]{36})\}\.ssfile$")


def _u32le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _dictionary_timeline_candidates(data: bytes) -> list[dict[str, Any]]:
    candidates = []
    for cue_map_version_offset in range(max(0, len(data) - 32)):
        if _u32le(data, cue_map_version_offset) != 1:
            continue
        cue_count_offset = cue_map_version_offset + 4
        cue_count = _u32le(data, cue_count_offset)
        if not 1 <= cue_count <= 10000:
            continue
        entries_offset = cue_count_offset + 4
        entries_end = entries_offset + cue_count * 20
        if entries_end + 4 > len(data):
            continue
        cues = []
        indices = []
        for cue_index in range(cue_count):
            offset = entries_offset + cue_index * 20
            indices.append(_u32le(data, offset + 16))
            cues.append(
                {
                    "offset": offset,
                    "guid": data[offset : offset + 16].hex(),
                    "cue_index": _u32le(data, offset + 16),
                }
            )
        else:
            if len(indices) != len(set(indices)):
                continue
            timeline_count = _u32le(data, entries_end)
            timeline_offset = entries_end + 4
            timeline_end = timeline_offset + timeline_count * 16
            if not 1 <= timeline_count <= 10000 or timeline_end > len(data):
                continue
            timeline = []
            valid = True
            for record_index in range(timeline_count):
                try:
                    # Scripted playback resolves positive raw references by
                    # exact serialized key; generic structural parsers still
                    # retain historical candidates elsewhere.
                    record = timeline_record(data, timeline_offset + record_index * 16, "exact_key")
                except ValueError:
                    valid = False
                    break
                if record["field_a"] != 1 or record["field_b"] != 1:
                    valid = False
                    break
                resolved_index = record["resolved_dictionary_index"]
                if resolved_index is not None and resolved_index not in indices:
                    valid = False
                    break
                timeline.append(record)
            if valid:
                candidates.append(
                    {
                        "cue_map_version_offset": cue_map_version_offset,
                        "cue_count_offset": cue_count_offset,
                        "cue_count": cue_count,
                        "cues": cues,
                        "timeline_count_offset": entries_end,
                        "timeline_offset": timeline_offset,
                        "timeline_count": timeline_count,
                        "timeline_end_offset": timeline_end,
                        "timeline": timeline,
                    }
                )
    return candidates


def _select_fallback_candidate(data: bytes) -> dict[str, Any]:
    candidates = _dictionary_timeline_candidates(data)
    header_footer_offset = _u32le(data, 8)
    expected_end = (
        header_footer_offset - TRAILER_SIZE
        if header_footer_offset > 0
        else len(data) - TRAILER_SIZE
    )
    exact = [row for row in candidates if row["timeline_end_offset"] == expected_end]
    if len(exact) != 1:
        raise ValueError(
            f"expected one dictionary/timeline ending at {expected_end}, found {len(exact)} "
            f"among {len(candidates)} structural candidates"
        )
    return exact[0]


def _timeline_summary(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "negative_time_count": sum(row["elapsed"] < 0 for row in timeline),
        "ref_zero_count": sum(row["raw_cue_reference"] == 0 for row in timeline),
        "positive_reference_count": sum(row["raw_cue_reference"] > 0 for row in timeline),
        "raw_cue_references": sorted({row["raw_cue_reference"] for row in timeline}),
        "resolved_dictionary_indices": sorted(
            row["resolved_dictionary_index"]
            for row in timeline
            if row["resolved_dictionary_index"] is not None
        ),
        "elapsed_min": min((row["elapsed"] for row in timeline if row["elapsed"] >= 0), default=None),
        "elapsed_max": max((row["elapsed"] for row in timeline if row["elapsed"] >= 0), default=None),
    }


def _referenced_cue_guids(
    cues: list[dict[str, Any]], timeline: list[dict[str, Any]]
) -> list[str]:
    by_index = {row["cue_index"]: row["guid"] for row in cues}
    return sorted(
        {
            by_index[row["resolved_dictionary_index"]]
            for row in timeline
            if row["resolved_dictionary_index"] is not None
            and row["resolved_dictionary_index"] in by_index
        }
    )


def _base(path: Path, data: bytes) -> dict[str, Any]:
    match = _SCRIPT_FILENAME.match(path.name)
    return {
        "path": str(path),
        "filename": path.name,
        "soundswitch_id": match.group(1).upper() if match else None,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": _u32le(data, 4) if len(data) >= 8 else None,
        "header_footer_offset": _u32le(data, 8) if len(data) >= 12 else None,
        "header_footer_secondary_offset": _u32le(data, 12) if len(data) >= 16 else None,
        "layout_selector_offset_20": _u32le(data, 20) if len(data) >= 24 else None,
        "fixture_profile_guid_raw_hex": data[28:44].hex() if len(data) >= 44 else None,
    }


def analyze_file(path: Path, shared_table: bytes) -> dict[str, Any]:
    data = path.read_bytes()
    row = _base(path, data)
    if data[:4] != MAGIC:
        return {**row, "status": "unsupported", "unsupported_reason": "not a SoundSwitch container"}
    try:
        # Version-locked SoundSwitch 2.10.3 runtime playback rule.
        parsed = parse_scripted_structure(data, shared_table, "exact_key")
    except ValueError as shared_error:
        try:
            candidate = _select_fallback_candidate(data)
        except ValueError as fallback_error:
            return {
                **row,
                "status": "unsupported",
                "layout": "unclassified_v3",
                "shared_table_error": str(shared_error),
                "unsupported_reason": str(fallback_error),
            }
        timeline = candidate["timeline"]
        footer_offset = row["header_footer_offset"] or None
        trailer_offset = candidate["timeline_end_offset"]
        if footer_offset is not None and trailer_offset + TRAILER_SIZE != footer_offset:
            return {
                **row,
                "status": "unsupported",
                "unsupported_reason": "timeline does not meet header-addressed footer after 13-byte trailer",
            }
        layout = (
            "dictionary_timeline_then_addressed_footer"
            if footer_offset is not None
            else "dictionary_timeline_no_shared_anchor"
        )
        return {
            **row,
            "status": "structurally_parsed_not_wire_validated",
            "layout": layout,
            "shared_table_error": str(shared_error),
            "cue_count_offset": candidate["cue_count_offset"],
            "cue_count": candidate["cue_count"],
            "timeline_count_offset": candidate["timeline_count_offset"],
            "timeline_offset": candidate["timeline_offset"],
            "timeline_count": candidate["timeline_count"],
            "continuation_timeline_count": 0,
            "timeline_end_offset": candidate["timeline_end_offset"],
            "trailer_offset": trailer_offset,
            "trailer_hex": data[trailer_offset : trailer_offset + TRAILER_SIZE].hex(),
            "footer_offset": footer_offset,
            "footer_size": len(data) - footer_offset if footer_offset is not None else 0,
            "footer_hex": data[footer_offset:].hex() if footer_offset is not None else "",
            "reference_rule": "SoundSwitch scripted playback: positive raw resolves by exact serialized-key lookup; raw 0 is clear/control.",
            "reference_evidence": (
                "same packed 16-byte record grammar and bounded references as the wire-validated "
                "A5 layout; this layout itself has no representative wire capture"
            ),
            "referenced_cue_guids": _referenced_cue_guids(
                candidate["cues"], timeline
            ),
            **_timeline_summary(timeline),
        }
    timeline = parsed["timeline"]
    return {
        **row,
        "status": "structurally_parsed",
        "layout": "shared_441_table_dictionary_timeline",
        "shared_block_offset": parsed["shared_block_offset"],
        "shared_block_size": parsed["shared_block_size"],
        "cue_count_offset": parsed["cue_count_offset"],
        "cue_count": parsed["cue_count"],
        "timeline_count_offset": parsed["timeline_count_offset"],
        "timeline_count": parsed["timeline_count"],
        "declared_timeline_count": parsed["declared_timeline_count"],
        "continuation_timeline_count": parsed["continuation_timeline_count"],
        "timeline_end_offset": parsed["extra_offset"],
        "trailer_offset": parsed["trailer_offset"],
        "trailer_hex": parsed["trailer_hex"],
        "extra_size": parsed["extra_size"],
        "reference_rule": "SoundSwitch scripted playback: positive raw resolves by exact serialized-key lookup; raw 0 is clear/control",
        "reference_evidence": "live-Ghidra evidence packet; structural for other files",
        "referenced_cue_guids": _referenced_cue_guids(parsed["cues"], timeline),
        **_timeline_summary(timeline),
    }


def analyze(paths: list[Path], autoloop_reference: Path) -> dict[str, Any]:
    shared_table = shared_table_from_autoloop(autoloop_reference)
    files = [analyze_file(path, shared_table) for path in paths]
    signatures = Counter(
        (
            row.get("layout"),
            row.get("layout_selector_offset_20"),
            row.get("fixture_profile_guid_raw_hex"),
            bool(row.get("header_footer_offset")),
        )
        for row in files
    )
    return {
        "status": "partial",
        "file_count": len(files),
        "structurally_parsed_count": sum(row["status"] != "unsupported" for row in files),
        "wire_validated_layout_count": 1,
        "unsupported_file_count": sum(row["status"] == "unsupported" for row in files),
        "layout_counts": dict(sorted(Counter(row.get("layout", "unknown") for row in files).items())),
        "layout_signatures": [
            {
                "layout": signature[0],
                "layout_selector_offset_20": signature[1],
                "fixture_profile_guid_raw_hex": signature[2],
                "has_header_addressed_footer": signature[3],
                "file_count": count,
            }
            for signature, count in sorted(signatures.items(), key=lambda item: str(item[0]))
        ],
        "unsupported_reason": (
            "only A5 has representative wire validation; one demo layout remains structurally "
            "unclassified and transport semantics are not captured"
        ),
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--autoloop-reference", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.files, args.autoloop_reference), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
