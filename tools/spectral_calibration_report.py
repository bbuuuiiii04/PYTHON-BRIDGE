#!/usr/bin/env python3
"""Re-runnable v4 spectral calibration report (read-only, offline).

Recomputes every corpus-scale calibration claim on the current v4 cache +
current Rekordbox markers, so a tuning decision rests on measured numbers, not
memory. Never writes a cache entry, never touches the DB / ANLZ / audio beyond
reads, never edits a threshold. It imports ``spectral_profile`` /
``spectral_cache`` / ``anlz_reader`` for all shipped math; the F2 rule pack
(family classifier, intensity tier, darkness decision, bass-forward) is
design-only (LIGHTING_ENGINE_V2_DESIGN.md §§3-5) and implemented here from the
pinned formulas — analysis DESCRIBES sound, it never times or triggers a cue.

    python3 tools/spectral_calibration_report.py \
        --json /tmp/awr147/report.json --markdown /tmp/awr147/report.md [--limit N]

Splits: ``library`` (all on-disk tracks with a v4 entry), ``by_genre`` (the
BY GENRE calibration set — the only split used for calibration *claims*), and
``new`` (tracks whose cache key is absent from ``--pre-sweep-keys`` — the
held-out drift check). BY GENRE = folder node 666898931's 25 child playlists,
RAP excluded, deduped by ContentID (contract ``spectral_analysis``).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache, spectral_profile  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import read_anlz_drops  # noqa: E402
from rb_ss_bridge_v2.audio_spectral_features import SpectralFeaturesV4  # noqa: E402

SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
DB_PATH = Path("~/Library/Pioneer/rekordbox/master.db").expanduser()
BY_GENRE_FOLDER_ID = "666898931"          # the 25-child folder (design doc App. A)
BY_GENRE_EXCLUDE = {"RAP"}                 # track-selection rule
DEFAULT_PRE_SWEEP_KEYS = "/tmp/awr147/pre_sweep_keys.txt"

pct = spectral_profile.percentile


# --------------------------------------------------------------------------- #
# Rekordbox enumeration (same read-only DB access as tools/spectral_sweep.py) #
# --------------------------------------------------------------------------- #
def _open_db() -> Any:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    return Rekordbox6Database(str(DB_PATH), unlock=True)


def _enumerate(db: Any) -> tuple[list[dict[str, str]], dict[str, set[str]]]:
    """On-disk active tracks + {content_id: {playlist names}} for BY GENRE."""
    genre_pls = [
        p for p in db.get_playlist()
        if str(getattr(p, "ParentID", "")) == BY_GENRE_FOLDER_ID
        and str(getattr(p, "Name", "")) not in BY_GENRE_EXCLUDE
    ]
    cid_playlists: dict[str, set[str]] = {}
    for pl in genre_pls:
        name = str(pl.Name)
        for row in db.get_playlist_songs(PlaylistID=str(pl.ID)):
            cid_playlists.setdefault(str(row.ContentID), set()).add(name)

    tracks: list[dict[str, str]] = []
    for c in db.get_content():
        if getattr(c, "rb_local_deleted", 0):
            continue
        filepath = str(c.FolderPath or "")
        if not filepath or not os.path.isfile(filepath):
            continue
        anlz_rel = str(getattr(c, "AnalysisDataPath", "") or "")
        anlz_abs = str(SHARE_ROOT / anlz_rel.lstrip("/")) if anlz_rel else ""
        tracks.append({
            "content_id": str(c.ID),
            "title": str(c.Title or ""),
            "filepath": filepath,
            "anlz_abs": anlz_abs,
        })
    tracks.sort(key=lambda t: t["content_id"])
    return tracks, cid_playlists


# --------------------------------------------------------------------------- #
# F2 rule pack — design-only formulas (LIGHTING_ENGINE_V2_DESIGN.md §§3-5).    #
# Verbatim from the pins in the AWR-147 phase-1 task file; see module docstring.#
# --------------------------------------------------------------------------- #
def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def tolerant_scan(v4: SpectralFeaturesV4, drop: int) -> Optional[tuple[int, int, int, float]]:
    """§4.1 steps 1-3: newest sub-only-gone beat e in [D-4, D-1], run start, raw_gap,
    and the run's bass_duty. Returns None when no gone beat sits in the pickup window."""
    sub = v4.series["sub_db"]
    bass = v4.series["bass_db"]
    n = v4.n_beats
    lo = max(0, drop - 4)
    hi = min(n - 1, drop - 1)
    e = None
    for i in range(hi, lo - 1, -1):
        if sub[i] < 5.0:
            e = i
            break
    if e is None:
        return None
    start = e
    while start - 1 >= 0 and sub[start - 1] < 5.0:
        start -= 1
    raw_gap = e - start + 1
    run = range(start, e + 1)
    bass_duty = sum(1 for i in run if bass[i] >= 8.0) / (e - start + 1)
    return e, start, raw_gap, bass_duty


