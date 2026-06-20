#!/usr/bin/env python3
"""Read-only structural analyzer for observed SoundSwitch autoloop files."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


MAGIC = b"\xaa\xaa\x09\x55"
EVENT_COUNT_OFFSET = 2255
POST_EVENTS_SHARED_SIZE = 441
TRAILER_SIZE = 13


def _u32le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _timeline_record(data: bytes, offset: int) -> dict:
    field_a, field_b, low_time_byte = struct.unpack_from(">III", data, offset)
    if low_time_byte > 255:
        raise ValueError(f"timeline low-time byte exceeds 255 at byte {offset}")
    packed = _u32le(data, offset + 12)
    high_time_bytes = packed & 0x00FFFFFF
    raw_reference = packed >> 24
    return {
        "offset": offset,
        "field_a": field_a,
        "field_b": field_b,
        "low_time_byte": low_time_byte,
        "time": (
            -1
            if high_time_bytes == 0x00FFFFFF
            else (high_time_bytes << 8) | low_time_byte
        ),
        "raw_cue_reference": raw_reference,
        "resolved_dictionary_index": raw_reference - 1 if raw_reference > 0 else None,
        "reference_kind": "cue" if raw_reference > 0 else "clear_control",
    }


def parse_autoloop_structure(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError("not a SoundSwitch container")
    if len(data) < EVENT_COUNT_OFFSET + 4:
        raise ValueError("file is shorter than the observed autoloop prefix")

    event_count = _u32le(data, EVENT_COUNT_OFFSET)
    offset = EVENT_COUNT_OFFSET + 4
    events = []
    for index in range(event_count):
        if offset + 17 > len(data):
            raise ValueError(f"truncated event record {index}")
        record_type, tick_a, tick_b, auxiliary = struct.unpack_from(
            "<IIII", data, offset
        )
        trailer = data[offset + 16]
        if record_type != 2 or tick_a != tick_b or trailer != 0:
            raise ValueError(f"unexpected event record at byte {offset}")
        events.append(
            {
                "offset": offset,
                "type": record_type,
                "tick_a": tick_a,
                "tick_b": tick_b,
                "auxiliary": auxiliary,
                "trailer": trailer,
            }
        )
        offset += 17

    shared_block_offset = offset
    offset += POST_EVENTS_SHARED_SIZE
    if offset + 4 > len(data):
        raise ValueError("missing cue dictionary")

    cue_count_offset = offset
    cue_count = _u32be(data, offset)
    offset += 4
    cues = []
    for index in range(cue_count):
        if offset + 20 > len(data):
            raise ValueError(f"truncated cue-dictionary entry {index}")
        if data[offset : offset + 3] != b"\0\0\0":
            raise ValueError(f"unexpected cue-dictionary prefix at byte {offset}")
        cues.append(
            {
                "offset": offset,
                "guid": data[offset + 3 : offset + 19].hex(),
                "cue_index": data[offset + 19],
            }
        )
        offset += 20
    cue_indices = [entry["cue_index"] for entry in cues]
    if len(cue_indices) != len(set(cue_indices)):
        raise ValueError("cue-dictionary indices are not unique")

    if offset + 4 > len(data):
        raise ValueError("missing timeline count")
    timeline_count_offset = offset
    declared_timeline_count = _u32be(data, offset)
    offset += 4
    timeline = []
    for index in range(declared_timeline_count):
        if offset + 16 > len(data):
            raise ValueError(f"truncated timeline record {index}")
        timeline.append(_timeline_record(data, offset))
        offset += 16

    if len(data) - offset < TRAILER_SIZE:
        raise ValueError("missing observed 13-byte trailer")
    extra = data[offset : len(data) - TRAILER_SIZE]
    continuation = []
    if extra and len(extra) % 16 == 0:
        continuation_offset = offset
        while offset < len(data) - TRAILER_SIZE:
            continuation.append(_timeline_record(data, offset))
            offset += 16
        if any(row["field_b"] != 1 for row in continuation):
            continuation = []
            offset = continuation_offset
    timeline.extend(continuation)

    return {
        "size": len(data),
        "version": _u32le(data, 4),
        "fixture_profile_guid": data[28:44].hex(),
        "event_count_offset": EVENT_COUNT_OFFSET,
        "event_count": event_count,
        "events": events,
        "shared_block_offset": shared_block_offset,
        "shared_block_size": POST_EVENTS_SHARED_SIZE,
        "cue_count_offset": cue_count_offset,
        "cue_count": cue_count,
        "cues": cues,
        "timeline_count_offset": timeline_count_offset,
        "declared_timeline_count": declared_timeline_count,
        "continuation_timeline_count": len(continuation),
        "timeline_count": len(timeline),
        "timeline": timeline,
        "extra_offset": offset,
        "extra_size": 0 if continuation else len(extra),
        "extra_hex": "" if continuation else extra.hex(),
        "trailer_offset": len(data) - TRAILER_SIZE,
        "trailer_hex": data[-TRAILER_SIZE:].hex(),
    }


def summary(path: Path, parsed: dict) -> dict:
    timeline = parsed["timeline"]
    return {
        "path": str(path),
        "status": "parsed",
        "size": parsed["size"],
        "version": parsed["version"],
        "event_count_offset": parsed["event_count_offset"],
        "event_count": parsed["event_count"],
        "nonzero_auxiliary_count": sum(
            row["auxiliary"] != 0 for row in parsed["events"]
        ),
        "auxiliary_values": sorted({row["auxiliary"] for row in parsed["events"]}),
        "shared_block_offset": parsed["shared_block_offset"],
        "cue_count_offset": parsed["cue_count_offset"],
        "cue_count": parsed["cue_count"],
        "timeline_count_offset": parsed["timeline_count_offset"],
        "timeline_count": parsed["timeline_count"],
        "negative_time_count": sum(row["time"] < 0 for row in timeline),
        "ref_zero_count": sum(row["raw_cue_reference"] == 0 for row in timeline),
        "declared_timeline_count": parsed["declared_timeline_count"],
        "continuation_timeline_count": parsed["continuation_timeline_count"],
        "extra_size": parsed["extra_size"],
        "trailer_offset": parsed["trailer_offset"],
        "trailer_hex": parsed["trailer_hex"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    output = []
    for path in args.files:
        data = path.read_bytes()
        try:
            parsed = parse_autoloop_structure(data)
            row = (
                {"path": str(path), "status": "parsed", **parsed}
                if args.full
                else summary(path, parsed)
            )
            row["sha256"] = hashlib.sha256(data).hexdigest()
            output.append(row)
        except ValueError as error:
            output.append(
                {
                    "path": str(path),
                    "status": "unsupported",
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "version": _u32le(data, 4) if len(data) >= 8 else None,
                    "unsupported_reason": str(error),
                }
            )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
