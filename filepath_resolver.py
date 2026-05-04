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
from typing import Optional

from .config import AUDIO_EXTS, LSOF_LEN_TOLERANCE_MS, LSOF_COOLDOWN_S
from .models import BridgeEvent, Ev, PositionSnapshot

log = logging.getLogger("filepath_resolver")


# ── Helpers ──────────────────────────────────────────────────────────────────

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
    # mutagen.File auto-detects format — required for WAV (ID3 stored in RIFF chunk,
    # not a bare ID3 header, so mutagen.id3.ID3 raises ID3NoHeaderError on .wav files).
    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(filepath)
        if audio and audio.tags and hasattr(audio.tags, "getall"):
            for tag in audio.tags.getall("TXXX"):
                if tag.desc.lower() == "soundswitch_id":
                    return str(tag.text[0]) if tag.text else ""
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

    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db_path = os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
        db = Rekordbox6Database(db_path, unlock=True)
        for c in db.get_content():
            anlz_db = getattr(c, 'AnalysisDataPath', None) or ""
            if anlz_uuid in anlz_db:
                fp   = c.FolderPath or ""
                bpm  = (c.BPM / 100.0) if c.BPM else 0.0
                ssid = _read_soundswitch_id(fp) if fp else ""
                return {
                    'filepath':       fp,
                    'bpm':            bpm,
                    'content_id':     str(c.ID),
                    'first_beat_ms':  0.0,
                    'soundswitch_id': ssid,
                    'total_ms':       float((c.Length * 1000) if c.Length else 0),
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
        db_path = os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
        db = Rekordbox6Database(db_path, unlock=True)
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

    def resolve_by_anlz(self, deck: int, load_gen: int, anlz_path: str) -> None:
        """Resolve track via ANLZ path DB lookup. Falls back to lsof on failure."""
        threading.Thread(
            target=self._resolve_anlz_worker,
            args=(deck, load_gen, anlz_path),
            daemon=True,
            name=f"anlz-d{deck}",
        ).start()

    def _resolve_anlz_worker(self, deck: int, load_gen: int, anlz_path: str) -> None:
        try:
            result = _db_lookup_by_anlz(anlz_path)
            if result:
                log.info("anlz deck %d: resolved → %s bpm=%.1f",
                         deck, os.path.basename(result['filepath']), result['bpm'])
                self._queue.put_nowait(BridgeEvent(
                    kind=Ev.FILEPATH_RESOLVED,
                    deck=deck,
                    source='anlz',
                    payload={**result, 'load_gen': load_gen},
                ))
            else:
                log.debug("anlz deck %d: DB miss — falling back to lsof", deck)
                self.resolve_async(deck, load_gen)
        except Exception:
            log.exception("_resolve_anlz_worker deck %d failed", deck)

    def resolve_by_title(self, deck: int, load_gen: int, title: str) -> None:
        """Fuzzy DB lookup by TL track title. Runs in a daemon thread.

        Used as fallback when ANLZ is unavailable and lsof can't match by
        track length (e.g. DDJ-800 deck 2 where memory track_length_ms = 0).
        Races with lsof — first to post FILEPATH_RESOLVED wins via load_gen check.
        """
        threading.Thread(
            target=self._resolve_title_worker,
            args=(deck, load_gen, title),
            daemon=True,
            name=f"title-d{deck}",
        ).start()

    def _resolve_title_worker(self, deck: int, load_gen: int, title: str) -> None:
        try:
            words = [w.lower() for w in re.split(r"[\s()\[\]\-]+", title) if len(w) > 2]
            if not words:
                return
            db = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
                db_path = os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
                db = Rekordbox6Database(db_path, unlock=True)
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
            log.info("title deck %d: resolved → %s bpm=%.1f",
                     deck, os.path.basename(fp), bpm)
            self._queue.put_nowait(BridgeEvent(
                kind=Ev.FILEPATH_RESOLVED,
                deck=deck,
                source="title",
                payload={
                    "filepath":       fp,
                    "bpm":            bpm,
                    "content_id":     str(best.ID),
                    "first_beat_ms":  0.0,
                    "soundswitch_id": ssid,
                    "total_ms":       total_ms,
                    "load_gen":       load_gen,
                },
            ))
        except Exception:
            log.exception("_resolve_title_worker deck %d failed", deck)

    def resolve_async(
        self,
        deck: int,
        load_gen: int,
        other_deck_path: str = "",
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
                ).start()
                return
            self._last_trigger[deck] = now

        threading.Thread(
            target=self._resolve,
            args=(deck, load_gen, other_deck_path),
            daemon=True,
            name=f"lsof-d{deck}",
        ).start()

    def _resolve(self, deck: int, load_gen: int, other_deck_path: str) -> None:
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
                log.warning("lsof deck %d: still 0 audio files after retry — giving up", deck)
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
                log.debug("lsof deck %d: no match (target_ms=%d, files=%d)", deck, target_ms, len(files))
                return

            # Guard: if memory track length changed while we ran, the match is stale
            snap2 = self._cache.get(deck)
            new_len = snap2.track_length_ms if snap2 else 0
            if target_ms > 0 and new_len > 0 and abs(new_len - target_ms) > LSOF_LEN_TOLERANCE_MS:
                log.info("lsof deck %d: discarded — length changed %d→%d ms while running",
                         deck, target_ms, new_len)
                return

            log.info("lsof deck %d: matched → %s", deck, os.path.basename(matched))

            content_id, bpm, first_beat_ms = _db_lookup(matched)
            ssid = _read_soundswitch_id(matched)
            total_ms = float(target_ms) if target_ms else 0.0

            self._queue.put_nowait(BridgeEvent(
                kind=Ev.FILEPATH_RESOLVED,
                deck=deck,
                source="lsof",
                payload={
                    "filepath":        matched,
                    "bpm":             bpm,
                    "content_id":      content_id,
                    "first_beat_ms":   first_beat_ms,
                    "soundswitch_id":  ssid,
                    "total_ms":        total_ms,
                    "load_gen":        load_gen,
                },
            ))
        except Exception:
            log.exception("FilepathResolver._resolve deck %d failed", deck)
