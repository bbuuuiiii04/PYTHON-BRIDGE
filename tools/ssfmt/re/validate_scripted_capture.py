#!/usr/bin/env python3
"""Validate a scripted timeline against passive Art-Net frames.

Research helper only. The default CH11 control-layer assignment is a named,
A5-specific hypothesis and is never presented as a universal format rule.
"""
from __future__ import annotations

import argparse
import bisect
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re

from analyze_scripted_ssfile import parse_scripted_structure, shared_table_from_autoloop
from analyze_ssfile_structure import REFERENCE_RULES
from layered_renderer import (
    render_at_elapsed,
    render_playback_state,
    render_timeline,
    venue_cue_records,
)
from parse_artnet_pcap import universe_frames
from parse_venue_cues import parse_venue_cues


ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ARM_SCRIPTED = re.compile(
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<fraction>\d+)"
    r".*?\[SM\] arm-scripted\s+deck=(?P<deck>\d+)\b.*?"
    r"\belapsed=(?P<elapsed>\d+(?::\d+)+\.\d+)"
)
POSITION_SAMPLE = re.compile(
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<fraction>\d+)"
    r".*?\[SM\] pos\s+deck=(?P<deck>\d+)\s+"
    r"(?P<elapsed>\d+(?::\d+)+\.\d+).*?\bmode=(?P<mode>[a-z_]+)"
)
STOP_MARKER = re.compile(
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<fraction>\d+)"
    r".*?\[SM\] stop\s+deck=(?P<deck>\d+)\b.*?"
    r"\belapsed=(?P<elapsed>\d+(?::\d+)+\.\d+)"
)
SCRIPTED_TO_IDLE = re.compile(
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<fraction>\d+)"
    r".*?\[SM\] mode\s+deck=(?P<deck>\d+)\s+scripted→idle\s+"
    r"elapsed=(?P<elapsed>\d+(?::\d+)+\.\d+)"
)


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


def require_resolvable_reference_rule(reference_rule: str) -> str:
    if reference_rule not in {"direct", "one_based"}:
        raise ValueError(
            "scripted capture validation requires explicit direct or one_based "
            "provenance; ambiguous and mixed/edited files fail closed"
        )
    return reference_rule


def elapsed_seconds(raw: str) -> float:
    """Parse logger elapsed values such as 0:00.040 or 1:02:03.500."""
    parts = raw.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError(f"unsupported elapsed value {raw!r}")
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return hours * 3600.0 + minutes * 60.0 + seconds


def local_log_epoch(match: re.Match, capture_reference_epoch: float) -> float:
    """Resolve a date-less local log timestamp nearest a capture epoch."""
    fraction = match.group("fraction")
    microsecond = int((fraction + "000000")[:6])
    reference = datetime.fromtimestamp(capture_reference_epoch)
    wall_time = reference.replace(
        hour=int(match.group("hour")),
        minute=int(match.group("minute")),
        second=int(match.group("second")),
        microsecond=microsecond,
    )
    candidates = [wall_time + timedelta(days=offset) for offset in (-1, 0, 1)]
    return min(
        (candidate.timestamp() for candidate in candidates),
        key=lambda value: abs(value - capture_reference_epoch),
    )


def bridge_scripted_start(
    bridge_log: Path,
    capture_reference_epoch: float,
    owner_deck: int | None = None,
) -> dict:
    """Anchor track zero to a copied bridge ``arm-scripted`` observation.

    Bridge logs contain local wall time but no date. The capture epoch supplies
    the date; the closest of that date and its adjacent days is selected so a
    capture spanning midnight remains deterministic.
    """
    candidates = []
    for line_number, raw_line in enumerate(
        bridge_log.read_text(errors="replace").splitlines(), start=1
    ):
        line = ANSI_ESCAPE.sub("", raw_line)
        match = ARM_SCRIPTED.search(line)
        if match is None:
            continue
        deck = int(match.group("deck"))
        if owner_deck is not None and deck != owner_deck:
            continue
        observed_epoch = local_log_epoch(match, capture_reference_epoch)
        observed_elapsed = elapsed_seconds(match.group("elapsed"))
        candidates.append(
            {
                "start_epoch": observed_epoch - observed_elapsed,
                "observed_epoch": observed_epoch,
                "observed_elapsed_seconds": observed_elapsed,
                "deck": deck,
                "line_number": line_number,
                "line": line,
            }
        )
    if candidates:
        return min(
            candidates,
            key=lambda row: abs(row["observed_epoch"] - capture_reference_epoch),
        )
    deck_scope = f" for deck {owner_deck}" if owner_deck is not None else ""
    raise ValueError(f"no arm-scripted observation{deck_scope} in {bridge_log}")


