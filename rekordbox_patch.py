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
  * **verified, no app copy** — deep+strict ``codesign --verify``, then re-reads
    get-task-allow. The operator explicitly declined a full Rekordbox backup,
    so a failed sign is reported plainly instead of creating one.

CLI:
    python3 -m rb_ss_bridge_v2.rekordbox_patch --check
    python3 -m rb_ss_bridge_v2.rekordbox_patch --dry-run
    python3 -m rb_ss_bridge_v2.rekordbox_patch --apply          # prompts to confirm (always)

The menubar / frozen app uses run_interactive_gui() (macOS dialogs), never the CLI.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import os
import plistlib
import re
import select
import shlex
import subprocess
import sys
import tempfile
import time
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


def build_sign_script(steps: list[tuple[str, list[str]]]) -> str:
    """Build the one privileged root-bundle signing script.

    Every path/argument is shell-quoted. The maintainer explicitly rejected
    full-app backups, so a nonzero sign exits immediately for the caller to
    report and verify instead of copying Rekordbox on every attempt.
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
        # An admin-shell wrapper may wrap stderr; allow the marker mid-line.
        idx = line.find("RBSS_SIGN_FAIL:")
        if idx != -1:
            return line[idx + len("RBSS_SIGN_FAIL:"):] or None
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


def is_user_cancel(stderr: str) -> bool:
    """True when an admin authorization was cancelled before signing began."""
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


# A "runner" runs one argv and returns (returncode, stderr). The two privileged
# runners below receive one combined root-bundle script. Verify + entitlement
# re-read stay read-only and always run in-process.

def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        # 600s for the single root-bundle sign.
        p = subprocess.run(argv, capture_output=True, text=True, timeout=600,
                           env=sanitized_system_env(os.environ))
        return p.returncode, p.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"codesign did not run: {exc}"


def _failed_without_backup(
    reason: str,
    argv: list[str],
    commands: list[list[str]] | None = None,
) -> "PatchResult":
    """Report a failed mutation without pretending the target was restored."""
    return PatchResult(
        False,
        "failed",
        reason
        + " No Rekordbox backup was made by request. Do not assume it will launch; "
        "reinstall or update Rekordbox if a subsequent signature check fails.",
        command=argv,
        commands=commands,
    )


def run_via_admin(argv: list[str]) -> tuple[int, str]:
    """Run argv as root behind a macOS admin-password prompt (osascript).

    The command is written to a temp shell script (each arg shell-quoted) and
    osascript only references that fixed, shell-quoted temp path — nothing from
    argv is interpolated into the AppleScript string, so an app/plist path can't
    inject. Kept only for source/legacy callers; the frozen menu uses the native
    authorization runner below.
    """
    script = "#!/bin/sh\nexec " + " ".join(shlex.quote(a) for a in argv) + "\n"
    return run_shell_via_admin(script, timeout=600)


def run_shell_via_admin(script_text: str, timeout: int = 1800) -> tuple[int, str]:
    """Run a full shell script as root behind one osascript admin prompt.

    Writes ``script_text`` to a temp file and invokes ``/bin/sh <temp>`` with
    administrator privileges — one password dialog for the root-bundle sign.
    Default timeout is 1800s.
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


_NATIVE_ADMIN_EXIT = "RBSS_NATIVE_RC:"
_AUTHORIZATION_CANCELED = -60006


