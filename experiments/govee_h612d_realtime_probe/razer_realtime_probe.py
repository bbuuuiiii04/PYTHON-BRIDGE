#!/usr/bin/env python3
"""Govee Razer/DreamView realtime protocol probe.

Sends undocumented razer-style UDP commands to control individual
segments on a Govee RGBICW strip in realtime.

Protocol derived from LedFx's Govee backend (reverse-engineered).

Packet format:
  [header(5 bytes)] [segment_count(1 byte)] [R,G,B × segments] [XOR checksum(1 byte)]

  header variants:
    dreams: BB 00 FA B0 00   (original DreamView capture)
    chroma: BB 00 0E B0 00   (Razer Chroma capture)
    govee:  BB 00 20 B0 00   (Govee Desktop DreamView)

  Activate:  BB 00 01 B1 01 0A   → base64: "uwABsQEK"
  Deactivate: BB 00 01 B1 00 0B  → base64: "uwABsQAL"

Encoded packet is sent as JSON:
  {"msg":{"cmd":"razer","data":{"pt":"<base64>"}}}
  via UDP to ip:4003

Usage:
    python razer_realtime_probe.py --ip 192.168.x.x
    python razer_realtime_probe.py --ip 192.168.x.x --segments 20
    python razer_realtime_probe.py --ip 192.168.x.x --header chroma
    python razer_realtime_probe.py --ip 192.168.x.x --header all
    python razer_realtime_probe.py --ip 192.168.x.x --test chase
    python razer_realtime_probe.py --ip 192.168.x.x --test all
"""
from __future__ import annotations

import argparse
import base64
import json
import socket
import sys
import time
from typing import Sequence


CONTROL_PORT = 4003

# ── Header variants ──────────────────────────────────────────────────────────
HEADERS = {
    "dreams": [0xBB, 0x00, 0xFA, 0xB0, 0x00],
    "chroma": [0xBB, 0x00, 0x0E, 0xB0, 0x00],
    "govee":  [0xBB, 0x00, 0x20, 0xB0, 0x00],
}

# ── Activate / Deactivate packets ────────────────────────────────────────────
# BB 00 01 B1 01 0A → activate razer mode
ACTIVATE_PT = "uwABsQEK"
# BB 00 01 B1 00 0B → deactivate razer mode
DEACTIVATE_PT = "uwABsQAL"


def xor_checksum(data: bytes | list[int]) -> int:
    """Compute XOR checksum over all bytes."""
    result = 0
    for b in data:
        result ^= b
    return result


def build_frame_packet(
    header: list[int],
    segments: list[tuple[int, int, int]],
) -> bytes:
    """Build a razer frame packet.

    Format: header(5) + segment_count(1) + R,G,B*N + checksum(1)
    """
    seg_count = len(segments)
    packet = list(header) + [seg_count]

    for r, g, b in segments:
        packet.extend([r & 0xFF, g & 0xFF, b & 0xFF])

    chk = xor_checksum(packet)
    packet.append(chk)

    return bytes(packet)


def encode_packet(packet: bytes) -> str:
    """Base64-encode a binary packet."""
    return base64.b64encode(packet).decode("utf-8")


def send_razer_cmd(sock: socket.socket, ip: str, pt: str) -> None:
    """Send a razer JSON command with the given base64 payload."""
    msg = {"msg": {"cmd": "razer", "data": {"pt": pt}}}
    data = json.dumps(msg).encode("utf-8")
    sock.sendto(data, (ip, CONTROL_PORT))


def send_frame(
    sock: socket.socket,
    ip: str,
    header: list[int],
    segments: list[tuple[int, int, int]],
) -> None:
    """Build, encode, and send one frame."""
    packet = build_frame_packet(header, segments)
    encoded = encode_packet(packet)
    send_razer_cmd(sock, ip, encoded)


def log_packet_hex(label: str, packet: bytes) -> None:
    """Print packet bytes in hex for debugging."""
    hex_str = " ".join(f"{b:02X}" for b in packet)
    b64 = base64.b64encode(packet).decode()
    print(f"  [{label}] hex: {hex_str}")
    print(f"  [{label}] b64: {b64}")


# ── Test patterns ────────────────────────────────────────────────────────────

def test_solid_color(
    sock: socket.socket,
    ip: str,
    header: list[int],
    num_segments: int,
    r: int, g: int, b: int,
    label: str,
    hold_s: float = 1.5,
) -> None:
    """Set all segments to a solid color and hold."""
    print(f"  → Solid {label}: ({r}, {g}, {b}) × {num_segments} segments")
    segments = [(r, g, b)] * num_segments

    # Log first packet for debugging
    packet = build_frame_packet(header, segments)
    log_packet_hex(label, packet)

    send_frame(sock, ip, header, segments)
    time.sleep(hold_s)


