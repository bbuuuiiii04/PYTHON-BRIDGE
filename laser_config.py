"""Laser Director JSON config loader and validator.

Public API
----------
load_laser_director_config(path=None) -> LaserConfigResult

Path resolution (in order):
  1. ``path`` argument, if provided.
  2. ``RBSS_LASER_CONFIG`` environment variable.
  3. ``<repo_root>/config/laser_director.json``.
  4. If the file is absent → LaserConfigResult(available=False, reason="not_configured").

Missing config is not a bridge error. Invalid config disables Laser Director
and records errors; the bridge still starts.

This module performs file I/O only at startup (called from __main__.py).
It must not be imported or called from StateManager._push_tick.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .laser_models import LaserMidiMessage, LaserPersonality, LaserScene

log = logging.getLogger("laser_config")

_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "laser_director.json"

_VALID_KINDS = frozenset({"note_pulse", "note_on", "note_off", "cc"})
_VALID_SAFETY_CLASSES = frozenset({
    "safe", "movement_low", "movement_medium", "movement_high",
    "high_impact", "strobe", "blackout",
})
_VALID_SCENE_TYPES = frozenset({"static", "autoloop", "utility"})

_DURATION_MIN = 10
_DURATION_MAX = 250

_PERSONALITY_ROLE_FIELDS = (
    "safe_scene",
    "default_scene",
    "phrase_scene",
    "buildup_scene",
    "pre_drop_scene",
    "drop_scene",
    "post_drop_scene",
    "breakdown_scene",
    "transition_scene",
)
_LIFECYCLE_SCENE_FIELDS = (
    "startup_scene",
    "stop_scene",
    "stale_scene",
    "emergency_scene",
    "fallback_scene",
)


# ---------------------------------------------------------------------------
# Config result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LaserConfig:
    """Fully validated Laser Director configuration.

    Produced only by load_laser_director_config() after all validation passes.
    """
    enabled: bool
    dry_run: bool
    midi_output_port: str
    scenes: dict[str, LaserScene]
    personalities: dict[str, LaserPersonality]
    default_personality: str
    startup_scene: str
    stop_scene: str
    stale_scene: str
    emergency_scene: str
    fallback_scene: str


@dataclass(frozen=True)
class LaserConfigResult:
    """Result of a config load attempt.

    reason values:
      "ok"               — config loaded and validated successfully.
      "not_configured"   — config file absent; Laser Director is disabled.
      "invalid_config"   — config present but failed validation.
      "dependency_missing" — a required Python dependency is not installed.
    """
    available: bool
    reason: str
    config: Optional[LaserConfig] = None
    errors: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_laser_director_config(
    path: Optional[str] = None,
) -> LaserConfigResult:
    """Load and validate the Laser Director JSON config.

    Never raises. Returns LaserConfigResult in all cases.
    """
    resolved = _resolve_path(path)

    if resolved is None or not resolved.exists():
        log.debug("[laser_config] config file absent → not_configured")
        return LaserConfigResult(available=False, reason="not_configured")

    log.debug("[laser_config] loading config from %s", resolved)
    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return _invalid(f"cannot read config file {resolved}: {exc}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _invalid(f"invalid JSON in {resolved}: {exc}")

    if not isinstance(data, dict):
        return _invalid("config root must be a JSON object")

    errors = _validate(data)
    if errors:
        log.warning("[laser_config] config invalid (%d error(s))", len(errors))
        for e in errors:
            log.warning("[laser_config]   %s", e)
        return LaserConfigResult(
            available=False,
            reason="invalid_config",
            errors=tuple(errors),
        )

    config = _build_config(data)
    log.info(
        "[laser_config] loaded  enabled=%s  dry_run=%s  scenes=%d  personalities=%d",
        config.enabled,
        config.dry_run,
        len(config.scenes),
        len(config.personalities),
    )
    return LaserConfigResult(available=True, reason="ok", config=config)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path(explicit: Optional[str]) -> Optional[Path]:
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("RBSS_LASER_CONFIG")
    if env:
        return Path(env)
    return _DEFAULT_CONFIG_PATH


def _invalid(msg: str) -> LaserConfigResult:
    return LaserConfigResult(
        available=False,
        reason="invalid_config",
        errors=(msg,),
    )


def _validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    # enabled
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("'enabled' must be a boolean")
        enabled = False

    # dry_run (may be absent → defaults to True)
    dry_run = data.get("dry_run", True)
    if not isinstance(dry_run, bool):
        errors.append("'dry_run' must be a boolean")
        dry_run = True

    # midi_output_port required when live MIDI is active
    midi_port = data.get("midi_output_port", "")
    if not isinstance(midi_port, str):
        errors.append("'midi_output_port' must be a string")
        midi_port = ""
    if enabled and not dry_run and not midi_port.strip():
        errors.append(
            "'midi_output_port' must be a non-empty string when enabled=true and dry_run=false"
        )

    # scenes
    scenes_raw = data.get("scenes")
    if not isinstance(scenes_raw, dict) or not scenes_raw:
        errors.append("'scenes' must be a non-empty object")
        scenes_raw = {}
    else:
        for scene_name, scene_data in scenes_raw.items():
            errors.extend(_validate_scene(scene_name, scene_data))

    scene_keys = set(scenes_raw.keys())

    # lifecycle scene references
    for field_name in _LIFECYCLE_SCENE_FIELDS:
        ref = data.get(field_name)
        if not isinstance(ref, str) or not ref:
            errors.append(f"'{field_name}' must be a non-empty string")
        elif ref not in scene_keys:
            errors.append(
                f"'{field_name}' references unknown scene '{ref}'"
            )

    # personalities (optional)
    personalities_raw = data.get("personalities")
    if personalities_raw is not None:
        if not isinstance(personalities_raw, dict):
            errors.append("'personalities' must be an object")
        else:
            for p_name, p_data in personalities_raw.items():
                errors.extend(_validate_personality(p_name, p_data, scene_keys))

            default_p = data.get("default_personality")
            if not isinstance(default_p, str) or not default_p:
                errors.append(
                    "'default_personality' must be a non-empty string when 'personalities' is present"
                )
            elif default_p not in personalities_raw:
                errors.append(
                    f"'default_personality' references unknown personality '{default_p}'"
                )

    return errors


def _validate_scene(name: str, data: Any) -> list[str]:
    errors: list[str] = []
    prefix = f"scene '{name}'"

    if not isinstance(data, dict):
        return [f"{prefix}: must be an object"]

    scene_type = data.get("scene_type", "static")
    if scene_type not in _VALID_SCENE_TYPES:
        errors.append(f"{prefix}: 'scene_type' must be one of {sorted(_VALID_SCENE_TYPES)}, got {scene_type!r}")

    safety_class = data.get("safety_class", "safe")
    if safety_class not in _VALID_SAFETY_CLASSES:
        errors.append(
            f"{prefix}: 'safety_class' must be one of {sorted(_VALID_SAFETY_CLASSES)}, got {safety_class!r}"
        )

    midi_raw = data.get("midi")
    if not isinstance(midi_raw, dict):
        errors.append(f"{prefix}: 'midi' must be an object")
    else:
        errors.extend(_validate_midi(prefix, midi_raw))

    return errors


def _validate_midi(prefix: str, midi: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    kind = midi.get("kind", "note_pulse")
    if kind not in _VALID_KINDS:
        errors.append(f"{prefix}: midi 'kind' must be one of {sorted(_VALID_KINDS)}, got {kind!r}")

    channel = midi.get("channel", 1)
    if not isinstance(channel, int) or not (1 <= channel <= 16):
        errors.append(f"{prefix}: midi 'channel' must be an integer 1–16, got {channel!r}")

    note = midi.get("note", 0)
    if not isinstance(note, int) or not (0 <= note <= 127):
        errors.append(f"{prefix}: midi 'note' must be an integer 0–127, got {note!r}")

    velocity = midi.get("velocity", 127)
    if not isinstance(velocity, int) or not (0 <= velocity <= 127):
        errors.append(f"{prefix}: midi 'velocity' must be an integer 0–127, got {velocity!r}")

    cc = midi.get("cc", 0)
    if not isinstance(cc, int) or not (0 <= cc <= 127):
        errors.append(f"{prefix}: midi 'cc' must be an integer 0–127, got {cc!r}")

    value = midi.get("value", 0)
    if not isinstance(value, int) or not (0 <= value <= 127):
        errors.append(f"{prefix}: midi 'value' must be an integer 0–127, got {value!r}")

    if kind == "note_pulse":
        duration_ms = midi.get("duration_ms", 80)
        if not isinstance(duration_ms, int) or not (_DURATION_MIN <= duration_ms <= _DURATION_MAX):
            errors.append(
                f"{prefix}: midi 'duration_ms' must be an integer {_DURATION_MIN}–{_DURATION_MAX}, "
                f"got {duration_ms!r}"
            )

    return errors


def _validate_personality(
    name: str,
    data: Any,
    scene_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    prefix = f"personality '{name}'"

    if not isinstance(data, dict):
        return [f"{prefix}: must be an object"]

    for role in _PERSONALITY_ROLE_FIELDS:
        ref = data.get(role)
        if not isinstance(ref, str) or not ref:
            errors.append(f"{prefix}: '{role}' must be a non-empty string")
        elif ref not in scene_keys:
            errors.append(f"{prefix}: '{role}' references unknown scene '{ref}'")

    phrase_interval_beats = data.get("phrase_interval_beats", 32)
    if (
        not isinstance(phrase_interval_beats, int)
        or isinstance(phrase_interval_beats, bool)
        or phrase_interval_beats < 1
    ):
        errors.append(
            f"{prefix}: 'phrase_interval_beats' must be a positive integer"
        )

    minimum_scene_hold_beats = data.get("minimum_scene_hold_beats", 0)
    if (
        not isinstance(minimum_scene_hold_beats, int)
        or isinstance(minimum_scene_hold_beats, bool)
        or minimum_scene_hold_beats < 0
    ):
        errors.append(
            f"{prefix}: 'minimum_scene_hold_beats' must be a non-negative integer"
        )

    normal_changes_only_on_phrase_boundary = data.get(
        "normal_changes_only_on_phrase_boundary", False
    )
    if not isinstance(normal_changes_only_on_phrase_boundary, bool):
        errors.append(
            f"{prefix}: 'normal_changes_only_on_phrase_boundary' must be a boolean"
        )

    buildup_approach_beats = data.get("buildup_approach_beats", 8)
    if (
        not isinstance(buildup_approach_beats, int)
        or isinstance(buildup_approach_beats, bool)
        or buildup_approach_beats < 0
    ):
        errors.append(
            f"{prefix}: 'buildup_approach_beats' must be a non-negative integer"
        )

    buildup_hold_beats = data.get("buildup_hold_beats", 8)
    if (
        not isinstance(buildup_hold_beats, int)
        or isinstance(buildup_hold_beats, bool)
        or buildup_hold_beats < 0
    ):
        errors.append(
            f"{prefix}: 'buildup_hold_beats' must be a non-negative integer"
        )

    pre_drop_lookahead_beats = data.get("pre_drop_lookahead_beats", 4)
    if (
        not isinstance(pre_drop_lookahead_beats, int)
        or isinstance(pre_drop_lookahead_beats, bool)
        or pre_drop_lookahead_beats < 0
    ):
        errors.append(
            f"{prefix}: 'pre_drop_lookahead_beats' must be a non-negative integer"
        )

    return errors


def _build_config(data: dict[str, Any]) -> LaserConfig:
    """Build a LaserConfig from already-validated data. Does not re-validate."""
    scenes: dict[str, LaserScene] = {}
    for scene_name, scene_data in data.get("scenes", {}).items():
        scenes[scene_name] = _build_scene(scene_name, scene_data)

    personalities: dict[str, LaserPersonality] = {}
    for p_name, p_data in data.get("personalities", {}).items():
        personalities[p_name] = _build_personality(p_name, p_data)

    return LaserConfig(
        enabled=bool(data.get("enabled", False)),
        dry_run=bool(data.get("dry_run", True)),
        midi_output_port=str(data.get("midi_output_port", "")),
        scenes=scenes,
        personalities=personalities,
        default_personality=str(data.get("default_personality", "")),
        startup_scene=str(data.get("startup_scene", "")),
        stop_scene=str(data.get("stop_scene", "")),
        stale_scene=str(data.get("stale_scene", "")),
        emergency_scene=str(data.get("emergency_scene", "")),
        fallback_scene=str(data.get("fallback_scene", "")),
    )


def _build_scene(name: str, data: dict[str, Any]) -> LaserScene:
    midi_raw = data.get("midi", {})
    midi = LaserMidiMessage(
        kind=str(midi_raw.get("kind", "note_pulse")),
        channel=int(midi_raw.get("channel", 1)),
        note=int(midi_raw.get("note", 0)),
        velocity=int(midi_raw.get("velocity", 127)),
        cc=int(midi_raw.get("cc", 0)),
        value=int(midi_raw.get("value", 0)),
        duration_ms=int(midi_raw.get("duration_ms", 80)),
    )
    return LaserScene(
        name=name,
        scene_type=str(data.get("scene_type", "static")),
        safety_class=str(data.get("safety_class", "safe")),
        midi=midi,
        fallback_scene=str(data.get("fallback_scene", "safe_static")),
        cooldown_beats=float(data.get("cooldown_beats", 0.0)),
        immediate=bool(data.get("immediate", False)),
    )


def _build_personality(name: str, data: dict[str, Any]) -> LaserPersonality:
    return LaserPersonality(
        name=name,
        safe_scene=str(data.get("safe_scene", "")),
        default_scene=str(data.get("default_scene", "")),
        phrase_scene=str(data.get("phrase_scene", "")),
        buildup_scene=str(data.get("buildup_scene", "")),
        pre_drop_scene=str(data.get("pre_drop_scene", "")),
        drop_scene=str(data.get("drop_scene", "")),
        post_drop_scene=str(data.get("post_drop_scene", "")),
        breakdown_scene=str(data.get("breakdown_scene", "")),
        transition_scene=str(data.get("transition_scene", "")),
        allow_high_impact=bool(data.get("allow_high_impact", False)),
        phrase_interval_beats=int(data.get("phrase_interval_beats", 32)),
        minimum_scene_hold_beats=int(data.get("minimum_scene_hold_beats", 0)),
        normal_changes_only_on_phrase_boundary=bool(
            data.get("normal_changes_only_on_phrase_boundary", False)
        ),
        buildup_approach_beats=int(data.get("buildup_approach_beats", 8)),
        buildup_hold_beats=int(data.get("buildup_hold_beats", 8)),
        pre_drop_lookahead_beats=int(data.get("pre_drop_lookahead_beats", 4)),
    )
