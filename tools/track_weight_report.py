"""Offline library track-weight report — energy-fabric stage E1 (AWR-286,
revised by AWR-291).

Read-only corpus sweep: enumerates on-disk Rekordbox tracks + the BY GENRE
playlist folder, loads each track's cached v4 spectral features, computes the
gain-invariant track-weight components (``track_weight_v0``), builds the
library-relative weight, checks the three pinned acceptance controls on the
by_genre split — loudness, dynamic-range compression, and component redundancy —
writes a version-owned sidecar store, and prints a human report.

ZERO runtime behavior change: nothing in the bridge imports this tool or the
descriptor module (a static test enforces that). The Rekordbox DB, ANLZ files,
audio, and the v3/v4 cache dirs are READ-ONLY; the only thing written is
``<cache_dir>/trackweight_v1/track_weight_store.json`` (+ optional ``--out``).
The store is machine-local and must NEVER be committed.

Advisory: run this AFTER a mixing session, not during — it is offline and only
adds disk reads, but there is no reason to compete for I/O mid-set.

No threshold tuning to pass: a failed acceptance is a valid result — reported
plainly, exit 1. Changing any pinned constant is a spec amendment for the exec.
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache  # noqa: E402
from rb_ss_bridge_v2 import track_weight_v0  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import read_anlz_drops  # noqa: E402
from rb_ss_bridge_v2.drop_energy_v0 import drop_body_levels  # noqa: E402
from rb_ss_bridge_v2.track_weight_v0 import (  # noqa: E402
    COMPONENT_CORRELATION_MAX,
    COMPONENT_KEYS,
    DRAMA_ACCEPT_MAX,
    MIN_BEATS,
    REL_BODY_OFFSET_DB,
    SPEARMAN_ACCEPT_MAX,
    acceptance_verdict,
    build_distribution,
    components,
    degenerate_components,
    robust_dynamic_range,
    spearman,
    track_weight,
    _percentile,
)

SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
DB_PATH = Path("~/Library/Pioneer/rekordbox/master.db").expanduser()
BY_GENRE_FOLDER_ID = "666898931"          # the 25-child BY GENRE folder
BY_GENRE_EXCLUDE = {"RAP"}
STORE_SUBDIR = "trackweight_v1"
STORE_NAME = "track_weight_store.json"


# --------------------------------------------------------------------------- #
# Rekordbox enumeration (same read-only DB access as spectral_calibration)    #
# --------------------------------------------------------------------------- #
def _open_db() -> Any:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    return Rekordbox6Database(str(DB_PATH), unlock=True)


def _enumerate(db: Any) -> "tuple[list, dict]":
    """On-disk active tracks + {content_id: {BY GENRE playlist names}}."""
    genre_pls = [
        p for p in db.get_playlist()
        if str(getattr(p, "ParentID", "")) == BY_GENRE_FOLDER_ID
        and str(getattr(p, "Name", "")) not in BY_GENRE_EXCLUDE
    ]
    cid_playlists: "dict[str, set]" = {}
    for pl in genre_pls:
        name = str(pl.Name)
        for row in db.get_playlist_songs(PlaylistID=str(pl.ID)):
            cid_playlists.setdefault(str(row.ContentID), set()).add(name)

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
                       "filepath": filepath, "anlz_abs": anlz_abs})
    tracks.sort(key=lambda t: t["content_id"])
    return tracks, cid_playlists


def _grid_for(anlz_abs: str) -> "tuple[list, list]":
    """(beatgrid_times_ms, drop_beat_indices) from the ANLZ, or ([], []) when
    absent/short. Returns the drop markers too so the corpus drop-level
    distribution is built from the SAME file open, not a second parse (EREV1 N4)."""
    if not anlz_abs or not os.path.isfile(anlz_abs):
        return [], []
    data = read_anlz_drops(anlz_abs)
    ctx = data.waveform_context
    if ctx is not None and len(ctx.beatgrid_times_ms) >= 2:
        return list(ctx.beatgrid_times_ms), list(data.drop_beat_indices)
    return [], []


# --------------------------------------------------------------------------- #
# Pure store build/write (test seam)                                          #
# --------------------------------------------------------------------------- #
def build_store(scored: "Sequence[dict]", distribution: "dict",
                acceptance: "dict", generated_unix: int,
                drop_body_levels_by_genre: "Sequence[float]" = ()) -> "dict":
    """Pure store dict (schema v2, AWR-291). `scored` items carry cache_key/
    filepath/content_id/title/components/track_weight. `acceptance` carries
    accepted/reason/rho_by_genre/n_by_genre/rho_library/rho_drama/
    rho_components_max/degenerate. `drop_body_levels_by_genre` is the accumulated
    corpus drop-window level distribution (E3's body-term fallback)."""
    tracks = {}
    for r in scored:
        tracks[r["cache_key"]] = {
            "filepath": r["filepath"], "content_id": r["content_id"],
            "title": r["title"], "components": r["components"],
            "track_weight": r["track_weight"]}
    return {
        "schema_version": track_weight_v0.STORE_SCHEMA_VERSION,   # == 2
        "generated_unix": int(generated_unix),
        "accepted": bool(acceptance["accepted"]),
        "acceptance": {
            "reason": acceptance["reason"],
            "spearman_by_genre": acceptance["rho_by_genre"],
            "threshold": SPEARMAN_ACCEPT_MAX,
            "n_by_genre": acceptance["n_by_genre"],
            "spearman_library": acceptance["rho_library"],
            "spearman_drama": acceptance.get("rho_drama"),
            "drama_threshold": DRAMA_ACCEPT_MAX,
            "component_correlation_max": acceptance.get("rho_components_max"),
            "component_correlation_threshold": COMPONENT_CORRELATION_MAX,
            "degenerate": list(acceptance["degenerate"])},
        "constants": {
            "rel_body_offset_db": REL_BODY_OFFSET_DB,
            "min_beats": MIN_BEATS,
            "component_keys": list(COMPONENT_KEYS)},
        "distribution": {k: list(distribution.get(k, [])) for k in COMPONENT_KEYS},
        "drop_body_distribution": sorted(drop_body_levels_by_genre),
        "tracks": tracks}


def write_store(store: "dict", cache_dir: "Path") -> "Path":
    """Atomic write (tempfile + os.replace, the put_cached_v4 pattern) to
    <cache_dir>/trackweight_v1/track_weight_store.json."""
    import json
    out_dir = Path(cache_dir) / STORE_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / STORE_NAME
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=out_dir,
                                         prefix=".store.", suffix=".tmp",
                                         delete=False) as fp:
            tmp_name = fp.name
            json.dump(store, fp, sort_keys=True)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_name, path)
    except OSError:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass
        raise
    return path


