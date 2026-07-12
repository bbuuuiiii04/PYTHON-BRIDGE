"""soundswitch_frame_sender.py — SoundSwitch CH1-CH19 frame expander and DMX sender.

Bridges the SoundSwitch renderer output (19-channel tuples) to the Enttec DMX
Pro wire format.  Physical DMX addresses come exclusively from the fixture_map
argument; addresses are never inferred from channel names.

A zero packet is sent before close on owner-driven stop() / zero_and_stop()
(idle timeout, stale-input, source/player/verifier error, or shutdown),
matching the VLN catchable-exit blackout convention (see enttec_dmx_pro.py
for the HARD KILL HAZARD note).

SoundSwitch pack semantic proof comes from the pack-generation proof gate
(Task 0.5), not from this module or from VLN.
"""
from __future__ import annotations

import logging
import struct
import threading
import time
from typing import Callable, Mapping

from .enttec_dmx_pro import (
    SoundSwitchDmxWorker,
    build_dmx_packet,
    _open_port,
    _ZERO_PACKET,
)

log = logging.getLogger(__name__)

_SS_CHANNEL_COUNT = 19  # SoundSwitch fixture channel count (CH1..CH19)


# ---------------------------------------------------------------------------
# Pure expansion helper
# ---------------------------------------------------------------------------

def expand_ch1_ch19_to_512(
    frame_19: tuple[int, ...],
    fixture_map: Mapping[int, int],
) -> bytearray:
    """Expand a 19-channel SoundSwitch frame into a 512-byte DMX universe.

    Args:
        frame_19: Tuple of exactly 19 channel values (CH1..CH19), each 0-255.
                  If shorter, missing channels default to 0.
        fixture_map: Mapping of {ch_number: dmx_address} where ch_number is
                     1-based (1..19) and dmx_address is 1-based (1..512).
                     Physical addresses come from this map ONLY — names are
                     never used to infer addresses.

    Returns:
        512-byte bytearray with the channel values placed at the correct DMX
        addresses; all other addresses are 0.
    """
    out = bytearray(512)
    for ch_num, dmx_addr in fixture_map.items():
        if not (1 <= ch_num <= _SS_CHANNEL_COUNT):
            continue
        if not (1 <= dmx_addr <= 512):
            continue
        idx = ch_num - 1  # 0-based index into frame_19
        value = frame_19[idx] if idx < len(frame_19) else 0
        out[dmx_addr - 1] = value if isinstance(value, int) and 0 <= value <= 255 else 0
    return out


def _build_artdmx(
    universe: int,
    frame_512: bytes | bytearray,
    sequence: int = 0,
) -> bytes:
    """Build one ArtDMX packet from an already-expanded 512-byte DMX frame."""
    return (
        b"Art-Net\x00"
        + struct.pack("<H", 0x5000)
        + struct.pack(">H", 0x000E)
        + bytes([sequence & 0xFF, 0x00])
        + struct.pack("<H", int(universe) & 0x7FFF)
        + struct.pack(">H", 512)
        + bytes(frame_512[:512]).ljust(512, b"\x00")
    )


# ---------------------------------------------------------------------------
# Frame sender
# ---------------------------------------------------------------------------

