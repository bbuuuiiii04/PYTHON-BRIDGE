#!/usr/bin/env python3
"""Idempotently stage the AWR-187 firework redesign into an LED look-director
config (CFIX2/apply_gentle_drop_routing precedent).

Exactly ONE look is touched: looks.rt_drop_firework_explosion —
  scene_ref     -> drop_firework_explosion_2  (the redesigned strobing effect)
  allow_strobe  -> true   (v2 registers as a strobe; C5 validation requires it)
  color_source  -> engine (explosion hues come from the injected palette tints)
  params        -> the desk-tunable redesign defaults (quicker surge, much
                   lower hold, denser + shorter-lived embers, hz/duty strobe
                   knobs; spark/tint colors kept from v1)

No other key anywhere in the config is read or written. The script refuses to
write (exit 3) if safety.allow_strobe is not already true — flipping the look
to a strobe under a strobe-forbidding safety block would fail config
validation and take ALL LED down at the next bridge start.

Atomic write + backup: the previous content is copied to
<config>.pre_awr187.bak once (first run only), then the new JSON is written to
a temp file in the same directory and os.replace()d over the target.

Idempotent: a second run detects the look already matches and writes nothing.

DEFAULT TARGET IS THE LIVE CONFIG. Do not run this against the live config
yourself — the executive runs it at the gate, BEFORE the next bridge start
(the pre-apply look still points at v1, which stays registered and valid).
For tests / dry checks pass --config <path> at a fixture copy.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "led_look_director.json"

LOOK_NAME = "rt_drop_firework_explosion"

# The exact post-apply look fields (mirrors config/led_look_director.example.json).
TARGET_FIELDS = {
    "scene_ref": "drop_firework_explosion_2",
    "allow_strobe": True,
    "color_source": "engine",
    "params": {
        "color_a": [255, 240, 220],
        "color_b": [255, 170, 60],
        "spark_a": [255, 170, 60],
        "spark_b": [255, 240, 220],
        "surge_beats": 0.25,
        "bg_hold": 0.25,
        "sparkle_density": 0.5,
        "sparkle_size": 1.0,
        "sparkle_life_s": 0.15,
        "hz": 6.0,
        "duty": 0.3,
    },
}


def apply(data: dict) -> bool:
    """Mutate data in place — the one firework look, nothing else.

    Returns True if anything changed, False if already at target (no-op).
    Raises KeyError if the look is missing (wrong config file).
    """
    look = data["looks"][LOOK_NAME]
    changed = any(look.get(k) != v for k, v in TARGET_FIELDS.items())
    if changed:
        look.update(json.loads(json.dumps(TARGET_FIELDS)))  # fresh copies
    return changed


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

    if not bool(data.get("safety", {}).get("allow_strobe", False)):
        print(
            "error: safety.allow_strobe is not true — refusing to flip the look "
            "to a strobe (config validation would reject it and take all LED "
            "down at the next bridge start). Nothing written.",
            file=sys.stderr,
        )
        return 3
    if LOOK_NAME not in data.get("looks", {}):
        print(f"error: look '{LOOK_NAME}' not in this config. Nothing written.", file=sys.stderr)
        return 2

    before = data["looks"][LOOK_NAME]
    print(f"[before] {LOOK_NAME}: scene_ref={before.get('scene_ref')} "
          f"allow_strobe={before.get('allow_strobe')} color_source={before.get('color_source')}")

    changed = apply(data)
    if not changed:
        print("[result] already applied — no changes written.")
        return 0

    backup = path.with_name(path.name + ".pre_awr187.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"[backup] wrote {backup}")

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    after = data["looks"][LOOK_NAME]
    print(f"[after]  {LOOK_NAME}: scene_ref={after.get('scene_ref')} "
          f"allow_strobe={after.get('allow_strobe')} color_source={after.get('color_source')} "
          f"params={json.dumps(after.get('params'))}")
    print(f"[result] applied — wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
