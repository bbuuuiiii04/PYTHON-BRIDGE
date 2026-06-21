#!/usr/bin/env python3
"""Strict read-only scanner for observed SoundSwitch Venue static-look slots."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from parse_venue_cues import CHANNEL_BY_ID, KNOWN_FIXTURE_GROUPS


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _scalar_table(
    data: bytes, offset: int, expected_count: int, expected_ids: list[int] | None
) -> tuple[list[dict], int] | None:
    if offset + 4 > len(data) or _u32(data, offset) != expected_count:
        return None
    offset += 4
    rows = []
    for _ in range(expected_count):
        if offset + 12 > len(data):
            return None
        instance_id = _u32(data, offset)
        value = struct.unpack_from("<d", data, offset + 4)[0]
        if not math.isfinite(value):
            return None
        rows.append(
            {"offset": offset, "fixture_instance_id": instance_id, "value": value}
        )
        offset += 12
    ids = [row["fixture_instance_id"] for row in rows]
    if len(ids) != len(set(ids)) or expected_ids is not None and ids != expected_ids:
        return None
    return rows, offset


def static_look_at(data: bytes, start: int) -> dict | None:
    if start + 16 > len(data):
        return None
    unknown_u32, fixture_count, enabled, name_length = struct.unpack_from(
        "<IIII", data, start
    )
    if unknown_u32 != 0 or not 1 <= fixture_count <= 64 or enabled not in (0, 1):
        return None
    if not 1 <= name_length <= 96:
        return None
    name_offset = start + 16
    name_end = name_offset + 2 * name_length
    if name_end > len(data):
        return None
    try:
        decoded_name = data[name_offset:name_end].decode("utf-16le")
    except UnicodeDecodeError:
        return None
    if not decoded_name.endswith("\0"):
        return None
    name = decoded_name[:-1]
    if not all(32 <= ord(character) < 127 for character in name):
        return None

    first = _scalar_table(data, name_end, fixture_count, None)
    if first is None:
        return None
    primary_values, offset = first
    instance_ids = [row["fixture_instance_id"] for row in primary_values]
    second = _scalar_table(data, offset, fixture_count, instance_ids)
    if second is None:
        return None
    secondary_values, offset = second

    if offset + 4 > len(data) or _u32(data, offset) != fixture_count:
        return None
    offset += 4
    state_rows = []
    for _ in range(fixture_count):
        if offset + 12 > len(data):
            return None
        instance_id, state, reserved = struct.unpack_from("<IiI", data, offset)
        state_rows.append(
            {
                "offset": offset,
                "fixture_instance_id": instance_id,
                "state": state,
                "reserved": reserved,
            }
        )
        offset += 12
    if [row["fixture_instance_id"] for row in state_rows] != instance_ids:
        return None

    if offset + 4 > len(data) or _u32(data, offset) != fixture_count:
        return None
    offset += 4
    position_rows = []
    for _ in range(fixture_count):
        if offset + 20 > len(data):
            return None
        instance_id = _u32(data, offset)
        position_rows.append(
            {
                "offset": offset,
                "fixture_instance_id": instance_id,
                "position_reference_guid": data[offset + 4 : offset + 20].hex(),
            }
        )
        offset += 20
    if [row["fixture_instance_id"] for row in position_rows] != instance_ids:
        return None

    if offset + 4 > len(data):
        return None
    entry_count = _u32(data, offset)
    if entry_count > 1024:
        return None
    offset += 4
    entries = []
    groups: dict[str, dict[str, int]] = {}
    for _ in range(entry_count):
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
            }
        )
        groups.setdefault(hex(fixture_group), {})[str(channel)] = value
        offset += 16

    return {
        "offset": start,
        "end_offset": offset,
        "unknown_u32": unknown_u32,
        "enabled": enabled,
        "name": name,
        "name_offset": name_offset,
        "name_end_offset": name_end,
        "fixture_count": fixture_count,
        "fixture_instance_ids": instance_ids,
        "primary_values": primary_values,
        "secondary_values": secondary_values,
        "states": state_rows,
        "positions": position_rows,
        "entry_count": entry_count,
        "entries": entries,
        "groups": groups,
    }


def parse_static_looks(data: bytes) -> list[dict]:
    looks = []
    offset = 0
    while offset + 16 <= len(data):
        look = static_look_at(data, offset)
        if look is None:
            offset += 1
            continue
        look["slot_ordinal"] = len(looks)
        looks.append(look)
        offset = look["end_offset"]
    return looks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("venue", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    data = args.venue.read_bytes()
    looks = parse_static_looks(data)
    output = looks if args.full else [
        {
            key: value
            for key, value in look.items()
            if key not in {"primary_values", "secondary_values", "states", "positions", "entries"}
        }
        for look in looks
    ]
    print(
        json.dumps(
            {
                "path": str(args.venue),
                "status": "partial",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "static_look_count": len(looks),
                "identity_rule": "slot_ordinal within the observed Venue static-look sequence",
                "unsupported_reason": (
                    "observed slot grammar is decoded; containing Venue object labels and "
                    "slot deletion/reordering behavior remain outside this parser"
                ),
                "static_looks": output,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
