"""Pure frame renderer for Govee realtime/DreamView effects."""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Callable, Mapping

RGB = tuple[int, int, int]
Frame = list[RGB]
EffectFn = Callable[[float, float, int, Mapping[str, Any], int, int], Frame]

_EDM_DURATION_BEATS = 32.0


def _clamp_channel(value: Any) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(255, numeric))


def _color(value: Any, default: RGB = (255, 255, 255)) -> RGB:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return default
    return (
        _clamp_channel(value[0]),
        _clamp_channel(value[1]),
        _clamp_channel(value[2]),
    )


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, float(t)))
    return (
        _clamp_channel(a[0] + (b[0] - a[0]) * t),
        _clamp_channel(a[1] + (b[1] - a[1]) * t),
        _clamp_channel(a[2] + (b[2] - a[2]) * t),
    )


def _scale(c: RGB, amount: float) -> RGB:
    return (
        _clamp_channel(c[0] * amount),
        _clamp_channel(c[1] * amount),
        _clamp_channel(c[2] * amount),
    )


def _stable_int(*parts: Any) -> int:
    text = "|".join(str(part) for part in parts)
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False)


def _rng(*parts: Any) -> random.Random:
    return random.Random(_stable_int(*parts))


def _empty(segments: int, color: RGB = (0, 0, 0)) -> Frame:
    return [color for _ in range(max(0, int(segments)))]


def _distance_on_ring(index: int, pos: float, segments: int) -> float:
    diff = abs(float(index) - pos)
    return min(diff, max(0.0, float(segments) - diff))


def _dual_chase(
    *,
    beat: float,
    segments: int,
    loop_beats: float,
    offset_beats: float,
    color1: RGB,
    color2: RGB,
    width: float = 0.8,
    reverse_second: bool = False,
    bg: RGB = (0, 0, 0),
) -> Frame:
    if segments <= 0:
        return []
    loop_beats = max(0.001, float(loop_beats))
    pos1 = ((beat / loop_beats) % 1.0) * segments
    if reverse_second:
        pos2 = ((1.0 - (beat / loop_beats)) % 1.0) * segments
    else:
        pos2 = (((beat + offset_beats) / loop_beats) % 1.0) * segments
    frame = [bg for _ in range(segments)]
    for idx in range(segments):
        dist1 = _distance_on_ring(idx, pos1, segments)
        dist2 = _distance_on_ring(idx, pos2, segments)
        intensity1 = max(0.0, 1.0 - (dist1 / max(0.001, width)))
        intensity2 = max(0.0, 1.0 - (dist2 / max(0.001, width)))
        r = bg[0] * max(0.0, 1.0 - intensity1 - intensity2)
        g = bg[1] * max(0.0, 1.0 - intensity1 - intensity2)
        b = bg[2] * max(0.0, 1.0 - intensity1 - intensity2)
        r += color1[0] * intensity1 + color2[0] * intensity2
        g += color1[1] * intensity1 + color2[1] * intensity2
        b += color1[2] * intensity1 + color2[2] * intensity2
        frame[idx] = (_clamp_channel(r), _clamp_channel(g), _clamp_channel(b))
    return frame


def _sparkle_frame(
    *,
    segments: int,
    density: float,
    color: RGB | Callable[[int], RGB],
    seed: int,
    frame_index: int,
    beat_bucket: int,
    power: float = 1.5,
) -> Frame:
    density = max(0.0, min(1.0, float(density)))
    frame: Frame = []
    for idx in range(max(0, segments)):
        local_rng = _rng(seed, frame_index, beat_bucket, idx)
        if local_rng.random() >= density:
            frame.append((0, 0, 0))
            continue
        intensity = local_rng.random() ** power
        c = color(idx) if callable(color) else color
        frame.append(_scale(c, intensity))
    return frame


