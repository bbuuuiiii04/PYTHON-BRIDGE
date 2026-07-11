"""Detect and (with explicit consent) patch Rekordbox so the bridge can read it.

The bridge reads Rekordbox's live state via ``task_for_pid`` (see ``rb_memory.py``),
which macOS only permits when the TARGET — rekordbox — carries the
``com.apple.security.get-task-allow`` entitlement. Stock Rekordbox from
Pioneer/AlphaTheta is Developer-ID signed + notarized and does NOT carry it, so
on an un-patched Mac the bridge launches but reads nothing.

This module re-signs Rekordbox **ad-hoc** with ``get-task-allow`` added
(preserving its existing entitlements), replicating the signature already present
and proven working on the maintainer's primary Mac (ad-hoc + get-task-allow +
disable-library-validation).

THIS MODIFIES A THIRD-PARTY APP, so it is deliberately conservative:
  * **opt-in** — never runs without explicit operator consent (CLI ``--apply`` /
    menubar confirmation); ``--check``/``--dry-run`` do nothing destructive;
  * **refused while Rekordbox is running** — you re-sign a quit app, then relaunch
    it for the new signature to take effect;
  * **guarded** — only ever touches a bundle whose id is ``com.pioneerdj.rekordboxdj``;
  * **fail-closed + verified** — ``codesign --verify`` then re-reads get-task-allow;
    on any failure it reports the step and tells you to reinstall Rekordbox;
  * **reversible** only by reinstalling/updating Rekordbox (a RB update reverts the
    patch — expected; re-run this after an update).

CLI:
    python3 -m rb_ss_bridge_v2.rekordbox_patch --check
    python3 -m rb_ss_bridge_v2.rekordbox_patch --dry-run
    python3 -m rb_ss_bridge_v2.rekordbox_patch --apply          # prompts to confirm (always)

The menubar / frozen app uses run_interactive_gui() (macOS dialogs), never the CLI.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REKORDBOX_APP_PATHS: tuple[Path, ...] = (
    Path("/Applications/rekordbox 7/rekordbox.app"),
    Path("/Applications/rekordbox 6/rekordbox.app"),
    Path("/Applications/rekordbox/rekordbox.app"),
)
REKORDBOX_BUNDLE_ID = "com.pioneerdj.rekordboxdj"

# The entitlements that make the bridge's read work, matching the proven-working
# ad-hoc signature on the maintainer's primary Mac. Merged OVER the app's existing
# entitlements (everything else preserved), so Rekordbox keeps its own capabilities.
GET_TASK_ALLOW = "com.apple.security.get-task-allow"
ADDED_ENTITLEMENTS: dict[str, bool] = {
    GET_TASK_ALLOW: True,
    "com.apple.security.cs.disable-library-validation": True,
    "com.apple.security.cs.allow-unsigned-executable-memory": True,
}


# ── Pure, testable seams ─────────────────────────────────────────────────────

# The library-path vars PyInstaller's bootloader rewrites at launch, pointing them
# into the bundle and saving the pre-launch value as ``<VAR>_ORIG``.
_PYINSTALLER_LIBVARS = (
    "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES",
    "LD_LIBRARY_PATH", "LIBPATH", "SHLIB_PATH",
)


def sanitized_system_env(mapping) -> dict:
    """A copy of ``mapping`` with PyInstaller's bundle library-path pollution
    undone, for spawning macOS system tools (osascript/codesign/pgrep) or a
    non-bundled child from the frozen app.

    The bootloader points DYLD_LIBRARY_PATH (etc.) at the bundle's Frameworks and
    stashes the original as ``<VAR>_ORIG``. A child must see the ORIGINAL value
    (or none), never the bundle's, so restore each var from its ``_ORIG`` — or
    drop it when there was none — and strip the ``_ORIG`` bookkeeping keys. SIP
    tools ignore DYLD_* already, so this is defense-in-depth; it is also correct
    for any non-SIP helper those tools spawn. Pure — the unit-test seam."""
    env = dict(mapping)
    for var in _PYINSTALLER_LIBVARS:
        orig = f"{var}_ORIG"
        if orig in env:
            env[var] = env[orig]
        else:
            env.pop(var, None)
        env.pop(orig, None)
    return env


def parse_entitlements_output(data: bytes) -> dict:
    """Extract the entitlements dict from ``codesign -d --entitlements`` output.

    codesign prints an XML plist (possibly with leading/trailing noise); an
    unsigned app or one with no entitlements yields no plist. Returns {} on
    anything unparseable — fail-open to "no entitlements known" is safe because
    the caller then treats the app as needing a patch and re-verifies after.
    """
    if not data:
        return {}
    start = data.find(b"<?xml")
    if start == -1:
        start = data.find(b"<plist")
    end = data.rfind(b"</plist>")
    if start == -1 or end == -1:
        return {}
    try:
        obj = plistlib.loads(data[start:end + len(b"</plist>")])
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def build_patched_entitlements(current: dict) -> dict:
    """Current entitlements with the bridge-read entitlements merged in."""
    merged = dict(current)
    merged.update(ADDED_ENTITLEMENTS)
    return merged


def needs_patch(current: dict) -> bool:
    """True unless get-task-allow is already present and true."""
    return current.get(GET_TASK_ALLOW) is not True


def codesign_argv(app: Path, entitlements_path: Path) -> list[str]:
    """The ad-hoc re-sign command. ``--deep`` re-signs EVERY nested component
    ad-hoc too — frameworks, helper apps (rekordboxAgent.app), dylibs — matching
    the proven-working state on the maintainer's Mac, where `codesign -dv` shows
    the main bundle AND every nested item ad-hoc. A stock notarized Rekordbox
    will NOT launch as ad-hoc-main + Developer-ID/hardened nested, so a top-bundle-
    only re-sign would produce an unlaunchable app. ``--entitlements`` applies to
    the main executable, so get-task-allow lands where the bridge attaches."""
    return [
        "codesign", "--force", "--deep", "--sign", "-",
        "--entitlements", str(entitlements_path), str(app),
    ]


def enough_disk_for_backup(app_size: int, free: int, margin: int = 500 * 1024 * 1024) -> bool:
    """True if there is room to copy the whole bundle plus a safety margin. Pure —
    the test seam for the pre-re-sign disk guard (refuse rather than risk bricking
    Rekordbox with no restore path)."""
    return free >= app_size + margin


def is_user_cancel(stderr: str) -> bool:
    """True when an osascript admin escalation was cancelled by the operator
    (rc -128 / 'User canceled'). Rekordbox was never touched — the trampoline never
    ran codesign — so this is a CLEAN abort, not a codesign failure that needs a
    restore (which would pop a spurious second admin prompt). Pure test seam."""
    s = (stderr or "").lower()
    return "user canceled" in s or "user cancelled" in s or "(-128)" in s


# ── On-machine inspection (read-only) ────────────────────────────────────────

def find_rekordbox(app_paths: tuple[Path, ...] | None = None) -> Path | None:
    for app in (app_paths or REKORDBOX_APP_PATHS):
        if app.exists():
            return app
    return None


def bundle_id(app: Path) -> str:
    try:
        with open(app / "Contents" / "Info.plist", "rb") as fh:
            return str(plistlib.load(fh).get("CFBundleIdentifier", ""))
    except OSError:
        return ""


def read_entitlements(app: Path) -> dict:
    try:
        proc = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", "--xml", str(app)],
            capture_output=True, timeout=30, env=sanitized_system_env(os.environ),
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_entitlements_output(proc.stdout or b"")


def has_get_task_allow(app: Path) -> bool:
    return read_entitlements(app).get(GET_TASK_ALLOW) is True


def is_rekordbox_running() -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-x", "rekordbox"], capture_output=True, timeout=10,
            env=sanitized_system_env(os.environ),
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False  # can't tell -> treat as not running; apply_patch re-guards


# ── The patch ────────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    ok: bool
    action: str            # "already_patched" | "would_patch" | "patched" | "refused" | "failed"
    message: str
    command: list[str] | None = None


# A "runner" runs the codesign re-sign command and returns (returncode, stderr).
# The re-sign is the ONLY step needing write access to /Applications; verify +
# re-read are read-only and always run in-process.

def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        # 600s: a --deep re-sign of the ~2.4 GB universal Rekordbox bundle.
        p = subprocess.run(argv, capture_output=True, text=True, timeout=600,
                           env=sanitized_system_env(os.environ))
        return p.returncode, p.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"codesign did not run: {exc}"


# ── Backup / restore (never leave Rekordbox unlaunchable) ────────────────────
# codesign --force strips the old seal before writing the new one, so a mid-write
# failure (timeout, disk-full, force-quit) can leave Rekordbox unlaunchable. We
# snapshot the bundle BEFORE the re-sign (no admin needed — reading /Applications
# and writing a user temp dir), then restore it on ANY failure, so the operator
# is never told to reinstall (which on a guest means re-licensing Rekordbox).

def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            total += p.lstat().st_size
        except OSError:
            pass
    return total


def _snapshot_app(app: Path) -> Path | None:
    """Copy the bundle to a user temp backup after a free-disk guard. Returns the
    backup path, or None if there is not enough disk or the copy failed — the
    caller then REFUSES (never re-sign without a restore path)."""
    try:
        app_size = _dir_size(app)
        free = shutil.disk_usage(app.parent).free
    except OSError:
        return None
    if not enough_disk_for_backup(app_size, free):
        return None
    try:
        backup_dir = Path(tempfile.mkdtemp(prefix="rbss_rekordbox_backup_"))
        backup = backup_dir / app.name
        # ditto preserves the bundle's signature/metadata exactly (the point of
        # the backup); as the user, no admin prompt.
        subprocess.run(["ditto", str(app), str(backup)], check=True, timeout=1200,
                       capture_output=True)
    except (OSError, subprocess.SubprocessError):
        shutil.rmtree(backup_dir, ignore_errors=True)
        return None
    return backup


def _restore_app(app: Path, backup: Path, runner) -> bool:
    """Restore the backup over the (possibly damaged) bundle, as root via the same
    runner the re-sign used (one command; codesign --force only rewrites existing
    signature files, so `ditto backup app` overwrites them back in place). True on
    success."""
    rc, _ = (runner or _default_runner)(["ditto", str(backup), str(app)])
    return rc == 0


def _cleanup_backup(backup: Path) -> None:
    shutil.rmtree(backup.parent, ignore_errors=True)


def _fail_restored(app: Path, backup: Path, runner, reason: str, argv: list[str]) -> "PatchResult":
    """A failure result that first restores Rekordbox from the backup, so the
    message says 'still launchable' (never 'reinstall'); if the restore itself
    fails, it keeps the backup and says where it is."""
    if _restore_app(app, backup, runner):
        _cleanup_backup(backup)
        tail = " Rekordbox was restored from a pre-signing backup and is still launchable."
    else:
        tail = (f" Automatic restore failed — your original Rekordbox is backed up at "
                f"{backup.parent}; copy it back over {app} to recover (no reinstall needed).")
    return PatchResult(False, "failed", reason + tail, command=argv)


def run_via_admin(argv: list[str]) -> tuple[int, str]:
    """Run argv as root behind a macOS admin-password prompt (osascript).

    The command is written to a temp shell script (each arg shell-quoted) and
    osascript only references that fixed, shell-quoted temp path — nothing from
    argv is interpolated into the AppleScript string, so an app/plist path can't
    inject. Used by the menubar and CLI --admin when /Applications isn't writable.
    """
    script = "#!/bin/sh\nexec " + " ".join(shlex.quote(a) for a in argv) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script)
        sh_path = fh.name
    try:
        os.chmod(sh_path, 0o755)
        osa = subprocess.run(
            ["osascript", "-e",
             f'do shell script "/bin/sh {shlex.quote(sh_path)}" with administrator privileges'],
            capture_output=True, text=True, timeout=600,
            env=sanitized_system_env(os.environ),
        )
        return osa.returncode, osa.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"admin escalation failed: {exc}"
    finally:
        try:
            os.unlink(sh_path)
        except OSError:
            pass


def apply_patch(app: Path, *, dry_run: bool = True, runner=None) -> PatchResult:
    """Re-sign ``app`` ad-hoc with get-task-allow, fail-closed and verified.

    dry_run=True (default) does NO modification — it returns the exact codesign
    command that WOULD run. Callers must pass dry_run=False AND have obtained
    explicit consent to modify Rekordbox.
    """
    if bundle_id(app) != REKORDBOX_BUNDLE_ID:
        return PatchResult(False, "refused",
                           f"{app} is not Rekordbox (bundle id != {REKORDBOX_BUNDLE_ID}); refusing to sign.")
    if is_rekordbox_running():
        return PatchResult(False, "refused",
                           "Rekordbox is running — quit it first (re-sign only takes effect on relaunch).")

    current = read_entitlements(app)
    if not needs_patch(current):
        return PatchResult(True, "already_patched",
                           "Rekordbox already carries get-task-allow — nothing to do.")

    merged = build_patched_entitlements(current)
    # Write the entitlements to a temp plist codesign will read.
    with tempfile.NamedTemporaryFile("wb", suffix=".plist", delete=False) as fh:
        plistlib.dump(merged, fh)
        ents_path = Path(fh.name)
    argv = codesign_argv(app, ents_path)

    if dry_run:
        return PatchResult(True, "would_patch",
                           "Dry run — Rekordbox NOT modified. This command would add get-task-allow.",
                           command=argv)

    # Exclusive lock so a double-click / two concurrent runs can't interleave two
    # `codesign --force` writes on the same bundle (which would corrupt it).
    lock_fh = open(Path(tempfile.gettempdir()) / "rbss_rekordbox_patch.lock", "w")
    try:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return PatchResult(False, "refused",
                               "Another Rekordbox patch is already in progress — wait for it to finish.")

        # Snapshot BEFORE any --force write, so any failure below is recoverable.
        # No snapshot -> refuse (never re-sign without a restore path).
        backup = _snapshot_app(app)
        if backup is None:
            return PatchResult(False, "refused",
                               "Not enough free disk to safely back up Rekordbox (~2.4 GB) before "
                               "re-signing — refusing rather than risk leaving it unlaunchable. "
                               "Free up space and try again.")

        rc, err = (runner or _default_runner)(argv)
        if rc != 0:
            if is_user_cancel(err):
                # Operator dismissed the admin prompt: codesign never ran, Rekordbox
                # is untouched. Clean abort — do NOT restore (that would pop a second
                # admin prompt and falsely claim a recovery).
                _cleanup_backup(backup)
                return PatchResult(False, "refused",
                                   "Cancelled — Rekordbox was not modified.", command=argv)
            hint = ""
            if "not permitted" in err.lower() or "permission denied" in err.lower():
                hint = " (needs admin — run with sudo, or use --admin / the menubar which prompt for your password)"
            return _fail_restored(app, backup, runner, f"codesign failed{hint}: {err.strip()}.", argv)

        # Verify the re-sign is structurally valid AND the entitlement took. (This
        # cannot prove Rekordbox LAUNCHES / that task_for_pid works — the operator
        # confirms that by relaunching Rekordbox.) Any failure restores the backup.
        try:
            verify = subprocess.run(["codesign", "--verify", "--strict", str(app)],
                                    capture_output=True, text=True, timeout=180,
                                    env=sanitized_system_env(os.environ))
        except (OSError, subprocess.SubprocessError) as exc:
            return _fail_restored(app, backup, runner, f"could not verify the re-sign ({exc}).", argv)
        if verify.returncode != 0:
            return _fail_restored(app, backup, runner,
                                  "the re-sign did not verify: " + verify.stderr.strip() + ".", argv)
        if not has_get_task_allow(app):
            return _fail_restored(app, backup, runner,
                                  "the re-sign succeeded but get-task-allow is still absent — no change took effect.",
                                  argv)
        _cleanup_backup(backup)
        return PatchResult(True, "patched",
                           "Rekordbox patched. RELAUNCH Rekordbox and confirm it opens; then start the "
                           "bridge and it will read it.", command=argv)
    finally:
        lock_fh.close()  # releases the flock


# ── macOS GUI flow (menubar / frozen-app dispatch) ───────────────────────────

def _osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                          timeout=600, env=sanitized_system_env(os.environ))


def _gui_notify(message: str) -> None:
    # Modal OK dialog — a one-shot result the operator should actually see.
    _osascript(f'display dialog {json.dumps(message)} buttons {{"OK"}} '
               f'default button "OK" with title "RBSS Bridge"')


def _gui_confirm(message: str) -> bool:
    try:
        p = _osascript(f'display dialog {json.dumps(message)} buttons {{"Cancel", "Enable Reads"}} '
                       f'default button "Cancel" with title "RBSS Bridge"')
    except subprocess.SubprocessError:
        return False
    return p.returncode == 0 and "Enable Reads" in (p.stdout or "")


def run_interactive_gui() -> int:
    """Menubar/frozen-app entry: check → consent dialog → admin patch → result.
    Every message goes through a macOS dialog; no terminal needed."""
    app = find_rekordbox()
    if app is None:
        _gui_notify("Rekordbox not found in /Applications — install it first.")
        return 2
    if has_get_task_allow(app):
        _gui_notify("Rekordbox reads are already enabled on this Mac.")
        return 0
    if is_rekordbox_running():
        _gui_notify("Quit Rekordbox first, then choose Enable Rekordbox Reads again.")
        return 1
    if not _gui_confirm(
        "Enable the bridge to read Rekordbox on this Mac?\n\n"
        "This re-signs Rekordbox so the bridge can read its playback state. A "
        "Rekordbox update will undo it — just run this again. You'll be asked for "
        "your admin password."
    ):
        return 1
    result = apply_patch(app, dry_run=False, runner=run_via_admin)
    _gui_notify(result.message)
    return 0 if result.ok else 1


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Enable the bridge to read Rekordbox memory on this Mac.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="report whether Rekordbox is already patched (default)")
    g.add_argument("--dry-run", action="store_true", help="show the exact command without modifying anything")
    g.add_argument("--apply", action="store_true", help="apply the patch (Rekordbox must be quit)")
    ap.add_argument("--admin", action="store_true",
                    help="prompt for your admin password (osascript) instead of requiring sudo")
    args = ap.parse_args(argv)

    app = find_rekordbox()
    if app is None:
        print("Rekordbox not found in /Applications.")
        return 2

    if args.apply:
        print(f"About to RE-SIGN {app} ad-hoc (deep) to add get-task-allow.")
        print("  - This modifies Rekordbox (a Rekordbox update will revert it).")
        print("  - Quit Rekordbox first. You may be asked for your admin password.")
        if input("Type YES to proceed: ").strip() != "YES":
            print("Aborted.")
            return 1
        result = apply_patch(app, dry_run=False, runner=(run_via_admin if args.admin else None))
    elif args.dry_run:
        result = apply_patch(app, dry_run=True)
    else:  # --check (default)
        patched = has_get_task_allow(app)
        running = is_rekordbox_running()
        print(f"Rekordbox: {app}")
        print(f"  get-task-allow present: {'YES (bridge can read it)' if patched else 'NO (bridge will read nothing)'}")
        print(f"  running now: {'yes' if running else 'no'}")
        if not patched:
            print("  -> run with --apply to enable reads (quit Rekordbox first).")
        return 0 if patched else 3

    print(result.message)
    if result.command and (args.dry_run or not result.ok):
        print("  command:", " ".join(result.command))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
