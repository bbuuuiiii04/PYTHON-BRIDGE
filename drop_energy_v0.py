"""Per-drop energy grades — energy-fabric stage E3 (AWR-290/291), STATUS-ONLY.

**Describes sound; never times or triggers a cue.** At E3 there is NO consumer:
no presentation / laser / LED path may read `DropDecision.energy_grade` (a static
import-fence test allows only `state_manager.py` + `tools/` + `tests/`). Absent /
thin / malformed data ⇒ that drop is ungraded (omitted) or `None` — never a
fabricated grade. Constants are pinned; changing any — including the gate
thresholds — is a spec amendment with exec sign-off, NEVER an implementation
decision to make a run or test pass.

Runtime-imported (by `state_manager.py` on the ANLZ worker thread); stdlib only,
pure, no I/O. The E1 track weight AND the corpus drop-level fallback distribution
are passed in — this module never opens the store.

Four REQUIRED terms per drop window `[beat, beat+16)` (AWR-291). All four are
ranks or ratios, so all four are inherently level-invariant, a stronger property
than the relative-dB construction the v1 terms used:
- `body`      = mid-rank of this window's level (window mean `full_db` −
                `loudness_ref_db`) among the track's OWN drop-window levels when the
                track has ≥2 of them (`body_basis = "track_drops"`); otherwise
                among the corpus drop-level distribution carried in the v2 store
                (`body_basis = "corpus"`, measured 2.18% of tracks). A rank CANNOT
                saturate — this replaced the v1 level `body` term, which was pinned
                at 1.000 on 94% of drops.
- `activity`  = clip01(mean `fluxsum_midhigh` / this track's own p90 of
                `fluxsum_midhigh`). A dB-domain onset-flux window sum normalised to
                the track's own range — it REPLACED the v1 `onset` count term, whose
                cached `onset_mh_p90` normaliser sat in {2,3,4} on 98.2% of tracks.
- `perc_high` = clip01(mean `perc_high` / this track's own p90 of `perc_high`).
- `growl`     = clip01(mean `growl_flatness` / `growl_timbre_p90`).
`within_track` = mean of ALL FOUR terms; `library_scaled` = `within_track ×
track_weight` or None. Each grade dict also PUBLISHES the four term values
(`body`, `activity`, `perc_high`, `growl`) beside `within_track` / `library_scaled`
/ `coverage` / `body_basis` (§2 facet publication) — they were already computed
per window and until now discarded; they are RECORDED on the grade and in the
ANLZ payload, and the per-deck status block projects them off (it surfaces only
`beat` / `within_track` / `library_scaled`).

Four-terms-or-omit law (5f): if ANY of the four normalisers is absent, non-finite,
or ≤ 0 — the in-module `fluxsum_midhigh` p90, `growl_timbre_p90`, the in-module
`perc_high` p90, or the body basis — that drop is omitted. `within_track` is
ALWAYS a mean over exactly
four terms or the drop does not exist; it is NEVER a re-weighted mean over fewer.
`score_windows` is the ONE implementation of the term math — `grade_drops` wraps
it and the report tool / G7 reuse it, so no second copy of the formula can drift.

Three properties of the rank `body` term the reader must not misread as absolute:
1. The ranking population is the RAW ANLZ marker set (`data.drop_beat_indices`),
   NOT the true drops. Measured 3,335 raw graded windows; 1,659 SMART drops attach
   (50.3% of the ranking population never attaches); the runway-filtered TRUE drops
   the presentation layer keys off number 1,243 (62.7% of the ranking population
   never reaches a surface). (1,659 was previously mislabeled here as "surfaced true
   drops" — it is the SMART-drop count.) So the term means "how this
   moment ranks among ALL of this track's raw Rekordbox drop markers", and it
   MOVES if Rekordbox re-analysis adds/removes a marker anywhere in the track. A
   deliberate choice (the raw set is the stable, complete, tick-independent
   population; ranking against the plan-selected subset would make the grade depend
   on smart-drop selection), recorded so it is not silent.
2. On a track with exactly 2 gradeable drops the mid-rank can only be `{0.25,
   0.75}` (measured 6.2% of tracks). The rank is doing what a rank does with n=2.
3. Exact within-track level ties (measured 3.0% of levels) share a value via the
   mid-rank definition `(less + 0.5·equal)/n`, never ordered arbitrarily.
4. The LEVEL DEFINITION under the rank is itself unstable (AWR-291 §6 item 11):
   median within-track drop-level spread is 1.27 dB ≈ 13 storage quanta (0.1 dB),
   and the rank is not stable across defensible level definitions — the raw-vs-true
   basis alone measures rho +0.7426 with median |Δ| 0.125. Level is signal-exhausted
   inside drops, so the rank is honest about ORDER, not about margins.

Gain-invariant by construction in exact arithmetic. In the shipped pipeline the
cancellation is exact to about ±0.005 grade units, because every stored dB value
is rounded to 0.1 dB (`audio_spectral_features.py:307-311`); and it does not hold
at all on beats pinned at the fixed −100.0 dB power floor (`:35`, `:313-314`),
which occurs on ~19% of BY GENRE tracks. Verified by re-extraction at two gains,
not by adding an offset to cached values (`tools/energy_perturbation_check.py`).
That invariance is exact about LEVEL and SILENT ABOUT SPECTRUM: a mastering EQ tilt
moves E1's `brightness_med` (measured dose-response, E1SCRAMBLE §10), and the measured
mastering leak is a median +0.044 weight (p90 ~0.11) — which reaches `library_scaled`
through the track weight — so "level-invariant" must never be read as
"mastering-immune".

True-drop law: this module grades whatever raw-marker beats it is handed — the
ATTACHMENT to plan decisions (`grades_by_beat` + `plan_track`) and every surface
key off plan-selected true drops only; raw-marker grades are attach material,
never surfaced. `body_basis` is recorded on every grade but never surfaced.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

# ---- pinned constants (a spec amendment moves any of these, never the impl) --
DROP_WINDOW_BEATS = 16          # drop_window_vector's own width convention
MIN_WINDOW_BEATS = 8            # thinner coverage ⇒ that drop ungraded (omitted)
COVERAGE_GATE = 0.95            # G1 (Part D)
TERM_SATURATION_MAX = 0.20      # G2: worst single term's railed fraction
TERM_CORRELATION_MAX = 0.60     # G3: worst |rho| between any two terms
IQR_GATE = 0.10                 # G4 (raised from v1's 0.05)
RANKABILITY_GATE = 0.90         # G5: tracks whose graded drops differ
LEVEL_SEPARATION_DB = 3.0       # G6: dB sanity check on the window indexing
GRADE_SEPARATION_GATE = 0.10    # G7: the composite must out-grade breakdowns
MIN_ACCEPT_N = 100              # E1/E2 floor


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _all_finite(xs) -> bool:
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def _finite_pos(x) -> "Optional[float]":
    """x as a finite float > 0, else None. A required normaliser that is absent,
    non-finite, or ≤ 0 omits the drop (the four-terms-or-omit law, 5f)."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if (math.isfinite(f) and f > 0.0) else None


