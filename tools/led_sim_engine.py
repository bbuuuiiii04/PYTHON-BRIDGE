"""LED room simulator engine (AWR-196) — pure functions, no HTTP, no sockets.

Offline tooling only. This module NEVER contacts the Govee device: no UDP, no
transport/discovery imports (`govee_realtime_transport`, `govee_lan_discovery`
are forbidden here), no subprocesses. Frames come from the real production
renderer (`GoveeFrameRenderer`) — the sim reimplements zero effects.

The pad lane's `tools.led_pad_lab` (AWR-193 fence) is imported READ-ONLY and
lazily inside function bodies; any failure there degrades lab features while
production rendering stays fully functional (that degradation is a contract —
the pad lane rewrites that module in parallel).
"""
from __future__ import annotations

import argparse
import json
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
except ImportError:  # run as `python3 -m tools.led_sim_engine` from the repo root
    _ensure_parent_on_path()
    from rb_ss_bridge_v2.govee_frame_renderer import (  # type: ignore
        Frame,
        GoveeFrameRenderer,
        REALTIME_EFFECT_NAMES,
    )

EXAMPLE_PROFILE_PATH = _REPO_ROOT / "config" / "led_sim_profile.example.json"
DEFAULT_PROFILE_PATH = _REPO_ROOT / "config" / "led_sim_profile.json"
LAB_DIR = _REPO_ROOT / "config" / "led_lab"

_DIRECTIONS = {"cw", "ccw"}
_HOLD_MODES = {"zoh", "slew"}


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
    segments = profile.get("segments")
    if not isinstance(segments, int) or isinstance(segments, bool) or not (1 <= segments <= 1000):
        errors.append("segments must be an integer in [1, 1000]")
        segments = None
    room = profile.get("room_mm")
    if (
        not isinstance(room, (list, tuple))
        or len(room) != 2
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in room)
    ):
        errors.append("room_mm must be [width_mm, height_mm] with positive numbers")
    corners = profile.get("corner_segments")
    if (
        not isinstance(corners, (list, tuple))
        or len(corners) != 4
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in corners)
    ):
        errors.append("corner_segments must be a list of 4 numbers")
    else:
        if segments is not None and not all(0 <= float(v) < segments for v in corners):
            errors.append(f"corner_segments values must lie in [0, {segments})")
        if not all(float(a) < float(b) for a, b in zip(corners, corners[1:])):
            errors.append("corner_segments must be strictly ascending")
    start = profile.get("start_corner")
    if not isinstance(start, int) or isinstance(start, bool) or not (0 <= start <= 3):
        errors.append("start_corner must be an integer in [0, 3]")
    if profile.get("direction") not in _DIRECTIONS:
        errors.append("direction must be cw or ccw")
    _check_number(profile, "gamma", 0.2, 5.0, errors)
    white = profile.get("white_point")
    if (
        not isinstance(white, (list, tuple))
        or len(white) != 3
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 4.0 for v in white)
    ):
        errors.append("white_point must be [r, g, b] gains in [0, 4]")
    _check_number(profile, "brightness", 0.0, 4.0, errors)
    _check_number(profile, "diffusion_width_seg", 0.1, 10.0, errors)
    _check_number(profile, "bleed", 0.0, 1.0, errors)
    _check_number(profile, "wash_reach_mm", 0.0, 100000.0, errors)
    _check_number(profile, "wash_gain", 0.0, 10.0, errors)
    _check_number(profile, "fps", 1, 120, errors)
    _check_number(profile, "latency_ms", -2000.0, 2000.0, errors)
    if profile.get("hold_mode") not in _HOLD_MODES:
        errors.append("hold_mode must be zoh or slew")
    _check_number(profile, "slew_ms", 0.0, 5000.0, errors)
    _check_number(profile, "bpm", 20.0, 300.0, errors)
    return errors


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


# --- geometry ----------------------------------------------------------------

def _room_corners(room_mm: tuple[float, float]) -> list[tuple[float, float]]:
    # Top-down view, y grows downward; corners in clockwise order.
    width, height = float(room_mm[0]), float(room_mm[1])
    return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]


_INWARD_NORMALS = [(0.0, 1.0), (-1.0, 0.0), (0.0, -1.0), (1.0, 0.0)]  # per physical wall 0-3


