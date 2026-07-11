#!/usr/bin/env python3
"""Offline, read-only evaluator for the hardness_v0 shadow descriptor (AWR-203).

Reports the deterministic descriptive evidence you can get WITHOUT structured
independent ear gold. It makes NO taste-accuracy, held-out-improvement, or
readiness claim, and it does not run group bootstrap / accuracy scoring (there
is no structured gold yet). It is read-only: it opens the Rekordbox master.db
READ-ONLY (via the shared enumerator), reads current ANLZ beatgrids, and reads
the v4 spectral cache. It never extracts, writes, or touches the running bridge.

Cache identity rule (the stale-copy defense): every track is resolved
content_id -> current filepath -> current ANLZ beatgrid ->
spectral_cache.get_cached_v4(filepath, grid). The v4 cache is FORWARD-KEYED on
sha1(realpath, mtime_ns, size, beatgrid_fingerprint), so a non-None return is
already provably the current entry — a stale-grid or moved-file copy has a
different key and is unreachable. As defense-in-depth we additionally re-read
the one current-key payload and assert its stored audio_filepath +
beatgrid_fingerprint match. We never enumerate raw cache JSON.

Usage:
    python3 tools/hardness_ablation.py --self-check       # synthetic, no I/O
    python3 tools/hardness_ablation.py --limit 25         # small read-only run
    python3 tools/hardness_ablation.py                    # full corpus
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> rb_ss_bridge_v2 package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> tools.* package

from rb_ss_bridge_v2 import hardness_v0, spectral_cache  # noqa: E402

REDUCERS = hardness_v0.REDUCERS
PATHS = hardness_v0.PATHS
BOUNDARY_LO, BOUNDARY_HI = 0.8, 1.2
STRATA = (("1", 1, 1), ("2", 2, 2), ("3-4", 3, 4), ("5-7", 5, 7), ("8+", 8, 10 ** 9))


# --- cache identity (read-only; reads exactly the current-key payload) ----------
def verify_identity(filepath: str, grid) -> str:
    """'ok' if the current-key cache payload matches current realpath+grid, else why not.

    Uses the cache module's own key/fingerprint helpers so it stays bit-identical
    to what get_cached_v4 keys on. Reads only the current-key file — never a scan.
    """
    key = spectral_cache._cache_key(filepath, grid)
    if key is None:
        return "unresolvable"
    path = spectral_cache._cache_dir_v4() / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "missing"
    if payload.get("audio_filepath") != os.path.realpath(filepath):
        return "realpath_mismatch"
    if payload.get("beatgrid_fingerprint") != spectral_cache._beatgrid_fingerprint(grid):
        return "fingerprint_mismatch"
    return "ok"


def resolve_track(track: dict):
    """Return (v4, grid, valid_drops) for a current track, or ('reason', None, None)."""
    from rb_ss_bridge_v2.anlz_reader import read_anlz_drops

    anlz = track.get("anlz_abs") or ""
    if not anlz or not os.path.isfile(anlz):
        return ("no_anlz", None, None)
    try:
        data = read_anlz_drops(anlz)
    except Exception:  # ANLZ parse is best-effort; a bad file reads as no signal
        return ("anlz_error", None, None)
    ctx = data.waveform_context
    if ctx is None or len(ctx.beatgrid_times_ms) < 2:
        return ("no_grid", None, None)
    grid = list(ctx.beatgrid_times_ms)
    v4 = spectral_cache.get_cached_v4(track["filepath"], grid)
    if v4 is None:
        return ("uncached", None, None)
    identity = verify_identity(track["filepath"], grid)
    if identity != "ok":
        return (f"identity_{identity}", None, None)
    drops = [int(d) for d in data.drop_beat_indices if 0 <= int(d) < v4.n_beats]
    if not drops:
        return ("no_drops", None, None)
    return (v4, grid, drops)


# --- per-track scoring (done while v4 is in scope; only scalars retained) -------
def score_track(cid: str, title: str, v4, drops):
    """All per-drop metrics for one track, or None if a baseline can't be formed."""
    n_beats = v4.n_beats
    bases = {r: hardness_v0.track_baseline(v4, drops, reducer=r) for r in REDUCERS}
    if any(b is None for b in bases.values()):
        return None
    reducer_drop_t3 = {r: 0 for r in REDUCERS}
    reducer_track_t3 = {r: False for r in REDUCERS}
    drop_rows = []
    for d in drops:
        hs = {r: hardness_v0.hardness_result(v4, d, bases[r], reducer=r) for r in REDUCERS}
        for r in REDUCERS:
            if hs[r].t3:
                reducer_drop_t3[r] += 1
                reducer_track_t3[r] = True
        mx = hs["max"]
        row = {
            "cid": cid,
            "h_max": mx.h,
            "t3_max": mx.t3,
            "winning_path": mx.winning_path,
            "paths": (mx.repeated_wall, mx.abrasive_hammer, mx.growling_hammer),
            "manufactured": hs["center"].h < 1.0 <= mx.h,
            "boundary": BOUNDARY_LO <= mx.h <= BOUNDARY_HI,
        }
        # marker flips (max reducer): does the T3 verdict move if the MARKER slides?
        shift = {}
        for q in (-2, -1, 0, 1, 2):
            dq = d + q
            if 0 <= dq < n_beats:
                r = hardness_v0.hardness_result(v4, dq, bases["max"], reducer="max")
                if r is not None:
                    shift[q] = r.t3
        base_t3 = shift.get(0)
        row["cmp_pm1"] = base_t3 is not None and (-1 in shift or 1 in shift)
        row["cmp_pm2"] = base_t3 is not None and (-2 in shift or 2 in shift)
        row["flip_pm1"] = row["cmp_pm1"] and any(shift[q] != base_t3 for q in (-1, 1) if q in shift)
        row["flip_pm2"] = row["cmp_pm2"] and any(shift[q] != base_t3 for q in (-2, 2) if q in shift)
        drop_rows.append(row)
    return {
        "cid": cid,
        "title": title,
        "n_drops": len(drops),
        "t3_any_max": any(row["t3_max"] for row in drop_rows),
        "reducer_drop_t3": reducer_drop_t3,
        "reducer_track_t3": reducer_track_t3,
        "drop_rows": drop_rows,
    }


