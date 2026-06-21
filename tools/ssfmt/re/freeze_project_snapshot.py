#!/usr/bin/env python3
"""Freeze one stable SoundSwitch project snapshot outside the live project.

The destination must be new and must not be inside ``~/Music/SoundSwitch``.
Files are copied from the same stable-read inventory used by the mutation
comparator, then made read-only.  The manifest is emitted to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from compare_project_snapshots import SnapshotError, _sha256, _snapshot


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def freeze(source: Path, destination: Path) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    soundswitch_root = (Path.home() / "Music" / "SoundSwitch").resolve()
    if destination.exists():
        raise SnapshotError(f"destination already exists: {destination}")
    if _is_relative_to(destination, source) or _is_relative_to(destination, soundswitch_root):
        raise SnapshotError(
            "destination must be outside the source project and ~/Music/SoundSwitch"
        )

    inventory, blobs = _snapshot(source)
    destination.mkdir(parents=True)
    written = []
    for row in inventory["files"]:
        relative_path = row["relative_path"]
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(blobs[relative_path])
            handle.flush()
            os.fsync(handle.fileno())
        target.chmod(0o444)
        copied = target.read_bytes()
        if len(copied) != row["size"] or _sha256(copied) != row["sha256"]:
            raise SnapshotError(f"frozen copy verification failed: {relative_path}")
        written.append(relative_path)

    for directory in sorted(
        (path for path in destination.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    destination.chmod(0o555)
    return {
        "schema_version": 1,
        "status": "frozen_and_verified",
        "source_project": str(source),
        "destination_project": str(destination),
        "file_count": len(written),
        "inventory": inventory["files"],
        "scope_limit": "read-only research snapshot; no SoundSwitch source file was modified",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_project", type=Path)
    parser.add_argument("destination_project", type=Path)
    args = parser.parse_args()
    try:
        report = freeze(args.source_project, args.destination_project)
    except (SnapshotError, OSError) as error:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "failed_closed",
                    "error": f"{type(error).__name__}: {error}",
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2) from error
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
