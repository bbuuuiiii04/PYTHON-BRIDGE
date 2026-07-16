"""Production lab-draft adapter for the Govee frame-engine child (AWR-260).

Lazily loads ``config/led_lab/effects_lab.py`` the same way the pad does, then
renders accepted looks whose ``scene_ref`` is ``lab:<draft>`` (or
``lab_adapter`` + ``lab_draft`` param). Fail-dark and budget-watchdog so a bad
cue can never stall the child's frame cadence or throw into the runner.
"""
from __future__ import annotations

import collections
import importlib.util
import logging
import time
import traceback as traceback_mod
from pathlib import Path
from typing import Any, Callable, Mapping

from .govee_frame_renderer import Frame, MotionField, universal_colorizer

log = logging.getLogger("govee_lab_adapter")

LAB_SCENE_PREFIX = "lab:"
LAB_ADAPTER_SCENE = "lab_adapter"
_BUDGET_S = 0.010
_BUDGET_HITS_TO_DISABLE = 3
_BUDGET_WINDOW = 20
_KINDS = frozenset({"slot", "frame"})


def is_lab_production_scene(scene_ref: str) -> bool:
    text = str(scene_ref or "").strip()
    return text.startswith(LAB_SCENE_PREFIX) or text == LAB_ADAPTER_SCENE


def lab_draft_from_scene(
    scene_ref: str,
    params: Mapping[str, Any] | None = None,
) -> str:
    text = str(scene_ref or "").strip()
    if text.startswith(LAB_SCENE_PREFIX):
        return text[len(LAB_SCENE_PREFIX) :].strip()
    if text == LAB_ADAPTER_SCENE:
        raw = params or {}
        return str(raw.get("lab_draft") or raw.get("draft") or "").strip()
    return ""


def default_lab_module_path(config_path: Path | str | None = None) -> Path:
    if config_path is not None:
        return Path(config_path).resolve().parent / "led_lab" / "effects_lab.py"
    env = __import__("os").environ.get("RBSS_LED_CONFIG")
    if env:
        return Path(env).resolve().parent / "led_lab" / "effects_lab.py"
    return Path("config/led_lab/effects_lab.py")


def load_lab_effects(path: Path | str) -> dict[str, Any]:
    """Import ``LAB_EFFECTS`` from a lab module path (pad-compatible)."""
    module_path = Path(path)
    try:
        spec = importlib.util.spec_from_file_location(
            f"govee_lab_adapter_{id(module_path)}", module_path
        )
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
        return {
            "ok": False,
            "effects": {},
            "error": str(exc),
            "traceback": traceback_mod.format_exc(),
        }


def _blank(segments: int) -> Frame:
    return [(0, 0, 0)] * max(0, int(segments))


