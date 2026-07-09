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
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from .config import (
    AUTOLOOP_ARM_PHRASE_BEATS, ARM_GUARD_S, STOP_DEBOUNCE_S,
    PLAY_SETTLE_MS,
    BPM_THRESHOLD_SCRIPTED, BPM_THRESHOLD_UNSCRIPTED,
    MEM_STALE_S, SMART_DROP_LOOKAHEAD_BEATS, SMART_DROP_IGNORE_INTRO_BEATS,
    SMART_DROP_IGNORE_OUTRO_BEATS, PHRASE_ANCHOR_BEATS,
    SMART_BREAKDOWN_DEFAULT_DURATION_BEATS,
    SMART_BREAKDOWN_IGNORE_INTRO_BEATS, SMART_BREAKDOWN_IGNORE_OUTRO_BEATS,
)

from .beat_math import (
    _compute_beat_pos,
    _compute_beatgrid_position,
    _beatgrid_elapsed_for_abs_beat,
)
from .active_deck_resolver import (
    MIXER_STALE_AFTER_S, RB_MASTER_STALE_AFTER_S,
    ActiveDeckDecision,
    ResolverDeckInput,
    ResolverState,
    resolve_active_deck,
)
from .smart_phrasing import (
    build_phrase_segments_from_markers,
    select_smart_drops,
    select_smart_breakdowns,
    find_restore_beat,
)
from .models import (
    ArmSequence, BridgeEvent, DeckState, Ev, MixerAuthoritySnapshot, OutputState,
    PositionSnapshot, SmartDropEnergyShadow, TrackMetadata,
)
from . import led_dispatch_policy as _led_dispatch_policy
from .led_dispatch_policy import LEDDispatchPolicyMixin
from .led_palette_control import LedPaletteControl, PaletteFeedbackWriter
from .led_config import load_drop_presentation_config
from .led_identity_v2 import (
    IdentityStore,
    NORM_ANCHORS as LED_IDENTITY_NORM_ANCHORS,
    assign_zone as assign_led_identity_zone,
    content_key as led_identity_content_key,
    content_hash as led_identity_content_hash,
    derive_dressing as derive_led_identity_dressing,
    identity_scores as led_identity_scores,
    norm as led_identity_norm,
    record_from_dressing as led_identity_record_from_dressing,
)
from .led_models import IdentityV2Config
from .drop_presentation import (
    AUDIBLE_DAMPER_BEATS,
    LEDS_ONLY,
    LEDS_PLUS_LASERS,
    LASERS_ONLY,
    LEARNED_STORE_PATH,
    LearnedStore,
    SessionState,
    TrackPlan,
    WindowActions,
    WindowInputs,
    WindowMachine,
    gearshift_qualifies,
    plan_track,
    resolve_presentation,
)
from .laser_color_engine import (
    LaserColorEngine as LaserColorMapper,
    _nearest_fixed_color as _laser_nearest_fixed_color,
    load_laser_color_map,
)
from .laser_models import LaserContext, LaserPersonality, LaserResolvedScene
from .soundswitch_laser_player import (
    ZERO_FRAME as _PACK_ZERO_FRAME,
    normalize_soundswitch_id as _pack_normalize_id,
)
from .native_autoloop_resolver import (
    NATIVE_AUTOLOOP_STATUSES,
    NativeAutoloopDecision,
    NativeAutoloopResolver,
    finalize_native_autoloop_render,
)
from .soundswitch_pack_runtime import PackRuntime, DISABLED_PACK_RUNTIME
from .osl_output import OS2LOutput
from .rb_memory import PositionCache
from .scripted_tracks import SCRIPTED_TRACKS, lookup as st_lookup
from . import bridge_log
from .filepath_resolver import has_soundswitch_scripted_id
from .personality_resolver import PersonalityResolver, PlaylistCache
from .session_recorder import SessionRecorder
from .session_phase_trace import AutoloopPhaseTracer, build_autoloop_phase_row
from .sound_switch_engine import SoundSwitchEngine
from . import spectral_cache
from . import spectral_profile
from .audio_spectral_features import (
    extract_spectral_features,
    extract_spectral_features_v4,
)
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
__all__ = ["StateManager", "SmartDropTickResult"]


def __getattr__(name: str) -> Any:
    if name.startswith("LED_") or name.startswith("_LED_"):
        try:
            return getattr(_led_dispatch_policy, name)
        except AttributeError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

_LATENCY_WARN_MS = 50.0
_TC_LATENCY_WARN_MS = 250.0
# T7c pack driver: only a genuine seek/cue jump (not normal playback or jitter)
# should flag elapsed discontinuity. Err HIGH — a missed discontinuity just renders
# the scripted frame at the new position; a false one ZEROs one tick.
_PACK_SEEK_JUMP_MS = 2000
# One-tick elapsed delta that cannot be real 1x playback (drag-scrub steps in the
# 2026-07-02 capture were 408-1295 ms/tick; real playback is <=~20 ms/tick), and
# how long the automatic base stays dark after the last such jump. SoundSwitch
# stays dark through a waveform scrub and re-shows shortly after it settles; the
# pack must not strobe through 100+ s of cues during a drag.
_PACK_SCRUB_JUMP_MS = 400
_PACK_SCRUB_HOLD_S = 0.6
LIVE_BPM_FOLLOW_ENV = "RBSS_LIVE_BPM_FOLLOW"
AUTOLOOP_MASTER_PHRASE_ARM_ENV = "RBSS_AUTOLOOP_MASTER_PHRASE_ARM"
SMART_DROP_ENV = "RBSS_SMART_DROP"
SMART_BREAKDOWN_ENV = "RBSS_SMART_BREAKDOWN"
PHRASE_ANCHOR_ENV = "RBSS_PHRASE_ANCHOR"
SMART_REARM_EXPERIMENT_ENV = "RBSS_SMART_REARM_EXPERIMENT"
SPECTRAL_ENABLE_ENV = "RBSS_SPECTRAL_ENABLE"


def _pack_operational_state(
    *,
    enabled: bool,
    blackout: bool,
    input_degraded: bool,
    static_held: bool,
    scripted_active: bool,
    autoloop_phase_blocked: bool,
    software_zero_frame: bool,
    native_autoloop_status: str = "",
    parity_live_blocked: bool = False,
) -> str:
    """Resolve the bounded display priority; companion booleans remain authoritative."""
    if not enabled:
        return "disabled"
    if blackout:
        return "blackout"
    if parity_live_blocked:
        return "unverified_parity"
    if input_degraded:
        return "input_degraded"
    if static_held:
        return "static_held"
    if scripted_active:
        return "scripted_active"
    if native_autoloop_status in NATIVE_AUTOLOOP_STATUSES:
        return native_autoloop_status
    if autoloop_phase_blocked:
        return "autoloop_phase_blocked"
    return "software_zero_frame"
WIDE_WINDOW_ENV = "RBSS_DROP_WIDE_WINDOW"
SCRIPTED_SHOWFILE_DIRECT_ENV = "RBSS_SCRIPTED_SHOWFILE_DIRECT"
STATE_MANAGER_PROFILE_ENV = "RBSS_SM_PROFILE"
# WI-1/2/3/4/5/6/7 kill-switches (read once at startup; default ON except cooldown)
_SNAPSHOT_PUBLISH_INTERVAL_S = 0.05
_PROFILE_SUMMARY_INTERVAL_S = 10.0
_PROFILE_WINDOW = 2048

def _read_runtime_anlz_data(
    anlz_path: str,
    *,
    audio_filepath: str = "",
    spectral_enabled: bool = False,
    identity_enabled: bool = False,
    identity_key: str = "",
    identity_config: IdentityV2Config | None = None,
    wide_window: bool = False,
) -> TrackAnlzData:
    data = read_anlz_drops(anlz_path)
    ctx = data.waveform_context

    v4 = None
    beatgrid_times_ms: list[float] = []
    if (spectral_enabled or identity_enabled) and audio_filepath and ctx is not None:
        beatgrid_times_ms = list(ctx.beatgrid_times_ms)
        try:
            v4 = spectral_cache.get_cached_v4(audio_filepath, beatgrid_times_ms)
            if v4 is None:
                grid_span_s = 0.0
                if len(beatgrid_times_ms) >= 2:
                    grid_span_s = (float(beatgrid_times_ms[-1]) - float(beatgrid_times_ms[0])) / 1000.0
                if grid_span_s <= _V4_AT_LOAD_MAX_S:
                    v4 = extract_spectral_features_v4(audio_filepath, beatgrid_times_ms)
                    if v4 is not None:
                        spectral_cache.put_cached_v4(audio_filepath, beatgrid_times_ms, v4)
                        log.info("[SM] spectral-path  source=v4-extract  file=%s", bf.short(audio_filepath))
        except Exception as exc:
            log.warning("[LED] identity-derive-failed file=%s err=%s", bf.short(audio_filepath), type(exc).__name__)
            v4 = None

    if identity_enabled and identity_config is not None and identity_key:
        data.led_identity = _derive_led_identity_record(
            v4,
            key=identity_key,
            cfg=identity_config,
        )

    if spectral_enabled and ctx is not None and data.drop_beat_indices:
        if not beatgrid_times_ms:
            beatgrid_times_ms = list(ctx.beatgrid_times_ms)
        features = _runtime_spectral_features(audio_filepath, beatgrid_times_ms, v4=v4)
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


# Longer grids defer v4 extraction to the offline sweep; the legacy v3 path
# keeps today's behavior for them (design doc §4.10 change 5).
_V4_AT_LOAD_MAX_S = 900.0


def _runtime_spectral_features(audio_filepath: str, beatgrid_times_ms: list[float], *, v4=None):
    if not audio_filepath:
        return None
    if v4 is not None:
        return spectral_profile.compat_features(v4)
    v4 = spectral_cache.get_cached_v4(audio_filepath, beatgrid_times_ms)
    if v4 is not None:
        return spectral_profile.compat_features(v4)
    cached = spectral_cache.get_cached(audio_filepath, beatgrid_times_ms)
    if cached is not None:
        log.info("[SM] spectral-path  source=v3-cache  file=%s", bf.short(audio_filepath))
        return cached
    grid_span_s = 0.0
    if len(beatgrid_times_ms) >= 2:
        grid_span_s = (float(beatgrid_times_ms[-1]) - float(beatgrid_times_ms[0])) / 1000.0
    if grid_span_s <= _V4_AT_LOAD_MAX_S:
        v4 = extract_spectral_features_v4(audio_filepath, beatgrid_times_ms)
        if v4 is not None:
            spectral_cache.put_cached_v4(audio_filepath, beatgrid_times_ms, v4)
            log.info("[SM] spectral-path  source=v4-extract  file=%s", bf.short(audio_filepath))
            return spectral_profile.compat_features(v4)
    features = extract_spectral_features(audio_filepath, beatgrid_times_ms)
    if features is not None:
        spectral_cache.put_cached(audio_filepath, beatgrid_times_ms, features)
        log.info("[SM] spectral-path  source=v3-extract  file=%s", bf.short(audio_filepath))
    return features


def _derive_led_identity_record(v4, *, key: str, cfg: IdentityV2Config) -> dict[str, Any]:
    key_hash = led_identity_content_hash(key)
    if v4 is None:
        dressing = derive_led_identity_dressing(
            "NEUTRAL",
            cfg.zones["NEUTRAL"],
            key_hash,
            0.5,
            0.5,
            0.0,
        )
        return led_identity_record_from_dressing(
            dressing,
            key_hash=key_hash,
            base="provisional",
            scores={},
            norm_inputs={"bass": 0.5, "drama": 0.5, "punch": 0.0},
        )
    axes = spectral_profile.identity_axes(v4)
    scalars = dict(v4.scalars)
    flags = spectral_profile.sustained_synth_flags(v4)
    synth_rate = (sum(1 for flag in flags if flag) / len(flags)) if flags else 0.0
    scores = led_identity_scores(axes, scalars, synth_rate)
    zone = assign_led_identity_zone(scores)
    bass_lo, bass_hi = cfg.bass_norm
    norm_inputs = {
        "bass": led_identity_norm(float(axes.get("bass", 0.5)), bass_lo, bass_hi),
        "drama": led_identity_norm(float(axes.get("drama", 0.0)), *LED_IDENTITY_NORM_ANCHORS["drama"]),
        "punch": led_identity_norm(float(axes.get("punch", 0.0)), *LED_IDENTITY_NORM_ANCHORS["punch"]),
    }
    dressing = derive_led_identity_dressing(
        zone,
        cfg.zones[zone],
        key_hash,
        norm_inputs["bass"],
        norm_inputs["drama"],
        norm_inputs["punch"],
    )
    return led_identity_record_from_dressing(
        dressing,
        key_hash=key_hash,
        base="measured",
        scores=scores,
        norm_inputs=norm_inputs,
    )


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













