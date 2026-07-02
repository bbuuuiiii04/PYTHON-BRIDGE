#!/usr/bin/env python3
"""Read-only structural analyzer for observed SoundSwitch autoloop files."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


MAGIC = b"\xaa\xaa\x09\x55"
INTENSITY_TRACK_TYPE = 1
INTENSITY_TRACK_NODE_COUNT_OFFSET = 2255
# Compatibility alias for older research consumers. The 17-byte records were
# initially labeled generic events; binary analysis identifies them as the
# type-1 (intensity) AttributeTrack nodes.
EVENT_COUNT_OFFSET = INTENSITY_TRACK_NODE_COUNT_OFFSET
POST_EVENTS_SHARED_SIZE = 441
# Physical SoundSwitchDocData v12 trailer: u32, bool, u32, bool. Older research
# reported 13 bytes because its three-byte-shifted view included the trailing
# bytes of the final timeline raw-reference word.
TRAILER_SIZE = 10
MINIMAL_SHARED_BLOCK_OFFSET = 87
OBSERVED_SHARED_BLOCK_SHA256 = (
    "ef84f0902fac69c8836cab500cee88b61b71ce13f3bf544d8c3f9ecfb6e73fd1"
)
REFERENCE_RULES = ("exact_key", "direct", "one_based", "ambiguous")


def _u32le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def decode_timeline_time(high_time_bytes: int, low_time_byte: int) -> int:
    """Reassemble the observed split field as a signed 32-bit tick value."""
    encoded = (high_time_bytes << 8) | low_time_byte
    return encoded - (1 << 32) if encoded & 0x80000000 else encoded


def _timeline_record(data: bytes, offset: int, reference_rule: str) -> dict:
    field_a, field_b, elapsed, raw_reference = struct.unpack_from(
        "<IIiI", data, offset
    )
    if field_a > 1:
        raise ValueError(
            f"timeline entry version {field_a} is unsupported at byte {offset}"
        )
    if field_b != 1:
        raise ValueError(
            f"timeline entry constant is {field_b}, expected 1 at byte {offset}"
        )
    direct_index = raw_reference if raw_reference > 0 else None
    one_based_index = raw_reference - 1 if raw_reference > 0 else None
    resolved_index = {
        "exact_key": direct_index,
        "direct": direct_index,
        "one_based": one_based_index,
        "ambiguous": None,
    }[reference_rule]
    return {
        "offset": offset,
        "field_a": field_a,
        "field_b": field_b,
        "low_time_byte": elapsed & 0xFF,
        "time": elapsed,
        "raw_cue_reference": raw_reference,
        "direct_dictionary_index": direct_index,
        "one_based_dictionary_index": one_based_index,
        "reference_rule": reference_rule,
        "resolved_dictionary_index": resolved_index,
        "reference_kind": "cue" if raw_reference > 0 else "clear_control",
    }


def _parse_legacy_autoloop_structure(data: bytes, reference_rule: str) -> dict:
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
        record_type, tick_a, tick_b, attribute_value = struct.unpack_from(
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
                "attribute_value": attribute_value,
                "attribute_value_percent": attribute_value / 0xFFFFFFFF * 100.0,
                "auxiliary": attribute_value,
                "trailer": trailer,
            }
        )
        offset += 17

    shared_block_offset = offset
    offset += POST_EVENTS_SHARED_SIZE - 1
    if offset + 8 > len(data):
        raise ValueError("missing cue dictionary")

    cue_map_version_offset = offset
    cue_map_version = _u32le(data, offset)
    if cue_map_version != 1:
        raise ValueError(
            f"cue-map version is {cue_map_version}, expected 1 at byte {offset}"
        )
    offset += 4
    cue_count_offset = offset
    cue_count = _u32le(data, offset)
    offset += 4
    cues = []
    for index in range(cue_count):
        if offset + 20 > len(data):
            raise ValueError(f"truncated cue-dictionary entry {index}")
        cues.append(
            {
                "offset": offset,
                "guid": data[offset : offset + 16].hex(),
                "cue_index": _u32le(data, offset + 16),
            }
        )
        offset += 20
    cue_indices = [entry["cue_index"] for entry in cues]
    if len(cue_indices) != len(set(cue_indices)):
        raise ValueError("cue-dictionary indices are not unique")

    if offset + 4 > len(data):
        raise ValueError("missing timeline count")
    timeline_count_offset = offset
    declared_timeline_count = _u32le(data, offset)
    offset += 4
    timeline = []
    for index in range(declared_timeline_count):
        if offset + 16 > len(data):
            raise ValueError(f"truncated timeline record {index}")
        timeline.append(_timeline_record(data, offset, reference_rule))
        offset += 16

    if len(data) - offset < TRAILER_SIZE:
        raise ValueError("missing observed 13-byte trailer")
    extra = data[offset : len(data) - TRAILER_SIZE]
    if extra:
        raise ValueError(
            f"{len(extra)} undeclared byte(s) remain between the declared timeline "
            f"and document trailer at byte {offset}"
        )

    return {
        "layout": "embedded_fixture_groups_events_shared441",
        "reference_rule": reference_rule,
        "size": len(data),
        "version": _u32le(data, 4),
        "fixture_profile_guid": data[28:44].hex(),
        "event_count_offset": EVENT_COUNT_OFFSET,
        "event_count": event_count,
        "events": events,
        "attribute_track_type": INTENSITY_TRACK_TYPE,
        "attribute_track_role": "intensity",
        "shared_block_offset": shared_block_offset,
        "shared_block_size": POST_EVENTS_SHARED_SIZE,
        "cue_map_version_offset": cue_map_version_offset,
        "cue_map_version": cue_map_version,
        "cue_count_offset": cue_count_offset,
        "cue_count": cue_count,
        "cues": cues,
        "timeline_count_offset": timeline_count_offset,
        "declared_timeline_count": declared_timeline_count,
        "continuation_timeline_count": 0,
        "timeline_count": len(timeline),
        "timeline": timeline,
        "extra_offset": offset,
        "extra_size": 0,
        "extra_hex": "",
        "trailer_offset": len(data) - TRAILER_SIZE,
        "trailer_hex": data[-TRAILER_SIZE:].hex(),
    }


def _parse_minimal_autoloop_structure(data: bytes, reference_rule: str) -> dict:
    """Parse the compact layout emitted for a newly created v3 autoloop."""
    shared_block_offset = MINIMAL_SHARED_BLOCK_OFFSET
    shared_end = shared_block_offset + POST_EVENTS_SHARED_SIZE
    if len(data) < shared_end + 4 + TRAILER_SIZE:
        raise ValueError("file is shorter than the compact autoloop prefix")
    shared_hash = hashlib.sha256(data[shared_block_offset:shared_end]).hexdigest()
    if shared_hash != OBSERVED_SHARED_BLOCK_SHA256:
        raise ValueError(
            "compact autoloop shared-table hash is not the observed v3 table"
        )

    offset = shared_end - 1
    cue_map_version_offset = offset
    cue_map_version = _u32le(data, offset)
    if cue_map_version != 1:
        raise ValueError("compact autoloop cue-map version is not 1")
    offset += 4
    cue_count_offset = offset
    cue_count = _u32le(data, offset)
    if not 1 <= cue_count <= 255:
        raise ValueError("compact autoloop cue count is outside 1..255")
    offset += 4
    cues = []
    for index in range(cue_count):
        if offset + 20 > len(data):
            raise ValueError(f"truncated compact cue-dictionary entry {index}")
        cues.append(
            {
                "offset": offset,
                "guid": data[offset : offset + 16].hex(),
                "cue_index": _u32le(data, offset + 16),
            }
        )
        offset += 20
    cue_indices = [entry["cue_index"] for entry in cues]
    if len(cue_indices) != len(set(cue_indices)):
        raise ValueError("compact cue-dictionary indices are not unique")

    if offset + 4 > len(data):
        raise ValueError("missing compact autoloop timeline count")
    timeline_count_offset = offset
    timeline_count = _u32le(data, offset)
    if timeline_count > 10000:
        raise ValueError("compact autoloop timeline count exceeds 10000")
    offset += 4
    timeline = []
    cue_index_set = set(cue_indices)
    for index in range(timeline_count):
        if offset + 16 > len(data):
            raise ValueError(f"truncated compact timeline record {index}")
        row = _timeline_record(data, offset, reference_rule)
        resolved = row["resolved_dictionary_index"]
        candidate_indices = {
            row["direct_dictionary_index"],
            row["one_based_dictionary_index"],
        } - {None}
        if (
            resolved is not None
            and resolved not in cue_index_set
            or resolved is None
            and row["raw_cue_reference"] > 0
            and not candidate_indices.intersection(cue_index_set)
        ):
            raise ValueError(
                f"compact timeline record at byte {offset} has no valid cue-index candidate"
            )
        timeline.append(row)
        offset += 16
    if len(data) - offset != TRAILER_SIZE:
        raise ValueError(
            "compact autoloop does not end with exactly one 13-byte trailer"
        )

    return {
        "layout": "compact_shared441_dictionary_timeline",
        "reference_rule": reference_rule,
        "size": len(data),
        "version": _u32le(data, 4),
        "fixture_profile_guid": None,
        "fixture_profile_source": "not_embedded_in_compact_layout",
        "prefix_size": shared_block_offset,
        "prefix_sha256": hashlib.sha256(data[:shared_block_offset]).hexdigest(),
        "event_count_offset": None,
        "event_count": 0,
        "events": [],
        "attribute_track_type": None,
        "attribute_track_role": "not_embedded_in_compact_layout",
        "shared_block_offset": shared_block_offset,
        "shared_block_size": POST_EVENTS_SHARED_SIZE,
        "cue_map_version_offset": cue_map_version_offset,
        "cue_map_version": cue_map_version,
        "cue_count_offset": cue_count_offset,
        "cue_count": cue_count,
        "cues": cues,
        "timeline_count_offset": timeline_count_offset,
        "declared_timeline_count": timeline_count,
        "continuation_timeline_count": 0,
        "timeline_count": timeline_count,
        "timeline": timeline,
        "extra_offset": offset,
        "extra_size": 0,
        "extra_hex": "",
        "trailer_offset": offset,
        "trailer_hex": data[offset:].hex(),
    }


def parse_autoloop_structure(data: bytes, reference_rule: str = "ambiguous") -> dict:
    """Parse an autoloop .ssfile.

    Cue references index a GUID/key dictionary whose physical entries are
    ``guid[16], u32le key``. Ghidra evidence for scripted playback resolves a
    positive raw reference by exact serialized-key lookup. Raw zero is the
    clear/control sentinel. Historical ``one_based`` and ``direct`` modes remain
    exposed only for old research comparisons.

    The default remains ``ambiguous`` because this is a generic structural
    research parser, not a version-locked player. The bounded scripted exporter
    must use exact-key resolution.
    """
    if data[:4] != MAGIC:
        raise ValueError("not a SoundSwitch container")
    if reference_rule not in REFERENCE_RULES:
        raise ValueError(f"unsupported reference rule: {reference_rule}")
    try:
        return _parse_legacy_autoloop_structure(data, reference_rule)
    except ValueError as legacy_error:
        try:
            return _parse_minimal_autoloop_structure(data, reference_rule)
        except ValueError as compact_error:
            raise ValueError(
                f"legacy layout: {legacy_error}; compact layout: {compact_error}"
            ) from compact_error


def summary(path: Path, parsed: dict) -> dict:
    timeline = parsed["timeline"]
    return {
        "path": str(path),
        "status": "parsed",
        "layout": parsed["layout"],
        "reference_rule": parsed["reference_rule"],
        "size": parsed["size"],
        "version": parsed["version"],
        "fixture_profile_guid": parsed["fixture_profile_guid"],
        "event_count_offset": parsed["event_count_offset"],
        "event_count": parsed["event_count"],
        "attribute_track_type": parsed["attribute_track_type"],
        "attribute_track_role": parsed["attribute_track_role"],
        "nonzero_intensity_node_count": sum(
            row["attribute_value"] != 0 for row in parsed["events"]
        ),
        "intensity_attribute_values": sorted(
            {row["attribute_value"] for row in parsed["events"]}
        ),
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
    parser.add_argument(
        "--reference-rule",
        choices=REFERENCE_RULES,
        default="ambiguous",
        help="default 'ambiguous' preserves candidates; exact_key is the "
        "scripted playback rule, while direct/one_based remain for old research comparisons",
    )
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    output = []
    for path in args.files:
        data = path.read_bytes()
        try:
            parsed = parse_autoloop_structure(data, args.reference_rule)
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
