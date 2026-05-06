"""
rb_ss_bridge_v2 — entry point and wiring.

Replaces Frida hooks with:
  - TL log parsing  (master change, play/pause, track load)
  - Direct RB memory (position at 60 Hz)
  - lsof / DB        (filepath identification on track load)

OSC is kept for scripted show triggers (TL playlist.yaml osc_triggers).

Run:
  python -m rb_ss_bridge_v2
"""
from __future__ import annotations

import logging
import os
import queue
import signal
import sys
import time
import threading
import fcntl

from .config import OSC_LISTEN_PORT, TL_LOG_PATH, TL_PLAYLIST_PATH
from .filepath_resolver import FilepathResolver
from .models import BridgeEvent, Ev
from .mtc_reader import MTCReader
from .osl_output import OS2LConnection, OS2LOutput, SoundSwitchDiscovery
from .os2l_injector import OS2LInjector
from .rb_memory import PositionCache, RBMemoryReader
from .scripted_tracks import preload_from_tl, resolve_filepaths
from .state_manager import StateManager
from .tl_tailer import TLLogTailer, read_initial_state
from .diagnostics import DriftDetector, enable_debug, is_debug
from .link_reader import LinkReader
from .live_bpm import LIVE_BPM_DISABLE_ENV, LiveBPMService
from .logging_manager import get_logging_manager

# ── Logging ───────────────────────────────────────────────────────────────────

class _ColorFormatter(logging.Formatter):
    _RESET    = "\033[0m"
    _GREY     = "\033[90m"
    _WHITE    = "\033[37m"
    _YELLOW   = "\033[33m"
    _RED      = "\033[31m"
    _BRED     = "\033[91m"
    _BGREEN   = "\033[92m"
    _BCYAN    = "\033[96m"
    _BMAGENTA = "\033[95m"
    _ORANGE   = "\033[38;5;214m"

    _LEVEL = {
        logging.DEBUG:    _GREY,
        logging.INFO:     _WHITE,
        logging.WARNING:  _ORANGE,
        logging.ERROR:    _RED,
        logging.CRITICAL: _BRED,
    }

    # First match wins
    _PATTERNS = [
        # Red: action needed now.
        ("rb_restarted",            _BRED),
        ("rb restarted",            _BRED),
        ("memory stale",            _BRED),
        ("forcing stop",            _BRED),
        ("playback stopped",        _BRED),
        ("→ idle",                  _BRED),
        (" paused",                 _BRED),
        (" stopped",                _BRED),
        ("osc listener failed",     _BRED),
        ("os2l send error",         _BRED),
        ("clearing ss show",        _BRED),

        # Orange/yellow: degraded, retrying, or needs follow-up but still running.
        ("event latency",           _ORANGE),
        ("attach failed",           _ORANGE),
        ("queue full",              _ORANGE),
        ("connect failed",          _ORANGE),
        ("port error",              _ORANGE),
        ("failed",                  _ORANGE),
        ("retry",                   _ORANGE),
        ("[lbpm][error]",           _ORANGE),
        ("[lbpm][invalid]",         _ORANGE),
        ("[rbmem][error]",          _ORANGE),
        ("[rbmem][invalid]",        _ORANGE),
        ("[rbmem][reject]",         _ORANGE),
        ("fallback",                _YELLOW),
        ("disabled",                _YELLOW),
        ("not installed",           _YELLOW),
        ("[ss][live-bpm-pending]",  _YELLOW),
        ("[rbmem][pending]",        _YELLOW),
        ("[rbmem][inconclusive]",   _YELLOW),
        ("cooldown",                _YELLOW),
        ("discarded",               _YELLOW),
        ("no peers",                _YELLOW),

        # Cyan: deck routing and master-deck decisions.
        ("master_changed",          _BCYAN),
        ("master changed",          _BCYAN),
        ("deck switch",             _BCYAN),
        ("auto-switch",             _BCYAN),
        ("active_deck",             _BCYAN),
        ("correcting: active deck", _BCYAN),

        # Cyan: steady-state autoloop status, intentionally scan-friendly.
        ("[ss][autoloop-tick]",     _BCYAN),
        ("[lbpm][scan]",            _BCYAN),
        ("[lbpm][current]",         _BCYAN),
        ("[rbmem][scan]",           _BCYAN),
        ("[rbmem][candidate]",      _BCYAN),
        ("[rbmem][status]",         _BCYAN),

        # Magenta: scripted show lifecycle.
        ("scripted_arm",            _BMAGENTA),
        ("scripted_clear",          _BMAGENTA),
        ("scripted arm",            _BMAGENTA),
        ("arm scripted",            _BMAGENTA),
        ("arm unscripted",          _BMAGENTA),
        ("phase2",                  _BMAGENTA),
        ("scripted cleared",        _BMAGENTA),

        # Green: successful user-facing state.
        ("track_loaded",            _BGREEN),
        ("filepath_resolved",       _BGREEN),
        ("filepath resolved",       _BGREEN),
        ("resolved →",              _BGREEN),
        ("resolved:",               _BGREEN),
        ("► d",                     _BGREEN),
        ("playing",                 _BGREEN),
        ("resume",                  _BGREEN),
        ("resuming",                _BGREEN),
        ("attached pid",            _BGREEN),
        ("connected to soundswitch",_BGREEN),
        ("[ss][autoloop-arm]",      _BGREEN),
        ("[ss][live-bpm-apply]",    _BGREEN),
        ("[lbpm][attach]",          _BGREEN),
        ("[lbpm][validated]",       _BGREEN),
        ("[rbmem][attach]",         _BGREEN),
        ("[rbmem][validated]",      _BGREEN),
        ("autoloop",                _BGREEN),

        # Grey: diagnostic/status noise.
        ("link bpm:",               _GREY),
        ("timecode deck",           _GREY),
        ("mtc deck",                _GREY),
        ("event processed",         _GREY),
        ("event relation",          _GREY),
        ("scripted_tracks: registry", _GREY),
    ]

    def format(self, record: logging.LogRecord) -> str:
        msg, args = record.msg, record.args
        prefix = LOG.indent(record)
        if prefix:
            record.msg = prefix + str(record.msg)
        try:
            text = super().format(record)
        finally:
            record.msg, record.args = msg, args
        text += LOG.annotate(record)
        msg = record.getMessage().lower()
        color = self._WHITE
        for pattern, c in self._PATTERNS:
            if pattern in msg:
                color = c
                break
        else:
            color = self._LEVEL.get(record.levelno, self._WHITE)
        return f"{color}{text}{self._RESET}"


