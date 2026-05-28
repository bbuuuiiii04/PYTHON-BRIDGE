#!/usr/bin/env python3
"""Summarize Smart Drop telemetry CSV rows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Smart Drop telemetry CSV rows.")
    parser.add_argument("--csv", required=True, help="Path to smart_drop_telemetry.csv")
    parser.add_argument("--since", help="Include rows at or after YYYY-MM-DD or ISO timestamp")
    args = parser.parse_args(argv)

    telemetry_path = Path(args.csv).expanduser()
    rows = _load_rows(telemetry_path, since=_parse_since(args.since))
    _print_summary(telemetry_path, rows)
    return 0


def _parse_since(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _load_rows(path: Path, *, since: Optional[float] = None) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if since is None:
        return rows
    return [
        row for row in rows
        if _float_or_none(row.get("created_at", "")) is not None
        and _float_or_none(row.get("created_at", "")) >= since
    ]


def _print_summary(path: Path, rows: list[dict[str, str]]) -> None:
    labeled = [row for row in rows if _int_or_none(row.get("correct_beat", "")) is not None]
    print("Smart Drop telemetry summary")
    print(f"csv: {path}")
    print(f"decisions: {len(rows)}")
    print(f"labeled: {len(labeled)}")
    if not rows:
        return

    exact = 0
    within_one = 0
    correct_scores: list[float] = []
    delta_histogram: Counter[int] = Counter()
    source_counts: Counter[str] = Counter()
    source_labeled: Counter[str] = Counter()
    feature_totals: defaultdict[str, float] = defaultdict(float)
    feature_counts: Counter[str] = Counter()

    for row in rows:
        source = row.get("source", "") or "unknown"
        source_counts[source] += 1
        anlz_beat = _int_or_none(row.get("anlz_beat", ""))
        suggested_beat = _int_or_none(row.get("suggested_beat", ""))
        correct_beat = _int_or_none(row.get("correct_beat", ""))
        if anlz_beat is not None and suggested_beat is not None:
            delta_histogram[suggested_beat - anlz_beat] += 1
        if correct_beat is not None and suggested_beat is not None:
            source_labeled[source] += 1
            exact += int(suggested_beat == correct_beat)
            within_one += int(abs(suggested_beat - correct_beat) <= 1)
            score = _score_for_candidate(row.get("top_candidates_json", ""), correct_beat)
            if score is not None:
                correct_scores.append(score)
        for name, value in _json_object(row.get("feature_breakdown_json", "")).items():
            number = _float_or_none(value)
            if number is not None:
                feature_totals[name] += number
                feature_counts[name] += 1

    print("sources:")
    for source in sorted(source_counts):
        print(f"  {source}: {source_counts[source]} decisions, {source_labeled[source]} labeled")

    print("suggested_minus_anlz_histogram:")
    for delta in sorted(delta_histogram):
        print(f"  {delta:+d}: {delta_histogram[delta]}")

    if labeled:
        print(f"labeled_exact: {exact}/{len(labeled)}")
        print(f"labeled_within_1: {within_one}/{len(labeled)}")
    if correct_scores:
        print(
            "mean_score_at_correct_candidate: "
            f"{sum(correct_scores) / len(correct_scores):.6f} ({len(correct_scores)} rows)"
        )

    if feature_counts:
        print("mean_feature_at_suggested:")
        for name in sorted(feature_counts):
            print(f"  {name}: {feature_totals[name] / feature_counts[name]:.6f}")


def _score_for_candidate(raw: str, beat: int) -> Optional[float]:
    data = _json_array(raw)
    for item in data:
        if not isinstance(item, dict):
            continue
        if _int_or_none(item.get("beat")) == beat:
            return _float_or_none(item.get("score"))
    return None


def _json_object(raw: str) -> dict[str, object]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_array(raw: str) -> list[object]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _int_or_none(value: object) -> Optional[int]:
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> Optional[float]:
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
