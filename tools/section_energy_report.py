"""Offline per-section energy-grade report — energy-fabric stage E2 (AWR-288).

Read-only corpus sweep: enumerates the BY GENRE Rekordbox tracks, loads each
track's cached v4 features + the E1 track-weight store (through the ONE refusal
gate `section_energy_v0.load_track_weight_store`, shared with the runtime),
computes per-section grades, and evaluates the pinned G1/G2 gates. Writes NO
store (E2 has no sidecar); `--out` copies the report text only.

ZERO runtime behavior change: importing this tool touches nothing live; the
Rekordbox DB / ANLZ / audio / caches are READ-ONLY. No threshold tuning to pass —
a failed gate is a valid result, reported plainly, exit 1; changing any pinned
constant is a spec amendment for the exec.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache  # noqa: E402
from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import read_anlz_drops  # noqa: E402
from rb_ss_bridge_v2.section_energy_v0 import (  # noqa: E402
    SPREAD_MIN,
    COVERAGE_GATE,
    SPREAD_GATE_FRACTION,
    gates_verdict,
    grade_sections,
    load_track_weight_store,
    store_track_weight,
)

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


def _enumerate(db: Any) -> "tuple[list, dict]":
    genre_pls = [
        p for p in db.get_playlist()
        if str(getattr(p, "ParentID", "")) == BY_GENRE_FOLDER_ID
        and str(getattr(p, "Name", "")) not in BY_GENRE_EXCLUDE
    ]
    cid_playlists: "dict[str, set]" = {}
    for pl in genre_pls:
        for row in db.get_playlist_songs(PlaylistID=str(pl.ID)):
            cid_playlists.setdefault(str(row.ContentID), set()).add(str(pl.Name))
    tracks: "list[dict]" = []
    for c in db.get_content():
        if getattr(c, "rb_local_deleted", 0):
            continue
        filepath = str(c.FolderPath or "")
        if not filepath or not os.path.isfile(filepath):
            continue
        anlz_rel = str(getattr(c, "AnalysisDataPath", "") or "")
        anlz_abs = str(SHARE_ROOT / anlz_rel.lstrip("/")) if anlz_rel else ""
        tracks.append({"content_id": str(c.ID), "title": str(c.Title or ""),
                       "filepath": filepath, "anlz_abs": anlz_abs,
                       "by_genre": str(c.ID) in cid_playlists})
    tracks.sort(key=lambda t: t["content_id"])
    return tracks, cid_playlists


def run(argv: "Sequence[str]") -> int:
    ap = argparse.ArgumentParser(description="Offline E2 section-energy report")
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

    tracks, _cid = _enumerate(db)
    forced_partial = args.limit is not None
    if forced_partial:
        tracks = tracks[:max(0, args.limit)]

    n_by_genre_total = 0
    n_by_genre_eligible = 0        # by_genre + v4 + store row (G1 denominator)
    n_graded = 0                   # eligible + non-empty grades (G1 numerator)
    n_spread_ok = 0                # graded + within_track spread >= SPREAD_MIN
    lib_graded = 0
    lib_scored = 0
    counts = {"no_grid": 0, "no_v4": 0}
    spreads = []
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
        key = spectral_cache._cache_key(t["filepath"], grid)
        has_row = bool(store) and key is not None \
            and key in store.get("tracks", {})
        tw = store_track_weight(store, key) if (store and key) else None
        grades = grade_sections(
            v4, anlz_drops=list(data.drop_beat_indices),
            anlz_buildups=list(data.buildup_beat_indices),
            anlz_breakdowns=list(data.breakdown_beat_indices),
            track_weight=tw)
        lib_scored += 1
        if grades:
            lib_graded += 1
        if t["by_genre"] and has_row:
            n_by_genre_eligible += 1
            if grades:
                n_graded += 1
                wt = [g["within_track"] for g in grades]
                spread = max(wt) - min(wt)
                spreads.append(spread)
                if spread >= SPREAD_MIN:
                    n_spread_ok += 1

    if forced_partial:
        accepted, reason = False, "partial_run"
    else:
        accepted, reason = gates_verdict(n_by_genre_eligible, n_graded,
                                         n_spread_ok)

    emit("# Energy E2 — per-section grade report")
    emit("# OFFLINE / read-only. Bridge unchanged. Grades are STATUS-ONLY (no consumer).")
    emit("")
    emit("store: %s" % ("loaded (E1 accepted)" if store else "refused_or_missing"))
    emit("by_genre tracks total: %d" % n_by_genre_total)
    emit("  eligible (v4 + store row): %d   graded: %d   spread_ok(>=%.2f): %d"
         % (n_by_genre_eligible, n_graded, SPREAD_MIN, n_spread_ok))
    emit("  no_grid: %d   no_v4: %d" % (counts["no_grid"], counts["no_v4"]))
    emit("  library-wide (informational): scored %d, graded %d"
         % (lib_scored, lib_graded))
    # F1 MUST-print absolute coverage line (store/cache hole visibility)
    abs_cov = (n_by_genre_eligible / n_by_genre_total) if n_by_genre_total else 0.0
    emit("  absolute coverage n_by_genre_eligible/n_by_genre_total = %d/%d = %.3f (INFORMATIONAL)"
         % (n_by_genre_eligible, n_by_genre_total, abs_cov))
    emit("")
    g1 = (n_graded / n_by_genre_eligible) if n_by_genre_eligible else 0.0
    g2 = (n_spread_ok / n_graded) if n_graded else 0.0
    emit("ACCEPTANCE: %s   reason=%s" % ("ACCEPTED" if accepted else "NOT ACCEPTED",
                                         reason))
    emit("  G1 coverage  n_graded/n_by_genre_eligible = %.3f  (gate >= %.2f)"
         % (g1, COVERAGE_GATE))
    emit("  G2 spread    n_spread_ok/n_graded = %.3f  (gate >= %.2f at spread >= %.2f)"
         % (g2, SPREAD_GATE_FRACTION, SPREAD_MIN))
    if spreads:
        ss = sorted(spreads)
        emit("  within_track spread: min %.3f  median %.3f  max %.3f"
             % (ss[0], ss[len(ss) // 2], ss[-1]))
    if forced_partial:
        emit("")
        emit("!! PARTIAL RUN (--limit %s): acceptance forced FALSE (partial_run)."
             % args.limit)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