class _AuthorizationItem(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("value_length", ctypes.c_uint32),
        ("value", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
    ]


class _AuthorizationRights(ctypes.Structure):
    _fields_ = [
        ("count", ctypes.c_uint32),
        ("items", ctypes.POINTER(_AuthorizationItem)),
    ]


def parse_native_admin_exit(output: str) -> tuple[int, str] | None:
    """Split the wrapper's final exit marker from native-admin command output."""
    match = re.search(rf"(?:^|\n){re.escape(_NATIVE_ADMIN_EXIT)}(\d+)\s*\Z", output)
    if match is None:
        return None
    return int(match.group(1)), output[:match.start()].rstrip()


def run_shell_via_native_authorization(
    script_text: str, timeout: int = 1800,
) -> tuple[int, str]:
    """Run a root shell script via the calling app's native macOS authorization.

    Unlike an ``osascript`` escalation, this keeps the responsible application as
    RBSS Bridge, so its App Management grant can update a protected app bundle.
    The outer wrapper owns the exit marker because the inner signing script
    deliberately calls ``exit`` on failure.
    """
    if sys.platform != "darwin":
        return 1, "native admin authorization is available only on macOS"
    payload_path = None
    wrapper_path = None
    auth = ctypes.c_void_p()
    pipe = ctypes.c_void_p()
    security = None
    libc = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(script_text)
            if not script_text.endswith("\n"):
                fh.write("\n")
            payload_path = fh.name
        os.chmod(payload_path, 0o700)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write("#!/bin/sh\nexec 2>&1\nPATH=/usr/bin:/bin:/usr/sbin:/sbin\n")
            fh.write(f"/bin/sh {shlex.quote(payload_path)}\n")
            fh.write(f'rc=$?; printf "\\n{_NATIVE_ADMIN_EXIT}%s\\n" "$rc"\n')
            wrapper_path = fh.name
        os.chmod(wrapper_path, 0o700)

        security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        security.AuthorizationCreate.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        security.AuthorizationCreate.restype = ctypes.c_int32
        security.AuthorizationCopyRights.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_AuthorizationRights), ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_void_p,
        ]
        security.AuthorizationCopyRights.restype = ctypes.c_int32
        security.AuthorizationExecuteWithPrivileges.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_void_p),
        ]
        security.AuthorizationExecuteWithPrivileges.restype = ctypes.c_int32
        security.AuthorizationFree.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        libc.fileno.argtypes = [ctypes.c_void_p]
        libc.fileno.restype = ctypes.c_int
        libc.fclose.argtypes = [ctypes.c_void_p]
        libc.fclose.restype = ctypes.c_int

        status = security.AuthorizationCreate(None, None, 0, ctypes.byref(auth))
        if status:
            return 1, f"native admin authorization setup failed (OSStatus {status})"
        tool = b"/bin/sh"
        tool_value = ctypes.create_string_buffer(tool)
        item = _AuthorizationItem(
            b"system.privilege.admin", len(tool),
            ctypes.cast(tool_value, ctypes.c_void_p), 0,
        )
        rights = _AuthorizationRights(1, ctypes.pointer(item))
        status = security.AuthorizationCopyRights(
            auth, ctypes.byref(rights), None, 0x3, None,
        )
        if status:
            if status == _AUTHORIZATION_CANCELED:
                return 1, "User canceled native admin authorization."
            return 1, f"native admin authorization was not granted (OSStatus {status})"
        argv = (ctypes.c_char_p * 2)(wrapper_path.encode(), None)
        # ponytail: use the still-present native API because a signed SMJobBless
        # helper cannot ship from this ad-hoc USB build; replace it only when the
        # project gains a distributable signed privileged helper.
        status = security.AuthorizationExecuteWithPrivileges(
            auth, tool, 0, argv, ctypes.byref(pipe),
        )
        if status:
            return 1, f"native admin command could not start (OSStatus {status})"
        if not pipe.value:
            return 1, "native admin command did not provide an output pipe"
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        fd = libc.fileno(pipe)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return 1, f"native admin command timed out after {timeout}s"
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                return 1, f"native admin command timed out after {timeout}s"
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        output = b"".join(chunks).decode("utf-8", errors="replace")
        parsed = parse_native_admin_exit(output)
        if parsed is None:
            return 1, output + "\nNative admin command did not return an exit marker."
        return parsed
    except (OSError, ValueError, ctypes.ArgumentError) as exc:
        return 1, f"native admin escalation failed: {exc}"
    finally:
        if pipe.value and libc is not None:
            try:
                libc.fclose(pipe)
            except OSError:
                pass
        if auth.value and security is not None:
            try:
                security.AuthorizationFree(auth, 0)
            except OSError:
                pass
        for path in (wrapper_path, payload_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


def run_via_native_authorization(argv: list[str]) -> tuple[int, str]:
    """Native-authorize one root command for CLI callers."""
    script = "exec " + " ".join(shlex.quote(a) for a in argv) + "\n"
    return run_shell_via_native_authorization(script, timeout=600)


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
        result = PatchResult(
            True, "would_patch",
            "Dry run — Rekordbox NOT modified. Root-bundle sign plan "
            f"(exactly 1 codesign command, no nested re-sign):\n"
            f"  {' '.join(sign_argv)}",
            command=sign_argv,
            commands=argvs,
        )
        try:
            ents_path.unlink()
        except OSError:
            pass
        return result

    # Exclusive lock so a double-click / two concurrent runs can't interleave two
    # `codesign --force` writes on the same bundle (which would corrupt it).
    lock_fh = open(Path(tempfile.gettempdir()) / "rbss_rekordbox_patch.lock", "w")
    try:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return PatchResult(False, "refused",
                               "Another Rekordbox patch is already in progress — wait for it to finish.")

        argvs = plan_codesign_argvs(app, ents_path)
        sign_argv = argvs[0]
        steps = [(sign_argv[-1], sign_argv)]

        admin_shell_runner = (
            run_shell_via_native_authorization
            if runner is run_via_native_authorization
            else run_shell_via_admin if runner is run_via_admin else None
        )
        if admin_shell_runner is not None:
            script = build_sign_script(steps)
            rc, err = admin_shell_runner(script)
            if rc != 0:
                if is_user_cancel(err):
                    # Operator dismissed the authorization prompt before the
                    # privileged signing script ran.
                    return PatchResult(False, "refused",
                                       "Cancelled — Rekordbox was not modified.",
                                       command=sign_argv, commands=argvs)
                component = parse_sign_fail_component(err) or str(app)
                detail = _codesign_fail_detail(err)
                detail_tail = f" Detail: {detail}" if detail else ""
                cmd_note = f" Failed command: {' '.join(sign_argv)}."
                am_hint = app_management_block_hint(err, app)
                am_tail = f" {am_hint}" if am_hint else ""
                failed = _failed_without_backup(
                    f"codesign failed on {component}.{cmd_note}{detail_tail}{am_tail}",
                    sign_argv, argvs,
                )
                return failed
        else:
            active_runner = runner or _default_runner
            rc, err = active_runner(sign_argv)
            if rc != 0:
                if is_user_cancel(err):
                    return PatchResult(False, "refused",
                                       "Cancelled — Rekordbox was not modified.",
                                       command=sign_argv, commands=argvs)
                hint = ""
                if "not permitted" in err.lower() or "permission denied" in err.lower():
                    hint = (" (needs admin — run with sudo, or use --admin / "
                            "the menubar which prompt for your password)")
                failed = _failed_without_backup(
                    f"codesign failed on {sign_argv[-1]}{hint}: {err.strip()}.",
                    sign_argv, argvs,
                )
                return failed

        # Verify the re-sign is structurally valid AND the entitlement took. (This
        # cannot prove Rekordbox LAUNCHES / that task_for_pid works — the operator
        # confirms that by relaunching Rekordbox.) The operator declined a
        # full-bundle backup, so failure reports are intentionally not recovery claims.
        try:
            verify = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(app)],
                capture_output=True, text=True, timeout=180,
                env=sanitized_system_env(os.environ),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            failed = _failed_without_backup(
                f"could not verify the re-sign ({exc}).", sign_argv, argvs)
            return failed
        if verify.returncode != 0:
            failed = _failed_without_backup(
                "the re-sign did not verify: " + verify.stderr.strip() + ".",
                sign_argv, argvs)
            return failed
        try:
            target_patched = has_get_task_allow(app)
        except EntitlementsReadError as exc:
            failed = _failed_without_backup(
                f"the re-sign could not be verified safely ({exc}).", sign_argv, argvs)
            return failed
        if not target_patched:
            failed = _failed_without_backup(
                "the re-sign succeeded but get-task-allow is still absent — "
                "no change took effect.", sign_argv, argvs)
            return failed
        return PatchResult(
            True, "patched",
            "Rekordbox target patched. RELAUNCH Rekordbox and confirm it opens. "
            "A positive get-task-allow check proves the target patch only; it "
            "does not prove a live attach. Stock foreign-Mac attach after "
            "patch + deep verify + GTA=true + relaunch is live-unvalidated / "
            "unknown. No full Rekordbox backup was created.",
            command=sign_argv, commands=argvs,
        )
    finally:
        lock_fh.close()  # releases the flock
        try:
            ents_path.unlink()
        except OSError:
            pass


