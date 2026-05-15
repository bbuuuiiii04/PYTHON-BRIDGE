#!/usr/bin/env python3
"""Run rb_ss_bridge_v2 with JSONL session recording enabled."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="JSONL capture path")
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="skip unchanged position snapshots by elapsed/play/track length",
    )
    args = parser.parse_args()

    package_dir = Path(__file__).resolve().parents[1]
    package_parent = package_dir.parent
    env = os.environ.copy()
    env["RBSS_RECORD_SESSION"] = str(Path(args.output).expanduser())
    env["RBSS_RECORD_DEDUP"] = "1" if args.dedup else "0"

    print(f"[REC] recording to {env['RBSS_RECORD_SESSION']}", file=sys.stderr)
    os.chdir(package_parent)
    os.execvpe(sys.executable, [sys.executable, "-m", "rb_ss_bridge_v2"], env)


if __name__ == "__main__":
    main()