def _dip_score(v4: SpectralFeaturesV4, b: int) -> float:
    """§4.1 step 5 dip_score(b)."""
    full = v4.series["full_db"]
    sub = v4.series["sub_db"]
    lo = max(0, b - 16)
    prev_full = full[lo:b]
    prev_sub = sub[lo:b]
    if not prev_full:
        return 0.0
    term1 = pct(prev_full, 50.0) - full[b]
    term2 = 0.25 * max(0.0, min(8.0, pct(prev_sub, 50.0) - sub[b]))
    return term1 + term2


def darkness_decision(v4: SpectralFeaturesV4, drop: int) -> dict[str, Any]:
    """§4.1 per-drop decision → one of blackout / dip / snap / perc-flick, plus the
    within-blackout fields (gap, dark_beats, abort_at, capped, busy_kill).

    Assumption (documented in the findings doc): the design pins every formula but
    not the exact per-drop *dip trigger window*; this tool tests the pickup-tolerance
    window [D-4, D-1] for a firing dip beat, matching the STARsound [128,129]@D=131
    acceptance anchor and the gone scan's tolerance.
    """
    sub = v4.series["sub_db"]
    growl = v4.series["growl_band_db"]
    n = v4.n_beats
    scan = tolerant_scan(v4, drop)
    busy_kill = False
    if scan is not None:
        e, start, raw_gap, bass_duty = scan
        if bass_duty <= 0.85:
            gap = min(raw_gap, 16)
            w_start = drop - gap
            # Floor-returned abort: darkness ends where a 2-consecutive floor-present
            # run STARTS; a lone pickup present beat stays dark ("dark through the
            # pickup"); floor back at window entry renders zero dark beats.
            def present(i: int) -> bool:
                return 0 <= i < n and sub[i] >= 5.0
            abort_at = None
            for bb in range(w_start, drop - 1):
                if present(bb) and present(bb + 1):
                    abort_at = bb
                    break
            dark_beats = (abort_at - w_start) if abort_at is not None else gap
            return {
                "kind": "blackout",
                "raw_gap": raw_gap,
                "gap": gap,
                "dark_beats": dark_beats,
                "abort_at": abort_at,
                "capped": raw_gap >= 16,
                "zero_dark": dark_beats == 0,
                "busy_kill": False,
            }
        busy_kill = True
    # no blackout (no gone run in window, or busy build) → dip / snap / perc-flick
    dip_fires = any(
        _dip_score(v4, b) >= 4.0 and sub[b] >= 5.0
        for b in range(max(0, drop - 4), min(n, drop))
    )
    if dip_fires:
        return {"kind": "dip", "busy_kill": busy_kill}
    perc = drop >= 2 and growl[drop - 1] <= growl[drop - 2] - 5.0
    return {"kind": "perc-flick" if perc else "snap", "busy_kill": busy_kill}