LOG = get_logging_manager()
logging.basicConfig(level=logging.INFO, datefmt="%H:%M:%S", stream=sys.stdout)
LOG.configure(json_output=bool(os.environ.get("BRIDGE_LOG_JSON")), root_level=logging.INFO)
LOG.reload_from_env()
_handler = logging.root.handlers[0]
if not os.environ.get("BRIDGE_LOG_JSON"):
    _handler.setFormatter(_ColorFormatter(
        "%(asctime)s [%(levelname)-7s] %(message)s", datefmt="%H:%M:%S"
    ))
log = logging.getLogger("bridge")

_LOCK_FD = None
_LOCK_PATH = "/tmp/rb_ss_bridge_v2.lock"


def _acquire_single_instance_lock() -> bool:
    """Return False when another bridge process already owns the runtime lock."""
    global _LOCK_FD
    fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode("ascii"))
    _LOCK_FD = fd
    return True


# ── OSC listener (scripted arm triggers from TL) ──────────────────────────────

def start_osc_listener(event_queue: queue.Queue[BridgeEvent], state_manager: StateManager) -> None:
    """Listen on UDP for /bridge/active_deck and /bridge/track_loaded from TL."""
    try:
        from pythonosc import dispatcher as osc_dispatcher  # type: ignore
        from pythonosc import osc_server                    # type: ignore
        from pythonosc.udp_client import SimpleUDPClient    # type: ignore
    except ImportError:
        LOG.log_error(log, "python-osc not installed - scripted arm triggers will not work")
        return

    disp = osc_dispatcher.Dispatcher()

    def _active_deck(address, *args):
        if not args:
            return
        try:
            deck = int(float(args[0]))
        except (TypeError, ValueError):
            return
        bridge_deck = ((deck - 1) % 2) + 1 if deck > 0 else 1
        event_queue.put_nowait(BridgeEvent(
            kind=Ev.MASTER_CHANGED, deck=bridge_deck, source="osc",
        ))

    def _track_loaded(address, *args):
        if not args:
            return
        try:
            track_id = int(float(args[0]))
        except (TypeError, ValueError):
            return
        # Use the deck that most recently received a TRACK_LOADED event from the TL log.
        # This is more reliable than get_active_deck() when loading on the non-master deck,
        # because TL log events carry explicit deck info (A/B/C/D) while the OSC message does not.
        # Falls back to active deck if no TRACK_LOADED has been seen yet (startup edge case).
        target = state_manager.get_last_loaded_deck() or state_manager.get_active_deck()
        if track_id >= 2:
            # Auto-populate new scripted track from DB if not yet registered
            from .scripted_tracks import SCRIPTED_TRACKS
            if track_id not in SCRIPTED_TRACKS:
                # FM-7: run DB scan in daemon thread, not OSC handler thread
                threading.Thread(
                    target=_auto_populate,
                    args=(track_id, target, event_queue),
                    daemon=True,
                    name="auto-populate",
                ).start()
                return
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.SCRIPTED_ARM,
                deck=target,
                payload={"scripted_id": track_id},
                source="osc",
            ))
        else:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.SCRIPTED_CLEAR, deck=target, source="osc",
            ))

    disp.map("/bridge/active_deck",  _active_deck)
    disp.map("/bridge/bridge_deck",  _active_deck)
    disp.map("/bridge/track_loaded", _track_loaded)
    disp.set_default_handler(lambda addr, *a: log.debug("OSC: %s %s", addr, a))

    try:
        srv = osc_server.ThreadingOSCUDPServer(("0.0.0.0", OSC_LISTEN_PORT), disp)
    except OSError as exc:
        LOG.log_error(log, "OSC listener failed on port %d: %s", OSC_LISTEN_PORT, exc)
        return

    log.info("OSC listener on UDP :%d", OSC_LISTEN_PORT)
    threading.Thread(target=srv.serve_forever, name="osc-server", daemon=True).start()

    # Re-register with TL so it re-announces current state
    def _register():
        time.sleep(1.0)
        try:
            cl = SimpleUDPClient("127.0.0.1", 20808)
            cl.send_message("/Register", [])
        except Exception:
            pass
    threading.Thread(target=_register, daemon=True).start()


