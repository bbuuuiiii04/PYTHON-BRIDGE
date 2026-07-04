#!/usr/bin/env python3
"""Build reduced SoundSwitch U0 parity fixtures from a passive capture."""
from __future__ import annotations

import argparse
import bisect
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.soundswitch_laser_player import CHANNEL_COUNT, render_scripted_frame  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_loader import (  # noqa: E402
    LoadedAutoloop,
    LoadedDocument,
    LoadedScriptedTrack,
    LoadedTimelineEvent,
    load_pack,
)
from rb_ss_bridge_v2.tools.ssfmt.soundswitch_parity_oracle import (  # noqa: E402
    AutoloopSample,
    OracleReport,
    classify_autoloop,
)

DEFAULT_CAPTURE = REPO_ROOT / "tools/ssfmt/captures/parity/parity_20260701T185231Z"
DEFAULT_WITNESS_SSIDS = (
    "528e8b22-bd17-41b9-a111-275d3e8b3031",
    "ae9e3c61-af40-4392-80b4-380d39c631b9",
    "9947c65e-cfd1-476e-aa90-4aed65ae5f11",
    "fc10fc02-93c2-418f-8815-16088884da42",
)
AUTOLOOP_RUN_MARGIN_MS = 10
AUTOLOOP_SEGMENT_GAP_NS = 1_000_000_000
CONTROL_CHANNELS = frozenset((8, 9, 11))
STATIC_UNAVAILABLE_REASON = (
    "actions.jsonl contains no completed static_held windows; slot 31 unavailable"
)


@dataclass(frozen=True, slots=True)
class JoinResult:
    rows: tuple[dict[str, Any], ...]
    stats: Mapping[str, int | float]


def normalize_ssid(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    return text.lower()


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("rb") as handle:
        for raw in handle:
            if raw.strip():
                yield json.loads(raw)


def iter_artdmx(path: Path, universe: int) -> Iterable[dict[str, Any]]:
    marker = f'"universe":{universe},'.encode("ascii")
    with path.open("rb") as handle:
        for raw in handle:
            if marker not in raw:
                continue
            row = json.loads(raw)
            if row.get("universe") == universe:
                yield row


def build_u0_runs(packet_path: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in iter_artdmx(packet_path, 0):
        mono_ns = int(row["mono_ns"])
        sha = str(row["dmx_sha256"])
        frame = tuple(int(value) for value in row["ch1_32"][:CHANNEL_COUNT])
        if current and current["dmx_sha256"] == sha:
            current["e"] = mono_ns
            current["n"] += 1
            continue
        if current:
            runs.append(current)
        current = {"s": mono_ns, "e": mono_ns, "n": 1, "dmx_sha256": sha, "f": frame}
    if current:
        runs.append(current)
    return runs


def _signature(row: Mapping[str, Any]) -> tuple[int, str]:
    return int(row["sequence"]) & 0xFF, str(row["dmx_sha256"])


def _sidecar_rows(
    rows: Iterable[Mapping[str, Any]],
    witness_ssids: set[str],
) -> Iterable[dict[str, Any]]:
    for row in rows:
        ssid = normalize_ssid(row.get("soundswitch_id"))
        if ssid in witness_ssids:
            yield {
                "ssid": ssid,
                "sequence": int(row["sequence"]) & 0xFF,
                "dmx_sha256": str(row["dmx_sha256"]),
                "elapsed_ms": int(row["elapsed_ms"]),
                "frame_index": int(row.get("frame_index", -1)),
                "transport": str(row.get("transport") or ""),
            }


def _autoloop_rows(
    rows: Iterable[Mapping[str, Any]],
    identities: set[str],
) -> Iterable[dict[str, Any]]:
    for row in rows:
        native = row.get("native_autoloop")
        if not isinstance(native, Mapping):
            continue
        identity = str(native.get("target_identity") or "")
        phase_tick = native.get("phase_tick")
        if identity not in identities or type(phase_tick) is not int:
            continue
        yield {
            "identity": identity,
            "sequence": int(row["sequence"]) & 0xFF,
            "dmx_sha256": str(row["dmx_sha256"]),
            "elapsed_ms": int(row["elapsed_ms"]),
            "frame_index": int(row.get("frame_index", -1)),
            "phase_tick": phase_tick,
            "status": str(native.get("status") or ""),
        }


def _monotone_ratio(rows: Sequence[Mapping[str, Any]], group_key: str = "ssid") -> float:
    total = 0
    ok = 0
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row[group_key]), []).append(row)
    for group in grouped.values():
        for left, right in zip(group, group[1:]):
            elapsed_delta = int(right["elapsed_ms"]) - int(left["elapsed_ms"])
            mono_delta = int(right["mono_ns"]) - int(left["mono_ns"])
            total += 1
            if elapsed_delta == 0 or mono_delta == 0 or (elapsed_delta > 0) == (mono_delta > 0):
                ok += 1
    return 1.0 if total == 0 else ok / total


