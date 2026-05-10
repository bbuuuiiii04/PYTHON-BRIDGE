#!/usr/bin/env python3
"""Dump Rekordbox PSSI phrase entries from local ANLZ files.

Usage:
    python scripts/dump_pssi_phrases.py /path/to/ANLZ0000.DAT [/more/paths...]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PssiRow:
    source_file: str
    mood: int
    entry_index: int
    kind: int
    pssi_beat: int
    bridge_beat: int
    elapsed_ms: int | None


def _candidate_anlz_paths(anlz_path: str) -> list[Path]:
    path = Path(anlz_path)
    candidates: list[Path] = []
    if path.suffix.upper() in (".DAT", ".EXT", ".2EX"):
        for suffix in (".EXT", ".2EX", ".DAT"):
            candidate = path.with_suffix(suffix)
            if candidate.exists():
                candidates.append(candidate)
    if not candidates and path.exists():
        candidates.append(path)

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _safe_getall_tags(anlz: object, tag_type: str) -> list[object]:
    try:
        return list(anlz.getall_tags(tag_type))  # type: ignore[attr-defined]
    except Exception:
        return []


def _extract_beatgrid_times_ms(anlz: object) -> list[float]:
    for tag_type in ("PQT2", "PQTZ"):
        for tag in _safe_getall_tags(anlz, tag_type):
            try:
                times = [float(t) * 1000.0 for t in tag.get_times()]  # type: ignore[attr-defined]
            except Exception:
                continue
            values = sorted(t for t in times if t >= 0.0)
            if values:
                return values
    return []


def _elapsed_for_bridge_beat(beatgrid_ms: list[float], bridge_beat: int) -> int | None:
    if not beatgrid_ms:
        return None
    if 0 <= bridge_beat < len(beatgrid_ms):
        return int(round(beatgrid_ms[bridge_beat]))
    return None


def _iter_pssi_rows(anlz_path: str) -> Iterable[PssiRow]:
    from pyrekordbox.anlz import AnlzFile  # type: ignore

    for candidate in _candidate_anlz_paths(anlz_path):
        try:
            anlz = AnlzFile.parse_file(candidate)
        except Exception as exc:
            print(f"[ERROR] parse failed: {candidate}: {exc}")
            continue

        beatgrid_ms = _extract_beatgrid_times_ms(anlz)
        tags = _safe_getall_tags(anlz, "PSSI")
        if not tags:
            print(f"[WARN] no PSSI tags: {candidate}")
            continue

        for tag in tags:
            content = getattr(tag, "content", None)
            mood = int(getattr(content, "mood", 0))
            entries = getattr(content, "entries", None)
            if entries is None and isinstance(content, dict):
                entries = content.get("entries")
            if not entries:
                continue

            for idx, entry in enumerate(entries):
                try:
                    kind = int(getattr(entry, "kind"))
                    pssi_beat = int(getattr(entry, "beat"))
                except Exception:
                    continue
                bridge_beat = max(0, pssi_beat - 1)
                elapsed_ms = _elapsed_for_bridge_beat(beatgrid_ms, bridge_beat)
                yield PssiRow(
                    source_file=str(candidate),
                    mood=mood,
                    entry_index=idx,
                    kind=kind,
                    pssi_beat=pssi_beat,
                    bridge_beat=bridge_beat,
                    elapsed_ms=elapsed_ms,
                )


def _format_elapsed(elapsed_ms: int | None) -> str:
    return "n/a" if elapsed_ms is None else str(elapsed_ms)


def dump_for_path(anlz_path: str) -> None:
    print(f"\n=== INPUT {anlz_path} ===")
    rows = list(_iter_pssi_rows(anlz_path))
    if not rows:
        print("no PSSI rows")
        return

    for row in rows:
        print(
            "source={source} mood={mood} idx={idx} kind={kind} "
            "pssi_beat={pssi} bridge_beat={bridge} elapsed_ms={elapsed}".format(
                source=row.source_file,
                mood=row.mood,
                idx=row.entry_index,
                kind=row.kind,
                pssi=row.pssi_beat,
                bridge=row.bridge_beat,
                elapsed=_format_elapsed(row.elapsed_ms),
            )
        )

    print("-- compact summary (bridge_beat, kind, mood, elapsed_ms) --")
    ordered = sorted(rows, key=lambda r: (r.bridge_beat, r.kind, r.mood, r.entry_index))
    for row in ordered:
        print(
            "{bridge:>6}, {kind:>2}, {mood:>2}, {elapsed}".format(
                bridge=row.bridge_beat,
                kind=row.kind,
                mood=row.mood,
                elapsed=_format_elapsed(row.elapsed_ms),
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump ANLZ PSSI phrase entries")
    parser.add_argument("anlz_paths", nargs="+", help="One or more ANLZ paths (.DAT/.EXT/.2EX)")
    args = parser.parse_args()

    try:
        import pyrekordbox.anlz  # noqa: F401
    except Exception as exc:
        print(f"[ERROR] pyrekordbox import failed: {exc}")
        return 1

    for path in args.anlz_paths:
        try:
            dump_for_path(path)
        except Exception as exc:
            print(f"[ERROR] unexpected failure for {path}: {exc}")
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
