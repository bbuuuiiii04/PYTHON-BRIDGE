"""Pure align-and-diff core for the offline Autoloop oracle."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Callable, Iterable

from .groundtruth import DMX_CH

TICKS_PER_BEAT = 600
ALIGNMENT_NOTE = (
    "latency_s and phase_offset_beats are partially degenerate; the result proves "
    "the best alignment, not independent physical constants"
)


def _ensure_repo_parent_on_path() -> None:
    parent = str(Path(__file__).resolve().parents[5])
    if parent not in sys.path:
        sys.path.insert(0, parent)


_ensure_repo_parent_on_path()
from rb_ss_bridge_v2.soundswitch_laser_player import render_autoloop_frame


@dataclass(frozen=True, slots=True)
class LookScore:
    scored: int = 0
    exact: int = 0

    @property
    def exact_rate(self) -> float | None:
        return self.exact / self.scored if self.scored else None


@dataclass(frozen=True, slots=True)
class WorstSample:
    timestamp: float
    look: str
    mismatch_count: int
    max_abs_error: int


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total_frames: int
    scored_frames: int
    exact_match_frames: int
    excluded_counts: dict[str, int] = field(default_factory=dict)
    per_channel_mismatches: dict[int, int] = field(default_factory=dict)
    per_look: dict[str, LookScore] = field(default_factory=dict)
    worst_samples: tuple[WorstSample, ...] = ()

    @property
    def exact_match_rate(self) -> float | None:
        return self.exact_match_frames / self.scored_frames if self.scored_frames else None


@dataclass(frozen=True, slots=True)
class Best:
    latency_s: float
    phase_offset_beats: float
    score: ScoreResult
    note: str = ALIGNMENT_NOTE


@dataclass(frozen=True, slots=True)
class _Selection:
    look: str | None
    reason: str | None


def phase_tick(abs_beat: float, phase_offset_beats: float) -> int:
    return max(0, round((abs_beat + phase_offset_beats) * TICKS_PER_BEAT))


def predicted_frame(loop: object, abs_beat: float, phase_offset_beats: float) -> tuple[int, ...]:
    return render_autoloop_frame(loop, phase_tick(abs_beat, phase_offset_beats))


def frame_mismatch(predicted: tuple[int, ...], actual: tuple[int, ...], tol: int) -> int:
    if len(predicted) != DMX_CH or len(actual) != DMX_CH:
        raise ValueError(f"predicted and actual frames must be {DMX_CH} channels")
    return sum(abs(predicted[index] - actual[index]) > tol for index in range(DMX_CH))


def _selection(look_fn: Callable[[float], str | None], t: float, abs_beat: float):
    if hasattr(look_fn, "selection_at"):
        return look_fn.selection_at(t, abs_beat)
    return _Selection(look_fn(t), None)


def _cached_frame(
    loop: object,
    look: str,
    abs_beat: float,
    phase_offset_beats: float,
    frame_cache: dict[tuple[str, int], tuple[int, ...]] | None,
) -> tuple[int, ...]:
    tick = phase_tick(abs_beat, phase_offset_beats)
    key = (look, tick % 19_200)
    if frame_cache is not None and key in frame_cache:
        return frame_cache[key]
    frame = render_autoloop_frame(loop, tick)
    if frame_cache is not None:
        frame_cache[key] = frame
    return frame


def score(
    frames: Iterable[tuple[float, tuple[int, ...]]],
    beat_fn: Callable[[float], float | None],
    look_fn: Callable[[float], str | None],
    loops: dict[str, object],
    *,
    latency_s: float,
    phase_offset_beats: float,
    tol: int,
    look_statuses: dict[str, str] | None = None,
    frame_cache: dict[tuple[str, int], tuple[int, ...]] | None = None,
) -> ScoreResult:
    total = 0
    scored = 0
    exact = 0
    excluded: dict[str, int] = {}
    channels: dict[int, int] = {}
    look_counts: dict[str, list[int]] = {}
    worst: list[WorstSample] = []

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for timestamp, actual in frames:
        total += 1
        aligned_t = timestamp - latency_s
        abs_beat = beat_fn(aligned_t)
        if abs_beat is None:
            exclude("transition")
            continue
        selected = _selection(look_fn, aligned_t, abs_beat)
        look = selected.look
        if look is None:
            exclude(selected.reason or "idle")
            continue
        loop = loops.get(look)
        if loop is None:
            exclude((look_statuses or {}).get(look, "CONTENT_DRIFTED"))
            continue

        predicted = _cached_frame(loop, look, abs_beat, phase_offset_beats, frame_cache)
        mismatched_channels = [
            index + 1
            for index in range(DMX_CH)
            if abs(predicted[index] - actual[index]) > tol
        ]
        mismatch_count = len(mismatched_channels)
        scored += 1
        if mismatch_count == 0:
            exact += 1
        for channel in mismatched_channels:
            channels[channel] = channels.get(channel, 0) + 1
        counts = look_counts.setdefault(look, [0, 0])
        counts[0] += 1
        counts[1] += int(mismatch_count == 0)
        if mismatch_count:
            max_error = max(abs(predicted[index] - actual[index]) for index in range(DMX_CH))
            worst.append(WorstSample(timestamp, look, mismatch_count, max_error))
            worst.sort(key=lambda item: (item.mismatch_count, item.max_abs_error), reverse=True)
            del worst[10:]

    return ScoreResult(
        total_frames=total,
        scored_frames=scored,
        exact_match_frames=exact,
        excluded_counts=dict(sorted(excluded.items())),
        per_channel_mismatches=dict(sorted(channels.items())),
        per_look={
            look: LookScore(scored=values[0], exact=values[1])
            for look, values in sorted(look_counts.items())
        },
        worst_samples=tuple(worst),
    )


def search(
    frames: Iterable[tuple[float, tuple[int, ...]]],
    beat_fn: Callable[[float], float | None],
    look_fn: Callable[[float], str | None],
    loops: dict[str, object],
    *,
    latency_grid: Iterable[float],
    phase_grid: Iterable[float],
    tol: int,
    look_statuses: dict[str, str] | None = None,
) -> Best:
    frame_list = list(frames)
    best: Best | None = None
    frame_cache: dict[tuple[str, int], tuple[int, ...]] = {}
    for latency_s in latency_grid:
        for phase_offset_beats in phase_grid:
            result = score(
                frame_list,
                beat_fn,
                look_fn,
                loops,
                latency_s=latency_s,
                phase_offset_beats=phase_offset_beats,
                tol=tol,
                look_statuses=look_statuses,
                frame_cache=frame_cache,
            )
            candidate_rate = result.exact_match_rate or 0.0
            best_rate = best.score.exact_match_rate if best else None
            if best is None or candidate_rate > (best_rate or 0.0):
                best = Best(latency_s, phase_offset_beats, result)
    if best is None:
        raise ValueError("empty latency/phase search grid")
    return best
