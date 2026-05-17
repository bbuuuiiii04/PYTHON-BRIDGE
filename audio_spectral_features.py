"""Optional audio spectral features for offline smart-drop scoring."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Optional, Sequence

log = logging.getLogger("audio_spectral_features")

SCHEMA_VERSION = 1
_LAZY_IMPORTS: Optional[tuple[Any, Any, Any]] = None


@dataclass(frozen=True)
class SpectralFeatures:
    sr: int
    schema_version: int
    sub_bass_envelope: tuple[float, ...]
    kick_envelope: tuple[float, ...]
    high_band_envelope: tuple[float, ...]


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
    """Extract per-beat envelopes, returning None on missing deps or decode errors."""
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
            high_band_envelope=_band_envelope_per_beat(
                np, mel, freqs, frame_times_ms, beatgrid_times_ms, 4000.0, 12000.0
            ),
        )
    except Exception as exc:
        log.debug("spectral feature extraction failed for %s: %s", audio_filepath, exc)
        return None


def _band_envelope_per_beat(
    np: Any,
    mel: Any,
    freqs: Any,
    frame_times_ms: Any,
    beatgrid_times_ms: Sequence[float],
    low_hz: float,
    high_hz: float,
) -> tuple[float, ...]:
    mask = (freqs >= low_hz) & (freqs < high_hz)
    if not bool(np.any(mask)):
        return tuple(0.0 for _ in beatgrid_times_ms)

    band = np.asarray(mel[mask, :], dtype=float)
    if band.size == 0:
        return tuple(0.0 for _ in beatgrid_times_ms)
    envelope = np.mean(band, axis=0)
    envelope = _normalize_envelope(np, envelope)

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
