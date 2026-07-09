#!/usr/bin/env python3
"""Idempotently stage the gentle-drop routing into an LED look-director config.

Part C of docs/plans/active/rt_phase_ember_visibility_spec_2026_07_09.md.

Two keys are written, and ONLY these two:
  1. banks.default.drop — append the four rt chase colorways
     (rt_drop_chase_{blue,cyan,red,green}) if missing (add-if-missing, existing
     order kept). They are realtime_razer, so this respects the cloud-disable
     order. They MUST be in the bank: drop_look_routing only NARROWS the bank
     fail-open, so a tier-1 cell naming looks that are absent from the bank
     intersects to EMPTY and fail-opens to the full bank — the gentle directive
     would silently no-op on every low-energy drop.
  2. f2.drop_look_routing — the full family x tier table:
       tier 1 (WALL/COMET/HOUSE/NEUTRAL) = the rt chase colorways that EXIST in
         looks{};
       tier 2 + tier 3 = the pre-existing modern looks (bank minus cloud minus the
         colorways) — big drops must not rotate into the gentle chases.

The gentle set is RT-ONLY. The 8 legacy `drop_diy_*` chases are CLOUD looks;
routing low-energy drops to them would resurrect transport fighting (the operator
disabled the cloud backend). They are excluded until Template-Lab produces RT
recreations — which then join tier 1 by name. As a guard, any cloud name still
sitting in the drop bank is filtered out of tiers 2/3, so this table never steers
a drop to a cloud look.

The routing table is a *selection* preference only, applied fail-open. It never
touches dispatch, so the led_dispatch_coordinator dwell / cooldown machinery is
unchanged.

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

# The 8 legacy DIY drop chases — CLOUD looks, excluded from all routing (operator
# cloud-disable). Kept only as the exclusion set: never re-added to a bank, never
# routed to. Their eventual replacement is RT recreations from Template Lab.
LEGACY_CLOUD = [
    "drop_diy_1_red_white_chase",
    "drop_diy_2_cyan",
    "drop_diy_3",
    "drop_diy_4_blue_cyan",
    "drop_diy_5_red",
    "drop_diy_green_sparkle",
    "drop_diy_pink_red_sparkle",
    "drop_diy_rainbow_sparkle",
]

# The soft rt chase colorways — the RT gentle chase class. tier 1 = these, BY NAME
# (allow_strobe is a permission flag, not the look's character), dropping only
# names absent from looks{}.
SOFT_QUARTET = [
    "rt_drop_chase_blue",
    "rt_drop_chase_cyan",
    "rt_drop_chase_red",
    "rt_drop_chase_green",
]

FAMILIES = ["WALL", "COMET", "HOUSE", "NEUTRAL"]

_CLOUD_EXCLUDE = set(LEGACY_CLOUD)


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
    """The soft rt chase colorways for tier 1, BY NAME. Drops only names absent
    from looks{}."""
    looks = _looks(data)
    return [q for q in SOFT_QUARTET if q in looks]


def build_target(data: dict) -> tuple[list, dict]:
    """Pure: compute (new drop bank, f2.drop_look_routing) for this config.

    The RT colorways MUST live in the bank or the tier-1 routing cell intersects
    to empty and fail-opens to the full bank (silent no-op on every gentle drop),
    so they are appended if missing (existing order kept). tier 1 = the RT
    colorways that exist in looks{}; tiers 2/3 = the pre-existing modern looks
    (bank minus cloud minus the colorways) — big drops must not rotate into the
    gentle chases.
    """
    current = _current_drop_bank(data)
    quartet = _gentle_quartet(data)
    quartet_set = set(quartet)
    modern = [x for x in current if x not in _CLOUD_EXCLUDE and x not in quartet_set]
    new_bank = list(current) + [q for q in quartet if q not in current]
    routing = {
        fam: {"1": list(quartet), "2": list(modern), "3": list(modern)}
        for fam in FAMILIES
    }
    return new_bank, routing


def apply(data: dict) -> bool:
    """Mutate data in place — banks.default.drop (append RT colorways) and
    f2.drop_look_routing. No other key.

    Returns True if anything changed, False if already at target (no-op).
    """
    new_bank, routing = build_target(data)
    banks = data.setdefault("banks", {})
    default = banks.setdefault("default", {})
    f2 = data.setdefault("f2", {})
    changed = default.get("drop") != new_bank or f2.get("drop_look_routing") != routing
    if changed:
        default["drop"] = new_bank
        f2["drop_look_routing"] = routing
    return changed


def _summary(data: dict, label: str) -> str:
    drop = _current_drop_bank(data)
    legacy_present = [n for n in LEGACY_CLOUD if n in drop]
    quartet_in_bank = [n for n in SOFT_QUARTET if n in drop]
    routing = data.get("f2", {}).get("drop_look_routing", {})
    fams = sorted(routing.keys()) if isinstance(routing, dict) else []
    lines = [
        f"[{label}] banks.default.drop: {len(drop)} looks "
        f"({len(quartet_in_bank)}/4 rt colorways, {len(legacy_present)} legacy cloud)",
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
    print(f"[info] tier-1 gentle set = {len(quartet)} rt colorways {quartet} (RT-only; no cloud)")

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
