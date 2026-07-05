"""Per-beat audio analysis for lighting (schema v4) + legacy v3 envelopes.

v3 (``SpectralFeatures``): five peak-normalized mel-band envelopes retained for
the smart-drop energy-shadow scorer. Its math is frozen verbatim in
``_extract_v3_features`` — the v4 extractor reuses it so the v3-compat block
stays bit-identical (the scorer consumes it unchanged).

v4 (``SpectralFeaturesV4``): absolute-dB per-beat/quarter-beat band series,
HPSS harmonic/percussive measures, onset densities, and timbre descriptors for
LIGHTING ENGINE v2. Design + audit + proofs:
docs/research/spectral_audio_analysis_redesign.md. The analysis describes
sound; it never times or triggers a cue.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import threading
from typing import Any, Mapping, Optional, Sequence

log = logging.getLogger("audio_spectral_features")

SCHEMA_VERSION = 3
SCHEMA_VERSION_V4 = 4
_LAZY_IMPORTS: Optional[tuple[Any, Any, Any]] = None

# ponytail: HPSS working set is a few hundred MB; one extraction at a time per process.
_V4_EXTRACT_LOCK = threading.Lock()

_SR = 22050
_N_FFT = 2048
_HOP = 512
_N_MELS = 128
_DB_FLOOR_POWER = 1e-10

# Single source of truth for every v4 band edge (Hz). Harmonic-component bands
# are role-named (see the design doc §4.3/§4.10).
BAND_RANGES: dict[str, tuple[float, float]] = {
    "sub": (20.0, 60.0),
    "bass": (60.0, 150.0),
    "lowmid": (150.0, 500.0),
    "mid": (500.0, 2000.0),
    "high": (2000.0, 6000.0),
    "air": (6000.0, 11025.0),
    "growl_band": (60.0, 500.0),       # harmonic level, beat + sub4 + frame rate
    "sustain_mid": (200.0, 2000.0),    # harmonic level
    "sustain_high": (2000.0, 8000.0),  # harmonic level
    "growl_flatness": (500.0, 4000.0), # harmonic flatness (distortion axis)
    "macro_low": (20.0, 200.0),        # percussive-ratio bands
    "macro_mid": (200.0, 2000.0),
    "macro_high": (2000.0, 11025.0),
    "attack_low": (20.0, 200.0),
    "onset_midhigh": (500.0, 11025.0),
}
_V4_BANDS = ("sub", "bass", "lowmid", "mid", "high", "air")

# Onset peak-picking on the raw superflux scale (corpus-absolute; never
# normalize per track — see design Appendix C).
_ONSET_PICK = dict(pre_max=1, post_max=1, pre_avg=8, post_avg=8, delta=1.5, wait=1)


@dataclass(frozen=True)
class SpectralFeatures:
    sr: int
    schema_version: int
    sub_bass_envelope: tuple[float, ...]
    kick_envelope: tuple[float, ...]
    low_mid_envelope: tuple[float, ...]
    high_mid_envelope: tuple[float, ...]
    high_band_envelope: tuple[float, ...]
    kick_max_envelope: tuple[float, ...]
    onset_strength_envelope: tuple[float, ...]
    spectral_flatness_envelope: tuple[float, ...]


@dataclass(frozen=True)
class SpectralFeaturesV4:
    """v4 analysis: v3-compat attributes (bit-identical) + absolute measurements.

    ``series``: per-beat tuples (see BAND_RANGES + design doc for semantics).
    ``sub4``: per-beat 4-slot quarter-beat dB tuples.
    ``scalars``: threshold-free per-track summary scalars only.
    ``growl_band_frames``: frame-rate harmonic 60-500 Hz dB envelope
    (future modulation derivations run from cache, never re-extraction).
    """

    sr: int
    schema_version: int
    n_beats: int
    duration_s: float
    frame_hop_s: float
    # v3-compat block (bit-identical to extract_spectral_features)
    sub_bass_envelope: tuple[float, ...]
    kick_envelope: tuple[float, ...]
    low_mid_envelope: tuple[float, ...]
    high_mid_envelope: tuple[float, ...]
    high_band_envelope: tuple[float, ...]
    kick_max_envelope: tuple[float, ...]
    onset_strength_envelope: tuple[float, ...]
    spectral_flatness_envelope: tuple[float, ...]
    # v4 measurements
    series: Mapping[str, tuple[float, ...]]
    sub4: Mapping[str, tuple[tuple[float, ...], ...]]
    growl_band_frames: tuple[float, ...]
    scalars: Mapping[str, float]


V4_SERIES_KEYS = (
    "sub_db", "bass_db", "lowmid_db", "mid_db", "high_db", "air_db",
    "full_db", "growl_band_db", "sustain_mid_db", "sustain_high_db",
    "growl_flatness", "centroid_hz",
    "perc_low", "perc_mid", "perc_high", "perc_full",
    "attack_db", "attack_low_db",
    "onset_density", "onset_density_midhigh", "fluxsum_midhigh",
)
V4_SUB4_KEYS = ("sub", "bass", "lowmid", "mid", "high", "air", "growl_band")
V4_SCALAR_KEYS = (
    "grit", "punch", "drama", "brightness_med", "loudness_ref_db",
    "growl_timbre_p90", "attack_low_p90", "onset_mh_p90",
)


def _lazy_import_librosa() -> Optional[tuple[Any, Any, Any]]:
    """Return (librosa, numpy, soundfile), or None when optional deps are absent."""
    global _LAZY_IMPORTS
    if _LAZY_IMPORTS is not None:
        return _LAZY_IMPORTS
    try:
        import librosa  # type: ignore
        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore
    except ImportError:
        return None
    _LAZY_IMPORTS = (librosa, np, sf)
    return _LAZY_IMPORTS


def extract_spectral_features(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
) -> Optional[SpectralFeatures]:
    """Extract v3 per-beat envelopes, returning None on missing deps or decode errors."""
    deps = _lazy_import_librosa()
    if deps is None:
        return None
    librosa, np, _sf = deps

    path = Path(audio_filepath)
    if not path.exists() or len(beatgrid_times_ms) < 2:
        return None

    try:
        y, sr = librosa.load(str(path), sr=22050, mono=True)
        if y is None or len(y) == 0:
            return None
        return _extract_v3_features(librosa, np, y, sr, beatgrid_times_ms)
    except Exception as exc:
        log.debug("spectral feature extraction failed for %s: %s", audio_filepath, exc)
        return None


def _extract_v3_features(
    librosa: Any,
    np: Any,
    y: Any,
    sr: int,
    beatgrid_times_ms: Sequence[float],
) -> Optional[SpectralFeatures]:
    """v3 math, verbatim — DO NOT change or 'optimize' onto a shared STFT.

    The v4 compat block must stay bit-identical to the historical v3 extractor:
    the explicit fmax=12000.0 mel (top filters empty above Nyquist), the
    separate onset_strength / spectral_flatness calls with their own internal
    STFTs, and the double normalization in the band path are all deliberate
    freezes (design doc §4.10 change 1).
    """
    n_mels = 128
    fmin = 20.0
    fmax = 12000.0
    hop_length = 512
    mel = librosa.feature.melspectrogram(
        y=y,
        sr=sr,
        n_fft=2048,
        hop_length=hop_length,
        n_mels=n_mels,
        fmin=fmin,
        fmax=fmax,
        power=2.0,
    )
    freqs = librosa.mel_frequencies(n_mels=n_mels, fmin=fmin, fmax=fmax)
    frame_times_ms = (
        librosa.frames_to_time(np.arange(mel.shape[1]), sr=sr, hop_length=hop_length)
        * 1000.0
    )

    return SpectralFeatures(
        sr=int(sr),
        schema_version=SCHEMA_VERSION,
        sub_bass_envelope=_band_envelope_per_beat(
            np, mel, freqs, frame_times_ms, beatgrid_times_ms, 20.0, 100.0
        ),
        kick_envelope=_band_envelope_per_beat(
            np, mel, freqs, frame_times_ms, beatgrid_times_ms, 60.0, 200.0
        ),
        low_mid_envelope=_band_envelope_per_beat(
            np, mel, freqs, frame_times_ms, beatgrid_times_ms, 200.0, 800.0
        ),
        high_mid_envelope=_band_envelope_per_beat(
            np, mel, freqs, frame_times_ms, beatgrid_times_ms, 800.0, 4000.0
        ),
        high_band_envelope=_band_envelope_per_beat(
            np, mel, freqs, frame_times_ms, beatgrid_times_ms, 4000.0, 12000.0
        ),
        kick_max_envelope=_band_envelope_per_beat(
            np,
            mel,
            freqs,
            frame_times_ms,
            beatgrid_times_ms,
            60.0,
            200.0,
            reducer="max",
        ),
        onset_strength_envelope=_frame_envelope_per_beat(
            np,
            librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length),
            frame_times_ms,
            beatgrid_times_ms,
        ),
        spectral_flatness_envelope=_frame_envelope_per_beat(
            np,
            librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0],
            frame_times_ms,
            beatgrid_times_ms,
            normalize=False,
        ),
    )


def extract_spectral_features_v4(
    audio_filepath: str,
    beatgrid_times_ms: Sequence[float],
) -> Optional[SpectralFeaturesV4]:
    """Extract the v4 analysis (compat block + absolute measurements).

    One extraction at a time per process (HPSS working set); returns None on
    missing deps, decode errors, or <2 beats — absent data reads as no signal.
    """
    deps = _lazy_import_librosa()
    if deps is None:
        return None
    librosa, np, _sf = deps

    path = Path(audio_filepath)
    if not path.exists() or len(beatgrid_times_ms) < 2:
        return None

    try:
        with _V4_EXTRACT_LOCK:
            y, sr = librosa.load(str(path), sr=22050, mono=True)
            if y is None or len(y) == 0:
                return None
            compat = _extract_v3_features(librosa, np, y, sr, beatgrid_times_ms)
            if compat is None:
                return None
            return _extract_v4_measurements(librosa, np, y, sr, beatgrid_times_ms, compat)
    except Exception as exc:
        log.debug("v4 spectral extraction failed for %s: %s", audio_filepath, exc)
        return None


def _extract_v4_measurements(
    librosa: Any,
    np: Any,
    y: Any,
    sr: int,
    beatgrid_times_ms: Sequence[float],
    compat: SpectralFeatures,
) -> SpectralFeaturesV4:
    """All v4 measurements from one STFT pass (compat block excepted by design)."""
    S = np.abs(librosa.stft(y, n_fft=_N_FFT, hop_length=_HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=_N_FFT)
    mel_fb = librosa.filters.mel(
        sr=sr, n_fft=_N_FFT, n_mels=_N_MELS, fmin=20.0, fmax=11025.0
    )
    mel_freqs = librosa.mel_frequencies(n_mels=_N_MELS, fmin=20.0, fmax=11025.0)
    mel = mel_fb @ S
    n_frames = int(S.shape[1])
    frame_times_ms = (
        librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=_HOP) * 1000.0
    )
    H, P = librosa.decompose.hpss(S)
    mel_P = mel_fb @ P

    spans = _beat_spans(beatgrid_times_ms)
    n_beats = len(spans)

    def r1(v: Any) -> float:
        return round(float(v), 1)

    def r4(v: Any) -> float:
        return round(float(v), 4)

    def db(power: Any) -> Any:
        return 10.0 * np.log10(np.maximum(power, _DB_FLOOR_POWER))

    def mel_band_power(lo: float, hi: float) -> Any:
        mask = (mel_freqs >= lo) & (mel_freqs < hi)
        return mel[mask, :].mean(axis=0)

    def lin_band_power(source: Any, lo: float, hi: float) -> Any:
        mask = (freqs >= lo) & (freqs < hi)
        return source[mask, :].mean(axis=0)

    def per_beat_db(power_frames: Any) -> tuple[float, ...]:
        # arithmetic mean of linear power per beat, then dB (energy semantics)
        return tuple(
            r1(db(_window_mean(np, power_frames, frame_times_ms, s, e)))
            for s, e in spans
        )

    def per_beat_sub4_db(power_frames: Any) -> tuple[tuple[float, ...], ...]:
        out = []
        for s, e in spans:
            q = (e - s) / 4.0
            out.append(tuple(
                r1(db(_window_mean(np, power_frames, frame_times_ms, s + k * q, s + (k + 1) * q)))
                for k in range(4)
            ))
        return tuple(out)

    def per_beat_mean(value_frames: Any, digits: int = 4) -> tuple[float, ...]:
        return tuple(
            round(float(_window_mean(np, value_frames, frame_times_ms, s, e)), digits)
            for s, e in spans
        )

    series: dict[str, tuple[float, ...]] = {}
    sub4: dict[str, tuple[tuple[float, ...], ...]] = {}

    band_power = {name: mel_band_power(*BAND_RANGES[name]) for name in _V4_BANDS}
    for name in _V4_BANDS:
        series[f"{name}_db"] = per_beat_db(band_power[name])
        sub4[name] = per_beat_sub4_db(band_power[name])
    full_power = mel.mean(axis=0)
    series["full_db"] = per_beat_db(full_power)

    growl_power = lin_band_power(H, *BAND_RANGES["growl_band"])
    series["growl_band_db"] = per_beat_db(growl_power)
    sub4["growl_band"] = per_beat_sub4_db(growl_power)
    growl_band_frames = tuple(r1(v) for v in db(growl_power))
    series["sustain_mid_db"] = per_beat_db(lin_band_power(H, *BAND_RANGES["sustain_mid"]))
    series["sustain_high_db"] = per_beat_db(lin_band_power(H, *BAND_RANGES["sustain_high"]))

    gf_mask = (freqs >= BAND_RANGES["growl_flatness"][0]) & (freqs < BAND_RANGES["growl_flatness"][1])
    Hg = np.maximum(H[gf_mask, :], _DB_FLOOR_POWER)
    growl_flat_frames = np.exp(np.mean(np.log(Hg), axis=0)) / (np.mean(Hg, axis=0))
    series["growl_flatness"] = per_beat_mean(growl_flat_frames, 4)

    centroid_frames = (freqs @ S) / np.maximum(S.sum(axis=0), _DB_FLOOR_POWER)
    series["centroid_hz"] = tuple(
        round(float(_window_mean(np, centroid_frames, frame_times_ms, s, e)), 1)
        for s, e in spans
    )

    for macro, key in (("macro_low", "perc_low"), ("macro_mid", "perc_mid"), ("macro_high", "perc_high")):
        lo, hi = BAND_RANGES[macro]
        mask = (freqs >= lo) & (freqs < hi)
        p_e = P[mask, :].sum(axis=0)
        h_e = H[mask, :].sum(axis=0)
        series[key] = per_beat_mean(p_e / (p_e + h_e + _DB_FLOOR_POWER), 4)
    p_full = P.sum(axis=0)
    h_full = H.sum(axis=0)
    series["perc_full"] = per_beat_mean(p_full / (p_full + h_full + _DB_FLOOR_POWER), 4)

    full_db_frames = db(full_power)
    d_full = np.diff(full_db_frames, prepend=full_db_frames[:1])
    series["attack_db"] = tuple(
        r1(_window_max(np, np.maximum(d_full, 0.0), frame_times_ms, s, e)) for s, e in spans
    )
    low_db_frames = db(lin_band_power(S, *BAND_RANGES["attack_low"]))
    d_low = np.diff(low_db_frames, prepend=low_db_frames[:1])
    series["attack_low_db"] = tuple(
        r1(_window_max(np, np.maximum(d_low, 0.0), frame_times_ms, s, e)) for s, e in spans
    )

    onset_full_env = librosa.onset.onset_strength(
        S=librosa.power_to_db(mel_P), sr=sr, hop_length=_HOP, max_size=3
    )
    mh_mask = mel_freqs >= BAND_RANGES["onset_midhigh"][0]
    onset_mh_env = librosa.onset.onset_strength(
        S=librosa.power_to_db(mel_P[mh_mask, :]), sr=sr, hop_length=_HOP, max_size=3
    )
    series["onset_density"] = _onset_counts(librosa, np, onset_full_env, frame_times_ms, spans, sr)
    series["onset_density_midhigh"] = _onset_counts(librosa, np, onset_mh_env, frame_times_ms, spans, sr)
    series["fluxsum_midhigh"] = tuple(
        r1(_window_sum(np, onset_mh_env, frame_times_ms, s, e)) for s, e in spans
    )

    flat_env = list(compat.spectral_flatness_envelope)
    kick_env = np.asarray(compat.kick_envelope, dtype=float)
    kick_mean = float(kick_env.mean()) if kick_env.size else 0.0
    full_db_beats = np.asarray(series["full_db"], dtype=float)
    scalars: dict[str, float] = {
        "grit": r4(np.median(np.asarray(flat_env, dtype=float))) if flat_env else 0.0,
        "punch": r4(float(kick_env.std()) / kick_mean) if kick_mean > 0.0 else 0.0,
        "drama": r1(np.percentile(full_db_beats, 95) - np.percentile(full_db_beats, 5)),
        "brightness_med": r1(np.median(np.asarray(series["centroid_hz"], dtype=float))),
        "loudness_ref_db": r1(np.percentile(full_db_beats, 95)),
        "growl_timbre_p90": r4(np.percentile(np.asarray(series["growl_flatness"], dtype=float), 90)),
        "attack_low_p90": r1(np.percentile(np.asarray(series["attack_low_db"], dtype=float), 90)),
        "onset_mh_p90": r1(np.percentile(np.asarray(series["onset_density_midhigh"], dtype=float), 90)),
    }

    return SpectralFeaturesV4(
        sr=int(sr),
        schema_version=SCHEMA_VERSION_V4,
        n_beats=n_beats,
        duration_s=r1(len(y) / float(sr)),
        frame_hop_s=r4(_HOP / float(sr)),
        sub_bass_envelope=compat.sub_bass_envelope,
        kick_envelope=compat.kick_envelope,
        low_mid_envelope=compat.low_mid_envelope,
        high_mid_envelope=compat.high_mid_envelope,
        high_band_envelope=compat.high_band_envelope,
        kick_max_envelope=compat.kick_max_envelope,
        onset_strength_envelope=compat.onset_strength_envelope,
        spectral_flatness_envelope=compat.spectral_flatness_envelope,
        series=series,
        sub4=sub4,
        growl_band_frames=growl_band_frames,
        scalars=scalars,
    )


def _beat_spans(beatgrid_times_ms: Sequence[float]) -> list[tuple[float, float]]:
    beats = [float(v) for v in beatgrid_times_ms]
    n = len(beats)
    if n >= 2:
        last_interval = beats[-1] - beats[-2]
    else:
        last_interval = 0.0
    if last_interval <= 0:
        last_interval = 500.0
    spans = []
    for i in range(n):
        start = beats[i]
        end = beats[i + 1] if i + 1 < n else start + last_interval
        spans.append((start, end))
    return spans


def _window_mean(np: Any, values: Any, frame_times_ms: Any, start_ms: float, end_ms: float) -> float:
    mask = (frame_times_ms >= start_ms) & (frame_times_ms < end_ms)
    if bool(np.any(mask)):
        return float(np.mean(values[mask]))
    nearest = int(np.argmin(np.abs(frame_times_ms - start_ms)))
    return float(values[nearest])


def _window_max(np: Any, values: Any, frame_times_ms: Any, start_ms: float, end_ms: float) -> float:
    mask = (frame_times_ms >= start_ms) & (frame_times_ms < end_ms)
    if bool(np.any(mask)):
        return float(np.max(values[mask]))
    nearest = int(np.argmin(np.abs(frame_times_ms - start_ms)))
    return float(values[nearest])


def _window_sum(np: Any, values: Any, frame_times_ms: Any, start_ms: float, end_ms: float) -> float:
    mask = (frame_times_ms >= start_ms) & (frame_times_ms < end_ms)
    if bool(np.any(mask)):
        return float(np.sum(values[mask]))
    return 0.0


def _onset_counts(
    librosa: Any,
    np: Any,
    onset_env: Any,
    frame_times_ms: Any,
    spans: list[tuple[float, float]],
    sr: int,
) -> tuple[float, ...]:
    peaks = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=_HOP,
        units="frames",
        normalize=False,
        **_ONSET_PICK,
    )
    peaks = np.asarray(peaks, dtype=int)
    if peaks.size:
        times = frame_times_ms[peaks]
    else:
        times = np.asarray([], dtype=float)
    counts = []
    for s, e in spans:
        counts.append(float(((times >= s) & (times < e)).sum()))
    return tuple(counts)


def _band_envelope_per_beat(
    np: Any,
    mel: Any,
    freqs: Any,
    frame_times_ms: Any,
    beatgrid_times_ms: Sequence[float],
    low_hz: float,
    high_hz: float,
    *,
    reducer: str = "mean",
) -> tuple[float, ...]:
    mask = (freqs >= low_hz) & (freqs < high_hz)
    if not bool(np.any(mask)):
        return tuple(0.0 for _ in beatgrid_times_ms)

    band = np.asarray(mel[mask, :], dtype=float)
    if band.size == 0:
        return tuple(0.0 for _ in beatgrid_times_ms)
    envelope = np.max(band, axis=0) if reducer == "max" else np.mean(band, axis=0)
    envelope = _normalize_envelope(np, envelope)
    return _frame_envelope_per_beat(np, envelope, frame_times_ms, beatgrid_times_ms)


def _frame_envelope_per_beat(
    np: Any,
    envelope: Any,
    frame_times_ms: Any,
    beatgrid_times_ms: Sequence[float],
    *,
    normalize: bool = True,
) -> tuple[float, ...]:
    envelope = np.asarray(envelope, dtype=float)
    if normalize:
        envelope = _normalize_envelope(np, envelope)
    if envelope.size == 0:
        return tuple(0.0 for _ in beatgrid_times_ms)
    frame_times_ms = np.asarray(frame_times_ms, dtype=float)
    if frame_times_ms.size == 0:
        return tuple(0.0 for _ in beatgrid_times_ms)
    if frame_times_ms.size != envelope.size:
        size = min(int(frame_times_ms.size), int(envelope.size))
        frame_times_ms = frame_times_ms[:size]
        envelope = envelope[:size]

    beat_times = [float(value) for value in beatgrid_times_ms]
    if len(beat_times) >= 2:
        last_interval = beat_times[-1] - beat_times[-2]
    else:
        last_interval = 0.0
    if last_interval <= 0:
        last_interval = 500.0

    values: list[float] = []
    for index, start_ms in enumerate(beat_times):
        if index + 1 < len(beat_times):
            end_ms = beat_times[index + 1]
        else:
            end_ms = start_ms + last_interval
        frame_mask = (frame_times_ms >= start_ms) & (frame_times_ms < end_ms)
        if bool(np.any(frame_mask)):
            values.append(float(np.mean(envelope[frame_mask])))
        else:
            nearest = int(np.argmin(np.abs(frame_times_ms - start_ms)))
            values.append(float(envelope[nearest]))
    return tuple(values)


def _normalize_envelope(np: Any, envelope: Any) -> Any:
    peak = float(np.max(envelope)) if envelope.size else 0.0
    if peak <= 0.0:
        return envelope
    return envelope / peak
