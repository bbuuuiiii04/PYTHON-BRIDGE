"""
Direct Rekordbox state reader — TimecodeLink-equivalent.

Polls Rekordbox memory at ~30 Hz and emits the same ``BridgeEvent`` kinds the
``TLLogTailer`` does today (``MASTER_CHANGED``, ``TRACK_LOADED``, ``PLAY``,
``PAUSE``, ``BPM_UPDATE``). Eliminates the dependency on TL's log file as the
authoritative event source.

Architecture
------------
* One daemon thread, period = ``MEM_POLL_HZ // 2`` Hz (default 30 Hz, matching
  TL's own poll cadence).
* Reads through pointer chains from a per-version ``RBOffsetVersion`` table
  (see ``rb_offsets.py``), via ``mach_vm_read_overwrite`` (same primitive
  ``rb_memory.py`` already uses).
* Fail-closed: if the running RB version has no offsets in the table, or the
  RB pid / base address cannot be resolved, the thread logs once and exits.
  ``StateManager`` continues running on ``TLLogTailer`` alone.
* Diff against last-seen state to suppress duplicate events. Each emit
  carries ``source='rb_state'`` so the StateManager and consumers can
  differentiate from ``source='tl_log'``.

Play / pause derivation
-----------------------
TL itself does not read a play-state byte. It reads a per-deck monotonic
position field (``OffsetVersion+0x60`` chain → ``readInt64`` → samples) and
infers ``isPlaying = (current != previous)``. We mirror that exactly.

Bridge-deck mapping
-------------------
RB has 4 decks A/B/C/D (0..3). The bridge has 2 decks (left=1, right=2).
Mapping comes from ``tl_tailer._bridge_deck``: A/C → 1, B/D → 2.
"""
from __future__ import annotations

import logging
import os
import queue
import struct
import threading
import time
from typing import Optional

from .config import MEM_POLL_HZ
from .models import BridgeEvent, Ev
from .rb_memory import (
    _base_from_vmmap,
    _get_vmmap_output,
    _read_bytes,
    _task_for_pid,
    get_rb_pid,
)
from .rb_offsets import ChainEntry, RBOffsetVersion, load_offsets_for_version

log = logging.getLogger("rb_state")

_RB_STATE_DISABLE_ENV = "RBSS_RB_STATE_DISABLE"

# RB deck index (0..3) → bridge deck (1 or 2). Same mapping as tl_tailer.
def _bridge_deck(rb_idx: int) -> int:
    return (rb_idx % 2) + 1


# Whether the same BPM should be re-emitted (matches tl_tailer / state_manager
# tolerance).
_BPM_EMIT_THRESHOLD = 0.05


