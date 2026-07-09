#!/usr/bin/env python3
"""Idempotently stage the gentle-drop routing into an LED look-director config.

Part C of docs/plans/active/rt_phase_ember_visibility_spec_2026_07_09.md.

Two edits, and ONLY these two keys:
  1. banks.default.drop  — re-add the 8 legacy `drop_diy_*` chases (they were
     surgically removed in an earlier mirror). Legacy first, then the existing
     modern looks, no duplicates.
  2. f2.drop_look_routing — write the full family x tier table:
       tier 1 (WALL/COMET/HOUSE/NEUTRAL) = 8 legacy chases + the soft rt chase
         colorways (rt_drop_chase_{blue,cyan,red,green}) that EXIST in looks{};
       tier 2 + tier 3 = the current modern drop bank (unchanged rotation).

Because drop_look_routing NARROWS the bank fail-open (an empty intersection keeps
the full bank), the legacy names MUST stay in the bank or the tier-1 cell would
silently no-op — hence edit 1 and edit 2 ship together.

The routing table is a *selection* preference only. Whatever look it steers to
still dispatches through led_dispatch_coordinator, so the cloud_diy rate-limit /
min-dwell machinery keeps applying to the legacy cloud looks — this script does
not touch it.

Idempotent: a second run detects the config already matches and writes nothing.

DEFAULT TARGET IS THE LIVE CONFIG. Do not run this against the live config
yourself — the executive runs it at the batched restart. For tests / dry checks
pass --config <path> to point at a fixture copy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "led_look_director.json"

# The 8 legacy DIY drop chases (operator's low-energy-drop rotation), in the
# canonical order they held in the example config before the mirror removed them.
LEGACY_8 = [
    "drop_diy_1_red_white_chase",
    "drop_diy_2_cyan",
    "drop_diy_3",
    "drop_diy_4_blue_cyan",
    "drop_diy_5_red",
    "drop_diy_green_sparkle",
    "drop_diy_pink_red_sparkle",
    "drop_diy_rainbow_sparkle",
]

# The soft rt chase colorways — the gentle chase class. Included in tier 1 BY NAME
# (allow_strobe is a permission flag, not the look's character), dropping only
# names that are absent from looks{}.
SOFT_QUARTET = [
    "rt_drop_chase_blue",
    "rt_drop_chase_cyan",
    "rt_drop_chase_red",
    "rt_drop_chase_green",
]

FAMILIES = ["WALL", "COMET", "HOUSE", "NEUTRAL"]

_LEGACY_SET = set(LEGACY_8)


def _looks(data: dict) -> dict:
    looks = data.get("looks")
    return looks if isinstance(looks, dict) else {}


def _current_drop_bank(data: dict) -> list:
    bank = (
        data.get("banks", {})
        .get("default", {})
        .get("drop", [])
    )
    return list(bank) if isinstance(bank, list) else []


def _gentle_quartet(data: dict) -> list:
    """The soft rt chase colorways for tier 1, BY NAME — allow_strobe is a
    permission flag, not the look's character. Drops only names absent from
    looks{}."""
    looks = _looks(data)
    return [q for q in SOFT_QUARTET if q in looks]


def build_target(data: dict) -> tuple[list, dict]:
    """Pure: compute the target (drop bank, routing table) for this config.

    Modern set = the current drop bank minus any legacy already present, so the
    result is stable whether the bank arrives with or without the legacy 8.
    """
    current = _current_drop_bank(data)
    modern = [x for x in current if x not in _LEGACY_SET]
    new_drop = LEGACY_8 + modern

    tier1 = LEGACY_8 + _gentle_quartet(data)
    routing = {
        fam: {"1": list(tier1), "2": list(modern), "3": list(modern)}
        for fam in FAMILIES
    }
    return new_drop, routing


def apply(data: dict) -> bool:
    """Mutate data in place (banks.default.drop + f2.drop_look_routing only).

    Returns True if anything changed, False if already at target (no-op).
    """
    new_drop, routing = build_target(data)

    banks = data.setdefault("banks", {})
    default = banks.setdefault("default", {})
    f2 = data.setdefault("f2", {})

    changed = default.get("drop") != new_drop or f2.get("drop_look_routing") != routing
    if changed:
        default["drop"] = new_drop
        f2["drop_look_routing"] = routing
    return changed


def _summary(data: dict, label: str) -> str:
    drop = _current_drop_bank(data)
    legacy_present = [n for n in LEGACY_8 if n in drop]
    routing = data.get("f2", {}).get("drop_look_routing", {})
    fams = sorted(routing.keys()) if isinstance(routing, dict) else []
    lines = [
        f"[{label}] banks.default.drop: {len(drop)} looks "
        f"({len(legacy_present)}/8 legacy present)",
        f"[{label}] f2.drop_look_routing: {len(fams)} families {fams}",
    ]
    if isinstance(routing, dict):
        for fam in FAMILIES:
            cell = routing.get(fam, {})
            if isinstance(cell, dict):
                sizes = {t: len(cell.get(t, [])) for t in ("1", "2", "3")}
                lines.append(f"[{label}]   {fam} tier sizes {sizes}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help="path to the LED look-director config (default: the LIVE config)",
    )
    args = ap.parse_args(argv)
    path = Path(args.config)

    if not path.exists():
        print(f"error: config not found: {path}", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))

    print(_summary(data, "before"))
    quartet = _gentle_quartet(data)
    print(f"[info] tier-1 gentle set = 8 legacy chases + {len(quartet)} soft quartet {quartet}")

    changed = apply(data)
    if not changed:
        print("[result] already applied — no changes written.")
        return 0

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(_summary(data, "after"))
    print(f"[result] applied — wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
