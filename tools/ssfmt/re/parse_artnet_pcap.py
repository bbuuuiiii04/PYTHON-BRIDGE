#!/usr/bin/env python3
"""Read-only ArtDmx decoder for classic pcap captures."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ARTNET_HEADER = b"Art-Net\x00"


def read_pcap(path: Path) -> tuple[int, list[tuple[float, bytes]]]:
    data = path.read_bytes()
    if len(data) < 24:
        raise ValueError("pcap is shorter than its global header")
    magic = data[:4]
    formats = {
        b"\xd4\xc3\xb2\xa1": ("<", False),
        b"\x4d\x3c\xb2\xa1": ("<", True),
        b"\xa1\xb2\xc3\xd4": (">", False),
        b"\xa1\xb2\x3c\x4d": (">", True),
    }
    if magic not in formats:
        raise ValueError(f"unsupported pcap magic {magic.hex()}")
    endian, nanoseconds = formats[magic]
    network = struct.unpack_from(endian + "I", data, 20)[0]
    packets = []
    offset = 24
    while offset + 16 <= len(data):
        seconds, fraction, captured, _original = struct.unpack_from(
            endian + "IIII", data, offset
        )
        offset += 16
        if offset + captured > len(data):
            raise ValueError(f"truncated packet at byte {offset - 16}")
        raw = data[offset : offset + captured]
        offset += captured
        timestamp = seconds + fraction / (1e9 if nanoseconds else 1e6)
        packets.append((timestamp, raw))
    if offset != len(data):
        raise ValueError(f"unparsed pcap trailing bytes at byte {offset}")
    return network, packets


def l3_payload(network: int, raw: bytes) -> bytes:
    if network in (0, 108):
        return raw[4:]
    if network == 1:
        return raw[14:]
    return raw


def udp_payload(ip: bytes) -> bytes | None:
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 17:
        return None
    header_length = (ip[0] & 0xF) * 4
    udp = ip[header_length:]
    return udp[8:] if len(udp) >= 8 else None


def artdmx_frames(path: Path) -> list[dict]:
    network, packets = read_pcap(path)
    rows = []
    for packet_offset, (timestamp, raw) in enumerate(packets):
        payload = udp_payload(l3_payload(network, raw))
        if not payload or payload[:8] != ARTNET_HEADER or len(payload) < 18:
            continue
        if struct.unpack_from("<H", payload, 8)[0] != 0x5000:
            continue
        universe = payload[14] | payload[15] << 8
        length = struct.unpack_from(">H", payload, 16)[0]
        if 18 + length > len(payload):
            raise ValueError(f"truncated ArtDmx payload in packet {packet_offset}")
        rows.append(
            {
                "packet_index": packet_offset,
                "timestamp": timestamp,
                "universe": universe,
                "length": length,
                "dmx": payload[18 : 18 + length],
            }
        )
    return rows


def universe_frames(
    path: Path, universe: int = 0, channels: int = 19
) -> list[tuple[float, tuple[int, ...]]]:
    return [
        (
            row["timestamp"],
            tuple(row["dmx"][:channels].ljust(channels, b"\0")),
        )
        for row in artdmx_frames(path)
        if row["universe"] == universe
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    parser.add_argument("--universe", type=int)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    pcap_data = args.pcap.read_bytes()
    network, packets = read_pcap(args.pcap)
    rows = artdmx_frames(args.pcap)
    all_artdmx_count = len(rows)
    universe_counts: dict[int, int] = {}
    universe_nonzero_frame_counts: dict[int, int] = {}
    universe_nonzero_channels: dict[int, set[int]] = {}
    universe_states: dict[int, set[bytes]] = {}
    for row in rows:
        universe = row["universe"]
        universe_counts[universe] = universe_counts.get(universe, 0) + 1
        universe_states.setdefault(universe, set()).add(row["dmx"])
        if any(row["dmx"]):
            universe_nonzero_frame_counts[universe] = (
                universe_nonzero_frame_counts.get(universe, 0) + 1
            )
        universe_nonzero_channels.setdefault(universe, set()).update(
            index for index, value in enumerate(row["dmx"], start=1) if value
        )
    if args.universe is not None:
        rows = [row for row in rows if row["universe"] == args.universe]
    previous: dict[int, bytes] = {}
    output = []
    for row in rows:
        dmx = row["dmx"]
        if not args.all and previous.get(row["universe"]) == dmx:
            continue
        output.append(
            {
                **{key: value for key, value in row.items() if key != "dmx"},
                "dmx": {str(index + 1): value for index, value in enumerate(dmx) if value},
            }
        )
        previous[row["universe"]] = dmx
    print(
        json.dumps(
            {
                "path": str(args.pcap),
                "status": "parsed",
                "size": len(pcap_data),
                "sha256": hashlib.sha256(pcap_data).hexdigest(),
                "version": "classic-pcap",
                "pcap_magic_hex": pcap_data[:4].hex(),
                "link_type": network,
                "packet_count": len(packets),
                "artdmx_frame_count": all_artdmx_count,
                "universe_frame_counts": {
                    str(universe): count for universe, count in sorted(universe_counts.items())
                },
                "universe_nonzero_frame_counts": {
                    str(universe): universe_nonzero_frame_counts.get(universe, 0)
                    for universe in sorted(universe_counts)
                },
                "universe_unique_state_counts": {
                    str(universe): len(universe_states[universe])
                    for universe in sorted(universe_counts)
                },
                "universe_nonzero_channels": {
                    str(universe): sorted(universe_nonzero_channels[universe])
                    for universe in sorted(universe_counts)
                },
                "filtered_universe": args.universe,
                "reported_frame_count": len(output),
                "unsupported_reason": None,
                "frames": output,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
