#!/usr/bin/env python3
"""Read-only ANLZ tag inventory and sampling helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


WAVEFORM_TAGS = ("PWV3", "PWAV", "PWV4", "PWV5", "PWV6", "PWV7", "PWV8")


def _parse_anlz_file(path: Path) -> Any:
    from pyrekordbox.anlz import AnlzFile  # type: ignore

    return AnlzFile.parse_file(path)


def _candidate_anlz_paths(anlz_path: str) -> list[Path]:
    path = Path(anlz_path).expanduser()
    candidates: list[Path] = []
    if path.suffix.upper() in (".DAT", ".EXT", ".2EX"):
        for suffix in (".EXT", ".2EX", ".DAT"):
            candidate = path.with_suffix(suffix)
            if candidate.exists():
                candidates.append(candidate)
    elif path.exists():
        candidates.append(path)

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _safe_getall_tags(anlz: Any, tag_type: str) -> list[Any]:
    try:
        return list(anlz.getall_tags(tag_type))
    except Exception:
        return []


def _safe_file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0


def _safe_public_names(obj: Any) -> list[str]:
    try:
        return sorted(name for name in dir(obj) if not name.startswith("_"))
    except Exception:
        return []


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (bool, int, float, str)):
        return value
    if value is None:
        return None
    return str(type(value).__name__)


def _safe_entries(content: Any) -> list[Any]:
    entries = getattr(content, "entries", None)
    if entries is None and isinstance(content, dict):
        entries = content.get("entries")
    if entries is None:
        return []
    try:
        return list(entries)
    except Exception:
        return []


def _sample_tag(tag: Any, limit_samples: int) -> dict[str, Any]:
    content = getattr(tag, "content", None)
    sample: dict[str, Any] = {
        "tag_public_names": _safe_public_names(tag),
        "content_public_names": _safe_public_names(content) if content is not None else [],
    }

    if content is not None:
        content_scalars: dict[str, Any] = {}
        for name in _safe_public_names(content):
            try:
                value = getattr(content, name)
            except Exception:
                continue
            if callable(value):
                continue
            if isinstance(value, (list, tuple, dict, set)):
                continue
            content_scalars[name] = _safe_scalar(value)
        if content_scalars:
            sample["content_scalar_fields"] = content_scalars

    entries = _safe_entries(content)
    if entries:
        sample["entry_count"] = len(entries)
        sample["entry_samples"] = [_safe_scalar(entry) for entry in entries[: max(0, limit_samples)]]
    return sample


def _extract_beatgrid_duration_ms(anlz: Any) -> float | None:
    for tag_type in ("PQT2", "PQTZ"):
        for tag in _safe_getall_tags(anlz, tag_type):
            try:
                times = sorted(float(t) * 1000.0 for t in tag.get_times() if float(t) >= 0.0)
            except Exception:
                continue
            if len(times) >= 2:
                return times[-1] + (times[-1] - times[-2])
    return None


def _waveform_inference(tag_type: str, tag: Any, duration_ms: float | None) -> dict[str, Any]:
    entries = _safe_entries(getattr(tag, "content", None))
    if not entries:
        return {}

    inferred: dict[str, Any] = {"entry_count": len(entries)}
    if tag_type in ("PWV3", "PWAV"):
        try:
            heights = [int(entry) & 0x1F for entry in entries]
            inferred["height_sample"] = heights[:8]
            inferred["height_peak"] = max(heights) if heights else None
        except Exception:
            inferred["height_sample"] = []

    if duration_ms and len(entries) > 0:
        inferred["inferred_ms_per_entry"] = round(float(duration_ms) / float(len(entries)), 4)
    return inferred


def dump_file(path: Path, limit_samples: int) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": _safe_file_size(path),
        "tag_types": [],
        "tag_counts": {},
        "available_public": {},
        "tags": {},
        "errors": [],
    }
    if not path.exists():
        record["errors"].append("missing_file")
        return record

    try:
        anlz = _parse_anlz_file(path)
    except Exception as exc:
        if isinstance(exc, (ImportError, ModuleNotFoundError)) or "pyrekordbox" in str(exc).lower():
            record["errors"].append(f"pyrekordbox_import_failed:{exc}")
        else:
            record["errors"].append(f"parse_failed:{exc}")
        return record

    try:
        tag_types = list(getattr(anlz, "tag_types"))
    except Exception:
        tag_types = []
    if not tag_types:
        try:
            tag_types = list(anlz.keys())
        except Exception:
            tag_types = []

    record["tag_types"] = sorted({str(tag_type) for tag_type in tag_types})
    record["available_public"] = {
        "anlz_public_names": _safe_public_names(anlz),
    }

    beatgrid_duration_ms = _extract_beatgrid_duration_ms(anlz)
    if beatgrid_duration_ms:
        record["inferred_track_duration_ms"] = round(float(beatgrid_duration_ms), 3)

    for tag_type in record["tag_types"]:
        try:
            tags = _safe_getall_tags(anlz, tag_type)
            record["tag_counts"][tag_type] = len(tags)
            tag_records: list[dict[str, Any]] = []
            for tag in tags:
                tag_record = _sample_tag(tag, limit_samples)
                if tag_type in WAVEFORM_TAGS:
                    tag_record["waveform_inference"] = _waveform_inference(
                        tag_type, tag, beatgrid_duration_ms
                    )
                tag_records.append(tag_record)
            record["tags"][tag_type] = tag_records
        except Exception as exc:
            record["errors"].append(f"tag_read_failed:{tag_type}:{exc}")
            continue

    return record


def _write_output(text: str, out_path: str | None) -> None:
    if out_path:
        Path(out_path).expanduser().write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _format_human(record: dict[str, Any]) -> str:
    lines = [
        f"file: {record.get('path', '')}",
        f"  exists: {record.get('exists', False)}",
        f"  size_bytes: {record.get('size_bytes', 0)}",
        f"  tag_types: {', '.join(record.get('tag_types', [])) or '(none)'}",
    ]
    if record.get("inferred_track_duration_ms") is not None:
        lines.append(f"  inferred_track_duration_ms: {record.get('inferred_track_duration_ms')}")
    lines.append("  tag_counts:")
    for tag_type, count in sorted(record.get("tag_counts", {}).items()):
        lines.append(f"    - {tag_type}: {count}")
    if record.get("errors"):
        lines.append("  errors:")
        for err in record["errors"]:
            lines.append(f"    - {err}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump ANLZ tags and safe sample data (read-only).")
    parser.add_argument("anlz_paths", nargs="+", help="ANLZ path(s), e.g. ANLZ0000.DAT/EXT/2EX")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--limit-samples", type=int, default=8, help="Max entry samples per tag.")
    parser.add_argument("--out", help="Optional output file path.")
    args = parser.parse_args()

    expanded: list[Path] = []
    for path in args.anlz_paths:
        candidates = _candidate_anlz_paths(path)
        if candidates:
            expanded.extend(candidates)
        else:
            expanded.append(Path(path).expanduser())

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in expanded:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)

    records = [dump_file(path, limit_samples=max(0, args.limit_samples)) for path in deduped]
    if args.json:
        _write_output(json.dumps({"files": records}, indent=2), args.out)
        return 0

    body = "\n\n".join(_format_human(record) for record in records)
    _write_output(body, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
