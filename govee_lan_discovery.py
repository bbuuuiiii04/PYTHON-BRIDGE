"""Govee LAN multicast discovery for resolving the realtime device IP at startup.

The realtime DreamView/Razer transport targets a hardcoded ``ip`` in
``led_look_director.json``. Govee strips take DHCP leases, so that IP drifts
whenever the device reboots or the lease rolls over, and every realtime frame
then fails with ``send_error:OSError`` (host unreachable) -- the strip goes dark
with no obvious cause.

This module sends the Govee multicast scan (``239.255.255.250:4001``) and listens
on ``:4002`` for device announcements, then resolves the correct IP by matching
the configured ``device_ref`` / expected SKU. It is best-effort: any socket error
returns no devices so the caller falls back to the configured static IP. Ported
from ``experiments/govee_h612d_realtime_probe/lan_scan.py``.
"""
from __future__ import annotations

import json
import logging
import socket
import struct
import time
from typing import Callable, Optional, Sequence

log = logging.getLogger(__name__)

MULTICAST_GROUP = "239.255.255.250"
SCAN_PORT = 4001
RECV_PORT = 4002

_SCAN_MESSAGE = json.dumps(
    {"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}
).encode("utf-8")


def discover_devices(timeout_s: float = 3.0) -> list[dict]:
    """Multicast-scan the LAN for Govee devices.

    Returns a list of ``{"ip", "device", "sku"}`` dicts (one per responding IP).
    Never raises: on any socket failure it logs and returns ``[]`` so realtime
    startup degrades to the configured static IP.
    """
    recv_sock: socket.socket | None = None
    send_sock: socket.socket | None = None
    try:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass  # SO_REUSEPORT is platform-specific; not required for a one-shot scan.
        recv_sock.bind(("", RECV_PORT))
        mreq = struct.pack(
            "4s4s", socket.inet_aton(MULTICAST_GROUP), socket.inet_aton("0.0.0.0")
        )
        recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        recv_sock.settimeout(0.5)

        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        send_sock.sendto(_SCAN_MESSAGE, (MULTICAST_GROUP, SCAN_PORT))

        devices: list[dict] = []
        seen_ips: set[str] = set()
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        while time.monotonic() < deadline:
            try:
                data, addr = recv_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                log.warning("[GOVEE-DISC] recv failed err=%s", exc)
                break
            ip = addr[0]
            if ip in seen_ips:
                continue
            seen_ips.add(ip)
            try:
                payload = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            msg_data = payload.get("msg", {}).get("data", {})
            devices.append(
                {
                    "ip": ip,
                    "device": str(msg_data.get("device", "")),
                    "sku": str(msg_data.get("sku", "")),
                }
            )
        return devices
    except OSError as exc:
        log.warning("[GOVEE-DISC] scan failed err=%s", exc)
        return []
    finally:
        for sock in (recv_sock, send_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


def select_device_ip(
    devices: Sequence[dict],
    configured_ip: str,
    *,
    device_ref: str = "",
    expected_sku: str = "",
) -> tuple[str, str]:
    """Pure selection: pick the best IP from a scan result.

    Preference order: exact ``device_ref`` match, then ``expected_sku`` match,
    then a lone device, otherwise the configured IP. Returns ``(ip, source)``
    where source is one of ``device_ref`` / ``sku`` / ``sole_device`` /
    ``config`` / ``ambiguous``.
    """
    if not devices:
        return (configured_ip, "config")

    if device_ref:
        for dv in devices:
            if str(dv.get("device", "")).upper() == device_ref.upper():
                return (str(dv.get("ip") or configured_ip), "device_ref")

    if expected_sku:
        sku_matches = [
            dv for dv in devices if str(dv.get("sku", "")).upper() == expected_sku.upper()
        ]
        if len(sku_matches) == 1:
            return (str(sku_matches[0].get("ip") or configured_ip), "sku")
        if len(sku_matches) > 1:
            # Multiple same-model strips and no device_ref hit: don't guess.
            return (configured_ip, "ambiguous")

    if len(devices) == 1:
        return (str(devices[0].get("ip") or configured_ip), "sole_device")

    return (configured_ip, "ambiguous")


def resolve_realtime_ip(
    configured_ip: str,
    *,
    device_ref: str = "",
    expected_sku: str = "",
    timeout_s: float = 3.0,
    discover: Optional[Callable[[float], list[dict]]] = None,
) -> tuple[str, str]:
    """Resolve the realtime device IP, preferring live discovery over config.

    Returns ``(ip, source)``. Falls back to ``configured_ip`` (source
    ``"config"`` / ``"ambiguous"``) when discovery finds nothing or can't
    disambiguate. ``discover`` is injectable for tests.
    """
    scan = discover or discover_devices
    devices = scan(timeout_s)
    return select_device_ip(
        devices, configured_ip, device_ref=device_ref, expected_sku=expected_sku
    )
