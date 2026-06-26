"""Deterministic compiler for the bounded SoundSwitch static pack.

This module is pure with respect to project and pack I/O.  It converts the
immutable decoder models into canonical JSON artifact values and pre-renders
the primary fixture's CH1-CH19 boundary frames.  It never imports research
parsers or passive captures.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any, Iterable

from .soundswitch_pack_models import (
    AttributeCue,
    CueAttribute,
    DecodedSoundSwitchProject,
    LightingDocument,
    StaticLook,
)
from .soundswitch_project_decoder import (
    CANONICAL_PROJECT_UUID,
    CANONICAL_SOUNDSWITCH_VERSION,
    CANONICAL_VENUE_GUID,
)

PACK_SCHEMA_VERSION = "1.0.0"
ACTIVE_CUE_UNION_SHA256 = "88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2"
ACTIVE_CUE_UNION_COUNT = 166
PRIMARY_FIXTURE_GROUP = 0x493
CONTROL_CHANNELS = frozenset((8, 9, 11))

# Current bridge policy surface.  These are crosswalk inputs, not invented
# SoundSwitch targets.  The target is resolved from the learned registry.
BRIDGE_SCENES: tuple[tuple[str, int, int], ...] = (
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
CONTROL_CLASSIFICATIONS = (
    "pack_selection", "static_override", "blackout_mask", "bridge_owned_safety",
    "no_project_target", "inactive_report_only", "unsupported_fail_export",
)


class SoundSwitchPackCompileError(ValueError):
    """Decoded source cannot be represented by the pinned pack schema."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root(kind: str, **values: Any) -> dict[str, Any]:
    return {"artifact_type": kind, "schema_version": PACK_SCHEMA_VERSION, **values}


def _hex(data: bytes) -> str:
    return data.hex()


def _attrs(rows: Iterable[CueAttribute]) -> list[dict[str, Any]]:
    return [asdict(row) for row in rows]


def render_static_look_frame(look: StaticLook) -> tuple[int, ...]:
    frame = [0] * 19
    for row in look.generic_attributes:
        if row.fixture_group == PRIMARY_FIXTURE_GROUP and 1 <= row.dmx_channel <= len(frame):
            frame[row.dmx_channel - 1] = row.value
    return tuple(frame)


def render_document_boundaries(
    document: LightingDocument,
    cues_by_guid: dict[str, AttributeCue],
) -> tuple[dict[str, Any], ...]:
    """Render saved-order boundary states for the primary 19-channel fixture.

    Negative records are applied in stored order.  Raw-zero clears the main
    layer while retaining the verified control channels.  Equal-time rows are
    deliberately not re-sorted.
    """
    frame = [0] * 19
    output: list[dict[str, Any]] = []
    for source_order, row in enumerate(document.timeline):
        if row.reference_kind == "clear_control":
            frame = [value if index + 1 in CONTROL_CHANNELS else 0
                     for index, value in enumerate(frame)]
        else:
            cue = cues_by_guid.get(row.resolved_cue_guid or "")
            if cue is None:
                candidate = row.resolved_stored_key
                raise SoundSwitchPackCompileError(
                    f"stale cue: source={document.relative_path}; offset={row.source_offset}; "
                    f"time={row.time}; raw_reference={row.raw_reference}; "
                    f"candidate_key={candidate}; missing_guid={row.resolved_cue_guid}; "
                    "remove/replace the placement in SoundSwitch, save, and re-export"
                )
            for attribute in cue.attributes:
                if (
                    attribute.fixture_group == PRIMARY_FIXTURE_GROUP
                    and 1 <= attribute.dmx_channel <= len(frame)
                ):
                    frame[attribute.dmx_channel - 1] = attribute.value
        output.append({"frame": frame.copy(), "source_order": source_order,
                       "source_offset": row.source_offset, "time": row.time})
    return tuple(output)


def _cue(cue: AttributeCue) -> dict[str, Any]:
    return {
        "attributes": _attrs(cue.attributes), "catalog_indices": list(cue.catalog_indices),
        "cue_guid": cue.cue_guid, "end_offset": cue.end_offset,
        "fixture_profile_guid": cue.fixture_profile_guid, "name": cue.name,
        "record_kind": cue.record_kind, "render_bearing": cue.render_bearing,
        "source_offset": cue.source_offset,
    }


def _look(look: StaticLook) -> dict[str, Any]:
    return {
        "colour_values": [{**asdict(row), "raw_value": _hex(row.raw_value)} for row in look.colour_values],
        "end_offset": look.end_offset, "generic_attributes": _attrs(look.generic_attributes),
        "intensity_values": [asdict(row) for row in look.intensity_values],
        "name": look.name, "position_values": [asdict(row) for row in look.position_values],
        "pre_rendered_frame_ch1_ch19": list(render_static_look_frame(look)),
        "record_version": look.record_version, "slot_index": look.slot_index,
        "source_offset": look.source_offset, "strobe_values": [asdict(row) for row in look.strobe_values],
    }


