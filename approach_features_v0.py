"""Raw four-view spectral approach descriptors (offline analysis, v0).

WHAT THIS IS: a single pure function, :func:`approach_features`, that takes an
already-loaded ``SpectralFeaturesV4`` and turns the cached per-beat series around
one drop into a bundle of *raw* numbers — quantiles, early-vs-late trends, floor
depths, below-floor run lengths, and the same descriptors recomputed at +/-2 beat
marker offsets. It DESCRIBES the approach; it decides nothing.

WHAT THIS IS NOT: there is no classifier here, no ``true_void``/``blackout``/class
output, no thresholds, no kind->length map, and no runtime importer. The whole
point of the SOL2 finding-1 refactor is that pre-drop darkness must be read from
the *shape over time*, not a one-sample level gate — this module is only the raw
descriptor layer that a future rules-first-vs-tiny-model bake-off will read. The
taste decisions (class boundaries, darkness lengths, the uncertain fall-back, the
marker radius) are deliberately left open.

DESIGN NOTES
- Pure and deterministic: reads ``v4.series`` / ``v4.scalars`` / ``v4.n_beats``
  only, no I/O, no randomness, no global state. Duck-typed so the synthetic v4
  test stubs work unchanged.
- Fail-safe and honest: a missing / short / non-finite / out-of-range series
  yields an explicit "unavailable / insufficient" result with a reason string —
  never a guessed value. Inconsistent *caller* inputs (e.g. giving both an
  approach start and an approach length) raise ``ValueError``.
- Reuses the shipped :func:`spectral_profile.percentile` helper; adds no new
  dependency. All summaries are first-differences, percentiles, and windowed
  means over the existing cache — no re-extraction.

Provenance: SOL2 finding-1 plan (approach-shape darkness); the four views are the
AWR-195 refactor-program charter (track-wide / current-section / approach /
first-8+following-8 landed). Absent data reads as "no signal", never an event.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from .spectral_profile import percentile

if TYPE_CHECKING:  # annotation only — the function is duck-typed at runtime
    from .audio_spectral_features import SpectralFeaturesV4


# The five charter trajectory axes (full / sub / growl / sustain / perc). Sustain
# is carried as its two cached bands so a caller can see mid vs high separately.
APPROACH_SERIES: tuple[str, ...] = (
    "full_db",
    "sub_db",
    "growl_band_db",
    "sustain_mid_db",
    "sustain_high_db",
    "perc_full",
)

# Robust quantiles exposed per series. p05 is the robust floor — NOT ``min``; the
# one-sample ``min`` gate is exactly the fragility this refactor replaces.
_QUANTILES: tuple[float, ...] = (5.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0)

# Data-derived quantiles at which run-length curves are reported (§ run_curves).
_RUN_REF_QUANTILES: tuple[float, ...] = (10.0, 25.0, 50.0)

# Engineering data-sufficiency floors, NOT musical thresholds: a slope needs two
# points, a first/second-half split needs the window to have both halves present.
_MIN_BEATS_FOR_TREND = 2

# Charter view (d) size: the first-8 and following-8 landed beats. This is the
# charter's view definition, not a class boundary or darkness length; overridable.
_DEFAULT_LANDED_LEN = 8

_OFFSET_DEFAULT_RADIUS = 2


def _isfinite(v: object) -> bool:
    try:
        return math.isfinite(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _r4(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(float(v), 4)


def _ols_slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Least-squares slope of ys over xs (per unit x). None if under-determined."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0.0:
        return None
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return num / den


def longest_run_below(values: Sequence[float], floor: float) -> int:
    """Longest run of consecutive finite beats strictly below ``floor``.

    A non-finite beat BREAKS the run — a hole cannot be claimed as below-floor.
    This is the caller-supplied-floor primitive; the descriptor bundle also
    reports run curves at data-derived quantiles so no musical floor is baked in.
    """
    best = cur = 0
    for v in values:
        if _isfinite(v) and float(v) < floor:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


@dataclass(frozen=True)
class SeriesStats:
    """Raw summary of one series over one window. All optional fields are None
    when there is not enough finite data to define them honestly."""

    present: bool          # was the series key present in v4 at all
    n_requested: int       # in-range beats in the window (after edge clamping)
    n_finite: int          # of those, how many were finite
    finite_frac: Optional[float]  # n_finite / n_requested (coverage), None if empty
    p05: Optional[float]
    p10: Optional[float]
    p25: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    p90: Optional[float]
    p95: Optional[float]
    mean: Optional[float]
    early_mean: Optional[float]   # mean over the first half of the window
    late_mean: Optional[float]    # mean over the second half
    delta: Optional[float]        # late_mean - early_mean (sign = fall/build)
    slope: Optional[float]        # OLS slope per beat over finite samples


@dataclass(frozen=True)
class RunCurve:
    """Below-floor run lengths for one series in the approach window, using a
    reference view's own quantiles as the floors — a run-length curve without a
    musical threshold. ``ref_view`` names where the floors came from."""

    ref_view: str  # "track" | "section" | "self"
    floor_p10: Optional[float]
    floor_p25: Optional[float]
    floor_p50: Optional[float]
    run_p10: Optional[int]
    run_p25: Optional[int]
    run_p50: Optional[int]


@dataclass(frozen=True)
class WindowStats:
    """One view over a beat window [start, end): availability + per-series stats."""

    req_start: int         # requested bounds (may sit outside the track)
    req_end: int
    start: int             # clamped, in-range bounds actually summarized
    end: int
    n_requested: int       # req_end - req_start (>= 0)
    n_available: int       # end - start (in-range beats)
    available: bool        # at least one in-range beat
    sufficient: bool       # trend computable: >= _MIN_BEATS_FOR_TREND in-range beats
                           # AND some series with that many FINITE samples (not slots)
    reason: str            # "" when available, else why not
    series: Mapping[str, SeriesStats]


@dataclass(frozen=True)
class DropRef:
    """Robust summary, across the supplied genuine drops, of one series' median
    over each drop's first-8 landed window — view (a)'s 'typical drop landing'."""

    n_drops: int
    p10: Optional[float]
    p50: Optional[float]
    p90: Optional[float]


@dataclass(frozen=True)
class ApproachFeatures:
    """The raw four-view descriptor bundle for one drop. Decides nothing."""

    # echoed, resolved inputs
    drop_beat: int
    approach_start: int
    approach_len: int
    landed_len: int
    n_beats: int
    available: bool
    reason: str

    # the four charter views
    track: WindowStats                       # (a) track-wide context
    drop_landing_ref: Optional[Mapping[str, DropRef]]  # (a) across genuine drops
    section: Optional[WindowStats]           # (b) explicit preceding window
    approach: WindowStats                    # (c) the pre-drop approach
    landed_first8: WindowStats               # (d) first landed beats
    landed_next8: WindowStats                # (d) following landed beats, SEPARATE

    # approach void run-length curves at data-derived quantiles
    run_curves: Mapping[str, RunCurve]

    # section/track-relative depths (approach floor p10 minus reference typical p50)
    depth_vs_track: Mapping[str, Optional[float]]
    depth_vs_section: Mapping[str, Optional[float]]

    # marker robustness: the approach + landed bundles at drop +/- offset
    approach_offsets: tuple[tuple[int, WindowStats], ...]
    landed_first8_offsets: tuple[tuple[int, WindowStats], ...]
    landed_next8_offsets: tuple[tuple[int, WindowStats], ...]


def descriptor_range(
    offset_bundles: Sequence[tuple[int, WindowStats]],
    series: str,
    stat: str,
) -> Optional[tuple[float, float]]:
    """(min, max) of one ``SeriesStats`` field across offset bundles; None if no
    offset produced a finite value. The marker-robustness 'range' companion to
    the raw offset bundles — a tight range means the descriptor is marker-stable.
    """
    vals: list[float] = []
    for _off, ws in offset_bundles:
        ss = ws.series.get(series)
        if ss is None:
            continue
        v = getattr(ss, stat, None)
        if v is not None and _isfinite(v):
            vals.append(float(v))
    if not vals:
        return None
    return (min(vals), max(vals))


def _summarize_series(
    values: Optional[Sequence[float]], start: int, end: int
) -> SeriesStats:
    """Raw summary of ``values[start:end]`` (bounds already clamped in-range)."""
    n_req = max(0, end - start)
    if values is None:
        return SeriesStats(
            present=False, n_requested=n_req, n_finite=0, finite_frac=None,
            p05=None, p10=None, p25=None, p50=None, p75=None, p90=None, p95=None,
            mean=None, early_mean=None, late_mean=None, delta=None, slope=None,
        )
    window = list(values[start:end])
    finite = [(i, float(v)) for i, v in enumerate(window) if _isfinite(v)]
    n = len(finite)
    finite_frac = _r4(n / n_req) if n_req > 0 else None
    if n == 0:
        return SeriesStats(
            present=True, n_requested=n_req, n_finite=0, finite_frac=finite_frac,
            p05=None, p10=None, p25=None, p50=None, p75=None, p90=None, p95=None,
            mean=None, early_mean=None, late_mean=None, delta=None, slope=None,
        )
    vals = [v for _, v in finite]
    q = {p: _r4(percentile(vals, p)) for p in _QUANTILES}
    # first/second half split by window POSITION (so a half that is all holes is
    # honestly empty), deterministic midpoint at n_req/2.
    mid = n_req / 2.0
    early = [v for i, v in finite if i < mid]
    late = [v for i, v in finite if i >= mid]
    early_mean = _r4(sum(early) / len(early)) if early else None
    late_mean = _r4(sum(late) / len(late)) if late else None
    delta = _r4(late_mean - early_mean) if (early_mean is not None and late_mean is not None) else None
    slope = _r4(_ols_slope([float(i) for i, _ in finite], vals))
    return SeriesStats(
        present=True, n_requested=n_req, n_finite=n, finite_frac=finite_frac,
        p05=q[5.0], p10=q[10.0], p25=q[25.0], p50=q[50.0], p75=q[75.0],
        p90=q[90.0], p95=q[95.0],
        mean=_r4(sum(vals) / n),
        early_mean=early_mean, late_mean=late_mean, delta=delta, slope=slope,
    )


def _window_stats(
    series_map: Mapping[str, Sequence[float]], n_beats: int, req_start: int, req_end: int
) -> WindowStats:
    start = max(0, min(int(req_start), n_beats))
    end = max(0, min(int(req_end), n_beats))
    if end < start:
        end = start
    n_avail = end - start
    n_requested = max(0, int(req_end) - int(req_start))
    available = n_avail >= 1
    series = {
        k: _summarize_series(series_map.get(k), start, end) for k in APPROACH_SERIES
    }
    # "Sufficient" means a trend is actually computable, not merely that beat slots
    # exist: it needs >= _MIN_BEATS_FOR_TREND in-range beat positions AND at least
    # one series with that many FINITE samples — an all-hole window spans beats but
    # yields no slope/delta/percentile. Both are required; either alone is hollow.
    enough_beats = n_avail >= _MIN_BEATS_FOR_TREND
    enough_finite = any(ss.n_finite >= _MIN_BEATS_FOR_TREND for ss in series.values())
    sufficient = enough_beats and enough_finite
    if n_requested <= 0:
        reason = "empty window (end <= start)"
    elif n_avail == 0:
        reason = "window out of track range"
    elif not enough_beats:
        reason = "insufficient beats for trend"
    elif not enough_finite:
        reason = "insufficient finite data for trend"
    else:
        reason = ""
    return WindowStats(
        req_start=int(req_start), req_end=int(req_end), start=start, end=end,
        n_requested=n_requested, n_available=n_avail,
        available=available, sufficient=sufficient, reason=reason, series=series,
    )


def _run_curves(
    series_map: Mapping[str, Sequence[float]],
    approach: WindowStats,
    track: WindowStats,
    section: Optional[WindowStats],
) -> dict[str, RunCurve]:
    """Longest below-floor runs in the approach window, floored at the reference
    view's own p10/p25/p50. Reference precedence: track ('deep for this track')
    -> section -> self. Reuses the already-computed quantiles; no re-percentile.
    """
    out: dict[str, RunCurve] = {}
    for k in APPROACH_SERIES:
        appr_vals = list((series_map.get(k) or [])[approach.start:approach.end])
        # pick a reference whose p10 is defined
        ref_view = "self"
        ref_ss = approach.series[k]
        for name, ws in (("track", track), ("section", section)):
            if ws is None:
                continue
            cand = ws.series.get(k)
            if cand is not None and cand.p10 is not None:
                ref_view, ref_ss = name, cand
                break
        floors = {q: getattr(ref_ss, f"p{int(q):02d}") for q in _RUN_REF_QUANTILES}
        runs = {
            q: (longest_run_below(appr_vals, floors[q]) if floors[q] is not None else None)
            for q in _RUN_REF_QUANTILES
        }
        out[k] = RunCurve(
            ref_view=ref_view,
            floor_p10=floors[10.0], floor_p25=floors[25.0], floor_p50=floors[50.0],
            run_p10=runs[10.0], run_p25=runs[25.0], run_p50=runs[50.0],
        )
    return out


def _depth(
    approach: WindowStats, ref: Optional[WindowStats]
) -> dict[str, Optional[float]]:
    """Per series: the approach FLOOR (p10) minus the reference's TYPICAL level
    (p50). Negative = the approach dips below where the track/section normally
    sits. The reference is the median, NOT its p10, on purpose: a long void drags
    a floor-vs-floor comparison to ~0 (the void contaminates the track's own p10),
    whereas the median stays at the body of the track — so this stays a true
    'deep for this track' signal. None when either side is undefined.
    """
    out: dict[str, Optional[float]] = {}
    for k in APPROACH_SERIES:
        a = approach.series[k].p10
        r = ref.series[k].p50 if ref is not None else None
        out[k] = _r4(a - r) if (a is not None and r is not None) else None
    return out


def _drop_landing_ref(
    series_map: Mapping[str, Sequence[float]],
    n_beats: int,
    genuine_drops: Sequence[int],
    landed_len: int,
) -> dict[str, DropRef]:
    """View (a) 'across supplied genuine drops': for each series, the robust
    spread of the per-drop first-``landed_len`` medians. Skips drops whose landed
    window has no finite data. Median per drop keeps one ringing beat from
    dominating (again: no ``min``).
    """
    out: dict[str, DropRef] = {}
    drops = [int(d) for d in genuine_drops if 0 <= int(d) < n_beats]
    for k in APPROACH_SERIES:
        vals = series_map.get(k)
        meds: list[float] = []
        if vals is not None:
            for d in drops:
                seg = [float(v) for v in vals[d:min(n_beats, d + landed_len)] if _isfinite(v)]
                if seg:
                    meds.append(percentile(seg, 50.0))
        if meds:
            out[k] = DropRef(
                n_drops=len(meds),
                p10=_r4(percentile(meds, 10.0)),
                p50=_r4(percentile(meds, 50.0)),
                p90=_r4(percentile(meds, 90.0)),
            )
        else:
            out[k] = DropRef(n_drops=0, p10=None, p50=None, p90=None)
    return out


def _resolve_approach_bounds(
    drop: int, approach_start: Optional[int], approach_len: Optional[int]
) -> tuple[int, int, bool]:
    """Return (start, end, start_is_derived). end is the drop. When the caller
    gave a length the window SLIDES with the drop (for offsets); when they gave an
    explicit start it stays FIXED and only the end moves."""
    if approach_start is not None:
        return int(approach_start), int(drop), False
    return int(drop) - int(approach_len), int(drop), True  # type: ignore[arg-type]


def approach_features(
    v4: "SpectralFeaturesV4",
    drop_beat: int,
    *,
    approach_start: Optional[int] = None,
    approach_len: Optional[int] = None,
    section_start: Optional[int] = None,
    section_len: Optional[int] = None,
    genuine_drops: Optional[Sequence[int]] = None,
    landed_len: int = _DEFAULT_LANDED_LEN,
    offset_radius: int = _OFFSET_DEFAULT_RADIUS,
) -> ApproachFeatures:
    """Raw four-view approach descriptors for one drop. Decides nothing.

    Inputs (all explicit):
      * ``v4`` — an already-loaded ``SpectralFeaturesV4`` (or duck-typed stub).
      * ``drop_beat`` — the drop marker beat index.
      * ``approach_start`` XOR ``approach_len`` — the pre-drop approach window is
        ``[approach_start, drop_beat)`` OR ``[drop_beat - approach_len, drop_beat)``.
        Exactly one is required.
      * ``section_start`` XOR ``section_len`` (optional) — the current-section
        window is ``[section_start, approach_start)`` OR
        ``[approach_start - section_len, approach_start)``. Neither -> section is
        reported unavailable (no window was supplied).
      * ``genuine_drops`` (optional) — the track's real drop markers; enables the
        across-genuine-drops landing reference of view (a).
      * ``landed_len`` — charter view (d) size (default 8).
      * ``offset_radius`` — recompute approach + landed bundles at drop +/- k for
        k in 0..offset_radius, for marker robustness.

    Raises ``ValueError`` only for inconsistent CALLER inputs (both/neither of an
    XOR pair, non-positive lengths, negative radius). Degenerate DATA (empty /
    short / non-finite / out-of-range) never raises — it yields explicit
    unavailable/insufficient bundles instead of a guessed value.
    """
    # --- validate caller inputs (safe exceptions, not guesses) ---
    if (approach_start is None) == (approach_len is None):
        raise ValueError("give exactly one of approach_start / approach_len")
    if approach_len is not None and int(approach_len) <= 0:
        raise ValueError("approach_len must be positive")
    if section_start is not None and section_len is not None:
        raise ValueError("give at most one of section_start / section_len")
    if section_len is not None and int(section_len) <= 0:
        raise ValueError("section_len must be positive")
    if int(landed_len) <= 0:
        raise ValueError("landed_len must be positive")
    if int(offset_radius) < 0:
        raise ValueError("offset_radius must be >= 0")

    series_map: Mapping[str, Sequence[float]] = getattr(v4, "series", {}) or {}
    n_beats = getattr(v4, "n_beats", None)
    if n_beats is None:  # fall back to the longest present series length
        n_beats = max((len(series_map[k]) for k in series_map), default=0)
    n_beats = int(n_beats)

    drop = int(drop_beat)
    a_start, a_end, derived = _resolve_approach_bounds(drop, approach_start, approach_len)
    resolved_len = a_end - a_start

    # --- the four views at the true drop marker ---
    track = _window_stats(series_map, n_beats, 0, n_beats)
    approach = _window_stats(series_map, n_beats, a_start, a_end)

    section: Optional[WindowStats] = None
    if section_start is not None:
        section = _window_stats(series_map, n_beats, int(section_start), a_start)
    elif section_len is not None:
        section = _window_stats(series_map, n_beats, a_start - int(section_len), a_start)

    landed_first8 = _window_stats(series_map, n_beats, drop, drop + int(landed_len))
    landed_next8 = _window_stats(
        series_map, n_beats, drop + int(landed_len), drop + 2 * int(landed_len)
    )

    drop_landing_ref = (
        _drop_landing_ref(series_map, n_beats, genuine_drops, int(landed_len))
        if genuine_drops is not None
        else None
    )

    run_curves = _run_curves(series_map, approach, track, section)
    depth_vs_track = _depth(approach, track)
    depth_vs_section = _depth(approach, section)

    # --- marker robustness: recompute approach + landed at drop +/- offset ---
    approach_offsets: list[tuple[int, WindowStats]] = []
    landed_first8_offsets: list[tuple[int, WindowStats]] = []
    landed_next8_offsets: list[tuple[int, WindowStats]] = []
    for off in range(-int(offset_radius), int(offset_radius) + 1):
        d = drop + off
        os_start, os_end, _ = _resolve_approach_bounds(
            d, None if derived else a_start, resolved_len if derived else None
        )
        approach_offsets.append((off, _window_stats(series_map, n_beats, os_start, os_end)))
        landed_first8_offsets.append(
            (off, _window_stats(series_map, n_beats, d, d + int(landed_len)))
        )
        landed_next8_offsets.append(
            (off, _window_stats(series_map, n_beats, d + int(landed_len), d + 2 * int(landed_len)))
        )

    # Top-level availability is honest only if the approach window both intersects
    # the track AND carries at least one finite datum in some series — an all-hole
    # (missing / entirely non-finite) window is not usable even though its beat
    # positions are in range. Per-series partial availability (each WindowStats /
    # SeriesStats) is unchanged; only this top-level flag gains the finite check.
    window_ok = approach.available
    has_finite = any(ss.n_finite > 0 for ss in approach.series.values())
    available = window_ok and has_finite
    if not window_ok:
        reason = "approach window has no in-range beats: " + approach.reason
    elif not has_finite:
        reason = "approach window has no finite data in any series"
    else:
        reason = ""

    return ApproachFeatures(
        drop_beat=drop,
        approach_start=a_start,
        approach_len=resolved_len,
        landed_len=int(landed_len),
        n_beats=n_beats,
        available=available,
        reason=reason,
        track=track,
        drop_landing_ref=drop_landing_ref,
        section=section,
        approach=approach,
        landed_first8=landed_first8,
        landed_next8=landed_next8,
        run_curves=run_curves,
        depth_vs_track=depth_vs_track,
        depth_vs_section=depth_vs_section,
        approach_offsets=tuple(approach_offsets),
        landed_first8_offsets=tuple(landed_first8_offsets),
        landed_next8_offsets=tuple(landed_next8_offsets),
    )