def segment_geometry(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map each strip segment onto the rectangle perimeter.

    The strip is a closed ring of `segments`; `corner_segments` (fractional
    strip positions) splits it into 4 arcs; arc k maps linearly onto the k-th
    wall traversed starting at room corner `start_corner` following
    `direction`. This function is THE calibration target — the UI's dragging
    just edits the profile and re-runs it.
    """
    segments = int(profile["segments"])
    corners_pos = [float(v) for v in profile["corner_segments"]]
    start = int(profile["start_corner"])
    direction = str(profile["direction"])
    room = _room_corners(tuple(profile["room_mm"]))

    # Traversed wall k: from room corner a_k to b_k; its physical wall index.
    walls: list[tuple[tuple[float, float], tuple[float, float], int]] = []
    for k in range(4):
        if direction == "cw":
            a = (start + k) % 4
            b = (a + 1) % 4
            wall_index = a
        else:
            a = (start - k) % 4
            b = (a - 1) % 4
            wall_index = b  # physical wall j connects corner j -> j+1
        walls.append((room[a], room[b], wall_index))

    # Arc k covers ring interval [corners_pos[k], next); the last arc wraps.
    arc_lengths = [
        (corners_pos[k + 1] - corners_pos[k]) if k < 3 else (segments - corners_pos[3] + corners_pos[0])
        for k in range(4)
    ]

    def strip_pos_to_point(pos: float) -> tuple[float, float, int]:
        rel = (pos - corners_pos[0]) % segments
        offset = 0.0
        for k in range(4):
            if rel < offset + arc_lengths[k] or k == 3:
                frac = (rel - offset) / arc_lengths[k]
                (ax, ay), (bx, by), wall_index = walls[k]
                return (ax + (bx - ax) * frac, ay + (by - ay) * frac, wall_index)
            offset += arc_lengths[k]
        raise AssertionError("unreachable")

    out: list[dict[str, Any]] = []
    for i in range(segments):
        cx, cy, wall_index = strip_pos_to_point(i + 0.5)
        x0, y0, _ = strip_pos_to_point(float(i))
        x1, y1, _ = strip_pos_to_point(float((i + 1) % segments))
        nx, ny = _INWARD_NORMALS[wall_index]
        out.append({
            "segment": i,
            "x_mm": cx,
            "y_mm": cy,
            "nx": nx,
            "ny": ny,
            "wall": wall_index,
            "x0_mm": x0,
            "y0_mm": y0,
            "x1_mm": x1,
            "y1_mm": y1,
        })
    return out


# --- photometrics ------------------------------------------------------------

def apply_bleed(frame: list[tuple[int, int, int]] | list[list[int]], bleed: float) -> list[tuple[int, int, int]]:
    """Ring-wrapped 3-tap mix: out[i] = (1-bleed)*f[i] + (bleed/2)*(f[i-1]+f[i+1]).

    Reference implementation; the JS view mirrors it (ledsim-view.js) — keep in
    lockstep.
    """
    n = len(frame)
    mix = float(bleed)
    out: list[tuple[int, int, int]] = []
    for i in range(n):
        prev, cur, nxt = frame[i - 1], frame[i], frame[(i + 1) % n]
        out.append(tuple(
            max(0, min(255, int(round((1.0 - mix) * cur[c] + (mix / 2.0) * (prev[c] + nxt[c])))))
            for c in range(3)
        ))
    return out


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
    renderer = GoveeFrameRenderer()
    beats = float(duration_s) * float(bpm) / 60.0
    total = max(1, int(round(beats * 60.0 / float(bpm) * int(fps))))
    if max_frames is not None:
        total = min(int(max_frames), total)
    frames: list[Frame] = []
    for index in range(total):
        t = index / float(fps)
        frames.append(renderer.render(
            name,
            beat_pos=t * float(bpm) / 60.0,
            local_t=t,
            frame_index=index,
            params=params,
            segments=segments,
            seed=seed,
        ))
    return frames


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
        out[look_name] = {"effect": effect, "params": params, "known": effect in REALTIME_EFFECT_NAMES}
    return {"ok": True, "looks": out, "error": "", "source": path.name}


# --- frames-JSONL codec --------------------------------------------------------

def write_frames_jsonl(path: Path | str, frames: list[Frame], *, fps: int, meta: Mapping[str, Any] | None = None) -> None:
    segments = len(frames[0]) if frames else 0
    lines = [json.dumps(
        {"v": 1, "kind": "header", "fps": int(fps), "segments": segments, "meta": dict(meta or {})},
        separators=(",", ":"),
    )]
    for index, frame in enumerate(frames):
        lines.append(json.dumps({
            "v": 1,
            "t_ms": int(round(index * 1000.0 / float(fps))),
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
    if not isinstance(header, dict) or header.get("v") != 1 or header.get("kind") != "header":
        fail(1, "first line must be a v=1 header object")
    fps = header.get("fps")
    segments = header.get("segments")
    if not isinstance(fps, int) or fps < 1:
        fail(1, "header fps must be a positive integer")
    if not isinstance(segments, int) or segments < 1:
        fail(1, "header segments must be a positive integer")
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
        if not isinstance(obj, dict) or obj.get("v") != 1:
            fail(line_no, "frame line must be a v=1 object")
        stamp = obj.get("t_ms")
        if not isinstance(stamp, int) or stamp < 0:
            fail(line_no, "t_ms must be a non-negative integer")
        frame = obj.get("frame")
        if not isinstance(frame, list) or len(frame) != segments:
            fail(line_no, f"frame must be a list of {segments} pixels")
        for pixel in frame:
            if (
                not isinstance(pixel, list)
                or len(pixel) != 3
                or not all(isinstance(c, int) and 0 <= c <= 255 for c in pixel)
            ):
                fail(line_no, "each pixel must be [r, g, b] ints in [0, 255]")
        frames.append(frame)
        t_ms.append(stamp)
    return {"fps": fps, "segments": segments, "meta": meta, "frames": frames, "t_ms": t_ms}


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
    frames = render_frames(
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
        meta={"name": args.name, "seed": args.seed, "bpm": args.bpm, "params": params},
    )
    print(f"wrote {len(frames)} frames x {args.segments} segments -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
