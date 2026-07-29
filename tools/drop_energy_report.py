"""Offline per-drop energy-grade report — energy-fabric stage E3 (AWR-290,
revised by AWR-291).

Read-only corpus sweep: enumerates the BY GENRE Rekordbox tracks, loads each
track's cached v4 features + the E1 track-weight store (through the ONE E2 refusal
loader), grades the raw ANLZ drop markers, and evaluates the seven pinned gates:
G1 coverage, G2 worst-term railed fraction, G3 worst-term correlation, G4
composite IQR, G5 rankability, G6 dB-level separation, G7 grade-space separation.
Also computes E2's "low"-section grades (the G6/G7 comparison set) and the
smart-vs-raw attach-match rate (informational). Writes NO store.

ZERO runtime behavior change; DB / ANLZ / audio / caches READ-ONLY. No threshold
tuning — a failed gate is a valid result, reported plainly, exit 1; changing any
pinned constant is a spec amendment for the exec. (E3REV N1 fold: the G6 and G7
lines print BOTH medians — drops AND "low" sections — not just their difference.)
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache  # noqa: E402
from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2 import drop_energy_v0  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import read_anlz_drops  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import select_smart_drops  # noqa: E402
from rb_ss_bridge_v2.track_weight_v0 import spearman  # noqa: E402
from rb_ss_bridge_v2.section_energy_v0 import (  # noqa: E402
    load_track_weight_store, store_track_weight)
from rb_ss_bridge_v2.drop_energy_v0 import (  # noqa: E402
    COVERAGE_GATE, TERM_SATURATION_MAX, TERM_CORRELATION_MAX, IQR_GATE,
    RANKABILITY_GATE, LEVEL_SEPARATION_DB, GRADE_SEPARATION_GATE,
    DROP_WINDOW_BEATS, MIN_WINDOW_BEATS,
    drop_body_levels, score_windows, grade_drops, gates_verdict, _all_finite,
    _finite_ref, _finite_pos, _percentile, _corpus_pool)

TERMS = ("body", "activity", "perc_high", "growl")


def _gradeable(v4, raw_drops, corpus_dist, *, third):
    """True iff the track produces >=1 grade under the given third-normaliser set:
    `third`='flux' = the R4 v3 set {in-module fluxsum p90, growl, perc p90};
    'onset' = the PRE-swap v2 set {onset_mh_p90, growl, perc p90}. The
    population-reconciliation probe for the swap — mirrors grade_drops/score_windows
    eligibility, and the 'flux' verdict is asserted equal to bool(grade_drops) every
    run, so it cannot silently drift from the live module.
    # ponytail: reproduces the retired v2 normaliser set only to MEASURE the
    # population delta the swap creates; drift-guarded against the module each run."""
    ref = _finite_ref(v4)
    if ref is None:
        return False
    scalars = getattr(v4, "scalars", None) or {}
    if _finite_pos(scalars.get("growl_timbre_p90")) is None:
        return False
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0:
        return False
    series = getattr(v4, "series", None) or {}
    full = series.get("full_db")
    perc = series.get("perc_high")
    growl = series.get("growl_flatness")
    third_series = series.get(
        "fluxsum_midhigh" if third == "flux" else "onset_density_midhigh")
    if not full or not perc or not growl or not third_series:
        return False
    if min(len(full), len(perc), len(growl), len(third_series)) < n:
        return False
    pb = perc[:n]
    if not _all_finite(pb) or _finite_pos(_percentile(sorted(pb), 90)) is None:
        return False
    if third == "flux":
        tb = third_series[:n]
        if not _all_finite(tb) or _finite_pos(_percentile(sorted(tb), 90)) is None:
            return False
    elif _finite_pos(scalars.get("onset_mh_p90")) is None:
        return False
    own = drop_body_levels(v4, raw_drops)
    if len(own) < 2 and not _corpus_pool(corpus_dist):
        return False
    for raw in raw_drops:
        b = int(raw)
        s = max(0, b)
        e = min(n, b + DROP_WINDOW_BEATS)
        if e - s < MIN_WINDOW_BEATS:
            continue
        if (_all_finite(full[s:e]) and _all_finite(third_series[s:e])
                and _all_finite(perc[s:e]) and _all_finite(growl[s:e])):
            return True
    return False

SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
DB_PATH = Path("~/Library/Pioneer/rekordbox/master.db").expanduser()
BY_GENRE_FOLDER_ID = "666898931"
BY_GENRE_EXCLUDE = {"RAP"}


def _open_db() -> Any:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    return Rekordbox6Database(str(DB_PATH), unlock=True)


def _enumerate(db: Any) -> "list":
    genre_pls = [
        p for p in db.get_playlist()
        if str(getattr(p, "ParentID", "")) == BY_GENRE_FOLDER_ID
        and str(getattr(p, "Name", "")) not in BY_GENRE_EXCLUDE
    ]
    cids: "set" = set()
    for pl in genre_pls:
        for row in db.get_playlist_songs(PlaylistID=str(pl.ID)):
            cids.add(str(row.ContentID))
    tracks: "list[dict]" = []
    for c in db.get_content():
        if getattr(c, "rb_local_deleted", 0):
            continue
        filepath = str(c.FolderPath or "")
        if not filepath or not os.path.isfile(filepath):
            continue
        anlz_rel = str(getattr(c, "AnalysisDataPath", "") or "")
        anlz_abs = str(SHARE_ROOT / anlz_rel.lstrip("/")) if anlz_rel else ""
        tracks.append({"content_id": str(c.ID), "filepath": filepath,
                       "anlz_abs": anlz_abs, "by_genre": str(c.ID) in cids})
    tracks.sort(key=lambda t: t["content_id"])
    return tracks


def _pct(sorted_vals, q):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    pos = (q / 100.0) * (n - 1)
    lo, hi = int(pos), min(int(pos) + 1, n - 1)
    return sorted_vals[lo] * (1 - (pos - lo)) + sorted_vals[hi] * (pos - lo)


