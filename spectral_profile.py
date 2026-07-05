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
    # Fast low-mid pulse (experimental — derived by running the shipped rule
    # on 3 operator-labeled wobble tracks + 5 negatives, 2026-07-05 follow-up;
    # wobble basses, dense rolls, chugs, and siren sweeps ALL fire it — it
    # measures fast periodic low-mid movement, not wobble specifically; the
    # operator scrub test is the acceptance gate, design doc Appendix E):
    "lowmid_pulse_min_duty": 0.6,    # sustained-tone gate
    "lowmid_pulse_min_cpb": 2.5,     # dominant modulation, cycles per beat
    "lowmid_pulse_min_conc": 0.10,   # dominant share of rate-grid power
    "lowmid_pulse_min_run": 2.0,     # consecutive flagged beats to count (Girl$ fires in 2-beat bursts)
    "lowmid_pulse_min_level_db": -70.0,  # window p90 must clear this (silence guard)
    # Section map (engineering scale constants, not corpus-calibrated — they
    # normalize feature diffs for a pacing-only chapter view):
    "section_block_beats": 16.0,
    "section_merge_threshold": 0.5,
    "section_scale_db": 6.0,
    "section_scale_frac": 0.25,
    "section_scale_centroid_hz": 800.0,
    "section_scale_flatness": 0.12,
    "section_scale_onsets": 1.5,
    "section_quiet_offset_db": -8.0, # below loudness_ref => quiet tier
    "section_loud_offset_db": -3.0,  # within this of loudness_ref => loud tier
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


def _goertzel_power(x: Sequence[float], cycles_per_window: float) -> float:
    """Power of one DFT component at a (possibly non-integer) bin, pure python."""
    n = len(x)
    if n < 2:
        return 0.0
    import math

    w = 2.0 * math.pi * cycles_per_window / n
    coeff = 2.0 * math.cos(w)
    s1 = 0.0
    s2 = 0.0
    for v in x:
        s0 = v + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return s1 * s1 + s2 * s2 - coeff * s1 * s2


# 24 log-spaced modulation rates, cycles per beat (BPM-independent decision grid).
PULSE_RATE_GRID_CPB: tuple[float, ...] = tuple(
    round(0.5 * (16.0 ** (k / 23.0)), 3) for k in range(24)
)


def lowmid_pulse_measure(
    v4: SpectralFeaturesV4,
    beatgrid_times_ms: Sequence[float],
    beat: int,
) -> tuple[float, float, float]:
    """(duty, dominant cycles/beat, concentration) of the harmonic low-mid
    envelope over a 4-beat window centered on ``beat``.

    Preprocessing matches the validated derivation exactly (design doc App. E):
    linearize the stored dB frames, divide by the window mean and subtract 1
    (DC removal), Hann window, then Goertzel at the cycles/beat rate grid
    converted through the window's actual beat span. Absent/short/silent data
    → (0, 0, 0), never an error.
    """
    import math

    n = v4.n_beats
    grid = beatgrid_times_ms
    if not grid or len(grid) != n or n < 4 or not v4.growl_band_frames:
        return (0.0, 0.0, 0.0)
    beat = max(0, min(int(beat), n - 1))
    lo = max(0, beat - 2)
    hi = min(n - 1, beat + 2)
    if hi - lo < 3:
        return (0.0, 0.0, 0.0)
    start_ms = float(grid[lo])
    end_ms = float(grid[hi])
    if end_ms <= start_ms:
        return (0.0, 0.0, 0.0)
    hop_ms = v4.frame_hop_s * 1000.0
    i0 = max(0, int(start_ms / hop_ms))
    i1 = min(len(v4.growl_band_frames), int(end_ms / hop_ms))
    seg_db = v4.growl_band_frames[i0:i1]
    if len(seg_db) < 32:
        return (0.0, 0.0, 0.0)
    cal = SPECTRAL_V4_CALIBRATION
    if percentile(seg_db, 90.0) < cal["lowmid_pulse_min_level_db"]:
        return (0.0, 0.0, 0.0)
    seg = [10.0 ** (v / 10.0) for v in seg_db]
    mean = sum(seg) / len(seg)
    if mean <= 0.0:
        return (0.0, 0.0, 0.0)
    p90 = percentile(seg, 90.0)
    duty = sum(1 for v in seg if v > 0.1 * p90) / len(seg)
    m = len(seg)
    x = [
        (seg[i] / mean - 1.0) * (0.5 - 0.5 * math.cos(2.0 * math.pi * i / (m - 1)))
        for i in range(m)
    ]
    window_s = (end_ms - start_ms) / 1000.0
    beats_in_window = hi - lo
    nyquist_cycles = 0.45 * m  # stay clearly below the envelope Nyquist
    powers: list[float] = []
    for cpb in PULSE_RATE_GRID_CPB:
        cycles = cpb * beats_in_window  # cycles across the window
        if cycles < 1.5 or cycles > nyquist_cycles:
            powers.append(0.0)
            continue
        powers.append(_goertzel_power(x, cycles))
    total = sum(powers)
    if total <= 0.0:
        return (round(duty, 4), 0.0, 0.0)
    top = max(range(len(powers)), key=lambda i: powers[i])
    _ = window_s  # window span retained for clarity; rates are c/b-native
    return (
        round(duty, 4),
        PULSE_RATE_GRID_CPB[top],
        round(powers[top] / total, 4),
    )