# --- reporting ------------------------------------------------------------------
def _pct(n, d):
    return f"{(100.0 * n / d):.2f}%" if d else "n/a"


def _flip_block(tracks, rows, *, boundary_only=False) -> str:
    cmp1 = sum(1 for r in rows if r["cmp_pm1"])
    cmp2 = sum(1 for r in rows if r["cmp_pm2"])
    f1 = sum(1 for r in rows if r["flip_pm1"])
    f2 = sum(1 for r in rows if r["flip_pm2"])
    lines = [
        f"- micro (per-drop): +/-1 flip {f1}/{cmp1} = {_pct(f1, cmp1)}; "
        f"+/-2 flip {f2}/{cmp2} = {_pct(f2, cmp2)}",
    ]
    if not boundary_only:
        def macro(field, cmpf):
            per = []
            for t in tracks:
                d = [row for row in t["drop_rows"] if row[cmpf]]
                if d:
                    per.append(sum(1 for row in d if row[field]) / len(d))
            return (sum(per) / len(per) if per else 0.0), len(per)
        m1, n1 = macro("flip_pm1", "cmp_pm1")
        m2, n2 = macro("flip_pm2", "cmp_pm2")
        lines.append(f"- track-macro: +/-1 {m1 * 100:.2f}% over {n1} tracks; "
                     f"+/-2 {m2 * 100:.2f}% over {n2} tracks")
    return "\n".join(lines)


