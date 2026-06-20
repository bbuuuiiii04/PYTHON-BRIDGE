#!/usr/bin/env python3
"""Historical Stage-1 bridge-MIDI/AppLog correlator restored from pyc.

Read-only.  Current validation uses ``validate_autoloop_capture.py``.
"""
from __future__ import annotations

import argparse
import re
from bisect import bisect_right
from collections import defaultdict


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def t2s(hms: str) -> float:
    hour, minute, second = hms.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(second)


def parse_bridge(path: str) -> list[tuple[float, str, str, str, str]]:
    fires = []
    pattern = re.compile(
        r"(\d\d:\d\d:\d\d\.\d+).*\[LX\]\s+"
        r"(fired|blackout_on sent|mask_on)\s+(.*)"
    )
    for line in open(path, errors="replace"):
        line = ANSI.sub("", line)
        match = pattern.search(line)
        if not match:
            continue
        rest = match.group(3)
        scene = (re.search(r"scene=(\S+)", rest) or [None, ""])[1]
        role = (re.search(r"role=(\S+)", rest) or [None, ""])[1]
        note = (re.search(r"note=(\d+)", rest) or [None, ""])[1]
        fires.append((t2s(match.group(1)), match.group(2), role, scene, note))
    return sorted(fires)


def parse_applog(paths: list[str]) -> list[tuple[float, int, int]]:
    changes = []
    pattern = re.compile(
        r"(\d\d:\d\d:\d\d\.\d+)\].*Deck (\d) "
        r"running autoloop bank -1, index (\d+)"
    )
    for path in paths:
        for line in open(path, errors="replace"):
            match = pattern.search(line)
            if match:
                changes.append(
                    (t2s(match.group(1)), int(match.group(2)), int(match.group(3)))
                )
    return sorted(changes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_logs", nargs="+")
    parser.add_argument("--bridge-log", default="/tmp/bridge.log")
    args = parser.parse_args()
    bridge = parse_bridge(args.bridge_log)
    app_log = parse_applog(args.app_logs)
    times = [fire[0] for fire in bridge]
    print(f"# bridge_fires={len(bridge)}  applog_changes={len(app_log)}")
    scene_indices: dict[tuple[int, str, str], dict[int, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    paired = 0
    for timestamp, deck, index in app_log:
        position = bisect_right(times, timestamp) - 1
        if position < 0 or not 0 <= timestamp - times[position] <= 1.0:
            continue
        _time, _kind, role, scene, note = bridge[position]
        scene_indices[(deck, scene or role or "?", note)][index] += 1
        paired += 1
    print(f"# paired={paired}/{len(app_log)} (index change within 1s after a fire)")
    for (deck, scene, note), indices in sorted(scene_indices.items()):
        top = sorted(indices.items(), key=lambda item: -item[1])
        print(f"deck={deck}  scene={scene:24s} note={note:>3}  ->  indices {top}")


if __name__ == "__main__":
    main()
