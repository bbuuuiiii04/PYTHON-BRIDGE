#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageLeft,
    NSMenu,
    NSMenuItem,
    NSMakeSize,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSAttributedString, NSMutableAttributedString, NSObject, NSTimer


REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHER = str(REPO_ROOT / "scripts" / "ss_bridge_watcher.sh")
# Single-instance guard is an exclusive flock on this file (see main()), NOT a
# pgrep on argv: the frozen bundle's argv is the .app binary path, which no
# source-run regex can match, and a source path is username-specific. flock keys
# on the file, so one guard covers both the frozen bundle and any source clone.
MENUBAR_LOCK_PATH = "/tmp/rb_ss_bridge_v2_menubar.lock"
# Where __main__._acquire_single_instance_lock writes the running bridge's pid.
# Lets a reopened frozen menubar re-adopt a bridge it has no Popen handle for
# (pgrep can't match a frozen bridge's argv).
BRIDGE_LOCK_PATH = "/tmp/rb_ss_bridge_v2.lock"
BRIDGE_PATTERN = r"^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$"
WATCHER_PATTERN = "^(/bin/bash|bash)[[:space:]]+" + WATCHER.replace(".", r"\.") + "$"
MONITOR_PATTERN = r"RBSS_BRIDGE_MONITOR|^tail -n 100 -F /tmp/bridge\.log$"
MANUAL_LAUNCHCTL_LABEL = "rbss_bridge_manual"
STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"
COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
LASER_PAD_PORT = 8765
LED_PAD_PORT = 8766
LASER_PAD_URL = f"http://127.0.0.1:{LASER_PAD_PORT}"
LED_PAD_URL = f"http://127.0.0.1:{LED_PAD_PORT}"
RECORDING_PATH_TEMPLATE = "/tmp/rbss-session-{stamp}.jsonl"
EXPORT_PROCESS_TIMEOUT_SECONDS = 120.0
EXPORT_RELOAD_TIMEOUT_SECONDS = 8.0
EXPORT_RELOAD_POLL_SECONDS = 0.25
EXPORT_WORKING_DIRECTORY = str(Path(__file__).resolve().parents[2])
CANONICAL_SOURCE_PROJECT = str(Path("~/Music/SoundSwitch/default.ssproj").expanduser())
CANONICAL_PACK_DIR = REPO_ROOT / "local" / "soundswitch" / "rbss_canonical_pack"
DETECT_MAX_AGE_SECONDS = 30.0
_SIDECAR_SUFFIX = ".source.json"

# Menubar status icons ship WITH the app so a guest Mac (or any non-maintainer
# clone) has them. Frozen: PyInstaller unpacks spec datas under sys._MEIPASS at
# the same rb_ss_bridge_v2/scripts/icons layout. Source: next to this file.
if getattr(sys, "frozen", False):
    ICON_DIR = Path(sys._MEIPASS) / "rb_ss_bridge_v2" / "scripts" / "icons"
else:
    ICON_DIR = Path(__file__).resolve().parent / "icons"
ICONS = {
    "off": str(ICON_DIR / "bridge_icon_off.png"),
    "initializing": str(ICON_DIR / "bridge_icon_initializing.png"),
    "on": str(ICON_DIR / "bridge_icon_on.png"),
}


_FONT_SZ = 13.0
_FONT_NORM = None   # resolved lazily
_FONT_BOLD = None


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


def current_generator_commit() -> str | None:
    repo = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip().lower()
    if (
        out.returncode != 0
        or len(commit) != 40
        or any(c not in "0123456789abcdef" for c in commit)
    ):
        return None
    return commit


def read_source_sidecar() -> dict | None:
    try:
        with open(_sidecar_path(CANONICAL_PACK_DIR), "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def detect_export_state() -> str:
    """Returns "up_to_date" only with exact positive proof; else "changes"."""
    pack = CANONICAL_PACK_DIR
    if pack.is_symlink() or not pack.is_dir():
        return "changes"
    sidecar = read_source_sidecar()
    if not sidecar:
        return "changes"
    raw_ignore = sidecar.get("ignored_paths")
    ignore = frozenset(
        p for p in raw_ignore
        if isinstance(p, str) and not p.startswith("recordable/")
    ) \
        if isinstance(raw_ignore, list) else frozenset()
    current = _source_content_fingerprint(CANONICAL_SOURCE_PROJECT, ignore=ignore)
    if current is None or current != sidecar.get("source_fingerprint"):
        return "changes"
    # ponytail: up-to-date is keyed purely on SoundSwitch source content. The
    # old git-commit guard un-greyed the button on every unrelated bridge
    # commit (auto-sync moves HEAD each turn) even when SoundSwitch was
    # unchanged. Re-add a generator-version guard only if a pack-format change
    # ever needs to force re-export.
    return "up_to_date"


def _fonts():
    global _FONT_NORM, _FONT_BOLD
    if _FONT_NORM is None:
        _FONT_NORM = NSFont.menuFontOfSize_(_FONT_SZ)
        _FONT_BOLD = NSFont.boldSystemFontOfSize_(_FONT_SZ)
    return _FONT_NORM, _FONT_BOLD


def _seg(text: str, *, bold: bool = False, color=None) -> NSAttributedString:
    norm, bold_font = _fonts()
    attrs: dict = {NSFontAttributeName: bold_font if bold else norm}
    if color is not None:
        attrs[NSForegroundColorAttributeName] = color
    return NSAttributedString.alloc().initWithString_attributes_(text, attrs)


def _join(*parts) -> NSMutableAttributedString:
    out = NSMutableAttributedString.alloc().init()
    for p in parts:
        out.appendAttributedString_(p)
    return out


def _cg():   return NSColor.systemGreenColor()
def _co():   return NSColor.systemOrangeColor()
def _cr():   return NSColor.systemRedColor()
def _cs():   return NSColor.secondaryLabelColor()
def _cb():   return NSColor.colorWithSRGBRed_green_blue_alpha_(0.22, 0.44, 0.72, 1.0)  # light navy
def _cp():   return NSColor.systemPurpleColor()                                          # scripted
def _cl():   return NSColor.colorWithSRGBRed_green_blue_alpha_(0.38, 0.68, 1.0, 1.0)   # light blue autoloop


_MENUBAR_LOCK_FD = None


def acquire_menubar_lock(path: str = MENUBAR_LOCK_PATH) -> bool:
    """Return False when another menubar already holds the exclusive lock.

    Mirrors __main__._acquire_single_instance_lock exactly: an flock on a fixed
    file, keyed on the file rather than argv, so ONE guard fires for the frozen
    bundle (whose argv is the .app binary) and any source clone alike. The fd is
    stashed in a module global so the lock is held for the whole process and only
    released when the menubar exits.
    """
    global _MENUBAR_LOCK_FD
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        # Can't create the lockfile (unwritable /tmp, or a pre-existing one owned
        # by another macOS user). Fail OPEN — never block the menubar from starting
        # over a lock-file quirk; a rare double menubar beats no menubar.
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode("ascii"))
    _MENUBAR_LOCK_FD = fd
    return True


def watcher_running() -> bool:
    result = subprocess.run(["pgrep", "-f", WATCHER_PATTERN], capture_output=True)
    return result.returncode == 0


def bridge_pids() -> list[str]:
    result = subprocess.run(["pgrep", "-f", BRIDGE_PATTERN], capture_output=True, text=True)
    return [pid for pid in result.stdout.strip().splitlines() if pid]


def _running_bridge_pid(path: str = BRIDGE_LOCK_PATH) -> int | None:
    """The pid of a live bridge holding the single-instance lock, or None.

    Reads the pid __main__ wrote into the lockfile, then proves it is (a) alive
    (os.kill 0) and (b) actually a bridge (its argv names the package + a run
    mode) — so a reopened frozen menubar can re-adopt a bridge it has no Popen
    handle for, and never SIGTERMs a recycled/foreign pid. A stale lockfile whose
    pid is dead or reused returns None. The flock remains the single source of
    truth for 'exactly one bridge'; this only READS who holds it."""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            pid = int(fp.readline().strip())
    except (OSError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)  # liveness probe only; signal 0 never touches the process
    except OSError:
        return None
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "rb_ss_bridge_v2" in out and ("--run-bridge" in out or "-m rb_ss_bridge_v2" in out):
        return pid
    return None


def bridge_status() -> str:
    return _bridge_status_from_pids(bridge_pids())


def _bridge_status_from_pids(pids: list[str]) -> str:
    if pids:
        return "on"
    if watcher_running():
        return "initializing"
    return "off"


def launchctl_domain() -> str:
    return f"gui/{os.getuid()}/{MANUAL_LAUNCHCTL_LABEL}"


