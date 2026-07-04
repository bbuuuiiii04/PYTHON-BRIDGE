"""
lsof-based track filepath resolution.

FilepathResolver.resolve_async() spawns a daemon thread that:
  1. runs lsof on rekordbox
  2. cross-references audio file durations against the track length in PositionCache
  3. queries the RB DB for BPM and content_id
  4. reads the SOUNDSWITCH_ID ID3 tag
  5. pushes a FILEPATH_RESOLVED event to event_queue

The load_gen field in both the trigger and the result lets StateManager
discard results that arrived for a stale track load.
"""
from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import threading
import time
import warnings
from pathlib import Path
from typing import Optional

from .beat_math import _compute_beatgrid_position
from .config import AUDIO_EXTS, LSOF_LEN_TOLERANCE_MS, LSOF_COOLDOWN_S, RB_DB_PATH
from .led_config import load_drop_presentation_config
from .logging_manager import get_logging_manager
from .models import BridgeEvent, Ev, PositionSnapshot
from . import bridge_fmt as bf

log = logging.getLogger("filepath_resolver")
LOG = get_logging_manager()

_EMPTY_BEATGRID = {
    "beatgrid_times_ms": [],
    "beatgrid_bpms": [],
    "beatgrid_source": "",
}
_MIN_BEATGRID_INTERVAL_MS = 150.0
_MAX_BEATGRID_INTERVAL_MS = 3000.0
_SS_PRELOAD_CACHE: dict[str, str] = {}
_SS_SCRIPTED_ID_CACHE: set[str] = set()


# ── Helpers ──────────────────────────────────────────────────────────────────

def seed_soundswitch_id_cache(mapping: dict[str, str]) -> None:
    _SS_PRELOAD_CACHE.update(mapping)


def _normalize_soundswitch_id(ssid: str) -> str:
    ssid = (ssid or "").strip().upper()
    if not ssid:
        return ""
    if not ssid.startswith("{"):
        ssid = "{" + ssid
    if not ssid.endswith("}"):
        ssid = ssid + "}"
    return ssid


def seed_soundswitch_scripted_id_cache(ids: set[str] | list[str] | tuple[str, ...]) -> None:
    _SS_SCRIPTED_ID_CACHE.update(
        normalized for ssid in ids
        if (normalized := _normalize_soundswitch_id(ssid))
    )


def has_soundswitch_scripted_id(ssid: str) -> bool:
    normalized = _normalize_soundswitch_id(ssid)
    return bool(normalized and normalized in _SS_SCRIPTED_ID_CACHE)


def _rb_pid() -> Optional[str]:
    out = subprocess.run(
        ["pgrep", "-x", "rekordbox"],
        capture_output=True, text=True, timeout=3,
    ).stdout.strip()
    return out.splitlines()[0] if out else None


def _lsof_audio_files(rb_pid: str) -> list[str]:
    out = subprocess.run(
        ["lsof", "-p", rb_pid, "-Fn"],
        capture_output=True, text=True, timeout=5,
    ).stdout
    result = []
    for line in out.splitlines():
        if not line.startswith("n"):
            continue
        path = line[1:]
        if os.path.splitext(path.lower())[1] in AUDIO_EXTS and os.path.isfile(path):
            result.append(path)
    return result


def _duration_ms(filepath: str) -> Optional[float]:
    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(filepath)
        if audio and audio.info:
            return audio.info.length * 1000.0
    except Exception:
        pass
    if filepath.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(filepath) as wf:
                return wf.getnframes() / wf.getframerate() * 1000.0
        except Exception:
            pass
    return None


