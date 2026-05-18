#!/usr/bin/env python3
"""Offline evaluator for smart-drop v2 scoring."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional, Sequence
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.anlz_reader import (  # noqa: E402
    MULTI_FEATURE_WEIGHTS_V2,
    _calculate_smart_drop_energy_shadow,
    _duration_from_beatgrid,
    _make_multi_feature_scorer,
    _multi_feature_breakdown,
    read_anlz_drops,
)
from rb_ss_bridge_v2.audio_spectral_features import (  # noqa: E402
    SCHEMA_VERSION,
    SpectralFeatures,
    extract_spectral_features,
)
from rb_ss_bridge_v2 import spectral_cache  # noqa: E402


FEATURE_NAMES = [
    "onset_score",
    "broad_onset_score",
    "post_lift",
    "pre_valley_depth",
    "downbeat_alignment",
    "distance_penalty",
    "sub_bass_onset",
    "kick_attack",
    "pre_drop_filter_sweep",
]


@dataclass
class LabeledDrop:
    track_id: str
    split: str
    rekordbox_beat: int
    correct_beat: int
    heights: list[int]
    beatgrid_times_ms: list[float]
    spectral: Optional[SpectralFeatures]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate smart-drop v2 scoring offline.")
    sub = parser.add_subparsers(dest="mode", required=True)

    scaffold = sub.add_parser("scaffold", help="Dump Rekordbox drop rows for labeling")
    scaffold.add_argument("--anlz", required=True)
    scaffold.add_argument("--audio", required=True)
    scaffold.add_argument("--title", required=True)
    scaffold.add_argument("--split", choices=["training", "holdout"], required=True)

    evaluate = sub.add_parser("evaluate", help="Evaluate v1/v2 variants against a corpus")
    evaluate.add_argument("--corpus", required=True)

    tune = sub.add_parser("tune", help="Fit nonnegative weights on the training split")
    tune.add_argument("--corpus", required=True)
    tune.add_argument("--ridge", type=float, default=0.01)

    label = sub.add_parser("label-from-cues", help="Auto-build a corpus YAML from Rekordbox DROP-commented cues.")
    label.add_argument("--cue-comment", default="DROP", help="Cue comment substring (case-insensitive) marking the real drop.")
    label.add_argument("--tracks", help="Optional newline-delimited file of titles to restrict the scan to.")
    label.add_argument("--exclude-scripted", default="~/TimecodeLink/playlist.yaml", help="TL playlist.yaml whose tracks are excluded as scripted. Empty string disables.")
    label.add_argument("--split", choices=["training", "holdout"], default="training", help="Split assigned to every emitted track.")
    label.add_argument("--holdout-titles", help="Optional file: titles listed here override --split to 'holdout'.")
    label.add_argument("--cue-window-beats", type=int, default=8, help="Max beat distance from RB drop for a cue to count as the same drop.")
    label.add_argument("--output", help="Output corpus YAML path. Default: stdout.")

    args = parser.parse_args(argv)
    if args.mode == "scaffold":
        return _cmd_scaffold(args)
    if args.mode == "evaluate":
        return _cmd_evaluate(args)
    if args.mode == "tune":
        return _cmd_tune(args)
    if args.mode == "label-from-cues":
        return _cmd_label_from_cues(args)
    return 2


def _cmd_scaffold(args: argparse.Namespace) -> int:
    data = read_anlz_drops(args.anlz)
    print(f"- anlz_path: {_yaml_scalar(args.anlz)}")
    print(f"  audio_path: {_yaml_scalar(args.audio)}")
    print(f"  title: {_yaml_scalar(args.title)}")
    print(f"  split: {args.split}")
    print("  drops:")
    for beat in data.drop_beat_indices:
        elapsed = ""
        ctx = data.waveform_context
        if ctx is not None and 0 <= beat < len(ctx.beatgrid_times_ms):
            elapsed = _format_elapsed(int(round(ctx.beatgrid_times_ms[beat])))
        print(f"    - rekordbox_beat: {beat}")
        print(f"      rekordbox_elapsed: {_yaml_scalar(elapsed)}")
        print("      correct_beat: null")
        print("      correct_elapsed: null")
        print('      notes: ""')
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    rows = _labeled_drops(_load_corpus(args.corpus))
    if not rows:
        print("No labeled drops found.")
        return 1

    variants = {
        "v1 (mean-lift)": _predict_v1,
        "v2 (waveform only)": _predict_v2_waveform,
        "v2 (waveform + spectral)": _predict_v2_spectral,
    }
    print(_format_summary_table(rows, variants))
    print()
    print("Per-feature ablation on training (v2 full):")
    print(_format_ablation(rows))
    print()
    print(_format_per_track_holdout(rows))
    return 0


def _cmd_tune(args: argparse.Namespace) -> int:
    try:
        import numpy as np  # type: ignore
        from scipy.optimize import nnls  # type: ignore
    except ImportError:
        print('install with: pip install -e ".[analysis]"')
        return 1

    rows = [row for row in _labeled_drops(_load_corpus(args.corpus)) if row.split == "training"]
    if not rows:
        print("No training labels found.")
        return 1

    x, y = _training_matrix(rows, np)
    if x.size == 0:
        print("No candidate rows available for tuning.")
        return 1
    ridge = max(0.0, float(args.ridge))
    if ridge > 0.0:
        x = np.vstack([x, math.sqrt(ridge) * np.eye(x.shape[1])])
        y = np.concatenate([y, np.zeros(x.shape[1])])

    weights, residual = nnls(x, y)
    named = {name: float(weights[index]) for index, name in enumerate(FEATURE_NAMES)}
    print("Tuned weights:")
    print("MULTI_FEATURE_WEIGHTS_V2 = {")
    for name in FEATURE_NAMES:
        print(f'    "{name}": {named[name]:.6f},')
    print("}")
    zeroes = [name for name, value in named.items() if value <= 1e-9]
    if zeroes:
        print("warning: zero weights: " + ", ".join(zeroes))
    condition = _condition_number(x, np)
    print(f"residual={residual:.6f}")
    print(f"condition number = {condition:.1f}")
    if condition > 100:
        print("warning: high condition number (multicollinearity)")
    print(_format_per_track_holdout(rows, weights=named))
    return 0


def _cmd_label_from_cues(args: argparse.Namespace) -> int:
    db = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
        db = Rekordbox6Database(os.path.expanduser("~/Library/Pioneer/rekordbox/master.db"), unlock=True)
        all_content = list(db.get_content())
        scripted, restrict = _load_scripted_titles(args.exclude_scripted), _title_lines(args.tracks)
        candidates = [c for c in all_content if not restrict or _matches_any(c, restrict)]
        kept = [c for c in candidates if not _matches_any(c, scripted)]
        excluded = len(candidates) - len(kept)
        print(f"[label] excluded {excluded} scripted tracks", file=sys.stderr)
        tracks, stats, manual, orphans = _label_tracks(
            kept, db, args.cue_comment.lower(), args, _title_lines(args.holdout_titles)
        )
    except Exception as exc:
        print(f"[label] RB scan failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if db is not None:
            try: db.close()
            except Exception: pass

    text = _format_labeled_tracks(tracks)
    if args.output:
        out = Path(args.output).expanduser(); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    _label_summary(len(all_content), excluded, stats, manual, orphans, args)
    return 0


def _label_tracks(candidates: list[Any], db: Any, needle: str, args: argparse.Namespace,
                  holdouts: list[str]) -> tuple[list[dict[str, Any]], dict[str, int], list[str], list[str]]:
    stats = {k: 0 for k in ("marked", "auto", "nowave", "manual", "orphan", "errors")}
    tracks: list[dict[str, Any]] = []; manual: list[str] = []; orphans: list[str] = []
    for content in candidates:
        title = _content_title(content)
        try:
            anlz_path = _first_dat(db.get_anlz_paths(content))
            if not anlz_path:
                continue
            cues = _extract_cues_from_db(db, content)
            drop_cues = [(i, c) for i, c in enumerate(cues) if needle in c["text"].lower()]
            if not drop_cues:
                continue
            stats["marked"] += 1
            data = read_anlz_drops(anlz_path); ctx = data.waveform_context
        except Exception as exc:
            stats["errors"] += 1
            print(f"[label] skipped {title}: {exc}", file=sys.stderr)
            continue
        if ctx is None or len(ctx.beatgrid_times_ms) < 2:
            stats["nowave"] += 1; continue
        beatgrid = list(ctx.beatgrid_times_ms); window_ms = abs(args.cue_window_beats * (beatgrid[1] - beatgrid[0]))
        rows: list[dict[str, Any]] = []; matched: set[int] = set()
        for rb_beat in data.drop_beat_indices:
            rb_ms = beatgrid[rb_beat] if 0 <= rb_beat < len(beatgrid) else None
            drops_near = [] if rb_ms is None else [(i, c) for i, c in drop_cues if abs(c["ms"] - rb_ms) <= window_ms]
            row = {"rekordbox_beat": rb_beat, "rekordbox_elapsed": _format_elapsed(int(round(rb_ms or 0)))}
            if drops_near:
                i, cue = min(drops_near, key=lambda item: abs(item[1]["ms"] - (rb_ms or 0)))
                matched.add(i)
                correct = _nearest_beat(cue["ms"], beatgrid); delta = correct - rb_beat
                stats["auto"] += 1
                row.update({"correct_beat": correct, "correct_elapsed": _format_elapsed(int(round(beatgrid[correct]))), "notes": f"auto from cue '{cue['text']}' @{_format_elapsed(cue['ms'])} (delta={delta:+d} beats)"})
            else:
                stats["manual"] += 1
                row.update({"correct_beat": None, "correct_elapsed": None, "notes": f"no DROP cue within +/-{args.cue_window_beats} beats - manual fill"})
                manual.append(f'{_yaml_scalar(title)} beat {rb_beat}: {row["notes"]}')
            rows.append(row)
        for i, cue in drop_cues:
            if i in matched:
                continue
            cue_beat = _nearest_beat(cue["ms"], beatgrid)
            if any(abs(cue["ms"] - beatgrid[b]) <= window_ms for b in data.drop_beat_indices if 0 <= b < len(beatgrid)):
                continue
            stats["orphan"] += 1
            rows.append({"rekordbox_beat": None, "rekordbox_elapsed": None, "correct_beat": cue_beat, "correct_elapsed": _format_elapsed(int(round(beatgrid[cue_beat]))),
                         "notes": "user-marked drop with no RB candidate; v1 cannot predict, v2 can score only if seeded"})
            orphans.append(f'{_yaml_scalar(title)} cue@beat {cue_beat}: user-marked but no RB drop candidate')
        tracks.append({"anlz_path": anlz_path, "audio_path": content.FolderPath or "", "title": title, "split": "holdout" if _matches_title(title, holdouts) else args.split, "drops": rows})
    return tracks, stats, manual, orphans


def _extract_cues_from_db(db: Any, content: Any) -> list[dict[str, Any]]:
    try:
        rows = db.get_cue(ContentID=content.ID)
    except TypeError:
        rows = [c for c in db.get_cue() if getattr(c, "ContentID", None) == content.ID]
    cues: list[dict[str, Any]] = []
    for row in rows:
        in_msec = getattr(row, "InMsec", None)
        if in_msec is None or in_msec < 0:
            continue
        cues.append({"ms": int(in_msec),
                     "text": str(getattr(row, "Comment", "") or ""),
                     "hot": 1 if getattr(row, "is_hot_cue", False) else 0})
    return cues


def _extract_cues(anlz: Any) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for tag_type in ("PCO2", "PCOB"):
        for tag in anlz.getall_tags(tag_type):
            content = getattr(tag, "content", None)
            entries = getattr(content, "entries", None) if not isinstance(content, dict) else content.get("entries")
            for entry in entries or []:
                time_ms = getattr(entry, "time", None)
                if time_ms is None:
                    continue
                cues.append({"ms": int(time_ms), "text": "" if tag_type == "PCOB" else str(getattr(entry, "comment", "") or ""), "hot": int(getattr(entry, "hot_cue", 0) or 0)})
    return cues


def _format_labeled_tracks(tracks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for track in tracks:
        lines += [f"- anlz_path: {_yaml_scalar(track['anlz_path'])}", f"  audio_path: {_yaml_scalar(track['audio_path'])}",
                  f"  title: {_yaml_scalar(track['title'])}", f"  split: {track['split']}", "  drops:"]
        for drop in track["drops"]:
            for prefix, key in (("    - ", "rekordbox_beat"), ("      ", "rekordbox_elapsed"),
                                ("      ", "correct_beat"), ("      ", "correct_elapsed")):
                lines.append(f"{prefix}{key}: {_yaml_value(drop[key])}")
            lines.append(f"      notes: {_yaml_scalar(drop['notes'])}")
    return "\n".join(lines) + ("\n" if lines else "")


def _load_scripted_titles(path: str) -> list[str]:
    if not path:
        return []
    p = Path(path).expanduser()
    if not p.exists():
        print(f"[label] warning: scripted playlist missing: {p}", file=sys.stderr)
        return []
    try:
        titles: list[str] = []; cur: Optional[str] = None; saw_bridge = False
        for raw in p.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if "track_id:" in s:
                cur = s.split("track_id:", 1)[1].strip().strip("\"'")
                saw_bridge = False
            elif "address:" in s and "/bridge/track_loaded" in s:
                saw_bridge = True
            elif s.startswith("value:") and saw_bridge and cur:
                try:
                    if int(float(s[len("value:"):].strip())) >= 2:
                        titles.append(cur)
                except ValueError:
                    pass
                saw_bridge = False
        return titles
    except Exception as exc:
        print(f"[label] warning: scripted playlist unreadable: {exc}", file=sys.stderr)
        return []


def _title_lines(path: Optional[str]) -> list[str]:
    return [] if not path else [line.strip() for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines() if line.strip()]


def _matches_any(content: Any, titles: Sequence[str]) -> bool:
    fp, title = str(getattr(content, "FolderPath", "") or ""), str(getattr(content, "Title", "") or "")
    return any(_matches_title(fp, [item]) or _matches_title(title, [item]) for item in titles)


def _matches_title(text: str, titles: Sequence[str]) -> bool:
    lower = text.lower()
    return any(title.lower() in lower or ((words := [w.lower() for w in re.split(r"[\s()\[\]\-]+", title) if w]) and all(w in lower for w in words)) for title in titles)


def _first_dat(paths: Any) -> Optional[str]:
    if isinstance(paths, dict):
        dat = paths.get("DAT")
        return str(dat) if dat is not None else None
    return next((str(path) for path in paths or [] if str(path).upper().endswith(".DAT")), None)


def _content_title(content: Any) -> str:
    return str(getattr(content, "Title", "") or Path(str(content.FolderPath or "")).stem)


def _label_summary(scanned: int, excluded: int, stats: dict[str, int],
                   manual: list[str], orphans: list[str], args: argparse.Namespace) -> None:
    lines = [f"scanned {scanned} RB tracks", f"excluded {excluded} scripted tracks",
             f"{stats['marked']} tracks had a '{args.cue_comment}'-commented cue",
             f"  auto-labeled drops: {stats['auto']}", f"  skipped (no waveform): {stats['nowave']}",
             f"  manual review (no cue near RB drop): {stats['manual']}", f"  orphan cues (no RB drop near cue): {stats['orphan']}",
             f"  errors (per-track exceptions): {stats['errors']}"]
    if manual:
        lines += ["", "manual review needed:"] + [f"  - {item}" for item in manual]
    if orphans:
        lines += ["", "orphan cues:"] + [f"  - {item}" for item in orphans]
    for line in lines:
        print(f"[label] {line}".rstrip(), file=sys.stderr)


def _load_corpus(path: str) -> list[dict[str, Any]]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    json_text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        payload = _parse_simple_yaml_corpus(text)
    if isinstance(payload, dict) and isinstance(payload.get("tracks"), list):
        payload = payload["tracks"]
    if not isinstance(payload, list):
        raise ValueError(f"corpus must be a list: {path}")
    return [dict(item) for item in payload if isinstance(item, dict)]


def _parse_simple_yaml_corpus(text: str) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    current_drop: Optional[dict[str, Any]] = None
    in_drops = False

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.startswith("- "):
            current = {}
            tracks.append(current)
            current_drop = None
            in_drops = False
            rest = line[2:].strip()
            if rest:
                key, value = _split_yaml_pair(rest)
                current[key] = _parse_scalar(value)
            continue
        if current is None:
            continue
        if indent == 2:
            key, value = _split_yaml_pair(line)
            if key == "drops":
                current["drops"] = []
                in_drops = True
            else:
                current[key] = _parse_scalar(value)
            continue
        if in_drops and indent == 4 and line.startswith("- "):
            current_drop = {}
            current.setdefault("drops", []).append(current_drop)
            rest = line[2:].strip()
            if rest:
                key, value = _split_yaml_pair(rest)
                current_drop[key] = _parse_scalar(value)
            continue
        if in_drops and indent == 6 and current_drop is not None:
            key, value = _split_yaml_pair(line)
            current_drop[key] = _parse_scalar(value)
    return tracks


def _split_yaml_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line, ""
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(value: str) -> Any:
    if value in ("", "null", "None", "~"):
        return None
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value.startswith(('"', "'")):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value.strip('"\'')
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _labeled_drops(tracks: list[dict[str, Any]]) -> list[LabeledDrop]:
    rows: list[LabeledDrop] = []
    for index, track in enumerate(tracks):
        split = str(track.get("split", "training") or "training")
        track_id = str(track.get("track_id") or track.get("title") or index)
        heights, beatgrid = _track_waveform_context(track)
        if not heights or len(beatgrid) < 8:
            continue
        spectral = _track_spectral_features(track, beatgrid)
        for drop in track.get("drops", []):
            if not isinstance(drop, dict):
                continue
            correct = _drop_correct_beat(drop, beatgrid)
            if correct is None:
                continue
            rows.append(LabeledDrop(
                track_id=track_id,
                split=split,
                rekordbox_beat=int(drop.get("rekordbox_beat", correct)),
                correct_beat=correct,
                heights=heights,
                beatgrid_times_ms=beatgrid,
                spectral=spectral,
            ))
    return rows


def _track_waveform_context(track: dict[str, Any]) -> tuple[list[int], list[float]]:
    if "waveform_values" in track and "beatgrid_times_ms" in track:
        return (
            [int(value) for value in _series_values(track.get("waveform_values", []))],
            _beatgrid_values(track.get("beatgrid_times_ms", [])),
        )

    anlz_path = str(track.get("anlz_path", "") or "")
    if not anlz_path:
        return [], []
    data = read_anlz_drops(anlz_path)
    ctx = data.waveform_context
    if ctx is None:
        return [], []
    return list(ctx.heights), list(ctx.beatgrid_times_ms)


def _track_spectral_features(
    track: dict[str, Any],
    beatgrid_times_ms: Sequence[float],
) -> Optional[SpectralFeatures]:
    payload = track.get("spectral_features")
    if isinstance(payload, dict):
        try:
            return SpectralFeatures(
                sr=int(payload.get("sr", 22050)),
                schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
                sub_bass_envelope=tuple(
                    float(v) for v in _series_values(payload["sub_bass_envelope"])
                ),
                kick_envelope=tuple(
                    float(v) for v in _series_values(payload["kick_envelope"])
                ),
                high_band_envelope=tuple(
                    float(v) for v in _series_values(payload["high_band_envelope"])
                ),
            )
        except Exception:
            return None

    audio_path = str(track.get("audio_path", "") or "")
    if not audio_path:
        return None
    cached = spectral_cache.get_cached(audio_path, beatgrid_times_ms)
    if cached is not None:
        return cached
    features = extract_spectral_features(audio_path, beatgrid_times_ms)
    if features is not None:
        spectral_cache.put_cached(audio_path, beatgrid_times_ms, features)
    return features


def _series_values(value: Any) -> list[float]:
    if isinstance(value, dict):
        length = int(value.get("length", 0) or 0)
        default = float(value.get("default", 0.0) or 0.0)
        values = [default for _ in range(length)]
        for item in value.get("ranges", []):
            if not isinstance(item, list) or len(item) != 3:
                continue
            start, end, item_value = int(item[0]), int(item[1]), float(item[2])
            for index in range(max(0, start), min(length, end)):
                values[index] = item_value
        for item in value.get("points", []):
            if not isinstance(item, list) or len(item) != 2:
                continue
            index, item_value = int(item[0]), float(item[1])
            if 0 <= index < length:
                values[index] = item_value
        return values
    return [float(item) for item in value or []]


def _beatgrid_values(value: Any) -> list[float]:
    if isinstance(value, dict):
        count = int(value.get("count", 0) or 0)
        start_ms = float(value.get("start_ms", 0.0) or 0.0)
        step_ms = float(value.get("step_ms", 500.0) or 500.0)
        return [start_ms + index * step_ms for index in range(count)]
    return [float(item) for item in value or []]


def _drop_correct_beat(drop: dict[str, Any], beatgrid_times_ms: Sequence[float]) -> Optional[int]:
    if drop.get("correct_beat") is not None:
        return int(drop["correct_beat"])
    if drop.get("correct_elapsed") is not None:
        elapsed_ms = _parse_elapsed_ms(str(drop["correct_elapsed"]))
        if elapsed_ms is None:
            return None
        return _nearest_beat(elapsed_ms, beatgrid_times_ms)
    return None


def _predict_v1(row: LabeledDrop) -> Optional[int]:
    shadows = _calculate_smart_drop_energy_shadow(
        row.heights,
        _duration_from_beatgrid(row.beatgrid_times_ms),
        row.beatgrid_times_ms,
        [row.rekordbox_beat],
    )
    return shadows[0].suggested_beat if shadows else None


def _predict_v2_waveform(row: LabeledDrop) -> Optional[int]:
    return _predict_v2(row, None, MULTI_FEATURE_WEIGHTS_V2)


def _predict_v2_spectral(row: LabeledDrop) -> Optional[int]:
    return _predict_v2(row, row.spectral, MULTI_FEATURE_WEIGHTS_V2)


def _predict_v2(
    row: LabeledDrop,
    spectral: Optional[SpectralFeatures],
    weights: dict[str, float],
) -> Optional[int]:
    shadows = _calculate_smart_drop_energy_shadow(
        row.heights,
        _duration_from_beatgrid(row.beatgrid_times_ms),
        row.beatgrid_times_ms,
        [row.rekordbox_beat],
        scorer=_make_multi_feature_scorer(weights),
        spectral_features=spectral,
    )
    return shadows[0].suggested_beat if shadows else None


def _format_summary_table(
    rows: list[LabeledDrop],
    variants: dict[str, Any],
) -> str:
    splits = ["training", "holdout"]
    header = "                              training              holdout\n"
    header += "                              exact  +/-1           exact  +/-1"
    lines = [header]
    for name, predictor in variants.items():
        parts = [f"{name:<30}"]
        for split in splits:
            subset = [row for row in rows if row.split == split]
            exact, near = _accuracy(subset, predictor)
            parts.append(f"{exact:>5.0%}  {near:>5.0%}")
        lines.append("  ".join(parts))
    return "\n".join(lines)


def _format_ablation(rows: list[LabeledDrop]) -> str:
    training = [row for row in rows if row.split == "training"]
    if not training:
        return "  no training rows"
    baseline, _near = _accuracy(training, _predict_v2_spectral)
    lines = []
    for feature in FEATURE_NAMES:
        weights = dict(MULTI_FEATURE_WEIGHTS_V2)
        weights[feature] = 0.0
        exact, _ = _accuracy(
            training,
            lambda row, weights=weights: _predict_v2(row, row.spectral, weights),
        )
        delta = int(round((exact - baseline) * 100))
        lines.append(f"  -{feature:<24} -> {exact:.0%} ({delta:+d} pp)")
    return "\n".join(lines)


def _format_per_track_holdout(
    rows: list[LabeledDrop],
    *,
    weights: Optional[dict[str, float]] = None,
) -> str:
    training = [row for row in rows if row.split == "training"]
    groups = sorted(set(row.track_id for row in training))
    if len(groups) < 2:
        return "Per-track holdout: insufficient groups"
    folds = min(5, len(groups))
    prefix = "Per-track holdout (no refit)"
    if len(groups) < 5:
        prefix = f"Per-track holdout (no refit): {folds} groups"

    fold_scores: list[float] = []
    for fold in range(folds):
        holdout_groups = {group for index, group in enumerate(groups) if index % folds == fold}
        fold_rows = [row for row in training if row.track_id in holdout_groups]
        if not fold_rows:
            continue
        exact, _ = _accuracy(
            fold_rows,
            lambda row: _predict_v2(row, row.spectral, weights or MULTI_FEATURE_WEIGHTS_V2),
        )
        fold_scores.append(exact)
    mean = sum(fold_scores) / len(fold_scores) if fold_scores else 0.0
    return f"{prefix}: mean per-track exact={mean:.0%} groups={len(fold_scores)}"


def _accuracy(rows: list[LabeledDrop], predictor: Any) -> tuple[float, float]:
    if not rows:
        return 0.0, 0.0
    exact = 0
    near = 0
    for row in rows:
        predicted = predictor(row)
        if predicted == row.correct_beat:
            exact += 1
        if predicted is not None and abs(predicted - row.correct_beat) <= 1:
            near += 1
    return exact / len(rows), near / len(rows)


def _training_matrix(rows: list[LabeledDrop], np: Any) -> tuple[Any, Any]:
    x_rows: list[list[float]] = []
    y_rows: list[float] = []
    for row in rows:
        for beat in range(row.rekordbox_beat, row.rekordbox_beat + 9):
            if beat < 0 or beat >= len(row.beatgrid_times_ms):
                continue
            features = _multi_feature_breakdown(
                beat,
                row.heights,
                row.beatgrid_times_ms,
                row.rekordbox_beat,
                row.spectral,
            )
            x_rows.append([features.get(name, 0.0) for name in FEATURE_NAMES])
            y_rows.append(1.0 if beat == row.correct_beat else 0.0)
    return np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float)


def _condition_number(matrix: Any, np: Any) -> float:
    try:
        return float(np.linalg.cond(matrix))
    except Exception:
        return float("inf")


def _format_elapsed(elapsed_ms: int) -> str:
    minutes, millis = divmod(max(0, int(elapsed_ms)), 60_000)
    seconds, millis = divmod(millis, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _parse_elapsed_ms(value: str) -> Optional[int]:
    try:
        minutes, rest = value.split(":", 1)
        seconds = float(rest)
        return int(round((int(minutes) * 60.0 + seconds) * 1000.0))
    except Exception:
        return None


def _nearest_beat(elapsed_ms: int, beatgrid_times_ms: Sequence[float]) -> int:
    return min(
        range(len(beatgrid_times_ms)),
        key=lambda beat: abs(float(beatgrid_times_ms[beat]) - elapsed_ms),
    )


def _yaml_scalar(value: str) -> str:
    return json.dumps(value)


def _yaml_value(value: Any) -> str:
    return "null" if value is None else (_yaml_scalar(value) if isinstance(value, str) else str(value))


if __name__ == "__main__":
    raise SystemExit(main())
