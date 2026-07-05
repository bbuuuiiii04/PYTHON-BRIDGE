"""
bridge_view.py -- read-only terminal viewer for the rb_ss_bridge_v2 JSONL
event stream (AWR-125, Task W6).

Two strictly separated layers:

* Pure layer (top half of this module): parse_record, lens_of, format_line,
  FRIENDLY, LatchState, format_age, parse_filter/filter_matches. Every
  function here is unit-testable without a terminal -- see
  tests/test_bridge_view.py.
* Curses layer (bottom half): a thin rendering/input shell over the pure
  layer. Not unit-tested (no terminal in CI); kept deliberately simple so
  correctness is visible by inspection.

Read-only, disposable, and crash-isolated from the bridge: it opens the
current run's JSONL file, reads to EOF, then follows by polling (~100 ms),
reopening on inode change (log rotation / bridge restart). It never writes to
the stream and never touches the bridge process -- closing or crashing this
viewer has zero effect on the show.

Acceptance criteria this file implements: docs/architecture/logging_authority.md
("Operator experience contract") and docs/plans/active/logging_overhaul_design.md
Section 2.7 (screens/keys/the nine-rule ADHD-first readability contract).

Importing this module has no side effects (mirrors bridge_log.py): all
terminal setup happens in main() via curses.wrapper(). bridge_log is imported
only for resolve_log_dir(); this module never calls bridge_log.init() --
it is a reader, never a writer of the stream.
"""
from __future__ import annotations

import argparse
import curses
import json
import os
import re
import select
import sys
import time
import traceback
from collections import deque
from pathlib import Path
from typing import Any

try:
    # Package context (tests run from the repo's parent dir, proof-gate style).
    from rb_ss_bridge_v2 import bridge_log
except ImportError:
    # Script context (the watcher launches this file directly).
    import bridge_log


# ═══════════════════════════════════════════════════════════════════════════
# Pure layer -- unit-tested in tests/test_bridge_view.py, no terminal needed.
# ═══════════════════════════════════════════════════════════════════════════

_LEVEL_NO: dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def _str_field(rec: dict[str, Any], key: str) -> str:
    """Return rec[key] if it's a string, else "" -- never raises on odd JSON."""
    value = rec.get(key)
    return value if isinstance(value, str) else ""


def _level_no(rec: dict[str, Any]) -> int:
    """Numeric level for rec["lvl"]; 0 (below DEBUG) for missing/unknown/bad-typed."""
    lvl = rec.get("lvl")
    if isinstance(lvl, str):
        return _LEVEL_NO.get(lvl, 0)
    return 0


def parse_record(line: str) -> dict[str, Any] | None:
    """Parse one JSONL line into a record dict.

    Tolerant by design (docs/architecture/logging_authority.md: "Unknown
    fields and categories must be tolerated by every reader"): returns None
    -- never raises -- for a blank line, a truncated/malformed line (the
    file-follower may hand this a bridge-death partial write), or JSON that
    doesn't decode to an object. Unknown/extra keys pass through untouched;
    this function enforces no schema.
    """
    line = line.strip()
    if not line:
        return None
    try:
        rec = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    return rec


# Legacy (not-yet-namespaced) infra modules whose stdlib log.* records should
# still surface in SYSTEM. One tuple, read side only (design doc Section 2.1);
# it shrinks as more of these modules migrate to perf.*/health.* emits.
#
# Entries are the modules' ACTUAL logger names, each verified against its
# `logging.getLogger(...)` call — note rb_state_reader.py names its logger
# "rb_state" (rb_state_reader.py:58), so that is the entry here (the W6 spec's
# draft said "rb_state_reader"; corrected at orchestrator review 2026-07-04).
LEGACY_INFRA = (
    "rb_memory", "rb_state", "live_bpm", "mtc_reader",
    "osl_output", "os2l_injector", "runtime_status", "bridge", "diagnostics",
)


