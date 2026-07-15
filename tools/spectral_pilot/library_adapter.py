"""Offline library enumeration for the Phase-0 spectral pilot (spec B3.1-B3.4, B7).

READ-ONLY. This module turns the existing Rekordbox library into the
``LocatorRow`` inputs ``selection.build_selection`` consumes. It never writes to,
locks, or mutates any Rekordbox data, audio file, cache, or label store. It never
runs v4 extraction: a missing/invalid v4 payload EXCLUDES the row, it is never
computed (spec B10).

Two layers, on purpose:
- ``list_locators`` — metadata only (id/artist/title/duration/bpm/path), for EVERY
  library row, with NO audio decode and NO hashing (spec B3.1).
- ``enrich`` — audio SHA-256, v4 presence/validity, beatgrid fingerprint, and
  candidate drop markers, for the 60-row seed pool + the seven anchors ONLY
  (spec B3.1: "Only these 60 may incur audio hashing and v4/grid/marker
  validation").

Every real read goes through an injectable ``LibraryReaders`` bundle, so the unit
tests drive this module with synthetic fixtures and never touch the live library.
``real_readers()`` is the only thing here that imports the live bridge modules, and
it is called only by the actual Phase-1 enumeration, never by a test.

────────────────────────────────────────────────────────────────────────────────
Verified offline-enumeration map (HEAD 9e690eb; every cite confirmed at this HEAD).
The reference read-only enumerator already in the repo is
``tools/lighting_sidecar_export.py``; this module mirrors its open pattern.

1. Enumerate tracks + id/artist/title/duration/bpm/path
   - DB open + iterate: ``Rekordbox6Database(str(RB_DB_PATH), unlock=True)`` then
     ``db.get_content()`` — tools/lighting_sidecar_export.py:253,260.
   - RB_DB_PATH = ~/Library/Pioneer/rekordbox/master.db — config.py:20.
   - Per content row: ``str(content.ID)`` stable locator id; ``content.Title``;
     ``content.ArtistName``; ``float(content.Length)`` seconds; ``content.BPM/100``;
     ``content.FolderPath`` absolute audio path; ``content.AnalysisDataPath`` →
     ANLZ; skip ``content.rb_local_deleted`` — tools/lighting_sidecar_export.py:
     162,200-213,177,261.
2. Beatgrid (beat times / count)
   - ``filepath_resolver._extract_beatgrid_from_anlz(path)`` reading PQT2/PQTZ via
     pyrekordbox — filepath_resolver.py:219-243; ANLZ path from
     ``filepath_resolver._local_anlz_path(content.AnalysisDataPath)`` :317-318.
     Beat count = ``len(beatgrid_times_ms)``.
3. Candidate drop markers = Rekordbox PSSI phrase drops (NOT the stale ANLZ cue
   cache, and NOT arbitrary DjmdCue hot-cues): ``anlz_reader.read_anlz_drops(path)
   .drop_beat_indices`` — anlz_reader.py:180-226. This is exactly what the bridge's
   F2 pipeline plans over, so it is the correct "candidate drop marker" set; a real
   probe showed a live track (Anti Up — I Cannot) has 0 DjmdCue rows but 6 phrase
   drops, so the cue-table source would have falsely blocked it.
4. v4 spectral cache — read-only present/valid, no recompute:
   ``spectral_cache.get_cached_v4(audio_path, beatgrid_times_ms)`` returns a
   ``SpectralFeaturesV4`` or None (only reads/parses JSON) — spectral_cache.py:
   142-155. Identity key = sha1(realpath \\0 mtime_ns \\0 size \\0 beatgrid_fp) via
   ``_cache_key`` :337-352; file at ``_cache_dir_v4()/{key}.json`` :214-223.
   Present = that file exists; Valid = get_cached_v4 non-None (payload schema +
   per-series length checks in ``_features_v4_from_payload`` :226-275).
5. ``spectral_profile.drop_window_vector(v4, drop_beat, *, width=16)`` summarizes
   the 16-beat window [start, start+16) at a drop — spectral_profile.py:619-637
   (used only downstream, for tier pinning via lighting_moments_v2.build_track_plan).
6. DB lock: master.db is SQLCipher/SQLite; existing readers open it in place with
   ``unlock=True`` while Rekordbox runs (SQLite allows concurrent readers) — no
   copy-to-read anywhere. To be safe against a WAL write-lock and to keep the
   byte-identity watch set untouched, the Phase-1 driver copies master.db into the
   pilot ``scratch/`` and opens the COPY. Reads of ANLZ / audio / v4-cache files
   never change mtime or size, so they are safe under the watch (guards.listing_hash
   keys on mtime_ns + size).
────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .canonical import sha256_hex, selection_hash
from .selection import ANCHOR_ROLES, LocatorRow, POOL_SIZE, WINDOW


class AnchorError(ValueError):
    """An anchor could not be pinned (missing content, invalid v4, no usable marker).

    Fail closed (spec B3.7, B10): an ineligible anchor STOPS with a report — it is
    never silently substituted.
    """


# The seven anchors — operator-decided 2026-07-15 (spec B3.7). Content-ids resolved
# read-only against the live library at Phase-1 prep and verified valid. `gold`
# anchors use their fixed B3.7 labeled-drop beats; T2/T3 pin the highest-F2-tier
# phrase drop at implementation. Order MUST match selection.ANCHOR_ROLES.
ANCHOR_SPECS = (
    ("WALL",  "51640855",  "gold", (128,)),        # REWIND — Ray Volpe, Sullivan King
    ("COMET", "250469778", "gold", (472,)),        # Laserbeam (TiDo Edit) — Ray Volpe
    ("HOUSE", "67676901",  "gold", (384,)),        # Utopia — Dombresky
    ("mixed", "216468125", "gold", (192, 288)),    # Sexy (Extended Mix) — Matt Sassari (montage)
    ("T1",    "1783601",   "gold", (128,)),        # ESSE Work It x Take It (Bellevue Rework)
    ("T2",    "87057007",  "pin",  ()),            # Like I Like It — Mau P (pin from RB markers)
    ("T3",    "127938342", "pin",  ()),            # I Cannot (Extended Mix) — Anti Up (pin)
)


def pick_highest_tier_beat(tiered_markers):
    """Pinning rule (spec B3.7 T2/T3): the marker whose frozen F2 plan tier is
    highest, tie-break earliest beat. ``tiered_markers`` = iterable of (beat, tier).
    """
    tiered = [(int(b), int(t)) for b, t in tiered_markers]
    if not tiered:
        return None
    return sorted(tiered, key=lambda bt: (-bt[1], bt[0]))[0][0]


def build_anchor_rows(get_meta, readers, tier_fn, *, specs=ANCHOR_SPECS):
    """Build the seven anchor LocatorRows in ANCHOR_ROLES order (spec B3.7/B7).

    ``get_meta(content_id) -> LocatorMeta`` resolves an anchor's library row;
    ``tier_fn(meta, covered_drops) -> [(beat, tier)]`` returns the F2 plan tier per
    covered drop (real: lighting_moments_v2.build_track_plan; fake under test). Gold
    anchors use their fixed B3.7 beats; T2/T3 pin the highest-tier phrase drop.
    Returns ``(rows, pins)`` where ``pins`` maps the pinned roles (T2/T3) to beats.
    Fails closed via ``AnchorError`` if any anchor lacks valid v4, its content, or a
    usable covered marker — never a silent substitution (spec B3.7, B10).
    """
    if tuple(s[0] for s in specs) != ANCHOR_ROLES:
        raise AnchorError("anchor specs order must match selection.ANCHOR_ROLES")
    rows, pins = [], {}
    for role, cid, kind, gold in specs:
        meta = get_meta(cid)
        if meta is None:
            raise AnchorError(f"anchor {role}: content_id {cid} not found in library")
        times = readers.beatgrid_times(meta.analysis_data_path) or []
        present, valid, v4_n = readers.v4_status(meta.audio_path, times)
        if not valid:
            raise AnchorError(f"anchor {role} ({cid}): no valid v4 payload")
        n_beats = int(v4_n) if v4_n else len(times)
        drops = tuple(sorted(int(b) for b in (readers.phrase_drops(meta.analysis_data_path) or [])))
        if kind == "gold":
            beats = tuple(int(b) for b in gold)
        else:
            covered = [b for b in drops if b >= 0 and b + WINDOW <= n_beats]
            if not covered:
                raise AnchorError(f"anchor {role} ({cid}): no usable candidate markers")
            beat = pick_highest_tier_beat(tier_fn(meta, covered))
            if beat is None:
                raise AnchorError(f"anchor {role} ({cid}): tier pinning produced no beat")
            beats = (int(beat),)
            pins[role] = int(beat)
        for b in beats:
            if not (0 <= b and b + WINDOW <= n_beats):
                raise AnchorError(f"anchor {role} ({cid}): beat {b} lacks 16-beat coverage")
        if role == "mixed":
            rows.append(enrich(meta, readers, marker_beats=beats, anchor_montage_beats=beats))
        else:
            rows.append(enrich(meta, readers, marker_beats=beats, anchor_marker_beat=beats[0]))
    return rows, pins


# --- metadata-only row (spec B3.1: listing WITHOUT audio decode/hash) ----------
@dataclass(frozen=True)
class LocatorMeta:
    """One library row's metadata — no audio, no hashing, no v4/grid read."""
    content_id_locator: str
    artist: str
    title: str
    duration_s: float
    bpm: float
    audio_path: str
    analysis_data_path: Optional[str]
    is_scripted: bool = False