def classify_family(vec: dict[str, float], lift: float, raw_gap: float) -> str:
    """§3.1 family classifier; first match wins. pre_gap = tolerant raw_gap (S-1)."""
    if vec["coverage"] < 8:
        return "NEUTRAL"
    if lift < -7 and vec["attack_low_p90"] < 5:
        return "NEUTRAL"
    bpm = vec["bpm"]
    if bpm >= 146 and vec["air_db"] < 0 and vec["sub_db"] >= 24 and vec["onset_density_mh"] <= 3.2:
        return "COMET"
    if vec["growl_flatness"] >= 0.27 and (vec["high_db"] >= 4 or vec["mid_db"] >= 8):
        return "WALL"
    if vec["sub_db"] >= 26 and vec["onset_density_mh"] <= 2.2 and raw_gap >= 1:
        return "WALL"
    if vec["onset_density_mh"] >= 3.4 and vec["high_db"] >= 5:
        return "WALL"
    if 116 <= bpm <= 144:
        if vec["low_swing_db"] >= 10.5 and vec["attack_low_p90"] >= 7:
            return "HOUSE"
        if (vec["growl_flatness"] < 0.24 and vec["sub_db"] >= 20
                and vec["low_swing_db"] < 10.5 and vec["bass_db"] >= 14):
            return "HOUSE"
    return "NEUTRAL"


def violence_tier(vec: dict[str, float], lift: float, raw_gap: float) -> tuple[float, int]:
    """§3.2 violence score and frozen tier cuts (p55=0.616, p85=0.698)."""
    v = (0.30 * _clip01((vec["full_db"] - 8) / 10)
         + 0.20 * _clip01((lift + 4) / 5)
         + 0.25 * _clip01(vec["attack_low_p90"] / 16)
         + 0.15 * _clip01(vec["onset_density_mh"] / 4)
         + 0.10 * _clip01(raw_gap / 8))
    tier = 3 if v >= 0.698 else 2 if v >= 0.616 else 1
    return v, tier


def bass_forward_pattern(v4: SpectralFeaturesV4, drop: int, width: int = 16) -> str:
    """§5.1 per-beat B (bass-forward) / K (kick-driving) / . (neither) over the window."""
    n = v4.n_beats
    start = max(0, drop)
    end = min(n, start + width)
    gb = v4.series["growl_band_db"][start:end]
    ald = v4.series["attack_low_db"][start:end]
    if not gb:
        return ""
    ceil = pct(gb, 90.0)
    out = []
    for g, a in zip(gb, ald):
        if a >= 9.0:
            out.append("K")
        elif g >= ceil - 3.0 and g >= 18.0:
            out.append("B")
        else:
            out.append(".")
    return "".join(out)


# --------------------------------------------------------------------------- #
# Per-track reductions                                                         #
# --------------------------------------------------------------------------- #
def _identity_even_odd(v4: SpectralFeaturesV4) -> dict[str, dict[str, float]]:
    """The four identity axes computed on even vs odd beats (stability seam, metric 6)."""
    flat = list(v4.spectral_flatness_envelope)
    kick = list(v4.kick_envelope)
    sub = list(v4.series["sub_db"])
    full = list(v4.series["full_db"])
    out: dict[str, dict[str, float]] = {}
    for parity, name in ((0, "even"), (1, "odd")):
        fl, kk, sb, fu = flat[parity::2], kick[parity::2], sub[parity::2], full[parity::2]
        km = (sum(kk) / len(kk)) if kk else 0.0
        out[name] = {
            "grit": pct(fl, 50.0) if fl else 0.0,
            "punch": (statistics.pstdev(kk) / km) if (km > 0 and len(kk) > 1) else 0.0,
            "bass": (sum(1 for v in sb if v > 5.0) / len(sb)) if sb else 0.0,
            "drama": (pct(fu, 95.0) - pct(fu, 5.0)) if fu else 0.0,
        }
    return out


def _spearman(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) < 3:
        return float("nan")

    def ranks(xs: Sequence[float]) -> list[float]:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((r - ma) ** 2 for r in ra))
    db_ = math.sqrt(sum((r - mb) ** 2 for r in rb))
    return num / (da * db_) if da > 0 and db_ > 0 else float("nan")


