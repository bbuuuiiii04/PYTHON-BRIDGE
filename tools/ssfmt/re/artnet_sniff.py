#!/usr/bin/env python3
"""Historical passive ArtDmx listener restored from surviving pyc.

This binds a live UDP port and is therefore operator-owned.  Agents must not run
it.  It never sends packets, but current capture guidance prefers operator-run
``tcpdump`` and offline ``parse_artnet_pcap.py``.
"""
from __future__ import annotations

import json
import socket
import struct
import sys
import time


OUT = "/tmp/ss_re/artnet_capture.jsonl"
HDR = b"Art-Net\0"


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind(("", 6454))
    except OSError as error:
        print(f"[artnet] BIND FAIL on 6454: {error}", flush=True)
        sys.exit(2)
    sock.settimeout(2.0)
    print("[artnet] listening on 0.0.0.0:6454 (passive)", flush=True)

    last: dict[int, bytes] = {}
    frames = changes = 0
    status_time = time.time()
    with open(OUT, "a") as output:
        while True:
            try:
                packet, source = sock.recvfrom(2048)
            except socket.timeout:
                packet = None
                source = ("", 0)
            now = time.time()
            if packet and packet[:8] == HDR:
                opcode = struct.unpack_from("<H", packet, 8)[0]
                if opcode == 0x5000 and len(packet) >= 18:
                    frames += 1
                    universe = (packet[15] << 8) | packet[14]
                    length = struct.unpack_from(">H", packet, 16)[0]
                    data = packet[18 : 18 + length]
                    if last.get(universe) != data:
                        changes += 1
                        nonzero = {
                            index: byte
                            for index, byte in enumerate(data, start=1)
                            if byte
                        }
                        difference = []
                        previous = last.get(universe)
                        if previous is not None:
                            for index in range(max(len(previous), len(data))):
                                before = previous[index] if index < len(previous) else 0
                                after = data[index] if index < len(data) else 0
                                if before != after:
                                    difference.append([index + 1, before, after])
                        record = {
                            "ts": round(now, 3),
                            "src": source[0],
                            "uni": universe,
                            "len": length,
                            "nonzero": nonzero,
                            "changed": difference[:64],
                        }
                        output.write(json.dumps(record) + "\n")
                        output.flush()
                        last[universe] = data
            if now - status_time >= 1.0:
                print(
                    f"[artnet] t={time.strftime('%H:%M:%S')} frames={frames} "
                    f"changes={changes} universes={sorted(last)}",
                    flush=True,
                )
                status_time = now


if __name__ == "__main__":
    main()