def _document(document: LightingDocument, cues: dict[str, AttributeCue], *, active: bool = True) -> dict[str, Any]:
    try:
        boundaries = list(render_document_boundaries(document, cues))
        render_status = "rendered"
    except SoundSwitchPackCompileError:
        if active:
            raise
        boundaries = []
        render_status = "unsupported_inactive"
    return {
        "container_version": document.container_version,
        "cue_dictionary": [asdict(row) for row in document.cue_dictionary],
        "cue_map_offset": document.cue_map_offset,
        "fixture_profile_guid": document.fixture_profile_guid,
        "intensity_nodes": [asdict(row) for row in document.intensity_nodes],
        "layout": document.layout,
        "pre_rendered_boundaries": boundaries, "pre_render_status": render_status,
        "relative_path": document.relative_path,
        "retained_footer_sha256": document.retained_footer_sha256,
        "retained_prefix_sha256": document.retained_prefix_sha256,
        "source_sha256": document.source_sha256, "source_size": document.source_size,
        "timeline": [asdict(row) for row in document.timeline],
        "trailer_hex": _hex(document.trailer), "trailer_offset": document.trailer_offset,
    }


def _normalized_ssid(path: str) -> str:
    match = re.fullmatch(r"\{([0-9A-Fa-f-]{36})\}\.ssfile", path)
    if match is None:
        raise SoundSwitchPackCompileError(f"noncanonical scripted path {path!r}")
    return match.group(1).lower()


def _active_script_paths(project: DecodedSoundSwitchProject) -> set[str]:
    existing_ssids = {row.soundswitch_id for row in project.track_map if row.filepath and
                     __import__("pathlib").Path(row.filepath).expanduser().is_file()}
    return {row.relative_path for row in project.scripted_track_classifications
            if row.status == "supported_mapped_primary" and row.soundswitch_id in existing_ssids}


def _active_union(project: DecodedSoundSwitchProject, active_scripts: set[str]) -> tuple[list[str], str]:
    active_loops = {row.target_identity for row in project.resolved_controls
                    if row.binding.enabled and row.binding.device_name == "IAC Driver Bus 1"
                    and row.target_kind == "autoloop" and row.target_identity}
    documents = [row for row in (*project.autoloops, *project.scripted_tracks)
                 if row.relative_path in active_loops or row.relative_path in active_scripts]
    guids = sorted({event.resolved_cue_guid.lower() for doc in documents for event in doc.timeline
                    if event.resolved_cue_guid})
    return guids, sha256_bytes("\n".join(guids).encode("ascii"))


def _selection_map(project: DecodedSoundSwitchProject) -> dict[str, Any]:
    controls = []
    event_targets: dict[tuple[str, int, int], dict[str, Any]] = {}
    for row in project.resolved_controls:
        b = row.binding
        if not b.enabled or row.target_kind == "non_render":
            classification = "inactive_report_only"
        elif row.target_kind == "static_look":
            classification = "static_override"
        elif (b.device_name, b.channel_zero_based, b.data_byte, row.target_kind) == \
                ("IAC Driver Bus 1", 0, 0, "autoloop"):
            classification = "blackout_mask"
        else:
            classification = "pack_selection"
        item = {"active": b.enabled, "channel_zero_based": b.channel_zero_based,
                "collection_id": b.collection_id, "control_path": b.control_path,
                "control_classification": classification,
                "data_byte": b.data_byte, "device_name": b.device_name,
                "message_type": b.message_type, "source_offset": b.source_offset,
                "target_identity": row.target_identity, "target_index": row.target_index,
                "target_kind": row.target_kind, "target_name": row.target_name}
        if row.target_kind == "static_look":
            item["interaction_mode"] = row.interaction_mode
        controls.append(item)
        if b.enabled and b.device_name == "IAC Driver Bus 1" and b.message_type == "note":
            event_targets[(b.device_name, b.channel_zero_based, b.data_byte)] = item
    controls.sort(key=lambda row: (row["device_name"], row["channel_zero_based"],
                                  row["data_byte"], row["control_path"], row["source_offset"]))
    scenes = []
    for name, channel, note in BRIDGE_SCENES:
        target = event_targets.get(("IAC Driver Bus 1", channel, note))
        if name == "house_post_drop_1":
            classification = "inactive_report_only"
        elif target:
            classification = "pack_selection"
        elif channel == 1 and note in (0, 1, 2):
            classification = "bridge_owned_safety"
        else:
            classification = "no_project_target"
        scenes.append({"channel_zero_based": channel, "data_byte": note,
                       "control_classification": classification,
                       "policy_name": name,
                       "resolution": "project_target" if target else "no_project_target",
                       "target_identity": target["target_identity"] if target else None,
                       "target_kind": target["target_kind"] if target else None})
    blackout = event_targets.get(("IAC Driver Bus 1", 0, 0))
    iac_selections = [row for row in controls if row["active"]
                      and row["device_name"] == "IAC Driver Bus 1"
                      and row["target_kind"] == "autoloop"]
    ddj_overrides = [row for row in controls if row["active"]
                     and row["device_name"] == "DDJ-800"
                     and row["target_kind"] == "static_look"]
    return _root("selection_map", bridge_scenes=scenes,
                 classification_policy={name: (
                     "export_fails before publication" if name == "unsupported_fail_export"
                     else "retained explicit control classification")
                     for name in CONTROL_CLASSIFICATIONS},
                 manual_blackout={"channel_zero_based": 0, "data_byte": 0,
                                   "control_classification": "blackout_mask",
                                   "resolution": "project_target" if blackout else "no_project_target",
                                   "target_identity": blackout["target_identity"] if blackout else None},
                 learned_controls=controls, iac_selections=iac_selections,
                 ddj_static_overrides=ddj_overrides,
                 no_target_policy_inputs=[asdict(row) | {
                     "control_classification": "no_project_target"}
                     for row in project.no_target_policy_inputs])


