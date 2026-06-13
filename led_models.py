"""Data models for the Phase 3 LED bridge skeleton.

These models are intentionally small and frozen where appropriate so policy and
transport layers can exchange immutable decisions without runtime-side mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class LEDTarget:
    name: str
    label: str
    device_ref: str
    expected_model: str
    control_route: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    mirror_targets: tuple[str, ...] = field(default_factory=tuple)


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
class LEDRateLimits:
    queue_maxsize: int = 8
    scene_retrigger_cooldown_s: float = 4.0
    high_impact_cooldown_s: float = 12.0
    request_timeout_s: float = 2.0
    worker_shutdown_timeout_s: float = 1.0


@dataclass(frozen=True)
class LEDAutomation:
    offset_s: float = 0.0


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


@dataclass(frozen=True)
class LEDLookDirectorStatus:
    available: bool
    enabled: bool
    dry_run: bool
    automation_enabled: bool
    automation_offset_s: float
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