def _read_soundswitch_id(filepath: str) -> str:
    if filepath in _SS_PRELOAD_CACHE:
        return _SS_PRELOAD_CACHE[filepath]
    # mutagen.File auto-detects format — required for WAV (ID3 stored in RIFF chunk,
    # not a bare ID3 header, so mutagen.id3.ID3 raises ID3NoHeaderError on .wav files).
    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(filepath)
        if audio and audio.tags and hasattr(audio.tags, "getall"):
            for tag in audio.tags.getall("TXXX"):
                if tag.desc.lower() == "soundswitch_id":
                    return str(tag.text[0]) if tag.text else ""
        if audio and audio.tags and hasattr(audio.tags, "get"):
            for key in ("soundswitch_id", "SOUNDSWITCH_ID"):
                value = audio.tags.get(key)
                if value:
                    if isinstance(value, (list, tuple)):
                        return str(value[0]) if value else ""
                    return str(value)
    except Exception:
        pass
    # Fallback: raw ID3 scan for formats mutagen.File doesn't auto-detect.
    try:
        from mutagen.id3 import ID3  # type: ignore
        for tag in ID3(filepath).getall("TXXX"):
            if tag.desc.lower() == "soundswitch_id":
                return str(tag.text[0]) if tag.text else ""
    except Exception:
        pass
    return ""


def _candidate_anlz_paths(anlz_path: str) -> list[Path]:
    path = Path(anlz_path)
    candidates = [path]
    if path.suffix.upper() in (".DAT", ".EXT", ".2EX"):
        for suffix in (".2EX", ".EXT", ".DAT"):
            candidates.append(path.with_suffix(suffix))

    seen: set[str] = set()
    result = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen and candidate.exists():
            seen.add(key)
            result.append(candidate)
    return result


