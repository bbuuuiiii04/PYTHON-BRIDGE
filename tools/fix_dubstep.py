"""Fill the dubstep skeleton's empty primary scenes with house placeholders.

Sends one /api/draft patch that:
  - Sets dubstep's 6 primary scene slots (default, phrase, buildup, drop,
    post_drop, breakdown) to existing house scenes.
  - Ensures post_drop_bank and breakdown_bank contain their primaries
    (currently empty for dubstep).

After running, the 6 'must be a non-empty string' validation errors clear
and the header banner goes away. You then customize dubstep in the UI.

This script ONLY mutates the in-memory draft. Disk is not touched until
you hit Save & Apply in the UI.

Usage:
    python3 tools/fix_dubstep.py --dry-run
    python3 tools/fix_dubstep.py
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

PATCH = {
    "personalities": {
        "dubstep": {
            "default_scene": "house_groove_1",
            "phrase_scene": "house_groove_1",
            "buildup_scene": "house_buildup_1",
            "drop_scene": "house_drop_1",
            "post_drop_scene": "house_drop_1",
            "breakdown_scene": "house_breakdown_1",
            "post_drop_bank": ["house_drop_1"],
            "breakdown_bank": ["house_breakdown_1"],
        }
    }
}


def fetch_config(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/api/config", timeout=5) as resp:
        return json.loads(resp.read())


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
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cfg_payload = fetch_config(args.base)
    cfg = cfg_payload["config"]
    personalities = cfg.get("personalities") or {}
    if "dubstep" not in personalities:
        print("dubstep personality not found in draft. Nothing to do.")
        return 1

    scenes = cfg.get("scenes") or {}
    needed = {"house_groove_1", "house_buildup_1", "house_drop_1", "house_breakdown_1"}
    missing = sorted(s for s in needed if s not in scenes)
    if missing:
        print(f"ERROR: required house scenes missing from config: {missing}")
        print("Refusing to apply patch that would create dangling references.")
        return 2

    print("Patch to apply:")
    print(json.dumps(PATCH, indent=2))
    print()

    if args.dry_run:
        print("--dry-run: no changes sent.")
        return 0

    result = post_patch(args.base, PATCH)
    print("Response:")
    print(json.dumps(result, indent=2))

    after_payload = fetch_config(args.base)
    errs = after_payload.get("errors") or []
    dubstep_errs = [e for e in errs if "dubstep" in e]
    print()
    print(f"Total errors after patch: {len(errs)}")
    print(f"Dubstep errors after patch: {len(dubstep_errs)}")
    if dubstep_errs:
        for e in dubstep_errs:
            print(f"  - {e}")
        return 3
    print("Dubstep validation clear. Hit Save & Apply in the UI to persist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
