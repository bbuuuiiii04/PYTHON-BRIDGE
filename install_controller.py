"""Native in-app install helpers for the frozen menubar (AWR-186 M2, Task 2/4).

Pure decision helpers + a subprocess-free installer the menubar wraps in UI.
The menubar (scripts/bridge_menubar.py) imports this ONLY in frozen runs — a
source-run menubar never touches it, so source behavior stays byte-identical.

The file-level ``install_manifest.txt`` remains backward-compatible with the
retired AWR-122 shell helpers, so native Purge can safely clean an older install.
New sticks ship only the DMG and use this native install/update/purge path.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePath

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "RBSS Bridge"
APPS_DIR = Path.home() / "Applications"
MANIFEST_NAME = "install_manifest.txt"
INCOMPLETE_MARKER_NAME = "install_incomplete"
PAYLOAD_DIRNAME = "RBSS_payload"
BUILD_MANIFEST_NAME = "build_manifest.json"
LOGS_DIR = Path.home() / "Library" / "Logs" / "rb_ss_bridge"
_REQUIRED_HOME_FILES = frozenset(
    {
        "govee.env",
        "laser_director.json",
        "led_look_director.json",
        "soundswitch_pack_player.json",
        "laser_color_map.json",
    }
)
_REQUIRED_PAYLOAD_PATHS = frozenset(
    {
        "spectral_cache",
        "soundswitch_pack",
        "lighting_sidecar",
        "streamdeck_midi_bindings.json",
        BUILD_MANIFEST_NAME,
    }
)


def bundle_root(executable: str | Path) -> Path | None:
    """The enclosing ``*.app`` bundle of a frozen executable, or None."""
    for parent in Path(executable).resolve().parents:
        if parent.name.endswith(".app"):
            return parent
    return None


def running_from_read_only_location(bundle: str | Path) -> bool:
    """True when the bundle runs from a mounted DMG or an app-translocation
    mirror — the two launch locations that mean 'not installed on this Mac'."""
    text = str(bundle)
    return text.startswith("/Volumes/") or "/AppTranslocation/" in text


def payload_dir(bundle: str | Path) -> Path:
    """RBSS_payload sits next to the .app inside the mounted DMG (make_stick.sh
    stages both into the DMG root)."""
    return Path(bundle).parent / PAYLOAD_DIRNAME


def should_offer_install(
    bundle: str | Path | None,
    manifest_exists: bool,
    install_incomplete: bool | None = None,
) -> bool:
    """Show the one native install/update action on every DMG/translocated run.

    The optional third argument keeps this helper deterministic in tests. The
    marker does not change visibility; it selects the retry label below.
    """
    return bundle is not None and running_from_read_only_location(bundle)


def install_action_title(
    manifest_exists: bool,
    install_incomplete: bool | None = None,
) -> str:
    """Plain label for the single native DMG action."""
    if install_incomplete is None:
        install_incomplete = (APP_SUPPORT_DIR / INCOMPLETE_MARKER_NAME).exists()
    if install_incomplete:
        return "Retry Installation…"
    if manifest_exists:
        return "Update This Mac…"
    return "Install on This Mac…"


@dataclass
class InstallResult:
    ok: bool
    failed_step: str = ""
    app_dest: Path | None = None
    installed_files: int = 0
    manifest_path: Path | None = None
    notes: list[str] = field(default_factory=list)


def _iter_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_package(bundle: Path) -> tuple[Path, dict]:
    """Validate the DMG's complete, hash-locked app + payload before copying."""
    payload = payload_dir(bundle)
    manifest_path = payload / BUILD_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"read package build manifest ({type(exc).__name__})") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("generation"), str)
        or not manifest["generation"].strip()
        or not isinstance(manifest.get("files"), list)
    ):
        raise ValueError("package build manifest has an unsupported shape")

    root = bundle.parent
    expected: dict[str, tuple[int, str]] = {}
    for row in manifest["files"]:
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256"}:
            raise ValueError("package build manifest has a malformed file row")
        rel = row["path"]
        pure = PurePath(rel) if isinstance(rel, str) else PurePath("..")
        if (
            not isinstance(rel, str)
            or pure.is_absolute()
            or ".." in pure.parts
            or pure.parts[:1] not in {("RBSS Bridge.app",), (PAYLOAD_DIRNAME,)}
            or rel == f"{PAYLOAD_DIRNAME}/{BUILD_MANIFEST_NAME}"
            or rel in expected
            or not isinstance(row["size"], int)
            or row["size"] < 0
            or not isinstance(row["sha256"], str)
            or len(row["sha256"]) != 64
        ):
            raise ValueError("package build manifest has an unsafe file row")
        expected[rel] = (row["size"], row["sha256"])

    actual = {
        str(path.relative_to(root))
        for tree in (bundle, payload)
        for path in _iter_files(tree)
        if path != manifest_path
    }
    if actual != set(expected):
        raise ValueError("package file list does not match its build manifest")
    for rel, (size, digest) in expected.items():
        path = root / rel
        try:
            if path.stat().st_size != size or _sha256(path) != digest:
                raise ValueError(f"package file failed integrity check: {rel}")
        except OSError as exc:
            raise ValueError(
                f"package file cannot be read: {rel} ({type(exc).__name__})"
            ) from exc

    home = payload / "home"
    present = {path.name for path in home.iterdir()} if home.is_dir() else set()
    missing = sorted(_REQUIRED_HOME_FILES - present)
    missing.extend(
        sorted(name for name in _REQUIRED_PAYLOAD_PATHS if not (payload / name).exists())
    )
    for dirname in ("spectral_cache", "soundswitch_pack", "lighting_sidecar"):
        directory = payload / dirname
        if not directory.is_dir() or not _iter_files(directory):
            missing.append(f"{dirname} (empty)")
    if missing:
        raise ValueError(f"package is missing required managed data: {', '.join(missing)}")
    if present != _REQUIRED_HOME_FILES or any(not path.is_file() for path in home.iterdir()):
        raise ValueError("package managed home data has unexpected entries")
    try:
        for name in _REQUIRED_HOME_FILES - {"govee.env"}:
            if not isinstance(json.loads((home / name).read_text(encoding="utf-8")), dict):
                raise ValueError(f"managed config is not a JSON object: {name}")
        key_rows = [
            line.split("=", 1)[1].strip()
            for line in (home / "govee.env").read_text(encoding="utf-8").splitlines()
            if line.startswith("GOVEE_API_KEY=")
        ]
        bindings = json.loads(
            (payload / "streamdeck_midi_bindings.json").read_text(encoding="utf-8")
        )
        required_binding = {"channel", "interaction", "name", "note", "target_kind"}
        sidecar = json.loads(
            (payload / "lighting_sidecar" / "index.json").read_text(encoding="utf-8")
        )
        tracks = sidecar.get("tracks") if isinstance(sidecar, dict) else None
        for path in (payload / "soundswitch_pack").rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"package managed data is malformed ({type(exc).__name__})") from exc
    if len(key_rows) != 1 or not key_rows[0]:
        raise ValueError("package Govee credential is missing or empty")
    if (
        not isinstance(bindings, list)
        or not bindings
        or any(not isinstance(row, dict) or set(row) != required_binding for row in bindings)
    ):
        raise ValueError("package Stream Deck MIDI bindings are malformed")
    if (
        sidecar.get("schema_version") != 1
        or not isinstance(tracks, list)
        or not tracks
        or sidecar.get("track_count") != len(tracks)
    ):
        raise ValueError("package lighting sidecar is empty or malformed")
    return payload, manifest


