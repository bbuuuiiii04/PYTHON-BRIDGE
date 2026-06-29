"""CLI for the offline SoundSwitch Autoloop equivalence oracle."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .active_look import ActiveLookResolver, build_note_to_autoloop
from .content import MATCHED_SOURCE, load_autoloops, verify_against_capture
from .diff import Best, ScoreResult, search
from .groundtruth import load_groundtruth
from .phase_track import beat_at, load_phase_samples

STATUS = "SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED"
REPORT_MD = "autoloop_oracle_report.md"
REPORT_JSON = "autoloop_oracle_report.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_pack() -> Path:
    return _repo_root() / "local" / "soundswitch" / "rbss_canonical_pack"


def _capture_file(capture: Path, *names: str) -> Path:
    for name in names:
        path = capture / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"{capture} has none of: {', '.join(names)}")


def _grid(start: float, stop: float, step: float) -> list[float]:
    count = round((stop - start) / step)
    return [round(start + index * step, 6) for index in range(count + 1)]


def _fine_grid(center: float, radius: float, step: float, low: float, high: float) -> list[float]:
    return [
        value
        for value in _grid(center - radius, center + radius, step)
        if low <= value <= high
    ]


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f}"


def _score_to_dict(score: ScoreResult) -> dict:
    return {
        "total_frames": score.total_frames,
        "scored_frames": score.scored_frames,
        "exact_match_frames": score.exact_match_frames,
        "exact_match_rate": score.exact_match_rate,
        "excluded_counts": score.excluded_counts,
        "per_channel_mismatches": score.per_channel_mismatches,
        "per_look": {
            look: {
                "scored": row.scored,
                "exact": row.exact,
                "exact_rate": row.exact_rate,
            }
            for look, row in score.per_look.items()
        },
        "worst_samples": [asdict(row) for row in score.worst_samples],
    }


def _verdict(content_status: str, scored: int, exact_rate: float | None) -> str:
    if content_status != MATCHED_SOURCE:
        return content_status
    if scored == 0:
        return "NO_GROUNDTRUTH"
    if exact_rate == 1.0:
        return "EQUIVALENT"
    return "MISMATCH(residual)"


def _per_look_rows(
    note_to_autoloop: dict[int, str],
    content_statuses: dict[str, str],
    best: Best,
) -> list[dict]:
    rows = []
    for note, look in sorted(note_to_autoloop.items()):
        score_row = best.score.per_look.get(look)
        scored = score_row.scored if score_row else 0
        exact = score_row.exact if score_row else 0
        exact_rate = score_row.exact_rate if score_row else None
        content_status = content_statuses.get(look, "MISSING")
        rows.append({
            "note": note,
            "look": look,
            "content_status": content_status,
            "scored_frames": scored,
            "exact_match_frames": exact,
            "exact_match_rate": exact_rate,
            "verdict": _verdict(content_status, scored, exact_rate),
        })
    return rows


def _write_report(capture: Path, report: dict) -> None:
    rows = report["per_look"]
    lines = [
        "# SoundSwitch Autoloop Equivalence Oracle",
        "",
        f"Status: {STATUS}",
        "",
        f"Capture: `{report['capture_dir']}`",
        f"Pack: `{report['pack']}`",
        f"Tolerance: {report['tol']}",
        "",
        "## Best Alignment",
        "",
        f"- latency_s: {report['best']['latency_s']:.6f}",
        f"- phase_offset_beats: {report['best']['phase_offset_beats']:.6f}",
        f"- note: {report['best']['note']}",
        f"- overall exact-match rate: {_rate(report['score']['exact_match_rate'])}",
        f"- scored frames: {report['score']['scored_frames']} / {report['score']['total_frames']}",
        "",
        "## Exclusions",
        "",
    ]
    if report["score"]["excluded_counts"]:
        for reason, count in sorted(report["score"]["excluded_counts"].items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none: 0")
    lines.extend([
        "",
        "## Per-Look Verdicts",
        "",
        "| note | look | content | scored | exact | exact rate | verdict |",
        "|---:|---|---|---:|---:|---:|---|",
    ])
    for row in rows:
        lines.append(
            f"| {row['note']} | {row['look']} | {row['content_status']} | "
            f"{row['scored_frames']} | {row['exact_match_frames']} | "
            f"{_rate(row['exact_match_rate'])} | {row['verdict']} |"
        )
    never_seen = [row for row in rows if row["verdict"] == "NO_GROUNDTRUTH"]
    lines.extend(["", "## Looks Never Seen On Wire", ""])
    if never_seen:
        for row in never_seen:
            lines.append(f"- note {row['note']} / {row['look']}")
    else:
        lines.append("- none")
    lines.extend(["", "## Worst Mismatch Samples", ""])
    if report["score"]["worst_samples"]:
        for row in report["score"]["worst_samples"]:
            lines.append(
                f"- t={row['timestamp']:.6f} look={row['look']} "
                f"mismatch_channels={row['mismatch_count']} max_abs_error={row['max_abs_error']}"
            )
    else:
        lines.append("- none")
    lines.append("")
    (capture / REPORT_MD).write_text("\n".join(lines), encoding="utf-8")
    (capture / REPORT_JSON).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_capture(capture_dir: str | Path, *, pack: str | Path, tol: int) -> dict:
    capture = Path(capture_dir).expanduser()
    pcap = _capture_file(capture, "artnet_classic.pcap", "artnet.pcap")
    session = _capture_file(capture, "session.jsonl")
    bridge_log = _capture_file(capture, "logs/bridge.log", "bridge.log")
    project_hashes = _capture_file(capture, "project.before.sha256")

    frames = load_groundtruth(pcap)
    samples = load_phase_samples(session)
    loops = load_autoloops(pack)
    content_statuses = verify_against_capture(loops, project_hashes)
    matched_loops = {
        identity: loop
        for identity, loop in loops.items()
        if content_statuses.get(identity) == MATCHED_SOURCE
    }
    note_to_autoloop = build_note_to_autoloop(pack)
    resolver = ActiveLookResolver.from_phase_and_log(samples, note_to_autoloop, bridge_log)
    beat_fn = lambda t: beat_at(samples, t)

    coarse = search(
        frames,
        beat_fn,
        resolver,
        matched_loops,
        latency_grid=_grid(-0.25, 0.25, 0.05),
        phase_grid=_grid(0.0, 32.0, 0.5),
        tol=tol,
        look_statuses=content_statuses,
    )
    best = search(
        frames,
        beat_fn,
        resolver,
        matched_loops,
        latency_grid=_fine_grid(coarse.latency_s, 0.05, 0.01, -0.25, 0.25),
        phase_grid=_fine_grid(coarse.phase_offset_beats, 0.5, 0.05, 0.0, 32.0),
        tol=tol,
        look_statuses=content_statuses,
    )

    report = {
        "status": STATUS,
        "capture_dir": str(capture),
        "pack": str(Path(pack).expanduser()),
        "pcap": str(pcap),
        "session": str(session),
        "project_before_sha256": str(project_hashes),
        "tol": tol,
        "search_grid": {
            "coarse": {
                "latency_s": {"min": -0.25, "max": 0.25, "step": 0.05},
                "phase_offset_beats": {"min": 0.0, "max": 32.0, "step": 0.5},
            },
            "fine": {
                "latency_s": {"center": coarse.latency_s, "radius": 0.05, "step": 0.01},
                "phase_offset_beats": {
                    "center": coarse.phase_offset_beats,
                    "radius": 0.5,
                    "step": 0.05,
                },
            },
        },
        "best": {
            "latency_s": best.latency_s,
            "phase_offset_beats": best.phase_offset_beats,
            "note": best.note,
        },
        "score": _score_to_dict(best.score),
        "content_statuses": content_statuses,
        "per_look": _per_look_rows(note_to_autoloop, content_statuses, best),
    }
    _write_report(capture, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--pack", type=Path, default=_default_pack())
    parser.add_argument("--tol", type=int, default=0)
    args = parser.parse_args()
    report = run_capture(args.capture_dir, pack=args.pack, tol=args.tol)
    print(json.dumps({
        "capture_dir": report["capture_dir"],
        "report_md": str(Path(report["capture_dir"]) / REPORT_MD),
        "report_json": str(Path(report["capture_dir"]) / REPORT_JSON),
        "latency_s": report["best"]["latency_s"],
        "phase_offset_beats": report["best"]["phase_offset_beats"],
        "exact_match_rate": report["score"]["exact_match_rate"],
        "scored_frames": report["score"]["scored_frames"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
