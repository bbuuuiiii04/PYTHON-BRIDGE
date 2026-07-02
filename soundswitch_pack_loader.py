"""Verified, immutable loader for SoundSwitch static-pack artifacts.

The loader performs no migration.  It first runs the independent verifier,
then parses the verified JSON into frozen runtime-neutral models.  It has no
MIDI API, serial, network, project-parser, or research-tool dependency.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

# Shared immutable empty mapping used as a dataclass default.  A bare
# ``MappingProxyType({})`` default is rejected by dataclasses on Python 3.11+
# (unhashable -> treated as a mutable default), so defaults must go through
# ``field(default_factory=...)``.  The proxy is read-only, so sharing one
# instance is safe.
_EMPTY_MAPPING: Mapping[Any, Any] = MappingProxyType({})

from .soundswitch_pack_verifier import SoundSwitchPackVerificationError, verify_pack
from .soundswitch_parity_registry import PARITY_LANES, count_lanes

SUPPORTED_SCHEMA_MAJOR = 1
AUTOLOOP_CYCLE_TICKS = 19_200
_CONTROL_CLASSIFICATIONS = frozenset({
    "pack_selection", "static_override", "blackout_mask",
    "bridge_owned_safety", "no_project_target", "inactive_report_only",
    "unsupported_fail_export",
})
_MESSAGE_TYPES = frozenset({"note", "control_change", "pitch_bend"})


class SoundSwitchPackLoadError(ValueError):
    """A verified pack cannot be represented by the current immutable model."""


@dataclass(frozen=True, slots=True)
class PackMidiBinding:
    """Verified learned controller binding retained for runtime input routing."""

    device_name: str
    message_type: Literal["note", "control_change", "pitch_bend"]
    channel_zero_based: int
    data_byte: int
    target_kind: Literal[
        "static_look", "autoloop", "blackout_mask", "pack_selection",
        "bridge_owned_safety", "no_project_target", "inactive_report_only",
    ]
    target_slot: int | None = None
    target_identity: str | None = None
    interaction: Literal["press", "toggle"] = "press"


@dataclass(frozen=True, slots=True)
class LoadedAutoloopBinding:
    channel_zero_based: int
    data_byte: int
    target_identity: str
    target_name: str


@dataclass(frozen=True, slots=True)
class LoadedAttribute:
    fixture_group: int
    channel_id: int
    dmx_channel: int
    value: int


@dataclass(frozen=True, slots=True)
class LoadedScalarValue:
    source_offset: int
    fixture_instance_id: int
    value: float


@dataclass(frozen=True, slots=True)
class LoadedColourValue:
    source_offset: int
    fixture_instance_id: int
    raw_value: bytes


@dataclass(frozen=True, slots=True)
class LoadedPositionValue:
    source_offset: int
    fixture_instance_id: int
    position_guid: str


@dataclass(frozen=True, slots=True)
class LoadedIntensityNode:
    source_offset: int
    record_version: int
    start_tick: int
    end_tick: int
    attribute_value: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class LoadedTimelineEvent:
    time: int
    source_order: int
    source_offset: int
    reference_kind: Literal["clear_control", "cue"]
    raw_reference: int
    patch: tuple[LoadedAttribute, ...]
    record_version: int = 1
    resolved_stored_key: int | None = None
    resolved_cue_guid: str | None = None
    boundary_frame: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    relative_path: str
    layout: str
    events: tuple[LoadedTimelineEvent, ...]
    intensity_nodes: tuple[LoadedIntensityNode, ...]
    cycle_ticks: int | None = None
    parity_lane: str = field(default="unverified_parity", repr=False)
    parity_evidence: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_MAPPING, repr=False)


@dataclass(frozen=True, slots=True)
class LoadedScriptedTrack:
    soundswitch_id: str
    status: str
    supported_active: bool
    document: LoadedDocument | None


@dataclass(frozen=True, slots=True)
class LoadedAutoloop:
    identity: str
    supported_active: bool
    document: LoadedDocument


@dataclass(frozen=True, slots=True)
class LoadedStaticLook:
    slot_index: int
    record_version: int
    name: str
    generic_attributes: tuple[LoadedAttribute, ...]
    intensity_values: tuple[LoadedScalarValue, ...]
    strobe_values: tuple[LoadedScalarValue, ...]
    colour_values: tuple[LoadedColourValue, ...]
    position_values: tuple[LoadedPositionValue, ...]
    profile_has_intensity_channel: bool = False
    parity_lane: str = field(default="unverified_parity", repr=False)
    parity_evidence: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_MAPPING, repr=False)


@dataclass(frozen=True, slots=True)
class LoadedPack:
    schema_version: str
    manifest_sha256: str
    has_intensity_channel: bool
    scripted: Mapping[str, LoadedScriptedTrack | LoadedDocument]
    autoloops: Mapping[str, LoadedAutoloop | LoadedDocument]
    static_looks: Mapping[int, LoadedStaticLook]
    autoloop_bindings: Mapping[tuple[int, int], LoadedAutoloopBinding] = field(
        default_factory=lambda: _EMPTY_MAPPING)
    bridge_scene_crosswalk: Mapping[str, str] = field(default_factory=lambda: _EMPTY_MAPPING)
    learned_midi_bindings: tuple[PackMidiBinding, ...] = ()
    project_identity: Mapping[str, str | int] = field(default_factory=lambda: _EMPTY_MAPPING)
    supported_boundary: Mapping[str, str | int] = field(default_factory=lambda: _EMPTY_MAPPING)
    source_inventory_sha256: str = ""
    active_cue_union: Mapping[str, str | int] = field(default_factory=lambda: _EMPTY_MAPPING)
    totals: Mapping[str, int] = field(default_factory=lambda: _EMPTY_MAPPING)
    render_cue_guids: frozenset[str] = frozenset()
    catalog_tail_guids: frozenset[str] = frozenset()
    parity_summary: Mapping[str, int] = field(default_factory=lambda: _EMPTY_MAPPING, repr=False)
    unverified_documents: tuple[str, ...] = field(default=(), repr=False)


def _fail(message: str) -> None:
    raise SoundSwitchPackLoadError(message)


def _schema_major(version: Any, relative: str) -> int:
    if not isinstance(version, str):
        _fail(f"mandatory schema_version missing from {relative}")
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdecimal() for part in parts):
        _fail(f"invalid schema_version in {relative}")
    major = int(parts[0])
    if major != SUPPORTED_SCHEMA_MAJOR:
        _fail(f"unsupported schema major {major} in {relative}; runtime migration is forbidden")
    return major


def _read_artifact(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    relative = path.relative_to(root).as_posix()
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SoundSwitchPackLoadError(f"cannot parse verified artifact {relative}: {exc}") from exc
    if not isinstance(value, dict):
        _fail(f"artifact root is not an object: {relative}")
    _schema_major(value.get("schema_version"), relative)
    return value, data


def _integer(value: Any, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an integer")
    return value


def _string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        _fail(f"{label} must be a {'string' if allow_empty else 'non-empty string'}")
    return value


def _parity_lane(value: Any, label: str) -> str:
    if value not in PARITY_LANES:
        _fail(f"{label} parity_lane is invalid")
    return str(value)


def _parity_evidence(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} parity_evidence must be an object")
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, (str, int, bool)) and item is not None:
            _fail(f"{label} parity_evidence is not sanitized")
        sanitized[key] = item
    return MappingProxyType(sanitized)


def _runtime_metadata(
    manifest: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[
    Mapping[str, str],
    tuple[PackMidiBinding, ...],
    Mapping[str, str | int],
    Mapping[str, str | int],
    str,
    Mapping[str, str | int],
    Mapping[str, int],
]:
    """Parse only verified, sanitized runtime metadata; fail closed on drift."""
    scene_rows = selection.get("bridge_scenes")
    if not isinstance(scene_rows, list):
        _fail("bridge scene crosswalk is missing")
    crosswalk: dict[str, str] = {}
    seen_policies: set[str] = set()
    for row in scene_rows:
        if not isinstance(row, dict):
            _fail("bridge scene crosswalk row must be an object")
        policy = _string(row.get("policy_name"), "bridge policy_name")
        if policy in seen_policies:
            _fail(f"duplicate bridge policy_name: {policy}")
        seen_policies.add(policy)
        resolution = row.get("resolution")
        classification = row.get("control_classification")
        target = row.get("target_identity")
        if resolution not in ("project_target", "no_project_target") \
                or classification not in _CONTROL_CLASSIFICATIONS:
            _fail(f"invalid bridge scene semantics for {policy}")
        if resolution == "project_target":
            if classification != "pack_selection":
                _fail(f"project-target bridge scene is not pack_selection: {policy}")
            crosswalk[policy] = _string(target, f"bridge target_identity for {policy}")
        elif target is not None:
            _fail(f"no-target bridge scene carries a target identity: {policy}")
    if not crosswalk:
        _fail("bridge scene crosswalk has no project targets")

    control_rows = selection.get("learned_controls")
    if not isinstance(control_rows, list):
        _fail("learned controller rows are missing")
    bindings: list[PackMidiBinding] = []
    seen_events: set[tuple[str, str, int, int]] = set()
    seen_static_slots: set[tuple[str, int]] = set()
    for row in control_rows:
        if not isinstance(row, dict):
            _fail("learned controller row must be an object")
        active = row.get("active")
        if type(active) is not bool:
            _fail("learned controller active flag must be boolean")
        device = _string(row.get("device_name"), "learned controller device_name")
        message_type = row.get("message_type")
        channel = row.get("channel_zero_based")
        data_byte = row.get("data_byte")
        classification = row.get("control_classification")
        target_kind = row.get("target_kind")
        interaction_mode = row.get("interaction_mode")
        if message_type not in _MESSAGE_TYPES \
                or type(channel) is not int or not 0 <= channel <= 15 \
                or type(data_byte) is not int or not 0 <= data_byte <= 127 \
                or classification not in _CONTROL_CLASSIFICATIONS:
            _fail("malformed learned controller semantics")
        event_key = (device, message_type, channel, data_byte)
        if active:
            if event_key in seen_events:
                _fail("duplicate active learned controller event")
            seen_events.add(event_key)
        if not active or classification not in ("static_override", "blackout_mask"):
            continue
        if message_type != "note":
            _fail("active render controller binding must use a note message")
        if classification == "static_override":
            slot = row.get("target_index")
            if target_kind != "static_look" or type(slot) is not int or not 0 <= slot <= 31:
                _fail("invalid static_override controller target")
            if interaction_mode not in ("press", "toggle"):
                _fail("invalid static_override interaction mode")
            static_key = (device, slot)
            if static_key in seen_static_slots:
                _fail("duplicate active static_override slot ownership")
            seen_static_slots.add(static_key)
            bindings.append(PackMidiBinding(
                device_name=device,
                message_type="note",
                channel_zero_based=channel,
                data_byte=data_byte,
                target_kind="static_look",
                target_slot=slot,
                interaction=interaction_mode,
            ))
        else:
            identity = row.get("target_identity")
            if target_kind not in ("autoloop", "static_look"):
                _fail("invalid blackout_mask controller target kind")
            bindings.append(PackMidiBinding(
                device_name=device,
                message_type="note",
                channel_zero_based=channel,
                data_byte=data_byte,
                target_kind="blackout_mask",
                target_identity=_string(identity, "blackout target_identity"),
            ))

    project = manifest.get("project")
    boundary = manifest.get("supported_boundary")
    source_inventory = manifest.get("source_inventory")
    active_union = manifest.get("active_cue_union")
    totals = manifest.get("totals")
    if not isinstance(project, dict) or not isinstance(boundary, dict) \
            or not isinstance(source_inventory, list) or not isinstance(active_union, dict) \
            or not isinstance(totals, dict):
        _fail("manifest runtime metadata is malformed")
    project_identity: dict[str, str | int] = {
        "container_version": _integer(project.get("container_version"), "container_version"),
        "project_uuid": _string(project.get("project_uuid"), "project_uuid"),
        "soundswitch_version": _string(project.get("soundswitch_version"), "soundswitch_version"),
        "venue_guid": _string(project.get("venue_guid"), "venue_guid"),
    }
    supported_boundary: dict[str, str | int] = {
        "channel_span": _string(boundary.get("channel_span"), "boundary channel_span"),
        "fixture_profile_guid": _string(
            boundary.get("fixture_profile_guid"), "boundary fixture_profile_guid",
        ),
        "project_uuid": _string(boundary.get("project_uuid"), "boundary project_uuid"),
        "soundswitch_version": _string(
            boundary.get("soundswitch_version"), "boundary soundswitch_version",
        ),
        "universe": _integer(boundary.get("universe"), "boundary universe"),
    }
    for row in source_inventory:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) \
                or not isinstance(row.get("sha256"), str) \
                or type(row.get("size")) is not int \
                or not isinstance(row.get("parse_status"), str):
            _fail("source inventory row is malformed")
    source_hash = hashlib.sha256(json.dumps(
        source_inventory,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    union_count = active_union.get("count")
    union_hash = active_union.get("sha256")
    if type(union_count) is not int or not isinstance(union_hash, str):
        _fail("active cue union metadata is malformed")
    active_cue_union: dict[str, str | int] = {
        "count": union_count,
        "sha256": union_hash,
    }
    sanitized_totals: dict[str, int] = {}
    for key, value in totals.items():
        if not isinstance(key, str) or type(value) is not int:
            _fail("manifest totals are malformed")
        sanitized_totals[key] = value
    return (
        MappingProxyType(crosswalk),
        tuple(bindings),
        MappingProxyType(project_identity),
        MappingProxyType(supported_boundary),
        source_hash,
        MappingProxyType(active_cue_union),
        MappingProxyType(sanitized_totals),
    )


def _autoloop_bindings(
    iac_rows: list[Any],
    autoloops: Mapping[str, LoadedAutoloop],
) -> Mapping[tuple[int, int], LoadedAutoloopBinding]:
    bindings: dict[tuple[int, int], LoadedAutoloopBinding] = {}
    for row in iac_rows:
        if not isinstance(row, dict):
            _fail("active IAC selection row must be an object")
        if row.get("active") is not True:
            _fail("active IAC Autoloop row must be active")
        if row.get("device_name") != "IAC Driver Bus 1" \
                or row.get("message_type") != "note" \
                or row.get("target_kind") != "autoloop":
            _fail("active IAC Autoloop row has invalid semantics")
        channel = row.get("channel_zero_based")
        data_byte = row.get("data_byte")
        if type(channel) is not int or not 0 <= channel <= 15 \
                or type(data_byte) is not int or not 0 <= data_byte <= 127:
            _fail("active IAC Autoloop row has invalid channel/note")
        identity = _string(row.get("target_identity"), "Autoloop target_identity")
        name = _string(row.get("target_name"), "Autoloop target_name")
        if identity not in autoloops:
            _fail("active IAC selection references a missing Autoloop")
        key = (channel, data_byte)
        if key in bindings:
            _fail("duplicate active Autoloop note binding")
        bindings[key] = LoadedAutoloopBinding(channel, data_byte, identity, name)
    return MappingProxyType(bindings)


def _attribute(row: dict[str, Any]) -> LoadedAttribute:
    return LoadedAttribute(
        fixture_group=_integer(row.get("fixture_group"), "fixture_group"),
        channel_id=_integer(row.get("channel_id"), "channel_id"),
        dmx_channel=_integer(row.get("dmx_channel"), "dmx_channel"),
        value=_integer(row.get("value"), "attribute value"),
    )


def _scalar(row: dict[str, Any]) -> LoadedScalarValue:
    value = row.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _fail("static scalar value must be numeric")
    return LoadedScalarValue(
        _integer(row.get("source_offset"), "static scalar source_offset"),
        _integer(row.get("fixture_instance_id"), "fixture_instance_id"),
        float(value),
    )


def _colour(row: dict[str, Any]) -> LoadedColourValue:
    raw = row.get("raw_value")
    if not isinstance(raw, str):
        _fail("static colour raw_value must be hexadecimal")
    try:
        data = bytes.fromhex(raw)
    except ValueError as exc:
        raise SoundSwitchPackLoadError("invalid static colour raw_value") from exc
    return LoadedColourValue(
        _integer(row.get("source_offset"), "static colour source_offset"),
        _integer(row.get("fixture_instance_id"), "fixture_instance_id"), data,
    )


def _position(row: dict[str, Any]) -> LoadedPositionValue:
    guid = row.get("position_guid")
    if not isinstance(guid, str):
        _fail("static position GUID must be a string")
    return LoadedPositionValue(
        _integer(row.get("source_offset"), "static position source_offset"),
        _integer(row.get("fixture_instance_id"), "fixture_instance_id"), guid,
    )


def _intensity(row: dict[str, Any]) -> LoadedIntensityNode:
    enabled = row.get("enabled")
    if type(enabled) is not bool:
        _fail("intensity enabled flag must be boolean")
    return LoadedIntensityNode(
        _integer(row.get("source_offset"), "intensity source_offset"),
        _integer(row.get("record_version"), "intensity record_version"),
        _integer(row.get("start_tick"), "intensity start_tick"),
        _integer(row.get("end_tick"), "intensity end_tick"),
        _integer(row.get("attribute_value"), "intensity attribute_value"), enabled,
    )


def _frame(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != 19 or any(
            type(item) is not int or not 0 <= item <= 255 for item in value):
        _fail(f"{label} must contain exactly 19 byte values")
    return tuple(value)


def _document(value: dict[str, Any], cue_patches: Mapping[str, tuple[LoadedAttribute, ...]],
              *, autoloop: bool, renderable: bool = True) -> LoadedDocument:
    timeline = value.get("timeline")
    boundaries = value.get("pre_rendered_boundaries")
    if not isinstance(timeline, list) or not isinstance(boundaries, list):
        _fail("verified timeline/boundary mismatch")
    if renderable and len(timeline) != len(boundaries):
        _fail("verified renderable timeline/boundary mismatch")
    if not renderable and boundaries and len(timeline) != len(boundaries):
        _fail("verified inactive timeline has partial boundaries")
    events = []
    for order, row in enumerate(timeline):
        boundary = boundaries[order] if boundaries else None
        if not isinstance(row, dict) or (boundary is not None and not isinstance(boundary, dict)):
            _fail("timeline/boundary rows must be objects")
        kind = row.get("reference_kind")
        if kind not in ("clear_control", "cue"):
            _fail("unsupported timeline reference kind")
        guid = row.get("resolved_cue_guid")
        if kind == "cue":
            if renderable and (not isinstance(guid, str) or guid not in cue_patches):
                _fail("stale cue in verified timeline")
            patch = cue_patches.get(guid, ()) if isinstance(guid, str) else ()
        else:
            patch = ()
        if boundary is None:
            source_order = order
            boundary_frame = None
        else:
            source_order = _integer(boundary.get("source_order"), "boundary source_order")
            if source_order != order \
                    or boundary.get("source_offset") != row.get("source_offset") \
                    or boundary.get("time") != row.get("time"):
                _fail("boundary provenance does not match timeline")
            boundary_frame = _frame(boundary.get("frame"), "pre-rendered boundary")
        events.append(LoadedTimelineEvent(
            time=_integer(row.get("time"), "timeline time"),
            source_order=source_order,
            source_offset=_integer(row.get("source_offset"), "timeline source_offset"),
            reference_kind=kind,
            raw_reference=_integer(row.get("raw_reference"), "timeline raw_reference"),
            patch=patch,
            record_version=_integer(row.get("record_version"), "timeline record_version"),
            resolved_stored_key=(None if row.get("resolved_stored_key") is None else
                                 _integer(row.get("resolved_stored_key"),
                                          "timeline resolved_stored_key")),
            resolved_cue_guid=guid if isinstance(guid, str) else None,
            boundary_frame=boundary_frame,
        ))
    relative = value.get("relative_path")
    layout = value.get("layout")
    if not isinstance(relative, str) or not isinstance(layout, str):
        _fail("document identity/layout is missing")
    nodes = value.get("intensity_nodes")
    if not isinstance(nodes, list):
        _fail("document intensity nodes are missing")
    return LoadedDocument(relative, layout, tuple(events), tuple(_intensity(row) for row in nodes),
                          AUTOLOOP_CYCLE_TICKS if autoloop else None,
                          _parity_lane(value.get("parity_lane"), f"{relative} document"),
                          _parity_evidence(value.get("parity_evidence"), f"{relative} document"))


def load_pack(pack: str | Path) -> LoadedPack:
    """Verify and immutably load a canonical pack directory.

    Verification intentionally happens before any artifact becomes player
    state.  Every artifact is then independently checked for a mandatory,
    supported schema major.  No runtime migration path exists.
    """
    root = Path(pack).expanduser()
    try:
        verification = verify_pack(root)
    except SoundSwitchPackVerificationError as exc:
        message = str(exc)
        if "render/catalog-tail cue GUIDs" in message:
            message = f"catalog-tail GUID collision: {message}"
        elif "classification does not reconcile to active inventory" in message:
            message = f"active scripted inventory mismatch: {message}"
        raise SoundSwitchPackLoadError(message) from exc
    if verification.get("verified") is not True:
        _fail("independent verifier did not authorize the pack")

    snapshot = {path.relative_to(root).as_posix(): _read_artifact(path, root)
                for path in sorted(root.rglob("*.json"))}
    values = {relative: item[0] for relative, item in snapshot.items()}
    manifest = values.get("manifest.json")
    if manifest is None:
        _fail("manifest.json is missing")
    schema_version = manifest.get("schema_version")
    _schema_major(schema_version, "manifest.json")
    manifest_bytes = snapshot["manifest.json"][1]
    if hashlib.sha256(manifest_bytes).hexdigest() != verification.get("manifest_sha256"):
        _fail("pack changed after independent verification")
    hash_rows = manifest.get("artifact_hashes")
    if not isinstance(hash_rows, list):
        _fail("manifest artifact hash table is missing")
    declared: dict[str, tuple[int, str]] = {}
    for row in hash_rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) \
                or type(row.get("size")) is not int or not isinstance(row.get("sha256"), str):
            _fail("manifest artifact hash row is invalid")
        relative = row["path"]
        if relative in declared:
            _fail("manifest artifact hash path is duplicated")
        declared[relative] = (row["size"], row["sha256"])
    if set(snapshot) != {"manifest.json", *declared}:
        _fail("pack file set changed after independent verification")
    for relative, (expected_size, expected_sha256) in declared.items():
        data = snapshot[relative][1]
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
            _fail(f"pack artifact changed after independent verification: {relative}")

    venue = values.get("venue_cues.json", {})
    records = venue.get("records")
    if not isinstance(records, list):
        _fail("Venue cue records are missing")
    cue_patches: dict[str, tuple[LoadedAttribute, ...]] = {}
    catalog_tail_guids: set[str] = set()
    for row in records:
        if row.get("record_kind") == "minimal_default_catalog_tail":
            guid = row.get("cue_guid")
            if not isinstance(guid, str) or guid in catalog_tail_guids:
                _fail("invalid/duplicate default catalog-tail record")
            catalog_tail_guids.add(guid)
            continue
        if row.get("record_kind") != "fixture_payload":
            _fail("unsupported Venue cue record kind")
        guid = row.get("cue_guid")
        attributes = row.get("attributes")
        if not isinstance(guid, str) or not isinstance(attributes, list) or guid in cue_patches:
            _fail("invalid/duplicate render-bearing Venue cue")
        cue_patches[guid] = tuple(_attribute(attribute) for attribute in attributes)
    if set(cue_patches) & catalog_tail_guids:
        _fail("default catalog-tail GUID must be distinct from render-bearing cues")

    profile = values.get("fixture_profile.json", {})
    has_intensity = profile.get("has_intensity_channel")
    if type(has_intensity) is not bool:
        _fail("fixture intensity-channel declaration is missing")

    static_value = values.get("static_looks.json", {})
    static_rows = static_value.get("records")
    if not isinstance(static_rows, list):
        _fail("Static Look records are missing")
    looks: dict[int, LoadedStaticLook] = {}
    for row in static_rows:
        slot = _integer(row.get("slot_index"), "Static Look slot")
        looks[slot] = LoadedStaticLook(
            slot_index=slot,
            record_version=_integer(row.get("record_version"), "Static Look version"),
            name=row.get("name") if isinstance(row.get("name"), str) else "",
            generic_attributes=tuple(_attribute(item) for item in row.get("generic_attributes", [])),
            intensity_values=tuple(_scalar(item) for item in row.get("intensity_values", [])),
            strobe_values=tuple(_scalar(item) for item in row.get("strobe_values", [])),
            colour_values=tuple(_colour(item) for item in row.get("colour_values", [])),
            position_values=tuple(_position(item) for item in row.get("position_values", [])),
            profile_has_intensity_channel=has_intensity,
            parity_lane=_parity_lane(row.get("parity_lane"), f"Static Look {slot}"),
            parity_evidence=_parity_evidence(row.get("parity_evidence"), f"Static Look {slot}"),
        )

    selection_value = values.get("selection_map.json", {})
    iac_rows = selection_value.get("iac_selections")
    if not isinstance(iac_rows, list):
        _fail("active IAC selection map is missing")
    active_loops = {row.get("target_identity") for row in iac_rows
                    if isinstance(row, dict) and row.get("active") is True
                    and row.get("target_kind") == "autoloop"
                    and isinstance(row.get("target_identity"), str)}

    track_map_value = values.get("track_map.json", {})
    inventory_rows = track_map_value.get("scripted_inventory")
    if not isinstance(inventory_rows, list):
        _fail("scripted active-inventory map is missing")
    active_scripts = {row.get("soundswitch_id", "").lower() for row in inventory_rows
                      if isinstance(row, dict) and row.get("active_existing_path") is True
                      and isinstance(row.get("soundswitch_id"), str)}

    loops: dict[str, LoadedAutoloop] = {}
    for relative, artifact in values.items():
        if not relative.startswith("autoloops/"):
            continue
        doc_value = artifact.get("document")
        if not isinstance(doc_value, dict):
            _fail(f"Autoloop document missing: {relative}")
        doc = _document(doc_value, cue_patches, autoloop=True)
        if doc.relative_path in loops:
            _fail(f"duplicate Autoloop identity: {doc.relative_path}")
        loops[doc.relative_path] = LoadedAutoloop(
            identity=doc.relative_path,
            supported_active=doc.relative_path in active_loops,
            document=doc,
        )
    if not active_loops.issubset(loops):
        _fail("active IAC selection references a missing Autoloop")
    autoloop_bindings = _autoloop_bindings(iac_rows, loops)

    scripts: dict[str, LoadedScriptedTrack] = {}
    for relative, artifact in values.items():
        if not relative.startswith("scripted/"):
            continue
        classification = artifact.get("classification")
        if not isinstance(classification, dict):
            _fail(f"scripted classification missing: {relative}")
        ssid = classification.get("soundswitch_id")
        status = classification.get("status")
        if not isinstance(ssid, str) or not isinstance(status, str):
            _fail(f"scripted identity/status missing: {relative}")
        normalized = ssid.lower()
        if normalized in scripts:
            _fail(f"duplicate normalized soundswitch_id: {ssid}")
        doc_value = artifact.get("document")
        renderable = status == "supported_mapped_primary"
        active = renderable and normalized in active_scripts
        document = (_document(doc_value, cue_patches, autoloop=False, renderable=renderable)
                    if isinstance(doc_value, dict) else None)
        scripts[normalized] = LoadedScriptedTrack(
            soundswitch_id=normalized, status=status,
            supported_active=(active and document is not None),
            document=document,
        )
    authorized_scripts = {ssid for ssid, row in scripts.items() if row.supported_active}
    if active_scripts != authorized_scripts:
        _fail("active scripted inventory is missing or classified unsupported")

    (
        bridge_scene_crosswalk,
        learned_midi_bindings,
        project_identity,
        supported_boundary,
        source_inventory_sha256,
        active_cue_union,
        totals,
    ) = _runtime_metadata(manifest, selection_value)
    if not set(bridge_scene_crosswalk.values()).issubset(loops):
        _fail("bridge scene crosswalk references a missing Autoloop")
    for binding in learned_midi_bindings:
        if binding.target_kind == "static_look" and binding.target_slot not in looks:
            _fail("controller binding references a missing Static Look")
    lanes: list[str] = [look.parity_lane for look in looks.values()]
    unverified = [f"static:{slot}" for slot, look in looks.items()
                  if look.parity_lane == "unverified_parity"]
    for ssid, row in scripts.items():
        if row.document is None:
            continue
        lanes.append(row.document.parity_lane)
        if row.supported_active and row.document.parity_lane == "unverified_parity":
            unverified.append(f"scripted:{ssid}")
    for identity, row in loops.items():
        lanes.append(row.document.parity_lane)
        if row.supported_active and row.document.parity_lane == "unverified_parity":
            unverified.append(f"autoloop:{identity}")

    return LoadedPack(
        schema_version=schema_version,
        manifest_sha256=str(verification.get("manifest_sha256", "")),
        has_intensity_channel=has_intensity,
        scripted=MappingProxyType(scripts), autoloops=MappingProxyType(loops),
        static_looks=MappingProxyType(looks),
        autoloop_bindings=autoloop_bindings,
        bridge_scene_crosswalk=bridge_scene_crosswalk,
        learned_midi_bindings=learned_midi_bindings,
        project_identity=project_identity,
        supported_boundary=supported_boundary,
        source_inventory_sha256=source_inventory_sha256,
        active_cue_union=active_cue_union,
        totals=totals,
        render_cue_guids=frozenset(cue_patches),
        catalog_tail_guids=frozenset(catalog_tail_guids),
        parity_summary=MappingProxyType(count_lanes(lanes)),
        unverified_documents=tuple(sorted(unverified)),
    )


__all__ = [
    "AUTOLOOP_CYCLE_TICKS", "LoadedAttribute", "LoadedAutoloop", "LoadedColourValue", "LoadedDocument",
    "LoadedAutoloopBinding", "LoadedIntensityNode", "LoadedPack", "LoadedPositionValue",
    "LoadedScalarValue", "LoadedScriptedTrack", "LoadedStaticLook", "LoadedTimelineEvent",
    "PackMidiBinding",
    "SoundSwitchPackLoadError", "load_pack",
]