def _copy_managed_payload(payload: Path, target: Path) -> int:
    installed = 0
    for dirname in ("spectral_cache", "soundswitch_pack", "lighting_sidecar"):
        source = payload / dirname
        shutil.copytree(source, target / dirname, symlinks=True)
        installed += len(_iter_files(source))
    for source in _iter_files(payload / "home"):
        shutil.copy2(source, target / source.name)
        installed += 1
    for name in ("streamdeck_midi_bindings.json", BUILD_MANIFEST_NAME):
        shutil.copy2(payload / name, target / name)
        installed += 1
    return installed


def _replace(source: Path, destination: Path) -> None:
    """One-filesystem rename; kept as the narrow failure-injection seam."""
    source.replace(destination)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _commit_install(
    app_stage: Path,
    support_stage: Path,
    app_dest: Path,
    app_support: Path,
) -> list[str]:
    """Commit both staged trees; restore the prior pair if any rename fails."""
    token = app_stage.name.rsplit("-", 1)[-1]
    app_backup = app_dest.parent / f".{app_dest.name}.previous-{token}"
    support_backup = app_support.parent / f".{app_support.name}.previous-{token}"
    app_old = app_new = support_old = support_new = False
    try:
        if app_dest.exists():
            _replace(app_dest, app_backup)
            app_old = True
        _replace(app_stage, app_dest)
        app_new = True
        if app_support.exists():
            _replace(app_support, support_backup)
            support_old = True
        _replace(support_stage, app_support)
        support_new = True
        if hasattr(os, "sync"):
            os.sync()
    except OSError as exc:
        rollback_errors: list[str] = []
        try:
            if support_new and app_support.exists():
                _replace(app_support, support_stage)
            if support_old and support_backup.exists():
                _replace(support_backup, app_support)
        except OSError as rollback_exc:
            rollback_errors.append(f"support rollback {type(rollback_exc).__name__}")
        try:
            if app_new and app_dest.exists():
                _replace(app_dest, app_stage)
            if app_old and app_backup.exists():
                _replace(app_backup, app_dest)
        except OSError as rollback_exc:
            rollback_errors.append(f"app rollback {type(rollback_exc).__name__}")
        detail = f"commit install ({type(exc).__name__})"
        if rollback_errors:
            detail += "; " + ", ".join(rollback_errors)
        return [detail]

    cleanup_errors: list[str] = []
    for backup in (app_backup, support_backup):
        if not backup.exists():
            continue
        try:
            _remove_path(backup)
        except OSError as exc:
            cleanup_errors.append(
                f"old backup retained at {backup} ({type(exc).__name__})"
            )
    if hasattr(os, "sync"):
        try:
            os.sync()
        except OSError as exc:
            cleanup_errors.append(f"final disk flush ({type(exc).__name__})")
    return cleanup_errors


