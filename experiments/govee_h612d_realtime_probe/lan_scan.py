#!/usr/bin/env python3
"""Govee LAN device scanner.

Sends a multicast scan command to 239.255.255.250:4001
and listens on UDP 4002 for device responses.
Prints discovered Govee devices: ip, device, sku, firmware versions.

Usage:
    python lan_scan.py [--timeout 5]
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time


MULTICAST_GROUP = "239.255.255.250"
SCAN_PORT = 4001
RECV_PORT = 4002

SCAN_MESSAGE = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode("utf-8")


def scan(timeout_s: float = 5.0) -> list[dict]:
    """Send multicast scan and collect responses."""
    # Create a UDP socket for receiving responses
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    recv_sock.bind(("", RECV_PORT))

    # Join multicast group on all interfaces
    mreq = struct.pack("4s4s", socket.inet_aton(MULTICAST_GROUP), socket.inet_aton("0.0.0.0"))
    recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    recv_sock.settimeout(1.0)

    # Create a separate socket for sending the scan command
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    print(f"[SCAN] Sending multicast scan to {MULTICAST_GROUP}:{SCAN_PORT}")
    print(f"[SCAN] Listening on UDP :{RECV_PORT} for {timeout_s}s")
    print(f"[SCAN] Payload: {SCAN_MESSAGE.decode()}")
    print()

    send_sock.sendto(SCAN_MESSAGE, (MULTICAST_GROUP, SCAN_PORT))

    devices: list[dict] = []
    seen_ips: set[str] = set()
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        try:
            data, addr = recv_sock.recvfrom(4096)
        except socket.timeout:
            continue

        ip = addr[0]
        if ip in seen_ips:
            continue
        seen_ips.add(ip)

        try:
            payload = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"[SCAN] Non-JSON response from {ip}: {exc}")
            continue

        msg = payload.get("msg", {})
        cmd = msg.get("cmd", "")
        msg_data = msg.get("data", {})

        device_info = {
            "ip": ip,
            "cmd": cmd,
            "device": msg_data.get("device", ""),
            "sku": msg_data.get("sku", ""),
            "ble_version_hard": msg_data.get("bleVersionHard", ""),
            "ble_version_soft": msg_data.get("bleVersionSoft", ""),
            "wifi_version_hard": msg_data.get("wifiVersionHard", ""),
            "wifi_version_soft": msg_data.get("wifiVersionSoft", ""),
            "raw": payload,
        }
        devices.append(device_info)

        print(f"  ╔══════════════════════════════════════════════")
        print(f"  ║ DEVICE FOUND")
        print(f"  ╠══════════════════════════════════════════════")
        print(f"  ║ IP:                {ip}")
        print(f"  ║ Device ID:         {device_info['device']}")
        print(f"  ║ SKU:               {device_info['sku']}")
        print(f"  ║ BLE HW Version:    {device_info['ble_version_hard']}")
        print(f"  ║ BLE SW Version:    {device_info['ble_version_soft']}")
        print(f"  ║ WiFi HW Version:   {device_info['wifi_version_hard']}")
        print(f"  ║ WiFi SW Version:   {device_info['wifi_version_soft']}")
        print(f"  ╚══════════════════════════════════════════════")
        print()

    send_sock.close()
    recv_sock.close()

    return devices


def main() -> None:
    parser = argparse.ArgumentParser(description="Govee LAN device scanner")
    parser.add_argument("--timeout", type=float, default=5.0, help="Scan timeout in seconds (default: 5)")
    args = parser.parse_args()

    print("=" * 60)
    print("  GOVEE LAN SCANNER")
    print("=" * 60)
    print()

    devices = scan(timeout_s=args.timeout)

    print()
    print("=" * 60)
    print(f"  SCAN COMPLETE: {len(devices)} device(s) found")
    print("=" * 60)

    if not devices:
        print()
        print("  [!] No devices found.")
        print("  [!] Check that:")
        print("  [!]   1. LAN Control is enabled in the Govee app")
        print("  [!]   2. Your device is on the same subnet")
        print("  [!]   3. Multicast is not blocked by your router/firewall")
        print("  [!]   4. Govee Desktop app is not running (can lock the device)")
        sys.exit(1)

    # Dump raw JSON for each device
    print()
    print("--- RAW RESPONSES ---")
    for d in devices:
        print(json.dumps(d["raw"], indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
