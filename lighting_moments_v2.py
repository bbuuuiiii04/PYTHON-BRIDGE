#!/usr/bin/env python3
"""LIGHTING ENGINE v2 — Feature 2 rule engine (AWR-163): the pure moment brain.

Turns the calibrated v4 spectral analysis into per-drop moment decisions: drop
family, intensity tier, the quantized emphasis-blackout ladder, true-stop class,
white-share, animation rung, bass-forward pattern, simmer/euphoric eligibility,
and build-move selection. Every function here is PURE over already-cached v4
series + Rekordbox marker lists — no I/O, no re-analysis, no runtime side effects
(design authority: LIGHTING_ENGINE_V2_DESIGN.md §4.1 "no re-analysis, ever").

Analysis DESCRIBES sound; markers stay authoritative for WHEN a cue fires. This
module chooses *dressing*, never timing.

Provenance of the rules:
  * Family classifier      — design D§3.1 (verbatim; ported from the shipped
                             read-only report tool, code-verified).
  * Intensity tier         — design D§3.2, the CURRENT corpus-absolute grading
                             (frozen cuts p55=0.616 / p85=0.698). The AWR-147
                             desk pass flagged this scorer "on notice" (6
                             known under-/over-reads clustering on
                             hard-techno / big-room / older masters). The
                             family-percentile REDESIGN was evaluated against
                             the corpus and REJECTED — it satisfied 0 of its 5
                             acceptance fixtures and broke two validated reads
                             (see docs registry AWR-163). The redesign
                             hypothesis of record is era/loudness normalisation
                             (C§6d); NOT implemented here. Ships on the current
                             tier by executive ruling 2026-07-09.
  * Darkness ladder        — calibration C§6f FINAL LADDER (the 41-verdict desk
                             pass) REPLACES D§4.1's `gap=min(raw_gap,16)` sizing.
                             *** TIER-INDEPENDENT BY CONTRACT (executive ruling
                             condition 4): the 16-beat rung keys on FAMILY-GRADE
                             (WALL/COMET = hard) + collapse length, and true-stop
                             keys on percussion content. No tier value is read
                             anywhere in the ladder. ***
  * The rest (white-share, rung, bass-forward, simmer, euphoric, build-move) —
    design D§5 / D§9, pinned formulas.

The `reason` string on every decision is the D§12 observability contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from . import spectral_profile
from .audio_spectral_features import SpectralFeaturesV4

_pct = spectral_profile.percentile


# --------------------------------------------------------------------------- #
# Named constants (every threshold lives here — D§12 / repo constant hygiene).  #
# --------------------------------------------------------------------------- #

# --- Family classifier (D§3.1) ---
FAM_COVERAGE_MIN = 8
FAM_NEUTRAL_LIFT = -7.0
FAM_NEUTRAL_ATTACK = 5.0
FAM_COMET_BPM = 146.0
FAM_COMET_AIR_MAX = 0.0
FAM_COMET_SUB_MIN = 24.0
FAM_COMET_ONSET_MAX = 3.2
FAM_WALL_GROWL_FLAT = 0.27
FAM_WALL_HIGH = 4.0
FAM_WALL_MID = 8.0
FAM_WALL_TRAP_SUB = 26.0
FAM_WALL_TRAP_ONSET_MAX = 2.2
FAM_WALL_DENSE_ONSET = 3.4
FAM_WALL_DENSE_HIGH = 5.0
FAM_HOUSE_BPM_LO = 116.0
FAM_HOUSE_BPM_HI = 144.0
FAM_HOUSE_STAB_SWING = 10.5
FAM_HOUSE_STAB_ATTACK = 7.0
FAM_HOUSE_GROWL_FLAT_MAX = 0.24
FAM_HOUSE_GROWL_SUB = 20.0
FAM_HOUSE_GROWL_BASS = 14.0

# Family "hardness grade" — the ONLY family signal the darkness ladder reads.
# WALL (distorted / trap monster) and COMET (fast dark pounding) ARE the
# "hard/dark monster" classes by design (D§3); HOUSE/NEUTRAL are soft.
HARD_FAMILIES = frozenset({"WALL", "COMET"})

# --- Intensity tier (D§3.2, CURRENT corpus-absolute — frozen) ---
TIER_P55 = 0.616   # frozen corpus p55 → tier 2
TIER_P85 = 0.698   # frozen corpus p85 → tier 3
# Track-start damping (A.2b / AWR-139 runway): a drop closer than this many beats
# to track start caps at tier 1 unless hotcue-tagged. Damping only lowers tiers.
TIER_RUNWAY_BEATS = 64

# --- Floor / gone-run scan (D§4.1 steps 1-2) ---
GONE_SUB_DB = 5.0          # sub-only "floor gone" threshold (bimodal valley)
PICKUP_TOLERANCE = 4       # newest gone beat sought in [D-4, D-1]
FLOOR_PRESENT_DB = 5.0     # sub present again

# --- Darkness ladder (C§6f) — QUANTIZED, TIER-INDEPENDENT ---
QUANTIZED_RUNGS = (1, 2, 4, 8, 16)
BALLOON_PERC_BOUNDARY = 0.35   # build-window perc_full < this → balloon-shrink,
                               # not black (melodic swell). Gray zone 0.30-0.40
                               # defaults to black (>=0.35); pinned per A.3.
COLLAPSE_GAP = 16              # a true collapse = a sub-only run this long. 16
                               # fires ONLY for hard family (WALL/COMET) over a
                               # collapse this deep; melodic/mainstage never 16.
BUSY_DUTY = 0.85              # bass_duty above this = drums driving the build
DRIVING_PERC = 0.55          # OR build perc_full above this = driving → 4-black
SOFT_GROOVE_MAX = 2          # soft family, music-runs-straight-in → 1-2 beats
ABORT_RUN = 2                # darkness ends at the 2nd consecutive present beat

# --- True-stop class (C§6f: percussion done + vocals/effects only) ---
STOP_PERC_MAX = 0.15         # med(perc_full[window]) <= this
STOP_LIFT_FLOOR = -10.0      # AND med(full_db[window]) >= ref - 10 (still audible)
STOP_WIDTH = 16

# --- Relative dip (D§4.1 step 5, TUNE-LIVE) ---
DIP_SCORE_FIRE = 4.0
DIP_SUB_ASSIST = 0.25
DIP_CAP_BEATS = 4

# --- Perc-cut flick upgrade (D§4.1 step 6) ---
PERC_CUT_DROP_DB = 5.0       # growl_band[D-1] <= growl_band[D-2] - 5 → 1-beat cut

# --- White share (D§5.2, TUNE-LIVE) ---
WHITE_BUILD_CAP = 64
WHITE_FLUX_SCALE = 40.0
WHITE_LEVEL_SCALE = 6.0
WHITE_BASE = 0.25
WHITE_SPAN = 0.75
WHITE_MIN = 0.15
WHITE_MAX = 1.0

# --- Bass-forward (D§5.1) ---
BF_CEIL_MARGIN = 3.0
BF_BASS_MIN = 18.0
BF_KICK_ATTACK = 9.0

# --- Animation rung (D§5.3) ---
RUNG_QUIET_SIMMER = 4
RUNG_QUIET_SPARSE = 2
RUNG_QUIET_SPARSE_ATTACK = 6.0
RUNG_T3_BPM_LO = 113.0       # 0.25 rung only where BPM<=113 or |BPM-150|<=2,
RUNG_T3_ALIAS_HZ = 150.0     # else it aliases against the 30fps frame clock
RUNG_T3_ALIAS_TOL = 2.0

# --- Simmer (D§5.4) ---
SIMMER_ATTACK_MAX = 2.5
SIMMER_ONSET_MAX = 0.5

# --- Euphoric (D§5.5) ---
EUPHORIC_MIN_RUN = 8

# --- Build move (D§9) — selection thresholds over corpus-normalised axes ---
MOVE_SQUEEZE_PUNCH = 0.60
MOVE_SQUEEZE_ATTACK = 0.45
MOVE_FUSE_ONSET = 0.5
MOVE_FUSE_SWING_DB = 10.0


# --------------------------------------------------------------------------- #
# Small helpers                                                                #
# --------------------------------------------------------------------------- #
def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _median(xs: Sequence[float]) -> float:
    return _pct(list(xs), 50.0) if xs else 0.0


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _quantize_down(x: float) -> int:
    """Largest quantized rung <= x (>=1). The measured gap caps here."""
    best = QUANTIZED_RUNGS[0]
    for r in QUANTIZED_RUNGS:
        if r <= x:
            best = r
    return best


def family_grade(family: str) -> str:
    """'hard' for WALL/COMET (the monster classes), 'soft' otherwise.
    The ONLY family fact the darkness ladder is allowed to read."""
    return "hard" if family in HARD_FAMILIES else "soft"


# --------------------------------------------------------------------------- #
# Family classifier (D§3.1 — verbatim)                                         #
# --------------------------------------------------------------------------- #
def classify_family(vec: dict[str, float], lift: float, raw_gap: float) -> str:
    """§3.1 family classifier; first match wins. Descriptors, never genres."""
    if vec.get("coverage", 0.0) < FAM_COVERAGE_MIN:
        return "NEUTRAL"
    if lift < FAM_NEUTRAL_LIFT and vec["attack_low_p90"] < FAM_NEUTRAL_ATTACK:
        return "NEUTRAL"
    bpm = vec["bpm"]
    if (bpm >= FAM_COMET_BPM and vec["air_db"] < FAM_COMET_AIR_MAX
            and vec["sub_db"] >= FAM_COMET_SUB_MIN
            and vec["onset_density_mh"] <= FAM_COMET_ONSET_MAX):
        return "COMET"
    if (vec["growl_flatness"] >= FAM_WALL_GROWL_FLAT
            and (vec["high_db"] >= FAM_WALL_HIGH or vec["mid_db"] >= FAM_WALL_MID)):
        return "WALL"
    if (vec["sub_db"] >= FAM_WALL_TRAP_SUB
            and vec["onset_density_mh"] <= FAM_WALL_TRAP_ONSET_MAX and raw_gap >= 1):
        return "WALL"
    if vec["onset_density_mh"] >= FAM_WALL_DENSE_ONSET and vec["high_db"] >= FAM_WALL_DENSE_HIGH:
        return "WALL"
    if FAM_HOUSE_BPM_LO <= bpm <= FAM_HOUSE_BPM_HI:
        if vec["low_swing_db"] >= FAM_HOUSE_STAB_SWING and vec["attack_low_p90"] >= FAM_HOUSE_STAB_ATTACK:
            return "HOUSE"
        if (vec["growl_flatness"] < FAM_HOUSE_GROWL_FLAT_MAX and vec["sub_db"] >= FAM_HOUSE_GROWL_SUB
                and vec["low_swing_db"] < FAM_HOUSE_STAB_SWING and vec["bass_db"] >= FAM_HOUSE_GROWL_BASS):
            return "HOUSE"
    return "NEUTRAL"


# --------------------------------------------------------------------------- #
# Intensity tier (D§3.2 — CURRENT corpus-absolute; see module note)           #
# --------------------------------------------------------------------------- #
def violence_score(vec: dict[str, float], lift: float, raw_gap: float) -> float:
    """§3.2 violence score (corpus-absolute)."""
    return (0.30 * _clip01((vec["full_db"] - 8) / 10)
            + 0.20 * _clip01((lift + 4) / 5)
            + 0.25 * _clip01(vec["attack_low_p90"] / 16)
            + 0.15 * _clip01(vec["onset_density_mh"] / 4)
            + 0.10 * _clip01(raw_gap / 8))


def violence_tier(vec: dict[str, float], lift: float, raw_gap: float) -> tuple[float, int]:
    """§3.2 → (violence, tier) with the FROZEN corpus-absolute cuts.

    ponytail: NOT the family-percentile redesign — that was measured against the
    corpus and failed 0/5 of its own fixtures (docs AWR-163). Current tier ships;
    era/loudness-normalised redesign is the open hypothesis.
    """
    v = violence_score(vec, lift, raw_gap)
    tier = 3 if v >= TIER_P85 else 2 if v >= TIER_P55 else 1
    return v, tier


def damp_track_start(tier: int, drop_beat: int, hotcue_tagged: bool = False) -> int:
    """A.2b track-start damping (mirrors AWR-139 runway): a drop within
    TIER_RUNWAY_BEATS of track start caps at tier 1 unless hotcue-tagged.
    Damping only ever LOWERS a tier."""
    if hotcue_tagged:
        return tier
    if drop_beat < TIER_RUNWAY_BEATS:
        return min(tier, 1)
    return tier


def tier_name(tier: int) -> str:
    """Laser/energy vocabulary (AWR-162): tier 1/2/3 → standard/intense/monster;
    a family-NEUTRAL or damped-thin drop is 'small' (handled by the consumer)."""
    return {1: "standard", 2: "intense", 3: "monster"}.get(tier, "standard")


# --------------------------------------------------------------------------- #
# Gone-run scan / dip / true-stop (D§4.1 inputs; C§6f true-stop)              #
# --------------------------------------------------------------------------- #
def tolerant_scan(v4: SpectralFeaturesV4, drop: int) -> Optional[tuple[int, int, int, float]]:
    """D§4.1 steps 1-2: newest sub-only-gone beat e in [D-4, D-1], the run start,
    raw_gap, and the run's bass_duty. None when no gone beat sits in the pickup
    window (music runs straight in with no emptiness)."""
    sub = v4.series["sub_db"]
    bass = v4.series["bass_db"]
    n = v4.n_beats
    lo = max(0, drop - PICKUP_TOLERANCE)
    hi = min(n - 1, drop - 1)
    e = None
    for i in range(hi, lo - 1, -1):
        if sub[i] < GONE_SUB_DB:
            e = i
            break
    if e is None:
        return None
    start = e
    while start - 1 >= 0 and sub[start - 1] < GONE_SUB_DB:
        start -= 1
    raw_gap = e - start + 1
    bass_duty = sum(1 for i in range(start, e + 1) if bass[i] >= 8.0) / raw_gap
    return e, start, raw_gap, bass_duty


def _dip_score(v4: SpectralFeaturesV4, b: int) -> float:
    """D§4.1 step 5 dip_score(b)."""
    full = v4.series["full_db"]
    sub = v4.series["sub_db"]
    lo = max(0, b - 16)
    prev_full = full[lo:b]
    prev_sub = sub[lo:b]
    if not prev_full:
        return 0.0
    term1 = _pct(prev_full, 50.0) - full[b]
    term2 = DIP_SUB_ASSIST * max(0.0, min(8.0, _pct(prev_sub, 50.0) - sub[b]))
    return term1 + term2


def _build_window(drop: int, buildup_beat: Optional[int], run_start: int) -> int:
    """Low edge of the pre-drop build window (buildup marker → drop). Falls back
    to the emptiness-run start, then a 16-beat lookback, when no buildup marker."""
    if buildup_beat is not None and 0 <= buildup_beat < drop:
        lo = buildup_beat
    else:
        lo = min(run_start, drop - 16)
    return max(0, lo)


def _build_medians(v4: SpectralFeaturesV4, lo: int, drop: int) -> tuple[float, float]:
    """(median perc_full, median lift) over the pre-drop build window [lo, drop)."""
    perc = v4.series["perc_full"][lo:drop]
    full = v4.series["full_db"][lo:drop]
    ref = float(v4.scalars.get("loudness_ref_db", 0.0))
    return _median(perc), (_median(full) - ref if full else -99.0)


def true_stop(v4: SpectralFeaturesV4, drop: int, *, buildup_beat: Optional[int] = None,
              run_start: Optional[int] = None) -> bool:
    """C§6f 'true stop': percussion done, vocals/effects only, but STILL AUDIBLE.
    Pre-drop window (A.3 'pre-window percussion gone'). This audibility floor is
    exactly what separates a true stop (Cruel Summer → 8-beat black) from a
    melodic balloon swell (Caramelle −14 dB → shrink)."""
    lo = _build_window(drop, buildup_beat, run_start if run_start is not None else drop - 16)
    perc_build, lift_build = _build_medians(v4, lo, drop)
    return perc_build <= STOP_PERC_MAX and lift_build >= STOP_LIFT_FLOOR


# --------------------------------------------------------------------------- #
# THE DARKNESS LADDER (C§6f) — quantized emphasis, TIER-INDEPENDENT            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DarknessDecision:
    kind: str                       # blackout | balloon | dip | perc-flick | snap
    beats: int                      # rendered dark/shrink beats (0 for a bare flick)
    window: Optional[tuple[int, int]]  # [start, drop) in beats, or None
    abort_at: Optional[int]         # floor-returned early release beat, or None
    cap_inputs: dict[str, Any]      # raw_gap / bass_duty / perc_build / grade / stop
    reason: str


def _abort(v4: SpectralFeaturesV4, drop: int, beats: int) -> tuple[Optional[int], int]:
    """Floor-returned abort (D§4.1 step 4 / OLC-B): darkness ends at the 2nd
    consecutive present beat inside the window. A lone pickup present beat stays
    dark; floor back at entry renders zero dark beats."""
    sub = v4.series["sub_db"]
    n = v4.n_beats
    w_start = drop - beats

    def present(i: int) -> bool:
        return 0 <= i < n and sub[i] >= FLOOR_PRESENT_DB

    for bb in range(w_start, drop - 1):
        if present(bb) and present(bb + 1):
            return bb, bb - w_start
    return None, beats


def darkness_ladder(v4: SpectralFeaturesV4, drop: int, family: str,
                    buildup_beat: Optional[int] = None) -> DarknessDecision:
    """C§6f FINAL LADDER. Returns the pre-drop darkness decision.

    *** EXECUTIVE CONDITION 4 — TIER-INDEPENDENT ***
    The blackout LENGTH is drop EMPHASIS, keyed on:
      family_grade (hard=WALL/COMET vs soft) · true-stop (percussion content) ·
      collapse length (raw_gap) · build perc_full (balloon split) · bass_duty.
    NO intensity-tier value is read anywhere below. The 16-beat rung fires ONLY
    for a hard/dark monster (WALL/COMET) over a genuine collapse; a soft-family
    drop never earns 16 regardless of how deep/quiet it measures.
    """
    n = v4.n_beats
    growl = v4.series["growl_band_db"]
    scan = tolerant_scan(v4, drop)

    if scan is None:
        # No emptiness in the pickup window → dip / snap / perc-cut flick (D§4.1 5-6).
        dip_fires = any(
            _dip_score(v4, b) >= DIP_SCORE_FIRE and v4.series["sub_db"][b] >= FLOOR_PRESENT_DB
            for b in range(max(0, drop - PICKUP_TOLERANCE), min(n, drop))
        )
        if dip_fires:
            return DarknessDecision("dip", DIP_CAP_BEATS, None, None,
                                    {"grade": family_grade(family)},
                                    "relative dip: full-band ducked, floor present")
        perc = drop >= 2 and growl[drop - 1] <= growl[drop - 2] - PERC_CUT_DROP_DB
        if perc:
            return DarknessDecision("perc-flick", 1, (drop - 1, drop), None,
                                    {"grade": family_grade(family)},
                                    "perc-cut flick: measured percussive cut before the marker")
        return DarknessDecision("snap", 0, None, None, {"grade": family_grade(family)},
                                "snap-to-black flick: music slams straight in")

    e, run_start, raw_gap, bass_duty = scan
    lo = _build_window(drop, buildup_beat, run_start)
    perc_build, lift_build = _build_medians(v4, lo, drop)
    grade = family_grade(family)
    # A true stop = percussion done AND still audible (vocals/effects). This
    # audibility floor is what tells a stop (→ 8) from a melodic swell (→ balloon).
    stop = perc_build <= STOP_PERC_MAX and lift_build >= STOP_LIFT_FLOOR

    # 1) BALLOON — melodic swell (low build percussion, NOT an audible vocal stop)
    #    shrinks instead of blacking, even into a hard drop (Stereo Love), so this
    #    is checked BEFORE the hard-16 branch.
    if perc_build < BALLOON_PERC_BOUNDARY and not stop:
        beats = _quantize_down(raw_gap)
        return DarknessDecision(
            "balloon", beats, (drop - beats, drop), None,
            {"raw_gap": raw_gap, "bass_duty": round(bass_duty, 3),
             "perc_build": round(perc_build, 3), "grade": grade, "stop": False},
            f"balloon-shrink: melodic build (perc {perc_build:.2f} < {BALLOON_PERC_BOUNDARY})")

    # 2) BLACK — quantized emphasis length, TIER-INDEPENDENT.
    if stop:
        emphasis, why = 8, "true stop: percussion done, vocals/effects only"
    elif grade == "hard" and raw_gap >= COLLAPSE_GAP:
        emphasis, why = 16, "true collapse into a hard/dark monster (WALL/COMET)"
    elif grade == "hard":
        emphasis, why = 4, "hard drop, short pickup emphasis"
    else:
        driving = bass_duty > BUSY_DUTY or perc_build >= DRIVING_PERC
        if driving:
            emphasis, why = 4, "soft build, drums driving → default emphasis"
        else:
            emphasis, why = SOFT_GROOVE_MAX, "groove / music runs straight in"

    beats = _quantize_down(min(emphasis, raw_gap))   # measured gap CAPS the length
    abort_at, dark_beats = _abort(v4, drop, beats)
    return DarknessDecision(
        "blackout", beats, (drop - beats, drop), abort_at,
        {"raw_gap": raw_gap, "bass_duty": round(bass_duty, 3),
         "perc_build": round(perc_build, 3), "grade": grade, "stop": stop,
         "emphasis": emphasis, "dark_beats": dark_beats},
        f"blackout {beats}: {why}"
        + (f" (capped by gap {raw_gap})" if raw_gap < emphasis else "")
        + (f"; abort@{abort_at}" if abort_at is not None else ""))


# --------------------------------------------------------------------------- #
# White share (D§5.2)                                                          #
# --------------------------------------------------------------------------- #
def white_share(v4: SpectralFeaturesV4, buildup_beat: int, drop_beat: int) -> tuple[float, str]:
    """D§5.2: the build's measured energy sets the white mix at the top."""
    lo = max(0, min(buildup_beat, drop_beat))
    hi = min(v4.n_beats, drop_beat)
    if hi - lo < 2:
        return WHITE_MIN, "white-share: build window too short → floor"
    lo = max(lo, hi - WHITE_BUILD_CAP)
    flux = v4.series["fluxsum_midhigh"][lo:hi]
    full = v4.series["full_db"][lo:hi]
    mid = len(flux) // 2
    flux_rise = _mean(flux[mid:]) - _mean(flux[:mid])
    level_rise = _median(full[mid:]) - _median(full[:mid])
    E = _clip01(0.5 * _clip01(flux_rise / WHITE_FLUX_SCALE)
                + 0.5 * _clip01(level_rise / WHITE_LEVEL_SCALE))
    share = max(WHITE_MIN, min(WHITE_MAX, WHITE_BASE + WHITE_SPAN * E))
    return share, f"white-share {share:.2f}: build energy E={E:.2f}"