# --- injectable read-only reader bundle (real wiring in real_readers) ----------
@dataclass(frozen=True)
class LibraryReaders:
    """Read-only accessors. Real wiring imports the bridge; tests inject fakes.

    All callables are pure reads; none may write, extract, or mutate anything.
    - ``audio_sha256(path) -> str``: SHA-256 hex of the audio file bytes.
    - ``beatgrid_times(analysis_data_path) -> list[float] | None``: beat times (ms).
    - ``beatgrid_fingerprint(times) -> str``: stable grid fingerprint.
    - ``phrase_drops(analysis_data_path) -> list[int]``: candidate drop beats.
    - ``v4_status(audio_path, times) -> (present: bool, valid: bool, n_beats|None)``.
    - ``label_store_hash() -> str``: current label-store provenance hash.
    """
    audio_sha256: Callable[[str], str]
    beatgrid_times: Callable[[Optional[str]], Optional[list]]
    beatgrid_fingerprint: Callable[[list], str]
    phrase_drops: Callable[[Optional[str]], list]
    v4_status: Callable[[str, list], tuple]
    label_store_hash: Callable[[], str]


# --- layer 1: metadata listing (all rows, no audio) ---------------------------
def list_locators(contents, *, scripted_ids=()) -> list:
    """One ``LocatorMeta`` per non-deleted content row (spec B3.1, no audio read).

    ``contents`` is any iterable of objects exposing the DjmdContent attributes
    (``ID, Title, ArtistName, Length, BPM, FolderPath, AnalysisDataPath,
    rb_local_deleted``) — a real ``db.get_content()`` at Phase-1, ``SimpleNamespace``
    fixtures under test.
    """
    scripted = set(scripted_ids)
    out = []
    for c in contents:
        if getattr(c, "rb_local_deleted", 0):
            continue
        cid = str(c.ID)
        out.append(LocatorMeta(
            content_id_locator=cid,
            artist=str(getattr(c, "ArtistName", None) or ""),
            title=str(getattr(c, "Title", None) or ""),
            duration_s=float(getattr(c, "Length", 0.0) or 0.0),
            bpm=float(getattr(c, "BPM", 0.0) or 0.0) / 100.0,
            audio_path=str(getattr(c, "FolderPath", None) or ""),
            analysis_data_path=(str(c.AnalysisDataPath) if getattr(c, "AnalysisDataPath", None) else None),
            is_scripted=cid in scripted,
        ))
    return out


