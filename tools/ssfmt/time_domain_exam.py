#!/usr/bin/env python3
"""Measure SoundSwitch time-domain parity from the July 2026 passive capture."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.soundswitch_laser_player import (  # noqa: E402
    ZERO_FRAME,
    render_autoloop_frame,
    render_scripted_frame,
)
from rb_ss_bridge_v2.soundswitch_pack_loader import (  # noqa: E402
    AUTOLOOP_CYCLE_TICKS,
    LoadedAutoloop,
    LoadedDocument,
    LoadedScriptedTrack,
    load_pack,
)
from rb_ss_bridge_v2.tools.ssfmt.build_parity_fixture import (  # noqa: E402
    DEFAULT_CAPTURE,
    DEFAULT_WITNESS_SSIDS,
    build_u0_runs,
    iter_artdmx,
    iter_jsonl,
    join_autoloop_to_mono,
    join_sidecar_to_mono,
    load_alignment_windows,
    normalize_ssid,
    split_autoloop_segments,
)

WIRE_FRAME_MS = 40.0


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    count: int

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept


def linear_fit(points: Sequence[tuple[float, float]]) -> LinearFit | None:
    if len(points) < 2:
        return None
    x_mean = statistics.fmean(x for x, _ in points)
    y_mean = statistics.fmean(y for _, y in points)
    denom = sum((x - x_mean) ** 2 for x, _ in points)
    if denom == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denom
    return LinearFit(slope=slope, intercept=y_mean - slope * x_mean, count=len(points))


def summarize(values: Sequence[float], *, bound_ms: float = WIRE_FRAME_MS) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    p95 = ordered[min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)]
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 3),
        "rms_ms": round(rms, 3),
        "p95_ms": round(p95, 3),
        "max_abs_ms": round(max(abs(value) for value in values), 3),
        "beyond_one_wire_frame": sum(1 for value in values if abs(value) > bound_ms),
    }


def summarize_counts(values: Sequence[int], *, outlier_threshold: int) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(values),
        "median": statistics.median(values),
        "p95": ordered[min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)],
        "max": max(values),
        "beyond_threshold": sum(1 for value in values if value > outlier_threshold),
    }


def unwrap_ticks(rows: Sequence[Mapping[str, Any]], cycle_ticks: int = AUTOLOOP_CYCLE_TICKS) -> list[int]:
    unwrapped: list[int] = []
    offset = 0
    previous: int | None = None
    for row in rows:
        tick = int(row["phase_tick"])
        if previous is not None and tick + offset < previous - cycle_ticks / 2:
            offset += cycle_ticks
        value = tick + offset
        unwrapped.append(value)
        previous = value
    return unwrapped


def frame_hex(frame: Sequence[int]) -> str:
    return bytes(int(value) & 0xFF for value in frame).hex()


def dmx_sha256(frame: Sequence[int]) -> str:
    payload = bytes(int(value) & 0xFF for value in frame) + bytes(512 - len(frame))
    return hashlib.sha256(payload).hexdigest()


def _run_starts_by_frame(runs: Sequence[Mapping[str, Any]]) -> dict[tuple[int, ...], list[int]]:
    by_frame: dict[tuple[int, ...], list[int]] = {}
    for run in runs:
        by_frame.setdefault(tuple(int(value) for value in run["f"]), []).append(int(run["s"]))
    return by_frame


def nearest_run_start(starts: Sequence[int], predicted_ns: float, *, radius_ms: float = 750.0) -> int | None:
    if not starts:
        return None
    index = bisect.bisect_left(starts, int(predicted_ns))
    choices = []
    if index < len(starts):
        choices.append(starts[index])
    if index:
        choices.append(starts[index - 1])
    if not choices:
        return None
    best = min(choices, key=lambda value: abs(value - predicted_ns))
    return best if abs(best - predicted_ns) <= radius_ms * 1_000_000 else None


def _window_rows(rows: Sequence[Mapping[str, Any]], windows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not windows:
        return list(rows)
    out = []
    for row in rows:
        mono_s = int(row["mono_ns"]) / 1_000_000_000
        frame_index = int(row.get("frame_index", -1))
        for window in windows:
            start = window.get("t_start_mono")
            end = window.get("t_end_mono")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and float(start) <= mono_s <= float(end):
                out.append(row)
                break
            first = window.get("frame_index_start")
            last = window.get("frame_index_end")
            if isinstance(first, int) and isinstance(last, int) and first <= frame_index <= last:
                out.append(row)
                break
    return out


def _scripted_doc(track: LoadedScriptedTrack | LoadedDocument) -> LoadedDocument | None:
    if isinstance(track, LoadedScriptedTrack):
        return track.document
    return track


def scripted_timing(pack_path: Path, capture: Path, runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pack = load_pack(pack_path)
    witnesses = tuple(normalize_ssid(value) for value in DEFAULT_WITNESS_SSIDS)
    joined = join_sidecar_to_mono(
        iter_jsonl(capture / "rbss_artnet_truth_frames.slice.jsonl"),
        iter_artdmx(capture / "artdmx_packets.jsonl", 1),
        witness_ssids=witnesses,
    )
    windows = load_alignment_windows(capture / "alignment_index.jsonl")
    starts_by_frame = _run_starts_by_frame(runs)
    by_ssid: dict[str, Any] = {}
    all_residuals: list[float] = []
    all_decision_deltas: list[float] = []
    for ssid in witnesses:
        track = pack.scripted.get(ssid)
        doc = _scripted_doc(track) if track is not None else None
        rows = _window_rows([row for row in joined.rows if row["ssid"] == ssid], windows.get(ssid, ()))
        fit = linear_fit([(float(row["elapsed_ms"]), float(row["mono_ns"])) for row in rows])
        if doc is None or fit is None:
            by_ssid[ssid] = {"reason": "missing_doc_or_fit", "joined_rows": len(rows)}
            continue
        residuals = []
        decision_deltas = []
        previous = tuple(ZERO_FRAME)
        joined_index = 0
        for event in doc.events:
            expected = render_scripted_frame(doc, int(event.time))
            if expected == previous:
                continue
            previous = expected
            predicted = fit.predict(float(event.time))
            observed = nearest_run_start(starts_by_frame.get(expected, ()), predicted)
            if observed is None:
                continue
            residual_ms = (observed - predicted) / 1_000_000
            residuals.append(residual_ms)
            expected_sha = dmx_sha256(expected)
            while joined_index < len(rows) and (
                int(rows[joined_index]["elapsed_ms"]) < int(event.time)
                or str(rows[joined_index].get("dmx_sha256")) != expected_sha
            ):
                joined_index += 1
            if joined_index < len(rows):
                decision_deltas.append((int(rows[joined_index]["mono_ns"]) - observed) / 1_000_000)
        drift = linear_fit([(float(index), value) for index, value in enumerate(residuals)])
        by_ssid[ssid] = {
            "joined_rows": len(rows),
            "boundary_residuals": summarize(residuals),
            "drift_slope_ms_per_boundary": None if drift is None else round(drift.slope, 6),
            "u1_minus_u0_transition_ms": summarize(decision_deltas),
        }
        all_residuals.extend(residuals)
        all_decision_deltas.extend(decision_deltas)
    return {
        "join_stats": dict(joined.stats),
        "witnesses": by_ssid,
        "overall_boundary_residuals": summarize(all_residuals),
        "overall_u1_minus_u0_transition_ms": summarize(all_decision_deltas),
    }


def autoloop_timing(pack_path: Path, capture: Path, runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pack = load_pack(pack_path)
    windows = load_alignment_windows(capture / "alignment_index.jsonl", surface="autoloop")
    identities = tuple(sorted(windows))
    joined = join_autoloop_to_mono(
        iter_jsonl(capture / "rbss_artnet_truth_frames.slice.jsonl"),
        iter_artdmx(capture / "artdmx_packets.jsonl", 1),
        identities=identities,
    )
    starts_by_frame = _run_starts_by_frame(runs)
    by_identity: dict[str, Any] = {}
    all_residuals: list[float] = []
    all_rates: list[float] = []
    wrap_residuals: list[float] = []
    for identity in identities:
        loop = pack.autoloops.get(identity)
        if not isinstance(loop, LoadedAutoloop):
            by_identity[identity] = {"reason": "missing_autoloop_doc"}
            continue
        rows = _window_rows([row for row in joined.rows if row["identity"] == identity], windows.get(identity, ()))
        segments = split_autoloop_segments(rows)
        residuals = []
        rates = []
        wraps = []
        for segment in segments:
            ordered = sorted(segment, key=lambda row: int(row["mono_ns"]))
            if len(ordered) < 2:
                continue
            unwrapped = unwrap_ticks(ordered, loop.document.cycle_ticks or AUTOLOOP_CYCLE_TICKS)
            fit = linear_fit([(float(tick), float(row["mono_ns"])) for tick, row in zip(unwrapped, ordered)])
            if fit is None:
                continue
            ticks_per_second = 1_000_000_000 / fit.slope if fit.slope else 0.0
            rates.append(ticks_per_second / 600.0 * 60.0)
            cycle_ticks = loop.document.cycle_ticks or AUTOLOOP_CYCLE_TICKS
            base_cycle = (unwrapped[0] // cycle_ticks) * cycle_ticks
            previous = tuple(ZERO_FRAME)
            for event in loop.document.events:
                phase = base_cycle + (int(event.time) % cycle_ticks)
                expected = render_autoloop_frame(loop, phase)
                if expected == previous:
                    continue
                previous = expected
                predicted = fit.predict(float(phase))
                observed = nearest_run_start(starts_by_frame.get(expected, ()), predicted)
                if observed is None:
                    continue
                residual_ms = (observed - predicted) / 1_000_000
                residuals.append(residual_ms)
                wrapped_event = int(event.time) % cycle_ticks
                if wrapped_event < 600 or wrapped_event > cycle_ticks - 600:
                    wraps.append(residual_ms)
        by_identity[identity] = {
            "joined_rows": len(rows),
            "segments": len(segments),
            "transition_residuals": summarize(residuals),
            "wrap_residuals": summarize(wraps),
            "implied_bpm": summarize(rates, bound_ms=999999),
        }
        all_residuals.extend(residuals)
        all_rates.extend(rates)
        wrap_residuals.extend(wraps)
    return {
        "join_stats": dict(joined.stats),
        "loops": by_identity,
        "overall_transition_residuals": summarize(all_residuals),
        "overall_wrap_residuals": summarize(wrap_residuals),
        "overall_implied_bpm": summarize(all_rates, bound_ms=999999),
    }


def capture_inventory(capture: Path) -> dict[str, Any]:
    actions = list(iter_jsonl(capture / "actions.jsonl"))
    alignment = list(iter_jsonl(capture / "alignment_index.jsonl"))
    status = list(iter_jsonl(capture / "status_samples.jsonl"))
    action_labels: dict[str, int] = {}
    for row in actions:
        key = f"{row.get('surface')}:{row.get('label')}"
        action_labels[key] = action_labels.get(key, 0) + 1
    statuses = [row.get("status", {}) for row in status if isinstance(row.get("status"), Mapping)]
    samples_with_bpm = sum(
        1 for row in statuses
        if row.get("heartbeat", {}).get("bpm") not in (None, "unknown", 0, 0.0)
    )
    playing_samples = sum(
        1 for row in statuses
        for deck in row.get("state_manager", {}).get("deck", {}).values()
        if isinstance(deck, Mapping) and deck.get("playing") is True
    )
    return {
        "actions_count": len(actions),
        "alignment_count": len(alignment),
        "status_samples_count": len(status),
        "action_labels": action_labels,
        "status_samples_with_bpm": samples_with_bpm,
        "status_playing_deck_samples": playing_samples,
        "scripted_windows": sum(1 for row in alignment if row.get("surface") == "scripted"),
        "autoloop_windows": sum(1 for row in alignment if row.get("surface") == "autoloop"),
        "static_windows": sum(1 for row in alignment if row.get("surface") == "static"),
    }


def handoffs(capture: Path) -> dict[str, Any]:
    all_scripted = [
        row for row in join_sidecar_to_mono(
            iter_jsonl(capture / "rbss_artnet_truth_frames.slice.jsonl"),
            iter_artdmx(capture / "artdmx_packets.jsonl", 1),
            witness_ssids=[row["ssid"] for row in iter_jsonl(capture / "alignment_index.jsonl") if row.get("surface") == "scripted"],
        ).rows
    ]
    changes = []
    previous: Mapping[str, Any] | None = None
    for row in all_scripted:
        if previous is not None and row.get("ssid") != previous.get("ssid"):
            changes.append({
                "from": previous.get("ssid"),
                "to": row.get("ssid"),
                "mono_gap_ms": round((int(row["mono_ns"]) - int(previous["mono_ns"])) / 1_000_000, 3),
                "elapsed_from": previous.get("elapsed_ms"),
                "elapsed_to": row.get("elapsed_ms"),
            })
        previous = row
    zero_runs = []
    run = 0
    for row in all_scripted:
        if str(row.get("dmx_sha256", "")).startswith("076a27c7"):
            run += 1
        elif run:
            zero_runs.append(run)
            run = 0
    if run:
        zero_runs.append(run)
    return {
        "scripted_handoff_count": len(changes),
        "sample_handoffs": changes[:12],
        "u1_zero_frame_run_lengths_frames": summarize_counts(zero_runs, outlier_threshold=2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    runs = build_u0_runs(args.capture / "artdmx_packets.jsonl")
    result = {
        "capture": str(args.capture),
        "pack": str(args.pack),
        "u0_run_count": len(runs),
        "inventory": capture_inventory(args.capture),
        "scripted": scripted_timing(args.pack, args.capture, runs),
        "autoloop": autoloop_timing(args.pack, args.capture, runs),
        "handoffs": handoffs(args.capture),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(args.out),
        "scripted": result["scripted"]["overall_boundary_residuals"],
        "autoloop": result["autoloop"]["overall_transition_residuals"],
        "handoffs": result["handoffs"]["scripted_handoff_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