def _drop_records(v4: SpectralFeaturesV4, drops: Sequence[int], title: str,
                  playlists: list[str]) -> list[dict[str, Any]]:
    ref = float(v4.scalars.get("loudness_ref_db", 0.0))
    recs = []
    for d in drops:
        if d < 0 or d >= v4.n_beats:
            continue
        vec = spectral_profile.drop_window_vector(v4, d, width=16)
        scan = tolerant_scan(v4, d)
        raw_gap = scan[2] if scan is not None else 0
        run_duty = scan[3] if scan is not None else None
        lift = round(vec.get("full_db", 0.0) - ref, 2)
        fam = classify_family(vec, lift, raw_gap) if vec["coverage"] else "NEUTRAL"
        viol, tier = (violence_tier(vec, lift, raw_gap) if vec["coverage"] else (0.0, 1))
        dark = darkness_decision(v4, d)
        pat = bass_forward_pattern(v4, d)
        b_rate = (pat.count("B") / len(pat)) if pat else 0.0
        recs.append({
            "title": title,
            "playlists": playlists,
            "drop_beat": int(d),
            "coverage": vec["coverage"],
            "lift": lift,
            "raw_gap": raw_gap,
            "family": fam,
            "violence": round(viol, 4),
            "tier": tier,
            "darkness": dark,
            "bass_forward": pat,
            "b_rate": round(b_rate, 4),
            "_run_duty": round(run_duty, 4) if run_duty is not None else None,
            "vector": vec,
        })
    return recs


# --------------------------------------------------------------------------- #
# Aggregation                                                                  #
# --------------------------------------------------------------------------- #
SPLITS = ("library", "by_genre", "new")


def _hist_2db(values: Sequence[float], lo: float = -40.0, hi: float = 40.0) -> dict[str, int]:
    bins: Counter = Counter()
    for v in values:
        if v < lo:
            key = f"<{lo:.0f}"
        elif v >= hi:
            key = f">={hi:.0f}"
        else:
            b = math.floor((v - lo) / 2.0) * 2 + lo
            key = f"{b:.0f}"
        bins[key] += 1
    return dict(bins)


def build_report(tracks: list[dict[str, str]], cid_playlists: dict[str, set[str]],
                 pre_keys: set[str], limit: int) -> dict[str, Any]:
    if limit:
        tracks = tracks[:limit]

    # per-split accumulators
    sub_beats: dict[str, list[float]] = {s: [] for s in SPLITS}
    full_beats: dict[str, list[float]] = {s: [] for s in SPLITS}
    growl_flat_beats: dict[str, list[float]] = {s: [] for s in SPLITS}
    onset_mh_beats: dict[str, list[float]] = {s: [] for s in SPLITS}
    loud_ref: dict[str, list[float]] = {s: [] for s in SPLITS}
    bass_duty_track: dict[str, list[float]] = {s: [] for s in SPLITS}
    lowmid_rate_track: dict[str, list[tuple[float, str]]] = {s: [] for s in SPLITS}
    ident_even: dict[str, dict[str, list[float]]] = {"grit": [], "punch": [], "bass": [], "drama": []}
    ident_odd: dict[str, dict[str, list[float]]] = {"grit": [], "punch": [], "bass": [], "drama": []}
    drops_by_split: dict[str, list[dict[str, Any]]] = {s: [] for s in SPLITS}
    playlist_family: dict[str, Counter] = {}

    counts = Counter()
    extract_failed: list[str] = []
    all_records: list[dict[str, Any]] = []
    ident_saturation: list[dict[str, Any]] = []

    for t in tracks:
        counts["scope"] += 1
        anlz = t["anlz_abs"]
        grid: list[float] = []
        drops: list[int] = []
        if anlz and os.path.isfile(anlz):
            data = read_anlz_drops(anlz)
            ctx = data.waveform_context
            if ctx is not None and len(ctx.beatgrid_times_ms) >= 2:
                grid = list(ctx.beatgrid_times_ms)
                drops = list(data.drop_beat_indices)
        has_grid = bool(grid)
        v4 = spectral_cache.get_cached_v4(t["filepath"], grid) if has_grid else None
        if not has_grid:
            counts["no_grid"] += 1
            continue
        if v4 is None:
            counts["no_v4"] += 1
            extract_failed.append(t["title"])
            continue
        counts["has_v4"] += 1

        key = spectral_cache._cache_key(t["filepath"], grid)
        is_new = key is not None and f"{key}.json" not in pre_keys
        pls = sorted(cid_playlists.get(t["content_id"], set()))
        in_bg = bool(pls)
        member = ["library"]
        if in_bg:
            member.append("by_genre")
        if is_new:
            member.append("new")

        # beat-level accumulation
        for s in member:
            sub_beats[s].extend(v4.series["sub_db"])
            full_beats[s].extend(v4.series["full_db"])
            growl_flat_beats[s].extend(v4.series["growl_flatness"])
            onset_mh_beats[s].extend(v4.series["onset_density_midhigh"])
            loud_ref[s].append(float(v4.scalars.get("loudness_ref_db", 0.0)))
            bass_duty_track[s].append(spectral_profile.bass_duty(v4))

        # metric 12 lowmid pulse firing rate (full-track scan)
        flags = spectral_profile.lowmid_pulse_flags(v4, grid)
        rate = (sum(1 for f in flags if f) / len(flags)) if flags else 0.0
        for s in member:
            lowmid_rate_track[s].append((rate, t["title"]))

        # counterexample (v): identity axis saturated at exactly 0.0 or 1.0
        axes = spectral_profile.identity_axes(v4)
        sat = {k: v for k, v in axes.items() if v in (0.0, 1.0)}
        if sat:
            ident_saturation.append({"title": t["title"], "playlists": pls, "saturated": sat,
                                     "axes": axes})

        # metric 6 identity stability (by_genre only)
        if in_bg and v4.n_beats >= 6:
            eo = _identity_even_odd(v4)
            for ax in ident_even:
                ident_even[ax].append(eo["even"][ax])
                ident_odd[ax].append(eo["odd"][ax])

        # drop-level metrics
        recs = _drop_records(v4, drops, t["title"], pls)
        for r in recs:
            for s in member:
                drops_by_split[s].append(r)
            for pl in pls:
                playlist_family.setdefault(pl, Counter())[r["family"]] += 1
        all_records.extend(recs)
        counts["drops_library"] += len(recs)

    return _assemble(
        counts, extract_failed, sub_beats, full_beats, growl_flat_beats,
        onset_mh_beats, loud_ref, bass_duty_track, lowmid_rate_track,
        ident_even, ident_odd, drops_by_split, playlist_family, all_records,
        ident_saturation,
    )


