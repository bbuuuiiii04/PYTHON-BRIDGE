from __future__ import annotations

import copy
import importlib.util
import json
import re
import tempfile
import threading
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
from .file_backup import rotate_backup


class StaleLabEntry(ValueError):
    """Raised when a lab save's ``updated`` stamp does not match disk."""

    def __init__(self, name: str, *, disk_updated: str, client_updated: str) -> None:
        super().__init__(
            f"stale_entry: {name} changed since you loaded it "
            f"(disk={disk_updated!r}, client={client_updated!r})"
        )
        self.name = name
        self.disk_updated = disk_updated
        self.client_updated = client_updated
        self.code = "stale_entry"

_IDENT_RE = re.compile(r"^[a-z0-9_]+$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
# AWR-279 #8: cap draft-id length so the editor header stays legible and its ✕
# stays reachable. Slug bases are truncated with room to spare for a _N suffix.
_MAX_NAME_LEN = 60
_SLUG_BASE_LEN = 57
_KINDS = {"slot", "frame"}
_STATUSES = {"iterating", "accepted", "rejected", "promoted"}
_TIMING_MODES = {"beat", "time", "mixed", "static", "unknown"}
_TARGET_ROLES = {"", "ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def clamp_cue_beats(raw: Any, *, default: float = 16.0) -> float:
    """Beats-until-auto-stop, floored so a one-shot always has a real runway.

    AWR-279 #2: THE shared cue-length validator. Every server intake (lab save,
    lab play, pad save) funnels through here. 0 / negative / blank / non-numeric
    fall back to ``default`` then floor at 1 — a loop-off "Play once" with a
    nonpositive length would leave ``CueTimer`` unable to auto-stop and stream
    forever, and the card would lie about the stored length.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    if not (value > 0):  # also catches NaN
        value = default
    return max(1.0, value)


def slugify_lab_name(display: str, existing: set[str] | None = None) -> str:
    """Turn any display name into a unique [a-z0-9_]+ draft id.

    ``"My Drop Cue"`` → ``my_drop_cue``; collisions append ``_2``, ``_3``, …
    Empty / non-slugable input becomes ``untitled``. Also skips production
    renderer names so Create never lands on a collision brick.
    """
    raw = _SLUG_RE.sub("_", str(display or "").strip().lower()).strip("_")
    base = raw if raw and _IDENT_RE.fullmatch(raw) else "untitled"
    base = base[:_SLUG_BASE_LEN]  # AWR-279 #8: keep ids bounded (room for _N suffix)
    taken = set(existing or ())
    candidate = base
    n = 2
    while (
        candidate in taken
        or candidate in REALTIME_EFFECT_NAMES
        or f"lab_{candidate}" in REALTIME_EFFECT_NAMES
    ):
        candidate = f"{base}_{n}"
        n += 1
    return candidate


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
        self._lock = threading.RLock()

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
        # AWR-258: rotating snapshots for both crown-jewel lab files.
        rotate_backup(self.path, keep=5)
        if self.module_path.exists():
            rotate_backup(self.module_path, keep=5)
        _write_json_atomic(self.path, data)

    def list(self) -> list[dict[str, Any]]:
        # "production_collision" is a decoration for callers (UI chips/banners),
        # never persisted: save() copies only its known payload keys.
        with self._lock:
            raw = self._load()
        out: list[dict[str, Any]] = []
        for item in raw["entries"]:
            entry = copy.deepcopy(item)
            name = str(entry.get("name", ""))
            entry["production_collision"] = name in REALTIME_EFFECT_NAMES or f"lab_{name}" in REALTIME_EFFECT_NAMES
            entry["beat_synced"] = entry.get("timing_mode") in ("beat", "mixed")
            entry.setdefault("target_role", "")
            out.append(entry)
        return out

    def get(self, name: str) -> dict[str, Any]:
        for item in self.list():
            if item.get("name") == name:
                return item
        raise ValueError(f"unknown lab draft: {name}")

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        overwrite = bool(payload.get("overwrite"))
        with self._lock:
            data = self._load()
            entries = data["entries"]
            existing = next((item for item in entries if item.get("name") == name), None)
            # Collision with production renderer names blocks CREATE only. An
            # existing entry whose name later became a production effect must stay
            # saveable (Save/Accept/Reject/Archive) — otherwise promotion bricks it.
            self._validate_name(name, check_collision=existing is None)
            if existing is not None and not overwrite and "updated" in payload:
                client_updated = str(payload.get("updated") or "")
                disk_updated = str(existing.get("updated") or "")
                if client_updated != disk_updated:
                    raise StaleLabEntry(name, disk_updated=disk_updated, client_updated=client_updated)
            created = existing.get("created") if existing else _now()
            current = copy.deepcopy(existing or {})
            current.update({
                "name": name,
                "kind": str(payload.get("kind", current.get("kind", "slot"))),
                "fn": str(payload.get("fn", current.get("fn", name))),
                "params": payload.get("params", current.get("params", {})) if isinstance(payload.get("params", current.get("params", {})), dict) else {},
                "cue_beats": clamp_cue_beats(payload.get("cue_beats", current.get("cue_beats"))),
                "notes": str(payload.get("notes", current.get("notes", ""))),
                "brief": str(payload.get("brief", current.get("brief", ""))),
                "status": str(payload.get("status", current.get("status", "iterating"))),
                "timing_mode": str(payload.get("timing_mode", current.get("timing_mode", "unknown"))),
                "target_role": str(payload.get("target_role", current.get("target_role", ""))),
                "param_specs": self._validate_param_specs(payload.get("param_specs", current.get("param_specs", {}))),
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
            raise ValueError("lab status must be iterating, accepted, rejected, or promoted")
        entry = self.get(name)
        entry["status"] = status
        # Internal status flip always has the disk stamp from get(); allow write.
        return self.save(entry)

    def archive(self, name: str) -> dict[str, Any]:
        return self.set_status(name, "promoted")

    def delete(self, name: str) -> dict[str, Any]:
        with self._lock:
            data = self._load()
            entries = data["entries"]
            existing = next((item for item in entries if item.get("name") == name), None)
            if existing is None:
                raise ValueError(f"unknown lab draft: {name}")
            entries.remove(existing)
            self._save(data)
            return {"ok": True, "deleted": name}

    @staticmethod
    def scene_ref(name: str) -> str:
        return f"lab_{name}"

    @staticmethod
    def _validate_param_specs(value: Any) -> dict[str, dict[str, Any]]:
        if value in (None, {}):
            return {}
        if not isinstance(value, dict):
            raise ValueError("param_specs must be a dict of param -> spec")
        out: dict[str, dict[str, Any]] = {}
        for key, spec in value.items():
            if not str(key) or not isinstance(spec, dict):
                raise ValueError(f"param_specs[{key!r}] must be a dict")
            kind = str(spec.get("kind", "slider"))
            if kind not in ("slider", "toggle", "select"):
                raise ValueError(f"param_specs[{key!r}].kind must be slider, toggle, or select")
            clean: dict[str, Any] = {"kind": kind, "label": str(spec.get("label", key))}
            if kind == "slider":
                if "min" not in spec or "max" not in spec:
                    raise ValueError(f"param_specs[{key!r}] slider needs min and max")
                lo = float(spec["min"]); hi = float(spec["max"]); step = float(spec.get("step", 1))
                if not (hi > lo) or step <= 0:
                    raise ValueError(f"param_specs[{key!r}] needs max > min and step > 0")
                clean.update({"min": lo, "max": hi, "step": step})
            elif kind == "select":
                options = spec.get("options")
                if not isinstance(options, list) or len(options) < 2:
                    raise ValueError(f"param_specs[{key!r}] select needs ≥2 options")
                clean_opts: list[dict[str, Any]] = []
                seen: set[str] = set()
                for opt in options:
                    if not isinstance(opt, dict) or "value" not in opt:
                        raise ValueError(f"param_specs[{key!r}] options need value+label")
                    val = opt["value"]
                    if isinstance(val, bool) or val is None:
                        raise ValueError(f"param_specs[{key!r}] option value must be str/number")
                    if isinstance(val, (int, float)):
                        # Persist ints as ints when whole; else float.
                        if isinstance(val, float) and val.is_integer():
                            val = int(val)
                    else:
                        val = str(val)
                    token = repr(val)
                    if token in seen:
                        raise ValueError(f"param_specs[{key!r}] duplicate option value")
                    seen.add(token)
                    clean_opts.append({"value": val, "label": str(opt.get("label", val))})
                clean["options"] = clean_opts
            out[str(key)] = clean
        return out

    @staticmethod
    def _validate_name(name: str, *, check_collision: bool = True) -> None:
        if not name or not _IDENT_RE.fullmatch(name):
            raise ValueError("lab name must match [a-z0-9_]+")
        if len(name) > _MAX_NAME_LEN:
            raise ValueError(f"lab name is too long (max {_MAX_NAME_LEN} characters)")
        if check_collision and (name in REALTIME_EFFECT_NAMES or f"lab_{name}" in REALTIME_EFFECT_NAMES):
            raise ValueError(f"lab name collides with production renderer: {name}")

    def _validate_entry(self, entry: dict[str, Any]) -> None:
        # Validates stored entries: no collision check (see save()).
        self._validate_name(str(entry.get("name", "")), check_collision=False)
        if entry.get("kind") not in _KINDS:
            raise ValueError("lab kind must be slot or frame")
        if not str(entry.get("fn", "")).isidentifier():
            raise ValueError("lab fn must be a Python identifier")
        if entry.get("status") not in _STATUSES:
            raise ValueError("lab status must be iterating, accepted, rejected, or promoted")
        if entry.get("timing_mode") not in _TIMING_MODES:
            raise ValueError("lab timing_mode must be beat, time, mixed, static, or unknown")
        if entry.get("target_role") not in _TARGET_ROLES:
            raise ValueError(
                "lab target_role must be empty or one of ambient, groove, buildup, "
                "pre_drop, drop, post_drop, breakdown, utility"
            )


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


def render_preview_frames(
    renderer: "LabRenderer",
    scene_ref: str,
    *,
    params: Mapping[str, Any],
    segments: int,
    seed: int,
    fps: int,
    bpm: float,
    beats: float,
    max_frames: int = 2000,
) -> list[Frame]:
    total = min(int(max_frames), max(1, int(round(beats * 60.0 / bpm * fps))))
    frames: list[Frame] = []
    for index in range(total):
        t = index / float(fps)
        frames.append(renderer.render(
            scene_ref,
            beat_pos=t * bpm / 60.0,
            local_t=t,
            frame_index=index,
            params=params,
            segments=segments,
            seed=seed,
        ))
    return frames


class LabRenderer:
    def __init__(
        self,
        module_path: Path | str,
        delegate: GoveeFrameRenderer | None = None,
        *,
        fn_for: Callable[[str], str] | None = None,
    ) -> None:
        self.module_path = Path(module_path)
        self.delegate = delegate or GoveeFrameRenderer()
        self.fn_for = fn_for
        # Resolver results memoized per name so render() never does registry
        # I/O per frame; reload() (run on every play/preview spec) clears it.
        self._fn_cache: dict[str, str] = {}
        self.effects: dict[str, tuple[str, Callable[..., Any]]] = {}
        self.last_error = ""
        self.last_traceback = ""

    def reload(self) -> dict[str, Any]:
        result = load_lab_effects(self.module_path)
        self.effects = result["effects"] if result["ok"] else {}
        self.last_error = result["error"]
        self.last_traceback = result["traceback"]
        self._fn_cache.clear()
        return result

    def blank(self, segments: int) -> Frame:
        return self.delegate.blank(segments)

    def render(self, name: str, *, beat_pos: float, local_t: float, frame_index: int, params: Mapping[str, Any] | None, segments: int, seed: int) -> Frame:
        text = str(name)
        if not text.startswith("lab_"):
            return self.delegate.render(name, beat_pos=beat_pos, local_t=local_t, frame_index=frame_index, params=params, segments=segments, seed=seed)
        key = text.removeprefix("lab_")
        found = self.effects.get(key)
        if found is None and self.fn_for is not None:
            # Name first, entry-fn fallback: renamed drafts whose module still
            # registers the original fn keep rendering. A resolver failure must
            # not raise out of render — it just means name-only (blank) behavior.
            fn_name = self._fn_cache.get(key)
            if fn_name is None:
                try:
                    fn_name = str(self.fn_for(key))
                except Exception:
                    fn_name = key
                self._fn_cache[key] = fn_name
            found = self.effects.get(fn_name)
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
