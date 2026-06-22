#!/usr/bin/env python3
"""Layered autoloop validation against passive Art-Net and copied logs."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from analyze_ssfile_structure import parse_autoloop_structure
from layered_renderer import render_timeline, venue_cue_records
from parse_artnet_pcap import universe_frames
from parse_venue_cues import parse_venue_cues


ANSI = re.compile(r"\x1b\[[0-9;]*m")
LOOP_TICKS = 19_200


def time_of_day(value: str) -> float:
    hour, minute, second = value.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


def parse_bridge(path: Path) -> list[tuple]:
    pattern = re.compile(
        r"(\d\d:\d\d:\d\d\.\d+).*\[LX\]\s+"
        r"(fired|blackout_on sent|mask_on)\s+(.*)"
    )
    rows = []
    for line in path.open(errors="replace"):
        match = pattern.search(ANSI.sub("", line))
        if not match:
            continue
        rest = match.group(3)
        scene = (re.search(r"scene=(\S+)", rest) or [None, ""])[1]
        role = (re.search(r"role=(\S+)", rest) or [None, ""])[1]
        note = (re.search(r"note=(\d+)", rest) or [None, ""])[1]
        rows.append((time_of_day(match.group(1)), match.group(2), role, scene, note))
    return sorted(rows)


def parse_app_logs(paths: list[Path]) -> list[dict]:
    timestamp = r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\]"
    autoloop = re.compile(
        timestamp + r".*Deck (\d) running autoloop bank -1, index (\d+)"
    )
    scripted = re.compile(timestamp + r".*Deck (\d) running scripted track \{([^}]+)\}")
    rows = set()
    for path in paths:
        for line in path.open(errors="replace"):
            match = autoloop.search(line)
            if match:
                rows.add(
                    (
                        datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp(),
                        int(match.group(2)),
                        "autoloop",
                        int(match.group(3)),
                    )
                )
                continue
            match = scripted.search(line)
            if match:
                rows.add(
                    (
                        datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp(),
                        int(match.group(2)),
                        "scripted",
                        match.group(3).lower(),
                    )
                )
    return [
        {"timestamp": row[0], "deck": row[1], "mode": row[2], "selection": row[3]}
        for row in sorted(rows)
    ]


def parse_logged_bpms(path: Path) -> list[tuple[float, float]]:
    pattern = re.compile(r"(\d\d:\d\d:\d\d\.\d+).*\[BEAT\].*bpm=([0-9.]+)")
    rows = []
    for line in path.open(errors="replace"):
        match = pattern.search(ANSI.sub("", line))
        if match:
            rows.append((time_of_day(match.group(1)), float(match.group(2))))
    return rows


def dominant_note_indices(
    fires: list[tuple], app_events: list[dict], deck: int = 1, tolerance: float = 0.1
) -> dict[int, int]:
    counts: dict[int, Counter] = defaultdict(Counter)
    for fire_time, _kind, _role, _scene, note_text in fires:
        if not note_text or int(note_text) == 0:
            continue
        for event in app_events:
            if event["mode"] != "autoloop" or event["deck"] != deck:
                continue
            event_time = datetime.fromtimestamp(event["timestamp"])
            seconds = (
                event_time.hour * 3600
                + event_time.minute * 60
                + event_time.second
                + event_time.microsecond / 1e6
            )
            delta = seconds - fire_time
            if 0 <= delta <= tolerance:
                counts[int(note_text)][int(event["selection"])] += 1
    return {
        note: counter.most_common(1)[0][0]
        for note, counter in counts.items()
        if counter
    }


def changed_frames(frames: list[tuple]) -> list[tuple]:
    changed = []
    previous = None
    for timestamp, state in frames:
        if state != previous:
            changed.append((timestamp, state))
            previous = state
    return changed


def build_render_events(
    ssfile: Path,
    cue_records: dict[str, dict],
    initial_state: tuple[int, ...],
    initial_policy: str,
    control_channels: tuple[int, ...],
    owner_deck: int,
) -> tuple[list[dict], list[str]]:
    # PROVISIONAL one_based (preserves prior behavior); autoloop convention is
    # provenance-dependent and unproven by wire. See soundswitch_ssfile_format.md.
    parsed = parse_autoloop_structure(ssfile.read_bytes(), "one_based")
    first_pass = render_timeline(
        parsed,
        cue_records,
        time_key="time",
        initial_state=initial_state,
        initial_state_policy=initial_policy,
        control_channels=control_channels,
        owner_deck=owner_deck,
    )
    # A second zero-initialized pass uses the prior cycle's final rendered state
    # as explicit inherited state. This is a steady-loop hypothesis, not wire input.
    if initial_policy == "all_zero_static_render" and first_pass:
        inherited = tuple(first_pass[-1]["state"]["rendered_state"])
        rows = render_timeline(
            parsed,
            cue_records,
            time_key="time",
            initial_state=inherited,
            initial_state_policy="steady_loop_from_project_bytes",
            control_channels=control_channels,
            owner_deck=owner_deck,
        )
    else:
        rows = first_pass
    errors = sorted(
        {
            row["source_decode_error"]
            for row in rows
            if row["source_decode_error"] is not None
        }
    )
    return [row for row in rows if row["time"] >= 0], errors


def fit_phase(
    frames: list[tuple[float, tuple[int, ...]]],
    start: float,
    bpm: float,
    events: list[dict],
    other_deck_events: list[dict],
) -> dict:
    events = sorted(events, key=lambda row: (row["time"] % LOOP_TICKS, row["sequence"]))
    rate = bpm * 10.0
    changes = changed_frames(frames)
    event_times = [row["time"] % LOOP_TICKS for row in events]
    event_states = [tuple(row["state"]["rendered_state"]) for row in events]

    def predicted_at(phase: float) -> tuple[int, ...] | None:
        if not event_times:
            return None
        index = bisect.bisect_right(event_times, phase) - 1
        if index < 0:
            index = len(event_times) - 1
        return event_states[index]

    candidates = {0}
    for timestamp, wire_state in changes:
        elapsed = timestamp - start
        for event, expected in zip(events, event_states):
            if expected == wire_state:
                center = int(round((event["time"] - rate * elapsed) % LOOP_TICKS))
                candidates.add((center - 1) % LOOP_TICKS)
                candidates.add(center % LOOP_TICKS)
                candidates.add((center + 1) % LOOP_TICKS)

    best = None
    for offset in candidates:
        exact = known = 0
        for timestamp, wire_state in frames:
            expected = predicted_at((offset + rate * (timestamp - start)) % LOOP_TICKS)
            if expected is None:
                continue
            known += 1
            exact += expected == wire_state
        score = (exact, known, -offset)
        if best is None or score > best[0]:
            best = (score, offset)
    if best is None:
        return {"phase_offset": None, "exact_frames": 0, "compared_frames": 0}

    exact, compared, _unused = best[0]
    offset = best[1]
    mismatch_channels: Counter[int] = Counter()
    mismatch_value_pairs: dict[int, Counter[tuple[int, int]]] = defaultdict(Counter)
    mismatches_near_other_deck = 0
    mismatch_frames = 0
    other_times = [event["timestamp"] for event in other_deck_events]
    for timestamp, wire_state in frames:
        expected = predicted_at((offset + rate * (timestamp - start)) % LOOP_TICKS)
        if expected is None or expected == wire_state:
            continue
        mismatch_frames += 1
        mismatch_channels.update(
            channel
            for channel, (expected_value, actual_value) in enumerate(
                zip(expected, wire_state), start=1
            )
            if expected_value != actual_value
        )
        for channel, (expected_value, actual_value) in enumerate(
            zip(expected, wire_state), start=1
        ):
            if expected_value != actual_value:
                mismatch_value_pairs[channel][(expected_value, actual_value)] += 1
        if any(abs(timestamp - other_time) <= 0.4 for other_time in other_times):
            mismatches_near_other_deck += 1

    transition_residuals = []
    if events:
        segment_end = frames[-1][0]
        for event in events:
            event_phase = event["time"] % LOOP_TICKS
            cycle = math.floor((offset + rate * (frames[0][0] - start) - event_phase) / LOOP_TICKS)
            for cycle_number in range(cycle - 1, cycle + 4):
                expected_time = start + (
                    event_phase + cycle_number * LOOP_TICKS - offset
                ) / rate
                if not frames[0][0] <= expected_time <= segment_end:
                    continue
                expected_state = tuple(event["state"]["rendered_state"])
                matches = [
                    timestamp - expected_time
                    for timestamp, wire_state in changes
                    if wire_state == expected_state and abs(timestamp - expected_time) <= 0.1
                ]
                if matches:
                    transition_residuals.append(min(matches, key=abs) * 1000.0)

    return {
        "phase_offset": offset,
        "exact_frames": exact,
        "compared_frames": compared,
        "exact_frame_ratio": exact / compared if compared else None,
        "mismatch_frames": mismatch_frames,
        "mismatch_channels": {
            str(channel): count for channel, count in sorted(mismatch_channels.items())
        },
        "mismatch_value_pairs": {
            str(channel): [
                {"expected": pair[0], "actual": pair[1], "count": count}
                for pair, count in counter.most_common()
            ]
            for channel, counter in sorted(mismatch_value_pairs.items())
        },
        "mismatches_near_other_deck_change": mismatches_near_other_deck,
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
        "matched_transition_count": len(transition_residuals),
    }


def _default_ticks_per_beat() -> list[int]:
    """Broad rational candidate set: cycle / (integer beats-per-cycle) plus
    common animation rates. 600 is always included but never assumed."""
    candidates = {480, 600, 720}
    for beats in range(8, 129):
        if LOOP_TICKS % beats == 0:
            candidates.add(LOOP_TICKS // beats)
    return sorted(candidates)


def load_phase_trace(path: Path) -> list[dict]:
    rows = []
    for line in path.open(errors="replace"):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("kind") == "autoloop_phase":
            rows.append(row)
    rows.sort(key=lambda r: r.get("mono_ns", 0))
    return rows


PHASE_FOOTER_KIND = "phase_trace_footer"


def load_phase_trace_footer(path: Path) -> dict | None:
    """Return the last ``phase_trace_footer`` integrity record in the trace, or None."""
    footer = None
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("kind") == PHASE_FOOTER_KIND:
                footer = row
    return footer


def evaluate_phase_trace_integrity(footer: dict | None) -> tuple[bool, str]:
    """Pure, fail-closed integrity check for one B1 phase-trace capture.

    A missing footer, an unclean tracer close, or any nonzero dropped/undrained
    count invalidates the ENTIRE capture run. There are no timestamped drop
    ranges, so per-segment salvage is impossible (possible future work if drop
    timestamps are ever added). Returns ``(ok, reason)``.
    """
    if footer is None:
        return (False, "missing phase_trace_footer (cannot prove zero dropped rows)")
    if not footer.get("close_ok", False):
        return (False, f"phase-trace close not clean: {footer}")
    dropped = int(footer.get("dropped", 0) or 0)
    undrained = int(footer.get("undrained", 0) or 0)
    if dropped or undrained:
        return (
            False,
            f"phase-trace lost rows (dropped={dropped}, undrained={undrained}); "
            "whole capture invalid",
        )
    return (True, "ok")


def _beat_at_epoch(phase_rows: list[dict], epoch_s: float, clock_offset_s: float) -> float | None:
    if not phase_rows:
        return None
    target_ns = (epoch_s + clock_offset_s) * 1e9
    best = min(phase_rows, key=lambda r: abs(r.get("epoch_ns", 0) - target_ns))
    return best.get("abs_beat_pos")


def _origin_hypotheses(phase_rows: list[dict]) -> list[dict]:
    """Enumerate phase-origin candidates strictly from recorded state.

    No free fitted offset is ever introduced: every origin is a value the bridge
    actually recorded (arm-sync target, MIDI/refire origin, phrase anchor,
    accepted-selection beat) plus the continuous previous-phase (global 0).
    """
    origins: list[dict] = [{"beat": 0.0, "kind": "continuous_global"}]
    seen = {0.0}

    def add(beat, kind):
        if beat is None:
            return
        try:
            beat = float(beat)
        except (TypeError, ValueError):
            return
        if beat in seen:
            return
        seen.add(beat)
        origins.append({"beat": beat, "kind": kind})

    for row in phase_rows:
        add(row.get("autoloop_arm_sync_beat"), "arm_sync")
        add(row.get("midi_refire_origin_beat"), "midi_refire")
        add(row.get("phrase_anchor_last_beat"), "phrase_anchor")
        add(row.get("last_autoloop_status_phrase_beat"), "status_phrase")
        if row.get("autoloop_tick_just_fired"):
            add(row.get("abs_beat_pos"), "accepted_selection")
    return origins


def run_t7d(args) -> None:
    """Falsifiable T7d phase-contract fit over one captured scenario segment.

    Inputs are one immutable pack ssfile, the schema-2 phase trace (beat
    authority), the passive Universe-0 pcap (observed wire frames), and the
    venue cue library. The contract decision itself is delegated to the
    unit-tested pure oracle in ``t7d_phase_contract``. This path is exercised
    only against real captures; the alignment seam (clock offset, segment
    window) is part of the B5 derivation and must be confirmed on real data --
    it is NOT validated here and does not upgrade repo hardware status.
    """
    from t7d_phase_contract import LOOP_TICKS as ORACLE_CYCLE  # noqa: F401
    from t7d_phase_contract import QUANTIZERS, fit_phase_contract

    frames = universe_frames(args.pcap)
    if not frames:
        raise SystemExit("no Universe-0 ArtDmx frames")
    phase_rows = load_phase_trace(args.phase_trace)
    if not phase_rows:
        raise SystemExit("no schema-2 autoloop_phase rows in trace")
    # Fail closed on capture integrity: any dropped/undrained row or unclean
    # tracer close invalidates the entire run (no timestamped drop ranges).
    integrity_ok, integrity_reason = evaluate_phase_trace_integrity(
        load_phase_trace_footer(args.phase_trace)
    )
    if not integrity_ok:
        raise SystemExit(f"INCOMPLETE_T7D_EVIDENCE: {integrity_reason}")

    control_channels = tuple(
        sorted({int(v) for v in args.control_channels.split(",") if v.strip()})
    )
    cue_records = venue_cue_records(parse_venue_cues(args.venue.read_bytes()), args.fixture_group)
    render_events, errors = build_render_events(
        args.t7d_ssfile, cue_records, (0,) * 19, "all_zero_static_render",
        control_channels, args.owner_deck,
    )
    if errors:
        raise SystemExit(f"source decode errors: {errors}")
    events = [
        {"tick": int(ev["time"]) % LOOP_TICKS, "state": tuple(ev["state"]["rendered_state"])}
        for ev in render_events
    ]
    if not events:
        raise SystemExit("empty immutable timeline")

    samples = []
    for epoch_s, state in frames:
        beat = _beat_at_epoch(phase_rows, epoch_s, args.clock_offset)
        if beat is None:
            continue
        samples.append({"t": epoch_s, "beat": beat, "state": state})

    tpbs = (
        [int(v) for v in args.ticks_per_beat.split(",") if v.strip()]
        if args.ticks_per_beat
        else _default_ticks_per_beat()
    )
    if 600 not in tpbs:
        tpbs.append(600)
    hypotheses = {
        "ticks_per_beat": sorted(set(tpbs)),
        "quantizers": list(QUANTIZERS),
        "origins": _origin_hypotheses(phase_rows),
        "cycle_ticks": LOOP_TICKS,
        "min_discriminating": args.min_discriminating,
        "min_frames": args.min_frames,
    }
    result = fit_phase_contract(samples, events, hypotheses)
    result["inputs"] = {
        "pcap": str(args.pcap),
        "pcap_sha256": hashlib.sha256(args.pcap.read_bytes()).hexdigest(),
        "phase_trace": str(args.phase_trace),
        "phase_rows": len(phase_rows),
        "ssfile": args.t7d_ssfile.name,
        "frames": len(frames),
        "aligned_samples": len(samples),
        "owner_deck": args.owner_deck,
        "clock_offset_s": args.clock_offset,
    }
    result["hardware_status"] = "SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED"
    print(json.dumps(result, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    parser.add_argument("bridge_log", nargs="?", type=Path)
    parser.add_argument("app_logs", nargs="*", type=Path)
    parser.add_argument("--proj", type=Path)
    parser.add_argument("--venue", required=True, type=Path)
    parser.add_argument("--fixture-group", default="0x493")
    parser.add_argument("--control-channels", default="11")
    parser.add_argument("--owner-deck", type=int, default=1)
    # Falsifiable T7d phase-contract mode (consumes the schema-2 phase trace):
    parser.add_argument("--t7d", action="store_true", help="run the falsifiable T7d phase-contract fit")
    parser.add_argument("--phase-trace", type=Path, help="schema-2 autoloop_phase JSONL")
    parser.add_argument("--t7d-ssfile", type=Path, help="one immutable pack ssfile for this segment")
    parser.add_argument("--ticks-per-beat", default="", help="comma list; default = broad rational search")
    parser.add_argument("--clock-offset", type=float, default=0.0, help="measured dual-timestamp clock residual (s)")
    parser.add_argument("--min-discriminating", type=int, default=4)
    parser.add_argument("--min-frames", type=int, default=20)
    args = parser.parse_args()

    if args.t7d:
        missing = [n for n in ("phase_trace", "t7d_ssfile") if getattr(args, n) is None]
        if missing:
            raise SystemExit(f"--t7d requires: {', '.join('--' + m.replace('_', '-') for m in missing)}")
        run_t7d(args)
        return
    if args.bridge_log is None or not args.app_logs or args.proj is None:
        raise SystemExit("legacy mode requires: bridge_log app_logs... --proj --venue")

    control_channels = tuple(
        sorted({int(value) for value in args.control_channels.split(",") if value.strip()})
    )
    frames = universe_frames(args.pcap)
    if not frames:
        raise SystemExit("no Universe-0 ArtDmx frames")
    midnight = datetime.fromtimestamp(frames[0][0]).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    fires = parse_bridge(args.bridge_log)
    app_events = parse_app_logs(args.app_logs)
    bpms = parse_logged_bpms(args.bridge_log)
    note_map = dominant_note_indices(fires, app_events, deck=args.owner_deck)
    venue_bytes = args.venue.read_bytes()
    cue_records = venue_cue_records(parse_venue_cues(venue_bytes), args.fixture_group)

    epoch_fires = [
        (midnight + row[0], *row[1:])
        for row in fires
        if frames[0][0] <= midnight + row[0] <= frames[-1][0]
    ]
    segments = []
    for position, (fire_epoch, _kind, role, scene, note_text) in enumerate(epoch_fires):
        if not note_text or int(note_text) == 0:
            continue
        note = int(note_text)
        app_index = note_map.get(note)
        if app_index is None:
            continue
        next_fire = epoch_fires[position + 1][0] if position + 1 < len(epoch_fires) else frames[-1][0]
        end = min(next_fire, frames[-1][0])
        selected = [row for row in frames if fire_epoch + 0.15 <= row[0] < end - 0.08]
        if len(selected) < 20:
            continue
        seconds_of_day = fire_epoch - midnight
        bpm = min(bpms, key=lambda row: abs(row[0] - seconds_of_day))[1] if bpms else None
        if bpm is None:
            continue
        ssfile = args.proj / f"SSAutoLoop{app_index + 1}.ssfile"
        other_deck_events = [
            event
            for event in app_events
            if event["deck"] != args.owner_deck
            and selected[0][0] - 0.4 <= event["timestamp"] <= selected[-1][0] + 0.4
        ]

        static_events, static_errors = build_render_events(
            ssfile,
            cue_records,
            (0,) * 19,
            "all_zero_static_render",
            control_channels,
            args.owner_deck,
        )
        transition_events, transition_errors = build_render_events(
            ssfile,
            cue_records,
            selected[0][1],
            "first_selected_wire_frame_transition_only",
            control_channels,
            args.owner_deck,
        )
        static_fit = fit_phase(selected, fire_epoch, bpm, static_events, other_deck_events)
        transition_fit = fit_phase(selected, fire_epoch, bpm, transition_events, other_deck_events)
        if static_errors or transition_errors:
            classification = "source_decode_error"
        elif static_fit.get("exact_frame_ratio") == 1.0:
            classification = "byte_exact_static_render"
        elif (
            static_fit.get("mismatch_frames", 0)
            and static_fit.get("mismatches_near_other_deck_change", 0)
            == static_fit.get("mismatch_frames", 0)
        ):
            classification = "possible_other_deck_ownership_change"
        else:
            classification = "unresolved_layer_or_field"
        segments.append(
            {
                "note": note,
                "scene": scene,
                "role": role,
                "app_log_index": app_index,
                "ssfile": ssfile.name,
                "start": datetime.fromtimestamp(fire_epoch).isoformat(timespec="milliseconds"),
                "duration_seconds": round(end - fire_epoch, 3),
                "bpm": bpm,
                "frames": len(selected),
                "expected_owner_deck": args.owner_deck,
                "owner_confidence": "bridge-correlation-only; output ownership unresolved",
                "other_deck_changes": other_deck_events,
                "control_channels_hypothesis": list(control_channels),
                "source_decode_errors": sorted(set(static_errors + transition_errors)),
                "static_zero_initial_fit": static_fit,
                "transition_only_wire_initial_fit": transition_fit,
                "classification": classification,
            }
        )

    source_files = []
    for filename in sorted({segment["ssfile"] for segment in segments}):
        path = args.proj / filename
        data = path.read_bytes()
        parsed = parse_autoloop_structure(data, "one_based")  # PROVISIONAL; see ssfile_format doc
        source_files.append(
            {
                "path": str(path),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "version": parsed["version"],
                "event_count_offset": parsed["event_count_offset"],
                "event_count": parsed["event_count"],
                "shared_block_offset": parsed["shared_block_offset"],
                "cue_count_offset": parsed["cue_count_offset"],
                "cue_count": parsed["cue_count"],
                "timeline_count_offset": parsed["timeline_count_offset"],
                "timeline_count": parsed["timeline_count"],
                "trailer_offset": parsed["trailer_offset"],
            }
        )
    pcap_bytes = args.pcap.read_bytes()
    print(
        json.dumps(
            {
                "status": "partial",
                "pcap": str(args.pcap),
                "pcap_size": len(pcap_bytes),
                "pcap_sha256": hashlib.sha256(pcap_bytes).hexdigest(),
                "pcap_version": "classic-pcap",
                "frame_count": len(frames),
                "capture_duration_seconds": frames[-1][0] - frames[0][0],
                "venue": str(args.venue),
                "venue_size": len(venue_bytes),
                "venue_sha256": hashlib.sha256(venue_bytes).hexdigest(),
                "venue_version": int.from_bytes(venue_bytes[4:8], "little"),
                "venue_cue_count": len(cue_records),
                "fixture_group": args.fixture_group,
                "note_map": note_map,
                "owner_model": {
                    "expected_owner_deck": args.owner_deck,
                    "confidence": "provisional",
                    "known_limit": "AppLog tracks per-deck selections but does not identify Universe-0 owner",
                },
                "source_files": source_files,
                "unsupported_reason": (
                    "control/effect fields and Universe-0 deck ownership remain unresolved; "
                    "transition-only wire-initial fits are not static render proof"
                ),
                "segments": segments,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