def _assemble(counts, extract_failed, sub_beats, full_beats, growl_flat_beats,
              onset_mh_beats, loud_ref, bass_duty_track, lowmid_rate_track,
              ident_even, ident_odd, drops_by_split, playlist_family, all_records,
              ident_saturation):
    metrics: dict[str, Any] = {}

    def split_map(fn):
        return {s: fn(s) for s in SPLITS}

    # 1: sub_db valley around 5.0
    def m1(s):
        vals = sub_beats[s]
        n = len(vals) or 1
        below = sum(1 for v in vals if -3.0 <= v < 5.0) / n
        above = sum(1 for v in vals if 5.0 <= v < 13.0) / n
        return {"n_beats": len(vals), "within8_below_pct": round(below * 100, 2),
                "within8_above_pct": round(above * 100, 2),
                "hist_2db": _hist_2db(vals)}
    metrics["1_sub_db_valley"] = split_map(m1)

    # 2: full_db p1 vs true-silence -30
    metrics["2_full_db_p1"] = split_map(
        lambda s: {"p1": round(pct(full_beats[s], 1.0), 2), "threshold": -30.0,
                   "n_beats": len(full_beats[s])})

    # 3: percentile rank of growl_flatness 0.25
    def m3(s):
        vals = growl_flat_beats[s]
        n = len(vals) or 1
        rank = sum(1 for v in vals if v < 0.25) / n * 100
        return {"pct_rank_of_0.25": round(rank, 1), "n_beats": len(vals)}
    metrics["3_growl_flatness_rank"] = split_map(m3)

    # 4: onset_density_midhigh p90 vs roll threshold 3.0
    metrics["4_onset_mh_p90"] = split_map(
        lambda s: {"p90": round(pct(onset_mh_beats[s], 90.0), 3), "threshold": 3.0,
                   "n_beats": len(onset_mh_beats[s])})

    # 5: loudness_ref_db p5-p95 spread
    metrics["5_loudness_ref_spread"] = split_map(
        lambda s: {"p5": round(pct(loud_ref[s], 5.0), 2), "p95": round(pct(loud_ref[s], 95.0), 2),
                   "n_tracks": len(loud_ref[s])})

    # 6: identity even/odd Spearman (by_genre only)
    metrics["6_identity_spearman_by_genre"] = {
        ax: round(_spearman(ident_even[ax], ident_odd[ax]), 4) for ax in ident_even
    }
    metrics["6_identity_spearman_by_genre"]["n_tracks"] = len(ident_even["grit"])
    metrics["6_identity_spearman_by_genre"]["v3_gate_band"] = [0.902, 0.957]

    # 7: per-track bass_duty p5/p95
    metrics["7_bass_duty_spread"] = split_map(
        lambda s: {"p5": round(pct(bass_duty_track[s], 5.0), 4),
                   "p95": round(pct(bass_duty_track[s], 95.0), 4),
                   "n_tracks": len(bass_duty_track[s])})

    # 8: family distribution over all drops (+ per-playlist)
    def m8(s):
        c = Counter(r["family"] for r in drops_by_split[s])
        n = sum(c.values()) or 1
        return {"n_drops": sum(c.values()),
                "dist": {k: c.get(k, 0) for k in ("HOUSE", "WALL", "COMET", "NEUTRAL")},
                "pct": {k: round(c.get(k, 0) / n * 100, 1) for k in ("HOUSE", "WALL", "COMET", "NEUTRAL")}}
    metrics["8_family_distribution"] = split_map(m8)
    metrics["8_per_playlist"] = {
        pl: {"n": sum(c.values()),
             "pct": {k: round(c.get(k, 0) / (sum(c.values()) or 1) * 100, 1)
                     for k in ("HOUSE", "WALL", "COMET", "NEUTRAL")}}
        for pl, c in sorted(playlist_family.items())
    }

    # 9: violence percentiles + tier counts
    def m9(s):
        vs = [r["violence"] for r in drops_by_split[s]]
        tc = Counter(r["tier"] for r in drops_by_split[s])
        return {"n_drops": len(vs), "p55": round(pct(vs, 55.0), 4), "p85": round(pct(vs, 85.0), 4),
                "tier_cuts": [0.616, 0.698],
                "tiers": {1: tc.get(1, 0), 2: tc.get(2, 0), 3: tc.get(3, 0)}}
    metrics["9_violence_tiers"] = split_map(m9)

    # 10: darkness decisions
    def m10(s):
        recs = drops_by_split[s]
        kinds = Counter(r["darkness"]["kind"] for r in recs)
        blk = [r["darkness"] for r in recs if r["darkness"]["kind"] == "blackout"]
        aborts = sum(1 for d in blk if d.get("abort_at") is not None)
        capped = sum(1 for d in blk if d.get("capped"))
        zero_dark = sum(1 for d in blk if d.get("zero_dark"))
        busy = sum(1 for r in recs if r["darkness"].get("busy_kill"))
        dark_hist = Counter(min(16, d["dark_beats"]) for d in blk)
        # runs whose bass_duty sits in the 0.85-cliff band [0.80, 0.90]
        duty_cliff = sum(1 for r in recs
                         if r["_run_duty"] is not None and 0.80 <= r["_run_duty"] <= 0.90)
        return {"n_drops": len(recs),
                "blackout": kinds.get("blackout", 0), "dip": kinds.get("dip", 0),
                "snap": kinds.get("snap", 0), "perc_flick": kinds.get("perc-flick", 0),
                "aborts": aborts, "at_16_cap": capped, "zero_dark": zero_dark,
                "busy_kills": busy, "duty_band_0.80_0.90": duty_cliff,
                "dark_beats_hist": {str(k): dark_hist[k] for k in sorted(dark_hist)}}
    metrics["10_darkness"] = split_map(m10)

    # 11: bass-forward
    def m11(s):
        recs = [r for r in drops_by_split[s] if r["bass_forward"]]
        n = len(recs) or 1
        with_b = sum(1 for r in recs if "B" in r["bass_forward"])
        all_b = sum(1 for r in recs if set(r["bass_forward"]) == {"B"})
        all_k = sum(1 for r in recs if set(r["bass_forward"]) == {"K"})
        rates = [r["b_rate"] for r in recs]
        return {"n_windows": len(recs), "with_ge1_B_pct": round(with_b / n * 100, 1),
                "b_rate_p25": round(pct(rates, 25.0), 3), "b_rate_p50": round(pct(rates, 50.0), 3),
                "b_rate_p75": round(pct(rates, 75.0), 3),
                "all_B_windows": all_b, "all_K_windows": all_k}
    metrics["11_bass_forward"] = split_map(m11)

    # 12: lowmid pulse firing rate distribution + top-10
    def m12(s):
        rates = [r for r, _ in lowmid_rate_track[s]]
        top = sorted(lowmid_rate_track[s], reverse=True)[:10]
        return {"n_tracks": len(rates), "p50": round(pct(rates, 50.0), 4),
                "p90": round(pct(rates, 90.0), 4), "max": round(max(rates), 4) if rates else 0.0,
                "top10": [{"title": t, "rate": round(r, 4)} for r, t in top]}
    metrics["12_lowmid_pulse"] = split_map(m12)

    counterexamples = _counterexamples(all_records, ident_saturation)

    return {
        "counts": dict(counts),
        "extract_failed_titles": sorted(extract_failed),
        "metrics": metrics,
        "counterexamples": counterexamples,
        "records": all_records,
    }


