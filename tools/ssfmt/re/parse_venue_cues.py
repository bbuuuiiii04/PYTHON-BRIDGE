#!/usr/bin/env python3
"""Read-only parser for the exact observed Venue attribute-cue records."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


CHANNEL_IDS = (82, 83, 84, 85, *range(256, 271))
CHANNEL_BY_ID = {channel_id: index + 1 for index, channel_id in enumerate(CHANNEL_IDS)}
KNOWN_FIXTURE_GROUPS = {0x493, 0x494, 0x496, 0x497}


def cue_at(data: bytes, name_offset: int) -> dict | None:
    if name_offset + 4 > len(data):
        return None
    name_length = struct.unpack_from("<I", data, name_offset)[0]
    if not 2 <= name_length <= 96:
        return None
    name_end = name_offset + 4 + 2 * name_length
    header_end = name_end + 60
    if header_end > len(data):
        return None
    try:
        decoded_name = data[name_offset + 4 : name_end].decode("utf-16le")
    except UnicodeDecodeError:
        return None
    if not decoded_name.endswith("\0"):
        return None
    name = decoded_name[:-1]
    if not name or not all(32 <= ord(character) < 127 for character in name):
        return None

    cue_guid = data[name_end + 4 : name_end + 20]
    unknown_u32, flag_a, flag_b = struct.unpack_from("<III", data, name_end + 20)
    fixture_profile_guid = data[name_end + 32 : name_end + 48]
    flag_c, flag_d, entry_count = struct.unpack_from("<III", data, name_end + 48)
    if (flag_a, flag_b, flag_c, flag_d) != (1, 1, 1, 1):
        return None
    if not 1 <= entry_count <= 1024:
        return None

    entries_offset = name_end + 60
    entries_end = entries_offset + 16 * entry_count
    if entries_end > len(data):
        return None
    entries = []
    groups: dict[str, dict[str, int]] = {}
    for entry_index in range(entry_count):
        offset = entries_offset + 16 * entry_index
        present, fixture_group, channel_id = struct.unpack_from("<III", data, offset)
        repeated_value = data[offset + 12 : offset + 16]
        if present != 1 or fixture_group not in KNOWN_FIXTURE_GROUPS:
            return None
        if channel_id not in CHANNEL_BY_ID or len(set(repeated_value)) != 1:
            return None
        channel = CHANNEL_BY_ID[channel_id]
        value = repeated_value[0]
        entries.append(
            {
                "offset": offset,
                "fixture_group": fixture_group,
                "channel_id": channel_id,
                "channel": channel,
                "value": value,
            }
        )
        groups.setdefault(hex(fixture_group), {})[str(channel)] = value

    return {
        "offset": name_offset,
        "name": name,
        "name_end_offset": name_end,
        "marker_hex": data[name_end : name_end + 4].hex(),
        "cue_guid": cue_guid.hex(),
        "unknown_u32": unknown_u32,
        "fixture_profile_guid": fixture_profile_guid.hex(),
        "entry_count": entry_count,
        "entries_offset": entries_offset,
        "entries_end_offset": entries_end,
        "entries": entries,
        "groups": groups,
    }


def parse_venue_cues(data: bytes) -> list[dict]:
    cues = []
    offset = 0
    while offset + 4 <= len(data):
        cue = cue_at(data, offset)
        if cue is None:
            offset += 1
            continue
        cues.append(cue)
        offset = cue["entries_end_offset"]
    return cues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("venue", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    data = args.venue.read_bytes()
    cues = parse_venue_cues(data)
    output = cues if args.full else [
        {key: value for key, value in cue.items() if key != "entries"} for cue in cues
    ]
    print(
        json.dumps(
            {
                "path": str(args.venue),
                "status": "partial",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "version": struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else None,
                "cue_count": len(cues),
                "first_cue_offset": cues[0]["offset"] if cues else None,
                "last_cue_end_offset": cues[-1]["entries_end_offset"] if cues else None,
                "unsupported_reason": (
                    "attribute cue records are decoded; venue fixture patch, positions, "
                    "categories, and remaining top-level objects are outside this parser"
                ),
                "cues": output,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
