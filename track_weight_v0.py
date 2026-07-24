"""Offline library track-weight descriptor — energy-fabric stage E1 (AWR-286).

**NON-AUTHORITATIVE / OFFLINE ONLY.** This module has **zero runtime importers**
(only ``tools/`` and ``tests/`` may import it — a static test enforces this
forever). It describes sound; it NEVER times or triggers a cue and decides
NOTHING live. There is no live consumer at this stage — E2+ consumers arrive
under their own specs. Absent / short / malformed data returns ``None`` — never a
fabricated weight.

What it computes: four gain-invariant per-track descriptor components, then a
library-relative weight in [0,1] = the mean of each component's mid-rank
percentile across the whole library.

Gain-invariance by construction (the EFREV-N3 cure): the two dB duties compare
each track's own ``full_db`` / ``sub_db`` beats against that track's OWN
``loudness_ref_db`` (= p95 full_db, ``audio_spectral_features.py:423``), so a
uniform per-track mastering offset shifts numerator and reference together and
cancels EXACTLY; ``onset_density_midhigh`` and ``growl_flatness`` are count / ratio
series untouched by level. Ranking against the library then only ever absorbs
LIBRARY-WIDE offsets — no absolute-dB feature enters the aggregate. (A spectral
REBALANCE is outside gain-invariance scope, per review N3.)

Constants are pinned; changing any — including the acceptance thresholds — is a
spec amendment for the exec, NEVER an implementation decision to make a run pass.

Annotations are strings (``from __future__ import annotations``) so no package
import (e.g. ``SpectralFeaturesV4``) is ever required to satisfy a type checker —
the module imports stdlib only (review N1).
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

# ---- pinned constants (changing any is a spec amendment) --------------------
REL_BODY_OFFSET_DB = -8.0    # reuse of the section_quiet_offset_db precedent
REL_SUB_OFFSET_DB = -12.0    # [assumed] sub-presence floor below the track's p95
MIN_BEATS = 64               # tracks shorter than 16 bars yield None
COMPONENT_KEYS = ("body_duty", "sub_duty", "onset_mh_mean", "growl_flatness_mean")
SPEARMAN_ACCEPT_MAX = 0.50   # |rho| gate, by_genre split (Part D rationale)
MIN_ACCEPT_N = 100           # by_genre tracks required for the gate to be meaningful


def _finite_floats(xs) -> Optional[list]:
    """Return the list as floats if every element is a finite real, else None."""
    out = []
    for x in xs:
        try:
            f = float(x)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(f):
            return None
        out.append(f)
    return out


def components(v4) -> "Optional[dict]":
    """The four pure descriptor components for one track, or None on
    missing / short / malformed data (never a fabricated number). `v4` is a
    duck-typed SpectralFeaturesV4 (``.scalars``, ``.series``, ``.n_beats``)."""
    scalars = getattr(v4, "scalars", None)
    if not scalars or "loudness_ref_db" not in scalars:
        return None
    try:
        ref = float(scalars["loudness_ref_db"])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(ref):
        return None
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n < MIN_BEATS:
        return None
    series = getattr(v4, "series", None)
    if not series:
        return None
    try:
        full = series["full_db"]
        sub = series["sub_db"]
        onset = series["onset_density_midhigh"]
        flat = series["growl_flatness"]
    except (KeyError, TypeError):
        return None
    parsed = [_finite_floats(s) for s in (full, sub, onset, flat)]
    if any(p is None or len(p) < n for p in parsed):
        return None
    full, sub, onset, flat = (p[:n] for p in parsed)
    body_thr = ref + REL_BODY_OFFSET_DB
    sub_thr = ref + REL_SUB_OFFSET_DB
    return {
        "body_duty": sum(1 for x in full if x >= body_thr) / n,
        "sub_duty": sum(1 for x in sub if x >= sub_thr) / n,
        "onset_mh_mean": sum(onset) / n,
        "growl_flatness_mean": sum(flat) / n,
    }


def rank_in(sorted_values: "Sequence[float]", value: float) -> float:
    """Mid-rank percentile in [0,1]: (count_less + 0.5*count_equal) / n. An empty
    distribution is a PROGRAMMING error, not a data condition -> ValueError
    (never 0.5, never None)."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("rank_in called with an empty distribution")
    less = sum(1 for x in sorted_values if x < value)
    equal = sum(1 for x in sorted_values if x == value)
    return (less + 0.5 * equal) / n


def build_distribution(all_components: "Sequence[dict]") -> "dict":
    """Per component key, the SORTED list of library values."""
    dist = {k: [] for k in COMPONENT_KEYS}
    for comp in all_components:
        for k in COMPONENT_KEYS:
            dist[k].append(float(comp[k]))
    for k in COMPONENT_KEYS:
        dist[k].sort()
    return dist


def track_weight(comp: "dict", distribution: "dict") -> float:
    """Mean of the four rank_in percentiles. Equal weights, pinned."""
    return sum(rank_in(distribution[k], comp[k])
               for k in COMPONENT_KEYS) / len(COMPONENT_KEYS)


def _mid_ranks(xs: "list") -> "list":
    """Average (mid) ranks, 1-based, with ties sharing their mean rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i, n = 0, len(xs)
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: "Sequence[float]", ys: "Sequence[float]") -> "Optional[float]":
    """Spearman rho = Pearson on average (mid) ranks. None if len < 3, lengths
    differ, or either side is constant (zero variance). Pure stdlib — CI is
    Python 3.11, so statistics.correlation(method='ranked') (3.12+) is NOT used."""
    xs, ys = list(xs), list(ys)
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = _mid_ranks(xs), _mid_ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((r - mx) ** 2 for r in rx)
    syy = sum((r - my) ** 2 for r in ry)
    if sxx == 0.0 or syy == 0.0:
        return None
    sxy = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    return sxy / math.sqrt(sxx * syy)


def _percentile(sorted_values: "Sequence[float]", q: float) -> "Optional[float]":
    """Local linear-interpolation percentile (q in [0,100]). Reimplemented here
    on purpose — importing spectral_profile would couple this shadow module to
    runtime code."""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_values[0])
    pos = (q / 100.0) * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def degenerate_components(distribution: "dict") -> "list":
    """Component keys whose library values have p25 == p75 (zero IQR): ranking on
    them would be noise. Empty / single-value distributions count as degenerate."""
    out = []
    for k in COMPONENT_KEYS:
        vals = sorted(distribution.get(k, []))
        if len(vals) < 2:
            out.append(k)
            continue
        if _percentile(vals, 25) == _percentile(vals, 75):
            out.append(k)
    return out


def acceptance_verdict(n_by_genre: int, rho: "Optional[float]",
                       degenerate: "Sequence[str]") -> "tuple":
    """Pure accept decision (Part-D gate, test seam). Returns (accepted, reason).
    Precedence: corpus size -> loudness proxy -> degenerate component -> ok."""
    if n_by_genre < MIN_ACCEPT_N:
        return (False, "insufficient_corpus")
    if rho is None or abs(rho) > SPEARMAN_ACCEPT_MAX:
        return (False, "loudness_proxy")
    if list(degenerate):
        return (False, "degenerate_component")
    return (True, "ok")
