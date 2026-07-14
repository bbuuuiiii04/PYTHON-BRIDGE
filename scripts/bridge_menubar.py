#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shlex
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
STREAMDECK_LOCK_PATH = "/tmp/streamdeck_midi.lock"
BRIDGE_PATTERN = r"^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$"
WATCHER_PATTERN = "^(/bin/bash|bash)[[:space:]]+" + WATCHER.replace(".", r"\.") + "$"
MONITOR_TITLE = "RBSS_BRIDGE_MONITOR"
MONITOR_PATTERN = r"RBSS_BRIDGE_MONITOR|--run-log-viewer|/bridge_view\.py"
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
# Full deep Rekordbox verification is intentionally background-only and can take
# tens of seconds on the large app bundle. Recheck occasionally, not every 30 s.
RB_READS_MAX_AGE_SECONDS = 600.0
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


def _running_streamdeck_pid(path: str = STREAMDECK_LOCK_PATH) -> int | None:
    """Live Stream Deck helper holding its singleton lock, or None."""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            pid = int(fp.readline().strip())
    except (OSError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    try:
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "--run-streamdeck" in command or "streamdeck_midi.py" in command:
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


def usb_button_text(in_progress: bool, state: str) -> str:
    if in_progress:
        return "Rebuilding USB Bridge…"
    if state == "no_usb":
        return "No USB Found"
    if state == "up_to_date":
        return "USB Bridge Rebuilt"
    return "Rebuild USB Bridge…"  # "outdated" or any unknown -> actionable label


def usb_button_enabled(in_progress: bool, state: str, frozen: bool) -> bool:
    """Actionable only on a source run with a mounted, out-of-date stick.
    Rebuild is maintainer-side like export: the frozen guest bundle hides the
    item entirely, and every uncertain state resolves to 'outdated' (clickable),
    never to a false 'up to date'."""
    return (not in_progress) and (not frozen) and state == "outdated"


def patch_rb_button_text(in_progress: bool, state: str) -> str:
    """Visible title for the Patch Rekordbox action (pure state table).

    'Rekordbox Patched' means get-task-allow is present and the app's full
    signature verifies — never that the bridge has attached or that stock
    foreign-Mac attach is proven.
    """
    if in_progress:
        return "Patching Rekordbox…"
    if state == "checking":
        return "Checking Rekordbox…"
    if state == "enabled":
        return "Rekordbox Patched"
    return "Patch Rekordbox"  # absent, unknown, or no cached result yet


def patch_rb_button_enabled(in_progress: bool, state: str) -> bool:
    """Grey while checking/patching or after a positive complete verify."""
    return (not in_progress) and state not in ("enabled", "checking")


def classify_usb_state(
    mount_count: int,
    stick_generation: str | None,
    stamp: dict | None,
    current_fingerprint: str | None,
) -> str:
    """Pure decision: 'no_usb' | 'up_to_date' | 'outdated'. Fails toward 'outdated'."""
    if mount_count == 0:
        return "no_usb"
    if mount_count > 1:
        return "outdated"  # ambiguous; the click handler guides "leave only one"
    if not stick_generation:
        return "outdated"  # no complete bridge generation on the stick
    if not isinstance(stamp, dict) or stamp.get("generation") != stick_generation:
        return "outdated"  # we did not build this stick (or cold start)
    if not current_fingerprint:
        return "outdated"  # cannot prove the sources are unchanged
    return "up_to_date" if stamp.get("source_fingerprint") == current_fingerprint else "outdated"


# ponytail: stat-signature (path+size+mtime_ns), NOT a content hash. Re-analysis and
# code edits always rewrite mtimes, so this catches every real change in normal use
# and fails toward "rebuild"; the only miss is an identical-content, identical-mtime
# rewrite, which does not happen naturally. Upgrade to a content hash only if that
# ever matters.
# ponytail: this list mirrors make_stick.sh's staged inputs by hand. If that script's
# inputs change, update this list (test_bridge_menubar pins the key entries).
def _usb_source_roots() -> list[Path]:
    support = Path.home() / "Library" / "Application Support" / "RBSS Bridge"
    tools = REPO_ROOT / "tools"
    config = REPO_ROOT / "config"
    roots: list[Path] = []
    roots += sorted(REPO_ROOT.glob("*.py"))                       # flat bridge modules
    roots += [REPO_ROOT / "streamdeck", REPO_ROOT / "scripts"]    # bundled packages
    roots += sorted(tools.glob("*.py"))                           # bundled/build tools
    roots += [tools / "laser_pad_assets", tools / "led_pad_assets"]
    roots += [REPO_ROOT / "pyproject.toml",
              REPO_ROOT / "packaging" / "rbss_launcher.spec",
              REPO_ROOT / "packaging" / "sign.sh",
              REPO_ROOT / "packaging" / "make_stick.sh"]
    roots += sorted((REPO_ROOT / "packaging").glob("*.lock"))
    roots += sorted(config.glob("*.example.json"))
    roots += [config / name for name in (
        "laser_director.json", "led_look_director.json",
        "soundswitch_pack_player.json", "laser_color_map.json")]
    roots.append(support / "govee.env")
    roots.append(support / "spectral_cache")                      # big tree — stat only
    # The exported pack (pack_path from the live config) + canonical Stream Deck
    # bindings — the same inputs make_stick.sh stages into RBSS_payload/.
    try:
        value = json.loads((REPO_ROOT / "config" / "soundswitch_pack_player.json")
                           .read_text(encoding="utf-8"))
        pack = value.get("pack_path", "") if isinstance(value, dict) else ""
        if pack:
            roots.append(Path(pack))
    except (OSError, ValueError):
        pass  # the config file itself is already a root; unreadability surfaces there
    roots.append(REPO_ROOT / "local" / "soundswitch"
                 / ".rbss_canonical_pack.midi_bindings.json")
    return roots


def usb_source_signature(roots: list[Path] | None = None) -> str:
    """Cheap stat signature over every USB-build input (~44 ms measured 2026-07-12
    over the full root set; daemon-thread only, never per render tick). Never
    reads file contents. Per-file lstat failures are skipped like
    _source_stat_signature; an absent root contributes nothing (absence is
    stable, so it cannot flip the verdict spuriously)."""
    if roots is None:
        roots = _usb_source_roots()
    entries: list[tuple[str, int, int]] = []
    for root in roots:
        if root.is_dir():
            for dirpath, dirs, files in os.walk(root, followlinks=False):
                dirs.sort()
                for name in sorted(files):
                    path = Path(dirpath) / name
                    try:
                        st = path.lstat()
                    except OSError:
                        continue
                    entries.append((str(path), st.st_size, st.st_mtime_ns))
        else:
            try:
                st = root.lstat()
            except OSError:
                continue
            entries.append((str(root), st.st_size, st.st_mtime_ns))
    digest = hashlib.sha256()
    for name, size, mtime in sorted(entries):
        digest.update(f"{name}\x00{size}\x00{mtime}\n".encode("utf-8"))
    return digest.hexdigest()


def _usb_stamp_path() -> Path:
    return (Path.home() / "Library" / "Application Support" / "RBSS Bridge"
            / ".usb_rebuild_state.json")


def read_usb_stamp() -> dict | None:
    try:
        with open(_usb_stamp_path(), "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_usb_stamp(generation: str, fingerprint: str) -> None:
    """Atomic write; OSError swallowed HERE ONLY — a stamp we could not write just
    means the next detection reads None -> 'outdated', which is safe."""
    path = _usb_stamp_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps({"generation": generation, "source_fingerprint": fingerprint}),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except OSError:
        pass


def read_stick_generation(mount: Path) -> str | None:
    """The published stick's build generation, from the manifest make_stick.sh
    writes; None on any error (-> 'outdated')."""
    manifest = (mount / "RBSS BRIDGE USB" / "lighting_sidecar"
                / ".rbss_build_manifest.json")
    try:
        with open(manifest, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None
    generation = data.get("generation") if isinstance(data, dict) else None
    return generation if isinstance(generation, str) and generation else None


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


def open_terminal_command(command: str, title: str = "RBSS_TERMINAL") -> bool:
    safe_cmd = command.replace("\\", "\\\\").replace('"', '\\"')
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Terminal"\n'
        'activate\n'
        f'do script "{safe_cmd}"\n'
        f'set custom title of selected tab of front window to "{safe_title}"\n'
        'end tell'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def log_viewer_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-log-viewer"]
    return [sys.executable, str(REPO_ROOT / "bridge_view.py")]


def log_viewer_terminal_command(argv: list[str] | None = None) -> str:
    command = " ".join(shlex.quote(part) for part in (argv or log_viewer_argv()))
    inner = f"printf '\\033]0;{MONITOR_TITLE}\\007'; {command}"
    # $0 carries the stable marker while the viewer child is alive, allowing
    # source and frozen menubars to share one no-duplicates check.
    return f"bash -c {shlex.quote(inner)} {MONITOR_TITLE}"


def monitor_open() -> bool:
    return subprocess.run(
        ["pgrep", "-f", MONITOR_PATTERN], capture_output=True
    ).returncode == 0


def open_live_log() -> bool:
    """Ensure one disposable log viewer is open; report launch failure."""
    if monitor_open():
        return True
    return open_terminal_command(log_viewer_terminal_command(), MONITOR_TITLE)


def pioneer_usb_mounts(volumes_root: str | os.PathLike[str] = "/Volumes") -> list[Path]:
    """Mounted Rekordbox USB roots, identified by their PIONEER directory."""
    try:
        mounts = list(Path(volumes_root).iterdir())
    except OSError:
        return []
    return sorted(
        (mount for mount in mounts if mount.is_dir() and (mount / "PIONEER").is_dir()),
        key=lambda path: path.name.lower(),
    )


def _app_bundle_for_executable(executable: str | os.PathLike[str]) -> Path | None:
    for parent in Path(executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def restart_menubar_argv() -> list[str]:
    """Delayed replacement so this process releases the singleton lock first."""
    if getattr(sys, "frozen", False):
        bundle = _app_bundle_for_executable(sys.executable)
        if bundle is None:
            return []
        relaunch = f"open -n {shlex.quote(str(bundle))}"
    else:
        relaunch = " ".join(
            shlex.quote(part) for part in (sys.executable, str(Path(__file__).resolve()))
        )
    return ["/bin/sh", "-c", f"sleep 1; exec {relaunch}"]


def installed_relaunch_argv(app_dest: str | os.PathLike[str]) -> list[str]:
    """Open the installed app only after this DMG menubar releases its lock."""
    return [
        "/bin/sh",
        "-c",
        f"sleep 1; exec open -n {shlex.quote(str(app_dest))}",
    ]


def delayed_detach_argv(mount: str | os.PathLike[str]) -> list[str]:
    """Detach a DMG after this copy exits without interpolating its path."""
    return [
        "/bin/sh", "-c",
        'sleep 1; exec /usr/bin/hdiutil detach "$1" -quiet',
        "rbss-detach", str(mount),
    ]


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


def _import_rekordbox_patch():
    """Import rekordbox_patch the way usb_launcher does (`from rb_ss_bridge_v2
    import rekordbox_patch`): frozen, PyInstaller already bundles the package for
    --patch-rekordbox; source runs need the repo parent on sys.path first."""
    parent = str(REPO_ROOT.parent)
    if not getattr(sys, "frozen", False) and parent not in sys.path:
        sys.path.insert(0, parent)
    from rb_ss_bridge_v2 import rekordbox_patch

    return rekordbox_patch


def _rb_reads_verdict() -> tuple[str, str]:
    """Check the Rekordbox target entitlement and complete signature.

    The legacy verdict tokens are "enabled" | "not_enabled" | "unknown", but
    enabled means only "valid target patch present". It still does not prove
    a live task_for_pid attach. Shells out via
    codesign and must NEVER run on the AppKit main thread."""
    try:
        rekordbox_patch = _import_rekordbox_patch()
        app = rekordbox_patch.find_rekordbox()
        if app is None:
            return "unknown", "Rekordbox app not found in /Applications"
        if rekordbox_patch.has_valid_target_patch(app):
            return "enabled", str(app)
        return "not_enabled", str(app)
    except Exception as exc:
        return "unknown", f"{type(exc).__name__}: {exc}"


def rb_reads_status_title(state: str) -> str:
    return {
        "enabled": "Rekordbox target patch: present",
        "not_enabled": "Rekordbox target patch: not present",
    }.get(state, "Rekordbox target patch: unknown")


def _format_child_failure(label: str, returncode: int, stderr_tail: str) -> str:
    """Plain-language dialog text when a spawned child dies at startup (pure seam
    for the frozen bridge / rekordbox-patch spawns, which otherwise fail silent)."""
    what = {
        "frozen_bridge_start": "The bridge couldn't start",
        "frozen_streamdeck_start": "The Stream Deck helper couldn't start",
        "patch_rekordbox": "The Rekordbox target patch didn't start",
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


def compact_status_lines(
    status: dict,
    pids: list[str] | None = None,
    *,
    bridge_state: str | None = None,
) -> list:
    """Four operator-useful rows. Detailed deck/phrasing/check data belongs in
    the live log, not the everyday menu."""
    pids = pids or []

    # The process/lock result is newer truth than the last JSON snapshot. After
    # a stop, never keep painting the old Rekordbox/laser/LED state green until
    # the status file ages out.
    if bridge_state in {"off", "initializing"}:
        bridge_text = "Starting" if bridge_state == "initializing" else "Off"
        bridge_color = _co() if bridge_state == "initializing" else _cs()
        return [
            _join(_seg("○  ", color=bridge_color), _seg("BRIDGE", bold=True),
                  _seg(f"  {bridge_text}", color=bridge_color)),
            _join(_seg("  Rekordbox  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("  Lasers  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("  LEDs  ", color=_cs()), _seg("—", color=_cs())),
        ]

    if not status or status.get("stale"):
        age_s = status.get("stale_age_s", 0) if status else 0
        age_str = f"{age_s}s stale" if age_s else "no snapshot"
        return [
            _join(_seg("⊘  ", color=_co()), _seg("BRIDGE", bold=True), _seg(f"  {age_str}", color=_co())),
            _join(_seg("  Rekordbox  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("  Lasers  ", color=_cs()), _seg("—", color=_cs())),
            _join(_seg("  LEDs  ", color=_cs()), _seg("—", color=_cs())),
        ]

    laser = status.get("laser_director", {})
    multi_seg = _seg(f"  ⚠ {len(pids)} procs", color=_co()) if len(pids) > 1 else _seg("")
    bridge_row = _join(
        _seg("●  ", color=_cg()),
        _seg("BRIDGE", bold=True),
        _seg("  On", color=_cg()),
        multi_seg,
    )

    rb = status.get("rekordbox", {})
    rb = rb if isinstance(rb, dict) else {}
    rb_reason = str(rb.get("reason") or "")
    if rb.get("reads_ok"):
        rb_text, rb_color = "Reading", _cg()
    elif rb_reason == "reads_blocked":
        rb_text, rb_color = "Blocked", _cr()
    elif rb.get("version") in (None, "", "unknown") and not rb_reason:
        rb_text, rb_color = "Not detected", _cs()
    else:
        rb_text, rb_color = "Waiting", _co()
    rb_row = _join(
        _seg("  Rekordbox  ", color=_cs()),
        _seg(rb_text, color=rb_color),
        _seg(f"  {rb_reason}", color=_cs()) if rb_reason else _seg(""),
    )

    laser_available = bool(laser.get("available"))
    laser_enabled = bool(laser.get("enabled"))
    laser_emergency = bool(laser.get("emergency"))
    executor = laser.get("executor") or {}
    midi = executor.get("midi") or {}
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

    laser_row = _join(
        _seg("  Lasers  ", color=_cs()),
        _seg(laser_txt, color=laser_col),
        _seg(f"  {degraded_reason[:14]}", color=_co()) if degraded_reason else _seg(""),
    )

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
    led_segs.append(
        _seg(f"  {led_degraded[:14]}", color=_co()) if led_degraded else _seg("")
    )
    led_row = _join(*led_segs)

    return [bridge_row, rb_row, laser_row, led_row]


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


# One small menu on both Macs. Source-only authoring actions are filtered by
# _menu_visibility(); frozen install/purge is filtered by the same seam.
MENU_BLUEPRINT: tuple = (
    ("action", "toggle_item", "", "toggleBridge:"),  # title set by refresh_
    ("action", "open_log_item", "Open Live Log", "openLiveLog:"),
    ("submenu", "status_submenu_item", "Status", None, (
        ("status_rows", "status_rows", 4, None),
    )),
    ("submenu", "tools_item", "Tools", None, (
        ("action", "map_lasers_item", "Laser Pad…", "mapLasers:"),
        ("action", "led_pad_item", "LED Pad…", "openLedPad:"),
    )),
    ("submenu", "laser_safety_item", "Laser Safety", None, (
        ("action", "laser_blackout_item", "EMERGENCY: Stop All Lasers", "laserBlackout:"),
        ("action", "laser_clear_blackout_item", "Resume Lasers", "laserClearBlackout:"),
    )),
    # User override of the AWR-226 slim-menu cut: restore the target-patch
    # action (not the old standing status row). Present in both editions.
    # Maintenance block: Export + Rebuild (source-only) + Patch (always),
    # then Purge (frozen+available) and Restart Menubar.
    ("sep", "maintenance_sep", None, None),
    ("action", "export_item", "SoundSwitch Export…", "exportFromSS:"),
    ("action", "update_usb_item", "Rebuild USB Bridge…", "updateUsbBridge:"),
    ("action", "patch_rekordbox_item", "Patch Rekordbox", "enableRekordboxReads:"),
    ("action", "purge_item", "Purge RBSS Bridge…", "purgeBridge:"),
    ("action", "restart_item", "Restart Menubar", "restartMenubar:"),
)


def _menu_visibility(*, frozen: bool, purge: bool) -> dict[str, bool]:
    """Exact source/frozen inventory; the builder is the only consumer."""
    return {
        "tools_item": not frozen,
        "export_item": not frozen,
        "update_usb_item": not frozen,
        # Patch is always visible, so the maintenance separator stays visible
        # in frozen mode too (Export/Rebuild still hide; Purge stays gated).
        "maintenance_sep": True,
        "purge_item": frozen and purge,
    }


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
        # Rebuild-USB item state (mirrors the export item's fields above).
        self._usb_rebuild_in_progress = False
        self._usb_state = "outdated"  # safe actionable default until detection resolves
        self._usb_pending_fingerprint = None  # captured at click time, stamped at finish
        self._usb_detect_in_progress = False
        self._usb_mounts_key = None
        self._usb_detect_at = 0.0
        self._usb_detect_generation = 0
        self._pack_auto_pending_enabled = None
        self._pack_auto_retried_enabled = None
        self._frozen_bridge_proc = None
        self._frozen_streamdeck_proc = None
        self._streamdeck_retry_at = 0.0
        self._adopted_frozen_bridge = False
        # Rekordbox target-patch entitlement cache (same shape as the export
        # detect cache: monotonic timestamp + in-progress guard + daemon-thread
        # refresh). _rb_reads_in_progress = background entitlement check;
        # _patch_rb_in_progress = the patch child is running — keep them distinct
        # so a periodic refresh cannot overwrite "Patching Rekordbox…".
        self._rb_reads_state = "unknown"
        self._rb_reads_at = 0.0
        self._rb_reads_in_progress = False
        self._patch_rb_in_progress = False
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
        self._install_action_title = "Install on This Mac…"
        offer_install = False
        frozen = bool(getattr(sys, "frozen", False))
        purge_offer = False
        if frozen:
            from rb_ss_bridge_v2.install_controller import (
                APP_SUPPORT_DIR,
                INCOMPLETE_MARKER_NAME,
                MANIFEST_NAME,
                bundle_root,
                install_action_title,
                running_from_read_only_location,
                should_offer_install,
            )

            bundle = bundle_root(sys.executable)
            manifest_exists = (APP_SUPPORT_DIR / MANIFEST_NAME).exists()
            offer_install = bool(should_offer_install(bundle, manifest_exists))
            self._install_action_title = install_action_title(
                manifest_exists,
                (APP_SUPPORT_DIR / INCOMPLETE_MARKER_NAME).exists(),
            )
            purge_offer = bool(
                manifest_exists
                and bundle is not None
                and not running_from_read_only_location(bundle)
            )
        self._install_required = offer_install

        self.status_rows = []
        visibility = _menu_visibility(frozen=frozen, purge=purge_offer)
        for entry in MENU_BLUEPRINT:
            self._build_menu_entry(self.menu, entry, visibility)
        if offer_install:
            self.install_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                self._install_action_title, "installOnMac:", ""
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

    def _build_menu_entry(self, menu, entry, visibility):
        """Materialize one visible MENU_BLUEPRINT entry."""
        kind, attr, title, selector = entry[0], entry[1], entry[2], entry[3]
        if attr in visibility and not visibility[attr]:
            return
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
                self._build_menu_entry(submenu, sub_entry, visibility)
        elif kind == "info":
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            item.setEnabled_(False)
            menu.addItem_(item)
            setattr(self, attr, item)
        else:  # "action"
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
                self._adopted_frozen_bridge = True
        if getattr(sys, "frozen", False) and not getattr(self, "_install_required", False):
            if status == "on":
                self._ensure_frozen_streamdeck()
            else:
                streamdeck_proc = getattr(self, "_frozen_streamdeck_proc", None)
                if (
                    (streamdeck_proc is not None and streamdeck_proc.poll() is None)
                    or _running_streamdeck_pid() is not None
                    or getattr(self, "_adopted_frozen_bridge", False)
                ):
                    self._stop_frozen_streamdeck()
                self._adopted_frozen_bridge = False
        if status != self._status:
            self._set_icon(status)
            self._status = status
        for item, title in zip(
            self.status_rows,
            compact_status_lines(self._snapshot, pids, bridge_state=status),
        ):
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
        if getattr(self, "_install_required", False):
            self.toggle_item.setTitle_("Install or Update This Mac first")
            self.toggle_item.setEnabled_(False)
        else:
            self.toggle_item.setEnabled_(True)
        self._render_export_state()
        self._auto_set_soundswitch_pack()
        self._maybe_detect_export_state()
        self._render_usb_state()
        self._maybe_detect_usb_state()
        self._render_patch_rb_state()
        self._maybe_check_rb_reads()
        laser = self._snapshot.get("laser_director", {})
        available = bool(laser.get("available"))
        enabled = bool(laser.get("enabled"))
        emergency = bool(laser.get("emergency"))
        manual_override = bool(laser.get("manual_override"))
        self.laser_blackout_item.setEnabled_(available and enabled and not emergency)
        self.laser_clear_blackout_item.setEnabled_(available and (emergency or manual_override))
        self._adapt_timer(status)

    def _render_export_state(self):
        if getattr(self, "export_item", None) is None:
            return
        self.export_item.setEnabled_(
            export_button_enabled(self._export_in_progress, self._export_up_to_date, False))
        self.export_item.setTitle_({
            "Export": "SoundSwitch Export…",
            "Exporting…": "SoundSwitch Exporting…",
            "Exported": "SoundSwitch Exported",
        }[export_button_text(self._export_in_progress, self._export_up_to_date)])

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

    def _render_usb_state(self):
        # Single owner of the rebuild item's title + enabled state. In-progress
        # wins, so the periodic repaint keeps "Rebuilding…" for the whole build
        # (the same reason _render_export_state checks _export_in_progress first).
        if getattr(self, "update_usb_item", None) is None:
            return
        frozen = bool(getattr(sys, "frozen", False))
        self.update_usb_item.setTitle_(
            usb_button_text(self._usb_rebuild_in_progress, self._usb_state))
        self.update_usb_item.setEnabled_(
            usb_button_enabled(self._usb_rebuild_in_progress, self._usb_state, frozen))

    def _maybe_detect_usb_state(self):
        if getattr(sys, "frozen", False):
            return  # the rebuild item is hidden on frozen/guest runs
        if self._usb_rebuild_in_progress or self._usb_detect_in_progress:
            return
        # Main-thread throttle stays CHEAP: mount names (one /Volumes iterdir)
        # plus an age cap. The full stat signature costs ~44 ms over the real
        # input tree — measured 2026-07-12 — so it runs ONLY on the daemon
        # thread below; recomputing it here every 1 s render tick would put a
        # 4% duty cycle on the AppKit main thread (review finding R1). Mount
        # changes repaint on the next tick; source edits repaint within
        # DETECT_MAX_AGE_SECONDS. Kept a plain string: it crosses
        # performSelectorOnMainThread_, and str bridges/compares reliably.
        # ponytail: a hung network volume under /Volumes would stall this is_dir
        # probe on the main thread; switch to NSWorkspace volume-mount
        # notifications if that ever bites (local-USB workflow today).
        mounts_key = ",".join(p.name for p in pioneer_usb_mounts())
        fresh_enough = (time.monotonic() - self._usb_detect_at) < DETECT_MAX_AGE_SECONDS
        if mounts_key == self._usb_mounts_key and fresh_enough:
            return
        self._usb_detect_in_progress = True
        self._usb_detect_generation += 1
        generation = self._usb_detect_generation
        threading.Thread(
            target=self._run_usb_detect, args=(generation, mounts_key), daemon=True).start()

    def _run_usb_detect(self, generation, mounts_key):
        try:
            mounts = pioneer_usb_mounts()
            stick_gen = read_stick_generation(mounts[0]) if len(mounts) == 1 else None
            verdict = classify_usb_state(
                len(mounts), stick_gen, read_usb_stamp(), usb_source_signature())
        except Exception:
            verdict = "outdated"  # fail toward action, never toward false "rebuilt"
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishUsbDetect:",
            {"verdict": verdict, "mounts_key": mounts_key, "generation": generation},
            False,
        )

    def finishUsbDetect_(self, payload):
        generation = payload.get("generation") if isinstance(payload, dict) else None
        if generation != self._usb_detect_generation:
            return
        verdict = payload.get("verdict") if isinstance(payload, dict) else "outdated"
        self._usb_state = verdict if verdict in ("no_usb", "up_to_date") else "outdated"
        self._usb_mounts_key = payload.get("mounts_key") if isinstance(payload, dict) else None
        self._usb_detect_at = time.monotonic()
        self._usb_detect_in_progress = False
        self._render_usb_state()

    def _record_usb_rebuild_stamp(self):
        # Stamp the CLICK-TIME fingerprint (never a post-build one: an edit made
        # during the multi-minute build must leave the verdict "outdated").
        if not self._usb_pending_fingerprint:
            return
        mounts = pioneer_usb_mounts()
        if len(mounts) != 1:
            return
        stick_gen = read_stick_generation(mounts[0])
        if stick_gen:
            write_usb_stamp(stick_gen, self._usb_pending_fingerprint)

    def _maybe_check_rb_reads(self):
        # Mirrors _maybe_detect_export_state: menu render reads the cached row
        # instantly; a daemon thread refreshes it (codesign shells out, so the
        # check must never run on the AppKit main thread).
        if self._rb_reads_in_progress:
            return
        if (time.monotonic() - self._rb_reads_at) < RB_READS_MAX_AGE_SECONDS:
            return
        self._rb_reads_in_progress = True
        # Paint the initial state immediately.  refresh_ rendered once before
        # reaching this method, so without this repaint a cold launch exposed
        # an actionable "Patch Rekordbox" label until the next one-second tick.
        self._render_patch_rb_state()
        threading.Thread(target=self._run_rb_reads_check, daemon=True).start()

    def _run_rb_reads_check(self):
        verdict, _detail = _rb_reads_verdict()
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishRbReadsCheck:", verdict, False,
        )

    def finishRbReadsCheck_(self, verdict):
        self._rb_reads_state = str(verdict)
        self._rb_reads_at = time.monotonic()
        self._rb_reads_in_progress = False
        item = getattr(self, "rb_reads_status_item", None)
        if item is not None:
            item.setTitle_(rb_reads_status_title(self._rb_reads_state))
        self._render_patch_rb_state()

    def _render_patch_rb_state(self):
        # Single owner of the Patch Rekordbox title + enabled state. In-progress
        # wins so a periodic refresh / entitlement completion cannot overwrite
        # "Patching Rekordbox…" with a stale normal title.
        if getattr(self, "patch_rekordbox_item", None) is None:
            return
        state = self._rb_reads_state
        if (
            self._rb_reads_in_progress
            and not self._rb_reads_at
            and state == "unknown"
        ):
            state = "checking"
        self.patch_rekordbox_item.setTitle_(
            patch_rb_button_text(self._patch_rb_in_progress, state))
        self.patch_rekordbox_item.setEnabled_(
            patch_rb_button_enabled(self._patch_rb_in_progress, state))

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
        verify_rb_reads=False,
        combined_log=False,
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
        failure alert) back to the main thread. verify_rb_reads additionally
        re-checks the get-task-allow entitlement on exit 0 (on the watcher
        thread — codesign shells out) so the completion dialog reports verified
        ground truth, never an exit-code guess."""
        err_path = None
        err_fh = subprocess.DEVNULL
        try:
            log_dir = _child_error_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            err_path = log_dir / (
                "streamdeck.log" if combined_log else f"{label}.err.log"
            )
            # Truncate per spawn ("wb"): _watch_child reads this file's tail to
            # decide whether THIS start crashed. Appending would let a previous
            # crash's traceback trigger a false alert on a later clean start.
            err_fh = open(err_path, "ab" if combined_log else "wb")
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
                stdout=err_fh if combined_log else subprocess.DEVNULL,
                stderr=subprocess.STDOUT if combined_log else err_fh,
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
                    verify_rb_reads,
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
        verify_rb_reads=False,
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
        if verify_rb_reads and payload["returncode"] == 0:
            # Ground truth on THIS thread (codesign shells out; never main-thread):
            # the completion selector only renders the verdict carried here.
            verdict, detail = _rb_reads_verdict()
            payload["verify"] = {"verdict": verdict, "detail": detail}
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
        if attr == "update_usb_item":
            # BEFORE the early returns below, so every completion path (success,
            # failure, spawn error, signal death) resets the busy flag.
            self._usb_rebuild_in_progress = False
            if payload.get("returncode", 0) == 0:
                self._record_usb_rebuild_stamp()
            self._usb_pending_fingerprint = None
            self._usb_detect_at = 0.0  # stick changed — force a fresh detection
            self._usb_mounts_key = None
            self._render_usb_state()
        if attr == "patch_rekordbox_item":
            # Every completion path resets the patch busy flag. Exit-0 verify
            # renders from the verified verdict inside _show_rb_reads_verdict
            # (never from the exit code alone); other paths re-render now.
            self._patch_rb_in_progress = False
            if not payload.get("verify"):
                self._render_patch_rb_state()
        returncode = payload.get("returncode", 0)
        if returncode == 0:
            verify = payload.get("verify")
            if verify:
                self._show_rb_reads_verdict(verify, payload.get("err_path") or "")
                return
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

    def _show_rb_reads_verdict(self, verify, err_path):
        """Verified completion dialog for the Rekordbox target patch (exit 0 only).

        Native NSAlert, not an osascript notification — TCC can silently hide
        notifications on a foreign Mac. The verdict was computed on the watcher
        thread; here we only render it and refresh the Patch Rekordbox action.
        Never silent, and never describes the target check as live-read proof."""
        verdict = verify.get("verdict")
        detail = verify.get("detail") or ""
        # Reuse the entitlement updater (already main-thread here) so the action
        # title/enabled state is correct the moment the alert shows.
        self.finishRbReadsCheck_(
            verdict if verdict in ("enabled", "not_enabled") else "unknown"
        )
        if verdict == "enabled":
            # Exit 0 covers both a fresh apply and "already present"; never claim
            # a fresh install. finishRbReadsCheck_ still paints Patched only on
            # this positive entitlement verdict.
            title = "Rekordbox target patch verified"
            body = (
                f"The target get-task-allow entitlement is present on {detail}.\n\n"
                "That proves the Rekordbox target patch only; it does not prove a "
                "live attach. Stock Apple-Silicon foreign-Mac attach after a "
                "successful patch + deep verify + GTA=true + relaunch is "
                "live-unvalidated / unknown — not a confirmed caller-authorization "
                "blocker (AWR-222). On this Mac, only the running bridge log can "
                'confirm a live attach; watch for "RB reads blocked".'
            )
        elif verdict == "not_enabled":
            title = "Rekordbox target patch did not take effect"
            body = (
                "The helper finished, but the re-signing did not take effect — "
                f"Rekordbox still lacks the get-task-allow entitlement on {detail}."
            )
            if err_path:
                body += f"\n\nFull log: {err_path}"
        else:
            title = "Rekordbox target patch: could not verify"
            body = (
                "The helper finished, but the result could not be verified: "
                f"{detail or 'unknown reason'}."
            )
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(body)
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
        if proc is None:
            return False
        if proc.poll() is not None:
            self._frozen_bridge_proc = None
            return False
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._frozen_bridge_proc = None
        return True

    def _ensure_frozen_streamdeck(self) -> None:
        """Keep one packaged Stream Deck helper beside a running frozen bridge."""
        proc = getattr(self, "_frozen_streamdeck_proc", None)
        if proc is not None and proc.poll() is None:
            return
        self._frozen_streamdeck_proc = None
        if _running_streamdeck_pid() is not None:
            return
        now = time.monotonic()
        if now < getattr(self, "_streamdeck_retry_at", 0.0):
            return
        self._streamdeck_retry_at = now + 3.0
        try:
            self._frozen_streamdeck_proc = self._spawn_watched(
                [sys.executable, "--run-streamdeck"],
                label="frozen_streamdeck_start",
                combined_log=True,
            )
        except Exception as exc:
            self.showChildFailure_(
                _format_child_failure("frozen_streamdeck_start", 1, str(exc))
            )

    def _stop_frozen_streamdeck(self) -> bool:
        """Stop the owned or safely adopted helper before stopping the bridge."""
        proc = getattr(self, "_frozen_streamdeck_proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            self._frozen_streamdeck_proc = None
            return True
        self._frozen_streamdeck_proc = None

        pid = _running_streamdeck_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
        deadline = time.monotonic() + 5.0
        while _running_streamdeck_pid() == pid and time.monotonic() < deadline:
            time.sleep(0.05)
        if _running_streamdeck_pid() == pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return True

    def _toggle_bridge_frozen(self) -> None:
        # Frozen bundle only: the menubar owns the bridge as its OWN child
        # process (a re-exec of this binary with --run-bridge). No pkill / no
        # pattern matching -- a frozen bridge's argv doesn't match the
        # source-run regexes, and the exclusive flock is the real
        # single-instance guard. M1 is launch-on-click with no auto-restart;
        # M2 finalizes the frozen lifecycle (see the runbook).
        owned = getattr(self, "_frozen_bridge_proc", None)
        if owned is not None and owned.poll() is None:
            self._stop_frozen_streamdeck()
            self._stop_frozen_bridge_child()
            return
        self._stop_frozen_bridge_child()  # discard a completed owned handle
        # No owned child, but a bridge from a PREVIOUS menubar may still hold the
        # lock (pgrep can't see a frozen one). Re-adopt and STOP it by its lockfile
        # pid — validated to be a live bridge, so we never SIGTERM a recycled pid —
        # so the operator is never stuck with a live, uncontrollable bridge holding
        # the Enttec/OS2L port. SIGTERM lets it shut down cleanly and release the
        # flock; the next refresh reflects it, and one bridge is never left running.
        adopted = _running_bridge_pid()
        if adopted is not None:
            self._stop_frozen_streamdeck()
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
        if self._frozen_bridge_proc is not None:
            self._ensure_frozen_streamdeck()
            if not open_live_log():
                self.showLiveLogFailure_(None)

    def toggleBridge_(self, _sender):
        if getattr(sys, "frozen", False):
            if getattr(self, "_install_required", False):
                return
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

    def openLiveLog_(self, _sender):
        if not open_live_log():
            self.showLiveLogFailure_(None)

    def showLiveLogFailure_(self, _sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("The live log couldn't open")
        alert.setInformativeText_(
            "Allow RBSS Bridge to control Terminal in System Settings → "
            "Privacy & Security → Automation, then choose Open Live Log again. "
            "The bridge keeps running."
        )
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def _bridge_fully_off(self) -> bool:
        proc = getattr(self, "_frozen_bridge_proc", None)
        streamdeck_proc = getattr(self, "_frozen_streamdeck_proc", None)
        return (
            bridge_status() == "off"
            and _running_bridge_pid() is None
            and _running_streamdeck_pid() is None
            and (proc is None or proc.poll() is not None)
            and (streamdeck_proc is None or streamdeck_proc.poll() is not None)
        )

    def _require_bridge_off(self, operation: str) -> bool:
        if self._bridge_fully_off():
            return True
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Stop the bridge first")
        alert.setInformativeText_(
            f"The bridge must be fully off before {operation}. Stop it from this "
            "menu, wait until it says Bridge Off, then try again."
        )
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        return False

    def installOnMac_(self, _sender):
        if self._install_in_progress:
            return
        if not self._require_bridge_off("installing or updating this Mac"):
            return
        action_title = getattr(self, "_install_action_title", "Install on This Mac…")
        verb = action_title.split()[0]
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"{verb} RBSS Bridge on this Mac?")
        alert.setInformativeText_(
            "Copies the app to ~/Applications and installs the lighting payload "
            "(pre-analyzed tracks, configs, Govee key) into Application Support. "
            "The bridge never starts by itself — you still start it from this menu."
        )
        alert.addButtonWithTitle_(verb)
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        self._install_in_progress = True
        self.install_item.setEnabled_(False)
        self.install_item.setTitle_({
            "Install": "Installing…",
            "Update": "Updating…",
            "Retry": "Retrying…",
        }.get(verb, "Working…"))
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
            from rb_ss_bridge_v2.install_controller import (
                APP_SUPPORT_DIR,
                INCOMPLETE_MARKER_NAME,
                MANIFEST_NAME,
                install_action_title,
                operator_install_failure_message,
            )

            self._install_action_title = install_action_title(
                (APP_SUPPORT_DIR / MANIFEST_NAME).exists(),
                (APP_SUPPORT_DIR / INCOMPLETE_MARKER_NAME).exists(),
            )
            self.install_item.setTitle_(self._install_action_title)
            self.install_item.setEnabled_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Install didn't finish")
            alert.setInformativeText_(
                operator_install_failure_message(
                    str(payload.get("failed_step") or "")
                )
            )
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return
        # Offer to eject, then quit this DMG-run copy. The installed menu opens
        # one second later, after this process releases the menubar singleton
        # lock; opening it here can merely activate this DMG copy and strand the
        # user with no installed menubar after termination.
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
                delayed_detach_argv(mount),
                start_new_session=True,
            )
        subprocess.Popen(
            installed_relaunch_argv(payload["app_dest"]),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        NSApplication.sharedApplication().terminate_(self)

    def purgeBridge_(self, _sender):
        if self._purge_in_progress:
            return
        if not self._require_bridge_off("purging this Mac"):
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
        threading.Thread(target=self._run_purge, daemon=True).start()

    def updateUsbBridge_(self, _sender):
        if not self._require_bridge_off("rebuilding the USB bridge"):
            return
        mounts = pioneer_usb_mounts()
        if len(mounts) != 1:
            alert = NSAlert.alloc().init()
            if not mounts:
                alert.setMessageText_("No Rekordbox USB found")
                alert.setInformativeText_(
                    "Connect one USB containing a PIONEER folder, then try again."
                )
            else:
                alert.setMessageText_("More than one Rekordbox USB found")
                alert.setInformativeText_(
                    "Leave only the USB you want to rebuild connected: "
                    + ", ".join(path.name for path in mounts)
                )
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return
        mount = mounts[0]
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"Rebuild RBSS Bridge on {mount.name}?")
        alert.setInformativeText_(
            "This creates a fresh DMG and updates the show payload and phrase "
            "memory on that USB."
        )
        alert.addButtonWithTitle_("Rebuild")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        self._usb_rebuild_in_progress = True
        # Capture the source fingerprint NOW: stamping a post-build fingerprint
        # would fold in any edit made DURING the multi-minute build and falsely
        # mark a stick built from older sources as up to date.
        self._usb_pending_fingerprint = usb_source_signature()
        self._render_usb_state()
        self._spawn_watched(
            ["bash", str(REPO_ROOT / "packaging" / "make_stick.sh"), str(mount)],
            label="update_usb_bridge",
            busy_item_attr="update_usb_item",
            busy_title="Rebuilding USB Bridge…",
            success_message=(
                f"USB Bridge, show payload, and phrase memory rebuilt on {mount.name}."
            ),
            failure_title="USB Bridge rebuild failed",
        )

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
                f"moves to the Trash and this removed app closes. "
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
        # Re-sign the Rekordbox target with get-task-allow (TimecodeLink-style
        # target-patch mechanism). Positive entitlement ≠ live attach proof;
        # stock foreign-Mac attach after clean patch+verify+GTA+relaunch remains
        # live-unvalidated / unknown (AWR-222). Admin UI stays off the menubar thread.
        if self._patch_rb_in_progress:
            return
        if getattr(sys, "frozen", False):
            argv = [sys.executable, "--patch-rekordbox"]
        else:
            argv = [sys.executable, str(REPO_ROOT / "usb_launcher.py"), "--patch-rekordbox"]
        self._patch_rb_in_progress = True
        self._render_patch_rb_state()
        self._spawn_watched(
            argv,
            label="patch_rekordbox",
            busy_item_attr="patch_rekordbox_item",
            busy_title="Patching Rekordbox…",
            failure_title="Rekordbox target patch failed",
            # Exit 0 alone doesn't prove the re-sign took: the watcher re-checks
            # the entitlement and the completion dialog reports that verdict.
            verify_rb_reads=True,
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

    def restartMenubar_(self, _sender):
        argv = restart_menubar_argv()
        if not argv:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Menubar restart unavailable")
            alert.setInformativeText_("The running app bundle could not be located.")
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return
        subprocess.Popen(
            argv,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_system_env(),
        )
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
