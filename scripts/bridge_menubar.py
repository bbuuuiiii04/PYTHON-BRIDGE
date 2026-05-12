#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
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

from command_builders import build_laser_wizard_command


WATCHER = "/Users/bbui/ss_bridge_watcher.sh"
MENUBAR_PATTERN = r"^[^[:space:]]*(python3|Python)[^[:space:]]*[[:space:]]+/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar\.py$"
BRIDGE_PATTERN = r"^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$"
WATCHER_PATTERN = r"^(/bin/bash|bash)[[:space:]]+/Users/bbui/ss_bridge_watcher\.sh$"
MONITOR_PATTERN = r"RBSS_BRIDGE_MONITOR|^tail -n 100 -F /tmp/bridge\.log$"
MANUAL_LAUNCHCTL_LABEL = "rbss_bridge_manual"
STATUS_PATH = "/tmp/rb_ss_bridge_v2_status.json"
COMMANDS_PATH = "/tmp/rb_ss_bridge_v2_commands.jsonl"
LASER_WIZARD_CMD = build_laser_wizard_command(Path(__file__))

ICON_DIR = Path("/Users/bbui")
ICONS = {
    "off": str(ICON_DIR / "bridge_icon_off.png"),
    "initializing": str(ICON_DIR / "bridge_icon_initializing.png"),
    "on": str(ICON_DIR / "bridge_icon_on.png"),
}


_FONT_SZ = 13.0
_FONT_NORM = None   # resolved lazily
_FONT_BOLD = None


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


def open_terminal_command(command: str, title: str = "RBSS_LASER_WIZARD") -> None:
    safe_cmd = command.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Terminal" to activate\n'
        f'tell application "Terminal" to do script "{safe_cmd}"'
    )
    subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
        ]

    sm = status.get("state_manager", {})
    ss = status.get("soundswitch", {})
    validation = status.get("validation", {})
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

    return [bridge_row, ss_row] + deck_rows + [checks_row, smart_row]


class BridgeMenuBar(NSObject):
    def init(self):
        self = objc.super(BridgeMenuBar, self).init()
        if self is None:
            return None
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.menu = NSMenu.alloc().init()
        self.status_rows = []
        for _ in range(8):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
            item.setEnabled_(False)
            self.menu.addItem_(item)
            self.status_rows.append(item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.toggle_item = self._add_action("", "toggleBridge:")
        
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
        self.menu.addItem_(NSMenuItem.separatorItem())
        self.validation_item = self._add_action("Run Health Check", "runValidation:")
        self.map_lasers_item = self._add_action("Map Lasers", "mapLasers:")
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
        smart_drop_on = bool(self._snapshot.get("state_manager", {}).get("smart_drop_enabled"))
        self.smart_drop_item.setTitle_("Smart Drops: On" if smart_drop_on else "Smart Drops: Off")
        smart_breakdown_on = bool(self._snapshot.get("state_manager", {}).get("smart_breakdown_enabled"))
        self.smart_breakdown_item.setTitle_("Smart Breakdowns: On" if smart_breakdown_on else "Smart Breakdowns: Off")
        self._adapt_timer(status)

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

    def mapLasers_(self, _sender):
        open_terminal_command(LASER_WIZARD_CMD)

    def toggleSmartDrop_(self, _sender):
        append_command({"cmd": "toggle_smart_drop"})
        self.refresh_(None)

    def toggleSmartBreakdown_(self, _sender):
        append_command({"cmd": "toggle_smart_breakdown"})
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
