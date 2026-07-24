"""Offline per-drop energy-grade report — energy-fabric stage E3 (AWR-290).

Read-only corpus sweep: enumerates the BY GENRE Rekordbox tracks, loads each
track's cached v4 features + the E1 track-weight store (through the ONE E2 refusal
loader), grades the raw ANLZ drop markers, and evaluates the pinned G1/G2/G3
gates. Also computes E2's "low"-section grades (the G3 comparison set) and the
smart-vs-raw attach-match rate (informational). Writes NO store.

ZERO runtime behavior change; DB / ANLZ / audio / caches READ-ONLY. No threshold
tuning — a failed gate is a valid result, reported plainly, exit 1; changing any
pinned constant is a spec amendment for the exec. (E3REV N1 fold: this report
prints BOTH G3 medians — drops AND "low" sections — not just their difference.)
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
from rb_ss_bridge_v2.section_energy_v0 import (  # noqa: E402
    load_track_weight_store, store_track_weight, grade_sections)
from rb_ss_bridge_v2.drop_energy_v0 import (  # noqa: E402
    COVERAGE_GATE, IQR_GATE, SEPARATION_GATE, grade_drops, gates_verdict)

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

    n_by_genre_total = 0
    n_by_genre_eligible = 0
    n_graded = 0
    drop_withins = []        # all graded by_genre drops' within_track (G2 + G3)
    low_withins = []         # "low"-section within_track over eligible tracks (G3)
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
        grades = grade_drops(v4, drop_beats=raw_drops, track_weight=tw)
        if grades:
            n_graded += 1
            graded_beats = {g["drop_beat"] for g in grades}
            drop_withins.extend(g["within_track"] for g in grades)
            smart = select_smart_drops(raw_drops, total_beats=int(v4.n_beats))
            smart_total += len(smart)
            smart_matched += sum(1 for sd in smart if int(sd) in graded_beats)
        for sec in grade_sections(
                v4, anlz_drops=raw_drops,
                anlz_buildups=list(data.buildup_beat_indices),
                anlz_breakdowns=list(data.breakdown_beat_indices),
                track_weight=tw):
            if sec["label"] == "low":
                low_withins.append(sec["within_track"])

    ds = sorted(drop_withins)
    iqr = (_pct(ds, 75) - _pct(ds, 25)) if len(ds) >= 2 else None
    drop_median = _pct(ds, 50)
    low_median = _pct(sorted(low_withins), 50)
    separation = (drop_median - low_median) if (drop_median is not None
                                                and low_median is not None) else None

    if forced_partial:
        accepted, reason = False, "partial_run"
    else:
        accepted, reason = gates_verdict(n_by_genre_eligible, n_graded, iqr,
                                         separation)

    match_rate = (smart_matched / smart_total) if smart_total else None
    abs_cov = (n_by_genre_eligible / n_by_genre_total) if n_by_genre_total else 0.0

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
    emit("  graded drops: %d   'low' sections: %d" % (len(ds), len(low_withins)))
    emit("  attach-match rate (smart drops on a graded raw beat) = %s (%d/%d, INFORMATIONAL)"
         % (("%.3f" % match_rate) if match_rate is not None else "n/a",
            smart_matched, smart_total))
    emit("")
    g1 = (n_graded / n_by_genre_eligible) if n_by_genre_eligible else 0.0
    emit("ACCEPTANCE: %s   reason=%s" % ("ACCEPTED" if accepted else "NOT ACCEPTED", reason))
    emit("  G1 coverage  n_graded/n_by_genre_eligible = %.3f  (gate >= %.2f)" % (g1, COVERAGE_GATE))
    emit("  G2 non-degeneracy  IQR(drop within_track) = %s  (gate >= %.2f)"
         % (("%.4f" % iqr) if iqr is not None else "n/a", IQR_GATE))
    emit("  G3 separation  median(drop) - median('low') = %s  (gate >= %.2f)"
         % (("%.4f" % separation) if separation is not None else "n/a", SEPARATION_GATE))
    # N1 fold: both medians, not just their difference
    emit("     median(drop within_track) = %s ; median('low' section within_track) = %s"
         % (("%.4f" % drop_median) if drop_median is not None else "n/a",
            ("%.4f" % low_median) if low_median is not None else "n/a"))
    if forced_partial:
        emit("")
        emit("!! PARTIAL RUN (--limit %s): acceptance forced FALSE (partial_run)." % args.limit)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
