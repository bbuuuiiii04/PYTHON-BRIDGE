"""H612D simulator engine (AWR-196) — pure functions, no HTTP, no sockets.

Offline tooling only. This module NEVER contacts the Govee device: no UDP, no
transport/discovery imports (`govee_realtime_transport`, `govee_lan_discovery`
are forbidden here), no subprocesses. Production frames are composed offline
by the real `GoveeRealtimeRunner` and collected immediately before its transport
boundary, so the sim reimplements neither effects nor runtime frame composition.
The runner is driven on an explicit ideal grid; this is not a live timing
capture. Device-side optical and timing behavior remains calibration work.

The pad lane's `tools.led_pad_lab` (AWR-193 fence) is imported READ-ONLY and
lazily inside function bodies; any failure there degrades lab features while
production rendering stays fully functional (that degradation is a contract —
the pad lane rewrites that module in parallel).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_parent_on_path() -> None:
    parent = str(_REPO_ROOT.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


try:
    from ..govee_frame_renderer import Frame, GoveeFrameRenderer, REALTIME_EFFECT_NAMES
    from ..govee_realtime_runner import EffectSpec, GoveeRealtimeRunner
    from ..led_models import BeatAnchor
except ImportError:  # run as `python3 -m tools.led_sim_engine` from the repo root
    _ensure_parent_on_path()
    from rb_ss_bridge_v2.govee_frame_renderer import (  # type: ignore
        Frame,
        GoveeFrameRenderer,
        REALTIME_EFFECT_NAMES,
    )
    from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec, GoveeRealtimeRunner  # type: ignore
    from rb_ss_bridge_v2.led_models import BeatAnchor  # type: ignore

EXAMPLE_PROFILE_PATH = _REPO_ROOT / "config" / "led_sim_profile.example.json"
DEFAULT_PROFILE_PATH = _REPO_ROOT / "config" / "led_sim_profile.json"
LAB_DIR = _REPO_ROOT / "config" / "led_lab"

_HOLD_MODES = {"zoh", "slew"}
_CALIBRATION_STATUSES = {"unmeasured", "relative", "measured"}
_CALIBRATION_DOMAINS = ("color", "timing", "spatial")

H612D_MODEL = "H612D"
H612D_SEGMENTS = 60
H612D_LEDS_PER_SEGMENT = 6
H612D_PHYSICAL_LEDS = 360
H612D_LENGTH_MM = 14996.16
H612D_JUNCTION_MM = H612D_LENGTH_MM / 2.0  # 7498.08 — absolute arc mm, never proportional
H612D_LED_PITCH_MM = H612D_LENGTH_MM / H612D_PHYSICAL_LEDS  # 41.656 mm/LED (fixed)
H612D_SEGMENT_MM = H612D_LENGTH_MM / H612D_SEGMENTS  # ~249.936 mm (~250 mm)
MM_PER_FOOT = 304.8

DEFAULT_ROOM_MM = (5216.0, 2284.0)
LAYOUT_PRESETS = ("perimeter", "snake", "custom")
# Legacy room-layout keys kept for old profiles; the room view reads `layout` only.
LEGACY_LAYOUT_KEYS = (
    "room_mm", "corner_segments", "start_corner", "direction",
    "wash_reach_mm", "wash_gain", "diffusion_width_seg",
)

FRAME_SOURCE_PRODUCTION_RUNNER_OFFLINE = "production_runner_offline"
TIMING_SOURCE_IDEAL_GRID = "ideal_grid"
MIN_FPS = 1
MAX_FPS = 120
MIN_BPM = 20.0
MAX_BPM = 300.0
MAX_DURATION_S = 30.0
MIN_BEAT_DIVISION = 0.01
MAX_BEAT_DIVISION = 16.0
CALIBRATION_SEQUENCE_VERSION = "h612d-cal-v2"
CALIBRATION_CAPTURE_FPS = (10, 20, 30, 40, 60)
FRAME_SOURCE_CALIBRATION_GENERATED = "calibration_generated_offline"


# --- profile -----------------------------------------------------------------

def load_profile(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("profile root must be a JSON object")
    return data


def _check_number(profile: Mapping[str, Any], key: str, lo: float, hi: float, errors: list[str]) -> None:
    value = profile.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not (lo <= float(value) <= hi):
        errors.append(f"{key} must be a number in [{lo}, {hi}]")


def validate_profile(profile: Mapping[str, Any]) -> list[str]:
    """Return error strings; empty list = valid. Unknown keys are allowed."""
    errors: list[str] = []
    if not isinstance(profile, Mapping):
        return ["profile must be a JSON object"]
    if profile.get("schema") != 1:
        errors.append("schema must be 1")
    if profile.get("device_model") != H612D_MODEL:
        errors.append(f"device_model must be {H612D_MODEL}")
    segments = profile.get("segments")
    if not isinstance(segments, int) or isinstance(segments, bool) or segments != H612D_SEGMENTS:
        errors.append(f"segments must be {H612D_SEGMENTS}")
        segments = None
    leds_per_segment = profile.get("leds_per_segment")
    if not isinstance(leds_per_segment, int) or isinstance(leds_per_segment, bool) or leds_per_segment != H612D_LEDS_PER_SEGMENT:
        errors.append(f"leds_per_segment must be {H612D_LEDS_PER_SEGMENT}")
    physical_leds = profile.get("physical_leds")
    if not isinstance(physical_leds, int) or isinstance(physical_leds, bool) or physical_leds != H612D_PHYSICAL_LEDS:
        errors.append(f"physical_leds must be {H612D_PHYSICAL_LEDS}")
    _check_number(profile, "strip_length_mm", H612D_LENGTH_MM, H612D_LENGTH_MM, errors)
    _check_number(profile, "gamma", 0.2, 5.0, errors)
    white = profile.get("white_point")
    if (
        not isinstance(white, (list, tuple))
        or len(white) != 3
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 4.0 for v in white)
    ):
        errors.append("white_point must be [r, g, b] gains in [0, 4]")
    _check_number(profile, "brightness", 0.0, 4.0, errors)
    _check_number(profile, "glow_radius", 0.1, 6.0, errors)
    _check_number(profile, "glow_gain", 0.0, 4.0, errors)
    _check_number(profile, "bleed", 0.0, 1.0, errors)
    fps = profile.get("fps")
    if not isinstance(fps, int) or isinstance(fps, bool) or not (MIN_FPS <= fps <= MAX_FPS):
        errors.append(f"fps must be an integer in [{MIN_FPS}, {MAX_FPS}]")
    _check_number(profile, "latency_ms", -2000.0, 2000.0, errors)
    if profile.get("hold_mode") not in _HOLD_MODES:
        errors.append("hold_mode must be zoh or slew")
    _check_number(profile, "slew_ms", 0.0, 5000.0, errors)
    _check_number(profile, "bpm", 20.0, 300.0, errors)
    if profile.get("calibration_status") not in _CALIBRATION_STATUSES:
        errors.append(f"calibration_status must be one of {sorted(_CALIBRATION_STATUSES)}")
    domains = profile.get("calibration_domains")
    if not isinstance(domains, Mapping):
        errors.append("calibration_domains must be an object")
    else:
        for domain in _CALIBRATION_DOMAINS:
            if domains.get(domain) not in _CALIBRATION_STATUSES:
                errors.append(
                    f"calibration_domains.{domain} must be one of {sorted(_CALIBRATION_STATUSES)}"
                )
        if all(domains.get(domain) in _CALIBRATION_STATUSES for domain in _CALIBRATION_DOMAINS):
            values = [domains[domain] for domain in _CALIBRATION_DOMAINS]
            expected = (
                "unmeasured" if all(value == "unmeasured" for value in values)
                else "measured" if all(value == "measured" for value in values)
                else "relative"
            )
            if profile.get("calibration_status") != expected:
                errors.append(f"calibration_status must be {expected!r} for calibration_domains")

    evidence = profile.get("calibration_evidence")
    if not isinstance(evidence, Mapping):
        errors.append("calibration_evidence must be an object")
    elif profile.get("calibration_status") in {"relative", "measured"}:
        required_strings = (
            "sequence_version", "sequence_sha256", "capture_sha256",
            "device_firmware", "phone_model", "capture_date",
        )
        for key in required_strings:
            if not isinstance(evidence.get(key), str) or not evidence[key].strip():
                errors.append(f"calibration_evidence.{key} must be a non-empty string")
        for key in ("sequence_sha256", "capture_sha256"):
            value = evidence.get(key)
            if isinstance(value, str) and (
                len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value)
            ):
                errors.append(f"calibration_evidence.{key} must be a 64-character SHA-256 hex digest")
        if not isinstance(evidence.get("camera_settings"), Mapping) or not evidence["camera_settings"]:
            errors.append("calibration_evidence.camera_settings must be a non-empty object")
        measured_fields = evidence.get("measured_fields")
        if (
            not isinstance(measured_fields, list)
            or not measured_fields
            or not all(isinstance(value, str) and value.strip() for value in measured_fields)
        ):
            errors.append("calibration_evidence.measured_fields must be a non-empty string list")
        if not isinstance(evidence.get("fit_residuals"), Mapping) or not evidence["fit_residuals"]:
            errors.append("calibration_evidence.fit_residuals must be a non-empty object")
        unknowns = evidence.get("remaining_unknowns")
        if not isinstance(unknowns, list) or not all(isinstance(value, str) for value in unknowns):
            errors.append("calibration_evidence.remaining_unknowns must be a string list")
        if profile.get("calibration_status") == "measured" and (
            not isinstance(evidence.get("reference_instrument"), str)
            or not evidence["reference_instrument"].strip()
        ):
            errors.append("calibration_evidence.reference_instrument is required for measured status")

    room = profile.get("room_mm")
    if room is not None:
        if (
            not isinstance(room, (list, tuple))
            or len(room) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) > 0 for v in room)
        ):
            errors.append("room_mm must be [width_mm, height_mm] with positive numbers")

    layout = profile.get("layout")
    if layout is not None:
        if not isinstance(layout, Mapping):
            errors.append("layout must be an object")
        else:
            preset = layout.get("preset")
            if preset not in LAYOUT_PRESETS:
                errors.append(f"layout.preset must be one of {list(LAYOUT_PRESETS)}")
            flip = layout.get("flip_chain", False)
            if not isinstance(flip, bool):
                errors.append("layout.flip_chain must be a boolean")
            points = layout.get("points_mm")
            if not isinstance(points, (list, tuple)) or len(points) < 2:
                errors.append("layout.points_mm must be a list of ≥2 [x, y] points")
            else:
                for index, point in enumerate(points):
                    if (
                        not isinstance(point, (list, tuple))
                        or len(point) != 2
                        or not all(
                            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
                            for v in point
                        )
                    ):
                        errors.append(f"layout.points_mm[{index}] must be a finite [x, y] pair")
                        break
    return errors


# --- strip layout (room polyline → LED positions) ----------------------------

def _as_xy(point: Any) -> tuple[float, float]:
    return (float(point[0]), float(point[1]))


def mm_to_feet(mm: float) -> float:
    return float(mm) / MM_PER_FOOT


def format_length_mm(mm: float) -> str:
    """Feet primary, metric secondary — e.g. '49.2 ft · 15.0 m'."""
    feet = mm_to_feet(mm)
    meters = float(mm) / 1000.0
    return f"{feet:.1f} ft · {meters:.1f} m"


def room_size_mm(profile: Mapping[str, Any] | None = None) -> tuple[float, float]:
    """Room width/height in mm; defaults to the operator room when absent."""
    room = (profile or {}).get("room_mm") if profile else None
    if (
        isinstance(room, (list, tuple))
        and len(room) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) > 0 for v in room)
    ):
        return (float(room[0]), float(room[1]))
    return (float(DEFAULT_ROOM_MM[0]), float(DEFAULT_ROOM_MM[1]))


def perimeter_preset_points(room_mm: tuple[float, float] | list[float] | None = None) -> list[list[float]]:
    """Rectangle loop with a real bottom-center gap; junction at top-center.

    Closed room perimeter is 2*(W+H). The strip is H612D_LENGTH_MM, so the gap
    is exactly perimeter - strip (3.84 mm for the operator 5216×2284 room). Path
    length equals the strip when perimeter ≥ strip; otherwise the path is nearly
    closed and layout_led_positions reports the shortfall. Never stretch LEDs.
    """
    width, height = room_size_mm({"room_mm": list(room_mm)} if room_mm is not None else None)
    perimeter = 2.0 * (width + height)
    gap = perimeter - H612D_LENGTH_MM
    if gap < 0.0:
        # Room too small for a full strip loop — tiny visual gap; shortfall warned later.
        gap = min(width * 0.001, 1.0)
    half = width / 2.0
    return [
        [half - gap / 2.0, 0.0],
        [0.0, 0.0],
        [0.0, height],
        [half, height],
        [width, height],
        [width, 0.0],
        [half + gap / 2.0, 0.0],
    ]


def _pack_serpentine_mm(
    *,
    start: tuple[float, float],
    length_mm: float,
    x_left: float,
    x_right: float,
    y_min: float,
    row_pitch: float,
) -> list[list[float]]:
    """Append a downward serpentine of exactly length_mm (or as much as fits)."""
    points: list[list[float]] = []
    x, y = float(start[0]), float(start[1])
    remaining = float(length_mm)
    at_right = abs(x - x_right) <= abs(x - x_left)
    pitch = max(20.0, float(row_pitch))
    guard = 0
    while remaining > 1e-6 and guard < 10000:
        guard += 1
        down_room = y - y_min
        if down_room > 1e-9:
            dv = min(down_room, remaining, pitch)
            y -= dv
            points.append([x, y])
            remaining -= dv
            if remaining <= 1e-6:
                break
        target_x = x_left if at_right else x_right
        span = abs(target_x - x)
        if span <= 1e-9:
            if y <= y_min + 1e-9:
                break
            continue
        move = min(span, remaining)
        x = x + (target_x - x) * (move / span)
        points.append([x, y])
        remaining -= move
        if move >= span - 1e-9:
            at_right = not at_right
        if y <= y_min + 1e-9 and remaining > 1e-6 and abs(x - target_x) <= 1e-9:
            # Tighten pitch at the floor to keep packing length.
            pitch = max(8.0, pitch * 0.5)
            if pitch <= 8.0 + 1e-9 and down_room <= 1e-9:
                break
    return points


def snake_preset_points(room_mm: tuple[float, float] | list[float] | None = None) -> list[list[float]]:
    """S-path in true room mm; total = strip length; junction at top-right bend.

    First half (exactly H612D_JUNCTION_MM): three horizontal runs + two rises
    ending at the top-right bend. Second half: downward serpentine packing the
    remaining H612D_JUNCTION_MM inside the room. No LED-spacing stretch.
    """
    width, height = room_size_mm({"room_mm": list(room_mm)} if room_mm is not None else None)
    half = H612D_JUNCTION_MM
    margin = min(200.0, min(width, height) * 0.05)
    avail_w = max(1.0, width - 2.0 * margin)
    avail_h = max(1.0, height - 2.0 * margin)

    # Prefer a taller first-half S (TR near the top).
    rise_span = min(avail_h * 0.55, half * 0.35)
    v = rise_span / 2.0
    run = (half - 2.0 * v) / 3.0
    if run > avail_w:
        run = avail_w
        v = (half - 3.0 * run) / 2.0
    if run <= 0.0 or v < 0.0:
        # Extreme rooms: fall back to max-width runs and whatever rise fits the half.
        run = min(avail_w, half / 3.0)
        v = max(0.0, (half - 3.0 * run) / 2.0)

    left = margin + (avail_w - run) / 2.0
    right = left + run
    y0 = margin
    y1 = y0 + v
    y2 = y1 + v
    if y2 > height - margin:
        scale = (height - margin - y0) / max(y2 - y0, 1e-9)
        y1 = y0 + (y1 - y0) * scale
        y2 = y0 + (y2 - y0) * scale
        v = (y2 - y0) / 2.0
        run = (half - 2.0 * v) / 3.0
        left = margin + (avail_w - run) / 2.0
        right = left + run

    points: list[list[float]] = [
        [left, y0],
        [right, y0],
        [right, y1],
        [left, y1],
        [left, y2],
        [right, y2],  # top-right bend = junction at absolute 7498.08 mm
    ]

    row_pitch = max(40.0, min(140.0, (y2 - margin) / 10.0))
    points.extend(_pack_serpentine_mm(
        start=(points[5][0], points[5][1]),
        length_mm=half,
        x_left=left,
        x_right=right,
        y_min=margin,
        row_pitch=row_pitch,
    ))
    return points


def preset_layout_points(preset: str, room_mm: tuple[float, float] | list[float] | None = None) -> list[list[float]]:
    if preset == "snake":
        return snake_preset_points(room_mm)
    if preset == "perimeter":
        return perimeter_preset_points(room_mm)
    raise ValueError(f"unknown layout preset: {preset!r}")


def default_layout(room_mm: tuple[float, float] | list[float] | None = None) -> dict[str, Any]:
    """Perimeter preset derived from room_mm — used when profile has no layout."""
    return {
        "preset": "perimeter",
        "points_mm": perimeter_preset_points(room_mm),
        "flip_chain": False,
    }


def resolve_layout(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return a concrete layout object; synthesize perimeter when missing."""
    layout = profile.get("layout")
    room = room_size_mm(profile)
    if not isinstance(layout, Mapping):
        return default_layout(room)
    preset = layout.get("preset", "custom")
    if preset not in LAYOUT_PRESETS:
        preset = "custom"
    points = layout.get("points_mm")
    if preset in ("perimeter", "snake") and (
        not isinstance(points, (list, tuple)) or len(points) < 2
    ):
        points = preset_layout_points(preset, room)
    elif not isinstance(points, (list, tuple)) or len(points) < 2:
        points = perimeter_preset_points(room)
        preset = "perimeter"
    flip = layout.get("flip_chain", False)
    return {
        "preset": preset if preset in LAYOUT_PRESETS else "custom",
        "points_mm": [[float(p[0]), float(p[1])] for p in points],
        "flip_chain": bool(flip) if isinstance(flip, bool) else False,
    }


