"""LED Look Director config loader/validator (Phase 3 skeleton)."""
from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Optional

_log = logging.getLogger(__name__)

from .govee_frame_renderer import (
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
)
from .led_models import (
    ColorEngineConfig,
    LEDAutomation,
    LEDBank,
    LEDConfig,
    LEDConfigResult,
    LEDDropPair,
    LEDLook,
    LEDRateLimits,
    LEDRealtimeConfig,
    LEDSafety,
    LEDScriptedModePolicy,
    LEDTarget,
    Palette,
    _DEFAULT_SCALE_STOPS,
)
from .soundswitch_pack_loader import PackMidiBinding
from .drop_presentation import (
    DropPresentationConfig,
    load_drop_presentation_config as _load_drop_presentation_block,
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
_LOOK_ACTIONS = frozenset({"scene", "music_mode", "diy_scene", "off", "unmapped", "realtime"})
_LOOK_BACKENDS = frozenset({"cloud_diy", "realtime_razer"})
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
# Scripted source/default roles exclude utility; utility is an off destination.
_SCRIPTED_REMAP_ROLES = tuple(role for role in _BANK_ROLES if role != "utility")
_SCRIPTED_REMAP_DESTINATION_ROLES = _BANK_ROLES
_SCRIPTED_MODE_DEFAULT_ROLE = "breakdown"
_SCRIPTED_MODE_DEFAULT_ROLE_MAP = MappingProxyType({
    "ambient": "breakdown",
    "groove": "utility",
    "buildup": "buildup",
    "pre_drop": "buildup",
    "drop": "utility",
    "post_drop": "utility",
    "breakdown": "breakdown",
})
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


def load_drop_presentation_config(path: str | None = None) -> DropPresentationConfig:
    """Read the top-level `/drop_presentation` block from the same config file
    `load_led_look_director_config` uses (same path/env-override resolution),
    independent of the main LED config's validation pipeline — an unrelated
    `looks`/`banks` error there must never block hot-cue tags or the
    presentation policy. Any failure (missing file, bad JSON, wrong shape)
    degrades to defaults; never raises."""
    resolved = _resolve_path(path)
    if resolved is None:
        return DropPresentationConfig()
    return _load_drop_presentation_block(resolved)


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

    param_profiles_raw = data.get("realtime_param_profiles", {})
    if param_profiles_raw is None:
        param_profiles_raw = {}
    if not isinstance(param_profiles_raw, dict):
        errors.append("'realtime_param_profiles' must be an object")
        param_profiles_raw = {}

    looks_raw = data.get("looks")
    if not isinstance(looks_raw, dict) or not looks_raw:
        errors.append("'looks' must be a non-empty object")
        looks_raw = {}
    else:
        for name, look in looks_raw.items():
            _validate_look(name, look, param_profiles_raw, errors)

    look_names = set(looks_raw.keys())
    target_names = set(targets_raw.keys())
    _validate_drop_pairs(data, look_names, errors)
    _validate_post_drop_cycle_beats(data, errors)
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

    _validate_scripted_mode(data.get("scripted_mode"), errors)

    automation = data.get("automation", {})
    if automation is None:
        automation = {}
    if not isinstance(automation, dict):
        errors.append("'automation' must be an object")
    else:
        _validate_automation(automation, errors)

    _validate_realtime_cross_checks(data, errors)

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
    backend = target.get("backend", "cloud_diy")
    if not isinstance(backend, str) or backend not in _LOOK_BACKENDS:
        errors.append(f"{prefix} field 'backend' must be one of {sorted(_LOOK_BACKENDS)}")
    realtime = target.get("realtime", {})
    if realtime is None:
        realtime = {}
    if not isinstance(realtime, dict):
        errors.append(f"{prefix} field 'realtime' must be an object")
        return
    if not bool(realtime.get("enabled", False)):
        return
    protocol = realtime.get("protocol", "")
    if protocol and protocol != "razer_dreamview":
        errors.append(f"{prefix} realtime.protocol must be 'razer_dreamview'")
    ip = realtime.get("ip", "")
    if not isinstance(ip, str) or not _is_dotted_quad(ip):
        errors.append(f"{prefix} realtime.ip must be a dotted-quad IPv4 address")
    port = realtime.get("port", 4003)
    if not isinstance(port, int) or isinstance(port, bool) or port < 1 or port > 65535:
        errors.append(f"{prefix} realtime.port must be between 1 and 65535")
    segments = realtime.get("segments", 20)
    if not isinstance(segments, int) or isinstance(segments, bool) or segments < 1:
        errors.append(f"{prefix} realtime.segments must be an integer >= 1")
    fps = realtime.get("fps", 30)
    if not isinstance(fps, int) or isinstance(fps, bool) or fps < 1 or fps > 120:
        errors.append(f"{prefix} realtime.fps must be between 1 and 120")
    header_bytes = realtime.get("header_bytes", [])
    if not isinstance(header_bytes, list) or not header_bytes:
        errors.append(f"{prefix} realtime.header_bytes must be a non-empty list")
    else:
        if len(header_bytes) != 5:
            errors.append(f"{prefix} realtime.header_bytes must be exactly 5 bytes")
        for index, value in enumerate(header_bytes):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 255:
                errors.append(f"{prefix} realtime.header_bytes[{index}] must be 0..255")
    for field_name in ("activate_pt", "deactivate_pt"):
        value = realtime.get(field_name, "")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix} realtime.{field_name} must be a non-empty string")


