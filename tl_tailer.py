"""
TL log tailer and event parser.

parse_line() is pure/stateless — no global state, fully unit-testable.
TLLogTailer is a daemon thread that tails the log and enqueues events.
Handles file rotation via inode tracking.

Stateful processing (ANLZ correlation, ENGINE STATE parsing) lives in
TLLogTailer._process_line(), separate from the stateless parse_line().
"""
from __future__ import annotations

import queue
import re
import threading
import time
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .models import BridgeEvent, Ev

log = logging.getLogger("tl_tailer")
ANLZ_DIRECT_ENV = "RBSS_ANLZ_DIRECT"
PLAY_DIRECT_ENV = "RBSS_PLAY_DIRECT"

# ── Regexes ──────────────────────────────────────────────────────────────────

# 0-indexed layer number in "Rekordbox master deck changed: X -> Y"
_RE_MASTER  = re.compile(r'Rekordbox master deck changed: (-?\d+) -> (-?\d+)')
_RE_LOADED  = re.compile(r'\[EVENT\] Deck ([A-D]) loaded: "([^"]*)"')
_RE_PLAYING = re.compile(r'\[EVENT\] Deck ([A-D]) (playing|paused)')

# ANLZ: path fires just before deck assignment
_RE_ANLZ_PATH = re.compile(r'AnlzParser: parsed (\d+) beats from "([^"]+)"')
_RE_ANLZ_DECK = re.compile(r'Deck (\d+) ANLZ loaded: (\d+) beats')

# ENGINE STATE: master + per-deck BPM + per-layer TC (fires every ~15 s)
_RE_ES_MASTER = re.compile(r'Master: Layer ([A-D])')
_RE_ES_DECK   = re.compile(
    r'Deck ([A-D]): "([^"]*)" @ [^ ]+ BPM=([\d.]+) pitch=([+-]?[\d.]+)% \[(PLAYING|PAUSED)\]'
)
# "Layer A: Deck A, TC=00:00:42:15, 100.0% [ACTIVE]"
_RE_ES_LAYER_TC = re.compile(
    r'Layer ([A-D]): Deck ([A-D]), TC=(\d{2}):(\d{2}):(\d{2}):(\d{2}),?\s*([\d.]+)%'
)

# Physical deck letter → 1-based index (for _bridge_deck)
_LETTER_TO_IDX = {'A': 1, 'B': 2, 'C': 3, 'D': 4}


def _bridge_deck(idx: int) -> int:
    """Map 1-indexed physical deck (1-4) to bridge deck (1 or 2).

    DDJ-800: decks 1&3 are the left channel (bridge deck 1),
             decks 2&4 are the right channel (bridge deck 2).
    """
    return ((idx - 1) % 2) + 1


def parse_line(line: str) -> Optional[BridgeEvent]:
    """Parse one TL log line into a BridgeEvent, or None if not actionable.

    Stateless and side-effect-free. ANLZ / ENGINE STATE require stateful
    context and are handled by TLLogTailer._process_line instead.
    """
    m = _RE_MASTER.search(line)
    if m:
        raw = int(m.group(2))
        if raw < 0:
            return None   # -1 = no master yet; not actionable
        # raw is 0-indexed layer number; add 1 for _bridge_deck's 1-indexed input
        return BridgeEvent(
            kind=Ev.MASTER_CHANGED,
            deck=_bridge_deck(raw + 1),
            source='tl_log',
        )

    m = _RE_LOADED.search(line)
    if m:
        idx = _LETTER_TO_IDX.get(m.group(1))
        if idx is None:
            return None
        return BridgeEvent(
            kind=Ev.TRACK_LOADED,
            deck=_bridge_deck(idx),
            payload={'title': m.group(2)},
            source='tl_log',
        )

    m = _RE_PLAYING.search(line)
    if m:
        idx = _LETTER_TO_IDX.get(m.group(1))
        if idx is None:
            return None
        kind = Ev.PLAY if m.group(2) == 'playing' else Ev.PAUSE
        return BridgeEvent(kind=kind, deck=_bridge_deck(idx), source='tl_log')

    return None


# ── Startup state reader ──────────────────────────────────────────────────────

