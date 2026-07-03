from __future__ import annotations

import itertools
from typing import Any

from .govee_frame_renderer import (
    EDM_BUILDS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
)
from .govee_realtime_runner import _COLOR_SIG_KEYS


RGB_KEYS = frozenset({"color", "bg", "color_a", "color_b"})


def _meta(
    label: str,
    kind: str,
    *,
    min: float | None = None,  # noqa: A002
    max: float | None = None,  # noqa: A002
    step: float | None = None,
    choices: tuple[Any, ...] = (),
    help: str,
    advanced: bool = False,
) -> dict[str, Any]:
    return {
        "label": label,
        "kind": kind,
        "min": min,
        "max": max,
        "step": step,
        "choices": choices,
        "help": help,
        "advanced": advanced,
    }


CONTROL_META: dict[str, dict[str, Any]] = {
    "travel_beats": _meta("Motion Beats", "number", min=0.01, max=32, step=0.25, help="How many beats the motion takes.", advanced=True),
    "loop_beats": _meta("Motion Beats (loop)", "number", min=0.01, max=32, step=0.25, help="How many beats the motion loop takes.", advanced=True),
    "breath_beats": _meta("Breath Beats", "number", min=0.01, max=32, step=0.25, help="How many beats a breathing cycle takes."),
    "burst_beats": _meta("Burst Beats", "number", min=0.01, max=16, step=0.25, help="How many beats the burst takes."),
    "drift_beats": _meta("Color Drift Beats", "number", min=0.01, max=64, step=0.25, help="How many beats color drift takes."),
    "duration_beats": _meta("Cycle Beats", "number", min=0, max=64, step=1, help="How many beats the cue cycle covers."),
    "width": _meta("Head Width", "number", min=0.01, max=4, step=0.05, help="How wide the moving head appears.", advanced=True),
    "trail_beats": _meta("Trail Beats", "number", min=0, max=8, step=0.25, help="How long the motion trail lasts.", advanced=True),
    "trail": _meta("Trail Length", "int", min=0, max=60, step=1, help="How many LEDs remain behind the moving head."),
    "heads": _meta("Comet Count", "int", min=1, max=16, step=1, help="How many comets can overlap.", advanced=True),
    "span_beats": _meta("Span Beats", "number", min=0, max=32, step=0.25, help="How many beats the span covers."),
    "period_beats": _meta("Breath Beats", "number", min=0, max=32, step=0.25, help="How many beats a pulse takes."),
    "floor": _meta("Minimum Glow", "number", min=0, max=1, step=0.05, help="The dimmest point in the pulse."),
    "density": _meta("Sparkle Density", "number", min=0, max=1, step=0.05, help="How many sparkles appear."),
    "duty": _meta("Strobe Duty", "number", min=0, max=1, step=0.05, help="How much of the strobe cycle stays lit."),
    "subdivision": _meta("Strobe Rate", "choice", choices=(1, 2, 4, 8), help="Beat subdivision used for strobe timing."),
    "speed": _meta("Sweep Speed", "number", min=0, max=16, step=0.25, help="How quickly the sweep moves."),
    "decay": _meta("Fade Decay", "number", min=0, max=16, step=0.25, help="How quickly the burst fades."),
    "sync_mode": _meta("Sync Mode", "choice", choices=("retrigger", "overlap", "continuous"), help="How motion responds to beat triggers.", advanced=True),
    "beat_division": _meta("Beat Division", "number", min=0.01, max=16, step=0.25, help="How often beat triggers fire.", advanced=True),
    "max_pulses": _meta("Max Comets", "int", min=1, max=16, step=1, help="Maximum overlapping comets.", advanced=True),
    "spawn_on_wrap": _meta("Spawn on Loop Wrap", "bool", help="Start a comet when the beat wraps backward.", advanced=True),
    "reverse": _meta("Reverse Direction", "bool", help="Run motion in the opposite direction.", advanced=True),
    "color": _meta("Color", "rgb", help="Fixed RGB color."),
    "bg": _meta("Background Color", "rgb", help="Fixed RGB background color."),
    "color_a": _meta("Color A", "rgb", help="First fixed RGB color."),
    "color_b": _meta("Color B", "rgb", help="Second fixed RGB color."),
}

