"""Offline per-section energy-grade report — energy-fabric stage E2 (AWR-288,
revised by AWR-291).

Read-only corpus sweep: enumerates the BY GENRE Rekordbox tracks, loads each
track's cached v4 features + the E1 track-weight store (through the ONE refusal
gate `section_energy_v0.load_track_weight_store`, shared with the runtime),
computes per-section grades, and evaluates the four pinned gates: G1 coverage,
G2 saturation, G3 rankability, G4 separation. Writes NO store (E2 has no
sidecar); `--out` copies the report text only.

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
    COVERAGE_GATE,
    RANKABILITY_GATE,
    SATURATION_GATE_MAX,
    SEPARATION_GATE,
    gates_verdict,
    grade_sections,
    load_track_weight_store,
    store_track_weight,
)

JITTER_OFFSETS = (-4, -2, -1, 1, 2, 4)


def _pct(sorted_vals, q):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    pos = (q / 100.0) * (n - 1)
    lo, hi = int(pos), min(int(pos) + 1, n - 1)
    return sorted_vals[lo] * (1 - (pos - lo)) + sorted_vals[hi] * (pos - lo)


def _shift(markers, off, n):
    """Every marker moved by `off` beats, clamped into [0, n]. Sliding all markers
    slides every section boundary — the boundary-jitter probe (E2-c)."""
    return [min(max(0, int(m) + off), n) for m in markers]

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
    n_chorus_tracks = 0            # eligible tracks with >= 3 chorus sections
    n_chorus_rankable = 0          # ... of those, with >= 2 distinct chorus grades
    lib_graded = 0
    lib_scored = 0
    counts = {"no_grid": 0, "no_v4": 0}
    all_section_withins = []       # every graded by_genre section (G2 saturation)
    chorus_withins = []            # chorus sections (G4 + 4c bottom-rail)
    low_withins = []               # 'low' sections (G4 separation)
    jitter = {off: [] for off in JITTER_OFFSETS}   # 4b, report-only
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
        drops = list(data.drop_beat_indices)
        buildups = list(data.buildup_beat_indices)
        breakdowns = list(data.breakdown_beat_indices)
        grades = grade_sections(
            v4, anlz_drops=drops, anlz_buildups=buildups,
            anlz_breakdowns=breakdowns, track_weight=tw)
        lib_scored += 1
        if grades:
            lib_graded += 1
        if t["by_genre"] and has_row:
            n_by_genre_eligible += 1
            if grades:
                n_graded += 1
                chorus_here = []
                for g in grades:
                    w = g["within_track"]
                    all_section_withins.append(w)
                    if g["label"] == "chorus":
                        chorus_withins.append(w)
                        chorus_here.append(w)
                    elif g["label"] == "low":
                        low_withins.append(w)
                if len(chorus_here) >= 3:
                    n_chorus_tracks += 1
                    if len(set(chorus_here)) >= 2:
                        n_chorus_rankable += 1
                # 4b boundary-jitter: slide every marker by `off` and re-grade
                n_beats = int(v4.n_beats)
                base = grades
                for off in JITTER_OFFSETS:
                    sh = grade_sections(
                        v4, anlz_drops=_shift(drops, off, n_beats),
                        anlz_buildups=_shift(buildups, off, n_beats),
                        anlz_breakdowns=_shift(breakdowns, off, n_beats),
                        track_weight=None)
                    for a, b in zip(base, sh):
                        jitter[off].append(abs(b["within_track"] - a["within_track"]))

    railed_fraction = (sum(1 for w in all_section_withins if w <= 0.0 or w >= 1.0)
                       / len(all_section_withins)) if all_section_withins else None
    rankable_fraction = (n_chorus_rankable / n_chorus_tracks) if n_chorus_tracks else None
    chorus_med = _pct(sorted(chorus_withins), 50) if chorus_withins else None
    low_med = _pct(sorted(low_withins), 50) if low_withins else None
    separation = (chorus_med - low_med) if (chorus_med is not None
                                            and low_med is not None) else None
    chorus_bottom = sum(1 for w in chorus_withins if w <= 0.0)

    if forced_partial:
        accepted, reason = False, "partial_run"
    else:
        accepted, reason = gates_verdict(n_by_genre_eligible, n_graded,
                                         railed_fraction, rankable_fraction,
                                         separation)

    emit("# Energy E2 — per-section grade report")
    emit("# OFFLINE / read-only. Bridge unchanged. Grades are STATUS-ONLY (no consumer).")
    emit("")
    emit("store: %s" % ("loaded (E1 accepted)" if store else "refused_or_missing"))
    emit("by_genre tracks total: %d" % n_by_genre_total)
    emit("  eligible (v4 + store row): %d   graded: %d   graded sections: %d"
         % (n_by_genre_eligible, n_graded, len(all_section_withins)))
    emit("  no_grid: %d   no_v4: %d" % (counts["no_grid"], counts["no_v4"]))
    emit("  library-wide (informational): scored %d, graded %d"
         % (lib_scored, lib_graded))
    # F1 MUST-print absolute coverage line (store/cache hole visibility)
    abs_cov = (n_by_genre_eligible / n_by_genre_total) if n_by_genre_total else 0.0
    emit("  absolute coverage n_by_genre_eligible/n_by_genre_total = %d/%d = %.3f (INFORMATIONAL)"
         % (n_by_genre_eligible, n_by_genre_total, abs_cov))
    emit("")
    g1 = (n_graded / n_by_genre_eligible) if n_by_genre_eligible else 0.0
    emit("ACCEPTANCE: %s   reason=%s" % ("ACCEPTED" if accepted else "NOT ACCEPTED",
                                         reason))
    emit("  G1 coverage    n_graded/n_by_genre_eligible = %.3f  (gate >= %.2f)"
         % (g1, COVERAGE_GATE))
    emit("  G2 saturation  railed fraction = %s  (gate <= %.2f)"
         % (("%.4f" % railed_fraction) if railed_fraction is not None else "n/a",
            SATURATION_GATE_MAX))
    emit("  G3 rankability chorus tracks (>=3) with >=2 distinct grades = %s  (gate >= %.2f, n=%d)"
         % (("%.4f" % rankable_fraction) if rankable_fraction is not None else "n/a",
            RANKABILITY_GATE, n_chorus_tracks))
    emit("  G4 separation  median(chorus) - median('low') = %s  (gate >= %.2f)"
         % (("%.4f" % separation) if separation is not None else "n/a",
            SEPARATION_GATE))
    emit("     median(chorus) = %s ; median('low') = %s"
         % (("%.4f" % chorus_med) if chorus_med is not None else "n/a",
            ("%.4f" % low_med) if low_med is not None else "n/a"))
    # 4c bottom-rail chorus fraction, counted DIRECTLY over all chorus sections
    n_chorus = len(chorus_withins)
    pct_bottom = (100.0 * chorus_bottom / n_chorus) if n_chorus else 0.0
    emit("  chorus sections at the bottom rail = %d / %d = %.2f%%  (INFORMATIONAL; median aggregator, expect ~0.6%%)"
         % (chorus_bottom, n_chorus, pct_bottom))
    emit("")
    emit("## Boundary-jitter sensitivity (INFORMATIONAL — not a gate)")
    emit("  offset  median |delta|  p90 |delta|")
    for off in JITTER_OFFSETS:
        ds = sorted(jitter[off])
        med = _pct(ds, 50)
        p90 = _pct(ds, 90)
        emit("  %+d      %s          %s"
             % (off, ("%.4f" % med) if med is not None else "n/a",
                ("%.4f" % p90) if p90 is not None else "n/a"))
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