def _percentile(sorted_values: "Sequence[float]", q: float) -> "Optional[float]":
    """Local linear-interpolation percentile (q in [0,100]). Reimplemented here on
    purpose — importing spectral_profile would couple this runtime module to it."""
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


def _mid_rank(sorted_levels: "Sequence[float]", value: float) -> float:
    """Mid-rank percentile in [0,1]: (count_less + 0.5*count_equal) / n. The same
    definition proven in track_weight_v0.rank_in, reimplemented locally because
    drop_energy_v0 must NOT import that root module (it is outside the E3 fence and
    the dependency direction would be backwards). An empty pool is a PROGRAMMING
    error (callers guarantee n ≥ 1) -> ValueError."""
    n = len(sorted_levels)
    if n == 0:
        raise ValueError("_mid_rank called with an empty distribution")
    less = sum(1 for x in sorted_levels if x < value)
    equal = sum(1 for x in sorted_levels if x == value)
    return (less + 0.5 * equal) / n


def _finite_ref(v4) -> "Optional[float]":
    scalars = getattr(v4, "scalars", None) or {}
    ref = scalars.get("loudness_ref_db")
    if ref is None:
        return None
    try:
        ref = float(ref)
    except (TypeError, ValueError):
        return None
    return ref if math.isfinite(ref) else None


