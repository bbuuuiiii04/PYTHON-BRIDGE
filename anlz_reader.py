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

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("anlz_reader")

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


@dataclass
class TrackAnlzData:
    drop_beat_indices: list[int]


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

        pssi_drops = _extract_pssi_drop_beats(parsed)
        if pssi_drops:
            return TrackAnlzData(pssi_drops)

        waveform_drops = _extract_waveform_drop_beats(parsed)
        return TrackAnlzData(waveform_drops)
    except Exception:
        log.debug("ANLZ drop read failed", exc_info=True)
        return TrackAnlzData([])


def _extract_pssi_drop_beats(parsed: list[tuple[Path, Any]]) -> list[int]:
    drops: set[int] = set()
    for _path, anlz in parsed:
        for tag in _safe_getall_tags(anlz, "PSSI"):
            content = getattr(tag, "content", None)
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
                if kind == 5 and bridge_beat > 0:
                    drops.add(bridge_beat)
    return sorted(drops)


def _extract_waveform_drop_beats(parsed: list[tuple[Path, Any]]) -> list[int]:
    try:
        waveform = _extract_waveform(parsed)
        if waveform is None:
            return []
        heights, waveform_source = waveform

        beatgrid_times_ms = _extract_beatgrid_times(parsed)
        if len(beatgrid_times_ms) >= 8:
            waveform_duration_ms = _duration_from_beatgrid(beatgrid_times_ms)
        elif waveform_source == "PWV3":
            waveform_duration_ms = len(heights) * _PWV3_MS_PER_ENTRY_FALLBACK
        else:
            waveform_duration_ms = 0.0

        return _detect_drop_beats(heights, waveform_duration_ms, beatgrid_times_ms)
    except Exception:
        log.debug("ANLZ waveform drop extract failed", exc_info=True)
        return []


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


def _detect_drop_beats(
    heights: list[int],
    waveform_duration_ms: float,
    beatgrid_times_ms: list[float],
) -> list[int]:
    """Pure drop detection from pre-extracted heights and beat grid."""
    try:
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

        if not bar_energies:
            return []
        track_max = max(bar_energies)
        if track_max <= 0:
            return []

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
                        and drop_beat <= (total_bars - IGNORE_OUTRO_BARS) * 4
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
