"""Frozen dataclasses for the Laser Director subsystem.

These types cross the boundary between StateManager and LaserDirector.
All types are frozen so callers cannot accidentally mutate shared state.

Runtime-crossing types (used by both config and runtime):
  LaserMidiMessage  — a single MIDI command produced by a scene trigger.
  LaserScene        — a validated scene with MIDI mapping and safety metadata.
  LaserPersonality  — a role-to-scene-name mapping profile.

Tick-boundary types (built inside StateManager._push_tick):
  LaserContext      — immutable bridge state snapshot passed to tick().
  LaserSceneDecision — result of one policy evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .smart_phrasing import SmartPhrasingState


@dataclass(frozen=True)
class LaserMidiMessage:
    """A single MIDI command that a scene trigger produces.

    kind       — "note_pulse", "note_on", "note_off", or "cc".
    channel    — MIDI channel 1–16.
    note       — MIDI note number 0–127 (used by note_pulse/note_on/note_off).
    velocity   — note velocity 0–127.
    cc         — CC number 0–127 (used by cc kind).
    value      — CC value 0–127 (used by cc kind).
    duration_ms — note-on hold time in ms for note_pulse; validated 10–250.
    behavior    — "pulse", "hold_ms", "hold_beats", "note_on", or "note_off".
                  Backward compatibility: when omitted, runtime falls back to kind.
    hold_ms     — explicit hold duration for hold_ms behavior; validated 10–30000.
    hold_beats  — beat-relative hold duration for hold_beats behavior; validated
                  0.25–128 and materialized by LaserSceneExecutor using ctx.bpm.
    """
    kind: str = "note_pulse"
    channel: int = 1
    note: int = 0
    velocity: int = 127
    cc: int = 0
    value: int = 0
    duration_ms: int = 80
    behavior: str = "pulse"
    hold_ms: int = 0
    hold_beats: float = 0.0


@dataclass(frozen=True)
class LaserScene:
    """A fully validated scene definition.

    name          — the arbitrary operator-defined scene key.
    scene_type    — "static", "autoloop", or "utility".
    safety_class  — one of safe/movement_low/movement_medium/movement_high/
                    high_impact/strobe/blackout.
    midi          — the MIDI message sent when this scene is triggered.
    fallback_scene — scene name to use when this scene is blocked by cooldown
                    or safety. Must be a key in the scenes dict.
    cooldown_beats — minimum beat hold before this scene can re-trigger.
    immediate      — when True, may trigger between phrase boundaries.
    ss_look_name   — optional SoundSwitch look name for operator orientation only.
    """
    name: str
    scene_type: str
    safety_class: str
    midi: LaserMidiMessage
    fallback_scene: str = "safe_static"
    cooldown_beats: float = 0.0
    immediate: bool = False
    label: str = ""
    ss_look_name: str = ""


@dataclass(frozen=True)
class LaserPersonality:
    """A role-to-scene-name mapping for one musical personality/genre.

    All scene name values must reference keys in the LaserConfig.scenes dict.
    """
    name: str
    safe_scene: str
    default_scene: str
    phrase_scene: str
    buildup_scene: str
    pre_drop_scene: str
    drop_scene: str
    post_drop_scene: str
    breakdown_scene: str
    transition_scene: str
    phrase_bank: tuple[str, ...] = field(default_factory=tuple)
    buildup_bank: tuple[str, ...] = field(default_factory=tuple)
    drop_bank: tuple[str, ...] = field(default_factory=tuple)
    post_drop_bank: tuple[str, ...] = field(default_factory=tuple)
    breakdown_bank: tuple[str, ...] = field(default_factory=tuple)
    allow_high_impact: bool = False
    phrase_interval_beats: int = 32
    minimum_scene_hold_beats: int = 0
    normal_changes_only_on_phrase_boundary: bool = False
    buildup_lookahead_beats: int = 32


@dataclass(frozen=True)
class LaserContext:
    """Minimal immutable snapshot of bridge state passed to LaserDirector.tick().

    Built inside StateManager._push_tick from already-computed local variables.
    Must not require any I/O, dict construction, or MIDI/config work to create.
    """
    active_deck: int
    playing: bool
    elapsed_ms: int
    bpm: float
    beatpos: float       # 0.0–4.0 within current bar
    abs_beat: float      # absolute beat count from track start
    position_stale: bool
    lighting_mode: str   # "idle", "autoloop", "scripted"
    os2l_connected: bool
    active_track_loaded: bool = False
    autoloop_ready: bool = False
    autoloop_tick_just_fired: bool = False
    scripted_id: int = 0
    smart_drop_blackout_active: bool = False
    smart_drop_blackout_arm: bool = False
    smart_phrasing_blackout_arm: bool = False
    # SmartPhrasing state produced by StateManager each tick and consumed by
    # LaserDirector / LaserSceneExecutor for phrase policy and transition-mask behavior.
    smart_phrasing: Optional[SmartPhrasingState] = None


@dataclass(frozen=True)
class LaserSceneDecision:
    """Result of one LaserDirector policy evaluation.

    ``scene``    — the chosen scene name (an arbitrary operator-defined string).
    ``reason``   — short human-readable label for why this scene was chosen.
    ``role``     — stable policy role used by scene-bank/executor logic.
    ``priority`` — numeric priority level (lower = higher priority).
    ``source``   — originating policy branch ("emergency", "manual", "policy").
    """
    scene: str
    reason: str
    priority: int
    source: str
    role: str = "idle"
