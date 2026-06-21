"""enttec_dmx_pro.py — Enttec DMX USB PRO packet framing and serial worker.

Ported from the VirtualLaserNode reference implementation
(~/virtuallasernode/calib/dmx_pro.py, confirmed 2026-06-21).  The packet
framing is byte-equivalent to the VLN reference; any intentional divergence
is noted in comments.

HARD KILL HAZARD (reproduced verbatim from the VLN reference):
  Because the Enttec Pro widget keeps outputting the last frame on its own,
  a HARD-KILLED process leaves the lasers stuck at the last frame — NOT dark.
  Software cannot claim fail-safe for kill -9 / host-death.  A physical kill
  switch / DMX-side power path is the true failsafe.
  On owner-driven stop() the worker pushes a real zero packet to the wire
  before closing.  Signal delivery (__main__ _shutdown) is the bridge owner's
  responsibility — not this module's.

Protocol (confirmed via VLN label-3 round-trip):
  packet = 0x7E | label | len_lsb | len_msb | payload | 0xE7  (len little-endian)
  Send DMX (label 6): payload = start_code(0x00) + 512 channel bytes  =>  len 513
    blackout = 7E 06 01 02 00 <512x00> E7   (518 bytes total)

Channels are 1-based DMX addresses (CH1..CH512); byte index = ch - 1.

Unit tests must NOT open a real serial port.  The port_factory argument is
injectable so tests can substitute a FakeSerial.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — byte-identical to VLN reference
# ---------------------------------------------------------------------------

MSG_START: int = 0x7E
MSG_END: int = 0xE7
LABEL_SEND_DMX: int = 6
DMX_START_CODE: int = 0x00


# ---------------------------------------------------------------------------
# Pure packet framing — byte-equivalent to VLN build_dmx_packet
# ---------------------------------------------------------------------------

def build_dmx_packet(frame_512: bytes | bytearray) -> bytes:
    """Label-6 Send-DMX packet for a 512-byte DMX frame.

    Pure function; unit-tested for byte equivalence with the VLN reference.

    Args:
        frame_512: Up to 512 channel bytes.  Shorter inputs are zero-padded;
                   longer inputs are truncated to 512 bytes.

    Returns:
        518-byte packet:
          [0x7E, 6, 0x01, 0x02, 0x00, ch1..ch512, 0xE7]
    """
    body = bytes([DMX_START_CODE]) + bytes(frame_512[:512]).ljust(512, b"\x00")
    n = len(body)  # always 513
    return bytes([MSG_START, LABEL_SEND_DMX, n & 0xFF, (n >> 8) & 0xFF]) + body + bytes([MSG_END])


# Pre-computed zero packet — byte-equivalent to VLN _ZERO_PACKET.
_ZERO_PACKET: bytes = build_dmx_packet(bytearray(512))


# ---------------------------------------------------------------------------
# Serial port factory (injectable for tests)
# ---------------------------------------------------------------------------

def _open_port(port: str, *, timeout: float = 1.0, write_timeout: float = 2.0):
    """Open an Enttec DMX USB Pro serial port.

    Baud rate is irrelevant for the FT245-based Pro; framing carries meaning.
    The port is opened at 115200 only because the OS requires a value.
    Not called during unit tests — tests inject a FakeSerial via port_factory.
    """
    import serial  # pyserial; optional runtime dep
    return serial.Serial(port, baudrate=115200, timeout=timeout, write_timeout=write_timeout)


# ---------------------------------------------------------------------------
# Mailbox worker — one thread owns the serial port
# ---------------------------------------------------------------------------

class SoundSwitchDmxWorker:
    """Background worker that serialises DMX frame sends to an Enttec DMX Pro.

    The hot path (200 Hz bridge tick) drops frames into a bounded deque
    (maxlen=2, latest-frame-only semantics).  The worker drains the deque at
    its own pace, sending only the most-recent frame per iteration.

    On owner-driven `stop()` the worker pushes a zero packet before closing
    the serial port to reduce the risk of stuck fixtures
    (see HARD KILL HAZARD above).

    Args:
        port: Serial port path (e.g. "/dev/cu.usbserial-XXXX").
        port_factory: Callable returning a serial-like object.  Defaults to
            _open_port.  Inject a FakeSerial in unit tests so that NO real
            hardware port is opened.
        poll_s: Seconds between mailbox drain cycles (default 0.02 = 50 Hz).
    """

    def __init__(
        self,
        port: str,
        *,
        port_factory: Callable | None = None,
        poll_s: float = 0.02,
    ) -> None:
        self._port = port
        self._port_factory: Callable = port_factory or _open_port
        self._poll_s = poll_s

        # Bounded mailbox: latest-frame-only (maxlen=2 absorbs bursts).
        self._mailbox: deque[bytes] = deque(maxlen=2)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._ser = None  # serial handle; only touched inside worker thread

        # Diagnostics
        self._sent_count: int = 0
        self._error_count: int = 0
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SoundSwitchDmxWorker",
            daemon=True,
        )
        self._thread.start()
        log.info("SoundSwitchDmxWorker started on port %s", self._port)

    def stop(self) -> None:
        """Request a clean shutdown (pushes zero packet before close)."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        log.info("SoundSwitchDmxWorker stopped")

    def put_frame(self, packet: bytes) -> None:
        """Drop a pre-built DMX packet into the mailbox (non-blocking)."""
        with self._lock:
            self._mailbox.append(packet)

    def status(self) -> dict:
        """Return a sanitised diagnostic snapshot (non-blocking)."""
        return {
            "worker": "SoundSwitchDmxWorker",
            "port": self._port,
            "running": self._thread is not None and self._thread.is_alive(),
            "sent_count": self._sent_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "mailbox_depth": len(self._mailbox),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._ser = self._port_factory(self._port)
            log.debug("SoundSwitchDmxWorker: serial port opened: %s", self._port)
        except Exception as exc:
            self._last_error = str(exc)
            self._error_count += 1
            log.error("SoundSwitchDmxWorker: failed to open port %s: %s", self._port, exc)
            return

        try:
            while not self._stop_event.is_set():
                packet = self._drain_mailbox()
                if packet is not None:
                    self._send_packet(packet)
                else:
                    time.sleep(self._poll_s)
        finally:
            self._push_zero_and_close()

    def _drain_mailbox(self) -> bytes | None:
        """Pop the latest frame from the mailbox, discarding stale ones."""
        with self._lock:
            if not self._mailbox:
                return None
            latest = self._mailbox[-1]
            self._mailbox.clear()
            return latest

    def _send_packet(self, packet: bytes) -> None:
        if self._ser is None:
            return
        try:
            self._ser.write(packet)
            self._ser.flush()
            self._sent_count += 1
        except Exception as exc:
            self._last_error = str(exc)
            self._error_count += 1
            log.warning("SoundSwitchDmxWorker: write error: %s", exc)

    def _push_zero_and_close(self) -> None:
        """Push a zero packet before closing to reduce stuck-fixture risk.

        HARD KILL HAZARD: this blackout only runs on catchable exits.
        A kill -9 / host crash bypasses this entirely; the Enttec Pro firmware
        will continue autonomously retransmitting the last non-zero frame.
        A physical kill switch / DMX-side power path is the true failsafe.
        """
        if self._ser is None:
            return
        try:
            self._ser.write(_ZERO_PACKET)
            self._ser.flush()
            log.debug("SoundSwitchDmxWorker: zero packet sent before close")
        except Exception as exc:
            log.warning("SoundSwitchDmxWorker: zero packet send failed: %s", exc)
        try:
            self._ser.close()
        except Exception as exc:
            log.warning("SoundSwitchDmxWorker: serial close failed: %s", exc)
        self._ser = None

__all__ = [
    "MSG_START",
    "MSG_END",
    "LABEL_SEND_DMX",
    "DMX_START_CODE",
    "build_dmx_packet",
    "_ZERO_PACKET",
    "SoundSwitchDmxWorker",
]
