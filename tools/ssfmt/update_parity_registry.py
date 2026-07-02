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
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedScriptedTrack, load_pack  # noqa: E402
from rb_ss_bridge_v2.soundswitch_parity_oracle import ScriptedSample, classify_scripted  # noqa: E402


def _samples(rows: list[dict[str, object]]) -> tuple[ScriptedSample, ...]:
    return tuple(
        ScriptedSample(
            elapsed_ms=int(row["elapsed_ms"]),
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
            "rows_passed": int(report.counts.get("MATCH", 0)) + int(report.counts.get("U0_DARK", 0)),
            "rows_total": len(report.samples),
            "source_sha256": source_sha,
            "truth_source": report.truth_source,
            "venue_source_sha256": venue_sha,
            "verdict": report.verdict,
        }
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    records = build_scripted_registry(args.pack, args.fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical_json_bytes(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
