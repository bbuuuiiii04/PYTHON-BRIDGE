"""
Scripted track registry and TL playlist.yaml preloader.

SCRIPTED_TRACKS maps TL playlist.yaml value → track info dict.
Keys 2, 3, 12 are hardcoded (see MEMORY.md for rationale).
Keys 4+ are auto-registered by preload_from_tl() at startup.

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

SCRIPTED_TRACKS: dict[int, dict] = {
    2: {
        "name":          "Mean Girls rmx - FINAL V4.wav",
        "filepath":      "",   # populated by _resolve_filepath()
        "bpm":           0.0,
        "total_ms":      0,
        "first_beat_ms": 0.0,
    },
    3: {
        "name":          "fkdaspekr x Kernkraft 400 (DYNASTY Remake).wav",
        "filepath":      "",
        "bpm":           0.0,
        "total_ms":      0,
        "first_beat_ms": 0.0,
    },
    # Key 12 hardcoded: preload_from_tl intermittently misses it (DB concurrency with RB)
    12: {
        "name":          "Niggas In Paris X Core X OK!OK!OK! (AWON Edit)",
        "filepath":      "",
        "bpm":           150.0,
        "total_ms":      169_000,
        "first_beat_ms": 0.0,
    },
}


def lookup(track_id: int) -> Optional[dict]:
    return SCRIPTED_TRACKS.get(track_id)


def register(track_id: int, info: dict) -> None:
    if track_id not in SCRIPTED_TRACKS:
        SCRIPTED_TRACKS[track_id] = info
        log.info("scripted_tracks: registered id=%d name=%s", track_id, info.get("name", "?"))


# ── Startup preload ───────────────────────────────────────────────────────────

def _log_registry() -> None:
    ids = sorted(SCRIPTED_TRACKS)
    log.info("scripted_tracks: registry = %s (%d tracks)", ids, len(ids))


def preload_from_tl(tl_playlist_path: str) -> None:
    """Scan TL playlist.yaml and pre-register unknown scripted tracks via RB DB.

    Called once at startup before any events arrive. Safe to call if DB is
    locked — failure is logged and skipped, not fatal.
    """
    if not os.path.exists(tl_playlist_path):
        log.debug("preload_from_tl: playlist.yaml not found, skipping")
        return

    to_find: list[tuple[int, str]] = []
    try:
        with open(tl_playlist_path) as f:
            lines = f.readlines()
        cur_name: Optional[str] = None
        saw_bridge = False
        for line in lines:
            s = line.strip()
            if "track_id:" in s:
                cur_name = s.split("track_id:", 1)[1].strip().strip('"').strip("'")
                saw_bridge = False
            elif "address:" in s and "/bridge/track_loaded" in s:
                saw_bridge = True
            elif s.startswith("value:") and saw_bridge and cur_name:
                try:
                    val = int(float(s[len("value:"):].strip()))
                except (TypeError, ValueError):
                    continue
                if val >= 2 and val not in SCRIPTED_TRACKS:
                    to_find.append((val, cur_name))
                saw_bridge = False
    except Exception as exc:
        log.warning("preload_from_tl: read error: %s", exc)
        return

    if not to_find:
        log.info("preload_from_tl: all TL tracks already registered")
        return

    log.info("preload_from_tl: looking up %d track(s) in RB DB", len(to_find))
    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db_path = os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
        db = Rekordbox6Database(db_path, unlock=True)
        all_content = list(db.get_content())
    except Exception as exc:
        log.warning("preload_from_tl: DB open failed: %s", exc)
        return
    finally:
        # FM-6: close DB after reading all content
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    for tl_val, tl_name in to_find:
        if not tl_name:
            continue
        words = [w.lower() for w in re.split(r"[\s()\[\]\-]+", tl_name) if w]
        best = None
        for c in all_content:
            fp = (c.FolderPath or "").lower()
            if not fp:
                continue
            if tl_name.lower() in fp:
                best = c
                break
            if words and all(w in fp for w in words):
                best = c
                break

        if best is None:
            log.warning("preload_from_tl: no DB match for '%s' (id=%d)", tl_name, tl_val)
            continue

        fp = best.FolderPath or ""
        # FM-5: read ssid at startup so _arm_scripted never does disk I/O
        ssid = ""
        if fp:
            try:
                from .filepath_resolver import _read_soundswitch_id
                ssid = _read_soundswitch_id(fp)
            except Exception:
                pass
        register(tl_val, {
            "name":          tl_name,
            "filepath":      fp,
            "bpm":           (best.BPM / 100.0) if best.BPM else 0.0,
            "total_ms":      (best.Length * 1000) if best.Length else 0,
            "first_beat_ms": 0.0,
            "ssid":          ssid,
        })
        log.info("preload_from_tl: id=%d '%s' bpm=%.1f", tl_val, tl_name,
                 SCRIPTED_TRACKS[tl_val]["bpm"])

    _log_registry()


def resolve_filepaths(db_path: Optional[str] = None) -> None:
    """Fill in missing 'filepath' fields for hardcoded entries by fuzzy DB search.

    Entries 2 and 3 have known names but empty filepath — resolve once at startup.
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