_RE_CONFIG_MASTER = re.compile(r'master_layer:\s*(\d+)')
_RE_LOG_TIMESTAMP = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]')
_INITIAL_ENGINE_STATE_MAX_AGE_S = 60.0


def _latest_engine_state_from_tail(log_path: Path) -> tuple[str, Optional[datetime], float]:
    try:
        with open(log_path, 'rb') as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 32768))
            tail = fh.read().decode('utf-8', errors='replace')
    except Exception as exc:
        log.debug("read_initial_state: log tail read failed: %s", exc)
        return "", None, float("inf")

    last = tail.rfind('=== ENGINE STATE ===')
    if last == -1:
        return "", None, float("inf")

    line_start = tail.rfind("\n", 0, last) + 1
    marker_line = tail[line_start:tail.find("\n", last)]
    timestamp = None
    age_s = float("inf")
    m_ts = _RE_LOG_TIMESTAMP.search(marker_line)
    if m_ts:
        try:
            timestamp = datetime.strptime(m_ts.group(1), "%Y-%m-%d %H:%M:%S")
            age_s = (datetime.now() - timestamp).total_seconds()
            if age_s < 0:
                age_s = 0.0
        except ValueError:
            log.debug("read_initial_state: invalid ENGINE STATE timestamp: %s", m_ts.group(1))

    end = tail.find('====================', last + 20)
    if end == -1:
        return "", timestamp, age_s
    return tail[last:end], timestamp, age_s


def _parse_engine_state_decks(block: str) -> dict[int, dict]:
    decks: dict[int, dict] = {}
    for m in _RE_ES_DECK.finditer(block):
        idx = _LETTER_TO_IDX.get(m.group(1), 1)
        deck = _bridge_deck(idx)
        title = m.group(2).strip()
        if not title:
            continue
        decks[deck] = {
            "title": title,
            "bpm": float(m.group(3)),
            "pitch_factor": 1.0 + (float(m.group(4)) / 100.0),
            "playing": m.group(5) == "PLAYING",
        }

    for m in _RE_ES_LAYER_TC.finditer(block):
        deck_letter = m.group(2)
        idx = _LETTER_TO_IDX.get(deck_letter, 1)
        deck = _bridge_deck(idx)
        if deck not in decks:
            continue
        h   = int(m.group(3))
        mn  = int(m.group(4))
        s   = int(m.group(5))
        ff  = int(m.group(6))
        elapsed_ms = (h * 3600 + mn * 60 + s) * 1000 + int(ff * 1000.0 / 30)
        decks[deck]["elapsed_ms"] = elapsed_ms
        decks[deck]["pitch_factor"] = float(m.group(7)) / 100.0

    return decks


def read_initial_state(log_path: Path) -> dict:
    """Determine the initial active deck for StateManager startup.

    Priority:
      1. config.yaml master_layer field (TL updates this on every master change)
      2. Last ENGINE STATE block in the log (fallback)
      3. Default to deck 1

    Returns dict with active_deck: int (1 or 2), plus fresh startup deck state
    reconstructed from the latest ENGINE STATE block when available.
    """
    config_path = log_path.parent / "config.yaml"
    engine_block, _engine_ts, engine_age_s = _latest_engine_state_from_tail(log_path)
    active_deck = 1
    active_source = "default"

    # Primary: config.yaml — TL persists master_layer here across restarts
    try:
        text = config_path.read_text(encoding='utf-8', errors='replace')
        m = _RE_CONFIG_MASTER.search(text)
        if m:
            raw = int(m.group(1))   # 0-indexed layer number
            active_deck = _bridge_deck(raw + 1)
            active_source = f"master_layer={raw} from config.yaml"
            log.info("read_initial_state: active_deck=%d (master_layer=%d from config.yaml)",
                     active_deck, raw)
    except Exception as exc:
        log.debug("read_initial_state: config.yaml read failed: %s", exc)

    # Fallback: last ENGINE STATE block in the log
    if active_source == "default" and engine_block:
        m = _RE_ES_MASTER.search(engine_block)
        if m:
            idx = _LETTER_TO_IDX.get(m.group(1), 1)
            active_deck = _bridge_deck(idx)
            active_source = f"Layer {m.group(1)} from ENGINE STATE"
            log.info("read_initial_state: active_deck=%d (Layer %s from ENGINE STATE)",
                     active_deck, m.group(1))

    decks = {}
    if engine_block and engine_age_s <= _INITIAL_ENGINE_STATE_MAX_AGE_S:
        decks = _parse_engine_state_decks(engine_block)
        if decks:
            log.info("read_initial_state: found %d startup loaded deck(s) from ENGINE STATE age=%.1fs",
                     len(decks), engine_age_s)
    elif engine_block:
        log.info("read_initial_state: skipping startup deck preload; ENGINE STATE age=%.1fs",
                 engine_age_s)

    if active_source == "default":
        log.info("read_initial_state: defaulting to deck 1")
    return {
        'active_deck': active_deck,
        'decks': decks,
        'engine_state_age_s': engine_age_s,
    }