class StateManager(LEDDispatchPolicyMixin):
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
        led_identity_store: Optional[IdentityStore] = None,
        led_palette_control_config: Optional[dict[str, Any]] = None,
        os2l_connected_provider=None,
        recorder: Optional[SessionRecorder] = None,
        soundswitch_pack_runtime=None,
        mixer_authority_enabled: bool = False,
    ) -> None:
        self._eq    = event_queue
        self._cache = position_cache
        self._out   = output
        self._live_bpm = live_bpm
        self._recorder = recorder if recorder is not None else SessionRecorder.from_env()
        # B1 evidence-only autoloop phase tracer (schema-2). Attached ONLY while a
        # session recording started via the runtime command is active; None ⇒ the
        # tick emits no phase rows (zero overhead beyond one truth test). NOT a T7d
        # runtime/output feature — preparatory capture tooling only.
        self._phase_tracer: Optional[AutoloopPhaseTracer] = None
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
        self._pack_frame_count = 0
        self._pack_status_snapshot: dict[str, Any] = {}
        self._publish_pack_status(
            runtime=self._pack_runtime,
            scripted_active=False,
            input_degraded=False,
            static_held=False,
            blackout=False,
            autoloop_phase_blocked=False,
            software_zero_frame=True,
        )
        # Push-thread-owned driver trackers (NOT part of the swappable bundle).
        self._pack_last_load_gen: tuple[int, int] | None = None   # (active, load_gen)
        self._pack_last_elapsed_ms: int | None = None
        self._pack_scrub_hold_until: float = 0.0
        self._pack_last_static_layers: tuple[Any, ...] = ()
        self._pack_last_mail_drop_count: int = 0      # RW-4: monotonic mailbox-drop baseline
        self._pack_input_degraded_latched: bool = False  # RW-4: unified input-degradation latch
        self._pack_input_health_logged_error: bool = False
        self._pack_play_hold_key: tuple[int, int, int, str] | None = None  # play identity (active, load_gen, scripted_id, norm_ssid)
        self._pack_play_hold_deadline: float = 0.0                 # monotonic deadline; paused-hold expires here
        self._pack_logged_error = False
        self._native_autoloop = NativeAutoloopResolver()
        self._native_captured_scene: LaserResolvedScene | None = None
        self._native_abs_beat_pos: float | None = None
        self._native_log_key: tuple[Any, ...] = ()
        _laser_color_map = load_laser_color_map()
        self._laser_color_engine = LaserColorMapper(_laser_color_map)
        log.info(
            "[SM] laser-color-map  enabled=%s  fixed_colors=%d",
            _laser_color_map.enabled,
            sum(1 for v in (_laser_color_map.fixed or {}).values() if v is not None),
        )
        self._laser_color_led_sig: tuple[Any, ...] | None = None
        self._last_sp_snapshot: Optional[SmartPhrasingSnapshot] = None

        # ── Drop presentation policy (Package 3, AWR-119) ─────────────────────
        # Self-contained load, mirroring self._laser_color_engine above — no
        # __main__.py wiring needed. enabled: false is checked at every
        # consumption site below (master regression gate), not here, so a live
        # config edit takes effect without a restart.
        self._drop_presentation_config = load_drop_presentation_config()
        if self._drop_presentation_config.ws_handoff_enabled:
            # Task 5: parsed but deliberately not implemented in this package
            # (authority doc's optional white_sand handoff tier). Named no-op
            # guard so an operator who flips this on gets a clear signal
            # instead of silent nothing.
            log.warning(
                "[SM] drop-presentation-ws-handoff-not-implemented  "
                "reason=ws_handoff_enabled is parsed but its ritual tier is not "
                "implemented in this package; no behavior change occurs"
            )
        self._drop_presentation_session = SessionState()
        self._drop_presentation_window = WindowMachine(self._drop_presentation_config)
        self._drop_presentation_plan: Optional[TrackPlan] = None
        self._drop_presentation_plan_deck: int = 0
        self._drop_presentation_plan_load_gen: int = 0
        self._drop_presentation_plan_content_id: str = ""
        # Per-deck "have both halves of a plan's inputs arrived for THIS load"
        # latches (Task 4 item 1: the plan finalizes only once both ANLZ data
        # and hot-cue tags are in; until then drops fail-open to leds_plus_lasers
        # via _drop_presentation_pending_for_this_drop's None fallback below).
        self._drop_presentation_anlz_ready: dict[int, int] = {1: -1, 2: -1}
        self._drop_presentation_tags_ready: dict[int, int] = {1: -1, 2: -1}
        self._drop_presentation_tag_beats: dict[int, tuple[float, ...]] = {1: (), 2: ()}
        # Opening-damper ≥16-beat audible latch bookkeeping: first audible beat
        # seen per (deck, load_gen); SessionState.mark_track_counted() is
        # already idempotent, so no separate "already counted" set is needed
        # here.
        self._drop_presentation_audible_start_beat: dict[tuple[int, int], float] = {}
        # Solo pad: one-shot manual arm state (tier 2), keyed on (deck, load_gen)
        # so it auto-invalidates on track change without a separate clear call
        # (authority doc: "an armed solo never carries into a track the
        # operator didn't aim it at"). The feedback string is what
        # LedPaletteControl's get_laser_solo pulls ("off" | "armed" | "active").
        self._drop_presentation_armed_key: Optional[tuple[int, int]] = None
        self._drop_presentation_solo_feedback: str = "off"
        # One-tick request set by a pad press while a solo window is open
        # (AWR-159 Task 1); _drop_presentation_tick consumes it into
        # WindowInputs.manual_interaction=True the very next tick and clears it,
        # regardless of that tick's impact_now value.
        self._drop_presentation_manual_cancel: bool = False
        # Set by _drive_pack_output each tick: pack live AND the latest autoloop
        # base render had no diagnostic (Task 4 items 3-4's darkness-guard input).
        self._drop_presentation_base_live: bool = False
        # Cached each tick by _drop_presentation_tick; read back by the Solo pad
        # handler (arm/veto) and the feedback updater. Applied-output holds are
        # tracked separately so _drop_presentation_apply_actions only calls
        # into the owner-set/player exactly on a change, not every tick.
        self._drop_presentation_last_pending: tuple[Optional[str], str, Optional[float]] = (None, "", None)
        self._drop_presentation_last_actions: Optional[WindowActions] = None
        self._drop_presentation_led_dark_held: bool = False
        self._drop_presentation_base_suppressed_held: bool = False
        # Fail-open detectors (authority doc: track change / active-deck change
        # must restore any active window). Compared against each tick, updated
        # every tick, so the very NEXT tick after either changes carries True
        # exactly once. None (not 0) means "never seen this deck yet" -- load_gen
        # 0/1 are real values, so a 0-sentinel would spuriously read as a track
        # change on the very first tick a deck is ever evaluated.
        self._drop_presentation_last_load_gen: dict[int, Optional[int]] = {1: None, 2: None}
        self._drop_presentation_last_active_deck: Optional[int] = None
        try:
            _os.makedirs(_os.path.dirname(LEARNED_STORE_PATH) or ".", exist_ok=True)
        except OSError as exc:
            log.warning("[SM] drop-presentation-state-dir-failed  err=%s", type(exc).__name__)
        self._drop_presentation_learned_store = LearnedStore.load(LEARNED_STORE_PATH)
        self._drop_presentation_learned_writer = PaletteFeedbackWriter(
            LEARNED_STORE_PATH, debounce_s=0.5,
        )
        self._drop_presentation_learned_writer.start()

        self._init_led_dispatch_state(led_look_director, led_scene_adapter, led_color_engine)
        self._last_audible_deck: int = 1
        self._v2_identity_cfg: IdentityV2Config | None = None
        if led_color_engine is not None:
            engine_config = getattr(led_color_engine, "_config", None)
            self._v2_identity_cfg = getattr(engine_config, "v2", None)
        self._v2_identity_enabled = bool(
            self._v2_identity_cfg is not None and self._v2_identity_cfg.enabled
        )
        self._led_v2_latch = bool(self._v2_identity_enabled)
        self._led_identity_store = led_identity_store or IdentityStore()
        self._led_identity_writer = None
        if self._v2_identity_enabled and self._v2_identity_cfg is not None:
            try:
                _os.makedirs(_os.path.dirname(self._v2_identity_cfg.store_path) or ".", exist_ok=True)
            except OSError as exc:
                log.warning("[LED] identity-state-dir-failed err=%s", type(exc).__name__)
            if self._led_identity_store.write_allowed:
                self._led_identity_writer = PaletteFeedbackWriter(
                    self._v2_identity_cfg.store_path,
                    debounce_s=0.5,
                )
                self._led_identity_writer.start()
            set_v2_active = getattr(led_color_engine, "set_v2_active", None)
            if callable(set_v2_active):
                set_v2_active(self._led_v2_latch)
        palette_control_config = led_palette_control_config or {}
        raw_palette_notes = palette_control_config.get("palette_notes", {})
        palette_notes = dict(raw_palette_notes) if isinstance(raw_palette_notes, dict) else {}
        # white_sand rides its own config key; without this merge the feedback
        # payload has no note for it and the deck blanks key 5.
        ws_note = palette_control_config.get("white_sand_note")
        if type(ws_note) is int and 0 <= ws_note <= 127:
            palette_notes.setdefault("white_sand", ws_note)
        raw_long_press_s = palette_control_config.get("long_press_s", 0.5)
        long_press_s = (
            float(raw_long_press_s)
            if isinstance(raw_long_press_s, (int, float)) and not isinstance(raw_long_press_s, bool)
            else 0.5
        )
        control_notes = {
            "lock": palette_control_config.get("lock_note"),
            "led_mute": palette_control_config.get("led_mute_note"),
            "laser_mute": palette_control_config.get("laser_mute_note"),
            "laser_solo": palette_control_config.get("laser_solo_note"),
            "rainbow": palette_control_config.get("rainbow_note"),
        }
        control_notes = {
            key: int(note)
            for key, note in control_notes.items()
            if type(note) is int and 0 <= note <= 127
        }
        raw_zone_notes = palette_control_config.get("zone_notes", {})
        zone_notes = {
            str(name): int(note)
            for name, note in (raw_zone_notes.items() if isinstance(raw_zone_notes, dict) else ())
            if type(note) is int and 0 <= note <= 127
        }
        raw_manual_notes = palette_control_config.get("manual_notes", {})
        manual_notes = {
            str(name): int(note)
            for name, note in (raw_manual_notes.items() if isinstance(raw_manual_notes, dict) else ())
            if type(note) is int and 0 <= note <= 127
        }
        max_energy_note = palette_control_config.get("max_energy_note")
        self._led_palette_control = (
            LedPaletteControl(
                engine=led_color_engine,
                led_event_sink=self._handle_led_event,
                get_abs_beat=self._palette_control_abs_beat,
                get_phrase_anchor=self._palette_control_phrase_anchor,
                get_laser_blackout=lambda: bool(self._pack_status_snapshot.get("blackout", False)),
                get_laser_solo=lambda: self._drop_presentation_solo_feedback,
                get_static_held=self._palette_static_held,
                get_engine_mode=lambda: "v2" if self._led_v2_latch else "v1",
                apply_zone_correction=self._apply_led_zone_correction,
                clear_zone_correction=self._clear_led_zone_correction,
                toggle_max_energy=self._toggle_led_max_energy,
                get_max_energy_armed=lambda: bool(getattr(self, "_led_max_energy_armed", False)),
                palette_notes=palette_notes,
                zone_notes=zone_notes,
                manual_notes=manual_notes,
                max_energy_note=max_energy_note if type(max_energy_note) is int else None,
                control_notes=control_notes,
                long_press_s=long_press_s,
            )
            if led_color_engine is not None
            else None
        )
        # Cheap change-signature of the color engine's palette state, compared
        # every playing tick so the deck feedback is republished when the engine
        # changes palette on its own (fade commit, dwell drift) — not only on
        # operator pad presses (2026-07-05 stale-pad fix).
        self._palette_feedback_sig: tuple | None = None
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
        self._mixer_authority_enabled = bool(mixer_authority_enabled)

        # Per-deck state (written only by this thread after start())
        self._deck: dict[int, DeckState] = {
            1: DeckState(number=1),
            2: DeckState(number=2),
        }
        # Push-loop bookkeeping
        self._os = OutputState()
        self._mixer_snapshot = MixerAuthoritySnapshot(
            valid=False,
            deck={},
            updated_at=0.0,
            reason="missing_offsets",
        )
        self._active_deck_resolver_state = ResolverState()

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

        # RB raw deck index (0-3) that last drove PLAY per bridge deck. Two RB
        # decks share one bridge slot (1&3→1, 2&4→2); while the owning RB deck
        # is playing, a transient load surfacing on its idle sibling must not
        # clobber the playing deck's metadata (live 2026-07-02: Wanton→
        # BLACKPINK→Wanton flap mid-autoloop armed the wrong scripted show).
        self._deck_play_owner: dict[int, int] = {}

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
        self._last_sp_reset_reason: str = ""
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

    def set_initial_state(
        self,
        active_deck: int,
        source: str = "default startup",
        *,
        rb_master_valid: bool = False,
    ) -> None:
        """Apply startup active-deck state before the event loop starts."""
        if active_deck not in (0, 1, 2):
            return
        self._os.active_deck = active_deck
        if active_deck in (1, 2):
            self._last_audible_deck = active_deck
        self._os.active_deck_authority_reason = (
            "startup_idle" if active_deck == 0 else "startup_fallback"
        )
        if rb_master_valid and active_deck in (1, 2):
            self._os.rb_master_deck = active_deck
            self._os.rb_master_deck_valid = True
            self._os.rb_master_deck_source = source
            self._os.rb_master_deck_updated_at = time.monotonic()
            self._os.rb_master_fallback_reason = ""
        log.info("[SM] init  deck=%d  src=%s", active_deck, source)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._run, name="state-manager", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()
        if self._led_palette_control is not None:
            self._led_palette_control.stop()
        if self._led_identity_writer is not None:
            self._led_identity_writer.stop()
        self._drop_presentation_learned_writer.stop()

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

    def _palette_control_abs_beat(self) -> float | None:
        sp = self._last_sp_state
        if sp is not None and sp.abs_beat is not None:
            return float(sp.abs_beat)
        return None

    def _palette_control_phrase_anchor(self, start_beat: float) -> float | None:
        sp = self._last_sp_state
        if sp is not None and sp.phrase_anchor_target_beat is not None:
            target = float(sp.phrase_anchor_target_beat)
            if target > start_beat:
                return target
        snap = self._last_sp_snapshot
        if snap is None:
            return None
        target = float(snap.phrase_anchor_last_beat + snap.phrase_anchor_period_beats)
        return target if target > start_beat else None

    def _palette_static_held(self) -> tuple:
        rt = self._pack_runtime
        midi_input = getattr(rt, "midi_input", None) if rt is not None else None
        if midi_input is None:
            return ()
        try:
            layers = midi_input.snapshot().held_layers
        except Exception:
            return ()
        return tuple(
            (layer.channel, layer.note, layer.kind)
            for layer in layers
            if getattr(layer, "note", -1) >= 0
        )

    # ── Main loop ────────────────────────────────────────────────────────────

    def _run(self) -> None:
        log.info("[SM] starting")
        loop_error_count = 0
        next_loop_error_log = 0.0
        with bridge_log.thread_guard("state-manager"):
            while not self._stop.is_set():
                t0 = time.monotonic()
                remaining = 0.0
                push_started = False
                push_completed = False
                try:
                    profiler = self._profiler
                    if profiler is None:
                        self._drain_events()
                        push_started = True
                        self._push_tick()
                        push_completed = True
                        self._maybe_publish_snapshot(time.monotonic())
                        remaining = self._TICK_INTERVAL - (time.monotonic() - t0)
                    else:
                        queue_depth = self._queue_depth()
                        self._drain_events()
                        t1 = time.monotonic()
                        push_started = True
                        self._push_tick()
                        push_completed = True
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
                except Exception as exc:
                    loop_error_count += 1
                    now = time.monotonic()
                    if not push_started or push_completed:
                        self._submit_pack_zero_frame()
                    if now >= next_loop_error_log:
                        bridge_log.health(
                            "tick", "push loop error; skipping tick error=%s count=%d",
                            type(exc).__name__, loop_error_count, lvl=logging.ERROR,
                        )
                        next_loop_error_log = now + 1.0
                    remaining = self._TICK_INTERVAL - (now - t0)
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
        color_engine_status["led_mute"] = bool(
            getattr(self, "_led_blackout_owners", set())
            or getattr(self, "_led_emergency_blackout", False)
        )
        color_engine_status["laser_mute"] = bool(
            self._pack_status_snapshot.get("blackout", False)
        )
        palette_control_status = {}
        if self._led_palette_control is not None:
            try:
                palette_control_status = self._led_palette_control.snapshot()
            except Exception as exc:
                palette_control_status = {
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
        now = time.monotonic()
        mixer_age = (
            now - self._mixer_snapshot.updated_at
            if self._mixer_snapshot.updated_at > 0.0
            else None
        )
        mixer_decks = {
            str(num): {
                "upfader_raw": reading.upfader_raw,
                "upfader_norm": reading.upfader_norm,
                "upfader_label": reading.upfader_label,
                "low_raw": reading.low_raw,
                "low_norm": reading.low_norm,
                "low_label": reading.low_label,
            }
            for num, reading in self._mixer_snapshot.deck.items()
        }
        rb_master_age = (
            now - os.rb_master_deck_updated_at
            if os.rb_master_deck_updated_at > 0.0
            else None
        )
        rb_master_status_valid = bool(os.rb_master_deck_valid)
        if rb_master_age is not None and rb_master_age > RB_MASTER_STALE_AFTER_S:
            rb_master_status_valid = False
        snapshot = {
            "active_deck": os.active_deck,
            "show_deck": os.active_deck,
            "rb_master_deck": os.rb_master_deck,
            "rb_master_deck_valid": rb_master_status_valid,
            "rb_master_deck_source": os.rb_master_deck_source,
            "rb_master_deck_updated_at": os.rb_master_deck_updated_at,
            "rb_master_deck_age_s": rb_master_age,
            "rb_master_fallback_reason": os.rb_master_fallback_reason,
            "active_deck_authority_reason": os.active_deck_authority_reason,
            "mixer_authority_valid": os.mixer_authority_valid,
            "mixer_authority_updated_at": os.mixer_authority_updated_at,
            "mixer_authority_age_s": mixer_age,
            "mixer_fallback_reason": os.mixer_fallback_reason,
            "mixer": {
                "enabled": self._mixer_authority_enabled,
                "valid": os.mixer_authority_valid,
                "reason": self._mixer_snapshot.reason,
                "updated_at": self._mixer_snapshot.updated_at,
                "age_s": mixer_age,
                "deck": mixer_decks,
            },
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
            "palette_control": palette_control_status,
            "deck": deck,
        }
        with self._snapshot_lock:
            self._published_snapshot = snapshot
            self._led_color_engine_status = dict(color_engine_status)

    def start_session_recording(self, path: str, *, dedup: bool = False) -> bool:
        if self._recorder:
            return False
        # schema=2 so the session carries B1 autoloop_phase rows + an integrity
        # footer. The tracer is attached ONLY here (recording explicitly enabled);
        # the env/from_env construction path stays schema-1 with no tracer.
        self._recorder = SessionRecorder(path, dedup=dedup, schema=2)
        self._phase_tracer = AutoloopPhaseTracer(self._recorder.write_phase_row)
        log.info(
            "[SM] record-session-start  path=%s  dedup=%s  phase_trace=on",
            path, "on" if dedup else "off",
        )
        return True

    def stop_session_recording(self) -> bool:
        if not self._recorder:
            return False
        path = str(self._recorder.path)
        # Tear down the phase tracer FIRST: stop new emits, drain the writer into
        # the still-open recorder, write an integrity footer, THEN close the
        # recorder. Closing the recorder first would make write_phase_row a silent
        # no-op and lose queued rows.
        tracer = self._phase_tracer
        self._phase_tracer = None
        if tracer is not None:
            result = tracer.close()
            self._recorder.write_phase_trace_footer(
                dropped=result.dropped,
                undrained=result.undrained,
                close_ok=result.ok,
                timed_out=result.timed_out,
                writer_error=result.writer_error,
            )
            if not result.ok:
                log.warning(
                    "[SM] phase-trace close NOT clean (capture invalid)  dropped=%d  "
                    "undrained=%d  timed_out=%s  writer_error=%s",
                    result.dropped, result.undrained, result.timed_out, result.writer_error,
                )
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
                with bridge_log.event_scope(
                    ev.kind,
                    deck=ev.deck,
                    trace_id=str(payload.get("__trace_id", "")),
                ):
                    self._handle_event(ev)
                    enqueue_mono = payload.pop("__enqueue_mono", None)
                    latency_ms = (
                        (time.monotonic() - float(enqueue_mono)) * 1000.0
                        if enqueue_mono is not None else 0.0
                    )
                    warn_ms = _TC_LATENCY_WARN_MS if ev.kind == Ev.TC_UPDATE else _LATENCY_WARN_MS
                    if latency_ms > warn_ms:
                        log.warning("[SM] event-late  kind=%s  latency_ms=%d", ev.kind, int(latency_ms))
                    elif log.isEnabledFor(logging.DEBUG):
                        log.debug("event processed %.1fms kind=%s", latency_ms, ev.kind)
            except Exception:
                log.error("StateManager: error handling %s", ev.kind, exc_info=True)

    # ── Event dispatch ────────────────────────────────────────────────────────

    def _handle_event(self, ev: BridgeEvent) -> None:
        if log.isEnabledFor(logging.DEBUG):
            payload = {k: v for k, v in ev.payload.items() if not k.startswith("__")}
            log.debug("event received kind=%s src=%s payload=%s", ev.kind, ev.source, payload)
        d = ev.deck

        if ev.kind == Ev.MIXER_STATE:
            snapshot = ev.payload.get("snapshot")
            if isinstance(snapshot, MixerAuthoritySnapshot):
                self._mixer_snapshot = snapshot
                self._rerun_active_deck_resolver("mixer_state")

        elif ev.kind == Ev.MASTER_CHANGED:
            if self._mixer_authority_enabled and ev.source == "rb_state":
                raw_deck = ev.payload.get("rb_raw_deck")
                if d in (1, 2):
                    if raw_deck not in (0, 1):
                        self._invalidate_rb_master(
                            ev.payload.get("reason") or "unsupported_raw_deck"
                        )
                        return
                    self._os.rb_master_deck = d
                    self._os.rb_master_deck_valid = True
                    self._os.rb_master_deck_source = ev.source
                    self._os.rb_master_deck_updated_at = time.monotonic()
                    self._os.rb_master_fallback_reason = ""
                else:
                    self._invalidate_rb_master(ev.payload.get("reason") or "invalid_deck")
                    return
                self._rerun_active_deck_resolver("rb_master")
            else:
                self._request_legacy_active_deck(d, ev.source)

        elif ev.kind == Ev.LEGACY_ACTIVE_DECK:
            self._request_legacy_active_deck(d, ev.source)

        elif ev.kind == Ev.TRACK_LOADED:
            if d not in (1, 2):
                log.info("[SM] load-ignored  deck=%s  reason=invalid_deck", d)
                return
            if self._is_playing_sibling_load(d, ev):
                log.info(
                    "[SM] load-ignored  deck=%d  reason=playing_sibling  rb_raw_deck=%s",
                    d, ev.payload.get("rb_raw_deck"),
                )
                return
            self._on_track_loaded(d, ev.payload.get("title", ""), ev)

        elif ev.kind == Ev.PLAY:
            if d not in (1, 2):
                return
            if not self._deck[d].playing:
                log.info("[SM] play  deck=%d  src=%s", d, ev.source)
            raw_deck = ev.payload.get("rb_raw_deck")
            if type(raw_deck) is int:
                self._deck_play_owner[d] = raw_deck
            self._deck[d].playing = True
            self._rerun_active_deck_resolver("play")

        elif ev.kind == Ev.PAUSE:
            if d not in (1, 2):
                return
            if self._deck[d].playing:
                log.info("[SM] pause  deck=%d  src=%s", d, ev.source)
            self._deck[d].playing = False
            if d == self._os.active_deck:
                self._os.play_settle_after = 0.0
            self._rerun_active_deck_resolver("pause")

        elif ev.kind == Ev.FILEPATH_RESOLVED:
            if d not in (1, 2):
                log.info("[SM] resolve-ignored  deck=%s  reason=invalid_deck", d)
                return
            self._on_filepath_resolved(d, ev.payload)

        elif ev.kind == Ev.ANLZ_PATH:
            if d not in (1, 2):
                log.info("[SM] anlz-path-ignored  deck=%s  reason=invalid_deck", d)
                return
            if self._is_playing_sibling_load(d, ev):
                log.info(
                    "[SM] anlz-path-ignored  deck=%d  reason=playing_sibling  rb_raw_deck=%s",
                    d, ev.payload.get("rb_raw_deck"),
                )
                return
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
                    self._drop_presentation_anlz_ready[ev.deck] = gen
                    self._maybe_build_drop_plan(ev.deck)
                else:
                    log.debug("[SM] anlz-drops-stale  deck=%d  gen=%d  current=%d",
                              ev.deck, gen, d_obj.load_gen)

        elif ev.kind == Ev.TC_UPDATE:
            if ev.deck not in (1, 2):
                return
            tc_ms = ev.payload.get('elapsed_ms', 0)
            if tc_ms > 0:
                pitch = ev.payload.get('pitch_factor', 1.0)
                self._tc_anchor[ev.deck] = (tc_ms, ev.mono, pitch)

        elif ev.kind == Ev.BPM_UPDATE:
            if d not in (1, 2):
                return
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
            if d not in (1, 2):
                log.info("[SM] scripted-arm-ignored  deck=%s  reason=invalid_deck", d)
                return
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
            if d not in (1, 2):
                log.info("[SM] scripted-clear-ignored  deck=%s  reason=invalid_deck", d)
                return
            self._arm_unscripted(d)

        elif ev.kind == Ev.RB_RESTARTED:
            # FM-11: force stop immediately — don't wait for stale detection
            log.info("[SM] rb-restart  pid=%d  action=stop", ev.payload.get("pid", 0))
            self._pending_arm = None
            for d in self._deck.values():
                d.playing = False
                d.scripted_id = 0
            if self._os.was_playing and self._os.active_deck in (1, 2):
                self._do_stop(self._os.active_deck, self._os.last_beat_elapsed_ms)
                self._dispatch_led_idle_ambient(
                    active=self._os.active_deck,
                    d=self._deck[self._os.active_deck],
                    reason="rb_restart",
                )
            self._tc_anchor = {1: (0, 0.0, 1.0), 2: (0, 0.0, 1.0)}
            self._rerun_active_deck_resolver("rb_restarted")
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
        elif ev.kind == Ev.LED_TRACK_IDENTITY:
            self._handle_led_track_identity(ev)
        elif ev.kind == Ev.LED_ENGINE_MODE:
            self._set_led_engine_mode(str(ev.payload.get("mode", "v1")))
        elif ev.kind == Ev.LED_MAX_ENERGY_PAD:
            self._toggle_led_max_energy()
        elif ev.kind in {
            Ev.LED_PALETTE_PAD,
            Ev.LED_PALETTE_LOCK_PAD,
            Ev.LED_MUTE_PAD,
            Ev.LED_RAINBOW_PAD,
            Ev.LED_ZONE_PAD,
            Ev.LED_MANUAL_PAD,
        }:
            coordinator = getattr(self, "_led_palette_control", None)
            if coordinator is not None:
                coordinator.handle_event(ev)

        elif ev.kind == Ev.LASER_SOLO_PAD:
            self._drop_presentation_solo_pad_pressed()

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
                bridge_log.perf(
                    "override",
                    "laser %s (from %s)",
                    "on" if self._laser_director.is_enabled() else "off",
                    ev.source,
                    data={
                        "surface": "laser",
                        "action": "toggle",
                        "source": ev.source,
                        "enabled": self._laser_director.is_enabled(),
                    },
                )
            elif ev.kind == Ev.LASER_SET_ENABLED:
                enabled = bool(ev.payload.get("enabled", False))
                self._laser_director.set_enabled(enabled)
                if not enabled and self._laser_executor is not None:
                    self._laser_executor.clear_pending_blackout(
                        reason="laser_director_disabled"
                    )
                bridge_log.perf(
                    "override",
                    "laser %s (from %s)",
                    "on" if enabled else "off",
                    ev.source,
                    data={
                        "surface": "laser",
                        "action": "set_enabled",
                        "source": ev.source,
                        "enabled": enabled,
                    },
                )
            elif ev.kind == Ev.LASER_SCENE:
                scene = str(ev.payload.get("scene", ""))
                ttl_s = float(ev.payload.get("ttl_s", 4.0))
                if scene:
                    self._laser_director.set_manual_override(scene, ttl_s)
                    bridge_log.perf(
                        "override",
                        "laser manual scene %s (from %s)",
                        scene,
                        ev.source,
                        data={
                            "surface": "laser",
                            "action": "scene",
                            "source": ev.source,
                            "scene": scene,
                            "ttl_s": ttl_s,
                        },
                    )
            elif ev.kind == Ev.LASER_BLACKOUT:
                self._laser_director.set_emergency_blackout(True)
                bridge_log.perf(
                    "override",
                    "laser blackout — all laser output off (from %s)",
                    ev.source,
                    data={"surface": "laser", "action": "blackout", "source": ev.source},
                )
            elif ev.kind == Ev.LASER_CLEAR_BLACKOUT:
                self._laser_director.clear_emergency_blackout()
                bridge_log.perf(
                    "override",
                    "laser blackout released (from %s)",
                    ev.source,
                    data={"surface": "laser", "action": "clear_blackout", "source": ev.source},
                )
            elif ev.kind == Ev.LASER_CLEAR_SCENE_OVERRIDE:
                self._laser_director.clear_manual_override()
                bridge_log.perf(
                    "override",
                    "laser manual scene released (from %s)",
                    ev.source,
                    data={
                        "surface": "laser",
                        "action": "clear_scene_override",
                        "source": ev.source,
                    },
                )
            elif ev.kind == Ev.LASER_SET_PERSONALITY:
                if ev.source not in {"test", "unit_test", "internal"}:
                    log.warning(
                        "[PERSONALITY] external LASER_SET_PERSONALITY source=%s",
                        ev.source or "unknown",
                    )
                personality_name = str(ev.payload.get("personality", ""))
                provider = self._laser_personality_provider
                applied = False
                if provider is None:
                    self._laser_director.set_personality(personality_name)
                    applied = True
                else:
                    personality_cfg = provider(personality_name)
                    if personality_cfg is not None:
                        self._apply_personality_change(personality_name, personality_cfg)
                        applied = True
                if applied:
                    bridge_log.perf(
                        "override",
                        "laser personality %s (from %s)",
                        personality_name,
                        ev.source,
                        data={
                            "surface": "laser",
                            "action": "set_personality",
                            "source": ev.source,
                            "personality": personality_name,
                        },
                    )

    def _handle_led_track_identity(self, ev: BridgeEvent) -> None:
        deck = int(ev.payload.get("deck", ev.deck))
        if deck not in (1, 2):
            return
        d = self._deck[deck]
        load_gen = int(ev.payload.get("load_gen", -1))
        if load_gen != d.load_gen:
            log.debug("[LED] identity-stale deck=%d gen=%d current=%d", deck, load_gen, d.load_gen)
            return
        key = str(ev.payload.get("key") or "")
        record = ev.payload.get("record")
        if not key or not isinstance(record, dict):
            return
        store_record = self._led_identity_store.get(key)
        mutated = False
        if record.get("base") == "measured":
            mutated = self._led_identity_store.freeze(key, record)
            store_record = self._led_identity_store.get(key)
        elif store_record is None:
            store_record = dict(record)
        final_record = store_record or dict(record)
        engine = self._led_color_engine
        set_identity = getattr(engine, "set_track_identity", None)
        if callable(set_identity):
            set_identity(deck, load_gen, key, final_record)
        if mutated and self._led_identity_writer is not None:
            self._led_identity_writer.submit(self._led_identity_store.to_dict())
        zone = str((final_record.get("correction") or {}).get("zone") or final_record.get("zone") or "NEUTRAL")
        log.info(
            "[LED] identity deck=%d zone=%s slot=%s depth=%s corrected=%s key=%s",
            deck,
            zone,
            final_record.get("hue_slot", "-"),
            final_record.get("depth_variant", "-"),
            "yes" if final_record.get("correction") else "no",
            bf.short(key),
        )

    def _set_led_engine_mode(self, mode: str) -> None:
        if mode not in {"v1", "v2"}:
            return
        if mode == "v2" and not self._v2_identity_enabled:
            log.info("[LED] engine v2 ignored reason=not_configured")
            mode = "v1"
        next_latch = mode == "v2"
        if self._led_v2_latch == next_latch:
            return
        self._led_v2_latch = next_latch
        if not next_latch:
            self._led_max_energy_armed = False
        engine = self._led_color_engine
        set_v2_active = getattr(engine, "set_v2_active", None)
        if callable(set_v2_active):
            set_v2_active(next_latch)
        log.info("[LED] engine mode=%s", "v2" if next_latch else "v1")
        control = getattr(self, "_led_palette_control", None)
        if control is not None:
            control.publish_feedback()

    def _toggle_led_max_energy(self) -> None:
        if not self._led_v2_latch:
            return
        self._led_max_energy_armed = not bool(getattr(self, "_led_max_energy_armed", False))
        log.info("[LED] max_energy %s", "armed" if self._led_max_energy_armed else "disarmed")
        control = getattr(self, "_led_palette_control", None)
        if control is not None:
            control.publish_feedback()

    def _active_led_identity_key(self) -> tuple[int, str]:
        deck = self._os.active_deck
        if deck not in (1, 2):
            return (0, "")
        meta = self._deck[deck].meta
        if not meta.content_id and not meta.filepath:
            return (deck, "")
        return (deck, led_identity_content_key(str(meta.content_id or ""), str(meta.filepath or "")))

    def _apply_led_zone_correction(self, zone: str) -> None:
        deck, key = self._active_led_identity_key()
        if deck not in (1, 2) or not key:
            return
        mutated = self._led_identity_store.set_correction(key, zone)
        record = self._led_identity_store.get(key)
        if record is None:
            return
        set_identity = getattr(self._led_color_engine, "set_track_identity", None)
        if callable(set_identity):
            set_identity(deck, self._deck[deck].load_gen, key, record)
        if mutated and self._led_identity_writer is not None:
            self._led_identity_writer.submit(self._led_identity_store.to_dict())

    def _clear_led_zone_correction(self) -> None:
        deck, key = self._active_led_identity_key()
        if deck not in (1, 2) or not key:
            return
        mutated = self._led_identity_store.clear_correction(key)
        record = self._led_identity_store.get(key)
        if record is not None:
            set_identity = getattr(self._led_color_engine, "set_track_identity", None)
            if callable(set_identity):
                set_identity(deck, self._deck[deck].load_gen, key, record)
        if mutated and self._led_identity_writer is not None:
            self._led_identity_writer.submit(self._led_identity_store.to_dict())

    def _mixer_valid_fresh(self, now: float) -> bool:
        if not self._mixer_authority_enabled:
            return False
        if not self._mixer_snapshot.valid or self._mixer_snapshot.updated_at <= 0.0:
            return False
        return (now - self._mixer_snapshot.updated_at) <= MIXER_STALE_AFTER_S

    def _resolver_deck_inputs(self) -> dict[int, ResolverDeckInput]:
        out: dict[int, ResolverDeckInput] = {}
        for deck_num, reading in self._mixer_snapshot.deck.items():
            if deck_num not in (1, 2):
                continue
            out[deck_num] = ResolverDeckInput(
                playing=bool(self._deck[deck_num].playing),
                upfader_raw=reading.upfader_raw,
                upfader_norm=reading.upfader_norm,
                upfader_label=reading.upfader_label,
                low_raw=reading.low_raw,
                low_norm=reading.low_norm,
                low_label=reading.low_label,
            )
        if not out:
            for deck_num in (1, 2):
                out[deck_num] = ResolverDeckInput(
                    playing=bool(self._deck[deck_num].playing),
                    upfader_raw=0.0,
                    upfader_norm=0.0,
                    upfader_label="down",
                    low_raw=127.5,
                    low_norm=0.5,
                    low_label="neutral",
                )
        return out

    def _rerun_active_deck_resolver(self, source: str) -> None:
        if not self._mixer_authority_enabled:
            return
        now = time.monotonic()
        decision = resolve_active_deck(
            current_active_deck=self._os.active_deck,
            rb_master_deck=self._os.rb_master_deck,
            rb_master_deck_valid=self._os.rb_master_deck_valid,
            rb_master_deck_source=self._os.rb_master_deck_source,
            rb_master_deck_updated_at=self._os.rb_master_deck_updated_at,
            rb_master_fallback_reason=self._os.rb_master_fallback_reason,
            deck=self._resolver_deck_inputs(),
            mixer_valid=self._mixer_snapshot.valid,
            mixer_updated_at=self._mixer_snapshot.updated_at,
            mixer_reason=self._mixer_snapshot.reason,
            state=self._active_deck_resolver_state,
            now=now,
        )
        self._active_deck_resolver_state = decision.state
        self._os.active_deck_authority_reason = decision.authority_reason
        self._os.mixer_authority_valid = self._mixer_valid_fresh(now)
        self._os.mixer_authority_updated_at = self._mixer_snapshot.updated_at
        self._os.mixer_fallback_reason = decision.fallback_reason
        if decision.active_deck != self._os.active_deck:
            self._apply_resolved_active_deck(
                decision.active_deck,
                source=source,
                reason=decision.authority_reason,
            )

    def _invalidate_rb_master(self, reason: str) -> None:
        self._os.rb_master_deck = None
        self._os.rb_master_deck_valid = False
        self._os.rb_master_deck_source = "rb_state"
        self._os.rb_master_deck_updated_at = time.monotonic()
        self._os.rb_master_fallback_reason = reason
        self._rerun_active_deck_resolver("rb_master_invalid")

    # ── Deck switch ───────────────────────────────────────────────────────────

    def _on_master_changed(self, new_deck: int, source: str) -> None:
        self._request_legacy_active_deck(new_deck, source)

    def _request_legacy_active_deck(self, new_deck: int, source: str) -> None:
        if new_deck not in (1, 2):
            return
        if self._mixer_authority_enabled:
            self._rerun_active_deck_resolver("legacy_active_ignored")
            return
        self._apply_resolved_active_deck(
            new_deck,
            source=source,
            reason="legacy_active_deck_fallback",
        )

    def _apply_resolved_active_deck(self, new_deck: int, *, source: str, reason: str) -> None:
        old_deck = self._os.active_deck
        if new_deck == old_deck:
            return
        if new_deck not in (0, 1, 2):
            return
        bridge_log.perf(
            "deck",
            "switch %d->%d (%s)",
            old_deck,
            new_deck,
            reason,
            deck=new_deck,
            data={"old": old_deck, "new": new_deck, "src": source, "reason": reason},
        )
        if old_deck in (1, 2) and new_deck in (1, 2):
            self._apply_nonzero_active_deck_switch(old_deck, new_deck, source)
            return
        if new_deck == 0:
            self._os.active_deck = 0
            self._enter_idle_no_audible(reason=reason)
            return
        self._os.active_deck = new_deck
        self._last_audible_deck = new_deck
        self._reset_for_active_deck_entry(new_deck, source)

    def _apply_nonzero_active_deck_switch(self, old_deck: int, new_deck: int, source: str) -> None:
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
        self._drop_presentation_gearshift_check(old_deck, new_deck)
        self._os.active_deck = new_deck
        self._last_audible_deck = new_deck
        self._led_hold_active = True
        self._led_hold_started_mono = 0.0
        self._led_hold_started_beat = None
        self._reset_for_active_deck_entry(new_deck, source)

    def _drop_presentation_gearshift_check(self, old_deck: int, new_deck: int) -> None:
        """Tier 5 (authority doc): compute the BPM-jump delta live-then-meta on
        BOTH sides of a real deck-to-deck handover (a pitched deck plays its
        live tempo, not its tag). Never fires on the session's first master
        because this method is only reached from a deck->deck switch, never
        the 0->deck entry path."""
        if not self._drop_presentation_config.enabled:
            return
        outgoing = self._autoloop.live_bpm_value(old_deck)
        if outgoing is None or outgoing <= 0:
            outgoing = self._deck[old_deck].meta.bpm or None
        incoming = self._autoloop.live_bpm_value(new_deck)
        if incoming is None or incoming <= 0:
            incoming = self._deck[new_deck].meta.bpm or None
        if gearshift_qualifies(outgoing, incoming, self._drop_presentation_config.gearshift_bpm_jump):
            new_d = self._deck[new_deck]
            self._drop_presentation_session.set_gearshift_pending((new_deck, new_d.load_gen))
            log.info(
                "[SM] drop-presentation-gearshift  deck=%d→%d  bpm=%.1f→%.1f",
                old_deck, new_deck, outgoing or 0.0, incoming or 0.0,
            )

    def _reset_for_active_deck_entry(self, new_deck: int, source: str) -> None:
        new_d = self._deck[new_deck]
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
        self._led_clear_dispatch_retries()
        self._clear_led_drop_lifecycle()
        self._clear_smart_rearm_state()
        self._autoloop.clear_arm_phrase_lock()
        self._autoloop.clear_live_bpm_follow()
        self._autoloop.clear_tempo_relock()
        self._autoloop.clear_pending_master_phrase_arm()
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="master_changed")
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason="master_changed")
        self._reset_native_autoloop()
        if (
            self._personality_eligible_deck.get(new_deck, False)
            and new_d.meta.content_id
        ):
            self._resolve_personality_for_deck(
                new_deck,
                new_d.meta,
                trigger="active_deck_changed",
            )
        # The new master's ANLZ data / hot-cue tags may have already resolved
        # while it was only "loaded" (not yet active) -- (re)attempt the plan
        # now that _maybe_build_drop_plan's active-deck guard will pass.
        self._maybe_build_drop_plan(new_deck)

    def _enter_idle_no_audible(self, *, reason: str) -> None:
        self._pending_arm = None
        self._tc_anchor = {1: (0, 0.0, 1.0), 2: (0, 0.0, 1.0)}
        self._os.was_playing = False
        self._os.play_settle_after = 0.0
        self._os.not_playing_since = 0.0
        self._os.last_sent_bpm = 0.0
        self._os.autoloop_arm_bpm = 0.0
        self._os.autoloop_arm_deck = 0
        self._os.last_autoloop_status_phrase_beat = 0
        self._os.lighting_mode = "idle"
        self._os.lighting_desired = "idle"
        self._os.lighting_stable_since = 0.0
        self._os.last_armed_filepath = ""
        self._led_rt_permitted = False
        self._led_rt_beat = None
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""
        self._led_smart_drop_blackout_key = ""
        self._led_clear_dispatch_retries()
        self._led_hold_active = False
        self._led_hold_started_mono = 0.0
        self._led_hold_started_beat = None
        self._clear_led_drop_lifecycle()
        self._clear_smart_rearm_state()
        self._autoloop.clear_arm_phrase_lock()
        self._autoloop.clear_live_bpm_follow()
        self._autoloop.clear_tempo_relock()
        self._autoloop.clear_tempo_anchor()
        self._autoloop.clear_pending_master_phrase_arm()
        self._clear_idle_lighting_outputs()
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason=reason)
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason=reason)
        self._reset_native_autoloop()
        deck = self._last_audible_deck if self._last_audible_deck in (1, 2) else 1
        self._dispatch_led_idle_ambient(
            active=deck,
            d=self._deck[deck],
            reason="idle_no_audible",
        )

    # ── Track load → lsof trigger ─────────────────────────────────────────────

    def _is_playing_sibling_load(self, deck: int, ev: BridgeEvent) -> bool:
        """True when a load/anlz event comes from the idle RB sibling of a deck
        whose owning RB deck is currently playing.

        RB decks 1&3 share bridge deck 1 (2&4 share 2). The reader diffs each RB
        deck's buffers independently, so a transient title/anlz write on the idle
        sibling emits events onto the playing bridge slot and clobbers its
        metadata (observed live 2026-07-02: mid-autoloop Wanton→BLACKPINK→Wanton
        flap armed and then tore down the wrong scripted show). A real load onto
        the playing RB deck itself is unaffected (RB stops the deck on load, and
        same-owner events always pass). Fail-open: events without rb_raw_deck, or
        with no recorded play owner, are accepted unchanged.
        """
        if not self._deck[deck].playing:
            return False
        raw_deck = ev.payload.get("rb_raw_deck")
        owner = self._deck_play_owner.get(deck)
        return type(raw_deck) is int and type(owner) is int and raw_deck != owner

    def _on_track_loaded(self, deck: int, title: str, ev: BridgeEvent) -> None:
        d = self._deck[deck]
        d.meta.clear()
        d.scripted_id = 0
        self._personality_eligible_deck[deck] = False
        d.load_gen += 1
        self._loaded_anlz_path.pop(deck, None)
        if deck == self._os.active_deck:
            self._led_hold_active = True
            self._led_hold_started_mono = 0.0
            self._led_hold_started_beat = None
            self._clear_led_drop_lifecycle()
            self._clear_smart_rearm_state()
            self._autoloop.clear_arm_phrase_lock()
            self._autoloop.clear_live_bpm_follow()
            self._autoloop.clear_tempo_relock()
            self._autoloop.clear_pending_master_phrase_arm()
            if self._laser_executor is not None:
                self._laser_executor.reset_runtime_state(reason="active_track_loaded")
            if self._laser_director is not None:
                self._laser_director.reset_runtime_state(reason="active_track_loaded")
            self._reset_native_autoloop()
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

        if self._resolver is None:
            return

        # Prefer ANLZ-based resolution (no subprocess, fires before this event)
        anlz_path = self._pending_anlz_path.pop(deck, None)
        if anlz_path:
            log.debug("track load: deck %d using ANLZ path for resolution", deck)
            self._resolver.resolve_by_anlz(deck, d.load_gen, anlz_path, trace_id=trace_id)
            if self._smart_rearm_experiment or self._v2_identity_enabled:
                self._loaded_anlz_path[deck] = (anlz_path, d.load_gen)
            if self._smart_rearm_experiment:
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
        identity_enabled: bool = False,
        identity_key: str = "",
        identity_config: IdentityV2Config | None = None,
        wide_window: bool = False,
    ) -> None:
        eq = self._eq
        source = "anlz_spectral" if spectral_enabled else ("anlz_identity" if identity_enabled else "anlz")

        def _anlz_worker(path: str, bridge_deck: int, gen: int) -> None:
            try:
                result = _read_runtime_anlz_data(
                    path,
                    audio_filepath=audio_filepath,
                    spectral_enabled=spectral_enabled,
                    identity_enabled=identity_enabled,
                    identity_key=identity_key,
                    identity_config=identity_config,
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
            if result.led_identity is not None:
                try:
                    eq.put_nowait(BridgeEvent(
                        kind=Ev.LED_TRACK_IDENTITY,
                        deck=bridge_deck,
                        payload={
                            "deck": bridge_deck,
                            "load_gen": gen,
                            "key": identity_key,
                            "record": result.led_identity,
                        },
                        source=source,
                    ))
                except queue.Full:
                    log.warning("[SM] queue-full  event=led-track-identity  deck=%d", bridge_deck)

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
        # Authority doc reset boundary: personality application changes the role
        # banks, so the latched native Autoloop look must drop; the next fire edge
        # re-anchors from the new banks (a one-tick zero gap is preferred over stale).
        self._reset_native_autoloop()
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
        # Drop presentation hot-cue tags (Task 2): absent on the lsof/title
        # fallback paths, which simply carry no tags -- fail-open, never a crash.
        self._drop_presentation_tag_beats[deck] = tuple(
            float(b) for b in payload.get("laser_tag_beats", [])
        )
        self._drop_presentation_tags_ready[deck] = gen
        self._maybe_build_drop_plan(deck)
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
        if self._spectral_enable or self._v2_identity_enabled:
            loaded_anlz = self._loaded_anlz_path.pop(deck, None)
            if loaded_anlz is not None:
                anlz_path, anlz_gen = loaded_anlz
                if anlz_gen == d.load_gen:
                    worker_kwargs = {
                        "audio_filepath": meta.filepath,
                        "spectral_enabled": self._spectral_enable,
                        "wide_window": self._wide_window_enable,
                    }
                    if self._v2_identity_enabled:
                        worker_kwargs.update(
                            identity_enabled=True,
                            identity_key=led_identity_content_key(
                                str(meta.content_id or ""),
                                str(meta.filepath or ""),
                            ),
                            identity_config=self._v2_identity_cfg,
                        )
                    self._start_anlz_worker(
                        anlz_path,
                        deck,
                        d.load_gen,
                        **worker_kwargs,
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

    # ── Drop presentation: static per-track plan ──────────────────────────────

    def _maybe_build_drop_plan(self, deck: int) -> None:
        """Build the TrackPlan once BOTH ANLZ data and hot-cue tags have landed
        for this exact load (Task 4 item 1). Before that, and for the inactive
        deck, drops fail-open to leds_plus_lasers via the None-plan fallback in
        the per-tick wiring below. Pure reads off already-published DeckState;
        no I/O here (the DB read already happened in filepath_resolver; the
        learned store was loaded once at startup)."""
        if deck != self._os.active_deck:
            return
        d = self._deck.get(deck)
        if d is None:
            return
        load_gen = d.load_gen
        if (
            self._drop_presentation_anlz_ready.get(deck) != load_gen
            or self._drop_presentation_tags_ready.get(deck) != load_gen
        ):
            return
        content_id = str(d.meta.content_id or "")
        drop_beats = tuple(float(b) for b in d.meta.smart_drops)
        phrase_roles = self._build_phrase_segments(d)
        tag_beats = self._drop_presentation_tag_beats.get(deck, ())
        learned_beats = (
            self._drop_presentation_learned_store.beats_for_track(content_id)
            if content_id else ()
        )
        self._drop_presentation_plan = plan_track(
            drop_beats, phrase_roles, tag_beats, learned_beats,
            self._drop_presentation_config,
        )
        self._drop_presentation_plan_deck = deck
        self._drop_presentation_plan_load_gen = load_gen
        self._drop_presentation_plan_content_id = content_id
        if self._drop_presentation_plan.unmatched_tag_beats:
            log.info(
                "[SM] drop-presentation-unmatched-tags  deck=%d  beats=%s",
                deck,
                ",".join(f"{b:.1f}" for b in self._drop_presentation_plan.unmatched_tag_beats),
            )

    # ── Drop presentation: per-tick ladder + window ───────────────────────────

    def _drop_presentation_tick(
        self, *, active: int, d: DeckState, sp_state: SmartPhrasingState, impact_now: bool,
    ) -> None:
        """Feed the WindowMachine once per push tick (Task 4 item 3). Pure reads
        off already-computed locals/DeckState; the only mutation is the
        session/learned-store bookkeeping committed at the exact impact tick
        below (in-memory only — the learned-store FILE write rides the
        background writer thread, never this thread's tick path)."""
        cfg = self._drop_presentation_config
        if not cfg.enabled:
            return
        if self._os.lighting_mode == "scripted":
            # Required Behavior Test 9: zero policy activity end-to-end on a
            # scripted track -- no plan lookup, no ladder evaluation, no
            # session/learned-store mutation. Still tick the window machine
            # (scripted_mode=True) so a dark/suppressed state left over from a
            # PRIOR autoloop track's window restores via its universal
            # fail-open, rather than latching until the next autoloop track.
            actions = self._drop_presentation_window.tick(
                WindowInputs(
                    abs_beat=sp_state.abs_beat, beats_to_next_drop=None, next_drop_beat=None,
                    drop_role="none", impact_now=False, laser_visible=False,
                    scripted_mode=True, stopped=not d.playing,
                ),
                pending_presentation=None, pending_reason="",
            )
            self._drop_presentation_apply_actions(actions)
            self._drop_presentation_last_actions = actions
            self._drop_presentation_last_pending = (None, "", None)
            self._drop_presentation_manual_cancel = False
            return
        # AWR-140 follow-up: the Laser Director now emits reason="drop_crossing" for the capped
        # 2nd-chorus LABEL re-arm too (armed_this_tick without a smart-drop marker). A label re-arm
        # is NOT a drop-presentation impact -- presentation stays per true drop / smart-drop marker
        # (AWR-139). Require a real marker crossing this tick so a 2nd-chorus re-arm cannot re-enter
        # or extend the window, re-fire the presentation verdict, or double-count drop stats.
        impact_now = bool(impact_now and sp_state.smart_drop_crossing)
        session = self._drop_presentation_session
        track_key = (active, d.load_gen)
        previous_load_gen = self._drop_presentation_last_load_gen.get(active)
        track_changed = previous_load_gen is not None and previous_load_gen != d.load_gen
        previous_active_deck = self._drop_presentation_last_active_deck
        active_deck_changed = previous_active_deck is not None and previous_active_deck != active
        self._drop_presentation_last_load_gen[active] = d.load_gen
        self._drop_presentation_last_active_deck = active

        # Opening-damper ≥16-beat audible latch: count a track once its deck
        # has been the audible active deck (playing) for >=16 beats since
        # load, once per (deck, load_gen). A loaded-but-never-audible deck
        # never reaches d.playing here and so never counts.
        if d.playing and sp_state.abs_beat is not None:
            start_beat = self._drop_presentation_audible_start_beat.get(track_key)
            if start_beat is None:
                self._drop_presentation_audible_start_beat[track_key] = sp_state.abs_beat
            elif (sp_state.abs_beat - start_beat) >= AUDIBLE_DAMPER_BEATS:
                session.mark_track_counted(active, d.load_gen)

        role = "none"
        if sp_state.smart_drop_crossing:
            role = "drop"
        elif sp_state.current_phrase_is_chorus or sp_state.smart_post_drop_active:
            role = "post_drop"

        plan = self._drop_presentation_plan
        plan_current = (
            plan is not None
            and self._drop_presentation_plan_deck == active
            and self._drop_presentation_plan_load_gen == d.load_gen
        )
        eval_beat = sp_state.active_drop_beat if impact_now else sp_state.next_smart_drop_beat
        decision = (
            plan.decision_for(eval_beat)
            if plan_current and eval_beat is not None
            else None
        )

        pending_presentation: Optional[str] = None
        pending_reason = ""
        auto_solo_fired = False
        armed = self._drop_presentation_armed_key == track_key
        presentation_impact = bool(
            impact_now
            and (
                armed
                or (decision is not None and (decision.runway > 0.0 or decision.tagged))
            )
        )
        if decision is not None:
            gearshift_pending = session.gearshift_pending_for(track_key)
            record_breaking = session.is_record_breaking(decision.runway, cfg.record_min_drops)
            auto_solo_used = session.auto_solo_used(track_key)
            damper_active = session.damper_active(cfg.opening_tracks)
            vetoed = session.is_vetoed(track_key, decision.beat)
            pending_presentation, pending_reason, auto_solo_fired = resolve_presentation(
                decision,
                armed=armed,
                gearshift_pending=gearshift_pending,
                record_breaking=record_breaking,
                auto_solo_used=auto_solo_used,
                damper_active=damper_active,
                vetoed=vetoed,
            )
        elif impact_now:
            if armed:
                # AWR-159 Task 2: a manual arm is an explicit operator
                # override -- honor it even when the plan has no exact-beat
                # match for this impact (the plan-unavailable fallback below
                # stays for the non-manual case only).
                pending_presentation, pending_reason = LASERS_ONLY, "solo_manual"
            else:
                # Plan not finalized yet (ANLZ/tags still resolving) -- fail-open
                # to today's behavior, exactly as the spec requires.
                pending_presentation, pending_reason = LEDS_PLUS_LASERS, "plan_unavailable"

        laser_masked = False
        if self._laser_executor is not None:
            laser_masked = bool(self._laser_executor.mask_owners_active())
        midi_input = getattr(self._pack_runtime, "midi_input", None)
        if midi_input is not None:
            try:
                laser_masked = laser_masked or bool(midi_input.snapshot().blackout_held)
            except Exception:
                laser_masked = True  # fail toward "not visible", never toward a dark room
        laser_enabled = bool(
            self._laser_director is not None and self._laser_director.is_enabled()
        )
        laser_visible = (
            self._drop_presentation_base_live
            and role in ("drop", "post_drop")
            and not laser_masked
            and laser_enabled
        )

        inputs = WindowInputs(
            abs_beat=sp_state.abs_beat,
            beats_to_next_drop=sp_state.beats_to_next_drop,
            next_drop_beat=sp_state.next_smart_drop_beat,
            drop_role=role,
            impact_now=presentation_impact,
            laser_visible=laser_visible,
            stopped=not d.playing,
            track_changed=track_changed,
            active_deck_changed=active_deck_changed,
            manual_interaction=self._drop_presentation_manual_cancel,
        )
        # One-tick request, consumed regardless of this tick's impact_now (a
        # cancel is not an impact) -- AWR-159 Task 1.
        self._drop_presentation_manual_cancel = False
        actions = self._drop_presentation_window.tick(
            inputs, pending_presentation=pending_presentation, pending_reason=pending_reason,
        )
        self._drop_presentation_apply_actions(actions)
        self._drop_presentation_last_pending = (pending_presentation, pending_reason, eval_beat)
        self._drop_presentation_last_actions = actions

        if impact_now:
            if armed:
                # One-shot: consumed by this drop's impact regardless of guard
                # outcome or whether the plan had a decision for this beat
                # (AWR-159 Task 2) -- the arm targeted "the next true drop",
                # which has now happened.
                self._drop_presentation_armed_key = None
            if decision is not None:
                if auto_solo_fired:
                    session.mark_auto_solo_used(track_key)
                if session.gearshift_pending_for(track_key):
                    session.consume_gearshift_pending(track_key)
                if actions.reason == "solo_manual":
                    content_id = self._drop_presentation_plan_content_id
                    if content_id and self._drop_presentation_learned_store.record(content_id, decision.beat):
                        self._drop_presentation_learned_writer.submit(
                            self._drop_presentation_learned_store.to_dict()
                        )
                session.finalize_drop_observation(decision.runway, has_phrase_data=plan.has_phrase_data)
        # Recompute every tick (not just at impact): a cancel's fail-open, or
        # the window ending naturally, must reach the pad without waiting for
        # the next drop's impact tick or another press (AWR-159 Task 1).
        self._drop_presentation_update_solo_feedback()

    def _drop_presentation_apply_actions(self, actions: WindowActions) -> None:
        """Apply this tick's WindowMachine output. Idempotent: safe to call
        every tick even when nothing changed. LED pre-dark/solo-window dark
        rides the Package-2 owner SET (never touches other owners); base
        suppression never touches masks/blackout (soundswitch_laser_player)."""
        held = self._drop_presentation_led_dark_held
        if actions.led_dark_hold and not held:
            self._handle_led_event(BridgeEvent(
                kind=Ev.LED_BLACKOUT, deck=0,
                payload={"reason": "drop_spotlight"}, source="drop_presentation",
            ))
            self._drop_presentation_led_dark_held = True
        elif not actions.led_dark_hold and held:
            self._handle_led_event(BridgeEvent(
                kind=Ev.LED_CLEAR_BLACKOUT, deck=0,
                payload={"reason": "drop_spotlight"}, source="drop_presentation",
            ))
            self._drop_presentation_led_dark_held = False

        player = getattr(self._pack_runtime, "player", None)
        if player is not None and actions.base_suppressed != self._drop_presentation_base_suppressed_held:
            player.set_base_suppressed(actions.base_suppressed)
            self._drop_presentation_base_suppressed_held = actions.base_suppressed

    def _drop_presentation_release_on_stop(self) -> None:
        """Fail-open the drop-presentation window on a hard stop.

        The reader-stale stop branch (and any stop path that short-circuits
        before _drop_presentation_tick's sole call site) would otherwise leave a
        Laser-Solo / pre-dark LED dark-hold latched: _do_stop resets the lasers
        but never releases the drop_spotlight LED blackout owner, and
        _dispatch_led_idle_ambient then renders nothing while that owner is held
        -- a dark room until the reader recovers and the window ends on its own.
        Reuse the WindowMachine's universal stopped=True fail-open (tick returns
        _IDLE_ACTIONS regardless of phase) plus the idempotent action applier, so
        this releases the drop_spotlight owner and base suppression and returns
        the machine to idle. No-op when the policy is disabled (keeps
        enabled:false byte-identical) and idempotent (safe on every stop path,
        including healthy stops that also reach _drop_presentation_tick this
        tick). Pure/in-memory -- no I/O added to the 200 Hz path."""
        if not self._drop_presentation_config.enabled:
            return
        actions = self._drop_presentation_window.tick(
            WindowInputs(
                abs_beat=None, beats_to_next_drop=None, next_drop_beat=None,
                drop_role="none", impact_now=False, laser_visible=False,
                scripted_mode=False, stopped=True,
            ),
            pending_presentation=None, pending_reason="",
        )
        self._drop_presentation_apply_actions(actions)
        self._drop_presentation_last_actions = actions
        self._drop_presentation_last_pending = (None, "", None)
        self._drop_presentation_manual_cancel = False

    def _drop_presentation_update_solo_feedback(self) -> None:
        last_actions = self._drop_presentation_last_actions
        if last_actions is not None and last_actions.presentation == LASERS_ONLY:
            state = "active"
        elif self._drop_presentation_armed_key is not None:
            state = "armed"
        else:
            state = "armed" if self._drop_presentation_last_pending[0] == LASERS_ONLY else "off"
        if state != self._drop_presentation_solo_feedback:
            prev = self._drop_presentation_solo_feedback
            self._drop_presentation_solo_feedback = state
            bridge_log.perf(
                "override",
                "laser solo %s (was %s)",
                state,
                prev,
                data={
                    "surface": "laser",
                    "action": "solo_feedback",
                    "state": state,
                    "prev": prev,
                    "pending_reason": self._drop_presentation_last_pending[1] or "",
                    "armed_manual": self._drop_presentation_armed_key is not None,
                },
            )
            if self._led_palette_control is not None:
                self._led_palette_control.maybe_publish()

    def _drop_presentation_solo_pad_pressed(self) -> None:
        """Ev.LASER_SOLO_PAD: arm / disarm / veto / cancel-active per the
        authority doc's Solo Source Contracts. No-ops with no active deck;
        still allowed (and arms) during a scripted track, which only affects
        an autoloop-mode true drop later (authority doc §Scripted-Track
        Exemption). Four states from the pad's perspective: arm (idle ->
        armed), disarm (armed -> idle), veto (auto-tier pending -> idle), and
        cancel (window open -> idle, AWR-159 Task 1)."""
        cfg = self._drop_presentation_config
        if not cfg.enabled:
            return
        active = self._os.active_deck
        if active not in (1, 2):
            return
        d = self._deck[active]
        track_key = (active, d.load_gen)
        session = self._drop_presentation_session

        if self._drop_presentation_solo_feedback == "active":
            # A solo window is currently open (Govees dark). Request a
            # one-tick fail-open instead of falling through to "arm the next
            # drop", which used to leave the CURRENT dark window untouched.
            self._drop_presentation_manual_cancel = True
            bridge_log.perf(
                "override", "[LASER] solo-cancelled by=pad",
                data={"surface": "laser", "action": "solo_cancel"},
            )
            return

        if self._drop_presentation_armed_key == track_key:
            self._drop_presentation_armed_key = None
            self._drop_presentation_update_solo_feedback()
            return

        pending_presentation, pending_reason, pending_beat = self._drop_presentation_last_pending
        if pending_presentation == LASERS_ONLY and pending_reason != "solo_manual" and pending_beat is not None:
            # Veto: a non-manual tier is currently pending for the upcoming
            # drop. Learned solos are additionally un-learned (the recovery
            # path for a press that shouldn't stick); gear-shift/record simply
            # stop pending for this specific drop (session bookkeeping for
            # gear-shift's one-shot flag still clears normally at that drop's
            # own impact, vetoed or not).
            session.veto_beat(track_key, pending_beat)
            unlearned = False
            if pending_reason == "solo_learned":
                content_id = self._drop_presentation_plan_content_id
                unlearned = bool(
                    content_id
                    and self._drop_presentation_learned_store.remove(content_id, pending_beat)
                )
                if unlearned:
                    self._drop_presentation_learned_writer.submit(
                        self._drop_presentation_learned_store.to_dict()
                    )
            bridge_log.perf(
                "override",
                "laser solo veto (%s)",
                pending_reason,
                data={
                    "surface": "laser",
                    "action": "solo_veto",
                    "pending_reason": pending_reason,
                    "pending_beat": pending_beat,
                    "unlearned": unlearned,
                },
            )
            self._drop_presentation_update_solo_feedback()
            return

        self._drop_presentation_armed_key = track_key
        self._drop_presentation_update_solo_feedback()

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
                bridge_log.perf(
                    "scripted",
                    "arm-fail deck=%d id=%d reason=unregistered",
                    deck,
                    track_id,
                    lvl=logging.WARNING,
                    deck=deck,
                    data={"action": "arm-fail", "deck": deck, "id": track_id, "reason": "unregistered"},
                )
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
        mirror = 3 - deck

        bridge_log.perf(
            "scripted",
            "arm deck=%d id=%d elapsed=%s bpm=%.1f file=%s",
            deck, track_id, bf.elapsed(elapsed_ms), d.meta.bpm,
            bf.short(track.get("filepath", "")),
            deck=deck,
            data={
                "action": "arm",
                "deck": deck,
                "id": track_id,
                "elapsed_ms": elapsed_ms,
                "bpm": d.meta.bpm,
                "file": bf.short(track.get("filepath", "")),
            },
        )

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
        elapsed_ms = snap.elapsed_ms if snap and not snap.is_stale() else arm.elapsed_ms
        bridge_log.perf(
            "scripted",
            "arm-phase2 deck=%d id=%d elapsed=%s",
            arm.deck, arm.track_id, bf.elapsed(elapsed_ms),
            deck=arm.deck,
            data={"action": "arm-phase2", "deck": arm.deck, "id": arm.track_id, "elapsed_ms": elapsed_ms},
        )
        arm_meta = arm.arm_meta
        # Use current active_deck, not the snapshot — deck may have switched in 100ms
        cur_active = self._os.active_deck
        # Send to all 4 SS deck slots: active + mirror bridge deck + VDJ layers 3/4.
        # Phase 0 clears all 4; if mirror is not reloaded here the push loop sends
        # elapsed to an empty SS deck, which confuses SS's scripted show engine.
        # Matches v1 behaviour: always load both bridge decks at arm time.
        self._sse.send_scripted_arm_phase1(arm.deck, arm_meta, cur_active, elapsed_ms=elapsed_ms)
        self._log_status()

    def _arm_unscripted(self, deck: int) -> None:
        """Clear scripted state. Lighting machine re-evaluates next tick."""
        d = self._deck[deck]
        log.info("[SM] clear-scripted  deck=%d", deck)
        d.scripted_id = 0
        d.meta.soundswitch_id = ""
        # RW-3 (A.4): scripted de-ownership of the HELD deck immediately disarms the pack
        # pause-hold. SCRIPTED_CLEAR is the only de-owner whose state a same-drain
        # re-resolve+re-arm can fully restore, so the 4-tuple play_identity cannot see the
        # transient; tear the latch down here. Gate on the hold-owning deck
        # (_pack_play_hold_key[0]) so a mirror-deck clear (operator loading the next track
        # on the idle deck during a brief pause) does NOT spuriously drop the active deck's
        # hold. Same _run thread as the driver (no lock); push-local only.
        if self._pack_play_hold_key is not None and self._pack_play_hold_key[0] == deck:
            self._pack_play_hold_key = None
            self._pack_play_hold_deadline = 0.0

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
            self._led_clear_dispatch_retries()
            self._clear_led_drop_lifecycle()
            if self._laser_director is not None:
                self._laser_director.reset_runtime_state(reason="scripted")
            self._reset_native_autoloop()
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
            if self._laser_director is not None:
                self._laser_director.reset_runtime_state(reason="idle")
            self._reset_native_autoloop()
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
            self._clear_idle_lighting_outputs()

    def _clear_idle_lighting_outputs(self) -> None:
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
            self._submit_pack_zero_frame(rt)
            raise
        if rt is not None and rt.active:
            self._drive_pack_output()

    def _submit_pack_zero_frame(self, rt: PackRuntime | None = None) -> None:
        rt = self._pack_runtime if rt is None else rt
        if rt is not None and rt.active and rt.backend is not None:
            try:
                rt.backend.submit_frame(_PACK_ZERO_FRAME)
            except Exception:
                pass

    def _update_laser_color_from_led(
        self,
        *,
        white_moment: bool,
        drop_phase: str | None,
        post_drop_progress: float | None,
    ) -> None:
        led_engine = self._led_color_engine
        laser_engine = self._laser_color_engine
        if led_engine is None or laser_engine is None:
            return
        try:
            state = led_engine.color_state()
            laser_engine.update(
                state,
                white_moment=white_moment,
                drop_phase=drop_phase,
                post_drop_progress=post_drop_progress,
            )
        except Exception:
            # Keep the previous held color if the LED color read fails.
            pass

    def _sync_laser_color_if_needed(self, sp_state: SmartPhrasingState) -> None:
        """Recompute the held laser snapshot when LED color_state moves.

        Fable's per-frame hold only helps once a snapshot exists; the snapshot
        was still computed solely on accepted automation look fires, so manual
        pads, v2 zone/manual dressing, and override-fades could leave lasers on
        a stale CH8 until the next section look.
        """
        laser_engine = self._laser_color_engine
        led_engine = self._led_color_engine
        if laser_engine is None or led_engine is None:
            return
        try:
            color_state = led_engine.color_state()
        except Exception:
            return
        rgb = color_state.get("rgb")
        # Quantize live_rgb to its laser color bucket (not raw RGB): the LEDs'
        # last-emitted color is last-writer-wins across roles and can differ every
        # 200 Hz tick, so a raw-RGB signature element would flap the sig every tick
        # and force a per-tick _target + color_state recompute (CPU-starvation
        # history). The laser only cares which of the 6 fixed buckets it lands in,
        # so the sig changes at cue cadence, not tick cadence.
        live = color_state.get("live_rgb")
        live_bucket = (
            _laser_nearest_fixed_color(tuple(int(v) for v in live))
            if isinstance(live, (list, tuple)) and len(live) == 3
            and all(isinstance(v, int) and not isinstance(v, bool) for v in live)
            else None
        )
        sig = (
            tuple(rgb) if isinstance(rgb, (list, tuple)) and len(rgb) == 3 else (),
            color_state.get("palette"),
            bool(color_state.get("white_sand_active")),
            bool(color_state.get("rainbow_active")),
            live_bucket,
        )
        if sig == self._laser_color_led_sig:
            return
        self._laser_color_led_sig = sig
        role = self._laser_color_last_led_role()
        post_drop = (
            self._laser_color_post_drop_progress(role, sp_state)
            if role is not None
            else None
        )
        self._update_laser_color_from_led(
            white_moment=self._laser_color_white_moment(),
            drop_phase=role,
            post_drop_progress=post_drop,
        )

    def _bootstrap_laser_color_if_needed(self) -> None:
        """Seed the held laser snapshot from current LED color when none exists yet.

        The per-frame hold forwards ``laser_engine.snapshot()`` onto every autoloop
        frame, but the snapshot is normally computed only when an LED look fires.
        v2 identity/manual color can be live before that first trigger, leaving CH8
        on baked pack color indefinitely.
        """
        laser_engine = self._laser_color_engine
        led_engine = self._led_color_engine
        if laser_engine is None or led_engine is None or laser_engine.snapshot() is not None:
            return
        active = self._os.active_deck
        if active not in (1, 2) or not self._deck[active].playing:
            return
        sp_state = self._last_sp_state
        role = self._laser_color_last_led_role()
        post_drop = (
            self._laser_color_post_drop_progress(role, sp_state)
            if role is not None and sp_state is not None
            else None
        )
        self._update_laser_color_from_led(
            white_moment=self._laser_color_white_moment(),
            drop_phase=role,
            post_drop_progress=post_drop,
        )

    def _laser_color_last_led_role(self) -> str | None:
        event = str(getattr(self, "_led_last_event", "") or "")
        if not event.startswith("automation:"):
            return None
        role = event.split(":", 2)[1]
        if role not in {"ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility"}:
            return None
        return role

    def _laser_color_white_moment(self) -> bool:
        white_moment_fn = getattr(self._led_scene_adapter, "last_white_moment", None)
        return bool(white_moment_fn()) if callable(white_moment_fn) else False

    def _laser_color_post_drop_progress(
        self,
        role: str | None,
        sp_state: SmartPhrasingState,
    ) -> float | None:
        if role != "post_drop" or sp_state.active_drop_beat is None:
            return None
        abs_beat = self._led_abs_beat(sp_state)
        if abs_beat is None:
            return None
        cycle = self._led_post_drop_cycle_beats()
        return max(0.0, min(1.0, (abs_beat - float(sp_state.active_drop_beat)) / cycle))

    def set_pack_runtime(self, runtime: PackRuntime) -> None:
        """Atomically publish a new pack runtime bundle (command thread → push loop).

        The runtime ref is published in one assignment, so the push loop never sees a
        mixed old/new runtime. All blocking work (load_pack, serial open/close,
        old-sender zero_and_stop) must already be done by the caller.

        RW-4: a swapped-in bundle always carries a FRESH player (boots with no
        static layers) and a fresh input group (boots with no held layers), so the
        push loop's last-pushed layer tracker is reset here. Otherwise a layer tuple
        carried from the old player could equal the new snapshot's tuple and skip
        set_static_layers on the fresh player. A single reference assignment is
        atomic under the GIL; the push loop at worst reads it one tick stale and
        re-syncs. The degradation latch is deliberately NOT reset (it must survive
        a swap; see H10).
        """
        self._pack_runtime = runtime or DISABLED_PACK_RUNTIME
        self._pack_last_static_layers = ()
        self._pack_frame_count = 0
        self._pack_logged_error = False
        self._pack_input_health_logged_error = False
        self._reset_native_autoloop()
        self._publish_pack_status(
            runtime=self._pack_runtime,
            scripted_active=False,
            input_degraded=False,
            static_held=False,
            blackout=False,
            autoloop_phase_blocked=False,
            software_zero_frame=True,
        )

    def get_pack_runtime(self) -> PackRuntime:
        """Current pack runtime bundle (for the command-thread controller's snapshot)."""
        return self._pack_runtime

    def get_pack_status(self) -> dict[str, Any]:
        """Sanitized pack status for the runtime status surface (no paths/ports/etc.)."""
        status = dict(self._pack_status_snapshot)
        truth_sink = getattr(self._pack_runtime, "truth_sink", None)
        if truth_sink is not None:
            try:
                status["truth_check"] = truth_sink.status()
            except Exception:
                status["truth_check"] = {
                    "enabled": True,
                    "reason": "status_error",
                    "sidecar_error": "status_error",
                }
        return status

    def _enqueue_pack_truth_frame(
        self,
        *,
        runtime: PackRuntime,
        frame: tuple[int, ...],
        intent: dict[str, Any],
    ) -> None:
        truth_sink = getattr(runtime, "truth_sink", None)
        if truth_sink is None:
            return
        try:
            truth_sink.submit_frame(frame, intent)
        except Exception:
            log.error("[SM] artnet truth-check enqueue failed", exc_info=False)

    def _pack_truth_intent(
        self,
        *,
        active_deck: int,
        lighting_mode: str,
        scripted_active: bool,
        scripted_id: int = 0,
        soundswitch_id: str = "",
        input_degraded: bool = False,
        static_layers: tuple[Any, ...] = (),
        blackout: bool = False,
        blackout_bindings: tuple[str, ...] = (),
        elapsed_ms: int = 0,
        transport: str = "",
        native_autoloop: NativeAutoloopDecision | None = None,
    ) -> dict[str, Any]:
        native_status = native_autoloop.status if native_autoloop is not None else ""
        mode = "idle"
        if blackout:
            mode = "blackout"
        elif static_layers:
            mode = "static"
        elif scripted_active:
            mode = "scripted"
        elif native_status in ("rendering_active", "empty_dark_look", "base_suppressed"):
            mode = "autoloop"
        return {
            "mode": mode,
            "active_deck": int(active_deck),
            "lighting_mode": str(lighting_mode or ""),
            "scripted_active": bool(scripted_active),
            "scripted_id": int(scripted_id or 0),
            "soundswitch_id": soundswitch_id or "",
            "input_degraded": bool(input_degraded),
            "static_held": bool(static_layers),
            "static_slots": [
                int(slot)
                for slot in (getattr(layer, "slot", None) for layer in static_layers)
                if type(slot) is int
            ],
            "blackout": bool(blackout),
            "blackout_bindings": [str(key) for key in blackout_bindings],
            "elapsed_ms": int(elapsed_ms or 0),
            "transport": str(transport or ""),
            "native_autoloop": (
                native_autoloop.to_status_dict()
                if native_autoloop is not None
                else NativeAutoloopDecision("software_zero_frame").to_status_dict()
            ),
        }

    def _publish_pack_status(
        self,
        *,
        runtime: PackRuntime,
        scripted_active: bool,
        input_degraded: bool,
        static_held: bool,
        blackout: bool,
        autoloop_phase_blocked: bool,
        software_zero_frame: bool,
        parity_live_blocked: bool = False,
        native_autoloop: NativeAutoloopDecision | dict[str, Any] | None = None,
        overlay_suppressed_static_held: bool = False,
        overlay_suppressed_blackout: bool = False,
        overlay_suppressed_input_degraded: bool = False,
    ) -> None:
        """Publish one fresh software-intent snapshot with one atomic assignment."""
        rt = runtime or DISABLED_PACK_RUNTIME
        try:
            has_active_identity = bool(getattr(rt.backend, "last_accepted_identity", None))
        except Exception:
            has_active_identity = False
        active = bool(rt.active)
        if isinstance(native_autoloop, NativeAutoloopDecision):
            native_block = native_autoloop.to_status_dict()
        elif isinstance(native_autoloop, dict):
            native_block = dict(native_autoloop)
        else:
            native_block = NativeAutoloopDecision("software_zero_frame").to_status_dict()
        native_status = str(native_block.get("status", ""))
        status = rt.sanitized_status()
        status.update({
            "operational_state": _pack_operational_state(
                enabled=active,
                blackout=bool(blackout),
                input_degraded=bool(input_degraded),
                static_held=bool(static_held),
                parity_live_blocked=bool(parity_live_blocked),
                scripted_active=bool(scripted_active),
                autoloop_phase_blocked=bool(autoloop_phase_blocked),
                software_zero_frame=bool(software_zero_frame),
                native_autoloop_status=native_status if active else "",
            ),
            "scripted_active": bool(scripted_active),
            "input_degraded": bool(input_degraded),
            "static_held": bool(static_held),
            "blackout": bool(blackout),
            "parity_live_blocked": bool(parity_live_blocked),
            "overlay_suppressed": {
                "static_held": bool(overlay_suppressed_static_held),
                "blackout": bool(overlay_suppressed_blackout),
                "input_degraded": bool(overlay_suppressed_input_degraded),
            },
            "autoloop_phase_blocked": bool(autoloop_phase_blocked),
            "software_zero_frame": bool(software_zero_frame),
            "native_autoloop": native_block,
            "frame_count": max(0, int(self._pack_frame_count)),
            "has_active_identity": has_active_identity,
        })
        self._pack_status_snapshot = status

    def _reset_native_autoloop(self) -> None:
        self._native_autoloop.reset()
        self._native_captured_scene = None
        self._native_abs_beat_pos = None
        self._native_log_key = ()

    def _update_pack_input_health(
        self,
        midi_input: Any,
    ) -> tuple[bool, bool, tuple[Any, ...], bool, tuple[Any, ...]]:
        try:
            s = midi_input.snapshot()
            worker_alive = bool(s.worker_alive)
            err = s.error
            drops = int(s.mail_drop_count)
            held_layers = s.held_layers
            if type(held_layers) is not tuple:
                raise TypeError("held_layers must be an immutable tuple")
            blackout_held = bool(s.blackout_held)
            blackout_bindings = tuple(getattr(s, "blackout_bindings", ()))
        except Exception:
            self._pack_input_degraded_latched = True
            raise
        self._pack_last_mail_drop_count = drops
        if not worker_alive:
            self._pack_input_degraded_latched = True
        if (
            self._pack_input_degraded_latched
            and worker_alive and err is None
            and not held_layers and not blackout_held
        ):
            self._pack_input_degraded_latched = False
        input_healthy = not self._pack_input_degraded_latched
        input_degraded = not input_healthy
        if self._led_palette_control is not None:
            self._led_palette_control.on_input_health(input_healthy)
            self._led_palette_control.maybe_publish()
        return input_healthy, input_degraded, held_layers, blackout_held, blackout_bindings

    def _drive_pack_input_health_inactive(self, rt: PackRuntime) -> None:
        input_degraded = True
        try:
            _, input_degraded, _, _, _ = self._update_pack_input_health(rt.midi_input)
            self._pack_input_health_logged_error = False
        except Exception as exc:
            self._pack_input_degraded_latched = True
            if self._led_palette_control is not None:
                try:
                    self._led_palette_control.on_input_health(False)
                    self._led_palette_control.maybe_publish()
                except Exception:
                    pass
            if not self._pack_input_health_logged_error:
                log.error(
                    "[SM] pack input health error; marking degraded  error=%s",
                    type(exc).__name__,
                )
                self._pack_input_health_logged_error = True
        if bool(self._pack_status_snapshot.get("input_degraded", False)) == input_degraded:
            return
        self._publish_pack_status(
            runtime=rt,
            scripted_active=False,
            static_held=False,
            blackout=False,
            autoloop_phase_blocked=False,
            software_zero_frame=True,
            input_degraded=input_degraded,
        )

    def _drive_pack_output(self, now: float | None = None) -> None:
        """T7c/T7e: drive the pack player from authoritative deck state; submit one
        CH1-CH19 frame. READ-ONLY w.r.t. DeckState; fail-safe to ZERO; never raises
        into the tick. Automatic base ZEROs on any non-happy-path (stop/stale/error/
        track-change/discontinuity) via clear_selection() so a held manual Static
        Override stands alone while idle. See
        docs/plans/active/soundswitch_t7c_pack_driver_spec.md."""
        rt = self._pack_runtime
        if rt is None or not rt.active:
            self._drop_presentation_base_live = False
            if rt is not None and rt.midi_input is not None:
                self._drive_pack_input_health_inactive(rt)
            return
        now = time.monotonic() if now is None else now
        # Drop presentation darkness-guard input (Task 4 items 3-4): defaults
        # False every pass; only the exact autoloop-base-rendered-clean branch
        # below sets it True. Any other path (scripted, idle, error, missing
        # selection, unsupported layout) leaves lasers "not visible".
        self._drop_presentation_base_live = False
        player, backend, midi_input = rt.player, rt.backend, rt.midi_input
        self._bootstrap_laser_color_if_needed()
        laser_color_engine = self._laser_color_engine
        player.set_color_snapshot(
            laser_color_engine.snapshot() if laser_color_engine is not None else None
        )
        truth_sink = getattr(rt, "truth_sink", None)
        input_healthy = True
        input_degraded = False
        layers: tuple[Any, ...] = ()
        blackout = False
        blackout_bindings: tuple[str, ...] = ()
        transport = None
        parity_live_blocked = False
        try:
            smart_dark = False
            if self._laser_executor is not None:
                smart_dark = bool(self._laser_executor.mask_owners_active())
            soundswitch_connected = bool(
                self._os2l_connected_provider is not None
                and self._os2l_connected_provider()
            )
            # 1. Controller masks + static overrides (in-memory snapshot; no I/O).
            #    RW-4: an UNHEALTHY controller drops its MANUAL OVERLAY ONLY (held
            #    Static Look + blackout forced released); the automatic scripted base
            #    (RW-3 gate below) is deliberately left running, so a DDJ-800 dropout
            #    keeps the scripted show on (operator policy 2026-06-24). Held input is
            #    honored only from a FRESH HEALTHY snapshot.
            #
            #    FAIL-CLOSED: health fields are read DIRECTLY off the snapshot. A
            #    malformed double missing them raises and the outer except below submits
            #    ZERO — missing health never reads as healthy. An
            #    empty-alias group is healthy by REAL construction (worker_alive=True,
            #    error=None; soundswitch_midi_input.py:455), not by a default.
            #
            #    UNIFIED degradation latch: worker death / input-port-gone latches
            #    overlay distrust. Transient error strings and mailbox-drop counters do
            #    not clear a still-live layer stack. The latch clears ONLY on a clean,
            #    quiet, healthy snapshot (worker alive, no error, no held layers, no
            #    blackout), so a stale layer cannot resurface on mere worker recovery.
            if midi_input is not None:
                (
                    input_healthy,
                    input_degraded,
                    held_layers,
                    blackout_held,
                    snapshot_blackout_bindings,
                ) = self._update_pack_input_health(midi_input)
                blackout = (blackout_held if input_healthy else False) or smart_dark
                blackout_bindings = snapshot_blackout_bindings if input_healthy else ()
                layers = held_layers if input_healthy else ()
                player.set_masks(blackout=blackout, emergency=False)
                if layers != self._pack_last_static_layers:
                    player.set_static_layers(layers)
                    self._pack_last_static_layers = layers
            else:
                blackout = smart_dark
                player.set_masks(blackout=blackout, emergency=False)
                if self._led_palette_control is not None:
                    self._led_palette_control.on_input_health(False)
                    self._led_palette_control.maybe_publish()

            if soundswitch_connected and truth_sink is None:
                native_decision = self._native_autoloop.resolve(
                    pack_sha12=rt.pack_sha12,
                    bindings={},
                    scene=None,
                    lighting_mode=self._os.lighting_mode,
                    scripted_active=False,
                    playing=False,
                    fresh=False,
                    track_changed=False,
                    discontinuity=False,
                    soundswitch_present=True,
                    abs_beat_pos=0.0,
                    phase_offset_beats=rt.phase_offset_beats,
                )
                player.clear_selection()
                player.set_static_layers(())
                # This clears derived bridge output only; held intent is recomputed next pass.
                player.set_masks(blackout=False, emergency=False)
                self._pack_last_static_layers = ()
                self._pack_play_hold_key = None
                self._pack_play_hold_deadline = 0.0
                self._pack_frame_count += 1
                self._publish_pack_status(
                    runtime=rt,
                    scripted_active=False,
                    input_degraded=False,
                    static_held=False,
                    blackout=False,
                    autoloop_phase_blocked=True,
                    software_zero_frame=True,
                    native_autoloop=native_decision,
                    overlay_suppressed_static_held=bool(layers),
                    overlay_suppressed_blackout=bool(blackout),
                    overlay_suppressed_input_degraded=bool(input_degraded),
                )
                backend.submit_frame(_PACK_ZERO_FRAME)
                return

            # 1b. No active deck (idle between tracks): the manual overlay above stays
            #     operator-controlled — presses/releases/toggles/blackout keep applying
            #     while the automatic base is cleared. Held static stands alone during
            #     idle and still loses to blackout (manual-static policy).
            active = self._os.active_deck
            if active not in (1, 2):
                player.clear_selection()
                frame = player.render().frame
                self._pack_frame_count += 1
                self._enqueue_pack_truth_frame(
                    runtime=rt,
                    frame=frame,
                    intent=self._pack_truth_intent(
                        active_deck=active,
                        lighting_mode=self._os.lighting_mode,
                        scripted_active=False,
                        input_degraded=input_degraded,
                        static_layers=layers,
                        blackout=blackout,
                        blackout_bindings=blackout_bindings,
                    ),
                )
                if soundswitch_connected:
                    self._publish_pack_status(
                        runtime=rt,
                        scripted_active=False,
                        input_degraded=False,
                        static_held=False,
                        blackout=False,
                        autoloop_phase_blocked=True,
                        software_zero_frame=True,
                        native_autoloop=NativeAutoloopDecision(
                            "soundswitch_present_native_suppressed",
                            reason="soundswitch_present",
                        ),
                        overlay_suppressed_static_held=bool(layers),
                        overlay_suppressed_blackout=bool(blackout),
                        overlay_suppressed_input_degraded=bool(input_degraded),
                    )
                    backend.submit_frame(_PACK_ZERO_FRAME)
                    return
                self._publish_pack_status(
                    runtime=rt,
                    scripted_active=False,
                    input_degraded=input_degraded,
                    static_held=bool(layers),
                    blackout=bool(blackout),
                    autoloop_phase_blocked=False,
                    software_zero_frame=frame == _PACK_ZERO_FRAME,
                )
                backend.submit_frame(frame)
                return
            d = self._deck[active]
            snap = self._cache.get(active)

            # 2. Derive the happy-path gate (fail-conservative; uncertain ⇒ ZERO base).
            load_key = (active, int(getattr(d, "load_gen", 0)))
            track_changed = (
                self._pack_last_load_gen is not None and load_key != self._pack_last_load_gen
            )
            self._pack_last_load_gen = load_key
            elapsed_ms = max(0, int(getattr(d, "elapsed_ms", 0) or 0))
            playing = bool(getattr(d, "playing", False))
            delta_ms = (
                abs(elapsed_ms - self._pack_last_elapsed_ms)
                if not track_changed and self._pack_last_elapsed_ms is not None
                else 0
            )
            if delta_ms >= _PACK_SCRUB_JUMP_MS and playing:
                # Scrub/seek latch (playing only): each impossible-for-playback
                # jump re-arms a short dark hold, so a sustained waveform drag
                # stays dark (like SoundSwitch) instead of strobing through every
                # scrubbed cue; rendering resumes _PACK_SCRUB_HOLD_S after the
                # last jump. Paused seeks keep RW-2 semantics (one-tick zero on a
                # >=_PACK_SEEK_JUMP_MS jump, then the pause-hold re-render).
                self._pack_scrub_hold_until = now + _PACK_SCRUB_HOLD_S
            discont = (
                delta_ms >= _PACK_SEEK_JUMP_MS
                or (not track_changed and playing and now < self._pack_scrub_hold_until)
            )
            self._pack_last_elapsed_ms = elapsed_ms
            fresh = not (snap is None or snap.is_stale(MEM_STALE_S))
            ssid = getattr(getattr(d, "meta", None), "soundswitch_id", "") or ""
            norm_ssid = _pack_normalize_id(ssid)              # RW-3: capture once
            metadata_ready = norm_ssid is not None
            # RW-3 mode authority: the bridge's scripted classification is
            # DeckState.scripted_id (the flag _update_lighting keys on, :3117), NOT a
            # syntactically valid UUID. Mode-only: do not consult the scripted registry
            # for identity (it false-zeros filepath-matched shows; see spec A.3).
            scripted_id = int(getattr(d, "scripted_id", 0) or 0)
            scripted_owned = scripted_id != 0
            # RW-3 temporal hold identity (A.4): bind the pause-hold to the full played
            # identity so a bare re-arm / re-resolve to a different scripted_id or ssid
            # cannot resurrect a stale paused frame. Same-identity clear->re-resolve->arm
            # is closed by the _arm_unscripted teardown (Task 2). Reuse load_key above.
            play_identity = (*load_key, scripted_id, norm_ssid)

            # 3. Automatic base transport derivation (RW-2). The pure player
            #    re-renders from immutable events at elapsed_ms each tick, so paused
            #    holds the current authoritative frame, never a cached one (A.5).
            #    Hold is bound to the PLAYED (deck, load_gen) identity and a
            #    STOP_DEBOUNCE_S deadline so (i) a never-played freshly-loaded track
            #    is never held, and (ii) the hold matches the OS2L idle debounce.
            #    os.was_playing is the obsolete-frame guard (A.5). The ZERO path
            #    stays clear_selection() so a held Static Override stands alone; we
            #    never emit transport="stopped"/"ended"/"unloaded".
            # Reuse the EXISTING bindings computed above: `playing`,
            # `fresh`, `metadata_ready`, `track_changed`, `discont`, `load_key`.
            # Do not re-declare them; scripted and native share the same gates.
            scripted_happy = (
                fresh and metadata_ready and scripted_owned
                and not track_changed and not discont
            )
            was_playing = bool(getattr(self._os, "was_playing", False))
            if scripted_happy and playing:
                transport = "playing"
                self._pack_play_hold_key = play_identity
                self._pack_play_hold_deadline = now + STOP_DEBOUNCE_S
            elif (
                scripted_happy and was_playing
                and play_identity == self._pack_play_hold_key
                and now < self._pack_play_hold_deadline
            ):
                transport = "paused"
            else:
                transport = None  # stopped/hold-expired/unloaded/stale/changed/discont/unowned
                if play_identity != self._pack_play_hold_key:
                    self._pack_play_hold_key = None
                    self._pack_play_hold_deadline = 0.0
            if transport is not None:
                scripted_result = player.select_scripted(
                    soundswitch_id=ssid, elapsed_ms=elapsed_ms, transport=transport,
                    metadata_ready=True, authority="fresh", source_errored=False,
                    elapsed_discontinuous=False, track_changed=False,
                )
                # If the scripted base cannot render (e.g. soundswitch_id absent from the
                # pack), clear it so a held manual Static Look stands alone instead of going
                # dark. clear_selection() leaves held static + masks intact; static still
                # loses to blackout/emergency (checked first in player.render()).
                if scripted_result.diagnostic is not None:
                    parity_live_blocked = scripted_result.diagnostic.code == "unverified_parity"
                    if not parity_live_blocked:
                        player.clear_selection()
                native_decision = self._native_autoloop.resolve(
                    pack_sha12=rt.pack_sha12,
                    bindings={},
                    scene=None,
                    lighting_mode=self._os.lighting_mode,
                    scripted_active=True,
                    playing=playing,
                    fresh=fresh,
                    track_changed=track_changed,
                    discontinuity=discont,
                    soundswitch_present=False,
                    abs_beat_pos=self._native_abs_beat_pos or 0.0,
                    phase_offset_beats=rt.phase_offset_beats,
                )
            else:
                pack = player.pack
                native_scene = self._native_captured_scene
                # Only bootstrap from the laser executor's HELD scene when the
                # resolver has not yet latched. current_autoloop_scene() returns
                # the active scene every tick; feeding it on hold ticks (after a
                # latch) re-anchors anchor_beat=abs_beat_pos every tick and pins
                # phase_tick at 0. Once latched, hold ticks must pass scene=None so
                # the anchor holds and phase advances; genuine refires still arrive
                # via _native_captured_scene (the real edge). See 2026-07-01
                # all_surface capture (every Autoloop row phase_tick=0).
                if (
                    native_scene is None
                    and self._native_autoloop.state is None
                    and self._laser_executor is not None
                ):
                    current_autoloop_scene = getattr(
                        self._laser_executor, "current_autoloop_scene", None)
                    if callable(current_autoloop_scene):
                        native_scene = current_autoloop_scene()
                native_decision = self._native_autoloop.resolve(
                    pack_sha12=rt.pack_sha12,
                    bindings=getattr(pack, "autoloop_bindings", {}),
                    scene=native_scene,
                    lighting_mode=self._os.lighting_mode,
                    scripted_active=scripted_owned,
                    playing=playing,
                    fresh=fresh,
                    track_changed=track_changed,
                    discontinuity=discont,
                    soundswitch_present=False,
                    abs_beat_pos=self._native_abs_beat_pos or 0.0,
                    phase_offset_beats=rt.phase_offset_beats,
                )
                if native_decision.target_identity and native_decision.phase_tick is not None:
                    result = player.select_autoloop(
                        native_decision.target_identity,
                        native_decision.phase_tick,
                        authority="fresh",
                    )
                    self._drop_presentation_base_live = result.diagnostic is None
                    native_decision = finalize_native_autoloop_render(native_decision, result)
                    parity_live_blocked = native_decision.status == "unverified_parity"
                    if native_decision.status in ("missing_autoloop_file", "unsupported_layout"):
                        self._native_autoloop.reset()
                        player.clear_selection()
                        self._drop_presentation_base_live = False
                else:
                    player.clear_selection()

            native_log_key = (
                native_decision.status,
                native_decision.role,
                native_decision.scene,
                native_decision.note,
                native_decision.target_identity,
                native_decision.diagnostic,
            )
            if native_log_key != self._native_log_key:
                self._native_log_key = native_log_key
                log.info(
                    "[SM] native-autoloop  status=%s  diag=%s  role=%s  scene=%s  note=%s  target=%s  name=%s  reason=%s",
                    native_decision.status,
                    native_decision.diagnostic or "-",  # DIAG: the real reason the 'unsupported_layout' catch-all hides
                    native_decision.role or "-",
                    native_decision.scene or "-",
                    native_decision.note if native_decision.note is not None else "-",
                    native_decision.target_identity or "-",
                    native_decision.soundswitch_name or "-",
                    native_decision.reason or "-",
                )

            # 4. Publish software intent, then submit that same frame exactly once.
            frame = player.render().frame
            native_status = native_decision.status
            self._pack_frame_count += 1
            self._enqueue_pack_truth_frame(
                runtime=rt,
                frame=frame,
                intent=self._pack_truth_intent(
                    active_deck=active,
                    lighting_mode=self._os.lighting_mode,
                    scripted_active=transport is not None,
                    scripted_id=scripted_id,
                    soundswitch_id=ssid,
                    input_degraded=input_degraded,
                    static_layers=layers,
                    blackout=blackout,
                    blackout_bindings=blackout_bindings,
                    elapsed_ms=elapsed_ms,
                    transport=transport or "",
                    native_autoloop=native_decision,
                ),
            )
            if soundswitch_connected:
                self._drop_presentation_base_live = False  # bridge render is discarded for ZERO
                self._publish_pack_status(
                    runtime=rt,
                    scripted_active=False,
                    input_degraded=False,
                    static_held=False,
                    blackout=False,
                    autoloop_phase_blocked=True,
                    software_zero_frame=True,
                    native_autoloop=NativeAutoloopDecision(
                        "soundswitch_present_native_suppressed",
                        reason="soundswitch_present",
                    ),
                    overlay_suppressed_static_held=bool(layers),
                    overlay_suppressed_blackout=bool(blackout),
                    overlay_suppressed_input_degraded=bool(input_degraded),
                )
                backend.submit_frame(_PACK_ZERO_FRAME)
                return
            self._publish_pack_status(
                runtime=rt,
                scripted_active=transport is not None,
                input_degraded=input_degraded,
                static_held=bool(layers),
                blackout=bool(blackout),
                parity_live_blocked=parity_live_blocked,
                autoloop_phase_blocked=(
                    rt.active
                    and self._os.lighting_mode == "autoloop"
                    and transport is None
                    and native_status not in ("rendering_active", "empty_dark_look", "base_suppressed")
                ),
                software_zero_frame=frame == _PACK_ZERO_FRAME,
                native_autoloop=native_decision,
            )
            backend.submit_frame(frame)
        except Exception as exc:
            # Fail-closed for the darkness guard: any error this pass means
            # "lasers are not verifiably visible", never a stale True.
            self._drop_presentation_base_live = False
            if not self._pack_logged_error:
                log.error(
                    "[SM] pack driver error; resolving ZERO  error=%s",
                    type(exc).__name__,
                )
                self._pack_logged_error = True
            input_degraded = bool(
                getattr(rt, "midi_input", None) is not None
                and self._pack_input_degraded_latched
            )
            self._publish_pack_status(
                runtime=rt,
                scripted_active=False,
                input_degraded=input_degraded,
                static_held=False,
                blackout=False,
                autoloop_phase_blocked=False,
                software_zero_frame=True,
            )
            try:
                backend.submit_frame(_PACK_ZERO_FRAME)
            except Exception:
                pass

    def _push_tick_inner(self) -> None:
        self._native_captured_scene = None
        self._native_abs_beat_pos = None
        self._rerun_active_deck_resolver("push_tick")
        if self._os.active_deck not in (1, 2):
            if self._os.was_playing or self._os.lighting_mode != "idle" or self._pending_arm is not None:
                self._enter_idle_no_audible(reason="idle_no_audible")
            return

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
                bridge_log.health("reader", "stop-stale deck=%d", active, deck=active)
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
                        self._native_captured_scene = self._laser_executor.on_decision(
                            decision, _lctx)
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
            if not self._mixer_authority_enabled and not d.playing and not arm_guard:
                if self._deck[mirror].playing:
                    bridge_log.perf(
                        "deck",
                        "switch %d->%d (%s)",
                        active,
                        mirror,
                        "idle+mirror-playing",
                        deck=mirror,
                        data={
                            "old": active,
                            "new": mirror,
                            "src": "auto",
                            "reason": "idle+mirror-playing",
                        },
                    )
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
                    self._native_captured_scene = self._laser_executor.on_decision(
                        decision, _lctx)
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

        elapsed_ms = int(raw_elapsed_ms)
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
        self._native_abs_beat_pos = float(abs_beat_pos)

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
            if other_playing and not arm_guard and not self._mixer_authority_enabled:
                bridge_log.perf(
                    "deck",
                    "switch %d->%d (%s)",
                    active,
                    mirror,
                    "stopped+mirror-playing",
                    deck=mirror,
                    data={
                        "old": active,
                        "new": mirror,
                        "src": "auto",
                        "reason": "stopped+mirror-playing",
                    },
                )
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
        if (
            not self._mixer_authority_enabled
            and not os.was_playing and not d.playing and not arm_guard
        ):
            if self._deck[mirror].playing:
                bridge_log.perf(
                    "deck",
                    "switch %d->%d (%s)",
                    active,
                    mirror,
                    "idle+mirror-playing",
                    deck=mirror,
                    data={
                        "old": active,
                        "new": mirror,
                        "src": "auto",
                        "reason": "idle+mirror-playing",
                    },
                )
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
                    self._native_captured_scene = self._laser_executor.on_decision(
                        decision, _lctx)
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
            led_trigger_count = self._led_automation_trigger_count
            # Advance any override-fade and mirror engine-driven palette changes
            # to the deck BEFORE the gated automation dispatch, so a stable
            # role-key / hold / pre-drop blackout can't freeze the fade or the
            # pad (2026-07-05).
            self._advance_palette_fade_and_publish(led_sp_state)
            self._dispatch_led_automation(
                active=active,
                d=d,
                sp_state=led_sp_state,
                position_stale=(snap is None or snap.is_stale(MEM_STALE_S)),
            )
            if self._led_automation_trigger_count != led_trigger_count:
                led_role = self._laser_color_last_led_role()
                if led_role is not None:
                    self._update_laser_color_from_led(
                        white_moment=self._laser_color_white_moment(),
                        drop_phase=led_role,
                        post_drop_progress=self._laser_color_post_drop_progress(led_role, led_sp_state),
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
                        bridge_log.perf(
                            "drop",
                            "crossing deck=%d beat=%d blackout=%s",
                            active,
                            this_beat,
                            smart_drop_blackout_mode,
                            deck=active,
                            beat=float(this_beat),
                            data={
                                "deck": active,
                                "beat": this_beat,
                                "blackout_mode": smart_drop_blackout_mode,
                                "blackout_armed": smart_drop_result.blackout_armed,
                            },
                        )
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
                        bridge_log.perf(
                            "ss",
                            "midi-refire deck=%d beat=%d source=%s",
                            active,
                            this_beat,
                            refire_source,
                            deck=active,
                            beat=this_beat,
                            data={
                                "action": "midi-refire",
                                "deck": active,
                                "beat": this_beat,
                                "source": refire_source,
                                "origin_before": origin,
                                "origin_after": os.midi_refire_origin_beat,
                                "previous": previous_refire_beat,
                                "interval": AUTOLOOP_ARM_PHRASE_BEATS,
                                "marker_latched": marker_crossed,
                                "grid": grid_status,
                            },
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
                self._native_captured_scene = self._laser_executor.on_decision(decision, ctx)
        # Drop presentation policy (Package 3): reuses the Laser Director's own
        # drop_crossing decision as "a true drop is impacting THIS tick" per
        # the authority doc's "no new drop detection" rule -- assumed known
        # limitation: if the Laser Director is never configured at all
        # (self._laser_director is None), drop_presentation never sees an
        # impact either. Matches the operator's actual setup (Laser Director
        # configured and live); see the handoff report for the alternative
        # considered (a second, parallel DropLifecycle instance) and why it
        # was not built.
        self._drop_presentation_tick(
            active=active, d=d, sp_state=sp_state, impact_now=drop_crossing_decision_emitted,
        )
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

        # ── B1 evidence-only autoloop phase trace (schema-2) ──────────────────
        # Active ONLY while a session recording is running. Hot-path cost when
        # inactive: one attribute load + truth test. When active: two non-blocking
        # clock reads + a primitive dict build + one bounded put_nowait. NO file/
        # socket/MIDI/serial/subprocess/sleep/contended-lock I/O on the tick (the
        # tracer's daemon writer thread owns all I/O). Read-only w.r.t. DeckState/
        # OutputState. emit() never blocks or raises. Reached only on the full
        # playing path (every non-playing/stale/stop branch returned earlier), so
        # rows are dense across the captured window and absent when not playing.
        tracer = self._phase_tracer
        if tracer is not None and d.playing:
            tracer.emit(build_autoloop_phase_row(
                mono_ns=time.monotonic_ns(),
                epoch_ns=time.time_ns(),
                active_deck=active,
                load_gen=int(d.load_gen),
                playing=bool(d.playing),
                position_stale=bool(snap is None or snap.is_stale(MEM_STALE_S)),
                elapsed_ms=int(elapsed_ms),
                bpm=float(bpm),
                abs_beat_pos=float(abs_beat_pos),
                beatgrid_source=d.meta.beatgrid_source,
                lighting_mode=os.lighting_mode,
                autoloop_arm_pending=bool(os.autoloop_arm_pending),
                autoloop_arm_sync_beat=int(os.autoloop_arm_sync_beat),
                autoloop_arm_target_elapsed_ms=int(os.autoloop_arm_target_elapsed_ms),
                pending_autoloop_arm_reason=os.pending_autoloop_arm_reason,
                midi_refire_origin_beat=int(os.midi_refire_origin_beat),
                last_autoloop_status_phrase_beat=int(os.last_autoloop_status_phrase_beat),
                phrase_anchor_last_beat=int(os.phrase_anchor_last_beat),
                drop_cut_armed=bool(os.drop_cut_armed),
                autoloop_tick_just_fired=bool(autoloop_tick_just_fired),
                # Reserved diagnostics: no cheap authoritative tick-local source
                # today, and the oracle does not consume them. Do NOT call
                # status()/executor/backend or heavy joins from the tick to fill
                # these — leave None (see spec §A / Part B absolute rules).
                role=None,
                reason=None,
                accepted_scene=None,
                accepted_note=None,
                accepted_trigger_gen=None,
            ))

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
        _sp_diag = _sp_result.diagnostics[0] if _sp_result.diagnostics else None
        _sp_reset_reason = _sp_diag.reason if _sp_diag is not None else ""
        if _sp_reset_reason != self._last_sp_reset_reason:
            _sp_deck = _sp_diag.deck_id if _sp_diag is not None else _sp_snapshot.deck_id
            _sp_track = _sp_diag.track_id if _sp_diag is not None else _sp_snapshot.track_id
            _sp_abs_beat = _sp_diag.abs_beat if _sp_diag is not None else _sp_snapshot.abs_beat
            log.info(
                "[SP] reset-reason-change reason=%s prev=%s deck=%s track=%s abs_beat=%s",
                _sp_reset_reason or "-",
                self._last_sp_reset_reason or "-",
                _sp_deck or "-",
                _sp_track or "-",
                _sp_abs_beat if _sp_abs_beat is not None else "-",
            )
            self._last_sp_reset_reason = _sp_reset_reason
        sp_state = _sp_result.state
        self._last_sp_state = sp_state
        self._last_sp_snapshot = _sp_snapshot
        return sp_state

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
        if deck not in (1, 2):
            return
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
        self._led_clear_dispatch_retries()
        self._led_hold_active = False
        self._led_hold_started_mono = 0.0
        self._led_hold_started_beat = None
        self._clear_led_drop_lifecycle()
        self._clear_smart_rearm_state()
        self._autoloop.clear_arm_phrase_lock()
        self._autoloop.clear_live_bpm_follow()
        self._autoloop.clear_tempo_relock()
        self._autoloop.clear_tempo_anchor()
        os.live_follow_generation += 1
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="stop")
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason="stop")
        self._reset_native_autoloop()
        # Fail-open any held drop-presentation LED dark hold: every stop routes
        # through here, so a reader-stale stop can't leave the room latched dark
        # (the stale branch returns before _drop_presentation_tick would).
        self._drop_presentation_release_on_stop()

    def _do_resume(self, deck: int, elapsed_ms: int, bpm: float) -> None:
        if deck not in (1, 2):
            return
        mirror = 3 - deck
        d = self._deck[deck]
        m = self._deck[mirror]
        log.info("[SM] resume  deck=%d  elapsed=%s  bpm=%.1f  file=%s",
                 deck, bf.elapsed(elapsed_ms), bpm, bf.short(d.meta.filepath))

        # Deck mismatch correction: if active deck is empty but other has track, swap
        if not self._mixer_authority_enabled and not d.meta.filepath and m.meta.filepath:
            bridge_log.perf(
                "deck",
                "switch %d->%d (%s)",
                deck,
                mirror,
                "empty-deck",
                deck=mirror,
                data={"old": deck, "new": mirror, "src": "auto", "reason": "empty-deck"},
            )
            self._os.active_deck = mirror
            self._last_audible_deck = mirror
            deck, mirror = mirror, deck
            d, m = m, d
        elif self._mixer_authority_enabled and not d.meta.filepath and m.meta.filepath:
            self._rerun_active_deck_resolver("resume_empty_deck")

        self._os.was_playing          = True
        self._os.last_sent_bpm        = 0.0
        self._os.last_beat_elapsed_ms = elapsed_ms
        self._os.last_autoloop_status_phrase_beat = 0
        self._led_last_auto_role_key = ""
        self._led_last_idle_role_key = ""
        self._led_smart_drop_blackout_key = ""
        self._led_clear_dispatch_retries()
        self._clear_led_drop_lifecycle()
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason="resume")
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="resume")
        self._reset_native_autoloop()
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
