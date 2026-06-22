"""
StateManager — authoritative state + 200 Hz push loop.

Single event-loop thread:
  - drains event_queue at the top of every tick
  - reads PositionCache for current position
  - coordinates SoundSwitch output via SoundSwitchEngine and keeps canonical
    per-tick beat/BPM/elapsed fanout ordering
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
import os as _os
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from .config import (
    AUTOLOOP_ARM_PHRASE_BEATS, ARM_GUARD_S, STOP_DEBOUNCE_S,
    PLAY_SETTLE_MS, TIMING_COMPENSATION_MS,
    BPM_THRESHOLD_SCRIPTED, BPM_THRESHOLD_UNSCRIPTED,
    MEM_STALE_S, SMART_DROP_LOOKAHEAD_BEATS, SMART_DROP_IGNORE_INTRO_BEATS,
    SMART_DROP_IGNORE_OUTRO_BEATS, PHRASE_ANCHOR_BEATS,
    SMART_BREAKDOWN_DEFAULT_DURATION_BEATS,
    SMART_BREAKDOWN_IGNORE_INTRO_BEATS, SMART_BREAKDOWN_IGNORE_OUTRO_BEATS,
    LED_BACKSTEP_SEEK_BEATS,
)

from .beat_math import (
    _compute_beat_pos,
    _compute_beatgrid_position,
    _beatgrid_elapsed_for_abs_beat,
)
from .smart_phrasing import (
    build_phrase_segments_from_markers,
    select_smart_drops,
    select_smart_breakdowns,
    find_restore_beat,
)
from .models import (
    ArmSequence, BridgeEvent, DeckState, Ev, OutputState, PositionSnapshot,
    SmartDropEnergyShadow, TrackMetadata,
)
from .led_models import BeatAnchor, LEDContext
from .govee_frame_renderer import REALTIME_EFFECT_PARAM_KEYS, SLOT_EFFECTS, MAX_SLOTS
from .laser_models import LaserContext, LaserPersonality
from .soundswitch_laser_player import (
    ZERO_FRAME as _PACK_ZERO_FRAME,
    normalize_soundswitch_id as _pack_normalize_id,
)
from .soundswitch_pack_runtime import PackRuntime, DISABLED_PACK_RUNTIME
from .osl_output import OS2LOutput
from .rb_memory import PositionCache
from .scripted_tracks import SCRIPTED_TRACKS, lookup as st_lookup
from .logging_manager import get_logging_manager
from .filepath_resolver import has_soundswitch_scripted_id
from .personality_resolver import PersonalityResolver, PlaylistCache
from .session_recorder import SessionRecorder
from .sound_switch_engine import SoundSwitchEngine
from . import spectral_cache
from .audio_spectral_features import extract_spectral_features
from .anlz_reader import (
    MULTI_FEATURE_WEIGHTS_V2,
    TrackAnlzData,
    _calculate_smart_drop_energy_shadow,
    _duration_from_beatgrid,
    _make_multi_feature_scorer,
    read_anlz_drops,
)
from .autoloop_controller import (
    AutoloopController,
    AutoloopTickContext,
    send_direct_autoloop_rearm as _send_direct_autoloop_rearm,
)
from .smart_phrasing import (
    SmartPhrasingEngine, SmartPhrasingSnapshot, PhraseSegment, BeatSegment,
    SmartPhrasingState,
)
from .smart_rearm import (
    SmartDropTickResult,
    SmartRearmContext,
    SmartRearmCoordinator,
)
from . import bridge_fmt as bf

log = logging.getLogger("state_manager")
LOG = get_logging_manager()
__all__ = ["StateManager", "SmartDropTickResult"]

_LATENCY_WARN_MS = 50.0
_TC_LATENCY_WARN_MS = 250.0
# T7c pack driver: only a genuine seek/cue jump (not normal playback or jitter)
# should flag elapsed discontinuity. Err HIGH — a missed discontinuity just renders
# the scripted frame at the new position; a false one ZEROs one tick.
_PACK_SEEK_JUMP_MS = 2000
LIVE_BPM_FOLLOW_ENV = "RBSS_LIVE_BPM_FOLLOW"
AUTOLOOP_MASTER_PHRASE_ARM_ENV = "RBSS_AUTOLOOP_MASTER_PHRASE_ARM"
SMART_DROP_ENV = "RBSS_SMART_DROP"
SMART_BREAKDOWN_ENV = "RBSS_SMART_BREAKDOWN"
PHRASE_ANCHOR_ENV = "RBSS_PHRASE_ANCHOR"
SMART_REARM_EXPERIMENT_ENV = "RBSS_SMART_REARM_EXPERIMENT"
SPECTRAL_ENABLE_ENV = "RBSS_SPECTRAL_ENABLE"
WIDE_WINDOW_ENV = "RBSS_DROP_WIDE_WINDOW"
SCRIPTED_SHOWFILE_DIRECT_ENV = "RBSS_SCRIPTED_SHOWFILE_DIRECT"
STATE_MANAGER_PROFILE_ENV = "RBSS_SM_PROFILE"
# WI-1/2/3/4/5/6/7 kill-switches (read once at startup; default ON except cooldown)
LED_PHRASE_MONOTONIC_ENV   = "RBSS_LED_PHRASE_MONOTONIC"
LED_MIN_DWELL_ENV          = "RBSS_LED_MIN_DWELL"
LED_CANCEL_PENDING_ENV     = "RBSS_LED_CANCEL_PENDING"
LED_RT_RECONCILE_ENV       = "RBSS_LED_RT_RECONCILE"
LED_TRANSPORT_STICKY_ENV   = "RBSS_LED_TRANSPORT_STICKY"
LED_TRANSPORT_COOLDOWN_ENV = "RBSS_LED_TRANSPORT_COOLDOWN"  # default OFF
_SNAPSHOT_PUBLISH_INTERVAL_S = 0.05
LED_DEFAULT_DROP_IMPACT_BEATS = 8.0
LED_DEFAULT_GROOVE_CYCLE_BEATS = 32.0
LED_DEFAULT_POST_DROP_CYCLE_BEATS = 32.0
_LED_DROP_IMPACT_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})
# Max drop impacts per drop lifecycle. The first fires off an Up/Low buildup;
# this allows one extra back-to-back Chorus->Chorus drop before settling into
# post_drop (i.e. up to two drop hits in a row, then post_drop).
LED_MAX_DROP_IMPACTS = 2
_PROFILE_SUMMARY_INTERVAL_S = 10.0
_PROFILE_WINDOW = 2048
_LED_ADAPTER_STATUS_SAFE_KEYS = {
    "available",
    "running",
    "dry_run",
    "degraded",
    "degraded_reason",
    "queue_depth",
    "queue_max",
    "accepted_count",
    "rejected_count",
    "dropped_count",
    "queue_full_count",
    "deduped_count",
    "rate_limited_count",
    "send_count",
    "send_error_count",
    "malformed_response_count",
    "consecutive_send_failures",
    "circuit_open",
    "last_error",
    "last_command_at",
    "last_command_look",
}


def _read_runtime_anlz_data(
    anlz_path: str,
    *,
    audio_filepath: str = "",
    spectral_enabled: bool = False,
    wide_window: bool = False,
) -> TrackAnlzData:
    data = read_anlz_drops(anlz_path)
    if not spectral_enabled:
        return data
    ctx = data.waveform_context
    if ctx is None or not data.drop_beat_indices:
        return data

    beatgrid_times_ms = list(ctx.beatgrid_times_ms)
    features = _runtime_spectral_features(audio_filepath, beatgrid_times_ms)
    phrases = list(data.buildup_beat_indices) + list(data.breakdown_beat_indices)
    data.energy_shadow = _calculate_smart_drop_energy_shadow(
        list(ctx.heights),
        _duration_from_beatgrid(beatgrid_times_ms),
        beatgrid_times_ms,
        data.drop_beat_indices,
        # TODO(M4): hoist the v2 runtime scorer if this path becomes hot enough.
        scorer=_make_multi_feature_scorer(
            MULTI_FEATURE_WEIGHTS_V2,
            wide_window=wide_window,
            phrases=phrases,
        ),
        spectral_features=features,
        wide_window=wide_window,
        phrases=phrases,
    )
    return data


def _runtime_spectral_features(audio_filepath: str, beatgrid_times_ms: list[float]):
    if not audio_filepath:
        return None
    cached = spectral_cache.get_cached(audio_filepath, beatgrid_times_ms)
    if cached is not None:
        return cached
    features = extract_spectral_features(audio_filepath, beatgrid_times_ms)
    if features is not None:
        spectral_cache.put_cached(audio_filepath, beatgrid_times_ms, features)
    return features


def _energy_shadow_priority(shadows: list[SmartDropEnergyShadow]) -> int:
    if any(item.source == "v2_spectral" for item in shadows):
        return 2
    if any(item.source == "v2_waveform" for item in shadows):
        return 1
    return 0


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
        led_look_director=None,
        led_scene_adapter=None,
        led_color_engine=None,
        os2l_connected_provider=None,
        recorder: Optional[SessionRecorder] = None,
        soundswitch_pack_runtime=None,
    ) -> None:
        self._eq    = event_queue
        self._cache = position_cache
        self._out   = output
        self._live_bpm = live_bpm
        self._recorder = recorder if recorder is not None else SessionRecorder.from_env()
        # Optional Laser Director — None means disabled/not configured.
        # Mutated only from this thread after start().
        self._laser_director = laser_director
        self._laser_executor = laser_executor
        self._laser_personality_provider = laser_personality_provider
        # T7c SoundSwitch pack driver (None ⇒ neutral; existing path unchanged).
        # The driver READS DeckState; StateManager remains the only DeckState writer.
        # T7e: one immutable runtime bundle, published atomically by the command
        # thread (set_pack_runtime) and read once per tick by the push loop, so the
        # driver never sees a mixed old/new runtime. Default = disabled (neutral).
        self._pack_runtime: PackRuntime = soundswitch_pack_runtime or DISABLED_PACK_RUNTIME
        # Push-thread-owned driver trackers (NOT part of the swappable bundle).
        self._pack_last_load_gen: tuple[int, int] | None = None   # (active, load_gen)
        self._pack_last_elapsed_ms: int | None = None
        self._pack_last_static_slot: int | None = None
        self._pack_logged_error = False
        self._led_look_director = led_look_director
        self._led_scene_adapter = led_scene_adapter
        # M1b WI-1: optional LED color engine (None ⇒ no color injection).
        self._led_color_engine = led_color_engine
        self._led_manual_override = ""
        self._led_manual_target_override = ""
        self._led_emergency_blackout = False
        self._led_last_error = ""
        self._led_last_event = ""
        self._led_last_look = ""
        self._led_trigger_count = 0
        self._led_rejected_count = 0
        self._led_enabled_latch = False
        self._led_dry_run_latch = True
        self._led_automation_enabled_latch = False
        self._led_scripted_mode_automation_latch = False
        self._led_scripted_default_role = "breakdown"
        self._led_scripted_role_map: dict[str, str] = {}
        self._led_last_auto_role_key = ""
        # M1b WI-2: structured (section_id, cycle) published alongside the
        # string role_key so the color engine seeds on stable fields without
        # parsing the marker text.
        self._led_last_section_cycle: tuple[str, int] = ("", 0)
        self._led_automation_gate_reason = "not_configured"
        self._led_automation_trigger_count = 0
        self._led_automation_gated_count = 0
        self._led_smart_drop_blackout_key = ""
        self._led_first_drop_anchor_beat: float | None = None
        self._led_drop_impact_until_beat: float | None = None
        self._led_drop_impact_count = 0
        self._led_active_drop_look = ""
        self._led_committed_drop_anchor_beat: float | None = None
        self._led_committed_drop_decision: Any | None = None
        self._led_drop_look_fired_anchor: float | None = None
        self._led_automation_offset_s = 0.0
        self._led_cloud_automation_offset_s = 0.0
        self._led_realtime_automation_offset_s = 0.0
        self._led_last_idle_role_key = ""
        self._led_rt_permitted = False
        self._led_rt_beat: tuple[int, float, float, float, bool] | None = None
        self._led_color_engine_status: dict[str, Any] = {
            "available": bool(led_color_engine is not None),
            "enabled": bool(getattr(led_color_engine, "enabled", False)),
            "reason": "ok" if led_color_engine is not None else "not_configured",
        }
        self._last_sp_snapshot: Optional[SmartPhrasingSnapshot] = None
        # WI-1 monotonic beat clamp state
        self._led_beat_monotonic: Optional[float] = None
        self._led_beat_monotonic_key: Optional[tuple[int, int]] = None
        self._phrase_monotonic_enabled: bool = (
            _os.environ.get(LED_PHRASE_MONOTONIC_ENV, "1") != "0"
        )
        # WI-2 phrase latch state
        self._led_phrase_seq: int = 0
        self._led_phrase_committed_start: Optional[float] = None
        # WI-8 observability counters
        self._led_phrase_latch_reset_count: int = 0
        if self._led_look_director is not None:
            try:
                status_payload = self._led_look_director.status()
                self._led_enabled_latch = bool(status_payload.get("enabled", False))
                self._led_dry_run_latch = bool(status_payload.get("dry_run", True))
                self._led_automation_enabled_latch = bool(
                    status_payload.get("automation_enabled", False)
                )
                self._led_scripted_mode_automation_latch = bool(
                    status_payload.get("scripted_mode_automation", False)
                )
                sm_policy = status_payload.get("scripted_mode", {}) or {}
                if not isinstance(sm_policy, dict):
                    sm_policy = {}
                self._led_scripted_default_role = str(
                    sm_policy.get("default_role", "breakdown")
                )
                self._led_scripted_role_map = dict(sm_policy.get("role_map", {}))
                cloud_offset = float(
                    status_payload.get(
                        "automation_cloud_offset_s",
                        status_payload.get("automation_offset_s", 0.0),
                    )
                )
                realtime_offset = float(
                    status_payload.get("automation_realtime_offset_s", 0.0)
                )
                self._led_cloud_automation_offset_s = max(0.0, cloud_offset)
                self._led_realtime_automation_offset_s = max(0.0, realtime_offset)
                # Backward-compatible status alias; cloud keeps the legacy lead.
                self._led_automation_offset_s = self._led_cloud_automation_offset_s
                self._led_automation_gate_reason = (
                    "" if self._led_automation_enabled_latch else "automation_disabled"
                )
            except Exception:
                self._led_enabled_latch = False
                self._led_dry_run_latch = True
                self._led_automation_enabled_latch = False
                self._led_scripted_mode_automation_latch = False
                self._led_scripted_default_role = "breakdown"
                self._led_scripted_role_map = {}
                self._led_automation_gate_reason = "status_unavailable"
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
            and _os.environ.get(PHRASE_ANCHOR_ENV, "0") == "1"
        )
        self._spectral_enable = (
            self._smart_rearm_experiment
            and _os.environ.get(SPECTRAL_ENABLE_ENV, "0") == "1"
        )
        self._wide_window_enable = _os.environ.get(WIDE_WINDOW_ENV, "1") != "0"
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
        self._personality_resolver: Optional[PersonalityResolver] = None
        self._personality_playlist_cache: Optional[PlaylistCache] = None
        # Bridge only sees logical decks 1/2 via _RB_TO_BRIDGE (DDJ-800 mirrors
        # 1<->3 and 2<->4 at the physical layer). Extend this dict if logical
        # deck count grows.
        self._personality_eligible_deck: dict[int, bool] = {1: False, 2: False}
        self._pending_arm: Optional[ArmSequence] = None

        # Rate-limited position logging (once every 5 s per deck)
        self._last_pos_log: dict[int, float] = {1: 0.0, 2: 0.0}

        # Timecode fallback anchor: (elapsed_ms, wall_time, pitch_factor) per deck.
        # Updated by TC_UPDATE events.
        self._tc_anchor: dict[int, tuple[int, float, float]] = {1: (0, 0.0, 1.0), 2: (0, 0.0, 1.0)}

        # ANLZ path keyed by bridge deck: populated by ANLZ_PATH event,
        # consumed by _on_track_loaded to skip lsof
        self._pending_anlz_path: dict[int, str] = {}
        self._loaded_anlz_path: dict[int, tuple[str, int]] = {}

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
        self._last_sp_state: Optional[SmartPhrasingState] = None
        # Latches sp.phrase_anchor_requested (one 200 Hz tick) until the next
        # beat boundary consumes it, so a marker crossing can never be dropped.
        self._pending_phrase_marker: bool = False
        self._publish_snapshot()
        self._snapshot_publish_interval_s = _SNAPSHOT_PUBLISH_INTERVAL_S
        self._next_snapshot_publish_at = time.monotonic() + self._snapshot_publish_interval_s
        self._profiler = (
            _StateManagerProfiler()
            if _os.environ.get(STATE_MANAGER_PROFILE_ENV, "0") != "0"
            else None
        )

        # ── SmartPhrasingEngine integration (Issue #33) ───────────────────
        # One engine instance, updated each tick inside _build_laser_context.
        # Timing constants cached here to avoid config reads inside _push_tick.
        self._smart_phrasing_engine = SmartPhrasingEngine()
        self._sp_phrase_lookahead: float = 32.0   # project rule: buildup = 32 beats before Smart Drop
        self._sp_drop_window: float = float(SMART_DROP_LOOKAHEAD_BEATS)
        self._sp_post_drop: float = 8.0           # conservative default; not consumed until Phase 3
        self._sp_transition_window: float = float(SMART_DROP_LOOKAHEAD_BEATS)
        self._sp_breakdown_default_restore: int = SMART_BREAKDOWN_DEFAULT_DURATION_BEATS
        self._active_personality_for_timing: Optional[LaserPersonality] = None
        self._last_applied_personality: Optional[LaserPersonality] = None
        self._phrase_segments_cache: dict[int, tuple[int, tuple[PhraseSegment, ...]]] = {}
        self._smart_drop_beats_cache: dict[int, tuple[int, tuple[float, ...]]] = {}
        self._breakdown_segments_cache: dict[int, tuple[int, tuple[BeatSegment, ...]]] = {}
        self._sse = SoundSwitchEngine(self._out)
        self._autoloop = AutoloopController(
            output_state_ref=lambda: self._os,
            deck_ref=lambda d: self._deck[d],
            live_bpm_service=self._live_bpm,
            sse=self._sse,
            clock=time.monotonic,
            logger=log,
            live_bpm_follow=self._live_bpm_follow,
            recorder_ref=lambda: self._recorder,
        )

        def _autoloop_rearm_bridge(*args, **kwargs):
            return _send_direct_autoloop_rearm(self, *args, **kwargs)

        def _hold_mask(owner: str) -> None:
            if self._laser_executor is not None:
                self._laser_executor.hold_blackout_mask(owner)

        def _release_mask(owner: str) -> None:
            if self._laser_executor is not None:
                self._laser_executor.release_blackout_mask(owner)

        self._smart_rearm = SmartRearmCoordinator(
            output_state_ref=lambda: self._os,
            deck_ref=lambda d: self._deck[d],
            send_direct_autoloop_rearm=_autoloop_rearm_bridge,
            send_smart_transition_clear=self._sse.send_smart_transition_clear,
            hold_blackout_mask=_hold_mask,
            release_blackout_mask=_release_mask,
        )
        callback = getattr(self._laser_director, "set_personality_apply_callback", None)
        if callable(callback):
            callback(self._apply_personality_change)
        self._recache_initial_personality_timing()

    def set_initial_state(self, active_deck: int, source: str = "default startup") -> None:
        """Apply startup active-deck state before the event loop starts."""
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
        authority for timecode synthesis; the memory reader only uses this value
        to find paused Deck-2 candidates and still requires movement validation
        before publishing memory snapshots.
        """
        if deck not in (1, 2):
            return None
        d = self._deck[deck]
        anchor_ms, anchor_at, anchor_pitch = self._tc_anchor.get(deck, (0, 0.0, 1.0))
        now = time.monotonic()
        if anchor_ms > 0 and 0.0 < now - anchor_at < 45.0:
            age_ms = (now - anchor_at) * 1000.0 * anchor_pitch
            return int(anchor_ms + (age_ms if d.playing else 0.0))
        if d.elapsed_ms > 0:
            return d.elapsed_ms
        return None

    def get_deck_playing(self, deck: int) -> bool:
        """Authoritative play state hint for memory-side discovery scheduling."""
        if deck not in (1, 2):
            return False
        return self._deck[deck].playing

    def led_status_provider(self) -> dict[str, Any]:
        available = self._led_look_director is not None and self._led_scene_adapter is not None
        reason = "ok"
        if not available:
            reason = "not_configured"
        elif not self._led_enabled_latch:
            reason = "disabled"
        elif self._led_last_error:
            reason = "degraded"

        payload: dict[str, Any] = {
            "available": bool(available),
            "enabled": bool(self._led_enabled_latch),
            "reason": reason,
            "manual_override": self._led_manual_override,
            "manual_target_override": self._led_manual_target_override,
            "emergency_blackout": bool(self._led_emergency_blackout),
            "last_error": self._led_last_error,
            "last_event": self._led_last_event,
            "last_look": self._led_last_look,
            "trigger_count": int(self._led_trigger_count),
            "rejected_count": int(self._led_rejected_count),
            "dry_run": bool(self._led_dry_run_latch),
            "automation_enabled": bool(self._led_automation_enabled_latch),
            "automation_gate_reason": self._led_automation_gate_reason,
            "automation_last_role_key": self._led_last_auto_role_key,
            "automation_trigger_count": int(self._led_automation_trigger_count),
            "automation_gated_count": int(self._led_automation_gated_count),
            "automation_offset_s": float(self._led_automation_offset_s),
            "automation_cloud_offset_s": float(self._led_cloud_automation_offset_s),
            "automation_realtime_offset_s": float(
                self._led_realtime_automation_offset_s
            ),
            "smart_drop_blackout_active": bool(self._led_smart_drop_blackout_key),
            # WI-8 observability
            "phrase_latch_seq": int(self._led_phrase_seq),
            "phrase_latch_reset_count": int(self._led_phrase_latch_reset_count),
        }

        if self._led_look_director is not None:
            try:
                raw_director = self._led_look_director.status()
                if isinstance(raw_director, dict):
                    payload["director"] = {
                        "available": bool(raw_director.get("available", True)),
                        "enabled": bool(raw_director.get("enabled", False)),
                        "dry_run": bool(raw_director.get("dry_run", True)),
                        "automation_enabled": bool(raw_director.get("automation_enabled", False)),
                        "automation_offset_s": float(
                            raw_director.get("automation_offset_s", 0.0)
                        ),
                        "automation_cloud_offset_s": float(
                            raw_director.get("automation_cloud_offset_s", 0.0)
                        ),
                        "automation_realtime_offset_s": float(
                            raw_director.get("automation_realtime_offset_s", 0.0)
                        ),
                        "scripted_mode_automation": bool(
                            raw_director.get("scripted_mode_automation", False)
                        ),
                        "current_look": str(raw_director.get("current_look", "")),
                        "last_reason": str(raw_director.get("last_reason", "")),
                        "last_source": str(raw_director.get("last_source", "")),
                        "manual_override": str(raw_director.get("manual_override", "")),
                        "emergency_blackout": bool(raw_director.get("emergency_blackout", False)),
                    }
            except Exception as exc:
                payload["reason"] = "provider_error"
                payload["last_error"] = f"director_status_error:{type(exc).__name__}"

        if self._led_scene_adapter is not None:
            try:
                raw_adapter = self._led_scene_adapter.status()
                payload["adapter"] = self._sanitize_led_adapter_status(raw_adapter)
            except Exception as exc:
                payload["reason"] = "provider_error"
                payload["last_error"] = f"adapter_status_error:{type(exc).__name__}"

        return payload

    def color_engine_status_provider(self) -> dict[str, Any]:
        """Return the latest StateManager-published color engine status copy."""
        with self._snapshot_lock:
            return dict(self._led_color_engine_status)

    def get_active_beat_anchor(self) -> Optional[BeatAnchor]:
        """Return the LED realtime beat snapshot when automation is permitted."""
        if not self._led_rt_permitted or self._led_rt_beat is None:
            return None
        deck, abs_beat_pos, bpm, captured_monotonic, playing = self._led_rt_beat
        if not playing or bpm <= 0.0:
            return None
        return BeatAnchor(
            deck=deck,
            abs_beat_pos=abs_beat_pos,
            bpm=bpm,
            captured_monotonic=captured_monotonic,
            playing=playing,
            permitted=True,
        )

    def _sanitize_led_adapter_status(self, raw_status: Any) -> dict[str, Any]:
        if not isinstance(raw_status, dict):
            return {}
        safe: dict[str, Any] = {}
        for key in _LED_ADAPTER_STATUS_SAFE_KEYS:
            if key not in raw_status:
                continue
            value = raw_status.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
        provider = raw_status.get("provider")
        if isinstance(provider, dict):
            provider_safe: dict[str, Any] = {}
            for key in ("api_key_present", "target_count", "scene_count"):
                value = provider.get(key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    provider_safe[key] = value
            if provider_safe:
                safe["provider"] = provider_safe
        realtime = raw_status.get("realtime")
        if isinstance(realtime, dict):
            realtime_safe: dict[str, Any] = {}
            for key in (
                "owner",
                "active",
                "provider_bound",
                "desired_effect",
                "active_effect",
                "frame_index",
                "idle_since",
                "last_error",
                "realtime_trigger_count",
                "tactical_blackout_count",
            ):
                value = realtime.get(key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    realtime_safe[key] = value
            transport = realtime.get("transport")
            if isinstance(transport, dict):
                transport_safe: dict[str, Any] = {}
                for key in (
                    "ip",
                    "port",
                    "segments",
                    "frames_sent",
                    "command_count",
                    "send_error_count",
                    "last_error",
                    "last_payload_bytes",
                ):
                    value = transport.get(key)
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        transport_safe[key] = value
                if transport_safe:
                    realtime_safe["transport"] = transport_safe
            if realtime_safe:
                safe["realtime"] = realtime_safe
        return safe

    def _sanitize_led_scene_ref(self, scene_ref: Any) -> str:
        text = str(scene_ref or "").strip()
        if not text:
            return ""
        if re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5,}", text):
            return "<redacted>"
        if len(text) > 80:
            return "<redacted>"
        if any(ch in text for ch in ("\n", "\r", "\t")):
            return "<redacted>"
        if not any(ch.isalpha() for ch in text):
            return "<redacted>"
        allowed_punct = {" ", "_", "-", ".", "/", ":"}
        if not all(ch.isalnum() or ch in allowed_punct for ch in text):
            return "<redacted>"
        return text

    def _set_led_automation_gate_reason(
        self,
        reason: str,
        *,
        active_deck: Optional[int] = None,
        role: str = "",
        role_key: str = "",
    ) -> None:
        previous = self._led_automation_gate_reason
        self._led_automation_gate_reason = reason
        if reason == previous:
            return
        log.info(
            "[RGB] gate-reason-change reason=%s prev=%s enabled=%s dry_run=%s automation_enabled=%s active_deck=%d role=%s role_key=%s",
            reason or "clear",
            previous or "clear",
            bool(self._led_enabled_latch),
            bool(self._led_dry_run_latch),
            bool(self._led_automation_enabled_latch),
            int(active_deck if active_deck is not None else self._os.active_deck),
            role or "-",
            role_key or "-",
        )

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
        color_engine_status = {
            "available": False,
            "enabled": False,
            "reason": "not_configured",
        }
        sp = self._last_sp_state
        if self._laser_executor is not None:
            try:
                executor_blackout_pending = bool(
                    self._laser_executor.status().get("blackout_pending_for_drop_window", False)
                )
            except Exception:
                executor_blackout_pending = False
        if self._led_color_engine is not None:
            try:
                raw_color_status = self._led_color_engine.snapshot()
                color_engine_status = {
                    **(
                        raw_color_status
                        if isinstance(raw_color_status, dict)
                        else {}
                    ),
                    "available": True,
                    "enabled": bool(getattr(self._led_color_engine, "enabled", False)),
                    "reason": "ok",
                }
            except Exception as exc:
                color_engine_status = {
                    "available": True,
                    "enabled": bool(getattr(self._led_color_engine, "enabled", False)),
                    "reason": "provider_error",
                    "last_error": f"{type(exc).__name__}: {exc}",
                }
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
            "smart_drop_enabled": self._smart_drop_enabled,
            "smart_breakdown_enabled": self._smart_breakdown_enabled,
            "smart_phrasing": (
                None
                if sp is None
                else {
                    "phrase_label": sp.current_phrase_label,
                    "is_up": sp.current_phrase_is_up,
                    "is_chorus": sp.current_phrase_is_chorus,
                    "is_low": sp.current_phrase_is_low,
                    "next_smart_drop_beat": sp.next_smart_drop_beat,
                    "beats_to_next_drop": sp.beats_to_next_drop,
                    "smart_drop_window_active": sp.smart_drop_window_active,
                    "transition_window_active": sp.transition_window_active,
                    "smart_breakdown_active": sp.smart_breakdown_active,
                    "smart_post_drop_active": sp.smart_post_drop_active,
                    "phrase_anchor_target_beat": sp.phrase_anchor_target_beat,
                    "reason": sp.reason,
                }
            ),
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
            "recording": self.recording_status(),
            "led_color_engine": color_engine_status,
            "deck": deck,
        }
        with self._snapshot_lock:
            self._published_snapshot = snapshot
            self._led_color_engine_status = dict(color_engine_status)

    def start_session_recording(self, path: str, *, dedup: bool = False) -> bool:
        if self._recorder:
            return False
        self._recorder = SessionRecorder(path, dedup=dedup)
        log.info("[SM] record-session-start  path=%s  dedup=%s", path, "on" if dedup else "off")
        return True

    def stop_session_recording(self) -> bool:
        if not self._recorder:
            return False
        path = str(self._recorder.path)
        self._recorder.close()
        self._recorder = None
        log.info("[SM] record-session-stop  path=%s", path)
        return True

    def toggle_session_recording(self, path: str, *, dedup: bool = False) -> bool:
        if self._recorder:
            return self.stop_session_recording()
        return self.start_session_recording(path, dedup=dedup)

    def recording_status(self) -> dict:
        if not self._recorder:
            return {"active": False, "path": "", "dedup": False, "counts": {}}
        return self._recorder.status()

    def _drain_events(self) -> None:
        """Consume all pending events without blocking."""
        while True:
            try:
                ev = self._eq.get_nowait()
            except queue.Empty:
                break
            if self._recorder:
                self._recorder.record_event(ev)
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
                    meta = d_obj.meta
                    event_source = ev.payload.get("source", "anlz")
                    raw_drops = list(ev.payload.get("drop_beat_indices", []))
                    raw_breakdowns = list(ev.payload.get("breakdown_beat_indices", []))
                    raw_buildups = list(ev.payload.get("buildup_beat_indices", []))
                    raw_mood = ev.payload.get("mood", 0)
                    total_beats = len(meta.beatgrid_times_ms)

                    existing_markers_empty = not any((
                        meta.anlz_drops, meta.anlz_breakdowns,
                        meta.anlz_buildups, meta.anlz_mood,
                    ))
                    can_update = event_source == "anlz" or existing_markers_empty
                    markers_changed = can_update and (
                        raw_drops != meta.anlz_drops
                        or raw_breakdowns != meta.anlz_breakdowns
                        or raw_buildups != meta.anlz_buildups
                        or raw_mood != meta.anlz_mood
                    )

                    next_drops = raw_drops if can_update else meta.anlz_drops
                    next_smart_drops = select_smart_drops(
                        next_drops,
                        total_beats=total_beats,
                    )
                    next_breakdowns = raw_breakdowns if can_update else meta.anlz_breakdowns
                    next_smart_breakdowns = select_smart_breakdowns(
                        next_breakdowns,
                        total_beats=total_beats,
                    )

                    selected_set = set(next_smart_drops)
                    new_shadow = [
                        item for item in ev.payload.get("energy_shadow", [])
                        if isinstance(item, SmartDropEnergyShadow)
                        and item.anlz_beat in selected_set
                    ]
                    if (
                        meta.smart_drop_energy_shadow
                        and _energy_shadow_priority(meta.smart_drop_energy_shadow)
                        > _energy_shadow_priority(new_shadow)
                    ):
                        new_shadow = [
                            item for item in meta.smart_drop_energy_shadow
                            if item.anlz_beat in selected_set
                        ]
                    shadow_changed = new_shadow != meta.smart_drop_energy_shadow

                    if markers_changed:
                        self._clear_phrase_segment_cache(ev.deck)
                        meta.anlz_drops = raw_drops
                        meta.smart_drops = next_smart_drops
                        meta.anlz_breakdowns = raw_breakdowns
                        meta.smart_breakdowns = next_smart_breakdowns
                        meta.anlz_buildups = raw_buildups
                        meta.anlz_mood = raw_mood
                    meta.smart_drop_energy_shadow = new_shadow
                    if markers_changed or shadow_changed:
                        log.info("[SM] smart-transition-select  deck=%d  drops=%d  smart_drops=%d  bd=%d  smart_bd=%d  up=%d  source=%s",
                                 ev.deck,
                                 len(meta.anlz_drops),
                                 len(meta.smart_drops),
                                 len(meta.anlz_breakdowns),
                                 len(meta.smart_breakdowns),
                                 len(meta.anlz_buildups),
                                 event_source)
                        for item in new_shadow:
                            log.info(
                                "[SM] smart-drop-energy-shadow  deck=%d  "
                                "anlz_elapsed=%s  suggested_elapsed=%s  "
                                "lift_anlz=%.2f  lift_suggested=%.2f  confidence=%.2f  source=%s",
                                ev.deck,
                                bf.elapsed(item.anlz_elapsed_ms),
                                bf.elapsed(item.suggested_elapsed_ms),
                                item.lift_at_anlz,
                                item.lift_at_suggested,
                                item.confidence,
                                item.source,
                            )
                else:
                    log.debug("[SM] anlz-drops-stale  deck=%d  gen=%d  current=%d",
                              ev.deck, gen, d_obj.load_gen)

        elif ev.kind == Ev.TC_UPDATE:
            tc_ms = ev.payload.get('elapsed_ms', 0)
            if tc_ms > 0:
                pitch = ev.payload.get('pitch_factor', 1.0)
                self._tc_anchor[ev.deck] = (tc_ms, ev.mono, pitch)

        elif ev.kind == Ev.BPM_UPDATE:
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
                self._personality_eligible_deck[d] = False
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
                self._dispatch_led_idle_ambient(
                    active=self._os.active_deck,
                    d=self._deck[self._os.active_deck],
                    reason="rb_restart",
                )
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
            self._autoloop.clear_arm_phrase_lock()
            self._autoloop.clear_live_bpm_follow()
            self._autoloop.clear_tempo_relock()
            self._autoloop.clear_pending_master_phrase_arm()
            if self._live_bpm is not None:
                try:
                    self._live_bpm.invalidate()
                except Exception:
                    log.debug("live BPM invalidation failed", exc_info=True)

        elif ev.kind == Ev.SMART_DROP_TOGGLE:
            self.toggle_smart_drop()

        elif ev.kind == Ev.SMART_BREAKDOWN_TOGGLE:
            self.toggle_smart_breakdown()

        elif ev.kind in {
            Ev.LED_SET_ENABLED,
            Ev.LED_SCENE,
            Ev.LED_BLACKOUT,
            Ev.LED_CLEAR_BLACKOUT,
            Ev.LED_CLEAR_SCENE_OVERRIDE,
        }:
            self._handle_led_event(ev)

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
                if ev.source not in {"test", "unit_test", "internal"}:
                    log.warning(
                        "[PERSONALITY] external LASER_SET_PERSONALITY source=%s",
                        ev.source or "unknown",
                    )
                personality_name = str(ev.payload.get("personality", ""))
                provider = self._laser_personality_provider
                if provider is None:
                    self._laser_director.set_personality(personality_name)
                else:
                    personality_cfg = provider(personality_name)
                    if personality_cfg is not None:
                        self._apply_personality_change(personality_name, personality_cfg)

    def _handle_led_event(self, ev: BridgeEvent) -> None:
        if ev.kind == Ev.LED_SET_ENABLED:
            self._led_enabled_latch = bool(ev.payload.get("enabled", False))
            self._dispatch_led_manual_command(reason="set_enabled")
            return

        if ev.kind == Ev.LED_SCENE:
            look = str(ev.payload.get("look", "")).strip()
            if not look:
                self._led_last_event = "manual_scene"
                self._led_last_error = "led_scene_missing_look"
                self._led_rejected_count += 1
                return
            if "target" in ev.payload:
                target = str(ev.payload.get("target", "")).strip()
                if target and not self._led_target_exists(target):
                    self._led_last_event = "manual_scene"
                    self._led_last_error = f"unknown_target:{target}"
                    self._led_rejected_count += 1
                    return
                self._led_manual_target_override = target
            else:
                self._led_manual_target_override = ""
            self._led_manual_override = look
            self._dispatch_led_manual_command(reason="manual_scene")
            return

        if ev.kind == Ev.LED_BLACKOUT:
            if "target" in ev.payload:
                target = str(ev.payload.get("target", "")).strip()
                if target and not self._led_target_exists(target):
                    self._led_last_event = "blackout"
                    self._led_last_error = f"unknown_target:{target}"
                    self._led_rejected_count += 1
                    return
                self._led_manual_target_override = target
            self._led_emergency_blackout = True
            self._dispatch_led_manual_command(reason="blackout")
            return

        if ev.kind == Ev.LED_CLEAR_BLACKOUT:
            self._led_emergency_blackout = False
            self._dispatch_led_manual_command(reason="clear_blackout")
            return

        if ev.kind == Ev.LED_CLEAR_SCENE_OVERRIDE:
            self._led_manual_override = ""
            self._led_manual_target_override = ""
            self._dispatch_led_manual_command(reason="clear_scene_override")
            return

    def _led_target_exists(self, target_name: str) -> bool:
        director = self._led_look_director
        if director is None:
            return False
        config = getattr(director, "_config", None)
        if config is None:
            return False
        targets = getattr(config, "targets", None)
        if not isinstance(targets, dict):
            return False
        return target_name in targets

    def _dispatch_led_manual_command(self, *, reason: str) -> None:
        if self._led_color_engine is not None and reason in ("blackout", "manual_scene"):
            self._led_color_engine.reset_fade_memory()
        self._led_last_event = reason
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""

        if self._led_look_director is None or self._led_scene_adapter is None:
            self._led_last_error = "not_configured"
            return
        if not self._led_enabled_latch:
            self._led_last_error = ""
            return

        manual_look = self._led_manual_override or None
        try:
            set_manual_override = getattr(self._led_look_director, "set_manual_override", None)
            if callable(set_manual_override):
                accepted = set_manual_override(manual_look)
                if accepted is False and manual_look:
                    self._led_manual_override = ""
                    self._led_last_error = f"unknown_look:{manual_look}"
                    self._led_rejected_count += 1
                    return
            set_emergency_blackout = getattr(self._led_look_director, "set_emergency_blackout", None)
            if callable(set_emergency_blackout):
                set_emergency_blackout(self._led_emergency_blackout)
            decision = self._led_look_director.tick(
                LEDContext(
                    role="manual",
                    manual_look=manual_look,
                    emergency_blackout=self._led_emergency_blackout,
                    target_override=self._led_manual_target_override,
                )
            )
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            return

        if decision is None:
            self._led_last_error = ""
            self._led_last_look = ""
            return

        try:
            accepted = bool(self._led_scene_adapter.trigger(decision))
        except Exception as exc:
            self._led_last_error = f"adapter_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            return

        if accepted:
            self._led_trigger_count += 1
            self._led_last_error = ""
            self._led_last_look = str(getattr(decision, "look", ""))
            return

        self._led_rejected_count += 1
        self._led_last_error = "adapter_rejected"

    def _dispatch_led_smart_drop_blackout(
        self,
        *,
        active: int,
        d: DeckState,
        sp_state: SmartPhrasingState,
        phase: str,
    ) -> None:
        marker = ""
        if sp_state.active_drop_beat is not None:
            marker = f"{sp_state.active_drop_beat:.3f}"
        elif sp_state.next_smart_drop_beat is not None:
            marker = f"{sp_state.next_smart_drop_beat:.3f}"
        drop_anchor = self._led_drop_anchor_for_blackout(sp_state)
        if self._led_same_drop_anchor(drop_anchor, self._led_drop_look_fired_anchor):
            return
        blackout_key = f"{active}:{d.load_gen}:smart_drop_blackout:{phase}:{marker}"
        if blackout_key == self._led_smart_drop_blackout_key:
            return

        drop_preview = self._led_drop_decision_for_anchor(sp_state, commit=True)
        tactical_blackout = getattr(self._led_scene_adapter, "tactical_blackout", None)
        if (
            drop_preview is not None
            and str(getattr(drop_preview, "backend", "")) == "realtime_razer"
            and callable(tactical_blackout)
        ):
            self._led_last_auto_role_key = blackout_key
            self._led_last_event = f"automation:smart_drop_blackout:{phase}:realtime"
            try:
                accepted = bool(tactical_blackout(drop_preview))
            except Exception as exc:
                self._led_last_error = f"adapter_error:{type(exc).__name__}"
                self._led_rejected_count += 1
                self._led_automation_gated_count += 1
                self._set_led_automation_gate_reason(
                    "adapter_error",
                    active_deck=active,
                    role="smart_drop_blackout",
                    role_key=blackout_key,
                )
                log.warning(
                    "[RGB] tactical-blackout-error phase=%s look=%s role_key=%s active_deck=%d err=%s",
                    phase,
                    str(getattr(drop_preview, "look", "")) or "-",
                    blackout_key,
                    active,
                    type(exc).__name__,
                )
                return
            if accepted:
                self._led_trigger_count += 1
                self._led_automation_trigger_count += 1
                self._led_smart_drop_blackout_key = blackout_key
                self._led_last_error = ""
                self._led_last_look = "realtime_blackout"
                self._set_led_automation_gate_reason(
                    "",
                    active_deck=active,
                    role="smart_drop_blackout",
                    role_key=blackout_key,
                )
                log.info(
                    "[RGB] tactical-blackout-accepted phase=%s next_drop=%s role_key=%s trigger_count=%d active_deck=%d",
                    phase,
                    str(getattr(drop_preview, "look", "")) or "-",
                    blackout_key,
                    self._led_automation_trigger_count,
                    active,
                )
                return
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._led_last_error = "adapter_rejected"
            self._set_led_automation_gate_reason(
                "adapter_rejected",
                active_deck=active,
                role="smart_drop_blackout",
                role_key=blackout_key,
            )
            return

        context = LEDContext(
            role="pre_drop",
            manual_look=None,
            emergency_blackout=True,
            active_deck=active,
            playing=d.playing,
            lighting_mode=self._os.lighting_mode,
            scripted_id=d.scripted_id,
        )
        try:
            decision = self._led_look_director.tick(context)
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "director_error",
                active_deck=active,
                role="smart_drop_blackout",
                role_key=blackout_key,
            )
            log.warning(
                "[RGB] director-error role=%s phase=%s role_key=%s active_deck=%d err=%s",
                "smart_drop_blackout",
                phase,
                blackout_key,
                active,
                type(exc).__name__,
            )
            self._led_last_auto_role_key = blackout_key
            return

        self._led_last_auto_role_key = blackout_key
        self._led_last_event = f"automation:smart_drop_blackout:{phase}"
        if decision is None:
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "no_look:smart_drop_blackout",
                active_deck=active,
                role="smart_drop_blackout",
                role_key=blackout_key,
            )
            return

        look = str(getattr(decision, "look", ""))
        scene_ref = self._sanitize_led_scene_ref(getattr(decision, "scene_ref", ""))
        decision_reason = str(getattr(decision, "reason", ""))
        try:
            accepted = bool(self._led_scene_adapter.trigger(decision))
        except Exception as exc:
            self._led_last_error = f"adapter_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "adapter_error",
                active_deck=active,
                role="smart_drop_blackout",
                role_key=blackout_key,
            )
            log.warning(
                "[RGB] adapter-error role=%s phase=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d err=%s",
                "smart_drop_blackout",
                phase,
                look or "-",
                scene_ref or "-",
                decision_reason or "-",
                blackout_key,
                active,
                type(exc).__name__,
            )
            return

        if accepted:
            self._led_trigger_count += 1
            self._led_automation_trigger_count += 1
            self._led_smart_drop_blackout_key = blackout_key
            self._led_last_error = ""
            self._led_last_look = look
            self._set_led_automation_gate_reason(
                "",
                active_deck=active,
                role="smart_drop_blackout",
                role_key=blackout_key,
            )
            log.info(
                "[RGB] trigger-accepted role=%s phase=%s look=%s scene_ref=%s reason=%s role_key=%s trigger_count=%d active_deck=%d",
                "smart_drop_blackout",
                phase,
                look or "-",
                scene_ref or "-",
                decision_reason or "-",
                blackout_key,
                self._led_automation_trigger_count,
                active,
            )
            return

        self._led_rejected_count += 1
        self._led_automation_gated_count += 1
        self._led_last_error = "adapter_rejected"
        self._set_led_automation_gate_reason(
            "adapter_rejected",
            active_deck=active,
            role="smart_drop_blackout",
            role_key=blackout_key,
        )
        log.warning(
            "[RGB] adapter-rejected role=%s phase=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d",
            "smart_drop_blackout",
            phase,
            look or "-",
            scene_ref or "-",
            decision_reason or "-",
            blackout_key,
            active,
        )

    def _dispatch_led_automation(
        self,
        *,
        active: int,
        d: DeckState,
        sp_state: SmartPhrasingState,
        position_stale: bool = False,
    ) -> None:
        if self._led_look_director is None or self._led_scene_adapter is None:
            self._gate_led_automation("not_configured", active_deck=active)
            return
        if not self._led_enabled_latch:
            self._gate_led_automation("disabled", active_deck=active)
            return
        if not self._led_automation_enabled_latch:
            self._gate_led_automation("automation_disabled", active_deck=active)
            return
        if self._led_emergency_blackout:
            self._gate_led_automation("emergency_blackout", active_deck=active)
            return
        if not d.playing or not d.meta.filepath:
            self._gate_led_automation("not_ready", active_deck=active)
            return
        if position_stale:
            self._gate_led_automation("position_stale", active_deck=active)
            return

        if self._led_manual_override:
            self._gate_led_automation("manual_override", active_deck=active, rt_permitted=True)
            return
        scripted_led_mode = bool(
            d.scripted_id
            and self._os.lighting_mode == "scripted"
            and self._led_scripted_mode_automation_latch
        )
        if d.scripted_id and not self._led_scripted_mode_automation_latch:
            self._gate_led_automation("scripted_mode", active_deck=active, rt_permitted=True)
            return

        if self._os.lighting_mode != "autoloop" and not scripted_led_mode:
            self._gate_led_automation("not_autoloop", active_deck=active)
            return
        # NOTE: LED automation is intentionally NOT gated on the SoundSwitch
        # autoloop *arm* completion. Govee looks are a separate path from SS
        # scenes, so a freshly-playing track lights immediately instead of
        # waiting for the SS arm (which only completes on a phrase boundary).
        # The laser director keeps its own autoloop_ready coupling separately.

        self._led_rt_permitted = True
        self._led_last_idle_role_key = ""
        if sp_state.smart_drop_crossing:
            # Pre-drop blackout may already be active; at the crossing beat the
            # state-aware LED role resolver decides whether this is an impact or
            # an immediate post-drop continuation.
            self._led_smart_drop_blackout_key = ""
        elif self._led_should_smart_drop_blackout(sp_state):
            self._dispatch_led_smart_drop_blackout(
                active=active,
                d=d,
                sp_state=sp_state,
                phase="pre_drop",
            )
            return

        # WI-2: advance the phrase latch before building role_key so the seq is
        # current when groove/ambient/post_drop embed it into their marker.
        if self._phrase_monotonic_enabled:
            self._advance_led_phrase_latch(sp_state)

        role = self._led_role_from_smart_phrasing(sp_state, mutate=True)
        original_role = role
        role = self._led_effective_role_for_dispatch(role, scripted=scripted_led_mode)
        role_key = self._led_automation_role_key(active, d, sp_state, original_role)
        if role_key == self._led_last_auto_role_key:
            return

        # M1b WI-5: structured section/cycle published by the role_key builder.
        section_id, cycle = self._led_last_section_cycle

        # M1b WI-1/WI-5: advance the color engine's journey state.  Guarded so a
        # missing/disabled engine is a complete no-op, and any engine exception
        # is swallowed (behave as engine-off for this tick — never crash dispatch).
        engine = self._led_color_engine
        if engine is not None and engine.enabled:
            try:
                engine.begin_dispatch(
                    active_deck=active,
                    load_gen=d.load_gen,
                    content_id=str(d.meta.content_id or ""),
                    filepath=str(d.meta.filepath or ""),
                    role=role,
                    section_id=section_id,
                    cycle=cycle,
                )
            except Exception as exc:
                self._led_last_error = f"color_engine_error:{type(exc).__name__}"

        context = LEDContext(
            role=role,
            manual_look=None,
            emergency_blackout=False,
            active_deck=active,
            playing=d.playing,
            lighting_mode=self._os.lighting_mode,
            scripted_id=d.scripted_id,
            diy_eligible=(
                engine.diy_eligible
                if (engine is not None and engine.enabled)
                else None
            ),
        )
        decision = None
        if role == "drop":
            decision = self._consume_led_committed_drop_decision(sp_state)
        try:
            if decision is None:
                decision = self._led_look_director.tick(context)
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "director_error",
                active_deck=active,
                role=role,
                role_key=role_key,
            )
            log.warning(
                "[RGB] director-error role=%s role_key=%s active_deck=%d err=%s",
                role,
                role_key,
                active,
                type(exc).__name__,
            )
            self._led_last_auto_role_key = role_key
            return

        self._led_last_auto_role_key = role_key
        self._led_last_event = f"automation:{role}"
        if decision is None:
            self._led_automation_gated_count += 1
            no_look_reason = f"no_look:{role}"
            self._set_led_automation_gate_reason(
                no_look_reason,
                active_deck=active,
                role=role,
                role_key=role_key,
            )
            log.info(
                "[RGB] no-look role=%s role_key=%s reason=%s active_deck=%d",
                role,
                role_key,
                no_look_reason,
                active,
            )
            return

        # M1b WI-5: inject the engine-resolved color into the finalized decision
        # (merge, never replace — preserves sync_mode/beat_division and any other
        # static params).  Exempt/baked looks and disabled engine inject nothing.
        # Any engine error leaves the decision unmodified (engine-off behavior).
        if engine is not None and engine.enabled:
            try:
                scene_ref_for_multi = str(getattr(decision, "scene_ref", ""))
                slot_based = scene_ref_for_multi in SLOT_EFFECTS
                
                if slot_based:
                    computed = engine.resolve_slot_colors(
                        role=role,
                        section_id=section_id,
                        cycle=cycle,
                        look_name=decision.look,
                        color_source=getattr(decision, "color_source", "engine"),
                        slot_count=MAX_SLOTS,
                    )
                    if computed:
                        palette_name = engine.snapshot().get("current_palette", "")
                        slot_colors = computed.get("slot_colors", [])
                        slot_count = len(slot_colors)
                        if slot_count >= 6:
                            first_rgb = tuple(slot_colors[0])
                            last_grad = tuple(slot_colors[4])
                            slot5_white = (tuple(slot_colors[5]) == (255, 255, 255))
                            log_msg = f"first={first_rgb} last_grad={last_grad} slot5_white={slot5_white}"
                        else:
                            log_msg = f"slot_colors={slot_count}"
                        
                        log.info(
                            "[RGB] color-inject look=%s palette=%s %s role=%s role_key=%s",
                            decision.look,
                            palette_name,
                            log_msg,
                            role,
                            role_key,
                        )
                        decision = replace(
                            decision,
                            params={**decision.params, **computed},
                        )
                else:
                    multi = "color_a" in REALTIME_EFFECT_PARAM_KEYS.get(
                        scene_ref_for_multi, frozenset()
                    )
                    computed = engine.resolve_color(
                        role=role,
                        section_id=section_id,
                        cycle=cycle,
                        look_name=decision.look,
                        color_source=getattr(decision, "color_source", "engine"),
                        multi=multi,
                    )
                    if computed:
                        palette_name = engine.snapshot().get("current_palette", "")
                        log.info(
                            "[RGB] color-inject look=%s palette=%s color=%s role=%s role_key=%s",
                            decision.look,
                            palette_name,
                            computed.get("color"),
                            role,
                            role_key,
                        )
                        decision = replace(
                            decision,
                            params={**decision.params, **computed},
                        )
            except Exception as exc:
                self._led_last_error = f"color_engine_error:{type(exc).__name__}"

        look = str(getattr(decision, "look", ""))
        scene_ref = self._sanitize_led_scene_ref(getattr(decision, "scene_ref", ""))
        decision_reason = str(getattr(decision, "reason", ""))
        try:
            accepted = bool(self._led_scene_adapter.trigger(decision))
        except Exception as exc:
            self._led_last_error = f"adapter_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "adapter_error",
                active_deck=active,
                role=role,
                role_key=role_key,
            )
            log.warning(
                "[RGB] adapter-error role=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d err=%s",
                role,
                look,
                scene_ref or "-",
                decision_reason or "-",
                role_key,
                active,
                type(exc).__name__,
            )
            return

        if accepted:
            self._led_trigger_count += 1
            self._led_automation_trigger_count += 1
            self._led_last_error = ""
            self._led_last_look = look
            self._led_smart_drop_blackout_key = ""
            if role == "drop":
                self._led_note_drop_decision_accepted(decision, sp_state)
            self._set_led_automation_gate_reason(
                "",
                active_deck=active,
                role=role,
                role_key=role_key,
            )
            log.info(
                "[RGB] trigger-accepted role=%s look=%s scene_ref=%s reason=%s role_key=%s trigger_count=%d active_deck=%d",
                role,
                look or "-",
                scene_ref or "-",
                decision_reason or "-",
                role_key,
                self._led_automation_trigger_count,
                active,
            )
            return

        self._led_rejected_count += 1
        self._led_automation_gated_count += 1
        self._led_last_error = "adapter_rejected"
        self._set_led_automation_gate_reason(
            "adapter_rejected",
            active_deck=active,
            role=role,
            role_key=role_key,
        )
        log.warning(
            "[RGB] adapter-rejected role=%s look=%s scene_ref=%s reason=%s role_key=%s active_deck=%d",
            role,
            look or "-",
            scene_ref or "-",
            decision_reason or "-",
            role_key,
            active,
        )

    def _dispatch_led_idle_ambient(
        self,
        *,
        active: int,
        d: DeckState,
        reason: str,
    ) -> None:
        self._led_rt_permitted = False
        self._led_smart_drop_blackout_key = ""

        role_key = f"{active}:{d.load_gen}:idle_ambient:{bool(d.meta.filepath)}"
        if self._led_look_director is None or self._led_scene_adapter is None:
            self._gate_led_automation("not_configured", active_deck=active, role="ambient")
            return
        if not self._led_enabled_latch:
            self._gate_led_automation("disabled", active_deck=active, role="ambient")
            return
        if not self._led_automation_enabled_latch:
            self._gate_led_automation("automation_disabled", active_deck=active, role="ambient")
            return
        if self._led_emergency_blackout:
            self._gate_led_automation("emergency_blackout", active_deck=active, role="ambient")
            return
        if self._led_manual_override:
            self._gate_led_automation("manual_override", active_deck=active, role="ambient")
            return
        if role_key == self._led_last_idle_role_key:
            return

        if self._led_color_engine is not None:
            self._led_color_engine.reset_fade_memory()

        context = LEDContext(
            role="ambient",
            manual_look=None,
            emergency_blackout=False,
            active_deck=active,
            playing=False,
            lighting_mode="idle",
            scripted_id=d.scripted_id,
        )
        try:
            decision = self._led_look_director.tick(context)
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "director_error",
                active_deck=active,
                role="ambient",
                role_key=role_key,
            )
            self._led_last_auto_role_key = role_key
            self._led_last_idle_role_key = role_key
            return

        self._led_last_auto_role_key = role_key
        self._led_last_idle_role_key = role_key
        self._led_last_event = f"automation:idle_ambient:{reason}"
        if decision is None:
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "no_look:ambient",
                active_deck=active,
                role="ambient",
                role_key=role_key,
            )
            return

        look = str(getattr(decision, "look", ""))
        try:
            accepted = bool(self._led_scene_adapter.trigger(decision))
        except Exception as exc:
            self._led_last_error = f"adapter_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            self._led_automation_gated_count += 1
            self._set_led_automation_gate_reason(
                "adapter_error",
                active_deck=active,
                role="ambient",
                role_key=role_key,
            )
            log.warning(
                "[RGB] adapter-error role=ambient look=%s reason=%s role_key=%s active_deck=%d err=%s",
                look or "-",
                reason,
                role_key,
                active,
                type(exc).__name__,
            )
            return

        if accepted:
            self._led_trigger_count += 1
            self._led_automation_trigger_count += 1
            self._led_last_error = ""
            self._led_last_look = look
            self._set_led_automation_gate_reason(
                "",
                active_deck=active,
                role="ambient",
                role_key=role_key,
            )
            log.info(
                "[RGB] trigger-accepted role=ambient look=%s reason=%s role_key=%s trigger_count=%d active_deck=%d",
                look or "-",
                reason,
                role_key,
                self._led_automation_trigger_count,
                active,
            )
            return

        self._led_rejected_count += 1
        self._led_automation_gated_count += 1
        self._led_last_error = "adapter_rejected"
        self._set_led_automation_gate_reason(
            "adapter_rejected",
            active_deck=active,
            role="ambient",
            role_key=role_key,
        )

    def _gate_led_automation(
        self,
        reason: str,
        *,
        active_deck: Optional[int] = None,
        role: str = "",
        role_key: str = "",
        rt_permitted: bool = False,
    ) -> None:
        self._led_rt_permitted = rt_permitted
        if reason != self._led_automation_gate_reason:
            self._led_automation_gated_count += 1
            if self._led_color_engine is not None and reason in ("emergency_blackout", "manual_override"):
                self._led_color_engine.reset_fade_memory()
        self._set_led_automation_gate_reason(
            reason,
            active_deck=active_deck,
            role=role,
            role_key=role_key,
        )
        self._led_last_auto_role_key = ""

    def _led_should_smart_drop_blackout(self, sp_state: SmartPhrasingState) -> bool:
        """True when Govee should be in pre-drop blackout for Smart Drop."""
        return bool(
            sp_state.transition_mask_arm_latched
            or sp_state.transition_mask_should_arm
            or sp_state.transition_window_active
        )

    def _preview_led_drop_decision(
        self,
        sp_state: SmartPhrasingState | None = None,
    ) -> Any:
        if sp_state is not None:
            return self._led_drop_decision_for_anchor(sp_state, commit=False)
        return self._preview_led_decision_for_role("drop")

    def _preview_led_decision_for_role(self, role: str) -> Any:
        preview_role = getattr(self._led_look_director, "preview_role", None)
        if not callable(preview_role):
            return None
        try:
            return preview_role(role)
        except Exception:
            return None

    def _led_drop_anchor_for_blackout(
        self,
        sp_state: SmartPhrasingState,
    ) -> float | None:
        if sp_state.active_drop_beat is not None:
            return float(sp_state.active_drop_beat)
        if sp_state.next_smart_drop_beat is not None:
            return float(sp_state.next_smart_drop_beat)
        return self._led_drop_marker_anchor(sp_state)

    def _led_same_drop_anchor(
        self,
        left: float | None,
        right: float | None,
    ) -> bool:
        if left is None or right is None:
            return False
        return float(left) == float(right)

    def _led_drop_decision_for_anchor(
        self,
        sp_state: SmartPhrasingState,
        *,
        commit: bool,
    ) -> Any:
        anchor = self._led_drop_anchor_for_blackout(sp_state)
        if (
            self._led_same_drop_anchor(anchor, self._led_committed_drop_anchor_beat)
            and self._led_committed_drop_decision is not None
        ):
            return self._led_committed_drop_decision
        if not commit or anchor is None:
            return self._preview_led_decision_for_role("drop")

        commit_role = getattr(self._led_look_director, "commit_role", None)
        decision = None
        if callable(commit_role):
            try:
                decision = commit_role("drop")
            except Exception:
                decision = None
        if decision is None:
            decision = self._preview_led_decision_for_role("drop")
        if decision is not None:
            self._led_committed_drop_anchor_beat = float(anchor)
            self._led_committed_drop_decision = decision
        return decision

    def _consume_led_committed_drop_decision(
        self,
        sp_state: SmartPhrasingState,
    ) -> Any:
        anchor = self._led_drop_anchor_for_blackout(sp_state)
        if not self._led_same_drop_anchor(anchor, self._led_committed_drop_anchor_beat):
            return None
        decision = self._led_committed_drop_decision
        self._led_committed_drop_anchor_beat = None
        self._led_committed_drop_decision = None
        return decision

    def _led_effective_role_for_dispatch(
        self,
        role: str,
        *,
        scripted: bool = False,
    ) -> str:
        if not scripted:
            return role
        return self._led_scripted_role_map.get(role, self._led_scripted_default_role)

    def _led_role_has_mapped_look(self, role: str) -> bool:
        has_role_look = getattr(self._led_look_director, "has_role_look", None)
        if callable(has_role_look):
            try:
                return bool(has_role_look(role))
            except Exception:
                return False
        return self._preview_led_decision_for_role(role) is not None

    def _led_role_from_smart_phrasing(
        self,
        sp_state: SmartPhrasingState,
        *,
        mutate: bool = False,
    ) -> str:
        if mutate and self._led_drop_lifecycle_should_clear(sp_state):
            self._clear_led_drop_lifecycle()

        drop_anchor = self._led_drop_marker_anchor(sp_state)
        if drop_anchor is not None:
            if self._led_drop_impact_allowed(sp_state):
                if mutate:
                    self._led_arm_drop_lifecycle(drop_anchor)
                return "drop"
            if mutate and self._led_first_drop_anchor_beat is None:
                self._led_first_drop_anchor_beat = drop_anchor
            return "post_drop"

        if sp_state.smart_breakdown_active or sp_state.breakdown_start_crossing:
            return "breakdown"
        if sp_state.transition_window_active:
            return "pre_drop"
        if self._led_buildup_active(sp_state):
            return "buildup"

        if sp_state.current_phrase_is_chorus or sp_state.smart_post_drop_active:
            abs_beat = self._led_abs_beat(sp_state)
            if (
                abs_beat is not None
                and self._led_drop_impact_until_beat is not None
                and abs_beat < self._led_drop_impact_until_beat
            ):
                return "drop"
            return "post_drop"
        if sp_state.current_phrase_is_low:
            return "breakdown"
        return "groove"

    def _led_buildup_active(self, sp_state: SmartPhrasingState) -> bool:
        """Match laser_director: buildup only in up phrase within lookahead of next drop."""
        beats_to_next_drop = sp_state.beats_to_next_drop
        if beats_to_next_drop is None or beats_to_next_drop <= 0:
            return False
        if beats_to_next_drop > self._sp_phrase_lookahead:
            return False
        return bool(
            sp_state.current_phrase_is_up
            and not sp_state.current_phrase_is_chorus
        )

    def _led_drop_marker_anchor(self, sp_state: SmartPhrasingState) -> float | None:
        if sp_state.current_phrase_is_chorus and sp_state.phrase_start_crossing:
            if sp_state.current_phrase_start_beat is not None:
                return float(sp_state.current_phrase_start_beat)
        if sp_state.smart_drop_crossing:
            if sp_state.active_drop_beat is not None:
                return float(sp_state.active_drop_beat)
            return self._led_abs_beat(sp_state)
        return None

    def _led_drop_impact_allowed(self, sp_state: SmartPhrasingState) -> bool:
        previous = str(sp_state.previous_phrase_label or "other")
        if previous in _LED_DROP_IMPACT_PREDECESSORS:
            return True
        if sp_state.smart_drop_crossing:
            # Fallback smart-drop tracks may not have an explicit chorus marker;
            # keep the impact when the current phrase context is already Up/Low.
            current = str(sp_state.current_phrase_label or "other")
            if current in _LED_DROP_IMPACT_PREDECESSORS:
                return True
        if previous == "chorus":
            # Once a chorus/drop lifecycle exists, allow up to two
            # Chorus->Chorus impacts before settling into post_drop. This also
            # covers tracks whose first chorus marker only anchored post_drop
            # and did not itself fire an impact.
            if (
                self._led_first_drop_anchor_beat is not None
                and self._led_drop_impact_count < LED_MAX_DROP_IMPACTS
            ):
                return True
        return False

    def _led_drop_lifecycle_should_clear(self, sp_state: SmartPhrasingState) -> bool:
        if sp_state.smart_drop_crossing:
            return False
        if sp_state.current_phrase_is_chorus or sp_state.smart_post_drop_active:
            return False
        return self._led_first_drop_anchor_beat is not None

    def _led_arm_drop_lifecycle(self, anchor_beat: float) -> None:
        if self._led_first_drop_anchor_beat is None:
            self._led_first_drop_anchor_beat = float(anchor_beat)
        self._led_drop_impact_until_beat = (
            float(anchor_beat) + LED_DEFAULT_DROP_IMPACT_BEATS
        )
        self._led_drop_impact_count += 1
        self._led_active_drop_look = ""

    def _led_note_drop_decision_accepted(
        self,
        decision: Any,
        sp_state: SmartPhrasingState,
    ) -> None:
        look = str(getattr(decision, "look", "") or "")
        anchor = self._led_drop_marker_anchor(sp_state)
        if anchor is None:
            anchor = self._led_first_drop_anchor_beat
        if anchor is None:
            anchor = self._led_abs_beat(sp_state)
        if anchor is None:
            return
        duration = LED_DEFAULT_DROP_IMPACT_BEATS
        duration_fn = getattr(self._led_look_director, "drop_duration_beats", None)
        if callable(duration_fn):
            try:
                duration = float(duration_fn(look))
            except Exception:
                duration = LED_DEFAULT_DROP_IMPACT_BEATS
        duration = max(0.001, duration)
        if self._led_first_drop_anchor_beat is None:
            self._led_first_drop_anchor_beat = float(anchor)
        self._led_drop_impact_until_beat = float(anchor) + duration
        self._led_active_drop_look = look
        self._led_drop_look_fired_anchor = float(anchor)

    def _clear_led_drop_lifecycle(self) -> None:
        self._led_first_drop_anchor_beat = None
        self._led_drop_impact_until_beat = None
        self._led_drop_impact_count = 0
        self._led_active_drop_look = ""
        self._led_committed_drop_anchor_beat = None
        self._led_committed_drop_decision = None
        self._led_drop_look_fired_anchor = None
        clear_queued = getattr(
            self._led_look_director, "clear_queued_post_drop", None
        )
        if callable(clear_queued):
            try:
                clear_queued()
            except Exception:
                pass

    def _led_abs_beat(self, sp_state: SmartPhrasingState) -> float | None:
        if sp_state.abs_beat is not None:
            return float(sp_state.abs_beat)
        if (
            sp_state.current_phrase_start_beat is not None
            and sp_state.beats_into_phrase is not None
        ):
            return float(sp_state.current_phrase_start_beat) + float(sp_state.beats_into_phrase)
        if sp_state.active_drop_beat is not None:
            return float(sp_state.active_drop_beat)
        return None

    def _led_post_drop_cycle_beats(self) -> float:
        cycle_fn = getattr(self._led_look_director, "post_drop_cycle_beats", None)
        if callable(cycle_fn):
            try:
                return max(0.001, float(cycle_fn()))
            except Exception:
                pass
        return LED_DEFAULT_POST_DROP_CYCLE_BEATS

    # ── WI-1/2 phrase latch helpers ───────────────────────────────────────────

    def _reset_led_phrase_latch(self, reason: str) -> None:
        """Clear the phrase-start latch on a genuine backward seek.

        Called by the WI-1 monotonic clamp when a real seek (delta >=
        LED_BACKSTEP_SEEK_BEATS beats backward) is detected.  Bumps the
        reset counter for WI-8 observability.
        """
        self._led_phrase_committed_start = None
        self._led_phrase_latch_reset_count += 1
        log.debug("[RGB] phrase-latch reset reason=%s", reason)

    def _clamp_led_beat(self, abs_beat_pos: float, active: int, load_gen: int) -> float:
        """WI-1 monotonic LED/phrasing playhead clamp.
        
        Sub-beat backward jitter (delta in (-LED_BACKSTEP_SEEK_BEATS, 0)) is held to
        the previous value so phrasing never crosses a segment boundary backwards.
        A backstep >= LED_BACKSTEP_SEEK_BEATS is a real seek/cue/reload: accept it and
        reset the phrase latch. Keyed on (active, load_gen) so a reload/deck-switch
        resets cleanly. No-op (pass-through) when the flag is off.
        """
        key = (active, load_gen)
        if key != self._led_beat_monotonic_key:
            self._led_beat_monotonic_key = key
            self._led_beat_monotonic = abs_beat_pos
            return abs_beat_pos
        prev = self._led_beat_monotonic
        if self._phrase_monotonic_enabled and prev is not None:
            delta = abs_beat_pos - prev
            if -LED_BACKSTEP_SEEK_BEATS < delta < 0.0:
                log.debug("[RGB] beat-clamp deck=%d abs=%.3f→%.3f delta=%.4f", active, abs_beat_pos, prev, delta)
                abs_beat_pos = prev
            elif delta <= -LED_BACKSTEP_SEEK_BEATS:
                log.debug("[RGB] beat-seek deck=%d abs=%.3f→%.3f delta=%.4f", active, prev, abs_beat_pos, delta)
                self._reset_led_phrase_latch("seek")
        self._led_beat_monotonic = abs_beat_pos
        return abs_beat_pos

    def _advance_led_phrase_latch(self, sp_state: SmartPhrasingState) -> None:
        """Advance the phrase-seq latch on a forward phrase change. WI-1 guarantees
        abs_beat (and thus current_phrase_start_beat) is monotonic, so this fires
        exactly once per phrase entry. Never retreats; retreat only via
        _reset_led_phrase_latch on a real seek."""
        start = sp_state.current_phrase_start_beat
        if start is None:
            return
        committed = self._led_phrase_committed_start
        if committed is None or start > committed:
            self._led_phrase_committed_start = start
            self._led_phrase_seq += 1
            log.debug("[RGB] phrase-latch advance seq=%d start=%.3f", self._led_phrase_seq, start)

    def _led_automation_role_key(
        self,
        active: int,
        d: DeckState,
        sp_state: SmartPhrasingState,
        role: str,
    ) -> str:
        marker = ""
        # M1b WI-2: structured section/cycle derived from the SAME source
        # expressions that build `marker` (never by parsing the marker string).
        section_id = ""
        cycle = 0
        if role == "drop":
            anchor = self._led_drop_marker_anchor(sp_state)
            if anchor is None:
                anchor = self._led_first_drop_anchor_beat
            if anchor is not None:
                marker = f"{float(anchor):.3f}"
        elif role == "post_drop":
            anchor = self._led_first_drop_anchor_beat
            if anchor is None:
                anchor = (
                    sp_state.current_phrase_start_beat
                    if sp_state.current_phrase_start_beat is not None
                    else sp_state.active_drop_beat
                )
            if anchor is not None:
                abs_beat = self._led_abs_beat(sp_state)
                elapsed = max(0.0, float(abs_beat or anchor) - float(anchor))
                cycle = int(elapsed // self._led_post_drop_cycle_beats())
                if self._phrase_monotonic_enabled:
                    # WI-2: embed phrase_seq instead of raw anchor to prevent
                    # A→B→A oscillation from different phrase start reads.
                    marker = f"seq{self._led_phrase_seq}:c{cycle}"
                    section_id = f"seq{self._led_phrase_seq}"
                else:
                    marker = f"{float(anchor):.3f}:c{cycle}"
                    section_id = f"{float(anchor):.3f}"
            else:
                marker = str(sp_state.current_phrase_label)
                section_id = marker
        elif role in {"buildup", "pre_drop"} and sp_state.next_smart_drop_beat is not None:
            marker = f"{sp_state.next_smart_drop_beat:.3f}"
        elif role == "breakdown" and sp_state.breakdown_restore_beat is not None:
            marker = f"{sp_state.breakdown_restore_beat:.3f}"
        elif role == "groove":
            abs_beat = self._led_abs_beat(sp_state)
            if self._phrase_monotonic_enabled:
                # WI-2: embed monotonically-advancing seq instead of raw
                # current_phrase_start_beat.  The cycle still uses abs_beat
                # (which is itself clamped by WI-1) so a 112→80→112 wobble
                # maps to a single seq and the key does not change.
                if abs_beat is not None:
                    # When the latch hasn't been advanced yet (committed_start is
                    # None), fall back to current_phrase_start_beat so the cycle
                    # is still computed correctly.  The seq already disambiguates
                    # which phrase we are in; the committed_start only anchors the
                    # intra-phrase cycle offset.
                    committed = self._led_phrase_committed_start
                    if committed is None:
                        committed = sp_state.current_phrase_start_beat
                    elapsed_from_seq = max(
                        0.0,
                        float(abs_beat) - float(committed or 0.0),
                    )
                    cycle = int(elapsed_from_seq // LED_DEFAULT_GROOVE_CYCLE_BEATS)
                    marker = (
                        f"{sp_state.current_phrase_label}:"
                        f"seq{self._led_phrase_seq}:c{cycle}"
                    )
                    section_id = (
                        f"{sp_state.current_phrase_label}:"
                        f"seq{self._led_phrase_seq}"
                    )
                else:
                    marker = str(sp_state.current_phrase_label)
                    section_id = marker
            else:
                anchor = sp_state.current_phrase_start_beat
                if anchor is not None and abs_beat is not None:
                    elapsed = max(0.0, float(abs_beat) - float(anchor))
                    cycle = int(elapsed // LED_DEFAULT_GROOVE_CYCLE_BEATS)
                    marker = (
                        f"{sp_state.current_phrase_label}:"
                        f"{float(anchor):.3f}:c{cycle}"
                    )
                    section_id = (
                        f"{sp_state.current_phrase_label}:"
                        f"{float(anchor):.3f}"
                    )
                else:
                    marker = str(sp_state.current_phrase_label)
                    section_id = marker
        elif role == "ambient":
            if self._phrase_monotonic_enabled:
                # WI-2: use phrase_seq for ambient too — same class of oscillation risk
                marker = f"{sp_state.current_phrase_label}:seq{self._led_phrase_seq}"
            else:
                marker = str(sp_state.current_phrase_label)
        # M1b WI-2: publish structured section/cycle for the color engine.
        # `section_id or marker` keeps the unlisted branches (drop, buildup,
        # pre_drop, breakdown, ambient) on section_id = marker / cycle = 0.
        self._led_last_section_cycle = (section_id or marker, cycle)
        return f"{active}:{d.load_gen}:{role}:{marker}"

    # ── Deck switch ───────────────────────────────────────────────────────────

    def _on_master_changed(self, new_deck: int, source: str) -> None:
        old_deck = self._os.active_deck
        if new_deck == old_deck:
            return
        log.info("[SM] switch  %d→%d  src=%s", old_deck, new_deck, source)
        LOG.stats.record_transition(new_deck, "master")
        # OSC race fix: /bridge/active_deck can arrive after /bridge/track_loaded,
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
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""
        self._led_smart_drop_blackout_key = ""
        self._clear_led_drop_lifecycle()
        self._clear_smart_rearm_state()
        self._autoloop.clear_arm_phrase_lock()
        self._autoloop.clear_live_bpm_follow()
        self._autoloop.clear_tempo_relock()
        self._autoloop.clear_pending_master_phrase_arm()
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="master_changed")
        if (
            self._personality_eligible_deck.get(new_deck, False)
            and new_d.meta.content_id
        ):
            self._resolve_personality_for_deck(
                new_deck,
                new_d.meta,
                trigger="master_changed",
            )

    # ── Track load → lsof trigger ─────────────────────────────────────────────

    def _on_track_loaded(self, deck: int, title: str, ev: BridgeEvent) -> None:
        d = self._deck[deck]
        d.meta.clear()
        d.scripted_id = 0
        self._personality_eligible_deck[deck] = False
        d.load_gen += 1
        self._loaded_anlz_path.pop(deck, None)
        if deck == self._os.active_deck:
            self._clear_led_drop_lifecycle()
            self._clear_smart_rearm_state()
            self._autoloop.clear_arm_phrase_lock()
            self._autoloop.clear_live_bpm_follow()
            self._autoloop.clear_tempo_relock()
            self._autoloop.clear_pending_master_phrase_arm()
            if self._laser_executor is not None:
                self._laser_executor.reset_runtime_state(reason="active_track_loaded")
            if self._led_look_director is not None:
                self._led_look_director.reset_for_track()
        d.track_title_hint = title
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
                self._loaded_anlz_path[deck] = (anlz_path, d.load_gen)
                self._start_anlz_worker(
                    anlz_path,
                    deck,
                    d.load_gen,
                    wide_window=self._wide_window_enable,
                )
        else:
            other = 3 - deck
            other_path = self._deck[other].meta.filepath
            # Fire both: lsof (fast, uses track length) and title-based DB lookup
            # (reliable fallback when memory track_length=0 prevents lsof from matching)
            self._resolver.resolve_async(deck, d.load_gen, other_path, trace_id=trace_id)
            if title:
                self._resolver.resolve_by_title(deck, d.load_gen, title, trace_id=trace_id)

    def _start_anlz_worker(
        self,
        anlz_path: str,
        deck: int,
        load_gen: int,
        *,
        audio_filepath: str = "",
        spectral_enabled: bool = False,
        wide_window: bool = False,
    ) -> None:
        eq = self._eq
        source = "anlz_spectral" if spectral_enabled else "anlz"

        def _anlz_worker(path: str, bridge_deck: int, gen: int) -> None:
            try:
                result = _read_runtime_anlz_data(
                    path,
                    audio_filepath=audio_filepath,
                    spectral_enabled=spectral_enabled,
                    wide_window=wide_window,
                )
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
                        "source": source,
                    },
                    source=source,
                ))
            except queue.Full:
                log.warning("[SM] queue-full  event=anlz-data  deck=%d", bridge_deck)

        threading.Thread(
            target=_anlz_worker,
            args=(anlz_path, deck, load_gen),
            daemon=True,
            name=f"{source}-drop-{deck}",
        ).start()

    def attach_resolver(self, resolver) -> None:  # type: ignore[type-arg]
        self._resolver = resolver

    def attach_personality_resolver(self, resolver: PersonalityResolver) -> None:
        self._personality_resolver = resolver

    def attach_personality_playlist_cache(self, cache: PlaylistCache) -> None:
        self._personality_playlist_cache = cache

    def attach_laser_personality_provider(
        self,
        provider: Optional[Callable[[str], Optional[LaserPersonality]]],
    ) -> None:
        self._laser_personality_provider = provider

    def get_last_applied_personality(self) -> Optional[LaserPersonality]:
        return self._last_applied_personality

    def _recache_initial_personality_timing(self) -> None:
        director = self._laser_director
        provider = self._laser_personality_provider
        get_personality = getattr(director, "get_personality", None)
        if provider is None or not callable(get_personality):
            return
        personality = provider(str(get_personality()))
        if personality is not None:
            self._recache_personality_timing(personality)

    def _apply_personality_change(
        self,
        name: str,
        personality: LaserPersonality,
    ) -> None:
        if self._laser_director is not None:
            self._laser_director.set_personality(name)
            self._laser_director.set_personality_config(personality)
        if self._laser_executor is not None:
            self._laser_executor.set_personality(personality)
        self._recache_personality_timing(personality)
        self._last_applied_personality = personality

    def _recache_personality_timing(
        self,
        personality: Optional[LaserPersonality],
    ) -> None:
        self._active_personality_for_timing = personality
        if personality is None:
            self._sp_drop_window = float(SMART_DROP_LOOKAHEAD_BEATS)
            self._sp_transition_window = float(SMART_DROP_LOOKAHEAD_BEATS)
            self._sp_post_drop = 8.0
            self._sp_breakdown_default_restore = SMART_BREAKDOWN_DEFAULT_DURATION_BEATS
            self._sp_phrase_lookahead = 32.0
        else:
            self._sp_drop_window = float(personality.pre_drop_blackout_beats)
            self._sp_transition_window = float(personality.pre_drop_blackout_beats)
            self._sp_post_drop = float(personality.post_drop_hold_beats)
            self._sp_breakdown_default_restore = int(
                personality.breakdown_default_restore_beats
            )
            self._sp_phrase_lookahead = float(personality.buildup_lookahead_beats)
        for deck in (1, 2):
            self._clear_phrase_segment_cache(deck)

    def _resolve_personality_for_deck(
        self,
        deck: int,
        meta: TrackMetadata,
        *,
        trigger: str = "filepath_resolved",
    ) -> None:
        resolver = self._personality_resolver
        director = self._laser_director
        provider = self._laser_personality_provider
        if resolver is None or director is None or provider is None:
            return
        if deck != self._os.active_deck:
            log.debug(
                "[PERSONALITY] skip-resolve deck=%d trigger=%s reason=not-master active=%d",
                deck,
                trigger,
                self._os.active_deck,
            )
            return

        content_id = str(meta.content_id or "")
        cache = self._personality_playlist_cache
        playlists: frozenset[str]
        if cache is None:
            playlists = frozenset()
        elif not content_id:
            playlists = frozenset()
        else:
            cached = cache.get(content_id)
            if cached is None:
                cache.refresh()
                cached = cache.get(content_id)
            playlists = cached or frozenset()

        resolution = resolver.resolve(playlists=playlists, bpm=meta.bpm)
        personality_cfg = provider(resolution.name)
        if personality_cfg is None:
            log.warning(
                "[PERSONALITY] deck=%d content_id=%r unresolved=%r reason=missing_config",
                deck,
                content_id,
                resolution.name,
            )
            return

        queue_change = getattr(director, "queue_personality_change", None)
        if callable(queue_change):
            queue_change(resolution.name, personality_cfg)
        # Timing drives SmartPhrasing + LED before phrase-boundary scene apply.
        self._recache_personality_timing(personality_cfg)

        mismatch = ""
        bpm_min = float(personality_cfg.bpm_band_min)
        bpm_max = float(personality_cfg.bpm_band_max)
        if (
            resolution.reason == "playlist_match"
            and meta.bpm > 0
            and not (bpm_min == 0.0 and bpm_max == 0.0)
            and not (bpm_min <= meta.bpm < bpm_max)
        ):
            mismatch = f" outside band {bpm_min:g}-{bpm_max:g}"

        matched = f' matched="{resolution.matched}"' if resolution.matched else ""
        reason = resolution.reason
        if reason == "default" and not resolution.matched:
            matched = " reason=bpm_no_match"
        log.info(
            '[PERSONALITY] deck=%d trigger=%s content_id=%r file="%s" -> %s '
            '(rule=%s%s, file_bpm=%g%s)',
            deck,
            trigger,
            content_id,
            bf.short(meta.filepath),
            resolution.name,
            reason,
            matched,
            meta.bpm,
            mismatch,
        )

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
        self._clear_phrase_segment_cache(deck)
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
        if self._spectral_enable:
            loaded_anlz = self._loaded_anlz_path.pop(deck, None)
            if loaded_anlz is not None:
                anlz_path, anlz_gen = loaded_anlz
                if anlz_gen == d.load_gen:
                    self._start_anlz_worker(
                        anlz_path,
                        deck,
                        d.load_gen,
                        audio_filepath=meta.filepath,
                        spectral_enabled=True,
                        wide_window=self._wide_window_enable,
                    )
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
                self._personality_eligible_deck[deck] = False
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
                self._personality_eligible_deck[deck] = True
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.SCRIPTED_CLEAR,
                        deck=deck,
                        source="filepath_resolved",
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=scripted-clear  deck=%d", deck)
                self._resolve_personality_for_deck(deck, meta)

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

        # Get current elapsed: prefer memory snap, otherwise use the push loop's
        # latest elapsed estimate when the DPU is unresolvable.
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
        self._sse.send_scripted_arm_phase0(deck)

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
        self._sse.send_scripted_arm_phase1(arm.deck, arm_meta, cur_active)
        self._log_status()

    def _arm_unscripted(self, deck: int) -> None:
        """Clear scripted state. Lighting machine re-evaluates next tick."""
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
            debounce_s = self._autoloop.idle_debounce_s
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
        d = self._deck[deck]
        self._os.last_arm_mono = time.monotonic()

        if mode == "scripted":
            self._led_last_auto_role_key = ""
            self._led_last_idle_role_key = ""
            self._led_smart_drop_blackout_key = ""
            self._clear_led_drop_lifecycle()
            self._clear_smart_rearm_state()
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            # Arm the scripted show. _arm_scripted is internally debounced (2 s)
            # so rapid pause/resume doesn't cause a full re-arm sequence.
            self._arm_scripted(deck, d.scripted_id)

        elif mode == "autoloop":
            self._clear_smart_rearm_state()
            self._pending_arm = None
            if (
                self._os.autoloop_arm_after_master_change
                and self._laser_executor is not None
                and self._laser_director is not None
                and self._laser_director.is_enabled()
            ):
                # Mask the transition: SS stays dark from the master switch until
                # the first phrase-relative re-fire (Task 4 releases this owner).
                self._laser_executor.hold_blackout_mask("master_switch")
            self._autoloop.arm_autoloop(
                deck,
                elapsed_ms,
                bpm,
                False,
            )

        elif mode == "idle":
            self._clear_smart_rearm_state()
            self._pending_arm = None
            self._os.last_armed_filepath = ""
            self._os.autoloop_arm_bpm = 0.0
            self._os.autoloop_arm_deck = 0
            self._os.last_autoloop_status_phrase_beat = 0
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            self._autoloop.clear_arm_phrase_lock()
            self._autoloop.clear_live_bpm_follow()
            self._autoloop.clear_tempo_relock()
            self._autoloop.clear_tempo_anchor()
            self._autoloop.clear_pending_master_phrase_arm()
            self._os.live_follow_generation += 1
            for dn in range(1, 5):
                self._out.send_deck_play(dn, "off")
                self._out._sub(f"deck {dn} loop", "off", verbose=True)
            for dn in range(1, 5):
                self._sse.send_deck_clear(dn)

    # ── Push loop ─────────────────────────────────────────────────────────────

    def _push_tick(self) -> None:
        """Wrapper: run the tick body, then drive the SoundSwitch pack output once.

        The body has multiple early returns, so the pack driver runs here (not inside
        the body) to guarantee exactly one drive per tick. If the body raises, submit a
        direct ZERO frame (NOT the normal driver, which would read possibly-partial
        state) so a crash can never retain non-zero DMX, then re-raise.
        """
        rt = self._pack_runtime
        try:
            self._push_tick_inner()
        except BaseException:
            if rt is not None and rt.active and rt.backend is not None:
                try:
                    rt.backend.submit_frame(_PACK_ZERO_FRAME)
                except Exception:
                    pass
            raise
        if rt is not None and rt.active:
            self._drive_pack_output()

    def set_pack_runtime(self, runtime: PackRuntime) -> None:
        """Atomically publish a new pack runtime bundle (command thread → push loop).

        A single attribute assignment; the push loop reads one reference per tick, so
        it never sees a mixed old/new runtime. All blocking work (load_pack, serial
        open/close, old-sender zero_and_stop) must already be done by the caller.
        """
        self._pack_runtime = runtime or DISABLED_PACK_RUNTIME

    def get_pack_status(self) -> dict[str, Any]:
        """Sanitized pack status for the runtime status surface (no paths/ports/etc.)."""
        rt = self._pack_runtime
        return rt.sanitized_status() if rt is not None else DISABLED_PACK_RUNTIME.sanitized_status()

    def _drive_pack_output(self) -> None:
        """T7c/T7e: drive the pack player from authoritative deck state; submit one
        CH1-CH19 frame. READ-ONLY w.r.t. DeckState; fail-safe to ZERO; never raises
        into the tick. Automatic base ZEROs on any non-happy-path (stop/stale/error/
        track-change/discontinuity) via clear_selection() so a held manual Static
        Override stands alone while idle. See
        docs/plans/active/soundswitch_t7c_pack_driver_spec.md."""
        rt = self._pack_runtime
        if rt is None or not rt.active:
            return
        player, backend, midi_input = rt.player, rt.backend, rt.midi_input
        try:
            active = self._os.active_deck
            d = self._deck[active]
            snap = self._cache.get(active)

            # 1. Controller masks + static overrides (in-memory snapshot; no I/O).
            if midi_input is not None:
                s = midi_input.snapshot()
                player.set_masks(blackout=bool(s.blackout_held), emergency=False)
                slot = s.held_static_slot
                if slot != self._pack_last_static_slot:
                    if slot is not None:
                        player.hold_static(int(slot))
                    elif self._pack_last_static_slot is not None:
                        player.release_static(int(self._pack_last_static_slot))
                    self._pack_last_static_slot = slot

            # 2. Derive the happy-path gate (fail-conservative; uncertain ⇒ ZERO base).
            load_key = (active, int(getattr(d, "load_gen", 0)))
            track_changed = (
                self._pack_last_load_gen is not None and load_key != self._pack_last_load_gen
            )
            self._pack_last_load_gen = load_key
            elapsed_ms = max(0, int(getattr(d, "elapsed_ms", 0) or 0))
            discont = (
                not track_changed
                and self._pack_last_elapsed_ms is not None
                and abs(elapsed_ms - self._pack_last_elapsed_ms) >= _PACK_SEEK_JUMP_MS
            )
            self._pack_last_elapsed_ms = elapsed_ms
            fresh = not (snap is None or snap.is_stale(MEM_STALE_S))
            playing = bool(getattr(d, "playing", False))
            ssid = getattr(getattr(d, "meta", None), "soundswitch_id", "") or ""
            metadata_ready = _pack_normalize_id(ssid) is not None

            # 3. Automatic base: scripted only on the full happy path; else clear it so
            #    a held static stands alone and no stale frame is retained.
            #    Manual-static policy: a held Static Override is operator-controlled via
            #    the (independent) MIDI controller, so it stays visible during ANY
            #    non-happy-path here — idle/stop AND stale/error/track-change/
            #    discontinuity. It loses only to blackout/emergency (set_masks -> render
            #    ZERO above) and to pack-disabled/shutdown (driver inert / sender ZERO).
            if playing and fresh and metadata_ready and not track_changed and not discont:
                player.select_scripted(
                    soundswitch_id=ssid, elapsed_ms=elapsed_ms, transport="playing",
                    metadata_ready=True, authority="fresh", source_errored=False,
                    elapsed_discontinuous=False, track_changed=False,
                )
            else:
                player.clear_selection()

            # 4. Submit exactly one frame.
            backend.submit_frame(player.render().frame)
        except Exception:
            if not self._pack_logged_error:
                log.exception("[SM] pack driver error; resolving ZERO")
                self._pack_logged_error = True
            try:
                backend.submit_frame(_PACK_ZERO_FRAME)
            except Exception:
                pass

    def _push_tick_inner(self) -> None:
        # FM-1: check two-phase arm timer before any other push logic
        self._check_pending_arm()

        now = time.monotonic()
        os  = self._os
        active = os.active_deck
        d   = self._deck[active]
        mirror = 3 - active

        # ── Read position from memory ─────────────────────────────────────────
        snap = self._cache.get(active)
        if self._recorder and snap:
            self._recorder.record_position(active, snap)

        # When memory has no snap for this deck (DPU unresolved, e.g. no track
        # loaded in RB, DVS mode, or DPU2 vtable mismatch), synthesize a snap
        # from recent timecode so the push loop can resume/beat/elapsed normally.
        if snap is None:
            anchor_ms, anchor_at, anchor_pitch = self._tc_anchor.get(active, (0, 0.0, 1.0))
            if anchor_ms > 0 and anchor_at > 0 and (now - anchor_at) < 45.0:
                age_ms = (now - anchor_at) * 1000.0 * anchor_pitch
                snap = PositionSnapshot(
                    deck=active,
                    elapsed_ms=int(anchor_ms + (age_ms if d.playing else 0.0)),
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
                    sp_state = self._update_smart_phrasing_state(
                        active, d, 0.0, 0.0,
                    )
                    _lctx = self._build_laser_context(
                        active, d, os.last_beat_elapsed_ms, d.meta.bpm, 0.0, 0.0, snap, now,
                        sp_state=sp_state,
                    )
                    decision = self._laser_director.tick(_lctx, now=now)
                    if self._laser_executor is not None:
                        self._laser_executor.on_tick(_lctx)
                        self._laser_executor.on_decision(decision, _lctx)
                self._dispatch_led_idle_ambient(
                    active=active,
                    d=d,
                    reason="stale_stop",
                )
                return
            # Not playing: run lighting machine and auto-detect from current state.
            bpm = d.meta.bpm
            elapsed_ms = d.elapsed_ms or 0
            confident_playing = d.playing
            self._update_lighting(active, d, confident_playing, elapsed_ms, bpm, now)
            arm_guard = (now - os.last_arm_mono) < ARM_GUARD_S
            switch_requested = False
            if not d.playing and not arm_guard:
                if self._deck[mirror].playing:
                    log.info("[SM] switch  %d→%d  src=auto  reason=idle+mirror-playing",
                             active, mirror)
                    switch_requested = True
                    os.last_arm_mono = now
                    try:
                        self._eq.put_nowait(BridgeEvent(
                            kind=Ev.MASTER_CHANGED, deck=mirror, source="auto-detect",
                        ))
                    except queue.Full:
                        log.warning("[SM] queue-full  event=switch  deck=%d→%d  src=auto",
                                    active, mirror)
            if self._laser_director is not None:
                sp_state = self._update_smart_phrasing_state(
                    active, d, 0.0, 0.0,
                )
                _lctx = self._build_laser_context(
                    active, d, elapsed_ms, bpm, 0.0, 0.0, snap, now,
                    sp_state=sp_state,
                )
                decision = self._laser_director.tick(_lctx, now=now)
                if self._laser_executor is not None:
                    self._laser_executor.on_tick(_lctx)
                    self._laser_executor.on_decision(decision, _lctx)
            if not switch_requested:
                self._dispatch_led_idle_ambient(
                    active=active,
                    d=d,
                    reason="stale_idle",
                )
            return

        # Interpolate position: memory updates at 60 Hz; push loop at 200 Hz
        elapsed_since = (now - snap.updated_at) * 1000.0
        raw_elapsed_ms = snap.elapsed_ms + (elapsed_since if snap.playing else 0.0)
        mem_playing = snap.playing

        # Timecode fallback: when memory gives 0 (v2's container/DPU path reaches the wrong
        # inner for deck 2 in DDJ-800 mode — the correct deck-2 inner does write position
        # at +0xC, but it's reachable via outer+0x78, not container+0x480 or DPU scan).
        if snap.elapsed_ms == 0:
            anchor_ms, anchor_at, anchor_pitch = self._tc_anchor.get(active, (0, 0.0, 1.0))
            if anchor_ms > 0 and anchor_at > 0 and (now - anchor_at) < 45.0:
                age_ms = (now - anchor_at) * 1000.0 * anchor_pitch
                raw_elapsed_ms = anchor_ms + (age_ms if (mem_playing or d.playing) else 0.0)

        elapsed_ms = int(raw_elapsed_ms) + TIMING_COMPENSATION_MS
        prev_elapsed_ms = d.elapsed_ms
        d.elapsed_ms = elapsed_ms

        # ── Rate-limited timecode log (once per 5 s, both decks) ────────────────
        if now - self._last_pos_log[active] >= 5.0:
            self._last_pos_log[active] = now
            _live_a = self._autoloop.live_bpm_value(active)
            _live_a_s = f"  live_bpm={_live_a:.1f}" if _live_a is not None else ""
            log.info("[SM] pos  deck=%d  %s  bpm=%.1f%s  mode=%s  file=%s",
                     active, bf.elapsed(elapsed_ms), d.meta.bpm, _live_a_s,
                     "scripted" if d.scripted_id else "autoloop",
                     bf.short(d.meta.filepath))

        mirror_snap = self._cache.get(mirror)
        if mirror_snap and now - self._last_pos_log[mirror] >= 5.0:
            self._last_pos_log[mirror] = now
            dm = self._deck[mirror]
            _live_m = self._autoloop.live_bpm_value(mirror)
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

        # Beat position: computed from the current pitch-adjusted BPM.
        beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms) if bpm > 0 else 0.0
        beat_ms = 60_000.0 / bpm if bpm > 0 else 0.0
        abs_beat_pos = (
            self._autoloop.fallback_abs_beat_for_elapsed(active, elapsed_ms, bpm, d.meta.first_beat_ms)
            if beat_ms > 0 else 0.0
        )
        grid_pos = None
        if os.lighting_mode == "autoloop":
            grid_pos = _compute_beatgrid_position(elapsed_ms, d.meta.beatgrid_times_ms)
            if grid_pos is not None:
                beat_pos, abs_beat_pos = grid_pos
        bpm = self._autoloop.apply_live_bpm_follow(active, mirror, bpm, abs_beat_pos, now)
        if bpm > 0 and grid_pos is None:
            beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms)
            beat_ms = 60_000.0 / bpm
            abs_beat_pos = self._autoloop.fallback_abs_beat_for_elapsed(
                active, elapsed_ms, bpm, d.meta.first_beat_ms,
            )

        # ── Stop detection ────────────────────────────────────────────────────
        # d.playing is the authoritative transport state; memory corroboration
        # is kept for other_playing / auto-detect to guard against mis-mapped DPU offsets.
        is_playing = mem_playing or d.playing

        # ── Lighting state machine ────────────────────────────────────────────
        # Authoritative pause state wins even if memory (unreliable on DDJ-800
        # mode=4112) still shows playing.
        confident_playing = d.playing
        self._update_lighting(active, d, confident_playing, elapsed_ms, bpm, now)
        if os.lighting_mode == "autoloop" and grid_pos is None:
            grid_pos = _compute_beatgrid_position(elapsed_ms, d.meta.beatgrid_times_ms)
            if grid_pos is not None:
                beat_pos, abs_beat_pos = grid_pos

        # ── WI-1 monotonic LED/phrasing playhead clamp ────────────────────────
        abs_beat_pos = self._clamp_led_beat(abs_beat_pos, active, d.load_gen)

        self._led_rt_beat = (
            active,
            float(abs_beat_pos),
            float(bpm),
            float(now),
            bool(d.playing),
        )

        # Arm guard recomputed here so it reflects any arm fired by _update_lighting.
        arm_guard = (now - os.last_arm_mono) < ARM_GUARD_S

        # Stop detection follows authoritative transport state; memory cannot
        # override a pause event.
        if not d.playing and not arm_guard and os.was_playing:
            if os.not_playing_since == 0.0:
                os.not_playing_since = now
            stop_confirmed = (now - os.not_playing_since) >= STOP_DEBOUNCE_S
        else:
            if d.playing:
                os.not_playing_since = 0.0
            stop_confirmed = False

        # Check other deck for auto-switch.
        # Require authoritative confirmation (d.playing) in addition to memory; guards against
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
                self._dispatch_led_idle_ambient(
                    active=active,
                    d=d,
                    reason="stop_confirmed",
                )
            return

        # ── Auto-detect: active idle + mirror playing → switch ───────────────
        # Handles the case where RB auto-assigns master without an explicit
        # deck-change event.
        idle_switch_requested = False
        if not os.was_playing and not d.playing and not arm_guard:
            if self._deck[mirror].playing:
                log.info("[SM] switch  %d→%d  src=auto  reason=idle+mirror-playing",
                         active, mirror)
                idle_switch_requested = True
                os.last_arm_mono = now
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.MASTER_CHANGED, deck=mirror, source="auto-detect",
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=switch  deck=%d→%d  src=auto",
                                active, mirror)

        # ── Resume detection (was stopped, now playing) ───────────────────────
        # Authoritative transport state confirmed playback.
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
            if not idle_switch_requested:
                self._dispatch_led_idle_ambient(
                    active=active,
                    d=d,
                    reason="idle",
                )
            if self._laser_director is not None:
                sp_state = self._update_smart_phrasing_state(
                    active, d, 0.0, 0.0,
                )
                _lctx = self._build_laser_context(
                    active, d, elapsed_ms, bpm, beat_pos, abs_beat_pos, snap, now,
                    sp_state=sp_state,
                )
                decision = self._laser_director.tick(_lctx, now=now)
                if self._laser_executor is not None:
                    self._laser_executor.on_tick(_lctx)
                    self._laser_executor.on_decision(decision, _lctx)
            return

        # ── Emit elapsed + beat ───────────────────────────────────────────────
        if os.lighting_mode == "autoloop" and os.autoloop_arm_pending:
            self._autoloop.tick(
                now,
                AutoloopTickContext(active, mirror, bpm, abs_beat_pos, elapsed_ms),
            )

        sp_state = self._update_smart_phrasing_state(
            active, d, abs_beat_pos, bpm,
        )
        if sp_state.phrase_anchor_requested:
            self._pending_phrase_marker = True
        if d.playing:
            led_sp_state = self._led_sp_state_for_next_backend(sp_state, bpm)
            self._dispatch_led_automation(
                active=active,
                d=d,
                sp_state=led_sp_state,
                position_stale=(snap is None or snap.is_stale(MEM_STALE_S)),
            )
        else:
            self._dispatch_led_idle_ambient(
                active=active,
                d=d,
                reason="paused",
            )

        # BPM: send immediately when last_sent_bpm is 0 (fresh arm / deck switch) so
        # SS autoloop activates on the current tick, not at the next beat boundary.
        # VDJ sends BPM to all 4 decks; SS may use deck 3/4 internally.
        if bpm > 0 and os.last_sent_bpm == 0.0:
            for dk in self._sse.deck_route(active):
                self._out.send_bpm(dk, bpm)
            os.last_sent_bpm = bpm
        elif bpm > 0 and os.last_sent_bpm > 0:
            threshold = (BPM_THRESHOLD_SCRIPTED if d.scripted_id
                         else BPM_THRESHOLD_UNSCRIPTED)
            if abs(bpm - os.last_sent_bpm) > threshold:
                for dk in self._sse.deck_route(active):
                    self._out.send_bpm(dk, bpm)
                os.last_sent_bpm = bpm

        # Beat boundary detection: fire a beat event when elapsed crosses the next beat
        beatpos_out = abs_beat_pos if os.lighting_mode == "autoloop" else beat_pos
        autoloop_tick_just_fired = False
        smart_drop_result = SmartDropTickResult.none()
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
                last_abs_beat = self._autoloop.fallback_abs_beat_for_elapsed(
                    active, os.last_beat_elapsed_ms, bpm, d.meta.first_beat_ms,
                )
                last_beat = int(last_abs_beat)
            else:
                last_beat = int((os.last_beat_elapsed_ms - d.meta.first_beat_ms) / beat_ms) if beat_ms > 0 else 0

            if this_beat > last_beat:
                beat_index = this_beat % 4
                if os.pending_autoloop_arm_meta is not None:
                    self._autoloop.tick(
                        now,
                        AutoloopTickContext(active, mirror, bpm, abs_beat_pos, elapsed_ms),
                    )
                if os.lighting_mode == "autoloop":
                    beat_out = this_beat
                    pending_live_bpm = os.pending_live_bpm
                    if pending_live_bpm > 0:
                        self._sse.send_live_bpm_follow(active, pending_live_bpm)
                        bpm = pending_live_bpm
                        os.autoloop_arm_bpm = pending_live_bpm
                        self._autoloop.set_tempo_anchor(elapsed_ms, abs_beat_pos, pending_live_bpm)
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
                    smart_rearm_result = self._smart_rearm.tick(
                        active,
                        sp_state,
                        SmartRearmContext(
                            mirror=mirror,
                            bpm=bpm,
                            this_beat=this_beat,
                            elapsed_ms=elapsed_ms,
                            abs_beat_pos=abs_beat_pos,
                            blackout_mode=smart_drop_blackout_mode,
                            smart_drop_enabled=self._smart_drop_enabled,
                            smart_breakdown_enabled=self._smart_breakdown_enabled,
                            phrase_anchor_enabled=self._phrase_anchor_enabled,
                            lighting_mode_is_autoloop=True,
                        ),
                    )
                    smart_drop_result = smart_rearm_result.drop
                    if smart_drop_result.crossing:
                        change = True
                        if not smart_drop_blackout_mode:
                            autoloop_tick_just_fired = True
                    if smart_rearm_result.breakdown_fired:
                        change = True
                        autoloop_tick_just_fired = True
                    if smart_rearm_result.phrase_anchor_fired:
                        change = True
                        autoloop_tick_just_fired = True

                os.last_beat_elapsed_ms = elapsed_ms
                for dk in self._sse.deck_route(active):
                    self._out.send_beat(dk, bpm, beat_out, change=change)
                was_arm_pending = os.autoloop_arm_pending
                self._autoloop.tick(
                    now,
                    AutoloopTickContext(active, mirror, bpm, abs_beat_pos, elapsed_ms),
                )
                if was_arm_pending and not os.autoloop_arm_pending:
                    autoloop_tick_just_fired = True
                if os.lighting_mode == "autoloop":
                    # Phrase-relative MIDI re-fire (Piece 2):
                    #   primary  — RB phrase-marker crossing (latched), resets the counter
                    #   secondary— every 32 beats counted from the last marker fire
                    #   fallback — absolute 32-grid until the first marker is seen
                    marker_crossed = self._pending_phrase_marker
                    self._pending_phrase_marker = False
                    phrase_anchor_rearmed = bool(smart_rearm_result.phrase_anchor_fired)
                    origin = os.midi_refire_origin_beat
                    previous_refire_beat = os.last_autoloop_status_phrase_beat
                    refire = False
                    refire_source = "none"
                    if phrase_anchor_rearmed:
                        refire = True
                        refire_source = "phrase_anchor"
                    elif marker_crossed:
                        refire = True
                        refire_source = "marker"
                    elif origin >= 0:
                        refire = (this_beat - origin) >= AUTOLOOP_ARM_PHRASE_BEATS
                        if refire:
                            refire_source = "interval"
                    else:
                        refire = (
                            (this_beat // AUTOLOOP_ARM_PHRASE_BEATS)
                            > (last_beat // AUTOLOOP_ARM_PHRASE_BEATS)
                        )
                        if refire:
                            refire_source = "fallback_grid"
                    if refire and this_beat != os.last_autoloop_status_phrase_beat:
                        os.midi_refire_origin_beat = this_beat
                        os.last_autoloop_status_phrase_beat = this_beat
                        grid_status = d.meta.beatgrid_source if grid_pos is not None else "fallback"
                        log.info(
                            "[SM] midi-refire  deck=%d  beat=%d  source=%s  "
                            "origin_before=%d  origin_after=%d  previous=%d  "
                            "interval=%d  marker_latched=%s  grid=%s",
                            active,
                            this_beat,
                            refire_source,
                            origin,
                            os.midi_refire_origin_beat,
                            previous_refire_beat,
                            AUTOLOOP_ARM_PHRASE_BEATS,
                            marker_crossed,
                            grid_status,
                        )
                        self._autoloop.log_autoloop_tick(
                            active, elapsed_ms, beatpos_out, bpm, d.meta.bpm, grid_status
                        )
                        autoloop_tick_just_fired = True
                        if self._laser_executor is not None:
                            self._laser_executor.release_blackout_mask("master_switch")

        if os.lighting_mode == "autoloop":
            self._maybe_log_energy_suggest_would_fire(
                active, prev_elapsed_ms, elapsed_ms, d
            )

        # Laser Director tick — dry-run only in Phase 1.
        # Must not block, send MIDI, call OS2LOutput, or mutate DeckState/OutputState.
        drop_crossing_decision_emitted = False
        smart_drop_blackout_arm = bool(
            (
                smart_drop_result.blackout_armed
                or (
                    self._os.drop_cut_armed
                    and not smart_drop_result.crossing
                )
            )
            and smart_drop_blackout_mode
            and not self._os.breakdown_active
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
                smart_drop_blackout_mode=smart_drop_blackout_mode,
                smart_drop_result=smart_drop_result,
                sp_state=sp_state,
            )
            laser_director_enabled = self._laser_director.is_enabled()
            if (
                (smart_drop_blackout_arm or ctx.smart_phrasing_blackout_arm)
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
                self._laser_executor.on_tick(ctx)
                self._laser_executor.on_decision(decision, ctx)
        if smart_drop_result.crossing and smart_drop_blackout_mode:
            # Ordering requirement: in blackout mode keep os.drop_cut_armed true
            # through phrase-anchor processing so the coordinator suppresses
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
        for dk in self._sse.deck_route(active):
            self._out.send_elapsed(dk, elapsed_ms, beatpos_out)

    def _maybe_log_energy_suggest_would_fire(
        self, active: int, prev_elapsed_ms: float, elapsed_ms: float, d: DeckState
    ) -> None:
        shadows = d.meta.smart_drop_energy_shadow
        if not shadows:
            return
        for shadow in shadows:
            if shadow.confidence <= 0.0:
                continue
            suggested = float(shadow.suggested_elapsed_ms)
            if prev_elapsed_ms < suggested <= elapsed_ms:
                log.info(
                    "[SM] energy-suggest ★ deck=%d would-fire-now@%s  conf=%.2f",
                    active,
                    bf.elapsed(shadow.suggested_elapsed_ms),
                    shadow.confidence,
                )

    def _update_smart_phrasing_state(
        self,
        active: int,
        d,
        abs_beat_pos: float,
        bpm: float,
    ) -> SmartPhrasingState:
        deck = int(active)
        phrase_cached = self._phrase_segments_cache.get(deck)
        if phrase_cached and phrase_cached[0] == d.load_gen:
            phrase_segments = phrase_cached[1]
        else:
            phrase_segments = tuple(self._build_phrase_segments(d))
            self._phrase_segments_cache[deck] = (d.load_gen, phrase_segments)

        drop_cached = self._smart_drop_beats_cache.get(deck)
        if drop_cached and drop_cached[0] == d.load_gen:
            smart_drop_beats = drop_cached[1]
        else:
            smart_drop_beats = tuple(self._build_smart_drop_beats(d))
            self._smart_drop_beats_cache[deck] = (d.load_gen, smart_drop_beats)

        breakdown_cached = self._breakdown_segments_cache.get(deck)
        if breakdown_cached and breakdown_cached[0] == d.load_gen:
            breakdown_segments = breakdown_cached[1]
        else:
            breakdown_segments = tuple(self._build_breakdown_segments(d))
            self._breakdown_segments_cache[deck] = (d.load_gen, breakdown_segments)

        _sp_snapshot = SmartPhrasingSnapshot(
            deck_id=str(active),
            track_id=d.meta.content_id or d.meta.filepath or None,
            is_playing=d.playing,
            abs_beat=abs_beat_pos if bpm > 0 else None,
            phrase_segments=phrase_segments,
            smart_drop_beats=smart_drop_beats,
            breakdown_segments=breakdown_segments,
            phrase_lookahead_beats=self._sp_phrase_lookahead,
            drop_window_beats=self._sp_drop_window,
            post_drop_beats=self._sp_post_drop,
            transition_window_beats=self._sp_transition_window,
            phrase_anchor_last_beat=self._os.phrase_anchor_last_beat,
            phrase_anchor_period_beats=PHRASE_ANCHOR_BEATS,
        )
        _sp_result = self._smart_phrasing_engine.update(_sp_snapshot)
        sp_state = _sp_result.state
        self._last_sp_state = sp_state
        self._last_sp_snapshot = _sp_snapshot
        return sp_state

    def _led_sp_state_with_offset(
        self,
        sp_state: SmartPhrasingState,
        bpm: float,
        offset_s: float | None = None,
    ) -> SmartPhrasingState:
        if offset_s is None:
            offset_s = self._led_automation_offset_s
        if offset_s <= 0.0 or bpm <= 0.0 or self._last_sp_snapshot is None:
            return sp_state
        snapshot = self._last_sp_snapshot
        if snapshot.abs_beat is None or not snapshot.is_playing:
            return sp_state
        offset_beats = (bpm / 60.0) * offset_s
        return self._smart_phrasing_engine.preview_with_beat_offset(
            snapshot,
            offset_beats,
        )

    def _led_sp_state_for_next_backend(
        self,
        sp_state: SmartPhrasingState,
        bpm: float,
    ) -> SmartPhrasingState:
        cloud_offset_s = self._led_cloud_automation_offset_s
        realtime_offset_s = self._led_realtime_automation_offset_s
        if cloud_offset_s == realtime_offset_s:
            return self._led_sp_state_with_offset(sp_state, bpm, cloud_offset_s)

        cloud_sp_state = self._led_sp_state_with_offset(sp_state, bpm, cloud_offset_s)
        if self._led_should_smart_drop_blackout(cloud_sp_state):
            drop_preview = self._led_drop_decision_for_anchor(
                cloud_sp_state,
                commit=True,
            )
            if (
                drop_preview is not None
                and str(getattr(drop_preview, "backend", "cloud_diy") or "cloud_diy")
                == "realtime_razer"
            ):
                return self._led_sp_state_with_offset(sp_state, bpm, realtime_offset_s)
            return cloud_sp_state

        cloud_role = self._led_role_from_smart_phrasing(cloud_sp_state)
        if cloud_role == "drop":
            cloud_preview = self._led_drop_decision_for_anchor(
                cloud_sp_state,
                commit=True,
            )
        else:
            cloud_preview = self._preview_led_decision_for_role(cloud_role)
        if cloud_preview is not None:
            backend = str(getattr(cloud_preview, "backend", "cloud_diy") or "cloud_diy")
            if backend == "realtime_razer":
                return self._led_sp_state_with_offset(sp_state, bpm, realtime_offset_s)
            return cloud_sp_state

        realtime_sp_state = self._led_sp_state_with_offset(
            sp_state,
            bpm,
            realtime_offset_s,
        )
        realtime_role = self._led_role_from_smart_phrasing(realtime_sp_state)
        if realtime_role == "drop":
            realtime_preview = self._led_drop_decision_for_anchor(
                realtime_sp_state,
                commit=True,
            )
        else:
            realtime_preview = self._preview_led_decision_for_role(realtime_role)
        if (
            realtime_preview is not None
            and str(getattr(realtime_preview, "backend", "cloud_diy") or "cloud_diy")
            == "realtime_razer"
        ):
            return realtime_sp_state
        return cloud_sp_state

    def _clear_phrase_segment_cache(self, deck: int) -> None:
        self._phrase_segments_cache.pop(deck, None)
        self._smart_drop_beats_cache.pop(deck, None)
        self._breakdown_segments_cache.pop(deck, None)

    def _build_phrase_segments(self, d) -> tuple[PhraseSegment, ...]:
        return build_phrase_segments_from_markers(
            anlz_buildups=d.meta.anlz_buildups,
            anlz_drops=d.meta.anlz_drops,
            anlz_breakdowns=d.meta.anlz_breakdowns,
            smart_drops=d.meta.smart_drops,
            total_beats=len(d.meta.beatgrid_times_ms),
        )

    def _build_smart_drop_beats(self, d) -> tuple[float, ...]:
        return tuple(float(x) for x in d.meta.smart_drops)

    def _build_breakdown_segments(self, d) -> tuple[BeatSegment, ...]:
        # Note: this uses raw ANLZ breakdowns filtered dynamically, while the
        # coordinator breakdown path uses pre-filtered d.meta.smart_breakdowns.
        return tuple(
            BeatSegment(
                start_beat=float(bd_beat),
                end_beat=float(find_restore_beat(
                    bd_beat,
                    d.meta.anlz_buildups,
                    d.meta.smart_drops,
                    self._sp_breakdown_default_restore
                ))
            ) for bd_beat in select_smart_breakdowns(
                d.meta.anlz_breakdowns,
                total_beats=len(d.meta.beatgrid_times_ms)
            )
        )

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
        smart_drop_blackout_mode: bool = False,
        smart_drop_result: Optional[SmartDropTickResult] = None,
        *,
        sp_state: SmartPhrasingState,
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
        if smart_drop_result is None:
            smart_drop_result = SmartDropTickResult.none()

        smart_phrasing_blackout_arm = bool(
            smart_drop_blackout_mode
            and sp_state.transition_mask_arm_latched
            and not self._os.breakdown_active
            and not self._os.autoloop_arm_pending
            and self._os.pending_autoloop_arm_meta is None
            and not smart_drop_result.crossing
        )

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
            scripted_id=d.scripted_id,
            smart_drop_blackout_active=self._os.drop_cut_armed,
            smart_drop_blackout_arm=smart_drop_blackout_arm,
            smart_phrasing_blackout_arm=smart_phrasing_blackout_arm,
            smart_phrasing=sp_state,
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
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""
        self._led_smart_drop_blackout_key = ""
        self._clear_led_drop_lifecycle()
        self._clear_smart_rearm_state()
        self._autoloop.clear_arm_phrase_lock()
        self._autoloop.clear_live_bpm_follow()
        self._autoloop.clear_tempo_relock()
        self._autoloop.clear_tempo_anchor()
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
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""
        self._led_smart_drop_blackout_key = ""
        self._clear_led_drop_lifecycle()
        self._log_status()

    def _clear_smart_rearm_state(self) -> None:
        os = self._os
        if self._laser_executor is not None:
            self._laser_executor.clear_pending_blackout(reason="smart_rearm_state_cleared")
        self._smart_phrasing_engine.clear_smart_rearm_state()
        if self._last_sp_state is not None:
            self._last_sp_state = replace(
                self._last_sp_state,
                transition_window_active=False,
                transition_mask_arm_latched=False,
            )
        os.drop_cut_armed = False
        os.drop_rearm_beat = 0
        os.breakdown_active = False
        os.breakdown_restore_beat = 0
        os.phrase_anchor_last_beat = -1
        os.midi_refire_origin_beat = -1
        self._pending_phrase_marker = False
        self._clear_led_drop_lifecycle()

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
