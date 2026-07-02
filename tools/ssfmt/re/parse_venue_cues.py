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


def parse_fixture_profile_channels(data: bytes) -> list[dict]:
    """Decode the first current-profile channel-definition set.

    The observed Venue embeds a complete 19-channel RAVE fixture profile before
    the cue catalog. Each definition begins with version 2, a channel ID, a
    present flag, and a UTF-16LE name. A second mode-specific subset follows;
    selecting the earliest valid definition for every known channel ID retains
    the complete primary profile without conflating the subset.
    """
    by_id: dict[int, dict] = {}
    scan_end = min(len(data), 8192)
    for offset in range(0, max(0, scan_end - 16)):
        version, channel_id, present, name_length = struct.unpack_from(
            "<IIII", data, offset
        )
        if (
            version != 2
            or channel_id not in CHANNEL_BY_ID
            or present != 1
            or not 2 <= name_length <= 64
            or channel_id in by_id
        ):
            continue
        name_offset = offset + 16
        name_end = name_offset + name_length * 2
        if name_end > scan_end:
            continue
        try:
            decoded = data[name_offset:name_end].decode("utf-16le")
        except UnicodeDecodeError:
            continue
        if not decoded.endswith("\0") or "\0" in decoded[:-1]:
            continue
        name = decoded[:-1]
        if not name or not all(32 <= ord(character) < 127 for character in name):
            continue
        by_id[channel_id] = {
            "offset": offset,
            "record_version": version,
            "channel_id": channel_id,
            "dmx_channel": CHANNEL_BY_ID[channel_id],
            "name": name,
            "name_offset": name_offset,
            "name_end_offset": name_end,
        }
    return [by_id[channel_id] for channel_id in CHANNEL_IDS if channel_id in by_id]


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
    if not 0 <= entry_count <= 1024:
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
                "raw_hex": data[offset : offset + 16].hex(),
                "unknown_u32_0x00": present,
                "fixture_group": fixture_group,
                "channel_id": channel_id,
                "channel": channel,
                "value": value,
                "repeated_value_raw_hex": repeated_value.hex(),
            }
        )
        groups.setdefault(hex(fixture_group), {})[str(channel)] = value

    return {
        "record_kind": "fixture_payload",
        "offset": name_offset,
        "name": name,
        "name_end_offset": name_end,
        "marker_hex": data[name_end : name_end + 4].hex(),
        "header_offset": name_end,
        "header_end_offset": header_end,
        "header_raw_hex": data[name_end:header_end].hex(),
        "header_fields": {
            **{
                f"unknown_u8_0x{relative:02x}": {
                    "offset": name_end + relative,
                    "value": data[name_end + relative],
                }
                for relative in range(4)
            },
            "unknown_u32_0x14": {"offset": name_end + 20, "value": unknown_u32},
            "unknown_u32_0x18": {"offset": name_end + 24, "value": flag_a},
            "unknown_u32_0x1c": {"offset": name_end + 28, "value": flag_b},
            "unknown_u32_0x30": {"offset": name_end + 48, "value": flag_c},
            "unknown_u32_0x34": {"offset": name_end + 52, "value": flag_d},
            "entry_count_u32_0x38": {
                "offset": name_end + 56,
                "value": entry_count,
            },
        },
        "cue_guid": cue_guid.hex(),
        "unknown_u32": unknown_u32,
        "fixture_profile_guid": fixture_profile_guid.hex(),
        "entry_count": entry_count,
        "entries_offset": entries_offset,
        "entries_end_offset": entries_end,
        "entries": entries,
        "groups": groups,
    }


def minimal_tail_cue_at(data: bytes, name_offset: int) -> dict | None:
    """Parse the default/empty cue record observed immediately before the cue index."""
    if name_offset + 4 > len(data):
        return None
    name_length = struct.unpack_from("<I", data, name_offset)[0]
    if not 2 <= name_length <= 96:
        return None
    name_end = name_offset + 4 + 2 * name_length
    record_end = name_end + 28
    if record_end > len(data):
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

    marker = data[name_end : name_end + 4]
    cue_guid = data[name_end + 4 : name_end + 20]
    if data[name_end + 20 : name_end + 24] != b"\xff\xff\xff\xff":
        return None
    catalog_count = struct.unpack_from("<I", data, name_end + 24)[0]
    # The controlled Attribute Cue catalog contained 233+ identities. A
    # structurally similar 12-position fixture list exists earlier in Venue;
    # exclude that different object class rather than mislabeling it as a cue.
    if not 64 <= catalog_count <= 1024:
        return None
    catalog_end = record_end + 4 * catalog_count
    if catalog_end > len(data):
        return None
    catalog_indices = list(
        struct.unpack_from(f"<{catalog_count}I", data, record_end)
    )
    if catalog_indices != list(range(catalog_count)):
        return None

    return {
        "record_kind": "minimal_default_catalog_tail",
        "offset": name_offset,
        "name": name,
        "name_end_offset": name_end,
        "marker_hex": marker.hex(),
        "cue_guid": cue_guid.hex(),
        "unknown_u32": None,
        "fixture_profile_guid": None,
        "entry_count": 0,
        "entries_offset": None,
        "entries_end_offset": name_end + 24,
        "entries": [],
        "groups": {},
        "catalog_count": catalog_count,
        "catalog_indices_offset": record_end,
        "catalog_indices_end_offset": catalog_end,
    }


def parse_venue_cues(data: bytes) -> list[dict]:
    # PHYSICAL scan: records are reported exactly as framed on disk
    # ([name][guid][header][value block]). NOTE the byte-proven
    # precede-association (2026-07-02): each framed value block semantically
    # belongs to the NEXT (name, guid) identity. Structural tools consume
    # this physical framing; semantic consumers must re-associate (see
    # layered_renderer.venue_cue_records).
    cues = []
    offset = 0
    while offset + 4 <= len(data):
        cue = cue_at(data, offset)
        if cue is None:
            cue = minimal_tail_cue_at(data, offset)
        if cue is None:
            offset += 1
            continue
        cues.append(cue)
        offset = cue.get("catalog_indices_end_offset", cue["entries_end_offset"])
    return cues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("venue", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    data = args.venue.read_bytes()
    cues = parse_venue_cues(data)
    fixture_profile_channels = parse_fixture_profile_channels(data)
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
                "fixture_profile_channels": fixture_profile_channels,
                "fixture_profile_channel_count": len(fixture_profile_channels),
                "fixture_profile_has_intensity_channel": any(
                    channel["name"].casefold() == "intensity"
                    for channel in fixture_profile_channels
                ),
                "unsupported_reason": (
                    "attribute cue records and the primary fixture-profile channel names are "
                    "decoded; venue fixture instances, positions, categories, and remaining "
                    "top-level objects are outside this parser"
                ),
                "cues": output,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
