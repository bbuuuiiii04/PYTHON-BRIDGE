from __future__ import annotations

import argparse
import difflib
import json
import logging
import mimetypes
import tempfile
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from urllib.parse import urlparse

import mido

from ..laser_config import LaserConfigResult, load_laser_director_config
from .laser_config_ops import (
    _DEFAULT_CONFIG_PATH,
    _DEFAULT_PERSONALITY,
    _default_pad_meta,
    _ensure_core_fields,
    _ensure_house_personality,
    _ensure_pad_meta,
    _ensure_personality_exists,
    _ensure_scene_baselines,
    apply_mapping,
    find_duplicate_notes_keyed,
    find_soft_duplicate_notes,
    load_or_create_config,
    save_config_atomically,
    update_role_bank_cooldown,
    validate_config_data,
    verify_mappings_runtime,
)

_ASSETS_DIR = Path(__file__).resolve().parent / "laser_pad_assets"


class LaserPadService:
    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH) -> None:
        self._config_path = Path(config_path)
        self._lock = Lock()
        self._draft = load_or_create_config(self._config_path)

    @property
    def config_path(self) -> Path:
        return self._config_path

    def _load_config_result(self, config: dict[str, Any]) -> LaserConfigResult:
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as fp:
            json.dump(config, fp, indent=2, sort_keys=True)
            fp.write("\n")
            temp_path = Path(fp.name)
        try:
            return load_laser_director_config(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

    def _duplicate_refs(self, refs: list[tuple[str, str, str]]) -> list[dict[str, str]]:
        return [
            {
                "personality": str(personality),
                "role": str(role),
                "scene_name": str(scene_name),
            }
            for personality, role, scene_name in refs
        ]

    def _validate_patch_payload(self, patch: dict[str, Any]) -> None:
        for key, value in patch.items():
            if key == "_pad_meta":
                if not isinstance(value, dict):
                    raise ValueError("_pad_meta must be an object")
                if "banks" in value and not isinstance(value.get("banks"), list):
                    raise ValueError("_pad_meta.banks must be a list")
            if isinstance(value, dict):
                self._validate_patch_payload(value)

    def get_config_payload(self) -> dict[str, Any]:
        with self._lock:
            config = json.loads(json.dumps(self._draft))
        loader_result = self._load_config_result(config)
        errors, warnings = validate_config_data(config, loader_result=loader_result)
        hard_dupes = [
            {
                "channel": int(channel),
                "note": int(note),
                "refs": self._duplicate_refs(refs),
            }
            for (channel, note), refs in find_duplicate_notes_keyed(config, by="channel_note")
        ]
        soft_dupes = [
            {
                "note": int(note),
                "refs": self._duplicate_refs(refs),
            }
            for note, refs in find_soft_duplicate_notes(config)
        ]
        return {
            "config": config,
            "errors": errors,
            "warnings": warnings,
            "hard_duplicates": hard_dupes,
            "soft_duplicates": soft_dupes,
        }

    def _deep_merge(self, target: dict[str, Any], patch: dict[str, Any]) -> None:
        for key, value in patch.items():
            if value is None:
                target.pop(key, None)
            elif isinstance(value, dict) and isinstance(target.get(key), dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value

    def _apply_mapping_patch(self, payload: dict[str, Any]) -> str:
        personality = str(payload.get("personality", "")).strip()
        role = str(payload.get("role", "")).strip()
        if not personality or not role:
            raise ValueError("mapping patch requires personality and role")
        note = int(payload.get("note", 0))
        channel = int(payload.get("channel", 1))
        velocity = int(payload.get("velocity", 127))
        behavior = payload.get("behavior")
        hold_ms = payload.get("hold_ms")
        hold_beats = payload.get("hold_beats")
        cooldown_beats = payload.get("cooldown_beats")
        safety_class = payload.get("safety_class")
        immediate = payload.get("immediate")

        scene_name = apply_mapping(
            self._draft,
            personality=personality,
            role=role,
            note=note,
            channel=channel,
            velocity=velocity,
            replace_primary=bool(payload.get("replace_primary", False)),
            add_to_bank=bool(payload.get("add_to_bank", False)),
            behavior=str(behavior) if isinstance(behavior, str) and behavior else None,
            hold_ms=int(hold_ms) if hold_ms is not None else None,
            hold_beats=float(hold_beats) if hold_beats is not None else None,
            cooldown_beats=float(cooldown_beats) if cooldown_beats is not None else None,
            safety_class=str(safety_class) if isinstance(safety_class, str) and safety_class else None,
            immediate=bool(immediate) if immediate is not None else None,
        )
        label = payload.get("label")
        if isinstance(label, str):
            self._draft.setdefault("scenes", {}).setdefault(scene_name, {})["label"] = label
        return scene_name

    def apply_draft_patch(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            patch = payload.get("patch")
            if isinstance(patch, dict):
                self._validate_patch_payload(patch)
                candidate = json.loads(json.dumps(self._draft))
                self._deep_merge(candidate, patch)
                self._draft = candidate
            mapping = payload.get("mapping")
            mapped_scene = ""
            if isinstance(mapping, dict):
                mapped_scene = self._apply_mapping_patch(mapping)
            config = json.loads(json.dumps(self._draft))
        loader_result = self._load_config_result(config)
        errors, warnings = validate_config_data(config, loader_result=loader_result)
        result: dict[str, Any] = {
            "ok": True,
            "errors": errors,
            "warnings": warnings,
        }
        if mapped_scene:
            result["scene_name"] = mapped_scene
        return result

    def discard_draft(self) -> dict[str, Any]:
        with self._lock:
            self._draft = load_or_create_config(self._config_path)
        return self.get_config_payload()

    def commit_draft(self) -> dict[str, Any]:
        with self._lock:
            config = json.loads(json.dumps(self._draft))

        loader_result = self._load_config_result(config)
        errors, warnings = validate_config_data(config, loader_result=loader_result)
        if errors:
            return {
                "ok": False,
                "errors": errors,
                "warnings": warnings,
            }

        with self._lock:
            config_to_save = json.loads(json.dumps(self._draft))
            loader_result_to_save = self._load_config_result(config_to_save)
            save_errors, save_warnings = validate_config_data(config_to_save, loader_result=loader_result_to_save)
            if save_errors:
                return {
                    "ok": False,
                    "errors": save_errors,
                    "warnings": save_warnings,
                }
            backup = save_config_atomically(config_to_save, path=self._config_path)
        return {
            "ok": True,
            "backup_path": str(backup) if backup else "",
            "errors": save_errors,
            "warnings": save_warnings,
        }

    @staticmethod
    def _normalize_personality_name(raw: Any) -> str:
        name = str(raw or "").strip().lower()
        if not name:
            raise ValueError("personality name is required")
        return name

    def create_personality(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = self._normalize_personality_name(payload.get("name"))
        with self._lock:
            personalities = self._draft.setdefault("personalities", {})
            if name in personalities:
                raise ValueError(f"personality '{name}' already exists")
            _ensure_personality_exists(self._draft, name)
        return {"ok": True, "name": name}

    def delete_personality(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = self._normalize_personality_name(payload.get("name"))
        with self._lock:
            personalities = self._draft.setdefault("personalities", {})
            if name not in personalities:
                raise ValueError(f"personality '{name}' does not exist")
            if len(personalities) <= 1:
                raise ValueError("cannot delete the last remaining personality")
            personalities.pop(name)
            new_default = str(self._draft.get("default_personality", ""))
            if new_default == name:
                new_default = sorted(personalities.keys())[0]
                self._draft["default_personality"] = new_default
            pad_meta = self._draft.get("_pad_meta")
            if isinstance(pad_meta, dict):
                ui = pad_meta.get("ui")
                if isinstance(ui, dict) and ui.get("last_personality") == name:
                    ui["last_personality"] = new_default
        return {"ok": True, "deleted": name, "new_default": new_default}

    def duplicate_personality(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._normalize_personality_name(payload.get("source"))
        new_name = self._normalize_personality_name(payload.get("name"))
        with self._lock:
            personalities = self._draft.setdefault("personalities", {})
            if source not in personalities:
                raise ValueError(f"personality '{source}' does not exist")
            if new_name in personalities:
                raise ValueError(f"personality '{new_name}' already exists")
            source_data = personalities[source]
            personalities[new_name] = json.loads(json.dumps(source_data))
        return {"ok": True, "name": new_name, "source": source}

    def rename_personality(self, payload: dict[str, Any]) -> dict[str, Any]:
        old_name = self._normalize_personality_name(payload.get("old"))
        new_name = self._normalize_personality_name(payload.get("new"))
        with self._lock:
            personalities = self._draft.setdefault("personalities", {})
            if old_name not in personalities:
                raise ValueError(f"personality '{old_name}' does not exist")
            if old_name == new_name:
                return {"ok": True, "name": new_name, "unchanged": True}
            if new_name in personalities:
                raise ValueError(f"personality '{new_name}' already exists")
            personalities[new_name] = personalities.pop(old_name)
            if str(self._draft.get("default_personality", "")) == old_name:
                self._draft["default_personality"] = new_name
            pad_meta = self._draft.get("_pad_meta")
            if isinstance(pad_meta, dict):
                ui = pad_meta.get("ui")
                if isinstance(ui, dict) and ui.get("last_personality") == old_name:
                    ui["last_personality"] = new_name
        return {"ok": True, "name": new_name}

    def reset_banks_to_default(self) -> dict[str, Any]:
        with self._lock:
            default_personality = str(
                self._draft.get("default_personality", _DEFAULT_PERSONALITY)
            )
            defaults = _default_pad_meta(default_personality)
            pad_meta = self._draft.setdefault("_pad_meta", {})
            if not isinstance(pad_meta, dict):
                pad_meta = {}
                self._draft["_pad_meta"] = pad_meta
            pad_meta["banks"] = defaults["banks"]
            if not isinstance(pad_meta.get("ui"), dict):
                pad_meta["ui"] = defaults["ui"]
            pad_meta.setdefault("schema_version", defaults["schema_version"])
        return {"ok": True}

    def apply_role_cooldown(self, payload: dict[str, Any]) -> dict[str, Any]:
        personality = str(payload.get("personality", "")).strip()
        role = str(payload.get("role", "")).strip()
        if not personality or not role:
            raise ValueError("personality and role are required")
        try:
            cooldown_beats = float(payload.get("cooldown_beats"))
        except (TypeError, ValueError) as exc:
            raise ValueError("cooldown_beats must be a number") from exc
        with self._lock:
            update_role_bank_cooldown(
                self._draft,
                personality=personality,
                role=role,
                cooldown_beats=cooldown_beats,
            )
            config = json.loads(json.dumps(self._draft))
        loader_result = self._load_config_result(config)
        errors, warnings = validate_config_data(config, loader_result=loader_result)
        return {
            "ok": True,
            "errors": errors,
            "warnings": warnings,
        }

    def validate_draft(self) -> dict[str, Any]:
        with self._lock:
            config = json.loads(json.dumps(self._draft))
        loader_result = self._load_config_result(config)
        errors, warnings = validate_config_data(config, loader_result=loader_result)
        return {
            "errors": errors,
            "warnings": warnings,
        }

    def verify_draft(self) -> dict[str, Any]:
        with self._lock:
            config = json.loads(json.dumps(self._draft))
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as fp:
            json.dump(config, fp, indent=2, sort_keys=True)
            fp.write("\n")
            temp_path = Path(fp.name)
        try:
            checks = verify_mappings_runtime(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return {
            "checks": [
                {
                    "name": name,
                    "ok": ok,
                    "detail": detail,
                }
                for name, ok, detail in checks
            ]
        }

    def _history_path(self, name: str) -> Path:
        candidate = Path(name)
        if candidate.name != name:
            raise ValueError("invalid history item")
        expected_prefix = f"{self._config_path.name}.bak-"
        if not name.startswith(expected_prefix):
            raise ValueError("history entry must be a config backup")
        path = (self._config_path.parent / name).resolve()
        config_parent = self._config_path.parent.resolve()
        if not path.is_relative_to(config_parent):
            raise ValueError("invalid history path")
        return path

    def list_history(self) -> list[dict[str, Any]]:
        pattern = f"{self._config_path.name}.bak-*"
        stats: list[tuple[Path, Any]] = []
        for path in self._config_path.parent.glob(pattern):
            try:
                stat = path.stat()
            except OSError as exc:
                logging.warning("list_history: skipping %s: %s", path.name, exc)
                continue
            stats.append((path, stat))
        stats.sort(key=lambda item: item[1].st_mtime, reverse=True)
        entries = [
            {
                "name": path.name,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
            for path, stat in stats
        ]
        return entries

    def history_diff(self, name: str) -> str:
        history_path = self._history_path(name)
        if not history_path.exists():
            raise FileNotFoundError("history entry not found")
        history_text = history_path.read_text(encoding="utf-8").splitlines(keepends=True)
        with self._lock:
            current_text = (
                json.dumps(self._draft, indent=2, sort_keys=True) + "\n"
            ).splitlines(keepends=True)
        diff = difflib.unified_diff(
            history_text,
            current_text,
            fromfile=history_path.name,
            tofile="draft",
        )
        return "".join(diff)

    def restore_history(self, name: str) -> dict[str, Any]:
        history_path = self._history_path(name)
        if not history_path.exists():
            raise FileNotFoundError("history entry not found")
        restored = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(restored, dict):
            raise ValueError("backup JSON root must be an object")
        _ensure_core_fields(restored)
        _ensure_scene_baselines(restored)
        _ensure_house_personality(restored)
        _ensure_pad_meta(restored)
        with self._lock:
            self._draft = restored
        return self.get_config_payload()

    def get_midi_ports(self) -> list[str]:
        return list(mido.get_output_names())

    def _test_bpm(self, payload: dict[str, Any]) -> float:
        raw = payload.get("bpm")
        if raw is not None:
            return max(1.0, float(raw))
        with self._lock:
            bpm = (
                self._draft.get("_pad_meta", {})
                .get("ui", {})
                .get("bpm_for_test_fire", 128)
            )
        return max(1.0, float(bpm))

    def _resolve_duration_ms(self, payload: dict[str, Any]) -> int:
        behavior = str(payload.get("behavior", "pulse"))
        if behavior == "hold_beats":
            hold_beats = float(payload.get("hold_beats", 0.0))
            bpm = self._test_bpm(payload)
            hold_ms = int(hold_beats * 60000.0 / bpm)
            return max(10, min(30000, hold_ms))
        if behavior == "hold_ms":
            hold_ms = int(payload.get("hold_ms", 0))
            return max(10, min(30000, hold_ms))
        duration_ms = int(payload.get("duration_ms", 100))
        return max(10, min(30000, duration_ms))

    def test_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        note = int(payload.get("note", 0))
        channel = int(payload.get("channel", 1))
        velocity = int(payload.get("velocity", 127))
        if not (0 <= note <= 127):
            raise ValueError("note must be in 0-127")
        if not (1 <= channel <= 16):
            raise ValueError("channel must be in 1-16")
        if not (0 <= velocity <= 127):
            raise ValueError("velocity must be in 0-127")

        duration_ms = self._resolve_duration_ms(payload)
        with self._lock:
            dry_run = bool(self._draft.get("dry_run", True))
            midi_port_name = str(self._draft.get("midi_output_port", "")).strip()

        if dry_run:
            return {"ok": True, "dry_run": True, "sent_ms": duration_ms}

        if not midi_port_name:
            names = self.get_midi_ports()
            if not names:
                raise RuntimeError("No MIDI output ports available.")
            midi_port_name = names[0]

        msg_channel = channel - 1
        with mido.open_output(midi_port_name) as out:
            out.send(
                mido.Message(
                    "note_on",
                    note=note,
                    velocity=velocity,
                    channel=msg_channel,
                )
            )
            time.sleep(duration_ms / 1000.0)
            out.send(
                mido.Message(
                    "note_off",
                    note=note,
                    velocity=0,
                    channel=msg_channel,
                )
            )
        return {"ok": True, "dry_run": False, "sent_ms": duration_ms}


class _LaserPadHandler(BaseHTTPRequestHandler):
    service: LaserPadService

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(path))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(_ASSETS_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            rel = parsed.path.removeprefix("/static/")
            target = (_ASSETS_DIR / rel).resolve()
            assets_root = _ASSETS_DIR.resolve()
            if not target.is_relative_to(assets_root):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            self._serve_file(target)
            return
        if parsed.path == "/api/config":
            self._send_json(HTTPStatus.OK, self.service.get_config_payload())
            return
        if parsed.path == "/api/midi_ports":
            self._send_json(HTTPStatus.OK, {"ports": self.service.get_midi_ports()})
            return
        if parsed.path == "/api/history":
            try:
                self._send_json(HTTPStatus.OK, {"items": self.service.list_history()})
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        if parsed.path.startswith("/api/history/") and parsed.path.endswith("/diff"):
            try:
                name = parsed.path[len("/api/history/") : -len("/diff")].strip("/")
                diff_text = self.service.history_diff(name)
                self._send_json(HTTPStatus.OK, {"name": name, "diff": diff_text})
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if (
            parsed.path
            not in {
                "/api/test_note",
                "/api/draft",
                "/api/commit",
                "/api/discard",
                "/api/validate",
                "/api/verify",
                "/api/role_cooldown",
                "/api/banks/reset",
                "/api/personality/create",
                "/api/personality/rename",
                "/api/personality/duplicate",
                "/api/personality/delete",
            }
            and not parsed.path.startswith("/api/history/")
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            if parsed.path == "/api/test_note":
                result = self.service.test_note(payload)
            elif parsed.path == "/api/draft":
                result = self.service.apply_draft_patch(payload)
            elif parsed.path == "/api/commit":
                result = self.service.commit_draft()
            elif parsed.path == "/api/discard":
                result = self.service.discard_draft()
            elif parsed.path == "/api/validate":
                result = self.service.validate_draft()
            elif parsed.path == "/api/verify":
                result = self.service.verify_draft()
            elif parsed.path == "/api/role_cooldown":
                result = self.service.apply_role_cooldown(payload)
            elif parsed.path == "/api/banks/reset":
                result = self.service.reset_banks_to_default()
            elif parsed.path == "/api/personality/create":
                result = self.service.create_personality(payload)
            elif parsed.path == "/api/personality/rename":
                result = self.service.rename_personality(payload)
            elif parsed.path == "/api/personality/duplicate":
                result = self.service.duplicate_personality(payload)
            elif parsed.path == "/api/personality/delete":
                result = self.service.delete_personality(payload)
            else:
                if parsed.path.startswith("/api/history/") and parsed.path.endswith("/restore"):
                    name = parsed.path[len("/api/history/") : -len("/restore")].strip("/")
                    result = self.service.restore_history(name)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
            self._send_json(HTTPStatus.OK, result)
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def build_handler(service: LaserPadService) -> type[_LaserPadHandler]:
    class Handler(_LaserPadHandler):
        pass

    Handler.service = service
    return Handler


def run_server(
    *,
    host: str = "0.0.0.0",
    port: int = 8765,
    config_path: Path = _DEFAULT_CONFIG_PATH,
) -> None:
    service = LaserPadService(config_path=config_path)
    handler = build_handler(service)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Laser Pad running at http://{host}:{port}")
    server.serve_forever()


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Laser Pad web server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="Path to laser_director.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    run_server(host=args.host, port=args.port, config_path=Path(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