# --------------------------------------------------------------------------- #
# Report rendering                                                            #
# --------------------------------------------------------------------------- #
def _five_num(values: "Sequence[float]") -> str:
    v = sorted(values)
    if not v:
        return "n/a"
    return "min %.4f  p25 %.4f  p50 %.4f  p75 %.4f  max %.4f" % (
        v[0], _percentile(v, 25), _percentile(v, 50), _percentile(v, 75), v[-1])


def _fmt_rho(x: "Optional[float]") -> str:
    return "%.4f" % x if x is not None else "None"


def _fmt_signed(x: "Optional[float]") -> str:
    return "%+.4f" % x if x is not None else "None"


def run(argv: "Sequence[str]") -> int:
    ap = argparse.ArgumentParser(description="Offline E1 track-weight report")
    ap.add_argument("--cache-dir", default=None,
                    help="override RBSS_SPECTRAL_CACHE_DIR for this run")
    ap.add_argument("--out", default=None, help="also write the report text here")
    ap.add_argument("--limit", type=int, default=None,
                    help="DEV ONLY: truncate the track list; forces "
                         "acceptance=false reason=partial_run")
    args = ap.parse_args(list(argv))
    if args.cache_dir:
        os.environ["RBSS_SPECTRAL_CACHE_DIR"] = args.cache_dir

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
    except Exception as exc:                      # pyrekordbox missing / DB open
        sys.stderr.write("ENV ERROR: cannot open Rekordbox DB (%s): %s\n"
                         % (type(exc).__name__, exc))
        return 2

    tracks, cid_playlists = _enumerate(db)
    forced_partial = args.limit is not None
    if forced_partial:
        tracks = tracks[:max(0, args.limit)]

    counts = {"scope": 0, "no_grid": 0, "no_v4": 0, "insufficient": 0,
              "scored": 0}
    scored = []                                   # per-track scored records
    drop_body_by_genre = []                        # corpus drop-window levels (E3 fallback)
    for t in tracks:
        counts["scope"] += 1
        grid, drop_beats = _grid_for(t["anlz_abs"])
        if not grid:
            counts["no_grid"] += 1
            continue
        v4 = spectral_cache.get_cached_v4(t["filepath"], grid)
        if v4 is None:
            counts["no_v4"] += 1
            continue
        comp = components(v4)
        if comp is None:
            counts["insufficient"] += 1
            continue
        key = spectral_cache._cache_key(t["filepath"], grid)
        if key is None:
            counts["insufficient"] += 1
            continue
        counts["scored"] += 1
        is_by_genre = t["content_id"] in cid_playlists
        scored.append({
            "cache_key": key, "filepath": t["filepath"],
            "content_id": t["content_id"], "title": t["title"],
            "components": comp,
            "loudness_ref_db": float(v4.scalars["loudness_ref_db"]),
            "robust_dynamic_range": robust_dynamic_range(v4),
            "is_by_genre": is_by_genre,
            "playlists": sorted(cid_playlists.get(t["content_id"], set()))})
        if is_by_genre:
            drop_body_by_genre.extend(drop_body_levels(v4, drop_beats))

    distribution = build_distribution([r["components"] for r in scored]) \
        if scored else {k: [] for k in COMPONENT_KEYS}
    for r in scored:
        r["track_weight"] = track_weight(r["components"], distribution)

    by_genre = [r for r in scored if r["is_by_genre"]]
    rho_by_genre = spearman([r["loudness_ref_db"] for r in by_genre],
                            [r["track_weight"] for r in by_genre])
    rho_library = spearman([r["loudness_ref_db"] for r in scored],
                           [r["track_weight"] for r in scored])
    # 2a: compression negative control (dynamic-range proxy, by_genre)
    rd_pairs = [(r["track_weight"], r["robust_dynamic_range"]) for r in by_genre
                if r["robust_dynamic_range"] is not None]
    rho_drama = (spearman([p[0] for p in rd_pairs], [p[1] for p in rd_pairs])
                 if rd_pairs else None)
    # 2a-bis: full component correlation matrix + worst off-diagonal (by_genre)
    comp_series = {k: [r["components"][k] for r in by_genre] for k in COMPONENT_KEYS}
    comp_matrix = {}
    rho_components_max = None
    for a in COMPONENT_KEYS:
        for b in COMPONENT_KEYS:
            if a == b:
                comp_matrix[(a, b)] = 1.0
                continue
            rho = spearman(comp_series[a], comp_series[b])
            comp_matrix[(a, b)] = rho
            if rho is not None:
                rho_components_max = (abs(rho) if rho_components_max is None
                                      else max(rho_components_max, abs(rho)))
    degenerate = degenerate_components(distribution)

    if forced_partial:
        accepted, reason = False, "partial_run"
    else:
        accepted, reason = acceptance_verdict(len(by_genre), rho_by_genre,
                                              rho_drama, rho_components_max,
                                              degenerate)

    acceptance = {"accepted": accepted, "reason": reason,
                  "rho_by_genre": rho_by_genre, "n_by_genre": len(by_genre),
                  "rho_library": rho_library, "rho_drama": rho_drama,
                  "rho_components_max": rho_components_max,
                  "degenerate": degenerate}
    store = build_store(scored, distribution, acceptance, int(time.time()),
                        drop_body_levels_by_genre=drop_body_by_genre)
    store_path = write_store(store, cache_dir)

    # ---- report ----
    emit("# Energy E1 — library track-weight report")
    emit("# OFFLINE / read-only. Bridge unchanged. Run after sessions, not during.")
    emit("")
    emit("tracks in scope: %d" % counts["scope"])
    emit("  scored: %d   no_grid: %d   no_v4: %d   insufficient(short/malformed): %d"
         % (counts["scored"], counts["no_grid"], counts["no_v4"],
            counts["insufficient"]))
    emit("  by_genre scored: %d" % len(by_genre))
    emit("")
    if forced_partial:
        emit("!! PARTIAL RUN (--limit %s): acceptance forced FALSE (partial_run); "
             "NOT a valid acceptance result." % args.limit)
        emit("")
    emit("ACCEPTANCE: %s   reason=%s" % ("ACCEPTED" if accepted else "NOT ACCEPTED",
                                         reason))
    emit("  Spearman(loudness_ref_db, track_weight) by_genre = %s  (gate |rho| <= %.2f, n >= 100)"
         % (_fmt_rho(rho_by_genre), SPEARMAN_ACCEPT_MAX))
    emit("  Spearman(dynamic range p95-p25, track_weight) by_genre = %s  (gate |rho| <= %.2f, n >= 100)"
         % (_fmt_signed(rho_drama), DRAMA_ACCEPT_MAX))
    emit("  Spearman library-wide = %s  (INFORMATIONAL only)" % _fmt_rho(rho_library))
    emit("  degenerate components: %s" % (degenerate or "none"))
    emit("")
    # 2a-bis: component correlation matrix + gated worst off-diagonal
    _abbr = {"body_duty": "body_duty", "brightness_med": "brightness",
             "onset_mh_mean": "onset_mh", "growl_flatness_mean": "growl_flat"}
    emit("## Component correlation (by_genre) — gate: worst |rho| <= %.2f"
         % COMPONENT_CORRELATION_MAX)
    emit("  %-20s%s" % ("", "".join("%11s" % _abbr[k] for k in COMPONENT_KEYS)))
    for a in COMPONENT_KEYS:
        cells = "".join(
            ("%+11.3f" % comp_matrix[(a, b)]) if comp_matrix[(a, b)] is not None
            else "%11s" % "None" for b in COMPONENT_KEYS)
        emit("  %-20s%s" % (_abbr[a], cells))
    emit("  worst |rho| between components = %s   (gate <= %.2f)"
         % (("%.4f" % rho_components_max) if rho_components_max is not None
            else "None", COMPONENT_CORRELATION_MAX))
    emit("  corpus drop-body levels (E3 fallback distribution): %d"
         % len(drop_body_by_genre))
    emit("")
    emit("## Component distributions (library, all scored)")
    for k in COMPONENT_KEYS:
        emit("  %-20s %s" % (k, _five_num(distribution[k])))
    emit("  %-20s %s" % ("track_weight",
                         _five_num([r["track_weight"] for r in scored])))
    emit("")
    ranked = sorted(scored, key=lambda r: (-r["track_weight"], r["content_id"]))
    emit("## Top 15 by weight")
    for r in ranked[:15]:
        emit("  %.4f  %s" % (r["track_weight"], r["title"][:70]))
    emit("## Bottom 15 by weight")
    for r in ranked[-15:]:
        emit("  %.4f  %s" % (r["track_weight"], r["title"][:70]))
    emit("")
    emit("## Per BY-GENRE-playlist median weight (descriptive; read is optional)")
    pl_weights: "dict[str, list]" = {}
    for r in by_genre:
        for name in r["playlists"]:
            pl_weights.setdefault(name, []).append(r["track_weight"])
    for name in sorted(pl_weights, key=lambda n: -_percentile(sorted(pl_weights[n]), 50)):
        med = _percentile(sorted(pl_weights[name]), 50)
        emit("  %.4f  (n=%d)  %s" % (med, len(pl_weights[name]), name))
    emit("")
    emit("store written: %s (accepted=%s) — machine-local, never commit"
         % (store_path, accepted))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
