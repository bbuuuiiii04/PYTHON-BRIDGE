#!/usr/bin/env python3
"""Pure measurement + gate functions for the STEMS PILOT (AWR-168).

No torch, no I/O, no audio decode — importable and testable with numpy alone.
The runner (``tools/stems_pilot.py``) does the heavy separation + STFT, builds
per-frame *linear* band-power arrays per stem, and calls these functions. Beat
aggregation reuses v4's exact semantics (imported from
``rb_ss_bridge_v2.audio_spectral_features``) so per-stem envelopes line up with
the v4 full-mix measures they must beat. The Goertzel modulation grid reuses
``rb_ss_bridge_v2.spectral_profile`` so wobble rates read on the same scale.

Offline tooling only; touches no bridge runtime state, no cache, no config.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Mapping, Sequence

# parent-of-repo on path so ``rb_ss_bridge_v2.*`` imports resolve (mirrors
# tools/spectral_sweep.py). tools->bridge imports are allowed; never the reverse.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    _beat_spans,
    _window_mean,
)
from rb_ss_bridge_v2.spectral_profile import (  # noqa: E402
    PULSE_RATE_GRID_CPB,
    _goertzel_power,
)

_DB_FLOOR_POWER = 1e-10

# Bands measured per stem; names index audio_spectral_features.BAND_RANGES.
# "full" is the whole-spectrum mean the runner supplies directly (not a range).
STEM_BANDS: dict[str, tuple[str, ...]] = {
    "drums": ("full", "attack_low", "high"),
    "bass": ("full", "sub", "bass"),
    "vocals": ("full", "mid"),
    "other": ("full", "mid"),
}

# Frozen pass/fail thresholds (Part B Task 4). Provisional through the first 5
# pilot tracks, then frozen; every change to these is logged in the report.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "sep_ok_frac": 0.90,          # criterion 1: >=90% separate without error
    "peak_rss_gb_max": 6.5,       # criterion 1: peak RSS under 6.5 GB
    "recon_within_frac": 0.90,    # criterion 2: >=90% of tracks re-sum
    "recon_median_db": 1.5,       # criterion 2: median per-beat |delta| <= 1.5 dB
    "pump_db": 3.0,               # criterion 3: pump visibility threshold
    "pump_min_anchors": 2,        # criterion 3: on >=2 sidechain anchors
    "ghost_margin_db": -12.0,     # criterion 4: bounded vocal ghosting
    "wobble_min_moments": 2,      # criterion 5: dominant rate at >=2 of 4 moments
    "elements_pass_floor": 6,     # criterion 6: >=6 of 9 elements PASS
}


def _db(power: object) -> object:
    return 10.0 * np.log10(np.maximum(power, _DB_FLOOR_POWER))


def stem_beat_envelopes(
    power_frames: Mapping[str, Sequence[float]],
    frame_times_ms: Sequence[float],
    beatgrid_times_ms: Sequence[float],
) -> dict[str, dict[str, tuple]]:
    """Per-beat and per-quarter-beat dB series for one stem's band-power frames.

    ``power_frames`` maps band name -> per-frame *linear* power. Beat-span math
    is identical to v4: arithmetic mean of linear power per span, then
    ``10*log10(max(p, 1e-10))``, rounded to 0.1 dB; empty spans fall back to the
    nearest frame (inside ``_window_mean``). Returns
    ``{band: {"beat": (dB,...), "quarter": ((dB,dB,dB,dB),...)}}``.
    """
    ft = np.asarray(frame_times_ms, dtype=float)
    spans = _beat_spans(beatgrid_times_ms)
    out: dict[str, dict[str, tuple]] = {}
    for band, frames in power_frames.items():
        f = np.asarray(frames, dtype=float)
        beat: list[float] = []
        quarter: list[tuple[float, ...]] = []
        for s, e in spans:
            beat.append(round(float(_db(_window_mean(np, f, ft, s, e))), 1))
            q = (e - s) / 4.0
            quarter.append(tuple(
                round(float(_db(_window_mean(np, f, ft, s + k * q, s + (k + 1) * q))), 1)
                for k in range(4)
            ))
        out[band] = {"beat": tuple(beat), "quarter": tuple(quarter)}
    return out


def reconstruction_delta_db(
    mix_full_frames: Sequence[float],
    summed_stems_full_frames: Sequence[float],
    frame_times_ms: Sequence[float],
    beatgrid_times_ms: Sequence[float],
) -> tuple[float, ...]:
    """Per-beat ``|dB(mix) - dB(sum-of-stems)|`` — stems must re-sum to the mix.

    Both inputs are per-frame linear full-spectrum power (the runner sums the
    stem *waveforms* then re-STFTs for a true reconstruction check). Identical
    arrays -> all zeros; a 3 dB power offset -> 3.0 per beat.
    """
    ft = np.asarray(frame_times_ms, dtype=float)
    spans = _beat_spans(beatgrid_times_ms)
    mix = np.asarray(mix_full_frames, dtype=float)
    summed = np.asarray(summed_stems_full_frames, dtype=float)
    out: list[float] = []
    for s, e in spans:
        d_mix = float(_db(_window_mean(np, mix, ft, s, e)))
        d_sum = float(_db(_window_mean(np, summed, ft, s, e)))
        out.append(round(abs(d_mix - d_sum), 3))
    return tuple(out)


def pump_visibility(
    bass_sub_quarters: Sequence[Sequence[float]],
    drums_low_quarters: Sequence[Sequence[float]],
) -> float:
    """Median within-beat dip depth (dB) of the bass sub at drum-kick instants.

    Scores only beats whose drum low-band peaks in quarter slot 0 (on the beat).
    Dip = ``max(bass sub slots 1..3) - bass sub slot 0`` — positive when the sub
    is ducked on the kick and recovers. Flat sustain -> ~0.
    """
    dips: list[float] = []
    for bass_q, drum_q in zip(bass_sub_quarters, drums_low_quarters):
        if len(bass_q) != 4 or len(drum_q) != 4:
            continue
        if int(np.argmax(np.asarray(drum_q, dtype=float))) != 0:
            continue  # kick not slot-0-led — skip
        recovery = max(bass_q[1], bass_q[2], bass_q[3])
        dips.append(float(recovery) - float(bass_q[0]))
    if not dips:
        return 0.0
    return round(float(np.median(dips)), 2)


def ghost_margin_db(
    vocal_full_beats: Sequence[float],
    instrumental_windows: Sequence[Sequence[int]],
) -> float:
    """Vocal-stem level inside known-instrumental windows vs the track vocal p95.

    ``instrumental_windows`` is a list of ``(start_beat, end_beat)`` index
    ranges. Returns ``p95(vocal in windows) - p95(vocal over track)``; more
    negative = cleaner (little vocal bleed where there should be none).
    """
    v = np.asarray(vocal_full_beats, dtype=float)
    if v.size == 0:
        return 0.0
    ref = float(np.percentile(v, 95))
    inside: list[float] = []
    for win in instrumental_windows:
        lo = max(0, int(win[0]))
        hi = min(int(v.size), int(win[1]))
        if hi > lo:
            inside.extend(v[lo:hi].tolist())
    if not inside:
        return 0.0
    ghost = float(np.percentile(np.asarray(inside, dtype=float), 95))
    return round(ghost - ref, 1)


def modulation_strength(
    stem_frames: Sequence[float],
    frame_hop_s: float,
    beatgrid_times_ms: Sequence[float],
    window: Sequence[int],
) -> tuple[float, float]:
    """(dominant cycles/beat, concentration) of a stem envelope's periodicity.

    Reuses ``lowmid_pulse_measure``'s validated preprocessing (linearize dB,
    divide by window mean minus 1 for DC removal, Hann, Goertzel over
    ``PULSE_RATE_GRID_CPB``) applied to any stem's frame-rate dB envelope over
    the ``(start_beat, end_beat)`` window. Full 0.5-8.0 cyc/beat grid, NO 2.5
    cyc/beat gate — the slow-wub range must be readable. Absent/short/silent
    data -> (0.0, 0.0), never an error.
    """
    grid = [float(g) for g in beatgrid_times_ms]
    lo = max(0, int(window[0]))
    hi = min(len(grid) - 1, int(window[1]))
    if hi - lo < 3 or frame_hop_s <= 0.0:
        return (0.0, 0.0)
    start_ms = grid[lo]
    end_ms = grid[hi]
    if end_ms <= start_ms:
        return (0.0, 0.0)
    hop_ms = frame_hop_s * 1000.0
    i0 = max(0, int(start_ms / hop_ms))
    i1 = min(len(stem_frames), int(end_ms / hop_ms))
    seg_db = list(stem_frames[i0:i1])
    if len(seg_db) < 32:
        return (0.0, 0.0)
    seg = [10.0 ** (v / 10.0) for v in seg_db]
    mean = sum(seg) / len(seg)
    if mean <= 0.0:
        return (0.0, 0.0)
    m = len(seg)
    x = [
        (seg[i] / mean - 1.0) * (0.5 - 0.5 * math.cos(2.0 * math.pi * i / (m - 1)))
        for i in range(m)
    ]
    beats_in_window = hi - lo
    nyquist_cycles = 0.45 * m
    powers: list[float] = []
    for cpb in PULSE_RATE_GRID_CPB:
        cycles = cpb * beats_in_window
        if cycles < 1.5 or cycles > nyquist_cycles:
            powers.append(0.0)
            continue
        powers.append(_goertzel_power(x, cycles))
    total = sum(powers)
    if total <= 0.0:
        return (0.0, 0.0)
    top = max(range(len(powers)), key=lambda i: powers[i])
    return (PULSE_RATE_GRID_CPB[top], round(powers[top] / total, 4))


def parse_mmss(text: object) -> float:
    """Operator time label -> milliseconds. Accepts "1:01.7", "75.3", "1:02:03"."""
    parts = str(text).strip().split(":")
    if len(parts) == 1:
        sec = float(parts[0])
    elif len(parts) == 2:
        sec = int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError(f"unparseable time label: {text!r}")
    if sec < 0:
        raise ValueError(f"negative time label: {text!r}")
    return sec * 1000.0


def nearest_beat(beatgrid_times_ms: Sequence[float], t_ms: float) -> int:
    """Index of the beat nearest to ``t_ms`` (0 on an empty grid)."""
    a = np.asarray(beatgrid_times_ms, dtype=float)
    if a.size == 0:
        return 0
    return int(np.argmin(np.abs(a - float(t_ms))))


def evaluate_gates(
    scorecard: Mapping[str, object],
    thresholds: Mapping[str, float],
) -> dict[str, object]:
    """Deterministic PASS/FAIL over the 6 frozen gate criteria (Part B Task 4).

    Pure dict-in/dict-out. Missing scorecard fields fail their criterion closed
    (never raise). ``scorecard`` shape (all supplied by the runner):
      operational:    {separated_ok_frac, peak_rss_gb}
      reconstruction: {tracks_within_frac}
      sidechain:      {anchors_pumped}
      vocal:          {pair_separates: bool, ghost_margin_db}
      wobble:         {moments_detected}
      elements:       {element_name: "PASS"|"PARTIAL"|"FAIL", ...}
    """
    t = dict(DEFAULT_THRESHOLDS)
    t.update(thresholds or {})

    op = scorecard.get("operational", {}) or {}
    recon = scorecard.get("reconstruction", {}) or {}
    sc = scorecard.get("sidechain", {}) or {}
    vocal = scorecard.get("vocal", {}) or {}
    wobble = scorecard.get("wobble", {}) or {}
    elements = scorecard.get("elements", {}) or {}

    n_pass = sum(1 for v in elements.values() if v == "PASS")
    any_full_fail = any(v == "FAIL" for v in elements.values())

    criteria: dict[str, bool] = {
        "operational": (
            float(op.get("separated_ok_frac", 0.0)) >= t["sep_ok_frac"]
            and float(op.get("peak_rss_gb", 1e9)) <= t["peak_rss_gb_max"]
        ),
        "reconstruction": (
            float(recon.get("tracks_within_frac", 0.0)) >= t["recon_within_frac"]
        ),
        "sidechain": (
            int(sc.get("anchors_pumped", 0)) >= int(t["pump_min_anchors"])
        ),
        "vocal": (
            bool(vocal.get("pair_separates", False))
            and float(vocal.get("ghost_margin_db", 0.0)) <= t["ghost_margin_db"]
        ),
        "wobble": (
            int(wobble.get("moments_detected", 0)) >= int(t["wobble_min_moments"])
        ),
        "named_element_floor": (
            n_pass >= int(t["elements_pass_floor"]) and not any_full_fail
        ),
    }

    call_off_reasons = [name for name, ok in criteria.items() if not ok]
    verdict = "PASS" if all(criteria.values()) else "FAIL"
    return {
        "criteria": criteria,
        "elements": dict(elements),
        "elements_pass": n_pass,
        "verdict": verdict,
        "call_off_reasons": call_off_reasons,
    }