def compile_pack_artifacts(
    project: DecodedSoundSwitchProject,
    *, generator_commit: str,
    enforce_pinned_totals: bool = True,
) -> dict[str, bytes]:
    if project.identity.project_uuid != CANONICAL_PROJECT_UUID or \
            project.identity.soundswitch_version != CANONICAL_SOUNDSWITCH_VERSION or \
            project.identity.venue_guid != CANONICAL_VENUE_GUID:
        raise SoundSwitchPackCompileError("source identity is outside the pinned boundary")
    if any(row.active for row in project.diagnostics):
        raise SoundSwitchPackCompileError("active unsupported diagnostics block publication")
    # F10: active render-affecting controls must use the "note" message type.
    # CC/pitch-bend bindings on static_look or autoloop targets are unsupported;
    # the operator must relearn the control to a note-capable mapping in SoundSwitch.
    for row in project.resolved_controls:
        b = row.binding
        if b.enabled and row.target_kind in ("static_look", "autoloop") and b.message_type != "note":
            raise SoundSwitchPackCompileError(
                f"active render-affecting control uses unsupported MIDI message type "
                f"{b.message_type!r} at {b.device_name!r} ch{b.channel_zero_based} "
                f"data_byte={b.data_byte} path={b.control_path!r}: "
                "relearn to a note-capable control in SoundSwitch, save, and re-export"
            )
    cues = {row.cue_guid: row for row in project.render_cues}
    active_scripts = _active_script_paths(project)
    union, union_sha = _active_union(project, active_scripts)
    enabled_iac = [r for r in project.resolved_controls if r.binding.enabled
                   and r.binding.device_name == "IAC Driver Bus 1" and r.target_kind == "autoloop"]
    enabled_ddj = [r for r in project.resolved_controls if r.binding.enabled
                   and r.binding.device_name == "DDJ-800" and r.target_kind == "static_look"]
    if enforce_pinned_totals:
        actual = (len(project.render_cues), len(project.catalog_tail_cues), len(project.attribute_cues),
                  len(project.static_looks), len(project.autoloops),
                  len(project.scripted_track_classifications), len(project.scripted_tracks),
                  len(active_scripts), len(enabled_iac), len(enabled_ddj), len(union), union_sha)
        expected = (232, 1, 233, 32, 42, 45, 44, 32, 19, 4,
                    ACTIVE_CUE_UNION_COUNT, ACTIVE_CUE_UNION_SHA256)
        if actual != expected:
            raise SoundSwitchPackCompileError(f"pinned current-project totals drifted: expected={expected!r}; actual={actual!r}")

    artifacts: dict[str, bytes] = {}
    def add(path: str, value: dict[str, Any]) -> None:
        artifacts[path] = canonical_json_bytes(value)

    add("fixture_profile.json", _root("fixture_profile", universe=0, channel_span="CH1-CH19",
        fixture_profile_guid=project.identity.venue_guid, has_intensity_channel=False,
        channels=[asdict(row) for row in project.fixture_channels]))
    add("venue_cues.json", _root("venue_cues", render_cue_count=len(project.render_cues),
        catalog_tail_count=len(project.catalog_tail_cues), total_record_count=len(project.attribute_cues),
        records=[_cue(row) for row in project.attribute_cues]))
    add("static_looks.json", _root("static_looks", count=len(project.static_looks),
        records=[_look(row) for row in project.static_looks]))
    add("midi_mappings.json", _root("midi_mappings", maps=[{
        "relative_path": m.relative_path, "source_sha256": m.source_sha256, "status": m.status,
        "version": m.version, "devices": [{"name": d.name, "feedback_hex": _hex(d.feedback_bytes),
        "collections": [{"collection_id": c.collection_id,
        "bindings": [asdict(b) for b in c.bindings]} for c in d.collections]} for d in m.devices]
    } for m in project.learned_midi_maps]))
    add("selection_map.json", _selection_map(project))
    add("track_map.json", _root("track_map", records=[{
        "artist": row.artist, "locator_state": row.locator_state,
        "saved_locator_sha256": sha256_bytes(row.filepath.encode("utf-8")),
        "soundswitch_id": row.soundswitch_id, "source_offset": row.source_offset,
        "title": row.title} for row in project.track_map],
        scripted_inventory=[asdict(row) | {"active_existing_path": row.relative_path in active_scripts}
                            for row in sorted(project.scripted_track_classifications,
                                              key=lambda item: item.soundswitch_id)]))
    for doc in sorted(project.autoloops, key=lambda row: int(re.search(r"(\d+)", row.relative_path).group(1))):
        number = int(re.search(r"(\d+)", doc.relative_path).group(1))
        add(f"autoloops/{number}.json", _root("autoloop", document=_document(doc, cues)))
    classes = {row.relative_path: row for row in project.scripted_track_classifications}
    decoded = {row.relative_path: row for row in project.scripted_tracks}
    for path, classification in sorted(classes.items()):
        identity = _normalized_ssid(path)
        doc = decoded.get(path)
        add(f"scripted/{identity}.json", _root("scripted", classification=asdict(classification),
            document=_document(doc, cues, active=path in active_scripts) if doc is not None else None,
            unsupported_inactive=doc is None))
    add("import_report.json", _root("import_report",
        diagnostics=sorted((asdict(row) for row in project.diagnostics),
                           key=lambda row: (row["relative_path"], row["code"], row["offset"] or -1, row["message"])),
        hardware_status="SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED"))

    artifact_rows = [{"path": path, "sha256": sha256_bytes(data), "size": len(data)}
                     for path, data in sorted(artifacts.items())]
    totals = {"active_cue_union": len(union), "active_existing_path_scripted": len(active_scripts),
              "catalog_tail_records": len(project.catalog_tail_cues), "ddj_static_overrides": len(enabled_ddj),
              "iac_autoloop_bindings": len(enabled_iac), "learned_mappings": sum(
                  len(c.bindings) for m in project.learned_midi_maps for d in m.devices for c in d.collections),
              "parsed_scripted": len(project.scripted_tracks), "render_cues": len(project.render_cues),
              "scripted_inventory": len(project.scripted_track_classifications),
              "static_looks": len(project.static_looks), "total_autoloops": len(project.autoloops),
              "total_venue_records": len(project.attribute_cues)}
    diagnostics_by_path: dict[str, list[str]] = {}
    for diagnostic in project.diagnostics:
        diagnostics_by_path.setdefault(diagnostic.relative_path, []).append(diagnostic.code)
    def parse_status(path: str) -> str:
        codes = diagnostics_by_path.get(path, [])
        if "unsupported_inactive_script" in codes:
            return "unsupported_inactive"
        if "opaque_artifact" in codes:
            return "retained_opaque"
        if codes:
            return "decoded_with_inactive_diagnostic"
        return "decoded"
    manifest = _root("manifest", generator={"commit": generator_commit, "name": "rb_ss_bridge_v2"},
        project={"container_version": project.identity.container_version,
                 "project_uuid": project.identity.project_uuid,
                 "soundswitch_version": project.identity.soundswitch_version,
                 "venue_guid": project.identity.venue_guid, "venue_name": project.identity.venue_name},
        source_inventory=[{"parse_status": parse_status(row.relative_path), "path": row.relative_path,
                           "sha256": row.sha256, "size": row.size} for row in project.source_inventory],
        artifact_hashes=artifact_rows, totals=totals,
        active_cue_union={"count": len(union), "sha256": union_sha},
        supported_boundary={"channel_span": "CH1-CH19", "fixture_profile_guid": CANONICAL_VENUE_GUID,
                            "project_uuid": CANONICAL_PROJECT_UUID, "soundswitch_version": "2.10.3",
                            "universe": 0})
    artifacts["manifest.json"] = canonical_json_bytes(manifest)
    return dict(sorted(artifacts.items()))


__all__ = ["ACTIVE_CUE_UNION_COUNT", "ACTIVE_CUE_UNION_SHA256", "PACK_SCHEMA_VERSION",
           "SoundSwitchPackCompileError", "canonical_json_bytes", "compile_pack_artifacts",
           "render_document_boundaries", "render_static_look_frame", "sha256_bytes"]
