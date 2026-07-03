from __future__ import annotations

import copy
import importlib.util
import json
import re
import tempfile
import traceback as traceback_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ..govee_frame_renderer import (
    GoveeFrameRenderer,
    REALTIME_EFFECT_NAMES,
    Frame,
    MotionField,
    universal_colorizer,
)

_IDENT_RE = re.compile(r"^[a-z0-9_]+$")
_KINDS = {"slot", "frame"}
_STATUSES = {"iterating", "accepted", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), prefix=f"{path.name}.tmp-") as fp:
            temp_path = Path(fp.name)
            json.dump(data, fp, indent=2, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


class LabRegistry:
    def __init__(self, lab_dir: Path | str) -> None:
        self.lab_dir = Path(lab_dir)
        self.path = self.lab_dir / "drafts.json"
        self.module_path = self.lab_dir / "effects_lab.py"

    def _empty(self) -> dict[str, Any]:
        return {"entries": []}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            data = {"entries": data}
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            raise ValueError("lab drafts root must contain entries list")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.lab_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        _write_json_atomic(self.path, data)

    def list(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._load()["entries"]]

    def get(self, name: str) -> dict[str, Any]:
        for item in self.list():
            if item.get("name") == name:
                return item
        raise ValueError(f"unknown lab draft: {name}")

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        self._validate_name(name)
        data = self._load()
        entries = data["entries"]
        existing = next((item for item in entries if item.get("name") == name), None)
        created = existing.get("created") if existing else _now()
        current = copy.deepcopy(existing or {})
        current.update({
            "name": name,
            "kind": str(payload.get("kind", current.get("kind", "slot"))),
            "fn": str(payload.get("fn", current.get("fn", name))),
            "params": payload.get("params", current.get("params", {})) if isinstance(payload.get("params", current.get("params", {})), dict) else {},
            "cue_beats": float(payload.get("cue_beats", current.get("cue_beats", 16)) or 16),
            "notes": str(payload.get("notes", current.get("notes", ""))),
            "brief": str(payload.get("brief", current.get("brief", ""))),
            "status": str(payload.get("status", current.get("status", "iterating"))),
            "created": created,
            "updated": _now(),
        })
        self._validate_entry(current)
        if existing:
            entries[entries.index(existing)] = current
        else:
            entries.append(current)
        self._save(data)
        return {"ok": True, "entry": copy.deepcopy(current)}

    def set_status(self, name: str, status: str) -> dict[str, Any]:
        if status not in _STATUSES:
            raise ValueError("lab status must be iterating, accepted, or rejected")
        entry = self.get(name)
        entry["status"] = status
        return self.save(entry)

    @staticmethod
    def scene_ref(name: str) -> str:
        return f"lab_{name}"

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not _IDENT_RE.fullmatch(name):
            raise ValueError("lab name must match [a-z0-9_]+")
        if name in REALTIME_EFFECT_NAMES or f"lab_{name}" in REALTIME_EFFECT_NAMES:
            raise ValueError(f"lab name collides with production renderer: {name}")

    def _validate_entry(self, entry: dict[str, Any]) -> None:
        self._validate_name(str(entry.get("name", "")))
        if entry.get("kind") not in _KINDS:
            raise ValueError("lab kind must be slot or frame")
        if not str(entry.get("fn", "")).isidentifier():
            raise ValueError("lab fn must be a Python identifier")
        if entry.get("status") not in _STATUSES:
            raise ValueError("lab status must be iterating, accepted, or rejected")


def load_lab_effects(path: Path | str) -> dict[str, Any]:
    module_path = Path(path)
    try:
        spec = importlib.util.spec_from_file_location(f"led_pad_lab_{id(module_path)}", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load lab module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = getattr(module, "LAB_EFFECTS", {})
        if not isinstance(raw, dict):
            raise ValueError("LAB_EFFECTS must be a dict")
        effects: dict[str, tuple[str, Callable[..., Any]]] = {}
        for name, value in raw.items():
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(f"LAB_EFFECTS[{name!r}] must be (kind, fn)")
            kind, fn = value
            if kind not in _KINDS or not callable(fn):
                raise ValueError(f"LAB_EFFECTS[{name!r}] has invalid kind or function")
            effects[str(name)] = (str(kind), fn)
        return {"ok": True, "effects": effects, "error": "", "traceback": ""}
    except Exception as exc:
        return {"ok": False, "effects": {}, "error": str(exc), "traceback": traceback_mod.format_exc()}


class LabRenderer:
    def __init__(self, module_path: Path | str, delegate: GoveeFrameRenderer | None = None) -> None:
        self.module_path = Path(module_path)
        self.delegate = delegate or GoveeFrameRenderer()
        self.effects: dict[str, tuple[str, Callable[..., Any]]] = {}
        self.last_error = ""
        self.last_traceback = ""

    def reload(self) -> dict[str, Any]:
        result = load_lab_effects(self.module_path)
        self.effects = result["effects"] if result["ok"] else {}
        self.last_error = result["error"]
        self.last_traceback = result["traceback"]
        return result

    def blank(self, segments: int) -> Frame:
        return self.delegate.blank(segments)

    def render(self, name: str, *, beat_pos: float, local_t: float, frame_index: int, params: Mapping[str, Any] | None, segments: int, seed: int) -> Frame:
        text = str(name)
        if not text.startswith("lab_"):
            return self.delegate.render(name, beat_pos=beat_pos, local_t=local_t, frame_index=frame_index, params=params, segments=segments, seed=seed)
        found = self.effects.get(text.removeprefix("lab_"))
        if found is None:
            return self.delegate.blank(segments)
        kind, fn = found
        safe_params = params if isinstance(params, Mapping) else {}
        if kind == "slot":
            field: MotionField = fn(float(beat_pos), max(0.0, float(local_t)), int(frame_index), safe_params, max(0, int(segments)), int(seed))
            frame = universal_colorizer(field, _slot_colors(safe_params.get("slot_colors")))
        else:
            frame = fn(float(beat_pos), max(0.0, float(local_t)), int(frame_index), safe_params, max(0, int(segments)), int(seed))
        return _clamp_pad(frame, segments)


def _slot_colors(value: Any) -> list[tuple[int, int, int]]:
    if not isinstance(value, (list, tuple)) or not value:
        return [(255, 255, 255)]
    colors = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return [(255, 255, 255)]
        colors.append((_clamp(item[0]), _clamp(item[1]), _clamp(item[2])))
    return colors


def _clamp(value: Any) -> int:
    try:
        return max(0, min(255, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _clamp_pad(frame: Any, segments: int) -> Frame:
    seg = max(0, int(segments))
    out: Frame = []
    for item in list(frame or [])[:seg]:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            out.append((_clamp(item[0]), _clamp(item[1]), _clamp(item[2])))
    if len(out) < seg:
        out.extend([(0, 0, 0)] * (seg - len(out)))
    return out
