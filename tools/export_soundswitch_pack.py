#!/usr/bin/env python3
"""Export the pinned saved SoundSwitch project into a canonical static pack."""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import logging
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
from rb_ss_bridge_v2.tools.ssfmt.update_parity_registry import (  # noqa: E402
    build_autoloop_registry, build_scripted_registry, build_static_registry,
    reconcile_edited_witnesses,
)


CANONICAL_SOURCE_PROJECT = Path("~/Music/SoundSwitch/default.ssproj").expanduser()
CANONICAL_PACK_DIR = REPO_ROOT / "local" / "soundswitch" / "rbss_canonical_pack"
PARITY_REGISTRY_DIR = REPO_ROOT / "tests" / "fixtures" / "soundswitch"
# Committed capture-derived U0 evidence. Registries are recomputed from these
# fixtures against the pack actually being exported (see
# `_compile_and_stage_with_self_healed_parity`) so a venue-cue ADDITION (which
# changes SoundSwitchVenues.bin's sha and therefore every `venue_source_sha256`
# pin) self-heals instead of permanently stranding witnessed documents in
# `unverified_parity` until someone manually reruns the registry tool.
PARITY_ORACLE_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "soundswitch" / "parity_oracle"
SCRIPTED_FIXTURE = PARITY_ORACLE_FIXTURE_DIR / "scripted_reduced.json"
AUTOLOOP_FIXTURE = PARITY_ORACLE_FIXTURE_DIR / "autoloop_reduced.json"
STATIC_FIXTURE = PARITY_ORACLE_FIXTURE_DIR / "static_reduced.json"
logger = logging.getLogger("export_soundswitch_pack")

_SIDECAR_SUFFIX = ".source.json"  # sibling of the pack dir; NEVER inside it
_BINDING_SIDECAR_SUFFIX = ".midi_bindings.json"

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


class BindingSidecarWriteError(RuntimeError):
    """The required Stream Deck MIDI binding sidecar could not be written."""


class UnverifiedParityPublishError(RuntimeError):
    """A verified pack still contains documents that cannot publish as trusted parity."""