def perform_install(
    bundle: str | Path,
    *,
    apps_dir: Path = APPS_DIR,
    app_support: Path = APP_SUPPORT_DIR,
) -> InstallResult:
    """Install a verified app/payload generation, rolling back as one update."""
    bundle = Path(bundle)
    result = InstallResult(ok=False)
    app_dest = apps_dir / bundle.name
    manifest = app_support / MANIFEST_NAME
    incomplete_marker = app_support / INCOMPLETE_MARKER_NAME
    result.app_dest = app_dest
    result.manifest_path = manifest

    try:
        apps_dir.mkdir(parents=True, exist_ok=True)
        app_support.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.failed_step = f"create target folders ({type(exc).__name__})"
        return result

    # The old install remains launchable throughout staging. This marker only
    # changes the DMG action label to Retry if validation/copy/commit stops.
    try:
        incomplete_marker.write_text("install unfinished\n", encoding="utf-8")
    except OSError as exc:
        result.failed_step = f"mark install unfinished ({type(exc).__name__})"
        return result

    try:
        payload, package_manifest = _validate_package(bundle)
    except (OSError, ValueError) as exc:
        result.failed_step = str(exc)
        return result

    try:
        app_bytes = sum(p.stat().st_size for p in _iter_files(bundle))
        payload_bytes = sum(p.stat().st_size for p in _iter_files(payload))
        required = app_bytes + payload_bytes + 500 * 1024 * 1024
        if apps_dir.stat().st_dev == app_support.parent.stat().st_dev:
            enough = shutil.disk_usage(apps_dir).free >= required
        else:
            enough = (
                shutil.disk_usage(apps_dir).free >= app_bytes + 250 * 1024 * 1024
                and shutil.disk_usage(app_support.parent).free
                >= payload_bytes + 250 * 1024 * 1024
            )
    except OSError as exc:
        result.failed_step = f"check free disk ({type(exc).__name__})"
        return result
    if not enough:
        result.failed_step = "insufficient free disk for a rollback-safe update"
        return result

    app_stage = Path(tempfile.mkdtemp(prefix=f".{bundle.name}.installing-", dir=apps_dir))
    support_stage = Path(
        tempfile.mkdtemp(prefix=f".{app_support.name}.installing-", dir=app_support.parent)
    )
    try:
        app_stage.rmdir()
        shutil.copytree(bundle, app_stage, symlinks=True)
        installed_files = _copy_managed_payload(payload, support_stage)
        learned = app_support / "state"
        if learned.is_dir() and not learned.is_symlink():
            shutil.copytree(learned, support_stage / "state", symlinks=True)

        installed_paths = [str(app_dest)]
        installed_paths.extend(
            str(app_support / path.relative_to(support_stage))
            for path in _iter_files(support_stage)
        )
        manifest_text = "\n".join(installed_paths) + "\n"
        (support_stage / MANIFEST_NAME).write_text(manifest_text, encoding="utf-8")
    except OSError as exc:
        result.failed_step = f"stage complete install ({type(exc).__name__})"
        shutil.rmtree(app_stage, ignore_errors=True)
        shutil.rmtree(support_stage, ignore_errors=True)
        return result

    commit_notes = _commit_install(app_stage, support_stage, app_dest, app_support)
    if commit_notes and commit_notes[0].startswith("commit install"):
        result.failed_step = commit_notes[0]
        shutil.rmtree(app_stage, ignore_errors=True)
        shutil.rmtree(support_stage, ignore_errors=True)
        return result
    result.notes.extend(commit_notes)
    result.installed_files = installed_files
    result.manifest_path = app_support / MANIFEST_NAME
    result.notes.append(f"installed generation {package_manifest['generation']}")
    result.ok = True
    return result


