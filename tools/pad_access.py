"""LAN-access helpers shared by the LED Pad and Laser Pad web UIs.

Provides a same-network "Open on another device" affordance: a best-effort
LAN IP detection plus a payload describing whether the currently bound host
is loopback-only or reachable from other devices on the network.

This module NEVER changes bind behavior by itself. It only reports the
state of a server that has already bound to some host/port; the decision to
bind non-loopback stays an explicit operator action made elsewhere (e.g.
``--host lan`` on the pad CLIs).
"""

from __future__ import annotations

import ipaddress
import socket


def detect_lan_ip() -> str | None:
    """Best-effort LAN IP detection via the UDP-connect trick.

    Opens a UDP socket and "connects" it to a public address purely so the
    OS picks a local interface/IP for routing; no packets are actually sent
    (UDP connect() only sets the default peer for the socket, no I/O
    happens). Returns ``None`` if detection fails (e.g. no network).
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        return None


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def access_payload(bound_host: str, port: int) -> dict:
    """Describe how a pad server bound at ``bound_host``:``port`` can be reached.

    Never raises on LAN-detection failure: ``lan_url`` is simply ``None``
    when detection is unavailable, so callers can surface this as a UI
    state instead of a 500.
    """
    loopback_only = _is_loopback_host(bound_host)
    lan_url: str | None = None
    if not loopback_only:
        if bound_host in ("0.0.0.0", "::"):
            lan_ip = detect_lan_ip()
            if lan_ip is not None:
                lan_url = f"http://{lan_ip}:{port}/"
        else:
            lan_url = f"http://{bound_host}:{port}/"
    return {
        "ok": True,
        "bound_host": bound_host,
        "port": port,
        "loopback_only": loopback_only,
        "lan_url": lan_url,
    }