def lens_of(rec: dict[str, Any]) -> set[str]:
    """Return the set of lens names *rec* belongs to (membership can overlap).

    PERFORMANCE = cat starts with "perf."
    OPERATOR    = levelno >= WARNING, or cat starts with "health."
    SYSTEM      = cat starts with ("sys.", "health."), or (src is a legacy
                  infra module AND levelno >= INFO -- see deviation note)
    DEBUG       = always (the firehose lens)

    DEVIATION (reported, reasoned -- see final handoff report): the spec's
    literal SYSTEM predicate is "cat.startswith(('sys.','health.')) or src in
    LEGACY_INFRA" with no level qualifier on the second clause. Taken
    literally, a DEBUG-level record from a legacy-infra module -- e.g.
    rb_memory's per-candidate spam, whose src IS exactly "rb_memory"
    (confirmed logging.getLogger("rb_memory") at rb_memory.py:40) -- would
    also match SYSTEM. That contradicts (a) this same task's explicit
    required test ("a DEBUG record with cat rb_memory ... routes to the
    DEBUG lens ONLY", spec Part B Task W6) and (b) the design doc's own
    general guarantee ("a chatty or badly-logged subsystem can pollute MAX
    DEBUG only", logging_overhaul_design.md Section 2.1). Gating the
    LEGACY_INFRA branch on levelno >= INFO resolves both without losing
    intended signal: every named SYSTEM-relevant event from these modules
    (attach, RB gone, drift, queue drops) is INFO/WARNING/ERROR already, or
    migrates to an explicit health.* cat that matches the first clause
    directly. DEBUG-level content is, by construction, the forensic-only
    firehose this whole design exists to contain -- consistent with every
    other lens here already being level-aware.
    """
    cat = _str_field(rec, "cat")
    src = _str_field(rec, "src")
    levelno = _level_no(rec)

    lenses = {"DEBUG"}
    if cat.startswith("perf."):
        lenses.add("PERFORMANCE")
    if levelno >= _LEVEL_NO["WARNING"] or cat.startswith("health."):
        lenses.add("OPERATOR")
    if cat.startswith(("sys.", "health.")) or (
        src in LEGACY_INFRA and levelno >= _LEVEL_NO["INFO"]
    ):
        lenses.add("SYSTEM")
    return lenses


# Friendly display names for known categories (design doc Section 2.1 rule 6:
# plain words, never codes). Unmapped categories fall back to their raw
# cat/src string verbatim -- a new perf.*/health.* category routes itself
# with no viewer change required (the "extension rule",
# docs/architecture/logging_authority.md).
FRIENDLY: dict[str, str] = {
    "perf.deck": "deck",
    "perf.drop": "drop",
    "perf.laser.scene": "laser",
    "perf.laser.fired": "laser",
    "perf.laser.personality": "laser",
    "perf.led.look": "led",
    "perf.led.palette": "led",
    "perf.autoloop": "autoloop",
    "perf.scripted": "scripted",
    "perf.ss": "ss",
    "perf.override": "override",
    "perf.heartbeat": "heartbeat",
    "health.os2l": "os2l",
    "health.midi": "midi",
    "health.dmx": "dmx",
    "health.govee.cloud": "govee",
    "health.govee.rt": "govee-rt",
    "health.rb": "rb",
    "health.reader": "reader",
    "health.queue": "queue",
    "health.tick": "tick",
    "health.thread": "thread",
    "sys.boot": "boot",
    "sys.shutdown": "shutdown",
    "sys.thread": "thread",
    "sys.cmd": "cmd",
    "sys.tick": "tick",
    "sys.config": "config",
    "sys.log": "log",
    "sys.crash": "crash",
    # Legacy stdlib records carry cat == logger name (module). Map the known
    # ones to plain words (rule 6) so e.g. "soundswitch_midi_input" doesn't
    # blow out the surface column and read as code.
    "soundswitch_midi_input": "soundswitch",
    "osl_output": "soundswitch",
    "os2l_injector": "soundswitch",
    "state_manager": "bridge",
    "runtime_status": "bridge",
    "diagnostics": "bridge",
    "live_bpm": "bpm",
    "rb_memory": "rekordbox",
    "rb_state": "rekordbox",
    "pyrekordbox.db6.database": "rekordbox",
    "pyrekordbox.anlz.file": "rekordbox",
    "mtc_reader": "timecode",
    "laser_config": "laser",
    "led_config": "led",
    "enttec_dmx_pro": "dmx",
}

# Surfaces that carry a stable identity hue in the feed (rule 5). The hue
# itself lives in the curses layer's _ATTR_MAP ("surface:<name>" keys) so
# taste tweaks touch exactly one map; heartbeat is absent (header-only).
_SURFACE_HUED = frozenset(
    {"deck", "drop", "laser", "led", "autoloop", "scripted", "ss", "override"}
)

_TIME_WIDTH = 10   # "21:14:03.5"
_DECK_WIDTH = 3    # "D1 " / "D12" / "   " (blank-padded when absent)
_SURFACE_WIDTH = 11  # widest friendly name ("soundswitch"); longer names hard-cap
_ELLIPSIS = "…"

