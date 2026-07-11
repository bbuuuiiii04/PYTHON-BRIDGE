#!/usr/bin/env python3
"""AWR-210 lighting-sidecar EXPORTER (offline tool, read-only sources).

Writes a portable lighting memory of every analyzed track onto a USB stick's
bridge payload so a FOREIGN laptop (no local collection) can light his tracks
fully. Rekordbox exports no PSSI to USB; the local ANLZ EXT files carry it, so
the sidecar copies the ANLZ FILES themselves plus a per-track index of the
runtime identity/lighting levers (beatgrid fingerprint + tags, SoundSwitch id,
laser-tag beats, v4 spectral cache). The runtime CONSUMER is AWR-211 (separate).

    python3 tools/lighting_sidecar_export.py --dest "/Volumes/MINK" [--full] [--limit N]

Boundaries (AWR-210 Part B/C): this is an OFFLINE tool. It edits NO runtime
module and nothing in the runtime imports it. Every source is READ-ONLY
(master.db, the local ANLZ share, the v4 spectral cache, the audio files). It
writes ONLY inside ``<dest>/lighting_sidecar/`` — never the running bridge,
never a guest/mounted stick outside the named dest, never anything from
``config/`` or ``govee.env``. Fail closed + loud: any track whose data can't be
read is SKIPPED with a reason in the report, never half-written.

Identity/lighting reuse is by IMPORT of the exact runtime helpers so the
sidecar's fingerprints/tags match what the resolver computes at runtime by
construction (drift here would silently break AWR-211's identity join).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache  # noqa: E402
from rb_ss_bridge_v2.config import RB_DB_PATH  # noqa: E402
from rb_ss_bridge_v2.filepath_resolver import (  # noqa: E402
    _candidate_anlz_paths,
    _extract_beatgrid_from_anlz,
    _fetch_laser_tag_beats,
    _hotcue_marker,
    _local_anlz_path,
    _read_soundswitch_id,
)

SCHEMA_VERSION = 1
SIDECAR_DIRNAME = "lighting_sidecar"

# Reason classes for a skipped track. EXPECTED = healthy-library reasons that
# do NOT fail the run; anything else is a real inconsistency → nonzero exit.
EXPECTED_SKIP_REASONS = frozenset({"no_analysis", "no_beatgrid"})


# ── pure helpers (unit-tested without a real DB/cache) ────────────────────────
def reason_class(reason: str) -> str:
    return "expected" if reason in EXPECTED_SKIP_REASONS else "unexpected"


def safe_dest(sidecar_root: Path, relpath: str) -> Path:
    """Resolve ``relpath`` under ``sidecar_root``; refuse any escape.

    The single guard every write routes through — proves nothing lands outside
    the named sidecar directory (Part C: never write outside dest).
    """
    root = os.path.abspath(str(sidecar_root))
    target = os.path.abspath(os.path.join(root, relpath))
    if os.path.commonpath([root, target]) != root:
        raise ValueError(f"refusing to write outside sidecar dir: {relpath!r}")
    return Path(target)


def _stat_sig(path: Path) -> Optional[list]:
    try:
        st = path.stat()
    except OSError:
        return None
    return [int(st.st_size), int(st.st_mtime_ns)]


def source_signature(anlz_sources: list[Path], v4_source: Optional[Path]) -> dict:
    """Incremental key: source ANLZ mtime+size + the v4 cache record's."""
    anlz = []
    for p in sorted(anlz_sources, key=lambda x: x.name):
        sig = _stat_sig(p)
        if sig is not None:
            anlz.append([p.name, sig[0], sig[1]])
    v4 = _stat_sig(v4_source) if v4_source is not None else None
    return {"anlz": anlz, "v4": v4}


def unchanged(old_record: Optional[dict], sig: dict, dest_files: list[Path]) -> bool:
    """Skip re-copy when sources match the prior run AND dest files survive."""
    if not old_record or old_record.get("source_sig") != sig:
        return False
    return all(p.exists() for p in dest_files)


def prune_targets(old_ids: set[str], current_ids: set[str]) -> list[str]:
    """content_ids present in the prior sidecar but gone from the library."""
    return sorted(old_ids - current_ids, key=_id_sort_key)