def bridge_position_observations(
    bridge_log: Path,
    capture_reference_epoch: float,
    owner_deck: int | None = None,
) -> list[dict]:
    """Return copied bridge position observations with capture-date epochs."""
    rows = []
    for line_number, raw_line in enumerate(
        bridge_log.read_text(errors="replace").splitlines(), start=1
    ):
        line = ANSI_ESCAPE.sub("", raw_line)
        match = POSITION_SAMPLE.search(line)
        if match is None:
            continue
        deck = int(match.group("deck"))
        if owner_deck is not None and deck != owner_deck:
            continue
        rows.append(
            {
                "observed_epoch": local_log_epoch(match, capture_reference_epoch),
                "elapsed_ms": elapsed_seconds(match.group("elapsed")) * 1000.0,
                "deck": deck,
                "mode": match.group("mode"),
                "line_number": line_number,
                "line": line,
            }
        )
    return sorted(rows, key=lambda row: row["observed_epoch"])


def classify_position_edges(rows: list[dict]) -> None:
    """Annotate observed position discontinuities without inferring loop intent."""
    previous = None
    previous_classification = None
    for row in rows:
        classification = "initial"
        wall_delta = playback_delta = None
        if previous is not None:
            wall_delta = row["observed_epoch"] - previous["observed_epoch"]
            playback_delta = (row["elapsed_ms"] - previous["elapsed_ms"]) / 1000.0
            if playback_delta < -1.0:
                classification = "backward_discontinuity_seek_or_loop"
            elif playback_delta - wall_delta > 2.0:
                classification = "forward_seek"
            elif abs(playback_delta) < 0.1 and wall_delta > 1.0:
                classification = "paused_or_ended"
            elif previous_classification == "paused_or_ended":
                classification = "resume_or_refire"
            elif abs(playback_delta - wall_delta) <= 1.0:
                classification = "continuous"
            else:
                classification = "rate_discontinuity"
        row["wall_delta_seconds"] = wall_delta
        row["playback_delta_seconds"] = playback_delta
        row["edge_from_previous"] = classification
        previous = row
        previous_classification = classification