# --------------------------------------------------------------------------- #
# Bass-forward pattern (D§5.1)                                                 #
# --------------------------------------------------------------------------- #
def bass_forward_pattern(v4: SpectralFeaturesV4, drop: int, width: int = 16) -> str:
    """D§5.1 per-beat B (bass-forward) / K (kick-driving) / . over the window."""
    n = v4.n_beats
    start = max(0, drop)
    end = min(n, start + width)
    gb = v4.series["growl_band_db"][start:end]
    ald = v4.series["attack_low_db"][start:end]
    if not gb:
        return ""
    ceil = _pct(gb, 90.0)
    out = []
    for g, a in zip(gb, ald):
        if a >= BF_KICK_ATTACK:
            out.append("K")
        elif g >= ceil - BF_CEIL_MARGIN and g >= BF_BASS_MIN:
            out.append("B")
        else:
            out.append(".")
    return "".join(out)


# --------------------------------------------------------------------------- #
# Animation rung (D§5.3)                                                       #
# --------------------------------------------------------------------------- #
def drop_rate_rung(tier: int, bpm: float) -> float:
    """D§5.3 drop rung: tier1→1, tier2→0.5, tier3→0.25 only where the 30fps
    frame clock can render it (BPM<=113 or |BPM-150|<=2), else 0.5 (alias guard).
    (Tier is a legitimate rung input — only the DARKNESS ladder is tier-free.)"""
    if tier <= 1:
        return 1.0
    if tier == 2:
        return 0.5
    if bpm <= RUNG_T3_BPM_LO or abs(bpm - RUNG_T3_ALIAS_HZ) <= RUNG_T3_ALIAS_TOL:
        return 0.25
    return 0.5