def _solid(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    return _empty(segments, _color(params.get("color"), (255, 255, 255)))


def _blackout(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    return _empty(segments)


def _beat_chase(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    bg = _color(params.get("bg"), (0, 0, 0))
    trail = max(0, int(params.get("trail", 3)))
    span_beats = max(0.001, float(params.get("span_beats", 1.0)))
    head = int(((beat % span_beats) / span_beats) * max(1, segments))
    frame = []
    for idx in range(max(0, segments)):
        dist = (idx - head) % max(1, segments)
        if dist == 0:
            frame.append(color)
        elif dist <= trail:
            amount = 1.0 - (dist / float(trail + 1))
            frame.append(_lerp(bg, color, amount))
        else:
            frame.append(bg)
    return frame


def _beat_strobe(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    subdivision = int(params.get("subdivision", 4))
    if subdivision not in {1, 2, 4, 8}:
        subdivision = 4
    duty = max(0.0, min(1.0, float(params.get("duty", 0.5))))
    on = ((beat * subdivision) % 1.0) < duty
    return _empty(segments, color if on else (0, 0, 0))


def _drop_burst(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    bg = _color(params.get("bg"), (0, 0, 0))
    decay = max(0.001, float(params.get("decay", 0.6)))
    if local_t > 4.0 * decay:
        return _empty(segments, bg)
    amount = math.exp(-max(0.0, local_t) / decay)
    return _empty(segments, _lerp(bg, color, amount))


def _breathe(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    period = max(0.001, float(params.get("period_beats", 4.0)))
    floor = max(0.0, min(1.0, float(params.get("floor", 0.1))))
    amount = floor + (1.0 - floor) * (0.5 - 0.5 * math.cos(2.0 * math.pi * beat / period))
    return _empty(segments, _scale(color, amount))


def _gradient_sweep(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color_a = _color(params.get("color_a"), (0, 0, 255))
    color_b = _color(params.get("color_b"), (0, 255, 255))
    speed = float(params.get("speed", 1.0))
    offset = (beat * speed) % 1.0
    frame = []
    for idx in range(max(0, segments)):
        t = ((idx / max(1, segments)) + offset) % 1.0
        tri = 1.0 - abs((t * 2.0) - 1.0)
        frame.append(_lerp(color_a, color_b, tri))
    return frame


def _sparkle(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    bg = _color(params.get("bg"), (0, 0, 0))
    density = float(params.get("density", 0.2))
    sparkles = _sparkle_frame(
        segments=segments,
        density=density,
        color=color,
        seed=seed,
        frame_index=frame_index,
        beat_bucket=int(beat * 16.0),
    )
    return [_lerp(bg, value, 1.0) if value != (0, 0, 0) else bg for value in sparkles]


def _color_pulse(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    bg = _color(params.get("bg"), (0, 0, 0))
    amount = max(0.0, 1.0 - ((beat % 1.0) / 0.5))
    return _empty(segments, _lerp(bg, color, amount))


def _bar_wipe(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color = _color(params.get("color"), (255, 255, 255))
    bg = _color(params.get("bg"), (0, 0, 0))
    filled = int(((beat % 4.0) / 4.0) * max(1, segments))
    return [color if idx < filled else bg for idx in range(max(0, segments))]


def _edm_color_for_look(name: str, beat: float) -> tuple[RGB, RGB]:
    if name.endswith("_blue"):
        return (0, 0, 255), (0, 0, 255)
    if name.endswith("_cyan"):
        return (0, 255, 255), (0, 255, 255)
    if name.endswith("_red"):
        return (255, 0, 0), (255, 0, 0)
    if name.endswith("_green"):
        return (0, 255, 0), (0, 255, 0)
    swap = int(beat) % 2 == 0
    return (
        (0, 255, 255) if swap else (255, 255, 255),
        (255, 255, 255) if swap else (0, 255, 255),
    )


def _edm_beat(beat: float, params: Mapping[str, Any]) -> float:
    duration = max(1.0, float(params.get("duration_beats", _EDM_DURATION_BEATS)))
    return beat % duration


def _groove_chase(name: str, beat: float, segments: int) -> Frame:
    color1, color2 = _edm_color_for_look(name, beat)
    return _dual_chase(
        beat=beat,
        segments=segments,
        loop_beats=4.0,
        offset_beats=2.0,
        color1=color1,
        color2=color2,
    )


def _groove_nebula(beat: float, segments: int) -> Frame:
    breath = 0.5 + 0.5 * math.sin(beat * math.pi / 2.0)
    bg = (int(15 * breath), 0, int(50 * breath))
    return _dual_chase(
        beat=beat,
        segments=segments,
        loop_beats=4.0,
        offset_beats=2.0,
        color1=(0, 255, 255),
        color2=(255, 255, 255),
        reverse_second=True,
        bg=bg,
    )


def _drop_chase(name: str, beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color1, color2 = _edm_color_for_look(name, beat)
    strobe_on = (int(beat * 16.0) % 2) == 0
    if not strobe_on:
        return _empty(segments)
    if beat < 8.0:
        progress = beat / 8.0
        density = max(0.02, min(1.0, (4.0 * (1.0 - progress) + 0.5) / max(1.0, segments)))
        return _sparkle_frame(
            segments=segments,
            density=density,
            color=color1,
            seed=seed,
            frame_index=frame_index,
            beat_bucket=int(beat * 16.0),
        )
    return _dual_chase(
        beat=beat - 8.0,
        segments=segments,
        loop_beats=2.0,
        offset_beats=1.0,
        color1=color1,
        color2=color2,
    )


def _drop_nebula(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    strobe_on = (int(beat * 16.0) % 2) == 0
    if not strobe_on:
        return _empty(segments)
    if beat < 8.0:
        progress = beat / 8.0
        density = max(0.02, min(1.0, (4.0 * (1.0 - progress) + 0.5) / max(1.0, segments)))
        return _sparkle_frame(
            segments=segments,
            density=density,
            color=lambda idx: (0, 255, 255) if idx % 2 == 0 else (255, 255, 255),
            seed=seed,
            frame_index=frame_index,
            beat_bucket=int(beat * 16.0),
        )
    breath = 0.5 + 0.5 * math.sin((beat - 8.0) * math.pi)
    bg = (int(15 * breath), 0, int(50 * breath))
    return _dual_chase(
        beat=beat - 8.0,
        segments=segments,
        loop_beats=2.0,
        offset_beats=1.0,
        color1=(0, 255, 255),
        color2=(255, 255, 255),
        reverse_second=True,
        bg=bg,
    )


def _buildup_nebula(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    if beat < 16.0:
        breath = 0.5 + 0.5 * math.sin(beat * math.pi / 2.0)
        bg = (int(10 * breath), 0, int(40 * breath))
    elif beat < 24.0:
        p = (beat - 16.0) / 8.0
        bg = (int(10 + 70 * p), 0, int(40 + 40 * p))
    else:
        local_rng = _rng(seed, frame_index, int(beat * 8.0))
        bg = (local_rng.randint(120, 220), 0, local_rng.randint(50, 150))

    phase = 0.15 * beat + 0.012 * (beat ** 2)
    frame = _dual_chase(
        beat=phase,
        segments=segments,
        loop_beats=1.0,
        offset_beats=0.5,
        color1=(0, 255, 255),
        color2=(255, 255, 255),
        reverse_second=True,
        bg=bg,
    )
    if beat >= 31.0:
        return _empty(segments, (255, 255, 255) if int(local_t * 40.0) % 2 == 0 else (0, 0, 0))
    if beat >= 16.0:
        p_strobe = (beat - 16.0) / 15.0
        strobe_freq = 5.0 + 13.0 * p_strobe
        if math.sin(2.0 * math.pi * strobe_freq * local_t) <= 0.0:
            frame = [_scale(c, 0.15) for c in frame]
    return frame


def _zone_indices(segments: int, zone_count: int, zone: int) -> range:
    start = int((zone / max(1, zone_count)) * segments)
    end = int(((zone + 1) / max(1, zone_count)) * segments)
    return range(start, max(start + 1, end))


def _buildup_zone_strobe(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    if beat >= 31.0:
        return _empty(segments, (255, 255, 255) if int(local_t * 40.0) % 2 == 0 else (0, 0, 0))
    if beat < 16.0:
        density = min(1.0, (0.1 + 3.9 * (beat / 16.0)) / max(1.0, segments / 4.0))
        strobe_freq = 4.0 + 8.0 * (beat / 16.0)
        if math.sin(2.0 * math.pi * strobe_freq * local_t) <= 0.0:
            return _empty(segments)
        return _sparkle_frame(
            segments=segments,
            density=density,
            color=(255, 255, 255),
            seed=seed,
            frame_index=frame_index,
            beat_bucket=int(beat * 8.0),
        )
    t = beat - 16.0
    chase_phase = 2.0 * t + 0.133 * (t ** 2)
    active_zone = int((chase_phase % 1.0) * 4.0)
    strobe_freq = 12.0 + 8.0 * (t / 15.0)
    if math.sin(2.0 * math.pi * strobe_freq * local_t) <= 0.0:
        return _empty(segments)
    frame = _empty(segments)
    for idx in _zone_indices(segments, 4, active_zone):
        if 0 <= idx < segments:
            frame[idx] = (255, 255, 255)
    return frame


def _buildup_half_strobe(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    if beat < 16.0:
        return _buildup_zone_strobe(beat, local_t, frame_index, params, segments, seed)
    if beat < 20.0:
        freq = 10.0 + 10.0 * ((beat - 16.0) / 4.0)
    else:
        freq = 20.0
    strobe_on = int(local_t * freq) % 2 == 0
    half = max(1, segments // 2)
    frame = _empty(segments)
    for idx in range(segments):
        first_half = idx < half
        if first_half == strobe_on:
            frame[idx] = (255, 255, 255)
    return frame


def _buildup_ramp_3(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    progress = min(1.0, beat / _EDM_DURATION_BEATS)
    strobe_freq = 4.0 + 12.0 * progress
    strobe_on = 1.0 if math.sin(2.0 * math.pi * strobe_freq * local_t) > 0.0 else 0.0
    gate = (1.0 - min(1.0, progress * 2.0)) + min(1.0, progress * 2.0) * strobe_on
    frame = _empty(segments)
    if segments > 0:
        pos = int((35.0 * local_t) % segments)
        frame[pos] = _scale((255, 255, 255), gate)
    return frame


def _buildup_ramp_2(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    progress = min(1.0, beat / _EDM_DURATION_BEATS)
    strobe_freq = 6.0 + 12.0 * progress
    if math.sin(2.0 * math.pi * strobe_freq * local_t) <= 0.0:
        return _empty(segments)
    particle_count = int(1.0 + 4.0 * progress)
    frame = _empty(segments)
    for idx in range(max(1, particle_count)):
        pos = int((65.0 * local_t + idx * (segments / max(1, particle_count))) % max(1, segments))
        if 0 <= pos < segments:
            frame[pos] = (255, 255, 255)
    return frame


def _buildup_ramp_1(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    progress = min(1.0, beat / _EDM_DURATION_BEATS)
    density = min(1.0, (0.05 + 3.95 * progress) / max(1.0, segments))
    return _sparkle_frame(
        segments=segments,
        density=density,
        color=(255, 255, 255),
        seed=seed,
        frame_index=frame_index,
        beat_bucket=int(beat * 8.0),
    )


def _edm_dispatch(name: str, beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    cue_beat = _edm_beat(beat, params)
    if name.startswith("groove_chase_"):
        return _groove_chase(name, cue_beat, segments)
    if name == "groove_freestyle_nebula":
        return _groove_nebula(cue_beat, segments)
    if name.startswith("drop_chase_") and name != "drop_chase_freestyle_nebula":
        return _drop_chase(name, cue_beat, local_t, frame_index, params, segments, seed)
    if name == "drop_chase_freestyle_nebula":
        return _drop_nebula(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "buildup_freestyle_nebula":
        return _buildup_nebula(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "buildup_white_zone_strobe":
        return _buildup_zone_strobe(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "buildup_white_half_strobe":
        return _buildup_half_strobe(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "buildup_ramp_3":
        return _buildup_ramp_3(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "buildup_ramp_2":
        return _buildup_ramp_2(cue_beat, local_t, frame_index, params, segments, seed)
    return _buildup_ramp_1(cue_beat, local_t, frame_index, params, segments, seed)


_GENERIC_EFFECTS: dict[str, EffectFn] = {
    "solid": _solid,
    "blackout": _blackout,
    "beat_chase": _beat_chase,
    "beat_strobe": _beat_strobe,
    "drop_burst": _drop_burst,
    "breathe": _breathe,
    "gradient_sweep": _gradient_sweep,
    "sparkle": _sparkle,
    "color_pulse": _color_pulse,
    "bar_wipe": _bar_wipe,
}

EDM_BUILDS: dict[str, str] = {
    "buildup_ramp_1": "32-beat continuous linear white sparkle ramp with very fast decay.",
    "buildup_ramp_2": "32-beat fast white chase particles strobing and scaling in count.",
    "buildup_ramp_3": "32-beat smooth white chase wave morphing into an accelerating strobe.",
    "buildup_white_zone_strobe": "32-beat buildup: expanding stroboscopic sparkles into 4 zones that strobe chase.",
    "buildup_white_half_strobe": "32-beat buildup: expanding stroboscopic sparkles into 2 alternating stroboscopic halves.",
    "buildup_freestyle_nebula": "32-beat freestyle: opposite comets + breathing purple/magenta bg + shutter strobe + climax flash.",
    "groove_chase_blue": "32-beat smooth blue dual-head chase.",
    "groove_chase_cyan": "32-beat smooth cyan dual-head chase.",
    "groove_chase_red": "32-beat smooth red dual-head chase.",
    "groove_chase_green": "32-beat smooth green dual-head chase.",
    "groove_chase_cyan_white": "32-beat smooth alternating cyan/white dual-head chase.",
    "groove_freestyle_nebula": "32-beat smooth freestyle groove: opposite comets + breathing purple/magenta bg.",
    "drop_chase_blue": "32-beat drop: 8-beat sparkle strobe burst + 2-beat blue chase strobe.",
    "drop_chase_cyan": "32-beat drop: 8-beat sparkle strobe burst + 2-beat cyan chase strobe.",
    "drop_chase_red": "32-beat drop: 8-beat sparkle strobe burst + 2-beat red chase strobe.",
    "drop_chase_green": "32-beat drop: 8-beat sparkle strobe burst + 2-beat green chase strobe.",
    "drop_chase_cyan_white": "32-beat drop: 8-beat sparkle strobe burst + 2-beat cyan/white chase strobe.",
    "drop_chase_freestyle_nebula": "32-beat freestyle drop: 8-beat sparkle strobe burst + 2-beat opposite comets strobe.",
}

_EFFECTS: dict[str, EffectFn] = dict(_GENERIC_EFFECTS)


def _make_edm_effect(effect_name: str) -> EffectFn:
    def _effect(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
        return _edm_dispatch(effect_name, beat, local_t, frame_index, params, segments, seed)

    return _effect


for _name in EDM_BUILDS:
    _EFFECTS[_name] = _make_edm_effect(_name)


REALTIME_EFFECT_NAMES = frozenset(_EFFECTS.keys())
REALTIME_STROBE_EFFECTS = frozenset(
    {
        "beat_strobe",
        "buildup_ramp_2",
        "buildup_ramp_3",
        "buildup_white_zone_strobe",
        "buildup_white_half_strobe",
        "buildup_freestyle_nebula",
        "drop_chase_blue",
        "drop_chase_cyan",
        "drop_chase_red",
        "drop_chase_green",
        "drop_chase_cyan_white",
        "drop_chase_freestyle_nebula",
    }
)
REALTIME_EFFECT_PARAM_KEYS: dict[str, frozenset[str]] = {
    "solid": frozenset({"color"}),
    "blackout": frozenset(),
    "beat_chase": frozenset({"color", "bg", "trail", "span_beats"}),
    "beat_strobe": frozenset({"color", "subdivision", "duty"}),
    "drop_burst": frozenset({"color", "bg", "decay"}),
    "breathe": frozenset({"color", "period_beats", "floor"}),
    "gradient_sweep": frozenset({"color_a", "color_b", "speed"}),
    "sparkle": frozenset({"color", "bg", "density"}),
    "color_pulse": frozenset({"color", "bg"}),
    "bar_wipe": frozenset({"color", "bg"}),
}
for _name in EDM_BUILDS:
    REALTIME_EFFECT_PARAM_KEYS[_name] = frozenset({"duration_beats"})


class GoveeFrameRenderer:
    """Stateless renderer. Unknown effect names fail dark."""

    def render(
        self,
        name: str,
        *,
        beat_pos: float,
        local_t: float,
        frame_index: int,
        params: Mapping[str, Any] | None,
        segments: int,
        seed: int,
    ) -> Frame:
        effect = _EFFECTS.get(str(name))
        if effect is None:
            return _empty(segments)
        safe_params: Mapping[str, Any] = params if isinstance(params, Mapping) else {}
        frame = effect(
            float(beat_pos),
            max(0.0, float(local_t)),
            int(frame_index),
            safe_params,
            max(0, int(segments)),
            int(seed),
        )
        return [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in frame[: max(0, int(segments))]]
