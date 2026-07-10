#!/usr/bin/env python3
"""Stage the AWR-197 speed/size law into an LED look-director config.

Operator order (2026-07-10): the per-section beat-speed convention and the
drop-BIG -> post_drop-SMALL comet pairing (palette comet 6 -> 2 is the
exemplar) stop living as scattered renderer defaults and become EXPLICIT
config params. This script mirrors the tracked example-config edits into the
LIVE config. STAGED ONLY: the bridge reads this file at start; nothing here
touches the running process.

What it writes (set-if-missing everywhere — a re-run never clobbers later
operator desk tuning of the look params):
  1. Explicit beat-speed params on the banks.default groove/breakdown/drop/
     post_drop realtime looks, at each look's CURRENT EFFECTIVE value (the
     renderer default it already rides, or its already-explicit value) — the
     render output is byte-identical. The only behavior delta: looks gaining
     travel_beats=2.0 extend the beat-sync engine's paused-flight expiry from
     1.25 to 2.25 beats (pause path only).
  2. Deletes the two DEAD legacy drop_pairs entries `rt_drop_chase` and
     `rt_drop_nebula` (live-only leftovers of the AWR-156 remnant rename; the
     example config deleted them then). Their drop looks are not in any bank,
     so the pairs can never fire — and both violate the width ordering law
     (drop width 0.8 implicit vs post_drop width 4).

Safety properties (CFIX2 precedent):
  - Structural anomalies (missing look / scene_ref mismatch) abort BEFORE any
    write.
  - The mutated config is validated through the real loader
    (led_config.load_led_look_director_config_from_dict) BEFORE any write.
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

# look name -> (expected scene_ref, {param: law value})
# Values are each look's current effective value — see the AWR-197 paragraph
# in docs/subsystems/led_govee.md for the per-look provenance.
SPEED_PARAMS: dict[str, tuple[str, dict[str, float]]] = {
    "rt_groove_chase": ("rt_groove_chase", {"loop_beats": 4.0}),
    "rt_groove_nebula": ("rt_groove_nebula", {"loop_beats": 4.0}),
    "rt_groove_center_chase": ("groove_center_chase", {"travel_beats": 1.0}),
    "rt_groove_center_burst_retract": (
        "groove_center_burst_retract", {"burst_beats": 1.0}),
    "rt_breakdown_full_breathing": (
        "breakdown_full_breathing", {"breath_beats": 8.0, "drift_beats": 32.0}),
    "rt_post_drop_chase": ("rt_post_drop_chase", {"travel_beats": 2.0}),
    "rt_post_drop_nebula": ("rt_post_drop_nebula", {"travel_beats": 2.0}),
    "rt_post_drop_firework_chase": (
        "post_drop_firework_chase", {"travel_beats": 1.0}),
    "rt_post_drop_remnant_chase": ("rt_drop_chase", {"travel_beats": 2.0}),
    "rt_post_drop_remnant_nebula": ("rt_drop_nebula", {"travel_beats": 2.0}),
    "rt_rainbow_post_drop": ("rainbow_ordered", {"loop_beats": 4.0}),
    "rt_post_drop_palette_comet": ("palette_comet", {"loop_beats": 4.0}),
}

# Dead legacy pairs to delete (drop side absent from every bank -> never
# fires; width-ordering violators). Deleted only if the drop look is really
# absent from banks.default at run time — checked, not assumed.
DEAD_PAIRS = ("rt_drop_chase", "rt_drop_nebula")


def apply(data: dict) -> bool:
    """Mutate data in place, set-if-missing only. Returns True if anything
    changed. Raises ValueError (before any meaningful mutation) when the
    config doesn't look like the one this script was written against."""
    looks = data.get("looks")
    if not isinstance(looks, dict):
        raise ValueError("config has no looks{} object")
    pairs = data.get("drop_pairs")
    if not isinstance(pairs, dict):
        raise ValueError("drop_pairs missing")
    default_bank = data.get("banks", {}).get("default")
    if not isinstance(default_bank, dict):
        raise ValueError("banks.default missing")

    # Preconditions first — never half-apply.
    for name, (scene_ref, _) in SPEED_PARAMS.items():
        look = looks.get(name)
        if not isinstance(look, dict):
            raise ValueError(f"looks.{name} missing")
        if look.get("scene_ref") != scene_ref:
            raise ValueError(
                f"looks.{name} scene_ref={look.get('scene_ref')!r} != "
                f"expected {scene_ref!r} — config drifted, refusing")
        if look.get("params") is not None and not isinstance(look.get("params"), dict):
            raise ValueError(f"looks.{name}.params is not an object")
    banked = {n for role in default_bank.values() if isinstance(role, list) for n in role}
    for pair_name in DEAD_PAIRS:
        if pair_name in pairs and pair_name in banked:
            raise ValueError(
                f"drop_pairs.{pair_name} is banked — not dead, refusing to delete")

    changed = False
    for name, (_, wanted) in SPEED_PARAMS.items():
        params = looks[name].setdefault("params", {})
        if looks[name]["params"] is None:
            looks[name]["params"] = params = {}
        for key, value in wanted.items():
            if key not in params:
                params[key] = value
                changed = True
    for pair_name in DEAD_PAIRS:
        if pair_name in pairs:
            del pairs[pair_name]
            changed = True
    return changed


def verify(data: dict) -> list[str]:
    """Post-conditions on a config dict. Empty list == staged correctly."""
    problems: list[str] = []
    looks = data.get("looks", {})
    for name, (_, wanted) in SPEED_PARAMS.items():
        params = (looks.get(name) or {}).get("params") or {}
        for key in wanted:
            if key not in params:
                problems.append(f"looks.{name}.params.{key} missing")
    for pair_name in DEAD_PAIRS:
        if pair_name in data.get("drop_pairs", {}):
            problems.append(f"drop_pairs.{pair_name} still present")
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

    backup = path.with_name(f"{path.name}.backup_awr197_{int(time.time())}")
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

    touched = sum(len(w) for _, w in SPEED_PARAMS.values())
    print(f"[result] applied — wrote {path} (backup {backup.name})")
    print(f"[after] {len(SPEED_PARAMS)} looks carry explicit speed params "
          f"({touched} keys set-if-missing); dead pairs removed: "
          f"{[p for p in DEAD_PAIRS if p not in reread.get('drop_pairs', {})]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
