#!/usr/bin/env python3
"""Read-only inventory for non-timeline artifacts in a SoundSwitch project."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any


_GUID_TEXT = re.compile(
    rb"\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}"
)
_ASCII_STRING = re.compile(rb"[\x20-\x7e]{4,}")
_SCRIPT_FILENAME = re.compile(
    r"^\{([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\}\.ssfile$"
)
_AUTOLOOP_CONTROL_PATH = re.compile(
    r"^SoundSwitch\.Controls\.AutoLoopsPlayAutoloop([0-9]+)$"
)
_STATIC_OVERRIDE_CONTROL_PATH = re.compile(
    r"^SoundSwitch\.Controls\.StaticOverride([0-9]+)$"
)

_RECORDABLE_MAGIC = 0xDEADBEEF
_RECORDABLE_MAP_SIGNATURE = 0x01380308
_RECORDABLE_STRING_SIGNATURE = 0x01380305
_RECORDABLE_VECTOR_SIGNATURE = 0x01380306
_RECORDABLE_SHARED_PTR_SIGNATURE = 0x01380307
_MIDI_MESSAGE_TYPES = {0: "note", 1: "control_change", 2: "pitch_bend"}


class _RecordableReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def _take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise ValueError(f"truncated at offset {self.offset}")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def u8(self) -> int:
        return self._take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def signature(self, expected: int) -> None:
        actual = self.u32()
        if actual != expected:
            raise ValueError(
                f"signature 0x{actual:08x} at offset {self.offset - 4}; "
                f"expected 0x{expected:08x}"
            )

    def string(self) -> str:
        self.signature(_RECORDABLE_STRING_SIGNATURE)
        end = self.data.find(b"\0", self.offset)
        if end < 0:
            raise ValueError(f"unterminated string at offset {self.offset}")
        value = self.data[self.offset:end].decode("utf-8")
        self.offset = end + 1
        return value


def _bounded_count(reader: _RecordableReader, label: str) -> int:
    count = reader.u64()
    if count > 100_000:
        raise ValueError(f"implausible {label} count {count}")
    return count


def _decode_recordable_control_map(data: bytes) -> dict[str, Any] | None:
    """Decode the NamedControlMapCollections recordable used for MIDI learns.

    Other recordable files use a similar container for control registries. They
    do not have the status byte before the top-level map signature and are left
    classified separately.
    """
    if len(data) < 15 or struct.unpack_from("<I", data, 0)[0] != _RECORDABLE_MAGIC:
        return None
    if struct.unpack_from("<I", data, 7)[0] != _RECORDABLE_MAP_SIGNATURE:
        return None

    reader = _RecordableReader(data)
    reader.signature(_RECORDABLE_MAGIC)
    version = reader.u16()
    status = reader.u8()
    reader.signature(_RECORDABLE_MAP_SIGNATURE)
    device_count = _bounded_count(reader, "device")
    devices = []
    bindings = []
    for _ in range(device_count):
        device_name = reader.string()
        reader.signature(_RECORDABLE_VECTOR_SIGNATURE)
        collection_count = _bounded_count(reader, "collection")
        collections = []
        for _ in range(collection_count):
            collection_id = reader.u32()
            reader.signature(_RECORDABLE_VECTOR_SIGNATURE)
            binding_count = _bounded_count(reader, "binding")
            collection_bindings = []
            for _ in range(binding_count):
                reader.signature(_RECORDABLE_SHARED_PTR_SIGNATURE)
                message_type = reader.u8()
                data_byte = reader.u8()
                channel_zero_based = reader.u8()
                control_path = reader.string()
                enabled = reader.u8() == 1
                binding = {
                    "device_name": device_name,
                    "collection_id": collection_id,
                    "message_type": _MIDI_MESSAGE_TYPES.get(
                        message_type, f"unknown_{message_type}"
                    ),
                    "message_type_raw": message_type,
                    "data_byte": data_byte,
                    "channel_zero_based": channel_zero_based,
                    "channel_one_based": channel_zero_based + 1,
                    "control_path": control_path,
                    "enabled": enabled,
                }
                collection_bindings.append(binding)
                bindings.append(binding)
            collections.append(
                {
                    "collection_id": collection_id,
                    "bindings": collection_bindings,
                }
            )
        reader.signature(_RECORDABLE_VECTOR_SIGNATURE)
        feedback_size = _bounded_count(reader, "feedback")
        feedback = reader._take(feedback_size)
        devices.append(
            {
                "device_name": device_name,
                "collections": collections,
                "feedback_bytes_hex": feedback.hex(),
            }
        )
    reader.signature(_RECORDABLE_MAGIC)
    if reader.offset != len(data):
        raise ValueError(f"{len(data) - reader.offset} trailing bytes")
    enabled_by_event: dict[tuple[str, str, int, int], set[str]] = {}
    for binding in bindings:
        if not binding["enabled"]:
            continue
        key = (
            binding["device_name"],
            binding["message_type"],
            binding["channel_one_based"],
            binding["data_byte"],
        )
        enabled_by_event.setdefault(key, set()).add(binding["control_path"])
    collisions = [
        {
            "device_name": key[0],
            "message_type": key[1],
            "channel_one_based": key[2],
            "data_byte": key[3],
            "control_paths": sorted(control_paths),
        }
        for key, control_paths in enabled_by_event.items()
        if len(control_paths) > 1
    ]
    collisions.sort(
        key=lambda row: (
            row["device_name"],
            row["message_type"],
            row["channel_one_based"],
            row["data_byte"],
        )
    )
    return {
        "version": version,
        "status": status,
        "device_count": device_count,
        "binding_count": len(bindings),
        "devices": devices,
        "bindings": bindings,
        "enabled_event_collision_count": len(collisions),
        "enabled_event_collisions": collisions,
    }


def _decode_recordable_control_label_state(data: bytes) -> dict[str, Any] | None:
    """Decode PushButton label RGBA plus saved checkable Press/Toggle state."""
    if len(data) < 18 or struct.unpack_from("<I", data, 0)[0] != _RECORDABLE_MAGIC:
        return None
    if struct.unpack_from("<I", data, 6)[0] != _RECORDABLE_MAP_SIGNATURE:
        return None
    if len(data) >= 11 and struct.unpack_from("<I", data, 7)[0] == _RECORDABLE_MAP_SIGNATURE:
        return None

    reader = _RecordableReader(data)
    reader.signature(_RECORDABLE_MAGIC)
    version = reader.u16()
    if version != 1:
        return None
    reader.signature(_RECORDABLE_MAP_SIGNATURE)
    count = _bounded_count(reader, "control-label")
    rows = []
    for _ in range(count):
        control_path = reader.string()
        rgba = reader.u32()
        mode_raw = reader.u8()
        if mode_raw not in (0, 1):
            raise ValueError(f"invalid interaction mode {mode_raw}")
        rows.append(
            {
                "control_path": control_path,
                "label_rgba_hex": f"{rgba:08x}",
                "interaction_mode": "toggle" if mode_raw == 1 else "press",
                "interaction_mode_raw": mode_raw,
            }
        )
    reader.signature(_RECORDABLE_MAGIC)
    if reader.offset != len(data):
        raise ValueError(f"{len(data) - reader.offset} trailing bytes")
    return {"version": version, "control_count": count, "controls": rows}


def _resolve_autoloop_midi_bindings(
    artifacts: list[dict[str, Any]], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve enabled MIDI autoloop controls through catalog category order.

    SoundSwitch control slots are grouped in 32-entry category banks. The
    catalog's category-order tables, not catalog file order or display names,
    identify the selected AppLog index and therefore SSAutoLoop file number.
    """
    entries_by_index = {
        entry["app_log_index"]: entry for entry in catalog.get("entries", [])
    }
    category_rows = {
        row["category_index"]: row for row in catalog.get("category_order", [])
    }
    resolved: list[dict[str, Any]] = []
    for artifact in artifacts:
        control_map = artifact.get("control_map")
        if control_map is None:
            continue
        for binding in control_map.get("bindings", []):
            match = _AUTOLOOP_CONTROL_PATH.fullmatch(binding.get("control_path", ""))
            if (
                match is None
                or not binding.get("enabled")
                or binding.get("message_type") != "note"
            ):
                continue
            control_slot = int(match.group(1))
            category_index, category_slot = divmod(control_slot, 32)
            row: dict[str, Any] = {
                "source_relative_path": artifact["relative_path"],
                "source_sha256": artifact["sha256"],
                "device_name": binding["device_name"],
                "collection_id": binding["collection_id"],
                "midi_channel_one_based": binding["channel_one_based"],
                "midi_note": binding["data_byte"],
                "control_path": binding["control_path"],
                "control_slot": control_slot,
                "category_index": category_index,
                "category_slot": category_slot,
            }
            category = category_rows.get(category_index)
            if category is None:
                row.update(
                    {
                        "status": "unresolved",
                        "unresolved_reason": f"catalog has no category {category_index}",
                    }
                )
            elif category_slot >= len(category["app_log_indices"]):
                row.update(
                    {
                        "status": "unresolved",
                        "category": category["category"],
                        "unresolved_reason": (
                            f"category slot {category_slot} exceeds "
                            f"{len(category['app_log_indices'])} catalog entries"
                        ),
                    }
                )
            else:
                app_log_index = category["app_log_indices"][category_slot]
                entry = entries_by_index.get(app_log_index)
                if entry is None:
                    row.update(
                        {
                            "status": "unresolved",
                            "category": category["category"],
                            "app_log_index": app_log_index,
                            "unresolved_reason": "category table references a missing entry",
                        }
                    )
                else:
                    row.update(
                        {
                            "status": "resolved",
                            "category": category["category"],
                            "app_log_index": app_log_index,
                            "file_number": entry["file_number"],
                            "autoloop_file": f"SSAutoLoop{entry['file_number']}.ssfile",
                            "display_name": entry["display_name"],
                        }
                    )
            resolved.append(row)
    return sorted(
        resolved,
        key=lambda row: (
            row["device_name"],
            row["midi_channel_one_based"],
            row["midi_note"],
            row["control_path"],
        ),
    )