def section_rate_rung(section_tier: str, is_simmer: bool, med_attack_low: float) -> int:
    """D§5.3 section rung for atmospheric/groove sections."""
    if section_tier == "quiet":
        if is_simmer:
            return RUNG_QUIET_SIMMER
        return RUNG_QUIET_SPARSE if med_attack_low < RUNG_QUIET_SPARSE_ATTACK else 1
    return 1  # mid / loud → every beat (drop cues override with their own rung)


# --------------------------------------------------------------------------- #
# Simmer / euphoric eligibility (D§5.4 / D§5.5)                                #
# --------------------------------------------------------------------------- #
def is_simmer(v4: SpectralFeaturesV4, start: int, end: int) -> bool:
    """D§5.4: a percussion-free stretch reads as a low simmer (sparse-and-dim)."""
    end = min(end, v4.n_beats)
    if end <= start:
        return False
    attack = v4.series["attack_low_db"][start:end]
    onset = v4.series["onset_density_midhigh"][start:end]
    return _median(attack) < SIMMER_ATTACK_MAX and _median(onset) < SIMMER_ONSET_MAX


def euphoric_runs(sustained_synth_flags: Sequence[bool], min_run: int = EUPHORIC_MIN_RUN) -> bool:
    """D§5.5: euphoric-eligible when clean sustained-synth (source-agnostic; vocals
    count) runs >= min_run consecutive beats. Selection-only — schedules nothing."""
    run = 0
    for f in sustained_synth_flags:
        run = run + 1 if f else 0
        if run >= min_run:
            return True
    return False


