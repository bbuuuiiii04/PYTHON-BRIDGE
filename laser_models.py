"""Frozen dataclasses for the Laser Director subsystem.

These types cross the boundary between StateManager and LaserDirector.
All types are frozen so callers cannot accidentally mutate shared state.
"""
from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class LaserSceneDecision:
    """Result of one LaserDirector policy evaluation.

    ``scene``    — the chosen scene name (an arbitrary operator-defined string).
    ``reason``   — short human-readable label for why this scene was chosen.
    ``priority`` — numeric priority level (lower = higher priority).
    ``source``   — originating policy branch ("emergency", "manual", "policy").
    """
    scene: str
    reason: str
    priority: int
    source: str
