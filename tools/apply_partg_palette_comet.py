#!/usr/bin/env python3
"""Stage the Part G palette-cycling comet pair into an LED look-director config.

Part G of docs/plans/active/rt_phase_ember_visibility_spec_2026_07_09.md
(AWR-188): the palette-cycling comet replaces the pulled BAKED-rainbow pair.
The renderer/effect side (`palette_comet` slot effect, C5 allowlist, example
config defs) ships in the repo; this script banks the pair into the LIVE
config. It is delivered as a script because ledtune concurrently rewrites
`f2.drop_look_routing` (Round A) — THE EXECUTIVE RUNS THIS AFTER ROUND A
LANDS. Do not run it against the live config from a build lane.

What it writes (add-if-missing everywhere — a re-run never clobbers later
operator desk tuning of the look params):
  1. looks.rt_drop_palette_comet + looks.rt_post_drop_palette_comet — the
     Part G pair (engine-colored `palette_comet` slot effect; exact copies of
     the example-config defs).
  2. drop_pairs.rt_drop_palette_comet -> rt_post_drop_palette_comet
     (mirrors the old rt_rainbow_drop pair entry).
  3. f2.drop_look_routing.COMET tiers "2" and "3" — append the drop look
     (COMET family only, per the Part G dispatch brief).
  4. banks.default.drop — append the drop look. It MUST be in the bank:
     routing only NARROWS the bank fail-open, so a routed name absent from
     the bank intersects to empty and silently no-ops (the Part C lesson).
  5. banks.default.post_drop — append the post_drop look (pair consumption
     requires the look to exist; bank membership keeps it in the post_drop
     rotation like the old rainbow post_drop was).

Safety properties (CFIX2 precedent):
  - Structural anomalies (missing COMET tier cells / banks) abort BEFORE any
    write — this script never half-builds the Round A routing table.
  - The mutated config is validated through the real loader
    (led_config.load_led_look_director_config_from_dict) BEFORE any write;
    validator errors abort with nothing written. This also fails closed when
    the checked-out repo lacks the Part G renderer registration (the C5
    allowlist would reject the `palette_comet` scene_ref).
  - Timestamped backup next to the config (gitignored via *.backup_*), then
    an atomic same-directory tmp+rename write.
  - Self-verifying: the written file is re-read and re-checked; on mismatch
    the backup is restored and the script exits non-zero.
  - Idempotent: a second run detects the config already matches and writes
    nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "led_look_director.json"

DROP_LOOK = "rt_drop_palette_comet"
POST_DROP_LOOK = "rt_post_drop_palette_comet"

# Exact copies of the config/led_look_director.example.json defs. Movement
# params mirror the pulled rt_rainbow_* pair; color_source is "engine" so the
# dispatch layer injects the track palette as slot_colors (the whole point:
# a palette, not a renderer branch).
LOOK_DEFS = {
    DROP_LOOK: {
        "target": "room_perimeter",
        "action": "realtime",
        "scene_ref": "palette_comet",
        "fallback": "rt_blackout",
        "safety_class": "drop",
        "brightness": 100,
        "allow_strobe": False,
        "backend": "realtime_razer",
        "color_source": "engine",
        "params": {"width": 6, "cycle_beats": 1, "travel_per_beat": 30},
    },
    POST_DROP_LOOK: {
        "target": "room_perimeter",
        "action": "realtime",
        "scene_ref": "palette_comet",
        "fallback": "rt_blackout",
        "safety_class": "post_drop",
        "brightness": 100,
        "allow_strobe": False,
        "backend": "realtime_razer",
        "color_source": "engine",
        # AWR-197: loop_beats 4.0 is the explicit accepted-as-is legacy pace
        # (kept example-synced; test_partg_palette_comet pins the match).
        "params": {"width": 2, "cycle_beats": 8, "loop_beats": 4.0},
    },
}


def apply(data: dict) -> bool:
    """Mutate data in place, add-if-missing only. Returns True if anything
    changed. Raises ValueError (nothing mutated) when the config lacks the
    containers this script appends into — never half-builds them."""
    looks = data.get("looks")
    if not isinstance(looks, dict):
        raise ValueError("config has no looks{} object")
    comet_cell = data.get("f2", {}).get("drop_look_routing", {}).get("COMET")
    if not isinstance(comet_cell, dict):
        raise ValueError("f2.drop_look_routing.COMET missing — run AFTER Round A lands")
    for tier in ("2", "3"):
        if not isinstance(comet_cell.get(tier), list):
            raise ValueError(f"f2.drop_look_routing.COMET.{tier} is not a list")
    default_bank = data.get("banks", {}).get("default")
    if not isinstance(default_bank, dict):
        raise ValueError("banks.default missing")
    for role in ("drop", "post_drop"):
        if not isinstance(default_bank.get(role), list):
            raise ValueError(f"banks.default.{role} is not a list")
    pairs = data.get("drop_pairs")
    if not isinstance(pairs, dict):
        raise ValueError("drop_pairs missing")

    changed = False
    for name, spec in LOOK_DEFS.items():
        if name not in looks:
            looks[name] = json.loads(json.dumps(spec))  # deep copy
            changed = True
    if DROP_LOOK not in pairs:
        pairs[DROP_LOOK] = {"post_drop": POST_DROP_LOOK}
        changed = True
    for tier in ("2", "3"):
        if DROP_LOOK not in comet_cell[tier]:
            comet_cell[tier].append(DROP_LOOK)
            changed = True
    if DROP_LOOK not in default_bank["drop"]:
        default_bank["drop"].append(DROP_LOOK)
        changed = True
    if POST_DROP_LOOK not in default_bank["post_drop"]:
        default_bank["post_drop"].append(POST_DROP_LOOK)
        changed = True
    return changed


def verify(data: dict) -> list[str]:
    """Post-conditions on a config dict. Empty list == staged correctly."""
    problems: list[str] = []
    looks = data.get("looks", {})
    for name in (DROP_LOOK, POST_DROP_LOOK):
        if name not in looks:
            problems.append(f"looks.{name} missing")
    pair = data.get("drop_pairs", {}).get(DROP_LOOK)
    if not isinstance(pair, dict) or pair.get("post_drop") != POST_DROP_LOOK:
        problems.append(f"drop_pairs.{DROP_LOOK} not wired to {POST_DROP_LOOK}")
    comet = data.get("f2", {}).get("drop_look_routing", {}).get("COMET", {})
    for tier in ("2", "3"):
        if DROP_LOOK not in (comet.get(tier) or []):
            problems.append(f"COMET tier {tier} missing {DROP_LOOK}")
    bank = data.get("banks", {}).get("default", {})
    if DROP_LOOK not in (bank.get("drop") or []):
        problems.append(f"banks.default.drop missing {DROP_LOOK}")
    if POST_DROP_LOOK not in (bank.get("post_drop") or []):
        problems.append(f"banks.default.post_drop missing {POST_DROP_LOOK}")
    return problems


def _loader_errors(data: dict) -> list[str]:
    """Run the mutated config through the REAL led_config loader. Fail closed:
    an un-importable loader is a reason NOT to touch the live config."""
    sys.path.insert(0, str(_REPO_ROOT.parent))
    try:
        from rb_ss_bridge_v2.led_config import (  # noqa: E402
            load_led_look_director_config_from_dict,
        )
    except Exception as exc:  # pragma: no cover - environment failure path
        return [f"cannot import led_config loader for validation: {exc!r}"]
    result = load_led_look_director_config_from_dict(data)
    if not result.available or result.reason != "ok":
        return list(result.errors) or [f"loader rejected config: {result.reason}"]
    return []


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

    try:
        changed = apply(data)
    except ValueError as exc:
        print(f"error: {exc} — nothing written.", file=sys.stderr)
        return 2

    problems = verify(data)
    if problems:
        print("error: post-conditions unmet after apply — nothing written:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    if not changed:
        print("[result] already applied — no changes written.")
        return 0

    loader_problems = _loader_errors(data)
    if loader_problems:
        print("error: led_config loader rejects the staged config — nothing written:", file=sys.stderr)
        for p in loader_problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    backup = path.with_name(f"{path.name}.backup_partg_{int(time.time())}")
    shutil.copy2(path, backup)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    reread = json.loads(path.read_text(encoding="utf-8"))
    problems = verify(reread)
    if problems:
        shutil.copy2(backup, path)
        print("error: written file failed re-verification — backup restored:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 3

    comet = reread["f2"]["drop_look_routing"]["COMET"]
    print(f"[result] applied — wrote {path} (backup {backup.name})")
    print(f"[after] COMET tier sizes {{'2': {len(comet['2'])}, '3': {len(comet['3'])}}}; "
          f"banks.default.drop {len(reread['banks']['default']['drop'])} looks, "
          f"post_drop {len(reread['banks']['default']['post_drop'])} looks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
