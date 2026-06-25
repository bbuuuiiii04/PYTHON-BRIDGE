#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import objc
from AppKit import (
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


WATCHER = "/Users/bbui/ss_bridge_watcher.sh"
MENUBAR_PATTERN = r"^[^[:space:]]*(python3|Python)[^[:space:]]*[[:space:]]+/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar\.py$"
BRIDGE_PATTERN = r"^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$"
WATCHER_PATTERN = r"^(/bin/bash|bash)[[:space:]]+/Users/bbui/ss_bridge_watcher\.sh$"
MONITOR_PATTERN = r"RBSS_BRIDGE_MONITOR|^tail -n 100 -F /tmp/bridge\.log$"
MANUAL_LAUNCHCTL_LABEL = "rbss_bridge_manual"
STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"
COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
LASER_PAD_URL = "http://127.0.0.1:8765"
RECORDING_PATH_TEMPLATE = "/tmp/rbss-session-{stamp}.jsonl"
EXPORT_PROCESS_TIMEOUT_SECONDS = 120.0
EXPORT_RELOAD_TIMEOUT_SECONDS = 8.0
EXPORT_RELOAD_POLL_SECONDS = 0.25
EXPORT_WORKING_DIRECTORY = str(Path(__file__).resolve().parents[2])
CANONICAL_SOURCE_PROJECT = str(Path("~/Music/SoundSwitch/default.ssproj").expanduser())
CANONICAL_PACK_DIR = Path("~/Music/SoundSwitch/rbss_canonical_pack").expanduser()
DETECT_MAX_AGE_SECONDS = 30.0
_SIDECAR_SUFFIX = ".source.json"

ICON_DIR = Path("/Users/bbui")
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


def _source_content_fingerprint(project: str | os.PathLike[str]) -> str | None:
    """Exact change signal: sha256 over sorted (relpath, sha256(file bytes)) of
    every regular file in the bundle. Returns None if the bundle is absent."""
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
            try:
                data = path.read_bytes()
            except OSError:
                return None  # unreadable source -> treat as "cannot prove up-to-date"
            rel = path.relative_to(base).as_posix()
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
    current = _source_content_fingerprint(CANONICAL_SOURCE_PROJECT)
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


def already_running() -> bool:
    result = subprocess.run(["pgrep", "-f", MENUBAR_PATTERN], capture_output=True, text=True)
    pids = [p for p in result.stdout.strip().split("\n") if p and int(p) != os.getpid()]
    return len(pids) > 0


def watcher_running() -> bool:
    result = subprocess.run(["pgrep", "-f", WATCHER_PATTERN], capture_output=True)
    return result.returncode == 0


def bridge_pids() -> list[str]:
    result = subprocess.run(["pgrep", "-f", BRIDGE_PATTERN], capture_output=True, text=True)
    return [pid for pid in result.stdout.strip().splitlines() if pid]


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


def pack_toggle_line(pack_status: dict, *, bridge_status: str | None = None) -> tuple[str, bool]:
    """(title, clickable) for the Lighting Pack on/off item.

    Pure: derived only from the copied snapshot. The menu never drives DMX —
    clicking only enqueues a set_soundswitch_pack command for the bridge.
    """
    if bridge_status == "off":
        return "Lighting Pack: bridge off", False
    pack = pack_status if isinstance(pack_status, dict) else {}
    if not pack.get("available") or pack.get("reason") == "not_configured":
        return "Lighting Pack: not configured", False
    if pack.get("enabled"):
        return "Lighting Pack: On  (click to turn off)", True
    return "Lighting Pack: Off  (click to turn on)", True


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
        "autoloop_phase_blocked": "autoloop blocked",
        "software_zero_frame": "zeroed",
    }.get(pack.get("operational_state"), "unknown")
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