_CODE_PREFIX_RE = re.compile(r"^(?:\s*\[[A-Za-z0-9_.-]+\])+\s*")


def display_msg(msg: Any) -> str:
    """Message text with legacy [CODE][PREFIX] blocks stripped for display.

    Rule 6 (plain words, never codes): old-style modules still write
    "[SS-MIDI] input port gone" — the bracket codes duplicate the surface
    column and read as noise mid-set. Display-only: the stream on disk is
    untouched, agents keep the raw text.
    """
    return _CODE_PREFIX_RE.sub("", str(msg))


def _format_time(ts: Any) -> str:
    """HH:MM:SS.d (deciseconds) in local time; a placeholder on bad input."""
    try:
        t = float(ts)
        struct = time.localtime(t)
        tenths = int((t % 1) * 10)  # t % 1 is always in [0, 1) even for t < 0
    except (TypeError, ValueError, OverflowError, OSError):
        return "-" * _TIME_WIDTH
    return f"{struct.tm_hour:02d}:{struct.tm_min:02d}:{struct.tm_sec:02d}.{tenths}"


def _surface_of(rec: dict[str, Any]) -> str:
    """Friendly one-word surface name for a record (rule 6: plain words)."""
    cat = _str_field(rec, "cat") or _str_field(rec, "src")
    return FRIENDLY.get(cat, cat) or "?"


def _truncate_segments(
    segments: list[tuple[str, str]], width: int
) -> list[tuple[str, str]]:
    """Truncate a segment list to *width* rendered columns, ellipsis-suffixed.

    Never wraps (rule 3): cuts mid-segment if needed and always reserves one
    column for the trailing "…" once truncation is necessary.
    """
    if width <= 0:
        return []
    total = sum(len(text) for text, _ in segments)
    if total <= width:
        return segments
    if width == 1:
        return [(_ELLIPSIS, "dim")]
    budget = width - 1
    out: list[tuple[str, str]] = []
    used = 0
    for text, attr in segments:
        remaining = budget - used
        if remaining <= 0:
            break
        if len(text) <= remaining:
            out.append((text, attr))
            used += len(text)
        else:
            out.append((text[:remaining], attr))
            used += remaining
            break
    out.append((_ELLIPSIS, "dim"))
    return out


def format_line(rec: dict[str, Any], width: int) -> list[tuple[str, str]]:
    """Render one record as ordered (text, attr_key) segments.

    Fixed columns: "HH:MM:SS.s  D<deck>  <surface>  <payload> (<reason>) @b<beat>"
    (design doc Section 2.7 / spec Part B Task W6). attr_key is "dim"
    (plumbing -- timestamp, reason, beat) or "bright" (payload -- deck,
    surface, value); rule 4's "most important word is the most visible word".
    Concatenating every segment's text reproduces the literal rendered line;
    the curses layer turns attr_key into a color/attribute via its own
    lookup, so this function stays terminal-free and directly assertable in
    tests.

    Truncates to *width* columns with a trailing "…"; never wraps (rule 3).
    The deck/surface columns are fixed-width and blank-padded when absent so
    the eye can scan columns across lines that do/don't carry a deck (rule 3).
    """
    time_text = _format_time(rec.get("ts"))
    deck = rec.get("deck")
    deck_text = (f"D{deck}" if deck is not None else "").ljust(_DECK_WIDTH)
    surface = _surface_of(rec)
    # Hard-cap so an unmapped long source can never break column alignment.
    surface_text = surface[:_SURFACE_WIDTH].ljust(_SURFACE_WIDTH)
    payload_text = display_msg(rec.get("msg", ""))

    # Rule 5: one surface = one stable hue, and level colors outrank identity
    # hues (yellow = warning, red = broken and ONLY broken). Unknown surfaces
    # (legacy/sys records) stay plain bright so nothing depends on the map.
    lvl = _level_no(rec)
    if lvl >= 40:  # ERROR+
        value_key = "red"
    elif lvl >= 30:  # WARNING
        value_key = "yellow"
    elif surface in _SURFACE_HUED:
        value_key = f"surface:{surface}"
    else:
        value_key = "bright"

    segments: list[tuple[str, str]] = [
        (time_text, "dim"),
        ("  ", "dim"),
        (deck_text, "bright"),
        ("  ", "dim"),
        (surface_text, value_key),
        ("  ", "dim"),
        (payload_text, value_key),
    ]

    data = rec.get("data")
    reason = data.get("reason") if isinstance(data, dict) else None
    if reason:
        segments.append((f" ({reason})", "dim"))

    beat = rec.get("beat")
    if beat is not None:
        segments.append((f" @b{beat}", "dim"))

    return _truncate_segments(segments, width)


