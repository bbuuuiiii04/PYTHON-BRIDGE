#!/usr/bin/env python3
"""Validate a scripted timeline against passive Art-Net frames.

Research helper only. The default CH11 control-layer assignment is a named,
A5-specific hypothesis and is never presented as a universal format rule.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path

from analyze_scripted_ssfile import parse_scripted_structure, shared_table_from_autoloop
from layered_renderer import render_timeline, venue_cue_records
from parse_artnet_pcap import universe_frames
from parse_venue_cues import parse_venue_cues


def changed_frames(
    frames: list[tuple[float, tuple[int, ...]]]
) -> list[tuple[float, tuple[int, ...]]]:
    changed = []
    previous = None
    for timestamp, state in frames:
        if state != previous:
            changed.append((timestamp, state))
            previous = state
    return changed


def frame_at(
    frames: list[tuple[float, tuple[int, ...]]],
    timestamps: list[float],
    timestamp: float,
) -> tuple[int, ...] | None:
    index = bisect.bisect_right(timestamps, timestamp) - 1
    return frames[index][1] if index >= 0 else None


def fit_start(
    frames: list[tuple[float, tuple[int, ...]]], events: list[dict], sample_delay: float
) -> tuple[float, tuple] | None:
    changes = changed_frames(frames)
    timestamps = [row[0] for row in frames]
    candidates = []
    for event in events:
        state = tuple(event["state"]["rendered_state"])
        if not event["changes_state"]:
            continue
        for timestamp, wire_state in changes:
            if wire_state == state:
                candidates.append(timestamp - event["time"] / 1000.0)
    best = None
    for start in candidates:
        exact = in_window = 0
        residuals = []
        for event in events:
            expected_time = start + event["time"] / 1000.0
            if not frames[0][0] <= expected_time <= frames[-1][0]:
                continue
            in_window += 1
            expected = tuple(event["state"]["rendered_state"])
            exact += frame_at(frames, timestamps, expected_time + sample_delay) == expected
            if event["changes_state"]:
                matches = [
                    abs(timestamp - expected_time)
                    for timestamp, wire_state in changes
                    if wire_state == expected
                ]
                if matches:
                    residuals.append(min(matches))
        score = (exact, in_window, -sum(residuals), -max(residuals, default=0.0))
        if best is None or score > best[0]:
            best = (score, start)
    return (best[1], best[0]) if best else None


def fit_ordered_timing(changes: list[tuple], events: list[dict]) -> dict | None:
    expected = [event for event in events if event["changes_state"]]
    if not expected or len(changes) < len(expected):
        return None
    best = None
    for offset in range(len(changes) - len(expected) + 1):
        window = changes[offset : offset + len(expected)]
        start = window[0][0] - expected[0]["time"] / 1000.0
        residuals = [
            observed[0] - (start + event["time"] / 1000.0)
            for event, observed in zip(expected, window)
        ]
        rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
        score = (max(abs(value) for value in residuals), rms)
        if best is None or score < best[0]:
            best = (
                score,
                {
                    "start": start,
                    "wire_change_offset": offset,
                    "matched": {
                        event["sequence"]: observed[0]
                        for event, observed in zip(expected, window)
                    },
                },
            )
    return best[1] if best else None


def channel_residuals(expected: tuple[int, ...], actual: tuple[int, ...] | None) -> list[dict]:
    if actual is None:
        return [
            {"channel": channel, "expected": value, "actual": None, "delta": None}
            for channel, value in enumerate(expected, start=1)
        ]
    return [
        {
            "channel": channel,
            "expected": expected_value,
            "actual": actual_value,
            "delta": actual_value - expected_value,
        }
        for channel, (expected_value, actual_value) in enumerate(zip(expected, actual), start=1)
        if expected_value != actual_value
    ]


def parse_channels(raw: str) -> tuple[int, ...]:
    try:
        channels = tuple(sorted({int(value) for value in raw.split(",") if value.strip()}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("control channels must be comma-separated integers") from error
    if any(channel < 1 or channel > 19 for channel in channels):
        raise argparse.ArgumentTypeError("control channels must be within CH1..CH19")
    return channels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    parser.add_argument("scripted_file", type=Path)
    parser.add_argument("--autoloop-reference", required=True, type=Path)
    parser.add_argument("--venue", required=True, type=Path)
    parser.add_argument("--fixture-group", default="0x493")
    parser.add_argument("--control-channels", default="11")
    parser.add_argument("--sample-delay-ms", type=float, default=30.0)
    parser.add_argument("--owner-deck", type=int)
    args = parser.parse_args()

    control_channels = parse_channels(args.control_channels)
    frames = universe_frames(args.pcap)
    if not frames:
        raise SystemExit("no Universe-0 ArtDmx frames")
    scripted_bytes = args.scripted_file.read_bytes()
    venue_bytes = args.venue.read_bytes()
    parsed = parse_scripted_structure(
        scripted_bytes, shared_table_from_autoloop(args.autoloop_reference)
    )
    events = render_timeline(
        parsed,
        venue_cue_records(parse_venue_cues(venue_bytes), args.fixture_group),
        time_key="elapsed",
        initial_state=(0,) * 19,
        initial_state_policy="all_zero_static_render",
        control_channels=control_channels,
        owner_deck=args.owner_deck,
    )
    changes = changed_frames(frames)
    exact_fit = fit_start(frames, events, args.sample_delay_ms / 1000.0)
    ordered_fit = None if exact_fit else fit_ordered_timing(changes, events)
    if exact_fit:
        start = exact_fit[0]
        fit_mode = "exact_layered_state_anchor"
        ordered_matches = {}
    elif ordered_fit:
        start = ordered_fit["start"]
        fit_mode = "ordered_transition_timing_only"
        ordered_matches = ordered_fit["matched"]
    else:
        raise SystemExit("unable to fit scripted timeline to capture")

    timestamps = [row[0] for row in frames]
    checked = []
    for event in events:
        expected_time = start + event["time"] / 1000.0
        if not frames[0][0] <= expected_time <= frames[-1][0]:
            continue
        expected = tuple(event["state"]["rendered_state"])
        actual = frame_at(
            frames, timestamps, expected_time + args.sample_delay_ms / 1000.0
        )
        residuals = channel_residuals(expected, actual)
        transition_residual_ms = None
        if event["sequence"] in ordered_matches:
            transition_residual_ms = (ordered_matches[event["sequence"]] - expected_time) * 1000.0
        elif event["changes_state"]:
            matches = [
                timestamp - expected_time
                for timestamp, wire_state in changes
                if wire_state == expected
            ]
            if matches:
                transition_residual_ms = min(matches, key=abs) * 1000.0
        checked.append(
            {
                **event,
                "expected_wire_epoch": expected_time,
                "observed_wire_state": list(actual) if actual is not None else None,
                "byte_exact": not residuals,
                "channel_residuals": residuals,
                "transition_residual_ms": (
                    round(transition_residual_ms, 3)
                    if transition_residual_ms is not None
                    else None
                ),
            }
        )

    transition_residuals = [
        row["transition_residual_ms"]
        for row in checked
        if row["transition_residual_ms"] is not None
    ]
    positive = [row for row in checked if row["reference_kind"] == "cue"]
    clears = [row for row in checked if row["reference_kind"] == "clear_control"]
    result = {
        "status": "fitted",
        "fit_mode": fit_mode,
        "pcap": str(args.pcap),
        "pcap_size": args.pcap.stat().st_size,
        "pcap_sha256": hashlib.sha256(args.pcap.read_bytes()).hexdigest(),
        "pcap_version": "classic-pcap",
        "capture_duration_seconds": frames[-1][0] - frames[0][0],
        "frame_count": len(frames),
        "wire_change_count": len(changes),
        "scripted_file": str(args.scripted_file),
        "scripted_file_size": len(scripted_bytes),
        "scripted_file_sha256": hashlib.sha256(scripted_bytes).hexdigest(),
        "scripted_file_version": parsed["version"],
        "venue": str(args.venue),
        "venue_size": len(venue_bytes),
        "venue_sha256": hashlib.sha256(venue_bytes).hexdigest(),
        "venue_version": int.from_bytes(venue_bytes[4:8], "little"),
        "fixture_group": args.fixture_group,
        "owner_deck": args.owner_deck,
        "initial_state_policy": {
            "name": "all_zero_static_render",
            "wire_seeded": False,
            "state": [0] * 19,
        },
        "layer_model": {
            "confidence": "provisional_single_file",
            "control_channels": list(control_channels),
            "positive_reference_rule": "dictionary_index = raw_reference - 1",
            "ref_zero_rule": "clear main layer; retain independent control layers",
            "captured_frames_used_as_renderer_input": False,
        },
        "shared_block_offset": parsed["shared_block_offset"],
        "cue_count_offset": parsed["cue_count_offset"],
        "cue_count": parsed["cue_count"],
        "timeline_count_offset": parsed["timeline_count_offset"],
        "timeline_count": parsed["timeline_count"],
        "trailer_offset": parsed["trailer_offset"],
        "checked_event_count": len(checked),
        "exact_event_frames": sum(row["byte_exact"] for row in checked),
        "all_event_frames_exact": all(row["byte_exact"] for row in checked),
        "positive_reference_event_count": len(positive),
        "exact_positive_reference_event_frames": sum(row["byte_exact"] for row in positive),
        "ref_zero_event_count": len(clears),
        "exact_ref_zero_event_frames": sum(row["byte_exact"] for row in clears),
        "rms_transition_residual_ms": (
            math.sqrt(
                sum(value * value for value in transition_residuals)
                / len(transition_residuals)
            )
            if transition_residuals
            else None
        ),
        "max_abs_transition_residual_ms": max(
            (abs(value) for value in transition_residuals), default=None
        ),
        "events": checked,
        "scope_limit": (
            "single A5 file and fixture group; control-channel rule is provisional and "
            "does not establish other scripted layouts, transport, or hardware behavior"
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
