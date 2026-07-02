"""Independent verifier for SoundSwitch static pack directories.

Verification deliberately duplicates the canonical JSON and schema checks; it
does not call exporter/compiler helpers.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .soundswitch_parity_registry import PARITY_LANES

SCHEMA_VERSION = "1.0.0"
PROJECT_UUID = "{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}"
VENUE_GUID = "b8ad2201b9e4c94696c898a7e8f6a5a9"
SOUNDSWITCH_VERSION = "2.10.3"
PRIMARY_FIXTURE_GROUP = 0x493
CONTROL_CHANNELS = frozenset((8, 9, 11))
ATTRIBUTE_FIELDS = {"channel_id", "dmx_channel", "fixture_group", "source_offset", "value"}
TIMELINE_FIELDS = {"raw_reference", "record_version", "reference_kind", "resolved_cue_guid",
                   "resolved_stored_key", "source_offset", "time"}
BOUNDARY_FIELDS = {"frame", "source_offset", "source_order", "time"}
INTENSITY_FIELDS = {"attribute_value", "enabled", "end_tick", "record_version",
                    "source_offset", "start_tick"}
STATIC_LOOK_FIELDS = {"colour_values", "end_offset", "generic_attributes", "intensity_values",
                      "name", "parity_evidence", "parity_lane", "position_values",
                      "pre_rendered_frame_ch1_ch19",
                      "record_version", "slot_index", "source_offset", "strobe_values"}
SCALAR_FIELDS = {"fixture_instance_id", "source_offset", "value"}
COLOUR_FIELDS = {"fixture_instance_id", "raw_value", "source_offset"}
POSITION_FIELDS = {"fixture_instance_id", "position_guid", "source_offset"}
CONTROL_CLASSIFICATIONS = {
    "pack_selection", "static_override", "blackout_mask", "bridge_owned_safety",
    "no_project_target", "inactive_report_only", "unsupported_fail_export",
}
BRIDGE_SCENES = (
    ("house_groove_1", 0, 32), ("house_buildup_1", 0, 64),
    ("house_drop_1", 0, 96), ("house_drop_2", 0, 97),
    ("house_drop_5", 0, 98), ("house_drop_3", 0, 99),
    ("house_drop_4", 0, 100), ("house_drop_6", 0, 101),
    ("house_drop_7", 0, 102), ("house_drop_8", 0, 103),
    ("house_drop_9", 0, 104), ("house_drop_10", 0, 105),
    ("house_drop_11", 0, 106), ("house_drop_12", 0, 107),
    ("house_drop_13", 0, 108), ("house_drop_14", 0, 109),
    ("house_drop_15", 0, 110), ("house_drop_16", 0, 111),
    ("house_breakdown_1", 0, 1), ("house_post_drop_1", 0, 41),
    ("safe_static", 1, 0), ("transition_safe_1", 1, 1),
    ("emergency_blackout", 1, 2),
)


class SoundSwitchPackVerificationError(ValueError):
    pass


def _fail(message: str) -> None:
    raise SoundSwitchPackVerificationError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SoundSwitchPackVerificationError(f"noncanonical JSON value: {exc}") from exc


def _read_json(path: Path, relative: str) -> tuple[bytes, dict[str, Any]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SoundSwitchPackVerificationError(f"cannot read {relative}: {exc}") from exc
    duplicates: list[str] = []
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in rows:
            if key in value:
                duplicates.append(key)
            value[key] = item
        return value
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SoundSwitchPackVerificationError(f"invalid JSON {relative}: {exc}") from exc
    if duplicates or not isinstance(value, dict):
        _fail(f"duplicate key or non-object root in {relative}")
    if data != _canonical(value):
        _fail(f"noncanonical JSON bytes in {relative}")
    if value.get("schema_version") != SCHEMA_VERSION:
        _fail(f"unsupported schema version in {relative}")
    return data, value


def _regular_files(root: Path) -> list[str]:
    if root.is_symlink() or not root.is_dir():
        _fail("pack root must be a real directory")
    output = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in dirs:
            if (base / name).is_symlink():
                _fail("pack symlinks are forbidden")
        for name in files:
            path = base / name
            if path.is_symlink() or not path.is_file():
                _fail("pack entries must be regular files")
            output.append(path.relative_to(root).as_posix())
    folded: dict[str, str] = {}
    for relative in output:
        old = folded.setdefault(relative.casefold(), relative)
        if old != relative:
            _fail("case-colliding pack artifact")
    return sorted(output)


def _ordered(rows: Any, key, label: str) -> None:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        _fail(f"malformed rows: {label}")
    try:
        expected = sorted(rows, key=key)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SoundSwitchPackVerificationError(f"malformed ordering key: {label}") from exc
    if rows != expected:
        _fail(f"noncanonical order: {label}")


def _validate_midi_registry(value: dict[str, Any], source_hashes: dict[str, str],
                            source_sizes: dict[str, int]) -> list[dict[str, Any]]:
    if set(value) != {"artifact_type", "schema_version", "maps"} \
            or value.get("artifact_type") != "midi_mappings":
        _fail("unknown/missing learned MIDI registry field")
    maps = value.get("maps")
    if not isinstance(maps, list) or not maps:
        _fail("learned MIDI registry is missing/empty")
    _ordered(maps, lambda row: row.get("relative_path", ""), "learned MIDI maps")
    registry: list[dict[str, Any]] = []
    for mapping in maps:
        if not isinstance(mapping, dict) or set(mapping) != {
                "relative_path", "source_sha256", "status", "version", "devices"}:
            _fail("unknown/missing learned MIDI map field")
        relative = mapping.get("relative_path")
        if not isinstance(relative, str) or not relative.startswith("recordable/") \
                or relative not in source_hashes or relative not in source_sizes \
                or not isinstance(mapping.get("source_sha256"), str) \
                or mapping.get("source_sha256") != source_hashes.get(relative):
            _fail("learned MIDI map source/hash mismatch")
        if type(mapping.get("version")) is not int or mapping["version"] != 1 \
                or type(mapping.get("status")) is not int or mapping["status"] != 1:
            _fail("unsupported learned MIDI map version/status")
        devices = mapping.get("devices")
        if not isinstance(devices, list) or not devices:
            _fail("learned MIDI device registry is empty")
        _ordered(devices, lambda row: row.get("name", ""), "learned MIDI devices")
        device_names: set[str] = set()
        binding_offsets: set[int] = set()
        for device in devices:
            if not isinstance(device, dict) or set(device) != {"name", "feedback_hex", "collections"}:
                _fail("unknown/missing learned MIDI device field")
            name = device.get("name")
            feedback = device.get("feedback_hex")
            if not isinstance(name, str) or not name or name in device_names \
                    or not isinstance(feedback, str):
                _fail("invalid/duplicate learned MIDI device")
            device_names.add(name)
            try:
                decoded_feedback = bytes.fromhex(feedback)
            except ValueError as exc:
                raise SoundSwitchPackVerificationError("invalid MIDI feedback bytes") from exc
            if decoded_feedback.hex() != feedback:
                _fail("noncanonical MIDI feedback bytes")
            collections = device.get("collections")
            if not isinstance(collections, list):
                _fail("invalid MIDI collection registry")
            _ordered(collections, lambda row: row.get("collection_id", -1), "MIDI collections")
            collection_ids: set[int] = set()
            for collection in collections:
                if not isinstance(collection, dict) or set(collection) != {"collection_id", "bindings"}:
                    _fail("unknown/missing MIDI collection field")
                collection_id = collection.get("collection_id")
                bindings = collection.get("bindings")
                if type(collection_id) is not int or collection_id < 0 \
                        or collection_id in collection_ids or not isinstance(bindings, list):
                    _fail("invalid/duplicate MIDI collection")
                collection_ids.add(collection_id)
                _ordered(bindings, lambda row: row.get("source_offset", -1), "MIDI binding source order")
                for binding in bindings:
                    if not isinstance(binding, dict) or set(binding) != {
                            "source_offset", "device_name", "collection_id", "message_type",
                            "message_type_raw", "data_byte", "channel_zero_based", "control_path",
                            "enabled"}:
                        _fail("unknown/missing learned MIDI binding field")
                    offset = binding.get("source_offset")
                    raw = binding.get("message_type_raw")
                    kind = binding.get("message_type")
                    expected_kind = {0: "note", 1: "control_change", 2: "pitch_bend"}.get(raw)
                    if (type(offset) is not int or not 0 <= offset < source_sizes[relative]
                            or offset in binding_offsets or type(raw) is not int or raw not in (0, 1, 2)
                            or kind != expected_kind or type(binding.get("enabled")) is not bool
                            or binding.get("device_name") != name
                            or binding.get("collection_id") != collection_id
                            or type(binding.get("channel_zero_based")) is not int
                            or not 0 <= binding["channel_zero_based"] <= 15
                            or type(binding.get("data_byte")) is not int
                            or not 0 <= binding["data_byte"] <= 127
                            or not isinstance(binding.get("control_path"), str)
                            or not binding["control_path"]
                            or binding["control_path"].strip() != binding["control_path"]):
                        _fail("malformed learned MIDI binding")
                    binding_offsets.add(offset)
                    registry.append({"active": binding["enabled"],
                                     "channel_zero_based": binding["channel_zero_based"],
                                     "collection_id": collection_id,
                                     "control_path": binding["control_path"],
                                     "data_byte": binding["data_byte"], "device_name": name,
                                     "message_type": kind, "source_offset": offset})
    registry.sort(key=lambda row: (row["device_name"], row["channel_zero_based"],
                                   row["data_byte"], row["control_path"], row["source_offset"]))
    return registry


def _apply_patch(frame: list[int], attributes: list[dict[str, Any]], label: str) -> None:
    if not isinstance(attributes, list) or any(not isinstance(row, dict) for row in attributes):
        _fail(f"malformed cue attributes in {label}")
    seen: set[tuple[int, int]] = set()
    for attribute in attributes:
        if set(attribute) != ATTRIBUTE_FIELDS or type(attribute.get("source_offset")) is not int:
            _fail(f"unknown/missing cue attribute field in {label}")
        group = attribute.get("fixture_group")
        channel = attribute.get("dmx_channel")
        value = attribute.get("value")
        channel_id = attribute.get("channel_id")
        if type(group) is not int or type(channel_id) is not int \
                or type(channel) is not int or not 1 <= channel <= 19 \
                or type(value) is not int or not 0 <= value <= 255:
            _fail(f"invalid/duplicate cue attribute in {label}")
        key = (group, channel_id)
        if key in seen:
            _fail(f"invalid/duplicate cue attribute in {label}")
        seen.add(key)
        if group == PRIMARY_FIXTURE_GROUP:
            frame[channel - 1] = value


def _validate_static_scalar(row: Any, label: str) -> None:
    if not isinstance(row, dict) or set(row) != SCALAR_FIELDS \
            or type(row.get("source_offset")) is not int \
            or type(row.get("fixture_instance_id")) is not int \
            or not isinstance(row.get("value"), (int, float)) \
            or isinstance(row.get("value"), bool):
        _fail(f"malformed Static Look {label} row")


def _validate_static_colour(row: Any) -> None:
    if not isinstance(row, dict) or set(row) != COLOUR_FIELDS \
            or type(row.get("source_offset")) is not int \
            or type(row.get("fixture_instance_id")) is not int \
            or not isinstance(row.get("raw_value"), str):
        _fail("malformed Static Look colour row")
    try:
        decoded = bytes.fromhex(row["raw_value"])
    except ValueError as exc:
        raise SoundSwitchPackVerificationError("invalid Static Look colour raw_value") from exc
    if decoded.hex() != row["raw_value"]:
        _fail("noncanonical Static Look colour raw_value")


def _validate_static_position(row: Any) -> None:
    if not isinstance(row, dict) or set(row) != POSITION_FIELDS \
            or type(row.get("source_offset")) is not int \
            or type(row.get("fixture_instance_id")) is not int \
            or not isinstance(row.get("position_guid"), str):
        _fail("malformed Static Look position row")


def _validate_parity(row: Any, label: str) -> None:
    if not isinstance(row, dict):
        _fail(f"malformed parity object for {label}")
    lane = row.get("parity_lane")
    evidence = row.get("parity_evidence")
    if lane not in PARITY_LANES or not isinstance(evidence, dict):
        _fail(f"malformed parity lane for {label}")
    for key, value in evidence.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, bool)) and value is not None:
            _fail(f"unsanitized parity evidence for {label}")


def _validate_document(doc: Any, expected_path: str,
                       cue_patches: dict[str, list[dict[str, Any]]],
                       source_hashes: dict[str, str], *, active: bool = True) -> set[str]:
    if not isinstance(doc, dict):
        _fail(f"malformed document object for {expected_path}")
    if doc.get("relative_path") != expected_path:
        _fail(f"document identity mismatch for {expected_path}")
    if doc.get("source_sha256") != source_hashes.get(expected_path):
        _fail(f"source hash mismatch for {expected_path}")
    if active and doc.get("fixture_profile_guid") != VENUE_GUID:
        _fail(f"profile mismatch for active document {expected_path}")
    timeline = doc.get("timeline")
    boundaries = doc.get("pre_rendered_boundaries")
    _validate_parity(doc, expected_path)
    parity_lane = doc.get("parity_lane")
    if not isinstance(timeline, list) or not isinstance(boundaries, list):
        _fail(f"timeline/boundary count mismatch for {expected_path}")
    if any(not isinstance(row, dict) for row in timeline) or any(
            not isinstance(row, dict) for row in boundaries):
        _fail(f"malformed timeline/boundary row for {expected_path}")
    if any(set(row) != TIMELINE_FIELDS for row in timeline) or any(
            set(row) != BOUNDARY_FIELDS for row in boundaries):
        _fail(f"unknown/missing timeline/boundary field for {expected_path}")
    render_status = doc.get("pre_render_status")
    oracle_rendered = render_status == "oracle_rendered"
    if active and (len(timeline) != len(boundaries)
                   or render_status not in ("rendered", "oracle_rendered")):
        _fail(f"active document is not completely pre-rendered: {expected_path}")
    if not active and boundaries and len(timeline) != len(boundaries):
        _fail(f"partial inactive boundary render: {expected_path}")
    offsets = [row.get("source_offset") for row in timeline]
    if any(type(offset) is not int for offset in offsets) \
            or offsets != sorted(offsets) or len(offsets) != len(set(offsets)):
        _fail(f"noncanonical timeline source order for {expected_path}")
    refs: set[str] = set()
    recomputed = [0] * 19
    for index, row in enumerate(timeline):
        kind = row.get("reference_kind")
        guid = row.get("resolved_cue_guid")
        raw = row.get("raw_reference")
        stored = row.get("resolved_stored_key")
        if type(row.get("time")) is not int or type(row.get("source_offset")) is not int \
                or type(raw) is not int or type(row.get("record_version")) is not int \
                or (stored is not None and type(stored) is not int):
            _fail(f"malformed timeline primitive for {expected_path}")
        if kind == "clear_control":
            if raw != 0 or stored is not None or guid is not None:
                _fail(f"invalid clear reference for {expected_path}")
            recomputed = [value if channel + 1 in CONTROL_CHANNELS else 0
                          for channel, value in enumerate(recomputed)]
        elif kind == "cue":
            if not isinstance(raw, int) or raw <= 0 or stored != raw:
                _fail(f"unresolved/stale positive reference for {expected_path}")
            if guid is None:
                if parity_lane != "unverified_parity":
                    _fail(f"unresolved positive reference is not unverified for {expected_path}")
            elif isinstance(guid, str) and guid in cue_patches:
                refs.add(guid.lower())
                _apply_patch(recomputed, cue_patches[guid], expected_path)
            elif parity_lane != "unverified_parity":
                _fail(f"stale positive reference is not unverified for {expected_path}")
        else:
            _fail(f"unknown reference semantics for {expected_path}")
        if boundaries:
            boundary = boundaries[index]
            if type(boundary.get("source_order")) is not int \
                    or type(boundary.get("source_offset")) is not int \
                    or type(boundary.get("time")) is not int:
                _fail(f"malformed boundary primitive for {expected_path}")
            if boundary.get("source_order") != index or boundary.get("source_offset") != row.get("source_offset") \
                    or boundary.get("time") != row.get("time"):
                _fail(f"boundary provenance mismatch for {expected_path}")
            frame = boundary.get("frame")
            if not isinstance(frame, list) or len(frame) != 19 or any(
                    not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255
                    for value in frame):
                _fail(f"invalid pre-rendered frame for {expected_path}")
            if frame != recomputed and not oracle_rendered:
                _fail(f"pre-rendered boundary semantic mismatch for {expected_path}")
    intensity_nodes = doc.get("intensity_nodes", [])
    if not isinstance(intensity_nodes, list) or any(
            not isinstance(node, dict) for node in intensity_nodes):
        _fail(f"malformed intensity nodes for {expected_path}")
    for node in intensity_nodes:
        if set(node) != INTENSITY_FIELDS \
                or any(type(node.get(key)) is not int for key in (
                    "source_offset", "record_version", "start_tick", "end_tick", "attribute_value")) \
                or type(node.get("enabled")) is not bool:
            _fail(f"malformed intensity node for {expected_path}")
    return refs


def verify_pack(
    pack: str | os.PathLike[str],
    *,
    source_project: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    root = Path(pack)
    files = _regular_files(root)
    if "manifest.json" not in files:
        _fail("manifest.json is missing")
    manifest_bytes, manifest = _read_json(root / "manifest.json", "manifest.json")
    if manifest.get("artifact_type") != "manifest":
        _fail("manifest artifact type mismatch")
    project = manifest.get("project", {})
    boundary = manifest.get("supported_boundary", {})
    if not isinstance(project, dict) or not isinstance(boundary, dict):
        _fail("malformed manifest project/supported boundary")
    if project.get("project_uuid") != PROJECT_UUID or boundary.get("project_uuid") != PROJECT_UUID:
        _fail("canonical project UUID mismatch")
    if project.get("venue_guid") != VENUE_GUID or boundary.get("fixture_profile_guid") != VENUE_GUID:
        _fail("Venue/profile mismatch")
    if project.get("soundswitch_version") != SOUNDSWITCH_VERSION \
            or boundary.get("soundswitch_version") != SOUNDSWITCH_VERSION:
        _fail("SoundSwitch version mismatch")
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, list):
        _fail("artifact hash table is missing")
    _ordered(hashes, lambda row: row.get("path", ""), "artifact hashes")
    declared = [row.get("path") for row in hashes]
    if any(not isinstance(path, str) for path in declared):
        _fail("malformed artifact hash path")
    if files != sorted(["manifest.json", *declared]):
        _fail("missing or extra artifact")
    values: dict[str, dict[str, Any]] = {"manifest.json": manifest}
    for row in hashes:
        relative = row.get("path")
        if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
            _fail("unsafe artifact path")
        data, value = _read_json(root / relative, relative)
        if len(data) != row.get("size") or _sha(data) != row.get("sha256"):
            _fail(f"artifact hash/size mismatch: {relative}")
        values[relative] = value

    required = {"fixture_profile.json", "venue_cues.json", "static_looks.json",
                "midi_mappings.json", "selection_map.json", "track_map.json", "import_report.json"}
    if not required.issubset(values):
        _fail("required pack artifact missing")
    source_rows = manifest.get("source_inventory")
    if not isinstance(source_rows, list):
        _fail("source inventory missing")
    _ordered(source_rows, lambda row: row.get("path", ""), "source inventory")
    if any(not isinstance(row.get("path"), str) for row in source_rows):
        _fail("invalid source inventory path")
    source_hashes = {row.get("path"): row.get("sha256") for row in source_rows}
    source_sizes = {row.get("path"): row.get("size") for row in source_rows}
    if len(source_hashes) != len(source_rows) or any(
            not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts
            for path in source_hashes):
        _fail("invalid source inventory")
    if source_project is not None:
        project_root = Path(source_project).expanduser()
        actual = {}
        for directory, dirs, names in os.walk(project_root, followlinks=False):
            base = Path(directory)
            if any((base / name).is_symlink() for name in (*dirs, *names)):
                _fail("source project symlink")
            for name in names:
                path = base / name
                relative = path.relative_to(project_root).as_posix()
                data = path.read_bytes()
                actual[relative] = (len(data), _sha(data))
        expected = {row["path"]: (row["size"], row["sha256"]) for row in source_rows}
        if actual != expected:
            _fail("source project drift/mismatch")

    registry_bindings = _validate_midi_registry(
        values["midi_mappings.json"], source_hashes, source_sizes)

    profile = values["fixture_profile.json"]
    channels = profile.get("channels")
    if profile.get("fixture_profile_guid") != VENUE_GUID or profile.get("channel_span") != "CH1-CH19" \
            or profile.get("has_intensity_channel") is not False or not isinstance(channels, list) \
            or len(channels) != 19 or any(not isinstance(row, dict) for row in channels):
        _fail("fixture profile contents mismatch")
    venue = values["venue_cues.json"]
    records = venue.get("records", [])
    _ordered(records, lambda row: row.get("source_offset", -1), "Venue cue records")
    render = [row for row in records if row.get("record_kind") == "fixture_payload"]
    tails = [row for row in records if row.get("record_kind") == "minimal_default_catalog_tail"]
    venue_counts = (len(render), len(tails), len(records))
    if len(render) + len(tails) != len(records):
        _fail("unsupported Venue cue record kind")
    if not render:
        _fail("Venue cue split has no render-bearing cues")
    if (venue.get("render_cue_count"), venue.get("catalog_tail_count"),
            venue.get("total_record_count")) != venue_counts:
        _fail("Venue count split mismatch")
    cue_guids = [row.get("cue_guid") for row in records]
    if any(not isinstance(guid, str) or re.fullmatch(r"[0-9a-f]{32}", guid) is None
           for guid in cue_guids) or len(set(cue_guids)) != len(cue_guids):
        _fail("Venue render/catalog-tail cue GUIDs must be valid and globally unique")
    if any(row.get("render_bearing") is not True for row in render):
        _fail("fixture-payload Venue cues must remain render-bearing")
    if any(row.get("render_bearing") is not False or row.get("attributes") for row in tails):
        _fail("catalog-tail must remain distinct and non-render-bearing")
    cue_patches = {row.get("cue_guid"): row.get("attributes") for row in render}
    if len(cue_patches) != len(render) or any(not isinstance(rows, list) for rows in cue_patches.values()):
        _fail("duplicate Venue cue GUID")
    for row in render:
        _apply_patch([0] * 19, row["attributes"], f"Venue cue {row.get('cue_guid')}")
    looks = values["static_looks.json"].get("records", [])
    _ordered(looks, lambda row: row.get("slot_index", -1), "Static Look records")
    if values["static_looks.json"].get("count") != 32 or [row.get("slot_index") for row in looks] != list(range(32)):
        _fail("Static Look count/order mismatch")
    for row in looks:
        if set(row) != STATIC_LOOK_FIELDS or type(row.get("slot_index")) is not int \
                or type(row.get("record_version")) is not int \
                or type(row.get("source_offset")) is not int \
                or type(row.get("end_offset")) is not int \
                or not isinstance(row.get("name"), str):
            _fail("malformed Static Look primitive/field schema")
        _validate_parity(row, f"Static Look {row.get('slot_index')}")
        frame = row.get("pre_rendered_frame_ch1_ch19")
        if row.get("record_version") != 5 or not isinstance(frame, list) or len(frame) != 19 \
                or any(type(value) is not int or not 0 <= value <= 255 for value in frame):
            _fail("invalid Static Look record")
        recomputed = [0] * 19
        attributes = row.get("generic_attributes")
        if not isinstance(attributes, list):
            _fail("invalid Static Look attribute map")
        _apply_patch(recomputed, attributes, f"Static Look {row.get('slot_index')}")
        if frame != recomputed:
            _fail("pre-rendered Static Look semantic mismatch")
        intensity_values = row.get("intensity_values")
        strobe_values = row.get("strobe_values")
        colour_values = row.get("colour_values")
        position_values = row.get("position_values")
        if any(not isinstance(rows, list) for rows in (
                intensity_values, strobe_values, colour_values, position_values)):
            _fail("malformed Static Look retained-value container")
        for scalar in intensity_values:
            _validate_static_scalar(scalar, "intensity")
        for scalar in strobe_values:
            _validate_static_scalar(scalar, "strobe")
        for colour in colour_values:
            _validate_static_colour(colour)
        for position in position_values:
            _validate_static_position(position)

    track = values["track_map.json"]
    inventory = track.get("scripted_inventory", [])
    track_records = track.get("records", [])
    if not isinstance(inventory, list) or not isinstance(track_records, list):
        _fail("scripted inventory/track map missing")
    _ordered(inventory, lambda row: row.get("soundswitch_id", ""), "scripted inventory")
    inventory_fields = {"active_existing_path", "fixture_profile_guid", "relative_path",
                        "soundswitch_id", "status", "track_map_mapping_count"}
    inventory_by_ssid: dict[str, dict[str, Any]] = {}
    mapped_counts: dict[str, int] = {}
    for record in track_records:
        if not isinstance(record, dict) or not isinstance(record.get("soundswitch_id"), str):
            _fail("malformed scripted track-map row")
        normalized = record["soundswitch_id"].upper()
        mapped_counts[normalized] = mapped_counts.get(normalized, 0) + 1
    for row in inventory:
        if not isinstance(row, dict) or set(row) != inventory_fields:
            _fail("unknown/missing scripted inventory field")
        ssid = row.get("soundswitch_id")
        if not isinstance(ssid, str) or re.fullmatch(r"[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}", ssid) is None \
                or row.get("relative_path") != "{" + ssid + "}.ssfile" \
                or type(row.get("active_existing_path")) is not bool \
                or type(row.get("track_map_mapping_count")) is not int \
                or row.get("track_map_mapping_count") != mapped_counts.get(ssid, 0) \
                or ssid in inventory_by_ssid:
            _fail("scripted inventory does not reconcile to track map")
        inventory_by_ssid[ssid] = row
    active_scripts = {row["relative_path"] for row in inventory
                      if row["active_existing_path"]}

    autoloop_paths = sorted(path for path in values if re.fullmatch(r"autoloops/[1-9][0-9]*\.json", path))
    script_paths = sorted(path for path in values if re.fullmatch(r"scripted/[0-9a-f-]{36}\.json", path))
    if {Path(path).stem.upper() for path in script_paths} != set(inventory_by_ssid):
        _fail("scripted inventory/artifact identity mismatch")
    refs_by_source: dict[str, set[str]] = {}
    for artifact in autoloop_paths:
        doc = values[artifact].get("document")
        expected = f"SSAutoLoop{Path(artifact).stem}.ssfile"
        refs_by_source[expected] = _validate_document(doc, expected, cue_patches, source_hashes)
    parsed_scripted = 0
    for artifact in script_paths:
        row = values[artifact]
        classification = row.get("classification", {})
        expected_ssid = Path(artifact).stem.upper()
        if not isinstance(classification, dict):
            _fail(f"malformed scripted classification: {artifact}")
        if classification.get("soundswitch_id") != expected_ssid:
            _fail("scripted normalized SSID mismatch")
        expected_path = "{" + expected_ssid + "}.ssfile"
        inventory_row = inventory_by_ssid[expected_ssid]
        expected_classification = {key: value for key, value in inventory_row.items()
                                   if key != "active_existing_path"}
        if classification != expected_classification:
            _fail("scripted artifact classification does not reconcile to active inventory")
        active = inventory_row["active_existing_path"]
        doc = row.get("document")
        if doc is None:
            if row.get("unsupported_inactive") is not True or active \
                    or classification.get("status") == "supported_mapped_primary":
                _fail("unsupported active scripted row")
        else:
            parsed_scripted += 1
            if row.get("unsupported_inactive") is not False:
                _fail("renderable scripted artifact has unsupported marker")
            if active and (classification.get("status") != "supported_mapped_primary"
                           or classification.get("fixture_profile_guid") != VENUE_GUID
                           or classification.get("track_map_mapping_count", 0) <= 0):
                _fail("active scripted inventory is unsupported or non-renderable")
            refs_by_source[expected_path] = _validate_document(
                doc, expected_path, cue_patches, source_hashes, active=active)

    selection = values["selection_map.json"]
    controls = selection.get("learned_controls", [])
    _ordered(controls, lambda row: (row.get("device_name", ""), row.get("channel_zero_based", -1),
                                    row.get("data_byte", -1), row.get("control_path", ""),
                                    row.get("source_offset", -1)), "learned controls")
    selection_registry = [{key: row.get(key) for key in (
        "active", "channel_zero_based", "collection_id", "control_path", "data_byte",
        "device_name", "message_type", "source_offset")} for row in controls]
    if selection_registry != registry_bindings:
        _fail("selection map does not exactly reconcile to learned MIDI registry")
    policy = selection.get("classification_policy")
    if not isinstance(policy, dict) or set(policy) != CONTROL_CLASSIFICATIONS:
        _fail("F-3 classification policy is incomplete")
    for row in controls:
        if not row.get("active") or row.get("target_kind") == "non_render":
            expected_class = "inactive_report_only"
        elif row.get("device_name") == "IAC Driver Bus 1" \
                and row.get("channel_zero_based") == 0 \
                and row.get("data_byte") == 0 \
                and row.get("message_type") == "note":
            expected_class = "blackout_mask"
        elif row.get("target_kind") == "static_look":
            expected_class = "static_override"
        else:
            expected_class = "pack_selection"
        if row.get("control_classification") != expected_class:
            _fail("learned control has incorrect F-3 classification")
        if row.get("target_kind") == "static_look":
            if row.get("interaction_mode") not in ("press", "toggle"):
                _fail("static override interaction mode is missing or invalid")
        elif "interaction_mode" in row:
            _fail("non-static learned control carries interaction mode")
    active_render = [row for row in controls if row.get("active") and row.get("target_kind") in ("autoloop", "static_look")]
    if any(row.get("message_type") != "note" for row in active_render):
        _fail("unsupported active message semantics")
    if any(not isinstance(row.get("target_identity"), str) for row in active_render):
        _fail("active selection has malformed target identity")
    iac = [row for row in active_render if row.get("device_name") == "IAC Driver Bus 1" and row.get("target_kind") == "autoloop"]
    ddj = [row for row in active_render if row.get("device_name") == "DDJ-800" and row.get("target_kind") == "static_look"]
    for row in ddj:
        if type(row.get("target_index")) is not int or not 0 <= row["target_index"] < len(looks):
            _fail("active DDJ Static Override target mismatch")
    if selection.get("iac_selections") != iac or selection.get("ddj_static_overrides") != ddj:
        _fail("explicit IAC/DDJ crosswalk mismatch")
    seen_static_slots: set[tuple[Any, Any]] = set()
    seen_events: set[tuple[Any, Any, Any, Any]] = set()
    for row in controls:
        if not row.get("active"):
            continue
        event_key = (row.get("device_name"), row.get("message_type"),
                     row.get("channel_zero_based"), row.get("data_byte"))
        if event_key in seen_events:
            _fail("duplicate active learned controller event")
        seen_events.add(event_key)
        if row.get("control_classification") != "static_override":
            continue
        slot = row.get("target_index")
        if row.get("target_kind") != "static_look" or type(slot) is not int or not 0 <= slot <= 31:
            _fail("invalid static_override controller target")
        owner = (row.get("device_name"), slot)
        if owner in seen_static_slots:
            _fail("duplicate active static_override slot ownership")
        seen_static_slots.add(owner)
    scenes = selection.get("bridge_scenes", [])
    iac_note_by_event = {
        (row.get("channel_zero_based"), row.get("data_byte")): row for row in controls
        if row.get("active")
        and row.get("device_name") == "IAC Driver Bus 1"
        and row.get("message_type") == "note"
    }
    expected_scenes = []
    for name, channel, note in BRIDGE_SCENES:
        target = iac_note_by_event.get((channel, note))
        classification = ("inactive_report_only" if name == "house_post_drop_1" else
                          "pack_selection" if target else
                          "bridge_owned_safety" if channel == 1 and note in (0, 1, 2)
                          else "no_project_target")
        expected_scenes.append({"channel_zero_based": channel,
                                "control_classification": classification,
                                "data_byte": note, "policy_name": name,
                                "resolution": "project_target" if target else "no_project_target",
                                "target_identity": target.get("target_identity") if target else None,
                                "target_kind": target.get("target_kind") if target else None})
    if scenes != expected_scenes:
        _fail("bridge scene F-3 crosswalk mismatch")
    for scene in scenes:
        if scene.get("resolution") == "project_target" \
                and scene.get("control_classification") != "pack_selection":
            _fail("project-target bridge scene is not pack_selection: "
                  f"{scene.get('policy_name')}")
    autoloop_identities = {f"SSAutoLoop{Path(path).stem}.ssfile" for path in autoloop_paths}
    active_loop_paths = {row.get("target_identity") for row in iac}
    if not active_loop_paths:
        _fail("bridge scene crosswalk has no project targets")
    if not active_loop_paths.issubset(autoloop_identities):
        _fail("active IAC selection references a missing Autoloop")
    crosswalk_targets = {scene.get("target_identity") for scene in scenes
                         if scene.get("resolution") == "project_target"}
    if not crosswalk_targets:
        _fail("bridge scene crosswalk has no project targets")
    if not crosswalk_targets.issubset(autoloop_identities):
        _fail("bridge scene crosswalk references a missing Autoloop")
    blackout = iac_note_by_event.get((0, 0))
    expected_blackout = {"channel_zero_based": 0, "control_classification": "blackout_mask",
                         "data_byte": 0, "resolution": "project_target" if blackout else "no_project_target",
                         "target_identity": blackout.get("target_identity") if blackout else None}
    if selection.get("manual_blackout") != expected_blackout:
        _fail("manual blackout F-3 crosswalk mismatch")
    no_targets = selection.get("no_target_policy_inputs")
    if not isinstance(no_targets, list) or any(not isinstance(row, dict) for row in no_targets) \
            or any(
            row.get("control_classification") != "no_project_target" for row in no_targets):
        _fail("no-target policy classification mismatch")

    union = sorted(set().union(*(refs_by_source.get(path, set())
                                for path in active_loop_paths | active_scripts)))
    union_sha = _sha("\n".join(union).encode("ascii"))
    declared_union = manifest.get("active_cue_union", {})
    if declared_union != {"count": len(union), "sha256": union_sha}:
        _fail("active-cue union count/hash drift")
    lane_values = [str(row.get("parity_lane", "unverified_parity")) for row in looks]
    for artifact in autoloop_paths:
        doc = values[artifact].get("document")
        if isinstance(doc, dict):
            lane_values.append(str(doc.get("parity_lane", "unverified_parity")))
    for artifact in script_paths:
        doc = values[artifact].get("document")
        if isinstance(doc, dict):
            lane_values.append(str(doc.get("parity_lane", "unverified_parity")))
    expected_lanes = {lane: lane_values.count(lane) for lane in sorted(PARITY_LANES)}
    if manifest.get("parity_lanes") != expected_lanes:
        _fail("parity lane summary mismatch")
    totals = manifest.get("totals", {})
    if not isinstance(totals, dict):
        _fail("malformed manifest totals")
    expected_totals = {"render_cues": len(render), "catalog_tail_records": len(tails),
                       "total_venue_records": len(records), "static_looks": len(looks),
                       "total_autoloops": len(autoloop_paths),
                       "scripted_inventory": len(inventory),
                       "parsed_scripted": parsed_scripted,
                       "active_existing_path_scripted": len(active_scripts),
                       "iac_autoloop_bindings": len(iac), "ddj_static_overrides": len(ddj),
                       "active_cue_union": len(union), "learned_mappings": len(registry_bindings)}
    if totals != expected_totals:
        _fail("manifest totals mismatch")
    return {"manifest_sha256": _sha(manifest_bytes), "artifact_count": len(files),
            "active_cue_union_sha256": union_sha, "verified": True}


__all__ = ["SoundSwitchPackVerificationError", "verify_pack"]
