import math
import bisect
from typing import Optional


def _compute_beat_pos(elapsed_ms: float, bpm: float, first_beat_ms: float = 0.0) -> float:
    """Fractional beat position within current bar.

    Returns 0.0 if bpm == 0. Negative means before first beat.
    """
    if bpm <= 0:
        return 0.0
    beat_ms = 60_000.0 / bpm
    offset = elapsed_ms - first_beat_ms
    pos = math.fmod(offset / beat_ms, 4.0)
    return pos if pos >= 0 else pos + 4.0


def _compute_beatgrid_position(
    elapsed_ms: float,
    beatgrid_times_ms: list[float],
) -> Optional[tuple[float, float]]:
    """Return (wrapped_0_to_4, absolute) beat position from ordered grid markers."""
    if len(beatgrid_times_ms) < 2:
        return None

    times = beatgrid_times_ms
    idx = bisect.bisect_right(times, elapsed_ms) - 1
    if idx < 0:
        interval = times[1] - times[0]
        if interval <= 0:
            return None
        abs_pos = (elapsed_ms - times[0]) / interval
    elif idx >= len(times) - 1:
        interval = times[-1] - times[-2]
        if interval <= 0:
            return None
        abs_pos = (len(times) - 1) + ((elapsed_ms - times[-1]) / interval)
    else:
        interval = times[idx + 1] - times[idx]
        if interval <= 0:
            return None
        abs_pos = idx + ((elapsed_ms - times[idx]) / interval)

    wrapped = math.fmod(abs_pos, 4.0)
    if wrapped < 0:
        wrapped += 4.0
    return wrapped, abs_pos


def _beatgrid_elapsed_for_abs_beat(
    abs_beat: int,
    beatgrid_times_ms: list[float],
) -> Optional[tuple[int, str]]:
    """Return (elapsed_ms, source) for an absolute beat target from grid markers."""
    if len(beatgrid_times_ms) < 2:
        return None

    target = int(abs_beat)
    times = beatgrid_times_ms
    if 0 <= target < len(times):
        return int(round(times[target])), "grid"

    interval = times[-1] - times[-2]
    if interval <= 0:
        return None
    elapsed_ms = times[-1] + ((target - (len(times) - 1)) * interval)
    return int(round(elapsed_ms)), "grid-extrapolated"