def _id_sort_key(content_id: str):
    return (0, int(content_id)) if content_id.isdigit() else (1, content_id)


def build_index(records: list[dict], *, built_at: dict) -> dict:
    """Deterministic index assembly (records sorted by content_id)."""
    ordered = sorted(records, key=lambda r: _id_sort_key(str(r["content_id"])))
    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": built_at,
        "track_count": len(ordered),
        "tracks": ordered,
    }


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parents[1]),
             "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


# ── per-track export (uses the live DB/cache; caller wraps in try/except) ─────
def _v4_source_path(filepath: str, beatgrid_times_ms) -> Optional[Path]:
    """Locate the track's v4 cache file by the SAME key the cache writes under."""
    if not filepath:
        return None
    key = spectral_cache._cache_key(filepath, beatgrid_times_ms)
    if not key:
        return None
    candidate = spectral_cache._cache_dir_v4() / f"{key}.json"
    return candidate if candidate.exists() else None


def _export_track(db, content, sidecar_root: Path, old_record: Optional[dict],
                  full: bool) -> tuple[Optional[dict], Optional[str], bool]:
    """Return (record, skip_reason, reused). Exactly one of record/reason set."""
    content_id = str(content.ID)
    analysis_path = str(getattr(content, "AnalysisDataPath", None) or "")
    if not analysis_path:
        return None, "no_analysis", False

    local_anlz = _local_anlz_path(analysis_path)
    anlz_sources = _candidate_anlz_paths(local_anlz)
    if not anlz_sources:
        return None, "anlz_missing", False

    beatgrid = _extract_beatgrid_from_anlz(local_anlz)
    grid_times = beatgrid.get("beatgrid_times_ms") or []
    if len(grid_times) < 2:
        return None, "no_beatgrid", False

    filepath = str(getattr(content, "FolderPath", None) or "")
    v4_source = _v4_source_path(filepath, grid_times)
    sig = source_signature(anlz_sources, v4_source)

    anlz_relpaths = sorted(f"anlz/{content_id}/{p.name}" for p in anlz_sources)
    v4_relpath = f"v4/{content_id}.json" if v4_source is not None else None
    dest_files = [safe_dest(sidecar_root, rp) for rp in anlz_relpaths]
    if v4_relpath:
        dest_files.append(safe_dest(sidecar_root, v4_relpath))

    if not full and unchanged(old_record, sig, dest_files):
        return old_record, None, True

    # Rebuild: copy ANLZ set + v4, then the fresh record. copy2 preserves mtime.
    for src, rp in zip(sorted(anlz_sources, key=lambda x: x.name), anlz_relpaths):
        dst = safe_dest(sidecar_root, rp)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if v4_source is not None and v4_relpath:
        dst = safe_dest(sidecar_root, v4_relpath)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v4_source, dst)

    bpm = (content.BPM / 100.0) if getattr(content, "BPM", None) else 0.0
    duration_s = float(content.Length) if getattr(content, "Length", None) else 0.0
    laser_tag_beats: list[float] = []
    try:
        laser_tag_beats = _fetch_laser_tag_beats(
            db, content_id, list(grid_times), _hotcue_marker())
    except Exception:  # curation-data only; identity already confirmed
        laser_tag_beats = []

    record = {
        "content_id": content_id,
        "title": str(getattr(content, "Title", None) or ""),
        "artist": str(getattr(content, "ArtistName", None) or ""),
        "duration_s": duration_s,
        "bpm": bpm,
        "beatgrid_fingerprint": spectral_cache._beatgrid_fingerprint(grid_times),
        "anlz_relpaths": anlz_relpaths,
        "v4_relpath": v4_relpath,
        "soundswitch_id": _read_soundswitch_id(filepath) if filepath else "",
        "laser_tag_beats": laser_tag_beats,
        "source_filepath": filepath,
        "source_sig": sig,
    }
    return record, None, False


def _prune(sidecar_root: Path, content_id: str) -> None:
    anlz_dir = safe_dest(sidecar_root, f"anlz/{content_id}")
    if anlz_dir.is_dir():
        shutil.rmtree(anlz_dir)
    v4_file = safe_dest(sidecar_root, f"v4/{content_id}.json")
    if v4_file.exists():
        v4_file.unlink()


