#!/usr/bin/env python3
"""Offline evaluator for smart-drop v2 scoring."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
import math
import os
import random
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
    "kick_pattern_onset",
    "bass_pattern_onset",
    "low_mid_pattern_onset",
    "high_mid_pattern_onset",
    "phrase_energy_step",
    "spectral_balance_shift",
    "centroid_drop",
    "spectral_flux_onset",
    "silence_frame_pre",
    "buildup_sweep_slope",
    "amplitude_jump_at_c",
    "bass_sustain_1bar",
    "phrase_grid_alignment",
    "post_drop_kick_continuity",
    "post_drop_energy_stability",
    "post_drop_minus_pre_drop",
    "no_bigger_drop_later",
]

WIDE_WINDOW_ENV = "RBSS_DROP_WIDE_WINDOW"


@dataclass
class LabeledDrop:
    track_id: str
    split: str
    rekordbox_beat: int
    correct_beat: int
    heights: list[int]
    beatgrid_times_ms: list[float]
    spectral: Optional[SpectralFeatures]


@dataclass
class NnlsTuneResult:
    weights: dict[str, float]
    residual: float
    condition: float


@dataclass
class RankLossTuneResult:
    weights: dict[str, float]
    pairs: int
    final_loss: float
    zero_count: int


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
    evaluate.add_argument("--weights", help="Weight set for the v2 spectral variant: shipped, nnls, or JSON/YAML file")

    tune = sub.add_parser("tune", help="Fit nonnegative weights on the training split")
    tune.add_argument("--corpus", required=True)
    tune.add_argument("--objective", choices=["nnls", "rank_loss"], default=None)
    tune.add_argument("--ridge", type=float, default=0.01)
    tune.add_argument("--margin", type=float, default=0.1)
    tune.add_argument("--anchor-l2", type=float, default=1.0)
    tune.add_argument("--l1", type=float, default=0.01)
    tune.add_argument("--anchor", action="append", default=[])
    tune.add_argument("--seed", type=int, default=0)

    bootstrap = sub.add_parser("bootstrap-ci", help="Track-level bootstrap CI for frozen weights")
    bootstrap.add_argument("--corpus", required=True)
    bootstrap.add_argument("--weights", required=True)
    bootstrap.add_argument("--weights-b")
    bootstrap.add_argument("--split", choices=["holdout", "training", "all"], default="holdout")
    bootstrap.add_argument("--n-iter", type=int, default=1000)
    bootstrap.add_argument("--seed", type=int, default=0)
    bootstrap.add_argument("--metric", choices=["exact", "near"], default="exact")

    reshuffle = sub.add_parser("reshuffle", help="Random track-level split comparison for frozen weights")
    reshuffle.add_argument("--corpus", required=True)
    reshuffle.add_argument("--weights-a", required=True)
    reshuffle.add_argument("--weights-b", required=True)
    reshuffle.add_argument("--n-splits", type=int, default=10)
    reshuffle.add_argument("--holdout-frac", type=float, default=0.32)
    reshuffle.add_argument("--seed", type=int, default=0)
    reshuffle.add_argument("--retune-b", action="store_true")

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
    if args.mode == "bootstrap-ci":
        return _cmd_bootstrap_ci(args)
    if args.mode == "reshuffle":
        return _cmd_reshuffle(args)
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
    weights = None
    if args.weights:
        try:
            weights = _resolve_weight_spec(args.weights, rows)
        except ImportError:
            print('install with: pip install -e ".[analysis]"')
            return 1
        except ValueError as exc:
            print(str(exc))
            return 1

    variants = {
        "v1 (mean-lift)": _predict_v1,
        "v2 (waveform only)": _predict_v2_waveform,
        "v2 (waveform + spectral)": (
            _predict_v2_spectral
            if weights is None
            else lambda row: _predict_v2(row, row.spectral, weights)
        ),
    }
    print(_format_summary_table(rows, variants))
    print()
    print("Per-feature ablation on training (v2 full):")
    print(_format_ablation(rows, weights=weights))
    print()
    print(_format_per_track_holdout(rows, weights=weights))
    return 0


def _cmd_tune(args: argparse.Namespace) -> int:
    objective = args.objective or "nnls"
    if args.objective is None:
        print(
            "warning: tune currently defaults to --objective nnls; pass --objective rank_loss for the anchored tuner",
            file=sys.stderr,
        )
    try:
        import numpy as np  # type: ignore
        from scipy.optimize import minimize, nnls  # type: ignore
    except ImportError:
        print('install with: pip install -e ".[analysis]"')
        return 1

    rows = [row for row in _labeled_drops(_load_corpus(args.corpus)) if row.split == "training"]
    if not rows:
        print("No training labels found.")
        return 1

    if objective == "nnls":
        try:
            result = _fit_nnls_weights(rows, np, nnls, ridge=float(args.ridge))
        except ValueError as exc:
            print(str(exc))
            return 1
        named = result.weights
        _print_tuned_weights(named)
        zeroes = [name for name, value in named.items() if value <= 1e-9]
        if zeroes:
            print("warning: zero weights: " + ", ".join(zeroes))
        print(f"residual={result.residual:.6f}")
        print(f"condition number = {result.condition:.1f}")
        if result.condition > 100:
            print("warning: high condition number (multicollinearity)")
        print(_format_per_track_holdout(rows, weights=named))
        return 0

    try:
        anchors = _parse_anchors(args.anchor)
        result = _fit_rank_loss_weights(
            rows,
            np,
            minimize,
            margin=float(args.margin),
            anchor_l2=float(args.anchor_l2),
            l1=float(args.l1),
            anchors=anchors,
            seed=int(args.seed),
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    named = result.weights
    _print_tuned_weights(named)
    print(f"pairs={result.pairs}")
    print(f"final loss={result.final_loss:.6f}")
    print(f"zero-weight features={result.zero_count}")
    print(_format_per_track_holdout(rows, weights=named))
    return 0


def _cmd_bootstrap_ci(args: argparse.Namespace) -> int:
    rows = _labeled_drops(_load_corpus(args.corpus))
    if args.split != "all":
        sample_rows = [row for row in rows if row.split == args.split]
    else:
        sample_rows = rows
    if not sample_rows:
        print(f"No labeled drops found for split={args.split}.")
        return 1
    if args.n_iter <= 0:
        print("--n-iter must be positive")
        return 1
    try:
        weights_a = _resolve_weight_spec(args.weights, rows)
        weights_b = _resolve_weight_spec(args.weights_b, rows) if args.weights_b else None
    except ImportError:
        print('install with: pip install -e ".[analysis]"')
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1

    groups = _group_rows_by_track(sample_rows)
    track_ids = sorted(groups)
    counts_a = _track_metric_counts(sample_rows, weights_a)
    counts_b = _track_metric_counts(sample_rows, weights_b) if weights_b is not None else None
    rng = random.Random(int(args.seed))
    values_a: list[float] = []
    diffs: list[float] = []
    for _index in range(int(args.n_iter)):
        sampled = [rng.choice(track_ids) for _ in track_ids]
        score_a = _metric_from_track_counts(sampled, counts_a, args.metric)
        values_a.append(score_a)
        if counts_b is not None:
            score_b = _metric_from_track_counts(sampled, counts_b, args.metric)
            diffs.append(score_b - score_a)

    point = _metric_from_track_counts(track_ids, counts_a, args.metric)
    low, high = _percentile_interval(values_a)
    print(f"bootstrap-ci (track-level, n_iter={args.n_iter}, split={args.split}, metric={args.metric})")
    print(f"  point estimate: {_format_pct(point)}")
    print(f"  95% CI:         [{_format_pct(low)}, {_format_pct(high)}]")
    print(f"  mean:           {_format_pct(_mean(values_a))}")
    print(f"  std:            {_format_pp(_stddev(values_a), signed=False)}")
    print(f"  unique tracks:  {len(track_ids)}")
    if weights_b is not None:
        diff_low, diff_high = _percentile_interval(diffs)
        print(f"  paired diff (b - a) 95% CI: [{_format_pp(diff_low)}, {_format_pp(diff_high)}]")
        print(f"  paired diff mean:          {_format_pp(_mean(diffs))}")
    return 0


def _cmd_reshuffle(args: argparse.Namespace) -> int:
    if args.n_splits <= 0:
        print("--n-splits must be positive")
        return 1
    if not 0.0 < float(args.holdout_frac) < 1.0:
        print("--holdout-frac must be between 0 and 1")
        return 1
    rows = _labeled_drops(_load_corpus(args.corpus))
    groups = _group_rows_by_track(rows)
    track_ids = sorted(groups)
    if len(track_ids) < 2:
        print("reshuffle requires at least two tracks")
        return 1
    try:
        weights_a = _resolve_weight_spec(args.weights_a, rows)
        frozen_b = None if args.retune_b else _resolve_weight_spec(args.weights_b, rows)
    except ImportError:
        print('install with: pip install -e ".[analysis]"')
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1
    np = minimize = None
    if args.retune_b:
        try:
            import numpy as np  # type: ignore
            from scipy.optimize import minimize  # type: ignore
        except ImportError:
            print('install with: pip install -e ".[analysis]"')
            return 1

    rng = random.Random(int(args.seed))
    records: list[tuple[int, float, float, float]] = []
    track_scores_a = _track_metric_values(rows, weights_a, "exact")
    track_scores_b = None if args.retune_b else _track_metric_values(rows, frozen_b, "exact")
    holdout_count = max(1, min(len(track_ids) - 1, int(round(len(track_ids) * float(args.holdout_frac)))))
    for index in range(int(args.n_splits)):
        shuffled = list(track_ids)
        rng.shuffle(shuffled)
        holdout_ids = set(shuffled[:holdout_count])
        train_ids = set(shuffled[holdout_count:])
        holdout_rows = [row for track_id in sorted(holdout_ids) for row in groups[track_id]]
        if args.retune_b:
            train_rows = [row for track_id in sorted(train_ids) for row in groups[track_id]]
            try:
                weights_b = _fit_rank_loss_weights(
                    train_rows,
                    np,
                    minimize,
                    margin=0.1,
                    anchor_l2=1.0,
                    l1=0.01,
                    anchors={},
                    seed=int(args.seed) + index,
                ).weights
            except ValueError as exc:
                print(str(exc))
                return 1
        else:
            weights_b = frozen_b
        score_a = _mean([track_scores_a[track_id] for track_id in holdout_ids])
        score_b = (
            _per_track_metric_for_weights(holdout_rows, weights_b, "exact")
            if track_scores_b is None
            else _mean([track_scores_b[track_id] for track_id in holdout_ids])
        )
        records.append((index + 1, score_a, score_b, score_b - score_a))

    wins_a = [record for record in records if record[1] > record[2]]
    wins_b = [record for record in records if record[2] > record[1]]
    ties = [record for record in records if record[1] == record[2]]
    print(f"reshuffle (n_splits={args.n_splits}, holdout_frac={float(args.holdout_frac):.2f}, retune_b={bool(args.retune_b)})")
    print("  split  weights_a  weights_b  diff")
    for split, score_a, score_b, diff in records:
        print(f"  {split:>4}   {_format_pct(score_a):>8}  {_format_pct(score_b):>8}  {_format_pp(diff):>8}")
    print("  --")
    print(f"  weights_a wins: {len(wins_a)}/{len(records)} (avg {_format_pp(_mean([a - b for _i, a, b, _d in wins_a]))} when winning)")
    print(f"  weights_b wins: {len(wins_b)}/{len(records)} (avg {_format_pp(_mean([b - a for _i, a, b, _d in wins_b]))} when winning)")
    print(f"  ties:           {len(ties)}/{len(records)}")
    print(f"  mean diff:      {_format_pp(_mean([record[3] for record in records]))} (b - a)")
    return 0


def _print_tuned_weights(named: dict[str, float]) -> None:
    print("Tuned weights:")
    print("MULTI_FEATURE_WEIGHTS_V2 = {")
    for name in FEATURE_NAMES:
        print(f'    "{name}": {named[name]:.6f},')
    print("}")


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
                low_mid_envelope=tuple(
                    float(v) for v in _series_values(payload["low_mid_envelope"])
                ),
                high_mid_envelope=tuple(
                    float(v) for v in _series_values(payload["high_mid_envelope"])
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
    wide_window = os.environ.get(WIDE_WINDOW_ENV, "1") != "0"
    shadows = _calculate_smart_drop_energy_shadow(
        row.heights,
        _duration_from_beatgrid(row.beatgrid_times_ms),
        row.beatgrid_times_ms,
        [row.rekordbox_beat],
        scorer=_make_multi_feature_scorer(weights, wide_window=wide_window),
        spectral_features=spectral,
        wide_window=wide_window,
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


def _format_ablation(
    rows: list[LabeledDrop],
    *,
    weights: Optional[dict[str, float]] = None,
) -> str:
    training = [row for row in rows if row.split == "training"]
    if not training:
        return "  no training rows"
    base_weights = weights or MULTI_FEATURE_WEIGHTS_V2
    baseline, _near = _accuracy(
        training,
        lambda row: _predict_v2(row, row.spectral, base_weights),
    )
    lines = []
    for feature in FEATURE_NAMES:
        ablated = dict(base_weights)
        ablated[feature] = 0.0
        exact, _ = _accuracy(
            training,
            lambda row, weights=ablated: _predict_v2(row, row.spectral, weights),
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


def _fit_nnls_weights(rows: list[LabeledDrop], np: Any, nnls: Any, *, ridge: float) -> NnlsTuneResult:
    x, y = _training_matrix(rows, np)
    if x.size == 0:
        raise ValueError("No candidate rows available for tuning.")
    ridge = max(0.0, float(ridge))
    if ridge > 0.0:
        x = np.vstack([x, math.sqrt(ridge) * np.eye(x.shape[1])])
        y = np.concatenate([y, np.zeros(x.shape[1])])
    weights, residual = nnls(x, y)
    named = {name: float(weights[index]) for index, name in enumerate(FEATURE_NAMES)}
    return NnlsTuneResult(
        weights=named,
        residual=float(residual),
        condition=_condition_number(x, np),
    )


def _fit_rank_loss_weights(
    rows: list[LabeledDrop],
    np: Any,
    minimize: Any,
    *,
    margin: float,
    anchor_l2: float,
    l1: float,
    anchors: dict[str, float],
    seed: int,
) -> RankLossTuneResult:
    if margin < 0.0:
        raise ValueError("--margin must be non-negative")
    if anchor_l2 < 0.0:
        raise ValueError("--anchor-l2 must be non-negative")
    if l1 < 0.0:
        raise ValueError("--l1 must be non-negative")
    design = _rank_loss_design(rows, np)
    if design.size == 0:
        raise ValueError("No valid rank-loss pairs available for tuning.")
    pair_count = int(design.shape[0])
    # Keep CLI regularizer strengths aligned with the ad-hoc PR #88 tuner while
    # reporting the hinge term as an average over rank pairs.
    regularizer_scale = 1.0 / float(pair_count + len(rows))
    effective_anchor_l2 = anchor_l2 * regularizer_scale
    effective_l1 = l1 * regularizer_scale
    w0 = np.asarray([float(MULTI_FEATURE_WEIGHTS_V2.get(name, 0.0)) for name in FEATURE_NAMES], dtype=float)
    if not np.any(w0):
        rng = np.random.default_rng(int(seed))
        w0 = rng.uniform(0.0, 0.01, size=len(FEATURE_NAMES))
    anchor_indexes = [(FEATURE_NAMES.index(name), value) for name, value in anchors.items()]

    def objective(weights: Any) -> tuple[float, Any]:
        raw_margin = margin - design.dot(weights)
        active = raw_margin > 0.0
        active_margin = raw_margin[active]
        loss = float(np.sum(active_margin * active_margin) / pair_count) if active_margin.size else 0.0
        grad = np.zeros_like(weights)
        if active_margin.size:
            grad -= (2.0 / pair_count) * design[active].T.dot(active_margin)
        if effective_anchor_l2 > 0.0:
            for index, value in anchor_indexes:
                delta = float(weights[index]) - float(value)
                loss += effective_anchor_l2 * delta * delta
                grad[index] += 2.0 * effective_anchor_l2 * delta
        if effective_l1 > 0.0:
            loss += effective_l1 * float(np.sum(weights))
            grad += effective_l1
        return loss, grad

    result = minimize(
        objective,
        w0,
        method="L-BFGS-B",
        jac=True,
        bounds=[(0.0, None)] * len(FEATURE_NAMES),
        options={"maxiter": 1000},
    )
    weights = np.maximum(result.x, 0.0)
    final_loss, _grad = objective(weights)
    named = {name: float(weights[index]) for index, name in enumerate(FEATURE_NAMES)}
    zero_count = sum(1 for value in named.values() if value <= 1e-9)
    return RankLossTuneResult(
        weights=named,
        pairs=pair_count,
        final_loss=float(final_loss),
        zero_count=zero_count,
    )


def _rank_loss_design(rows: list[LabeledDrop], np: Any) -> Any:
    pairs: list[list[float]] = []
    for row in rows:
        start = row.rekordbox_beat
        end = row.rekordbox_beat + 8
        if row.correct_beat < start or row.correct_beat > end:
            continue
        if row.correct_beat < 0 or row.correct_beat >= len(row.beatgrid_times_ms):
            continue
        correct = _feature_vector(row, row.correct_beat)
        for beat in range(start, end + 1):
            if beat == row.correct_beat:
                continue
            if beat < 0 or beat >= len(row.beatgrid_times_ms):
                continue
            wrong = _feature_vector(row, beat)
            pairs.append([correct[index] - wrong[index] for index in range(len(FEATURE_NAMES))])
    return np.asarray(pairs, dtype=float)


def _feature_vector(row: LabeledDrop, beat: int) -> list[float]:
    features = _multi_feature_breakdown(
        beat,
        row.heights,
        row.beatgrid_times_ms,
        row.rekordbox_beat,
        row.spectral,
    )
    return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]


def _parse_anchors(items: Sequence[str]) -> dict[str, float]:
    anchors: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --anchor {item!r}; expected NAME=VALUE")
        name, value = item.split("=", 1)
        name = name.strip()
        if name not in FEATURE_NAMES:
            raise ValueError(f"unknown anchor feature: {name}")
        try:
            anchors[name] = float(value)
        except ValueError as exc:
            raise ValueError(f"invalid anchor value for {name}: {value}") from exc
    return anchors


def _resolve_weight_spec(spec: str, rows: list[LabeledDrop]) -> dict[str, float]:
    if spec == "shipped":
        return _complete_weights(dict(MULTI_FEATURE_WEIGHTS_V2), source="shipped", report_missing=False)
    if spec == "nnls":
        import numpy as np  # type: ignore
        from scipy.optimize import nnls  # type: ignore

        training = [row for row in rows if row.split == "training"]
        if not training:
            raise ValueError("No training labels found for nnls weights.")
        return _fit_nnls_weights(training, np, nnls, ridge=0.01).weights
    return _load_weights_file(spec)


def _load_weights_file(path: str) -> dict[str, float]:
    weight_path = Path(path).expanduser()
    text = weight_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = _parse_simple_weights_yaml(text)
    if not isinstance(payload, dict):
        raise ValueError(f"weights file must be a mapping: {path}")
    return _complete_weights(payload, source=str(weight_path), report_missing=True)


def _parse_simple_weights_yaml(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, value = _split_yaml_pair(line)
        if not key:
            continue
        payload[key.strip("\"'")] = _parse_scalar(value)
    return payload


def _complete_weights(payload: dict[str, Any], *, source: str, report_missing: bool) -> dict[str, float]:
    unknown = sorted(name for name in payload if name not in FEATURE_NAMES)
    if unknown:
        raise ValueError(f"weights file contains unknown features in {source}: {', '.join(unknown)}")
    missing = [name for name in FEATURE_NAMES if name not in payload]
    if missing and report_missing:
        print(
            "weights file missing features defaulted to 0.0: " + ", ".join(missing),
            file=sys.stderr,
        )
    weights: dict[str, float] = {}
    for name in FEATURE_NAMES:
        try:
            weights[name] = float(payload.get(name, 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"weights file has non-numeric value for {name}") from exc
    return weights


def _group_rows_by_track(rows: list[LabeledDrop]) -> dict[str, list[LabeledDrop]]:
    groups: dict[str, list[LabeledDrop]] = {}
    for row in rows:
        groups.setdefault(row.track_id, []).append(row)
    return groups


def _track_metric_counts(
    rows: list[LabeledDrop],
    weights: dict[str, float],
) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        predicted = _predict_v2(row, row.spectral, weights)
        item = counts.setdefault(row.track_id, {"exact": 0, "near": 0, "total": 0})
        item["total"] += 1
        if predicted == row.correct_beat:
            item["exact"] += 1
        if predicted is not None and abs(predicted - row.correct_beat) <= 1:
            item["near"] += 1
    return counts


def _metric_from_track_counts(
    track_ids: Sequence[str],
    counts: dict[str, dict[str, int]],
    metric: str,
) -> float:
    total = sum(counts[track_id]["total"] for track_id in track_ids)
    if total <= 0:
        return 0.0
    correct = sum(counts[track_id][metric] for track_id in track_ids)
    return correct / total


def _metric_for_weights(rows: list[LabeledDrop], weights: dict[str, float], metric: str) -> float:
    exact, near = _accuracy(rows, lambda row: _predict_v2(row, row.spectral, weights))
    return exact if metric == "exact" else near


def _track_metric_values(
    rows: list[LabeledDrop],
    weights: dict[str, float],
    metric: str,
) -> dict[str, float]:
    groups = _group_rows_by_track(rows)
    return {
        track_id: _metric_for_weights(track_rows, weights, metric)
        for track_id, track_rows in groups.items()
    }


def _per_track_metric_for_weights(rows: list[LabeledDrop], weights: dict[str, float], metric: str) -> float:
    groups = _group_rows_by_track(rows)
    if not groups:
        return 0.0
    return _mean([_metric_for_weights(group_rows, weights, metric) for group_rows in groups.values()])


def _percentile_interval(values: list[float]) -> tuple[float, float]:
    return _percentile(values, 0.025), _percentile(values, 0.975)


def _percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percent
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return float(ordered[lower])
    fraction = rank - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _format_pct(value: float) -> str:
    return f"{value * 100.0:.1f}%"


def _format_pp(value: float, *, signed: bool = True) -> str:
    sign = "+" if signed else ""
    return f"{value * 100.0:{sign}.1f}pp"


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
