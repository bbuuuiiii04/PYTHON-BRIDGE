"""Offline intrinsic-hardness shadow descriptor — SOL3 candidate, Increment A.

**NON-AUTHORITATIVE / OFFLINE ONLY.** This is a *frozen in-sample benchmark
candidate*, not a validated boundary. It has **zero runtime importers** (only
``tools/`` and ``tests/`` may import it — see the invariant test) and it never
times or triggers a cue. ``violence`` / ``.tier`` remain the sole live authority;
this module does not route anything live and does not replace them.

Honest naming: ``H >= 1.0`` is *just path-threshold firing* — it means "at least
one of the three transparent paths cleared every one of its own thresholds." It
is NOT an independently validated hardness boundary. The candidate is in-sample
(anchors + thresholds hand-iterated against the same named pins it passes) and
**binary T3 only** — there is no T1/T2 boundary here and none may be invented
from this formula. Absent / malformed / empty data returns ``None`` (no result),
never a phantom T3.

Formula (per candidate marker alignment, over a first-8 and a following-8 landed
view, each term averaged across the two halves):

    B = clip01((Q25(full_db)          - 13.7) / 3.8)    # persistent body / wall
    A = clip01((Q25(high_db)          + 5.5)  / 10.4)   # sustained high-band abrasion
    R = mean_beats clip01((growl_band_db - 20)/12)
                 * clip01((growl_flatness - 0.10)/0.20) # distorted-growl duty
    N = clip01((mean(onset_density_midhigh) - 1.7)/1.3) # landed mid-high onset density

Alignment picks one center offset in marker-2 .. marker+2 (reducer-controlled;
the Rekordbox marker stays the cue, only the descriptor window moves). Per-term
track baseline ``T*`` is the median of the aligned-local terms across the track's
genuine drops. Three paths, then ``H = max(paths)``:

    repeated_wall   = min(T_B/0.92, T_A/0.80)                       # per-track only
    abrasive_hammer = min(T_B/0.70, L_B/0.75, L_A/0.60)
    growling_hammer = min(T_N/0.65, L_B/0.80, L_R/0.40, L_N/0.70)

Design + adversarial review: docs/research/spectral_audio_analysis_redesign.md
and /tmp/rbss_lane_signals/sol46spectral_hardness_plan.HARDNESS_PLAN.report.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

# Same numpy-'linear' (type-7) percentile the corpus anchors were measured with.
# Importing spectral_profile keeps Q25 bit-identical to the anchor calibration;
# spectral_profile is a pure module (librosa/numpy stay lazy in the extractor).
# This import is one-directional — nothing imports hardness_v0 back into runtime.
from .spectral_profile import percentile

# --- frozen constants: the AWR-147-class freeze surface (move ONLY with new
# benchmark evidence; the reducer, the 8+8 window sizes, and the Q25 choice are
# part of the freeze too) --------------------------------------------------------
# (B_lo, B_span, A_lo, A_span, R_db_lo, R_db_span, R_flat_lo, R_flat_span, N_lo, N_span)
ANCHORS: Tuple[float, ...] = (13.7, 3.8, -5.5, 10.4, 20.0, 12.0, 0.10, 0.20, 1.7, 1.3)
# repeated_wall(T_B, T_A) | abrasive(T_B, L_B, L_A) | growling(T_N, L_B, L_R, L_N)
PATH_THRESHOLDS: Tuple[float, ...] = (0.92, 0.80, 0.70, 0.75, 0.60, 0.65, 0.80, 0.40, 0.70)
ALIGN_WEIGHTS: Tuple[float, ...] = (0.40, 0.25, 0.20, 0.15)  # B, A, R, N — picks the offset only
ALIGN_RADIUS: int = 2          # descriptor search window: marker +/- 2 beats
HALF_BEATS: int = 8            # first-8 and following-8 landed views
T3_GATE: float = 1.0           # H >= T3_GATE == "a path fired" (NOT a validated boundary)
MIN_STABLE_DROPS: int = 5      # below this, the per-track median T* is flagged unstable

REDUCERS: Tuple[str, ...] = ("center", "median", "q75", "max")
PATHS: Tuple[str, ...] = ("repeated_wall", "abrasive_hammer", "growling_hammer")
_REQUIRED_SERIES: Tuple[str, ...] = (
    "full_db", "high_db", "growl_band_db", "growl_flatness", "onset_density_midhigh",
)


@dataclass(frozen=True)
class TrackBaseline:
    """Per-term median of the aligned-local terms over a track's genuine drops."""

    t_body: float
    t_abrasion: float
    t_growl: float
    t_onset: float
    n_drops: int
    stable: bool          # n_drops >= MIN_STABLE_DROPS
    reducer: str

    @property
    def terms(self) -> Tuple[float, float, float, float]:
        return (self.t_body, self.t_abrasion, self.t_growl, self.t_onset)