def drop_body_levels(v4, drop_beats) -> "list[float]":
    """Per drop with window coverage >= MIN_WINDOW_BEATS: the window's mean full_db
    minus the track's own loudness_ref_db, in dB. The ONE implementation of this
    window convention - tools/track_weight_report.py imports it rather than
    reimplementing it, so the corpus fallback distribution ranks exactly the same
    quantity the primary term does. [] on absent / short / non-finite data."""
    ref = _finite_ref(v4)
    if ref is None:
        return []
    series = getattr(v4, "series", None) or {}
    full = series.get("full_db")
    if not full:
        return []
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0 or len(full) < n:
        return []
    out: "list[float]" = []
    for raw in drop_beats:
        beat = int(raw)
        s = max(0, beat)
        e = min(n, beat + DROP_WINDOW_BEATS)
        coverage = e - s
        if coverage < MIN_WINDOW_BEATS:
            continue
        fw = full[s:e]
        if not _all_finite(fw):
            continue
        out.append((sum(fw) / coverage) - ref)
    return out


def _track_normalisers(v4) -> "Optional[tuple]":
    """(fluxsum_p90, growl_timbre_p90, perc_high_p90) as finite positives, or None
    if ANY is unusable — the four-terms-or-omit law applies at the track level.
    `onset_mh_p90` is RETIRED from the required set (R4): the fluxsum p90 and the
    perc_high p90 have no cached scalar, so each is computed in-module over the
    track's own n_beats (one sorted() on the ANLZ worker thread, never the push
    loop) — the fluxsum p90 exactly the way the perc_high p90 always was."""
    scalars = getattr(v4, "scalars", None) or {}
    growl_p90 = _finite_pos(scalars.get("growl_timbre_p90"))
    if growl_p90 is None:
        return None
    series = getattr(v4, "series", None) or {}
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0:
        return None
    flux = series.get("fluxsum_midhigh")
    if not flux or len(flux) < n:
        return None
    fb = flux[:n]
    if not _all_finite(fb):
        return None
    flux_p90 = _finite_pos(_percentile(sorted(fb), 90))
    if flux_p90 is None:
        return None
    perc = series.get("perc_high")
    if not perc or len(perc) < n:
        return None
    pb = perc[:n]
    if not _all_finite(pb):
        return None
    perc_p90 = _finite_pos(_percentile(sorted(pb), 90))
    if perc_p90 is None:
        return None
    return (flux_p90, growl_p90, perc_p90)


def score_windows(v4, window_beats, *, body_pool) -> "list[dict]":
    """Per window with coverage >= MIN_WINDOW_BEATS and all-finite data: a dict
    {"beat", "coverage", "body", "activity", "perc_high", "growl", "within_track"}.
    `body_pool` is the rank basis the body term ranks against (the track's own drop
    levels, or the corpus distribution) — it is sorted here. Returns [] if the
    track's loudness_ref_db, any of the three normalisers (the in-module
    fluxsum/perc_high p90s or the cached growl p90), or the body_pool is unusable
    (four-terms-or-omit). This is the ONE copy of the E3 term math: grade_drops
    wraps it and the report / G7 reuse it so no formula drifts."""
    if not body_pool:
        return []
    ref = _finite_ref(v4)
    if ref is None:
        return []
    norms = _track_normalisers(v4)
    if norms is None:
        return []
    flux_p90, growl_p90, perc_p90 = norms
    series = getattr(v4, "series", None) or {}
    full = series.get("full_db")
    flux = series.get("fluxsum_midhigh")
    perc = series.get("perc_high")
    growl = series.get("growl_flatness")
    if not full or not flux or not perc or not growl:
        return []
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0 or min(len(full), len(flux), len(perc), len(growl)) < n:
        return []
    pool = sorted(body_pool)
    out: "list[dict]" = []
    for raw in window_beats:
        beat = int(raw)
        s = max(0, beat)
        e = min(n, beat + DROP_WINDOW_BEATS)
        coverage = e - s
        if coverage < MIN_WINDOW_BEATS:
            continue
        fw, xw, pw, gw = full[s:e], flux[s:e], perc[s:e], growl[s:e]
        if not (_all_finite(fw) and _all_finite(xw)
                and _all_finite(pw) and _all_finite(gw)):
            continue
        level = (sum(fw) / coverage) - ref
        body = _mid_rank(pool, level)
        activity_term = _clip01((sum(xw) / coverage) / flux_p90)
        perc_term = _clip01((sum(pw) / coverage) / perc_p90)
        growl_term = _clip01((sum(gw) / coverage) / growl_p90)
        within = (body + activity_term + perc_term + growl_term) / 4.0
        out.append({"beat": beat, "coverage": coverage, "body": body,
                    "activity": activity_term, "perc_high": perc_term,
                    "growl": growl_term, "within_track": within})
    return out


