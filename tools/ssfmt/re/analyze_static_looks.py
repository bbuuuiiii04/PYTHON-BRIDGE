#!/usr/bin/env python3
"""Strict read-only parser for SoundSwitch Venue static-look collections."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from parse_venue_cues import CHANNEL_BY_ID, KNOWN_FIXTURE_GROUPS


_STATIC_LOOKS_VERSION = 1
_STATIC_LOOK_COUNT = 32
_STATIC_LOOK_VERSION = 5
_CAF_STRING_ENCODING = 1


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _caf_string(data: bytes, offset: int) -> tuple[str, int] | None:
    if offset + 8 > len(data):
        return None
    encoding, character_count = struct.unpack_from("<II", data, offset)
    if encoding != _CAF_STRING_ENCODING or not 1 <= character_count <= 256:
        return None
    start = offset + 8
    end = start + 2 * character_count
    if end > len(data):
        return None
    try:
        decoded = data[start:end].decode("utf-16le")
    except UnicodeDecodeError:
        return None
    if not decoded.endswith("\0") or "\0" in decoded[:-1]:
        return None
    name = decoded[:-1]
    if not all(32 <= ord(character) < 127 for character in name):
        return None
    return name, end


def _scalar_map(data: bytes, offset: int) -> tuple[list[dict], int] | None:
    if offset + 4 > len(data):
        return None
    count = _u32(data, offset)
    if count > 1024:
        return None
    offset += 4
    rows = []
    for _ in range(count):
        if offset + 12 > len(data):
            return None
        fixture_instance_id = _u32(data, offset)
        value = struct.unpack_from("<d", data, offset + 4)[0]
        if not math.isfinite(value):
            return None
        rows.append(
            {
                "offset": offset,
                "fixture_instance_id": fixture_instance_id,
                "value": value,
            }
        )
        offset += 12
    if len({row["fixture_instance_id"] for row in rows}) != len(rows):
        return None
    return rows, offset


def _colour_map(data: bytes, offset: int) -> tuple[list[dict], int] | None:
    if offset + 4 > len(data):
        return None
    count = _u32(data, offset)
    if count > 1024:
        return None
    offset += 4
    rows = []
    for _ in range(count):
        if offset + 12 > len(data):
            return None
        fixture_instance_id = _u32(data, offset)
        raw = data[offset + 4 : offset + 12]
        rows.append(
            {
                "offset": offset,
                "fixture_instance_id": fixture_instance_id,
                "colour_value_u64": int.from_bytes(raw, "little"),
                "colour_value_raw_hex": raw.hex(),
            }
        )
        offset += 12
    if len({row["fixture_instance_id"] for row in rows}) != len(rows):
        return None
    return rows, offset


def _position_map(data: bytes, offset: int) -> tuple[list[dict], int] | None:
    if offset + 4 > len(data):
        return None
    count = _u32(data, offset)
    if count > 1024:
        return None
    offset += 4
    rows = []
    for _ in range(count):
        if offset + 20 > len(data):
            return None
        rows.append(
            {
                "offset": offset,
                "fixture_instance_id": _u32(data, offset),
                "position_reference_guid": data[offset + 4 : offset + 20].hex(),
            }
        )
        offset += 20
    if len({row["fixture_instance_id"] for row in rows}) != len(rows):
        return None
    return rows, offset


def _fixture_attributes(data: bytes, offset: int) -> tuple[list[dict], dict, int] | None:
    if offset + 4 > len(data):
        return None
    count = _u32(data, offset)
    if count > 4096:
        return None
    offset += 4
    entries = []
    groups: dict[str, dict[str, int]] = {}
    for _ in range(count):
        if offset + 16 > len(data):
            return None
        present, fixture_group, channel_id = struct.unpack_from("<III", data, offset)
        repeated_value = data[offset + 12 : offset + 16]
        if (
            present != 1
            or fixture_group not in KNOWN_FIXTURE_GROUPS
            or channel_id not in CHANNEL_BY_ID
            or len(set(repeated_value)) != 1
        ):
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
                "attribute_value_raw_hex": repeated_value.hex(),
            }
        )
        groups.setdefault(hex(fixture_group), {})[str(channel)] = value
        offset += 16
    return entries, groups, offset


def static_look_at(data: bytes, start: int) -> dict | None:
    """Parse one physical version-5 ``StaticLook`` record."""
    if start + 12 > len(data) or _u32(data, start) != _STATIC_LOOK_VERSION:
        return None
    string_result = _caf_string(data, start + 4)
    if string_result is None:
        return None
    name, offset = string_result

    primary = _scalar_map(data, offset)
    if primary is None:
        return None
    primary_values, offset = primary
    secondary = _scalar_map(data, offset)
    if secondary is None:
        return None
    secondary_values, offset = secondary
    colours = _colour_map(data, offset)
    if colours is None:
        return None
    colour_values, offset = colours
    positions_result = _position_map(data, offset)
    if positions_result is None:
        return None
    positions, offset = positions_result
    fixture_result = _fixture_attributes(data, offset)
    if fixture_result is None:
        return None
    entries, groups, offset = fixture_result

    instance_ids = [row["fixture_instance_id"] for row in primary_values]
    for rows in (secondary_values, colour_values, positions):
        if [row["fixture_instance_id"] for row in rows] != instance_ids:
            return None
    return {
        "offset": start,
        "end_offset": offset,
        "record_version": _STATIC_LOOK_VERSION,
        "name": name,
        "fixture_count": len(instance_ids),
        "fixture_instance_ids": instance_ids,
        "primary_values": primary_values,
        "secondary_values": secondary_values,
        "colour_values": colour_values,
        "positions": positions,
        "entry_count": len(entries),
        "entries": entries,
        "groups": groups,
    }


def parse_static_look_collections(data: bytes) -> list[dict]:
    """Find complete GUID-keyed ``StaticLooks`` containers in Venue bytes."""
    marker = struct.pack("<II", _STATIC_LOOKS_VERSION, _STATIC_LOOK_COUNT)
    collections = []
    search_offset = 16
    while True:
        header_offset = data.find(marker, search_offset)
        if header_offset < 0:
            break
        guid_offset = header_offset - 16
        offset = header_offset + len(marker)
        looks = []
        for slot_index in range(_STATIC_LOOK_COUNT):
            look = static_look_at(data, offset)
            if look is None:
                looks = []
                break
            look["slot_index"] = slot_index
            look["slot_ordinal"] = slot_index
            looks.append(look)
            offset = look["end_offset"]
        if looks:
            collections.append(
                {
                    "guid_offset": guid_offset,
                    "venue_guid": data[guid_offset:header_offset].hex(),
                    "header_offset": header_offset,
                    "end_offset": offset,
                    "version": _STATIC_LOOKS_VERSION,
                    "slot_count": _STATIC_LOOK_COUNT,
                    "static_looks": looks,
                }
            )
            search_offset = offset
        else:
            search_offset = header_offset + 1
    return collections


def primary_venue_identity(data: bytes) -> dict | None:
    """Decode the bounded current-layout primary Venue identity at the file head."""
    if len(data) < 52:
        return None
    venue_count, venue_version = struct.unpack_from("<II", data, 20)
    if venue_count < 1 or venue_version != 4:
        return None
    name_result = _caf_string(data, 44)
    if name_result is None:
        return None
    name, _ = name_result
    return {
        "venue_count": venue_count,
        "venue_version": venue_version,
        "venue_guid": data[28:44].hex(),
        "venue_name": name,
    }


def parse_static_looks(data: bytes) -> list[dict]:
    """Return the primary current Venue's exact 32-slot collection."""
    identity = primary_venue_identity(data)
    if identity is None:
        return []
    matches = [
        row
        for row in parse_static_look_collections(data)
        if row["venue_guid"] == identity["venue_guid"]
    ]
    return matches[0]["static_looks"] if len(matches) == 1 else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("venue", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    data = args.venue.read_bytes()
    identity = primary_venue_identity(data)
    collections = parse_static_look_collections(data)
    looks = parse_static_looks(data)
    output = looks if args.full else [
        {
            key: value
            for key, value in look.items()
            if key
            not in {
                "primary_values",
                "secondary_values",
                "colour_values",
                "positions",
                "entries",
            }
        }
        for look in looks
    ]
    print(
        json.dumps(
            {
                "path": str(args.venue),
                "status": "parsed" if identity is not None and len(looks) == 32 else "unsupported",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "primary_venue": identity,
                "collection_count": len(collections),
                "static_look_count": len(looks),
                "identity_rule": "zero-based StaticOverride suffix selects the same slot_index",
                "static_looks": output,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