def build_report(tracks, coverage, *, scope_note: str) -> str:
    drop_rows = [row for t in tracks for row in t["drop_rows"]]
    n_tracks = len(tracks)
    n_drops = len(drop_rows)
    out = []
    w = out.append
    w("# hardness_v0 offline ablation — descriptive evidence only")
    w("")
    w("**NOT** a taste-accuracy, held-out-improvement, or readiness claim. `H>=1` is")
    w("path-threshold firing, not a validated boundary. In-sample, binary T3 only.")
    w(f"Formula freeze: ANCHORS={hardness_v0.ANCHORS} PATH_THRESHOLDS={hardness_v0.PATH_THRESHOLDS}")
    w(f"ALIGN_WEIGHTS={hardness_v0.ALIGN_WEIGHTS} ALIGN_RADIUS={hardness_v0.ALIGN_RADIUS} "
      f"T3_GATE={hardness_v0.T3_GATE} MIN_STABLE_DROPS={hardness_v0.MIN_STABLE_DROPS}")
    w("")
    w("## Coverage")
    w(f"- scope: {scope_note}")
    for k in ("enumerated", "no_anlz", "anlz_error", "no_grid", "uncached", "no_drops"):
        if k in coverage:
            w(f"- {k}: {coverage[k]}")
    for k in sorted(coverage):
        if k.startswith("identity_"):
            w(f"- {k}: {coverage[k]}  (cache-identity reject — NOT scored)")
    w(f"- scored tracks: {n_tracks}")
    w(f"- scored drops: {n_drops}")
    if n_drops == 0:
        w("")
        w("No scored drops — nothing further to report (uncached corpus or no current cache).")
        return "\n".join(out)

    w("")
    w("## Reducer prevalence (T3 rate)")
    w("| reducer | drop T3 | track-any T3 |")
    w("|---|---|---|")
    for r in REDUCERS:
        drop_n = sum(t["reducer_drop_t3"][r] for t in tracks)
        track_n = sum(1 for t in tracks if t["reducer_track_t3"][r])
        w(f"| {r} | {_pct(drop_n, n_drops)} | {_pct(track_n, n_tracks)} |")

    manufactured = sum(1 for row in drop_rows if row["manufactured"])
    w("")
    w("## Manufactured-T3 fraction (argmax selection bias)")
    w(f"- drops with H_center < 1.0 <= H_max: {manufactured}/{n_drops} = {_pct(manufactured, n_drops)}")
    w("  (T3s that exist only because the +/-2 alignment search took the max)")

    w("")
    w("## Per-path counts (max reducer, true marker)")
    w("| path | won | standalone (>=1) | unique (only this >=1) |")
    w("|---|---|---|---|")
    idx = {p: i for i, p in enumerate(PATHS)}
    for p in PATHS:
        won = sum(1 for row in drop_rows if row["winning_path"] == p)
        standalone = sum(1 for row in drop_rows if row["paths"][idx[p]] >= 1.0)
        unique = sum(1 for row in drop_rows
                     if row["paths"][idx[p]] >= 1.0
                     and all(row["paths"][idx[q]] < 1.0 for q in PATHS if q != p))
        w(f"| {p} | {won} | {standalone} | {unique} |")

    w("")
    w("## n_drops stability strata")
    w("| stratum | tracks | track-any T3 (max) |")
    w("|---|---|---|")
    for label, lo, hi in STRATA:
        bucket = [t for t in tracks if lo <= t["n_drops"] <= hi]
        t3 = sum(1 for t in bucket if t["t3_any_max"])
        w(f"| {label} | {len(bucket)} | {_pct(t3, len(bucket))} |")
    unstable = sum(1 for t in tracks if t["n_drops"] < hardness_v0.MIN_STABLE_DROPS)
    w(f"- tracks with n_drops < MIN_STABLE_DROPS ({hardness_v0.MIN_STABLE_DROPS}), "
      f"unstable T*: {unstable}/{n_tracks}")

    w("")
    w("## Marker-shift T3 flips (max reducer)")
    w(_flip_block(tracks, drop_rows))

    boundary = [row for row in drop_rows if row["boundary"]]
    w("")
    w(f"## Boundary-conditioned flips (H_max in [{BOUNDARY_LO}, {BOUNDARY_HI}])")
    w(_flip_block(tracks, boundary, boundary_only=True) if boundary
      else "- no drops in the boundary band")

    w("")
    w("## Candidate caveats (do not read as separation)")
    for line in (
        "H>=1.0 is a tautology for 'a path fired', NOT an independent boundary.",
        "repeated_wall is a per-track verdict (uses only T*), stamped on every drop "
        "of a track including its soft markers.",
        "B is near-pure loudness (~0.26/dB); on a non-loudness-matched holdout, "
        "repeated_wall/abrasive partly become loudness detectors.",
        "max reducer inflates local terms vs center (see manufactured-T3 fraction).",
        "all separation is in-sample; anchors+thresholds were hand-iterated on the "
        "same named pins. No independent gold exists, so accuracy is UNSCORED here.",
        "REWIND/Latch-class provisional-grid tracks move on reanalysis — directional "
        "smoke tests only.",
    ):
        w(f"- {line}")
    return "\n".join(out)