# ── Log tailer ────────────────────────────────────────────────────────────────

class TLLogTailer(threading.Thread):
    """Tail the TL log file and push parsed events onto event_queue.

    Seeks to end on first open (no history replay).
    Reopens automatically on file rotation (inode change or disappearance).

    Stateful tracking:
      _last_anlz_beats / _last_anlz_path  — ANLZ beat-count correlation
      _in_engine_state                    — ENGINE STATE block accumulator
    """

    _IDLE_POLL_S = 0.05

    def __init__(
        self,
        log_path: Path,
        event_queue: queue.Queue[BridgeEvent],
        *,
        anlz_direct_ready: Optional[Callable[[int], bool]] = None,
        play_direct_ready: Optional[Callable[[int], bool]] = None,
    ):
        super().__init__(name="tl-log-tailer", daemon=True)
        self._path  = log_path
        self._queue = event_queue
        self._stop  = threading.Event()
        self._anlz_direct_ready = anlz_direct_ready
        self._play_direct_ready = play_direct_ready

        # ANLZ stateful correlation
        self._last_anlz_beats: int = 0
        self._last_anlz_path:  str = ""

        # ENGINE STATE accumulator
        self._in_engine_state: bool = False
        self._es_lines: list[str]   = []

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        log.info("TLLogTailer: watching %s", self._path)
        while not self._stop.is_set():
            try:
                self._tail_once()
            except Exception:
                log.exception("TLLogTailer: unexpected error — restarting in 2 s")
                time.sleep(2)

    def _tail_once(self) -> None:
        while not self._path.exists() and not self._stop.is_set():
            time.sleep(1)
        if self._stop.is_set():
            return

        try:
            inode = self._path.stat().st_ino
        except FileNotFoundError:
            return

        with open(self._path, encoding='utf-8', errors='replace') as fh:
            fh.seek(0, 2)
            while not self._stop.is_set():
                line = fh.readline()
                if line:
                    self._process_line(line)
                else:
                    try:
                        new_inode = self._path.stat().st_ino
                    except FileNotFoundError:
                        log.warning("TLLogTailer: log removed — waiting")
                        return
                    if new_inode != inode:
                        log.info("TLLogTailer: log rotated (%d→%d) — reopening",
                                 inode, new_inode)
                        return
                    time.sleep(self._IDLE_POLL_S)

    def _enqueue(self, ev: BridgeEvent) -> None:
        try:
            self._queue.put_nowait(ev)
        except queue.Full:
            log.warning("TLLogTailer: queue full — dropping %s", ev.kind)

    def _play_direct_bypass_enabled(self, deck: int) -> bool:
        if os.environ.get(PLAY_DIRECT_ENV) != "1":
            return False
        if self._play_direct_ready is None:
            return True
        try:
            return bool(self._play_direct_ready(deck))
        except Exception:
            return False

    def _anlz_direct_bypass_enabled(self, deck: int) -> bool:
        if os.environ.get(ANLZ_DIRECT_ENV) != "1":
            return False
        if self._anlz_direct_ready is None:
            return True
        try:
            return bool(self._anlz_direct_ready(deck))
        except Exception:
            return False

    def _process_line(self, line: str) -> None:
        # ── ENGINE STATE accumulator ──────────────────────────────────────────
        if '=== ENGINE STATE ===' in line:
            self._in_engine_state = True
            self._es_lines = []
            return
        if self._in_engine_state:
            if '====================' in line:
                self._in_engine_state = False
                self._flush_engine_state()
            else:
                self._es_lines.append(line)
            return

        # ── ANLZ path capture ─────────────────────────────────────────────────
        m = _RE_ANLZ_PATH.search(line)
        if m:
            self._last_anlz_beats = int(m.group(1))
            self._last_anlz_path  = m.group(2)
            return

        # ── ANLZ deck correlation → emit ANLZ_PATH before TRACK_LOADED ───────
        m = _RE_ANLZ_DECK.search(line)
        if m:
            deck_idx = int(m.group(1))   # 0-indexed
            beats    = int(m.group(2))
            if beats == self._last_anlz_beats and self._last_anlz_path:
                bridge_deck = _bridge_deck(deck_idx + 1)
                if not self._anlz_direct_bypass_enabled(bridge_deck):
                    self._enqueue(BridgeEvent(
                        kind=Ev.ANLZ_PATH,
                        deck=bridge_deck,
                        payload={'anlz_path': self._last_anlz_path},
                        source='tl_log',
                    ))
                self._last_anlz_beats = 0
                self._last_anlz_path  = ""
            return

        # ── Stateless events ──────────────────────────────────────────────────
        ev = parse_line(line)
        if ev is not None:
            if ev.kind in (Ev.PLAY, Ev.PAUSE) and self._play_direct_bypass_enabled(ev.deck):
                return
            self._enqueue(ev)

    def _flush_engine_state(self) -> None:
        """Parse accumulated ENGINE STATE lines and emit MASTER_CHANGED + BPM_UPDATE events."""
        block = "\n".join(self._es_lines)

        # Master deck — always emit so StateManager stays in sync even when TL
        # doesn't fire an explicit 'Rekordbox master deck changed' line.
        m = _RE_ES_MASTER.search(block)
        if m:
            idx  = _LETTER_TO_IDX.get(m.group(1), 1)
            deck = _bridge_deck(idx)
            self._enqueue(BridgeEvent(
                kind=Ev.MASTER_CHANGED,
                deck=deck,
                source='engine_state',
            ))

        for m in _RE_ES_DECK.finditer(block):
            letter  = m.group(1)
            bpm     = float(m.group(3))
            idx     = _LETTER_TO_IDX.get(letter, 1)
            deck    = _bridge_deck(idx)
            if bpm > 0:
                self._enqueue(BridgeEvent(
                    kind=Ev.BPM_UPDATE,
                    deck=deck,
                    payload={'bpm': bpm},
                    source='engine_state',
                ))

        # Emit TC_UPDATE for each active layer so StateManager can use TL TC
        # as fallback position for decks where memory position is unreliable
        # (e.g. DDJ-800 deck 2 / mode=4112 never writes to inner+0xC).
        for m in _RE_ES_LAYER_TC.finditer(block):
            deck_letter = m.group(2)
            h   = int(m.group(3))
            mn  = int(m.group(4))
            s   = int(m.group(5))
            ff  = int(m.group(6))
            pitch_factor = float(m.group(7)) / 100.0
            elapsed_ms = (h * 3600 + mn * 60 + s) * 1000 + int(ff * 1000.0 / 30)
            if elapsed_ms == 0:
                continue
            idx  = _LETTER_TO_IDX.get(deck_letter, 1)
            deck = _bridge_deck(idx)
            mm2, ss2 = divmod(elapsed_ms // 1000, 60)
            ms2 = elapsed_ms % 1000
            log.info("timecode deck %d (layer %s): %d:%02d.%03d  pitch=%.1f%%",
                     deck, m.group(1), mm2, ss2, ms2, pitch_factor * 100.0)
            self._enqueue(BridgeEvent(
                kind=Ev.TC_UPDATE,
                deck=deck,
                payload={'elapsed_ms': elapsed_ms, 'pitch_factor': pitch_factor},
                source='engine_state',
            ))

        log.debug("TLLogTailer: flushed ENGINE STATE (%d lines)", len(self._es_lines))
