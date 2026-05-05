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
from typing import Any, Optional


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

    def is_empty(self) -> bool:
        return not self.filepath


@dataclass
class DeckState:
    """Authoritative per-deck state. Written only by StateManager."""
    number: int
    meta: TrackMetadata = field(default_factory=TrackMetadata)
    playing: bool = False
    elapsed_ms: int = 0
    # TL-managed scripted show ID (0 = unscripted / none)
    scripted_id: int = 0
    # generation counter: incremented on every track_loaded event so
    # in-flight lsof threads can detect staleness
    load_gen: int = 0
    # Track title from TL [EVENT] Deck X loaded — used as DB lookup fallback
    # when ANLZ fails and lsof can't disambiguate by track length
    tl_title: str = ""


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


@dataclass
class BridgeEvent:
    """Immutable typed event; produced by any source, consumed by StateManager."""
    kind: str       # one of Ev.* constants
    deck: int       # 1 or 2 (0 = global / irrelevant)
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""          # 'tl_log', 'osc', 'lsof', 'memory'
    mono: float = field(default_factory=time.monotonic)


@dataclass
class OutputState:
    """Mutable push-loop state. Owned exclusively by the push-loop closure."""
    active_deck: int = 1
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
    autoloop_arm_pending_since: float = 0.0  # monotonic time when arm was triggered
    last_autoloop_status_mono: float = 0.0  # rate-limit autoloop status diagnostics
    pending_live_bpm: float = 0.0
    last_live_follow_bpm: float = 0.0
    last_live_follow_send_mono: float = 0.0
    autoloop_change_on_next_beat: bool = False
    autoloop_arm_after_master_change: bool = False
    autoloop_master_change_source: str = ""
    pending_autoloop_arm_meta: Optional[TrackMetadata] = None
    pending_autoloop_arm_deck: int = 0
    pending_autoloop_arm_mirror: int = 0
    pending_autoloop_arm_active: int = 0
    pending_autoloop_arm_source: str = ""
    live_follow_generation: int = 0


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
    MASTER_CHANGED    = "master_changed"    # deck = new master (1 or 2)
    TRACK_LOADED      = "track_loaded"      # deck, payload={title: str, load_gen: int}
    PLAY              = "play"              # deck
    PAUSE             = "pause"             # deck
    FILEPATH_RESOLVED = "filepath_resolved" # deck, payload={filepath, bpm, content_id,
                                            #   first_beat_ms, soundswitch_id, total_ms, load_gen}
    ANLZ_PATH         = "anlz_path"         # deck, payload={anlz_path: str} — fires before TRACK_LOADED
    BPM_UPDATE        = "bpm_update"        # deck, payload={bpm: float} — from ENGINE STATE every ~15s
    TC_UPDATE         = "tc_update"         # deck, payload={elapsed_ms: int} — from ENGINE STATE TC
    SCRIPTED_ARM      = "scripted_arm"      # deck, payload={scripted_id: int}
    SCRIPTED_CLEAR    = "scripted_clear"    # deck  (TL value=1 / default)
    RB_RESTARTED      = "rb_restarted"      # global, payload={pid: int}
    LIGHTING_SCRIPTED_ON = "lighting_scripted_on"  # master deck: scripted track playing
    LIGHTING_AUTOLOOP_ON = "lighting_autoloop_on"  # master deck: unscripted track playing
    LIGHTING_OFF         = "lighting_off"          # master deck: not playing
