from __future__ import annotations

import argparse
import copy
import difflib
import json
import logging
import mimetypes
import re
import shutil
import sys
import tempfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import urlparse

from ..govee_frame_renderer import REALTIME_EFFECT_NAMES, REALTIME_EFFECT_PARAM_KEYS, SLOT_EFFECTS
from ..led_color_engine import LedColorEngine
from ..led_config import LEDConfigResult, _resolve_path, load_led_look_director_config_from_dict
from ..led_pad_controls import controls_for, render_catalog
from ..runtime_status import STATUS_PATH
from .led_pad_lab import LabRegistry, LabRenderer, load_lab_effects
from .led_pad_playback import PadPlayback

_ASSETS_DIR = Path(__file__).resolve().parent / "led_pad_assets"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "led_look_director.json"
_IDENT_RE = re.compile(r"^[a-z0-9_]+$")
_ROLE_BANKS = ("ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility")
_VISIBLE_BANKS = ("drafts", "ambient", "groove", "buildup", "drop", "post_drop", "breakdown", "utility")
_STOP_LOOKS = frozenset({"safe_default", "blackout"})
logger = logging.getLogger("led_pad_web")


def _resolved_config_path(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    return _resolve_path(None) or _DEFAULT_CONFIG_PATH


def _draft_path_for(path: Path) -> Path:
    return path.with_name("led_look_director.draft.json")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(path.parent),
            prefix=f"{path.name}.tmp-",
        ) as fp:
            temp_path = Path(fp.name)
            json.dump(data, fp, indent=2, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def save_config_atomically(config: dict[str, Any], path: Path) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(f"{path.name}.bak-{ts}")
        suffix = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.bak-{ts}-{suffix}")
            suffix += 1
        shutil.copy2(path, backup)
    _write_json_atomic(path, config)
    return backup


def _normalized(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _default_pad_meta(config: dict[str, Any]) -> dict[str, Any]:
    palettes = list((config.get("color_engine") or {}).get("palettes", {}).keys())
    return {
        "drafts": [],
        "looks": {},
        "ui": {"bpm": 128, "test_palette": palettes[0] if palettes else "", "loop": True},
    }


def _ensure_pad_meta(config: dict[str, Any]) -> None:
    meta = config.setdefault("_pad_meta", {})
    if not isinstance(meta, dict):
        config["_pad_meta"] = meta = {}
    defaults = _default_pad_meta(config)
    for key, value in defaults.items():
        if key not in meta or not isinstance(meta.get(key), type(value)):
            meta[key] = copy.deepcopy(value)
    ui = meta.setdefault("ui", {})
    if not isinstance(ui, dict):
        meta["ui"] = ui = {}
    for key, value in defaults["ui"].items():
        ui.setdefault(key, value)
    meta.setdefault("drafts", [])
    meta.setdefault("looks", {})


def _default_bank(config: dict[str, Any]) -> dict[str, Any]:
    banks = config.setdefault("banks", {})
    if not isinstance(banks, dict):
        config["banks"] = banks = {}
    default = banks.setdefault("default", {})
    if not isinstance(default, dict):
        banks["default"] = default = {}
    for bank in _ROLE_BANKS:
        items = default.setdefault(bank, [])
        if not isinstance(items, list):
            default[bank] = []
    return default


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        name = str(item)
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _pad_lists(config: dict[str, Any]) -> dict[str, list[str]]:
    _ensure_pad_meta(config)
    default = _default_bank(config)
    lists = {bank: _dedupe(default.get(bank, [])) for bank in _ROLE_BANKS}
    lists["drafts"] = _dedupe(config["_pad_meta"].get("drafts", []))
    return lists


def _bank_for(config: dict[str, Any], name: str) -> str:
    lists = _pad_lists(config)
    for bank in ("drafts",) + _ROLE_BANKS:
        if name in lists.get(bank, []):
            return bank
    return "other"


def _remove_from_pad_banks(config: dict[str, Any], name: str) -> None:
    default = _default_bank(config)
    for bank in _ROLE_BANKS:
        default[bank] = [item for item in default.get(bank, []) if item != name]
    meta = config.setdefault("_pad_meta", {})
    meta["drafts"] = [item for item in meta.get("drafts", []) if item != name]


def _add_to_bank(config: dict[str, Any], name: str, bank: str) -> None:
    _remove_from_pad_banks(config, name)
    if bank == "drafts":
        drafts = config.setdefault("_pad_meta", {}).setdefault("drafts", [])
        drafts.append(name)
        config["_pad_meta"]["drafts"] = _dedupe(drafts)
        return
    default = _default_bank(config)
    default.setdefault(bank, []).append(name)
    default[bank] = _dedupe(default[bank])


def _drop_pair_refs(config: dict[str, Any], name: str) -> list[str]:
    refs: list[str] = []
    pairs = config.get("drop_pairs", {})
    if not isinstance(pairs, dict):
        return refs
    for drop, raw in pairs.items():
        post = raw.get("post_drop") if isinstance(raw, dict) else None
        if name == drop or name == post:
            refs.append(f"{drop}->{post}")
    return refs


class LedPadService:
    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        dry_run: bool = False,
        status_path: Path | str = STATUS_PATH,
        playback: Any | None = None,
        playback_factory: Callable[[Any], Any] | None = None,
        lab_dir: Path | str | None = None,
    ) -> None:
        self._config_path = _resolved_config_path(config_path)
        self._draft_path = _draft_path_for(self._config_path)
        self._status_path = Path(status_path)
        self._lock = Lock()
        self._draft = self._load_initial_draft()
        self._lab = LabRegistry(lab_dir or (self._config_path.parent / "led_lab"))
        self._lab_renderer = LabRenderer(self._lab.module_path)
        self._playback = playback
        if self._playback is None:
            result = self._load_config_result(self._draft)
            if not result.available or result.config is None:
                raise ValueError("; ".join(result.errors) or "LED config is not available")
            self._playback = playback_factory(result.config) if playback_factory else PadPlayback(result.config, dry_run=dry_run, renderer=self._lab_renderer)
        self._playing_name = ""
        self._last_play_editor: dict[str, Any] | None = None

    @property
    def draft_path(self) -> Path:
        return self._draft_path

    @property
    def config_path(self) -> Path:
        return self._config_path

    def shutdown(self) -> None:
        shutdown = getattr(self._playback, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def _load_initial_draft(self) -> dict[str, Any]:
        source = self._draft_path if self._draft_path.exists() else self._config_path
        if not source.exists():
            raise FileNotFoundError(f"LED config not found: {source}")
        config = _load_json(source)
        _ensure_pad_meta(config)
        _default_bank(config)
        return config

    def _persist_draft_locked(self) -> None:
        _ensure_pad_meta(self._draft)
        _write_json_atomic(self._draft_path, self._draft)

    def _load_config_result(self, config: dict[str, Any]) -> LEDConfigResult:
        return load_led_look_director_config_from_dict(config)

    def _validate(self, config: dict[str, Any]) -> tuple[list[str], list[str]]:
        result = self._load_config_result(config)
        errors = list(result.errors)
        warnings: list[str] = []
        return errors, warnings

    def _dirty_for(self, config: dict[str, Any]) -> dict[str, Any]:
        live = _load_json(self._config_path) if self._config_path.exists() else {}
        _ensure_pad_meta(live)
        _default_bank(live)
        looks = sorted(
            name
            for name in set((config.get("looks") or {}).keys()) | set((live.get("looks") or {}).keys())
            if _normalized((config.get("looks") or {}).get(name)) != _normalized((live.get("looks") or {}).get(name))
        )
        current_lists = _pad_lists(config)
        live_lists = _pad_lists(live)
        banks: dict[str, bool] = {}
        for bank in _VISIBLE_BANKS:
            members = set(current_lists.get(bank, []))
            bank_changed = current_lists.get(bank, []) != live_lists.get(bank, [])
            banks[bank] = bank_changed or any(name in members for name in looks)
        meta_current = copy.deepcopy(config.get("_pad_meta", {}))
        meta_live = copy.deepcopy(live.get("_pad_meta", {}))
        meta_current.pop("ui", None)
        meta_live.pop("ui", None)
        meta_changed = _normalized(meta_current) != _normalized(meta_live)
        global_dirty = (
            _normalized(config) != _normalized(live)
            or bool(looks)
            or meta_changed
            or any(banks.values())
        )
        return {"global": global_dirty, "banks": banks, "looks": looks}

    def _bank_payload(self, config: dict[str, Any]) -> dict[str, list[str]]:
        lists = _pad_lists(config)
        payload = {bank: lists.get(bank, []) for bank in _VISIBLE_BANKS}
        default = _default_bank(config)
        other = list(lists.get("pre_drop", []))
        for bank, values in default.items():
            if bank not in _ROLE_BANKS:
                if isinstance(values, list):
                    other.extend(str(item) for item in values)
        payload["other"] = _dedupe(other)
        return payload

    def _guard_mutable(self, config: dict[str, Any], name: str, *, move: bool = False, delete: bool = False) -> None:
        if name in {str(config.get(key, "")) for key in _STOP_LOOKS}:
            action = "move" if move else "delete" if delete else "change"
            raise ValueError(f"{name} is {action}-protected")
        refs = _drop_pair_refs(config, name)
        if refs and delete:
            raise ValueError(f"{name} is referenced by drop pair {', '.join(refs)}")

    def _ensure_unique_bank_locked(self, config: dict[str, Any]) -> None:
        lists = _pad_lists(config)
        counts: dict[str, int] = {}
        for values in lists.values():
            for name in values:
                counts[name] = counts.get(name, 0) + 1
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"look appears in more than one LED Pad bank: {', '.join(duplicates)}")

    def get_config_payload(self) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._draft)
        errors, warnings = self._validate(config)
        return {
            "ok": True,
            "config": config,
            "errors": errors,
            "warnings": warnings,
            "dirty": self._dirty_for(config),
            "banks": self._bank_payload(config),
        }

    def get_renders(self) -> dict[str, Any]:
        renders = []
        for item in render_catalog():
            render = dict(item)
            render["controls"] = controls_for(str(item["name"]))
            renders.append(render)
        return {"ok": True, "renders": renders}

    def get_palettes(self) -> dict[str, Any]:
        with self._lock:
            palettes = list(((self._draft.get("color_engine") or {}).get("palettes") or {}).keys())
        return {
            "ok": True,
            "palettes": palettes,
            "warnings": [] if palettes else ["color_engine.palettes is empty or unavailable"],
        }

    def _validate_name(self, name: str, *, new: bool = False, config: dict[str, Any]) -> None:
        if not name or not _IDENT_RE.fullmatch(name):
            raise ValueError("look name must match [a-z0-9_]+")
        if new and name in (config.get("looks") or {}):
            raise ValueError(f"look already exists: {name}")

    def _candidate_save_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        look_patch = payload.get("look")
        params = payload.get("params")
        if not isinstance(look_patch, dict):
            raise ValueError("look/save requires look object")
        if not isinstance(params, dict):
            params = {}
        candidate = copy.deepcopy(self._draft)
        self._validate_name(name, config=candidate)
        scene_ref = str(look_patch.get("scene_ref") or (candidate.get("looks", {}).get(name) or {}).get("scene_ref") or "")
        allowed = REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, frozenset())
        unknown = sorted(str(key) for key in params if str(key) not in allowed)
        if unknown:
            raise ValueError(f"unknown params for {scene_ref}: {', '.join(unknown)}")
        looks = candidate.setdefault("looks", {})
        current = copy.deepcopy(looks.get(name, {}))
        current.update(copy.deepcopy(look_patch))
        current["params"] = copy.deepcopy(params)
        looks[name] = current
        engine = candidate.setdefault("color_engine", {})
        if "slot_fill" in payload:
            engine.setdefault("slot_fill_strategy_by_look", {})[name] = str(payload.get("slot_fill"))
        if "mono_chance" in payload:
            engine.setdefault("slot_mono_chance_by_look", {})[name] = float(payload.get("mono_chance"))
        if "locked_palette" in payload:
            locked = engine.setdefault("locked_palette_by_look", {})
            palette_name = str(payload.get("locked_palette") or "")
            if palette_name:
                locked[name] = palette_name
            else:
                locked.pop(name, None)
        meta = candidate.setdefault("_pad_meta", {}).setdefault("looks", {})
        meta.setdefault(name, {})
        if "cue_beats" in payload:
            meta[name]["cue_beats"] = float(payload.get("cue_beats") or 0)
        self._ensure_unique_bank_locked(candidate)
        return candidate

    def save_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            candidate = self._candidate_save_look(payload)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def duplicate_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = str(payload.get("source", "")).strip()
        new_name = str(payload.get("new_name", "")).strip()
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            self._validate_name(new_name, new=True, config=candidate)
            looks = candidate.setdefault("looks", {})
            if source not in looks:
                raise ValueError(f"unknown look: {source}")
            looks[new_name] = copy.deepcopy(looks[source])
            engine = candidate.setdefault("color_engine", {})
            for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
                mapping = engine.setdefault(key, {})
                if source in mapping:
                    mapping[new_name] = copy.deepcopy(mapping[source])
            meta = candidate.setdefault("_pad_meta", {})
            meta.setdefault("looks", {})[new_name] = copy.deepcopy(meta.get("looks", {}).get(source, {}))
            _add_to_bank(candidate, new_name, "drafts")
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "name": new_name, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def move_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        bank = str(payload.get("bank", "")).strip()
        if bank not in _ROLE_BANKS + ("drafts",):
            raise ValueError("bank must be one of the LED Pad banks")
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            if name not in (candidate.get("looks") or {}):
                raise ValueError(f"unknown look: {name}")
            self._guard_mutable(candidate, name, move=True)
            _add_to_bank(candidate, name, bank)
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def delete_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            if name not in (candidate.get("looks") or {}):
                raise ValueError(f"unknown look: {name}")
            self._guard_mutable(candidate, name, delete=True)
            candidate["looks"].pop(name, None)
            _remove_from_pad_banks(candidate, name)
            engine = candidate.setdefault("color_engine", {})
            for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
                if isinstance(engine.get(key), dict):
                    engine[key].pop(name, None)
            candidate.setdefault("_pad_meta", {}).setdefault("looks", {}).pop(name, None)
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def _session(self, config: dict[str, Any]) -> dict[str, Any]:
        _ensure_pad_meta(config)
        return config["_pad_meta"]["ui"]

    def session(self, payload: dict[str, Any]) -> dict[str, Any]:
        update_after = False
        with self._lock:
            session = self._session(self._draft)
            if "bpm" in payload:
                bpm = float(payload["bpm"])
                if bpm <= 0:
                    raise ValueError("bpm must be > 0")
                session["bpm"] = bpm
                self._playback.set_bpm(bpm)
            if "test_palette" in payload:
                session["test_palette"] = str(payload["test_palette"])
                update_after = bool(self._playing_name and self._last_play_editor)
            if "loop" in payload:
                session["loop"] = bool(payload["loop"])
                self._playback.set_loop(bool(payload["loop"]))
            self._persist_draft_locked()
            out = copy.deepcopy(session)
        if update_after and self._last_play_editor:
            self.update({"name": self._playing_name, "editor": self._last_play_editor})
        return {"ok": True, "session": out}

    def _look_state(self, config: dict[str, Any], name: str, editor: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], float]:
        looks = config.get("looks") or {}
        look = copy.deepcopy(looks.get(name) or {})
        if not look:
            raise ValueError(f"unknown look: {name}")
        cue_beats = float(config.get("_pad_meta", {}).get("looks", {}).get(name, {}).get("cue_beats", 16))
        if editor:
            patch = editor.get("look")
            if isinstance(patch, dict):
                look.update(copy.deepcopy(patch))
            params = editor.get("params")
            if isinstance(params, dict):
                look["params"] = copy.deepcopy(params)
            if "cue_beats" in editor:
                cue_beats = float(editor.get("cue_beats") or cue_beats)
        params = dict(look.get("params") or {})
        return look, params, cue_beats

    def _inject_engine_colors(self, config: dict[str, Any], name: str, look: dict[str, Any], params: dict[str, Any], *, force_slot: bool = False) -> None:
        if str(look.get("color_source", "engine")) != "engine":
            return
        result = self._load_config_result(config)
        if result.config is None or result.config.color_engine is None:
            return
        session = self._session(config)
        palette = str(session.get("test_palette") or "")
        engine = LedColorEngine(result.config.color_engine, set_seed=0)
        if palette:
            engine.set_palette(palette)
        engine.lock()
        scene_ref = str(look.get("scene_ref", ""))
        role = _bank_for(config, name)
        if force_slot or scene_ref in SLOT_EFFECTS:
            params.update(engine.resolve_slot_colors(
                role=role,
                section_id="led_pad",
                cycle=0,
                look_name=name,
                color_source="engine",
            ))
            return
        multi = "color_a" in REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, ()) or "color_b" in REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, ())
        params.update(engine.resolve_color(
            role=role,
            section_id="led_pad",
            cycle=0,
            look_name=name,
            color_source="engine",
            multi=multi,
        ))

    def _overlay_editor_slot_config(self, config: dict[str, Any], name: str, editor: dict[str, Any] | None) -> dict[str, Any]:
        if not editor:
            return config
        engine = config.setdefault("color_engine", {})
        if "slot_fill" in editor:
            engine.setdefault("slot_fill_strategy_by_look", {})[name] = str(editor["slot_fill"])
        if "mono_chance" in editor:
            engine.setdefault("slot_mono_chance_by_look", {})[name] = float(editor["mono_chance"])
        if "locked_palette" in editor:
            locked = engine.setdefault("locked_palette_by_look", {})
            palette_name = str(editor.get("locked_palette") or "")
            if palette_name:
                locked[name] = palette_name
            else:
                locked.pop(name, None)
        return config

    def _play_spec(self, config: dict[str, Any], name: str, editor: dict[str, Any] | None) -> tuple[dict[str, Any], float]:
        config = self._overlay_editor_slot_config(config, name, editor)
        look, params, cue_beats = self._look_state(config, name, editor)
        scene_ref = str(look.get("scene_ref", ""))
        if scene_ref not in REALTIME_EFFECT_NAMES:
            raise ValueError("cloud scene - not previewable in the pad")
        allowed = REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, frozenset())
        unknown = sorted(str(key) for key in params if str(key) not in allowed)
        if unknown:
            raise ValueError(f"unknown params for {scene_ref}: {', '.join(unknown)}")
        self._inject_engine_colors(config, name, look, params)
        return {
            "look_name": name,
            "scene_ref": scene_ref,
            "params": params,
            "allow_strobe": bool(look.get("allow_strobe")),
            "safety_allow_strobe": bool((config.get("safety") or {}).get("allow_strobe")),
        }, cue_beats

    def lab_list(self) -> dict[str, Any]:
        return {"ok": True, "entries": self._lab.list(), "module_path": str(self._lab.module_path)}

    def lab_reload(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        result = load_lab_effects(self._lab.module_path)
        return {
            "ok": bool(result["ok"]),
            "effects": sorted(result["effects"].keys()),
            "error": result["error"],
            "traceback": result["traceback"],
            "module_path": str(self._lab.module_path),
        }

    def lab_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._lab.save(payload)

    def lab_accept(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._lab.set_status(str(payload.get("name", "")).strip(), "accepted")

    def lab_reject(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._lab.set_status(str(payload.get("name", "")).strip(), "rejected")

    def _lab_play_spec(self, config: dict[str, Any], entry: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        reload_result = self._lab_renderer.reload()
        if not reload_result["ok"]:
            raise RuntimeError(reload_result["traceback"] or reload_result["error"])
        name = str(entry["name"])
        kind = str(entry["kind"])
        effects = reload_result["effects"]
        if name not in effects:
            raise ValueError(f"lab effect not registered: {name}")
        params = copy.deepcopy(entry.get("params") or {})
        if isinstance(payload.get("params"), dict):
            params.update(copy.deepcopy(payload["params"]))
        look = {"scene_ref": LabRegistry.scene_ref(name), "color_source": "engine"}
        self._inject_engine_colors(config, LabRegistry.scene_ref(name), look, params, force_slot=(kind == "slot"))
        return {
            "look_name": LabRegistry.scene_ref(name),
            "scene_ref": LabRegistry.scene_ref(name),
            "params": params,
            "allow_strobe": False,
            "safety_allow_strobe": bool((config.get("safety") or {}).get("allow_strobe")),
        }, float(payload.get("cue_beats", entry.get("cue_beats", 16)) or 16)

    def lab_play(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        entry = self._lab.get(name)
        with self._lock:
            config = copy.deepcopy(self._draft)
            session = copy.deepcopy(self._session(config))
        ownership = self._playback.ownership()
        if ownership.get("state") == "bridge_owned":
            if not bool(payload.get("takeover")):
                return {"ok": False, "error": "ownership_required", "ownership": ownership}
            self._playback.request_takeover()
        spec, cue_beats = self._lab_play_spec(config, entry, payload)
        self._playback.set_bpm(float(session.get("bpm") or 128))
        self._playback.play(spec, cue_beats=cue_beats, loop=bool(session.get("loop", True)))
        self._playing_name = str(spec["look_name"])
        self._last_play_editor = None
        return {"ok": True, "spec": spec, "cue_beats": cue_beats, "playback": self._playback.status()}

    def play(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        editor = payload.get("editor") if isinstance(payload.get("editor"), dict) else None
        with self._lock:
            config = copy.deepcopy(self._draft)
            session = copy.deepcopy(self._session(config))
        ownership = self._playback.ownership()
        if ownership.get("state") == "bridge_owned":
            if not bool(payload.get("takeover")):
                return {"ok": False, "error": "ownership_required", "ownership": ownership}
            self._playback.request_takeover()
        spec, cue_beats = self._play_spec(config, name, editor)
        self._playback.set_bpm(float(session.get("bpm") or 128))
        self._playback.play(spec, cue_beats=cue_beats, loop=bool(session.get("loop", True)))
        self._playing_name = name
        self._last_play_editor = copy.deepcopy(editor) if editor else None
        return {"ok": True, "spec": spec, "cue_beats": cue_beats, "playback": self._playback.status()}

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or self._playing_name).strip()
        playback_status = self._playback.status()
        if not playback_status.get("playing"):
            self._playing_name = ""
            self._last_play_editor = None
        if not self._playing_name or name != self._playing_name:
            return {"ok": True, "applied": False}
        editor = payload.get("editor") if isinstance(payload.get("editor"), dict) else None
        with self._lock:
            config = copy.deepcopy(self._draft)
        spec, _cue_beats = self._play_spec(config, name, editor)
        self._playback.update(spec)
        self._last_play_editor = copy.deepcopy(editor) if editor else self._last_play_editor
        return {"ok": True, "applied": True, "spec": spec, "playback": self._playback.status()}

    def stop(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.stop()
        self._playing_name = ""
        self._last_play_editor = None
        return {"ok": True, "playback": self._playback.status()}

    def emergency_stop(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.emergency_stop()
        self._playing_name = ""
        self._last_play_editor = None
        return {"ok": True, "playback": self._playback.status()}

    def release(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.release()
        self._playing_name = ""
        self._last_play_editor = None
        return {"ok": True, "ownership": self._playback.ownership()}

    def takeover(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.request_takeover()
        return {"ok": True, "ownership": self._playback.ownership()}

    def commit(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._draft)
            errors, warnings = self._validate(config)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings}
            backup = save_config_atomically(config, self._config_path)
            self._draft = copy.deepcopy(config)
            self._persist_draft_locked()
        return {
            "ok": True,
            "backup_path": str(backup) if backup else "",
            "restart_note": "Committed - bridge restart required to take effect live.",
        }

    def discard(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._draft = _load_json(self._config_path)
            _ensure_pad_meta(self._draft)
            _default_bank(self._draft)
            self._draft_path.unlink(missing_ok=True)
        return self.get_config_payload()

    def history(self) -> dict[str, Any]:
        items = sorted(self._config_path.parent.glob(f"{self._config_path.name}.bak-*"), reverse=True)
        return {"ok": True, "history": [{"name": item.name, "path": str(item), "size": item.stat().st_size} for item in items]}

    def history_diff(self, name: str) -> dict[str, Any]:
        path = self._config_path.parent / name
        if not path.name.startswith(f"{self._config_path.name}.bak-") or not path.exists():
            raise ValueError("unknown backup")
        old = path.read_text(encoding="utf-8").splitlines()
        current = json.dumps(self._draft, indent=2, sort_keys=True).splitlines()
        diff = "\n".join(difflib.unified_diff(old, current, fromfile=path.name, tofile="draft", lineterm=""))
        return {"ok": True, "name": name, "diff": diff}

    def history_restore(self, name: str) -> dict[str, Any]:
        path = self._config_path.parent / name
        if not path.name.startswith(f"{self._config_path.name}.bak-") or not path.exists():
            raise ValueError("unknown backup")
        config = _load_json(path)
        _ensure_pad_meta(config)
        _default_bank(config)
        errors, warnings = self._validate(config)
        if errors:
            return {"ok": False, "errors": errors, "warnings": warnings}
        with self._lock:
            self._draft = config
            self._persist_draft_locked()
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def runtime_status(self) -> dict[str, Any]:
        bridge: dict[str, Any] = {"live": False, "path": str(self._status_path)}
        try:
            raw = json.loads(self._status_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                bridge.update(raw)
                bridge["live"] = True
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
        playback = self._playback.status()
        return {
            "ok": True,
            "bridge": bridge,
            "ownership": self._playback.ownership(),
            "playing_look": playback.get("playing_look", ""),
            "playback": playback,
        }


def build_handler(service: LedPadService) -> type[BaseHTTPRequestHandler]:
    class _LedPadHandler(BaseHTTPRequestHandler):
        _GET_ROUTES = {
            "/api/config": service.get_config_payload,
            "/api/renders": service.get_renders,
            "/api/palettes": service.get_palettes,
            "/api/history": service.history,
            "/api/runtime_status": service.runtime_status,
            "/api/lab/list": service.lab_list,
            "/api/lab/reload": service.lab_reload,
        }
        _POST_ROUTES = {
            "/api/look/save": service.save_look,
            "/api/look/duplicate": service.duplicate_look,
            "/api/look/move": service.move_look,
            "/api/look/delete": service.delete_look,
            "/api/play": service.play,
            "/api/update": service.update,
            "/api/stop": service.stop,
            "/api/emergency_stop": service.emergency_stop,
            "/api/takeover": service.takeover,
            "/api/release": service.release,
            "/api/session": service.session,
            "/api/commit": service.commit,
            "/api/discard": service.discard,
            "/api/lab/save": service.lab_save,
            "/api/lab/play": service.lab_play,
            "/api/lab/reload": service.lab_reload,
            "/api/lab/accept": service.lab_accept,
            "/api/lab/reject": service.lab_reject,
        }

        def log_message(self, fmt: str, *args: object) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _send_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            raw = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/":
                    self._send_file(_ASSETS_DIR / "index.html")
                    return
                if path == "/lab":
                    self._send_file(_ASSETS_DIR / "lab.html")
                    return
                if path.startswith("/static/"):
                    target = (_ASSETS_DIR / path.removeprefix("/static/")).resolve()
                    if _ASSETS_DIR.resolve() not in target.parents:
                        self.send_error(HTTPStatus.FORBIDDEN)
                        return
                    self._send_file(target)
                    return
                if path.startswith("/api/history/") and path.endswith("/diff"):
                    name = path.removeprefix("/api/history/").removesuffix("/diff")
                    self._send_json(service.history_diff(name))
                    return
                route = self._GET_ROUTES.get(path)
                if route is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(route())
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.OK)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path.startswith("/api/history/") and path.endswith("/restore"):
                    name = path.removeprefix("/api/history/").removesuffix("/restore")
                    self._send_json(service.history_restore(name))
                    return
                route = self._POST_ROUTES.get(path)
                if route is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(route(self._read_json()))
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.OK)

    return _LedPadHandler


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    config_path: Path | str | None = None,
    dry_run: bool = False,
) -> ThreadingHTTPServer:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    service = LedPadService(config_path=config_path, dry_run=dry_run)
    server = ThreadingHTTPServer((host, int(port)), build_handler(service))
    setattr(server, "led_pad_service", service)
    logger.info("LED Pad listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    finally:
        service.shutdown()
        server.server_close()
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local LED Pad web UI")
    parser.add_argument("--host", "--bind", dest="host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--config", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Use the realtime dry-run transport")
    args = parser.parse_args(argv)
    try:
        run_server(host=args.host, port=args.port, config_path=args.config, dry_run=args.dry_run)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"led_pad: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
