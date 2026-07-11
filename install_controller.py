"""Native in-app install helpers for the frozen menubar (AWR-186 M2, Task 2/4).

Pure decision helpers + a subprocess-free installer the menubar wraps in UI.
The menubar (scripts/bridge_menubar.py) imports this ONLY in frozen runs — a
source-run menubar never touches it, so source behavior stays byte-identical.

Interoperability contract: the manifest written here is the SAME file-level
``install_manifest.txt`` the AWR-122 interim stick commands use (one absolute
path per line, app bundle path first, appended as each item lands), so
``packaging/stick/purge.command`` and the native menubar PURGE remove exactly
what either installer created.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePath

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "RBSS Bridge"
APPS_DIR = Path.home() / "Applications"
MANIFEST_NAME = "install_manifest.txt"
PAYLOAD_DIRNAME = "RBSS_payload"
LOGS_DIR = Path.home() / "Library" / "Logs" / "rb_ss_bridge"


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


def should_offer_install(bundle: str | Path | None, manifest_exists: bool) -> bool:
    """Menubar shows "Install on this Mac…" only for a DMG/translocated run
    that has not been installed yet (no manifest on this Mac)."""
    if bundle is None or manifest_exists:
        return False
    return running_from_read_only_location(bundle)


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


def perform_install(
    bundle: str | Path,
    *,
    apps_dir: Path = APPS_DIR,
    app_support: Path = APP_SUPPORT_DIR,
) -> InstallResult:
    """Copy the app + payload onto this Mac, manifest-recorded, fail closed.

    Steps (manifest appended AFTER each success, so a partial failure leaves the
    manifest listing exactly what was actually created):
      1. app bundle -> <apps_dir>/RBSS Bridge.app
      2. payload spectral_cache/** -> <app_support>/spectral_cache/** (file-level)
      3. payload home/*            -> <app_support>/* (govee.env + live configs)
      4. payload soundswitch_pack/** -> <app_support>/soundswitch_pack/** (file-level)

    No subprocesses, no dialogs — the menubar owns the UI around this. A failed
    step reports WHICH step and stops; nothing is rolled back (the DMG-run app
    stays fully usable either way).
    """
    bundle = Path(bundle)
    result = InstallResult(ok=False)
    app_dest = apps_dir / bundle.name
    manifest = app_support / MANIFEST_NAME
    result.app_dest = app_dest
    result.manifest_path = manifest

    try:
        apps_dir.mkdir(parents=True, exist_ok=True)
        app_support.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.failed_step = f"create target folders ({type(exc).__name__})"
        return result

    # Disk pre-flight: refuse rather than leave a half-copied, unlaunchable app on a
    # low-disk guest. Reuses the same predicate the Rekordbox backup uses.
    from rb_ss_bridge_v2.rekordbox_patch import enough_disk_for_backup
    try:
        app_size = sum(p.lstat().st_size for p in bundle.rglob("*") if not p.is_symlink())
        free = shutil.disk_usage(apps_dir).free
    except OSError as exc:
        result.failed_step = f"check free disk ({type(exc).__name__})"
        return result
    if not enough_disk_for_backup(app_size, free):
        result.failed_step = "insufficient free disk to copy the app"
        return result
    try:
        if app_dest.exists():
            shutil.rmtree(app_dest)
        shutil.copytree(bundle, app_dest, symlinks=True)
    except OSError as exc:
        # Roll back a partial copy so the guest is never left with a broken app.
        shutil.rmtree(app_dest, ignore_errors=True)
        result.failed_step = f"copy app to {app_dest} ({type(exc).__name__})"
        return result
    try:
        manifest.write_text(f"{app_dest}\n", encoding="utf-8")
    except OSError as exc:
        result.failed_step = f"write manifest ({type(exc).__name__})"
        return result

    payload = payload_dir(bundle)
    cache_src = payload / "spectral_cache"
    if cache_src.is_dir():
        for src in _iter_files(cache_src):
            rel = src.relative_to(cache_src)
            dest = app_support / "spectral_cache" / rel
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
            except OSError as exc:
                result.failed_step = (
                    f"install analysis cache file {rel} ({type(exc).__name__})"
                )
                return result
            with manifest.open("a", encoding="utf-8") as fp:
                fp.write(f"{dest}\n")
            result.installed_files += 1
    else:
        result.notes.append("no spectral_cache payload — tracks analyze on first play")

    home_src = payload / "home"
    if home_src.is_dir():
        for src in _iter_files(home_src):
            dest = app_support / src.name
            # Never overwrite an operator's TUNED config on a reinstall/upgrade —
            # home/* is live config (govee.env + laser/led/pack), not cache. (The
            # cache + pack dirs below keep refreshing; they are content, not tuning.)
            if dest.exists():
                result.notes.append(
                    f"kept existing {src.name} (reinstall did not overwrite tuned config)"
                )
                continue
            try:
                shutil.copyfile(src, dest)
            except OSError as exc:
                result.failed_step = f"install config {src.name} ({type(exc).__name__})"
                return result
            with manifest.open("a", encoding="utf-8") as fp:
                fp.write(f"{dest}\n")
            result.installed_files += 1
    else:
        result.notes.append(
            "no home-parity payload — bridge runs on example configs, no Govee cloud"
        )

    pack_src = payload / "soundswitch_pack"
    if pack_src.is_dir():
        for src in _iter_files(pack_src):
            rel = src.relative_to(pack_src)
            dest = app_support / "soundswitch_pack" / rel
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
            except OSError as exc:
                result.failed_step = f"install pack file {rel} ({type(exc).__name__})"
                return result
            with manifest.open("a", encoding="utf-8") as fp:
                fp.write(f"{dest}\n")
            result.installed_files += 1

    result.ok = True
    return result


def path_is_removable(path: str, *, apps_dir: Path = APPS_DIR, app_support: Path = APP_SUPPORT_DIR) -> bool:
    """Same allowlist discipline as packaging/stick/purge.command: a manifest
    entry is removable only under ~/Applications or the RBSS App Support dir,
    and never with a '..' component."""
    if ".." in PurePath(path).parts:
        return False
    text = str(path)
    return text.startswith(f"{apps_dir}/") or text.startswith(f"{app_support}/")


@dataclass
class PurgeResult:
    removed: int = 0
    skipped: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    remains_note: str = (
        "Permission entries in System Settings stay (macOS keeps those; inert)."
    )


def perform_purge(
    *,
    apps_dir: Path = APPS_DIR,
    app_support: Path = APP_SUPPORT_DIR,
    logs_dir: Path = LOGS_DIR,
    own_app: Path | None = None,
) -> PurgeResult:
    """Remove everything the bridge installed or created — three roots, in order.

    1. Manifest paths (exactly, allowlist-checked, '..' rejected) — skipping
       ``own_app``, which the menubar moves to Trash itself after this returns.
    2. The whole App Support dir (configs/secrets/caches/state, incl. manifest).
    3. ~/Library/Logs/rb_ss_bridge.

    A failed item is recorded and the purge CONTINUES to the next removable
    item — never a silent half-broken stop. Touches nothing outside the three
    roots: not the stick, not the DMG, not other volumes.
    """
    result = PurgeResult()
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
        try:
            shutil.rmtree(root)
            result.removed += 1
        except OSError as exc:
            result.failures.append(f"{root} ({type(exc).__name__})")
    return result
