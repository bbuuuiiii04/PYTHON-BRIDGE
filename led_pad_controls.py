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
    default: Any = None,
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
        "default": default,
    }


# `default` is the renderer's ACTUAL unset-param fallback, hand-extracted from
# govee_frame_renderer.py (see tests/test_led_pad_controls.py for the source
# lines this is audited against, and docs/guides/led_pad.md for the audit
# table). `None` means "no single static fallback exists" for this key across
# ALL scene_refs that expose it — either because the renderer never actually
# reads that key from params (it is only present because it rides the
# `_SYNC_PARAM_KEYS` blanket allowlist added to every scene), or because the
# static fallback genuinely differs by scene_ref (see PARAM_DEFAULT_OVERRIDES
# below). The UI shows "auto" for `None` defaults rather than inventing a
# number.
CONTROL_META: dict[str, dict[str, Any]] = {
    "travel_beats": _meta("Motion Beats", "number", min=0.01, max=32, step=0.25, help="How many beats the motion takes.", advanced=True, default=None),
    "loop_beats": _meta("Motion Beats (loop)", "number", min=0.01, max=32, step=0.25, help="How many beats the motion loop takes.", advanced=True, default=4.0),
    "breath_beats": _meta("Breath Beats", "number", min=0.01, max=32, step=0.25, help="How many beats a breathing cycle takes.", default=8.0),
    "burst_beats": _meta("Burst Beats", "number", min=0.01, max=16, step=0.25, help="How many beats the burst takes.", default=1.0),
    "drift_beats": _meta("Color Drift Beats", "number", min=0.01, max=64, step=0.25, help="How many beats color drift takes.", default=32.0),
    "duration_beats": _meta("Cycle Beats", "number", min=0, max=64, step=1, help="How many beats the cue cycle covers.", default=32.0),
    "width": _meta("Head Width", "number", min=0.01, max=4, step=0.05, help="How wide the moving head appears.", advanced=True, default=None),
    "trail_beats": _meta("Trail Beats", "number", min=0, max=8, step=0.25, help="How long the motion trail lasts.", advanced=True, default=None),
    "trail": _meta("Trail Length", "int", min=0, max=60, step=1, help="How many LEDs remain behind the moving head.", default=3),
    "heads": _meta("Comet Count", "int", min=1, max=16, step=1, help="How many comets can overlap.", advanced=True, default=None),
    "span_beats": _meta("Span Beats", "number", min=0, max=32, step=0.25, help="How many beats the span covers.", default=1.0),
    "period_beats": _meta("Breath Beats", "number", min=0, max=32, step=0.25, help="How many beats a pulse takes.", default=4.0),
    "floor": _meta("Minimum Glow", "number", min=0, max=1, step=0.05, help="The dimmest point in the pulse.", default=0.1),
    "density": _meta("Sparkle Density", "number", min=0, max=1, step=0.05, help="How many sparkles appear.", default=0.2),
    "duty": _meta("Strobe Duty", "number", min=0, max=1, step=0.05, help="How much of the strobe cycle stays lit.", default=0.5),
    "subdivision": _meta("Strobe Rate", "choice", choices=(1, 2, 4, 8), help="Beat subdivision used for strobe timing.", default=4),
    "speed": _meta("Sweep Speed", "number", min=0, max=16, step=0.25, help="How quickly the sweep moves.", default=1.0),
    "decay": _meta("Fade Decay", "number", min=0, max=16, step=0.25, help="How quickly the burst fades.", default=0.6),
    "sync_mode": _meta("Sync Mode", "choice", choices=("retrigger", "overlap", "continuous"), help="How motion responds to beat triggers.", advanced=True, default=None),
    "beat_division": _meta("Beat Division", "number", min=0.01, max=16, step=0.25, help="How often beat triggers fire.", advanced=True, default=1.0),
    "max_pulses": _meta("Max Comets", "int", min=1, max=16, step=1, help="Maximum overlapping comets.", advanced=True, default=None),
    "spawn_on_wrap": _meta("Spawn on Loop Wrap", "bool", help="Start a comet when the beat wraps backward.", advanced=True, default=None),
    "reverse": _meta("Reverse Direction", "bool", help="Run motion in the opposite direction.", advanced=True, default=None),
    "color": _meta("Color", "rgb", help="Fixed RGB color."),
    "bg": _meta("Background Color", "rgb", help="Fixed RGB background color."),
    "color_a": _meta("Color A", "rgb", help="First fixed RGB color."),
    "color_b": _meta("Color B", "rgb", help="Second fixed RGB color."),
    # AWR-156 additions.
    "hz": _meta("Strobe Hz", "number", min=0.5, max=10, step=0.1, help="Real-time strobe rate (BPM-free).", default=6.0),
    "start_width": _meta("Start Width", "number", min=0.3, max=8, step=0.1, help="Head width at the start of the build.", advanced=True, default=4.0),
    "end_width": _meta("End Width", "number", min=0.3, max=8, step=0.1, help="Head width at the end of the build.", advanced=True, default=1.0),
    "build_beats": _meta("Build Beats", "number", min=1, max=64, step=1, help="How many beats the build takes.", default=16.0),
    "dim_floor": _meta("Dim Floor", "number", min=0.05, max=1, step=0.05, help="The dimmest brightness the build reaches.", default=0.35),
    "base_width": _meta("Base Width", "number", min=0.3, max=6, step=0.1, help="Resting head width between beats.", advanced=True, default=1.5),
    "pulse_width": _meta("Pulse Width", "number", min=0, max=8, step=0.1, help="How much the head widens on each beat.", advanced=True, default=3.0),
    "color_mode": _meta("Color Mode", "choice", choices=(0, 1, 2, 3), help="How the two heads split across palette slots.", advanced=True, default=2),
    "dim_beats": _meta("Background Dim Beats", "number", min=0.5, max=32, step=0.5, help="How many beats the background takes to dim to black.", default=8.0),
    "ember_hold_beats": _meta("Ember Hold Beats", "number", min=0, max=32, step=0.5, help="How many beats embers stay at full brightness.", default=8.0),
    "ember_decay_beats": _meta("Ember Decay Beats", "number", min=0.25, max=16, step=0.25, help="How many beats embers take to fade out after the hold.", default=2.0),
    "sparkle_density": _meta("Sparkle Density", "number", min=0, max=0.8, step=0.05, help="How many embers are active at once.", default=0.35),
    "sparkle_size": _meta("Sparkle Size", "number", min=0.5, max=3, step=0.1, help="How wide each ember appears.", default=1.0),
    "sparkle_life_s": _meta("Sparkle Life (s)", "number", min=0.1, max=2, step=0.05, help="How many real seconds each ember lives.", default=0.8),
    # AWR-161 additions (defaults hand-extracted from govee_frame_renderer.py's
    # `_rainbow_ordered` / `_drop_firework_explosion` params.get fallbacks).
    "cycle_beats": _meta("Rainbow Cycle Beats", "number", min=1, max=64, step=0.5, help="How many beats the rainbow hue cycle takes.", default=8.0),
    "rainbow_span": _meta("Rainbow Span", "number", min=0.1, max=2, step=0.05, help="How much of the spectrum spans the strip.", default=1.0),
    "travel_per_beat": _meta("Travel Per Beat", "number", min=2, max=120, step=1, help="Beat-locked head advance (auto = legacy loop pace).", advanced=True, default=None),
    "surge_beats": _meta("Surge Beats", "number", min=0.1, max=8, step=0.1, help="How many beats the explosion surge lasts.", default=0.5),
    "bg_level": _meta("Flash Brightness", "number", min=0.2, max=1, step=0.05, help="Peak brightness of the explosion flash.", default=1.0),
    # AWR-187: min dropped 0.2 -> 0 (v2's quick dim may settle fully dark).
    "bg_hold": _meta("Flash Hold", "number", min=0, max=1, step=0.05, help="Brightness the flash settles to after the surge.", default=0.7),
    "spark_a": _meta("Spark Color A", "rgb", help="First ember spark color."),
    "spark_b": _meta("Spark Color B", "rgb", help="Second ember spark color."),
}

