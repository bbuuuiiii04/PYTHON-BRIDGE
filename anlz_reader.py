"""Read Rekordbox ANLZ phrase and waveform data for smart-drop planning.

# SPIKE RESULTS
# 2026-05-07, source:
# /Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/eac/ed59d-f6a1-4814-a850-312b003de118/
# A: waveform entries are exposed as tag.content.entries.
# B: PWV3/PWAV entries are bare ints; height = entry & 0x1F.
# C: no useful duration field found; use validated full beatgrid duration:
#    last_beat_time_ms + (last_beat_time_ms - previous_beat_time_ms).
#    Sparse .EXT PQT2 with only 2 timestamps must be rejected; .DAT PQTZ provided
#    the full tested grid.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Optional

from .models import SmartDropEnergyShadow

log = logging.getLogger("anlz_reader")

SMART_DROP_TELEMETRY_CSV_ENV = "RBSS_SMART_DROP_TELEMETRY_CSV"
_SMART_DROP_TELEMETRY_SCHEMA = 1
_SMART_DROP_TELEMETRY_FIELDS = [
    "schema",
    "created_at",
    "source",
    "anlz_beat",
    "suggested_beat",
    "anlz_elapsed_ms",
    "suggested_elapsed_ms",
    "score_at_anlz",
    "score_at_suggested",
    "confidence",
    "top_candidates_json",
    "feature_breakdown_json",
    "correct_beat",
    "correct_elapsed_ms",
    "notes",
]

BREAKDOWN_THRESHOLD = 0.35
DROP_THRESHOLD = 0.65
MIN_LOW_BARS = 3
MAX_DROP_GAP_BARS = 2
POST_HIT_SHIFT_WINDOW_BARS = 8
POST_HIT_MIN_LOW_BARS = 2
COOLDOWN_BARS = 16
IGNORE_INTRO_BARS = 8
IGNORE_OUTRO_BARS = 8

_MIN_BEATGRID_INTERVAL_MS = 150.0
_MAX_BEATGRID_INTERVAL_MS = 3000.0
_PWV3_MS_PER_ENTRY_FALLBACK = 6.7

# Multi-feature smart-drop scoring weights.
#
# Produced by tools/eval_smart_drop_algorithm.py from the anchored-tuner-harness
# tuner commit on main: 288203697e207420c894529327f30d9c38775443
# branch with the anchored pairwise hinge rank-loss objective and no anchors:
#
#     python tools/eval_smart_drop_algorithm.py tune \
#         --corpus ~/smart_drop_corpus_filtered.yaml \
#         --objective rank_loss --margin 0.1 --l1 0.01 --seed 0
#
# Corpus: ~/smart_drop_corpus_filtered.yaml (66 tracks / 367 labeled windows).
#
# Validation (5 seeds x 20 random track-level splits = 100 split-comparisons):
#   retune vs PR #88 (shipped): 68/26/6 wins/losses/ties, mean diff +1.5pp.
#   retune vs PR #87:           50/40/10,                 mean diff +0.7pp.
#   PR #88 vs PR #87:           40/55/5,                  mean diff -0.8pp
#                               (i.e. PR #88's nominal advantage was noise).
#   Bootstrap-ci paired diff vs shipped on full corpus (n=56 unique tracks):
#                               +1.6pp, 95% CI [-2.3pp, +5.5pp].
#
# The anchored-on-seed-features prior used in PR #88 is dropped. Under the
# rank-loss objective the data drives centroid_drop and spectral_flux_onset
# to ~0 on this corpus; forcing them positive (PR #88) measurably hurt
# generalization. See docs/drop_detection_review_v2.md.
MULTI_FEATURE_WEIGHTS_V2: dict[str, float] = {
    "onset_score": 0.000000,
    "broad_onset_score": 0.000000,
    "post_lift": 0.013896,
    "pre_valley_depth": 0.006064,
    "downbeat_alignment": 0.077649,
    "distance_penalty": 0.031940,
    "kick_pattern_onset": 0.958909,
    "bass_pattern_onset": 0.000000,
    "low_mid_pattern_onset": 0.000000,
    "high_mid_pattern_onset": 1.661027,
    "phrase_energy_step": 0.344555,
    "spectral_balance_shift": 0.037456,
    "centroid_drop": 0.000000,
    "spectral_flux_onset": 0.003867,
}

MultiFeatureScorer = Callable[
    [int, list[int], list[float], int, Optional[Any]],
    float,
]


@dataclass(frozen=True)
class WaveformContext:
    heights: tuple[int, ...]
    ms_per_entry: float
    beatgrid_times_ms: tuple[float, ...]


@dataclass
class TrackAnlzData:
    drop_beat_indices: list[int]
    breakdown_beat_indices: list[int] = field(default_factory=list)
    buildup_beat_indices: list[int] = field(default_factory=list)
    mood: int = 0
    energy_shadow: list[SmartDropEnergyShadow] = field(default_factory=list)
    waveform_context: Optional[WaveformContext] = None


def read_smart_drop_energy_shadow(
    anlz_path: str,
    selected_drops: list[int],
) -> list[SmartDropEnergyShadow]:
    """Return waveform-energy suggestions near ANLZ drops without moving targets."""
    if not selected_drops:
        return []
    try:
        from pyrekordbox.anlz import AnlzFile  # type: ignore
    except Exception as exc:
        log.debug("ANLZ energy shadow unavailable: pyrekordbox import failed: %s", exc)
        return []

    try:
        parsed = []
        for path in _candidate_anlz_paths(anlz_path):
            try:
                parsed.append((path, AnlzFile.parse_file(path)))
            except Exception as exc:
                log.debug("ANLZ energy shadow parse failed for %s: %s", path, exc)
        return _extract_smart_drop_energy_shadow(parsed, selected_drops)
    except Exception:
        log.debug("ANLZ energy shadow read failed", exc_info=True)
        return []


def read_anlz_drops(anlz_path: str) -> TrackAnlzData:
    """Parse ANLZ files for the given path and return drop beat data.

    Returns TrackAnlzData([]) on parse failures, missing files, missing pyrekordbox,
    unsupported tag shapes, or no detected drops.
    """
    try:
        from pyrekordbox.anlz import AnlzFile  # type: ignore
    except Exception as exc:
        log.debug("ANLZ drop read unavailable: pyrekordbox import failed: %s", exc)
        return TrackAnlzData([])

    try:
        parsed = []
        for path in _candidate_anlz_paths(anlz_path):
            try:
                parsed.append((path, AnlzFile.parse_file(path)))
            except Exception as exc:
                log.debug("ANLZ drop parse failed for %s: %s", path, exc)

        if not parsed:
            return TrackAnlzData([])

        mood, pssi_drops, pssi_breakdowns, pssi_buildups = _extract_pssi_phrases(parsed)
        waveform_context = _extract_waveform_context(parsed)
        if pssi_drops or pssi_breakdowns:
            return TrackAnlzData(
                pssi_drops,
                pssi_breakdowns,
                pssi_buildups,
                mood,
                _extract_smart_drop_energy_shadow(parsed, pssi_drops),
                waveform_context,
            )

        waveform_drops, waveform_breakdowns = _extract_waveform_phrases(parsed)
        return TrackAnlzData(
            waveform_drops,
            waveform_breakdowns,
            [],
            0,
            _extract_smart_drop_energy_shadow(parsed, waveform_drops),
            waveform_context,
        )
    except Exception:
        log.debug("ANLZ drop read failed", exc_info=True)
        return TrackAnlzData([])


def _extract_pssi_phrases(parsed: list[tuple[Path, Any]]) -> tuple[int, list[int], list[int], list[int]]:
    ordered = sorted(parsed, key=lambda item: _candidate_priority(item[0]))
    for _path, anlz in ordered:
        mood = 0
        drops: set[int] = set()
        breakdowns: set[int] = set()
        buildups: set[int] = set()
        for tag in _safe_getall_tags(anlz, "PSSI"):
            content = getattr(tag, "content", None)
            mood = int(getattr(content, "mood", 0))
            entries = getattr(content, "entries", None)
            if entries is None and isinstance(content, dict):
                entries = content.get("entries")
            if entries is None:
                continue
            for entry in entries:
                try:
                    kind = int(getattr(entry, "kind"))
                    pssi_beat = int(getattr(entry, "beat"))
                except Exception:
                    continue
                bridge_beat = max(0, pssi_beat - 1)
                if bridge_beat <= 0:
                    continue
                
                if mood == 1:
                    if kind == 5:
                        drops.add(bridge_beat)
                    elif kind == 3:
                        breakdowns.add(bridge_beat)
                    elif kind == 2:
                        buildups.add(bridge_beat)
                elif mood in (2, 3):
                    if kind == 9:
                        drops.add(bridge_beat)
                    elif kind == 8:
                        breakdowns.add(bridge_beat)
                    elif kind in (4, 5):
                        buildups.add(bridge_beat)

        if drops or breakdowns:
            return mood, sorted(drops), sorted(breakdowns), sorted(buildups)
    return 0, [], [], []


def _candidate_priority(path: Path) -> int:
    suffix = path.suffix.upper()
    if suffix == ".EXT":
        return 0
    if suffix == ".2EX":
        return 1
    if suffix == ".DAT":
        return 2
    return 3


def _extract_waveform_phrases(parsed: list[tuple[Path, Any]]) -> tuple[list[int], list[int]]:
    try:
        waveform = _extract_waveform(parsed)
        if waveform is None:
            return [], []
        heights, waveform_source = waveform

        beatgrid_times_ms = _extract_beatgrid_times(parsed)
        if len(beatgrid_times_ms) >= 8:
            waveform_duration_ms = _duration_from_beatgrid(beatgrid_times_ms)
        elif waveform_source == "PWV3":
            waveform_duration_ms = len(heights) * _PWV3_MS_PER_ENTRY_FALLBACK
        else:
            waveform_duration_ms = 0.0

        bar_energies = _compute_bar_energies(heights, waveform_duration_ms, beatgrid_times_ms)
        if not bar_energies:
            return [], []
            
        track_max = max(bar_energies)
        if track_max <= 0:
            return [], []
            
        return (
            _detect_drop_beats(bar_energies, track_max),
            _detect_breakdown_beats(bar_energies, track_max)
        )
    except Exception:
        log.debug("ANLZ waveform phrase extract failed", exc_info=True)
        return [], []


def _extract_smart_drop_energy_shadow(
    parsed: list[tuple[Path, Any]],
    selected_drops: list[int],
) -> list[SmartDropEnergyShadow]:
    try:
        waveform = _extract_waveform(parsed)
        if waveform is None:
            return []
        heights, _waveform_source = waveform
        beatgrid_times_ms = _extract_beatgrid_times(parsed)
        if len(beatgrid_times_ms) < 8:
            return []
        waveform_duration_ms = _duration_from_beatgrid(beatgrid_times_ms)
        return _calculate_smart_drop_energy_shadow(
            heights,
            waveform_duration_ms,
            beatgrid_times_ms,
            selected_drops,
        )
    except Exception:
        log.debug("ANLZ energy shadow extract failed", exc_info=True)
        return []


def _extract_waveform_context(parsed: list[tuple[Path, Any]]) -> Optional[WaveformContext]:
    waveform = _extract_waveform(parsed)
    if waveform is None:
        return None
    heights, _waveform_source = waveform
    beatgrid_times_ms = _extract_beatgrid_times(parsed)
    if len(beatgrid_times_ms) < 8:
        return None
    waveform_duration_ms = _duration_from_beatgrid(beatgrid_times_ms)
    if waveform_duration_ms <= 0 or not heights:
        return None
    ms_per_entry = waveform_duration_ms / len(heights)
    if ms_per_entry <= 0:
        return None
    return WaveformContext(
        heights=tuple(heights),
        ms_per_entry=ms_per_entry,
        beatgrid_times_ms=tuple(beatgrid_times_ms),
    )


def _calculate_smart_drop_energy_shadow(
    heights: list[int],
    waveform_duration_ms: float,
    beatgrid_times_ms: list[float],
    selected_drops: list[int],
    *,
    scorer: Optional[MultiFeatureScorer] = None,
    spectral_features: Optional[Any] = None,
) -> list[SmartDropEnergyShadow]:
    if not heights or waveform_duration_ms <= 0 or len(beatgrid_times_ms) < 8:
        return []

    ms_per_entry = waveform_duration_ms / len(heights)
    if ms_per_entry <= 0:
        return []

    if scorer is not None:
        return _v2_compute_shadows(
            heights,
            beatgrid_times_ms,
            selected_drops,
            scorer=scorer,
            spectral_features=spectral_features,
        )
    return _v1_compute_shadows(heights, ms_per_entry, beatgrid_times_ms, selected_drops)


def _v1_compute_shadows(
    heights: list[int],
    ms_per_entry: float,
    beatgrid_times_ms: list[float],
    selected_drops: list[int],
) -> list[SmartDropEnergyShadow]:
    shadows: list[SmartDropEnergyShadow] = []
    for drop_beat in sorted(set(int(beat) for beat in selected_drops)):
        lift_at_anlz = _energy_lift_for_beat(
            heights,
            ms_per_entry,
            beatgrid_times_ms,
            drop_beat,
        )
        if lift_at_anlz is None:
            continue

        best_beat = drop_beat
        best_lift = lift_at_anlz
        for candidate_beat in range(drop_beat + 1, drop_beat + 9):
            candidate_lift = _energy_lift_for_beat(
                heights,
                ms_per_entry,
                beatgrid_times_ms,
                candidate_beat,
            )
            if candidate_lift is None:
                continue
            if candidate_lift > best_lift:
                best_beat = candidate_beat
                best_lift = candidate_lift

        shadows.append(SmartDropEnergyShadow(
            anlz_beat=drop_beat,
            suggested_beat=best_beat,
            anlz_elapsed_ms=int(round(beatgrid_times_ms[drop_beat])),
            suggested_elapsed_ms=int(round(beatgrid_times_ms[best_beat])),
            lift_at_anlz=lift_at_anlz,
            lift_at_suggested=best_lift,
            confidence=best_lift - lift_at_anlz,
        ))
    return shadows


def _v2_compute_shadows(
    heights: list[int],
    beatgrid_times_ms: list[float],
    selected_drops: list[int],
    *,
    scorer: MultiFeatureScorer,
    spectral_features: Optional[Any] = None,
) -> list[SmartDropEnergyShadow]:
    shadows: list[SmartDropEnergyShadow] = []
    source = "v2_spectral" if spectral_features is not None else "v2_waveform"
    for drop_beat in sorted(set(int(beat) for beat in selected_drops)):
        if drop_beat < 0 or drop_beat >= len(beatgrid_times_ms):
            continue

        scored: list[tuple[int, float]] = []
        for candidate_beat in range(drop_beat, drop_beat + 9):
            if candidate_beat < 0 or candidate_beat >= len(beatgrid_times_ms):
                continue
            score = scorer(
                candidate_beat,
                heights,
                beatgrid_times_ms,
                drop_beat,
                spectral_features,
            )
            scored.append((candidate_beat, score))
        if not scored:
            continue

        scored.sort(key=lambda item: item[1], reverse=True)
        best_beat, best_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else 0.0
        score_at_anlz = next(
            (score for beat, score in scored if beat == drop_beat),
            0.0,
        )
        confidence = _score_confidence(best_score, second_score)
        feature_breakdown = _multi_feature_breakdown(
            best_beat,
            heights,
            beatgrid_times_ms,
            drop_beat,
            spectral_features,
        )
        shadow = SmartDropEnergyShadow(
            anlz_beat=drop_beat,
            suggested_beat=best_beat,
            anlz_elapsed_ms=int(round(beatgrid_times_ms[drop_beat])),
            suggested_elapsed_ms=int(round(beatgrid_times_ms[best_beat])),
            lift_at_anlz=score_at_anlz,
            lift_at_suggested=best_score,
            confidence=confidence,
            score_at_anlz=score_at_anlz,
            score_at_suggested=best_score,
            feature_breakdown=feature_breakdown,
            source=source,
        )
        _append_smart_drop_telemetry(shadow, scored, feature_breakdown)
        shadows.append(shadow)
    return shadows


def _append_smart_drop_telemetry(
    shadow: SmartDropEnergyShadow,
    scored: list[tuple[int, float]],
    feature_breakdown: dict[str, float],
) -> None:
    path = os.environ.get(SMART_DROP_TELEMETRY_CSV_ENV, "")
    if not path:
        return
    try:
        telemetry_path = Path(path).expanduser()
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not telemetry_path.exists() or telemetry_path.stat().st_size == 0
        row = {
            "schema": _SMART_DROP_TELEMETRY_SCHEMA,
            "created_at": f"{time.time():.3f}",
            "source": shadow.source,
            "anlz_beat": shadow.anlz_beat,
            "suggested_beat": shadow.suggested_beat,
            "anlz_elapsed_ms": shadow.anlz_elapsed_ms,
            "suggested_elapsed_ms": shadow.suggested_elapsed_ms,
            "score_at_anlz": f"{shadow.score_at_anlz:.6f}",
            "score_at_suggested": f"{shadow.score_at_suggested:.6f}",
            "confidence": f"{shadow.confidence:.6f}",
            "top_candidates_json": json.dumps(
                [
                    {"beat": beat, "score": round(float(score), 6)}
                    for beat, score in scored[:9]
                ],
                separators=(",", ":"),
                sort_keys=True,
            ),
            "feature_breakdown_json": json.dumps(
                {name: round(float(value), 6) for name, value in feature_breakdown.items()},
                separators=(",", ":"),
                sort_keys=True,
            ),
            "correct_beat": "",
            "correct_elapsed_ms": "",
            "notes": "",
        }
        with telemetry_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_SMART_DROP_TELEMETRY_FIELDS)
            if needs_header:
                writer.writeheader()
            writer.writerow(row)
    except Exception:
        log.warning("smart-drop telemetry append failed", exc_info=True)


def _score_confidence(best: float, second_best: float) -> float:
    if best <= 0.0:
        return 0.0
    raw = (best - second_best) / max(best, 1e-6)
    return max(0.0, min(1.0, raw))


def _energy_lift_for_beat(
    heights: list[int],
    ms_per_entry: float,
    beatgrid_times_ms: list[float],
    beat: int,
) -> Optional[float]:
    before = _average_waveform_energy_for_beats(
        heights,
        ms_per_entry,
        beatgrid_times_ms,
        beat - 16,
        beat,
    )
    after = _average_waveform_energy_for_beats(
        heights,
        ms_per_entry,
        beatgrid_times_ms,
        beat,
        beat + 16,
    )
    if before is None or after is None:
        return None
    return after - before


def _onset_score(
    beat: int,
    heights: list[int],
    beatgrid_times_ms: list[float],
) -> float:
    energies = _beat_energies(heights, beatgrid_times_ms, beat, beat + 5)
    if len(energies) < 2:
        return 0.0
    return max(0.0, max(b - a for a, b in zip(energies, energies[1:])))


def _broad_onset_score(
    beat: int,
    heights: list[int],
    beatgrid_times_ms: list[float],
) -> float:
    before = _average_feature_energy(heights, beatgrid_times_ms, beat, beat + 2)
    after = _average_feature_energy(heights, beatgrid_times_ms, beat + 2, beat + 4)
    if before is None or after is None:
        return 0.0
    return max(0.0, after - before)


def _post_lift(
    beat: int,
    heights: list[int],
    beatgrid_times_ms: list[float],
) -> float:
    ms_per_entry = _ms_per_waveform_entry(heights, beatgrid_times_ms)
    if ms_per_entry is None:
        return 0.0
    lift = _energy_lift_for_beat(heights, ms_per_entry, beatgrid_times_ms, beat)
    return 0.0 if lift is None else lift


def _pre_valley_depth(
    beat: int,
    heights: list[int],
    beatgrid_times_ms: list[float],
) -> float:
    prior = _average_feature_energy(heights, beatgrid_times_ms, beat - 16, beat - 4)
    valley = _average_feature_energy(heights, beatgrid_times_ms, beat - 4, beat)
    if prior is None or valley is None:
        return 0.0
    return max(0.0, prior - valley)


def _downbeat_alignment(beat: int) -> float:
    if beat % 4 == 0:
        return 1.0
    if beat % 2 == 0:
        return 0.5
    return 0.0


def _distance_penalty(beat: int, anlz_beat: int) -> float:
    return max(0.0, 1.0 - (abs(int(beat) - int(anlz_beat)) / 8.0))


def _multi_feature_breakdown(
    beat: int,
    heights: list[int],
    beatgrid_times_ms: list[float],
    anlz_beat: int,
    spectral_features: Optional[Any],
) -> dict[str, float]:
    features = {
        "onset_score": _onset_score(beat, heights, beatgrid_times_ms),
        "broad_onset_score": _broad_onset_score(beat, heights, beatgrid_times_ms),
        "post_lift": _post_lift(beat, heights, beatgrid_times_ms),
        "pre_valley_depth": _pre_valley_depth(beat, heights, beatgrid_times_ms),
        "downbeat_alignment": _downbeat_alignment(beat),
        "distance_penalty": _distance_penalty(beat, anlz_beat),
    }
    def spectral_score(fn: Callable[[int, Any], float]) -> float:
        return 0.0 if spectral_features is None else fn(beat, spectral_features)

    features.update({
        "kick_pattern_onset": spectral_score(_kick_pattern_onset),
        "bass_pattern_onset": spectral_score(_bass_pattern_onset),
        "low_mid_pattern_onset": spectral_score(_low_mid_pattern_onset),
        "high_mid_pattern_onset": spectral_score(_high_mid_pattern_onset),
        "phrase_energy_step": spectral_score(_phrase_energy_step),
        "spectral_balance_shift": spectral_score(_spectral_balance_shift),
        "centroid_drop": spectral_score(_centroid_drop),
        "spectral_flux_onset": spectral_score(_spectral_flux_onset),
    })
    return features


def _multi_feature_score(
    beat: int,
    heights: list[int],
    beatgrid_times_ms: list[float],
    anlz_beat: int,
    spectral_features: Optional[Any],
    weights: Optional[dict[str, float]] = None,
) -> float:
    resolved = weights if weights is not None else MULTI_FEATURE_WEIGHTS_V2
    features = _multi_feature_breakdown(
        beat,
        heights,
        beatgrid_times_ms,
        anlz_beat,
        spectral_features,
    )
    return sum(features[name] * resolved.get(name, 0.0) for name in features)


def _make_multi_feature_scorer(weights: dict[str, float]) -> MultiFeatureScorer:
    weight_copy = dict(weights)

    def scorer(
        beat: int,
        heights: list[int],
        beatgrid_times_ms: list[float],
        anlz_beat: int,
        spectral_features: Optional[Any],
    ) -> float:
        return _multi_feature_score(
            beat,
            heights,
            beatgrid_times_ms,
            anlz_beat,
            spectral_features,
            weight_copy,
        )

    return scorer


def _kick_pattern_onset(beat: int, spectral_features: Any) -> float:
    return _pattern_onset(beat, _spectral_envelope(spectral_features, "kick_envelope"), window=8)


def _bass_pattern_onset(beat: int, spectral_features: Any) -> float:
    return _pattern_onset(beat, _spectral_envelope(spectral_features, "sub_bass_envelope"), window=8)


def _low_mid_pattern_onset(beat: int, spectral_features: Any) -> float:
    return _pattern_onset(beat, _spectral_envelope(spectral_features, "low_mid_envelope"), window=8)


def _high_mid_pattern_onset(beat: int, spectral_features: Any) -> float:
    return _pattern_onset(beat, _spectral_envelope(spectral_features, "high_mid_envelope"), window=8)


def _phrase_energy_step(beat: int, spectral_features: Any) -> float:
    kick, bass, high = _spectral_triplet(spectral_features)
    if not kick or not bass or not high:
        return 0.0
    n = min(len(kick), len(bass), len(high))
    combined = [kick[i] + bass[i] + high[i] for i in range(n)]
    return _pattern_onset(beat, combined, window=8)


def _spectral_balance_shift(beat: int, spectral_features: Any) -> float:
    kick, bass, high = _spectral_triplet(spectral_features)
    if not kick or not bass or not high:
        return 0.0
    n = min(len(kick), len(bass), len(high))
    before_start, after_end = max(0, beat - 8), min(n, beat + 8)
    if before_start >= beat or after_end <= beat:
        return 0.0

    def lows_ratio(start: int, end: int) -> float:
        lows = sum(kick[i] + bass[i] for i in range(start, end))
        highs = sum(high[i] for i in range(start, end)) + 1e-6
        return lows / (lows + highs)

    return max(0.0, lows_ratio(beat, after_end) - lows_ratio(before_start, beat))


def _centroid_drop(beat: int, spectral_features: Any) -> float:
    centroids = _per_beat_centroid(spectral_features)
    if not centroids:
        return 0.0
    before_start, after_end = max(0, beat - 8), min(len(centroids), beat + 8)
    if before_start >= beat or after_end <= beat:
        return 0.0
    before = sum(centroids[before_start:beat]) / (beat - before_start)
    after = sum(centroids[beat:after_end]) / (after_end - beat)
    return max(0.0, (before - after) / _BAND_CENTERS_HZ[-1])


def _spectral_flux_onset(beat: int, spectral_features: Any) -> float:
    energy = _per_beat_total_energy(spectral_features)
    if not energy or beat < 1 or beat >= len(energy):
        return 0.0
    peak = max(energy[max(0, beat - 1):min(len(energy), beat + 2)])
    baseline = sorted(energy[max(0, beat - 8):beat])
    if not baseline:
        return 0.0
    return max(0.0, peak - baseline[len(baseline) // 2])


def _pattern_onset(beat: int, envelope: list[float], window: int = 8) -> float:
    if not envelope:
        return 0.0
    after_end, before_start = min(len(envelope), beat + window), max(0, beat - window)
    if after_end <= beat or before_start >= beat:
        return 0.0
    after = sum(envelope[beat:after_end]) / (after_end - beat)
    before = sum(envelope[before_start:beat]) / (beat - before_start)
    return max(0.0, after - before)


_BAND_CENTERS_HZ = (60.0, 130.0, 500.0, 2400.0, 8000.0)
_SPECTRAL_BAND_ATTRS = (
    "sub_bass_envelope", "kick_envelope", "low_mid_envelope",
    "high_mid_envelope", "high_band_envelope",
)


def _spectral_bands(spectral_features: Any) -> tuple[list[float], ...]:
    return tuple(_spectral_envelope(spectral_features, attr) for attr in _SPECTRAL_BAND_ATTRS)


def _per_beat_centroid(spectral_features: Any) -> list[float]:
    bands = _spectral_bands(spectral_features)
    if not all(bands):
        return []
    centroids: list[float] = []
    for values in zip(*bands):
        total = sum(values)
        if total <= 1e-9:
            centroids.append(0.0)
            continue
        centroids.append(sum(c * v for c, v in zip(_BAND_CENTERS_HZ, values)) / total)
    return centroids


def _per_beat_total_energy(spectral_features: Any) -> list[float]:
    bands = _spectral_bands(spectral_features)
    return [] if not all(bands) else [sum(values) for values in zip(*bands)]


def _spectral_triplet(spectral_features: Any) -> tuple[list[float], list[float], list[float]]:
    return (
        _spectral_envelope(spectral_features, "kick_envelope"),
        _spectral_envelope(spectral_features, "sub_bass_envelope"),
        _spectral_envelope(spectral_features, "high_band_envelope"),
    )


def _spectral_envelope(spectral_features: Any, attr: str) -> list[float]:
    try:
        return [float(value) for value in getattr(spectral_features, attr)]
    except Exception:
        return []


def _beat_energies(
    heights: list[int],
    beatgrid_times_ms: list[float],
    start_beat: int,
    end_beat: int,
) -> list[float]:
    energies: list[float] = []
    for beat in range(start_beat, end_beat):
        value = _average_feature_energy(heights, beatgrid_times_ms, beat, beat + 1)
        if value is not None:
            energies.append(value)
    return energies


def _average_feature_energy(
    heights: list[int],
    beatgrid_times_ms: list[float],
    start_beat: int,
    end_beat: int,
) -> Optional[float]:
    ms_per_entry = _ms_per_waveform_entry(heights, beatgrid_times_ms)
    if ms_per_entry is None:
        return None
    return _average_waveform_energy_for_beats(
        heights,
        ms_per_entry,
        beatgrid_times_ms,
        start_beat,
        end_beat,
    )


def _ms_per_waveform_entry(
    heights: list[int],
    beatgrid_times_ms: list[float],
) -> Optional[float]:
    if not heights or len(beatgrid_times_ms) < 2:
        return None
    duration_ms = _duration_from_beatgrid(beatgrid_times_ms)
    if duration_ms <= 0:
        return None
    ms_per_entry = duration_ms / len(heights)
    if ms_per_entry <= 0:
        return None
    return ms_per_entry


def _average_waveform_energy_for_beats(
    heights: list[int],
    ms_per_entry: float,
    beatgrid_times_ms: list[float],
    start_beat: int,
    end_beat: int,
) -> Optional[float]:
    if start_beat < 0 or end_beat <= start_beat or end_beat >= len(beatgrid_times_ms):
        return None
    start_ms = beatgrid_times_ms[start_beat]
    end_ms = beatgrid_times_ms[end_beat]
    if end_ms <= start_ms:
        return None
    start_idx = _clamp_index(int(start_ms / ms_per_entry), len(heights))
    end_idx = _clamp_index(int(end_ms / ms_per_entry), len(heights))
    if end_idx <= start_idx:
        end_idx = min(len(heights), start_idx + 1)
    window = heights[start_idx:end_idx]
    if not window:
        return None
    return sum(window) / len(window)


def _candidate_anlz_paths(anlz_path: str) -> list[Path]:
    path = Path(anlz_path)
    candidates: list[Path] = []
    if path.suffix.upper() in (".DAT", ".EXT", ".2EX"):
        for suffix in (".EXT", ".2EX", ".DAT"):
            candidate = path.with_suffix(suffix)
            if candidate.exists():
                candidates.append(candidate)
    if not candidates and path.exists():
        candidates.append(path)

    seen: set[str] = set()
    result: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _compute_bar_energies(
    heights: list[int],
    waveform_duration_ms: float,
    beatgrid_times_ms: list[float],
) -> list[float]:
    if not heights or waveform_duration_ms <= 0 or len(beatgrid_times_ms) < 8:
        return []

    times = [float(t) for t in beatgrid_times_ms if float(t) >= 0.0]
    if len(times) < 8:
        return []

    total_bars = (len(times) - 1) // 4
    if total_bars <= IGNORE_INTRO_BARS + IGNORE_OUTRO_BARS:
        return []

    ms_per_entry = waveform_duration_ms / len(heights)
    if ms_per_entry <= 0:
        return []

    use_mean = len(heights) < total_bars
    bar_energies: list[float] = []
    for bar in range(total_bars):
        start_ms = times[bar * 4]
        end_ms = times[(bar + 1) * 4]
        if end_ms <= start_ms:
            return []
        start_idx = _clamp_index(int(start_ms / ms_per_entry), len(heights))
        end_idx = _clamp_index(int(end_ms / ms_per_entry), len(heights))
        if end_idx <= start_idx:
            end_idx = min(len(heights), start_idx + 1)
        window = heights[start_idx:end_idx]
        if not window:
            bar_energies.append(0.0)
        elif use_mean:
            bar_energies.append(sum(window) / len(window))
        else:
            bar_energies.append(float(max(window)))

    return bar_energies

def _detect_drop_beats(
    bar_energies: list[float],
    track_max: float,
) -> list[int]:
    """Pure drop detection from pre-extracted bar energies."""
    try:
        total_bars = len(bar_energies)
        low_cutoff = BREAKDOWN_THRESHOLD * track_max
        high_cutoff = DROP_THRESHOLD * track_max
        drops: list[int] = []
        last_accepted = -10**9
        i = 0
        while i < len(bar_energies):
            if bar_energies[i] >= low_cutoff:
                i += 1
                continue

            low_start = i
            while i < len(bar_energies) and bar_energies[i] < low_cutoff:
                i += 1
            low_len = i - low_start
            if low_len < MIN_LOW_BARS:
                continue

            scan = i
            while scan < len(bar_energies):
                if scan - i > MAX_DROP_GAP_BARS:
                    break
                if bar_energies[scan] > high_cutoff:
                    drop_bar = _refine_drop_bar_after_buildup_hit(
                        bar_energies, scan, low_cutoff, high_cutoff
                    )
                    drop_beat = drop_bar * 4
                    if (
                        drop_beat >= IGNORE_INTRO_BARS * 4
                        and drop_beat < (total_bars - IGNORE_OUTRO_BARS) * 4
                        and drop_beat - last_accepted >= COOLDOWN_BARS * 4
                    ):
                        drops.append(drop_beat)
                        last_accepted = drop_beat
                    i = scan + 1
                    break
                scan += 1
            else:
                break

        return sorted(drops)
    except Exception:
        log.debug("ANLZ drop detect failed", exc_info=True)
        return []

def _detect_breakdown_beats(
    bar_energies: list[float],
    track_max: float,
) -> list[int]:
    """Detect high->low energy transitions (breakdowns)."""
    try:
        total_bars = len(bar_energies)
        low_cutoff = BREAKDOWN_THRESHOLD * track_max
        high_cutoff = DROP_THRESHOLD * track_max
        breakdowns: list[int] = []
        
        i = 0
        while i < len(bar_energies):
            if bar_energies[i] < high_cutoff:
                i += 1
                continue
                
            high_end = i
            while high_end < len(bar_energies) and bar_energies[high_end] >= low_cutoff:
                high_end += 1
                
            if high_end >= len(bar_energies):
                break
                
            low_start = high_end
            low_end = low_start
            while low_end < len(bar_energies) and bar_energies[low_end] < low_cutoff:
                low_end += 1
                
            if low_end - low_start >= MIN_LOW_BARS:
                breakdown_beat = low_start * 4
                if (
                    breakdown_beat >= IGNORE_INTRO_BARS * 4
                    and breakdown_beat < (total_bars - IGNORE_OUTRO_BARS) * 4
                ):
                    breakdowns.append(breakdown_beat)
            i = low_end
            
        return sorted(breakdowns)
    except Exception:
        log.debug("ANLZ drop detect failed", exc_info=True)
        return []


def _refine_drop_bar_after_buildup_hit(
    bar_energies: list[float],
    candidate_bar: int,
    low_cutoff: float,
    high_cutoff: float,
) -> int:
    """Shift from a buildup hit to a following post-break low->hit pattern.

    Some tracks spike at the start of a buildup, then briefly drop to a final quiet
    valley before the true drop. If that valley happens shortly after the candidate,
    use the high bar after the valley as the drop.
    """
    max_scan = min(len(bar_energies), candidate_bar + POST_HIT_SHIFT_WINDOW_BARS + 1)
    i = candidate_bar + 1
    while i < max_scan:
        if bar_energies[i] >= low_cutoff:
            i += 1
            continue
        low_start = i
        while i < max_scan and bar_energies[i] < low_cutoff:
            i += 1
        if i - low_start >= POST_HIT_MIN_LOW_BARS and i < len(bar_energies):
            if bar_energies[i] > high_cutoff:
                return i
        i += 1
    return candidate_bar


def _clamp_index(index: int, length: int) -> int:
    return max(0, min(length, index))


def _extract_waveform(parsed: list[tuple[Path, Any]]) -> Optional[tuple[list[int], str]]:
    for tag_type in ("PWV3", "PWAV"):
        for _path, anlz in parsed:
            for tag in _safe_getall_tags(anlz, tag_type):
                entries = _tag_entries(tag)
                if entries:
                    return ([int(entry) & 0x1F for entry in entries], tag_type)
    return None


def _extract_beatgrid_times(parsed: list[tuple[Path, Any]]) -> list[float]:
    for tag_type in ("PQT2", "PQTZ"):
        for path, anlz in parsed:
            for tag in _safe_getall_tags(anlz, tag_type):
                times = _grid_times_from_tag(tag, f"{tag_type}:{path.name}")
                if times:
                    return times
    return []


def _safe_getall_tags(anlz: Any, tag_type: str) -> list[Any]:
    try:
        return list(anlz.getall_tags(tag_type))
    except Exception:
        return []


def _tag_entries(tag: Any) -> list[int]:
    content = getattr(tag, "content", None)
    entries = getattr(content, "entries", None)
    if entries is None and isinstance(content, dict):
        entries = content.get("entries")
    if entries is None:
        return []
    try:
        return [int(entry) for entry in entries]
    except Exception:
        return []


def _grid_times_from_tag(tag: Any, source: str) -> list[float]:
    try:
        times = [float(t) * 1000.0 for t in tag.get_times()]
    except Exception as exc:
        log.debug("ANLZ %s beatgrid time read failed: %s", source, exc)
        return []

    rows = sorted(time_ms for time_ms in times if time_ms >= 0.0)
    if len(rows) < 8:
        return []

    intervals = [b - a for a, b in zip(rows, rows[1:])]
    if not _plausible_intervals(intervals):
        log.debug("ANLZ %s rejected implausible beatgrid intervals=%s", source, intervals[:8])
        return []
    return rows


def _plausible_intervals(intervals: list[float]) -> bool:
    if not intervals or any(interval <= 0.0 for interval in intervals):
        return False
    median = sorted(intervals)[len(intervals) // 2]
    return _MIN_BEATGRID_INTERVAL_MS <= median <= _MAX_BEATGRID_INTERVAL_MS


def _duration_from_beatgrid(beatgrid_times_ms: list[float]) -> float:
    if len(beatgrid_times_ms) < 2:
        return 0.0
    return beatgrid_times_ms[-1] + (beatgrid_times_ms[-1] - beatgrid_times_ms[-2])
