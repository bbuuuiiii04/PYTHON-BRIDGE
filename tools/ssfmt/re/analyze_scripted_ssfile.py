#!/usr/bin/env python3
"""Read-only analyzer for observed shared-table scripted SoundSwitch files."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from analyze_ssfile_structure import (
    MAGIC,
    REFERENCE_RULES,
    TRAILER_SIZE,
    decode_timeline_time,
    parse_autoloop_structure,
)


def u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def u32le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def shared_table_from_autoloop(path: Path) -> bytes:
    data = path.read_bytes()
    parsed = parse_autoloop_structure(data)
    start = parsed["shared_block_offset"]
    return data[start : start + parsed["shared_block_size"]]


def timeline_record(
    data: bytes, offset: int, reference_rule: str = "ambiguous"
) -> dict:
    field_a, field_b, low_time_byte = struct.unpack_from(">III", data, offset)
    if low_time_byte > 255:
        raise ValueError(f"scripted low-time byte exceeds 255 at byte {offset}")
    packed = u32le(data, offset + 12)
    high_time_bytes = packed & 0x00FFFFFF
    raw_reference = packed >> 24
    direct_index = raw_reference if raw_reference > 0 else None
    one_based_index = raw_reference - 1 if raw_reference > 0 else None
    return {
        "offset": offset,
        "field_a": field_a,
        "field_b": field_b,
        "low_time_byte": low_time_byte,
        "elapsed": decode_timeline_time(high_time_bytes, low_time_byte),
        "raw_cue_reference": raw_reference,
        "direct_dictionary_index": direct_index,
        "one_based_dictionary_index": one_based_index,
        "reference_rule": reference_rule,
        "resolved_dictionary_index": {
            "direct": direct_index,
            "one_based": one_based_index,
            "ambiguous": None,
        }[reference_rule],
        "reference_kind": "cue" if raw_reference > 0 else "clear_control",
    }


def parse_scripted_structure(
    data: bytes, shared_table: bytes, reference_rule: str = "ambiguous"
) -> dict:
    """Parse a scripted-track .ssfile.

    WIRE-PROVEN provenance facts (A5/SANFRANDISCO Art-Net capture, 14/14 exact):
    - Legacy scripted records are ONE-BASED (raw == cue_index byte + 1).
    - Newly written records (current SoundSwitch) are DIRECT (raw == cue_index byte).
    - Editing a legacy file appends the new record DIRECT without renormalizing the
      old one-based records => MIXED file with no byte-level disambiguator
      (version 3, field_a=field_b=1, elapsed-sorted).

    Resolution is therefore not deterministic from bytes alone for the general
    corpus. Default is ``ambiguous`` (both candidate indices preserved). Pass an
    explicit rule only with justified provenance (e.g. one_based for an untouched
    legacy file; direct for a freshly created file); mixed files must fail closed.
    """
    if data[:4] != MAGIC:
        raise ValueError("not a SoundSwitch container")
    if len(data) < 8:
        raise ValueError("file is shorter than the SoundSwitch header")
    version = u32le(data, 4)

    locations = []
    start = 0
    while True:
        offset = data.find(shared_table, start)
        if offset < 0:
            break
        locations.append(offset)
        start = offset + 1
    if len(locations) != 1:
        raise ValueError(f"expected one observed shared table, found {len(locations)}")

    shared_block_offset = locations[0]
    offset = shared_block_offset + len(shared_table)
    if offset + 4 > len(data):
        raise ValueError("missing scripted cue dictionary")
    cue_count_offset = offset
    cue_count = u32be(data, offset)
    offset += 4
    cues = []
    for index in range(cue_count):
        if offset + 20 > len(data):
            raise ValueError(f"truncated scripted cue entry {index}")
        if data[offset : offset + 3] != b"\0\0\0":
            raise ValueError(f"unexpected scripted cue prefix at byte {offset}")
        cues.append(
            {
                "offset": offset,
                "guid": data[offset + 3 : offset + 19].hex(),
                "cue_index": data[offset + 19],
            }
        )
        offset += 20

    if offset + 4 > len(data):
        raise ValueError("missing scripted timeline count")
    timeline_count_offset = offset
    declared_timeline_count = u32be(data, offset)
    offset += 4
    timeline = []
    for index in range(declared_timeline_count):
        if offset + 16 > len(data):
            raise ValueError(f"truncated scripted timeline record {index}")
        timeline.append(timeline_record(data, offset, reference_rule))
        offset += 16

    if len(data) - offset < TRAILER_SIZE:
        raise ValueError("missing scripted trailer")
    extra = data[offset : len(data) - TRAILER_SIZE]
    continuation = []
    if extra and len(extra) % 16 == 0:
        continuation_offset = offset
        while offset < len(data) - TRAILER_SIZE:
            continuation.append(timeline_record(data, offset, reference_rule))
            offset += 16
        if any(row["field_b"] != 1 for row in continuation):
            continuation = []
            offset = continuation_offset
    timeline.extend(continuation)

    return {
        "size": len(data),
        "version": version,
        "reference_rule": reference_rule,
        "shared_block_offset": shared_block_offset,
        "shared_block_size": len(shared_table),
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


def summary(parsed: dict) -> dict:
    timeline = parsed["timeline"]
    return {
        "size": parsed["size"],
        "version": parsed["version"],
        "reference_rule": parsed["reference_rule"],
        "shared_block_offset": parsed["shared_block_offset"],
        "cue_count_offset": parsed["cue_count_offset"],
        "cue_count": parsed["cue_count"],
        "timeline_count_offset": parsed["timeline_count_offset"],
        "declared_timeline_count": parsed["declared_timeline_count"],
        "continuation_timeline_count": parsed["continuation_timeline_count"],
        "timeline_count": parsed["timeline_count"],
        "elapsed_min": min((row["elapsed"] for row in timeline if row["elapsed"] >= 0), default=None),
        "elapsed_max": max((row["elapsed"] for row in timeline if row["elapsed"] >= 0), default=None),
        "negative_time_count": sum(row["elapsed"] < 0 for row in timeline),
        "clear_control_event_count": sum(
            row["reference_kind"] == "clear_control" for row in timeline
        ),
        "raw_cue_references": sorted({row["raw_cue_reference"] for row in timeline}),
        "resolved_dictionary_indices": sorted(
            {
                row["resolved_dictionary_index"]
                for row in timeline
                if row["resolved_dictionary_index"] is not None
            }
        ),
        "extra_offset": parsed["extra_offset"],
        "extra_size": parsed["extra_size"],
        "trailer_offset": parsed["trailer_offset"],
        "trailer_hex": parsed["trailer_hex"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--autoloop-reference", required=True, type=Path)
    parser.add_argument(
        "--reference-rule",
        choices=REFERENCE_RULES,
        default="ambiguous",
        help="convention is provenance-dependent; default 'ambiguous' preserves both "
        "candidates. legacy=one_based is wire-proven; new=direct; edited legacy=MIXED "
        "(fail closed). Pass one_based/direct only with justified provenance.",
    )
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    shared_table = shared_table_from_autoloop(args.autoloop_reference)
    output = []
    for path in args.files:
        data = path.read_bytes()
        try:
            parsed = parse_scripted_structure(data, shared_table, args.reference_rule)
            row = (
                {"path": str(path), "status": "parsed", **parsed}
                if args.full
                else {"path": str(path), "status": "parsed", **summary(parsed)}
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
                    "version": u32le(data, 4) if len(data) >= 8 else None,
                    "unsupported_reason": str(error),
                }
            )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