# ── macOS GUI flow (menubar / frozen-app dispatch) ───────────────────────────

def _native_alert(message: str, buttons: tuple[str, ...]) -> str | None:
    """Show one native modal and return its button title.

    The frozen ``--patch-rekordbox`` child is itself a windowed app.  A bare
    ``osascript display dialog`` can fail before consent in that child, whereas
    the bundle already ships PyObjC/AppKit for its menubar.  Import lazily so
    headless patch/check paths never load AppKit.
    """
    from AppKit import (  # type: ignore
        NSAlert,
        NSAlertFirstButtonReturn,
        NSApplication,
        NSApplicationActivationPolicyRegular,
    )

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)
    alert = NSAlert.alloc().init()
    alert.setMessageText_("RBSS Bridge")
    alert.setInformativeText_(message)
    for button in buttons:
        alert.addButtonWithTitle_(button)
    index = int(alert.runModal()) - int(NSAlertFirstButtonReturn)
    return buttons[index] if 0 <= index < len(buttons) else None


def _gui_notify(message: str) -> None:
    try:
        _native_alert(message, ("OK",))
    except Exception:
        pass


def _gui_confirm(message: str) -> bool:
    try:
        # First/return-key button stays Cancel; only the explicit second choice signs.
        return _native_alert(message, ("Cancel", "Apply Patch")) == "Apply Patch"
    except Exception:
        return False


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
    result = apply_patch(app, dry_run=False, runner=run_via_native_authorization)
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
                    help="prompt for your admin password with native macOS authorization")
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
        result = apply_patch(
            app,
            dry_run=False,
            runner=(run_via_native_authorization if args.admin else None),
        )
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