for _key, _entry in CONTROL_META.items():
    _entry["color_sig"] = _key in _COLOR_SIG_KEYS


# Per-scene_ref default overrides for keys whose renderer fallback genuinely
# differs by scene_ref (confirmed by reading govee_frame_renderer.py; see
# docs/guides/led_pad.md for the audit table with exact source lines). Only
# `travel_beats` and `width` diverge today; every other key in CONTROL_META is
# either uniform across every scene_ref that actually reads it from `params`,
# or is never read from `params` at all (default None / "auto").
PARAM_DEFAULT_OVERRIDES: dict[str, dict[str, Any]] = {
    "groove_center_chase": {"travel_beats": 1.0},
    "post_drop_firework_chase": {"travel_beats": 1.0},
    "rt_post_drop_chase": {"travel_beats": 2.0, "width": 0.8},
    "rt_post_drop_nebula": {"travel_beats": 2.0, "width": 0.8},
    "rt_drop_chase": {"travel_beats": 2.0, "width": 0.8},
    "rt_drop_nebula": {"travel_beats": 2.0, "width": 0.8},
    # AWR-156: the Hz gate's duty fallback (0.3) differs from beat_strobe's
    # (0.5, the global CONTROL_META default).
    "drop_white_aggressive": {"duty": 0.3},
    "drop_strobe_colorway": {"duty": 0.3},
    # AWR-187: the redesigned firework's fallbacks diverge from v1's (which set
    # the CONTROL_META globals): quicker surge, much lower hold, denser +
    # shorter-lived embers, Hz-gate duty 0.3.
    "drop_firework_explosion_2": {
        "surge_beats": 0.25, "bg_hold": 0.25, "sparkle_density": 0.5,
        "sparkle_life_s": 0.15, "duty": 0.3,
    },
}


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
        "rt_groove_heartbeat",
    ),
    "Buildup": (
        "buildup_ramp_1",
        "buildup_ramp_2",
        "buildup_ramp_3",
        "buildup_white_zone_strobe",
        "buildup_white_half_strobe",
        "buildup_freestyle_nebula",
        "buildup_balloon_comet",
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
        "drop_strobe_colorway",
        "drop_firework_explosion",
        "drop_firework_explosion_2",
        "rainbow_ordered",
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
        "rt_post_drop_firework_remnants",
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
    overrides = PARAM_DEFAULT_OVERRIDES.get(str(scene_ref), {})
    for key in sorted(REALTIME_EFFECT_PARAM_KEYS.get(str(scene_ref), frozenset())):
        meta = dict(CONTROL_META[key])
        meta["key"] = key
        if key in overrides:
            meta["default"] = overrides[key]
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
