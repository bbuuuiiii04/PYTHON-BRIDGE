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


COMET_MIN_HEAD_SOFT = 1.0   # one/two segment anti-aliased head
COMET_MIN_TRAIL_LEDS = 0.0  # default comet is a tight dot, not a long tail
COMET_TAIL_SCALE = 0.35
COMET_INTENSITY_FLOOR = 0.04


def _comet_frame(progress: float, segments: int, color: RGB, head_soft: float,
                 trail_len: float, direction: int) -> Frame:
    """A compact comet head with an optional trailing fade.

    The default is intentionally tiny: a one/two segment normalized head.  A
    longer tail appears only when callers explicitly pass a positive
    ``trail_beats`` value.
    """
    if segments <= 0:
        return []
    pos = progress * segments if direction >= 0 else (1.0 - progress) * segments
    head_soft = max(0.5, float(head_soft))
    trail_len = max(0.0, float(trail_len))
    acc = [[0.0, 0.0, 0.0] for _ in range(segments)]
    head_weights: list[tuple[int, float]] = []
    for idx in range(segments):
        intensity = max(0.0, 1.0 - abs(float(idx) - pos) / head_soft)
        if intensity > 0.0:
            head_weights.append((idx, intensity))
    total_head = sum(weight for _, weight in head_weights)
    if total_head > 0.0:
        for idx, weight in head_weights:
            amount = weight / total_head
            acc[idx][0] += color[0] * amount
            acc[idx][1] += color[1] * amount
            acc[idx][2] += color[2] * amount

    if trail_len > 0.0:
        for idx in range(segments):
            # d > 0 => this LED is behind the head, opposite the travel direction.
            d = (pos - idx) if direction >= 0 else (idx - pos)
            if d <= head_soft:
                continue
            intensity = COMET_TAIL_SCALE * math.exp(-(d - head_soft) / trail_len)
            if intensity < COMET_INTENSITY_FLOOR:
                continue
            acc[idx][0] += color[0] * intensity
            acc[idx][1] += color[1] * intensity
            acc[idx][2] += color[2] * intensity
    return [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in acc]


def _ring_head_frame(pos: float, segments: int, color: RGB) -> Frame:
    """Single head that interpolates around the ring instead of snapping to an index."""
    if segments <= 0:
        return []
    pos = float(pos) % float(segments)
    lower = int(math.floor(pos)) % segments
    upper = (lower + 1) % segments
    frac = pos - math.floor(pos)
    frame = _empty(segments)
    frame[lower] = _scale(color, 1.0 - frac)
    if frac > 0.0:
        frame[upper] = _scale(color, frac)
    return frame


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


