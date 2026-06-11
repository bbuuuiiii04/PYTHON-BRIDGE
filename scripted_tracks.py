"""Scripted track registry and startup filepath resolver.

SCRIPTED_TRACKS maps scripted show IDs to track info dicts. Entries are
registered by bridge tests/configuration before startup resolution runs.

Thread safety: register() is called only at startup (single-threaded context).
               lookup() is read-only after startup. No lock needed.
"""
from __future__ import annotations

import logging
import os
import re
import warnings
from typing import Optional

log = logging.getLogger("scripted_tracks")

# ── Registry ─────────────────────────────────────────────────────────────────

SCRIPTED_TRACKS: dict[int, dict] = {}


def lookup(track_id: int) -> Optional[dict]:
    return SCRIPTED_TRACKS.get(track_id)


def register(track_id: int, info: dict) -> None:
    if track_id not in SCRIPTED_TRACKS:
        SCRIPTED_TRACKS[track_id] = info
        log.debug("scripted_tracks: registered id=%d name=%s", track_id, info.get("name", "?"))


# ── Startup resolution ────────────────────────────────────────────────────────

def _log_registry() -> None:
    ids = sorted(SCRIPTED_TRACKS)
    log.info("scripted_tracks: registry  count=%d  ids=%s", len(ids), ids)


def resolve_filepaths(db_path: Optional[str] = None) -> None:
    """Fill in missing 'filepath' fields for preloaded entries by fuzzy DB search.

    Safe to call even if DB is unavailable.
    """
    needs = {tid: t for tid, t in SCRIPTED_TRACKS.items() if not t.get("filepath")}
    if not needs:
        return
    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        path = db_path or os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
        db = Rekordbox6Database(path, unlock=True)
        all_content = list(db.get_content())
    except Exception as exc:
        log.warning("resolve_filepaths: DB open failed: %s", exc)
        return
    finally:
        # FM-6: always close DB
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    for tid, track in list(needs.items()):
        name = track["name"]
        words = [w.lower() for w in re.split(r"[\s()\[\]\-]+", name) if w]
        for c in all_content:
            fp = c.FolderPath or ""
            if not fp:
                continue
            if name.lower() in fp.lower() or (words and all(w in fp.lower() for w in words)):
                track["filepath"] = fp
                if c.BPM and not track["bpm"]:
                    track["bpm"] = c.BPM / 100.0
                if c.Length and not track["total_ms"]:
                    track["total_ms"] = c.Length * 1000
                # FM-5: read ssid at startup so _arm_scripted never does disk I/O
                if not track.get("ssid"):
                    try:
                        from .filepath_resolver import _read_soundswitch_id
                        track["ssid"] = _read_soundswitch_id(fp)
                    except Exception:
                        track["ssid"] = ""
                log.info("resolve_filepaths: id=%d → %s ssid=%s",
                         tid, os.path.basename(fp), bool(track.get("ssid")))
                break
        else:
            log.warning("resolve_filepaths: id=%d '%s' not found in DB", tid, name)
