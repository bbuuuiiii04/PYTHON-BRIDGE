#!/usr/bin/env python3
"""Standalone Phase 2 manual Govee trigger tool.

This script intentionally stays outside bridge runtime modules.
Default mode is dry-run; live calls require --live and GOVEE_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request


BASE_URL = "https://openapi.api.govee.com"
API_KEY_HEADER = "Govee-API-Key"
REQUEST_TIMEOUT_S = 2.0
CONTROL_ENDPOINT = "/router/api/v1/device/control"

PHASE1_MANIFEST_PATH = Path("/tmp/govee_phase1_evidence_manifest.json")
PHASE1_SUMMARY_PATH = Path("/tmp/govee_api_reference_summary.txt")
PHASE1_DEVICES_PATH = Path("/tmp/govee_h612d_devices.json")
PHASE1_SCENES_PATH = Path("/tmp/govee_h612d_scenes.json")
RESULT_PATH = Path("/tmp/govee_h612d_trigger_result.json")

PROVENANCE_MAX_AGE_HOURS = 24

OFFICIAL_SOURCE_URLS = [
    "https://developer.govee.com/llms.txt",
    "https://developer.govee.com/docs/getting-started.md",
    "https://developer.govee.com/docs/support-product-model.md",
    "https://developer.govee.com/reference/get-you-devices.md",
    "https://developer.govee.com/reference/get-devices-status.md",
    "https://developer.govee.com/reference/get-light-scene.md",
    "https://developer.govee.com/reference/control-you-devices.md",
    "https://developer.govee.com/changelog/important-policy-update-important-notice-regarding-api-key-security-management.md",
]

CAP_ON_OFF_TYPE = "devices.capabilities.on_off"
CAP_ON_OFF_INSTANCE = "powerSwitch"
CAP_BRIGHTNESS_TYPE = "devices.capabilities.range"
CAP_BRIGHTNESS_INSTANCE = "brightness"
CAP_COLOR_TYPE = "devices.capabilities.color_setting"
CAP_COLOR_INSTANCE = "colorRgb"
CAP_DYNAMIC_SCENE_TYPE = "devices.capabilities.dynamic_scene"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_source_command(argv: List[str]) -> str:
    script = argv[0] if argv else "tools/govee_manual_trigger.py"
    safe_script = script if script else "tools/govee_manual_trigger.py"
    quoted = " ".join(shlex.quote(part) for part in [safe_script, *argv[1:]])
    return f"python3 {quoted}".strip()


def run_git_command(repo_root: Path, args: List[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def get_repo_context(repo_root: Path) -> Dict[str, str]:
    branch = run_git_command(repo_root, ["branch", "--show-current"]) or "unknown"
    commit = run_git_command(repo_root, ["rev-parse", "HEAD"]) or "unknown"
    return {"branch": branch, "commit": commit}


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first_nonempty(device: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = device.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def redact_device_id(device_id: str) -> str:
    if not device_id:
        return "<missing>"
    compact = device_id.replace(":", "")
    if len(compact) <= 6:
        return "***REDACTED***"
    return f"{compact[:4]}...{compact[-4:]}"


def looks_like_placeholder_ref(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("todo_", "example_", "fake_", "placeholder", "unmapped"))


def summarize_value(value: Any) -> str:
    if isinstance(value, dict):
        keys = sorted(value.keys())
        return f"object keys={keys}"
    if isinstance(value, list):
        return f"list len={len(value)}"
    return repr(value)


def select_bool_name(name: str) -> str:
    lowered = name.strip().lower()
    if lowered in ("on", "off"):
        return lowered
    return name


def capability_options_lookup(capability: Dict[str, Any]) -> Dict[str, Any]:
    parameters = capability.get("parameters")
    if not isinstance(parameters, dict):
        return {}
    options = parameters.get("options")
    if not isinstance(options, list):
        return {}
    lookup: Dict[str, Any] = {}
    for option in options:
        if not isinstance(option, dict):
            continue
        if "name" in option:
            lookup[str(option["name"]).strip().lower()] = option.get("value")
    return lookup


def capability_range(capability: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    parameters = capability.get("parameters")
    if not isinstance(parameters, dict):
        return None
    range_obj = parameters.get("range")
    if not isinstance(range_obj, dict):
        return None
    min_v = range_obj.get("min")
    max_v = range_obj.get("max")
    if not isinstance(min_v, (int, float)) or not isinstance(max_v, (int, float)):
        return None
    return (int(min_v), int(max_v))


def classify_default_target(device: Dict[str, Any]) -> bool:
    sku = first_nonempty(device, ["sku"]).upper()
    model = first_nonempty(device, ["model", "deviceModel", "deviceType"]).upper()
    name = first_nonempty(device, ["deviceName", "name"]).upper()
    return ("H612D" in sku) or ("H612D" in model) or ("ROOM_PERIMETER" in name)


def validate_provenance(
    manifest: Dict[str, Any],
    repo_context: Dict[str, str],
    now_utc: datetime,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    artifacts_by_path: Dict[str, Dict[str, Any]] = {}

    branch = str(manifest.get("repo_branch", "")).strip()
    commit = str(manifest.get("repo_commit", "")).strip()
    if branch != repo_context["branch"]:
        errors.append("phase1_manifest_branch_mismatch")
    if commit != repo_context["commit"]:
        errors.append("phase1_manifest_commit_mismatch")

    artifacts = manifest.get("artifacts_written")
    if not isinstance(artifacts, list):
        errors.append("phase1_manifest_artifacts_missing")
        artifacts = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if path:
            artifacts_by_path[path] = item

    required = {
        str(PHASE1_SUMMARY_PATH): "api_summary",
        str(PHASE1_DEVICES_PATH): "devices",
    }
    optional = {
        str(PHASE1_SCENES_PATH): "scenes",
    }

    checked: Dict[str, Dict[str, Any]] = {}
    for artifact_path, label in {**required, **optional}.items():
        record = artifacts_by_path.get(artifact_path)
        status = {
            "label": label,
            "record_found": bool(record),
            "file_exists": Path(artifact_path).exists(),
            "is_stale": True,
            "generated_at": "",
            "source_command": "",
            "error": "",
        }
        if not status["record_found"]:
            status["error"] = "record_missing"
            if artifact_path in required:
                errors.append(f"{label}_provenance_missing")
            else:
                warnings.append(f"{label}_provenance_missing")
            checked[label] = status
            continue

        generated_at = str(record.get("generated_at", "")).strip()
        source_command = str(record.get("source_command", "")).strip()
        status["generated_at"] = generated_at
        status["source_command"] = source_command

        if not status["file_exists"]:
            status["error"] = "file_missing"
            if artifact_path in required:
                errors.append(f"{label}_artifact_missing")
            else:
                warnings.append(f"{label}_artifact_missing")
            checked[label] = status
            continue

        parsed = parse_iso_utc(generated_at)
        if parsed is None:
            status["error"] = "generated_at_invalid"
            if artifact_path in required:
                errors.append(f"{label}_generated_at_invalid")
            else:
                warnings.append(f"{label}_generated_at_invalid")
            checked[label] = status
            continue

        age = now_utc - parsed
        stale = age > timedelta(hours=PROVENANCE_MAX_AGE_HOURS)
        status["is_stale"] = stale
        if stale:
            status["error"] = f"stale_age_hours>{PROVENANCE_MAX_AGE_HOURS}"
            if artifact_path in required:
                errors.append(f"{label}_artifact_stale")
            else:
                warnings.append(f"{label}_artifact_stale")

        if "govee_capability_capture.py" not in source_command:
            status["error"] = "unexpected_source_command"
            if artifact_path in required:
                errors.append(f"{label}_source_command_unexpected")
            else:
                warnings.append(f"{label}_source_command_unexpected")

        checked[label] = status

    return {
        "ok_for_devices": "devices_artifact_stale" not in errors
        and "devices_artifact_missing" not in errors
        and "devices_provenance_missing" not in errors
        and "phase1_manifest_branch_mismatch" not in errors
        and "phase1_manifest_commit_mismatch" not in errors
        and "phase1_manifest_artifacts_missing" not in errors
        and "devices_generated_at_invalid" not in errors
        and "devices_source_command_unexpected" not in errors,
        "ok_for_scenes": (
            "scenes" in checked
            and checked["scenes"]["record_found"]
            and checked["scenes"]["file_exists"]
            and not checked["scenes"]["is_stale"]
            and checked["scenes"]["error"] in ("",)
        ),
        "errors": errors,
        "warnings": warnings,
        "artifacts": checked,
    }


def extract_device_rows(devices_payload: Any) -> List[Dict[str, Any]]:
    if isinstance(devices_payload, dict):
        rows = devices_payload.get("data")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def select_target_device(
    rows: List[Dict[str, Any]],
    target_sku: str,
    target_name_contains: str,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], str]:
    candidates = rows[:]

    if target_sku:
        needle = target_sku.strip().upper()
        candidates = [row for row in candidates if first_nonempty(row, ["sku"]).upper() == needle]

    if target_name_contains:
        needle = target_name_contains.strip().upper()
        candidates = [row for row in candidates if needle in first_nonempty(row, ["deviceName", "name"]).upper()]

    selection_reason = "explicit_target_filters" if (target_sku or target_name_contains) else "default_target_selector"

    if not target_sku and not target_name_contains:
        candidates = [row for row in candidates if classify_default_target(row)]

    if not candidates:
        return None, [], selection_reason

    # Prefer exact H612D SKU when multiple rows match.
    prioritized = sorted(
        candidates,
        key=lambda row: (
            0 if first_nonempty(row, ["sku"]).upper() == "H612D" else 1,
            first_nonempty(row, ["deviceName", "name"]).upper(),
            first_nonempty(row, ["sku"]).upper(),
        ),
    )
    return prioritized[0], candidates, selection_reason


def find_capability(device: Dict[str, Any], cap_type: str, instance: str) -> Optional[Dict[str, Any]]:
    capabilities = device.get("capabilities")
    if not isinstance(capabilities, list):
        return None
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        if str(capability.get("type")) == cap_type and str(capability.get("instance")) == instance:
            return capability
    return None


def build_scene_index(scenes_payload: Any, selected_device: Dict[str, Any]) -> List[Dict[str, Any]]:
    attempts = []
    if isinstance(scenes_payload, dict):
        candidate = scenes_payload.get("scene_attempts")
        if isinstance(candidate, list):
            attempts = [item for item in candidate if isinstance(item, dict)]

    target_sku = first_nonempty(selected_device, ["sku"])
    target_device = first_nonempty(selected_device, ["device"])
    options: List[Dict[str, Any]] = []

    for attempt in attempts:
        target = attempt.get("target")
        if not isinstance(target, dict):
            continue
        if str(target.get("sku", "")) != target_sku:
            continue
        if str(target.get("device", "")) != target_device:
            continue
        response = attempt.get("response")
        if not isinstance(response, dict):
            continue
        payload = response.get("payload")
        if not isinstance(payload, dict):
            continue
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list):
            continue

        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            if str(capability.get("type")) != CAP_DYNAMIC_SCENE_TYPE:
                continue
            instance = str(capability.get("instance", ""))
            parameters = capability.get("parameters")
            if not isinstance(parameters, dict):
                continue
            capability_options = parameters.get("options")
            if not isinstance(capability_options, list):
                continue
            for option in capability_options:
                if not isinstance(option, dict):
                    continue
                name = str(option.get("name", "")).strip()
                value = option.get("value")
                if not name:
                    continue
                id_candidates: List[str] = []
                if isinstance(value, dict):
                    if "id" in value:
                        id_candidates.append(str(value["id"]))
                    if "paramId" in value:
                        id_candidates.append(str(value["paramId"]))
                elif value is not None:
                    id_candidates.append(str(value))
                options.append(
                    {
                        "name": name,
                        "capability_type": CAP_DYNAMIC_SCENE_TYPE,
                        "instance": instance,
                        "value": value,
                        "id_candidates": id_candidates,
                    }
                )
    return options


def resolve_scene(scene_query: str, scene_options: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    query = scene_query.strip()
    if not query:
        return None, "scene query is empty"

    lowered = query.casefold()

    exact_name = [item for item in scene_options if str(item.get("name", "")).casefold() == lowered]
    if len(exact_name) == 1:
        return exact_name[0], "matched scene by exact name"
    if len(exact_name) > 1:
        return None, "scene name is ambiguous (multiple exact-name matches)"

    id_matches = [item for item in scene_options if lowered in {x.casefold() for x in item.get("id_candidates", [])}]
    if len(id_matches) == 1:
        return id_matches[0], "matched scene by id"
    if len(id_matches) > 1:
        return None, "scene id is ambiguous (multiple id matches)"

    contains = [item for item in scene_options if lowered in str(item.get("name", "")).casefold()]
    if len(contains) == 1:
        return contains[0], "matched scene by unique name substring"
    if len(contains) > 1:
        return None, "scene query matched multiple scene names; use a more specific scene name or id"

    return None, "scene not found for selected target"


def parse_color_rgb(value: str) -> Tuple[Optional[int], str]:
    raw = value.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if raw.startswith("#"):
        raw = raw[1:]

    try:
        if all(ch in "0123456789abcdef" for ch in raw) and raw:
            parsed = int(raw, 16)
        else:
            parsed = int(value, 10)
    except ValueError:
        return None, "color value must be an integer or hex like 0xRRGGBB"

    if parsed < 0 or parsed > 16777215:
        return None, "color value must be between 0 and 16777215"
    return parsed, ""


def http_json_control(payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    url = f"{BASE_URL}{CONTROL_ENDPOINT}"
    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url=url, data=body_bytes, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header(API_KEY_HEADER, api_key)

    try:
        with urllib_request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
            status_code = int(response.getcode())
            raw_text = response.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = {"_non_json_body": raw_text}
            return {"ok": True, "status_code": status_code, "response": parsed, "error": ""}
    except urllib_error.HTTPError as exc:
        raw_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = {"_non_json_body": raw_text}
        return {"ok": False, "status_code": int(exc.code), "response": parsed, "error": f"HTTP {exc.code}"}
    except urllib_error.URLError as exc:
        return {"ok": False, "status_code": None, "response": None, "error": f"Network error: {exc.reason}"}
    except TimeoutError:
        return {"ok": False, "status_code": None, "response": None, "error": "Network error: timeout"}


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone Phase 2 manual Govee trigger tool.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build intended action only (default).")
    mode_group.add_argument("--live", action="store_true", help="Send one live control request.")

    parser.add_argument("--target-sku", default="", help="Target SKU exact match (e.g. H612D).")
    parser.add_argument("--target-name-contains", default="", help="Case-insensitive device name match substring.")

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--scene", default="", help="Scene name or scene id to trigger.")
    action_group.add_argument("--off", action="store_true", help="Send power off via on_off capability.")
    action_group.add_argument("--blackout", action="store_true", help="Alias of --off.")
    action_group.add_argument("--brightness", type=int, help="Set brightness value when supported.")
    action_group.add_argument("--color-rgb", default="", help="Set RGB integer/hex value when supported.")
    action_group.add_argument("--list-scenes", action="store_true", help="List sanitized scene options for target.")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    phase_started_at = utc_now_iso()
    source_command = build_source_command([Path(__file__).as_posix(), *argv])
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    repo_context = get_repo_context(repo_root)
    now_utc = datetime.now(timezone.utc)

    mode = "live" if args.live else "dry-run"
    action = "scene" if args.scene else "off" if (args.off or args.blackout) else "brightness" if args.brightness is not None else "color_rgb" if args.color_rgb else "list_scenes"
    result: Dict[str, Any] = {
        "phase": "Phase 2 - Standalone Manual Govee Trigger",
        "generated_at": utc_now_iso(),
        "phase_started_at": phase_started_at,
        "mode": mode,
        "source_command": source_command,
        "repo_branch": repo_context["branch"],
        "repo_commit": repo_context["commit"],
        "official_sources_checked": OFFICIAL_SOURCE_URLS,
        "official_contract": {
            "base_url": BASE_URL,
            "control_endpoint": CONTROL_ENDPOINT,
            "auth_header": API_KEY_HEADER,
            "request_timeout_s": REQUEST_TIMEOUT_S,
        },
        "artifact_paths": {
            "phase1_manifest": str(PHASE1_MANIFEST_PATH),
            "phase1_api_summary": str(PHASE1_SUMMARY_PATH),
            "phase1_devices": str(PHASE1_DEVICES_PATH),
            "phase1_scenes": str(PHASE1_SCENES_PATH),
            "result_json": str(RESULT_PATH),
        },
        "live_call_approved_by_supervisor": "external_gate_required",
        "live_calls_made": False,
        "action": action,
        "ok": False,
        "error": "",
        "warnings": [],
    }

    if args.live and args.dry_run:
        result["error"] = "choose either --dry-run or --live"
        write_json(RESULT_PATH, result)
        print("status=error mode=invalid reason=choose-either-dry-run-or-live")
        return 2

    summary_text = ""
    if not PHASE1_SUMMARY_PATH.exists():
        result["error"] = "missing /tmp/govee_api_reference_summary.txt; run Phase 1 capture first"
        write_json(RESULT_PATH, result)
        print("status=error phase1_summary=missing")
        return 2
    summary_text = PHASE1_SUMMARY_PATH.read_text(encoding="utf-8")
    if CONTROL_ENDPOINT not in summary_text or API_KEY_HEADER not in summary_text:
        result["error"] = "phase1 API summary missing required control endpoint/header evidence"
        write_json(RESULT_PATH, result)
        print("status=error phase1_summary=insufficient")
        return 2

    if not PHASE1_MANIFEST_PATH.exists():
        result["error"] = "missing /tmp/govee_phase1_evidence_manifest.json; run Phase 1 capture first"
        write_json(RESULT_PATH, result)
        print("status=error phase1_manifest=missing")
        return 2

    try:
        manifest_payload = read_json(PHASE1_MANIFEST_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        result["error"] = f"cannot parse phase1 manifest: {exc}"
        write_json(RESULT_PATH, result)
        print("status=error phase1_manifest=unreadable")
        return 2

    if not isinstance(manifest_payload, dict):
        result["error"] = "phase1 manifest must be a JSON object"
        write_json(RESULT_PATH, result)
        print("status=error phase1_manifest=invalid-structure")
        return 2

    provenance = validate_provenance(manifest_payload, repo_context, now_utc)
    result["artifact_provenance"] = provenance
    if not provenance["ok_for_devices"]:
        result["error"] = "phase1 device artifact provenance is missing/stale or branch/commit mismatched"
        write_json(RESULT_PATH, result)
        print("status=error provenance=devices-not-current")
        return 2

    try:
        devices_payload = read_json(PHASE1_DEVICES_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        result["error"] = f"cannot parse {PHASE1_DEVICES_PATH}: {exc}"
        write_json(RESULT_PATH, result)
        print("status=error devices_artifact=unreadable")
        return 2

    rows = extract_device_rows(devices_payload)
    if not rows:
        result["error"] = "phase1 devices artifact has no device rows"
        write_json(RESULT_PATH, result)
        print("status=error devices=empty")
        return 2

    selected, candidates, selection_reason = select_target_device(
        rows=rows,
        target_sku=args.target_sku,
        target_name_contains=args.target_name_contains,
    )
    result["target_selection"] = {
        "reason": selection_reason,
        "candidate_count": len(candidates),
        "explicit_filters": {
            "target_sku": args.target_sku or "",
            "target_name_contains": args.target_name_contains or "",
        },
    }
    if selected is None:
        result["error"] = "no matching target device found from phase1 devices artifact"
        write_json(RESULT_PATH, result)
        print("status=error target=not-found")
        return 2

    target_sku = first_nonempty(selected, ["sku"])
    target_device = first_nonempty(selected, ["device"])
    target_name = first_nonempty(selected, ["deviceName", "name"]) or "<unnamed>"
    result["target"] = {
        "sku": target_sku,
        "device": target_device if args.live else redact_device_id(target_device),
        "device_redacted": redact_device_id(target_device),
        "name": target_name,
    }

    capability_payload: Optional[Dict[str, Any]] = None
    action_detail: Dict[str, Any] = {}
    listed_scene_names: List[str] = []

    if action == "scene":
        if not provenance["ok_for_scenes"]:
            result["error"] = "scene action requested but phase1 scene artifact provenance is missing/stale"
            write_json(RESULT_PATH, result)
            print("status=error scenes_provenance=not-current")
            return 2
        try:
            scenes_payload = read_json(PHASE1_SCENES_PATH)
        except (OSError, json.JSONDecodeError) as exc:
            result["error"] = f"cannot parse {PHASE1_SCENES_PATH}: {exc}"
            write_json(RESULT_PATH, result)
            print("status=error scenes_artifact=unreadable")
            return 2

        scene_options = build_scene_index(scenes_payload, selected)
        if not scene_options:
            result["error"] = "no dynamic scene options found for selected target"
            write_json(RESULT_PATH, result)
            print("status=error scenes=unavailable")
            return 2
        resolved, reason = resolve_scene(args.scene, scene_options)
        if resolved is None:
            result["error"] = reason
            result["scene_choices_preview"] = sorted({item["name"] for item in scene_options})[:10]
            write_json(RESULT_PATH, result)
            print(f"status=error scene=unresolved reason={reason}")
            return 2
        capability_payload = {
            "type": resolved["capability_type"],
            "instance": resolved["instance"],
            "value": resolved["value"],
        }
        action_detail = {
            "scene_query": args.scene,
            "scene_resolution": reason,
            "scene_name": resolved["name"],
            "scene_value_summary": summarize_value(resolved["value"]),
        }

    elif action == "off":
        cap = find_capability(selected, CAP_ON_OFF_TYPE, CAP_ON_OFF_INSTANCE)
        if cap is None:
            result["error"] = "selected target does not expose on_off powerSwitch capability"
            write_json(RESULT_PATH, result)
            print("status=error capability=on_off-missing")
            return 2

        options_lookup = capability_options_lookup(cap)
        off_value = options_lookup.get("off", 0)
        if off_value is None:
            result["error"] = "on_off capability does not define an off value"
            write_json(RESULT_PATH, result)
            print("status=error capability=on_off-off-value-missing")
            return 2
        capability_payload = {
            "type": CAP_ON_OFF_TYPE,
            "instance": CAP_ON_OFF_INSTANCE,
            "value": off_value,
        }
        action_detail = {"requested": "off", "blackout_alias_used": bool(args.blackout)}

    elif action == "brightness":
        cap = find_capability(selected, CAP_BRIGHTNESS_TYPE, CAP_BRIGHTNESS_INSTANCE)
        if cap is None:
            result["error"] = "selected target does not expose brightness range capability"
            write_json(RESULT_PATH, result)
            print("status=error capability=brightness-missing")
            return 2
        numeric = int(args.brightness)
        cap_range = capability_range(cap)
        if cap_range is None:
            result["error"] = "brightness capability missing numeric range definition"
            write_json(RESULT_PATH, result)
            print("status=error capability=brightness-range-missing")
            return 2
        min_v, max_v = cap_range
        if numeric < min_v or numeric > max_v:
            result["error"] = f"brightness must be between {min_v} and {max_v}"
            write_json(RESULT_PATH, result)
            print(f"status=error brightness=out-of-range allowed={min_v}-{max_v}")
            return 2
        capability_payload = {
            "type": CAP_BRIGHTNESS_TYPE,
            "instance": CAP_BRIGHTNESS_INSTANCE,
            "value": numeric,
        }
        action_detail = {"requested_brightness": numeric, "allowed_range": {"min": min_v, "max": max_v}}

    elif action == "color_rgb":
        cap = find_capability(selected, CAP_COLOR_TYPE, CAP_COLOR_INSTANCE)
        if cap is None:
            result["error"] = "selected target does not expose colorRgb capability"
            write_json(RESULT_PATH, result)
            print("status=error capability=color-rgb-missing")
            return 2
        color_value, color_error = parse_color_rgb(args.color_rgb)
        if color_value is None:
            result["error"] = color_error
            write_json(RESULT_PATH, result)
            print(f"status=error color={color_error}")
            return 2
        cap_range = capability_range(cap)
        if cap_range is not None:
            min_v, max_v = cap_range
            if color_value < min_v or color_value > max_v:
                result["error"] = f"color value must be between {min_v} and {max_v}"
                write_json(RESULT_PATH, result)
                print(f"status=error color=out-of-range allowed={min_v}-{max_v}")
                return 2
        capability_payload = {
            "type": CAP_COLOR_TYPE,
            "instance": CAP_COLOR_INSTANCE,
            "value": color_value,
        }
        action_detail = {"requested_color_rgb": color_value}

    elif action == "list_scenes":
        if not provenance["ok_for_scenes"]:
            result["error"] = "scene listing requested but phase1 scene artifact provenance is missing/stale"
            write_json(RESULT_PATH, result)
            print("status=error scenes_provenance=not-current")
            return 2
        try:
            scenes_payload = read_json(PHASE1_SCENES_PATH)
        except (OSError, json.JSONDecodeError) as exc:
            result["error"] = f"cannot parse {PHASE1_SCENES_PATH}: {exc}"
            write_json(RESULT_PATH, result)
            print("status=error scenes_artifact=unreadable")
            return 2
        scene_options = build_scene_index(scenes_payload, selected)
        listed_scene_names = sorted({item["name"] for item in scene_options})
        result["scene_choices"] = listed_scene_names
        result["scene_choice_count"] = len(listed_scene_names)
        if not listed_scene_names:
            result["warnings"].append("no dynamic scene options found for selected target")
        result["ok"] = True
        write_json(RESULT_PATH, result)
        print(
            "status=ok mode=dry-run action=list-scenes "
            f"target={target_sku}/{redact_device_id(target_device)} scenes={len(listed_scene_names)}"
        )
        return 0

    if capability_payload is None:
        result["error"] = "no actionable capability payload resolved"
        write_json(RESULT_PATH, result)
        print("status=error capability-payload=missing")
        return 2

    control_payload = {
        "requestId": str(uuid.uuid4()),
        "payload": {
            "sku": target_sku,
            "device": target_device,
            "capability": capability_payload,
        },
    }
    result["intended_control"] = {
        "capability": capability_payload,
        "payload_preview": {
            "requestId": "<generated-uuid>",
            "payload": {
                "sku": target_sku,
                "device": redact_device_id(target_device),
                "capability": {
                    "type": capability_payload["type"],
                    "instance": capability_payload["instance"],
                    "value_summary": summarize_value(capability_payload["value"]),
                },
            },
        },
        "action_detail": action_detail,
    }

    if not args.live:
        result["ok"] = True
        result["mode"] = "dry-run"
        result["live_calls_made"] = False
        write_json(RESULT_PATH, result)
        print(
            "status=ok mode=dry-run "
            f"action={action} target={target_sku}/{redact_device_id(target_device)} "
            f"capability={capability_payload['type']}::{capability_payload['instance']}"
        )
        return 0

    api_key = os.environ.get("GOVEE_API_KEY", "").strip()
    if not api_key:
        result["error"] = "GOVEE_API_KEY is missing; refusing --live before any network call"
        write_json(RESULT_PATH, result)
        print("status=error live-refused missing-api-key")
        return 2

    response = http_json_control(control_payload, api_key=api_key)
    result["mode"] = "live"
    result["live_calls_made"] = True
    result["live_response"] = response
    result["live_request_private"] = control_payload
    result["private_artifact_note"] = (
        "This result artifact may contain raw Govee response data and is private by default."
    )

    response_body = response.get("response")
    response_code = None
    response_msg = ""
    if isinstance(response_body, dict):
        response_code = response_body.get("code")
        response_msg = str(response_body.get("msg", ""))
    command_success = bool(response.get("ok")) and str(response_code) == "200"
    result["ok"] = command_success
    result["operator_visual_confirmation_required"] = command_success
    result["post_live_requirement"] = (
        "If this live command reports success, require operator visual confirmation before claiming physical LED proof."
    )

    write_json(RESULT_PATH, result)
    status_word = "ok" if command_success else "error"
    print(
        f"status={status_word} mode=live action={action} "
        f"target={target_sku}/{redact_device_id(target_device)} "
        f"http_status={response.get('status_code')} api_code={response_code}"
    )
    return 0 if command_success else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
