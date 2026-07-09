"""Data models for the Phase 3 LED bridge skeleton.

These models are intentionally small and frozen where appropriate so policy and
transport layers can exchange immutable decisions without runtime-side mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Dict, Tuple

RGB = Tuple[int, int, int]


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
    motion_style: str = ""
    travel: str = ""


@dataclass(frozen=True)
class Palette:
    """A named palette entry in the color engine library (§7a)."""
    range: Tuple[str, str] = ("blue", "cyan")
    spread: float = 0.10
    weight: float = 1.0
    dwell: Optional[int] = None  # None → use global palette_dwell_tracks
    focus_modes: Dict[str, float] = field(default_factory=dict)  # empty → full-range roam
    type: str = "journey"
    rgb: Optional[Tuple[int, int, int]] = None


@dataclass(frozen=True)
class ZoneRampConfig:
    base_ramp: tuple[RGB, RGB, RGB]
    accent_ramp: tuple[RGB, RGB]
    slot5_white: RGB = (255, 255, 255)
    hue_span: float = 0.06


@dataclass(frozen=True)
class IdentityV2Config:
    enabled: bool = False
    zones: Dict[str, ZoneRampConfig] = field(default_factory=dict)
    bass_norm: tuple[float, float] = (0.5856, 0.9688)
    store_path: str = "local/state/led_identity_v2.json"
    soft_flip_beats: float = 8.0
    palate_reset_enabled: bool = True
    palate_reset_beats: float = 4.0
    palate_reset_dim: float = 0.35
    bloom_enabled: bool = True
    bloom_hold_beats: float = 8.0
    bloom_beats: float = 8.0
    bloom_dim: float = 0.3
    punch_sharp_threshold: float = 0.6
    budget_wide_threshold: float = 0.5


def _f2_num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _f2_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class F2Config:
    """LIGHTING ENGINE v2 Feature 2 (moments / darkness / drop-typing) config
    block (AWR-163). An ABSENT block ⇒ enabled False, so an un-mirrored live
    config stays byte-identical to v1 (kill test); the example config ships
    enabled True and the operator's mirror + restart activates it. Validation
    fails closed to defaults; unknown legacy keys are ignored."""
    enabled: bool = False
    # {family: {tier(int): (look names...)}}. Empty ⇒ drop looks keep today's
    # rotation pick (unknown cell also falls back to rotation).
    drop_look_routing: Dict[str, Dict[int, Tuple[str, ...]]] = field(default_factory=dict)
    balloon_perc_boundary: float = 0.35      # C§6f pinned; TUNE-LIVE
    dip_cap_beats: int = 4                    # D§4.1-5 TUNE-LIVE
    flick_ms: int = 200                       # D§4.1-6 TUNE-LIVE
    impact_burndown_enabled: bool = False     # AWR-162 (C) ships disabled
    impact_burndown_ease_beats: int = 8
    # AWR-170 (D.2): lasers black out this many beats before every chorus phrase
    # start. ABSENT ⇒ 0 ⇒ feature fully off (the mirror rule — no key = today's
    # behavior); the example config ships 4.
    pre_chorus_laser_beats: int = 0

    @classmethod
    def from_dict(cls, data: Any) -> "F2Config":
        src = data if isinstance(data, dict) else {}
        routing: Dict[str, Dict[int, Tuple[str, ...]]] = {}
        raw = src.get("drop_look_routing")
        if isinstance(raw, dict):
            for fam, tiers in raw.items():
                if not isinstance(tiers, dict):
                    continue
                cell: Dict[int, Tuple[str, ...]] = {}
                for tk, names in tiers.items():
                    try:
                        ti = int(tk)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(names, list):
                        cell[ti] = tuple(str(n) for n in names)
                if cell:
                    routing[str(fam)] = cell
        bd = src.get("impact_burndown")
        bd = bd if isinstance(bd, dict) else {}
        return cls(
            enabled=bool(src.get("enabled", False)),
            drop_look_routing=routing,
            balloon_perc_boundary=_f2_num(src.get("balloon_perc_boundary"), 0.35),
            dip_cap_beats=_f2_int(src.get("dip_cap_beats"), 4),
            flick_ms=_f2_int(src.get("flick_ms"), 200),
            impact_burndown_enabled=bool(bd.get("enabled", False)),
            impact_burndown_ease_beats=_f2_int(bd.get("ease_beats"), 8),
            pre_chorus_laser_beats=max(0, _f2_int(src.get("pre_chorus_laser_beats"), 0)),
        )


def _f4_param_dict(raw: Any) -> Dict[str, Any]:
    """Coerce a seasoning param dict to {str: finite-number | str}. Anything else
    (nested objects, bools, non-finite) is dropped — fail-closed to no-op."""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            f = float(value)
            if f == f and f not in (float("inf"), float("-inf")):
                out[str(key)] = f
        elif isinstance(value, str):
            out[str(key)] = value
    return out


@dataclass(frozen=True)
class F4Config:
    """LIGHTING ENGINE v2 Feature 4 (texture seasoning) config block (AWR-164).
    Absent block ⇒ enabled False, so an un-mirrored live config stays byte-
    identical to F2-only (kill test); the example ships enabled and the operator's
    mirror + restart activates it. S-2 containment: nothing here schedules,
    darkens, or types anything — it only picks variant params inside an already-
    selected look. Validation fails closed to defaults; unknown keys are ignored."""
    enabled: bool = False
    # lowmid_pulse stays UNCONSUMED behind this flag (C§6d experimental) — the
    # busy-pulse duty is recorded in the plan for observability, rendered by
    # nothing. Flipping this true renders nothing today (no consumer exists).
    busy_pulse_experimental: bool = False
    # {seasoning_key: {param: value}} merged into the drop cue's params. Keys are
    # family+texture (house_stab / house_sustain / wall_trap / wall_dense / ...);
    # an unknown key ⇒ {} ⇒ family default variant (containment).
    variant_seasoning: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # look names to prefer during euphoric windows (fail-open — empty, or none of
    # them in the bank, ⇒ no added preference; only ever NARROWS within the bank).
    euphoric_bright_looks: Tuple[str, ...] = ()
    # params merged into a quiet-section role cue during a MEASURED simmer.
    simmer_seasoning: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> "F4Config":
        src = data if isinstance(data, dict) else {}
        seasoning: Dict[str, Dict[str, Any]] = {}
        raw = src.get("variant_seasoning")
        if isinstance(raw, dict):
            for key, params in raw.items():
                cell = _f4_param_dict(params)
                seasoning[str(key)] = cell   # empty cell kept ⇒ explicit "no-op"
        bright_raw = src.get("euphoric_bright_looks")
        bright = tuple(str(n) for n in bright_raw) if isinstance(bright_raw, list) else ()
        return cls(
            enabled=bool(src.get("enabled", False)),
            busy_pulse_experimental=bool(src.get("busy_pulse_experimental", False)),
            variant_seasoning=seasoning,
            euphoric_bright_looks=bright,
            simmer_seasoning=_f4_param_dict(src.get("simmer_seasoning")),
        )


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
    locked_palette_by_look: Dict[str, str] = field(default_factory=dict)
    palette_control: Mapping[str, Any] = field(default_factory=dict, compare=False)
    palette_control_bindings: tuple[Any, ...] = field(default_factory=tuple, compare=False)
    exempt_looks: Tuple[str, ...] = field(default_factory=tuple)
    diy_color_tags: Dict[str, str] = field(default_factory=dict)
    set_seed_mode: str = "random"
    palettes: Dict[str, Palette] = field(default_factory=dict)
    v2: Optional[IdentityV2Config] = None


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
class LEDScriptedModePolicy:
    """Scripted-track LED role remap policy."""
    default_role: str = "breakdown"
    role_map: Mapping[str, str] = field(default_factory=dict, compare=False)


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
    scripted_mode: LEDScriptedModePolicy = field(default_factory=LEDScriptedModePolicy)
    blank_role_hold: bool = True


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
    look_preference: Optional[Callable[[str], bool]] = field(default=None, compare=False)


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
    blank_role_hold: bool = True


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
