"""Pure derived views over cached v4 spectral analysis (no numpy/librosa).

Everything here is a cheap pure function over ``SpectralFeaturesV4`` — classes
and thresholds are re-tunable without re-extraction (the cache stores raw
measurements only). The analysis DESCRIBES sound; nothing here is a timing or
trigger signal: structural moments stay with ANLZ markers and locked designs.
Absent data reads as "no signal", never as a false event.

Design + calibration provenance: docs/research/spectral_audio_analysis_redesign.md.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .audio_spectral_features import SCHEMA_VERSION, SpectralFeatures, SpectralFeaturesV4

# Corpus-absolute thresholds, calibrated on the BY GENRE playlists (2026-07-05,
# 36-track design set; re-verified at corpus scale after the library sweep —
# see the design doc §7). Consumers may re-tune per feature spec; values here
# are the analysis-layer defaults.
SPECTRAL_V4_CALIBRATION: dict[str, float] = {
    "bottom_gone_sub_db": 5.0,       # sub band below this AND
    "bottom_gone_bass_db": 8.0,      # ...bass band below this => bottom gone
    "true_silence_full_db": -30.0,   # full band below this => literal silence
    "roll_density": 3.0,             # mid/high onsets per beat
    "stab_attack_low_db": 12.0,      # low-band within-beat dB rise
    "sustain_swing_db": 4.5,         # bass sub4 swing below this => sustained
    "sustain_min_bass_db": 12.0,     # ...with real bass present
    "growl_min_flatness": 0.25,      # harmonic 500-4000 flatness (distortion)
    "growl_min_db": 10.0,            # ...with growl-band harmonic energy
    "synth_min_mid_db": 12.0,        # sustained harmonic mids present
    "synth_max_flatness": 0.12,      # ...clean/tonal timbre
    "kick_prominent_attack_db": 6.0, # low-band attack marks a kick-led beat
    "bright_tilt_centroid_hz": 1500.0,
    "thick_min_bands": 4.0,          # bands above their floor => thick texture
    "thick_band_floor_db": 0.0,
}


def compat_features(v4: SpectralFeaturesV4) -> SpectralFeatures:
    """The bit-identical v3 view (feeds the smart-drop scorer unchanged)."""
    return SpectralFeatures(
        sr=v4.sr,
        schema_version=SCHEMA_VERSION,
        sub_bass_envelope=v4.sub_bass_envelope,
        kick_envelope=v4.kick_envelope,
        low_mid_envelope=v4.low_mid_envelope,
        high_mid_envelope=v4.high_mid_envelope,
        high_band_envelope=v4.high_band_envelope,
        kick_max_envelope=v4.kick_max_envelope,
        onset_strength_envelope=v4.onset_strength_envelope,
        spectral_flatness_envelope=v4.spectral_flatness_envelope,
    )


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile (numpy 'linear' method), pure python."""
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def bass_duty(v4: SpectralFeaturesV4, *, threshold_db: Optional[float] = None) -> float:
    """Fraction of beats with real sub weight (the 'bass' identity axis).

    Derived at load, never stored — re-tuning the threshold can never
    desynchronize cache entries (design §4.10 change 4).
    """
    th = SPECTRAL_V4_CALIBRATION["bottom_gone_sub_db"] if threshold_db is None else threshold_db
    sub = v4.series["sub_db"]
    if not sub:
        return 0.0
    return sum(1 for v in sub if v > th) / len(sub)


def sub_weight_med(v4: SpectralFeaturesV4) -> float:
    """Median sub level over beats where the bottom is present."""
    th = SPECTRAL_V4_CALIBRATION["bottom_gone_sub_db"]
    present = [v for v in v4.series["sub_db"] if v > th]
    return percentile(present, 50.0) if present else -100.0


def identity_axes(v4: SpectralFeaturesV4) -> dict[str, float]:
    """The four Feature-1 character axes: grit / punch / bass / drama."""
    return {
        "grit": float(v4.scalars["grit"]),
        "punch": float(v4.scalars["punch"]),
        "bass": round(bass_duty(v4), 4),
        "drama": float(v4.scalars["drama"]),
    }