def _corpus_pool(corpus_drop_levels) -> "list[float]":
    """The corpus fallback distribution as finite floats, or [] if unusable."""
    if not corpus_drop_levels:
        return []
    out: "list[float]" = []
    for x in corpus_drop_levels:
        try:
            f = float(x)
        except (TypeError, ValueError):
            return []
        if not math.isfinite(f):
            return []
        out.append(f)
    return out


def grade_drops(v4, *, drop_beats, track_weight: "Optional[float]",
                corpus_drop_levels: "Optional[Sequence[float]]" = None
                ) -> "list[dict]":
    """Per raw drop beat with window coverage ≥ MIN_WINDOW_BEATS: the four-term
    grade, or [] on missing/non-finite `loudness_ref_db`, absent/short series, any
    unusable normaliser, or no usable body basis. Never a fabricated grade (a thin
    or non-finite window, or a track that cannot supply all four terms, is
    omitted). The body basis is chosen once per track: `track_drops` when the track
    has ≥2 of its own gradeable drop levels, else `corpus` when the passed
    distribution is usable, else the whole track is ungraded."""
    own_levels = drop_body_levels(v4, drop_beats)
    if len(own_levels) >= 2:
        body_basis, pool = "track_drops", own_levels
    else:
        corpus_pool = _corpus_pool(corpus_drop_levels)
        if corpus_pool:
            body_basis, pool = "corpus", corpus_pool
        else:
            return []
    out: "list[dict]" = []
    for row in score_windows(v4, drop_beats, body_pool=pool):
        within = row["within_track"]
        lib = (within * track_weight
               if isinstance(track_weight, (int, float))
               and math.isfinite(track_weight) else None)
        # §2 facet publication: carry the four term values (already computed by
        # score_windows one line before the mean, and until now discarded)
        # through onto the grade dict, beside within_track/library_scaled/
        # coverage/body_basis. body_basis is the E3 basis record; no new basis.
        out.append({"drop_beat": row["beat"], "within_track": within,
                    "library_scaled": lib, "coverage": row["coverage"],
                    "body_basis": body_basis,
                    "body": row["body"], "activity": row["activity"],
                    "perc_high": row["perc_high"], "growl": row["growl"]})
    return out


def grades_by_beat(grades: "list[dict]") -> "dict[int, dict]":
    """Attach lookup: raw drop beat (int) → grade dict."""
    return {int(g["drop_beat"]): g for g in grades}


def gates_verdict(n_by_genre_eligible: int, n_graded: int,
                  term_railed_max: "Optional[float]",
                  term_rho_max: "Optional[float]",
                  iqr: "Optional[float]",
                  rankable_fraction: "Optional[float]",
                  level_separation_db: "Optional[float]",
                  grade_separation: "Optional[float]") -> "tuple[bool, str]":
    """Offline verdict. Precedence: corpus floor → G1 coverage → G2 term saturation
    → G3 term correlation → G4 composite IQR → G5 rankability → G6 level separation
    → G7 grade separation. `n_by_genre_eligible` = by_genre tracks with a v4 entry
    AND an accepted-store row AND ≥1 ANLZ drop marker; G1 polices window / grade
    holes only. Every None fails closed."""
    if n_by_genre_eligible < MIN_ACCEPT_N:
        return (False, "insufficient_corpus")
    if n_graded / n_by_genre_eligible < COVERAGE_GATE:
        return (False, "insufficient_coverage")
    if term_railed_max is None or term_railed_max > TERM_SATURATION_MAX:
        return (False, "saturated_term")
    if term_rho_max is None or term_rho_max > TERM_CORRELATION_MAX:
        return (False, "redundant_terms")
    if iqr is None or iqr < IQR_GATE:
        return (False, "degenerate_distribution")
    if rankable_fraction is None or rankable_fraction < RANKABILITY_GATE:
        return (False, "unrankable_grades")
    if level_separation_db is None or level_separation_db < LEVEL_SEPARATION_DB:
        return (False, "inverted_level_separation")
    if grade_separation is None or grade_separation < GRADE_SEPARATION_GATE:
        return (False, "inverted_or_flat_grade_separation")
    return (True, "ok")