def _load_parity_registry(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_parity_registries() -> dict[str, object]:
    return {
        "scripted": _load_parity_registry(PARITY_REGISTRY_DIR / "scripted_parity_registry.json"),
        "autoloop": _load_parity_registry(PARITY_REGISTRY_DIR / "autoloop_parity_registry.json"),
        "static": _load_parity_registry(PARITY_REGISTRY_DIR / "static_parity_registry.json"),
    }


def _recomputed_parity_registries(
    staging: Path, stale_registries: dict[str, object],
) -> dict[str, object]:
    """Recompute each parity surface's registry from its committed capture
    fixture against the pack just staged.

    A surface whose fixture file is absent falls back to the stale (pass-1,
    committed-snapshot) registry for that surface only -- status quo when
    there is no capture evidence file to (re)verify against. A fixture that
    IS present but whose builder raises is deliberately NOT caught here: the
    exception must propagate so a broken evidence pipeline fails the export
    loudly instead of silently publishing with degraded/empty parity
    evidence for that surface.
    """
    fresh: dict[str, object] = dict(stale_registries)
    if SCRIPTED_FIXTURE.is_file():
        fresh["scripted"] = build_scripted_registry(staging, SCRIPTED_FIXTURE)
    if AUTOLOOP_FIXTURE.is_file():
        fresh["autoloop"] = build_autoloop_registry(staging, AUTOLOOP_FIXTURE)
    if STATIC_FIXTURE.is_file():
        fresh["static"] = build_static_registry(staging, STATIC_FIXTURE)
    return fresh


def _compile_and_stage_with_self_healed_parity(
    decoded, parent: Path, destination_name: str, *, generator_commit: str | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    """Compile+stage the pack, self-healing its parity registries from the
    committed capture fixtures before the pack can ever verify or publish.

    Pass 1 compiles and stages using the committed registry snapshots exactly
    as before. Pass 2 rebuilds each surface's registry from the fixtures
    against that staged pack -- the builders are lane-independent (they read
    documents/renders, not `parity_lane` fields), so the pass-1 lanes do not
    bias the rebuild. If the fresh registries differ from the ones pass 1
    used (e.g. a venue-cue ADDITION changed `venue_source_sha256` and would
    otherwise strand every witnessed document in `unverified_parity` until a
    human reruns the registry tool), the pack is recompiled with the fresh
    registries and re-staged; the pass-1 staging is discarded. If identical
    -- the common case once the committed snapshots are already current --
    the pass-1 staging is returned unchanged and no second compile happens.
    """
    stale_registries = _load_parity_registries()
    if generator_commit is None:
        generator_commit = _generator_commit()
    artifacts = compile_pack_artifacts(
        decoded, generator_commit=generator_commit, parity_registry=stale_registries,
    )
    staging = _stage_artifacts(artifacts, parent, destination_name)
    try:
        fresh_registries = _recomputed_parity_registries(staging, stale_registries)
        retirements: list[dict[str, str]] = []
        for surface in ("scripted", "autoloop"):
            fresh_surface = fresh_registries.get(surface)
            stale_surface = stale_registries.get(surface)
            if isinstance(fresh_surface, dict) and isinstance(stale_surface, dict):
                reconciled, retired = reconcile_edited_witnesses(fresh_surface, stale_surface)
                fresh_registries[surface] = reconciled
                retirements.extend(retired)
        for retirement in retirements:
            logger.info(
                "[EXPORT] parity-evidence-retired identity=%s reason=witness_source_edited",
                retirement["identity"],
            )
        if fresh_registries == stale_registries:
            return staging, retirements
        recompiled = compile_pack_artifacts(
            decoded, generator_commit=generator_commit, parity_registry=fresh_registries,
        )
        restaged = _stage_artifacts(recompiled, parent, destination_name)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    return restaged, retirements


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


def _source_stat_signature(project: str | os.PathLike[str]) -> str | None:
    """Cheap change gate: sha256 over sorted (relpath, size, mtime_ns) of every
    regular file in the bundle. Returns None if the bundle is absent."""
    base = Path(project).expanduser()
    if not base.is_dir():
        return None
    entries = []
    for root, dirs, files in os.walk(base, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            path = Path(root) / name
            try:
                st = path.lstat()
            except OSError:
                continue
            rel = path.relative_to(base).as_posix()
            entries.append((rel, st.st_size, st.st_mtime_ns))
    digest = hashlib.sha256()
    for rel, size, mtime in sorted(entries):
        digest.update(f"{rel}\x00{size}\x00{mtime}\n".encode("utf-8"))
    return digest.hexdigest()


def _source_content_fingerprint(
    project: str | os.PathLike[str], *, ignore: frozenset[str] = frozenset(),
) -> str | None:
    """Exact change signal: sha256 over sorted (relpath, sha256(file bytes)) of
    every regular file in the bundle, excluding `ignore` relpaths. Returns None
    if the bundle is absent."""
    base = Path(project).expanduser()
    if not base.is_dir():
        return None
    rows = []
    for root, dirs, files in os.walk(base, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            path = Path(root) / name
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            if rel in ignore:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                return None  # unreadable source -> treat as "cannot prove up-to-date"
            rows.append((rel, hashlib.sha256(data).hexdigest()))
    digest = hashlib.sha256()
    for rel, file_hash in sorted(rows):
        digest.update(f"{rel}\x00{file_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def _sidecar_path(destination: Path) -> Path:
    return destination.parent / f".{destination.name}{_SIDECAR_SUFFIX}"


def _binding_sidecar_path(destination: Path) -> Path:
    return destination.parent / f".{destination.name}{_BINDING_SIDECAR_SUFFIX}"


def _opaque_source_paths(pack_dir: Path) -> frozenset[str]:
    """Relpaths the decoder retained but parsed nothing from (backups, demo
    media, caches). SoundSwitch rewrites these during normal navigation, so they
    must not count as pending export changes. Read from the pack manifest the
    publish just wrote; absent/unreadable -> empty (fall back to whole-tree)."""
    try:
        manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    inventory = manifest.get("source_inventory", []) if isinstance(manifest, dict) else []
    return frozenset(
        row["path"] for row in inventory
        if isinstance(row, dict)
        and row.get("parse_status") == "retained_opaque"
        and isinstance(row.get("path"), str)
        and not row["path"].startswith("recordable/")
    )


def _write_source_sidecar(
    destination: Path, source: Path, manifest_sha256: str,
    *, generator_commit: str | None = None,
) -> None:
    ignored = _opaque_source_paths(destination)
    fingerprint = _source_content_fingerprint(source, ignore=ignored)
    if fingerprint is None:
        return  # cannot fingerprint -> leave no sidecar; detection stays "changes"
    if generator_commit is None:
        generator_commit = _generator_commit()
    payload = {
        "source_fingerprint": fingerprint,
        "generator_commit": generator_commit,
        "pack_manifest_sha256": manifest_sha256,
        "ignored_paths": sorted(ignored),
    }
    _atomic_write_result(_sidecar_path(destination), payload)


def _binding_sidecar_rows(decoded) -> list[dict[str, object]]:
    rows = []
    for row in decoded.resolved_controls:
        binding = row.binding
        if not binding.enabled or row.target_kind != "static_look":
            continue
        if binding.message_type != "note" or row.interaction_mode not in ("press", "toggle"):
            continue
        rows.append({
            "channel": binding.channel_zero_based,
            "note": binding.data_byte,
            "target_kind": "static_look",
            "interaction": row.interaction_mode,
            "name": row.target_name or "",
        })
    rows.sort(key=lambda item: (item["channel"], item["note"], item["name"]))
    return rows


def _write_binding_sidecar(destination: Path, decoded) -> None:
    _atomic_write_result(_binding_sidecar_path(destination), _binding_sidecar_rows(decoded))


def _write_required_binding_sidecar(destination: Path, decoded) -> None:
    try:
        _write_binding_sidecar(destination, decoded)
    except Exception as exc:
        raise BindingSidecarWriteError("midi binding sidecar write failed") from exc


def _stage_binding_sidecar(parent: Path, destination_name: str, decoded) -> Path:
    """Produce and durably write the required binding sidecar to a sibling temp.

    Done BEFORE the canonical pack swap so a sidecar that cannot be produced or
    written fails the publish while the prior verified pack stays untouched; the
    returned temp is promoted with one rename after the swap. The ``.tmp-`` prefix
    matches ``_gc_orphan_staging`` so an interrupted run's temp is reclaimed.
    """
    try:
        data = (json.dumps(_binding_sidecar_rows(decoded), sort_keys=True,
                           separators=(",", ":")) + "\n").encode()
        fd, staging_name = tempfile.mkstemp(prefix=f".{destination_name}.tmp-", dir=parent)
        staging = Path(staging_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_dir(parent)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            staging.unlink(missing_ok=True)
            raise
        return staging
    except Exception as exc:
        raise BindingSidecarWriteError("midi binding sidecar write failed") from exc


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
    candidates = sorted(parent.glob(f".{name}.bak-*"), key=_backup_sort_key, reverse=True)
    if not candidates:
        return
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("destination must be a real directory")
    # A swap backup is ALWAYS created from a real directory (see _atomic_swap_dir),
    # so only a real directory may ever become the canonical pack. Any symlink/file
    # ".bak-*" is stray (or hostile) junk and must NEVER be moved into place.
    real_backups = [p for p in candidates if p.is_dir() and not p.is_symlink()]
    junk = [p for p in candidates if not (p.is_dir() and not p.is_symlink())]
    if not destination.exists() and real_backups:
        os.replace(real_backups[0], destination)
        _fsync_dir(parent)
        real_backups = real_backups[1:]
    if destination.is_dir() and not destination.is_symlink():
        for backup in real_backups:
            _remove_backup(backup)
    for stray in junk:
        _remove_backup(stray)
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
    owned_inode = os.fstat(fd).st_ino
    try:
        os.write(fd, f"{os.getpid()}\n{time.monotonic()}\n".encode("ascii"))
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            if lock_path.stat().st_ino == owned_inode:
                lock_path.unlink()
                _fsync_dir(parent)
        except OSError:
            pass
        raise
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
    staging, retirements = _compile_and_stage_with_self_healed_parity(
        decoded, parent, destination.name,
    )
    try:
        result = verify_pack(staging, source_project=source)
        os.replace(staging, destination)
        # Persist the rename itself so the published pack survives a crash.
        _fsync_dir(parent)
        try:
            _write_required_binding_sidecar(destination, decoded)
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            _fsync_dir(parent)
            raise
        return {**result, "parity_evidence_retired": retirements}
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _assert_publishable_parity(pack: Path, *, allow_unverified_parity: bool) -> None:
    if allow_unverified_parity:
        return
    try:
        manifest = json.loads((pack / "manifest.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    lanes = manifest.get("parity_lanes")
    if not isinstance(lanes, dict):
        return
    unverified = lanes.get("unverified_parity", 0)
    if isinstance(unverified, int) and unverified > 0:
        raise UnverifiedParityPublishError(
            f"pack has {unverified} unverified_parity documents; "
            "trusted publication requires oracle_proven or algorithm_generalized parity"
        )


def publish_pack(
    project: str | os.PathLike[str], destination_path: str | os.PathLike[str],
    *, allow_unverified_parity: bool = False, generator_commit: str | None = None,
) -> dict[str, object]:
    source = Path(project).expanduser()
    destination = Path(destination_path).expanduser()
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("destination must be a real directory or absent")
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("destination parent must be an existing real directory")
    with _export_lock(parent, destination.name):
        _recover_orphan_backup(parent, destination.name)
        _gc_orphan_staging(parent, destination.name)
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise ValueError("destination must be a real directory or absent")
        first_export = not destination.exists()
        decoded = decode_project(source)
        # Read the generator commit ONCE per publish and thread it to both the
        # manifest (compile) and the source sidecar, so an auto-sync commit
        # landing mid-publish can't split provenance (AWR-179 D4-F3).
        if generator_commit is None:
            generator_commit = _generator_commit()
        staging, retirements = _compile_and_stage_with_self_healed_parity(
            decoded, parent, destination.name, generator_commit=generator_commit,
        )
        try:
            result = verify_pack(staging, source_project=source)
            _assert_publishable_parity(
                staging,
                allow_unverified_parity=allow_unverified_parity,
            )
            # Stage the REQUIRED binding sidecar before the swap so a sidecar that
            # cannot be produced/written fails the publish with the canonical pack
            # untouched (matching export_pack's all-or-nothing contract). It is a
            # sibling file, so it is promoted with one rename after the swap.
            staged_sidecar = _stage_binding_sidecar(parent, destination.name, decoded)
            try:
                if first_export:
                    os.replace(staging, destination)
                    _fsync_dir(parent)
                else:
                    _atomic_swap_dir(staging, destination, parent)
            except OSError as exc:
                staged_sidecar.unlink(missing_ok=True)
                raise PackSwapError("canonical pack swap failed") from exc
            except BaseException:
                staged_sidecar.unlink(missing_ok=True)
                raise
            try:
                os.replace(staged_sidecar, _binding_sidecar_path(destination))
                _fsync_dir(parent)
            except OSError as exc:
                staged_sidecar.unlink(missing_ok=True)
                raise BindingSidecarWriteError("midi binding sidecar promote failed") from exc
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return {
            **result,
            "first_export": first_export,
            "parity_evidence_retired": retirements,
            "generator_commit": generator_commit,
        }


def _atomic_write_result(path: Path, result: object) -> None:
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
    if isinstance(exc, BindingSidecarWriteError):
        return "sidecar_failed"
    if isinstance(exc, UnverifiedParityPublishError):
        return "unverified_parity"
    return "unknown_error"


def _canonical_publish_result() -> dict[str, object]:
    try:
        CANONICAL_PACK_DIR.parent.mkdir(parents=True, exist_ok=True)
        result = publish_pack(CANONICAL_SOURCE_PROJECT, CANONICAL_PACK_DIR)
    except Exception as exc:
        return {
            "ok": False,
            "verdict": _publish_verdict(exc),
            "manifest_sha256": "",
            "artifact_count": 0,
            "first_export": False,
            "parity_evidence_retired": [],
            "error_category": type(exc).__name__,
        }
    try:
        _write_source_sidecar(
            CANONICAL_PACK_DIR,
            CANONICAL_SOURCE_PROJECT,
            str(result["manifest_sha256"]),
            generator_commit=result.get("generator_commit"),
        )
    except Exception:
        pass
    return {
        "ok": True,
        "verdict": "published",
        "manifest_sha256": result["manifest_sha256"],
        "artifact_count": result["artifact_count"],
        "first_export": result["first_export"],
        "parity_evidence_retired": result.get("parity_evidence_retired", []),
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
    # Operator visibility: show the note -> SoundSwitch Autoloop mapping the bridge
    # will resolve at runtime, loaded from the pack just written. Best-effort: a
    # summary failure must never fail the export itself.
    try:
        from rb_ss_bridge_v2.soundswitch_pack_loader import load_pack
        loaded = load_pack(args.output)
        print(f"autoloops: {len(loaded.autoloops)}")
        print(f"autoloop_bindings: {len(loaded.autoloop_bindings)}")
        for (ch0, note), binding in sorted(loaded.autoloop_bindings.items()):
            print(f"  ch{ch0 + 1} note {note} -> {binding.target_name} "
                  f"({binding.target_identity})")
    except Exception as exc:  # noqa: BLE001 — summary is advisory only
        print(f"binding-summary: unavailable ({type(exc).__name__})")
    print("status: SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
