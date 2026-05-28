"""Read-only scan of the running laser_pad draft.

Lists duplicate (channel, note) scene clusters and orphan scenes so you can
decide which ones are safe to delete.

Usage:
    python3 tools/orphan_scan.py            # scan the running web service
    python3 tools/orphan_scan.py --file config/laser_director.json   # scan a file
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

TOP = ["startup_scene", "stop_scene", "stale_scene", "emergency_scene", "fallback_scene"]
UTIL = ["safe_scene", "default_scene", "transition_scene", "pre_drop_scene"]
PRIM = ["phrase_scene", "buildup_scene", "drop_scene", "post_drop_scene", "breakdown_scene"]
BANK = ["phrase_bank", "buildup_bank", "drop_bank", "post_drop_bank", "breakdown_bank"]


def load_from_service(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())["config"]


def load_from_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def scan(cfg: dict) -> None:
    scenes = cfg.get("scenes", {})
    personalities = cfg.get("personalities", {})

    ref: set[str] = set()
    origin: dict[str, list[str]] = defaultdict(list)

    for f in TOP:
        v = cfg.get(f)
        if isinstance(v, str) and v:
            ref.add(v)
            origin[v].append(f"config:{f}")

    mc = cfg.get("manual_commands", {})
    if isinstance(mc, dict):
        for slot, body in mc.items():
            if isinstance(body, dict) and body.get("scene"):
                s = body["scene"]
                ref.add(s)
                origin[s].append(f"manual:{slot}")

    for pn, pd in personalities.items():
        if not isinstance(pd, dict):
            continue
        for f in UTIL + PRIM:
            v = pd.get(f)
            if isinstance(v, str) and v:
                ref.add(v)
                origin[v].append(f"{pn}:{f}")
        for f in BANK:
            for s in pd.get(f, []) or []:
                if isinstance(s, str) and s:
                    ref.add(s)
                    origin[s].append(f"{pn}:{f}")

    by_pos: dict[tuple[int, int], list[str]] = defaultdict(list)
    for sn, so in scenes.items():
        if not isinstance(so, dict):
            continue
        midi = so.get("midi") or {}
        if midi.get("note") is None:
            continue
        by_pos[(int(midi.get("channel") or 1), int(midi.get("note")))].append(sn)

    dups = {k: v for k, v in by_pos.items() if len(v) > 1}

    print(
        f"Total scenes: {len(scenes)} | Referenced: {len(ref)} | "
        f"Orphans: {len(scenes) - len(ref)} | Duplicate positions: {len(dups)}\n"
    )

    safe_del: list[str] = []
    unsafe: list[tuple[tuple[int, int], list[str]]] = []
    for (ch, n), names in sorted(dups.items()):
        refs = [x for x in names if x in ref]
        orph = [x for x in names if x not in ref]
        print(f"ch{ch} note{n}:")
        for x in names:
            tag = "REF" if x in ref else "orphan"
            print(f"  {x:35s} [{tag}] {origin.get(x, [])}")
        if refs and orph:
            safe_del.extend(orph)
        elif not refs:
            unsafe.append(((ch, n), names))

    print(f"\n=== SAFE to delete ({len(safe_del)}) ===")
    for x in safe_del:
        m = scenes[x].get("midi") or {}
        print(f"  DELETE  {x:35s}  ch{m.get('channel')} note{m.get('note')}")

    print(f"\n=== Needs review ({len(unsafe)}) all-orphan clusters ===")
    for k, v in unsafe:
        print(f"  {k}: {v}")

    in_dups = {x for names in dups.values() for x in names}
    solo = [s for s in scenes if s not in ref and s not in in_dups]
    print(f"\n=== Standalone orphans ({len(solo)}) ===")
    for x in solo:
        m = scenes[x].get("midi") or {}
        print(f"  {x:35s}  ch{m.get('channel')} note{m.get('note')}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8765/api/config")
    p.add_argument("--file", type=Path, help="Scan a JSON file instead of the live service")
    args = p.parse_args()

    if args.file:
        cfg = load_from_file(args.file)
    else:
        cfg = load_from_service(args.url)
    scan(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
