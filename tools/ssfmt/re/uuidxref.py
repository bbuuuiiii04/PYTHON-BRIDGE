#!/usr/bin/env python3
"""Historical Stage-1 UUID cross-reference probe, restored from surviving pyc.

This heuristic helped establish that 12 repeated UUID/slot records were shared
references.  They are now known to be Venue position presets.  Use
``analyze_fixture_prefix.py`` for current evidence.
"""
from __future__ import annotations

import os
import struct
import sys


def candidates(data: bytes) -> list[tuple[int, bytes, int]]:
    out = []
    seen = set()
    offset = 4
    while offset + 20 <= len(data):
        group = data[offset : offset + 16]
        index = struct.unpack_from("<I", data, offset + 16)[0]
        integers = struct.unpack("<4I", group)
        biggish = sum(value > 0xFFFF for value in integers) >= 2
        if any(integers) and biggish and index <= 31 and group not in seen:
            seen.add(group)
            out.append((offset, group, index))
        offset += 4
    return out


def main() -> None:
    probe = sys.argv[1]
    others = sys.argv[2:]
    data = open(probe, "rb").read()
    refs = candidates(data)
    print(
        f"# probe={os.path.basename(probe)} size={len(data)} "
        f"candidate_refs={len(refs)} others={len(others)}"
    )
    blobs = {path: open(path, "rb").read() for path in others if os.path.isfile(path)}
    for offset, group, index in refs:
        hits = [os.path.basename(path) for path, blob in blobs.items() if group in blob]
        print(f"off={offset:5d} idx={index:2d} uuid={group.hex()} hits={hits or '-'}")


if __name__ == "__main__":
    main()
