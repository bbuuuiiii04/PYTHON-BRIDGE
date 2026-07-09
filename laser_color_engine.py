"""Pure CH8/CH9 laser color mapper.

The state-manager thread calls update() and snapshot(); no locks are needed.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger("rb_ss_bridge_v2.laser_color")


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

# ponytail: 3-tier rank, per-fixture luminance if it ever looks wrong.
# Hardcoded brightness rank for the "laser never dimmer than the LEDs" floor.
_BRIGHTNESS = {"white": 3, "cyan": 2, "green": 2, "yellow": 2, "blue": 1, "purple": 1, "red": 1}


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
    # Per-mood menus: {mood: ((\"solid\", name)
    #                        | (\"chase\", ch8, (name, ...))
    #                        | (\"chase_tiered\", {tier: ch8}, (name, ...)), ...)}
    # Stored as nested tuples so the frozen dataclass stays immutable (the tiered
    # entry's inner dict is read-only in practice — never mutated or hashed).
    menus: Mapping[str, tuple] | None = None

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
            menus=_parse_menus(src.get("menus")),
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
        tier: str | None = None,
    ) -> None:
        try:
            target = self._target(
                state,
                white_moment=white_moment,
                drop_phase=drop_phase,
                post_drop_progress=post_drop_progress,
                tier=tier,
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
        tier: str | None = None,
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

        # Follow the LEDs' actual last-emitted color if it is available; fall
        # back to the palette-center rgb otherwise. Either way, fail closed
        # (return None -> authored CH8/CH9 pass through) on an invalid rgb.
        live_raw = state.get("live_rgb")
        live = live_raw if _valid_rgb(live_raw) else state.get("rgb")
        if not _valid_rgb(live):
            return None
        live = tuple(int(v) for v in live)

        fixed_ch9 = self._map.fixed_ch9
        menu = (self._map.menus or {}).get(state.get("palette"))
        if not menu:
            # Legacy: mood with no menu keeps the single-solid nearest-fixed path.
            name = _nearest_fixed_color(live)
            ch8 = fixed.get(name)
            if ch8 is None:
                return None
            ch9 = None if fixed_ch9 is None else self._settled_ch9(fixed_ch9, drop_phase, post_drop_progress)
            return (ch8, ch9)

        led_color = _nearest_fixed_color(live)
        led_b = _led_brightness(live, state, white_moment)
        eligible = [e for e in menu if _entry_brightness(e) >= led_b]
        if not eligible:
            # Never go dark: keep the brightest allowed entry.
            eligible = [max(menu, key=_entry_brightness)]

        is_drop = drop_phase == "drop"
        entry = _pick_menu_entry(eligible, led_color, is_drop)
        if entry[0] == "solid":
            ch8 = fixed.get(entry[1])
        elif entry[0] == "chase_tiered":
            # AWR-170 (B): the drop's energy tier picks the chase DIVISION class
            # (100→116→140 for red+white). Unknown/None tier ⇒ standard.
            ch8 = _resolve_tier_ch8(entry[1], tier)
        else:  # "chase" (single-value): byte-identical to pre-AWR-170.
            ch8 = entry[1]
        if ch8 is None:
            return None
        ch9 = None if fixed_ch9 is None else self._settled_ch9(fixed_ch9, drop_phase, post_drop_progress)
        return (ch8, ch9)

    def _settled_ch9(self, ch9: int, drop_phase: str | None, progress: float | None) -> int:
        ease_beats = int((self._map.settle or {}).get("ease_beats", 0) or 0)
        if ease_beats <= 0 or drop_phase != "post_drop" or progress is None:
            return ch9
        t = max(0.0, min(1.0, float(progress)))
        return max(0, int(round(ch9 * (1.0 - t))))


# Resolve the default relative to THIS module (repo root), not the process cwd.
# The live bridge runs `python3 -m rb_ss_bridge_v2` from the repo PARENT
# (ss_bridge_watcher.sh cd's to dirname(REPO_ROOT)), so a bare "config/..." default
# resolved to a nonexistent path and silently loaded an all-null/disabled map —
# which disabled the whole laser-color-from-LED-palette feature at runtime.
_DEFAULT_COLOR_MAP_PATH = Path(__file__).resolve().parent / "config" / "laser_color_map.json"


def load_laser_color_map(path: str | Path = _DEFAULT_COLOR_MAP_PATH) -> LaserColorMap:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        # Loud, not silent: an unreadable map disables the whole laser-color
        # feature (authored CH8/CH9 pass through). That silent-disable once hid
        # a cwd/relative-path bug for weeks. Surface it so it can't hide again.
        log.warning(
            "[laser-color] map not loaded path=%s err=%s -> DISABLED "
            "(lasers keep baked pack color)", path, type(exc).__name__,
        )
        data = {}
    return LaserColorMap.from_dict(data)


def _nearest_fixed_color(rgb: tuple[int, int, int]) -> str:
    def dist(name: str) -> int:
        target = FIXED_COLOR_RGB[name]
        return sum((rgb[i] - target[i]) ** 2 for i in range(3))

    return min(FIXED_COLOR_ORDER, key=dist)


def _parse_menus(raw: Any) -> Mapping[str, tuple] | None:
    """Parse the config `menus` block into nested tuples (frozen-safe).

    Each mood's list becomes a tuple of normalized entries:
      - a str name -> ("solid", name)
      - {"chase": <ch8>, "colors": [a] or [a, b]} -> ("chase", ch8, (a, ...))
      - {"chase": {"standard"|"intense"|"monster": <ch8>}, "colors": [...]}
        -> ("chase_tiered", {tier: ch8}, (a, ...))  (AWR-170 B: per-tier division)
    Malformed entries are dropped silently (fail closed: a junk per-tier chase is
    skipped, never invented); a mood that ends up empty is omitted entirely (so the
    mood falls back to the legacy nearest-fixed path).
    """
    if not isinstance(raw, Mapping):
        return None
    menus: dict[str, tuple] = {}
    for mood, entries_src in raw.items():
        if not isinstance(entries_src, list):
            continue
        entries: list[tuple] = []
        for item in entries_src:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    entries.append(("solid", name))
            elif isinstance(item, Mapping):
                colors_src = item.get("colors")
                if not isinstance(colors_src, list):
                    continue
                names = tuple(
                    c.strip() for c in colors_src if isinstance(c, str) and c.strip()
                )
                if not 1 <= len(names) <= 2:
                    continue
                chase_raw = item.get("chase")
                if isinstance(chase_raw, Mapping):
                    tiers = _resolve_chase_tiers(chase_raw)
                    if tiers is None:
                        continue  # all-junk per-tier dict: fail closed, skip entry
                    entries.append(("chase_tiered", tiers, names))
                else:
                    ch8 = _byte_or_none(chase_raw)
                    if ch8 is None:
                        continue
                    entries.append(("chase", ch8, names))
        if entries:
            menus[str(mood)] = tuple(entries)
    return menus or None


_CHASE_TIERS = ("standard", "intense", "monster")


def _resolve_chase_tiers(raw: Mapping[str, Any]) -> dict[str, int] | None:
    """Per-tier chase dict -> a fully-populated {standard,intense,monster: ch8}.

    Missing keys fall back to `standard`, then to the first present value. All-junk
    (no valid 0-255 byte anywhere) -> None so the caller fails closed to skipping the
    entry (never invents a division). ponytail: a dict inside the frozen map is safe
    — menu entries are only ever read, never mutated or hashed.
    """
    parsed = {t: _byte_or_none(raw.get(t)) for t in _CHASE_TIERS}
    present = {t: v for t, v in parsed.items() if v is not None}
    if not present:
        return None
    base = present.get("standard", next(iter(present.values())))
    return {t: present.get(t, base) for t in _CHASE_TIERS}


def _resolve_tier_ch8(tiers: Mapping[str, int], tier: str | None) -> int | None:
    """CH8 for the current drop tier; None/unknown/`small` tier -> standard."""
    if tier in tiers:
        return tiers[tier]
    return tiers.get("standard")


def _entry_brightness(entry: tuple) -> int:
    """Brightness rank of a menu entry (solid name, or chase's brightest color)."""
    if entry[0] == "solid":
        return _BRIGHTNESS.get(entry[1], 1)
    # chase: rank of the brightest of its colors; unknown names default to 2.
    return max(_BRIGHTNESS.get(c, 2) for c in entry[2])


def _led_brightness(live_rgb: tuple[int, int, int], state: Mapping[str, Any], white_moment: bool) -> int:
    """Brightness rank the laser must not fall below.

    Takes the already-resolved live rgb (never re-reads state blindly — a
    None/invalid rgb would throw and silently kill the feature via update()'s
    catch-all). In practice at the menu-pick point white_moment/white_sand are
    already false (they early-return to white), so this only ever separates
    rank 1 from rank 2 within a menu.
    """
    if white_moment or bool(state.get("white_sand_active")):
        return 3
    return _BRIGHTNESS.get(_nearest_fixed_color(live_rgb), 1)


def _pick_menu_entry(eligible: list[tuple], led_color: str, is_drop: bool) -> tuple:
    """Deterministic (no RNG) menu pick from the already-filtered eligible list.

    Drops prefer a chase (fires the two-color effect); non-drops track the
    matching solid. `eligible` is guaranteed non-empty by the caller.
    """
    chases = [e for e in eligible if e[0] in ("chase", "chase_tiered")]
    solids = [e for e in eligible if e[0] == "solid"]
    if is_drop:
        for e in chases:
            if led_color in e[2]:
                return e
        if chases:
            return chases[0]
        for e in solids:
            if e[1] == led_color:
                return e
        return max(eligible, key=_entry_brightness)
    # non-drop: track the solid
    for e in solids:
        if e[1] == led_color:
            return e
    if solids:
        return max(solids, key=_entry_brightness)
    return max(chases, key=_entry_brightness)


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