def polyline_arc_length(points: list[tuple[float, float]] | list[list[float]]) -> float:
    total = 0.0
    for start, end in zip(points, points[1:]):
        x0, y0 = _as_xy(start)
        x1, y1 = _as_xy(end)
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def _point_at_arc_distance(
    points: list[tuple[float, float]] | list[list[float]],
    distance: float,
    total_length: float,
) -> tuple[float, float]:
    """Sample a polyline at arc distance in [0, total_length]. Zero-length edges skipped."""
    if not points:
        return (0.0, 0.0)
    if len(points) == 1 or total_length <= 0.0:
        return _as_xy(points[0])
    target = max(0.0, min(float(distance), total_length))
    if target >= total_length:
        return _as_xy(points[-1])
    walked = 0.0
    for start, end in zip(points, points[1:]):
        x0, y0 = _as_xy(start)
        x1, y1 = _as_xy(end)
        edge = math.hypot(x1 - x0, y1 - y0)
        if edge <= 1e-12:
            continue
        if walked + edge >= target:
            t = (target - walked) / edge
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        walked += edge
    return _as_xy(points[-1])


def layout_led_positions(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Place the strip on the layout polyline in true room millimetres.

    LED pitch is fixed (H612D_LED_PITCH_MM). Distances are absolute along the
    polyline — never stretched to fit the drawing. Path longer than the strip →
    strip ends at strip_length_mm; remaining path is excess guide. Path shorter →
    unplaced_mm shortfall (visible warning); LEDs beyond the path are null.

    Junction is always at absolute H612D_JUNCTION_MM when the path reaches it.

    Reference implementation; ledsim-view.js mirrors this — keep in lockstep.
    """
    layout = resolve_layout(profile)
    points = [_as_xy(p) for p in layout["points_mm"]]
    if layout["flip_chain"]:
        points = list(reversed(points))
    path_length = polyline_arc_length(points)
    strip_length = H612D_LENGTH_MM
    pitch = H612D_LED_PITCH_MM
    segment_mm = H612D_SEGMENT_MM
    placed_length = min(path_length, strip_length)
    unplaced_mm = max(0.0, strip_length - path_length)
    excess_path_mm = max(0.0, path_length - strip_length)
    if excess_path_mm < 1e-6:
        excess_path_mm = 0.0
    if unplaced_mm < 1e-6:
        unplaced_mm = 0.0

    def sample(arc_mm: float) -> tuple[float, float]:
        if path_length <= 1e-12:
            return points[0] if points else (0.0, 0.0)
        return _point_at_arc_distance(points, min(max(0.0, arc_mm), path_length), path_length)

    led_positions: list[tuple[float, float] | None] = []
    for index in range(H612D_PHYSICAL_LEDS):
        distance = (index + 0.5) * pitch
        if distance <= path_length + 1e-9:
            led_positions.append(sample(distance))
        else:
            led_positions.append(None)

    boundaries: list[tuple[float, float] | None] = []
    for index in range(H612D_SEGMENTS + 1):
        distance = index * segment_mm
        if distance <= path_length + 1e-9:
            boundaries.append(sample(distance))
        else:
            boundaries.append(None)

    junction = sample(H612D_JUNCTION_MM) if path_length + 1e-9 >= H612D_JUNCTION_MM else None
    strip_end = sample(placed_length)
    return {
        "leds_mm": led_positions,
        "segment_boundaries_mm": boundaries,
        "junction_mm": junction,
        "start_mm": sample(0.0),
        "end_mm": strip_end,
        "path_end_mm": sample(path_length),
        "points_mm": points,
        "path_length_mm": path_length,
        "strip_length_mm": strip_length,
        "placed_length_mm": placed_length,
        "unplaced_mm": unplaced_mm,
        "excess_path_mm": excess_path_mm,
        "led_pitch_mm": pitch,
        "segment_mm": segment_mm,
        "junction_arc_mm": H612D_JUNCTION_MM,
        "flip_chain": bool(layout["flip_chain"]),
        "preset": layout["preset"],
        "path_label": format_length_mm(path_length),
        "strip_label": format_length_mm(strip_length),
    }


def save_profile(path: Path | str, profile: Mapping[str, Any]) -> None:
    """Validate then atomically write (tmp + rename). Raises ValueError when invalid."""
    errors = validate_profile(profile)
    if errors:
        raise ValueError("; ".join(errors))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(target.parent), prefix=f"{target.name}.tmp-"
        ) as fp:
            temp_path = Path(fp.name)
            json.dump(dict(profile), fp, indent=2, sort_keys=True)
            fp.write("\n")
        temp_path.replace(target)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


# --- photometrics ------------------------------------------------------------

def apply_bleed(frame: list[tuple[int, int, int]] | list[list[int]], bleed: float) -> list[tuple[int, int, int]]:
    """Linear-strip 3-tap mix; endpoints never leak into each other.

    Reference implementation; the JS view mirrors it (ledsim-view.js) — keep in
    lockstep.
    """
    n = len(frame)
    if n == 0:
        return []
    mix = float(bleed)
    out: list[tuple[int, int, int]] = []
    for i in range(n):
        cur = frame[i]
        prev = frame[i - 1] if i else cur
        nxt = frame[i + 1] if i + 1 < n else cur
        out.append(tuple(
            max(0, min(255, int(round((1.0 - mix) * cur[c] + (mix / 2.0) * (prev[c] + nxt[c])))))
            for c in range(3)
        ))
    return out


def transform_color(rgb: tuple[int, int, int] | list[int], profile: Mapping[str, Any]) -> tuple[int, int, int]:
    """Reference H612D command-RGB to display-RGB transfer used by the browser.

    The defaults are identity assumptions. Calibration replaces gamma, channel
    gains, brightness, and glow parameters; no value here claims measured
    hardware behavior.
    """
    gamma = float(profile.get("gamma", 1.0))
    brightness = float(profile.get("brightness", 1.0))
    gains = profile.get("white_point", (1.0, 1.0, 1.0))
    return tuple(
        max(0, min(255, int(round(
            255.0 * max(0.0, float(gains[c]) * brightness * (int(rgb[c]) / 255.0)) ** gamma
        ))))
        for c in range(3)
    )


def device_segments(frame: list[tuple[int, int, int]] | list[list[int]], profile: Mapping[str, Any]) -> list[tuple[int, int, int]]:
    """Apply the calibrated transfer and linear optical bleed to 60 commands."""
    return apply_bleed([transform_color(pixel, profile) for pixel in frame], float(profile.get("bleed", 0.0)))


def expand_segments(
    frame: list[tuple[int, int, int]] | list[list[int]],
    leds_per_segment: int = H612D_LEDS_PER_SEGMENT,
) -> list[tuple[int, int, int]]:
    """Expand each logical H612D segment into its six physical emitters."""
    repeat = max(1, int(leds_per_segment))
    return [tuple(int(channel) for channel in pixel) for pixel in frame for _ in range(repeat)]


def validate_fps(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not (MIN_FPS <= value <= MAX_FPS):
        raise ValueError(f"fps must be an integer in [{MIN_FPS}, {MAX_FPS}]")
    return value


def validate_render_timing(
    *, fps: Any, duration_s: Any, bpm: Any, beat_division: Any = 0.0,
) -> tuple[int, float, float, float]:
    rate = validate_fps(fps)
    values = {"duration_s": duration_s, "bpm": bpm, "beat_division": beat_division}
    normalized: dict[str, float] = {}
    for name, value in values.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("duration_s, bpm, and beat_division must be finite numbers")
        try:
            normalized[name] = float(value)
        except (OverflowError, ValueError):
            raise ValueError("duration_s, bpm, and beat_division must be finite numbers") from None
        if not math.isfinite(normalized[name]):
            raise ValueError("duration_s, bpm, and beat_division must be finite numbers")
    duration = normalized["duration_s"]
    tempo = normalized["bpm"]
    division = normalized["beat_division"]
    if not (0.0 < duration <= MAX_DURATION_S):
        raise ValueError(f"duration_s must be in (0, {MAX_DURATION_S:g}]")
    if not (MIN_BPM <= tempo <= MAX_BPM):
        raise ValueError(f"bpm must be in [{MIN_BPM:g}, {MAX_BPM:g}]")
    if division != 0.0 and not (MIN_BEAT_DIVISION <= division <= MAX_BEAT_DIVISION):
        raise ValueError(
            f"beat_division must be 0 or in [{MIN_BEAT_DIVISION:g}, {MAX_BEAT_DIVISION:g}]"
        )
    return rate, duration, tempo, division


def frame_timestamps(frame_count: int, fps: int) -> list[int]:
    """Ideal-grid millisecond timestamps; measured captures can replace these."""
    rate = validate_fps(fps)
    return [int(round(index * 1000.0 / float(rate))) for index in range(max(0, int(frame_count)))]


# --- render adapter ----------------------------------------------------------

def render_frames(
    name: str,
    *,
    params: Mapping[str, Any] | None,
    seed: int,
    fps: int,
    duration_s: float,
    bpm: float,
    segments: int,
    max_frames: int | None = None,
) -> list[Frame]:
    """Drive the production renderer; deterministic for identical args.

    beat/local_t/frame_index derivation mirrors tools/led_pad_lab.py
    render_preview_frames exactly (beats = duration_s*bpm/60, then the same
    rounding chain) so sim frames match lab-preview frames for the same
    (effect, params, seed, bpm, fps).
    """
    rate, duration, tempo, _ = validate_render_timing(fps=fps, duration_s=duration_s, bpm=bpm)
    renderer = GoveeFrameRenderer()
    beats = duration * tempo / 60.0
    total = max(1, int(round(beats * 60.0 / tempo * rate)))
    if max_frames is not None:
        total = min(int(max_frames), total)
    frames: list[Frame] = []
    for index in range(total):
        t = index / float(rate)
        frames.append(renderer.render(
            name,
            beat_pos=t * tempo / 60.0,
            local_t=t,
            frame_index=index,
            params=params,
            segments=segments,
            seed=seed,
        ))
    return frames


class _FrameCaptureTransport:
    """Tool-only runner sink. Same tiny surface as the production transport."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def activate(self) -> bool:
        return True

    def deactivate(self) -> bool:
        return True

    def set_brightness(self, _value: int) -> bool:
        return True

    def send_frame(self, frame: Frame) -> bool:
        self.frames.append(list(frame))
        return True

    def blackout(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def status(self) -> dict[str, Any]:
        return {"frames_sent": len(self.frames), "send_error_count": 0, "last_error": ""}


def render_runtime_frames(
    name: str,
    *,
    params: Mapping[str, Any] | None,
    seed: int,
    fps: int,
    duration_s: float,
    bpm: float,
    segments: int,
    sync_mode: str = "",
    beat_division: float = 0.0,
) -> list[Frame]:
    """Capture the same runner composition that feeds the production transport.

    This stays single-threaded and offline: the runner receives a capture sink,
    a deterministic monotonic clock, and neutral CFX anchors. Device behavior
    begins after this frame boundary and is calibrated separately.
    """
    rate, duration, tempo, division = validate_render_timing(
        fps=fps, duration_s=duration_s, bpm=bpm, beat_division=beat_division,
    )
    total = max(1, int(round(duration * rate)))
    transport = _FrameCaptureTransport()
    runner = GoveeRealtimeRunner(
        transport,
        GoveeFrameRenderer(),
        segments=int(segments),
        fps=rate,
        time_fn=lambda: 0.0,
        sleep_fn=lambda _seconds: None,
    )
    runner.set_desired(EffectSpec(
        effect_name=name,
        params=dict(params or {}),
        seed=int(seed),
        applied_monotonic=0.0,
        sync_mode=str(sync_mode or ""),
        beat_division=division,
    ))
    for index in range(total):
        now = index / float(rate)
        runner._tick_once(  # noqa: SLF001 - exact production composition is the point of this offline tool
            BeatAnchor(
                deck=1,
                abs_beat_pos=now * tempo / 60.0,
                bpm=tempo,
                captured_monotonic=now,
                playing=True,
                permitted=True,
            ),
            now,
        )
    if len(transport.frames) != total:
        raise RuntimeError(f"runtime capture produced {len(transport.frames)} frames, expected {total}")
    return transport.frames


# --- lab bridge (guarded; AWR-193 fence) --------------------------------------

def _import_lab():
    """Lazy READ-ONLY import of the pad lane's lab module (rewritten in parallel)."""
    _ensure_parent_on_path()
    import importlib

    return importlib.import_module("rb_ss_bridge_v2.tools.led_pad_lab")


def lab_catalog() -> dict[str, Any]:
    try:
        lab = _import_lab()
        registry = lab.LabRegistry(LAB_DIR)
        drafts = registry.list() if registry.path.exists() else []
        return {"ok": True, "drafts": drafts, "error": ""}
    except Exception as exc:
        return {"ok": False, "drafts": [], "error": str(exc)}


def render_lab_frames(
    name: str,
    *,
    params: Mapping[str, Any] | None,
    seed: int,
    fps: int,
    duration_s: float,
    bpm: float,
    segments: int,
    max_frames: int = 10000,
) -> dict[str, Any]:
    try:
        lab = _import_lab()
        registry = lab.LabRegistry(LAB_DIR)

        def fn_for(draft_name: str) -> str:
            # Mirrors the pad's non-throwing name-first/fn-fallback resolver.
            try:
                entry = registry.get(str(draft_name))
            except Exception:
                return str(draft_name)
            return str(entry.get("fn") or draft_name)

        renderer = lab.LabRenderer(registry.module_path, fn_for=fn_for)
        renderer.reload()
        if renderer.last_error:
            return {"ok": False, "frames": [], "error": renderer.last_error}
        scene = name if str(name).startswith("lab_") else f"lab_{name}"
        beats = float(duration_s) * float(bpm) / 60.0
        frames = lab.render_preview_frames(
            renderer,
            scene,
            params=dict(params or {}),
            segments=int(segments),
            seed=int(seed),
            fps=int(fps),
            bpm=float(bpm),
            beats=beats,
            max_frames=int(max_frames),
        )
        return {"ok": True, "frames": frames, "error": ""}
    except Exception as exc:
        return {"ok": False, "frames": [], "error": str(exc)}


# --- production looks source ---------------------------------------------------

def look_params_catalog() -> dict[str, Any]:
    """Effect name + params per realtime look, from the live config else example.

    Fails closed with an error string when the shape surprises us; never guesses
    key names. The sim only READS this config.
    """
    live = _REPO_ROOT / "config" / "led_look_director.json"
    example = _REPO_ROOT / "config" / "led_look_director.example.json"
    path = live if live.exists() else example
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "looks": {}, "error": f"{path.name}: {exc}", "source": path.name}
    looks = data.get("looks") if isinstance(data, dict) else None
    if not isinstance(looks, dict):
        return {"ok": False, "looks": {}, "error": f"{path.name}: expected top-level 'looks' object", "source": path.name}
    out: dict[str, Any] = {}
    for look_name in sorted(looks):
        look = looks[look_name]
        if not isinstance(look, dict) or look.get("action") != "realtime":
            continue
        effect = look.get("scene_ref")
        params = look.get("params", {})
        if not isinstance(effect, str) or not effect or not isinstance(params, dict):
            return {
                "ok": False,
                "looks": {},
                "error": f"{path.name}: realtime look {look_name!r} has unexpected scene_ref/params shape",
                "source": path.name,
            }
        digest = hashlib.blake2b(look_name.encode("utf-8"), digest_size=8).digest()
        seed = int.from_bytes(digest, "big", signed=False) & 0x7FFFFFFF
        out[look_name] = {
            "effect": effect,
            "params": params,
            "params_stage": "pre_runtime_injection",
            "known": effect in REALTIME_EFFECT_NAMES,
            "seed": seed,
            "sync_mode": str(params.get("sync_mode") or ""),
            "beat_division": float(params.get("beat_division") or 0.0),
        }
    return {"ok": True, "looks": out, "error": "", "source": path.name}


# --- frames-JSONL codec --------------------------------------------------------

def write_frames_jsonl(
    path: Path | str,
    frames: list[Frame],
    *,
    fps: int,
    meta: Mapping[str, Any] | None = None,
    t_ms: list[int] | None = None,
    duration_ms: int | None = None,
) -> None:
    rate = validate_fps(fps)
    if duration_ms is not None and (
        not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0
    ):
        raise ValueError("duration_ms must be a non-negative integer")
    segments = len(frames[0]) if frames else 0
    for frame in frames:
        if len(frame) != segments:
            raise ValueError("all frames must have the same segment count")
        if any(
            not isinstance(pixel, (list, tuple))
            or len(pixel) != 3
            or any(not isinstance(channel, int) or isinstance(channel, bool) or not (0 <= channel <= 255)
                   for channel in pixel)
            for pixel in frame
        ):
            raise ValueError("each pixel must be [r, g, b] ints in [0, 255]")
    stamps = list(t_ms) if t_ms is not None else frame_timestamps(len(frames), rate)
    if len(stamps) != len(frames):
        raise ValueError("t_ms length must match frames length")
    if any(not isinstance(stamp, int) or isinstance(stamp, bool) or stamp < 0 for stamp in stamps):
        raise ValueError("t_ms values must be non-negative integers")
    if any(current < previous for previous, current in zip(stamps, stamps[1:])):
        raise ValueError("t_ms values must be nondecreasing")
    if duration_ms is not None and stamps and duration_ms <= stamps[-1]:
        raise ValueError("duration_ms must be greater than the final t_ms")
    header = {"v": 1, "kind": "header", "fps": rate, "segments": segments, "meta": dict(meta or {})}
    if duration_ms is not None:
        header["duration_ms"] = duration_ms
    lines = [json.dumps(header, separators=(",", ":"))]
    for stamp, frame in zip(stamps, frames):
        lines.append(json.dumps({
            "v": 1,
            "t_ms": int(stamp),
            "frame": [[int(r), int(g), int(b)] for r, g, b in frame],
        }, separators=(",", ":")))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_frames_jsonl(path: Path | str) -> dict[str, Any]:
    """Fails closed per file: any bad line raises ValueError with its line number."""
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines()

    def fail(line_no: int, message: str) -> None:
        raise ValueError(f"{target}:{line_no}: {message}")

    if not lines:
        fail(1, "empty frames-jsonl file")
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        fail(1, f"invalid JSON header: {exc}")
    if (
        not isinstance(header, dict)
        or not isinstance(header.get("v"), int)
        or isinstance(header.get("v"), bool)
        or header.get("v") != 1
        or header.get("kind") != "header"
    ):
        fail(1, "first line must be a v=1 header object")
    fps = header.get("fps")
    segments = header.get("segments")
    if not isinstance(fps, int) or isinstance(fps, bool) or not (MIN_FPS <= fps <= MAX_FPS):
        fail(1, "header fps must be a positive integer")
    if not isinstance(segments, int) or isinstance(segments, bool) or segments < 1:
        fail(1, "header segments must be a positive integer")
    duration_ms = header.get("duration_ms")
    if "duration_ms" in header and (
        not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0
    ):
        fail(1, "header duration_ms must be a non-negative integer")
    meta = header.get("meta")
    if not isinstance(meta, dict):
        fail(1, "header meta must be an object")

    frames: list[list[list[int]]] = []
    t_ms: list[int] = []
    for line_no, raw in enumerate(lines[1:], start=2):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail(line_no, f"invalid JSON: {exc}")
        if (
            not isinstance(obj, dict)
            or not isinstance(obj.get("v"), int)
            or isinstance(obj.get("v"), bool)
            or obj.get("v") != 1
        ):
            fail(line_no, "frame line must be a v=1 object")
        stamp = obj.get("t_ms")
        if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp < 0:
            fail(line_no, "t_ms must be a non-negative integer")
        if t_ms and stamp < t_ms[-1]:
            fail(line_no, "t_ms must be nondecreasing")
        frame = obj.get("frame")
        if not isinstance(frame, list) or len(frame) != segments:
            fail(line_no, f"frame must be a list of {segments} pixels")
        for pixel in frame:
            if (
                not isinstance(pixel, list)
                or len(pixel) != 3
                or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in pixel)
            ):
                fail(line_no, "each pixel must be [r, g, b] ints in [0, 255]")
        frames.append(frame)
        t_ms.append(stamp)
    if duration_ms is not None and t_ms and duration_ms <= t_ms[-1]:
        fail(1, "header duration_ms must be greater than the final t_ms")
    if duration_ms is None:
        duration_ms = int(round(t_ms[-1] + 1000.0 / fps)) if t_ms else 0
        duration_source = "derived_from_timestamps_and_fps"
    else:
        duration_source = "header"
    return {
        "fps": fps,
        "segments": segments,
        "duration_ms": duration_ms,
        "duration_source": duration_source,
        "meta": meta,
        "frames": frames,
        "t_ms": t_ms,
    }