def stop_manual_launchctl_job() -> None:
    subprocess.run(
        ["launchctl", "bootout", launchctl_domain()],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def close_monitor() -> None:
    subprocess.run(["pkill", "-f", MONITOR_PATTERN])
    subprocess.run(
        [
            "osascript",
            "-e", 'tell application "Terminal"',
            "-e", "repeat",
            "-e", "set closedTab to false",
            "-e", "repeat with w in windows",
            "-e", "repeat with t in tabs of w",
            "-e", 'if custom title of t is "RBSS_BRIDGE_MONITOR" then',
            "-e", "close t",
            "-e", "set closedTab to true",
            "-e", "exit repeat",
            "-e", "end if",
            "-e", "end repeat",
            "-e", "if closedTab then exit repeat",
            "-e", "end repeat",
            "-e", "if not closedTab then exit repeat",
            "-e", "end repeat",
            "-e", "end tell",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def read_status() -> dict:
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return {}
    age = time.time() - float(data.get("written_at", 0.0))
    if age > 3.0:
        data["stale"] = True
        data["stale_age_s"] = int(age)
    return data


def append_command(command: dict) -> None:
    line = json.dumps(command, sort_keys=True) + "\n"
    fd = os.open(COMMANDS_PATH, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(COMMANDS_PATH, 0o600)
    except OSError:
        pass


def build_export_argv(result_path: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "rb_ss_bridge_v2.tools.export_soundswitch_pack",
        "--publish-canonical",
        "--result-json",
        result_path,
    ]


def _safe_error_category(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "UnknownError"
    if (
        not value.isascii()
        or not value.replace("_", "a").isalnum()
        or not (value[0].isalpha() or value[0] == "_")
    ):
        return "UnknownError"
    return value


def parse_export_result(text: str) -> dict:
    fallback = {"ok": False, "verdict": "unknown_error"}
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return fallback
    if not isinstance(value, dict) or type(value.get("ok")) is not bool:
        return fallback
    allowed_verdicts = {
        "published", "source_error", "verify_failed", "locked", "swap_failed", "unknown_error",
        "sidecar_failed",
    }
    verdict = value.get("verdict")
    manifest_sha256 = value.get("manifest_sha256")
    artifact_count = value.get("artifact_count")
    first_export = value.get("first_export")
    error_category = value.get("error_category")
    if verdict not in allowed_verdicts:
        return fallback
    if not isinstance(manifest_sha256, str):
        return fallback
    if value["ok"] and (
        len(manifest_sha256) != 64
        or any(char not in "0123456789abcdef" for char in manifest_sha256)
        or verdict != "published"
    ):
        return fallback
    if type(artifact_count) is not int or artifact_count < 0:
        return fallback
    if type(first_export) is not bool or not isinstance(error_category, str):
        return fallback
    return {
        "ok": value["ok"],
        "verdict": verdict,
        "manifest_sha256": manifest_sha256,
        "artifact_count": artifact_count,
        "first_export": first_export,
        "error_category": "" if value["ok"] else _safe_error_category(error_category),
    }


def evaluate_reload_ack(status: dict, expected_sha12: str) -> str:
    if not isinstance(status, dict) or not status or status.get("stale"):
        return "stale"
    pack = status.get("soundswitch_pack")
    if not isinstance(pack, dict) or not bool(pack.get("enabled")):
        return "not_live"
    if pack.get("pack_sha12") == expected_sha12:
        return "succeeded"
    return "pending"


def export_button_text(in_progress: bool, up_to_date: bool) -> str:
    if in_progress:
        return "Exporting…"
    if up_to_date:
        return "Exported"
    return "Export"


def export_button_enabled(in_progress: bool, up_to_date: bool, frozen: bool) -> bool:
    """Export is a maintainer authoring step: it needs the SoundSwitch source
    project on disk and the `-m` export tool, neither of which a frozen guest
    bundle has (a frozen click would only hit usb_launcher's unknown-mode exit).
    So the button is actionable only on a source run that has real changes."""
    return not in_progress and not up_to_date and not frozen


def _artnet_exam_active(status: dict) -> bool:
    # DualTriggerBackend (artnet_truth_check startup only) is the sole source of
    # "midi_link" in the executor's midi status; it's wired once at bridge boot
    # and untouched by pack enable/disable swaps, so it survives the very
    # auto-disable this function needs to detect and skip.
    midi = status.get("laser_director", {}).get("executor", {}).get("midi", {})
    return isinstance(midi, dict) and "midi_link" in midi


def pack_auto_command(status: dict, *, bridge_status: str | None = None) -> dict | None:
    if bridge_status != "on" or not isinstance(status, dict) or not status or status.get("stale"):
        return None
    soundswitch = status.get("soundswitch", {})
    pack = status.get("soundswitch_pack", {})
    if not isinstance(soundswitch, dict) or not isinstance(pack, dict):
        return None
    connected = soundswitch.get("connected")
    if type(connected) is not bool:
        return None
    if not pack.get("available") or pack.get("reason") == "not_configured":
        return None
    if _artnet_exam_active(status):
        return None
    enabled = bool(pack.get("enabled"))
    desired = not connected
    if enabled == desired:
        return None
    return {"cmd": "set_soundswitch_pack", "action": "enable", "enabled": desired}


def _led_color_engine_status(status: dict) -> dict:
    # The status file nests the engine snapshot under state_manager (that is where
    # runtime_status writes it); older shapes carried it at the top level. Read the
    # real nested path first, fall back to top level so both shapes resolve.
    if not isinstance(status, dict):
        return {}
    sm = status.get("state_manager")
    if isinstance(sm, dict) and isinstance(sm.get("led_color_engine"), dict):
        return sm["led_color_engine"]
    color = status.get("led_color_engine")
    return color if isinstance(color, dict) else {}


def led_engine_v2_available(status: dict) -> bool:
    return "engine" in _led_color_engine_status(status)


def led_engine_v2_enabled(status: dict) -> bool:
    return _led_color_engine_status(status).get("engine") == "v2"


def led_engine_v2_command(status: dict) -> dict:
    return {
        "cmd": "led_engine",
        "mode": "v1" if led_engine_v2_enabled(status) else "v2",
    }


def export_result_line(state: str, result: dict | None = None) -> str:
    result = result or {}
    return {
        "published_not_live": "  saved (loads when pack enabled)",
        "reload_succeeded": "  live now",
        "reload_failed": "  saved — live reload not confirmed",
        "export_failed": f"  export failed ({_safe_error_category(result.get('error_category'))})",
    }.get(state, "")


def pack_export_status_line(
    pack_status: dict,
    *,
    stale: bool,
    export_phase: str,
    export_state: str,
    export_up_to_date: bool,
    export_result: dict | None = None,
    bridge_status: str | None = None,
    soundswitch_connected: bool | None = None,
) -> str:
    """Plain-language line under the Export button: what the lighting pack is
    doing live, plus only the export feedback the button can't show."""
    if bridge_status == "off":
        return "Lighting: bridge off"
    if stale:
        return "Lighting: no status yet"
    pack = pack_status if isinstance(pack_status, dict) else {}
    light_label = {
        "disabled": "pack off",
        "blackout": "blackout",
        "input_degraded": "input degraded",
        "static_held": "holding static",
        "scripted_active": "scripted active",
        "rendering_active": "native autoloop",
        "empty_dark_look": "native dark",
        "base_suppressed": "native dark",
        "missing_binding": "autoloop missing binding",
        "missing_autoloop_file": "autoloop file missing",
        "unsupported_layout": "autoloop unsupported",
        "unverified_parity": "unverified parity",
        "soundswitch_present_native_suppressed": "SoundSwitch owns lights",
        "autoloop_phase_blocked": "autoloop blocked",
        "software_zero_frame": "zeroed",
    }.get(pack.get("operational_state"), "unknown")
    if pack.get("unverified_parity_count"):
        light_label = "unverified parity"
    if pack.get("static_binding_gap"):
        light_label = "static binding gap"
    # Steady Exported / Ready-to-export is already on the button; only surface
    # progress, failure, or a save/reload result the button can't convey.
    note = ""
    if export_phase == "exporting":
        note = "exporting…"
    elif export_phase == "reloading":
        note = "reloading…"
    elif export_state == "published_not_live":
        note = "saved — enable pack to go live"
    elif export_state == "reload_succeeded":
        note = "live now"
    elif export_state == "reload_failed":
        note = "saved — reload unconfirmed"
    elif export_state == "export_failed":
        category = _safe_error_category((export_result or {}).get("error_category"))[:32]
        note = f"export failed ({category})"
    # Why the pack is off. With SoundSwitch connected, off is the INTENDED state —
    # SS holds the shared Enttec FTDI port, so a boot-time "pack_start_failed" there is
    # the expected handoff, NOT a fault. Only when SS is disconnected (the bridge was
    # meant to own the port) does a failure reason mean "check the rig".
    if not note and light_label == "pack off":
        if soundswitch_connected:
            note = "SoundSwitch active"
        else:
            note = {
                "pack_load_failed": "pack unreadable — re-export",
                "pack_start_failed": "output didn't start (check Enttec)",
            }.get(pack.get("reason"), "")
    line = f"Lighting: {light_label}"
    if note:
        line = f"{line} · {note}"
    return line[:80]


def _export_failure_result(exc: Exception) -> dict:
    return {
        "ok": False,
        "verdict": "unknown_error",
        "manifest_sha256": "",
        "artifact_count": 0,
        "first_export": False,
        "error_category": _safe_error_category(type(exc).__name__),
    }


def open_terminal_command(command: str, title: str = "RBSS_TERMINAL") -> None:
    safe_cmd = command.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Terminal" to activate\n'
        f'tell application "Terminal" to do script "{safe_cmd}"'
    )
    subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_browser_url(url: str) -> None:
    subprocess.run(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _system_env() -> dict:
    """os.environ with PyInstaller's bundle DYLD_* pollution undone, for spawning
    children/system tools. Reuses the one sanitizer in rekordbox_patch; falls back
    to a plain copy if that import isn't resolvable (bare-import contexts)."""
    try:
        from rb_ss_bridge_v2.rekordbox_patch import sanitized_system_env
        return sanitized_system_env(os.environ)
    except Exception:
        return dict(os.environ)


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    """True if something is already listening on host:port (the pad server)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def laser_pad_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-laser-pad"]
    return [sys.executable, str(REPO_ROOT / "scripts" / "laser_pad.py")]


def led_pad_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-led-pad"]
    return [sys.executable, str(REPO_ROOT / "scripts" / "led_pad.py")]


def open_pad(url: str, port: int, argv: list[str]) -> None:
    """Bring the pad server up if it isn't already, then open it in the browser.

    The pad web servers are standalone processes nothing else starts, so on a
    guest Mac (or a fresh launch) 'open <url>' would land on connection-refused.
    Spawn one (detached, its own port is the doubles guard) and wait briefly for
    the port before opening, so the browser sees a live server."""
    up = _port_open(port)
    if not up:
        subprocess.Popen(argv, start_new_session=True, env=_system_env())
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if _port_open(port):
                up = True
                break
            time.sleep(0.1)
    if not up:
        # Never open a dead loopback URL — say so instead of a silent no-op.
        _notify("The pad didn't start — try again in a moment, or check the logs.")
        return
    open_browser_url(url)


def _is_user_cancel(stderr: str) -> bool:
    """True when an osascript admin escalation was cancelled by the operator.

    The patch_rekordbox helper captures osascript stderr internally and exits 1
    with empty stderr on both consent-cancel and admin-password-cancel, so this
    branch is presently unreachable for that child — kept for future helpers that
    surface cancel text on stderr."""
    s = (stderr or "").lower()
    return "user canceled" in s or "user cancelled" in s or "(-128)" in s


def _format_child_failure(label: str, returncode: int, stderr_tail: str) -> str:
    """Plain-language dialog text when a spawned child dies at startup (pure seam
    for the frozen bridge / rekordbox-patch spawns, which otherwise fail silent)."""
    what = {
        "frozen_bridge_start": "The bridge couldn't start",
        "patch_rekordbox": "Enabling Rekordbox reads didn't start",
    }.get(label, "A helper process didn't start")
    tail = (stderr_tail or "").strip()
    if len(tail) > 600:
        tail = "…" + tail[-600:]
    detail = f"It exited with code {returncode}."
    if tail:
        detail += f"\n\n{tail}"
    return f"{what}. {detail}"


def _child_error_log_dir() -> Path:
    """Where spawned children's stderr is captured (same tree as bridge logs)."""
    runtime = os.environ.get("RBSS_RUNTIME_DIR")
    base = Path(runtime) / "logs" if runtime else Path.home() / "Library" / "Logs" / "rb_ss_bridge"
    return base


def default_recording_path() -> str:
    return RECORDING_PATH_TEMPLATE.format(stamp=time.strftime("%Y%m%d-%H%M%S"))


def newest_recorded_session() -> str | None:
    import glob

    files = sorted(glob.glob(RECORDING_PATH_TEMPLATE.format(stamp="*")))
    return files[-1] if files else None


def rekordbox_running() -> bool:
    # Same canonical check the watcher uses (pgrep -x rekordbox); replay must
    # never run against live decks.
    return subprocess.run(["pgrep", "-x", "rekordbox"], capture_output=True).returncode == 0


def _notify(message: str) -> None:
    # Reuse osascript (already this file's dialog mechanism) for a visible,
    # non-blocking heads-up without pulling in more AppKit surface.
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification {json.dumps(message)} with title "RBSS Bridge"'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        pass


def recording_status_from_snapshot(status: dict) -> dict:
    sm = status.get("state_manager") or {}
    rec = sm.get("recording") or {}
    if not isinstance(rec, dict):
        return {"active": False, "path": ""}
    return rec


def compact_status_lines(status: dict, pids: list[str] | None = None) -> list:
    pids = pids or []
    _dash = _seg("  —", color=_cs())

    if not status or status.get("stale"):
        age_s = status.get("stale_age_s", 0) if status else 0
        age_str = f"{age_s}s stale" if age_s else "no snapshot"
        return [
            _join(_seg("⊘  ", color=_co()), _seg("BRIDGE", bold=True), _seg(f"  {age_str}", color=_co())),
            _join(_seg("  SS  ", color=_cs()), _seg("Unknown", color=_cs())),
            _join(_seg("■ ", color=_cs()), _seg("D1", bold=True), _dash),
            _join(_seg("  └  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("■ ", color=_cs()), _seg("D2", bold=True), _dash),
            _join(_seg("  └  ", color=_cs()), _seg("—", color=_cs())),
            _seg("  Checks  —", color=_cs()),
            _join(_seg("  Smart Phrasing  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("  Lasers  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("  LEDs  ", color=_cs()), _seg("—", color=_cs())),
        ]

    sm = status.get("state_manager", {})
    ss = status.get("soundswitch", {})
    validation = status.get("validation", {})
    laser = status.get("laser_director", {})
    active = str(sm.get("active_deck", "?"))
    mode = sm.get("lighting_mode", "idle")
    decks = sm.get("deck", {})
    smart_drop_on = bool(sm.get("smart_drop_enabled"))
    smart_breakdown_on = bool(sm.get("smart_breakdown_enabled"))

    # Row 0: bridge header
    multi_seg = _seg(f"  ⚠ {len(pids)} procs", color=_co()) if len(pids) > 1 else _seg("")
    # Surface the ONE reliable make-or-break (P1 diagnosability): the bridge can't
    # read Rekordbox on this Mac (authorization denied). No extra row (the 10-row zip
    # contract holds); it rides on the BRIDGE line. We deliberately do NOT warn on
    # 'unsupported_version' (deck reads use a version-robust ObjC scan that doesn't
    # need the offset table, so it would false-alarm on an RB upgrade) or on a
    # transient 'attach_failed'; both still ride in the status JSON for diagnostics.
    rb = status.get("rekordbox", {})
    rb_reason = rb.get("reason") if isinstance(rb, dict) else ""
    rb_warn_text = "  ⚠ RB reads blocked" if rb_reason == "reads_blocked" else ""
    bridge_row = _join(
        _seg("●  ", color=_cg()),
        _seg("BRIDGE", bold=True),
        _seg(f"  D{active} Active", color=_cs()),
        multi_seg,
        _seg(rb_warn_text, color=_cr()) if rb_warn_text else _seg(""),
    )

    # Row 1: SoundSwitch
    ss_ok = ss.get("connected")
    ss_row = _join(
        _seg("  SS  ", color=_cb()),
        _seg("✓" if ss_ok else "✗", color=_cg() if ss_ok else _cr()),
    )

    # Rows 2–5: two deck pairs (header + track)
    mode_map = {"autoloop": "Autoloop", "scripted": "Scripted", "idle": "Idle"}
    deck_rows = []
    for deck in ("1", "2"):
        d = decks.get(deck, {})
        runtime = status.get("deck_runtime", {}).get(deck, {})
        is_active = active == deck
        playing = d.get("playing")

        play_sym = "▶" if playing else "■"
        play_color = _cg() if playing else _cs()
        d_color = _co() if is_active else None

        live = runtime.get("live_bpm") or {}
        bpm_str = f"  {live['bpm']:.1f} BPM" if live.get("bpm") else "  — BPM"

        if is_active:
            ml = mode_map.get(str(mode), str(mode).title()[:10])
            ml_color = _cl() if ml == "Autoloop" else (_cp() if ml == "Scripted" else _cs())
        else:
            ml = "—"
            ml_color = _cs()

        name = Path(d.get("filepath") or "").name or "—"
        if len(name) > 30:
            name = name[:27] + "…"

        header = _join(
            _seg(f"{play_sym} ", color=play_color),
            _seg(f"D{deck}", bold=True, color=d_color),
            _seg(bpm_str, color=_cs()),
            _seg(f"   {ml}", color=ml_color),
        )
        track = _join(
            _seg("  └  ", color=_cs()),
            _seg(name, color=_cs()),
        )
        deck_rows.extend([header, track])

    # Row 6: checks
    pass_c = validation.get("pass_count", 0)
    warn_c = validation.get("warn_count", 0)
    fail_c = validation.get("fail_count", 0)
    issue = validation.get("latest_issue") or ""
    if len(issue) > 26:
        issue = issue[:23] + "…"
    check_color = _cr() if fail_c else (_co() if warn_c else _cs())
    checks_row = _join(
        _seg("  Checks  ", color=_cs()),
        _seg(validation.get("state", "idle").title(), color=check_color),
        _seg(f"   {pass_c}P {warn_c}W {fail_c}F", color=_cs()),
        _seg(f"   {issue}", color=_co()) if issue else _seg(""),
    )

    # Row 7: smart phrasing
    sd_txt = "On" if smart_drop_on else "Off"
    sd_col = _cg() if smart_drop_on else _cs()
    sb_txt = "On" if smart_breakdown_on else "Off"
    sb_col = _cg() if smart_breakdown_on else _cs()
    
    smart_row = _join(
        _seg("  Smart Phrasing  ", color=_cs()),
        _seg(f"Drops: {sd_txt}", color=sd_col),
        _seg("  |  ", color=_cs()),
        _seg(f"Breakdowns: {sb_txt}", color=sb_col),
    )

    laser_available = bool(laser.get("available"))
    laser_enabled = bool(laser.get("enabled"))
    laser_emergency = bool(laser.get("emergency"))
    laser_scene = str(laser.get("current_scene") or "—")
    laser_reason = str(laser.get("last_reason") or "—")
    executor = laser.get("executor") or {}
    midi = executor.get("midi") or {}
    queue_size = int(midi.get("queue_size", 0) or 0)
    queue_max = int(midi.get("queue_max", 0) or 0)
    drop_count = int(midi.get("drop_count", 0) or 0)
    degraded_reason = str(midi.get("degraded_reason") or "")

    if not laser_available:
        laser_txt = "—"
        laser_col = _cs()
    elif laser_emergency:
        laser_txt = "BLACKOUT"
        laser_col = _cr()
    elif laser_enabled and not degraded_reason:
        laser_txt = "On"
        laser_col = _cg()
    elif laser_enabled:
        laser_txt = "On"
        laser_col = _co()
    else:
        laser_txt = "Off"
        laser_col = _cs()

    if len(laser_scene) > 18:
        laser_scene = laser_scene[:15] + "..."
    if len(laser_reason) > 18:
        laser_reason = laser_reason[:15] + "..."

    laser_row = _join(
        _seg("  Lasers  ", color=_cs()),
        _seg(laser_txt, color=laser_col),
        _seg(f"  scene={laser_scene}", color=_cs()),
        _seg(f"  reason={laser_reason}", color=_cs()),
        _seg(f"  midi={queue_size}/{queue_max} drops={drop_count}", color=_cs()),
        _seg(f"  {degraded_reason[:14]}", color=_co()) if degraded_reason else _seg(""),
    )

    # Row 9: LEDs glance (AWR-192) — same shape discipline as the laser row.
    led_fields = led_row_fields(status)
    led_state = led_fields["state"]
    led_degraded = led_fields["degraded_reason"]
    if led_state == "on":
        led_txt = "On"
        led_col = _co() if led_degraded else _cg()
    elif led_state == "off":
        led_txt = "Off"
        led_col = _cs()
    else:
        led_txt = "—"
        led_col = _cs()

    led_segs = [_seg("  LEDs  ", color=_cs()), _seg(led_txt, color=led_col)]
    if led_state == "on":
        led_fps = led_fields["fps"]
        if led_fps is not None:
            led_segs.append(_seg(f"  {led_fps:.0f}fps", color=_cs()))
        led_effect = led_fields["effect"]
        if led_effect:
            if len(led_effect) > 18:
                led_effect = led_effect[:15] + "..."
            led_segs.append(_seg(f"  {led_effect}", color=_cs()))
        led_palette = led_fields["palette"]
        if led_palette:
            if len(led_palette) > 18:
                led_palette = led_palette[:15] + "..."
            led_segs.append(_seg(f"  {led_palette}", color=_cs()))
    led_segs.append(
        _seg(f"  {led_degraded[:14]}", color=_co()) if led_degraded else _seg("")
    )
    led_row = _join(*led_segs)

    return [bridge_row, ss_row] + deck_rows + [checks_row, smart_row, laser_row, led_row]


def _phrasing_summary(sp_block: dict | None) -> str:
    if not sp_block:
        return "Phrasing: —"
    phrase = str(sp_block.get("phrase_label") or "other")
    next_drop = sp_block.get("next_smart_drop_beat")
    beats_to_drop = sp_block.get("beats_to_next_drop")
    anchor = sp_block.get("phrase_anchor_target_beat")
    next_drop_txt = "-" if next_drop is None else str(int(next_drop))
    if beats_to_drop is None:
        in_txt = "-"
    else:
        in_txt = str(int(round(float(beats_to_drop))))
    anchor_txt = "-" if anchor is None else str(int(anchor))
    return f"Phrasing: {phrase}  next_drop={next_drop_txt}  in={in_txt}b  anchor={anchor_txt}"


def led_row_fields(status: dict) -> dict:
    """Glance fields for the LEDs status row; every field degrades to a
    safe default when absent (director off, bridge starting, stale)."""
    led = status.get("led_look_director") if isinstance(status, dict) else None
    if isinstance(led, dict):
        state = "on" if led.get("enabled") else "off"
    else:
        led = {}
        state = "unknown"
    adapter = led.get("adapter")
    if not isinstance(adapter, dict):
        adapter = {}
    realtime = adapter.get("realtime")
    if not isinstance(realtime, dict):
        realtime = {}
    fps = None
    if realtime.get("active"):
        raw_fps = realtime.get("achieved_fps")
        if isinstance(raw_fps, (int, float)) and not isinstance(raw_fps, bool):
            fps = float(raw_fps)
    effect = realtime.get("active_effect")
    if not isinstance(effect, str):
        effect = ""
    palette = _led_color_engine_status(status).get("current_palette")
    if not isinstance(palette, str):
        palette = ""
    degraded_reason = ""
    if adapter.get("degraded"):
        raw_reason = adapter.get("degraded_reason")
        if isinstance(raw_reason, str):
            degraded_reason = raw_reason
    return {
        "state": state,
        "fps": fps,
        "effect": effect,
        "palette": palette,
        "degraded_reason": degraded_reason,
    }


# (kind, attr, title, selector) — kind: "status_rows" | "sep" | "action" | "info" | "submenu"
# "submenu" carries a nested tuple of entries in slot 4.
# AWR-192 layout: status glance → bridge toggle → LIVE block → AUTHORING +
# CHECKS block → MAINTENANCE block. Pure data; the builder in
# BridgeMenuBar._build_menu_entry walks it.
MENU_BLUEPRINT: tuple = (
    ("status_rows", "status_rows", 10, None),
    ("sep", None, None, None),
    ("action", "toggle_item", "", "toggleBridge:"),  # title set by refresh_
    ("sep", None, None, None),  # LIVE block
    ("action", "laser_blackout_item", "Laser Blackout", "laserBlackout:"),
    ("action", "laser_clear_blackout_item", "Clear Laser Blackout", "laserClearBlackout:"),
    ("submenu", "smart_phrasing_item", "Smart Phrasing", None, (
        ("action", "smart_drop_item", "Smart Drops", "toggleSmartDrop:"),
        ("action", "smart_breakdown_item", "Smart Breakdowns", "toggleSmartBreakdown:"),
    )),
    ("submenu", "laser_item", "Laser Director", None, (
        ("action", "laser_toggle_item", "Laser Director", "toggleLaserDirector:"),
        ("sep", None, None, None),
        ("info", "laser_scene_item", "", None),
        ("info", "laser_reason_item", "", None),
        ("info", "laser_personality_item", "", None),
        ("info", "laser_midi_item", "", None),
        ("info", "laser_phrasing_item", "", None),
    )),
    # TEMPORARY (v2 rollout): remove after v2 color identity is the default operator surface.
    ("action", "led_engine_v2_item", "LED Engine v2", "toggleLedEngineV2:"),
    ("action", "map_lasers_item", "Laser Pad…", "mapLasers:"),
    ("action", "led_pad_item", "LED Pad…", "openLedPad:"),
    ("sep", None, None, None),  # AUTHORING + CHECKS block
    ("action", "export_item", "Export", "exportFromSS:"),
    ("info", "export_status_item", "", None),
    ("action", "record_session_item", "Record Session: Off", "toggleRecordSession:"),
    ("action", "test_lights_item", "Test the Lights…", "testLights:"),
    ("action", "validation_item", "Run Health Check", "runValidation:"),
    ("action", "enable_rb_reads_item", "Enable Rekordbox Reads…", "enableRekordboxReads:"),
    ("sep", None, None, None),  # MAINTENANCE block
    # AWR-186 M2 SLOT: purge item — function owned by the usbm2 round;
    # structure only. Frozen-gated at build time (m2_offer); when the gate is
    # closed the attr stays None, exactly as M2 shipped it. The install offer
    # is NOT here: per the M2 spec it is primary-positioned (inserted at menu
    # index 0 + separator, after the blueprint walk) on DMG-guest runs.
    ("action", "purge_item", "Purge RBSS Bridge…", "purgeBridge:"),
    ("action", "quit_item", "Quit Menubar (bridge keeps running)", "quit:"),
)


class BridgeMenuBar(NSObject):
    def init(self):
        self = objc.super(BridgeMenuBar, self).init()
        if self is None:
            return None
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.menu = NSMenu.alloc().init()
        # Honor our own setEnabled_ calls (e.g. greying the Export button when
        # up-to-date). Default autoenablesItems=True makes AppKit force-enable
        # any item with an action, silently ignoring setEnabled_(False).
        self.menu.setAutoenablesItems_(False)
        self._export_in_progress = False
        self._export_phase = "idle"
        self._export_state = "idle"
        self._export_result = {}
        self._export_up_to_date = False
        self._detect_in_progress = False
        self._detect_sig = None
        self._detect_at = 0.0
        self._detect_generation = 0
        self._pack_auto_pending_enabled = None
        self._pack_auto_retried_enabled = None
        # Native install offer + purge (AWR-186 M2) — frozen runs only, so
        # source-run menubars never import install_controller and stay
        # byte-identical. Install offered only when running from the DMG/
        # translocation with no manifest; purge only on installed copies.
        # AWR-192 moved WHERE the items sit (MENU_BLUEPRINT maintenance slot);
        # the gating below and the handlers are M2's, verbatim.
        self.install_item = None
        self.purge_item = None
        self._install_in_progress = False
        self._purge_in_progress = False
        offer_install = False
        m2_offer = {"purge_item": False}
        if getattr(sys, "frozen", False):
            from rb_ss_bridge_v2.install_controller import (
                APP_SUPPORT_DIR,
                MANIFEST_NAME,
                bundle_root,
                running_from_read_only_location,
                should_offer_install,
            )

            bundle = bundle_root(sys.executable)
            manifest_exists = (APP_SUPPORT_DIR / MANIFEST_NAME).exists()
            offer_install = bool(should_offer_install(bundle, manifest_exists))
            # PURGE (AWR-186 Task 4): installed copies only — manifest present
            # and not running from the DMG/translocation.
            m2_offer["purge_item"] = bool(
                manifest_exists
                and bundle is not None
                and not running_from_read_only_location(bundle)
            )

        self.status_rows = []
        for entry in MENU_BLUEPRINT:
            self._build_menu_entry(self.menu, entry, m2_offer)
        # Install offer stays the PRIMARY item on DMG-guest runs (M2 spec Task
        # 2): inserted at the very top, above the status rows — M2's original
        # mechanism verbatim, not a blueprint slot.
        if offer_install:
            self.install_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Install on this Mac…", "installOnMac:", ""
            )
            self.install_item.setTarget_(self)
            self.menu.insertItem_atIndex_(self.install_item, 0)
            self.menu.insertItem_atIndex_(NSMenuItem.separatorItem(), 1)
        self.status_item.setMenu_(self.menu)
        self._status = None
        self._snapshot = {}
        self._timer_interval = 1.0
        self._timer = None
        self.refresh_(None)
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self._timer_interval, self, "refresh:", None, True
        )
        return self

    def _add_action(self, title: str, selector: str):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setTarget_(self)
        self.menu.addItem_(item)
        return item

    def _build_menu_entry(self, menu, entry, m2_offer):
        """Materialize one MENU_BLUEPRINT entry into `menu` (AWR-192).

        Reproduces the pre-blueprint per-item mechanics exactly: _add_action
        for top-level actions, disabled no-action items for info rows,
        setSubmenu_ for submenus, setattr for every named entry.
        """
        kind, attr, title, selector = entry[0], entry[1], entry[2], entry[3]
        if kind == "sep":
            menu.addItem_(NSMenuItem.separatorItem())
        elif kind == "status_rows":
            for _ in range(title):
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
                item.setEnabled_(False)
                menu.addItem_(item)
                self.status_rows.append(item)
        elif kind == "submenu":
            submenu = NSMenu.alloc().init()
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            item.setSubmenu_(submenu)
            menu.addItem_(item)
            setattr(self, attr, item)
            # smart_phrasing_item -> smart_phrasing_menu, laser_item -> laser_menu
            setattr(self, attr.replace("_item", "_menu"), submenu)
            for sub_entry in entry[4]:
                self._build_menu_entry(submenu, sub_entry, m2_offer)
        elif kind == "info":
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            item.setEnabled_(False)
            menu.addItem_(item)
            setattr(self, attr, item)
        else:  # "action"
            if attr in m2_offer and not m2_offer[attr]:
                return  # M2 gate closed: attr stays None (set before the loop)
            if menu is self.menu:
                item = self._add_action(title, selector)
            else:
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    title, selector, ""
                )
                item.setTarget_(self)
                menu.addItem_(item)
            setattr(self, attr, item)

    def refresh_(self, _timer):
        self._snapshot = read_status()
        pids = bridge_pids()
        status = _bridge_status_from_pids(pids)
        # A frozen bridge child (argv '.../rb_ss_bridge_v2 --run-bridge') can't
        # match BRIDGE_PATTERN, so pgrep never sees it — the owned handle is the
        # only liveness signal. Without this a live frozen bridge reads 'Off',
        # identical to a dead one. And after a menubar quit/relaunch we no longer
        # own the handle, so also re-adopt a bridge still holding the lock — else
        # it is invisible AND uncontrollable (the Enttec/OS2L port stays held).
        if status == "off" and getattr(sys, "frozen", False):
            proc = getattr(self, "_frozen_bridge_proc", None)
            if proc is not None and proc.poll() is None:
                status = "on"
            elif _running_bridge_pid() is not None:
                status = "on"
        if status != self._status:
            self._set_icon(status)
            self._status = status
        for item, title in zip(self.status_rows, compact_status_lines(self._snapshot, pids)):
            if isinstance(title, str):
                item.setTitle_(title)
            else:
                item.setAttributedTitle_(title)
        count = len(pids)
        if status == "on":
            suffix = f" ({count} copies)" if count > 1 else ""
            self.toggle_item.setTitle_(f"Bridge On{suffix}  (click to stop)")
        elif status == "initializing":
            self.toggle_item.setTitle_("Bridge Initializing  (click to stop)")
        else:
            self.toggle_item.setTitle_("Bridge Off  (click to start)")
        self._render_export_state()
        self._auto_set_soundswitch_pack()
        self._maybe_detect_export_state()
        smart_drop_on = bool(self._snapshot.get("state_manager", {}).get("smart_drop_enabled"))
        self.smart_drop_item.setTitle_("Smart Drops: On" if smart_drop_on else "Smart Drops: Off")
        smart_breakdown_on = bool(self._snapshot.get("state_manager", {}).get("smart_breakdown_enabled"))
        self.smart_breakdown_item.setTitle_("Smart Breakdowns: On" if smart_breakdown_on else "Smart Breakdowns: Off")
        laser = self._snapshot.get("laser_director", {})
        available = bool(laser.get("available"))
        enabled = bool(laser.get("enabled"))
        emergency = bool(laser.get("emergency"))
        manual_override = bool(laser.get("manual_override"))
        if available:
            self.laser_toggle_item.setEnabled_(True)
            self.laser_toggle_item.setTitle_(f"Laser Director: {'On' if enabled else 'Off'}")
        else:
            self.laser_toggle_item.setEnabled_(False)
            self.laser_toggle_item.setTitle_("Laser Director: not configured")

        self.laser_blackout_item.setEnabled_(available and enabled and not emergency)
        self.laser_clear_blackout_item.setEnabled_(available and (emergency or manual_override))

        scene = str(laser.get("current_scene") or "—")
        reason = str(laser.get("last_reason") or "—")
        personality = str(laser.get("personality") or "—")
        executor = laser.get("executor") or {}
        midi = executor.get("midi") or {}
        queue_size = int(midi.get("queue_size", 0) or 0)
        queue_max = int(midi.get("queue_max", 0) or 0)
        drop_count = int(midi.get("drop_count", 0) or 0)
        degraded_reason = str(midi.get("degraded_reason") or "")
        midi_suffix = f" {degraded_reason}" if degraded_reason else ""
        self.laser_scene_item.setTitle_(f"Current Scene: {scene}")
        self.laser_reason_item.setTitle_(f"Reason: {reason}")
        self.laser_personality_item.setTitle_(f"Personality: {personality}")
        self.laser_midi_item.setTitle_(
            f"MIDI: {queue_size}/{queue_max} drops={drop_count}{midi_suffix}"
        )
        sp_block = (self._snapshot.get("state_manager") or {}).get("smart_phrasing")
        self.laser_phrasing_item.setTitle_(_phrasing_summary(sp_block))
        recording = recording_status_from_snapshot(self._snapshot)
        recording_active = bool(recording.get("active"))
        if status == "off":
            self.record_session_item.setEnabled_(False)
            self.record_session_item.setTitle_("Record Session: Bridge Off")
        else:
            self.record_session_item.setEnabled_(True)
            if recording_active:
                rec_path = Path(str(recording.get("path") or "")).name or "capture"
                self.record_session_item.setTitle_(f"Record Session: On ({rec_path})")
            else:
                self.record_session_item.setTitle_("Record Session: Off")
        v2_available = led_engine_v2_available(self._snapshot)
        self.led_engine_v2_item.setEnabled_(status == "on" and v2_available)
        self.led_engine_v2_item.setTitle_(
            "LED Engine v2" if v2_available else "LED Engine v2: not configured"
        )
        self.led_engine_v2_item.setState_(1 if led_engine_v2_enabled(self._snapshot) else 0)
        self._adapt_timer(status)

    def _render_export_state(self):
        frozen = bool(getattr(sys, "frozen", False))
        self.export_item.setEnabled_(
            export_button_enabled(self._export_in_progress, self._export_up_to_date, frozen))
        if frozen:
            # Authoring-only: the guest bundle has no SoundSwitch source project
            # and can't run the -m export tool, so make that plain, not a dead
            # lit button that fails on click.
            self.export_item.setTitle_("Export — on the mixing Mac only")
            self.export_status_item.setTitle_("Lighting pack ships pre-exported on the stick")
            return
        self.export_item.setTitle_(
            export_button_text(self._export_in_progress, self._export_up_to_date))
        self.export_status_item.setTitle_(
            pack_export_status_line(
                self._snapshot.get("soundswitch_pack", {}),
                stale=not self._snapshot or bool(self._snapshot.get("stale")),
                export_phase=self._export_phase,
                export_state=self._export_state,
                export_up_to_date=self._export_up_to_date,
                export_result=self._export_result,
                bridge_status=self._status,
                soundswitch_connected=(self._snapshot.get("soundswitch", {}) or {}).get("connected"),
            ))

    def _auto_set_soundswitch_pack(self):
        command = pack_auto_command(self._snapshot, bridge_status=self._status)
        if command is None:
            # Clear the debounce latch on a fresh settled snapshot so a later
            # transition can re-send. Keying it on confirmed enabled==target instead
            # latches forever after a failed enable (e.g. no Enttec port), killing
            # auto enable/disable for the menubar's life. Stale/off keeps the latch.
            snap = self._snapshot if isinstance(self._snapshot, dict) else {}
            if self._status == "on" and snap and not snap.get("stale"):
                self._pack_auto_pending_enabled = None
                self._pack_auto_retried_enabled = None
            return
        target = command["enabled"]
        if target == self._pack_auto_pending_enabled:
            snap = self._snapshot if isinstance(self._snapshot, dict) else {}
            pack = snap.get("soundswitch_pack", {}) if isinstance(snap, dict) else {}
            if (
                target is True
                and getattr(self, "_pack_auto_retried_enabled", None) != target
                and isinstance(pack, dict)
                and pack.get("reason") == "pack_start_failed"
            ):
                append_command(command)
                self._pack_auto_retried_enabled = target
            return
        append_command(command)
        self._pack_auto_pending_enabled = target
        self._pack_auto_retried_enabled = None

    def _maybe_detect_export_state(self):
        if getattr(sys, "frozen", False):
            return  # Export is disabled on frozen/guest runs — nothing to detect.
        if self._export_in_progress or self._detect_in_progress:
            return
        sig = _source_stat_signature(CANONICAL_SOURCE_PROJECT)
        fresh_enough = (time.monotonic() - self._detect_at) < DETECT_MAX_AGE_SECONDS
        if sig == self._detect_sig and fresh_enough:
            return
        self._detect_in_progress = True
        self._detect_generation += 1
        generation = self._detect_generation
        threading.Thread(target=self._run_detect, args=(generation, sig), daemon=True).start()

    def _run_detect(self, generation, sig):
        try:
            verdict = detect_export_state()
        except Exception:
            verdict = "changes"
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishDetect:", {"verdict": verdict, "sig": sig, "generation": generation}, False,
        )

    def finishDetect_(self, payload):
        generation = payload.get("generation") if isinstance(payload, dict) else None
        if generation != self._detect_generation:
            return
        verdict = payload.get("verdict") if isinstance(payload, dict) else "changes"
        self._export_up_to_date = verdict == "up_to_date"
        self._detect_sig = payload.get("sig") if isinstance(payload, dict) else None
        self._detect_at = time.monotonic()
        self._detect_in_progress = False
        self._render_export_state()

    def exportFromSS_(self, _sender):
        if getattr(sys, "frozen", False):
            return  # authoring-only; the item is disabled on frozen runs.
        if self._export_in_progress:
            return
        self._export_in_progress = True
        self._export_phase = "exporting"
        self._export_state = "exporting"
        self._export_result = {}
        self._detect_generation += 1
        self._detect_in_progress = False
        self._render_export_state()
        threading.Thread(target=self._run_export, daemon=True).start()

    def _run_export(self):
        result_path = None
        published_result = None
        try:
            with tempfile.NamedTemporaryFile(prefix="rbss-export-result-", suffix=".json",
                                             delete=False) as result_file:
                result_path = Path(result_file.name)
            subprocess.run(
                build_export_argv(str(result_path)),
                cwd=EXPORT_WORKING_DIRECTORY,
                timeout=EXPORT_PROCESS_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            result = parse_export_result(result_path.read_text(encoding="utf-8"))
            if not result.get("ok"):
                self._marshal_export_result("export_failed", result)
                return
            published_result = result
            self._marshal_export_phase("reloading")

            expected_sha12 = result["manifest_sha256"][:12]
            if not bridge_pids():
                self._marshal_export_result("published_not_live", result)
                return
            precheck = evaluate_reload_ack(read_status(), expected_sha12)
            if precheck == "not_live":
                # Bridge is up but pack output is disabled: saved to disk, not live.
                self._marshal_export_result("published_not_live", result)
                return
            if precheck == "stale":
                # Bridge is alive but its status snapshot is not fresh, so we cannot
                # confirm pack output is enabled. Never fire a blind reload at an
                # unknown live state; report saved-but-unconfirmed.
                self._marshal_export_result("reload_failed", result)
                return
            if precheck == "succeeded":
                # The live pack already serves this exact content (e.g. identical
                # re-export): it is already live, so do not re-send a reload.
                self._marshal_export_result("reload_succeeded", result)
                return

            # precheck == "pending": fresh + enabled + sha not yet matching.
            append_command({"cmd": "set_soundswitch_pack", "action": "reload"})
            deadline = time.monotonic() + EXPORT_RELOAD_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if evaluate_reload_ack(read_status(), expected_sha12) == "succeeded":
                    self._marshal_export_result("reload_succeeded", result)
                    return
                time.sleep(EXPORT_RELOAD_POLL_SECONDS)
            self._marshal_export_result("reload_failed", result)
        except Exception as exc:
            if published_result is None:
                self._marshal_export_result("export_failed", _export_failure_result(exc))
            else:
                self._marshal_export_result("reload_failed", published_result)
        finally:
            if result_path is not None:
                result_path.unlink(missing_ok=True)

    def _marshal_export_result(self, state: str, result: dict):
        payload = {"state": state, "result": result}
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishExport:", payload, False,
        )

    def _marshal_export_phase(self, phase: str):
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "setExportPhase:", phase, False,
        )

    def setExportPhase_(self, phase):
        if not self._export_in_progress:
            return
        self._export_phase = phase if phase in {"exporting", "reloading"} else "exporting"
        self._render_export_state()

    def finishExport_(self, payload):
        state = payload.get("state") if isinstance(payload, dict) else "export_failed"
        result = payload.get("result") if isinstance(payload, dict) else {}
        allowed_states = {
            "published_not_live", "reload_succeeded", "reload_failed", "export_failed",
        }
        self._export_state = state if state in allowed_states else "export_failed"
        self._export_result = result if isinstance(result, dict) else {}
        self._export_phase = "idle"
        self._export_in_progress = False
        self._export_up_to_date = state != "export_failed"
        self._detect_sig = None
        self._render_export_state()

    def _adapt_timer(self, status: str) -> None:
        if self._timer is None:
            return
        desired = 1.0 if status in ("on", "initializing") else 3.0
        if desired != self._timer_interval:
            self._timer.invalidate()
            self._timer_interval = desired
            self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                desired, self, "refresh:", None, True
            )

    def _set_icon(self, status: str) -> None:
        button = self.status_item.button()
        if button is None:
            return
        button.setTitle_("RBSS")
        icon_path = ICONS[status]
        # initByReferencingFile_ returns a NON-nil empty image for a missing path,
        # so guard on existence — else a guest Mac shows a blank icon instead of
        # the "RBSS" text fallback.
        image = (
            NSImage.alloc().initByReferencingFile_(icon_path)
            if os.path.exists(icon_path)
            else None
        )
        if image is not None:
            image.setTemplate_(True)
            image.setSize_(NSMakeSize(16, 16))
            button.setImage_(image)
            button.setImagePosition_(NSImageLeft)
        else:
            button.setImage_(None)

    def _spawn_watched(
        self,
        argv,
        *,
        label,
        early_window=4.0,
        busy_item_attr=None,
        busy_title=None,
        success_message=None,
        failure_title=None,
    ):
        """Spawn a detached child, capturing its stderr to a log; if it exits
        nonzero within early_window seconds, surface the stderr tail in a dialog.

        These frozen re-exec children (--run-bridge, --patch-rekordbox) were
        fire-and-forget with no stderr and no exit check, so any early crash was
        completely invisible ('does nothing'). Watching runs on a daemon thread —
        it never touches the bridge's 200 Hz loop (separate process) or the
        AppKit main thread except the final marshalled alert. Returns the Popen.

        When busy_item_attr is set, the watcher waits for the full child lifetime
        and always marshals a visible completion (busy title, success notify, or
        failure alert) back to the main thread."""
        err_path = None
        err_fh = subprocess.DEVNULL
        try:
            log_dir = _child_error_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            err_path = log_dir / f"{label}.err.log"
            # Truncate per spawn ("wb"): _watch_child reads this file's tail to
            # decide whether THIS start crashed. Appending would let a previous
            # crash's traceback trigger a false alert on a later clean start.
            err_fh = open(err_path, "wb")
        except OSError:
            err_path, err_fh = None, subprocess.DEVNULL
        saved_title = None
        if busy_item_attr:
            item = getattr(self, busy_item_attr, None)
            if item is not None:
                saved_title = item.title()
                item.setEnabled_(False)
                if busy_title:
                    item.setTitle_(busy_title)
        try:
            proc = subprocess.Popen(
                argv,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=err_fh,
                env=_system_env(),
            )
        except Exception as exc:
            if hasattr(err_fh, "close") and err_fh is not subprocess.DEVNULL:
                try:
                    err_fh.close()
                except OSError:
                    pass
            if busy_item_attr:
                self.finishWatchedChild_({
                    "returncode": 1,
                    "tail": str(exc),
                    "label": label,
                    "err_path": str(err_path) if err_path else "",
                    "busy_item_attr": busy_item_attr,
                    "saved_title": saved_title,
                    "success_message": success_message,
                    "failure_title": failure_title,
                })
                return None
            raise
        if hasattr(err_fh, "close"):
            err_fh.close()  # the child has its own dup; drop the parent's handle
        if busy_item_attr:
            threading.Thread(
                target=self._watch_child_full,
                args=(
                    proc,
                    err_path,
                    label,
                    busy_item_attr,
                    saved_title,
                    success_message,
                    failure_title,
                ),
                daemon=True,
            ).start()
        else:
            threading.Thread(
                target=self._watch_child,
                args=(proc, err_path, label, early_window),
                daemon=True,
            ).start()
        return proc

    def _read_child_stderr_tail(self, err_path) -> str:
        if err_path is None:
            return ""
        try:
            return Path(err_path).read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            return ""

    def _watch_child_full(
        self,
        proc,
        err_path,
        label,
        busy_item_attr,
        saved_title,
        success_message,
        failure_title,
    ):
        payload = {
            "label": label,
            "err_path": str(err_path) if err_path else "",
            "busy_item_attr": busy_item_attr,
            "saved_title": saved_title,
            "success_message": success_message,
            "failure_title": failure_title,
        }
        try:
            payload["returncode"] = proc.wait()
            payload["tail"] = self._read_child_stderr_tail(err_path)
        except Exception as exc:
            payload["returncode"] = 1
            payload["tail"] = str(exc)
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishWatchedChild:", payload, False,
        )

    def finishWatchedChild_(self, payload):
        attr = payload.get("busy_item_attr")
        saved_title = payload.get("saved_title")
        if attr:
            item = getattr(self, attr, None)
            if item is not None:
                if saved_title is not None:
                    item.setTitle_(saved_title)
                item.setEnabled_(True)
        returncode = payload.get("returncode", 0)
        if returncode == 0:
            message = payload.get("success_message")
            if message:
                _notify(message)
            return
        if returncode < 0:
            # Signal death (e.g. SIGTERM at logout): restore the item silently —
            # mirrors the early-window watcher and avoids false alerts when
            # children are torn down by the OS.
            return
        tail = payload.get("tail") or ""
        if _is_user_cancel(tail):
            return
        title = payload.get("failure_title") or "Operation failed"
        detail_parts = [f"It exited with code {returncode}."]
        stderr_tail = tail.strip()
        if stderr_tail:
            if len(stderr_tail) > 600:
                stderr_tail = "…" + stderr_tail[-600:]
            detail_parts.append(stderr_tail)
        err_path = payload.get("err_path") or ""
        if err_path:
            detail_parts.append(f"Full log: {err_path}")
        detail_parts.append("If you cancelled the prompts, you can ignore this.")
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_("\n\n".join(detail_parts))
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def _watch_child(self, proc, err_path, label, early_window):
        try:
            returncode = proc.wait(timeout=early_window)
        except subprocess.TimeoutExpired:
            return  # still alive past the window -> it started; its own UI owns it
        if returncode <= 0:
            # 0 = clean exit; negative = killed by a signal — our own stop
            # (_stop_frozen_bridge_child sends SIGTERM -> -15) or an OS kill.
            # Neither is a startup crash, so never pop a "couldn't start" dialog.
            return
        tail = self._read_child_stderr_tail(err_path)
        # Only a CRASH writes a traceback to stderr. A nonzero exit with no stderr
        # is a handled outcome the child already reported via its OWN dialog (e.g.
        # the operator cancelled the Rekordbox-patch prompt) — alerting there would
        # be a false "didn't start". Surface only genuine early crashes.
        if not tail.strip():
            return
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "showChildFailure:", _format_child_failure(label, returncode, tail), False,
        )

    def showChildFailure_(self, message):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("RBSS Bridge")
        alert.setInformativeText_(str(message))
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def _stop_frozen_bridge_child(self) -> bool:
        """Stop the owned bridge child by handle (never pkill/pattern — the
        flock is the real single-instance guard). True if one was stopped."""
        proc = getattr(self, "_frozen_bridge_proc", None)
        if proc is None or proc.poll() is not None:
            return False
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._frozen_bridge_proc = None
        return True

    def _toggle_bridge_frozen(self) -> None:
        # Frozen bundle only: the menubar owns the bridge as its OWN child
        # process (a re-exec of this binary with --run-bridge). No pkill / no
        # pattern matching -- a frozen bridge's argv doesn't match the
        # source-run regexes, and the exclusive flock is the real
        # single-instance guard. M1 is launch-on-click with no auto-restart;
        # M2 finalizes the frozen lifecycle (see the runbook).
        if self._stop_frozen_bridge_child():
            return
        # No owned child, but a bridge from a PREVIOUS menubar may still hold the
        # lock (pgrep can't see a frozen one). Re-adopt and STOP it by its lockfile
        # pid — validated to be a live bridge, so we never SIGTERM a recycled pid —
        # so the operator is never stuck with a live, uncontrollable bridge holding
        # the Enttec/OS2L port. SIGTERM lets it shut down cleanly and release the
        # flock; the next refresh reflects it, and one bridge is never left running.
        adopted = _running_bridge_pid()
        if adopted is not None:
            try:
                os.kill(adopted, signal.SIGTERM)
            except OSError:
                pass
            return
        # Not running: spawn one child bridge. If another bridge (source-run or
        # bundled) already holds the flock, the child logs the refusal and exits
        # nonzero -- the watcher surfaces "a bridge is already running" (a race we
        # otherwise couldn't see), not a silent 'Off'.
        self._frozen_bridge_proc = self._spawn_watched(
            [sys.executable, "--run-bridge"], label="frozen_bridge_start",
        )

    def toggleBridge_(self, _sender):
        if getattr(sys, "frozen", False):
            self._toggle_bridge_frozen()
            self.refresh_(None)
            return
        if bridge_status() != "off":
            stop_manual_launchctl_job()
            subprocess.run(["pkill", "-f", WATCHER_PATTERN])
            subprocess.run(["pkill", "-f", BRIDGE_PATTERN])
            close_monitor()
            deadline = time.time() + 1.5
            while bridge_pids() and time.time() < deadline:
                time.sleep(0.2)
            if bridge_pids():
                subprocess.run(["pkill", "-9", "-f", BRIDGE_PATTERN])
        else:
            stop_manual_launchctl_job()
            close_monitor()
            subprocess.Popen(
                [WATCHER],
                env={**os.environ, "RBSS_BRIDGE_MANUAL": "1"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        self.refresh_(None)

    def installOnMac_(self, _sender):
        if self._install_in_progress:
            return
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Install RBSS Bridge on this Mac?")
        alert.setInformativeText_(
            "Copies the app to ~/Applications and installs the lighting payload "
            "(pre-analyzed tracks, configs, Govee key) into Application Support. "
            "The bridge never starts by itself — you still start it from this menu."
        )
        alert.addButtonWithTitle_("Install")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        self._install_in_progress = True
        self.install_item.setEnabled_(False)
        self.install_item.setTitle_("Installing…")
        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self):
        from rb_ss_bridge_v2.install_controller import bundle_root, perform_install

        try:
            result = perform_install(bundle_root(sys.executable))
            payload = {
                "ok": result.ok,
                "failed_step": result.failed_step,
                "app_dest": str(result.app_dest or ""),
                "installed_files": result.installed_files,
            }
        except Exception as exc:  # marshal to a visible dialog — never die silently
            payload = {
                "ok": False,
                "failed_step": f"unexpected error ({type(exc).__name__})",
                "app_dest": "",
                "installed_files": 0,
            }
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishInstall:", payload, False,
        )

    def finishInstall_(self, payload):
        self._install_in_progress = False
        if not payload.get("ok"):
            self.install_item.setTitle_("Install on this Mac…")
            self.install_item.setEnabled_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Install didn't finish")
            alert.setInformativeText_(
                f"Failed step: {payload.get('failed_step') or 'unknown'}. "
                "Nothing is half-broken: the app keeps running from the installer "
                "disk, and the install record lists exactly what was copied."
            )
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return
        # Relaunch the installed copy (menubar only — never starts the bridge),
        # offer to eject the DMG, then quit this DMG-run copy.
        subprocess.Popen(["open", payload["app_dest"]])
        from rb_ss_bridge_v2.install_controller import bundle_root

        bundle = bundle_root(sys.executable)
        mount = None
        if bundle is not None and str(bundle).startswith("/Volumes/"):
            mount = Path(*bundle.parts[:3])
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Installed")
        alert.setInformativeText_(
            f"{payload['installed_files']} payload file(s) installed. The installed "
            "copy is opening from ~/Applications now."
            + (" Eject the installer disk?" if mount else "")
        )
        if mount:
            alert.addButtonWithTitle_("Eject")
            alert.addButtonWithTitle_("Keep Mounted")
        else:
            alert.addButtonWithTitle_("OK")
        response = alert.runModal()
        if mount and response == NSAlertFirstButtonReturn:
            # Detached: the eject can only succeed once this DMG-run copy exits.
            subprocess.Popen(
                ["/bin/sh", "-c", f'sleep 1; hdiutil detach "{mount}" -quiet'],
                start_new_session=True,
            )
        NSApplication.sharedApplication().terminate_(self)

    def purgeBridge_(self, _sender):
        if self._purge_in_progress:
            return
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Purge RBSS Bridge from this Mac?")
        alert.setInformativeText_(
            "Removes: the app in ~/Applications, everything in "
            "~/Library/Application Support/RBSS Bridge (installed configs, Govee "
            "key, analysis cache, learned state), and the logs in "
            "~/Library/Logs/rb_ss_bridge. The USB stick and its DMG are NOT "
            "touched. Permission entries in System Settings stay (macOS keeps "
            "those; they are inert)."
        )
        alert.addButtonWithTitle_("Purge")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        self._purge_in_progress = True
        self.purge_item.setEnabled_(False)
        self.purge_item.setTitle_("Purging…")
        # Stop the owned bridge child FIRST, by handle + flock (M1 rule:
        # never pkill/pattern), so nothing writes while files disappear.
        self._stop_frozen_bridge_child()
        threading.Thread(target=self._run_purge, daemon=True).start()

    def _run_purge(self):
        from rb_ss_bridge_v2.install_controller import bundle_root, perform_purge

        try:
            own = bundle_root(sys.executable)
            result = perform_purge(own_app=own)
            payload = {
                "removed": result.removed,
                "failures": list(result.failures),
                "skipped": list(result.skipped),
                "remains_note": result.remains_note,
                "own_app": str(own or ""),
            }
        except Exception as exc:  # marshal to a visible dialog — never die silently
            payload = {
                "removed": 0,
                "failures": [f"unexpected error ({type(exc).__name__})"],
                "skipped": [],
                "remains_note": "",
                "own_app": "",
            }
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishPurge:", payload, False,
        )

    def finishPurge_(self, payload):
        self._purge_in_progress = False
        alert = NSAlert.alloc().init()
        failures = payload.get("failures") or []
        if failures:
            alert.setMessageText_("Purge finished with leftovers")
            detail = "; ".join(failures[:5])
            alert.setInformativeText_(
                f"Removed {payload.get('removed', 0)} item(s). Could not remove: "
                f"{detail}. {payload.get('remains_note', '')}"
            )
        else:
            alert.setMessageText_("Purged")
            alert.setInformativeText_(
                f"Removed {payload.get('removed', 0)} item(s). The app itself now "
                f"moves to the Trash and the menubar quits. "
                f"{payload.get('remains_note', '')}"
            )
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        own_app = payload.get("own_app")
        if own_app:
            # Move the running bundle to Trash [assumed mechanism — macOS allows
            # trashing a running app's bundle; the operator walkthrough verifies].
            from Foundation import NSURL

            from AppKit import NSWorkspace

            NSWorkspace.sharedWorkspace().recycleURLs_completionHandler_(
                [NSURL.fileURLWithPath_(own_app)], None
            )
        NSApplication.sharedApplication().terminate_(self)

    def runValidation_(self, _sender):
        append_command({"cmd": "run_validation"})
        self.refresh_(None)

    def toggleRecordSession_(self, _sender):
        recording = recording_status_from_snapshot(read_status())
        command = {"cmd": "toggle_record_session"}
        if not bool(recording.get("active")):
            command["path"] = default_recording_path()
            command["dedup"] = False
        append_command(command)
        if self is not None:
            self.refresh_(None)

    def testLights_(self, _sender):
        # Test the Lights: replay the newest recorded session through the full
        # rig. Live-safety guards fail closed with a visible message; the
        # launcher re-checks them too (defense in depth).
        if rekordbox_running():
            _notify("Quit Rekordbox first — Test the Lights replays a recorded set and can't run against live decks.")
            return
        path = newest_recorded_session()
        if not path:
            _notify("No test session recorded yet. Record one from this menu during a real set, then Test the Lights.")
            return
        if getattr(sys, "frozen", False):
            argv = [sys.executable, "--replay-session", path]
        else:
            argv = [sys.executable, str(REPO_ROOT / "usb_launcher.py"), "--replay-session", path]
        subprocess.Popen(argv, start_new_session=True)
        _notify(f"Test the Lights: replaying {Path(path).name} — watch the rig.")

    def enableRekordboxReads_(self, _sender):
        # Re-sign Rekordbox (with your consent + admin password) so the bridge can
        # read its playback state — the get-task-allow patch. Dispatched to the
        # launcher so the menubar thread never blocks on the admin prompt/codesign;
        # all UI is macOS dialogs owned by that process.
        if getattr(sys, "frozen", False):
            argv = [sys.executable, "--patch-rekordbox"]
        else:
            argv = [sys.executable, str(REPO_ROOT / "usb_launcher.py"), "--patch-rekordbox"]
        self._spawn_watched(
            argv,
            label="patch_rekordbox",
            busy_item_attr="enable_rb_reads_item",
            busy_title="Enabling Rekordbox reads…",
            success_message=(
                "Rekordbox reads step finished — follow any dialogs it showed."
            ),
            failure_title="Enable Rekordbox Reads failed",
        )

    def mapLasers_(self, _sender):
        # Off the AppKit main thread: open_pad may spawn the server and wait up to
        # 3s for its port, which would otherwise freeze the menu on first launch.
        threading.Thread(
            target=open_pad, args=(LASER_PAD_URL, LASER_PAD_PORT, laser_pad_argv()),
            daemon=True,
        ).start()

    def openLedPad_(self, _sender):
        threading.Thread(
            target=open_pad, args=(LED_PAD_URL, LED_PAD_PORT, led_pad_argv()),
            daemon=True,
        ).start()

    def toggleLedEngineV2_(self, _sender):
        append_command(led_engine_v2_command(read_status()))
        if self is not None:
            self.refresh_(None)

    def toggleSmartDrop_(self, _sender):
        append_command({"cmd": "toggle_smart_drop"})
        self.refresh_(None)

    def toggleSmartBreakdown_(self, _sender):
        append_command({"cmd": "toggle_smart_breakdown"})
        self.refresh_(None)

    def toggleLaserDirector_(self, _sender):
        append_command({"cmd": "toggle_laser_director"})
        self.refresh_(None)

    def laserBlackout_(self, _sender):
        append_command({"cmd": "laser_blackout"})
        self.refresh_(None)

    def laserClearBlackout_(self, _sender):
        append_command({"cmd": "laser_clear_blackout"})
        self.refresh_(None)

    def quit_(self, _sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Quit the menubar?")
        alert.setInformativeText_(
            "The bridge keeps running if it is already on. To get the menubar "
            "back, open \"RBSS Bridge\" again from Applications, the USB stick, "
            "or the DMG."
        )
        alert.addButtonWithTitle_("Quit")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() == NSAlertFirstButtonReturn:
            NSApplication.sharedApplication().terminate_(self)


def main() -> None:
    if not acquire_menubar_lock():
        return
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = BridgeMenuBar.alloc().init()  # retained by app during run()  # noqa: F841
    app.run()


if __name__ == "__main__":
    main()
