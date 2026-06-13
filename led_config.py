"""LED Look Director config loader/validator (Phase 3 skeleton)."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable

from .led_models import (
    LEDAutomation,
    LEDBank,
    LEDConfig,
    LEDConfigResult,
    LEDLook,
    LEDRateLimits,
    LEDSafety,
    LEDTarget,
)

_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "led_look_director.json"

_SECRET_KEY_TOKENS = (
    "apikey",
    "token",
    "secret",
    "authorization",
    "authheader",
    "bearer",
    "password",
)
_PLACEHOLDER_TOKENS = (
    "operator_scene_name_or_id",
    "redacted",
    "operator-local",
    "operator_local",
    "placeholder",
    "example_",
    "fake_",
    "todo_",
    "unmapped",
    "replace_me",
    "changeme",
)
_LOOK_ACTIONS = frozenset({"scene", "music_mode", "diy_scene", "off", "unmapped"})
_MUSIC_MODE_NAMES = frozenset({"rhythm", "sprouting", "shiny"})
_BANK_ROLES = (
    "ambient",
    "groove",
    "buildup",
    "pre_drop",
    "drop",
    "post_drop",
    "breakdown",
    "utility",
)
_RATE_LIMIT_DEFAULTS = LEDRateLimits()
_AUTOMATION_DEFAULTS = LEDAutomation()
_MAX_AUTOMATION_OFFSET_S = 10.0


def load_led_look_director_config(path: str | None = None) -> LEDConfigResult:
    """Load and validate LED config from JSON file path."""
    resolved = _resolve_path(path)
    if resolved is None or not resolved.exists():
        return LEDConfigResult(available=False, reason="not_configured")
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
    return load_led_look_director_config_from_dict(data)


def load_led_look_director_config_from_dict(data: dict[str, Any]) -> LEDConfigResult:
    """Validate and build LED config from an already parsed dict."""
    if not isinstance(data, dict):
        return _invalid("config root must be a JSON object")

    errors: list[str] = []
    _collect_secret_key_errors(data, "$", errors)
    _validate(data, errors)
    if errors:
        return LEDConfigResult(
            available=False,
            reason="invalid_config",
            errors=tuple(errors),
        )
    return LEDConfigResult(available=True, reason="ok", config=_build_config(data))


def _resolve_path(explicit: str | None) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    env_path = os.environ.get("RBSS_LED_CONFIG")
    if env_path:
        return Path(env_path)
    return _DEFAULT_CONFIG_PATH


def _invalid(message: str) -> LEDConfigResult:
    return LEDConfigResult(
        available=False,
        reason="invalid_config",
        errors=(message,),
    )


def _collect_secret_key_errors(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if _is_secret_key(key_text):
                errors.append(
                    f"secret-like key '{key_text}' is not allowed at {path}"
                )
            _collect_secret_key_errors(nested, f"{path}.{key_text}", errors)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _collect_secret_key_errors(nested, f"{path}[{index}]", errors)


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(token in normalized for token in _SECRET_KEY_TOKENS)


def _validate(data: dict[str, Any], errors: list[str]) -> None:
    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int):
        errors.append("'schema_version' must be an integer")
    elif schema_version != 1:
        errors.append("'schema_version' must be 1")

    enabled = data.get("enabled")
    dry_run = data.get("dry_run")
    automation_enabled = data.get("automation_enabled")
    if not isinstance(enabled, bool):
        errors.append("'enabled' must be a boolean")
    if not isinstance(dry_run, bool):
        errors.append("'dry_run' must be a boolean")
    if not isinstance(automation_enabled, bool):
        errors.append("'automation_enabled' must be a boolean")

    targets_raw = data.get("targets")
    if not isinstance(targets_raw, dict) or not targets_raw:
        errors.append("'targets' must be a non-empty object")
        targets_raw = {}
    else:
        for name, target in targets_raw.items():
            _validate_target(name, target, errors)

    looks_raw = data.get("looks")
    if not isinstance(looks_raw, dict) or not looks_raw:
        errors.append("'looks' must be a non-empty object")
        looks_raw = {}
    else:
        for name, look in looks_raw.items():
            _validate_look(name, look, errors)

    look_names = set(looks_raw.keys())
    target_names = set(targets_raw.keys())
    for name, target in targets_raw.items():
        if not isinstance(target, dict):
            continue
        mirror_raw = target.get("mirror_targets", [])
        if mirror_raw is None:
            mirror_raw = []
        if not isinstance(mirror_raw, list):
            errors.append(f"target '{name}' field 'mirror_targets' must be a list")
            continue
        for index, mirror_ref in enumerate(mirror_raw):
            if not isinstance(mirror_ref, str) or not mirror_ref.strip():
                errors.append(
                    f"target '{name}' field 'mirror_targets[{index}]' must be a non-empty string"
                )
            elif mirror_ref == name:
                errors.append(f"target '{name}' cannot mirror to itself")
            elif mirror_ref not in target_names:
                errors.append(
                    f"target '{name}' mirror_targets references unknown target '{mirror_ref}'"
                )

    for name, look in looks_raw.items():
        if not isinstance(look, dict):
            continue
        target_ref = look.get("target")
        if isinstance(target_ref, str) and target_ref:
            if target_ref not in target_names:
                errors.append(
                    f"look '{name}' references unknown target '{target_ref}'"
                )
        fallback = look.get("fallback", "")
        if fallback:
            if not isinstance(fallback, str):
                errors.append(f"look '{name}' field 'fallback' must be a string")
            elif fallback not in look_names:
                errors.append(f"look '{name}' fallback references unknown look '{fallback}'")

    banks_raw = data.get("banks")
    if not isinstance(banks_raw, dict) or not banks_raw:
        errors.append("'banks' must be a non-empty object")
        banks_raw = {}
    else:
        for bank_name, bank in banks_raw.items():
            _validate_bank(bank_name, bank, look_names, errors)

    safe_default = data.get("safe_default")
    blackout = data.get("blackout")
    if not isinstance(safe_default, str) or not safe_default:
        errors.append("'safe_default' must be a non-empty string")
    elif safe_default not in look_names:
        errors.append(f"'safe_default' references unknown look '{safe_default}'")

    if not isinstance(blackout, str) or not blackout:
        errors.append("'blackout' must be a non-empty string")
    elif blackout not in look_names:
        errors.append(f"'blackout' references unknown look '{blackout}'")

    rate_limits = data.get("rate_limits")
    if not isinstance(rate_limits, dict):
        errors.append("'rate_limits' must be an object")
    else:
        _validate_rate_limits(rate_limits, errors)

    safety = data.get("safety")
    if not isinstance(safety, dict):
        errors.append("'safety' must be an object")
    else:
        _validate_safety(safety, errors)

    automation = data.get("automation", {})
    if automation is None:
        automation = {}
    if not isinstance(automation, dict):
        errors.append("'automation' must be an object")
    else:
        _validate_automation(automation, errors)

    if isinstance(dry_run, bool) and not dry_run:
        _validate_live_ready(data, errors)


def _validate_target(name: str, target: Any, errors: list[str]) -> None:
    prefix = f"target '{name}'"
    if not isinstance(target, dict):
        errors.append(f"{prefix} must be an object")
        return
    for field_name in ("label", "device_ref", "expected_model", "control_route"):
        value = target.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix} field '{field_name}' must be a non-empty string")
    capabilities = target.get("capabilities", [])
    if not isinstance(capabilities, list):
        errors.append(f"{prefix} field 'capabilities' must be a list of strings")
    else:
        for index, value in enumerate(capabilities):
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{prefix} field 'capabilities[{index}]' must be a non-empty string"
                )


def _validate_look(name: str, look: Any, errors: list[str]) -> None:
    prefix = f"look '{name}'"
    if not isinstance(look, dict):
        errors.append(f"{prefix} must be an object")
        return
    target = look.get("target")
    if not isinstance(target, str) or not target:
        errors.append(f"{prefix} field 'target' must be a non-empty string")

    action = look.get("action")
    if not isinstance(action, str) or action not in _LOOK_ACTIONS:
        errors.append(
            f"{prefix} field 'action' must be one of {sorted(_LOOK_ACTIONS)}"
        )
    elif action in {"scene", "music_mode", "diy_scene"}:
        scene_ref = look.get("scene_ref")
        if not isinstance(scene_ref, str) or not scene_ref.strip():
            errors.append(f"{prefix} requires non-empty 'scene_ref' for action='{action}'")
        elif action == "music_mode":
            _validate_music_mode_ref(prefix, scene_ref, errors)
        elif action == "diy_scene":
            _validate_diy_scene_ref(prefix, scene_ref, errors)

    safety_class = look.get("safety_class", "")
    if not isinstance(safety_class, str) or not safety_class.strip():
        errors.append(f"{prefix} field 'safety_class' must be a non-empty string")

    brightness = look.get("brightness", 100)
    if not isinstance(brightness, int) or isinstance(brightness, bool):
        errors.append(f"{prefix} field 'brightness' must be an integer")
    elif brightness < 0 or brightness > 100:
        errors.append(f"{prefix} field 'brightness' must be between 0 and 100")

    allow_strobe = look.get("allow_strobe", False)
    if not isinstance(allow_strobe, bool):
        errors.append(f"{prefix} field 'allow_strobe' must be a boolean")


def _validate_bank(
    bank_name: str,
    bank: Any,
    look_names: set[str],
    errors: list[str],
) -> None:
    prefix = f"bank '{bank_name}'"
    if not isinstance(bank, dict):
        errors.append(f"{prefix} must be an object")
        return
    for role in _BANK_ROLES:
        if role not in bank:
            errors.append(f"{prefix} missing role list '{role}'")
            continue
        values = bank.get(role)
        if not isinstance(values, list):
            errors.append(f"{prefix} role '{role}' must be a list")
            continue
        for index, look_name in enumerate(values):
            if not isinstance(look_name, str) or not look_name:
                errors.append(
                    f"{prefix} role '{role}[{index}]' must be a non-empty string"
                )
                continue
            if look_name not in look_names:
                errors.append(
                    f"{prefix} role '{role}' references unknown look '{look_name}'"
                )


def _validate_rate_limits(rate_limits: dict[str, Any], errors: list[str]) -> None:
    queue_maxsize = rate_limits.get("queue_maxsize", _RATE_LIMIT_DEFAULTS.queue_maxsize)
    if not isinstance(queue_maxsize, int) or isinstance(queue_maxsize, bool):
        errors.append("'rate_limits.queue_maxsize' must be an integer")
    elif queue_maxsize < 1 or queue_maxsize > 16:
        errors.append("'rate_limits.queue_maxsize' must be between 1 and 16")

    _validate_non_negative_number(
        "rate_limits.scene_retrigger_cooldown_s",
        rate_limits.get(
            "scene_retrigger_cooldown_s",
            _RATE_LIMIT_DEFAULTS.scene_retrigger_cooldown_s,
        ),
        errors,
    )
    _validate_non_negative_number(
        "rate_limits.high_impact_cooldown_s",
        rate_limits.get(
            "high_impact_cooldown_s",
            _RATE_LIMIT_DEFAULTS.high_impact_cooldown_s,
        ),
        errors,
    )
    _validate_positive_number(
        "rate_limits.request_timeout_s",
        rate_limits.get("request_timeout_s", _RATE_LIMIT_DEFAULTS.request_timeout_s),
        errors,
    )
    _validate_positive_number(
        "rate_limits.worker_shutdown_timeout_s",
        rate_limits.get(
            "worker_shutdown_timeout_s",
            _RATE_LIMIT_DEFAULTS.worker_shutdown_timeout_s,
        ),
        errors,
    )


def _validate_automation(automation: dict[str, Any], errors: list[str]) -> None:
    offset_s = automation.get("offset_s", _AUTOMATION_DEFAULTS.offset_s)
    _validate_non_negative_number("automation.offset_s", offset_s, errors)
    if isinstance(offset_s, (int, float)) and not isinstance(offset_s, bool):
        if float(offset_s) > _MAX_AUTOMATION_OFFSET_S:
            errors.append(
                f"'automation.offset_s' must be <= {_MAX_AUTOMATION_OFFSET_S:g}"
            )


def _validate_safety(safety: dict[str, Any], errors: list[str]) -> None:
    max_brightness = safety.get("max_brightness")
    if not isinstance(max_brightness, int) or isinstance(max_brightness, bool):
        errors.append("'safety.max_brightness' must be an integer")
    elif max_brightness < 1 or max_brightness > 100:
        errors.append("'safety.max_brightness' must be between 1 and 100")

    allow_strobe = safety.get("allow_strobe")
    if not isinstance(allow_strobe, bool):
        errors.append("'safety.allow_strobe' must be a boolean")

    max_strobe_duration_ms = safety.get("max_strobe_duration_ms")
    if not isinstance(max_strobe_duration_ms, int) or isinstance(max_strobe_duration_ms, bool):
        errors.append("'safety.max_strobe_duration_ms' must be an integer")
    elif max_strobe_duration_ms < 1 or max_strobe_duration_ms > 750:
        errors.append("'safety.max_strobe_duration_ms' must be between 1 and 750")

    _validate_non_negative_number(
        "safety.high_impact_cooldown_s",
        safety.get("high_impact_cooldown_s"),
        errors,
    )

    drop_flash_duration_ms = safety.get("drop_flash_duration_ms")
    if not isinstance(drop_flash_duration_ms, int) or isinstance(drop_flash_duration_ms, bool):
        errors.append("'safety.drop_flash_duration_ms' must be an integer")
    elif drop_flash_duration_ms < 1 or drop_flash_duration_ms > 750:
        errors.append("'safety.drop_flash_duration_ms' must be between 1 and 750")

    emergency = safety.get("emergency_blackout_always_available")
    if not isinstance(emergency, bool):
        errors.append("'safety.emergency_blackout_always_available' must be a boolean")
    elif emergency is not True:
        errors.append("'safety.emergency_blackout_always_available' must be true")

    scripted = safety.get("scripted_mode_automation")
    if not isinstance(scripted, bool):
        errors.append("'safety.scripted_mode_automation' must be a boolean")


def _validate_non_negative_number(field: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"'{field}' must be a number")
        return
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        errors.append(f"'{field}' must be a finite number >= 0")


def _validate_positive_number(field: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"'{field}' must be a number")
        return
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        errors.append(f"'{field}' must be a finite number > 0")


def _validate_live_ready(data: dict[str, Any], errors: list[str]) -> None:
    enabled = data.get("enabled")
    if enabled is not True:
        errors.append("'enabled' must be true when 'dry_run' is false")

    targets = data.get("targets", {})
    if isinstance(targets, dict):
        for name, target in targets.items():
            if not isinstance(target, dict):
                continue
            device_ref = str(target.get("device_ref", ""))
            if _is_placeholder_ref(device_ref):
                errors.append(
                    f"target '{name}' device_ref is placeholder-like and invalid for dry_run=false"
                )

    looks = data.get("looks", {})
    if isinstance(looks, dict):
        for name, look in looks.items():
            if not isinstance(look, dict):
                continue
            action = str(look.get("action", ""))
            if action == "unmapped":
                errors.append(
                    f"look '{name}' uses action='unmapped' and cannot be used when dry_run=false"
                )
            if action in {"scene", "music_mode", "diy_scene"}:
                scene_ref = str(look.get("scene_ref", ""))
                if _is_placeholder_ref(scene_ref):
                    errors.append(
                        f"look '{name}' has placeholder-like scene_ref and cannot be used when dry_run=false"
                    )

    for key_name in ("safe_default", "blackout"):
        look_name = data.get(key_name)
        if not isinstance(look_name, str):
            continue
        look = looks.get(look_name) if isinstance(looks, dict) else None
        if isinstance(look, dict) and str(look.get("action")) == "unmapped":
            errors.append(
                f"'{key_name}' references unmapped look '{look_name}' which is invalid for dry_run=false"
            )


def _is_placeholder_ref(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    return any(token in normalized for token in _PLACEHOLDER_TOKENS)


def _validate_music_mode_ref(prefix: str, scene_ref: str, errors: list[str]) -> None:
    parts = [part.strip() for part in scene_ref.split(":")]
    mode = parts[0].casefold() if parts else ""
    if mode not in _MUSIC_MODE_NAMES:
        errors.append(
            f"{prefix} music_mode scene_ref must start with one of {sorted(_MUSIC_MODE_NAMES)}"
        )
    if len(parts) >= 2:
        try:
            sensitivity = int(parts[1])
        except ValueError:
            errors.append(f"{prefix} music_mode sensitivity must be an integer")
        else:
            if sensitivity < 0 or sensitivity > 100:
                errors.append(f"{prefix} music_mode sensitivity must be between 0 and 100")
    if len(parts) >= 3 and parts[2].casefold() not in {"auto", "manual", "on", "off"}:
        errors.append(f"{prefix} music_mode color mode must be auto/on or manual/off")
    if len(parts) > 3:
        errors.append(f"{prefix} music_mode scene_ref has too many ':' sections")


def _validate_diy_scene_ref(prefix: str, scene_ref: str, errors: list[str]) -> None:
    try:
        value = int(scene_ref.strip())
    except ValueError:
        return
    if value <= 0:
        errors.append(f"{prefix} diy_scene scene_ref must be a positive Govee DIY scene value")


def _build_config(data: dict[str, Any]) -> LEDConfig:
    targets_raw = data["targets"]
    looks_raw = data["looks"]
    banks_raw = data["banks"]
    rate_limits_raw = data["rate_limits"]
    safety_raw = data["safety"]
    automation_raw = data.get("automation", {})
    if not isinstance(automation_raw, dict):
        automation_raw = {}

    targets: dict[str, LEDTarget] = {}
    for name, target in targets_raw.items():
        targets[name] = LEDTarget(
            name=name,
            label=str(target.get("label", "")),
            device_ref=str(target.get("device_ref", "")),
            expected_model=str(target.get("expected_model", "")),
            control_route=str(target.get("control_route", "")),
            capabilities=tuple(str(v) for v in target.get("capabilities", []) or ()),
            mirror_targets=tuple(str(v) for v in target.get("mirror_targets", []) or ()),
        )

    looks: dict[str, LEDLook] = {}
    for name, look in looks_raw.items():
        looks[name] = LEDLook(
            name=name,
            target=str(look.get("target", "")),
            action=str(look.get("action", "")),
            scene_ref=str(look.get("scene_ref", "")),
            fallback=str(look.get("fallback", "")),
            safety_class=str(look.get("safety_class", "safe")),
            brightness=int(look.get("brightness", 100)),
            allow_strobe=bool(look.get("allow_strobe", False)),
        )

    banks: dict[str, LEDBank] = {}
    for name, bank in banks_raw.items():
        banks[name] = LEDBank(
            ambient=_to_tuple(bank.get("ambient", [])),
            groove=_to_tuple(bank.get("groove", [])),
            buildup=_to_tuple(bank.get("buildup", [])),
            pre_drop=_to_tuple(bank.get("pre_drop", [])),
            drop=_to_tuple(bank.get("drop", [])),
            post_drop=_to_tuple(bank.get("post_drop", [])),
            breakdown=_to_tuple(bank.get("breakdown", [])),
            utility=_to_tuple(bank.get("utility", [])),
        )

    return LEDConfig(
        schema_version=int(data["schema_version"]),
        enabled=bool(data["enabled"]),
        dry_run=bool(data["dry_run"]),
        automation_enabled=bool(data["automation_enabled"]),
        targets=targets,
        looks=looks,
        banks=banks,
        safe_default=str(data["safe_default"]),
        blackout=str(data["blackout"]),
        automation=LEDAutomation(
            offset_s=float(
                automation_raw.get("offset_s", _AUTOMATION_DEFAULTS.offset_s)
            ),
        ),
        rate_limits=LEDRateLimits(
            queue_maxsize=int(
                rate_limits_raw.get("queue_maxsize", _RATE_LIMIT_DEFAULTS.queue_maxsize)
            ),
            scene_retrigger_cooldown_s=float(
                rate_limits_raw.get(
                    "scene_retrigger_cooldown_s",
                    _RATE_LIMIT_DEFAULTS.scene_retrigger_cooldown_s,
                )
            ),
            high_impact_cooldown_s=float(
                rate_limits_raw.get(
                    "high_impact_cooldown_s",
                    _RATE_LIMIT_DEFAULTS.high_impact_cooldown_s,
                )
            ),
            request_timeout_s=float(
                rate_limits_raw.get("request_timeout_s", _RATE_LIMIT_DEFAULTS.request_timeout_s)
            ),
            worker_shutdown_timeout_s=float(
                rate_limits_raw.get(
                    "worker_shutdown_timeout_s",
                    _RATE_LIMIT_DEFAULTS.worker_shutdown_timeout_s,
                )
            ),
        ),
        safety=LEDSafety(
            max_brightness=int(safety_raw["max_brightness"]),
            allow_strobe=bool(safety_raw["allow_strobe"]),
            max_strobe_duration_ms=int(safety_raw["max_strobe_duration_ms"]),
            high_impact_cooldown_s=float(safety_raw["high_impact_cooldown_s"]),
            drop_flash_duration_ms=int(safety_raw["drop_flash_duration_ms"]),
            emergency_blackout_always_available=bool(
                safety_raw["emergency_blackout_always_available"]
            ),
            scripted_mode_automation=bool(safety_raw["scripted_mode_automation"]),
        ),
    )


def _to_tuple(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(str(v) for v in values)