def export(dest: str, *, full: bool = False, limit: Optional[int] = None) -> dict:
    """Run the export; return the report dict (also drives the exit code)."""
    started = time.monotonic()
    sidecar_root = Path(dest).expanduser() / SIDECAR_DIRNAME
    sidecar_root.mkdir(parents=True, exist_ok=True)

    index_path = sidecar_root / "index.json"
    old_by_id: dict[str, dict] = {}
    if index_path.exists() and not full:
        try:
            old = json.loads(index_path.read_text(encoding="utf-8"))
            old_by_id = {str(r["content_id"]): r for r in old.get("tracks", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            old_by_id = {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)

    records: list[dict] = []
    skipped: list[dict] = []
    reused = 0
    current_ids: set[str] = set()
    processed = 0
    for content in db.get_content():
        if getattr(content, "rb_local_deleted", 0):
            continue
        content_id = str(content.ID)
        current_ids.add(content_id)
        if limit is not None and processed >= limit:
            continue
        processed += 1
        try:
            record, reason, was_reused = _export_track(
                db, content, sidecar_root, old_by_id.get(content_id), full)
        except Exception as exc:  # never let one bad row abort the run
            skipped.append({"content_id": content_id,
                            "reason": f"exception:{type(exc).__name__}"})
            continue
        if record is not None:
            records.append(record)
            reused += int(was_reused)
        else:
            skipped.append({"content_id": content_id, "reason": reason})

    # Prune tracks gone from the library (only the ones we actually kept files
    # for — bound by the prior index; with --limit we still know current_ids).
    pruned = prune_targets(set(old_by_id), current_ids)
    for content_id in pruned:
        _prune(sidecar_root, content_id)

    built_at = {"head": _git_head(),
                "timestamp": datetime.now(timezone.utc).isoformat()}
    index = build_index(records, built_at=built_at)
    tmp = index_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=2, sort_keys=False), encoding="utf-8")
    os.replace(tmp, index_path)

    unexpected = sorted({s["reason"] for s in skipped
                         if reason_class(s["reason"].split(":")[0]) == "unexpected"})
    report = {
        "dest": str(sidecar_root),
        "exported": len(records),
        "reused_unchanged": reused,
        "skipped": len(skipped),
        "skipped_by_reason": _count_reasons(skipped),
        "skipped_detail": skipped,
        "pruned": len(pruned),
        "pruned_ids": pruned,
        "unexpected_skip_reasons": unexpected,
        "bytes": {
            "anlz": _dir_bytes(sidecar_root / "anlz"),
            "v4": _dir_bytes(sidecar_root / "v4"),
            "index": index_path.stat().st_size,
        },
        "elapsed_s": round(time.monotonic() - started, 2),
        "ok": not unexpected,
    }
    return report


def _count_reasons(skipped: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for s in skipped:
        counts[s["reason"]] = counts.get(s["reason"], 0) + 1
    return dict(sorted(counts.items()))


def _fmt_mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", required=True,
                    help="stick payload ROOT (sidecar written to <dest>/lighting_sidecar/)")
    ap.add_argument("--full", action="store_true",
                    help="force a full rebuild (ignore the incremental index)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap tracks processed (smoke runs)")
    args = ap.parse_args(argv)

    report = export(args.dest, full=args.full, limit=args.limit)
    b = report["bytes"]
    total = b["anlz"] + b["v4"] + b["index"]
    print(f"lighting sidecar → {report['dest']}")
    print(f"  exported={report['exported']}  reused={report['reused_unchanged']}  "
          f"skipped={report['skipped']}  pruned={report['pruned']}")
    if report["skipped_by_reason"]:
        print(f"  skip reasons: {report['skipped_by_reason']}")
    print(f"  size: anlz={_fmt_mb(b['anlz'])}  v4={_fmt_mb(b['v4'])}  "
          f"index={_fmt_mb(b['index'])}  total={_fmt_mb(total)}")
    print(f"  elapsed={report['elapsed_s']}s")
    if not report["ok"]:
        print(f"  UNEXPECTED skips: {report['unexpected_skip_reasons']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
