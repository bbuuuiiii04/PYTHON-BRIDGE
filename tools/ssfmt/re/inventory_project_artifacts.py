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
            "role": "external-control mapping/recording data",
            "future_pack_action": "hash and report separately from authored lighting",
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
        output["format"] = "structured binary control mapping"
        output["magic_u32le"] = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else None
        output["version"] = None
        output["unsupported_reason"] = (
            "record framing and numeric binding fields are not decoded; printable control "
            "identifiers alone do not establish semantics"
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


def analyze(project_dir: Path) -> dict[str, Any]:
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
        "unsupported_reason": (
            ".ssa and .sspreset payload semantics and recordable numeric binding fields "
            "remain opaque; classifications are fail-closed"
        ),
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.project_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
