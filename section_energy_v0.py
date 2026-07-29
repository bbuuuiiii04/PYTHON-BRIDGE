"""Per-section energy grades — energy-fabric stage E2 (AWR-288/291), STATUS-ONLY.

**Describes sound; never times or triggers a cue.** At E2 there is NO consumer:
no LED / laser / SoundSwitch module may read these grades (a static import-fence
test enforces the allowlist). Absent / short / malformed data ⇒ `None` or `[]` —
never a fabricated grade. Constants are pinned; changing any — including the gate
thresholds — is a spec amendment with exec sign-off, NEVER an implementation
decision to make a run or test pass.

Unlike E1's `track_weight_v0`, this module IS runtime-imported (by
`state_manager.py` on the ANLZ worker thread), so it stays pure: stdlib only, and
the segment builders (`smart_phrasing.build_phrase_segments_from_markers`,
`spectral_profile.section_map`) are imported LAZILY inside `grade_sections` to
avoid any import-order coupling at bridge startup. The ONLY I/O is
`load_track_weight_store()` — worker / offline threads only, NEVER the push loop.

Two grades per section:
- `within_track` = the section's **median** `full_db` (AWR-291: median, not mean
  — one silent beat pinned at the −100 dB floor no longer drags a whole drop
  section's grade to zero; a mean over a long outro that fades to silence
  describes neither the drop nor the tail) mapped through the loudness-relative
  span −12 dB → 0.0, 0 dB → 1.0, measured against the track's own
  `loudness_ref_db`. This span is NO LONGER the `spectral_profile` section tiers
  (those are −8/−3): the old top rail sat on the corpus median and pinned ~49% of
  sections at 1.000, so AWR-291 re-placed it from the measured section-level
  distribution.
- `library_scaled` = `within_track × track_weight` (the ladder's §B.2 product
  law), or `None` when the E1 track-weight store is missing / refused.

Three published facets ride beside the two grades on every section dict (§2/§3
facet publication — RECORDED on the grade dict + the ANLZ payload, but NEVER
surfaced on the per-deck status block; `current_section` projects them off,
below):
- `segmentation_basis` in {`markers`, `section_map`} — WHICH lawful basis drew
  the section boundaries (the marker phrase segments, or the audio section-map
  fallback). Chosen inside `_normalized_segments`, which now RETURNS it.
- `contrast_class` in {`flat`, `normal`} — `flat` iff the UNCLIPPED per-section
  `rel` range (max − min over the sections that grade) is < `CONTRAST_FLAT_MAX_DB`
  (5.0 dB). Reduced in the same pass that grades; the `label` stays the
  runway/true-drop authority.
- `slope` — §3's within-section loudness-trajectory channel: the mean POSITIVE
  per-beat slope of the smoothed `full_db` over a ~3 s attentional window,
  aggregated per section (`t_pos`), in RAW dB per attentional window — NON-negative
  (`0.0` for a section with no rise), unbounded above, NOT mapped to [0,1]. It
  measures how hard a section is RISING, not which way it moves. The beat clock is
  derived IN-MODULE from the v4 object (`60 × n_beats / duration_s`, ruled C1) so
  `grade_sections` needs no tempo argument and the call site stays closed; an
  underivable clock (or a section with no finite windowed slope inside it) yields
  an ABSENT `slope` key, never a fabricated `0.0`. The windowed-slope math
  (`_moving_average` / `_trailing_slope` / `_bpm_window_beats`) is extracted
  verbatim from the C3 prototype (`c3_lib` / `c3_e2_tension`), never retyped, and
  only the IN-SECTION window MODE is offered — the trailing MODE inverts the
  predicted sign (C3-measured) and is structurally unreachable here.

Gain-invariant by construction in exact arithmetic. In the shipped pipeline the
cancellation is exact to about ±0.005 grade units, because every stored dB value
is rounded to 0.1 dB (`audio_spectral_features.py:307-311`); and it does not hold
at all on beats pinned at the fixed −100.0 dB power floor (`:35`, `:313-314`),
which occurs on ~19% of BY GENRE tracks. Verified by re-extraction at two gains,
not by adding an offset to cached values (`tools/energy_perturbation_check.py`).

Refusal law, enforced by construction: `load_track_weight_store()` returns None
unless the file parses, `schema_version == 2` (AWR-291), `accepted is True`, and
`tracks`/`distribution` are present dicts — so an `accepted: false` / missing /
malformed / v1 store yields no library-scaled grade, never a fabricated one.
`within_track` takes no store input, so with a refused store the section still
grades, with `library_scaled = None` (EREV1 N6) — this refuses to library-scale,
not to grade.
"""
from __future__ import annotations

