"""
StateManager — authoritative state + 200 Hz push loop.

Single event-loop thread:
  - drains event_queue at the top of every tick
  - reads PositionCache for current position
  - drives beat emission and OS2L sends
  - handles deck switches, arm/clear, play/stop

All DeckState writes happen in this thread. No external locks on DeckState.

Section map:
  StateManager.__init__
  StateManager.start / stop
  StateManager._run           — main loop
  StateManager._handle_event  — event dispatch
  StateManager._push_tick     — 200 Hz beat/position logic
  arm / unarm helpers
  stop / resume helpers
"""
from __future__ import annotations

import bisect
import logging
import math
import os as _os
import queue
import threading
import time
from collections import deque
from typing import Callable, Optional

from .config import (
    AUTOLOOP_ARM_PHRASE_BEATS, AUTOLOOP_BEATS, ARM_GUARD_S, STOP_DEBOUNCE_S,
    PLAY_SETTLE_MS, TIMING_COMPENSATION_MS,
    BPM_THRESHOLD_SCRIPTED, BPM_THRESHOLD_UNSCRIPTED,
    MEM_STALE_S, SMART_DROP_LOOKAHEAD_BEATS, SMART_DROP_IGNORE_INTRO_BEATS,
    SMART_DROP_IGNORE_OUTRO_BEATS, PHRASE_ANCHOR_BEATS,
    SMART_BREAKDOWN_WINDOW_BEATS, SMART_BREAKDOWN_DEFAULT_DURATION_BEATS,
    SMART_BREAKDOWN_IGNORE_INTRO_BEATS, SMART_BREAKDOWN_IGNORE_OUTRO_BEATS,
)

from .beat_math import (
    _compute_beat_pos,
    _compute_beatgrid_position,
    _beatgrid_elapsed_for_abs_beat,
)
from .smart_phrasing import (
    build_phase2_phrase_segments,
    select_smart_drops,
    select_smart_breakdowns,
    _current_phrase_context,
    find_restore_beat,
)
from .models import (
    ArmSequence, BridgeEvent, DeckState, Ev, OutputState, PositionSnapshot,
    SmartDropEnergyShadow, TrackMetadata,
)
from .laser_models import LaserContext, LaserPersonality
from .osl_output import OS2LOutput
from .rb_memory import PositionCache
from .scripted_tracks import SCRIPTED_TRACKS, lookup as st_lookup
from .logging_manager import get_logging_manager
from .filepath_resolver import has_soundswitch_scripted_id
from .smart_phrasing import (
    SmartPhrasingEngine, SmartPhrasingSnapshot, PhraseSegment,
)
from . import bridge_fmt as bf

log = logging.getLogger("state_manager")
LOG = get_logging_manager()

_LATENCY_WARN_MS = 50.0
_TC_LATENCY_WARN_MS = 250.0
_AUTOLOOP_IDLE_DEBOUNCE_S = max(STOP_DEBOUNCE_S, 2.0)
LIVE_BPM_FOLLOW_ENV = "RBSS_LIVE_BPM_FOLLOW"
AUTOLOOP_MASTER_PHRASE_ARM_ENV = "RBSS_AUTOLOOP_MASTER_PHRASE_ARM"
SMART_DROP_ENV = "RBSS_SMART_DROP"
SMART_BREAKDOWN_ENV = "RBSS_SMART_BREAKDOWN"
PHRASE_ANCHOR_ENV = "RBSS_PHRASE_ANCHOR"
SMART_REARM_EXPERIMENT_ENV = "RBSS_SMART_REARM_EXPERIMENT"
SCRIPTED_SHOWFILE_DIRECT_ENV = "RBSS_SCRIPTED_SHOWFILE_DIRECT"
_LIVE_BPM_FOLLOW_THRESHOLD = BPM_THRESHOLD_UNSCRIPTED
_LIVE_BPM_FOLLOW_SEND_INTERVAL_S = 0.10
_AUTOLOOP_MASTER_PHRASE_START_GRACE_BEATS = 0.5
_AUTOLOOP_PHRASE_LATE_TOLERANCE_MS = 125
_AUTOLOOP_PHRASE_MIN_RUNWAY_MS = 1000
STATE_MANAGER_PROFILE_ENV = "RBSS_SM_PROFILE"
_SNAPSHOT_PUBLISH_INTERVAL_S = 0.05
_PROFILE_SUMMARY_INTERVAL_S = 10.0
_PROFILE_WINDOW = 2048
_SMART_DROP_SIGNAL_NONE = 0
_SMART_DROP_SIGNAL_BLACKOUT_ARMED = 1
_SMART_DROP_SIGNAL_CROSSING = 2


class _RollingDurations:
    """Bounded duration samples in milliseconds."""

    def __init__(self, maxlen: int = _PROFILE_WINDOW) -> None:
        self._values: deque[float] = deque(maxlen=maxlen)

    def add(self, value_ms: float) -> None:
        self._values.append(value_ms)

    def summary(self) -> str:
        if not self._values:
            return "avg=0.000 p95=0.000 p99=0.000 max=0.000"
        values = sorted(self._values)
        count = len(values)
        avg = sum(values) / count
        p95 = values[min(count - 1, int(count * 0.95))]
        p99 = values[min(count - 1, int(count * 0.99))]
        return "avg=%.3f p95=%.3f p99=%.3f max=%.3f" % (
            avg, p95, p99, values[-1],
        )


class _StateManagerProfiler:
    """Optional low-rate aggregate profiler for the 200 Hz StateManager loop."""

    def __init__(self, interval_s: float = _PROFILE_SUMMARY_INTERVAL_S) -> None:
        self._interval_s = interval_s
        self._last_summary_at = time.monotonic()
        self._tick = _RollingDurations()
        self._drain = _RollingDurations()
        self._push = _RollingDurations()
        self._snapshot = _RollingDurations()
        self._overrun_count = 0
        self._worst_overrun_ms = 0.0
        self._max_queue_depth = 0

    def record(
        self,
        *,
        tick_ms: float,
        drain_ms: float,
        push_ms: float,
        snapshot_ms: Optional[float],
        overrun_ms: float,
        queue_depth: int,
    ) -> None:
        self._tick.add(tick_ms)
        self._drain.add(drain_ms)
        self._push.add(push_ms)
        if snapshot_ms is not None:
            self._snapshot.add(snapshot_ms)
        if overrun_ms > 0:
            self._overrun_count += 1
            self._worst_overrun_ms = max(self._worst_overrun_ms, overrun_ms)
        if queue_depth > self._max_queue_depth:
            self._max_queue_depth = queue_depth

    def maybe_log(self, now: float) -> None:
        if now - self._last_summary_at < self._interval_s:
            return
        self._last_summary_at = now
        log.info(
            "[SM][PROFILE] tick_ms(%s) drain_ms(%s) push_ms(%s) "
            "snapshot_ms(%s) overruns=%d worst_overrun_ms=%.3f max_queue_depth=%d",
            self._tick.summary(),
            self._drain.summary(),
            self._push.summary(),
            self._snapshot.summary(),
            self._overrun_count,
            self._worst_overrun_ms,
            self._max_queue_depth,
        )


# ── Beat position helper ──────────────────────────────────────────────────────













