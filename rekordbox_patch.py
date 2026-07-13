"""Detect and (with explicit consent) patch the Rekordbox target.

The bridge reads Rekordbox's live state via ``task_for_pid`` (see ``rb_memory.py``).
Target ``com.apple.security.get-task-allow`` is the expected access mechanism and
matches the TimecodeLink target-patch model (TimecodeLink had no caller
``cs.debugger`` and used the same ``task_for_pid`` / ``mach_vm_read_overwrite``
attach). This helper changes only the TARGET — Rekordbox — by adding that
entitlement. A positive entitlement check proves the Rekordbox target patch
only; it does not by itself prove a successful live attach or full foreign-Mac
parity. Stock Apple-Silicon foreign-Mac attach after a successful patch + deep
verify + GTA=true + relaunch is **live-unvalidated / unknown** — not confirmed
unsupported, and not a confirmed caller-authorization blocker. Earlier failed
runs never reached that clean pre-attach state, so they cannot prove caller
denial. Do not weaken SIP on a guest Mac (AWR-222).

This module re-signs Rekordbox **ad-hoc** with ``get-task-allow`` added
(preserving its existing entitlements). The maintainer Mac has custom SIP with
Debugging Restrictions disabled; that local behavior is not foreign-Mac proof.

THIS MODIFIES A THIRD-PARTY APP, so it is deliberately conservative:
  * **opt-in** — never runs without explicit operator consent (CLI ``--apply`` /
    menubar confirmation); ``--check``/``--dry-run`` do nothing destructive;
  * **refused while Rekordbox is running** — you re-sign a quit app, then relaunch
    it for the new signature to take effect;
  * **guarded** — only ever touches a bundle whose id is ``com.pioneerdj.rekordboxdj``;
  * **fail-closed + verified** — deep+strict ``codesign --verify``, then re-reads
    get-task-allow; on signing failure the same admin script restores the
    pre-sign backup (or keeps it and names the path if restore fails);
  * **reversible** via the retained pre-sign backup, or by reinstalling/updating
    Rekordbox (a RB update reverts the patch — expected; re-run this after an
    update).

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
BACKUP_ROOT = (
    Path.home() / "Library" / "Application Support" / "RBSS Rekordbox Backups"
)
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


class EntitlementsReadError(RuntimeError):
    """The target's entitlements could not be read safely."""


def _parse_entitlements_checked(data: bytes) -> tuple[dict, bool]:
    """Return (entitlements, structurally_valid_output)."""
    if not data:
        return {}, True
    start = data.find(b"<?xml")
    if start == -1:
        start = data.find(b"<plist")
    end = data.rfind(b"</plist>")
    if start == -1 or end == -1:
        return {}, False
    try:
        obj = plistlib.loads(data[start:end + len(b"</plist>")])
    except Exception:
        return {}, False
    return (obj, True) if isinstance(obj, dict) else ({}, False)


def parse_entitlements_output(data: bytes) -> dict:
    """Extract the entitlements dict from ``codesign -d --entitlements`` output.

    codesign prints an XML plist (possibly with leading/trailing noise); an
    unsigned app or one with no entitlements yields no plist. Returns {} on
    anything unparseable — fail-open to "no entitlements known" is safe because
    the caller then treats the app as needing a patch and re-verifies after.
    """
    parsed, valid = _parse_entitlements_checked(data)
    return parsed if valid else {}


def build_patched_entitlements(current: dict) -> dict:
    """Current entitlements with the bridge-read entitlements merged in."""
    merged = dict(current)
    merged.update(ADDED_ENTITLEMENTS)
    return merged


def needs_patch(current: dict) -> bool:
    """True unless get-task-allow is already present and true."""
    return current.get(GET_TASK_ALLOW) is not True


def codesign_argv(app: Path, entitlements_path: Path) -> list[str]:
    """Root-bundle ad-hoc sign argv only (no ``--deep``, no nested re-sign).

    One command: sign the ``.app`` with the merged entitlements plist so
    get-task-allow lands on the main attach target. Nested helpers / frameworks
    / ``rekordboxAgent`` keep their original Pioneer signatures.
    """
    return [
        "codesign", "--force", "--sign", "-",
        "--entitlements", str(entitlements_path), str(app),
    ]


def plan_codesign_argvs(app: Path, entitlements_path: Path) -> list[list[str]]:
    """Compatibility seam: exactly one root-bundle codesign argv."""
    return [codesign_argv(app, entitlements_path)]


