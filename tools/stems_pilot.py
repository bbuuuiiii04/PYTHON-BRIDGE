#!/usr/bin/env python3
"""STEMS PILOT runner (AWR-168): gated 4-stem separation quality gate.

Splits 30-50 of the operator's own masters into drums/bass/vocals/other with
HTDemucs, measures per-stem per-beat envelopes, and evaluates a FROZEN pass/fail
gate on the elements he named (sidechained subs, offbeat hats, claps/snares,
screeches, wobbles, 808s, rolls, distorted kicks, vocal axis). Offline tooling
only: it reads audio + ANLZ beatgrids and writes JSON to its OWN namespace
(``~/Library/Application Support/RBSS Bridge/stems_pilot/``). It never touches
the live bridge, the v3/v4 spectral caches, configs, or any runtime module.
Heavy imports (torch, demucs, librosa) are lazy — the code + ``--dry-run`` +
``--report`` paths run with no install.

GATED INSTALL PROCEDURE (run only after disk cleanup + executive word):

    python3.11 -m venv ~/.venvs/rbss-stems
    ~/.venvs/rbss-stems/bin/pip install --no-cache-dir \
        torch demucs librosa soundfile pyrekordbox
    # torch 2.x cp311 arm64; pin + record resolved versions in the report.
    # pyrekordbox is required for corpus enumeration (not in the base brief
    # pip line; added here because _enumerate_tracks needs it).

Disk budget: torch + deps ~1.5-2.5 GB installed; htdemucs weights ~80 MB
(downloaded to the demucs cache on first run). Stems NEVER hit disk except
``--snippets`` clips. The tool refuses to start and aborts between tracks below
``--min-free-gb`` (default 4 GB hard floor; run with 10 per the exec constraint).

TEARDOWN on call-off (refund the disk):

    rm -rf ~/.venvs/rbss-stems ~/.cache/torch/hub/checkpoints  # demucs weights
    # (weights also cached under ~/.cache/torch or the demucs models dir)

Usage:
    python3.11 tools/stems_pilot.py --dry-run                 # resolve corpus, no deps beyond pyrekordbox
    ~/.venvs/rbss-stems/bin/python tools/stems_pilot.py --limit 5 --min-free-gb 10   # tune first
    ~/.venvs/rbss-stems/bin/python tools/stems_pilot.py --min-free-gb 10 --threads 3 # full pilot + gate
    ~/.venvs/rbss-stems/bin/python tools/stems_pilot.py --report                     # recompute gate only
    ~/.venvs/rbss-stems/bin/python tools/stems_pilot.py --sweep --min-free-gb 10     # full library (on PASS)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # parent-of-repo → package

import numpy as np  # noqa: E402

import stems_pilot_metrics as spm  # noqa: E402  (sibling tools/ module)
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    _DB_FLOOR_POWER,
    _HOP,
    _N_FFT,
    BAND_RANGES,
)

SHARE_ROOT = Path("~/Library/Pioneer/rekordbox/share").expanduser()
DB_PATH = Path("~/Library/Pioneer/rekordbox/master.db").expanduser()
OUT_ROOT = Path("~/Library/Application Support/RBSS Bridge/stems_pilot").expanduser()
ENV_DIR = OUT_ROOT / "envelopes"
LABELS_PATH = OUT_ROOT / "labels.json"  # operator ground-truth labels (P1)
SR = 44100  # demucs htdemucs native rate

# Pinned anchors (element -> case-insensitive title substrings). All are
# operator-validated moments from the authority docs (spec Part B Task 1).
# "distorted kicks / industrial claps-snares" is scored as two elements sharing
# the industrial anchor set; that makes 9 scored elements.
ANCHORS: dict[str, list[str]] = {
    "wobble": ["capochino", "girl$", "you & me", "lunch"],
    "sidechain_sub": ["rock ur world"],
    "rolls": ["girl$", "satisfaction"],
    "eight08s": ["one chance", "kidstopbreathing"],
    "screeches": ["drop em", "stfu", "gnarly", "embercore"],
    "distorted_kicks": ["pitch mad attak", "tremor", "age of love"],
    "claps_snares": ["pitch mad attak", "tremor", "age of love"],
    "offbeat_hats": ["which one", "bangarang"],
    "vocal_axis": ["can't say nah", "kissed", "adventure of a lifetime", "temperature"],
}
ELEMENTS = list(ANCHORS.keys())
MIN_CORPUS = 30
MAX_CORPUS = 50


# ---------------------------------------------------------------------------
# disk floor (self-enforced, tool-level, per Part C invariant)
# ---------------------------------------------------------------------------
def _free_gb(path: str = "/") -> float:
    return shutil.disk_usage(path).free / 1e9


def _disk_ok(min_free_gb: float, path: str = "/") -> bool:
    return _free_gb(path) >= min_free_gb


# ---------------------------------------------------------------------------
# corpus resolution (reuses tools/spectral_sweep.py enumeration exactly)
# ---------------------------------------------------------------------------
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


def _beatgrid_for(anlz_abs: str) -> list[float] | None:
    from rb_ss_bridge_v2.anlz_reader import read_anlz_drops

    if not anlz_abs or not os.path.isfile(anlz_abs):
        return None
    ctx = read_anlz_drops(anlz_abs).waveform_context
    if ctx is None or len(ctx.beatgrid_times_ms) < 2:
        return None
    return list(ctx.beatgrid_times_ms)


def _resolve_corpus(limit: int = 0) -> tuple[list[dict], dict[str, list[str]]]:
    """Return (picked tracks with grids + element tags, unresolved anchors).

    Each picked track: {content_id, title, filepath, anlz_abs, grid, elements}.
    """
    tracks = _enumerate_tracks()
    by_title = [(t, t["title"].lower()) for t in tracks]
    picked: dict[str, dict] = {}
    unresolved: dict[str, list[str]] = {}
    notes: dict[str, list[str]] = {}

    for element, needles in ANCHORS.items():
        for needle in needles:
            matches = [t for (t, low) in by_title if needle in low]
            gridded = [(m, _beatgrid_for(m["anlz_abs"])) for m in matches]
            gridded = [(m, g) for (m, g) in gridded if g is not None]
            if not gridded:
                unresolved.setdefault(element, []).append(
                    needle if not matches else f"{needle} (matched {len(matches)}, none gridded)")
                continue
            if len(matches) > 1:
                # versions/edits of the same song — include all gridded matches
                # (not a guess of one), capped, and record the ambiguity note.
                notes.setdefault(element, []).append(
                    f"{needle}: {len(matches)} matches, {len(gridded)} gridded (all included, cap 3)")
            for m, g in gridded[:3]:
                entry = picked.setdefault(m["content_id"], {**m, "grid": g, "elements": []})
                if element not in entry["elements"]:
                    entry["elements"].append(element)

    # fill to MIN_CORPUS from remaining gridded tracks (deterministic by id),
    # tagged "fill" for context/reconstruction stats (recorded in report).
    if len(picked) < MIN_CORPUS:
        for t in tracks:
            if len(picked) >= MIN_CORPUS:
                break
            if t["content_id"] in picked:
                continue
            grid = _beatgrid_for(t["anlz_abs"])
            if grid is None:
                continue
            picked[t["content_id"]] = {**t, "grid": grid, "elements": ["fill"]}

    # anchors first, fill last, cap at MAX_CORPUS (spec: 30-50 tracks).
    out = sorted(picked.values(), key=lambda t: t["content_id"])
    anchors = [t for t in out if t["elements"] != ["fill"]]
    fills = [t for t in out if t["elements"] == ["fill"]]
    out = (anchors + fills)[:MAX_CORPUS]
    if limit:
        out = out[:limit]
    if notes:
        unresolved = {**unresolved, "_ambiguity_notes": notes}  # carried into report
    return out, unresolved


# ---------------------------------------------------------------------------
# separation + STFT (gated path — lazy heavy imports)
# ---------------------------------------------------------------------------
_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is None:
        import demucs.pretrained  # type: ignore

        _MODEL = demucs.pretrained.get_model("htdemucs")
        _MODEL.cpu()
        _MODEL.eval()
    return _MODEL


def _decode_stereo(filepath: str):
    import librosa  # type: ignore

    y, _sr = librosa.load(filepath, sr=SR, mono=False)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim == 1:
        y = np.stack([y, y])
    return np.ascontiguousarray(y)  # (2, n)


def _separate(mix_stereo, model, segment: float):
    """Return {stem_name: (2, n) float32}. One permitted segment-halving retry."""
    import torch  # type: ignore
    from demucs.apply import apply_model  # type: ignore

    wav = torch.from_numpy(mix_stereo)[None]  # (1, 2, n)
    for seg in (segment, segment / 2.0):
        try:
            with torch.no_grad():
                out = apply_model(
                    model, wav, split=True, segment=seg, overlap=0.25,
                    device="cpu", num_workers=0, progress=False,
                )
            arr = out[0].cpu().numpy()  # (sources, 2, n)
            return {name: arr[i] for i, name in enumerate(model.sources)}, seg
        except RuntimeError as exc:  # OOM / alloc — halve once then give up
            if seg != segment:
                raise
            print(f"    segment {seg:.1f}s failed ({exc}); retrying at {seg/2:.1f}s", flush=True)
    raise RuntimeError("separation failed after segment halving")


def _stft_power(mono):
    import librosa  # type: ignore

    S = np.abs(librosa.stft(mono, n_fft=_N_FFT, hop_length=_HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=_N_FFT)
    frame_times_ms = librosa.frames_to_time(
        np.arange(S.shape[1]), sr=SR, hop_length=_HOP
    ) * 1000.0
    return S, freqs, frame_times_ms


def _band_power(S, freqs, band: str):
    if band == "full":
        return S.mean(axis=0)
    lo, hi = BAND_RANGES[band]
    mask = (freqs >= lo) & (freqs < hi)
    if not bool(np.any(mask)):
        return np.full(S.shape[1], _DB_FLOOR_POWER)
    return S[mask, :].mean(axis=0)


def _frames_db(S, freqs, band: str):
    p = _band_power(S, freqs, band)
    return tuple(round(float(v), 1) for v in 10.0 * np.log10(np.maximum(p, _DB_FLOOR_POWER)))


def _track_envelopes(filepath: str, grid: list[float], model, segment: float) -> dict:
    """Separate + measure one track. Returns the per-track envelope payload."""
    mix = _decode_stereo(filepath)
    stems, used_seg = _separate(mix, model, segment)
    n = min([mix.shape[1]] + [s.shape[1] for s in stems.values()])
    mix = mix[:, :n]
    stems = {k: v[:, :n] for k, v in stems.items()}

    frame_times_ms = None
    payload_stems: dict[str, dict] = {}
    wobble_frames: dict[str, list] = {}
    for name, wav in stems.items():
        mono = wav.mean(axis=0)
        S, freqs, ft = _stft_power(mono)
        frame_times_ms = ft
        bands = spm.STEM_BANDS.get(name, ("full",))
        power_frames = {b: _band_power(S, freqs, b) for b in bands}
        payload_stems[name] = spm.stem_beat_envelopes(power_frames, ft, grid)
        if name in ("bass", "other"):
            wobble_frames[name] = list(_frames_db(S, freqs, "growl_band"))

    # reconstruction: sum stem waveforms vs the mix (mono), per-beat dB delta
    summed_mono = np.sum([s for s in stems.values()], axis=0).mean(axis=0)
    mix_mono = mix.mean(axis=0)
    S_sum, freqs_s, ft_s = _stft_power(summed_mono)
    S_mix, _f, _ft = _stft_power(mix_mono)
    recon = spm.reconstruction_delta_db(
        _band_power(S_mix, _f, "full"), _band_power(S_sum, freqs_s, "full"), ft_s, grid
    )
    full_mix_beats = spm.stem_beat_envelopes(
        {"full": _band_power(S_mix, _f, "full")}, _ft, grid
    )["full"]["beat"]

    return {
        "n_beats": len(spm._beat_spans(grid)),
        "frame_hop_s": round(_HOP / float(SR), 6),
        "segment_used_s": round(used_seg, 2),
        "stems": payload_stems,
        "wobble_frames": wobble_frames,
        "reconstruction_delta_beats": list(recon),
        "vocal_full_beats": list(payload_stems.get("vocals", {}).get("full", {}).get("beat", [])),
        "full_mix_beats": list(full_mix_beats),
    }


# ---------------------------------------------------------------------------
# per-element proxy scoring (each returns "cleared on this track" bool + stat)
# ---------------------------------------------------------------------------
def _beats(T, stem, band):
    return np.asarray(T["stems"].get(stem, {}).get(band, {}).get("beat", []), dtype=float)


def _quarters(T, stem, band):
    return T["stems"].get(stem, {}).get(band, {}).get("quarter", [])


def _crest(arr, hi=95, lo=50):
    a = np.asarray(arr, dtype=float)
    return float(np.percentile(a, hi) - np.percentile(a, lo)) if a.size else 0.0


def _high_energy_windows(full_beats, top_frac=0.4, min_run=4):
    a = np.asarray(full_beats, dtype=float)
    if a.size < min_run:
        return []
    thr = np.percentile(a, 100 * (1 - top_frac))
    windows, start = [], None
    for i, v in enumerate(a):
        if v >= thr and start is None:
            start = i
        elif v < thr and start is not None:
            if i - start >= min_run:
                windows.append((start, i))
            start = None
    if start is not None and a.size - start >= min_run:
        windows.append((start, a.size))
    return windows


def _pump_stat(T) -> float:
    return spm.pump_visibility(_quarters(T, "bass", "sub"), _quarters(T, "drums", "attack_low"))


def _rolls_stat(T) -> float:
    """Longest run of consecutive beats whose drums-high sub-beats are ALL filled
    (min-of-4 quarters >= track high p60). A snare/hi-hat buildup roll sustains
    sub-beat energy across several beats; a single backbeat hit does not. Tuned
    on the first-5 set: the labeled roll (Girl$ snare buildup) = 13, non-rolls 1-5.
    """
    q = _quarters(T, "drums", "high")
    b = _beats(T, "drums", "high")
    if not q or b.size == 0:
        return 0.0
    p60 = float(np.percentile(b, 60))
    best = run = 0
    for slots in q:
        run = run + 1 if (len(slots) == 4 and min(slots) >= p60) else 0
        best = max(best, run)
    return float(best)


def _eight08s_stat(T) -> float:
    b = _beats(T, "bass", "sub")
    if b.size == 0:
        return 0.0
    p95 = np.percentile(b, 95)
    return float(np.mean(b >= p95 - 6.0))  # fraction sustained near sub peak


def _screeches_stat(T) -> float:
    return _crest(_beats(T, "other", "mid"), 95, 50)


def _distorted_kicks_stat(T) -> float:
    flat = [v for slots in _quarters(T, "drums", "attack_low") for v in slots]
    return _crest(flat, 95, 50)


def _claps_snares_stat(T) -> float:
    return _crest(_beats(T, "drums", "high"), 90, 50)


def _offbeat_hats_stat(T) -> float:
    q = _quarters(T, "drums", "high")
    if not q:
        return 0.0
    diffs = [((s[1] + s[3]) / 2.0) - ((s[0] + s[2]) / 2.0) for s in q if len(s) == 4]
    return float(np.mean(diffs)) if diffs else 0.0


# element -> (stat function, clear threshold). vocal_axis is scored separately.
ELEMENT_STATS = {
    "sidechain_sub": (_pump_stat, 3.0),
    "rolls": (_rolls_stat, 6.0),  # >=6 consecutive all-sub-beats-filled beats

    "eight08s": (_eight08s_stat, 0.15),
    "screeches": (_screeches_stat, 10.0),
    "distorted_kicks": (_distorted_kicks_stat, 8.0),
    "claps_snares": (_claps_snares_stat, 8.0),
    "offbeat_hats": (_offbeat_hats_stat, 2.0),
}
WOBBLE_CONC_FLOOR = 0.30


def _wobble_cleared(T, grid: list[float]) -> tuple[bool, float]:
    best = 0.0
    for stem in ("bass", "other"):
        frames = T["wobble_frames"].get(stem)
        if not frames:
            continue
        n = len(grid)
        for lo in range(0, max(1, n - 4), 2):
            rate, conc = spm.modulation_strength(frames, T["frame_hop_s"], grid, (lo, lo + 4))
            if 0.5 <= rate <= 8.0:
                best = max(best, conc)
    return (best >= WOBBLE_CONC_FLOOR, round(best, 4))


def _wobble_labeled(T, grid: list[float], moments_ms: list[float]) -> list[dict]:
    """Score modulation at the operator's labeled moments (spec-faithful: the
    criterion is 'dominant rate readable at his moments'). Background = median
    scan concentration across the track, reported alongside for honesty (shows
    whether the moment stands out from beat-rate periodicity) but not gated."""
    n = len(grid)
    concs = []
    for stem in ("bass", "other"):
        frames = T["wobble_frames"].get(stem)
        if not frames:
            continue
        for lo in range(0, max(1, n - 4), 2):
            _r, c = spm.modulation_strength(frames, T["frame_hop_s"], grid, (lo, lo + 4))
            concs.append(c)
    background = float(np.median(concs)) if concs else 0.0
    out = []
    for ms in moments_ms:
        bi = spm.nearest_beat(grid, ms)
        win = (max(0, bi - 2), min(n - 1, bi + 2))
        best_rate, best_conc = 0.0, 0.0
        for stem in ("bass", "other"):
            frames = T["wobble_frames"].get(stem)
            if not frames:
                continue
            rate, conc = spm.modulation_strength(frames, T["frame_hop_s"], grid, win)
            if conc > best_conc:
                best_rate, best_conc = rate, conc
        out.append({
            "at_s": round(ms / 1000.0, 1),
            "rate_cpb": best_rate,
            "conc": round(best_conc, 4),
            "background_conc": round(background, 4),
            "cleared": bool(0.5 <= best_rate <= 8.0 and best_conc >= WOBBLE_CONC_FLOOR),
        })
    return out


def _wobble_spans_scored(T, grid: list[float], span_windows: list[tuple[int, int]]) -> list[dict]:
    """Score operator-labeled wobble SPANS (whole sections: 'repeats throughout
    the drop'). Same frozen floors as moments; background = median concentration
    over same-width windows tiled across the track (matched-scale honesty)."""
    n = len(grid)
    out = []
    for lo, hi in span_windows:
        width = max(4, hi - lo)
        bg = []
        best_rate, best_conc = 0.0, 0.0
        for stem in ("bass", "other"):
            frames = T["wobble_frames"].get(stem)
            if not frames:
                continue
            for s in range(0, max(1, n - width), width):
                _r, c = spm.modulation_strength(frames, T["frame_hop_s"], grid, (s, s + width))
                bg.append(c)
            rate, conc = spm.modulation_strength(frames, T["frame_hop_s"], grid, (lo, hi))
            if conc > best_conc:
                best_rate, best_conc = rate, conc
        out.append({
            "span_s": [round(grid[lo] / 1000.0, 1), round(grid[min(hi, n - 1)] / 1000.0, 1)],
            "rate_cpb": best_rate,
            "conc": round(best_conc, 4),
            "background_conc": round(float(np.median(bg)) if bg else 0.0, 4),
            "cleared": bool(0.5 <= best_rate <= 8.0 and best_conc >= WOBBLE_CONC_FLOOR),
        })
    return out


def _label_windows_beats(windows, grid: list[float]) -> list[tuple[int, int]]:
    out = []
    for pair in windows or []:
        a = spm.nearest_beat(grid, spm.parse_mmss(pair[0]))
        b = spm.nearest_beat(grid, spm.parse_mmss(pair[1]))
        if b > a:
            out.append((a, b))
    return out


# ---------------------------------------------------------------------------
# scorecard aggregation + gate
# ---------------------------------------------------------------------------
def _verdict(cleared: int) -> str:
    return "PASS" if cleared >= 2 else ("PARTIAL" if cleared == 1 else "FAIL")


def _build_scorecard(records: list[dict], op: dict, thresholds: dict) -> dict:
    """records: [{content_id,title,elements,grid,env,labels?}] for separated tracks.

    Once ANY operator label of a kind exists, that criterion scores labeled
    anchors only (auto-derived proxies for vocal windows / wobble scan are the
    exact thing the pilot proved invalid); unlabeled anchors show "unlabeled"."""
    labeled_wobble_any = any(
        (r.get("labels") or {}).get("wobble_moments") or (r.get("labels") or {}).get("wobble_spans")
        for r in records
    )
    labeled_vocal_any = any((r.get("labels") or {}).get("vocal_free_windows") for r in records)
    # reconstruction: frac of tracks whose median per-beat |delta| <= threshold
    recon_ok = 0
    recon_meds = []
    for r in records:
        d = r["env"]["reconstruction_delta_beats"]
        med = float(np.median(d)) if d else 99.0
        recon_meds.append(med)
        if med <= thresholds["recon_median_db"]:
            recon_ok += 1
    tracks_within_frac = recon_ok / len(records) if records else 0.0

    # per-element PASS/PARTIAL/FAIL across each element's anchor tracks
    elements: dict[str, str] = {}
    element_detail: dict[str, list] = {}
    for element in ELEMENTS:
        anchors = [r for r in records if element in r["elements"]]
        cleared = 0
        detail = []
        for r in anchors:
            labels = r.get("labels") or {}
            if element == "wobble":
                if labels.get("wobble_moments") or labels.get("wobble_spans"):
                    moments = _wobble_labeled(
                        r["env"], r["grid"],
                        [spm.parse_mmss(m) for m in labels.get("wobble_moments") or []],
                    ) + _wobble_spans_scored(
                        r["env"], r["grid"],
                        _label_windows_beats(labels.get("wobble_spans"), r["grid"]),
                    )
                    ok = any(m["cleared"] for m in moments)
                    stat = moments
                elif labeled_wobble_any:
                    ok, stat = False, "unlabeled"
                else:
                    ok, stat = _wobble_cleared(r["env"], r["grid"])
            elif element == "vocal_axis":
                if labels.get("vocal_free_windows"):
                    windows = _label_windows_beats(labels["vocal_free_windows"], r["grid"])
                elif labeled_vocal_any:
                    windows = []
                else:
                    windows = _high_energy_windows(r["env"]["full_mix_beats"])
                margin = spm.ghost_margin_db(r["env"]["vocal_full_beats"], windows)
                if not windows:
                    ok, stat = False, "unlabeled"
                else:
                    ok, stat = (margin <= thresholds["ghost_margin_db"]), round(margin, 1)
            else:
                fn, thr = ELEMENT_STATS[element]
                stat = round(float(fn(r["env"])), 3)
                ok = stat >= thr
            cleared += int(ok)
            detail.append({"title": r["title"][:40], "stat": stat, "cleared": ok})
        elements[element] = _verdict(cleared) if anchors else "FAIL"
        element_detail[element] = detail

    # sidechain: pump>=3dB on how many of the sidechain anchors
    sidechain_anchors = [r for r in records if "sidechain_sub" in r["elements"]]
    anchors_pumped = sum(
        1 for r in sidechain_anchors if _pump_stat(r["env"]) >= thresholds["pump_db"]
    )

    # vocal: pair separation (extremes of vocal presence among vocal anchors) +
    # worst ghost margin. With operator labels: labeled windows on labeled
    # anchors only; without: auto-derived high-energy windows (legacy).
    vocal_anchors = [r for r in records if "vocal_axis" in r["elements"]]
    if labeled_vocal_any:
        margins = [
            spm.ghost_margin_db(
                r["env"]["vocal_full_beats"],
                _label_windows_beats((r.get("labels") or {}).get("vocal_free_windows"), r["grid"]),
            )
            for r in vocal_anchors
            if (r.get("labels") or {}).get("vocal_free_windows")
        ]
    else:
        margins = [
            spm.ghost_margin_db(
                r["env"]["vocal_full_beats"], _high_energy_windows(r["env"]["full_mix_beats"])
            )
            for r in vocal_anchors
        ]
    worst_ghost = max(margins) if margins else 0.0  # closest to 0 = worst bleed
    presences = [
        (float(np.median(np.asarray(r["env"]["vocal_full_beats"], dtype=float)))
         - float(np.median(np.asarray(r["env"]["full_mix_beats"], dtype=float))))
        if r["env"]["vocal_full_beats"] else -99.0
        for r in vocal_anchors
    ]
    pair_separates = (max(presences) - min(presences) >= 3.0) if len(presences) >= 2 else False

    # wobble: with labels, count the operator's cleared moments; without,
    # legacy one-per-anchor scan count (known false-positive-prone).
    wobble_moments = 0
    for r in records:
        if "wobble" not in r["elements"]:
            continue
        labels = r.get("labels") or {}
        if labeled_wobble_any:
            if labels.get("wobble_moments") or labels.get("wobble_spans"):
                scored = _wobble_labeled(
                    r["env"], r["grid"],
                    [spm.parse_mmss(m) for m in labels.get("wobble_moments") or []],
                ) + _wobble_spans_scored(
                    r["env"], r["grid"],
                    _label_windows_beats(labels.get("wobble_spans"), r["grid"]),
                )
                wobble_moments += sum(int(m["cleared"]) for m in scored)
        else:
            ok, _stat = _wobble_cleared(r["env"], r["grid"])
            wobble_moments += int(ok)

    return {
        "operational": op,
        "reconstruction": {
            "tracks_within_frac": round(tracks_within_frac, 3),
            "median_delta_db_p50": round(float(np.median(recon_meds)), 2) if recon_meds else None,
        },
        "sidechain": {"anchors_pumped": anchors_pumped, "anchors_total": len(sidechain_anchors)},
        "vocal": {"pair_separates": pair_separates, "ghost_margin_db": round(worst_ghost, 1)},
        "wobble": {"moments_detected": wobble_moments},
        "labels": {
            "wobble_labeled_tracks": sum(
                1 for r in records if (r.get("labels") or {}).get("wobble_moments")),
            "vocal_labeled_tracks": sum(
                1 for r in records if (r.get("labels") or {}).get("vocal_free_windows")),
        },
        "elements": elements,
        "element_detail": element_detail,
        "n_tracks": len(records),
    }


# ---------------------------------------------------------------------------
# run loops
# ---------------------------------------------------------------------------
def _peak_rss_gb() -> float:
    import resource

    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss / 1e9 if sys.platform == "darwin" else maxrss / 1e6  # darwin=bytes, linux=KB


def _cache_key(filepath: str, grid: list[float]) -> str | None:
    from rb_ss_bridge_v2.spectral_cache import _cache_key as ck

    return ck(filepath, grid)


def _run_pilot(args) -> int:
    if not _disk_ok(args.min_free_gb):
        print(f"ABORT: free disk {_free_gb():.1f} GB < floor {args.min_free_gb} GB", flush=True)
        return 3
    import torch  # type: ignore

    torch.set_num_threads(args.threads)
    ENV_DIR.mkdir(parents=True, exist_ok=True)

    corpus, unresolved = _resolve_corpus(args.limit)
    print(f"pilot corpus: {len(corpus)} gridded tracks; unresolved anchors: {unresolved}", flush=True)
    model = _load_model()

    records, n_err, started = [], 0, time.perf_counter()
    for i, t in enumerate(corpus, 1):
        if not _disk_ok(args.min_free_gb):
            print(f"ABORT between tracks: free disk {_free_gb():.1f} GB < {args.min_free_gb} GB", flush=True)
            break
        key = _cache_key(t["filepath"], t["grid"])
        env_path = ENV_DIR / f"{key}.json"
        if key and env_path.exists():  # resumable
            env = json.loads(env_path.read_text())
        else:
            t0 = time.perf_counter()
            try:
                env = _track_envelopes(t["filepath"], t["grid"], model, args.segment)
            except Exception as exc:  # per-track: log + skip (resumable)
                n_err += 1
                print(f"[{i}/{len(corpus)}] SKIP {t['title'][:40]}: {exc}", flush=True)
                continue
            env["sep_seconds"] = round(time.perf_counter() - t0, 1)
            env["peak_rss_gb"] = round(_peak_rss_gb(), 2)
            env["content_id"] = t["content_id"]
            env["title"] = t["title"]
            env["elements"] = t["elements"]
            if key:
                env_path.write_text(json.dumps(env))
        records.append({**t, "env": env})
        if i % 5 == 0 or i == len(corpus):
            el = (time.perf_counter() - started) / 60.0
            print(f"[STEMS-HB] pilot {i}/{len(corpus)} err={n_err} rss={_peak_rss_gb():.1f}GB "
                  f"elapsed={el:.1f}m free={_free_gb():.0f}GB", flush=True)

    return _finish_scorecard(records, corpus, n_err, unresolved, args)


def _finish_scorecard(records, corpus, n_err, unresolved, args) -> int:
    n_sep = len(records)
    op = {
        "separated_ok_frac": round(n_sep / len(corpus), 3) if corpus else 0.0,
        "peak_rss_gb": round(_peak_rss_gb(), 2),
        "errors": n_err,
        "median_sep_seconds": round(
            float(np.median([r["env"].get("sep_seconds", 0.0) for r in records])), 1
        ) if records else 0.0,
    }
    thresholds = dict(spm.DEFAULT_THRESHOLDS)
    scorecard = _build_scorecard(records, op, thresholds)
    gate = spm.evaluate_gates(scorecard, thresholds)
    scorecard["gate"] = gate
    scorecard["unresolved_anchors"] = unresolved
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "scorecard.json").write_text(json.dumps(scorecard, indent=1))
    _write_report_md(scorecard)
    print(json.dumps({"verdict": gate["verdict"], "call_off": gate["call_off_reasons"],
                      "elements": scorecard["elements"], "operational": op}, indent=1), flush=True)
    return 0 if gate["verdict"] == "PASS" else 1


def _write_report_md(scorecard: dict) -> None:
    g = scorecard["gate"]
    lines = [
        "# STEMS PILOT scorecard", "",
        f"**Verdict: {g['verdict']}**  call-off: {g['call_off_reasons'] or 'none'}", "",
        f"- tracks separated: {scorecard['n_tracks']}",
        f"- operational: {scorecard['operational']}",
        f"- reconstruction: {scorecard['reconstruction']}",
        f"- sidechain: {scorecard['sidechain']}",
        f"- vocal: {scorecard['vocal']}",
        f"- wobble: {scorecard['wobble']}",
        f"- unresolved anchors: {scorecard.get('unresolved_anchors', {})}", "",
        "## Elements", "",
    ]
    for el, verdict in scorecard["elements"].items():
        lines.append(f"- **{el}**: {verdict} — {scorecard['element_detail'].get(el, [])}")
    (OUT_ROOT / "report.md").write_text("\n".join(lines) + "\n")


def _run_report(args) -> int:
    """Recompute scorecard + gate from existing envelope JSONs (no separation).
    Auto-loads operator labels from ``labels.json`` when present; labeled tracks
    get their REAL beatgrid re-resolved (mm:ss labels need true beat times —
    the uniform fallback grid is fiction)."""
    if not ENV_DIR.exists():
        print("no envelopes to report on", flush=True)
        return 1
    labels = _load_labels()
    grids = _real_grids(set(labels)) if labels else {}
    records = []
    n_labeled = 0
    for p in sorted(ENV_DIR.glob("*.json")):
        env = json.loads(p.read_text())
        cid = str(env.get("content_id", p.stem))
        grid, track_labels = _grid_from_env(env), None
        if cid in labels:
            real = grids.get(cid)
            if real and abs((len(real) - 1) - env.get("n_beats", 0)) <= 2:
                grid, track_labels = real, labels[cid]
                n_labeled += 1
            else:
                print(f"labels SKIPPED for {env.get('title', cid)!r}: "
                      f"{'no real beatgrid resolvable' if not real else 'beatgrid length drifted'}",
                      flush=True)
        records.append({
            "content_id": cid,
            "title": env.get("title", p.stem),
            "elements": env.get("elements", ["fill"]),
            "grid": grid,
            "env": env,
            **({"labels": track_labels} if track_labels else {}),
        })
    if labels:
        print(f"labels: {len(labels)} labeled track(s) in labels.json, "
              f"{n_labeled} matched to envelopes + real grids", flush=True)
    return _finish_scorecard(records, records, 0, {}, args)


def _load_labels() -> dict[str, dict]:
    """labels.json -> {content_id: track labels} for tracks with any content."""
    if not LABELS_PATH.exists():
        return {}
    raw = json.loads(LABELS_PATH.read_text())
    out = {}
    for cid, t in (raw.get("tracks") or {}).items():
        if t.get("wobble_moments") or t.get("wobble_spans") or t.get("vocal_free_windows"):
            out[str(cid)] = t
    return out


def _real_grids(content_ids: set[str]) -> dict[str, list[float]]:
    """Re-resolve true beatgrids for labeled tracks via the rekordbox DB +
    ANLZ reader (plain Python — no venv/torch). Fail soft: {} on DB trouble."""
    if not content_ids:
        return {}
    try:
        tracks = _enumerate_tracks()
    except Exception as exc:
        print(f"labels DISABLED: rekordbox DB unavailable ({exc})", flush=True)
        return {}
    out = {}
    for t in tracks:
        if t["content_id"] in content_ids:
            grid = _beatgrid_for(t["anlz_abs"])
            if grid:
                out[t["content_id"]] = grid
    return out


def _grid_from_env(env: dict) -> list[float]:
    # uniform grid reconstructed from n_beats (spacing irrelevant to --report
    # stats except wobble windowing, which uses beat indices, not ms).
    n = env.get("n_beats", 0)
    return [float(i * 500) for i in range(n)]


def _run_sweep(args) -> int:
    """Full-library envelope cache (on PASS). Separate every gridded track,
    skip existing envelopes, envelopes only (no scorecard). Progress /25."""
    if not _disk_ok(args.min_free_gb):
        print(f"ABORT: free disk {_free_gb():.1f} GB < floor {args.min_free_gb} GB", flush=True)
        return 3
    import torch  # type: ignore

    torch.set_num_threads(args.threads)
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    tracks = _enumerate_tracks()
    if args.limit:
        tracks = tracks[: args.limit]
    print(f"sweep scope: {len(tracks)} on-disk tracks", flush=True)
    model = _load_model()
    counts = {"ok": 0, "cached": 0, "no_grid": 0, "err": 0}
    started = time.perf_counter()
    for i, t in enumerate(tracks, 1):
        if not _disk_ok(args.min_free_gb):
            print(f"[STEMS-HB] sweep ABORT between tracks: free {_free_gb():.0f}GB < {args.min_free_gb}GB "
                  f"(resumable) {counts}", flush=True)
            break
        grid = _beatgrid_for(t["anlz_abs"])
        if grid is None:
            counts["no_grid"] += 1
        else:
            key = _cache_key(t["filepath"], grid)
            env_path = ENV_DIR / f"{key}.json" if key else None
            if env_path and env_path.exists():
                counts["cached"] += 1
            else:
                try:
                    env = _track_envelopes(t["filepath"], grid, model, args.segment)
                    env["content_id"] = t["content_id"]
                    env["title"] = t["title"]
                    env["elements"] = ["sweep"]
                    if env_path:
                        env_path.write_text(json.dumps(env))
                    counts["ok"] += 1
                except Exception as exc:
                    counts["err"] += 1
                    print(f"  SKIP {t['title'][:40]}: {exc}", flush=True)
        if i % 25 == 0 or i == len(tracks):
            el = (time.perf_counter() - started) / 60.0
            print(f"[STEMS-HB] sweep {i}/{len(tracks)} {counts} elapsed={el:.1f}m "
                  f"free={_free_gb():.0f}GB rss={_peak_rss_gb():.1f}GB", flush=True)
    n_env = len(list(ENV_DIR.glob("*.json")))
    size_mb = sum(f.stat().st_size for f in ENV_DIR.glob("*.json")) / 1e6
    print(json.dumps({"counts": counts, "envelopes": n_env, "cache_mb": round(size_mb, 1)}, indent=1), flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="STEMS PILOT runner (AWR-168)")
    p.add_argument("--dry-run", action="store_true", help="resolve corpus + print scope, no separation")
    p.add_argument("--limit", type=int, default=0, help="cap corpus to N tracks")
    p.add_argument("--report", action="store_true", help="recompute scorecard from existing envelopes")
    p.add_argument("--sweep", action="store_true", help="full-library envelope cache (on PASS)")
    p.add_argument("--snippets", action="store_true", help="(reserved) write A/B stem clips for flagged windows")
    p.add_argument("--min-free-gb", type=float, default=4.0, help="disk floor (abort below)")
    p.add_argument("--threads", type=int, default=4, help="torch.set_num_threads")
    p.add_argument("--segment", type=float, default=7.8, help="demucs segment seconds")
    args = p.parse_args()

    if args.dry_run:
        corpus, unresolved = _resolve_corpus(args.limit)
        print(f"pilot corpus: {len(corpus)} gridded tracks (target >= {MIN_CORPUS})")
        by_el: dict[str, int] = {}
        for t in corpus:
            for el in t["elements"]:
                by_el[el] = by_el.get(el, 0) + 1
        print(f"per-element track counts: {by_el}")
        print(f"unresolved/ambiguous anchors: {json.dumps(unresolved, indent=1)}")
        print(f"free disk: {_free_gb():.1f} GB (floor {args.min_free_gb})")
        for t in corpus:
            print(f"  {t['content_id']:>6}  {t['elements']}  {t['title'][:50]}")
        return 0
    if args.report:
        return _run_report(args)
    if args.sweep:
        return _run_sweep(args)
    return _run_pilot(args)


if __name__ == "__main__":
    raise SystemExit(main())
