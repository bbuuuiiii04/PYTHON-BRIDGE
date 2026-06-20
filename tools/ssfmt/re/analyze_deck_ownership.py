#!/usr/bin/env python3
"""Correlate per-deck AppLog selections with passive Universe-0 changes."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from parse_artnet_pcap import universe_frames
from validate_autoloop_capture import changed_frames, parse_app_logs


def _cluster_events(events: list[dict[str, Any]], tolerance: float = 0.05) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for event in events:
        if not clusters or event["timestamp"] - clusters[-1][-1]["timestamp"] > tolerance:
            clusters.append([event])
        else:
            clusters[-1].append(event)
    return clusters


def analyze(
    pcap: Path,
    app_logs: list[Path],
    validation_report: dict[str, Any] | None,
) -> dict[str, Any]:
    frames = universe_frames(pcap)
    if not frames:
        raise ValueError("capture has no Universe-0 ArtDmx frames")
    changes = changed_frames(frames)
    change_times = [row[0] for row in changes]
    events = [
        event
        for event in parse_app_logs(app_logs)
        if frames[0][0] <= event["timestamp"] <= frames[-1][0]
    ]
    correlations = []
    for event in events:
        insertion = bisect.bisect_left(change_times, event["timestamp"])
        candidates = [
            changes[index]
            for index in (insertion - 1, insertion)
            if 0 <= index < len(changes)
        ]
        nearest = min(candidates, key=lambda row: abs(row[0] - event["timestamp"])) if candidates else None
        changes_100ms = [row for row in changes if abs(row[0] - event["timestamp"]) <= 0.1]
        changes_400ms = [row for row in changes if abs(row[0] - event["timestamp"]) <= 0.4]
        correlations.append(
            {
                **event,
                "nearest_wire_change_delta_ms": (
                    round((nearest[0] - event["timestamp"]) * 1000.0, 3) if nearest else None
                ),
                "nearest_wire_state": list(nearest[1]) if nearest else None,
                "wire_change_count_within_100ms": len(changes_100ms),
                "wire_change_count_within_400ms": len(changes_400ms),
            }
        )
    clusters = _cluster_events(events)
    cluster_deck_sets = Counter(tuple(sorted({row["deck"] for row in cluster})) for cluster in clusters)
    segment_summary = None
    if validation_report:
        segments = validation_report.get("segments", [])
        segment_summary = {
            "segment_count": len(segments),
            "segments_with_other_deck_changes": sum(bool(row["other_deck_changes"]) for row in segments),
            "byte_exact_segments_with_other_deck_changes": sum(
                row["classification"] == "byte_exact_static_render" and bool(row["other_deck_changes"])
                for row in segments
            ),
            "unresolved_segments_with_other_deck_changes": sum(
                row["classification"] != "byte_exact_static_render" and bool(row["other_deck_changes"])
                for row in segments
            ),
            "mismatch_frames_near_other_deck_change": sum(
                row["static_zero_initial_fit"]["mismatches_near_other_deck_change"]
                for row in segments
            ),
            "total_static_mismatch_frames": sum(
                row["static_zero_initial_fit"]["mismatch_frames"] for row in segments
            ),
        }
    return {
        "status": "blocked",
        "pcap": str(pcap),
        "pcap_size": pcap.stat().st_size,
        "pcap_sha256": hashlib.sha256(pcap.read_bytes()).hexdigest(),
        "pcap_version": "classic-pcap",
        "capture_start_epoch": frames[0][0],
        "capture_end_epoch": frames[-1][0],
        "capture_duration_seconds": frames[-1][0] - frames[0][0],
        "universe_zero_frame_count": len(frames),
        "universe_zero_change_count": len(changes),
        "app_logs": [
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "version": None,
            }
            for path in app_logs
        ],
        "app_event_count": len(events),
        "app_event_counts": [
            {"deck": key[0], "mode": key[1], "count": value}
            for key, value in sorted(Counter((row["deck"], row["mode"]) for row in events).items())
        ],
        "observed_decks": sorted({row["deck"] for row in events}),
        "selection_counts_by_deck": {
            str(deck): dict(sorted(Counter(row["selection"] for row in events if row["deck"] == deck).items()))
            for deck in sorted({row["deck"] for row in events})
        },
        "event_cluster_count": len(clusters),
        "event_cluster_deck_sets": [
            {"decks": list(decks), "count": count}
            for decks, count in sorted(cluster_deck_sets.items())
        ],
        "events_with_wire_change_within_100ms": sum(
            row["wire_change_count_within_100ms"] > 0 for row in correlations
        ),
        "events_with_wire_change_within_400ms": sum(
            row["wire_change_count_within_400ms"] > 0 for row in correlations
        ),
        "validation_segment_correlation": segment_summary,
        "correlations": correlations,
        "unsupported_reason": (
            "AppLogs expose independent Deck 0 and Deck 1 selection events but do not record "
            "master-deck, crossfader, stop/unload, or Universe-0 owner state; nearby wire changes "
            "therefore cannot identify the causal deck"
        ),
        "unsupported_cases": {
            "deck_3_4": "no AppLog events in the capture",
            "scripted_autoloop_overlap": "not isolated",
            "master_deck_change": "not logged",
            "crossfader": "not logged",
            "stop_unload": "not isolated",
            "deck_transfer": "not isolated",
        },
        "operator_protocol_required": [
            "fixtures physically disconnected or explicitly confirmed safe",
            "capture Universe 0 and 1 passively from a known cleared state",
            "hold one deck constant while changing only the other deck selection",
            "change only master-deck ownership, then only crossfader position, in separate runs",
            "repeat for stop, unload, deck transfer, and one scripted/autoloop overlap",
            "copy AppLogs and bridge.log immediately after each run",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    parser.add_argument("app_logs", nargs="+", type=Path)
    parser.add_argument("--validation-report", type=Path)
    args = parser.parse_args()
    validation = json.loads(args.validation_report.read_text()) if args.validation_report else None
    print(json.dumps(analyze(args.pcap, args.app_logs, validation), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
