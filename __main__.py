"""
rb_ss_bridge_v2 — entry point and wiring.

Replaces Frida hooks with:
  - Direct RB memory (master change, play/pause, track load, position)
  - MTC fallback    (active-deck timecode)
  - lsof / DB        (filepath identification on track load)

OSC is kept for bridge control triggers.

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
from typing import Any, Callable, Optional

from .config import OSC_LISTEN_PORT, RB_DB_PATH
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
    ANLZ_DIRECT_ENV,
    MASTER_DIRECT_ENV,
    PLAY_DIRECT_ENV,
    TRACK_LOAD_DIRECT_ENV,
    make_rb_state_reader,
    direct_master_label,
    read_direct_master_status,
)
from .scripted_tracks import resolve_filepaths
from .ss_library_scanner import start_ss_library_scan
from .state_manager import (
    AUTOLOOP_MASTER_PHRASE_ARM_ENV,
    LIVE_BPM_FOLLOW_ENV,
    PHRASE_ANCHOR_ENV,
    SMART_DROP_ENV,
    SMART_REARM_EXPERIMENT_ENV,
    StateManager,
)
from .diagnostics import DriftDetector, enable_debug, is_debug
from .live_bpm import LIVE_BPM_DISABLE_ENV, LiveBPMService, read_rekordbox_version
from .logging_manager import get_logging_manager
from .laser_config import LaserConfig, LaserConfigResult, load_laser_director_config
from .laser_director import LaserDirector
from .laser_executor import LaserSceneExecutor
from .laser_models import LaserPersonality
from .midi_output import MidiOutput
from .led_config import LEDConfigResult, load_led_look_director_config
from .led_look_director import LEDLookDirector, LED_AUTOMATION_ROLE_ORDER
from .govee_scene_adapter import GoveeSceneAdapter
from .govee_runtime_sender import GoveeRuntimeSender
from .govee_frame_renderer import GoveeFrameRenderer
from .govee_owner_state import GoveeOwnerStateMachine
from .govee_realtime_runner import GoveeRealtimeRunner
from .govee_lan_discovery import resolve_realtime_ip
from .govee_realtime_transport import GoveeRealtimeDryRunTransport, GoveeRealtimeTransport
from .led_dispatch_coordinator import LEDDispatchCoordinator
from .personality_resolver import PersonalityResolver, PlaylistCache
from .runtime_status import CommandReader, StatusWriter
from .validation_runner import ValidationRunner
from .tools.config_reloader import ConfigReloader, HOT_RELOAD_DISABLE_ENV

GOVEE_REALTIME_ENV = "RBSS_GOVEE_REALTIME"

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
    _LIME     = "\033[1;38;5;82m"

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
        ("[sm] energy-suggest",     _LIME),

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


@dataclass(frozen=True)
class LEDStartupBundle:
    led_director: Optional[LEDLookDirector]
    led_adapter: Optional[Any]
    status_provider: Optional[Callable[[], dict]]
    realtime_runner: Optional[GoveeRealtimeRunner] = None


def _build_personality_resolver(cfg: LaserConfig) -> PersonalityResolver:
    alias_index = {
        alias: name
        for name, personality in cfg.personalities.items()
        for alias in personality.aliases
    }
    bpm_bands = {
        name: (personality.bpm_band_min, personality.bpm_band_max)
        for name, personality in cfg.personalities.items()
    }
    return PersonalityResolver(
        alias_index=alias_index,
        bpm_priority=cfg.bpm_priority,
        bpm_bands=bpm_bands,
        known_personalities=set(cfg.personalities.keys()),
        default=cfg.default_personality,
    )


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


def _build_led_startup_wiring(
    cfg_result: LEDConfigResult,
) -> LEDStartupBundle:
    """Build optional LED director/adapter startup wiring."""
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

            return LEDStartupBundle(None, None, _invalid_status)
        return LEDStartupBundle(None, None, None)

    cfg = cfg_result.config
    try:
        led_director = LEDLookDirector(cfg, shuffled_roles=LED_AUTOMATION_ROLE_ORDER)
        govee_sender = None
        if not cfg.dry_run:
            govee_sender = GoveeRuntimeSender(cfg)
        cloud_adapter = GoveeSceneAdapter(
            cfg,
            send_command=govee_sender.send if govee_sender is not None else None,
            status_provider=govee_sender.status if govee_sender is not None else None,
        )
        led_adapter: Any = cloud_adapter
        realtime_runner: GoveeRealtimeRunner | None = None
        realtime_enabled = (
            os.environ.get(GOVEE_REALTIME_ENV) == "1"
            and any(target.realtime.enabled for target in cfg.targets.values())
        )
        if realtime_enabled:
            realtime_target = next(
                target for target in cfg.targets.values() if target.realtime.enabled
            )
            rt = realtime_target.realtime
            resolved_ip = rt.ip
            if cfg.dry_run:
                transport = GoveeRealtimeDryRunTransport(
                    ip=rt.ip,
                    port=rt.port,
                    segments=rt.segments,
                )
            else:
                # DHCP drifts the strip's IP; multicast-discover the live address
                # so a stale config IP no longer silently dark-outs realtime.
                resolved_ip, ip_source = resolve_realtime_ip(
                    rt.ip,
                    device_ref=realtime_target.device_ref,
                    expected_sku=realtime_target.expected_model,
                    timeout_s=3.0,
                )
                if resolved_ip != rt.ip:
                    log.info(
                        "[MAIN] govee realtime ip via %s: config=%s -> %s",
                        ip_source, rt.ip, resolved_ip,
                    )
                else:
                    log.info(
                        "[MAIN] govee realtime ip source=%s ip=%s", ip_source, resolved_ip
                    )
                transport = GoveeRealtimeTransport(
                    resolved_ip,
                    port=rt.port,
                    segments=rt.segments,
                    header_bytes=rt.header_bytes,
                    stretch=rt.stretch,
                    activate_pt=rt.activate_pt,
                    deactivate_pt=rt.deactivate_pt,
                )
                transport.deactivate()
            realtime_runner = GoveeRealtimeRunner(
                transport,
                GoveeFrameRenderer(),
                segments=rt.segments,
                fps=rt.fps,
            )
            led_adapter = LEDDispatchCoordinator(
                cloud_adapter,
                realtime_runner,
                GoveeOwnerStateMachine(),
                cfg,
            )
    except Exception as exc:
        log.warning("[MAIN] led-startup-failed  err=%s", exc)

        def _failed_status() -> dict:
            return {
                "available": False,
                "enabled": False,
                "reason": "startup_error",
                "last_error": f"{type(exc).__name__}: {exc}",
            }

        return LEDStartupBundle(None, None, _failed_status)

    def _status() -> dict:
        payload = led_director.status()
        payload["adapter"] = led_adapter.status()
        return payload

    return LEDStartupBundle(led_director, led_adapter, _status, realtime_runner)

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


# ── OSC listener (bridge control triggers) ────────────────────────────────────

def start_osc_listener(
    event_queue: queue.Queue[BridgeEvent],
    state_manager: StateManager,
    *,
    master_direct_ready: Optional[Callable[[], bool]] = None,
) -> None:
    """Listen on UDP for bridge active-deck and track-loaded control messages."""
    try:
        from pythonosc import dispatcher as osc_dispatcher  # type: ignore
        from pythonosc import osc_server                    # type: ignore
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
        # Use the deck that most recently received a TRACK_LOADED event.
        # This is more reliable than get_active_deck() when loading on the non-master deck
        # because track-loaded events carry explicit deck info while this OSC message does not.
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
            log.info("[MAIN][SHADOW] scripted-osc  deck=%d  id=%d", target, track_id)
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
        log.info("[MAIN] rsr-direct  scripted=on  (%s=0 to re-enable legacy osc path)",
                 SCRIPTED_DIRECT_ENV)
    threading.Thread(target=srv.serve_forever, name="osc-server", daemon=True).start()


def _auto_populate(track_id: int, active_deck: int, eq: queue.Queue) -> None:
    """Query RB DB for an unknown track_id and register it, then fire SCRIPTED_ARM."""
    import warnings
    log.info("[MAIN] auto-populate  id=%d  action=db-query", track_id)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
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


def _direct_master_startup_seed(rb_version: str, fallback_deck: int = 1) -> tuple[int, str]:
    """Return startup active deck and seed source, defaulting to deck 1."""
    if os.environ.get(MASTER_SEED_DIRECT_ENV) != "1":
        return fallback_deck, "default startup"

    if not rb_version:
        log.info("[MASTER-SEED] direct=none fallback=%s using=fallback reason=version_lookup_failed",
                 direct_master_label(fallback_deck))
        return fallback_deck, "default startup"

    first = read_direct_master_status(rb_version)
    if not first.supported:
        log.info("[MASTER-SEED] direct=none fallback=%s using=fallback reason=unsupported_version",
                 direct_master_label(fallback_deck))
        return fallback_deck, "default startup"
    if not first.readable:
        log.info("[MASTER-SEED] direct=none fallback=%s using=fallback reason=%s",
                 direct_master_label(fallback_deck), first.reason or "unreadable")
        return fallback_deck, "default startup"
    if first.bridge_deck not in (1, 2):
        log.info("[MASTER-SEED] direct=%s fallback=%s using=fallback reason=%s",
                 direct_master_label(first.bridge_deck), direct_master_label(fallback_deck),
                 first.reason or "none")
        return fallback_deck, "default startup"

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
        log.info("[MASTER-SEED] direct=%s fallback=%s using=fallback reason=%s",
                 direct_master_label(second.bridge_deck),
                 direct_master_label(fallback_deck),
                 reason or "unstable")
        return fallback_deck, "default startup"

    log.info("[MASTER-SEED] direct=%s fallback=%s using=direct",
             direct_master_label(first.bridge_deck), direct_master_label(fallback_deck))
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
    led_cfg_result = load_led_look_director_config()
    led_bundle = _build_led_startup_wiring(led_cfg_result)
    led_look_director = led_bundle.led_director
    led_scene_adapter = led_bundle.led_adapter
    led_status_provider = led_bundle.status_provider
    log.info(
        "[MAIN] led-config  reason=%s  available=%s  enabled=%s",
        led_cfg_result.reason,
        led_cfg_result.available,
        (
            led_cfg_result.config.enabled
            if led_cfg_result.config is not None
            else False
        ),
    )

    # Startup: resolve any scripted tracks already registered by bridge config/tests.
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
        led_look_director=led_look_director,
        led_scene_adapter=led_scene_adapter,
    )
    if led_bundle.realtime_runner is not None:
        led_bundle.realtime_runner.set_beat_provider(sm.get_active_beat_anchor)
        led_bundle.realtime_runner.start()
    if laser_cfg_result.available and laser_cfg_result.config is not None:
        cfg = laser_cfg_result.config
        personality_resolver = _build_personality_resolver(cfg)
        playlist_cache = PlaylistCache(RB_DB_PATH, folder_name="BY GENRE")
        sm.attach_personality_resolver(personality_resolver)
        sm.attach_personality_playlist_cache(playlist_cache)
        threading.Thread(
            target=playlist_cache.refresh,
            name="personality-cache-bootstrap",
            daemon=True,
        ).start()
        log.info(
            "[MAIN] personality-resolver attached aliases=%d bpm_priority=%d",
            sum(len(p.aliases) for p in cfg.personalities.values()),
            len(cfg.bpm_priority),
        )
    validation_runner = ValidationRunner(
        conn,
        pos_cache,
        live_bpm,
        sm,
        laser_config_result=laser_cfg_result,
        midi_output=midi_output,
        laser_status_provider=laser_status_provider,
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

    def _set_led_look_director(enabled: bool) -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LED_SET_ENABLED,
                deck=0,
                payload={"enabled": bool(enabled)},
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=led-set-enabled")
            return False

    def _led_scene(look: str, ttl_s: float | None, target: str | None = None) -> bool:
        payload: dict[str, object] = {"look": look}
        if ttl_s is not None:
            payload["ttl_s"] = float(ttl_s)
        if target:
            payload["target"] = target
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LED_SCENE,
                deck=0,
                payload=payload,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=led-scene")
            return False

    def _led_blackout(reason: str | None, target: str | None = None) -> bool:
        payload: dict[str, object] = {}
        if reason:
            payload["reason"] = reason
        if target:
            payload["target"] = target
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LED_BLACKOUT,
                deck=0,
                payload=payload,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=led-blackout")
            return False

    def _led_clear_blackout() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LED_CLEAR_BLACKOUT,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=led-clear-blackout")
            return False

    def _led_clear_scene_override() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.LED_CLEAR_SCENE_OVERRIDE,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=led-clear-scene-override")
            return False

    def _toggle_record_session(path: Optional[str], dedup: bool) -> bool:
        if not path:
            path = f"/tmp/rbss-session-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        return sm.toggle_session_recording(path, dedup=dedup)

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
        led_set_enabled_callback=_set_led_look_director,
        led_scene_callback=_led_scene,
        led_blackout_callback=_led_blackout,
        led_clear_blackout_callback=_led_clear_blackout,
        led_clear_scene_override_callback=_led_clear_scene_override,
        record_session_toggle_callback=_toggle_record_session,
    )
    sm_led_status_provider = getattr(sm, "led_status_provider", None)
    if not callable(sm_led_status_provider):
        sm_led_status_provider = led_status_provider
    status_writer = StatusWriter(
        sm,
        live_bpm,
        pos_cache,
        conn,
        validation_runner,
        command_reader,
        laser_status_provider=laser_status_provider,
        led_status_provider=sm_led_status_provider,
    )

    # Initialize master deck from guarded direct read when available, otherwise deck 1.
    rb_version_for_direct_master = read_rekordbox_version()
    initial_active_deck, initial_active_source = _direct_master_startup_seed(
        rb_version_for_direct_master,
        1,
    )
    sm.set_initial_state(initial_active_deck, source=initial_active_source)
    log.info("[MASTER-INIT] version=%s seed_source=%s deck=%d",
             rb_version_for_direct_master or "unknown",
             initial_active_source.replace(" ", "_"),
             initial_active_deck)

    # Filepath resolver (triggered by TRACK_LOADED, pushes FILEPATH_RESOLVED)
    resolver = FilepathResolver(event_queue, pos_cache)
    sm.attach_resolver(resolver)

    # Direct-reader readiness gates
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
        "  rsr=%s  direct=%s  live_bpm=%s  follow=%s"
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

    def _on_laser_config_reload(result: LaserConfigResult) -> None:
        if not result.available or result.config is None:
            detail = "; ".join(result.errors) if result.errors else result.reason
            log.warning(
                "[MAIN] laser-config-reload  changed=1  status=invalid  reason=%s",
                detail,
            )
            return
        cfg = result.config
        sm.attach_personality_resolver(_build_personality_resolver(cfg))
        sm.attach_laser_personality_provider(
            lambda name, cfg=cfg: cfg.personalities.get(name)
        )
        active_name = ""
        get_personality = getattr(laser_director, "get_personality", None)
        if callable(get_personality):
            active_name = str(get_personality() or "")
        active_personality = cfg.personalities.get(active_name) if active_name else None
        if active_name and active_personality is None:
            log.warning(
                "[MAIN] laser-config-reload  active_personality=%r missing "
                "from new config; falling back to default=%r",
                active_name,
                cfg.default_personality,
            )
            active_name = cfg.default_personality
            active_personality = cfg.personalities.get(active_name)
        existing = sm.get_last_applied_personality()
        active_unchanged = bool(
            active_name
            and active_personality is not None
            and active_personality == existing
        )
        if active_name and active_personality is not None and not active_unchanged:
            try:
                event_queue.put_nowait(
                    BridgeEvent(
                        kind=Ev.LASER_SET_PERSONALITY,
                        deck=0,
                        payload={"personality": active_name},
                        source="internal",
                    )
                )
            except queue.Full:
                log.warning(
                    "[MAIN] queue-full  event=laser-set-personality "
                    "reason=reload  active=%r",
                    active_name,
                )
        log.info(
            "[MAIN] laser-config-reload  changed=1  status=applied  "
            "action=resolver_and_provider_rebuilt aliases=%d "
            "bpm_priority=%d active_unchanged=%s",
            sum(len(p.aliases) for p in cfg.personalities.values()),
            len(cfg.bpm_priority),
            "yes" if active_unchanged else "no",
        )

    config_reloader = ConfigReloader(on_reload=_on_laser_config_reload)
    hot_reload_disabled = os.environ.get(HOT_RELOAD_DISABLE_ENV) == "1"
    if hot_reload_disabled:
        log.info("[MAIN] laser-config-reload  enabled=0  reason=%s", HOT_RELOAD_DISABLE_ENV)
    else:
        log.info("[MAIN] laser-config-reload  enabled=1  path=%s", config_reloader.config_path)
        config_reloader.start()

    # Graceful shutdown on SIGTERM / SIGINT
    def _shutdown(sig, frame):
        log.info("[MAIN] shutdown  sig=%d", sig)
        LOG.stop_control_watcher()
        config_reloader.stop()
        status_writer.stop()
        command_reader.stop()
        sm.stop()
        if rb_state_reader is not None:
            rb_state_reader.stop()
        mem_reader.stop()
        live_bpm.stop()
        mtc.stop()
        injector.stop()
        if midi_output is not None:
            midi_output.stop()
        if led_scene_adapter is not None:
            led_scene_adapter.shutdown()
        if led_bundle.realtime_runner is not None:
            led_bundle.realtime_runner.stop()
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