def bridge_zero_output_observations(
    bridge_log: Path,
    capture_reference_epoch: float,
    owner_deck: int | None = None,
) -> list[dict]:
    """Return scripted-to-idle and confirmed-stop observations from a bridge log."""
    rows = []
    for line_number, raw_line in enumerate(
        bridge_log.read_text(errors="replace").splitlines(), start=1
    ):
        line = ANSI_ESCAPE.sub("", raw_line)
        for marker_kind, pattern in (
            ("scripted_to_idle", SCRIPTED_TO_IDLE),
            ("stop", STOP_MARKER),
        ):
            match = pattern.search(line)
            if match is None:
                continue
            deck = int(match.group("deck"))
            if owner_deck is not None and deck != owner_deck:
                continue
            rows.append(
                {
                    "observed_epoch": local_log_epoch(match, capture_reference_epoch),
                    "elapsed_ms": elapsed_seconds(match.group("elapsed")) * 1000.0,
                    "deck": deck,
                    "marker_kind": marker_kind,
                    "line_number": line_number,
                    "line": line,
                }
            )
    return sorted(rows, key=lambda row: row["observed_epoch"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    parser.add_argument("scripted_file", type=Path)
    parser.add_argument("--autoloop-reference", required=True, type=Path)
    parser.add_argument("--venue", required=True, type=Path)
    parser.add_argument("--fixture-group", default="0x493")
    parser.add_argument(
        "--reference-rule",
        choices=(*REFERENCE_RULES, "mixed"),
        default="ambiguous",
        help="legacy=one_based, newly-created=direct; ambiguous/mixed fail closed",
    )
    parser.add_argument("--control-channels", default="8,9,11")
    parser.add_argument("--sample-delay-ms", type=float, default=30.0)
    parser.add_argument("--owner-deck", type=int)
    start_group = parser.add_mutually_exclusive_group()
    start_group.add_argument(
        "--bridge-log",
        type=Path,
        help="copied bridge log whose arm-scripted line anchors track zero",
    )
    start_group.add_argument(
        "--start-epoch",
        type=float,
        help="explicit Unix epoch for track elapsed zero",
    )
    args = parser.parse_args()

    control_channels = parse_channels(args.control_channels)
    frames = universe_frames(args.pcap)
    if not frames:
        raise SystemExit("no Universe-0 ArtDmx frames")
    scripted_bytes = args.scripted_file.read_bytes()
    venue_bytes = args.venue.read_bytes()
    try:
        reference_rule = require_resolvable_reference_rule(args.reference_rule)
    except ValueError as error:
        parser.error(str(error))
    parsed = parse_scripted_structure(
        scripted_bytes,
        shared_table_from_autoloop(args.autoloop_reference),
        reference_rule,
    )
    cue_records = venue_cue_records(parse_venue_cues(venue_bytes), args.fixture_group)
    events = render_timeline(
        parsed,
        cue_records,
        time_key="elapsed",
        initial_state=(0,) * 19,
        initial_state_policy="all_zero_static_render",
        control_channels=control_channels,
        owner_deck=args.owner_deck,
    )
    changes = changed_frames(frames)
    start_observation = None
    if args.bridge_log is not None:
        try:
            start_observation = bridge_scripted_start(
                args.bridge_log, frames[0][0], args.owner_deck
            )
        except ValueError as error:
            parser.error(str(error))
        start = start_observation["start_epoch"]
        fit_mode = "bridge_arm_scripted_anchor"
        ordered_matches = {}
    elif args.start_epoch is not None:
        start = args.start_epoch
        fit_mode = "explicit_start_epoch_anchor"
        ordered_matches = {}
    else:
        exact_fit = fit_start(frames, events, args.sample_delay_ms / 1000.0)
        ordered_fit = None if exact_fit else fit_ordered_timing(changes, events)
        if exact_fit:
            start = exact_fit[0]
            fit_mode = "exploratory_exact_layered_state_fit"
            ordered_matches = {}
        elif ordered_fit:
            start = ordered_fit["start"]
            fit_mode = "exploratory_ordered_transition_fit"
            ordered_matches = ordered_fit["matched"]
        else:
            raise SystemExit("unable to fit scripted timeline to capture")
    timestamps = [row[0] for row in frames]
    checked = []
    for event in events:
        expected_time = start + event["time"] / 1000.0
        sample_elapsed_ms = event["time"] + args.sample_delay_ms
        sample_time = start + sample_elapsed_ms / 1000.0
        if (
            sample_elapsed_ms < 0
            or not frames[0][0] <= sample_time <= frames[-1][0]
        ):
            continue
        expected_render = render_at_elapsed(
            parsed,
            cue_records,
            sample_elapsed_ms,
            initial_state=(0,) * 19,
            initial_state_policy="all_zero_static_render",
            control_channels=control_channels,
            owner_deck=args.owner_deck,
        )
        expected = tuple(expected_render["state"]["rendered_state"])
        actual = frame_at(frames, timestamps, sample_time)
        residuals = channel_residuals(expected, actual)
        control_residuals = [
            row for row in residuals if row["channel"] in control_channels
        ]
        main_residuals = [
            row for row in residuals if row["channel"] not in control_channels
        ]
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
                "sample_elapsed_ms": sample_elapsed_ms,
                "sample_wire_epoch": sample_time,
                "sample_active_event_sequence": (
                    expected_render["active_event"]["source_sequence"]
                    if expected_render["active_event"] is not None
                    else None
                ),
                "expected_wire_state": list(expected),
                "observed_wire_state": list(actual) if actual is not None else None,
                "byte_exact": not residuals,
                "control_channels_byte_exact": not control_residuals,
                "main_channels_byte_exact": not main_residuals,
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
    position_checks = []
    if args.bridge_log is not None:
        for observation in bridge_position_observations(
            args.bridge_log, frames[0][0], args.owner_deck
        ):
            if observation["observed_epoch"] < start:
                continue
            sample_time = observation["observed_epoch"] + args.sample_delay_ms / 1000.0
            if not frames[0][0] <= sample_time <= frames[-1][0]:
                continue
            expected_render = render_at_elapsed(
                parsed,
                cue_records,
                observation["elapsed_ms"],
                initial_state=(0,) * 19,
                initial_state_policy="all_zero_static_render",
                control_channels=control_channels,
                owner_deck=args.owner_deck,
            )
            expected = tuple(expected_render["state"]["rendered_state"])
            actual = frame_at(frames, timestamps, sample_time)
            residuals = channel_residuals(expected, actual)
            position_checks.append(
                {
                    **observation,
                    "sample_wire_epoch": sample_time,
                    "expected_wire_state": list(expected),
                    "observed_wire_state": list(actual) if actual is not None else None,
                    "byte_exact": not residuals,
                    "channel_residuals": residuals,
                }
            )
        classify_position_edges(position_checks)
    edge_counts = {
        name: sum(row["edge_from_previous"] == name for row in position_checks)
        for name in sorted({row["edge_from_previous"] for row in position_checks})
    }
    zero_output_checks = []
    if args.bridge_log is not None:
        for observation in bridge_zero_output_observations(
            args.bridge_log, frames[0][0], args.owner_deck
        ):
            if observation["observed_epoch"] < start:
                continue
            sample_time = observation["observed_epoch"] + args.sample_delay_ms / 1000.0
            if not frames[0][0] <= sample_time <= frames[-1][0]:
                continue
            expected_render = render_playback_state(
                parsed,
                cue_records,
                observation["elapsed_ms"],
                "ended",
                initial_state=(0,) * 19,
                initial_state_policy="all_zero_static_render",
                control_channels=control_channels,
                owner_deck=args.owner_deck,
            )
            expected = tuple(expected_render["state"]["rendered_state"])
            actual = frame_at(frames, timestamps, sample_time)
            residuals = channel_residuals(expected, actual)
            zero_output_checks.append(
                {
                    **observation,
                    "sample_wire_epoch": sample_time,
                    "expected_wire_state": list(expected),
                    "observed_wire_state": list(actual) if actual is not None else None,
                    "byte_exact": not residuals,
                    "channel_residuals": residuals,
                }
            )
    result = {
        "status": (
            "anchored"
            if args.bridge_log is not None or args.start_epoch is not None
            else "fitted"
        ),
        "fit_mode": fit_mode,
        "start_epoch": start,
        "start_source": (
            {
                "kind": "bridge_arm_scripted",
                "path": str(args.bridge_log),
                **start_observation,
            }
            if start_observation is not None
            else {
                "kind": "explicit_start_epoch"
                if args.start_epoch is not None
                else "exploratory_wire_fit"
            }
        ),
        "bridge_log_evidence": (
            {
                "path": str(args.bridge_log),
                "size": args.bridge_log.stat().st_size,
                "sha256": hashlib.sha256(args.bridge_log.read_bytes()).hexdigest(),
            }
            if args.bridge_log is not None
            else None
        ),
        "pcap": str(args.pcap),
        "pcap_size": args.pcap.stat().st_size,
        "pcap_sha256": hashlib.sha256(args.pcap.read_bytes()).hexdigest(),
        "pcap_version": "classic-pcap",
        "capture_duration_seconds": frames[-1][0] - frames[0][0],
        "frame_count": len(frames),
        "wire_change_count": len(changes),
        "sample_delay_ms": args.sample_delay_ms,
        "scripted_file": str(args.scripted_file),
        "scripted_file_size": len(scripted_bytes),
        "scripted_file_sha256": hashlib.sha256(scripted_bytes).hexdigest(),
        "scripted_file_version": parsed["version"],
        "venue": str(args.venue),
        "venue_size": len(venue_bytes),
        "venue_sha256": hashlib.sha256(venue_bytes).hexdigest(),
        "venue_version": int.from_bytes(venue_bytes[4:8], "little"),
        "fixture_group": args.fixture_group,
        "reference_rule": reference_rule,
        "owner_deck": args.owner_deck,
        "initial_state_policy": {
            "name": "all_zero_static_render",
            "wire_seeded": False,
            "state": [0] * 19,
        },
        "layer_model": {
            "confidence": "provisional_until_representative_scripted_capture",
            "control_channels": list(control_channels),
            "positive_reference_rule": reference_rule,
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
        "exact_control_channel_event_samples": sum(
            row["control_channels_byte_exact"] for row in checked
        ),
        "all_control_channel_event_samples_exact": all(
            row["control_channels_byte_exact"] for row in checked
        ),
        "exact_main_channel_event_samples": sum(
            row["main_channels_byte_exact"] for row in checked
        ),
        "all_main_channel_event_samples_exact": all(
            row["main_channels_byte_exact"] for row in checked
        ),
        "per_channel_exact_event_samples": {
            str(channel): sum(
                not any(
                    residual["channel"] == channel
                    for residual in row["channel_residuals"]
                )
                for row in checked
            )
            for channel in range(1, 20)
        },
        "positive_reference_event_count": len(positive),
        "exact_positive_reference_event_frames": sum(row["byte_exact"] for row in positive),
        "ref_zero_event_count": len(clears),
        "exact_ref_zero_event_frames": sum(row["byte_exact"] for row in clears),
        "bridge_position_sample_count": len(position_checks),
        "exact_bridge_position_samples": sum(
            row["byte_exact"] for row in position_checks
        ),
        "all_bridge_position_samples_exact": bool(position_checks)
        and all(row["byte_exact"] for row in position_checks),
        "bridge_position_edge_counts": edge_counts,
        "bridge_position_samples": position_checks,
        "zero_output_marker_count": len(zero_output_checks),
        "exact_zero_output_markers": sum(
            row["byte_exact"] for row in zero_output_checks
        ),
        "all_zero_output_markers_exact": bool(zero_output_checks)
        and all(row["byte_exact"] for row in zero_output_checks),
        "zero_output_markers": zero_output_checks,
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
            "one capture and fixture group. Position classifications report observed "
            "discontinuities only: a backward discontinuity cannot distinguish seek from loop "
            "without operator timing or another runtime marker. No hardware behavior is proven"
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
