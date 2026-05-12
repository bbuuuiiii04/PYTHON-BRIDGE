"""Pure waveform-energy utilities for offline ANLZ analysis.

This module is intentionally side-effect free:
- No filesystem or database access.
- No Rekordbox / SoundSwitch integration.
- Deterministic, unit-testable computations only.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Literal

IntensityClass = Literal["subtle", "medium", "major", "peak", "low_confidence"]

DROP_LIFT_SUBTLE = 0.05
DROP_LIFT_MEDIUM = 0.15
DROP_LIFT_MAJOR = 0.30
DROP_LIFT_PEAK = 0.45

BREAKDOWN_DEPTH_MEDIUM = 0.30
BREAKDOWN_DEPTH_TRUE_LOW = 0.55

BUILDUP_SLOPE_MILD = 0.15
BUILDUP_SLOPE_STRONG = 0.40

LOW_CONFIDENCE_WINDOW_BEATS = 4
LOW_CONFIDENCE_CUTOFF = 0.35


@dataclass(frozen=True)
class EnergySeries:
    values: tuple[float, ...]
    source: str = ""


@dataclass(frozen=True)
class EnergyWindow:
    beat: int
    pre: tuple[float, ...]
    post: tuple[float, ...]
    pre_mean: float
    post_mean: float
    lift: float
    peak: float
    valley: float


@dataclass(frozen=True)
class SmartTransitionIntensity:
    class_name: IntensityClass
    lift: float
    pre_mean: float
    post_mean: float
    confidence: float
    reason: str
    recommended_action: str


def normalize_energy_series(values: list[float] | tuple[float, ...], *, source: str = "") -> EnergySeries:
    if not values:
        return EnergySeries(values=(), source=source)
    safe = [max(0.0, float(value)) for value in values]
    vmax = max(safe)
    if vmax <= 0.0:
        return EnergySeries(values=(), source=source)
    return EnergySeries(values=tuple(value / vmax for value in safe), source=source)


def map_index_to_elapsed_ms(index: int, count: int, total_ms: float) -> float:
    if count <= 1 or total_ms <= 0.0:
        return 0.0
    clamped = max(0, min(int(index), count - 1))
    return (clamped / float(count - 1)) * float(total_ms)


def elapsed_ms_to_nearest_beat(elapsed_ms: float, beatgrid_times_ms: list[float]) -> int | None:
    if not beatgrid_times_ms:
        return None
    if len(beatgrid_times_ms) == 1:
        return 0

    idx = bisect.bisect_left(beatgrid_times_ms, elapsed_ms)
    if idx <= 0:
        return 0
    if idx >= len(beatgrid_times_ms):
        return len(beatgrid_times_ms) - 1

    before = beatgrid_times_ms[idx - 1]
    after = beatgrid_times_ms[idx]
    if abs(elapsed_ms - before) <= abs(after - elapsed_ms):
        return idx - 1
    return idx


def energy_window_for_beat(
    beat: int,
    beatgrid_times_ms: list[float],
    energy_values: list[float] | tuple[float, ...],
    total_ms: float,
    pre_beats: int,
    post_beats: int,
) -> EnergyWindow | None:
    if not beatgrid_times_ms or len(beatgrid_times_ms) < 2:
        return None
    normalized = normalize_energy_series(energy_values).values
    if not normalized:
        return None

    if pre_beats <= 0 or post_beats <= 0:
        return None

    duration_ms = float(total_ms) if total_ms > 0.0 else _infer_total_ms_from_grid(beatgrid_times_ms)
    if duration_ms <= 0.0:
        return None

    center_ms = _elapsed_ms_for_beat(beat, beatgrid_times_ms)
    pre_start_ms = _elapsed_ms_for_beat(beat - pre_beats, beatgrid_times_ms)
    post_end_ms = _elapsed_ms_for_beat(beat + post_beats, beatgrid_times_ms)

    pre = _slice_energy_between_ms(normalized, duration_ms, pre_start_ms, center_ms)
    post = _slice_energy_between_ms(normalized, duration_ms, center_ms, post_end_ms)
    if not pre or not post:
        return None

    pre_mean = _mean(pre)
    post_mean = _mean(post)
    all_values = pre + post

    return EnergyWindow(
        beat=int(beat),
        pre=tuple(pre),
        post=tuple(post),
        pre_mean=pre_mean,
        post_mean=post_mean,
        lift=post_mean - pre_mean,
        peak=max(all_values),
        valley=min(all_values),
    )


def classify_drop_intensity(window: EnergyWindow) -> SmartTransitionIntensity:
    confidence = _window_confidence(window)
    if not _has_min_window_samples(window):
        return _intensity(
            "low_confidence",
            window,
            min(confidence, LOW_CONFIDENCE_CUTOFF),
            "insufficient_window_samples",
            "no_change",
        )
    if confidence < LOW_CONFIDENCE_CUTOFF:
        return _intensity("low_confidence", window, confidence, "insufficient_confidence", "no_change")

    lift = window.lift
    if lift >= DROP_LIFT_PEAK:
        return _intensity("peak", window, confidence, "strong_post_drop_lift", "blackout_mask_ok_high_laser")
    if lift >= DROP_LIFT_MAJOR:
        return _intensity("major", window, confidence, "major_post_drop_lift", "normal_smart_drop_high_laser")
    if lift >= DROP_LIFT_MEDIUM:
        return _intensity("medium", window, confidence, "medium_post_drop_lift", "normal_smart_drop")
    if lift >= DROP_LIFT_SUBTLE:
        return _intensity("subtle", window, confidence, "subtle_post_drop_lift", "avoid_blackout")
    return _intensity("low_confidence", window, confidence, "no_clear_drop_lift", "no_change")


def classify_breakdown_intensity(window: EnergyWindow) -> SmartTransitionIntensity:
    confidence = _window_confidence(window)
    if not _has_min_window_samples(window):
        return _intensity(
            "low_confidence",
            window,
            min(confidence, LOW_CONFIDENCE_CUTOFF),
            "insufficient_window_samples",
            "no_change",
        )
    if confidence < LOW_CONFIDENCE_CUTOFF:
        return _intensity("low_confidence", window, confidence, "insufficient_confidence", "no_change")

    depth = window.pre_mean - window.post_mean
    if depth >= BREAKDOWN_DEPTH_TRUE_LOW and window.post_mean <= 0.25:
        return _intensity("peak", window, confidence, "true_low_breakdown", "minimal_look_blackout_optional")
    if depth >= BREAKDOWN_DEPTH_MEDIUM:
        return _intensity("major", window, confidence, "clear_breakdown", "clear_or_minimal_look")
    if depth >= DROP_LIFT_SUBTLE:
        return _intensity("subtle", window, confidence, "mild_breakdown", "reduce_intensity")
    return _intensity("low_confidence", window, confidence, "no_clear_breakdown", "no_change")


def classify_buildup_intensity(window: EnergyWindow) -> SmartTransitionIntensity:
    confidence = _window_confidence(window)
    if not _has_min_window_samples(window):
        return _intensity(
            "low_confidence",
            window,
            min(confidence, LOW_CONFIDENCE_CUTOFF),
            "insufficient_window_samples",
            "no_change",
        )
    if confidence < LOW_CONFIDENCE_CUTOFF:
        return _intensity("low_confidence", window, confidence, "insufficient_confidence", "no_change")

    slope = window.post_mean - window.pre_mean
    if slope >= BUILDUP_SLOPE_STRONG:
        return _intensity("major", window, confidence, "strong_rising_buildup", "escalate_fx_before_drop")
    if slope >= BUILDUP_SLOPE_MILD:
        return _intensity("medium", window, confidence, "mild_rising_buildup", "normal_buildup_behavior")
    if slope >= DROP_LIFT_SUBTLE:
        return _intensity("subtle", window, confidence, "slight_rise", "small_escalation")
    return _intensity("low_confidence", window, confidence, "flat_or_falling_buildup", "no_change")


def _infer_total_ms_from_grid(beatgrid_times_ms: list[float]) -> float:
    if len(beatgrid_times_ms) < 2:
        return 0.0
    last = float(beatgrid_times_ms[-1])
    interval = float(beatgrid_times_ms[-1] - beatgrid_times_ms[-2])
    if interval <= 0.0:
        return 0.0
    return last + interval


def _elapsed_ms_for_beat(beat: int, beatgrid_times_ms: list[float]) -> float:
    if beat <= 0:
        first = float(beatgrid_times_ms[0])
        interval = float(beatgrid_times_ms[1] - beatgrid_times_ms[0])
        if interval <= 0.0:
            return first
        return first + (beat * interval)

    if beat < len(beatgrid_times_ms):
        return float(beatgrid_times_ms[beat])

    last = float(beatgrid_times_ms[-1])
    interval = float(beatgrid_times_ms[-1] - beatgrid_times_ms[-2])
    if interval <= 0.0:
        return last
    extra = beat - (len(beatgrid_times_ms) - 1)
    return last + (extra * interval)


def _slice_energy_between_ms(
    values: tuple[float, ...],
    total_ms: float,
    start_ms: float,
    end_ms: float,
) -> list[float]:
    if end_ms <= start_ms or total_ms <= 0.0:
        return []
    count = len(values)
    start_idx = _elapsed_ms_to_index(start_ms, count, total_ms)
    end_idx = _elapsed_ms_to_index(end_ms, count, total_ms)
    if end_idx <= start_idx:
        end_idx = min(count, start_idx + 1)
    return list(values[start_idx:end_idx])


def _elapsed_ms_to_index(elapsed_ms: float, count: int, total_ms: float) -> int:
    if count <= 1 or total_ms <= 0.0:
        return 0
    clamped = max(0.0, min(float(elapsed_ms), total_ms))
    pos = clamped / total_ms
    return int(round(pos * (count - 1)))


def _window_confidence(window: EnergyWindow) -> float:
    min_samples = min(len(window.pre), len(window.post))
    coverage = min(1.0, min_samples / float(LOW_CONFIDENCE_WINDOW_BEATS))
    dynamic = min(1.0, abs(window.lift) / max(0.001, DROP_LIFT_MEDIUM))
    return round((coverage * 0.7) + (dynamic * 0.3), 4)


def _has_min_window_samples(window: EnergyWindow) -> bool:
    return len(window.pre) >= LOW_CONFIDENCE_WINDOW_BEATS and len(window.post) >= LOW_CONFIDENCE_WINDOW_BEATS


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _intensity(
    class_name: IntensityClass,
    window: EnergyWindow,
    confidence: float,
    reason: str,
    action: str,
) -> SmartTransitionIntensity:
    return SmartTransitionIntensity(
        class_name=class_name,
        lift=window.lift,
        pre_mean=window.pre_mean,
        post_mean=window.post_mean,
        confidence=confidence,
        reason=reason,
        recommended_action=action,
    )
