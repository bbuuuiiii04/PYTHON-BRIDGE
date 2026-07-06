#!/usr/bin/env python3
"""Read-only calibration summary for LIGHTING ENGINE v2 F1 identity.

The script reads existing spectral v4 cache JSON files and mirrors the pure
StateManager identity scoring path. It does not scan Rekordbox, extract audio,
write cache files, write identity-store records, or touch live config.

The starting bass_norm anchors were 0.15/0.90 before corpus calibration; rerun
this tool after a new v4 cache sweep before changing those anchors.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import spectral_cache, spectral_profile  # noqa: E402
from rb_ss_bridge_v2.led_identity_v2 import (  # noqa: E402
    NORM_ANCHORS,
    assign_zone,
    identity_scores,
)

ANCHOR_CHECKS: dict[str, dict[str, str]] = {
    "starsound_pt3": {
        "label": "STARsound (pt3)",
        "expected_zone": "GLACIER",
    },
    "cant_say_nah": {
        "label": "Can't Say Nah",
        "expected_zone": "DEEP_POOL",
    },
}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 6) if values else 0.0,
        "p5": round(_percentile(values, 5.0), 6),
        "p25": round(_percentile(values, 25.0), 6),
        "p50": round(_percentile(values, 50.0), 6),
        "p75": round(_percentile(values, 75.0), 6),
        "p95": round(_percentile(values, 95.0), 6),
        "max": round(max(values), 6) if values else 0.0,
    }


def _cache_dir_v4(path: str | None) -> Path:
    if path:
        return Path(path).expanduser()
    return spectral_cache._cache_dir_v4()  # type: ignore[attr-defined]


def _iter_paths(cache_dir: Path, limit: int | None) -> Iterable[Path]:
    count = 0
    for path in sorted(cache_dir.glob("*.json")):
        yield path
        count += 1
        if limit is not None and count >= limit:
            return


def _is_stale(payload: dict[str, Any]) -> bool:
    audio_filepath = payload.get("audio_filepath")
    if not isinstance(audio_filepath, str) or not audio_filepath:
        return True
    try:
        stat = os.stat(audio_filepath)
    except OSError:
        return True
    return (
        int(payload.get("mtime_ns", -1)) != int(stat.st_mtime_ns)
        or int(payload.get("size", -1)) != int(stat.st_size)
    )


def _feature_from_path(path: Path, *, include_stale: bool) -> tuple[str, Any | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ("corrupt", None, "")
    if not include_stale and _is_stale(payload):
        return ("stale", None, "")
    feature = spectral_cache._features_v4_from_payload(payload)  # type: ignore[attr-defined]
    audio_filepath = payload.get("audio_filepath")
    path_text = audio_filepath if isinstance(audio_filepath, str) else ""
    return ("ok", feature, path_text) if feature is not None else ("invalid", None, path_text)


def _anchor_key(audio_filepath: str) -> str:
    text = (
        audio_filepath.lower()
        .replace("’", "'")
        .replace("_", " ")
        .replace("-", " ")
    )
    if "starsound" in text and ("pt3" in text or "pt 3" in text or "part 3" in text):
        return "starsound_pt3"
    if "can't say nah" in text or "cant say nah" in text:
        return "cant_say_nah"
    return ""


def build_summary(cache_dir: Path, *, limit: int | None, include_stale: bool) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    zones: Counter[str] = Counter()
    axes_values: dict[str, list[float]] = {key: [] for key in ("grit", "punch", "bass", "drama")}
    scalar_values: dict[str, list[float]] = {
        key: []
        for key in (
            "attack_low_p90",
            "brightness_med",
            "growl_timbre_p90",
            "onset_mh_p90",
        )
    }
    score_values: dict[str, list[float]] = {
        key: []
        for key in ("aggression", "luminance", "distortion")
    }
    synth_rates: list[float] = []
    anchor_results: dict[str, dict[str, Any]] = {}

    for path in _iter_paths(cache_dir, limit):
        status, v4, audio_filepath = _feature_from_path(path, include_stale=include_stale)
        counts[status] += 1
        if v4 is None:
            continue
        axes = spectral_profile.identity_axes(v4)
        flags = spectral_profile.sustained_synth_flags(v4)
        synth_rate = (sum(1 for flag in flags if flag) / len(flags)) if flags else 0.0
        scores = identity_scores(axes, dict(v4.scalars), synth_rate)
        zone = assign_zone(scores)
        zones[zone] += 1
        anchor_key = _anchor_key(audio_filepath)
        if anchor_key and anchor_key not in anchor_results:
            expected = ANCHOR_CHECKS[anchor_key]["expected_zone"]
            anchor_results[anchor_key] = {
                "label": ANCHOR_CHECKS[anchor_key]["label"],
                "status": "pass" if zone == expected else "fail",
                "expected_zone": expected,
                "actual_zone": zone,
                "audio_filepath": audio_filepath,
            }
        for key, value in axes.items():
            if key in axes_values:
                axes_values[key].append(float(value))
        for key in scalar_values:
            scalar_values[key].append(float(v4.scalars.get(key, 0.0)))
        for key, value in scores.items():
            score_values[key].append(float(value))
        synth_rates.append(float(synth_rate))

    valid = counts["ok"]
    total = sum(counts.values())
    bass = axes_values["bass"]
    anchor_checks = {
        key: anchor_results.get(
            key,
            {
                "label": target["label"],
                "status": "not_found",
                "expected_zone": target["expected_zone"],
            },
        )
        for key, target in ANCHOR_CHECKS.items()
    }
    return {
        "cache_dir": str(cache_dir),
        "entries_seen": total,
        "valid_entries": valid,
        "anchor_checks": anchor_checks,
        "skipped": {
            "stale": counts["stale"],
            "corrupt": counts["corrupt"],
            "invalid": counts["invalid"],
        },
        "zone_distribution": dict(sorted(zones.items())),
        "zone_distribution_pct": {
            zone: round((count / valid) * 100.0, 2) if valid else 0.0
            for zone, count in sorted(zones.items())
        },
        "recommended_bass_norm": {
            "p5": round(_percentile(bass, 5.0), 6),
            "p95": round(_percentile(bass, 95.0), 6),
        },
        "axis_percentiles": {key: _summary(values) for key, values in axes_values.items()},
        "scalar_percentiles": {key: _summary(values) for key, values in scalar_values.items()},
        "synth_rate_percentiles": _summary(synth_rates),
        "score_percentiles": {key: _summary(values) for key, values in score_values.items()},
        "current_norm_anchors": {
            key: [float(lo), float(hi)] for key, (lo, hi) in sorted(NORM_ANCHORS.items())
        },
        "notes": [
            "read-only summary over existing spectral v4 cache files",
            "recommended_bass_norm is p5/p95 of spectral_profile.identity_axes(v4)['bass']",
            "zone_distribution mirrors led_identity_v2.identity_scores + assign_zone",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", help="Override v4 cache directory")
    parser.add_argument("--limit", type=int, help="Limit number of cache files read")
    parser.add_argument("--include-stale", action="store_true", help="Include stale cache payloads")
    args = parser.parse_args(argv)

    cache_dir = _cache_dir_v4(args.cache_dir)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    summary = build_summary(cache_dir, limit=args.limit, include_stale=bool(args.include_stale))
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