# --- test cards ----------------------------------------------------------------

_CARD_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "gray50": (128, 128, 128),
}

TEST_CARD_KINDS = tuple(sorted(_CARD_COLORS)) + ("single_segment",)


def test_card_frames(kind: str, segments: int) -> list[Frame]:
    """Static photometric calibration references (1 frame each)."""
    count = max(0, int(segments))
    if kind == "single_segment":
        frame: list[tuple[int, int, int]] = [(0, 0, 0)] * count
        if count:
            frame[0] = (255, 255, 255)
        return [frame]
    color = _CARD_COLORS.get(kind)
    if color is None:
        raise ValueError(f"unknown test card kind: {kind!r}")
    return [[color] * count]


CALIBRATION_SEQUENCE_NAMES = (
    "segment_map",
    "color_response",
    "timing_response",
)


def calibration_sequence(name: str, *, segments: int = H612D_SEGMENTS, fps: int = 60) -> dict[str, Any]:
    """Deterministic H612D measurement frames. Generates data; never sends it."""
    if name not in CALIBRATION_SEQUENCE_NAMES:
        raise ValueError(f"unknown calibration sequence: {name!r}")
    if not isinstance(segments, int) or isinstance(segments, bool) or segments != H612D_SEGMENTS:
        raise ValueError(f"segments must be {H612D_SEGMENTS}")
    count = segments
    rate = validate_fps(fps)

    frames: list[Frame] = []
    markers: list[dict[str, Any]] = []

    def solid(color: tuple[int, int, int]) -> Frame:
        return [color] * count

    def add(frame: Frame, hold: int, label: str) -> None:
        markers.append({"frame": len(frames), "label": label})
        frames.extend([list(frame) for _ in range(max(1, int(hold)))])

    short = max(1, round(rate * 0.1))
    gap = max(1, round(rate * 0.05))
    sync = max(1, round(rate * 0.5))
    black = solid((0, 0, 0))
    white = solid((255, 255, 255))

    add(black, sync, "black reference")
    add(white, sync, "sync white")
    add(black, sync, "sync black")

    if name == "segment_map":
        for segment in range(count):
            for level in (16, 64, 255):
                frame = list(black)
                frame[segment] = (level, level, level)
                add(frame, max(1, round(rate * 0.25)), f"segment {segment:02d} level {level}")
                add(black, gap, "gap")
    elif name == "color_response":
        levels = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 160, 192, 224, 255)
        channels = (
            ("red", (1, 0, 0)),
            ("green", (0, 1, 0)),
            ("blue", (0, 0, 1)),
            ("white", (1, 1, 1)),
        )
        loads = ("isolated", "alternating", "full")
        patch_hold = max(1, round(rate * 0.75))
        patch_gap = max(1, round(rate * 0.1))

        def load_frame(color: tuple[int, int, int], load: str) -> Frame:
            if load == "full":
                return solid(color)
            frame = list(black)
            indices = (count // 2,) if load == "isolated" else range(0, count, 2)
            for index in indices:
                frame[index] = color
            return frame

        for label, mask in channels:
            for load in loads:
                for level in levels:
                    color = tuple(level * value for value in mask)
                    add(load_frame(color, load), patch_hold, f"{label} {level} {load}")
                    add(black, patch_gap, "black reset")
        for label, color in (
            ("cyan", (0, 255, 255)),
            ("magenta", (255, 0, 255)),
            ("yellow", (255, 255, 0)),
            ("orange", (255, 96, 0)),
            ("violet", (160, 0, 255)),
        ):
            for load in loads:
                for level in (64, 128, 255):
                    scaled = tuple(round(channel * level / 255) for channel in color)
                    add(load_frame(scaled, load), patch_hold, f"{label} {level} {load}")
                    add(black, patch_gap, "black reset")
    else:
        def coded_timing_frame(code: int, pass_index: int) -> Frame:
            """Constant-load visible counter: Gray + complement + binary + checks."""
            frame = list(black)
            gray = code ^ (code >> 1)
            for bit in range(8):
                gray_on = bool(gray & (1 << bit))
                binary_on = bool(code & (1 << bit))
                for offset in (0, 16):
                    frame[offset + bit] = (255, 255, 255) if gray_on else (0, 0, 0)
                    frame[offset + 8 + bit] = (0, 0, 0) if gray_on else (255, 255, 255)
                frame[32 + bit] = (255, 255, 255) if binary_on else (0, 0, 0)
                frame[40 + bit] = (0, 0, 0) if binary_on else (255, 255, 255)
            for bit, start in enumerate((48, 50)):
                on = bool(pass_index & (1 << bit))
                frame[start] = (255, 255, 255) if on else (0, 0, 0)
                frame[start + 1] = (0, 0, 0) if on else (255, 255, 255)
            parity = bool(code.bit_count() & 1)
            frame[52] = (255, 255, 255) if parity else (0, 0, 0)
            frame[53] = (0, 0, 0) if parity else (255, 255, 255)
            frame[54 + (code % 6)] = (255, 255, 255)
            return frame

        for pass_index, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
            add(black, short, f"timing pass {pass_index + 1} preamble black")
            add(solid(color), short, f"timing pass {pass_index + 1} preamble color")
            add(black, short, f"timing pass {pass_index + 1} preamble black 2")
            for code in range(256):
                add(coded_timing_frame(code, pass_index), 1, f"timing pass {pass_index + 1} code {code:03d}")
        for hold in (1, 2, 3, 4, 6, 8, 12, 18, 30):
            add(white, hold, f"white {hold}f")
            add(black, hold, f"black {hold}f")
        for hold in (1, 2):
            for segment in range(count):
                frame = list(black)
                frame[segment] = (255, 255, 255)
                add(frame, hold, f"chase {hold}f segment {segment:02d}")

    add(black, sync, "final black")
    payload = {
        "sequence_version": CALIBRATION_SEQUENCE_VERSION,
        "name": name,
        "fps": rate,
        "segments": count,
        "frames": frames,
        "markers": markers,
    }
    sequence_sha256 = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "name": name,
        "fps": rate,
        "segments": count,
        "duration_ms": int(round(len(frames) * 1000.0 / rate)),
        "duration_source": "generated_exact",
        "frame_source": FRAME_SOURCE_CALIBRATION_GENERATED,
        "timing_source": TIMING_SOURCE_IDEAL_GRID,
        "sequence_version": CALIBRATION_SEQUENCE_VERSION,
        "sequence_sha256": sequence_sha256,
        "frames": frames,
        "t_ms": frame_timestamps(len(frames), rate),
        "markers": markers,
    }


