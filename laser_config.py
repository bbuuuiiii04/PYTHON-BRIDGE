"""Laser Director JSON config loader and validator.

Public API
----------
load_laser_director_config(path=None) -> LaserConfigResult
load_laser_director_config_from_dict(data) -> LaserConfigResult

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
from .personality_resolver import canonicalize_text

log = logging.getLogger("laser_config")

_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "laser_director.json"

_VALID_KINDS = frozenset({"note_pulse", "note_on", "note_off", "cc"})
_VALID_BEHAVIORS = frozenset({"pulse", "hold_ms", "hold_beats", "note_on", "note_off"})
_VALID_SAFETY_CLASSES = frozenset({
    "safe", "movement_low", "movement_medium", "movement_high",
    "high_impact", "strobe", "blackout",
})
_VALID_SCENE_TYPES = frozenset({"static", "autoloop", "utility"})
_VALID_SMART_DROP_MODES = frozenset({"blackout_mask", "legacy_rearm"})

_DURATION_MIN = 10
_DURATION_MAX = 250
_HOLD_MS_MIN = 10
_HOLD_MS_MAX = 30000
_HOLD_BEATS_MIN = 0.25
_HOLD_BEATS_MAX = 128.0

_PERSONALITY_REQUIRED_ROLE_FIELDS = (
    "safe_scene",
    "default_scene",
    "phrase_scene",
    "buildup_scene",
    "drop_scene",
    "breakdown_scene",
    "transition_scene",
)
_PERSONALITY_BANK_FIELDS = (
    "phrase_bank",
    "buildup_bank",
    "drop_bank",
    "post_drop_bank",
    "breakdown_bank",
)
_PERSONALITY_DEFAULTED_FIELDS = {
    "aliases": (),
    "bpm_band_min": 0.0,
    "bpm_band_max": 0.0,
    "pre_drop_blackout_beats": 4,
    "post_drop_hold_beats": 8,
    "breakdown_default_restore_beats": 64,
}
_DEPRECATED_PERSONALITY_TIMING_FIELDS = (
    "buildup_approach_beats",
    "buildup_hold_beats",
    "pre_drop_lookahead_beats",
    "buildup_max_drop_distance_beats",
    "pre_drop_scene",
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
    smart_drop_mode: str
    midi_output_port: str
    scenes: dict[str, LaserScene]
    personalities: dict[str, LaserPersonality]
    default_personality: str
    startup_scene: str
    stop_scene: str
    stale_scene: str
    emergency_scene: str
    fallback_scene: str
    bpm_priority: tuple[str, ...] = field(default_factory=tuple)
    manual_blackout_on: Optional[LaserMidiMessage] = None
    manual_blackout_off: Optional[LaserMidiMessage] = None


@dataclass(frozen=True)
class LaserConfigResult:
    """Result of a config load attempt.

    reason values:
      "ok"               — config loaded and validated successfully.
      "not_configured"   — config file absent; Laser Director is disabled.
      "invalid_config"   — config present but failed validation.
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

    return load_laser_director_config_from_dict(data)


def load_laser_director_config_from_dict(data: dict[str, Any]) -> LaserConfigResult:
    """Validate and build a Laser Director config from an already-parsed dict.

    Never raises. Returns LaserConfigResult in all cases.
    """
    if not isinstance(data, dict):
        return _invalid("config root must be a JSON object")

    _warn_deprecated_personality_timing_fields(data)

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

    _log_missing_personality_field_defaults(data)
    config = _build_config(data)
    _log_bpm_overlaps(config)
    if (
        config.smart_drop_mode == "blackout_mask"
        and config.manual_blackout_on is None
        and config.manual_blackout_off is None
    ):
        log.warning(
            "smart_drop_mode='blackout_mask' but manual_commands.blackout_on/off are not configured; "
            "Smart Drop transitions will not be masked."
        )
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


def _warn_deprecated_personality_timing_fields(data: dict[str, Any]) -> None:
    personalities = data.get("personalities")
    if not isinstance(personalities, dict):
        return
    present: set[str] = set()
    for personality_data in personalities.values():
        if not isinstance(personality_data, dict):
            continue
        for field_name in _DEPRECATED_PERSONALITY_TIMING_FIELDS:
            if field_name in personality_data:
                present.add(field_name)
    if not present:
        return
    ordered = [
        field_name
        for field_name in _DEPRECATED_PERSONALITY_TIMING_FIELDS
        if field_name in present
    ]
    log.warning(
        "[LASER-CONFIG] deprecated keys ignored: %s - remove from config; "
        "will be hard-fail in a future release.",
        ", ".join(ordered),
    )


