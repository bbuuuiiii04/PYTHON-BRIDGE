#!/usr/bin/env python3
"""Offline whole-library spectral v4 sweep (read-only except the v4 cache).

Enumerates active Rekordbox tracks whose audio exists on disk, resolves each
beatgrid through the same ``read_anlz_drops`` the runtime uses, extracts the
v4 analysis, and writes v4 cache entries. Never touches v3 entries, the
Rekordbox DB, ANLZ files, or audio files.

Backfill-aware skip: an entry counts as "cached" only when it already carries
the growl_centroid_frames field (AWR-176). Pre-AWR-176 v4 entries still parse
(tolerant read) but lack that field, so an ordinary re-run re-extracts and
overwrites exactly them — the standard sweep IS the backfill run.

Run under caffeinate so the machine cannot sleep mid-sweep:

    caffeinate -i python3 tools/spectral_sweep.py --jobs 2

``--verify N`` proves runtime/sweep cache-key parity on N sample tracks
(identical beatgrid fingerprints from every ANLZ sibling candidate path).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
DB_PATH = Path("~/Library/Pioneer/rekordbox/master.db").expanduser()


def _enumerate_tracks() -> list[dict[str, str]]:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore

    db = Rekordbox6Database(str(DB_PATH), unlock=True)
    tracks: list[dict[str, str]] = []
    try:
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
    finally:
        db.close()
    tracks.sort(key=lambda t: t["content_id"])
    return tracks


def _worker_init() -> None:
    # One BLAS/FFT thread per worker; parallelism comes from processes.
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["VECLIB_MAXIMUM_THREADS"] = "1"


def _sweep_one(track: dict[str, str]) -> tuple[str, str, float]:
    from rb_ss_bridge_v2 import spectral_cache
    from rb_ss_bridge_v2.anlz_reader import read_anlz_drops
    from rb_ss_bridge_v2.audio_spectral_features import extract_spectral_features_v4

    started = time.perf_counter()
    if not track["anlz_abs"] or not os.path.isfile(track["anlz_abs"]):
        return ("no_anlz", track["title"], 0.0)
    data = read_anlz_drops(track["anlz_abs"])
    ctx = data.waveform_context
    if ctx is None or len(ctx.beatgrid_times_ms) < 2:
        return ("no_grid", track["title"], time.perf_counter() - started)
    grid = list(ctx.beatgrid_times_ms)
    cached = spectral_cache.get_cached_v4(track["filepath"], grid)
    if cached is not None and cached.growl_centroid_frames:
        return ("cached", track["title"], time.perf_counter() - started)
    features = extract_spectral_features_v4(track["filepath"], grid)
    if features is None:
        return ("extract_failed", track["title"], time.perf_counter() - started)
    spectral_cache.put_cached_v4(track["filepath"], grid, features)
    return ("ok", track["title"], time.perf_counter() - started)


def _verify_key_parity(tracks: list[dict[str, str]], count: int) -> int:
    """Prove every ANLZ sibling candidate path yields the same cache key."""
    from rb_ss_bridge_v2.anlz_reader import read_anlz_drops
    from rb_ss_bridge_v2.spectral_cache import _beatgrid_fingerprint

    checked = 0
    failures = 0
    for track in tracks:
        if checked >= count:
            break
        base = Path(track["anlz_abs"])
        if not base.is_file():
            continue
        siblings = [
            base.with_suffix(ext)
            for ext in (".DAT", ".EXT", ".2EX")
            if base.with_suffix(ext).is_file()
        ]
        if len(siblings) < 2:
            continue
        prints = set()
        for candidate in siblings:
            data = read_anlz_drops(str(candidate))
            ctx = data.waveform_context
            if ctx is None:
                continue
            prints.add(_beatgrid_fingerprint(list(ctx.beatgrid_times_ms)))
        if not prints:
            continue  # no candidate has a beatgrid (FX one-shots) — nothing to mismatch
        checked += 1
        if len(prints) != 1:
            failures += 1
            print(f"PARITY FAIL: {track['title']} fingerprints={prints}")
    print(f"key parity: {checked - failures}/{checked} tracks consistent across ANLZ siblings")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2,
                        help="parallel extraction processes (default 2 — sized for 8 GB RAM)")
    parser.add_argument("--limit", type=int, default=0, help="only process the first N tracks")
    parser.add_argument("--verify", type=int, default=0,
                        help="verify cache-key parity on N tracks, then exit")
    parser.add_argument("--dry-run", action="store_true", help="list scope and exit")
    args = parser.parse_args()

    tracks = _enumerate_tracks()
    if args.limit:
        tracks = tracks[: args.limit]
    print(f"scope: {len(tracks)} on-disk active tracks")
    if args.dry_run:
        return 0
    if args.verify:
        return _verify_key_parity(tracks, args.verify)

    from concurrent.futures import ProcessPoolExecutor

    counts: dict[str, int] = {}
    slowest: list[tuple[float, str]] = []
    started = time.perf_counter()
    done = 0
    with ProcessPoolExecutor(max_workers=max(1, args.jobs), initializer=_worker_init) as pool:
        for status, title, seconds in pool.map(_sweep_one, tracks, chunksize=4):
            counts[status] = counts.get(status, 0) + 1
            done += 1
            slowest.append((seconds, title))
            slowest.sort(reverse=True)
            del slowest[5:]
            if done % 25 == 0 or done == len(tracks):
                elapsed = time.perf_counter() - started
                print(f"[{done}/{len(tracks)}] {counts}  elapsed={elapsed/60:.1f}m", flush=True)

    elapsed = time.perf_counter() - started
    from rb_ss_bridge_v2.spectral_cache import _cache_dir_v4

    v4_dir = _cache_dir_v4()
    size_mb = sum(f.stat().st_size for f in v4_dir.glob("*.json")) / 1e6 if v4_dir.exists() else 0.0
    n_entries = len(list(v4_dir.glob("*.json"))) if v4_dir.exists() else 0
    print(json.dumps({
        "tracks": len(tracks),
        "counts": counts,
        "elapsed_min": round(elapsed / 60.0, 1),
        "v4_entries": n_entries,
        "v4_cache_mb": round(size_mb, 1),
        "slowest": [[round(s, 1), t[:40]] for s, t in slowest],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