# --- CLI -------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LED sim engine offline tools")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render-jsonl", help="render an effect to a frames-JSONL file")
    render.add_argument("--name", required=True, help="production effect name")
    render.add_argument("--out", required=True, help="output .jsonl path")
    render.add_argument("--params", default="{}", help="effect params as a JSON object")
    render.add_argument("--seed", type=int, default=0)
    render.add_argument("--fps", type=int, default=60)
    render.add_argument("--duration-s", type=float, default=4.0)
    render.add_argument("--bpm", type=float, default=128.0)
    render.add_argument("--segments", type=int, default=60)
    args = parser.parse_args(argv)

    params = json.loads(args.params)
    if not isinstance(params, dict):
        raise SystemExit("--params must be a JSON object")
    frames = render_runtime_frames(
        args.name,
        params=params,
        seed=args.seed,
        fps=args.fps,
        duration_s=args.duration_s,
        bpm=args.bpm,
        segments=args.segments,
    )
    write_frames_jsonl(
        args.out,
        frames,
        fps=args.fps,
        duration_ms=int(round(args.duration_s * 1000.0)),
        meta={
            "name": args.name,
            "seed": args.seed,
            "bpm": args.bpm,
            "params": params,
            "pipeline": "runtime",
            "frame_source": FRAME_SOURCE_PRODUCTION_RUNNER_OFFLINE,
            "timing_source": TIMING_SOURCE_IDEAL_GRID,
        },
    )
    print(f"wrote {len(frames)} frames x {args.segments} segments -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