def _grid_from_tag(tag, source: str) -> Optional[dict]:  # type: ignore[no-untyped-def]
    try:
        times = [float(t) * 1000.0 for t in tag.get_times()]
        bpms = [float(bpm) for bpm in tag.get_bpms()]
    except Exception as exc:
        log.debug("ANLZ %s beatgrid read failed: %s", source, exc)
        return None

    rows = sorted(
        (time_ms, bpm)
        for time_ms, bpm in zip(times, bpms)
        if time_ms >= 0.0 and bpm > 0.0
    )
    if len(rows) < 2:
        return None

    intervals = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    if (
        any(interval <= 0.0 for interval in intervals)
        or not intervals
        or sorted(intervals)[len(intervals) // 2] < _MIN_BEATGRID_INTERVAL_MS
        or sorted(intervals)[len(intervals) // 2] > _MAX_BEATGRID_INTERVAL_MS
    ):
        log.debug("ANLZ %s rejected implausible beatgrid intervals=%s",
                  source, intervals[:8])
        return None

    return {
        "beatgrid_times_ms": [time_ms for time_ms, _ in rows],
        "beatgrid_bpms": [bpm for _, bpm in rows],
        "beatgrid_source": source,
    }


def _extract_beatgrid_from_anlz(anlz_path: str) -> dict:
    """Return beatgrid fields from ANLZ data, preferring PQT2 over PQTZ."""
    try:
        from pyrekordbox.anlz import AnlzFile  # type: ignore
    except Exception as exc:
        log.debug("ANLZ beatgrid unavailable: pyrekordbox import failed: %s", exc)
        return dict(_EMPTY_BEATGRID)

    parsed = []
    for path in _candidate_anlz_paths(anlz_path):
        try:
            parsed.append((path, AnlzFile.parse_file(path)))
        except Exception as exc:
            log.debug("ANLZ beatgrid parse failed for %s: %s", path, exc)

    for tag_type in ("PQT2", "PQTZ"):
        for path, anlz in parsed:
            for tag in anlz.getall_tags(tag_type):
                grid = _grid_from_tag(tag, f"{tag_type}:{path.name}")
                if grid:
                    log.debug("ANLZ beatgrid %s markers=%d",
                              grid["beatgrid_source"], len(grid["beatgrid_times_ms"]))
                    return grid

    return dict(_EMPTY_BEATGRID)


def _hotcue_marker() -> str:
    # `load_drop_presentation_config` degrades to a "LASER" default on any
    # failure (missing/malformed config) — never raises, never blocks a load.
    return load_drop_presentation_config().hotcue_marker


def _fetch_laser_tag_beats(db, content_id: str, beatgrid_times_ms: list[float], marker: str) -> list[float]:
    """Drop-presentation hot-cue tags (docs/architecture/drop_presentation_authority.md
    §Solo Source Contracts, tier 3). Reads named hot cues from Rekordbox's
    `DjmdCue` rows via ``db.get_cue()`` (verified live 2026-07-04: 413 named cue
    points library-wide; the on-disk ANLZ cue cache is stale/empty and must
    never be used instead). Converts each matching cue's ``InMsec`` to an
    absolute beat position with the SAME beatgrid math the rest of the bridge
    uses (``beat_math._compute_beatgrid_position``), so a marker beat lands in
    the identical coordinate system as ``drop_beat_indices`` — no parallel
    conversion. The caller (``_db_lookup_by_anlz``) wraps this call in its own
    narrow try/except so a curation-data failure here degrades to "no tags"
    without discarding an otherwise-successful track resolution.
    """
    marker_norm = marker.strip().lower()
    if not marker_norm:
        return []
    beats: list[float] = []
    for cue in db.get_cue(ContentID=content_id, rb_local_deleted=0):
        comment = str(getattr(cue, "Comment", None) or "")
        if marker_norm not in comment.lower():
            continue
        in_msec = getattr(cue, "InMsec", None)
        if not isinstance(in_msec, (int, float)) or in_msec < 0:
            continue
        grid_pos = _compute_beatgrid_position(float(in_msec), beatgrid_times_ms)
        if grid_pos is None:
            continue
        beats.append(grid_pos[1])
    return beats


def _db_lookup_by_anlz(anlz_path: str) -> Optional[dict]:
    """Look up track metadata using the ANLZ file path UUID.

    The ANLZ path contains a UUID directory that matches the DB's AnalysisDataPath.
    Returns a payload dict ready for FILEPATH_RESOLVED, or None on failure.
    """
    m = re.search(r'USBANLZ/[^/]+/([^/]+)/ANLZ', anlz_path)
    if not m:
        log.debug("_db_lookup_by_anlz: cannot extract UUID from %s", anlz_path)
        return None
    anlz_uuid = m.group(1)
    beatgrid = _extract_beatgrid_from_anlz(anlz_path)
    first_beat_ms = beatgrid["beatgrid_times_ms"][0] if beatgrid["beatgrid_times_ms"] else 0.0

    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
        for c in db.get_content():
            anlz_db = getattr(c, 'AnalysisDataPath', None) or ""
            if anlz_uuid in anlz_db:
                fp   = c.FolderPath or ""
                bpm  = (c.BPM / 100.0) if c.BPM else 0.0
                ssid = _read_soundswitch_id(fp) if fp else ""
                content_id = str(c.ID)
                laser_tag_beats: list[float] = []
                try:
                    laser_tag_beats = _fetch_laser_tag_beats(
                        db, content_id, beatgrid["beatgrid_times_ms"], _hotcue_marker(),
                    )
                except Exception as exc:
                    # Curation-data failure only: the track resolution above
                    # already succeeded and must not be discarded over this.
                    log.warning(
                        "[FRES] laser-tag-read-failed  content_id=%s  err=%s",
                        content_id, type(exc).__name__,
                    )
                return {
                    'filepath':       fp,
                    'bpm':            bpm,
                    'content_id':     content_id,
                    'first_beat_ms':  first_beat_ms,
                    **beatgrid,
                    'soundswitch_id': ssid,
                    'total_ms':       float((c.Length * 1000) if c.Length else 0),
                    'laser_tag_beats': laser_tag_beats,
                }
        log.debug("_db_lookup_by_anlz: UUID %s not found in DB", anlz_uuid)
    except Exception as exc:
        log.debug("_db_lookup_by_anlz: %s", exc)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    return None


def _db_lookup(filepath: str) -> tuple[str, float, float]:
    """Return (content_id, bpm, first_beat_ms). All zeros on failure."""
    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
        norm = filepath.replace("\\", "/")
        for c in db.get_content():
            if not c.FolderPath:
                continue
            if c.FolderPath == filepath or c.FolderPath.replace("\\", "/") == norm:
                content_id = str(c.ID)
                bpm = (c.BPM / 100.0) if c.BPM else 0.0
                return content_id, bpm, 0.0  # first_beat_ms needs ANLZ — 0.0 safe default
    except Exception as exc:
        log.debug("DB lookup error: %s", exc)
    finally:
        # FM-6: always close DB to avoid fd leak
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    return "", 0.0, 0.0


# ── Resolver ─────────────────────────────────────────────────────────────────

class FilepathResolver:
    """Triggers lsof-based track identification for a deck.

    One instance shared between both decks; spawns short-lived daemon threads.
    Uses PositionCache for track-length disambiguation (replaces Frida DPU lengths).
    """

    def __init__(self, event_queue: queue.Queue[BridgeEvent], cache: "PositionCache") -> None:  # type: ignore[name-defined]
        self._queue = event_queue
        self._cache = cache
        self._last_trigger: dict[int, float] = {1: 0.0, 2: 0.0}
        self._lock = threading.Lock()

    def resolve_by_anlz(self, deck: int, load_gen: int, anlz_path: str, *, trace_id: str = "") -> None:
        """Resolve track via ANLZ path DB lookup. Falls back to lsof on failure."""
        threading.Thread(
            target=self._resolve_anlz_worker,
            args=(deck, load_gen, anlz_path, trace_id),
            daemon=True,
            name=f"anlz-d{deck}",
        ).start()

    def _resolve_anlz_worker(self, deck: int, load_gen: int, anlz_path: str, trace_id: str) -> None:
        try:
            result = _db_lookup_by_anlz(anlz_path)
            if result:
                log.info("[FRES] resolve  deck=%d  src=anlz  file=%s  bpm=%.1f",
                         deck, bf.short(result['filepath']), result['bpm'])
                payload = {**result, 'load_gen': load_gen}
                if trace_id:
                    payload["__trace_id"] = trace_id
                self._queue.put_nowait(BridgeEvent(
                    kind=Ev.FILEPATH_RESOLVED,
                    deck=deck,
                    source='anlz',
                    payload=payload,
                ))
            else:
                log.debug("[FRES] resolve-miss  deck=%d  src=anlz  action=fallback-lsof", deck)
                self.resolve_async(deck, load_gen, trace_id=trace_id)
        except Exception:
            log.exception("_resolve_anlz_worker deck %d failed", deck)

    def resolve_by_title(self, deck: int, load_gen: int, title: str, *, trace_id: str = "") -> None:
        """Fuzzy DB lookup by TL track title. Runs in a daemon thread.

        Used as fallback when ANLZ is unavailable and lsof can't match by
        track length (e.g. DDJ-800 deck 2 where memory track_length_ms = 0).
        Races with lsof — first to post FILEPATH_RESOLVED wins via load_gen check.
        """
        threading.Thread(
            target=self._resolve_title_worker,
            args=(deck, load_gen, title, trace_id),
            daemon=True,
            name=f"title-d{deck}",
        ).start()

    def _resolve_title_worker(self, deck: int, load_gen: int, title: str, trace_id: str) -> None:
        try:
            words = [w.lower() for w in re.split(r"[\s()\[\]\-]+", title) if len(w) > 2]
            if not words:
                return
            db = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
                db = Rekordbox6Database(str(RB_DB_PATH), unlock=True)
                best = None
                for c in db.get_content():
                    fp = (c.FolderPath or "").lower()
                    if not fp:
                        continue
                    if title.lower() in fp or all(w in fp for w in words):
                        best = c
                        break
            except Exception as exc:
                log.debug("resolve_by_title deck %d: DB error: %s", deck, exc)
                return
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

            if best is None:
                log.debug("resolve_by_title deck %d: no DB match for '%s'", deck, title)
                return

            fp   = best.FolderPath or ""
            bpm  = (best.BPM / 100.0) if best.BPM else 0.0
            ssid = _read_soundswitch_id(fp) if fp else ""
            total_ms = float((best.Length * 1000) if best.Length else 0)
            log.info("[FRES] resolve  deck=%d  src=title  file=%s  bpm=%.1f",
                     deck, bf.short(fp), bpm)
            payload = {
                    "filepath":       fp,
                    "bpm":            bpm,
                    "content_id":     str(best.ID),
                    "first_beat_ms":  0.0,
                    **_EMPTY_BEATGRID,
                    "soundswitch_id": ssid,
                    "total_ms":       total_ms,
                    "load_gen":       load_gen,
            }
            if trace_id:
                payload["__trace_id"] = trace_id
            self._queue.put_nowait(BridgeEvent(
                kind=Ev.FILEPATH_RESOLVED,
                deck=deck,
                source="title",
                payload=payload,
            ))
        except Exception:
            log.exception("_resolve_title_worker deck %d failed", deck)

    def resolve_async(
        self,
        deck: int,
        load_gen: int,
        other_deck_path: str = "",
        *,
        trace_id: str = "",
    ) -> None:
        """Fire-and-forget lsof probe for deck. Respects LSOF_COOLDOWN_S."""
        now = time.monotonic()
        with self._lock:
            last = self._last_trigger.get(deck, 0.0)
            remaining = LSOF_COOLDOWN_S - (now - last)
            if remaining > 0:
                # FM-4: schedule retry instead of silently dropping
                log.debug("FilepathResolver: cooldown deck %d — retry in %.1fs", deck, remaining)
                threading.Timer(
                    remaining,
                    self.resolve_async,
                    args=(deck, load_gen, other_deck_path),
                    kwargs={"trace_id": trace_id},
                ).start()
                return
            self._last_trigger[deck] = now

        threading.Thread(
            target=self._resolve,
            args=(deck, load_gen, other_deck_path, trace_id),
            daemon=True,
            name=f"lsof-d{deck}",
        ).start()

    def _resolve(self, deck: int, load_gen: int, other_deck_path: str, trace_id: str) -> None:
        try:
            pid = _rb_pid()
            if not pid:
                log.debug("lsof deck %d: rekordbox not found", deck)
                return

            files = _lsof_audio_files(pid)
            if not files:
                # FM-10: retry once after 500ms (RB may be mid-swap between fds)
                log.debug("lsof deck %d: 0 audio files — retrying in 500ms", deck)
                time.sleep(0.5)
                files = _lsof_audio_files(pid)
            if not files:
                log.warning("[FRES] resolve-fail  deck=%d  src=lsof  reason=no-audio-files", deck)
                return

            # Use track length from memory cache (replaces Frida frida_dpu_lengths)
            snap: Optional[PositionSnapshot] = self._cache.get(deck)
            target_ms = snap.track_length_ms if snap and snap.track_length_ms > 0 else 0

            matched: Optional[str] = None
            if target_ms > 0:
                for fp in files:
                    if fp == other_deck_path:
                        continue
                    dur = _duration_ms(fp)
                    if dur is not None and abs(dur - target_ms) < LSOF_LEN_TOLERANCE_MS:
                        matched = fp
                        break
            elif len(files) == 1 and files[0] != other_deck_path:
                matched = files[0]

            if not matched:
                if target_ms == 0:
                    log.debug(
                        "lsof deck %d: track_length_ms=0 — title DB lookup is primary resolver",
                        deck,
                    )
                else:
                    log.debug("lsof deck %d: no match (target_ms=%d, files=%d)", deck, target_ms, len(files))
                return

            # Guard: if memory track length changed while we ran, the match is stale
            snap2 = self._cache.get(deck)
            new_len = snap2.track_length_ms if snap2 else 0
            if target_ms > 0 and new_len > 0 and abs(new_len - target_ms) > LSOF_LEN_TOLERANCE_MS:
                log.info("[FRES] resolve-stale  deck=%d  reason=length-changed  %dms→%dms",
                         deck, target_ms, new_len)
                return

            log.info("[FRES] match  deck=%d  src=lsof  file=%s", deck, bf.short(matched))

            content_id, bpm, first_beat_ms = _db_lookup(matched)
            ssid = _read_soundswitch_id(matched)
            total_ms = float(target_ms) if target_ms else 0.0

            payload = {
                    "filepath":        matched,
                    "bpm":             bpm,
                    "content_id":      content_id,
                    "first_beat_ms":   first_beat_ms,
                    **_EMPTY_BEATGRID,
                    "soundswitch_id":  ssid,
                    "total_ms":        total_ms,
                    "load_gen":        load_gen,
            }
            if trace_id:
                payload["__trace_id"] = trace_id
            self._queue.put_nowait(BridgeEvent(
                kind=Ev.FILEPATH_RESOLVED,
                deck=deck,
                source="lsof",
                payload=payload,
            ))
        except Exception:
            log.exception("FilepathResolver._resolve deck %d failed", deck)
