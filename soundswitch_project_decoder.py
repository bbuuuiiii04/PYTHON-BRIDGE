"""Strict, read-only decoder for the pinned SoundSwitch 2.10.3 project.

The module intentionally has no dependency on ``tools/ssfmt/re``.  Files are
inventoried and hashed before semantic decoding, then re-statted and re-hashed
before a result is returned.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import struct
from pathlib import Path
from typing import Any, Callable

from .soundswitch_pack_models import (
    AttributeCue,
    AutoloopCatalog,
    AutoloopCatalogEntry,
    AutoloopCategory,
    ControlLabelState,
    CueAttribute,
    CueDictionaryEntry,
    DecodedSoundSwitchProject,
    FixtureChannel,
    IntensityNode,
    LearnedMidiMap,
    LightingDocument,
    MidiBinding,
    MidiCollection,
    MidiDevice,
    NoTargetPolicyInput,
    ProjectIdentity,
    ResolvedControlBinding,
    ScriptedTrackClassification,
    SourceDiagnostic,
    SourceFile,
    StaticColourValue,
    StaticLook,
    StaticPositionValue,
    StaticScalarValue,
    TimelineRecord,
    TrackMapRecord,
)

CANONICAL_PROJECT_UUID = "{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}"
CANONICAL_SOUNDSWITCH_VERSION = "2.10.3"
CANONICAL_CONTAINER_VERSION = 3
CANONICAL_VENUE_GUID = "b8ad2201b9e4c94696c898a7e8f6a5a9"
_MAGIC = b"\xaa\xaa\x09\x55"
_TRAILER_SIZE = 10
_MAX_COUNT = 100_000
_MAX_STRING_UNITS = 32_768
_CHANNEL_IDS = (82, 83, 84, 85, *range(256, 271))
_CHANNEL_BY_ID = {value: index + 1 for index, value in enumerate(_CHANNEL_IDS)}
_FIXTURE_GROUPS = frozenset((0x493, 0x494, 0x496, 0x497))
_SHARED_441_HASH = "ef84f0902fac69c8836cab500cee88b61b71ce13f3bf544d8c3f9ecfb6e73fd1"
_SCRIPT_NAME = re.compile(
    r"^\{([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\}\.ssfile$"
)
_AUTOLOOP_NAME = re.compile(r"^SSAutoLoop([1-9][0-9]*)\.ssfile$")
_AUTOLOOP_CONTROL = re.compile(r"^SoundSwitch\.Controls\.AutoLoopsPlayAutoloop([0-9]+)$")
_STATIC_CONTROL = re.compile(r"^SoundSwitch\.Controls\.StaticOverride([0-9]+)$")
_TRACK_MAPPING_PREFIX = b"\x04\x00\x00\x00\x01"
_AUDIO_SUFFIXES = frozenset(
    (".aac", ".aif", ".aiff", ".alac", ".flac", ".m4a", ".mp3", ".mp4",
     ".ogg", ".opus", ".wav", ".wma")
)


class SoundSwitchDecodeError(ValueError):
    """A source cannot be decoded inside the pinned product boundary."""

    def __init__(
        self, code: str, message: str, *, relative_path: str = "", offset: int | None = None
    ) -> None:
        self.code = code
        self.relative_path = relative_path
        self.offset = offset
        location = relative_path or "project"
        if offset is not None:
            location += f":{offset}"
        super().__init__(f"{code} [{location}]: {message}")


def _fail(code: str, message: str, path: str = "", offset: int | None = None) -> None:
    raise SoundSwitchDecodeError(code, message, relative_path=path, offset=offset)


def _u32(data: bytes, offset: int, path: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        _fail("bounds", "u32 is outside the source", path, offset)
    return struct.unpack_from("<I", data, offset)[0]


def _i32(data: bytes, offset: int, path: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        _fail("bounds", "i32 is outside the source", path, offset)
    return struct.unpack_from("<i", data, offset)[0]


def _bounded_count(value: int, label: str, path: str, offset: int, limit: int = _MAX_COUNT) -> int:
    if value > limit:
        _fail("count_bounds", f"{label} count {value} exceeds {limit}", path, offset)
    return value


def _caf_string(data: bytes, offset: int, path: str, *, ascii_only: bool = False) -> tuple[str, int]:
    if offset + 8 > len(data):
        _fail("string_bounds", "missing CAF string header", path, offset)
    encoding, units = struct.unpack_from("<II", data, offset)
    if encoding != 1 or not 1 <= units <= _MAX_STRING_UNITS:
        _fail("string_format", f"invalid CAF string encoding/count {encoding}/{units}", path, offset)
    end = offset + 8 + units * 2
    if end > len(data):
        _fail("string_bounds", "CAF string extends beyond source", path, offset)
    try:
        decoded = data[offset + 8:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise SoundSwitchDecodeError("string_format", "invalid UTF-16LE", relative_path=path,
                                     offset=offset) from exc
    if not decoded.endswith("\0") or "\0" in decoded[:-1]:
        _fail("string_format", "CAF string must contain exactly one terminal NUL", path, offset)
    value = decoded[:-1]
    if ascii_only and any(not 32 <= ord(char) < 127 for char in value):
        _fail("string_format", "bounded source name contains non-ASCII text", path, offset)
    return value, end


def _plain_utf16_string(data: bytes, offset: int, path: str) -> tuple[str, int]:
    units = _bounded_count(_u32(data, offset, path), "UTF-16", path, offset, _MAX_STRING_UNITS)
    if units < 1:
        _fail("string_format", "UTF-16 string has zero length", path, offset)
    end = offset + 4 + units * 2
    if end > len(data):
        _fail("string_bounds", "UTF-16 string extends beyond source", path, offset)
    try:
        decoded = data[offset + 4:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise SoundSwitchDecodeError("string_format", "invalid UTF-16LE", relative_path=path,
                                     offset=offset) from exc
    if not decoded.endswith("\0") or "\0" in decoded[:-1]:
        _fail("string_format", "UTF-16 string must contain exactly one terminal NUL", path, offset)
    return decoded[:-1], end


def _json_no_duplicates(data: bytes, path: str) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in rows:
            if key in output:
                _fail("duplicate_key", f"duplicate JSON key {key!r}", path)
            output[key] = value
        return output

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SoundSwitchDecodeError("manifest", "invalid UTF-8 JSON manifest",
                                     relative_path=path) from exc
    if not isinstance(value, dict):
        _fail("manifest", "project manifest must be an object", path)
    return value


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_file(path: Path, relative_path: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SoundSwitchDecodeError("source_read", str(exc), relative_path=relative_path) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail("source_type", "source entry is not a regular file", relative_path)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read()
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ) or len(data) != after.st_size:
        _fail("source_drift", "source changed while being read", relative_path)
    return data, after


def _snapshot_tree(root: Path) -> tuple[tuple[SourceFile, ...], dict[str, bytes]]:
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise SoundSwitchDecodeError("source_root", str(exc)) from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        _fail("source_root", "project root must be a real directory, not a symlink")
    entries: list[tuple[str, Path]] = []
    pending = [("", root)]
    while pending:
        prefix, directory = pending.pop()
        try:
            children = list(os.scandir(directory))
        except OSError as exc:
            raise SoundSwitchDecodeError("source_read", str(exc), relative_path=prefix) from exc
        for child in children:
            relative = f"{prefix}/{child.name}" if prefix else child.name
            if child.is_symlink():
                _fail("symlink", "symlinks are forbidden in a source project", relative)
            if child.is_dir(follow_symlinks=False):
                pending.append((relative, Path(child.path)))
            elif child.is_file(follow_symlinks=False):
                entries.append((relative, Path(child.path)))
            else:
                _fail("source_type", "non-file project entry is unsupported", relative)
    folded: dict[str, str] = {}
    for relative, _ in entries:
        key = relative.casefold()
        if key in folded and folded[key] != relative:
            _fail("case_collision", f"case-colliding paths {folded[key]!r} and {relative!r}")
        folded[key] = relative
    inventory: list[SourceFile] = []
    blobs: dict[str, bytes] = {}
    for relative, path in sorted(entries):
        data, metadata = _read_regular_file(path, relative)
        blobs[relative] = data
        inventory.append(SourceFile(relative, len(data), _hash(data), metadata.st_mtime_ns,
                                    stat.S_IMODE(metadata.st_mode)))
    return tuple(inventory), blobs


def _preflight_identity(root: Path) -> tuple[ProjectIdentity, tuple[SourceFile, SourceFile]]:
    """Read only the two identity sources before traversing the project tree."""
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise SoundSwitchDecodeError("source_identity", str(exc)) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("source_identity", "project root must be a real directory")
    blobs: dict[str, bytes] = {}
    fingerprints = []
    for relative in (".ssproj", "SoundSwitchVenues.bin"):
        try:
            data, file_stat = _read_regular_file(root / relative, relative)
        except SoundSwitchDecodeError as exc:
            raise SoundSwitchDecodeError("source_identity", str(exc), relative_path=relative) from exc
        blobs[relative] = data
        fingerprints.append(SourceFile(relative, len(data), _hash(data), file_stat.st_mtime_ns,
                                       stat.S_IMODE(file_stat.st_mode)))
    return _identity_gate(blobs), (fingerprints[0], fingerprints[1])


def _assert_stable(root: Path, expected: tuple[SourceFile, ...]) -> None:
    current, _ = _snapshot_tree(root)
    if current != expected:
        _fail("source_drift", "project inventory/stat/hash changed during decode")


def _primary_venue_identity(data: bytes, path: str) -> tuple[str, str]:
    if len(data) < 52 or _u32(data, 20, path) < 1 or _u32(data, 24, path) != 4:
        _fail("source_identity", "unsupported primary Venue header", path)
    name, _ = _caf_string(data, 44, path, ascii_only=True)
    return data[28:44].hex(), name


def _identity_gate(blobs: dict[str, bytes]) -> ProjectIdentity:
    manifest_data = blobs.get(".ssproj")
    venue_data = blobs.get("SoundSwitchVenues.bin")
    if manifest_data is None or venue_data is None:
        _fail("source_identity", "required .ssproj or SoundSwitchVenues.bin is missing")
    manifest = _json_no_duplicates(manifest_data, ".ssproj")
    version = manifest.get("version")
    if not isinstance(version, dict):
        _fail("source_identity", "manifest version object is missing", ".ssproj")
    version_text = f"{version.get('major')}.{version.get('minor')}.{version.get('hotfix')}"
    venue_guid, venue_name = _primary_venue_identity(venue_data, "SoundSwitchVenues.bin")
    failures = []
    if manifest.get("id") != CANONICAL_PROJECT_UUID:
        failures.append("project UUID")
    if version_text != CANONICAL_SOUNDSWITCH_VERSION:
        failures.append("SoundSwitch version")
    if venue_guid != CANONICAL_VENUE_GUID:
        failures.append("primary Venue GUID")
    if failures:
        _fail("source_identity", "canonical gate rejected: " + ", ".join(failures))
    return ProjectIdentity(CANONICAL_PROJECT_UUID, version_text, CANONICAL_CONTAINER_VERSION,
                           venue_guid, venue_name)


def _fixture_channels(data: bytes, path: str) -> tuple[FixtureChannel, ...]:
    by_id: dict[int, FixtureChannel] = {}
    scan_end = min(len(data), 8192)
    for offset in range(max(0, scan_end - 16)):
        version, channel_id, present, units = struct.unpack_from("<IIII", data, offset)
        if version != 2 or channel_id not in _CHANNEL_BY_ID or present != 1 or not 2 <= units <= 64:
            continue
        end = offset + 16 + units * 2
        if end > scan_end:
            continue
        try:
            raw = data[offset + 16:end].decode("utf-16le")
        except UnicodeDecodeError:
            continue
        if not raw.endswith("\0") or "\0" in raw[:-1] or not raw[:-1]:
            continue
        candidate = FixtureChannel(offset, channel_id, _CHANNEL_BY_ID[channel_id], raw[:-1])
        prior = by_id.get(channel_id)
        if prior is None:
            by_id[channel_id] = candidate
    if tuple(by_id) != tuple(value for value in _CHANNEL_IDS if value in by_id) or len(by_id) != 19:
        _fail("fixture_profile", "canonical 19-channel profile was not decoded", path)
    return tuple(by_id[value] for value in _CHANNEL_IDS)


def _cue_candidate(data: bytes, offset: int, path: str) -> AttributeCue | None:
    if offset + 4 > len(data):
        return None
    units = struct.unpack_from("<I", data, offset)[0]
    if not 2 <= units <= 96:
        return None
    name_end = offset + 4 + units * 2
    if name_end + 28 > len(data):
        return None
    try:
        raw_name = data[offset + 4:name_end].decode("utf-16le")
    except UnicodeDecodeError:
        return None
    if not raw_name.endswith("\0") or "\0" in raw_name[:-1] or not raw_name[:-1]:
        return None
    name = raw_name[:-1]
    guid = data[name_end + 4:name_end + 20].hex()
    if data[name_end + 20:name_end + 24] == b"\xff" * 4:
        count = struct.unpack_from("<I", data, name_end + 24)[0]
        if not 64 <= count <= 1024:
            return None
        end = name_end + 28 + count * 4
        if end > len(data):
            return None
        indices = struct.unpack_from(f"<{count}I", data, name_end + 28)
        if indices != tuple(range(count)):
            return None
        return AttributeCue(offset, end, "minimal_default_catalog_tail", name, guid, None, (), indices)
    if name_end + 60 > len(data):
        return None
    unknown, flag_a, flag_b = struct.unpack_from("<III", data, name_end + 20)
    flag_c, flag_d, count = struct.unpack_from("<III", data, name_end + 48)
    if (flag_a, flag_b, flag_c, flag_d) != (1, 1, 1, 1) or count > 4096:
        return None
    fixture_guid = data[name_end + 32:name_end + 48].hex()
    end = name_end + 60 + count * 16
    if end > len(data):
        return None
    rows: list[CueAttribute] = []
    keys: set[tuple[int, int]] = set()
    for index in range(count):
        row_offset = name_end + 60 + index * 16
        present, group, channel_id = struct.unpack_from("<III", data, row_offset)
        repeated = data[row_offset + 12:row_offset + 16]
        if present != 1 or group not in _FIXTURE_GROUPS or channel_id not in _CHANNEL_BY_ID \
                or len(set(repeated)) != 1:
            return None
        key = (group, channel_id)
        if key in keys:
            _fail("duplicate_key", "duplicate cue fixture/channel key", path, row_offset)
        keys.add(key)
        rows.append(CueAttribute(row_offset, group, channel_id, _CHANNEL_BY_ID[channel_id], repeated[0]))
    return AttributeCue(offset, end, "fixture_payload", name, guid, fixture_guid, tuple(rows))


def decode_venue_cues(data: bytes, path: str = "SoundSwitchVenues.bin") -> tuple[AttributeCue, ...]:
    cues: list[AttributeCue] = []
    offset = 0
    while offset + 4 <= len(data):
        cue = _cue_candidate(data, offset, path)
        if cue is None:
            offset += 1
        else:
            cues.append(cue)
            offset = cue.end_offset
    guids = [row.cue_guid for row in cues]
    if len(guids) != len(set(guids)):
        _fail("duplicate_key", "duplicate Venue cue GUID", path)
    return tuple(cues)


def _scalar_map(data: bytes, offset: int, path: str) -> tuple[tuple[StaticScalarValue, ...], int]:
    count = _bounded_count(_u32(data, offset, path), "static scalar", path, offset, 1024)
    offset += 4
    rows = []
    ids = set()
    for _ in range(count):
        if offset + 12 > len(data):
            _fail("bounds", "truncated static scalar map", path, offset)
        fixture_id = _u32(data, offset, path)
        value = struct.unpack_from("<d", data, offset + 4)[0]
        if fixture_id in ids or not math.isfinite(value):
            _fail("static_look", "duplicate fixture ID or nonfinite scalar", path, offset)
        ids.add(fixture_id)
        rows.append(StaticScalarValue(offset, fixture_id, value))
        offset += 12
    return tuple(rows), offset


def _static_look(data: bytes, offset: int, slot: int, path: str) -> tuple[StaticLook, int]:
    start = offset
    if _u32(data, offset, path) != 5:
        _fail("static_look", "static slot version is not 5", path, offset)
    name, offset = _caf_string(data, offset + 4, path)
    intensity, offset = _scalar_map(data, offset, path)
    strobe, offset = _scalar_map(data, offset, path)
    colour_count = _bounded_count(_u32(data, offset, path), "colour", path, offset, 1024)
    offset += 4
    colours = []
    colour_ids = set()
    for _ in range(colour_count):
        if offset + 12 > len(data):
            _fail("bounds", "truncated colour map", path, offset)
        fixture_id = _u32(data, offset, path)
        if fixture_id in colour_ids:
            _fail("duplicate_key", "duplicate colour fixture ID", path, offset)
        colour_ids.add(fixture_id)
        colours.append(StaticColourValue(offset, fixture_id, data[offset + 4:offset + 12]))
        offset += 12
    position_count = _bounded_count(_u32(data, offset, path), "position", path, offset, 1024)
    offset += 4
    positions = []
    position_ids = set()
    for _ in range(position_count):
        if offset + 20 > len(data):
            _fail("bounds", "truncated position map", path, offset)
        fixture_id = _u32(data, offset, path)
        if fixture_id in position_ids:
            _fail("duplicate_key", "duplicate position fixture ID", path, offset)
        position_ids.add(fixture_id)
        positions.append(StaticPositionValue(offset, fixture_id, data[offset + 4:offset + 20].hex()))
        offset += 20
    fixture_count = _bounded_count(_u32(data, offset, path), "static attribute", path, offset, 4096)
    offset += 4
    attributes = []
    keys = set()
    for _ in range(fixture_count):
        if offset + 16 > len(data):
            _fail("bounds", "truncated static generic attribute", path, offset)
        present, group, channel_id = struct.unpack_from("<III", data, offset)
        repeated = data[offset + 12:offset + 16]
        if present != 1 or group not in _FIXTURE_GROUPS or channel_id not in _CHANNEL_BY_ID \
                or len(set(repeated)) != 1:
            _fail("static_look", "invalid generic attribute row", path, offset)
        key = (group, channel_id)
        if key in keys:
            _fail("duplicate_key", "duplicate static fixture/channel key", path, offset)
        keys.add(key)
        attributes.append(CueAttribute(offset, group, channel_id, _CHANNEL_BY_ID[channel_id], repeated[0]))
        offset += 16
    base_ids = tuple(row.fixture_instance_id for row in intensity)
    if tuple(row.fixture_instance_id for row in strobe) != base_ids \
            or tuple(row.fixture_instance_id for row in colours) != base_ids \
            or tuple(row.fixture_instance_id for row in positions) != base_ids:
        _fail("static_look", "five Static Look maps do not share fixture ordering", path, start)
    return StaticLook(start, offset, slot, 5, name, intensity, strobe, tuple(colours),
                      tuple(positions), tuple(attributes)), offset


def decode_static_looks(data: bytes, venue_guid: str = CANONICAL_VENUE_GUID,
                        path: str = "SoundSwitchVenues.bin") -> tuple[StaticLook, ...]:
    marker = bytes.fromhex(venue_guid) + struct.pack("<II", 1, 32)
    headers = []
    search = 0
    while True:
        start = data.find(marker, search)
        if start < 0:
            break
        headers.append(start)
        search = start + 1
    if len(headers) != 1:
        _fail("static_look", f"expected one primary Venue Static Looks collection header, found {len(headers)}", path)
    offset = headers[0] + len(marker)
    looks = []
    for slot in range(32):
        look, offset = _static_look(data, offset, slot, path)
        looks.append(look)
    return tuple(looks)


def _valid_trailer(data: bytes, offset: int) -> bool:
    return offset >= 0 and offset + 10 <= len(data) and data[offset + 4] in (0, 1) \
        and data[offset + 9] in (0, 1)


def _ssfile_candidates(data: bytes, expected_end: int, path: str) -> list[tuple[int, tuple[CueDictionaryEntry, ...], tuple[TimelineRecord, ...], int]]:
    candidates = []
    search = 0
    marker = struct.pack("<I", 1)
    while True:
        offset = data.find(marker, search, max(0, expected_end - 7))
        if offset < 0:
            break
        search = offset + 1
        if offset + 8 > expected_end:
            continue
        count = struct.unpack_from("<I", data, offset + 4)[0]
        if not 1 <= count <= 10_000:
            continue
        entries_end = offset + 8 + count * 20
        if entries_end + 4 > expected_end:
            continue
        timeline_count = struct.unpack_from("<I", data, entries_end)[0]
        if timeline_count > 100_000 or entries_end + 4 + timeline_count * 16 != expected_end:
            continue
        cues = []
        keys = set()
        guids = set()
        valid = True
        for index in range(count):
            row_offset = offset + 8 + index * 20
            guid = data[row_offset:row_offset + 16].hex()
            key = struct.unpack_from("<I", data, row_offset + 16)[0]
            if key in keys or guid in guids:
                valid = False
                break
            keys.add(key); guids.add(guid)
            cues.append(CueDictionaryEntry(row_offset, guid, key))
        if not valid:
            continue
        by_key = {row.stored_key: row.cue_guid for row in cues}
        timeline = []
        timeline_offset = entries_end + 4
        for index in range(timeline_count):
            row_offset = timeline_offset + index * 16
            version, constant, time, raw = struct.unpack_from("<IIiI", data, row_offset)
            if version != 1 or constant != 1:
                valid = False
                break
            resolved = raw - 1 if raw else None
            if resolved is not None and resolved not in by_key:
                valid = False
                break
            timeline.append(TimelineRecord(row_offset, version, time, raw,
                                           "cue" if raw else "clear_control", resolved,
                                           by_key.get(resolved)))
        if valid:
            candidates.append((offset, tuple(cues), tuple(timeline), timeline_offset))
    return candidates


def decode_ssfile(data: bytes, relative_path: str, source_sha256: str | None = None) -> LightingDocument:
    if len(data) < 8 + _TRAILER_SIZE or data[:4] != _MAGIC:
        _fail("ssfile_header", "not a SoundSwitch container", relative_path)
    version = _u32(data, 4, relative_path)
    if version != CANONICAL_CONTAINER_VERSION:
        _fail("ssfile_version", f"container version {version} is unsupported", relative_path, 4)
    footer_offset = _u32(data, 8, relative_path) if len(data) >= 12 else 0
    if footer_offset:
        if footer_offset < _TRAILER_SIZE or footer_offset > len(data):
            _fail("ssfile_footer", "header footer offset is outside source", relative_path, 8)
        trailer_offset = footer_offset - _TRAILER_SIZE
    else:
        trailer_offset = len(data) - _TRAILER_SIZE
    if not _valid_trailer(data, trailer_offset):
        _fail("ssfile_trailer", "document lacks an exact physical 10-byte trailer", relative_path,
              trailer_offset)
    candidates = _ssfile_candidates(data, trailer_offset, relative_path)
    candidates = [
        candidate
        for candidate in candidates
        if candidate[2]
        or any(
            _hash(data[start:start + 441]) == _SHARED_441_HASH
            for start in range(max(0, candidate[0] - 600), candidate[0])
            if start + 441 <= candidate[0] + 1
        )
    ]
    if len(candidates) != 1:
        _fail("ssfile_layout", f"expected one physical cue-map/timeline candidate, found {len(candidates)}",
              relative_path)
    cue_offset, cues, timeline, _ = candidates[0]
    intensity: list[IntensityNode] = []
    if _AUTOLOOP_NAME.fullmatch(relative_path) and len(data) >= 2259:
        node_count = _u32(data, 2255, relative_path)
        if node_count <= 10_000 and 2259 + node_count * 17 <= cue_offset:
            node_offset = 2259
            parsed_nodes = []
            for _ in range(node_count):
                record_version, start, end, value = struct.unpack_from("<IiiI", data, node_offset)
                enabled = data[node_offset + 16]
                if record_version != 2 or start != end or enabled not in (0, 1):
                    parsed_nodes = []
                    break
                parsed_nodes.append(IntensityNode(node_offset, record_version, start, end, value,
                                                  bool(enabled)))
                node_offset += 17
            intensity = parsed_nodes
    shared_positions = []
    needle = None
    # Locate only the validated shared-table hash; raw bytes are retained through prefix hashing.
    for start in range(max(0, cue_offset - 600), cue_offset):
        end = start + 441
        if end <= cue_offset + 1 and _hash(data[start:end]) == _SHARED_441_HASH:
            shared_positions.append(start)
    if len(shared_positions) > 1:
        _fail("ssfile_layout", "multiple shared 441-byte tables found", relative_path)
    layout = "shared_441_dictionary_timeline" if shared_positions else \
        ("dictionary_timeline_addressed_footer" if footer_offset else "dictionary_timeline_no_shared_anchor")
    footer = data[footer_offset:] if footer_offset else b""
    fixture_profile_guid = data[28:44].hex() if len(data) >= 44 else ""
    return LightingDocument(relative_path, source_sha256 or _hash(data), len(data), version,
                            fixture_profile_guid, layout,
                            cue_offset, cues, timeline, tuple(intensity), trailer_offset,
                            data[trailer_offset:trailer_offset + 10], _hash(data[:cue_offset]),
                            _hash(footer) if footer else None)


def decode_catalog(data: bytes, path: str, source_sha256: str | None = None) -> AutoloopCatalog:
    if len(data) < 25 or data[:4] != _MAGIC:
        _fail("catalog_header", "not a SoundSwitch catalog", path)
    version, reserved_a, reserved_b, layout, category_count = struct.unpack_from("<IIIII", data, 4)
    expected_layout = {
        "SoundSwitchAutoLoops.bin": 2,
        "SoundSwitchAutoLoopsEx.bin": 3,
    }.get(path)
    if version != 3 or reserved_a or reserved_b or layout not in (2, 3) \
            or expected_layout is not None and layout != expected_layout:
        _fail("catalog_header", "unsupported catalog header", path)
    _bounded_count(category_count, "category", path, 20, 1024)
    offset = 24
    raw_categories = []
    for index in range(category_count):
        start = offset
        enabled = _u32(data, offset, path)
        if enabled not in (0, 1):
            _fail("catalog", "invalid category enabled flag", path, offset)
        name, offset = _plain_utf16_string(data, offset + 4, path)
        raw_categories.append((start, index, name, bool(enabled)))
    entry_count = _bounded_count(_u32(data, offset, path), "catalog entry", path, offset, 10_000)
    offset += 4
    entries = []
    indices = set()
    for ordering in range(entry_count):
        start = offset
        record_type, app_index, bars, enabled = struct.unpack_from("<IIII", data, offset)
        offset += 16
        name, offset = _plain_utf16_string(data, offset, path)
        category_index = _u32(data, offset, path); offset += 4
        if record_type != 2 or bars != 8 or enabled not in (0, 1) or category_index >= category_count:
            _fail("catalog", "invalid catalog entry", path, start)
        if app_index in indices:
            _fail("duplicate_key", "duplicate AppLog index", path, start)
        indices.add(app_index)
        entries.append(AutoloopCatalogEntry(start, ordering, app_index, app_index + 1,
                                            bool(enabled), name, category_index,
                                            raw_categories[category_index][2]))
    orders = []
    for category_index in range(category_count):
        if category_index:
            if offset >= len(data) or data[offset] != 1:
                _fail("catalog", "missing category-order marker", path, offset)
            offset += 1
        start = offset
        count = _bounded_count(_u32(data, offset, path), "category order", path, offset, 10_000)
        offset += 4
        if offset + count * 4 > len(data):
            _fail("bounds", "category order extends beyond source", path, offset)
        app_indices = struct.unpack_from(f"<{count}I", data, offset)
        offset += count * 4
        if len(app_indices) != len(set(app_indices)):
            _fail("duplicate_key", "duplicate category AppLog identity", path, start)
        orders.append(AutoloopCategory(start, category_index, raw_categories[category_index][2],
                                      raw_categories[category_index][3], app_indices))
    if offset >= len(data) or data[offset] != 1 or offset + 1 != len(data):
        _fail("catalog_eof", "catalog does not end at its final marker", path, offset)
    by_category = {index: {row.app_log_index for row in entries if row.category_index == index}
                   for index in range(category_count)}
    for row in orders:
        order_ids = set(row.app_log_indices)
        valid = order_ids == by_category[row.category_index] if layout == 2 \
            else by_category[row.category_index].issubset(order_ids)
        if not valid:
            _fail("catalog", "category ordering disagrees with catalog entries", path, row.source_offset)
    return AutoloopCatalog(path, source_sha256 or _hash(data), version, layout, tuple(orders), tuple(entries))


def _qt_uuid(raw: bytes) -> str:
    first, second, third = struct.unpack_from("<IHH", raw)
    tail = raw[8:]
    return (f"{first:08X}-{second:04X}-{third:04X}-{tail[0]:02X}{tail[1]:02X}-"
            + "".join(f"{byte:02X}" for byte in tail[2:]))


def _optional_qstring(data: bytes, offset: int, path: str) -> tuple[str | None, int]:
    flag = _u32(data, offset, path); offset += 4
    if flag == 0:
        return None, offset
    if flag != 1:
        _fail("track_map", "invalid optional string flag", path, offset - 4)
    return _plain_utf16_string(data, offset, path)


def decode_track_map(data: bytes, path: str = "SoundSwitchTrackMap.bin") -> tuple[TrackMapRecord, ...]:
    if len(data) < 8:
        _fail("track_map", "TrackMap is shorter than its header", path)
    rows = []
    search = 0
    while True:
        marker = data.find(_TRACK_MAPPING_PREFIX, search)
        if marker < 0:
            break
        search = marker + 1
        try:
            uuid_offset = marker + len(_TRACK_MAPPING_PREFIX)
            if uuid_offset + 16 > len(data):
                continue
            ssid = _qt_uuid(data[uuid_offset:uuid_offset + 16])
            offset = uuid_offset + 16
            title, offset = _optional_qstring(data, offset, path)
            artist, offset = _optional_qstring(data, offset, path)
            filepath, offset = _optional_qstring(data, offset, path)
        except SoundSwitchDecodeError:
            continue
        if filepath and Path(filepath).suffix.casefold() in _AUDIO_SUFFIXES:
            rows.append(TrackMapRecord(marker, ssid, title, artist, filepath))
    if not rows:
        _fail("track_map", "no bounded TrackMap mapping records found", path)
    folded: dict[str, str] = {}
    for row in rows:
        key = row.filepath.casefold()
        if key in folded and folded[key] != row.filepath:
            _fail("case_collision", "TrackMap contains case-colliding locator paths", path,
                  row.source_offset)
        folded[key] = row.filepath
    return tuple(rows)


def _is_bounded_in_app_demo(ssid: str, rows: tuple[TrackMapRecord, ...],
                            project_blobs: dict[str, bytes]) -> bool:
    """Recognize the one saved, project-bundled inactive demo artifact."""
    return "In App Demo.mp4" in project_blobs and any(
        row.soundswitch_id == ssid
        and row.title == "SoundSwitch 2.0 In-App Demo"
        and row.artist == "inMusic NZ Ltd"
        and Path(row.filepath).name == "In App Demo.mp4"
        for row in rows
    )


def _classify_script_source(
    relative_path: str,
    fixture_profile_guid: str,
    rows: tuple[TrackMapRecord, ...],
    project_blobs: dict[str, bytes],
) -> ScriptedTrackClassification:
    match = _SCRIPT_NAME.fullmatch(relative_path)
    if match is None:
        _fail("script_identity", "script filename is not a normalized SSID", relative_path)
    ssid = match.group(1).upper()
    mapping_count = sum(row.soundswitch_id == ssid for row in rows)
    if _is_bounded_in_app_demo(ssid, rows, project_blobs):
        status = "inactive_bundled_demo"
    elif mapping_count and fixture_profile_guid != CANONICAL_VENUE_GUID:
        _fail(
            "unsupported_active_layout",
            "mapped scripted identity uses a nonprimary fixture profile",
            relative_path,
        )
    elif mapping_count:
        status = "supported_mapped_primary"
    elif fixture_profile_guid != CANONICAL_VENUE_GUID:
        status = "inactive_unmapped_alternate_profile"
    else:
        status = "inactive_unmapped_primary"
    return ScriptedTrackClassification(
        ssid, relative_path, fixture_profile_guid, mapping_count, status
    )


class _RecordableReader:
    def __init__(self, data: bytes, path: str) -> None:
        self.data = data; self.path = path; self.offset = 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            _fail("recordable_bounds", "recordable field extends beyond source", self.path, self.offset)
        value = self.data[self.offset:self.offset + size]; self.offset += size; return value

    def u8(self) -> int: return self.take(1)[0]
    def u16(self) -> int: return struct.unpack("<H", self.take(2))[0]
    def u32(self) -> int: return struct.unpack("<I", self.take(4))[0]
    def u64(self) -> int: return struct.unpack("<Q", self.take(8))[0]
    def signature(self, expected: int) -> None:
        start = self.offset
        if self.u32() != expected: _fail("recordable_signature", f"expected 0x{expected:08x}", self.path, start)
    def count(self, label: str) -> int:
        return _bounded_count(self.u64(), label, self.path, self.offset - 8)
    def string(self) -> str:
        self.signature(0x01380305)
        start = self.offset; end = self.data.find(b"\0", start)
        if end < 0 or end - start > 65535: _fail("recordable_string", "invalid NUL string", self.path, start)
        try: value = self.data[start:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SoundSwitchDecodeError("recordable_string", "invalid UTF-8", relative_path=self.path,
                                         offset=start) from exc
        if any(ord(char) < 32 for char in value): _fail("recordable_string", "control character in string", self.path, start)
        self.offset = end + 1; return value


def decode_learned_midi(data: bytes, path: str, source_sha256: str | None = None) -> LearnedMidiMap | None:
    if len(data) < 15 or data[:4] != struct.pack("<I", 0xDEADBEEF) \
            or data[7:11] != struct.pack("<I", 0x01380308):
        return None
    reader = _RecordableReader(data, path)
    reader.signature(0xDEADBEEF); version = reader.u16(); status = reader.u8()
    if version != 1: _fail("recordable_version", f"learned map version {version} is unsupported", path, 4)
    reader.signature(0x01380308)
    devices = []; device_names = set()
    for _ in range(reader.count("device")):
        device = reader.string()
        if device in device_names: _fail("duplicate_key", "duplicate MIDI device", path, reader.offset)
        device_names.add(device); reader.signature(0x01380306)
        collections = []; collection_ids = set()
        for _ in range(reader.count("collection")):
            collection_id = reader.u32()
            if collection_id in collection_ids: _fail("duplicate_key", "duplicate MIDI collection", path, reader.offset - 4)
            collection_ids.add(collection_id); reader.signature(0x01380306)
            bindings = []; binding_keys = set()
            for _ in range(reader.count("binding")):
                start = reader.offset; reader.signature(0x01380307)
                message_raw = reader.u8(); data_byte = reader.u8(); channel = reader.u8()
                if message_raw not in (0, 1, 2) or channel > 15:
                    _fail("midi_binding", "unsupported message type or channel", path, start)
                control_path = reader.string(); enabled_raw = reader.u8()
                if enabled_raw not in (0, 1): _fail("midi_binding", "invalid enabled flag", path, reader.offset - 1)
                key = (message_raw, data_byte, channel, control_path)
                if key in binding_keys: _fail("duplicate_key", "duplicate MIDI binding", path, start)
                binding_keys.add(key)
                bindings.append(MidiBinding(start, device, collection_id,
                                            ("note", "control_change", "pitch_bend")[message_raw],
                                            message_raw, data_byte, channel, control_path, bool(enabled_raw)))
            collections.append(MidiCollection(collection_id, tuple(bindings)))
        reader.signature(0x01380306); feedback = reader.take(reader.count("feedback"))
        devices.append(MidiDevice(device, tuple(collections), feedback))
    reader.signature(0xDEADBEEF)
    if reader.offset != len(data): _fail("recordable_eof", "trailing learned-map bytes", path, reader.offset)
    return LearnedMidiMap(path, source_sha256 or _hash(data), version, status, tuple(devices))


def decode_control_label_states(
    data: bytes, path: str, source_sha256: str | None = None
) -> tuple[ControlLabelState, ...] | None:
    """Decode SoundSwitch saved button label colour + press/toggle state.

    Reverse-engineered from SoundSwitch 2.10.3:
    ``ControlManagerPrivate::loadControlLabelColour`` reads this map, calls
    ``QAbstractButton::setCheckable(flag)``, then stores the same flag at
    ``PushButton+0xc1``. The UI context menu writes that byte as Press/Toggle.
    """
    if len(data) < 18 or data[:4] != struct.pack("<I", 0xDEADBEEF) \
            or data[6:10] != struct.pack("<I", 0x01380308):
        return None
    if data[7:11] == struct.pack("<I", 0x01380308):
        return None
    reader = _RecordableReader(data, path)
    reader.signature(0xDEADBEEF)
    version = reader.u16()
    if version != 1:
        return None
    reader.signature(0x01380308)
    states = []
    seen = set()
    source = source_sha256 or _hash(data)
    for _ in range(reader.count("control label")):
        offset = reader.offset
        control_path = reader.string()
        if control_path in seen:
            _fail("duplicate_key", "duplicate control label state", path, offset)
        seen.add(control_path)
        rgba = reader.u32()
        mode_raw = reader.u8()
        if mode_raw not in (0, 1):
            _fail("control_label_state", "invalid interaction mode flag", path, reader.offset - 1)
        states.append(ControlLabelState(
            offset, path, source, control_path, rgba,
            "toggle" if mode_raw == 1 else "press",
        ))
    reader.signature(0xDEADBEEF)
    if reader.offset != len(data):
        _fail("recordable_eof", "trailing control-label bytes", path, reader.offset)
    return tuple(states)


def _all_bindings(maps: tuple[LearnedMidiMap, ...]) -> tuple[MidiBinding, ...]:
    return tuple(binding for mapping in maps for device in mapping.devices
                 for collection in device.collections for binding in collection.bindings)


def _reconcile_catalog_autoloops(catalogs: tuple[AutoloopCatalog, ...],
                                 documents: tuple[LightingDocument, ...],
                                 primary_profile_guid: str = CANONICAL_VENUE_GUID) -> None:
    expected: dict[str, AutoloopCatalogEntry] = {}
    for catalog in catalogs:
        for entry in catalog.entries:
            relative = f"SSAutoLoop{entry.file_number}.ssfile"
            prior = expected.get(relative)
            if prior is not None and prior != entry:
                _fail("identity_conflict", f"conflicting catalog identity for {relative}")
            expected[relative] = entry
    actual: dict[str, LightingDocument] = {}
    for document in documents:
        if document.relative_path in actual:
            _fail("identity_conflict", f"duplicate Autoloop source {document.relative_path}")
        if document.fixture_profile_guid != primary_profile_guid:
            _fail(
                "unsupported_active_layout",
                "catalog-backed Autoloop uses a nonprimary fixture profile",
                document.relative_path,
            )
        actual[document.relative_path] = document
    missing = sorted(set(expected) - set(actual))
    orphaned = sorted(set(actual) - set(expected))
    if missing or orphaned:
        _fail("autoloop_inventory", f"missing={missing!r}; orphaned={orphaned!r}")


def _validate_document_cues(documents: tuple[LightingDocument, ...], venue_cue_guids: set[str],
                            primary_profile_guid: str,
                            active_script_paths: set[str] | None = None) -> tuple[SourceDiagnostic, ...]:
    diagnostics = []
    for document in documents:
        missing = sorted({row.resolved_cue_guid for row in document.timeline
                          if row.resolved_cue_guid is not None
                          and row.resolved_cue_guid not in venue_cue_guids})
        if not missing:
            continue
        script_match = _SCRIPT_NAME.fullmatch(document.relative_path)
        inactive = script_match is not None and (
            document.fixture_profile_guid != primary_profile_guid
            if active_script_paths is None
            else document.relative_path not in active_script_paths
        )
        if not inactive:
            _fail("missing_cue", f"{len(missing)} referenced Venue cue GUID(s) are missing",
                  document.relative_path)
        diagnostics.append(SourceDiagnostic(
            "inactive_missing_cue", document.relative_path,
            f"{len(missing)} referenced cue GUID(s) are outside the primary Venue",
            active=False,
        ))
    return tuple(diagnostics)


def _resolve_controls(maps: tuple[LearnedMidiMap, ...], catalogs: tuple[AutoloopCatalog, ...],
                      static_looks: tuple[StaticLook, ...], autoloop_paths: set[str],
                      control_states: dict[str, ControlLabelState]) -> tuple[ResolvedControlBinding, ...]:
    entries: dict[int, AutoloopCatalogEntry] = {}
    categories: dict[int, AutoloopCategory] = {}
    for catalog in catalogs:
        for entry in catalog.entries:
            if entry.app_log_index in entries and entries[entry.app_log_index] != entry:
                _fail("identity_conflict", f"conflicting AppLog identity {entry.app_log_index}")
            entries[entry.app_log_index] = entry
        # Extended catalog contains the complete current category-order tables.
        if len(catalog.categories) >= len(categories):
            categories = {row.category_index: row for row in catalog.categories}
    resolved = []
    events: dict[tuple[str, str, int, int], set[str]] = {}
    for binding in _all_bindings(maps):
        render = _AUTOLOOP_CONTROL.fullmatch(binding.control_path) or _STATIC_CONTROL.fullmatch(binding.control_path)
        if binding.enabled and render:
            key = (binding.device_name, binding.message_type, binding.channel_zero_based, binding.data_byte)
            events.setdefault(key, set()).add(binding.control_path)
            if binding.message_type != "note":
                _fail("unsupported_active_control", "render-affecting CC/pitch binding is unsupported",
                      offset=binding.source_offset)
        auto = _AUTOLOOP_CONTROL.fullmatch(binding.control_path)
        static = _STATIC_CONTROL.fullmatch(binding.control_path)
        if not binding.enabled and (auto or static):
            # Disabled learns are part of the complete registry but cannot make
            # a project artifact active or collide with an enabled event.
            control_index = int((auto or static).group(1))
            interaction_mode = None
            if static:
                state = control_states.get(binding.control_path)
                if state is None:
                    _fail(
                        "unresolved_control",
                        f"Static Override slot {control_index} has no saved interaction mode",
                    )
                interaction_mode = state.interaction_mode
            resolved.append(ResolvedControlBinding(
                binding,
                "autoloop" if auto else "static_look",
                None if auto else f"{CANONICAL_VENUE_GUID}:slot:{control_index}",
                control_index,
                None,
                interaction_mode,
            ))
            continue
        if auto:
            slot = int(auto.group(1)); category_index, category_slot = divmod(slot, 32)
            category = categories.get(category_index)
            if category is None or category_slot >= len(category.app_log_indices):
                _fail("unresolved_control", f"Autoloop control slot {slot} has no catalog target")
            app_index = category.app_log_indices[category_slot]; entry = entries.get(app_index)
            if entry is None: _fail("unresolved_control", f"catalog AppLog {app_index} is missing")
            target = f"SSAutoLoop{entry.file_number}.ssfile"
            if target not in autoloop_paths: _fail("unresolved_control", f"Autoloop target {target} is missing")
            resolved.append(ResolvedControlBinding(binding, "autoloop", target,
                                                   entry.app_log_index, entry.display_name))
        elif static:
            slot = int(static.group(1))
            if slot >= len(static_looks): _fail("unresolved_control", f"Static Override slot {slot} is missing")
            state = control_states.get(binding.control_path)
            if state is None:
                _fail("unresolved_control", f"Static Override slot {slot} has no saved interaction mode")
            resolved.append(ResolvedControlBinding(
                binding, "static_look", f"{CANONICAL_VENUE_GUID}:slot:{slot}", slot,
                static_looks[slot].name, state.interaction_mode,
            ))
        else:
            resolved.append(ResolvedControlBinding(binding, "non_render", None, None))
    collisions = [(key, paths) for key, paths in events.items() if len(paths) > 1]
    if collisions:
        key, paths = collisions[0]
        _fail("midi_collision", f"enabled event {key!r} maps to render controls {sorted(paths)!r}")
    return tuple(resolved)


def decode_project(project: str | os.PathLike[str], *,
                   no_target_policy_inputs: tuple[str, ...] = (),
                   _before_stability_check: Callable[[], None] | None = None) -> DecodedSoundSwitchProject:
    """Decode one canonical saved project without writing it or opening devices."""
    root = Path(project).expanduser()
    preflight_identity, preflight_sources = _preflight_identity(root)
    inventory, blobs = _snapshot_tree(root)
    identity = _identity_gate(blobs)
    inventory_by_path = {row.relative_path: row for row in inventory}
    if identity != preflight_identity or any(
        inventory_by_path.get(row.relative_path) != row for row in preflight_sources
    ):
        _fail("source_drift", "identity sources changed after canonical preflight")

    venue_data = blobs["SoundSwitchVenues.bin"]
    channels = _fixture_channels(venue_data, "SoundSwitchVenues.bin")
    cues = decode_venue_cues(venue_data)
    render_count = sum(cue.render_bearing for cue in cues)
    tail_count = len(cues) - render_count
    if render_count <= 0:
        _fail("venue_cue_split", "expected at least one render-bearing Venue cue",
              "SoundSwitchVenues.bin")
    if any(cue.render_bearing and cue.record_kind != "fixture_payload" for cue in cues) \
            or any((not cue.render_bearing) and cue.attributes for cue in cues):
        _fail("venue_cue_split",
              f"invalid render/catalog-tail split: {render_count} render + {tail_count} catalog-tail",
              "SoundSwitchVenues.bin")
    looks = decode_static_looks(venue_data, identity.venue_guid)

    catalogs = tuple(decode_catalog(blobs[name], name, _hash(blobs[name])) for name in
                     ("SoundSwitchAutoLoops.bin", "SoundSwitchAutoLoopsEx.bin") if name in blobs)
    if len(catalogs) != 2:
        _fail("catalog", "both canonical Autoloop catalogs are required")

    track_map_data = blobs.get("SoundSwitchTrackMap.bin")
    if track_map_data is None: _fail("track_map", "SoundSwitchTrackMap.bin is missing")
    track_map = decode_track_map(track_map_data)

    autoloops = []
    scripts = []
    script_classifications = []
    script_ids = set()
    unsupported_script_paths = set()
    diagnostics = []
    for relative, data in sorted(blobs.items()):
        if _AUTOLOOP_NAME.fullmatch(relative):
            autoloops.append(decode_ssfile(data, relative, _hash(data)))
        else:
            match = _SCRIPT_NAME.fullmatch(relative)
            if match:
                ssid = match.group(1).upper()
                if ssid in script_ids: _fail("identity_conflict", f"duplicate scripted identity {ssid}")
                script_ids.add(ssid)
                fixture_profile_guid = data[28:44].hex() if len(data) >= 44 else ""
                classification = _classify_script_source(
                    relative, fixture_profile_guid, track_map, blobs
                )
                script_classifications.append(classification)
                if classification.status != "supported_mapped_primary":
                    diagnostics.append(SourceDiagnostic(
                        classification.status,
                        relative,
                        "script retained as an explicit inactive source-policy row",
                        active=False,
                    ))
                try:
                    scripts.append(decode_ssfile(data, relative, _hash(data)))
                except SoundSwitchDecodeError as exc:
                    if classification.status == "supported_mapped_primary":
                        raise
                    unsupported_script_paths.add(relative)
                    diagnostics.append(SourceDiagnostic(
                        "unsupported_inactive_script", relative, str(exc), active=False
                    ))
    _reconcile_catalog_autoloops(catalogs, tuple(autoloops), identity.venue_guid)
    venue_cue_guids = {cue.cue_guid for cue in cues if cue.render_bearing}
    active_script_paths = {
        row.relative_path for row in script_classifications
        if row.status == "supported_mapped_primary"
    }
    diagnostics.extend(_validate_document_cues(tuple((*autoloops, *scripts)), venue_cue_guids,
                                                identity.venue_guid, active_script_paths))

    learned = []
    control_label_states = []
    decoded_paths = {".ssproj", "SoundSwitchVenues.bin", "SoundSwitchAutoLoops.bin",
                     "SoundSwitchAutoLoopsEx.bin", "SoundSwitchTrackMap.bin"}
    decoded_paths.update(row.relative_path for row in autoloops)
    decoded_paths.update(row.relative_path for row in scripts)
    decoded_paths.update(unsupported_script_paths)
    for relative, data in sorted(blobs.items()):
        if relative.startswith("recordable/") and relative.endswith(".dat"):
            mapping = decode_learned_midi(data, relative, _hash(data))
            if mapping is not None:
                learned.append(mapping); decoded_paths.add(relative)
                continue
            states = decode_control_label_states(data, relative, _hash(data))
            if states is not None:
                control_label_states.extend(states); decoded_paths.add(relative)
    if not learned: _fail("learned_midi", "no complete learned MIDI registry was decoded")
    control_states_by_path: dict[str, ControlLabelState] = {}
    for state in control_label_states:
        if _STATIC_CONTROL.fullmatch(state.control_path) is None:
            continue
        prior = control_states_by_path.get(state.control_path)
        if prior is not None and prior != state:
            _fail("identity_conflict", f"conflicting control label state for {state.control_path}")
        control_states_by_path[state.control_path] = state
    for source in inventory:
        if source.relative_path not in decoded_paths:
            diagnostics.append(SourceDiagnostic("opaque_artifact", source.relative_path,
                                                "retained by path, size, hash, mode, and mtime; no render semantics",
                                                active=False))
    resolved = _resolve_controls(tuple(learned), catalogs, looks,
                                 {row.relative_path for row in autoloops},
                                 control_states_by_path)
    if any(not name or name.strip() != name for name in no_target_policy_inputs) \
            or len(no_target_policy_inputs) != len(set(no_target_policy_inputs)):
        _fail("no_target_policy", "policy names must be unique, nonempty, and trimmed")
    no_targets = tuple(NoTargetPolicyInput(name) for name in no_target_policy_inputs)
    if _before_stability_check is not None:
        _before_stability_check()
    _assert_stable(root, inventory)
    return DecodedSoundSwitchProject(identity, inventory, channels, cues, looks, catalogs,
                                     tuple(autoloops), tuple(scripts), tuple(script_classifications),
                                     track_map, tuple(learned), resolved, no_targets,
                                     tuple(diagnostics))


__all__ = [
    "CANONICAL_PROJECT_UUID", "CANONICAL_SOUNDSWITCH_VERSION", "CANONICAL_VENUE_GUID",
    "SoundSwitchDecodeError", "decode_catalog", "decode_control_label_states",
    "decode_learned_midi", "decode_project",
    "decode_ssfile", "decode_static_looks", "decode_track_map", "decode_venue_cues",
]