def bottom_gone_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: kick+sub floor is absent (the shared silence primitive input)."""
    cal = SPECTRAL_V4_CALIBRATION
    sub = v4.series["sub_db"]
    bass = v4.series["bass_db"]
    return [
        s < cal["bottom_gone_sub_db"] and b < cal["bottom_gone_bass_db"]
        for s, b in zip(sub, bass)
    ]


def empty_floor_runs(
    v4: SpectralFeaturesV4, *, min_len: int = 2
) -> list[tuple[int, int, str]]:
    """Merged runs of floor absence: (start_beat, end_beat, kind).

    kind is "true_silence" (full band gone — literal silence) or "empty_floor"
    (bottom gone, other instruments still playing). One primitive, three
    consumers (texture darkness, blackout sizing, landing eligibility) —
    review P-2/F-16.
    """
    cal = SPECTRAL_V4_CALIBRATION
    gone = bottom_gone_flags(v4)
    silent = [v < cal["true_silence_full_db"] for v in v4.series["full_db"]]
    # per-beat kind; runs split where the kind changes (a breakdown fading to
    # literal silence is two different things to a blackout consumer)
    kinds = [
        ("true_silence" if s else "empty_floor") if g else None
        for g, s in zip(gone, silent)
    ]
    runs: list[tuple[int, int, str]] = []
    start: Optional[int] = None
    current: Optional[str] = None
    for i, kind in enumerate(kinds):
        if kind != current:
            if current is not None and start is not None and i - start >= min_len:
                runs.append((start, i - 1, current))
            start = i if kind is not None else None
            current = kind
    if current is not None and start is not None and len(kinds) - start >= min_len:
        runs.append((start, len(kinds) - 1, current))
    return runs


def pre_drop_gap_beats(v4: SpectralFeaturesV4, drop_beat: int, *, max_scan: int = 32) -> int:
    """Length of the bottom-gone run immediately before a drop beat.

    Sizes the audio-matched pre-drop blackout (consumer caps it, e.g. ~4 bars).
    0 means the music runs straight in (consumer plays its snap flick).
    Purely descriptive: the drop beat itself always comes from ANLZ markers.
    """
    gone = bottom_gone_flags(v4)
    if drop_beat <= 0 or drop_beat > len(gone):
        return 0
    gap = 0
    for i in range(drop_beat - 1, max(-1, drop_beat - 1 - max_scan), -1):
        if i < len(gone) and gone[i]:
            gap += 1
        else:
            break
    return gap


def roll_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: mid/high percussion roll density reached (snare rolls)."""
    th = SPECTRAL_V4_CALIBRATION["roll_density"]
    return [d >= th for d in v4.series["onset_density_midhigh"]]


