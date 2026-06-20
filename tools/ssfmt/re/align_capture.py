#!/usr/bin/env python3
"""Historical Stage-1 pcap/AppLog alignment helper restored from pyc.

Read-only for its inputs.  It writes ``index_dmx_library.json`` beside the pcap,
so prefer the current validators for routine analysis.
"""
from __future__ import annotations

import bisect
import json
import os
import re
import struct
import sys
from collections import defaultdict
from datetime import datetime


ARTNET = b"Art-Net\0"


def pcap_frames(path: str) -> list[tuple[float, int, bytes]]:
    data = open(path, "rb").read()
    magic = data[:4]
    endian = "<" if magic[0] in (0xD4, 0x4D) else ">"
    nanoseconds = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    offset = 24
    output = []
    while offset + 16 <= len(data):
        seconds, fraction, captured, _original = struct.unpack_from(
            endian + "IIII", data, offset
        )
        offset += 16
        if offset + captured > len(data):
            break
        raw = data[offset : offset + captured]
        offset += captured
        timestamp = seconds + fraction / (1e9 if nanoseconds else 1e6)
        ip = raw[4:]
        if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 17:
            continue
        udp = ip[(ip[0] & 0xF) * 4 :]
        if len(udp) < 8:
            continue
        payload = udp[8:]
        if (
            payload[:8] != ARTNET
            or struct.unpack_from("<H", payload, 8)[0] != 0x5000
            or len(payload) < 18
        ):
            continue
        universe = (payload[15] << 8) | payload[14]
        length = struct.unpack_from(">H", payload, 16)[0]
        output.append((timestamp, universe, payload[18 : 18 + length]))
    return output


def applog(paths: list[str]) -> list[tuple[float, int, int]]:
    pattern = re.compile(
        r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\].*"
        r"Deck (\d) running autoloop bank -1, index (\d+)"
    )
    rows = []
    for path in paths:
        try:
            handle = open(path, errors="replace")
        except FileNotFoundError:
            continue
        for line in handle:
            match = pattern.search(line)
            if not match:
                continue
            timestamp = datetime.strptime(
                match.group(1), "%Y-%m-%d %H:%M:%S.%f"
            ).timestamp()
            rows.append((timestamp, int(match.group(2)), int(match.group(3))))
    return sorted(rows)


def hms(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def main() -> None:
    pcap = sys.argv[1]
    logs = sys.argv[2:]
    frames = pcap_frames(pcap)
    if not frames:
        print("NO FRAMES")
        return
    start, end = frames[0][0], frames[-1][0]
    span = end - start
    universes = sorted({universe for _ts, universe, _dmx in frames})
    print(
        f"# pcap frames={len(frames)}  span {hms(start)}..{hms(end)} "
        f"({span:.0f}s)  universes={universes}"
    )
    per_universe: dict[int, list[tuple[float, bytes]]] = defaultdict(list)
    for timestamp, universe, dmx in frames:
        per_universe[universe].append((timestamp, dmx))
    for universe in universes:
        fps = len(per_universe[universe]) / span if span else 0
        print(f"#   uni{universe}: {len(per_universe[universe])} frames (~{fps:.0f} fps)")
    for left, right in zip(universes, universes[1:]):
        pairs = zip(per_universe[left], per_universe[right])
        compared = [(a[1], b[1]) for a, b in pairs]
        same = sum(a == b for a, b in compared)
        verdict = "MIRROR (identical)" if compared and same == len(compared) else "DISTINCT content"
        print(f"# uni{left} vs uni{right}: {same}/{len(compared)} aligned frames identical -> {verdict}")

    events = [row for row in applog(logs) if start <= row[0] <= end]
    print(f"# AppLog index-changes in window={len(events)}  decks={sorted({row[1] for row in events})}")
    event_times = [row[0] for row in events]
    library = []
    for universe in universes:
        # The old helper treated the deck with the most temporally adjacent
        # changed frames as the provisional owner.
        deck_scores: dict[int, int] = defaultdict(int)
        previous = None
        change_times = []
        for timestamp, dmx in per_universe[universe]:
            if dmx != previous:
                change_times.append(timestamp)
                previous = dmx
        for timestamp, deck, _index in events:
            position = bisect.bisect_left(change_times, timestamp)
            nearby = [
                change_times[i]
                for i in (position - 1, position)
                if 0 <= i < len(change_times)
            ]
            if nearby and min(abs(value - timestamp) for value in nearby) <= 0.9:
                deck_scores[deck] += 1
        deck = max(deck_scores, key=deck_scores.get) if deck_scores else -1
        total = sum(deck_scores.values())
        confidence = 100.0 * deck_scores.get(deck, 0) / total if total else 0.0
        print(f"# uni{universe} look-switches -> best Deck {deck} ({confidence:.0f}% aligned)")
        selected_events = [row for row in events if row[1] == deck]
        index_rows: dict[int, list[tuple[float, bytes]]] = defaultdict(list)
        selected_times = [row[0] for row in selected_events]
        for timestamp, dmx in per_universe[universe]:
            position = bisect.bisect_right(selected_times, timestamp) - 1
            if position >= 0:
                index_rows[selected_events[position][2]].append((timestamp, dmx))
        print(f"\n## Universe {universe} (Deck {deck}) — per-index coverage [{len(index_rows)} indices]")
        for index, rows in sorted(index_rows.items()):
            seconds = rows[-1][0] - rows[0][0] if len(rows) > 1 else 0.0
            print(f"   index {index:3d} {len(rows):5d} frames  ~{seconds:5.1f}s")
            library.append(
                {
                    "uni": universe,
                    "deck": deck,
                    "index": index,
                    "frames": len(rows),
                    "secs": round(seconds, 3),
                    "sample_dmx": list(rows[0][1]),
                }
            )
    output = os.path.join(os.path.dirname(os.path.abspath(pcap)), "index_dmx_library.json")
    with open(output, "w") as handle:
        json.dump(library, handle, indent=2, sort_keys=True)
    print(f"\n# wrote {output} ({len(library)} entries)")


if __name__ == "__main__":
    main()
