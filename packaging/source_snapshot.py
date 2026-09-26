"""Copy current Git-listed files, then verify the copy and unchanged source bytes.

Ignored local configs and analysis data are staged separately by make_stick.sh.
No Git index, commit, branch, or working-tree file is changed.
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def record(root, name):
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe source path: {name}")
    path = root / name
    if any(root.joinpath(*relative.parts[:i]).is_symlink()
           for i in range(1, len(relative.parts))):
        raise ValueError(f"source symlink is not supported: {name}")
    if path.is_symlink():
        target = os.readlink(path)
        if (Path(target).is_absolute() or not path.is_file()
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError(f"source symlink escapes the snapshot or is broken: {name}")
        return [name, "symlink", target]
    if not path.is_file():
        raise ValueError(f"source is not a regular file: {name}")
    return [name, stat.S_IMODE(path.stat().st_mode),
            hashlib.sha256(path.read_bytes()).hexdigest()]


def inventory(root):
    names = subprocess.check_output([
        "git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
        "--exclude-standard",
    ]).decode().split("\0")
    # A deleted tracked file is deliberately absent from the current snapshot.
    return [record(root, name) for name in sorted(set(names)) if name
            and ((root / name).exists() or (root / name).is_symlink())]


def verify(destination):
    manifest = (destination.parent / "source_manifest.json").read_bytes()
    rows = json.loads(manifest)
    if [record(destination, row[0]) for row in rows] != rows:
        raise ValueError("source snapshot changed; refusing to publish")
    return hashlib.sha256(manifest).hexdigest()


def create(source, destination):
    rows = inventory(source)
    destination.mkdir(parents=True, exist_ok=False)
    for name, _mode, _digest in rows:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target, follow_symlinks=False)
    (destination.parent / "source_manifest.json").write_text(json.dumps(rows))
    digest = verify(destination)
    if inventory(source) != rows:
        raise ValueError("source files changed while taking the snapshot; retry rebuild")
    return digest


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--verify":
            print(verify(Path(sys.argv[2]).resolve()))
        elif len(sys.argv) == 3:
            print(create(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
        else:
            raise ValueError("usage: source_snapshot.py SOURCE DEST | --verify DEST")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"make_stick: {exc}")