# --------------------------------------------------------------------------- #
# Build-move selection (D§9)                                                   #
# --------------------------------------------------------------------------- #
def build_move(norm_punch: float, norm_attack_low_p90: float,
               norm_onset_mh_p90: float, low_swing_p50_db: float,
               balloon: bool = False) -> str:
    """D§9 per-track move from measured character. `balloon` (from the darkness
    ladder's balloon branch, A.6) is the fourth member and wins when set.
    norm_* are the corpus-normalised identity axes supplied by the caller."""
    if balloon:
        return "balloon"
    if norm_punch >= MOVE_SQUEEZE_PUNCH and norm_attack_low_p90 >= MOVE_SQUEEZE_ATTACK:
        return "squeeze-explode"
    if norm_onset_mh_p90 >= MOVE_FUSE_ONSET and low_swing_p50_db >= MOVE_FUSE_SWING_DB:
        return "fuse"
    return "swell"


# --------------------------------------------------------------------------- #
# Per-drop convenience: family + tier from a cached window                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DropDecision:
    drop_beat: int
    family: str
    violence: float
    tier: int              # damped, current corpus-absolute tier
    darkness: DarknessDecision
    bass_forward: str
    reason: str


def decide_drop(v4: SpectralFeaturesV4, drop: int, *, buildup_beat: Optional[int] = None,
                hotcue_tagged: bool = False) -> DropDecision:
    """Full per-drop decision over cached series. Pure; no timing side effects."""
    vec = spectral_profile.drop_window_vector(v4, drop, width=16)
    ref = float(v4.scalars.get("loudness_ref_db", 0.0))
    if not vec.get("coverage"):
        empty = DarknessDecision("snap", 0, None, None, {}, "thin window: no coverage")
        return DropDecision(drop, "NEUTRAL", 0.0, 1, empty, "", "thin window → NEUTRAL/T1")
    lift = vec["full_db"] - ref
    scan = tolerant_scan(v4, drop)
    raw_gap = scan[2] if scan is not None else 0
    fam = classify_family(vec, lift, raw_gap)
    viol, tier = violence_tier(vec, lift, raw_gap)
    tier = damp_track_start(tier, drop, hotcue_tagged)
    dark = darkness_ladder(v4, drop, fam, buildup_beat)
    bf = bass_forward_pattern(v4, drop)
    reason = f"{fam} T{tier} (v{viol:.3f}); {dark.reason}"
    return DropDecision(drop, fam, round(viol, 4), tier, dark, bf, reason)