# --- seed-pool id pick (mirrors selection.seed_pool, metadata only) -----------
def seed_pool_ids(metas, *, pilot_seed, dev_content_ids=(), scripted_ids=()) -> list:
    """The 60 pool content-ids, by the exact spec B3.1 hash rule (no audio needed).

    Removes development + scripted rows, sorts survivors by
    ``SHA256(pilot_seed || content_id)`` and takes the first 60 — the identical
    ordering ``selection.seed_pool`` applies to full ``LocatorRow`` objects, so
    enriching only these ids is faithful to selection.
    """
    dev = set(dev_content_ids)
    scr = set(scripted_ids)
    survivors = [m for m in metas
                 if m.content_id_locator not in dev and m.content_id_locator not in scr and not m.is_scripted]
    survivors.sort(key=lambda m: selection_hash(pilot_seed, m.content_id_locator))
    return [m.content_id_locator for m in survivors[:POOL_SIZE]]


# --- layer 2: enrich (audio hash + v4 + grid + markers), pool + anchors only ---
def enrich(meta, readers, *, marker_beats=None, anchor_marker_beat=None,
           anchor_montage_beats=None) -> LocatorRow:
    """Build a full ``LocatorRow`` for ONE row (spec B3.1 audio/v4/grid/marker read).

    v4 is only read, never computed (spec B10): a present-but-invalid payload sets
    ``v4_valid=False`` (→ invalid_v4 exclusion); an absent one sets
    ``v4_present=False`` (→ missing_v4). ``marker_beats`` overrides the phrase-drop
    read when the caller already pinned specific beats (anchors); otherwise the
    candidate markers are the ANLZ phrase drops. ``n_beats`` comes from the valid v4
    when present, else the beatgrid length (so coverage can still be evaluated for a
    missing/invalid-v4 row that is about to be excluded anyway).
    """
    times = readers.beatgrid_times(meta.analysis_data_path) or []
    grid_fp = readers.beatgrid_fingerprint(times) if times else ""
    present, valid, v4_n_beats = readers.v4_status(meta.audio_path, times)
    n_beats = int(v4_n_beats) if (valid and v4_n_beats) else len(times)
    audio_sha = readers.audio_sha256(meta.audio_path)
    if marker_beats is not None:
        markers = tuple(sorted(int(b) for b in marker_beats))
    else:
        markers = tuple(sorted(int(b) for b in (readers.phrase_drops(meta.analysis_data_path) or [])))
    return LocatorRow(
        content_id_locator=meta.content_id_locator,
        audio_sha256=audio_sha,
        recording_lineage_id=meta.content_id_locator,   # each row its own lineage; dups caught by suspicious pairs
        audio_duplicate_group=audio_sha,                # exact-audio identity
        artist=meta.artist, title=meta.title, duration_s=meta.duration_s, bpm=meta.bpm,
        beatgrid_fingerprint=grid_fp,
        marker_set_fingerprint=sha256_hex(list(markers))[:16],
        label_store_hash=readers.label_store_hash(),
        n_beats=n_beats,
        candidate_markers=markers,
        v4_present=bool(present), v4_valid=bool(valid),
        is_scripted=meta.is_scripted,
        anchor_marker_beat=anchor_marker_beat,
        anchor_montage_beats=(tuple(int(b) for b in anchor_montage_beats)
                              if anchor_montage_beats else None),
    )