def _resolve_static_look_midi_bindings(
    artifacts: list[dict[str, Any]], venue_path: Path
) -> dict[str, Any]:
    """Resolve learned ``StaticOverrideN`` controls to primary Venue slot N."""
    try:
        from analyze_static_looks import parse_static_looks, primary_venue_identity

        venue_data = venue_path.read_bytes()
        venue_identity = primary_venue_identity(venue_data)
        static_looks = parse_static_looks(venue_data)
    except (ImportError, OSError, UnicodeDecodeError, ValueError) as exc:
        return {
            "status": "unsupported",
            "venue_error": str(exc),
            "binding_count": 0,
            "bindings": [],
        }

    interaction_by_path = {
        row["control_path"]: row["interaction_mode"]
        for artifact in artifacts
        for row in (artifact.get("control_label_state") or {}).get("controls", [])
    }
    rows = []
    for artifact in artifacts:
        control_map = artifact.get("control_map")
        if control_map is None:
            continue
        for binding in control_map.get("bindings", []):
            match = _STATIC_OVERRIDE_CONTROL_PATH.fullmatch(
                binding.get("control_path", "")
            )
            if match is None or not binding.get("enabled"):
                continue
            slot_index = int(match.group(1))
            row = {
                "source_relative_path": artifact["relative_path"],
                "source_sha256": artifact["sha256"],
                "device_name": binding["device_name"],
                "collection_id": binding["collection_id"],
                "message_type": binding["message_type"],
                "midi_channel_one_based": binding["channel_one_based"],
                "midi_data_byte": binding["data_byte"],
                "control_path": binding["control_path"],
                "interaction_mode": interaction_by_path.get(binding["control_path"]),
                "slot_index": slot_index,
            }
            if row["interaction_mode"] not in ("press", "toggle"):
                row.update(
                    {
                        "status": "unresolved",
                        "unresolved_reason": "saved StaticOverride interaction mode is not decoded",
                    }
                )
                rows.append(row)
                continue
            if len(static_looks) != 32:
                row.update(
                    {
                        "status": "unresolved",
                        "unresolved_reason": "primary Venue 32-slot StaticLooks collection is not decoded",
                    }
                )
            elif slot_index >= len(static_looks):
                row.update(
                    {
                        "status": "unresolved",
                        "unresolved_reason": f"static-look slot {slot_index} is outside 0..31",
                    }
                )
            else:
                look = static_looks[slot_index]
                row.update(
                    {
                        "status": "resolved",
                        "name": look["name"],
                        "fixture_count": look["fixture_count"],
                        "entry_count": look["entry_count"],
                        "groups": look["groups"],
                    }
                )
            rows.append(row)
    rows.sort(
        key=lambda row: (
            row["device_name"],
            row["midi_channel_one_based"],
            row["midi_data_byte"],
            row["control_path"],
        )
    )
    unresolved_count = sum(row["status"] != "resolved" for row in rows)
    return {
        "status": (
            "resolved"
            if venue_identity is not None and len(static_looks) == 32 and unresolved_count == 0
            else "partial_fail_closed"
        ),
        "venue_relative_path": venue_path.name,
        "venue_sha256": _sha256(venue_path.read_bytes()) if venue_path.is_file() else None,
        "primary_venue": venue_identity,
        "slot_count": len(static_looks),
        "binding_count": len(rows),
        "resolved_binding_count": len(rows) - unresolved_count,
        "unresolved_binding_count": unresolved_count,
        "bindings": rows,
    }