def roll_acceleration(v4: SpectralFeaturesV4, beat: int, *, window: int = 8) -> float:
    """Trailing rise of roll flux at ``beat`` (positive = accelerating build)."""
    flux = v4.series["fluxsum_midhigh"]
    if not flux:
        return 0.0
    beat = max(0, min(beat, len(flux) - 1))
    recent = flux[max(0, beat - window // 2) : beat + 1]
    earlier = flux[max(0, beat - window) : max(1, beat - window // 2)]
    if not recent or not earlier:
        return 0.0
    return round(
        (sum(recent) / len(recent)) - (sum(earlier) / len(earlier)), 1
    )


def stab_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: hard low-end hit (stabby/punchy attack with the floor present)."""
    cal = SPECTRAL_V4_CALIBRATION
    gone = bottom_gone_flags(v4)
    return [
        a > cal["stab_attack_low_db"] and not g
        for a, g in zip(v4.series["attack_low_db"], gone)
    ]


def sustained_bass_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: bass floor held flat through the beat (horn/rolling sub, not hits)."""
    cal = SPECTRAL_V4_CALIBRATION
    out = []
    for slots, bass in zip(v4.sub4["bass"], v4.series["bass_db"]):
        swing = max(slots) - min(slots)
        out.append(swing < cal["sustain_swing_db"] and bass > cal["sustain_min_bass_db"])
    return out


def growl_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: distorted harmonic texture (growl/scream timbre)."""
    cal = SPECTRAL_V4_CALIBRATION
    return [
        f > cal["growl_min_flatness"] and g > cal["growl_min_db"]
        for f, g in zip(v4.series["growl_flatness"], v4.series["growl_band_db"])
    ]


def sustained_synth_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: clean sustained harmonic mids (synth pad/chord presence).

    Describes sound, not emotion — whether a sustained synth in a pounding
    160 BPM track reads "euphoric" is the consumer's call on the full vector.
    """
    cal = SPECTRAL_V4_CALIBRATION
    return [
        m > cal["synth_min_mid_db"] and f < cal["synth_max_flatness"]
        for m, f in zip(v4.series["sustain_mid_db"], v4.series["growl_flatness"])
    ]


def kick_prominence_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: percussion-led low end (texture Tier 1 kick-prominence)."""
    cal = SPECTRAL_V4_CALIBRATION
    gone = bottom_gone_flags(v4)
    return [
        a > cal["kick_prominent_attack_db"] and not g
        for a, g in zip(v4.series["attack_low_db"], gone)
    ]


def bright_tilt_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: spectrum tilted bright (texture Tier 1 bright/dark tilt)."""
    th = SPECTRAL_V4_CALIBRATION["bright_tilt_centroid_hz"]
    return [c > th for c in v4.series["centroid_hz"]]


def thick_flags(v4: SpectralFeaturesV4) -> list[bool]:
    """Per beat: many bands active at once (texture Tier 1 thick/thin)."""
    cal = SPECTRAL_V4_CALIBRATION
    floor = cal["thick_band_floor_db"]
    need = cal["thick_min_bands"]
    bands = [v4.series[k] for k in ("sub_db", "bass_db", "lowmid_db", "mid_db", "high_db", "air_db")]
    out = []
    for i in range(v4.n_beats):
        active = sum(1 for series in bands if series[i] > floor)
        out.append(active >= need)
    return out


def drop_window_vector(
    v4: SpectralFeaturesV4, drop_beat: int, *, width: int = 16
) -> dict[str, float]:
    """Descriptors of one drop window for the drop-type cue selector.

    ``coverage`` counts the beats actually available — the consumer's neutral
    default (v2 review F-11) keys off thin coverage. Chooses nothing itself.
    """
    n = v4.n_beats
    start = max(0, int(drop_beat))
    end = min(n, start + width)
    coverage = max(0, end - start)
    if coverage == 0:
        return {"coverage": 0.0}
    w = slice(start, end)
    w8 = slice(start, min(n, start + 8))

    def mean(key: str, sl: slice) -> float:
        vals = v4.series[key][sl]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    swing = [max(s) - min(s) for s in v4.sub4["bass"][w]]
    beat_s = (v4.duration_s / n) if n else 0.5
    return {
        "coverage": float(coverage),
        "sub_db": mean("sub_db", w),
        "bass_db": mean("bass_db", w),
        "mid_db": mean("mid_db", w),
        "high_db": mean("high_db", w),
        "air_db": mean("air_db", w),
        "full_db": mean("full_db", w),
        "low_swing_db": round(sum(swing) / len(swing), 1) if swing else 0.0,
        "attack_low_p90": round(percentile(v4.series["attack_low_db"][w], 90.0), 1),
        "perc_low": mean("perc_low", w),
        "harm_ratio": round(1.0 - mean("perc_full", w), 4),
        "centroid_hz": mean("centroid_hz", w),
        "growl_flatness": round(percentile(v4.series["growl_flatness"][w], 50.0), 4),
        "sustain_mid_db_d8": round(percentile(v4.series["sustain_mid_db"][w8], 50.0), 1),
        "sustain_high_db_d8": round(percentile(v4.series["sustain_high_db"][w8], 50.0), 1),
        "onset_density_mh": mean("onset_density_midhigh", w),
        "fluxsum_mh": mean("fluxsum_midhigh", w),
        "pre_gap_beats": float(pre_drop_gap_beats(v4, start)),
        "bpm": round(60.0 / beat_s, 1) if beat_s > 0 else 0.0,
    }