import json
import math
from typing import Any, Optional

# ---- pinned constants (a spec amendment moves any of these, never the impl) --
# Loudness-relative span for the section grade. NOT the spectral_profile section
# tier offsets any more: those are -8/-3 and are flagged in their own source as
# "engineering scale constants, not corpus-calibrated" (spectral_profile.py:54-55).
# Re-placed by AWR-291 from the measured corpus distribution of section levels
# relative to loudness_ref_db (p05 -12.02, p50 -3.13, p95 -0.40 dB): the old top
# rail sat on the corpus MEDIAN, pinning 49.0% of sections at 1.000.
SECTION_SPAN_LOW_DB = -12.0      # -> 0.0
SECTION_SPAN_HIGH_DB = 0.0       # -> 1.0
MIN_SECTION_BEATS = 4
STORE_SCHEMA_VERSION = 2         # AWR-291 bump; SECOND of two declarations (the
                                 # first is track_weight_v0.STORE_SCHEMA_VERSION —
                                 # NOT imported here, restated; both fail closed on
                                 # skew, asserted equal in tests).
COVERAGE_GATE = 0.95             # G1, by_genre (Part D)
SATURATION_GATE_MAX = 0.20       # G2: fraction of sections on either rail
RANKABILITY_GATE = 0.90          # G3: tracks whose chorus sections differ
SEPARATION_GATE = 0.25           # G4: median(chorus) - median(low)
MIN_ACCEPT_N = 100               # G-gate corpus floor (== E1's MIN_ACCEPT_N)

# ---- §3 slope channel — pinned constants (a spec amendment moves any, never the
# impl). Extracted verbatim from the C3 prototype (c3_e2_tension.py:28-33 /
# c3_lib.py:128-133); the slope MATH below is likewise a byte-copy, never retyped.
ATT_SECONDS = 3.0                # Farbood/TenseMusic loudness attentional window
SILENCE_GUARD_DB = 60.0          # floor full_db at ref-60 dB before smoothing
CONTRAST_FLAT_MAX_DB = 5.0       # 'flat' iff unclipped per-section rel range < this


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _median(values) -> float:
    """Median of a non-empty numeric sequence. Local — importing spectral_profile
    would couple this runtime module to it (same one-way convention as the span
    constants above)."""
    v = sorted(values)
    n = len(v)
    mid = n // 2
    if n % 2:
        return float(v[mid])
    return (float(v[mid - 1]) + float(v[mid])) / 2.0


def load_track_weight_store(path) -> "Optional[dict]":
    """Refusal gate (Absolute Rules / E1REV law): the parsed E1 store dict, or
    None. Never raises on bad content — OSError / JSONDecodeError / shape
    problems all become a reasoned None."""
    try:
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(store, dict):
        return None
    if store.get("schema_version") != STORE_SCHEMA_VERSION:
        return None
    if store.get("accepted") is not True:
        return None
    if not isinstance(store.get("tracks"), dict):
        return None
    if not isinstance(store.get("distribution"), dict):
        return None
    return store


def store_track_weight(store: "dict", cache_key: str) -> "Optional[float]":
    """`store["tracks"][cache_key]["track_weight"]` as a finite float, else None."""
    try:
        tw = store["tracks"][cache_key]["track_weight"]
        tw = float(tw)
    except (KeyError, TypeError, ValueError):
        return None
    return tw if math.isfinite(tw) else None


# --- §3 slope math: extracted VERBATIM from the C3 prototype, never retyped -----
# `_moving_average` / `_trailing_slope` / `_bpm_window_beats` are byte-for-byte
# copies of `c3_lib.moving_average` / `trailing_slope` / `bpm_window_beats` (only
# the leading underscore on the name differs); `_slope_series` / `_section_slope`
# port `c3_e2_tension.tension_series` (guard=True) / `section_tension` (t_pos,
# in-section MODE). A build-time byte-diff asserts the copies match the prototype.
def _moving_average(xs, w):
    """Centred moving average, window w beats (edge-truncated)."""
    n = len(xs)
    if w <= 1:
        return list(xs)
    half = w // 2
    out = []
    csum = [0.0]
    for x in xs:
        csum.append(csum[-1] + x)
    for i in range(n):
        a = max(0, i - half)
        b = min(n, i + half + 1)
        out.append((csum[b] - csum[a]) / (b - a))
    return out