for _key, _entry in CONTROL_META.items():
    _entry["color_sig"] = _key in _COLOR_SIG_KEYS


RENDER_GROUPS: dict[str, tuple[str, ...]] = {
    "Solid & utility": ("solid", "blackout"),
    "Ambient & breakdown": (
        "breathe",
        "gradient_sweep",
        "sparkle",
        "twinkle_blue",
        "rt_twinkle",
        "breakdown_full_breathing",
        "breakdown_star_twinkle",
        "breakdown_star_twinkle_sand",
    ),
    "Groove": (
        "beat_chase",
        "bar_wipe",
        "color_pulse",
        "groove_chase_blue",
        "groove_chase_cyan",
        "groove_chase_red",
        "groove_chase_green",
        "groove_chase_cyan_white",
        "groove_freestyle_nebula",
        "rt_groove_chase",
        "rt_groove_nebula",
        "groove_center_chase",
        "groove_center_burst_retract",
    ),
    "Buildup": (
        "buildup_ramp_1",
        "buildup_ramp_2",
        "buildup_ramp_3",
        "buildup_white_zone_strobe",
        "buildup_white_half_strobe",
        "buildup_freestyle_nebula",
    ),
    "Drop": (
        "beat_strobe",
        "drop_burst",
        "drop_chase_blue",
        "drop_chase_cyan",
        "drop_chase_red",
        "drop_chase_green",
        "drop_chase_cyan_white",
        "drop_center_burst_blue_cyan",
        "drop_chase_freestyle_nebula",
        "drop_white_aggressive",
        "rt_drop_chase",
        "rt_drop_nebula",
        "rt_drop_center_burst",
    ),
    "Post-drop": (
        "post_drop_chase_blue",
        "post_drop_chase_cyan",
        "post_drop_chase_red",
        "post_drop_chase_green",
        "post_drop_chase_cyan_white",
        "post_drop_center_comet_blue_cyan",
        "post_drop_freestyle_nebula",
        "post_drop_white_shatter",
        "rt_post_drop_chase",
        "rt_post_drop_nebula",
        "rt_post_drop_center_comet",
        "post_drop_firework_chase",
    ),
}

if __debug__:
    assert set(itertools.chain.from_iterable(RENDER_GROUPS.values())) == set(REALTIME_EFFECT_NAMES)


def _humanize(name: str) -> str:
    return name.replace("rt_", "").replace("_", " ").replace("post drop", "post-drop").title()


RENDER_LABELS: dict[str, str] = {
    name: f"{_humanize(name)} (show-colored)" if name in SLOT_EFFECTS else _humanize(name)
    for name in REALTIME_EFFECT_NAMES
}


def controls_for(scene_ref: str) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for key in sorted(REALTIME_EFFECT_PARAM_KEYS.get(str(scene_ref), frozenset())):
        meta = dict(CONTROL_META[key])
        meta["key"] = key
        controls.append(meta)
    controls.sort(key=lambda item: (bool(item.get("advanced")), str(item.get("label", ""))))
    return controls


def render_catalog() -> list[dict[str, Any]]:
    group_for: dict[str, str] = {}
    for group, names in RENDER_GROUPS.items():
        for name in names:
            group_for[name] = group
    return [
        {
            "name": name,
            "label": RENDER_LABELS[name],
            "group": group_for[name],
            "description": EDM_BUILDS.get(name, ""),
            "slot_based": name in SLOT_EFFECTS,
            "strobe": name in REALTIME_STROBE_EFFECTS,
            "color_source_capable": name in SLOT_EFFECTS,
        }
        for name in sorted(REALTIME_EFFECT_NAMES, key=lambda item: (group_for[item], RENDER_LABELS[item]))
    ]
