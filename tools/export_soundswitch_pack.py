#!/usr/bin/env python3
"""Export the pinned saved SoundSwitch project into a canonical static pack."""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.soundswitch_pack import compile_pack_artifacts  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_verifier import (  # noqa: E402
    SoundSwitchPackVerificationError, verify_pack,
)
from rb_ss_bridge_v2.soundswitch_project_decoder import (  # noqa: E402
    SoundSwitchDecodeError, decode_project,
)


CANONICAL_SOURCE_PROJECT = Path("~/Music/SoundSwitch/default.ssproj").expanduser()
CANONICAL_PACK_DIR = Path("~/Music/SoundSwitch/rbss_canonical_pack").expanduser()

_RENAME_SWAP = 0x00000002
_EXPORT_LOCK_TTL_SECONDS = 10 * 60
try:
    _libc = ctypes.CDLL("libc.dylib", use_errno=True)
except OSError:
    _libc = None


class ExportAlreadyRunningError(RuntimeError):
    """Another publisher currently owns the destination lock."""


class PackSwapError(OSError):
    """The verified staged pack could not replace the canonical pack."""


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


def _fsync_dir(directory: Path) -> None:
    """fsync a directory so prior creates/renames within it survive a crash.

    File *contents* are made durable with ``os.fsync(fd)`` at write time, but the
    directory entries (and the atomic ``os.replace`` rename) are only durable
    after the containing directory itself is fsync'd.  Opening a directory fd and
    fsyncing it is unsupported on some platforms (e.g. Windows raises); treat
    that as best-effort rather than failing an otherwise-good export.
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _stage_artifacts(
    artifacts: dict[str, bytes], parent: Path, destination_name: str,
) -> Path:
    staging = Path(tempfile.mkdtemp(prefix=f".{destination_name}.tmp-", dir=parent))
    try:
        written_dirs = {staging}
        for relative, data in artifacts.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            written_dirs.add(path.parent)
        for directory in written_dirs:
            _fsync_dir(directory)
        return staging
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _renamex_np_swap(a: Path, b: Path, *, libc=None) -> None:
    handle = _libc if libc is None else libc
    if handle is None or not hasattr(handle, "renamex_np"):
        raise NotImplementedError("directory swap is unavailable")
    renamex_np = handle.renamex_np
    try:
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
    except AttributeError:
        pass
    result = renamex_np(os.fsencode(a), os.fsencode(b), _RENAME_SWAP)
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        raise OSError(error_number, os.strerror(error_number))


def _remove_backup(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def _backup_sort_key(path: Path) -> tuple[int, str]:
    try:
        modified = path.stat().st_mtime_ns
    except OSError:
        modified = -1
    return modified, path.name


def _recover_orphan_backup(parent: Path, name: str) -> None:
    destination = parent / name
    backups = sorted(parent.glob(f".{name}.bak-*"), key=_backup_sort_key, reverse=True)
    if not backups:
        return
    if not destination.exists() and not destination.is_symlink():
        os.replace(backups[0], destination)
        _fsync_dir(parent)
        backups = backups[1:]
    if destination.exists() or destination.is_symlink():
        for backup in backups:
            _remove_backup(backup)
        _fsync_dir(parent)


def _gc_orphan_staging(parent: Path, name: str) -> None:
    for staging in parent.glob(f".{name}.tmp-*"):
        if staging.is_symlink() or not staging.is_dir():
            staging.unlink(missing_ok=True)
        else:
            shutil.rmtree(staging, ignore_errors=True)
    _fsync_dir(parent)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_is_stale(lock_path: Path) -> bool:
    try:
        age = max(0.0, time.time() - lock_path.stat().st_mtime)
        first_line = lock_path.read_text(encoding="ascii", errors="strict").splitlines()[0]
        pid = int(first_line)
    except (OSError, UnicodeError, ValueError, IndexError):
        return True
    return age > _EXPORT_LOCK_TTL_SECONDS or not _pid_is_alive(pid)


@contextmanager
def _export_lock(parent: Path, name: str):
    lock_path = parent / f".{name}.export.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock_path, flags, 0o600)
    except FileExistsError:
        if not _lock_is_stale(lock_path):
            raise ExportAlreadyRunningError("export already running") from None
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        try:
            fd = os.open(lock_path, flags, 0o600)
        except FileExistsError:
            raise ExportAlreadyRunningError("export already running") from None
    try:
        os.write(fd, f"{os.getpid()}\n{time.monotonic()}\n".encode("ascii"))
        os.fsync(fd)
        owned_inode = os.fstat(fd).st_ino
    finally:
        os.close(fd)
    _fsync_dir(parent)
    try:
        yield
    finally:
        try:
            if lock_path.stat().st_ino == owned_inode:
                lock_path.unlink()
                _fsync_dir(parent)
        except FileNotFoundError:
            pass


def _atomic_swap_dir(staging: Path, destination: Path, parent: Path) -> None:
    try:
        _renamex_np_swap(destination, staging)
    except (OSError, AttributeError, NotImplementedError):
        backup = parent / f".{destination.name}.bak-{secrets.token_hex(8)}"
        os.replace(destination, backup)
        _fsync_dir(parent)
        try:
            os.replace(staging, destination)
        except BaseException:
            os.replace(backup, destination)
            _fsync_dir(parent)
            raise
        _fsync_dir(parent)
        _remove_backup(backup)
        _fsync_dir(parent)
        return
    _fsync_dir(parent)
    shutil.rmtree(staging, ignore_errors=True)
    _fsync_dir(parent)


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
    staging = _stage_artifacts(artifacts, parent, destination.name)
    try:
        result = verify_pack(staging, source_project=source)
        os.replace(staging, destination)
        # Persist the rename itself so the published pack survives a crash.
        _fsync_dir(parent)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def publish_pack(
    project: str | os.PathLike[str], destination_path: str | os.PathLike[str],
) -> dict[str, object]:
    source = Path(project).expanduser()
    destination = Path(destination_path).expanduser()
    if destination.is_symlink():
        raise ValueError("destination must not be a symlink")
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("destination parent must be an existing real directory")
    with _export_lock(parent, destination.name):
        _recover_orphan_backup(parent, destination.name)
        _gc_orphan_staging(parent, destination.name)
        if destination.is_symlink():
            raise ValueError("destination must not be a symlink")
        first_export = not destination.exists()
        decoded = decode_project(source)
        artifacts = compile_pack_artifacts(decoded, generator_commit=_generator_commit())
        staging = _stage_artifacts(artifacts, parent, destination.name)
        try:
            result = verify_pack(staging, source_project=source)
            try:
                if first_export:
                    os.replace(staging, destination)
                    _fsync_dir(parent)
                else:
                    _atomic_swap_dir(staging, destination, parent)
            except OSError as exc:
                raise PackSwapError("canonical pack swap failed") from exc
            return {**result, "first_export": first_export}
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise


def _atomic_write_result(path: Path, result: dict[str, object]) -> None:
    parent = path.expanduser().parent
    fd, staging_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=parent)
    staging = Path(staging_name)
    try:
        data = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, path.expanduser())
        _fsync_dir(parent)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        staging.unlink(missing_ok=True)
        raise


def _publish_verdict(exc: Exception) -> str:
    if isinstance(exc, ExportAlreadyRunningError):
        return "locked"
    if isinstance(exc, (SoundSwitchDecodeError, FileNotFoundError)):
        return "source_error"
    if isinstance(exc, SoundSwitchPackVerificationError):
        return "verify_failed"
    if isinstance(exc, PackSwapError):
        return "swap_failed"
    return "unknown_error"


def _canonical_publish_result() -> dict[str, object]:
    try:
        result = publish_pack(CANONICAL_SOURCE_PROJECT, CANONICAL_PACK_DIR)
    except Exception as exc:
        return {
            "ok": False,
            "verdict": _publish_verdict(exc),
            "manifest_sha256": "",
            "artifact_count": 0,
            "first_export": False,
            "error_category": type(exc).__name__,
        }
    return {
        "ok": True,
        "verdict": "published",
        "manifest_sha256": result["manifest_sha256"],
        "artifact_count": result["artifact_count"],
        "first_export": result["first_export"],
        "error_category": "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--publish-canonical", action="store_true")
    parser.add_argument("--result-json", type=Path)
    args = parser.parse_args(argv)
    if args.publish_canonical:
        if args.project is not None or args.output is not None or args.result_json is None:
            parser.error("canonical publish requires only --publish-canonical and --result-json")
        result = _canonical_publish_result()
        try:
            _atomic_write_result(args.result_json, result)
        except Exception:
            return 1
        return 0 if result["ok"] else 1
    if args.project is None or args.output is None or args.result_json is not None:
        parser.error("legacy export requires --project and --output")
    result = export_pack(args.project, args.output)
    print(f"pack: {args.output.expanduser()}")
    print(f"manifest_sha256: {result['manifest_sha256']}")
    print(f"artifacts: {result['artifact_count']}")
    print("status: SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