def _trailing_slope(sm, w):
    """Least-squares slope (units/beat) over the trailing w beats ending at i.

    Farbood/TenseMusic 'attentional window' shape: the slope of the smoothed
    feature over the last w beats. Beats with <3 samples of history get None.
    """
    n = len(sm)
    out = [None] * n
    for i in range(n):
        a = max(0, i - w + 1)
        m = i - a + 1
        if m < 3:
            continue
        xs = range(m)
        mx = (m - 1) / 2.0
        ys = sm[a:i + 1]
        my = sum(ys) / m
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        out[i] = num / den if den > 0 else None
    return out


def _bpm_window_beats(bpm, seconds):
    """Seconds -> beats at this track's tempo, floored at 2 beats."""
    if not (isinstance(bpm, float) and math.isfinite(bpm)) or bpm <= 0:
        return None
    return max(2, int(round(seconds * bpm / 60.0)))


def _derive_bpm(v4) -> "Optional[float]":
    """Beat clock derived IN-MODULE from the v4 object (ruled C1): bpm =
    60 × n_beats / duration_s. No signature or call-site change — grade_sections
    receives no tempo. None (⇒ absent slope, never a fabricated 0.0) when the
    clock is not derivable: n_beats ≤ 0, or duration_s non-finite / ≤ 0."""
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0:
        return None
    dur = getattr(v4, "duration_s", None)
    try:
        dur = float(dur)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(dur) or dur <= 0.0:
        return None
    return 60.0 * n / dur


def _slope_series(full, ref, n, bpm):
    """(per-beat smoothed-loudness slope × window, window w) in dB per attentional
    window, or (None, None). Ports c3_e2_tension.tension_series (guard=True): floor
    at ref−SILENCE_GUARD_DB, centred moving-average, trailing least-squares slope,
    scaled by the window length. Refuses (None) on a non-derivable window or any
    non-finite beat in full[:n] — refusal beats fabrication."""
    fb = list(full[:n])
    if not fb or not all(isinstance(x, (int, float)) and math.isfinite(x)
                         for x in fb):
        return None, None
    w = _bpm_window_beats(bpm, ATT_SECONDS)
    if w is None:
        return None, None
    floor = ref - SILENCE_GUARD_DB
    fb = [x if x > floor else floor for x in fb]
    sm = _moving_average(fb, w)
    sl = _trailing_slope(sm, w)
    return [None if s is None else s * w for s in sl], w


def _section_slope(slope_win, s, e, w) -> "Optional[float]":
    """t_pos — the mean POSITIVE per-beat slope (dB per attentional window) over
    the IN-SECTION window [min(e-1, s+w-1), e). Non-negative (each term clamped at
    0 before the mean), 0.0 for a section with no rise; None when no finite windowed
    slope lands inside the section. This is the in-section MODE of
    c3_e2_tension.section_tension — the trailing MODE (lo = s) is C3's measured
    sign-inverting configuration and is not reachable here."""
    lo = min(e - 1, s + w - 1)
    vals = [x for x in slope_win[lo:e] if x is not None]
    if not vals:
        return None
    return sum(max(0.0, x) for x in vals) / len(vals)


def _normalized_segments(v4, anlz_drops, anlz_buildups, anlz_breakdowns):
    """((start, end_exclusive, label) integer beat ranges, segmentation_basis).
    basis is 'markers' when the marker phrase segments produce ranges, else
    'section_map' when the audio-derived fallback does (the E2 basis record — it is
    now RETURNED, not discarded). Lazy imports keep this module's top level
    stdlib-only."""
    from rb_ss_bridge_v2 import smart_phrasing  # noqa: PLC0415
    segs = smart_phrasing.build_phrase_segments_from_markers(
        list(anlz_buildups), list(anlz_drops), list(anlz_breakdowns),
        [], int(v4.n_beats))
    out = []
    for s in segs:
        out.append((int(s.start_beat), int(s.end_beat), str(s.label)))
    if out:
        return out, "markers"
    from rb_ss_bridge_v2 import spectral_profile  # noqa: PLC0415
    blocks = spectral_profile.section_map(
        v4, drops=anlz_drops, buildups=anlz_buildups, breakdowns=anlz_breakdowns)
    for b in blocks:
        # section_map end_beat is inclusive (b-1); normalize to exclusive.
        out.append((int(b["start_beat"]), int(b["end_beat"]) + 1, "other"))
    return out, "section_map"