def test_chase(
    sock: socket.socket,
    ip: str,
    header: list[int],
    num_segments: int,
    chase_color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int] = (0, 0, 30),
    cycles: int = 2,
    fps: float = 20,
) -> None:
    """Moving single-pixel chase across all segments."""
    print(f"  → Chase: {chase_color} on {bg_color}, {cycles} cycles, {fps} fps")
    frame_delay = 1.0 / fps

    for cycle in range(cycles):
        for i in range(num_segments):
            segments = [bg_color] * num_segments
            segments[i] = chase_color
            send_frame(sock, ip, header, segments)
            time.sleep(frame_delay)


def test_strobe(
    sock: socket.socket,
    ip: str,
    header: list[int],
    num_segments: int,
    color: tuple[int, int, int] = (255, 255, 255),
    flashes: int = 4,
    on_ms: float = 50,
    off_ms: float = 100,
) -> None:
    """Short strobe burst. Max 1-2 seconds total."""
    print(f"  → Strobe: {flashes} flashes, {on_ms}ms on / {off_ms}ms off")
    black = [(0, 0, 0)] * num_segments
    white = [color] * num_segments

    for _ in range(flashes):
        send_frame(sock, ip, header, white)
        time.sleep(on_ms / 1000.0)
        send_frame(sock, ip, header, black)
        time.sleep(off_ms / 1000.0)


def test_gradient(
    sock: socket.socket,
    ip: str,
    header: list[int],
    num_segments: int,
    hold_s: float = 2.0,
) -> None:
    """Rainbow gradient across all segments."""
    print(f"  → Rainbow gradient across {num_segments} segments")
    segments: list[tuple[int, int, int]] = []
    for i in range(num_segments):
        # Simple hue rotation: R→G→B across segments
        hue = i / max(num_segments - 1, 1)
        if hue < 1/3:
            t = hue * 3
            r, g, b = int(255 * (1 - t)), int(255 * t), 0
        elif hue < 2/3:
            t = (hue - 1/3) * 3
            r, g, b = 0, int(255 * (1 - t)), int(255 * t)
        else:
            t = (hue - 2/3) * 3
            r, g, b = int(255 * t), 0, int(255 * (1 - t))
        segments.append((r, g, b))

    packet = build_frame_packet(header, segments)
    log_packet_hex("gradient", packet)
    send_frame(sock, ip, header, segments)
    time.sleep(hold_s)


def test_dim_blue_rest(
    sock: socket.socket,
    ip: str,
    header: list[int],
    num_segments: int,
) -> None:
    """Set all segments to dim blue as a rest/idle frame."""
    print(f"  → Dim blue rest frame")
    segments = [(0, 0, 20)] * num_segments
    send_frame(sock, ip, header, segments)


# ── Main test runner ─────────────────────────────────────────────────────────

def run_tests(
    sock: socket.socket,
    ip: str,
    header_name: str,
    header: list[int],
    num_segments: int,
    tests: Sequence[str],
) -> dict[str, str]:
    """Run specified tests with a given header. Returns test→status dict."""
    header_hex = " ".join(f"{b:02X}" for b in header)
    print()
    print(f"╔{'═' * 58}╗")
    print(f"║  HEADER: {header_name:<10}  [{header_hex}]")
    print(f"║  SEGMENTS: {num_segments}")
    print(f"╚{'═' * 58}╝")

    results: dict[str, str] = {}

    # Activate razer mode
    print()
    print("  ▶ Activating razer mode...")
    activate_bytes = base64.b64decode(ACTIVATE_PT)
    log_packet_hex("activate", activate_bytes)
    send_razer_cmd(sock, ip, ACTIVATE_PT)
    time.sleep(0.3)

    # Set brightness to 100
    brightness_msg = {"msg": {"cmd": "brightness", "data": {"value": 100}}}
    data = json.dumps(brightness_msg).encode("utf-8")
    sock.sendto(data, (ip, CONTROL_PORT))
    time.sleep(0.2)

    try:
        for test in tests:
            print()
            print(f"  ── TEST: {test} ──")

            try:
                if test == "red":
                    test_solid_color(sock, ip, header, num_segments, 255, 0, 0, "RED")
                    results[test] = "SENT"

                elif test == "green":
                    test_solid_color(sock, ip, header, num_segments, 0, 255, 0, "GREEN")
                    results[test] = "SENT"

                elif test == "blue":
                    test_solid_color(sock, ip, header, num_segments, 0, 0, 255, "BLUE")
                    results[test] = "SENT"

                elif test == "chase":
                    test_chase(sock, ip, header, num_segments)
                    results[test] = "SENT"

                elif test == "strobe":
                    test_strobe(sock, ip, header, num_segments)
                    results[test] = "SENT"

                elif test == "gradient":
                    test_gradient(sock, ip, header, num_segments)
                    results[test] = "SENT"

                elif test == "rest":
                    test_dim_blue_rest(sock, ip, header, num_segments)
                    results[test] = "SENT"

                else:
                    print(f"  ✗ Unknown test: {test}")
                    results[test] = "UNKNOWN"
                    continue

                print(f"  ✓ {test}: frames sent (check strip visually!)")

            except Exception as exc:
                print(f"  ✗ {test}: {exc}")
                results[test] = f"ERROR: {exc}"

            # Small gap between tests
            time.sleep(0.3)

    finally:
        # Dim blue rest frame before deactivating
        print()
        print("  ▶ Sending dim blue rest frame...")
        test_dim_blue_rest(sock, ip, header, num_segments)
        time.sleep(0.5)

        # Deactivate razer mode
        print("  ▶ Deactivating razer mode...")
        deactivate_bytes = base64.b64decode(DEACTIVATE_PT)
        log_packet_hex("deactivate", deactivate_bytes)
        send_razer_cmd(sock, ip, DEACTIVATE_PT)
        time.sleep(0.3)

    return results


