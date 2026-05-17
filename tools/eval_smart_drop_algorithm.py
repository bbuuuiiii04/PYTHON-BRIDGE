#!/usr/bin/env python3
"""Offline evaluator for smart-drop v2 scoring."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
import math
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

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

    args = parser.parse_args(argv)
    if args.mode == "scaffold":
        return _cmd_scaffold(args)
    if args.mode == "evaluate":
        return _cmd_evaluate(args)
    if args.mode == "tune":
        return _cmd_tune(args)
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


if __name__ == "__main__":
    raise SystemExit(main())