def _join_rows_to_mono(
    rows: Iterable[Mapping[str, Any]],
    u1_rows: Iterable[Mapping[str, Any]],
    *,
    group_key: str,
    lookahead: int,
) -> JoinResult:
    u1_iter = iter(u1_rows)
    joined: list[dict[str, Any]] = []
    consumed = 0
    dropped = 0
    for row in rows:
        target = _signature(row)
        for offset in range(max(1, lookahead)):
            try:
                packet = next(u1_iter)
            except StopIteration:
                dropped += 1
                break
            consumed += 1
            if _signature(packet) != target:
                if offset + 1 >= lookahead:
                    dropped += 1
                continue
            joined.append({
                **row,
                "mono_ns": int(packet["mono_ns"]),
            })
            break
    ratio = _monotone_ratio(joined, group_key)
    if ratio < 0.99:
        raise ValueError(f"sidecar/U1 join is not jointly monotone: {ratio:.3f}")
    return JoinResult(
        rows=tuple(joined),
        stats={"joined": len(joined), "dropped": dropped, "u1_consumed": consumed,
               "monotone_ratio": ratio},
    )


def join_sidecar_to_mono(
    sidecar_rows: Iterable[Mapping[str, Any]],
    u1_rows: Iterable[Mapping[str, Any]],
    *,
    witness_ssids: Iterable[str] = DEFAULT_WITNESS_SSIDS,
    lookahead: int = 10_000,
) -> JoinResult:
    witnesses = {normalize_ssid(value) for value in witness_ssids}
    return _join_rows_to_mono(
        _sidecar_rows(sidecar_rows, witnesses),
        u1_rows,
        group_key="ssid",
        lookahead=lookahead,
    )


def join_autoloop_to_mono(
    sidecar_rows: Iterable[Mapping[str, Any]],
    u1_rows: Iterable[Mapping[str, Any]],
    *,
    identities: Iterable[str],
    lookahead: int = 10_000,
) -> JoinResult:
    return _join_rows_to_mono(
        _autoloop_rows(sidecar_rows, {str(value) for value in identities}),
        u1_rows,
        group_key="identity",
        lookahead=lookahead,
    )


def load_alignment_windows(path: Path, *, surface: str = "scripted") -> dict[str, tuple[dict[str, Any], ...]]:
    windows: dict[str, list[dict[str, Any]]] = {}
    for row in iter_jsonl(path):
        if row.get("surface") != surface:
            continue
        if surface == "autoloop":
            key = str(row.get("loop_identity") or str(row.get("label", "")).removeprefix("autoloop_"))
        else:
            key = normalize_ssid(row.get("ssid") or str(row.get("label", "")).removeprefix("scripted_"))
        if not key:
            continue
        windows.setdefault(key, []).append({
            "t_start_mono": row.get("t_start_mono"),
            "t_end_mono": row.get("t_end_mono"),
            "frame_index_start": row.get("frame_index_start"),
            "frame_index_end": row.get("frame_index_end"),
        })
    return {ssid: tuple(rows) for ssid, rows in windows.items()}


