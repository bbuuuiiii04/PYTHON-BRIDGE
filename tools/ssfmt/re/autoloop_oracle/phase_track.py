"""Autoloop phase timeline extracted from session JSONL."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PhaseSample:
    epoch_s: float
    abs_beat_pos: float
    bpm: float
    active_deck: int
    lighting_mode: str
    playing: bool
    accepted_note: int | None
    phrase_anchor_last_beat: float
    midi_refire_origin_beat: float


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def load_phase_samples(session_jsonl: str | Path) -> list[PhaseSample]:
    samples: list[PhaseSample] = []
    with Path(session_jsonl).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("kind") != "autoloop_phase":
                continue
            samples.append(PhaseSample(
                epoch_s=float(row["epoch_ns"]) / 1_000_000_000.0,
                abs_beat_pos=float(row["abs_beat_pos"]),
                bpm=float(row["bpm"]),
                active_deck=int(row["active_deck"]),
                lighting_mode=str(row["lighting_mode"]),
                playing=bool(row["playing"]),
                accepted_note=_optional_int(row.get("accepted_note")),
                phrase_anchor_last_beat=float(row["phrase_anchor_last_beat"]),
                midi_refire_origin_beat=float(row["midi_refire_origin_beat"]),
            ))
    samples.sort(key=lambda sample: sample.epoch_s)
    return samples


def beat_at(samples: list[PhaseSample], t: float) -> float | None:
    if not samples or t < samples[0].epoch_s or t > samples[-1].epoch_s:
        return None

    low = 0
    high = len(samples) - 1
    while low <= high:
        mid = (low + high) // 2
        mid_t = samples[mid].epoch_s
        if mid_t < t:
            low = mid + 1
        elif mid_t > t:
            high = mid - 1
        else:
            return samples[mid].abs_beat_pos

    left_index = high
    right_index = low
    if left_index < 0 or right_index >= len(samples):
        return None
    left = samples[left_index]
    right = samples[right_index]
    if left.active_deck != right.active_deck:
        return None
    if right.abs_beat_pos < left.abs_beat_pos:
        return None
    span = right.epoch_s - left.epoch_s
    if span <= 0:
        return None
    ratio = (t - left.epoch_s) / span
    return left.abs_beat_pos + (right.abs_beat_pos - left.abs_beat_pos) * ratio
