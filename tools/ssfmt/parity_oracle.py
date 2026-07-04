#!/usr/bin/env python3
"""Run the offline SoundSwitch U0 parity oracle on reduced fixtures."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.soundswitch_pack_loader import load_pack  # noqa: E402
from rb_ss_bridge_v2.tools.ssfmt.soundswitch_parity_oracle import (  # noqa: E402
    AutoloopSample,
    ScriptedSample,
    StaticSample,
    classify_autoloop,
    classify_scripted,
    classify_static,
)


def _scripted_samples(rows: list[dict[str, object]]) -> list[ScriptedSample]:
    samples = []
    for row in rows:
        samples.append(ScriptedSample(
            elapsed_ms=int(row["elapsed_ms"]),
            u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
            label=str(row.get("label") or ""),
        ))
    return samples


def _autoloop_samples(rows: list[dict[str, object]]) -> list[AutoloopSample]:
    samples = []
    for row in rows:
        samples.append(AutoloopSample(
            phase_tick=int(row["phase_tick"]),
            u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
            label=str(row.get("label") or ""),
        ))
    return samples


def _static_samples(rows: object) -> list[StaticSample]:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    samples = []
    for row in rows:
        if isinstance(row, dict):
            samples.append(StaticSample(
                u0_frame=tuple(int(value) for value in row["u0_frame"]),  # type: ignore[index]
                label=str(row.get("label") or ""),
            ))
    return samples


def _static_frames(pack: Path) -> dict[int, tuple[int, ...]]:
    value = json.loads((pack / "static_looks.json").read_text(encoding="utf-8"))
    return {
        int(row["slot_index"]): tuple(int(value) for value in row["pre_rendered_frame_ch1_ch19"])
        for row in value.get("records", [])
        if isinstance(row, dict)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="local/soundswitch/rbss_canonical_pack")
    parser.add_argument("--fixture", required=True,
                        help="Reduced JSON fixture containing scripted and/or autoloop U0 rows.")
    args = parser.parse_args(argv)

    pack_path = Path(args.pack)
    pack = load_pack(pack_path)
    fixture = json.loads(Path(args.fixture).read_text())
    reports = []
    for ssid, rows in sorted(fixture.get("scripted", {}).items()):
        track = pack.scripted.get(ssid.lower())
        if track is None:
            reports.append({"ssid": ssid, "verdict": "FAIL", "reason": "missing_scripted_doc"})
            continue
        reports.append({"ssid": ssid, **classify_scripted(track, _scripted_samples(rows)).to_dict()})
    for identity, rows in sorted(fixture.get("autoloop", {}).items()):
        loop = pack.autoloops.get(identity)
        if loop is None:
            reports.append({"identity": identity, "verdict": "FAIL", "reason": "missing_autoloop_doc"})
            continue
        if not rows:
            reports.append({"identity": identity, "verdict": "SKIP", "reason": "no_promotable_u0_rows"})
            continue
        reports.append({"identity": identity, **classify_autoloop(loop, _autoloop_samples(rows)).to_dict()})
    static_rows = fixture.get("static", {})
    if isinstance(static_rows, dict) and static_rows:
        frames = _static_frames(pack_path)
        for slot_text, rows in sorted(static_rows.items(), key=lambda item: int(item[0])):
            slot = int(slot_text)
            frame = frames.get(slot)
            if frame is None:
                reports.append({"slot": slot, "verdict": "FAIL", "reason": "missing_static_look"})
                continue
            for sample in _static_samples(rows):
                reports.append({"slot": slot, **classify_static(frame, sample).to_dict()})
    print(json.dumps({"reports": reports}, indent=2, sort_keys=True))
    return 1 if any(row.get("verdict") == "FAIL" for row in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