def format_age(ts: float, now: float | None = None) -> str:
    """Render how long ago epoch-seconds *ts* was: 'just now'/'5s ago'/'2m ago'/...

    Rule 7 (relative time where it aids judgment): used for staleness and
    latched-problem ages, never for the feed's absolute timestamps. *now* is
    injectable for deterministic tests (mirrors bridge_fmt.log_throttled's
    now= convention); defaults to time.time(). Clock skew (ts in the
    "future") clamps to "just now" rather than showing a negative age.
    """
    if not isinstance(ts, (int, float)):
        return "?"  # corrupt record: tolerate, never crash the viewer
    current = time.time() if now is None else now
    seconds = max(0.0, current - ts)
    if seconds < 1:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = int(seconds // 3600)
    if hours < 24:
        return f"{hours}h ago"
    days = int(seconds // 86400)
    return f"{days}d ago"


def _latch_ts(rec: dict[str, Any]) -> float:
    ts = rec.get("ts")
    return ts if isinstance(ts, (int, float)) else 0.0


def format_strip(latched: list[dict[str, Any]], now: float) -> str:
    """Red OPERATOR-strip text: the NEWEST problem first, plus a count.

    One line must carry the most urgent fact. The old oldest-first " | " join
    let a stale config nag hide a seconds-old failure behind the right edge
    (operator review, 2026-07-05). A single latch renders in full; several
    render as a count + the newest, with the key hints for the rest.
    """
    if len(latched) == 1:
        e = latched[0]
        age = format_age(e.get("ts", now), now=now)
        return f"⚠ {_surface_of(e)} {display_msg(e.get('msg', ''))} ({age}) · a clears"
    newest = max(latched, key=_latch_ts)
    age = format_age(newest.get("ts", now), now=now)
    return (
        f"⚠ {len(latched)} problems · newest: {_surface_of(newest)} "
        f"{display_msg(newest.get('msg', ''))} ({age}) · a clears · 2 lists all"
    )


def parse_filter(text: str) -> dict[str, Any]:
    """Parse a DEBUG-screen filter string into {substring, deck, cat_prefix}.

    Recognizes whitespace-separated `deck=N` and `cat=prefix` tokens (design
    doc Section 2.7); every other token is joined back with a space as a
    plain substring to match against cat/msg (case-insensitive). An
    unparseable `deck=` value (not an int) is treated as ordinary substring
    text rather than raising or silently dropping it.
    """
    deck: int | None = None
    cat_prefix = ""
    leftover: list[str] = []
    for token in text.split():
        if token.startswith("deck="):
            raw = token[len("deck="):]
            try:
                deck = int(raw)
            except ValueError:
                leftover.append(token)
        elif token.startswith("cat="):
            cat_prefix = token[len("cat="):]
        else:
            leftover.append(token)
    return {"substring": " ".join(leftover), "deck": deck, "cat_prefix": cat_prefix}


def filter_matches(filt: dict[str, Any], rec: dict[str, Any]) -> bool:
    """True if *rec* satisfies every clause of a parse_filter() result."""
    deck = filt.get("deck")
    if deck is not None and rec.get("deck") != deck:
        return False
    cat_prefix = filt.get("cat_prefix") or ""
    cat = _str_field(rec, "cat")
    if cat_prefix and not cat.startswith(cat_prefix):
        return False
    substring = (filt.get("substring") or "").lower()
    if substring:
        msg = str(rec.get("msg", ""))
        if substring not in cat.lower() and substring not in msg.lower():
            return False
    return True


class LatchState:
    """Tracks currently-latched WARNING+/health.* problems (design doc Section 2.7).

    note(rec) latches any WARNING+ record (any category) or a health.*
    record at WARNING+; a health.* record BELOW WARNING (the recovery signal
    -- e.g. health("midi", "recovered", lvl=INFO)) clears the latch for that
    exact category. ack() clears every latched category regardless of
    recoverability. A category with no recovery signal -- a plain WARNING/
    ERROR outside health.* -- stays latched until acked, matching "nothing
    important can scroll away, nothing is ever communicated by a transient
    flash alone."
    """

    def __init__(self) -> None:
        self._latched: dict[str, dict[str, Any]] = {}
        self._quiet_since: float = time.time()

    def note(self, rec: dict[str, Any]) -> bool:
        """Update latch state from one incoming record.

        Returns True exactly when a brand-new category latches for the first
        time -- the curses layer's cue to ring the bell once per new latch,
        never on a repeat warning for an already-latched category.
        """
        cat = _str_field(rec, "cat")
        levelno = _level_no(rec)
        is_health = cat.startswith("health.")

        if is_health and levelno < _LEVEL_NO["WARNING"]:
            existed = self._latched.pop(cat, None) is not None
            if existed and not self._latched:
                ts = rec.get("ts")
                self._quiet_since = ts if isinstance(ts, (int, float)) else time.time()
            return False

        if levelno >= _LEVEL_NO["WARNING"]:
            is_new = cat not in self._latched
            self._latched[cat] = rec
            return is_new

        return False

    def ack(self, now: float | None = None) -> None:
        """Clear every latched entry (operator acknowledgement, key 'a')."""
        self._latched.clear()
        self._quiet_since = time.time() if now is None else now

    @property
    def latched(self) -> list[dict[str, Any]]:
        """Currently latched records, oldest-latched category first."""
        return list(self._latched.values())

    @property
    def quiet_since(self) -> float:
        """Epoch seconds of the last transition into 'nothing latched'."""
        return self._quiet_since

    def is_quiet(self) -> bool:
        return not self._latched


# ═══════════════════════════════════════════════════════════════════════════
# Curses layer -- thin rendering/input shell over the pure layer above.
# Not unit-tested (no terminal in CI/tests); kept simple and inspectable.
# ═══════════════════════════════════════════════════════════════════════════

_SCREEN_NAMES = {1: "SHOW", 2: "OPERATOR", 3: "SYSTEM", 4: "DEBUG"}

_ATTR_MAP: dict[str, int] = {}


def _attr_for(key: str) -> int:
    return _ATTR_MAP.get(key, curses.A_NORMAL)


def _init_colors() -> None:
    """Populate _ATTR_MAP: dim/bright plumbing-vs-payload plus the fixed
    green/cyan/yellow/orange/red state vocabulary (rule 5). Degrades to plain
    attributes on a terminal with no color support rather than raising.
    """
    _ATTR_MAP["dim"] = curses.A_DIM
    _ATTR_MAP["bright"] = curses.A_BOLD
    _ATTR_MAP["normal"] = curses.A_NORMAL
    if not curses.has_colors():
        _ATTR_MAP["green"] = curses.A_NORMAL
        _ATTR_MAP["cyan"] = curses.A_NORMAL
        _ATTR_MAP["yellow"] = curses.A_BOLD
        _ATTR_MAP["orange"] = curses.A_BOLD
        _ATTR_MAP["red"] = curses.A_BOLD | curses.A_REVERSE
        for name in _SURFACE_HUED:
            _ATTR_MAP[f"surface:{name}"] = curses.A_BOLD
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    curses.init_pair(1, curses.COLOR_GREEN, bg)
    curses.init_pair(2, curses.COLOR_CYAN, bg)
    curses.init_pair(3, curses.COLOR_YELLOW, bg)
    curses.init_pair(4, curses.COLOR_RED, bg)
    curses.init_pair(5, curses.COLOR_MAGENTA, bg)
    curses.init_pair(6, curses.COLOR_BLUE, bg)
    _ATTR_MAP["green"] = curses.color_pair(1)
    _ATTR_MAP["cyan"] = curses.color_pair(2)
    _ATTR_MAP["yellow"] = curses.color_pair(3)
    # No true "orange" in the base 8-color palette; bold yellow approximates
    # it without assuming 256-color support. Rule 5's hard requirement is red
    # meaning broken and ONLY broken -- the exact orange hue is a nicety.
    _ATTR_MAP["orange"] = curses.color_pair(3) | curses.A_BOLD
    _ATTR_MAP["red"] = curses.color_pair(4) | curses.A_BOLD
    # "dim" via a real grey when the terminal has one: macOS Terminal renders
    # A_DIM as barely-off-white, which collapsed the plumbing/payload contrast
    # (operator report, 2026-07-05). 244 = mid-grey in the xterm-256 palette.
    if curses.COLORS >= 256:
        try:
            curses.init_pair(7, 244, bg)
            _ATTR_MAP["dim"] = curses.color_pair(7)
        except curses.error:
            pass  # keep A_DIM
    # Rule 5, second half: one surface = one stable hue, bold (payload rule 4).
    # Red is NOT in this map -- red stays broken-only; drop uses bold yellow
    # as its identity emphasis (a drop is an attention moment, not a fault).
    _hue = {
        "deck": curses.color_pair(2),      # cyan
        "laser": curses.color_pair(5),     # magenta
        "led": curses.color_pair(1),       # green
        "autoloop": curses.color_pair(6),  # blue
        "scripted": curses.color_pair(6),  # blue
        "ss": curses.color_pair(6),        # blue
        "drop": curses.color_pair(3),      # yellow
        "override": 0,                     # white
    }
    for name in _SURFACE_HUED:
        _ATTR_MAP[f"surface:{name}"] = _hue[name] | curses.A_BOLD


def _draw_segments(win: Any, y: int, x: int, segments: list[tuple[str, str]], max_x: int) -> None:
    cx = x
    for text, attr_key in segments:
        if cx >= max_x or not text:
            continue
        remaining = max_x - cx
        chunk = text[:remaining]
        try:
            win.addstr(y, cx, chunk, _attr_for(attr_key))
        except curses.error:
            pass  # bottom-right-cell write raises on some terminals; harmless
        cx += len(chunk)


class _FileFollower:
    """Read-only follower for current.jsonl (design doc Section 2.7 / spec Part C).

    Reads to EOF, then the caller polls again (~100 ms, driven by the main
    loop's curses timeout -- no sleep lives in this class). Reopens on inode
    change (log rotation / bridge restart). Holds back an incomplete trailing
    line rather than ever handing parse_record a truncated JSON fragment --
    "tolerates" a partial last line by waiting for it, not by guessing at it.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: Any = None
        self._inode: int | None = None
        self._partial = ""

    def poll(self) -> list[str]:
        """Non-blocking: return whatever complete new lines are available now."""
        if self._file is None:
            try:
                self._file = self._path.open("r", encoding="utf-8")
                self._inode = os.fstat(self._file.fileno()).st_ino
            except OSError:
                return []
        try:
            chunk = self._file.read()
        except OSError:
            self._file = None
            return []
        if chunk:
            self._partial += chunk
            parts = self._partial.split("\n")
            self._partial = parts.pop()
            return parts
        try:
            current_inode = os.stat(self._path).st_ino
        except OSError:
            current_inode = None
        if current_inode is not None and current_inode != self._inode:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
            self._partial = ""
        return []


class ViewerState:
    """Curses-layer mutable state: per-lens buffers, latch, screen, input mode."""

    def __init__(self) -> None:
        self.screen: int = 1
        self.frozen: bool = False
        self.scroll: int = 0
        self.filter_text: str = ""
        self.filter_editing: bool = False
        self.latch = LatchState()
        self.last_heartbeat: dict[str, Any] | None = None
        self.health_latest: dict[str, dict[str, Any]] = {}
        self.feeds: dict[str, deque[dict[str, Any]]] = {
            "PERFORMANCE": deque(maxlen=2000),
            "OPERATOR": deque(maxlen=2000),
            "SYSTEM": deque(maxlen=2000),
            "DEBUG": deque(maxlen=2000),
        }
        self.dirty: bool = True

    def ingest(self, rec: dict[str, Any]) -> None:
        cat = _str_field(rec, "cat")
        lenses = lens_of(rec)
        if cat == "perf.heartbeat":
            # Header-only: the heartbeat already drives the sticky header, so
            # scrolling it through the SHOW feed is motion without meaning
            # (readability rule 1: the screen is still when the show is
            # steady). It stays in DEBUG for forensics.
            lenses = lenses - {"PERFORMANCE"}
            self.last_heartbeat = rec
        for lens in lenses:
            self.feeds[lens].append(rec)
        if cat.startswith("health."):
            self.health_latest[cat] = rec
        self.dirty = True

    def visible_scroll(self) -> int:
        return self.scroll if self.frozen else 0

    def handle_key(self, ch: int) -> bool:
        """Handle one keypress. Returns False to request quit ('q')."""
        self.dirty = True
        if self.filter_editing:
            return self._handle_filter_key(ch)
        if ch in (ord("q"), ord("Q")):
            return False
        if ch in (ord("1"), ord("2"), ord("3"), ord("4")):
            self.screen = ch - ord("0")
            self.scroll = 0
        elif ch == ord(" "):
            self.frozen = not self.frozen
        elif self.frozen and ch in (ord("j"), curses.KEY_DOWN):
            self.scroll = max(0, self.scroll - 1)
        elif self.frozen and ch in (ord("k"), curses.KEY_UP):
            self.scroll += 1
        elif ch in (ord("a"), ord("A")):
            self.latch.ack()
        elif self.screen == 4 and ch == ord("/"):
            self.filter_editing = True
        elif self.screen == 4 and ch == ord("c"):
            self.filter_text = ""
        return True

    def _handle_filter_key(self, ch: int) -> bool:
        if ch in (10, 13, 27):  # Enter or Escape leaves edit mode
            self.filter_editing = False
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.filter_text = self.filter_text[:-1]
        elif 32 <= ch < 127:
            self.filter_text += chr(ch)
        return True


def _draw_title_bar(stdscr: Any, state: ViewerState, width: int) -> None:
    """Row 0, always -- fixed position regardless of screen/content (rule 2)."""
    tabs = "  ".join(
        f"*{n} {_SCREEN_NAMES[n]}*" if n == state.screen else f" {n} {_SCREEN_NAMES[n]} "
        for n in (1, 2, 3, 4)
    )
    frozen = "  FROZEN(space=resume)" if state.frozen else ""
    text = f"{tabs}{frozen}"
    try:
        stdscr.addstr(0, 0, text[:width].ljust(width), _attr_for("dim") | curses.A_REVERSE)
    except curses.error:
        pass


def _draw_header(stdscr: Any, state: ViewerState, width: int, now: float, top: int) -> int:
    """SHOW screen sticky header from the latest perf.heartbeat. Returns rows used."""
    hb = state.last_heartbeat
    if hb is None:
        try:
            stdscr.addstr(top, 0, "waiting for heartbeat…"[:width], _attr_for("dim"))
        except curses.error:
            pass
        return 1
    data = hb.get("data") if isinstance(hb.get("data"), dict) else {}
    ts = hb.get("ts")
    age = now - ts if isinstance(ts, (int, float)) else 0.0
    if age > 15:
        age_attr = "red"
    elif age > 5:
        age_attr = "yellow"
    else:
        age_attr = "green"
    line1 = "  ".join([
        f"D{data.get('deck', '?')}",
        f"{data.get('bpm', '?')}bpm",
        f"phrase={data.get('phrase', '?')}",
        f"laser={data.get('laser_scene', '?')}",
        f"led={data.get('led_look', '?')}",
        f"palette={data.get('palette', '?')}",
    ])
    line2 = f"last rec {format_age(ts, now=now)}" if isinstance(ts, (int, float)) else "last rec unknown"
    try:
        stdscr.addstr(top, 0, line1[:width], _attr_for("bright"))
        stdscr.addstr(top + 1, 0, line2[:width], _attr_for(age_attr))
    except curses.error:
        pass
    return 2


def _draw_feed(
    stdscr: Any, top: int, height: int, width: int, records: list[dict[str, Any]], scroll: int
) -> None:
    if height <= 0:
        return
    end = max(0, len(records) - scroll)
    start = max(0, end - height)
    window = records[start:end]
    row = top
    for i, rec in enumerate(window):
        is_newest = scroll == 0 and i == len(window) - 1
        marker = "▸ " if is_newest else "  "
        try:
            stdscr.addstr(row, 0, marker, _attr_for("dim"))
        except curses.error:
            pass
        _draw_segments(stdscr, row, len(marker), format_line(rec, max(0, width - len(marker))), width)
        row += 1


def _draw_operator_strip(stdscr: Any, row: int, width: int, state: ViewerState, now: float) -> None:
    """Bottom-fixed OPERATOR strip on SHOW: green/quiet or red/latched (rules 2 + 5)."""
    if state.latch.is_quiet():
        since = time.strftime("%H:%M:%S", time.localtime(state.latch.quiet_since))
        text = f"✓ all quiet since {since}"
        attr = "green"
    else:
        text = format_strip(state.latch.latched, now)
        attr = "red"
    try:
        stdscr.addstr(row, 0, text[:width].ljust(width), _attr_for(attr))
    except curses.error:
        pass


def _draw_show(stdscr: Any, state: ViewerState, height: int, width: int, now: float) -> None:
    top = 1
    header_rows = _draw_header(stdscr, state, width, now, top)
    strip_row = height - 1
    feed_top = top + header_rows + 1
    feed_height = max(0, strip_row - feed_top)
    _draw_feed(stdscr, feed_top, feed_height, width, list(state.feeds["PERFORMANCE"]), state.visible_scroll())
    if strip_row >= feed_top:
        _draw_operator_strip(stdscr, strip_row, width, state, now)


def _draw_operator(stdscr: Any, state: ViewerState, height: int, width: int, now: float) -> None:
    row = 1
    for cat in sorted(state.health_latest):
        if row >= height - 1:
            break
        rec = state.health_latest[cat]
        line = f"{_surface_of(rec)}: {display_msg(rec.get('msg', ''))} ({format_age(rec.get('ts', now), now=now)})"
        try:
            stdscr.addstr(row, 0, line[:width], _attr_for("dim"))
        except curses.error:
            pass
        row += 1
    row += 1
    _draw_feed(stdscr, row, max(0, height - row), width, list(state.feeds["OPERATOR"]), state.visible_scroll())


def _draw_system(stdscr: Any, state: ViewerState, height: int, width: int, now: float) -> None:
    _draw_feed(stdscr, 1, max(0, height - 1), width, list(state.feeds["SYSTEM"]), state.visible_scroll())


def _draw_debug(stdscr: Any, state: ViewerState, height: int, width: int, now: float) -> None:
    filt = parse_filter(state.filter_text)
    records = [r for r in state.feeds["DEBUG"] if filter_matches(filt, r)]
    if state.filter_editing:
        prompt = f"/{state.filter_text}█"  # block cursor while editing
    elif state.filter_text:
        prompt = f"/{state.filter_text}   (c clears)"
    else:
        prompt = "(no filter -- / to filter, c to clear)"
    try:
        stdscr.addstr(1, 0, prompt[:width], _attr_for("dim"))
    except curses.error:
        pass
    _draw_feed(stdscr, 2, max(0, height - 2), width, records, state.visible_scroll())


_SCREEN_DRAW = {1: _draw_show, 2: _draw_operator, 3: _draw_system, 4: _draw_debug}


def _repaint(stdscr: Any, state: ViewerState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    now = time.time()
    _draw_title_bar(stdscr, state, width)
    try:
        _SCREEN_DRAW[state.screen](stdscr, state, height, width, now)
    except curses.error:
        pass
    stdscr.refresh()


def _stdin_ready() -> bool:
    """Zero-timeout poll: would a read on stdin return immediately (data OR
    EOF/hangup)? Used to tell a getch() timeout apart from a dead terminal."""
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except (OSError, ValueError):
        return True  # stdin fd unusable at all -> treat the terminal as gone


def _run(stdscr: Any, path: Path) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.timeout(100)  # ~10 Hz tick; also bounds getch() blocking (stillness rule)
    _init_colors()

    follower = _FileFollower(path)
    state = ViewerState()
    last_paint = 0.0
    last_age_bucket: int | None = None

    while True:
        got_new = False
        for line in follower.poll():
            rec = parse_record(line)
            if rec is None:
                continue
            state.ingest(rec)
            got_new = True
            if state.latch.note(rec):
                try:
                    curses.beep()
                except curses.error:
                    pass

        ch = stdscr.getch()
        if ch == -1 and _stdin_ready():
            # getch() returning ERR while stdin reports "readable" means EOF/
            # EIO -- the terminal is gone (window closed without a SIGHUP
            # reaching an orphaned viewer). Without this exit the viewer spins
            # headless at 100% CPU and its surviving process makes the
            # watcher's monitor_open() think a window is still open (the
            # 2026-07-05 menubar no-viewer-window regression). One more getch
            # drains the race where a real key landed right after the timeout.
            ch = stdscr.getch()
            if ch == -1:
                return
        if ch != -1 and not state.handle_key(ch):
            return

        now = time.monotonic()
        age_bucket = int(now)  # once-a-second refresh so relative ages stay current
        should_paint = state.dirty or got_new or ch != -1 or age_bucket != last_age_bucket
        if should_paint and (now - last_paint) >= 0.1:
            _repaint(stdscr, state)
            last_paint = now
            last_age_bucket = age_bucket
            state.dirty = False


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bridge_view",
        description=(
            "Read-only JSONL log viewer for rb_ss_bridge_v2 (AWR-125). Follows "
            "current.jsonl and renders the four fixed lenses "
            "(1 SHOW / 2 OPERATOR / 3 SYSTEM / 4 DEBUG)."
        ),
    )
    parser.add_argument(
        "--path",
        default=None,
        help="JSONL file to follow (default: resolved log dir's current.jsonl).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    path = Path(args.path) if args.path else (bridge_log.resolve_log_dir(os.environ) / "current.jsonl")
    try:
        curses.wrapper(_run, path)
    except Exception:
        # curses.wrapper() already restores the terminal to a sane state
        # before re-raising; this is the "print traceback, exit nonzero" half
        # of the spec's exception-safety requirement.
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
