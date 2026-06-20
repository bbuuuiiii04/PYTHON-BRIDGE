#!/usr/bin/env python3
"""Heuristic token viewer for SoundSwitch containers; discovery only."""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def tokens(data: bytes, limit: int | None = None) -> list[dict]:
    rows = []
    offset = 0
    while offset + 4 <= len(data) and (limit is None or len(rows) < limit):
        value = struct.unpack_from("<I", data, offset)[0]
        byte_count = value * 2
        if 1 <= value <= 4096 and offset + 4 + byte_count <= len(data):
            raw = data[offset + 4 : offset + 4 + byte_count]
            try:
                decoded = raw.decode("utf-16le")
            except UnicodeDecodeError:
                decoded = ""
            if decoded.endswith("\0") and all(
                character == "\0" or character in "\r\n\t" or ord(character) >= 32
                for character in decoded
            ):
                rows.append(
                    {
                        "offset": offset,
                        "kind": "utf16le",
                        "code_units": value,
                        "value": decoded[:-1],
                    }
                )
                offset += 4 + byte_count
                continue
        rows.append({"offset": offset, "kind": "u32le", "value": value})
        offset += 4
    if offset < len(data):
        rows.append(
            {
                "offset": offset,
                "kind": "unparsed_tail",
                "size": len(data) - offset,
                "hex_prefix": data[offset : offset + 64].hex(),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("limit", nargs="?", type=int)
    args = parser.parse_args()
    data = args.file.read_bytes()
    print(
        json.dumps(
            {
                "path": str(args.file),
                "size": len(data),
                "version": struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else None,
                "warning": "heuristic discovery tokens; not a format parser",
                "tokens": tokens(data, args.limit),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