DEEP_GROOVE_UKG = {"DEEP HOUSE", "GROOVE HOUSE", "UKG"}


def _counterexamples(records: list[dict[str, Any]],
                     ident_saturation: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    def brief(r, extra=None):
        out = {"title": r["title"], "drop_beat": r["drop_beat"], "playlists": r["playlists"],
               "family": r["family"], "violence": r["violence"], "tier": r["tier"]}
        if extra:
            out.update(extra)
        return out

    ce: dict[str, list[dict[str, Any]]] = {}
    # (i) NEUTRAL with violence >= 0.698
    ce["i_neutral_high_violence"] = [
        brief(r) for r in sorted(records, key=lambda r: -r["violence"])
        if r["family"] == "NEUTRAL" and r["violence"] >= 0.698][:10]
    # (ii) tier-3 in deep/groove/UKG
    ce["ii_tier3_in_groovy_house"] = [
        brief(r, {"lift": r["lift"]}) for r in sorted(records, key=lambda r: -r["violence"])
        if r["tier"] == 3 and DEEP_GROOVE_UKG.intersection(r["playlists"])][:10]
    # (iii) blackout runs with raw_gap >= 40 (cap distortion size)
    ce["iii_blackout_rawgap_ge40"] = [
        brief(r, {"raw_gap": r["raw_gap"], "dark_beats": r["darkness"].get("dark_beats")})
        for r in sorted(records, key=lambda r: -r["raw_gap"])
        if r["darkness"]["kind"] == "blackout" and r["raw_gap"] >= 40][:10]
    # (iv) busy-kill near-misses (run bass_duty 0.80-0.90)
    ce["iv_busy_kill_near_miss"] = _near_miss_records(records)[:10]
    # (v) tracks with any identity axis saturated at exactly 0.0 or 1.0
    ce["v_identity_saturation"] = ident_saturation[:10]
    return ce


def _near_miss_records(records):
    out = []
    for r in records:
        duty = r.get("_run_duty")
        if duty is not None and 0.80 <= duty <= 0.90:
            out.append({"title": r["title"], "drop_beat": r["drop_beat"],
                        "playlists": r["playlists"], "run_duty": round(duty, 3),
                        "kind": r["darkness"]["kind"]})
    return sorted(out, key=lambda x: x["run_duty"])


# --------------------------------------------------------------------------- #
# Markdown rendering                                                           #
# --------------------------------------------------------------------------- #
def render_markdown(report: dict[str, Any]) -> str:
    m = report["metrics"]
    L = []
    L.append("# Spectral calibration report (auto-generated)\n")
    L.append(f"Counts: `{report['counts']}`\n")
    L.append(f"extract_failed titles: {report['extract_failed_titles']}\n")

    def bg(metric, *keys):
        d = m[metric]["by_genre"]
        return d

    L.append("\n## Metric summary (by_genre split unless noted)\n")
    L.append(f"1. sub_db valley: below={bg('1_sub_db_valley')['within8_below_pct']}% "
             f"above={bg('1_sub_db_valley')['within8_above_pct']}% (prior 4.7/5.7)")
    L.append(f"2. full_db p1 = {bg('2_full_db_p1')['p1']} (prior -26; threshold -30)")
    L.append(f"3. growl_flatness 0.25 pct-rank = p{bg('3_growl_flatness_rank')['pct_rank_of_0.25']} (prior ~p78)")
    L.append(f"4. onset_mh p90 = {bg('4_onset_mh_p90')['p90']} (threshold 3.0; prior thr>p90)")
    L.append(f"5. loudness_ref spread p5-p95 = {bg('5_loudness_ref_spread')['p5']}-{bg('5_loudness_ref_spread')['p95']} (prior 15.3-19.3)")
    s6 = m["6_identity_spearman_by_genre"]
    L.append(f"6. identity Spearman grit/punch/bass/drama = {s6['grit']}/{s6['punch']}/{s6['bass']}/{s6['drama']} "
             f"(prior .929/.935/.967/.928; gate {s6['v3_gate_band']})")
    L.append(f"7. bass_duty p5/p95 = {bg('7_bass_duty_spread')['p5']}/{bg('7_bass_duty_spread')['p95']} (anchors .5856/.9688)")
    fam = m["8_family_distribution"]["library"]
    L.append(f"8. family (library, n={fam['n_drops']}): {fam['pct']} (prior HOUSE41/WALL21/COMET11/NEUTRAL27)")
    v9 = m["9_violence_tiers"]["library"]
    L.append(f"9. violence p55/p85 = {v9['p55']}/{v9['p85']} (cuts .616/.698); tiers {v9['tiers']} (prior 2159/1176/601)")
    d10 = m["10_darkness"]["library"]
    L.append(f"10. darkness (library): blk {d10['blackout']} / dip {d10['dip']} / snap {d10['snap']} / "
             f"perc {d10['perc_flick']} / abort {d10['aborts']}; cap16 {d10['at_16_cap']}; zero-dark {d10['zero_dark']}; "
             f"busy-kills {d10['busy_kills']} (prior 1320/1145/1366/105/150; 219;48)")
    b11 = m["11_bass_forward"]["library"]
    L.append(f"11. bass-forward (library): {b11['with_ge1_B_pct']}% windows have >=1 B; "
             f"all-B {b11['all_B_windows']} all-K {b11['all_K_windows']}")
    l12 = m["12_lowmid_pulse"]["library"]
    L.append(f"12. lowmid pulse fire-rate p50/p90/max = {l12['p50']}/{l12['p90']}/{l12['max']}")

    L.append("\n## Counterexamples\n")
    for name, rows in report["counterexamples"].items():
        def label(r):
            t = r.get("title", "?")
            return f"{t}@{r['drop_beat']}" if "drop_beat" in r else t
        body = "; ".join(label(r) for r in rows[:10]) if rows else "none"
        L.append(f"- **{name}** ({len(rows)}): {body}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default="")
    ap.add_argument("--markdown", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pre-sweep-keys", default=DEFAULT_PRE_SWEEP_KEYS)
    args = ap.parse_args()

    pre_keys: set[str] = set()
    p = Path(args.pre_sweep_keys)
    if p.is_file():
        pre_keys = {ln.strip() for ln in p.read_text().splitlines() if ln.strip()}
    else:
        print(f"WARN: pre-sweep keys {args.pre_sweep_keys} absent — 'new' split empty", file=sys.stderr)

    t0 = time.perf_counter()
    db = _open_db()
    try:
        tracks, cid_playlists = _enumerate(db)
    finally:
        db.close()
    by_genre_cids = len(cid_playlists)
    print(f"scope: {len(tracks)} on-disk tracks; by_genre ContentIDs: {by_genre_cids}; "
          f"pre-sweep keys: {len(pre_keys)}", file=sys.stderr)

    report = build_report(tracks, cid_playlists, pre_keys, args.limit)
    report["meta"] = {
        "by_genre_content_ids": by_genre_cids,
        "pre_sweep_keys": len(pre_keys),
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))
        print(f"wrote {args.json} ({len(report['records'])} drop records)", file=sys.stderr)
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(report))
        print(f"wrote {args.markdown}", file=sys.stderr)
    if not args.json and not args.markdown:
        print(json.dumps(report["metrics"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
