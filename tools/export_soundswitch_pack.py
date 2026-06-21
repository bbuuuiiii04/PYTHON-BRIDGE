#!/usr/bin/env python3
"""Export the pinned saved SoundSwitch project into a canonical static pack."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.soundswitch_pack import compile_pack_artifacts  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_verifier import verify_pack  # noqa: E402
from rb_ss_bridge_v2.soundswitch_project_decoder import decode_project  # noqa: E402


def _generator_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("cannot determine generator git commit") from exc
    commit = result.stdout.strip().lower()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise RuntimeError("generator git commit is not a full SHA-1")
    return commit


def export_pack(project: str | os.PathLike[str], output: str | os.PathLike[str]) -> dict[str, object]:
    source = Path(project).expanduser()
    destination = Path(output).expanduser()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"output must be a new path: {destination}")
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("output parent must be an existing real directory")
    decoded = decode_project(source)
    artifacts = compile_pack_artifacts(decoded, generator_commit=_generator_commit())
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=parent))
    try:
        for relative, data in artifacts.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        result = verify_pack(staging, source_project=source)
        os.replace(staging, destination)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = export_pack(args.project, args.output)
    print(f"pack: {args.output.expanduser()}")
    print(f"manifest_sha256: {result['manifest_sha256']}")
    print(f"artifacts: {result['artifact_count']}")
    print("status: SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