def build_sign_restore_script(
    steps: list[tuple[str, list[str]]], app: Path, backup: Path,
) -> str:
    """Build a ``/bin/sh`` script: run the sign step(s), restore on any failure.

    Assumes the script already runs with administrator privileges (one osascript
    escalation). Every path/argument is shell-quoted. On codesign failure it
    restores ``backup`` → ``app`` in-script so recovery does not need a second
    password prompt. The apply plan is a single root-bundle step.
    """
    lines = ["#!/bin/sh"]
    for label, argv in steps:
        lines.append(
            f"printf '%s\\n' {shlex.quote('RBSS_SIGNING:' + label)} >&2"
        )
        quoted = " ".join(shlex.quote(a) for a in argv)
        lines.append(f"{quoted}")
        lines.append("rc=$?")
        lines.append("if [ \"$rc\" -ne 0 ]; then")
        lines.append(
            f"  printf '%s\\n' {shlex.quote('RBSS_SIGN_FAIL:' + label)} >&2"
        )
        lines.append(
            f"  ditto {shlex.quote(str(backup))} {shlex.quote(str(app))}"
        )
        lines.append("  if [ $? -eq 0 ]; then")
        lines.append("    printf '%s\\n' 'RBSS_RESTORE_OK' >&2")
        lines.append("  else")
        lines.append("    printf '%s\\n' 'RBSS_RESTORE_FAIL' >&2")
        lines.append("  fi")
        lines.append("  exit \"$rc\"")
        lines.append("fi")
    lines.append("printf '%s\\n' 'RBSS_SIGN_OK' >&2")
    lines.append("exit 0")
    lines.append("")
    return "\n".join(lines)


def parse_sign_fail_component(stderr: str) -> str | None:
    """Return the path/label after ``RBSS_SIGN_FAIL:``, or None."""
    for line in (stderr or "").splitlines():
        if line.startswith("RBSS_SIGN_FAIL:"):
            return line[len("RBSS_SIGN_FAIL:"):] or None
        # osascript may wrap stderr; allow the marker mid-line.
        idx = line.find("RBSS_SIGN_FAIL:")
        if idx != -1:
            return line[idx + len("RBSS_SIGN_FAIL:"):] or None
    return None


def parse_restore_marker(stderr: str) -> str | None:
    """Return ``ok`` / ``fail`` from in-script restore markers, or None."""
    text = stderr or ""
    if "RBSS_RESTORE_OK" in text:
        return "ok"
    if "RBSS_RESTORE_FAIL" in text:
        return "fail"
    return None


