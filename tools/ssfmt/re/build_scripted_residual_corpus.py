#!/usr/bin/env python3
"""Build a deterministic corpus of scripted validator residuals.

Research helper only. Validator frames remain comparison oracles: this module
reports them and never feeds them back into the renderer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from parse_venue_cues import parse_venue_cues


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ssid(report: dict[str, Any]) -> str:
    name = Path(report["scripted_file"]).stem
    return name[1:-1] if name.startswith("{") and name.endswith("}") else name


def _cue_record(cue: dict[str, Any] | None, venue_data: bytes) -> dict[str, Any] | None:
    if cue is None:
        return None
    end = cue.get("catalog_indices_end_offset") or cue["entries_end_offset"]
    start = cue["offset"]
    return {
        "record_kind": cue["record_kind"],
        "offset": start,
        "end_offset": end,
        "raw_hex": venue_data[start:end].hex(),
        "name": cue["name"],
        "cue_guid": cue["cue_guid"],
        "catalog_ordinal_unknown_u32": cue.get("unknown_u32"),
        "marker_hex": cue.get("marker_hex"),
        "fixture_profile_guid": cue.get("fixture_profile_guid"),
        "header_fields": cue.get("header_fields", {}),
    }


def _event_context(events: list[dict[str, Any]], index: int) -> dict[str, Any]:
    event = events[index]
    previous = events[index - 1] if index else None
    following = events[index + 1] if index + 1 < len(events) else None

    def compact(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            key: row.get(key)
            for key in (
                "sequence",
                "source_sequence",
                "time",
                "record_offset",
                "raw_cue_reference",
                "resolved_dictionary_index",
                "guid",
                "cue_name",
                "reference_kind",
                "byte_exact",
            )
        }

    return {
        "previous": compact(previous),
        "current": compact(event),
        "next": compact(following),
        "spacing_from_previous_ms": (
            event["time"] - previous["time"] if previous is not None else None
        ),
        "spacing_to_next_ms": (
            following["time"] - event["time"] if following is not None else None
        ),
    }


def _active_event_index(events: list[dict[str, Any]], elapsed_ms: float) -> int | None:
    eligible = [
        (row["time"], row.get("source_sequence", index), index)
        for index, row in enumerate(events)
        if 0 <= row["time"] <= elapsed_ms
    ]
    return max(eligible)[2] if eligible else None


def _signature(kind: str, cue_identity: str, residuals: Iterable[dict[str, Any]]) -> str:
    channels = ",".join(str(row["channel"]) for row in residuals)
    return f"{kind}|cue={cue_identity}|channels={channels or 'none'}"


def _observation_base(
    report: dict[str, Any], report_path: str, report_sha256: str
) -> dict[str, Any]:
    return {
        "track": Path(report["scripted_file"]).name,
        "ssid": _ssid(report),
        "fixture_group": report["fixture_group"],
        "reference_rule": report["reference_rule"],
        "report_path": report_path,
        "report_sha256": report_sha256,
        "pcap": report["pcap"],
        "pcap_sha256": report["pcap_sha256"],
        "scripted_file": report["scripted_file"],
        "scripted_file_sha256": report["scripted_file_sha256"],
        "venue": report["venue"],
        "venue_sha256": report["venue_sha256"],
    }


def build_corpus(
    loaded_reports: Iterable[tuple[str, str, dict[str, Any]]],
    venue_data: bytes,
) -> dict[str, Any]:
    """Return a stable residual corpus from ``(path, sha256, report)`` rows."""
    venue_cues = parse_venue_cues(venue_data)
    venue_by_guid = {cue["cue_guid"]: cue for cue in venue_cues}
    observations: list[dict[str, Any]] = []
    usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"exact": [], "residual": []}
    )

    sorted_reports = sorted(
        loaded_reports,
        key=lambda item: (
            _ssid(item[2]),
            item[2]["fixture_group"],
            item[2]["pcap"],
            item[0],
        ),
    )
    for report_path, report_sha256, report in sorted_reports:
        base = _observation_base(report, report_path, report_sha256)
        events = report.get("events", [])
        for index, event in enumerate(events):
            guid = event.get("guid")
            cue_identity = guid or f"missing_guid:{event.get('reference_kind', 'unknown')}"
            usage_row = {
                "ssid": base["ssid"],
                "fixture_group": base["fixture_group"],
                "pcap_sha256": base["pcap_sha256"],
                "kind": "event",
                "elapsed_ms": event["time"],
                "sequence": event.get("sequence"),
            }
            usage[cue_identity]["exact" if event["byte_exact"] else "residual"].append(
                usage_row
            )
            if event["byte_exact"]:
                continue
            residuals = sorted(event["channel_residuals"], key=lambda row: row["channel"])
            cue = venue_by_guid.get(guid) if guid else None
            signature = _signature("event", cue_identity, residuals)
            observations.append(
                {
                    **base,
                    "observation_kind": "event",
                    "elapsed_ms": event["time"],
                    "sequence": event.get("sequence"),
                    "source_sequence": event.get("source_sequence"),
                    "record_offset": event.get("record_offset"),
                    "raw_cue_reference": event.get("raw_cue_reference"),
                    "direct_dictionary_index": (
                        event["raw_cue_reference"]
                        if event.get("raw_cue_reference", 0) > 0
                        else None
                    ),
                    "one_based_dictionary_index": (
                        event["raw_cue_reference"] - 1
                        if event.get("raw_cue_reference", 0) > 0
                        else None
                    ),
                    "resolved_dictionary_index": event.get("resolved_dictionary_index"),
                    "guid": guid,
                    "cue_name": event.get("cue_name"),
                    "cue_type": cue.get("record_kind") if cue else None,
                    "venue_cue_record": _cue_record(cue, venue_data),
                    "patch": event.get("patch", {}),
                    "expected_wire_state": event.get("expected_wire_state"),
                    "observed_wire_state": event.get("observed_wire_state"),
                    "channel_residuals": residuals,
                    "active_control_state": event.get("state", {}).get(
                        "control_layers", {}
                    ),
                    "timeline_context": _event_context(events, index),
                    "signature_key": signature,
                }
            )

        for position_index, position in enumerate(report.get("bridge_position_samples", [])):
            if position["byte_exact"]:
                continue
            active_index = _active_event_index(events, position["elapsed_ms"])
            active = events[active_index] if active_index is not None else None
            guid = active.get("guid") if active else None
            cue_identity = guid or "no_active_cue"
            residuals = sorted(position["channel_residuals"], key=lambda row: row["channel"])
            cue = venue_by_guid.get(guid) if guid else None
            signature = _signature("position", cue_identity, residuals)
            observations.append(
                {
                    **base,
                    "observation_kind": "position",
                    "elapsed_ms": position["elapsed_ms"],
                    "position_index": position_index,
                    "bridge_log_line_number": position.get("line_number"),
                    "bridge_edge_from_previous": position.get("edge_from_previous"),
                    "raw_cue_reference": active.get("raw_cue_reference") if active else None,
                    "direct_dictionary_index": (
                        active["raw_cue_reference"]
                        if active and active.get("raw_cue_reference", 0) > 0
                        else None
                    ),
                    "one_based_dictionary_index": (
                        active["raw_cue_reference"] - 1
                        if active and active.get("raw_cue_reference", 0) > 0
                        else None
                    ),
                    "resolved_dictionary_index": (
                        active.get("resolved_dictionary_index") if active else None
                    ),
                    "guid": guid,
                    "cue_name": active.get("cue_name") if active else None,
                    "cue_type": cue.get("record_kind") if cue else None,
                    "venue_cue_record": _cue_record(cue, venue_data),
                    "patch": active.get("patch", {}) if active else {},
                    "expected_wire_state": position.get("expected_wire_state"),
                    "observed_wire_state": position.get("observed_wire_state"),
                    "channel_residuals": residuals,
                    "active_control_state": (
                        active.get("state", {}).get("control_layers", {}) if active else {}
                    ),
                    "timeline_context": (
                        _event_context(events, active_index)
                        if active_index is not None
                        else None
                    ),
                    "signature_key": signature,
                }
            )

    observations.sort(
        key=lambda row: (
            row["ssid"],
            row["fixture_group"],
            row["pcap_sha256"],
            row["observation_kind"],
            row["elapsed_ms"],
            row.get("sequence", row.get("position_index", -1)),
        )
    )
    clusters: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(observations):
        clusters[row["signature_key"]].append(index)
    for row in observations:
        related = [observations[index] for index in clusters[row["signature_key"]]]
        row["same_residual_occurs_in"] = sorted(
            {
                f"{item['ssid']}|{item['fixture_group']}|{item['pcap_sha256']}|"
                f"{item['observation_kind']}"
                for item in related
            }
        )

    cue_usage = []
    for identity, states in sorted(usage.items()):
        cue = venue_by_guid.get(identity)
        cue_usage.append(
            {
                "cue_identity": identity,
                "cue_name": cue.get("name") if cue else None,
                "exact_uses": sorted(
                    states["exact"],
                    key=lambda row: (
                        row["ssid"], row["fixture_group"], row["elapsed_ms"]
                    ),
                ),
                "residual_uses": sorted(
                    states["residual"],
                    key=lambda row: (
                        row["ssid"], row["fixture_group"], row["elapsed_ms"]
                    ),
                ),
            }
        )

    return {
        "status": "residual_corpus_only_no_semantic_inference",
        "venue_sha256": _sha256(venue_data),
        "captured_frames_used_as_renderer_input": False,
        "report_count": len(sorted_reports),
        "residual_observation_count": len(observations),
        "cluster_count": len(clusters),
        "clusters": [
            {
                "signature_key": signature,
                "observation_indices": indices,
                "observation_count": len(indices),
                "ssids": sorted({observations[index]["ssid"] for index in indices}),
                "fixture_groups": sorted(
                    {observations[index]["fixture_group"] for index in indices}
                ),
            }
            for signature, indices in sorted(clusters.items())
        ],
        "cue_usage": cue_usage,
        "observations": observations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--venue", required=True, type=Path)
    args = parser.parse_args()
    loaded_reports = []
    for path in args.reports:
        data = path.read_bytes()
        loaded_reports.append((str(path), _sha256(data), json.loads(data)))
    venue_data = args.venue.read_bytes()
    print(json.dumps(build_corpus(loaded_reports, venue_data), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
