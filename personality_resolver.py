"""Per-track Laser Personality resolution.

``PersonalityResolver`` is deliberately pure: callers provide already-loaded
playlist names and file BPM, and it returns a deterministic decision.  Rekordbox
database access is isolated in ``PlaylistCache`` so StateManager can control
when I/O happens.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import threading
import warnings
from typing import Literal, Mapping, Optional, Sequence

log = logging.getLogger("personality_resolver")

ResolutionReason = Literal["playlist_match", "bpm_range_match", "default"]


@dataclass(frozen=True)
class PersonalityResolution:
    name: str
    reason: ResolutionReason
    matched: str = ""


def canonicalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


class PersonalityResolver:
    """Pure, deterministic personality resolver."""

    def __init__(
        self,
        *,
        alias_index: Mapping[str, str],
        bpm_priority: Sequence[str],
        bpm_bands: Mapping[str, tuple[float, float]],
        known_personalities: set[str],
        default: str,
        quiet: bool = False,
    ) -> None:
        self._known_personalities = set(known_personalities)
        self._default = default if default in self._known_personalities else ""
        if default and default not in self._known_personalities and not quiet:
            log.warning(
                "[PERSONALITY] default_personality=%r not in known personalities; "
                "resolver will return empty name on default path",
                default,
            )
        self._alias_index = {
            canonicalize_text(alias): personality
            for alias, personality in alias_index.items()
            if canonicalize_text(alias) and personality in self._known_personalities
        }
        self._aliases_longest_first = tuple(
            sorted(self._alias_index.keys(), key=lambda alias: (-len(alias), alias))
        )
        self._alias_patterns = tuple(
            (alias, re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)"))
            for alias in self._aliases_longest_first
        )
        self._bpm_priority = tuple(
            name for name in bpm_priority if name in self._known_personalities
        )
        self._bpm_bands = {
            name: (float(band[0]), float(band[1]))
            for name, band in bpm_bands.items()
            if name in self._known_personalities
        }

    def resolve(
        self,
        *,
        playlists: frozenset[str],
        bpm: float,
    ) -> PersonalityResolution:
        canonical_playlists = tuple(
            canonicalize_text(name) for name in playlists if canonicalize_text(name)
        )

        for alias, pattern in self._alias_patterns:
            if any(pattern.search(playlist) for playlist in canonical_playlists):
                return PersonalityResolution(
                    name=self._alias_index[alias],
                    reason="playlist_match",
                    matched=alias,
                )

        file_bpm = float(bpm or 0.0)
        if file_bpm > 0.0:
            for name in self._bpm_priority:
                bpm_min, bpm_max = self._bpm_bands.get(name, (0.0, 0.0))
                if bpm_min == 0.0 and bpm_max == 0.0:
                    continue
                if bpm_min <= file_bpm < bpm_max:
                    return PersonalityResolution(
                        name=name,
                        reason="bpm_range_match",
                        matched=f"{bpm_min:g}-{bpm_max:g}",
                    )

        return PersonalityResolution(
            name=self._default,
            reason="default",
            matched="",
        )


class PlaylistCache:
    """Rekordbox playlist membership cache, scoped to a named folder
    (default 'PER GENRE')."""

    def __init__(self, db_path: Path, *, folder_name: str = "PER GENRE") -> None:
        self._db_path = Path(db_path)
        self._folder_name = canonicalize_text(folder_name)
        self._by_content_id: dict[str, frozenset[str]] = {}
        self._loaded = False
        self._last_logged_track_count = -1
        self._last_logged_playlist_count = -1
        self._refresh_lock = threading.Lock()

    def get(self, content_id: str) -> Optional[frozenset[str]]:
        key = str(content_id or "")
        if not key:
            return frozenset()
        if not self._loaded:
            return None
        return self._by_content_id.get(key, frozenset())

    def refresh(self) -> int:
        if not self._refresh_lock.acquire(blocking=False):
            log.debug(
                "[PERSONALITY] refresh already in progress tracks=%d",
                len(self._by_content_id),
            )
            return len(self._by_content_id)
        try:
            db = None
            next_cache: dict[str, set[str]] = {}
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    from pyrekordbox.db6 import Rekordbox6Database  # type: ignore

                db = Rekordbox6Database(str(self._db_path), unlock=True)
                playlists = list(self._iter_playlists(db))
                parent_ids = {
                    str(getattr(playlist, "ID", ""))
                    for playlist in playlists
                    if canonicalize_text(getattr(playlist, "Name", "")) == self._folder_name
                }
                if not parent_ids:
                    log.warning("[PERSONALITY] PER GENRE folder not found in Rekordbox DB")
                    self._by_content_id = {}
                    self._loaded = True
                    return 0

                genre_playlists = [
                    playlist for playlist in playlists
                    if str(getattr(playlist, "ParentID", "")) in parent_ids
                ]
                if not genre_playlists:
                    log.warning("[PERSONALITY] PER GENRE folder has no child playlists")

                total_skipped = 0
                for playlist in genre_playlists:
                    playlist_name = str(getattr(playlist, "Name", "") or "")
                    playlist_id = getattr(playlist, "ID", None)
                    content_ids, skipped = self._iter_playlist_content_ids(db, playlist_id)
                    total_skipped += skipped
                    for content_id in content_ids:
                        next_cache.setdefault(str(content_id), set()).add(playlist_name)
            except Exception:
                log.warning("[PERSONALITY] PER GENRE cache refresh failed", exc_info=True)
                return len(self._by_content_id)
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

            self._by_content_id = {
                content_id: frozenset(names)
                for content_id, names in next_cache.items()
            }
            self._loaded = True
            new_track_count = len(self._by_content_id)
            new_playlist_count = len(genre_playlists)
            if (
                new_track_count != self._last_logged_track_count
                or new_playlist_count != self._last_logged_playlist_count
            ):
                log.info(
                    "[PERSONALITY] PER GENRE cache refreshed tracks=%d playlists=%d skipped_rows=%d",
                    new_track_count,
                    new_playlist_count,
                    total_skipped,
                )
                self._last_logged_track_count = new_track_count
                self._last_logged_playlist_count = new_playlist_count
            return len(self._by_content_id)
        finally:
            self._refresh_lock.release()

    def _iter_playlists(self, db) -> Sequence[object]:  # type: ignore[no-untyped-def]
        for method_name in ("get_playlist", "get_playlists"):
            method = getattr(db, method_name, None)
            if callable(method):
                return tuple(method())
        return ()

    def _iter_playlist_content_ids(self, db, playlist_id) -> tuple[tuple[str, ...], int]:  # type: ignore[no-untyped-def]
        if playlist_id is None:
            return ((), 0)
        for method_name in ("get_playlist_contents", "get_playlist_content"):
            method = getattr(db, method_name, None)
            if not callable(method):
                continue
            try:
                rows = method(playlist_id)
            except TypeError:
                rows = method(str(playlist_id))
            ids: list[str] = []
            skipped = 0
            for row in rows:
                content_id = (
                    getattr(row, "ContentID", None)
                    or getattr(row, "content_id", None)
                    or getattr(row, "ID", None)
                    or getattr(row, "TrackID", None)
                )
                if content_id is not None:
                    ids.append(str(content_id))
                else:
                    skipped += 1
            return tuple(ids), skipped
        return ((), 0)