class SoundSwitchFrameSender:
    """Wraps a SoundSwitchDmxWorker and exposes a submit() interface.

    The LaserOutputBackend (PackOutputBackend) calls submit() on the 200 Hz
    tick path.  Expansion and mailbox insertion are non-blocking; the worker
    thread handles the actual serial write.

    Args:
        port: Serial port path, forwarded to SoundSwitchDmxWorker.
        port_factory: Injected serial factory (for tests — MUST be provided in
            unit tests so that NO real serial hardware port is opened).
        poll_s: Worker drain cadence in seconds (default 0.02 = 50 Hz).
        idle_blackout_s: Seconds without a submit() call before the worker
            is told to push a zero packet (stale-input safety).  0 disables.
    """

    def __init__(
        self,
        port: str = "",
        *,
        fixture_map: Mapping[int, int],
        port_factory: Callable | None = None,
        poll_s: float = 0.02,
        idle_blackout_s: float = 0.0,
    ) -> None:
        self._port = port
        self._fixture_map = _validated_fixture_map(fixture_map)
        self._idle_blackout_s = idle_blackout_s
        self._ready_event = threading.Event()
        self._startup_error: str | None = None

        actual_port_factory = port_factory or _open_port

        def _tracked_port_factory(port_name: str, **kwargs):
            try:
                handle = actual_port_factory(port_name, **kwargs)
            except Exception as exc:
                # Only the startup window owns readiness / _startup_error.
                if not self._ready_event.is_set():
                    self._startup_error = type(exc).__name__
                    self._ready_event.set()
                raise
            if not self._ready_event.is_set():
                self._ready_event.set()
            return handle

        self._worker = SoundSwitchDmxWorker(
            port,
            port_factory=_tracked_port_factory,
            poll_s=poll_s,
        )
        self._last_submit_ts: float = time.monotonic()
        self._submit_count: int = 0
        self._zero_count: int = 0
        self._stopped = False

        # Optional idle-watchdog thread
        self._idle_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, *, readiness_timeout_s: float = 2.0) -> None:
        """Start only after the serial port is confirmed open, or raise.

        Idempotent: a second start() on an already-running sender is a no-op.
        """
        if self._worker.status().get("running") and self._startup_error is None:
            return
        self._stopped = False
        self._ready_event.clear()
        self._startup_error = None
        self._worker.start()
        if not self._ready_event.wait(timeout=max(0.01, readiness_timeout_s)):
            self.stop()
            raise RuntimeError("SoundSwitch DMX startup readiness timed out")
        if self._startup_error is not None:
            self.stop()
            raise RuntimeError("SoundSwitch DMX port failed to open")
        if self._idle_blackout_s > 0:
            self._idle_thread = threading.Thread(
                target=self._idle_watchdog,
                name="SoundSwitchFrameSender-idle",
                daemon=True,
            )
            self._idle_thread.start()
        log.info("SoundSwitchFrameSender started")

    def stop(self) -> None:
        """Request a clean shutdown: zero packet sent before serial close."""
        if self._stopped:
            return
        self._stopped = True
        self.zero_and_stop()
        log.info("SoundSwitchFrameSender stopped")

    # ------------------------------------------------------------------
    # Hot path
    # ------------------------------------------------------------------

    def submit(self, frame_19: tuple[int, ...]) -> None:
        """Expand frame_19 via the validated fixture map and enqueue it.

        Non-blocking.  The underlying mailbox discards stale frames so
        only the most-recent frame is ever transmitted.

        Physical addresses come from the construction-time fixture map ONLY;
        names are never used.
        """
        if self._stopped:
            return
        dmx_frame = expand_ch1_ch19_to_512(frame_19, self._fixture_map)
        packet = build_dmx_packet(dmx_frame)
        self._worker.put_frame(packet)
        self._last_submit_ts = time.monotonic()
        self._submit_count += 1

    def zero_and_stop(self) -> None:
        """Push a zero packet immediately, then stop the worker.

        Called on idle timeout, error, or owner-driven stop()/shutdown.
        Matches the VLN catchable-exit blackout convention.
        """
        self._stopped = True
        self._worker.put_frame(_ZERO_PACKET)
        self._zero_count += 1
        self._worker.stop()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return a sanitised diagnostic snapshot (non-blocking)."""
        worker_status = self._worker.status()
        return {
            "sender": "SoundSwitchFrameSender",
            "stopped": self._stopped,
            "submit_count": self._submit_count,
            "zero_count": self._zero_count,
            "idle_blackout_s": self._idle_blackout_s,
            "seconds_since_last_submit": round(
                time.monotonic() - self._last_submit_ts, 3
            ),
            "worker": {
                "running": bool(worker_status.get("running", False)),
                "sent_count": int(worker_status.get("sent_count", 0)),
                "error_count": int(worker_status.get("error_count", 0)),
                "has_error": bool(worker_status.get("last_error")),
                "mailbox_depth": int(worker_status.get("mailbox_depth", 0)),
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _idle_watchdog(self) -> None:
        """Push a zero packet if no submit() calls arrive within the timeout."""
        while not self._stopped:
            time.sleep(max(self._idle_blackout_s / 4, 0.1))
            if self._stopped:
                break
            age = time.monotonic() - self._last_submit_ts
            if age >= self._idle_blackout_s:
                log.warning(
                    "SoundSwitchFrameSender: idle %.1fs >= %.1fs — pushing zero packet",
                    age,
                    self._idle_blackout_s,
                )
                self._worker.put_frame(_ZERO_PACKET)
                self._zero_count += 1
                # Reset timer so we don't spam zero packets.
                self._last_submit_ts = time.monotonic()


def _validated_fixture_map(fixture_map: Mapping[int, int]) -> dict[int, int]:
    if not isinstance(fixture_map, Mapping):
        raise ValueError("fixture_map must be a mapping")
    normalized = dict(fixture_map)
    if set(normalized) != set(range(1, _SS_CHANNEL_COUNT + 1)):
        raise ValueError("fixture_map must define exactly CH1..CH19")
    if any(type(address) is not int or not 1 <= address <= 512
           for address in normalized.values()):
        raise ValueError("fixture_map addresses must be integers from 1 to 512")
    if len(set(normalized.values())) != len(normalized):
        raise ValueError("fixture_map addresses must be unique")
    return normalized


__all__ = [
    "expand_ch1_ch19_to_512",
    "_build_artdmx",
    "SoundSwitchFrameSender",
]
