#!/usr/bin/env python3
"""Audit the older artnet_lo corpus and its surviving derived alignment files."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from parse_artnet_pcap import artdmx_frames, read_pcap
from parse_venue_cues import parse_venue_cues


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text().splitlines():
        if "  " not in line:
            continue
        expected, raw_path = line.split("  ", 1)
        source = Path(raw_path)
        actual = _sha256(source) if source.is_file() else None
        rows.append(
            {
                "path": str(source),
                "filename": source.name,
                "expected_sha256": expected,
                "current_sha256": actual,
                "exists": source.is_file(),
                "matches_current": actual == expected,
            }
        )
    return rows


def _cue_semantics(path: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for cue in parse_venue_cues(path.read_bytes()):
        result[cue["cue_guid"]] = {
            "name": cue["name"],
            "fixture_profile_guid": cue["fixture_profile_guid"],
            "groups": cue["groups"],
        }
    return result


def analyze(
    pcap: Path,
    index_library: Path,
    baseline_hashes: Path,
    snapshot_venue: Path,
    current_venue: Path,
) -> dict[str, Any]:
    network, packets = read_pcap(pcap)
    artdmx = artdmx_frames(pcap)
    universe_rows: dict[int, list[dict[str, Any]]] = {}
    for row in artdmx:
        universe_rows.setdefault(row["universe"], []).append(row)
    universe_activity = []
    for universe, rows in sorted(universe_rows.items()):
        states = {row["dmx"] for row in rows}
        channels = sorted(
            {
                index
                for row in rows
                for index, value in enumerate(row["dmx"], start=1)
                if value
            }
        )
        universe_activity.append(
            {
                "universe": universe,
                "frame_count": len(rows),
                "nonzero_frame_count": sum(any(row["dmx"]) for row in rows),
                "unique_state_count": len(states),
                "nonzero_channels": channels,
            }
        )

    baselines = _baseline_rows(baseline_hashes)
    autoloop_baselines = [
        row for row in baselines if row["filename"].startswith("SSAutoLoop")
    ]
    library_raw = json.loads(index_library.read_text())
    library_rows = list(library_raw.values()) if isinstance(library_raw, dict) else library_raw
    indices = sorted({int(row["index"]) for row in library_rows})
    universe_zero_frames = len(universe_rows.get(0, []))
    library_frame_total = sum(int(row["frames"]) for row in library_rows)
    snapshot_cues = _cue_semantics(snapshot_venue)
    current_cues = _cue_semantics(current_venue)
    return {
        "status": "partial",
        "pcap": {
            "path": str(pcap),
            "size": pcap.stat().st_size,
            "sha256": _sha256(pcap),
            "version": "classic-pcap",
            "link_type": network,
            "packet_count": len(packets),
            "artdmx_frame_count": len(artdmx),
            "capture_duration_seconds": (
                artdmx[-1]["timestamp"] - artdmx[0]["timestamp"] if artdmx else None
            ),
            "universe_activity": universe_activity,
        },
        "baseline": {
            "path": str(baseline_hashes),
            "entry_count": len(baselines),
            "matching_current_count": sum(row["matches_current"] for row in baselines),
            "changed_or_missing_count": sum(not row["matches_current"] for row in baselines),
            "changed_or_missing": [row for row in baselines if not row["matches_current"]],
            "autoloop_count": len(autoloop_baselines),
            "autoloops_matching_current_count": sum(
                row["matches_current"] for row in autoloop_baselines
            ),
        },
        "venue_cue_semantics": {
            "snapshot_path": str(snapshot_venue),
            "snapshot_sha256": _sha256(snapshot_venue),
            "current_path": str(current_venue),
            "current_sha256": _sha256(current_venue),
            "snapshot_cue_count": len(snapshot_cues),
            "current_cue_count": len(current_cues),
            "same_guid_set": set(snapshot_cues) == set(current_cues),
            "same_parsed_cue_semantics": snapshot_cues == current_cues,
        },
        "derived_index_library": {
            "path": str(index_library),
            "sha256": _sha256(index_library),
            "entry_count": len(library_rows),
            "app_log_indices": indices,
            "missing_catalog_indices": sorted(
                (set(range(18)) | set(range(32, 56))) - set(indices)
            ),
            "reported_frame_total": library_frame_total,
            "universe_zero_frame_count": universe_zero_frames,
            "unassigned_frame_count": universe_zero_frames - library_frame_total,
            "contains_raw_segment_timestamps": False,
            "contains_only_sample_state_per_index": True,
        },
        "unsupported_reason": (
            "the derived library proves historical index coverage and sample states but does "
            "not retain raw segment timestamps; copied AppLogs for this capture are absent, so "
            "it cannot be upgraded to per-frame byte-exact validation without inventing boundaries"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    parser.add_argument("--index-library", required=True, type=Path)
    parser.add_argument("--baseline-hashes", required=True, type=Path)
    parser.add_argument("--snapshot-venue", required=True, type=Path)
    parser.add_argument("--current-venue", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(
                args.pcap,
                args.index_library,
                args.baseline_hashes,
                args.snapshot_venue,
                args.current_venue,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
