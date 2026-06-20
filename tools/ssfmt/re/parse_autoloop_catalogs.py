#!/usr/bin/env python3
"""Strict parser for the observed base and extended autoloop catalogs."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


MAGIC = b"\xaa\xaa\x09\x55"


def u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise ValueError(f"missing u32 at byte {offset}")
    return struct.unpack_from("<I", data, offset)[0]


def string(data: bytes, offset: int) -> tuple[str, int, int]:
    length = u32(data, offset)
    end = offset + 4 + length * 2
    if length < 1 or end > len(data):
        raise ValueError(f"invalid UTF-16 length {length} at byte {offset}")
    try:
        value = data[offset + 4 : end].decode("utf-16le")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid UTF-16 at byte {offset}") from error
    if not value.endswith("\0"):
        raise ValueError(f"UTF-16 string lacks terminator at byte {offset}")
    return value[:-1], end, length


def parse_catalog(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError("not a SoundSwitch catalog")
    version = u32(data, 4)
    reserved_a = u32(data, 8)
    reserved_b = u32(data, 12)
    layout = u32(data, 16)
    if (reserved_a, reserved_b) != (0, 0) or layout not in (2, 3):
        raise ValueError("unexpected catalog header")
    category_count = u32(data, 20)
    offset = 24
    categories = []
    for index in range(category_count):
        enabled_offset = offset
        enabled = u32(data, offset)
        offset += 4
        name_offset = offset
        name, offset, _length = string(data, offset)
        categories.append(
            {
                "index": index,
                "enabled_offset": enabled_offset,
                "enabled": enabled,
                "name_offset": name_offset,
                "name": name,
            }
        )

    entry_count_offset = offset
    entry_count = u32(data, offset)
    offset += 4
    entries = []
    for ordering in range(entry_count):
        record_offset = offset
        record_type = u32(data, offset)
        offset += 4
        if record_type != 2:
            raise ValueError(f"unexpected catalog record type at byte {record_offset}")
        index_offset = offset
        app_log_index = u32(data, offset)
        bars = u32(data, offset + 4)
        enabled = u32(data, offset + 8)
        offset += 12
        name_offset = offset
        display_name, offset, _length = string(data, offset)
        category_offset = offset
        category_index = u32(data, offset)
        offset += 4
        if bars != 8 or enabled != 1 or category_index >= category_count:
            raise ValueError(f"unexpected entry fields at byte {record_offset}")
        entries.append(
            {
                "ordering": ordering,
                "record_offset": record_offset,
                "record_type": record_type,
                "index_offset": index_offset,
                "app_log_index": app_log_index,
                "file_number": app_log_index + 1,
                "bars": bars,
                "enabled": enabled,
                "name_offset": name_offset,
                "display_name": display_name,
                "category_offset": category_offset,
                "category_index": category_index,
                "category": categories[category_index]["name"],
            }
        )

    table_offset = offset
    category_order = []
    for category_index in range(category_count):
        marker_offset = None
        marker = None
        if category_index > 0:
            marker_offset = offset
            marker = data[offset] if offset < len(data) else None
            if marker != 1:
                raise ValueError(f"unexpected category-table marker at byte {offset}")
            offset += 1
        count_offset = offset
        count = u32(data, offset)
        offset += 4
        indices_offset = offset
        indices = []
        for _unused in range(count):
            indices.append(u32(data, offset))
            offset += 4
        category_order.append(
            {
                "category_index": category_index,
                "category": categories[category_index]["name"],
                "marker_offset": marker_offset,
                "marker": marker,
                "count_offset": count_offset,
                "count": count,
                "indices_offset": indices_offset,
                "app_log_indices": indices,
            }
        )
    final_marker_offset = offset
    if offset >= len(data) or data[offset] != 1:
        raise ValueError(f"missing final catalog marker at byte {offset}")
    offset += 1
    if offset != len(data):
        raise ValueError(f"unparsed catalog trailing bytes at byte {offset}")

    entries_by_category = {
        category_index: {entry["app_log_index"] for entry in entries if entry["category_index"] == category_index}
        for category_index in range(category_count)
    }
    for row in category_order:
        table_indices = set(row["app_log_indices"])
        entry_indices = entries_by_category[row["category_index"]]
        valid = (
            table_indices == entry_indices
            if layout == 2
            else entry_indices.issubset(table_indices)
        )
        if not valid:
            raise ValueError(
                f"category index table disagrees with entries for category {row['category_index']}"
            )

    return {
        "size": len(data),
        "version": version,
        "layout": layout,
        "category_count": category_count,
        "categories": categories,
        "entry_count_offset": entry_count_offset,
        "entry_count": entry_count,
        "entries": entries,
        "category_index_table_offset": table_offset,
        "category_order": category_order,
        "final_marker_offset": final_marker_offset,
        "unparsed_size": len(data) - offset,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    output = []
    for path in args.files:
        data = path.read_bytes()
        try:
            output.append(
                {
                    "path": str(path),
                    "status": "parsed",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    **parse_catalog(data),
                }
            )
        except ValueError as error:
            output.append(
                {
                    "path": str(path),
                    "status": "unsupported",
                    "size": len(data),
                    "version": u32(data, 4) if len(data) >= 8 else None,
                    "unsupported_reason": str(error),
                }
            )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
