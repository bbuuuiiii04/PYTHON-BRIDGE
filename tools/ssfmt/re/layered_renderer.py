#!/usr/bin/env python3
"""Research-only layered renderer for decoded SoundSwitch timeline records.

This is deliberately not a production parser or bridge dependency. It keeps
layer ownership and initial-state assumptions explicit so passive captures can
falsify a hypothesis instead of becoming hidden renderer input.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


CHANNEL_COUNT = 19
TRANSPORT_STATES = {"playing", "paused", "ended", "unloaded"}


@dataclass
class LayeredState:
    inherited: tuple[int, ...] = (0,) * CHANNEL_COUNT
    main: dict[int, int] = field(default_factory=dict)
    controls: dict[str, dict[int, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.inherited) != CHANNEL_COUNT:
            raise ValueError(f"inherited state must contain {CHANNEL_COUNT} channels")

    def apply_patch(
        self,
        patch: dict[int, int],
        control_channels: set[int],
        control_layer: str = "fixture_control",
    ) -> None:
        controls = self.controls.setdefault(control_layer, {})
        for channel, value in patch.items():
            if not 1 <= channel <= CHANNEL_COUNT:
                raise ValueError(f"patch channel {channel} is outside CH1..CH19")
            if not 0 <= value <= 255:
                raise ValueError(f"patch value {value} is outside byte range")
            if channel in control_channels:
                controls[channel] = value
            else:
                self.main[channel] = value

    def clear_main(self) -> None:
        self.main = {channel: 0 for channel in range(1, CHANNEL_COUNT + 1)}

    def rendered(self) -> tuple[int, ...]:
        state = list(self.inherited)
        for channel, value in self.main.items():
            state[channel - 1] = value
        for layer in self.controls.values():
            for channel, value in layer.items():
                state[channel - 1] = value
        return tuple(state)

    def snapshot(self) -> dict:
        return {
            "inherited_state": list(self.inherited),
            "main_layer": {str(channel): value for channel, value in sorted(self.main.items())},
            "control_layers": {
                name: {str(channel): value for channel, value in sorted(values.items())}
                for name, values in sorted(self.controls.items())
            },
            "rendered_state": list(self.rendered()),
        }


def venue_cue_records(cues: Iterable[dict], fixture_group: str) -> dict[str, dict]:
    return {
        cue["cue_guid"]: {
            "name": cue["name"],
            "offset": cue["offset"],
            "patch": {
                int(channel): value
                for channel, value in cue["groups"].get(fixture_group, {}).items()
            },
        }
        for cue in cues
    }


def render_timeline(
    parsed: dict,
    cue_records: dict[str, dict],
    *,
    time_key: str,
    initial_state: tuple[int, ...] = (0,) * CHANNEL_COUNT,
    initial_state_policy: str = "all_zero",
    control_channels: Iterable[int] = (),
    owner_deck: int | None = None,
) -> list[dict]:
    """Resolve and render already-structurally-decoded timeline records."""
    control_channel_set = set(control_channels)
    if any(channel < 1 or channel > CHANNEL_COUNT for channel in control_channel_set):
        raise ValueError("control channels must be within CH1..CH19")
    dictionary = {entry["cue_index"]: entry for entry in parsed["cues"]}
    state = LayeredState(inherited=initial_state)
    previous = state.rendered()
    rows = []
    for sequence, event in enumerate(parsed["timeline"]):
        raw_reference = event["raw_cue_reference"]
        resolved_index = event["resolved_dictionary_index"]
        reference_kind = event["reference_kind"]
        dictionary_entry = dictionary.get(resolved_index) if resolved_index is not None else None
        guid = dictionary_entry["guid"] if dictionary_entry is not None else None
        cue = cue_records.get(guid) if guid is not None else None
        source_decode_error = None
        event_kind = reference_kind

        if event[time_key] < 0:
            event_kind = "negative_time_sentinel"
        elif reference_kind == "clear_control":
            state.clear_main()
        else:
            if dictionary_entry is None:
                source_decode_error = f"dictionary index {resolved_index} is absent"
            elif cue is None:
                source_decode_error = f"Venue cue {guid} is absent"
            else:
                state.apply_patch(cue["patch"], control_channel_set)

        rendered = state.rendered()
        rows.append(
            {
                "sequence": sequence,
                "source_sequence": event.get("source_sequence", sequence),
                "record_offset": event["offset"],
                "time": event[time_key],
                "time_field": time_key,
                "raw_cue_reference": raw_reference,
                "resolved_dictionary_index": resolved_index,
                "reference_kind": reference_kind,
                "event_kind": event_kind,
                "dictionary_record_offset": (
                    dictionary_entry["offset"] if dictionary_entry is not None else None
                ),
                "guid": guid,
                "cue_name": cue["name"] if cue is not None else None,
                "venue_cue_record_offset": cue["offset"] if cue is not None else None,
                "patch": dict(sorted(cue["patch"].items())) if cue is not None else {},
                "source_decode_error": source_decode_error,
                "owner_deck": owner_deck,
                "initial_state_policy": initial_state_policy,
                "state": state.snapshot(),
                "changes_state": rendered != previous,
            }
        )
        previous = rendered
    return rows


def render_at_elapsed(
    parsed: dict,
    cue_records: dict[str, dict],
    elapsed_ms: int | float,
    *,
    initial_state: tuple[int, ...] = (0,) * CHANNEL_COUNT,
    initial_state_policy: str = "all_zero",
    control_channels: Iterable[int] = (),
    owner_deck: int | None = None,
) -> dict:
    """Rebuild a scripted frame as a pure function of playback elapsed.

    Scripted records are ordered by elapsed time and then by their stored source
    order. Replaying from the explicit initial state on every call makes seeks,
    pause/resume samples, and loop-back queries independent of prior calls. The
    ordering policy is wire-supported for specific Opalite seek/loop/refire
    samples, but remains a research hypothesis outside the captured base-render
    scope.
    """
    if elapsed_ms < 0:
        raise ValueError("scripted elapsed_ms must be non-negative")
    reference_rule = parsed.get("reference_rule")
    if reference_rule not in {"direct", "one_based"}:
        raise ValueError(
            "scripted render requires explicit direct or one_based provenance; "
            f"got {reference_rule or 'unspecified'}"
        )

    eligible = []
    for source_sequence, event in enumerate(parsed["timeline"]):
        event_time = event["elapsed"]
        if 0 <= event_time <= elapsed_ms:
            eligible.append(
                (
                    event_time,
                    source_sequence,
                    {**event, "source_sequence": source_sequence},
                )
            )
    eligible.sort(key=lambda row: (row[0], row[1]))
    selected = [row[2] for row in eligible]
    rows = render_timeline(
        {**parsed, "timeline": selected},
        cue_records,
        time_key="elapsed",
        initial_state=initial_state,
        initial_state_policy=initial_state_policy,
        control_channels=control_channels,
        owner_deck=owner_deck,
    )
    if rows:
        state = rows[-1]["state"]
    else:
        state = LayeredState(inherited=initial_state).snapshot()
    return {
        "elapsed_ms": elapsed_ms,
        "reference_rule": reference_rule,
        "timeline_order_policy": "elapsed_then_source_sequence",
        "initial_state_policy": initial_state_policy,
        "applied_event_count": len(rows),
        "active_event": rows[-1] if rows else None,
        "state": state,
        "source_decode_errors": sorted(
            {
                row["source_decode_error"]
                for row in rows
                if row["source_decode_error"] is not None
            }
        ),
    }


def render_playback_state(
    parsed: dict,
    cue_records: dict[str, dict],
    elapsed_ms: int | float,
    transport_state: str,
    *,
    initial_state: tuple[int, ...] = (0,) * CHANNEL_COUNT,
    initial_state_policy: str = "all_zero",
    control_channels: Iterable[int] = (),
    owner_deck: int | None = None,
) -> dict:
    """Render a transport-aware scripted frame without mutable history.

    Playing and paused states are both pure render-at-elapsed queries. A seek,
    loop-back, or re-fire is therefore just another query at its new elapsed
    position. Ended and unloaded states explicitly clear every channel rather
    than retaining timeline layers. The policy is research-only until each edge
    has passive wire evidence. The current evidence covers representative
    Opalite edges but does not make the underlying scripted renderer complete.
    """
    if transport_state not in TRANSPORT_STATES:
        raise ValueError(
            f"transport_state must be one of {sorted(TRANSPORT_STATES)}; "
            f"got {transport_state!r}"
        )
    reference_rule = parsed.get("reference_rule")
    if reference_rule not in {"direct", "one_based"}:
        raise ValueError(
            "scripted render requires explicit direct or one_based provenance; "
            f"got {reference_rule or 'unspecified'}"
        )
    if transport_state in {"ended", "unloaded"}:
        return {
            "elapsed_ms": elapsed_ms,
            "reference_rule": reference_rule,
            "transport_state": transport_state,
            "transport_output_policy": "all_zero_idle",
            "timeline_order_policy": "elapsed_then_source_sequence",
            "initial_state_policy": initial_state_policy,
            "applied_event_count": 0,
            "active_event": None,
            "state": LayeredState(inherited=(0,) * CHANNEL_COUNT).snapshot(),
            "source_decode_errors": [],
        }
    rendered = render_at_elapsed(
        parsed,
        cue_records,
        elapsed_ms,
        initial_state=initial_state,
        initial_state_policy=initial_state_policy,
        control_channels=control_channels,
        owner_deck=owner_deck,
    )
    return {
        **rendered,
        "transport_state": transport_state,
        "transport_output_policy": "render_at_elapsed",
    }
