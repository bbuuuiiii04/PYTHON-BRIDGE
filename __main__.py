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

import atexit
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
from .os2l_injector import INJECT_PATH_ENV, OS2LInjector
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
from .rb_offsets import RBOffsetVersion, load_offsets_for_version
from .scripted_tracks import resolve_filepaths
from . import spectral_cache
from .ss_library_scanner import start_ss_library_scan
from .state_manager import (
    AUTOLOOP_MASTER_PHRASE_ARM_ENV,
    LIVE_BPM_FOLLOW_ENV,
    PHRASE_ANCHOR_ENV,
    SMART_DROP_ENV,
    SMART_REARM_EXPERIMENT_ENV,
    StateManager,
)
from .diagnostics import DriftDetector
from .live_bpm import LIVE_BPM_DISABLE_ENV, LiveBPMService, read_rekordbox_version
from . import bridge_log
from .laser_config import LaserConfig, LaserConfigResult, load_laser_director_config
from .laser_director import LaserDirector
from .laser_executor import LaserSceneExecutor
from .laser_output_backend import (
    DualTriggerBackend,
    LaserOutputBackend,
    MidiOutputBackend,
    NoneBackend,
    PackOutputBackend,
)
from .laser_models import LaserPersonality
from .midi_output import MidiOutput
from .artnet_truth import ArtNetTruthSink, load_truth_check_env
from .soundswitch_frame_sender import SoundSwitchFrameSender
from .soundswitch_laser_player import LaserPackPlayer
from .laser_color_engine import load_laser_color_map
from .soundswitch_midi_input import SoundSwitchMidiInputGroup
from .soundswitch_pack_loader import LoadedPack, load_pack
from .soundswitch_pack_runtime import PackRuntime
from .soundswitch_pack_controller import SoundSwitchPackController
from .soundswitch_pack_player_config import (
    SoundSwitchPackPlayerConfigResult,
    load_soundswitch_pack_player_config,
)
from .led_config import LEDConfigResult, load_led_look_director_config
from .led_look_director import LEDLookDirector, LED_AUTOMATION_ROLE_ORDER
from .led_color_engine import LedColorEngine
from .led_identity_v2 import ALL_ZONES, IdentityStore
from .led_palette_control import LIVE_PALETTE_STATE_PATH
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

bridge_log.init()
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
class SoundSwitchPackStartupBundle:
    """Startup-only pack resources; ``laser_backend=None`` means legacy MIDI."""

    laser_backend: Optional[LaserOutputBackend]
    pack: Optional[LoadedPack]
    player: Optional[LaserPackPlayer]
    midi_input: Optional[SoundSwitchMidiInputGroup]
    frame_sender: Optional[SoundSwitchFrameSender]
    reason: str
    truth_sink: Optional[ArtNetTruthSink] = None
    truth_check_reason: str = "disabled"


