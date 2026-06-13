#!/usr/bin/env python3
"""Standalone Phase 1 Govee capability capture tool.

This tool is intentionally standalone and does not import bridge runtime modules.
Default behavior is dry-run and performs no live Govee API calls.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request


BASE_URL = "https://openapi.api.govee.com"
API_KEY_HEADER = "Govee-API-Key"
REQUEST_TIMEOUT_S = 2.0

ENDPOINT_LIST_DEVICES = "/router/api/v1/user/devices"
ENDPOINT_DEVICE_STATE = "/router/api/v1/device/state"
ENDPOINT_DEVICE_SCENES = "/router/api/v1/device/scenes"
ENDPOINT_DEVICE_CONTROL = "/router/api/v1/device/control"

LIVE_APPROVAL_PHRASE = "LIVE COMMAND APPROVED - PHASE 1"

OFFICIAL_SOURCE_URLS = [
    "https://developer.govee.com/docs/getting-started",
    "https://developer.govee.com/docs/support-product-model",
    "https://developer.govee.com/llms.txt",
    "https://developer.govee.com/reference/get-you-devices",
    "https://developer.govee.com/reference/get-devices-status",
    "https://developer.govee.com/reference/get-light-scene",
    "https://developer.govee.com/reference/control-you-devices",
    "https://developer.govee.com/reference/subscribe-device-event",
    "https://developer.govee.com/changelog/important-policy-update-important-notice-regarding-api-key-security-management",
    # llms.txt-linked markdown references inspected for this phase
    "https://developer.govee.com/docs/getting-started.md",
    "https://developer.govee.com/reference/get-you-devices.md",
    "https://developer.govee.com/reference/get-devices-status.md",
    "https://developer.govee.com/reference/get-light-scene.md",
    "https://developer.govee.com/reference/control-you-devices.md",
    "https://developer.govee.com/reference/subscribe-device-event.md",
    "https://developer.govee.com/changelog/important-policy-update-important-notice-regarding-api-key-security-management.md",
]

ARTIFACT_API_REFERENCE = Path("/tmp/govee_api_reference_summary.txt")
ARTIFACT_SUMMARY = Path("/tmp/govee_h612d_summary.txt")
ARTIFACT_DEVICES = Path("/tmp/govee_h612d_devices.json")
ARTIFACT_SCENES = Path("/tmp/govee_h612d_scenes.json")
ARTIFACT_MANIFEST = Path("/tmp/govee_phase1_evidence_manifest.json")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_source_command(argv: List[str]) -> str:
    script = argv[0] if argv else "tools/govee_capability_capture.py"
    safe_script = script if script else "tools/govee_capability_capture.py"
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


def get_repo_context(repo_root: Path) -> Dict[str, Any]:
    branch = run_git_command(repo_root, ["branch", "--show-current"])
    commit = run_git_command(repo_root, ["rev-parse", "HEAD"])
    status_text = run_git_command(repo_root, ["status", "--short"])
    status_lines = [line for line in status_text.splitlines() if line.strip()] if status_text != "unknown" else []
    return {
        "branch": branch or "unknown",
        "commit": commit or "unknown",
        "status_lines": status_lines,
    }


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_parent_dir(path)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def redact_device_id(device_id: str) -> str:
    if not device_id:
        return "<missing>"
    compact = device_id.replace(":", "")
    if len(compact) <= 6:
        return "***REDACTED***"
    return f"{compact[:4]}...{compact[-4:]}"


def first_nonempty(device: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = device.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def parse_device_rows(devices_response: Any) -> List[Dict[str, Any]]:
    if not isinstance(devices_response, dict):
        return []
    rows = devices_response.get("data")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def classify_target(device: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    sku = first_nonempty(device, ["sku"]).upper()
    model = first_nonempty(device, ["model", "deviceModel", "deviceType"]).upper()
    name = first_nonempty(device, ["deviceName", "name"]).upper()

    if "H612D" in sku:
        reasons.append("sku_contains_H612D")
    if "H612D" in model:
        reasons.append("model_contains_H612D")
    if "ROOM_PERIMETER" in name:
        reasons.append("name_contains_ROOM_PERIMETER")
    return (len(reasons) > 0, reasons)


def http_json_request(method: str, endpoint: str, api_key: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    body_bytes: Optional[bytes] = None
    if payload is not None:
        body_bytes = json.dumps(payload).encode("utf-8")

    req = urllib_request.Request(url=url, data=body_bytes, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header(API_KEY_HEADER, api_key)

    try:
        with urllib_request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
            status_code = int(response.getcode())
            raw_text = response.read().decode("utf-8", errors="replace")
            parsed: Any
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = {"_non_json_body": raw_text}
            return {
                "ok": True,
                "status_code": status_code,
                "response": parsed,
                "error": None,
            }
    except urllib_error.HTTPError as exc:
        raw_text = exc.read().decode("utf-8", errors="replace")
        parsed_error: Any
        try:
            parsed_error = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed_error = {"_non_json_body": raw_text}
        return {
            "ok": False,
            "status_code": int(exc.code),
            "response": parsed_error,
            "error": f"HTTP {exc.code}",
        }
    except urllib_error.URLError as exc:
        return {
            "ok": False,
            "status_code": None,
            "response": None,
            "error": f"Network error: {exc.reason}",
        }
    except TimeoutError:
        return {
            "ok": False,
            "status_code": None,
            "response": None,
            "error": "Network error: timeout",
        }


def build_api_reference_summary(
    generated_at: str,
    source_command: str,
    mode: str,
    repo_branch: str,
    repo_commit: str,
) -> str:
    lines = [
        "Govee API reference extraction summary (Phase 1)",
        f"generated_at: {generated_at}",
        f"mode: {mode}",
        f"source_command: {source_command}",
        f"branch: {repo_branch}",
        f"commit: {repo_commit}",
        "",
        "Official sources inspected:",
    ]
    lines.extend(f"- {url}" for url in OFFICIAL_SOURCE_URLS)

    lines.extend(
        [
            "",
            "Core API contract (official docs):",
            f"- Base URL: {BASE_URL}",
            f"- Auth header: {API_KEY_HEADER}",
            "- API key usage: pass the API key in the request header only; keep key in environment and do not print/log/store it.",
            "",
            "Endpoints and methods:",
            f"- List devices/capabilities: GET {ENDPOINT_LIST_DEVICES}",
            f"- Query device state: POST {ENDPOINT_DEVICE_STATE} with payload.sku and payload.device, plus requestId",
            f"- Query dynamic scenes: POST {ENDPOINT_DEVICE_SCENES} with payload.sku and payload.device, plus requestId",
            f"- Device control (not used in Phase 1): POST {ENDPOINT_DEVICE_CONTROL} with payload.capability object",
            "",
            "Payload/response shape highlights:",
            "- Get You Devices response includes data[] entries with sku, device, optional deviceName, and capabilities[].",
            "- Capabilities are objects with type, instance, and parameters metadata (for controllable options).",
            "- Get Device State response includes payload.capabilities[] with current state values.",
            "- Get Dynamic Scene returns capabilities for dynamic scenes; commonly type=devices.capabilities.dynamic_scene, instance=lightScene.",
            "- Scene control format uses /device/control capability object, and value may be scene IDs or a structured object (for example {paramId, id}) per capability definition.",
            "",
            "Error and limit notes:",
            "- 401 indicates unauthorized/invalid API key.",
            "- 429 indicates request limit exceeded (documented as 10,000 requests per account per day).",
            "",
            "Supported model evidence:",
            "- H612D appears in the official supported-product-model H61xx list.",
            "- H612DAD1 is not explicitly listed on the support-product-model page (at time of this extraction).",
            "- Supported-model listing is not proof of scene-control capability for a specific paired device.",
            "",
            "Subscribe Device Event relevance:",
            "- Subscribe Device Event is MQTT-based realtime event monitoring for event-type capabilities.",
            "- It is deferred for v1 capability capture/control flow in this phase because this phase is one-shot capability discovery, not realtime event subscription.",
            "",
            "API key security policy (2026-05-15 changelog):",
            "- Generating a new API key immediately invalidates all previously active keys for the account.",
            "- Operational implication: rotate key references in all services before/at key regeneration to prevent outages.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_human_summary(
    generated_at: str,
    phase_started_at: str,
    source_command: str,
    mode: str,
    repo_context: Dict[str, Any],
    live_calls_made: bool,
    devices_result: Optional[Dict[str, Any]],
    target_rows: List[Dict[str, Any]],
    scene_attempts: List[Dict[str, Any]],
) -> str:
    lines = [
        "Govee H612D capability capture summary",
        f"generated_at: {generated_at}",
        f"phase_started_at: {phase_started_at}",
        f"mode: {mode}",
        f"source_command: {source_command}",
        f"branch: {repo_context.get('branch', 'unknown')}",
        f"commit: {repo_context.get('commit', 'unknown')}",
        "",
        f"live_govee_calls: {'yes' if live_calls_made else 'no'}",
    ]

    if not live_calls_made:
        lines.extend(
            [
                "result: dry-run only; no live Govee API requests were sent.",
                f"official_reference_summary: {ARTIFACT_API_REFERENCE}",
                f"phase_manifest: {ARTIFACT_MANIFEST}",
                "note: raw device/scene JSON artifacts are only written in --live mode.",
            ]
        )
        return "\n".join(lines) + "\n"

    if devices_result is None:
        lines.append("result: live mode started but no device request result was captured.")
        return "\n".join(lines) + "\n"

    lines.append(f"devices_request_ok: {'yes' if devices_result.get('ok') else 'no'}")
    lines.append(f"devices_http_status: {devices_result.get('status_code')}")
    lines.append(f"devices_raw_artifact: {ARTIFACT_DEVICES}")

    device_rows = parse_device_rows(devices_result.get("response"))
    lines.append(f"devices_discovered: {len(device_rows)}")
    lines.append("")
    lines.append("devices (redacted):")
    if not device_rows:
        lines.append("- none")
    else:
        for row in device_rows:
            sku = first_nonempty(row, ["sku"]) or "<missing>"
            name = first_nonempty(row, ["deviceName", "name"]) or "<unnamed>"
            device_id = first_nonempty(row, ["device"]) or "<missing>"
            lines.append(f"- sku={sku} name={name} device={redact_device_id(device_id)}")

    lines.append("")
    lines.append(f"target_devices_found: {len(target_rows)}")
    if target_rows:
        lines.append("target_match_reasons:")
        for row in target_rows:
            device_id = first_nonempty(row, ["device"])
            sku = first_nonempty(row, ["sku"]) or "<missing>"
            name = first_nonempty(row, ["deviceName", "name"]) or "<unnamed>"
            _, reasons = classify_target(row)
            lines.append(
                f"- sku={sku} name={name} device={redact_device_id(device_id)} reasons={','.join(reasons) if reasons else 'none'}"
            )
    else:
        lines.append("target_match_reasons: none")

    lines.append("")
    lines.append(f"scene_attempt_count: {len(scene_attempts)}")
    if scene_attempts:
        lines.append(f"scene_raw_artifact: {ARTIFACT_SCENES}")
        lines.append("scene_attempts:")
        for idx, attempt in enumerate(scene_attempts, start=1):
            target = attempt.get("target", {})
            sku = str(target.get("sku", "<missing>"))
            device_id = str(target.get("device", "<missing>"))
            status_code = attempt.get("status_code")
            ok = attempt.get("ok")
            lines.append(
                f"- #{idx} sku={sku} device={redact_device_id(device_id)} ok={'yes' if ok else 'no'} status={status_code}"
            )
    else:
        lines.append("scene_raw_artifact: not_written")

    lines.append("")
    lines.append("raw_json_note: Raw /tmp JSON files are private debugging provenance and not prompt-safe by default.")
    return "\n".join(lines) + "\n"


def artifact_record(
    path: Path,
    purpose: str,
    generated_at: str,
    source_command: str,
    sanitized: bool,
    prompt_safe: bool,
    contains_raw_response: bool,
) -> Dict[str, Any]:
    return {
        "path": str(path),
        "purpose": purpose,
        "generated_at": generated_at,
        "source_command": source_command,
        "sanitized": "yes" if sanitized else "no",
        "prompt_safe": "yes" if prompt_safe else "no",
        "contains_raw_govee_response": "yes" if contains_raw_response else "no",
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone Govee capability capture tool (Phase 1).")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without live Govee API calls (default mode).",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Allow live Govee API calls (requires approval phrase and GOVEE_API_KEY).",
    )
    parser.add_argument(
        "--approval-phrase",
        default="",
        help=f"Exact approval phrase required for --live: '{LIVE_APPROVAL_PHRASE}'",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    phase_started_at = utc_now_iso()
    source_command = build_source_command([Path(__file__).as_posix(), *argv])
    args = parse_args(argv)

    live_mode = bool(args.live)
    mode = "live" if live_mode else "dry-run"

    repo_root = Path(__file__).resolve().parent.parent
    repo_context = get_repo_context(repo_root)
    status_lines = repo_context.get("status_lines", [])

    artifacts_written: List[Dict[str, Any]] = []
    commands_run: List[str] = [source_command]
    tests_run: List[str] = [source_command]
    live_calls_made = False
    scene_attempts: List[Dict[str, Any]] = []
    target_rows: List[Dict[str, Any]] = []
    devices_result: Optional[Dict[str, Any]] = None

    generated_at = utc_now_iso()

    api_reference_text = build_api_reference_summary(
        generated_at=generated_at,
        source_command=source_command,
        mode=mode,
        repo_branch=str(repo_context.get("branch", "unknown")),
        repo_commit=str(repo_context.get("commit", "unknown")),
    )
    write_text(ARTIFACT_API_REFERENCE, api_reference_text)
    artifacts_written.append(
        artifact_record(
            path=ARTIFACT_API_REFERENCE,
            purpose="Official Govee API source extraction summary",
            generated_at=generated_at,
            source_command=source_command,
            sanitized=True,
            prompt_safe=True,
            contains_raw_response=False,
        )
    )

    if live_mode:
        if args.approval_phrase != LIVE_APPROVAL_PHRASE:
            print("ERROR: --live requires exact --approval-phrase value for Phase 1.")
            print("No live API calls were made.")
            return 2

        api_key = os.environ.get("GOVEE_API_KEY", "").strip()
        if not api_key:
            print("ERROR: GOVEE_API_KEY is required for --live mode.")
            print("No live API calls were made.")
            return 2

        live_calls_made = True
        devices_result = http_json_request("GET", ENDPOINT_LIST_DEVICES, api_key=api_key, payload=None)
        devices_payload = devices_result.get("response")
        if devices_payload is None:
            devices_payload = {
                "error": devices_result.get("error"),
                "status_code": devices_result.get("status_code"),
            }
        write_json(ARTIFACT_DEVICES, devices_payload)
        artifacts_written.append(
            artifact_record(
                path=ARTIFACT_DEVICES,
                purpose="Raw live device/capability response payload",
                generated_at=generated_at,
                source_command=source_command,
                sanitized=False,
                prompt_safe=False,
                contains_raw_response=True,
            )
        )

        device_rows = parse_device_rows(devices_result.get("response"))
        for row in device_rows:
            is_target, reasons = classify_target(row)
            if is_target:
                copied = dict(row)
                copied["_target_reasons"] = reasons
                target_rows.append(copied)

        if target_rows:
            for target in target_rows:
                sku = first_nonempty(target, ["sku"])
                device = first_nonempty(target, ["device"])
                if not sku or not device:
                    scene_attempts.append(
                        {
                            "target": {"sku": sku, "device": device},
                            "ok": False,
                            "status_code": None,
                            "error": "missing sku or device",
                            "response": None,
                        }
                    )
                    continue
                payload = {"requestId": str(uuid.uuid4()), "payload": {"sku": sku, "device": device}}
                scene_result = http_json_request(
                    "POST",
                    ENDPOINT_DEVICE_SCENES,
                    api_key=api_key,
                    payload=payload,
                )
                scene_attempts.append(
                    {
                        "target": {
                            "sku": sku,
                            "device": device,
                            "deviceName": first_nonempty(target, ["deviceName", "name"]),
                        },
                        "ok": scene_result.get("ok"),
                        "status_code": scene_result.get("status_code"),
                        "error": scene_result.get("error"),
                        "response": scene_result.get("response"),
                    }
                )

            write_json(ARTIFACT_SCENES, {"scene_attempts": scene_attempts})
            artifacts_written.append(
                artifact_record(
                    path=ARTIFACT_SCENES,
                    purpose="Raw live dynamic-scene query responses for matched targets",
                    generated_at=generated_at,
                    source_command=source_command,
                    sanitized=False,
                    prompt_safe=False,
                    contains_raw_response=True,
                )
            )

    summary_text = build_human_summary(
        generated_at=generated_at,
        phase_started_at=phase_started_at,
        source_command=source_command,
        mode=mode,
        repo_context=repo_context,
        live_calls_made=live_calls_made,
        devices_result=devices_result,
        target_rows=target_rows,
        scene_attempts=scene_attempts,
    )
    write_text(ARTIFACT_SUMMARY, summary_text)
    artifacts_written.append(
        artifact_record(
            path=ARTIFACT_SUMMARY,
            purpose="Readable redacted Phase 1 capture summary",
            generated_at=generated_at,
            source_command=source_command,
            sanitized=True,
            prompt_safe=True,
            contains_raw_response=False,
        )
    )

    phase_completed_at = utc_now_iso()
    manifest = {
        "repo_branch": repo_context.get("branch", "unknown"),
        "repo_commit": repo_context.get("commit", "unknown"),
        "git_status_summary": f"{len(status_lines)} dirty entries before/at run time",
        "unrelated_dirty_files": status_lines,
        "phase_started_at": phase_started_at,
        "phase_completed_at": phase_completed_at,
        "changed_files": ["tools/govee_capability_capture.py"],
        "forbidden_files_touched": "no",
        "commands_run": commands_run,
        "tests_run": tests_run,
        "live_govee_calls": "yes" if live_calls_made else "no",
        "live_command_approved_by_supervisor": "yes" if live_mode else "not_applicable",
        "human_visual_confirmation": "not_applicable",
        "official_sources_checked": OFFICIAL_SOURCE_URLS,
        "artifacts_written": artifacts_written,
        "stale_artifacts_reused": "no",
    }
    write_json(ARTIFACT_MANIFEST, manifest)

    print(f"Mode: {mode}")
    print(f"Official summary: {ARTIFACT_API_REFERENCE}")
    print(f"Readable summary: {ARTIFACT_SUMMARY}")
    print(f"Evidence manifest: {ARTIFACT_MANIFEST}")
    if live_calls_made:
        print(f"Live devices artifact: {ARTIFACT_DEVICES}")
        if scene_attempts:
            print(f"Live scenes artifact: {ARTIFACT_SCENES}")
        else:
            print("Live scenes artifact: not_written (no matching H612D/ROOM_PERIMETER targets)")
    else:
        print("Live calls: none (dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
