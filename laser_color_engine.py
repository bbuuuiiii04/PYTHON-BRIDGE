"""Pure CH8/CH9 laser color mapper.

The state-manager thread calls update() and snapshot(); no locks are needed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


FIXED_COLOR_ORDER = ("red", "green", "blue", "cyan", "yellow", "purple")
FIXED_COLOR_RGB = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "yellow": (255, 255, 0),
    "purple": (255, 0, 255),  # fixture band 28-31 is MAGENTA (camera calibration 2026-06-05)
}
DEFAULT_WHITE_TEMPLATES = (
    "drop_white_aggressive",
    "post_drop_white_shatter",
    "buildup_white_zone_strobe",
    "buildup_white_half_strobe",
)


@dataclass(frozen=True)
class LaserColorSnapshot:
    ch8: int
    ch9: int | None
    seq: int


@dataclass(frozen=True)
class LaserColorMap:
    enabled: bool = False
    fixed: Mapping[str, int | None] | None = None
    fixed_ch9: int | None = None
    effects: Mapping[str, Mapping[str, int | None]] | None = None
    settle: Mapping[str, int] | None = None
    white_templates: tuple[str, ...] = DEFAULT_WHITE_TEMPLATES

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "LaserColorMap":
        src = data if isinstance(data, Mapping) else {}
        fixed_src = src.get("fixed") if isinstance(src.get("fixed"), Mapping) else {}
        effects_src = src.get("effects") if isinstance(src.get("effects"), Mapping) else {}
        rainbow_src = (
            effects_src.get("rainbow_family")
            if isinstance(effects_src.get("rainbow_family"), Mapping)
            else {}
        )
        settle_src = src.get("settle") if isinstance(src.get("settle"), Mapping) else {}
        templates_src = src.get("white_templates")
        templates = (
            tuple(str(name) for name in templates_src if str(name))
            if isinstance(templates_src, list)
            else DEFAULT_WHITE_TEMPLATES
        )
        return cls(
            enabled=bool(src.get("enabled", False)),
            fixed={name: _byte_or_none(fixed_src.get(name)) for name in (*FIXED_COLOR_ORDER, "white")},
            fixed_ch9=_byte_or_none(src.get("fixed_ch9")),
            effects={
                "rainbow_family": {
                    "ch8": _byte_or_none(rainbow_src.get("ch8")),
                    "ch9": _byte_or_none(rainbow_src.get("ch9")),
                }
            },
            settle={"ease_beats": max(0, _int_or_default(settle_src.get("ease_beats"), 8))},
            white_templates=templates or DEFAULT_WHITE_TEMPLATES,
        )


class LaserColorEngine:
    def __init__(self, color_map: LaserColorMap) -> None:
        self._map = color_map
        self._snapshot: LaserColorSnapshot | None = None
        self._seq = 0

    @property
    def white_templates(self) -> tuple[str, ...]:
        return self._map.white_templates

    def update(
        self,
        state: Mapping[str, Any],
        *,
        white_moment: bool,
        drop_phase: str | None,
        post_drop_progress: float | None,
    ) -> None:
        try:
            target = self._target(
                state,
                white_moment=white_moment,
                drop_phase=drop_phase,
                post_drop_progress=post_drop_progress,
            )
        except Exception:
            target = None
        if target is None:
            self._snapshot = None
            return
        self._seq += 1
        self._snapshot = LaserColorSnapshot(target[0], target[1], self._seq)

    def snapshot(self) -> LaserColorSnapshot | None:
        return self._snapshot

    def _target(
        self,
        state: Mapping[str, Any],
        *,
        white_moment: bool,
        drop_phase: str | None,
        post_drop_progress: float | None,
    ) -> tuple[int, int | None] | None:
        if not self._map.enabled:
            return None
        fixed = self._map.fixed or {}
        if white_moment or bool(state.get("white_sand_active")):
            ch8 = fixed.get("white")
            # White preserves whatever speed (CH9) is already authored — None means
            # "leave that channel alone" at the merge seam (soundswitch_laser_player).
            return None if ch8 is None else (ch8, None)
        if bool(state.get("rainbow_active")):
            rainbow = (self._map.effects or {}).get("rainbow_family", {})
            ch8 = rainbow.get("ch8")
            ch9 = rainbow.get("ch9")
            if ch8 is None or ch9 is None:
                return None
            return (ch8, self._settled_ch9(ch9, drop_phase, post_drop_progress))
        rgb = state.get("rgb")
        if not _valid_rgb(rgb):
            return None
        name = _nearest_fixed_color(tuple(int(v) for v in rgb))
        ch8 = fixed.get(name)
        if ch8 is None:
            return None
        fixed_ch9 = self._map.fixed_ch9
        ch9 = None if fixed_ch9 is None else self._settled_ch9(fixed_ch9, drop_phase, post_drop_progress)
        return (ch8, ch9)

    def _settled_ch9(self, ch9: int, drop_phase: str | None, progress: float | None) -> int:
        ease_beats = int((self._map.settle or {}).get("ease_beats", 0) or 0)
        if ease_beats <= 0 or drop_phase != "post_drop" or progress is None:
            return ch9
        t = max(0.0, min(1.0, float(progress)))
        return max(0, int(round(ch9 * (1.0 - t))))


def load_laser_color_map(path: str | Path = "config/laser_color_map.json") -> LaserColorMap:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return LaserColorMap.from_dict(data)


def _nearest_fixed_color(rgb: tuple[int, int, int]) -> str:
    def dist(name: str) -> int:
        target = FIXED_COLOR_RGB[name]
        return sum((rgb[i] - target[i]) ** 2 for i in range(3))

    return min(FIXED_COLOR_ORDER, key=dist)


def _valid_rgb(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in value)
    )


def _byte_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 255 else None


def _int_or_default(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