def _inside_window(row: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]) -> bool:
    if not windows:
        return True
    mono_s = int(row["mono_ns"]) / 1_000_000_000
    frame_index = int(row.get("frame_index", -1))
    for window in windows:
        start = window.get("t_start_mono")
        end = window.get("t_end_mono")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) \
                and float(start) <= mono_s <= float(end):
            return True
        first = window.get("frame_index_start")
        last = window.get("frame_index_end")
        if isinstance(first, int) and isinstance(last, int) and first <= frame_index <= last:
            return True
    return False


def _event_time(event: LoadedTimelineEvent | Mapping[str, Any]) -> int:
    if isinstance(event, Mapping):
        return int(event["time"])
    return int(event.time)


def _candidate_targets(events: Sequence[LoadedTimelineEvent | Mapping[str, Any]]) -> list[tuple[int, str]]:
    times = sorted({time for event in events if (time := _event_time(event)) >= 0})
    targets: list[tuple[int, str]] = []
    for index, time in enumerate(times):
        targets.append((time + 150, f"event_{index:04d}_post_boundary"))
        if index + 1 < len(times) and times[index + 1] - time > 2_000:
            targets.append(((time + times[index + 1]) // 2, f"event_{index:04d}_mid_hold"))
    return targets


def _nearest_elapsed(rows: Sequence[Mapping[str, Any]], target_ms: int) -> Mapping[str, Any] | None:
    if not rows:
        return None
    elapsed = [int(row["elapsed_ms"]) for row in rows]
    index = bisect.bisect_left(elapsed, target_ms)
    choices = []
    if index < len(rows):
        choices.append(rows[index])
    if index:
        choices.append(rows[index - 1])
    return min(choices, key=lambda row: abs(int(row["elapsed_ms"]) - target_ms))


def _run_for_mono(runs: Sequence[Mapping[str, Any]], mono_ns: int, margin_ns: int) -> Mapping[str, Any] | None:
    for run in runs:
        start = int(run["s"])
        end = int(run["e"])
        if start <= mono_ns <= end and start + margin_ns <= mono_ns <= end - margin_ns:
            return run
    return None


def select_rows(
    joined: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    events: Sequence[LoadedTimelineEvent | Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]] = (),
    *,
    margin_ms: int = 120,
) -> list[dict[str, Any]]:
    rows = sorted(joined, key=lambda row: int(row["elapsed_ms"]))
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for target_ms, label in _candidate_targets(events):
        candidate = _nearest_elapsed(rows, target_ms)
        if candidate is None or not _inside_window(candidate, windows):
            continue
        run = _run_for_mono(runs, int(candidate["mono_ns"]), margin_ms * 1_000_000)
        if run is None:
            continue
        key = (str(candidate["ssid"]), int(candidate["mono_ns"]))
        if key in seen:
            continue
        seen.add(key)
        run_ms = max(0, int(round((int(run["e"]) - int(run["s"])) / 1_000_000)))
        selected.append({
            "elapsed_ms": int(candidate["elapsed_ms"]),
            "label": label,
            "mono_ns": int(candidate["mono_ns"]),
            "run_ms": run_ms,
            "u0_frame": list(run["f"]),
        })
    return selected


def _spread_phase_rows(rows: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return list(rows)
    selected = {0, len(rows) - 1}
    for index in range(limit):
        selected.add(round(index * (len(rows) - 1) / max(1, limit - 1)))
    return [rows[index] for index in sorted(selected)][:limit]


def split_autoloop_segments(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_gap_ns: int = AUTOLOOP_SEGMENT_GAP_NS,
) -> list[tuple[dict[str, Any], ...]]:
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_mono: int | None = None
    for row in sorted(rows, key=lambda item: int(item["mono_ns"])):
        mono_ns = int(row["mono_ns"])
        if previous_mono is not None and mono_ns - previous_mono > max_gap_ns:
            if current:
                segments.append(current)
            current = []
        current.append(dict(row))
        previous_mono = mono_ns
    if current:
        segments.append(current)
    return [tuple(segment) for segment in segments]


def select_autoloop_rows(
    joined: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]] = (),
    *,
    limit: int = 8,
    margin_ms: int = AUTOLOOP_RUN_MARGIN_MS,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_phases: set[int] = set()
    for candidate in sorted(joined, key=lambda row: int(row["phase_tick"])):
        if not _inside_window(candidate, windows):
            continue
        phase_tick = int(candidate["phase_tick"])
        if phase_tick in seen_phases:
            continue
        run = _run_for_mono(runs, int(candidate["mono_ns"]), margin_ms * 1_000_000)
        if run is None:
            continue
        seen_phases.add(phase_tick)
        run_ms = max(0, int(round((int(run["e"]) - int(run["s"])) / 1_000_000)))
        selected.append({
            "label": f"phase_{phase_tick}",
            "mono_ns": int(candidate["mono_ns"]),
            "phase_tick": phase_tick,
            "run_ms": run_ms,
            "status": str(candidate.get("status") or ""),
            "u0_frame": list(run["f"]),
        })
    return _spread_phase_rows(selected, limit)


def _autoloop_samples(rows: Sequence[Mapping[str, Any]]) -> tuple[AutoloopSample, ...]:
    return tuple(
        AutoloopSample(
            phase_tick=int(row["phase_tick"]),
            u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
            label=str(row.get("label") or ""),
        )
        for row in rows
    )


def _passed_sample_count(report: OracleReport) -> int:
    return sum(1 for row in report.samples if row.issue in ("match", "u0_dark"))


def _event_summary(document: LoadedDocument) -> list[dict[str, Any]]:
    return [
        {
            "source_order": event.source_order,
            "time": event.time,
            "raw_reference": event.raw_reference,
            "reference_kind": event.reference_kind,
            "channels": [
                attribute.dmx_channel
                for attribute in event.patch
                if 1 <= attribute.dmx_channel <= CHANNEL_COUNT
            ],
        }
        for event in document.events
    ]


def _autoloop_diagnostic(
    identity: str,
    loop: LoadedAutoloop,
    rows: Sequence[Mapping[str, Any]],
    report: OracleReport,
    *,
    segment_index: int,
    segment_count: int,
    reason: str = "best_contiguous_segment_failed_oracle",
) -> dict[str, Any]:
    by_phase = {int(row["phase_tick"]): row for row in rows}
    return {
        "class": "autoloop_capture_divergence",
        "identity": identity,
        "reason": reason,
        "segment_index": segment_index,
        "segments_evaluated": segment_count,
        "cycle_ticks": loop.document.cycle_ticks,
        "rows_passed": _passed_sample_count(report),
        "rows_total": len(report.samples),
        "serialized_event_count": len(loop.document.events),
        "serialized_events": _event_summary(loop.document),
        "samples": [
            {
                "label": sample.label,
                "phase_tick": sample.phase_tick,
                "mono_ns": int(by_phase.get(sample.phase_tick, {}).get("mono_ns", 0)),
                "run_ms": int(by_phase.get(sample.phase_tick, {}).get("run_ms", 0)),
                "class_name": sample.class_name,
                "issue": sample.issue,
                "expected_disk_frame": list(sample.expected_frame),
                "observed_u0_frame": list(sample.u0_frame),
                "channel_diffs": _diffs(sample.expected_frame, sample.u0_frame),
            }
            for sample in report.samples
        ],
    }


def _no_autoloop_rows_diagnostic(
    identity: str,
    loop: LoadedAutoloop,
    *,
    segment_count: int,
) -> dict[str, Any]:
    return {
        "class": "autoloop_capture_divergence",
        "identity": identity,
        "reason": "no_steady_u0_rows_in_contiguous_segments",
        "segments_evaluated": segment_count,
        "cycle_ticks": loop.document.cycle_ticks,
        "serialized_event_count": len(loop.document.events),
        "serialized_events": _event_summary(loop.document),
        "samples": [],
    }


def _diffs(expected: Sequence[int], observed: Sequence[int]) -> list[dict[str, int]]:
    return [
        {"channel": index, "expected": int(left), "u0": int(right)}
        for index, (left, right) in enumerate(zip(expected, observed), 1)
        if int(left) != int(right)
    ]


def _document_from(value: LoadedDocument | LoadedScriptedTrack) -> LoadedDocument:
    if isinstance(value, LoadedScriptedTrack):
        if value.document is None:
            raise ValueError("scripted track has no loaded document")
        return value.document
    return value


def _reachable_by_channel(frame: Sequence[int], document: LoadedDocument) -> bool:
    values: dict[int, set[int]] = {channel: set() for channel in range(1, CHANNEL_COUNT + 1)}
    for event in document.events:
        for attribute in event.patch:
            if 1 <= attribute.dmx_channel <= CHANNEL_COUNT:
                values[attribute.dmx_channel].add(attribute.value)
    return all(value == 0 or int(value) in values[index]
               for index, value in enumerate(frame, 1))


def _nearest_event(document: LoadedDocument, elapsed_ms: int) -> LoadedTimelineEvent | None:
    if not document.events:
        return None
    return min(document.events, key=lambda event: abs(event.time - elapsed_ms))


def screen_rows(
    rows: Sequence[Mapping[str, Any]],
    document: LoadedDocument | LoadedScriptedTrack,
    venue_values: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    del venue_values
    doc = _document_from(document)
    witnesses: list[dict[str, Any]] = []
    divergence: list[dict[str, Any]] = []
    for row in rows:
        observed = tuple(int(value) for value in row["u0_frame"])
        if len(observed) != CHANNEL_COUNT:
            raise ValueError("U0 frame must contain 19 channels")
        expected = render_scripted_frame(doc, int(row["elapsed_ms"]))
        if expected == observed:
            witnesses.append(dict(row))
            continue
        event = _nearest_event(doc, int(row["elapsed_ms"]))
        if not _reachable_by_channel(observed, doc):
            class_name = "cross_deck_bleed"
        elif event is not None:
            class_name = "stale_source_edit"
        else:
            class_name = "join_ambiguity"
        divergence.append({
            "class": class_name,
            "elapsed_ms": int(row["elapsed_ms"]),
            "label": str(row.get("label") or ""),
            "mono_ns": int(row.get("mono_ns", 0)),
            "event_time": None if event is None else event.time,
            "raw_reference": None if event is None else event.raw_reference,
            "expected_disk_frame": list(expected),
            "observed_u0_frame": list(observed),
            "channel_diffs": _diffs(expected, observed),
        })
    return witnesses, divergence


def build_scripted_fixture(
    capture: Path,
    pack_path: Path,
    *,
    witness_ssids: Iterable[str] = DEFAULT_WITNESS_SSIDS,
) -> dict[str, Any]:
    witnesses = tuple(normalize_ssid(value) for value in witness_ssids)
    pack = load_pack(pack_path)
    runs = build_u0_runs(capture / "artdmx_packets.jsonl")
    joined = join_sidecar_to_mono(
        iter_jsonl(capture / "rbss_artnet_truth_frames.slice.jsonl"),
        iter_artdmx(capture / "artdmx_packets.jsonl", 1),
        witness_ssids=witnesses,
    )
    windows = load_alignment_windows(capture / "alignment_index.jsonl")
    scripted: dict[str, list[dict[str, Any]]] = {}
    ledger: dict[str, list[dict[str, Any]]] = {}
    for ssid in witnesses:
        track = pack.scripted.get(ssid)
        if not isinstance(track, LoadedScriptedTrack) or track.document is None:
            ledger[ssid] = [{"class": "join_ambiguity", "reason": "missing_scripted_doc"}]
            scripted[ssid] = []
            continue
        selected = select_rows(
            [row for row in joined.rows if row["ssid"] == ssid],
            runs,
            track.document.events,
            windows.get(ssid, ()),
        )
        witness_rows, divergence_rows = screen_rows(selected, track.document)
        scripted[ssid] = witness_rows
        if divergence_rows:
            ledger[ssid] = divergence_rows
    return {
        "capture_id": capture.name,
        "scripted": scripted,
        "capture_source_divergence": ledger,
        "builder": {
            "tool": "tools/ssfmt/build_parity_fixture.py",
            "join_stats": dict(joined.stats),
        },
    }


AutoloopCandidate = tuple[int, Sequence[dict[str, Any]], OracleReport]
AutoloopLedgerEntry = tuple[int, Sequence[dict[str, Any]], OracleReport, str]


def _autoloop_candidate_rank(candidate: AutoloopCandidate) -> tuple[bool, int, int, int]:
    segment_index, selected, report = candidate
    return (report.passed, _passed_sample_count(report), len(selected), -segment_index)


def choose_autoloop_candidate(
    candidates: Sequence[AutoloopCandidate],
) -> tuple[AutoloopCandidate | None, list[AutoloopLedgerEntry]]:
    """Pick the promoted segment (if any passed) and ledger every other non-PASS segment.

    ``candidates`` holds one entry per contiguous capture segment that produced at
    least one selected U0 row (segments with zero selected rows are excluded by the
    caller before this is invoked). Returns ``(promoted, ledger)`` where ``promoted``
    is ``None`` when no segment passed the oracle. PASS segments are never ledgered:
    only the chosen best candidate (when nothing passed) and the non-promoted
    non-PASS siblings are recorded, ordered by ``segment_index``.
    """
    if not candidates:
        return None, []
    ordered = sorted(candidates, key=lambda item: item[0])
    passed = [candidate for candidate in candidates if candidate[2].passed]
    if passed:
        promoted = max(passed, key=_autoloop_candidate_rank)
        ledger = [
            (segment_index, selected, report, "sibling_segment_failed_oracle")
            for segment_index, selected, report in ordered
            if not report.passed
        ]
        return promoted, ledger
    best = max(candidates, key=_autoloop_candidate_rank)
    best_index = best[0]
    ledger = [
        (
            segment_index,
            selected,
            report,
            "best_contiguous_segment_failed_oracle" if segment_index == best_index
            else "sibling_segment_failed_oracle",
        )
        for segment_index, selected, report in ordered
    ]
    return None, ledger


def build_autoloop_fixture(
    capture: Path,
    pack_path: Path,
    *,
    identities: Iterable[str] | None = None,
) -> dict[str, Any]:
    pack = load_pack(pack_path)
    runs = build_u0_runs(capture / "artdmx_packets.jsonl")
    windows = load_alignment_windows(capture / "alignment_index.jsonl", surface="autoloop")
    selected_identities = tuple(sorted(str(value) for value in (identities or windows.keys())))
    joined = join_autoloop_to_mono(
        iter_jsonl(capture / "rbss_artnet_truth_frames.slice.jsonl"),
        iter_artdmx(capture / "artdmx_packets.jsonl", 1),
        identities=selected_identities,
    )
    autoloop: dict[str, list[dict[str, Any]]] = {}
    missing: dict[str, list[dict[str, Any]]] = {}
    for identity in selected_identities:
        loop = pack.autoloops.get(identity)
        if not isinstance(loop, LoadedAutoloop):
            missing[identity] = [{"class": "join_ambiguity", "reason": "missing_autoloop_doc"}]
            autoloop[identity] = []
            continue
        segments = split_autoloop_segments([row for row in joined.rows if row["identity"] == identity])
        candidates: list[AutoloopCandidate] = []
        for segment_index, segment in enumerate(segments):
            selected = select_autoloop_rows(segment, runs, windows.get(identity, ()))
            if not selected:
                continue
            report = classify_autoloop(loop, _autoloop_samples(selected))
            candidates.append((segment_index, selected, report))
        if not candidates:
            autoloop[identity] = []
            missing[identity] = [_no_autoloop_rows_diagnostic(
                identity,
                loop,
                segment_count=len(segments),
            )]
            continue
        promoted, ledger_entries = choose_autoloop_candidate(candidates)
        autoloop[identity] = list(promoted[1]) if promoted is not None else []
        if ledger_entries:
            missing[identity] = [
                _autoloop_diagnostic(
                    identity,
                    loop,
                    selected,
                    report,
                    segment_index=segment_index,
                    segment_count=len(segments),
                    reason=reason,
                )
                for segment_index, selected, report, reason in ledger_entries
            ]
    fixture = {
        "capture_id": capture.name,
        "autoloop": autoloop,
        "builder": {
            "tool": "tools/ssfmt/build_parity_fixture.py",
            "join_stats": dict(joined.stats),
        },
    }
    if missing:
        fixture["capture_source_divergence"] = missing
    return fixture


def _slot_values(rows: Iterable[Mapping[str, Any]], label_suffix: str) -> tuple[int, ...]:
    slots: list[int] = []
    seen: set[int] = set()
    for row in rows:
        label = str(row.get("label") or "")
        slot = row.get("look_slot")
        if type(slot) is int and label.endswith(label_suffix) and slot not in seen:
            slots.append(slot)
            seen.add(slot)
    return tuple(slots)


def build_static_fixture(capture: Path, pack_path: Path) -> dict[str, Any]:
    del pack_path
    action_rows = tuple(iter_jsonl(capture / "actions.jsonl"))
    attempted_slots = _slot_values(action_rows, "_incomplete_no_static_held")
    unavailable_slots = _slot_values(action_rows, "_reclassified_unavailable_from_streamdeck")
    summary: Mapping[str, Any] = {}
    capture_end = capture / "capture_end.json"
    if capture_end.exists():
        data = json.loads(capture_end.read_text(encoding="utf-8"))
        surfaces = data.get("surfaces")
        if isinstance(surfaces, Mapping) and isinstance(surfaces.get("static"), Mapping):
            summary = surfaces["static"]
    if not attempted_slots:
        attempted = summary.get("attempted_slots")
        if isinstance(attempted, list):
            attempted_slots = tuple(slot for slot in attempted if type(slot) is int)
    if not unavailable_slots:
        unavailable = summary.get("unavailable_slots")
        if isinstance(unavailable, list):
            unavailable_slots = tuple(slot for slot in unavailable if type(slot) is int)
    attempted_slots = tuple(slot for slot in attempted_slots if slot not in set(unavailable_slots))
    reason = str(summary.get("reason") or STATIC_UNAVAILABLE_REASON)
    return {
        "capture_id": capture.name,
        "static": {},
        "static_capture_windows": "unavailable",
        "reason": reason,
        "attempted_slots": list(attempted_slots),
        "unavailable_slots": list(unavailable_slots),
        "builder": {
            "tool": "tools/ssfmt/build_parity_fixture.py",
            "actions": {
                "attempted_slots": list(attempted_slots),
                "unavailable_slots": list(unavailable_slots),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--surface", choices=("scripted", "autoloop", "static"), default="scripted")
    parser.add_argument("--ssid", action="append", default=None,
                        help="Scripted witness SoundSwitch ID. Defaults to the parity witnesses.")
    parser.add_argument("--autoloop-identity", action="append", default=None,
                        help="Autoloop identity. Defaults to autoloops covered by the capture alignment.")
    args = parser.parse_args(argv)

    if args.surface == "static":
        fixture = build_static_fixture(args.capture, args.pack)
    elif args.surface == "autoloop":
        fixture = build_autoloop_fixture(
            args.capture,
            args.pack,
            identities=args.autoloop_identity,
        )
    else:
        fixture = build_scripted_fixture(
            args.capture,
            args.pack,
            witness_ssids=args.ssid or DEFAULT_WITNESS_SSIDS,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
