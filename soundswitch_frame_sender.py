"""soundswitch_frame_sender.py — SoundSwitch CH1-CH19 frame expander and DMX sender.

Bridges the SoundSwitch renderer output (19-channel tuples) to the Enttec DMX
Pro wire format.  Physical DMX addresses come exclusively from the fixture_map
argument; addresses are never inferred from channel names.

Idle, stale-input, source/player/verifier error, normal stop, SIGINT, SIGTERM,
or any sender shutdown sends a zero packet before close, matching the VLN
catchable-exit blackout convention (see enttec_dmx_pro.py for the HARD KILL
HAZARD note).

SoundSwitch pack semantic proof comes from the pack-generation proof gate
(Task 0.5), not from this module or from VLN.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .enttec_dmx_pro import (
    SoundSwitchDmxWorker,
    build_dmx_packet,
    _ZERO_PACKET,
)

log = logging.getLogger(__name__)

_SS_CHANNEL_COUNT = 19  # SoundSwitch fixture channel count (CH1..CH19)


# ---------------------------------------------------------------------------
# Pure expansion helper
# ---------------------------------------------------------------------------

def expand_ch1_ch19_to_512(
    frame_19: tuple[int, ...],
    fixture_map: dict[int, int],
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
        out[dmx_addr - 1] = value  # 1-based address → 0-based byte index
    return out


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
        port_factory: Callable | None = None,
        poll_s: float = 0.02,
        idle_blackout_s: float = 0.0,
    ) -> None:
        self._port = port
        self._idle_blackout_s = idle_blackout_s
        self._worker = SoundSwitchDmxWorker(
            port,
            port_factory=port_factory,
            poll_s=poll_s,
        )
        self._last_submit_ts: float = time.monotonic()
        self._submit_count: int = 0
        self._zero_count: int = 0
        self._stopped = False

        # Optional idle-watchdog thread
        self._idle_thread: threading.Thread | None = None
        if idle_blackout_s > 0:
            self._idle_thread = threading.Thread(
                target=self._idle_watchdog,
                name="SoundSwitchFrameSender-idle",
                daemon=True,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the underlying DMX worker and optional idle watchdog."""
        self._worker.start()
        if self._idle_thread is not None and not self._idle_thread.is_alive():
            self._idle_thread.start()
        log.info("SoundSwitchFrameSender started (port=%s)", self._port)

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

    def submit(
        self,
        frame_19: tuple[int, ...],
        fixture_map: dict[int, int],
    ) -> None:
        """Expand frame_19 via fixture_map and enqueue for DMX output.

        Non-blocking.  The underlying mailbox discards stale frames so
        only the most-recent frame is ever transmitted.

        Physical addresses come from fixture_map ONLY; names are never used.
        """
        if self._stopped:
            return
        dmx_frame = expand_ch1_ch19_to_512(frame_19, fixture_map)
        packet = build_dmx_packet(dmx_frame)
        self._worker.put_frame(packet)
        self._last_submit_ts = time.monotonic()
        self._submit_count += 1

    def zero_and_stop(self) -> None:
        """Push a zero packet immediately, then stop the worker.

        Called on idle timeout, error, SIGINT, SIGTERM, or explicit shutdown.
        Matches the VLN catchable-exit blackout convention.
        """
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
            "port": self._port,
            "stopped": self._stopped,
            "submit_count": self._submit_count,
            "zero_count": self._zero_count,
            "idle_blackout_s": self._idle_blackout_s,
            "seconds_since_last_submit": round(
                time.monotonic() - self._last_submit_ts, 3
            ),
            "worker": worker_status,
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


__all__ = [
    "expand_ch1_ch19_to_512",
    "SoundSwitchFrameSender",
]
