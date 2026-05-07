"""
Direct Rekordbox state reader — experimental TimecodeLink corroboration.

Polls Rekordbox memory at ~30 Hz and emits the same ``BridgeEvent`` kinds the
``TLLogTailer`` does today (``MASTER_CHANGED``, ``TRACK_LOADED``, ``PLAY``,
``PAUSE``, ``BPM_UPDATE``). This reader is for shadow validation and parity
analysis until live sessions prove it can match TL safely. TL remains the
authoritative source for DeckState, lighting, and routing unless a later,
explicit promotion changes that contract.

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
* Diff against last-seen state to suppress duplicate events. Each emit carries
  ``source='rb_state'`` so shadow-mode wiring can keep these events out of the
  authoritative StateManager path.

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
import re
import struct
import threading
import time
from dataclasses import dataclass
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
RB_MASTER_DIRECT_SOURCE = "offset_table"
RB_MASTER_TL_SOURCE = "tl_log"

# RB deck index (0..3) → bridge deck (1 or 2). Same mapping as tl_tailer.
def _bridge_deck(rb_idx: int) -> int:
    return (rb_idx % 2) + 1


# Whether the same BPM should be re-emitted (matches tl_tailer / state_manager
# tolerance).
_BPM_EMIT_THRESHOLD = 0.05
_PLAY_WARMUP_POLLS = 3
_PLAY_EVIDENCE_POLLS = 2
_TRACK_INFO_FIELD_RE = re.compile(r"(?:^|\n)\s*(?:[A-Za-z]\s+)?Title:\s*(.*?)(?:\r?\n|$)")


def extract_track_title(track_info: object) -> str:
    """Extract TL-comparable title text from RB's packed track-info buffer."""
    text = str(track_info or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    m = _TRACK_INFO_FIELD_RE.search(text)
    if m:
        return m.group(1).strip()
    return text


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
        self._valid_pos_polls: dict[int, int] = {}
        self._pending_playing: dict[int, bool] = {}
        self._pending_playing_count: dict[int, int] = {}

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
        track_info = self._follow_string(task, base, offs.track_info_per_deck[d], 500)
        if track_info is not None:
            title = extract_track_title(track_info)
            if title and title != self._last_track.get(d):
                self._last_track[d] = title
                self._enqueue(BridgeEvent(
                    kind=Ev.TRACK_LOADED,
                    deck=bridge,
                    payload={'title': title},
                    source='rb_state',
                ))
            elif not title:
                self._last_track.pop(d, None)

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
            self._reset_play_inference(d)
            return
        prev = self._last_pos_samples.get(d)
        self._last_pos_samples[d] = pos
        self._valid_pos_polls[d] = self._valid_pos_polls.get(d, 0) + 1
        if prev is None:
            # First poll: cannot infer movement yet.
            return
        if self._valid_pos_polls[d] <= _PLAY_WARMUP_POLLS:
            self._pending_playing.pop(d, None)
            self._pending_playing_count.pop(d, None)
            return

        is_playing = pos != prev
        was_playing = self._last_playing.get(d)
        pending = self._pending_playing.get(d)
        if pending == is_playing:
            self._pending_playing_count[d] = self._pending_playing_count.get(d, 0) + 1
        else:
            self._pending_playing[d] = is_playing
            self._pending_playing_count[d] = 1

        if self._pending_playing_count[d] < _PLAY_EVIDENCE_POLLS:
            return
        self._pending_playing_count[d] = 0

        if was_playing is None:
            self._last_playing[d] = is_playing
            return
        if was_playing != is_playing:
            self._last_playing[d] = is_playing
            self._enqueue(BridgeEvent(
                kind=Ev.PLAY if is_playing else Ev.PAUSE,
                deck=bridge,
                source='rb_state',
            ))

    def _reset_play_inference(self, d: int) -> None:
        self._last_pos_samples.pop(d, None)
        self._valid_pos_polls[d] = 0
        self._pending_playing.pop(d, None)
        self._pending_playing_count.pop(d, None)

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


@dataclass(frozen=True)
class DirectMasterStatus:
    """One-shot direct master-deck read status.

    This is intentionally observational. It does not enqueue events and does
    not change StateManager authority; callers can use it for startup visibility
    and future arbitration readiness.
    """

    attempted: bool
    supported: bool
    available: bool
    readable: bool
    source: str
    reason: str
    rb_version: str = ""
    rb_raw: Optional[int] = None
    bridge_deck: Optional[int] = None
    pid: Optional[int] = None
    base: Optional[int] = None


@dataclass(frozen=True)
class DirectMasterObservation:
    """Bounded startup observation result for direct master corroboration."""

    initial: DirectMasterStatus
    final: DirectMasterStatus
    attempts: int
    outcome: str


def read_direct_master_status(
    rb_version: str,
    *,
    rb_pid: Optional[int] = None,
    base_addr: Optional[int] = None,
) -> DirectMasterStatus:
    """Read the current RB master byte once through the offset table.

    Fail-closed semantics:
      * unsupported RB version -> unavailable
      * attach failure -> unavailable
      * unreadable/null chain -> unavailable
      * 0xFF/no-master sentinel -> readable but no bridge deck

    The returned status is for logging/status only. It must not be used to
    mutate StateManager without an explicit master-only arbitration step.
    """
    offs = load_offsets_for_version(rb_version)
    if offs is None:
        log.info("[RBMASTER][DIRECT] attempted=1 supported_version=0 readable=0 "
                 "version=%s direct_master=unavailable fail_closed_reason=unsupported_version "
                 "authority=tl_log",
                 rb_version or "<unknown>")
        return DirectMasterStatus(
            attempted=True,
            supported=False,
            available=False,
            readable=False,
            source=RB_MASTER_TL_SOURCE,
            reason="unsupported_version",
            rb_version=rb_version,
        )

    reader = RBStateReader(queue.Queue(maxsize=1), offs, rb_pid=rb_pid, base_addr=base_addr)
    try:
        task, base = reader._attach()
    except Exception as exc:
        log.info("[RBMASTER][DIRECT] attempted=1 supported_version=1 readable=0 "
                 "version=%s direct_master=unavailable fail_closed_reason=attach_failed "
                 "detail=%s authority=tl_log",
                 offs.version,
                 exc)
        return DirectMasterStatus(
            attempted=True,
            supported=True,
            available=False,
            readable=False,
            source=RB_MASTER_TL_SOURCE,
            reason="attach_failed",
            rb_version=offs.version,
        )

    master_raw = reader._follow_u8(task, base, offs.master_deck)
    if master_raw is None:
        log.info("[RBMASTER][DIRECT] attempted=1 supported_version=1 readable=0 "
                 "version=%s direct_master=unavailable fail_closed_reason=unreadable "
                 "authority=tl_log",
                 offs.version)
        return DirectMasterStatus(
            attempted=True,
            supported=True,
            available=False,
            readable=False,
            source=RB_MASTER_TL_SOURCE,
            reason="unreadable",
            rb_version=offs.version,
            pid=reader._rb_pid,
            base=base,
        )

    bridge_deck = _bridge_deck(master_raw) if 0 <= master_raw < offs.deck_count else None
    reason = "ok" if bridge_deck is not None else "no_master"
    log.info("[RBMASTER][DIRECT] attempted=1 supported_version=1 readable=1 "
             "version=%s raw=%d direct_master=%s reason=%s source=%s authority=tl_log",
             offs.version, master_raw, direct_master_label(bridge_deck), reason,
             RB_MASTER_DIRECT_SOURCE)
    return DirectMasterStatus(
        attempted=True,
        supported=True,
        available=True,
        readable=True,
        source=RB_MASTER_DIRECT_SOURCE,
        reason=reason,
        rb_version=offs.version,
        rb_raw=master_raw,
        bridge_deck=bridge_deck,
        pid=reader._rb_pid,
        base=base,
    )


def observe_direct_master_startup(
    rb_version: str,
    *,
    settle_s: float = 3.0,
    interval_s: float = 0.25,
    rb_pid: Optional[int] = None,
    base_addr: Optional[int] = None,
    clock=time.monotonic,
    sleeper=time.sleep,
) -> DirectMasterObservation:
    """Observe direct master briefly at startup until a real deck appears.

    This is observational only. It attaches once, polls the versioned master
    byte for a short bounded window, and returns the first non-sentinel master
    if it appears. TL/ENGINE STATE remains authoritative regardless of outcome.
    """
    offs = load_offsets_for_version(rb_version)
    if offs is None:
        status = DirectMasterStatus(
            attempted=True,
            supported=False,
            available=False,
            readable=False,
            source=RB_MASTER_TL_SOURCE,
            reason="unsupported_version",
            rb_version=rb_version,
        )
        log.info("[RBMASTER][DIRECT] phase=initial attempted=1 supported_version=0 "
                 "readable=0 version=%s direct_master=unavailable "
                 "fail_closed_reason=unsupported_version authority=tl_log",
                 rb_version or "<unknown>")
        return DirectMasterObservation(status, status, 1, "fail_closed")

    reader = RBStateReader(queue.Queue(maxsize=1), offs, rb_pid=rb_pid, base_addr=base_addr)
    try:
        task, base = reader._attach()
    except Exception as exc:
        status = DirectMasterStatus(
            attempted=True,
            supported=True,
            available=False,
            readable=False,
            source=RB_MASTER_TL_SOURCE,
            reason="attach_failed",
            rb_version=offs.version,
        )
        log.info("[RBMASTER][DIRECT] phase=initial attempted=1 supported_version=1 "
                 "readable=0 version=%s direct_master=unavailable "
                 "fail_closed_reason=attach_failed detail=%s authority=tl_log",
                 offs.version, exc)
        return DirectMasterObservation(status, status, 1, "fail_closed")

    deadline = clock() + max(0.0, settle_s)
    attempts = 0
    initial: Optional[DirectMasterStatus] = None
    last: Optional[DirectMasterStatus] = None

    while True:
        attempts += 1
        status = _read_direct_master_from_attached(reader, task, base, offs)
        last = status
        if initial is None:
            initial = status
            log.info("[RBMASTER][DIRECT] phase=initial attempted=1 supported_version=1 "
                     "readable=%s version=%s raw=%s direct_master=%s reason=%s "
                     "authority=tl_log",
                     "1" if status.readable else "0",
                     status.rb_version,
                     status.rb_raw if status.rb_raw is not None else "-",
                     direct_master_label(status.bridge_deck) if status.readable else "unavailable",
                     status.reason)
        if status.bridge_deck in (1, 2):
            phase = "settled" if attempts > 1 else "initial"
            log.info("[RBMASTER][DIRECT] phase=%s attempts=%d supported_version=1 "
                     "readable=1 version=%s raw=%d direct_master=%s reason=ok "
                     "authority=tl_log",
                     phase, attempts, status.rb_version, status.rb_raw or 0,
                     direct_master_label(status.bridge_deck))
            return DirectMasterObservation(initial, status, attempts, "settled")
        if not status.readable:
            log.info("[RBMASTER][DIRECT] phase=expired attempts=%d supported_version=1 "
                     "readable=0 version=%s direct_master=unavailable "
                     "fail_closed_reason=%s authority=tl_log",
                     attempts, status.rb_version, status.reason)
            return DirectMasterObservation(initial, status, attempts, "fail_closed")
        now = clock()
        if now >= deadline:
            log.info("[RBMASTER][DIRECT] phase=expired attempts=%d supported_version=1 "
                     "readable=1 version=%s raw=%s direct_master=%s reason=%s "
                     "authority=tl_log",
                     attempts, status.rb_version,
                     status.rb_raw if status.rb_raw is not None else "-",
                     direct_master_label(status.bridge_deck), status.reason)
            return DirectMasterObservation(initial, status, attempts, "no_master_persisted")
        sleeper(min(interval_s, max(0.0, deadline - now)))


def _read_direct_master_from_attached(
    reader: RBStateReader,
    task: int,
    base: int,
    offs: RBOffsetVersion,
) -> DirectMasterStatus:
    master_raw = reader._follow_u8(task, base, offs.master_deck)
    if master_raw is None:
        return DirectMasterStatus(
            attempted=True,
            supported=True,
            available=False,
            readable=False,
            source=RB_MASTER_TL_SOURCE,
            reason="unreadable",
            rb_version=offs.version,
            pid=reader._rb_pid,
            base=base,
        )
    bridge_deck = _bridge_deck(master_raw) if 0 <= master_raw < offs.deck_count else None
    return DirectMasterStatus(
        attempted=True,
        supported=True,
        available=True,
        readable=True,
        source=RB_MASTER_DIRECT_SOURCE,
        reason="ok" if bridge_deck is not None else "no_master",
        rb_version=offs.version,
        rb_raw=master_raw,
        bridge_deck=bridge_deck,
        pid=reader._rb_pid,
        base=base,
    )


def direct_master_label(deck: Optional[int]) -> str:
    """Return compact log text for a bridge master deck value."""
    if deck in (1, 2):
        return f"deck{deck}"
    if deck in (None, 0):
        return "none"
    return "unavailable"


def direct_master_corroboration(status: DirectMasterStatus, tl_startup_deck: int) -> str:
    """Classify direct master vs TL startup state for one-shot validation logs."""
    if not status.available or not status.readable:
        return "no_direct"
    if status.bridge_deck is None:
        return "no_master"
    if tl_startup_deck not in (1, 2):
        return "no_tl"
    if status.bridge_deck == tl_startup_deck:
        return "agree"
    return "disagree"


def direct_master_summary_fields(status: DirectMasterStatus, tl_startup_deck: int) -> dict[str, str]:
    """Return stable, compact fields for direct-master live validation."""
    fail_closed_reason = "" if status.available and status.readable else status.reason
    return {
        "direct_probe_attempted": "1" if status.attempted else "0",
        "supported_version": "1" if status.supported else "0",
        "readable": "1" if status.readable else "0",
        "version": status.rb_version or "<unknown>",
        "direct_source": status.source,
        "direct_master": (
            direct_master_label(status.bridge_deck)
            if status.available and status.readable
            else "unavailable"
        ),
        "direct_raw": str(status.rb_raw) if status.rb_raw is not None else "-",
        "tl_startup_master": direct_master_label(tl_startup_deck),
        "corroboration": direct_master_corroboration(status, tl_startup_deck),
        "fail_closed_reason": fail_closed_reason or "-",
    }


def direct_master_observation_summary_fields(
    observation: DirectMasterObservation,
    tl_startup_deck: int,
) -> dict[str, str]:
    fields = direct_master_summary_fields(observation.final, tl_startup_deck)
    fields["attempts"] = str(observation.attempts)
    fields["outcome"] = observation.outcome
    fields["initial_direct_master"] = (
        direct_master_label(observation.initial.bridge_deck)
        if observation.initial.readable else "unavailable"
    )
    fields["initial_raw"] = (
        str(observation.initial.rb_raw)
        if observation.initial.rb_raw is not None else "-"
    )
    return fields


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