def lowmid_pulse_flags(
    v4: SpectralFeaturesV4, beatgrid_times_ms: Sequence[float]
) -> list[bool]:
    """Per beat: sustained low-mid tone with a fast periodic level movement
    (LFO wobble). Experimental — calibrated on 3 operator-labeled positives +
    5 negatives (design doc Appendix E); persistence removes isolated blips.
    Descriptive only; absent data → all False.
    """
    cal = SPECTRAL_V4_CALIBRATION
    n = v4.n_beats
    raw = [False] * n
    for b in range(n):
        duty, cpb, conc = lowmid_pulse_measure(v4, beatgrid_times_ms, b)
        raw[b] = (
            duty >= cal["lowmid_pulse_min_duty"]
            and cpb >= cal["lowmid_pulse_min_cpb"]
            and conc >= cal["lowmid_pulse_min_conc"]
        )
    min_run = int(cal["lowmid_pulse_min_run"])
    out = [False] * n
    start: Optional[int] = None
    for i, v in enumerate(raw + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_run:
                for j in range(start, i):
                    out[j] = True
            start = None
    return out


def section_map(
    v4: SpectralFeaturesV4,
    drops: Sequence[int] = (),
    buildups: Sequence[int] = (),
    breakdowns: Sequence[int] = (),
) -> list[dict[str, object]]:
    """Chapter map: merged blocks of similar measured character.

    Boundaries describe character change; cue timing stays with ANLZ markers
    and locked designs — section starts are not cue times. Blocks are 16 beats
    anchored at beat 0, with forced boundaries at every supplied marker beat
    (markers are trusted structure; a false "chorus up" marker therefore forces
    a spurious boundary — accepted, see design doc Appendix D item 4: a phantom
    chapter break is a pacing hiccup, and the neighboring sections' near-equal
    character makes it visible to consumers). Merging is a single left-to-right
    pass; a growing section's character is recomputed over its full span before
    each comparison; merging never crosses a drop marker. ``energy_tier`` is
    relative to the track's stored loudness reference and can read top-heavy on
    brickwalled masters (design doc Appendix E).
    """
    cal = SPECTRAL_V4_CALIBRATION
    n = v4.n_beats
    if n == 0:
        return []
    block = max(4, int(cal["section_block_beats"]))
    marker_beats = {int(b) for b in list(drops) + list(buildups) + list(breakdowns) if 0 < int(b) < n}
    drop_beats = {int(b) for b in drops if 0 < int(b) < n}
    bounds = sorted({0, n} | {b for b in range(block, n, block)} | marker_beats)

    gone = bottom_gone_flags(v4)

    def character(a: int, b: int) -> dict[str, float]:
        sl = slice(a, b)
        span = max(1, b - a)
        series = v4.series
        return {
            "full_db": round(sum(series["full_db"][sl]) / span, 1),
            "sub_present": round(sum(1 for g in gone[sl] if not g) / span, 4),
            "perc_full": round(sum(series["perc_full"][sl]) / span, 4),
            "centroid_hz": round(percentile(series["centroid_hz"][sl], 50.0), 1),
            "growl_flatness": round(percentile(series["growl_flatness"][sl], 50.0), 4),
            "onset_mh": round(sum(series["onset_density_midhigh"][sl]) / span, 4),
            "sustain_mid_db": round(percentile(series["sustain_mid_db"][sl], 50.0), 1),
        }

    def distance(c1: dict[str, float], c2: dict[str, float]) -> float:
        d = (
            abs(c1["full_db"] - c2["full_db"]) / cal["section_scale_db"]
            + abs(c1["sub_present"] - c2["sub_present"]) / cal["section_scale_frac"]
            + abs(c1["perc_full"] - c2["perc_full"]) / cal["section_scale_frac"]
            + abs(c1["centroid_hz"] - c2["centroid_hz"]) / cal["section_scale_centroid_hz"]
            + abs(c1["growl_flatness"] - c2["growl_flatness"]) / cal["section_scale_flatness"]
            + abs(c1["onset_mh"] - c2["onset_mh"]) / cal["section_scale_onsets"]
            + abs(c1["sustain_mid_db"] - c2["sustain_mid_db"]) / cal["section_scale_db"]
        )
        return d / 7.0

    sections: list[list[int]] = []  # [start, end) pairs, merged in place
    for a, b in zip(bounds, bounds[1:]):
        if sections:
            prev = sections[-1]
            if a not in drop_beats and distance(
                character(prev[0], prev[1]), character(a, b)
            ) < cal["section_merge_threshold"]:
                prev[1] = b
                continue
        sections.append([a, b])

    ref = float(v4.scalars.get("loudness_ref_db", 0.0))
    out: list[dict[str, object]] = []
    for a, b in sections:
        ch = character(a, b)
        level = ch["full_db"]
        if level < ref + cal["section_quiet_offset_db"]:
            tier = "quiet"
        elif level >= ref + cal["section_loud_offset_db"]:
            tier = "loud"
        else:
            tier = "mid"
        out.append({
            "start_beat": a,
            "end_beat": b - 1,
            "energy_tier": tier,
            "character": ch,
        })
    return out


def drop_window_vector(
    v4: SpectralFeaturesV4,
    drop_beat: int,
    *,
    width: int = 16,
    wobble: Optional[Sequence[bool]] = None,
) -> dict[str, float]:
    """Descriptors of one drop window for the drop-type cue selector.

    ``coverage`` counts the beats actually available — the consumer's neutral
    default (v2 review F-11) keys off thin coverage. Chooses nothing itself.
    Pass precomputed ``wobble`` flags (from :func:`lowmid_pulse_flags`) to include
    a ``pulse_frac`` field; omitted otherwise (the flags cost a full-track scan,
    so callers compute them once).
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
    vec = {
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
    if wobble is not None:
        flags = list(wobble)[start:end]
        vec["pulse_frac"] = round(sum(1 for f in flags if f) / coverage, 4)
    return vec