def run(argv: "Sequence[str]") -> int:
    ap = argparse.ArgumentParser(description="Offline E3 drop-energy report")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=None,
                    help="DEV ONLY: truncate track list; forces partial_run")
    args = ap.parse_args(list(argv))

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    cache_dir = spectral_cache._cache_dir()
    if not cache_dir.exists():
        sys.stderr.write("ENV ERROR: cache dir absent: %s\n" % cache_dir)
        return 2
    try:
        db = _open_db()
    except Exception as exc:
        sys.stderr.write("ENV ERROR: cannot open Rekordbox DB (%s): %s\n"
                         % (type(exc).__name__, exc))
        return 2

    store = load_track_weight_store(
        cache_dir / "trackweight_v1" / "track_weight_store.json")
    tracks = _enumerate(db)
    forced_partial = args.limit is not None
    if forced_partial:
        tracks = tracks[:max(0, args.limit)]

    corpus_dist = list((store or {}).get("drop_body_distribution") or [])
    n_by_genre_total = 0
    n_by_genre_eligible = 0
    n_graded = 0
    total_graded_drops = 0
    corpus_basis_count = 0
    n_graded_v2 = 0          # R4 population reconciliation: v2 onset_mh_p90 set
    entered_ids = []         # eligible tracks in v3 but not v2 (build report)
    left_ids = []            # eligible tracks in v2 but not v3 (build report)
    n_drop_tracks = 0        # eligible tracks with >= 3 graded drops (G5)
    n_drop_rankable = 0      # ... of those, with >= 2 distinct composite grades
    term_vals = {k: [] for k in TERMS}   # G2 saturation + G3 correlation
    drop_withins = []        # composite (G4 IQR + G7 drop median)
    drop_levels = []         # drop-window rel dB (G6 drop side)
    low_levels = []          # 'low' section rel dB (G6 low side)
    low_composites = []      # G7 'low' composite (body ranked vs track's drops)
    lib_tw_pairs = []        # (library_scaled, track_weight) — INFORMATIONAL
    lib_within_pairs = []    # (library_scaled, within_track) — INFORMATIONAL
    smart_total = 0
    smart_matched = 0
    counts = {"no_grid": 0, "no_v4": 0, "no_drops": 0, "no_store_row": 0}
    for t in tracks:
        if t["by_genre"]:
            n_by_genre_total += 1
        anlz = t["anlz_abs"]
        data = read_anlz_drops(anlz) if (anlz and os.path.isfile(anlz)) else None
        ctx = data.waveform_context if data is not None else None
        grid = (list(ctx.beatgrid_times_ms)
                if ctx is not None and len(ctx.beatgrid_times_ms) >= 2 else [])
        if not grid:
            counts["no_grid"] += 1
            continue
        v4 = spectral_cache.get_cached_v4(t["filepath"], grid)
        if v4 is None:
            counts["no_v4"] += 1
            continue
        raw_drops = list(data.drop_beat_indices)
        if not raw_drops:
            counts["no_drops"] += 1
            continue
        key = spectral_cache._cache_key(t["filepath"], grid)
        has_row = bool(store) and key is not None and key in store.get("tracks", {})
        if not (t["by_genre"] and has_row):
            if t["by_genre"]:
                counts["no_store_row"] += 1
            continue
        # ELIGIBLE: by_genre + v4 + store row + >=1 ANLZ drop marker
        n_by_genre_eligible += 1
        tw = store_track_weight(store, key)
        buildups = list(data.buildup_beat_indices)
        breakdowns = list(data.breakdown_beat_indices)
        own_levels = drop_body_levels(v4, raw_drops)
        grades = grade_drops(v4, drop_beats=raw_drops, track_weight=tw,
                             corpus_drop_levels=corpus_dist)
        # R4 population reconciliation (INFORMATIONAL): grade under both the v3
        # activity set and the retired v2 onset set; the flux probe is drift-guarded
        # against the live module.
        gv3 = _gradeable(v4, raw_drops, corpus_dist, third="flux")
        gv2 = _gradeable(v4, raw_drops, corpus_dist, third="onset")
        if gv3 != bool(grades):
            raise AssertionError(
                "reconcile probe drift vs grade_drops at %s" % t["content_id"])
        if gv2:
            n_graded_v2 += 1
        if gv3 and not gv2:
            entered_ids.append(t["content_id"])
        elif gv2 and not gv3:
            left_ids.append(t["content_id"])
        if grades:
            n_graded += 1
            basis = grades[0]["body_basis"]
            pool = own_levels if basis == "track_drops" else corpus_dist
            scored = score_windows(v4, raw_drops, body_pool=pool)
            for row in scored:
                for k in TERMS:
                    term_vals[k].append(row[k])
            withins = [g["within_track"] for g in grades]
            drop_withins.extend(withins)
            total_graded_drops += len(grades)
            corpus_basis_count += sum(1 for g in grades if g["body_basis"] == "corpus")
            if len(withins) >= 3:
                n_drop_tracks += 1
                if len(set(withins)) >= 2:
                    n_drop_rankable += 1
            if tw is not None:
                for g in grades:
                    if g["library_scaled"] is not None:
                        lib_tw_pairs.append((g["library_scaled"], tw))
                        lib_within_pairs.append((g["library_scaled"], g["within_track"]))
            graded_beats = {g["drop_beat"] for g in grades}
            smart = select_smart_drops(raw_drops, total_beats=int(v4.n_beats))
            smart_total += len(smart)
            smart_matched += sum(1 for sd in smart if int(sd) in graded_beats)
        # G6 drop side (this track's drop-window rel dB)
        drop_levels.extend(own_levels)
        # G6 low side + G7 low composite (body ranked vs the track's OWN drops)
        ref = float(v4.scalars["loudness_ref_db"])
        full = v4.series["full_db"]
        n_beats = int(v4.n_beats)
        # _normalized_segments now returns (segments, segmentation_basis) — the
        # basis is unused here; the section iteration is unchanged (byte-identical
        # report output).
        _segs, _basis = section_energy_v0._normalized_segments(
            v4, raw_drops, buildups, breakdowns)
        for (start, end, label) in _segs:
            if label != "low":
                continue
            s = max(0, int(start))
            e = min(n_beats, int(end))
            if e - s >= 1:
                fw = full[s:e]
                if _all_finite(fw):
                    low_levels.append(sum(fw) / len(fw) - ref)
            if own_levels:
                for row in score_windows(v4, [start], body_pool=own_levels):
                    low_composites.append(row["within_track"])

    # ---- gate quantities ----
    def _railed(vals):
        return (sum(1 for v in vals if v <= 0.0 or v >= 1.0) / len(vals)) if vals else None

    term_railed = {k: _railed(term_vals[k]) for k in TERMS}
    _rf = [v for v in term_railed.values() if v is not None]
    term_railed_max = max(_rf) if _rf else None
    term_matrix = {}
    term_rho_max = None
    for a in TERMS:
        for b in TERMS:
            if a == b:
                term_matrix[(a, b)] = 1.0
                continue
            rho = spearman(term_vals[a], term_vals[b])
            term_matrix[(a, b)] = rho
            if rho is not None:
                term_rho_max = abs(rho) if term_rho_max is None else max(term_rho_max, abs(rho))
    ds = sorted(drop_withins)
    iqr = (_pct(ds, 75) - _pct(ds, 25)) if len(ds) >= 2 else None
    rankable_fraction = (n_drop_rankable / n_drop_tracks) if n_drop_tracks else None
    drop_lvl_med = _pct(sorted(drop_levels), 50)
    low_lvl_med = _pct(sorted(low_levels), 50)
    level_sep = (drop_lvl_med - low_lvl_med) if (drop_lvl_med is not None
                                                 and low_lvl_med is not None) else None
    drop_comp_med = _pct(ds, 50)
    low_comp_med = _pct(sorted(low_composites), 50)
    grade_sep = (drop_comp_med - low_comp_med) if (drop_comp_med is not None
                                                   and low_comp_med is not None) else None
    rho_lib_tw = (spearman([p[0] for p in lib_tw_pairs], [p[1] for p in lib_tw_pairs])
                  if len(lib_tw_pairs) >= 3 else None)
    rho_lib_within = (spearman([p[0] for p in lib_within_pairs],
                               [p[1] for p in lib_within_pairs])
                      if len(lib_within_pairs) >= 3 else None)

    if forced_partial:
        accepted, reason = False, "partial_run"
    else:
        accepted, reason = gates_verdict(
            n_by_genre_eligible, n_graded, term_railed_max, term_rho_max, iqr,
            rankable_fraction, level_sep, grade_sep)

    match_rate = (smart_matched / smart_total) if smart_total else None
    abs_cov = (n_by_genre_eligible / n_by_genre_total) if n_by_genre_total else 0.0
    corpus_pct = (100.0 * corpus_basis_count / total_graded_drops) if total_graded_drops else 0.0

    emit("# Energy E3 — per-drop grade report")
    emit("# OFFLINE / read-only. Bridge unchanged. Grades are STATUS-ONLY (no consumer).")
    emit("")
    emit("store: %s" % ("loaded (E1 accepted)" if store else "refused_or_missing"))
    emit("by_genre tracks total: %d" % n_by_genre_total)
    emit("  eligible (v4 + store row + >=1 drop): %d   graded: %d" % (n_by_genre_eligible, n_graded))
    emit("  skips: no_grid %d  no_v4 %d  no_drops %d  by_genre_no_store_row %d"
         % (counts["no_grid"], counts["no_v4"], counts["no_drops"], counts["no_store_row"]))
    emit("  absolute coverage n_by_genre_eligible/n_by_genre_total = %d/%d = %.3f (INFORMATIONAL)"
         % (n_by_genre_eligible, n_by_genre_total, abs_cov))
    emit("  graded drops: %d   'low' windows: %d" % (len(ds), len(low_composites)))
    emit("  corpus body-basis drops = %d / %d = %.2f%% (INFORMATIONAL; per-drop rate; "
         "~2.18%% of TRACKS have <2 own drops and fall to the corpus basis)"
         % (corpus_basis_count, total_graded_drops, corpus_pct))
    emit("  attach-match rate (smart drops on a graded raw beat) = %s (%d/%d, INFORMATIONAL)"
         % (("%.3f" % match_rate) if match_rate is not None else "n/a",
            smart_matched, smart_total))
    emit("  population reconciliation (R4 swap): graded %d tracks / %d drops (v3 activity set)"
         "  vs  %d tracks (v2 onset_mh_p90 set)  delta %+d tracks [entered %d, left %d;"
         " content_ids in build report] (INFORMATIONAL)"
         % (n_graded, total_graded_drops, n_graded_v2, n_graded - n_graded_v2,
            len(entered_ids), len(left_ids)))
    emit("")
    g1 = (n_graded / n_by_genre_eligible) if n_by_genre_eligible else 0.0
    emit("ACCEPTANCE: %s   reason=%s" % ("ACCEPTED" if accepted else "NOT ACCEPTED", reason))
    emit("  G1 coverage      n_graded/n_by_genre_eligible = %.3f  (gate >= %.2f)" % (g1, COVERAGE_GATE))
    emit("  G2 saturation    worst term railed fraction = %s  (gate <= %.2f)"
         % (("%.4f" % term_railed_max) if term_railed_max is not None else "n/a", TERM_SATURATION_MAX))
    for k in TERMS:
        emit("       term %-10s railed = %s"
             % (k, ("%.4f" % term_railed[k]) if term_railed[k] is not None else "n/a"))
    emit("  G3 correlation   worst |rho| between terms = %s  (gate <= %.2f)"
         % (("%.4f" % term_rho_max) if term_rho_max is not None else "n/a", TERM_CORRELATION_MAX))
    emit("       %-12s%s" % ("", "".join("%11s" % k for k in TERMS)))
    for a in TERMS:
        cells = "".join(
            ("%+11.3f" % term_matrix[(a, b)]) if term_matrix[(a, b)] is not None
            else "%11s" % "None" for b in TERMS)
        emit("       %-12s%s" % (a, cells))
    emit("  G4 IQR           IQR(drop within_track) = %s  (gate >= %.2f)"
         % (("%.4f" % iqr) if iqr is not None else "n/a", IQR_GATE))
    emit("  G5 rankability   tracks (>=3 drops) with >=2 distinct grades = %s  (gate >= %.2f, n=%d)"
         % (("%.4f" % rankable_fraction) if rankable_fraction is not None else "n/a",
            RANKABILITY_GATE, n_drop_tracks))
    emit("  G6 level sep     median(drop rel_dB) - median('low' rel_dB) = %s  (gate >= %.2f dB)"
         % (("%.4f" % level_sep) if level_sep is not None else "n/a", LEVEL_SEPARATION_DB))
    emit("       median(drop rel_dB) = %s ; median('low' rel_dB) = %s"
         % (("%.4f" % drop_lvl_med) if drop_lvl_med is not None else "n/a",
            ("%.4f" % low_lvl_med) if low_lvl_med is not None else "n/a"))
    emit("  G7 grade sep     median(drop composite) - median('low' composite) = %s  (gate >= %.2f)"
         % (("%.4f" % grade_sep) if grade_sep is not None else "n/a", GRADE_SEPARATION_GATE))
    emit("       median(drop) = %s ; median('low') = %s ; n_low = %d"
         % (("%.4f" % drop_comp_med) if drop_comp_med is not None else "n/a",
            ("%.4f" % low_comp_med) if low_comp_med is not None else "n/a",
            len(low_composites)))
    emit("")
    emit("  rho(library_scaled, track_weight) = %s   (INFORMATIONAL; v1 +0.9803, v2 expected ~+0.884)"
         % (("%+.4f" % rho_lib_tw) if rho_lib_tw is not None else "n/a"))
    emit("  rho(library_scaled, within_track) = %s   (INFORMATIONAL; v1 +0.1713, v2 expected ~+0.510)"
         % (("%+.4f" % rho_lib_within) if rho_lib_within is not None else "n/a"))
    if forced_partial:
        emit("")
        emit("!! PARTIAL RUN (--limit %s): acceptance forced FALSE (partial_run)." % args.limit)

    # entered/left content_ids -> stderr for the build report (NOT the report text:
    # a variable-length per-track list would make the Task-2 pin fragile).
    sys.stderr.write("RECONCILE entered(%d)=%s\n"
                     % (len(entered_ids), ",".join(entered_ids) or "-"))
    sys.stderr.write("RECONCILE left(%d)=%s\n"
                     % (len(left_ids), ",".join(left_ids) or "-"))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