def _bridge_scene_binding_inventory(
    artifacts: list[dict[str, Any]],
    autoloop_bindings: list[dict[str, Any]],
    config_path: Path | None,
) -> dict[str, Any] | None:
    if config_path is None:
        return None
    data = config_path.read_bytes()
    config = json.loads(data.decode("utf-8"))
    output_name = config.get("midi_output_port")
    decoded_by_key: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for artifact in artifacts:
        control_map = artifact.get("control_map")
        if control_map is None:
            continue
        for binding in control_map.get("bindings", []):
            if not binding.get("enabled") or binding.get("message_type") != "note":
                continue
            key = (
                binding["device_name"],
                binding["channel_one_based"],
                binding["data_byte"],
            )
            decoded_by_key.setdefault(key, []).append(binding)
    autoloop_by_key = {
        (row["device_name"], row["midi_channel_one_based"], row["midi_note"]): row
        for row in autoloop_bindings
        if row["status"] == "resolved"
    }

    references: dict[str, set[str]] = {}
    default_personality = config.get("default_personality")
    personality = config.get("personalities", {}).get(default_personality, {})
    for key, value in personality.items():
        if key.endswith("_bank") and isinstance(value, list):
            for scene_name in value:
                if scene_name:
                    references.setdefault(scene_name, set()).add(
                        f"personality.{default_personality}.{key}"
                    )
        elif key.endswith("_scene") and isinstance(value, str) and value:
            references.setdefault(value, set()).add(
                f"personality.{default_personality}.{key}"
            )
    for key in (
        "emergency_scene",
        "fallback_scene",
        "startup_scene",
        "stop_scene",
        "stale_scene",
    ):
        scene_name = config.get(key)
        if scene_name:
            references.setdefault(scene_name, set()).add(key)

    scenes = []
    for scene_name, scene in sorted(config.get("scenes", {}).items()):
        midi = scene.get("midi", {})
        channel = midi.get("channel")
        note = midi.get("note")
        key = (output_name, channel, note)
        matches = decoded_by_key.get(key, [])
        autoloop = autoloop_by_key.get(key)
        scenes.append(
            {
                "scene": scene_name,
                "referenced_by": sorted(references.get(scene_name, set())),
                "midi_channel_one_based": channel,
                "midi_note": note,
                "scene_type": scene.get("scene_type"),
                "safety_class": scene.get("safety_class"),
                "status": (
                    "resolved_autoloop_binding"
                    if autoloop is not None
                    else "resolved_non_autoloop_binding"
                    if matches
                    else "no_decoded_project_binding"
                ),
                "matched_control_paths": sorted(
                    {binding["control_path"] for binding in matches}
                ),
                "autoloop_file": (
                    autoloop.get("autoloop_file") if autoloop is not None else None
                ),
                "app_log_index": (
                    autoloop.get("app_log_index") if autoloop is not None else None
                ),
            }
        )

    manual_commands = []
    for command_name, command in sorted(config.get("manual_commands", {}).items()):
        channel = command.get("channel")
        note = command.get("note")
        key = (output_name, channel, note)
        matches = decoded_by_key.get(key, [])
        autoloop = autoloop_by_key.get(key)
        manual_commands.append(
            {
                "command": command_name,
                "midi_channel_one_based": channel,
                "midi_note": note,
                "behavior": command.get("behavior"),
                "status": (
                    "resolved_autoloop_binding"
                    if autoloop is not None
                    else "resolved_non_autoloop_binding"
                    if matches
                    else "no_decoded_project_binding"
                ),
                "matched_control_paths": sorted(
                    {binding["control_path"] for binding in matches}
                ),
                "autoloop_file": (
                    autoloop.get("autoloop_file") if autoloop is not None else None
                ),
                "app_log_index": (
                    autoloop.get("app_log_index") if autoloop is not None else None
                ),
            }
        )
    return {
        "config_sha256": _sha256(data),
        "default_personality": default_personality,
        "scene_count": len(scenes),
        "referenced_scene_count": sum(bool(row["referenced_by"]) for row in scenes),
        "referenced_scene_without_project_binding_count": sum(
            bool(row["referenced_by"])
            and row["status"] == "no_decoded_project_binding"
            for row in scenes
        ),
        "scenes": scenes,
        "manual_commands": manual_commands,
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    size = len(data)
    return -sum(
        (count / size) * math.log2(count / size)
        for count in Counter(data).values()
    )


def _qt_uuid_bytes(value: str) -> bytes:
    parts = value.strip("{}").split("-")
    return (
        struct.pack("<IHH", int(parts[0], 16), int(parts[1], 16), int(parts[2], 16))
        + bytes.fromhex(parts[3] + parts[4])
    )


def _known_script_ids(project_dir: Path) -> list[str]:
    ids = []
    for path in project_dir.glob("*.ssfile"):
        match = _SCRIPT_FILENAME.match(path.name)
        if match:
            ids.append(match.group(1).upper())
    return sorted(ids)


def _known_id_references(data: bytes, ids: list[str]) -> list[dict[str, Any]]:
    references = []
    for value in ids:
        encodings = {
            "qt_uuid": _qt_uuid_bytes(value),
            "ascii_braced": f"{{{value}}}".encode(),
            "utf16le_braced": f"{{{value}}}\0".encode("utf-16le"),
        }
        for encoding, needle in encodings.items():
            offset = data.find(needle)
            if offset >= 0:
                references.append(
                    {"soundswitch_id": value, "encoding": encoding, "offset": offset}
                )
    return references


def _strings(data: bytes) -> list[dict[str, Any]]:
    return [
        {"offset": match.start(), "value": match.group().decode("ascii")}
        for match in _ASCII_STRING.finditer(data)
    ]


def _classification(relative_path: str) -> dict[str, str]:
    if relative_path == ".ssproj":
        return {
            "role": "editable project manifest",
            "future_pack_action": "read, hash, and report project ID/version",
            "current_render_requirement": "inventory metadata; not a cue renderer input",
        }
    if relative_path.endswith(".ssa"):
        return {
            "role": "opaque high-entropy track-adjacent analysis artifact",
            "future_pack_action": "hash and report; fail closed if later proven render-affecting",
            "current_render_requirement": "unknown; no decoded render field",
        }
    if relative_path.endswith(".sspreset"):
        return {
            "role": "opaque automation preset source",
            "future_pack_action": "hash and report; do not interpret without controlled diffs",
            "current_render_requirement": "unknown when automation preset is active",
        }
    if relative_path.startswith("recordable/"):
        return {
            "role": "external-control registry or MIDI-learn mapping data",
            "future_pack_action": "decode known MIDI maps; hash/report other registries separately",
            "current_render_requirement": "not required for static timeline rendering",
        }
    if relative_path == "In App Demo.mp4":
        return {
            "role": "bundled demo media",
            "future_pack_action": "ignore as authored lighting source; optionally hash/report",
            "current_render_requirement": "not required",
        }
    if relative_path == "SoundSwitchVenues.bin.backup":
        return {
            "role": "non-authoritative venue backup",
            "future_pack_action": "report/hash only; never use as current source truth",
            "current_render_requirement": "not required and must not override current Venue",
        }
    return {
        "role": "unclassified",
        "future_pack_action": "fail closed",
        "current_render_requirement": "unknown",
    }


def _describe(path: Path, project_dir: Path, script_ids: list[str]) -> dict[str, Any]:
    data = path.read_bytes()
    relative_path = str(path.relative_to(project_dir))
    strings = _strings(data) if len(data) <= 2_000_000 else []
    output: dict[str, Any] = {
        "path": str(path),
        "relative_path": relative_path,
        "size": len(data),
        "sha256": _sha256(data),
        "magic_hex": data[:16].hex(),
        "byte_entropy": round(_entropy(data), 6),
        "classification": _classification(relative_path),
        "text_guid_references": [
            {"offset": match.start(), "value": match.group().decode("ascii")}
            for match in _GUID_TEXT.finditer(data)
        ],
        "known_script_id_references": (
            _known_id_references(data, script_ids) if len(data) <= 2_000_000 else []
        ),
        "ascii_string_count": len(strings),
        "soundswitch_control_strings": [
            row for row in strings if row["value"].startswith("SoundSwitch.Controls.")
        ],
    }
    if relative_path == ".ssproj":
        manifest = json.loads(data.decode("utf-8"))
        output["format"] = "JSON"
        output["project_id"] = manifest.get("id")
        output["version"] = manifest.get("version")
    elif relative_path.startswith("recordable/"):
        output["format"] = "structured binary control registry"
        output["magic_u32le"] = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else None
        output["version"] = struct.unpack_from("<H", data, 4)[0] if len(data) >= 6 else None
        try:
            control_map = _decode_recordable_control_map(data)
        except (UnicodeDecodeError, ValueError) as exc:
            output["control_map_decode_error"] = str(exc)
            output["unsupported_reason"] = "recognized MIDI control map failed strict decoding"
        else:
            if control_map is not None:
                output["format"] = "structured binary MIDI control map"
                output["control_map"] = control_map
            else:
                try:
                    control_label_state = _decode_recordable_control_label_state(data)
                except (UnicodeDecodeError, ValueError) as exc:
                    output["control_label_state_decode_error"] = str(exc)
                    output["unsupported_reason"] = (
                        "recognized control-label registry failed strict decoding"
                    )
                else:
                    if control_label_state is not None:
                        output["format"] = "structured binary control label state map"
                        output["control_label_state"] = control_label_state
                    else:
                        output["unsupported_reason"] = (
                            "control-registry payload framing is not decoded; printable control "
                            "identifiers alone do not establish registry semantics"
                        )
    elif relative_path == "In App Demo.mp4":
        output["format"] = "ISO Base Media File"
        output["brand"] = data[8:12].decode("ascii", errors="replace") if len(data) >= 12 else None
        output["version"] = None
    elif relative_path == "SoundSwitchVenues.bin.backup":
        output["format"] = "SoundSwitch Venue binary"
        output["version"] = struct.unpack_from("<I", data, 4)[0] if len(data) >= 8 else None
    else:
        output["format"] = "opaque binary"
        output["version"] = None
        output["unsupported_reason"] = "no structurally validated parser for this artifact type"
    if relative_path.endswith(".ssa"):
        stem = path.stem.strip("{}").upper()
        output["filename_soundswitch_id"] = stem
        output["matching_script_file"] = str(project_dir / f"{{{stem}}}.ssfile")
        output["matching_script_file_exists"] = (project_dir / f"{{{stem}}}.ssfile").is_file()
    return output


def analyze(
    project_dir: Path, laser_config_path: Path | None = None
) -> dict[str, Any]:
    paths = [project_dir / ".ssproj"]
    paths.extend(sorted(project_dir.glob("*.ssa")))
    paths.extend(sorted((project_dir / "automation_presets").glob("*.sspreset")))
    paths.extend(sorted((project_dir / "recordable").glob("*.dat")))
    paths.extend(
        [
            project_dir / "In App Demo.mp4",
            project_dir / "SoundSwitchVenues.bin.backup",
        ]
    )
    paths = [path for path in paths if path.is_file()]
    script_ids = _known_script_ids(project_dir)
    current_venue = project_dir / "SoundSwitchVenues.bin"
    backup = project_dir / "SoundSwitchVenues.bin.backup"
    artifacts = [_describe(path, project_dir, script_ids) for path in paths]
    catalog_paths = [
        path
        for path in (
            project_dir / "SoundSwitchAutoLoops.bin",
            project_dir / "SoundSwitchAutoLoopsEx.bin",
        )
        if path.is_file()
    ]
    catalog_status = "not_available"
    catalog_sha256s: dict[str, str] = {}
    binding_rows: list[dict[str, Any]] = []
    catalog_error = None
    if catalog_paths:
        try:
            from parse_autoloop_catalogs import parse_catalog

            parsed_catalogs = []
            for catalog_path in catalog_paths:
                catalog_data = catalog_path.read_bytes()
                catalog_sha256s[str(catalog_path.relative_to(project_dir))] = _sha256(
                    catalog_data
                )
                parsed_catalogs.append(parse_catalog(catalog_data))
            entries_by_index: dict[int, dict[str, Any]] = {}
            for parsed in parsed_catalogs:
                for entry in parsed["entries"]:
                    existing = entries_by_index.get(entry["app_log_index"])
                    if existing is not None and existing != entry:
                        raise ValueError(
                            f"conflicting catalog entry {entry['app_log_index']}"
                        )
                    entries_by_index[entry["app_log_index"]] = entry
            catalog = {
                "entries": list(entries_by_index.values()),
                "category_order": parsed_catalogs[-1]["category_order"],
            }
            binding_rows = _resolve_autoloop_midi_bindings(artifacts, catalog)
            catalog_status = "parsed"
        except (ImportError, ValueError) as exc:
            catalog_status = "unsupported"
            catalog_error = str(exc)
    unresolved_binding_count = sum(
        row["status"] != "resolved" for row in binding_rows
    )
    static_look_bindings = _resolve_static_look_midi_bindings(
        artifacts, current_venue
    )
    bridge_inventory = _bridge_scene_binding_inventory(
        artifacts, binding_rows, laser_config_path
    )
    return {
        "path": str(project_dir),
        "status": "partial_classification",
        "version": None,
        "artifact_count": len(artifacts),
        "artifact_type_counts": dict(
            sorted(Counter(Path(item["relative_path"]).suffix or item["relative_path"] for item in artifacts).items())
        ),
        "current_venue_backup_comparison": {
            "current_path": str(current_venue),
            "backup_path": str(backup),
            "same_bytes": (
                current_venue.read_bytes() == backup.read_bytes()
                if current_venue.is_file() and backup.is_file()
                else None
            ),
            "current_sha256": _sha256(current_venue.read_bytes()) if current_venue.is_file() else None,
            "backup_sha256": _sha256(backup.read_bytes()) if backup.is_file() else None,
        },
        "autoloop_midi_selection": {
            "status": (
                "resolved"
                if catalog_status == "parsed" and unresolved_binding_count == 0
                else "partial_fail_closed"
                if catalog_status == "parsed"
                else catalog_status
            ),
            "catalog_relative_paths": [
                str(path.relative_to(project_dir)) for path in catalog_paths
            ],
            "catalog_sha256s": catalog_sha256s,
            "catalog_error": catalog_error,
            "enabled_note_binding_count": len(binding_rows),
            "resolved_binding_count": len(binding_rows) - unresolved_binding_count,
            "unresolved_binding_count": unresolved_binding_count,
            "bindings": binding_rows,
        },
        "static_look_midi_selection": static_look_bindings,
        "bridge_scene_bindings": bridge_inventory,
        "unsupported_reason": (
            ".ssa, .sspreset, and non-MIDI recordable control-registry payload semantics "
            "remain opaque; classifications are fail-closed"
        ),
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--laser-config", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(args.project_dir, args.laser_config), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
