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
from rb_ss_bridge_v2.soundswitch_parity_oracle import (  # noqa: E402
    AutoloopSample,
    ScriptedSample,
    classify_autoloop,
    classify_scripted,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default="local/soundswitch/rbss_canonical_pack")
    parser.add_argument("--fixture", required=True,
                        help="Reduced JSON fixture containing scripted and/or autoloop U0 rows.")
    args = parser.parse_args(argv)

    pack = load_pack(args.pack)
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
        reports.append({"identity": identity, **classify_autoloop(loop, _autoloop_samples(rows)).to_dict()})
    print(json.dumps({"reports": reports}, indent=2, sort_keys=True))
    return 1 if any(row.get("verdict") == "FAIL" for row in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