@dataclass(frozen=True)
class HardnessResult:
    h: float
    t3: bool                                       # h >= T3_GATE (path-threshold firing only)
    winning_path: str                              # PATHS entry with the max path value
    repeated_wall: float
    abrasive_hammer: float
    growling_hammer: float
    winning_offset: int                            # selected alignment center, beats vs marker
    marker_shift_range: Tuple[float, float]        # (min H, max H) over marker-2..marker+2
    local_terms: Tuple[float, float, float, float]  # L_B, L_A, L_R, L_N at the selected offset
    track_terms: Tuple[float, float, float, float]  # T_B, T_A, T_R, T_N
    n_drops: int
    t_star_stable: bool                            # n_drops >= MIN_STABLE_DROPS
    reducer: str


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


# --- pure term functions (each clip01, so each is already in [0, 1]) -----------
def _body_term(full_db_slice: Sequence[float]) -> float:
    return _clip01((percentile(full_db_slice, 25.0) - ANCHORS[0]) / ANCHORS[1])


def _abrasion_term(high_db_slice: Sequence[float]) -> float:
    return _clip01((percentile(high_db_slice, 25.0) - ANCHORS[2]) / ANCHORS[3])


def _growl_duty_term(
    growl_db_slice: Sequence[float], growl_flat_slice: Sequence[float]
) -> float:
    n = len(growl_db_slice)
    if n == 0:
        return 0.0
    total = 0.0
    for db, flat in zip(growl_db_slice, growl_flat_slice):
        total += (
            _clip01((db - ANCHORS[4]) / ANCHORS[5])
            * _clip01((flat - ANCHORS[6]) / ANCHORS[7])
        )
    return total / n


def _onset_term(onset_slice: Sequence[float]) -> float:
    n = len(onset_slice)
    if n == 0:
        return 0.0
    return _clip01(((sum(onset_slice) / n) - ANCHORS[8]) / ANCHORS[9])


def _isfinite(v: Any) -> bool:
    """True only for a real, finite number. NaN, +/-inf, and non-numeric or
    non-coercible values all read False -- hardness feeds raw slices straight into
    ``percentile``/``sum`` with no hole filter, so any of these would poison H."""
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _valid_v4(v4: Any) -> bool:
    """A v4 usable for hardness: positive n_beats and every required series a
    full-length sequence of finite numbers.

    Rejects (so the caller returns ``None``, never a phantom T3): a missing / None
    / wrong-length series, a non-sequence (scalar / no ``__len__``) series value,
    and any series carrying a non-finite (NaN/+/-inf) or non-numeric beat. The last
    two matter because the term math clips +inf to 1.0 (a phantom T3) and lets NaN
    flow straight to H=NaN -- neither is real acoustic evidence.
    """
    try:
        n = int(v4.n_beats)
    except (AttributeError, TypeError, ValueError):
        return False
    if n <= 0:
        return False
    series = getattr(v4, "series", None)
    if series is None:
        return False
    for key in _REQUIRED_SERIES:
        try:
            vals = series[key]
        except (KeyError, TypeError):
            return False
        try:
            wrong_len = vals is None or len(vals) != n
        except TypeError:            # scalar / no __len__ -> malformed, not usable
            return False
        if wrong_len:
            return False
        if not all(_isfinite(x) for x in vals):
            return False
    return True


def _window_bounds(start: int, n_beats: int) -> Tuple[int, int]:
    """Clamp an 8-beat half to [0, n_beats); always >= 1 beat (matches the sweep h8 convention)."""
    s = 0 if start < 0 else (n_beats - 1 if start > n_beats - 1 else start)
    e = min(n_beats, s + HALF_BEATS)
    return s, e


def _local_terms_at(v4: Any, center: int, n_beats: int) -> Tuple[float, float, float, float]:
    """(L_B, L_A, L_R, L_N) at ``center``: each term averaged over the first-8 and following-8 halves."""
    s = v4.series
    full, high = s["full_db"], s["high_db"]
    gdb, gflat = s["growl_band_db"], s["growl_flatness"]
    onset = s["onset_density_midhigh"]
    b = a = r = n = 0.0
    for half_start in (center, center + HALF_BEATS):
        lo, hi = _window_bounds(half_start, n_beats)
        b += _body_term(full[lo:hi])
        a += _abrasion_term(high[lo:hi])
        r += _growl_duty_term(gdb[lo:hi], gflat[lo:hi])
        n += _onset_term(onset[lo:hi])
    return (b / 2.0, a / 2.0, r / 2.0, n / 2.0)


def _align_score(terms: Tuple[float, float, float, float]) -> float:
    return sum(w * t for w, t in zip(ALIGN_WEIGHTS, terms))


def _offsets() -> Tuple[int, ...]:
    return tuple(range(-ALIGN_RADIUS, ALIGN_RADIUS + 1))


def _check_reducer(reducer: str) -> None:
    if reducer not in REDUCERS:
        raise ValueError(f"unknown reducer {reducer!r}; expected one of {REDUCERS}")