class RBStateReader(threading.Thread):
    """Daemon thread that emits BridgeEvents derived from direct RB memory reads.

    Lifecycle is identical to ``TLLogTailer``: instantiate, ``start()``,
    consumer reads from the same queue ``StateManager`` already wires up.

    The instance is **safely a no-op** when offsets for the current RB version
    are missing — ``run()`` exits immediately without attaching to RB.
    """

    def __init__(
        self,
        event_queue: queue.Queue,
        offsets: Optional[RBOffsetVersion],
        *,
        rb_pid: Optional[int] = None,
        base_addr: Optional[int] = None,
        poll_hz: Optional[int] = None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        super().__init__(name="rb-state-reader", daemon=True)
        self._q = event_queue
        self._offs = offsets
        self._stop = threading.Event()
        hz = poll_hz if poll_hz is not None else max(1, MEM_POLL_HZ // 2)
        self._period = 1.0 / hz
        self._rb_pid = rb_pid
        self._base = base_addr
        self._clock = clock
        self._sleeper = sleeper

        # Per-deck last-seen state for diffing
        self._last_master: Optional[int] = None
        self._last_track: dict[int, str] = {}
        self._last_bpm: dict[int, float] = {}
        self._last_pos_samples: dict[int, int] = {}
        self._last_playing: dict[int, bool] = {}

    def stop(self) -> None:
        self._stop.set()

    # ── Thread entry ─────────────────────────────────────────────────────────
    def run(self) -> None:
        if os.getenv(_RB_STATE_DISABLE_ENV):
            log.info("RBStateReader disabled via %s", _RB_STATE_DISABLE_ENV)
            return
        if self._offs is None:
            log.info("RBStateReader: no offsets for current RB version; not starting")
            return
        try:
            task, base = self._attach()
        except Exception:
            log.exception("RBStateReader: attach failed; falling back to TLLogTailer only")
            return
        log.info("RBStateReader: attached pid=%s base=0x%x version=%s",
                 self._rb_pid, base, self._offs.version)

        next_tick = self._clock()
        while not self._stop.is_set():
            try:
                self._tick(task, base)
            except OSError as exc:
                # mach_vm_read_overwrite failed — likely pointer chain broke
                # mid-poll (common during track loads). Single-tick error is OK.
                log.debug("RBStateReader: tick read error: %s", exc)
            except Exception:
                log.exception("RBStateReader: tick crashed; sleeping 1 s")
                self._sleeper(1.0)
                next_tick = self._clock()
                continue
            next_tick += self._period
            sleep = next_tick - self._clock()
            if sleep > 0:
                self._sleeper(sleep)
            else:
                # Missed deadline; resync rather than spinning
                next_tick = self._clock()

    # ── Attach helpers ───────────────────────────────────────────────────────
    def _attach(self) -> tuple[int, int]:
        pid = self._rb_pid if self._rb_pid is not None else get_rb_pid()
        if pid is None:
            raise RuntimeError("Rekordbox pid not found (pgrep -x rekordbox)")
        self._rb_pid = pid
        task = _task_for_pid(pid)
        base = self._base if self._base is not None else _base_from_vmmap(_get_vmmap_output(pid))
        self._base = base
        return task, base

    # ── Per-poll body ────────────────────────────────────────────────────────
    def _tick(self, task: int, base: int) -> None:
        offs = self._offs
        assert offs is not None, "guarded in run()"

        master_raw = self._follow_u8(task, base, offs.master_deck)
        if master_raw is not None and master_raw != self._last_master:
            self._last_master = master_raw
            if 0 <= master_raw < offs.deck_count:
                self._enqueue(BridgeEvent(
                    kind=Ev.MASTER_CHANGED,
                    deck=_bridge_deck(master_raw),
                    source='rb_state',
                ))

        for d in range(offs.deck_count):
            self._tick_deck(task, base, d)

    def _tick_deck(self, task: int, base: int, d: int) -> None:
        offs = self._offs
        assert offs is not None
        bridge = _bridge_deck(d)

        # Track-info string — same chain TL uses for [EVENT] Deck X loaded:.
        # RB stores 500-byte buffer; TL parses "Title - Artist".
        title = self._follow_string(task, base, offs.track_info_per_deck[d], 500)
        if title is not None and title != self._last_track.get(d):
            self._last_track[d] = title
            if title:
                self._enqueue(BridgeEvent(
                    kind=Ev.TRACK_LOADED,
                    deck=bridge,
                    payload={'title': title},
                    source='rb_state',
                ))

        # Live BPM (post-sync, post-tempo).
        bpm = self._follow_float(task, base, offs.bpm_per_deck[d])
        if bpm is not None and bpm > 0:
            prev = self._last_bpm.get(d, 0.0)
            if abs(bpm - prev) > _BPM_EMIT_THRESHOLD:
                self._last_bpm[d] = bpm
                self._enqueue(BridgeEvent(
                    kind=Ev.BPM_UPDATE,
                    deck=bridge,
                    payload={'bpm': bpm},
                    source='rb_state',
                ))

        # Play / pause inference: position field movement between polls.
        pos = self._follow_i64(task, base, offs.live_pos_per_deck[d])
        if pos is None:
            return
        prev = self._last_pos_samples.get(d)
        self._last_pos_samples[d] = pos
        if prev is None:
            # First poll: cannot infer movement yet.
            return
        is_playing = pos != prev
        was_playing = self._last_playing.get(d)
        if was_playing != is_playing:
            self._last_playing[d] = is_playing
            self._enqueue(BridgeEvent(
                kind=Ev.PLAY if is_playing else Ev.PAUSE,
                deck=bridge,
                source='rb_state',
            ))

    # ── Queue helper ─────────────────────────────────────────────────────────
    def _enqueue(self, ev: BridgeEvent) -> None:
        try:
            self._q.put_nowait(ev)
        except queue.Full:
            # Same policy as tl_tailer: drop on overflow rather than block.
            log.warning("RBStateReader: queue full; dropping %s", ev.kind)

    # ── Pointer-chain primitives ─────────────────────────────────────────────
    def _follow_addr(self, task: int, base: int, ch: ChainEntry) -> Optional[int]:
        """Walk the chain and return the resolved final address. None on null deref."""
        addr = base
        for hop in ch.hops:
            try:
                ptr_bytes = _read_bytes(task, addr + hop, 8)
            except OSError:
                return None
            addr = struct.unpack_from("<Q", ptr_bytes)[0]
            if addr == 0:
                return None
        return addr + ch.final_off

    def _follow_u8(self, task: int, base: int, ch: ChainEntry) -> Optional[int]:
        addr = self._follow_addr(task, base, ch)
        if addr is None:
            return None
        try:
            return _read_bytes(task, addr, 1)[0]
        except OSError:
            return None

    def _follow_float(self, task: int, base: int, ch: ChainEntry) -> Optional[float]:
        addr = self._follow_addr(task, base, ch)
        if addr is None:
            return None
        try:
            data = _read_bytes(task, addr, 4)
        except OSError:
            return None
        v = struct.unpack_from("<f", data)[0]
        # Filter out NaN / inf / nonsense (TL also rejects with fallback 120.0f
        # but we'd rather suppress than synthesise).
        if not (0.0 < v < 1000.0):
            return None
        return v

    def _follow_i64(self, task: int, base: int, ch: ChainEntry) -> Optional[int]:
        addr = self._follow_addr(task, base, ch)
        if addr is None:
            return None
        try:
            data = _read_bytes(task, addr, 8)
        except OSError:
            return None
        return struct.unpack_from("<q", data)[0]

    def _follow_string(self, task: int, base: int, ch: ChainEntry, n: int) -> Optional[str]:
        """Read up to n bytes at the chain endpoint and decode as UTF-8 up to NUL."""
        addr = self._follow_addr(task, base, ch)
        if addr is None:
            return None
        try:
            data = _read_bytes(task, addr, n)
        except OSError:
            return None
        nul = data.find(b'\x00')
        if nul >= 0:
            data = data[:nul]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")


# ── Convenience constructor ──────────────────────────────────────────────────

def make_rb_state_reader(
    event_queue: queue.Queue,
    rb_version: str,
    **kwargs,
) -> RBStateReader:
    """Construct an RBStateReader for the current RB version.

    The returned reader is a no-op (run() exits immediately) when
    ``rb_version`` is unsupported. This lets ``__main__.py`` always start the
    reader without a version check, mirroring how ``TLLogTailer`` is always
    started regardless of TL's actual log presence.
    """
    offsets = load_offsets_for_version(rb_version)
    if offsets is None:
        log.info("RBStateReader: RB version %r not in offset table; reader will be a no-op",
                 rb_version)
    return RBStateReader(event_queue, offsets, **kwargs)