def _validate_look(
    name: str,
    look: Any,
    param_profiles: dict[str, Any],
    errors: list[str],
) -> None:
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
    backend = look.get("backend", "cloud_diy")
    if not isinstance(backend, str) or backend not in _LOOK_BACKENDS:
        errors.append(f"{prefix} field 'backend' must be one of {sorted(_LOOK_BACKENDS)}")
    elif action in {"scene", "music_mode", "diy_scene"}:
        scene_ref = look.get("scene_ref")
        if not isinstance(scene_ref, str) or not scene_ref.strip():
            errors.append(f"{prefix} requires non-empty 'scene_ref' for action='{action}'")
        elif action == "music_mode":
            _validate_music_mode_ref(prefix, scene_ref, errors)
        elif action == "diy_scene":
            _validate_diy_scene_ref(prefix, scene_ref, errors)
    if action == "realtime":
        scene_ref = look.get("scene_ref")
        if backend != "realtime_razer":
            errors.append(f"{prefix} action='realtime' requires backend='realtime_razer'")
        if not isinstance(scene_ref, str) or not scene_ref.strip():
            errors.append(f"{prefix} requires non-empty 'scene_ref' for action='realtime'")
        elif scene_ref not in REALTIME_EFFECT_NAMES:
            errors.append(f"{prefix} scene_ref references unknown realtime effect '{scene_ref}'")
        profile_name = look.get("param_profile", "")
        profile_params: dict[str, Any] = {}
        if profile_name:
            if not isinstance(profile_name, str):
                errors.append(f"{prefix} field 'param_profile' must be a string")
            elif profile_name not in param_profiles:
                errors.append(f"{prefix} param_profile references unknown profile '{profile_name}'")
            elif not isinstance(param_profiles[profile_name], dict):
                errors.append(f"realtime_param_profiles.{profile_name} must be an object")
            else:
                profile_params = dict(param_profiles[profile_name])
        params = look.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            errors.append(f"{prefix} field 'params' must be an object")
        elif isinstance(scene_ref, str):
            params = {**profile_params, **params}
            allowed = REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, frozenset())
            for key in params:
                if key not in allowed:
                    errors.append(f"{prefix} params.{key} is not valid for effect '{scene_ref}'")
            _validate_realtime_params(prefix, scene_ref, params, errors)
    elif backend == "realtime_razer":
        errors.append(f"{prefix} backend='realtime_razer' requires action='realtime'")
    else:
        params = look.get("params", {})
        if params is not None and not isinstance(params, dict):
            errors.append(f"{prefix} field 'params' must be an object")

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


def _validate_drop_pairs(
    data: dict[str, Any],
    look_names: set[str],
    errors: list[str],
) -> None:
    pairs = data.get("drop_pairs", {})
    if pairs is None:
        return
    if not isinstance(pairs, dict):
        errors.append("'drop_pairs' must be an object")
        return
    for drop_name, raw_pair in pairs.items():
        if not isinstance(drop_name, str) or not drop_name:
            errors.append("'drop_pairs' keys must be non-empty look names")
            continue
        if drop_name not in look_names:
            errors.append(f"drop_pairs references unknown drop look '{drop_name}'")
        if not isinstance(raw_pair, dict):
            errors.append(f"drop_pairs.{drop_name} must be an object")
            continue
        post_drop = raw_pair.get("post_drop")
        if not isinstance(post_drop, str) or not post_drop:
            errors.append(f"drop_pairs.{drop_name}.post_drop must be a non-empty string")
        elif post_drop not in look_names:
            errors.append(
                f"drop_pairs.{drop_name}.post_drop references unknown look '{post_drop}'"
            )
        duration = raw_pair.get("duration_beats", 8.0)
        _validate_positive_number(
            f"drop_pairs.{drop_name}.duration_beats",
            duration,
            errors,
        )


def _validate_post_drop_cycle_beats(data: dict[str, Any], errors: list[str]) -> None:
    value = data.get("post_drop_cycle_beats", 32.0)
    _validate_positive_number("post_drop_cycle_beats", value, errors)


def _is_dotted_quad(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 and str(int(part)) == part for part in parts)
    except ValueError:
        return False