# --- corpus + self-check drivers ------------------------------------------------
def run_corpus(limit=None):
    from tools.spectral_sweep import _enumerate_tracks

    source = _enumerate_tracks()
    if limit:
        source = source[:limit]
    coverage = {"enumerated": len(source)}
    scored = []
    for track in source:
        v4, grid, drops = resolve_track(track)
        if grid is None:
            reason = v4  # the reason string
            coverage[reason] = coverage.get(reason, 0) + 1
            continue
        entry = score_track(track["content_id"], track.get("title", ""), v4, drops)
        if entry is None:
            coverage["no_baseline"] = coverage.get("no_baseline", 0) + 1
            continue
        scored.append(entry)
    return scored, coverage


def _synthetic_tracks():
    """Two in-memory tracks (no DB/cache) so --self-check proves the whole pipeline."""
    n = 32
    hard = {
        "full_db": [17.0] * n, "high_db": [3.0] * n,
        "growl_band_db": [30.0] * n, "growl_flatness": [0.28] * n,
        "onset_density_midhigh": [3.0] * n,
    }
    soft = {
        "full_db": [12.0] * n, "high_db": [-6.0] * n,
        "growl_band_db": [0.0] * n, "growl_flatness": [0.0] * n,
        "onset_density_midhigh": [0.5] * n,
    }

    def mk(series):
        s = {k: tuple(float(x) for x in v) for k, v in series.items()}
        for k in hardness_v0._REQUIRED_SERIES:
            s.setdefault(k, (0.0,) * n)
        return SimpleNamespace(n_beats=n, series=s)

    return [
        ("HARD", "synthetic hard", mk(hard), [0, 6, 12, 18, 24]),
        ("SOFT", "synthetic soft", mk(soft), [0, 6, 12, 18, 24]),
    ]


def run_self_check():
    scored = [score_track(cid, title, v4, drops) for cid, title, v4, drops in _synthetic_tracks()]
    return scored, {"enumerated": len(scored)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None,
                    help="score only the first N enumerated tracks")
    ap.add_argument("--self-check", action="store_true",
                    help="run the metric pipeline on 2 synthetic tracks (no DB/cache/ANLZ I/O)")
    args = ap.parse_args(argv)

    if args.self_check:
        scored, coverage = run_self_check()
        note = "SELF-CHECK synthetic tracks (no external I/O)"
    else:
        scored, coverage = run_corpus(limit=args.limit)
        note = "current Rekordbox tracks resolved through current ANLZ grid + v4 cache (read-only)"
        if args.limit:
            note += f"; first {args.limit} enumerated"
    print(build_report(scored, coverage, scope_note=note))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