def default_recording_path() -> str:
    return RECORDING_PATH_TEMPLATE.format(stamp=time.strftime("%Y%m%d-%H%M%S"))


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
    bridge_row = _join(
        _seg("●  ", color=_cg()),
        _seg("BRIDGE", bold=True),
        _seg(f"  D{active} Active", color=_cs()),
        multi_seg,
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

    return [bridge_row, ss_row] + deck_rows + [checks_row, smart_row, laser_row]


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
        self.status_rows = []
        for _ in range(9):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
            item.setEnabled_(False)
            self.menu.addItem_(item)
            self.status_rows.append(item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.toggle_item = self._add_action("", "toggleBridge:")

        self.export_item = self._add_action("Export", "exportFromSS:")
        self.export_status_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "", None, ""
        )
        self.export_status_item.setEnabled_(False)
        self.menu.addItem_(self.export_status_item)
        
        self.smart_phrasing_menu = NSMenu.alloc().init()
        self.smart_phrasing_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Smart Phrasing", None, "")
        self.smart_phrasing_item.setSubmenu_(self.smart_phrasing_menu)
        self.menu.addItem_(self.smart_phrasing_item)
        
        self.smart_drop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Smart Drops", "toggleSmartDrop:", "")
        self.smart_drop_item.setTarget_(self)
        self.smart_phrasing_menu.addItem_(self.smart_drop_item)
        
        self.smart_breakdown_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Smart Breakdowns", "toggleSmartBreakdown:", "")
        self.smart_breakdown_item.setTarget_(self)
        self.smart_phrasing_menu.addItem_(self.smart_breakdown_item)

        self.laser_menu = NSMenu.alloc().init()
        self.laser_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Laser Director", None, "")
        self.laser_item.setSubmenu_(self.laser_menu)
        self.menu.addItem_(self.laser_item)

        self.laser_toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Laser Director", "toggleLaserDirector:", ""
        )
        self.laser_toggle_item.setTarget_(self)
        self.laser_menu.addItem_(self.laser_toggle_item)

        self.laser_blackout_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Emergency Blackout", "laserBlackout:", ""
        )
        self.laser_blackout_item.setTarget_(self)
        self.laser_menu.addItem_(self.laser_blackout_item)

        self.laser_clear_blackout_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Clear Blackout", "laserClearBlackout:", ""
        )
        self.laser_clear_blackout_item.setTarget_(self)
        self.laser_menu.addItem_(self.laser_clear_blackout_item)

        self.laser_menu.addItem_(NSMenuItem.separatorItem())

        self.laser_scene_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.laser_scene_item.setEnabled_(False)
        self.laser_menu.addItem_(self.laser_scene_item)

        self.laser_reason_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.laser_reason_item.setEnabled_(False)
        self.laser_menu.addItem_(self.laser_reason_item)

        self.laser_personality_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.laser_personality_item.setEnabled_(False)
        self.laser_menu.addItem_(self.laser_personality_item)

        self.laser_midi_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.laser_midi_item.setEnabled_(False)
        self.laser_menu.addItem_(self.laser_midi_item)

        self.laser_phrasing_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        self.laser_phrasing_item.setEnabled_(False)
        self.laser_menu.addItem_(self.laser_phrasing_item)

        self.menu.addItem_(NSMenuItem.separatorItem())
        self.validation_item = self._add_action("Run Health Check", "runValidation:")
        self.record_session_item = self._add_action("Record Session: Off", "toggleRecordSession:")
        self.map_lasers_item = self._add_action("Laser Pad…", "mapLasers:")
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.quit_item = self._add_action("Quit Menu", "quit:")
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

    def refresh_(self, _timer):
        self._snapshot = read_status()
        pids = bridge_pids()
        status = _bridge_status_from_pids(pids)
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
        self._adapt_timer(status)

    def _render_export_state(self):
        self.export_item.setTitle_(
            export_button_text(self._export_in_progress, self._export_up_to_date))
        self.export_item.setEnabled_(
            not self._export_in_progress and not self._export_up_to_date)
        self.export_status_item.setTitle_(
            pack_export_status_line(
                self._snapshot.get("soundswitch_pack", {}),
                stale=not self._snapshot or bool(self._snapshot.get("stale")),
                export_phase=self._export_phase,
                export_state=self._export_state,
                export_up_to_date=self._export_up_to_date,
                export_result=self._export_result,
                bridge_status=self._status,
            ))

    def _maybe_detect_export_state(self):
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
        image = NSImage.alloc().initByReferencingFile_(ICONS[status])
        if image is not None:
            image.setTemplate_(True)
            image.setSize_(NSMakeSize(16, 16))
            button.setImage_(image)
            button.setImagePosition_(NSImageLeft)
        else:
            button.setImage_(None)

    def toggleBridge_(self, _sender):
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

    def mapLasers_(self, _sender):
        open_browser_url(LASER_PAD_URL)

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
        NSApplication.sharedApplication().terminate_(self)


if __name__ == "__main__":
    if already_running():
        sys.exit(0)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = BridgeMenuBar.alloc().init()
    app.run()
