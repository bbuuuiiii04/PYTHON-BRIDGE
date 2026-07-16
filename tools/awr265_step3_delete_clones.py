#!/usr/bin/env python3
"""AWR-265 Step 3 follow-up — delete color-suffix clones AFTER live-mix verify.

DO NOT RUN until the operator confirms the next live mix looks right with the
palette-fed base cues. This script is the single-command cleanup.

What it does (example + live configs):
  1. Backs up each config to *.pre_awr265_step3.bak
  2. Removes every look listed in banks.legacy_color_suffix (the clones)
  3. Removes the legacy_color_suffix bank itself
  4. Strips those names from drop_pairs / locked_palette_by_look / exempt_looks /
     pad drafts / f2 plan name lists when present
  5. Re-runs load_led_look_director_config and refuses to write if available!=True

Residuals that MUST stay (frame A/B never went green — Step 0):
  Leave these out of --include-residuals unless a later engine round lands:
    rt_groove_chase_cyan_white, rt_drop_chase_cyan_white, rt_post_drop_chase_cyan_white,
    rt_drop_center_burst_blue_cyan, rt_post_drop_center_comet_blue_cyan, rt_twinkle_blue

Usage (from repo root, after operator verdict):
  python3 tools/awr265_step3_delete_clones.py --dry-run
  python3 tools/awr265_step3_delete_clones.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PARENT = _ROOT.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402

RESIDUALS = frozenset(
    {
        "rt_groove_chase_cyan_white",
        "rt_drop_chase_cyan_white",
        "rt_post_drop_chase_cyan_white",
        "rt_drop_center_burst_blue_cyan",
        "rt_post_drop_center_comet_blue_cyan",
        "rt_twinkle_blue",
    }
)


def _legacy_names(cfg: dict) -> list[str]:
    legacy = (cfg.get("banks") or {}).get("legacy_color_suffix") or {}
    names: list[str] = []
    if isinstance(legacy, dict):
        for values in legacy.values():
            if isinstance(values, list):
                names.extend(str(v) for v in values)
    return sorted(set(names))


def _scrub(cfg: dict, delete: set[str]) -> None:
    looks = cfg.get("looks") or {}
    for name in list(looks):
        if name in delete:
            looks.pop(name, None)
    banks = cfg.get("banks") or {}
    banks.pop("legacy_color_suffix", None)
    default = banks.get("default") or {}
    if isinstance(default, dict):
        for role, values in list(default.items()):
            if isinstance(values, list):
                default[role] = [n for n in values if n not in delete]
    pairs = cfg.get("drop_pairs") or {}
    if isinstance(pairs, dict):
        for key in list(pairs):
            if key in delete:
                pairs.pop(key, None)
                continue
            entry = pairs.get(key)
            if isinstance(entry, dict):
                for k, v in list(entry.items()):
                    if v in delete:
                        entry.pop(k, None)
    engine = cfg.get("color_engine") or {}
    if isinstance(engine, dict):
        exempt = engine.get("exempt_looks")
        if isinstance(exempt, list):
            engine["exempt_looks"] = [n for n in exempt if n not in delete]
        for key in (
            "locked_palette_by_look",
            "slot_fill_strategy_by_look",
            "slot_mono_chance_by_look",
        ):
            mapping = engine.get(key)
            if isinstance(mapping, dict):
                for name in list(mapping):
                    if name in delete:
                        mapping.pop(name, None)
    # f2 family plan name lists
    f2 = cfg.get("f2") or {}
    plans = f2.get("plans") if isinstance(f2, dict) else None
    if isinstance(plans, dict):
        for family, tiers in plans.items():
            if not isinstance(tiers, dict):
                continue
            for tier, names in list(tiers.items()):
                if isinstance(names, list):
                    tiers[tier] = [n for n in names if n not in delete]


def process(path: Path, *, apply: bool, include_residuals: bool) -> int:
    cfg = json.loads(path.read_text())
    names = set(_legacy_names(cfg))
    if not include_residuals:
        names -= RESIDUALS
    if not names:
        print(f"{path}: nothing to delete")
        return 0
    print(f"{path}: would delete {len(names)} looks:")
    for name in sorted(names):
        print(f"  - {name}")
    if RESIDUALS & set(_legacy_names(cfg)) and not include_residuals:
        kept = sorted(RESIDUALS & set(_legacy_names(cfg)))
        print(f"{path}: keeping residuals (IMPOSSIBLE A/B): {', '.join(kept)}")
    candidate = json.loads(json.dumps(cfg))
    _scrub(candidate, names)
    # Write to temp path for loader gate
    tmp = path.with_suffix(path.suffix + ".awr265_step3_check")
    tmp.write_text(json.dumps(candidate, indent=2) + "\n")
    result = load_led_look_director_config(str(tmp))
    tmp.unlink(missing_ok=True)
    print(
        f"LOADER gate: available={result.available} reason={result.reason} "
        f"errors={list(result.errors)}"
    )
    if not result.available:
        print("REFUSING to apply — loader would go dark")
        return 2
    if not apply:
        print("dry-run only (pass --apply to write)")
        return 0
    bak = path.with_suffix(path.suffix + ".pre_awr265_step3.bak")
    bak.write_text(path.read_text())
    path.write_text(json.dumps(candidate, indent=2) + "\n")
    print(f"wrote {path} (backup {bak})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--include-residuals",
        action="store_true",
        help="Also delete IMPOSSIBLE A/B residuals (dangerous; default keep)",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Config path (default: example + live if present)",
    )
    args = parser.parse_args(argv)
    paths = [Path(p) for p in args.config] if args.config else [
        _ROOT / "config/led_look_director.example.json",
        _ROOT / "config/led_look_director.json",
    ]
    rc = 0
    for path in paths:
        if not path.exists():
            print(f"skip missing {path}")
            continue
        rc = max(rc, process(path, apply=args.apply, include_residuals=args.include_residuals))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