def _clamp_channel(value: Any) -> int:
    try:
        return max(0, min(255, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _slot_colors(value: Any) -> list[tuple[int, int, int]]:
    if not isinstance(value, (list, tuple)) or not value:
        return [(255, 255, 255)]
    colors: list[tuple[int, int, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return [(255, 255, 255)]
        colors.append((_clamp_channel(item[0]), _clamp_channel(item[1]), _clamp_channel(item[2])))
    return colors


def _clamp_frame(frame: Any, segments: int) -> Frame:
    seg = max(0, int(segments))
    out: Frame = []
    for item in list(frame or [])[:seg]:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            out.append((_clamp_channel(item[0]), _clamp_channel(item[1]), _clamp_channel(item[2])))
    if len(out) < seg:
        out.extend([(0, 0, 0)] * (seg - len(out)))
    return out


class LabProductionAdapter:
    """Render accepted lab drafts inside the frame-engine child."""

    def __init__(
        self,
        module_path: Path | str | None = None,
        *,
        time_fn: Callable[[], float] | None = None,
        budget_s: float = _BUDGET_S,
        budget_hits_to_disable: int = _BUDGET_HITS_TO_DISABLE,
        budget_window: int = _BUDGET_WINDOW,
    ) -> None:
        self.module_path = Path(module_path) if module_path is not None else default_lab_module_path()
        self._time_fn = time_fn or time.perf_counter
        self._budget_s = float(budget_s)
        self._budget_hits_to_disable = int(budget_hits_to_disable)
        self._budget_window = max(1, int(budget_window))
        self.effects: dict[str, tuple[str, Callable[..., Any]]] = {}
        self.module_ok = False
        self.last_error = ""
        self.last_traceback = ""
        self._loaded = False
        self._disabled: set[str] = set()
        self._budget_hits: dict[str, collections.deque[bool]] = {}
        self._disable_logged: set[str] = set()

    def reload(self) -> dict[str, Any]:
        result = load_lab_effects(self.module_path)
        self.effects = result["effects"] if result["ok"] else {}
        self.module_ok = bool(result["ok"])
        self.last_error = str(result.get("error") or "")
        self.last_traceback = str(result.get("traceback") or "")
        self._loaded = True
        # Fresh module → clear session disables so a fixed cue can recover.
        self._disabled.clear()
        self._budget_hits.clear()
        self._disable_logged.clear()
        return result

    def ensure_loaded(self) -> bool:
        if not self._loaded:
            self.reload()
        return self.module_ok

    def is_available(self, scene_ref: str, params: Mapping[str, Any] | None = None) -> bool:
        if not is_lab_production_scene(scene_ref):
            return True
        if not self.ensure_loaded():
            return False
        draft = lab_draft_from_scene(scene_ref, params)
        if not draft or draft in self._disabled:
            return False
        return draft in self.effects

    def render(
        self,
        scene_ref: str,
        *,
        beat_pos: float,
        local_t: float,
        frame_index: int,
        params: Mapping[str, Any] | None,
        segments: int,
        seed: int,
    ) -> Frame:
        seg = max(0, int(segments))
        safe_params: Mapping[str, Any] = params if isinstance(params, Mapping) else {}
        draft = lab_draft_from_scene(scene_ref, safe_params)
        if not draft:
            return _blank(seg)
        if draft in self._disabled:
            return _blank(seg)
        if not self.ensure_loaded():
            return _blank(seg)
        found = self.effects.get(draft)
        if found is None:
            return _blank(seg)
        kind, fn = found
        started = self._time_fn()
        try:
            if kind == "slot":
                field: MotionField = fn(
                    float(beat_pos),
                    max(0.0, float(local_t)),
                    int(frame_index),
                    safe_params,
                    seg,
                    int(seed),
                )
                frame = universal_colorizer(field, _slot_colors(safe_params.get("slot_colors")))
            else:
                frame = fn(
                    float(beat_pos),
                    max(0.0, float(local_t)),
                    int(frame_index),
                    safe_params,
                    seg,
                    int(seed),
                )
            out = _clamp_frame(frame, seg)
        except Exception:
            # Never propagate — solid black, engine stays alive.
            log.debug(
                "[LAB] render-exception draft=%s frame=%s",
                draft,
                frame_index,
                exc_info=True,
            )
            out = _blank(seg)
        elapsed = self._time_fn() - started
        self._note_budget(draft, elapsed)
        return out

    def _note_budget(self, draft: str, elapsed_s: float) -> None:
        over = elapsed_s > self._budget_s
        window = self._budget_hits.setdefault(
            draft, collections.deque(maxlen=self._budget_window)
        )
        window.append(over)
        if sum(1 for hit in window if hit) < self._budget_hits_to_disable:
            return
        if draft in self._disabled:
            return
        self._disabled.add(draft)
        if draft not in self._disable_logged:
            self._disable_logged.add(draft)
            log.warning(
                "[LAB] cue-disabled-for-session draft=%s reason=render_budget "
                "budget_ms=%.1f hits=%d window=%d",
                draft,
                self._budget_s * 1000.0,
                self._budget_hits_to_disable,
                self._budget_window,
            )
