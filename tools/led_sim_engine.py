"""H612D simulator engine (AWR-196) — pure functions, no HTTP, no sockets.

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
import hashlib
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

H612D_MODEL = "H612D"
H612D_SEGMENTS = 60
H612D_LEDS_PER_SEGMENT = 6
H612D_PHYSICAL_LEDS = 360
H612D_LENGTH_MM = 14996.16


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
    _check_number(profile, "fps", 1, 120, errors)
    _check_number(profile, "latency_ms", -2000.0, 2000.0, errors)
    if profile.get("hold_mode") not in _HOLD_MODES:
        errors.append("hold_mode must be zoh or slew")
    _check_number(profile, "slew_ms", 0.0, 5000.0, errors)
    _check_number(profile, "bpm", 20.0, 300.0, errors)
    if profile.get("calibration_status") not in _CALIBRATION_STATUSES:
        errors.append(f"calibration_status must be one of {sorted(_CALIBRATION_STATUSES)}")
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


def frame_timestamps(frame_count: int, fps: int) -> list[int]:
    """Ideal-grid millisecond timestamps; measured captures can replace these."""
    return [int(round(index * 1000.0 / float(fps))) for index in range(max(0, int(frame_count)))]


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
    total = max(1, int(round(float(duration_s) * int(fps))))
    transport = _FrameCaptureTransport()
    runner = GoveeRealtimeRunner(
        transport,
        GoveeFrameRenderer(),
        segments=int(segments),
        fps=int(fps),
        time_fn=lambda: 0.0,
        sleep_fn=lambda _seconds: None,
    )
    runner.set_desired(EffectSpec(
        effect_name=name,
        params=dict(params or {}),
        seed=int(seed),
        applied_monotonic=0.0,
        sync_mode=str(sync_mode or ""),
        beat_division=float(beat_division or 0.0),
    ))
    for index in range(total):
        now = index / float(fps)
        runner._tick_once(  # noqa: SLF001 - exact production composition is the point of this offline tool
            BeatAnchor(
                deck=1,
                abs_beat_pos=now * float(bpm) / 60.0,
                bpm=float(bpm),
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
) -> None:
    segments = len(frames[0]) if frames else 0
    stamps = list(t_ms) if t_ms is not None else frame_timestamps(len(frames), fps)
    if len(stamps) != len(frames):
        raise ValueError("t_ms length must match frames length")
    lines = [json.dumps(
        {"v": 1, "kind": "header", "fps": int(fps), "segments": segments, "meta": dict(meta or {})},
        separators=(",", ":"),
    )]
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


CALIBRATION_SEQUENCE_NAMES = (
    "segment_map",
    "color_response",
    "timing_response",
)


def calibration_sequence(name: str, *, segments: int = H612D_SEGMENTS, fps: int = 60) -> dict[str, Any]:
    """Deterministic H612D measurement frames. Generates data; never sends it."""
    if name not in CALIBRATION_SEQUENCE_NAMES:
        raise ValueError(f"unknown calibration sequence: {name!r}")
    count = int(segments)
    rate = int(fps)
    if count != H612D_SEGMENTS:
        raise ValueError(f"segments must be {H612D_SEGMENTS}")
    if not (1 <= rate <= 120):
        raise ValueError("fps must be in [1, 120]")

    frames: list[Frame] = []
    markers: list[dict[str, Any]] = []

    def solid(color: tuple[int, int, int]) -> Frame:
        return [color] * count

    def add(frame: Frame, hold: int, label: str) -> None:
        markers.append({"frame": len(frames), "label": label})
        frames.extend([list(frame) for _ in range(max(1, int(hold)))])

    short = max(1, round(rate * 0.1))
    gap = max(1, round(rate / 30.0))
    sync = max(1, round(rate * 0.25))
    black = solid((0, 0, 0))
    white = solid((255, 255, 255))

    add(black, sync, "black reference")
    add(white, sync, "sync white")
    add(black, sync, "sync black")

    if name == "segment_map":
        for segment in range(count):
            frame = list(black)
            frame[segment] = (255, 255, 255)
            add(frame, short, f"segment {segment:02d}")
            add(black, gap, "gap")
    elif name == "color_response":
        levels = (0, 1, 2, 4, 8, 16, 32, 64, 96, 128, 160, 192, 224, 255)
        channels = (
            ("red", (1, 0, 0)),
            ("green", (0, 1, 0)),
            ("blue", (0, 0, 1)),
            ("white", (1, 1, 1)),
        )
        for label, mask in channels:
            for level in levels:
                add(solid(tuple(level * value for value in mask)), short, f"{label} {level}")
        for label, color in (
            ("cyan", (0, 255, 255)),
            ("magenta", (255, 0, 255)),
            ("yellow", (255, 255, 0)),
        ):
            for level in (64, 128, 255):
                add(solid(tuple(round(channel * level / 255) for channel in color)), short, f"{label} {level}")
    else:
        for hold in (1, 2, 3, 4, 6, 8, 12, 18, 30):
            add(white, hold, f"white {hold}f")
            add(black, hold, f"black {hold}f")
        for hold in (1, 2):
            for segment in range(count):
                frame = list(black)
                frame[segment] = (255, 255, 255)
                add(frame, hold, f"chase {hold}f segment {segment:02d}")

    add(black, sync, "final black")
    return {
        "name": name,
        "fps": rate,
        "segments": count,
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
        meta={"name": args.name, "seed": args.seed, "bpm": args.bpm, "params": params, "pipeline": "runtime"},
    )
    print(f"wrote {len(frames)} frames x {args.segments} segments -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
