#!/usr/bin/env python3
"""Offline spectral v4 pre-warm sweep of a rekordbox USB export (AWR-183).

Same extraction + cache seams as ``tools/spectral_sweep.py``, different
enumeration: walks ``<mount>/PIONEER/USBANLZ`` for ``ANLZ*.DAT`` files, reads
each track's device-relative audio path (PPTH tag, e.g.
``/Contents/Artist/Album/x.wav``), and writes v4 cache entries keyed by the
ON-STICK absolute audio path (``<mount>/Contents/...``). A bridge on ANY Mac
that mounts this stick under the same volume name derives the same key at
load, so copying ``~/Library/Application Support/RBSS Bridge/spectral_cache``
to that Mac makes every stick track full-strength from its first beat (no
~15s first-load extraction).

Reads the stick + audio only; writes ONLY v4 cache entries (atomic
tmp+rename, safe alongside a running bridge). Never touches the Rekordbox DB,
ANLZ files, audio files, or v3 entries.

    caffeinate -i python3 tools/spectral_stick_sweep.py /Volumes/USB --jobs 2

Stated assumption (also printed in the summary): the target Mac mounts the
stick at the same ``/Volumes/<name>`` path — a volume-name collision there
(mounting as "USB 1") would miss every key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # rb_ss_bridge_v2 package
sys.path.insert(0, str(Path(__file__).resolve().parent))      # sibling spectral_sweep

from spectral_sweep import _sweep_one, _worker_init  # reuse the proven worker


def collect_tracks(dat_paths, read_ppth, mount: str, isfile) -> list[dict[str, str]]:
    """Pure enumeration core (the test seam): ANLZ .DAT files -> sweep tracks.

    Keeps the first ANLZ seen per resolved audio path; skips entries whose
    PPTH is absent/unreadable or whose audio file is missing on the stick.
    """
    tracks: list[dict[str, str]] = []
    seen: set[str] = set()
    mount_path = Path(mount)
    for dat in sorted(str(p) for p in dat_paths):
        ppth = read_ppth(dat)
        if not ppth:
            continue
        audio = str(mount_path / ppth.lstrip("/"))
        if audio in seen or not isfile(audio):
            continue
        seen.add(audio)
        tracks.append({
            "content_id": dat,  # stable sort/progress id; stick tracks have no DB id
            "title": Path(audio).name,
            "filepath": audio,
            "anlz_abs": dat,
        })
    return tracks


def _read_ppth(dat: str) -> str:
    from pyrekordbox.anlz import AnlzFile  # type: ignore

    try:
        return str(AnlzFile.parse_file(dat).get("path") or "")
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount", help="mounted rekordbox export root, e.g. /Volumes/USB")
    parser.add_argument("--jobs", type=int, default=2,
                        help="parallel extraction processes (default 2)")
    parser.add_argument("--limit", type=int, default=0, help="only process the first N tracks")
    parser.add_argument("--dry-run", action="store_true", help="list scope and exit")
    args = parser.parse_args()

    anlz_root = Path(args.mount) / "PIONEER" / "USBANLZ"
    if not anlz_root.is_dir():
        print(f"not a rekordbox export: {anlz_root} is missing")
        return 1
    dats = anlz_root.rglob("ANLZ*.DAT")
    tracks = collect_tracks(dats, _read_ppth, args.mount, os.path.isfile)
    print(f"scope: {len(tracks)} stick tracks keyed under {args.mount}")
    if args.limit:
        tracks = tracks[: args.limit]
    if args.dry_run:
        return 0

    from concurrent.futures import ProcessPoolExecutor

    counts: dict[str, int] = {}
    started = time.perf_counter()
    done = 0
    with ProcessPoolExecutor(max_workers=max(1, args.jobs), initializer=_worker_init) as pool:
        for status, _title, _seconds in pool.map(_sweep_one, tracks, chunksize=4):
            counts[status] = counts.get(status, 0) + 1
            done += 1
            if done % 25 == 0 or done == len(tracks):
                elapsed = time.perf_counter() - started
                print(f"[{done}/{len(tracks)}] {counts}  elapsed={elapsed/60:.1f}m", flush=True)

    print(json.dumps({
        "tracks": len(tracks),
        "counts": counts,
        "elapsed_min": round((time.perf_counter() - started) / 60.0, 1),
    }, indent=1))
    print(f"NOTE: keys assume the target Mac mounts this stick at {args.mount} "
          "(same volume name, no collision).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