class StateManager:
    """Central state machine.

    Create, then call start(). The event loop and push loop share one thread
    so DeckState is never accessed concurrently.
    """

    _TICK_INTERVAL = 1.0 / 200   # 200 Hz

    def __init__(
        self,
        event_queue:    queue.Queue[BridgeEvent],
        position_cache: PositionCache,
        output:         OS2LOutput,
        live_bpm=None,
        live_bpm_follow: Optional[bool] = None,
        laser_director=None,
        laser_executor=None,
        laser_personality_provider: Optional[Callable[[str], Optional[LaserPersonality]]] = None,
        os2l_connected_provider=None,
    ) -> None:
        self._eq    = event_queue
        self._cache = position_cache
        self._out   = output
        self._live_bpm = live_bpm
        # Optional Laser Director — None means disabled/not configured.
        # Mutated only from this thread after start().
        self._laser_director = laser_director
        self._laser_executor = laser_executor
        self._laser_personality_provider = laser_personality_provider
        # Constant-time connectivity check; must not build a dict or call status().
        self._os2l_connected_provider = os2l_connected_provider
        self._live_bpm_follow = (
            _os.environ.get(LIVE_BPM_FOLLOW_ENV, "1") != "0"
            if live_bpm_follow is None else live_bpm_follow
        )
        self._autoloop_master_phrase_arm = (
            _os.environ.get(AUTOLOOP_MASTER_PHRASE_ARM_ENV, "1") != "0"
        )
        self._smart_rearm_experiment = (
            _os.environ.get(SMART_REARM_EXPERIMENT_ENV, "0") == "1"
        )
        self._smart_drop_enabled = (
            self._smart_rearm_experiment
            and _os.environ.get(SMART_DROP_ENV, "1") != "0"
        )
        self._smart_breakdown_enabled = (
            self._smart_rearm_experiment
            and _os.environ.get(SMART_BREAKDOWN_ENV, "1") != "0"
        )
        self._phrase_anchor_enabled = (
            self._smart_rearm_experiment
            and _os.environ.get(PHRASE_ANCHOR_ENV, "1") != "0"
        )
        self._stop  = threading.Event()

        # Per-deck state (written only by this thread after start())
        self._deck: dict[int, DeckState] = {
            1: DeckState(number=1),
            2: DeckState(number=2),
        }
        # Push-loop bookkeeping
        self._os = OutputState()

        # Arm debounce: (track_id, deck) → last arm time
        self._arm_times: dict[tuple, float] = {}

        # FM-3: initialize resolver and pending arm before any events arrive
        self._resolver = None
        self._pending_arm: Optional[ArmSequence] = None

        # Rate-limited position logging (once every 5 s per deck)
        self._last_pos_log: dict[int, float] = {1: 0.0, 2: 0.0}

        # TL TC fallback: (elapsed_ms, wall_time, pitch_factor) per deck
        # Updated by TC_UPDATE events. pitch_factor from ENGINE STATE pitch% field.
        self._tl_tc: dict[int, tuple[int, float, float]] = {1: (0, 0.0, 1.0), 2: (0, 0.0, 1.0)}

        # ANLZ path keyed by bridge deck: populated by ANLZ_PATH event,
        # consumed by _on_track_loaded to skip lsof
        self._pending_anlz_path: dict[int, str] = {}

        # Guards stale lsof results: each TRACK_LOADED increments this per deck
        # FilepathResolver echoes load_gen back in FILEPATH_RESOLVED
        # (already stored in DeckState.load_gen)

        # Tracks which deck most recently received a TRACK_LOADED event.
        # Updated by _on_track_loaded; read by OSC handler to route SCRIPTED_ARM.
        self._last_loaded_deck: int = 0

        # Per deck trace/timing for TRACK_LOADED -> FILEPATH_RESOLVED.
        self._load_trace: dict[int, str] = {}
        self._load_mono: dict[int, float] = {}

        # Published from the StateManager thread; read by status writer threads.
        self._snapshot_lock = threading.Lock()
        self._published_snapshot: dict = {}
        self._publish_snapshot()
        self._snapshot_publish_interval_s = _SNAPSHOT_PUBLISH_INTERVAL_S
        self._next_snapshot_publish_at = time.monotonic() + self._snapshot_publish_interval_s
        self._profiler = (
            _StateManagerProfiler()
            if _os.environ.get(STATE_MANAGER_PROFILE_ENV, "0") != "0"
            else None
        )

        # ── Phase 2 shadow: SmartPhrasingEngine (Issue #33) ──────────────
        # One engine instance, updated each tick inside _build_laser_context.
        # Timing constants cached here to avoid config reads inside _push_tick.
        self._smart_phrasing_engine = SmartPhrasingEngine()
        self._sp_phrase_lookahead: float = 32.0   # project rule: buildup = 32 beats before Smart Drop
        self._sp_drop_window: float = float(SMART_DROP_LOOKAHEAD_BEATS)
        self._sp_post_drop: float = 8.0           # conservative default; not consumed until Phase 3
        self._sp_transition_window: float = float(SMART_DROP_LOOKAHEAD_BEATS)

    def set_initial_state(self, active_deck: int, source: str = "TL ENGINE STATE") -> None:
        """Apply startup state read from TL ENGINE STATE before event loop starts."""
        if active_deck in (1, 2):
            self._os.active_deck = active_deck
            log.info("[SM] init  deck=%d  src=%s", active_deck, source)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._run, name="state-manager", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()

    def get_active_deck(self) -> int:
        return self._os.active_deck

    def get_last_loaded_deck(self) -> int:
        """Deck that most recently received a TRACK_LOADED event (1 or 2; 0 if none yet)."""
        return self._last_loaded_deck

    def get_deck_elapsed_ms(self, deck: int) -> Optional[int]:
        """Best current elapsed estimate for memory-side provisional discovery.

        This is a read-only hint for RBMemoryReader. StateManager remains the
        authority for TL/MTC synthesis; the memory reader only uses this value
        to find paused Deck-2 candidates and still requires movement validation
        before publishing memory snapshots.
        """
        if deck not in (1, 2):
            return None
        d = self._deck[deck]
        tl_ms, tl_at, tl_pitch = self._tl_tc.get(deck, (0, 0.0, 1.0))
        now = time.monotonic()
        if tl_ms > 0 and 0.0 < now - tl_at < 45.0:
            age_ms = (now - tl_at) * 1000.0 * tl_pitch
            return int(tl_ms + (age_ms if d.playing else 0.0))
        if d.elapsed_ms > 0:
            return d.elapsed_ms
        return None

    def get_deck_playing(self, deck: int) -> bool:
        """TL-authoritative play state hint for memory-side discovery scheduling."""
        if deck not in (1, 2):
            return False
        return self._deck[deck].playing

    def snapshot(self) -> dict:
        """Return the latest published state copy.

        DeckState and OutputState stay owned by the StateManager thread. This
        method only returns a copy published by that thread.
        """
        with self._snapshot_lock:
            return {
                **self._published_snapshot,
                "deck": {
                    str(deck): dict(values)
                    for deck, values in self._published_snapshot.get("deck", {}).items()
                },
            }

    # ── Main loop ────────────────────────────────────────────────────────────

    def _run(self) -> None:
        log.info("[SM] starting")
        while not self._stop.is_set():
            t0 = time.monotonic()
            profiler = self._profiler
            if profiler is None:
                self._drain_events()
                self._push_tick()
                self._maybe_publish_snapshot(time.monotonic())
                remaining = self._TICK_INTERVAL - (time.monotonic() - t0)
            else:
                queue_depth = self._queue_depth()
                self._drain_events()
                t1 = time.monotonic()
                self._push_tick()
                t2 = time.monotonic()
                did_publish = self._maybe_publish_snapshot(t2)
                t3 = time.monotonic()
                elapsed_s = t3 - t0
                remaining = self._TICK_INTERVAL - elapsed_s
                profiler.record(
                    tick_ms=elapsed_s * 1000.0,
                    drain_ms=(t1 - t0) * 1000.0,
                    push_ms=(t2 - t1) * 1000.0,
                    snapshot_ms=((t3 - t2) * 1000.0 if did_publish else None),
                    overrun_ms=max(0.0, -remaining * 1000.0),
                    queue_depth=queue_depth,
                )
                profiler.maybe_log(t3)
            if remaining > 0:
                time.sleep(remaining)

    def _queue_depth(self) -> int:
        try:
            return int(self._eq.qsize())
        except Exception:
            return 0

    def _maybe_publish_snapshot(self, now: float) -> bool:
        if now < self._next_snapshot_publish_at:
            return False
        self._publish_snapshot()
        self._next_snapshot_publish_at = now + self._snapshot_publish_interval_s
        return True

    def _publish_snapshot(self) -> None:
        os = self._os
        executor_blackout_pending = False
        if self._laser_executor is not None:
            try:
                executor_blackout_pending = bool(
                    self._laser_executor.status().get("blackout_pending_for_drop_window", False)
                )
            except Exception:
                executor_blackout_pending = False
        deck = {}
        for num, state in self._deck.items():
            deck[str(num)] = {
                "playing": state.playing,
                "filepath": state.meta.filepath,
                "scripted_id": state.scripted_id,
                "elapsed_ms": state.elapsed_ms,
                "bpm": state.meta.bpm,
                "soundswitch_id": state.meta.soundswitch_id,
                "load_gen": state.load_gen,
            }
        snapshot = {
            "active_deck": os.active_deck,
            "lighting_mode": os.lighting_mode,
            "lighting_desired": os.lighting_desired,
            "was_playing": os.was_playing,
            "autoloop_arm_pending": os.autoloop_arm_pending,
            "autoloop_arm_bpm": os.autoloop_arm_bpm,
            "autoloop_arm_deck": os.autoloop_arm_deck,
            "autoloop_arm_sync_beat": os.autoloop_arm_sync_beat,
            "autoloop_arm_target_elapsed_ms": os.autoloop_arm_target_elapsed_ms,
            "autoloop_arm_target_source": os.autoloop_arm_target_source,
            "pending_live_bpm": os.pending_live_bpm,
            "drop_cut_armed": os.drop_cut_armed,
            "smart_drop_transition_window_active": os.drop_cut_armed,
            # Backward-compatible field name, now reflecting executor blackout MIDI state.
            "smart_drop_blackout_active": executor_blackout_pending,
            "scripted_id": 0, # Dead compatibility field — OutputState never had scripted_id; actual per-deck value is in deck[n]["scripted_id"]
            "smart_drop_enabled": self._smart_drop_enabled,
            "smart_breakdown_enabled": self._smart_breakdown_enabled,
            "pending_scripted_arm": (
                None
                if self._pending_arm is None
                else {
                    "deck": self._pending_arm.deck,
                    "track_id": self._pending_arm.track_id,
                    "fire_at": self._pending_arm.fire_at,
                    "phase": "phase2_pending",
                }
            ),
            "deck": deck,
        }
        with self._snapshot_lock:
            self._published_snapshot = snapshot

    def _drain_events(self) -> None:
        """Consume all pending events without blocking."""
        while True:
            try:
                ev = self._eq.get_nowait()
            except queue.Empty:
                break
            try:
                payload = ev.payload or {}
                anomaly = LOG.detect_anomaly(ev)
                with LOG.event_scope(
                    ev.kind,
                    deck=ev.deck,
                    source=ev.source,
                    trace_id=str(payload.get("__trace_id", "")),
                    anomaly=anomaly,
                ):
                    self._handle_event(ev)
                    latency_ms, prev = LOG.finish_event(ev)
                    warn_ms = _TC_LATENCY_WARN_MS if ev.kind == Ev.TC_UPDATE else _LATENCY_WARN_MS
                    if latency_ms > warn_ms:
                        log.warning("[SM] event-late  kind=%s  latency_ms=%d", ev.kind, int(latency_ms))
                    elif log.isEnabledFor(logging.DEBUG):
                        if prev and prev.kind != ev.kind:
                            delta_ms = (time.monotonic() - prev.mono) * 1000.0
                            log.debug("event relation: %s deck%d %.1fms after %s deck%d",
                                      ev.kind, ev.deck, delta_ms, prev.kind, prev.deck)
                        log.debug("event processed %.1fms kind=%s", latency_ms, ev.kind)
            except Exception:
                LOG.log_error(log, "StateManager: error handling %s", ev.kind,
                              payload=getattr(ev, "payload", {}), exc_info=True)

    # ── Event dispatch ────────────────────────────────────────────────────────

    def _handle_event(self, ev: BridgeEvent) -> None:
        payload = {k: v for k, v in ev.payload.items() if not k.startswith("__")}
        log.debug("event received kind=%s src=%s payload=%s", ev.kind, ev.source, payload)
        d = ev.deck

        if ev.kind == Ev.MASTER_CHANGED:
            self._on_master_changed(d, ev.source)

        elif ev.kind == Ev.TRACK_LOADED:
            self._on_track_loaded(d, ev.payload.get("title", ""), ev)

        elif ev.kind == Ev.PLAY:
            if not self._deck[d].playing:
                log.info("[SM] play  deck=%d  src=%s", d, ev.source)
            self._deck[d].playing = True

        elif ev.kind == Ev.PAUSE:
            if self._deck[d].playing:
                log.info("[SM] pause  deck=%d  src=%s", d, ev.source)
            self._deck[d].playing = False
            if d == self._os.active_deck:
                self._os.play_settle_after = 0.0

        elif ev.kind == Ev.FILEPATH_RESOLVED:
            self._on_filepath_resolved(d, ev.payload)

        elif ev.kind == Ev.ANLZ_PATH:
            # Store ANLZ path; consumed by next TRACK_LOADED for this deck
            self._pending_anlz_path[ev.deck] = ev.payload.get('anlz_path', '')

        elif ev.kind == Ev.ANLZ_DATA:
            d_obj = self._deck.get(ev.deck)
            if d_obj is not None:
                gen = ev.payload.get("load_gen", -1)
                if gen == d_obj.load_gen:
                    raw_drops = list(ev.payload.get("drop_beat_indices", []))
                    raw_breakdowns = list(ev.payload.get("breakdown_beat_indices", []))
                    raw_buildups = list(ev.payload.get("buildup_beat_indices", []))
                    total_beats = len(d_obj.meta.beatgrid_times_ms)
                    
                    d_obj.meta.anlz_drops = raw_drops
                    d_obj.meta.smart_drops = select_smart_drops(
                        raw_drops,
                        total_beats=total_beats,
                    )
                    
                    d_obj.meta.anlz_breakdowns = raw_breakdowns
                    d_obj.meta.smart_breakdowns = select_smart_breakdowns(
                        raw_breakdowns,
                        total_beats=total_beats,
                    )
                    
                    d_obj.meta.anlz_buildups = raw_buildups
                    d_obj.meta.anlz_mood = ev.payload.get("mood", 0)
                    
                    selected_set = set(d_obj.meta.smart_drops)
                    shadow = [
                        item for item in ev.payload.get("energy_shadow", [])
                        if isinstance(item, SmartDropEnergyShadow)
                        and item.anlz_beat in selected_set
                    ]
                    d_obj.meta.smart_drop_energy_shadow = shadow
                    log.info("[SM] smart-transition-select  deck=%d  drops=%d  smart_drops=%d  bd=%d  smart_bd=%d  up=%d",
                             ev.deck,
                             len(d_obj.meta.anlz_drops),
                             len(d_obj.meta.smart_drops),
                             len(d_obj.meta.anlz_breakdowns),
                             len(d_obj.meta.smart_breakdowns),
                             len(d_obj.meta.anlz_buildups))
                    for item in shadow:
                        log.info(
                            "[SM] smart-drop-energy-shadow  deck=%d  "
                            "anlz_elapsed=%s  suggested_elapsed=%s  "
                            "lift_anlz=%.2f  lift_suggested=%.2f  confidence=%.2f",
                            ev.deck,
                            bf.elapsed(item.anlz_elapsed_ms),
                            bf.elapsed(item.suggested_elapsed_ms),
                            item.lift_at_anlz,
                            item.lift_at_suggested,
                            item.confidence,
                        )
                else:
                    log.debug("[SM] anlz-drops-stale  deck=%d  gen=%d  current=%d",
                              ev.deck, gen, d_obj.load_gen)

        elif ev.kind == Ev.TC_UPDATE:
            tc_ms = ev.payload.get('elapsed_ms', 0)
            if tc_ms > 0:
                pitch = ev.payload.get('pitch_factor', 1.0)
                self._tl_tc[ev.deck] = (tc_ms, ev.mono, pitch)

        elif ev.kind == Ev.BPM_UPDATE:
            # ENGINE STATE fires every ~15s with live pitch-adjusted BPM
            d = self._deck[ev.deck]
            new_bpm = ev.payload.get('bpm', 0.0)
            if self._live_bpm is not None and new_bpm > 0:
                try:
                    self._live_bpm.update_hint(ev.deck, new_bpm, d.meta.bpm)
                except Exception:
                    log.debug("live BPM hint update failed", exc_info=True)
            if new_bpm > 0 and abs(new_bpm - d.meta.bpm) > 0.5:
                log.debug("bpm_update deck %d: %.1f → %.1f", ev.deck, d.meta.bpm, new_bpm)
                d.meta.bpm = new_bpm

        elif ev.kind == Ev.SCRIPTED_ARM:
            sid = ev.payload.get("scripted_id", 0)
            if sid:
                d_obj = self._deck[d]
                if d_obj.scripted_id != sid:
                    d_obj.scripted_id = sid
                    # If OSC arrived after the deck switch already armed the wrong show,
                    # reset lighting_mode so the machine re-arms with the correct id.
                    if d == self._os.active_deck and self._os.lighting_mode == "scripted":
                        self._os.lighting_mode = ""

        elif ev.kind == Ev.SCRIPTED_CLEAR:
            self._arm_unscripted(d)

        elif ev.kind == Ev.RB_RESTARTED:
            # FM-11: force stop immediately — don't wait for stale detection
            log.info("[SM] rb-restart  pid=%d  action=stop", ev.payload.get("pid", 0))
            self._pending_arm = None
            for d in self._deck.values():
                d.playing = False
                d.scripted_id = 0
            if self._os.was_playing:
                self._do_stop(self._os.active_deck, self._os.last_beat_elapsed_ms)
            self._os.was_playing = False
            self._os.not_playing_since = 0.0
            # Reset lighting state machine so it re-derives on next tick without debounce.
            self._os.lighting_mode    = "idle"
            self._os.lighting_desired = "idle"
            self._os.lighting_stable_since = 0.0
            self._os.autoloop_arm_bpm = 0.0
            self._os.autoloop_arm_deck = 0
            self._os.last_autoloop_status_phrase_beat = 0
            self._clear_smart_rearm_state()
            self._clear_autoloop_arm_phrase_lock()
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_pending_autoloop_master_phrase_arm()
            if self._live_bpm is not None:
                try:
                    self._live_bpm.invalidate()
                except Exception:
                    log.debug("live BPM invalidation failed", exc_info=True)

        elif ev.kind == Ev.SMART_DROP_TOGGLE:
            self.toggle_smart_drop()

        elif ev.kind == Ev.SMART_BREAKDOWN_TOGGLE:
            self.toggle_smart_breakdown()

        elif self._laser_director is not None:
            if ev.kind == Ev.LASER_TOGGLE:
                was_enabled = self._laser_director.is_enabled()
                self._laser_director.toggle_enabled()
                if (
                    was_enabled
                    and not self._laser_director.is_enabled()
                    and self._laser_executor is not None
                ):
                    self._laser_executor.clear_pending_blackout(
                        reason="laser_director_disabled"
                    )
            elif ev.kind == Ev.LASER_SET_ENABLED:
                enabled = bool(ev.payload.get("enabled", False))
                self._laser_director.set_enabled(enabled)
                if not enabled and self._laser_executor is not None:
                    self._laser_executor.clear_pending_blackout(
                        reason="laser_director_disabled"
                    )
            elif ev.kind == Ev.LASER_SCENE:
                scene = str(ev.payload.get("scene", ""))
                ttl_s = float(ev.payload.get("ttl_s", 4.0))
                if scene:
                    self._laser_director.set_manual_override(scene, ttl_s)
            elif ev.kind == Ev.LASER_BLACKOUT:
                self._laser_director.set_emergency_blackout(True)
            elif ev.kind == Ev.LASER_CLEAR_BLACKOUT:
                self._laser_director.clear_emergency_blackout()
            elif ev.kind == Ev.LASER_CLEAR_SCENE_OVERRIDE:
                self._laser_director.clear_manual_override()
            elif ev.kind == Ev.LASER_SET_PERSONALITY:
                personality_name = str(ev.payload.get("personality", ""))
                self._laser_director.set_personality(personality_name)
                provider = self._laser_personality_provider
                if provider is not None:
                    personality_cfg = provider(personality_name)
                    if personality_cfg is not None:
                        self._laser_director.set_personality_config(personality_cfg)
                        if self._laser_executor is not None:
                            self._laser_executor.set_personality(personality_cfg)

    # ── Deck switch ───────────────────────────────────────────────────────────

    def _on_master_changed(self, new_deck: int, source: str) -> None:
        old_deck = self._os.active_deck
        if new_deck == old_deck:
            return
        log.info("[SM] switch  %d→%d  src=%s", old_deck, new_deck, source)
        LOG.stats.record_transition(new_deck, "master")
        # OSC race fix: TL's /bridge/active_deck can arrive after /bridge/track_loaded,
        # so SCRIPTED_ARM may land on the old active deck. If old deck wasn't playing
        # and new deck has no scripted_id, transfer it.
        old_d = self._deck[old_deck]
        new_d = self._deck[new_deck]
        if (
            _os.environ.get("RBSS_SCRIPTED_DIRECT") == "0"
            and old_d.scripted_id > 0
            and new_d.scripted_id == 0
            and not old_d.playing
        ):
            log.debug("[SM] scripted-transfer  %d→%d  id=%d  reason=osc-race",
                      old_deck, new_deck, old_d.scripted_id)
            new_d.scripted_id = old_d.scripted_id
            old_d.scripted_id = 0
        self._os.active_deck = new_deck
        self._os.last_arm_mono = time.monotonic()
        self._os.push_reset_bpm = True
        # Force lighting re-evaluation for the new master on the next tick.
        # Reset both lighting_mode and lighting_desired so the mode transition
        # always fires even when both old and new master have scripted tracks.
        self._os.lighting_mode    = ""
        self._os.lighting_desired = ""
        self._os.lighting_stable_since = 0.0
        # Reset push-loop play state so old deck's was_playing doesn't trigger
        # an immediate stale force-stop on the new active deck.
        self._os.was_playing = False
        self._os.play_settle_after = 0.0
        self._os.not_playing_since = 0.0
        self._os.autoloop_arm_bpm = 0.0
        self._os.autoloop_arm_deck = 0
        self._os.last_autoloop_status_phrase_beat = 0
        self._os.autoloop_arm_after_master_change = True
        self._os.autoloop_master_change_source = source
        self._clear_smart_rearm_state()
        self._clear_autoloop_arm_phrase_lock()
        self._clear_live_bpm_follow()
        self._clear_autoloop_tempo_relock()
        self._clear_pending_autoloop_master_phrase_arm()
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="master_changed")

    # ── Track load → lsof trigger ─────────────────────────────────────────────

    def _on_track_loaded(self, deck: int, title: str, ev: BridgeEvent) -> None:
        d = self._deck[deck]
        d.meta.clear()
        d.scripted_id = 0
        d.load_gen += 1
        if deck == self._os.active_deck:
            self._clear_smart_rearm_state()
            self._clear_autoloop_arm_phrase_lock()
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_pending_autoloop_master_phrase_arm()
            if self._laser_executor is not None:
                self._laser_executor.reset_runtime_state(reason="active_track_loaded")
        d.tl_title = title
        self._last_loaded_deck = deck
        trace_id = str(ev.payload.get("__trace_id", ""))
        if trace_id:
            self._load_trace[deck] = trace_id
        self._load_mono[deck] = time.monotonic()
        log.info("[SM] load  deck=%d  title=%s  gen=%d  src=%s",
                 deck, title or "<unknown>", d.load_gen, ev.source)
        LOG.stats.record_transition(deck, "track_loaded")

        if self._resolver is None:
            return

        # Prefer ANLZ-based resolution (no subprocess, fires before this event)
        anlz_path = self._pending_anlz_path.pop(deck, None)
        if anlz_path:
            log.debug("track load: deck %d using ANLZ path for resolution", deck)
            self._resolver.resolve_by_anlz(deck, d.load_gen, anlz_path, trace_id=trace_id)
            if self._smart_rearm_experiment:
                eq = self._eq
                load_gen = d.load_gen

                def _anlz_worker(path: str, bridge_deck: int, gen: int) -> None:
                    try:
                        from .anlz_reader import read_anlz_drops
                        result = read_anlz_drops(path)
                    except Exception:
                        log.debug("[SM] anlz-worker-error", exc_info=True)
                        return
                    try:
                        eq.put_nowait(BridgeEvent(
                            kind=Ev.ANLZ_DATA,
                            deck=bridge_deck,
                            payload={
                                "drop_beat_indices": result.drop_beat_indices,
                                "breakdown_beat_indices": result.breakdown_beat_indices,
                                "buildup_beat_indices": result.buildup_beat_indices,
                                "mood": result.mood,
                                "energy_shadow": result.energy_shadow,
                                "load_gen": gen,
                            },
                            source="anlz",
                        ))
                    except queue.Full:
                        log.warning("[SM] queue-full  event=anlz-data  deck=%d", bridge_deck)

                threading.Thread(
                    target=_anlz_worker,
                    args=(anlz_path, deck, load_gen),
                    daemon=True,
                    name=f"anlz-drop-{deck}",
                ).start()
        else:
            other = 3 - deck
            other_path = self._deck[other].meta.filepath
            # Fire both: lsof (fast, uses track length) and title-based DB lookup
            # (reliable fallback when memory track_length=0 prevents lsof from matching)
            self._resolver.resolve_async(deck, d.load_gen, other_path, trace_id=trace_id)
            if title:
                self._resolver.resolve_by_title(deck, d.load_gen, title, trace_id=trace_id)

    def attach_resolver(self, resolver) -> None:  # type: ignore[type-arg]
        self._resolver = resolver

    # ── Filepath resolved ─────────────────────────────────────────────────────

    def _on_filepath_resolved(self, deck: int, payload: dict) -> None:
        d = self._deck[deck]
        gen = payload.get("load_gen", -1)
        if gen != d.load_gen:
            log.debug("[SM] resolve-stale  deck=%d  gen=%d  current=%d", deck, gen, d.load_gen)
            return

        meta = d.meta
        meta.filepath       = payload["filepath"]
        meta.bpm            = payload["bpm"]
        meta.content_id     = payload["content_id"]
        meta.first_beat_ms  = payload["first_beat_ms"]
        meta.beatgrid_times_ms = list(payload.get("beatgrid_times_ms", []))
        meta.beatgrid_bpms = list(payload.get("beatgrid_bpms", []))
        meta.beatgrid_source = payload.get("beatgrid_source", "")
        meta.soundswitch_id = payload["soundswitch_id"]
        meta.total_ms       = payload["total_ms"]
        if self._live_bpm is not None and meta.bpm > 0:
            try:
                self._live_bpm.update_hint(deck, meta.bpm, meta.bpm)
            except Exception:
                log.debug("live BPM library hint update failed", exc_info=True)

        load_delta_ms = 0.0
        if deck in self._load_mono:
            load_delta_ms = (time.monotonic() - self._load_mono[deck]) * 1000.0
        log.info("[SM] resolve  deck=%d  file=%s  bpm=%.1f  ssid=%s  latency_ms=%d",
                 deck, bf.short(payload["filepath"]), meta.bpm,
                 meta.soundswitch_id or "none", int(load_delta_ms))
        if _os.environ.get("RBSS_RB_STATE_SHADOW") == "1":  # A6 shadow log
            ssid = meta.soundswitch_id
            if ssid:
                scripted_id = next(
                    (tid for tid, t in SCRIPTED_TRACKS.items() if t.get("ssid") == ssid),
                    None,
                )
                log.info("[SM][SHADOW] scripted-match  deck=%d  id=%s  ssid=%s  latency_ms=%d",
                         deck, scripted_id if scripted_id is not None else "none",
                         ssid, int(load_delta_ms))
            else:
                log.info("[SM][SHADOW] scripted-clear  deck=%d  reason=no-ssid  latency_ms=%d",
                         deck, int(load_delta_ms))
        LOG.stats.record_transition(deck, "filepath_resolved")
        if _os.environ.get("RBSS_SCRIPTED_DIRECT") != "0":
            ssid = meta.soundswitch_id
            filepath = meta.filepath
            scripted_id = None
            matched_by_filepath = False
            ssid_direct = False
            if ssid:
                scripted_id = next(
                    (tid for tid, t in SCRIPTED_TRACKS.items() if t.get("ssid") == ssid),
                    None,
                )
                if (
                    scripted_id is None
                    and _os.environ.get(SCRIPTED_SHOWFILE_DIRECT_ENV, "0") == "1"
                    and has_soundswitch_scripted_id(ssid)
                ):
                    scripted_id = (hash(ssid) & 0x7FFFFFFF) or 1
                    ssid_direct = True
            if scripted_id is None and filepath:
                filepath_matches = [
                    tid for tid, t in SCRIPTED_TRACKS.items()
                    if t.get("filepath") == filepath
                ]
                if len(filepath_matches) == 1:
                    scripted_id = filepath_matches[0]
                    matched_by_filepath = True
                elif len(filepath_matches) > 1:
                    log.info(
                        "[SM] scripted-clear  deck=%d  reason=ambiguous"
                        "  ambiguous_matches=%d  latency_ms=%d",
                        deck, len(filepath_matches), int(load_delta_ms),
                    )
            if scripted_id is not None:
                source = "direct" if ssid_direct else "registry"
                log_fn = log.warning if matched_by_filepath and not ssid else log.info
                log_fn("[SM] scripted-match  deck=%d  scripted_id=%d"
                       "  ssid=%s  source=%s  latency_ms=%d",
                       deck, scripted_id, ssid or "none", source, int(load_delta_ms))
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.SCRIPTED_ARM,
                        deck=deck,
                        payload={"scripted_id": scripted_id},
                        source="filepath_resolved",
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=scripted-arm  deck=%d", deck)
            else:
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.SCRIPTED_CLEAR,
                        deck=deck,
                        source="filepath_resolved",
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=scripted-clear  deck=%d", deck)

    # ── Scripted arm / clear ──────────────────────────────────────────────────

    def _arm_scripted(self, deck: int, track_id: int) -> None:
        # FM-1: non-blocking two-phase arm — no time.sleep() in push loop thread
        track = st_lookup(track_id)
        if not track:
            d = self._deck[deck]
            if _os.environ.get("RBSS_SCRIPTED_DIRECT") != "0" and d.meta.soundswitch_id:
                track = {
                    "filepath":          d.meta.filepath,
                    "bpm":               d.meta.bpm,
                    "first_beat_ms":     d.meta.first_beat_ms,
                    "total_ms":          d.meta.total_ms,
                    "ssid":              d.meta.soundswitch_id,
                    "beatgrid_times_ms": list(d.meta.beatgrid_times_ms),
                    "beatgrid_bpms":     list(d.meta.beatgrid_bpms),
                    "beatgrid_source":   d.meta.beatgrid_source,
                }
            else:
                log.warning("[SM] arm-fail  deck=%d  id=%d  reason=unregistered", deck, track_id)
                return

        # Debounce concurrent arm calls
        key = (track_id, deck)
        now = time.monotonic()
        if now - self._arm_times.get(key, 0.0) < 2.0:
            log.debug("[SM] arm-debounce  deck=%d  id=%d  age=%.1fs",
                      deck, track_id, now - self._arm_times.get(key, 0.0))
            return
        self._arm_times[key] = now
        self._os.last_arm_mono = now

        # Apply track data to DeckState
        d = self._deck[deck]
        d.scripted_id        = track_id
        d.meta.filepath          = track["filepath"]
        d.meta.bpm               = track["bpm"]
        d.meta.first_beat_ms     = track["first_beat_ms"]
        d.meta.beatgrid_times_ms = list(track.get("beatgrid_times_ms") or [])
        d.meta.beatgrid_bpms     = list(track.get("beatgrid_bpms") or [])
        d.meta.beatgrid_source   = track.get("beatgrid_source", "")
        d.meta.total_ms          = float(track.get("total_ms", 0))
        # FM-5: use ssid from registry (populated at startup by resolve_filepaths)
        # never do synchronous disk I/O here
        if not d.meta.soundswitch_id:
            d.meta.soundswitch_id = track.get("ssid", "")

        # Get current elapsed — prefer memory snap, fall back to d.elapsed_ms which
        # the push loop keeps current via TL TC when the DPU is unresolvable (DVS mode).
        snap = self._cache.get(deck)
        if snap and not snap.is_stale():
            elapsed_ms = snap.elapsed_ms
        else:
            elapsed_ms = self._deck[deck].elapsed_ms  # maintained by push loop
        elapsed_ms += TIMING_COMPENSATION_MS

        mirror = 3 - deck

        log.info("[SM] arm-scripted  deck=%d  id=%d  elapsed=%s  bpm=%.1f  file=%s",
                 deck, track_id, bf.elapsed(elapsed_ms), d.meta.bpm,
                 bf.short(track.get("filepath", "")))
        LOG.stats.record_transition(deck, "scripted_arm")

        # Phase 0 (immediate): clear all 4 SS deck slots, stop playback + any autoloop
        for dk in (deck, mirror, 3, 4):
            self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            self._out.send_loop_off(dk)
            self._out.send_deck_play(dk, "off")

        # Phase 1 (scheduled): send_deck_load after SS has processed the clear
        arm_meta = TrackMetadata(
            filepath=d.meta.filepath, soundswitch_id=d.meta.soundswitch_id,
            bpm=d.meta.bpm, first_beat_ms=d.meta.first_beat_ms, total_ms=d.meta.total_ms,
            beatgrid_times_ms=list(d.meta.beatgrid_times_ms),
            beatgrid_bpms=list(d.meta.beatgrid_bpms),
            beatgrid_source=d.meta.beatgrid_source,
        )
        object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)

        self._pending_arm = ArmSequence(
            deck=deck,
            track_id=track_id,
            fire_at=now + 0.10,
            arm_meta=arm_meta,
            elapsed_ms=elapsed_ms,
            mirror=mirror,
            active_deck=self._os.active_deck,
        )

    def _check_pending_arm(self) -> None:
        """FM-1: fire phase 1 of a pending scripted arm (send_deck_load) when timer expires."""
        arm = self._pending_arm
        if arm is None or time.monotonic() < arm.fire_at:
            return
        self._pending_arm = None
        # Refresh elapsed in case position advanced since phase 0
        snap = self._cache.get(arm.deck)
        elapsed_ms = (snap.elapsed_ms if snap and not snap.is_stale() else arm.elapsed_ms) + TIMING_COMPENSATION_MS
        log.info("[SM] arm-phase2  deck=%d  id=%d  elapsed=%s", arm.deck, arm.track_id, bf.elapsed(elapsed_ms))
        arm_meta = arm.arm_meta
        object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)
        # Use current active_deck, not the snapshot — deck may have switched in 100ms
        cur_active = self._os.active_deck
        # Send to all 4 SS deck slots: active + mirror bridge deck + VDJ layers 3/4.
        # Phase 0 clears all 4; if mirror is not reloaded here the push loop sends
        # elapsed to an empty SS deck, which confuses SS's scripted show engine.
        # Matches v1 behaviour: always load both bridge decks at arm time.
        for dk in (arm.deck, arm.mirror, 3, 4):
            self._out.send_deck_load(dk, arm_meta, cur_active, play="on")
        self._log_status()

    def _arm_unscripted(self, deck: int) -> None:
        """TL value=1: clear scripted state. Lighting machine re-evaluates next tick."""
        d = self._deck[deck]
        log.info("[SM] clear-scripted  deck=%d", deck)
        d.scripted_id = 0
        d.meta.soundswitch_id = ""

    # ── Lighting state machine ────────────────────────────────────────────────

    def _update_lighting(
        self,
        deck: int,
        d: "DeckState",
        is_playing: bool,
        elapsed_ms: int,
        bpm: float,
        now: float,
    ) -> None:
        """Derive and apply lighting mode from master deck state. Called every tick.

        Rule:
          scripted track + playing  → SCRIPTED_MODE
          unscripted track + playing → AUTOLOOP_MODE
          not playing               → IDLE (debounced by STOP_DEBOUNCE_S)

        Only fires SS output on mode transitions. Fully state-derived — not
        event-driven, so missed events cannot leave SS in a stale mode.
        """
        os = self._os

        if d.scripted_id and is_playing:
            desired = "scripted"
        elif is_playing:
            desired = "autoloop"
        else:
            desired = "idle"

        # Track when desired last changed so we can debounce idle transitions.
        if desired != os.lighting_desired:
            os.lighting_desired = desired
            os.lighting_stable_since = now

        # Idle transitions are debounced to prevent flicker on transient pauses.
        debounce_s = STOP_DEBOUNCE_S if desired == "idle" else 0.0
        if desired == "idle" and os.lighting_mode == "autoloop":
            debounce_s = _AUTOLOOP_IDLE_DEBOUNCE_S
        if (now - os.lighting_stable_since) < debounce_s:
            return

        if desired == os.lighting_mode:
            # No mode change, but re-arm autoloop if filepath arrived after the initial arm.
            if desired == "autoloop" and d.meta.filepath and d.meta.filepath != os.last_armed_filepath:
                log.info("[SM] rearm-autoloop  deck=%d  file=%s", deck, bf.short(d.meta.filepath))
                self._apply_lighting(deck, "autoloop", elapsed_ms, bpm)
            return

        log.info("[SM] mode  deck=%d  %s→%s  elapsed=%s",
                 deck, os.lighting_mode or "none", desired, bf.elapsed(elapsed_ms))
        os.lighting_mode = desired
        self._apply_lighting(deck, desired, elapsed_ms, bpm)

    def _apply_lighting(self, deck: int, mode: str, elapsed_ms: int, bpm: float) -> None:
        """Send SS commands for a lighting mode transition. No blocking, no sleep.

        Called only by _update_lighting, only on actual mode changes.
        """
        mirror = 3 - deck
        d = self._deck[deck]
        self._os.last_arm_mono = time.monotonic()

        if mode == "scripted":
            self._clear_smart_rearm_state()
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            # Arm the scripted show. _arm_scripted is internally debounced (2 s)
            # so rapid pause/resume doesn't cause a full re-arm sequence.
            self._arm_scripted(deck, d.scripted_id)

        elif mode == "autoloop":
            self._clear_smart_rearm_state()
            self._pending_arm = None
            self._os.push_reset_bpm = True
            arm_bpm, bpm_source = self._autoloop_arm_bpm(deck, d.meta.bpm)
            self._os.autoloop_arm_bpm = arm_bpm
            self._os.autoloop_arm_deck = deck
            self._os.autoloop_arm_pending = True
            self._os.autoloop_arm_sync_beat = 0
            self._os.autoloop_arm_pending_since = time.monotonic()
            self._os.last_autoloop_status_phrase_beat = 0
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_autoloop_tempo_anchor()
            self._clear_pending_autoloop_master_phrase_arm()
            self._os.last_live_follow_bpm = arm_bpm
            self._os.last_live_follow_send_mono = 0.0
            self._os.live_follow_generation += 1
            arm_after_master = self._os.autoloop_arm_after_master_change
            arm_source = self._os.autoloop_master_change_source
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            log.info("[SM] arm-autoloop  deck=%d  elapsed=%s  bpm=%.1f  src=%s  file=%s",
                     deck, bf.elapsed(elapsed_ms), arm_bpm, bpm_source, bf.short(d.meta.filepath))
            log.debug("[SM] arm-autoloop  deck=%d  mirror=%d  loop=%d  meta_bpm=%.2f"
                      "  after_master=%s  master_src=%s  prev=%s",
                      deck, mirror, AUTOLOOP_BEATS, d.meta.bpm,
                      arm_after_master, arm_source or "<none>",
                      bf.short(self._os.last_armed_filepath))
            if arm_after_master and self._autoloop_master_phrase_arm:
                for dk in (deck, mirror, 3, 4):
                    self._out.send_deck_clear(dk)
                    self._out.send_loop_off(dk)
                log.info("[SM] clear-autoloop  deck=%d  src=%s", deck, arm_source or "<none>")
            else:
                for dk in (deck, mirror, 3, 4):
                    self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            if d.meta.filepath:
                self._os.last_armed_filepath = d.meta.filepath
                arm_meta = TrackMetadata(
                    filepath=d.meta.filepath,
                    soundswitch_id="",
                    bpm=arm_bpm,
                    first_beat_ms=d.meta.first_beat_ms,
                    beatgrid_times_ms=list(d.meta.beatgrid_times_ms),
                    beatgrid_bpms=list(d.meta.beatgrid_bpms),
                    beatgrid_source=d.meta.beatgrid_source,
                    total_ms=d.meta.total_ms,
                )
                object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)
                abs_beat = self._autoloop_abs_beat_for_elapsed(elapsed_ms, arm_bpm, arm_meta)
                self._set_autoloop_tempo_anchor(elapsed_ms, abs_beat, arm_bpm)
                if self._should_delay_autoloop_master_arm(arm_after_master, abs_beat):
                    target = self._next_autoloop_arm_phrase(abs_beat)
                    target_elapsed_ms, target_source = self._autoloop_target_elapsed_for_beat(
                        target, elapsed_ms, arm_bpm, arm_meta,
                    )
                    pending_reason = "scheduled"
                    if target_elapsed_ms - elapsed_ms < _AUTOLOOP_PHRASE_MIN_RUNWAY_MS:
                        pending_reason = "short-runway"
                    self._os.autoloop_arm_sync_beat = target
                    self._os.autoloop_arm_target_elapsed_ms = target_elapsed_ms
                    self._os.autoloop_arm_target_source = target_source
                    self._os.pending_autoloop_arm_meta = arm_meta
                    self._os.pending_autoloop_arm_deck = deck
                    self._os.pending_autoloop_arm_mirror = mirror
                    self._os.pending_autoloop_arm_active = deck
                    self._os.pending_autoloop_arm_source = arm_source or "master"
                    self._os.pending_autoloop_arm_reason = pending_reason
                    log.info("[SM] arm-pending  deck=%d  beat=%.1f→%d  until=%dms  file=%s",
                             deck, abs_beat, target,
                             target_elapsed_ms - elapsed_ms, bf.short(d.meta.filepath))
                    log.debug("[SM] arm-pending  deck=%d  target_elapsed=%dms  grid=%s"
                              "  src=%s  reason=%s",
                              deck, target_elapsed_ms, target_source,
                              arm_source or "<none>", pending_reason)
                else:
                    self._send_autoloop_deck_load(deck, mirror, deck, arm_meta)
                    if arm_after_master and self._autoloop_master_phrase_arm:
                        phrase_beat = self._previous_autoloop_arm_phrase(abs_beat)
                        phrase_elapsed_ms, phrase_source = self._autoloop_target_elapsed_for_beat(
                            phrase_beat, elapsed_ms, arm_bpm, arm_meta,
                        )
                        lateness_ms = max(0, elapsed_ms - phrase_elapsed_ms)
                        if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
                            self._schedule_autoloop_master_correction(
                                deck, mirror, deck, arm_meta, arm_bpm, elapsed_ms,
                                phrase_beat, arm_source or "master", "phrase-grace-late",
                            )
                            log.warning("[SS][AUTOLOOP-MASTER-ARM-GRACE-LATE]"
                                        " [SM] arm-grace-late  deck=%d  beat=%d"
                                        "  late=%dms  tolerance=%dms",
                                        deck, phrase_beat, lateness_ms,
                                        _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS)
            else:
                self._os.last_armed_filepath = ""
                for dk in (deck, mirror):
                    self._deck[dk].meta.first_beat_ms = 0.0
                abs_beat = self._autoloop_abs_beat_for_elapsed(elapsed_ms, arm_bpm, d.meta)
                self._set_autoloop_tempo_anchor(elapsed_ms, abs_beat, arm_bpm)
                for dk in (deck, mirror, 3, 4):
                    self._out.send_loop_on(dk)
                    self._out._sub(f"deck {dk} play", "on", verbose=True)
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""

        elif mode == "idle":
            self._clear_smart_rearm_state()
            self._pending_arm = None
            self._os.last_armed_filepath = ""
            self._os.autoloop_arm_bpm = 0.0
            self._os.autoloop_arm_deck = 0
            self._os.last_autoloop_status_phrase_beat = 0
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            self._clear_autoloop_arm_phrase_lock()
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_autoloop_tempo_anchor()
            self._clear_pending_autoloop_master_phrase_arm()
            self._os.live_follow_generation += 1
            for dn in range(1, 5):
                self._out.send_deck_play(dn, "off")
                self._out._sub(f"deck {dn} loop", "off", verbose=True)
            for dn in range(1, 5):
                self._out.send_deck_clear(dn)

    # ── Push loop ─────────────────────────────────────────────────────────────

    def _push_tick(self) -> None:
        # FM-1: check two-phase arm timer before any other push logic
        self._check_pending_arm()

        now = time.monotonic()
        os  = self._os
        active = os.active_deck
        d   = self._deck[active]
        mirror = 3 - active

        # ── Read position from memory ─────────────────────────────────────────
        snap = self._cache.get(active)

        # When memory has no snap for this deck (DPU unresolved — e.g. no track
        # loaded in RB, DVS mode, or DPU2 vtable mismatch), synthesize a snap
        # from TL TC so the push loop can resume/beat/elapsed normally.
        # TL TC fires every ~15 s from ENGINE STATE; 45 s guard limits drift.
        if snap is None:
            tl_ms, tl_at, tl_pitch = self._tl_tc.get(active, (0, 0.0, 1.0))
            if tl_ms > 0 and tl_at > 0 and (now - tl_at) < 45.0:
                age_ms = (now - tl_at) * 1000.0 * tl_pitch
                snap = PositionSnapshot(
                    deck=active,
                    elapsed_ms=int(tl_ms + (age_ms if d.playing else 0.0)),
                    playing=d.playing,
                    track_length_ms=0,
                    updated_at=now,
                )

        # FM-11: if memory is stale (RB gone / unreadable), force stop if playing.
        # If not playing: still run lighting machine + auto-detect so deck switches
        # and arm transitions are not blocked by a temporarily unreadable DPU.
        if snap is None or snap.is_stale(MEM_STALE_S):
            if os.was_playing:
                log.warning("[SM] stop-stale  deck=%d", active)
                self._pending_arm = None
                self._do_stop(active, os.last_beat_elapsed_ms)
                if self._laser_director is not None:
                    _lctx = self._build_laser_context(
                        active, d, os.last_beat_elapsed_ms, d.meta.bpm, 0.0, 0.0, snap, now,
                    )
                    decision = self._laser_director.tick(_lctx, now=now)
                    if self._laser_executor is not None:
                        self._laser_executor.on_decision(decision, _lctx)
                return
            # Not playing — run lighting machine and auto-detect with TL state only.
            bpm = d.meta.bpm
            elapsed_ms = d.elapsed_ms or 0
            confident_playing = d.playing
            self._update_lighting(active, d, confident_playing, elapsed_ms, bpm, now)
            arm_guard = (now - os.last_arm_mono) < ARM_GUARD_S
            if not d.playing and not arm_guard:
                if self._deck[mirror].playing:
                    log.info("[SM] switch  %d→%d  src=auto  reason=idle+mirror-playing",
                             active, mirror)
                    os.last_arm_mono = now
                    try:
                        self._eq.put_nowait(BridgeEvent(
                            kind=Ev.MASTER_CHANGED, deck=mirror, source="auto-detect",
                        ))
                    except queue.Full:
                        log.warning("[SM] queue-full  event=switch  deck=%d→%d  src=auto",
                                    active, mirror)
            if self._laser_director is not None:
                _lctx = self._build_laser_context(
                    active, d, elapsed_ms, bpm, 0.0, 0.0, snap, now,
                )
                decision = self._laser_director.tick(_lctx, now=now)
                if self._laser_executor is not None:
                    self._laser_executor.on_decision(decision, _lctx)
            return

        # Interpolate position: memory updates at 60 Hz; push loop at 200 Hz
        elapsed_since = (now - snap.updated_at) * 1000.0
        raw_elapsed_ms = snap.elapsed_ms + (elapsed_since if snap.playing else 0.0)
        mem_playing = snap.playing

        # TL TC fallback: when memory gives 0 (v2's container/DPU path reaches the wrong
        # inner for deck 2 in DDJ-800 mode — the correct deck-2 inner does write position
        # at +0xC, but it's reachable via outer+0x78, not container+0x480 or DPU scan).
        if snap.elapsed_ms == 0:
            tl_ms, tl_at, tl_pitch = self._tl_tc.get(active, (0, 0.0, 1.0))
            if tl_ms > 0 and tl_at > 0 and (now - tl_at) < 45.0:
                age_ms = (now - tl_at) * 1000.0 * tl_pitch
                raw_elapsed_ms = tl_ms + (age_ms if (mem_playing or d.playing) else 0.0)

        elapsed_ms = int(raw_elapsed_ms) + TIMING_COMPENSATION_MS
        d.elapsed_ms = elapsed_ms

        # ── Rate-limited timecode log (once per 5 s, both decks) ────────────────
        if now - self._last_pos_log[active] >= 5.0:
            self._last_pos_log[active] = now
            _live_a = self._live_bpm_value(active)
            _live_a_s = f"  live_bpm={_live_a:.1f}" if _live_a is not None else ""
            log.info("[SM] pos  deck=%d  %s  bpm=%.1f%s  mode=%s  file=%s",
                     active, bf.elapsed(elapsed_ms), d.meta.bpm, _live_a_s,
                     "scripted" if d.scripted_id else "autoloop",
                     bf.short(d.meta.filepath))

        mirror_snap = self._cache.get(mirror)
        if mirror_snap and now - self._last_pos_log[mirror] >= 5.0:
            self._last_pos_log[mirror] = now
            dm = self._deck[mirror]
            _live_m = self._live_bpm_value(mirror)
            _live_m_s = f"  live_bpm={_live_m:.1f}" if _live_m is not None else ""
            log.info("[SM] pos  deck=%d  %s  bpm=%.1f%s  mode=%s  file=%s",
                     mirror, bf.elapsed(mirror_snap.elapsed_ms), dm.meta.bpm, _live_m_s,
                     "scripted" if dm.scripted_id else "autoloop",
                     bf.short(dm.meta.filepath))

        # ── BPM and beat position ─────────────────────────────────────────────
        bpm = d.meta.bpm
        if os.lighting_mode == "autoloop" and os.autoloop_arm_deck == active and os.autoloop_arm_bpm > 0:
            bpm = os.autoloop_arm_bpm
        if os.push_reset_bpm:
            os.last_sent_bpm = 0.0
            os.push_reset_bpm = False

        # Beat position: computed from ENGINE STATE BPM (pitch-adjusted every ~15s).
        beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms) if bpm > 0 else 0.0
        beat_ms = 60_000.0 / bpm if bpm > 0 else 0.0
        abs_beat_pos = (
            self._autoloop_fallback_abs_beat_for_elapsed(active, elapsed_ms, bpm, d.meta.first_beat_ms)
            if beat_ms > 0 else 0.0
        )
        grid_pos = None
        if os.lighting_mode == "autoloop":
            grid_pos = _compute_beatgrid_position(elapsed_ms, d.meta.beatgrid_times_ms)
            if grid_pos is not None:
                beat_pos, abs_beat_pos = grid_pos
        bpm = self._maybe_apply_live_bpm_follow(active, mirror, bpm, abs_beat_pos, now)
        if bpm > 0 and grid_pos is None:
            beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms)
            beat_ms = 60_000.0 / bpm
            abs_beat_pos = self._autoloop_fallback_abs_beat_for_elapsed(
                active, elapsed_ms, bpm, d.meta.first_beat_ms,
            )

        # ── Stop detection ────────────────────────────────────────────────────
        # TL PAUSE event sets d.playing=False; memory confirms it persists.
        # In v2 (no Frida), TL log is the authoritative play source.
        # is_playing (OR) is kept for other_playing / auto-detect where memory
        # corroboration helps guard against mis-mapped DPU offsets.
        is_playing = mem_playing or d.playing

        # ── Lighting state machine ────────────────────────────────────────────
        # TL is authoritative: d.playing=False (TL said pause) means not playing,
        # even if memory (unreliable on DDJ-800 mode=4112) still shows playing.
        confident_playing = d.playing
        self._update_lighting(active, d, confident_playing, elapsed_ms, bpm, now)
        if os.lighting_mode == "autoloop" and grid_pos is None:
            grid_pos = _compute_beatgrid_position(elapsed_ms, d.meta.beatgrid_times_ms)
            if grid_pos is not None:
                beat_pos, abs_beat_pos = grid_pos

        # Arm guard recomputed here so it reflects any arm fired by _update_lighting.
        arm_guard = (now - os.last_arm_mono) < ARM_GUARD_S

        # Stop detection is TL-authoritative for the same reason: d.playing=False
        # means stopped, memory cannot override a TL pause event.
        if not d.playing and not arm_guard and os.was_playing:
            if os.not_playing_since == 0.0:
                os.not_playing_since = now
            stop_confirmed = (now - os.not_playing_since) >= STOP_DEBOUNCE_S
        else:
            if d.playing:
                os.not_playing_since = 0.0
            stop_confirmed = False

        # Check other deck for auto-switch.
        # Require TL confirmation (d.playing) in addition to memory — guards against
        # wrong DPU offsets causing memory to misreport the other deck as playing.
        other_snap = self._cache.get(mirror)
        other_playing = ((other_snap is not None and not other_snap.is_stale()
                          and other_snap.playing)
                         and self._deck[mirror].playing)

        if stop_confirmed and os.was_playing:
            if other_playing and not arm_guard:
                log.info("[SM] switch  %d→%d  src=auto  reason=stopped+mirror-playing",
                         active, mirror)
                os.not_playing_since = 0.0
                os.last_arm_mono = now
                # FM-2: post to queue so _on_master_changed runs in event-loop thread
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.MASTER_CHANGED,
                        deck=mirror,
                        source="pause auto-switch",
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=switch  deck=%d→%d  src=auto",
                                active, mirror)
            else:
                self._do_stop(active, elapsed_ms)
            return

        # ── Auto-detect: active idle + mirror playing → switch ───────────────
        # Handles the case where TL doesn't send MASTER_CHANGED (e.g. track loaded
        # on deck 2 with nothing on deck 1 — RB may auto-assign master without a
        # deck-change log line).
        if not os.was_playing and not d.playing and not arm_guard:
            if self._deck[mirror].playing:
                log.info("[SM] switch  %d→%d  src=auto  reason=idle+mirror-playing",
                         active, mirror)
                os.last_arm_mono = now
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.MASTER_CHANGED, deck=mirror, source="auto-detect",
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=switch  deck=%d→%d  src=auto",
                                active, mirror)

        # ── Resume detection (was stopped, now playing) ───────────────────────
        # TL authoritative: d.playing=True means TL confirmed playback.
        real_play = d.playing
        if not os.was_playing and real_play:
            if os.play_settle_after == 0.0:
                os.play_settle_after = now + PLAY_SETTLE_MS / 1000.0
                log.debug("[SM] resume-settle  deck=%d  window=%dms", active, PLAY_SETTLE_MS)
            elif now >= os.play_settle_after:
                os.play_settle_after = 0.0
                self._do_resume(active, elapsed_ms, bpm)
            return   # don't emit beats until flash-arm fires

        if not os.was_playing:
            if self._laser_director is not None:
                _lctx = self._build_laser_context(
                    active, d, elapsed_ms, bpm, beat_pos, abs_beat_pos, snap, now,
                )
                decision = self._laser_director.tick(_lctx, now=now)
                if self._laser_executor is not None:
                    self._laser_executor.on_decision(decision, _lctx)
            return

        # ── Emit elapsed + beat ───────────────────────────────────────────────
        if os.lighting_mode == "autoloop" and os.autoloop_arm_pending:
            self._maybe_lock_autoloop_arm(active, mirror, bpm, abs_beat_pos, elapsed_ms)

        # BPM: send immediately when last_sent_bpm is 0 (fresh arm / deck switch) so
        # SS autoloop activates on the current tick, not at the next beat boundary.
        # VDJ sends BPM to all 4 decks; SS may use deck 3/4 internally.
        if bpm > 0 and os.last_sent_bpm == 0.0:
            for dk in (active, mirror, 3, 4):
                self._out.send_bpm(dk, bpm)
            os.last_sent_bpm = bpm
        elif bpm > 0 and os.last_sent_bpm > 0:
            threshold = (BPM_THRESHOLD_SCRIPTED if d.scripted_id
                         else BPM_THRESHOLD_UNSCRIPTED)
            if abs(bpm - os.last_sent_bpm) > threshold:
                for dk in (active, mirror, 3, 4):
                    self._out.send_bpm(dk, bpm)
                os.last_sent_bpm = bpm

        # Beat boundary detection: fire a beat event when elapsed crosses the next beat
        beatpos_out = abs_beat_pos if os.lighting_mode == "autoloop" else beat_pos
        autoloop_tick_just_fired = False
        smart_drop_signal = _SMART_DROP_SIGNAL_NONE
        smart_drop_blackout_mode = bool(
            self._laser_executor is not None
            and self._laser_executor.smart_drop_blackout_enabled()
        )
        if bpm > 0:
            this_beat = int(abs_beat_pos)
            if os.lighting_mode == "autoloop" and grid_pos is not None:
                last_grid_pos = _compute_beatgrid_position(
                    os.last_beat_elapsed_ms, d.meta.beatgrid_times_ms,
                )
                last_beat = int(last_grid_pos[1]) if last_grid_pos is not None else this_beat
            elif os.lighting_mode == "autoloop":
                last_abs_beat = self._autoloop_fallback_abs_beat_for_elapsed(
                    active, os.last_beat_elapsed_ms, bpm, d.meta.first_beat_ms,
                )
                last_beat = int(last_abs_beat)
            else:
                last_beat = int((os.last_beat_elapsed_ms - d.meta.first_beat_ms) / beat_ms) if beat_ms > 0 else 0

            if this_beat > last_beat:
                beat_index = this_beat % 4
                if os.pending_autoloop_arm_meta is not None:
                    self._maybe_lock_autoloop_arm(active, mirror, bpm, abs_beat_pos, elapsed_ms)
                if os.lighting_mode == "autoloop":
                    beat_out = this_beat
                    pending_live_bpm = os.pending_live_bpm
                    if pending_live_bpm > 0:
                        for dk in (active, mirror, 3, 4):
                            self._out.send_bpm(dk, pending_live_bpm)
                        bpm = pending_live_bpm
                        os.autoloop_arm_bpm = pending_live_bpm
                        self._set_autoloop_tempo_anchor(elapsed_ms, abs_beat_pos, pending_live_bpm)
                        os.last_live_follow_bpm = pending_live_bpm
                        os.last_live_follow_send_mono = now
                        os.last_sent_bpm = pending_live_bpm
                        os.pending_live_bpm = 0.0
                        change = True
                        log.info("[SM] bpm-apply  deck=%d  bpm=%.2f  beat=%d",
                                 active, pending_live_bpm, this_beat)
                    else:
                        change = os.autoloop_change_on_next_beat
                    os.autoloop_change_on_next_beat = False
                else:
                    beat_out = beat_index
                    change = (beat_index == 0)
                # smart-drop / phrase-anchor BEFORE send_beat so deck-load goes
                # out before the activation beat event reaches SoundSwitch.
                if os.lighting_mode == "autoloop":
                    if self._smart_drop_enabled and d.meta.smart_drops:
                        smart_drop_signal = _smart_drop_tick(
                            self,
                            active,
                            mirror,
                            bpm,
                            this_beat,
                            elapsed_ms,
                            blackout_mode=smart_drop_blackout_mode,
                        )
                        if smart_drop_signal == _SMART_DROP_SIGNAL_CROSSING:
                            change = True
                            if not smart_drop_blackout_mode:
                                autoloop_tick_just_fired = True
                    if self._smart_breakdown_enabled and d.meta.smart_breakdowns:
                        if _smart_breakdown_tick(self, active, mirror, bpm, this_beat, elapsed_ms):
                            change = True
                            autoloop_tick_just_fired = True
                    if self._phrase_anchor_enabled:
                        if _phrase_anchor_tick(
                            self, active, mirror, bpm, this_beat, elapsed_ms, abs_beat_pos
                        ):
                            change = True
                            autoloop_tick_just_fired = True

                os.last_beat_elapsed_ms = elapsed_ms
                for dk in (active, mirror, 3, 4):
                    self._out.send_beat(dk, bpm, beat_out, change=change)
                was_arm_pending = os.autoloop_arm_pending
                self._maybe_lock_autoloop_arm(active, mirror, bpm, abs_beat_pos, elapsed_ms)
                if was_arm_pending and not os.autoloop_arm_pending:
                    autoloop_tick_just_fired = True
                if os.lighting_mode == "autoloop":
                    phrase_beat = (this_beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS
                    if (
                        phrase_beat > 0
                        and phrase_beat > last_beat
                        and phrase_beat != os.last_autoloop_status_phrase_beat
                    ):
                        os.last_autoloop_status_phrase_beat = phrase_beat
                        grid_status = d.meta.beatgrid_source if grid_pos is not None else "fallback"
                        self._log_autoloop_tick(
                            active, elapsed_ms, beatpos_out, bpm, d.meta.bpm, grid_status
                        )
                        autoloop_tick_just_fired = True

        # Laser Director tick — dry-run only in Phase 1.
        # Must not block, send MIDI, call OS2LOutput, or mutate DeckState/OutputState.
        drop_crossing_decision_emitted = False
        smart_drop_blackout_arm = bool(
            (
                smart_drop_signal == _SMART_DROP_SIGNAL_BLACKOUT_ARMED
                or (
                    self._os.drop_cut_armed
                    and smart_drop_signal != _SMART_DROP_SIGNAL_CROSSING
                )
            )
            and smart_drop_blackout_mode
        )
        if self._laser_director is not None:
            ctx = self._build_laser_context(
                active,
                d,
                elapsed_ms,
                bpm,
                beat_pos,
                abs_beat_pos,
                snap,
                now,
                autoloop_tick_just_fired=autoloop_tick_just_fired,
                smart_drop_blackout_arm=smart_drop_blackout_arm,
            )
            laser_director_enabled = self._laser_director.is_enabled()
            if (
                smart_drop_blackout_arm
                and not laser_director_enabled
                and self._laser_executor is not None
            ):
                self._laser_executor.clear_pending_blackout(
                    reason="laser_director_disabled"
                )
            decision = self._laser_director.tick(ctx, now=now)
            drop_crossing_decision_emitted = bool(
                decision is not None and decision.reason == "drop_crossing"
            )
            if self._laser_executor is not None:
                self._laser_executor.on_decision(decision, ctx)
        if smart_drop_signal == _SMART_DROP_SIGNAL_CROSSING and smart_drop_blackout_mode:
            # Ordering requirement: in blackout mode keep os.drop_cut_armed true
            # through phrase-anchor processing so _phrase_anchor_tick suppresses
            # same-beat phrase-anchor rearm. Do crossing cleanup only here,
            # after phrase-anchor processing has already run for this tick.
            if (
                self._laser_executor is not None
                and not drop_crossing_decision_emitted
            ):
                self._laser_executor.clear_pending_blackout(
                    reason="smart_drop_crossing_without_drop_decision"
                )
            os.phrase_anchor_last_beat = max(os.phrase_anchor_last_beat, os.drop_rearm_beat)
            os.drop_cut_armed = False
            os.drop_rearm_beat = 0

        # Elapsed + beatpos — send at every push tick (SS needs continuous updates).
        # Test A: in autoloop only, send absolute beat position to match VDJ-like
        # OS2L timing while leaving beat events unchanged for isolation.
        for dk in (active, mirror, 3, 4):
            self._out.send_elapsed(dk, elapsed_ms, beatpos_out)

    def _build_laser_context(
        self,
        active: int,
        d,
        elapsed_ms: int,
        bpm: float,
        beat_pos: float,
        abs_beat_pos: float,
        snap,
        now: float,
        autoloop_tick_just_fired: bool = False,
        smart_drop_blackout_arm: bool = False,
    ):
        """Build a frozen LaserContext from already-computed push-tick locals.

        Must not call conn.status(), read files, build dicts, scan MIDI ports,
        or perform any I/O. All values come from pre-computed local variables.
        """
        os2l_connected = (
            self._os2l_connected_provider()
            if self._os2l_connected_provider is not None
            else False
        )
        active_track_loaded = bool(d.meta.filepath)
        autoloop_ready = (
            self._os.lighting_mode == "autoloop"
            and not self._os.autoloop_arm_pending
            and self._os.pending_autoloop_arm_meta is None
            and bool(self._os.last_armed_filepath)
            and self._os.last_armed_filepath == d.meta.filepath
        )
        current_phrase_is_up, current_phrase_is_chorus = _current_phrase_context(
            abs_beat=abs_beat_pos,
            up_markers=d.meta.anlz_buildups,
            chorus_markers=d.meta.anlz_drops,
            low_markers=d.meta.anlz_breakdowns,
        )

        # ── Phase 2 shadow: SmartPhrasingEngine update (Issue #33) ────────
        # Build snapshot from already-loaded DeckState.meta.  No I/O, no
        # config reads, no file parsing.  Result is passive data only.
        _sp_snapshot = SmartPhrasingSnapshot(
            deck_id=str(active),
            track_id=d.meta.content_id or None,
            is_playing=d.playing,
            abs_beat=abs_beat_pos if bpm > 0 else None,
            phrase_segments=build_phase2_phrase_segments(
                anlz_buildups=d.meta.anlz_buildups,
                anlz_drops=d.meta.anlz_drops,
                anlz_breakdowns=d.meta.anlz_breakdowns,
                smart_drops=d.meta.smart_drops,
                total_beats=len(d.meta.beatgrid_times_ms),
            ),
            smart_drop_beats=tuple(float(x) for x in d.meta.smart_drops),
            # Phase 2 shadow: breakdown_segments left empty because ANLZ
            # breakdown data is start-marker-only with no reliable end-beat.
            breakdown_segments=(),
            phrase_lookahead_beats=self._sp_phrase_lookahead,
            drop_window_beats=self._sp_drop_window,
            post_drop_beats=self._sp_post_drop,
            transition_window_beats=self._sp_transition_window,
        )
        _sp_result = self._smart_phrasing_engine.update(_sp_snapshot)

        return LaserContext(
            active_deck=active,
            playing=d.playing,
            elapsed_ms=elapsed_ms,
            bpm=bpm,
            beatpos=beat_pos,
            abs_beat=abs_beat_pos,
            position_stale=(snap is None or snap.is_stale(MEM_STALE_S)),
            lighting_mode=self._os.lighting_mode,
            os2l_connected=os2l_connected,
            active_track_loaded=active_track_loaded,
            autoloop_ready=autoloop_ready,
            autoloop_tick_just_fired=autoloop_tick_just_fired,
            breakdown_active=self._os.breakdown_active,
            smart_drops=tuple(d.meta.smart_drops),
            anlz_buildups=tuple(d.meta.anlz_buildups),
            current_phrase_is_up=current_phrase_is_up,
            current_phrase_is_chorus=current_phrase_is_chorus,
            scripted_id=d.scripted_id,
            smart_drop_blackout_active=self._os.drop_cut_armed,
            smart_drop_blackout_arm=smart_drop_blackout_arm,
            smart_phrasing=_sp_result.state,
        )

    # ── Stop / resume helpers ─────────────────────────────────────────────────

    def _do_stop(self, deck: int, elapsed_ms: int) -> None:
        log.info("[SM] stop  deck=%d  elapsed=%s", deck, bf.elapsed(elapsed_ms))
        os = self._os
        self._deck[deck].playing  = False
        os.was_playing            = False
        os.last_beat_elapsed_ms   = elapsed_ms
        os.stop_elapsed_ms        = elapsed_ms
        os.not_playing_since      = 0.0
        os.last_sent_bpm          = 0.0
        os.autoloop_arm_bpm       = 0.0
        os.autoloop_arm_deck      = 0
        os.last_autoloop_status_phrase_beat = 0
        self._clear_smart_rearm_state()
        self._clear_autoloop_arm_phrase_lock()
        self._clear_live_bpm_follow()
        self._clear_autoloop_tempo_relock()
        self._clear_autoloop_tempo_anchor()
        os.live_follow_generation += 1
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="stop")

    def _do_resume(self, deck: int, elapsed_ms: int, bpm: float) -> None:
        mirror = 3 - deck
        d = self._deck[deck]
        m = self._deck[mirror]
        log.info("[SM] resume  deck=%d  elapsed=%s  bpm=%.1f  file=%s",
                 deck, bf.elapsed(elapsed_ms), bpm, bf.short(d.meta.filepath))

        # Deck mismatch correction: if active deck is empty but other has track, swap
        if not d.meta.filepath and m.meta.filepath:
            log.info("[SM] switch  %d→%d  src=auto  reason=empty-deck", deck, mirror)
            self._os.active_deck = mirror
            deck, mirror = mirror, deck
            d, m = m, d

        self._os.was_playing          = True
        self._os.last_sent_bpm        = 0.0
        self._os.last_beat_elapsed_ms = elapsed_ms
        self._os.last_autoloop_status_phrase_beat = 0
        self._log_status()

    def _log_autoloop_tick(
        self,
        active: int,
        elapsed_ms: int,
        beatpos_out: float,
        timing_bpm: float,
        meta_bpm: float,
        grid_status: str,
    ) -> None:
        os = self._os
        live_status = self._live_bpm_status_text(active)
        log.info("[SS][AUTOLOOP-TICK] [SM] autoloop-tick  deck=%d  elapsed=%s  beat=%.2f"
                  "  bpm=%.2f  arm_bpm=%.2f  meta_bpm=%.2f  grid=%s  %s  %s  file=%s",
                  active, bf.elapsed(elapsed_ms), beatpos_out,
                  timing_bpm, os.autoloop_arm_bpm, meta_bpm, grid_status, live_status,
                  self._live_bpm_follow_status_text(),
                  bf.short(os.last_armed_filepath))

    def _should_delay_autoloop_master_arm(self, arm_after_master: bool, abs_beat_pos: float) -> bool:
        if not self._autoloop_master_phrase_arm or not arm_after_master:
            return False
        return not self._is_near_autoloop_phrase_start(abs_beat_pos)

    def _is_near_autoloop_phrase_start(self, abs_beat_pos: float) -> bool:
        phrase_offset = math.fmod(max(abs_beat_pos, 0.0), AUTOLOOP_ARM_PHRASE_BEATS)
        if phrase_offset < 0:
            phrase_offset += AUTOLOOP_ARM_PHRASE_BEATS
        return phrase_offset <= _AUTOLOOP_MASTER_PHRASE_START_GRACE_BEATS

    def _autoloop_abs_beat_for_elapsed(
        self,
        elapsed_ms: int,
        bpm: float,
        meta: TrackMetadata,
    ) -> float:
        grid_pos = _compute_beatgrid_position(elapsed_ms, meta.beatgrid_times_ms)
        if grid_pos is not None:
            return grid_pos[1]
        if bpm <= 0:
            return 0.0
        beat_ms = 60_000.0 / bpm
        return (elapsed_ms - meta.first_beat_ms) / beat_ms

    def _autoloop_target_elapsed_for_beat(
        self,
        target_beat: int,
        current_elapsed_ms: int,
        bpm: float,
        meta: TrackMetadata,
    ) -> tuple[int, str]:
        grid_target = _beatgrid_elapsed_for_abs_beat(target_beat, meta.beatgrid_times_ms)
        if grid_target is not None:
            return grid_target
        if bpm <= 0:
            return current_elapsed_ms, "fallback"
        beat_ms = 60_000.0 / bpm
        os = self._os
        if os.autoloop_anchor_bpm > 0:
            elapsed_ms = os.autoloop_anchor_elapsed_ms + (
                (target_beat - os.autoloop_anchor_abs_beat) * beat_ms
            )
        else:
            elapsed_ms = meta.first_beat_ms + (target_beat * beat_ms)
        return int(round(elapsed_ms)), "fallback"

    def _autoloop_fallback_abs_beat_for_elapsed(
        self,
        deck: int,
        elapsed_ms: int,
        bpm: float,
        first_beat_ms: float,
    ) -> float:
        os = self._os
        if (
            os.lighting_mode == "autoloop"
            and os.autoloop_arm_deck == deck
            and os.autoloop_anchor_bpm > 0
            and bpm > 0
        ):
            beat_ms = 60_000.0 / bpm
            return os.autoloop_anchor_abs_beat + (
                (elapsed_ms - os.autoloop_anchor_elapsed_ms) / beat_ms
            )
        if bpm <= 0:
            return 0.0
        beat_ms = 60_000.0 / bpm
        return (elapsed_ms - first_beat_ms) / beat_ms

    def _set_autoloop_tempo_anchor(self, elapsed_ms: int, abs_beat: float, bpm: float) -> None:
        os = self._os
        os.autoloop_anchor_elapsed_ms = elapsed_ms
        os.autoloop_anchor_abs_beat = abs_beat
        os.autoloop_anchor_bpm = bpm

    def _clear_autoloop_tempo_anchor(self) -> None:
        os = self._os
        os.autoloop_anchor_elapsed_ms = 0
        os.autoloop_anchor_abs_beat = 0.0
        os.autoloop_anchor_bpm = 0.0

    def _send_autoloop_deck_load(
        self,
        deck: int,
        mirror: int,
        active: int,
        arm_meta: TrackMetadata,
    ) -> None:
        # VDJ: active deck + mirror 1/2 + decks 3 and 4 all get the same track.
        for dk in (deck, mirror, 3, 4):
            self._out.send_deck_load(dk, arm_meta, active, play="on")

    def _schedule_autoloop_master_correction(
        self,
        deck: int,
        mirror: int,
        active: int,
        arm_meta: TrackMetadata,
        bpm: float,
        current_elapsed_ms: int,
        from_target_beat: int,
        source: str,
        reason: str,
    ) -> None:
        correction_meta = TrackMetadata(
            filepath=arm_meta.filepath,
            soundswitch_id=arm_meta.soundswitch_id,
            bpm=arm_meta.bpm,
            first_beat_ms=arm_meta.first_beat_ms,
            beatgrid_times_ms=list(arm_meta.beatgrid_times_ms),
            beatgrid_bpms=list(arm_meta.beatgrid_bpms),
            beatgrid_source=arm_meta.beatgrid_source,
            total_ms=arm_meta.total_ms,
            content_id=arm_meta.content_id,
        )
        target = int(from_target_beat) + AUTOLOOP_ARM_PHRASE_BEATS
        target_elapsed_ms, target_source = self._autoloop_target_elapsed_for_beat(
            target, current_elapsed_ms, bpm, correction_meta,
        )
        while target_elapsed_ms - current_elapsed_ms < _AUTOLOOP_PHRASE_MIN_RUNWAY_MS:
            target += AUTOLOOP_ARM_PHRASE_BEATS
            target_elapsed_ms, target_source = self._autoloop_target_elapsed_for_beat(
                target, current_elapsed_ms, bpm, correction_meta,
            )

        os = self._os
        os.autoloop_arm_pending = True
        os.autoloop_arm_pending_since = time.monotonic()
        os.autoloop_arm_sync_beat = target
        os.autoloop_arm_target_elapsed_ms = target_elapsed_ms
        os.autoloop_arm_target_source = target_source
        os.pending_autoloop_arm_meta = correction_meta
        os.pending_autoloop_arm_deck = deck
        os.pending_autoloop_arm_mirror = mirror
        os.pending_autoloop_arm_active = active
        os.pending_autoloop_arm_source = source
        os.pending_autoloop_arm_reason = f"correction-{reason}"
        log.info("[SM] arm-correction-pending  deck=%d  beat=%d  until=%dms"
                 "  reason=%s  grid=%s  src=%s  file=%s",
                 deck, target, target_elapsed_ms - current_elapsed_ms,
                 reason, target_source, source or "<none>",
                 bf.short(correction_meta.filepath))

    def _maybe_apply_live_bpm_follow(
        self,
        deck: int,
        mirror: int,
        timing_bpm: float,
        abs_beat_pos: float,
        now: float,
    ) -> float:
        os = self._os
        if not self._live_bpm_follow or os.lighting_mode != "autoloop":
            return timing_bpm
        if os.autoloop_arm_deck != deck or os.autoloop_arm_bpm <= 0:
            self._clear_live_bpm_follow()
            return timing_bpm
        if not os.was_playing:
            return timing_bpm
        if not self._deck[deck].playing:
            self._clear_live_bpm_follow()
            return timing_bpm

        live_bpm = self._live_bpm_value(deck)
        if live_bpm is None:
            return timing_bpm

        if abs(live_bpm - timing_bpm) <= _LIVE_BPM_FOLLOW_THRESHOLD:
            self._clear_live_bpm_follow()
            return timing_bpm

        if now - os.last_live_follow_send_mono < _LIVE_BPM_FOLLOW_SEND_INTERVAL_S:
            return timing_bpm

        os.pending_live_bpm = live_bpm
        return timing_bpm

    def _live_bpm_value(self, deck: int) -> Optional[float]:
        if self._live_bpm is None:
            return None
        try:
            live = self._live_bpm.get_bpm(deck)
        except Exception:
            log.debug("live BPM read failed", exc_info=True)
            return None
        if live is None or not math.isfinite(live) or live <= 0:
            return None
        return float(live)

    def _next_autoloop_arm_phrase(self, abs_beat_pos: float) -> int:
        """Calculate next phrase boundary for autoloop arm synchronization."""
        beat = max(1, int(abs_beat_pos) + 1)
        while beat % AUTOLOOP_ARM_PHRASE_BEATS != 0:
            beat += 1
        return beat

    def _previous_autoloop_arm_phrase(self, abs_beat_pos: float) -> int:
        beat = max(0, int(math.floor(abs_beat_pos)))
        return (beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS

    def _maybe_lock_autoloop_arm(
        self,
        active: int,
        mirror: int,
        bpm: float,
        abs_beat_pos: float,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        os = self._os
        if (
            os.lighting_mode != "autoloop"
            or os.autoloop_arm_deck != active
            or not os.autoloop_arm_pending
            or bpm <= 0
        ):
            return

        if os.autoloop_arm_sync_beat == 0:
            os.autoloop_arm_sync_beat = self._next_autoloop_arm_phrase(abs_beat_pos)
        if elapsed_ms is None:
            deck_elapsed = self._deck[active].elapsed_ms
            if deck_elapsed > 0:
                elapsed_ms = deck_elapsed
            elif bpm > 0:
                beat_ms = 60_000.0 / bpm
                elapsed_ms = int(round(self._deck[active].meta.first_beat_ms + (abs_beat_pos * beat_ms)))
            else:
                elapsed_ms = 0
        if os.autoloop_arm_target_elapsed_ms == 0:
            os.autoloop_arm_target_elapsed_ms, os.autoloop_arm_target_source = (
                self._autoloop_target_elapsed_for_beat(
                    os.autoloop_arm_sync_beat,
                    elapsed_ms,
                    bpm,
                    self._deck[active].meta,
                )
            )
            log.info("[SM] arm-pending  deck=%d  beat=%.1f→%d  until=%dms  grid=%s",
                     active, abs_beat_pos, os.autoloop_arm_sync_beat,
                     os.autoloop_arm_target_elapsed_ms - elapsed_ms,
                     os.autoloop_arm_target_source or "fallback")

        if elapsed_ms < os.autoloop_arm_target_elapsed_ms:
            return

        current_beat = int(abs_beat_pos)
        target_beat = os.autoloop_arm_sync_beat
        target_elapsed_ms = os.autoloop_arm_target_elapsed_ms
        target_source = os.autoloop_arm_target_source or "fallback"
        lateness_ms = max(0, elapsed_ms - target_elapsed_ms)
        arm_bpm = os.autoloop_arm_bpm if os.autoloop_arm_bpm > 0 else bpm
        pending_meta = os.pending_autoloop_arm_meta
        scheduled_correction = False
        if pending_meta is not None:
            pending_source = os.pending_autoloop_arm_source or "<none>"
            pending_reason = os.pending_autoloop_arm_reason or "scheduled"
            needs_correction = (
                pending_reason == "short-runway"
                or lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS
            )
            arm_elapsed_ms = elapsed_ms if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS else target_elapsed_ms
            object.__setattr__(pending_meta, "elapsed_ms", arm_elapsed_ms)
            if pending_reason.startswith("correction-"):
                for dk in (active, mirror, 3, 4):
                    self._out.send_deck_clear(dk)
                    self._out.send_loop_off(dk)
                log.info("[SM] arm-correction-clear  deck=%d  beat=%d  reason=%s",
                         active, target_beat, pending_reason)
            self._send_autoloop_deck_load(
                os.pending_autoloop_arm_deck or active,
                os.pending_autoloop_arm_mirror or mirror,
                os.pending_autoloop_arm_active or active,
                pending_meta,
            )
            os.autoloop_change_on_next_beat = False
            log.info("[SM] arm-locked  deck=%d  beat=%d  late=%dms"
                     "  bpm=%.2f  reason=%s  correction=%s  src=%s",
                     active, target_beat, lateness_ms,
                     arm_bpm, pending_reason, needs_correction, pending_source)
            self._clear_pending_autoloop_master_phrase_arm()
            if needs_correction:
                reason = "late" if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS else "short-runway"
                self._schedule_autoloop_master_correction(
                    active, mirror, active, pending_meta, arm_bpm, elapsed_ms,
                    target_beat, pending_source, reason,
                )
                scheduled_correction = True
                if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
                    log.warning("[SS][AUTOLOOP-MASTER-ARM-LATE-CORRECTION]"
                                " [SM] arm-late  deck=%d  beat=%d  late=%dms"
                                "  tolerance=%dms  grid=%s",
                                active, target_beat, lateness_ms,
                                _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS, target_source)
        elif lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
            log.warning("[SS][AUTOLOOP-PHRASE-MISS]"
                        " [SM] arm-phrase-miss  deck=%d  beat=%d  late=%dms"
                        "  tolerance=%dms  grid=%s",
                        active, target_beat, lateness_ms,
                        _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS, target_source)
        for dk in (active, mirror, 3, 4):
            self._out.send_bpm(dk, arm_bpm)
        os.last_sent_bpm = arm_bpm
        if not scheduled_correction:
            os.autoloop_arm_pending = False
            os.autoloop_arm_sync_beat = 0
            os.autoloop_arm_target_elapsed_ms = 0
            os.autoloop_arm_target_source = ""
            os.autoloop_arm_pending_since = 0.0
        log.info("[SM] arm-locked-final  deck=%d  beat=%d  late=%dms  bpm=%.2f",
                 active, target_beat, lateness_ms, arm_bpm)

    def _clear_autoloop_arm_phrase_lock(self) -> None:
        os = self._os
        os.autoloop_arm_pending = False
        os.autoloop_arm_sync_beat = 0
        os.autoloop_arm_target_elapsed_ms = 0
        os.autoloop_arm_target_source = ""
        os.autoloop_arm_pending_since = 0.0

    def _clear_live_bpm_follow(self) -> None:
        os = self._os
        os.pending_live_bpm = 0.0

    def _clear_autoloop_tempo_relock(self) -> None:
        self._os.autoloop_change_on_next_beat = False

    def _clear_pending_autoloop_master_phrase_arm(self) -> None:
        os = self._os
        os.pending_autoloop_arm_meta = None
        os.pending_autoloop_arm_deck = 0
        os.pending_autoloop_arm_mirror = 0
        os.pending_autoloop_arm_active = 0
        os.pending_autoloop_arm_source = ""
        os.pending_autoloop_arm_reason = ""

    def _clear_smart_rearm_state(self) -> None:
        os = self._os
        if self._laser_executor is not None:
            self._laser_executor.clear_pending_blackout(reason="smart_rearm_state_cleared")
        os.drop_cut_armed = False
        os.drop_rearm_beat = 0
        os.breakdown_active = False
        os.breakdown_restore_beat = 0
        os.phrase_anchor_last_beat = -1

    def toggle_smart_drop(self) -> None:
        """Toggle smart drop on/off at runtime. Must run in StateManager thread."""
        if not self._smart_rearm_experiment:
            self._smart_drop_enabled = False
            self._clear_smart_rearm_state()
            log.info("[SM] smart-drop-toggle  enabled=False  reason=experiment-off")
            return
        self._smart_drop_enabled = not self._smart_drop_enabled
        if not self._smart_drop_enabled:
            self._clear_smart_rearm_state()
        log.info("[SM] smart-drop-toggle  enabled=%s", self._smart_drop_enabled)

    def toggle_smart_breakdown(self) -> None:
        """Toggle smart breakdown on/off at runtime. Must run in StateManager thread."""
        if not self._smart_rearm_experiment:
            self._smart_breakdown_enabled = False
            self._clear_smart_rearm_state()
            log.info("[SM] smart-breakdown-toggle  enabled=False  reason=experiment-off")
            return
        self._smart_breakdown_enabled = not self._smart_breakdown_enabled
        if not self._smart_breakdown_enabled:
            self._clear_smart_rearm_state()
        log.info("[SM] smart-breakdown-toggle  enabled=%s", self._smart_breakdown_enabled)

    def _autoloop_arm_bpm(self, deck: int, fallback_bpm: float) -> tuple[float, str]:
        live = self._live_bpm_value(deck)
        if live is not None:
            return live, "live"
        return fallback_bpm, "fallback"

    def _live_bpm_status_text(self, deck: int) -> str:
        if self._live_bpm is None:
            return "live_bpm=unavailable"
        try:
            status = self._live_bpm.get_status(deck)
        except Exception:
            log.debug("live BPM status read failed", exc_info=True)
            status = None
        if status is None:
            return "live_bpm=fallback_meta live_source=fallback_meta"
        age_ms = (time.monotonic() - status.updated_at) * 1000.0
        source = getattr(status, "source", "unknown")
        return (
            f"live_bpm={status.bpm:.2f} "
            f"live_source={source} "
            f"live_age_ms={age_ms:.0f} "
            f"live_addr=0x{status.addr:x}/{status.type_name}"
        )

    def _live_bpm_follow_status_text(self) -> str:
        os = self._os
        if not self._live_bpm_follow:
            return "follow=off"
        if os.pending_live_bpm > 0:
            return f"follow=on pending_bpm={os.pending_live_bpm:.2f}"
        return "follow=on gated_bpm=active"

    # ── Instrumentation ───────────────────────────────────────────────────────

    def _log_status(self) -> None:
        active = self._os.active_deck
        for dk in (1, 2):
            d = self._deck[dk]
            mark = "►" if dk == active else " "
            snap = self._cache.get(dk)
            pos_s = bf.elapsed(snap.elapsed_ms) if snap else "no-snap"
            log.info("%s [SM] status  deck=%d  file=%s  bpm=%.1f  pos=%s  mode=%s",
                     mark, dk, bf.short(d.meta.filepath), d.meta.bpm, pos_s,
                     ("scripted" if d.scripted_id else "autoloop") if d.playing else "stopped")


def _send_direct_autoloop_rearm(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    elapsed_ms: int,
    reason: str,
    target_beat: Optional[int] = None,
) -> bool:
    d = sm._deck[active]
    if not d.meta.filepath:
        return False

    arm_bpm = sm._os.autoloop_arm_bpm if sm._os.autoloop_arm_bpm > 0 else bpm
    arm_meta = TrackMetadata(
        filepath=d.meta.filepath,
        soundswitch_id="",
        bpm=arm_bpm,
        first_beat_ms=d.meta.first_beat_ms,
        beatgrid_times_ms=list(d.meta.beatgrid_times_ms),
        beatgrid_bpms=list(d.meta.beatgrid_bpms),
        beatgrid_source=d.meta.beatgrid_source,
        total_ms=d.meta.total_ms,
    )
    target_elapsed_ms = elapsed_ms
    target_source = "current"
    lateness_ms = 0
    if target_beat is not None:
        target_elapsed_ms, target_source = sm._autoloop_target_elapsed_for_beat(
            target_beat, elapsed_ms, arm_bpm, arm_meta,
        )
        lateness_ms = max(0, elapsed_ms - target_elapsed_ms)

    object.__setattr__(arm_meta, "elapsed_ms", target_elapsed_ms)
    sm._os.last_arm_mono = time.monotonic()
    sm._os.last_armed_filepath = d.meta.filepath
    for dk in (active, mirror, 3, 4):
        sm._out.send_deck_clear(dk)
        sm._out.send_loop_off(dk)
    sm._send_autoloop_deck_load(active, mirror, active, arm_meta)
    for dk in (active, mirror, 3, 4):
        sm._out.send_bpm(dk, arm_bpm)
    sm._os.last_sent_bpm = arm_bpm
    log.info("[SM] autoloop-rearm  deck=%d  reason=%s  beat=%s  elapsed=%s"
             "  target_elapsed=%s  late=%dms  grid=%s  bpm=%.1f  file=%s",
             active, reason, target_beat if target_beat is not None else "-",
             bf.elapsed(elapsed_ms), bf.elapsed(target_elapsed_ms),
             lateness_ms, target_source, arm_bpm, bf.short(d.meta.filepath))
    return True


def _smart_drop_tick(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    this_beat: int,
    elapsed_ms: int,
    blackout_mode: bool = True,
) -> int:
    """Fire smart-drop cut before a detected drop, then rearm on the drop beat.

    Returns:
      0 when no smart-drop transition happened,
      1 when entering the pre-drop blackout window (armed),
      2 when drop crossing is reached (drop should fire now).
    """
    os = sm._os
    d = sm._deck[active]

    if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
        return _SMART_DROP_SIGNAL_NONE

    if os.breakdown_active:
        return _SMART_DROP_SIGNAL_NONE

    if os.drop_cut_armed:
        if this_beat >= os.drop_rearm_beat:
            if blackout_mode:
                log.info(
                    "[SM] smart-drop-crossing  deck=%d  beat=%d  drop_at=%d",
                    active,
                    this_beat,
                    os.drop_rearm_beat,
                )
                return _SMART_DROP_SIGNAL_CROSSING
            log.info("[SM] smart-drop-rearm  deck=%d  beat=%d", active, this_beat)
            if _send_direct_autoloop_rearm(
                sm, active, mirror, bpm, elapsed_ms, "smart-drop",
                target_beat=os.drop_rearm_beat,
            ):
                os.phrase_anchor_last_beat = os.drop_rearm_beat
                os.drop_cut_armed = False
                os.drop_rearm_beat = 0
                return _SMART_DROP_SIGNAL_CROSSING
        return _SMART_DROP_SIGNAL_NONE

    for drop_beat in d.meta.smart_drops:
        cutoff = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        if this_beat < cutoff:
            break
        if this_beat >= drop_beat:
            continue
        if any(this_beat <= bd_beat < drop_beat for bd_beat in d.meta.smart_breakdowns):
            continue
        if blackout_mode:
            log.info(
                "[SM] smart-drop-blackout-arm  deck=%d  beat=%d  drop_at=%d",
                active,
                this_beat,
                drop_beat,
            )
        else:
            log.info("[SM] smart-drop-cut  deck=%d  beat=%d  drop_at=%d", active, this_beat, drop_beat)
            for dk in (active, mirror, 3, 4):
                sm._out.send_deck_clear(dk)
                sm._out.send_loop_off(dk)
        os.drop_cut_armed = True
        os.drop_rearm_beat = drop_beat
        return _SMART_DROP_SIGNAL_BLACKOUT_ARMED
    return _SMART_DROP_SIGNAL_NONE




def _smart_breakdown_tick(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    this_beat: int,
    elapsed_ms: int,
) -> bool:
    os = sm._os
    d = sm._deck[active]

    if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
        return False

    if os.drop_cut_armed:
        return False
        
    if os.breakdown_active:
        if this_beat >= os.breakdown_restore_beat:
            log.info("[SM] smart-breakdown-restore  deck=%d  beat=%d", active, this_beat)
            if _send_direct_autoloop_rearm(
                sm, active, mirror, bpm, elapsed_ms, "smart-breakdown",
                target_beat=os.breakdown_restore_beat,
            ):
                os.phrase_anchor_last_beat = os.breakdown_restore_beat
                os.breakdown_active = False
                os.breakdown_restore_beat = 0
                return True
        return False
        
    for bd_beat in d.meta.smart_breakdowns:
        if this_beat < bd_beat:
            break
        if this_beat >= bd_beat + SMART_BREAKDOWN_WINDOW_BEATS + 1:
            continue
        if this_beat == bd_beat:
            log.info("[SM] smart-breakdown-cut  deck=%d  beat=%d", active, this_beat)
            for dk in (active, mirror, 3, 4):
                sm._out.send_deck_clear(dk)
                sm._out.send_loop_off(dk)
            os.breakdown_active = True
            os.breakdown_restore_beat = find_restore_beat(bd_beat, d.meta.anlz_buildups, d.meta.smart_drops, SMART_BREAKDOWN_DEFAULT_DURATION_BEATS)
            break
    return False

def _phrase_anchor_tick(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    this_beat: int,
    elapsed_ms: int,
    abs_beat_pos: float,
) -> bool:
    """Rearm autoloop every PHRASE_ANCHOR_BEATS to correct phrasing drift.

    Returns True if a rearm fired (caller should set change=True on the beat
    event), False otherwise.
    """
    os = sm._os

    if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
        return False

    if os.drop_cut_armed:
        return False

    if os.breakdown_active:
        return False

    if os.phrase_anchor_last_beat < 0:
        os.phrase_anchor_last_beat = (
            int(abs_beat_pos) // PHRASE_ANCHOR_BEATS
        ) * PHRASE_ANCHOR_BEATS
        return False

    next_anchor = os.phrase_anchor_last_beat + PHRASE_ANCHOR_BEATS
    if this_beat > next_anchor + 8:
        os.phrase_anchor_last_beat = this_beat
        return False

    # Pre-clear: 1 beat before anchor so SS renders the cleared state
    # before the reload arrives on the anchor beat.
    if this_beat == next_anchor - 1:
        log.info("[SM] phrase-anchor-clear  deck=%d  beat=%d  anchor=%d",
                 active, this_beat, next_anchor)
        for dk in (active, mirror, 3, 4):
            sm._out.send_deck_clear(dk)
            sm._out.send_loop_off(dk)
        return False

    if this_beat >= next_anchor:
        log.info("[SM] phrase-anchor  deck=%d  beat=%d  anchor=%d",
                 active, this_beat, next_anchor)
        if _send_direct_autoloop_rearm(
            sm, active, mirror, bpm, elapsed_ms, "phrase-anchor",
            target_beat=next_anchor,
        ):
            os.phrase_anchor_last_beat = next_anchor
            return True
    return False
