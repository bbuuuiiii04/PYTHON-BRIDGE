"""Per-drop energy grades — energy-fabric stage E3 (AWR-290), STATUS-ONLY.

**Describes sound; never times or triggers a cue.** At E3 there is NO consumer:
no presentation / laser / LED path may read `DropDecision.energy_grade` (a static
import-fence test allows only `state_manager.py` + `tools/` + `tests/`). Absent /
thin / malformed data ⇒ that drop is ungraded (omitted) or `None` — never a
fabricated grade. Constants are pinned; changing any — including the gate
thresholds — is a spec amendment with exec sign-off, NEVER an implementation
decision to make a run or test pass.

Runtime-imported (by `state_manager.py` on the ANLZ worker thread); stdlib only,
pure, no I/O. The E1 track weight is passed in — this module never opens the
store (the runtime reaches it only through E2's refusal-by-construction memo).

Three gain-invariant terms per drop window `[beat, beat+16)`:
- `body`   = mean `full_db` mapped through the section-tier span (−8 dB → 0.0,
             −3 dB → 1.0) measured against the track's own `loudness_ref_db`.
- `sub_duty` = fraction of window beats with `sub_db ≥ ref − 12` (E1's sub rail).
- `onset_ratio` = mean `onset_density_midhigh` over the track's own `onset_mh_p90`
                  (omitted, not a division blow-up, when p90 ≤ 0 / non-finite).
`within_track` = mean of the present terms; `library_scaled` = `within_track ×
track_weight` or None. All three are loudness-relative / count-ratio, so a uniform
per-track mastering offset cancels exactly (the proven E1/E2 mechanism).

True-drop law: this module grades whatever raw-marker beats it is handed — the
ATTACHMENT to plan decisions (`grades_by_beat` + `plan_track`) and every surface
key off plan-selected true drops only; raw-marker grades are attach material,
never surfaced.
"""
from __future__ import annotations

import math
from typing import Optional

# ---- pinned constants (a spec amendment moves any of these, never the impl) --
DROP_WINDOW_BEATS = 16          # drop_window_vector's own width convention
MIN_WINDOW_BEATS = 8            # thinner coverage ⇒ that drop ungraded (omitted)
BODY_QUIET_OFFSET_DB = -8.0     # the proven section-tier span (E2 constants)
BODY_LOUD_OFFSET_DB = -3.0
SUB_OFFSET_DB = -12.0           # E1's REL_SUB_OFFSET_DB
IQR_GATE = 0.05                 # G2 (Part D)
SEPARATION_GATE = 0.15          # G3 (Part D)
COVERAGE_GATE = 0.95            # G1 (Part D)
MIN_ACCEPT_N = 100              # E1/E2 floor


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _all_finite(xs) -> bool:
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def grade_drops(v4, *, drop_beats, track_weight: "Optional[float]") -> "list[dict]":
    """Per raw drop beat with window coverage ≥ MIN_WINDOW_BEATS: the three-term
    gain-invariant grade, or [] on missing/non-finite `loudness_ref_db` or absent/
    short series. Never a fabricated grade (a thin or non-finite window is
    omitted)."""
    scalars = getattr(v4, "scalars", None) or {}
    ref = scalars.get("loudness_ref_db")
    if ref is None:
        return []
    try:
        ref = float(ref)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(ref):
        return []
    series = getattr(v4, "series", None) or {}
    full = series.get("full_db")
    sub = series.get("sub_db")
    onset = series.get("onset_density_midhigh")
    if not full or not sub or not onset:
        return []
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0 or len(full) < n or len(sub) < n or len(onset) < n:
        return []
    p90 = scalars.get("onset_mh_p90")
    try:
        p90 = float(p90)
    except (TypeError, ValueError):
        p90 = None
    if p90 is not None and (not math.isfinite(p90) or p90 <= 0.0):
        p90 = None

    span = BODY_LOUD_OFFSET_DB - BODY_QUIET_OFFSET_DB          # 5.0 dB
    sub_thr = ref + SUB_OFFSET_DB
    out: "list[dict]" = []
    for raw in drop_beats:
        beat = int(raw)
        s = max(0, beat)
        e = min(n, beat + DROP_WINDOW_BEATS)
        coverage = e - s
        if coverage < MIN_WINDOW_BEATS:
            continue
        fw, sw, ow = full[s:e], sub[s:e], onset[s:e]
        if not (_all_finite(fw) and _all_finite(sw) and _all_finite(ow)):
            continue
        rel = (sum(fw) / coverage) - ref
        body = _clip01((rel - BODY_QUIET_OFFSET_DB) / span)
        sub_duty = sum(1 for x in sw if x >= sub_thr) / coverage
        terms = [body, sub_duty]
        if p90 is not None:
            terms.append(_clip01((sum(ow) / coverage) / p90))
        within = sum(terms) / len(terms)
        lib = (within * track_weight
               if isinstance(track_weight, (int, float))
               and math.isfinite(track_weight) else None)
        out.append({"drop_beat": beat, "within_track": within,
                    "library_scaled": lib, "coverage": coverage})
    return out


def grades_by_beat(grades: "list[dict]") -> "dict[int, dict]":
    """Attach lookup: raw drop beat (int) → grade dict."""
    return {int(g["drop_beat"]): g for g in grades}


def gates_verdict(n_by_genre_eligible: int, n_graded: int, iqr: "Optional[float]",
                  separation: "Optional[float]") -> "tuple[bool, str]":
    """G1/G2/G3 offline verdict. Precedence: corpus floor → G1 coverage → G2
    non-degeneracy (IQR) → G3 separation. `n_by_genre_eligible` = by_genre tracks
    with a v4 entry AND an accepted-store row AND ≥1 ANLZ drop marker (E2 F1
    lesson); G1 polices window/grade holes only."""
    if n_by_genre_eligible < MIN_ACCEPT_N:
        return (False, "insufficient_corpus")
    if n_graded / n_by_genre_eligible < COVERAGE_GATE:
        return (False, "insufficient_coverage")
    if iqr is None or iqr < IQR_GATE:
        return (False, "degenerate_distribution")
    if separation is None or separation < SEPARATION_GATE:
        return (False, "inverted_or_flat_separation")
    return (True, "ok")
