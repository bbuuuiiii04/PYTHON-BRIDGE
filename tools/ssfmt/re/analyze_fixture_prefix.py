#!/usr/bin/env python3
"""Decode the observed six-group fixture prefix in current autoloop files."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from parse_venue_cues import parse_venue_cues


MAGIC = b"\xaa\xaa\x09\x55"
GROUP_COUNT_OFFSET = 48
GROUPS_OFFSET = 52
GROUP_FIXED_PREFIX_SIZE = 72
POSITION_REFERENCE_SIZE = 20
GROUP_FIXED_SUFFIX_SIZE = 44


class ParseError(ValueError):
    """The file does not use the byte-verified six-group prefix layout."""


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ParseError(f"u32 outside file at offset {offset}")
    return struct.unpack_from("<I", data, offset)[0]


def _qstrings(data: bytes) -> list[dict[str, Any]]:
    strings = []
    for offset in range(max(0, len(data) - 7)):
        units = _u32(data, offset)
        if not 2 <= units <= 100:
            continue
        end = offset + 4 + units * 2
        if end > len(data):
            continue
        try:
            value = data[offset + 4 : end].decode("utf-16le")
        except UnicodeDecodeError:
            continue
        if not value.endswith("\0") or "\0" in value[:-1]:
            continue
        value = value[:-1]
        if not value or any(character not in "\r\n\t" and ord(character) < 32 for character in value):
            continue
        strings.append({"offset": offset, "data_offset": offset + 4, "end_offset": end, "value": value})
    return strings


def parse_fixture_prefix(data: bytes) -> dict[str, Any]:
    if data[:4] != MAGIC:
        raise ParseError("not a SoundSwitch container")
    if len(data) < GROUPS_OFFSET:
        raise ParseError("file is shorter than the observed fixture header")
    group_count = _u32(data, GROUP_COUNT_OFFSET)
    if group_count != 6:
        raise ParseError(
            f"group count/layout discriminator at offset 48 is {group_count}, not observed value 6"
        )
    offset = GROUPS_OFFSET
    groups = []
    for group_index in range(group_count):
        start = offset
        position_count = _u32(data, start + 68)
        if position_count != 12:
            raise ParseError(
                f"group {group_index} position count at offset {start + 68} is "
                f"{position_count}, not observed value 12"
            )
        positions = []
        offset = start + GROUP_FIXED_PREFIX_SIZE
        for position_index in range(position_count):
            positions.append(
                {
                    "record_offset": offset,
                    "position_reference_raw_hex": data[offset : offset + 16].hex(),
                    "slot": _u32(data, offset + 16),
                    "slot_offset": offset + 16,
                }
            )
            offset += POSITION_REFERENCE_SIZE
        suffix_offset = offset
        offset += GROUP_FIXED_SUFFIX_SIZE
        group_id = _u32(data, start)
        groups.append(
            {
                "group_index": group_index,
                "record_offset": start,
                "record_end_offset": offset,
                "record_size": offset - start,
                "group_id": group_id,
                "group_id_hex": hex(group_id),
                "parent_or_owner_reference": _u32(data, start + 40),
                "parent_or_owner_reference_offset": start + 40,
                "position_count": position_count,
                "position_count_offset": start + 68,
                "positions": positions,
                "fixed_prefix_hex": data[start : start + GROUP_FIXED_PREFIX_SIZE].hex(),
                "fixed_suffix_offset": suffix_offset,
                "fixed_suffix_hex": data[suffix_offset:offset].hex(),
            }
        )
    expected_ids = list(range(0x492, 0x498))
    actual_ids = [group["group_id"] for group in groups]
    if actual_ids != expected_ids:
        raise ParseError(f"unexpected group ID sequence {actual_ids!r}")
    return {
        "size": len(data),
        "version": _u32(data, 4),
        "fixture_profile_guid_raw_hex": data[28:44].hex(),
        "fixture_profile_guid_offset": 28,
        "group_count": group_count,
        "group_count_offset": GROUP_COUNT_OFFSET,
        "groups_offset": GROUPS_OFFSET,
        "groups_end_offset": offset,
        "groups_sha256": hashlib.sha256(data[GROUPS_OFFSET:offset]).hexdigest(),
        "groups": groups,
    }


def _venue_context(venue_path: Path, parsed: dict[str, Any]) -> dict[str, Any]:
    data = venue_path.read_bytes()
    strings = _qstrings(data)
    cues = parse_venue_cues(data)
    unique_positions = {
        position["position_reference_raw_hex"]
        for group in parsed["groups"]
        for position in group["positions"]
    }
    position_definitions = []
    for raw_hex in sorted(unique_positions):
        raw = bytes.fromhex(raw_hex)
        hits = []
        search_offset = 0
        while True:
            hit = data.find(raw, search_offset)
            if hit < 0:
                break
            hits.append(hit)
            search_offset = hit + 1
        definition_offset = hits[0] if hits else None
        name = None
        name_offset = None
        if definition_offset is not None:
            preceding = [row for row in strings if row["end_offset"] <= definition_offset]
            if preceding:
                candidate = max(preceding, key=lambda row: row["end_offset"])
                if definition_offset - candidate["end_offset"] <= 16:
                    name = candidate["value"]
                    name_offset = candidate["offset"]
        position_definitions.append(
            {
                "position_reference_raw_hex": raw_hex,
                "venue_occurrence_count": len(hits),
                "venue_first_offset": definition_offset,
                "venue_name": name,
                "venue_name_offset": name_offset,
            }
        )
    fixture_names = [
        {"name": row["value"], "name_length_offset": row["offset"], "name_offset": row["data_offset"]}
        for row in strings
        if row["value"].startswith("Fixture ") and row["value"][8:].isdigit()
    ]
    group_combinations = Counter(
        tuple(sorted(int(group, 16) for group in cue["groups"])) for cue in cues
    )
    return {
        "path": str(venue_path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": _u32(data, 4),
        "fixture_profile_guid_raw_hex_at_offset_28": data[28:44].hex(),
        "profile_matches_file_prefix": data[28:44].hex() == parsed["fixture_profile_guid_raw_hex"],
        "parsed_attribute_cue_count": len(cues),
        "attribute_cue_profile_counts": dict(sorted(Counter(cue["fixture_profile_guid"] for cue in cues).items())),
        "attribute_cue_group_combinations": [
            {"group_ids": list(groups), "cue_count": count}
            for groups, count in sorted(group_combinations.items())
        ],
        "position_definitions": position_definitions,
        "fixture_instance_name_offsets": fixture_names,
        "fixture_patch_status": "unsupported",
        "fixture_patch_unsupported_reason": (
            "four fixture-instance names are located, but the surrounding binary fields have "
            "not established universe, base address, or mirror routing without a controlled diff"
        ),
    }


def analyze(paths: list[Path], venue: Path | None) -> dict[str, Any]:
    files = []
    parsed_for_context = None
    for path in paths:
        data = path.read_bytes()
        try:
            parsed = parse_fixture_prefix(data)
            if parsed_for_context is None:
                parsed_for_context = parsed
            files.append(
                {
                    "path": str(path),
                    "status": "parsed",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    **parsed,
                }
            )
        except ParseError as exc:
            files.append(
                {
                    "path": str(path),
                    "status": "unsupported",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "version": _u32(data, 4) if len(data) >= 8 else None,
                    "unsupported_reason": str(exc),
                }
            )
    parsed_files = [row for row in files if row["status"] == "parsed"]
    output: dict[str, Any] = {
        "status": "partial",
        "file_count": len(files),
        "parsed_file_count": len(parsed_files),
        "unsupported_file_count": len(files) - len(parsed_files),
        "distinct_group_block_hashes": sorted({row["groups_sha256"] for row in parsed_files}),
        "unsupported_reason": (
            "the six-group topology and position references are decoded; universe/address "
            "ownership and the remaining unnamed group fields are not"
        ),
        "files": files,
    }
    if venue is not None and parsed_for_context is not None:
        output["venue_context"] = _venue_context(venue, parsed_for_context)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--venue", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.files, args.venue), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