@dataclass(frozen=True)
class LEDStartupBundle:
    led_director: Optional[LEDLookDirector]
    led_adapter: Optional[Any]
    status_provider: Optional[Callable[[], dict]]
    realtime_runner: Optional[GoveeRealtimeRunner] = None
    led_color_engine: Optional[Any] = None
    led_identity_store: Optional[IdentityStore] = None


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
    *,
    backend: Optional[LaserOutputBackend] = None,
    dual_with_midi: bool = False,
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
        scenes=cfg.scenes,
    )
    if cfg.default_personality:
        laser_director.set_personality(cfg.default_personality)
    if initial_personality is not None:
        laser_director.set_personality_config(initial_personality)

    midi_output: Optional[MidiOutput] = None
    laser_backend = backend
    if laser_backend is None:
        midi_output = MidiOutput(
            port_name=cfg.midi_output_port,
            dry_run=cfg.dry_run,
        )
        midi_output.start()
        laser_backend = MidiOutputBackend(midi_output)
    elif dual_with_midi:
        if cfg.dry_run:
            log.warning(
                "[MAIN] artnet-truth-check dry_run=1 — SoundSwitch receives no "
                "real MIDI during the exam; the comparison will be vacuous"
            )
        midi_output = MidiOutput(
            port_name=cfg.midi_output_port,
            dry_run=cfg.dry_run,
        )
        midi_output.start()
        laser_backend = DualTriggerBackend(
            pack_backend=laser_backend,
            midi_backend=MidiOutputBackend(midi_output),
        )
    laser_executor = LaserSceneExecutor(
        config=cfg,
        backend=laser_backend,
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


def _build_soundswitch_pack_startup(
    cfg_result: SoundSwitchPackPlayerConfigResult,
    *,
    pack_loader=load_pack,
    player_factory=LaserPackPlayer,
    frame_sender_factory=SoundSwitchFrameSender,
    midi_input_factory=SoundSwitchMidiInputGroup,
    truth_sink_factory=ArtNetTruthSink,
    truth_env_loader=load_truth_check_env,
    event_sink=None,
    extra_midi_bindings=(),
) -> SoundSwitchPackStartupBundle:
    """Choose pack-vs-legacy output before starting any output worker.

    ``laser_backend=None`` deliberately preserves the existing MIDI startup
    path.  An explicit none/dry-run config returns ``NoneBackend`` so neither
    MIDI nor DMX is opened.  When pack mode is requested but the direct DMX
    hardware is not available, return ``None`` so the legacy SoundSwitch/IAC
    path stays alive until pack hardware can actually start.
    """
    if not cfg_result.available or cfg_result.config is None:
        return SoundSwitchPackStartupBundle(
            None, None, None, None, None,
            f"legacy_midi_{cfg_result.reason}",
        )
    cfg = cfg_result.config
    if not cfg.enabled:
        return SoundSwitchPackStartupBundle(
            None, None, None, None, None, "legacy_midi_disabled",
        )

    try:
        pack = pack_loader(cfg.pack_path)
    except Exception as exc:
        log.warning(
            "[MAIN] soundswitch-pack disabled  reason=pack_load_failed  error=%s",
            type(exc).__name__,
        )
        return SoundSwitchPackStartupBundle(
            NoneBackend(), None, None, None, None, "pack_load_failed",
        )

    player = player_factory(pack, parity_live=True)
    truth_env = truth_env_loader()
    if truth_env.enabled:
        midi_kwargs = {"stale_timeout_ms": cfg.controller_hold_timeout_ms}
        if event_sink is not None:
            midi_kwargs["event_sink"] = event_sink
        if extra_midi_bindings:
            midi_kwargs["extra_bindings"] = extra_midi_bindings
        midi_input = midi_input_factory(
            pack.learned_midi_bindings,
            cfg.midi_input_aliases,
            **midi_kwargs,
        )
        backend = PackOutputBackend(
            scene_to_identity=dict(pack.bridge_scene_crosswalk),
            frame_sender=None,
        )
        truth_sink = truth_sink_factory(
            universe=truth_env.universe,
            fixture_map=cfg.fixture_map,
            targets=truth_env.targets,
            sidecar_path=truth_env.sidecar_path,
            pack_sha256=getattr(pack, "manifest_sha256", "") or "",
            queue_bound=truth_env.queue_bound,
        )
        return SoundSwitchPackStartupBundle(
            backend, pack, player, midi_input, None,
            "artnet_truth_check", truth_sink, truth_env.reason,
        )
    if truth_env.reason not in ("disabled",):
        log.warning("[MAIN] artnet-truth-check disabled  reason=%s", truth_env.reason)
    if cfg.dry_run or cfg.output_backend == "none":
        return SoundSwitchPackStartupBundle(
            NoneBackend(), pack, player, None, None,
            "dry_run" if cfg.dry_run else "none",
        )
    if cfg.output_backend == "midi":
        return SoundSwitchPackStartupBundle(
            None, pack, player, None, None, "legacy_midi_configured",
        )
    if not cfg.enttec_port:
        log.warning("[MAIN] soundswitch-pack disabled  reason=missing_enttec_port")
        return SoundSwitchPackStartupBundle(
            None, pack, player, None, None, "pack_start_failed",
        )

    midi_input: Optional[SoundSwitchMidiInputGroup] = None
    frame_sender: Optional[SoundSwitchFrameSender] = None
    try:
        midi_kwargs = {"stale_timeout_ms": cfg.controller_hold_timeout_ms}
        if event_sink is not None:
            midi_kwargs["event_sink"] = event_sink
        if extra_midi_bindings:
            midi_kwargs["extra_bindings"] = extra_midi_bindings
        midi_input = midi_input_factory(
            pack.learned_midi_bindings,
            cfg.midi_input_aliases,
            **midi_kwargs,
        )
        frame_sender = frame_sender_factory(
            cfg.enttec_port,
            fixture_map=cfg.fixture_map,
            idle_blackout_s=cfg.frame_stale_timeout_ms / 1000.0,
        )
        backend = PackOutputBackend(
            scene_to_identity=dict(pack.bridge_scene_crosswalk),
            frame_sender=frame_sender,
        )
    except Exception as exc:
        if frame_sender is not None:
            try:
                frame_sender.stop()
            except Exception:
                pass
        log.warning(
            "[MAIN] soundswitch-pack disabled  reason=worker_start_failed  error=%s",
            type(exc).__name__,
        )
        return SoundSwitchPackStartupBundle(
            None, pack, player, midi_input, None, "pack_start_failed",
        )
    return SoundSwitchPackStartupBundle(
        backend, pack, player, midi_input, frame_sender, "pack",
    )


def _start_soundswitch_pack_workers(
    bundle: SoundSwitchPackStartupBundle,
) -> SoundSwitchPackStartupBundle:
    """Start a fully constructed pack bundle after cleanup authority exists."""
    if bundle.reason == "artnet_truth_check":
        midi_input = bundle.midi_input
        if midi_input is not None:
            try:
                midi_input.start()
            except Exception as exc:
                try:
                    midi_input.stop()
                except Exception:
                    pass
                midi_input = None
                log.warning(
                    "[MAIN] soundswitch-pack disabled  reason=worker_start_failed  error=%s",
                    type(exc).__name__,
                )
        try:
            if bundle.truth_sink is not None:
                bundle.truth_sink.start()
        except Exception as exc:
            if bundle.truth_sink is not None:
                try:
                    bundle.truth_sink.stop()
                except Exception:
                    pass
            log.warning(
                "[MAIN] soundswitch-pack disabled  reason=worker_start_failed  error=%s",
                type(exc).__name__,
            )
            return SoundSwitchPackStartupBundle(
                None, bundle.pack, bundle.player, midi_input, None, "pack_start_failed",
                None, bundle.truth_check_reason,
            )
        if midi_input is not bundle.midi_input:
            return SoundSwitchPackStartupBundle(
                bundle.laser_backend, bundle.pack, bundle.player, midi_input,
                bundle.frame_sender, bundle.reason, bundle.truth_sink,
                bundle.truth_check_reason,
            )
        return bundle
    if bundle.reason != "pack" or bundle.frame_sender is None:
        return bundle
    midi_input = bundle.midi_input
    if midi_input is not None:
        try:
            midi_input.start()
        except Exception as exc:
            try:
                midi_input.stop()
            except Exception:
                pass
            midi_input = None
            log.warning(
                "[MAIN] soundswitch-pack disabled  reason=worker_start_failed  error=%s",
                type(exc).__name__,
            )
    try:
        bundle.frame_sender.start()
    except Exception as exc:
        try:
            bundle.frame_sender.stop()
        except Exception:
            pass
        log.warning(
            "[MAIN] soundswitch-pack disabled  reason=worker_start_failed  error=%s",
            type(exc).__name__,
        )
        return SoundSwitchPackStartupBundle(
            None, bundle.pack, bundle.player, midi_input, None, "pack_start_failed",
        )
    if midi_input is not bundle.midi_input:
        return SoundSwitchPackStartupBundle(
            bundle.laser_backend, bundle.pack, bundle.player, midi_input,
            bundle.frame_sender, bundle.reason,
        )
    return bundle


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
        # M1b WI-1: instantiate the color engine ONLY when a color_engine config
        # block parsed successfully.  Live config has no block ⇒ None ⇒ no engine
        # ⇒ zero behavior change.
        engine = (
            LedColorEngine(cfg.color_engine)
            if cfg.color_engine is not None
            else None
        )
        identity_store = (
            IdentityStore.load(cfg.color_engine.v2.store_path)
            if cfg.color_engine is not None
            and cfg.color_engine.v2 is not None
            and cfg.color_engine.v2.enabled
            else None
        )
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
                white_templates=load_laser_color_map().white_templates,
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

    return LEDStartupBundle(
        led_director, led_adapter, _status, realtime_runner, engine, identity_store
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
        log.error("python-osc not installed - scripted arm triggers will not work")
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
        if deck <= 0:
            return
        bridge_deck = ((deck - 1) % 2) + 1
        event_queue.put_nowait(BridgeEvent(
            kind=Ev.LEGACY_ACTIVE_DECK, deck=bridge_deck, source="osc",
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
        if target not in (1, 2):
            log.info("[MAIN][SHADOW] scripted-osc ignored  deck=%s  reason=no_active_deck", target)
            return
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
        log.error("OSC listener failed on port %d: %s", OSC_LISTEN_PORT, exc)
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
    if first.rb_raw not in (0, 1) or first.bridge_deck not in (1, 2):
        log.info("[MASTER-SEED] direct=%s fallback=%s using=fallback reason=%s",
                 direct_master_label(first.bridge_deck), direct_master_label(fallback_deck),
                 "unsupported_raw_deck" if first.rb_raw in (2, 3) else (first.reason or "none"))
        return fallback_deck, "default startup"

    time.sleep(0.5)
    second = read_direct_master_status(
        rb_version,
        rb_pid=first.pid,
        base_addr=first.base,
    )
    if (
        not second.readable
        or second.rb_raw not in (0, 1)
        or second.bridge_deck not in (1, 2)
        or second.bridge_deck != first.bridge_deck
        or second.rb_raw != first.rb_raw
    ):
        reason = second.reason if not second.readable else (
            "unsupported_raw_deck" if second.rb_raw in (2, 3) else "unstable"
        )
        log.info("[MASTER-SEED] direct=%s fallback=%s using=fallback reason=%s",
                 direct_master_label(second.bridge_deck),
                 direct_master_label(fallback_deck),
                 reason or "unstable")
        return fallback_deck, "default startup"

    log.info("[MASTER-SEED] direct=%s fallback=%s using=direct",
             direct_master_label(first.bridge_deck), direct_master_label(fallback_deck))
    return int(first.bridge_deck), "direct master seed"


def _offsets_have_mixer_authority(offsets: Optional[RBOffsetVersion]) -> bool:
    if offsets is None:
        return False
    return all((
        offsets.mixer_deck1_upfader_raw is not None,
        offsets.mixer_deck2_upfader_raw is not None,
        offsets.mixer_deck1_low_raw is not None,
        offsets.mixer_deck2_low_raw is not None,
    ))


def _rb_state_authoritative_kinds(
    *,
    anlz_direct: bool,
    play_direct: bool,
    track_load_direct: bool,
    master_direct: bool,
    mixer_authority: bool,
) -> set[str]:
    kinds: set[str] = set()
    if anlz_direct:
        kinds.add(Ev.ANLZ_PATH)
    if play_direct or mixer_authority:
        kinds.update({Ev.PLAY, Ev.PAUSE})
    if track_load_direct:
        kinds.add(Ev.TRACK_LOADED)
    if master_direct or mixer_authority:
        kinds.add(Ev.MASTER_CHANGED)
    if mixer_authority:
        kinds.add(Ev.MIXER_STATE)
    return kinds


def _initial_show_deck_for_startup(
    initial_active_deck: int,
    initial_active_source: str,
    *,
    mixer_authority: bool,
) -> tuple[int, bool]:
    rb_master_valid = initial_active_source == "direct master seed"
    show_deck = 0 if mixer_authority and not rb_master_valid else initial_active_deck
    return show_deck, rb_master_valid


# ── Main ─────────────────────────────────────────────────────────────────────

def _shutdown_zero_pack_outputs(
    pack_output_owners: dict[str, Any],
    sm: Any | None,
) -> None:
    """Send a final zero frame + close on shutdown for the pack's DMX output.

    Zeroes the LIVE runtime sender/input (authoritative after any runtime swap)
    AND the startup-owned slots. All calls are idempotent: stop() on an already-
    stopped sender is a no-op, and the no-swap case where the live sender IS the
    startup sender simply stops the same object once. sm is None only during the
    pre-StateManager startup window, where only the startup slots exist.
    """
    # Live runtime first: this is the only handle to a sender installed by a
    # runtime enable/reload/backend swap. Single atomic read of the runtime.
    if sm is not None:
        try:
            rt = sm.get_pack_runtime()
        except Exception:
            rt = None
        if rt is not None:
            live_sender = getattr(rt, "frame_sender", None)
            if live_sender is not None:
                try:
                    live_sender.stop()
                except Exception:
                    pass
            live_input = getattr(rt, "midi_input", None)
            if live_input is not None:
                try:
                    live_input.stop()
                except Exception:
                    pass
            live_truth_sink = getattr(rt, "truth_sink", None)
            if live_truth_sink is not None:
                try:
                    live_truth_sink.stop()
                except Exception:
                    pass
    # Startup-owned slots: covers the pre-sm early-shutdown window and is a
    # harmless no-op once the live sender (same object pre-swap) is stopped.
    sender = pack_output_owners.pop("sender", None)
    midi_input = pack_output_owners.pop("midi_input", None)
    truth_sink = pack_output_owners.pop("truth_sink", None)
    if sender is not None:
        try:
            sender.stop()
        except Exception:
            pass
    if midi_input is not None:
        try:
            midi_input.stop()
        except Exception:
            pass
    if truth_sink is not None:
        try:
            truth_sink.stop()
        except Exception:
            pass


def _start_spectral_cache_eviction_if_enabled() -> threading.Thread | None:
    if (
        os.environ.get("RBSS_SMART_REARM_EXPERIMENT") != "1"
        or os.environ.get("RBSS_SPECTRAL_ENABLE") != "1"
    ):
        return None

    def _worker() -> None:
        evicted = spectral_cache.evict_stale()
        evicted_v4 = spectral_cache.evict_stale_v4()
        log.info(
            "[MAIN] spectral-cache-evict  evicted=%d  evicted_v4=%d",
            evicted,
            evicted_v4,
        )

    thread = threading.Thread(target=_worker, name="spectral-cache-evict", daemon=True)
    thread.start()
    return thread


def main() -> None:
    if not _acquire_single_instance_lock():
        log.error("another rb_ss_bridge_v2 process is already running; exiting")
        return

    # Pin the live palette feedback path now, long before any StateManager /
    # LedPaletteControl is constructed below. This is the ONLY place that
    # sets RBSS_PALETTE_STATE_PATH for the real bridge process; every other
    # construction path (ad-hoc verification scripts, direct test-module
    # runs, subagent scratch runs) never sets it and falls through to a
    # per-pid throwaway file (led_palette_control._resolve_palette_state_path),
    # so a stray process is structurally unable to write this live file and
    # fight the real bridge's PaletteFeedbackWriter over it. setdefault() so
    # an operator-exported override still wins.
    os.environ.setdefault("RBSS_PALETTE_STATE_PATH", LIVE_PALETTE_STATE_PATH)

    # Install owner cleanup before any pack-controlled port is opened.  The
    # mutable slots let the handler/atexit path own resources even while the
    # rest of bridge startup is still in progress.
    pack_output_owners: dict[str, Any] = {"sender": None, "midi_input": None, "truth_sink": None}
    _sm_holder: dict[str, Any] = {"sm": None}  # set after StateManager is built

    def _cleanup_pack_outputs() -> None:
        _shutdown_zero_pack_outputs(pack_output_owners, _sm_holder["sm"])

    def _early_shutdown(sig, frame):
        log.info("[MAIN] shutdown  sig=%d  phase=startup", sig)
        _cleanup_pack_outputs()
        raise SystemExit(0)

    atexit.register(_cleanup_pack_outputs)
    signal.signal(signal.SIGTERM, _early_shutdown)
    signal.signal(signal.SIGINT, _early_shutdown)

    if "--debug" in sys.argv:
        # bridge_log.init() already applied BRIDGE_DEBUG=1 at module-import
        # time (before argv parsing could see --debug); a direct root-level
        # set here is the equivalent no-re-init fix so both paths land on
        # the same DEBUG-everywhere behavior.
        logging.root.setLevel(logging.DEBUG)

    log.info("[MAIN] starting")
    # Shared authoritative event queue.
    raw_event_queue: queue.Queue[BridgeEvent] = queue.Queue(maxsize=512)
    event_queue = bridge_log.TraceQueue(raw_event_queue)
    laser_cfg_result = load_laser_director_config()
    soundswitch_pack_cfg_result = load_soundswitch_pack_player_config()
    led_cfg_result = load_led_look_director_config()
    palette_control_bindings = (
        led_cfg_result.config.color_engine.palette_control_bindings
        if (
            led_cfg_result.config is not None
            and led_cfg_result.config.color_engine is not None
        )
        else ()
    )
    palette_control_config = (
        led_cfg_result.config.color_engine.palette_control
        if (
            led_cfg_result.config is not None
            and led_cfg_result.config.color_engine is not None
        )
        else {}
    )
    def _pad_event_sink(ev: BridgeEvent) -> None:
        # LoggingEventQueue exposes put_nowait (not put); queue-full drops the
        # pad event with a log line so the MIDI input worker can never die on
        # a burst.
        try:
            event_queue.put_nowait(ev)
        except queue.Full:
            log.warning("[MAIN] queue-full  event=%s", ev.kind)

    soundswitch_pack_bundle = _build_soundswitch_pack_startup(
        soundswitch_pack_cfg_result,
        event_sink=_pad_event_sink,
        extra_midi_bindings=palette_control_bindings,
    )
    pack_output_owners["sender"] = soundswitch_pack_bundle.frame_sender
    pack_output_owners["midi_input"] = soundswitch_pack_bundle.midi_input
    pack_output_owners["truth_sink"] = soundswitch_pack_bundle.truth_sink
    soundswitch_pack_bundle = _start_soundswitch_pack_workers(
        soundswitch_pack_bundle,
    )
    pack_output_owners["sender"] = soundswitch_pack_bundle.frame_sender
    pack_output_owners["midi_input"] = soundswitch_pack_bundle.midi_input
    pack_output_owners["truth_sink"] = soundswitch_pack_bundle.truth_sink
    laser_bundle = _build_laser_startup_wiring(
        laser_cfg_result,
        backend=soundswitch_pack_bundle.laser_backend,
        dual_with_midi=(soundswitch_pack_bundle.reason == "artnet_truth_check"),
    )
    laser_director = laser_bundle.laser_director
    laser_executor = laser_bundle.laser_executor
    laser_status_provider = laser_bundle.status_provider
    laser_personality_provider = laser_bundle.personality_provider
    midi_output = laser_bundle.midi_output
    soundswitch_frame_sender = soundswitch_pack_bundle.frame_sender
    soundswitch_midi_input = soundswitch_pack_bundle.midi_input
    soundswitch_truth_sink = soundswitch_pack_bundle.truth_sink
    soundswitch_pack_player = soundswitch_pack_bundle.player
    # T7e: one immutable runtime bundle published to StateManager. enabled only when
    # pack output or default-off truth-check workers actually started.
    pack_sha256 = (getattr(soundswitch_pack_bundle.pack, "manifest_sha256", "") or "")
    soundswitch_pack_runtime = PackRuntime(
        enabled=(soundswitch_pack_bundle.reason in ("pack", "artnet_truth_check")),
        reason=soundswitch_pack_bundle.reason,
        player=soundswitch_pack_player,
        midi_input=soundswitch_midi_input,
        backend=soundswitch_pack_bundle.laser_backend,
        frame_sender=soundswitch_frame_sender,
        pack_sha12=pack_sha256[:12],
        pack_sha256=pack_sha256,
        phase_offset_beats=(
            soundswitch_pack_cfg_result.config.phase_offset_beats
            if soundswitch_pack_cfg_result.config is not None else 0.0
        ),
        truth_sink=soundswitch_truth_sink,
        truth_check_reason=soundswitch_pack_bundle.truth_check_reason,
    )
    log.info(
        "[MAIN] soundswitch-pack-config  reason=%s  available=%s  enabled=%s  startup=%s",
        soundswitch_pack_cfg_result.reason,
        soundswitch_pack_cfg_result.available,
        (
            soundswitch_pack_cfg_result.config.enabled
            if soundswitch_pack_cfg_result.config is not None
            else False
        ),
        soundswitch_pack_bundle.reason,
    )
    _loaded_pack = soundswitch_pack_bundle.pack
    if _loaded_pack is not None:
        log.info(
            "[MAIN] soundswitch-pack-loaded  sha=%s  autoloops=%d  bindings=%d  scripted=%d",
            (getattr(_loaded_pack, "manifest_sha256", "") or "")[:12] or "-",
            len(getattr(_loaded_pack, "autoloops", ()) or ()),
            len(getattr(_loaded_pack, "autoloop_bindings", ()) or ()),
            len(getattr(_loaded_pack, "scripted", ()) or ()),
        )
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

    anlz_direct = os.environ.get(ANLZ_DIRECT_ENV) == "1"
    play_direct = os.environ.get(PLAY_DIRECT_ENV) == "1"
    track_load_direct = os.environ.get(TRACK_LOAD_DIRECT_ENV) == "1"
    master_direct = os.environ.get(MASTER_DIRECT_ENV) == "1"
    rb_version_for_direct_master = read_rekordbox_version()
    mixer_authority = _offsets_have_mixer_authority(
        load_offsets_for_version(rb_version_for_direct_master)
        if rb_version_for_direct_master
        else None
    )
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
    # Position cache (RBMemoryReader → PositionCache → StateManager push loop)
    pos_cache = PositionCache()
    live_bpm = LiveBPMService()
    if live_bpm.disabled:
        log.warning("[MAIN] live-bpm-disabled  reason=%s=1  fallback=engine-state-bpm",
                    LIVE_BPM_DISABLE_ENV)
    _start_spectral_cache_eviction_if_enabled()

    # OS2L output
    conn = OS2LConnection()
    conn.start()
    output = OS2LOutput(conn)
    injector: OS2LInjector | None = None
    if os.environ.get("RBSS_OS2L_INJECT") == "1" or os.environ.get(INJECT_PATH_ENV):
        injector = OS2LInjector(conn)
        log.info("[MAIN] os2l-injector enabled  path=%s", injector.path)
    else:
        log.info("[MAIN] os2l-injector disabled  enable=RBSS_OS2L_INJECT=1")

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
        led_color_engine=led_bundle.led_color_engine,
        led_identity_store=led_bundle.led_identity_store,
        led_palette_control_config=palette_control_config,
        os2l_connected_provider=conn.is_connected,
        soundswitch_pack_runtime=soundswitch_pack_runtime,
        mixer_authority_enabled=mixer_authority,
    )
    _sm_holder["sm"] = sm
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

    def _toggle_smart_drop() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.SMART_DROP_TOGGLE,
                deck=0,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=smart-drop-toggle")
            return False

    def _toggle_smart_breakdown() -> bool:
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=Ev.SMART_BREAKDOWN_TOGGLE,
                deck=0,
                source="runtime_command",
                payload={},
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=smart-breakdown-toggle")
            return False

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

    def _led_palette_command(cmd: str, name: str | None = None) -> bool:
        if cmd in ("led_palette_queue", "led_palette_override"):
            raw_name = str(name or "").strip()
            zone = raw_name.upper()
            intent = "queue" if cmd == "led_palette_queue" else "override"
            if zone in ALL_ZONES:
                kind = Ev.LED_ZONE_PAD
                payload = {"name": zone, "intent": intent}
            else:
                kind = Ev.LED_PALETTE_PAD
                payload = {"name": raw_name, "intent": intent}
        elif cmd in ("led_palette_lock", "led_palette_unlock"):
            kind = Ev.LED_PALETTE_LOCK_PAD
            payload = {"intent": "lock" if cmd == "led_palette_lock" else "unlock"}
        elif cmd == "led_rainbow_toggle":
            kind = Ev.LED_RAINBOW_PAD
            payload = {}
        elif cmd == "led_engine":
            kind = Ev.LED_ENGINE_MODE
            payload = {"mode": str(name or "v1")}
        elif cmd == "led_manual_override":
            kind = Ev.LED_MANUAL_PAD
            payload = {"name": str(name or "")}
        elif cmd == "led_manual_clear":
            kind = Ev.LED_MANUAL_PAD
            payload = {"clear": True}
        elif cmd == "led_max_energy_toggle":
            kind = Ev.LED_MAX_ENERGY_PAD
            payload = {}
        else:
            return False
        try:
            event_queue.put_nowait(BridgeEvent(
                kind=kind,
                deck=0,
                payload=payload,
                source="runtime_command",
            ))
            return True
        except queue.Full:
            log.warning("[MAIN] queue-full  event=%s", cmd)
            return False

    def _toggle_record_session(path: Optional[str], dedup: bool) -> bool:
        if not path:
            path = f"/tmp/rbss-session-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        return sm.toggle_session_recording(path, dedup=dedup)

    def _prepare_pack_runtime() -> PackRuntime:
        # Validate-first build of a NEW, UNSTARTED pack runtime (load_pack + verify +
        # construct backend/sender). Raises on failure so the controller keeps the old
        # runtime. No serial opens here — the controller starts the sender on publish.
        cfg_result = load_soundswitch_pack_player_config()
        bundle = _build_soundswitch_pack_startup(
            cfg_result,
            event_sink=_pad_event_sink,
            extra_midi_bindings=palette_control_bindings,
        )
        if bundle.player is None or bundle.laser_backend is None:
            raise RuntimeError("pack_prepare_failed")
        if bundle.frame_sender is None and bundle.truth_sink is None:
            raise RuntimeError("pack_prepare_failed")
        pack_sha256 = (getattr(bundle.pack, "manifest_sha256", "") or "")
        return PackRuntime(
            enabled=False,
            reason=bundle.reason if bundle.truth_sink is not None else "prepared",
            player=bundle.player,
            midi_input=bundle.midi_input, backend=bundle.laser_backend,
            frame_sender=bundle.frame_sender,
            pack_sha12=pack_sha256[:12],
            pack_sha256=pack_sha256,
            phase_offset_beats=(
                cfg_result.config.phase_offset_beats
                if cfg_result.config is not None else 0.0
            ),
            truth_sink=bundle.truth_sink,
            truth_check_reason=bundle.truth_check_reason,
        )

    soundswitch_pack_controller = SoundSwitchPackController(
        publish=sm.set_pack_runtime,
        snapshot=lambda: sm.get_pack_runtime(),
        prepare=_prepare_pack_runtime,
    )

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
        led_palette_callback=_led_palette_command,
        record_session_toggle_callback=_toggle_record_session,
        pack_command_callback=soundswitch_pack_controller.handle,
    )
    sm_led_status_provider = getattr(sm, "led_status_provider", None)
    if not callable(sm_led_status_provider):
        sm_led_status_provider = led_status_provider
    sm_color_status_provider = getattr(sm, "color_engine_status_provider", None)
    if not callable(sm_color_status_provider):
        sm_color_status_provider = None
    status_writer = StatusWriter(
        sm,
        live_bpm,
        pos_cache,
        conn,
        validation_runner,
        command_reader,
        laser_status_provider=laser_status_provider,
        led_status_provider=sm_led_status_provider,
        color_engine_status_provider=sm_color_status_provider,
        pack_status_provider=sm.get_pack_status,
    )

    # Initialize master deck from guarded direct read when available, otherwise deck 1.
    initial_active_deck, initial_active_source = _direct_master_startup_seed(
        rb_version_for_direct_master,
        1,
    )
    initial_show_deck, initial_rb_master_valid = _initial_show_deck_for_startup(
        initial_active_deck,
        initial_active_source,
        mixer_authority=mixer_authority,
    )
    sm.set_initial_state(
        initial_show_deck,
        source=initial_active_source,
        rb_master_valid=initial_rb_master_valid,
    )
    log.info("[MASTER-INIT] version=%s seed_source=%s deck=%d",
             rb_version_for_direct_master or "unknown",
             initial_active_source.replace(" ", "_"),
             initial_show_deck)

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

    if anlz_direct or play_direct or track_load_direct or master_direct or mixer_authority:
        rb_version = rb_version_for_direct_master
        if not rb_version:
            log.warning("[MAIN] rsr-skip  reason=version-lookup-failed")
        else:
            rb_event_queue = queue.Queue(maxsize=1)
            authoritative_kinds = _rb_state_authoritative_kinds(
                anlz_direct=anlz_direct,
                play_direct=play_direct,
                track_load_direct=track_load_direct,
                master_direct=master_direct,
                mixer_authority=mixer_authority,
            )
            rb_state_reader = make_rb_state_reader(
                rb_event_queue,
                rb_version,
                authoritative_queue=event_queue,
                authoritative_kinds=authoritative_kinds,
                drop_unrouted_events=True,
                shadow_logs_enabled=False,
                position_cache=pos_cache,
                anlz_available_callback=_set_anlz_direct_ready if anlz_direct else None,
                transport_available_callback=(
                    _set_play_direct_ready if play_direct or mixer_authority else None
                ),
                track_load_available_callback=(
                    _set_track_load_direct_ready if track_load_direct else None
                ),
                master_available_callback=(
                    _set_master_direct_ready if master_direct or mixer_authority else None
                ),
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
                if mixer_authority:
                    active_flags.append("mixer")
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
    if injector is not None:
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
    if mixer_authority:
        direct_flags.append("mixer")
    log.info(
        "[MAIN] running  state=on  active_deck=%d  seed=%s  rb_version=%s"
        "  rsr=%s  direct=%s  live_bpm=%s  follow=%s"
        "  phrase_arm=%s  smart_rearm=%s  smart_drop=%s  phrase_anchor=%s"
        "  scripted_direct=%s  osc=%d",
        initial_show_deck,
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
    )

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
        # Push direct-DMX zero before any potentially slow watcher/thread joins.
        _cleanup_pack_outputs()
        config_reloader.stop()
        status_writer.stop()
        command_reader.stop()
        command_reader.join(timeout=2.0)   # quiesce the command thread: no more swaps can publish
        _cleanup_pack_outputs()            # authoritative re-zero of the final live runtime (idempotent)
        sm.stop()
        if rb_state_reader is not None:
            rb_state_reader.stop()
        mem_reader.stop()
        live_bpm.stop()
        mtc.stop()
        if injector is not None:
            injector.stop()
        if midi_output is not None:
            midi_output.stop()
        if led_scene_adapter is not None:
            led_scene_adapter.shutdown()
        if led_bundle.realtime_runner is not None:
            led_bundle.realtime_runner.stop()
        discovery.stop()
        conn.stop()
        # Last: keep the event stream alive through the whole teardown so a
        # hang/crash in any join above still produces records (W2 review M-1).
        bridge_log.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    # Block main thread
    sm_thread.join()


if __name__ == "__main__":
    main()
