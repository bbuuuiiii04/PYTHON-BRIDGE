"""Offline gain-invariance check by RE-EXTRACTION — energy fabric (AWR-291, G-c).

The three modules' existing "gain invariance" unit tests add a float offset to
ALREADY-ROUNDED cached values, never re-round, and have no floor: they prove the
algebra cancels a synthetic offset, but cannot detect what the real pipeline does.
This tool applies Sturm's horse method (*ACM Computers in Entertainment* 14(2),
2016): apply a transformation IRRELEVANT to the construct (a uniform level
attenuation) and check the output does not move. It re-extracts real audio at a
second gain and compares E1 / E2 / E3 against the cached original.

Offline, read-only against the library, ~10 deterministically-chosen BY GENRE
tracks, one audio pass each. TWO hard safety rules, either of which would corrupt
the library if broken:
  * NEVER call `spectral_cache.put_cached_v4` and never write under the cache dir —
    a gain-shifted entry in the real v4 cache would silently poison every future
    energy run. The extractor is called directly, never a get-or-compute helper.
  * Never write to / move / re-encode any file under the Rekordbox library path.
    The only writes are inside a `tempfile.TemporaryDirectory()` and the optional
    `--out` report.

Report-only thresholds (not a CI gate — needs an audio pass + optional deps):
expected max delta ≈ 0.005 grade units (the 0.1 dB quantization, A.4 item 3); HARD
FAILURE (exit 1) if any grade moves by more than 0.10 (20× expected = a real
invariance break). Missing librosa / numpy / soundfile ⇒ exit 2.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache  # noqa: E402
from rb_ss_bridge_v2 import track_weight_v0  # noqa: E402
from rb_ss_bridge_v2 import section_energy_v0  # noqa: E402
from rb_ss_bridge_v2 import drop_energy_v0  # noqa: E402
from rb_ss_bridge_v2.anlz_reader import read_anlz_drops  # noqa: E402

SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
DB_PATH = Path("~/Library/Pioneer/rekordbox/master.db").expanduser()
BY_GENRE_FOLDER_ID = "666898931"
BY_GENRE_EXCLUDE = {"RAP"}

DELTA_DB = -6.0206          # MUST stay negative (attenuation): a positive gain
                            # could clip and confound the test with a 2nd transform
HARD_FAIL_DELTA = 0.10      # exit 1 if any grade moves more than this
EXPECTED_DELTA = 0.005      # the 0.1 dB quantization drift (A.4 item 3)
DB_FLOOR = -100.0           # 10*log10(_DB_FLOOR_POWER); invariance fails outright here


# --------------------------------------------------------------------------- #
# Pure comparison seam (unit-tested; no audio, no cache, no I/O)               #
# --------------------------------------------------------------------------- #
def max_grade_delta(orig: "Sequence[float]",
                    shifted: "Sequence[float]") -> "Optional[float]":
    """Max |orig[i] - shifted[i]| over two paired numeric grade lists. None when
    either is empty or the lengths differ — an unmatched comparison is NOT a zero
    delta and must not be read as a pass."""
    if not orig or not shifted or len(orig) != len(shifted):
        return None
    return max(abs(float(a) - float(b)) for a, b in zip(orig, shifted))


def perturbation_verdict(max_delta: "Optional[float]") -> "tuple":
    """(ok, reason). None (nothing comparable) fails closed."""
    if max_delta is None:
        return (False, "no_comparison")
    if max_delta > HARD_FAIL_DELTA:
        return (False, "invariance_break")
    return (True, "ok")


# --------------------------------------------------------------------------- #
# Per-layer grade extraction (distribution-independent, single-track)         #
# --------------------------------------------------------------------------- #
def _e1_values(v4) -> "Optional[list]":
    comp = track_weight_v0.components(v4)
    if comp is None:
        return None
    return [comp[k] for k in track_weight_v0.COMPONENT_KEYS]


def _e2_values(v4, data) -> "list":
    return [g["within_track"] for g in section_energy_v0.grade_sections(
        v4, anlz_drops=list(data.drop_beat_indices),
        anlz_buildups=list(data.buildup_beat_indices),
        anlz_breakdowns=list(data.breakdown_beat_indices), track_weight=None)]


def _e3_values(v4, data) -> "list":
    return [g["within_track"] for g in drop_energy_v0.grade_drops(
        v4, drop_beats=list(data.drop_beat_indices), track_weight=None)]


def _touches_floor(v4) -> bool:
    full = (getattr(v4, "series", None) or {}).get("full_db") or []
    return any(isinstance(x, (int, float)) and x <= DB_FLOOR + 1e-6 for x in full)


# --------------------------------------------------------------------------- #
# Enumeration (same read-only DB access as the three report tools)            #
# --------------------------------------------------------------------------- #
def _open_db() -> Any:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    return Rekordbox6Database(str(DB_PATH), unlock=True)


def _enumerate(db: Any) -> "list":
    genre_pls = [
        p for p in db.get_playlist()
        if str(getattr(p, "ParentID", "")) == BY_GENRE_FOLDER_ID
        and str(getattr(p, "Name", "")) not in BY_GENRE_EXCLUDE
    ]
    cids: "set" = set()
    for pl in genre_pls:
        for row in db.get_playlist_songs(PlaylistID=str(pl.ID)):
            cids.add(str(row.ContentID))
    tracks: "list[dict]" = []
    for c in db.get_content():
        if getattr(c, "rb_local_deleted", 0):
            continue
        filepath = str(c.FolderPath or "")
        if not filepath or not os.path.isfile(filepath):
            continue
        if str(c.ID) not in cids:
            continue
        anlz_rel = str(getattr(c, "AnalysisDataPath", "") or "")
        anlz_abs = str(SHARE_ROOT / anlz_rel.lstrip("/")) if anlz_rel else ""
        tracks.append({"content_id": str(c.ID), "title": str(c.Title or ""),
                       "filepath": filepath, "anlz_abs": anlz_abs})
    tracks.sort(key=lambda t: t["content_id"])
    return tracks


def run(argv: "Sequence[str]") -> int:
    ap = argparse.ArgumentParser(description="Offline energy gain-invariance check")
    ap.add_argument("--out", default=None, help="also write the report text here")
    args = ap.parse_args(list(argv))

    try:
        import librosa            # type: ignore  # noqa: F401
        import numpy as np        # type: ignore
        import soundfile as sf    # type: ignore
    except Exception as exc:
        sys.stderr.write("ENV ERROR: optional deps missing (%s): %s\n"
                         % (type(exc).__name__, exc))
        return 2
    from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
        extract_spectral_features_v4)

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    cache_dir = spectral_cache._cache_dir()
    if not cache_dir.exists():
        sys.stderr.write("ENV ERROR: cache dir absent: %s\n" % cache_dir)
        return 2
    try:
        db = _open_db()
    except Exception as exc:
        sys.stderr.write("ENV ERROR: cannot open Rekordbox DB (%s): %s\n"
                         % (type(exc).__name__, exc))
        return 2

    tracks = _enumerate(db)
    if not tracks:
        sys.stderr.write("ENV ERROR: no BY GENRE tracks enumerated\n")
        return 2
    step = max(1, len(tracks) // 10)
    selected = tracks[::step]

    emit("# Energy perturbation check — gain-invariance by RE-EXTRACTION")
    emit("# OFFLINE / read-only library. Temp-dir writes only; cache NEVER written.")
    emit("")
    emit("BY GENRE tracks: %d   selected (every %d-th): %d   DELTA_DB=%.4f"
         % (len(tracks), step, len(selected), DELTA_DB))
    emit("")

    worst = 0.0
    hard_fail = False
    gain = 10.0 ** (DELTA_DB / 20.0)
    with tempfile.TemporaryDirectory() as td:
        for t in selected:
            anlz = t["anlz_abs"]
            data = read_anlz_drops(anlz) if (anlz and os.path.isfile(anlz)) else None
            ctx = data.waveform_context if data is not None else None
            grid = (list(ctx.beatgrid_times_ms)
                    if ctx is not None and len(ctx.beatgrid_times_ms) >= 2 else [])
            if not grid:
                emit("  SKIP no_grid   %s" % t["title"][:60])
                continue
            v4 = spectral_cache.get_cached_v4(t["filepath"], grid)
            if v4 is None:
                emit("  SKIP no_v4     %s" % t["title"][:60])
                continue
            try:
                y, sr = librosa.load(t["filepath"], sr=22050, mono=True)
                y_shift = y * gain
                # tmp_wav lives ONLY inside the TemporaryDirectory — never next to
                # the source, never in the library. float32 subtype: no re-quantize.
                tmp_wav = os.path.join(td, "shift_%s.wav" % t["content_id"])
                sf.write(tmp_wav, y_shift, 22050, subtype="FLOAT")
                shifted = extract_spectral_features_v4(tmp_wav, grid)
                os.remove(tmp_wav)     # keep the temp dir small across ~10 tracks
            except Exception as exc:
                emit("  SKIP extract-failed (%s) %s" % (type(exc).__name__, t["title"][:50]))
                continue
            if shifted is None:
                emit("  SKIP shifted_none %s" % t["title"][:56])
                continue

            d1 = max_grade_delta(_e1_values(v4), _e1_values(shifted))
            d2 = max_grade_delta(_e2_values(v4, data), _e2_values(shifted, data))
            d3 = max_grade_delta(_e3_values(v4, data), _e3_values(shifted, data))
            track_max = max([d for d in (d1, d2, d3) if d is not None], default=None)
            if track_max is not None:
                worst = max(worst, track_max)
                if track_max > HARD_FAIL_DELTA:
                    hard_fail = True
            emit("  E1 %s  E2 %s  E3 %s   floor=%s   %s"
                 % (_fmt(d1), _fmt(d2), _fmt(d3),
                    "YES" if _touches_floor(v4) else "no", t["title"][:44]))

    emit("")
    emit("worst delta across all layers/tracks = %.5f  (expected ~%.3f, hard fail > %.2f)"
         % (worst, EXPECTED_DELTA, HARD_FAIL_DELTA))
    ok, reason = perturbation_verdict(worst if selected else None)
    emit("VERDICT: %s   reason=%s" % ("PASS" if (ok and not hard_fail) else "FAIL",
                                      "invariance_break" if hard_fail else reason))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if hard_fail else 0


def _fmt(x: "Optional[float]") -> str:
    return "%.5f" % x if x is not None else "  n/a  "


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
