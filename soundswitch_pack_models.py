"""Immutable source models for the bounded SoundSwitch pack exporter.

These models describe saved SoundSwitch project bytes only.  They contain no
runtime, MIDI, network, serial, or device behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SourceFile:
    relative_path: str
    size: int
    sha256: str
    mtime_ns: int
    mode: int


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    project_uuid: str
    soundswitch_version: str
    container_version: int
    venue_guid: str
    venue_name: str


@dataclass(frozen=True, slots=True)
class SourceDiagnostic:
    code: str
    relative_path: str
    message: str
    offset: int | None = None
    active: bool = False


@dataclass(frozen=True, slots=True)
class FixtureChannel:
    source_offset: int
    channel_id: int
    dmx_channel: int
    name: str


@dataclass(frozen=True, slots=True)
class CueAttribute:
    source_offset: int
    fixture_group: int
    channel_id: int
    dmx_channel: int
    value: int


@dataclass(frozen=True, slots=True)
class AttributeCue:
    source_offset: int
    end_offset: int
    record_kind: Literal["fixture_payload", "minimal_default_catalog_tail"]
    name: str
    cue_guid: str
    fixture_profile_guid: str | None
    attributes: tuple[CueAttribute, ...]
    catalog_indices: tuple[int, ...] = ()

    @property
    def render_bearing(self) -> bool:
        return self.record_kind == "fixture_payload"


@dataclass(frozen=True, slots=True)
class StaticScalarValue:
    source_offset: int
    fixture_instance_id: int
    value: float


@dataclass(frozen=True, slots=True)
class StaticColourValue:
    source_offset: int
    fixture_instance_id: int
    raw_value: bytes


@dataclass(frozen=True, slots=True)
class StaticPositionValue:
    source_offset: int
    fixture_instance_id: int
    position_guid: str


@dataclass(frozen=True, slots=True)
class StaticLook:
    source_offset: int
    end_offset: int
    slot_index: int
    record_version: int
    name: str
    intensity_values: tuple[StaticScalarValue, ...]
    strobe_values: tuple[StaticScalarValue, ...]
    colour_values: tuple[StaticColourValue, ...]
    position_values: tuple[StaticPositionValue, ...]
    generic_attributes: tuple[CueAttribute, ...]


@dataclass(frozen=True, slots=True)
class CueDictionaryEntry:
    source_offset: int
    cue_guid: str
    stored_key: int


@dataclass(frozen=True, slots=True)
class TimelineRecord:
    source_offset: int
    record_version: int
    time: int
    raw_reference: int
    reference_kind: Literal["clear_control", "cue"]
    resolved_stored_key: int | None
    resolved_cue_guid: str | None


@dataclass(frozen=True, slots=True)
class IntensityNode:
    source_offset: int
    record_version: int
    start_tick: int
    end_tick: int
    attribute_value: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class LightingDocument:
    relative_path: str
    source_sha256: str
    source_size: int
    container_version: int
    fixture_profile_guid: str
    layout: str
    cue_map_offset: int
    cue_dictionary: tuple[CueDictionaryEntry, ...]
    timeline: tuple[TimelineRecord, ...]
    intensity_nodes: tuple[IntensityNode, ...]
    trailer_offset: int
    trailer: bytes
    retained_prefix_sha256: str
    retained_footer_sha256: str | None


@dataclass(frozen=True, slots=True)
class AutoloopCatalogEntry:
    source_offset: int
    ordering: int
    app_log_index: int
    file_number: int
    enabled: bool
    display_name: str
    category_index: int
    category: str


@dataclass(frozen=True, slots=True)
class AutoloopCategory:
    source_offset: int
    category_index: int
    name: str
    enabled: bool
    app_log_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AutoloopCatalog:
    relative_path: str
    source_sha256: str
    version: int
    layout: int
    categories: tuple[AutoloopCategory, ...]
    entries: tuple[AutoloopCatalogEntry, ...]


@dataclass(frozen=True, slots=True)
class TrackMapRecord:
    source_offset: int
    soundswitch_id: str
    title: str | None
    artist: str | None
    filepath: str
    locator_state: Literal["saved_unverified"] = "saved_unverified"


@dataclass(frozen=True, slots=True)
class ScriptedTrackClassification:
    soundswitch_id: str
    relative_path: str
    fixture_profile_guid: str
    track_map_mapping_count: int
    status: Literal[
        "supported_mapped_primary",
        "inactive_unmapped_alternate_profile",
        "inactive_unmapped_primary",
        "inactive_bundled_demo",
    ]


@dataclass(frozen=True, slots=True)
class MidiBinding:
    source_offset: int
    device_name: str
    collection_id: int
    message_type: Literal["note", "control_change", "pitch_bend"]
    message_type_raw: int
    data_byte: int
    channel_zero_based: int
    control_path: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class MidiCollection:
    collection_id: int
    bindings: tuple[MidiBinding, ...]


@dataclass(frozen=True, slots=True)
class MidiDevice:
    name: str
    collections: tuple[MidiCollection, ...]
    feedback_bytes: bytes


@dataclass(frozen=True, slots=True)
class LearnedMidiMap:
    relative_path: str
    source_sha256: str
    version: int
    status: int
    devices: tuple[MidiDevice, ...]


@dataclass(frozen=True, slots=True)
class ResolvedControlBinding:
    binding: MidiBinding
    target_kind: Literal["autoloop", "static_look", "no_target", "non_render"]
    target_identity: str | None
    target_index: int | None
    target_name: str | None = None


@dataclass(frozen=True, slots=True)
class NoTargetPolicyInput:
    """A bridge policy input intentionally lacking a SoundSwitch learned target."""
    policy_name: str
    reason: str = "intentionally unmapped in the source project"


@dataclass(frozen=True, slots=True)
class DecodedSoundSwitchProject:
    identity: ProjectIdentity
    source_inventory: tuple[SourceFile, ...]
    fixture_channels: tuple[FixtureChannel, ...]
    attribute_cues: tuple[AttributeCue, ...]
    static_looks: tuple[StaticLook, ...]
    autoloop_catalogs: tuple[AutoloopCatalog, ...]
    autoloops: tuple[LightingDocument, ...]
    scripted_tracks: tuple[LightingDocument, ...]
    scripted_track_classifications: tuple[ScriptedTrackClassification, ...]
    track_map: tuple[TrackMapRecord, ...]
    learned_midi_maps: tuple[LearnedMidiMap, ...]
    resolved_controls: tuple[ResolvedControlBinding, ...]
    no_target_policy_inputs: tuple[NoTargetPolicyInput, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    @property
    def render_cues(self) -> tuple[AttributeCue, ...]:
        return tuple(cue for cue in self.attribute_cues if cue.render_bearing)

    @property
    def catalog_tail_cues(self) -> tuple[AttributeCue, ...]:
        return tuple(cue for cue in self.attribute_cues if not cue.render_bearing)
