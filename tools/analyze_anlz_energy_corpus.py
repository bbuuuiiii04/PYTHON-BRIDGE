#!/usr/bin/env python3
"""Offline ANLZ energy corpus analyzer (read-only)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.energy_model import (  # noqa: E402
    classify_breakdown_intensity,
    classify_buildup_intensity,
    classify_drop_intensity,
    energy_window_for_beat,
)
from rb_ss_bridge_v2.tools.anlz_tag_dump import (  # noqa: E402
    _candidate_anlz_paths,
    _parse_anlz_file,
    _safe_getall_tags,
)


def _read_manifest(path: str) -> list[dict[str, Any]]:
    manifest_path = Path(path).expanduser()
    if manifest_path.suffix.lower() == ".json":
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(item) for item in payload]
        if isinstance(payload, dict) and isinstance(payload.get("tracks"), list):
            return [dict(item) for item in payload["tracks"]]
        return []

    rows: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            parsed = dict(row)
            for key in ("beatgrid_times_ms", "drop_beats", "breakdown_beats", "buildup_beats"):
                if isinstance(parsed.get(key), str) and parsed[key]:
                    try:
                        parsed[key] = json.loads(parsed[key])
                    except Exception:
                        parsed[key] = []
            if isinstance(parsed.get("total_ms"), str) and parsed["total_ms"]:
                try:
                    parsed["total_ms"] = float(parsed["total_ms"])
                except Exception:
                    parsed["total_ms"] = 0.0
            rows.append(parsed)
    return rows


def _extract_waveform_and_grid_for_root(anlz_root: str) -> dict[str, Any]:
    parsed: list[tuple[Path, Any]] = []
    candidates = _candidate_anlz_paths(anlz_root)
    if not candidates:
        return {"errors": [f"missing_anlz_candidates:{anlz_root}"]}
    for candidate in candidates:
        try:
            parsed.append((candidate, _parse_anlz_file(candidate)))
        except Exception:
            continue

    if not parsed:
        return {"errors": [f"parse_failed:no_readable_anlz:{anlz_root}"]}

    waveform_values: list[float] = []
    waveform_source = ""
    for tag_type in ("PWV3", "PWAV"):
        for _path, anlz in parsed:
            for tag in _safe_getall_tags(anlz, tag_type):
                content = getattr(tag, "content", None)
                entries = getattr(content, "entries", None)
                if entries is None and isinstance(content, dict):
                    entries = content.get("entries")
                if entries:
                    try:
                        waveform_values = [float(int(entry) & 0x1F) for entry in entries]
                        waveform_source = tag_type
                    except Exception:
                        waveform_values = []
                    if waveform_values:
                        break
            if waveform_values:
                break
        if waveform_values:
            break

    beatgrid_times_ms: list[float] = []
    for tag_type in ("PQT2", "PQTZ"):
        for _path, anlz in parsed:
            for tag in _safe_getall_tags(anlz, tag_type):
                try:
                    times = sorted(float(t) * 1000.0 for t in tag.get_times() if float(t) >= 0.0)
                except Exception:
                    continue
                if len(times) >= 2:
                    beatgrid_times_ms = times
                    break
            if beatgrid_times_ms:
                break
        if beatgrid_times_ms:
            break

    markers = _extract_markers_from_pssi(parsed)
    total_ms = 0.0
    if len(beatgrid_times_ms) >= 2:
        total_ms = beatgrid_times_ms[-1] + (beatgrid_times_ms[-1] - beatgrid_times_ms[-2])
    return {
        "waveform_values": waveform_values,
        "waveform_source": waveform_source,
        "beatgrid_times_ms": beatgrid_times_ms,
        "drop_beats": markers["drop_beats"],
        "breakdown_beats": markers["breakdown_beats"],
        "buildup_beats": markers["buildup_beats"],
        "total_ms": total_ms,
        "errors": [],
    }


def _safe_float_list(values: Any) -> list[float]:
    if values is None:
        return []
    result: list[float] = []
    for value in values:
        try:
            result.append(float(value))
        except Exception:
            continue
    return result


def _safe_int_list(values: Any) -> list[int]:
    if values is None:
        return []
    result: list[int] = []
    for value in values:
        try:
            result.append(int(value))
        except Exception:
            continue
    return result


def _manifest_has_field(track: dict[str, Any], key: str) -> bool:
    return key in track and track.get(key) is not None


def _normalize_manifest_track(track: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(track)
    warnings = list(normalized.get("warnings", [])) if isinstance(normalized.get("warnings"), list) else []
    normalized["warnings"] = warnings

    waveform_present = _manifest_has_field(normalized, "waveform_values") or _manifest_has_field(normalized, "energy_values")
    anlz_path = str(normalized.get("anlz_path", "") or "")
    extracted: dict[str, Any] = {}
    if not waveform_present and anlz_path:
        extracted = _extract_waveform_and_grid_for_root(anlz_path)
        if extracted.get("errors"):
            warnings.extend(str(err) for err in extracted["errors"])
            warnings.append("waveform_extraction_failed")

    if _manifest_has_field(normalized, "waveform_values"):
        normalized["waveform_values"] = _safe_float_list(normalized.get("waveform_values"))
    elif _manifest_has_field(normalized, "energy_values"):
        normalized["waveform_values"] = _safe_float_list(normalized.get("energy_values"))
    else:
        normalized["waveform_values"] = _safe_float_list(extracted.get("waveform_values", []))

    if _manifest_has_field(normalized, "waveform_source"):
        normalized["waveform_source"] = str(normalized.get("waveform_source", "") or "")
    else:
        normalized["waveform_source"] = str(extracted.get("waveform_source", "") or "")

    if _manifest_has_field(normalized, "beatgrid_times_ms"):
        normalized["beatgrid_times_ms"] = _safe_float_list(normalized.get("beatgrid_times_ms"))
    else:
        normalized["beatgrid_times_ms"] = _safe_float_list(extracted.get("beatgrid_times_ms", []))

    for key in ("drop_beats", "breakdown_beats", "buildup_beats"):
        if _manifest_has_field(normalized, key):
            normalized[key] = _safe_int_list(normalized.get(key))
        else:
            normalized[key] = _safe_int_list(extracted.get(key, []))

    try:
        total_ms_value = float(normalized.get("total_ms", 0.0) or 0.0)
    except Exception:
        total_ms_value = 0.0
    if total_ms_value <= 0.0 and extracted:
        total_ms_value = float(extracted.get("total_ms", 0.0) or 0.0)
    normalized["total_ms"] = total_ms_value
    normalized["errors"] = list(extracted.get("errors", []))
    return normalized


def _extract_markers_from_pssi(parsed: list[tuple[Path, Any]]) -> dict[str, list[int]]:
    drops: set[int] = set()
    breakdowns: set[int] = set()
    buildups: set[int] = set()
    for _path, anlz in parsed:
        for tag in _safe_getall_tags(anlz, "PSSI"):
            content = getattr(tag, "content", None)
            mood = int(getattr(content, "mood", 0))
            entries = getattr(content, "entries", None)
            if entries is None and isinstance(content, dict):
                entries = content.get("entries")
            if not entries:
                continue
            for entry in entries:
                try:
                    kind = int(getattr(entry, "kind"))
                    bridge_beat = max(0, int(getattr(entry, "beat")) - 1)
                except Exception:
                    continue
                if bridge_beat <= 0:
                    continue
                if mood == 1:
                    if kind == 5:
                        drops.add(bridge_beat)
                    elif kind == 3:
                        breakdowns.add(bridge_beat)
                    elif kind == 2:
                        buildups.add(bridge_beat)
                elif mood in (2, 3):
                    if kind == 9:
                        drops.add(bridge_beat)
                    elif kind == 8:
                        breakdowns.add(bridge_beat)
                    elif kind in (4, 5):
                        buildups.add(bridge_beat)
    return {
        "drop_beats": sorted(drops),
        "breakdown_beats": sorted(breakdowns),
        "buildup_beats": sorted(buildups),
    }


def _classify_profile(marker_rows: list[dict[str, Any]]) -> str:
    if not marker_rows:
        return "unknown"
    peak_or_major_drop = sum(
        1 for row in marker_rows if row["marker_kind"] == "drop" and row["class_name"] in ("peak", "major")
    )
    strong_breakdowns = sum(
        1 for row in marker_rows if row["marker_kind"] == "breakdown" and row["class_name"] in ("peak", "major")
    )
    if peak_or_major_drop >= 2:
        return "high_energy_peak"
    if strong_breakdowns >= 2 and peak_or_major_drop == 0:
        return "breakdown_heavy"
    if peak_or_major_drop == 0 and strong_breakdowns <= 1:
        return "chill_minimal"
    return "standard_dance"


def _marker_action(marker_kind: str, class_name: str) -> str:
    if marker_kind == "drop":
        if class_name == "peak":
            return "candidate_blackout_mask_high_laser"
        if class_name in ("major", "medium"):
            return "normal_smart_drop_behavior"
        if class_name == "subtle":
            return "avoid_blackout"
        return "no_change_low_confidence"
    if marker_kind == "breakdown":
        if class_name in ("peak", "major"):
            return "clear_minimal_look"
        if class_name == "subtle":
            return "reduce_intensity"
        return "no_change_low_confidence"
    if marker_kind == "buildup":
        if class_name in ("major", "medium"):
            return "rising_energy_escalation_ok"
        if class_name == "subtle":
            return "small_escalation_only"
        return "no_change_low_confidence"
    return "no_change"


def _elapsed_ms_for_marker(beat: int, beatgrid: list[float]) -> float | None:
    if len(beatgrid) < 2:
        return None
    if 0 <= beat < len(beatgrid):
        return round(float(beatgrid[beat]), 3)
    interval = beatgrid[-1] - beatgrid[-2]
    if interval <= 0.0:
        return None
    if beat >= len(beatgrid):
        extra = beat - (len(beatgrid) - 1)
        return round(float(beatgrid[-1] + (extra * interval)), 3)
    return round(float(beatgrid[0] + (beat * interval)), 3)


def _analyze_track(
    track: dict[str, Any],
    track_index: int,
    pre_beats: int,
    post_beats: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    beatgrid = [value for value in _safe_float_list(track.get("beatgrid_times_ms", [])) if value >= 0.0]
    waveform = _safe_float_list(track.get("waveform_values", []))
    total_ms = float(track.get("total_ms", 0.0) or 0.0)
    track_id = f"track-{track_index}"
    track_filepath = str(track.get("track_filepath", "") or "")
    anlz_path = str(track.get("anlz_path", "") or "")
    waveform_source = str(track.get("waveform_source", "") or "")
    warnings = [str(value) for value in track.get("warnings", [])] if isinstance(track.get("warnings"), list) else []
    marker_rows: list[dict[str, Any]] = []

    marker_sets = (
        ("drop", [int(value) for value in track.get("drop_beats", [])]),
        ("breakdown", [int(value) for value in track.get("breakdown_beats", [])]),
        ("buildup", [int(value) for value in track.get("buildup_beats", [])]),
    )
    for marker_kind, beats in marker_sets:
        for beat in beats:
            window = energy_window_for_beat(
                beat=beat,
                beatgrid_times_ms=beatgrid,
                energy_values=waveform,
                total_ms=total_ms,
                pre_beats=pre_beats,
                post_beats=post_beats,
            )
            if window is None:
                row_warning = ""
                if not waveform:
                    row_warning = "missing_waveform_data"
                elif len(beatgrid) < 2:
                    row_warning = "missing_or_short_beatgrid"
                else:
                    row_warning = "window_unavailable"
                if warnings:
                    row_warning = f"{row_warning};{warnings[0]}"
                marker_rows.append(
                    {
                        "record_type": "marker",
                        "track_index": track_index,
                        "track_id": track_id,
                        "track": track_filepath or anlz_path,
                        "track_filepath": track_filepath,
                        "anlz_path": anlz_path,
                        "marker_kind": marker_kind,
                        "beat": beat,
                        "elapsed_ms": _elapsed_ms_for_marker(beat, beatgrid),
                        "waveform_source": waveform_source,
                        "class_name": "low_confidence",
                        "confidence": 0.0,
                        "pre_mean": 0.0,
                        "post_mean": 0.0,
                        "warning": row_warning,
                        "pre_energy": 0.0,
                        "post_energy": 0.0,
                        "lift": 0.0,
                        "recommended_action": "no_change_low_confidence",
                    }
                )
                continue

            if marker_kind == "drop":
                intensity = classify_drop_intensity(window)
            elif marker_kind == "breakdown":
                intensity = classify_breakdown_intensity(window)
            else:
                intensity = classify_buildup_intensity(window)

            marker_rows.append(
                {
                    "record_type": "marker",
                    "track_index": track_index,
                    "track_id": track_id,
                    "track": track_filepath or anlz_path,
                    "track_filepath": track_filepath,
                    "anlz_path": anlz_path,
                    "marker_kind": marker_kind,
                    "beat": beat,
                    "elapsed_ms": _elapsed_ms_for_marker(beat, beatgrid),
                    "waveform_source": waveform_source,
                    "class_name": intensity.class_name,
                    "confidence": intensity.confidence,
                    "pre_mean": round(window.pre_mean, 4),
                    "post_mean": round(window.post_mean, 4),
                    "pre_energy": round(window.pre_mean, 4),
                    "post_energy": round(window.post_mean, 4),
                    "lift": round(window.lift, 4),
                    "recommended_action": _marker_action(marker_kind, intensity.class_name),
                }
            )

    profile = _classify_profile(marker_rows)
    summary = {
        "record_type": "track",
        "track_index": track_index,
        "track_id": track_id,
        "track": track_filepath or anlz_path,
        "track_filepath": track_filepath,
        "anlz_path": anlz_path,
        "waveform_source": waveform_source,
        "detected_waveform_source": waveform_source,
        "total_ms": total_ms,
        "total_beats": max(0, len(beatgrid) - 1),
        "beatgrid_count": len(beatgrid),
        "smart_drop_beats": track.get("drop_beats", []),
        "breakdown_ranges": track.get("breakdown_beats", []),
        "drop_marker_count": len(track.get("drop_beats", [])),
        "breakdown_marker_count": len(track.get("breakdown_beats", [])),
        "buildup_marker_count": len(track.get("buildup_beats", [])),
        "marker_count_total": len(track.get("drop_beats", []))
        + len(track.get("breakdown_beats", []))
        + len(track.get("buildup_beats", [])),
        "warnings": warnings,
        "performance_profile_hint": profile,
    }
    for row in marker_rows:
        row["performance_profile_hint"] = profile
    return summary, marker_rows


def _write_jsonl(records: list[dict[str, Any]], output_path: str) -> None:
    path = Path(output_path).expanduser()
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _render_report(tracks: list[dict[str, Any]], markers: list[dict[str, Any]]) -> str:
    lines = [
        "# ANLZ Energy Corpus Report",
        "",
        "Classification in this report is advisory only and does not change runtime behavior.",
        "",
    ]
    marker_map: dict[str, list[dict[str, Any]]] = {}
    for row in markers:
        marker_map.setdefault(str(row["track"]), []).append(row)

    for track in tracks:
        track_name = str(track["track"])
        rows = marker_map.get(track_name, [])
        lines.extend(
            [
                f"## {track_name}",
                f"- total beats: {track['total_beats']}",
                f"- detected waveform source: {track['waveform_source'] or 'unknown'}",
                f"- smart drop beats: {track['smart_drop_beats']}",
                f"- breakdown ranges: {track['breakdown_ranges']}",
                f"- suggested Performance Profile: {track['performance_profile_hint']}",
                f"- warnings: {track['warnings']}" if track.get("warnings") else "",
                "",
            ]
        )
        for row in rows:
            lines.append(
                "- marker={kind} beat={beat} pre={pre:.3f} post={post:.3f} lift={lift:.3f} "
                "confidence={confidence:.3f} class={cls} action={action}".format(
                    kind=row["marker_kind"],
                    beat=row["beat"],
                    pre=row["pre_energy"],
                    post=row["post_energy"],
                    lift=row["lift"],
                    confidence=row["confidence"],
                    cls=row["class_name"],
                    action=row["recommended_action"],
                )
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze ANLZ waveform energy corpus (offline/read-only).")
    parser.add_argument("--anlz", nargs="+", help="ANLZ path(s) to analyze directly.")
    parser.add_argument("--manifest", help="JSON/CSV manifest file with track + marker metadata.")
    parser.add_argument("--jsonl-out", required=True, help="Output JSONL path.")
    parser.add_argument("--report-out", help="Output Markdown report path (stdout if omitted).")
    parser.add_argument("--pre-beats", type=int, default=16, help="Window size before each marker beat.")
    parser.add_argument("--post-beats", type=int, default=16, help="Window size after each marker beat.")
    parser.add_argument("--limit-tracks", type=int, default=0, help="Optional max tracks to process.")
    args = parser.parse_args()

    if not args.anlz and not args.manifest:
        parser.error("provide --anlz or --manifest")
    if args.anlz and args.manifest:
        parser.error("use either --anlz or --manifest, not both")

    tracks: list[dict[str, Any]] = []
    if args.manifest:
        try:
            manifest_tracks = _read_manifest(args.manifest)
        except Exception as exc:
            parser.error(f"unable to read manifest: {exc}")
        tracks = [_normalize_manifest_track(track) for track in manifest_tracks]
    elif args.anlz:
        extracted_tracks: list[dict[str, Any]] = []
        for anlz_root in args.anlz:
            extracted = _extract_waveform_and_grid_for_root(anlz_root)
            extracted_tracks.append(
                {
                    "track_filepath": "",
                    "anlz_path": anlz_root,
                    "waveform_values": extracted.get("waveform_values", []),
                    "waveform_source": extracted.get("waveform_source", ""),
                    "beatgrid_times_ms": extracted.get("beatgrid_times_ms", []),
                    "drop_beats": extracted.get("drop_beats", []),
                    "breakdown_beats": extracted.get("breakdown_beats", []),
                    "buildup_beats": extracted.get("buildup_beats", []),
                    "total_ms": extracted.get("total_ms", 0.0),
                    "warnings": list(extracted.get("errors", [])),
                }
            )
        tracks = extracted_tracks

    if args.limit_tracks > 0:
        tracks = tracks[: args.limit_tracks]

    summaries: list[dict[str, Any]] = []
    marker_rows: list[dict[str, Any]] = []
    for index, track in enumerate(tracks, start=1):
        summary, rows = _analyze_track(track, track_index=index, pre_beats=args.pre_beats, post_beats=args.post_beats)
        summaries.append(summary)
        marker_rows.extend(rows)

    all_records = summaries + marker_rows
    _write_jsonl(all_records, args.jsonl_out)

    report = _render_report(summaries, marker_rows)
    if args.report_out:
        Path(args.report_out).expanduser().write_text(report + "\n", encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