def grade_sections(v4, *, anlz_drops, anlz_buildups, anlz_breakdowns,
                   track_weight: "Optional[float]") -> "list[dict]":
    """The E2 core. Returns a list of self-describing section grades, or [] on
    missing `loudness_ref_db` / empty-or-short series / non-finite values."""
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
    if not full:
        return []
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0 or len(full) < n:
        return []

    segments, basis = _normalized_segments(
        v4, anlz_drops, anlz_buildups, anlz_breakdowns)
    bpm = _derive_bpm(v4)
    slope_win, w = (_slope_series(full, ref, n, bpm)
                    if bpm is not None else (None, None))

    span = SECTION_SPAN_HIGH_DB - SECTION_SPAN_LOW_DB                # 12.0 dB
    grades: "list[dict]" = []
    rels: "list[float]" = []   # unclipped per-section rel, for contrast_class range
    for start, end, label in segments:
        s = max(0, start)
        e = min(n, end)
        if e - s < MIN_SECTION_BEATS:
            continue
        beats = full[s:e]
        if not beats or not all(isinstance(x, (int, float)) and math.isfinite(x)
                                for x in beats):
            continue
        rel = _median(beats) - ref
        within = _clip01((rel - SECTION_SPAN_LOW_DB) / span)
        lib = (within * track_weight
               if isinstance(track_weight, (int, float))
               and math.isfinite(track_weight) else None)
        grade = {"start_beat": s, "end_beat": e, "label": label,
                 "within_track": within, "library_scaled": lib,
                 "segmentation_basis": basis}
        if slope_win is not None:
            slope = _section_slope(slope_win, s, e, w)
            if slope is not None:               # absent (never 0.0) if unusable
                grade["slope"] = slope
        grades.append(grade)
        rels.append(rel)
    if grades:
        contrast_class = ("flat" if (max(rels) - min(rels)) < CONTRAST_FLAT_MAX_DB
                          else "normal")
        for g in grades:
            g["contrast_class"] = contrast_class
    return grades


def current_section(grades: "list[dict]", abs_beat: float) -> "Optional[dict]":
    """The PROJECTION of the section containing `abs_beat` ([start, end)) to the
    frozen five-key status set {start_beat, end_beat, label, within_track,
    library_scaled}, or None. The facets (`slope` / `segmentation_basis` /
    `contrast_class`) stay on the grade dicts and in the ANLZ payload record but
    are NEVER surfaced on the per-deck status block — this projection is what keeps
    that status SHAPE frozen while the grade dicts grow (§2 Task 3e). Linear scan —
    at most a few dozen sections."""
    for g in grades:
        if g["start_beat"] <= abs_beat < g["end_beat"]:
            return {"start_beat": g["start_beat"], "end_beat": g["end_beat"],
                    "label": g["label"],
                    "within_track": g.get("within_track"),
                    "library_scaled": g.get("library_scaled")}
    return None


def gates_verdict(n_by_genre_eligible: int, n_graded: int,
                  railed_fraction: "Optional[float]",
                  rankable_fraction: "Optional[float]",
                  separation: "Optional[float]") -> "tuple[bool, str]":
    """Offline verdict. Precedence: corpus floor → G1 coverage → G2 saturation →
    G3 rankability → G4 separation. `n_by_genre_eligible` = by_genre tracks with a
    v4 entry AND an accepted-store row (E2REV F1); G1 polices segmentation /
    grade-math holes only. Every None fails closed."""
    if n_by_genre_eligible < MIN_ACCEPT_N:
        return (False, "insufficient_corpus")
    if n_graded / n_by_genre_eligible < COVERAGE_GATE:
        return (False, "insufficient_coverage")
    if railed_fraction is None or railed_fraction > SATURATION_GATE_MAX:
        return (False, "saturated_grades")
    if rankable_fraction is None or rankable_fraction < RANKABILITY_GATE:
        return (False, "unrankable_grades")
    if separation is None or separation < SEPARATION_GATE:
        return (False, "inverted_or_flat_separation")
    return (True, "ok")