def _log_missing_personality_field_defaults(data: dict[str, Any]) -> None:
    personalities = data.get("personalities")
    if not isinstance(personalities, dict):
        return
    for name, personality_data in personalities.items():
        if not isinstance(personality_data, dict):
            continue
        for field_name, default in _PERSONALITY_DEFAULTED_FIELDS.items():
            if field_name in personality_data:
                continue
            log.info(
                "[CONFIG] personality %r missing field %r - using default %r",
                str(name),
                field_name,
                default,
            )


def _log_bpm_overlaps(config: LaserConfig) -> None:
    bands: list[tuple[str, float, float]] = []
    for name, personality in config.personalities.items():
        bpm_min = float(personality.bpm_band_min)
        bpm_max = float(personality.bpm_band_max)
        if bpm_min == 0.0 and bpm_max == 0.0:
            continue
        bands.append((name, bpm_min, bpm_max))

    for idx, (left_name, left_min, left_max) in enumerate(bands):
        for right_name, right_min, right_max in bands[idx + 1:]:
            overlap_min = max(left_min, right_min)
            overlap_max = min(left_max, right_max)
            if overlap_min < overlap_max:
                log.info(
                    "[CONFIG] bpm-overlap personalities=%s[%g-%g],%s[%g-%g] zone=%g-%g",
                    left_name,
                    left_min,
                    left_max,
                    right_name,
                    right_min,
                    right_max,
                    overlap_min,
                    overlap_max,
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

    smart_drop_mode = data.get("smart_drop_mode", "blackout_mask")
    if not isinstance(smart_drop_mode, str):
        errors.append("'smart_drop_mode' must be a string")
        smart_drop_mode = "blackout_mask"
    elif smart_drop_mode not in _VALID_SMART_DROP_MODES:
        errors.append(
            f"'smart_drop_mode' must be one of {sorted(_VALID_SMART_DROP_MODES)}, got {smart_drop_mode!r}"
        )
        smart_drop_mode = "blackout_mask"

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
        scene_keys = set(str(name) for name in scenes_raw)
        for scene_name, scene_data in scenes_raw.items():
            errors.extend(_validate_scene(scene_name, scene_data, scene_keys))

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
            errors.extend(_validate_personality_aliases(personalities_raw))
            errors.extend(_validate_bpm_priority(data, personalities_raw))

            default_p = data.get("default_personality")
            if not isinstance(default_p, str) or not default_p:
                errors.append(
                    "'default_personality' must be a non-empty string when 'personalities' is present"
                )
            elif default_p not in personalities_raw:
                errors.append(
                    f"'default_personality' references unknown personality '{default_p}'"
                )

    errors.extend(_validate_manual_commands(data, smart_drop_mode=smart_drop_mode))
    return errors


def canon_alias(value: str) -> str:
    return canonicalize_text(value)


def _validate_personality_aliases(personalities_raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    for p_name, p_data in personalities_raw.items():
        if not isinstance(p_data, dict):
            continue
        aliases = p_data.get("aliases", [])
        if aliases is None:
            aliases = []
        if not isinstance(aliases, list):
            errors.append(f"personality '{p_name}': 'aliases' must be a list of strings")
            continue
        for index, alias in enumerate(aliases):
            if not isinstance(alias, str) or not alias.strip():
                errors.append(
                    f"personality '{p_name}': 'aliases[{index}]' must be a non-empty string"
                )
                continue
            canonical = canon_alias(alias)
            owner = seen.get(canonical)
            if owner is not None and owner != p_name:
                errors.append(
                    f"personality '{p_name}': alias {alias!r} duplicates personality '{owner}'"
                )
            else:
                seen[canonical] = str(p_name)
    return errors


def _validate_bpm_priority(
    data: dict[str, Any],
    personalities_raw: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    bpm_priority = data.get("bpm_priority", [])
    if bpm_priority is None:
        bpm_priority = []
    if not isinstance(bpm_priority, list):
        return ["'bpm_priority' must be a list of personality names"]
    for index, name in enumerate(bpm_priority):
        if not isinstance(name, str) or not name:
            errors.append(f"'bpm_priority[{index}]' must be a non-empty string")
            continue
        if name not in personalities_raw:
            errors.append(f"'bpm_priority[{index}]' references unknown personality '{name}'")
    return errors


def _validate_manual_commands(data: dict[str, Any], *, smart_drop_mode: str) -> list[str]:
    errors: list[str] = []
    manual_commands = data.get("manual_commands")

    def _resolved_behavior(raw: dict[str, Any]) -> str:
        kind = str(raw.get("kind", "note_pulse"))
        return _infer_behavior(kind, raw.get("behavior"))

    if manual_commands is None:
        if "manual_blackout_on" in data or "manual_blackout_off" in data:
            manual_commands = {
                "blackout_on": data.get("manual_blackout_on"),
                "blackout_off": data.get("manual_blackout_off"),
            }
        else:
            return errors

    if not isinstance(manual_commands, dict):
        errors.append("'manual_commands' must be an object")
        return errors

    blackout_on = manual_commands.get("blackout_on")
    if blackout_on is not None:
        if not isinstance(blackout_on, dict):
            errors.append("'manual_commands.blackout_on' must be an object")
        else:
            errors.extend(_validate_midi("manual_commands.blackout_on", blackout_on))

    blackout_off = manual_commands.get("blackout_off")
    if blackout_off is not None:
        if not isinstance(blackout_off, dict):
            errors.append("'manual_commands.blackout_off' must be an object")
        else:
            errors.extend(_validate_midi("manual_commands.blackout_off", blackout_off))

    has_blackout_on = isinstance(blackout_on, dict)
    has_blackout_off = isinstance(blackout_off, dict)

    if has_blackout_off and not has_blackout_on:
        errors.append(
            "'manual_commands.blackout_on' must be configured if 'manual_commands.blackout_off' is configured"
        )

    if smart_drop_mode == "blackout_mask" and has_blackout_on:
        assert isinstance(blackout_on, dict)
        blackout_on_behavior = _resolved_behavior(blackout_on)
        if blackout_on_behavior not in ("note_on", "pulse"):
            errors.append(
                "'manual_commands.blackout_on' must resolve to behavior='note_on' or 'pulse'"
            )

        if blackout_on_behavior == "note_on":
            if not has_blackout_off:
                errors.append(
                    "'manual_commands.blackout_off' must be configured when 'blackout_on' is a hold (note_on)"
                )
            elif _resolved_behavior(blackout_off) != "note_off":
                errors.append(
                    "'manual_commands.blackout_off' must resolve to behavior='note_off' to clear the note_on hold"
                )

    return errors


def _validate_scene(name: str, data: Any, scene_keys: set[str]) -> list[str]:
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

    fallback_scene = data.get("fallback_scene", "")
    if fallback_scene and fallback_scene not in scene_keys:
        errors.append(f"{prefix}: 'fallback_scene' references unknown scene '{fallback_scene}'")

    cooldown_beats = data.get("cooldown_beats", 0.0)
    if isinstance(cooldown_beats, bool) or not isinstance(cooldown_beats, (int, float)):
        errors.append(f"{prefix}: 'cooldown_beats' must be a number >= 0")
    elif float(cooldown_beats) < 0:
        errors.append(f"{prefix}: 'cooldown_beats' must be >= 0")

    return errors


def _validate_midi(prefix: str, midi: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    kind = midi.get("kind", "note_pulse")
    if kind not in _VALID_KINDS:
        errors.append(f"{prefix}: midi 'kind' must be one of {sorted(_VALID_KINDS)}, got {kind!r}")

    behavior = midi.get("behavior")
    if behavior is not None and behavior not in _VALID_BEHAVIORS:
        errors.append(
            f"{prefix}: midi 'behavior' must be one of {sorted(_VALID_BEHAVIORS)}, got {behavior!r}"
        )

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

    if behavior == "pulse":
        duration_ms = midi.get("duration_ms", 80)
        if not isinstance(duration_ms, int) or not (_DURATION_MIN <= duration_ms <= _DURATION_MAX):
            errors.append(
                f"{prefix}: midi 'duration_ms' must be an integer {_DURATION_MIN}–{_DURATION_MAX} "
                f"for behavior='pulse', got {duration_ms!r}"
            )
    elif behavior == "hold_ms":
        hold_ms = midi.get("hold_ms")
        if (
            not isinstance(hold_ms, int)
            or isinstance(hold_ms, bool)
            or not (_HOLD_MS_MIN <= hold_ms <= _HOLD_MS_MAX)
        ):
            errors.append(
                f"{prefix}: midi 'hold_ms' must be an integer {_HOLD_MS_MIN}–{_HOLD_MS_MAX} "
                f"for behavior='hold_ms', got {hold_ms!r}"
            )
    elif behavior == "hold_beats":
        hold_beats = midi.get("hold_beats")
        if (
            not isinstance(hold_beats, (int, float))
            or isinstance(hold_beats, bool)
            or not (_HOLD_BEATS_MIN <= float(hold_beats) <= _HOLD_BEATS_MAX)
        ):
            errors.append(
                f"{prefix}: midi 'hold_beats' must be a number {_HOLD_BEATS_MIN}–{_HOLD_BEATS_MAX} "
                f"for behavior='hold_beats', got {hold_beats!r}"
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

    for role in _PERSONALITY_REQUIRED_ROLE_FIELDS:
        ref = data.get(role)
        if not isinstance(ref, str) or not ref:
            errors.append(f"{prefix}: '{role}' must be a non-empty string")
        elif ref not in scene_keys:
            errors.append(f"{prefix}: '{role}' references unknown scene '{ref}'")

    # post_drop_scene: required only in emphasized_drop (it holds a separate
    # post-drop look). In drop_mode the drop look itself is held, so an empty
    # post_drop_scene is valid. When present it must reference a known scene.
    post_drop_ref = data.get("post_drop_scene", "")
    if not isinstance(post_drop_ref, str):
        errors.append(f"{prefix}: 'post_drop_scene' must be a string")
    elif _canon_drop_style(data.get("drop_style")) == "emphasized_drop" and not post_drop_ref:
        errors.append(
            f"{prefix}: 'post_drop_scene' must be a non-empty string for emphasized_drop"
        )
    elif post_drop_ref and post_drop_ref not in scene_keys:
        errors.append(
            f"{prefix}: 'post_drop_scene' references unknown scene '{post_drop_ref}'"
        )

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

    buildup_lookahead_beats = data.get("buildup_lookahead_beats", 32)
    if (
        not isinstance(buildup_lookahead_beats, int)
        or isinstance(buildup_lookahead_beats, bool)
        or buildup_lookahead_beats < 1
    ):
        errors.append(
            f"{prefix}: 'buildup_lookahead_beats' must be a positive integer"
        )

    for field_name in (
        "pre_drop_blackout_beats",
        "post_drop_hold_beats",
        "breakdown_default_restore_beats",
    ):
        value = data.get(field_name, _PERSONALITY_DEFAULTED_FIELDS[field_name])
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            errors.append(f"{prefix}: '{field_name}' must be a non-negative integer")

    drop_lifecycle_mirror = data.get("drop_lifecycle_mirror", True)
    if not isinstance(drop_lifecycle_mirror, bool):
        errors.append(f"{prefix}: 'drop_lifecycle_mirror' must be a boolean")

    drop_entry_only = data.get("drop_entry_only", False)
    if not isinstance(drop_entry_only, bool):
        errors.append(f"{prefix}: 'drop_entry_only' must be a boolean")

    max_drops_in_a_row = data.get("max_drops_in_a_row", 2)
    if (
        not isinstance(max_drops_in_a_row, int)
        or isinstance(max_drops_in_a_row, bool)
        or max_drops_in_a_row < 1
    ):
        errors.append(f"{prefix}: 'max_drops_in_a_row' must be a positive integer")

    for _knob in ("drop_impact_beats", "post_drop_cycle_beats"):
        _value = data.get(_knob, 32.0)
        if isinstance(_value, bool) or not isinstance(_value, (int, float)) or _value <= 0:
            errors.append(f"{prefix}: '{_knob}' must be a positive number")

    drop_arm_cooldown_beats = data.get("drop_arm_cooldown_beats", 0.0)
    if (
        isinstance(drop_arm_cooldown_beats, bool)
        or not isinstance(drop_arm_cooldown_beats, (int, float))
        or drop_arm_cooldown_beats < 0
    ):
        errors.append(f"{prefix}: 'drop_arm_cooldown_beats' must be a non-negative number")

    bpm_band_min = data.get("bpm_band_min", 0.0)
    bpm_band_max = data.get("bpm_band_max", 0.0)
    bpm_values_valid = True
    for field_name, value in (
        ("bpm_band_min", bpm_band_min),
        ("bpm_band_max", bpm_band_max),
    ):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or float(value) < 0.0
        ):
            errors.append(f"{prefix}: '{field_name}' must be a non-negative number")
            bpm_values_valid = False
    if bpm_values_valid:
        bpm_min = float(bpm_band_min)
        bpm_max = float(bpm_band_max)
        if not (bpm_min == 0.0 and bpm_max == 0.0) and bpm_min >= bpm_max:
            errors.append(
                f"{prefix}: 'bpm_band_min' must be less than 'bpm_band_max' "
                "unless both are 0.0"
            )

    for bank_field in _PERSONALITY_BANK_FIELDS:
        bank_raw = data.get(bank_field)
        if bank_raw is None:
            continue
        if not isinstance(bank_raw, list):
            errors.append(f"{prefix}: '{bank_field}' must be a list of scene names")
            continue
        for index, scene_name in enumerate(bank_raw):
            if not isinstance(scene_name, str) or not scene_name:
                errors.append(
                    f"{prefix}: '{bank_field}[{index}]' must be a non-empty string"
                )
                continue
            if scene_name not in scene_keys:
                errors.append(
                    f"{prefix}: '{bank_field}' references unknown scene '{scene_name}'"
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
    manual_blackout_on, manual_blackout_off = _build_manual_commands(data)

    return LaserConfig(
        enabled=bool(data.get("enabled", False)),
        dry_run=bool(data.get("dry_run", True)),
        smart_drop_mode=str(data.get("smart_drop_mode", "blackout_mask")),
        midi_output_port=str(data.get("midi_output_port", "")),
        scenes=scenes,
        personalities=personalities,
        default_personality=str(data.get("default_personality", "")),
        startup_scene=str(data.get("startup_scene", "")),
        stop_scene=str(data.get("stop_scene", "")),
        stale_scene=str(data.get("stale_scene", "")),
        emergency_scene=str(data.get("emergency_scene", "")),
        fallback_scene=str(data.get("fallback_scene", "")),
        bpm_priority=tuple(str(name) for name in data.get("bpm_priority", []) or ()),
        manual_blackout_on=manual_blackout_on,
        manual_blackout_off=manual_blackout_off,
    )


def _build_manual_commands(
    data: dict[str, Any],
) -> tuple[Optional[LaserMidiMessage], Optional[LaserMidiMessage]]:
    manual_commands = data.get("manual_commands")
    if isinstance(manual_commands, dict):
        return (
            _build_midi_message(manual_commands.get("blackout_on")),
            _build_midi_message(manual_commands.get("blackout_off")),
        )
    if "manual_blackout_on" in data or "manual_blackout_off" in data:
        return (
            _build_midi_message(data.get("manual_blackout_on")),
            _build_midi_message(data.get("manual_blackout_off")),
        )
    return (None, None)


def _build_midi_message(raw: Any) -> Optional[LaserMidiMessage]:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind", "note_pulse"))
    behavior = _infer_behavior(kind, raw.get("behavior"))
    return LaserMidiMessage(
        kind=kind,
        channel=int(raw.get("channel", 1)),
        note=int(raw.get("note", 0)),
        velocity=int(raw.get("velocity", 127)),
        cc=int(raw.get("cc", 0)),
        value=int(raw.get("value", 0)),
        duration_ms=int(raw.get("duration_ms", 80)),
        behavior=behavior,
        hold_ms=int(raw.get("hold_ms", 0)),
        hold_beats=float(raw.get("hold_beats", 0.0)),
    )


def _build_scene(name: str, data: dict[str, Any]) -> LaserScene:
    midi_raw = data.get("midi", {})
    kind = str(midi_raw.get("kind", "note_pulse"))
    behavior = _infer_behavior(kind, midi_raw.get("behavior"))
    midi = LaserMidiMessage(
        kind=kind,
        channel=int(midi_raw.get("channel", 1)),
        note=int(midi_raw.get("note", 0)),
        velocity=int(midi_raw.get("velocity", 127)),
        cc=int(midi_raw.get("cc", 0)),
        value=int(midi_raw.get("value", 0)),
        duration_ms=int(midi_raw.get("duration_ms", 80)),
        behavior=behavior,
        hold_ms=int(midi_raw.get("hold_ms", 0)),
        hold_beats=float(midi_raw.get("hold_beats", 0.0)),
    )
    return LaserScene(
        name=name,
        scene_type=str(data.get("scene_type", "static")),
        safety_class=str(data.get("safety_class", "safe")),
        midi=midi,
        fallback_scene=str(data.get("fallback_scene", "safe_static")),
        cooldown_beats=float(data.get("cooldown_beats", 0.0)),
        immediate=bool(data.get("immediate", False)),
        label=str(data.get("label", "")),
    )


def _build_personality(name: str, data: dict[str, Any]) -> LaserPersonality:
    return LaserPersonality(
        name=name,
        safe_scene=str(data.get("safe_scene", "")),
        default_scene=str(data.get("default_scene", "")),
        phrase_scene=str(data.get("phrase_scene", "")),
        buildup_scene=str(data.get("buildup_scene", "")),
        drop_scene=str(data.get("drop_scene", "")),
        post_drop_scene=str(data.get("post_drop_scene", "")),
        breakdown_scene=str(data.get("breakdown_scene", "")),
        transition_scene=str(data.get("transition_scene", "")),
        phrase_bank=tuple(str(scene) for scene in data.get("phrase_bank", []) or ()),
        buildup_bank=tuple(str(scene) for scene in data.get("buildup_bank", []) or ()),
        drop_bank=tuple(str(scene) for scene in data.get("drop_bank", []) or ()),
        post_drop_bank=tuple(
            str(scene) for scene in data.get("post_drop_bank", []) or ()
        ),
        breakdown_bank=tuple(
            str(scene) for scene in data.get("breakdown_bank", []) or ()
        ),
        aliases=tuple(canon_alias(str(alias)) for alias in data.get("aliases", []) or ()),
        bpm_band_min=float(data.get("bpm_band_min", 0.0)),
        bpm_band_max=float(data.get("bpm_band_max", 0.0)),
        allow_high_impact=bool(data.get("allow_high_impact", False)),
        phrase_interval_beats=int(data.get("phrase_interval_beats", 32)),
        minimum_scene_hold_beats=int(data.get("minimum_scene_hold_beats", 0)),
        normal_changes_only_on_phrase_boundary=bool(
            data.get("normal_changes_only_on_phrase_boundary", False)
        ),
        buildup_lookahead_beats=int(data.get("buildup_lookahead_beats", 32)),
        pre_drop_blackout_beats=int(data.get("pre_drop_blackout_beats", 4)),
        post_drop_hold_beats=int(data.get("post_drop_hold_beats", 8)),
        breakdown_default_restore_beats=int(
            data.get("breakdown_default_restore_beats", 64)
        ),
        drop_style=_canon_drop_style(data.get("drop_style")),
        drop_lifecycle_mirror=bool(data.get("drop_lifecycle_mirror", True)),
        max_drops_in_a_row=int(data.get("max_drops_in_a_row", 2)),
        drop_impact_beats=float(data.get("drop_impact_beats", 32.0)),
        post_drop_cycle_beats=float(data.get("post_drop_cycle_beats", 32.0)),
        drop_entry_only=bool(data.get("drop_entry_only", False)),
        drop_arm_cooldown_beats=float(data.get("drop_arm_cooldown_beats", 0.0)),
    )


def _canon_drop_style(value: object) -> str:
    """Normalize drop_style to a known value; default to drop_mode."""
    style = str(value or "").strip().lower()
    return "emphasized_drop" if style == "emphasized_drop" else "drop_mode"


def _infer_behavior(kind: str, behavior: object) -> str:
    if isinstance(behavior, str) and behavior:
        return behavior
    if kind == "note_pulse":
        return "pulse"
    if kind == "note_on":
        return "note_on"
    if kind == "note_off":
        return "note_off"
    return "pulse"