# --- real bridge wiring (the ONLY live-import path; never called by a test) ----
def real_readers(*, repo_root):
    """Wire ``LibraryReaders`` to the live bridge modules (Phase-1 only).

    Imports the bridge as the ``rb_ss_bridge_v2`` package from ``repo_root``'s
    parent, which is how the bridge's own relative imports resolve. Pure reads only.
    """
    import hashlib
    import os
    import sys
    from pathlib import Path

    parent = str(Path(repo_root).resolve().parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    import rb_ss_bridge_v2.filepath_resolver as fr
    import rb_ss_bridge_v2.anlz_reader as ar
    import rb_ss_bridge_v2.spectral_cache as sc

    def _audio_sha256(path):
        # A streaming/remote track (e.g. a soundcloud: locator) has no local file;
        # return a deterministic per-path sentinel — the row has no valid v4 either,
        # so it is excluded (missing_v4), never silently hashed to a real digest.
        if not path or not os.path.exists(path):
            return "no-local-audio:" + hashlib.sha256((path or "").encode("utf-8")).hexdigest()[:32]
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _anlz_path(analysis_data_path):
        return fr._local_anlz_path(analysis_data_path) if analysis_data_path else None

    def _beatgrid_times(analysis_data_path):
        p = _anlz_path(analysis_data_path)
        if not p:
            return None
        bg = fr._extract_beatgrid_from_anlz(p)
        return bg.get("beatgrid_times_ms") if bg else None

    def _phrase_drops(analysis_data_path):
        p = _anlz_path(analysis_data_path)
        if not p:
            return []
        try:
            tad = ar.read_anlz_drops(str(p))
        except Exception:
            return []
        return list(getattr(tad, "drop_beat_indices", []) or [])

    def _v4_status(audio_path, times):
        # No grid, no local audio, or any stat/parse failure ⇒ treat as missing v4
        # (the cache key stats the audio file, which raises for a remote locator).
        if not times or not audio_path or not os.path.exists(audio_path):
            return (False, False, None)
        try:
            key = sc._cache_key(audio_path, times)
            present = (sc._cache_dir_v4() / f"{key}.json").exists()
            v4 = sc.get_cached_v4(audio_path, times)
        except OSError:
            return (False, False, None)
        return (present, v4 is not None, getattr(v4, "n_beats", None) if v4 else None)

    def _label_store_hash():
        labels = Path(repo_root) / "local" / "labels"
        if not labels.exists():
            return "none"
        entries = []
        for f in sorted(labels.rglob("*")):
            try:
                st = f.stat()
            except OSError:
                continue
            entries.append([str(f.relative_to(labels)), st.st_size, st.st_mtime_ns])
        return sha256_hex(entries)

    return LibraryReaders(
        audio_sha256=_audio_sha256, beatgrid_times=_beatgrid_times,
        beatgrid_fingerprint=lambda t: sc._beatgrid_fingerprint(t),
        phrase_drops=_phrase_drops, v4_status=_v4_status, label_store_hash=_label_store_hash,
    )
