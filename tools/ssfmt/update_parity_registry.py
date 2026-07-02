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
    classify_autoloop,
    classify_scripted,
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


def build_autoloop_registry(pack_path: Path, fixture_path: Path) -> dict[str, dict[str, object]]:
    pack = load_pack(pack_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    capture_id = str(fixture.get("capture_id") or "")
    manifest = _manifest(pack_path)
    venue_sha = _venue_sha(manifest)
    records: dict[str, dict[str, object]] = {}
    for identity, rows in sorted(fixture.get("autoloop", {}).items()):
        loop = pack.autoloops.get(identity)
        if not isinstance(loop, LoadedAutoloop):
            continue
        source_sha, layout = _autoloop_document_source(pack_path, identity)
        if rows:
            report = classify_autoloop(loop, _autoloop_samples(rows))
            report_dict = report.to_dict()
            verdict = report.verdict
            truth_source = report.truth_source
            rows_passed = _passed_sample_count(report_dict)
            rows_total = len(report.samples)
        else:
            report_dict = _empty_fail_report("autoloop")
            verdict = "FAIL"
            truth_source = "SoundSwitch U0"
            rows_passed = 0
            rows_total = 0
        records[identity] = {
            "capture_id": capture_id,
            "divergence": [],
            "layout": layout,
            "oracle_report_sha256": sha256_bytes(canonical_json_bytes(report_dict)),
            "rows_passed": rows_passed,
            "rows_total": rows_total,
            "source_sha256": source_sha,
            "truth_source": truth_source,
            "venue_source_sha256": venue_sha,
            "verdict": verdict,
        }
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--surface", choices=("scripted", "autoloop"), default="scripted")
    args = parser.parse_args(argv)

    if args.surface == "autoloop":
        records = build_autoloop_registry(args.pack, args.fixture)
    else:
        records = build_scripted_registry(args.pack, args.fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical_json_bytes(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
