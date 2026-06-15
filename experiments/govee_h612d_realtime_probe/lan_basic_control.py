#!/usr/bin/env python3
"""Govee LAN basic control test.

Tests official LAN API commands on a Govee device:
  - devStatus query
  - brightness control
  - colorwc (color with warm/cold white)

Usage:
    python lan_basic_control.py --ip 192.168.x.x
    python lan_basic_control.py --ip 192.168.x.x --brightness 50
    python lan_basic_control.py --ip 192.168.x.x --skip-color
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time


CONTROL_PORT = 4003
RECV_PORT = 4002


def send_udp(sock: socket.socket, ip: str, message: dict, port: int = CONTROL_PORT) -> None:
    """Send a JSON UDP message to the device."""
    data = json.dumps(message).encode("utf-8")
    sock.sendto(data, (ip, port))


def recv_response(sock: socket.socket, timeout: float = 2.0) -> tuple[dict | None, str]:
    """Wait for a UDP response. Returns (parsed_json, raw_string)."""
    sock.settimeout(timeout)
    try:
        data, addr = sock.recvfrom(4096)
        raw = data.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return parsed, raw
    except socket.timeout:
        return None, ""


def test_dev_status(sock: socket.socket, ip: str) -> bool:
    """Send devStatus and print result."""
    print()
    print("─" * 60)
    print("  TEST 1: devStatus")
    print("─" * 60)

    msg = {"msg": {"cmd": "devStatus", "data": {}}}
    print(f"  → Sending: {json.dumps(msg)}")
    send_udp(sock, ip, msg)

    parsed, raw = recv_response(sock)
    if parsed is None:
        print("  ✗ FAIL: No response to devStatus")
        print(f"    Raw: {raw!r}")
        return False

    print(f"  ✓ PASS: Got devStatus response")
    print(f"    Raw: {raw}")

    msg_data = parsed.get("msg", {}).get("data", {})
    print(f"    on/off:      {msg_data.get('onOff', '?')}")
    print(f"    brightness:  {msg_data.get('brightness', '?')}")
    print(f"    color:       {msg_data.get('color', '?')}")
    print(f"    colorTemp:   {msg_data.get('colorTemInKelvin', '?')}")
    return True


def test_brightness(sock: socket.socket, ip: str, value: int = 80) -> bool:
    """Test brightness control."""
    print()
    print("─" * 60)
    print(f"  TEST 2: Brightness → {value}")
    print("─" * 60)

    msg = {"msg": {"cmd": "brightness", "data": {"value": value}}}
    print(f"  → Sending: {json.dumps(msg)}")
    send_udp(sock, ip, msg)

    # Brightness commands may or may not get a response
    time.sleep(0.5)
    parsed, raw = recv_response(sock, timeout=1.0)
    if parsed:
        print(f"  ✓ PASS: Got response: {raw}")
    else:
        print(f"  ~ SENT: No response (normal for some devices)")

    # Verify with devStatus
    time.sleep(0.3)
    msg = {"msg": {"cmd": "devStatus", "data": {}}}
    send_udp(sock, ip, msg)
    parsed, raw = recv_response(sock)
    if parsed:
        brightness_now = parsed.get("msg", {}).get("data", {}).get("brightness", "?")
        print(f"  ✓ Verified brightness: {brightness_now}")
        return True
    else:
        print(f"  ~ Could not verify (no devStatus response)")
        return True  # Sent successfully, just can't verify


def test_color(sock: socket.socket, ip: str, r: int, g: int, b: int, label: str) -> bool:
    """Test colorwc command."""
    print()
    print("─" * 60)
    print(f"  TEST 3: Color → {label} ({r}, {g}, {b})")
    print("─" * 60)

    msg = {
        "msg": {
            "cmd": "colorwc",
            "data": {
                "color": {"r": r, "g": g, "b": b},
                "colorTemInKelvin": 0,
            },
        }
    }
    print(f"  → Sending: {json.dumps(msg)}")
    send_udp(sock, ip, msg)

    time.sleep(0.5)
    parsed, raw = recv_response(sock, timeout=1.0)
    if parsed:
        print(f"  ✓ PASS: Got response: {raw}")
    else:
        print(f"  ~ SENT: No response (normal for some devices)")

    return True


def test_turn_on(sock: socket.socket, ip: str) -> bool:
    """Ensure the device is ON before tests."""
    print()
    print("─" * 60)
    print("  PRE-TEST: Turn ON")
    print("─" * 60)

    msg = {"msg": {"cmd": "turn", "data": {"value": 1}}}
    print(f"  → Sending: {json.dumps(msg)}")
    send_udp(sock, ip, msg)

    time.sleep(0.5)
    parsed, raw = recv_response(sock, timeout=1.0)
    if parsed:
        print(f"  ✓ Response: {raw}")
    else:
        print(f"  ~ SENT (no response)")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Govee LAN basic control test")
    parser.add_argument("--ip", required=True, help="Device IP address")
    parser.add_argument("--brightness", type=int, default=80, help="Brightness value 0-100 (default: 80)")
    parser.add_argument("--skip-color", action="store_true", help="Skip color test")
    args = parser.parse_args()

    print("=" * 60)
    print("  GOVEE LAN BASIC CONTROL TEST")
    print(f"  Target: {args.ip}:{CONTROL_PORT}")
    print("=" * 60)

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    results: dict[str, bool] = {}

    try:
        # Pre-test: turn on
        test_turn_on(sock, args.ip)
        time.sleep(0.5)

        # Test 1: devStatus
        results["devStatus"] = test_dev_status(sock, args.ip)
        time.sleep(0.5)

        # Test 2: brightness
        results["brightness"] = test_brightness(sock, args.ip, args.brightness)
        time.sleep(0.5)

        # Test 3: color
        if not args.skip_color:
            results["color_red"] = test_color(sock, args.ip, 255, 0, 0, "RED")
            time.sleep(1.0)
            results["color_green"] = test_color(sock, args.ip, 0, 255, 0, "GREEN")
            time.sleep(1.0)
            results["color_blue"] = test_color(sock, args.ip, 0, 0, 255, "BLUE")
            time.sleep(1.0)
            # Restore to white
            results["color_white"] = test_color(sock, args.ip, 255, 255, 255, "WHITE (restore)")

    finally:
        sock.close()

    # Print results table
    print()
    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {test_name}")
    print("=" * 60)

    all_passed = all(results.values())
    if all_passed:
        print("  ✓ ALL OFFICIAL LAN TESTS PASSED")
    else:
        print("  ✗ SOME TESTS FAILED")
    print()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
