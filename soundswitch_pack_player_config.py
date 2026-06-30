"""Validated startup-only configuration for the SoundSwitch pack player.

The loader is deliberately fail-closed and never raises.  It performs file I/O
only when called by startup/reload orchestration; it must never be called from
``StateManager._push_tick``.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional


log = logging.getLogger("soundswitch_pack_player_config")

_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "soundswitch_pack_player.json"
_CONFIG_ENV = "RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG"
_VALID_OUTPUT_BACKENDS = frozenset({"none", "midi", "pack"})
_FIXTURE_CHANNELS = frozenset(range(1, 20))
_ALLOWED_KEYS = frozenset({
    "_comment",
    "enabled",
    "dry_run",
    "output_backend",
    "pack_path",
    "fixture_map",
    "fixture_map_path",
    "midi_input_aliases",
    "enttec_port",
    "frame_stale_timeout_ms",
    "controller_hold_timeout_ms",
    "phase_offset_beats",
})


@dataclass(frozen=True, slots=True)
class SoundSwitchPackPlayerConfig:
    """Fully validated, immutable startup configuration."""

    enabled: bool
    dry_run: bool
    output_backend: str
    pack_path: str
    fixture_map: Mapping[int, int]
    fixture_map_path: str
    midi_input_aliases: Mapping[str, str]
    enttec_port: str
    frame_stale_timeout_ms: int
    controller_hold_timeout_ms: int
    phase_offset_beats: float = 0.0


@dataclass(frozen=True, slots=True)
class SoundSwitchPackPlayerConfigResult:
    """Never-raising result for a pack-player config load attempt."""

    available: bool
    reason: str
    config: Optional[SoundSwitchPackPlayerConfig] = None
    errors: tuple[str, ...] = field(default_factory=tuple)


def load_soundswitch_pack_player_config(
    path: Optional[str] = None,
) -> SoundSwitchPackPlayerConfigResult:
    """Load and validate config using explicit path, env, then repo default.

    A non-empty ``fixture_map_path`` is resolved relative to the config file's
    directory unless it is absolute.  It is authoritative over the inline map.
    This function catches all read, parse, and validation failures.
    """
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return SoundSwitchPackPlayerConfigResult(
                available=False,
                reason="not_configured",
            )
        data = _read_json_object(resolved, "config")
        return load_soundswitch_pack_player_config_from_dict(
            data,
            base_dir=resolved.parent,
        )
    except Exception as exc:  # The public loader's contract is never-raising.
        return _invalid(f"cannot load config: {type(exc).__name__}")


def load_soundswitch_pack_player_config_from_dict(
    data: object,
    *,
    base_dir: str | Path | None = None,
) -> SoundSwitchPackPlayerConfigResult:
    """Validate already-parsed config data without propagating exceptions."""
    try:
        if not isinstance(data, dict):
            return _invalid("config root must be a JSON object")
        unknown = sorted(set(data) - _ALLOWED_KEYS)
        if unknown:
            return _invalid(f"unknown config keys: {', '.join(unknown)}")

        errors: list[str] = []
        enabled = _bool_field(data, "enabled", False, errors)
        dry_run = _bool_field(data, "dry_run", True, errors)
        output_backend = data.get("output_backend", "none")
        if not isinstance(output_backend, str) or output_backend not in _VALID_OUTPUT_BACKENDS:
            errors.append("output_backend must be one of: midi, none, pack")

        pack_path = _string_field(data, "pack_path", "", errors)
        fixture_map_path = _string_field(data, "fixture_map_path", "", errors)
        enttec_port = _string_field(data, "enttec_port", "", errors)
        frame_stale_timeout_ms = _positive_int_field(
            data, "frame_stale_timeout_ms", 250, errors,
        )
        controller_hold_timeout_ms = _positive_int_field(
            data, "controller_hold_timeout_ms", 2000, errors,
        )
        phase_offset_beats = _float_field(data, "phase_offset_beats", 0.0, errors)
        midi_input_aliases = _aliases(data.get("midi_input_aliases", {}), errors)

        fixture_value: object = data.get(
            "fixture_map",
            {str(channel): channel for channel in range(1, 20)},
        )
        if fixture_map_path:
            fixture_file = Path(fixture_map_path).expanduser()
            if not fixture_file.is_absolute():
                fixture_file = Path(base_dir or _DEFAULT_CONFIG_PATH.parent) / fixture_file
            try:
                fixture_value = _read_json_object(fixture_file, "fixture_map")
            except Exception as exc:
                errors.append(
                    "fixture_map_path cannot be loaded: "
                    f"{type(exc).__name__}"
                )
                fixture_value = {}
        fixture_map = _fixture_map(fixture_value, errors)

        if errors:
            return SoundSwitchPackPlayerConfigResult(
                available=False,
                reason="invalid_config",
                errors=tuple(errors),
            )

        config = SoundSwitchPackPlayerConfig(
            enabled=enabled,
            dry_run=dry_run,
            output_backend=output_backend,
            pack_path=pack_path,
            fixture_map=MappingProxyType(dict(fixture_map)),
            fixture_map_path=fixture_map_path,
            midi_input_aliases=MappingProxyType(dict(midi_input_aliases)),
            enttec_port=enttec_port,
            frame_stale_timeout_ms=frame_stale_timeout_ms,
            controller_hold_timeout_ms=controller_hold_timeout_ms,
            phase_offset_beats=phase_offset_beats,
        )
        return SoundSwitchPackPlayerConfigResult(
            available=True,
            reason="ok",
            config=config,
        )
    except Exception as exc:  # Keep the from-dict seam just as fail-closed.
        return _invalid(f"cannot validate config: {type(exc).__name__}")


def _resolve_path(explicit: Optional[str]) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get(_CONFIG_ENV)
    if env:
        return Path(env).expanduser()
    return _DEFAULT_CONFIG_PATH


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"{label} root must be a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _bool_field(
    data: dict[str, Any], key: str, default: bool, errors: list[str],
) -> bool:
    value = data.get(key, default)
    if type(value) is not bool:
        errors.append(f"{key} must be boolean")
        return default
    return value


def _string_field(
    data: dict[str, Any], key: str, default: str, errors: list[str],
) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        errors.append(f"{key} must be a string")
        return default
    return value


def _positive_int_field(
    data: dict[str, Any], key: str, default: int, errors: list[str],
) -> int:
    value = data.get(key, default)
    if type(value) is not int or value <= 0:
        errors.append(f"{key} must be a positive integer")
        return default
    return value


def _float_field(
    data: dict[str, Any], key: str, default: float, errors: list[str],
) -> float:
    value = data.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        errors.append(f"{key} must be a finite number")
        return default
    return float(value)


def _aliases(value: object, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        errors.append("midi_input_aliases must be an object")
        return {}
    aliases: dict[str, str] = {}
    for device_name, port_alias in value.items():
        if not isinstance(device_name, str) or not device_name.strip():
            errors.append("midi_input_aliases keys must be non-empty strings")
            continue
        if not isinstance(port_alias, str) or not port_alias.strip():
            errors.append("midi_input_aliases values must be non-empty strings")
            continue
        aliases[device_name] = port_alias
    return aliases


def _fixture_map(value: object, errors: list[str]) -> dict[int, int]:
    if not isinstance(value, dict):
        errors.append("fixture_map must be an object")
        return {}
    parsed: dict[int, int] = {}
    for raw_channel, raw_address in value.items():
        channel: int | None = None
        if type(raw_channel) is int:
            channel = raw_channel
        elif isinstance(raw_channel, str):
            try:
                channel = int(raw_channel, 10)
            except ValueError:
                pass
        if channel is None or channel not in _FIXTURE_CHANNELS:
            errors.append(f"fixture_map key {raw_channel!r} must identify CH1..CH19")
            continue
        if channel in parsed:
            errors.append(f"fixture_map has duplicate channel after integer coercion: {channel}")
            continue
        if type(raw_address) is not int or not 1 <= raw_address <= 512:
            errors.append(
                f"fixture_map CH{channel} address must be an integer from 1 to 512"
            )
            continue
        parsed[channel] = raw_address
    missing = sorted(_FIXTURE_CHANNELS - set(parsed))
    extra = sorted(set(parsed) - _FIXTURE_CHANNELS)
    if missing:
        errors.append("fixture_map must define every channel CH1..CH19")
    if extra:  # Defensive; out-of-range entries are already rejected above.
        errors.append("fixture_map contains channels outside CH1..CH19")
    return parsed


def _invalid(message: str) -> SoundSwitchPackPlayerConfigResult:
    log.warning("[soundswitch_pack_player_config] %s", message)
    return SoundSwitchPackPlayerConfigResult(
        available=False,
        reason="invalid_config",
        errors=(message,),
    )


__all__ = [
    "SoundSwitchPackPlayerConfig",
    "SoundSwitchPackPlayerConfigResult",
    "load_soundswitch_pack_player_config",
    "load_soundswitch_pack_player_config_from_dict",
]