def path_is_removable(path: str, *, apps_dir: Path = APPS_DIR, app_support: Path = APP_SUPPORT_DIR) -> bool:
    """A manifest entry is removable only under ~/Applications or the RBSS App
    Support dir, and never with a '..' component."""
    if ".." in PurePath(path).parts:
        return False
    text = str(path)
    return text.startswith(f"{apps_dir}/") or text.startswith(f"{app_support}/")


@dataclass
class PurgeResult:
    removed: int = 0
    skipped: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    remains_note: str = (
        "Permission entries in System Settings stay (macOS keeps those; inert)."
    )


def perform_purge(
    *,
    apps_dir: Path = APPS_DIR,
    app_support: Path = APP_SUPPORT_DIR,
    logs_dir: Path = LOGS_DIR,
    own_app: Path | None = None,
    backup_archive: Path | None = None,
) -> PurgeResult:
    """Remove everything the bridge installed or created — three roots, in order.

    1. Manifest paths (exactly, allowlist-checked, '..' rejected) — skipping
       ``own_app``, which the menubar moves to Trash itself after this returns.
    2. Preserve any legacy original-Rekordbox backup outside the purge root,
       then remove the App Support dir (configs/secrets/caches/state/manifest).
    3. ~/Library/Logs/rb_ss_bridge.

    A failed item is recorded and the purge CONTINUES to the next removable
    item — never a silent half-broken stop. Touches nothing outside the three
    roots: not the stick, not the DMG, not other volumes.
    """
    result = PurgeResult()
    legacy_backups = app_support / "rekordbox_backups"
    backup_archive = backup_archive or app_support.parent / "RBSS Rekordbox Backups"
    backup_migration_failed = False
    if legacy_backups.is_dir() and not legacy_backups.is_symlink():
        try:
            backup_archive.mkdir(parents=True, exist_ok=True)
            for source in sorted(legacy_backups.iterdir()):
                destination = backup_archive / source.name
                suffix = 2
                while destination.exists():
                    destination = backup_archive / f"{source.name}.legacy-{suffix}"
                    suffix += 1
                shutil.move(str(source), str(destination))
                result.preserved.append(str(destination))
            legacy_backups.rmdir()
            result.remains_note += (
                f" Original Rekordbox backup preserved at {backup_archive}."
            )
        except OSError as exc:
            backup_migration_failed = True
            result.failures.append(
                f"preserve Rekordbox backup at {backup_archive} ({type(exc).__name__})"
            )
    elif legacy_backups.exists():
        backup_migration_failed = True
        result.failures.append(
            f"preserve Rekordbox backup at {legacy_backups} (unsafe path type)"
        )

    manifest = app_support / MANIFEST_NAME
    lines: list[str] = []
    try:
        lines = [
            line.strip()
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError:
        result.skipped.append(f"no readable manifest at {manifest}")

    for line in lines:
        if own_app is not None and line == str(own_app):
            continue  # the running bundle goes to Trash after purge
        if backup_migration_failed and (
            line == str(legacy_backups) or line.startswith(f"{legacy_backups}/")
        ):
            result.skipped.append(line)
            continue
        if not path_is_removable(line, apps_dir=apps_dir, app_support=app_support):
            result.skipped.append(line)
            continue
        target = Path(line)
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            result.removed += 1
        except OSError as exc:
            result.failures.append(f"{line} ({type(exc).__name__})")

    for root in (app_support, logs_dir):
        if not root.exists():
            continue
        if root == app_support and backup_migration_failed:
            result.skipped.append(
                f"kept {app_support} because its Rekordbox backup could not be preserved"
            )
            continue
        try:
            shutil.rmtree(root)
            result.removed += 1
        except OSError as exc:
            result.failures.append(f"{root} ({type(exc).__name__})")
    return result
