"""
Shared data models for rb_ss_bridge_v2.

Update rules:
  DeckState  — written only by StateManager (event-loop thread).
  PositionSnapshot — written only by RBMemoryReader; read by push loop via PositionCache.
  BridgeEvent — immutable once created; only enqueued, never mutated.
  OutputState — written only by the push loop inside StateManager.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional


@dataclass
class SmartDropEnergyShadow:
    anlz_beat: int
    suggested_beat: int
    anlz_elapsed_ms: int
    suggested_elapsed_ms: int
    lift_at_anlz: float
    lift_at_suggested: float
    confidence: float
    score_at_anlz: float = 0.0
    score_at_suggested: float = 0.0
    feature_breakdown: Optional[dict[str, float]] = None
    source: str = "v1"


@dataclass
class TrackMetadata:
    filepath: str = ""
    soundswitch_id: str = ""
    bpm: float = 0.0
    content_id: str = ""
    first_beat_ms: float = 0.0
    beatgrid_times_ms: list[float] = field(default_factory=list)
    beatgrid_bpms: list[float] = field(default_factory=list)
    beatgrid_source: str = ""
    total_ms: float = 0.0
    cue_positions: list[int] = field(default_factory=list)
    anlz_drops: list[int] = field(default_factory=list)
    smart_drops: list[int] = field(default_factory=list)
    anlz_breakdowns: list[int] = field(default_factory=list)
    smart_breakdowns: list[int] = field(default_factory=list)
    anlz_buildups: list[int] = field(default_factory=list)
    anlz_mood: int = 0
    smart_drop_energy_shadow: list[SmartDropEnergyShadow] = field(default_factory=list)
    # F2 per-track plan (lighting_moments_v2.F2TrackPlan); None when F2 off or no
    # v4 cache. Typed Any to keep models.py free of a lighting-engine import.
    f2_plan: Optional[Any] = None

    def clear(self) -> None:
        self.filepath = ""
        self.soundswitch_id = ""
        self.bpm = 0.0
        self.content_id = ""
        self.first_beat_ms = 0.0
        self.beatgrid_times_ms = []
        self.beatgrid_bpms = []
        self.beatgrid_source = ""
        self.total_ms = 0.0
        self.cue_positions = []
        self.anlz_drops = []
        self.smart_drops = []
        self.anlz_breakdowns = []
        self.smart_breakdowns = []
        self.anlz_buildups = []
        self.anlz_mood = 0
        self.smart_drop_energy_shadow = []
        self.f2_plan = None

    def is_empty(self) -> bool:
        return not self.filepath


@dataclass
class DeckState:
    """Authoritative per-deck state. Written only by StateManager."""
    number: int
    meta: TrackMetadata = field(default_factory=TrackMetadata)
    playing: bool = False
    elapsed_ms: int = 0
    # Scripted show ID (0 = unscripted / none)
    scripted_id: int = 0
    # generation counter: incremented on every track_loaded event so
    # in-flight lsof threads can detect staleness
    load_gen: int = 0
    # Track title hint from the load event; used as DB lookup fallback when
    # ANLZ fails and lsof can't disambiguate by track length.
    track_title_hint: str = ""


@dataclass
class PositionSnapshot:
    """Latest position / play state read from RB memory for one bridge deck.

    Updated at ~60 Hz by RBMemoryReader; read by push loop via PositionCache.
    A snapshot with updated_at == 0 means "never received".
    """
    deck: int
    elapsed_ms: int = 0
    playing: bool = False
    track_length_ms: int = 0
    ddj_mode: bool = False
    updated_at: float = 0.0  # time.monotonic() of last successful read

    def age_s(self) -> float:
        if self.updated_at == 0.0:
            return float("inf")
        return time.monotonic() - self.updated_at

    def is_stale(self, threshold_s: float = 3.0) -> bool:
        return self.age_s() > threshold_s


@dataclass(frozen=True)
class MixerDeckReading:
    deck: int
    upfader_raw: float
    upfader_norm: float
    upfader_label: str
    low_raw: float
    low_norm: float
    low_label: str


@dataclass(frozen=True)
class MixerAuthoritySnapshot:
    valid: bool
    deck: Mapping[int, MixerDeckReading]
    updated_at: float
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "deck", MappingProxyType(dict(self.deck)))


@dataclass(frozen=True)
class RBMasterState:
    deck: Optional[int]
    valid: bool
    source: str
    updated_at: float
    fallback_reason: str = ""


@dataclass
class BridgeEvent:
    """Immutable typed event; produced by any source, consumed by StateManager."""
    kind: str       # one of Ev.* constants
    deck: int       # 1 or 2 (0 = global / irrelevant)
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""          # producer name, e.g. 'rb_state', 'osc', 'lsof', 'memory'
    mono: float = field(default_factory=time.monotonic)


@dataclass
class OutputState:
    """Mutable push-loop state. Owned exclusively by the push-loop closure."""
    active_deck: int = 1
    rb_master_deck: Optional[int] = None
    rb_master_deck_valid: bool = False
    rb_master_deck_source: str = "unknown"
    rb_master_deck_updated_at: float = 0.0
    rb_master_fallback_reason: str = "unknown"
    active_deck_authority_reason: str = "startup"
    mixer_authority_valid: bool = False
    mixer_authority_updated_at: float = 0.0
    mixer_fallback_reason: str = "missing_offsets"
    was_playing: bool = False
    last_beat_elapsed_ms: int = 0
    last_sent_elapsed_ms: int = 0
    last_sent_bpm: float = 0.0
    last_arm_mono: float = 0.0        # suppresses stop-detection for 3 s after arm/switch
    not_playing_since: float = 0.0   # stop debounce start time (0 = not counting)
    play_settle_after: float = 0.0   # monotonic: when to fire flash-arm after resume
    stop_elapsed_ms: int = 0          # position at last stop (for restart detection)
    push_reset_bpm: bool = False      # signal: reset last_sent_bpm on next tick
    # Lighting state machine — updated only by _update_lighting() in _push_tick
    lighting_mode:         str   = "idle"  # last applied lighting mode ("scripted"/"autoloop"/"idle")
    lighting_desired:      str   = "idle"  # desired mode, tracked for debounce
    lighting_stable_since: float = 0.0    # monotonic time when lighting_desired last changed
    last_armed_filepath:   str   = ""     # filepath sent in last autoloop arm; re-arm if changed
    autoloop_arm_bpm:      float = 0.0    # BPM chosen when current autoloop armed
    autoloop_arm_deck:     int   = 0      # deck for autoloop_arm_bpm
    autoloop_arm_pending:  bool  = False  # True after arm, waiting for phrase lock
    autoloop_arm_sync_beat: int  = 0      # Target phrase boundary beat
    autoloop_arm_target_elapsed_ms: int = 0
    autoloop_arm_target_source: str = ""
    autoloop_arm_pending_since: float = 0.0  # monotonic time when arm was triggered
    last_autoloop_status_phrase_beat: int = 0  # last 32-beat phrase logged
    pending_live_bpm: float = 0.0
    last_live_follow_bpm: float = 0.0
    last_live_follow_send_mono: float = 0.0
    autoloop_anchor_elapsed_ms: int = 0
    autoloop_anchor_abs_beat: float = 0.0
    autoloop_anchor_bpm: float = 0.0
    autoloop_change_on_next_beat: bool = False
    autoloop_arm_after_master_change: bool = False
    autoloop_master_change_source: str = ""
    pending_autoloop_arm_meta: Optional[TrackMetadata] = None
    pending_autoloop_arm_deck: int = 0
    pending_autoloop_arm_mirror: int = 0
    pending_autoloop_arm_active: int = 0
    pending_autoloop_arm_source: str = ""
    pending_autoloop_arm_reason: str = ""
    live_follow_generation: int = 0
    drop_cut_armed: bool = False
    drop_rearm_beat: int = 0
    breakdown_active: bool = False
    breakdown_restore_beat: int = 0
    phrase_anchor_last_beat: int = -1
    # Origin beat for the 32-beat MIDI re-fire counter (Piece 2). -1 = no phrase
    # marker seen yet on this track → fall back to the absolute 32-beat grid.
    midi_refire_origin_beat: int = -1


@dataclass
class ArmSequence:
    """Non-blocking two-phase scripted arm.

    Phase 0 fires immediately (clear all 4 decks + play off).
    Phase 1 fires when time.monotonic() >= fire_at (send_deck_load to active + 3 + 4).
    Checked each push tick via StateManager._check_pending_arm().
    """
    deck:       int
    track_id:   int
    fire_at:    float
    arm_meta:   "TrackMetadata"
    elapsed_ms: int
    mirror:     int
    active_deck: int


# ── Event kind constants ──────────────────────────────────────────────────────

class Ev:
    MIXER_STATE       = "mixer_state"       # global, payload={snapshot: MixerAuthoritySnapshot}
    MASTER_CHANGED    = "master_changed"    # deck = new master (1 or 2)
    LEGACY_ACTIVE_DECK = "legacy_active_deck" # deck = OSC/debug fallback active-deck request
    TRACK_LOADED      = "track_loaded"      # deck, payload={title: str, load_gen: int}
    PLAY              = "play"              # deck
    PAUSE             = "pause"             # deck
    FILEPATH_RESOLVED = "filepath_resolved" # deck, payload={filepath, bpm, content_id,
                                            #   first_beat_ms, soundswitch_id, total_ms, load_gen,
                                            #   laser_tag_beats?: list[float] (ANLZ-resolved path only)}
    ANLZ_PATH         = "anlz_path"         # deck, payload={anlz_path: str} — fires before TRACK_LOADED
    ANLZ_DATA         = "anlz_data"         # deck, payload={drop_beat_indices: list[int], load_gen: int}
    BPM_UPDATE        = "bpm_update"        # deck, payload={bpm: float}
    TC_UPDATE         = "tc_update"         # deck, payload={elapsed_ms: int}
    SCRIPTED_ARM      = "scripted_arm"      # deck, payload={scripted_id: int}
    SCRIPTED_CLEAR    = "scripted_clear"    # deck
    RB_RESTARTED      = "rb_restarted"      # global, payload={pid: int}
    SMART_DROP_TOGGLE = "smart_drop_toggle" # global runtime toggle from menu/command channel
    SMART_BREAKDOWN_TOGGLE = "smart_breakdown_toggle"
    # Laser Director events — all global (deck=0)
    LASER_TOGGLE               = "laser_toggle"               # toggle enabled state
    LASER_SET_ENABLED          = "laser_set_enabled"          # payload={enabled: bool}
    LASER_SCENE                = "laser_scene"                # payload={scene: str, ttl_s: float}
    LASER_BLACKOUT             = "laser_blackout"             # latch emergency blackout
    LASER_CLEAR_BLACKOUT       = "laser_clear_blackout"       # clear emergency blackout
    LASER_CLEAR_SCENE_OVERRIDE = "laser_clear_scene_override" # clear manual scene only
    LASER_SET_PERSONALITY      = "laser_set_personality"      # internal/test only; payload={personality: str}
    # LED Look Director events — all global (deck=0). Payload-only contracts
    # for later StateManager ownership.
    LED_SET_ENABLED            = "led_set_enabled"            # payload={enabled: bool}
    LED_SCENE                  = "led_scene"                  # payload={look: str, ttl_s?: float}
    LED_BLACKOUT               = "led_blackout"               # payload={reason?: str}; reason is owner key
    LED_CLEAR_BLACKOUT         = "led_clear_blackout"         # payload={reason?: str}; clear owner key
    LED_CLEAR_SCENE_OVERRIDE   = "led_clear_scene_override"   # clear manual scene only
    LED_PALETTE_PAD            = "led_palette_pad"            # payload={name: str, phase: "down"|"up", intent?: queue|override}
    LED_PALETTE_LOCK_PAD       = "led_palette_lock_pad"       # payload={intent?: lock|unlock}
    LED_MUTE_PAD               = "led_mute_pad"               # toggle LED mute owner
    LED_RAINBOW_PAD            = "led_rainbow_pad"            # toggle Rainbow mode
    LED_ZONE_PAD               = "led_zone_pad"               # payload={name: str, phase: "down"|"up"}
    LED_MANUAL_PAD             = "led_manual_pad"             # payload={name: str}
    LED_MAX_ENERGY_PAD         = "led_max_energy_pad"         # payload={}
    LED_ENGINE_MODE            = "led_engine_mode"            # payload={mode: "v1"|"v2"}
    LED_TRACK_IDENTITY         = "led_track_identity"         # payload={deck, load_gen, key, record}
    # Drop presentation policy (Package 3, AWR-119) — global (deck=0).
    LASER_SOLO_PAD             = "laser_solo_pad"             # arm/disarm/veto the pending Laser Solo