def _drop_center_burst_blue_cyan(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    frame = [(0, 0, 0)] * segments
    center = segments / 2.0
    
    # Phase 1: Burst every half beat from the physical center to both ends
    pulse_phase = (beat % 0.5) / 0.5
    pulse_width = 1.0  # Smallest possible sharp burst
    current_dist = pulse_phase * (center + pulse_width)
    
    # 3 out of 4 bursts are pure deep blue, 1 out of 4 is cyan
    burst_idx = int((beat % 8.0) * 2.0)
    is_blue_burst = (burst_idx % 4) != 3
    g_base = 0 if is_blue_burst else 200
    
    for idx in range(segments):
        if idx % 2 != 0:
            continue
        dist_from_center = abs(idx - center)
        dist_from_pulse = abs(dist_from_center - current_dist)
        intensity = max(0.0, 1.0 - (dist_from_pulse / pulse_width))
        if intensity > 0:
            frame[idx] = (0, int(g_base * intensity), int(255 * intensity))
    return frame

def _post_drop_center_comet_blue_cyan(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    frame = [(0, 0, 0)] * segments
    center = segments / 2.0
    
    # Phase 2: Dual comets spawning in the middle and chasing outward on the beat + strobing
    strobe_on = (int(beat * 16.0) % 2) == 0
    if not strobe_on:
        return frame
        
    comet_width = 1.0  # Extremely small comet tail
    
    for age in [beat % 1.0, (beat % 1.0) + 1.0]:
        if age > 2.0:
            continue
            
        comet_head_dist = age * center
        
        # 3 out of 4 comets are pure deep blue, 1 out of 4 is cyan
        spawn_beat = beat - age
        spawn_idx = int(round(spawn_beat))
        is_blue_comet = (spawn_idx % 4) != 3
        g_base = 0 if is_blue_comet else 200
        
        for idx in range(segments):
            dist_from_center = abs(idx - center)
            
            if comet_head_dist - comet_width <= dist_from_center <= comet_head_dist:
                intensity = 1.0 - ((comet_head_dist - dist_from_center) / comet_width)
                r = 0
                g = int(g_base * intensity)
                b = int(255 * intensity)
                
                old_r, old_g, old_b = frame[idx]
                frame[idx] = (min(255, old_r + r), min(255, old_g + g), min(255, old_b + b))
                
    return frame


def _drop_chase(name: str, beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    color1, color2 = _edm_color_for_look(name, beat)
    # M1b WI-4: prefer an engine-injected color; fall back to the suffix color.
    color1 = _color(params.get("color"), color1)
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
    return _drop_chase_comets(name, beat, segments, color1, color2)


def _post_drop_chase(name: str, beat: float, params: Mapping[str, Any], segments: int) -> Frame:
    color1, color2 = _edm_color_for_look(name, beat)
    # M1b WI-4: prefer an engine-injected color; fall back to the suffix color.
    color1 = _color(params.get("color"), color1)
    strobe_on = (int(beat * 16.0) % 2) == 0
    if not strobe_on:
        return _empty(segments)
    # Standalone post-drop chase: comets begin at beat 0 (no sparkle intro) and
    # keep spawning across the full cue. Unlike the drop chase, it does not
    # borrow the drop's 8-beat-offset timeline, so it has no dark tail near the
    # end of the cycle.
    return _drop_chase_comets(name, beat, segments, color1, color2, start=0.0)


def _post_drop_nebula(beat: float, segments: int) -> Frame:
    strobe_on = (int(beat * 16.0) % 2) == 0
    if not strobe_on:
        return _empty(segments)
    return _drop_chase_comets(
        "drop_chase_freestyle_nebula",
        beat,
        segments,
        (0, 255, 255),
        (255, 255, 255),
        start=0.0,
    )


def _drop_white_aggressive(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    # Full-strip pure-white 16th-note strobe with a sharp ~25% duty cycle (1 frame ON).
    # To prevent dropped frames at 40fps, we use a 16th-note cycle (0.25 beats) 
    # and keep the ON time very short (0.0625 beats, which is ~1 frame).
    # This guarantees a reliable, punchy, dark strobe effect.
    # Cue length is owned by the bridge's drop window.
    strobe_on = (beat % 0.25) < 0.0625
    return _empty(segments, (255, 255, 255) if strobe_on else (0, 0, 0))


def _post_drop_white_shatter(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    # Per-frame full-white stroboscopic static. Each pixel is independently
    # re-randomized every render frame (keyed on frame_index) for a true
    # 1-frame lifespan. The spawn rate dissolves 13 -> 3 over the look's first
    # 4 beats, then holds at the ~3 floor for the rest of the post-drop window.
    # `beat` is the post_drop look's own local beat (starts ~0 at trigger), so
    # there is no -16 offset like the single-timeline sandbox prototype.
    progress = min(1.0, max(0.0, beat / 4.0))
    spawn_rate = 10.0 * (1.0 - progress) + 3.0
    density = min(1.0, spawn_rate / float(max(1, segments)))
    frame: Frame = []
    for idx in range(max(0, segments)):
        lit = _rng(seed, frame_index, idx).random() < density
        frame.append((255, 255, 255) if lit else (0, 0, 0))
    return frame


def _drop_chase_spawn_times(beat: float, *, start: float = 8.0) -> list[tuple[float, int]]:
    interval = 1.0
    travel_beats = 2.0
    if beat < start:
        return []
    last_spawn = min(float(beat), _EDM_DURATION_BEATS - interval)
    out: list[tuple[float, int]] = []
    spawn_idx = 0
    spawn_at = start
    while spawn_at <= last_spawn + 1e-9:
        age = float(beat) - spawn_at
        if 0.0 <= age <= travel_beats:
            out.append((spawn_at, spawn_idx))
        spawn_idx += 1
        spawn_at = start + spawn_idx * interval
    return out


def _drop_chase_comets(
    name: str,
    beat: float,
    segments: int,
    color1: RGB,
    color2: RGB,
    *,
    start: float = 8.0,
) -> Frame:
    renderer = GoveeFrameRenderer()
    frames = []
    for spawn_at, spawn_idx in _drop_chase_spawn_times(beat, start=start):
        color = color1 if spawn_idx % 2 == 0 else color2
        frames.append(
            renderer.render_comet(
                name,
                progress=(float(beat) - spawn_at) / 2.0,
                segments=segments,
                width=0.8,
                direction=1,
                params={
                    "color": color,
                    "travel_beats": 2.0,
                    "trail_beats": 0.0,
                },
            )
        )
    if not frames:
        return _empty(segments)
    return GoveeFrameRenderer.fold_additive(frames, segments)


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
    return _drop_chase_comets(
        "drop_chase_freestyle_nebula",
        beat,
        segments,
        (0, 255, 255),
        (255, 255, 255),
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


def _buildup_ramp_3_spawn_times(beat: float) -> list[tuple[float, float]]:
    phases = (
        (0.0, 16.0, 1.0, 2.0),
        (16.0, 24.0, 0.5, 1.0),
        (24.0, _EDM_DURATION_BEATS, 0.25, 1.0),
    )
    out: list[tuple[float, float]] = []
    for start, end, interval, travel_beats in phases:
        if beat < start:
            continue
        last_spawn = min(float(beat), end - interval)
        spawn_idx = 0
        spawn_at = start
        while spawn_at <= last_spawn + 1e-9:
            age = float(beat) - spawn_at
            if 0.0 <= age <= travel_beats:
                out.append((spawn_at, travel_beats))
            spawn_idx += 1
            spawn_at = start + spawn_idx * interval
    return out


def _buildup_ramp_3(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    if beat >= 24.0 and beat % 0.25 >= 0.125:
        return _empty(segments)

    renderer = GoveeFrameRenderer()
    frames = []
    for spawn_at, travel_beats in _buildup_ramp_3_spawn_times(beat):
        frames.append(
            renderer.render_comet(
                "buildup_ramp_3",
                progress=(float(beat) - spawn_at) / travel_beats,
                segments=segments,
                width=0.8,
                direction=1,
                params={
                    "color": (255, 255, 255),
                    "travel_beats": travel_beats,
                    "trail_beats": 0.0,
                },
            )
        )
    if not frames:
        return _empty(segments)
    return GoveeFrameRenderer.fold_additive(frames, segments)


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


def _twinkle_blue(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    macro_phase = beat / 32.0
    macro_swell = 0.25 + 0.75 * math.sin(macro_phase * math.pi)

    beat_phase = beat % 1.0
    # Beat pulse: smooth exponential decay on each beat
    beat_pulse = 0.15 + 0.85 * math.exp(-3.5 * beat_phase)

    frame = [(0, 0, 0)] * segments
    for idx in range(segments):
        # Create a stable timeline for this segment
        star_rng = _rng(seed, "star_timeline", idx)
        
        # Period: how often this segment twinkles (e.g. between 18 and 36 beats)
        period = 18.0 + star_rng.random() * 18.0
        # Phase offset: when it starts twinkling
        phi = star_rng.random() * period
        
        # Local time in this segment's lifecycle
        t_cycle = (beat + phi) % period
        
        # Active twinkle window (2.0 beats long)
        if t_cycle >= 2.0:
            continue
            
        # Envelope: fade-in for 0.5 beats, fade-out for 1.5 beats
        if t_cycle < 0.5:
            envelope = t_cycle / 0.5
        else:
            envelope = (2.0 - t_cycle) / 1.5

        # Get color
        choice = star_rng.randint(0, 3)
        if choice == 0:
            c = (0, 0, 255)       # deep blue
        elif choice == 1:
            c = (0, 128, 255)     # medium blue
        elif choice == 2:
            c = (30, 144, 255)    # dodger blue
        else:
            c = (0, 255, 255)     # vibrant cyan

        # Gentle individual twinkle (sine wave, ~2.4Hz) - no strobing
        twinkle = 0.6 + 0.4 * math.sin(local_t * 15.0 + idx * 3.7)

        # Scale intensity: keep it smaller and more delicate (0.70 max scale)
        intensity = envelope * beat_pulse * twinkle * macro_swell * 0.70
        frame[idx] = _scale(c, intensity)

    return frame


def _edm_dispatch(name: str, beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> Frame:
    cue_beat = _edm_beat(beat, params)
    if name.startswith("groove_chase_"):
        return _groove_chase(name, cue_beat, segments)
    if name == "groove_freestyle_nebula":
        return _groove_nebula(cue_beat, segments)
    if name.startswith("drop_chase_") and name != "drop_chase_freestyle_nebula":
        return _drop_chase(name, cue_beat, local_t, frame_index, params, segments, seed)
    if name == "drop_center_burst_blue_cyan":
        return _drop_center_burst_blue_cyan(cue_beat, local_t, frame_index, params, segments, seed)
    if name.startswith("post_drop_chase_"):
        return _post_drop_chase(name, cue_beat, params, segments)
    if name == "post_drop_center_comet_blue_cyan":
        return _post_drop_center_comet_blue_cyan(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "post_drop_freestyle_nebula":
        return _post_drop_nebula(cue_beat, segments)
    if name == "drop_white_aggressive":
        return _drop_white_aggressive(cue_beat, local_t, frame_index, params, segments, seed)
    if name == "post_drop_white_shatter":
        return _post_drop_white_shatter(cue_beat, local_t, frame_index, params, segments, seed)
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
    if name == "twinkle_blue":
        return _twinkle_blue(cue_beat, local_t, frame_index, params, segments, seed)
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
    "drop_center_burst_blue_cyan": "32-beat drop: half-beat bursts from center to edges.",
    "post_drop_center_comet_blue_cyan": "32-beat post-drop: strobing dual comets chasing outward from center.",
    "drop_chase_red": "32-beat drop: 8-beat sparkle strobe burst + 2-beat red chase strobe.",
    "drop_chase_green": "32-beat drop: 8-beat sparkle strobe burst + 2-beat green chase strobe.",
    "drop_chase_cyan_white": "32-beat drop: 8-beat sparkle strobe burst + 2-beat cyan/white chase strobe.",
    "drop_chase_freestyle_nebula": "32-beat freestyle drop: 8-beat sparkle strobe burst + 2-beat opposite comets strobe.",
    "post_drop_chase_blue": "32-beat post-drop: immediate 2-beat blue comet chase strobe.",
    "post_drop_chase_cyan": "32-beat post-drop: immediate 2-beat cyan comet chase strobe.",
    "post_drop_chase_red": "32-beat post-drop: immediate 2-beat red comet chase strobe.",
    "post_drop_chase_green": "32-beat post-drop: immediate 2-beat green comet chase strobe.",
    "post_drop_chase_cyan_white": "32-beat post-drop: immediate alternating cyan/white comet chase strobe.",
    "post_drop_freestyle_nebula": "32-beat post-drop: immediate cyan/white freestyle comet chase strobe.",
    "drop_white_aggressive": "Drop: full-strip pure-white 32nd-note strobe (bridge-owned duration).",
    "post_drop_white_shatter": "Post-drop: per-frame full-white stroboscopic static dissolving 13->3 over 4 beats then held low.",
    "twinkle_blue": "32-beat super twinkly blue cyan look that pulses on beat.",
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
        "post_drop_chase_blue",
        "post_drop_chase_cyan",
        "post_drop_chase_red",
        "post_drop_chase_green",
        "post_drop_chase_cyan_white",
        "post_drop_freestyle_nebula",
        "drop_white_aggressive",
        "post_drop_white_shatter",
        "twinkle_blue",
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

_SYNC_PARAM_KEYS = frozenset({
    "sync_mode", "beat_division", "travel_beats", "width",
    "trail_beats", "heads", "max_pulses", "spawn_on_wrap", "reverse",
})
for _k in list(REALTIME_EFFECT_PARAM_KEYS):
    REALTIME_EFFECT_PARAM_KEYS[_k] = REALTIME_EFFECT_PARAM_KEYS[_k] | _SYNC_PARAM_KEYS
# Allow explicit color override on the comet (overlap) chases.
for _k in ("groove_chase_blue", "groove_chase_cyan", "groove_chase_red",
           "groove_chase_green", "groove_chase_cyan_white"):
    REALTIME_EFFECT_PARAM_KEYS[_k] = REALTIME_EFFECT_PARAM_KEYS[_k] | frozenset({"color"})

_OVERLAP_EFFECTS = frozenset({
    "groove_chase_blue", "groove_chase_cyan", "groove_chase_red",
    "groove_chase_green", "groove_chase_cyan_white",
})
_RETRIGGER_EFFECTS = frozenset({
    "beat_chase", "beat_strobe", "drop_burst", "color_pulse", "bar_wipe", "sparkle",
})

def is_comet_effect(name: str) -> bool:
    """True for effects whose realtime render is the traveling comet primitive."""
    return str(name) in _OVERLAP_EFFECTS

def default_sync_mode(name: str) -> str:
    name = str(name)
    if name in _OVERLAP_EFFECTS:
        return "overlap"
    if name in _RETRIGGER_EFFECTS:
        return "retrigger"
    return "continuous"

def default_beat_division(name: str) -> float:
    return 1.0


class GoveeFrameRenderer:
    """Stateless renderer. Unknown effect names fail dark."""

    def blank(self, segments: int) -> Frame:
        return _empty(max(0, int(segments)))

    def render_comet(self, name: str, *, progress: float, segments: int,
                     width: float, direction: int, params: Mapping[str, Any] | None) -> Frame:
        seg = max(0, int(segments))
        safe = params if isinstance(params, Mapping) else {}
        color = _color(safe.get("color"), _edm_color_for_look(str(name), 0.0)[0])
        travel = max(1e-3, float(safe.get("travel_beats", 1.0)))
        trail_beats = max(0.0, float(safe.get("trail_beats", 0.0)))
        head_soft = max(COMET_MIN_HEAD_SOFT, float(width))
        trail_len = max(COMET_MIN_TRAIL_LEDS, (trail_beats / travel) * seg)
        frame = _comet_frame(float(progress), seg, color, head_soft, trail_len, int(direction))
        clamped = [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in frame[:seg]]
        if len(clamped) < seg:
            clamped.extend([(0, 0, 0)] * (seg - len(clamped)))
        return clamped

    @staticmethod
    def fold_additive(frames: list[Frame], segments: int) -> Frame:
        seg = max(0, int(segments))
        acc = [[0, 0, 0] for _ in range(seg)]
        for f in frames:
            for i in range(min(seg, len(f))):
                acc[i][0] += f[i][0]; acc[i][1] += f[i][1]; acc[i][2] += f[i][2]
        return [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in acc]

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
        seg_count = max(0, int(segments))
        frame = effect(
            float(beat_pos),
            max(0.0, float(local_t)),
            int(frame_index),
            safe_params,
            seg_count,
            int(seed),
        )
        clamped = [
            (_clamp_channel(r), _clamp_channel(g), _clamp_channel(b))
            for r, g, b in frame[:seg_count]
        ]
        # Defensive: an effect that returns fewer pixels than requested would be
        # rejected by the transport's segment-count check. Pad dark so the frame
        # is always exactly `segments` long.
        if len(clamped) < seg_count:
            clamped.extend([(0, 0, 0)] * (seg_count - len(clamped)))
        return clamped
