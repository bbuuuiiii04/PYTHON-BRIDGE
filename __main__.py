"""
rb_ss_bridge_v2 — entry point and wiring.

Replaces Frida hooks with:
  - Direct RB memory (master change, play/pause, track load, position)
  - TL log parsing  (fallback state, MTC provider, startup ENGINE STATE)
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
from dataclasses import dataclass
from typing import Callable, Optional

from .config import OSC_LISTEN_PORT, TL_LOG_PATH, TL_PLAYLIST_PATH
from .filepath_resolver import (
    FilepathResolver,
    seed_soundswitch_id_cache,
    seed_soundswitch_scripted_id_cache,
)
from .models import BridgeEvent, Ev
from .mtc_reader import MTCReader
from .osl_output import OS2LConnection, OS2LOutput, SoundSwitchDiscovery
from .os2l_injector import OS2LInjector
from .rb_memory import PositionCache, RBMemoryReader
from .rb_state_reader import (
    make_rb_state_reader,
    direct_master_label,
    read_direct_master_status,
)
from .scripted_tracks import preload_from_tl, resolve_filepaths
from .ss_library_scanner import start_ss_library_scan
from .state_manager import (
    AUTOLOOP_MASTER_PHRASE_ARM_ENV,
    LIVE_BPM_FOLLOW_ENV,
    PHRASE_ANCHOR_ENV,
    SMART_DROP_ENV,
    SMART_REARM_EXPERIMENT_ENV,
    StateManager,
)
from .tl_tailer import (
    ANLZ_DIRECT_ENV,
    MASTER_DIRECT_ENV,
    PLAY_DIRECT_ENV,
    TRACK_LOAD_DIRECT_ENV,
    TLLogTailer,
    read_initial_state,
)
from .diagnostics import DriftDetector, enable_debug, is_debug
from .live_bpm import LIVE_BPM_DISABLE_ENV, LiveBPMService, read_rekordbox_version
from .logging_manager import get_logging_manager
from .laser_config import LaserConfigResult, load_laser_director_config
from .laser_director import LaserDirector
from .laser_executor import LaserSceneExecutor
from .laser_models import LaserPersonality
from .midi_output import MidiOutput
from .runtime_status import CommandReader, StatusWriter
from .validation_runner import ValidationRunner

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
    _BPINK    = "\033[38;5;213m"
    _ORANGE   = "\033[38;5;214m"

    _LEVEL = {
        logging.DEBUG:    _GREY,
        logging.INFO:     _WHITE,
        logging.WARNING:  _ORANGE,
        logging.ERROR:    _RED,
        logging.CRITICAL: _BRED,
    }

    # First match wins. Patterns are checked against lowercased message text.
    _PATTERNS = [
        # Pink: Laser Director config and scene policy.
        ("[laser] scene",           _BPINK),
        ("[laser] reason-update",   _BPINK),
        ("[laser_config]",          _BPINK),
        ("[main] laser-config",     _BPINK),

        # Red: requires attention / playback stopped.
        ("rb-restart",              _BRED),
        ("stop-stale",              _BRED),
        ("[sm] stop ",              _BRED),
        ("[sm] pause",              _BRED),
        ("osc listener failed",     _BRED),
        ("[os2l] send-error",       _BRED),
        ("→idle",                   _BRED),

        # Orange: degraded, late, or retrying — still running but needs watch.
        ("[sm] event-late",         _ORANGE),
        ("[sm] arm-grace-late",     _ORANGE),
        ("[sm] arm-late",           _ORANGE),
        ("[sm] arm-phrase-miss",    _ORANGE),
        ("queue-full",              _ORANGE),
        ("connect-fail",            _ORANGE),
        ("resolve-fail",            _ORANGE),
        ("attach failed",           _ORANGE),
        ("port error",              _ORANGE),
        ("failed",                  _ORANGE),
        ("retry",                   _ORANGE),
        ("[lbpm][error]",           _ORANGE),
        ("[lbpm][invalid]",         _ORANGE),
        ("[rbmem][error]",          _ORANGE),
        ("[rbmem][invalid]",        _ORANGE),
        ("[rbmem][reject]",         _ORANGE),

        # Yellow: pending, fallback, or degraded-but-working.
        ("[sm] arm-pending",        _YELLOW),
        ("[sm] arm-correction-pending", _YELLOW),
        ("[sm] arm-correction-clear", _YELLOW),
        ("[sm] clear-autoloop",     _YELLOW),
        ("fallback",                _YELLOW),
        ("disabled",                _YELLOW),
        ("not installed",           _YELLOW),
        ("[rbmem][pending]",        _YELLOW),
        ("[rbmem][inconclusive]",   _YELLOW),
        ("shutdown signal",         _YELLOW),
        ("cooldown",                _YELLOW),
        ("resolve-stale",           _YELLOW),
        ("no peers",                _YELLOW),

        # Cyan: deck routing and master-deck decisions.
        ("[sm] switch",             _BCYAN),
        ("[sm] status",             _BCYAN),
        ("master_changed",          _BCYAN),
        ("master changed",          _BCYAN),
        ("[master-seed]",           _BCYAN),
        ("[rbmaster]",              _BCYAN),

        # Cyan: steady-state scan-friendly status.
        ("[lbpm][scan]",            _BCYAN),
        ("[lbpm][current]",         _BCYAN),
        ("[rbmem][scan]",           _BCYAN),
        ("[rbmem][candidate]",      _BCYAN),
        ("[rbmem][status]",         _BCYAN),

        # Magenta: scripted show lifecycle.
        ("[sm] arm-scripted",       _BMAGENTA),
        ("[sm] arm-phase2",         _BMAGENTA),
        ("[sm] clear-scripted",     _BMAGENTA),
        ("[sm][shadow]",            _BMAGENTA),
        ("[main][shadow]",          _BMAGENTA),
        ("scripted_arm",            _BMAGENTA),
        ("scripted_clear",          _BMAGENTA),
        ("[ss-scan] complete",      _BMAGENTA),
        ("[ss-scan] candidate",     _GREY),
        ("[ss-scan]",               _GREY),

        # Green: successful user-facing state.
        ("rb_ss_bridge_v2 starting", _BGREEN),
        ("rb_ss_bridge_v2 running", _BGREEN),
        ("[main] startup",          _BGREEN),
        ("[main] starting",         _BGREEN),
        ("[main] running",          _BGREEN),
        ("osc listener on",         _BGREEN),
        ("[sm] load",               _BGREEN),
        ("[sm] resolve",            _BGREEN),
        ("[fres] resolve",          _BGREEN),
        ("[fres] match",            _BGREEN),
        ("[sm] play",               _BGREEN),
        ("[sm] resume",             _BGREEN),
        ("[sm] arm-autoloop",       _BGREEN),
        ("[sm] rearm-autoloop",     _BGREEN),
        ("[sm] arm-locked",         _BGREEN),
        ("[sm] bpm-apply",          _BGREEN),
        ("[os2l] connected",        _BGREEN),
        ("► ",                      _BGREEN),
        ("attached pid",            _BGREEN),
        ("[lbpm][attach]",          _BGREEN),
        ("[lbpm][validated]",       _BGREEN),
        ("[rbmem][attach]",         _BGREEN),
        ("[rbmem][validated]",      _BGREEN),

        # Grey: high-frequency diagnostic noise.
        ("[tl] tc",                 _GREY),
        ("[mtc]",                   _GREY),
        ("event processed",         _GREY),
        ("scripted_tracks: registry", _GREY),
    ]

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        import time as _time
        ct = self.converter(record.created)
        s = _time.strftime("%H:%M:%S", ct)
        return f"{s}.{int(record.msecs):03d}"

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
MASTER_SEED_DIRECT_ENV = "RBSS_MASTER_SEED_DIRECT"
SCRIPTED_DIRECT_ENV = "RBSS_SCRIPTED_DIRECT"


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default) != "0"


def _onoff(value: bool) -> str:
    return "on" if value else "off"


@dataclass(frozen=True)
class LaserStartupBundle:
    laser_director: Optional[LaserDirector]
    laser_executor: Optional[LaserSceneExecutor]
    midi_output: Optional[MidiOutput]
    status_provider: Optional[Callable[[], dict]]
    personality_provider: Optional[Callable[[str], Optional[LaserPersonality]]]


def _build_laser_startup_wiring(
    cfg_result: LaserConfigResult,
) -> LaserStartupBundle:
    """Build optional LaserDirector and status provider from startup config result."""
    if not cfg_result.available or cfg_result.config is None:
        if cfg_result.reason == "invalid_config":
            errors = [str(err) for err in cfg_result.errors]

            def _invalid_status() -> dict:
                return {
                    "available": False,
                    "enabled": False,
                    "reason": "invalid_config",
                    "errors": errors,
                }

            return LaserStartupBundle(None, None, None, _invalid_status, None)
        return LaserStartupBundle(None, None, None, None, None)

    cfg = cfg_result.config
    default_scene = cfg.startup_scene
    initial_personality: Optional[LaserPersonality] = None
    if cfg.default_personality:
        personality = cfg.personalities.get(cfg.default_personality)
        if personality is not None:
            default_scene = personality.default_scene
            initial_personality = personality

    laser_director = LaserDirector(
        dry_run=cfg.dry_run,
        enabled=cfg.enabled,
        safe_scene=cfg.fallback_scene,
        default_scene=default_scene,
        emergency_scene=cfg.emergency_scene,
    )
    if cfg.default_personality:
        laser_director.set_personality(cfg.default_personality)
    if initial_personality is not None:
        laser_director.set_personality_config(initial_personality)

    midi_output = MidiOutput(
        port_name=cfg.midi_output_port,
        dry_run=cfg.dry_run,
    )
    midi_output.start()
    laser_executor = LaserSceneExecutor(
        config=cfg,
        midi_output=midi_output,
        personality=initial_personality,
    )

    def _status() -> dict:
        status = laser_director.status()
        status["executor"] = laser_executor.status()
        return status

    def _personality_provider(name: str) -> Optional[LaserPersonality]:
        return cfg.personalities.get(name)

    return LaserStartupBundle(
        laser_director=laser_director,
        laser_executor=laser_executor,
        midi_output=midi_output,
        status_provider=_status,
        personality_provider=_personality_provider,
    )

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

def start_osc_listener(
    event_queue: queue.Queue[BridgeEvent],
    state_manager: StateManager,
    *,
    master_direct_ready: Optional[Callable[[], bool]] = None,
) -> None:
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
        if master_direct_ready is not None:
            try:
                if master_direct_ready():
                    return
            except Exception:
                pass
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
        if os.environ.get(SCRIPTED_DIRECT_ENV) != "0":
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
            log.info("[MAIN][SHADOW] scripted-tl-osc  deck=%d  id=%d", target, track_id)  # A6 shadow log
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

    log.info("[MAIN] osc-listen  port=%d", OSC_LISTEN_PORT)
    if os.environ.get(SCRIPTED_DIRECT_ENV) != "0":
        log.info("[MAIN] rsr-direct  scripted=on  (%s=0 to re-enable tl-osc path)",
                 SCRIPTED_DIRECT_ENV)
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
    log.info("[MAIN] auto-populate  id=%d  action=db-query", track_id)
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
        log.warning("[MAIN] auto-populate-fail  id=%d  err=%s", track_id, exc)
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
            log.info("[MAIN] startup-deck  deck=%d  title=%s  bpm=%.1f  playing=%s",
                     deck, title, bpm, bool(info.get("playing", False)))
        except queue.Full:
            log.warning("[MAIN] queue-full  event=startup-deck  deck=%d  title=%s",
                        deck, title)

    if seeded:
        log.info("[MAIN] startup-preload  count=%d", seeded)


def _direct_master_startup_seed(rb_version: str, tl_deck: int) -> tuple[int, str]:
    """Return startup active deck and seed source, failing closed to TL."""
    if os.environ.get(MASTER_SEED_DIRECT_ENV) != "1":
        return tl_deck, "TL ENGINE STATE"

    if not rb_version:
        log.info("[MASTER-SEED] direct=none tl=%s using=tl reason=version_lookup_failed",
                 direct_master_label(tl_deck))
        return tl_deck, "TL ENGINE STATE"

    first = read_direct_master_status(rb_version)
    if not first.supported:
        log.info("[MASTER-SEED] direct=none tl=%s using=tl reason=unsupported_version",
                 direct_master_label(tl_deck))
        return tl_deck, "TL ENGINE STATE"
    if not first.readable:
        log.info("[MASTER-SEED] direct=none tl=%s using=tl reason=%s",
                 direct_master_label(tl_deck), first.reason or "unreadable")
        return tl_deck, "TL ENGINE STATE"
    if first.bridge_deck not in (1, 2):
        log.info("[MASTER-SEED] direct=%s tl=%s using=tl reason=%s",
                 direct_master_label(first.bridge_deck), direct_master_label(tl_deck),
                 first.reason or "none")
        return tl_deck, "TL ENGINE STATE"

    time.sleep(0.5)
    second = read_direct_master_status(
        rb_version,
        rb_pid=first.pid,
        base_addr=first.base,
    )
    if (
        not second.readable
        or second.bridge_deck not in (1, 2)
        or second.bridge_deck != first.bridge_deck
        or second.rb_raw != first.rb_raw
    ):
        reason = second.reason if not second.readable else "unstable"
        log.info("[MASTER-SEED] direct=%s tl=%s using=tl reason=%s",
                 direct_master_label(second.bridge_deck),
                 direct_master_label(tl_deck),
                 reason or "unstable")
        return tl_deck, "TL ENGINE STATE"

    log.info("[MASTER-SEED] direct=%s tl=%s using=direct",
             direct_master_label(first.bridge_deck), direct_master_label(tl_deck))
    return int(first.bridge_deck), "direct master seed"


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not _acquire_single_instance_lock():
        log.error("another rb_ss_bridge_v2 process is already running; exiting")
        return

    if is_debug() or "--debug" in sys.argv:
        enable_debug()

    log.info("[MAIN] starting")
    laser_cfg_result = load_laser_director_config()
    laser_bundle = _build_laser_startup_wiring(laser_cfg_result)
    laser_director = laser_bundle.laser_director
    laser_executor = laser_bundle.laser_executor
    laser_status_provider = laser_bundle.status_provider
    laser_personality_provider = laser_bundle.personality_provider
    midi_output = laser_bundle.midi_output
    log.info(
        "[MAIN] laser-config  reason=%s  available=%s  enabled=%s",
        laser_cfg_result.reason,
        laser_cfg_result.available,
        (
            laser_cfg_result.config.enabled
            if laser_cfg_result.config is not None
            else False
        ),
    )

    # Startup: pre-register scripted tracks from TL playlist.yaml + resolve filepaths
    preload_from_tl(str(TL_PLAYLIST_PATH))
    resolve_filepaths()
    start_ss_library_scan(
        callback=seed_soundswitch_id_cache,
        scripted_id_callback=seed_soundswitch_scripted_id_cache,
    )

    # Shared authoritative event queue.
    raw_event_queue: queue.Queue[BridgeEvent] = queue.Queue(maxsize=512)
    anlz_direct = os.environ.get(ANLZ_DIRECT_ENV) == "1"
    play_direct = os.environ.get(PLAY_DIRECT_ENV) == "1"
    track_load_direct = os.environ.get(TRACK_LOAD_DIRECT_ENV) == "1"
    master_direct = os.environ.get(MASTER_DIRECT_ENV) == "1"
    if track_load_direct and not anlz_direct:
        log.warning("[MAIN] rsr-config  track-load-direct requires anlz-direct; ignoring")
        track_load_direct = False
    rb_state_reader = None
    anlz_direct_ready_decks: set[int] = set()
    anlz_direct_ready_lock = threading.Lock()
    play_direct_ready_decks: set[int] = set()
    play_direct_ready_lock = threading.Lock()
    track_load_direct_ready_decks: set[int] = set()
    track_load_direct_ready_lock = threading.Lock()
    master_direct_ready_flag: bool = False
    master_direct_ready_lock = threading.Lock()
    event_queue = LOG.wrap_queue(raw_event_queue)

    # Position cache (RBMemoryReader → PositionCache → StateManager push loop)
    pos_cache = PositionCache()
    live_bpm = LiveBPMService()
    if live_bpm.disabled:
        log.warning("[MAIN] live-bpm-disabled  reason=%s=1  fallback=engine-state-bpm",
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
    sm = StateManager(
        event_queue,
        pos_cache,
        output,
        live_bpm=live_bpm,
        laser_director=laser_director,
        laser_executor=laser_executor,
        laser_personality_provider=laser_personality_provider,
    )
    validation_runner = ValidationRunner(
        conn,
        pos_cache,
        live_bpm,
        sm,
        laser_config_result=laser_cfg_result,
        midi_output=midi_output,
    )

    def _toggle_smart_drop() -> None:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.SMART_DROP_TOGGLE,
                deck=0,
                source="runtime_command",
            ))
        except queue.Full:
            log.warning("[MAIN] queue-full  event=smart-drop-toggle")

    def _toggle_smart_breakdown() -> None:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.SMART_BREAKDOWN_TOGGLE,
                deck=0,
                source="runtime_command",
                payload={},
            ))
        except queue.Full:
            log.warning("[MAIN] queue-full  event=smart-breakdown-toggle")

    def _toggle_laser_director() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_TOGGLE,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-toggle")
            return False

    def _set_laser_director(enabled: bool) -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_SET_ENABLED,
                deck=0,
                payload={"enabled": bool(enabled)},
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-set-enabled")
            return False

    def _laser_blackout() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_BLACKOUT,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-blackout")
            return False

    def _laser_clear_blackout() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_CLEAR_BLACKOUT,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-clear-blackout")
            return False

    def _laser_scene(scene: str, ttl_s: float) -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_SCENE,
                deck=0,
                payload={"scene": scene, "ttl_s": ttl_s},
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-scene")
            return False

    def _laser_clear_scene_override() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_CLEAR_SCENE_OVERRIDE,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-clear-scene-override")
            return False

    def _laser_set_personality(personality: str) -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LASER_SET_PERSONALITY,
                deck=0,
                payload={"personality": personality},
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=laser-set-personality")
            return False

    command_reader = CommandReader(
        validation_runner,
        smart_drop_toggle_callback=_toggle_smart_drop,
        smart_breakdown_toggle_callback=_toggle_smart_breakdown,
        laser_toggle_callback=_toggle_laser_director,
        laser_set_enabled_callback=_set_laser_director,
        laser_blackout_callback=_laser_blackout,
        laser_clear_blackout_callback=_laser_clear_blackout,
        laser_scene_callback=_laser_scene,
        laser_clear_scene_override_callback=_laser_clear_scene_override,
        laser_set_personality_callback=_laser_set_personality,
    )
    status_writer = StatusWriter(
        sm,
        live_bpm,
        pos_cache,
        conn,
        validation_runner,
        command_reader,
        laser_status_provider=laser_status_provider,
    )

    # Initialize master deck from last TL ENGINE STATE (fixes startup deck bug)
    init = read_initial_state(TL_LOG_PATH)
    rb_version_for_direct_master = read_rekordbox_version()
    initial_active_deck, initial_active_source = _direct_master_startup_seed(
        rb_version_for_direct_master,
        init['active_deck'],
    )
    sm.set_initial_state(initial_active_deck, source=initial_active_source)
    log.info("[MASTER-INIT] version=%s seed_source=%s deck=%d",
             rb_version_for_direct_master or "unknown",
             initial_active_source.replace(" ", "_"),
             initial_active_deck)

    # Filepath resolver (triggered by TRACK_LOADED, pushes FILEPATH_RESOLVED)
    resolver = FilepathResolver(event_queue, pos_cache)
    sm.attach_resolver(resolver)
    _seed_initial_decks(event_queue, init)

    # TL log tailer
    def _set_anlz_direct_ready(deck: int, ready: bool) -> None:
        if deck not in (1, 2):
            return
        with anlz_direct_ready_lock:
            if ready:
                anlz_direct_ready_decks.add(deck)
            else:
                anlz_direct_ready_decks.discard(deck)

    def _is_anlz_direct_ready(deck: int) -> bool:
        with anlz_direct_ready_lock:
            return deck in anlz_direct_ready_decks

    def _set_play_direct_ready(deck: int, ready: bool) -> None:
        if deck not in (1, 2):
            return
        with play_direct_ready_lock:
            if ready:
                play_direct_ready_decks.add(deck)
            else:
                play_direct_ready_decks.discard(deck)

    def _is_play_direct_ready(deck: int) -> bool:
        with play_direct_ready_lock:
            return deck in play_direct_ready_decks

    def _set_track_load_direct_ready(deck: int, ready: bool) -> None:
        if deck not in (1, 2):
            return
        with track_load_direct_ready_lock:
            if ready:
                track_load_direct_ready_decks.add(deck)
            else:
                track_load_direct_ready_decks.discard(deck)

    def _is_track_load_direct_ready(deck: int) -> bool:
        with track_load_direct_ready_lock:
            return deck in track_load_direct_ready_decks

    def _set_master_direct_ready(ready: bool) -> None:
        nonlocal master_direct_ready_flag
        with master_direct_ready_lock:
            master_direct_ready_flag = ready

    def _is_master_direct_ready() -> bool:
        with master_direct_ready_lock:
            return master_direct_ready_flag

    tailer = TLLogTailer(
        TL_LOG_PATH,
        event_queue,
        anlz_direct_ready=_is_anlz_direct_ready if anlz_direct else None,
        master_direct_ready=_is_master_direct_ready if master_direct else None,
        play_direct_ready=_is_play_direct_ready if play_direct else None,
        track_load_direct_ready=_is_track_load_direct_ready if track_load_direct else None,
    )

    if anlz_direct or play_direct or track_load_direct or master_direct:
        rb_version = read_rekordbox_version()
        if not rb_version:
            log.warning("[MAIN] rsr-skip  reason=version-lookup-failed")
        else:
            rb_event_queue = queue.Queue(maxsize=1)
            authoritative_kinds = set()
            if anlz_direct:
                authoritative_kinds.add(Ev.ANLZ_PATH)
            if play_direct:
                authoritative_kinds.update({Ev.PLAY, Ev.PAUSE})
            if track_load_direct:
                authoritative_kinds.add(Ev.TRACK_LOADED)
            if master_direct:
                authoritative_kinds.add(Ev.MASTER_CHANGED)
            rb_state_reader = make_rb_state_reader(
                rb_event_queue,
                rb_version,
                authoritative_queue=event_queue,
                authoritative_kinds=authoritative_kinds,
                drop_unrouted_events=True,
                shadow_logs_enabled=False,
                position_cache=pos_cache,
                anlz_available_callback=_set_anlz_direct_ready if anlz_direct else None,
                transport_available_callback=_set_play_direct_ready if play_direct else None,
                track_load_available_callback=(
                    _set_track_load_direct_ready if track_load_direct else None
                ),
                master_available_callback=_set_master_direct_ready if master_direct else None,
            )
            if getattr(rb_state_reader, "_offs", None) is None:
                log.warning("[MAIN] rsr-skip  reason=unsupported-version  version=%s", rb_version)
                rb_state_reader = None
            else:
                active_flags = []
                if anlz_direct:
                    active_flags.append("anlz")
                if play_direct:
                    active_flags.append("play")
                if track_load_direct:
                    active_flags.append("track-load")
                if master_direct:
                    active_flags.append("master")
                log.info("[MAIN] rsr-direct  flags=%s", "+".join(active_flags))

    # Memory reader (with drift detection + FM-11 RB_RESTARTED events)
    mem_reader = RBMemoryReader(
        pos_cache,
        drift_detector=DriftDetector(),
        event_queue=event_queue,
        deck_elapsed_hint=sm.get_deck_elapsed_ms,
        deck_playing_hint=sm.get_deck_playing,
        rb_version=rb_version_for_direct_master,
    )

    # MTC reader — ~25 fps position fallback from RB via IAC Bus 1.
    # Posts TC_UPDATE events for the active deck; state_manager ignores them
    # once PositionCache has a live memory snapshot for that deck.
    mtc = MTCReader(event_queue, sm.get_active_deck)
    mtc.start()

    # Start all components
    tailer.start()
    if rb_state_reader is not None:
        rb_state_reader.start()
    mem_reader.start()
    live_bpm.start()
    injector.start()
    sm_thread = sm.start()
    command_reader.start()
    status_writer.start()

    # OSC listener (scripted arm triggers)
    start_osc_listener(
        event_queue,
        sm,
        master_direct_ready=_is_master_direct_ready if master_direct else None,
    )

    direct_flags = []
    if anlz_direct:
        direct_flags.append("anlz")
    if play_direct:
        direct_flags.append("play")
    if track_load_direct:
        direct_flags.append("track-load")
    if master_direct:
        direct_flags.append("master")
    log.info(
        "[MAIN] running  state=on  active_deck=%d  seed=%s  rb_version=%s"
        "  tl=optional  rsr=%s  direct=%s  live_bpm=%s  follow=%s"
        "  phrase_arm=%s  smart_rearm=%s  smart_drop=%s  phrase_anchor=%s"
        "  scripted_direct=%s  osc=%d  log_control=%s",
        initial_active_deck,
        initial_active_source.replace(" ", "_"),
        rb_version_for_direct_master or "unknown",
        _onoff(rb_state_reader is not None),
        "+".join(direct_flags) if direct_flags else "none",
        _onoff(not live_bpm.disabled),
        _onoff(_env_enabled(LIVE_BPM_FOLLOW_ENV, "1")),
        _onoff(_env_enabled(AUTOLOOP_MASTER_PHRASE_ARM_ENV, "1")),
        _onoff(_env_enabled(SMART_REARM_EXPERIMENT_ENV, "0")),
        _onoff(
            _env_enabled(SMART_REARM_EXPERIMENT_ENV, "0")
            and _env_enabled(SMART_DROP_ENV, "1")
        ),
        _onoff(
            _env_enabled(SMART_REARM_EXPERIMENT_ENV, "0")
            and _env_enabled(PHRASE_ANCHOR_ENV, "1")
        ),
        _onoff(_env_enabled(SCRIPTED_DIRECT_ENV, "1")),
        OSC_LISTEN_PORT,
        os.environ.get("BRIDGE_LOG_CONTROL", "/tmp/rb_ss_bridge_v2_logging.json"),
    )
    LOG.start_control_watcher(log)

    # Graceful shutdown on SIGTERM / SIGINT
    def _shutdown(sig, frame):
        log.info("[MAIN] shutdown  sig=%d", sig)
        LOG.stop_control_watcher()
        status_writer.stop()
        command_reader.stop()
        sm.stop()
        tailer.stop()
        if rb_state_reader is not None:
            rb_state_reader.stop()
        mem_reader.stop()
        live_bpm.stop()
        mtc.stop()
        injector.stop()
        if midi_output is not None:
            midi_output.stop()
        discovery.stop()
        conn.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    def _reload_logging(sig, frame):
        LOG.reload_from_env()
        LOG.log_stats(log)
        log.info("[MAIN] log-reload  src=BRIDGE_LOG_*")

    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _reload_logging)

    # Block main thread
    sm_thread.join()


if __name__ == "__main__":
    main()
