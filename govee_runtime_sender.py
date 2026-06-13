"""Runtime Govee sender for LED Look Director decisions.

This module is intentionally small and secret-aware: API keys are read only from
the process environment, raw device IDs are never exposed in status, and raw
Govee responses are reduced to bounded success/error strings.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from .led_models import LEDAdapterCommand, LEDConfig

BASE_URL = "https://openapi.api.govee.com"
API_KEY_HEADER = "Govee-API-Key"
CONTROL_ENDPOINT = "/router/api/v1/device/control"
USER_DEVICES_ENDPOINT = "/router/api/v1/user/devices"
DEVICE_SCENES_ENDPOINT = "/router/api/v1/device/scenes"

DEVICES_PATH = Path("/tmp/govee_h612d_devices.json")
SCENES_PATH = Path("/tmp/govee_h612d_scenes.json")

CAP_ON_OFF_TYPE = "devices.capabilities.on_off"
CAP_ON_OFF_INSTANCE = "powerSwitch"
CAP_DYNAMIC_SCENE_TYPE = "devices.capabilities.dynamic_scene"
CAP_MUSIC_SETTING_TYPE = "devices.capabilities.music_setting"
CAP_MUSIC_SETTING_INSTANCE = "musicMode"
CAP_DIY_SCENE_INSTANCE = "diyScene"
MUSIC_MODE_VALUES = {
    "rhythm": 0,
    "sprouting": 1,
    "shiny": 2,
}


def redact_device_id(device_id: str) -> str:
    compact = str(device_id or "").replace(":", "")
    if len(compact) <= 6:
        return "<redacted>"
    return f"{compact[:4]}...{compact[-4:]}"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first_nonempty(row: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _device_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [row for row in payload["data"] if isinstance(row, dict)]
    return []


def _find_device(rows: list[dict[str, Any]], *, sku: str, device_ref: str) -> dict[str, Any] | None:
    for row in rows:
        if _first_nonempty(row, ("sku",)).upper() != sku.upper():
            continue
        if _first_nonempty(row, ("device",)) == device_ref:
            return row
    return None


def _capability_options_lookup(capability: Mapping[str, Any]) -> dict[str, Any]:
    parameters = capability.get("parameters")
    if not isinstance(parameters, dict):
        return {}
    options = parameters.get("options")
    if not isinstance(options, list):
        return {}
    lookup: dict[str, Any] = {}
    for option in options:
        if isinstance(option, dict) and "name" in option:
            lookup[str(option["name"]).strip().casefold()] = option.get("value")
    return lookup


def _find_capability(device: Mapping[str, Any], cap_type: str, instance: str) -> Mapping[str, Any] | None:
    capabilities = device.get("capabilities")
    if not isinstance(capabilities, list):
        return None
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        if str(capability.get("type")) == cap_type and str(capability.get("instance")) == instance:
            return capability
    return None


def _build_scene_index(scenes_payload: Any, *, sku: str, device_ref: str) -> dict[str, Mapping[str, Any]]:
    attempts = []
    if isinstance(scenes_payload, dict) and isinstance(scenes_payload.get("scene_attempts"), list):
        attempts = [item for item in scenes_payload["scene_attempts"] if isinstance(item, dict)]

    index: dict[str, Mapping[str, Any]] = {}
    for attempt in attempts:
        target = attempt.get("target")
        if not isinstance(target, dict):
            continue
        if str(target.get("sku", "")).upper() != sku.upper():
            continue
        if str(target.get("device", "")) != device_ref:
            continue
        response = attempt.get("response")
        payload = response.get("payload") if isinstance(response, dict) else None
        capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
        if not isinstance(capabilities, list):
            continue
        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            if str(capability.get("type")) != CAP_DYNAMIC_SCENE_TYPE:
                continue
            instance = str(capability.get("instance", ""))
            parameters = capability.get("parameters")
            options = parameters.get("options") if isinstance(parameters, dict) else None
            if not isinstance(options, list):
                continue
            for option in options:
                if not isinstance(option, dict):
                    continue
                name = str(option.get("name", "")).strip()
                value = option.get("value")
                if not name:
                    continue
                index[name.casefold()] = {
                    "name": name,
                    "type": CAP_DYNAMIC_SCENE_TYPE,
                    "instance": instance,
                    "value": value,
                }
    return index


def _positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _is_diy_scene_index_entry(scene: Mapping[str, Any] | None) -> bool:
    return bool(scene is not None and scene.get("instance") == CAP_DIY_SCENE_INSTANCE)


def _fetch_user_device_rows(*, api_key: str, urlopen: Callable[..., Any]) -> list[dict[str, Any]]:
    req = urllib_request.Request(
        url=f"{BASE_URL}{USER_DEVICES_ENDPOINT}",
        method="GET",
    )
    req.add_header(API_KEY_HEADER, api_key)
    with urlopen(req, timeout=5.0) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return _device_rows(json.loads(raw))


def _fetch_device_scenes(
    *,
    api_key: str,
    sku: str,
    device_ref: str,
    urlopen: Callable[..., Any],
) -> Any:
    payload = {
        "requestId": str(uuid.uuid4()),
        "payload": {
            "sku": sku,
            "device": device_ref,
        },
    }
    req = urllib_request.Request(
        url=f"{BASE_URL}{DEVICE_SCENES_ENDPOINT}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header(API_KEY_HEADER, api_key)
    with urlopen(req, timeout=5.0) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _load_device_rows(
    *,
    devices_path: Path,
    api_key: str,
    urlopen: Callable[..., Any],
    required_device_refs: tuple[tuple[str, str], ...] = (),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if devices_path.is_file():
            rows = _device_rows(_read_json(devices_path))
    except (OSError, json.JSONDecodeError):
        rows = []

    missing = [
        device_ref
        for sku, device_ref in required_device_refs
        if _find_device(rows, sku=sku, device_ref=device_ref) is None
    ]
    if not missing or not str(api_key).strip():
        return rows

    try:
        api_rows = _fetch_user_device_rows(api_key=str(api_key).strip(), urlopen=urlopen)
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return rows

    by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            by_key[(row.get("sku"), row.get("device"))] = row
    for row in api_rows:
        if isinstance(row, dict):
            by_key[(row.get("sku"), row.get("device"))] = row
    return list(by_key.values())


class GoveeRuntimeSender:
    """Translate LED adapter commands into physical Govee API calls."""

    def __init__(
        self,
        config: LEDConfig,
        *,
        api_key: str | None = None,
        devices_path: Path = DEVICES_PATH,
        scenes_path: Path = SCENES_PATH,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        self._api_key = api_key if api_key is not None else os.environ.get("GOVEE_API_KEY", "")
        self._urlopen = urlopen or urllib_request.urlopen
        self._target_meta: dict[str, dict[str, Any]] = {}
        self._devices_by_target: dict[str, dict[str, Any]] = {}
        self._scene_indexes: dict[str, dict[str, Mapping[str, Any]]] = {}

        rows = _load_device_rows(
            devices_path=devices_path,
            api_key=str(self._api_key or ""),
            urlopen=self._urlopen,
            required_device_refs=tuple(
                (target.expected_model, target.device_ref)
                for target in config.targets.values()
                if target.control_route == "govee_platform_dynamic_scene"
            ),
        )
        try:
            scenes_payload = _read_json(scenes_path)
        except (OSError, json.JSONDecodeError):
            scenes_payload = {}
        for name, target in config.targets.items():
            if target.control_route != "govee_platform_dynamic_scene":
                continue
            device = _find_device(
                rows,
                sku=target.expected_model,
                device_ref=target.device_ref,
            )
            if device is None:
                raise ValueError(f"target_not_found:{name}")
            sku = _first_nonempty(device, ("sku",))
            device_ref = _first_nonempty(device, ("device",))
            self._target_meta[name] = {
                "sku": sku,
                "device": device_ref,
                "redacted": redact_device_id(device_ref),
            }
            self._devices_by_target[name] = device
            self._scene_indexes[name] = _build_scene_index(
                scenes_payload,
                sku=sku,
                device_ref=device_ref,
            )
        self._refresh_named_diy_scene_indexes()

    def status(self) -> dict[str, Any]:
        mirror_count = sum(len(target.mirror_targets) for target in self._config.targets.values())
        return {
            "api_key_present": bool(str(self._api_key).strip()),
            "target_count": len(self._target_meta),
            "mirror_count": mirror_count,
            "scene_count": sum(len(index) for index in self._scene_indexes.values()),
        }

    def _refresh_named_diy_scene_indexes(self) -> None:
        api_key = str(self._api_key or "").strip()
        if not api_key:
            return

        refs_by_target: dict[str, set[str]] = {}
        for look in self._config.looks.values():
            if look.action != "diy_scene" or _positive_int_or_none(look.scene_ref) is not None:
                continue
            target_names = [look.target]
            target_cfg = self._config.targets.get(look.target)
            if target_cfg is not None:
                target_names.extend(target_cfg.mirror_targets)
            for target_name in target_names:
                refs_by_target.setdefault(target_name, set()).add(look.scene_ref.casefold())

        for target_name, wanted_refs in refs_by_target.items():
            current = self._scene_indexes.get(target_name, {})
            if all(_is_diy_scene_index_entry(current.get(ref)) for ref in wanted_refs):
                continue
            meta = self._target_meta.get(target_name)
            if meta is None:
                continue
            try:
                response = _fetch_device_scenes(
                    api_key=api_key,
                    sku=str(meta.get("sku", "")),
                    device_ref=str(meta.get("device", "")),
                    urlopen=self._urlopen,
                )
            except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                continue
            refreshed = _build_scene_index(
                {
                    "scene_attempts": [
                        {
                            "target": {
                                "sku": meta.get("sku", ""),
                                "device": meta.get("device", ""),
                            },
                            "response": response,
                        }
                    ]
                },
                sku=str(meta.get("sku", "")),
                device_ref=str(meta.get("device", "")),
            )
            if refreshed:
                merged = dict(current)
                merged.update(refreshed)
                self._scene_indexes[target_name] = merged

    def send(self, command: LEDAdapterCommand, timeout_s: float) -> dict[str, Any]:
        primary = self._send_to_target(command, timeout_s=timeout_s)
        target_cfg = self._config.targets.get(command.target)
        if target_cfg is None:
            return primary
        for mirror_name in target_cfg.mirror_targets:
            mirror_cmd = replace(command, target=mirror_name)
            self._send_to_target(mirror_cmd, timeout_s=timeout_s)
        return primary

    def _send_to_target(self, command: LEDAdapterCommand, *, timeout_s: float) -> dict[str, Any]:
        api_key = str(self._api_key or "").strip()
        if not api_key:
            raise RuntimeError("missing_govee_api_key")

        target = self._target_meta.get(command.target)
        if target is None:
            return {"ok": False, "error": "unknown_target"}

        capability = self._capability_payload(command)
        if capability is None:
            return {"ok": False, "error": "unresolved_capability"}

        payload = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": target["sku"],
                "device": target["device"],
                "capability": capability,
            },
        }
        response = self._post_control(payload, api_key=api_key, timeout_s=timeout_s)
        if response.get("ok") is not True:
            return {"ok": False, "error": str(response.get("error") or "send_failed")}

        body = response.get("response")
        api_code = body.get("code") if isinstance(body, dict) else None
        if str(api_code) != "200":
            return {"ok": False, "error": f"api_code:{api_code}"}
        return {"ok": True}

    def _capability_payload(self, command: LEDAdapterCommand) -> dict[str, Any] | None:
        if command.action == "scene":
            scene = self._scene_indexes.get(command.target, {}).get(command.scene_ref.casefold())
            if scene is None:
                return None
            return {
                "type": scene["type"],
                "instance": scene["instance"],
                "value": scene["value"],
            }
        if command.action == "diy_scene":
            diy_value = _positive_int_or_none(command.scene_ref)
            if diy_value is None:
                scene = self._scene_indexes.get(command.target, {}).get(command.scene_ref.casefold())
                if not _is_diy_scene_index_entry(scene):
                    return None
                raw_value = scene.get("value")
                if isinstance(raw_value, Mapping):
                    raw_value = raw_value.get("id", raw_value.get("value"))
                diy_value = _positive_int_or_none(raw_value)
                if diy_value is None:
                    return None
            return {
                "type": CAP_DYNAMIC_SCENE_TYPE,
                "instance": CAP_DIY_SCENE_INSTANCE,
                "value": diy_value,
            }
        if command.action == "music_mode":
            parsed = self._parse_music_mode_ref(command.scene_ref)
            if parsed is None:
                return None
            return {
                "type": CAP_MUSIC_SETTING_TYPE,
                "instance": CAP_MUSIC_SETTING_INSTANCE,
                "value": parsed,
            }
        if command.action == "off":
            device = self._devices_by_target.get(command.target)
            if device is None:
                return None
            cap = _find_capability(device, CAP_ON_OFF_TYPE, CAP_ON_OFF_INSTANCE)
            if cap is None:
                return None
            off_value = _capability_options_lookup(cap).get("off", 0)
            return {
                "type": CAP_ON_OFF_TYPE,
                "instance": CAP_ON_OFF_INSTANCE,
                "value": off_value,
            }
        return None

    def _parse_music_mode_ref(self, scene_ref: str) -> dict[str, int] | None:
        parts = [part.strip() for part in str(scene_ref or "").split(":")]
        if not parts or not parts[0]:
            return None
        mode_value = MUSIC_MODE_VALUES.get(parts[0].casefold())
        if mode_value is None:
            return None
        sensitivity = 100
        if len(parts) >= 2:
            try:
                sensitivity = int(parts[1])
            except ValueError:
                return None
            if sensitivity < 0 or sensitivity > 100:
                return None
        auto_color = 1
        if len(parts) >= 3:
            token = parts[2].casefold()
            if token in {"auto", "on"}:
                auto_color = 1
            elif token in {"manual", "off"}:
                auto_color = 0
            else:
                return None
        return {"musicMode": mode_value, "sensitivity": sensitivity, "autoColor": auto_color}

    def _post_control(self, payload: dict[str, Any], *, api_key: str, timeout_s: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url=f"{BASE_URL}{CONTROL_ENDPOINT}",
            data=body,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        req.add_header(API_KEY_HEADER, api_key)
        try:
            with self._urlopen(req, timeout=max(0.001, float(timeout_s))) as response:
                status_code = int(response.getcode())
                raw = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            return {"ok": False, "error": f"http_status:{int(exc.code)}"}
        except urllib_error.URLError as exc:
            return {"ok": False, "error": f"network_error:{exc.reason.__class__.__name__}"}
        except TimeoutError:
            return {"ok": False, "error": "network_timeout"}

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        return {"ok": 200 <= status_code < 300, "response": parsed, "error": ""}