def _codesign_fail_detail(stderr: str) -> str:
    """Short non-secret stderr leftover after stripping RBSS_* markers."""
    keep: list[str] = []
    for line in (stderr or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if (
            "RBSS_SIGNING:" in stripped
            or "RBSS_SIGN_FAIL:" in stripped
            or "RBSS_RESTORE_OK" in stripped
            or "RBSS_RESTORE_FAIL" in stripped
            or "RBSS_SIGN_OK" in stripped
        ):
            continue
        # Never surface password / auth prompt text.
        low = stripped.lower()
        if "password" in low or "passwd" in low:
            continue
        keep.append(stripped)
    if not keep:
        return ""
    joined = " ".join(keep)
    if len(joined) > 240:
        joined = joined[:237] + "..."
    return joined


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


def app_management_block_hint(
    err: str,
    app: Path,
    *,
    frozen: bool | None = None,
) -> str:
    """Guidance when System Policy App Management blocked an /Applications write.

    Only for ``Operation not permitted`` against a target under ``/Applications``.
    Frozen vs source wording differs; unrelated sign failures return ``""``.
    """
    if "operation not permitted" not in (err or "").lower():
        return ""
    app_s = str(app)
    if not (app_s == "/Applications" or app_s.startswith("/Applications/")):
        return ""
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        return (
            "macOS blocked updating Rekordbox (App Management). "
            "Open System Settings \u2192 Privacy & Security \u2192 App Management, "
            "turn on RBSS Bridge, then try Patch Rekordbox again. "
            "An admin password alone is not enough."
        )
    return (
        "macOS blocked updating Rekordbox (App Management). "
        "Use the RBSS Bridge app build that requests App Management permission, "
        "then try Patch Rekordbox again."
    )


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
    except (OSError, subprocess.SubprocessError) as exc:
        raise EntitlementsReadError(f"codesign could not run: {exc}") from exc
    if proc.returncode != 0:
        raw_detail = proc.stderr or b""
        detail = (
            raw_detail.decode("utf-8", errors="replace")
            if isinstance(raw_detail, bytes)
            else str(raw_detail)
        ).strip()
        raise EntitlementsReadError(detail or f"codesign exited {proc.returncode}")
    parsed, valid = _parse_entitlements_checked(proc.stdout or b"")
    if not valid:
        raise EntitlementsReadError("codesign returned malformed entitlement data")
    return parsed


def has_get_task_allow(app: Path) -> bool:
    return read_entitlements(app).get(GET_TASK_ALLOW) is True


def is_rekordbox_running() -> bool | None:
    """True/False when pgrep knows, None when it cannot be trusted."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "rekordbox"], capture_output=True, timeout=10,
            env=sanitized_system_env(os.environ),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


# ── The patch ────────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    ok: bool
    action: str            # "already_patched" | "would_patch" | "patched" | "refused" | "failed"
    message: str
    command: list[str] | None = None
    commands: list[list[str]] | None = None


# A "runner" runs one argv and returns (returncode, stderr). When the runner is
# ``run_via_admin``, apply_patch instead builds one privileged root-bundle script
# via ``run_shell_via_admin`` so the operator sees a single password prompt.
# Verify + entitlement re-read are read-only and always run in-process.

def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        # 600s for the single root-bundle sign; full admin plan uses
        # run_shell_via_admin (1800s).
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


def _snapshot_app(app: Path, backup_root: Path = BACKUP_ROOT) -> Path | None:
    """Copy the bundle to a user temp backup after a free-disk guard. Returns the
    backup path, or None if there is not enough disk or the copy failed — the
    caller then REFUSES (never re-sign without a restore path)."""
    try:
        app_size = _dir_size(app)
        backup_root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(backup_root).free
    except OSError:
        return None
    if not enough_disk_for_backup(app_size, free):
        return None
    backup_dir = None
    try:
        backup_dir = Path(tempfile.mkdtemp(prefix="backup_", dir=backup_root))
        backup = backup_dir / app.name
        # ditto preserves the bundle's signature/metadata exactly (the point of
        # the backup); as the user, no admin prompt.
        subprocess.run(["ditto", str(app), str(backup)], check=True, timeout=1200,
                       capture_output=True)
    except (OSError, subprocess.SubprocessError):
        if backup_dir is not None:
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
    inject. Used for single-command restore after a reported sign success when
    later Python verify/entitlement checks fail. Full sign+restore uses
    ``run_shell_via_admin`` instead.
    """
    script = "#!/bin/sh\nexec " + " ".join(shlex.quote(a) for a in argv) + "\n"
    return run_shell_via_admin(script, timeout=600)


def run_shell_via_admin(script_text: str, timeout: int = 1800) -> tuple[int, str]:
    """Run a full shell script as root behind one osascript admin prompt.

    Writes ``script_text`` to a temp file and invokes ``/bin/sh <temp>`` with
    administrator privileges — one password dialog for the root-bundle sign
    (and in-script restore on failure). Default timeout is 1800s.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script_text)
        if not script_text.endswith("\n"):
            fh.write("\n")
        sh_path = fh.name
    try:
        os.chmod(sh_path, 0o755)
        osa = subprocess.run(
            ["osascript", "-e",
             f'do shell script "/bin/sh {shlex.quote(sh_path)}" with administrator privileges'],
            capture_output=True, text=True, timeout=timeout,
            env=sanitized_system_env(os.environ),
        )
        # osascript often puts failure detail in stdout; keep both for markers.
        err = (osa.stderr or "") + (("\n" + osa.stdout) if osa.stdout else "")
        return osa.returncode, err
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
    running = is_rekordbox_running()
    if running is None:
        return PatchResult(False, "refused",
                           "Could not tell whether Rekordbox is running; refusing to re-sign it.")
    if running:
        return PatchResult(False, "refused",
                           "Rekordbox is running — quit it first (re-sign only takes effect on relaunch).")

    try:
        current = read_entitlements(app)
    except EntitlementsReadError as exc:
        return PatchResult(
            False,
            "refused",
            f"Could not safely read Rekordbox's existing entitlements ({exc}); "
            "refusing to re-sign so none are stripped.",
        )
    if not needs_patch(current):
        return PatchResult(True, "already_patched",
                           "Rekordbox already carries get-task-allow — nothing to do.")

    merged = build_patched_entitlements(current)
    # Write the entitlements to a temp plist codesign will read.
    with tempfile.NamedTemporaryFile("wb", suffix=".plist", delete=False) as fh:
        plistlib.dump(merged, fh)
        ents_path = Path(fh.name)

    if dry_run:
        argvs = plan_codesign_argvs(app, ents_path)
        sign_argv = argvs[0]
        return PatchResult(
            True, "would_patch",
            "Dry run — Rekordbox NOT modified. Root-bundle sign plan "
            f"(exactly 1 codesign command, no nested re-sign):\n"
            f"  {' '.join(sign_argv)}",
            command=sign_argv,
            commands=argvs,
        )

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

        argvs = plan_codesign_argvs(app, ents_path)
        sign_argv = argvs[0]
        steps = [(sign_argv[-1], sign_argv)]

        use_admin_script = runner is run_via_admin
        if use_admin_script:
            script = build_sign_restore_script(steps, app, backup)
            rc, err = run_shell_via_admin(script)
            if rc != 0:
                if is_user_cancel(err):
                    # Operator dismissed the admin prompt: the privileged script
                    # never ran, Rekordbox is untouched. Clean abort — do NOT
                    # restore (that would pop a second admin prompt).
                    _cleanup_backup(backup)
                    return PatchResult(False, "refused",
                                       "Cancelled — Rekordbox was not modified.",
                                       command=sign_argv, commands=argvs)
                component = parse_sign_fail_component(err) or str(app)
                restore_state = parse_restore_marker(err)
                detail = _codesign_fail_detail(err)
                detail_tail = f" Detail: {detail}" if detail else ""
                cmd_note = f" Failed command: {' '.join(sign_argv)}."
                am_hint = app_management_block_hint(err, app)
                am_tail = f" {am_hint}" if am_hint else ""
                # Retain the backup after any failed apply as operator evidence,
                # even when in-script restore reported OK (safer than today's
                # successful-restore cleanup until the operator confirms launch).
                if restore_state == "ok":
                    return PatchResult(
                        False, "failed",
                        f"codesign failed on {component}.{cmd_note}{detail_tail} "
                        "Rekordbox was restored from the pre-signing backup in "
                        "the same admin step and should still be launchable. "
                        f"Backup retained at {backup.parent}.{am_tail}",
                        command=sign_argv, commands=argvs,
                    )
                if restore_state == "fail":
                    return PatchResult(
                        False, "failed",
                        f"codesign failed on {component}.{cmd_note}{detail_tail} "
                        "Automatic restore failed — your original Rekordbox is "
                        f"backed up at {backup.parent}; copy it back over {app} "
                        f"to recover (no reinstall needed).{am_tail}",
                        command=sign_argv, commands=argvs,
                    )
                return PatchResult(
                    False, "failed",
                    f"codesign failed on {component}.{cmd_note}{detail_tail} "
                    "The restore result could not be confirmed from the admin "
                    f"script output. A verified pre-sign backup is retained at "
                    f"{backup.parent}; copy it back over {app} if Rekordbox will "
                    f"not launch (no reinstall needed).{am_tail}",
                    command=sign_argv, commands=argvs,
                )
        else:
            active_runner = runner or _default_runner
            rc, err = active_runner(sign_argv)
            if rc != 0:
                if is_user_cancel(err):
                    _cleanup_backup(backup)
                    return PatchResult(False, "refused",
                                       "Cancelled — Rekordbox was not modified.",
                                       command=sign_argv, commands=argvs)
                hint = ""
                if "not permitted" in err.lower() or "permission denied" in err.lower():
                    hint = (" (needs admin — run with sudo, or use --admin / "
                            "the menubar which prompt for your password)")
                return _fail_restored(
                    app, backup, active_runner,
                    f"codesign failed on {sign_argv[-1]}{hint}: {err.strip()}.",
                    sign_argv,
                )

        # Verify the re-sign is structurally valid AND the entitlement took. (This
        # cannot prove Rekordbox LAUNCHES / that task_for_pid works — the operator
        # confirms that by relaunching Rekordbox.) Any failure restores the backup.
        # Never skip restore merely because verify happens to pass after a failure:
        # sign-failure restore already ran in-script (admin) or via _fail_restored.
        restore_runner = run_via_admin if use_admin_script else (runner or _default_runner)
        try:
            verify = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(app)],
                capture_output=True, text=True, timeout=180,
                env=sanitized_system_env(os.environ),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return _fail_restored(
                app, backup, restore_runner,
                f"could not verify the re-sign ({exc}).", sign_argv,
            )
        if verify.returncode != 0:
            return _fail_restored(
                app, backup, restore_runner,
                "the re-sign did not verify: " + verify.stderr.strip() + ".",
                sign_argv,
            )
        try:
            target_patched = has_get_task_allow(app)
        except EntitlementsReadError as exc:
            return _fail_restored(
                app, backup, restore_runner,
                f"the re-sign could not be verified safely ({exc}).", sign_argv,
            )
        if not target_patched:
            return _fail_restored(
                app, backup, restore_runner,
                "the re-sign succeeded but get-task-allow is still absent — "
                "no change took effect.",
                sign_argv,
            )
        return PatchResult(
            True, "patched",
            "Rekordbox target patched. RELAUNCH Rekordbox and confirm it opens. "
            "A positive get-task-allow check proves the target patch only; it "
            "does not prove a live attach. Stock foreign-Mac attach after "
            "patch + deep verify + GTA=true + relaunch is live-unvalidated / "
            "unknown. "
            f"The original app is kept at {backup.parent}; purging RBSS Bridge "
            "does not remove it.",
            command=sign_argv, commands=argvs,
        )
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
        p = _osascript(f'display dialog {json.dumps(message)} buttons {{"Cancel", "Apply Patch"}} '
                       f'default button "Cancel" with title "RBSS Bridge"')
    except subprocess.SubprocessError:
        return False
    return p.returncode == 0 and "Apply Patch" in (p.stdout or "")


def run_interactive_gui() -> int:
    """Menubar/frozen-app entry: check → consent dialog → admin patch → result.
    Every message goes through a macOS dialog; no terminal needed."""
    app = find_rekordbox()
    if app is None:
        _gui_notify("Rekordbox not found in /Applications — install it first.")
        return 2
    try:
        already_patched = has_get_task_allow(app)
    except EntitlementsReadError as exc:
        _gui_notify(
            "Could not safely read Rekordbox's current entitlements, so it was "
            f"not modified: {exc}"
        )
        return 1
    if already_patched:
        _gui_notify(
            "The Rekordbox target patch is already present. That proves the "
            "target entitlement only; it does not prove a live attach on this Mac."
        )
        return 0
    running = is_rekordbox_running()
    if running is None:
        _gui_notify("Could not tell whether Rekordbox is running, so it was not modified.")
        return 1
    if running:
        _gui_notify("Quit Rekordbox first, then choose Apply Rekordbox Target Patch again.")
        return 1
    if not _gui_confirm(
        "Apply the Rekordbox target patch?\n\n"
        "This re-signs Rekordbox with get-task-allow (TimecodeLink-style target "
        "patch). A positive entitlement proves the patch only, not a live attach. "
        "Stock foreign-Mac attach after patch + deep verify + GTA=true + relaunch "
        "is live-unvalidated / unknown — not a confirmed caller-authorization "
        "blocker. A Rekordbox update will undo it. You'll be asked for your "
        "admin password."
    ):
        return 1
    result = apply_patch(app, dry_run=False, runner=run_via_admin)
    _gui_notify(result.message)
    return 0 if result.ok else 1


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inspect or apply the Rekordbox target patch.")
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
        print(f"About to RE-SIGN {app} ad-hoc (root bundle only) to add get-task-allow.")
        print("  - This modifies Rekordbox (a Rekordbox update will revert it).")
        print("  - Quit Rekordbox first. You may be asked for your admin password.")
        if input("Type YES to proceed: ").strip() != "YES":
            print("Aborted.")
            return 1
        result = apply_patch(app, dry_run=False, runner=(run_via_admin if args.admin else None))
    elif args.dry_run:
        result = apply_patch(app, dry_run=True)
    else:  # --check (default)
        try:
            patched = has_get_task_allow(app)
        except EntitlementsReadError as exc:
            print(f"Could not safely read Rekordbox entitlements: {exc}")
            return 4
        running = is_rekordbox_running()
        print(f"Rekordbox: {app}")
        print(
            "  target get-task-allow present: "
            f"{'YES (target patch only; live attach unproven)' if patched else 'NO'}"
        )
        print(f"  running now: {'yes' if running else 'no' if running is False else 'unknown (could not verify)'}")
        if running is None:
            return 4
        if not patched:
            print("  -> run with --apply to add the target patch (quit Rekordbox first).")
        return 0 if patched else 3

    print(result.message)
    if result.command and (args.dry_run or not result.ok):
        print("  command:", " ".join(result.command))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
