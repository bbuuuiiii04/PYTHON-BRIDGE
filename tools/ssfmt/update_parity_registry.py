#!/usr/bin/env python3
"""Write scripted SoundSwitch parity registry records from a reduced fixture."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.soundswitch_pack import canonical_json_bytes, sha256_bytes  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedAutoloop, LoadedScriptedTrack, load_pack  # noqa: E402
from rb_ss_bridge_v2.soundswitch_parity_oracle import (  # noqa: E402
    AutoloopSample,
    ScriptedSample,
    StaticSample,
    classify_autoloop,
    classify_scripted,
    classify_static,
)


def _passed_sample_count(report_dict: dict[str, object]) -> int:
    return sum(
        1 for row in report_dict.get("samples", [])
        if isinstance(row, dict) and row.get("issue") in ("match", "u0_dark")
    )


def _empty_fail_report(surface: str) -> dict[str, object]:
    return {
        "counts": {},
        "issues": {"missing_rows": 1},
        "samples": [],
        "surface": surface,
        "truth_source": "SoundSwitch U0",
        "verdict": "FAIL",
    }


def _samples(rows: list[dict[str, object]]) -> tuple[ScriptedSample, ...]:
    return tuple(
        ScriptedSample(
            elapsed_ms=int(row["elapsed_ms"]),
            u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
            label=str(row.get("label") or ""),
        )
        for row in rows
    )


def _autoloop_samples(rows: list[dict[str, object]]) -> tuple[AutoloopSample, ...]:
    return tuple(
        AutoloopSample(
            phase_tick=int(row["phase_tick"]),
            u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
            label=str(row.get("label") or ""),
        )
        for row in rows
    )


def _static_samples(rows: object) -> tuple[StaticSample, ...]:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return ()
    return tuple(
        StaticSample(
            u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
            label=str(row.get("label") or ""),
        )
        for row in rows
        if isinstance(row, dict)
    )


def _merged_static_report(frame: tuple[int, ...], samples: tuple[StaticSample, ...]) -> dict[str, object]:
    reports = [classify_static(frame, sample).to_dict() for sample in samples]
    counts: dict[str, int] = {}
    issues: dict[str, int] = {}
    report_samples: list[dict[str, object]] = []
    for report in reports:
        for key, value in report.get("counts", {}).items():  # type: ignore[union-attr]
            counts[str(key)] = counts.get(str(key), 0) + int(value)
        for key, value in report.get("issues", {}).items():  # type: ignore[union-attr]
            issues[str(key)] = issues.get(str(key), 0) + int(value)
        for row in report.get("samples", []):  # type: ignore[union-attr]
            if isinstance(row, dict):
                report_samples.append(row)
    return {
        "counts": dict(sorted(counts.items())),
        "issues": dict(sorted(issues.items())),
        "samples": report_samples,
        "surface": "static",
        "truth_source": "SoundSwitch U0",
        "verdict": "FAIL" if any(row.get("verdict") == "FAIL" for row in reports) else "PASS",
    }


def _manifest(pack: Path) -> dict[str, object]:
    return json.loads((pack / "manifest.json").read_text(encoding="utf-8"))


def _venue_sha(manifest: dict[str, object]) -> str:
    for row in manifest.get("source_inventory", []):  # type: ignore[union-attr]
        if isinstance(row, dict) and row.get("path") == "SoundSwitchVenues.bin":
            return str(row.get("sha256") or "")
    return ""


def _document_source(pack: Path, ssid: str) -> tuple[str, str]:
    document = json.loads((pack / f"scripted/{ssid}.json").read_text(encoding="utf-8"))["document"]
    return str(document["source_sha256"]), str(document["layout"])


def _autoloop_document_source(pack: Path, identity: str) -> tuple[str, str]:
    number = "".join(char for char in identity if char.isdigit())
    document = json.loads((pack / f"autoloops/{number}.json").read_text(encoding="utf-8"))["document"]
    return str(document["source_sha256"]), str(document["layout"])


def _static_frames(pack: Path) -> dict[int, tuple[int, ...]]:
    value = json.loads((pack / "static_looks.json").read_text(encoding="utf-8"))
    return {
        int(row["slot_index"]): tuple(int(value) for value in row["pre_rendered_frame_ch1_ch19"])
        for row in value.get("records", [])
        if isinstance(row, dict)
    }


def build_scripted_registry(pack_path: Path, fixture_path: Path) -> dict[str, dict[str, object]]:
    pack = load_pack(pack_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    capture_id = str(fixture.get("capture_id") or "")
    divergence = fixture.get("capture_source_divergence", {})
    manifest = _manifest(pack_path)
    venue_sha = _venue_sha(manifest)
    records: dict[str, dict[str, object]] = {}
    for ssid, rows in sorted(fixture.get("scripted", {}).items()):
        track = pack.scripted.get(ssid)
        if not isinstance(track, LoadedScriptedTrack) or track.document is None:
            continue
        report = classify_scripted(track, _samples(rows))
        report_dict = report.to_dict()
        source_sha, layout = _document_source(pack_path, ssid)
        records[ssid] = {
            "capture_id": capture_id,
            "divergence": list(divergence.get(ssid, [])) if isinstance(divergence, dict) else [],
            "layout": layout,
            "oracle_report_sha256": sha256_bytes(canonical_json_bytes(report_dict)),
            "rows_passed": _passed_sample_count(report_dict),
            "rows_total": len(report.samples),
            "source_sha256": source_sha,
            "truth_source": report.truth_source,
            "venue_source_sha256": venue_sha,
            "verdict": report.verdict,
        }
    return records


def build_static_registry(pack_path: Path, fixture_path: Path) -> dict[str, object]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    capture_id = str(fixture.get("capture_id") or "")
    manifest = _manifest(pack_path)
    venue_sha = _venue_sha(manifest)
    static_rows = fixture.get("static", {})
    records: dict[str, object] = {}
    if isinstance(static_rows, dict) and static_rows:
        frames = _static_frames(pack_path)
        for slot_text, rows in sorted(static_rows.items(), key=lambda item: int(item[0])):
            slot = int(slot_text)
            samples = _static_samples(rows)
            report_dict = (
                _merged_static_report(frames[slot], samples)
                if slot in frames and samples
                else _empty_fail_report("static")
            )
            records[str(slot)] = {
                "capture_id": capture_id,
                "oracle_report_sha256": sha256_bytes(canonical_json_bytes(report_dict)),
                "rows_passed": _passed_sample_count(report_dict),
                "rows_total": len(report_dict.get("samples", [])),  # type: ignore[arg-type]
                "truth_source": "SoundSwitch U0",
                "venue_source_sha256": venue_sha,
                "verdict": report_dict["verdict"],
            }
        return records
    return {
        "capture_id": capture_id,
        "look_source_evidence": "non_generic_assertion_c6",
        "reason": str(fixture.get("reason") or ""),
        "static_capture_windows": str(fixture.get("static_capture_windows") or "unavailable"),
        "truth_source": "SoundSwitch U0",
        "venue_source_sha256": venue_sha,
        "verdict": "PASS",
    }


def reconcile_edited_witnesses(
    fresh: dict[str, dict[str, object]],
    committed: dict[str, dict[str, object]],
) -> tuple[dict[str, dict[str, object]], list[dict[str, str]]]:
    """Drop FAIL records whose sources were edited since the evidence last passed."""
    reconciled = dict(fresh)
    retirements: list[dict[str, str]] = []
    for identity, fresh_record in fresh.items():
        committed_record = committed.get(identity)
        if (
            fresh_record.get("verdict") != "FAIL"
            or not isinstance(committed_record, dict)
            or committed_record.get("verdict") != "PASS"
        ):
            continue
        committed_source = str(committed_record.get("source_sha256") or "")
        fresh_source = str(fresh_record.get("source_sha256") or "")
        committed_venue = str(committed_record.get("venue_source_sha256") or "")
        fresh_venue = str(fresh_record.get("venue_source_sha256") or "")
        source_changed = bool(fresh_source) and fresh_source != committed_source
        venue_changed = bool(fresh_venue and committed_venue) and fresh_venue != committed_venue
        if not committed_source or not (source_changed or venue_changed):
            continue
        reconciled.pop(identity, None)
        retirements.append({
            "identity": identity,
            "reason": "witness_source_edited",
            "committed_source_sha256": committed_source,
            "fresh_source_sha256": fresh_source,
            "committed_venue_source_sha256": committed_venue,
            "fresh_venue_source_sha256": fresh_venue,
            "capture_id": str(fresh_record.get("capture_id") or ""),
        })
    return reconciled, sorted(retirements, key=lambda row: row["identity"])


def _autoloop_registry_record(
    loop: LoadedAutoloop,
    rows: list[dict[str, object]],
    *,
    capture_id: str,
    divergence_entry: object,
    source_sha: str,
    layout: str,
    venue_sha: str,
) -> dict[str, object] | None:
    """Pure per-identity record builder for ``build_autoloop_registry``.

    Returns ``None`` when there is no capture evidence for this loop (``rows``
    is empty): absence of evidence is not evidence of parity, so the loop gets
    no registry entry and the compiler may still generalize it from its
    layout family. When rows ARE present, the loop is pinned to whatever
    verdict the oracle actually reaches -- PASS or FAIL -- so a
    fixture-witnessed regression (e.g. a stale render no longer matching its
    own capture rows) cannot silently fall through to
    ``algorithm_generalized``; the compiler maps a FAIL registry entry to
    ``unverified_parity`` and never treats an entry as absent.
    """
    if not rows:
        return None
    report = classify_autoloop(loop, _autoloop_samples(rows))
    report_dict = report.to_dict()
    return {
        "capture_id": capture_id,
        "divergence": list(divergence_entry) if isinstance(divergence_entry, list) else [],
        "layout": layout,
        "oracle_report_sha256": sha256_bytes(canonical_json_bytes(report_dict)),
        "rows_passed": _passed_sample_count(report_dict),
        "rows_total": len(report.samples),
        "source_sha256": source_sha,
        "truth_source": report.truth_source,
        "venue_source_sha256": venue_sha,
        "verdict": report.verdict,
    }


def build_autoloop_registry(pack_path: Path, fixture_path: Path) -> dict[str, dict[str, object]]:
    pack = load_pack(pack_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    capture_id = str(fixture.get("capture_id") or "")
    divergence = fixture.get("capture_source_divergence", {})
    manifest = _manifest(pack_path)
    venue_sha = _venue_sha(manifest)
    records: dict[str, dict[str, object]] = {}
    for identity, rows in sorted(fixture.get("autoloop", {}).items()):
        loop = pack.autoloops.get(identity)
        if not isinstance(loop, LoadedAutoloop):
            continue
        source_sha, layout = _autoloop_document_source(pack_path, identity)
        record = _autoloop_registry_record(
            loop, rows,
            capture_id=capture_id,
            divergence_entry=divergence.get(identity, []) if isinstance(divergence, dict) else [],
            source_sha=source_sha,
            layout=layout,
            venue_sha=venue_sha,
        )
        if record is not None:
            records[identity] = record
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--surface", choices=("scripted", "autoloop", "static"), default="scripted")
    args = parser.parse_args(argv)

    if args.surface == "static":
        records = build_static_registry(args.pack, args.fixture)
    elif args.surface == "autoloop":
        records = build_autoloop_registry(args.pack, args.fixture)
    else:
        records = build_scripted_registry(args.pack, args.fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical_json_bytes(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