def _validate_realtime_params(
    prefix: str,
    effect_name: str,
    params: dict[str, Any],
    errors: list[str],
) -> None:
    for field_name in ("color", "bg", "color_a", "color_b"):
        if field_name in params and not _is_rgb(params[field_name]):
            errors.append(f"{prefix} params.{field_name} must be an RGB list")
    if "trail" in params:
        value = params["trail"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{prefix} params.trail must be an integer >= 0")
    for field_name in ("span_beats", "decay", "period_beats", "floor", "speed", "density", "duration_beats", "duty"):
        if field_name in params:
            _validate_non_negative_number(f"{prefix} params.{field_name}", params[field_name], errors)
    if "subdivision" in params and params["subdivision"] not in {1, 2, 4, 8}:
        errors.append(f"{prefix} params.subdivision must be one of [1, 2, 4, 8]")
    # Unit-interval params: the renderer clamps these to [0, 1], so reject
    # out-of-range config values up front rather than silently clamping.
    for field_name in ("floor", "duty", "density"):
        if field_name in params:
            value = params[field_name]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if value < 0 or value > 1:
                    errors.append(f"{prefix} params.{field_name} must be between 0 and 1")
    if "sync_mode" in params and params["sync_mode"] not in ("retrigger", "overlap", "continuous"):
        errors.append(f"{prefix} params.sync_mode must be one of [retrigger, overlap, continuous]")
    if "beat_division" in params:
        value = params["beat_division"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"{prefix} params.beat_division must be a number > 0")
    if "trail_beats" in params:
        _validate_non_negative_number(f"{prefix} params.trail_beats", params["trail_beats"], errors)
    for field_name in ("travel_beats", "width", "burst_beats", "breath_beats", "drift_beats", "loop_beats"):
        if field_name in params:
            value = params[field_name]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or value <= 0
            ):
                errors.append(f"{prefix} params.{field_name} must be a number > 0")
    for field_name in ("heads", "max_pulses"):
        if field_name in params:
            value = params[field_name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(f"{prefix} params.{field_name} must be an integer >= 1")
    if "spawn_on_wrap" in params and not isinstance(params["spawn_on_wrap"], bool):
        errors.append(f"{prefix} params.spawn_on_wrap must be a boolean")
    if "reverse" in params and not isinstance(params["reverse"], bool):
        errors.append(f"{prefix} params.reverse must be a boolean")


def _is_rgb(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 3:
        return False
    return all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in value)


def _validate_realtime_cross_checks(data: dict[str, Any], errors: list[str]) -> None:
    targets = data.get("targets", {})
    looks = data.get("looks", {})
    banks = data.get("banks", {})
    safety = data.get("safety", {})
    if not isinstance(targets, dict) or not isinstance(looks, dict):
        return

    def _backend_for(look_name: str) -> str:
        look = looks.get(look_name)
        if not isinstance(look, dict):
            return "cloud_diy"
        return str(look.get("backend", "cloud_diy") or "cloud_diy")

    for name, look in looks.items():
        if not isinstance(look, dict):
            continue
        backend = _backend_for(name)
        target_ref = look.get("target")
        target = targets.get(target_ref) if isinstance(target_ref, str) else None
        if backend == "realtime_razer":
            if not isinstance(target, dict):
                continue
            realtime = target.get("realtime", {})
            if not isinstance(realtime, dict) or not bool(realtime.get("enabled", False)):
                errors.append(
                    f"look '{name}' uses realtime backend but target '{target_ref}' has realtime.enabled=false"
                )
            if str(look.get("scene_ref", "")) in REALTIME_STROBE_EFFECTS:
                if not bool(look.get("allow_strobe", False)):
                    errors.append(f"look '{name}' realtime strobe effect requires allow_strobe=true")
                if isinstance(safety, dict) and not bool(safety.get("allow_strobe", False)):
                    errors.append(f"look '{name}' realtime strobe effect requires safety.allow_strobe=true")
        fallback = look.get("fallback", "")
        if isinstance(fallback, str) and fallback:
            if fallback in looks and _backend_for(fallback) != backend:
                errors.append(f"look '{name}' fallback must use the same backend")

    for key_name in ("safe_default", "blackout"):
        look_name = data.get(key_name)
        if isinstance(look_name, str) and look_name in looks and _backend_for(look_name) != "cloud_diy":
            errors.append(f"'{key_name}' must reference a cloud_diy look")

    if not isinstance(banks, dict):
        return
    for bank_name, bank in banks.items():
        if not isinstance(bank, dict):
            continue
        # WI-7 warn-only: detect mixed backends in any role bank.
        # This is a warning (not an error) so the current live JSON keeps loading.
        # Promote to a hard error in a later pass once banks are split per transport.
        import logging as _logging
        _wl = _logging.getLogger("led_config")
        for role in _BANK_ROLES:
            values = bank.get(role, [])
            if not isinstance(values, list):
                continue
            backends_in_role = set()
            for look_name in values:
                if isinstance(look_name, str) and look_name in looks:
                    backends_in_role.add(_backend_for(look_name))
            if len(backends_in_role) > 1:
                _wl.warning(
                    "[RGB] config-warn bank '%s' role '%s' mixes backends %s "
                    "(WI-7: split into per-transport banks to eliminate transport thrash)",
                    bank_name, role, sorted(backends_in_role),
                )
        # Hard error only for utility (existing rule)
        for role in ("utility",):
            values = bank.get(role, [])
            if not isinstance(values, list):
                continue
            for look_name in values:
                if isinstance(look_name, str) and look_name in looks and _backend_for(look_name) != "cloud_diy":
                    errors.append(f"bank '{bank_name}' role '{role}' must contain only cloud_diy looks")


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
    # WI-3 dwell tunable
    _validate_non_negative_number(
        "rate_limits.min_look_dwell_s",
        rate_limits.get("min_look_dwell_s", _RATE_LIMIT_DEFAULTS.min_look_dwell_s),
        errors,
    )
    # WI-5 transport cooldown tunable
    _validate_non_negative_number(
        "rate_limits.transport_switch_cooldown_s",
        rate_limits.get(
            "transport_switch_cooldown_s",
            _RATE_LIMIT_DEFAULTS.transport_switch_cooldown_s,
        ),
        errors,
    )
    # WI-6 reconcile tunables
    _validate_non_negative_number(
        "rate_limits.rt_reconcile_window_s",
        rate_limits.get("rt_reconcile_window_s", _RATE_LIMIT_DEFAULTS.rt_reconcile_window_s),
        errors,
    )
    _validate_non_negative_number(
        "rate_limits.rt_reconcile_interval_s",
        rate_limits.get(
            "rt_reconcile_interval_s", _RATE_LIMIT_DEFAULTS.rt_reconcile_interval_s
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
    cloud_offset_s = automation.get("cloud_offset_s", offset_s)
    _validate_non_negative_number("automation.cloud_offset_s", cloud_offset_s, errors)
    if isinstance(cloud_offset_s, (int, float)) and not isinstance(cloud_offset_s, bool):
        if float(cloud_offset_s) > _MAX_AUTOMATION_OFFSET_S:
            errors.append(
                f"'automation.cloud_offset_s' must be <= {_MAX_AUTOMATION_OFFSET_S:g}"
            )
    realtime_offset_s = automation.get(
        "realtime_offset_s",
        _AUTOMATION_DEFAULTS.realtime_offset_s,
    )
    _validate_non_negative_number(
        "automation.realtime_offset_s",
        realtime_offset_s,
        errors,
    )
    if isinstance(realtime_offset_s, (int, float)) and not isinstance(realtime_offset_s, bool):
        if float(realtime_offset_s) > _MAX_AUTOMATION_OFFSET_S:
            errors.append(
                f"'automation.realtime_offset_s' must be <= {_MAX_AUTOMATION_OFFSET_S:g}"
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


def _validate_scripted_mode(raw: Any, errors: list[str]) -> None:
    """Validate the optional scripted_mode block."""
    if raw is None:
        return
    if not isinstance(raw, dict):
        errors.append("'scripted_mode' must be an object")
        return

    default_role = raw.get("default_role", _SCRIPTED_MODE_DEFAULT_ROLE)
    if not isinstance(default_role, str) or default_role not in _SCRIPTED_REMAP_ROLES:
        errors.append(
            f"'scripted_mode.default_role' must be one of {list(_SCRIPTED_REMAP_ROLES)}"
        )

    role_map = raw.get("role_map", {})
    if not isinstance(role_map, dict):
        errors.append("'scripted_mode.role_map' must be an object")
        return

    for src, dst in role_map.items():
        if not isinstance(src, str) or src not in _SCRIPTED_REMAP_ROLES:
            errors.append(
                f"'scripted_mode.role_map' has invalid source role '{src}'"
            )
        if not isinstance(dst, str) or dst not in _SCRIPTED_REMAP_DESTINATION_ROLES:
            errors.append(
                f"'scripted_mode.role_map.{src}' has invalid destination role '{dst}'"
            )


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


def _validate_color_engine(data: dict[str, Any]) -> list[str]:
    """Validate the color_engine config block per §15.5 rules.

    Returns a list of human-readable error strings; empty list = valid.
    """
    errors: list[str] = []

    # enabled must be bool
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("color_engine.enabled must be a boolean")

    # scale_stops: must be a dict of str → [r,g,b]
    scale_stops_raw = data.get("scale_stops", dict(_DEFAULT_SCALE_STOPS))
    if not isinstance(scale_stops_raw, dict):
        errors.append("color_engine.scale_stops must be an object")
        scale_stops_raw = dict(_DEFAULT_SCALE_STOPS)
    else:
        for stop_name, stop_val in scale_stops_raw.items():
            if not isinstance(stop_val, (list, tuple)) or len(stop_val) != 3:
                errors.append(
                    f"color_engine.scale_stops.{stop_name} must be an RGB list of 3 integers"
                )
            elif not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in stop_val):
                errors.append(
                    f"color_engine.scale_stops.{stop_name} RGB values must be integers 0..255"
                )
    valid_stop_keys = set(scale_stops_raw.keys()) if isinstance(scale_stops_raw, dict) else set()

    # palette_dwell_tracks >= 1
    palette_dwell_tracks = data.get("palette_dwell_tracks", 4)
    if not isinstance(palette_dwell_tracks, int) or isinstance(palette_dwell_tracks, bool):
        errors.append("color_engine.palette_dwell_tracks must be an integer")
    elif palette_dwell_tracks < 1:
        errors.append("color_engine.palette_dwell_tracks must be >= 1")

    # snap_eligible_drop_indices: list of ints >= 1
    snap_indices = data.get("snap_eligible_drop_indices", [2, 3])
    if not isinstance(snap_indices, list):
        errors.append("color_engine.snap_eligible_drop_indices must be a list")
    else:
        for i, idx in enumerate(snap_indices):
            if not isinstance(idx, int) or isinstance(idx, bool):
                errors.append(
                    f"color_engine.snap_eligible_drop_indices[{i}] must be an integer"
                )
            elif idx < 1:
                errors.append(
                    f"color_engine.snap_eligible_drop_indices[{i}] must be >= 1"
                )

    # big_shift_chance in [0, 1]
    big_shift_chance = data.get("big_shift_chance", 0.25)
    if not isinstance(big_shift_chance, (int, float)) or isinstance(big_shift_chance, bool):
        errors.append("color_engine.big_shift_chance must be a number")
    elif not (0.0 <= float(big_shift_chance) <= 1.0):
        errors.append("color_engine.big_shift_chance must be in [0, 1]")

    # big_shift_weight_bias: number
    big_shift_weight_bias = data.get("big_shift_weight_bias", 1.0)
    if not isinstance(big_shift_weight_bias, (int, float)) or isinstance(big_shift_weight_bias, bool):
        errors.append("color_engine.big_shift_weight_bias must be a number")

    # drama_by_role: bool
    drama_by_role = data.get("drama_by_role", True)
    if not isinstance(drama_by_role, bool):
        errors.append("color_engine.drama_by_role must be a boolean")

    # role_spread: dict of str → number
    role_spread = data.get("role_spread", {})
    if not isinstance(role_spread, dict):
        errors.append("color_engine.role_spread must be an object")
    else:
        for role_name, spread_val in role_spread.items():
            if not isinstance(spread_val, (int, float)) or isinstance(spread_val, bool):
                errors.append(f"color_engine.role_spread.{role_name} must be a number")

    # step_within_section: dict of str → bool
    step_within_section = data.get("step_within_section", {})
    if not isinstance(step_within_section, dict):
        errors.append("color_engine.step_within_section must be an object")
    else:
        for role_name, step_val in step_within_section.items():
            if not isinstance(step_val, bool):
                errors.append(f"color_engine.step_within_section.{role_name} must be a boolean")

    # slot_fill_strategy_by_look: dict of str -> str
    slot_fill_strategy_by_look = data.get("slot_fill_strategy_by_look", {})
    if not isinstance(slot_fill_strategy_by_look, dict):
        errors.append("color_engine.slot_fill_strategy_by_look must be an object")
    else:
        for look_name, strategy_val in slot_fill_strategy_by_look.items():
            if strategy_val not in ("gradient_even", "random_with_replacement", "random_with_mono_chance"):
                errors.append(f"color_engine.slot_fill_strategy_by_look.{look_name} must be 'gradient_even', 'random_with_replacement', or 'random_with_mono_chance'")

    # slot_fill_strategy_by_role: dict of str -> str
    slot_fill_strategy_by_role = data.get("slot_fill_strategy_by_role", {})
    if not isinstance(slot_fill_strategy_by_role, dict):
        errors.append("color_engine.slot_fill_strategy_by_role must be an object")
    else:
        for role_name, strategy_val in slot_fill_strategy_by_role.items():
            if strategy_val not in ("gradient_even", "random_with_replacement", "random_with_mono_chance"):
                errors.append(f"color_engine.slot_fill_strategy_by_role.{role_name} must be 'gradient_even', 'random_with_replacement', or 'random_with_mono_chance'")

    # slot_mono_chance_by_look: dict of str -> number in [0, 1]
    slot_mono_chance_by_look = data.get("slot_mono_chance_by_look", {})
    if not isinstance(slot_mono_chance_by_look, dict):
        errors.append("color_engine.slot_mono_chance_by_look must be an object")
    else:
        for look_name, chance_val in slot_mono_chance_by_look.items():
            if not isinstance(chance_val, (int, float)) or isinstance(chance_val, bool):
                errors.append(f"color_engine.slot_mono_chance_by_look.{look_name} must be a number")
            elif not (0.0 <= float(chance_val) <= 1.0):
                errors.append(f"color_engine.slot_mono_chance_by_look.{look_name} must be in [0, 1]")

    # locked_palette_by_look: dict of look -> existing palette name
    locked_palette_by_look = data.get("locked_palette_by_look", {})
    if not isinstance(locked_palette_by_look, dict):
        errors.append("color_engine.locked_palette_by_look must be an object")
    else:
        palettes_for_lock = data.get("palettes", {})
        palette_names = set(palettes_for_lock) if isinstance(palettes_for_lock, dict) else set()
        for look_name, palette_name in locked_palette_by_look.items():
            if not isinstance(palette_name, str):
                errors.append(f"color_engine.locked_palette_by_look.{look_name} must be a palette name")
            elif palette_name not in palette_names:
                errors.append(f"color_engine.locked_palette_by_look.{look_name} references unknown palette '{palette_name}'")

    palette_control = data.get("palette_control", {})
    if not isinstance(palette_control, dict):
        errors.append("color_engine.palette_control must be an object")
    elif palette_control:
        if not isinstance(palette_control.get("enabled", False), bool):
            errors.append("color_engine.palette_control.enabled must be a boolean")
        if not isinstance(palette_control.get("device", "Stream Deck"), str):
            errors.append("color_engine.palette_control.device must be a string")
        channel = palette_control.get("channel", 2)
        if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 15:
            errors.append("color_engine.palette_control.channel must be an integer 0..15")
        palette_notes = palette_control.get("palette_notes", {})
        palettes_for_control = data.get("palettes", {})
        palette_names = set(palettes_for_control) if isinstance(palettes_for_control, dict) else set()
        if not isinstance(palette_notes, dict):
            errors.append("color_engine.palette_control.palette_notes must be an object")
        else:
            for name, note in palette_notes.items():
                if not isinstance(name, str) or name not in palette_names:
                    errors.append(f"color_engine.palette_control.palette_notes.{name} must name a configured palette")
                if not isinstance(note, int) or isinstance(note, bool) or not 0 <= note <= 127:
                    errors.append(f"color_engine.palette_control.palette_notes.{name} must be a MIDI note 0..127")
        for key in (
            "white_sand_note", "lock_note", "led_mute_note", "laser_mute_note",
            "laser_solo_note", "rainbow_note",
        ):
            note = palette_control.get(key)
            if not isinstance(note, int) or isinstance(note, bool) or not 0 <= note <= 127:
                errors.append(f"color_engine.palette_control.{key} must be a MIDI note 0..127")

    # fade_beats_by_role: dict of str → number
    fade_beats_by_role = data.get("fade_beats_by_role", {})
    if not isinstance(fade_beats_by_role, dict):
        errors.append("color_engine.fade_beats_by_role must be an object")
    else:
        for role_name, fade_val in fade_beats_by_role.items():
            if not isinstance(fade_val, (int, float)) or isinstance(fade_val, bool):
                errors.append(f"color_engine.fade_beats_by_role.{role_name} must be a number")

    # exempt_looks: list of strings
    exempt_looks = data.get("exempt_looks", [])
    if not isinstance(exempt_looks, list):
        errors.append("color_engine.exempt_looks must be a list")
    else:
        for i, name in enumerate(exempt_looks):
            if not isinstance(name, str):
                errors.append(f"color_engine.exempt_looks[{i}] must be a string")

    # diy_color_tags: dict of str → str
    diy_color_tags = data.get("diy_color_tags", {})
    if not isinstance(diy_color_tags, dict):
        errors.append("color_engine.diy_color_tags must be an object")
    else:
        for look_name, tag_val in diy_color_tags.items():
            if not isinstance(tag_val, str):
                errors.append(f"color_engine.diy_color_tags.{look_name} must be a string")

    # set_seed_mode: string
    set_seed_mode = data.get("set_seed_mode", "random")
    if not isinstance(set_seed_mode, str):
        errors.append("color_engine.set_seed_mode must be a string")

    # palettes: non-empty dict
    palettes = data.get("palettes")
    if not isinstance(palettes, dict) or not palettes:
        errors.append("color_engine.palettes must be a non-empty object")
        return errors  # can't validate palette contents

    # Validate each palette
    weight_sum = 0.0
    for palette_name, palette_data in palettes.items():
        if not isinstance(palette_data, dict):
            errors.append(f"color_engine.palettes.{palette_name} must be an object")
            continue
        p_prefix = f"color_engine.palettes.{palette_name}"
        p_type = palette_data.get("type", "journey")
        if p_type not in ("journey", "fixed_rgb", "rainbow"):
            errors.append(f"{p_prefix}.type must be journey, fixed_rgb, or rainbow")
        rgb = palette_data.get("rgb")
        if p_type == "fixed_rgb":
            if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
                errors.append(f"{p_prefix}.rgb is required for fixed_rgb and must be an RGB list")
            elif not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in rgb):
                errors.append(f"{p_prefix}.rgb values must be integers 0..255")
        elif rgb is not None:
            errors.append(f"{p_prefix}.rgb is only allowed for fixed_rgb palettes")

        # range: journey palettes require two stop names; fixed/rainbow palettes may omit it.
        p_range = palette_data.get("range", ("blue", "cyan") if p_type != "journey" else None)
        if not isinstance(p_range, (list, tuple)) or len(p_range) != 2:
            errors.append(f"{p_prefix}.range must be a list of 2 stop names")
        else:
            for endpoint in p_range:
                if not isinstance(endpoint, str):
                    errors.append(f"{p_prefix}.range endpoints must be strings")
                elif endpoint not in valid_stop_keys:
                    errors.append(
                        f"{p_prefix}.range endpoint '{endpoint}' is not a key in scale_stops"
                    )

        # white in [0, 1]
        white = palette_data.get("white", 0.0)
        if not isinstance(white, (int, float)) or isinstance(white, bool):
            errors.append(f"{p_prefix}.white must be a number")
        elif not (0.0 <= float(white) <= 1.0):
            errors.append(f"{p_prefix}.white must be in [0, 1]")

        # spread >= 0
        spread = palette_data.get("spread", 0.10)
        if not isinstance(spread, (int, float)) or isinstance(spread, bool):
            errors.append(f"{p_prefix}.spread must be a number")
        elif float(spread) < 0.0:
            errors.append(f"{p_prefix}.spread must be >= 0")

        # weight >= 0
        weight = palette_data.get("weight", 1.0)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            errors.append(f"{p_prefix}.weight must be a number")
        elif float(weight) < 0.0:
            errors.append(f"{p_prefix}.weight must be >= 0")
        else:
            weight_sum += float(weight)

        # dwell: optional int
        dwell = palette_data.get("dwell")
        if dwell is not None:
            if not isinstance(dwell, int) or isinstance(dwell, bool) or dwell < 1:
                errors.append(f"{p_prefix}.dwell must be a positive integer")

        # focus_modes: dict of str → number, with positive sum if present
        focus_modes = palette_data.get("focus_modes")
        if focus_modes is not None:
            if not isinstance(focus_modes, dict):
                errors.append(f"{p_prefix}.focus_modes must be an object")
            else:
                fm_sum = 0.0
                for mode_name, mode_weight in focus_modes.items():
                    if not isinstance(mode_weight, (int, float)) or isinstance(mode_weight, bool):
                        errors.append(f"{p_prefix}.focus_modes.{mode_name} must be a number")
                    elif float(mode_weight) < 0.0:
                        errors.append(f"{p_prefix}.focus_modes.{mode_name} must be >= 0")
                    else:
                        fm_sum += float(mode_weight)
                if focus_modes and fm_sum <= 0.0:
                    errors.append(
                        f"{p_prefix}.focus_modes weights must sum to > 0"
                    )

    # Check total palette weight > 0 (guards div-by-zero)
    if weight_sum <= 0.0:
        errors.append("color_engine.palettes: sum of all palette weights must be > 0")

    return errors


def _parse_color_engine(data: dict[str, Any]) -> Optional[ColorEngineConfig]:
    """Parse and return a ColorEngineConfig, or None if absent or invalid.

    Validation errors disable only the color engine (never the whole LED config).
    """
    raw = data.get("color_engine")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        _log.warning("[RGB] color_engine block is not an object — engine disabled")
        return None

    errs = _validate_color_engine(raw)
    if errs:
        _log.warning(
            "[RGB] color_engine config invalid — engine disabled. Errors: %s",
            "; ".join(errs),
        )
        return None

    # Build scale_stops
    scale_stops_raw = raw.get("scale_stops", dict(_DEFAULT_SCALE_STOPS))
    scale_stops: dict[str, tuple[int, int, int]] = {
        k: (int(v[0]), int(v[1]), int(v[2])) for k, v in scale_stops_raw.items()
    }

    # Build palettes
    palettes_raw = raw["palettes"]
    palettes: dict[str, Palette] = {}
    for name, p in palettes_raw.items():
        p_range_raw = p.get("range", ("blue", "cyan"))
        p_range: tuple[str, str] = (str(p_range_raw[0]), str(p_range_raw[1]))
        focus_modes_raw = p.get("focus_modes") or {}
        focus_modes: dict[str, float] = {k: float(v) for k, v in focus_modes_raw.items()}
        dwell_raw = p.get("dwell")
        palettes[name] = Palette(
            range=p_range,
            white=float(p.get("white", 0.0)),
            spread=float(p.get("spread", 0.10)),
            weight=float(p.get("weight", 1.0)),
            dwell=int(dwell_raw) if dwell_raw is not None else None,
            focus_modes=focus_modes,
            type=str(p.get("type", "journey")),
            rgb=tuple(int(v) for v in p["rgb"]) if p.get("type", "journey") == "fixed_rgb" else None,
        )

    # Build snap_eligible_drop_indices
    snap_indices = raw.get("snap_eligible_drop_indices", [2, 3])
    snap_tuple: tuple[int, ...] = tuple(int(i) for i in snap_indices)

    # Build exempt_looks
    exempt_looks_raw = raw.get("exempt_looks", [])
    exempt_looks: tuple[str, ...] = tuple(str(s) for s in exempt_looks_raw)

    # Build role_spread
    role_spread_raw = raw.get("role_spread", {"drop": 0.35, "groove": 0.12, "ambient": 0.10})
    role_spread: dict[str, float] = {k: float(v) for k, v in role_spread_raw.items()}

    # Build step_within_section
    step_raw = raw.get("step_within_section", {"drop": False, "post_drop": True, "groove": True})
    step_within_section: dict[str, bool] = {k: bool(v) for k, v in step_raw.items()}

    # Build slot_fill_strategy_by_look
    sfs_look_raw = raw.get("slot_fill_strategy_by_look", {})
    slot_fill_strategy_by_look: dict[str, str] = {k: str(v) for k, v in sfs_look_raw.items()}

    # Build slot_fill_strategy_by_role
    sfs_role_raw = raw.get("slot_fill_strategy_by_role", {})
    slot_fill_strategy_by_role: dict[str, str] = {k: str(v) for k, v in sfs_role_raw.items()}

    # Build slot_mono_chance_by_look
    mono_chance_raw = raw.get("slot_mono_chance_by_look", {})
    slot_mono_chance_by_look: dict[str, float] = {k: float(v) for k, v in mono_chance_raw.items()}

    # Build locked_palette_by_look
    locked_palette_raw = raw.get("locked_palette_by_look", {})
    locked_palette_by_look: dict[str, str] = {k: str(v) for k, v in locked_palette_raw.items()}
    palette_control = dict(raw.get("palette_control", {}) or {})
    palette_control_bindings = _build_palette_control_bindings(palette_control)

    # Build fade_beats_by_role
    fade_raw = raw.get(
        "fade_beats_by_role",
        {"drop": 0.0, "buildup": 0.0, "breakdown": 4.0, "post_drop": 2.0, "groove": 2.0, "ambient": 4.0},
    )
    fade_beats_by_role: dict[str, float] = {k: float(v) for k, v in fade_raw.items()}

    # Build diy_color_tags
    diy_color_tags_raw = raw.get("diy_color_tags", {})
    diy_color_tags: dict[str, str] = {k: str(v) for k, v in diy_color_tags_raw.items()}

    return ColorEngineConfig(
        enabled=bool(raw.get("enabled", True)),
        scale_stops=scale_stops,
        palette_dwell_tracks=int(raw.get("palette_dwell_tracks", 4)),
        snap_eligible_drop_indices=snap_tuple,
        big_shift_chance=float(raw.get("big_shift_chance", 0.25)),
        big_shift_weight_bias=float(raw.get("big_shift_weight_bias", 1.0)),
        drama_by_role=bool(raw.get("drama_by_role", True)),
        role_spread=role_spread,
        step_within_section=step_within_section,
        fade_beats_by_role=fade_beats_by_role,
        slot_fill_strategy_by_look=slot_fill_strategy_by_look,
        slot_fill_strategy_by_role=slot_fill_strategy_by_role,
        slot_mono_chance_by_look=slot_mono_chance_by_look,
        locked_palette_by_look=locked_palette_by_look,
        palette_control=palette_control,
        palette_control_bindings=palette_control_bindings,
        exempt_looks=exempt_looks,
        diy_color_tags=diy_color_tags,
        set_seed_mode=str(raw.get("set_seed_mode", "random")),
        palettes=palettes,
    )


def _build_palette_control_bindings(raw: dict[str, Any]) -> tuple[PackMidiBinding, ...]:
    if not raw or not bool(raw.get("enabled", False)):
        return ()
    device = str(raw.get("device", "Stream Deck"))
    channel = int(raw.get("channel", 2))
    bindings: list[PackMidiBinding] = []
    for name, note in (raw.get("palette_notes", {}) or {}).items():
        bindings.append(PackMidiBinding(
            device_name=device,
            message_type="note",
            channel_zero_based=channel,
            data_byte=int(note),
            target_kind="palette_pad",
            target_name=str(name),
        ))
    white_sand_note = raw.get("white_sand_note")
    if white_sand_note is not None:
        bindings.append(PackMidiBinding(
            device_name=device,
            message_type="note",
            channel_zero_based=channel,
            data_byte=int(white_sand_note),
            target_kind="palette_pad",
            target_name="white_sand",
        ))
    fixed = (
        ("lock_note", "palette_lock_pad"),
        ("led_mute_note", "led_mute_pad"),
        ("rainbow_note", "rainbow_pad"),
    )
    for key, kind in fixed:
        bindings.append(PackMidiBinding(
            device_name=device,
            message_type="note",
            channel_zero_based=channel,
            data_byte=int(raw[key]),
            target_kind=kind,  # type: ignore[arg-type]
        ))
    bindings.append(PackMidiBinding(
        device_name=device,
        message_type="note",
        channel_zero_based=channel,
        data_byte=int(raw["laser_mute_note"]),
        target_kind="blackout_mask",
        interaction="toggle",
    ))
    return tuple(bindings)


def _build_scripted_mode(raw: Any) -> LEDScriptedModePolicy:
    """Build the conservative scripted-mode role remap policy."""
    if not isinstance(raw, dict):
        return LEDScriptedModePolicy(
            default_role=_SCRIPTED_MODE_DEFAULT_ROLE,
            role_map=MappingProxyType(dict(_SCRIPTED_MODE_DEFAULT_ROLE_MAP)),
        )

    default_role = str(raw.get("default_role", _SCRIPTED_MODE_DEFAULT_ROLE))
    role_map_raw = raw.get("role_map", {})
    role_map = (
        {str(k): str(v) for k, v in role_map_raw.items()}
        if isinstance(role_map_raw, dict)
        else {}
    )
    return LEDScriptedModePolicy(
        default_role=default_role,
        role_map=MappingProxyType(role_map),
    )


def _build_config(data: dict[str, Any]) -> LEDConfig:
    targets_raw = data["targets"]
    looks_raw = data["looks"]
    param_profiles_raw = data.get("realtime_param_profiles", {})
    if not isinstance(param_profiles_raw, dict):
        param_profiles_raw = {}
    drop_pairs_raw = data.get("drop_pairs", {})
    if not isinstance(drop_pairs_raw, dict):
        drop_pairs_raw = {}
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
            backend=str(target.get("backend", "cloud_diy")),
            realtime=_build_realtime_config(target.get("realtime", {})),
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
            backend=str(look.get("backend", "cloud_diy")),
            params=MappingProxyType(_build_look_params(look, param_profiles_raw)),
            color_source=str(look.get("color_source", "engine")),
            diy_color=str(look.get("diy_color", "")),
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

    drop_pairs: dict[str, LEDDropPair] = {}
    for drop_name, raw_pair in drop_pairs_raw.items():
        if not isinstance(drop_name, str) or not isinstance(raw_pair, dict):
            continue
        drop_pairs[drop_name] = LEDDropPair(
            drop=drop_name,
            post_drop=str(raw_pair.get("post_drop", "")),
            duration_beats=float(raw_pair.get("duration_beats", 8.0)),
        )

    legacy_offset_s = float(
        automation_raw.get("offset_s", _AUTOMATION_DEFAULTS.offset_s)
    )
    cloud_offset_s = float(automation_raw.get("cloud_offset_s", legacy_offset_s))
    realtime_offset_s = float(
        automation_raw.get(
            "realtime_offset_s",
            _AUTOMATION_DEFAULTS.realtime_offset_s,
        )
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
            offset_s=cloud_offset_s,
            cloud_offset_s=cloud_offset_s,
            realtime_offset_s=realtime_offset_s,
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
            min_look_dwell_s=float(
                rate_limits_raw.get("min_look_dwell_s", _RATE_LIMIT_DEFAULTS.min_look_dwell_s)
            ),
            transport_switch_cooldown_s=float(
                rate_limits_raw.get(
                    "transport_switch_cooldown_s",
                    _RATE_LIMIT_DEFAULTS.transport_switch_cooldown_s,
                )
            ),
            rt_reconcile_window_s=float(
                rate_limits_raw.get(
                    "rt_reconcile_window_s", _RATE_LIMIT_DEFAULTS.rt_reconcile_window_s
                )
            ),
            rt_reconcile_interval_s=float(
                rate_limits_raw.get(
                    "rt_reconcile_interval_s",
                    _RATE_LIMIT_DEFAULTS.rt_reconcile_interval_s,
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
        drop_pairs=drop_pairs,
        post_drop_cycle_beats=float(data.get("post_drop_cycle_beats", 32.0)),
        color_engine=_parse_color_engine(data),
        scripted_mode=_build_scripted_mode(data.get("scripted_mode")),
    )


def _build_look_params(look: dict[str, Any], param_profiles: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    profile_name = look.get("param_profile", "")
    if isinstance(profile_name, str) and isinstance(param_profiles.get(profile_name), dict):
        params.update(param_profiles[profile_name])
    params.update(dict(look.get("params", {}) or {}))
    return params


def _to_tuple(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(str(v) for v in values)


def _build_realtime_config(raw: Any) -> LEDRealtimeConfig:
    data = raw if isinstance(raw, dict) else {}
    header_bytes = data.get("header_bytes", ())
    if not isinstance(header_bytes, list):
        header_bytes = ()
    return LEDRealtimeConfig(
        enabled=bool(data.get("enabled", False)),
        protocol=str(data.get("protocol", "")),
        ip=str(data.get("ip", "")),
        port=int(data.get("port", 4003)),
        segments=int(data.get("segments", 20)),
        header=str(data.get("header", "")),
        header_bytes=tuple(int(v) & 0xFF for v in header_bytes),
        stretch=bool(data.get("stretch", False)),
        fps=int(data.get("fps", 30)),
        activate_pt=str(data.get("activate_pt", "")),
        deactivate_pt=str(data.get("deactivate_pt", "")),
        proof_status=str(data.get("proof_status", "not_proven")),
        proof_date=str(data.get("proof_date", "")),
    )