def _select_offset(
    per_offset: Sequence[Tuple[int, Tuple[float, float, float, float], float]], reducer: str
) -> Tuple[int, Tuple[float, float, float, float], float]:
    """Pick one (offset, terms, score) entry.

    ``center`` uses the marker itself; the rest rank the 5 offsets by alignment
    score and pick a positional rank (max=top, q75=index 3, median=index 2 of 5).
    Deterministic tie-break: prefer the smaller |offset| (least alignment
    'cheating'), then the more negative offset.
    """
    _check_reducer(reducer)
    if reducer == "center":
        for entry in per_offset:
            if entry[0] == 0:
                return entry
        # ALIGN_RADIUS >= 0 always includes offset 0; fall through defensively.
    ordered = sorted(per_offset, key=lambda e: (e[2], -abs(e[0]), -e[0]))
    n = len(ordered)
    if reducer == "max":
        return ordered[-1]
    if reducer == "median":
        return ordered[n // 2]
    # q75
    return ordered[int(round(0.75 * (n - 1)))]


def _aligned_local(
    v4: Any, drop: int, *, reducer: str = "max"
) -> Tuple[Tuple[float, float, float, float], int]:
    """Return (L terms, winning_offset) for ``drop`` under ``reducer``."""
    _check_reducer(reducer)
    n_beats = v4.n_beats
    per_offset = []
    for q in _offsets():
        terms = _local_terms_at(v4, drop + q, n_beats)
        per_offset.append((q, terms, _align_score(terms)))
    offset, terms, _ = _select_offset(per_offset, reducer)
    return terms, offset


def track_baseline(
    v4: Any, drop_indices: Sequence[int], *, reducer: str = "max"
) -> Optional[TrackBaseline]:
    """Per-term median of the aligned-local terms across the track's genuine drops.

    Returns ``None`` when the v4 is malformed or no drop index is in range —
    never a fabricated baseline.
    """
    _check_reducer(reducer)
    if not _valid_v4(v4):
        return None
    n_beats = v4.n_beats
    valid = [int(d) for d in drop_indices if 0 <= int(d) < n_beats]
    if not valid:
        return None
    locals_ = [_aligned_local(v4, d, reducer=reducer)[0] for d in valid]
    t_b = percentile([t[0] for t in locals_], 50.0)
    t_a = percentile([t[1] for t in locals_], 50.0)
    t_r = percentile([t[2] for t in locals_], 50.0)
    t_n = percentile([t[3] for t in locals_], 50.0)
    n = len(valid)
    return TrackBaseline(t_b, t_a, t_r, t_n, n, n >= MIN_STABLE_DROPS, reducer)


def _paths(
    local_terms: Tuple[float, float, float, float],
    track_terms: Tuple[float, float, float, float],
) -> Tuple[float, float, float]:
    l_b, l_a, l_r, l_n = local_terms
    t_b, t_a, t_r, t_n = track_terms
    repeated_wall = min(t_b / PATH_THRESHOLDS[0], t_a / PATH_THRESHOLDS[1])
    abrasive_hammer = min(
        t_b / PATH_THRESHOLDS[2], l_b / PATH_THRESHOLDS[3], l_a / PATH_THRESHOLDS[4]
    )
    growling_hammer = min(
        t_n / PATH_THRESHOLDS[5],
        l_b / PATH_THRESHOLDS[6],
        l_r / PATH_THRESHOLDS[7],
        l_n / PATH_THRESHOLDS[8],
    )
    return repeated_wall, abrasive_hammer, growling_hammer


def _argmax(values: Sequence[float]) -> int:
    """First-index-wins argmax (deterministic; ties resolve to the PATHS order)."""
    best = 0
    for i in range(1, len(values)):
        if values[i] > values[best]:
            best = i
    return best


def hardness_result(
    v4: Any, drop: int, baseline: Optional[TrackBaseline], *, reducer: str = "max"
) -> Optional[HardnessResult]:
    """H for one drop against a precomputed per-track baseline.

    Pure: no cache/DB/ANLZ/os access. Returns ``None`` (no result) for a missing
    baseline, malformed v4, or an out-of-range drop; raises ValueError only on an
    unknown reducer (a programming error), never a phantom T3.
    """
    _check_reducer(reducer)
    if baseline is None or not _valid_v4(v4):
        return None
    n_beats = v4.n_beats
    d = int(drop)
    if not (0 <= d < n_beats):
        return None
    track_terms = baseline.terms
    local_terms, winning_offset = _aligned_local(v4, d, reducer=reducer)
    paths = _paths(local_terms, track_terms)
    h = max(paths)
    winning_path = PATHS[_argmax(paths)]
    # Marker-shift diagnostic: H over every offset (raw per-offset local terms,
    # fixed baseline) — how much H moves if the marker itself slides +/- radius.
    shift_hs = [
        max(_paths(_local_terms_at(v4, d + q, n_beats), track_terms)) for q in _offsets()
    ]
    return HardnessResult(
        h=h,
        t3=h >= T3_GATE,
        winning_path=winning_path,
        repeated_wall=paths[0],
        abrasive_hammer=paths[1],
        growling_hammer=paths[2],
        winning_offset=winning_offset,
        marker_shift_range=(min(shift_hs), max(shift_hs)),
        local_terms=local_terms,
        track_terms=track_terms,
        n_drops=baseline.n_drops,
        t_star_stable=baseline.stable,
        reducer=reducer,
    )
