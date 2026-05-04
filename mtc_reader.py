"""
MIDI Time Code reader for absolute track position.

MTCReader listens on IAC Driver Bus 1 for MTC quarter-frame and full-frame
SysEx messages from Rekordbox and posts TC_UPDATE events to the bridge event
queue at ~25 fps.

Used as a higher-frequency position fallback for the active deck when direct
memory reading (PositionCache) has no snapshot — e.g. when the deck-2 ObjC
inner pointer scan has not yet resolved.

When memory does resolve, StateManager ignores TC_UPDATE in favour of the live
PositionSnapshot — no special logic required here.

MTC is always from the master/active deck, so get_active_deck() is called on
each publish to route the TC_UPDATE to the correct bridge deck.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from .models import BridgeEvent, Ev

log = logging.getLogger("mtc_reader")

_PORT_SUBSTR = "IAC Driver Bus 1"
_FPS_TABLE   = {0: 24.0, 1: 25.0, 2: 29.97, 3: 30.0}
_RETRY_S     = 5.0
_LOG_INTERVAL_S = 5.0   # rate-limit timecode log lines


class MTCReader:
    """Reads MTC from IAC Bus 1 and posts TC_UPDATE events at ~25 fps.

    Quarter-frame messages (8 per frame) are assembled into complete timestamps.
    Full-frame SysEx is handled for immediate updates after a cue jump.

    Degrades gracefully if mido is not installed or IAC Bus 1 is unavailable.
    """

    def __init__(
        self,
        event_queue:     queue.Queue[BridgeEvent],
        get_active_deck: Callable[[], int],
    ) -> None:
        self._queue           = event_queue
        self._get_active_deck = get_active_deck
        self._stop            = threading.Event()
        # Quarter-frame accumulator: index = message type (0-7), value = nibble (0-15)
        self._qf: list[Optional[int]] = [None] * 8
        self._last_log: float = 0.0

    def start(self) -> None:
        threading.Thread(target=self._run, name="mtc-reader", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import mido  # type: ignore
        except ImportError:
            log.warning("MTCReader: mido not installed — MTC position fallback disabled")
            return

        while not self._stop.is_set():
            ports = mido.get_input_names()
            port_name = next((p for p in ports if _PORT_SUBSTR in p), None)
            if not port_name:
                log.warning("MTCReader: %s not found — retry in %.0fs", _PORT_SUBSTR, _RETRY_S)
                self._stop.wait(_RETRY_S)
                continue

            log.info("MTCReader: opening %s", port_name)
            try:
                with mido.open_input(port_name) as port:
                    log.info("MTCReader: listening for MTC on %s", port_name)
                    self._qf = [None] * 8
                    while not self._stop.is_set():
                        for msg in port.iter_pending():
                            self._handle(msg)
                        time.sleep(0.002)   # 2 ms poll — well under 40 ms frame interval
            except Exception as exc:
                log.warning("MTCReader: port error: %s — retry in %.0fs", exc, _RETRY_S)
                self._stop.wait(_RETRY_S)

    def _handle(self, msg) -> None:
        if msg.type == 'quarter_frame':
            self._qf[msg.frame_type] = msg.frame_value
            # Type 7 is the last message of a complete 8-message sequence.
            if msg.frame_type == 7 and all(v is not None for v in self._qf):
                self._publish_qf()
                self._qf = [None] * 8

        elif msg.type == 'sysex':
            # Full-frame: F0 7F <dev> 01 01 hr mn sc fr F7
            # mido strips F0/F7, so data = [0x7F, <dev>, 0x01, 0x01, hr, mn, sc, fr]
            d = msg.data
            if len(d) >= 8 and d[2] == 0x01 and d[3] == 0x01:
                self._publish_ff(d[4], d[5], d[6], d[7])

    def _publish_qf(self) -> None:
        q       = self._qf
        frames  = (q[1] << 4) | q[0]
        seconds = (q[3] << 4) | q[2]
        minutes = (q[5] << 4) | q[4]
        hours   = ((q[7] & 0x01) << 4) | q[6]
        fps     = _FPS_TABLE.get((q[7] >> 1) & 0x03, 25.0)
        self._post(int((hours * 3600 + minutes * 60 + seconds) * 1000 + frames * 1000.0 / fps))

    def _publish_ff(self, hr: int, mn: int, sc: int, fr: int) -> None:
        fps   = _FPS_TABLE.get((hr >> 5) & 0x03, 25.0)
        hours = hr & 0x1F
        self._post(int((hours * 3600 + mn * 60 + sc) * 1000 + fr * 1000.0 / fps))

    def _post(self, elapsed_ms: int) -> None:
        if elapsed_ms <= 0:
            return
        deck = self._get_active_deck()
        now  = time.monotonic()
        if now - self._last_log >= _LOG_INTERVAL_S:
            self._last_log = now
            mm, ss = divmod(elapsed_ms // 1000, 60)
            ms     = elapsed_ms % 1000
            log.debug("MTC deck %d: %d:%02d.%03d", deck, mm, ss, ms)
        try:
            self._queue.put_nowait(BridgeEvent(
                kind=Ev.TC_UPDATE,
                deck=deck,
                payload={'elapsed_ms': elapsed_ms, 'pitch_factor': 1.0},
                source='mtc',
            ))
        except queue.Full:
            pass