ALL_TESTS = ["red", "green", "blue", "chase", "strobe", "gradient", "rest"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Govee Razer/DreamView realtime protocol probe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ip", required=True, help="Device IP address")
    parser.add_argument("--segments", type=int, default=20, help="Number of segments (default: 20)")
    parser.add_argument(
        "--header",
        choices=["dreams", "chroma", "govee", "all"],
        default="dreams",
        help="Header variant to use (default: dreams)",
    )
    parser.add_argument(
        "--test",
        choices=ALL_TESTS + ["all"],
        default="all",
        help="Which test(s) to run (default: all)",
    )
    parser.add_argument(
        "--stretch",
        action="store_true",
        help="Set header byte 4 to 0x01 (stretch mode)",
    )
    args = parser.parse_args()

    tests = ALL_TESTS if args.test == "all" else [args.test]
    headers_to_try = (
        list(HEADERS.keys()) if args.header == "all" else [args.header]
    )

    print("=" * 60)
    print("  GOVEE RAZER REALTIME PROTOCOL PROBE")
    print(f"  Target: {args.ip}:{CONTROL_PORT}")
    print(f"  Segments: {args.segments}")
    print(f"  Header(s): {', '.join(headers_to_try)}")
    print(f"  Tests: {', '.join(tests)}")
    print(f"  Stretch: {args.stretch}")
    print("=" * 60)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    all_results: dict[str, dict[str, str]] = {}

    try:
        for header_name in headers_to_try:
            header = list(HEADERS[header_name])
            if args.stretch:
                header[4] = 0x01

            results = run_tests(sock, args.ip, header_name, header, args.segments, tests)
            all_results[header_name] = results

            # Pause between header variants
            if len(headers_to_try) > 1:
                time.sleep(1.0)

    finally:
        sock.close()

    # ── Final results table ──────────────────────────────────────────────
    print()
    print()
    print("=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    print()
    print(f"  {'Header':<10} {'Test':<12} {'Status':<30}")
    print(f"  {'─'*10} {'─'*12} {'─'*30}")
    for header_name, results in all_results.items():
        for test_name, status in results.items():
            print(f"  {header_name:<10} {test_name:<12} {status:<30}")
    print()
    print("=" * 60)
    print()
    print("  ⚠  These tests send frames but cannot self-verify.")
    print("  ⚠  You must visually confirm if the strip responded.")
    print()
    print("  Questions to answer:")
    print("    1. Did you see RED, GREEN, BLUE solid colors?")
    print("    2. Did the white chase move across the strip?")
    print("    3. Did the strobe flash?")
    print("    4. Did the rainbow gradient appear?")
    print("    5. Which header worked (dreams/chroma/govee)?")
    print()
    print("  If nothing happened:")
    print("    - Try: --header all")
    print("    - Try: --segments 15  (or other counts)")
    print("    - Try: --stretch")
    print("    - Ensure Govee Desktop app is closed")
    print("    - Ensure LAN Control is enabled in Govee app")
    print()

    sys.exit(0)


if __name__ == "__main__":
    main()