def _auto_populate(track_id: int, active_deck: int, eq: queue.Queue) -> None:
    """Query RB DB for an unknown track_id and register it, then fire SCRIPTED_ARM."""
    import os
    import warnings
    log.info("auto-populate: unknown scripted id=%d — querying DB", track_id)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db_path = os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
        db = Rekordbox6Database(db_path, unlock=True)
        # We don't know the name; register a placeholder so the ID is known
        # The real metadata will arrive via lsof
        from .scripted_tracks import register
        register(track_id, {"name": f"auto-{track_id}", "filepath": "",
                             "bpm": 0.0, "total_ms": 0, "first_beat_ms": 0.0})
    except Exception as exc:
        log.warning("auto-populate: DB failed: %s", exc)
    eq.put_nowait(BridgeEvent(
        kind=Ev.SCRIPTED_ARM, deck=active_deck,
        payload={"scripted_id": track_id}, source="osc",
    ))


def _seed_initial_decks(eq: queue.Queue[BridgeEvent], init: dict) -> None:
    """Replay fresh ENGINE STATE deck identity through the normal event path."""
    decks = init.get("decks") or {}
    if not decks:
        return

    seeded = 0
    for deck in sorted(decks):
        info = decks[deck]
        title = str(info.get("title", ""))
        if not title:
            continue

        events = [
            BridgeEvent(
                kind=Ev.TRACK_LOADED,
                deck=deck,
                payload={"title": title},
                source="initial_engine_state",
            ),
        ]
        bpm = float(info.get("bpm", 0.0) or 0.0)
        if bpm > 0:
            events.append(BridgeEvent(
                kind=Ev.BPM_UPDATE,
                deck=deck,
                payload={"bpm": bpm},
                source="initial_engine_state",
            ))
        elapsed_ms = int(info.get("elapsed_ms", 0) or 0)
        if elapsed_ms > 0:
            events.append(BridgeEvent(
                kind=Ev.TC_UPDATE,
                deck=deck,
                payload={
                    "elapsed_ms": elapsed_ms,
                    "pitch_factor": float(info.get("pitch_factor", 1.0) or 1.0),
                },
                source="initial_engine_state",
            ))
        if bool(info.get("playing", False)):
            events.append(BridgeEvent(
                kind=Ev.PLAY,
                deck=deck,
                source="initial_engine_state",
            ))

        try:
            for ev in events:
                eq.put_nowait(ev)
            seeded += 1
            log.info("startup preload: deck=%d title=%s bpm=%.1f playing=%s",
                     deck, title, bpm, bool(info.get("playing", False)))
        except queue.Full:
            log.warning("startup preload: event queue full; deck=%d title=%s skipped",
                        deck, title)

    if seeded:
        log.info("startup preload: enqueued %d loaded deck(s) from ENGINE STATE", seeded)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not _acquire_single_instance_lock():
        log.error("another rb_ss_bridge_v2 process is already running; exiting")
        return

    if is_debug() or "--debug" in sys.argv:
        enable_debug()

    log.info("rb_ss_bridge_v2 starting")

    # Startup: pre-register scripted tracks from TL playlist.yaml + resolve filepaths
    preload_from_tl(str(TL_PLAYLIST_PATH))
    resolve_filepaths()

    # Shared event queue
    raw_event_queue: queue.Queue[BridgeEvent] = queue.Queue(maxsize=512)
    event_queue = LOG.wrap_queue(raw_event_queue)

    # Position cache (RBMemoryReader → PositionCache → StateManager push loop)
    pos_cache = PositionCache()
    live_bpm = LiveBPMService()
    if live_bpm.disabled:
        log.warning("Live BPM disabled by %s=1; autoloop will use ENGINE STATE/library BPM",
                    LIVE_BPM_DISABLE_ENV)

    # OS2L output
    conn = OS2LConnection()
    conn.start()
    output = OS2LOutput(conn)
    injector = OS2LInjector(conn)

    # DNS-SD discovery for SoundSwitch
    discovery = SoundSwitchDiscovery(conn)
    discovery.start()

    # State manager (event loop + push loop)
    sm = StateManager(event_queue, pos_cache, output, live_bpm=live_bpm)

    # Initialize master deck from last TL ENGINE STATE (fixes startup deck bug)
    init = read_initial_state(TL_LOG_PATH)
    sm.set_initial_state(init['active_deck'])

    # Filepath resolver (triggered by TRACK_LOADED, pushes FILEPATH_RESOLVED)
    resolver = FilepathResolver(event_queue, pos_cache)
    sm.attach_resolver(resolver)
    _seed_initial_decks(event_queue, init)

    # TL log tailer
    tailer = TLLogTailer(TL_LOG_PATH, event_queue)

    # Memory reader (with drift detection + FM-11 RB_RESTARTED events)
    from .diagnostics import DriftDetector
    mem_reader = RBMemoryReader(
        pos_cache,
        drift_detector=DriftDetector(),
        event_queue=event_queue,
        deck_elapsed_hint=sm.get_deck_elapsed_ms,
        deck_playing_hint=sm.get_deck_playing,
    )

    # Ableton Link reader (degrades gracefully if pylinklib unavailable)
    link = LinkReader()
    link.start()
    sm.attach_link(link)

    # MTC reader — ~25 fps position fallback from RB via IAC Bus 1.
    # Posts TC_UPDATE events for the active deck; state_manager ignores them
    # once PositionCache has a live memory snapshot for that deck.
    mtc = MTCReader(event_queue, sm.get_active_deck)
    mtc.start()

    # Start all components
    tailer.start()
    mem_reader.start()
    live_bpm.start()
    injector.start()
    sm_thread = sm.start()

    # OSC listener (scripted arm triggers)
    start_osc_listener(event_queue, sm)

    log.info("rb_ss_bridge_v2 running — Ctrl-C to stop")
    LOG.start_control_watcher(log)

    # Graceful shutdown on SIGTERM / SIGINT
    def _shutdown(sig, frame):
        log.info("shutdown signal received")
        LOG.stop_control_watcher()
        sm.stop()
        tailer.stop()
        mem_reader.stop()
        live_bpm.stop()
        link.stop()
        mtc.stop()
        injector.stop()
        discovery.stop()
        conn.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    def _reload_logging(sig, frame):
        LOG.reload_from_env()
        LOG.log_stats(log)
        log.info("logging runtime filters reloaded from BRIDGE_LOG_*")

    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _reload_logging)

    # Block main thread
    sm_thread.join()


if __name__ == "__main__":
    main()
