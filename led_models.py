"""Data models for the Phase 3 LED bridge skeleton.

These models are intentionally small and frozen where appropriate so policy and
transport layers can exchange immutable decisions without runtime-side mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Dict, Tuple


@dataclass(frozen=True)
class LEDRealtimeConfig:
    enabled: bool = False
    protocol: str = ""
    ip: str = ""
    port: int = 4003
    segments: int = 20
    header: str = ""
    header_bytes: tuple[int, ...] = field(default_factory=tuple)
    stretch: bool = False
    fps: int = 30
    activate_pt: str = ""
    deactivate_pt: str = ""
    proof_status: str = "not_proven"
    proof_date: str = ""


@dataclass(frozen=True)
class LEDTarget:
    name: str
    label: str
    device_ref: str
    expected_model: str
    control_route: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    mirror_targets: tuple[str, ...] = field(default_factory=tuple)
    backend: str = "cloud_diy"
    realtime: LEDRealtimeConfig = field(default_factory=LEDRealtimeConfig)


@dataclass(frozen=True)
class LEDLook:
    name: str
    target: str
    action: str
    scene_ref: str = ""
    fallback: str = ""
    safety_class: str = "safe"
    brightness: int = 100
    allow_strobe: bool = False
    backend: str = "cloud_diy"
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)
    color_source: str = "engine"
    diy_color: str = ""


@dataclass(frozen=True)
class Palette:
    """A named palette entry in the color engine library (§7a)."""
    range: Tuple[str, str] = ("blue", "cyan")
    white: float = 0.0
    spread: float = 0.10
    weight: float = 1.0
    dwell: Optional[int] = None  # None → use global palette_dwell_tracks
    focus_modes: Dict[str, float] = field(default_factory=dict)  # empty → full-range roam


# Canonical default scale stops (6 stops from §7/§15.5).
_DEFAULT_SCALE_STOPS: Dict[str, Tuple[int, int, int]] = {
    "green":   (0, 255, 0),
    "cyan":    (0, 255, 255),
    "blue":    (0, 0, 255),
    "purple":  (160, 0, 255),
    "magenta": (255, 0, 160),
    "red":     (255, 0, 0),
}


@dataclass(frozen=True)
class ColorEngineConfig:
    """Typed container for the color_engine config block (§7, §15.5).

    This is pure model/config plumbing — no engine runtime logic.
    """
    enabled: bool = True
    scale_stops: Dict[str, Tuple[int, int, int]] = field(
        default_factory=lambda: dict(_DEFAULT_SCALE_STOPS)
    )
    palette_dwell_tracks: int = 4
    snap_eligible_drop_indices: Tuple[int, ...] = (2, 3)
    big_shift_chance: float = 0.25
    big_shift_weight_bias: float = 1.0
    drama_by_role: bool = True
    role_spread: Dict[str, float] = field(
        default_factory=lambda: {"drop": 0.35, "groove": 0.12, "ambient": 0.10}
    )
    step_within_section: Dict[str, bool] = field(
        default_factory=lambda: {"drop": False, "post_drop": True, "groove": True}
    )
    fade_beats_by_role: Dict[str, float] = field(
        default_factory=lambda: {
            "drop": 0.0,
            "buildup": 0.0,
            "breakdown": 4.0,
            "post_drop": 2.0,
            "groove": 2.0,
            "ambient": 4.0,
        }
    )
    slot_fill_strategy_by_look: Dict[str, str] = field(default_factory=dict)
    slot_fill_strategy_by_role: Dict[str, str] = field(default_factory=dict)
    slot_mono_chance_by_look: Dict[str, float] = field(default_factory=dict)
    exempt_looks: Tuple[str, ...] = field(default_factory=tuple)
    diy_color_tags: Dict[str, str] = field(default_factory=dict)
    set_seed_mode: str = "random"
    palettes: Dict[str, Palette] = field(default_factory=dict)


@dataclass(frozen=True)
class LEDBank:
    ambient: tuple[str, ...] = field(default_factory=tuple)
    groove: tuple[str, ...] = field(default_factory=tuple)
    buildup: tuple[str, ...] = field(default_factory=tuple)
    pre_drop: tuple[str, ...] = field(default_factory=tuple)
    drop: tuple[str, ...] = field(default_factory=tuple)
    post_drop: tuple[str, ...] = field(default_factory=tuple)
    breakdown: tuple[str, ...] = field(default_factory=tuple)
    utility: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LEDDropPair:
    drop: str
    post_drop: str
    duration_beats: float = 8.0


@dataclass(frozen=True)
class LEDRateLimits:
    queue_maxsize: int = 8
    scene_retrigger_cooldown_s: float = 4.0
    high_impact_cooldown_s: float = 12.0
    request_timeout_s: float = 2.0
    worker_shutdown_timeout_s: float = 1.0
    # WI-3: same-role min dwell gate in the coordinator
    min_look_dwell_s: float = 1.5
    # WI-5: hard floor on DIY↔RT transport flips (default OFF, flag-guarded)
    transport_switch_cooldown_s: float = 2.0
    # WI-6: RT reconcile window and interval after a cloud DIY dispatch
    rt_reconcile_window_s: float = 5.0
    rt_reconcile_interval_s: float = 1.0


@dataclass(frozen=True)
class LEDAutomation:
    offset_s: float = 0.0
    cloud_offset_s: float = 0.0
    realtime_offset_s: float = 0.0


@dataclass(frozen=True)
class LEDSafety:
    max_brightness: int = 100
    allow_strobe: bool = True
    max_strobe_duration_ms: int = 750
    high_impact_cooldown_s: float = 12.0
    drop_flash_duration_ms: int = 750
    emergency_blackout_always_available: bool = True
    scripted_mode_automation: bool = False


@dataclass(frozen=True)
class LEDConfig:
    schema_version: int
    enabled: bool
    dry_run: bool
    automation_enabled: bool
    targets: dict[str, LEDTarget]
    looks: dict[str, LEDLook]
    banks: dict[str, LEDBank]
    safe_default: str
    blackout: str
    automation: LEDAutomation
    rate_limits: LEDRateLimits
    safety: LEDSafety
    drop_pairs: dict[str, LEDDropPair] = field(default_factory=dict)
    post_drop_cycle_beats: float = 32.0
    color_engine: Optional[ColorEngineConfig] = None


@dataclass(frozen=True)
class LEDConfigResult:
    available: bool
    reason: str
    config: Optional[LEDConfig] = None
    errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LEDContext:
    role: str = "ambient"
    manual_look: Optional[str] = None
    emergency_blackout: bool = False
    target_override: str = ""
    active_deck: int = 0
    playing: bool = False
    lighting_mode: str = ""
    scripted_id: int = 0
    # M1b WI-3: optional DIY-eligibility predicate supplied by the color engine.
    # When None (engine off), the director applies no palette filtering.
    diy_eligible: Optional[Callable[[str], bool]] = field(default=None, compare=False)


@dataclass(frozen=True)
class LEDLookDecision:
    look: str
    target: str
    action: str
    scene_ref: str
    reason: str
    source: str
    priority: int
    role: str
    backend: str = "cloud_diy"
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)
    # M1b WI-5: per-look color source ("engine" → injectable, "baked" → never recolored).
    color_source: str = field(default="engine", compare=False)


@dataclass(frozen=True)
class BeatAnchor:
    deck: int
    abs_beat_pos: float
    bpm: float
    captured_monotonic: float
    playing: bool
    permitted: bool


@dataclass(frozen=True)
class LEDLookDirectorStatus:
    available: bool
    enabled: bool
    dry_run: bool
    automation_enabled: bool
    automation_offset_s: float
    automation_cloud_offset_s: float
    automation_realtime_offset_s: float
    scripted_mode_automation: bool
    current_look: str
    last_reason: str
    last_source: str
    manual_override: str
    emergency_blackout: bool
    role_cursors: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class LEDAdapterCommand:
    look: str
    target: str
    action: str
    scene_ref: str
    reason: str
    source: str
    role: str


@dataclass(frozen=True)
class LEDAdapterStatus:
    available: bool
    running: bool
    dry_run: bool
    degraded: bool
    degraded_reason: str
    queue_depth: int
    queue_max: int
    accepted_count: int
    rejected_count: int
    dropped_count: int
    last_error: str
    queue_full_count: int = 0
    deduped_count: int = 0
    rate_limited_count: int = 0
    send_count: int = 0
    send_error_count: int = 0
    malformed_response_count: int = 0
    consecutive_send_failures: int = 0
    circuit_open: bool = False
    circuit_open_until: float = 0.0
