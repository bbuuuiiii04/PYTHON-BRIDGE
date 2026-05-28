"""Delete orphan scenes from the running laser_pad draft.

Targets a fixed list of scene names. For each, the script:
  - Re-confirms the scene is unreferenced (refuses to delete a scene
    that is now referenced anywhere).
  - Sends a single /api/draft patch with `null` values to remove them.

This script ONLY mutates the in-memory draft. Disk is not touched until
you hit Save & Apply in the UI.

Usage:
    python3 tools/orphan_cleanup.py            # apply
    python3 tools/orphan_cleanup.py --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict

ORPHANS_TO_DELETE = [
    "house_pre_drop_1",
    "house_drop_sustain_1",
    "house_post_drop_1",
    "house_phrase_1",
]

TOP = ["startup_scene", "stop_scene", "stale_scene", "emergency_scene", "fallback_scene"]
UTIL = ["safe_scene", "default_scene", "transition_scene", "pre_drop_scene"]
PRIM = ["phrase_scene", "buildup_scene", "drop_scene", "post_drop_scene", "breakdown_scene"]
BANK = ["phrase_bank", "buildup_bank", "drop_bank", "post_drop_bank", "breakdown_bank"]


def fetch_config(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/api/config", timeout=5) as resp:
        return json.loads(resp.read())["config"]


def references(cfg: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for f in TOP:
        v = cfg.get(f)
        if isinstance(v, str) and v:
            out[v].append(f"config:{f}")
    for pn, pd in (cfg.get("personalities") or {}).items():
        if not isinstance(pd, dict):
            continue
        for f in UTIL + PRIM:
            v = pd.get(f)
            if isinstance(v, str) and v:
                out[v].append(f"{pn}:{f}")
        for f in BANK:
            for s in pd.get(f, []) or []:
                if isinstance(s, str) and s:
                    out[s].append(f"{pn}:{f}")
    return out


def post_patch(base: str, patch: dict) -> dict:
    body = json.dumps({"patch": patch}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/draft",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8765")
    p.add_argument("--dry-run", action="store_true", help="Preview only; do not POST.")
    args = p.parse_args()

    cfg = fetch_config(args.base)
    scenes = cfg.get("scenes") or {}
    refs = references(cfg)

    print(f"Targets: {ORPHANS_TO_DELETE}")
    print()

    to_delete = []
    for name in ORPHANS_TO_DELETE:
        if name not in scenes:
            print(f"  SKIP    {name}: not in scenes (already removed?)")
            continue
        existing_refs = refs.get(name, [])
        if existing_refs:
            print(f"  REFUSE  {name}: now referenced by {existing_refs}")
            continue
        midi = (scenes[name].get("midi") or {})
        print(f"  WILL DELETE  {name}  ch{midi.get('channel')} note{midi.get('note')}")
        to_delete.append(name)

    if not to_delete:
        print("\nNothing to delete.")
        return 0

    if args.dry_run:
        print("\n--dry-run: no changes sent.")
        return 0

    patch = {"scenes": {name: None for name in to_delete}}
    print(f"\nPOST /api/draft  patch={json.dumps(patch)}")
    result = post_patch(args.base, patch)
    print(f"\nResponse:")
    print(json.dumps(result, indent=2))

    new_cfg = fetch_config(args.base)
    after = new_cfg.get("scenes") or {}
    still = [n for n in to_delete if n in after]
    if still:
        print(f"\nSTILL PRESENT: {still}")
        return 1
    print(f"\nDeleted {len(to_delete)} scene(s) from draft. Hit Save & Apply in the UI to persist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
